import sqlite3
import unittest

from service.indexer.indexer import apply_log, get_expire_candidates, init_db


def topic_addr(addr: str) -> str:
    return "0x" + ("0" * 24) + addr.lower().replace("0x", "")


def word_u256(v: int) -> str:
    return f"{v:064x}"


def word_addr(addr: str) -> str:
    return ("0" * 24) + addr.lower().replace("0x", "")


class IndexerStateTests(unittest.TestCase):
    FACTORY = "0xfac7000000000000000000000000000000000001"
    MARKET = "0xabc1000000000000000000000000000000000001"
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

    def _market_created_log(self):
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
                "0x142b571a3c036b6753710f2ec81868c8ee6e9b3fffc642f94783cf8778ea7388",
                topic_addr(self.MARKET),
                topic_addr(self.PROPOSER),
                topic_addr(self.RESOLVER),
            ],
            "data": data,
            "blockNumber": hex(10),
            "transactionHash": "0xaaa",
            "logIndex": hex(0),
        }

    def test_market_created_and_state_progression(self):
        apply_log(self.conn, self.FACTORY, self._market_created_log())
        self.conn.commit()

        maddr = self.MARKET.lower()
        row = self.conn.execute("SELECT * FROM markets WHERE market_address = ?", (maddr,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["state"], "OPEN")
        self.assertEqual(row["betting_closer"].lower(), self.BETTING_CLOSER.lower())
        self.assertEqual(row["resolution_closer"].lower(), self.RESOLUTION_CLOSER.lower())
        self.assertEqual(int(row["resolution_window"]), 3000)

        # BetPlaced: bettor, outcomeIndex=1, amount=100
        bet_log = {
            "address": self.MARKET,
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
        apply_log(self.conn, self.FACTORY, bet_log)
        self.conn.commit()

        totals = self.conn.execute("SELECT total_pot FROM market_totals WHERE market_address = ?", (maddr,)).fetchone()
        self.assertEqual(int(totals["total_pot"]), 100)

        # Resolve outcome 1
        resolve_log = {
            "address": self.MARKET,
            "topics": [
                "0x148a25ee2a7671350ab878ff183447de8ae5afa2ee0ae7d5ee1ad6b25c4868c2",
                "0x" + ("0" * 63) + "1",
            ],
            "data": "0x",
            "blockNumber": hex(12),
            "transactionHash": "0xaac",
            "logIndex": hex(0),
        }
        apply_log(self.conn, self.FACTORY, resolve_log)
        self.conn.commit()

        row2 = self.conn.execute("SELECT state FROM markets WHERE market_address = ?", (maddr,)).fetchone()
        self.assertEqual(row2["state"], "RESOLVED")

    def test_expire_candidates(self):
        apply_log(self.conn, self.FACTORY, self._market_created_log())
        self.conn.commit()

        # now_ts beyond resolution deadline (5000)
        cands = get_expire_candidates(self.conn, now_ts=6000)
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0]["market_address"], self.MARKET.lower())

        # Retract event should remove candidate
        retract_log = {
            "address": self.MARKET,
            "topics": ["0x6c8d8af1eb7d9e8ea2f489b8d39cc78f924042413d0e15ce70f8cdb53afab46a"],
            "data": "0x",
            "blockNumber": hex(13),
            "transactionHash": "0xaad",
            "logIndex": hex(0),
        }
        apply_log(self.conn, self.FACTORY, retract_log)
        self.conn.commit()
        cands2 = get_expire_candidates(self.conn, now_ts=6000)
        self.assertEqual(len(cands2), 0)

    def test_expire_candidates_when_resolution_window_closed_early(self):
        apply_log(self.conn, self.FACTORY, self._market_created_log())
        self.conn.commit()
        maddr = self.MARKET.lower()

        # Before on-chain deadline (5000), but resolution window closed by authority
        close_log = {
            "address": self.MARKET,
            "topics": ["0x3a016249126bba7044eec394afa8eba111d1ea6bda5a42b663f7d86944fd1f87"],
            "data": "0x" + word_u256(2500),
            "blockNumber": hex(11),
            "transactionHash": "0xaae",
            "logIndex": hex(0),
        }
        apply_log(self.conn, self.FACTORY, close_log)
        self.conn.commit()

        cands = get_expire_candidates(self.conn, now_ts=3000)
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0]["market_address"], maddr)

    def test_no_max_resolution_window_needs_authority_close(self):
        # Create market with no max windows: close_time=0, resolution_window=0, resolution_deadline=0
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
                "0x142b571a3c036b6753710f2ec81868c8ee6e9b3fffc642f94783cf8778ea7388",
                topic_addr(self.MARKET),
                topic_addr(self.PROPOSER),
                topic_addr(self.RESOLVER),
            ],
            "data": data,
            "blockNumber": hex(10),
            "transactionHash": "0xbbb",
            "logIndex": hex(0),
        }
        apply_log(self.conn, self.FACTORY, create_log)
        self.conn.commit()

        self.assertEqual(len(get_expire_candidates(self.conn, now_ts=999999)), 0)

        # Once resolution window is closed by authority, it becomes expire-eligible immediately.
        close_log = {
            "address": self.MARKET,
            "topics": ["0x3a016249126bba7044eec394afa8eba111d1ea6bda5a42b663f7d86944fd1f87"],
            "data": "0x" + word_u256(999000),
            "blockNumber": hex(11),
            "transactionHash": "0xbbc",
            "logIndex": hex(0),
        }
        apply_log(self.conn, self.FACTORY, close_log)
        self.conn.commit()
        self.assertEqual(len(get_expire_candidates(self.conn, now_ts=999999)), 1)


if __name__ == "__main__":
    unittest.main()

