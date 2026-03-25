import unittest

from service.explorer.logic import can_expire_candidate_row, classify_market_state


class ExplorerLogicTests(unittest.TestCase):
    def test_state_classification(self):
        self.assertEqual(classify_market_state({"state": "OPEN"}), "open")
        self.assertEqual(classify_market_state({"state": "RESOLVED"}), "resolved")
        self.assertEqual(classify_market_state({"state": "RETRACTED"}), "retracted")

    def test_can_expire_for_closed_resolution_window(self):
        row = {"resolution_window_closed": 1, "resolution_window": 0}
        self.assertTrue(can_expire_candidate_row(row, 1))

    def test_can_expire_for_finite_timeout(self):
        row = {"resolution_window_closed": 0, "resolution_window": 3600, "betting_closed_at": 1000}
        self.assertFalse(can_expire_candidate_row(row, 4500))
        self.assertTrue(can_expire_candidate_row(row, 4601))

    def test_no_max_resolution_not_expirable_by_time(self):
        row = {"resolution_window_closed": 0, "resolution_window": 0, "betting_close_time": 1000}
        self.assertFalse(can_expire_candidate_row(row, 999999))


if __name__ == "__main__":
    unittest.main()
