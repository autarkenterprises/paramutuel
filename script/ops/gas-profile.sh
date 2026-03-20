#!/usr/bin/env bash
set -euo pipefail

# Lightweight gas profiling helper for roadmap checkpoints.
# Usage:
#   bash script/ops/gas-profile.sh

echo "Running focused gas report tests..."
forge test --gas-report \
  --match-test "testCreateMarketStoresParameters|testBetResolveAndClaimPayouts|testRetractRefundsMinusFees|testExpireAfterDeadline|testDelegatedResolverSeparateFromProposer"

