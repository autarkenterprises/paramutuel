"""Tests for the Paramutuel MCP server tools."""
from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import mcp_server.server as server_mod

from mcp_server.server import (
    _compute_odds,
    _compute_batch_odds,
    _encode_call,
    _encode_erc20_approve,
    _selector,
    calculate_odds,
    quote_place_bet,
    quote_place_bets,
    encode_claim,
    encode_close_betting,
    encode_close_resolution_window,
    encode_create_wager,
    encode_create_wager_v2,
    encode_create_enumerated_wager_v3,
    encode_create_freeform_wager,
    encode_create_freeform_wager_v3,
    encode_expire,
    encode_place_bet,
    encode_place_bet_freeform,
    encode_place_bets,
    encode_resolve,
    encode_resolve_freeform,
    encode_retract,
    encode_withdraw_fees,
    get_protocol_info,
    FACTORY_ABI,
    FACTORY_ADDRESS,
    FACTORY_V3_ADDRESS,
    FACTORY_V2_ABI,
    FACTORY_V3_ABI,
    FACTORY_FREEFORM_ABI,
    WAGER_ABI,
    WAGER_V2_ABI,
    WAGER_V3_ABI,
    WAGER_FREEFORM_ABI,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestFreeformV3AnswerId(unittest.TestCase):
    def test_answer_id_matches_known_vector_paris(self):
        from mcp_server.server import _freeform_v3_answer_id_hex

        self.assertEqual(
            _freeform_v3_answer_id_hex("Paris").lower(),
            "0x1912e91243cbc3b42ab17ada47d57ab68ed946bc24de33ae4f6c13bdad067953",
        )

    def test_answer_id_differs_from_legacy_freeform_digest(self):
        from mcp_server.server import _freeform_v3_answer_id_hex
        from eth_hash.auto import keccak as _keccak256

        s = "same-string"
        legacy = "0x" + _keccak256(s.encode("utf-8")).hex()
        v3 = _freeform_v3_answer_id_hex(s)
        self.assertNotEqual(legacy.lower(), v3.lower())


class TestSelectors(unittest.TestCase):
    """Verify function selectors match known values from Foundry cast."""

    KNOWN_SELECTORS = {
        "createWager(address,string,string[],uint8,uint256,uint64,uint64,address,address,address,address[],uint16[])": "3b16de13",
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
        "createFreeformWager(address,string,uint64,uint64,address,address,address,address[],uint16[])": "cecc699e",
        "placeBet(string,uint256)": "d76f2a1e",
        "resolve(string)": "461a4478",
        "createEnumeratedWager(address,string,string[],uint8,uint256,uint64,uint64,address,address,address,address[],uint16[])": "0856f578",
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
            total_fee_bps=100,
            bet_amount=100_000,
        )
        self.assertEqual(result["total_pot_after"], 1_100_000)
        self.assertEqual(result["net_pot_after"], 1_089_000)
        self.assertEqual(result["expected_payout_raw"], 217_800)
        self.assertEqual(result["expected_profit_raw"], 117_800)
        self.assertAlmostEqual(result["post_bet_payout_multiple"], 2.178, places=3)

    def test_zero_outcome_total(self):
        result = _compute_odds(
            total_pot=0, outcome_total=0, total_fee_bps=100, bet_amount=100_000
        )
        self.assertIsNone(result["current_payout_multiple"])
        self.assertAlmostEqual(result["post_bet_payout_multiple"], 0.99, places=2)
        self.assertEqual(result["expected_payout_raw"], 99_000)

    def test_zero_fee(self):
        result = _compute_odds(
            total_pot=1_000_000,
            outcome_total=500_000,
            total_fee_bps=0,
            bet_amount=100_000,
        )
        self.assertEqual(result["net_pot_after"], 1_100_000)


class TestBatchOdds(unittest.TestCase):
    def test_batch_odds(self):
        result = _compute_batch_odds(
            total_pot=1_000_000,
            outcome_totals=[400_000, 600_000],
            total_fee_bps=100,
            bet_amounts=[100_000, 200_000],
        )

        # Fees are charged once on the total pot after all bets.
        self.assertEqual(result["total_pot_after"], 1_300_000)
        self.assertEqual(result["net_pot_after"], 1_287_000)

        legs = result["legs"]
        self.assertEqual(len(legs), 2)

        # Leg 0: outcome_after = 500_000
        self.assertEqual(legs[0]["expected_payout_raw"], 257_400)
        self.assertEqual(legs[0]["expected_profit_raw"], 157_400)
        self.assertAlmostEqual(legs[0]["post_bet_payout_multiple"], 2.574, places=3)

        # Leg 1: outcome_after = 800_000
        self.assertEqual(legs[1]["expected_payout_raw"], 321_750)
        self.assertEqual(legs[1]["expected_profit_raw"], 121_750)
        self.assertAlmostEqual(legs[1]["post_bet_payout_multiple"], 1.60875, places=3)


class TestTools(unittest.TestCase):
    """Test MCP tool functions return valid JSON."""

    def test_get_protocol_info(self):
        info = json.loads(_run(get_protocol_info()))
        self.assertIn("factory_address", info)
        self.assertIn("factory_v2_address", info)
        self.assertIn("factory_freeform_address", info)
        self.assertIn("factory_v3_address", info)
        self.assertIn("chain_id", info)
        self.assertIn("constants", info)
        self.assertIn("factory_v2_functions", info)
        self.assertIn("wager_v2_functions", info)
        self.assertIn("factory_freeform_functions", info)
        self.assertIn("wager_freeform_functions", info)
        self.assertIn("factory_v3_functions", info)
        self.assertIn("wager_v3_functions", info)
        self.assertIn("notes", info)
        self.assertEqual(info["constants"]["MAX_OUTCOMES"], 255)
        self.assertEqual(info["constants"]["FREEFORM_MAX_ANSWER_BYTES"], 1024)
        self.assertEqual(info["constants"]["FREEFORM_MAX_DISTINCT_ANSWERS_CAP"], 1024)
        self.assertIn("freeform_wagers", info["notes"])
        self.assertIn("v3_wagers", info["notes"])

    @unittest.expectedFailure
    def test_XFAIL_DEPRECATED_get_protocol_info_lacked_freeform_surface(self):
        """Documents pre-ADR-0009 MCP metadata; superseded by factory/wager freeform lists."""
        info = json.loads(_run(get_protocol_info()))
        self.assertNotIn("factory_freeform_functions", info)

    @unittest.expectedFailure
    def test_XFAIL_DEPRECATED_protocol_MAX_OUTCOMES_was_64(self):
        """Former surfaced constant before the on-chain cap was raised to 255."""
        info = json.loads(_run(get_protocol_info()))
        self.assertEqual(info["constants"]["MAX_OUTCOMES"], 64)

    def test_calculate_odds(self):
        result = json.loads(
            _run(calculate_odds(1_000_000, 400_000, 100, 100_000))
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

    def test_encode_place_bet_accepts_ticket_mask_override(self):
        plain = json.loads(
            _run(
                encode_place_bet(
                    "0x" + "ab" * 20, "0x" + "cd" * 20, 2, 1_000_000
                )
            )
        )
        masked = json.loads(
            _run(
                encode_place_bet(
                    "0x" + "ab" * 20,
                    "0x" + "cd" * 20,
                    2,
                    1_000_000,
                    ticket_mask=256,
                )
            )
        )
        self.assertNotEqual(plain["calldata"], masked["calldata"])

    def test_encode_place_bets_rejects_mask_length_mismatch(self):
        with self.assertRaises(ValueError):
            _run(
                encode_place_bets(
                    "0x" + "ab" * 20,
                    "0x" + "cd" * 20,
                    [0, 1],
                    [500_000, 500_000],
                    ticket_masks=[1],
                )
            )

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

    def test_encode_place_bet_freeform(self):
        result = json.loads(
            _run(
                encode_place_bet_freeform(
                    "0x" + "ab" * 20,
                    "0x" + "cd" * 20,
                    "Paris",
                    1_000_000,
                )
            )
        )
        self.assertTrue(result["calldata"].lower().startswith("0xd76f2a1e"))
        self.assertIn("approval_required", result)

    def test_encode_resolve_freeform(self):
        result = json.loads(
            _run(encode_resolve_freeform("0x" + "ab" * 20, "Paris"))
        )
        self.assertTrue(result["calldata"].lower().startswith("0x461a4478"))

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

    def test_encode_create_wager_requires_factory(self):
        prev = server_mod.FACTORY_ADDRESS
        server_mod.FACTORY_ADDRESS = ""
        try:
            with self.assertRaises(ValueError):
                _run(
                    encode_create_wager(
                        collateral_token="0x036CbD53842c5426634e7929541eC2318f3dCf7e",
                        proposition="Test?",
                        outcomes=["A", "B"],
                        betting_closer="0x" + "aa" * 20,
                        resolution_closer="0x" + "bb" * 20,
                    )
                )
        finally:
            server_mod.FACTORY_ADDRESS = prev

    def test_encode_create_wager_no_seeds(self):
        prev = server_mod.FACTORY_ADDRESS
        server_mod.FACTORY_ADDRESS = "0x" + "cd" * 20
        try:
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
            self.assertEqual(result["to"], server_mod.FACTORY_ADDRESS)
        finally:
            server_mod.FACTORY_ADDRESS = prev

    def test_encode_create_wager_with_seeds(self):
        prev = server_mod.FACTORY_ADDRESS
        server_mod.FACTORY_ADDRESS = "0x" + "cd" * 20
        try:
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
        finally:
            server_mod.FACTORY_ADDRESS = prev

    def test_encode_create_wager_v2_requires_factory(self):
        prev = server_mod.FACTORY_V2_ADDRESS
        server_mod.FACTORY_V2_ADDRESS = ""
        try:
            with self.assertRaises(ValueError):
                _run(
                    encode_create_wager_v2(
                        collateral_token="0x036CbD53842c5426634e7929541eC2318f3dCf7e",
                        proposition="V2?",
                        outcomes=["A", "B"],
                        payoff_policy=0,
                        policy_param=0,
                        betting_closer="0x" + "aa" * 20,
                        resolution_closer="0x" + "bb" * 20,
                    )
                )
        finally:
            server_mod.FACTORY_V2_ADDRESS = prev

    def test_encode_create_wager_v2_shape(self):
        prev = server_mod.FACTORY_V2_ADDRESS
        server_mod.FACTORY_V2_ADDRESS = "0x" + "ee" * 20
        try:
            result = json.loads(
                _run(
                    encode_create_wager_v2(
                        collateral_token="0x036CbD53842c5426634e7929541eC2318f3dCf7e",
                        proposition="V2?",
                        outcomes=["A", "B"],
                        payoff_policy=0,
                        policy_param=0,
                        betting_closer="0x" + "aa" * 20,
                        resolution_closer="0x" + "bb" * 20,
                    )
                )
            )
            self.assertIn("calldata", result)
            self.assertTrue(result["calldata"].startswith("0x"))
            self.assertEqual(result["to"], server_mod.FACTORY_V2_ADDRESS)
            self.assertTrue(result["calldata"].lower().startswith("0x3b16de13"))
        finally:
            server_mod.FACTORY_V2_ADDRESS = prev

    def test_encode_create_freeform_wager_requires_factory(self):
        prev = server_mod.FACTORY_FREEFORM_ADDRESS
        server_mod.FACTORY_FREEFORM_ADDRESS = ""
        try:
            with self.assertRaises(ValueError):
                _run(
                    encode_create_freeform_wager(
                        collateral_token="0x036CbD53842c5426634e7929541eC2318f3dCf7e",
                        proposition="Who wins?",
                        betting_closer="0x" + "aa" * 20,
                        resolution_closer="0x" + "bb" * 20,
                    )
                )
        finally:
            server_mod.FACTORY_FREEFORM_ADDRESS = prev

    def test_encode_create_freeform_wager_shape(self):
        prev = server_mod.FACTORY_FREEFORM_ADDRESS
        server_mod.FACTORY_FREEFORM_ADDRESS = "0x" + "ff" * 20
        try:
            result = json.loads(
                _run(
                    encode_create_freeform_wager(
                        collateral_token="0x036CbD53842c5426634e7929541eC2318f3dCf7e",
                        proposition="Freeform?",
                        betting_closer="0x" + "aa" * 20,
                        resolution_closer="0x" + "bb" * 20,
                    )
                )
            )
            self.assertIn("calldata", result)
            self.assertTrue(result["calldata"].lower().startswith("0xcecc699e"))
            self.assertEqual(result["to"], server_mod.FACTORY_FREEFORM_ADDRESS)
        finally:
            server_mod.FACTORY_FREEFORM_ADDRESS = prev

    def test_encode_create_enumerated_wager_v3_requires_factory(self):
        prev = server_mod.FACTORY_V3_ADDRESS
        server_mod.FACTORY_V3_ADDRESS = ""
        try:
            with self.assertRaises(ValueError):
                _run(
                    encode_create_enumerated_wager_v3(
                        collateral_token="0x036CbD53842c5426634e7929541eC2318f3dCf7e",
                        proposition="V3?",
                        outcomes=["A", "B"],
                        payoff_policy=0,
                        policy_param=0,
                        betting_closer="0x" + "aa" * 20,
                        resolution_closer="0x" + "bb" * 20,
                    )
                )
        finally:
            server_mod.FACTORY_V3_ADDRESS = prev

    def test_encode_create_enumerated_wager_v3_shape(self):
        prev = server_mod.FACTORY_V3_ADDRESS
        server_mod.FACTORY_V3_ADDRESS = "0x" + "ee" * 20
        try:
            result = json.loads(
                _run(
                    encode_create_enumerated_wager_v3(
                        collateral_token="0x036CbD53842c5426634e7929541eC2318f3dCf7e",
                        proposition="V3?",
                        outcomes=["A", "B"],
                        payoff_policy=0,
                        policy_param=0,
                        betting_closer="0x" + "aa" * 20,
                        resolution_closer="0x" + "bb" * 20,
                    )
                )
            )
            self.assertTrue(result["calldata"].lower().startswith("0x0856f578"))
            self.assertEqual(result["to"], server_mod.FACTORY_V3_ADDRESS)
        finally:
            server_mod.FACTORY_V3_ADDRESS = prev

    def test_encode_create_freeform_wager_v3_shape(self):
        prev = server_mod.FACTORY_V3_ADDRESS
        server_mod.FACTORY_V3_ADDRESS = "0x" + "ee" * 20
        try:
            result = json.loads(
                _run(
                    encode_create_freeform_wager_v3(
                        collateral_token="0x036CbD53842c5426634e7929541eC2318f3dCf7e",
                        proposition="FF v3?",
                        betting_closer="0x" + "aa" * 20,
                        resolution_closer="0x" + "bb" * 20,
                    )
                )
            )
            self.assertTrue(result["calldata"].lower().startswith("0xcecc699e"))
            self.assertEqual(result["to"], server_mod.FACTORY_V3_ADDRESS)
        finally:
            server_mod.FACTORY_V3_ADDRESS = prev


def _mock_httpx_indexer_payload(payload: dict):
    """Return a patch target so _indexer_get returns `payload`."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=payload)

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    return patch("mcp_server.server.httpx.AsyncClient", return_value=mock_cm)


class TestQuoteToolsMockedIndexer(unittest.TestCase):
    _v2_detail = {
        "wager": {
            "collateral_token": "0x036CbD53842c5426634e7929541eC2318f3dCf7e",
            "protocol_version": "v2",
            "state": "OPEN",
            "betting_closed_by_authority": 0,
            "betting_close_time": 9_999_999_999,
        },
        "totals": {"total_pot": "1000", "total_fee_bps": "0"},
        "outcomes": [],
        "ticket_pools": [{"ticket_mask": "4", "pool_total": "250"}],
    }

    def test_quote_place_bet_v2_sets_ticket_mask_and_pool_odds(self):
        with _mock_httpx_indexer_payload(self._v2_detail):
            raw = _run(
                quote_place_bet(
                    "0x" + "ab" * 20,
                    outcome_index=2,
                    amount=100,
                    require_open=False,
                )
            )
        body = json.loads(raw)
        self.assertEqual(body.get("protocol_version"), "v2")
        self.assertEqual(body.get("ticket_mask"), 4)
        calldata = body["placeBet"]["calldata"]
        self.assertTrue(calldata.startswith("0x4afe62b5"))
        # First uint256 argument word after selector should encode 4, not 2.
        word_hex = calldata[10 : 10 + 64]
        self.assertEqual(int(word_hex, 16), 4)

    def test_quote_place_bets_v2_encodes_ticket_masks_array(self):
        with _mock_httpx_indexer_payload(self._v2_detail):
            raw = _run(
                quote_place_bets(
                    "0x" + "ab" * 20,
                    outcome_indices=[2],
                    amounts=[50],
                    require_open=False,
                )
            )
        body = json.loads(raw)
        self.assertEqual(body.get("ticket_masks"), [4])
        self.assertIn("placeBets", body)

    _v3_enum_detail = {
        "wager": {
            "collateral_token": "0x036CbD53842c5426634e7929541eC2318f3dCf7e",
            "protocol_version": "v3_enum",
            "state": "OPEN",
            "betting_closed_by_authority": 0,
            "betting_close_time": 9_999_999_999,
        },
        "totals": {"total_pot": "1000", "total_fee_bps": "0"},
        "outcomes": [],
        "ticket_pools": [{"ticket_mask": "4", "pool_total": "250"}],
    }

    def test_quote_place_bet_v3_enum_matches_v2_ticket_mask_semantics(self):
        with _mock_httpx_indexer_payload(self._v3_enum_detail):
            raw = _run(
                quote_place_bet(
                    "0x" + "ab" * 20,
                    outcome_index=2,
                    amount=100,
                    require_open=False,
                )
            )
        body = json.loads(raw)
        self.assertEqual(body.get("protocol_version"), "v3_enum")
        self.assertEqual(body.get("ticket_mask"), 4)

    _v3_ff_detail = {
        "wager": {
            "collateral_token": "0x036CbD53842c5426634e7929541eC2318f3dCf7e",
            "protocol_version": "v3_freeform",
            "state": "OPEN",
            "betting_closed_by_authority": 0,
            "betting_close_time": 9_999_999_999,
        },
        "totals": {"total_pot": "1000", "total_fee_bps": "0"},
        "outcomes": [],
        "ticket_pools": [],
    }

    def test_quote_place_bet_v3_freeform_requires_answer(self):
        with _mock_httpx_indexer_payload(self._v3_ff_detail):
            with self.assertRaises(ValueError):
                _run(
                    quote_place_bet(
                        "0x" + "ab" * 20,
                        outcome_index=0,
                        amount=10,
                        require_open=False,
                    )
                )

    def test_quote_place_bets_v3_freeform_raises(self):
        with _mock_httpx_indexer_payload(self._v3_ff_detail):
            with self.assertRaises(ValueError):
                _run(
                    quote_place_bets(
                        "0x" + "ab" * 20,
                        outcome_indices=[0],
                        amounts=[10],
                        require_open=False,
                    )
                )

    _v1_detail = {
        "wager": {
            "collateral_token": "0x036CbD53842c5426634e7929541eC2318f3dCf7e",
            "protocol_version": "v1",
            "state": "OPEN",
            "betting_closed_by_authority": 0,
            "betting_close_time": 9_999_999_999,
        },
        "totals": {"total_pot": "1000", "total_fee_bps": "0"},
        "outcomes": [
            {"outcome_index": 0, "outcome_total": "600"},
            {"outcome_index": 1, "outcome_total": "400"},
        ],
        "ticket_pools": [],
    }

    def test_quote_place_bet_v1_encodes_outcome_index_not_bitmask(self):
        with _mock_httpx_indexer_payload(self._v1_detail):
            raw = _run(
                quote_place_bet(
                    "0x" + "ab" * 20,
                    outcome_index=1,
                    amount=50,
                    require_open=False,
                )
            )
        body = json.loads(raw)
        self.assertEqual(body.get("protocol_version"), "v1")
        self.assertNotIn("ticket_mask", body)
        calldata = body["placeBet"]["calldata"]
        word_hex = calldata[10 : 10 + 64]
        self.assertEqual(int(word_hex, 16), 1)


class TestABILoading(unittest.TestCase):
    def test_factory_abi_count(self):
        self.assertEqual(len(FACTORY_ABI), 19)

    def test_wager_abi_count(self):
        self.assertEqual(len(WAGER_ABI), 63)

    def test_factory_v3_address_set(self):
        self.assertTrue(FACTORY_V3_ADDRESS.startswith("0x"))
        self.assertEqual(len(FACTORY_V3_ADDRESS), 42)

    def test_v2_abis_bundled(self):
        self.assertGreater(len(FACTORY_V2_ABI), 5)
        self.assertGreater(len(WAGER_V2_ABI), 5)

    def test_freeform_abis_bundled(self):
        self.assertGreater(len(FACTORY_FREEFORM_ABI), 5)
        self.assertGreater(len(WAGER_FREEFORM_ABI), 5)

    def test_v3_abis_bundled(self):
        self.assertGreater(len(FACTORY_V3_ABI), 5)
        self.assertGreater(len(WAGER_V3_ABI), 5)


if __name__ == "__main__":
    unittest.main()
