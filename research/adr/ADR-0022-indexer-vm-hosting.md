# ADR-0022: Host the indexer on an Always Free VM behind its existing Cloud Run URL

Date: 2026-11-08
Status: **Accepted**
Builds on: ADR-0020 (operator step 3: redeploy the hosted indexer), ADR-0021, `docs/INDEXER-HOSTING.md`, `AGENTS.md` #1 / #4 / #5 / #15

## Context

The hosted indexer (`paramutuel-git`, Cloud Run, europe-west1) returned 500/503 because the project's billing account was closed. The operator has now attached a paid billing account (2026-11-08) and asked for the indexer to be set up again, as cheaply as the free allowances permit.

Redeploying the same Cloud Run service would bring back three defects in how it was hosted, all visible in its live configuration:

1. **The sync loop starves.** The service uses request-based billing, so Cloud Run throttles CPU outside requests. `live_api` runs its sync loop on a background thread of the same process, so the index advances only while somebody is waiting on a request.
2. **The database is thrown away.** The SQLite file lives in `/tmp`, an in-memory filesystem. When an idle instance scales to zero, the index goes with it. The next visitor starts a replay from `indexerFromBlock` (block 40,147,601). That is now 16 million blocks, and the public RPC caps `eth_getLogs` at 200 blocks (`-32614 eth_getLogs is limited to a 200 range`), so a replay takes at least 80,000 calls.
3. **Three databases.** `maxScale` is 3, and each instance indexes on its own, so two requests can get different answers.

Keeping CPU always allocated would fix (1). It costs about 2.6 million vCPU-seconds a month against a free allowance of 240,000, roughly $45 a month at list price, and it fixes neither (2) nor (3).

Compute Engine's free tier includes one e2-micro VM a month in us-west1, us-central1 or us-east1, plus 30 GB-months of standard persistent disk. A VM runs the indexer the way it was written: one always-on process with one database on a disk that survives restarts.

The web clients still need HTTPS. The explorer and dApp are served over HTTPS from GitHub Pages, so a browser blocks a plain-HTTP indexer as mixed content. The URL `https://paramutuel-git-406244230167.europe-west1.run.app` is wired into `config/deployments.json`, the MCP server, `Dockerfile.resolution` and the docs.

## Decision

1. **The indexer runs on a Compute Engine e2-micro** named `paramutuel-indexer` in `us-central1-a`. It has a 20 GB `pd-standard` boot disk and a reserved static external IP, and runs Ubuntu 24.04 minimal, whose Python 3.12 matches the container image. The VM has no service account: it needs no Google API.
2. **The code is a pinned checkout of the public repository.** The deploy script records the commit in instance metadata (`indexer-ref`). A startup script (`deploy/gce/startup.sh`) runs at every boot and on every update. It checks that commit out into `/opt/paramutuel`, installs the systemd unit from that same checkout, and restarts the service. It does nothing if the ref is missing or unknown, so the VM never runs an unpinned tree. The indexer is stdlib-only, so nothing else is installed except `git`.
3. **The unit (`deploy/gce/paramutuel-indexer.service`) runs the container image's command.**
   - The database is at `/var/lib/paramutuel/indexer.db`, on the persistent disk.
   - The process runs as an unprivileged system user, under systemd sandboxing, and restarts on failure.
   - Logs are read in 200-block chunks, the public RPC's maximum.
   - The RPC is the public `https://sepolia.base.org`, so the VM holds no secrets.
4. **The public URL does not change.** The Cloud Run service `paramutuel-git` is redeployed as a reverse proxy to the VM:
   - The proxy is Caddy's `reverse-proxy` command, using the pinned image `caddy:2.10.0`.
   - It runs with `--max-instances=1`, and Google terminates TLS.
   - Its environment variables are cleared, which removes the leaked provider RPC URL from the service.
   - No client changes.
5. **The Cloud Build trigger that redeployed the indexer image on every push to `master` is disabled.** Otherwise the next push would replace the proxy with the old in-memory indexer.
6. **Firewall:** `tcp:8080` is open to instances tagged `paramutuel-indexer`. The API serves only `GET` and `OPTIONS` over public chain data, so a direct client gains nothing it could not get through the proxy.
7. **Cost guard:** an alert budget of $5 a month on the project, with alerts at 50%, 90% and 100%. Google's spend-cap budgets cover Cloud Run but not Compute Engine (checked 2026-11-08), so alerts are the guard there. The proxy is bounded by its one instance.
8. **The resolution service stays unhosted.** It holds the resolver's private key and acts only when the operator writes a decision, so it runs on the operator's machine when needed (`docs/RESOLUTION-SERVICE.md`). The key never reaches a cloud host.

## Decision points

- **Region `us-central1`:** a free-tier region. The proxy stays in europe-west1 because the URL encodes the region, at the price of about 100 ms across the Atlantic per request.
- **Static IP:** the proxy targets the VM by address, so the address must survive a stop and start. An in-use static address is priced like an ephemeral one.
- **Updates:** `script/deploy/gce_indexer.sh` sets `indexer-ref` and re-runs the startup script over `gcloud compute ssh`. A reboot does the same.
- **Chunk size 200:** the indexer bisects a failed range, so a lower RPC limit later costs extra calls, not correctness.

## Success criteria

- `https://paramutuel-git-406244230167.europe-west1.run.app/health` is served by the VM, with `sync_lag_blocks` under 100 once the replay ends, and `skipped_log_count` 0.
- The index survives a service restart and a VM reboot: `last_indexed_block` afterwards is at or above its value before, with no replay.
- One database: successive public `/health` responses never report a lower `last_indexed_block`.
- `script/tests/test_gce_indexer.py` covers three things:
  - the startup script's install, update, data-preservation and fail-closed paths, in a sandbox;
  - the unit's persistent database path and its parity with the container command;
  - the deploy and proxy scripts' `gcloud` calls.
  These tests fail before the files exist.
- The first full month's bill for the project is under $5 (revisited in the AAR).

## Failure criteria

- The project's monthly cost exceeds $5. Then reconsider the static IP and egress first.
- The replay does not reach the head within 24 hours on the public RPC.
- Requests through the proxy fail when the VM is healthy.

## Rejected alternatives

- **Cloud Run with CPU always allocated and a mounted volume:** costs about $45 a month. SQLite over a Cloud Storage FUSE mount has no reliable locking.
- **TLS on the VM through an `sslip.io` hostname:** Let's Encrypt's per-domain limit is shared by every `sslip.io` user and has been exhausted in practice. IP-address certificates (generally available since January 2026) need ACME-profile support that Caddy's issue tracker still reports as broken.
- **Pointing clients at a new URL:** that means touching five files and every client's configuration, and it gains nothing over keeping the URL.
- **Hosting the resolution service on the VM:** the private key would then sit on a cloud host for a process that acts only on the operator's decisions.

## After Action Report

Pending.
