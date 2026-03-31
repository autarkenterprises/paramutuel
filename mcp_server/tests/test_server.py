"""Tests for the Paramutuel MCP server tools."""
from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from mcp_server.server import (
    _compute_odds,
    _encode_call,
    _encode_erc20_approve,
    _selector,
    calculate_odds,
    encode_claim,
    encode_close_betting,
    encode_close_resolution_window,
    encode_create_wager,
    encode_expire,
    encode_place_bet,
    encode_place_bets,
    encode_resolve,
    encode_retract,
    encode_withdraw_fees,
    get_protocol_info,
    FACTORY_ABI,
    FACTORY_ADDRESS,
    WAGER_ABI,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestSelectors(unittest.TestCase):
    """Verify function selectors match known values from Foundry cast."""

    KNOWN_SELECTORS = {
        "placeBet(uint256,uint256)": "4afe62b5",
        "placeBets(uint256[],uint256[])": "fce898c7",
        "claim()": "4e71d92d",
        "resolve(uint256)": "4f896d4f",
        "retract()": "47f57b32",
        "expire()": "79599f96",
        "closeBetting()": "15ac534d",
        "closeResolutionWindow()": "22ad3cf6",
        "withdrawFees()": "476343ee",
        "approve(address,uint256)": "095ea7b3",
    }

    def test_known_selectors(self):
        for sig, expected_hex in self.KNOWN_SELECTORS.items():
            sel = _selector(sig)
            self.assertEqual(
                sel.hex(),
                expected_hex,
                f"Selector mismatch for {sig}: got 0x{sel.hex()}, expected 0x{expected_hex}",
            )


class TestEncoding(unittest.TestCase):
    def test_no_arg_call(self):
        calldata = _encode_call("claim()", [], [])
        self.assertEqual(calldata, "0x4e71d92d")
        self.assertEqual(len(bytes.fromhex(calldata[2:])), 4)

    def test_single_uint256_call(self):
        calldata = _encode_call("resolve(uint256)", ["uint256"], [42])
        data = bytes.fromhex(calldata[2:])
        self.assertEqual(len(data), 4 + 32)  # selector + one word

    def test_erc20_approve(self):
        calldata = _encode_erc20_approve("0x" + "ab" * 20, 1_000_000)
        self.assertTrue(calldata.startswith("0x095ea7b3"))
        self.assertEqual(len(bytes.fromhex(calldata[2:])), 4 + 64)


class TestOdds(unittest.TestCase):
    def test_basic_odds(self):
        result = _compute_odds(
            total_pot=1_000_000,
            outcome_total=400_000,
            total_fee_bps=200,
            bet_amount=100_000,
        )
        self.assertEqual(result["total_pot_after"], 1_100_000)
        self.assertEqual(result["net_pot_after"], 1_078_000)
        self.assertEqual(result["expected_payout_raw"], 215_600)
        self.assertEqual(result["expected_profit_raw"], 115_600)
        self.assertAlmostEqual(result["post_bet_payout_multiple"], 2.156, places=3)

    def test_zero_outcome_total(self):
        result = _compute_odds(
            total_pot=0, outcome_total=0, total_fee_bps=200, bet_amount=100_000
        )
        self.assertIsNone(result["current_payout_multiple"])
        self.assertAlmostEqual(result["post_bet_payout_multiple"], 0.98, places=2)
        self.assertEqual(result["expected_payout_raw"], 98_000)

    def test_zero_fee(self):
        result = _compute_odds(
            total_pot=1_000_000,
            outcome_total=500_000,
            total_fee_bps=0,
            bet_amount=100_000,
        )
        self.assertEqual(result["net_pot_after"], 1_100_000)


class TestTools(unittest.TestCase):
    """Test MCP tool functions return valid JSON."""

    def test_get_protocol_info(self):
        info = json.loads(_run(get_protocol_info()))
        self.assertIn("factory_address", info)
        self.assertIn("chain_id", info)
        self.assertIn("constants", info)
        self.assertEqual(info["constants"]["MAX_OUTCOMES"], 64)

    def test_calculate_odds(self):
        result = json.loads(
            _run(calculate_odds(1_000_000, 400_000, 200, 100_000))
        )
        self.assertIn("expected_payout_raw", result)

    def test_encode_place_bet(self):
        result = json.loads(
            _run(
                encode_place_bet(
                    "0x" + "ab" * 20, "0x" + "cd" * 20, 0, 1_000_000
                )
            )
        )
        self.assertIn("calldata", result)
        self.assertIn("approval_required", result)
        self.assertTrue(result["calldata"].startswith("0x4afe62b5"))

    def test_encode_place_bets(self):
        result = json.loads(
            _run(
                encode_place_bets(
                    "0x" + "ab" * 20,
                    "0x" + "cd" * 20,
                    [0, 1],
                    [500_000, 500_000],
                )
            )
        )
        self.assertIn("calldata", result)
        self.assertEqual(result["approval_required"]["amount"], 1_000_000)

    def test_encode_resolve(self):
        result = json.loads(
            _run(encode_resolve("0x" + "ab" * 20, 1))
        )
        self.assertTrue(result["calldata"].startswith("0x4f896d4f"))

    def test_encode_retract(self):
        result = json.loads(_run(encode_retract("0x" + "ab" * 20)))
        self.assertTrue(result["calldata"].startswith("0x47f57b32"))

    def test_encode_expire(self):
        result = json.loads(_run(encode_expire("0x" + "ab" * 20)))
        self.assertTrue(result["calldata"].startswith("0x79599f96"))

    def test_encode_close_betting(self):
        result = json.loads(
            _run(encode_close_betting("0x" + "ab" * 20))
        )
        self.assertTrue(result["calldata"].startswith("0x15ac534d"))

    def test_encode_close_resolution_window(self):
        result = json.loads(
            _run(encode_close_resolution_window("0x" + "ab" * 20))
        )
        self.assertTrue(result["calldata"].startswith("0x22ad3cf6"))

    def test_encode_claim(self):
        result = json.loads(_run(encode_claim("0x" + "ab" * 20)))
        self.assertEqual(result["calldata"], "0x4e71d92d")

    def test_encode_withdraw_fees(self):
        result = json.loads(
            _run(encode_withdraw_fees("0x" + "ab" * 20))
        )
        self.assertTrue(result["calldata"].startswith("0x476343ee"))

    def test_encode_create_wager_no_seeds(self):
        result = json.loads(
            _run(
                encode_create_wager(
                    collateral_token="0x036CbD53842c5426634e7929541eC2318f3dCf7e",
                    proposition="Test?",
                    outcomes=["A", "B"],
                    betting_closer="0x" + "aa" * 20,
                    resolution_closer="0x" + "bb" * 20,
                )
            )
        )
        self.assertIn("calldata", result)
        self.assertNotIn("approval_required", result)
        self.assertEqual(result["to"], FACTORY_ADDRESS)

    def test_encode_create_wager_with_seeds(self):
        result = json.loads(
            _run(
                encode_create_wager(
                    collateral_token="0x036CbD53842c5426634e7929541eC2318f3dCf7e",
                    proposition="Test?",
                    outcomes=["A", "B"],
                    betting_closer="0x" + "aa" * 20,
                    resolution_closer="0x" + "bb" * 20,
                    seed_outcome_indices=[0, 1],
                    seed_amounts=[100_000, 200_000],
                )
            )
        )
        self.assertIn("approval_required", result)
        self.assertEqual(result["approval_required"]["amount"], 300_000)


class TestABILoading(unittest.TestCase):
    def test_factory_abi_count(self):
        self.assertEqual(len(FACTORY_ABI), 19)

    def test_wager_abi_count(self):
        self.assertEqual(len(WAGER_ABI), 63)

    def test_factory_address_set(self):
        self.assertTrue(FACTORY_ADDRESS.startswith("0x"))
        self.assertEqual(len(FACTORY_ADDRESS), 42)


if __name__ == "__main__":
    unittest.main()
