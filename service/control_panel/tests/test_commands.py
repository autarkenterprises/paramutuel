import unittest

from service.control_panel.commands import (
    build_create_wager_command,
    build_wager_action_command,
    lifecycle_workflow,
)


class ControlPanelCommandTests(unittest.TestCase):
    def test_create_wager_command_shape(self):
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
            "createWager(address,string,string[],uint64,uint64,address,address,address,address[],uint16[],uint256[],uint256[])",
            joined,
        )
        self.assertIn("[\"YES\",\"NO\"]", joined)

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
        self.assertIn("[0,1]", joined)
        self.assertIn("[100,200]", joined)

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

    def test_workflow_includes_closer_steps_for_no_max(self):
        steps = lifecycle_workflow(no_max_betting=True, no_max_resolution=True)
        self.assertIn("closeBetting", steps)
        self.assertIn("closeResolutionWindow (optional before expire)", steps)


if __name__ == "__main__":
    unittest.main()
