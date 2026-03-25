# ADR-0005: Delegated betting and resolution window closure

## Status

Accepted (MVP extension)

## Context

On-chain contracts cannot observe off-chain “event start” or “grading done” directly. Fixed `bettingCloseTime` and `resolutionDeadline` provide **timeouts**, but operators may need **authorized addresses** to align chain state with reality (e.g. close betting when a match starts, or end the resolver window early so a sweeper can `expire()`).

## Decision

1. **`bettingCloser`** (immutable, default **proposer** when `address(0)` at `createMarket`):
   - May call `closeBetting()` to set `bettingClosedByAuthority`.
   - `placeBet` reverts when `_bettingClosed()` is true: authority **or** `block.timestamp >= bettingCloseTime`.

2. **`resolutionCloser`** (immutable, default **proposer** when `address(0)`):
   - May call `closeResolutionWindow()` only after `_bettingClosed()`, setting `resolutionWindowClosedByAuthority`.
   - While that flag is set, `resolve` / `retract` revert (`ResolutionWindowOver`); `expire()` is allowed even before `resolutionDeadline`.

3. **Events**: `BettingClosedByAuthority`, `ResolutionWindowClosedByAuthority` for indexers and tooling.

4. **Factory** `MarketCreated` includes `bettingCloser` and `resolutionCloser` (resolved addresses) in the log data.

## Consequences

- Breaking change to `createMarket` and `MarketCreated` topic.
- Indexer schema gains `betting_closer`, `resolution_closer`, flags for authority closures, and sweeper logic must treat early-closed resolution windows as expire-eligible.
