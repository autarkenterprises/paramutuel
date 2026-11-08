"""ADR-0020 indexer regressions: state the indexer must derive correctly from logs.

Each test pins one verified finding (see research/adr/ADR-0020-*.md): fields that
were never written, data lost for good on one RPC hiccup, wagers made invisible by
a valid on-chain value, and failures that vanished without a trace.
"""
import sqlite3
import unittest
from unittest import mock

from service.indexer import indexer as ix
from service.indexer.indexer import TOPICS, apply_log, compute_winning_units, init_db

FACTORY = "0xfac7000000000000000000000000000000000004"
WAGER = "0xabc1000000000000000000000000000000000001"
PROPOSER = "0xabc2000000000000000000000000000000000002"
RESOLVER = "0xabc3000000000000000000000000000000000003"
TOKEN = "0xabc4000000000000000000000000000000000004"
BETTOR = "0xabc5000000000000000000000000000000000005"
ANSWER_ID = "0x" + "ab" * 32


def topic_addr(addr: str) -> str:
    return "0x" + ("0" * 24) + addr.lower().replace("0x", "")


def word(v: int) -> str:
    return f"{v:064x}"


def word_addr(addr: str) -> str:
    return ("0" * 24) + addr.lower().replace("0x", "")


def abi_bytes(raw: bytes) -> str:
    """ABI encoding of a single dynamic string/bytes event argument."""
    padded = raw.hex().ljust((len(raw) + 31) // 32 * 64, "0")
    return "0x" + word(32) + word(len(raw)) + padded


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)
        self.counter = 0

    def _meta(self, tx=None):
        self.counter += 1
        return {
            "blockNumber": hex(10 + self.counter),
            "transactionHash": tx or f"0x{self.counter:064x}",
            "logIndex": hex(0),
        }

    def _created_enum(self, policy=0, param=0, betting_close=2_000, window=3_000, deadline=5_000, tx=None):
        data = (
            "0x" + word_addr(TOKEN) + word(policy) + word(param) + word(betting_close) + word(window) + word(deadline)
            + word_addr(RESOLVER) + word_addr(RESOLVER)
        )
        return {
            "address": FACTORY,
            "topics": [TOPICS["WagerCreatedV3Enumerated"], topic_addr(WAGER), topic_addr(PROPOSER), topic_addr(RESOLVER)],
            "data": data,
            **self._meta(tx),
        }

    def _created_free(self):
        data = "0x" + word_addr(TOKEN) + word(2_000) + word(3_000) + word(5_000) + word_addr(RESOLVER) + word_addr(RESOLVER)
        return {
            "address": FACTORY,
            "topics": [TOPICS["WagerCreatedV3Freeform"], topic_addr(WAGER), topic_addr(PROPOSER), topic_addr(RESOLVER)],
            "data": data,
            **self._meta(),
        }

    def _bet_enum(self, mask, amount):
        return {
            "address": WAGER,
            "topics": [TOPICS["BetPlacedV3Enumerated"], topic_addr(BETTOR)],
            "data": "0x" + word(mask) + word(amount),
            **self._meta(),
        }

    def _bet_free(self, answer_id, amount):
        return {
            "address": WAGER,
            "topics": [TOPICS["BetPlacedV3Freeform"], topic_addr(BETTOR), answer_id],
            "data": "0x" + word(amount),
            **self._meta(),
        }

    def _reveal(self, answer_id, raw: bytes, address=WAGER):
        return {
            "address": address,
            "topics": [TOPICS["FreeformAnswerRevealedV3"], answer_id],
            "data": abi_bytes(raw),
            **self._meta(),
        }

    def _resolved_enum(self, mask):
        return {
            "address": WAGER,
            "topics": [TOPICS["ResolvedV3Enumerated"]],
            "data": "0x" + word(mask),
            **self._meta(),
        }

    def _resolved_free(self, answer_id):
        return {
            "address": WAGER,
            "topics": [TOPICS["ResolvedV3Freeform"], answer_id],
            "data": "0x",
            **self._meta(),
        }

    def _apply(self, *logs, rpc_url=None):
        for log in logs:
            apply_log(self.conn, FACTORY, log, rpc_url=rpc_url)
        self.conn.commit()

    def _totals(self):
        return self.conn.execute("SELECT * FROM wager_totals WHERE wager_address = ?", (WAGER,)).fetchone()

    def _wager(self):
        return self.conn.execute("SELECT * FROM wagers WHERE wager_address = ?", (WAGER,)).fetchone()


