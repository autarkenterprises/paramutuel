import unittest

from agents.paramutuel_bettor import planner


class _FakeIndexer:
    base_url = "http://fixture"

    def __init__(self, detail: dict) -> None:
        self._detail = detail

    def get_wager(self, wager_address: str) -> dict:
        return self._detail


class TestPlannerQuoteV3(unittest.TestCase):
    """Planner quotes against the ADR-0010 V3 indexer shape.

    V3 collapses `protocol_version` to `enumerated` (ticket-pool bitmasks
    keyed by `1 << outcome_index`) or `freeform` (ticket pools keyed by
    lowercased `answerId` hex; planner sorts them to make `outcome_index`
    a stable row selector).
    """

    def test_quote_wager_enumerated_reads_ticket_pool_by_mask(self) -> None:
        detail = {
            "wager": {
                "state": "OPEN",
                "protocol_version": "enumerated",
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

    def test_quote_wager_enumerated_missing_mask_uses_zero_pool(self) -> None:
        # Parity with the legacy `v2` path: selecting an outcome that has
        # no seeded ticket pool surfaces `outcome_total_raw == 0` rather
        # than raising, so the quote still returns calldata.
        detail = {
            "wager": {
                "state": "OPEN",
                "protocol_version": "enumerated",
                "collateral_token": "0x036CbD53842c5426634e7929541eC2318f3dCf7e",
                "betting_closed_by_authority": 0,
                "betting_close_time": 9_999_999_999,
            },
            "totals": {"total_pot": "500", "total_fee_bps": "0"},
            "outcomes": [],
            "ticket_pools": [{"ticket_mask": "1", "pool_total": "500"}],
        }
        client = _FakeIndexer(detail)
        q = planner.quote_wager(
            client,
            wager_address="0x" + "dd" * 20,
            outcome_index=2,
            bet_amount_raw=10,
        )
        self.assertEqual(q["outcome_total_raw"], 0)
        self.assertEqual(q["quote"].get("ticket_mask"), 4)

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
        self.assertEqual(q["quote"]["protocol_version"], "freeform")

    def test_quote_wager_freeform_answer_feeds_placeBet_string(self) -> None:
        detail = {
            "wager": {
                "protocol_version": "freeform",
                "collateral_token": "0x036CbD53842c5426634e7929541eC2318f3dCf7e",
                "state": "OPEN",
                "betting_close_time": 9_999_999_999,
            },
            "totals": {"total_pot": "500", "total_fee_bps": "0"},
            "outcomes": [],
            "ticket_pools": [
                {"ticket_mask": "0xbb", "pool_total": "100"},
                {"ticket_mask": "0xaa", "pool_total": "200"},
            ],
        }
        out = planner.quote_wager(
            _FakeIndexer(detail),
            wager_address="0x" + "ab" * 20,
            outcome_index=0,
            bet_amount_raw=10,
            freeform_answer="hello",
        )
        self.assertEqual(out["answer_id_hex"], "0xaa")
        self.assertTrue(out["quote"]["freeform_answer_supplied"])

    def test_quote_wager_freeform_rejects_out_of_range_index(self) -> None:
        # Parity with the old v1 "requires outcome row" check: an
        # out-of-range outcome_index must raise rather than silently
        # returning a zero-pool quote.
        detail = {
            "wager": {
                "state": "OPEN",
                "protocol_version": "freeform",
                "collateral_token": "0x036CbD53842c5426634e7929541eC2318f3dCf7e",
                "betting_closed_by_authority": 0,
                "betting_close_time": 9_999_999_999,
            },
            "totals": {"total_pot": "100", "total_fee_bps": "0"},
            "outcomes": [],
            "ticket_pools": [{"ticket_mask": "0xaa", "pool_total": "100"}],
        }
        client = _FakeIndexer(detail)
        with self.assertRaises(ValueError):
            planner.quote_wager(
                client,
                wager_address="0x" + "bb" * 20,
                outcome_index=5,
                bet_amount_raw=10,
            )


class _FakeListingIndexer:
    """Indexer fake serving both the list scan and per-wager detail."""

    base_url = "http://fixture"

    def __init__(self, details: dict) -> None:
        self._details = details

    def list_wagers(self, *, state: str, limit: int, order: str) -> list:
        return [dict(d["wager"], wager_address=a) for a, d in self._details.items()]

    def get_wager(self, wager_address: str) -> dict:
        return self._details[wager_address]


def _enum_detail(*, close_time: int, policy: int = 0, authority_closed: int = 0) -> dict:
    return {
        "wager": {
            "state": "OPEN",
            "protocol_version": "enumerated",
            "payoff_policy": policy,
            "outcomes_json": '["YES", "NO"]',
            "collateral_token": "0x036CbD53842c5426634e7929541eC2318f3dCf7e",
            "betting_closed_by_authority": authority_closed,
            "betting_close_time": close_time,
            "total_pot": "1000",
        },
        "totals": {"total_pot": "1000", "total_fee_bps": "100"},
        "outcomes": [],
        "ticket_pools": [{"ticket_mask": "1", "pool_total": "900"}, {"ticket_mask": "2", "pool_total": "100"}],
    }


class TestRecommendV3(unittest.TestCase):
    """ADR-0019: ``recommend`` must only rank wagers it can actually bet on
    and whose payout it models correctly.

    Before the fix it ranked every indexer ``OPEN`` wager, although V3 keeps
    ``state == Open`` after betting closes (so the top pick could be a
    guaranteed ``BettingClosed()`` revert), and it scored multi-winner
    policies with the SINGLE_WINNER formula ``bet * netAfter / (pool + bet)``,
    which is not what the contract pays under ANY_OF / EXACT_SET /
    AT_LEAST_K / WEIGHTED_OVERLAP.
    """

    OPEN_SW = "0x" + "01" * 20
    CLOSED_BY_TIME = "0x" + "02" * 20
    CLOSED_BY_AUTHORITY = "0x" + "03" * 20
    ANY_OF = "0x" + "04" * 20

    def _run(self):
        details = {
            self.OPEN_SW: _enum_detail(close_time=9_999_999_999),
            self.CLOSED_BY_TIME: _enum_detail(close_time=1),
            self.CLOSED_BY_AUTHORITY: _enum_detail(close_time=9_999_999_999, authority_closed=1),
            self.ANY_OF: _enum_detail(close_time=9_999_999_999, policy=1),
        }
        return planner.recommend(
            _FakeListingIndexer(details), strategy="value", bet_amount_raw=10, top=10
        )

    def test_only_bettable_single_winner_wagers_are_recommended(self) -> None:
        out = self._run()
        addrs = [r["summary"]["wager_address"] for r in out["recommendations"]]
        self.assertEqual(addrs, [self.OPEN_SW])
        self.assertTrue(all(r["pick"]["betting_open"] for r in out["recommendations"]))

    def test_skipped_wagers_are_reported_with_reasons(self) -> None:
        skipped = {s["wager_address"]: s["reason"] for s in self._run()["skipped"]}
        self.assertEqual(set(skipped), {self.CLOSED_BY_TIME, self.CLOSED_BY_AUTHORITY, self.ANY_OF})
        self.assertIn("betting", skipped[self.CLOSED_BY_TIME].lower())
        self.assertIn("payoff policy", skipped[self.ANY_OF].lower())

    def test_pick_outcome_flags_whether_odds_model_is_exact(self) -> None:
        from agents.paramutuel_bettor.policy import pick_outcome

        sw = pick_outcome(strategy="value", wager_detail=_enum_detail(close_time=9_999_999_999), bet_amount=10)
        anyof = pick_outcome(strategy="value", wager_detail=_enum_detail(close_time=9_999_999_999, policy=1), bet_amount=10)
        self.assertTrue(sw["odds_model_exact"])
        self.assertFalse(anyof["odds_model_exact"])


if __name__ == "__main__":
    unittest.main()
