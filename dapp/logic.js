// Shared pure logic for the browser dApp and Node tests.
(function initParamutuelLogic(globalScope) {
  const WAGER_TEMPLATES = {
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
    return WAGER_TEMPLATES[name] || WAGER_TEMPLATES.custom;
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

  /** Matches `ParamutuelWagerV2.PayoffPolicy` enum ordinals. */
  const PAYOFF_POLICY = Object.freeze({
    SINGLE_WINNER: 0,
    ANY_OF: 1,
    EXACT_SET: 2,
    AT_LEAST_K: 3,
    WEIGHTED_OVERLAP: 4,
  });

  function payoffPolicyLabel(policy) {
    const labels = ["SINGLE_WINNER", "ANY_OF", "EXACT_SET", "AT_LEAST_K", "WEIGHTED_OVERLAP"];
    const n = Number(policy);
    return Number.isInteger(n) && n >= 0 && n < labels.length ? labels[n] : `UNKNOWN(${policy})`;
  }

  function popcountMask(mask) {
    let m = BigInt(mask);
    let c = 0;
    while (m > 0n) {
      m &= m - 1n;
      c += 1;
    }
    return c;
  }

  /**
   * Build a v2 ticket bitmask from distinct outcome indices (0-based).
   * @param {number[]} indices
   * @param {number} numOptions
   * @returns {bigint}
   */
  function outcomeIndicesToTicketMask(indices, numOptions) {
    const n = Number(numOptions);
    if (!Number.isInteger(n) || n < 2 || n > 256) {
      throw new Error("numOptions must be an integer from 2 to 256.");
    }
    if (!indices || indices.length === 0) {
      throw new Error("Select at least one outcome index for the ticket.");
    }
    let mask = 0n;
    for (const idx of indices) {
      const i = Number(idx);
      if (!Number.isInteger(i) || i < 0 || i >= n) {
        throw new Error(`Outcome index ${idx} is out of range (0-${n - 1}).`);
      }
      const bit = 1n << BigInt(i);
      if ((mask & bit) !== 0n) {
        throw new Error(`Duplicate outcome index: ${i}`);
      }
      mask |= bit;
    }
    return mask;
  }

  /**
   * Comma-separated indices, e.g. "0" or "0,2" for a ticket on outcomes 0 and 2.
   * @param {string} csv
   * @param {number} numOptions
   * @returns {bigint}
   */
  function parseOutcomeIndicesCsvToTicketMask(csv, numOptions) {
    const parts = String(csv || "")
      .split(",")
      .map((x) => x.trim())
      .filter((x) => x.length > 0);
    if (parts.length === 0) {
      throw new Error("Ticket needs at least one outcome index.");
    }
    const indices = parts.map((v) => {
      const n = Number(v);
      if (!Number.isInteger(n) || n < 0) {
        throw new Error(`Invalid outcome index: ${v}`);
      }
      return n;
    });
    return outcomeIndicesToTicketMask(indices, numOptions);
  }

  /**
   * v1-style seed lines: each outcome index becomes a single-bit v2 seed ticket.
   * @param {number[]} outcomeIndices
   * @returns {bigint[]}
   */
  function seedOutcomeIndicesToTicketMasks(outcomeIndices) {
    return outcomeIndices.map((i) => {
      const n = Number(i);
      if (!Number.isInteger(n) || n < 0) {
        throw new Error(`Invalid seed outcome index: ${i}`);
      }
      return 1n << BigInt(n);
    });
  }

  function validatePolicyParamForCreate(policy, policyParam, numOutcomes) {
    const p = Number(policy);
    const k = Number(policyParam);
    if (p === PAYOFF_POLICY.AT_LEAST_K) {
      if (!Number.isInteger(k) || k < 1 || k > numOutcomes) {
        throw new Error(`AT_LEAST_K requires k between 1 and ${numOutcomes} (inclusive).`);
      }
    } else if (!Number.isFinite(k) || k !== 0) {
      throw new Error("policyParam must be 0 except for AT_LEAST_K (k).");
    }
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

  const WAGER_ACTION_CONFIG = {
    closeBetting: { section: "resolution", method: "closeBetting" },
    closeResolutionWindow: { section: "resolution", method: "closeResolutionWindow" },
    resolve: { section: "resolution", method: "resolve" },
    retract: { section: "resolution", method: "retract" },
    expire: { section: "resolution", method: "expire" },
    claim: { section: "claims", method: "claim" },
    withdrawFees: { section: "claims", method: "withdrawFees" },
  };

  /**
   * Domain-separated freeform ticket id (current Paramutuel deployment):
   * keccak256(abi.encodePacked(bytes1(0x03), bytes(answer))).
   * @param {string} answer UTF-8 answer string
   * @param {object} [ethersLib] ethers v6 (default: globalThis.ethers)
   */
  function freeformV3AnswerId(answer, ethersLib) {
    const E = ethersLib || (typeof globalThis !== "undefined" && globalThis.ethers);
    if (!E || typeof E.keccak256 !== "function") {
      throw new Error("freeformV3AnswerId requires ethers (load ethers before logic.js, or pass ethers as 2nd arg).");
    }
    const domain = E.hexlify(new Uint8Array([3]));
    return E.keccak256(E.concat([domain, E.toUtf8Bytes(answer)]));
  }

  function planWagerAction(
    actionName,
    { resolutionWagerAddress = "", claimsWagerAddress = "", activeWagerAddress = "" } = {}
  ) {
    const config = WAGER_ACTION_CONFIG[actionName];
    if (!config) throw new Error(`Unsupported action: ${actionName}`);
    const selected = config.section === "resolution" ? resolutionWagerAddress : claimsWagerAddress;
    const targetAddress = String(selected || "").trim() || String(activeWagerAddress || "").trim();
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
    WAGER_TEMPLATES,
    getTemplate,
    computeWindowArgs,
    validateWindowMins,
    parseMultiBetInputs,
    computeAbsoluteTemplateClose,
    resolveTemplate,
    WAGER_ACTION_CONFIG,
    planWagerAction,
    PAYOFF_POLICY,
    payoffPolicyLabel,
    popcountMask,
    outcomeIndicesToTicketMask,
    parseOutcomeIndicesCsvToTicketMask,
    seedOutcomeIndicesToTicketMasks,
    validatePolicyParamForCreate,
    freeformV3AnswerId,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    globalScope.ParamutuelLogic = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : window);
