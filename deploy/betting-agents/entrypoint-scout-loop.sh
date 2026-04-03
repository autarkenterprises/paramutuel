#!/usr/bin/env bash
set -euo pipefail

# Periodic JSON recommendations (stdout). Configure via env — scale replicas for a fleet.
# Does not sign transactions; pair executors separately (see EXECUTOR-PATTERN.md).

INTERVAL="${SCOUT_INTERVAL_SECONDS:-300}"

while true; do
  payload="$(python3 - <<'PY'
import json
import os

print(
    json.dumps(
        {
            "op": "recommend",
            "strategy": os.environ.get("BETTOR_STRATEGY", "best_post_multiple"),
            "bet_amount_raw": int(os.environ.get("BET_AMOUNT_RAW", "1000000")),
            "scan_limit": int(os.environ.get("SCOUT_SCAN_LIMIT", "25")),
            "min_total_pot_raw": int(os.environ.get("MIN_TOTAL_POT_RAW", "0")),
            "top": int(os.environ.get("SCOUT_TOP", "3")),
        }
    )
)
PY
)"
  echo "$payload" | paramutuel-bettor json || true
  sleep "$INTERVAL"
done
