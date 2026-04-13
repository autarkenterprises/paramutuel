# Live indexer hosting

The indexer exists so **any client**—wallet UI, explorer, or **agent**—can discover open wagers and pool state without trusting a proprietary API. That matches Paramutuel’s model: permissionless on-chain betting with transparent, machine-readable market data.

GitHub Pages is static-only, so the indexer HTTP API (`/health`, `/wagers`, `/wagers/:address`, …) must run on a container host.

**Canonical setup:** Google Cloud Run — see [`CLOUD-RUN-HOSTING.md`](CLOUD-RUN-HOSTING.md) (Dockerfile at repo root, env defaults, redeploy notes).

## What runs

- Process: `python3 -m service.indexer.live_api`
- Log sync loop and HTTP API share one process and SQLite (`INDEXER_DB_PATH`, typically ephemeral `/tmp` on Cloud Run).

## Repo defaults

- Factories and indexer start block: `config/deployments.json` (`baseSepolia.factoryAddress`, optional `factoryV2Address` / `factoryFreeformAddress`, `baseSepolia.indexerFromBlock`).
- Explorer / dApp API base: `baseSepolia.explorerApiBase` in the same file.

## Wire the hosted explorer

After you have the indexer URL:

```bash
./script/testnet/set_explorer_api_base.sh "https://your-indexer.example.run.app"
```

Commit and push `config/deployments.json` so GitHub Pages picks up the default.

## Notes

- Ephemeral DB: on cold start the indexer replays logs from `indexerFromBlock` / `INDEXER_FROM_BLOCK`.
- After a **new factory** deploy, update `indexerFromBlock` (and Dockerfile `INDEXER_FROM_BLOCK` if you rely on image defaults), then redeploy the hosted indexer.
