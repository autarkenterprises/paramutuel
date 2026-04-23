#!/usr/bin/env bash
set -euo pipefail

# Live Base Sepolia integration suite (against deployed contracts).
#
# Defaults to read-only mode (no transactions, no gas):
#   RPC_URL_BASE_SEPOLIA=... ./script/testnet/run_live_suite.sh
#   # optional override: FACTORY_ADDRESS=0x...
#
# Optional existing wager checks:
#   TESTNET_WAGER_ADDRESS=0x...
#
# Minimal transaction mode (low gas):
#   TESTNET_MODE=minimal-tx PRIVATE_KEY=0x... FACTORY_ADDRESS=0x... RPC_URL_BASE_SEPOLIA=... ./script/testnet/run_live_suite.sh
#
# Funded transaction mode (real collateral flow):
#   TESTNET_MODE=funded-tx PRIVATE_KEY=0x... RPC_URL_BASE_SEPOLIA=... ./script/testnet/run_live_suite.sh
#   Optional: TESTNET_COLLATERAL_TOKEN (defaults to Base Sepolia USDC in the Python suite).
#
# V3 payoff-policy matrix (enumerated): TESTNET_V3_CASES filter, TESTNET_SKIP_V3_MATRIX to skip.
# V3 freeform branch: TESTNET_SKIP_FREEFORM to skip. See docs/TESTNET-LIVE-SUITE.md.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

if [[ -f "$ROOT_DIR/config/service.env" || -f "$ROOT_DIR/.env" ]]; then
  source "$ROOT_DIR/script/lib/load_service_env.sh"
fi

source "$ROOT_DIR/script/lib/deployments.sh"
if [[ -z "${FACTORY_ADDRESS:-}" ]]; then
  ensure_factory_address "base-sepolia" "$ROOT_DIR/config/deployments.json" || true
fi
if [[ -z "${FACTORY_ADDRESS:-}" ]]; then
  echo "error: FACTORY_ADDRESS is required (or set config/deployments.json baseSepolia.factoryAddress)" >&2
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
if [[ "$MODE" == "funded-tx" && -z "${PRIVATE_KEY:-}" ]]; then
  echo "error: PRIVATE_KEY is required when TESTNET_MODE=funded-tx" >&2
  exit 1
fi

python3 -m unittest discover -s test/testnet -p "test_live_base_sepolia.py" -v
