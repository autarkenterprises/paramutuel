import unittest

from agents.paramutuel_bettor import planner


class _FakeIndexer:
    base_url = "http://fixture"

    def __init__(self, detail: dict) -> None:
        self._detail = detail

    def get_wager(self, wager_address: str) -> dict:
        return self._detail


class TestPlannerQuoteV2(unittest.TestCase):
    def test_quote_wager_v2_reads_ticket_pool_not_outcomes_table(self) -> None:
        detail = {
            "wager": {
                "state": "OPEN",
                "protocol_version": "v2",
                "collateral_token": "0x036CbD53842c5426634e7929541eC2318f3dCf7e",
                "betting_closed_by_authority": 0,
                "betting_close_time": 9_999_999_999,
            },
            "totals": {"total_pot": "5000", "total_fee_bps": "0"},
            "outcomes": [],
            "ticket_pools": [{"ticket_mask": "2", "pool_total": "400"}],
        }
        client = _FakeIndexer(detail)
        q = planner.quote_wager(
            client,
            wager_address="0x" + "aa" * 20,
            outcome_index=1,
            bet_amount_raw=100,
        )
        self.assertEqual(q["outcome_total_raw"], 400)
        self.assertEqual(q["quote"].get("ticket_mask"), 2)

    def test_quote_wager_freeform_sorts_pools_by_answer_id(self) -> None:
        detail = {
            "wager": {
                "state": "OPEN",
                "protocol_version": "freeform",
                "collateral_token": "0x036CbD53842c5426634e7929541eC2318f3dCf7e",
                "betting_closed_by_authority": 0,
                "betting_close_time": 9_999_999_999,
            },
            "totals": {"total_pot": "1000", "total_fee_bps": "0"},
            "outcomes": [],
            "ticket_pools": [
                {"ticket_mask": "0xbb", "pool_total": "200"},
                {"ticket_mask": "0xaa", "pool_total": "100"},
            ],
        }
        client = _FakeIndexer(detail)
        q = planner.quote_wager(
            client,
            wager_address="0x" + "cc" * 20,
            outcome_index=0,
            bet_amount_raw=50,
        )
        self.assertEqual(q["outcome_total_raw"], 100)
        self.assertEqual(q["answer_id_hex"], "0xaa")

    def test_quote_wager_v1_requires_outcome_row(self) -> None:
        detail = {
            "wager": {
                "state": "OPEN",
                "protocol_version": "v1",
                "collateral_token": "0x036CbD53842c5426634e7929541eC2318f3dCf7e",
                "betting_closed_by_authority": 0,
                "betting_close_time": 9_999_999_999,
            },
            "totals": {"total_pot": "1000", "total_fee_bps": "0"},
            "outcomes": [{"outcome_index": 0, "outcome_total": "900"}],
            "ticket_pools": [],
        }
        client = _FakeIndexer(detail)
        with self.assertRaises(ValueError):
            planner.quote_wager(
                client,
                wager_address="0x" + "bb" * 20,
                outcome_index=1,
                bet_amount_raw=10,
            )


if __name__ == "__main__":
    unittest.main()
