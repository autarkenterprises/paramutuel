#!/usr/bin/env bash
set -euo pipefail

# Multi-market, multi-actor stress suite against deployed Base Sepolia contracts.
#
# Read-only (no gas): samples latest markets from the factory.
#   FACTORY_ADDRESS=0x... RPC_URL_BASE_SEPOLIA=... ./script/testnet/run_stress_suite.sh
#
# Transaction mode: creates markets with distinct roles from a wallet pool JSON.
#   FACTORY_ADDRESS=... RPC_URL_BASE_SEPOLIA=... \
#   STRESS_MODE=tx STRESS_WALLET_POOL_PATH=test/testnet/stress_wallet_pool.json \
#   STRESS_FUNDER_PRIVATE_KEY=0x... \
#   ./script/testnet/run_stress_suite.sh
#
# Generate pool (do not commit):
#   python3 script/testnet/gen_stress_wallet_pool.py 40 test/testnet/stress_wallet_pool.json
# Fund actors (optional):
#   STRESS_POOL_PATH=test/testnet/stress_wallet_pool.json ./script/testnet/fund_stress_wallets.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

if [[ -z "${FACTORY_ADDRESS:-}" ]]; then
  echo "error: FACTORY_ADDRESS is required" >&2
  exit 1
fi

if [[ -z "${RPC_URL_BASE_SEPOLIA:-${RPC_URL_SEPOLIA:-}}" ]]; then
  echo "error: set RPC_URL_BASE_SEPOLIA (or RPC_URL_SEPOLIA)" >&2
  exit 1
fi

MODE="${STRESS_MODE:-readonly}"
echo "==> Stress suite mode: ${MODE}"

if [[ "$MODE" == "tx" ]]; then
  if [[ -z "${STRESS_WALLET_POOL_PATH:-}" ]]; then
    echo "error: STRESS_WALLET_POOL_PATH required for STRESS_MODE=tx" >&2
    exit 1
  fi
  if [[ ! -f "$STRESS_WALLET_POOL_PATH" ]]; then
    echo "error: wallet pool not found: $STRESS_WALLET_POOL_PATH" >&2
    exit 1
  fi
  export STRESS_WALLET_POOL_PATH
  if [[ -n "${STRESS_FUNDER_PRIVATE_KEY:-}" ]]; then
    export PRIVATE_KEY="$STRESS_FUNDER_PRIVATE_KEY"
  fi
fi

export STRESS_MODE="$MODE"
export FACTORY_ADDRESS
export RPC_URL_BASE_SEPOLIA="${RPC_URL_BASE_SEPOLIA:-${RPC_URL_SEPOLIA:-}}"

python3 -m unittest discover -s test/testnet -p "test_stress_base_sepolia.py" -v
