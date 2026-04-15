(function () {
  "use strict";

  const ethers = globalThis.ethers;
  const CONFIG_URL = "config/deployments.json";
  const FACTORY_ABI_URL = "dapp/abi/ParamutuelFactoryV3.json";

  const CHAIN_NAMES = {
    8453: "Base Mainnet",
    84532: "Base Sepolia",
  };

  const TOKEN_PRESETS = {
    84532: [
      { symbol: "USDC", address: "0x036CbD53842c5426634e7929541eC2318f3dCF7e", decimals: 6 },
      { symbol: "WETH", address: "0x4200000000000000000000000000000000000006", decimals: 18 },
    ],
    8453: [
      { symbol: "USDC", address: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", decimals: 6 },
      { symbol: "WETH", address: "0x4200000000000000000000000000000000000006", decimals: 18 },
      { symbol: "DAI", address: "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb", decimals: 18 },
    ],
  };

  function getTemplateApi() {
    return globalThis.ParamutuelProposeTemplates || null;
  }

  function getProposeProfile() {
    const body = document.body;
    const raw = body && body.getAttribute("data-propose-profile");
    return (raw && String(raw).trim()) || "default";
  }

  let deployments = null;
  let expectedChainId = null;
  let factoryAddress = null;
  let factoryAbi = null;
  let provider = null;
  let signer = null;
  let selectedTemplate = "yesno";

  function $(id) { return document.getElementById(id); }

  function resolveEip1193Provider() {
    const eth = globalThis.ethereum;
    if (!eth) return null;
    if (Array.isArray(eth.providers) && eth.providers.length > 0) {
      const withRequest = eth.providers.find((p) => p && typeof p.request === "function");
      return withRequest || eth.providers[0];
    }
    return eth;
  }

  async function loadJson(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  }

  async function loadDeployments() {
    const data = await loadJson(CONFIG_URL);
    deployments = data;
    const PSN = globalThis.ParamutuelSiteNetwork;
    const netKey = PSN
      ? PSN.getActiveNetworkKey(data)
      : String(data?.defaultNetwork || "baseSepolia").trim();
    const net = PSN ? PSN.getNetworkEntry(data, netKey) : data?.[netKey] || {};
    factoryAddress = String(net.factoryV3Address || "").trim() || null;
    const cid = net.chainId;
    expectedChainId = typeof cid === "number" ? cid : Number(cid);
  }

  async function loadFactoryAbi() {
    const j = await loadJson(FACTORY_ABI_URL);
    factoryAbi = j.abi;
  }

  function setStatus(msg) {
    const el = $("proposeStatus");
    if (el) el.textContent = msg;
  }

  function setError(msg) {
    const el = $("proposeError");
    if (el) {
      el.textContent = msg;
      el.hidden = !msg;
    }
  }

  function formatSeconds(sec) {
    if (sec >= 86400) return `${Math.round(sec / 86400)} day${sec >= 172800 ? "s" : ""}`;
    if (sec >= 3600) return `${Math.round(sec / 3600)} hour${sec >= 7200 ? "s" : ""}`;
    return `${Math.round(sec / 60)} minute${sec >= 120 ? "s" : ""}`;
  }

  function populateCollateralSelect() {
    const sel = $("proposeCollateral");
    if (!sel) return;
    sel.innerHTML = "";
    const presets = TOKEN_PRESETS[expectedChainId] || TOKEN_PRESETS[84532];
    for (const t of presets) {
      const opt = document.createElement("option");
      opt.value = t.address;
      opt.textContent = t.symbol;
      opt.dataset.decimals = String(t.decimals);
      sel.appendChild(opt);
    }
    const custom = document.createElement("option");
    custom.value = "custom";
    custom.textContent = "Custom address…";
    sel.appendChild(custom);
  }

  function selectTemplate(key) {
    const PT = getTemplateApi();
    if (!PT) {
      console.error("ParamutuelProposeTemplates missing — load propose-templates.js before propose-wager.js");
      return;
    }
    let tpl;
    try {
      tpl = PT.getResolvedTemplate(key, getProposeProfile());
    } catch (e) {
      console.error(e);
      return;
    }
    selectedTemplate = key;

    // Highlight selected template card
    document.querySelectorAll("[data-template]").forEach((el) => {
      el.classList.toggle("propose-tpl-selected", el.dataset.template === key);
    });

    // Show/hide outcomes vs freeform
    const outcomesSection = $("proposeOutcomesSection");
    const freeformNote = $("proposeFreeformNote");
    if (outcomesSection) outcomesSection.hidden = tpl.freeform;
    if (freeformNote) freeformNote.hidden = !tpl.freeform;

    const propEl = $("proposeProposition");
    if (propEl) {
      propEl.value = tpl.placeholderProposition;
      propEl.placeholder = tpl.freeform
        ? "Describe what bettors are trying to predict (resolver picks the exact winning text)."
        : "State the question clearly — outcomes below must match how you will resolve.";
    }

    // Populate outcome fields
    if (!tpl.freeform) {
      const container = $("proposeOutcomesList");
      if (container) {
        container.innerHTML = "";
        tpl.outcomes.forEach((label, i) => {
          const row = document.createElement("div");
          row.className = "propose-outcome-row";
          const inp = document.createElement("input");
          inp.type = "text";
          inp.className = "propose-outcome-input";
          inp.value = label;
          inp.placeholder = "Outcome " + (i + 1);
          row.appendChild(inp);
          if (i >= 2) {
            const removeBtn = document.createElement("button");
            removeBtn.type = "button";
            removeBtn.className = "propose-outcome-remove";
            removeBtn.title = "Remove";
            removeBtn.textContent = "\u00d7";
            removeBtn.addEventListener("click", () => { row.remove(); });
            row.appendChild(removeBtn);
          }
          container.appendChild(row);
        });
      }
    }

    // Set timing defaults
    const betClose = $("proposeBettingClose");
    const resWindow = $("proposeResolutionWindow");
    if (betClose) betClose.value = String(tpl.bettingClose);
    if (resWindow) resWindow.value = String(tpl.resolution);

    // Update timing display
    updateTimingDisplay();
  }

  function updateTimingDisplay() {
    const betClose = $("proposeBettingClose");
    const resWindow = $("proposeResolutionWindow");
    const betLabel = $("proposeBettingCloseLabel");
    const resLabel = $("proposeResolutionWindowLabel");
    if (betClose && betLabel) betLabel.textContent = formatSeconds(Number(betClose.value));
    if (resWindow && resLabel) resLabel.textContent = formatSeconds(Number(resWindow.value));
  }

  function addOutcome() {
    const container = $("proposeOutcomesList");
    if (!container) return;
    const count = container.querySelectorAll(".propose-outcome-row").length;
    if (count >= 255) return;
    const row = document.createElement("div");
    row.className = "propose-outcome-row";
    row.innerHTML = `<input type="text" class="propose-outcome-input" value="" placeholder="Outcome ${count + 1}" />` +
      `<button type="button" class="propose-outcome-remove" title="Remove">&times;</button>`;
    row.querySelector(".propose-outcome-remove").addEventListener("click", () => { row.remove(); });
    container.appendChild(row);
    row.querySelector("input").focus();
  }

  function collectOutcomes() {
    const inputs = document.querySelectorAll(".propose-outcome-input");
    const outcomes = [];
    for (const inp of inputs) {
      const v = inp.value.trim();
      if (v) outcomes.push(v);
    }
    return outcomes;
  }

  async function connectWallet() {
    const eip1193 = resolveEip1193Provider();
    if (!eip1193?.request) {
      throw new Error("No wallet found. Install MetaMask, Coinbase Wallet, or another browser wallet.");
    }
    provider = new ethers.BrowserProvider(eip1193);
    await provider.send("eth_requestAccounts", []);
    signer = await provider.getSigner();
    const addr = await signer.getAddress();
    $("proposeWalletAddr").textContent = addr;
    $("proposeConnectBtn").textContent = "Connected";

    // Check chain
    const net = await provider.getNetwork();
    const cid = Number(net.chainId);
    $("proposeNetworkStatus").textContent = `Network: ${CHAIN_NAMES[cid] || `chain ${cid}`}`;
    if (cid !== expectedChainId) {
      $("proposeNetworkStatus").textContent += ` (expected ${CHAIN_NAMES[expectedChainId] || expectedChainId})`;
    }

    // Default resolver to connected wallet
    const resolverInput = $("proposeResolver");
    if (resolverInput && !resolverInput.value) {
      resolverInput.value = addr;
    }
  }

  async function submitProposal() {
    setError("");
    if (!signer) await connectWallet();
    if (!factoryAddress) throw new Error("No factory address configured for this network.");
    if (!factoryAbi) await loadFactoryAbi();

    const PT = getTemplateApi();
    if (!PT) throw new Error("Template module not loaded.");
    const tpl = PT.getResolvedTemplate(selectedTemplate, getProposeProfile());
    const proposition = ($("proposeProposition")?.value || "").trim();
    if (!proposition) throw new Error("Enter a proposition (the question for this wager).");

    const isFreeform = tpl.freeform;
    let outcomes = [];
    if (!isFreeform) {
      outcomes = collectOutcomes();
      if (outcomes.length < 2) throw new Error("At least 2 outcomes are required.");
      if (outcomes.length > 255) throw new Error("Maximum 255 outcomes.");
    }

    const bettingCloseIn = Number($("proposeBettingClose")?.value || 0);
    const resolutionWindow = Number($("proposeResolutionWindow")?.value || 0);
    if (bettingCloseIn <= 0) throw new Error("Betting close window must be positive.");
    if (resolutionWindow <= 0) throw new Error("Resolution window must be positive.");

    const collateralSel = $("proposeCollateral");
    let collateralToken;
    if (collateralSel.value === "custom") {
      collateralToken = ($("proposeCollateralCustom")?.value || "").trim();
    } else {
      collateralToken = collateralSel.value;
    }
    if (!collateralToken || !ethers.isAddress(collateralToken)) {
      throw new Error("Valid collateral token address required.");
    }

    const resolverRaw = ($("proposeResolver")?.value || "").trim();
    const resolver = resolverRaw && ethers.isAddress(resolverRaw) ? resolverRaw : ethers.ZeroAddress;

    // Check chain
    const net = await provider.getNetwork();
    const cid = Number(net.chainId);
    if (cid !== expectedChainId) {
      throw new Error(`Switch wallet to ${CHAIN_NAMES[expectedChainId] || expectedChainId}. Currently on ${CHAIN_NAMES[cid] || cid}.`);
    }

    const nowSec = Math.floor(Date.now() / 1000);
    const closeTime = nowSec + bettingCloseIn;

    const factory = new ethers.Contract(factoryAddress, factoryAbi, signer);

    setStatus("Submitting create wager transaction…");
    let receipt;

    if (isFreeform) {
      const tx = await factory.createFreeformWager(
        collateralToken,
        proposition,
        BigInt(closeTime),
        BigInt(resolutionWindow),
        resolver,
        ethers.ZeroAddress, // bettingCloser
        ethers.ZeroAddress, // resolutionCloser
        [],  // extraFeeRecipients
        []   // extraFeeBps
      );
      receipt = await tx.wait();
    } else {
      const tx = await factory.createEnumeratedWager(
        collateralToken,
        proposition,
        outcomes,
        0,    // payoffPolicy: SINGLE_WINNER
        0n,   // policyParam
        BigInt(closeTime),
        BigInt(resolutionWindow),
        resolver,
        ethers.ZeroAddress, // bettingCloser
        ethers.ZeroAddress, // resolutionCloser
        [],  // extraFeeRecipients
        []   // extraFeeBps
      );
      receipt = await tx.wait();
    }

    // Find wager address from event
    let wagerAddress = null;
    for (const log of receipt.logs) {
      try {
        const parsed = factory.interface.parseLog(log);
        if (parsed && (parsed.name === "WagerCreatedV3Enumerated" || parsed.name === "WagerCreatedV3Freeform")) {
          wagerAddress = parsed.args.wager;
          break;
        }
      } catch (_) {}
    }

    if (!wagerAddress) {
      throw new Error("Wager created but could not find address in transaction receipt.");
    }

    setStatus("");
    const resultEl = $("proposeResult");
    if (resultEl) {
      const betBase = globalThis.__proposeBetPage || "bet.html";
      const betLink = `${betBase}?wager=${encodeURIComponent(wagerAddress)}`;
      resultEl.innerHTML = `<strong>Wager created:</strong> <code>${wagerAddress}</code><br>` +
        `<a href="${betLink}" class="btn btn-primary" style="margin-top:12px;display:inline-block;">Open bet page →</a>`;
      resultEl.hidden = false;
    }
  }

  async function init() {
    try {
      await loadDeployments();
    } catch (e) {
      console.warn("Could not load deployments:", e);
    }

    try {
      await loadFactoryAbi();
    } catch (e) {
      console.warn("Could not load factory ABI:", e);
    }

    populateCollateralSelect();

    // Template selection
    document.querySelectorAll("[data-template]").forEach((el) => {
      el.addEventListener("click", () => selectTemplate(el.dataset.template));
    });

    // Add outcome button
    $("proposeAddOutcome")?.addEventListener("click", addOutcome);

    // Timing display updates
    $("proposeBettingClose")?.addEventListener("input", updateTimingDisplay);
    $("proposeResolutionWindow")?.addEventListener("input", updateTimingDisplay);

    // Custom collateral toggle
    $("proposeCollateral")?.addEventListener("change", () => {
      const custom = $("proposeCollateralCustom");
      if (custom) custom.hidden = $("proposeCollateral").value !== "custom";
    });

    // Wallet
    $("proposeConnectBtn")?.addEventListener("click", async () => {
      try {
        await connectWallet();
      } catch (e) {
        setError(e.message || String(e));
      }
    });

    // Submit
    $("proposeSubmitBtn")?.addEventListener("click", async () => {
      try {
        await submitProposal();
      } catch (e) {
        setError(e.message || String(e));
        setStatus("");
      }
    });

    // Network switch listener
    const PSN = globalThis.ParamutuelSiteNetwork;
    if (PSN) {
      window.addEventListener(PSN.EVENT, () => {
        loadDeployments().then(() => populateCollateralSelect()).catch(console.warn);
      });
    }

    // Select default template
    selectTemplate("yesno");

    // Show factory info
    const factoryEl = $("proposeFactoryInfo");
    if (factoryEl) {
      if (factoryAddress) {
        factoryEl.textContent = `Factory: ${factoryAddress} on ${CHAIN_NAMES[expectedChainId] || "chain " + expectedChainId}`;
      } else {
        factoryEl.textContent = "No factory configured for this network.";
      }
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
