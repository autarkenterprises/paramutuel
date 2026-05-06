#!/usr/bin/env bash
#
# Fast test suite — the default test path per ADR-0013.
#
# Runs every check that does NOT require a live RPC, private key, or
# external indexer. Safe to run on every commit and on a developer
# machine without secrets.
#
# Layers exercised, in order:
#   1. Foundry contract suite      (forge test)
#   2. MCP server unit tests       (mcp_server/tests)
#   3. Bet scout agent unit tests  (agents/paramutuel_bettor/tests)
#   4. Service unit tests          (service/{indexer,proposition,explorer,resolution,control_panel}/tests)
#   5. dApp pure-helper tests      (dapp/tests via node --test)
#
# Anything that hits a network, requires PRIVATE_KEY, or talks to a live
# indexer belongs in script/test-extended.sh.
#
# Exit codes:
#   0 — all layers passed
#   non-zero — first failing layer's exit code (with the failing layer
#              name printed to stderr); the script aborts on first failure
#              so the operator can fix that layer rather than wading
#              through cascades.
#
# Environment:
#   FAST_SKIP_FORGE=1     skip the Foundry suite (rare; used only when
#                         forge is unavailable on a dev machine).
#   FAST_VERBOSE=1        keep the unittest -v output for Python suites.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

SECTION_FAILURES=()

# Print a banner so the operator can see which layer is currently running.
section() {
  echo
  echo "=== $1 ==="
}

# Run a command; on failure, print the layer name and exit non-zero.
# We do NOT continue past a failure: the AGENTS.md practice is "passing,
# regression-free test suite evaluation" before commit, so the first
# failing layer is the actionable signal.
run_layer() {
  local name="$1"; shift
  if ! "$@"; then
    echo
    echo "FAIL: $name" >&2
    exit 1
  fi
}

# Build the Python unittest verbosity flag once.
PY_VERBOSITY=()
if [[ "${FAST_VERBOSE:-0}" == "1" ]]; then
  PY_VERBOSITY=(-v)
fi

# 1. Foundry contract suite. The fast Solidity suite excludes test/testnet
#    via the foundry.toml `test = "test"` setting; testnet/*.py is Python
#    and not picked up by forge.
if [[ "${FAST_SKIP_FORGE:-0}" != "1" ]]; then
  section "forge test"
  # --no-match-path keeps the option open if a slow Solidity-side regression
  # ever needs to move to the extended suite. Currently empty (no exclusions).
  run_layer "forge test" forge test
else
  echo "(skipped Foundry suite per FAST_SKIP_FORGE=1)"
fi

# 2-4. Python unit suites. unittest discover is invoked per leaf directory
#      because the project does not have a top-level package wiring all
#      tests under one tree, and discovering from `service/` would try to
#      import non-package files. PYTHONPATH=. is needed for the bet scout
#      agent tests to resolve the `agents.paramutuel_bettor` module from
#      its layout.
section "mcp_server unit tests"
run_layer "mcp_server" python3 -m unittest discover "${PY_VERBOSITY[@]}" -s mcp_server/tests -p "test_*.py"

section "agents/paramutuel_bettor unit tests"
run_layer "agents/paramutuel_bettor" \
  env PYTHONPATH=. python3 -m unittest discover "${PY_VERBOSITY[@]}" -s agents/paramutuel_bettor/tests -p "test_*.py"

# Each service has its own tests/ directory; they are discovered
# individually so that an absent __init__.py in one service does not
# block the others, and so that any per-service teardown ordering stays
# isolated.
for service_dir in service/indexer service/proposition service/explorer service/resolution service/control_panel; do
  section "${service_dir} unit tests"
  run_layer "${service_dir}" \
    python3 -m unittest discover "${PY_VERBOSITY[@]}" -s "${service_dir}/tests" -p "test_*.py"
done

# 5. dApp pure-helper tests. node --test is invoked from the dapp/ working
#    directory because logic.test.js uses relative requires; the current
#    shell of this subprocess is restored on exit by `(...)`.
section "dapp pure-helper tests"
( cd dapp && run_layer "dapp" node --test tests/logic.test.js )

echo
echo "=== fast suite OK ==="
