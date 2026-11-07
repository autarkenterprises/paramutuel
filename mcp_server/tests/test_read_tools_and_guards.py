"""MCP read tools, input guards and loading fallbacks (ADR-0020, AGENTS.md #2).

An agent acts on what these return without a person checking, so each refusal has to happen here,
with a message it can act on, rather than as a reverted transaction later.
"""
from __future__ import annotations

import asyncio
import json
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import mcp_server.server as srv

ADDR = "0x" + "11" * 20
WAGER = "0x" + "22" * 20
FUTURE = 9_999_999_999


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def recording_get(payload):
    paths = []

    async def fake(path):
        paths.append(path)
        return payload

    return fake, paths


def open_wager(**kw):
    wager = {
        "state": "OPEN",
        "protocol_version": "enumerated",
        "payoff_policy": 0,
        "collateral_token": ADDR,
        "betting_closed_by_authority": 0,
        "betting_close_time": FUTURE,
        "outcomes_json": '["A","B"]',
        "min_new_ticket_stake": "0",
    }
    wager.update(kw)
    return {"wager": wager, "totals": {"total_pot": "1000", "total_fee_bps": "100"}, "ticket_pools": []}


class ReadToolTests(unittest.TestCase):
    def test_list_wagers_builds_the_query(self):
        fake, paths = recording_get({"wagers": [1]})
        with patch.object(srv, "_indexer_get", fake):
            self.assertEqual(json.loads(run(srv.list_wagers())), {"wagers": [1]})
            run(srv.list_wagers(state="open", limit=5))
        self.assertEqual(paths, ["/wagers?limit=100", "/wagers?limit=5&state=OPEN"])

    def test_get_wager_checks_the_address_before_any_request(self):
        fake, paths = recording_get({"wager": {}})
        with patch.object(srv, "_indexer_get", fake):
            run(srv.get_wager(WAGER))
            with self.assertRaises(ValueError):
                run(srv.get_wager("../health"))
        self.assertEqual(paths, [f"/wagers/{WAGER}"], "a bad address must not reach the indexer URL")

    def test_expire_candidates_and_health(self):
        fake, paths = recording_get({"ok": True})
        with patch.object(srv, "_indexer_get", fake):
            self.assertEqual(json.loads(run(srv.get_indexer_health())), {"ok": True})
            run(srv.get_expire_candidates())
        self.assertEqual(paths[0], "/health")
        self.assertRegex(paths[1], r"^/sweeper/expire-candidates\?now=\d+$")


