#!/usr/bin/env bash
set -euo pipefail

# Update config/deployments.json explorerApiBase for a target network key.
# Usage:
#   ./script/testnet/set_explorer_api_base.sh https://your-indexer.example [base-sepolia|base-mainnet]

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "usage: $0 <explorer-api-base-url> [network-key]" >&2
  exit 1
fi

API_BASE_INPUT="$1"
NETWORK_KEY="${2:-base-sepolia}"
CONFIG_PATH="${DEPLOYMENTS_CONFIG_PATH:-config/deployments.json}"

python3 - "$CONFIG_PATH" "$API_BASE_INPUT" "$NETWORK_KEY" <<'PY'
import json
import sys
from urllib.parse import urlparse
from pathlib import Path

config_path = Path(sys.argv[1])
api_base = sys.argv[2].strip()
network_key = sys.argv[3].strip()

parsed = urlparse(api_base)
if parsed.scheme not in ("http", "https") or not parsed.netloc:
    raise SystemExit("error: explorer api base must be an absolute http(s) URL")

key_map = {
    "base-sepolia": "baseSepolia",
    "base-sepolia-testnet": "baseSepolia",
    "base-mainnet": "baseMainnet",
    "base": "baseMainnet",
}
cfg_key = key_map.get(network_key, network_key)

if config_path.exists():
    data = json.loads(config_path.read_text(encoding="utf-8"))
else:
    data = {}

entry = dict(data.get(cfg_key) or {})
entry["explorerApiBase"] = api_base.rstrip("/")
data[cfg_key] = entry

config_path.parent.mkdir(parents=True, exist_ok=True)
config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
print(f"updated {config_path} -> {cfg_key}.explorerApiBase = {entry['explorerApiBase']}")
PY
