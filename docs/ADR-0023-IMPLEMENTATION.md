# ADR-0023 implementation notes: collateral receipt check

Decision: [`research/adr/ADR-0023-collateral-receipt-check.md`](../research/adr/ADR-0023-collateral-receipt-check.md).

## What changed

| Where | Change |
|---|---|
| `src/ParamutuelWagerV3.sol` | New `_pullCollateral(amount)`. It reads the wager's balance, calls `transferFrom`, requires `true`, and reverts `CollateralShortfall()` if the balance rose by less than `amount`. `placeBet(uint256,uint256)`, `placeBets` and `placeBet(string,uint256)` all pull through it. |
| `src/ParamutuelFactoryV3.sol` | New `_pullSeed(token, wager, amount)`, the same check for the seed total that the factory pulls into a new wager. It is a separate function so `_createEnumerated` stays within the stack limit of the unoptimised coverage build. |
| `src/interfaces/IERC20.sol` | Adds `balanceOf`. |
| `dapp/abi/`, `mcp_server/abi/` | Regenerated with `script/sync-abi.sh`; the only difference is the new error in each contract. |
| `test/utils/MockTokens.sol` | Adds `AdjustableTransferToken`, whose delivery the test sets: exact, short (a fee) or over. |
| `test/ParamutuelV3Hardening.t.sol` | Six `test_ADR0023_*` tests. Removes the two ADR-0018 tests that pinned the old fail-unsafe behaviour. |
| `script/mutation-check.py` | Three new mutants: delete the wager's check, delete the factory's check, and tighten `<` to `!=`. The `placeBet-transferFrom-check` mutant now targets the shared helper. |

## Tests

| Test | Shows |
|---|---|
| `test_ADR0023_feeOnTransfer_enumeratedPlaceBet_revertsShortfall` | Enumerated `placeBet` reverts; no tokens move and no stake is recorded. |
| `test_ADR0023_feeOnTransfer_placeBets_revertsShortfall` | The batch reverts as a whole. |
| `test_ADR0023_feeOnTransfer_freeformPlaceBet_revertsShortfall` | Freeform `placeBet` reverts. |
| `test_ADR0023_feeOnTransfer_seededCreate_revertsShortfall` | Seeded creation reverts with the factory's error, and no wager is created. |
| `test_ADR0023_feeSwitchedOnAfterBets_refusesNewBets_existingWagerStaysSolvent` | Once a fee is switched on, new bets revert. Every existing claim and fee withdrawal succeeds, the wager ends empty, and the winner receives 99% of what is owed. |
| `test_ADR0023_tokenDeliveringMore_isAccepted_atRequestedAmount` | An excess is accepted and the bet is recorded at the requested amount. The excess stays in the wager. |

The first five failed against the unchanged contracts ("next call did not revert as expected"). The last passed before and after the change. It pins behaviour the change had to keep, and it is what kills the `!=` mutant.

## Cost

Measured with `ParamutuelV3GasReport`, against `master`:

| Call | Before | After |
|---|---|---|
| Enumerated `placeBet`, first distinct mask | 246,420 | 248,220 |
| Enumerated `placeBet`, same mask | 71,635 | 73,435 |
| Freeform `placeBet`, first distinct answer | 204,852 | 206,670 |
| Freeform `placeBet`, same answer | 72,786 | 74,604 |
| `createEnumeratedWager`, no seed | 2,616,498 | 2,603,422 |
| `createFreeformWager` | 2,516,634 | 2,503,559 |

- **Bets** cost about 1,800 gas more each, the same for one ticket or a batch.
- **Creation** costs about 13,000 less, because the wager's three pulls now share one helper and its bytecode shrank.
- **Factory runtime size:** 22,820 bytes, 1,756 under EIP-170.

## Operator follow-ups

- **Deploy the corrected factory.** This is step 2 of [`ADR-0020-IMPLEMENTATION.md`](ADR-0020-IMPLEMENTATION.md), and it now carries this change too. Until then, the live factory accepts fee-on-transfer tokens and fails unsafely.
- **After that deploy,** drop "fee-on-transfer" from the unlisted-token warnings, which will then hold only for rebasing tokens:
  - `dapp/index.html`, `dapp/app.js` and `dapp/README.md`;
  - `site/propose-a-wager.html`, `site/resonance-propose.html` and `site/bet-logic.js`;
  - the README's notes on the live factory.
