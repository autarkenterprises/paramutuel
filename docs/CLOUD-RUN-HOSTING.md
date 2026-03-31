# Cloud Run Hosting (Indexer)

This runbook sets up the hosted indexer on Google Cloud Run from this repository.

## Service details

- Container source: repo root `Dockerfile`
- Process: `python3 -m service.indexer.live_api`
- Port: `8080` (Cloud Run default)
- DB path: `/tmp/indexer.db` (ephemeral; rebuilt from chain on cold start)

## Required env vars

- `RPC_URL_BASE_SEPOLIA` = your Base Sepolia RPC endpoint
- `INDEXER_NETWORK` = `base-sepolia`
- `INDEXER_FROM_BLOCK` = `39608044` (factory deploy block for current testnet factory)
- `INDEXER_DB_PATH` = `/tmp/indexer.db`
- `INDEXER_POLL_INTERVAL_SECONDS` = `15`
- optional override: `FACTORY_ADDRESS` (normally read from `config/deployments.json`)

## Deploy via Cloud Run UI (repo-connected)

1. Create service in Cloud Run and connect this GitHub repo.
2. Set build type to Dockerfile and point to `/Dockerfile`.
3. Configure environment variables listed above.
4. Deploy to a supported region (free-tier friendly: `us-central1` recommended).
5. After deployment, verify:
   - `GET /health` returns `{"ok": true, ...}`
   - `GET /wagers?limit=20&order=desc` returns populated results after sync

## Post-deploy wiring

- Update `config/deployments.json`:
  - `baseSepolia.explorerApiBase` -> new Cloud Run URL
- Commit/push that config change so dApp/explorer consume the new endpoint.
