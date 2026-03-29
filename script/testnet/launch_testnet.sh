#!/usr/bin/env bash
set -euo pipefail

# Full testnet launch helper.
# Usage:
#   RPC_URL_BASE_SEPOLIA=... PRIVATE_KEY=... TREASURY_ADDRESS=... ./script/testnet/launch_testnet.sh

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
require_env "TREASURY_ADDRESS"

# Preferred variable for reconciled chain decision (Base primary).
RPC_URL="${RPC_URL_BASE_SEPOLIA:-${RPC_URL_SEPOLIA:-}}"
if [[ -z "$RPC_URL" ]]; then
  echo "error: missing required env var: RPC_URL_BASE_SEPOLIA (or legacy RPC_URL_SEPOLIA)" >&2
  exit 1
fi

PROTOCOL_FEE_BPS="${PROTOCOL_FEE_BPS:-200}"
MIN_BETTING_WINDOW="${MIN_BETTING_WINDOW:-3600}"
MIN_RESOLUTION_WINDOW="${MIN_RESOLUTION_WINDOW:-3600}"
INDEXER_DB_PATH="${INDEXER_DB_PATH:-service/indexer/indexer.db}"

echo "==> Preflight checks"
forge --version >/dev/null
cast --version >/dev/null
python3 --version >/dev/null
node --version >/dev/null

echo "==> Quality gates"
forge test -q
PYTHONPATH=. python3 -m unittest discover -s service/indexer/tests -p "test_*.py" -q
PYTHONPATH=. python3 -m unittest discover -s service/explorer/tests -p "test_*.py" -q
PYTHONPATH=. python3 -m unittest discover -s service/control_panel/tests -p "test_*.py" -q
node --check dapp/app.js
node --test dapp/tests/logic.test.js >/dev/null

echo "==> Deploying factory to testnet"
export PRIVATE_KEY TREASURY_ADDRESS PROTOCOL_FEE_BPS MIN_BETTING_WINDOW MIN_RESOLUTION_WINDOW
forge script script/DeployFactory.s.sol \
  --rpc-url "$RPC_URL" \
  --broadcast

echo
echo "Factory deployment broadcasted."
echo "Next:"
echo "  1) record the deployed factory address from script output"
echo "  2) start indexer sync:"
echo "     python3 service/indexer/indexer.py --rpc-url \"$RPC_URL\" --factory-address <FACTORY> --db-path \"$INDEXER_DB_PATH\""
echo "  3) start indexer API:"
echo "     python3 -m service.indexer.api --db-path \"$INDEXER_DB_PATH\" --host 127.0.0.1 --port 8090"
echo "  4) start explorer:"
echo "     python3 -m service.explorer.server --indexer-base-url http://127.0.0.1:8090 --port 8091"
echo "  5) start control panel:"
echo "     python3 -m service.control_panel.web --rpc-url \"$RPC_URL\" --private-key \"\$PRIVATE_KEY\" --allow-execute --auth-token \"\$CONTROL_PANEL_TOKEN\" --port 8092"
echo "  6) start sweeper:"
echo "     python3 -m service.indexer.sweeper --db-path \"$INDEXER_DB_PATH\" --rpc-url \"$RPC_URL\" --private-key \"\$PRIVATE_KEY\" --execute --loop --interval-seconds 60"
