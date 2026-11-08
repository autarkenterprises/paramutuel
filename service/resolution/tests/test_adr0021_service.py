"""ADR-0021 U5: the resolution service reads only its own wagers, and says when it could not read them all.

It paged through every OPEN wager on the permissionless factory, oldest first, and stopped silently
after 50 pages. Its own newest wagers were the first to fall past that cap, and drifted to `expire()`
(refunds) instead of paying their winners, with nothing in any response to say so.
"""
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock
from urllib import request

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


class FakeIndexer:
    """Serves `total` OPEN wagers through `/wagers` paging and records every URL."""

    def __init__(self, total: int) -> None:
        self.total = total
        self.urls: list[str] = []

    def __call__(self, url, timeout=20):
        self.urls.append(url)
        query = dict(part.split("=", 1) for part in url.split("?", 1)[1].split("&"))
        offset, limit = int(query["offset"]), int(query["limit"])
        count = max(0, min(limit, self.total - offset))
        return {"wagers": [{"wager_address": f"0x{offset + i:040x}"} for i in range(count)]}


class LoadOpenWagersTests(unittest.TestCase):
    def load(self, indexer, **kw):
        with mock.patch.object(svc, "_http_get_json", indexer):
            return svc._load_open_wagers("http://indexer", **kw)

    def test_the_query_is_scoped_to_this_resolver(self):
        indexer = FakeIndexer(3)
        self.load(indexer, limit=None, resolver=RESOLVER)
        self.assertTrue(all(f"resolver={RESOLVER}" in url for url in indexer.urls), indexer.urls)

    def test_no_resolver_means_no_filter(self):
        indexer = FakeIndexer(3)
        self.load(indexer, limit=None)
        self.assertNotIn("resolver=", indexer.urls[0])

    def test_running_out_of_wagers_is_not_truncation(self):
        indexer = FakeIndexer(3)
        rows, truncated = self.load(indexer, limit=None, resolver=RESOLVER)
        self.assertEqual(len(rows), 3)
        self.assertFalse(truncated)
        self.assertEqual(len(indexer.urls), 1)

    def test_hitting_the_page_cap_is_reported(self):
        indexer = FakeIndexer(7)
        with mock.patch.object(svc, "INDEXER_PAGE_SIZE", 3), mock.patch.object(svc, "MAX_INDEXER_PAGES", 2):
            rows, truncated = self.load(indexer, limit=None)
        self.assertEqual(len(rows), 6)
        self.assertTrue(truncated)

    def test_an_exact_fit_at_the_cap_is_not_truncation(self):
        """A full last page proves nothing; one more row is asked for to find out."""
        indexer = FakeIndexer(6)
        with mock.patch.object(svc, "INDEXER_PAGE_SIZE", 3), mock.patch.object(svc, "MAX_INDEXER_PAGES", 2):
            rows, truncated = self.load(indexer, limit=None)
        self.assertEqual(len(rows), 6)
        self.assertFalse(truncated)

    def test_an_explicit_limit_reports_wagers_beyond_it(self):
        rows, truncated = self.load(FakeIndexer(25), limit=20)
        self.assertEqual((len(rows), truncated), (20, True))
        rows, truncated = self.load(FakeIndexer(20), limit=20)
        self.assertEqual((len(rows), truncated), (20, False))


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.load = mock.Mock(return_value=([dict(OPEN_WAGER)], True))
        self._patches = [
            mock.patch.object(svc, "_load_open_wagers", self.load),
            mock.patch.object(svc, "_read_decisions", return_value={}),
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

    def call(self, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = request.Request(self.base + path, data=data, method="POST" if data else "GET", headers={"X-Token": "s3cret"})
        with request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())

    def test_candidates_are_scoped_and_report_truncation(self):
        body = self.call("/candidates")
        self.assertIs(body["truncated"], True)
        self.assertEqual(self.load.call_args.kwargs["resolver"], RESOLVER)

    def test_run_once_is_scoped_and_reports_truncation(self):
        body = self.call("/run-once", {"execute": False})
        self.assertIs(body["truncated"], True)
        self.assertEqual(self.load.call_args.kwargs["resolver"], RESOLVER)

    def test_a_complete_read_says_so(self):
        self.load.return_value = ([dict(OPEN_WAGER)], False)
        self.assertIs(self.call("/candidates")["truncated"], False)
        self.assertIs(self.call("/run-once", {"execute": False})["truncated"], False)


if __name__ == "__main__":
    unittest.main()
