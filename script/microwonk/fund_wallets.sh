#!/usr/bin/env bash
# Distribute testnet ETH (gas) and USDC (bets) from the ARG treasury to all
# microwonk wallets listed in config/microwonk-wallets.json.
#
# Funding key resolution (first match wins):
#   1. MICROWONK_TREASURY_PRIVATE_KEY  (preferred; dedicated ARG treasury)
#   2. PRIVATE_KEY                     (fallback; shares the Proposition Service key)
#
# Requires:
#   - config/microwonk-wallets.json (run generate_wallets.sh first)
#   - Env: RPC_URL_BASE_SEPOLIA (or RPC_URL_BASE_MAINNET)
#   - Foundry 'cast' on PATH
#
# Tunables:
#   MICROWONK_FUND_WEI     per-wallet ETH in wei     (default 0.01 ETH = 1e16)
#   MICROWONK_USDC_TOKEN   USDC address              (default Base Sepolia USDC)
#   MICROWONK_USDC_RAW     per-wallet USDC raw units (default 50_000_000 = 50 USDC @ 6dp)
#   MICROWONK_ROLE_MULT    multiplier for proposer/resolver (default 5)
#   NETWORK                "base-sepolia" | "base-mainnet" (default base-sepolia)
#
# Side effects:
#   Appends a record of every disbursement to config/microwonk-disbursements.log
#   (committed, no secrets) — one row per (wallet, asset) pair.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

WALLETS_FILE="config/microwonk-wallets.json"
LEDGER="config/microwonk-disbursements.log"
NETWORK="${NETWORK:-base-sepolia}"

case "$NETWORK" in
  base-sepolia|base-sepolia-testnet)
    RPC_ENV="RPC_URL_BASE_SEPOLIA"
    DEFAULT_USDC="0x036CbD53842c5426634e7929541eC2318f3dCf7e"  # Base Sepolia USDC
    ;;
  base-mainnet|base)
    RPC_ENV="RPC_URL_BASE_MAINNET"
    DEFAULT_USDC="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # Base mainnet USDC
    ;;
  *)
    echo "error: unsupported NETWORK: $NETWORK" >&2
    exit 1
    ;;
esac

# Resolve funder key (treasury preferred, PRIVATE_KEY fallback).
TREASURY_KEY="${MICROWONK_TREASURY_PRIVATE_KEY:-${PRIVATE_KEY:-}}"
if [[ -z "$TREASURY_KEY" ]]; then
  echo "error: set MICROWONK_TREASURY_PRIVATE_KEY (preferred) or PRIVATE_KEY" >&2
  exit 1
fi
if [[ "${MICROWONK_TREASURY_PRIVATE_KEY:-}" == "" ]]; then
  echo "warn: using PRIVATE_KEY as funder (shared with Proposition Service)." >&2
  echo "      Consider setting MICROWONK_TREASURY_PRIVATE_KEY for role separation." >&2
fi

if [[ -z "${!RPC_ENV:-}" ]]; then
  echo "error: missing required env var: $RPC_ENV" >&2
  exit 1
fi
if ! command -v cast >/dev/null 2>&1; then
  echo "error: 'cast' not found on PATH. Install Foundry." >&2
  exit 1
fi
if [[ ! -f "$WALLETS_FILE" ]]; then
  echo "error: $WALLETS_FILE not found. Run generate_wallets.sh first." >&2
  exit 1
fi

RPC_URL="${!RPC_ENV}"
WEI="${MICROWONK_FUND_WEI:-10000000000000000}"           # 0.01 ETH
USDC_TOKEN="${MICROWONK_USDC_TOKEN:-$DEFAULT_USDC}"
USDC_RAW="${MICROWONK_USDC_RAW:-50000000}"               # 50 USDC
ROLE_MULT="${MICROWONK_ROLE_MULT:-5}"

# Entries exclude the treasury itself (it is the funder, not a recipient).
mapfile -t ENTRIES < <(python3 - "$WALLETS_FILE" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
for r, meta in d.get("roles", {}).items():
    if meta.get("role") == "treasury":
        continue
    print(f"role\t{meta['address']}\t{meta['key']}")
for w in d.get("microwonks", []):
    print(f"wonk\t{w['address']}\t{w['key']}")
PY
)

