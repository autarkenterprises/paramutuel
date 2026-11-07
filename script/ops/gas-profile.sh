#!/usr/bin/env bash
set -euo pipefail

# Lightweight gas profiling helper for roadmap checkpoints: the representative V3 scenarios, plus the
# worst-case resolve bounds that must stay under Base's 2^24 per-transaction gas cap.
# Usage:
#   bash script/ops/gas-profile.sh

echo "Running focused gas report tests..."
forge test --gas-report --match-contract "ParamutuelV3GasReport"
forge test -vv --match-test "test_C1_coldResolve_absoluteWorstCase_fitsTxGasCap"
