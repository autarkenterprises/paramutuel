/**
 * ADR-0018's allowlist decides which tokens the site presents as vetted, so a typo in it misleads people
 * about money. This checks its shape against the deployments config. It cannot check that each address
 * really is the named token, which needs a network: that remains an operator check (ADR-0018 AAR).
 */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { ethers } = require("ethers");

const CONFIG = path.join(__dirname, "..", "..", "config");
const allowlist = JSON.parse(fs.readFileSync(path.join(CONFIG, "collateral-allowlist.json"), "utf8"));
const deployments = JSON.parse(fs.readFileSync(path.join(CONFIG, "deployments.json"), "utf8"));

test("every network in the allowlist is a deployment network on the same chain", () => {
  const networks = Object.keys(allowlist).filter((k) => !k.startsWith("_") && k !== "schemaVersion");
  assert.ok(networks.includes("baseSepolia"));
  for (const key of networks) {
    assert.ok(deployments[key], `${key} is not in deployments.json`);
    assert.equal(allowlist[key].chainId, deployments[key].chainId, `${key} chainId differs from deployments.json`);
  }
});

test("every token entry is well formed", () => {
  for (const [key, net] of Object.entries(allowlist)) {
    if (key.startsWith("_") || key === "schemaVersion") continue;
    const seen = new Set();
    for (const t of net.tokens) {
      const where = `${key} ${t.symbol}`;
      // A checksum error means the address was retyped by hand somewhere along the way.
      assert.equal(ethers.getAddress(t.address), t.address, `${where}: address is not in checksum form`);
      assert.ok(!seen.has(t.address.toLowerCase()), `${where}: listed twice`);
      seen.add(t.address.toLowerCase());
      assert.match(t.symbol, /^[A-Za-z0-9.]{1,11}$/, `${where}: symbol`);
      assert.ok(Number.isInteger(t.decimals) && t.decimals >= 0 && t.decimals <= 36, `${where}: decimals`);
      assert.ok([1, 2].includes(t.tier), `${where}: tier must be 1 or 2`);
      assert.equal(t.class, "standard", `${where}: only standard tokens are covered by the solvency guarantee`);
    }
  }
});
