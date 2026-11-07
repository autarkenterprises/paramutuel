#!/usr/bin/env bash
#
# Extended test suite — slower regressions per ADR-0013.
#
# Wraps the existing testnet runners under `script/testnet/`. Requires
# secrets (PRIVATE_KEY) and network connectivity (RPC_URL_BASE_SEPOLIA),
# so it is NOT run on every commit. Per AGENTS.md practice #14: run in
# parallel during feature work, but BLOCK on it before any commit that
# changes functionality measured by the extended tests.
#
# Layers exercised, in order:
#   0. Local-chain end-to-end        (script/test-local-e2e.sh), no secrets or network needed
#   1. Live Base Sepolia integration (script/testnet/run_live_suite.sh)
#   2. Multi-wager stress suite      (script/testnet/run_stress_suite.sh)
#
# The live suites skip almost everything in their default read-only mode, so layer 0 is where most of
# the cross-layer verification happens. script/mutation-check.py is also on this path but runs on its
# own, since it takes about an hour.
#
# Mode is forwarded to the live suite via TESTNET_MODE
# (readonly | minimal-tx | funded-tx). Default: readonly, which needs
# only RPC_URL_BASE_SEPOLIA and works without a private key.
#
# Environment:
#   EXTENDED_SKIP_LOCAL=1     skip the local-chain end-to-end suite
#   EXTENDED_SKIP_LIVE=1      skip the live integration suite
#   EXTENDED_SKIP_STRESS=1    skip the stress suite
#   TESTNET_MODE              forwarded to run_live_suite.sh
#   RPC_URL_BASE_SEPOLIA      required (or RPC_URL_SEPOLIA fallback)
#   PRIVATE_KEY               required only when TESTNET_MODE != readonly
#
# Exit codes:
#   0 — all enabled layers passed
#   non-zero — first failing layer's exit code (script aborts on first
#              failure, like script/test-fast.sh)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Sanity: refuse to run if neither layer is enabled. The intent of this
# script is to gate functionality-changing commits on the extended
# suite; running it with everything skipped is almost always a mistake.
if [[ "${EXTENDED_SKIP_LOCAL:-0}" == "1" && "${EXTENDED_SKIP_LIVE:-0}" == "1" && "${EXTENDED_SKIP_STRESS:-0}" == "1" ]]; then
  echo "error: every extended layer is skipped; nothing to run" >&2
  exit 2
fi

section() {
  echo
  echo "=== $1 ==="
}

run_layer() {
  local name="$1"; shift
  if ! "$@"; then
    echo
    echo "FAIL: $name" >&2
    exit 1
  fi
}

# 0. Local chain: real cast, real indexer, real services, no secrets.
if [[ "${EXTENDED_SKIP_LOCAL:-0}" != "1" ]]; then
  section "local-chain end-to-end"
  run_layer "local e2e" script/test-local-e2e.sh
else
  echo "(skipped local e2e per EXTENDED_SKIP_LOCAL=1)"
fi

# 1. Live Base Sepolia integration suite. The wrapper validates
#    FACTORY_ADDRESS / RPC_URL itself; we forward TESTNET_MODE through
#    the environment so the operator can pick readonly / minimal-tx /
#    funded-tx without editing this script.
if [[ "${EXTENDED_SKIP_LIVE:-0}" != "1" ]]; then
  section "live Base Sepolia integration suite (mode=${TESTNET_MODE:-readonly})"
  run_layer "live suite" script/testnet/run_live_suite.sh
else
  echo "(skipped live suite per EXTENDED_SKIP_LIVE=1)"
fi

# 2. Multi-wager stress suite. Self-validates required env (e.g. wallet
#    pool / collateral configuration) inside the wrapper.
if [[ "${EXTENDED_SKIP_STRESS:-0}" != "1" ]]; then
  section "multi-wager stress suite"
  run_layer "stress suite" script/testnet/run_stress_suite.sh
else
  echo "(skipped stress suite per EXTENDED_SKIP_STRESS=1)"
fi

echo
echo "=== extended suite OK ==="
