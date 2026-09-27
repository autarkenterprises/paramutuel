import sqlite3
import unittest

from service.indexer.indexer import TOPICS, apply_log, get_expire_candidates, init_db


def topic_addr(addr: str) -> str:
    return "0x" + ("0" * 24) + addr.lower().replace("0x", "")


def word_u256(v: int) -> str:
    return f"{v:064x}"


def word_addr(addr: str) -> str:
    return ("0" * 24) + addr.lower().replace("0x", "")


class IndexerStateTests(unittest.TestCase):
    FACTORY = "0xfac7000000000000000000000000000000000004"
    WAGER = "0xabc1000000000000000000000000000000000001"
    PROPOSER = "0xabc2000000000000000000000000000000000002"
    RESOLVER = "0xabc3000000000000000000000000000000000003"
    TOKEN = "0xabc4000000000000000000000000000000000004"
    BETTOR = "0xabc5000000000000000000000000000000000005"
    BETTING_CLOSER = "0xabc6000000000000000000000000000000000006"
    RESOLUTION_CLOSER = "0xabc7000000000000000000000000000000000007"

    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)

    def _wager_created_enum_log(self, betting_close=2_000, window=3_000, deadline=5_000):
        data = (
            "0x"
            + word_addr(self.TOKEN)
            + word_u256(0)  # payoffPolicy (SINGLE_WINNER) in low byte
            + word_u256(0)  # policyParam
            + word_u256(betting_close)
            + word_u256(window)
            + word_u256(deadline)
            + word_addr(self.BETTING_CLOSER)
            + word_addr(self.RESOLUTION_CLOSER)
        )
        return {
            "address": self.FACTORY,
            "topics": [
                TOPICS["WagerCreatedV3Enumerated"],
                topic_addr(self.WAGER),
                topic_addr(self.PROPOSER),
                topic_addr(self.RESOLVER),
            ],
            "data": data,
            "blockNumber": hex(10),
            "transactionHash": "0xaaa",
            "logIndex": hex(0),
        }

    def _wager_created_freeform_log(self):
        data = (
            "0x"
            + word_addr(self.TOKEN)
            + word_u256(2_000)
            + word_u256(3_000)
            + word_u256(5_000)
            + word_addr(self.BETTING_CLOSER)
            + word_addr(self.RESOLUTION_CLOSER)
        )
        return {
            "address": self.FACTORY,
            "topics": [
                TOPICS["WagerCreatedV3Freeform"],
                topic_addr(self.WAGER),
                topic_addr(self.PROPOSER),
                topic_addr(self.RESOLVER),
            ],
            "data": data,
            "blockNumber": hex(40),
            "transactionHash": "0xff0",
            "logIndex": hex(0),
        }

    def test_wager_created_enum_sets_protocol_and_factory(self):
        apply_log(self.conn, self.FACTORY, self._wager_created_enum_log())
        self.conn.commit()

        maddr = self.WAGER.lower()
        row = self.conn.execute(
            "SELECT * FROM wagers WHERE wager_address = ?", (maddr,)
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["state"], "OPEN")
        self.assertEqual(row["protocol_version"], "enumerated")
        self.assertEqual(row["factory_address"].lower(), self.FACTORY.lower())
        self.assertEqual(row["betting_closer"].lower(), self.BETTING_CLOSER.lower())
        self.assertEqual(row["resolution_closer"].lower(), self.RESOLUTION_CLOSER.lower())
        self.assertEqual(int(row["resolution_window"]), 3000)

    def test_wager_created_rejected_when_emitter_is_not_factory(self):
        log = self._wager_created_enum_log()
        log["address"] = "0xdeadbeef00000000000000000000000000000000"
        apply_log(self.conn, self.FACTORY, log)
        self.conn.commit()
        row = self.conn.execute(
            "SELECT 1 FROM wagers WHERE wager_address = ?", (self.WAGER.lower(),)
        ).fetchone()
        self.assertIsNone(row)

    def test_bet_placed_and_resolve_enum_flow(self):
        apply_log(self.conn, self.FACTORY, self._wager_created_enum_log())
        self.conn.commit()
        maddr = self.WAGER.lower()

        mask0 = 4
        bet_log = {
            "address": self.WAGER,
            "topics": [
                TOPICS["BetPlacedV3Enumerated"],
                topic_addr(self.BETTOR),
            ],
            "data": "0x" + word_u256(mask0) + word_u256(77),
            "blockNumber": hex(11),
            "transactionHash": "0xaab",
            "logIndex": hex(0),
        }
        apply_log(self.conn, self.FACTORY, bet_log)
        self.conn.commit()

        pool = self.conn.execute(
            "SELECT pool_total FROM wager_ticket_pools WHERE wager_address = ? AND ticket_mask = ?",
            (maddr, str(mask0)),
        ).fetchone()
        self.assertEqual(int(pool["pool_total"]), 77)
        totals = self.conn.execute(
            "SELECT total_pot FROM wager_totals WHERE wager_address = ?", (maddr,)
        ).fetchone()
        self.assertEqual(int(totals["total_pot"]), 77)

        resolve_log = {
            "address": self.WAGER,
            "topics": [TOPICS["ResolvedV3Enumerated"]],
            "data": "0x" + word_u256(mask0),
            "blockNumber": hex(12),
            "transactionHash": "0xaac",
            "logIndex": hex(0),
        }
        apply_log(self.conn, self.FACTORY, resolve_log)
        self.conn.commit()

        row = self.conn.execute(
            "SELECT state FROM wagers WHERE wager_address = ?", (maddr,)
        ).fetchone()
        self.assertEqual(row["state"], "RESOLVED")
        win = self.conn.execute(
            "SELECT winning_outcome FROM wager_totals WHERE wager_address = ?", (maddr,)
        ).fetchone()
        self.assertEqual(win["winning_outcome"], str(mask0))

    def test_bet_placed_and_resolve_freeform_flow(self):
        apply_log(self.conn, self.FACTORY, self._wager_created_freeform_log())
        self.conn.commit()
        maddr = self.WAGER.lower()

        row = self.conn.execute(
            "SELECT protocol_version FROM wagers WHERE wager_address = ?", (maddr,)
        ).fetchone()
        self.assertEqual(row["protocol_version"], "freeform")

        aid_topic = "0x" + word_u256(0xC0DE)
        bet_log = {
            "address": self.WAGER,
            "topics": [
                TOPICS["BetPlacedV3Freeform"],
                topic_addr(self.BETTOR),
                aid_topic,
            ],
            "data": "0x" + word_u256(99),
            "blockNumber": hex(41),
            "transactionHash": "0xff1",
            "logIndex": hex(0),
        }
        apply_log(self.conn, self.FACTORY, bet_log)
        self.conn.commit()
        pool = self.conn.execute(
            "SELECT pool_total FROM wager_ticket_pools WHERE wager_address = ? AND ticket_mask = ?",
            (maddr, aid_topic.lower()),
        ).fetchone()
        self.assertEqual(int(pool["pool_total"]), 99)

        res_log = {
            "address": self.WAGER,
            "topics": [TOPICS["ResolvedV3Freeform"], aid_topic],
            "data": "0x",
            "blockNumber": hex(42),
            "transactionHash": "0xff2",
            "logIndex": hex(0),
        }
        apply_log(self.conn, self.FACTORY, res_log)
        self.conn.commit()
        win = self.conn.execute(
            "SELECT winning_outcome, state FROM wagers m JOIN wager_totals t ON t.wager_address = m.wager_address WHERE m.wager_address = ?",
            (maddr,),
        ).fetchone()
        self.assertEqual(win["winning_outcome"], aid_topic.lower())
        self.assertEqual(win["state"], "RESOLVED")

    def test_expire_candidates_after_deadline(self):
        apply_log(self.conn, self.FACTORY, self._wager_created_enum_log())
        self.conn.commit()

        cands = get_expire_candidates(self.conn, now_ts=6000)
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0]["wager_address"], self.WAGER.lower())

        retract_log = {
            "address": self.WAGER,
            "topics": [TOPICS["RetractedV3"]],
            "data": "0x",
            "blockNumber": hex(13),
            "transactionHash": "0xaad",
            "logIndex": hex(0),
        }
        apply_log(self.conn, self.FACTORY, retract_log)
        self.conn.commit()
        self.assertEqual(len(get_expire_candidates(self.conn, now_ts=6000)), 0)

    def test_expire_candidates_when_resolution_window_closed_early(self):
        apply_log(self.conn, self.FACTORY, self._wager_created_enum_log())
        self.conn.commit()
        maddr = self.WAGER.lower()

        close_log = {
            "address": self.WAGER,
            "topics": [TOPICS["ResolutionWindowClosedByAuthorityV3"]],
            "data": "0x" + word_u256(2500),
            "blockNumber": hex(11),
            "transactionHash": "0xaae",
            "logIndex": hex(0),
        }
        apply_log(self.conn, self.FACTORY, close_log)
        self.conn.commit()

        cands = get_expire_candidates(self.conn, now_ts=3000)
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0]["wager_address"], maddr)

    def test_no_max_resolution_window_needs_authority_close(self):
        apply_log(
            self.conn,
            self.FACTORY,
            self._wager_created_enum_log(betting_close=0, window=0, deadline=0),
        )
        self.conn.commit()

        self.assertEqual(len(get_expire_candidates(self.conn, now_ts=999999)), 0)

        close_log = {
            "address": self.WAGER,
            "topics": [TOPICS["ResolutionWindowClosedByAuthorityV3"]],
            "data": "0x" + word_u256(999000),
            "blockNumber": hex(11),
            "transactionHash": "0xbbc",
            "logIndex": hex(0),
        }
        apply_log(self.conn, self.FACTORY, close_log)
        self.conn.commit()
        self.assertEqual(len(get_expire_candidates(self.conn, now_ts=999999)), 1)

    def test_betting_closed_by_authority(self):
        apply_log(self.conn, self.FACTORY, self._wager_created_enum_log())
        self.conn.commit()
        maddr = self.WAGER.lower()

        close_log = {
            "address": self.WAGER,
            "topics": [TOPICS["BettingClosedByAuthorityV3"]],
            "data": "0x" + word_u256(1500),
            "blockNumber": hex(11),
            "transactionHash": "0xaaf",
            "logIndex": hex(0),
        }
        apply_log(self.conn, self.FACTORY, close_log)
        self.conn.commit()

        row = self.conn.execute(
            "SELECT betting_closed_by_authority, betting_closed_at FROM wagers WHERE wager_address = ?",
            (maddr,),
        ).fetchone()
        self.assertEqual(int(row["betting_closed_by_authority"]), 1)
        self.assertEqual(int(row["betting_closed_at"]), 1500)


