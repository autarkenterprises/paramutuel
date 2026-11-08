#!/usr/bin/env bash
# Point the public indexer URL at the indexer VM (ADR-0022).
#
# The Cloud Run service `paramutuel-git` (europe-west1) keeps its URL, which every client is configured
# with, but now runs only Caddy's `reverse-proxy` command, forwarding to the VM on port 8080. Cloud Run
# terminates TLS, so browsers on the HTTPS GitHub Pages site can call it.
#
#   - The Caddy image is pinned to a release.
#   - One instance at most: the proxy holds no state, and one instance bounds its cost.
#   - Environment variables are cleared. The old indexer image carried a provider RPC URL with a key in
#     it, which the proxy does not need.
#
# Usage:
#   export GCP_PROJECT_ID="paratest-491920"
#   ./script/deploy/cloud_run_indexer_proxy.sh
#
# Run script/deploy/gce_indexer.sh first: the upstream is the VM's static address.
# INDEXER_UPSTREAM overrides the upstream (e.g. http://203.0.113.7:8080).
set -euo pipefail

: "${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
REGION="${GCP_REGION:-europe-west1}"
SERVICE="${GCP_SERVICE:-paramutuel-git}"
ZONE="${GCE_ZONE:-us-central1-a}"
NAME="${GCE_INSTANCE:-paramutuel-indexer}"
CADDY_IMAGE="docker.io/library/caddy:2.10.0"

g() { gcloud --project="$GCP_PROJECT_ID" --quiet "$@"; }

if [[ -z "${INDEXER_UPSTREAM:-}" ]]; then
  if ! IP="$(g compute addresses describe "$NAME-ip" --region="${ZONE%-*}" --format='value(address)')" || [[ -z "$IP" ]]; then
    echo "No static address $NAME-ip: run script/deploy/gce_indexer.sh first" >&2
    exit 1
  fi
  INDEXER_UPSTREAM="http://$IP:8080"
fi

g run deploy "$SERVICE" --region="$REGION" \
  --image="$CADDY_IMAGE" \
  --command=caddy --args="reverse-proxy,--from,:8080,--to,$INDEXER_UPSTREAM" \
  --port=8080 --cpu=1 --memory=256Mi --max-instances=1 \
  --clear-env-vars --allow-unauthenticated

echo "$SERVICE now proxies to $INDEXER_UPSTREAM"
