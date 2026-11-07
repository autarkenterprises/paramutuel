// ADR-0020 D1: the hosted propose flow was dead for months because the deploy workflow's hard-coded
// copy list omitted two scripts. Nothing noticed, since every page still returned 200 and the local
// tree was complete. This test assembles the real artifact with the same script CI uses, and checks
// every local reference against what actually shipped.
//
// ADR-0020 D7: every wallet-connected page loads ethers from a CDN, so a compromised CDN could rewrite
// transactions. Subresource integrity makes the browser refuse altered bytes.

const test = require("node:test");
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const REPO = path.join(__dirname, "..", "..");

const artifact = fs.mkdtempSync(path.join(os.tmpdir(), "paramutuel-site-"));
execFileSync("bash", [path.join(REPO, "script", "assemble-site.sh"), artifact]);
test.after(() => fs.rmSync(artifact, { recursive: true, force: true }));

function walk(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    return entry.isDirectory() ? walk(full) : [full];
  });
}

const files = walk(artifact);
const pages = files.filter((f) => f.endsWith(".html"));
const scripts = files.filter((f) => f.endsWith(".js"));

/** Is this a same-site URL we can check on disk, rather than a link elsewhere or a template? */
function isLocal(url) {
  return !/^(https?:|mailto:|tel:|data:|#|\/\/|javascript:)/i.test(url) && !url.includes("${");
}

function assertShips(fromFile, url) {
  const clean = url.split(/[?#]/)[0];
  if (!clean) return;
  const target = path.resolve(path.dirname(fromFile), clean);
  const rel = path.relative(artifact, fromFile);
  assert.ok(fs.existsSync(target), `${rel} references ${url}, which is not in the deployed site`);
}

test("the artifact includes the pages the site is built around", () => {
  for (const page of ["index.html", "bet.html", "propose-a-wager.html", "resonance-propose.html", "dapp/index.html", "explorer/index.html"]) {
    assert.ok(fs.existsSync(path.join(artifact, page)), `${page} missing from artifact`);
  }
});

test("every script, stylesheet, frame and link a page references ships in the artifact", () => {
  let checked = 0;
  for (const page of pages) {
    const html = fs.readFileSync(page, "utf8");
    const refs = html.matchAll(/<(?:script|link|iframe|a|img)\b[^>]*?\s(?:src|href)="([^"]+)"/gi);
    for (const [, url] of refs) {
      if (!isLocal(url)) continue;
      assertShips(page, url);
      checked += 1;
    }
  }
  assert.ok(checked > 50, `scanner found suspiciously few references (${checked})`);
});

test("the propose pages load their scripts (the regression that took the flow down)", () => {
  for (const page of ["propose-a-wager.html", "resonance-propose.html"]) {
    const html = fs.readFileSync(path.join(artifact, page), "utf8");
    for (const script of ["propose-templates.js", "propose-wager.js"]) {
      assert.ok(html.includes(`src="${script}"`), `${page} no longer loads ${script}`);
      assert.ok(fs.existsSync(path.join(artifact, script)), `${script} does not ship`);
    }
  }
});

test("every config and ABI file a script fetches ships in the artifact", () => {
  let checked = 0;
  for (const script of scripts) {
    // Comments mention paths in prose; only code fetches them.
    const src = fs.readFileSync(script, "utf8").replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
    const refs = src.matchAll(/["'`]((?:\.\.\/)?(?:config|dapp\/abi|abi)\/[A-Za-z0-9._/-]+\.json)["'`]/g);
    for (const [, url] of refs) {
      assertShips(script, url);
      checked += 1;
    }
  }
  assert.ok(checked >= 5, `scanner found suspiciously few fetches (${checked})`);
});

test("every external script is pinned with subresource integrity", () => {
  let checked = 0;
  for (const page of pages) {
    const html = fs.readFileSync(page, "utf8");
    for (const [tag] of html.matchAll(/<script\b[^>]*\ssrc="https?:[^"]*"[^>]*>/gi)) {
      const rel = path.relative(artifact, page);
      assert.match(tag, /\sintegrity="sha(256|384|512)-[A-Za-z0-9+/=]+"/, `${rel}: ${tag} has no integrity hash`);
      assert.match(tag, /\scrossorigin="anonymous"/, `${rel}: ${tag} needs crossorigin="anonymous" for integrity to apply`);
      assert.match(tag, /@\d+\.\d+\.\d+\//, `${rel}: ${tag} must pin an exact version`);
      checked += 1;
    }
  }
  assert.ok(checked >= 5, `expected the wallet pages' ethers tags, found ${checked}`);
});

test("collateral allowlist ships with the site", () => {
  assert.ok(fs.existsSync(path.join(artifact, "config", "collateral-allowlist.json")));
});

test("the integrity hash on every page matches the ethers that the tests use", () => {
  // Tests used to run a newer ethers than the pages load, so they could pass on behaviour production
  // does not have. Pinning one version also verifies the hash here, with no network needed.
  const crypto = require("node:crypto");
  const dappDir = path.join(__dirname, "..");
  const pinned = JSON.parse(fs.readFileSync(path.join(dappDir, "package.json"), "utf8")).devDependencies.ethers;
  const bundle = fs.readFileSync(path.join(dappDir, "node_modules", "ethers", "dist", "ethers.umd.min.js"));
  const expected = `sha384-${crypto.createHash("sha384").update(bundle).digest("base64")}`;
  const pages = [
    path.join(dappDir, "index.html"),
    ...fs
      .readdirSync(path.join(dappDir, "..", "site"))
      .filter((f) => f.endsWith(".html"))
      .map((f) => path.join(dappDir, "..", "site", f)),
  ];
  let checked = 0;
  for (const page of pages) {
    for (const tag of fs.readFileSync(page, "utf8").match(/<script[^>]*ethers[^>]*>/g) || []) {
      assert.ok(tag.includes(`ethers@${pinned}/dist/ethers.umd.min.js`), `${page} loads a different ethers: ${tag}`);
      assert.ok(tag.includes(`integrity="${expected}"`), `${page} has the wrong integrity hash: ${tag}`);
      checked += 1;
    }
  }
  assert.equal(checked, 5, "the five wallet pages");
});
