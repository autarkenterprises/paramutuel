import unittest

from service.resolution.logic import actionability_reason, betting_is_closed, resolution_window_is_over
from service.resolution.service import evaluate_candidates


class ResolutionLogicTests(unittest.TestCase):
    def test_betting_closed_by_time(self) -> None:
        wager = {"betting_closed_by_authority": 0, "betting_close_time": 100}
        self.assertFalse(betting_is_closed(wager, now_ts=99))
        self.assertTrue(betting_is_closed(wager, now_ts=100))

    def test_resolution_window_over(self) -> None:
        wager = {
            "resolution_window_closed": 0,
            "resolution_window": 3600,
            "betting_closed_at": 1000,
            "betting_close_time": 0,
        }
        self.assertFalse(resolution_window_is_over(wager, now_ts=4600))
        self.assertTrue(resolution_window_is_over(wager, now_ts=4601))

    def test_actionability_reason(self) -> None:
        wager = {
            "wager_address": "0xabc1000000000000000000000000000000000001",
            "state": "OPEN",
            "resolver": "0xabc3000000000000000000000000000000000003",
            "betting_closed_by_authority": 1,
            "betting_close_time": 0,
            "resolution_window": 0,
            "resolution_window_closed": 0,
        }
        resolver = "0xabc3000000000000000000000000000000000003"
        self.assertIsNone(actionability_reason(wager, resolver_address=resolver, now_ts=1))
        self.assertEqual(
            actionability_reason(wager, resolver_address="0xabc4000000000000000000000000000000000004", now_ts=1),
            "resolver mismatch",
        )

    def test_evaluate_candidates_marks_actionable(self) -> None:
        resolver = "0xabc3000000000000000000000000000000000003"
        open_wagers = [
            {
                "wager_address": "0xabc1000000000000000000000000000000000001",
                "state": "OPEN",
                "resolver": resolver,
                "betting_closed_by_authority": 1,
                "betting_close_time": 0,
                "resolution_window": 0,
                "resolution_window_closed": 0,
            },
            {
                "wager_address": "0xabc1000000000000000000000000000000000002",
                "state": "OPEN",
                "resolver": resolver,
                "betting_closed_by_authority": 0,
                "betting_close_time": 999999,
                "resolution_window": 3600,
                "resolution_window_closed": 0,
            },
        ]
        decisions = {
            "0xabc1000000000000000000000000000000000001": {"action": "resolve", "outcomeIndex": 1}
        }
        rows = evaluate_candidates(
            open_wagers=open_wagers,
            decisions=decisions,
            resolver_address=resolver,
            now_ts=1000,
        )
        actionable = [r for r in rows if r.get("actionable")]
        self.assertEqual(len(actionable), 1)
        self.assertEqual(actionable[0]["wager_address"], "0xabc1000000000000000000000000000000000001")


if __name__ == "__main__":
    unittest.main()
