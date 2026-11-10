# Paramutuel V3 gas profile

`ParamutuelFactoryV3` + `ParamutuelWagerV3` combine **enumerated** (bitmask tickets + `PayoffPolicy`, same economics as ADR-0008 / v2) and **freeform** text answers (ADR-0009-style pools over `answerId`) behind one factory. Gas behavior is therefore **two-headed**: enumerated hot paths match v2 scaling (distinct ticket masks), while freeform `resolve` is essentially **fixed cost** (winning pool lookup + fee charge) regardless of how many distinct answers exist in the pool.

Measurements are **environment-dependent** (Solc **0.8.24**, Foundry, `foundry.toml`: `optimizer = true`, `optimizer_runs = 200`, `via_ir = true`). **Regenerate this document** after compiler settings or V3 bytecode changes.

## How to reproduce

```bash
# Isolated gasleft() logs (representative scenarios)
forge test --match-contract ParamutuelV3GasReport -vv

# Foundry tables (factory + wager function medians from the harness)
forge test --match-path 'test/ParamutuelV3*.t.sol' --gas-report

# Wrapper
bash script/profile_v3_gas.sh
```

Source: `test/ParamutuelV3Gas.t.sol` (`ParamutuelV3GasReport`).

## Contract sizes (`forge build --sizes`)

| Contract | Runtime size (B) | Initcode size (B) |
|----------|------------------|-------------------|
| `ParamutuelFactoryV3` | **22,650** | **23,031** |
| `ParamutuelWagerV3` | **11,670** | **15,425** |

V3 is a single deployment covering both enumerated and freeform modes; the legacy split of separate V1/V2/freeform factories has been removed from the tree (see ADR-0010).

## Snapshot — `gasleft()` (isolate mode)

Reported cost is **approximate** (measured as `gasBefore - gasAfter` around the external call).

### Enumerated mode

| Step | Approx. gas | Notes |
|------|-------------|--------|
| `placeBet` (first **new** mask) | **~248k** | Pays for `usedMasks.push` + per-bettor mask bookkeeping + transfer. |
| `placeBet` (same mask) | **~73k** | Hot path; no new global mask slot. Every bet includes about 1.8k for ADR-0023's two `balanceOf` reads around the pull. |
| `resolve` (`ANY_OF`, **2** distinct global masks) | **~114k** | Linear in `_usedMasks.length`. |
| `resolve` (`ANY_OF`, **16** distinct global masks) | **~178k** | ~**4–5k** gas per extra distinct mask in this scenario (same order of magnitude as v2 — see [`ADR-0008-GAS.md`](ADR-0008-GAS.md)). |
| `claim` (bettor used **2** masks) | **~90k** | Scales with **number of distinct masks** the bettor touched. |
| `resolve` (`WEIGHTED_OVERLAP`, **2** masks) | **~110k** | Constant-time `popcount` on intersections, so bit count no longer affects cost. |

### Freeform mode

| Step | Approx. gas | Notes |
|------|-------------|--------|
| `placeBet(string)` (first **new** `answerId`) | **~207k** | `keccak256` over domain-prefixed answer bytes, `usedAnswerIds.push`, and the once-per-answer `FreeformAnswerRevealedV3` event. |
| `placeBet(string)` (same answer) | **~75k** | No new global answer slot. |
| `resolve(string)` | **~105k** | Dominated by validation + fee path; **not** linear in distinct answers (only winning pool read). |
| `resolve` with **16** distinct answers in pool | **~101k** | Stays flat with pool size. `test_C2_freeform_answerSpaceCannotBeExhausted_resolveAndClaimStayFlat` pins this at 1,100 answers. |
| `claim` (winner) | **~80k** | Single winning `answerId` leg for the bettor. |

### Factory → new wager (no seed)

| Call | Approx. gas (`gasleft()`) | `--gas-report` median (reference) |
|------|---------------------------|-------------------------------------|
| `createEnumeratedWager` (3 outcomes, no seed) | **~2.60M** | ~2.59M |
| `createFreeformWager` | **~2.50M** | ~2.50M |

Per-wager bytecode carries **both** mode branches; there is still **one** factory address on the wire.

## The per-transaction gas cap

**Base enforces a hard cap of 16,777,216 gas (2^24) per transaction** (EIP-7825, activated by the Azul upgrade). A path whose worst case exceeds this is impossible, not merely expensive, so these numbers are limits rather than estimates:

| Worst case | Gas (real transaction, cold storage) | Pinned by |
|---|---|---|
| Griefed `resolve`: 1,024 multi-outcome masks + 255 single-outcome masks, 255 options, `WEIGHTED_OVERLAP` | **6,663,978** (40% of the cap) | `test_griefed_resolve_fits_the_real_per_transaction_gas_cap`, `test_C1_coldResolve_absoluteWorstCase_fitsTxGasCap` |
| `createEnumeratedWager` with 255 short outcomes | ~8.8M | Long outcome labels can exceed the cap; creation then simply fails |
| Creation with 32 extra fee recipients | ~1M above the base | `MAX_EXTRA_FEE_RECIPIENTS` |

Before ADR-0020, `_popcount` cost about 58 gas per set bit, and this griefed `resolve` cost **20.1M** at 255 options and **16.85M** at 200 options, so anyone could make such a wager unresolvable for about 96M gas in bets. Popcount is now constant time.

**Measuring gas:** `forge test` runs a whole test in one transaction, so storage touched earlier stays warm, and `gasleft()` deltas understate real cost (by about 4M for that `resolve`). Use the `cool` cheatcode as `test/ParamutuelV3Hardening.t.sol` does, or measure a real receipt as `test/integration/test_local_e2e.py` does.

## Cost drivers & limits (safety / UX)

