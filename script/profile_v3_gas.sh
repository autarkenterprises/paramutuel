#!/usr/bin/env bash
# Print Foundry gas report for Paramutuel V3 harness tests.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
forge test --match-path 'test/ParamutuelV3*.t.sol' --gas-report "$@"
