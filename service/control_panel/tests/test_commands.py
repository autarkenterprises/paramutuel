import unittest

from service.control_panel.commands import (
    build_create_freeform_wager_command,
    build_create_wager_command,
    build_wager_action_command,
    lifecycle_workflow,
)


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
        joined = " ".join(cmd.command)
        self.assertIn(
            "createEnumeratedWager(address,string,string[],uint8,uint256,uint64,uint64,address,address,address,address[],uint16[],uint256[],uint256[])",
            joined,
        )
        self.assertIn("[\"YES\",\"NO\"]", joined)

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
        # The `uint8 payoffPolicy` and `uint256 policyParam` args sit right
        # after the outcomes JSON; both default to 0 (SINGLE_WINNER, no param).
        idx = cmd.command.index("[\"YES\",\"NO\"]")
        self.assertEqual(cmd.command[idx + 1], "0")
        self.assertEqual(cmd.command[idx + 2], "0")

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
        joined = " ".join(cmd.command)
        self.assertIn("[\"A\",\"B\",\"C\",\"D\"] 3 2", joined)

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
        joined = " ".join(cmd.command)
        self.assertIn("[1,2]", joined)
        self.assertIn("[100,200]", joined)

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
                outcome_index=None,
                rpc_url="http://localhost:8545",
                private_key="0xabc",
            )

    def test_action_command_freeform_resolve_uses_string_sig(self):
        cmd = build_wager_action_command(
            wager="0x3333333333333333333333333333333333333333",
            action="resolve",
            outcome_index=None,
            protocol_version="freeform",
            winning_answer="Team A",
            rpc_url="http://localhost:8545",
            private_key="0xabc",
        )
        joined = " ".join(cmd.command)
        self.assertIn("resolve(string)", joined)
        self.assertIn("Team A", joined)

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
        joined = " ".join(cmd.command)
        self.assertIn("createFreeformWager(address,string,uint64,uint64,address,address,address,address[],uint16[])", joined)

    def test_workflow_includes_closer_steps_for_no_max(self):
        steps = lifecycle_workflow(no_max_betting=True, no_max_resolution=True)
        self.assertIn("closeBetting", steps)
        self.assertIn("closeResolutionWindow (optional before expire)", steps)


if __name__ == "__main__":
    unittest.main()
