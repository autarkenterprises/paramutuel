"""ADR-0020: the operator CLI, driven through its real argument parser."""
import contextlib
import io
import json
import unittest
from unittest import mock

from eth_abi import decode as abi_decode

from service.control_panel import cli
from service.control_panel.commands import CastResult

KEY = "0x" + "cd" * 32
WAGER = "0x" + "33" * 20
BASE = ["--rpc-url", "http://r", "--private-key", KEY]


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with mock.patch("sys.argv", ["cli", *BASE, *argv]), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = cli.main()
    return rc, out.getvalue(), err.getvalue()


class CliTests(unittest.TestCase):
    def test_dry_run_is_default_and_never_prints_the_key(self):
        rc, out, _ = run_cli("wager-action", "--wager", WAGER, "--action", "retract")
        self.assertEqual(rc, 0)
        self.assertNotIn("cd" * 32, out)
        self.assertIn("<redacted>", out)

    def test_winning_answer_is_not_stripped(self):
        """ADR-0019 finding 8 recorded this fixed; the CLI still called .strip() on it."""
        rc, out, _ = run_cli(
            "wager-action", "--wager", WAGER, "--action", "resolve",
            "--protocol-version", "freeform", "--winning-answer=  Paris  ",
        )
        self.assertEqual(rc, 0)
        calldata = out.split()[-1].strip("'")
        self.assertEqual(abi_decode(["string"], bytes.fromhex(calldata[10:]))[0], "  Paris  ")

    def test_winning_mask_flag_replaces_misnamed_outcome_index(self):
        rc, out, _ = run_cli("wager-action", "--wager", WAGER, "--action", "resolve", "--winning-mask", "5")
        self.assertEqual(rc, 0)
        calldata = out.split()[-1].strip("'")
        self.assertEqual(abi_decode(["uint256"], bytes.fromhex(calldata[10:]))[0], 5)

    def test_old_outcome_index_flag_is_gone_so_old_scripts_fail_loudly(self):
        """It carried a raw mask while the same word in the resolution service means an index."""
        with self.assertRaises(SystemExit):
            run_cli("wager-action", "--wager", WAGER, "--action", "resolve", "--outcome-index", "1")

    def test_execute_reports_a_mined_revert_as_failure(self):
        receipt = json.dumps({"status": "0x0", "transactionHash": "0xfeed"})
        fake = mock.Mock(returncode=0, stdout=receipt, stderr="")
        with mock.patch("service.control_panel.commands.subprocess.run", return_value=fake):
            rc, _, err = run_cli("--execute", "wager-action", "--wager", WAGER, "--action", "retract")
        self.assertEqual(rc, 1)
        self.assertIn("reverted", err)

    def test_invalid_address_exits_2_with_a_message(self):
        rc, _, err = run_cli("wager-action", "--wager", "0x123", "--action", "retract")
        self.assertEqual(rc, 2)
        self.assertIn("error:", err)

    def test_create_wager_passes_policy_and_min_stake(self):
        rc, out, _ = run_cli(
            "create-wager", "--factory", WAGER, "--collateral", WAGER, "--proposition", "Q?", "--outcomes", "A,B,C",
            "--betting-close-time", "1", "--resolution-window", "1", "--payoff-policy", "3", "--policy-param", "2",
            "--min-new-ticket-stake", "9",
        )
        self.assertEqual(rc, 0)
        self.assertIn("uint256)", out, "function line shows the minimum-stake overload")


class CliRemainingTests(unittest.TestCase):
    def test_missing_rpc_or_key_is_a_usage_error_not_a_traceback(self):
        err = io.StringIO()
        with (
            mock.patch.dict(cli.os.environ, {}, clear=True),
            mock.patch("sys.argv", ["cli", "wager-action", "--wager", WAGER, "--action", "retract"]),
            contextlib.redirect_stderr(err),
        ):
            self.assertEqual(cli.main(), 2)
        self.assertIn("required", err.getvalue())

    def test_freeform_create_dry_run_encodes_exactly_what_was_given(self):
        rc, out, _ = run_cli(
            "create-freeform-wager",
            "--factory", WAGER, "--collateral", WAGER, "--proposition=  Who wins?  ",
            "--betting-close-time", "5", "--resolution-window", "6",
            "--resolver", WAGER, "--betting-closer", WAGER, "--resolution-closer", WAGER,
            "--min-new-ticket-stake", "9",
        )
        self.assertEqual(rc, 0)
        calldata = out.split()[-1].strip("'")
        decoded = abi_decode(
            ["address", "string", "uint64", "uint64", "address", "address", "address", "address[]", "uint16[]", "uint256"],
            bytes.fromhex(calldata[10:]),
        )
        self.assertEqual(decoded[1], "  Who wins?  ")
        self.assertEqual(decoded[-1], 9)
        self.assertNotIn("cd" * 32, out)

    def test_execute_reports_success_and_failure_through_the_exit_code(self):
        """Scripts rely on this: a mined revert must not read as success."""
        ok = CastResult(ok=True, stdout="receipt", stderr="", tx_hash="0xbeef", returncode=0)
        with mock.patch.object(cli, "run_cast_send", return_value=ok):
            rc, out, _ = run_cli("--execute", "wager-action", "--wager", WAGER, "--action", "retract")
        self.assertEqual(rc, 0)
        self.assertIn("receipt", out)

        bad = CastResult(ok=False, stdout="", stderr="reverted on-chain", tx_hash="0xfeed", returncode=0)
        with mock.patch.object(cli, "run_cast_send", return_value=bad):
            rc, _, err = run_cli("--execute", "wager-action", "--wager", WAGER, "--action", "retract")
        self.assertEqual(rc, 1)
        self.assertIn("reverted on-chain", err)


if __name__ == "__main__":
    unittest.main()
