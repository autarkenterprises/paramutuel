#!/usr/bin/env bash
# Fund stress wallet pool addresses with Base Sepolia USDC from a funder key.
#
# Usage:
#   RPC_URL_BASE_SEPOLIA=... PRIVATE_KEY=0xFUNDER \
#   STRESS_POOL_PATH=test/testnet/stress_wallet_pool.json \
#   STRESS_USDC_TOKEN=0x036CbD53842c5426634e7929541eC2318f3dCf7e \
#   STRESS_USDC_AMOUNT_RAW=100000 \
#   ./script/testnet/fund_stress_wallets_usdc.sh
#
# Default amount is 100000 raw units (0.1 USDC at 6 decimals).

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
USDC_TOKEN="${STRESS_USDC_TOKEN:-0x036CbD53842c5426634e7929541eC2318f3dCf7e}"
AMOUNT_RAW="${STRESS_USDC_AMOUNT_RAW:-100000}"

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

FUNDER_ADDRESS="$(cast wallet address --private-key "$PRIVATE_KEY")"
pending_nonce() {
  cast rpc --rpc-url "$RPC_URL_BASE_SEPOLIA" eth_getTransactionCount "$FUNDER_ADDRESS" pending | tr -d '"'
}

echo "==> Funding ${#ADDRS[@]} unique addresses with ${AMOUNT_RAW} raw USDC each"
for addr in "${ADDRS[@]}"; do
  echo "    -> $addr"
  attempt=1
  while true; do
    nonce="$(pending_nonce)"
    if output="$(cast send "$USDC_TOKEN" "transfer(address,uint256)" "$addr" "$AMOUNT_RAW" --rpc-url "$RPC_URL_BASE_SEPOLIA" --private-key "$PRIVATE_KEY" --nonce "$nonce" --confirmations 1 2>&1)"; then
      echo "$output"
      break
    fi
    if [[ "$output" == *"replacement transaction underpriced"* || "$output" == *"nonce too low"* ]]; then
      if (( attempt >= 5 )); then
        echo "$output" >&2
        exit 1
      fi
      attempt=$((attempt + 1))
      sleep 1
      continue
    fi
    echo "$output" >&2
    exit 1
  done
done
echo "==> Done"
