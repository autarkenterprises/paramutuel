# ADR-0001: Core Immutability and Delegated Resolution

- **Status:** Accepted (design target)
- **Date:** 2026-03-20

## Context

The protocol thesis requires:

- permissionless market creation
- arbitrary proposition markets
- configurable/decentralizable resolution
- minimal long-term dependence on protocol upgrades

Current markets already store a `resolver` address and only accept `resolve/retract` from that address.

Open question: is this sufficient for service-agnostic, secure delegation to future resolver systems (including oracle contracts)?

## Decision

1. **Treat market contracts as immutable settlement primitives.**
   - Each market has immutable `proposer` and `resolver`.
   - Resolver delegation is configured at market creation.

2. **Resolver systems evolve externally, not inside the core market contract.**
   - A resolver may be:
     - the proposer EOA (default),
     - a multisig/service address,
     - a dedicated oracle/dispute contract.

3. **Pairing between markets and resolver authority is performed by the proposer at creation time.**
   - This is done via dApp, service UI, script, or direct contract call.
   - dApp mediation does **not** reduce permissionlessness because direct calls remain available.

4. **For oracle-style resolution, pairing workflow is explicit and event-driven.**
   - Resolver/oracle watches factory `MarketCreated` events where `resolver == oracleAddress`.
   - Oracle indexes candidate markets and applies its own policy/spec to decide whether to resolve.
   - Oracle sends `resolve/retract` transaction to the specific market address when conditions are met.

5. **No additional core protocol coupling is required for delegation itself.**
   - The market already needs only one trust anchor: authorized resolver address.

## Security and Non-Exploitation Workflow

### Baseline (EOA/service resolver)

1. Proposer chooses resolver address.
2. Market is created with immutable resolver.
3. Only resolver can finalize in window.
4. Anyone can `expire()` after deadline to prevent stuck funds.

### Oracle-style resolver (recommended pattern)

1. Proposer chooses oracle contract address as resolver.
2. Proposer optionally registers market metadata with oracle module (off-chain or on-chain policy registry).
3. Oracle tracks market state and external data feed.
4. Oracle finalizes market by calling `resolve/retract`.

## Consequences

### Positive

- Core protocol remains stable and minimal.
- Resolver innovation can iterate independently.
- Supports heterogeneous trust models per market.

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
  - prominently display proposer/resolver per market

## Future-Proofing Notes

If future resolver modules need richer deterministic matching, add this outside the core market via:

- resolver module registry contracts, and/or
- market metadata URIs/hashes indexed off-chain

without changing the settlement logic of deployed markets.

