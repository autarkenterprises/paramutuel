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

// ---------------------------------------------------------------------------
// ADR-0020 regressions
// ---------------------------------------------------------------------------

const fs = require("node:fs");
const path = require("node:path");
const BetLogic = require("../../site/bet-logic.js");
const DappLogic = require("../logic.js");

const WAGER_ROW = { state: "OPEN", betting_close_time: NOW + 3600, betting_closed_by_authority: 0 };

// W3: amounts went through Number(), so 0.0000001 became "1e-7" and parseUnits threw, and large
// values silently lost precision. The dApp and the site must agree, so both run the same cases.
for (const [name, parse] of [["site", BetLogic.parseHumanAmount], ["dApp", DappLogic.parseHumanAmount]]) {
  test(`${name}: parseHumanAmount keeps the exact digits the user typed`, () => {
    assert.equal(parse("10"), "10");
    assert.equal(parse(" 2.5 "), "2.5");
    assert.equal(parse("0.0000001"), "0.0000001");
    assert.equal(parse("123456789012345678901234567890.123456789012345678"), "123456789012345678901234567890.123456789012345678");
    assert.equal(parse(".5"), "0.5");
    assert.equal(parse("5."), "5");
  });

  test(`${name}: parseHumanAmount rejects what parseUnits would misread`, () => {
    for (const bad of ["", "   ", "0", "0.00", "-1", "1e5", "1e-7", "abc", "1,5", "1.2.3", "0x10", "Infinity", "NaN"]) {
      assert.throws(() => parse(bad), /amount/i, `should reject ${JSON.stringify(bad)}`);
    }
  });
}

test("dApp parseMultiBetInputs returns exact amount strings", () => {
  const parsed = DappLogic.parseMultiBetInputs("0,1", "0.0000001,123456789012345678901", false);
  assert.deepEqual(parsed.amountStrings, ["0.0000001", "123456789012345678901"]);
});

// W6: after an early close the real deadline is earlier than the immutable resolutionDeadline.
test("effective deadline is anchored on the authority close when betting closed early", () => {
  const w = { betting_close_time: 5000, resolution_window: 100, resolution_deadline: 5100, betting_closed_at: 1000 };
  assert.equal(BetLogic.effectiveResolutionDeadline(w), 1100);
});

test("effective deadline falls back to the scheduled close", () => {
  assert.equal(BetLogic.effectiveResolutionDeadline({ betting_close_time: 5000, resolution_window: 100, betting_closed_at: null }), 5100);
});

test("effective deadline is 0 when no time bound applies or betting has no anchor yet", () => {
  assert.equal(BetLogic.effectiveResolutionDeadline({ betting_close_time: 5000, resolution_window: 0 }), 0);
  assert.equal(BetLogic.effectiveResolutionDeadline({ betting_close_time: 0, resolution_window: 100, betting_closed_at: null }), 0);
});

// W1, W2: the submit button is decided in one place.
test("staking is blocked while betting is closed even with a wallet connected", () => {
  const closed = { ...WAGER_ROW, betting_close_time: NOW - 1 };
  const reason = BetLogic.stakeBlockReason({ wager: closed, nowSec: NOW, walletConnected: true, decimalsKnown: true });
  assert.match(reason, /closed/i);
});

test("staking is blocked until token decimals are known", () => {
  const reason = BetLogic.stakeBlockReason({ wager: WAGER_ROW, nowSec: NOW, walletConnected: true, decimalsKnown: false });
  assert.match(reason, /decimals/i);
});

test("staking needs a wallet", () => {
  const reason = BetLogic.stakeBlockReason({ wager: WAGER_ROW, nowSec: NOW, walletConnected: false, decimalsKnown: false });
  assert.match(reason, /wallet/i);
});

test("staking is allowed once open, connected, and decimals are known", () => {
  assert.equal(BetLogic.stakeBlockReason({ wager: WAGER_ROW, nowSec: NOW, walletConnected: true, decimalsKnown: true }), "");
});

test("bet-page.js sets the submit button in one place only, through stakeBlockReason", () => {
  // The page is DOM-bound with no harness. connectWallet once recomputed `disabled` from the raw state
  // string, silently undoing the ADR-0019 fix in the normal flow of loading a page and then connecting.
  const src = fs.readFileSync(path.join(__dirname, "..", "..", "site", "bet-page.js"), "utf8");
  const writes = src.match(/betSubmitBtn"\)\.disabled\s*=/g) || [];
  assert.equal(writes.length, 1, "exactly one writer of the submit button's disabled state");
  assert.ok(src.includes("BetLogic.stakeBlockReason("), "the one writer must use the tested decision");
  assert.ok(!/st !== "OPEN"/.test(src), "must not derive staking from the raw state string");
});

test("bet-page.js parses amounts as text, never through Number", () => {
  const src = fs.readFileSync(path.join(__dirname, "..", "..", "site", "bet-page.js"), "utf8");
  assert.ok(src.includes("BetLogic.parseHumanAmount("));
  assert.ok(!/parseAmountHuman\(n,/.test(src));
});

test("dApp resolve path does not trim the winning answer", () => {
  const src = fs.readFileSync(path.join(__dirname, "..", "app.js"), "utf8");
  const start = src.indexOf("async function resolveWager()");
  const body = src.slice(start, src.indexOf("async function retractWager()"));
  assert.ok(start > 0);
  assert.ok(!/winningOutcomeIndex"\)\.value\.trim\(\)\s*;\s*\n\s*if \(!ans\)/.test(body), "freeform answer must be byte-exact");
  assert.ok(/const ans = \$\("winningOutcomeIndex"\)\.value;/.test(body));
});

// W10: a token's self-reported symbol is attacker-controlled: a fake token can say "USDC".
const ALLOWLIST = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "..", "config", "collateral-allowlist.json"), "utf8"));
const USDC_SEPOLIA = "0x036CbD53842c5426634e7929541eC2318f3dCF7e";

