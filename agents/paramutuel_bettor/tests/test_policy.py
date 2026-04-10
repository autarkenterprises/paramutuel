import unittest

from agents.paramutuel_bettor import policy


class TestPolicy(unittest.TestCase):
    def test_pick_best_post_multiple(self) -> None:
        detail = {
            "wager": {
                "state": "OPEN",
                "betting_closed_by_authority": 0,
                "betting_close_time": 9_999_999_999,
            },
            "totals": {"total_pot": "1000", "total_fee_bps": "0"},
            "outcomes": [
                {"outcome_index": 0, "outcome_total": "900"},
                {"outcome_index": 1, "outcome_total": "100"},
            ],
        }
        r = policy.pick_outcome(strategy="best_post_multiple", wager_detail=detail, bet_amount=100)
        self.assertEqual(r["outcome_index"], 1)

    def test_pick_min_liquidity(self) -> None:
        detail = {
            "wager": {
                "state": "OPEN",
                "betting_closed_by_authority": 0,
                "betting_close_time": 9_999_999_999,
            },
            "totals": {"total_pot": "1000", "total_fee_bps": "0"},
            "outcomes": [
                {"outcome_index": 0, "outcome_total": "900"},
                {"outcome_index": 1, "outcome_total": "100"},
            ],
        }
        r = policy.pick_outcome(strategy="min_liquidity", wager_detail=detail, bet_amount=50)
        self.assertEqual(r["outcome_index"], 1)

    def test_pick_v2_uses_ticket_pools(self) -> None:
        detail = {
            "wager": {
                "state": "OPEN",
                "protocol_version": "v2",
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

    def test_pick_v2_empty_outcomes_raises(self) -> None:
        detail = {
            "wager": {
                "state": "OPEN",
                "protocol_version": "v2",
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


if __name__ == "__main__":
    unittest.main()
