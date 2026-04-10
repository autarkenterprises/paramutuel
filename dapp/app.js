// Load ethers via UMD in index.html:
// <script src="https://cdn.jsdelivr.net/npm/ethers@6.13.5/dist/ethers.umd.min.js"></script>
// The UMD bundle exposes `ethers` on `globalThis`.
const ethers = globalThis.ethers;

/**
 * Prefer a single EIP-1193 provider. Some browsers aggregate multiple wallets under
 * `ethereum.providers[]`; we pick the first entry that implements `request`.
 * Any wallet that injects a standards-compliant provider works with this dApp.
 */
function resolveEip1193Provider() {
  const eth = globalThis.ethereum;
  if (!eth) return null;
  if (Array.isArray(eth.providers) && eth.providers.length > 0) {
    const withRequest = eth.providers.find((p) => p && typeof p.request === "function");
    return withRequest || eth.providers[0];
  }
  return eth;
}

const FACTORY_ABI_URL = "abi/ParamutuelFactory.json";
const FACTORY_ABI_FALLBACK = "../out/ParamutuelFactory.sol/ParamutuelFactory.json";
const FACTORY_ABI_V2_URL = "abi/ParamutuelFactoryV2.json";
const FACTORY_ABI_V2_FALLBACK = "../out/ParamutuelFactoryV2.sol/ParamutuelFactoryV2.json";
const WAGER_ABI_URL = "abi/ParamutuelWager.json";
const WAGER_ABI_FALLBACK = "../out/ParamutuelWager.sol/ParamutuelWager.json";
const WAGER_ABI_V2_URL = "abi/ParamutuelWagerV2.json";
const WAGER_ABI_V2_FALLBACK = "../out/ParamutuelWagerV2.sol/ParamutuelWagerV2.json";
const FACTORY_ABI_FF_URL = "abi/ParamutuelFactoryFreeform.json";
const FACTORY_ABI_FF_FALLBACK = "../out/ParamutuelFactoryFreeform.sol/ParamutuelFactoryFreeform.json";
const WAGER_ABI_FF_URL = "abi/ParamutuelWagerFreeform.json";
const WAGER_ABI_FF_FALLBACK = "../out/ParamutuelWagerFreeform.sol/ParamutuelWagerFreeform.json";
const DEPLOYMENTS_CONFIG_URL = "../config/deployments.json";
const Logic = globalThis.ParamutuelLogic;

let provider;
let signer;
let userAddress;

let factoryAbiV1;
let wagerAbiV1;
let factoryAbiV2;
let wagerAbiV2;
let factoryAbiFF;
let wagerAbiFF;
/** @type {"v1"|"v2"|"freeform"} */
let activeWagerProtocol = "v1";

let wagerContract; // last-created wager
let currentChainId = null;
let walletListenersAttached = false;
let deploymentsConfig = null;
/** When embedded from site/app.html with ?siteNetwork=baseMainnet|baseSepolia */
let siteDeploymentNetworkKey = null;

/** Optional `?wager=0x…` deep link: pre-fills the active wager field; loads after wallet connect. */
let wagerAddressFromUrl = null;

const CHAIN_INFO = {
  1: { name: "Ethereum Mainnet" },
  8453: { name: "Base Mainnet" },
  84532: { name: "Base Sepolia" },
};
const DEPLOYMENTS_KEY_BY_CHAIN_ID = {
  8453: "baseMainnet",
  84532: "baseSepolia",
};

const TOKEN_PRESETS = {
  8453: [
    {
      symbol: "USDC",
      address: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
      decimals: 6,
    },
    {
      symbol: "WETH",
      address: "0x4200000000000000000000000000000000000006",
      decimals: 18,
    },
    {
      symbol: "DAI",
      address: "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb",
      decimals: 18,
    },
    {
      symbol: "cbBTC",
      address: "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf",
      decimals: 8,
    },
  ],
  84532: [
    {
      symbol: "USDC",
      address: "0x036CbD53842c5426634e7929541eC2318f3dCf7e",
      decimals: 6,
    },
    {
      symbol: "WETH",
      address: "0x4200000000000000000000000000000000000006",
      decimals: 18,
    },
  ],
};

function knownSymbolForToken(chainId, tokenAddress) {
  if (tokenAddress == null || chainId == null || Number.isNaN(chainId)) return null;
  const list = TOKEN_PRESETS[chainId] || [];
  const lower = String(tokenAddress).toLowerCase();
  const hit = list.find((t) => String(t.address).toLowerCase() === lower);
  return hit ? hit.symbol : null;
}

const ERC20_SYMBOL_STRING_ABI = ["function symbol() view returns (string)"];
const ERC20_SYMBOL_BYTES32_ABI = ["function symbol() view returns (bytes32)"];

async function fetchTokenSymbolFromChain(tokenAddress) {
  if (!provider || !ethers.isAddress(tokenAddress)) return null;
  const cStr = new ethers.Contract(tokenAddress, ERC20_SYMBOL_STRING_ABI, provider);
  try {
    const s = await cStr.symbol();
    if (typeof s === "string") {
      const t = s.trim();
      if (t) return t.slice(0, 32);
    }
  } catch (_) {}
  try {
    const cB = new ethers.Contract(tokenAddress, ERC20_SYMBOL_BYTES32_ABI, provider);
    const b = await cB.symbol();
    if (b != null && typeof ethers.decodeBytes32String === "function") {
      const t = ethers.decodeBytes32String(b).trim();
      if (t) return t.slice(0, 32);
    }
  } catch (_) {}
  return null;
}

async function resolveTokenSymbolForDisplay(tokenAddress) {
  const preset = knownSymbolForToken(currentChainId, tokenAddress);
  if (preset) return preset;
  return await fetchTokenSymbolFromChain(tokenAddress);
}

function $(id) {
  return document.getElementById(id);
}

function chainName(chainId) {
  const info = CHAIN_INFO[chainId];
  return info ? info.name : `Unknown chain (${chainId})`;
}

function deploymentConfigKeyForChain(chainId) {
  const n = chainId == null ? NaN : Number(chainId);
  if (Number.isFinite(n) && DEPLOYMENTS_KEY_BY_CHAIN_ID[n]) {
    return DEPLOYMENTS_KEY_BY_CHAIN_ID[n];
  }
  if (siteDeploymentNetworkKey && deploymentsConfig && deploymentsConfig[siteDeploymentNetworkKey]) {
    return siteDeploymentNetworkKey;
  }
  if (deploymentsConfig && typeof deploymentsConfig.defaultNetwork === "string") {
    const configured = deploymentsConfig.defaultNetwork.trim();
    if (configured.length > 0 && deploymentsConfig[configured]) {
      return configured;
    }
  }
  return "baseSepolia";
}

function applySiteDeploymentNetworkFromUrl() {
  siteDeploymentNetworkKey = null;
  if (!deploymentsConfig) return;
  try {
    const raw = new URLSearchParams(window.location.search).get("siteNetwork");
    if (!raw) return;
    const k = raw.trim();
    if (deploymentsConfig[k] && typeof deploymentsConfig[k] === "object") {
      siteDeploymentNetworkKey = k;
    }
  } catch (_) {}
}

function deploymentFactoryAddressForChain(chainId) {
  if (!deploymentsConfig) return "";
  const key = deploymentConfigKeyForChain(chainId);
  return String((deploymentsConfig[key] || {}).factoryAddress || "").trim();
}

function deploymentFactoryV2AddressForChain(chainId) {
  if (!deploymentsConfig) return "";
  const key = deploymentConfigKeyForChain(chainId);
  return String((deploymentsConfig[key] || {}).factoryV2Address || "").trim();
}

function deploymentFactoryFreeformAddressForChain(chainId) {
  if (!deploymentsConfig) return "";
  const key = deploymentConfigKeyForChain(chainId);
  return String((deploymentsConfig[key] || {}).factoryFreeformAddress || "").trim();
}

function applyDefaultFactoryAddress() {
  const current = $("factoryAddress").value.trim();
  if (current) return;
  const protocol = $("protocolVersion") ? $("protocolVersion").value : "v1";
  let configured = "";
  if (protocol === "v2") configured = deploymentFactoryV2AddressForChain(currentChainId);
  else if (protocol === "freeform") configured = deploymentFactoryFreeformAddressForChain(currentChainId);
  else configured = deploymentFactoryAddressForChain(currentChainId);
  if (!configured || !ethers.isAddress(configured)) return;
  $("factoryAddress").value = configured;
}

