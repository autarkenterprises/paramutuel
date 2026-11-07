#!/usr/bin/env python3
"""Best-effort daemon that calls ``expire()`` on stale wagers.

The sweeper reads ``expire_candidates`` from the indexer's SQLite DB
(see :func:`service.indexer.indexer.get_expire_candidates`) and, when
``--execute`` is passed, sends an ``expire()`` transaction to each via
``cast send``. By default the daemon runs in dry-run, printing the
command it *would* execute so an operator can inspect a window before
turning execution on.

Idempotency
-----------
The on-chain ``expire()`` reverts after the first successful call (the
wager state moves to ``RETRACTED``). The next sweep round re-reads the
candidate list, the now-retracted wager is no longer ``OPEN``, and it
drops out — so calling sweep on the same window repeatedly is safe and
self-converges. ``cast send`` returns non-zero on the contract revert
in the rare race where another caller expired the wager first; that
shows up as a ``FAILED`` line and is normal background noise. Success
means a mined receipt with status 1, because ``cast send`` also exits 0
for a mined revert.

Operational shape
-----------------
The daemon does not own a chain key; the caller supplies one through
``PRIVATE_KEY`` (preferred, since flags show up in process listings) or
``--private-key``. It never appears in dry-run output, which is the
default and usually ends up in logs. The intended deployment is a
low-priv hot wallet that can pay gas for ``expire()`` but holds no other
authority. Running with ``--loop --interval-seconds N`` gives a simple
forever-loop poller; absent ``--loop`` the script does a single sweep
and exits, suitable for cron.
"""
from __future__ import annotations

import argparse
import os
import time
from dataclasses import dataclass
from typing import Any, Callable

from service.control_panel.commands import build_wager_action_command, redact_argv, run_cast_send

from .indexer import db_connect, get_expire_candidates, init_db


@dataclass
class SweepResult:
    attempted: int
    succeeded: int
    failed: int


def _expire_command(wager_address: str, rpc_url: str, private_key: str) -> list[str]:
    return build_wager_action_command(
        wager=wager_address, action="expire", rpc_url=rpc_url, private_key=private_key
    ).command


def sweep_once(
    *,
    db_path: str,
    rpc_url: str,
    private_key: str,
    now_ts: int | None = None,
    execute: bool = False,
    runner: Callable[..., Any] | None = None,
) -> SweepResult:
    """Run one sweep pass over the indexer's candidate list.

    The ``runner`` indirection lets unit tests stub the subprocess call
    without spawning real processes. ``now_ts`` is forwarded to
    :func:`get_expire_candidates` so tests can pin a deterministic clock.

    Dry-run (``execute=False``) counts every candidate as "succeeded"
    because the only failure mode for a dry-run is an exception, which
    we surface by letting it propagate. Live runs count anything short
    of a mined, successful receipt as a failure and capture the reason
    for the operator log.
    """
    conn = db_connect(db_path)
    init_db(conn)
    candidates = get_expire_candidates(conn, now_ts=now_ts)
    conn.close()

    attempted = 0
    succeeded = 0
    failed = 0
    for row in candidates:
        wager = row["wager_address"]
        cmd = _expire_command(wager, rpc_url, private_key)
        attempted += 1
        if not execute:
            print("DRY_RUN", " ".join(redact_argv(cmd)))
            succeeded += 1
            continue
        result = run_cast_send(cmd, runner=runner)
        if result.ok:
            print(f"EXPIRED {wager} tx={result.tx_hash}")
            succeeded += 1
        else:
            print(f"FAILED {wager} rc={result.returncode} stderr={result.stderr.strip()}")
            failed += 1

    return SweepResult(attempted=attempted, succeeded=succeeded, failed=failed)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Paramutuel expire sweeper daemon")
    parser.add_argument("--db-path", default="service/indexer/indexer.db")
    parser.add_argument("--rpc-url", default=os.environ.get("RPC_URL_BASE_SEPOLIA") or os.environ.get("RPC_URL", ""))
    parser.add_argument("--private-key", default=os.environ.get("PRIVATE_KEY", ""), help="Prefer the PRIVATE_KEY env var.")
    parser.add_argument("--execute", action="store_true", help="Execute expire transactions. Default is dry-run.")
    parser.add_argument("--loop", action="store_true", help="Run continuously.")
    parser.add_argument("--interval-seconds", type=int, default=60)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.rpc_url or not args.private_key:
        raise SystemExit("RPC URL and private key are required (--rpc-url / RPC_URL, --private-key / PRIVATE_KEY)")

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
