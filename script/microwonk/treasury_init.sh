#!/usr/bin/env bash
# Initialise (or rotate) just the ARG treasury wallet, independently of the
# microwonks. Use this when you want to generate a new treasury key without
# regenerating the 8 microwonk personas.
#
# Writes:
#   - Updates config/microwonk-wallets.json "roles.treasury.address"
#   - Appends export MICROWONK_KEY_ARG_TREASURY=0x... to config/microwonk-keys.env
#   - Also exports MICROWONK_TREASURY_PRIVATE_KEY=0x... for convenience
#
# Rotation flow (sweep first to avoid stranding funds):
#   ./script/microwonk/sweep_wallets.sh      # pull microwonks -> current treasury
#   SWEEP_TO=0xCOLD ./script/microwonk/sweep_wallets.sh  # optional: drain old treasury
#   FORCE=1 ./script/microwonk/treasury_init.sh          # mint new treasury
#   ./script/microwonk/fund_wallets.sh                    # re-fund from new treasury

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

WALLETS="config/microwonk-wallets.json"
KEYS_ENV="config/microwonk-keys.env"
ROSTER="config/microwonk-roster.json"

if ! command -v cast >/dev/null 2>&1; then
  echo "error: 'cast' not found on PATH. Install Foundry." >&2
  exit 1
fi
if [[ ! -f "$ROSTER" ]]; then
  echo "error: roster file not found: $ROSTER" >&2
  exit 1
fi

FORCE="${FORCE:-0}"

# Parse existing treasury address (if any) out of wallets.json.
existing_addr=""
if [[ -f "$WALLETS" ]]; then
  existing_addr="$(python3 - "$WALLETS" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print(""); raise SystemExit
t = (d.get("roles") or {}).get("treasury") or {}
print(t.get("address") or "")
PY
)"
fi

if [[ -n "$existing_addr" && "$FORCE" != "1" ]]; then
  echo "error: treasury already initialised at $existing_addr" >&2
  echo "       Re-run with FORCE=1 to rotate (make sure you swept first)." >&2
  exit 1
fi

# Generate the EOA.
new_json="$(cast wallet new --json)"
new_addr="$(printf '%s' "$new_json" | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d[0]["address"] if isinstance(d,list) else d["address"])')"
new_pk="$(printf '%s' "$new_json" | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d[0]["private_key"] if isinstance(d,list) else d["private_key"])')"

# Ensure wallets.json exists with at least the treasury role seeded from roster.
if [[ ! -f "$WALLETS" ]]; then
  python3 - "$ROSTER" "$WALLETS" <<'PY'
import json, sys, datetime
roster = json.load(open(sys.argv[1]))
out = {
    "schemaVersion": 1,
    "network": roster.get("network", "baseSepolia"),
    "generatedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "roles": {},
    "microwonks": [],
}
for role, meta in roster.get("roles", {}).items():
    out["roles"][role] = {
        "key": meta["key"],
        "handle": meta.get("handle"),
        "role": meta["role"],
        "label": meta["label"],
        "address": "",
    }
open(sys.argv[2], "w").write(json.dumps(out, indent=2) + "\n")
PY
fi

# Patch treasury address into wallets.json.
python3 - "$WALLETS" "$new_addr" <<'PY'
import json, sys, datetime
path, addr = sys.argv[1], sys.argv[2]
d = json.load(open(path))
roles = d.setdefault("roles", {})
t = roles.setdefault("treasury", {
    "key": "arg_treasury",
    "handle": None,
    "role": "treasury",
    "label": "ARG Treasury",
})
t["address"] = addr
d["treasuryRotatedAt"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
open(path, "w").write(json.dumps(d, indent=2) + "\n")
PY

# Append key to keys.env (keep previous keys; rotation adds a new line).
if [[ ! -f "$KEYS_ENV" ]]; then
  {
    echo "# MICROWONK PRIVATE KEYS — DO NOT COMMIT"
    echo "# Initialised $(date -u +%Y-%m-%dT%H:%M:%SZ) by treasury_init.sh"
    echo ""
  } > "$KEYS_ENV"
  chmod 600 "$KEYS_ENV"
fi

# If rotating, comment out any previous treasury export to avoid confusion.
if grep -q '^export MICROWONK_KEY_ARG_TREASURY=' "$KEYS_ENV"; then
  sed -i.bak 's/^export MICROWONK_KEY_ARG_TREASURY=/# ROTATED-OUT export MICROWONK_KEY_ARG_TREASURY=/' "$KEYS_ENV"
  rm -f "${KEYS_ENV}.bak"
fi
if grep -q '^export MICROWONK_TREASURY_PRIVATE_KEY=' "$KEYS_ENV"; then
  sed -i.bak 's/^export MICROWONK_TREASURY_PRIVATE_KEY=/# ROTATED-OUT export MICROWONK_TREASURY_PRIVATE_KEY=/' "$KEYS_ENV"
  rm -f "${KEYS_ENV}.bak"
fi

{
  echo ""
  echo "# Treasury rotation $(date -u +%Y-%m-%dT%H:%M:%SZ)  address=$new_addr"
  echo "export MICROWONK_KEY_ARG_TREASURY=$new_pk"
  echo "export MICROWONK_TREASURY_PRIVATE_KEY=$new_pk"
} >> "$KEYS_ENV"

chmod 600 "$KEYS_ENV"

echo "==> Treasury EOA: $new_addr"
echo "==> Updated      $WALLETS"
echo "==> Appended key to $KEYS_ENV (prior treasury key commented out if present)"
echo ""
echo "Next:"
echo "  source $KEYS_ENV"
echo "  ./script/microwonk/check_balances.sh   # treasury row should show 0/0"
echo "  # Fund the treasury from a Base Sepolia faucet, then:"
echo "  ./script/microwonk/fund_wallets.sh"
