# ADR-0009: Freeform text-answer wagers (exact-match, single-winner parimutuel)

Date: 2026-04-04  
Status: Accepted — implemented (see [`docs/ADR-0009-IMPLEMENTATION.md`](../../docs/ADR-0009-IMPLEMENTATION.md))

Implementation notes (spec + v2 outcome-cap appendix): [`docs/ADR-0009-IMPLEMENTATION.md`](../../docs/ADR-0009-IMPLEMENTATION.md)

## Context

ADR-0008 generalizes settlement over a **fixed, enumerated** set of base options using compact encodings (bitmasks) and a resolver-submitted **winning set** (`winningMask`). The factory caps the number of base options at **`MAX_OUTCOMES = 255`** (fits one `uint256` bitfield; see `WagerV2Masks`), and every outcome must be known at **wager creation**.

Some propositions do not admit a reasonable fixed enumeration—for example, markets where the natural resolution is a **specific text answer** (name, ticker symbol, short phrase, or a canonical encoding of a scalar) chosen only at resolution time. Forcing these into buckets duplicates the “interval approximation” problem; allowing **open-ended answers** at bet time avoids combinatorial pre-registration.

Product ask: a **freeform** wager type where:

- The proposer **does not** supply an outcome list at creation.
- Each bettor submits a **text answer** (payload) with their stake.
- The resolver submits the **single winning text**.
- A bet wins **iff** the bettor’s answer matches the resolver’s string **exactly** (same rule for all bettors).
- Payoff economics mirror **single winning outcome** parimutuel: one winning pool; all other stake is losing; winners split the net pool after protocol rules.

This ADR records the decision to support that shape **as a distinct protocol surface**, not as a reinterpretation of bitmask v2.

## Decision

1. **Introduce a separate wager implementation (or clearly isolated module)** from `ParamutuelWagerV2`.  
   Freeform tickets are **not** bit indices; mapping them into `numOptions` / `winningMask` would be artificial and would not remove the need for string storage or hashing.

2. **Identify each distinct bettor answer by a fixed deterministic id**  
   Primary recommendation: `answerId = keccak256(bytes(answer))` for `string` answers (UTF-8 bytes only; no length prefix).  
   If future protocol surfaces must avoid cross-feature preimage collisions, use an explicit domain-separated variant (e.g. `keccak256(abi.encode(FREE_FORM_ANSWER_TYPEHASH, bytes(answer)))`) and document it as the **only** canonical id function for that deployment.  
   On-chain equality is **by identity of `answerId`**, not by scanning all prior strings.

3. **Accounting mirrors “distinct ticket” pools**  
   - `pool[answerId] += amount` on bet.  
   - Maintain `answerId[] usedAnswerIds` appended **once** the first time a given `answerId` receives stake (same pattern as v2 `_usedMasks`).  
   - Per-user bookkeeping: which `answerId`s (and amounts) the user holds, analogous to v2 `bets[user][mask]` / `_userMasks`.

4. **Resolution**  
   - Resolver calls `resolve(string calldata winningAnswer)` (or `bytes` if we prefer opaque payloads).  
   - `winningId = hash(winningAnswer)` using the **same** function as betting.  
   - Settlement uses **single-winner** semantics: only `pool[winningId]` is winning; distribute that pool’s entitlement under the same fee / treasury rules as v1 single-outcome resolution.  
   - **No** multi-winner sets, **no** payoff policies from ADR-0008 for this type unless a later ADR explicitly extends freeform.

5. **Exact match definition**  
   “Exact” means **identical ABI-encoded string bytes** as passed in `placeBet` vs `resolve`. The protocol does **not** perform Unicode normalization, case folding, trimming, or locale-sensitive comparison. Any such rules are **off-chain conventions** the resolver and UI must follow; mismatches due to spelling, invisible characters, or encoding are **user / resolver responsibility**.

6. **Bounds and gas safety**  
   - **Max answer length** (bytes): enforced in `placeBet` and `resolve` to cap calldata cost and storage churn.  
   - **Optional max distinct answers** (length of `usedAnswerIds`): cap worst-case `resolve` / `claim` iteration; if exceeded, creation or new distinct answers revert.  
   - Document that **resolve gas scales with the number of distinct answers that received stake**, not with string length alone.

