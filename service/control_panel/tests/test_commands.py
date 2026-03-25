import unittest

from service.control_panel.commands import (
    build_create_market_command,
    build_market_action_command,
    lifecycle_workflow,
)


class ControlPanelCommandTests(unittest.TestCase):
    def test_create_market_command_shape(self):
        cmd = build_create_market_command(
            factory="0x1111111111111111111111111111111111111111",
            collateral="0x2222222222222222222222222222222222222222",
            question="Q?",
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
        joined = " ".join(cmd.command)
        self.assertIn("createMarket(address,string,string[],uint64,uint64,address,address,address,address[],uint16[])", joined)
        self.assertIn("[\"YES\",\"NO\"]", joined)

    def test_action_command_requires_outcome_for_resolve(self):
        with self.assertRaises(ValueError):
            build_market_action_command(
                market="0x3333333333333333333333333333333333333333",
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
