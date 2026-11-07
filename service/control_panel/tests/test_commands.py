import unittest

from eth_abi import decode as abi_decode
from eth_hash.auto import keccak

from service.control_panel.commands import (
    build_create_freeform_wager_command,
    build_create_wager_command,
    build_wager_action_command,
    lifecycle_workflow,
)

CREATE_ENUM_SEEDED = (
    "createEnumeratedWager(address,string,string[],uint8,uint256,uint64,uint64,"
    "address,address,address,address[],uint16[],uint256[],uint256[])"
)
CREATE_ENUM_MIN = CREATE_ENUM_SEEDED[:-1] + ",uint256)"
CREATE_ENUM_TYPES = [
    "address", "string", "string[]", "uint8", "uint256", "uint64", "uint64",
    "address", "address", "address", "address[]", "uint16[]", "uint256[]", "uint256[]",
]
CREATE_FREEFORM = "createFreeformWager(address,string,uint64,uint64,address,address,address,address[],uint16[])"
CREATE_FREEFORM_MIN = CREATE_FREEFORM[:-1] + ",uint256)"
CREATE_FREEFORM_TYPES = ["address", "string", "uint64", "uint64", "address", "address", "address", "address[]", "uint16[]"]


def onchain_args(cmd, signature, types):
    """Decode what would actually reach the chain from a built command, independently of the encoder.

    The argv's last token is the calldata; this asserts its selector and returns the decoded args.
    """
    data = bytes.fromhex(cmd.command[-1].removeprefix("0x"))
    assert data[:4] == keccak(signature.encode())[:4], f"selector is not {signature}"
    return abi_decode(types, data[4:])


