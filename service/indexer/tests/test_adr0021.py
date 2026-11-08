"""ADR-0021 indexer regressions: findings U2-U5 of the independent review of ADR-0020.

U2  metadata retries back off, and a row that keeps failing cannot starve newer ones.
U3  `total_winning_stake` is a stake; the contract's weighted denominator has its own column.
U4  a chunk with no wager creations costs one `eth_getLogs`, not two.
U5  `/wagers` can be scoped to one resolver, so a resolver's own wagers never fall past a page cap.
"""
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock
from urllib import request
from urllib.error import HTTPError

from service.indexer import api as api_module
from service.indexer import indexer as ix
from service.indexer.indexer import TOPICS, apply_log, init_db

FACTORY = "0xfac7000000000000000000000000000000000004"
WAGER = "0xabc1000000000000000000000000000000000001"
WAGER2 = "0xabc1000000000000000000000000000000000002"
PROPOSER = "0xabc2000000000000000000000000000000000002"
RESOLVER = "0xabc3000000000000000000000000000000000003"
OTHER_RESOLVER = "0xabc3000000000000000000000000000000000009"
TOKEN = "0xabc4000000000000000000000000000000000004"
BETTOR = "0xabc5000000000000000000000000000000000005"
ANSWER_ID = "0x" + "ab" * 32


def topic_addr(addr: str) -> str:
    return "0x" + ("0" * 24) + addr.lower().replace("0x", "")


def word(v: int) -> str:
    return f"{v:064x}"


def word_addr(addr: str) -> str:
    return ("0" * 24) + addr.lower().replace("0x", "")


class Chain:
    """Builds raw logs; every log gets its own block and transaction."""

    def __init__(self) -> None:
        self.n = 0

    def _meta(self) -> dict:
        self.n += 1
        return {"blockNumber": hex(10 + self.n), "transactionHash": f"0x{self.n:064x}", "logIndex": "0x0"}

    def created_enum(self, wager=WAGER, policy=0, param=0) -> dict:
        data = (
            "0x" + word_addr(TOKEN) + word(policy) + word(param) + word(2_000) + word(3_000) + word(5_000)
            + word_addr(RESOLVER) + word_addr(RESOLVER)
        )
        return {
            "address": FACTORY,
            "topics": [TOPICS["WagerCreatedV3Enumerated"], topic_addr(wager), topic_addr(PROPOSER), topic_addr(RESOLVER)],
            "data": data,
            **self._meta(),
        }

    def created_free(self, wager=WAGER) -> dict:
        data = "0x" + word_addr(TOKEN) + word(2_000) + word(3_000) + word(5_000) + word_addr(RESOLVER) + word_addr(RESOLVER)
        return {
            "address": FACTORY,
            "topics": [TOPICS["WagerCreatedV3Freeform"], topic_addr(wager), topic_addr(PROPOSER), topic_addr(RESOLVER)],
            "data": data,
            **self._meta(),
        }

    def bet_enum(self, mask, amount, wager=WAGER) -> dict:
        return {
            "address": wager,
            "topics": [TOPICS["BetPlacedV3Enumerated"], topic_addr(BETTOR)],
            "data": "0x" + word(mask) + word(amount),
            **self._meta(),
        }

    def bet_free(self, answer_id, amount) -> dict:
        return {
            "address": WAGER,
            "topics": [TOPICS["BetPlacedV3Freeform"], topic_addr(BETTOR), answer_id],
            "data": "0x" + word(amount),
            **self._meta(),
        }

    def resolved_enum(self, mask) -> dict:
        return {"address": WAGER, "topics": [TOPICS["ResolvedV3Enumerated"]], "data": "0x" + word(mask), **self._meta()}

    def resolved_free(self, answer_id) -> dict:
        return {"address": WAGER, "topics": [TOPICS["ResolvedV3Freeform"], answer_id], "data": "0x", **self._meta()}


class Db(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)
        self.chain = Chain()

    def tearDown(self) -> None:
        self.conn.close()

    def apply(self, *logs) -> None:
        for log in logs:
            apply_log(self.conn, FACTORY, log, rpc_url=None)
        self.conn.commit()

    def totals(self, wager=WAGER):
        return self.conn.execute("SELECT * FROM wager_totals WHERE wager_address = ?", (wager,)).fetchone()


