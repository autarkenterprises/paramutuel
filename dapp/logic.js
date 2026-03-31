// Shared pure logic for the browser dApp and Node tests.
(function initParamutuelLogic(globalScope) {
  const MARKET_TEMPLATES = {
    custom: {
      bettingCloseMode: "relative",
      resolutionWindowMode: "relative",
      bettingCloseIn: 7200,
      resolutionWindow: 7200,
      bettingNoMax: false,
      resolutionNoMax: false,
    },
    flash: {
      bettingCloseMode: "relative",
      resolutionWindowMode: "relative",
      bettingCloseIn: 15 * 60,
      resolutionWindow: 2 * 60 * 60,
      bettingNoMax: false,
      resolutionNoMax: false,
    },
    sports: {
      bettingCloseMode: "relative",
      resolutionWindowMode: "relative",
      bettingCloseIn: 2 * 60 * 60,
      resolutionWindow: 24 * 60 * 60,
      bettingNoMax: false,
      resolutionNoMax: false,
    },
    election: {
      bettingCloseMode: "relative",
      resolutionWindowMode: "relative",
      bettingCloseIn: 30 * 24 * 60 * 60,
      resolutionWindow: 14 * 24 * 60 * 60,
      bettingNoMax: false,
      resolutionNoMax: false,
    },
    long: {
      bettingCloseMode: "relative",
      resolutionWindowMode: "relative",
      bettingCloseIn: 365 * 24 * 60 * 60,
      resolutionWindow: 180 * 24 * 60 * 60,
      bettingNoMax: false,
      resolutionNoMax: false,
    },
    "daily-utc-cutoff": {
      bettingCloseMode: "absolute",
      resolutionWindowMode: "relative",
      absoluteRule: "nextUtcMidnight",
      bettingCloseIn: 0,
      resolutionWindow: 24 * 60 * 60,
      bettingNoMax: false,
      resolutionNoMax: false,
    },
    "weekly-utc-cutoff": {
      bettingCloseMode: "absolute",
      resolutionWindowMode: "relative",
      absoluteRule: "nextUtcMondayMidnight",
      bettingCloseIn: 0,
      resolutionWindow: 72 * 60 * 60,
      bettingNoMax: false,
      resolutionNoMax: false,
    },
    "closer-only": {
      bettingCloseMode: "relative",
      resolutionWindowMode: "relative",
      bettingCloseIn: 7200,
      resolutionWindow: 7200,
      bettingNoMax: true,
      resolutionNoMax: true,
    },
  };

  function getTemplate(name) {
    return MARKET_TEMPLATES[name] || MARKET_TEMPLATES.custom;
  }

  function computeAbsoluteTemplateClose(nowSec, rule) {
    const now = new Date(Math.floor(nowSec) * 1000);
    if (rule === "nextUtcMidnight") {
      return Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1) / 1000;
    }
    if (rule === "nextUtcMondayMidnight") {
      const day = now.getUTCDay(); // 0=Sun ... 6=Sat
      const daysUntilMonday = day === 0 ? 1 : 8 - day;
      return Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + daysUntilMonday) / 1000;
    }
    throw new Error(`Unknown absolute template rule: ${rule}`);
  }

  function resolveTemplate(name, nowSec) {
    const template = { ...getTemplate(name) };
    if (template.bettingCloseMode !== "absolute") {
      return template;
    }
    const closeAt = computeAbsoluteTemplateClose(nowSec, template.absoluteRule);
    return {
      ...template,
      bettingCloseAt: closeAt,
      bettingCloseIn: Math.max(0, closeAt - Math.floor(nowSec)),
    };
  }

  function computeWindowArgs(
    nowSec,
    bettingCloseIn,
    resolutionWindow,
    bettingNoMax,
    resolutionNoMax,
    bettingCloseMode = "relative",
    bettingCloseAt = null,
    resolutionWindowMode = "relative",
    resolutionCloseAt = null
  ) {
    if (bettingCloseMode !== "relative" && bettingCloseMode !== "absolute") {
      throw new Error("bettingCloseMode must be 'relative' or 'absolute'.");
    }
    if (resolutionWindowMode !== "relative" && resolutionWindowMode !== "absolute") {
      throw new Error("resolutionWindowMode must be 'relative' or 'absolute'.");
    }
    if (
      !bettingNoMax &&
      bettingCloseMode === "relative" &&
      (!Number.isFinite(bettingCloseIn) || bettingCloseIn <= 0)
    ) {
      throw new Error("bettingCloseIn must be positive unless no-max betting is enabled.");
    }
    if (
      !bettingNoMax &&
      bettingCloseMode === "absolute" &&
      (!Number.isFinite(bettingCloseAt) || Number(bettingCloseAt) <= Math.floor(nowSec))
    ) {
      throw new Error("bettingCloseAt must be a future unix timestamp.");
    }
    if (
      !resolutionNoMax &&
      resolutionWindowMode === "relative" &&
      (!Number.isFinite(resolutionWindow) || resolutionWindow <= 0)
    ) {
      throw new Error("resolutionWindow must be positive unless no-max resolution is enabled.");
    }
    if (!resolutionNoMax && resolutionWindowMode === "absolute" && bettingNoMax) {
      throw new Error("resolutionCloseAt requires a finite betting close time.");
    }
    let closeTime = 0;
    if (!bettingNoMax) {
      closeTime =
        bettingCloseMode === "absolute"
          ? Math.floor(Number(bettingCloseAt))
          : Math.floor(nowSec) + Number(bettingCloseIn);
    }
    let resolutionWindowArg = 0;
    if (resolutionNoMax) {
      resolutionWindowArg = 0;
    } else if (resolutionWindowMode === "relative") {
      resolutionWindowArg = Number(resolutionWindow);
    } else {
      if (!Number.isFinite(resolutionCloseAt) || Number(resolutionCloseAt) <= closeTime) {
        throw new Error("resolutionCloseAt must be after betting close time.");
      }
      resolutionWindowArg = Math.floor(Number(resolutionCloseAt)) - closeTime;
    }
    return {
      closeTime,
      resolutionWindowArg,
    };
  }

  function validateWindowMins(minBettingWindow, minResolutionWindow, bettingCloseIn, resolutionWindow, bettingNoMax, resolutionNoMax) {
    const warnings = [];
    if (!bettingNoMax && BigInt(bettingCloseIn) < BigInt(minBettingWindow)) {
      warnings.push(`bettingCloseIn < minBettingWindow (${minBettingWindow})`);
    }
    if (!resolutionNoMax && BigInt(resolutionWindow) < BigInt(minResolutionWindow)) {
      throw new Error(`resolutionWindow < minResolutionWindow (${minResolutionWindow})`);
    }
    return warnings;
  }

  function parseMultiBetInputs(indicesCsv, amountsCsv, allowEmpty = true) {
    const parseCsv = (s) =>
      String(s || "")
        .split(",")
        .map((x) => x.trim())
        .filter((x) => x.length > 0);

    const rawIndices = parseCsv(indicesCsv);
    const rawAmounts = parseCsv(amountsCsv);

    if (rawIndices.length === 0 && rawAmounts.length === 0 && allowEmpty) {
      return { outcomeIndices: [], amountNumbers: [] };
    }
    if (rawIndices.length === 0 || rawAmounts.length === 0) {
      throw new Error("Both outcome indices and amounts are required.");
    }
    if (rawIndices.length !== rawAmounts.length) {
      throw new Error("Outcome indices and amounts length mismatch.");
    }

    const outcomeIndices = rawIndices.map((v) => {
      const n = Number(v);
      if (!Number.isInteger(n) || n < 0) throw new Error(`Invalid outcome index: ${v}`);
      return n;
    });
    const amountNumbers = rawAmounts.map((v) => {
      const n = Number(v);
      if (!Number.isFinite(n) || n <= 0) throw new Error(`Invalid amount: ${v}`);
      return n;
    });
    return { outcomeIndices, amountNumbers };
  }

  const MARKET_ACTION_CONFIG = {
    closeBetting: { section: "resolution", method: "closeBetting" },
    closeResolutionWindow: { section: "resolution", method: "closeResolutionWindow" },
    resolve: { section: "resolution", method: "resolve" },
    retract: { section: "resolution", method: "retract" },
    expire: { section: "resolution", method: "expire" },
    claim: { section: "claims", method: "claim" },
    withdrawFees: { section: "claims", method: "withdrawFees" },
  };

  function planMarketAction(
    actionName,
    { resolutionMarketAddress = "", claimsMarketAddress = "", activeMarketAddress = "" } = {}
  ) {
    const config = MARKET_ACTION_CONFIG[actionName];
    if (!config) throw new Error(`Unsupported action: ${actionName}`);
    const selected = config.section === "resolution" ? resolutionMarketAddress : claimsMarketAddress;
    const targetAddress = String(selected || "").trim() || String(activeMarketAddress || "").trim();
    if (!targetAddress) {
      throw new Error("Select a wager address in this section, or load an active wager above.");
    }
    return {
      actionName,
      section: config.section,
      method: config.method,
      targetAddress,
    };
  }

  const api = {
    MARKET_TEMPLATES,
    getTemplate,
    computeWindowArgs,
    validateWindowMins,
    parseMultiBetInputs,
    computeAbsoluteTemplateClose,
    resolveTemplate,
    MARKET_ACTION_CONFIG,
    planMarketAction,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    globalScope.ParamutuelLogic = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : window);
