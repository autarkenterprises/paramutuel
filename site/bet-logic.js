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

  /**
   * Validate a user-typed token amount and return it as text, ready for `ethers.parseUnits`.
   * Deliberately never goes through `Number`: that turned 0.0000001 into "1e-7", which parseUnits
   * rejects, and silently rounded large values, so the wallet would approve a different amount than
   * the one typed (ADR-0020).
   * @param {string} raw
   * @returns {string}
   */
  function parseHumanAmount(raw) {
    const text = String(raw == null ? "" : raw).trim();
    if (!/^(\d+\.?\d*|\.\d+)$/.test(text)) {
      throw new Error(`Invalid amount: ${JSON.stringify(text)}. Use plain digits, like 10 or 0.25.`);
    }
    const normalized = (text.startsWith(".") ? `0${text}` : text).replace(/\.$/, "");
    if (!/[1-9]/.test(normalized)) {
      throw new Error("Invalid amount: it must be greater than zero.");
    }
    return normalized;
  }

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

  /**
   * Whether a wager can take a stake from this user right now, and if not, why. The one source of the
   * submit button's state, so no code path can re-enable staking on its own.
   * @param {{wager: object, nowSec: number, walletConnected: boolean, decimalsKnown: boolean}} ctx
   * @returns {string} the reason staking is blocked, or "" when it is allowed
   */
  function stakeBlockReason({ wager, nowSec, walletConnected, decimalsKnown }) {
    const status = bettingOpenStatus(wager, nowSec);
    if (!status.open) return status.reason;
    if (!walletConnected) return "Connect your wallet to place a stake.";
    if (!decimalsKnown) {
      return "Token decimals are unknown, so a stake could be wrong by orders of magnitude. Enable manual decimals if the token cannot report them.";
    }
    return "";
  }

  /**
   * The moment the resolver's window really ends, in unix seconds, or 0 when no timer applies. The
   * contract's `resolutionDeadline` is computed at creation, so an early `closeBetting` makes it too
   * late: the window is anchored on when betting actually closed.
   */
  function effectiveResolutionDeadline(w) {
    const window = Number(w.resolution_window || 0);
    if (window <= 0) return 0;
    const closedAt = w.betting_closed_at != null ? Number(w.betting_closed_at) : Number(w.betting_close_time || 0);
    return closedAt > 0 ? closedAt + window : 0;
  }

  /**
   * What the curated list says about a collateral token (ADR-0018). `symbol` comes only from the list:
   * a token's own `symbol()` is attacker-controlled, so a fake token can claim to be USDC.
   * @param {object|null} allowlist parsed config/collateral-allowlist.json, or null if it failed to load
   * @param {string} networkKey e.g. "baseSepolia"
   * @param {string} address
   */
  function collateralTrust(allowlist, networkKey, address) {
    if (!allowlist) return { listed: false, unknown: true, symbol: null, tier: null, warning: "" };
    const wanted = String(address || "").toLowerCase();
    const tokens = (allowlist[networkKey] && allowlist[networkKey].tokens) || [];
    const hit = tokens.find((t) => String(t.address).toLowerCase() === wanted);
    if (hit) return { listed: true, unknown: false, symbol: hit.symbol, tier: hit.tier, warning: "" };
    return {
      listed: false,
      unknown: false,
      symbol: null,
      tier: null,
      warning:
        "This collateral token is not on the curated list. Its name may be misleading, and fee-on-transfer or rebasing tokens can leave the last claimants unpaid. Check the address before staking.",
    };
  }

  /**
   * Trust assumptions a bettor should see for wagers with no time limit. Anyone can `expire` a
   * time-bounded wager, but with a zero time the matching closer is the only way forward, and the
   * factory cannot check that its key still exists (ADR-0019 finding 5, ADR-0020 W11).
   */
  function livenessWarnings(w) {
    const warnings = [];
    if (Number(w.betting_close_time || 0) === 0 && !truthyFlag(w.betting_closed_by_authority)) {
      warnings.push(
        "No betting deadline: only the betting closer can end betting. If that key is lost, stakes are locked, because neither retract nor expire can run while betting is open."
      );
    }
    if (Number(w.resolution_window || 0) === 0 && !truthyFlag(w.resolution_window_closed)) {
      warnings.push(
        "No resolution deadline: only the resolver or the resolution closer can move this wager on. If both keys are lost, stakes are locked."
      );
    }
    return warnings;
  }

  /** A new ticket below the wager's minimum reverts, so catch it before the user pays for an approve. */
  function belowMinNewTicketStake({ minStake, poolTotal, amount }) {
    return minStake > 0n && poolTotal === 0n && amount < minStake;
  }

  /** Answers match byte-exactly, so differences a reader cannot see need calling out. */
  function answerNote(text) {
    if (text === null || text === undefined) return "Not valid UTF-8: shown by id only.";
    return text !== text.trim() ? "Has leading or trailing space, so it is a different answer from the same text without it." : "";
  }

  const api = {
    PAYOFF_POLICY_SINGLE_WINNER,
    answerNote,
    belowMinNewTicketStake,
    bettingOpenStatus,
    collateralTrust,
    effectiveResolutionDeadline,
    livenessWarnings,
    parseHumanAmount,
    perOutcomeMultipleSupported,
    stakeBlockReason,
  };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.ParamutuelBetLogic = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this);