# ---------------------------------------------------------------- U3: stake vs payout denominator


class WinningStakeTests(Db):
    def resolve_weighted(self) -> None:
        c = self.chain
        self.apply(c.created_enum(policy=4), c.bet_enum(0b01, 100), c.bet_enum(0b11, 40), c.bet_enum(0b10, 7))
        self.apply(c.resolved_enum(0b11))

    def test_weighted_overlap_keeps_the_stake_and_the_denominator_apart(self):
        """The site printed 'Winning stake 187' for 147 tokens staked: the weighted units, as tokens."""
        self.resolve_weighted()
        self.assertEqual(self.totals()["total_winning_stake"], str(100 + 40 + 7))
        self.assertEqual(self.totals()["payout_denominator"], str(100 * 1 + 40 * 2 + 7 * 1))

    def test_every_other_policy_has_one_value_for_both(self):
        for policy, param, mask in ((0, 0, 0b01), (1, 0, 0b01), (2, 0, 0b11), (3, 2, 0b11)):
            with self.subTest(policy=policy):
                self.setUp()
                c = self.chain
                self.apply(c.created_enum(policy=policy, param=param), c.bet_enum(0b01, 100), c.bet_enum(0b11, 40))
                self.apply(c.resolved_enum(mask))
                row = self.totals()
                self.assertEqual(row["total_winning_stake"], row["payout_denominator"])
                self.assertEqual(
                    int(row["payout_denominator"]),
                    ix.compute_winning_units(policy, param, mask, {0b01: 100, 0b11: 40}),
                )

    def test_freeform_denominator_is_the_winning_pool(self):
        c = self.chain
        self.apply(c.created_free(), c.bet_free(ANSWER_ID, 5), c.bet_free(ANSWER_ID, 6), c.resolved_free(ANSWER_ID))
        self.assertEqual(self.totals()["total_winning_stake"], "11")
        self.assertEqual(self.totals()["payout_denominator"], "11")

    def test_the_api_serves_both_in_the_list_and_the_detail(self):
        self.resolve_weighted()
        listed = api_module.list_wagers(self.conn, None, 10, None, "desc", 0)[0]
        self.assertEqual((listed["total_winning_stake"], listed["payout_denominator"]), ("147", "187"))
        detail = api_module.get_wager(self.conn, WAGER)["totals"]
        self.assertEqual((detail["total_winning_stake"], detail["payout_denominator"]), ("147", "187"))

    def test_an_existing_database_is_recomputed_when_the_column_arrives(self):
        """A database written before ADR-0021 holds the weighted units in total_winning_stake."""
        self.resolve_weighted()
        self.conn.execute("ALTER TABLE wager_totals DROP COLUMN payout_denominator")
        self.conn.execute("UPDATE wager_totals SET total_winning_stake = '187'")
        self.conn.commit()
        init_db(self.conn)
        self.assertEqual(self.totals()["total_winning_stake"], "147")
        self.assertEqual(self.totals()["payout_denominator"], "187")

    def test_the_migration_copies_a_freeform_winning_pool(self):
        """A freeform denominator is its winning pool, which total_winning_stake already held."""
        c = self.chain
        self.apply(c.created_free(), c.bet_free(ANSWER_ID, 5), c.bet_free(ANSWER_ID, 6), c.resolved_free(ANSWER_ID))
        self.conn.execute("ALTER TABLE wager_totals DROP COLUMN payout_denominator")
        self.conn.commit()
        init_db(self.conn)
        self.assertEqual((self.totals()["total_winning_stake"], self.totals()["payout_denominator"]), ("11", "11"))

    def test_the_migration_runs_once(self):
        """After the column exists, init_db (run on every boot) leaves the values alone."""
        self.resolve_weighted()
        self.conn.execute("UPDATE wager_totals SET payout_denominator = 'sentinel'")
        self.conn.commit()
        init_db(self.conn)
        self.assertEqual(self.totals()["payout_denominator"], "sentinel")


# ---------------------------------------------------------------- U2: metadata retry backoff


