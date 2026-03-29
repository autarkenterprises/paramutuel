# Task list (miscellaneous / backlog)

Cross-cutting items that are not tied to a single PR. Update this file when scope or decisions change.

---

## Protocol: fee totals (treasury + beneficiaries)

**Status:** Already enforced in the MVP contracts.

- **Factory** (`createMarket` in `src/ParamutuelFactory.sol`): builds fee recipients from `protocolFeeBps` (treasury) plus `extraFeeRecipients` / `extraFeeBps`. Reverts with `BadFeeConfig()` if `totalFeeBps > MAX_TOTAL_FEE_BPS`, where `MAX_TOTAL_FEE_BPS` is **1_000** (**10%** of the pot for MVP).
- **Market** (constructor in `src/ParamutuelMarket.sol`): reverts with `FeeTooHigh()` if the **sum of all `feeBps` exceeds `BPS_DENOMINATOR` (10_000)**, i.e. fee shares cannot exceed **100%** in basis points.

Markets created through the factory therefore see at most the factory cap (10% today); the market check is the invariant that no fee vector can imply more than 100% taken from the pot.

**Follow-ups (optional):**

- [x] Factory and market fee reverts are covered in `test/Paramutuel.t.sol` (e.g. total above `MAX_TOTAL_FEE_BPS`, and `FeeTooHigh` on direct market deploy).
- [ ] If governance raises the MVP cap later, keep the market `<= 100%` invariant; change factory constants only via audited deploy/upgrade.

---

## Product: browser extension ("bet you on the web")

**Goal:** While browsing (e.g. Twitter/X), a user can say "I bet you that will not happen", **create a Paramutuel market** from page context (question, outcomes), and **share a link** so a counterparty can open or bet without hunting addresses manually.

**Likely scope:**

- [ ] Extension shell (MV3): Chrome/Firefox; prefer WalletConnect / injected wallet over storing raw keys in the extension.
- [ ] Context capture: tweet or selection to prefill `question` / `outcomes` (always editable before submit).
- [ ] Chain and factory registry aligned with the dApp (Base Sepolia / Base); clear network-mismatch UI.
- [ ] Deep links: stable URLs (hosted dApp or similar) with `chainId`, `factory`, and `market` after creation.
- [ ] Create flow using existing `createMarket` ABI; reuse templates aligned with `dapp/logic.js` where possible.
- [ ] Share UX: copy link, optional "open in dApp" for users without the extension.
- [ ] Safety: show factory/market addresses prominently; warn on unknown factories (phishing resistance).

**Dependencies:** Stable deployed addresses, `docs/MACHINE.md` / ABI stability, and a bookmarkable dApp for counterparties.

**Roadmap:** Post-MVP product track parallel to resolver R&D; no protocol change required for v1 if the extension is a thin client over `ParamutuelFactory` / `ParamutuelMarket`.

---

## Maintenance

- [x] Link this file from `README.md` and `research/execution-roadmap.md` (keep discoverable).
