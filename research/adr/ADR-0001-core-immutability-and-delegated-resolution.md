# ADR-0001: Core Immutability and Delegated Resolution

- **Status:** Accepted (design target)
- **Date:** 2026-03-20

## Context

The protocol thesis requires:

- permissionless wager creation
- arbitrary proposition wagers
- configurable/decentralizable resolution
- minimal long-term dependence on protocol upgrades

Current wagers already store a `resolver` address and only accept `resolve/retract` from that address.

Open question: is this sufficient for service-agnostic, secure delegation to future resolver systems (including oracle contracts)?

## Decision

1. **Treat wager contracts as immutable settlement primitives.**
   - Each wager has immutable `proposer` and `resolver`.
   - Resolver delegation is configured at wager creation.

2. **Resolver systems evolve externally, not inside the core wager contract.**
   - A resolver may be:
     - the proposer EOA (default),
     - a multisig/service address,
     - a dedicated oracle/dispute contract.

3. **Pairing between wagers and resolver authority is performed by the proposer at creation time.**
   - This is done via dApp, service UI, script, or direct contract call.
   - dApp mediation does **not** reduce permissionlessness because direct calls remain available.

4. **For oracle-style resolution, pairing workflow is explicit and event-driven.**
   - Resolver/oracle watches factory `WagerCreated` events where `resolver == oracleAddress`.
   - Oracle indexes candidate wagers and applies its own policy/spec to decide whether to resolve.
   - Oracle sends `resolve/retract` transaction to the specific wager address when conditions are met.

5. **No additional core protocol coupling is required for delegation itself.**
   - The wager already needs only one trust anchor: authorized resolver address.

## Security and Non-Exploitation Workflow

### Baseline (EOA/service resolver)

1. Proposer chooses resolver address.
2. Wager is created with immutable resolver.
3. Only resolver can finalize in window.
4. Anyone can `expire()` after deadline to prevent stuck funds.

### Oracle-style resolver (recommended pattern)

1. Proposer chooses oracle contract address as resolver.
2. Proposer optionally registers wager metadata with oracle module (off-chain or on-chain policy registry).
3. Oracle tracks wager state and external data feed.
4. Oracle finalizes wager by calling `resolve/retract`.

## Consequences

### Positive

- Core protocol remains stable and minimal.
- Resolver innovation can iterate independently.
- Supports heterogeneous trust models per wager.

### Tradeoffs

- Misconfiguration risk (proposer sets wrong resolver).
- Resolver-specific metadata/policy is external to core and must be managed by resolver systems.

## Required Mitigations

- dApp guardrails:
  - resolver address validation
  - clear UX warning: resolver controls finalization
- service policy transparency:
  - publish resolver standards and SLA
- indexer/explorer visibility:
  - prominently display proposer/resolver per wager

## Future-Proofing Notes

If future resolver modules need richer deterministic matching, add this outside the core wager via:

- resolver module registry contracts, and/or
- wager metadata URIs/hashes indexed off-chain

without changing the settlement logic of deployed wagers.

## After Action Report

**AAR date:** 2026-05-06
**AAR status:** Backfilled 2026-05-06 per ADR-0012

**Outcome vs success criteria** (criteria implicit in original Decision; explicit articulation here):

- *Wager contracts treated as immutable settlement primitives with immutable `proposer` / `resolver`.* **Met** — `ParamutuelWagerV3` constructor sets `resolver` once and never mutates it (`src/ParamutuelWagerV3.sol`).
- *Resolver systems evolve externally to the core contract.* **Met** — delegated resolution shipped as an external Cloud Run service in `service/resolution/` (see `docs/RESOLUTION-SERVICE.md`), with no contract coupling.
- *Pairing performed by proposer at creation time, dApp-mediated path optional.* **Met** — `createEnumeratedWager` / `createFreeformWager` accept `resolver` directly; dApp, MCP, and direct `cast` call paths all work.
- *Anyone can `expire()` after deadline to prevent stuck funds.* **Met** — `ParamutuelWagerV3.expire` is permissionless; covered by Foundry tests.

**Outcome vs failure criteria:**

- *Misconfiguration risk (wrong resolver address).* **Mitigated** — dApp validation, indexer prominently displays resolver, `WagerCreated` event includes resolver address. Risk is not zero (proposer can still pick a wrong address) but observable.
- *Resolver-specific metadata leaks back into core.* **Avoided** — no resolver registry on-chain; metadata stays in indexer / off-chain runbooks.

**Lessons:** none new — this ADR is foundational and absorbed without surprise.

**Follow-ups:** none. Future oracle-style resolver work would be a new ADR, not an extension of this one.

**Revision schedule:** none required.

