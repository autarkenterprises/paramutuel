#!/usr/bin/env node
/**
 * Drives a real headless Chrome through the public pages, against a real local chain (ADR-0020).
 *
 * Unit tests cover the pure decisions in `bet-logic.js` and `logic.js`, but the wiring around them is
 * where the worst browser bugs here lived: a connect handler that re-enabled staking after betting
 * closed, a success message erased a moment after it appeared. Those need a real page to show up.
 *
 * Called by test_browser_e2e.py, which boots the stack and asserts on chain state:
 *     node driver.mjs <scenario> '<json config>'
 * Prints one JSON object on its last stdout line, and exits non-zero if a step fails.
 *
 * Talks to Chrome over the DevTools Protocol using Node's built-in WebSocket, so it needs no npm
 * packages. Two pieces stand in for the outside world:
 *
 *   - The wallet is a small EIP-1193 object that forwards to anvil, whose dev accounts are unlocked,
 *     so `eth_sendTransaction` produces real transactions. Everything above it is the page's own code
 *     and real ethers.
 *   - Requests leaving localhost are intercepted. The ethers CDN URL is answered with the identical file
 *     from npm, so the page's Subresource Integrity check runs for real and the test needs no network.
 *     Anything else external is blocked, so a page cannot quietly depend on a third party.
 */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const CDN_ETHERS = "https://cdn.jsdelivr.net/npm/ethers@6.13.5/dist/ethers.umd.min.js";
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** The injected wallet. `__switchAccount` plays the part of the user changing account in a wallet. */
function walletScript(account, rpc) {
  return `(() => {
    let current = ${JSON.stringify(account)};
    const listeners = {};
    window.ethereum = {
      on(event, fn) { (listeners[event] ||= []).push(fn); },
      removeListener(event, fn) { listeners[event] = (listeners[event] || []).filter((f) => f !== fn); },
      __switchAccount(next) { current = next; (listeners.accountsChanged || []).forEach((f) => f([next])); },
      async request({ method, params }) {
        if (method === "eth_requestAccounts" || method === "eth_accounts") return [current];
        const res = await fetch(${JSON.stringify(rpc)}, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params: params || [] }),
        });
        const out = await res.json();
        if (out.error) {
          const err = new Error(out.error.message);
          err.code = out.error.code;
          err.data = out.error.data;
          throw err;
        }
        return out.result;
      },
    };
  })();`;
}

class Browser {
  static async launch(cfg) {
    const profile = mkdtempSync(join(tmpdir(), "paramutuel-chrome-"));
    const proc = spawn(
      cfg.browser,
      [
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--no-first-run",
        "--remote-debugging-port=0",
        `--user-data-dir=${profile}`,
        "about:blank",
      ],
      { stdio: ["ignore", "ignore", "pipe"] }
    );
    const wsUrl = await new Promise((resolve, reject) => {
      let seen = "";
      const timer = setTimeout(() => reject(new Error(`Chrome did not start:\n${seen}`)), 30_000);
      proc.stderr.on("data", (chunk) => {
        seen += chunk;
        const match = seen.match(/DevTools listening on (ws:\/\/\S+)/);
        if (match) {
          clearTimeout(timer);
          resolve(match[1]);
        }
      });
      proc.on("exit", (code) => reject(new Error(`Chrome exited with ${code}:\n${seen}`)));
    });
    const browser = new Browser(cfg, proc, profile);
    await browser.connect(wsUrl);
    return browser;
  }

  constructor(cfg, proc, profile) {
    this.cfg = cfg;
    this.proc = proc;
    this.profile = profile;
    this.nextId = 1;
    this.pending = new Map();
    this.handlers = new Map();
    this.pages = [];
  }

