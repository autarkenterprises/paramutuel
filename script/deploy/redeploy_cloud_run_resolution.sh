#!/usr/bin/env bash
# Redeploy the resolution service to Cloud Run using Dockerfile.resolution.
#
# Usage:
#   export GCP_PROJECT_ID="your-project-id"
#   export GCP_REGION="europe-west1"           # optional
#   export GCP_SERVICE="paramutuel-resolution" # optional
#   ./script/deploy/redeploy_cloud_run_resolution.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

: "${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
REGION="${GCP_REGION:-europe-west1}"
SERVICE="${GCP_SERVICE:-paramutuel-resolution}"
IMAGE="gcr.io/${GCP_PROJECT_ID}/${SERVICE}:latest"

gcloud builds submit \
  --project="$GCP_PROJECT_ID" \
  --tag="$IMAGE" \
  --file=Dockerfile.resolution \
  .

exec gcloud run deploy "$SERVICE" \
  --project="$GCP_PROJECT_ID" \
  --region="$REGION" \
  --image="$IMAGE" \
  --quiet
