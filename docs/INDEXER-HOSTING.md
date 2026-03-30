# Live indexer hosting (Render)

GitHub Pages is static-only, so a live indexer API must run on a service host.  
The lightest setup in this repo is Render free tier using `render.yaml`.

## What gets deployed

- Web service entrypoint: `service.indexer.live_api`
- Behavior:
  - runs the log sync loop continuously against your RPC
  - serves the HTTP API (`/health`, `/markets`, `/markets/:address`) on the same process

## Render setup

1. In Render, create a **Blueprint** from this repo (so `render.yaml` is applied automatically).
2. Deploy.

No manual env vars are required for the default Base Sepolia setup in this repo:
- RPC defaults to `https://sepolia.base.org` via `render.yaml` env config.
- Factory address defaults from `config/deployments.json` (`defaultNetwork` + `<network>.factoryAddress`).

Optional overrides:
- set `RPC_URL_BASE_SEPOLIA` in Render if you want a different RPC provider
- set `FACTORY_ADDRESS` if you need to temporarily override config without committing

The service URL will look like:
- `https://<your-service>.onrender.com`

## Wire website explorer default

After you have the service URL:

```bash
./script/testnet/set_explorer_api_base.sh "https://<your-service>.onrender.com"
```

Then commit/push `config/deployments.json`.  
`site/explorer.html` will use that value as the default API base automatically.

## Notes

- Render free tier does **not** support persistent disks. This repo's `render.yaml` is configured for free tier:
  - `INDEXER_DB_PATH=/tmp/indexer.db` (ephemeral)
  - `INDEXER_FROM_BLOCK=39562334` (latest Base Sepolia factory deployment block at time of writing)
- Free tier may cold-start after idle periods. On cold start, indexer state is rebuilt from `INDEXER_FROM_BLOCK`.
- If redeploying a new factory, update `INDEXER_FROM_BLOCK` to that deployment block for faster warm-up.
- If you need persistent index state across restarts, use a paid plan with a disk and set `INDEXER_DB_PATH` to disk storage.