class WinningUnitsTests(unittest.TestCase):
    """The Python port must equal `_accumulateWinningUnits`, because clients divide by it.

    The local end-to-end suite compares it with the real `payoutDenominator` on-chain.
    """

    POOLS = {0b001: 100, 0b010: 200, 0b011: 40, 0b111: 8}

    def test_single_winner_is_the_winning_pool(self):
        self.assertEqual(compute_winning_units(0, 0, 0b010, {0b001: 100, 0b010: 200}), 200)

    def test_any_of_counts_every_overlapping_ticket(self):
        self.assertEqual(compute_winning_units(1, 0, 0b001, self.POOLS), 100 + 40 + 8)

    def test_exact_set_counts_only_the_identical_mask(self):
        self.assertEqual(compute_winning_units(2, 0, 0b011, self.POOLS), 40)

    def test_at_least_k_needs_k_overlapping_outcomes(self):
        self.assertEqual(compute_winning_units(3, 2, 0b011, self.POOLS), 40 + 8)

    def test_weighted_overlap_multiplies_by_overlap_size(self):
        self.assertEqual(compute_winning_units(4, 0, 0b011, self.POOLS), 100 * 1 + 200 * 1 + 40 * 2 + 8 * 2)

    def test_exact_above_int64(self):
        huge = 2**200
        self.assertEqual(compute_winning_units(1, 0, 1, {1: huge, 3: huge}), 2 * huge)


class ResolvedStakeTests(Base):
    def test_enumerated_resolve_records_total_winning_stake(self):
        # WEIGHTED_OVERLAP: the stake is tokens; the denominator weighs {A,B} twice (ADR-0021 U3).
        self._apply(self._created_enum(policy=4), self._bet_enum(0b01, 100), self._bet_enum(0b11, 40), self._bet_enum(0b10, 7))
        self._apply(self._resolved_enum(0b11))
        self.assertEqual(self._totals()["total_winning_stake"], str(100 + 40 + 7))
        self.assertEqual(self._totals()["payout_denominator"], str(100 + 80 + 7))

    def test_freeform_resolve_records_winning_pool(self):
        self._apply(self._created_free(), self._bet_free(ANSWER_ID, 5), self._bet_free(ANSWER_ID, 6))
        self._apply(self._resolved_free(ANSWER_ID))
        self.assertEqual(self._totals()["total_winning_stake"], "11")


class RevealedAnswerTests(Base):
    def _answers(self):
        return self.conn.execute("SELECT * FROM wager_answers WHERE wager_address = ?", (WAGER,)).fetchall()

    def test_answer_text_recorded_byte_exact(self):
        text = "  Café \"au lait\" "
        self._apply(self._created_free(), self._reveal(ANSWER_ID, text.encode()))
        rows = self._answers()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["answer_id"], ANSWER_ID)
        self.assertEqual(rows[0]["answer_text"], text)
        self.assertEqual(rows[0]["answer_hex"], "0x" + text.encode().hex())

    def test_replay_is_idempotent(self):
        reveal = self._reveal(ANSWER_ID, b"Paris")
        self._apply(self._created_free(), reveal, reveal)
        self.assertEqual(len(self._answers()), 1)

    def test_invalid_utf8_keeps_exact_hex_and_no_lossy_text(self):
        """`string` on-chain can hold any bytes. Lossy decoding would give clients a string that
        hashes to a different answer id, so only the exact bytes are kept."""
        self._apply(self._created_free(), self._reveal(ANSWER_ID, b"\xff\xfe"))
        row = self._answers()[0]
        self.assertIsNone(row["answer_text"])
        self.assertEqual(row["answer_hex"], "0xfffe")

    def test_reveal_from_unknown_contract_is_ignored(self):
        self._apply(self._created_free(), self._reveal(ANSWER_ID, b"spoof", address="0x" + "99" * 20))
        self.assertEqual(self._answers(), [])


