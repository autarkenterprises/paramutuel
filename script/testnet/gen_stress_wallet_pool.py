#!/usr/bin/env python3
"""Generate N random EOAs for Base Sepolia stress tests (Foundry cast).

Writes JSON: [ {"address": "0x...", "private_key": "0x..."}, ... ]

Usage:
  python3 script/testnet/gen_stress_wallet_pool.py 24 test/testnet/stress_wallet_pool.json

Never commit the output file; it contains private keys.
"""
from __future__ import annotations

import json
import subprocess
import sys


def main() -> None:
    if len(sys.argv) != 3:
        print("usage: gen_stress_wallet_pool.py <count> <out.json>", file=sys.stderr)
        sys.exit(2)
    count = int(sys.argv[1])
    out_path = sys.argv[2]
    if count < 1:
        print("error: count must be >= 1", file=sys.stderr)
        sys.exit(1)

    wallets: list[dict[str, str]] = []
    for _ in range(count):
        proc = subprocess.run(
            ["cast", "wallet", "new", "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            print(proc.stderr or proc.stdout, file=sys.stderr)
            sys.exit(1)
        data = json.loads(proc.stdout)
        if isinstance(data, list):
            wallets.extend(data)
        else:
            wallets.append(data)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(wallets, f, indent=2)
        f.write("\n")

    print(f"wrote {len(wallets)} wallets to {out_path}")


if __name__ == "__main__":
    main()
