# ADR-0008: Multi-winner resolution and generalized settlement semantics

Date: 2026-03-31  
Status: Proposed (reference); **contracts** merged to **`master`** (developed on `experiment/adr-0008-multi-winner-v2`) — see [`docs/ADR-0008-IMPLEMENTATION.md`](../../docs/ADR-0008-IMPLEMENTATION.md). Product semantics (**`ANY_OF`** vs **`EXACT_SET`** vs **`T ⊆ W`**) — [`docs/PAYOUT-CALCULATION.md`](../../docs/PAYOUT-CALCULATION.md) Part B glossary.

## Context

Current protocol semantics model a wager as a single winning outcome index selected by the resolver (`resolve(uint256 outcomeIndex)`), with payouts computed from stake in that one winning bucket.

This is insufficient for propositions where multiple options can be simultaneously true (example: "Which tickers are positive tomorrow?" across 10 symbols), and where users may want payout rules such as:

- **Any-of semantics:** bet is winning if any selected option is in the winning set.
- **Exact-set semantics:** bet is winning only if the selected set exactly matches the final winning set (`T == W`). (Distinct from **subset-of-truth** semantics `T ⊆ W` — “every picked option is a winner” — which v2 does **not** implement; future ADR if product requires it.)
- **Threshold semantics:** bet is winning if at least `k` selected options are in the winning set.
- **Weighted/scored semantics:** payout scales by overlap or score rather than binary win/loss.

Without generalized support, users must encode subsets as explicit outcomes, causing combinatorial explosion (`2^N` outcomes for full-set predicates).

## Decision

Adopt a staged architecture that introduces **generalized payoff policies** while preserving immutable-core posture for existing v1 contracts:

1. **Keep v1 contracts and deployed wagers unchanged.**  
   Existing single-winner wagers remain valid and operational.

2. **Introduce generalized settlement via a new protocol version (v2) and policy-driven payoff model.**  
   Do not retrofit storage/function signatures on deployed contracts.

3. **Represent final truth as a winner bitset (or equivalent compact set encoding) over base options.**  
   Resolver submits a set, not a single index.

4. **Bind each wager at creation to a `payoffPolicy` and parameters.**  
   The policy defines how a bet ticket is evaluated against the resolved winner set.

5. **Treat bet entries as selections (subset tickets) rather than scalar outcome index only.**  
   Settlement computes claim entitlement under the selected policy.

6. **Scope v2 policy set to a safe baseline first:**  
   - `SINGLE_WINNER` (back-compat behavior)  
   - `ANY_OF`  
   - `EXACT_SET`  
   Future policies (`AT_LEAST_K`, weighted overlap, score-based) require explicit follow-up ADRs.

## Full generality: required modifications

### Contract layer

- Add v2 wager contract/factory interfaces:
  - create with `baseOptions[]`, `payoffPolicy`, `policyParams`.
  - resolve with `winningSet` representation (bitset/bytes).
- Add bet placement methods for set selection:
  - compact selection encoding (bitset) and strict validation.
- Replace single winning bucket accounting with policy settlement accounting:
  - deterministic formula for winning ticket set and payout shares.
- Add explicit bounds to control gas and state growth:
  - max options, max selected options per ticket, max policy param size.
- Add policy-specific invariants and custom errors.

### Indexer/API layer

- Extend schema beyond single `winning_outcome`:
  - `winning_set_encoding`, `payoff_policy`, `policy_params_json`.
- Derive and expose policy-aware settlement previews and claimability state.
- Add deterministic replay tests for new resolution events and policy state.

### dApp and explorer UX

- Replace single "winning outcome index" resolver input with winner-set editor.
- Add wager creation controls for payoff policy + policy params.
- Add bettor ticket builder for subset selections.
- Add policy-specific odds and payout preview language:
  - user must see what constitutes a winning ticket under chosen policy.

### Service/control/MCP

- Update action encoders and operator tools:
  - policy-aware create and resolve payloads.
- Extend MCP tool contracts:
  - policy metadata, winner-set resolution encoding helpers.

### Security/economic analysis

- New attack surfaces:
  - policy complexity abuse, pathological ticket distributions, griefing via large set operations.
- Require policy-level gas profiling, claim-loop constraints, and formal invariant checks.

## Consequences

### Positive

- Eliminates combinatorial-outcome explosion for multi-true propositions.
- Enables broader classes of real-world wagers with explicit semantics.
- Keeps v1 deployment stable while enabling evolution via versioned contracts.

### Negative

- Substantially more complex settlement and UX.
- Larger testing and audit surface.
- Potentially higher gas for create/bet/resolve/claim paths depending on encoding and policy.

## Rejected alternatives

- **Encode every subset as an explicit outcome in v1:** rejected due to exponential growth and unusable UX.
- **Patch deployed v1 contracts in place:** rejected; conflicts with immutable-core posture and existing deployments.
- **Allow resolver to submit multiple winners but still use single-bucket payout logic:** rejected; semantically ambiguous and economically unsafe.

## Integration history (v2)

**v2 contracts, Foundry tests, gas reports, indexer / dApp / explorer / MCP** landed on `master` via branch **`experiment/adr-0008-multi-winner-v2`**. Further v2-only experiments may continue on that branch name; **`master`** is the default integration line.

Implementation notes and policy tables: [`docs/ADR-0008-IMPLEMENTATION.md`](../../docs/ADR-0008-IMPLEMENTATION.md). **“Any of” / “all of”** copy ↔ policies: [`docs/PAYOUT-CALCULATION.md`](../../docs/PAYOUT-CALCULATION.md) Part B glossary.

## Rollout plan

1. Spec phase: canonical policy math, encoding format, and validation rules.
2. Prototype phase: v2 contracts + reference settlement tests (on the integration branch above).
3. Tooling phase: dApp/indexer/service/MCP compatibility.
4. Testnet certification: multi-policy scenario matrix.
5. Audit and controlled launch for v2 factory/wagers.

## Acceptance criteria for implementation start

- Policy math spec with executable test vectors is approved.
- Gas bounds and option-count limits are defined.
- Indexer and API schema migration plan is agreed.
- UX copy for policy semantics is validated for user comprehension.
