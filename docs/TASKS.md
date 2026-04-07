# Task list (miscellaneous / backlog)

Cross-cutting items that are not tied to a single PR. Update this file when scope or decisions change.

---

## Protocol: fee totals (treasury + beneficiaries)

**Status:** Already enforced in the MVP contracts.

- **Factory** (`createWager` in `src/ParamutuelFactory.sol`): builds fee recipients from `protocolFeeBps` (treasury) plus `extraFeeRecipients` / `extraFeeBps`. Reverts with `BadFeeConfig()` if `totalFeeBps > MAX_TOTAL_FEE_BPS`, where `MAX_TOTAL_FEE_BPS` is **10_000** (**100%** of the pot, enabling full-beneficiary/charity wagers).
- **Wager** (constructor in `src/ParamutuelWager.sol`): reverts with `FeeTooHigh()` if the **sum of all `feeBps` exceeds `BPS_DENOMINATOR` (10_000)**, i.e. fee shares cannot exceed **100%** in basis points.

Wagers created through the factory therefore see at most the factory cap (100% today); the wager check is the invariant that no fee vector can imply more than 100% taken from the pot.

**Follow-ups (optional):**

- [x] Factory and wager fee reverts are covered in `test/Paramutuel.t.sol` (e.g. total above `MAX_TOTAL_FEE_BPS`, and `FeeTooHigh` on direct wager deploy).
- [x] Factory cap raised to 100% (`MAX_TOTAL_FEE_BPS=10_000`) to support charity-beneficiary wagers while preserving wager-level `<= 100%` invariants.

---

## Product: browser extension ("bet you on the web")

**Goal:** While browsing (e.g. Twitter/X), a user can say "I bet you that will not happen", **create a parimutuel wager** from page context (proposition, outcomes), and **share a link** so a counterparty can open or bet without hunting addresses manually.

**Likely scope:**

- [ ] Extension shell (MV3): Chrome/Firefox; prefer WalletConnect / injected wallet over storing raw keys in the extension.
- [ ] Context capture: tweet or selection to prefill `proposition` / `outcomes` (always editable before submit).
- [ ] Chain and factory registry aligned with the dApp (Base Sepolia / Base); clear network-mismatch UI.
- [ ] Deep links: stable URLs (hosted dApp or similar) with `chainId`, `factory`, and wager address after creation.
- [ ] Create flow using existing `createWager` ABI; reuse templates aligned with `dapp/logic.js` where possible.
- [ ] Share UX: copy link, optional "open in dApp" for users without the extension.
- [ ] Safety: show factory/wager addresses prominently; warn on unknown factories (phishing resistance).

**Dependencies:** Stable deployed addresses, `docs/MACHINE.md` / ABI stability, and a bookmarkable dApp for counterparties.

**Roadmap:** Post-MVP product track parallel to resolver R&D; no protocol change required for v1 if the extension is a thin client over `ParamutuelFactory` / `ParamutuelWager`.

---

## Maintenance

- [x] Link this file from `README.md` and `research/execution-roadmap.md` (keep discoverable).

---

## Release engineering (PyPI bet scout)

**Status:** Git tag `bettor-agent-v0.2.0` is pushed; workflows **Publish bet scout agent (PyPI)** and **(GHCR)** run on `bettor-agent-v*` tags.

**If PyPI upload fails in Actions:**

- [ ] In [pypi.org](https://pypi.org) create project **`paramutuel-bettor-agent`** (if it does not exist).
- [ ] Project → **Publishing** → **Add a new pending publisher** → GitHub → select this repo and workflow **Publish bet scout agent (PyPI)**.
- [ ] Re-run the failed workflow or push a new tag after fixing version alignment (`__version__` must match tag suffix).

**Optional:** Add a GitHub **Environment** named `pypi` with required reviewers and add `environment: { name: pypi }` to the publish job for manual approval gates.

**GHCR:** Ensure GitHub Actions is allowed to publish packages for the org/user; image is `ghcr.io/<lowercase-owner>/paramutuel-bettor-agent:<semver>`.

---

## Return later: Resolution Service

**Note:** Revisit Resolution Service follow-ups (auth hardening, automation/scheduling, integration tests, and operator runbooks) documented in `docs/RESOLUTION-SERVICE.md`.

---

## Website-assisted UX (post-ADR-0006/0007)

**Goal:** Ship a centralized assisted transaction path for non-power users without changing protocol contracts or regressing the advanced dApp.

- [ ] Define Assisted Transaction Gateway API contract (`quoteIntent`, `submitIntent`, `intentStatus`) and intent schema.
- [ ] Implement token capability classifier (EIP-2612 -> Permit2 -> approve fallback).
- [ ] Add preflight simulation and policy rejections (rate limits, spend caps, blocked token list).
- [ ] Build Tier 1 happy-path website flow for USDC + selected stablecoins.
- [ ] Add observability dashboards for sponsorship cost, failures by token/path, and abuse indicators.
- [ ] Document user-facing fallback from assisted website path to advanced dApp self-custody flow.

---

## Protocol v2: multi-winner resolution and generalized payout semantics (ADR-0008)

**Goal:** Enable wagers where multiple options can be true simultaneously, without requiring subset enumeration as explicit outcomes.

**Canonical integration branch:** `experiment/adr-0008-multi-winner-v2` — all v2 contract work, Foundry tests, gas docs, and follow-on indexer/dApp/MCP land here first; merge to `master` only after coordinated certification. Contents: `ParamutuelFactoryV2` + `ParamutuelWagerV2`, tests, [`docs/ADR-0008-IMPLEMENTATION.md`](ADR-0008-IMPLEMENTATION.md).

- [x] Specify canonical payoff policies and formulas (`SINGLE_WINNER`, `ANY_OF`, `EXACT_SET`, `AT_LEAST_K`, `WEIGHTED_OVERLAP`) — see implementation doc.
- [x] Define compact winner-set and ticket-selection encoding (`uint256` bitset, `MAX_DISTINCT_TICKETS`, factory `MAX_OUTCOMES = 64`).
- [x] Draft v2 factory/wager contracts for policy-bound creation and `resolve(winningMask)`.
- [x] Claim accounting + Foundry tests (including fuzz conservation on `ANY_OF`, extensive lifecycle/policy matrix, gas profiling harness — see `docs/ADR-0008-GAS.md`, `test/ParamutuelV2Extensive.t.sol`).
- [ ] Add indexer schema/API changes for `winning_mask`, policy metadata, and ticket masks on bets.
- [ ] Update dApp/explorer UX for policy + bitmask tickets + resolver set UI.
- [ ] Extend service/control/MCP for v2 create/resolve encodings.
- [ ] Gas/safety audit pass and formal limits sign-off before mainnet v2 factory.
