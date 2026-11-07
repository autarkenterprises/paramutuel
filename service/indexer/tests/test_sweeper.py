import contextlib
import io
import json
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from service.indexer.indexer import init_db
from service.indexer.sweeper import parse_args, sweep_once


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


if __name__ == "__main__":
    unittest.main()
