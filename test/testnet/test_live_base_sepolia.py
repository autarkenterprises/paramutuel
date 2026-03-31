import json
import os
import subprocess
import time
import unittest
from pathlib import Path


ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
MARKET_CREATED_TOPIC = "0x142b571a3c036b6753710f2ec81868c8ee6e9b3fffc642f94783cf8778ea7388"


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _rpc_url() -> str:
    return _env("RPC_URL_BASE_SEPOLIA") or _env("RPC_URL_SEPOLIA")


def _default_factory_address() -> str:
    config_path = Path(__file__).resolve().parents[2] / "config" / "deployments.json"
    if not config_path.exists():
        return ""
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    return str((data.get("baseSepolia") or {}).get("factoryAddress") or "").strip()


def _run_cast(args: list[str]) -> str:
    redacted_args: list[str] = []
    redact_next = False
    for token in args:
        if redact_next:
            redacted_args.append("<redacted>")
            redact_next = False
            continue
        redacted_args.append(token)
        if token == "--private-key":
            redact_next = True

    proc = subprocess.run(
        ["cast", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"cast {' '.join(redacted_args)} failed\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc.stdout.strip()


def _pending_nonce(rpc_url: str, sender: str) -> int:
    out = _run_cast(["rpc", "--rpc-url", rpc_url, "eth_getTransactionCount", sender, "pending"]).strip()
    try:
        parsed = json.loads(out)
        return int(parsed, 16) if str(parsed).startswith("0x") else int(parsed)
    except json.JSONDecodeError:
        raw = out.strip('"')
        return int(raw, 16) if raw.startswith("0x") else int(raw)


def _send_with_retry(private_key: str, address: str, signature: str, *fn_args: str) -> str:
    rpc = _rpc_url()
    if not rpc or not private_key:
        raise RuntimeError("RPC_URL_BASE_SEPOLIA and a private key are required")

    base_cmd = [
        "send",
        address,
        signature,
        *fn_args,
        "--rpc-url",
        rpc,
        "--private-key",
        private_key,
        "--confirmations",
        "1",
        "--json",
    ]
    try:
        out = _run_cast(base_cmd)
    except RuntimeError as exc:
        message = str(exc).lower()
        if "replacement transaction underpriced" not in message and "nonce too low" not in message:
            raise
        sender = _run_cast(["wallet", "address", "--private-key", private_key])
        nonce = str(_pending_nonce(rpc, sender))
        out = _run_cast([*base_cmd, "--nonce", nonce])

    try:
        payload = json.loads(out)
        tx_hash = payload.get("transactionHash")
        if tx_hash:
            return tx_hash
    except json.JSONDecodeError:
        pass

    for token in out.replace('"', " ").split():
        if token.startswith("0x") and len(token) == 66:
            return token
    raise RuntimeError(f"Unable to parse tx hash from cast output:\n{out}")


def _call(address: str, signature: str, *fn_args: str) -> str:
    rpc = _rpc_url()
    if not rpc:
        raise RuntimeError("RPC_URL_BASE_SEPOLIA (or RPC_URL_SEPOLIA) is required")
    return _run_cast(["call", address, signature, *fn_args, "--rpc-url", rpc]).splitlines()[0].strip()


def _send(address: str, signature: str, *fn_args: str) -> str:
    key = _env("PRIVATE_KEY")
    if not key:
        raise RuntimeError("RPC_URL_BASE_SEPOLIA and PRIVATE_KEY are required for tx mode")
    return _send_with_retry(key, address, signature, *fn_args)


def _send_with_key(private_key: str, address: str, signature: str, *fn_args: str) -> str:
    if not private_key:
        raise RuntimeError("RPC_URL_BASE_SEPOLIA and a private key are required")
    return _send_with_retry(private_key, address, signature, *fn_args)


def _send_expect_failure(private_key: str, address: str, signature: str, *fn_args: str) -> None:
    rpc = _rpc_url()
    if not rpc:
        raise RuntimeError("RPC_URL_BASE_SEPOLIA (or RPC_URL_SEPOLIA) is required")
    proc = subprocess.run(
        ["cast", "send", address, signature, *fn_args, "--rpc-url", rpc, "--private-key", private_key],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0:
        raise AssertionError(
            "Expected transaction to fail, but it succeeded:\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )


def _receipt(tx_hash: str) -> dict:
    rpc = _rpc_url()
    if not rpc:
        raise RuntimeError("RPC_URL_BASE_SEPOLIA (or RPC_URL_SEPOLIA) is required")
    out = _run_cast(["receipt", tx_hash, "--rpc-url", rpc, "--json"])
    return json.loads(out)


def _topic_to_address(topic_word: str) -> str:
    cleaned = topic_word.lower().replace("0x", "")
    return "0x" + cleaned[-40:]


def _extract_created_market_from_receipt(tx_hash: str, factory_address: str) -> str:
    payload = _receipt(tx_hash)
    for log in payload.get("logs", []):
        if str(log.get("address", "")).lower() != factory_address.lower():
            continue
        topics = log.get("topics") or []
        if len(topics) < 2:
            continue
        if str(topics[0]).lower() != MARKET_CREATED_TOPIC:
            continue
        return _topic_to_address(str(topics[1]))
    raise AssertionError(f"MarketCreated event not found in receipt for tx {tx_hash}")


def _as_int(value: str) -> int:
    value = value.strip().split()[0].replace("_", "")
    if value.startswith("0x"):
        return int(value, 16)
    return int(value)


def _as_bool(value: str) -> bool:
    v = value.strip().lower()
    if v in ("true", "1"):
        return True
    if v in ("false", "0"):
        return False
    raise ValueError(f"Expected bool-like value, got: {value}")


def _wait_for_markets_count(factory_address: str, min_expected: int, timeout_seconds: int = 45) -> int:
    deadline = time.time() + timeout_seconds
    last_seen = -1
    while time.time() < deadline:
        last_seen = _as_int(_call(factory_address, "marketsCount()(uint256)"))
        if last_seen >= min_expected:
            return last_seen
        time.sleep(2)
    raise AssertionError(
        f"Timed out waiting for marketsCount >= {min_expected}; last observed {last_seen}"
    )


def _wait_for_bool_value(
    contract_address: str, signature: str, expected: bool, timeout_seconds: int = 45
) -> bool:
    deadline = time.time() + timeout_seconds
    last_seen = None
    while time.time() < deadline:
        last_seen = _as_bool(_call(contract_address, signature))
        if last_seen is expected:
            return last_seen
        time.sleep(2)
    raise AssertionError(
        f"Timed out waiting for {signature} == {expected}; last observed {last_seen}"
    )


def _wait_for_state(
    contract_address: str, expected_state: int, timeout_seconds: int = 45
) -> int:
    deadline = time.time() + timeout_seconds
    last_seen = -1
    while time.time() < deadline:
        last_seen = _as_int(_call(contract_address, "state()(uint8)"))
        if last_seen == expected_state:
            return last_seen
        time.sleep(2)
    raise AssertionError(
        f"Timed out waiting for state == {expected_state}; last observed {last_seen}"
    )


def _parse_units(amount: str, decimals: int) -> int:
    value = amount.strip()
    if not value:
        raise ValueError("Amount cannot be empty")
    if value.count(".") > 1:
        raise ValueError(f"Invalid amount format: {amount}")
    if "." not in value:
        return int(value) * (10 ** decimals)

    whole, frac = value.split(".", 1)
    if not whole:
        whole = "0"
    if len(frac) > decimals:
        raise ValueError(f"Too many decimal places for token decimals={decimals}: {amount}")
    frac_scaled = frac.ljust(decimals, "0")
    return int(whole) * (10 ** decimals) + int(frac_scaled)


class TestBaseSepoliaLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rpc = _rpc_url()
        cls.factory = _env("FACTORY_ADDRESS") or _default_factory_address()
        cls.mode = _env("TESTNET_MODE", "readonly").lower()
        cls.market_address = _env("TESTNET_MARKET_ADDRESS")
        cls.private_key = _env("PRIVATE_KEY")
        cls.collateral_token = _env("TESTNET_COLLATERAL_TOKEN")
        cls.bet_amount = _env("TESTNET_BET_AMOUNT", "1")
        cls.secondary_private_key = _env("TESTNET_SECONDARY_PRIVATE_KEY")
        cls.unauthorized_private_key = _env("TESTNET_UNAUTHORIZED_PRIVATE_KEY")

        if not cls.rpc:
            raise unittest.SkipTest("Set RPC_URL_BASE_SEPOLIA (or RPC_URL_SEPOLIA)")
        if not cls.factory:
            raise unittest.SkipTest("Set FACTORY_ADDRESS or config/deployments.json baseSepolia.factoryAddress")

        cls.sender = ""
        if cls.private_key:
            cls.sender = _run_cast(["wallet", "address", "--private-key", cls.private_key])
        cls.secondary_sender = ""
        if cls.secondary_private_key:
            cls.secondary_sender = _run_cast(["wallet", "address", "--private-key", cls.secondary_private_key])

    def test_factory_view_invariants(self) -> None:
        treasury = _call(self.factory, "treasury()(address)")
        protocol_fee_bps = _as_int(_call(self.factory, "protocolFeeBps()(uint16)"))
        min_betting_window = _as_int(_call(self.factory, "minBettingWindow()(uint64)"))
        min_resolution_window = _as_int(_call(self.factory, "minResolutionWindow()(uint64)"))
        markets_count = _as_int(_call(self.factory, "marketsCount()(uint256)"))

        self.assertNotEqual(treasury.lower(), ZERO_ADDRESS)
        self.assertGreaterEqual(protocol_fee_bps, 0)
        self.assertLessEqual(protocol_fee_bps, 1000)
        self.assertGreaterEqual(min_betting_window, 0)
        self.assertGreaterEqual(min_resolution_window, 0)
        self.assertGreaterEqual(markets_count, 0)

    def test_existing_market_views(self) -> None:
        if not self.market_address:
            self.skipTest("Set TESTNET_MARKET_ADDRESS to run market read checks")

        factory_on_market = _call(self.market_address, "factory()(address)")
        betting_close_time = _as_int(_call(self.market_address, "bettingCloseTime()(uint64)"))
        resolution_window = _as_int(_call(self.market_address, "resolutionWindow()(uint64)"))
        resolution_deadline = _as_int(_call(self.market_address, "resolutionDeadline()(uint64)"))
        state = _as_int(_call(self.market_address, "state()(uint8)"))
        outcomes_count = _as_int(_call(self.market_address, "outcomesCount()(uint256)"))

        self.assertEqual(factory_on_market.lower(), self.factory.lower())
        self.assertGreaterEqual(betting_close_time, 0)
        self.assertGreaterEqual(resolution_window, 0)
        self.assertGreaterEqual(resolution_deadline, 0)
        self.assertIn(state, (0, 1, 2))
        self.assertGreaterEqual(outcomes_count, 2)

    def test_minimal_tx_lifecycle(self) -> None:
        if self.mode != "minimal-tx":
            self.skipTest("Set TESTNET_MODE=minimal-tx to run transaction lifecycle checks")
        if not self.private_key:
            self.skipTest("Set PRIVATE_KEY to run transaction lifecycle checks")

        before_count = _as_int(_call(self.factory, "marketsCount()(uint256)"))
        question = f"live-suite-{int(time.time())}"

        create_tx = _send(
            self.factory,
            "createMarket(address,string,string[],uint64,uint64,address,address,address,address[],uint16[])",
            "0x0000000000000000000000000000000000000001",
            question,
            '["YES","NO"]',
            "0",
            "0",
            ZERO_ADDRESS,
            self.sender,
            self.sender,
            "[]",
            "[]",
        )

        after_count = _wait_for_markets_count(self.factory, before_count + 1)
        self.assertGreaterEqual(after_count, before_count + 1)

        new_market = _extract_created_market_from_receipt(create_tx, self.factory)
        proposer = _call(new_market, "proposer()(address)")
        resolver = _call(new_market, "resolver()(address)")
        betting_closer = _call(new_market, "bettingCloser()(address)")
        resolution_closer = _call(new_market, "resolutionCloser()(address)")

        # Resolver defaults to proposer when zero is passed.
        # Closers are explicitly set to sender for no-max windows.
        self.assertEqual(proposer.lower(), self.sender.lower())
        self.assertEqual(resolver.lower(), self.sender.lower())
        self.assertEqual(betting_closer.lower(), self.sender.lower())
        self.assertEqual(resolution_closer.lower(), self.sender.lower())

        _send(new_market, "closeBetting()")
        betting_closed = _wait_for_bool_value(new_market, "bettingClosedByAuthority()(bool)", True)
        self.assertTrue(betting_closed)

        _send(new_market, "closeResolutionWindow()")
        resolution_closed = _wait_for_bool_value(
            new_market,
            "resolutionWindowClosedByAuthority()(bool)",
            True,
        )
        self.assertTrue(resolution_closed)

        _send(new_market, "expire()")
        state = _wait_for_state(new_market, 2)
        self.assertEqual(state, 2)  # Retracted

    def test_funded_tx_lifecycle_and_claims(self) -> None:
        if self.mode != "funded-tx":
            self.skipTest("Set TESTNET_MODE=funded-tx to run funded lifecycle checks")
        if not self.private_key:
            self.skipTest("Set PRIVATE_KEY to run funded lifecycle checks")
        if not self.collateral_token:
            self.skipTest("Set TESTNET_COLLATERAL_TOKEN to run funded lifecycle checks")

        decimals = _as_int(_call(self.collateral_token, "decimals()(uint8)"))
        amount_raw = _parse_units(self.bet_amount, decimals)
        if amount_raw <= 0:
            self.skipTest("TESTNET_BET_AMOUNT must parse to a positive amount")

        sender_balance = _as_int(_call(self.collateral_token, "balanceOf(address)(uint256)", self.sender))
        if sender_balance < amount_raw:
            self.skipTest(
                f"Connected wallet token balance too low: have {sender_balance}, need {amount_raw}"
            )

        before_count = _as_int(_call(self.factory, "marketsCount()(uint256)"))
        protocol_fee_bps = _as_int(_call(self.factory, "protocolFeeBps()(uint16)"))
        extra_bps = 1 if protocol_fee_bps < 1000 else 0
        extra_recipients = f"[{self.sender}]" if extra_bps > 0 else "[]"
        extra_bps_json = f"[{extra_bps}]" if extra_bps > 0 else "[]"

        # Resolve branch with real collateral + claim + fee withdrawal.
        create_tx_resolve = _send(
            self.factory,
            "createMarket(address,string,string[],uint64,uint64,address,address,address,address[],uint16[])",
            self.collateral_token,
            f"funded-resolve-{int(time.time())}",
            '["YES","NO"]',
            "0",
            "0",
            ZERO_ADDRESS,
            self.sender,
            self.sender,
            extra_recipients,
            extra_bps_json,
        )
        after_count = _wait_for_markets_count(self.factory, before_count + 1)
        self.assertGreaterEqual(after_count, before_count + 1)
        resolve_market = _extract_created_market_from_receipt(create_tx_resolve, self.factory)

        _send(self.collateral_token, "approve(address,uint256)", resolve_market, str(amount_raw))
        _send(resolve_market, "placeBet(uint256,uint256)", "0", str(amount_raw))

        if self.secondary_private_key:
            secondary_balance = _as_int(
                _call(self.collateral_token, "balanceOf(address)(uint256)", self.secondary_sender)
            )
            if secondary_balance >= amount_raw:
                _send_with_key(
                    self.secondary_private_key,
                    self.collateral_token,
                    "approve(address,uint256)",
                    resolve_market,
                    str(amount_raw),
                )
                _send_with_key(
                    self.secondary_private_key,
                    resolve_market,
                    "placeBet(uint256,uint256)",
                    "1",
                    str(amount_raw),
                )

        _send(resolve_market, "closeBetting()")
        _send(resolve_market, "resolve(uint256)", "0")
        _send(resolve_market, "claim()")
        _wait_for_state(resolve_market, 1)
        if extra_bps > 0:
            sender_fee_balance = _as_int(
                _call(resolve_market, "feeBalances(address)(uint256)", self.sender)
            )
            if sender_fee_balance > 0:
                _send(resolve_market, "withdrawFees()")

        # Retract branch with funded bet + claim.
        create_tx_retract = _send(
            self.factory,
            "createMarket(address,string,string[],uint64,uint64,address,address,address,address[],uint16[])",
            self.collateral_token,
            f"funded-retract-{int(time.time())}",
            '["YES","NO"]',
            "0",
            "0",
            ZERO_ADDRESS,
            self.sender,
            self.sender,
            "[]",
            "[]",
        )
        _wait_for_markets_count(self.factory, before_count + 2)
        retract_market = _extract_created_market_from_receipt(create_tx_retract, self.factory)
        _send(self.collateral_token, "approve(address,uint256)", retract_market, str(amount_raw))
        _send(retract_market, "placeBet(uint256,uint256)", "1", str(amount_raw))
        _send(retract_market, "closeBetting()")
        _send(retract_market, "retract()")
        _wait_for_state(retract_market, 2)
        _send(retract_market, "claim()")

        # Expire branch with funded bet + claim.
        create_tx_expire = _send(
            self.factory,
            "createMarket(address,string,string[],uint64,uint64,address,address,address,address[],uint16[])",
            self.collateral_token,
            f"funded-expire-{int(time.time())}",
            '["YES","NO"]',
            "0",
            "0",
            ZERO_ADDRESS,
            self.sender,
            self.sender,
            "[]",
            "[]",
        )
        _wait_for_markets_count(self.factory, before_count + 3)
        expire_market = _extract_created_market_from_receipt(create_tx_expire, self.factory)
        _send(self.collateral_token, "approve(address,uint256)", expire_market, str(amount_raw))
        _send(expire_market, "placeBet(uint256,uint256)", "0", str(amount_raw))
        _send(expire_market, "closeBetting()")
        _send(expire_market, "closeResolutionWindow()")
        _send(expire_market, "expire()")
        _wait_for_state(expire_market, 2)
        _send(expire_market, "claim()")

        # Optional negative-role checks from a non-authorized key.
        if self.unauthorized_private_key:
            create_tx_unauth = _send(
                self.factory,
                "createMarket(address,string,string[],uint64,uint64,address,address,address,address[],uint16[])",
                self.collateral_token,
                f"funded-unauth-{int(time.time())}",
                '["YES","NO"]',
                "0",
                "0",
                ZERO_ADDRESS,
                self.sender,
                self.sender,
                "[]",
                "[]",
            )
            _wait_for_markets_count(self.factory, before_count + 4)
            unauth_market = _extract_created_market_from_receipt(create_tx_unauth, self.factory)
            _send_expect_failure(self.unauthorized_private_key, unauth_market, "closeBetting()")
            _send_expect_failure(self.unauthorized_private_key, unauth_market, "resolve(uint256)", "0")


if __name__ == "__main__":
    unittest.main(verbosity=2)
