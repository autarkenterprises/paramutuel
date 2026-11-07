"""ADR-0020 regressions for the proposition service."""
import json
import os
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib import error, request

from eth_abi import decode as abi_decode

from service.proposition import db as dbm
from service.proposition import dispatch as dispatchm
from service.proposition import rss, server, synthesize

KEY = "0x" + "cd" * 32
ADDR = "0x" + "11" * 20
SCHEMA = Path(server.__file__).with_name("schema.sql")


class DispatchTests(unittest.TestCase):
    def _kwargs(self, **kw):
        base = dict(
            proposition='"Quoted" headline ',
            outcomes=["Oui, très bien", "No"],
            factory=ADDR,
            collateral=ADDR,
            rpc_url="http://r",
            private_key=KEY,
            betting_close_time=100,
            resolution_window=100,
            resolver=ADDR,
            betting_closer=ADDR,
            resolution_closer=ADDR,
            extra_recipients=[],
            extra_bps=[],
        )
        base.update(kw)
        return base

    def test_dry_run_never_returns_the_key(self):
        result = dispatchm.dispatch_proposal(**self._kwargs(dry_run=True))
        self.assertNotIn(KEY[2:], json.dumps(result))
        self.assertIn("<redacted>", result["command"])

    def test_text_reaches_the_chain_exactly(self):
        result = dispatchm.dispatch_proposal(**self._kwargs(dry_run=True))
        args = abi_decode(["address", "string", "string[]"], bytes.fromhex(result["command"][-1][10:]))
        self.assertEqual(args[1], '"Quoted" headline ')
        self.assertEqual(list(args[2]), ["Oui, très bien", "No"])

    def test_mined_revert_is_not_ok(self):
        """Otherwise the proposal is marked `dispatched` for a wager that does not exist."""
        fake = mock.Mock(returncode=0, stdout=json.dumps({"status": "0x0", "transactionHash": "0xfeed"}), stderr="")
        with mock.patch("service.control_panel.commands.subprocess.run", return_value=fake):
            result = dispatchm.dispatch_proposal(**self._kwargs())
        self.assertFalse(result["ok"])
        self.assertIn("reverted", result["stderr"])

    def test_success_is_ok(self):
        fake = mock.Mock(returncode=0, stdout=json.dumps({"status": "0x1", "transactionHash": "0xbeef"}), stderr="")
        with mock.patch("service.control_panel.commands.subprocess.run", return_value=fake):
            result = dispatchm.dispatch_proposal(**self._kwargs())
        self.assertTrue(result["ok"])
        self.assertEqual(result["tx_hash"], "0xbeef")


