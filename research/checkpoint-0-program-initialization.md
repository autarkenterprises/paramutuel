# Checkpoint 0 Implementation: Program Initialization

Status: In progress  
Owner: Project management org  
Linked roadmap: `research/execution-roadmap.md` (Checkpoint 0)

## Objective

Establish an operational baseline so protocol, dApp, service, governance, and data tracks can execute in parallel with explicit accountability.

## Deliverables

### 1) Track owner map

Fill in named owners before Checkpoint 1 starts:

| Track | Primary owner | Backup owner | Notes |
|------|----------------|--------------|-------|
| Protocol contracts | TBD | TBD | Foundry code/tests, deployment prep |
| dApp | TBD | TBD | UX, multi-market explorer, odds preview |
| Service entity | TBD | TBD | Proposal/resolution ops + sweeper |
| Governance/Treasury | TBD | TBD | Safe ops, signer policy, fee governance |
| Data/Indexer | TBD | TBD | Event ingestion, market state API |
| Security/Audit coordination | TBD | TBD | Threat model, audit vendor, fixes |

### 2) Operating cadence

- Weekly checkpoint review (owner updates + blockers)
- Biweekly risk review (security + governance)
- Roadmap change-control: ADR update required for architecture-impacting changes

### 3) CI baseline (minimum)

- `forge build`
- `forge test`
- `forge coverage --ir-minimum` (reporting command for review, not required on every PR if runtime is high)
- dApp JS syntax check:
  - `node --check dapp/app.js`

### 4) Decision log discipline

- New architecture or governance decisions must be captured in `research/adr/`.
- Roadmap progress should be tracked by appending status to checkpoint files under `research/`.

## Exit criteria

- Track owner table fully populated
- Meeting cadence agreed and scheduled
- CI baseline commands documented and executable
- No unresolved ownership gaps for Checkpoint 1

