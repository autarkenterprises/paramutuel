#!/usr/bin/env bash

# Resolve FACTORY_ADDRESS from config/deployments.json if not set in env.
read_factory_address_from_config() {
  local network_key="${1:-base-sepolia}"
  local config_path="${2:-config/deployments.json}"
  if [[ ! -f "$config_path" ]]; then
    return 1
  fi
  python3 - "$config_path" "$network_key" <<'PY'
import json
import sys

path = sys.argv[1]
network = sys.argv[2]
key_map = {
    "base-sepolia": "baseSepolia",
    "base-sepolia-testnet": "baseSepolia",
    "base-mainnet": "baseMainnet",
    "base": "baseMainnet",
}
cfg_key = key_map.get(network, network)
try:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
except Exception:
    raise SystemExit(1)
addr = str(((data.get(cfg_key) or {}).get("factoryAddress") or "")).strip()
if not addr:
    raise SystemExit(1)
print(addr)
PY
}

ensure_factory_address() {
  local network_key="${1:-base-sepolia}"
  local config_path="${2:-config/deployments.json}"
  if [[ -n "${FACTORY_ADDRESS:-}" ]]; then
    export FACTORY_ADDRESS
    return 0
  fi
  local resolved
  resolved="$(read_factory_address_from_config "$network_key" "$config_path" || true)"
  if [[ -z "$resolved" ]]; then
    return 1
  fi
  FACTORY_ADDRESS="$resolved"
  export FACTORY_ADDRESS
}
