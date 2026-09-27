// ADR-0019 regression: every contract method the dApp invokes must exist in
// the committed V3 ABI.
//
// Why this exists: `app.js` is browser-only (no unit harness), and ethers v6
// resolves `contract.foo(...)` dynamically — a method name that is absent
// from the ABI is only discovered at click-time as a TypeError. The V2 → V3
// migration left `wagerContract.ticketPoolTotal(mask)` behind (V3 renamed the
// getter to `ticketPoolByMask`), which silently broke every enumerated odds
// preview ("Could not compute odds preview"). This test statically scans the
// call sites and the lifecycle action table so that class of drift fails CI.

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const DAPP = path.join(__dirname, "..");
const REPO = path.join(DAPP, "..");

function abiFunctionNames(file) {
  const abi = JSON.parse(fs.readFileSync(file, "utf8")).abi;
  return new Set(abi.filter((e) => e.type === "function").map((e) => e.name));
}

const wagerFns = abiFunctionNames(path.join(DAPP, "abi", "ParamutuelWagerV3.json"));
const factoryFns = abiFunctionNames(path.join(DAPP, "abi", "ParamutuelFactoryV3.json"));

// ethers.Contract members that are not ABI functions.
const ETHERS_MEMBERS = new Set(["interface", "target", "connect", "getFunction", "getAddress", "runner", "filters", "on", "queryFilter", "waitForDeployment"]);

/** Collect `<receiver>.<name>(` call names from a JS source. */
function calledMethods(src, receivers) {
  const re = new RegExp(`\\b(?:${receivers.join("|")})\\.([A-Za-z_][A-Za-z0-9_]*)\\s*\\(`, "g");
  const names = new Set();
  let m;
  while ((m = re.exec(src)) !== null) {
    if (!ETHERS_MEMBERS.has(m[1])) names.add(m[1]);
  }
  return names;
}

test("every wager method called by dapp/app.js exists in the V3 wager ABI", () => {
  const src = fs.readFileSync(path.join(DAPP, "app.js"), "utf8");
  const called = calledMethods(src, ["wagerContract", "modeProbe"]);
  assert.ok(called.size > 5, "scanner found suspiciously few call sites");
  const missing = [...called].filter((n) => !wagerFns.has(n));
  assert.deepEqual(missing, [], `app.js calls wager methods absent from the ABI: ${missing.join(", ")}`);
});

test("every factory method called by dapp/app.js exists in the V3 factory ABI", () => {
  const src = fs.readFileSync(path.join(DAPP, "app.js"), "utf8");
  const called = calledMethods(src, ["factory"]);
  assert.ok(called.has("createEnumeratedWager") && called.has("createFreeformWager"));
  const missing = [...called].filter((n) => !factoryFns.has(n));
  assert.deepEqual(missing, [], `app.js calls factory methods absent from the ABI: ${missing.join(", ")}`);
});

test("every lifecycle action in WAGER_ACTION_CONFIG maps to a V3 wager function", () => {
  const { WAGER_ACTION_CONFIG } = require("../logic.js");
  for (const [action, cfg] of Object.entries(WAGER_ACTION_CONFIG)) {
    assert.ok(wagerFns.has(cfg.method), `${action} -> ${cfg.method} not in ABI`);
  }
});

test("committed dapp ABIs match the compiled contracts when out/ is present", (t) => {
  const pairs = [
    ["ParamutuelWagerV3", wagerFns],
    ["ParamutuelFactoryV3", factoryFns],
  ];
  for (const [name, committed] of pairs) {
    const built = path.join(REPO, "out", `${name}.sol`, `${name}.json`);
    if (!fs.existsSync(built)) {
      t.skip("out/ not built (run forge build); committed ABI is the source of truth");
      return;
    }
    assert.deepEqual([...abiFunctionNames(built)].sort(), [...committed].sort(), `${name} ABI drifted; run script/sync-abi.sh`);
  }
});
