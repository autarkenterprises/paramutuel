# Assisted UX and Gas Abstraction Roadmap

Date: 2026-03-30  
Status: Draft v1 (post-ADR-0006/0007)

This roadmap operationalizes:

- `research/adr/ADR-0006-surface-separation-self-custody-vs-assisted-ux.md`
- `research/adr/ADR-0007-assisted-transaction-gateway-and-token-paths.md`

## Scope boundary

- **In scope:** website/service-layer assistance (sponsorship, approval path detection, policy rails, observability).
- **Out of scope:** changes to core contracts under `src/` and mandatory dependency injection into `/dapp`.

---

## Phase 0 — Interface and policy design freeze

**Goal:** lock stable interfaces before implementation.

**Deliverables**

- Assisted Transaction Gateway (ATG) API draft:
  - `quoteIntent`
  - `submitIntent`
  - `intentStatus`
- Canonical intent schema:
  - chain id, market address, method, args hash, token, amount, signer, expiry, nonce
- Sponsorship policy spec:
  - per-user/day cap
  - per-token cap
  - blocked token list
  - emergency kill switch
- Token tier list:
  - Tier 1 happy path: USDC + selected stablecoins
  - Tier 2 best-effort: generic ERC-20

**Exit criteria**

- API and policy docs reviewed by protocol, dApp, and service owners.

---

## Phase 1 — Token path classifier + simulation engine

**Goal:** deterministically select execution path per token and action.

**Deliverables**

- Classifier module:
  - detect EIP-2612 support
  - detect Permit2 eligibility
  - fallback to standard `approve`
- Preflight simulation:
  - dry-run permit/approve + target method (`placeBet`/`placeBets`)
  - estimate sponsored gas cost and reject unsafe transactions
- Error taxonomy for UI:
  - user-correctable vs platform-internal vs policy rejection

**Exit criteria**

- Integration tests pass against:
  - USDC
  - at least one EIP-2612 token
  - at least one fallback-only token

---

## Phase 2 — Sponsored execution backend (adapter v1)

**Goal:** deliver first production-capable sponsored pipeline behind ATG.

**Deliverables**

- Adapter v1:
  - relayer submission
  - signer management
  - replay protection and nonce discipline
- Settlement accounting:
  - sponsorship spend by token/user/market
  - fee recovery model hooks
- Security controls:
  - per-IP and per-wallet rate limits
  - structured audit logs
  - circuit breaker thresholds

**Exit criteria**

- Soak test on Base Sepolia with burst traffic and no replay/race defects.

---

## Phase 3 — Website integration (happy-path first)

**Goal:** expose assisted betting UX to non-power users.

**Deliverables**

- Website flow:
  - wallet connect
  - choose market
  - collateral selector with Tier 1 defaults
  - "platform-sponsored" transaction path messaging
- UX rails:
  - explicit fee disclosure (if any)
  - fallback messaging when sponsorship unavailable
  - link to advanced dApp for unrestricted/manual mode
- Recovery UX:
  - failed intent retry
  - fallback to self-funded transaction when needed

**Exit criteria**

- User test cohort completes bet flow with no manual allowance troubleshooting in Tier 1 tokens.

---

## Phase 4 — General-purpose expansion

**Goal:** broaden token compatibility while preserving reliability.

**Deliverables**

- Tier 2 rollout:
  - controlled allowlist growth
  - per-token reliability scores
- Execution backend abstraction:
  - optional account-abstraction/paymaster adapter behind ATG
- Operational maturity:
  - alerting dashboards
  - automated anomaly detection on sponsorship spend

**Exit criteria**

- 30-day production window with stable error budget and controlled sponsorship economics.

---

## Phase 5 — Governance and long-term hardening

**Goal:** make assisted UX policy maintainable as protocol usage scales.

**Deliverables**

- Governance process for:
  - token tier changes
  - sponsorship caps
  - fee model updates
- Incident runbooks:
  - relayer outage
  - permit path degradation
  - token behavior drift
- Periodic dependency review:
  - external infra risk scorecards
  - migration plans between adapters/providers

**Exit criteria**

- Quarterly policy review cadence established with documented change log.

---

## Success metrics (cross-phase)

- Sponsored bet completion rate (Tier 1 tokens)
- Median time-to-confirmation
- Sponsorship cost per successful bet
- Failure rates by approval path (EIP-2612 / Permit2 / approve fallback)
- Escalation rate from website assisted mode to dApp advanced mode
