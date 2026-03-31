# Contract Upgrade Runbook (Testnet-first)

This runbook is the canonical checklist for factory/wager contract upgrades and redeploys.

## 1) Pre-change safety

- Confirm scope: ABI break vs. parameter-only change.
- Update ADR/docs first for intentional behavior changes.
- Ensure `.env` has `RPC_URL_BASE_SEPOLIA`, `PRIVATE_KEY`, `TREASURY_ADDRESS`.
- Record current deployed factory from `config/deployments.json`.

## 2) Local verification gates

- `forge build`
- `forge test`
- `python3 -m unittest discover -s service/indexer/tests`
- `python3 -m unittest discover -s service/control_panel/tests`
- `python3 -m unittest discover -s mcp_server/tests`
- `node --test dapp/tests/logic.test.js`

If any fail, do not deploy.

## 3) ABI sync + compatibility

- `bash script/sync-abi.sh`
- If ABI changed, update all callers (`dapp`, `service`, `mcp_server`, testnet suites).
- Re-run full gates after updates.

## 4) Deploy new factory

- `set -a && source .env && set +a`
- `./script/testnet/launch_testnet.sh`

Expected outcomes:
- New on-chain factory deployed.
- `config/deployments.json` auto-updated with new `baseSepolia.factoryAddress`.

## 5) Hosting propagation

- Update `config/deployments.json` (`baseSepolia.factoryAddress` is usually set by `launch_testnet.sh`):
  - Set `baseSepolia.indexerFromBlock` to the new factory deployment block.
- Update the root `Dockerfile` env `INDEXER_FROM_BLOCK` if you rely on image defaults for Cloud Run.
- Commit and push:
  - `config/deployments.json`
  - `Dockerfile` (if the default from-block changed)
  - any ABI/docs/test changes.

## 6) Redeploy hosted components

- GitHub Pages redeploy should trigger on push (`deploy-site.yml`).
- **Cloud Run** indexer: rebuild and deploy a new revision from the updated `master` (see [`CLOUD-RUN-HOSTING.md`](CLOUD-RUN-HOSTING.md)).
- Verify:
  - `GET /health` returns `ok`.
  - `GET /wagers` route works and reflects new factory over time.

## 7) Live end-to-end validation

- Live suite:
  - `TESTNET_MODE=readonly ./script/testnet/run_live_suite.sh`
  - `TESTNET_MODE=minimal-tx ./script/testnet/run_live_suite.sh`
  - `TESTNET_MODE=funded-tx ./script/testnet/run_live_suite.sh`
- Stress suite:
  - `STRESS_MODE=readonly ./script/testnet/run_stress_suite.sh`
  - `STRESS_MODE=tx ./script/testnet/run_stress_suite.sh`
  - `STRESS_MODE=funded-tx ./script/testnet/run_stress_suite.sh`

## 8) Post-deploy checklist

- Confirm `wagersCount()` increments on new factory.
- Confirm created wagers are queryable by hosted indexer/explorer.
- Document known lags (indexer catch-up/eventual consistency) in release notes.
- Tag release/commit with deployment tx hash and block number.
