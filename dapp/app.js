// Load ethers via UMD in index.html:
// <script src="https://cdn.jsdelivr.net/npm/ethers@6.13.5/dist/ethers.umd.min.js"></script>
// The UMD bundle exposes `ethers` on `globalThis`.
const ethers = globalThis.ethers;

const FACTORY_ABI_URL = "../out/ParamutuelFactory.sol/ParamutuelFactory.json";
const MARKET_ABI_URL = "../out/ParamutuelMarket.sol/ParamutuelMarket.json";

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
}

async function getFactoryConstraints(factoryAddress) {
  const factory = new ethers.Contract(factoryAddress, factoryAbi, provider);
  const minBettingWindow = await factory.minBettingWindow();
  const minResolutionWindow = await factory.minResolutionWindow();
  return { minBettingWindow, minResolutionWindow };
}

async function createMarket() {
  const factoryAddress = $("factoryAddress").value.trim();
  const collateralToken = $("collateralToken").value.trim();
  const outcomesCsv = $("outcomes").value.trim();
  const question = $("question").value.trim();

  const bettingCloseIn = Number($("bettingCloseIn").value);
  const resolutionWindow = Number($("resolutionWindow").value);
  const extraFeeRecipientsCsv = $("extraFeeRecipients").value.trim();
  const extraFeeBpsCsv = $("extraFeeBps").value.trim();
  const decimals = Number($("decimals").value);

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

  const closeTime = toUnixSeconds(bettingCloseIn);

  // Optional UI-side validation with factory constraints (still will revert if wrong).
  const { minBettingWindow, minResolutionWindow } = await getFactoryConstraints(factoryAddress);
  if (BigInt(bettingCloseIn) < BigInt(minBettingWindow)) {
    $("factoryConstraints").textContent = `Warning: bettingCloseIn < factory minBettingWindow (${minBettingWindow}).`;
  } else {
    $("factoryConstraints").textContent = `Factory constraints: minBettingWindow=${minBettingWindow}, minResolutionWindow=${minResolutionWindow}`;
  }
  if (BigInt(resolutionWindow) < BigInt(minResolutionWindow)) {
    throw new Error(`resolutionWindow < factory minResolutionWindow (${minResolutionWindow})`);
  }

  const factory = new ethers.Contract(factoryAddress, factoryAbi, signer);

  $("createStatus").textContent = "Submitting createMarket transaction...";
  const tx = await factory.createMarket(
    collateralToken,
    question,
    outcomes,
    BigInt(closeTime),
    BigInt(resolutionWindow),
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

  marketContract = new ethers.Contract(marketAddress, marketAbi, signer);
  $("marketAddress").textContent = marketAddress;
  $("createStatus").textContent = "Market created.";
}

async function placeBet() {
  if (!marketContract) throw new Error("Create a market first.");

  const outcomeIndex = Number($("betOutcomeIndex").value);
  const amountNumber = Number($("betAmount").value);
  const decimals = Number($("decimals").value);

  const collateralTokenAddress = await marketContract.collateralToken();
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
}

async function resolveMarket() {
  if (!marketContract) throw new Error("Create a market first.");
  const winningOutcomeIndex = Number($("winningOutcomeIndex").value);

  $("resolutionStatus").textContent = "Resolving...";
  const tx = await marketContract.resolve(winningOutcomeIndex);
  await tx.wait();
  $("resolutionStatus").textContent = "Resolved.";
}

async function retractMarket() {
  if (!marketContract) throw new Error("Create a market first.");
  $("resolutionStatus").textContent = "Retracting...";
  const tx = await marketContract.retract();
  await tx.wait();
  $("resolutionStatus").textContent = "Retracted.";
}

async function expireMarket() {
  if (!marketContract) throw new Error("Create a market first.");
  $("resolutionStatus").textContent = "Expiring...";
  const tx = await marketContract.expire();
  await tx.wait();
  $("resolutionStatus").textContent = "Expired.";
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
  $("walletStatus").textContent = "Ready.";
}

main().catch((e) => {
  console.error(e);
});