class FeeBpsEnrichmentTests(IndexerStateTests):
    """ADR-0019: ``wager_totals.total_fee_bps`` must mirror the wager's
    on-chain ``totalFeeBps()``.

    V3 creation events carry no fee data, so the indexer must read the
    immutable fee total via ``eth_call`` at creation time. Before ADR-0019
    the column was hard-coded to ``'0'`` and never updated, so every
    fee-aware consumer (bet scout EV, site odds preview, explorer) silently
    assumed a fee-free pot and overstated payouts by the fee share.
    Inherits the log builders from ``IndexerStateTests`` (its tests re-run
    here harmlessly).
    """

    FEE_BPS = 350

    def _fake_eth_call(self, calls):
        from service.indexer import indexer as ix

        def fake(rpc_url, to_addr, data_hex):
            calls.append((to_addr, data_hex))
            if data_hex == ix.WAGER_TOTAL_FEE_BPS_SELECTOR:
                return "0x" + word_u256(self.FEE_BPS)
            if data_hex == ix.WAGER_OUTCOMES_COUNT_SELECTOR:
                return "0x" + word_u256(0)
            # proposition(): ABI-encoded string "q"
            return "0x" + word_u256(32) + word_u256(1) + "71".ljust(64, "0")

        return fake

    def _fee_after_create(self, log, eth_call):
        from unittest import mock

        from service.indexer import indexer as ix

        with mock.patch.object(ix, "_eth_call_hex", eth_call):
            apply_log(self.conn, self.FACTORY, log, rpc_url="http://rpc.invalid")
        self.conn.commit()
        row = self.conn.execute(
            "SELECT total_fee_bps FROM wager_totals WHERE wager_address = ?", (self.WAGER.lower(),)
        ).fetchone()
        self.assertIsNotNone(row)
        return row["total_fee_bps"]

    def test_enumerated_create_records_onchain_total_fee_bps(self):
        calls = []
        fee = self._fee_after_create(self._wager_created_enum_log(), self._fake_eth_call(calls))
        self.assertEqual(fee, str(self.FEE_BPS))
        # Every enrichment call targets the new wager, never the factory.
        self.assertTrue(calls)
        self.assertTrue(all(to.lower() == self.WAGER.lower() for to, _ in calls))

    def test_freeform_create_records_onchain_total_fee_bps(self):
        fee = self._fee_after_create(self._wager_created_freeform_log(), self._fake_eth_call([]))
        self.assertEqual(fee, str(self.FEE_BPS))

    def test_fee_lookup_failure_does_not_block_indexing(self):
        def boom(*_a, **_k):
            raise RuntimeError("rpc down")

        fee = self._fee_after_create(self._wager_created_enum_log(), boom)
        self.assertEqual(fee, "0")


