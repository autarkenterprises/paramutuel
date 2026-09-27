/**
 * Pure decision helpers for the public staking page (`bet-page.js`).
 *
 * Extracted under ADR-0019 so the two decisions the page gets wrong most
 * easily are unit-tested (`dapp/tests/site-bet-logic.test.js`, run by
 * `script/test-fast.sh`). UMD-style like `dapp/logic.js`: in the browser it
 * attaches `globalThis.ParamutuelBetLogic`; under node it is `require`-able.
 * No DOM, no ethers, no network.
 */
(function (root) {
  "use strict";

  /** `ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER` wire value. */
  const PAYOFF_POLICY_SINGLE_WINNER = 0;

  function truthyFlag(v) {
    return v === true || v === 1 || v === "1" || v === "true";
  }

  /**
   * Mirror of the contract's `placeBet` gates, from an indexer wager row.
   *
   * The indexer's `state` stays `OPEN` after betting closes (V3 has no
   * separate "betting closed" state), so `state === "OPEN"` alone is not
   * enough. Contract: betting is closed iff `bettingClosedByAuthority` or
   * (`bettingCloseTime != 0` and `block.timestamp >= bettingCloseTime`).
   *
   * @param {object} w indexer row: state, betting_close_time, betting_closed_by_authority
   * @param {number} nowSec unix seconds (the wall clock approximates block time)
   * @returns {{open: boolean, reason: string}}
   */
  function bettingOpenStatus(w, nowSec) {
    const state = String((w && w.state) || "").toUpperCase();
    if (state !== "OPEN") {
      return { open: false, reason: `Wager is ${state || "not open"} — staking is closed.` };
    }
    if (truthyFlag(w.betting_closed_by_authority)) {
      return { open: false, reason: "Betting was closed by the betting closer — staking is closed." };
    }
    const close = Number(w.betting_close_time || 0);
    if (close > 0 && nowSec >= close) {
      return { open: false, reason: "Betting close time has passed — staking is closed; awaiting resolution." };
    }
    return { open: true, reason: "" };
  }

  /**
   * Whether "netPot / stake on outcome i" is the true if-this-wins multiple.
   * True only for SINGLE_WINNER: every other policy divides by the
   * resolver-dependent winning-units total (see docs/PAYOUT-CALCULATION.md
   * Part B), so a per-outcome multiple would misstate the payout.
   * Unknown policy returns false (never claim accuracy we cannot verify).
   */
  function perOutcomeMultipleSupported(policy) {
    if (policy === null || policy === undefined || policy === "") return false;
    return Number(policy) === PAYOFF_POLICY_SINGLE_WINNER;
  }

  const api = { PAYOFF_POLICY_SINGLE_WINNER, bettingOpenStatus, perOutcomeMultipleSupported };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.ParamutuelBetLogic = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this);
