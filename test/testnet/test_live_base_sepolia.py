import json
import os
import subprocess
import time
import unittest


ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _rpc_url() -> str:
    return _env("RPC_URL_BASE_SEPOLIA") or _env("RPC_URL_SEPOLIA")


def _run_cast(args: list[str]) -> str:
    proc = subprocess.run(
        ["cast", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"cast {' '.join(args)} failed\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc.stdout.strip()


def _call(address: str, signature: str, *fn_args: str) -> str:
    rpc = _rpc_url()
    if not rpc:
        raise RuntimeError("RPC_URL_BASE_SEPOLIA (or RPC_URL_SEPOLIA) is required")
    return _run_cast(["call", address, signature, *fn_args, "--rpc-url", rpc]).splitlines()[0].strip()


def _send(address: str, signature: str, *fn_args: str) -> str:
    rpc = _rpc_url()
    key = _env("PRIVATE_KEY")
    if not rpc or not key:
        raise RuntimeError("RPC_URL_BASE_SEPOLIA and PRIVATE_KEY are required for tx mode")
    out = _run_cast(
        ["send", address, signature, *fn_args, "--rpc-url", rpc, "--private-key", key, "--json"]
    )
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


def _as_int(value: str) -> int:
    value = value.strip()
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


class TestBaseSepoliaLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rpc = _rpc_url()
        cls.factory = _env("FACTORY_ADDRESS")
        cls.mode = _env("TESTNET_MODE", "readonly").lower()
        cls.market_address = _env("TESTNET_MARKET_ADDRESS")
        cls.private_key = _env("PRIVATE_KEY")

        if not cls.rpc:
            raise unittest.SkipTest("Set RPC_URL_BASE_SEPOLIA (or RPC_URL_SEPOLIA)")
        if not cls.factory:
            raise unittest.SkipTest("Set FACTORY_ADDRESS to run live suite")

        cls.sender = ""
        if cls.private_key:
            cls.sender = _run_cast(["wallet", "address", "--private-key", cls.private_key])

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

        _send(
            self.factory,
            "createMarket(address,string,string[],uint64,uint64,address,address,address,address[],uint16[])",
            "0x0000000000000000000000000000000000000001",
            question,
            '["YES","NO"]',
            "0",
            "0",
            ZERO_ADDRESS,
            ZERO_ADDRESS,
            ZERO_ADDRESS,
            "[]",
            "[]",
        )

        after_count = _as_int(_call(self.factory, "marketsCount()(uint256)"))
        self.assertEqual(after_count, before_count + 1)

        new_market = _call(self.factory, "markets(uint256)(address)", str(after_count - 1))
        proposer = _call(new_market, "proposer()(address)")
        resolver = _call(new_market, "resolver()(address)")
        betting_closer = _call(new_market, "bettingCloser()(address)")
        resolution_closer = _call(new_market, "resolutionCloser()(address)")

        # With zero-address role inputs, proposer should be used for all role addresses.
        self.assertEqual(proposer.lower(), self.sender.lower())
        self.assertEqual(resolver.lower(), self.sender.lower())
        self.assertEqual(betting_closer.lower(), self.sender.lower())
        self.assertEqual(resolution_closer.lower(), self.sender.lower())

        _send(new_market, "closeBetting()")
        betting_closed = _as_bool(_call(new_market, "bettingClosedByAuthority()(bool)"))
        self.assertTrue(betting_closed)

        _send(new_market, "closeResolutionWindow()")
        resolution_closed = _as_bool(_call(new_market, "resolutionWindowClosedByAuthority()(bool)"))
        self.assertTrue(resolution_closed)

        _send(new_market, "expire()")
        state = _as_int(_call(new_market, "state()(uint8)"))
        self.assertEqual(state, 2)  # Retracted


if __name__ == "__main__":
    unittest.main(verbosity=2)
