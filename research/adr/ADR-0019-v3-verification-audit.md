# ADR-0019: V3 verification audit — correctness vs intent, test-parity restoration

Date: 2026-09-26
Status: **Implemented** (audit + test backfill + off-chain fixes); contract-level mitigations **Proposed** (require a new factory / wager bytecode)
Builds on: ADR-0001, ADR-0005, ADR-0009, ADR-0010, ADR-0013, `AGENTS.md` #1 / #2 / #4 / #8

## Context

Much of this codebase was written by earlier, weaker agents. The operator asked for an independent
verification of the implementation's correctness and a validation against the project's stated
intent (README thesis + ADR corpus). The canonical protocol is `ParamutuelFactoryV3` +
`ParamutuelWagerV3` (ADR-0010); every other layer (indexer, sweeper, resolution service, MCP,
dApp, bet scout) mirrors its semantics off-chain.

The audit (full line-by-line read of `src/`, cross-check against ADR-0001/0002/0005/0009/0010,
`docs/PAYOUT-CALCULATION.md`, `docs/WAGER-LIFECYCLE.md`, plus a git-history trace of the test
suite) found:

1. **Contract economics are correct.** Parimutuel math for all five payoff policies, fee
   charging (once, floor-rounded, remainder to last recipient), refund math, and claim
   conservation (`sum(payouts) <= netPot`, dust stays in the wager) all match the docs. No
   reentrancy path found (all token-moving entry points are `nonReentrant`, state written
   before transfers). No arithmetic overflow reachable with realistic token supplies.

