# Contract Upgrade Runbook (Testnet-first)

This runbook is the canonical checklist for factory/wager contract upgrades and redeploys.

## 1) Pre-change safety

- Confirm scope: ABI break vs. parameter-only change.
- Update ADR/docs first for intentional behavior changes.
- Ensure `config/service.env` has `RPC_URL_BASE_SEPOLIA`, `PRIVATE_KEY`, `TREASURY_ADDRESS` (loaded via `script/lib/load_service_env.sh`).
- Record current deployed factory from `config/deployments.json`.

## 2) Local verification gates

- `forge build`
- `forge test`
- After **V3** bytecode changes, refresh the gas write-up: `forge test --match-contract ParamutuelV3GasReport -vv` and update [`PARAMUTUEL-V3-GAS.md`](PARAMUTUEL-V3-GAS.md) (full table: `bash script/profile_v3_gas.sh`).
- `python3 -m unittest discover -s service/indexer/tests` (includes HTTP API routes, V3 `apply_log` branches, live_api factory config)
- `python3 -m unittest discover -s service/control_panel/tests`
- `python3 -m unittest discover -s service/resolution/tests`
- `python3 -m unittest discover -s mcp_server/tests`
- `PYTHONPATH=. python3 -m unittest discover -s agents/paramutuel_bettor/tests`
- `(cd dapp && npm ci)` then `node --test dapp/tests/logic.test.js` (installs ethers for `freeformV3AnswerId` tests)

If any fail, do not deploy.

## 3) ABI sync + compatibility

- `bash script/sync-abi.sh` (syncs **v1, v2, freeform (ADR-0009), and v3** artifacts into `dapp/abi/` and `mcp_server/abi/`).
- If ABI changed, update all callers (`dapp`, `service`, `mcp_server`, bet scout, static site copies, testnet suites).
- Re-run full gates after updates.

## 4) Deploy new factory

- `./script/testnet/launch_testnet.sh` (sources `config/service.env` via `script/lib/load_service_env.sh`; ensure that file exists — copy from `config/service.env.example`).

Expected outcomes:
- New on-chain factory deployed.
- `config/deployments.json` auto-updated with new `baseSepolia.factoryAddress`.

## 5) Hosting propagation

- Update `config/deployments.json`:
  - `baseSepolia.factoryAddress` is set by `launch_testnet.sh` for the unified **`ParamutuelFactoryV3`**. V3 is a single factory covering both enumerated and freeform modes — no separate V2/freeform keys.
  - Set `indexerFromBlock` to a block **at or before** the V3 factory deployment; if you redeploy the factory after the indexer has already synced, backfill or reset the indexer DB with a lower cursor so create events are not missed.
- **Indexer live API** resolves the factory from env `FACTORY_ADDRESS` or `factoryAddress` in the deployments file (see `service/indexer/live_api.py`). `/health` echoes the configured factory.
- Update the root `Dockerfile` env `INDEXER_FROM_BLOCK` if you rely on image defaults for Cloud Run.
- Commit and push:
  - `config/deployments.json`
  - `Dockerfile` (if the default from-block changed)
  - any ABI/docs/test changes.

## 6) Redeploy hosted components

- GitHub Pages redeploy should trigger on push (`deploy-site.yml`).
- **Cloud Run** indexer: rebuild and deploy a new revision from the updated `master` (see [`CLOUD-RUN-HOSTING.md`](CLOUD-RUN-HOSTING.md) for factory env keys, `indexerFromBlock`, cursor resets, and **durable hosting** if `/wagers` stays empty).
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
