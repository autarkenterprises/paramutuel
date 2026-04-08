"""Multi-wager, multi-actor stress tests against deployed Base Sepolia contracts.

Modes (STRESS_MODE env):
  - readonly (default): eth_call only; samples latest wagers from the factory.
  - tx: creates STRESS_WAGER_COUNT wagers with distinct delegated roles per wager.
  - funded-tx: tx mode plus real collateral approve/placeBet/claim flows.

See docs/TESTNET-STRESS-SUITE.md for wallet pool generation and funding.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import unittest
from urllib import parse, request
from urllib.error import URLError
from pathlib import Path

from testnet_helpers import (
    DUMMY_COLLATERAL,
    V2_CREATE_WAGER_SIG,
    V2_FUNDED_RESOLVE_CASES,
    V2_MINIMAL_EXPIRE_POLICIES,
    default_factory_v2_address,
)


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


def _call(address: str, signature: str, *fn_args: str) -> str:
    rpc = _rpc_url()
    if not rpc:
        raise RuntimeError("RPC_URL_BASE_SEPOLIA (or RPC_URL_SEPOLIA) is required")
    return _run_cast(["call", address, signature, *fn_args, "--rpc-url", rpc]).splitlines()[0].strip()


def _send_key(private_key: str, address: str, signature: str, *fn_args: str) -> None:
    rpc = _rpc_url()
    if not rpc:
        raise RuntimeError("RPC_URL_BASE_SEPOLIA is required")
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
    ]
    try:
        _run_cast(base_cmd)
    except RuntimeError as exc:
        message = str(exc).lower()
        if "replacement transaction underpriced" not in message and "nonce too low" not in message:
            raise
        sender = _run_cast(["wallet", "address", "--private-key", private_key])
        nonce = str(_pending_nonce(rpc, sender))
        _run_cast([*base_cmd, "--nonce", nonce])


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


def _as_int(value: str) -> int:
    value = value.strip().split()[0].replace("_", "")
    if value.startswith("0x"):
        return int(value, 16)
    return int(value)


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


def _wait_for_wagers_count(factory_address: str, min_expected: int, timeout_seconds: int = 45) -> int:
    deadline = time.time() + timeout_seconds
    last_seen = -1
    while time.time() < deadline:
        last_seen = _as_int(_call(factory_address, "wagersCount()(uint256)"))
        if last_seen >= min_expected:
            return last_seen
        time.sleep(2)
    raise AssertionError(
        f"Timed out waiting for wagersCount >= {min_expected}; last observed {last_seen}"
    )


def _wait_for_state(contract_address: str, expected_state: int, timeout_seconds: int = 45) -> int:
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


def _load_wallet_pool(path: str) -> list[dict[str, str]]:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("wallet pool must be a non-empty JSON array")
    for row in data:
        if "private_key" not in row or "address" not in row:
            raise ValueError("each wallet entry needs address and private_key")
    return data


def _indexer_base_url() -> str:
    explicit = _env("STRESS_INDEXER_BASE_URL")
    if explicit:
        return explicit.rstrip("/")
    config_path = Path(__file__).resolve().parents[2] / "config" / "deployments.json"
    if not config_path.exists():
        return ""
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    return str((data.get("baseSepolia") or {}).get("explorerApiBase") or "").strip().rstrip("/")


def _wait_for_indexer_wager_address(base_url: str, wager_address: str, timeout_seconds: int = 120) -> None:
    deadline = time.time() + timeout_seconds
    needle = wager_address.lower()
    while time.time() < deadline:
        params = parse.urlencode({"q": wager_address, "limit": "10", "order": "desc"})
        try:
            with request.urlopen(f"{base_url}/wagers?{params}", timeout=20) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except (TimeoutError, URLError):
            time.sleep(5)
            continue
        for row in payload.get("wagers", []):
            if str(row.get("wager_address", "")).lower() == needle:
                return
        time.sleep(5)
    raise AssertionError(f"Timed out waiting for wager {wager_address} to appear in indexer search")


def _filtered_stress_v2_cases():
    raw = _env("STRESS_V2_CASES", "").strip()
    if not raw:
        return V2_FUNDED_RESOLVE_CASES
    want = {x.strip() for x in raw.split(",") if x.strip()}
    return tuple(c for c in V2_FUNDED_RESOLVE_CASES if c.case_id in want)


class TestBaseSepoliaStress(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rpc = _rpc_url()
        cls.factory = _env("FACTORY_ADDRESS") or _default_factory_address()
        cls.mode = _env("STRESS_MODE", "readonly").lower()
        cls.sample_wagers = int(_env("STRESS_SAMPLE_WAGERS", "12"))
        cls.wager_count = int(_env("STRESS_WAGER_COUNT", "3"))
        cls.pool_path = _env("STRESS_WALLET_POOL_PATH")
        cls.funder_key = _env("STRESS_FUNDER_PRIVATE_KEY") or _env("PRIVATE_KEY")
        cls.collateral_token = _env("STRESS_COLLATERAL_TOKEN")
        cls.bet_amount = _env("STRESS_BET_AMOUNT", "1")
        cls.unauthorized_private_key = _env("STRESS_UNAUTHORIZED_PRIVATE_KEY")
        cls.indexer_base_url = _indexer_base_url()

        if not cls.rpc:
            raise unittest.SkipTest("Set RPC_URL_BASE_SEPOLIA (or RPC_URL_SEPOLIA)")
        if not cls.factory:
            raise unittest.SkipTest("Set FACTORY_ADDRESS or config/deployments.json baseSepolia.factoryAddress")

    def test_readonly_sample_wagers(self) -> None:
        if self.mode != "readonly":
            self.skipTest("Set STRESS_MODE=readonly (default) for this test")

        total = _as_int(_call(self.factory, "wagersCount()(uint256)"))
        if total == 0:
            self.skipTest("No wagers on factory yet; run tx mode once or deploy wagers first")

        n = min(total, self.sample_wagers)
        for k in range(n):
            idx = total - 1 - k
            wager = _call(self.factory, "wagers(uint256)(address)", str(idx))
            factory_on_wager = _call(wager, "factory()(address)")
            self.assertEqual(factory_on_wager.lower(), self.factory.lower())
            state = _as_int(_call(wager, "state()(uint8)"))
            self.assertIn(state, (0, 1, 2))
            proposer = _call(wager, "proposer()(address)").lower()
            resolver = _call(wager, "resolver()(address)").lower()
            bc = _call(wager, "bettingCloser()(address)").lower()
            rc = _call(wager, "resolutionCloser()(address)").lower()
            self.assertTrue(proposer.startswith("0x"))
            self.assertTrue(resolver.startswith("0x"))
            self.assertTrue(bc.startswith("0x"))
            self.assertTrue(rc.startswith("0x"))

    def test_tx_multi_wager_distinct_roles(self) -> None:
        if self.mode != "tx":
            self.skipTest("Set STRESS_MODE=tx to run on-chain stress creation")

        if not self.pool_path:
            self.skipTest("Set STRESS_WALLET_POOL_PATH to a JSON pool from gen_stress_wallet_pool.py")
        if not self.funder_key:
            self.skipTest("Set STRESS_FUNDER_PRIVATE_KEY or PRIVATE_KEY for expire() and gas")

        pool = _load_wallet_pool(self.pool_path)
        need = self.wager_count * 4
        if len(pool) < need:
            self.skipTest(f"Pool has {len(pool)} wallets; need at least {need} (4 per wager)")

        min_res = _as_int(_call(self.factory, "minResolutionWindow()(uint64)"))

        for i in range(self.wager_count):
            base = i * 4
            w_prop = pool[base]
            w_res = pool[base + 1]
            w_bet_close = pool[base + 2]
            w_res_close = pool[base + 3]

            before = _as_int(_call(self.factory, "wagersCount()(uint256)"))
            proposition = f"stress-{int(time.time())}-{i}"
            # Rotate resolution window: 0 (no max), min_res, min_res — all closable via authority + expire
            res_win = (0, min_res, min_res)[i % 3]

            _send_key(
                w_prop["private_key"],
                self.factory,
                "createWager(address,string,string[],uint64,uint64,address,address,address,address[],uint16[])",
                DUMMY_COLLATERAL,
                proposition,
                '["A","B"]',
                "0",
                str(res_win),
                w_res["address"],
                w_bet_close["address"],
                w_res_close["address"],
                "[]",
                "[]",
            )

            after = _wait_for_wagers_count(self.factory, before + 1)
            self.assertGreaterEqual(after, before + 1)

            wager = _call(self.factory, "wagers(uint256)(address)", str(before))
            self.assertEqual(_call(wager, "proposer()(address)").lower(), w_prop["address"].lower())
            self.assertEqual(_call(wager, "resolver()(address)").lower(), w_res["address"].lower())
            self.assertEqual(_call(wager, "bettingCloser()(address)").lower(), w_bet_close["address"].lower())
            self.assertEqual(_call(wager, "resolutionCloser()(address)").lower(), w_res_close["address"].lower())

            _send_key(w_bet_close["private_key"], wager, "closeBetting()")

            branch = i % 3
            if branch == 0:
                _send_key(w_res_close["private_key"], wager, "closeResolutionWindow()")
                _send_key(self.funder_key, wager, "expire()")
                self.assertEqual(_wait_for_state(wager, 2), 2)
            elif branch == 1:
                _send_key(w_res["private_key"], wager, "resolve(uint256)", "0")
                self.assertEqual(_wait_for_state(wager, 1), 1)
            else:
                _send_key(w_res["private_key"], wager, "retract()")
                self.assertEqual(_wait_for_state(wager, 2), 2)

    def test_funded_tx_multi_wager_roles_and_claims(self) -> None:
        if self.mode != "funded-tx":
            self.skipTest("Set STRESS_MODE=funded-tx to run funded multi-wager stress")
        if not self.pool_path:
            self.skipTest("Set STRESS_WALLET_POOL_PATH to a JSON pool from gen_stress_wallet_pool.py")
        if not self.collateral_token:
            self.skipTest("Set STRESS_COLLATERAL_TOKEN for funded-tx mode")

        pool = _load_wallet_pool(self.pool_path)
        need = self.wager_count * 6
        if len(pool) < need:
            self.skipTest(f"Pool has {len(pool)} wallets; need at least {need} (6 per wager)")

        decimals = _as_int(_call(self.collateral_token, "decimals()(uint8)"))
        amount_raw = _parse_units(self.bet_amount, decimals)
        if amount_raw <= 0:
            self.skipTest("STRESS_BET_AMOUNT must parse to a positive amount")

        min_res = _as_int(_call(self.factory, "minResolutionWindow()(uint64)"))
        before_count = _as_int(_call(self.factory, "wagersCount()(uint256)"))
        first_wager = ""

        for i in range(self.wager_count):
            base = i * 6
            w_prop = pool[base]
            w_res = pool[base + 1]
            w_bet_close = pool[base + 2]
            w_res_close = pool[base + 3]
            w_bettor_yes = pool[base + 4]
            w_bettor_no = pool[base + 5]

            yes_balance = _as_int(
                _call(self.collateral_token, "balanceOf(address)(uint256)", w_bettor_yes["address"])
            )
            no_balance = _as_int(
                _call(self.collateral_token, "balanceOf(address)(uint256)", w_bettor_no["address"])
            )
            if yes_balance < amount_raw or no_balance < amount_raw:
                self.skipTest(
                    f"Insufficient collateral balances for funded-tx on wager {i}: "
                    f"need {amount_raw} on both bettor wallets"
                )

            proposition = f"stress-funded-{int(time.time())}-{i}"
            res_win = (0, min_res, min_res)[i % 3]

            _send_key(
                w_prop["private_key"],
                self.factory,
                "createWager(address,string,string[],uint64,uint64,address,address,address,address[],uint16[])",
                self.collateral_token,
                proposition,
                '["YES","NO"]',
                "0",
                str(res_win),
                w_res["address"],
                w_bet_close["address"],
                w_res_close["address"],
                "[]",
                "[]",
            )

            created_index = before_count + i
            _wait_for_wagers_count(self.factory, created_index + 1)
            wager = _call(self.factory, "wagers(uint256)(address)", str(created_index))
            if not first_wager:
                first_wager = wager

            self.assertEqual(_call(wager, "proposer()(address)").lower(), w_prop["address"].lower())
            self.assertEqual(_call(wager, "resolver()(address)").lower(), w_res["address"].lower())
            self.assertEqual(_call(wager, "bettingCloser()(address)").lower(), w_bet_close["address"].lower())
            self.assertEqual(_call(wager, "resolutionCloser()(address)").lower(), w_res_close["address"].lower())

            _send_key(
                w_bettor_yes["private_key"],
                self.collateral_token,
                "approve(address,uint256)",
                wager,
                str(amount_raw),
            )
            _send_key(
                w_bettor_yes["private_key"],
                wager,
                "placeBet(uint256,uint256)",
                "0",
                str(amount_raw),
            )
            _send_key(
                w_bettor_no["private_key"],
                self.collateral_token,
                "approve(address,uint256)",
                wager,
                str(amount_raw),
            )
            _send_key(
                w_bettor_no["private_key"],
                wager,
                "placeBet(uint256,uint256)",
                "1",
                str(amount_raw),
            )

            _send_key(w_bet_close["private_key"], wager, "closeBetting()")
            branch = i % 3
            if branch == 0:
                _send_key(w_res["private_key"], wager, "resolve(uint256)", "0")
                self.assertEqual(_wait_for_state(wager, 1), 1)
                _send_key(w_bettor_yes["private_key"], wager, "claim()")
            elif branch == 1:
                _send_key(w_res["private_key"], wager, "retract()")
                self.assertEqual(_wait_for_state(wager, 2), 2)
                _send_key(w_bettor_yes["private_key"], wager, "claim()")
                _send_key(w_bettor_no["private_key"], wager, "claim()")
            else:
                _send_key(w_res_close["private_key"], wager, "closeResolutionWindow()")
                _send_key(w_prop["private_key"], wager, "expire()")
                self.assertEqual(_wait_for_state(wager, 2), 2)
                _send_key(w_bettor_yes["private_key"], wager, "claim()")
                _send_key(w_bettor_no["private_key"], wager, "claim()")

        after_count = _wait_for_wagers_count(self.factory, before_count + self.wager_count)
        self.assertGreaterEqual(after_count, before_count + self.wager_count)

        if self.unauthorized_private_key and first_wager:
            _send_expect_failure(self.unauthorized_private_key, first_wager, "closeBetting()")
            _send_expect_failure(self.unauthorized_private_key, first_wager, "resolve(uint256)", "0")

        if self.indexer_base_url and first_wager:
            try:
                _wait_for_indexer_wager_address(self.indexer_base_url, first_wager)
            except AssertionError as exc:
                self.skipTest(f"Hosted indexer has not yet indexed wager {first_wager}: {exc}")


class TestBaseSepoliaStressV2(unittest.TestCase):
    """Factory v2 matrices: all PayoffPolicy values, placeBet + placeBets paths, multi-outcome tickets."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.rpc = _rpc_url()
        cls.factory_v2 = _env("FACTORY_V2_ADDRESS") or default_factory_v2_address()
        cls.mode = _env("STRESS_MODE", "readonly").lower()
        cls.sample_wagers = int(_env("STRESS_SAMPLE_WAGERS", "12"))
        cls.pool_path = _env("STRESS_WALLET_POOL_PATH")
        cls.funder_key = _env("STRESS_FUNDER_PRIVATE_KEY") or _env("PRIVATE_KEY")
        cls.collateral_token = _env("STRESS_COLLATERAL_TOKEN")
        cls.bet_amount = _env("STRESS_BET_AMOUNT", "1")
        cls.indexer_base_url = _indexer_base_url()
        cls.skip_v2 = _env("STRESS_SKIP_V2", "").lower() in ("1", "true", "yes")
        cls.v2_funded_count = int(_env("STRESS_V2_WAGER_COUNT", str(len(V2_FUNDED_RESOLVE_CASES))))
        cls.v2_minimal_count = int(_env("STRESS_V2_MINIMAL_COUNT", str(len(V2_MINIMAL_EXPIRE_POLICIES))))

        if cls.skip_v2:
            raise unittest.SkipTest("STRESS_SKIP_V2 set — skipping v2 stress tests")
        if not cls.rpc:
            raise unittest.SkipTest("Set RPC_URL_BASE_SEPOLIA (or RPC_URL_SEPOLIA)")
        if not cls.factory_v2:
            raise unittest.SkipTest(
                "Set FACTORY_V2_ADDRESS or config/deployments.json baseSepolia.factoryV2Address"
            )

    def test_readonly_factory_v2_sample_wagers(self) -> None:
        if self.mode != "readonly":
            self.skipTest("Set STRESS_MODE=readonly (default) for this test")

        total = _as_int(_call(self.factory_v2, "wagersCount()(uint256)"))
        if total == 0:
            self.skipTest("No v2 wagers on factory yet")

        n = min(total, self.sample_wagers)
        for k in range(n):
            idx = total - 1 - k
            wager = _call(self.factory_v2, "wagers(uint256)(address)", str(idx))
            factory_on_wager = _call(wager, "factory()(address)")
            self.assertEqual(factory_on_wager.lower(), self.factory_v2.lower())
            policy = _as_int(_call(wager, "payoffPolicy()(uint8)"))
            self.assertIn(policy, (0, 1, 2, 3, 4))
            state = _as_int(_call(wager, "state()(uint8)"))
            self.assertIn(state, (0, 1, 2))

    def test_tx_v2_minimal_policy_matrix_distinct_roles(self) -> None:
        if self.mode != "tx":
            self.skipTest("Set STRESS_MODE=tx to run v2 on-chain matrix")

        if not self.pool_path:
            self.skipTest("Set STRESS_WALLET_POOL_PATH")
        if not self.funder_key:
            self.skipTest("Set STRESS_FUNDER_PRIVATE_KEY or PRIVATE_KEY")

        pool = _load_wallet_pool(self.pool_path)
        need = self.v2_minimal_count * 4
        if len(pool) < need:
            self.skipTest(f"Pool needs >= {need} wallets for v2 minimal matrix (4 roles × policies)")

        min_res = _as_int(_call(self.factory_v2, "minResolutionWindow()(uint64)"))

        for i in range(self.v2_minimal_count):
            policy, param, outcomes_json = V2_MINIMAL_EXPIRE_POLICIES[i % len(V2_MINIMAL_EXPIRE_POLICIES)]
            with self.subTest(i=i, policy=policy):
                base = i * 4
                w_prop = pool[base]
                w_res = pool[base + 1]
                w_bc = pool[base + 2]
                w_rc = pool[base + 3]

                before = _as_int(_call(self.factory_v2, "wagersCount()(uint256)"))
                proposition = f"stress-v2-tx-{policy}-{int(time.time())}-{i}"
                res_win = (0, min_res, min_res)[i % 3]

                _send_key(
                    w_prop["private_key"],
                    self.factory_v2,
                    V2_CREATE_WAGER_SIG,
                    DUMMY_COLLATERAL,
                    proposition,
                    outcomes_json,
                    str(policy),
                    str(param),
                    "0",
                    str(res_win),
                    w_res["address"],
                    w_bc["address"],
                    w_rc["address"],
                    "[]",
                    "[]",
                )
                _wait_for_wagers_count(self.factory_v2, before + 1)
                wager = _call(self.factory_v2, "wagers(uint256)(address)", str(before))

                _send_key(w_bc["private_key"], wager, "closeBetting()")
                branch = i % 3
                if branch == 0:
                    _send_key(w_rc["private_key"], wager, "closeResolutionWindow()")
                    _send_key(self.funder_key, wager, "expire()")
                    self.assertEqual(_wait_for_state(wager, 2), 2)
                elif branch == 1:
                    _send_key(w_res["private_key"], wager, "resolve(uint256)", "1")
                    self.assertEqual(_wait_for_state(wager, 1), 1)
                else:
                    _send_key(w_res["private_key"], wager, "retract()")
                    self.assertEqual(_wait_for_state(wager, 2), 2)

    def test_funded_v2_payoff_policy_matrix(self) -> None:
        if self.mode != "funded-tx":
            self.skipTest("Set STRESS_MODE=funded-tx for v2 funded matrix")
        if not self.pool_path:
            self.skipTest("Set STRESS_WALLET_POOL_PATH")
        if not self.collateral_token:
            self.skipTest("Set STRESS_COLLATERAL_TOKEN")

        pool = _load_wallet_pool(self.pool_path)
        need = self.v2_funded_count * 5
        if len(pool) < need:
            self.skipTest(f"Pool needs >= {need} wallets (5 per v2 funded row: roles + bettor)")

        if not self.funder_key:
            self.skipTest("Set STRESS_FUNDER_PRIVATE_KEY or PRIVATE_KEY for expire() branch")

        cases = _filtered_stress_v2_cases()
        if not cases:
            self.skipTest("STRESS_V2_CASES filter removed all scenarios")

        decimals = _as_int(_call(self.collateral_token, "decimals()(uint8)"))
        amount_raw = _parse_units(self.bet_amount, decimals)
        if amount_raw <= 0:
            self.skipTest("STRESS_BET_AMOUNT must be positive")

        min_res = _as_int(_call(self.factory_v2, "minResolutionWindow()(uint64)"))
        before_all = _as_int(_call(self.factory_v2, "wagersCount()(uint256)"))
        first_wager = ""

        for i in range(self.v2_funded_count):
            case = cases[i % len(cases)]
            base = i * 5
            w_prop = pool[base]
            w_res = pool[base + 1]
            w_bc = pool[base + 2]
            w_rc = pool[base + 3]
            w_bet = pool[base + 4]
            legs = len(case.ticket_masks)
            total_stake = amount_raw * legs

            bettor_bal = _as_int(
                _call(self.collateral_token, "balanceOf(address)(uint256)", w_bet["address"])
            )
            if bettor_bal < total_stake:
                self.skipTest(
                    f"Bettor {w_bet['address'][:10]}… needs {total_stake} raw for {case.case_id}"
                )

            with self.subTest(i=i, case_id=case.case_id):
                before = _as_int(_call(self.factory_v2, "wagersCount()(uint256)"))
                proposition = f"stress-v2-funded-{case.case_id}-{int(time.time())}-{i}"
                res_win = (0, min_res, min_res)[i % 3]

                _send_key(
                    w_prop["private_key"],
                    self.factory_v2,
                    V2_CREATE_WAGER_SIG,
                    self.collateral_token,
                    proposition,
                    case.outcomes_json,
                    str(case.payoff_policy),
                    str(case.policy_param),
                    "0",
                    str(res_win),
                    w_res["address"],
                    w_bc["address"],
                    w_rc["address"],
                    "[]",
                    "[]",
                )
                _wait_for_wagers_count(self.factory_v2, before + 1)
                wager = _call(self.factory_v2, "wagers(uint256)(address)", str(before))
                if not first_wager:
                    first_wager = wager

                _send_key(
                    w_bet["private_key"],
                    self.collateral_token,
                    "approve(address,uint256)",
                    wager,
                    str(total_stake),
                )
                if case.use_place_bets and legs > 1:
                    masks_lit = "[" + ",".join(str(m) for m in case.ticket_masks) + "]"
                    amts_lit = "[" + ",".join(str(amount_raw) for _ in case.ticket_masks) + "]"
                    _send_key(
                        w_bet["private_key"],
                        wager,
                        "placeBets(uint256[],uint256[])",
                        masks_lit,
                        amts_lit,
                    )
                else:
                    for mask in case.ticket_masks:
                        _send_key(
                            w_bet["private_key"],
                            wager,
                            "placeBet(uint256,uint256)",
                            str(mask),
                            str(amount_raw),
                        )

                _send_key(w_bc["private_key"], wager, "closeBetting()")
                branch = i % 3
                if branch == 0:
                    _send_key(w_res["private_key"], wager, "resolve(uint256)", str(case.winning_mask))
                    self.assertEqual(_wait_for_state(wager, 1), 1)
                    _send_key(w_bet["private_key"], wager, "claim()")
                elif branch == 1:
                    _send_key(w_res["private_key"], wager, "retract()")
                    self.assertEqual(_wait_for_state(wager, 2), 2)
                    _send_key(w_bet["private_key"], wager, "claim()")
                else:
                    _send_key(w_rc["private_key"], wager, "closeResolutionWindow()")
                    _send_key(self.funder_key, wager, "expire()")
                    self.assertEqual(_wait_for_state(wager, 2), 2)
                    _send_key(w_bet["private_key"], wager, "claim()")

        self.assertGreaterEqual(
            _wait_for_wagers_count(self.factory_v2, before_all + self.v2_funded_count),
            before_all + self.v2_funded_count,
        )

        if self.indexer_base_url and first_wager:
            try:
                _wait_for_indexer_wager_address(self.indexer_base_url, first_wager)
            except AssertionError as exc:
                self.skipTest(str(exc))


if __name__ == "__main__":
    unittest.main(verbosity=2)
