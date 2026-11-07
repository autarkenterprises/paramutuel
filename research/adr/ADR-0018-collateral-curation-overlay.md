# ADR-0018: Collateral curation as an opt-in overlay (no core change)

Date: 2026-06-19
Status: **Proposed** (design ADR; implementation gated on operator input).
Builds on: [ADR-0001](ADR-0001-core-immutability-and-delegated-resolution.md) (immutable, collateral-agnostic core), [ADR-0006](ADR-0006-surface-separation-self-custody-vs-assisted-ux.md) (token-policy decision: protocol collateral-agnostic, site curates happy paths), [ADR-0016](ADR-0016-assisted-ux-funds-management.md) (Tier-1 / Tier-2 collateral split), [ADR-0017](ADR-0017-service-provider-concept.md) (service-provider catalog + manifest), [`AGENTS.md`](../../AGENTS.md) practices **#1**, **#2**, **#4**.

## Context

A 2026-06-19 codebase review re-examined the protocol's "any ERC-20 collateral" claim against the frozen-bytecode standard the Resonance Exchange ARG now imposes: the testnet deployment is production-grade and the only delta to mainnet is the chain it is minted on, so whatever bytecode ships for the ARG is the bytecode frozen for mainnet. There is no post-mint patch path.

`ParamutuelWagerV3` makes exactly two trust-neutral guarantees: it is **non-custodial** (funds move only by parimutuel math) and **solvent for standard ERC-20 collateral** (`Σ payouts ≤ totalPot`, floors leave dust). It does *not* guarantee that an arbitrary token is well-behaved. Two failure shapes exist:

- **No-bool-return tokens (USDT-class).** `bool ok = collateralToken.transferFrom(...)` against the `returns (bool)` interface reverts on empty return data. This **fails safe** — the bet cannot be placed, nothing is lost.
- **Fee-on-transfer / rebasing tokens.** The transfer *succeeds* but the wager credits the requested amount to `totalPot` while custody receives less (or later shrinks). This **fails unsafe** — the pot's solvency invariant is broken and late claimants cannot be paid.

This is not a new problem and the policy answer already exists. **ADR-0006 Decision §4** ratified "protocol remains collateral-agnostic; website curates happy-path tokens (USDC and major stablecoins) while retaining a universal fallback." Its AAR (2026-05-06) records that the curation "exists in copy but not yet in flow code." **ADR-0016** named a Tier-1 / Tier-2 split, also unbuilt. The decision this ADR records is therefore an *implementation* of an accepted policy, framed by the project's standing principle:

> **Neutral core, safety as opt-in overlay.** The core is small, frozen, and neutral; safety is layered, mutable, and chosen. Outcome correctness is supplied by the resolution overlay (Foundation Resolution Service today, UMA-style oracle later, or any resolver a proposer trusts); collateral soundness is supplied by the curation overlay specified here; fee/economic legibility is supplied by the disclosure overlay. The contract changes for none of them, because none of them were ever the contract's job.

The honest boundary: an overlay protects participants who *use the overlay*. A party who bypasses the curated surfaces and bets directly on a fee-on-transfer wager can still be harmed — exactly as a party who bets on a wager with a malicious resolver can be harmed. The protocol's answer is identical in both cases, and that symmetry is the justification for keeping the core neutral.

## Decision

