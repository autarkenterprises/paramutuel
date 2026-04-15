#!/usr/bin/env bash
# Generate fresh EOAs for the microwonk ARG: 8 personas + proposer + resolver.
#
# Reads:
#   config/microwonk-roster.json   (roles + microwonks; schema v1)
#
# Writes:
#   config/microwonk-wallets.json  (public: addresses + labels; safe to commit)
#   config/microwonk-keys.env      (private: export MICROWONK_KEY_<KEY>=0x...; gitignored)
#
# Safety:
#   - Refuses to overwrite existing outputs unless FORCE=1 is set.
#   - Never echoes private keys to stdout; only writes them to microwonk-keys.env.
#
# Usage:
#   ./script/microwonk/generate_wallets.sh
#   FORCE=1 ./script/microwonk/generate_wallets.sh   # regenerate from scratch
#
# Requires: cast (Foundry), python3.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

ROSTER="config/microwonk-roster.json"
WALLETS="config/microwonk-wallets.json"
KEYS_ENV="config/microwonk-keys.env"

if [[ ! -f "$ROSTER" ]]; then
  echo "error: roster file not found: $ROSTER" >&2
  exit 1
fi

if ! command -v cast >/dev/null 2>&1; then
  echo "error: 'cast' not found on PATH. Install Foundry: https://book.getfoundry.sh/" >&2
  exit 1
fi

FORCE="${FORCE:-0}"
if [[ "$FORCE" != "1" ]]; then
  for existing in "$WALLETS" "$KEYS_ENV"; do
    if [[ -e "$existing" ]]; then
      echo "error: $existing already exists. Refusing to overwrite." >&2
      echo "       Re-run with FORCE=1 to regenerate (destroys existing keys)." >&2
      exit 1
    fi
  done
fi

NETWORK="$(python3 -c "import json; print(json.load(open('$ROSTER')).get('network','baseSepolia'))")"

mapfile -t KEYS < <(python3 - "$ROSTER" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
out = []
for role, meta in r.get("roles", {}).items():
    out.append(meta["key"])
for w in r.get("microwonks", []):
    out.append(w["key"])
# de-dup, preserve order
seen = set()
for k in out:
    if k in seen:
        continue
    seen.add(k)
    print(k)
PY
)

if (( ${#KEYS[@]} == 0 )); then
  echo "error: no wallet keys parsed from $ROSTER" >&2
  exit 1
fi

echo "==> Generating ${#KEYS[@]} wallets for microwonk roster ($NETWORK)"

tmp_wallets="$(mktemp)"
tmp_keys="$(mktemp)"
trap 'rm -f "$tmp_wallets" "$tmp_keys"' EXIT

# header for keys env file
{
  echo "# MICROWONK PRIVATE KEYS — DO NOT COMMIT"
  echo "# Generated $(date -u +%Y-%m-%dT%H:%M:%SZ) by script/microwonk/generate_wallets.sh"
  echo "# Network: $NETWORK"
  echo "# These keys control wallets holding testnet ETH and USDC for the ARG."
  echo ""
} > "$tmp_keys"

# JSON assembly driven by python (stable ordering, pretty output)
export TMP_WALLETS_PATH="$tmp_wallets"
export TMP_KEYS_PATH="$tmp_keys"
export ROSTER_PATH="$ROSTER"
export NETWORK

python3 - <<'PY'
import json, os, subprocess, sys, pathlib

roster = json.load(open(os.environ["ROSTER_PATH"]))
network = os.environ["NETWORK"]
out_wallets = {
    "schemaVersion": 1,
    "network": network,
    "generatedAt": None,  # set by caller if desired
    "roles": {},
    "microwonks": [],
}
keys_buf = []

def new_wallet():
    r = subprocess.run(["cast", "wallet", "new", "--json"], capture_output=True, text=True, check=True)
    data = json.loads(r.stdout)
    if isinstance(data, list):
        data = data[0]
    return data["address"], data["private_key"]

for role_name, meta in roster.get("roles", {}).items():
    addr, pk = new_wallet()
    out_wallets["roles"][role_name] = {
        "key": meta["key"],
        "handle": meta.get("handle"),
        "role": meta["role"],
        "label": meta["label"],
        "address": addr,
    }
    keys_buf.append(f"export MICROWONK_KEY_{meta['key'].upper()}={pk}")
    # Treasury gets an alias that fund_wallets.sh / sweep_wallets.sh look up.
    if meta.get("role") == "treasury":
        keys_buf.append(f"export MICROWONK_TREASURY_PRIVATE_KEY={pk}")

for w in roster.get("microwonks", []):
    addr, pk = new_wallet()
    out_wallets["microwonks"].append({
        "key": w["key"],
        "handle": w["handle"],
        "designation": w["designation"],
        "address": addr,
        "avatarSeed": w.get("avatarSeed"),
    })
    keys_buf.append(f"export MICROWONK_KEY_{w['key'].upper()}={pk}")

pathlib.Path(os.environ["TMP_WALLETS_PATH"]).write_text(
    json.dumps(out_wallets, indent=2) + "\n", encoding="utf-8"
)
with open(os.environ["TMP_KEYS_PATH"], "a", encoding="utf-8") as f:
    f.write("\n".join(keys_buf) + "\n")

print(f"generated {len(out_wallets['roles']) + len(out_wallets['microwonks'])} wallets")
PY

# Stamp generatedAt
python3 - "$tmp_wallets" <<'PY'
import json, sys, datetime
p = sys.argv[1]
d = json.load(open(p))
d["generatedAt"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
open(p, "w").write(json.dumps(d, indent=2) + "\n")
PY

mv "$tmp_wallets" "$WALLETS"
mv "$tmp_keys" "$KEYS_ENV"
chmod 600 "$KEYS_ENV"
trap - EXIT

echo ""
echo "==> Wrote $WALLETS (public addresses, safe to commit)"
echo "==> Wrote $KEYS_ENV (private keys, gitignored; mode 600)"
echo ""
echo "Next steps:"
echo "  1. source $KEYS_ENV       # make keys available in your shell"
echo "  2. ./script/microwonk/fund_wallets.sh   # distribute ETH and USDC"
