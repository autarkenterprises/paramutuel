#!/usr/bin/env bash
# Report ETH and USDC balances for the ARG treasury and every microwonk wallet.
#
# Treasury row is printed first with threshold flags:
#   - ETH  < TREASURY_MIN_WEI       → "LOW-ETH"
#   - USDC < TREASURY_MIN_USDC_RAW  → "LOW-USDC"
#   A nonzero count of LOW flags sets exit code 2 (handy for CI / cron).
#
# Requires:
#   - config/microwonk-wallets.json
#   - Env: RPC_URL_BASE_SEPOLIA (or RPC_URL_BASE_MAINNET)
#   - Foundry 'cast' on PATH
#
# Tunables:
#   NETWORK                 base-sepolia | base-mainnet (default base-sepolia)
#   MICROWONK_USDC_TOKEN    USDC address (defaults by network)
#   TREASURY_MIN_WEI        ETH floor in wei (default 0.05 ETH = 5e16)
#   TREASURY_MIN_USDC_RAW   USDC floor raw   (default 200_000_000 = 200 USDC)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

WALLETS_FILE="config/microwonk-wallets.json"
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
  *) echo "error: unsupported NETWORK: $NETWORK" >&2; exit 1 ;;
esac

if [[ -z "${!RPC_ENV:-}" ]]; then
  echo "error: missing env var $RPC_ENV" >&2; exit 1
fi
if ! command -v cast >/dev/null 2>&1; then
  echo "error: 'cast' not found on PATH" >&2; exit 1
fi
if [[ ! -f "$WALLETS_FILE" ]]; then
  echo "error: $WALLETS_FILE not found. Run generate_wallets.sh first." >&2; exit 1
fi

RPC_URL="${!RPC_ENV}"
USDC_TOKEN="${MICROWONK_USDC_TOKEN:-$DEFAULT_USDC}"
MIN_WEI="${TREASURY_MIN_WEI:-50000000000000000}"     # 0.05 ETH
MIN_USDC="${TREASURY_MIN_USDC_RAW:-200000000}"       # 200 USDC

# Treasury first, then proposer/resolver (other roles), then microwonks.
mapfile -t ENTRIES < <(python3 - "$WALLETS_FILE" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
rows = []
treasury = None
others = []
for r, meta in d.get("roles", {}).items():
    row = ("treasury" if meta.get("role") == "treasury" else "role",
           meta["key"], meta["address"])
    if row[0] == "treasury":
        treasury = row
    else:
        others.append(row)
if treasury:
    rows.append(treasury)
rows.extend(others)
for w in d.get("microwonks", []):
    rows.append(("wonk", w["key"], w["address"]))
for kind, k, a in rows:
    print(f"{kind}\t{k}\t{a}")
PY
)

fmt_eth()  { python3 -c "v=int('$1'); print(f'{v/1e18:.6f} ETH')"; }
fmt_usdc() { python3 -c "v=int('$1'); print(f'{v/1e6:.6f} USDC')"; }

printf "%-9s %-20s %-44s %-20s %-22s %s\n" "type" "key" "address" "eth" "usdc" "flags"
printf "%-9s %-20s %-44s %-20s %-22s %s\n" "----" "---" "-------" "---" "----" "-----"

low_flags=0
for line in "${ENTRIES[@]}"; do
  IFS=$'\t' read -r kind key addr <<< "$line"
  eth_raw="$(cast balance "$addr" --rpc-url "$RPC_URL" 2>/dev/null || echo 0)"
  usdc_raw="$(cast call "$USDC_TOKEN" "balanceOf(address)(uint256)" "$addr" --rpc-url "$RPC_URL" 2>/dev/null | awk '{print $1}' || echo 0)"
  usdc_raw="${usdc_raw:-0}"
  flags=""
  if [[ "$kind" == "treasury" ]]; then
    if python3 -c "import sys; sys.exit(0 if int('$eth_raw') < int('$MIN_WEI') else 1)"; then
      flags+="LOW-ETH "
      low_flags=$((low_flags+1))
    fi
    if python3 -c "import sys; sys.exit(0 if int('$usdc_raw') < int('$MIN_USDC') else 1)"; then
      flags+="LOW-USDC "
      low_flags=$((low_flags+1))
    fi
    [[ -z "$flags" ]] && flags="OK"
  fi
  printf "%-9s %-20s %-44s %-20s %-22s %s\n" "$kind" "$key" "$addr" \
    "$(fmt_eth "$eth_raw")" "$(fmt_usdc "$usdc_raw")" "$flags"
done

if (( low_flags > 0 )); then
  echo ""
  echo "warn: $low_flags treasury threshold(s) breached." >&2
  echo "      Top up before running fund_wallets.sh." >&2
  exit 2
fi