7. **Edge case: no stake on the winning answer**  
   Choose one explicit behavior and encode it in the contract (and indexer):

   - **Recommended default:** treat as **invalid resolution** and `revert` (resolver must not finalize an answer nobody backed), **or**  
   - **Alternative:** refund all bettors pro-rata from gross pool after fees (more complex; requires spec of fee handling when there is no “winning side”).

   The ADR does not mandate which option; implementation must pick one and test it.

8. **Factory**  
   Add `ParamutuelFactoryFreeform` (name TBD) or a versioned factory method that deploys the freeform wager with the same **collateral, roles, windows, fees** patterns as existing factories. **Do not** require `string[] outcomes` in the create path.

9. **Immutability posture**  
   Same as ADR-0008: **do not mutate** deployed v1/v2 contracts. New bytecode only.

## Contract layer (implementation checklist)

- Constructor / create: proposition metadata, ERC20 collateral, resolver / closers, fee recipients, windows; **no outcome array**.  
- `placeBet(string calldata answer, uint256 amount)` (or overload with `bytes`).  
- `resolve(string calldata winningAnswer)` restricted to resolver; idempotent or single-shot per existing patterns.  
- `claim` (or batch) consistent with single-winner payout math.  
- Lifecycle: `closeBetting`, `closeResolutionWindow`, `expire`, `retract` as applicable—align with v1/v2 semantics unless there is a documented reason to differ.  
- Events: emit **hashes** for indexing; optionally emit full string in calldata for off-chain indexers (gas tradeoff) or emit hash-only and rely on calldata archival.  
- Errors: empty answer, length exceed, duplicate-resolution, no-stake-on-winner (if revert path), unauthorized resolver.

## Indexer / API / tooling

- New wager type / `protocol_version` (e.g. `freeform` or `v3-freeform`).  
- Index `usedAnswerIds`, per-user stakes, and resolution `winningId` + optional stored `winningAnswer` from logs or trace.  
- Odds preview: keyed by **observed** answers in the pool (off-chain aggregation of strings that map to known hashes).  
- MCP / agents: encode `placeBet` and `resolve` calldata; document **byte-exact** answer rules for automation.

## dApp / explorer UX

- Warn that **typos lose**; show hash or normalized preview where helpful **without** implying on-chain normalization.  
- Resolver UI: explicit confirmation of exact winning string bytes (hex or copy-paste safe control).

## Consequences

### Positive

- Supports markets that **cannot** be enumerated at creation without losing fidelity.  
- Reuses familiar parimutuel economics (single winning side).  
- Clear separation from bitmask complexity in ADR-0008.

### Negative

- **Unbounded distinct answers** (in principle) imply **settlement cost grows** with unique ticket count; must be capped or monitored.  
- **Calldata-heavy** bets for long strings.  
- **UX and dispute risk** off-chain (format wars, invisible characters) unless conventions are strict.  
- **Indexer and search** must handle arbitrary strings carefully (PII, abuse content)—product/policy outside pure smart-contract scope.

## Rejected alternatives

- **Encode every possible answer as a v2 outcome:** impossible for open-ended text.  
- **Use v2 with `numOptions = 0` and overload masks:** does not model string payloads or resolver-supplied winner text.  
- **Hash-only bets without revealing preimage on-chain:** would require a reveal phase or different claim flow; out of scope for this ADR’s “resolver submits winning text” model.  
- **On-chain Unicode normalization:** gas, correctness, and standard-choice ambiguity; rejected for v1 of this feature.

## Relationship to ADR-0008

ADR-0008 addresses **enumerated base options** and **set-valued** resolution. ADR-0009 addresses **unenumerated text answers** and **scalar resolution** (one winning string). They can coexist as separate wager types; compositing (e.g. freeform + multi-winner) is **not** in scope until explicitly specified.

## Rollout plan

