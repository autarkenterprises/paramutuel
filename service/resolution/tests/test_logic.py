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


class RemainingGateTests(unittest.TestCase):
    """Each of these decides whether the daemon may spend gas and the resolver's authority."""

    def test_clock_defaults_to_now(self) -> None:
        past = {"betting_closed_by_authority": 0, "betting_close_time": 100}
        self.assertTrue(betting_is_closed(past))
        over = {"resolution_window_closed": 0, "resolution_window": 10, "betting_closed_at": 100}
        self.assertTrue(resolution_window_is_over(over))

    def test_a_zero_close_time_is_open_until_an_authority_closes_it(self) -> None:
        self.assertFalse(betting_is_closed({"betting_closed_by_authority": 0, "betting_close_time": 0}, now_ts=10**12))
        self.assertTrue(betting_is_closed({"betting_closed_by_authority": 1, "betting_close_time": 0}, now_ts=1))

    def test_an_authority_closed_window_is_over_whatever_the_clock_says(self) -> None:
        self.assertTrue(resolution_window_is_over({"resolution_window_closed": 1, "resolution_window": 0}, now_ts=0))

    def test_no_window_never_ends_by_itself(self) -> None:
        wager = {"resolution_window_closed": 0, "resolution_window": 0, "betting_closed_at": 1}
        self.assertFalse(resolution_window_is_over(wager, now_ts=10**12))

    def test_window_runs_from_the_scheduled_close_when_never_closed_early(self) -> None:
        wager = {"resolution_window_closed": 0, "resolution_window": 10, "betting_closed_at": None, "betting_close_time": 100}
        self.assertFalse(resolution_window_is_over(wager, now_ts=110), "the last moment is still inside")
        self.assertTrue(resolution_window_is_over(wager, now_ts=111))

    def test_window_with_no_start_cannot_be_over(self) -> None:
        """Zero close time and not yet closed: the window has not begun."""
        wager = {"resolution_window_closed": 0, "resolution_window": 10, "betting_closed_at": None, "betting_close_time": 0}
        self.assertFalse(resolution_window_is_over(wager, now_ts=10**12))

    def test_reasons_name_the_blocker(self) -> None:
        base = {
            "state": "OPEN",
            "resolver": "0xabc",
            "betting_closed_by_authority": 1,
            "resolution_window_closed": 0,
            "resolution_window": 0,
        }
        self.assertIsNone(actionability_reason(base, resolver_address="0xABC", now_ts=1), "addresses compare case-insensitively")
        self.assertEqual(actionability_reason({**base, "state": "RESOLVED"}, resolver_address="0xabc", now_ts=1), "wager not OPEN")
        self.assertEqual(actionability_reason(base, resolver_address="0xdef", now_ts=1), "resolver mismatch")
        self.assertEqual(
            actionability_reason({**base, "betting_closed_by_authority": 0, "betting_close_time": 0}, resolver_address="0xabc", now_ts=1),
            "betting still open",
        )
        self.assertEqual(
            actionability_reason({**base, "resolution_window_closed": 1}, resolver_address="0xabc", now_ts=1),
            "resolution window over (use expire)",
        )


if __name__ == "__main__":
    unittest.main()