class CreationValueTests(Base):
    def test_close_time_above_int64_keeps_the_wager_visible(self):
        """`bettingCloseTime` is a uint64. 2**63 and above overflowed SQLite's INTEGER, which dropped
        the wager and orphaned all its bets."""
        self._apply(self._created_enum(betting_close=2**64 - 1, window=0, deadline=0), self._bet_enum(1, 5))
        row = self._wager()
        self.assertIsNotNone(row)
        self.assertEqual(row["betting_close_time"], 2**63 - 1, "clamped; still effectively never")
        self.assertEqual(self._totals()["total_pot"], "5")

    def test_replayed_creation_makes_no_rpc_calls(self):
        calls = []

        def eth_call(rpc_url, to_addr, data_hex):
            calls.append(data_hex)
            return "0x" + word(0)

        log = self._created_enum()
        with mock.patch.object(ix, "_eth_call_hex", eth_call):
            self._apply(log, rpc_url="http://rpc.invalid")
            before = len(calls)
            self.assertGreater(before, 0)
            self._apply(log, rpc_url="http://rpc.invalid")
        self.assertEqual(len(calls), before)


class MetadataRecoveryTests(Base):
    """One RPC hiccup used to blank a wager's proposition and outcomes and zero its fee for good."""

    def _healthy_chain(self):
        def eth_call(rpc_url, to_addr, data_hex):
            if data_hex == ix.WAGER_TOTAL_FEE_BPS_SELECTOR:
                return "0x" + word(350)
            if data_hex == ix.WAGER_MIN_NEW_TICKET_STAKE_SELECTOR:
                return "0x" + word(5000)
            if data_hex == ix.WAGER_OUTCOMES_COUNT_SELECTOR:
                return "0x" + word(2)
            if data_hex == ix.WAGER_PROPOSITION_SELECTOR:
                return abi_bytes(b"Will it?")
            return abi_bytes(b"Yes" if data_hex.endswith("0" * 64) else b"No")

        return eth_call

    def test_rpc_failure_marks_incomplete_then_backfill_repairs(self):
        def outage(rpc_url, to_addr, data_hex):
            raise OSError("connection reset")

        with mock.patch.object(ix, "_eth_call_hex", outage):
            self._apply(self._created_enum(), rpc_url="http://rpc.invalid")
        row = self._wager()
        self.assertEqual(row["metadata_complete"], 0)
        self.assertEqual(row["proposition"], "")
        self.assertEqual(self._totals()["total_fee_bps"], "0")

        with mock.patch.object(ix, "_eth_call_hex", self._healthy_chain()):
            repaired = ix.backfill_incomplete_metadata(self.conn, "http://rpc.invalid")
        self.assertEqual(repaired, 1)
        row = self._wager()
        self.assertEqual(row["metadata_complete"], 1)
        self.assertEqual(row["proposition"], "Will it?")
        self.assertEqual(row["outcomes_json"], '["Yes", "No"]')
        self.assertEqual(row["min_new_ticket_stake"], "5000")
        self.assertEqual(self._totals()["total_fee_bps"], "350")

    def test_backfill_leaves_row_incomplete_while_outage_continues(self):
        def outage(rpc_url, to_addr, data_hex):
            raise OSError("still down")

        with mock.patch.object(ix, "_eth_call_hex", outage):
            self._apply(self._created_enum(), rpc_url="http://rpc.invalid")
            self.assertEqual(ix.backfill_incomplete_metadata(self.conn, "http://rpc.invalid"), 0)
        self.assertEqual(self._wager()["metadata_complete"], 0)

    def test_min_stake_recorded_when_healthy(self):
        with mock.patch.object(ix, "_eth_call_hex", self._healthy_chain()):
            self._apply(self._created_enum(), rpc_url="http://rpc.invalid")
        self.assertEqual(self._wager()["min_new_ticket_stake"], "5000")
        self.assertEqual(self._wager()["metadata_complete"], 1)

    def test_older_wager_without_min_stake_getter_reads_zero_and_is_complete(self):
        """Wagers from the currently deployed factory have no `minNewTicketStake()`, which reverts.
        That is not a failure, so it must not be retried forever (ADR-0020 additivity)."""
        healthy = self._healthy_chain()

        def eth_call(rpc_url, to_addr, data_hex):
            if data_hex == ix.WAGER_MIN_NEW_TICKET_STAKE_SELECTOR:
                raise RuntimeError("RPC error: {'code': 3, 'message': 'execution reverted'}")
            return healthy(rpc_url, to_addr, data_hex)

        with mock.patch.object(ix, "_eth_call_hex", eth_call):
            self._apply(self._created_enum(), rpc_url="http://rpc.invalid")
        self.assertEqual(self._wager()["min_new_ticket_stake"], "0")
        self.assertEqual(self._wager()["metadata_complete"], 1)


