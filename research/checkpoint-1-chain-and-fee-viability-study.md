# Checkpoint 1 Implementation: Chain and Fee Viability Study

Status: In progress (chain + fee evidence recorded in `chain-and-fee-review.md`)  
Owner: Governance + Protocol + Data tracks  
Linked roadmap: `research/execution-roadmap.md` (Checkpoint 1)

## Objective

Pick launch chain(s) and initial fee policy with evidence, early enough to influence treasury, governance, and GTM planning.

## Required outputs

1. Chain selection memo → **`research/chain-and-fee-review.md`** (sections 1, 3–5)
2. Initial fee recommendation memo → **`research/chain-and-fee-review.md`** (sections 6–7)
3. TAM/throughput viability assumptions table → scoring table below still **TBD**; revenue sensitivity started in review doc §7.4

## A) Chain selection framework

Evaluate each candidate chain with measurable criteria:

| Criterion | Weight | Candidate A | Candidate B | Candidate C | Notes |
|----------|--------|-------------|-------------|-------------|-------|
| Avg tx cost (`createMarket`) | High | TBD | TBD | TBD | Measured on testnet/mainnet env |
| Avg tx cost (`placeBet`) | High | TBD | TBD | TBD | |
| Avg tx cost (`resolve`/`retract`/`expire`) | Medium | TBD | TBD | TBD | |
| Avg tx cost (`claim`) | High | TBD | TBD | TBD | |
| Finality/latency UX | Medium | TBD | TBD | TBD | |
| Stablecoin liquidity depth | High | TBD | TBD | TBD | |
| Wallet/user familiarity | Medium | TBD | TBD | TBD | |
| Indexer/tooling maturity | High | TBD | TBD | TBD | |
| Regulatory/geo operational fit | Medium | TBD | TBD | TBD | Non-legal internal assessment |

Decision rule: pick chain with best weighted score that satisfies liquidity + UX floor.

## B) Fee recommendation framework

Initial protocol fee BPS candidates: `100`, `200`, `300` (or alternatives).

For each candidate fee:

- bettor net payout impact by market profile
- expected protocol revenue under TAM scenarios
- competitiveness vs direct/adjacent products
- sensitivity to low-volume markets

### Scenario table (example)

| Scenario | Monthly handle | Fee bps | Gross protocol fee | Notes |
|---------|----------------|---------|--------------------|-------|
| Conservative | TBD | TBD | TBD | |
| Base | TBD | TBD | TBD | |
| Aggressive | TBD | TBD | TBD | |

## C) TAM assumptions (initial)

Capture explicit assumptions:

- target user cohorts (creator-led communities, bettors, resolution service clients)
- expected active markets/month
- avg unique bettors/market
- avg wager size distribution

All assumptions must cite source or operator rationale.

## Exit criteria

- Launch chain selected and documented
- Initial fee value selected with rationale
- Fee review cadence specified (e.g., quarterly or threshold-triggered)
- Memo approved by governance and protocol leads

