import os
import sqlite3
import tempfile
import unittest

from service.indexer.indexer import init_db
from service.indexer.sweeper import sweep_once


class SweeperTests(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        init_db(conn)
        conn.execute(
            """
            INSERT INTO markets(
              market_address, factory_address, proposer, resolver, betting_closer, resolution_closer,
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
