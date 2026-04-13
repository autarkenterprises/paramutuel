# Paramutuel v2 gas profile (ADR-0008)

Measurements are **environment-dependent** (Solc 0.8.24, Foundry, optimizer settings from `foundry.toml`). Regenerate before audits.

## How to reproduce

```bash
# Full Foundry table for all V2 tests
forge test --match-path 'test/ParamutuelV2*.t.sol' --gas-report

# Isolated `gasleft()` logs (first / second bet, resolve, claim)
forge test --match-contract ParamutuelV2GasReport -vv
```

Helper: `script/profile_v2_gas.sh` runs the `--gas-report` pass.

## Snapshot (representative)

### Contract deployment (from `--gas-report`, `ParamutuelV2.t.sol` only)

| Artifact | Deployment gas | Runtime size (bytes) |
|----------|----------------|----------------------|
| `ParamutuelFactoryV2` | ~3.74M | ~17.5k |
| `ParamutuelWagerV2` (per create) | (included in `createWager`) | ~13.3k |

### `ParamutuelWagerV2` function medians (aggregated across `ParamutuelV2.t.sol` runs)

| Function | Median gas (approx.) | Notes |
|----------|----------------------|--------|
| `placeBet` | ~219k | First use of a **new** ticket mask pays for `usedMasks.push` + user mask bookkeeping. |
| `placeBet` (same mask) | ~71k | Measured via `gasleft()` in `ParamutuelV2GasReport` — cheaper hot path. |
| `resolve` | ~131k | Scales **linearly** with `usedMasks.length` (loop over distinct ticket masks). |
| `claim` | ~77k | Scales with **number of distinct masks** the bettor used. |

### `createWager` (factory → new wager)

| Call | Approx. gas |
|------|-------------|
| `ParamutuelFactoryV2.createWager` (no seed) | ~2.09M (`gasleft()` log) / ~2.08M median in table |

### Resolve scaling check

| Scenario | Approx. gas (`gasleft()`) |
|----------|---------------------------|
| `ANY_OF`, **2** distinct global masks | ~136k |
| `ANY_OF`, **16** distinct global masks | ~200k |

Rule of thumb: **~4–5k gas per extra distinct ticket mask** in the resolve loop (policy checks + popcount + `ticketPoolTotal` read), plus base overhead — validate on target `numOptions` before mainnet.

## Cost drivers & limits

1. **`MAX_DISTINCT_TICKETS = 1024`** — worst-case resolve approaches **millions** of gas; keep product caps lower (e.g. 32–64 distinct masks) for L2 budgets.
2. **`WEIGHTED_OVERLAP`** — same loop as `ANY_OF` but extra `popcount` on the intersection per mask.
3. **`placeBets` batch** — one `transferFrom` + multiple `_recordBet`; amortizes ERC-20 overhead.

## Related

- [`ADR-0008-IMPLEMENTATION.md`](ADR-0008-IMPLEMENTATION.md)  
- [`ADR-0008-TEMPLATES.md`](ADR-0008-TEMPLATES.md)  
- **V3** (enumerated + freeform, one factory): [`PARAMUTUEL-V3-GAS.md`](PARAMUTUEL-V3-GAS.md)
