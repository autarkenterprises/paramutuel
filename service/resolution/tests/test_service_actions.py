import unittest

from service.resolution.service import _action_command, evaluate_candidates


class TestResolutionActions(unittest.TestCase):
    def test_resolve_command_prefers_winning_mask_over_outcome_index(self) -> None:
        cmd = _action_command(
            wager_address="0x" + "ab" * 20,
            action="resolve",
            rpc_url="http://localhost:8545",
            private_key="0x" + "cd" * 32,
            protocol_version="v2",
            resolve_uint256=1 << 4,
        )
        self.assertIn("resolve(uint256)", cmd)
        self.assertIn(str(1 << 4), cmd)

    def test_resolve_command_freeform_uses_string(self) -> None:
        cmd = _action_command(
            wager_address="0x" + "ab" * 20,
            action="resolve",
            rpc_url="http://localhost:8545",
            private_key="0x" + "cd" * 32,
            protocol_version="freeform",
            winning_answer="yes",
        )
        self.assertIn("resolve(string)", cmd)
        self.assertIn("yes", cmd)

    def test_resolve_command_requires_value(self) -> None:
        with self.assertRaises(ValueError):
            _action_command(
                wager_address="0x" + "ab" * 20,
                action="resolve",
                rpc_url="http://localhost:8545",
                private_key="0x" + "cd" * 32,
                protocol_version="v1",
                resolve_uint256=None,
            )

    def test_resolve_command_freeform_requires_answer(self) -> None:
        with self.assertRaises(ValueError):
            _action_command(
                wager_address="0x" + "ab" * 20,
                action="resolve",
                rpc_url="http://localhost:8545",
                private_key="0x" + "cd" * 32,
                protocol_version="freeform",
                winning_answer="",
            )

    def test_evaluate_candidates_surfaces_winning_mask_decision(self) -> None:
        resolver = "0xabc3000000000000000000000000000000000003"
        open_wagers = [
            {
                "wager_address": "0xabc1000000000000000000000000000000000001",
                "state": "OPEN",
                "protocol_version": "v2",
                "resolver": resolver,
                "betting_closed_by_authority": 1,
                "betting_close_time": 0,
                "resolution_window": 0,
                "resolution_window_closed": 0,
            },
        ]
        decisions = {
            "0xabc1000000000000000000000000000000000001": {
                "action": "resolve",
                "outcomeIndex": 0,
                "winningMask": 8,
            }
        }
        rows = evaluate_candidates(
            open_wagers=open_wagers,
            decisions=decisions,
            resolver_address=resolver,
            now_ts=1,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].get("decision_winning_mask"), 8)
        self.assertEqual(rows[0].get("decision_outcome_index"), 0)


if __name__ == "__main__":
    unittest.main()
