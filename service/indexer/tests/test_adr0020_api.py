"""ADR-0020 API regressions, exercised over real HTTP."""
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib import request
from urllib.error import HTTPError

from service.indexer.api import Handler
from service.indexer.indexer import db_connect, init_db, set_meta_int, set_meta_str

ENUM = "0x" + "11" * 20
FREE = "0x" + "22" * 20


class ApiTests(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = db_connect(self.db_path)
        init_db(self.conn)
        for addr, version, outcomes in ((ENUM, "enumerated", '["A","B","C"]'), (FREE, "freeform", "[]")):
            self.conn.execute(
                """INSERT INTO wagers(wager_address, factory_address, proposer, resolver, betting_closer,
                   resolution_closer, collateral_token, outcomes_json, protocol_version, payoff_policy,
                   betting_close_time, resolution_window, resolution_deadline, state, created_block,
                   created_tx_hash)
                   VALUES (?, 'f', 'p', 'r', 'b', 'c', 't', ?, ?, 1, 0, 0, 0, 'OPEN', 1, 'x')""",
                (addr, outcomes, version),
            )
            self.conn.execute("INSERT INTO wager_totals(wager_address) VALUES (?)", (addr,))
        self.conn.commit()
        Handler.conn = self.conn
        Handler.indexer_factory_address = None
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.conn.close()
        os.remove(self.db_path)

    def _get(self, path):
        with request.urlopen(self.base + path, timeout=10) as resp:
            return json.loads(resp.read().decode())

    def _pool(self, wager, key, total):
        self.conn.execute(
            "INSERT INTO wager_ticket_pools(wager_address, ticket_mask, pool_total) VALUES (?, ?, ?)",
            (wager, key, str(total)),
        )

    def _event(self, wager, i, name="BetPlacedV3Enumerated", payload=None):
        self.conn.execute(
            """INSERT INTO events_log(event_id, wager_address, event_name, block_number, tx_hash, log_index, payload_json)
               VALUES (?, ?, ?, ?, 'tx', ?, ?)""",
            (f"{wager}:{i}", wager, name, i, i, json.dumps(payload or {})),
        )

    # X1: every enumerated wager used to say "No stakes yet", because this list was always empty.
    def test_outcomes_are_derived_from_single_and_multi_bit_ticket_pools(self):
        self._pool(ENUM, "1", 100)  # {A}
        self._pool(ENUM, "2", 200)  # {B}
        self._pool(ENUM, "3", 50)  # {A,B}
        self.conn.commit()
        body = self._get(f"/wagers/{ENUM}")
        self.assertEqual(
            body["outcomes"],
            [
                {"outcome_index": 0, "outcome_total": "150"},
                {"outcome_index": 1, "outcome_total": "250"},
                {"outcome_index": 2, "outcome_total": "0"},
            ],
        )

    def test_outcome_totals_are_exact_above_2_53(self):
        self._pool(ENUM, "1", 2**200)
        self.conn.commit()
        self.assertEqual(self._get(f"/wagers/{ENUM}")["outcomes"][0]["outcome_total"], str(2**200))

    def test_freeform_has_no_outcome_rows(self):
        self.assertEqual(self._get(f"/wagers/{FREE}")["outcomes"], [])

    def test_enumerated_pools_sort_numerically_and_never_truncate(self):
        for mask in (10, 9, 100):
            self._pool(ENUM, str(mask), 1)
        self.conn.commit()
        rows = self._get(f"/wagers/{ENUM}?pool_limit=1")["ticket_pools"]
        self.assertEqual([r["ticket_mask"] for r in rows], ["9", "10", "100"])

    # C5: bettors must be able to see and join what has been staked on.
    def test_freeform_pools_carry_answer_text_and_sort_by_stake(self):
        self._pool(FREE, "0x" + "aa" * 32, 5)
        self._pool(FREE, "0x" + "bb" * 32, 50)
        self._pool(FREE, "0x" + "cc" * 32, 20)
        self.conn.execute(
            "INSERT INTO wager_answers(wager_address, answer_id, answer_text, answer_hex) VALUES (?, ?, 'Paris', '0x5061726973')",
            (FREE, "0x" + "bb" * 32),
        )
        self.conn.commit()
        rows = self._get(f"/wagers/{FREE}")["ticket_pools"]
        self.assertEqual([r["pool_total"] for r in rows], ["50", "20", "5"])
        self.assertEqual(rows[0]["answer_text"], "Paris")
        self.assertEqual(rows[0]["answer_hex"], "0x5061726973")
        self.assertIsNone(rows[1]["answer_text"])

    # X7: answer lists are unbounded on-chain now, so the response must not be.
    def test_freeform_pools_truncate_but_report_the_total(self):
        for i in range(12):
            self._pool(FREE, f"0x{i:064x}", i + 1)
        self.conn.commit()
        body = self._get(f"/wagers/{FREE}?pool_limit=5")
        self.assertEqual(len(body["ticket_pools"]), 5)
        self.assertEqual(body["ticket_pools_total"], 12)
        self.assertEqual(body["ticket_pools"][0]["pool_total"], "12", "largest stakes kept")

    def test_single_answer_lookup_works_past_the_limit(self):
        for i in range(12):
            self._pool(FREE, f"0x{i:064x}", i + 1)
        self.conn.commit()
        wanted = f"0x{0:064x}"
        body = self._get(f"/wagers/{FREE}?pool_limit=2&answer_id={wanted.upper().replace('0X', '0x')}")
        self.assertEqual([r["ticket_mask"] for r in body["ticket_pools"]], [wanted])

    def test_events_return_newest_window_in_order_with_total(self):
        for i in range(10):
            self._event(ENUM, i)
        self.conn.commit()
        body = self._get(f"/wagers/{ENUM}?events_limit=3")
        self.assertEqual([e["block_number"] for e in body["events"]], [7, 8, 9])
        self.assertEqual(body["events_total"], 10)

    def test_event_amounts_are_strings_so_js_cannot_round_them(self):
        self._event(ENUM, 1, payload={"bettor": "0xb", "ticketMask": 2**200, "amount": 2**100})
        self.conn.commit()
        payload = self._get(f"/wagers/{ENUM}")["events"][0]["payload_json"]
        self.assertEqual(payload["amount"], str(2**100))
        self.assertEqual(payload["ticketMask"], str(2**200))
        self.assertEqual(payload["bettor"], "0xb")

    # X7: malformed input and internal errors answer with JSON rather than resetting the connection.
    def _status(self, path):
        try:
            with request.urlopen(self.base + path, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode())
        except HTTPError as exc:
            return exc.code, json.loads(exc.read().decode())

    def test_bad_now_is_400(self):
        status, body = self._status("/sweeper/expire-candidates?now=abc")
        self.assertEqual(status, 400)
        self.assertIn("now", body["error"])

    def test_bad_limits_are_400(self):
        self.assertEqual(self._status(f"/wagers/{ENUM}?pool_limit=x")[0], 400)
        self.assertEqual(self._status(f"/wagers/{ENUM}?events_limit=x")[0], 400)

    def test_internal_error_is_json_500(self):
        original = Handler.conn

        class Broken:
            def execute(self, *a, **k):
                raise RuntimeError("database is locked")

        Handler.conn = Broken()
        try:
            status, body = self._status("/health")
        finally:
            Handler.conn = original
        self.assertEqual(status, 500)
        self.assertEqual(body["error"], "internal error")

    # X7: operators need to see lag and lost logs without reading server output.
    def test_health_reports_lag_and_skipped_logs(self):
        set_meta_int(self.conn, "chain_head", 1000)
        set_meta_int(self.conn, "last_indexed_block", 990)
        set_meta_int(self.conn, "skipped_log_count", 2)
        set_meta_str(self.conn, "last_skipped_log", "0xabc:1: bad data")
        self.conn.commit()
        body = self._get("/health")
        self.assertEqual(body["sync_lag_blocks"], 10)
        self.assertEqual(body["skipped_log_count"], 2)
        self.assertEqual(body["last_skipped_log"], "0xabc:1: bad data")

    def test_health_lag_is_null_before_first_sync(self):
        self.assertIsNone(self._get("/health")["sync_lag_blocks"])
        self.assertEqual(self._get("/health")["skipped_log_count"], 0)


if __name__ == "__main__":
    unittest.main()
