"""ADR-0020: the explorer's indexer proxy must pass upstream status codes through."""
import contextlib
import io
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock
from urllib import error, request

from service.explorer import server as server_module
from service.explorer.server import Handler


class FakeIndexer(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        code = 404 if "missing" in self.path else 200
        body = json.dumps({"path": self.path}).encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ProxyTests(unittest.TestCase):
    def setUp(self):
        self.upstream = ThreadingHTTPServer(("127.0.0.1", 0), FakeIndexer)
        threading.Thread(target=self.upstream.serve_forever, daemon=True).start()
        Handler.indexer_base_url = f"http://127.0.0.1:{self.upstream.server_address[1]}"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.upstream.shutdown()
        self.upstream.server_close()

    def _get(self, path):
        try:
            with request.urlopen(self.base + path, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode())
        except error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode())

    def test_forwards_path_and_query(self):
        code, body = self._get("/api/wagers?limit=5")
        self.assertEqual(code, 200)
        self.assertEqual(body["path"], "/wagers?limit=5")

    def test_not_found_stays_not_found(self):
        """A missing wager was reported as 502, indistinguishable from the indexer being down."""
        code, _ = self._get("/api/wagers/missing")
        self.assertEqual(code, 404)

    def test_unreachable_indexer_is_502(self):
        Handler.indexer_base_url = "http://127.0.0.1:9"
        code, body = self._get("/api/wagers")
        self.assertEqual(code, 502)
        self.assertIn("indexer", body["error"])


class StaticRouteTests(ProxyTests):
    def _static(self, path):
        try:
            with request.urlopen(self.base + path, timeout=10) as resp:
                return resp.status, resp.headers["Content-Type"], resp.read()
        except error.HTTPError as exc:
            return exc.code, exc.headers["Content-Type"], exc.read()

    def test_assets_are_served_with_their_types(self):
        for path, ctype in (("/", "text/html"), ("/app.js", "application/javascript"), ("/style.css", "text/css")):
            with self.subTest(path=path):
                code, got, body = self._static(path)
                self.assertEqual((code, got), (200, ctype))
                self.assertGreater(len(body), 0)

    def test_health(self):
        code, _, body = self._static("/health")
        self.assertEqual((code, json.loads(body)), (200, {"ok": True}))

    def test_unknown_routes_and_missing_assets_are_not_found(self):
        self.assertEqual(self._static("/nope")[0], 404)
        with mock.patch.object(server_module, "STATIC_DIR", server_module.Path("/nonexistent")):
            self.assertEqual(self._static("/")[0], 404)


class StartupTests(unittest.TestCase):
    def test_main_points_the_proxy_at_the_configured_indexer(self):
        served = []

        class FakeServer:
            def __init__(self, address, handler):
                self.address = address

            def serve_forever(self):
                served.append(self.address)

        saved = Handler.indexer_base_url
        self.addCleanup(setattr, Handler, "indexer_base_url", saved)
        argv = ["server", "--port", "9", "--indexer-base-url", "http://indexer.example"]
        with mock.patch("sys.argv", argv), mock.patch.object(server_module, "ThreadingHTTPServer", FakeServer), contextlib.redirect_stdout(io.StringIO()):
            server_module.main()
        self.assertEqual(Handler.indexer_base_url, "http://indexer.example")
        self.assertEqual(served, [("127.0.0.1", 9)])


if __name__ == "__main__":
    unittest.main()
