#!/usr/bin/env bash
set -euo pipefail

# Update config/deployments.json factoryAddress for a target network key.
# Usage:
#   ./script/testnet/set_factory_address.sh 0x... [base-sepolia|base-mainnet]

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "usage: $0 <factory-address> [network-key]" >&2
  exit 1
fi

FACTORY_ADDRESS_INPUT="$1"
NETWORK_KEY="${2:-base-sepolia}"
CONFIG_PATH="${DEPLOYMENTS_CONFIG_PATH:-config/deployments.json}"

python3 - "$CONFIG_PATH" "$FACTORY_ADDRESS_INPUT" "$NETWORK_KEY" <<'PY'
import json
import re
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
address = sys.argv[2].strip()
network_key = sys.argv[3].strip()

if not re.fullmatch(r"0x[a-fA-F0-9]{40}", address):
    raise SystemExit("error: factory address must be a 20-byte hex address (0x...)")

key_map = {
    "base-sepolia": ("baseSepolia", 84532),
    "base-sepolia-testnet": ("baseSepolia", 84532),
    "base-mainnet": ("baseMainnet", 8453),
    "base": ("baseMainnet", 8453),
}
cfg_key, chain_id = key_map.get(network_key, (network_key, None))

if config_path.exists():
    data = json.loads(config_path.read_text(encoding="utf-8"))
else:
    data = {}

entry = dict(data.get(cfg_key) or {})
entry["factoryAddress"] = address
if chain_id is not None:
    entry["chainId"] = chain_id
data[cfg_key] = entry

config_path.parent.mkdir(parents=True, exist_ok=True)
config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
print(f"updated {config_path} -> {cfg_key}.factoryAddress = {address}")
PY