def metadata(complete: bool) -> dict:
    return {
        "proposition": "Will it rain?" if complete else "",
        "outcomes": ["Yes", "No"] if complete else [],
        "total_fee_bps": 250 if complete else None,
        "min_new_ticket_stake": 0,
        "complete": complete,
    }


class BackfillBackoffTests(Db):
    def insert_incomplete(self, address: str, created_block: int) -> None:
        self.conn.execute(
            """INSERT INTO wagers(wager_address, factory_address, proposer, resolver, betting_closer,
               resolution_closer, collateral_token, betting_close_time, resolution_window,
               resolution_deadline, state, created_block, created_tx_hash, metadata_complete)
               VALUES (?, ?, 'p', 'r', 'b', 'c', 't', 0, 0, 0, 'OPEN', ?, 'x', 0)""",
            (address, FACTORY, created_block),
        )
        self.conn.execute("INSERT INTO wager_totals(wager_address) VALUES (?)", (address,))
        self.conn.commit()

    def row(self, address: str):
        return self.conn.execute("SELECT * FROM wagers WHERE wager_address = ?", (address,)).fetchone()

    def backfill(self, now: int, ok=lambda address: False, limit=25):
        fetch = mock.Mock(side_effect=lambda rpc, address: metadata(ok(address)))
        with mock.patch.object(ix, "fetch_wager_metadata", fetch):
            repaired = ix.backfill_incomplete_metadata(self.conn, "http://rpc", limit=limit, now=now)
        return repaired, [call.args[1] for call in fetch.call_args_list]

    def test_a_failing_row_waits_longer_after_each_failure(self):
        self.insert_incomplete(WAGER, 1)
        self.assertEqual(self.backfill(1_000)[1], [WAGER])
        self.assertEqual((self.row(WAGER)["metadata_attempts"], self.row(WAGER)["metadata_retry_at"]), (1, 1_015))
        self.assertEqual(self.backfill(1_014)[1], [], "not retried before its time")
        self.assertEqual(self.backfill(1_015)[1], [WAGER])
        self.assertEqual((self.row(WAGER)["metadata_attempts"], self.row(WAGER)["metadata_retry_at"]), (2, 1_045))

    def test_the_wait_is_capped_at_an_hour_and_never_abandoned(self):
        """An RPC outage of any length ends; a row dropped for good would blank the wager forever."""
        self.insert_incomplete(WAGER, 1)
        self.conn.execute("UPDATE wagers SET metadata_attempts = 40")
        self.backfill(5_000)
        self.assertEqual(self.row(WAGER)["metadata_retry_at"], 5_000 + 3_600)
        self.assertEqual(self.row(WAGER)["metadata_complete"], 0)

    def test_rows_that_keep_failing_do_not_starve_a_newer_one(self):
        """The 25 oldest incomplete rows were taken on every pass, so a 26th was never repaired."""
        old = [f"0x{i:040x}" for i in range(1, 26)]
        for i, address in enumerate(old):
            self.insert_incomplete(address, i + 1)
        self.insert_incomplete(WAGER, 100)
        self.backfill(1_000, ok=lambda a: a == WAGER)
        repaired, tried = self.backfill(1_020, ok=lambda a: a == WAGER)
        self.assertIn(WAGER, tried)
        self.assertEqual(repaired, 1)
        self.assertEqual(self.row(WAGER)["proposition"], "Will it rain?")
        self.assertEqual(self.row(WAGER)["metadata_complete"], 1)

    def test_a_repaired_row_is_left_alone_afterwards(self):
        self.insert_incomplete(WAGER, 1)
        self.backfill(1_000)
        self.backfill(1_015, ok=lambda a: True)
        self.assertEqual(self.row(WAGER)["metadata_complete"], 1)
        self.assertEqual(self.totals()["total_fee_bps"], "250")
        self.assertEqual(self.backfill(9_999)[1], [])

    def test_an_existing_database_gains_the_columns(self):
        # A `wagers` table as it was before ADR-0021: today's columns minus the two new ones. (SQLite's
        # DROP COLUMN rewrites the stored CREATE text and stumbles over the schema's comments.)
        new = {"metadata_attempts", "metadata_retry_at"}
        columns = [(r[1], r[2]) for r in self.conn.execute("PRAGMA table_info(wagers)") if r[1] not in new]
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(f"CREATE TABLE wagers ({', '.join(f'{name} {kind}' for name, kind in columns)})")
        init_db(conn)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(wagers)")}
        self.assertTrue({"metadata_attempts", "metadata_retry_at"} <= columns)
        conn.close()


