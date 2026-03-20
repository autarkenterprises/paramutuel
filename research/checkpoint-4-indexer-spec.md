# Checkpoint 4 Implementation: Minimal Custom Indexer Spec

Status: In progress  
Owner: Data/Indexer track  
Linked roadmap: `research/execution-roadmap.md` (Checkpoint 4)

## Objective

Deliver a minimal, deterministic, reorg-safe indexer with low dependency footprint to power:

- dApp market explorer
- service proposal/resolution console
- overdue unresolved market sweeper (`expire`)

---

## 1) Event Ingestion Scope

Index these events from `ParamutuelFactory` and `ParamutuelMarket`:

- Factory:
  - `MarketCreated`
- Market:
  - `BetPlaced`
  - `Resolved`
  - `Retracted`
  - `Expired`
  - `Claimed`
  - `FeeAccrued`
  - `FeeWithdrawn`

---

## 2) Minimal Data Model

### `markets`

- `market_address` (pk)
- `factory_address`
- `proposer`
- `resolver`
- `collateral_token`
- `betting_close_time`
- `resolution_deadline`
- `state` (`OPEN | RESOLVED | RETRACTED`)
- `created_block`
- `created_tx_hash`

### `market_outcomes`

- `market_address`
- `outcome_index`
- `outcome_text`
- `outcome_total`

### `market_totals`

- `market_address`
- `total_pot`
- `total_fee_bps`
- `winning_outcome` (nullable)
- `total_winning_stake` (nullable)

### `events_log` (append-only)

- `event_id` (`tx_hash + log_index`)
- `market_address`
- `event_name`
- `block_number`
- `tx_hash`
- `payload_json`

### Derived flags (computed)

- `is_overdue_unresolved`:
  - `state == OPEN && now > resolution_deadline`

---

## 3) API Surface (v1)

- `GET /markets?state=open|resolved|retracted`
- `GET /markets/:address`
- `GET /markets/:address/events`
- `GET /sweeper/expire-candidates`

Optional:

- `GET /markets/:address/odds` (if odds module colocated)

---

## 4) Reorg + Replay Strategy

- Process in block order.
- Keep `last_finalized_block` and configurable confirmation depth.
- On reorg detection:
  - rollback to common ancestor
  - replay forward
- Ensure handlers are idempotent by `event_id`.

---

## 5) Test Plan

### Unit tests

- event decoding correctness
- idempotent write behavior
- derived state transitions

### Integration tests

- replay fixtures with multiple markets and mixed lifecycles
- reorg simulation with rollback/replay
- sweeper candidate correctness

### Acceptance gate

- Deterministic full rebuild from configured start block
- Correct state for:
  - open market
  - resolved market
  - retracted market
  - expired market

---

## 6) Dependency Policy

- Prefer standard library + one DB client + one RPC client.
- Avoid heavy framework lock-in.
- Keep runtime and deployment surface minimal.

