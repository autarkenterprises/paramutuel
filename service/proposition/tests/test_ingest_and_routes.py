"""ADR-0020: the ingest driver and operator API routes had no tests at all (AGENTS.md #2)."""
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib import error, request

from service.proposition import db as dbm
from service.proposition import ingest, json_sources, rss, server

SCHEMA = Path(server.__file__).with_name("schema.sql")


def feed_item(ext="g1", title="Headline"):
    return rss.FeedItem(external_id=ext, title=title, link="https://example.com/a", summary="", published_raw="1767225600", raw={})


class IngestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "p.db")
        self.conn = dbm.connect(self.db)
        dbm.init_schema(self.conn, SCHEMA)
        self.sources = Path(self.tmp.name) / "sources.json"

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def _run(self, sources, **kw):
        self.sources.write_text(json.dumps(sources))
        return ingest.run_ingest(conn=self.conn, sources_path=self.sources, **kw)

    def _proposals(self):
        return dbm.list_proposals(self.conn)

    def test_rss_source_creates_a_pending_proposal_and_stores_the_date(self):
        with mock.patch.object(rss, "fetch_rss_items", return_value=[feed_item()]):
            summary = self._run({"sources": [{"id": "s", "type": "rss", "url": "https://f", "label": "Feed", "category": "news"}]})
        self.assertEqual((summary["new_source_rows"], summary["new_proposals"]), (1, 1))
        rows = self._proposals()
        self.assertEqual(rows[0]["status"], "pending")
        self.assertIn("Headline", rows[0]["proposition"])
        stored = self.conn.execute("SELECT published_at FROM source_items").fetchone()
        self.assertEqual(stored["published_at"], 1767225600)

    def test_rerun_creates_no_duplicates(self):
        sources = [{"id": "s", "type": "rss", "url": "https://f"}]
        with mock.patch.object(rss, "fetch_rss_items", return_value=[feed_item()]):
            self._run(sources)
            summary = self._run(sources)
        self.assertEqual(summary["new_proposals"], 0)
        self.assertEqual(len(self._proposals()), 1)

    def test_hackernews_and_json_sources(self):
        item = json_sources.JsonItem(external_id="1", title="T", link="https://x", summary="", raw={})
        with mock.patch.object(json_sources, "fetch_hackernews_top", return_value=[item]), \
                mock.patch.object(json_sources, "fetch_json_array", return_value=[json_sources.JsonItem("2", "U", "", "", {})]):
            summary = self._run([{"id": "h", "type": "hackernews"}, {"id": "j", "type": "json_array", "url": "https://j"}])
        self.assertEqual(summary["new_proposals"], 2)

    def test_one_bad_source_does_not_stop_the_others_and_is_reported(self):
        def fetch(url):
            if "bad" in url:
                raise OSError("timeout")
            return [feed_item()]

        with mock.patch.object(rss, "fetch_rss_items", side_effect=fetch):
            summary = self._run([{"id": "bad", "type": "rss", "url": "https://bad"}, {"id": "ok", "type": "rss", "url": "https://ok"}])
        self.assertEqual(summary["new_proposals"], 1)
        self.assertEqual(len(summary["errors"]), 1)
        self.assertIn("timeout", summary["errors"][0])

    def test_disabled_and_urlless_sources_are_skipped(self):
        with mock.patch.object(rss, "fetch_rss_items") as fetch:
            summary = self._run([{"id": "off", "type": "rss", "url": "https://f", "enabled": False}, {"id": "nourl", "type": "rss"}])
        fetch.assert_not_called()
        self.assertEqual(summary["new_proposals"], 0)

    def test_missing_or_malformed_config_is_no_sources(self):
        self.assertEqual(ingest.load_sources_config(Path(self.tmp.name) / "absent.json"), [])
        self.sources.write_text('"just a string"')
        self.assertEqual(ingest.load_sources_config(self.sources), [])


