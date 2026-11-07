#!/usr/bin/env bash
# Assemble the static GitHub Pages artifact into the directory given as $1 (default: _site).
#
# This is the single definition of what ships. The deploy workflow calls it, and
# dapp/tests/site-artifact.test.js runs it in the fast suite and checks every local reference against
# the result, so a page cannot reference a file that is not deployed. Site assets are copied by glob:
# a hard-coded list here once left the propose scripts out, and the hosted flow returned 404s
# (ADR-0020 D1).
#
# ABIs come from the committed dapp/abi/ files, which dapp/tests/abi-drift.test.js keeps in step with
# the contracts.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$ROOT/_site}"

mkdir -p "$OUT/dapp/abi" "$OUT/explorer" "$OUT/config"

# Website shell: everything except tests.
cp "$ROOT"/site/*.html "$ROOT"/site/*.js "$ROOT"/site/*.css "$OUT/"

# Runtime configuration read by the browser.
cp "$ROOT/config/deployments.json" "$ROOT/config/operator-hub.json" "$ROOT/config/collateral-allowlist.json" "$OUT/config/"

# Standalone dApp.
cp "$ROOT"/dapp/index.html "$ROOT"/dapp/app.js "$ROOT"/dapp/logic.js "$ROOT"/dapp/style.css "$OUT/dapp/"
cp "$ROOT"/dapp/abi/*.json "$OUT/dapp/abi/"

# Explorer, embedded by the site through an iframe.
cp "$ROOT"/service/explorer/static/index.html "$ROOT"/service/explorer/static/app.js "$ROOT"/service/explorer/static/style.css "$OUT/explorer/"
