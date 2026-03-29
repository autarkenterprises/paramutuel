"""Multi-market, multi-actor stress tests against deployed Base Sepolia contracts.

Modes (STRESS_MODE env):
  - readonly (default): eth_call only; samples latest markets from the factory.
  - tx: creates STRESS_MARKET_COUNT markets with distinct delegated roles per market.

See docs/TESTNET-STRESS-SUITE.md for wallet pool generation and funding.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import unittest
from pathlib import Path

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
DUMMY_COLLATERAL = "0x0000000000000000000000000000000000000001"


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


def _send_key(private_key: str, address: str, signature: str, *fn_args: str) -> None:
    rpc = _rpc_url()
    if not rpc:
        raise RuntimeError("RPC_URL_BASE_SEPOLIA is required")
    _run_cast(
        [
            "send",
            address,
            signature,
            *fn_args,
            "--rpc-url",
            rpc,
            "--private-key",
            private_key,
        ]
    )


def _as_int(value: str) -> int:
    value = value.strip()
    if value.startswith("0x"):
        return int(value, 16)
    return int(value)


def _load_wallet_pool(path: str) -> list[dict[str, str]]:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("wallet pool must be a non-empty JSON array")
    for row in data:
        if "private_key" not in row or "address" not in row:
            raise ValueError("each wallet entry needs address and private_key")
    return data


class TestBaseSepoliaStress(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rpc = _rpc_url()
        cls.factory = _env("FACTORY_ADDRESS")
        cls.mode = _env("STRESS_MODE", "readonly").lower()
        cls.sample_markets = int(_env("STRESS_SAMPLE_MARKETS", "12"))
        cls.market_count = int(_env("STRESS_MARKET_COUNT", "3"))
        cls.pool_path = _env("STRESS_WALLET_POOL_PATH")
        cls.funder_key = _env("STRESS_FUNDER_PRIVATE_KEY") or _env("PRIVATE_KEY")

        if not cls.rpc:
            raise unittest.SkipTest("Set RPC_URL_BASE_SEPOLIA (or RPC_URL_SEPOLIA)")
        if not cls.factory:
            raise unittest.SkipTest("Set FACTORY_ADDRESS")

    def test_readonly_sample_markets(self) -> None:
        if self.mode != "readonly":
            self.skipTest("Set STRESS_MODE=readonly (default) for this test")

        total = _as_int(_call(self.factory, "marketsCount()(uint256)"))
        if total == 0:
            self.skipTest("No markets on factory yet; run tx mode once or deploy markets first")

        n = min(total, self.sample_markets)
        for k in range(n):
            idx = total - 1 - k
            market = _call(self.factory, "markets(uint256)(address)", str(idx))
            factory_on_market = _call(market, "factory()(address)")
            self.assertEqual(factory_on_market.lower(), self.factory.lower())
            state = _as_int(_call(market, "state()(uint8)"))
            self.assertIn(state, (0, 1, 2))
            proposer = _call(market, "proposer()(address)").lower()
            resolver = _call(market, "resolver()(address)").lower()
            bc = _call(market, "bettingCloser()(address)").lower()
            rc = _call(market, "resolutionCloser()(address)").lower()
            self.assertTrue(proposer.startswith("0x"))
            self.assertTrue(resolver.startswith("0x"))
            self.assertTrue(bc.startswith("0x"))
            self.assertTrue(rc.startswith("0x"))

    def test_tx_multi_market_distinct_roles(self) -> None:
        if self.mode != "tx":
            self.skipTest("Set STRESS_MODE=tx to run on-chain stress creation")

        if not self.pool_path:
            self.skipTest("Set STRESS_WALLET_POOL_PATH to a JSON pool from gen_stress_wallet_pool.py")
        if not self.funder_key:
            self.skipTest("Set STRESS_FUNDER_PRIVATE_KEY or PRIVATE_KEY for expire() and gas")

        pool = _load_wallet_pool(self.pool_path)
        need = self.market_count * 4
        if len(pool) < need:
            self.skipTest(f"Pool has {len(pool)} wallets; need at least {need} (4 per market)")

        min_res = _as_int(_call(self.factory, "minResolutionWindow()(uint64)"))

        for i in range(self.market_count):
            base = i * 4
            w_prop = pool[base]
            w_res = pool[base + 1]
            w_bet_close = pool[base + 2]
            w_res_close = pool[base + 3]

            before = _as_int(_call(self.factory, "marketsCount()(uint256)"))
            question = f"stress-{int(time.time())}-{i}"
            # Rotate resolution window: 0 (no max), min_res, min_res — all closable via authority + expire
            res_win = (0, min_res, min_res)[i % 3]

            _send_key(
                w_prop["private_key"],
                self.factory,
                "createMarket(address,string,string[],uint64,uint64,address,address,address,address[],uint16[])",
                DUMMY_COLLATERAL,
                question,
                '["A","B"]',
                "0",
                str(res_win),
                w_res["address"],
                w_bet_close["address"],
                w_res_close["address"],
                "[]",
                "[]",
            )

            after = _as_int(_call(self.factory, "marketsCount()(uint256)"))
            self.assertEqual(after, before + 1)

            market = _call(self.factory, "markets(uint256)(address)", str(before))
            self.assertEqual(_call(market, "proposer()(address)").lower(), w_prop["address"].lower())
            self.assertEqual(_call(market, "resolver()(address)").lower(), w_res["address"].lower())
            self.assertEqual(_call(market, "bettingCloser()(address)").lower(), w_bet_close["address"].lower())
            self.assertEqual(_call(market, "resolutionCloser()(address)").lower(), w_res_close["address"].lower())

            _send_key(w_bet_close["private_key"], market, "closeBetting()")

            branch = i % 3
            if branch == 0:
                _send_key(w_res_close["private_key"], market, "closeResolutionWindow()")
                _send_key(self.funder_key, market, "expire()")
                self.assertEqual(_as_int(_call(market, "state()(uint8)")), 2)
            elif branch == 1:
                _send_key(w_res["private_key"], market, "resolve(uint256)", "0")
                self.assertEqual(_as_int(_call(market, "state()(uint8)")), 1)
            else:
                _send_key(w_res["private_key"], market, "retract()")
                self.assertEqual(_as_int(_call(market, "state()(uint8)")), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
