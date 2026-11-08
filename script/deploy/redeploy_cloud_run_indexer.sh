#!/usr/bin/env bash
# Deploy the indexer container (repo root Dockerfile) to a Cloud Run service of your own.
#
# The project's hosted indexer no longer runs this way (ADR-0022). It runs on a Compute Engine VM, and
# the Cloud Run service `paramutuel-git` is now an HTTPS proxy in front of it. To update the hosted
# indexer, use ./script/deploy/gce_indexer.sh. This script therefore has no default service name, and it
# refuses `paramutuel-git`: deploying the container there would replace the proxy with an indexer whose
# database lives in /tmp (docs/CLOUD-RUN-HOSTING.md explains why that loses the index).
#
# Requires: gcloud CLI, auth (`gcloud auth login`), and a project with Cloud Run + Cloud Build enabled.
#
# Usage:
#   export GCP_PROJECT_ID="your-project-id"
#   export GCP_SERVICE="your-indexer"         # required
#   export GCP_REGION="europe-west1"          # optional
#   ./script/deploy/redeploy_cloud_run_indexer.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
: "${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
if [[ -z "${GCP_SERVICE:-}" ]]; then
  echo "Set GCP_SERVICE to your own Cloud Run service. To update the hosted indexer, run ./script/deploy/gce_indexer.sh (ADR-0022)." >&2
  exit 1
fi
if [[ "$GCP_SERVICE" == "paramutuel-git" ]]; then
  echo "paramutuel-git is the HTTPS proxy to the indexer VM (ADR-0022); deploying the container there would replace it. Run ./script/deploy/gce_indexer.sh instead." >&2
  exit 1
fi
REGION="${GCP_REGION:-europe-west1}"
exec gcloud run deploy "$GCP_SERVICE" \
  --project="$GCP_PROJECT_ID" \
  --region="$REGION" \
  --source=. \
  --quiet
