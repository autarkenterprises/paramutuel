#!/usr/bin/env python3
"""Mutation check for the contracts (AGENTS.md #1, ADR-0020).

Tests only prove something if they fail when the code is wrong. This weakens one
guard at a time in a scratch copy of the repo, runs the contract suite, and
reports whether any test noticed. `src/` in the working tree is never touched.

ADR-0019 reported a 28/28 result from a harness it never committed, so the claim
could not be re-run. This file is that harness, extended to the ADR-0020 fixes.

Every mutation is one exact-string replacement, and a pattern that no longer
matches is reported as STALE rather than silently skipped, so the list cannot rot
unnoticed when `src/` changes.

Usage:
    python3 script/mutation-check.py            # every mutation (slow: one IR compile each)
    python3 script/mutation-check.py --only fee # ids containing a substring
    python3 script/mutation-check.py --list

A baseline run with no mutation happens first, because a suite that already fails would make every
mutation look killed.

Runs with the optimizer off, which compiles about five times faster and does not change whether a
guard holds. The one test excluded is a tight gas bound that only holds when optimized.

Exit 0 when every mutation is killed; 1 if any survived or went stale.
Belongs on the extended path (AGENTS.md #13): roughly one minute per mutation.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WAGER = "src/ParamutuelWagerV3.sol"
FACTORY = "src/ParamutuelFactoryV3.sol"
FULLMATH = "src/utils/FullMath.sol"
BITMATH = "src/utils/BitMath.sol"

# (id, file, exact text to replace, replacement). Text must occur exactly once.
MUTATIONS: list[tuple[str, str, str, str]] = [
    # --- authority and lifecycle guards (ADR-0019 set, updated for current source) ---
    ("closeBetting-auth", WAGER, "if (msg.sender != bettingCloser) revert NotBettingCloser();", ""),
    ("closeBetting-idempotence", WAGER, "        if (_bettingClosed()) return;\n        bettingClosedByAuthority = true;", "        bettingClosedByAuthority = true;"),
    ("closeResWin-auth", WAGER, "if (msg.sender != resolutionCloser) revert NotResolutionCloser();", ""),
    ("closeResWin-needs-betting-closed", WAGER, "if (msg.sender != resolutionCloser) revert NotResolutionCloser();\n        if (!_bettingClosed()) revert BettingNotClosed();", "if (msg.sender != resolutionCloser) revert NotResolutionCloser();"),
    ("closeResWin-after-final-noop", WAGER, "if (resolutionWindowClosedByAuthority || state != State.Open) return;", "if (resolutionWindowClosedByAuthority) return;"),
    ("resWinOpen-ignores-authority", WAGER, "        if (resolutionWindowClosedByAuthority) return false;\n", ""),
    ("resWinOpen-off-by-one", WAGER, "return block.timestamp <= uint256(_bettingClosedAt()) + uint256(resolutionWindow);", "return block.timestamp < uint256(_bettingClosedAt()) + uint256(resolutionWindow);"),
    ("anchor-ignores-authority", WAGER, "return bettingClosedByAuthority ? bettingClosedAtByAuthority : bettingCloseTime;", "return bettingCloseTime;"),
    ("bettingClosed-off-by-one", WAGER, "block.timestamp >= bettingCloseTime);", "block.timestamp > bettingCloseTime);"),
    ("retract-auth", WAGER, "function retract() external nonReentrant {\n        if (msg.sender != resolver) revert NotResolver();", "function retract() external nonReentrant {"),
    ("retract-finality", WAGER, "function retract() external nonReentrant {\n        if (msg.sender != resolver) revert NotResolver();\n        if (state != State.Open) revert AlreadyFinalized();", "function retract() external nonReentrant {\n        if (msg.sender != resolver) revert NotResolver();"),
    ("retract-window", WAGER, "if (!_resolutionWindowOpen()) revert ResolutionWindowOver();\n\n        _chargeFees();\n        state = State.Retracted;\n        emit RetractedV3();", "_chargeFees();\n        state = State.Retracted;\n        emit RetractedV3();"),
    ("expire-finality", WAGER, "function expire() external nonReentrant {\n        if (state != State.Open) revert AlreadyFinalized();", "function expire() external nonReentrant {"),
    ("expire-needs-betting-closed", WAGER, "function expire() external nonReentrant {\n        if (state != State.Open) revert AlreadyFinalized();\n        if (!_bettingClosed()) revert BettingNotClosed();", "function expire() external nonReentrant {\n        if (state != State.Open) revert AlreadyFinalized();"),
    ("expire-window", WAGER, "if (!_resolutionWindowOver()) revert ResolutionWindowOver();", ""),
    ("seeder-auth", WAGER, "if (msg.sender != factory) revert NotFactory();", ""),
    ("resolve-enum-auth", WAGER, "function resolve(uint256 winningMask_) external nonReentrant onlyEnumerated {\n        if (msg.sender != resolver) revert NotResolver();", "function resolve(uint256 winningMask_) external nonReentrant onlyEnumerated {"),
    ("resolve-free-auth", WAGER, "function resolve(string calldata winningAnswer) external nonReentrant onlyFreeform {\n        if (msg.sender != resolver) revert NotResolver();", "function resolve(string calldata winningAnswer) external nonReentrant onlyFreeform {"),
    ("resolve-no-winner-enum", WAGER, "if (units == 0) revert NoWinningStake();", ""),
    ("resolve-no-winner-free", WAGER, "if (winPool == 0) revert NoWinningStake();", ""),
    # --- money movement ---
    ("claim-nonReentrant", WAGER, "function claim() external nonReentrant returns (uint256 paid) {", "function claim() external returns (uint256 paid) {"),
    ("claim-double", WAGER, "if (hasClaimed[msg.sender]) revert NothingToClaim();", ""),
    ("claim-transfer-check", WAGER, 'bool ok = collateralToken.transfer(msg.sender, paid);\n        require(ok, "TRANSFER");\n        emit ClaimedV3', 'collateralToken.transfer(msg.sender, paid);\n        emit ClaimedV3'),
    ("claim-zero-reverts", WAGER, "if (paid == 0) revert NothingToClaim();\n", ""),
    ("claim-refund-uses-gross", WAGER, "paid = FullMath.mulDiv(grossUserStake, netPot, totalPot);", "paid = grossUserStake;"),
    ("claim-weight-ignored", WAGER, "uint256 weight = payoffPolicy == PayoffPolicy.WEIGHTED_OVERLAP ? amt * BitMath.popcount(overlap) : amt;", "uint256 weight = amt;"),
    ("withdrawFees-zeroes-balance", WAGER, "feeBalances[msg.sender] = 0;", ""),
    ("fee-remainder-to-last", WAGER, "slice = feesTotal - paid;", "slice = FullMath.mulDiv(feesTotal, feeBps[i], totalFeeBps);"),
    ("fees-skip-charge-on-retract", WAGER, "_chargeFees();\n        state = State.Retracted;\n        emit RetractedV3();", "state = State.Retracted;\n        emit RetractedV3();"),
    ("placeBet-transferFrom-check", WAGER, 'bool ok = collateralToken.transferFrom(msg.sender, address(this), amount);\n        require(ok, "TRANSFER_FROM");\n\n        _recordBetMask(msg.sender, ticketMask, amount);', 'collateralToken.transferFrom(msg.sender, address(this), amount);\n\n        _recordBetMask(msg.sender, ticketMask, amount);'),
    ("placeBet-after-final", WAGER, "function placeBet(uint256 ticketMask, uint256 amount) external nonReentrant onlyEnumerated {\n        if (state != State.Open) revert NotOpen();", "function placeBet(uint256 ticketMask, uint256 amount) external nonReentrant onlyEnumerated {"),
    ("placeBets-after-final", WAGER, "function placeBets(uint256[] calldata ticketMasks, uint256[] calldata amounts) external nonReentrant onlyEnumerated {\n        if (state != State.Open) revert NotOpen();", "function placeBets(uint256[] calldata ticketMasks, uint256[] calldata amounts) external nonReentrant onlyEnumerated {"),
    ("freeform-bet-after-final", WAGER, "function placeBet(string calldata answer, uint256 amount) external nonReentrant onlyFreeform {\n        if (state != State.Open) revert NotOpen();", "function placeBet(string calldata answer, uint256 amount) external nonReentrant onlyFreeform {"),
    # --- payoff policy logic ---
    ("exact-set-any-overlap", WAGER, "if (policy == PayoffPolicy.SINGLE_WINNER || policy == PayoffPolicy.EXACT_SET) {\n            return (T == W, overlap);", "if (policy == PayoffPolicy.SINGLE_WINNER || policy == PayoffPolicy.EXACT_SET) {\n            return (true, overlap);"),
    ("at-least-k-off-by-one", WAGER, "return (BitMath.popcount(overlap) >= policyParam, overlap);", "return (BitMath.popcount(overlap) > policyParam, overlap);"),
    ("weighted-units-unweighted", WAGER, "units += pool * BitMath.popcount(overlap);", "units += pool;"),
    ("mask-range-unchecked", WAGER, "if (mask >> numOptions != 0) revert InvalidTicketMask();", ""),
    ("winning-mask-range-unchecked", WAGER, "if (W >> numOptions != 0) revert InvalidWinningMask();", ""),
    ("single-winner-multibit-ticket", WAGER, "if (policy == PayoffPolicy.SINGLE_WINNER && !BitMath.isSingleBit(mask)) revert InvalidTicketMask();", ""),
    ("single-winner-multibit-resolve", WAGER, "if (payoffPolicy == PayoffPolicy.SINGLE_WINNER && !BitMath.isSingleBit(W)) {\n            revert InvalidWinningMask();\n        }", ""),
    # --- ADR-0020 fixes ---
    ("C1-popcount-loop-is-back", BITMATH, "x -= (x >> 1) & 0x5555555555555555555555555555555555555555555555555555555555555555;", "uint256 c;\n            for (uint256 y = x; y != 0; y &= y - 1) c++;\n            if (c < 256) return c;\n            x -= (x >> 1) & 0x5555555555555555555555555555555555555555555555555555555555555555;"),
    ("C3-single-bit-not-exempt", WAGER, "if (!BitMath.isSingleBit(ticketMask) && _usedMasks.length >= MAX_DISTINCT_TICKETS) {", "if (_usedMasks.length >= MAX_DISTINCT_TICKETS) {"),
    ("C3-cap-removed", WAGER, "if (!BitMath.isSingleBit(ticketMask) && _usedMasks.length >= MAX_DISTINCT_TICKETS) {", "if (false) {"),
    ("C3-min-stake-enum-removed", WAGER, "if (amount < minNewTicketStake) revert NewTicketStakeTooLow();\n            if (!BitMath", "if (!BitMath"),
    ("C3-min-stake-free-removed", WAGER, "if (amount < minNewTicketStake) revert NewTicketStakeTooLow();\n            _usedAnswerIds.push(id);", "_usedAnswerIds.push(id);"),
    ("C3-min-stake-off-by-one", WAGER, "if (amount < minNewTicketStake) revert NewTicketStakeTooLow();\n            if (!BitMath", "if (amount <= minNewTicketStake && minNewTicketStake != 0) revert NewTicketStakeTooLow();\n            if (!BitMath"),
    ("C4-mulDiv-overflow-unchecked", FULLMATH, "if (denominator <= prod1) revert MulDivOverflow();", ""),
    ("C4-fees-plain-math", WAGER, "return FullMath.mulDiv(totalPot, totalFeeBps, BPS_DENOMINATOR);", "return (totalPot * totalFeeBps) / BPS_DENOMINATOR;"),
    ("C4-winner-plain-math", WAGER, "paid = FullMath.mulDiv(betsByAnswer[msg.sender][winningAnswerId], netPot, payoutDenominator);", "paid = (betsByAnswer[msg.sender][winningAnswerId] * netPot) / payoutDenominator;"),
    ("C5-no-reveal-event", WAGER, "emit FreeformAnswerRevealedV3(id, answer);", ""),
    ("C5-reveal-every-bet", WAGER, "        betsByAnswer[bettor][id] += amount;", "        emit FreeformAnswerRevealedV3(id, answer);\n        betsByAnswer[bettor][id] += amount;"),
    # --- factory ---
    ("factory-window-min", FACTORY, "if (bettingCloseTime != 0 && bettingCloseTime < nowTs + minBettingWindow) revert WindowTooShort();", ""),
    ("factory-res-window-min", FACTORY, "if (resolutionWindow != 0 && resolutionWindow < minResolutionWindow) revert WindowTooShort();", ""),
    ("factory-no-betting-closer", FACTORY, "if (bettingCloseTime == 0 && bettingCloser == address(0)) revert InvalidLifecycleConfig();", ""),
    ("factory-no-resolution-closer", FACTORY, "if (resolutionWindow == 0 && resolutionCloser == address(0)) revert InvalidLifecycleConfig();", ""),
    ("factory-fee-cap", FACTORY, "if (totalFeeBps > MAX_TOTAL_FEE_BPS) revert BadFeeConfig();", ""),
    ("factory-zero-recipient", FACTORY, "if (extraRecipients[i] == address(0)) revert BadFeeConfig();", ""),
    ("factory-zero-bps", FACTORY, "if (extraBps[i] == 0) revert BadFeeConfig();", ""),
    ("factory-recipient-cap", FACTORY, "if (extraRecipients.length > MAX_EXTRA_FEE_RECIPIENTS) revert BadFeeConfig();", ""),
    ("factory-treasury-slot", FACTORY, "feeRecipients[idx] = treasury;", "feeRecipients[idx] = msg.sender;"),
    ("factory-zero-treasury", FACTORY, 'require(treasury_ != address(0), "TREASURY");', ""),
    ("factory-default-resolver-enum", FACTORY, "address resolvedResolver = a.resolver == address(0) ? msg.sender : a.resolver;", "address resolvedResolver = a.resolver;"),
    ("factory-default-resolver-free", FACTORY, "address resolvedResolver = resolver == address(0) ? msg.sender : resolver;", "address resolvedResolver = resolver;"),
    ("factory-seed-mask-range", FACTORY, "if (mask >> numOptions_ != 0) revert BadSeedConfig();", ""),
    # --- wager constructor defence in depth ---
    ("ctor-fee-cap", WAGER, "if (sum > BPS_DENOMINATOR) revert FeeTooHigh();", ""),
    ("ctor-outcome-cap", WAGER, 'require(p.outcomes.length <= 255, "OUTCOMES_MAX");', ""),
]

# Gas snapshots and the slow stateful suite are left out: neither is needed to detect a weakened guard
# and both would multiply run time. Invariants are exercised by the fast suite.
TEST_FILES_EXCLUDED = ("ParamutuelV3Gas.t.sol", "ParamutuelV3Invariant.t.sol")
TEST_COMMAND = ["forge", "test", "--no-match-test", "test_C6_"]
TEST_ENV = {**os.environ, "FOUNDRY_OPTIMIZER": "false"}


def run_tests(workdir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(TEST_COMMAND, cwd=workdir, capture_output=True, text=True, env=TEST_ENV)


def run_mutation(workdir: Path, rel_path: str, old: str, new: str) -> tuple[str, str]:
    """Apply one mutation, run the suite, restore. Returns (outcome, detail)."""
    path = workdir / rel_path
    original = path.read_text(encoding="utf-8")
    count = original.count(old)
    if count != 1:
        return "STALE", f"pattern occurs {count} times"
    path.write_text(original.replace(old, new), encoding="utf-8")
    try:
        proc = run_tests(workdir)
    finally:
        path.write_text(original, encoding="utf-8")
    out = proc.stdout + proc.stderr
    if "Compiler run failed" in out or "Error (" in out:
        return "COMPILE-ERROR", out.strip().splitlines()[-1][:160]
    if proc.returncode == 0:
        return "SURVIVED", ""
    failed = [line for line in out.splitlines() if line.startswith("[FAIL")]
    return "KILLED", f"{len(set(failed))} failing; first: {failed[0][:110] if failed else '?'}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", default="", help="run only mutations whose id contains this text")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args(argv)
    selected = [m for m in MUTATIONS if args.only in m[0]]
    if args.list:
        for m in selected:
            print(m[0])
        return 0

    bad = 0
    with tempfile.TemporaryDirectory(prefix="paramutuel-mutation-") as tmp:
        work = Path(tmp)
        shutil.copytree(ROOT / "src", work / "src")
        shutil.copytree(ROOT / "test", work / "test", ignore=shutil.ignore_patterns("testnet", "integration", *TEST_FILES_EXCLUDED))
        shutil.copytree(ROOT / "lib", work / "lib", ignore=shutil.ignore_patterns(".git"))
        for name in ("foundry.toml", "foundry.lock"):
            shutil.copy(ROOT / name, work / name)
        start = time.time()
        baseline = run_tests(work)
        if baseline.returncode != 0:
            print("Baseline suite fails without any mutation; results would be meaningless:", file=sys.stderr)
            print((baseline.stdout + baseline.stderr)[-2000:], file=sys.stderr)
            return 1
        print(f"baseline passes ({int(time.time() - start)}s)", flush=True)
        for i, (mid, rel, old, new) in enumerate(selected, 1):
            outcome, detail = run_mutation(work, rel, old, new)
            elapsed = int(time.time() - start)
            print(f"[{i}/{len(selected)} {elapsed}s] {outcome:13} {mid}  {detail}", flush=True)
            if outcome != "KILLED":
                bad += 1
    print(f"\n{len(selected) - bad}/{len(selected)} killed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
