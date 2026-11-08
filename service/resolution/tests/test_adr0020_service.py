"""ADR-0020 regressions for the resolution service, over real HTTP where it matters."""
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock
from urllib import error, request

from eth_abi import decode as abi_decode

from service.resolution import service as svc

KEY = "0x" + "cd" * 32
RESOLVER = "0xabc3000000000000000000000000000000000003"
WAGER = "0xabc1000000000000000000000000000000000001"
OPEN_WAGER = {
    "wager_address": WAGER,
    "state": "OPEN",
    "protocol_version": "freeform",
    "resolver": RESOLVER,
    "betting_closed_by_authority": 1,
    "betting_close_time": 0,
    "resolution_window": 0,
    "resolution_window_closed": 0,
}


class FreeformCalldataTests(unittest.TestCase):
    def test_winning_answer_bytes_on_chain_are_exactly_the_decision(self):
        """ADR-0019 asserted on the argv token, which `cast` then altered: "Paris " became "Paris".
        This decodes the calldata that actually reaches the chain."""
        for answer in (" Paris ", "Paris ", '"Paris"', "'Paris'", "--help", "--gas-limit=1", "-5", "café ☕"):
            with self.subTest(answer=answer):
                cmd = svc._action_command(
                    wager_address=WAGER, action="resolve", rpc_url="http://r", private_key=KEY,
                    protocol_version="freeform", winning_answer=answer,
                )
                self.assertEqual(abi_decode(["string"], bytes.fromhex(cmd[-1][10:]))[0], answer)


