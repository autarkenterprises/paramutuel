"""ADR-0021 U1: a freeform quote describes the answer it was given, not whatever row sits at an index.

`quote_wager` took the odds from `ticket_pools[outcome_index]` (sorted by answer id) but built the
calldata from `freeform_answer`, so the two could describe different answers. The index also moved
whenever a new answer id sorted before it, and since ADR-0020 the indexer lists only the 500 largest
pools, so an answer outside them was quoted as unstaked: a hugely overstated payout.
"""
import os
import unittest

from eth_hash.auto import keccak as reference_keccak

from agents.paramutuel_bettor import calldata, keccak, planner
from agents.paramutuel_bettor.indexer_client import IndexerClient

ADDR = "0x" + "ab" * 20
ANSWER = "Paris"
ANSWER_ID = "0x" + reference_keccak(b"\x03" + ANSWER.encode()).hex()


class KeccakTests(unittest.TestCase):
    """The package is stdlib-only, and hashlib's sha3_256 is not Ethereum's Keccak-256."""

    def test_known_vectors(self):
        self.assertEqual(keccak.keccak256(b"").hex(), "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470")
        self.assertEqual(keccak.keccak256(b"abc").hex(), "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45")

    def test_matches_the_reference_at_every_padding_boundary(self):
        """The rate is 136 bytes; 135, 136 and 137 take the three padding paths."""
        for length in list(range(0, 300)) + [1_000, 4_096]:
            data = os.urandom(length)
            with self.subTest(length=length):
                self.assertEqual(keccak.keccak256(data), reference_keccak(data))

    def test_answer_id_matches_the_contract_domain(self):
        for answer in (ANSWER, " Paris ", "café ☕", ""):
            with self.subTest(answer=answer):
                expected = "0x" + reference_keccak(b"\x03" + answer.encode("utf-8")).hex()
                self.assertEqual(calldata.freeform_answer_id_hex(answer), expected)


class FakeIndexer:
    """Mimics `/wagers/{addr}`: the 500 largest pools, or one answer's pool with `answer_id`."""

    def __init__(self, listed, everything):
        self.listed, self.everything = listed, everything
        self.calls = []

    def detail(self, pools):
        return {
            "wager": {"protocol_version": "freeform", "state": "OPEN", "betting_close_time": 9_999_999_999, "collateral_token": "0x" + "cc" * 20},
            "totals": {"total_pot": "100000", "total_fee_bps": "0"},
            "outcomes": [],
            "ticket_pools": pools,
        }

    def get_wager(self, wager_address, answer_id=None):
        self.calls.append(answer_id)
        if answer_id:
            return self.detail([p for p in self.everything if p["ticket_mask"] == answer_id])
        return self.detail(self.listed)


class QuoteTests(unittest.TestCase):
    def setUp(self):
        self.ours = {"ticket_mask": ANSWER_ID, "pool_total": "40000"}
        # The listing holds other answers only: ours is staked, but outside the largest pools.
        self.others = [{"ticket_mask": "0x" + f"{i:02x}" * 32, "pool_total": str(40_000 + 10_000 * i)} for i in (1, 2)]
        self.indexer = FakeIndexer(self.others, self.others + [self.ours])

    def quote(self, outcome_index=0, answer=ANSWER):
        return planner.quote_wager(
            self.indexer, wager_address=ADDR, outcome_index=outcome_index, bet_amount_raw=1_000, freeform_answer=answer
        )

    def test_odds_are_for_the_answer_being_bet(self):
        out = self.quote()
        self.assertEqual(out["outcome_total_raw"], 40_000)
        self.assertEqual(out["answer_id_hex"], ANSWER_ID)
        self.assertEqual(self.indexer.calls, [ANSWER_ID], "looked up by id, in one request")

    def test_the_index_cannot_point_the_odds_at_another_answer(self):
        self.assertEqual(self.quote(outcome_index=0)["outcome_total_raw"], self.quote(outcome_index=1)["outcome_total_raw"])

    def test_an_unstaked_answer_is_quoted_as_unstaked(self):
        out = self.quote(answer="Lyon")
        self.assertEqual(out["outcome_total_raw"], 0)
        self.assertEqual(out["answer_id_hex"], calldata.freeform_answer_id_hex("Lyon"))

    def test_without_an_answer_the_index_still_selects_a_listed_row(self):
        """There is no calldata without the answer text, so this stays an informational quote."""
        out = self.quote(outcome_index=1, answer=None)
        self.assertEqual(out["answer_id_hex"], self.others[1]["ticket_mask"])
        self.assertIsNone(out["quote"]["placeBet"]["calldata"])
        self.assertFalse(out["quote"]["execution_allowed"])


class ClientTests(unittest.TestCase):
    def test_get_wager_can_ask_for_one_answer(self):
        client = IndexerClient("http://indexer")
        seen = []
        client._get = lambda path: seen.append(path) or {}
        client.get_wager(ADDR.upper().replace("0X", "0x"), answer_id=ANSWER_ID)
        client.get_wager(ADDR)
        self.assertEqual(seen, [f"/wagers/{ADDR}?answer_id={ANSWER_ID}", f"/wagers/{ADDR}"])


if __name__ == "__main__":
    unittest.main()
