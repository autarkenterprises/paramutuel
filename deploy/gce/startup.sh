#!/usr/bin/env bash
# Startup script for the indexer VM (ADR-0022). Compute Engine runs it as root at every boot, and
# `script/deploy/gce_indexer.sh` re-runs it after changing the pinned commit.
#
# What it does, in order:
#   1. Reads two instance metadata attributes: `indexer-repo` (a git URL) and `indexer-ref` (a full
#      40-character commit hash). A branch name is refused: a branch moves under the VM, and only a
#      commit says exactly what runs.
#   2. Installs git if it is missing (Ubuntu minimal ships without it). The indexer itself needs only
#      Python's standard library, and Ubuntu 24.04 provides Python 3.12, as the container image does.
#   3. Clones the repository to /opt/paramutuel once, then fetches and checks out the pinned commit.
#   4. Installs the systemd unit from that same checkout, so code and unit always come from one commit,
#      then restarts the service.
#
# It fails closed: with no ref, a malformed ref, or a commit the repository does not have, it exits
# non-zero before touching the unit or the service, so the release already running keeps running.
#
# The index itself is not touched here. It lives in the unit's systemd StateDirectory
# (/var/lib/paramutuel), on the boot disk, outside the checkout.
#
# Testing: PARAMUTUEL_PREFIX roots every path in a sandbox. `script/tests/test_gce_indexer.py` runs this
# script with stubs for the metadata server (curl), systemctl and apt-get, against a real git repository.
# On the VM it is unset.
set -euo pipefail

PREFIX="${PARAMUTUEL_PREFIX:-}"
METADATA_URL="http://metadata.google.internal/computeMetadata/v1/instance/attributes"
APP_DIR="$PREFIX/opt/paramutuel"
UNIT_DIR="$PREFIX/etc/systemd/system"
SERVICE="paramutuel-indexer"

# One metadata attribute, or a non-zero exit if it is not set (curl -f fails on the server's 404).
metadata() {
  curl -fsS -H "Metadata-Flavor: Google" "$METADATA_URL/$1"
}

fail() {
  echo "startup: $*; leaving the running release alone" >&2
  exit 1
}

repo="$(metadata indexer-repo)" || fail "instance metadata has no indexer-repo"
ref="$(metadata indexer-ref)" || fail "instance metadata has no indexer-ref"
[[ "$ref" =~ ^[0-9a-f]{40}$ ]] || fail "indexer-ref must be a full commit hash, not '$ref'"

if ! command -v git >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1; then
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq git python3
fi

if [[ ! -d "$APP_DIR/.git" ]]; then
  git clone --quiet "$repo" "$APP_DIR"
fi
git -C "$APP_DIR" remote set-url origin "$repo"
git -C "$APP_DIR" fetch --quiet origin
git -C "$APP_DIR" cat-file -e "$ref^{commit}" 2>/dev/null || fail "commit $ref is not in $repo"
git -C "$APP_DIR" checkout --quiet --detach "$ref"

install -D -m 0644 "$APP_DIR/deploy/gce/$SERVICE.service" "$UNIT_DIR/$SERVICE.service"
systemctl daemon-reload
systemctl enable --quiet "$SERVICE"
systemctl restart "$SERVICE"
echo "startup: $SERVICE running $ref"