function syncProtocolCreateUi() {
  const el = $("createV2Fields");
  if (el) {
    const protocol = $("protocolVersion") ? $("protocolVersion").value : "v1";
    el.hidden = protocol !== "v2";
  }
  const outWrap = $("outcomesLabelWrap");
  if (outWrap) {
    const protocol = $("protocolVersion") ? $("protocolVersion").value : "v1";
    outWrap.hidden = protocol === "freeform";
  }
  const seedSec = $("seedLiquiditySection");
  if (seedSec) {
    const protocol = $("protocolVersion") ? $("protocolVersion").value : "v1";
    seedSec.hidden = protocol === "freeform";
  }
  const hint = $("factoryProtocolHint");
  if (hint) {
    const protocol = $("protocolVersion") ? $("protocolVersion").value : "v1";
    if (protocol === "v2") {
      hint.textContent =
        "Use a ParamutuelFactoryV2 deployment (ADR-0008). v1 / freeform factory addresses will revert.";
    } else if (protocol === "freeform") {
      hint.textContent =
        "Use ParamutuelFactoryFreeform (ADR-0009). No outcome list at create; bettors submit UTF-8 answers (max 1024 bytes each).";
    } else {
      hint.textContent =
        "Use ParamutuelFactory (v1). For bitmask tickets use v2; for open text answers use freeform.";
    }
  }
}

function tokenPresetValue(chainId, token) {
  return `${chainId}:${token.address}:${token.decimals}:${token.symbol}`;
}

function parseTokenPresetValue(value) {
  const [chainIdRaw, address, decimalsRaw, symbol] = value.split(":");
  return {
    chainId: Number(chainIdRaw),
    address,
    decimals: Number(decimalsRaw),
    symbol,
  };
}

function parseCsvToArray(s) {
  return s
    .split(",")
    .map((x) => x.trim())
    .filter((x) => x.length > 0);
}

function normalizeAddressInput(raw) {
  const cleaned = String(raw || "")
    // Remove common invisible unicode marks that can appear via copy/paste or browser autofill.
    .replace(/[\u200B-\u200D\uFEFF\u200E\u200F\u202A-\u202E\u2060-\u2069]/g, "")
    .replace(/\s+/g, "")
    .trim();
  if (!cleaned) return "";

  let candidate = cleaned;
  if (/^[0-9a-fA-F]{40}$/.test(candidate)) {
    candidate = `0x${candidate}`;
  }
  if (!/^0x[0-9a-fA-F]{40}$/.test(candidate)) {
    return null;
  }
  try {
    return ethers.getAddress(candidate);
  } catch (_) {
    try {
      return ethers.getAddress(candidate.toLowerCase());
    } catch (_) {
      return null;
    }
  }
}

function toUnixSeconds(secondsFromNow) {
  return Math.floor(Date.now() / 1000) + Number(secondsFromNow);
}

