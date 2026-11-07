#!/usr/bin/env bash
#
# End-to-end test against a real local chain: anvil, real `cast`, the real indexer and API, and every
# service, with no mocks between the layers. Needs Foundry and no secrets, so CI runs it on every push.
#
# It exists because the unit suites each stopped at their own boundary. Several bugs lived exactly at
# those boundaries, such as `cast` altering strings on the way to the chain (ADR-0020).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

forge build -q
PYTHONPATH=. python3 -m unittest discover -s test/integration -p "test_*.py" "$@"
