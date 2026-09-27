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

### AAR revision — 2026-09-26 (ADR-0019 verification audit)

**AAR status:** Revisited 2026-09-26 — **correction**.

The original AAR's first two bullets are **wrong**. Neither closer defaults to the proposer: since commit `bc8e4a8` ("support time-only windows and forbid uncloseable no-max markets") `address(0)` **disables** the role. `ParamutuelFactoryV3` passes `bettingCloser` / `resolutionCloser` through unchanged, and instead rejects `bettingCloseTime == 0 && bettingCloser == 0` and `resolutionWindow == 0 && resolutionCloser == 0` with `InvalidLifecycleConfig`. Only the *resolver* defaults to the proposer (ADR-0001). `docs/WAGER-LIFECYCLE.md` already described the real behaviour; this ADR did not. There was no test for either the default or its absence.

Decision §1 / §2 are therefore superseded in part: read "default **proposer** when `address(0)`" as "**optional**; `address(0)` means no authority close for that transition (time-based only)".

Additional facts the original AAR omitted, now pinned by `test/ParamutuelV3Lifecycle.t.sol`:

- An early `closeBetting()` re-anchors the resolution window at the close time, so the effective deadline can be **earlier** than the immutable `resolutionDeadline` (which is informational only). The indexer / sweeper / resolution service already anchor on `betting_closed_at`.
- With a zero-time window the closer is the only way forward; if its key is lost, stake is locked (neither `retract` nor `expire` can run while betting is open). ADR-0001's "anyone can `expire()`" guarantee holds for time-bounded wagers only.

**Evidence:** `test_zeroAddressCloser_disablesRole`, `test_create_roleDefaultsAndDeadline`, `test_earlyAuthorityClose_shortensEffectiveResolutionDeadline`, `test_noMaxBetting_resolutionWindowAnchoredAtAuthorityClose`, `test_noMaxResolution_expireRequiresResolutionCloser`.

**Lessons:** `LESSONS.md` L-008 (AAR claims need a named test).
