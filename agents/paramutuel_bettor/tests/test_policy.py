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


if __name__ == "__main__":
    unittest.main()