class LargeAmountTests(IndexerStateTests):
    """ADR-0019: pot arithmetic must be exact for any uint256 stake.

    ``total_pot`` was accumulated in SQL (``CAST(total_pot AS INTEGER) + ?``).
    SQLite integers are signed 64-bit, i.e. ~9.22 tokens of an 18-decimal
    collateral (WETH / DAI are site presets; collateral is permissionless):
    crossing 2**63 silently turned the pot into the REAL text ``'1.0e+19'``
    (breaking every ``int()`` / ``BigInt()`` consumer), and a single bet
    >= 2**63 raised ``OverflowError`` mid-``apply_log`` after the event row and
    ticket pool had already been written — a torn, committed state.
    """

    def _bet(self, amount, *, tx, log_index=0, freeform=False):
        if freeform:
            topics = [TOPICS["BetPlacedV3Freeform"], topic_addr(self.BETTOR), "0x" + "ab" * 32]
            data = "0x" + word_u256(amount)
        else:
            topics = [TOPICS["BetPlacedV3Enumerated"], topic_addr(self.BETTOR)]
            data = "0x" + word_u256(1) + word_u256(amount)
        return {
            "address": self.WAGER,
            "topics": topics,
            "data": data,
            "blockNumber": hex(11),
            "transactionHash": tx,
            "logIndex": hex(log_index),
        }

    def _pot(self):
        row = self.conn.execute(
            "SELECT total_pot FROM wager_totals WHERE wager_address = ?", (self.WAGER.lower(),)
        ).fetchone()
        return row["total_pot"]

    def test_enumerated_pot_is_exact_past_int64(self):
        apply_log(self.conn, self.FACTORY, self._wager_created_enum_log())
        for i in range(2):
            apply_log(self.conn, self.FACTORY, self._bet(5 * 10**18, tx=f"0xb{i}"))
        self.conn.commit()
        self.assertEqual(self._pot(), str(10 * 10**18))

    def test_single_huge_bet_is_exact_for_both_modes(self):
        huge = 10**30 + 7
        apply_log(self.conn, self.FACTORY, self._wager_created_freeform_log())
        apply_log(self.conn, self.FACTORY, self._bet(huge, tx="0xc1", freeform=True))
        apply_log(self.conn, self.FACTORY, self._bet(huge, tx="0xc2", freeform=True))
        self.conn.commit()
        self.assertEqual(self._pot(), str(2 * huge))
        pool = self.conn.execute(
            "SELECT pool_total FROM wager_ticket_pools WHERE wager_address = ?", (self.WAGER.lower(),)
        ).fetchone()
        self.assertEqual(pool["pool_total"], str(2 * huge))

    def test_failed_log_leaves_no_partial_state(self):
        """sync_logs applies each log atomically: a log that fails half-way
        must not leave its event row (or any other write) behind."""
        from unittest import mock

        from service.indexer import indexer as ix

        apply_log(self.conn, self.FACTORY, self._wager_created_enum_log())
        self.conn.commit()
        bad = self._bet(3, tx="0xdead")
        real_apply = ix.apply_log

        def half_apply(conn, factory, log, rpc_url=None):
            real_apply(conn, factory, log, rpc_url=rpc_url)
            raise RuntimeError("simulated failure after writes")

        with mock.patch.object(ix, "rpc_call", return_value="0x20"), \
             mock.patch.object(ix, "_eth_get_logs_bisect", return_value=[bad]), \
             mock.patch.object(ix, "apply_log", half_apply):
            ix.sync_logs(rpc_url="http://rpc.invalid", conn=self.conn, factory_address=self.FACTORY,
                         from_block=11, to_block=11, chunk_size=10)
        n = self.conn.execute(
            "SELECT COUNT(*) AS n FROM events_log WHERE tx_hash = ?", ("0xdead",)
        ).fetchone()["n"]
        self.assertEqual(n, 0)
        self.assertEqual(self._pot(), "0")


if __name__ == "__main__":
    unittest.main()
