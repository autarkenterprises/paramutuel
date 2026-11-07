"""ADR-0020: `cast send` exits 0 for a mined, reverted transaction, so the exit code alone is not success."""
import json
import subprocess
import unittest

from service.control_panel.commands import redact_argv, run_cast_send

ARGV = ["cast", "send", "--json", "--rpc-url", "http://r", "--private-key", "0x" + "cd" * 32, "0x" + "ab" * 20, "0x1234"]


class FakeProc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def receipt(status, tx="0xfeed"):
    return json.dumps({"status": status, "transactionHash": tx, "gasUsed": "0x5208"})


class RunCastSendTests(unittest.TestCase):
    def _run(self, proc):
        return run_cast_send(ARGV, runner=lambda *a, **k: proc)

    def test_mined_success(self):
        r = self._run(FakeProc(stdout=receipt("0x1", "0xabc")))
        self.assertTrue(r.ok)
        self.assertEqual(r.tx_hash, "0xabc")

    def test_mined_revert_exits_zero_but_is_a_failure(self):
        r = self._run(FakeProc(stdout=receipt("0x0", "0xabc")))
        self.assertFalse(r.ok)
        self.assertIn("reverted", r.stderr)
        self.assertEqual(r.tx_hash, "0xabc", "the failed hash is still useful to the operator")

    def test_nonzero_exit_is_a_failure(self):
        r = self._run(FakeProc(returncode=1, stderr="execution reverted: BettingNotClosed"))
        self.assertFalse(r.ok)
        self.assertIn("BettingNotClosed", r.stderr)

    def test_output_that_is_not_a_receipt_is_a_failure(self):
        """`--help` exits 0 with text output; that must never read as success."""
        self.assertFalse(self._run(FakeProc(stdout="Sign and publish a transaction")).ok)
        self.assertFalse(self._run(FakeProc(stdout="[]")).ok)
        self.assertFalse(self._run(FakeProc(stdout=json.dumps({"no": "status"}))).ok)

    def test_missing_cast_binary_is_reported_not_raised(self):
        def missing(*a, **k):
            raise FileNotFoundError("cast")

        r = run_cast_send(ARGV, runner=missing)
        self.assertFalse(r.ok)
        self.assertIn("cast", r.stderr)
        self.assertIn("PATH", r.stderr)

    def test_timeout_is_reported_and_warns_the_tx_may_land(self):
        def slow(*a, **k):
            raise subprocess.TimeoutExpired(cmd="cast", timeout=1)

        r = run_cast_send(ARGV, runner=slow)
        self.assertFalse(r.ok)
        self.assertIn("may still", r.stderr)

    def test_a_timeout_is_always_passed_to_the_subprocess(self):
        seen = {}

        def capture(cmd, **kw):
            seen.update(kw)
            return FakeProc(stdout=receipt("0x1"))

        run_cast_send(ARGV, runner=capture)
        self.assertGreater(seen["timeout"], 0)

    def test_key_is_never_echoed_in_reported_errors(self):
        key = "cd" * 32
        r = self._run(FakeProc(returncode=1, stderr=f"bad arg --private-key 0x{key}"))
        self.assertNotIn(key, r.stderr)


class RedactTests(unittest.TestCase):
    def test_redacts_value_after_flag_and_keeps_the_rest(self):
        out = redact_argv(ARGV)
        self.assertEqual(out[out.index("--private-key") + 1], "<redacted>")
        self.assertEqual(out[-1], "0x1234")
        self.assertEqual(ARGV[ARGV.index("--private-key") + 1], "0x" + "cd" * 32, "input not mutated")


if __name__ == "__main__":
    unittest.main()
