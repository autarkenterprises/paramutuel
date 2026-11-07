"""ADR-0020: the explorer's indexer proxy must pass upstream status codes through."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import error, request

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


if __name__ == "__main__":
    unittest.main()