FUNDER_ADDRESS="$(cast wallet address --private-key "$TREASURY_KEY")"
echo "==> Treasury: $FUNDER_ADDRESS"
echo "==> Network:  $NETWORK"
echo "==> USDC:     $USDC_TOKEN"
echo "==> Base:     $WEI wei ETH, $USDC_RAW raw USDC per recipient"
echo "==> Role multiplier (proposer/resolver): ${ROLE_MULT}x"
echo ""

# Initialise ledger if missing.
if [[ ! -f "$LEDGER" ]]; then
  {
    echo "# microwonk disbursement ledger (append-only, no secrets)"
    echo "# columns: iso_ts\tnetwork\tasset\tamount_raw\tfrom\tto\twallet_key\ttx_hash"
  } > "$LEDGER"
fi

ledger_append() {
  # $1=asset $2=amount_raw $3=to $4=wallet_key $5=tx_hash
  local ts
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$ts" "$NETWORK" "$1" "$2" "$FUNDER_ADDRESS" "$3" "$4" "$5" >> "$LEDGER"
}

pending_nonce() {
  cast rpc --rpc-url "$RPC_URL" eth_getTransactionCount "$FUNDER_ADDRESS" pending | tr -d '"'
}

send_value() {
  local to="$1" value="$2" attempt=1 nonce output tx
  while true; do
    nonce="$(pending_nonce)"
    if output="$(cast send "$to" --value "$value" --rpc-url "$RPC_URL" --private-key "$TREASURY_KEY" --nonce "$nonce" --confirmations 1 --json 2>&1)"; then
      tx="$(printf '%s' "$output" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("transactionHash",""))' 2>/dev/null || echo "")"
      printf '%s' "$tx"
      return 0
    fi
    if [[ "$output" == *"replacement transaction underpriced"* || "$output" == *"nonce too low"* ]]; then
      if (( attempt >= 5 )); then echo "$output" >&2; return 1; fi
      attempt=$((attempt + 1)); sleep 1; continue
    fi
    echo "$output" >&2
    return 1
  done
}

send_usdc() {
  local to="$1" amt="$2" attempt=1 nonce output tx
  while true; do
    nonce="$(pending_nonce)"
    if output="$(cast send "$USDC_TOKEN" "transfer(address,uint256)" "$to" "$amt" --rpc-url "$RPC_URL" --private-key "$TREASURY_KEY" --nonce "$nonce" --confirmations 1 --json 2>&1)"; then
      tx="$(printf '%s' "$output" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("transactionHash",""))' 2>/dev/null || echo "")"
      printf '%s' "$tx"
      return 0
    fi
    if [[ "$output" == *"replacement transaction underpriced"* || "$output" == *"nonce too low"* ]]; then
      if (( attempt >= 5 )); then echo "$output" >&2; return 1; fi
      attempt=$((attempt + 1)); sleep 1; continue
    fi
    echo "$output" >&2
    return 1
  done
}

for line in "${ENTRIES[@]}"; do
  IFS=$'\t' read -r flag addr key <<< "$line"
  if [[ "$flag" == "role" ]]; then
    value_wei=$(python3 -c "print(int($WEI) * int($ROLE_MULT))")
    usdc_amt=$(python3 -c "print(int($USDC_RAW) * int($ROLE_MULT))")
  else
    value_wei="$WEI"
    usdc_amt="$USDC_RAW"
  fi
  echo "--> $key ($flag) $addr"
  if [[ "$value_wei" -gt 0 ]]; then
    echo "    ETH  $value_wei wei"
    tx_eth="$(send_value "$addr" "$value_wei")"
    ledger_append "ETH" "$value_wei" "$addr" "$key" "$tx_eth"
  else
    echo "    ETH  skipped (MICROWONK_FUND_WEI=0)"
  fi
  if [[ "$usdc_amt" -gt 0 ]]; then
    echo "    USDC $usdc_amt raw"
    tx_usdc="$(send_usdc "$addr" "$usdc_amt")"
    ledger_append "USDC" "$usdc_amt" "$addr" "$key" "$tx_usdc"
  else
    echo "    USDC skipped (MICROWONK_USDC_RAW=0)"
  fi
done

echo ""
echo "==> Funding complete. Ledger appended to $LEDGER"
echo "==> Run ./script/microwonk/check_balances.sh to verify."