class ServerTests(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        conn = dbm.connect(self.db_path)
        dbm.init_schema(conn, SCHEMA)
        self.pid = dbm.insert_proposal(
            conn, cadence="event", category="news", proposition="P?", outcomes=["Yes", "No"], rationale="r",
            source_refs=[], source_item_ids=[],
        )
        dbm.update_proposal_status(conn, self.pid, status="approved")
        conn.close()
        H = server.Handler
        H.db_path, H.auth_token, H.factory, H.collateral, H.rpc_url, H.private_key, H.allow_execute = (
            self.db_path, "tok", ADDR, ADDR, "http://r", KEY, True,
        )
        H.resolver, H.betting_closer, H.resolution_closer = ADDR, ADDR, ADDR
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        os.remove(self.db_path)

    def _post(self, path):
        req = request.Request(self.base + path, data=b"", method="POST", headers={"Authorization": "Bearer tok"})
        try:
            with request.urlopen(req, timeout=15) as resp:
                return resp.status, json.loads(resp.read().decode())
        except error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode())

    def _status(self):
        conn = dbm.connect(self.db_path)
        row = dbm.get_proposal(conn, self.pid)
        conn.close()
        return row["status"]

    def test_concurrent_dispatch_creates_only_one_wager(self):
        """Two requests could both read `approved` and both send a create transaction."""
        calls = []

        def slow_success(*a, **k):
            calls.append(1)
            time.sleep(0.3)
            return mock.Mock(returncode=0, stdout=json.dumps({"status": "0x1", "transactionHash": "0xbeef"}), stderr="")

        results = []
        with mock.patch("service.control_panel.commands.subprocess.run", side_effect=slow_success):
            threads = [
                threading.Thread(target=lambda: results.append(self._post(f"/api/proposals/{self.pid}/dispatch")))
                for _ in range(3)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        self.assertEqual(len(calls), 1)
        self.assertEqual(sorted(r[0] for r in results), [200, 400, 400])
        self.assertEqual(self._status(), "dispatched")

    def test_mined_revert_marks_dispatch_failed(self):
        fake = mock.Mock(returncode=0, stdout=json.dumps({"status": "0x0", "transactionHash": "0xfeed"}), stderr="")
        with mock.patch("service.control_panel.commands.subprocess.run", return_value=fake):
            self._post(f"/api/proposals/{self.pid}/dispatch")
        self.assertEqual(self._status(), "dispatch_failed")

    def test_failed_dispatch_can_be_retried_explicitly(self):
        """`dispatch_failed` was terminal, stranding a proposal after one transient RPC failure."""
        fail = mock.Mock(returncode=1, stdout="", stderr="rpc down")
        with mock.patch("service.control_panel.commands.subprocess.run", return_value=fail):
            self._post(f"/api/proposals/{self.pid}/dispatch")
        self.assertEqual(self._status(), "dispatch_failed")
        code, _ = self._post(f"/api/proposals/{self.pid}/retry")
        self.assertEqual(code, 200)
        self.assertEqual(self._status(), "approved")

    def test_retry_only_applies_to_failed_dispatches(self):
        code, _ = self._post(f"/api/proposals/{self.pid}/retry")
        self.assertEqual(code, 400)
        self.assertEqual(self._status(), "approved")


class FeedParsingTests(unittest.TestCase):
    def test_rss_pubdate_is_parsed(self):
        """Only digit strings were recognised, so `published_at` was NULL for all normal RSS."""
        self.assertEqual(rss.published_ts("Thu, 01 Jan 2026 00:00:00 GMT"), 1767225600)

    def test_atom_timestamp_is_parsed(self):
        self.assertEqual(rss.published_ts("2026-01-01T00:00:00Z"), 1767225600)
        self.assertEqual(rss.published_ts("2026-01-01T01:00:00+01:00"), 1767225600)

    def test_epoch_values_still_work(self):
        self.assertEqual(rss.published_ts("1767225600"), 1767225600)
        self.assertEqual(rss.published_ts("1767225600000"), 1767225600)

    def test_unparseable_is_none(self):
        self.assertIsNone(rss.published_ts("yesterday"))
        self.assertIsNone(rss.published_ts(None))

    def test_title_with_nested_markup_is_kept(self):
        """`_text` returned "" whenever an element had no leading text, losing `<title><b>x</b></title>`."""
        items = rss.parse_feed_xml(b"<rss><channel><item><title><b>Bold</b> news</title><guid>g</guid></item></channel></rss>")
        self.assertIn("Bold", items[0].title)

    def test_rss_1_0_rdf_feed_is_parsed(self):
        """The `rdf:rdf` branch compared against a namespace-stripped tag, so it could never match."""
        xml = b"""<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/">
          <channel><title>c</title></channel>
          <item><title>One</title><link>https://example.com/1</link></item>
        </rdf:RDF>"""
        items = rss.parse_feed_xml(xml)
        self.assertEqual([i.title for i in items], ["One"])
        self.assertEqual(items[0].link, "https://example.com/1")


class SafeLinkTests(unittest.TestCase):
    def test_non_http_source_links_are_dropped(self):
        """Feed content is untrusted and these render as clickable links in the operator panel."""
        for bad in ("javascript:alert(1)", " JaVaScRiPt:alert(1)", "data:text/html,x", "file:///etc/passwd"):
            with self.subTest(bad=bad):
                _, _, _, refs = synthesize.build_proposition_bundle(
                    headline="H", source_label="S", category="c", link=bad, cadence="event"
                )
                self.assertEqual(refs, [{"label": "S", "url": ""}])

    def test_http_links_survive(self):
        for good in ("https://example.com/a?b=c", "http://example.com"):
            with self.subTest(good=good):
                _, _, _, refs = synthesize.build_proposition_bundle(
                    headline="H", source_label="S", category="c", link=good, cadence="event"
                )
                self.assertEqual(refs[0]["url"], good)


if __name__ == "__main__":
    unittest.main()
