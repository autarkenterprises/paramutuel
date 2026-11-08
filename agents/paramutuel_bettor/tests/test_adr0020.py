"""ADR-0020 regressions for the bet scout."""
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from eth_hash.auto import keccak

from agents.paramutuel_bettor import __main__ as cli
from agents.paramutuel_bettor import calldata, planner, policy

ADDR = "0x" + "11" * 20
FUTURE = 9_999_999_999
NASTY = ["Paris", " Paris ", "Paris ", '"Paris"', "'Paris'", "--help", "-5", "café ☕", "a,b", "x" * 33]


class NativeEncodingTests(unittest.TestCase):
    """`cast calldata` strips trailing whitespace and surrounding quotes, so the scout could hand an
    agent calldata for a different answer than the one it reported. It also made calldata depend on
    Foundry being installed, for a package advertised as stdlib-only."""

    def test_selectors_are_correct(self):
        for signature, selector in calldata.SELECTORS.items():
            with self.subTest(signature=signature):
                self.assertEqual(selector, "0x" + keccak(signature.encode())[:4].hex())

    def test_freeform_bet_matches_an_independent_encoder_for_every_awkward_string(self):
        for answer in NASTY:
            with self.subTest(answer=answer):
                expected = keccak(b"placeBet(string,uint256)")[:4] + abi_encode(["string", "uint256"], [answer, 7])
                self.assertEqual(calldata.encode_place_bet_freeform(answer, 7), "0x" + expected.hex())

    def test_resolve_matches_an_independent_encoder(self):
        for answer in NASTY:
            with self.subTest(answer=answer):
                expected = keccak(b"resolve(string)")[:4] + abi_encode(["string"], [answer])
                self.assertEqual(calldata.encode_resolve_freeform(answer), "0x" + expected.hex())

    def test_enumerated_bet_and_approve_match(self):
        expected = keccak(b"placeBet(uint256,uint256)")[:4] + abi_encode(["uint256", "uint256"], [2**200, 9])
        self.assertEqual(calldata.encode_place_bet(2**200, 9), "0x" + expected.hex())
        expected = keccak(b"approve(address,uint256)")[:4] + abi_encode(["address", "uint256"], [ADDR, 9])
        self.assertEqual(calldata.encode_approve(ADDR, 9), "0x" + expected.hex())

    def test_works_with_no_foundry_installed(self):
        source = Path(calldata.__file__).read_text(encoding="utf-8")
        self.assertNotIn("subprocess", source)
        self.assertNotIn("shutil", source)
        with mock.patch.dict("os.environ", {"PATH": ""}):
            self.assertIsNotNone(calldata.encode_place_bet(1, 1))


class FakeClient:
    base_url = "http://fixture"

    def __init__(self, detail, rows=None):
        self.detail = detail
        self.rows = rows or []

    def get_wager(self, wager_address, answer_id=None):
        return self.detail

    def list_wagers(self, **kw):
        return self.rows


def enum_detail(policy_id=0, **wager_fields):
    wager = {
        "state": "OPEN",
        "protocol_version": "enumerated",
        "payoff_policy": policy_id,
        "collateral_token": ADDR,
        "betting_closed_by_authority": 0,
        "betting_close_time": FUTURE,
        "outcomes_json": '["A","B"]',
        "min_new_ticket_stake": "0",
    }
    wager.update(wager_fields)
    return {"wager": wager, "totals": {"total_pot": "1000", "total_fee_bps": "0"}, "ticket_pools": [{"ticket_mask": "1", "pool_total": "400"}]}


class QuoteTests(unittest.TestCase):
    def test_quote_flags_inexact_odds_for_multi_winner_policies(self):
        """ADR-0019 fixed recommend and the MCP quote; this path still presented a false multiple."""
        q = planner.quote_wager(FakeClient(enum_detail(policy_id=1)), wager_address=ADDR, outcome_index=0, bet_amount_raw=5)
        self.assertFalse(q["odds_model_exact"])
        self.assertIn("winning", q["odds_note"])

    def test_quote_marks_single_winner_exact(self):
        q = planner.quote_wager(FakeClient(enum_detail()), wager_address=ADDR, outcome_index=0, bet_amount_raw=5)
        self.assertTrue(q["odds_model_exact"])
        self.assertNotIn("odds_note", q)

    def test_out_of_range_outcome_rejected(self):
        for bad in (2, -1):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                planner.quote_wager(FakeClient(enum_detail()), wager_address=ADDR, outcome_index=bad, bet_amount_raw=5)

    def test_new_ticket_below_minimum_is_not_executable(self):
        d = enum_detail(min_new_ticket_stake="100")
        q = planner.quote_wager(FakeClient(d), wager_address=ADDR, outcome_index=1, bet_amount_raw=99)
        self.assertFalse(q["quote"]["execution_allowed"])
        self.assertIn("minNewTicketStake", q["quote"]["revert_hint"])
        q = planner.quote_wager(FakeClient(d), wager_address=ADDR, outcome_index=0, bet_amount_raw=1)
        self.assertTrue(q["quote"]["execution_allowed"], "an existing ticket needs no minimum")