  connect(url) {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(url);
      this.ws.addEventListener("open", resolve);
      this.ws.addEventListener("error", reject);
      this.ws.addEventListener("message", (ev) => this.onMessage(JSON.parse(ev.data)));
    });
  }

  onMessage(msg) {
    if (msg.id && this.pending.has(msg.id)) {
      const { resolve, reject, method } = this.pending.get(msg.id);
      this.pending.delete(msg.id);
      if (msg.error) reject(new Error(`${method}: ${msg.error.message}`));
      else resolve(msg.result);
      return;
    }
    (this.handlers.get(`${msg.sessionId}:${msg.method}`) || []).forEach((fn) => fn(msg.params));
  }

  send(method, params = {}, sessionId) {
    const id = this.nextId++;
    this.ws.send(JSON.stringify({ id, method, params, sessionId }));
    return new Promise((resolve, reject) => this.pending.set(id, { resolve, reject, method }));
  }

  on(sessionId, method, fn) {
    const key = `${sessionId}:${method}`;
    this.handlers.set(key, [...(this.handlers.get(key) || []), fn]);
  }

  /** Open `path` in a fresh tab. `account` of null means a browser with no wallet installed. */
  async page(path, account) {
    const { targetId } = await this.send("Target.createTarget", { url: "about:blank" });
    const { sessionId } = await this.send("Target.attachToTarget", { targetId, flatten: true });
    const page = new Page(this, sessionId);
    await page.init(account);
    this.pages.push(page);
    await page.goto(path);
    return page;
  }

  pageErrors() {
    return this.pages.flatMap((p) => p.errors);
  }

  async close() {
    this.proc.removeAllListeners("exit");
    const exited = new Promise((resolve) => this.proc.once("exit", resolve));
    // Ask politely, so its helper processes stop writing to the profile before it is removed.
    this.send("Browser.close").catch(() => {});
    const timer = setTimeout(() => this.proc.kill("SIGKILL"), 5_000);
    await exited;
    clearTimeout(timer);
    this.ws.close();
    try {
      rmSync(this.profile, { recursive: true, force: true, maxRetries: 10, retryDelay: 200 });
    } catch (err) {
      // A leftover temporary profile should not fail a test about something else.
      console.error(`Could not remove ${this.profile}: ${err.message}`);
    }
  }
}

class Page {
  constructor(browser, sessionId) {
    this.browser = browser;
    this.cfg = browser.cfg;
    this.sessionId = sessionId;
    /** Uncaught exceptions and console errors, including failed integrity checks. */
    this.errors = [];
    /** Local files that answered 400 or above, such as a script missing from the site. */
    this.localFailures = [];
  }

  send(method, params) {
    return this.browser.send(method, params, this.sessionId);
  }

  on(method, fn) {
    this.browser.on(this.sessionId, method, fn);
  }

  async init(account) {
    const ethersBody = readFileSync(this.cfg.ethersFile).toString("base64");
    this.on("Runtime.exceptionThrown", ({ exceptionDetails: d }) => {
      this.errors.push(`exception: ${d.exception?.description || d.text}`);
    });
    this.on("Runtime.consoleAPICalled", ({ type, args }) => {
      if (type === "error") this.errors.push(`console.error: ${args.map((a) => a.value ?? a.description).join(" ")}`);
    });
    this.on("Log.entryAdded", ({ entry }) => {
      // Blocked third-party requests are logged by source "network", and are deliberate.
      if (entry.level === "error" && entry.source !== "network") this.errors.push(`log: ${entry.text}`);
    });
    this.on("Network.responseReceived", ({ response }) => {
      const url = new URL(response.url);
      const local = url.hostname === "127.0.0.1" && url.port === new URL(this.cfg.site).port;
      if (local && response.status >= 400 && !url.pathname.endsWith("favicon.ico")) {
        this.localFailures.push(`${response.status} ${url.pathname}`);
      }
    });
    this.on("Fetch.requestPaused", ({ requestId, request }) => {
      let answer;
      if (new URL(request.url).hostname === "127.0.0.1") {
        answer = this.send("Fetch.continueRequest", { requestId });
      } else if (request.url === CDN_ETHERS) {
        answer = this.send("Fetch.fulfillRequest", {
          requestId,
          responseCode: 200,
          responseHeaders: [
            { name: "Content-Type", value: "application/javascript" },
            { name: "Access-Control-Allow-Origin", value: "*" },
          ],
          body: ethersBody,
        });
      } else {
        answer = this.send("Fetch.failRequest", { requestId, errorReason: "BlockedByClient" });
      }
      // A request can vanish while paused, when a page navigates away. Nothing is waiting on it then.
      answer.catch(() => {});
    });
    await Promise.all(["Page.enable", "Runtime.enable", "Log.enable", "Network.enable"].map((m) => this.send(m)));
    await this.send("Fetch.enable", { patterns: [{ urlPattern: "*" }] });
    if (account) {
      await this.send("Page.addScriptToEvaluateOnNewDocument", { source: walletScript(account, this.cfg.rpc) });
    }
  }