class RouteTests(unittest.TestCase):
    def setUp(self):
        fd, self.db = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        conn = dbm.connect(self.db)
        dbm.init_schema(conn, SCHEMA)
        self.pid = dbm.insert_proposal(
            conn, cadence="event", category="c", proposition="P?", outcomes=["Y", "N"], rationale="r", source_refs=[], source_item_ids=[]
        )
        conn.close()
        H = server.Handler
        H.db_path = self.db
        H.auth_token = "tok"
        H.sources_path = Path("/nonexistent")
        H.allow_execute = False
        H.private_key = "secret-key-value"
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        os.remove(self.db)

    def _call(self, method, path, body=None, token="tok"):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        data = json.dumps(body).encode() if body is not None else (b"" if method != "GET" else None)
        req = request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode())
        except error.HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read().decode())
            except json.JSONDecodeError:
                return exc.code, {}

    def test_health_is_open_and_everything_else_needs_the_token(self):
        self.assertEqual(self._call("GET", "/health", token=None)[0], 200)
        for method, path in (("GET", "/api/proposals"), ("GET", "/api/config"), ("GET", "/api/sources"),
                             ("POST", "/api/ingest"), ("POST", f"/api/proposals/{self.pid}/approve"), ("PATCH", f"/api/proposals/{self.pid}")):
            with self.subTest(path=path):
                self.assertEqual(self._call(method, path, token=None)[0], 401)
                self.assertEqual(self._call(method, path, token="wrong")[0], 401)

    def test_config_never_reveals_the_key(self):
        code, body = self._call("GET", "/api/config")
        self.assertEqual(code, 200)
        self.assertTrue(body["private_key_set"])
        self.assertNotIn("secret-key-value", json.dumps(body))

    def test_review_flow(self):
        code, body = self._call("GET", "/api/proposals?status=pending")
        self.assertEqual((code, len(body["proposals"])), (200, 1))

        self.assertEqual(self._call("PATCH", f"/api/proposals/{self.pid}", {"proposition": "Better?", "outcomes": ["A", "B"]})[0], 200)
        self.assertEqual(self._call("PATCH", f"/api/proposals/{self.pid}", {"proposition": "", "outcomes": ["A"]})[0], 400)

        self.assertEqual(self._call("POST", f"/api/proposals/{self.pid}/approve")[0], 200)
        self.assertEqual(self._call("POST", f"/api/proposals/{self.pid}/approve")[0], 400, "only once")
        self.assertEqual(self._call("POST", f"/api/proposals/{self.pid}/reject")[0], 400, "approved is past rejecting")
        self.assertEqual(self._call("PATCH", f"/api/proposals/{self.pid}", {"proposition": "Late?", "outcomes": ["A", "B"]})[0], 400, "only pending is editable")

        body = self._call("GET", "/api/proposals")[1]["proposals"][0]
        self.assertEqual(body["proposition"], "Better?")
        self.assertEqual(body["status"], "approved")

    def test_reject(self):
        self.assertEqual(self._call("POST", f"/api/proposals/{self.pid}/reject")[0], 200)
        self.assertEqual(self._call("GET", "/api/proposals?status=rejected")[1]["proposals"][0]["id"], self.pid)

    def test_dispatch_is_refused_while_execution_is_disabled(self):
        self._call("POST", f"/api/proposals/{self.pid}/approve")
        self.assertEqual(self._call("POST", f"/api/proposals/{self.pid}/dispatch")[0], 403)

    def test_dispatch_needs_approval_first(self):
        self.assertEqual(self._call("POST", f"/api/proposals/{self.pid}/dispatch")[0], 400)

    def test_bad_routes(self):
        self.assertEqual(self._call("POST", "/api/proposals/abc/approve")[0], 400)
        self.assertEqual(self._call("POST", "/api/proposals/999/approve")[0], 404)
        self.assertEqual(self._call("POST", f"/api/proposals/{self.pid}/nonsense")[0], 404)
        self.assertEqual(self._call("PATCH", "/api/proposals/abc", {})[0], 400)

    def test_sources_with_no_config_file_is_empty(self):
        self.assertEqual(self._call("GET", "/api/sources")[1], {"sources": []})


if __name__ == "__main__":
    unittest.main()