def freeform_detail(text="Paris", hex_value="0x5061726973"):
    return {
        "wager": {
            "state": "OPEN",
            "protocol_version": "freeform",
            "collateral_token": ADDR,
            "betting_closed_by_authority": 0,
            "betting_close_time": FUTURE,
            "outcomes_json": "[]",
            "wager_address": ADDR,
        },
        "totals": {"total_pot": "100", "total_fee_bps": "0"},
        "ticket_pools": [{"ticket_mask": "0x" + "ab" * 32, "pool_total": "100", "answer_text": text, "answer_hex": hex_value}],
    }


class FreeformTests(unittest.TestCase):
    def test_pick_exposes_answer_text_from_the_indexer(self):
        pick = policy.pick_outcome(strategy="best_post_multiple", wager_detail=freeform_detail(" Paris "), bet_amount=5)
        self.assertEqual(pick["answer_text"], " Paris ")

    def test_recommendation_for_a_known_answer_is_executable_and_exact(self):
        """Without the text every freeform recommendation was unusable (ADR-0009 "observed answers")."""
        row = {"wager_address": ADDR, "total_pot": "100", "proposition": "Q?", "protocol_version": "freeform"}
        out = planner.recommend(FakeClient(freeform_detail(" Paris "), [row]), strategy="best_post_multiple", bet_amount_raw=5)
        quote = out["recommendations"][0]["quote"]
        self.assertTrue(quote["execution_allowed"])
        answer, _ = abi_decode(["string", "uint256"], bytes.fromhex(quote["placeBet"]["calldata"][10:]))
        self.assertEqual(answer, " Paris ")

    def test_answer_without_text_stays_not_executable(self):
        row = {"wager_address": ADDR, "total_pot": "100", "proposition": "Q?", "protocol_version": "freeform"}
        out = planner.recommend(FakeClient(freeform_detail(None, "0xfffe"), [row]), strategy="best_post_multiple", bet_amount_raw=5)
        self.assertFalse(out["recommendations"][0]["quote"]["execution_allowed"])


class CliTests(unittest.TestCase):
    def _run(self, argv, stdin=""):
        out = io.StringIO()
        with mock.patch.object(cli, "IndexerClient", return_value=FakeClient(freeform_detail())), \
                mock.patch.object(sys, "stdin", io.StringIO(stdin)), contextlib.redirect_stdout(out):
            code = cli.main(argv)
        return code, json.loads(out.getvalue())

    def test_cli_freeform_answer_is_byte_exact(self):
        """Documented as "Exact UTF-8 answer", but stripped."""
        _, body = self._run(["quote", "--wager", ADDR, "--outcome-index", "0", "--bet-amount-raw", "5", "--freeform-answer=  Paris  "])
        answer, _ = abi_decode(["string", "uint256"], bytes.fromhex(body["quote"]["placeBet"]["calldata"][10:]))
        self.assertEqual(answer, "  Paris  ")

    def test_json_bridge_freeform_answer_is_byte_exact(self):
        request = {"op": "quote", "wager_address": ADDR, "outcome_index": 0, "bet_amount_raw": 5, "freeform_answer": " Paris "}
        _, body = self._run(["json"], json.dumps(request))
        answer, _ = abi_decode(["string", "uint256"], bytes.fromhex(body["quote"]["placeBet"]["calldata"][10:]))
        self.assertEqual(answer, " Paris ")

    def test_json_bridge_missing_field_is_a_value_error_not_a_type_error(self):
        """The module promises JSON errors. A TypeError escaped as a traceback, breaking callers."""
        with self.assertRaises(ValueError):
            self._run(["json"], json.dumps({"op": "quote", "wager_address": ADDR, "bet_amount_raw": 5}))


class MetadataTests(unittest.TestCase):
    def test_agent_entrypoint_points_at_a_document_for_agents(self):
        """AGENTS.md became the contributor charter, so these links led nowhere useful."""
        root = Path(__file__).resolve().parents[3]
        manifest = json.loads((root / "agents" / "subagent-manifest.json").read_text())
        self.assertIn("docs/MACHINE.md", manifest["project"]["agent_entrypoint_doc"])
        self.assertIn("docs/MACHINE.md", (root / "pyproject.toml").read_text())

    def test_manifest_does_not_claim_an_unpublished_package_is_available(self):
        root = Path(__file__).resolve().parents[3]
        text = (root / "agents" / "subagent-manifest.json").read_text()
        distribution = json.loads(text)["subagents"][0]["distribution"]
        self.assertEqual(distribution["pypi_status"], "not yet published")


if __name__ == "__main__":
    unittest.main()
