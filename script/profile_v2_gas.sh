#!/usr/bin/env bash
# Print Foundry gas report for all Paramutuel v2 tests (ADR-0008 branch).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
forge test --match-path 'test/ParamutuelV2*.t.sol' --gas-report "$@"
