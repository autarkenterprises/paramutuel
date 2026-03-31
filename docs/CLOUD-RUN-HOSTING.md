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

## Deploy via Cloud Run UI (repo-connected)

1. Create service in Cloud Run and connect this GitHub repo.
2. Set build type to Dockerfile and point to `/Dockerfile`.
3. No environment variables are required unless you want overrides.
4. Deploy to a supported region (free-tier friendly: `us-central1` recommended).
5. After deployment, verify:
   - `GET /health` returns `{"ok": true, ...}`
   - `GET /wagers?limit=20&order=desc` returns populated results after sync

## Post-deploy wiring

- Update `config/deployments.json`:
  - `baseSepolia.explorerApiBase` -> new Cloud Run URL
- Commit/push that config change so dApp/explorer consume the new endpoint.
