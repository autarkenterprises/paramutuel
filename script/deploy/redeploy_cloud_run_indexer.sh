#!/usr/bin/env bash
# Redeploy the indexer to Cloud Run from the repo root Dockerfile.
# Requires: gcloud CLI, auth (`gcloud auth login`), and a project with Cloud Run + Cloud Build enabled.
#
# Usage:
#   export GCP_PROJECT_ID="your-project-id"
#   export GCP_REGION="europe-west1"          # optional
#   export GCP_SERVICE="paramutuel-git"       # optional; must match your service name
#   ./script/deploy/redeploy_cloud_run_indexer.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
: "${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
REGION="${GCP_REGION:-europe-west1}"
SERVICE="${GCP_SERVICE:-paramutuel-git}"
exec gcloud run deploy "$SERVICE" \
  --project="$GCP_PROJECT_ID" \
  --region="$REGION" \
  --source=. \
  --quiet