class QuoteGuardTests(unittest.TestCase):
    def _quote(self, payload, **kw):
        fake, _ = recording_get(payload)
        args = dict(wager_address=WAGER, outcome_index=0, amount=5)
        args.update(kw)
        with patch.object(srv, "_indexer_get", fake):
            return json.loads(run(srv.quote_place_bet(**args)))

    def test_single_quote_refusals(self):
        for payload, kw, message in (
            (open_wager(), dict(amount=0), "amount must be"),
            ({}, {}, "no wager payload"),
            (open_wager(state="RESOLVED"), dict(require_open=True), "state != OPEN"),
            (open_wager(betting_closed_by_authority=1), dict(require_open=True), "closed by authority"),
            (open_wager(betting_close_time=1), dict(require_open=True), "has passed"),
            (open_wager(protocol_version="v9"), {}, "Unsupported protocol_version"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                self._quote(payload, **kw)

    def test_a_no_deadline_wager_is_open(self):
        body = self._quote(open_wager(betting_close_time=0))
        self.assertIs(body["betting_open"], True)

    def test_closed_wager_can_be_quoted_for_information_if_asked(self):
        body = self._quote(open_wager(betting_close_time=1))
        self.assertIs(body["betting_open"], False, "require_open defaults to off so an agent can inspect")
        self.assertIn("has passed", body["revert_hint"])

    def _batch(self, payload, **kw):
        fake, _ = recording_get(payload)
        args = dict(wager_address=WAGER, outcome_indices=[0], amounts=[5])
        args.update(kw)
        with patch.object(srv, "_indexer_get", fake):
            return json.loads(run(srv.quote_place_bets(**args)))

    def test_batch_quote_refusals(self):
        for payload, kw, message in (
            (open_wager(), dict(amounts=[1, 2]), "length mismatch"),
            (open_wager(), dict(outcome_indices=[], amounts=[]), "non-empty"),
            (open_wager(), dict(amounts=[0]), "must be > 0"),
            ({}, {}, "no wager payload"),
            (open_wager(state="RESOLVED"), dict(require_open=True), "state != OPEN"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                self._batch(payload, **kw)

    def test_batch_quote_reads_each_pool_and_treats_a_new_outcome_as_empty(self):
        payload = open_wager()
        payload["ticket_pools"] = [{"ticket_mask": "1", "pool_total": "600"}]
        body = self._batch(payload, outcome_indices=[0, 1], amounts=[10, 20])
        self.assertTrue(body["placeBets"]["calldata"].startswith("0x"))

    def test_batch_odds_need_aligned_inputs(self):
        with self.assertRaisesRegex(ValueError, "length mismatch"):
            srv._compute_batch_odds(total_pot=1, outcome_totals=[1], total_fee_bps=0, bet_amounts=[1, 2])


class EncoderGuardTests(unittest.TestCase):
    def test_amounts_must_be_positive(self):
        with self.assertRaisesRegex(ValueError, "amount must be"):
            run(srv.encode_place_bet(WAGER, ADDR, outcome_index=0, amount=0))
        with self.assertRaisesRegex(ValueError, "amount must be"):
            run(srv.encode_place_bet_freeform(WAGER, ADDR, answer="x", amount=0))

    def test_batch_needs_aligned_arrays_either_way(self):
        with self.assertRaisesRegex(ValueError, "ticket_masks and amounts"):
            run(srv.encode_place_bets(WAGER, ADDR, amounts=[1, 2], ticket_masks=[1]))
        with self.assertRaisesRegex(ValueError, "outcome_indices and amounts"):
            run(srv.encode_place_bets(WAGER, ADDR, amounts=[1, 2], outcome_indices=[0]))
        with self.assertRaisesRegex(ValueError, "outcome_indices and amounts"):
            run(srv.encode_place_bets(WAGER, ADDR, amounts=[1]))

    def test_explicit_masks_are_used_exactly(self):
        from eth_abi import decode as abi_decode

        body = json.loads(run(srv.encode_place_bets(WAGER, ADDR, amounts=[7], ticket_masks=[5])))
        masks, amounts = abi_decode(["uint256[]", "uint256[]"], bytes.fromhex(body["calldata"][10:]))
        self.assertEqual((list(masks), list(amounts)), ([5], [7]))

    def test_create_refuses_what_the_factory_is_certain_to_reject(self):
        with self.assertRaisesRegex(ValueError, "resolution_closer"):
            srv._validate_create(1, 0, srv._ZERO_ADDRESS, srv._ZERO_ADDRESS, [], [])
        with self.assertRaisesRegex(ValueError, "betting_closer"):
            srv._validate_create(0, 1, srv._ZERO_ADDRESS, srv._ZERO_ADDRESS, [], [])
        with self.assertRaisesRegex(ValueError, "length mismatch"):
            srv._validate_create(1, 1, srv._ZERO_ADDRESS, srv._ZERO_ADDRESS, [ADDR], [])


class SmallHelperTests(unittest.TestCase):
    def test_outcome_count_tolerates_bad_stored_json(self):
        self.assertEqual(srv._outcome_count({"outcomes_json": "{nope"}), 0)

    def test_odds_are_only_exact_for_policies_the_model_describes(self):
        self.assertIs(srv._odds_model_exact({"protocol_version": "enumerated", "payoff_policy": ""}), False)
        self.assertIs(srv._odds_model_exact({"protocol_version": "enumerated", "payoff_policy": 0}), True)
        self.assertIs(srv._odds_model_exact({"protocol_version": "enumerated", "payoff_policy": 3}), False)


class LoadingFallbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_abi_comes_from_the_package_then_the_repo_then_forge_output(self):
        nowhere = self.root / "nowhere"
        repo_abi = self.root / "repo"
        repo_abi.mkdir()
        (repo_abi / "X.json").write_text(json.dumps({"abi": ["from repo"]}))
        out = self.root / "out" / "Y.sol"
        out.mkdir(parents=True)
        (out / "Y.json").write_text(json.dumps({"abi": ["from out"]}))
        with patch.object(srv, "_PACKAGE_ABI_DIR", nowhere), patch.object(srv, "_REPO_ABI_DIR", repo_abi), patch.object(srv, "_ROOT", self.root):
            self.assertEqual(srv._load_abi("X"), ["from repo"])
            self.assertEqual(srv._load_abi("Y"), ["from out"])

    def test_deployments_are_empty_when_neither_copy_exists(self):
        """A source tree with no config must still import, so that tests and tooling can load it."""
        with patch.object(srv, "_DEPLOYMENTS_PATH", self.root / "absent.json"), patch.object(srv, "__file__", str(self.root / "server.py")):
            self.assertEqual(srv._load_deployments(), {})


class EntrypointTests(unittest.TestCase):
    def test_python_dash_m_starts_the_server(self):
        with patch.object(srv.mcp_server, "run") as started:
            runpy.run_module("mcp_server", run_name="__main__")
        started.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
