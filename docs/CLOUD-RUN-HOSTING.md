# Cloud Run Hosting (Indexer)

This runbook sets up the hosted indexer on Google Cloud Run from this repository.

## Service details

- Container source: repo root `Dockerfile`
- Process: `python3 -m service.indexer.live_api`
- Port: `8080` (Cloud Run default)
- DB path: `/tmp/indexer.db` (ephemeral; rebuilt from chain on cold start)

## Environment (defaults in Dockerfile)

The root `Dockerfile` sets everything needed for a no-console deploy:

- `RPC_URL_BASE_SEPOLIA` = `https://sepolia.base.org` (public RPC; override for a private endpoint if you hit rate limits)
- `INDEXER_FROM_BLOCK` = `39608044` (factory deploy block for the current testnet factory)
- `INDEXER_NETWORK`, `INDEXER_DB_PATH`, `INDEXER_POLL_INTERVAL_SECONDS`, `PORT` = as in the Dockerfile

Optional overrides in the Cloud Run UI (only if needed): `FACTORY_ADDRESS`, `RPC_URL_BASE_SEPOLIA`, `INDEXER_FROM_BLOCK`, etc.

**Do not** set `INDEXER_FROM_BLOCK` to an empty value in the console: that overrides the Dockerfile default with “unset”, and the live indexer then relies on `indexerFromBlock` in `config/deployments.json` inside the image (added in-repo next to the factory). If both are missing, the container fails fast at startup.

Smaller `INDEXER_CHUNK_SIZE` (default `400` in the Dockerfile) reduces `eth_getLogs` payload on public RPCs.

## Deploy via Cloud Run UI (repo-connected)

1. Create service in Cloud Run and connect this GitHub repo.
2. Set build type to Dockerfile and point to `/Dockerfile`.
3. No environment variables are required unless you want overrides.
4. Deploy to a supported region (free-tier friendly: `us-central1` recommended).
5. After deployment, verify:
   - `GET /health` returns `{"ok": true, "wager_count": N, "last_indexed_block": B, ...}`
   - `GET /wagers?limit=20&order=desc` returns populated results after sync (may take one poll interval)

## Redeploy after indexer or Dockerfile changes

Cloud Run does **not** automatically pick up new Git commits unless your project has **continuous deployment** from this repo configured and working. After changing `service/indexer/`, the root `Dockerfile`, or event-topic logic, **redeploy** the service so a fresh container builds.

**Console:** Cloud Run → your service → **Edit & deploy new revision** → deploy (or use **Deploy revision** from the service overview).

**CLI (from repo root):** with `gcloud` authenticated:

```bash
export GCP_PROJECT_ID="your-gcp-project-id"
./script/deploy/redeploy_cloud_run_indexer.sh
```

(Adjust `GCP_REGION` / `GCP_SERVICE` if your service name or region differs.)

**How to tell the running image is stale:** `GET /health` shows `wager_count: 0` and `last_indexed_block` well above the factory deploy block, but Base Sepolia has `WagerCreated` logs for that factory. The running indexer likely predates the on-chain ABI (rebuild from latest `master`).

## Post-deploy wiring

- Update `config/deployments.json`:
  - `baseSepolia.explorerApiBase` -> new Cloud Run URL
- Commit/push that config change so dApp/explorer consume the new endpoint.