  async goto(path) {
    await this.send("Page.navigate", { url: `${this.cfg.site}/${path}` });
    await this.waitFor(`document.readyState === "complete" && location.href !== "about:blank"`, `load ${path}`);
  }

  async eval(expression) {
    const { result, exceptionDetails } = await this.send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
    });
    if (exceptionDetails) {
      throw new Error(`eval failed: ${exceptionDetails.exception?.description || exceptionDetails.text}\n${expression}`);
    }
    return result.value;
  }

  async waitFor(expression, label, timeoutMs = 60_000) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      if (await this.eval(`Boolean(${expression})`)) return;
      await sleep(100);
    }
    const body = await this.eval(`document.body ? document.body.innerText.slice(0, 2500) : "(no body)"`);
    throw new Error(`Timed out waiting for: ${label}\nExpression: ${expression}\nPage errors: ${this.errors.join(" | ")}\nPage text:\n${body}`);
  }

  el(selector) {
    return `document.querySelector(${JSON.stringify(selector)})`;
  }

  text(selector) {
    return this.eval(`${this.el(selector)}.textContent`);
  }

  value(selector) {
    return this.eval(`${this.el(selector)}.value`);
  }

  disabled(selector) {
    return this.eval(`${this.el(selector)}.disabled`);
  }

  visible(selector) {
    return this.eval(`(() => { const e = ${this.el(selector)}; return !!e && !e.hidden && e.getClientRects().length > 0; })()`);
  }

  /** Set a field the way typing does, with the events a page listens for. */
  async fill(selector, value) {
    await this.eval(`(() => {
      const e = ${this.el(selector)};
      e.value = ${JSON.stringify(value)};
      for (const type of ["input", "change", "blur"]) e.dispatchEvent(new Event(type, { bubbles: true }));
    })()`);
  }

  async check(selector, on = true) {
    await this.eval(`(() => {
      const e = ${this.el(selector)};
      e.checked = ${on};
      e.dispatchEvent(new Event("change", { bubbles: true }));
    })()`);
  }

  /** A real click: on a disabled button, as for a user, this does nothing. */
  async click(selector) {
    await this.eval(`${this.el(selector)}.click()`);
  }

  async waitForText(selector, fragment, timeoutMs) {
    await this.waitFor(
      `(${this.el(selector)}?.textContent || "").includes(${JSON.stringify(fragment)})`,
      `"${fragment}" in ${selector}`,
      timeoutMs
    );
  }

  async waitForVisible(selector, timeoutMs) {
    await this.waitFor(
      `(() => { const e = ${this.el(selector)}; return !!e && !e.hidden && e.getClientRects().length > 0; })()`,
      `${selector} visible`,
      timeoutMs
    );
  }

  async setText(selector, text) {
    await this.eval(`${this.el(selector)}.textContent = ${JSON.stringify(text)}`);
  }

  async switchAccount(account) {
    await this.eval(`window.ethereum.__switchAccount(${JSON.stringify(account)})`);
  }
}