function formatDateTimeLocal(date) {
  const pad2 = (n) => String(n).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}` +
    `T${pad2(date.getHours())}:${pad2(date.getMinutes())}`
  );
}

function ensureDefaultAbsoluteBettingClose() {
  if ($("bettingCloseAt").value) return;
  const relativeSeconds = Number($("bettingCloseIn").value);
  const fallbackSeconds = Number.isFinite(relativeSeconds) && relativeSeconds > 0 ? relativeSeconds : 7200;
  const closeDate = new Date(Date.now() + fallbackSeconds * 1000);
  $("bettingCloseAt").value = formatDateTimeLocal(closeDate);
}

function estimateBettingCloseFromInputs(nowSec) {
  if ($("bettingNoMax").checked) return null;
  const mode = $("bettingCloseMode").value;
  if (mode === "absolute") {
    const raw = $("bettingCloseAt").value.trim();
    if (!raw) return null;
    const tsMs = new Date(raw).getTime();
    if (!Number.isFinite(tsMs)) return null;
    return Math.floor(tsMs / 1000);
  }
  const closeIn = Number($("bettingCloseIn").value);
  if (!Number.isFinite(closeIn) || closeIn <= 0) return null;
  return Math.floor(nowSec) + Math.floor(closeIn);
}

function ensureDefaultAbsoluteResolutionClose() {
  if ($("resolutionCloseAt").value) return;
  const nowSec = Math.floor(Date.now() / 1000);
  const bettingCloseSec = estimateBettingCloseFromInputs(nowSec);
  const relativeSeconds = Number($("resolutionWindow").value);
  const fallbackSeconds = Number.isFinite(relativeSeconds) && relativeSeconds > 0 ? relativeSeconds : 7200;
  const anchorSec = Number.isFinite(bettingCloseSec) ? bettingCloseSec : nowSec;
  const closeDate = new Date((anchorSec + fallbackSeconds) * 1000);
  $("resolutionCloseAt").value = formatDateTimeLocal(closeDate);
}

function parseAmount(amountNumber, decimals) {
  // amountNumber is entered in whole tokens (e.g. "10" -> 10 tokens)
  const amountStr = String(amountNumber);
  return ethers.parseUnits(amountStr, decimals);
}

function formatRatio(numerator, denominator, precision) {
  if (denominator === 0n) return "N/A";
  const p = BigInt(precision);
  const scale = 10n ** p;
  const scaled = (numerator * scale) / denominator;
  const whole = scaled / scale;
  const frac = (scaled % scale).toString().padStart(precision, "0");
  return `${whole}.${frac}`;
}

function formatTokenAmount(amount, decimals, maxFractionDigits = 6) {
  const s = ethers.formatUnits(amount, decimals);
  const n = Number(s);
  if (Number.isFinite(n)) {
    return n.toLocaleString(undefined, { maximumFractionDigits: maxFractionDigits });
  }
  return s;
}

function clearOddsPreview(message) {
  $("oddsCurrentMultiple").value = "";
  $("oddsAfterMultiple").value = "";
  $("oddsExpectedPayout").value = "";
  $("oddsExpectedProfit").value = "";
  $("oddsStatus").textContent = message || "";
}

function netPot(totalPot, totalFeeBps) {
  return totalPot - ((totalPot * totalFeeBps) / 10000n);
}

async function updateOddsPreviewFreeform() {
  const answer = $("betOutcomeIndex").value.trim();
  if (!answer) {
    clearOddsPreview("Enter answer text to preview payout (exact bytes matter).");
    return;
  }
  const b = ethers.toUtf8Bytes(answer);
  if (b.length > 1024) {
    clearOddsPreview("Answer exceeds 1024 UTF-8 bytes (on-chain limit).");
    return;
  }
  const amountNumber = Number($("betAmount").value);
  if (!Number.isFinite(amountNumber) || amountNumber <= 0) {
    clearOddsPreview("Enter a positive bet amount to preview payout.");
    return;
  }

  const state = Number(await wagerContract.state());
  if (state !== 0) {
    clearOddsPreview("Wager is not open. Odds preview is only shown for open wagers.");
    return;
  }

  const answerId = ethers.keccak256(b);
  const collateralTokenAddress = await wagerContract.collateralToken();
  const decimals = await resolveBettingDecimals(collateralTokenAddress);
  const betAmount = parseAmount(amountNumber, decimals);

  const [totalPot, totalFeeBps, pool] = await Promise.all([
    wagerContract.totalPot(),
    wagerContract.totalFeeBps(),
    wagerContract.ticketPoolTotal(answerId),
  ]);

  const netBefore = netPot(totalPot, totalFeeBps);
  const currentMultiple =
    pool > 0n ? `${formatRatio(netBefore, pool, 4)}x` : "N/A (no stake yet on this answer)";

  const totalPotAfter = totalPot + betAmount;
  const netAfter = netPot(totalPotAfter, totalFeeBps);
  const poolAfter = pool + betAmount;

  const payoutPreview = (betAmount * netAfter) / poolAfter;
  const profitPreview = payoutPreview - betAmount;
  const afterMultiple = `${formatRatio(netAfter, poolAfter, 4)}x`;

  $("oddsCurrentMultiple").value = currentMultiple;
  $("oddsAfterMultiple").value = afterMultiple;
  $("oddsExpectedPayout").value = formatTokenAmount(payoutPreview, decimals);
  $("oddsExpectedProfit").value = formatTokenAmount(profitPreview, decimals);
  $("oddsStatus").textContent =
    "Freeform single-pool preview (same math as v1 single-outcome). Resolver must call resolve() with identical string bytes.";
}

async function updateOddsPreviewV2() {
  const amountNumber = Number($("betAmount").value);
  if (!Number.isFinite(amountNumber) || amountNumber <= 0) {
    clearOddsPreview("Enter a positive bet amount to preview payout.");
    return;
  }

  const state = Number(await wagerContract.state());
  if (state !== 0) {
    clearOddsPreview("Wager is not open. Odds preview is only shown for open wagers.");
    return;
  }

  const outcomesCount = Number(await wagerContract.outcomesCount());
  let mask;
  try {
    mask = Logic.parseOutcomeIndicesCsvToTicketMask($("betOutcomeIndex").value, outcomesCount);
  } catch (e) {
    clearOddsPreview(e.message || "Invalid ticket indices.");
    return;
  }

  const policy = Number(await wagerContract.payoffPolicy());
  if (policy === Logic.PAYOFF_POLICY.SINGLE_WINNER && Logic.popcountMask(mask) !== 1) {
    clearOddsPreview("SINGLE_WINNER wagers require exactly one outcome index in the ticket.");
    return;
  }

  const collateralTokenAddress = await wagerContract.collateralToken();
  const decimals = await resolveBettingDecimals(collateralTokenAddress);
  const betAmount = parseAmount(amountNumber, decimals);

  const [totalPot, totalFeeBps, pool] = await Promise.all([
    wagerContract.totalPot(),
    wagerContract.totalFeeBps(),
    wagerContract.ticketPoolTotal(mask),
  ]);

  if (policy === Logic.PAYOFF_POLICY.SINGLE_WINNER) {
    const netBefore = netPot(totalPot, totalFeeBps);
    const currentMultiple =
      pool > 0n ? `${formatRatio(netBefore, pool, 4)}x` : "N/A (no stake yet on this ticket)";

    const totalPotAfter = totalPot + betAmount;
    const netAfter = netPot(totalPotAfter, totalFeeBps);
    const poolAfter = pool + betAmount;

    const payoutPreview = (betAmount * netAfter) / poolAfter;
    const profitPreview = payoutPreview - betAmount;
    const afterMultiple = `${formatRatio(netAfter, poolAfter, 4)}x`;

    $("oddsCurrentMultiple").value = currentMultiple;
    $("oddsAfterMultiple").value = afterMultiple;
    $("oddsExpectedPayout").value = formatTokenAmount(payoutPreview, decimals);
    $("oddsExpectedProfit").value = formatTokenAmount(profitPreview, decimals);
    $("oddsStatus").textContent =
      "SINGLE_WINNER preview (this ticket wins only if it matches the single resolved outcome). " +
      "Integer rounding; other bets may change the pool first.";
    return;
  }

  $("oddsCurrentMultiple").value = "";
  $("oddsAfterMultiple").value = "";
  $("oddsExpectedPayout").value = "";
  $("oddsExpectedProfit").value = "";
  $("oddsStatus").textContent =
    `${Logic.payoffPolicyLabel(policy)}: stake pools under this ticket mask = ${formatTokenAmount(
      pool,
      decimals
    )} (raw mask ${mask.toString()}). ` +
    `Settlement splits netPot by policy vs the resolver’s winning set — see docs/PAYOUT-CALCULATION.md Part B; ` +
    `no single “if I win” multiple without knowing W.`;
}

async function updateOddsPreview() {
  if (!wagerContract) {
    clearOddsPreview("Create a wager first to preview odds.");
    return;
  }

  if (activeWagerProtocol === "freeform") {
    try {
      await updateOddsPreviewFreeform();
    } catch (e) {
      clearOddsPreview(`Could not compute odds preview: ${e.message}`);
    }
    return;
  }

  if (activeWagerProtocol === "v2") {
    try {
      await updateOddsPreviewV2();
    } catch (e) {
      clearOddsPreview(`Could not compute odds preview: ${e.message}`);
    }
    return;
  }

  try {
    const rawBet = $("betOutcomeIndex").value.trim();
    if (/[,\s]/.test(rawBet)) {
      clearOddsPreview("v1 wagers use a single outcome index (no commas).");
      return;
    }
    const outcomeIndex = Number(rawBet);
    const amountNumber = Number($("betAmount").value);
    if (!Number.isFinite(outcomeIndex) || outcomeIndex < 0 || !Number.isInteger(outcomeIndex)) {
      clearOddsPreview("Enter a valid outcome index.");
      return;
    }
    if (!Number.isFinite(amountNumber) || amountNumber <= 0) {
      clearOddsPreview("Enter a positive bet amount to preview payout.");
      return;
    }

    const state = Number(await wagerContract.state());
    if (state !== 0) {
      clearOddsPreview("Wager is not open. Odds preview is only shown for open wagers.");
      return;
    }

    const outcomesCount = Number(await wagerContract.outcomesCount());
    if (outcomeIndex >= outcomesCount) {
      clearOddsPreview(`Outcome index out of range (0-${outcomesCount - 1}).`);
      return;
    }

    const collateralTokenAddress = await wagerContract.collateralToken();
    const decimals = await resolveBettingDecimals(collateralTokenAddress);
    const betAmount = parseAmount(amountNumber, decimals);

    const [totalPot, totalFeeBps, outcomeTotal] = await Promise.all([
      wagerContract.totalPot(),
      wagerContract.totalFeeBps(),
      wagerContract.outcomeTotals(outcomeIndex),
    ]);

    const netBefore = netPot(totalPot, totalFeeBps);
    const currentMultiple =
      outcomeTotal > 0n ? `${formatRatio(netBefore, outcomeTotal, 4)}x` : "N/A (no stake yet)";

    const totalPotAfter = totalPot + betAmount;
    const netAfter = netPot(totalPotAfter, totalFeeBps);
    const outcomeTotalAfter = outcomeTotal + betAmount;

    const payoutPreview = (betAmount * netAfter) / outcomeTotalAfter;
    const profitPreview = payoutPreview - betAmount;
    const afterMultiple = `${formatRatio(netAfter, outcomeTotalAfter, 4)}x`;

    $("oddsCurrentMultiple").value = currentMultiple;
    $("oddsAfterMultiple").value = afterMultiple;
    $("oddsExpectedPayout").value = formatTokenAmount(payoutPreview, decimals);
    $("oddsExpectedProfit").value = formatTokenAmount(profitPreview, decimals);
    $("oddsStatus").textContent =
      "Preview uses on-chain integer rounding and may change if other bets arrive first.";
  } catch (e) {
    clearOddsPreview(`Could not compute odds preview: ${e.message}`);
  }
}

const ERC20_DECIMALS_ABI = ["function decimals() view returns (uint8)"];

/**
 * Read ERC-20 decimals() from chain (standard safeguard vs manual entry).
 * Some tokens return uint256; ethers normalizes to number.
 */
async function fetchTokenDecimals(tokenAddress) {
  if (!tokenAddress || !ethers.isAddress(tokenAddress)) {
    throw new Error("Invalid token address");
  }
  if (!provider) {
    throw new Error("Connect wallet first so the app can read decimals() from the token.");
  }
  const c = new ethers.Contract(tokenAddress, ERC20_DECIMALS_ABI, provider);
  const d = await c.decimals();
  const n = Number(d);
  if (!Number.isFinite(n) || n < 0 || n > 77) {
    throw new Error(`Unusual decimals() value: ${d}. Use manual override.`);
  }
  return n;
}

function syncDecimalsInputReadOnly() {
  const manual = $("decimalsManual").checked;
  $("decimals").readOnly = !manual;
  $("decimals").title = manual
    ? "Manual override active"
    : "Filled automatically from token decimals(); check Manual override to edit.";
}

function syncWindowInputState() {
  const bettingNoMax = $("bettingNoMax").checked;
  const bettingMode = $("bettingCloseMode").value;
  const resolutionNoMax = $("resolutionNoMax").checked;
  const resolutionMode = $("resolutionWindowMode").value;

  $("bettingCloseIn").readOnly = bettingNoMax || bettingMode !== "relative";
  $("bettingCloseAt").disabled = bettingNoMax || bettingMode !== "absolute";
  $("bettingCloseInWrap").style.display = !bettingNoMax && bettingMode === "relative" ? "" : "none";
  $("bettingCloseAtWrap").style.display = !bettingNoMax && bettingMode === "absolute" ? "" : "none";
  if (!bettingNoMax && bettingMode === "absolute") {
    ensureDefaultAbsoluteBettingClose();
  }

  $("resolutionWindow").readOnly = resolutionNoMax || resolutionMode !== "relative";
  $("resolutionCloseAt").disabled = resolutionNoMax || resolutionMode !== "absolute";
  $("resolutionWindowWrap").style.display = !resolutionNoMax && resolutionMode === "relative" ? "" : "none";
  $("resolutionCloseAtWrap").style.display =
    !resolutionNoMax && resolutionMode === "absolute" ? "" : "none";
  if (!resolutionNoMax && resolutionMode === "absolute") {
    ensureDefaultAbsoluteResolutionClose();
  }
}

function populateCollateralPresets() {
  const select = $("collateralPreset");
  const previous = select.value;
  select.innerHTML = "";

  const custom = document.createElement("option");
  custom.value = "custom";
  custom.textContent = "Custom token address";
  select.appendChild(custom);

  const chainIds = Object.keys(TOKEN_PRESETS).map(Number);
  for (const chainId of chainIds) {
    const tokens = TOKEN_PRESETS[chainId] || [];
    for (const token of tokens) {
      const option = document.createElement("option");
      option.value = tokenPresetValue(chainId, token);
      option.textContent = `${token.symbol} (${chainName(chainId)})`;
      select.appendChild(option);
    }
  }

  if (previous && [...select.options].some((opt) => opt.value === previous)) {
    select.value = previous;
  } else {
    select.value = "custom";
  }
}

async function applySelectedCollateralPreset() {
  const presetRaw = $("collateralPreset").value;
  if (presetRaw === "custom") return;

  const preset = parseTokenPresetValue(presetRaw);
  const normalizedPresetAddress = normalizeAddressInput(preset.address);
  if (!normalizedPresetAddress) {
    throw new Error(`Preset token address is invalid for ${preset.symbol}.`);
  }
  $("collateralToken").value = normalizedPresetAddress;

  if (!$("decimalsManual").checked) {
    $("decimals").value = String(preset.decimals);
  }

  let message = `Selected ${preset.symbol} on ${chainName(preset.chainId)} (${preset.address}).`;
  if (currentChainId !== null && currentChainId !== preset.chainId) {
    message += ` Wallet is connected to ${chainName(currentChainId)}; switch network before transacting.`;
    $("tokenMeta").textContent = message;
    return;
  }

  $("tokenMeta").textContent = message;
  await tryDetectDecimalsFromCollateralField();
}

async function refreshConnectedNetwork() {
  if (!provider) {
    currentChainId = null;
    $("networkStatus").textContent = "Network: connect wallet to detect chain.";
    populateCollateralPresets();
    applyDefaultFactoryAddress();
    return;
  }

  const network = await provider.getNetwork();
  currentChainId = Number(network.chainId);
  $("networkStatus").textContent = `Network: ${chainName(currentChainId)} (chainId ${currentChainId})`;
  populateCollateralPresets();
  applyDefaultFactoryAddress();
}

async function ensureContractExistsOnCurrentNetwork(address, label) {
  if (!provider) return;
  const code = await provider.getCode(address);
  if (code === "0x") {
    throw new Error(
      `${label} has no contract code on ${chainName(currentChainId)}. Check network and address.`
    );
  }
}

/**
 * Decimals used when parsing bet amounts: chain by default, manual if checked.
 */
async function resolveBettingDecimals(tokenAddress) {
  if ($("decimalsManual").checked) {
    const d = Number($("decimals").value);
    if (!Number.isFinite(d) || d < 0 || d > 77) {
      throw new Error("Invalid manual decimals (use 0–77).");
    }
    return d;
  }
  const d = await fetchTokenDecimals(tokenAddress);
  $("decimals").value = String(d);
  const sym = (await resolveTokenSymbolForDisplay(tokenAddress)) || null;
  const a = ethers.getAddress(tokenAddress);
  $("tokenMeta").textContent = sym
    ? `${sym} (${a}) — Token decimals: ${d} (read from token contract).`
    : `Token decimals: ${d} (read from token contract).`;
  return d;
}

async function tryDetectDecimalsFromCollateralField() {
  if ($("decimalsManual").checked) return;
  const addr = normalizeAddressInput($("collateralToken").value);
  if (!addr) {
    $("tokenMeta").textContent = "Enter a valid token address, then tab away to detect decimals.";
    return;
  }
  $("collateralToken").value = addr;
  const checksum = ethers.getAddress(addr);
  const symPreset = knownSymbolForToken(currentChainId, addr);
  if (!provider) {
    $("tokenMeta").textContent = symPreset
      ? `${symPreset} (${checksum}) — Connect wallet to read decimals() from the token.`
      : "Connect wallet to read decimals() from the token.";
    return;
  }
  try {
    const d = await fetchTokenDecimals(addr);
    $("decimals").value = String(d);
    const sym = symPreset || (await fetchTokenSymbolFromChain(addr));
    $("tokenMeta").textContent = sym
      ? `${sym} (${checksum}) — Token decimals: ${d} (read from token contract).`
      : `Token decimals: ${d} (read from token contract).`;
  } catch (e) {
    let sym = symPreset;
    if (!sym) {
      try {
        sym = await fetchTokenSymbolFromChain(addr);
      } catch (_) {
        sym = null;
      }
    }
    $("tokenMeta").textContent = sym
      ? `${sym} (${checksum}) — Could not read decimals(): ${e.message} — enable Manual decimals override.`
      : `Could not read decimals(): ${e.message} — enable Manual decimals override.`;
  }
}

async function fetchAbiWithFallback(primary, fallback) {
  try {
    const r = await fetch(primary);
    if (!r.ok) throw new Error(r.status);
    return (await r.json()).abi;
  } catch (_) {
    const r2 = await fetch(fallback);
    if (!r2.ok) throw new Error("ABI not found at " + primary + " or " + fallback);
    return (await r2.json()).abi;
  }
}

async function loadDeploymentsConfig() {
  try {
    const response = await fetch(DEPLOYMENTS_CONFIG_URL);
    if (!response.ok) return;
    deploymentsConfig = await response.json();
    applySiteDeploymentNetworkFromUrl();
  } catch (_) {
    // Optional for local/dev runs; manual factory entry still works.
  }
}

async function loadAbi() {
  [factoryAbiV1, wagerAbiV1, factoryAbiV2, wagerAbiV2, factoryAbiFF, wagerAbiFF] = await Promise.all([
    fetchAbiWithFallback(FACTORY_ABI_URL, FACTORY_ABI_FALLBACK),
    fetchAbiWithFallback(WAGER_ABI_URL, WAGER_ABI_FALLBACK),
    fetchAbiWithFallback(FACTORY_ABI_V2_URL, FACTORY_ABI_V2_FALLBACK),
    fetchAbiWithFallback(WAGER_ABI_V2_URL, WAGER_ABI_V2_FALLBACK),
    fetchAbiWithFallback(FACTORY_ABI_FF_URL, FACTORY_ABI_FF_FALLBACK),
    fetchAbiWithFallback(WAGER_ABI_FF_URL, WAGER_ABI_FF_FALLBACK),
  ]);
}

async function connectWallet() {
  const eip1193 = resolveEip1193Provider();
  if (!eip1193 || typeof eip1193.request !== "function") {
    throw new Error(
      "No EIP-1193 wallet found. Use a browser extension (MetaMask, Rabby, Coinbase Wallet, Frame, …) or any wallet that injects a compliant `window.ethereum` provider."
    );
  }

  provider = new ethers.BrowserProvider(eip1193);
  await provider.send("eth_requestAccounts", []);
  signer = await provider.getSigner();
  userAddress = await signer.getAddress();
  await refreshConnectedNetwork();

  $("walletAddr").textContent = userAddress;
  $("walletStatus").textContent = "Connected.";
  await tryDetectDecimalsFromCollateralField();

  if (wagerAddressFromUrl) {
    try {
      await setActiveWager(wagerAddressFromUrl);
      $("betStatus").textContent = "Loaded wager from URL.";
    } catch (e) {
      $("betStatus").textContent = `Could not load wager from link: ${e.message}`;
    }
  }

  if (!walletListenersAttached && typeof eip1193.on === "function") {
    eip1193.on("chainChanged", async () => {
      const next = resolveEip1193Provider() || eip1193;
      provider = new ethers.BrowserProvider(next);
      signer = await provider.getSigner();
      await refreshConnectedNetwork();
      $("walletStatus").textContent = "Network changed. Review factory/token before transacting.";
      await tryDetectDecimalsFromCollateralField();
    });
    eip1193.on("accountsChanged", async () => {
      if (!provider) return;
      signer = await provider.getSigner();
      userAddress = await signer.getAddress();
      $("walletAddr").textContent = userAddress;
    });
    walletListenersAttached = true;
  }
}

async function getFactoryConstraints(factoryAddress, protocol = "v1") {
  await ensureContractExistsOnCurrentNetwork(factoryAddress, "Factory address");
  const abi =
    protocol === "v2" ? factoryAbiV2 : protocol === "freeform" ? factoryAbiFF : factoryAbiV1;
  const factory = new ethers.Contract(factoryAddress, abi, provider);
  const minBettingWindow = await factory.minBettingWindow();
  const minResolutionWindow = await factory.minResolutionWindow();
  return { minBettingWindow, minResolutionWindow };
}

function getRunner() {
  if (signer) return signer;
  if (provider) return provider;
  throw new Error("Connect wallet first.");
}

async function setActiveWager(wagerAddress) {
  if (!ethers.isAddress(wagerAddress)) throw new Error("Invalid wager address.");
  await ensureContractExistsOnCurrentNetwork(wagerAddress, "Wager address");

  const commonProbe = new ethers.Contract(
    wagerAddress,
    ["function outcomesCount() view returns (uint256)"],
    provider
  );
  const oc = await commonProbe.outcomesCount();
  let protocol = "v1";
  if (oc === 0n) {
    protocol = "freeform";
  } else {
    const probe = new ethers.Contract(
      wagerAddress,
      ["function payoffPolicy() view returns (uint8)"],
      provider
    );
    try {
      await probe.payoffPolicy();
      protocol = "v2";
    } catch {
      protocol = "v1";
    }
  }
  activeWagerProtocol = protocol;
  const wagerAbi =
    protocol === "v2" ? wagerAbiV2 : protocol === "freeform" ? wagerAbiFF : wagerAbiV1;
  wagerContract = new ethers.Contract(wagerAddress, wagerAbi, getRunner());

  $("wagerAddress").textContent = wagerAddress;
  $("activeWagerAddress").value = wagerAddress;
  if (!$("resolutionWagerAddress").value.trim()) {
    $("resolutionWagerAddress").value = wagerAddress;
  }
  if (!$("claimsWagerAddress").value.trim()) {
    $("claimsWagerAddress").value = wagerAddress;
  }

  const metaEl = $("activeWagerCollateralMeta");
  if (metaEl) {
    metaEl.hidden = false;
    metaEl.textContent = "Reading collateral token…";
    try {
      const tokenAddr = await wagerContract.collateralToken();
      const sym = await resolveTokenSymbolForDisplay(tokenAddr);
      const disp = ethers.getAddress(tokenAddr);
      let line = sym ? `Collateral: ${sym} (${disp})` : `Collateral: ${disp}`;
      if (protocol === "freeform") {
        line += " · Protocol freeform (ADR-0009 text answers; resolve(string) must match bet bytes)";
      } else if (protocol === "v2") {
        const pol = await wagerContract.payoffPolicy();
        line += ` · Protocol v2 · ${Logic.payoffPolicyLabel(pol)}`;
      } else {
        line += " · Protocol v1 (single-outcome resolution)";
      }
      metaEl.textContent = line;
    } catch (e) {
      metaEl.textContent = "Could not read collateral token: " + e.message;
    }
  }

  syncBettingAndResolutionLabels();
  await updateOddsPreview();
}

function syncBettingAndResolutionLabels() {
  const v2 = activeWagerProtocol === "v2";
  const ff = activeWagerProtocol === "freeform";
  const betLab = $("betOutcomeFieldLabel");
  if (betLab) {
    betLab.textContent = ff
      ? "Answer text (exact UTF-8 bytes; ticket id = keccak256(bytes))"
      : v2
        ? "Ticket — outcome indices (comma-separated bitmask)"
        : "Outcome index (single integer)";
  }
  const winLab = $("winningOutcomeFieldLabel");
  if (winLab) {
    winLab.textContent = ff
      ? "Winning answer (exact UTF-8 string)"
      : v2
        ? "Winning set — outcome indices (comma-separated)"
        : "Winning outcome index";
  }
  const betPh = $("betOutcomeIndex");
  if (betPh) {
    betPh.placeholder = ff ? "e.g. Paris" : v2 ? "e.g. 0 or 0,2 for A and C" : "0";
  }
  const winPh = $("winningOutcomeIndex");
  if (winPh) {
    winPh.placeholder = ff ? "exact winning text" : v2 ? "e.g. 0,2 — exact true set" : "0";
  }
}

async function ensureWagerForPlannedAction(actionName) {
  const plan = Logic.planWagerAction(actionName, {
    resolutionWagerAddress: $("resolutionWagerAddress").value,
    claimsWagerAddress: $("claimsWagerAddress").value,
    activeWagerAddress: $("activeWagerAddress").value,
  });
  if (!ethers.isAddress(plan.targetAddress)) {
    throw new Error(`Invalid wager address for ${actionName}.`);
  }
  if (
    !wagerContract ||
    String(wagerContract.target || "").toLowerCase() !== plan.targetAddress.toLowerCase()
  ) {
    await setActiveWager(plan.targetAddress);
  }
  if (!wagerContract) throw new Error("Failed to load target wager.");
  return { plan, targetWager: wagerContract };
}

async function runWagerAction(actionName, ...args) {
  const { plan, targetWager } = await ensureWagerForPlannedAction(actionName);
  const method = plan.method;
  if (typeof targetWager[method] !== "function") {
    throw new Error(`Wager contract does not support action method ${method}.`);
  }
  const tx = await targetWager[method](...args);
  await tx.wait();
  return wagerContract;
}

async function createWager() {
  const factoryAddressInput = normalizeAddressInput($("factoryAddress").value);
  const collateralTokenInput = normalizeAddressInput($("collateralToken").value);
  const outcomesCsv = $("outcomes").value.trim();
  const proposition = $("proposition").value.trim();

  const bettingCloseIn = Number($("bettingCloseIn").value);
  const resolutionWindow = Number($("resolutionWindow").value);
  const bettingNoMax = $("bettingNoMax").checked;
  const resolutionNoMax = $("resolutionNoMax").checked;
  const bettingCloseMode = $("bettingCloseMode").value;
  const resolutionWindowMode = $("resolutionWindowMode").value;
  const bettingCloseAtRaw = $("bettingCloseAt").value.trim();
  const resolutionCloseAtRaw = $("resolutionCloseAt").value.trim();
  const extraFeeRecipientsCsv = $("extraFeeRecipients").value.trim();
  const extraFeeBpsCsv = $("extraFeeBps").value.trim();
  const seedOutcomeIndicesCsv = $("seedOutcomeIndices").value.trim();
  const seedAmountsCsv = $("seedAmounts").value.trim();
  const resolverInput = normalizeAddressInput($("resolverAddress").value);
  const bettingCloserInput = normalizeAddressInput($("bettingCloserAddress").value);
  const resolutionCloserInput = normalizeAddressInput($("resolutionCloserAddress").value);

  if (!factoryAddressInput) throw new Error("Factory address is required.");
  if (!collateralTokenInput) throw new Error("Collateral token is required.");
  if (!proposition) throw new Error("Proposition is required.");
  const protocol = $("protocolVersion") ? $("protocolVersion").value : "v1";
  if (protocol !== "freeform" && !outcomesCsv) throw new Error("Outcomes are required.");
  if (factoryAddressInput === null) throw new Error("Factory address is invalid.");
  if (collateralTokenInput === null) {
    throw new Error("Collateral token address is invalid. Use a 0x... ERC-20 address.");
  }
  if (resolverInput === null) throw new Error("Invalid resolver address.");
  if (bettingCloserInput === null) throw new Error("Invalid betting closer address.");
  if (resolutionCloserInput === null) throw new Error("Invalid resolution closer address.");

  const factoryAddress = factoryAddressInput;
  const collateralToken = collateralTokenInput;
  $("factoryAddress").value = factoryAddress;
  $("collateralToken").value = collateralToken;
  if (resolverInput) $("resolverAddress").value = resolverInput;
  if (bettingCloserInput) $("bettingCloserAddress").value = bettingCloserInput;
  if (resolutionCloserInput) $("resolutionCloserAddress").value = resolutionCloserInput;

  const presetRaw = $("collateralPreset").value;
  if (presetRaw !== "custom" && currentChainId !== null) {
    const preset = parseTokenPresetValue(presetRaw);
    if (preset.chainId !== currentChainId) {
      throw new Error(
        `Selected token preset is for ${chainName(preset.chainId)}, but wallet is on ${chainName(
          currentChainId
        )}. Switch your wallet to ${chainName(preset.chainId)} and retry.`
      );
    }
  }

  const outcomes = protocol === "freeform" ? [] : parseCsvToArray(outcomesCsv);
  if (protocol !== "freeform" && outcomes.length < 2) throw new Error("Need at least 2 outcomes.");

  if (protocol !== "freeform" && outcomes.length > 255) {
    throw new Error("Factory allows at most 255 outcomes.");
  }

  const extraFeeRecipients = extraFeeRecipientsCsv
    ? parseCsvToArray(extraFeeRecipientsCsv)
    : [];

  const extraFeeBps = extraFeeBpsCsv ? parseCsvToArray(extraFeeBpsCsv).map((x) => Number(x)) : [];

  if (extraFeeRecipients.length !== extraFeeBps.length) {
    throw new Error("extraFeeRecipients and extraFeeBps length mismatch.");
  }
  const seedParsed =
    protocol === "freeform"
      ? { outcomeIndices: [], amountNumbers: [] }
      : Logic.parseMultiBetInputs(seedOutcomeIndicesCsv, seedAmountsCsv, true);
  if (protocol !== "freeform") {
    for (const idx of seedParsed.outcomeIndices) {
      if (idx >= outcomes.length) {
        throw new Error(`Seed outcome index ${idx} out of range (0-${outcomes.length - 1}).`);
      }
    }
  }

  const nowSec = Math.floor(Date.now() / 1000);
  let bettingCloseAtSec = null;
  if (!bettingNoMax && bettingCloseMode === "absolute") {
    if (!bettingCloseAtRaw) {
      throw new Error("Bet close date/time is required for absolute mode.");
    }
    const betCloseMs = new Date(bettingCloseAtRaw).getTime();
    if (!Number.isFinite(betCloseMs)) {
      throw new Error("Bet close date/time is invalid.");
    }
    bettingCloseAtSec = Math.floor(betCloseMs / 1000);
  }
  let resolutionCloseAtSec = null;
  if (!resolutionNoMax && resolutionWindowMode === "absolute") {
    if (!resolutionCloseAtRaw) {
      throw new Error("Resolution close date/time is required for absolute mode.");
    }
    const resolutionCloseMs = new Date(resolutionCloseAtRaw).getTime();
    if (!Number.isFinite(resolutionCloseMs)) {
      throw new Error("Resolution close date/time is invalid.");
    }
    resolutionCloseAtSec = Math.floor(resolutionCloseMs / 1000);
  }

  const { closeTime, resolutionWindowArg } = Logic.computeWindowArgs(
    nowSec,
    bettingCloseIn,
    resolutionWindow,
    bettingNoMax,
    resolutionNoMax,
    bettingCloseMode,
    bettingCloseAtSec,
    resolutionWindowMode,
    resolutionCloseAtSec
  );

  // Optional UI-side validation with factory constraints (still will revert if wrong).
  const { minBettingWindow, minResolutionWindow } = await getFactoryConstraints(factoryAddress, protocol);
  const effectiveBettingCloseIn = bettingNoMax ? 0 : Math.max(0, closeTime - nowSec);
  const warnings = Logic.validateWindowMins(
    minBettingWindow,
    minResolutionWindow,
    effectiveBettingCloseIn,
    resolutionWindowArg,
    bettingNoMax,
    resolutionNoMax
  );
  $("factoryConstraints").textContent =
    `Factory constraints: minBettingWindow=${minBettingWindow}, minResolutionWindow=${minResolutionWindow}` +
    " (window values of 0 enable no-max mode)" +
    (warnings.length ? `; Warning: ${warnings.join("; ")}` : "");

  const factoryAbi =
    protocol === "v2" ? factoryAbiV2 : protocol === "freeform" ? factoryAbiFF : factoryAbiV1;
  const factory = new ethers.Contract(factoryAddress, factoryAbi, signer);

  let resolverArg = ethers.ZeroAddress;
  if (resolverInput && resolverInput.length > 0) {
    resolverArg = resolverInput;
  }

  let bettingCloserArg = ethers.ZeroAddress;
  if (bettingCloserInput && bettingCloserInput.length > 0) {
    bettingCloserArg = bettingCloserInput;
  }

  let resolutionCloserArg = ethers.ZeroAddress;
  if (resolutionCloserInput && resolutionCloserInput.length > 0) {
    resolutionCloserArg = resolutionCloserInput;
  }
  if (bettingNoMax && bettingCloserArg === ethers.ZeroAddress) {
    throw new Error("No max betting window requires a betting closer address.");
  }
  if (resolutionNoMax && resolutionCloserArg === ethers.ZeroAddress) {
    throw new Error("No max resolution window requires a resolution closer address.");
  }

  let seedAmountsRaw = [];
  let seedTotalAmount = 0n;
  if (seedParsed.outcomeIndices.length > 0) {
    const decimals = await resolveBettingDecimals(collateralToken);
    seedAmountsRaw = seedParsed.amountNumbers.map((n) => parseAmount(n, decimals));
    for (const amount of seedAmountsRaw) seedTotalAmount += amount;
  }

  if (seedAmountsRaw.length > 0) {
    const erc20Abi = ["function approve(address spender,uint256 amount) external returns (bool)"];
    const token = new ethers.Contract(collateralToken, erc20Abi, signer);
    $("createStatus").textContent = "Approving collateral for seed liquidity...";
    const approveTx = await token.approve(factoryAddress, seedTotalAmount);
    await approveTx.wait();
  }

  $("createStatus").textContent = "Submitting create wager transaction...";
  let receipt;
  if (protocol === "freeform") {
    const tx = await factory.createFreeformWager(
      collateralToken,
      proposition,
      BigInt(closeTime),
      BigInt(resolutionWindowArg),
      resolverArg,
      bettingCloserArg,
      resolutionCloserArg,
      extraFeeRecipients,
      extraFeeBps
    );
    receipt = await tx.wait();
  } else if (protocol === "v2") {
    const payoffPolicy = Number($("payoffPolicy").value);
    const policyParamRaw = Number($("policyParam").value);
    if (!Number.isInteger(payoffPolicy) || payoffPolicy < 0 || payoffPolicy > 4) {
      throw new Error("Invalid payoff policy (0–4).");
    }
    Logic.validatePolicyParamForCreate(payoffPolicy, policyParamRaw, outcomes.length);
    const policyParam =
      payoffPolicy === Logic.PAYOFF_POLICY.AT_LEAST_K ? BigInt(Math.floor(policyParamRaw)) : 0n;
    const seedMasks =
      seedParsed.outcomeIndices.length > 0
        ? Logic.seedOutcomeIndicesToTicketMasks(seedParsed.outcomeIndices)
        : [];
    if (seedMasks.length > 0 && payoffPolicy === Logic.PAYOFF_POLICY.SINGLE_WINNER) {
      for (const m of seedMasks) {
        if (Logic.popcountMask(m) !== 1) {
          throw new Error("SINGLE_WINNER seed tickets must be single-outcome indices only.");
        }
      }
    }
    const commonArgs = [
      collateralToken,
      proposition,
      outcomes,
      payoffPolicy,
      policyParam,
      BigInt(closeTime),
      BigInt(resolutionWindowArg),
      resolverArg,
      bettingCloserArg,
      resolutionCloserArg,
      extraFeeRecipients,
      extraFeeBps,
    ];
    const tx =
      seedMasks.length > 0
        ? await factory.createWager(...commonArgs, seedMasks, seedAmountsRaw)
        : await factory.createWager(...commonArgs);
    receipt = await tx.wait();
  } else {
    const tx = await factory[
      "createWager(address,string,string[],uint64,uint64,address,address,address,address[],uint16[],uint256[],uint256[])"
    ](
      collateralToken,
      proposition,
      outcomes,
      BigInt(closeTime),
      BigInt(resolutionWindowArg),
      resolverArg,
      bettingCloserArg,
      resolutionCloserArg,
      extraFeeRecipients,
      extraFeeBps,
      seedParsed.outcomeIndices,
      seedAmountsRaw
    );
    receipt = await tx.wait();
  }

  let wagerAddress = null;
  for (const log of receipt.logs) {
    try {
      const parsed = factory.interface.parseLog(log);
      if (
        parsed &&
        (parsed.name === "WagerCreated" ||
          parsed.name === "WagerCreatedV2" ||
          parsed.name === "WagerCreatedFreeform")
      ) {
        wagerAddress = parsed.args.wager;
        break;
      }
    } catch (_) {}
  }
  if (!wagerAddress) {
    throw new Error("WagerCreated / WagerCreatedV2 / WagerCreatedFreeform event not found in tx receipt.");
  }

  await setActiveWager(wagerAddress);
  $("createStatus").textContent = "Wager created.";
}

async function placeBet() {
  if (!wagerContract) throw new Error("Create a wager first.");

  const amountNumber = Number($("betAmount").value);
  const numOptions = Number(await wagerContract.outcomesCount());

  let placeArg;
  if (activeWagerProtocol === "freeform") {
    const answer = $("betOutcomeIndex").value.trim();
    if (!answer) {
      throw new Error("Enter the exact UTF-8 answer string to bet on (max 1024 bytes on-chain).");
    }
    const b = ethers.toUtf8Bytes(answer);
    if (b.length > 1024) throw new Error("Answer exceeds 1024 UTF-8 bytes.");
    placeArg = answer;
  } else if (activeWagerProtocol === "v2") {
    const mask = Logic.parseOutcomeIndicesCsvToTicketMask($("betOutcomeIndex").value.trim(), numOptions);
    const pol = Number(await wagerContract.payoffPolicy());
    if (pol === Logic.PAYOFF_POLICY.SINGLE_WINNER && Logic.popcountMask(mask) !== 1) {
      throw new Error("SINGLE_WINNER wagers require a ticket with exactly one outcome index.");
    }
    placeArg = mask;
  } else {
    const raw = $("betOutcomeIndex").value.trim();
    if (/[,\s]/.test(raw)) {
      throw new Error("v1 wagers use a single outcome index (no commas).");
    }
    const outcomeIndex = Number(raw);
    if (!Number.isInteger(outcomeIndex) || outcomeIndex < 0 || outcomeIndex >= numOptions) {
      throw new Error(`Outcome index must be an integer from 0 to ${numOptions - 1}.`);
    }
    placeArg = outcomeIndex;
  }

  const collateralTokenAddress = await wagerContract.collateralToken();
  const decimals = await resolveBettingDecimals(collateralTokenAddress);
  const erc20Abi = [
    "function approve(address spender,uint256 amount) external returns (bool)",
    "function transfer(address to,uint256 amount) external returns (bool)",
  ];
  const token = new ethers.Contract(collateralTokenAddress, erc20Abi, signer);

  const amount = parseAmount(amountNumber, decimals);

  $("betStatus").textContent = "Approving collateral...";
  const approveTx = await token.approve(wagerContract.target, amount);
  await approveTx.wait();

  $("betStatus").textContent = "Placing bet...";
  const tx = await wagerContract.placeBet(placeArg, amount);
  await tx.wait();
  $("betStatus").textContent = "Bet placed.";
  await updateOddsPreview();
}

async function placeBets() {
  if (!wagerContract) throw new Error("Create a wager first.");
  if (activeWagerProtocol === "freeform") {
    throw new Error("Freeform wagers only support placeBet(string,uint256). Use the single bet field above.");
  }

  const parsed = Logic.parseMultiBetInputs($("betOutcomeIndices").value, $("betAmounts").value, false);
  const numOpts = Number(await wagerContract.outcomesCount());
  for (const i of parsed.outcomeIndices) {
    if (i >= numOpts) {
      throw new Error(`Batch outcome index ${i} out of range (0-${numOpts - 1}).`);
    }
  }
  const collateralTokenAddress = await wagerContract.collateralToken();
  const decimals = await resolveBettingDecimals(collateralTokenAddress);
  const erc20Abi = [
    "function approve(address spender,uint256 amount) external returns (bool)",
    "function transfer(address to,uint256 amount) external returns (bool)",
  ];
  const token = new ethers.Contract(collateralTokenAddress, erc20Abi, signer);

  const amounts = parsed.amountNumbers.map((n) => parseAmount(n, decimals));
  let totalAmount = 0n;
  for (const amount of amounts) totalAmount += amount;

  $("betStatus").textContent = "Approving collateral for batch bet...";
  const approveTx = await token.approve(wagerContract.target, totalAmount);
  await approveTx.wait();

  $("betStatus").textContent = "Placing batch bet...";
  const legs = activeWagerProtocol === "v2" ? parsed.outcomeIndices.map((i) => 1n << BigInt(i)) : parsed.outcomeIndices;
  const tx = await wagerContract.placeBets(legs, amounts);
  await tx.wait();
  $("betStatus").textContent = "Batch bet placed.";
  await updateOddsPreview();
}

async function resolveWager() {
  let winningArg;
  const { targetWager } = await ensureWagerForPlannedAction("resolve");
  if (activeWagerProtocol === "freeform") {
    const ans = $("winningOutcomeIndex").value.trim();
    if (!ans) throw new Error("Enter the exact winning answer string (UTF-8 bytes must match a staked answer).");
    if (ethers.toUtf8Bytes(ans).length > 1024) throw new Error("Answer exceeds 1024 UTF-8 bytes.");
    winningArg = ans;
  } else if (activeWagerProtocol === "v2") {
    const numOptions = Number(await targetWager.outcomesCount());
    winningArg = Logic.parseOutcomeIndicesCsvToTicketMask($("winningOutcomeIndex").value.trim(), numOptions);
  } else {
    const raw = $("winningOutcomeIndex").value.trim();
    if (/[,\s]/.test(raw)) {
      throw new Error("v1 resolve uses a single winning outcome index (no commas).");
    }
    winningArg = Number(raw);
    if (!Number.isInteger(winningArg) || winningArg < 0) {
      throw new Error("Invalid winning outcome index.");
    }
    const numOptions = Number(await targetWager.outcomesCount());
    if (winningArg >= numOptions) {
      throw new Error(`Winning index out of range (0-${numOptions - 1}).`);
    }
  }

  $("resolutionStatus").textContent = "Resolving...";
  await runWagerAction("resolve", winningArg);
  $("resolutionStatus").textContent = "Resolved.";
  await updateOddsPreview();
}

async function retractWager() {
  $("resolutionStatus").textContent = "Retracting...";
  await runWagerAction("retract");
  $("resolutionStatus").textContent = "Retracted.";
  await updateOddsPreview();
}

async function expireWager() {
  $("resolutionStatus").textContent = "Expiring...";
  await runWagerAction("expire");
  $("resolutionStatus").textContent = "Expired.";
  await updateOddsPreview();
}

async function closeBettingOnWager() {
  $("resolutionStatus").textContent = "Closing betting...";
  await runWagerAction("closeBetting");
  $("resolutionStatus").textContent = "Betting closed (authority).";
  await updateOddsPreview();
}

async function closeResolutionWindowOnWager() {
  $("resolutionStatus").textContent = "Closing resolution window...";
  await runWagerAction("closeResolutionWindow");
  $("resolutionStatus").textContent = "Resolution window closed (authority).";
  await updateOddsPreview();
}

async function claim() {
  $("claimStatus").textContent = "Claiming payout...";
  await runWagerAction("claim");
  $("claimStatus").textContent = "Claimed (check token balance).";
}

async function withdrawFees() {
  $("claimStatus").textContent = "Withdrawing fees...";
  await runWagerAction("withdrawFees");
  $("claimStatus").textContent = "Fees withdrawn.";
}

async function main() {
  syncWindowInputState();
  populateCollateralPresets();
  await loadDeploymentsConfig();
  syncProtocolCreateUi();
  applyDefaultFactoryAddress();
  $("networkStatus").textContent = "Network: connect wallet to detect chain.";

  if ($("protocolVersion")) {
    $("protocolVersion").addEventListener("change", () => {
      syncProtocolCreateUi();
      if (!$("factoryAddress").value.trim()) {
        applyDefaultFactoryAddress();
      }
    });
  }

  $("wagerTemplate").addEventListener("change", () => {
    const nowSec = Math.floor(Date.now() / 1000);
    const template = Logic.resolveTemplate($("wagerTemplate").value, nowSec);
    const bettingMode = template.bettingCloseMode || "relative";
    const resolutionMode = template.resolutionWindowMode || "relative";
    $("bettingCloseMode").value = bettingMode;
    $("resolutionWindowMode").value = resolutionMode;
    $("bettingCloseIn").value = String(template.bettingCloseIn);
    if (bettingMode === "absolute" && Number.isFinite(template.bettingCloseAt)) {
      $("bettingCloseAt").value = formatDateTimeLocal(new Date(template.bettingCloseAt * 1000));
    } else if (bettingMode === "absolute") {
      ensureDefaultAbsoluteBettingClose();
    }
    $("resolutionWindow").value = String(template.resolutionWindow);
    if (resolutionMode === "absolute" && Number.isFinite(template.resolutionCloseAt)) {
      $("resolutionCloseAt").value = formatDateTimeLocal(new Date(template.resolutionCloseAt * 1000));
    } else if (resolutionMode === "absolute") {
      ensureDefaultAbsoluteResolutionClose();
    }
    $("bettingNoMax").checked = template.bettingNoMax;
    $("resolutionNoMax").checked = template.resolutionNoMax;
    syncWindowInputState();
  });
  $("bettingCloseMode").addEventListener("change", syncWindowInputState);
  $("resolutionWindowMode").addEventListener("change", syncWindowInputState);
  $("bettingNoMax").addEventListener("change", syncWindowInputState);
  $("resolutionNoMax").addEventListener("change", syncWindowInputState);
  $("collateralPreset").addEventListener("change", () => {
    applySelectedCollateralPreset().catch((e) => {
      $("tokenMeta").textContent = `Preset error: ${e.message}`;
    });
  });

  // Initialize UI with custom defaults.
  $("wagerTemplate").value = "custom";

  syncDecimalsInputReadOnly();
  $("decimalsManual").addEventListener("change", () => {
    syncDecimalsInputReadOnly();
    if (!$("decimalsManual").checked) {
      tryDetectDecimalsFromCollateralField();
    }
  });

  $("collateralToken").addEventListener("blur", () => {
    tryDetectDecimalsFromCollateralField().catch((e) => {
      $("tokenMeta").textContent = `Could not read decimals(): ${e.message}`;
    });
  });
  $("factoryAddress").addEventListener("blur", () => {
    const normalized = normalizeAddressInput($("factoryAddress").value);
    if (normalized) $("factoryAddress").value = normalized;
  });
  $("collateralToken").addEventListener("input", () => {
    const normalized = normalizeAddressInput($("collateralToken").value);
    if (normalized) $("collateralToken").value = normalized;
  });
  $("resolverAddress").addEventListener("blur", () => {
    const normalized = normalizeAddressInput($("resolverAddress").value);
    if (normalized) $("resolverAddress").value = normalized;
  });
  $("bettingCloserAddress").addEventListener("blur", () => {
    const normalized = normalizeAddressInput($("bettingCloserAddress").value);
    if (normalized) $("bettingCloserAddress").value = normalized;
  });
  $("resolutionCloserAddress").addEventListener("blur", () => {
    const normalized = normalizeAddressInput($("resolutionCloserAddress").value);
    if (normalized) $("resolutionCloserAddress").value = normalized;
  });

  $("betOutcomeIndex").addEventListener("input", () => {
    updateOddsPreview();
  });
  $("betAmount").addEventListener("input", () => {
    updateOddsPreview();
  });

  $("loadWagerBtn").addEventListener("click", async () => {
    try {
      if (!signer) await connectWallet();
      const address = $("activeWagerAddress").value.trim();
      await setActiveWager(address);
      $("betStatus").textContent = "Active wager loaded.";
    } catch (e) {
      $("betStatus").textContent = `Error: ${e.message}`;
    }
  });

  $("connectBtn").addEventListener("click", async () => {
    try {
      await connectWallet();
    } catch (e) {
      $("walletStatus").textContent = `Error: ${e.message}`;
    }
  });

  $("createWagerBtn").addEventListener("click", async () => {
    try {
      if (!signer) await connectWallet();
      await createWager();
    } catch (e) {
      $("createStatus").textContent = `Error: ${e.message}`;
    }
  });

  $("placeBetBtn").addEventListener("click", async () => {
    try {
      if (!signer) await connectWallet();
      await placeBet();
    } catch (e) {
      $("betStatus").textContent = `Error: ${e.message}`;
    }
  });

  $("placeBetsBtn").addEventListener("click", async () => {
    try {
      if (!signer) await connectWallet();
      await placeBets();
    } catch (e) {
      $("betStatus").textContent = `Error: ${e.message}`;
    }
  });

  $("resolveBtn").addEventListener("click", async () => {
    try {
      if (!signer) await connectWallet();
      await resolveWager();
    } catch (e) {
      $("resolutionStatus").textContent = `Error: ${e.message}`;
    }
  });

  $("retractBtn").addEventListener("click", async () => {
    try {
      if (!signer) await connectWallet();
      await retractWager();
    } catch (e) {
      $("resolutionStatus").textContent = `Error: ${e.message}`;
    }
  });

  $("expireBtn").addEventListener("click", async () => {
    try {
      if (!signer) await connectWallet();
      await expireWager();
    } catch (e) {
      $("resolutionStatus").textContent = `Error: ${e.message}`;
    }
  });

  $("closeBettingBtn").addEventListener("click", async () => {
    try {
      if (!signer) await connectWallet();
      await closeBettingOnWager();
    } catch (e) {
      $("resolutionStatus").textContent = `Error: ${e.message}`;
    }
  });

  $("closeResolutionBtn").addEventListener("click", async () => {
    try {
      if (!signer) await connectWallet();
      await closeResolutionWindowOnWager();
    } catch (e) {
      $("resolutionStatus").textContent = `Error: ${e.message}`;
    }
  });

  $("claimBtn").addEventListener("click", async () => {
    try {
      if (!signer) await connectWallet();
      await claim();
    } catch (e) {
      $("claimStatus").textContent = `Error: ${e.message}`;
    }
  });

  $("withdrawFeesBtn").addEventListener("click", async () => {
    try {
      if (!signer) await connectWallet();
      await withdrawFees();
    } catch (e) {
      $("claimStatus").textContent = `Error: ${e.message}`;
    }
  });

  // Load ABIs for factory/wager
  await loadAbi();

  const wagerParam = new URLSearchParams(window.location.search).get("wager");
  if (wagerParam) {
    const normalized = normalizeAddressInput(wagerParam);
    if (normalized) {
      wagerAddressFromUrl = normalized;
      $("activeWagerAddress").value = normalized;
      history.replaceState(
        null,
        "",
        `${window.location.pathname}?wager=${encodeURIComponent(normalized)}`
      );
    }
  }

  clearOddsPreview("Create a wager first to preview odds.");
  $("walletStatus").textContent = "Ready.";
}

main().catch((e) => {
  console.error(e);
});

