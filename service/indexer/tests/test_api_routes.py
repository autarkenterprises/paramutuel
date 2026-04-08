import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
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
        Handler.indexer_factory_address = None
        Handler.indexer_factory_v2_address = None
        Handler.indexer_factory_freeform_address = None

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self._seed_wagers()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.conn.close()
        Handler.indexer_factory_address = None
        Handler.indexer_factory_v2_address = None
        Handler.indexer_factory_freeform_address = None
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _get_json(self, path: str) -> tuple[int, dict]:
        with request.urlopen(self.base_url + path, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return resp.status, body

    def _insert_wager(
        self,
        wager: str,
        proposition: str,
        outcomes: list[str],
        created_block: int,
        created_tx_hash: str,
        proposer: str,
        collateral_token: str,
        total_pot: str = "0",
        *,
        protocol_version: str = "v1",
        payoff_policy: int | None = None,
        policy_param: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO wagers(
              wager_address, factory_address, proposer, resolver, betting_closer, resolution_closer,
              collateral_token, proposition, outcomes_json,
              protocol_version, payoff_policy, policy_param,
              betting_close_time, resolution_window, resolution_deadline,
              betting_closed_by_authority, resolution_window_closed, state, created_block, created_tx_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?)
            """,
            (
                wager,
                "0xfac7000000000000000000000000000000000001",
                proposer,
                "0xabc3000000000000000000000000000000000003",
                "0xabc4000000000000000000000000000000000004",
                "0xabc5000000000000000000000000000000000005",
                collateral_token,
                proposition,
                json.dumps(outcomes),
                protocol_version,
                payoff_policy,
                policy_param,
                1000,
                3600,
                4600,
                0,
                0,
                created_block,
                created_tx_hash,
            ),
        )
        self.conn.execute(
            "INSERT OR IGNORE INTO wager_totals(wager_address, total_pot, total_fee_bps) VALUES (?, ?, '0')",
            (wager, total_pot),
        )

    def _seed_wagers(self) -> None:
        self._insert_wager(
            wager="0xabc1000000000000000000000000000000000001",
            proposition="Will Team A win?",
            outcomes=["YES", "NO"],
            created_block=1,
            created_tx_hash="0xaaa",
            proposer="0xabc2000000000000000000000000000000000002",
            collateral_token="0xabc6000000000000000000000000000000000006",
            total_pot="12345",
        )
        self._insert_wager(
            wager="0xabc1000000000000000000000000000000000002",
            proposition="Will Team B launch?",
            outcomes=["UP", "DOWN"],
            created_block=2,
            created_tx_hash="0xaab",
            proposer="0xabc2000000000000000000000000000000000007",
            collateral_token="0xabc6000000000000000000000000000000000008",
            total_pot="0",
        )
        self._insert_wager(
            wager="0xabc1000000000000000000000000000000000003",
            proposition="Will Team C ship?",
            outcomes=["GREEN", "RED"],
            created_block=3,
            created_tx_hash="0xaac",
            proposer="0xabc2000000000000000000000000000000000009",
            collateral_token="0xabc6000000000000000000000000000000000010",
            total_pot="42",
        )
        self.conn.commit()

    def test_get_wager_includes_ticket_pools(self) -> None:
        status, body = self._get_json("/wagers/0xabc1000000000000000000000000000000000001")
        self.assertEqual(status, 200)
        self.assertIn("ticket_pools", body)
        self.assertEqual(body["ticket_pools"], [])

    def test_get_wager_v2_exposes_ticket_pools_rows(self) -> None:
        waddr = "0xabc10000000000000000000000000000000000aa"
        self._insert_wager(
            wager=waddr,
            proposition="V2 bitmask pool test",
            outcomes=["A", "B"],
            created_block=9,
            created_tx_hash="0xaaf",
            proposer="0xabc2000000000000000000000000000000000002",
            collateral_token="0xabc6000000000000000000000000000000000006",
            protocol_version="v2",
            payoff_policy=0,
            policy_param="0",
        )
        self.conn.execute(
            "INSERT INTO wager_ticket_pools(wager_address, ticket_mask, pool_total) VALUES (?, ?, ?)",
            (waddr.lower(), "2", "777"),
        )
        self.conn.commit()
        status, body = self._get_json(f"/wagers/{waddr}")
        self.assertEqual(status, 200)
        self.assertEqual(body["wager"]["protocol_version"], "v2")
        pools = {p["ticket_mask"]: p["pool_total"] for p in body["ticket_pools"]}
        self.assertEqual(pools.get("2"), "777")

    def test_wagers_search_includes_protocol_version_field(self) -> None:
        self._insert_wager(
            wager="0xabc10000000000000000000000000000000000bb",
            proposition="Alpha only",
            outcomes=["X", "Y"],
            created_block=8,
            created_tx_hash="0xaae",
            proposer="0xabc20000000000000000000000000000000000bb",
            collateral_token="0xabc6000000000000000000000000000000000006",
            protocol_version="v2",
        )
        self.conn.commit()
        status, body = self._get_json("/wagers?q=v2")
        self.assertEqual(status, 200)
        addrs = {m["wager_address"] for m in body["wagers"]}
        self.assertIn("0xabc10000000000000000000000000000000000bb", addrs)

    def test_health_echoes_configured_factories(self) -> None:
        Handler.indexer_factory_address = "0xfac7000000000000000000000000000000000001"
        Handler.indexer_factory_v2_address = "0xfac7000000000000000000000000000000000002"
        status, body = self._get_json("/health")
        self.assertEqual(status, 200)
        self.assertEqual(body.get("factory_address"), Handler.indexer_factory_address)
        self.assertEqual(body.get("factory_v2_address"), Handler.indexer_factory_v2_address)
        self.assertIsNone(body.get("factory_freeform_address"))

    def test_health_echoes_freeform_factory_when_set(self) -> None:
        Handler.indexer_factory_freeform_address = "0xfac7000000000000000000000000000000000003"
        status, body = self._get_json("/health")
        self.assertEqual(status, 200)
        self.assertEqual(body.get("factory_freeform_address"), Handler.indexer_factory_freeform_address)

    def test_root_returns_service_metadata(self) -> None:
        status, body = self._get_json("/")
        self.assertEqual(status, 200)
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("service"), "paramutuel-indexer-api")
        self.assertIn("/wagers?limit=20&offset=0&order=desc", body.get("endpoints", []))

    def test_prefixed_and_unprefixed_wager_routes_match(self) -> None:
        status1, body1 = self._get_json("/wagers?limit=1")
        status2, body2 = self._get_json("/api/wagers?limit=1")
        self.assertEqual(status1, 200)
        self.assertEqual(status2, 200)
        self.assertEqual(body1, body2)
        self.assertIn("wagers", body1)

    def test_legacy_market_routes_are_rejected(self) -> None:
        """Regression: pre-wager "/markets" paths must stay gone (404).

        If these ever return 200 again, a deprecated API surface has been reintroduced
        and this test should fail until the routes are removed or intentionally versioned.
        """
        with self.assertRaises(HTTPError):
            self._get_json("/markets?limit=1")
        with self.assertRaises(HTTPError):
            self._get_json("/api/markets?limit=1")

    def test_wagers_search_filters_on_proposition_text(self) -> None:
        status, body = self._get_json("/wagers?q=team%20a")
        self.assertEqual(status, 200)
        self.assertEqual(len(body["wagers"]), 1)
        self.assertEqual(body["wagers"][0]["proposition"], "Will Team A win?")

    def test_prefixed_wagers_search_filters_on_outcomes(self) -> None:
        status, body = self._get_json("/api/wagers?q=yes")
        self.assertEqual(status, 200)
        self.assertEqual(len(body["wagers"]), 1)
        self.assertIn("YES", body["wagers"][0]["outcomes_json"])

    def test_wagers_search_filters_on_role_and_total_fields(self) -> None:
        status, body = self._get_json("/wagers?q=abc2000000000000000000000000000000000007")
        self.assertEqual(status, 200)
        self.assertEqual(len(body["wagers"]), 1)
        self.assertEqual(body["wagers"][0]["wager_address"], "0xabc1000000000000000000000000000000000002")

        status2, body2 = self._get_json("/wagers?q=12345")
        self.assertEqual(status2, 200)
        self.assertEqual(len(body2["wagers"]), 1)
        self.assertEqual(body2["wagers"][0]["wager_address"], "0xabc1000000000000000000000000000000000001")

    def test_wagers_default_order_is_most_recent_first(self) -> None:
        status, body = self._get_json("/wagers?limit=3")
        self.assertEqual(status, 200)
        addresses = [m["wager_address"] for m in body["wagers"]]
        self.assertEqual(
            addresses,
            [
                "0xabc1000000000000000000000000000000000003",
                "0xabc1000000000000000000000000000000000002",
                "0xabc1000000000000000000000000000000000001",
            ],
        )

    def test_wagers_oldest_first_order(self) -> None:
        status, body = self._get_json("/wagers?limit=3&order=asc")
        self.assertEqual(status, 200)
        addresses = [m["wager_address"] for m in body["wagers"]]
        self.assertEqual(
            addresses,
            [
                "0xabc1000000000000000000000000000000000001",
                "0xabc1000000000000000000000000000000000002",
                "0xabc1000000000000000000000000000000000003",
            ],
        )

    def test_wagers_offset_pagination(self) -> None:
        status, body = self._get_json("/wagers?limit=1&offset=1&order=desc")
        self.assertEqual(status, 200)
        self.assertEqual(len(body["wagers"]), 1)
        self.assertEqual(body["wagers"][0]["wager_address"], "0xabc1000000000000000000000000000000000002")

    def test_wagers_invalid_order_or_offset_rejected(self) -> None:
        with self.assertRaises(HTTPError):
            self._get_json("/wagers?order=latest")
        with self.assertRaises(HTTPError):
            self._get_json("/wagers?offset=nan")

    def test_prefixed_health_route_works(self) -> None:
        status, body = self._get_json("/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(body.get("ok"))
        self.assertIn("wager_count", body)
        self.assertIn("last_indexed_block", body)
        self.assertIn("chain_head", body)
        self.assertIn("last_sync_error", body)
        self.assertIn("factory_address", body)
        self.assertIn("factory_v2_address", body)
        self.assertIn("factory_freeform_address", body)


if __name__ == "__main__":
    unittest.main()
