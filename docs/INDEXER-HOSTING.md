# Live indexer hosting (Render)

GitHub Pages is static-only, so a live indexer API must run on a service host.  
The lightest setup in this repo is Render free tier using `render.yaml`.

## What gets deployed

- Web service entrypoint: `service.indexer.live_api`
- Behavior:
  - runs the log sync loop continuously against your RPC
  - serves the HTTP API (`/health`, `/markets`, `/markets/:address`) on the same process

## Render setup

1. In Render, create **New Web Service** from this repo.
2. Render auto-detects `render.yaml`.
3. Set required secret env vars:
   - `RPC_URL_BASE_SEPOLIA` (or another RPC endpoint)
   - `FACTORY_ADDRESS` (optional if your config has `baseSepolia.factoryAddress`)
4. Deploy.

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

- Free tier may cold-start after idle periods.
- Persistent disk is configured in `render.yaml` (`/var/data/indexer.db`) so indexed state survives restarts.
