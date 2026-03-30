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

  function computeWindowArgs(
    nowSec,
    bettingCloseIn,
    resolutionWindow,
    bettingNoMax,
    resolutionNoMax,
    bettingCloseMode = "relative",
    bettingCloseAt = null
  ) {
    if (bettingCloseMode !== "relative" && bettingCloseMode !== "absolute") {
      throw new Error("bettingCloseMode must be 'relative' or 'absolute'.");
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
    if (!resolutionNoMax && (!Number.isFinite(resolutionWindow) || resolutionWindow <= 0)) {
      throw new Error("resolutionWindow must be positive unless no-max resolution is enabled.");
    }
    let closeTime = 0;
    if (!bettingNoMax) {
      closeTime =
        bettingCloseMode === "absolute"
          ? Math.floor(Number(bettingCloseAt))
          : Math.floor(nowSec) + Number(bettingCloseIn);
    }
    return {
      closeTime,
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

  const api = {
    MARKET_TEMPLATES,
    getTemplate,
    computeWindowArgs,
    validateWindowMins,
    parseMultiBetInputs,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    globalScope.ParamutuelLogic = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : window);
