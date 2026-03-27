# Full Testnet Rehearsal Plan

This checklist is the concrete execution path for ADR-0003 and the roadmap checkpoints.

Execution helpers:

- `script/testnet/launch_testnet.sh` (preflight + tests + deployment + service startup commands)
- `script/testnet/rehearsal_matrix.md` (operator scorecard for run tracking)

Recommended MVP chain order from Checkpoint 1: **Base first**, **Arbitrum second**.

## 1) Infrastructure and access

- Chain RPC endpoint selected and funded operator keys ready.
- One persistent host for:
  - indexer API (`service.indexer.api`)
  - explorer (`service.explorer.server`)
  - control panel web (`service.control_panel.web`)
  - sweeper daemon (`service.indexer.sweeper --loop`)
- TLS reverse proxy + DNS (if public URLs are used).
- Logs retained for all services.

## 2) Governance and treasury readiness (Checkpoint 2)

- Safe deployed on testnet.
- Signer threshold configured and signer drill completed.
- Fee withdrawal runbook tested once end-to-end.

## 3) Deploy and seed contracts

- Deploy `ParamutuelFactory` with target fee/min windows.
- Verify contracts and record addresses.
- Fund at least 6 distinct test accounts (proposers, bettors, resolvers, closers, sweepers).

## 4) Multi-market scenario matrix (ADR-0003)

Run at least 5 concurrent markets:

1. finite-window resolved
2. finite-window retracted
3. finite-window expired by third party
4. delegated resolver/closers
5. no-max closer-managed market (`bettingCloseTime=0`, `resolutionWindow=0`)

## 5) Service-layer exercise

- Indexer catches all events and derived states stay correct.
- Explorer shows all mixed states.
- Control panel CLI and web both perform lifecycle actions.
- Sweeper expires overdue candidates and is idempotent on repeat loops.

## 6) Pass/fail criteria per rehearsal

Pass only if all are true:

- zero failed contract interactions due to invalid lifecycle choreography
- all candidate markets end in valid terminal states (`RESOLVED` or `RETRACTED`)
- no market remains "stuck open" contrary to configured roles/windows
- fee accrual + withdrawal matches expected accounting
- service logs show successful retry/idempotency behavior

Fail if any are true:

- unresolved market cannot be progressed despite available role keys and configured lifecycle
- indexer/explorer show contradictory market state
- sweeper repeatedly fails same valid candidate without alert

## 7) Two-run certification

- Run rehearsal twice on separate days with fresh markets.
- Capture incident notes and remediation between runs.
- Declare launch readiness only after second clean pass.

## 8) Remaining external requirements before public launch

- domain registration and HTTPS certificates (if public-facing web)
- production VPS/container orchestration
- monitoring + alerts (index lag, service downtime, sweeper failures, unresolved-open count)
- backup/restore procedure for indexer DB or migration to managed DB
