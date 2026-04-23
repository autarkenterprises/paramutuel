# Cloud Run Hosting (Indexer)

This runbook sets up the hosted indexer on Google Cloud Run from this repository.

## Service details

- Container source: repo root `Dockerfile`
- Process: `python3 -m service.indexer.live_api`
- Port: `8080` (Cloud Run default)
- DB path: `/tmp/indexer.db` (ephemeral; rebuilt from chain on cold start)

### Ephemeral DB + Cloud Run scaling (why `/wagers` is often empty)

SQLite lives on the container filesystem. On Cloud Run that means:

- **Cold start / new revision:** each fresh container starts with an **empty** database and must **rescan** logs from `INDEXER_FROM_BLOCK` / `indexerFromBlock` (can take many minutes over a long history).
- **Multiple instances:** if **maximum instances** is more than **1**, requests can hit **different** containers with **different** (or empty) DB files. `/health` may show `wager_count: 0` and `last_indexed_block: null` on one instance while another is mid-sync.

So “switching contracts” is not enough if the service is scaled horizontally on ephemeral storage. See [Making the hosted index durable](#making-the-hosted-index-durable-recommended) below.

## Pointing the indexer at the V3 factory

The **live** process (`service.indexer.live_api`) reads the factory address from **`config/deployments.json` inside the image** (copied at build time) unless overridden by env:

| On-chain contract | Config key (`baseSepolia.*`) | Env override (optional) |
|-------------------|------------------------------|-------------------------|
| `ParamutuelFactoryV3` (unified) | `factoryAddress` | `FACTORY_ADDRESS` |

V3 is a **single** factory covering both enumerated and freeform modes (ADR-0010); legacy V1/V2/freeform factories and their config keys have been removed.

**Steps to switch over after you deploy a new factory on-chain:**

1. **Record the deployment block** (from the deploy transaction receipt).
2. **Edit `config/deployments.json`** for that network:
   - Set `factoryAddress` to the **new** V3 address.
   - Set **`indexerFromBlock`** to the V3 deployment block (or earlier if you want full history). If the new factory was deployed **after** the indexer already advanced its cursor, you must **reset the cursor** (see below) or you will **never** see older creates for that factory.
3. **Align image defaults:** if you rely on Dockerfile env for cold-start `INDEXER_FROM_BLOCK`, update `INDEXER_FROM_BLOCK` in the root `Dockerfile` to match the same starting block (or remove it and depend only on `indexerFromBlock` in JSON).
4. **Redeploy Cloud Run** so the container ships the updated `config/deployments.json` and indexer code (`./script/deploy/redeploy_cloud_run_indexer.sh` or UI “Edit & deploy new revision”).
5. **Optional Cloud Run console overrides** for emergencies (hotfix without rebuilding): set `FACTORY_ADDRESS`, `INDEXER_FROM_BLOCK`, `RPC_URL_BASE_SEPOLIA`. Do not set `INDEXER_FROM_BLOCK` to empty unless `indexerFromBlock` is present in the image’s JSON.
6. **Verify:** `GET /health` on a **single** long-lived instance should eventually show non-null `last_indexed_block`, growing `wager_count`, and `factory_address` echoing your config.

**Resetting the cursor (backfill / new factory):** the sync cursor is `last_indexed_block` in SQLite metadata. On ephemeral storage, a new container already starts “from scratch” using `indexerFromBlock`. For a **persistent** DB, delete the DB file or run a one-off maintenance procedure to delete meta rows and re-sync from the desired block (operationally: simplest is replace the volume or delete `indexer.db` and restart with a correct `indexerFromBlock`).

## Making the hosted index durable (recommended)

Pick one path; SQLite on ephemeral `/tmp` is only OK for demos.

1. **Minimum viable (no code change):** Cloud Run → service → **maximum instances = 1** (and usually **minimum instances = 1** to reduce cold starts). Every user hits the same SQLite file for the lifetime of that revision. You still **lose the DB on each new revision deploy** unless you add storage (next options).
2. **Persistent disk / volume:** mount a **read-write block or file volume** (e.g. Cloud Run volume backed by persistent storage) and set `INDEXER_DB_PATH` to a path **on that volume**. Keep **max instances = 1** so only one writer touches SQLite. Verify your platform’s docs: network file systems and SQLite are picky about locking.
3. **Proper backend (larger change):** store state in **PostgreSQL** (e.g. Cloud SQL) or another shared database and adjust the indexer to use it instead of SQLite—this is the robust fix if you need **multiple replicas** or **zero data loss** across deploys.

After any of these, redeploy and confirm `/wagers` returns data and the live test indexer visibility check can pass when pointed at this URL.

## Environment (defaults in Dockerfile)

The root `Dockerfile` sets everything needed for a no-console deploy:

- `RPC_URL_BASE_SEPOLIA` = `https://sepolia.base.org` (public RPC; override for a private endpoint if you hit rate limits)
- `INDEXER_FROM_BLOCK` = `39608044` (factory deploy block for the current testnet factory)
- `INDEXER_NETWORK`, `INDEXER_DB_PATH`, `INDEXER_POLL_INTERVAL_SECONDS`, `PORT` = as in the Dockerfile

Optional overrides in the Cloud Run UI (only if needed): `FACTORY_ADDRESS`, `RPC_URL_BASE_SEPOLIA`, `INDEXER_FROM_BLOCK`, `INDEXER_DB_PATH`, etc.

**Do not** set `INDEXER_FROM_BLOCK` to an empty value in the console: that overrides the Dockerfile default with “unset”, and the live indexer then relies on `indexerFromBlock` in `config/deployments.json` inside the image (added in-repo next to the factory). If both are missing, the container fails fast at startup.

`INDEXER_CHUNK_SIZE` (default `120` in the Dockerfile) sets the first `eth_getLogs` window; the indexer **bisects** the range automatically if the RPC returns HTTP 400 for an oversized window.

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