class FakeRpc:
    """Scripted JSON-RPC: records eth_getLogs filters and serves canned logs."""

    def __init__(self, head=100, logs_by_address=None):
        self.head = head
        self.filters = []
        self.logs_by_address = logs_by_address or {}

    def __call__(self, rpc_url, method, params):
        if method == "eth_blockNumber":
            return hex(self.head)
        if method == "eth_getLogs":
            flt = params[0]
            self.filters.append(flt)
            out = []
            for addr in flt.get("address") or []:
                out.extend(self.logs_by_address.get(addr.lower(), []))
            return out
        if method == "eth_call":
            return "0x" + word(0)
        raise AssertionError(f"unexpected rpc {method}")


class SyncTests(Base):
    def _sync(self, rpc, from_block=1, **kw):
        with mock.patch.object(ix, "rpc_call", rpc):
            return ix.sync_logs(
                rpc_url="http://rpc.invalid", conn=self.conn, factory_address=FACTORY,
                from_block=from_block, to_block=None, chunk_size=1000, **kw
            )

    def test_logs_are_filtered_by_address_factory_then_known_wagers(self):
        """An unfiltered topic scan let any contract emit our topics, inflating every response and
        stalling bisection. Only the factory and wagers it created are ever queried."""
        rpc = FakeRpc(logs_by_address={FACTORY: [self._created_enum()], WAGER: [self._bet_enum(1, 9)]})
        self._sync(rpc)
        self.assertEqual(rpc.filters[0]["address"], [FACTORY])
        self.assertEqual(rpc.filters[1]["address"], [WAGER])
        for flt in rpc.filters:
            self.assertNotIn("0x0000000000000000000000000000000000000000", flt["address"])
        self.assertEqual(self._totals()["total_pot"], "9")

    def test_wager_created_and_bet_in_one_chunk_are_both_applied(self):
        """Seed bets land in the creation tx, so the second query must see the new wager."""
        rpc = FakeRpc(logs_by_address={FACTORY: [self._created_enum()], WAGER: [self._bet_enum(1, 3), self._bet_enum(2, 4)]})
        self.assertEqual(self._sync(rpc), 3)
        self.assertEqual(self._totals()["total_pot"], "7")

    def test_no_known_wagers_means_no_second_query(self):
        rpc = FakeRpc()
        self._sync(rpc)
        self.assertEqual(len(rpc.filters), 1)

    def test_wager_addresses_are_batched(self):
        self._apply(self._created_enum())
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
        self._sync(rpc)
        # The factory shares the first batch with the wagers (ADR-0021 U4): 202 addresses, 2 queries.
        self.assertEqual(len(rpc.filters), 2)
        self.assertEqual(sum(len(f["address"]) for f in rpc.filters), ix.WAGER_ADDRESS_BATCH + 2)

    def test_confirmations_hold_back_the_unsafe_head(self):
        rpc = FakeRpc(head=100)
        self._sync(rpc, confirmations=5)
        self.assertEqual(rpc.filters[-1]["toBlock"], hex(95))
        self.assertEqual(ix.get_meta_int(self.conn, "last_indexed_block"), 95)
        self.assertEqual(ix.get_meta_int(self.conn, "chain_head"), 100)

    def test_being_caught_up_is_not_an_error(self):
        rpc = FakeRpc(head=100)
        self._sync(rpc, from_block=101)
        self.assertEqual(ix.get_meta_str(self.conn, "last_sync_error"), "")

    def test_cursor_beyond_head_is_still_reported(self):
        rpc = FakeRpc(head=100)
        self._sync(rpc, from_block=500)
        self.assertIn("ahead of chain head", ix.get_meta_str(self.conn, "last_sync_error"))

    def test_skipped_log_is_counted_and_described(self):
        """A log that cannot be applied is lost once the cursor moves on. That has to be visible."""
        bad = self._created_enum()
        bad["data"] = "0x1234"  # too short to decode
        rpc = FakeRpc(logs_by_address={FACTORY: [bad]})
        self._sync(rpc)
        self.assertEqual(ix.get_meta_int(self.conn, "skipped_log_count"), 1)
        self.assertIn(bad["transactionHash"], ix.get_meta_str(self.conn, "last_skipped_log"))

    def test_sync_pass_backfills_incomplete_metadata(self):
        def outage(rpc_url, to_addr, data_hex):
            raise OSError("down")

        with mock.patch.object(ix, "_eth_call_hex", outage):
            self._apply(self._created_enum(), rpc_url="http://rpc.invalid")
        self.assertEqual(self._wager()["metadata_complete"], 0)
        self._sync(FakeRpc(), from_block=101)
        self.assertEqual(self._wager()["metadata_complete"], 1)


