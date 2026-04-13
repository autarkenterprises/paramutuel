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
    FACTORY = "0xfac7000000000000000000000000000000000001"
    FACTORY_V2 = "0xfac7000000000000000000000000000000000002"
    FACTORY_FF = "0xfac7000000000000000000000000000000000003"
    FACTORY_V3 = "0xfac7000000000000000000000000000000000004"
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

    def _wager_created_log(self):
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
                "0x1b9545daed972e7de65f9c8b3445fdfd1af0c41cdc5774595c37bc7e35f28def",
                topic_addr(self.WAGER),
                topic_addr(self.PROPOSER),
                topic_addr(self.RESOLVER),
            ],
            "data": data,
            "blockNumber": hex(10),
            "transactionHash": "0xaaa",
            "logIndex": hex(0),
        }

    def test_wager_created_and_state_progression(self):
        apply_log(self.conn, self.FACTORY, "", self._wager_created_log())
        self.conn.commit()

        maddr = self.WAGER.lower()
        row = self.conn.execute("SELECT * FROM wagers WHERE wager_address = ?", (maddr,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["state"], "OPEN")
        self.assertEqual(row["betting_closer"].lower(), self.BETTING_CLOSER.lower())
        self.assertEqual(row["resolution_closer"].lower(), self.RESOLUTION_CLOSER.lower())
        self.assertEqual(int(row["resolution_window"]), 3000)

        # BetPlaced: bettor, outcomeIndex=1, amount=100
        bet_log = {
            "address": self.WAGER,
            "topics": [
                "0x001ecf1d0c4d22f324b3ecb9cdf0e5f772bc74ac104e6626f4b3845433d03105",
                topic_addr(self.BETTOR),
                "0x" + ("0" * 63) + "1",
            ],
            "data": "0x" + word_u256(100),
            "blockNumber": hex(11),
            "transactionHash": "0xaab",
            "logIndex": hex(0),
        }
        apply_log(self.conn, self.FACTORY, "", bet_log)
        self.conn.commit()

        totals = self.conn.execute("SELECT total_pot FROM wager_totals WHERE wager_address = ?", (maddr,)).fetchone()
        self.assertEqual(int(totals["total_pot"]), 100)

        # Resolve outcome 1
        resolve_log = {
            "address": self.WAGER,
            "topics": [
                "0x148a25ee2a7671350ab878ff183447de8ae5afa2ee0ae7d5ee1ad6b25c4868c2",
                "0x" + ("0" * 63) + "1",
            ],
            "data": "0x",
            "blockNumber": hex(12),
            "transactionHash": "0xaac",
            "logIndex": hex(0),
        }
        apply_log(self.conn, self.FACTORY, "", resolve_log)
        self.conn.commit()

        row2 = self.conn.execute("SELECT state FROM wagers WHERE wager_address = ?", (maddr,)).fetchone()
        self.assertEqual(row2["state"], "RESOLVED")

    def test_expire_candidates(self):
        apply_log(self.conn, self.FACTORY, "", self._wager_created_log())
        self.conn.commit()

        # now_ts beyond resolution deadline (5000)
        cands = get_expire_candidates(self.conn, now_ts=6000)
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0]["wager_address"], self.WAGER.lower())

        # Retract event should remove candidate
        retract_log = {
            "address": self.WAGER,
            "topics": ["0x6c8d8af1eb7d9e8ea2f489b8d39cc78f924042413d0e15ce70f8cdb53afab46a"],
            "data": "0x",
            "blockNumber": hex(13),
            "transactionHash": "0xaad",
            "logIndex": hex(0),
        }
        apply_log(self.conn, self.FACTORY, "", retract_log)
        self.conn.commit()
        cands2 = get_expire_candidates(self.conn, now_ts=6000)
        self.assertEqual(len(cands2), 0)

    def test_expire_candidates_when_resolution_window_closed_early(self):
        apply_log(self.conn, self.FACTORY, "", self._wager_created_log())
        self.conn.commit()
        maddr = self.WAGER.lower()

        # Before on-chain deadline (5000), but resolution window closed by authority
        close_log = {
            "address": self.WAGER,
            "topics": ["0x3a016249126bba7044eec394afa8eba111d1ea6bda5a42b663f7d86944fd1f87"],
            "data": "0x" + word_u256(2500),
            "blockNumber": hex(11),
            "transactionHash": "0xaae",
            "logIndex": hex(0),
        }
        apply_log(self.conn, self.FACTORY, "", close_log)
        self.conn.commit()

        cands = get_expire_candidates(self.conn, now_ts=3000)
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0]["wager_address"], maddr)

    def test_no_max_resolution_window_needs_authority_close(self):
        # Create wager with no max windows: close_time=0, resolution_window=0, resolution_deadline=0
        data = (
            "0x"
            + word_addr(self.TOKEN)
            + word_u256(0)
            + word_u256(0)
            + word_u256(0)
            + word_addr(self.BETTING_CLOSER)
            + word_addr(self.RESOLUTION_CLOSER)
        )
        create_log = {
            "address": self.FACTORY,
            "topics": [
                "0x1b9545daed972e7de65f9c8b3445fdfd1af0c41cdc5774595c37bc7e35f28def",
                topic_addr(self.WAGER),
                topic_addr(self.PROPOSER),
                topic_addr(self.RESOLVER),
            ],
            "data": data,
            "blockNumber": hex(10),
            "transactionHash": "0xbbb",
            "logIndex": hex(0),
        }
        apply_log(self.conn, self.FACTORY, "", create_log)
        self.conn.commit()

        self.assertEqual(len(get_expire_candidates(self.conn, now_ts=999999)), 0)

        # Once resolution window is closed by authority, it becomes expire-eligible immediately.
        close_log = {
            "address": self.WAGER,
            "topics": ["0x3a016249126bba7044eec394afa8eba111d1ea6bda5a42b663f7d86944fd1f87"],
            "data": "0x" + word_u256(999000),
            "blockNumber": hex(11),
            "transactionHash": "0xbbc",
            "logIndex": hex(0),
        }
        apply_log(self.conn, self.FACTORY, "", close_log)
        self.conn.commit()
        self.assertEqual(len(get_expire_candidates(self.conn, now_ts=999999)), 1)

    def _wager_created_v2_log(self):
        # WagerCreatedV2: 3 indexed addresses + non-indexed tail in data
        data = (
            "0x"
            + word_addr(self.TOKEN)
            + word_u256(0)  # payoffPolicy uint8 in last byte of word
            + word_u256(0)  # policyParam
            + word_u256(2_000)
            + word_u256(3_000)
            + word_u256(5_000)
            + word_addr(self.BETTING_CLOSER)
            + word_addr(self.RESOLUTION_CLOSER)
        )
        return {
            "address": self.FACTORY_V2,
            "topics": [
                "0x7245d6cca974fb4447fd236c460f3aa281da5ffa682c9b5392e99c37bb3ca89a",
                topic_addr(self.WAGER),
                topic_addr(self.PROPOSER),
                topic_addr(self.RESOLVER),
            ],
            "data": data,
            "blockNumber": hex(20),
            "transactionHash": "0xbb0",
            "logIndex": hex(0),
        }

    def test_wager_v2_ticket_pools_and_resolve(self):
        apply_log(self.conn, self.FACTORY, self.FACTORY_V2, self._wager_created_v2_log())
        self.conn.commit()
        maddr = self.WAGER.lower()
        row = self.conn.execute("SELECT * FROM wagers WHERE wager_address = ?", (maddr,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["protocol_version"], "v2")

        # v2 BetPlaced: bettor indexed; ticketMask + amount in data (mask = 1 << 0)
        mask0 = 1
        bet_log = {
            "address": self.WAGER,
            "topics": [
                "0x001ecf1d0c4d22f324b3ecb9cdf0e5f772bc74ac104e6626f4b3845433d03105",
                topic_addr(self.BETTOR),
            ],
            "data": "0x" + word_u256(mask0) + word_u256(50),
            "blockNumber": hex(21),
            "transactionHash": "0xbb1",
            "logIndex": hex(0),
        }
        apply_log(self.conn, self.FACTORY, self.FACTORY_V2, bet_log)
        self.conn.commit()
        pool = self.conn.execute(
            "SELECT pool_total FROM wager_ticket_pools WHERE wager_address = ? AND ticket_mask = ?",
            (maddr, str(mask0)),
        ).fetchone()
        self.assertIsNotNone(pool)
        self.assertEqual(int(pool["pool_total"]), 50)

        resolve_log = {
            "address": self.WAGER,
            "topics": ["0x148a25ee2a7671350ab878ff183447de8ae5afa2ee0ae7d5ee1ad6b25c4868c2"],
            "data": "0x" + word_u256(mask0),
            "blockNumber": hex(22),
            "transactionHash": "0xbb2",
            "logIndex": hex(0),
        }
        apply_log(self.conn, self.FACTORY, self.FACTORY_V2, resolve_log)
        self.conn.commit()
        win = self.conn.execute(
            "SELECT winning_outcome FROM wager_totals WHERE wager_address = ?", (maddr,)
        ).fetchone()
        self.assertEqual(win["winning_outcome"], str(mask0))

    def test_wager_created_v2_ignored_unless_emitter_is_factory_v2(self):
        """WagerCreatedV2 logs must not index when the log address is not the configured v2 factory."""
        log = self._wager_created_v2_log()
        log["address"] = self.FACTORY  # v1 factory address — wrong emitter
        apply_log(self.conn, self.FACTORY, self.FACTORY_V2, log)
        self.conn.commit()
        row = self.conn.execute(
            "SELECT 1 FROM wagers WHERE wager_address = ?", (self.WAGER.lower(),)
        ).fetchone()
        self.assertIsNone(row)

    def test_v2_resolved_single_topic_reads_mask_from_data(self):
        """v2 Resolved(uint256) is non-indexed: only the event topic hash + data word."""
        apply_log(self.conn, self.FACTORY, self.FACTORY_V2, self._wager_created_v2_log())
        self.conn.commit()
        maddr = self.WAGER.lower()
        resolve_log = {
            "address": self.WAGER,
            "topics": ["0x148a25ee2a7671350ab878ff183447de8ae5afa2ee0ae7d5ee1ad6b25c4868c2"],
            "data": "0x" + word_u256(6),
            "blockNumber": hex(30),
            "transactionHash": "0xcc0",
            "logIndex": hex(0),
        }
        apply_log(self.conn, self.FACTORY, self.FACTORY_V2, resolve_log)
        self.conn.commit()
        win = self.conn.execute(
            "SELECT winning_outcome FROM wager_totals WHERE wager_address = ?", (maddr,)
        ).fetchone()
        self.assertEqual(win["winning_outcome"], "6")

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
            "address": self.FACTORY_FF,
            "topics": [
                TOPICS["WagerCreatedFreeform"],
                topic_addr(self.WAGER),
                topic_addr(self.PROPOSER),
                topic_addr(self.RESOLVER),
            ],
            "data": data,
            "blockNumber": hex(40),
            "transactionHash": "0xff0",
            "logIndex": hex(0),
        }

    def test_wager_created_freeform_sets_protocol_version(self):
        apply_log(self.conn, self.FACTORY, self.FACTORY_V2, self._wager_created_freeform_log(), factory_freeform=self.FACTORY_FF)
        self.conn.commit()
        maddr = self.WAGER.lower()
        row = self.conn.execute("SELECT protocol_version, factory_address FROM wagers WHERE wager_address = ?", (maddr,)).fetchone()
        self.assertEqual(row["protocol_version"], "freeform")
        self.assertEqual(row["factory_address"].lower(), self.FACTORY_FF.lower())

    def test_bet_placed_freeform_updates_ticket_pool(self):
        apply_log(self.conn, self.FACTORY, self.FACTORY_V2, self._wager_created_freeform_log(), factory_freeform=self.FACTORY_FF)
        self.conn.commit()
        maddr = self.WAGER.lower()
        aid_topic = "0x" + word_u256(0xABCD)
        bet_log = {
            "address": self.WAGER,
            "topics": [
                TOPICS["BetPlacedFreeform"],
                topic_addr(self.BETTOR),
                aid_topic,
            ],
            "data": "0x" + word_u256(250),
            "blockNumber": hex(41),
            "transactionHash": "0xff1",
            "logIndex": hex(0),
        }
        apply_log(self.conn, self.FACTORY, self.FACTORY_V2, bet_log, factory_freeform=self.FACTORY_FF)
        self.conn.commit()
        pool = self.conn.execute(
            "SELECT pool_total FROM wager_ticket_pools WHERE wager_address = ? AND ticket_mask = ?",
            (maddr, aid_topic.lower()),
        ).fetchone()
        self.assertEqual(int(pool["pool_total"]), 250)

    def test_resolved_freeform_sets_winning_outcome_hex(self):
        apply_log(self.conn, self.FACTORY, self.FACTORY_V2, self._wager_created_freeform_log(), factory_freeform=self.FACTORY_FF)
        self.conn.commit()
        maddr = self.WAGER.lower()
        win_topic = "0x" + word_u256(0xDEAD)
        res_log = {
            "address": self.WAGER,
            "topics": [TOPICS["ResolvedFreeform"], win_topic],
            "data": "0x",
            "blockNumber": hex(42),
            "transactionHash": "0xff2",
            "logIndex": hex(0),
        }
        apply_log(self.conn, self.FACTORY, self.FACTORY_V2, res_log, factory_freeform=self.FACTORY_FF)
        self.conn.commit()
        win = self.conn.execute(
            "SELECT winning_outcome FROM wager_totals WHERE wager_address = ?", (maddr,)
        ).fetchone()
        self.assertEqual(win["winning_outcome"], win_topic.lower())

    def _wager_created_v3_enum_log(self):
        data = (
            "0x"
            + word_addr(self.TOKEN)
            + word_u256(0)  # payoff policy uint8 in low byte
            + word_u256(0)  # policyParam
            + word_u256(2_000)
            + word_u256(3_000)
            + word_u256(5_000)
            + word_addr(self.BETTING_CLOSER)
            + word_addr(self.RESOLUTION_CLOSER)
        )
        return {
            "address": self.FACTORY_V3,
            "topics": [
                TOPICS["WagerCreatedV3Enumerated"],
                topic_addr(self.WAGER),
                topic_addr(self.PROPOSER),
                topic_addr(self.RESOLVER),
            ],
            "data": data,
            "blockNumber": hex(50),
            "transactionHash": "0x330",
            "logIndex": hex(0),
        }

    def test_wager_created_v3_enum_sets_protocol_and_factory(self):
        apply_log(
            self.conn,
            self.FACTORY,
            self.FACTORY_V2,
            self._wager_created_v3_enum_log(),
            factory_v3=self.FACTORY_V3,
        )
        self.conn.commit()
        maddr = self.WAGER.lower()
        row = self.conn.execute("SELECT protocol_version, factory_address FROM wagers WHERE wager_address = ?", (maddr,)).fetchone()
        self.assertEqual(row["protocol_version"], "v3_enum")
        self.assertEqual(row["factory_address"].lower(), self.FACTORY_V3.lower())

    def test_bet_placed_v3_enum_updates_ticket_pool(self):
        apply_log(
            self.conn,
            self.FACTORY,
            self.FACTORY_V2,
            self._wager_created_v3_enum_log(),
            factory_v3=self.FACTORY_V3,
        )
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
            "blockNumber": hex(51),
            "transactionHash": "0x331",
            "logIndex": hex(0),
        }
        apply_log(self.conn, self.FACTORY, self.FACTORY_V2, bet_log, factory_v3=self.FACTORY_V3)
        self.conn.commit()
        pool = self.conn.execute(
            "SELECT pool_total FROM wager_ticket_pools WHERE wager_address = ? AND ticket_mask = ?",
            (maddr, str(mask0)),
        ).fetchone()
        self.assertEqual(int(pool["pool_total"]), 77)

    def test_resolved_v3_enumerated_sets_winning_mask(self):
        apply_log(
            self.conn,
            self.FACTORY,
            self.FACTORY_V2,
            self._wager_created_v3_enum_log(),
            factory_v3=self.FACTORY_V3,
        )
        self.conn.commit()
        maddr = self.WAGER.lower()
        res_log = {
            "address": self.WAGER,
            "topics": [TOPICS["ResolvedV3Enumerated"]],
            "data": "0x" + word_u256(8),
            "blockNumber": hex(52),
            "transactionHash": "0x332",
            "logIndex": hex(0),
        }
        apply_log(self.conn, self.FACTORY, self.FACTORY_V2, res_log, factory_v3=self.FACTORY_V3)
        self.conn.commit()
        win = self.conn.execute(
            "SELECT winning_outcome FROM wager_totals WHERE wager_address = ?", (maddr,)
        ).fetchone()
        self.assertEqual(win["winning_outcome"], "8")

    def _wager_created_v3_freeform_log(self):
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
            "address": self.FACTORY_V3,
            "topics": [
                TOPICS["WagerCreatedV3Freeform"],
                topic_addr(self.WAGER),
                topic_addr(self.PROPOSER),
                topic_addr(self.RESOLVER),
            ],
            "data": data,
            "blockNumber": hex(60),
            "transactionHash": "0x440",
            "logIndex": hex(0),
        }

    def test_wager_created_v3_freeform_and_bet_updates_pool(self):
        apply_log(
            self.conn,
            self.FACTORY,
            self.FACTORY_V2,
            self._wager_created_v3_freeform_log(),
            factory_v3=self.FACTORY_V3,
        )
        self.conn.commit()
        maddr = self.WAGER.lower()
        row = self.conn.execute("SELECT protocol_version FROM wagers WHERE wager_address = ?", (maddr,)).fetchone()
        self.assertEqual(row["protocol_version"], "v3_freeform")
        aid_topic = "0x" + word_u256(0xC0DE)
        bet_log = {
            "address": self.WAGER,
            "topics": [
                TOPICS["BetPlacedV3Freeform"],
                topic_addr(self.BETTOR),
                aid_topic,
            ],
            "data": "0x" + word_u256(99),
            "blockNumber": hex(61),
            "transactionHash": "0x441",
            "logIndex": hex(0),
        }
        apply_log(self.conn, self.FACTORY, self.FACTORY_V2, bet_log, factory_v3=self.FACTORY_V3)
        self.conn.commit()
        pool = self.conn.execute(
            "SELECT pool_total FROM wager_ticket_pools WHERE wager_address = ? AND ticket_mask = ?",
            (maddr, aid_topic.lower()),
        ).fetchone()
        self.assertEqual(int(pool["pool_total"]), 99)


if __name__ == "__main__":
    unittest.main()

