#!/usr/bin/env python3
"""Advise the operator (human + Claude) on which faucet to visit next.

Reads:
  config/faucet-playbook.json       -- faucet catalog (committed)
  config/microwonk-loading-docks.json -- dock addresses (committed)
  config/faucet-state.json          -- per-(faucet, address) timestamps (gitignored)

Writes:
  config/faucet-state.json          -- updated after each `record` call

Subcommands:
  next                List every (faucet, dock) pair that is eligible now.
  record <faucet> <dock_key> [tx_hash] [--asset ETH|USDC] [--amount-raw N]
                      Record a successful drip; timestamp advances the counter.
  progress            Print remaining ETH/USDC to hit the treasury targets.
  resume              Machine-readable JSON plan for Claude to drive Chrome.

Usage:
  python3 script/microwonk/next_faucet_run.py next
  python3 script/microwonk/next_faucet_run.py progress
  python3 script/microwonk/next_faucet_run.py record coinbase_cdp_base_sepolia dock_01 0xabc...
  python3 script/microwonk/next_faucet_run.py resume
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PLAYBOOK = ROOT / "config" / "faucet-playbook.json"
DOCKS = ROOT / "config" / "microwonk-loading-docks.json"
WALLETS = ROOT / "config" / "microwonk-wallets.json"
STATE = ROOT / "config" / "faucet-state.json"


def load_json(path: pathlib.Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_ts(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def state_get() -> dict:
    if not STATE.exists():
        return {"visits": []}
    return json.loads(STATE.read_text())


def state_put(state: dict) -> None:
    STATE.write_text(json.dumps(state, indent=2) + "\n")


def docks() -> list[dict]:
    d = load_json(DOCKS)
    return d.get("docks", [])


def playbook() -> dict:
    if not PLAYBOOK.exists():
        print(f"error: {PLAYBOOK} missing", file=sys.stderr)
        sys.exit(1)
    return load_json(PLAYBOOK)


def eligible(faucet: dict, address: str, visits: list[dict]) -> tuple[bool, str]:
    """Return (eligible, reason)."""
    relevant = [v for v in visits
                if v.get("faucet") == faucet["id"] and v.get("address", "").lower() == address.lower()]
    if not relevant:
        return True, "never visited"
    last = max(parse_ts(v["ts"]) for v in relevant)
    age = (now() - last).total_seconds()
    if "ratePerHourPerAddress" in faucet and faucet["ratePerHourPerAddress"]:
        needed = 3600 / faucet["ratePerHourPerAddress"]
        if age < needed:
            return False, f"cooldown {int(needed - age)}s (last {last.isoformat()})"
    if "ratePerDayPerAddress" in faucet and faucet["ratePerDayPerAddress"]:
        needed = 86400 / faucet["ratePerDayPerAddress"]
        if age < needed:
            return False, f"cooldown {int((needed - age)/60)}m (last {last.isoformat()})"
    return True, f"last visit {last.isoformat()}"


def cmd_next() -> None:
    pb = playbook()
    state = state_get()
    dks = docks()
    if not dks:
        print("no loading docks; run ./script/microwonk/loading_dock_init.sh 3", file=sys.stderr)
        sys.exit(1)

    print(f"{'faucet':<32} {'asset':<5} {'dock':<10} {'address':<44} {'status'}")
    print("-" * 110)
    for f in pb["faucets"]:
        for d in dks:
            ok, reason = eligible(f, d["address"], state.get("visits", []))
            tag = "READY" if ok else "wait"
            print(f"{f['id']:<32} {f['asset']:<5} {d['key']:<10} {d['address']:<44} {tag}  {reason}")


def cmd_record(args: argparse.Namespace) -> None:
    pb = playbook()
    faucet = next((f for f in pb["faucets"] if f["id"] == args.faucet), None)
    if not faucet:
        print(f"error: unknown faucet id '{args.faucet}'", file=sys.stderr)
        sys.exit(1)
    d = next((x for x in docks() if x["key"] == args.dock), None)
    if not d:
        print(f"error: unknown dock key '{args.dock}'", file=sys.stderr)
        sys.exit(1)
    asset = args.asset or faucet["asset"]
    amount = args.amount_raw
    if amount is None:
        amount = faucet.get("dripWei") if asset == "ETH" else faucet.get("dripRaw")
    state = state_get()
    state.setdefault("visits", []).append({
        "ts": now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "faucet": faucet["id"],
        "address": d["address"],
        "dock": d["key"],
        "asset": asset,
        "amount_raw": str(amount) if amount else None,
        "tx_hash": args.tx_hash,
    })
    state_put(state)
    print(f"recorded {faucet['id']} -> {d['key']} ({amount or '?'} raw {asset})")


def treasury_progress() -> dict:
    pb = playbook()
    wallets = load_json(WALLETS)
    addr = (wallets.get("roles") or {}).get("treasury", {}).get("address")
    target_eth = int(pb["targets"]["treasuryMinEthWei"])
    target_usdc = int(pb["targets"]["treasuryMinUsdcRaw"])
    if not addr:
        return {"treasury": None, "target_eth_wei": target_eth, "target_usdc_raw": target_usdc}
    # Try to query balances via cast; if unavailable, return None.
    def cast_try(args: list[str]) -> str | None:
        try:
            r = subprocess.run(args, capture_output=True, text=True, check=True, timeout=15)
            return r.stdout.strip()
        except Exception:
            return None

    eth_raw = cast_try(["cast", "balance", addr, "--rpc-url", "${RPC_URL_BASE_SEPOLIA}"])
    # cast doesn't expand env vars; pass the actual URL if set in env.
    import os
    rpc = os.environ.get("RPC_URL_BASE_SEPOLIA")
    if rpc:
        eth_raw = cast_try(["cast", "balance", addr, "--rpc-url", rpc])
        usdc_raw = cast_try([
            "cast", "call", "0x036CbD53842c5426634e7929541eC2318f3dCf7e",
            "balanceOf(address)(uint256)", addr, "--rpc-url", rpc,
        ])
        if usdc_raw:
            usdc_raw = usdc_raw.split()[0]
    else:
        eth_raw = usdc_raw = None
    return {
        "treasury": addr,
        "eth_raw": eth_raw,
        "usdc_raw": usdc_raw,
        "target_eth_wei": target_eth,
        "target_usdc_raw": target_usdc,
    }


def cmd_progress() -> None:
    p = treasury_progress()
    if not p["treasury"]:
        print("no treasury yet; run treasury_init.sh or generate_wallets.sh")
        return
    print(f"treasury       : {p['treasury']}")
    if p.get("eth_raw") is None:
        print("ETH / USDC balances: set RPC_URL_BASE_SEPOLIA to query live.")
    else:
        have_eth = int(p["eth_raw"])
        have_usdc = int(p["usdc_raw"] or 0)
        target_eth = p["target_eth_wei"]
        target_usdc = p["target_usdc_raw"]
        eth_status = "OK" if have_eth >= target_eth else f"need {(target_eth-have_eth)/1e18:.6f} more"
        usdc_status = "OK" if have_usdc >= target_usdc else f"need {(target_usdc-have_usdc)/1e6:.6f} more"
        print(f"eth  have/need : {have_eth/1e18:.6f} / {target_eth/1e18:.6f} ETH   ({eth_status})")
        print(f"usdc have/need : {have_usdc/1e6:.6f} / {target_usdc/1e6:.6f} USDC   ({usdc_status})")


def cmd_resume() -> None:
    """Emit a structured plan for Claude to drive Chrome automation."""
    pb = playbook()
    state = state_get()
    dks = docks()
    plan = {"ready": [], "waiting": []}
    for f in pb["faucets"]:
        for d in dks:
            ok, reason = eligible(f, d["address"], state.get("visits", []))
            entry = {
                "faucet_id": f["id"],
                "asset": f["asset"],
                "url": f["url"],
                "dock_key": d["key"],
                "dock_address": d["address"],
                "auth": f.get("auth"),
                "captcha": f.get("captcha", False),
                "human_step": f.get("humanStep"),
                "claude_step": f.get("claudeStep"),
                "reason": reason,
            }
            (plan["ready"] if ok else plan["waiting"]).append(entry)
    plan["progress"] = treasury_progress()
    print(json.dumps(plan, indent=2, default=str))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("next")
    sub.add_parser("progress")
    sub.add_parser("resume")
    rec = sub.add_parser("record")
    rec.add_argument("faucet")
    rec.add_argument("dock")
    rec.add_argument("tx_hash", nargs="?", default=None)
    rec.add_argument("--asset", choices=["ETH", "USDC"], default=None)
    rec.add_argument("--amount-raw", type=str, default=None)
    args = ap.parse_args()

    if args.cmd == "next":
        cmd_next()
    elif args.cmd == "record":
        cmd_record(args)
    elif args.cmd == "progress":
        cmd_progress()
    elif args.cmd == "resume":
        cmd_resume()
    else:
        ap.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
