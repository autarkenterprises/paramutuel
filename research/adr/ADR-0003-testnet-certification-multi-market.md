# ADR-0003: Testnet Certification for Protocol, dApp, and Service

- **Status:** Accepted
- **Date:** 2026-03-20

## Context

Before live launch, protocol and all auxiliary layers must be validated on testnet.

Requirement clarified: tests must cover **multiple deployed wagers** across **all lifecycle states**, not just isolated single-wager happy paths.

## Decision

A launch candidate is not production-eligible unless protocol, dApp, and service all pass the multi-wager certification matrix below.

## Certification Matrix (Required)

### A) Protocol (on-chain)

Run with at least 5 concurrently deployed wagers:

- open wagers with active bets
- resolved wagers
- retracted wagers
- expired wagers
- wagers with delegated resolvers

Must validate:

- wager creation works repeatedly without state cross-contamination
- claims and fee withdrawals work correctly per wager
- unresolved wagers can be expired by third parties after deadline

### B) dApp (end-user)

Must support and correctly render:

- listing many wagers with mixed states
- creating new wager with default and delegated resolver
- placing bets and claiming from specific chosen wager
- lifecycle state refresh under concurrent state changes

### C) Service Entity

Must demonstrate:

- wager proposal cadence over multiple wagers
- resolver service operations on multiple wagers
- **expiry sweeper** job that scans unresolved overdue wagers and calls `expire()`
- idempotent behavior (repeat sweeps do not break already-finalized wagers)

## Exit Criteria for Mainnet/L2 Launch

- 100% pass of certification matrix in two independent rehearsal runs
- no critical defects outstanding
- post-mortem notes captured from rehearsal and incorporated

## Consequences

### Positive

- reduces false confidence from single-flow demos
- validates lifecycle behavior in realistic concurrent conditions
- ensures service courtesy obligation (`expire`) is operational

### Tradeoffs

- longer pre-launch cycle
- requires testnet ops discipline across protocol + app + service

## After Action Report

**AAR date:** 2026-05-06
**AAR status:** Backfilled 2026-05-06 per ADR-0012

**Outcome vs success criteria** (criteria taken from original "Certification Matrix"):

- *Protocol section — ≥ 5 concurrently deployed wagers across lifecycle states.* **Met** — `test/testnet/test_stress_base_sepolia.py` (multi-market stress suite, 2026-03-29) deploys multiple wagers and exercises bet / resolve / retract / expire concurrently. `test/testnet/test_live_base_sepolia.py` covers the live happy path.
- *dApp section — listing, creation, betting, claiming, lifecycle refresh.* **Met** — `dapp/` covers all of these against Base Sepolia; manual rehearsal documented in `docs/TESTNET-REHEARSAL.md`.
- *Service section — proposal cadence, resolver service ops, **expiry sweeper**, idempotent sweeps.* **Met** — `service/proposition/`, `service/resolution/` (with `--allow-execute` flag), and Cloud Run jobs cover this. Idempotency is asserted by sweep tests.
- *Two independent rehearsal runs with 100% pass + post-mortem captured.* **Partially met** — multiple rehearsal cycles have been run (commit cadence shows iterative tightening of the suites), but no explicit "rehearsal-1 / rehearsal-2 / post-mortem" artifact lives in `docs/`. This is now the dominant gap blocking mainnet readiness.

**Outcome vs failure criteria:**

- *False confidence from single-flow demos.* **Avoided** — the suites explicitly cover concurrency and lifecycle mixes.
- *Testnet ops discipline lapse.* **Avoided so far** — the V3-only sweep (2026-04 → 2026-05) rewrote both suites for V3 in `c00d286` (`test(testnet): rewrite Base Sepolia live+stress suites for V3-only`), so the certification posture was preserved through a major refactor.

**Lessons:** none new — this ADR's discipline is internalized.

**Follow-ups:**

- Capture two formal rehearsal runs with explicit pass / fail tally and a written post-mortem (or rehearsal log under `docs/log/`) before mainnet cutover. Track under `docs/TESTNET-REHEARSAL.md`.
- Add an extended-suite gating step in `script/test-extended.sh` once ADR-0013 lands, so the certification matrix is run in CI rather than ad hoc.

**Revision schedule:** before mainnet factory deploy (same gate as ADR-0002).

