import unittest

from agents.paramutuel_bettor import calldata


class TestCalldataV2(unittest.TestCase):
    def test_build_quote_v2_uses_ticket_mask_for_place_bet_word(self) -> None:
        body = calldata.build_quote_like_payload(
            wager_address="0x" + "ab" * 20,
            collateral_token="0x" + "cd" * 20,
            outcome_index=3,
            amount=1_000,
            odds={},
            betting_open=True,
            revert_hint="",
            protocol_version="v2",
        )
        self.assertEqual(body["protocol_version"], "v2")
        self.assertEqual(body["ticket_mask"], 8)
        cd = body["placeBet"]["calldata"]
        if cd:
            word_hex = cd[10 : 10 + 64]
            self.assertEqual(int(word_hex, 16), 8)

    def test_build_quote_freeform_without_answer_omits_calldata(self) -> None:
        body = calldata.build_quote_like_payload(
            wager_address="0x" + "ab" * 20,
            collateral_token="0x" + "cd" * 20,
            outcome_index=0,
            amount=1_000,
            odds={},
            betting_open=True,
            revert_hint="",
            protocol_version="freeform",
            freeform_answer=None,
        )
        self.assertEqual(body["protocol_version"], "freeform")
        self.assertIsNone(body["placeBet"]["calldata"])
        self.assertFalse(body["execution_allowed"])
        self.assertIsNotNone(body["placeBet"]["calldata_note"])

    def test_build_quote_freeform_with_answer_encodes_string_fn(self) -> None:
        body = calldata.build_quote_like_payload(
            wager_address="0x" + "ab" * 20,
            collateral_token="0x" + "cd" * 20,
            outcome_index=0,
            amount=1_000_000,
            odds={},
            betting_open=True,
            revert_hint="",
            protocol_version="freeform",
            freeform_answer="Paris",
        )
        cd = body["placeBet"]["calldata"]
        if cd:
            self.assertTrue(cd.lower().startswith("0xd76f2a1e"))
            self.assertTrue(body["execution_allowed"])

    def test_encode_resolve_freeform_selector(self) -> None:
        cd = calldata.encode_resolve_freeform("yes")
        if cd:
            self.assertTrue(cd.startswith("0x"))
            self.assertGreater(len(cd), 10)

    def test_build_quote_v1_keeps_outcome_index_as_first_word(self) -> None:
        body = calldata.build_quote_like_payload(
            wager_address="0x" + "ab" * 20,
            collateral_token="0x" + "cd" * 20,
            outcome_index=3,
            amount=1_000,
            odds={},
            betting_open=True,
            revert_hint="",
            protocol_version="v1",
        )
        self.assertIsNone(body.get("ticket_mask"))
        cd = body["placeBet"]["calldata"]
        if cd:
            word_hex = cd[10 : 10 + 64]
            self.assertEqual(int(word_hex, 16), 3)


if __name__ == "__main__":
    unittest.main()