1. **No change to `src/`.** The V3 contracts remain collateral-agnostic. The core's documented solvency guarantee is scoped explicitly to standard ERC-20 collateral; fee-on-transfer and rebasing tokens are declared out of the core's guaranteed scope rather than defended against in frozen bytecode.
2. **Introduce a collateral-curation overlay** as off-chain configuration: a single `config/collateral-allowlist.json`, network-keyed to mirror `config/deployments.json`. Each token entry carries `address`, `symbol`, `decimals`, `tier` (1 = assisted-eligible per ADR-0016, 2 = unassisted-but-curated), and `class` (`standard` | `fee-on-transfer` | `rebasing` | `unknown`). The config is the single source of truth; services may cache it but must not contradict it.
3. **Wire the overlay into the curated surfaces.** The dApp create flow offers allowlisted tokens by default; an unlisted collateral address remains reachable (ADR-0006's universal fallback) only behind an explicit, warned, opt-in control. The bet surfaces (`site/bet.html`, `site/resonance-bet.html`, dApp bet flow) render a collateral-trust badge derived from the allowlist, alongside the existing fee-bps display.
4. **Pin the core's boundary with regression tests** (per L-003 and AGENTS.md #1/#2): a no-bool-return mock token whose `placeBet` reverts (fail-safe), and a fee-on-transfer mock token with a test that asserts and documents the solvency-break boundary (fail-unsafe). Both run in the fast suite so the limit is a named, executable fact rather than tribal knowledge.
5. **Narrow the public claim.** README and surface copy change "any ERC-20" to "any standard ERC-20 (no fee-on-transfer or rebasing tokens); curated collateral is recommended." The unqualified claim is the only place the marketing currently outruns the frozen contract.
6. **Make the overlay agent-discoverable.** The `agents/service-provider-manifest.json` from ADR-0017 references the allowlist URL so automated participants consume the same curation a human sees.

## Decision points

- **Single network-keyed file** (`config/collateral-allowlist.json`) rather than per-network files — mirrors `config/deployments.json` so the existing JS config loaders extend rather than fork.
- **Tier semantics inherit from ADR-0016**: Tier-1 = assisted-tx-eligible (deep DEX liquidity), Tier-2 = curated but unassisted. `class` is orthogonal and exists so a Tier-2 *standard* token (curated, no gas sponsorship) is distinguishable from an *uncurated* one.
- **Permissionlessness is preserved by construction**: the overlay defaults to curated tokens but never removes the path to an arbitrary ERC-20; the escape hatch is a warned opt-in, not a removal. This is the line that keeps "perfectly permissionless" true at the protocol layer.
- **Config is truth; indexer is cache.** Any collateral-trust labeling the indexer/explorer emits is derived from the committed allowlist, never independently asserted.

## Success criteria

- `config/collateral-allowlist.json` exists, is network-keyed, and its schema is documented in `service/README.md` or a dedicated note.
- dApp create defaults to the allowlist; selecting an unlisted collateral requires an explicit opt-in and shows a warning.
- The bet surfaces show a collateral-trust badge sourced from the allowlist.
- Two forge tests (no-bool revert; fee-on-transfer solvency-break) exist, pass, and run in `script/test-fast.sh`.
- No repository surface claims unqualified "any ERC-20"; the qualified claim appears in `README.md` and the bet/create copy.
- `agents/service-provider-manifest.json` references the allowlist.

## Failure criteria

- **Allowlist drifts from on-chain reality** (wrong token address for a network). Mitigation: a schema/checksum test, and ideally a CI check that resolves each address's `symbol()`/`decimals()` against the network RPC before merge.
- **The overlay hardens into a gate** — users can no longer reach the universal fallback. This silently regresses permissionlessness; mitigation: the warned opt-in path is itself covered by a test and called out in the dApp README.
- **Curation theater** — the badge is shown but ignored, and a bettor stakes into a fee-on-transfer wager anyway. Partly outside our control; disclosure is necessary, not sufficient. Recorded here so the AAR can revisit whether on-chain enforcement (the deferred registry overlay) becomes warranted.

## Rejected alternatives

- **`SafeERC20` in the core.** Would make USDT-class tokens usable, but mutates frozen bytecode to solve a problem ADR-0006 already assigned to the overlay; the no-bool case fails safe, so the only loss is USDT compatibility, which the curation overlay routes around by recommending USDC.
- **Balance-delta accounting to genuinely support fee-on-transfer.** Enlarges the immutable surface and forces messy per-bettor attribution of the token skim across a shared parimutuel pot; not worth it for v1.
- **A hard collateral allowlist inside `ParamutuelFactoryV3`.** On-chain gatekeeping in the core directly contradicts "perfectly permissionless." Deferred to an *optional* future overlay — a standalone collateral registry plus a curated-factory wrapper that calls the existing factory — which enforces on-chain for those who opt in without ever modifying the neutral core. Out of v1 scope, named here so it is not re-litigated.

## After Action Report

**AAR date:** Pending
**AAR status:** Pending

**Outcome vs success criteria:**

- <criterion>: <Met | Partially met | Not met> — <evidence>

**Outcome vs failure criteria:**

- <criterion>: <Avoided | Triggered | Mitigated> — <evidence>

**Lessons:** Pending.

**Follow-ups:** Optional on-chain collateral registry + curated-factory wrapper (deferred from Rejected alternatives) if curation theater proves material; revisit at the mainnet readiness gate.

**Revision schedule:** at the mainnet readiness gate, or after the first ARG campaign observes real collateral diversity beyond the curated set.
