import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib import request

from service.indexer.api import Handler
from service.indexer.indexer import db_connect, init_db


class ApiRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = db_connect(self.db_path)
        init_db(self.conn)
        Handler.conn = self.conn

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _get_json(self, path: str) -> tuple[int, dict]:
        with request.urlopen(self.base_url + path, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return resp.status, body

    def test_root_returns_service_metadata(self) -> None:
        status, body = self._get_json("/")
        self.assertEqual(status, 200)
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("service"), "paramutuel-indexer-api")
        self.assertIn("/markets?limit=100", body.get("endpoints", []))

    def test_prefixed_and_unprefixed_market_routes_match(self) -> None:
        status1, body1 = self._get_json("/markets?limit=1")
        status2, body2 = self._get_json("/api/markets?limit=1")
        self.assertEqual(status1, 200)
        self.assertEqual(status2, 200)
        self.assertEqual(body1, body2)
        self.assertIn("markets", body1)

    def test_prefixed_health_route_works(self) -> None:
        status, body = self._get_json("/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(body.get("ok"))


if __name__ == "__main__":
    unittest.main()