1. **Enumerated:** `MAX_DISTINCT_TICKETS = 1024` applies to new multi-outcome tickets; single-outcome tickets are exempt, so `_usedMasks` holds at most 1,279 entries. `resolve` costs about 5k gas per entry.
2. **Enumerated:** griefers can fill the multi-outcome capacity with dust tickets. Set `minNewTicketStake` to make that cost real collateral, which then pays into the pot.
3. **Freeform:** `MAX_ANSWER_BYTES = 1024` — long strings increase calldata cost for bettors; `answerId` is still a `bytes32`.
4. **Freeform:** no limit on distinct answers, because `resolve` and `claim` are O(1) and nothing on-chain iterates them. The indexer API bounds its response instead.
5. **Fees:** charged once at resolve / retract / expire, about 27k gas per recipient, included in the resolve numbers above.

## Illustrative USD (planning)

**Formula (same as [`research/chain-and-fee-review.md`](../research/chain-and-fee-review.md) §4):**

\[
\text{fee}_{\text{USD}} \approx \text{gas} \times \text{gasPrice}_{\text{gwei}} \times 10^{-9} \times \text{ETH}_{\text{USD}}
\]

**Caveats:** L2s may charge **L1 data / blob** components not captured by a simple `gas × gwei` product—especially for **large contract creations**. **ETH/USD** and **gwei** move constantly. Figures below are **order-of-magnitude** for budgeting, not quotes. **Revise** the assumption table when ETH/USD or network gwei snapshots change (see [`chain-and-fee-review.md`](../research/chain-and-fee-review.md) for methodology and explorer pointers).

### Assumptions used for the tables

| Input | Value | Rationale |
|-------|--------|-----------|
| **ETH / USD** | **$2,500** | Round planning number; replace with a live spot when presenting externally. |
| **Base** gas price | **0.005 gwei** | Low L2 snapshot aligned with `chain-and-fee-review.md` (Base explorer, 2026-03-20); real Base fees vary and can spike. |
| **Arbitrum One** gas price | **0.021 gwei** | Snapshot from same memo; **~4.2×** the Base gwei figure → multiply Base USD **~4.2×** for the same gas. |
| **Ethereum L1 (stress)** | **10 gwei** | Stress illustration only—per-wager `CREATE` is a poor fit at these prices (see memo §4.4). |

Effective **$ per gas unit** on Base at the above assumptions:  
\(0.005 \times 10^{-9} \times 2500 \approx \$1.25 \times 10^{-8}\) per gas.

### ~USD on Base (0.005 gwei, ETH $2,500)

Gas figures match the **Snapshot — `gasleft()`** section above unless noted.

| Operation | ~Gas | ~USD (Base) |
|-----------|------|-------------|
| `createEnumeratedWager` (3 outcomes, no seed) | ~2.60M | **~$0.033** |
| `createFreeformWager` | ~2.50M | **~$0.031** |
| `placeBet` enumerated (first **new** mask) | ~248k | **~$0.003** |
| `placeBet` enumerated (same mask) | ~73k | **~$0.0009** |
| `placeBet` freeform (first **new** answer) | ~207k | **~$0.003** |
| `placeBet` freeform (same answer) | ~75k | **~$0.0009** |
| `resolve` enumerated (`ANY_OF`, 2 distinct masks) | ~114k | **~$0.0014** |
| `resolve` enumerated (16 distinct masks) | ~178k | **~$0.0022** |
| `resolve` enumerated (`WEIGHTED_OVERLAP`, 2 masks) | ~110k | **~$0.0014** |
| `resolve` freeform | ~101–105k | **~$0.0013** |
| `claim` enumerated (2 user masks) | ~90k | **~$0.0011** |
| `claim` freeform (winner) | ~80k | **~$0.0010** |

**First-time bettor** (ERC-20 `approve` to the wager, then `placeBet`): add **~46k** gas (typical mock/ERC-20; real tokens vary) → **~$0.0006** on the same Base assumptions, **in addition to** `placeBet`.

**`retract` / `expire`:** not isolated in the V3 gas harness; both charge fees once like resolve. Expect **roughly the same order of magnitude as resolve** (often **~$0.001–0.003** on Base here) until measured explicitly.

### Same flows, stress L1 (10 gwei, ETH $2,500)

| Operation | ~Gas | ~USD (L1 stress) |
|-----------|------|------------------|
| `createEnumeratedWager` (~2.60M) | ~2.60M | **~$65** |
| `placeBet` (first new mask ~248k) | ~248k | **~$6.20** |
| `resolve` (~114k) | ~114k | **~$2.85** |

### Quick read

On **Base-class** L2s at **sub-cent gwei**, **creating** a V3 wager is typically **a few cents**; **bet / resolve / claim** are usually **sub-cent to a few cents** per transaction. **Dollar cost is dominated by chain and gas price**, not the difference between e.g. 130k and 200k gas on Base. For **Arbitrum** at **0.021 gwei**, scale the Base column by **~4.2×**.

## Related

- Enumerated policy semantics and v2 historical tables: [`ADR-0008-GAS.md`](ADR-0008-GAS.md), [`ADR-0008-IMPLEMENTATION.md`](ADR-0008-IMPLEMENTATION.md)  
- Freeform economics: [`ADR-0009-IMPLEMENTATION.md`](ADR-0009-IMPLEMENTATION.md)  
- ABI sync after changes: [`CONTRACT-UPGRADE-RUNBOOK.md`](CONTRACT-UPGRADE-RUNBOOK.md) (`script/sync-abi.sh`)

**Not a substitute for a formal audit** — use this profile for budgeting, regressions, and release notes; external review remains required before mainnet (see [`TASKS.md`](TASKS.md) — Mainnet).
