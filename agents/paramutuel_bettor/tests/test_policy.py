import unittest

from agents.paramutuel_bettor import policy


class TestPolicy(unittest.TestCase):
    """Strategy picker tests against the unified V3 wager payload.

    ADR-0010 removed the legacy v1 "outcomes table" code path — the
    picker now reads only `ticket_pools` for both enumerated and
    freeform modes.  Each test here maintains parity with the
    pre-migration behaviour: best-post-multiple still picks the
    smallest-pool outcome; min-liquidity still targets the minimum
    outcome total.
    """

    def _enumerated_three_outcome_detail(self) -> dict:
        return {
            "wager": {
                "protocol_version": "enumerated",
                "state": "OPEN",
                "betting_closed_by_authority": 0,
                "betting_close_time": 9_999_999_999,
                "outcomes_json": '["A","B","C"]',
            },
            "totals": {"total_pot": "1000", "total_fee_bps": "0"},
            "outcomes": [],
            "ticket_pools": [
                {"ticket_mask": "1", "pool_total": "900"},
                {"ticket_mask": "2", "pool_total": "800"},
                {"ticket_mask": "4", "pool_total": "100"},
            ],
        }

    def test_pick_best_post_multiple_picks_smallest_pool(self) -> None:
        r = policy.pick_outcome(
            strategy="best_post_multiple",
            wager_detail=self._enumerated_three_outcome_detail(),
            bet_amount=100,
        )
        self.assertEqual(r["outcome_index"], 2)
        self.assertEqual(r["per_outcome"][2]["ticket_mask"], 4)

    def test_pick_min_liquidity_picks_smallest_pool(self) -> None:
        r = policy.pick_outcome(
            strategy="min_liquidity",
            wager_detail=self._enumerated_three_outcome_detail(),
            bet_amount=50,
        )
        self.assertEqual(r["outcome_index"], 2)

    def test_pick_enumerated_default_protocol_version(self) -> None:
        # With no `protocol_version` set, the picker defaults to
        # enumerated and reads ticket pools keyed by single-bit masks.
        detail = {
            "wager": {
                "state": "OPEN",
                "outcomes_json": '["A","B"]',
                "betting_closed_by_authority": 0,
                "betting_close_time": 9_999_999_999,
            },
            "totals": {"total_pot": "1000", "total_fee_bps": "0"},
            "outcomes": [],
            "ticket_pools": [
                {"ticket_mask": "1", "pool_total": "900"},
                {"ticket_mask": "2", "pool_total": "100"},
            ],
        }
        r = policy.pick_outcome(strategy="best_post_multiple", wager_detail=detail, bet_amount=100)
        self.assertEqual(r["outcome_index"], 1)
        self.assertEqual(r["per_outcome"][1]["ticket_mask"], 2)

    def test_pick_freeform_uses_sorted_ticket_pools(self) -> None:
        detail = {
            "wager": {
                "state": "OPEN",
                "protocol_version": "freeform",
                "betting_closed_by_authority": 0,
                "betting_close_time": 9_999_999_999,
            },
            "totals": {"total_pot": "1000", "total_fee_bps": "0"},
            "outcomes": [],
            "ticket_pools": [
                {"ticket_mask": "0xbbbb", "pool_total": "100"},
                {"ticket_mask": "0xaaaa", "pool_total": "900"},
            ],
        }
        r = policy.pick_outcome(strategy="best_post_multiple", wager_detail=detail, bet_amount=100)
        # Sorted by ticket_mask: 0xaaaa then 0xbbbb; smaller pool → higher post-bet multiple.
        self.assertEqual(r["outcome_index"], 1)
        self.assertEqual(r["answer_id_hex"], "0xbbbb")
        self.assertIn("freeform_note", r)

    def test_pick_enumerated_empty_outcomes_raises(self) -> None:
        detail = {
            "wager": {
                "state": "OPEN",
                "protocol_version": "enumerated",
                "outcomes_json": "[]",
                "betting_closed_by_authority": 0,
                "betting_close_time": 9_999_999_999,
            },
            "totals": {"total_pot": "0", "total_fee_bps": "0"},
            "outcomes": [],
            "ticket_pools": [],
        }
        with self.assertRaises(ValueError):
            policy.pick_outcome(strategy="best_post_multiple", wager_detail=detail, bet_amount=1)

    def test_pick_unknown_strategy_raises(self) -> None:
        # Parity check for the strategy-name guard — previously only
        # implicitly covered via the v1 path.
        with self.assertRaises(ValueError):
            policy.pick_outcome(
                strategy="does-not-exist",
                wager_detail=self._enumerated_three_outcome_detail(),
                bet_amount=100,
            )


if __name__ == "__main__":
    unittest.main()