class ControlPanelCommandTests(unittest.TestCase):
    def test_create_wager_command_shape(self):
        # ADR-0010: control panel targets `createEnumeratedWager` with seeds
        # overload (empty seed arrays = no seed tickets).
        cmd = build_create_wager_command(
            factory="0x1111111111111111111111111111111111111111",
            collateral="0x2222222222222222222222222222222222222222",
            proposition="Q?",
            outcomes=["YES", "NO"],
            betting_close_time=1234567890,
            resolution_window=7200,
            resolver="0x0000000000000000000000000000000000000000",
            betting_closer="0x0000000000000000000000000000000000000000",
            resolution_closer="0x0000000000000000000000000000000000000000",
            extra_recipients=[],
            extra_bps=[],
            rpc_url="http://localhost:8545",
            private_key="0xabc",
        )
        args = onchain_args(cmd, CREATE_ENUM_SEEDED, CREATE_ENUM_TYPES)
        self.assertEqual(args[1], "Q?")
        self.assertEqual(args[2], ("YES", "NO"))
        self.assertEqual(cmd.signature, CREATE_ENUM_SEEDED)

    def test_create_wager_command_defaults_to_single_winner_policy(self):
        cmd = build_create_wager_command(
            factory="0x1111111111111111111111111111111111111111",
            collateral="0x2222222222222222222222222222222222222222",
            proposition="Q?",
            outcomes=["YES", "NO"],
            betting_close_time=1234567890,
            resolution_window=7200,
            resolver="0x0000000000000000000000000000000000000000",
            betting_closer="0x0000000000000000000000000000000000000000",
            resolution_closer="0x0000000000000000000000000000000000000000",
            extra_recipients=[],
            extra_bps=[],
            rpc_url="http://localhost:8545",
            private_key="0xabc",
        )
        args = onchain_args(cmd, CREATE_ENUM_SEEDED, CREATE_ENUM_TYPES)
        self.assertEqual(args[3], 0, "payoffPolicy defaults to SINGLE_WINNER")
        self.assertEqual(args[4], 0, "policyParam defaults to 0")

    def test_create_wager_command_forwards_payoff_policy_and_param(self):
        cmd = build_create_wager_command(
            factory="0x1111111111111111111111111111111111111111",
            collateral="0x2222222222222222222222222222222222222222",
            proposition="K of 4",
            outcomes=["A", "B", "C", "D"],
            betting_close_time=1,
            resolution_window=1,
            resolver="0x0000000000000000000000000000000000000000",
            betting_closer="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            resolution_closer="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            extra_recipients=[],
            extra_bps=[],
            payoff_policy=3,  # AT_LEAST_K
            policy_param=2,
            rpc_url="http://localhost:8545",
            private_key="0xabc",
        )
        args = onchain_args(cmd, CREATE_ENUM_SEEDED, CREATE_ENUM_TYPES)
        self.assertEqual(args[2], ("A", "B", "C", "D"))
        self.assertEqual((args[3], args[4]), (3, 2))

    def test_create_wager_command_rejects_invalid_payoff_policy(self):
        with self.assertRaises(ValueError):
            build_create_wager_command(
                factory="0x1111111111111111111111111111111111111111",
                collateral="0x2222222222222222222222222222222222222222",
                proposition="Q?",
                outcomes=["A", "B"],
                betting_close_time=1,
                resolution_window=1,
                resolver="0x0000000000000000000000000000000000000000",
                betting_closer="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                resolution_closer="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                extra_recipients=[],
                extra_bps=[],
                payoff_policy=99,
                rpc_url="http://localhost:8545",
                private_key="0xabc",
            )

    def test_create_wager_rejects_uncloseable_no_max(self):
        with self.assertRaises(ValueError):
            build_create_wager_command(
                factory="0x1111111111111111111111111111111111111111",
                collateral="0x2222222222222222222222222222222222222222",
                proposition="Q?",
                outcomes=["YES", "NO"],
                betting_close_time=0,
                resolution_window=0,
                resolver="0x0000000000000000000000000000000000000000",
                betting_closer="0x0000000000000000000000000000000000000000",
                resolution_closer="0x0000000000000000000000000000000000000000",
                extra_recipients=[],
                extra_bps=[],
                rpc_url="http://localhost:8545",
                private_key="0xabc",
            )

    def test_create_wager_accepts_seed_arrays(self):
        # V3 factory expects `uint256[] seedTicketMasks`, not raw outcome
        # indices.  The control panel promotes each outcome index `i` to
        # the single-outcome ticket bitmask `1 << i` — parity with the old
        # "seed outcome 0 + seed outcome 1" semantics.
        cmd = build_create_wager_command(
            factory="0x1111111111111111111111111111111111111111",
            collateral="0x2222222222222222222222222222222222222222",
            proposition="Q?",
            outcomes=["YES", "NO"],
            betting_close_time=1234567890,
            resolution_window=7200,
            resolver="0x0000000000000000000000000000000000000000",
            betting_closer="0x0000000000000000000000000000000000000000",
            resolution_closer="0x0000000000000000000000000000000000000000",
            extra_recipients=[],
            extra_bps=[],
            seed_outcome_indices=[0, 1],
            seed_amounts=[100, 200],
            rpc_url="http://localhost:8545",
            private_key="0xabc",
        )
        args = onchain_args(cmd, CREATE_ENUM_SEEDED, CREATE_ENUM_TYPES)
        self.assertEqual(args[12], (1, 2))
        self.assertEqual(args[13], (100, 200))

    def test_create_wager_rejects_seed_index_out_of_range(self):
        with self.assertRaises(ValueError):
            build_create_wager_command(
                factory="0x1111111111111111111111111111111111111111",
                collateral="0x2222222222222222222222222222222222222222",
                proposition="Q?",
                outcomes=["YES", "NO"],
                betting_close_time=1,
                resolution_window=1,
                resolver="0x0000000000000000000000000000000000000000",
                betting_closer="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                resolution_closer="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                extra_recipients=[],
                extra_bps=[],
                seed_outcome_indices=[2],  # only outcomes 0..1 exist
                seed_amounts=[100],
                rpc_url="http://localhost:8545",
                private_key="0xabc",
            )

    def test_create_wager_rejects_more_than_255_outcomes(self):
        with self.assertRaises(ValueError) as ctx:
            build_create_wager_command(
                factory="0x1111111111111111111111111111111111111111",
                collateral="0x2222222222222222222222222222222222222222",
                proposition="Q?",
                outcomes=["O"] * 256,
                betting_close_time=1234567890,
                resolution_window=7200,
                resolver="0x0000000000000000000000000000000000000000",
                betting_closer="0x0000000000000000000000000000000000000000",
                resolution_closer="0x0000000000000000000000000000000000000000",
                extra_recipients=[],
                extra_bps=[],
                rpc_url="http://localhost:8545",
                private_key="0xabc",
            )
        self.assertIn("255", str(ctx.exception))

    @unittest.expectedFailure
    def test_XFAIL_DEPRECATED_cli_rejected_66_outcomes_when_max_was_64(self):
        """Hypothetical strict CLI (never shipped): reject >64 outcomes. Cap is now 255 so 66 is valid."""
        with self.assertRaises(ValueError):
            build_create_wager_command(
                factory="0x1111111111111111111111111111111111111111",
                collateral="0x2222222222222222222222222222222222222222",
                proposition="Q?",
                outcomes=["O"] * 66,
                betting_close_time=1234567890,
                resolution_window=7200,
                resolver="0x0000000000000000000000000000000000000000",
                betting_closer="0x0000000000000000000000000000000000000000",
                resolution_closer="0x0000000000000000000000000000000000000000",
                extra_recipients=[],
                extra_bps=[],
                rpc_url="http://localhost:8545",
                private_key="0xabc",
            )

    def test_action_command_requires_outcome_for_resolve(self):
        with self.assertRaises(ValueError):
            build_wager_action_command(
                wager="0x3333333333333333333333333333333333333333",
                action="resolve",
                winning_mask=None,
                rpc_url="http://localhost:8545",
                private_key="0xabc",
            )

    def test_action_command_freeform_resolve_uses_string_sig(self):
        cmd = build_wager_action_command(
            wager="0x3333333333333333333333333333333333333333",
            action="resolve",
            winning_mask=None,
            protocol_version="freeform",
            winning_answer="Team A",
            rpc_url="http://localhost:8545",
            private_key="0xabc",
        )
        self.assertEqual(onchain_args(cmd, "resolve(string)", ["string"])[0], "Team A")

    def test_action_command_freeform_resolve_is_byte_exact(self):
        # V3 hashes the answer bytes verbatim (ADR-0009 §5), so " Team A " and "Team A" are different
        # pools. ADR-0019 asserted this on an argv token, which passed while `cast` was stripping the
        # trailing space on the way to the chain, so this checks the decoded calldata (ADR-0020).
        for answer in (" Team A ", "Team A ", '"Team A"', "'Team A'", "--help", "--rpc-url=http://evil"):
            with self.subTest(answer=answer):
                cmd = build_wager_action_command(
                    wager="0x3333333333333333333333333333333333333333",
                    action="resolve",
                    winning_mask=None,
                    protocol_version="freeform",
                    winning_answer=answer,
                    rpc_url="http://localhost:8545",
                    private_key="0xabc",
                )
                self.assertEqual(onchain_args(cmd, "resolve(string)", ["string"])[0], answer)

    def test_create_freeform_wager_command_shape(self):
        cmd = build_create_freeform_wager_command(
            factory="0x1111111111111111111111111111111111111111",
            collateral="0x2222222222222222222222222222222222222222",
            proposition="Who wins?",
            betting_close_time=1,
            resolution_window=1,
            resolver="0x0000000000000000000000000000000000000000",
            betting_closer="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            resolution_closer="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            extra_recipients=[],
            extra_bps=[],
            rpc_url="http://localhost:8545",
            private_key="0xabc",
        )
        args = onchain_args(cmd, CREATE_FREEFORM, CREATE_FREEFORM_TYPES)
        self.assertEqual(args[1], "Who wins?")

    # ------------------------------------------------------------------
    # ADR-0020
    # ------------------------------------------------------------------

    def _create(self, **kw):
        base = dict(
            factory="0x1111111111111111111111111111111111111111",
            collateral="0x2222222222222222222222222222222222222222",
            proposition="Q?",
            outcomes=["YES", "NO"],
            betting_close_time=1,
            resolution_window=1,
            resolver="0x0000000000000000000000000000000000000000",
            betting_closer="0x0000000000000000000000000000000000000000",
            resolution_closer="0x0000000000000000000000000000000000000000",
            extra_recipients=[],
            extra_bps=[],
            rpc_url="http://localhost:8545",
            private_key="0xabc",
        )
        base.update(kw)
        return build_create_wager_command(**base)

    def test_outcome_labels_reach_the_chain_exactly(self):
        """json.dumps escapes reached the chain verbatim: `café` was stored as `caf\\u00e9`."""
        labels = ["café ☕", "a,b", 'say "hi"', "back\\slash", " padded ", "--flag"]
        args = onchain_args(self._create(outcomes=labels), CREATE_ENUM_SEEDED, CREATE_ENUM_TYPES)
        self.assertEqual(list(args[2]), labels)

    def test_proposition_reaches_the_chain_exactly(self):
        for text in (' "Will it?" ', "--help", "trailing "):
            with self.subTest(text=text):
                args = onchain_args(self._create(proposition=text), CREATE_ENUM_SEEDED, CREATE_ENUM_TYPES)
                self.assertEqual(args[1], text)

    def test_min_new_ticket_stake_uses_the_new_overload(self):
        cmd = self._create(min_new_ticket_stake=5_000_000)
        args = onchain_args(cmd, CREATE_ENUM_MIN, CREATE_ENUM_TYPES + ["uint256"])
        self.assertEqual(args[14], 5_000_000)
        self.assertEqual(cmd.signature, CREATE_ENUM_MIN)

    def test_zero_min_stake_keeps_the_overload_the_deployed_factory_has(self):
        self.assertEqual(self._create(min_new_ticket_stake=0).signature, CREATE_ENUM_SEEDED)

    def test_freeform_min_stake_overload(self):
        cmd = build_create_freeform_wager_command(
            factory="0x1111111111111111111111111111111111111111",
            collateral="0x2222222222222222222222222222222222222222",
            proposition="Who?",
            betting_close_time=1,
            resolution_window=1,
            resolver="0x0000000000000000000000000000000000000000",
            betting_closer="0x0000000000000000000000000000000000000000",
            resolution_closer="0x0000000000000000000000000000000000000000",
            extra_recipients=[],
            extra_bps=[],
            min_new_ticket_stake=7,
            rpc_url="http://localhost:8545",
            private_key="0xabc",
        )
        args = onchain_args(cmd, CREATE_FREEFORM_MIN, CREATE_FREEFORM_TYPES + ["uint256"])
        self.assertEqual(args[9], 7)

    def test_winning_mask_accepts_large_decimal_strings_without_rounding(self):
        mask = 2**200 + 1  # JavaScript's Number would round this
        cmd = build_wager_action_command(
            wager="0x3333333333333333333333333333333333333333",
            action="resolve",
            winning_mask=str(mask),
            rpc_url="http://localhost:8545",
            private_key="0xabc",
        )
        self.assertEqual(onchain_args(cmd, "resolve(uint256)", ["uint256"])[0], mask)

    def test_winning_mask_rejects_non_integers(self):
        for bad in (1.5, True, "abc", -1, "0"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                build_wager_action_command(
                    wager="0x3333333333333333333333333333333333333333",
                    action="resolve",
                    winning_mask=bad,
                    rpc_url="http://localhost:8545",
                    private_key="0xabc",
                )

    def test_shell_rendering_never_contains_the_key(self):
        rendered = self._create(private_key="0x" + "cd" * 32).shell()
        self.assertNotIn("cd" * 32, rendered)
        self.assertIn("<redacted>", rendered)

    def test_invalid_address_rejected_before_anything_runs(self):
        with self.assertRaises(ValueError):
            self._create(factory="0x123")
        with self.assertRaises(ValueError):
            self._create(resolver="nonsense")

    def test_workflow_includes_closer_steps_for_no_max(self):
        steps = lifecycle_workflow(no_max_betting=True, no_max_resolution=True)
        self.assertIn("closeBetting", steps)
        self.assertIn("closeResolutionWindow (optional before expire)", steps)


class BuilderValidationTests(unittest.TestCase):
    """Each input the factory is certain to reject fails here with a clear message, before any gas."""

    ZERO = "0x0000000000000000000000000000000000000000"
    ONE = "0x1111111111111111111111111111111111111111"

    def _create(self, **kw):
        args = dict(
            factory=self.ONE, collateral=self.ONE, proposition="Q?", outcomes=["A", "B"], betting_close_time=1,
            resolution_window=1, resolver=self.ZERO, betting_closer=self.ZERO, resolution_closer=self.ZERO,
            extra_recipients=[], extra_bps=[], rpc_url="http://r", private_key="0xabc",
        )
        args.update(kw)
        return build_create_wager_command(**args)

    def _freeform(self, **kw):
        args = dict(
            factory=self.ONE, collateral=self.ONE, proposition="Q?", betting_close_time=1, resolution_window=1,
            resolver=self.ZERO, betting_closer=self.ZERO, resolution_closer=self.ZERO,
            extra_recipients=[], extra_bps=[], rpc_url="http://r", private_key="0xabc",
        )
        args.update(kw)
        return build_create_freeform_wager_command(**args)

    def test_enumerated_rejections(self):
        for kw, message in (
            (dict(outcomes=["only one"]), "at least 2"),
            (dict(extra_recipients=[self.ONE]), "extra_recipients"),
            (dict(seed_outcome_indices=[0]), "seed_outcome_indices"),
            (dict(seed_outcome_indices=[0], seed_amounts=[0]), "positive"),
            (dict(payoff_policy=5), "payoff_policy"),
            (dict(betting_close_time=0), "betting_closer"),
            (dict(resolution_window=0), "resolution_closer"),
        ):
            with self.subTest(kw=kw), self.assertRaisesRegex(ValueError, message):
                self._create(**kw)

    def test_freeform_rejections(self):
        for kw, message in (
            (dict(extra_recipients=[self.ONE]), "extra_recipients"),
            (dict(betting_close_time=0), "betting_closer"),
            (dict(resolution_window=0), "resolution_closer"),
        ):
            with self.subTest(kw=kw), self.assertRaisesRegex(ValueError, message):
                self._freeform(**kw)

    def test_no_max_windows_are_allowed_when_a_closer_is_named(self):
        self._create(betting_close_time=0, betting_closer=self.ONE)
        self._freeform(resolution_window=0, resolution_closer=self.ONE)

    def test_action_rejections(self):
        common = dict(wager=self.ONE, rpc_url="http://r", private_key="0xabc")
        with self.assertRaisesRegex(ValueError, "winning_answer"):
            build_wager_action_command(action="resolve", protocol_version="freeform", **common)
        with self.assertRaisesRegex(ValueError, "unsupported action"):
            build_wager_action_command(action="self-destruct", **common)


if __name__ == "__main__":
    unittest.main()
