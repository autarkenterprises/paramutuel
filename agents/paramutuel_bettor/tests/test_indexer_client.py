"""The scout's connection to the world: its HTTP client, JSON bridge and command line (ADR-0020).

The other scout tests use a fake client, so until now nothing exercised real HTTP or the commands a
parent agent actually runs.
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlparse

from agents.paramutuel_bettor import __main__ as cli
from agents.paramutuel_bettor import config, odds, planner, policy
from agents.paramutuel_bettor.indexer_client import IndexerClient

ROOT = Path(__file__).resolve().parents[3]
ADDR = "0x" + "11" * 20
FUTURE = 9_999_999_999


def wager_row(addr=ADDR, pot="1000", proposition="Will it rain?"):
    return {
        "wager_address": addr,
        "state": "OPEN",
        "protocol_version": "enumerated",
        "payoff_policy": 0,
        "collateral_token": ADDR,
        "betting_closed_by_authority": 0,
        "betting_close_time": FUTURE,
        "outcomes_json": '["Yes", "No"]',
        "proposition": proposition,
        "total_pot": pot,
        "total_fee_bps": "100",
    }


def wager_detail(addr=ADDR):
    return {
        "wager": wager_row(addr),
        "totals": {"total_pot": "1000", "total_fee_bps": "100"},
        "outcomes": [{"outcome_index": 0, "total": "600"}, {"outcome_index": 1, "total": "400"}],
        "ticket_pools": [{"ticket_mask": "1", "pool_total": "600"}, {"ticket_mask": "2", "pool_total": "400"}],
    }


class FakeIndexer(BaseHTTPRequestHandler):
    paths: list = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        type(self).paths.append(self.path)
        parsed = urlparse(self.path)
        code, body = 200, {}
        if parsed.path == "/health":
            body = {"ok": True, "wager_count": 1}
        elif parsed.path == "/wagers":
            body = {"wagers": [wager_row()]}
        elif parsed.path == f"/wagers/{ADDR}":
            body = wager_detail()
        elif parsed.path == "/list":
            body = ["not", "an", "object"]
        else:
            code, body = 500, {"error": "database is locked"}
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class ServerCase(unittest.TestCase):
    def setUp(self):
        FakeIndexer.paths = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeIndexer)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()


class ClientTests(ServerCase):
    def test_health_and_wager_detail(self):
        client = IndexerClient(self.url + "/")
        self.assertEqual(client.base_url, self.url, "a trailing slash must not double up in URLs")
        self.assertEqual(client.health()["wager_count"], 1)
        self.assertEqual(client.get_wager("  " + ADDR.upper().replace("0X", "0x") + " ")["wager"]["wager_address"], ADDR)
        self.assertEqual(FakeIndexer.paths[-1], f"/wagers/{ADDR}", "addresses are normalized before use")

    def test_list_sends_a_bounded_well_formed_query(self):
        rows = IndexerClient(self.url).list_wagers(state="open", limit=5000, offset=-3, order="asc", q=" team a&b ")
        self.assertEqual(len(rows), 1)
        query = parse_qs(urlparse(FakeIndexer.paths[-1]).query)
        self.assertEqual(query["limit"], ["1000"], "the API's own maximum")
        self.assertEqual(query["offset"], ["0"])
        self.assertEqual(query["state"], ["OPEN"])
        self.assertEqual(query["order"], ["asc"])
        self.assertEqual(query["q"], ["team a&b"], "search text is escaped and trimmed")

    def test_optional_filters_are_left_out_when_unset(self):
        IndexerClient(self.url).list_wagers(q="   ")
        self.assertNotIn("q=", FakeIndexer.paths[-1])
        self.assertNotIn("state=", FakeIndexer.paths[-1])

    def test_http_errors_carry_status_and_detail(self):
        with self.assertRaisesRegex(RuntimeError, "indexer HTTP 500.*database is locked"):
            IndexerClient(self.url)._get("/boom")

    def test_connection_failures_are_clear(self):
        with self.assertRaisesRegex(RuntimeError, "indexer request failed"):
            IndexerClient("http://127.0.0.1:9", timeout=2).health()

    def test_unexpected_response_shapes_become_empty_values(self):
        client = IndexerClient(self.url)
        with mock.patch.object(client, "_get", return_value=["x"]):
            self.assertEqual(client.health(), {})
            self.assertEqual(client.list_wagers(), [])
            self.assertEqual(client.get_wager(ADDR), {})
        with mock.patch.object(client, "_get", return_value={"wagers": "x"}):
            self.assertEqual(client.list_wagers(), [])


class CommandLineTests(ServerCase):
    def _run(self, *argv, stdin=""):
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(stdin)), contextlib.redirect_stdout(out):
            rc = cli.main(["--indexer-url", self.url, *argv])
        return rc, json.loads(out.getvalue())

    def test_health_command(self):
        rc, body = self._run("health")
        self.assertEqual(rc, 0)
        self.assertEqual(body["indexer_url"], self.url)
        self.assertEqual(body["health"]["wager_count"], 1)

    def test_scan_command_summarizes_rows(self):
        _, body = self._run("scan", "--state", "OPEN", "--limit", "5", "--q", "rain")
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["wagers"][0]["outcome_labels_preview"], ["Yes", "No"])
        self.assertIn("q=rain", FakeIndexer.paths[-1])

    def test_recommend_command_returns_signable_calldata(self):
        _, body = self._run("recommend", "--bet-amount-raw", "100", "--top", "1")
        self.assertEqual(len(body["recommendations"]), 1)
        quote = body["recommendations"][0]["quote"]
        self.assertTrue(quote["placeBet"]["calldata"].startswith("0x"))
        self.assertIs(quote["execution_allowed"], True)

    def test_json_bridge_ops(self):
        self.assertEqual(self._run("json", stdin='{"op": "health"}')[1]["health"]["wager_count"], 1)
        self.assertEqual(self._run("json", stdin='{"op": "scan", "state": "OPEN", "limit": 3}')[1]["count"], 1)
        body = self._run("json", stdin='{"op": "recommend", "bet_amount_raw": 100, "top": 1}')[1]
        self.assertEqual(len(body["recommendations"]), 1)

    def test_json_bridge_rejects_bad_requests_clearly(self):
        for stdin, message in (
            ("[1]", "must be an object"),
            ('{"op": "nonsense"}', "unknown op"),
            ('{"op": "recommend"}', "bet_amount_raw"),
            ('{"op": "quote", "outcome_index": 0}', "wager_address"),
        ):
            with self.subTest(stdin=stdin), self.assertRaisesRegex(ValueError, message):
                self._run("json", stdin=stdin)

    def test_script_mode_reports_errors_as_json_with_a_failing_exit_code(self):
        """A parent agent parses this. A Python traceback would look like the scout itself is broken."""
        done = subprocess.run(
            [sys.executable, "-m", "agents.paramutuel_bettor", "--indexer-url", "http://127.0.0.1:9", "--timeout", "2", "health"],
            capture_output=True,
            text=True,
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": str(ROOT)},
            timeout=60,
        )
        self.assertEqual(done.returncode, 1)
        body = json.loads(done.stderr)
        self.assertIs(body["ok"], False)
        self.assertIn("indexer request failed", body["error"])


class ConfigTests(unittest.TestCase):
    def test_environment_wins_and_loses_its_trailing_slash(self):
        with mock.patch.dict(os.environ, {"INDEXER_URL": " https://x/ "}, clear=True):
            self.assertEqual(config.load_default_indexer_url(), "https://x")

    def _with_config(self, text):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "config").mkdir()
        (root / "config" / "deployments.json").write_text(text)
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(config, "repo_root", return_value=root):
            return config.load_default_indexer_url()

    def test_reads_the_default_network_from_config(self):
        text = json.dumps({"defaultNetwork": "baseMainnet", "baseMainnet": {"explorerApiBase": "https://main/"}})
        self.assertEqual(self._with_config(text), "https://main")

    def test_broken_or_incomplete_config_falls_back_to_localhost(self):
        self.assertEqual(self._with_config("{nope"), "http://127.0.0.1:8090")
        self.assertEqual(self._with_config("{}"), "http://127.0.0.1:8090")


class FakeClient:
    base_url = "http://fixture"

    def __init__(self, rows, details=None, error=None):
        self.rows, self.details, self.error = rows, details or {}, error

    def list_wagers(self, **kw):
        return self.rows

    def get_wager(self, addr):
        if self.error:
            raise self.error
        return self.details[addr]


class RecommendFilterTests(unittest.TestCase):
    def test_filters_apply_before_any_detail_lookup(self):
        low_pot = wager_row("0x" + "22" * 20, pot="5")
        wrong_topic = wager_row("0x" + "33" * 20, proposition="Who wins the cup?")
        no_address = wager_row("")
        good = wager_row(ADDR)
        client = FakeClient([low_pot, wrong_topic, no_address, good], {ADDR: wager_detail(ADDR)})
        out = planner.recommend(
            client,
            strategy="best_post_multiple",
            bet_amount_raw=100,
            scan_limit=10,
            min_total_pot_raw=100,
            proposition_contains="RAIN",
            top=5,
        )
        self.assertEqual(out["candidates_scanned"], 2, "the row with no address is dropped later, without a lookup")
        self.assertEqual([r["summary"]["wager_address"] for r in out["recommendations"]], [ADDR])

    def test_one_failing_lookup_is_reported_and_does_not_stop_the_scan(self):
        client = FakeClient([wager_row(ADDR)], error=RuntimeError("indexer HTTP 500"))
        out = planner.recommend(
            client, strategy="best_post_multiple", bet_amount_raw=100, scan_limit=10, min_total_pot_raw=0, proposition_contains=None, top=5
        )
        self.assertEqual(out["recommendations"], [])
        self.assertIn("indexer HTTP 500", out["errors_sample"][0])


class SmallHelperTests(unittest.TestCase):
    def test_unparseable_outcome_labels_are_empty(self):
        self.assertEqual(policy._outcome_labels({"outcomes_json": "{nope"}), [])
        self.assertEqual(policy._outcome_labels({"outcomes_json": ["a", 1]}), ["a", "1"])

    def test_pool_lookup_tolerates_junk_rows_and_missing_masks(self):
        pools = ["junk", {"ticket_mask": "1", "pool_total": "7"}]
        self.assertEqual(policy._ticket_pool_total(pools, 1), 7)
        self.assertEqual(policy._ticket_pool_total(pools, 2), 0)

    def test_quote_needs_a_positive_amount(self):
        with self.assertRaisesRegex(ValueError, "bet_amount"):
            odds.compute_odds(total_pot=1, outcome_total=1, total_fee_bps=0, bet_amount=0)

    def test_betting_status(self):
        self.assertEqual(odds.betting_open_status({"state": "RESOLVED"}, now_ts=1), (False, "wager.state != OPEN"))
        self.assertEqual(odds.betting_open_status({"state": "OPEN", "betting_close_time": 0}, now_ts=1), (True, ""))
        self.assertFalse(odds.betting_open_status({"state": "OPEN", "betting_closed_by_authority": 1}, now_ts=1)[0])
        self.assertFalse(odds.betting_open_status({"state": "OPEN", "betting_close_time": 5}, now_ts=5)[0])


if __name__ == "__main__":
    unittest.main()
