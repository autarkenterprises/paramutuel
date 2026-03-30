// Load ethers via UMD in index.html:
// <script src="https://cdn.jsdelivr.net/npm/ethers@6.13.5/dist/ethers.umd.min.js"></script>
// The UMD bundle exposes `ethers` on `globalThis`.
const ethers = globalThis.ethers;

const FACTORY_ABI_URL = "abi/ParamutuelFactory.json";
const FACTORY_ABI_FALLBACK = "../out/ParamutuelFactory.sol/ParamutuelFactory.json";
const MARKET_ABI_URL = "abi/ParamutuelMarket.json";
const MARKET_ABI_FALLBACK = "../out/ParamutuelMarket.sol/ParamutuelMarket.json";
const DEPLOYMENTS_CONFIG_URL = "../config/deployments.json";
const Logic = globalThis.ParamutuelLogic;

let provider;
let signer;
let userAddress;

let factoryAbi;
let marketAbi;

let marketContract; // last-created market
let currentChainId = null;
let walletListenersAttached = false;
let deploymentsConfig = null;

const CHAIN_INFO = {
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

function $(id) {
  return document.getElementById(id);
}

function chainName(chainId) {
  const info = CHAIN_INFO[chainId];
  return info ? info.name : `Unknown chain (${chainId})`;
}

function deploymentConfigKeyForChain(chainId) {
  if (chainId !== null && DEPLOYMENTS_KEY_BY_CHAIN_ID[chainId]) {
    return DEPLOYMENTS_KEY_BY_CHAIN_ID[chainId];
  }
  if (deploymentsConfig && typeof deploymentsConfig.defaultNetwork === "string") {
    const configured = deploymentsConfig.defaultNetwork.trim();
    if (configured.length > 0 && deploymentsConfig[configured]) {
      return configured;
    }
  }
  return "baseSepolia";
}

function deploymentFactoryAddressForChain(chainId) {
  if (!deploymentsConfig) return "";
  const key = deploymentConfigKeyForChain(chainId);
  return String((deploymentsConfig[key] || {}).factoryAddress || "").trim();
}

function applyDefaultFactoryAddress() {
  const current = $("factoryAddress").value.trim();
  if (current) return;
  const configured = deploymentFactoryAddressForChain(currentChainId);
  if (!configured || !ethers.isAddress(configured)) return;
  $("factoryAddress").value = configured;
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

async function updateOddsPreview() {
  if (!marketContract) {
    clearOddsPreview("Create a market first to preview odds.");
    return;
  }

  try {
    const outcomeIndex = Number($("betOutcomeIndex").value);
    const amountNumber = Number($("betAmount").value);
    if (!Number.isFinite(outcomeIndex) || outcomeIndex < 0) {
      clearOddsPreview("Enter a valid outcome index.");
      return;
    }
    if (!Number.isFinite(amountNumber) || amountNumber <= 0) {
      clearOddsPreview("Enter a positive bet amount to preview payout.");
      return;
    }

    const state = Number(await marketContract.state());
    if (state !== 0) {
      clearOddsPreview("Market is not open. Odds preview is only shown for open markets.");
      return;
    }

    const outcomesCount = Number(await marketContract.outcomesCount());
    if (outcomeIndex >= outcomesCount) {
      clearOddsPreview(`Outcome index out of range (0-${outcomesCount - 1}).`);
      return;
    }

    const collateralTokenAddress = await marketContract.collateralToken();
    const decimals = await resolveBettingDecimals(collateralTokenAddress);
    const betAmount = parseAmount(amountNumber, decimals);

    const [totalPot, totalFeeBps, outcomeTotal] = await Promise.all([
      marketContract.totalPot(),
      marketContract.totalFeeBps(),
      marketContract.outcomeTotals(outcomeIndex),
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
  const mode = $("bettingCloseMode").value;
  $("bettingCloseIn").readOnly = bettingNoMax || mode !== "relative";
  $("bettingCloseAt").disabled = bettingNoMax || mode !== "absolute";
  $("bettingCloseInWrap").style.display = !bettingNoMax && mode === "relative" ? "" : "none";
  $("bettingCloseAtWrap").style.display = !bettingNoMax && mode === "absolute" ? "" : "none";
  if (!bettingNoMax && mode === "absolute") {
    ensureDefaultAbsoluteBettingClose();
  }
  $("resolutionWindow").readOnly = $("resolutionNoMax").checked;
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
  $("collateralToken").value = preset.address;

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
  $("tokenMeta").textContent = `Token decimals: ${d} (read from token contract).`;
  return d;
}

async function tryDetectDecimalsFromCollateralField() {
  if ($("decimalsManual").checked) return;
  const addr = $("collateralToken").value.trim();
  if (!addr || !ethers.isAddress(addr)) {
    $("tokenMeta").textContent = "Enter a valid token address, then tab away to detect decimals.";
    return;
  }
  if (!provider) {
    $("tokenMeta").textContent = "Connect wallet to read decimals() from the token.";
    return;
  }
  try {
    const d = await fetchTokenDecimals(addr);
    $("decimals").value = String(d);
    $("tokenMeta").textContent = `Token decimals: ${d} (read from token contract).`;
  } catch (e) {
    $("tokenMeta").textContent = `Could not read decimals(): ${e.message} — enable Manual decimals override.`;
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
  } catch (_) {
    // Optional for local/dev runs; manual factory entry still works.
  }
}

async function loadAbi() {
  [factoryAbi, marketAbi] = await Promise.all([
    fetchAbiWithFallback(FACTORY_ABI_URL, FACTORY_ABI_FALLBACK),
    fetchAbiWithFallback(MARKET_ABI_URL, MARKET_ABI_FALLBACK),
  ]);
}

async function connectWallet() {
  if (!window.ethereum) throw new Error("No window.ethereum found (install MetaMask).");

  provider = new ethers.BrowserProvider(window.ethereum);
  await provider.send("eth_requestAccounts", []);
  signer = await provider.getSigner();
  userAddress = await signer.getAddress();
  await refreshConnectedNetwork();

  $("walletAddr").textContent = userAddress;
  $("walletStatus").textContent = "Connected.";
  await tryDetectDecimalsFromCollateralField();

  if (!walletListenersAttached && window.ethereum && window.ethereum.on) {
    window.ethereum.on("chainChanged", async () => {
      provider = new ethers.BrowserProvider(window.ethereum);
      signer = await provider.getSigner();
      await refreshConnectedNetwork();
      $("walletStatus").textContent = "Network changed. Review factory/token before transacting.";
      await tryDetectDecimalsFromCollateralField();
    });
    window.ethereum.on("accountsChanged", async () => {
      if (!provider) return;
      signer = await provider.getSigner();
      userAddress = await signer.getAddress();
      $("walletAddr").textContent = userAddress;
    });
    walletListenersAttached = true;
  }
}

async function getFactoryConstraints(factoryAddress) {
  await ensureContractExistsOnCurrentNetwork(factoryAddress, "Factory address");
  const factory = new ethers.Contract(factoryAddress, factoryAbi, provider);
  const minBettingWindow = await factory.minBettingWindow();
  const minResolutionWindow = await factory.minResolutionWindow();
  return { minBettingWindow, minResolutionWindow };
}

function getRunner() {
  if (signer) return signer;
  if (provider) return provider;
  throw new Error("Connect wallet first.");
}

async function setActiveMarket(marketAddress) {
  if (!ethers.isAddress(marketAddress)) throw new Error("Invalid market address.");
  await ensureContractExistsOnCurrentNetwork(marketAddress, "Market address");
  marketContract = new ethers.Contract(marketAddress, marketAbi, getRunner());
  $("marketAddress").textContent = marketAddress;
  $("activeMarketAddress").value = marketAddress;
  if (!$("resolutionMarketAddress").value.trim()) {
    $("resolutionMarketAddress").value = marketAddress;
  }
  if (!$("claimsMarketAddress").value.trim()) {
    $("claimsMarketAddress").value = marketAddress;
  }
  await updateOddsPreview();
}

async function ensureMarketForPlannedAction(actionName) {
  const plan = Logic.planMarketAction(actionName, {
    resolutionMarketAddress: $("resolutionMarketAddress").value,
    claimsMarketAddress: $("claimsMarketAddress").value,
    activeMarketAddress: $("activeMarketAddress").value,
  });
  if (!ethers.isAddress(plan.targetAddress)) {
    throw new Error(`Invalid market address for ${actionName}.`);
  }
  if (
    !marketContract ||
    String(marketContract.target || "").toLowerCase() !== plan.targetAddress.toLowerCase()
  ) {
    await setActiveMarket(plan.targetAddress);
  }
  if (!marketContract) throw new Error("Failed to load target market.");
  return { plan, targetMarket: marketContract };
}

async function runMarketAction(actionName, ...args) {
  const { plan, targetMarket } = await ensureMarketForPlannedAction(actionName);
  const method = plan.method;
  if (typeof targetMarket[method] !== "function") {
    throw new Error(`Market contract does not support action method ${method}.`);
  }
  const tx = await targetMarket[method](...args);
  await tx.wait();
  return marketContract;
}

async function createMarket() {
  const factoryAddress = $("factoryAddress").value.trim();
  const collateralToken = $("collateralToken").value.trim();
  const outcomesCsv = $("outcomes").value.trim();
  const question = $("question").value.trim();

  const bettingCloseIn = Number($("bettingCloseIn").value);
  const resolutionWindow = Number($("resolutionWindow").value);
  const bettingNoMax = $("bettingNoMax").checked;
  const resolutionNoMax = $("resolutionNoMax").checked;
  const bettingCloseMode = $("bettingCloseMode").value;
  const bettingCloseAtRaw = $("bettingCloseAt").value.trim();
  const extraFeeRecipientsCsv = $("extraFeeRecipients").value.trim();
  const extraFeeBpsCsv = $("extraFeeBps").value.trim();
  const seedOutcomeIndicesCsv = $("seedOutcomeIndices").value.trim();
  const seedAmountsCsv = $("seedAmounts").value.trim();
  const resolverInput = $("resolverAddress").value.trim();
  const bettingCloserInput = $("bettingCloserAddress").value.trim();
  const resolutionCloserInput = $("resolutionCloserAddress").value.trim();

  if (!factoryAddress) throw new Error("Factory address is required.");
  if (!collateralToken) throw new Error("Collateral token is required.");
  if (!outcomesCsv) throw new Error("Outcomes are required.");
  if (!question) throw new Error("Question is required.");
  if (!ethers.isAddress(factoryAddress)) throw new Error("Factory address is invalid.");
  if (!ethers.isAddress(collateralToken)) throw new Error("Collateral token address is invalid.");

  const presetRaw = $("collateralPreset").value;
  if (presetRaw !== "custom" && currentChainId !== null) {
    const preset = parseTokenPresetValue(presetRaw);
    if (preset.chainId !== currentChainId) {
      throw new Error(
        `Selected token preset is for ${chainName(preset.chainId)}, but wallet is on ${chainName(currentChainId)}.`
      );
    }
  }

  const outcomes = parseCsvToArray(outcomesCsv);
  if (outcomes.length < 2) throw new Error("Need at least 2 outcomes.");

  const extraFeeRecipients = extraFeeRecipientsCsv
    ? parseCsvToArray(extraFeeRecipientsCsv)
    : [];

  const extraFeeBps = extraFeeBpsCsv ? parseCsvToArray(extraFeeBpsCsv).map((x) => Number(x)) : [];

  if (extraFeeRecipients.length !== extraFeeBps.length) {
    throw new Error("extraFeeRecipients and extraFeeBps length mismatch.");
  }
  const seedParsed = Logic.parseMultiBetInputs(seedOutcomeIndicesCsv, seedAmountsCsv, true);

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

  const { closeTime, resolutionWindowArg } = Logic.computeWindowArgs(
    nowSec,
    bettingCloseIn,
    resolutionWindow,
    bettingNoMax,
    resolutionNoMax,
    bettingCloseMode,
    bettingCloseAtSec
  );

  // Optional UI-side validation with factory constraints (still will revert if wrong).
  const { minBettingWindow, minResolutionWindow } = await getFactoryConstraints(factoryAddress);
  const effectiveBettingCloseIn = bettingNoMax ? 0 : Math.max(0, closeTime - nowSec);
  const warnings = Logic.validateWindowMins(
    minBettingWindow,
    minResolutionWindow,
    effectiveBettingCloseIn,
    resolutionWindow,
    bettingNoMax,
    resolutionNoMax
  );
  $("factoryConstraints").textContent =
    `Factory constraints: minBettingWindow=${minBettingWindow}, minResolutionWindow=${minResolutionWindow}` +
    " (window values of 0 enable no-max mode)" +
    (warnings.length ? `; Warning: ${warnings.join("; ")}` : "");

  const factory = new ethers.Contract(factoryAddress, factoryAbi, signer);

  let resolverArg = ethers.ZeroAddress;
  if (resolverInput.length > 0) {
    if (!ethers.isAddress(resolverInput)) throw new Error("Invalid resolver address.");
    resolverArg = resolverInput;
  }

  let bettingCloserArg = ethers.ZeroAddress;
  if (bettingCloserInput.length > 0) {
    if (!ethers.isAddress(bettingCloserInput)) throw new Error("Invalid betting closer address.");
    bettingCloserArg = bettingCloserInput;
  }

  let resolutionCloserArg = ethers.ZeroAddress;
  if (resolutionCloserInput.length > 0) {
    if (!ethers.isAddress(resolutionCloserInput)) throw new Error("Invalid resolution closer address.");
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

  $("createStatus").textContent = "Submitting createMarket transaction...";
  const tx = await factory[
    "createMarket(address,string,string[],uint64,uint64,address,address,address,address[],uint16[],uint256[],uint256[])"
  ](
    collateralToken,
    question,
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
  const receipt = await tx.wait();

  // Extract MarketCreated event args
  let marketAddress = null;
  for (const log of receipt.logs) {
    try {
      const parsed = factory.interface.parseLog(log);
      if (parsed && parsed.name === "MarketCreated") {
        marketAddress = parsed.args.market;
        break;
      }
    } catch (_) {}
  }
  if (!marketAddress) throw new Error("MarketCreated event not found in tx receipt.");

  await setActiveMarket(marketAddress);
  $("createStatus").textContent = "Market created.";
}

async function placeBet() {
  if (!marketContract) throw new Error("Create a market first.");

  const outcomeIndex = Number($("betOutcomeIndex").value);
  const amountNumber = Number($("betAmount").value);

  const collateralTokenAddress = await marketContract.collateralToken();
  const decimals = await resolveBettingDecimals(collateralTokenAddress);
  const erc20Abi = [
    "function approve(address spender,uint256 amount) external returns (bool)",
    "function transfer(address to,uint256 amount) external returns (bool)",
  ];
  const token = new ethers.Contract(collateralTokenAddress, erc20Abi, signer);

  const amount = parseAmount(amountNumber, decimals);

  $("betStatus").textContent = "Approving collateral...";
  const approveTx = await token.approve(marketContract.target, amount);
  await approveTx.wait();

  $("betStatus").textContent = "Placing bet...";
  const tx = await marketContract.placeBet(outcomeIndex, amount);
  await tx.wait();
  $("betStatus").textContent = "Bet placed.";
  await updateOddsPreview();
}

async function placeBets() {
  if (!marketContract) throw new Error("Create a market first.");

  const parsed = Logic.parseMultiBetInputs($("betOutcomeIndices").value, $("betAmounts").value, false);
  const collateralTokenAddress = await marketContract.collateralToken();
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
  const approveTx = await token.approve(marketContract.target, totalAmount);
  await approveTx.wait();

  $("betStatus").textContent = "Placing batch bet...";
  const tx = await marketContract.placeBets(parsed.outcomeIndices, amounts);
  await tx.wait();
  $("betStatus").textContent = "Batch bet placed.";
  await updateOddsPreview();
}

async function resolveMarket() {
  const winningOutcomeIndex = Number($("winningOutcomeIndex").value);

  $("resolutionStatus").textContent = "Resolving...";
  await runMarketAction("resolve", winningOutcomeIndex);
  $("resolutionStatus").textContent = "Resolved.";
  await updateOddsPreview();
}

async function retractMarket() {
  $("resolutionStatus").textContent = "Retracting...";
  await runMarketAction("retract");
  $("resolutionStatus").textContent = "Retracted.";
  await updateOddsPreview();
}

async function expireMarket() {
  $("resolutionStatus").textContent = "Expiring...";
  await runMarketAction("expire");
  $("resolutionStatus").textContent = "Expired.";
  await updateOddsPreview();
}

async function closeBettingOnMarket() {
  $("resolutionStatus").textContent = "Closing betting...";
  await runMarketAction("closeBetting");
  $("resolutionStatus").textContent = "Betting closed (authority).";
  await updateOddsPreview();
}

async function closeResolutionWindowOnMarket() {
  $("resolutionStatus").textContent = "Closing resolution window...";
  await runMarketAction("closeResolutionWindow");
  $("resolutionStatus").textContent = "Resolution window closed (authority).";
  await updateOddsPreview();
}

async function claim() {
  $("claimStatus").textContent = "Claiming payout...";
  await runMarketAction("claim");
  $("claimStatus").textContent = "Claimed (check token balance).";
}

async function withdrawFees() {
  $("claimStatus").textContent = "Withdrawing fees...";
  await runMarketAction("withdrawFees");
  $("claimStatus").textContent = "Fees withdrawn.";
}

async function main() {
  syncWindowInputState();
  populateCollateralPresets();
  await loadDeploymentsConfig();
  applyDefaultFactoryAddress();
  $("networkStatus").textContent = "Network: connect wallet to detect chain.";

  $("marketTemplate").addEventListener("change", () => {
    const nowSec = Math.floor(Date.now() / 1000);
    const template = Logic.resolveTemplate($("marketTemplate").value, nowSec);
    const mode = template.bettingCloseMode || "relative";
    $("bettingCloseMode").value = mode;
    $("bettingCloseIn").value = String(template.bettingCloseIn);
    if (mode === "absolute" && Number.isFinite(template.bettingCloseAt)) {
      $("bettingCloseAt").value = formatDateTimeLocal(new Date(template.bettingCloseAt * 1000));
    } else if (mode === "absolute") {
      ensureDefaultAbsoluteBettingClose();
    }
    $("resolutionWindow").value = String(template.resolutionWindow);
    $("bettingNoMax").checked = template.bettingNoMax;
    $("resolutionNoMax").checked = template.resolutionNoMax;
    syncWindowInputState();
  });
  $("bettingCloseMode").addEventListener("change", syncWindowInputState);
  $("bettingNoMax").addEventListener("change", syncWindowInputState);
  $("resolutionNoMax").addEventListener("change", syncWindowInputState);
  $("collateralPreset").addEventListener("change", () => {
    applySelectedCollateralPreset().catch((e) => {
      $("tokenMeta").textContent = `Preset error: ${e.message}`;
    });
  });

  // Initialize UI with custom defaults.
  $("marketTemplate").value = "custom";

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

  $("betOutcomeIndex").addEventListener("input", () => {
    updateOddsPreview();
  });
  $("betAmount").addEventListener("input", () => {
    updateOddsPreview();
  });

  $("loadMarketBtn").addEventListener("click", async () => {
    try {
      if (!signer) await connectWallet();
      const address = $("activeMarketAddress").value.trim();
      await setActiveMarket(address);
      $("betStatus").textContent = "Active market loaded.";
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

  $("createMarketBtn").addEventListener("click", async () => {
    try {
      if (!signer) await connectWallet();
      await createMarket();
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
      await resolveMarket();
    } catch (e) {
      $("resolutionStatus").textContent = `Error: ${e.message}`;
    }
  });

  $("retractBtn").addEventListener("click", async () => {
    try {
      if (!signer) await connectWallet();
      await retractMarket();
    } catch (e) {
      $("resolutionStatus").textContent = `Error: ${e.message}`;
    }
  });

  $("expireBtn").addEventListener("click", async () => {
    try {
      if (!signer) await connectWallet();
      await expireMarket();
    } catch (e) {
      $("resolutionStatus").textContent = `Error: ${e.message}`;
    }
  });

  $("closeBettingBtn").addEventListener("click", async () => {
    try {
      if (!signer) await connectWallet();
      await closeBettingOnMarket();
    } catch (e) {
      $("resolutionStatus").textContent = `Error: ${e.message}`;
    }
  });

  $("closeResolutionBtn").addEventListener("click", async () => {
    try {
      if (!signer) await connectWallet();
      await closeResolutionWindowOnMarket();
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

  // Load ABIs for factory/market
  await loadAbi();
  clearOddsPreview("Create a market first to preview odds.");
  $("walletStatus").textContent = "Ready.";
}

main().catch((e) => {
  console.error(e);
});

