#!/usr/bin/env bash
# Batch-forward ETH and USDC from every loading-dock EOA to the ARG treasury.
# Safe to re-run; idempotent; skips empty docks.
#
# Requires:
#   - config/microwonk-loading-docks.json  (run loading_dock_init.sh first)
#   - config/microwonk-wallets.json        (for treasury address)
#   - config/microwonk-keys.env sourced    (dock private keys as MICROWONK_KEY_DOCK_NN)
#   - Env: RPC_URL_BASE_SEPOLIA (or RPC_URL_BASE_MAINNET)
#   - Foundry 'cast' on PATH
#
# Tunables:
#   NETWORK                 base-sepolia | base-mainnet (default base-sepolia)
#   MICROWONK_USDC_TOKEN    USDC address (defaults by network)
#   DOCK_ETH_LEAVE_WEI      wei to leave on each dock (default 0)
#   DOCK_MIN_ETH_WEI        minimum ETH to attempt a transfer (default 2e14 = 0.0002 ETH)
#
# Side effects:
#   Appends one LOAD-prefixed row per (dock, asset) transfer to
#   config/microwonk-disbursements.log.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

DOCKS="config/microwonk-loading-docks.json"
WALLETS="config/microwonk-wallets.json"
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
if [[ ! -f "$DOCKS" ]]; then
  echo "error: $DOCKS not found. Run loading_dock_init.sh first." >&2; exit 1
fi
if [[ ! -f "$WALLETS" ]]; then
  echo "error: $WALLETS not found. Run generate_wallets.sh first." >&2; exit 1
fi
if [[ -z "${!RPC_ENV:-}" ]]; then
  echo "error: missing env var $RPC_ENV" >&2; exit 1
fi

RPC_URL="${!RPC_ENV}"
USDC_TOKEN="${MICROWONK_USDC_TOKEN:-$DEFAULT_USDC}"
LEAVE_WEI="${DOCK_ETH_LEAVE_WEI:-0}"
MIN_ETH_WEI="${DOCK_MIN_ETH_WEI:-200000000000000}"  # 0.0002 ETH floor

TREASURY_ADDR="$(python3 - "$WALLETS" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
print((d.get("roles") or {}).get("treasury", {}).get("address", ""))
PY
)"

if [[ -z "$TREASURY_ADDR" ]]; then
  echo "error: could not find treasury address in $WALLETS. Run treasury_init.sh." >&2
  exit 1
fi

echo "==> Treasury: $TREASURY_ADDR"
echo "==> Network:  $NETWORK"
echo "==> USDC:     $USDC_TOKEN"
echo ""

mapfile -t DOCK_ENTRIES < <(python3 - "$DOCKS" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
for x in d.get("docks", []):
    print(f"{x['key']}\t{x['address']}")
PY
)

ledger_append() {
  # $1=asset $2=amount_raw $3=from $4=key $5=tx_hash
  local ts; ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'LOAD\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$ts" "$NETWORK" "$1" "$2" "$3" "$TREASURY_ADDR" "$4" "$5" >> "$LEDGER"
}

any_moved=0

for line in "${DOCK_ENTRIES[@]}"; do
  IFS=$'\t' read -r key addr <<< "$line"
  # Upper-cased env var: dock_01 -> MICROWONK_KEY_DOCK_01
  var="MICROWONK_KEY_$(echo "$key" | tr '[:lower:]' '[:upper:]')"
  pk="${!var:-}"
  if [[ -z "$pk" ]]; then
    echo "warn: no key exported for $key ($var); skipping" >&2
    continue
  fi

  # USDC sweep
  usdc_raw="$(cast call "$USDC_TOKEN" "balanceOf(address)(uint256)" "$addr" \
    --rpc-url "$RPC_URL" 2>/dev/null | awk '{print $1}')"
  usdc_raw="${usdc_raw:-0}"
  if [[ "$usdc_raw" != "0" ]]; then
    echo "--> $key: forward $usdc_raw USDC-raw -> treasury"
    tx="$(cast send "$USDC_TOKEN" "transfer(address,uint256)" "$TREASURY_ADDR" "$usdc_raw" \
      --rpc-url "$RPC_URL" --private-key "$pk" --confirmations 1 --json 2>/dev/null \
      | python3 -c 'import json,sys;print(json.load(sys.stdin).get("transactionHash",""))' 2>/dev/null || echo "")"
    ledger_append "USDC" "$usdc_raw" "$addr" "$key" "$tx"
    any_moved=1
  fi

  # ETH sweep (leave gas buffer)
  eth_raw="$(cast balance "$addr" --rpc-url "$RPC_URL" 2>/dev/null || echo 0)"
  gas_price="$(cast gas-price --rpc-url "$RPC_URL" 2>/dev/null || echo 1000000000)"
  gas_cost=$(python3 -c "print(int($gas_price) * 21000 * 2)")
  send_wei=$(python3 -c "v=int($eth_raw)-int($LEAVE_WEI)-int($gas_cost); print(max(v,0))")
  if python3 -c "import sys; sys.exit(0 if int('$send_wei') < int('$MIN_ETH_WEI') else 1)"; then
    echo "    $key: ETH balance below floor ($send_wei wei < $MIN_ETH_WEI); skipping"
    continue
  fi
  echo "--> $key: forward $send_wei wei -> treasury"
  tx="$(cast send "$TREASURY_ADDR" --value "$send_wei" \
    --rpc-url "$RPC_URL" --private-key "$pk" --confirmations 1 --json 2>/dev/null \
    | python3 -c 'import json,sys;print(json.load(sys.stdin).get("transactionHash",""))' 2>/dev/null || echo "")"
  ledger_append "ETH" "$send_wei" "$addr" "$key" "$tx"
  any_moved=1
done

if (( any_moved == 0 )); then
  echo "==> All docks empty (above floor). Nothing to forward."
else
  echo ""
  echo "==> Load complete. Ledger appended to $LEDGER"
  echo "==> Run ./script/microwonk/check_balances.sh to verify treasury."
fi
