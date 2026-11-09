# ADR-0023: Refuse a bet when the wager receives less collateral than it records

Date: 2026-11-09
Status: **Accepted**
Builds on: ADR-0018 (collateral curation overlay), ADR-0020 (contract fixes awaiting a factory redeploy), `AGENTS.md` #1 / #2 / #4

## Context

The wager records each bet at the amount the bettor asked to transfer. A fee-on-transfer token delivers that amount minus its fee, so the wager owes more than it holds. With a 1% fee it is short by 1% of everything bet. Withdrawals pay the full amount owed or revert, first come, first served, so the last to withdraw get nothing until someone tops the balance back up. A winner can be the one left unpaid. Both cases were pinned by `test_ADR0018_feeOnTransferToken_breaksSolvency_failsUnsafe` and `test_ADR0018_feeOnTransferToken_lastWinnerUnpaid_untilToppedUp`.

ADR-0018 left the core unchanged and relied on the curated surfaces' warnings. It weighed two on-chain alternatives and rejected both:
- **Full support** through balance-delta accounting, because it means splitting each token skim across the tickets of a batch or seed.
- **A hard allowlist**, because it contradicts permissionlessness.

It did not weigh a third option: measure what arrived, and refuse the bet when it is less. Its own risks section names the gap that remains, "curation theater": a bettor who bypasses the site, or ignores its warning, can still lose money.

Two things make this the time to act:
- ADR-0018 wanted the core's bytecode frozen, but ADR-0020's fixes already require a new factory. The operator has not deployed it yet, so adding a check now costs no extra migration.
- Full support was reconsidered on 2026-11-09 and is still not worth it:
  - The token's fee on every payout cannot be fixed by the protocol.
  - Many fee-charging tokens also redistribute fees to holders, which changes balances like a rebasing token.
  - No curated token charges a fee.

## Decision

1. **Every collateral pull measures what arrived.** Each place that pulls collateral reads the recipient wager's `balanceOf` before and after its `transferFrom`, and reverts with `CollateralShortfall()` when the balance rose by less than the amount pulled:
   - the wager's three bet functions: `placeBet(uint256,uint256)`, `placeBets` and `placeBet(string,uint256)`;
   - the factory's seed-bet pull.
2. **No other behaviour changes.** A token that delivers what it is asked to behaves exactly as before. Accounting, events, signatures and the clients are unchanged, apart from one new error in each contract's ABI.
3. **`IERC20` gains `balanceOf`**, the only extra token method the core reads.
4. **Scope:** fee-on-transfer tokens now fail safe, like USDT-style tokens: the bet cannot be placed. Rebasing tokens remain unsupported, since their balances drift after the bet, where no check at the time of transfer can see it.

## Decision points

- **Revert on a shortfall only, not on any mismatch.** Only a shortfall breaks solvency. A token that delivers more than requested leaves an excess the wager never pays out, which costs no participant anything. Rejecting it would refuse a harmless token for no gain.
- **Measure the wager's balance, not the sender's.** What the wager can pay depends only on its own balance. A token may also take its fee from the sender on top of the amount, in which case the wager receives the full amount and the bet is safe.
- **The factory checks the seed pull itself.** It pulls the seed total straight into the new wager, so the wager never sees that transfer. The factory reads the wager's balance before and after, which also stays correct if someone sent tokens to the wager's predictable address in advance.
- **One error name in both contracts.** Both declare `CollateralShortfall()`, with the same selector, so a client decodes it the same way from either contract.
- **Fees switched on later.** If a token's issuer switches a fee on after bets exist:
  - new bets revert;
  - existing wagers stay solvent, because a fee on a payout lowers what the recipient receives, not what the wager holds against its records;
  - recipients receive less than they are owed. That is the token's behaviour, and it is disclosed.
- **Cost:** two extra `balanceOf` calls per pull, measured in the AAR.

## Success criteria

- New tests, written first and failing against the unchanged contracts, prove that a fee-on-transfer token:
  - reverts `placeBet` (enumerated and freeform), `placeBets` and a seeded creation with `CollateralShortfall()`;
  - moves no tokens and records no stake.
- A token whose fee is switched on after the bets refuses new bets, and every existing claim and fee withdrawal still succeeds.
- A token that delivers more than requested is accepted, its bet is recorded at the requested amount, and the wager holds at least what it owes.
- The two old fail-unsafe tests are replaced by fail-safe ones.
- `script/check-revert-coverage.py` passes.
- Mutants that delete either check are killed (`script/mutation-check.py --only shortfall`).
- The fast suite and `script/test-local-e2e.sh` pass.
- The factory stays under EIP-170's 24,576-byte limit.
- Docs say which behaviour the live factory has and which the redeployed one will have.

## Failure criteria

- A standard token is refused. That would mean a token whose `balanceOf` misreports, and no such token is in the curated list.
- The added gas makes any path in `docs/PARAMUTUEL-V3-GAS.md` exceed Base's per-transaction cap. It cannot: the check adds a fixed cost per transaction, not per ticket.
- The factory exceeds EIP-170.

## Rejected alternatives

- **Full support through balance-delta accounting:** see Context, and ADR-0018.
- **Revert on any mismatch:** see Decision points.
- **Leave the core unchanged and rely on warnings (ADR-0018's choice):** the only way it fails is unsafe, and only people who use the curated surfaces are protected.

## After Action Report

Pending.