class SchemaMigrationTests(unittest.TestCase):
    def test_init_db_adds_columns_to_a_database_from_the_previous_schema(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE wagers (wager_address TEXT PRIMARY KEY, factory_address TEXT NOT NULL,
              proposer TEXT NOT NULL, resolver TEXT NOT NULL, betting_closer TEXT NOT NULL,
              resolution_closer TEXT NOT NULL, collateral_token TEXT NOT NULL,
              proposition TEXT NOT NULL DEFAULT '', outcomes_json TEXT NOT NULL DEFAULT '[]',
              protocol_version TEXT NOT NULL DEFAULT 'enumerated', payoff_policy INTEGER, policy_param TEXT,
              betting_close_time INTEGER NOT NULL, resolution_window INTEGER NOT NULL,
              resolution_deadline INTEGER NOT NULL, betting_closed_by_authority INTEGER NOT NULL DEFAULT 0,
              betting_closed_at INTEGER, resolution_window_closed INTEGER NOT NULL DEFAULT 0,
              resolution_window_closed_at INTEGER, state TEXT NOT NULL, created_block INTEGER NOT NULL,
              created_tx_hash TEXT NOT NULL);
            CREATE TABLE wager_outcomes (wager_address TEXT, outcome_index INTEGER, outcome_total TEXT);
            """
        )
        init_db(conn)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(wagers)")}
        self.assertIn("min_new_ticket_stake", columns)
        self.assertIn("metadata_complete", columns)
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn("wager_outcomes", tables)
        self.assertIn("wager_answers", tables)
        init_db(conn)  # idempotent


if __name__ == "__main__":
    unittest.main()
