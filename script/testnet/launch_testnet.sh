#!/usr/bin/env bash
set -euo pipefail

# Full testnet launch helper.
# Usage:
#   cp config/service.env.example config/service.env   # once, then edit
#   ./script/testnet/launch_testnet.sh
#
# Required keys in config/service.env (or legacy .env): PRIVATE_KEY, TREASURY_ADDRESS,
# RPC_URL_BASE_SEPOLIA (or RPC_URL_SEPOLIA). Loaded via script/lib/load_service_env.sh.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

# Load centralized env (exports vars into this shell; must use return-safe loader).
# shellcheck disable=SC1091
source "$ROOT_DIR/script/lib/load_service_env.sh"

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

PROTOCOL_FEE_BPS="${PROTOCOL_FEE_BPS:-100}"
MIN_BETTING_WINDOW="${MIN_BETTING_WINDOW:-3600}"
MIN_RESOLUTION_WINDOW="${MIN_RESOLUTION_WINDOW:-3600}"
INDEXER_DB_PATH="${INDEXER_DB_PATH:-service/indexer/indexer.db}"
DEPLOYMENTS_CONFIG_PATH="${DEPLOYMENTS_CONFIG_PATH:-config/deployments.json}"

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
forge script script/DeployFactory.s.sol \
  --rpc-url "$RPC_URL" \
  --broadcast

DEPLOYED_FACTORY="$(
  python3 - <<'PY'
import glob
import json
from pathlib import Path

paths = glob.glob("broadcast/DeployFactory.s.sol/*/run-latest.json")
if not paths:
    raise SystemExit(1)
paths.sort(key=lambda p: Path(p).stat().st_mtime, reverse=True)
for path in paths:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        continue
    for tx in reversed(data.get("transactions", [])):
        if tx.get("contractName") == "ParamutuelFactory" and tx.get("contractAddress"):
            print(tx["contractAddress"])
            raise SystemExit(0)
raise SystemExit(1)
PY
)" || true

if [[ -n "${DEPLOYED_FACTORY:-}" ]]; then
  ./script/testnet/set_factory_address.sh "$DEPLOYED_FACTORY" base-sepolia >/dev/null
  echo "==> Updated single source of truth: $DEPLOYMENTS_CONFIG_PATH (baseSepolia.factoryAddress=$DEPLOYED_FACTORY)"
fi

FACTORY_FOR_NEXT="${DEPLOYED_FACTORY:-<FACTORY>}"

echo
echo "Factory deployment broadcasted."
echo "Next:"
echo "  1) factory address is stored in $DEPLOYMENTS_CONFIG_PATH"
echo "  2) start indexer sync:"
echo "     python3 service/indexer/indexer.py --rpc-url \"$RPC_URL\" --factory-address \"$FACTORY_FOR_NEXT\" --db-path \"$INDEXER_DB_PATH\""
echo "  3) start indexer API:"
echo "     python3 -m service.indexer.api --db-path \"$INDEXER_DB_PATH\" --host 127.0.0.1 --port 8090"
echo "  4) start explorer:"
echo "     python3 -m service.explorer.server --indexer-base-url http://127.0.0.1:8090 --port 8091"
echo "  5) start control panel:"
echo "     python3 -m service.control_panel.web --rpc-url \"$RPC_URL\" --private-key \"\$PRIVATE_KEY\" --allow-execute --auth-token \"\$CONTROL_PANEL_TOKEN\" --port 8092"
echo "  6) start sweeper:"
echo "     python3 -m service.indexer.sweeper --db-path \"$INDEXER_DB_PATH\" --rpc-url \"$RPC_URL\" --private-key \"\$PRIVATE_KEY\" --execute --loop --interval-seconds 60"
