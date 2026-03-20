# ADR-0004: Minimal Custom Indexer and Odds Calculator

- **Status:** Accepted
- **Date:** 2026-03-20

## Context

The project needs:

- service-agnostic market scanning
- a lightweight explorer for market states
- dApp/service odds and payout previews
- minimal dependencies with strong test coverage

## Decision

1. Build a **minimal custom indexer** first, not hosted subgraph.
2. Implement **odds/payout calculator** in dApp and service using indexed state + on-chain checks.
3. Keep indexer architecture simple and deterministic.

## Minimal Indexer Scope (v1)

Ingest and persist events:

- `MarketCreated`
- `BetPlaced`
- `Resolved`
- `Retracted`
- `Expired`
- `Claimed`
- `FeeAccrued`
- `FeeWithdrawn`

Derived fields:

- market status: `Open | Resolved | Retracted`
- unresolved overdue boolean (`now > resolutionDeadline` and still open)
- per-outcome totals, total pot, fee bps, proposer, resolver

Operational requirements:

- reorg-safe ingestion
- deterministic replay from a configured start block
- idempotent event application

## Odds / Payout Calculator Requirements

For each market/outcome:

1. **Current implied payout multiple if outcome wins now**
   - `multiple_i = netPot / outcomeTotal_i` (if `outcomeTotal_i > 0`)
   - where `netPot = totalPot - totalFees(totalPot)`

2. **Expected payout for user bet amount `x` on outcome `i`**
   - Pre-bet preview if market resolved immediately after this bet:
   - `newPot = totalPot + x`
   - `newOutcomeTotal_i = outcomeTotal_i + x`
   - `previewPayout = x / newOutcomeTotal_i * netPot(newPot)`

3. **Post-bet odds impact preview**
   - Show before/after payout multiple and pool share for selected outcome.

4. **Edge-case handling**
   - no-liquidity outcomes
   - markets no longer open
   - decimal precision and rounding disclosure

## Testing Requirements

- unit tests for formula correctness and rounding behavior
- fixture tests with multi-outcome markets
- integration tests against testnet indexed data for consistency

## Consequences

### Positive

- independent visibility layer for dApp and service
- supports scanner, sweeper, and analytics
- enables bettor decision support via odds preview

### Tradeoffs

- custom infra maintenance burden
- must handle chain reorg and backfill logic carefully