# ---------------------------------------------------------------- U4: one eth_getLogs per quiet chunk


class FakeRpc:
    """Serves logs by emitting address and topic, and records every eth_getLogs filter."""

    def __init__(self, logs=(), head=100) -> None:
        self.logs = list(logs)
        self.head = head
        self.filters: list[dict] = []

    def __call__(self, rpc_url, method, params):
        if method == "eth_blockNumber":
            return hex(self.head)
        assert method == "eth_getLogs", method
        flt = params[0]
        self.filters.append(flt)
        addresses = {a.lower() for a in flt["address"]}
        return [
            log for log in self.logs
            if log["address"].lower() in addresses and log["topics"][0] in flt["topics"][0]
        ]


class LogQueryTests(Db):
    def sync(self, rpc: FakeRpc) -> int:
        with mock.patch.object(ix, "rpc_call", rpc), mock.patch.object(
            ix, "fetch_wager_metadata", return_value=dict(ix._NO_METADATA)
        ):
            return ix.sync_logs("http://rpc", self.conn, FACTORY, 1, None, 1_000)

    def test_a_chunk_without_creations_costs_one_query(self):
        self.apply(self.chain.created_enum())
        bet = self.chain.bet_enum(1, 9)
        rpc = FakeRpc([bet])
        self.sync(rpc)
        self.assertEqual(len(rpc.filters), 1, "one round trip for the factory and every known wager")
        self.assertEqual(rpc.filters[0]["address"], [FACTORY, WAGER])
        topics = rpc.filters[0]["topics"][0]
        self.assertIn(TOPICS["WagerCreatedV3Enumerated"], topics)
        self.assertIn(TOPICS["BetPlacedV3Enumerated"], topics)
        self.assertEqual(self.totals()["total_pot"], "9")

    def test_only_wagers_created_in_the_chunk_get_a_second_query(self):
        """A new wager's seed bets land in its creation transaction, so they need a follow-up."""
        self.apply(self.chain.created_enum())
        rpc = FakeRpc([self.chain.created_enum(wager=WAGER2), self.chain.bet_enum(1, 4, wager=WAGER2), self.chain.bet_enum(2, 3)])
        self.assertEqual(self.sync(rpc), 3)
        self.assertEqual([f["address"] for f in rpc.filters], [[FACTORY, WAGER], [WAGER2]])
        self.assertEqual(self.totals(WAGER2)["total_pot"], "4")
        self.assertEqual(self.totals(WAGER)["total_pot"], "3")

    def test_every_known_wager_is_queried_exactly_once_across_batches(self):
        self.apply(self.chain.created_enum())
        for i in range(ix.WAGER_ADDRESS_BATCH):
            self.conn.execute(
                """INSERT INTO wagers(wager_address, factory_address, proposer, resolver, betting_closer,
                   resolution_closer, collateral_token, betting_close_time, resolution_window,
                   resolution_deadline, state, created_block, created_tx_hash)
                   VALUES (?, ?, 'p', 'r', 'b', 'c', 't', 0, 0, 0, 'OPEN', 1, 'x')""",
                (f"0x{i:040x}", FACTORY),
            )
        self.conn.commit()
        rpc = FakeRpc()
        self.sync(rpc)
        queried = [a for f in rpc.filters for a in f["address"]]
        self.assertEqual(len(rpc.filters), 2)
        self.assertTrue(all(len(f["address"]) <= ix.WAGER_ADDRESS_BATCH for f in rpc.filters))
        self.assertEqual(sorted(queried), sorted({FACTORY, WAGER, *(f"0x{i:040x}" for i in range(ix.WAGER_ADDRESS_BATCH))}))
        self.assertEqual(len(queried), len(set(queried)))

    def test_the_wager_list_is_read_once_per_sync_when_nothing_is_created(self):
        """A cold-start replay is ~100k chunks; re-reading every wager per chunk would dominate it."""
        self.apply(self.chain.created_enum())
        with mock.patch.object(ix, "_known_wagers", wraps=ix._known_wagers) as listing:
            with mock.patch.object(ix, "rpc_call", FakeRpc(head=30)), mock.patch.object(
                ix, "fetch_wager_metadata", return_value=dict(ix._NO_METADATA)
            ):
                ix.sync_logs("http://rpc", self.conn, FACTORY, 1, None, 10)
        self.assertEqual(listing.call_count, 1)

    def test_a_malformed_log_does_not_stop_the_chunk(self):
        self.apply(self.chain.created_enum())
        rpc = FakeRpc([self.chain.bet_enum(1, 9)])
        broken = {"address": WAGER, "blockNumber": "0x5", "logIndex": "0x0", "transactionHash": "0x1"}
        original = rpc.__call__

        def with_broken(rpc_url, method, params):
            out = original(rpc_url, method, params)
            return out + [broken] if method == "eth_getLogs" else out

        with mock.patch.object(ix, "rpc_call", with_broken), mock.patch.object(
            ix, "fetch_wager_metadata", return_value=dict(ix._NO_METADATA)
        ):
            ix.sync_logs("http://rpc", self.conn, FACTORY, 1, None, 1_000)
        self.assertEqual(self.totals()["total_pot"], "9")
        self.assertEqual(ix.get_meta_int(self.conn, "last_indexed_block"), 100, "the chunk completed")

    def test_a_creation_event_from_a_wager_address_is_still_ignored(self):
        """The factory and the wagers now share a query, so only the factory may create a wager."""
        self.apply(self.chain.created_enum())
        forged = self.chain.created_enum(wager=WAGER2)
        forged["address"] = WAGER
        self.sync(FakeRpc([forged]))
        self.assertIsNone(self.conn.execute("SELECT 1 FROM wagers WHERE wager_address = ?", (WAGER2,)).fetchone())


