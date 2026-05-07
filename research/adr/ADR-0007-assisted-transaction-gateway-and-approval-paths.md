# ADR-0007: Assisted transaction gateway with pluggable approval paths

## Status

Accepted

## Date

2026-03-30

## Context

Website users need reduced friction (ideally no ETH requirement) while interacting with unchanged Paramutuel contracts.

Gas abstraction introduces multiple moving parts:

- user operation execution (relayer/bundler/paymaster stack)
- allowance setup for wager contracts
- fee recovery and abuse controls

Asset behavior varies:

- Some assets implement EIP-2612 permit.
- Others can be handled via Permit2.
- Others require regular `approve`.

The system needs a generalized flow that works across many ERC-20 assets, plus safer, operationally stable "happy path" defaults for website users.

## Decision

1. **Adopt an upper-layer Assisted Transaction Gateway (ATG)**:
   - Website sends signed intents to an off-chain gateway service.
   - Gateway chooses execution strategy and submits on-chain transactions.
   - Core protocol contracts remain untouched.

2. **Use pluggable approval paths** in this priority order:
   - **Path A:** Native EIP-2612 permit + sponsored execution.
   - **Path B:** Permit2 signature path + sponsored execution.
   - **Path C:** Sponsored `approve` then sponsored action (two-step fallback).

3. **Execution adapters are replaceable**:
   - Initial adapter may use a relayer with policy controls.
   - Account-abstraction/paymaster adapter can be added later behind the same ATG interface.
   - Website and policy logic call ATG, not a specific execution backend.

4. **Dual collateral support tiers**:
   - **Tier 1 (happy path):** USDC + selected stablecoins with mature liquidity/tooling.
   - **Tier 2 (general):** Any ERC-20 collateral with best-effort path detection and explicit UX warnings.

5. **Safety and economics controls are mandatory**:
   - per-user and per-asset sponsorship limits
   - nonce/replay protections
   - max fee/slippage policy for sponsored actions
   - audit logs and cost attribution per wager/user/collateral

## Consequences

### Positive

- Future-proofs gas abstraction by decoupling website UX from a single infra vendor or standard.
- Supports broad ERC-20 compatibility through layered fallbacks.
- Preserves protocol purity and dApp independence.

### Tradeoffs

- Requires backend ops, monitoring, and anti-abuse systems.
- Permit2/relayer integrations add third-party operational dependencies.
- Website UX must communicate sponsorship limits and fallback behavior clearly.

## After Action Report

**AAR date:** 2026-05-06
**AAR status:** Backfilled 2026-05-06 per ADR-0012

**Outcome vs success criteria** (criteria implicit in Decision):

- *Assisted Transaction Gateway service.* **Not met (not started)** — no `service/atg/` or equivalent exists. `research/assisted-ux-roadmap.md` (Phase 0 design freeze) is the only artifact, and it remains in draft.
- *Pluggable approval paths (permit / Permit2 / approve+act).* **Not met** — no implementation.
- *Replaceable execution adapters.* **Not met** — no implementation.
- *Tier-1 / Tier-2 token policy.* **Not met as runtime behavior**, partially captured in `site/` copy.
- *Safety / economics controls.* **Not met** — no sponsorship limits, replay protection, or audit logs because no gateway exists.

**Outcome vs failure criteria:**

- *Backend ops / monitoring overhead.* **Avoided by deferral** — the cost has not been incurred because the feature was deprioritized.
- *Vendor lock-in via single relayer or AA stack.* **Avoided by deferral** — no integration committed yet.

**Lessons:** none new; the lesson here is meta — *deferring an "Accepted" ADR's implementation is acceptable, but the AAR must record that explicitly so the deferral is visible*. ADR-0012's discipline catches this.

**Follow-ups:**

- Decide whether ADR-0007 is **deferred** (current de-facto state) or **rejected**. Update `Status:` accordingly. If kept as `Accepted`, schedule resourcing.
- If implementation starts, refresh the assisted-ux roadmap document (currently dated 2026-03-30 and unfinished).
- The unimplemented status is a known gap in `docs/PROJECT-REVIEW.md` ("Assisted UX") — keep that pointer accurate.

**Revision schedule:** at the next product roadmap review, or at mainnet readiness gate.

### AAR revision — 2026-05-07 (testnet-as-production posture)

**AAR status:** Revisited 2026-05-07; effectively superseded by ADR-0016 for the unfunded-funds question

The original AAR called the assisted-UX gateway "deferred / not implemented." Under the Resonance Exchange ARG posture, deferral is *more* costly than the original AAR implied, not less:

- Microwonks bet via the bet-scout subagent and their own wallets; the gateway is **not** on their critical path.
- However, **human onlookers** observing the ARG who click through to `site/resonance-bet.html` and lack ETH for gas drop out of the user-visible flow. For a campaign optimised for retail observation, that is a UX failure on the live launch surface.
- The original ADR-0007 left the *funds-management* question (how the relayer sponsors gas without exhausting its ETH float, especially when settling arbitrary ERC-20 collateral) as one of several open items. That question is the load-bearing one for an actual deployment and warrants its own ADR.

**Revised follow-ups:**

- ADR-0007 remains **Accepted** as the architectural shape (split surfaces; assisted UX as upper-layer) but its *implementation* is moved into **ADR-0016** (`research/adr/ADR-0016-assisted-ux-funds-management.md`), which addresses the funds-management question explicitly.
- ADR-0007's "Status" header is unchanged (Accepted) — ADR-0016 builds on it rather than superseding it.

**Revised revision schedule:** at ADR-0016's first implementation cycle.
