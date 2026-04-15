/**
 * TDD for site/propose-templates.js (Propose a Wager / Resonance Exchange).
 * Run: node --test site/tests/propose-templates.test.cjs
 */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("path");

const scriptPath = path.join(__dirname, "..", "propose-templates.js");
require(scriptPath);

test("propose-templates module loads", () => {
  assert.ok(globalThis.ParamutuelProposeTemplates, "sets globalThis.ParamutuelProposeTemplates");
  assert.ok(typeof globalThis.ParamutuelProposeTemplates.getResolvedTemplate === "function");
});

test("yesno: enumerated, two outcomes, placeholder by profile", () => {
  const { getResolvedTemplate } = globalThis.ParamutuelProposeTemplates;
  const d = getResolvedTemplate("yesno", "default");
  assert.equal(d.freeform, false);
  assert.deepEqual(d.outcomes, ["Yes", "No"]);
  assert.ok(d.placeholderProposition.length > 40);
  const r = getResolvedTemplate("yesno", "resonance");
  assert.notEqual(r.placeholderProposition, d.placeholderProposition);
  assert.deepEqual(r.outcomes, d.outcomes);
});

test("pick: at least three outcomes, same structure as dApp single-winner enumerated", () => {
  const { getResolvedTemplate } = globalThis.ParamutuelProposeTemplates;
  const d = getResolvedTemplate("pick", "default");
  assert.equal(d.freeform, false);
  assert.ok(d.outcomes.length >= 3);
});

test("timed: longer windows than yesno; distinct from pick", () => {
  const { getResolvedTemplate } = globalThis.ParamutuelProposeTemplates;
  const y = getResolvedTemplate("yesno", "default");
  const t = getResolvedTemplate("timed", "default");
  assert.equal(t.freeform, false);
  assert.ok(t.bettingClose > y.bettingClose, "timed betting window should be longer than yesno");
  assert.ok(t.outcomes.length >= 3, "timed should include multiple result buckets");
  assert.notDeepEqual(t.outcomes, getResolvedTemplate("pick", "default").outcomes);
});

test("freeform: empty outcomes, longer resolve than yesno default", () => {
  const { getResolvedTemplate } = globalThis.ParamutuelProposeTemplates;
  const f = getResolvedTemplate("freeform", "default");
  assert.equal(f.freeform, true);
  assert.deepEqual(f.outcomes, []);
  assert.ok(f.resolution >= 24 * 60 * 60);
});

test("unknown template id throws", () => {
  const { getResolvedTemplate } = globalThis.ParamutuelProposeTemplates;
  assert.throws(() => getResolvedTemplate("nope", "default"), /Unknown propose template/);
});

test("unknown profile falls back to default placeholder", () => {
  const { getResolvedTemplate } = globalThis.ParamutuelProposeTemplates;
  const a = getResolvedTemplate("yesno", "default");
  const b = getResolvedTemplate("yesno", "does-not-exist");
  assert.equal(b.placeholderProposition, a.placeholderProposition);
});

test("listTemplateIds lists four public templates", () => {
  const { listTemplateIds } = globalThis.ParamutuelProposeTemplates;
  assert.deepEqual(listTemplateIds().sort(), ["freeform", "pick", "timed", "yesno"]);
});
