"""Outcome-count cap in metadata fetch mirrors on-chain `MAX_OUTCOMES`."""

import unittest

from service.indexer.indexer import MAX_WAGER_OUTCOMES


class OutcomeCapTests(unittest.TestCase):
    def test_MAX_WAGER_OUTCOMES_matches_protocol(self):
        self.assertEqual(MAX_WAGER_OUTCOMES, 255)

    @unittest.expectedFailure
    def test_XFAIL_DEPRECATED_MAX_WAGER_OUTCOMES_was_64(self):
        """Indexer metadata loop used `min(count, 64)` before the cap was raised."""
        self.assertEqual(MAX_WAGER_OUTCOMES, 64)


if __name__ == "__main__":
    unittest.main()
