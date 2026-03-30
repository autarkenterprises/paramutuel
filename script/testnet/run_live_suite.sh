#!/usr/bin/env bash
set -euo pipefail

# Live Base Sepolia integration suite (against deployed contracts).
#
# Defaults to read-only mode (no transactions, no gas):
#   FACTORY_ADDRESS=0x... RPC_URL_BASE_SEPOLIA=... ./script/testnet/run_live_suite.sh
#
# Optional existing market checks:
#   TESTNET_MARKET_ADDRESS=0x...
#
# Minimal transaction mode (low gas):
#   TESTNET_MODE=minimal-tx PRIVATE_KEY=0x... FACTORY_ADDRESS=0x... RPC_URL_BASE_SEPOLIA=... ./script/testnet/run_live_suite.sh
#
# Funded transaction mode (real collateral flow):
#   TESTNET_MODE=funded-tx PRIVATE_KEY=0x... TESTNET_COLLATERAL_TOKEN=0x... FACTORY_ADDRESS=0x... RPC_URL_BASE_SEPOLIA=... ./script/testnet/run_live_suite.sh

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

MODE="${TESTNET_MODE:-readonly}"
echo "==> Running live suite in mode: ${MODE}"
if [[ "$MODE" == "minimal-tx" && -z "${PRIVATE_KEY:-}" ]]; then
  echo "error: PRIVATE_KEY is required when TESTNET_MODE=minimal-tx" >&2
  exit 1
fi
if [[ "$MODE" == "funded-tx" ]]; then
  if [[ -z "${PRIVATE_KEY:-}" ]]; then
    echo "error: PRIVATE_KEY is required when TESTNET_MODE=funded-tx" >&2
    exit 1
  fi
  if [[ -z "${TESTNET_COLLATERAL_TOKEN:-}" ]]; then
    echo "error: TESTNET_COLLATERAL_TOKEN is required when TESTNET_MODE=funded-tx" >&2
    exit 1
  fi
fi

python3 -m unittest discover -s test/testnet -p "test_live_base_sepolia.py" -v
