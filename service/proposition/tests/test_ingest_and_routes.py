"""ADR-0020: the ingest driver and operator API routes had no tests at all (AGENTS.md #2)."""
import contextlib
import io
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

    def test_duplicates_from_every_source_type_are_not_proposed_twice(self):
        hn = json_sources.JsonItem(external_id="1", title="T", link="https://x", summary="", raw={})
        arr = json_sources.JsonItem("2", "U", "", "", {})
        sources = [{"id": "h", "type": "hackernews"}, {"id": "j", "type": "json_array", "url": "https://j"}, {"id": "r", "type": "rss", "url": "https://r"}]
        with mock.patch.object(json_sources, "fetch_hackernews_top", return_value=[hn]), \
                mock.patch.object(json_sources, "fetch_json_array", return_value=[arr]), \
                mock.patch.object(rss, "fetch_rss_items", return_value=[feed_item()]):
            self.assertEqual(self._run(sources)["new_proposals"], 3)
            self.assertEqual(self._run(sources)["new_proposals"], 0)

    def test_a_json_source_without_a_url_is_skipped(self):
        with mock.patch.object(json_sources, "fetch_json_array") as fetch:
            summary = self._run([{"id": "j", "type": "json_array"}])
        fetch.assert_not_called()
        self.assertEqual(summary["new_proposals"], 0)

    def test_ensure_db_creates_a_usable_schema(self):
        conn = ingest.ensure_db(os.path.join(self.tmp.name, "fresh.db"), SCHEMA)
        self.addCleanup(conn.close)
        self.assertEqual(dbm.list_proposals(conn), [])

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

    def _call(self, method, path, body=None, token="tok", raw=None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else (b"" if method != "GET" else None))
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

    def test_sources_returns_the_parsed_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sources.json"
            path.write_text(json.dumps({"sources": [{"id": "a", "type": "rss"}]}))
            server.Handler.sources_path = path
            self.assertEqual(self._call("GET", "/api/sources")[1], {"sources": [{"id": "a", "type": "rss"}]})

    def test_patch_rejects_bodies_that_are_not_json_objects(self):
        """These reset the connection, which the operator panel showed as a network failure (O11)."""
        for raw in (b"{nope", b"[1, 2]", b'"text"', b"\xff\xfe"):
            with self.subTest(raw=raw):
                code, body = self._call("PATCH", f"/api/proposals/{self.pid}", raw=raw)
                self.assertEqual(code, 400)
                self.assertIn("error", body)
        row = self._call("GET", "/api/proposals")[1]["proposals"][0]
        self.assertEqual(row["proposition"], "P?", "a rejected edit changes nothing")

    def test_ingest_route_reports_a_summary_and_can_add_calendar_drafts(self):
        code, body = self._call("POST", "/api/ingest")
        self.assertEqual((code, body["new_proposals"]), (200, 0))
        code, body = self._call("POST", "/api/ingest?calendar=1")
        self.assertEqual(code, 200)
        self.assertGreater(body["new_proposals"], 0)
        code, body = self._call("POST", "/api/ingest?calendar=1")
        self.assertEqual(body["new_proposals"], 0, "identical calendar drafts are skipped")
        self.assertGreater(body["calendar_skipped_duplicates"], 0)

    def test_dispatch_of_an_unknown_proposal_is_not_found(self):
        self.assertEqual(self._call("POST", "/api/proposals/999/dispatch")[0], 404)

    def test_dispatch_names_missing_configuration_rather_than_failing_on_chain(self):
        self._call("POST", f"/api/proposals/{self.pid}/approve")
        server.Handler.allow_execute = True
        self.addCleanup(setattr, server.Handler, "allow_execute", False)
        for attr in ("factory", "collateral", "rpc_url"):
            self.addCleanup(setattr, server.Handler, attr, getattr(server.Handler, attr))
            setattr(server.Handler, attr, "")
        code, body = self._call("POST", f"/api/proposals/{self.pid}/dispatch")
        self.assertEqual(code, 400)
        self.assertIn("missing", body["error"])

    def test_panel_assets_and_favicon_are_served_without_a_token(self):
        for path, ctype in (("/", "text/html"), ("/app.js", "application/javascript"), ("/style.css", "text/css")):
            with self.subTest(path=path), request.urlopen(self.base + path, timeout=10) as resp:
                self.assertEqual(resp.status, 200)
                self.assertIn(ctype, resp.headers["Content-Type"])
                self.assertGreater(len(resp.read()), 0)
        with request.urlopen(self.base + "/favicon.ico", timeout=10) as resp:
            self.assertEqual(resp.status, 204)

    def test_a_missing_asset_is_not_found(self):
        with mock.patch.object(server, "STATIC_DIR", Path("/nonexistent")):
            self.assertEqual(self._call("GET", "/", token=None)[0], 404)

    def test_unknown_routes_are_not_found(self):
        self.assertEqual(self._call("GET", "/nope")[0], 404)
        self.assertEqual(self._call("POST", "/nope")[0], 404)
        self.assertEqual(self._call("PATCH", "/nope")[0], 404)

    def test_cors_preflight_allows_the_token_header(self):
        req = request.Request(self.base + "/api/proposals", method="OPTIONS")
        with request.urlopen(req, timeout=10) as resp:
            self.assertEqual(resp.status, 204)
            self.assertIn("X-Proposition-Token", resp.headers["Access-Control-Allow-Headers"])


class DeploymentsLookupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "config").mkdir()
        self.path = self.root / "config" / "deployments.json"

    def test_uses_the_default_network(self):
        self.path.write_text(json.dumps({"defaultNetwork": "baseMainnet", "baseMainnet": {"factoryAddress": "0xmain"}, "baseSepolia": {"factoryAddress": "0xtest"}}))
        self.assertEqual(server._load_deployments_factory(self.root), "0xmain")

    def test_falls_back_to_sepolia_when_no_default_is_named(self):
        self.path.write_text(json.dumps({"baseSepolia": {"factoryAddress": "0xtest"}}))
        self.assertEqual(server._load_deployments_factory(self.root), "0xtest")

    def test_missing_or_broken_config_is_empty(self):
        self.assertEqual(server._load_deployments_factory(self.root), "")
        self.path.write_text("{nope")
        self.assertEqual(server._load_deployments_factory(self.root), "")


class StartupTests(unittest.TestCase):
    """`main` decides whether this process may send transactions, so its precedence rules matter."""

    class FakeServer:
        def __init__(self, address, handler):
            self.address = address

        def serve_forever(self):
            pass

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        saved = {k: v for k, v in vars(server.Handler).items() if not k.startswith("__") and not callable(v)}
        self.addCleanup(lambda: [setattr(server.Handler, k, v) for k, v in saved.items()])

    def _main(self, *argv, env=None):
        full_env = {"PROPOSITION_DB_PATH": os.path.join(self.tmp.name, "p.db"), **(env or {})}
        with (
            mock.patch.dict(os.environ, full_env, clear=True),
            mock.patch("sys.argv", ["server", *argv]),
            mock.patch.object(server, "ThreadingHTTPServer", self.FakeServer),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            server.main()

    def test_a_panel_token_is_mandatory(self):
        with self.assertRaisesRegex(SystemExit, "PROPOSITION_PANEL_TOKEN"):
            self._main()

    def test_execution_is_off_unless_asked_for(self):
        self._main(env={"PROPOSITION_PANEL_TOKEN": "t"})
        self.assertIs(server.Handler.allow_execute, False)

    def test_environment_can_enable_execution_and_flags_override_it(self):
        self._main(env={"PROPOSITION_PANEL_TOKEN": "t", "PROPOSITION_ALLOW_EXECUTE": "true"})
        self.assertIs(server.Handler.allow_execute, True)
        self._main("--no-allow-execute", env={"PROPOSITION_PANEL_TOKEN": "t", "PROPOSITION_ALLOW_EXECUTE": "1"})
        self.assertIs(server.Handler.allow_execute, False)
        self._main("--allow-execute", env={"PROPOSITION_PANEL_TOKEN": "t"})
        self.assertIs(server.Handler.allow_execute, True)

    def test_settings_reach_the_handler(self):
        env = {
            "PROPOSITION_PANEL_TOKEN": " t ",
            "PROPOSITION_COLLATERAL_TOKEN": "0xcoll",
            "FACTORY_ADDRESS": "0xfact",
            "RPC_URL": "http://r",
            "PRIVATE_KEY": "0xkey",
            "PROPOSITION_BETTING_CLOSE_OFFSET_SEC": "1",
            "PROPOSITION_RESOLUTION_WINDOW_SEC": "7200",
            "PROPOSITION_EXTRA_FEE_RECIPIENTS": "0xa, 0xb",
            "PROPOSITION_EXTRA_FEE_BPS": "1, 2",
        }
        self._main(env=env)
        H = server.Handler
        self.assertEqual((H.auth_token, H.collateral, H.factory, H.rpc_url, H.private_key), ("t", "0xcoll", "0xfact", "http://r", "0xkey"))
        self.assertEqual(H.betting_close_offset, 60, "offsets floor at one minute")
        self.assertEqual(H.resolution_window, 7200)
        self.assertEqual((H.extra_recipients, H.extra_bps), (["0xa", "0xb"], [1, 2]))

    def test_misaligned_extra_fee_lists_stop_startup(self):
        """A misaligned pair would otherwise fail every dispatch, or pay the wrong recipient."""
        env = {"PROPOSITION_PANEL_TOKEN": "t", "PROPOSITION_EXTRA_FEE_RECIPIENTS": "0xa,0xb", "PROPOSITION_EXTRA_FEE_BPS": "1"}
        with self.assertRaisesRegex(SystemExit, "mismatch"):
            self._main(env=env)


if __name__ == "__main__":
    unittest.main()
