// ADR-0019 regression tests for the public staking page (`site/bet-page.js`).
//
// Two verified defects, pinned against the pure helpers in `site/bet-logic.js`
// (the page itself is DOM-bound and has no harness; the decisions it makes
// were extracted so they can be tested here, with the dApp's node runner):
//
// 1. The page enabled "Approve & place bets" whenever the indexer said
//    `state === "OPEN"`. V3 keeps `state == Open` after betting closes (by
//    time or by the betting closer) until resolve / retract / expire, so users
//    were offered a stake that `placeBet` rejects with `BettingClosed()`.
// 2. The odds table showed `netPot / stake(1<<i)` as the "if it wins"
//    multiple for every enumerated wager. That is the claim formula only for
//    SINGLE_WINNER; for ANY_OF / EXACT_SET / AT_LEAST_K / WEIGHTED_OVERLAP the
//    denominator is the resolver-dependent winning-units total (and multi-bit
//    tickets live in other masks), so the number was misleading.

const test = require("node:test");
const assert = require("node:assert/strict");

const { bettingOpenStatus, perOutcomeMultipleSupported, PAYOFF_POLICY_SINGLE_WINNER } = require("../../site/bet-logic.js");

const NOW = 1_700_000_000;

test("OPEN wager before its close time with no authority close is bettable", () => {
  const s = bettingOpenStatus({ state: "OPEN", betting_close_time: NOW + 60, betting_closed_by_authority: 0 }, NOW);
  assert.equal(s.open, true);
});

test("betting closes exactly at betting_close_time (contract: now >= close)", () => {
  const s = bettingOpenStatus({ state: "OPEN", betting_close_time: NOW, betting_closed_by_authority: 0 }, NOW);
  assert.equal(s.open, false);
  assert.match(s.reason, /closed/i);
});

test("authority close stops betting even before the timed close", () => {
  const s = bettingOpenStatus({ state: "OPEN", betting_close_time: NOW + 3600, betting_closed_by_authority: 1 }, NOW);
  assert.equal(s.open, false);
});

test("no-max betting window (close time 0) stays open until the authority closes it", () => {
  assert.equal(bettingOpenStatus({ state: "OPEN", betting_close_time: 0, betting_closed_by_authority: 0 }, NOW).open, true);
  assert.equal(bettingOpenStatus({ state: "OPEN", betting_close_time: "0", betting_closed_by_authority: "1" }, NOW).open, false);
});

test("terminal states are never bettable", () => {
  for (const state of ["RESOLVED", "RETRACTED"]) {
    assert.equal(bettingOpenStatus({ state, betting_close_time: NOW + 60 }, NOW).open, false);
  }
});

test("per-outcome multiples are only offered for SINGLE_WINNER enumerated wagers", () => {
  assert.equal(PAYOFF_POLICY_SINGLE_WINNER, 0);
  assert.equal(perOutcomeMultipleSupported(0), true);
  assert.equal(perOutcomeMultipleSupported("0"), true);
  for (const p of [1, 2, 3, 4, "3"]) assert.equal(perOutcomeMultipleSupported(p), false);
  // Unknown policy (indexer row missing the column) must not claim accuracy.
  assert.equal(perOutcomeMultipleSupported(null), false);
  assert.equal(perOutcomeMultipleSupported(undefined), false);
});
