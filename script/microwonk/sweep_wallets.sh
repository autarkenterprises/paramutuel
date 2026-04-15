#!/usr/bin/env bash
# Sweep all ETH and USDC from microwonk wallets back to a designated sink.
#
# Default sink: the ARG treasury address from config/microwonk-wallets.json.
# Override with SWEEP_TO=0x...  (e.g. a cold wallet at campaign end).
#
# Requires:
#   - config/microwonk-wallets.json and config/microwonk-keys.env
#   - Env: RPC_URL_BASE_SEPOLIA (or RPC_URL_BASE_MAINNET)
#   - Foundry 'cast' on PATH
#
# Tunables:
#   NETWORK                 base-sepolia | base-mainnet (default base-sepolia)
#   MICROWONK_USDC_TOKEN    USDC address (defaults by network)
#   SWEEP_ETH_LEAVE_WEI     wei to leave per wallet (default 0)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

WALLETS_FILE="config/microwonk-wallets.json"
KEYS_ENV="config/microwonk-keys.env"
LEDGER="config/microwonk-disbursements.log"
NETWORK="${NETWORK:-base-sepolia}"

case "$NETWORK" in
  base-sepolia|base-sepolia-testnet)
    RPC_ENV="RPC_URL_BASE_SEPOLIA"
    DEFAULT_USDC="0x036CbD53842c5426634e7929541eC2318f3dCf7e"
    ;;
  base-mainnet|base)
    RPC_ENV="RPC_URL_BASE_MAINNET"
    DEFAULT_USDC="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    ;;
  *) echo "error: unsupported NETWORK" >&2; exit 1 ;;
esac

if ! command -v cast >/dev/null 2>&1; then
  echo "error: 'cast' not found on PATH" >&2; exit 1
fi
if [[ ! -f "$WALLETS_FILE" || ! -f "$KEYS_ENV" ]]; then
  echo "error: wallet files missing. Run generate_wallets.sh first." >&2; exit 1
fi
if [[ -z "${!RPC_ENV:-}" ]]; then
  echo "error: missing env var $RPC_ENV" >&2; exit 1
fi

# shellcheck disable=SC1090
source "$KEYS_ENV"

RPC_URL="${!RPC_ENV}"
USDC_TOKEN="${MICROWONK_USDC_TOKEN:-$DEFAULT_USDC}"
LEAVE_WEI="${SWEEP_ETH_LEAVE_WEI:-0}"

# Default SWEEP_TO = treasury address from wallets.json, else derive from
# MICROWONK_TREASURY_PRIVATE_KEY, else fallback to PRIVATE_KEY.
if [[ -z "${SWEEP_TO:-}" ]]; then
  SWEEP_TO="$(python3 - "$WALLETS_FILE" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
for meta in d.get("roles", {}).values():
    if meta.get("role") == "treasury":
        print(meta["address"])
        break
PY
)"
fi
if [[ -z "$SWEEP_TO" ]]; then
  src_key="${MICROWONK_TREASURY_PRIVATE_KEY:-${PRIVATE_KEY:-}}"
  if [[ -n "$src_key" ]]; then
    SWEEP_TO="$(cast wallet address --private-key "$src_key")"
  fi
fi
if [[ -z "$SWEEP_TO" ]]; then
  echo "error: could not determine sweep destination. Set SWEEP_TO=0x..." >&2
  exit 1
fi

echo "==> Sweep destination: $SWEEP_TO"
echo "==> Network:           $NETWORK"
echo "==> USDC token:        $USDC_TOKEN"
echo ""

# Skip the treasury row when iterating (it is the default sink).
mapfile -t ENTRIES < <(python3 - "$WALLETS_FILE" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
for r, meta in d.get("roles", {}).items():
    if meta.get("role") == "treasury":
        continue
    print(f"{meta['key']}\t{meta['address']}")
for w in d.get("microwonks", []):
    print(f"{w['key']}\t{w['address']}")
PY
)

ledger_append() {
  # $1=asset $2=amount_raw $3=from $4=wallet_key $5=tx_hash
  local ts
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  # Leading minus prefix in amount_raw flags a sweep (treasury is receiver).
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$ts" "$NETWORK" "$1" "-$2" "$3" "$SWEEP_TO" "$4" "$5" >> "$LEDGER"
}

for line in "${ENTRIES[@]}"; do
  IFS=$'\t' read -r key addr <<< "$line"
  var="MICROWONK_KEY_$(echo "$key" | tr '[:lower:]' '[:upper:]')"
  pk="${!var:-}"
  if [[ -z "$pk" ]]; then
    echo "warn: no key exported for $key ($var); skipping" >&2
    continue
  fi

  usdc_raw="$(cast call "$USDC_TOKEN" "balanceOf(address)(uint256)" "$addr" --rpc-url "$RPC_URL" 2>/dev/null | awk '{print $1}')"
  usdc_raw="${usdc_raw:-0}"
  if [[ "$usdc_raw" != "0" ]]; then
    echo "--> $key: transfer $usdc_raw USDC-raw -> $SWEEP_TO"
    tx="$(cast send "$USDC_TOKEN" "transfer(address,uint256)" "$SWEEP_TO" "$usdc_raw" \
      --rpc-url "$RPC_URL" --private-key "$pk" --confirmations 1 --json 2>/dev/null \
      | python3 -c 'import json,sys;print(json.load(sys.stdin).get("transactionHash",""))' 2>/dev/null || echo "")"
    ledger_append "USDC" "$usdc_raw" "$addr" "$key" "$tx"
  fi

  eth_raw="$(cast balance "$addr" --rpc-url "$RPC_URL" 2>/dev/null || echo 0)"
  gas_price="$(cast gas-price --rpc-url "$RPC_URL" 2>/dev/null || echo 1000000000)"
  gas_cost=$(python3 -c "print(int($gas_price) * 21000 * 2)")
  send_wei=$(python3 -c "v=int($eth_raw)-int($LEAVE_WEI)-int($gas_cost); print(max(v,0))")
  if [[ "$send_wei" == "0" ]]; then
    echo "    $key: ETH balance below sweep threshold; skipping"
    continue
  fi
  echo "--> $key: send $send_wei wei -> $SWEEP_TO"
  tx="$(cast send "$SWEEP_TO" --value "$send_wei" \
    --rpc-url "$RPC_URL" --private-key "$pk" --confirmations 1 --json 2>/dev/null \
    | python3 -c 'import json,sys;print(json.load(sys.stdin).get("transactionHash",""))' 2>/dev/null || echo "")"
  ledger_append "ETH" "$send_wei" "$addr" "$key" "$tx"
done

echo ""
echo "==> Sweep complete. Ledger appended to $LEDGER"
