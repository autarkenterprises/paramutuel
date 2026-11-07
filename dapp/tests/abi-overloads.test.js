/**
 * ethers v6 cannot choose between overloads of the same length by looking at the values: calling
 * `contract.placeBet(answer, amount)` throws "ambiguous function description". The V3 wager has two such
 * pairs, so until ADR-0020 the dApp could not place a single bet or resolve anything, and the bet page
 * could not take a freeform stake, in each case after the user had paid for an approve.
 *
 * No unit test noticed because everything else encodes by signature, and nothing ran these pages. The
 * browser test (test/integration/test_browser_e2e.py) now does; this keeps the fast suite honest too.
 */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { ethers } = require("ethers");
const { WAGER_ABI_FILES, CLIENT_SOURCES } = (() => {
  const root = path.join(__dirname, "..", "..");
  const siteDir = path.join(root, "site");
  return {
    WAGER_ABI_FILES: ["ParamutuelWagerV3.json", "ParamutuelFactoryV3.json"].map((f) => path.join(__dirname, "..", "abi", f)),
    CLIENT_SOURCES: [
      path.join(__dirname, "..", "app.js"),
      ...fs.readdirSync(siteDir).filter((f) => f.endsWith(".js")).map((f) => path.join(siteDir, f)),
    ],
  };
})();

function ambiguousNames() {
  const names = new Set();
  for (const file of WAGER_ABI_FILES) {
    const byName = {};
    for (const item of JSON.parse(fs.readFileSync(file, "utf8")).abi) {
      if (item.type === "function") (byName[item.name] ||= []).push(item.inputs.length);
    }
    for (const [name, lengths] of Object.entries(byName)) {
      if (new Set(lengths).size < lengths.length) names.add(name);
    }
  }
  return [...names];
}

function strippedSource(file) {
  return fs.readFileSync(file, "utf8").replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

test("the premise: ethers really does refuse a bare call to these functions", () => {
  const wager = new ethers.Interface(JSON.parse(fs.readFileSync(WAGER_ABI_FILES[0], "utf8")).abi);
  assert.throws(() => wager.getFunction("placeBet", ["Paris", 1n]), /ambiguous/);
  assert.throws(() => wager.getFunction("resolve", [5n]), /ambiguous/);
  assert.deepEqual(ambiguousNames().sort(), ["placeBet", "resolve"]);
});

test("no client calls an ambiguous function by its bare name", () => {
  const offenders = [];
  for (const file of CLIENT_SOURCES) {
    const source = strippedSource(file);
    for (const name of ambiguousNames()) {
      const bare = new RegExp(`(?<!Promise)\\.${name}\\(`, "g");
      for (const match of source.matchAll(bare)) offenders.push(`${path.basename(file)}: ${match[0]}`);
    }
  }
  assert.deepEqual(offenders, []);
});

test("no client routes an ambiguous function through the generic action runner", () => {
  const source = strippedSource(path.join(__dirname, "..", "app.js"));
  const routed = [...source.matchAll(/runWagerAction\("(\w+)"/g)].map((m) => m[1]);
  assert.ok(routed.includes("claim"), "the scan is looking at the right calls");
  for (const name of ambiguousNames()) assert.ok(!routed.includes(name), `${name} goes through runWagerAction`);
});

test("every signature a client names exists in the ABI", () => {
  const wager = new ethers.Interface(JSON.parse(fs.readFileSync(WAGER_ABI_FILES[0], "utf8")).abi);
  const seen = new Set();
  for (const file of CLIENT_SOURCES) {
    for (const match of strippedSource(file).matchAll(/"((?:placeBet|resolve)\([a-z0-9,]*\))"/g)) seen.add(match[1]);
  }
  assert.deepEqual([...seen].sort(), [
    "placeBet(string,uint256)",
    "placeBet(uint256,uint256)",
    "resolve(string)",
    "resolve(uint256)",
  ]);
  for (const signature of seen) assert.equal(wager.getFunction(signature).format(), signature);
});
