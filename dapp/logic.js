// Shared pure logic for the browser dApp and Node tests.
(function initParamutuelLogic(globalScope) {
  const MARKET_TEMPLATES = {
    custom: { bettingCloseIn: 7200, resolutionWindow: 7200, bettingNoMax: false, resolutionNoMax: false },
    sports: { bettingCloseIn: 2 * 60 * 60, resolutionWindow: 24 * 60 * 60, bettingNoMax: false, resolutionNoMax: false },
    election: {
      bettingCloseIn: 30 * 24 * 60 * 60,
      resolutionWindow: 14 * 24 * 60 * 60,
      bettingNoMax: false,
      resolutionNoMax: false,
    },
    long: {
      bettingCloseIn: 365 * 24 * 60 * 60,
      resolutionWindow: 180 * 24 * 60 * 60,
      bettingNoMax: false,
      resolutionNoMax: false,
    },
    "closer-only": { bettingCloseIn: 7200, resolutionWindow: 7200, bettingNoMax: true, resolutionNoMax: true },
  };

  function getTemplate(name) {
    return MARKET_TEMPLATES[name] || MARKET_TEMPLATES.custom;
  }

  function computeWindowArgs(nowSec, bettingCloseIn, resolutionWindow, bettingNoMax, resolutionNoMax) {
    if (!bettingNoMax && (!Number.isFinite(bettingCloseIn) || bettingCloseIn <= 0)) {
      throw new Error("bettingCloseIn must be positive unless no-max betting is enabled.");
    }
    if (!resolutionNoMax && (!Number.isFinite(resolutionWindow) || resolutionWindow <= 0)) {
      throw new Error("resolutionWindow must be positive unless no-max resolution is enabled.");
    }
    return {
      closeTime: bettingNoMax ? 0 : Math.floor(nowSec) + Number(bettingCloseIn),
      resolutionWindowArg: resolutionNoMax ? 0 : Number(resolutionWindow),
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

  const api = {
    MARKET_TEMPLATES,
    getTemplate,
    computeWindowArgs,
    validateWindowMins,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    globalScope.ParamutuelLogic = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : window);
