# ADR-0005: Delegated betting and resolution window closure

## Status

Accepted (MVP extension)

## Context

On-chain contracts cannot observe off-chain “event start” or “grading done” directly. Fixed `bettingCloseTime` and `resolutionDeadline` provide **timeouts**, but operators may need **authorized addresses** to align chain state with reality (e.g. close betting when a match starts, or end the resolver window early so a sweeper can `expire()`).

## Decision

1. **`bettingCloser`** (immutable, default **proposer** when `address(0)` at `createWager`):
   - May call `closeBetting()` to set `bettingClosedByAuthority`.
   - `placeBet` reverts when `_bettingClosed()` is true: authority **or** `block.timestamp >= bettingCloseTime`.

2. **`resolutionCloser`** (immutable, default **proposer** when `address(0)`):
   - May call `closeResolutionWindow()` only after `_bettingClosed()`, setting `resolutionWindowClosedByAuthority`.
   - While that flag is set, `resolve` / `retract` revert (`ResolutionWindowOver`); `expire()` is allowed even before `resolutionDeadline`.

3. **Events**: `BettingClosedByAuthority`, `ResolutionWindowClosedByAuthority` for indexers and tooling.

4. **Factory** `WagerCreated` includes `bettingCloser` and `resolutionCloser` (resolved addresses) in the log data.

## Consequences

- Breaking change to `createWager` and `WagerCreated` topic.
- Indexer schema gains `betting_closer`, `resolution_closer`, flags for authority closures, and sweeper logic must treat early-closed resolution windows as expire-eligible.

## After Action Report

**AAR date:** 2026-05-06
**AAR status:** Backfilled 2026-05-06 per ADR-0012

**Outcome vs success criteria** (criteria implicit in Decision):

- *Immutable `bettingCloser` defaulting to proposer when zero-address.* **Met** — `ParamutuelWagerV3` carries the role; default-to-proposer behavior implemented and tested.
- *Immutable `resolutionCloser` with proposer fallback.* **Met** — same pattern.
- *Authority-driven `closeBetting()` and `closeResolutionWindow()` events.* **Met** — `BettingClosedByAuthority`, `ResolutionWindowClosedByAuthority` indexed.
- *Factory `WagerCreated` includes both closer addresses.* **Met** — V3 events expose them; indexer schema includes the columns.
- *Sweeper treats early-closed resolution windows as expire-eligible.* **Met** — `service/resolution/` and the testnet sweeper exercise this path.

**Outcome vs failure criteria:**

- *Breaking change to `createWager` topic.* **Triggered as designed** — V1 → V2 → V3 each broke the topic; clients migrate via the indexer's `protocol_version` field.
- *Indexer schema drift.* **Avoided** — schema migrations stayed in step with each contract version.

**Lessons:** none new — the role-defaulting pattern is the kind of tactical decision that doesn't generalize beyond this contract.

**Follow-ups:** none. The roles ship in V3 and are exercised by every wager.

**Revision schedule:** none required.