// ---- Shared steps ----

async function waitForAddress(page, selector, address) {
  await page.waitFor(
    `(${page.el(selector)}?.textContent || "").toLowerCase() === ${JSON.stringify(address.toLowerCase())}`,
    `${selector} shows ${address}`
  );
}

async function connectBetPage(page, account) {
  await page.waitForVisible("#betSummary");
  await page.click("#betConnectBtn");
  await waitForAddress(page, "#betWalletAddr", account);
}

/** Submit a stake and wait for the page to report the outcome, starting from a blank status line. */
async function submitStake(page) {
  await page.setText("#betTxStatus", "");
  await page.click("#betSubmitBtn");
}

const SUCCESS = "placed successfully";

async function proposeReady(page) {
  await page.waitFor(`document.querySelectorAll("#proposeCollateral option").length > 0`, "collateral options");
  await page.waitFor(`document.querySelectorAll(".propose-outcome-input").length >= 2`, "template outcomes");
}

async function waitForProposed(page) {
  await page.waitForVisible("#proposeResult");
  return {
    wager: await page.eval(`document.querySelector("#proposeResult code").textContent`),
    link: await page.eval(`document.querySelector("#proposeResult a").getAttribute("href")`),
  };
}

// ---- Scenarios: each is the path a person takes through a page ----

