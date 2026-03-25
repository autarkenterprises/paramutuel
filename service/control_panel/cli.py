#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys

from .commands import build_create_market_command, build_market_action_command


def _split_csv(s: str) -> list[str]:
    if not s:
        return []
    return [x.strip() for x in s.split(",") if x.strip()]


def _split_int_csv(s: str) -> list[int]:
    return [int(x) for x in _split_csv(s)]


def _run_or_print(cmd: list[str], execute: bool) -> int:
    if not execute:
        print(" ".join(cmd))
        return 0
    return subprocess.run(cmd, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Paramutuel resolver/control-panel CLI")
    parser.add_argument("--rpc-url", default=os.environ.get("RPC_URL", ""))
    parser.add_argument("--private-key", default=os.environ.get("PRIVATE_KEY", ""))
    parser.add_argument("--execute", action="store_true", help="Execute cast command. Default prints command only.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("create-market")
    c.add_argument("--factory", required=True)
    c.add_argument("--collateral", required=True)
    c.add_argument("--question", required=True)
    c.add_argument("--outcomes", required=True, help="Comma-separated outcomes")
    c.add_argument("--betting-close-time", type=int, required=True, help="Unix ts or 0")
    c.add_argument("--resolution-window", type=int, required=True, help="seconds or 0")
    c.add_argument("--resolver", default="0x0000000000000000000000000000000000000000")
    c.add_argument("--betting-closer", default="0x0000000000000000000000000000000000000000")
    c.add_argument("--resolution-closer", default="0x0000000000000000000000000000000000000000")
    c.add_argument("--extra-recipients", default="")
    c.add_argument("--extra-bps", default="")

    a = sub.add_parser("market-action")
    a.add_argument("--market", required=True)
    a.add_argument(
        "--action",
        required=True,
        choices=[
            "close-betting",
            "close-resolution-window",
            "resolve",
            "retract",
            "expire",
            "claim",
            "withdraw-fees",
        ],
    )
    a.add_argument("--outcome-index", type=int)

    args = parser.parse_args()
    if not args.rpc_url or not args.private_key:
        print("RPC URL and PRIVATE_KEY are required (flags or env).", file=sys.stderr)
        return 2

    try:
        if args.cmd == "create-market":
            cmd = build_create_market_command(
                factory=args.factory,
                collateral=args.collateral,
                question=args.question,
                outcomes=_split_csv(args.outcomes),
                betting_close_time=args.betting_close_time,
                resolution_window=args.resolution_window,
                resolver=args.resolver,
                betting_closer=args.betting_closer,
                resolution_closer=args.resolution_closer,
                extra_recipients=_split_csv(args.extra_recipients),
                extra_bps=_split_int_csv(args.extra_bps),
                rpc_url=args.rpc_url,
                private_key=args.private_key,
            )
            return _run_or_print(cmd.command, args.execute)

        cmd = build_market_action_command(
            market=args.market,
            action=args.action,
            outcome_index=args.outcome_index,
            rpc_url=args.rpc_url,
            private_key=args.private_key,
        )
        return _run_or_print(cmd.command, args.execute)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