# ---------------------------------------------------------------- U5: /wagers?resolver=


class ResolverFilterTests(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = ix.db_connect(self.db_path)
        init_db(self.conn)
        for i, resolver in enumerate((RESOLVER, OTHER_RESOLVER, RESOLVER)):
            self.conn.execute(
                """INSERT INTO wagers(wager_address, factory_address, proposer, resolver, betting_closer,
                   resolution_closer, collateral_token, betting_close_time, resolution_window,
                   resolution_deadline, state, created_block, created_tx_hash)
                   VALUES (?, ?, 'p', ?, 'b', 'c', 't', 0, 0, 0, 'OPEN', ?, 'x')""",
                (f"0x{i + 1:040x}", FACTORY, resolver, i + 1),
            )
        self.conn.commit()
        api_module.Handler.conn = self.conn
        api_module.Handler.indexer_factory_address = None
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), api_module.Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.conn.close()
        os.remove(self.db_path)

    def get(self, path):
        try:
            with request.urlopen(self.base + path, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode())
        except HTTPError as exc:
            return exc.code, json.loads(exc.read().decode())

    def test_wagers_can_be_scoped_to_one_resolver(self):
        code, body = self.get(f"/wagers?state=OPEN&order=asc&resolver={RESOLVER.upper().replace('0X', '0x')}")
        self.assertEqual(code, 200)
        self.assertEqual([w["wager_address"] for w in body["wagers"]], [f"0x{1:040x}", f"0x{3:040x}"])

    def test_without_the_filter_every_resolver_is_listed(self):
        self.assertEqual(len(self.get("/wagers?state=OPEN")[1]["wagers"]), 3)

    def test_a_malformed_resolver_is_a_client_error(self):
        for bad in ("nonsense", "0x1234", "0x" + "g" * 40):
            with self.subTest(bad=bad):
                code, body = self.get(f"/wagers?resolver={bad}")
                self.assertEqual(code, 400)
                self.assertIn("resolver", body["error"])

    def test_the_root_route_documents_the_filter(self):
        self.assertTrue(any("resolver=" in e for e in self.get("/")[1]["endpoints"]))


if __name__ == "__main__":
    unittest.main()
