import contextlib
import io
import json
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from service.indexer.indexer import init_db
from service.indexer import sweeper
from service.indexer.sweeper import SweepResult, parse_args, sweep_once


class SweeperTests(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        init_db(conn)
        conn.execute(
            """
            INSERT INTO wagers(
              wager_address, factory_address, proposer, resolver, betting_closer, resolution_closer,
              collateral_token, betting_close_time, resolution_window, resolution_deadline,
              betting_closed_by_authority, betting_closed_at, resolution_window_closed, state, created_block, created_tx_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?)
            """,
            (
                "0xabc1000000000000000000000000000000000001",
                "0xfac7000000000000000000000000000000000001",
                "0xabc2000000000000000000000000000000000002",
                "0xabc3000000000000000000000000000000000003",
                "0xabc4000000000000000000000000000000000004",
                "0xabc5000000000000000000000000000000000005",
                "0xabc6000000000000000000000000000000000006",
                1000,
                3600,
                4600,
                1,
                1000,
                0,
                1,
                "0xaaa",
            ),
        )
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_sweep_once_dry_run(self):
        result = sweep_once(
            db_path=self.db_path,
            rpc_url="http://localhost:8545",
            private_key="0xabc",
            now_ts=5000,
            execute=False,
        )
        self.assertEqual(result.attempted, 1)
        self.assertEqual(result.succeeded, 1)
        self.assertEqual(result.failed, 0)

    def test_dry_run_never_prints_the_private_key(self):
        """Dry-run is the default and its output goes to logs (ADR-0020 O2)."""
        key = "0x" + "cd" * 32
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            sweep_once(db_path=self.db_path, rpc_url="http://localhost:8545", private_key=key, now_ts=5000, execute=False)
        self.assertIn("DRY_RUN", out.getvalue())
        self.assertNotIn("cd" * 32, out.getvalue())

    def _execute_with(self, proc):
        return sweep_once(
            db_path=self.db_path, rpc_url="http://localhost:8545", private_key="0xabc", now_ts=5000,
            execute=True, runner=lambda *a, **k: proc,
        )

    def test_mined_revert_counts_as_failure(self):
        """`cast send` exits 0 for a reverted transaction, e.g. when someone else expired it first."""
        proc = mock.Mock(returncode=0, stdout=json.dumps({"status": "0x0", "transactionHash": "0xfeed"}), stderr="")
        result = self._execute_with(proc)
        self.assertEqual((result.succeeded, result.failed), (0, 1))

    def test_mined_success_counts_as_success(self):
        proc = mock.Mock(returncode=0, stdout=json.dumps({"status": "0x1", "transactionHash": "0xfeed"}), stderr="")
        result = self._execute_with(proc)
        self.assertEqual((result.succeeded, result.failed), (1, 0))

    def test_private_key_can_come_from_the_environment(self):
        with mock.patch.dict("os.environ", {"PRIVATE_KEY": "0xfromenv", "RPC_URL": "http://r"}), mock.patch("sys.argv", ["sweeper"]):
            args = parse_args()
        self.assertEqual(args.private_key, "0xfromenv")
        self.assertEqual(args.rpc_url, "http://r")

    def test_sweep_once_execute_failure_counted(self):
        def bad_runner(*args, **kwargs):  # noqa: ANN002, ANN003
            class R:
                returncode = 1
                stderr = "boom"

            return R()

        result = sweep_once(
            db_path=self.db_path,
            rpc_url="http://localhost:8545",
            private_key="0xabc",
            now_ts=5000,
            execute=True,
            runner=bad_runner,
        )
        self.assertEqual(result.attempted, 1)
        self.assertEqual(result.succeeded, 0)
        self.assertEqual(result.failed, 1)


class SweeperMainTests(unittest.TestCase):
    """The daemon wrapper, which decides whether expire transactions go out and how often."""

    def _main(self, *argv, env=None, sweep=None, sleep=None):
        out = io.StringIO()
        sweep = sweep or mock.Mock(return_value=SweepResult(attempted=2, succeeded=1, failed=1))
        with (
            mock.patch.dict(os.environ, env if env is not None else {"RPC_URL": "http://r", "PRIVATE_KEY": "0xabc"}, clear=True),
            mock.patch("sys.argv", ["sweeper", *argv]),
            mock.patch.object(sweeper, "sweep_once", sweep),
            mock.patch.object(sweeper.time, "sleep", sleep or mock.Mock()),
            contextlib.redirect_stdout(out),
        ):
            sweeper.main()
        return sweep, out.getvalue()

    def test_refuses_to_run_without_rpc_or_key(self):
        for env in ({}, {"RPC_URL": "http://r"}, {"PRIVATE_KEY": "0xabc"}):
            with self.subTest(env=sorted(env)), self.assertRaisesRegex(SystemExit, "required"):
                self._main(env=env)

    def test_one_pass_is_a_dry_run_unless_told_otherwise(self):
        """Expiring a wager is irreversible, so sending must take an explicit flag."""
        sweep, out = self._main()
        self.assertEqual(sweep.call_count, 1)
        self.assertIs(sweep.call_args.kwargs["execute"], False)
        self.assertEqual(sweep.call_args.kwargs["rpc_url"], "http://r")
        self.assertIn("attempted=2 succeeded=1 failed=1", out)
        self.assertNotIn("0xabc", out)

    def test_execute_flag_reaches_the_sweep(self):
        sweep, _ = self._main("--execute")
        self.assertIs(sweep.call_args.kwargs["execute"], True)

    def test_loop_sleeps_between_passes_and_never_spins(self):
        class Stop(Exception):
            pass

        sleep = mock.Mock(side_effect=[None, Stop()])
        with self.assertRaises(Stop):
            self._main("--loop", "--interval-seconds", "0", sleep=sleep)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [1, 1], "a zero interval floors at one second")


if __name__ == "__main__":
    unittest.main()