1. Finalize: max length, max distinct answers, no-stake-on-winner behavior, event schema.  
2. Implement: factory + wager + Foundry tests (exact match, collisions only via hash, gas bounds, lifecycle parity).  
3. Audit: resolver abuse, griefing via many one-wei distinct answers, calldata DoS.  
4. Testnet certification: matrix analogous to ADR-0003 for create / bet / resolve / claim / expire.  
5. Indexer, explorer, MCP, and docs ship with contract addresses and version tag.

## Open questions

- Domain separation for `answerId` vs other protocol hashes.  
- Whether answers are `string` or raw `bytes` only in the ABI (bytes avoids UTF-8 assumptions in the type system but shifts encoding burden entirely to clients).  
- Whether to log full `winningAnswer` once at resolve for transparency vs hash-only + archival node reliance.

## After Action Report

**AAR date:** 2026-05-06
**AAR status:** Backfilled 2026-05-06 per ADR-0012; **superseded** at the contract layer by ADR-0010

**Summary:** ADR-0009 shipped fully as `ParamutuelFactoryFreeform` + `ParamutuelWagerFreeform` (UTF-8 answer, `keccak256(0x03 || answer)` ticket identity with domain-separation byte, exact byte match, single-winner parimutuel), then was **superseded at the contract layer** by ADR-0010 — the standalone freeform factory and wager were **deleted from the tree** and reimplemented inside `ParamutuelWagerV3` under `WagerMode.Freeform`. The economics and identity rule survive unchanged in V3.

**Outcome vs success criteria** (criteria from Decision §):

- *Separate wager implementation for freeform; not a reinterpretation of bitmask V2.* **Met initially**, then **deliberately reversed** by ADR-0010 — the reinterpretation that ADR-0009 forbade ("do not reinterpret bitmask V2") *was* avoided; ADR-0010 instead unified the **two** standalone implementations under a **single** mode-discriminated contract. This is consistent with ADR-0009's spirit: the freeform mode does not borrow bitmask semantics, even though it now shares a wager bytecode.
- *`answerId = keccak256(domain || bytes(answer))` with explicit domain byte.* **Met** — `FREEFORM_ANSWER_DOMAIN = 0x03` is fixed in V3 (`docs/ADR-0010-IMPLEMENTATION.md`).
- *Single-winner parimutuel over `pool[answerId]`.* **Met** — V3 freeform mode preserves the math; pinned by `testFreeform_documentationWorkedExample_rosebud` per `docs/PAYOUT-CALCULATION.md` Part C.
- *Exact-byte-match resolution; no on-chain normalization.* **Met** — V3 retains this rule explicitly. Worked example illustrates Rosebud / rosebud divergence.
- *Bounds: max answer length, max distinct answers.* **Met** — V3 enforces both; values documented in implementation notes.
- *No-stake-on-winner behavior chosen and tested.* **Met** — `resolve` reverts with `NoWinningStake` (recommended-default path).

**Outcome vs failure criteria** (from Negative consequences §):

- *Unbounded distinct answers → unbounded settlement cost.* **Avoided** — distinct-answer cap enforced at `placeBet`.
- *Calldata-heavy bets for long strings.* **Mitigated** — answer-length cap enforced.
- *UX / dispute risk from invisible characters.* **Triggered as designed** — exact-byte-match means typos lose. Documented in worked example.
- *Indexer must handle arbitrary strings (PII, abuse).* **Open** — handled at the indexer / explorer layer; no incident yet, but no formal abuse-content policy either.

**Lessons:**

- `LESSONS.md` L-001 (unify parallel surfaces) — ADR-0009 was the third parallel surface that triggered the unification ADR.
- `LESSONS.md` L-002 (delete superseded code) — generated by the freeform deletion in ADR-0010's sweep.

**Follow-ups:**

- Document an abuse-content policy for freeform answers (out-of-scope-content, PII, etc.) at the indexer / explorer layer.
- Decide whether to extend freeform to support multi-winner / set semantics in a future ADR (explicitly out of scope here).

**Revision schedule:** at next product roadmap review, or when the abuse-content question is concrete.
