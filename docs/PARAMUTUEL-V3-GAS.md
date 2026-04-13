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
| `ParamutuelFactoryV3` | **21,311** | **21,701** |
| `ParamutuelWagerV3` | **11,651** | **15,378** |

For comparison on the same toolchain (not a product requirement):

| Contract | Runtime size (B) |
|----------|------------------|
| `ParamutuelFactoryV2` | 17,275 |
| `ParamutuelWagerV2` | 9,065 |

V3’s larger factory reflects **one deployment** covering both modes; the wager runtime sits between legacy v2-only and a hypothetical “v2 + freeform” pair deployed separately.

## Snapshot — `gasleft()` (isolate mode)

Reported cost is **approximate** (measured as `gasBefore - gasAfter` around the external call).

### Enumerated mode

| Step | Approx. gas | Notes |
|------|-------------|--------|
| `placeBet` (first **new** mask) | **~246k** | Pays for `usedMasks.push` + per-bettor mask bookkeeping + transfer. |
| `placeBet` (same mask) | **~72k** | Hot path; no new global mask slot. |
| `resolve` (`ANY_OF`, **2** distinct global masks) | **~136k** | Linear in `_usedMasks.length`. |
| `resolve` (`ANY_OF`, **16** distinct global masks) | **~200k** | ~**4–5k** gas per extra distinct mask in this scenario (same order of magnitude as v2 — see [`ADR-0008-GAS.md`](ADR-0008-GAS.md)). |
| `claim` (bettor used **2** masks) | **~90k** | Scales with **number of distinct masks** the bettor touched. |
| `resolve` (`WEIGHTED_OVERLAP`, **2** masks) | **~132k** | Extra `popcount` work on intersections vs `ANY_OF`. |

### Freeform mode

| Step | Approx. gas | Notes |
|------|-------------|--------|
| `placeBet(string)` (first **new** `answerId`) | **~248k** | `keccak256` over domain-prefixed answer bytes + `usedAnswerIds.push`. |
| `placeBet(string)` (same answer) | **~73k** | No new global answer slot. |
| `resolve(string)` | **~128k** | Dominated by validation + fee path; **not** linear in distinct answers (only winning pool read). |
| `resolve` with **16** distinct answers in pool | **~123k** | Confirms resolve stays ~flat vs pool cardinality in sampled run. |
| `claim` (winner) | **~80k** | Single winning `answerId` leg for the bettor. |

### Factory → new wager (no seed)

| Call | Approx. gas (`gasleft()`) | `--gas-report` median (reference) |
|------|---------------------------|-------------------------------------|
| `createEnumeratedWager` (3 outcomes, no seed) | **~2.61M** | ~2.60M |
| `createFreeformWager` | **~2.51M** | ~2.51M |

Per-wager bytecode is larger than v2-only because the implementation carries **both** mode branches; product default is still **one** factory address on the wire.

## Foundry `--gas-report` excerpt (same run as above)

| Artifact | Deployment cost | Deployment size (report column) |
|----------|-----------------|----------------------------------|
| `ParamutuelFactoryV3` | ~4.66M | ~21.8k |
| `ParamutuelWagerV3` | (via factory `CREATE`) | ~16.1k (init/runtime column in report) |

Function medians from `test/ParamutuelV3Gas.t.sol` only:

| Function | Median (approx.) |
|----------|------------------|
| `placeBet(uint256,uint256)` | ~160k |
| `placeBet(string,uint256)` | ~161k |
| `resolve(uint256)` | ~131k |
| `resolve(string)` | ~122k |
| `claim` | ~77k |

## Cost drivers & limits (safety / UX)

1. **Enumerated:** `MAX_DISTINCT_TICKETS = 1024` — worst-case resolve iterates all used masks; keep **product caps** far below (e.g. tens of masks) on L2.
2. **Enumerated:** `WEIGHTED_OVERLAP` — same mask loop as `ANY_OF` with extra intersection popcount per ticket.
3. **Freeform:** `MAX_ANSWER_BYTES = 1024` — long strings increase calldata cost for bettors; `answerId` is still a `bytes32`.
4. **Freeform:** `maxDistinctAnswers` up to **1024** at factory level — each **new** answer pays a `usedAnswerIds.push` on first stake; resolve cost does not scale with that count.
5. **Fees:** `_chargeFeesOnce` runs at resolve / retract / expire — included in the resolve numbers above.

## Related

- Enumerated policy semantics and v2 historical tables: [`ADR-0008-GAS.md`](ADR-0008-GAS.md), [`ADR-0008-IMPLEMENTATION.md`](ADR-0008-IMPLEMENTATION.md)  
- Freeform economics: [`ADR-0009-IMPLEMENTATION.md`](ADR-0009-IMPLEMENTATION.md)  
- ABI sync after changes: [`CONTRACT-UPGRADE-RUNBOOK.md`](CONTRACT-UPGRADE-RUNBOOK.md) (`script/sync-abi.sh`)

**Not a substitute for a formal audit** — use this profile for budgeting, regressions, and release notes; external review remains required before mainnet (see [`TASKS.md`](TASKS.md) — Mainnet).
