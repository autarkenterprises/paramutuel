import unittest

from agents.paramutuel_bettor import odds


class TestOdds(unittest.TestCase):
    def test_compute_basic(self) -> None:
        r = odds.compute_odds(total_pot=1000, outcome_total=400, total_fee_bps=100, bet_amount=100)
        self.assertEqual(r["total_pot_after"], 1100)
        self.assertIsNotNone(r["post_bet_payout_multiple"])

    def test_betting_closed_by_time(self) -> None:
        open_ok, hint = odds.betting_open_status(
            {"state": "OPEN", "betting_closed_by_authority": 0, "betting_close_time": 100},
            now_ts=200,
        )
        self.assertFalse(open_ok)
        self.assertIn("close", hint)


if __name__ == "__main__":
    unittest.main()
