#!/usr/bin/env bash
# Fund addresses from a stress wallet pool JSON (see gen_stress_wallet_pool.py).
#
# Usage:
#   RPC_URL_BASE_SEPOLIA=... PRIVATE_KEY=0xFUNDER \
#   STRESS_POOL_PATH=test/testnet/stress_wallet_pool.json \
#   STRESS_FUND_WEI=5000000000000000 \
#   ./script/testnet/fund_stress_wallets.sh
#
# Default sends 0.005 ETH per address (5e15 wei).

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "error: missing required env var: $name" >&2
    exit 1
  fi
}

require_env "PRIVATE_KEY"
require_env "RPC_URL_BASE_SEPOLIA"
POOL="${STRESS_POOL_PATH:-test/testnet/stress_wallet_pool.json}"
WEI="${STRESS_FUND_WEI:-5000000000000000}"

if [[ ! -f "$POOL" ]]; then
  echo "error: pool file not found: $POOL" >&2
  exit 1
fi

if command -v jq >/dev/null 2>&1; then
  mapfile -t ADDRS < <(jq -r '.[].address' "$POOL" | sort -u)
else
  mapfile -t ADDRS < <(python3 -c "
import json
from pathlib import Path
w = json.loads(Path('$POOL').read_text())
seen = set()
for x in w:
    a = x['address'].lower()
    if a not in seen:
        seen.add(a)
        print(x['address'])
")
fi

echo "==> Funding ${#ADDRS[@]} unique addresses with ${WEI} wei each"
for addr in "${ADDRS[@]}"; do
  echo "    -> $addr"
  cast send "$addr" --value "$WEI" --rpc-url "$RPC_URL_BASE_SEPOLIA" --private-key "$PRIVATE_KEY"
done
echo "==> Done"