class PaginationTests(unittest.TestCase):
    def test_load_open_wagers_walks_every_page(self):
        """Only the newest 1000 were ever seen, starving the oldest wagers, which are the ones due."""
        pages = {0: [{"wager_address": f"0x{i:040x}"} for i in range(1000)], 1000: [{"wager_address": "0xlast"}]}
        urls = []

        def fake_get(url, timeout=20):
            urls.append(url)
            offset = int(url.split("offset=")[1].split("&")[0])
            return {"wagers": pages.get(offset, [])}

        with mock.patch.object(svc, "_http_get_json", fake_get):
            rows, truncated = svc._load_open_wagers("http://indexer", limit=None)
        self.assertFalse(truncated)
        self.assertEqual(len(rows), 1001)
        self.assertEqual(rows[-1]["wager_address"], "0xlast")
        self.assertEqual(len(urls), 2)

    def test_explicit_limit_stops_early(self):
        with mock.patch.object(svc, "_http_get_json", return_value={"wagers": [{"a": 1}] * 20}) as g:
            self.assertEqual(len(svc._load_open_wagers("http://indexer", limit=20)[0]), 20)
        # One page, then a one-row probe to learn whether more exist (ADR-0021 U5); never a walk.
        self.assertEqual(g.call_count, 2)


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.decision = {WAGER: {"action": "resolve", "winningAnswer": "the answer"}}
        self._patches = [
            mock.patch.object(svc, "_load_open_wagers", return_value=([dict(OPEN_WAGER)], False)),
            mock.patch.object(svc, "_read_decisions", side_effect=lambda path: self.decision),
        ]
        for p in self._patches:
            p.start()
        svc.Handler.indexer_base_url = "http://indexer.invalid"
        svc.Handler.decisions_path = "unused.json"
        svc.Handler.resolver_address = RESOLVER
        svc.Handler.rpc_url = "http://rpc.invalid"
        svc.Handler.private_key = KEY
        svc.Handler.auth_token = "s3cret"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), svc.Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        for p in self._patches:
            p.stop()
        svc.Handler.auth_token = None

    def _get(self, path, headers=None):
        req = request.Request(self.base + path, headers=headers or {})
        try:
            with request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode())
        except error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode())

    def _post(self, body=None, raw=None):
        data = raw if raw is not None else json.dumps(body).encode()
        req = request.Request(self.base + "/run-once", data=data, method="POST", headers={"X-Token": "s3cret"})
        try:
            with request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode())
        except error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode())

    # O7: a decision file written before betting closes must not become an insider-trading feed.
    def test_candidates_hide_pending_decisions_without_a_token(self):
        code, body = self._get("/candidates")
        self.assertEqual(code, 200)
        text = json.dumps(body)
        self.assertNotIn("the answer", text)
        row = body["candidates"][0]
        self.assertIsNone(row["decision"])
        self.assertNotIn("decision_winning_answer", row)
        self.assertTrue(row["decision_present"], "the operator view still shows that one exists")

    def test_candidates_show_decisions_with_a_token(self):
        code, body = self._get("/candidates", {"Authorization": "Bearer s3cret"})
        self.assertEqual(code, 200)
        self.assertEqual(body["candidates"][0]["decision_winning_answer"], "the answer")

    def test_candidates_bad_limit_is_400(self):
        self.assertEqual(self._get("/candidates?limit=abc")[0], 400)

    def test_indexer_down_is_502_json(self):
        with mock.patch.object(svc, "_load_open_wagers", side_effect=OSError("down")):
            code, body = self._get("/candidates")
        self.assertEqual(code, 502)
        self.assertIn("indexer", body["error"])
        with mock.patch.object(svc, "_load_open_wagers", side_effect=OSError("down")):
            code, _ = self._post({"execute": False})
        self.assertEqual(code, 502)

    def test_run_once_rejects_malformed_json(self):
        self.assertEqual(self._post(raw=b"{nope")[0], 400)

    # O1: a mined revert exits 0 from cast and used to be reported as success.
    def test_execute_reports_a_mined_revert_as_failed(self):
        receipt = json.dumps({"status": "0x0", "transactionHash": "0xfeed"})
        fake = mock.Mock(returncode=0, stdout=receipt, stderr="")
        with mock.patch("service.control_panel.commands.subprocess.run", return_value=fake):
            code, body = self._post({"execute": True})
        self.assertEqual(code, 200)
        self.assertEqual((body["succeeded"], body["failed"]), (0, 1))
        self.assertFalse(body["results"][0]["ok"])
        self.assertIn("reverted", body["results"][0]["stderr"])

    def test_execute_reports_success_with_hash(self):
        receipt = json.dumps({"status": "0x1", "transactionHash": "0xbeef"})
        fake = mock.Mock(returncode=0, stdout=receipt, stderr="")
        with mock.patch("service.control_panel.commands.subprocess.run", return_value=fake):
            _, body = self._post({"execute": True})
        self.assertEqual(body["succeeded"], 1)
        self.assertEqual(body["results"][0]["tx_hash"], "0xbeef")

    # D3: the service's own image shipped without cast.
    def test_execute_without_cast_is_reported_not_a_dropped_connection(self):
        with mock.patch("service.control_panel.commands.subprocess.run", side_effect=FileNotFoundError("cast")):
            code, body = self._post({"execute": True})
        self.assertEqual(code, 200)
        self.assertEqual(body["failed"], 1)
        self.assertIn("PATH", body["results"][0]["stderr"])

    def test_results_never_contain_the_key(self):
        fake = mock.Mock(returncode=1, stdout="", stderr=f"failed with --private-key {KEY}")
        with mock.patch("service.control_panel.commands.subprocess.run", return_value=fake):
            _, body = self._post({"execute": True})
        self.assertNotIn(KEY[2:], json.dumps(body))


class StartupTests(unittest.TestCase):
    def test_deriving_address_without_cast_explains_itself(self):
        with mock.patch.object(svc.subprocess, "run", side_effect=FileNotFoundError("cast")):
            with self.assertRaises(RuntimeError) as ctx:
                svc._extract_resolver_address("", KEY)
        self.assertIn("RESOLUTION_SERVICE_ADDRESS", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
