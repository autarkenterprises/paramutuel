# Paramutuel Execution Roadmap

Date: 2026-03-20  
Status: Draft v1 (checkpoint-driven)

This roadmap implements the architecture and governance decisions in `research/adr/`.

## Guiding constraints

- Core market protocol should remain as immutable as practical.
- Resolution must stay **configurable** per market (`resolver` address), enabling independent resolver evolution.
- Governance is required at launch for fee policy and treasury custody.
- Testnet certification must include **multiple markets in all lifecycle states**.
- dApp and service must include an odds/payout preview capability.
- Indexing should start as a **minimal custom indexer** with strong tests and low dependency footprint.

---

## Checkpoint 0 — Program Initialization

**Goal:** Establish ownership, timeline, and baseline tooling.

**Deliverables**
- Owner map for tracks:
  - Protocol
  - dApp
  - Service entity
  - Governance/Treasury
  - Data/Indexer
- CI baseline:
  - `forge test`
  - coverage command
  - JS syntax checks
- ADR set reviewed and accepted.

**Exit criteria**
- Team agrees on this roadmap and change-control process.

---

## Checkpoint 1 — Chain and Fee Viability Study (moved early)

**Goal:** Select target chain and initial protocol fee based on viability evidence.

**Deliverables**
- Chain comparison memo (L2s + candidate chains):
  - tx cost profile for `createMarket`, `placeBet`, `resolve`, `claim`, `expire`
  - wallet/UX ecosystem
  - stablecoin liquidity and on/off-ramp availability
  - indexer/data tooling maturity
- Initial fee recommendation memo:
  - benchmark against direct/adjacent competitors
  - bettor outcome sensitivity (1%, 2%, 3%, etc.)
  - expected revenue under TAM scenarios

**Exit criteria**
- Chosen launch chain(s).
- Chosen initial protocol fee and review cadence.

---

## Checkpoint 2 — Governance + Treasury Safe Readiness

**Goal:** Operational governance and custody before production deployment.

**Deliverables**
- Safe deployment on testnet:
  - owner list
  - threshold (e.g., 2-of-3 / 3-of-5)
  - signer key policy (hardware wallets, recovery)
- Treasury operations runbook:
  - fee withdrawal process
  - signer rotation process
  - incident path
- Governance parameter policy:
  - how fee changes are proposed and approved
  - max bounds and review guardrails

**Exit criteria**
- Successful testnet rehearsal:
  - fee accrual + withdrawal to Safe
  - at least one governance-style operational drill.

---

## Checkpoint 3 — Protocol Production Hardening

**Goal:** Finalize protocol implementation quality for launch.

**Deliverables**
- Coverage/gas baseline report committed.
- Security checklist and audit scope.
- Deployment/verification runbook.
- Resolver delegation tests (EOA, delegated service address).

**Exit criteria**
- All protocol tests pass.
- Coverage and gas reports accepted.
- No unresolved critical issues.

---

## Checkpoint 4 — Minimal Custom Indexer v1

**Goal:** Provide deterministic market state querying for dApp and service.

**Deliverables**
- Event ingestion for:
  - `MarketCreated`, `BetPlaced`, `Resolved`, `Retracted`, `Expired`, `Claimed`, `FeeAccrued`, `FeeWithdrawn`
- Derived state:
  - active/resolved/retracted
  - overdue unresolved markets (`expire` candidates)
  - totals and resolver/proposer metadata
- API endpoints (minimal):
  - list markets by state
  - market details
  - sweep targets for expiry bot

**Exit criteria**
- Reorg-safe replay from configured start block.
- Deterministic rebuild test passes.

---

## Checkpoint 5 — dApp v1.1 (Production Candidate)

**Goal:** Harden dApp for mainnet UX and resolver configurability.

**Deliverables**
- Resolver UX:
  - explicit proposer vs resolver display
  - clear warnings for delegated resolver choice
- Odds calculator:
  - current implied payout multiple per outcome
  - expected payout for entered bet
  - post-bet odds impact preview
- Multi-market explorer view powered by indexer.

**Exit criteria**
- Usability pass with testnet users on all major flows.
- Correct odds/payout preview against fixture scenarios.

---

## Checkpoint 6 — Service Entity MVP

**Goal:** Launch independent proposal/resolution operations on testnet.

**Deliverables**
- Service web presence and policy docs:
  - proposition standards
  - resolution policy/SLA
  - transparency dashboard
- Operator console for creating/resolving markets.
- Automated sweeper:
  - scans overdue unresolved markets
  - calls `expire()` as a network courtesy
  - idempotent and monitored

**Exit criteria**
- Service demonstrates repeated propose/resolve cycles.
- Sweeper successfully expires overdue markets across multiple test markets.

---

## Checkpoint 7 — Full Testnet Certification (Protocol + dApp + Service)

**Goal:** Validate end-to-end behavior with realistic concurrency.

**Required scenario matrix**
- At least 5+ concurrent markets:
  - open, resolved, retracted, expired, delegated-resolver
- Flows:
  - create -> bet -> resolve -> claim
  - create -> bet -> retract -> refund claim
  - create -> unresolved -> expire -> refund claim
  - fee accrual/withdrawal to treasury

**Exit criteria**
- Two clean rehearsal runs with no critical defects.
- Signed launch readiness review.

---

## Checkpoint 8 — Mainnet/L2 Launch

**Goal:** Controlled production launch with observability.

**Deliverables**
- Factory deployment + verification.
- dApp release with chain/address registry.
- Service entity live with sweep automation.
- Monitoring dashboards:
  - market counts by state
  - unresolved-overdue count
  - fee flows

**Exit criteria**
- First production markets complete full lifecycle successfully.
- Post-launch incident window passes with no critical regressions.

---

## Checkpoint 9 — Resolver Module R&D (Post-Launch Parallel Track)

**Goal:** Build decentralized resolver alternatives without changing core protocol.

**Deliverables**
- Resolver module interface and prototype(s):
  - optimistic/challenge model and/or
  - bonded dispute model
- Pilot markets using delegated module resolvers.

**Exit criteria**
- Module can resolve real markets via delegated resolver path.
- Formal migration/positioning plan for expanded decentralization.

---

## Ongoing Quality Requirements

- Every new feature includes tests.
- Coverage and gas reports updated as part of PR process.
- Keep dependency surface minimal across dApp/service/indexer.
- Maintain explicit changelog for protocol-adjacent operational changes.

