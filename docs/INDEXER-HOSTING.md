# Live indexer hosting

The indexer exists so **any client**—wallet UI, explorer, or **agent**—can discover open wagers and pool state without trusting a proprietary API. That matches Paramutuel’s model: permissionless on-chain betting with transparent, machine-readable market data.

GitHub Pages is static-only, so the indexer HTTP API (`/health`, `/wagers`, `/wagers/:address`, …) must run on a container host.

**Canonical setup:** Google Cloud Run — see [`CLOUD-RUN-HOSTING.md`](CLOUD-RUN-HOSTING.md) (Dockerfile at repo root, env defaults, redeploy notes).

## What runs

- Process: `python3 -m service.indexer.live_api`
- Log sync loop and HTTP API share one process and SQLite (`INDEXER_DB_PATH`, typically ephemeral `/tmp` on Cloud Run).

## Repo defaults

- Factory and indexer start block: `config/deployments.json` (`baseSepolia.factoryAddress`, `baseSepolia.indexerFromBlock`). V3 is one unified `ParamutuelFactoryV3` — no separate V1/V2/freeform keys.
- Explorer / dApp API base: `baseSepolia.explorerApiBase` in the same file.

## Wire the hosted explorer

After you have the indexer URL:

```bash
./script/testnet/set_explorer_api_base.sh "https://your-indexer.example.run.app"
```

Commit and push `config/deployments.json` so GitHub Pages picks up the default.

## Notes

- Ephemeral DB: on cold start the indexer replays logs from `indexerFromBlock` / `INDEXER_FROM_BLOCK`. This costs one `eth_getLogs` per chunk, so it grows with the factory's age (see [`CLOUD-RUN-HOSTING.md`](CLOUD-RUN-HOSTING.md)). Use persistent storage for anything long-lived.
- **Reorgs:** derived state is insert-only, so a reorg that moves or drops a transaction could double-count a stake or leave a ghost one. The indexer stays `INDEXER_CONFIRMATIONS` blocks behind the head (default 5) to make this unlikely. After a reorg deeper than that, delete the database and let it resync.
- **Health:** `GET /health` reports `sync_lag_blocks`, `last_sync_error` and `skipped_log_count`. A skipped log is lost until the database is rebuilt, so anything above zero needs a look.
- After a **new factory** deploy, update `factoryAddress` and `indexerFromBlock` (`script/testnet/set_factory_address.sh` does both), then redeploy the hosted indexer.
