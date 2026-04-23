import unittest

from agents.paramutuel_bettor import calldata


class TestCalldataV3(unittest.TestCase):
    """Bet scout calldata helpers, post-ADR-0010.

    The unified V3 protocol recognises exactly two `protocol_version`
    tags:

      * `enumerated` — bitmask tickets; single-outcome ticket is
        `1 << outcome_index`; calldata selects `placeBet(uint256,uint256)`.
      * `freeform` — UTF-8 answer; calldata selects
        `placeBet(string,uint256)` and only emits when the caller
        supplies the exact answer bytes.
    """

    def test_build_quote_enumerated_uses_single_bit_ticket_mask(self) -> None:
        body = calldata.build_quote_like_payload(
            wager_address="0x" + "ab" * 20,
            collateral_token="0x" + "cd" * 20,
            outcome_index=1,
            amount=50,
            odds={},
            betting_open=True,
            revert_hint="",
            protocol_version="enumerated",
        )
        self.assertEqual(body["protocol_version"], "enumerated")
        self.assertEqual(body["ticket_mask"], 2)

    def test_build_quote_enumerated_encodes_mask_as_first_placeBet_word(self) -> None:
        body = calldata.build_quote_like_payload(
            wager_address="0x" + "ab" * 20,
            collateral_token="0x" + "cd" * 20,
            outcome_index=3,
            amount=1_000,
            odds={},
            betting_open=True,
            revert_hint="",
            protocol_version="enumerated",
        )
        self.assertEqual(body["ticket_mask"], 8)
        cd = body["placeBet"]["calldata"]
        if cd:
            word_hex = cd[10 : 10 + 64]
            self.assertEqual(int(word_hex, 16), 8)

    def test_build_quote_enumerated_default_protocol_version(self) -> None:
        # When callers omit `protocol_version`, the helper defaults to
        # the enumerated-mask code path — parity with the old "unspecified
        # → legacy" fall-through, now collapsed to the canonical default.
        body = calldata.build_quote_like_payload(
            wager_address="0x" + "ab" * 20,
            collateral_token="0x" + "cd" * 20,
            outcome_index=2,
            amount=100,
            odds={},
            betting_open=True,
            revert_hint="",
        )
        self.assertEqual(body["protocol_version"], "enumerated")
        self.assertEqual(body["ticket_mask"], 4)

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
        # Freeform quotes should not expose an enumerated ticket_mask field.
        self.assertNotIn("ticket_mask", body)

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
            # 0xd76f2a1e is keccak4("placeBet(string,uint256)").
            self.assertTrue(cd.lower().startswith("0xd76f2a1e"))
            self.assertTrue(body["execution_allowed"])
            self.assertTrue(body["freeform_answer_supplied"])

    def test_encode_resolve_freeform_selector(self) -> None:
        cd = calldata.encode_resolve_freeform("yes")
        if cd:
            self.assertTrue(cd.startswith("0x"))
            self.assertGreater(len(cd), 10)


if __name__ == "__main__":
    unittest.main()
