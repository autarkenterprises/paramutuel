# ADR-0003: Testnet Certification for Protocol, dApp, and Service

- **Status:** Accepted
- **Date:** 2026-03-20

## Context

Before live launch, protocol and all auxiliary layers must be validated on testnet.

Requirement clarified: tests must cover **multiple deployed markets** across **all lifecycle states**, not just isolated single-market happy paths.

## Decision

A launch candidate is not production-eligible unless protocol, dApp, and service all pass the multi-market certification matrix below.

## Certification Matrix (Required)

### A) Protocol (on-chain)

Run with at least 5 concurrently deployed markets:

- open markets with active bets
- resolved markets
- retracted markets
- expired markets
- markets with delegated resolvers

Must validate:

- market creation works repeatedly without state cross-contamination
- claims and fee withdrawals work correctly per market
- unresolved markets can be expired by third parties after deadline

### B) dApp (end-user)

Must support and correctly render:

- listing many markets with mixed states
- creating new market with default and delegated resolver
- placing bets and claiming from specific chosen market
- lifecycle state refresh under concurrent state changes

### C) Service Entity

Must demonstrate:

- market proposal cadence over multiple markets
- resolver service operations on multiple markets
- **expiry sweeper** job that scans unresolved overdue markets and calls `expire()`
- idempotent behavior (repeat sweeps do not break already-finalized markets)

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

