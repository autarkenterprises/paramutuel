#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import time
from dataclasses import dataclass
from typing import Callable

from .indexer import db_connect, get_expire_candidates, init_db


@dataclass
class SweepResult:
    attempted: int
    succeeded: int
    failed: int


def _expire_command(market_address: str, rpc_url: str, private_key: str) -> list[str]:
    return [
        "cast",
        "send",
        market_address,
        "expire()",
        "--rpc-url",
        rpc_url,
        "--private-key",
        private_key,
    ]


def sweep_once(
    *,
    db_path: str,
    rpc_url: str,
    private_key: str,
    now_ts: int | None = None,
    execute: bool = False,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> SweepResult:
    conn = db_connect(db_path)
    init_db(conn)
    candidates = get_expire_candidates(conn, now_ts=now_ts)

    attempted = 0
    succeeded = 0
    failed = 0
    for row in candidates:
        market = row["market_address"]
        cmd = _expire_command(market, rpc_url, private_key)
        attempted += 1
        if not execute:
            print("DRY_RUN", " ".join(cmd))
            succeeded += 1
            continue
        proc = runner(cmd, check=False, capture_output=True, text=True)
        if proc.returncode == 0:
            print(f"EXPIRED {market}")
            succeeded += 1
        else:
            print(f"FAILED {market} rc={proc.returncode} stderr={proc.stderr.strip()}")
            failed += 1

    return SweepResult(attempted=attempted, succeeded=succeeded, failed=failed)


def main() -> None:
    parser = argparse.ArgumentParser(description="Paramutuel expire sweeper daemon")
    parser.add_argument("--db-path", default="service/indexer/indexer.db")
    parser.add_argument("--rpc-url", required=True)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--execute", action="store_true", help="Execute expire transactions. Default is dry-run.")
    parser.add_argument("--loop", action="store_true", help="Run continuously.")
    parser.add_argument("--interval-seconds", type=int, default=60)
    args = parser.parse_args()

    def _run_once() -> SweepResult:
        ts = int(time.time())
        result = sweep_once(
            db_path=args.db_path,
            rpc_url=args.rpc_url,
            private_key=args.private_key,
            now_ts=ts,
            execute=args.execute,
        )
        print(
            f"SWEEP now={ts} attempted={result.attempted} succeeded={result.succeeded} failed={result.failed}"
        )
        return result

    if not args.loop:
        _run_once()
        return

    while True:
        _run_once()
        time.sleep(max(1, args.interval_seconds))


if __name__ == "__main__":
    main()