const scenarios = {
  /** The project's first verb. Every refusal happens before any transaction. */
  async propose_enumerated(b, cfg) {
    const p = await b.page(cfg.page || "propose-a-wager.html", cfg.accounts.alice);
    await proposeReady(p);
    await p.click("#proposeConnectBtn");
    await waitForAddress(p, "#proposeWalletAddr", cfg.accounts.alice);
    // The page shows the address first and suggests the resolver a moment later, so wait for both.
    await p.waitFor(
      `${p.el("#proposeResolver")}.value.toLowerCase() === ${JSON.stringify(cfg.accounts.alice.toLowerCase())}`,
      "resolver defaults to the wallet"
    );

    await p.fill("#proposeProposition", cfg.proposition);
    await p.fill("#proposeCollateral", "custom");
    await p.waitForVisible("#proposeUnlistedAckRow");
    await p.fill("#proposeCollateralCustom", cfg.unlistedToken);

    await p.fill("#proposeResolver", "0xnot-an-address");
    await p.click("#proposeSubmitBtn");
    await p.waitForText("#proposeError", "not a valid address");

    await p.fill("#proposeResolver", cfg.accounts.resolver);
    await p.click("#proposeSubmitBtn");
    await p.waitForText("#proposeError", "curated list");

    await p.check("#proposeUnlistedAck");
    await p.click("#proposeSubmitBtn");
    return waitForProposed(p);
  },

  async propose_freeform(b, cfg) {
    const p = await b.page(cfg.page || "propose-a-wager.html", cfg.accounts.alice);
    await proposeReady(p);
    await p.click(`[data-template="freeform"]`);
    await p.waitFor(`document.querySelector("#proposeOutcomesSection").hidden`, "outcomes hidden for freeform");
    await p.fill("#proposeProposition", cfg.proposition);
    await p.fill("#proposeCollateral", "custom");

    // An address with no code would make a wager nobody could ever bet on.
    await p.fill("#proposeCollateralCustom", "0x000000000000000000000000000000000000dEaD");
    await p.click("#proposeSubmitBtn");
    await p.waitForText("#proposeError", "no contract");

    await p.fill("#proposeCollateralCustom", cfg.listedToken);
    await p.click("#proposeSubmitBtn");
    return waitForProposed(p);
  },

  /** A wallet account change must not leave the page acting for the old account. */
  async propose_after_account_switch(b, cfg) {
    const p = await b.page("propose-a-wager.html", cfg.accounts.alice);
    await proposeReady(p);
    await p.click("#proposeConnectBtn");
    await waitForAddress(p, "#proposeWalletAddr", cfg.accounts.alice);
    await p.switchAccount(cfg.accounts.bob);
    await waitForAddress(p, "#proposeWalletAddr", cfg.accounts.bob);
    await p.waitFor(
      `${p.el("#proposeResolver")}.value.toLowerCase() === ${JSON.stringify(cfg.accounts.bob.toLowerCase())}`,
      "the suggested resolver follows the wallet"
    );
    await p.fill("#proposeProposition", cfg.proposition);
    await p.fill("#proposeCollateral", "custom");
    await p.fill("#proposeCollateralCustom", cfg.listedToken);
    await p.click("#proposeSubmitBtn");
    return waitForProposed(p);
  },

  async propose_keeps_a_chosen_resolver_after_account_switch(b, cfg) {
    const p = await b.page("propose-a-wager.html", cfg.accounts.alice);
    await proposeReady(p);
    await p.click("#proposeConnectBtn");
    await waitForAddress(p, "#proposeWalletAddr", cfg.accounts.alice);
    await p.fill("#proposeResolver", cfg.accounts.resolver);
    await p.switchAccount(cfg.accounts.bob);
    await waitForAddress(p, "#proposeWalletAddr", cfg.accounts.bob);
    await p.waitForText("#proposeNetworkStatus", "Network");
    await sleep(500);
    return { resolver: await p.value("#proposeResolver") };
  },

  async bet_enumerated(b, cfg) {
    const page = cfg.page || "bet.html";
    const p = await b.page(`${page}?wager=${cfg.wager}`, cfg.accounts.alice);
    await p.waitForVisible("#betSummary");
    assert.equal(await p.text("#betState"), "OPEN");
    assert.equal(await p.disabled("#betSubmitBtn"), true, "no staking before connecting");
    assert.equal(await p.visible("#betCollateralWarning"), true, "unlisted token is flagged");
    assert.equal(await p.visible("#betCollateralHuman"), false, "a token's self-chosen symbol is not shown as fact");

    await connectBetPage(p, cfg.accounts.alice);
    await p.waitForText("#betDecimalsHint", "Token decimals: 18");
    await p.waitFor(`!document.querySelector("#betSubmitBtn").disabled`, "submit enabled after connecting");

    await p.fill(`.bet-amount-input[data-outcome-index="0"]`, "0.0");
    await submitStake(p);
    await p.waitForText("#betTxStatus", "greater than zero");

    await p.fill(`.bet-amount-input[data-outcome-index="0"]`, "");
    await p.fill(`.bet-amount-input[data-outcome-index="1"]`, "1.5");
    await submitStake(p);
    await p.waitForText("#betTxStatus", SUCCESS);

    // The refresh after a transaction used to erase this, so a person saw nothing happen.
    await sleep(1500);
    assert.ok((await p.text("#betTxStatus")).includes(SUCCESS), "the confirmation stays on screen");
    assert.equal(await p.value(`.bet-amount-input[data-outcome-index="1"]`), "", "a stake cannot be resent by accident");

    // Without reloading, the figures catch up once the indexer has seen the block.
    await p.waitForText("#betPot", "1,500,000,000,000,000,000");
    assert.ok((await p.text("#betTxStatus")).includes(SUCCESS), "later refreshes keep the confirmation too");

    // Number() turned this into 1e-7, which parseUnits rejects.
    await p.fill(`.bet-amount-input[data-outcome-index="0"]`, "0.0000001");
    await submitStake(p);
    await p.waitForText("#betTxStatus", SUCCESS);
    await p.waitForText("#betPot", "1,500,000,100,000,000,000");
    return { status: await p.text("#betTxStatus") };
  },

  async bet_after_account_switch(b, cfg) {
    const p = await b.page(`bet.html?wager=${cfg.wager}`, cfg.accounts.alice);
    await connectBetPage(p, cfg.accounts.alice);
    await p.switchAccount(cfg.accounts.bob);
    await waitForAddress(p, "#betWalletAddr", cfg.accounts.bob);
    await p.waitFor(`!document.querySelector("#betSubmitBtn").disabled`, "submit enabled for the new account");
    await p.fill(`.bet-amount-input[data-outcome-index="0"]`, "3");
    await submitStake(p);
    await p.waitForText("#betTxStatus", SUCCESS);
    return {};
  },

  async bet_freeform(b, cfg) {
    const p = await b.page(`bet.html?wager=${cfg.wager}`, cfg.accounts.alice);
    await p.waitForVisible("#betSummary");
    await p.waitForText("#betOutcomesTableBody", "Paris");
    assert.ok((await p.text("#betOutcomesTableBody")).includes("space"), "a note flags that the spaces are part of the answer");
    await connectBetPage(p, cfg.accounts.alice);
    await p.waitFor(`!document.querySelector("#betSubmitBtn").disabled`, "submit enabled");

    await p.click("#betOutcomesTableBody button");
    assert.equal(await p.value("#betFreeformAnswerInput"), " Paris ", "picking an answer keeps its exact bytes");
    await p.fill(".bet-amount-input[data-freeform-amount]", "1");
    await submitStake(p);
    await p.waitForText("#betTxStatus", SUCCESS);

    // Typed text forgives stray spaces (ADR-0009 section 5).
    await p.fill("#betFreeformAnswerInput", "  Rome  ");
    await p.fill(".bet-amount-input[data-freeform-amount]", "2");
    await submitStake(p);
    await p.waitForText("#betTxStatus", SUCCESS);
    return {};
  },

  /** W1: connecting a wallet used to re-enable staking on a wager whose betting had already closed. */
  async bet_closed(b, cfg) {
    const p = await b.page(`bet.html?wager=${cfg.wager}`, cfg.accounts.alice);
    await p.waitForVisible("#betSummary");
    assert.equal(await p.disabled("#betSubmitBtn"), true);
    await connectBetPage(p, cfg.accounts.alice);
    await sleep(1000);
    assert.equal(await p.disabled("#betSubmitBtn"), true, "connecting must not re-enable staking");
    return { status: await p.text("#betTxStatus") };
  },

  /** A stake below the minimum must fail before the user pays for an approve it would waste. */
  async bet_below_minimum(b, cfg) {
    const p = await b.page(`bet.html?wager=${cfg.wager}`, cfg.accounts.alice);
    await connectBetPage(p, cfg.accounts.alice);
    await p.waitFor(`!document.querySelector("#betSubmitBtn").disabled`, "submit enabled");
    await p.fill(`.bet-amount-input[data-outcome-index="0"]`, "0.5");
    await submitStake(p);
    await p.waitForText("#betTxStatus", "needs at least");
    return {};
  },

  async bet_above_minimum(b, cfg) {
    const p = await b.page(`bet.html?wager=${cfg.wager}`, cfg.accounts.alice);
    await connectBetPage(p, cfg.accounts.alice);
    await p.waitFor(`!document.querySelector("#betSubmitBtn").disabled`, "submit enabled");
    await p.fill(`.bet-amount-input[data-outcome-index="0"]`, "2");
    await submitStake(p);
    await p.waitForText("#betTxStatus", SUCCESS);
    return {};
  },

  async bet_listed_token(b, cfg) {
    const p = await b.page(`bet.html?wager=${cfg.wager}`, cfg.accounts.alice);
    await p.waitForVisible("#betSummary");
    return {
      symbol: await p.text("#betCollateralHuman"),
      warningVisible: await p.visible("#betCollateralWarning"),
    };
  },

  /** X1: the home ticker and the bet search both claimed "No stakes yet" for every enumerated wager. */
  async public_listings(b, cfg) {
    const home = await b.page("index.html", cfg.accounts.alice);
    await home.waitForText("#tickerTrack", cfg.proposition);
    // The ticker draws once without details, then again with them; this marks the second draw.
    await home.waitForText("#tickerStatus", "click a card");
    const ticker = await home.text("#tickerTrack");
    const place = await b.page("place-a-bet.html", cfg.accounts.alice);
    await place.fill("#homeBetSearchInput", cfg.proposition);
    await place.waitForText("#homeBetSearchResults", cfg.proposition);
    return { ticker, search: await place.text("#homeBetSearchResults") };
  },

  /** The explorer, as a direct visit and as `service/explorer/server.py` serves it. */
  async explorer_lists(b, cfg) {
    const p = await b.page(cfg.path ?? "explorer/index.html", cfg.accounts.alice);
    await p.waitForText("#wagers", cfg.proposition, 20_000);
    return {};
  },

  /** Every page loads, its local references resolve, ethers passes its integrity check. */
  async every_page(b, cfg) {
    const out = {};
    for (const path of cfg.pages) {
      const p = await b.page(path, cfg.accounts.alice);
      await sleep(700);
      out[path] = {
        localFailures: p.localFailures,
        ethers: await p.eval(`typeof globalThis.ethers`),
        declaresEthers: await p.eval(`Boolean(document.querySelector('script[src*="ethers"]'))`),
        integrity: await p.eval(`document.querySelector('script[src*="ethers"]')?.integrity || ""`),
      };
    }
    return { pages: out };
  },

  async no_wallet(b, cfg) {
    const bet = await b.page(`bet.html?wager=${cfg.wager}`, null);
    await bet.waitForVisible("#betSummary");
    await bet.click("#betConnectBtn");
    await bet.waitForText("#betNetworkStatus", "No EIP-1193 wallet");
    const propose = await b.page("propose-a-wager.html", null);
    await proposeReady(propose);
    await propose.click("#proposeConnectBtn");
    await propose.waitForText("#proposeError", "No wallet found");
    const dapp = await b.page("dapp/index.html", null);
    await dapp.waitForText("#walletStatus", "Ready.");
    await dapp.click("#connectBtn");
    await dapp.waitForText("#walletStatus", "No EIP-1193 wallet");
    return {};
  },

  /** The dApp's create form: the consent check, then a freeform wager with an extra fee recipient. */
  async dapp_create_freeform(b, cfg) {
    const p = await b.page("dapp/index.html", cfg.accounts.alice);
    await p.waitForText("#walletStatus", "Ready.");
    assert.equal((await p.value("#factoryAddress")).toLowerCase(), cfg.factory.toLowerCase(), "factory comes from the deployed config");
    await p.click("#connectBtn");
    await waitForAddress(p, "#walletAddr", cfg.accounts.alice);

    await p.fill("#protocolVersion", "v3_freeform");
    await p.fill("#collateralPreset", "custom");
    await p.fill("#collateralToken", cfg.unlistedToken);
    await p.fill("#proposition", cfg.proposition);
    await p.fill("#bettingCloseIn", "3600");
    await p.fill("#resolutionWindow", "3600");
    await p.fill("#resolverAddress", cfg.accounts.alice);
    await p.fill("#bettingCloserAddress", cfg.accounts.alice);
    await p.fill("#extraFeeRecipients", cfg.accounts.carol);
    await p.fill("#extraFeeBps", "250");

    await p.click("#createWagerBtn");
    await p.waitForText("#createStatus", "not on the curated list");
    await p.check("#allowUnlistedCollateral");
    await p.click("#createWagerBtn");
    await p.waitForText("#createStatus", "Wager created.");
    return { wager: await p.text("#wagerAddress") };
  },

  /** W4 and W7: resolve sends exact bytes, and the page follows the wallet between accounts. */
  async dapp_finish_freeform(b, cfg) {
    const p = await b.page("dapp/index.html", cfg.accounts.alice);
    await p.waitForText("#walletStatus", "Ready.");
    await p.fill("#activeWagerAddress", cfg.wager);
    await p.click("#loadWagerBtn");
    await p.waitForText("#betStatus", "Active wager loaded.");
    assert.ok((await p.text("#activeWagerWarnings")).includes("curated list"), "unlisted collateral is flagged");

    await p.fill("#betOutcomeIndex", "Rome");
    await p.fill("#betAmount", "1");
    await p.click("#placeBetBtn");
    await p.waitForText("#betStatus", "Bet placed.");

    await p.click("#closeBettingBtn");
    await p.waitForText("#resolutionStatus", "Betting closed");

    await p.fill("#winningOutcomeIndex", " Paris ");
    await p.waitForText("#winningAnswerBytes", "Will send 7 bytes: 0x20506172697320");
    assert.ok((await p.text("#winningAnswerBytes")).includes("space"), "the preview points out the spaces");
    await p.click("#resolveBtn");
    await p.waitForText("#resolutionStatus", "Resolved.");

    await p.switchAccount(cfg.accounts.bob);
    await waitForAddress(p, "#walletAddr", cfg.accounts.bob);
    await p.click("#claimBtn");
    await p.waitForText("#claimStatus", "Claimed");

    await p.switchAccount(cfg.accounts.carol);
    await waitForAddress(p, "#walletAddr", cfg.accounts.carol);
    await p.click("#withdrawFeesBtn");
    await p.waitForText("#claimStatus", "Fees withdrawn.");
    return {};
  },

  /** The enumerated path: a multi-outcome policy, seeded liquidity, a mask built from indices. */
  async dapp_enumerated_lifecycle(b, cfg) {
    const p = await b.page("dapp/index.html", cfg.accounts.alice);
    await p.waitForText("#walletStatus", "Ready.");
    await p.click("#connectBtn");
    await waitForAddress(p, "#walletAddr", cfg.accounts.alice);

    await p.fill("#protocolVersion", "v3_enum");
    await p.fill("#collateralPreset", "custom");
    await p.fill("#collateralToken", cfg.listedToken);
    await p.fill("#proposition", cfg.proposition);
    await p.fill("#outcomes", "North,South,East");
    await p.fill("#payoffPolicy", "1");
    await p.fill("#bettingCloseIn", "3600");
    await p.fill("#resolutionWindow", "3600");
    await p.fill("#resolverAddress", cfg.accounts.alice);
    await p.fill("#bettingCloserAddress", cfg.accounts.alice);
    await p.fill("#seedOutcomeIndices", "2");
    await p.fill("#seedAmounts", "1");
    await p.click("#createWagerBtn");
    await p.waitForText("#createStatus", "Wager created.");
    const wager = await p.text("#wagerAddress");

    await p.fill("#betOutcomeIndex", "0,1");
    await p.fill("#betAmount", "4");
    await p.click("#placeBetBtn");
    await p.waitForText("#betStatus", "Bet placed.");

    await p.click("#closeBettingBtn");
    await p.waitForText("#resolutionStatus", "Betting closed");
    await p.fill("#winningOutcomeIndex", "1");
    await p.click("#resolveBtn");
    await p.waitForText("#resolutionStatus", "Resolved.");
    await p.click("#claimBtn");
    await p.waitForText("#claimStatus", "Claimed");
    return { wager };
  },
};

// ---- Entry point ----

const [scenario, rawConfig] = process.argv.slice(2);
if (!scenarios[scenario]) {
  console.error(`Unknown scenario: ${scenario}. Known: ${Object.keys(scenarios).join(", ")}`);
  process.exit(2);
}
const cfg = JSON.parse(rawConfig);
const browser = await Browser.launch(cfg);
let exitCode = 0;
try {
  const result = await scenarios[scenario](browser, cfg);
  console.log(JSON.stringify({ ...result, pageErrors: browser.pageErrors() }));
} catch (err) {
  console.error(err.stack || String(err));
  console.error(`Page errors: ${browser.pageErrors().join(" | ")}`);
  exitCode = 1;
} finally {
  await browser.close();
}
process.exit(exitCode);
