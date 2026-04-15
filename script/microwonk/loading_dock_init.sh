#!/usr/bin/env bash
# Generate N "loading dock" EOAs whose sole purpose is to receive faucet drips
# and forward them to the ARG treasury. Keeping docks separate from the treasury
# means faucet rate limits apply per-dock (more parallel faucet visits), and the
# treasury address stays off faucet logs.
#
# Writes:
#   config/microwonk-loading-docks.json  (public addresses; safe to commit)
#   Appends MICROWONK_KEY_DOCK_<N>=0x... to config/microwonk-keys.env
#
# Usage:
#   ./script/microwonk/loading_dock_init.sh 3       # mint 3 dock wallets
#   FORCE=1 ./script/microwonk/loading_dock_init.sh # re-mint (destroys old docks)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

COUNT="${1:-3}"
DOCKS_FILE="config/microwonk-loading-docks.json"
KEYS_ENV="config/microwonk-keys.env"

if ! command -v cast >/dev/null 2>&1; then
  echo "error: 'cast' not found on PATH. Install Foundry." >&2
  exit 1
fi
if (( COUNT < 1 || COUNT > 200 )); then
  echo "error: count must be in [1, 200]" >&2
  exit 1
fi
if [[ ! -f "$KEYS_ENV" ]]; then
  echo "error: $KEYS_ENV not found. Run generate_wallets.sh first." >&2
  exit 1
fi

FORCE="${FORCE:-0}"
if [[ -f "$DOCKS_FILE" && "$FORCE" != "1" ]]; then
  echo "error: $DOCKS_FILE already exists. Re-run with FORCE=1 to rotate." >&2
  exit 1
fi

# If rotating, comment out old dock exports so they don't conflict.
if grep -q '^export MICROWONK_KEY_DOCK_' "$KEYS_ENV" 2>/dev/null; then
  sed -i.bak 's/^export MICROWONK_KEY_DOCK_/# ROTATED-OUT export MICROWONK_KEY_DOCK_/' "$KEYS_ENV"
  rm -f "${KEYS_ENV}.bak"
fi

echo "==> Generating $COUNT loading-dock EOAs"

python3 - "$DOCKS_FILE" "$COUNT" "$KEYS_ENV" <<'PY'
import json, os, subprocess, sys, datetime

out_path, count, keys_env = sys.argv[1], int(sys.argv[2]), sys.argv[3]
docks = []
key_lines = [
    "",
    f"# Loading dock rotation {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
]

for i in range(count):
    r = subprocess.run(["cast", "wallet", "new", "--json"],
                       capture_output=True, text=True, check=True)
    d = json.loads(r.stdout)
    if isinstance(d, list):
        d = d[0]
    idx = i + 1
    docks.append({
        "key": f"dock_{idx:02d}",
        "label": f"Loading dock #{idx:02d}",
        "address": d["address"],
        "role": "loading_dock",
    })
    key_lines.append(f"export MICROWONK_KEY_DOCK_{idx:02d}={d['private_key']}")

open(out_path, "w").write(json.dumps({
    "schemaVersion": 1,
    "generatedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "docks": docks,
}, indent=2) + "\n")

with open(keys_env, "a") as f:
    f.write("\n".join(key_lines) + "\n")

print(f"wrote {count} docks -> {out_path}")
for d in docks:
    print(f"  {d['key']}  {d['address']}")
PY

chmod 600 "$KEYS_ENV"

echo ""
echo "Next steps:"
echo "  source $KEYS_ENV"
echo "  # Register dock addresses with faucets that require account sign-up."
echo "  # After faucet drips arrive, run:"
echo "  ./script/microwonk/load_treasury.sh"
