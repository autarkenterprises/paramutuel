// Load ethers via UMD in index.html:
// <script src="https://cdn.jsdelivr.net/npm/ethers@6.13.5/dist/ethers.umd.min.js"></script>
// The UMD bundle exposes `ethers` on `globalThis`.
const ethers = globalThis.ethers;

const FACTORY_ABI_URL = "../out/ParamutuelFactory.sol/ParamutuelFactory.json";
const MARKET_ABI_URL = "../out/ParamutuelMarket.sol/ParamutuelMarket.json";
const Logic = globalThis.ParamutuelLogic;

let provider;
let signer;
let userAddress;

let factoryAbi;
let marketAbi;

let marketContract; // last-created market

function $(id) {
  return document.getElementById(id);
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
  $("bettingCloseIn").readOnly = $("bettingNoMax").checked;
  $("resolutionWindow").readOnly = $("resolutionNoMax").checked;
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

async function loadAbi() {
  const [factoryJson, marketJson] = await Promise.all([
    fetch(FACTORY_ABI_URL).then((r) => r.json()),
    fetch(MARKET_ABI_URL).then((r) => r.json()),
  ]);
  factoryAbi = factoryJson.abi;
  marketAbi = marketJson.abi;
}

async function connectWallet() {
  if (!window.ethereum) throw new Error("No window.ethereum found (install MetaMask).");

  provider = new ethers.BrowserProvider(window.ethereum);
  await provider.send("eth_requestAccounts", []);
  signer = await provider.getSigner();
  userAddress = await signer.getAddress();

  $("walletAddr").textContent = userAddress;
  $("walletStatus").textContent = "Connected.";
  await tryDetectDecimalsFromCollateralField();
}

async function getFactoryConstraints(factoryAddress) {
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
  marketContract = new ethers.Contract(marketAddress, marketAbi, getRunner());
  $("marketAddress").textContent = marketAddress;
  $("activeMarketAddress").value = marketAddress;
  await updateOddsPreview();
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
  const extraFeeRecipientsCsv = $("extraFeeRecipients").value.trim();
  const extraFeeBpsCsv = $("extraFeeBps").value.trim();
  const resolverInput = $("resolverAddress").value.trim();
  const bettingCloserInput = $("bettingCloserAddress").value.trim();
  const resolutionCloserInput = $("resolutionCloserAddress").value.trim();

  if (!factoryAddress) throw new Error("Factory address is required.");
  if (!collateralToken) throw new Error("Collateral token is required.");
  if (!outcomesCsv) throw new Error("Outcomes are required.");
  if (!question) throw new Error("Question is required.");

  const outcomes = parseCsvToArray(outcomesCsv);
  if (outcomes.length < 2) throw new Error("Need at least 2 outcomes.");

  const extraFeeRecipients = extraFeeRecipientsCsv
    ? parseCsvToArray(extraFeeRecipientsCsv)
    : [];

  const extraFeeBps = extraFeeBpsCsv ? parseCsvToArray(extraFeeBpsCsv).map((x) => Number(x)) : [];

  if (extraFeeRecipients.length !== extraFeeBps.length) {
    throw new Error("extraFeeRecipients and extraFeeBps length mismatch.");
  }

  const nowSec = Math.floor(Date.now() / 1000);
  const { closeTime, resolutionWindowArg } = Logic.computeWindowArgs(
    nowSec,
    bettingCloseIn,
    resolutionWindow,
    bettingNoMax,
    resolutionNoMax
  );

  // Optional UI-side validation with factory constraints (still will revert if wrong).
  const { minBettingWindow, minResolutionWindow } = await getFactoryConstraints(factoryAddress);
  const warnings = Logic.validateWindowMins(
    minBettingWindow,
    minResolutionWindow,
    bettingCloseIn,
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

  $("createStatus").textContent = "Submitting createMarket transaction...";
  const tx = await factory.createMarket(
    collateralToken,
    question,
    outcomes,
    BigInt(closeTime),
    BigInt(resolutionWindowArg),
    resolverArg,
    bettingCloserArg,
    resolutionCloserArg,
    extraFeeRecipients,
    extraFeeBps
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

async function resolveMarket() {
  if (!marketContract) throw new Error("Create a market first.");
  const winningOutcomeIndex = Number($("winningOutcomeIndex").value);

  $("resolutionStatus").textContent = "Resolving...";
  const tx = await marketContract.resolve(winningOutcomeIndex);
  await tx.wait();
  $("resolutionStatus").textContent = "Resolved.";
  await updateOddsPreview();
}

async function retractMarket() {
  if (!marketContract) throw new Error("Create a market first.");
  $("resolutionStatus").textContent = "Retracting...";
  const tx = await marketContract.retract();
  await tx.wait();
  $("resolutionStatus").textContent = "Retracted.";
  await updateOddsPreview();
}

async function expireMarket() {
  if (!marketContract) throw new Error("Create a market first.");
  $("resolutionStatus").textContent = "Expiring...";
  const tx = await marketContract.expire();
  await tx.wait();
  $("resolutionStatus").textContent = "Expired.";
  await updateOddsPreview();
}

async function closeBettingOnMarket() {
  if (!marketContract) throw new Error("Create a market first.");
  $("resolutionStatus").textContent = "Closing betting...";
  const tx = await marketContract.closeBetting();
  await tx.wait();
  $("resolutionStatus").textContent = "Betting closed (authority).";
  await updateOddsPreview();
}

async function closeResolutionWindowOnMarket() {
  if (!marketContract) throw new Error("Create a market first.");
  $("resolutionStatus").textContent = "Closing resolution window...";
  const tx = await marketContract.closeResolutionWindow();
  await tx.wait();
  $("resolutionStatus").textContent = "Resolution window closed (authority).";
  await updateOddsPreview();
}

async function claim() {
  if (!marketContract) throw new Error("Create a market first.");
  $("claimStatus").textContent = "Claiming payout...";
  const tx = await marketContract.claim();
  await tx.wait();
  $("claimStatus").textContent = "Claimed (check token balance).";
}

async function withdrawFees() {
  if (!marketContract) throw new Error("Create a market first.");
  $("claimStatus").textContent = "Withdrawing fees...";
  const tx = await marketContract.withdrawFees();
  await tx.wait();
  $("claimStatus").textContent = "Fees withdrawn.";
}

async function main() {
  syncWindowInputState();

  $("marketTemplate").addEventListener("change", () => {
    const template = Logic.getTemplate($("marketTemplate").value);
    $("bettingCloseIn").value = String(template.bettingCloseIn);
    $("resolutionWindow").value = String(template.resolutionWindow);
    $("bettingNoMax").checked = template.bettingNoMax;
    $("resolutionNoMax").checked = template.resolutionNoMax;
    syncWindowInputState();
  });
  $("bettingNoMax").addEventListener("change", syncWindowInputState);
  $("resolutionNoMax").addEventListener("change", syncWindowInputState);

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