test("allowlisted collateral is recognised regardless of address case", () => {
  const trust = BetLogic.collateralTrust(ALLOWLIST, "baseSepolia", USDC_SEPOLIA.toLowerCase());
  assert.equal(trust.listed, true);
  assert.equal(trust.symbol, "USDC");
  assert.equal(trust.tier, 1);
});

test("an unlisted token is flagged, and is not given the name it claims", () => {
  const trust = BetLogic.collateralTrust(ALLOWLIST, "baseSepolia", "0x" + "ab".repeat(20));
  assert.equal(trust.listed, false);
  assert.match(trust.warning, /not on the curated list/i);
  assert.match(trust.warning, /fee-on-transfer/i);
  assert.equal(trust.symbol, null, "never trust the token's own symbol()");
});

test("a listed token on another network is not listed here", () => {
  assert.equal(BetLogic.collateralTrust(ALLOWLIST, "baseMainnet", USDC_SEPOLIA).listed, false);
});

test("a missing allowlist degrades to unknown rather than a false assurance", () => {
  const trust = BetLogic.collateralTrust(null, "baseSepolia", USDC_SEPOLIA);
  assert.equal(trust.listed, false);
  assert.equal(trust.warning, "");
  assert.equal(trust.unknown, true);
});

test("the allowlist is well formed for every network", () => {
  for (const key of ["baseSepolia", "baseMainnet"]) {
    const net = ALLOWLIST[key];
    assert.ok(net.tokens.length > 0, key);
    for (const t of net.tokens) {
      assert.match(t.address, /^0x[0-9a-fA-F]{40}$/);
      assert.ok(t.symbol);
      assert.ok(Number.isInteger(t.decimals));
      assert.ok([1, 2].includes(t.tier));
      assert.ok(["standard", "fee-on-transfer", "rebasing", "unknown"].includes(t.class));
    }
  }
  const deployments = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "..", "config", "deployments.json"), "utf8"));
  assert.equal(ALLOWLIST.baseSepolia.chainId, deployments.baseSepolia.chainId);
  assert.equal(ALLOWLIST.baseMainnet.chainId, deployments.baseMainnet.chainId);
});

// W11: with no time limit, a closer's key is the only way forward.
test("no warnings for a fully time-bounded wager with no closer dependence", () => {
  assert.deepEqual(BetLogic.livenessWarnings({ betting_close_time: 100, resolution_window: 100 }), []);
});

test("a no-time-limit betting window warns that stakes depend on the closer's key", () => {
  const warnings = BetLogic.livenessWarnings({ betting_close_time: 0, resolution_window: 100, betting_closed_by_authority: 0 });
  assert.equal(warnings.length, 1);
  assert.match(warnings[0], /betting closer/i);
  assert.match(warnings[0], /locked/i);
});

test("the warning goes away once the closer has acted", () => {
  assert.deepEqual(BetLogic.livenessWarnings({ betting_close_time: 0, resolution_window: 100, betting_closed_by_authority: 1 }), []);
});

test("a no-time-limit resolution window warns too", () => {
  const warnings = BetLogic.livenessWarnings({ betting_close_time: 100, resolution_window: 0 });
  assert.equal(warnings.length, 1);
  assert.match(warnings[0], /resolver/i);
});

// C3: a bet below the minimum would pay for an approve and then revert.
test("below-minimum check only applies when opening a new ticket", () => {
  assert.equal(BetLogic.belowMinNewTicketStake({ minStake: 100n, poolTotal: 0n, amount: 99n }), true);
  assert.equal(BetLogic.belowMinNewTicketStake({ minStake: 100n, poolTotal: 0n, amount: 100n }), false);
  assert.equal(BetLogic.belowMinNewTicketStake({ minStake: 100n, poolTotal: 5n, amount: 1n }), false);
  assert.equal(BetLogic.belowMinNewTicketStake({ minStake: 0n, poolTotal: 0n, amount: 1n }), false);
});

// C5: whitespace in an answer is invisible, but it is a different pool.
test("answers with edge whitespace or no readable text are flagged", () => {
  assert.equal(BetLogic.answerNote("Paris"), "");
  assert.match(BetLogic.answerNote("Paris "), /space/i);
  assert.match(BetLogic.answerNote(" Paris"), /space/i);
  assert.match(BetLogic.answerNote(null), /not valid UTF-8/i);
});
