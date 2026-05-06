# ADR-0006: Surface separation between self-custody dApp and assisted website UX

## Status

Accepted

## Date

2026-03-30

## Context

The protocol allows wagers with arbitrary ERC-20 collateral, but transaction execution on Base requires ETH gas.

Business requirement:

- Users should be able to follow a wager link and place a bet with collateral token balances only.
- Contract changes are strongly disfavored; current core contracts should remain intact.
- Support should remain future-proof and general-purpose (not USDC-only at protocol level), while website UX can prioritize known happy paths (stablecoins and highly liquid tokens).

The project already has modular layers:

- immutable-ish protocol contracts
- advanced dApp interface
- centralized website and service layer

## Decision

1. **Preserve protocol contract boundaries**:
   - No gas-abstraction or relayer coupling is introduced in `src/` contracts.
   - No collateral-specific logic is added to contracts.

2. **Explicitly split product surfaces**:
   - **dApp (`/dapp`)** remains the advanced, power-user, self-custody interface to contracts.
   - **Website (`/site`)** may provide assisted transaction UX (gas sponsorship, policy rails, convenience flows).

3. **Keep assistance in upper layers only**:
   - All gasless or sponsored behavior is implemented in website/service components.
   - dApp remains fully functional without platform services and without dependencies on external relayer contracts.

4. **Token policy model**:
   - Protocol remains collateral-agnostic (any valid ERC-20 wager collateral).
   - Website can channel users toward curated happy-path tokens for assisted flows (USDC and major stablecoins), while retaining a universal fallback path.

## Consequences

### Positive

- Maintains long-term protocol composability and audit stability.
- Contains operational and dependency complexity in replaceable upper layers.
- Preserves a trustworthy "raw contract" interface for advanced users.
- Enables gradual rollout of assisted UX without protocol migration risk.

### Tradeoffs

- Two UX modes must be documented clearly to avoid user confusion.
- Assisted website flows require centralized policy and monitoring.
- Some edge-token assisted flows may be slower/costlier than curated stablecoin lanes.

## After Action Report

**AAR date:** 2026-05-06
**AAR status:** Backfilled 2026-05-06 per ADR-0012

**Outcome vs success criteria** (criteria implicit in Decision):

- *Protocol contract boundaries preserved.* **Met** — no gas-abstraction or relayer coupling exists in `src/`; V3 contracts are collateral-agnostic ERC-20.
- *Product surfaces split: `/dapp` advanced, `/site` assisted.* **Partially met** — `dapp/` is the self-custody power-user surface and works. `site/` is the marketing / navigation shell with the Resonance explorer skin and `bet.html` wallet staking page; **assisted UX (gas sponsorship, policy rails, convenience flows) is not yet shipped**. The surface is reserved but not occupied.
- *dApp fully functional without platform services.* **Met** — `dapp/` only requires an EIP-1193 wallet and a network RPC; no service-layer dependency.
- *Token policy: protocol collateral-agnostic; site curates happy paths.* **Met for protocol**, partially met for site (the Tier-1 / Tier-2 distinction exists in copy but not yet in flow code).

**Outcome vs failure criteria:**

- *Two UX modes confuse users.* **Currently avoided** — only one is live (self-custody dApp). Risk re-emerges when assisted flows ship.
- *Centralized policy and monitoring overhead bites.* **Deferred** — overhead is not yet incurred because assisted flows are unbuilt.

**Lessons:** none new.

**Follow-ups:**

- ADR-0007 (assisted transaction gateway) is the natural follow-on; its AAR (below) shows it is not yet implemented.
- When assisted flows ship, this AAR's "currently avoided" rows must be revisited.

**Revision schedule:** when ADR-0007 implementation begins, or no later than the mainnet readiness gate.
