const test = require("node:test");
const assert = require("node:assert/strict");

const {
  getTemplate,
  computeWindowArgs,
  validateWindowMins,
  parseMultiBetInputs,
  resolveTemplate,
  computeAbsoluteTemplateClose,
  planWagerAction,
  PAYOFF_POLICY,
  popcountMask,
  parseOutcomeIndicesCsvToTicketMask,
  seedOutcomeIndicesToTicketMasks,
  validatePolicyParamForCreate,
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

test("computeWindowArgs supports absolute resolution close with relative betting mode", () => {
  const args = computeWindowArgs(1000, 3600, 0, false, false, "relative", null, "absolute", 9600);
  assert.equal(args.closeTime, 4600);
  assert.equal(args.resolutionWindowArg, 5000);
});

test("computeWindowArgs supports absolute resolution close with absolute betting mode", () => {
  const args = computeWindowArgs(1000, 0, 0, false, false, "absolute", 5000, "absolute", 11000);
  assert.equal(args.closeTime, 5000);
  assert.equal(args.resolutionWindowArg, 6000);
});

test("computeWindowArgs rejects invalid absolute resolution close values", () => {
  assert.throws(
    () => computeWindowArgs(1000, 3600, 0, true, false, "relative", null, "absolute", 9000),
    /resolutionCloseAt requires a finite betting close time/
  );
  assert.throws(
    () => computeWindowArgs(1000, 3600, 0, false, false, "relative", null, "absolute", 4600),
    /resolutionCloseAt must be after betting close time/
  );
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

test("validateWindowMins enforces min resolution using computed absolute duration", () => {
  const absoluteComputedWindow = 1700;
  assert.throws(
    () => validateWindowMins(3600n, 1800n, 7200, absoluteComputedWindow, false, false),
    /minResolutionWindow/
  );
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

test("planWagerAction routes resolution actions to resolution wager", () => {
  const resolutionAddr = "0x1111111111111111111111111111111111111111";
  const claimsAddr = "0x2222222222222222222222222222222222222222";
  const activeAddr = "0x3333333333333333333333333333333333333333";
  const actions = ["closeBetting", "closeResolutionWindow", "resolve", "retract", "expire"];

  for (const action of actions) {
    const plan = planWagerAction(action, {
      resolutionWagerAddress: resolutionAddr,
      claimsWagerAddress: claimsAddr,
      activeWagerAddress: activeAddr,
    });
    assert.equal(plan.section, "resolution");
    assert.equal(plan.targetAddress, resolutionAddr);
  }
});

test("planWagerAction routes claims actions to claims wager", () => {
  const resolutionAddr = "0x1111111111111111111111111111111111111111";
  const claimsAddr = "0x2222222222222222222222222222222222222222";
  const activeAddr = "0x3333333333333333333333333333333333333333";
  const actions = ["claim", "withdrawFees"];

  for (const action of actions) {
    const plan = planWagerAction(action, {
      resolutionWagerAddress: resolutionAddr,
      claimsWagerAddress: claimsAddr,
      activeWagerAddress: activeAddr,
    });
    assert.equal(plan.section, "claims");
    assert.equal(plan.targetAddress, claimsAddr);
  }
});

test("planWagerAction falls back to active wager when section is empty", () => {
  const activeAddr = "0x3333333333333333333333333333333333333333";
  const plan = planWagerAction("resolve", {
    resolutionWagerAddress: "",
    claimsWagerAddress: "",
    activeWagerAddress: activeAddr,
  });
  assert.equal(plan.targetAddress, activeAddr);
  assert.equal(plan.method, "resolve");
});

test("planWagerAction enforces known actions and target presence", () => {
  assert.throws(() => planWagerAction("unknownAction", {}), /Unsupported action/);
  assert.throws(
    () => planWagerAction("claim", { resolutionWagerAddress: "", claimsWagerAddress: "", activeWagerAddress: "" }),
    /Select a wager address/
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

test("parseOutcomeIndicesCsvToTicketMask builds bitmask", () => {
  assert.equal(parseOutcomeIndicesCsvToTicketMask("0", 3), 1n);
  assert.equal(parseOutcomeIndicesCsvToTicketMask("0, 2", 3), 5n);
  assert.equal(parseOutcomeIndicesCsvToTicketMask("2", 5), 4n);
});

test("parseOutcomeIndicesCsvToTicketMask rejects invalid indices", () => {
  assert.throws(() => parseOutcomeIndicesCsvToTicketMask("", 3), /at least one/);
  assert.throws(() => parseOutcomeIndicesCsvToTicketMask("3", 3), /out of range/);
  assert.throws(() => parseOutcomeIndicesCsvToTicketMask("0,0", 3), /Duplicate/);
});

test("popcountMask counts bits", () => {
  assert.equal(popcountMask(0n), 0);
  assert.equal(popcountMask(5n), 2);
  assert.equal(popcountMask(7n), 3);
});

test("seedOutcomeIndicesToTicketMasks maps to single-bit masks", () => {
  assert.deepEqual(seedOutcomeIndicesToTicketMasks([0, 2]), [1n, 4n]);
});

test("validatePolicyParamForCreate enforces AT_LEAST_K k", () => {
  validatePolicyParamForCreate(PAYOFF_POLICY.ANY_OF, 0, 3);
  validatePolicyParamForCreate(PAYOFF_POLICY.AT_LEAST_K, 2, 3);
  assert.throws(
    () => validatePolicyParamForCreate(PAYOFF_POLICY.AT_LEAST_K, 0, 3),
    /AT_LEAST_K requires k/
  );
  assert.throws(
    () => validatePolicyParamForCreate(PAYOFF_POLICY.ANY_OF, 1, 3),
    /must be 0/
  );
});
