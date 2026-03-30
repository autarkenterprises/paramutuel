const test = require("node:test");
const assert = require("node:assert/strict");

const {
  getTemplate,
  computeWindowArgs,
  validateWindowMins,
  parseMultiBetInputs,
  resolveTemplate,
  computeAbsoluteTemplateClose,
  planMarketAction,
} = require("../logic.js");

test("template lookup falls back to custom", () => {
  const t = getTemplate("does-not-exist");
  assert.equal(t.bettingCloseIn, 7200);
  assert.equal(t.resolutionWindow, 7200);
});

test("closer-only template enables no-max windows", () => {
  const t = getTemplate("closer-only");
  assert.equal(t.bettingNoMax, true);
  assert.equal(t.resolutionNoMax, true);
});

test("computeWindowArgs uses zero sentinels for no-max", () => {
  const args = computeWindowArgs(1000, 3600, 7200, true, true);
  assert.equal(args.closeTime, 0);
  assert.equal(args.resolutionWindowArg, 0);
});

test("computeWindowArgs computes close timestamp for finite windows", () => {
  const args = computeWindowArgs(1000, 3600, 7200, false, false);
  assert.equal(args.closeTime, 4600);
  assert.equal(args.resolutionWindowArg, 7200);
});

test("computeWindowArgs rejects invalid finite windows", () => {
  assert.throws(() => computeWindowArgs(1000, 0, 7200, false, false), /bettingCloseIn/);
  assert.throws(() => computeWindowArgs(1000, 3600, 0, false, false), /resolutionWindow/);
});

test("computeWindowArgs supports absolute betting close mode", () => {
  const args = computeWindowArgs(1000, 0, 7200, false, false, "absolute", 5000);
  assert.equal(args.closeTime, 5000);
  assert.equal(args.resolutionWindowArg, 7200);
});

test("computeWindowArgs rejects invalid absolute betting close values", () => {
  assert.throws(() => computeWindowArgs(1000, 0, 7200, false, false, "absolute", 1000), /bettingCloseAt/);
  assert.throws(
    () => computeWindowArgs(1000, 0, 7200, false, false, "absolute", Number.NaN),
    /bettingCloseAt/
  );
});

test("validateWindowMins warns for small betting window and throws for bad resolution window", () => {
  const warnings = validateWindowMins(3600n, 1800n, 1200, 7200, false, false);
  assert.equal(warnings.length, 1);
  assert.match(warnings[0], /minBettingWindow/);
  assert.throws(() => validateWindowMins(3600n, 1800n, 7200, 1200, false, false), /minResolutionWindow/);
});

test("validateWindowMins ignores min checks in no-max mode", () => {
  const warnings = validateWindowMins(3600n, 1800n, 1, 1, true, true);
  assert.deepEqual(warnings, []);
});

test("parseMultiBetInputs parses aligned indices and amounts", () => {
  const parsed = parseMultiBetInputs("0, 2,1", "1.5,3,4.25", false);
  assert.deepEqual(parsed.outcomeIndices, [0, 2, 1]);
  assert.deepEqual(parsed.amountNumbers, [1.5, 3, 4.25]);
});

test("parseMultiBetInputs allows empty when requested", () => {
  const parsed = parseMultiBetInputs("", "", true);
  assert.deepEqual(parsed.outcomeIndices, []);
  assert.deepEqual(parsed.amountNumbers, []);
});

test("parseMultiBetInputs rejects invalid input shapes", () => {
  assert.throws(() => parseMultiBetInputs("0,1", "1", false), /length mismatch/);
  assert.throws(() => parseMultiBetInputs("x", "1", false), /Invalid outcome index/);
  assert.throws(() => parseMultiBetInputs("0", "0", false), /Invalid amount/);
});

test("planMarketAction routes resolution actions to resolution market", () => {
  const resolutionAddr = "0x1111111111111111111111111111111111111111";
  const claimsAddr = "0x2222222222222222222222222222222222222222";
  const activeAddr = "0x3333333333333333333333333333333333333333";
  const actions = ["closeBetting", "closeResolutionWindow", "resolve", "retract", "expire"];

  for (const action of actions) {
    const plan = planMarketAction(action, {
      resolutionMarketAddress: resolutionAddr,
      claimsMarketAddress: claimsAddr,
      activeMarketAddress: activeAddr,
    });
    assert.equal(plan.section, "resolution");
    assert.equal(plan.targetAddress, resolutionAddr);
  }
});

test("planMarketAction routes claims actions to claims market", () => {
  const resolutionAddr = "0x1111111111111111111111111111111111111111";
  const claimsAddr = "0x2222222222222222222222222222222222222222";
  const activeAddr = "0x3333333333333333333333333333333333333333";
  const actions = ["claim", "withdrawFees"];

  for (const action of actions) {
    const plan = planMarketAction(action, {
      resolutionMarketAddress: resolutionAddr,
      claimsMarketAddress: claimsAddr,
      activeMarketAddress: activeAddr,
    });
    assert.equal(plan.section, "claims");
    assert.equal(plan.targetAddress, claimsAddr);
  }
});

test("planMarketAction falls back to active market when section is empty", () => {
  const activeAddr = "0x3333333333333333333333333333333333333333";
  const plan = planMarketAction("resolve", {
    resolutionMarketAddress: "",
    claimsMarketAddress: "",
    activeMarketAddress: activeAddr,
  });
  assert.equal(plan.targetAddress, activeAddr);
  assert.equal(plan.method, "resolve");
});

test("planMarketAction enforces known actions and target presence", () => {
  assert.throws(() => planMarketAction("unknownAction", {}), /Unsupported action/);
  assert.throws(
    () => planMarketAction("claim", { resolutionMarketAddress: "", claimsMarketAddress: "", activeMarketAddress: "" }),
    /Select a market address/
  );
});

test("resolveTemplate computes absolute close for daily UTC cutoff", () => {
  const nowSec = Date.UTC(2026, 2, 30, 12, 0, 0) / 1000;
  const t = resolveTemplate("daily-utc-cutoff", nowSec);
  assert.equal(t.bettingCloseMode, "absolute");
  assert.equal(t.bettingCloseAt, Date.UTC(2026, 2, 31, 0, 0, 0) / 1000);
  assert.equal(t.bettingCloseIn, 12 * 60 * 60);
});

test("resolveTemplate computes absolute close for weekly UTC cutoff", () => {
  const nowSec = Date.UTC(2026, 2, 30, 12, 0, 0) / 1000; // Monday
  const t = resolveTemplate("weekly-utc-cutoff", nowSec);
  assert.equal(t.bettingCloseMode, "absolute");
  assert.equal(t.bettingCloseAt, Date.UTC(2026, 3, 6, 0, 0, 0) / 1000);
});

test("computeAbsoluteTemplateClose rejects unknown rules", () => {
  assert.throws(() => computeAbsoluteTemplateClose(0, "unknown"), /Unknown absolute template rule/);
});
