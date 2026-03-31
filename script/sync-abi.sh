#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
forge build -q
mkdir -p dapp/abi
mkdir -p mcp_server/abi
for name in ParamutuelFactory ParamutuelWager; do
  python3 -c "
import json, sys
d = json.load(open('out/${name}.sol/${name}.json'))
json.dump({'abi': d['abi']}, sys.stdout, indent=2)
print()
" > "dapp/abi/${name}.json"
  python3 -c "
import json, sys
d = json.load(open('out/${name}.sol/${name}.json'))
json.dump({'abi': d['abi']}, sys.stdout, indent=2)
print()
" > "mcp_server/abi/${name}.json"
done
echo "ABIs synced to dapp/abi/ and mcp_server/abi/"
