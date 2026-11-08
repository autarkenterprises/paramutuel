# Live indexer hosting

The indexer exists so **any client**—wallet UI, explorer, or **agent**—can discover open wagers and pool state without trusting a proprietary API. That matches Paramutuel’s model: permissionless on-chain betting with transparent, machine-readable market data.

GitHub Pages is static-only, so the indexer HTTP API (`/health`, `/wagers`, `/wagers/:address`, …) must run on a container host.

**Canonical setup (ADR-0022):** a Compute Engine VM runs the indexer with its database on a persistent disk, and the Cloud Run service `paramutuel-git` keeps the public HTTPS URL as a proxy to it. The container image (`Dockerfile`, [`CLOUD-RUN-HOSTING.md`](CLOUD-RUN-HOSTING.md)) is still the way to run your own copy.

## What runs

- Process: `python3 -m service.indexer.live_api`
- Log sync loop and HTTP API share one process and one SQLite file (`INDEXER_DB_PATH`). On the VM it is on disk. In the container image it is in `/tmp`, which Cloud Run discards when an instance stops.

## Hosted deployment (ADR-0022)

| Part | Where |
|---|---|
| Public URL | `https://paramutuel-git-406244230167.europe-west1.run.app`, the Cloud Run service `paramutuel-git` (europe-west1). It runs Caddy's `reverse-proxy` on a single instance, and Google terminates TLS. |
| Indexer | Compute Engine VM `paramutuel-indexer`: e2-micro, `us-central1-a`, project `paratest-491920`, static IP `paramutuel-indexer-ip` (34.55.109.217), port 8080. |
| Code | `/opt/paramutuel`, a checkout of the commit in the instance metadata `indexer-ref`. |
| Unit | [`deploy/gce/paramutuel-indexer.service`](../deploy/gce/paramutuel-indexer.service), installed from that checkout by [`deploy/gce/startup.sh`](../deploy/gce/startup.sh) at every boot. |
| Database | `/var/lib/paramutuel/indexer.db`, the unit's systemd `StateDirectory` (on disk at `/var/lib/private/paramutuel`, readable with `sudo`). It survives restarts, reboots and updates. |
| RPC | `https://sepolia.base.org` (public). It accepts at most 200 blocks per `eth_getLogs`, so the unit reads 200-block chunks. The VM holds no secrets. |
| Cost guard | Budget alert "paramutuel monthly" at $5/month (50%, 90% and 100% of actual spend, 100% forecast). |

Operations (from the repo root, with `gcloud` authenticated):

- **Deploy a new commit** (push it first; the VM fetches it from GitHub):
  `GCP_PROJECT_ID=paratest-491920 INDEXER_REF=<40-char commit> ./script/deploy/gce_indexer.sh`
  Without `INDEXER_REF` the script uses `origin/master` as last fetched. It updates the pin and re-runs the startup script over SSH. A commit the repository lacks is refused on the VM, and the running release keeps running.
- **Logs:** `gcloud compute ssh paramutuel-indexer --zone us-central1-a --project paratest-491920 --command 'sudo journalctl -u paramutuel-indexer -n 100'`
- **Rebuild the index** (after a reorg deeper than `INDEXER_CONFIRMATIONS`, or a factory cutover to an earlier start block): run `sudo systemctl stop paramutuel-indexer && sudo rm -f /var/lib/private/paramutuel/indexer.db* && sudo systemctl start paramutuel-indexer` over the same SSH. A full replay from `indexerFromBlock` costs one `eth_getLogs` per 200 blocks.
- **Proxy:** `GCP_PROJECT_ID=paratest-491920 ./script/deploy/cloud_run_indexer_proxy.sh` re-points it if the VM's address changes. `redeploy_cloud_run_indexer.sh` refuses `paramutuel-git`. The Cloud Build trigger that redeployed the indexer image on every push to `master` is disabled, because it would replace the proxy.
- **Cost:** the e2-micro and its 20 GB `pd-standard` disk in us-central1 are within Compute Engine's Always Free allowance. The proxy bills only while serving requests, on one instance. Sources disagree on whether the free tier covers the VM's external IPv4 address (about $3.65/month if it does not), so check the first billing report.

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

- Ephemeral DB (container image only): on cold start the indexer replays logs from `indexerFromBlock` / `INDEXER_FROM_BLOCK`. This costs one `eth_getLogs` per chunk (one more for a chunk that creates wagers, and one per further 200 wagers once there are many), so it grows with the factory's age (see [`CLOUD-RUN-HOSTING.md`](CLOUD-RUN-HOSTING.md)). Use persistent storage for anything long-lived.
- **Reorgs:** derived state is insert-only, so a reorg that moves or drops a transaction could double-count a stake or leave a ghost one. The indexer stays `INDEXER_CONFIRMATIONS` blocks behind the head (default 5) to make this unlikely. After a reorg deeper than that, delete the database and let it resync.
- **Health:** `GET /health` reports `sync_lag_blocks`, `last_sync_error` and `skipped_log_count`. A skipped log is lost until the database is rebuilt, so anything above zero needs a look. A wager whose text could not be read at creation shows a blank proposition until a retry succeeds; retries back off from 15 seconds to at most an hour per wager, so a stubborn one never crowds out the rest.
- After a **new factory** deploy, update `factoryAddress` and `indexerFromBlock` (`script/testnet/set_factory_address.sh` does both), push, then deploy that commit with `script/deploy/gce_indexer.sh` and rebuild the index (above).
