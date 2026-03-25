const test = require("node:test");
const assert = require("node:assert/strict");

const { getTemplate, computeWindowArgs, validateWindowMins } = require("../logic.js");

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
