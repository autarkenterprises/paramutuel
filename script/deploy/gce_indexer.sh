#!/usr/bin/env bash
# Create or update the indexer VM (ADR-0022). Safe to re-run: it creates only what is missing.
#
# Usage:
#   export GCP_PROJECT_ID="paratest-491920"
#   export INDEXER_REF="<40-char commit>"   # optional; defaults to origin/master as last fetched
#   ./script/deploy/gce_indexer.sh
#
# Creates, if absent:
#   - a static external IP `<name>-ip`. The Cloud Run proxy (cloud_run_indexer_proxy.sh) targets this
#     address, so it must survive a stop and start.
#   - a firewall rule `<name>-api` opening tcp:8080 to VMs tagged `<name>`. The API serves only GET and
#     OPTIONS over public chain data.
#   - the VM itself: an e2-micro with a 20 GB pd-standard disk in a free-tier region (us-west1,
#     us-central1, us-east1), so it fits Compute Engine's Always Free allowance. It has no service
#     account, because it calls no Google API.
# For an existing VM, it updates the pinned commit in metadata and re-runs the startup script over SSH.
#
# The VM fetches the commit from GitHub, so the commit must be pushed first.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

: "${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
ZONE="${GCE_ZONE:-us-central1-a}"
REGION="${ZONE%-*}"
NAME="${GCE_INSTANCE:-paramutuel-indexer}"
REPO="${INDEXER_REPO:-https://github.com/autarkenterprises/paramutuel.git}"
REF="${INDEXER_REF:-$(git rev-parse origin/master)}"
STARTUP="deploy/gce/startup.sh"

# The VM refuses anything else too (startup.sh); checking here fails before any change is made.
if [[ ! "$REF" =~ ^[0-9a-f]{40}$ ]]; then
  echo "INDEXER_REF must be a full 40-character commit hash, not '$REF'" >&2
  exit 1
fi
case "$REGION" in
  us-west1|us-central1|us-east1) ;;
  *) echo "warning: $REGION is outside the e2-micro free tier; this VM will be billed" >&2 ;;
esac

g() { gcloud --project="$GCP_PROJECT_ID" --quiet "$@"; }

if ! g compute addresses describe "$NAME-ip" --region="$REGION" >/dev/null 2>&1; then
  g compute addresses create "$NAME-ip" --region="$REGION"
fi
IP="$(g compute addresses describe "$NAME-ip" --region="$REGION" --format='value(address)')"

if ! g compute firewall-rules describe "$NAME-api" >/dev/null 2>&1; then
  g compute firewall-rules create "$NAME-api" --network=default --direction=INGRESS \
    --allow=tcp:8080 --source-ranges=0.0.0.0/0 --target-tags="$NAME"
fi

METADATA="indexer-repo=$REPO,indexer-ref=$REF"
if g compute instances describe "$NAME" --zone="$ZONE" >/dev/null 2>&1; then
  g compute instances add-metadata "$NAME" --zone="$ZONE" \
    --metadata="$METADATA" --metadata-from-file="startup-script=$STARTUP"
  g compute ssh "$NAME" --zone="$ZONE" --command="sudo google_metadata_script_runner startup"
else
  g compute instances create "$NAME" --zone="$ZONE" \
    --machine-type=e2-micro \
    --image-family=ubuntu-minimal-2404-lts-amd64 --image-project=ubuntu-os-cloud \
    --boot-disk-type=pd-standard --boot-disk-size=20GB \
    --address="$IP" --tags="$NAME" \
    --no-service-account --no-scopes --shielded-secure-boot \
    --metadata="$METADATA" --metadata-from-file="startup-script=$STARTUP"
fi

echo "Indexer VM $NAME at $IP, pinned to $REF"
echo "Health (once the startup script has run): http://$IP:8080/health"