2. **Test-parity regression (AGENTS.md #2 / #8).** Commit `b2a2f28` ("propagate ADR-0010
   V3-only protocol") deleted `test/Paramutuel.t.sol` (57 V1 tests) together with the V1
   contracts. The V1 suite covered the lifecycle / access-control / fee-cap / token-failure
   surface that V3 inherited verbatim; **none of it was ported to V3**. As of this ADR, 15 of
   the V3 wager/factory custom errors (`NotBettingCloser`, `NotResolutionCloser`,
   `AlreadyFinalized`, `ResolutionWindowOver`, `BettingNotClosed`, `WindowTooShort`,
   `BadFeeConfig`, `FeeConfigMismatch`, `FeeTooHigh`, `NotFactory`, `NotOpen`,
   `TooManyDistinctTickets`, `InvalidOutcome`, `InvalidDistinctCap`, `BadOutcomes`) and every
   string `require` (`TREASURY`, `FEE`, `AMOUNT`, `TRANSFER_FROM`, `TRANSFER`,
   `OUTCOMES_MIN/MAX`) have **no test**. `closeBetting`, `closeResolutionWindow`,
   `withdrawFees`, authority-anchored resolution windows and the factory-only seeder guard
   are untested. `forge coverage` remains blocked (the 17-argument wager constructor's ABI
   decoder is stack-too-deep even under `--ir-minimum`, re-verified with forge 1.5.1), so the
   gap was invisible to tooling.

3. **Freeform answer-space exhaustion griefing (security, medium).** ADR-0009's rollout plan
   required an audit of "griefing via many one-wei distinct answers"; no record of it exists.
   A PoC confirms: one address placing 1024 bets of 1 wei on distinct strings fills
   `maxDistinctAnswers` for **~101.5M gas (≈ $1.3 at the Base prices in
   `docs/PARAMUTUEL-V3-GAS.md`) and 1024 wei of stake**, after which *no* bettor can stake on
   any new answer — including the eventually-correct one. Done immediately after creation it
   neuters the market. The same shape applies to enumerated wagers with a multi-bit policy and
   `numOptions >= 11` (`MAX_DISTINCT_TICKETS = 1024` masks). SINGLE_WINNER enumerated wagers
   are immune (at most `numOptions <= 255` masks).

4. **Stale intent record (ADR-0005).** ADR-0005 §Decision says both closers "default
   **proposer** when `address(0)`", and its AAR claims that default is "Met … implemented and
   tested". It is neither: commit `bc8e4a8` deliberately changed the semantics so that
   `address(0)` **disables** the role (the factory passes it through unchanged and rejects
   zero-time windows without a closer). `docs/WAGER-LIFECYCLE.md` documents the real behavior;
   the ADR does not.

5. **Residual liveness assumption (documented, not new).** With `bettingCloseTime == 0` or
   `resolutionWindow == 0`, the corresponding closer is the *only* way forward; if that key is
   lost, stake is locked forever (`retract` and `expire` both require betting closed). The
   factory's `InvalidLifecycleConfig` check guarantees a closer exists, not that it stays live.
   ADR-0001's "anyone can `expire()` … to prevent stuck funds" holds only for time-bounded
   wagers.

6. **`resolutionDeadline` is informational only.** When `bettingCloser` closes early, the
   effective resolution deadline is `bettingClosedAtByAuthority + resolutionWindow`, earlier
   than the immutable `resolutionDeadline`. Off-chain consumers must derive the deadline from
   the close anchor, not read the immutable. (Checked against the indexer / sweeper in the
   peripheral review recorded in `docs/ADR-0019-IMPLEMENTATION.md`.)

Token-class caveats (no-bool tokens fail safe, fee-on-transfer / rebasing fail unsafe) are
already scoped by ADR-0018 and are not re-decided here.

## Decision

1. **Restore V3 test parity** in a new fast-suite file `test/ParamutuelV3Lifecycle.t.sol`
   porting every behavior the deleted V1 suite pinned that still exists in V3, plus the V3-only
   paths (seeder guard, distinct-ticket cap, constructor-level defence-in-depth). Each named
   revert in `src/` must be hit by at least one test asserting its selector.
2. **Prove the tests are non-trivial** (AGENTS.md #1) by mutation: for each lifecycle guard,
   temporarily delete or invert it in `src/` and confirm at least one new test fails; revert
   the mutation. Results recorded in `docs/ADR-0019-IMPLEMENTATION.md`. (Red-before-green is
   inverted here because the code pre-exists; mutation is the honest equivalent.)
3. **Pin the griefing boundary as an executable fact** (per `LESSONS.md` L-003): a fast-suite
   test demonstrating that 1024 one-wei distinct answers lock out new answers. The deployed
   bytecode is immutable, so the mitigation is **Proposed** for the next factory/wager
   revision, not implemented here:
   - a per-wager `minNewTicketStake` (minimum stake to open a new answer id / mask), and/or
   - making `maxDistinctAnswers` a proposer-chosen factory argument, so small private wagers
     can shrink the attack surface and large public ones can price it.
   Until then, curated surfaces (dApp / site / bet scout) should warn on freeform wagers whose
   `usedAnswerIdsCount()` approaches `maxDistinctAnswers`.
4. **Correct ADR-0005 by AAR revision** (append-only, per ADR-0012): record that closers are
   optional and `address(0)` disables the role since `bc8e4a8`, and retract the incorrect
   "Met" claim.
5. **Fix verified peripheral bugs** (indexer / services / clients) under TDD, each as its own
   commit on this branch, listed in `docs/ADR-0019-IMPLEMENTATION.md`.

## Decision points

- Test file layout: one new file rather than growing `ParamutuelV3Enumerated.t.sol`, because
  the lifecycle surface is mode-independent; freeform-specific lifecycle tests reuse the same
  file with a freeform helper.
- The PoC griefing test runs in the fast suite (~0.1 s wall time) — it does not qualify for
  the extended suite under AGENTS.md #13.
- No change to `src/` in this ADR. Contract mitigations are a future ADR with a new factory
  deployment (ADR-0002: parameter changes = new factory).

## Success criteria

- Every custom error and string `require` in `src/` is asserted by at least one test.
- Every mutation listed in the implementation notes is killed by the new tests.
- `script/test-fast.sh` passes with the new tests.
- ADR-0005 carries an AAR revision matching the code.
- Every peripheral finding is either fixed with a regression test or recorded with rationale.

## Failure criteria

- A new test passes against a mutated guard (test is structural, not behavioral) — fix the
  test before merge.
- Porting surfaces a genuine V3 behavioral regression vs V1 — escalate to a contract ADR
  rather than bending the test.

## Rejected alternatives

- **Patch `src/` to add a minimum-new-ticket stake now.** Deployed wagers are immutable and the
  live factory would keep producing vulnerable wagers; a contract change needs its own ADR,
  deployment plan, and indexer/client migration. Recorded as the Proposed follow-up instead.
- **Restore `test/Paramutuel.t.sol` from history.** It targets deleted V1 ABIs (`createWager`,
  outcome indices); porting is required, not restoration.

## After Action Report

**AAR date:** 2026-09-26
**AAR status:** Initial (revisit after the operator redeploys in `docs/ADR-0019-IMPLEMENTATION.md` §Operator follow-ups and the extended suite has run against them)

**Outcome vs success criteria:**

- *Every custom error and string `require` in `src/` asserted by a test.* **Met** — `script/check-revert-coverage.py` (fast suite): 30 errors + 8 strings; fails with 23 missing against master's `test/`.
- *Every listed mutation killed.* **Met** — 28 / 28 (one initial survivor fixed in `d25577a`); table in the implementation notes.
- *`script/test-fast.sh` passes.* **Met** — 109 Foundry tests + Python + node layers.
- *ADR-0005 AAR matches code.* **Met** — revision appended.
- *Every peripheral finding fixed with a regression test or recorded with rationale.* **Met** — 12 fixed under red → green; 2 intent/contract items recorded as follow-ups (answer-space mitigation, freeform answer-text recovery); 2 leads rejected with rationale.

**Outcome vs failure criteria:**

- *A new test passes against a mutated guard.* **Triggered once, mitigated** — fee-remainder test strengthened and re-verified.
- *Genuine V3 regression vs V1.* **Avoided** — no contract behaviour change was needed; all V1-era behaviours ported hold on V3.

**Lessons:** L-008 (AAR claims need a named test), L-009 (port tests by behaviour when deleting superseded code). Also reconfirmed L-006: the sub-agent leads were valuable but one (answer trimming on bet surfaces) was a convention, not a bug — verify before acting.

**Revision schedule:** after the resolution-service and indexer redeploys; again when the contract-mitigation ADR lands.

**AAR revision — 2026-11-07 (ADR-0020).** A second pass re-tested this AAR's claims. Several did not hold, which is the failure L-008 describes:

- *"12 fixed under red → green":* **three were partial.**
  - Finding 8 (answers stripped) was fixed in the resolution service, but the control-panel CLI still stripped (ADR-0020 O5), and so did dApp resolve (W4).
  - Finding 11 (staking after close) was undone in the normal flow, because connecting a wallet re-enabled the button (W1).
  - The byte-exact regression test asserted on the argument passed to `cast`, which `cast` then altered on its way to the chain (O0).
- *"28 / 28 mutations killed":* **not reproducible as recorded,** because the harness was never committed. ADR-0020 commits `script/mutation-check.py`; it includes these 28 among its 66, and all 66 are killed.
- *"Contract economics correct":* **holds for the arithmetic of the happy path.** But Base's per-transaction gas cap of 16,777,216 (EIP-7825) turned finding 3 from "new answers locked out" into "the market cannot be resolved" (C1). And checked 256-bit math could lock funds permanently on high-supply tokens (C4).
- *The extended suite as verification:* **its read-only mode skips 8 of 9 tests.** ADR-0020 added a local-chain end-to-end layer and a real-browser layer, and the browser layer found the most serious defect of either audit: no browser could resolve a V3 wager (ADR-0020 W14).
- *Follow-ups:* the two contract follow-ups (answer-space mitigation, answer-text recovery) are **done in source** by ADR-0020 and take effect when the factory is redeployed. The operator redeploys listed in the implementation notes are still pending.

