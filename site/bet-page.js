(function () {
  "use strict";

  const ethers = globalThis.ethers;
  const CONFIG_URL = "config/deployments.json";
  const WAGER_ABI_URL = "dapp/abi/ParamutuelWager.json";

  const CHAIN_NAMES = {
    8453: "Base Mainnet",
    84532: "Base Sepolia",
  };

  /** Base / Base Sepolia presets (aligned with dApp TOKEN_PRESETS). */
  const KNOWN_COLLATERAL_SYMBOLS = {
    84532: {
      "0x036cbd53842c5426634e7929541ec2318f3dcf7e": "USDC",
      "0x4200000000000000000000000000000000000006": "WETH",
    },
    8453: {
      "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913": "USDC",
      "0x4200000000000000000000000000000000000006": "WETH",
      "0x50c5725949a6f0c72e6c4a641f24049a917db0cb": "DAI",
      "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf": "cbBTC",
    },
  };

  const ERC20_DECIMALS_ABI = ["function decimals() view returns (uint8)"];
  const ERC20_SYMBOL_STRING_ABI = ["function symbol() view returns (string)"];
  const ERC20_SYMBOL_BYTES32_ABI = ["function symbol() view returns (bytes32)"];

  let deployments = null;
  let expectedChainId = null;
  let wagerAbi = null;
  let indexerBase = "";
  let provider = null;
  let signer = null;
  let wagerContract = null;
  let collateralTokenAddr = "";
  let outcomeLabels = [];
  /** Checksum address of the wager currently shown (for copy / reload). */
  let loadedWagerAddress = null;

  function $(id) {
    return document.getElementById(id);
  }

  function resolveEip1193Provider() {
    const eth = globalThis.ethereum;
    if (!eth) return null;
    if (Array.isArray(eth.providers) && eth.providers.length > 0) {
      const withRequest = eth.providers.find((p) => p && typeof p.request === "function");
      return withRequest || eth.providers[0];
    }
    return eth;
  }

  function normalizeAddress(raw) {
    const cleaned = String(raw || "")
      .replace(/[\u200B-\u200D\uFEFF\u200E\u200F\u202A-\u202E\u2060-\u2069]/g, "")
      .replace(/\s+/g, "")
      .trim();
    if (!cleaned) return null;
    let candidate = cleaned;
    if (/^[0-9a-fA-F]{40}$/.test(candidate)) candidate = `0x${candidate}`;
    if (!/^0x[0-9a-fA-F]{40}$/.test(candidate)) return null;
    try {
      return ethers.getAddress(candidate);
    } catch {
      try {
        return ethers.getAddress(candidate.toLowerCase());
      } catch {
        return null;
      }
    }
  }

  function parseAmountHuman(amountNumber, decimals) {
    return ethers.parseUnits(String(amountNumber), decimals);
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
    indexerBase = String(net.explorerApiBase || "").trim().replace(/\/$/, "");
    const cid = net.chainId;
    expectedChainId = typeof cid === "number" ? cid : Number(cid);
    return { netKey, indexerBase, expectedChainId };
  }

  async function loadWagerAbi() {
    const j = await loadJson(WAGER_ABI_URL);
    wagerAbi = j.abi;
  }

  function basescanUrl(addr) {
    const PSN = globalThis.ParamutuelSiteNetwork;
    if (PSN && typeof PSN.blockExplorerAddress === "function") {
      return PSN.blockExplorerAddress(expectedChainId, addr);
    }
    if (expectedChainId === 8453) return `https://basescan.org/address/${addr}`;
    return `https://sepolia.basescan.org/address/${addr}`;
  }

  function showEl(id, on) {
    const n = $(id);
    if (n) n.hidden = !on;
  }

  function setLoading(text) {
    showEl("betLoadPanel", true);
    const t = $("betLoadingText");
    if (t) t.textContent = text;
    $("betLoadingBlock").style.display = "flex";
  }

  function clearLoading() {
    showEl("betLoadPanel", false);
  }

  function showError(msg) {
    clearLoading();
    loadedWagerAddress = null;
    showEl("betError", true);
    showEl("betSummary", false);
    showEl("betFormSection", false);
    $("betErrorText").textContent = msg;
  }

  async function fetchWagerFromIndexer(address) {
    if (!indexerBase) throw new Error("Indexer URL missing in config/deployments.json.");
    const url = `${indexerBase}/wagers/${encodeURIComponent(address.toLowerCase())}`;
    const r = await fetch(url);
    if (r.status === 404) throw new Error("Wager not found in indexer (wrong address or not indexed yet).");
    if (!r.ok) throw new Error(`Indexer returned ${r.status}.`);
    return r.json();
  }

  /** Refresh summary/odds after a successful tx without toggling the loading panel. */
  async function refreshWagerFromIndexerSilently() {
    if (!loadedWagerAddress) return;
    try {
      await loadDeployments();
      if (!wagerAbi) await loadWagerAbi();
      const detail = await fetchWagerFromIndexer(loadedWagerAddress);
      await applyWagerDetail(loadedWagerAddress, detail);
    } catch (e) {
      console.warn("Could not refresh wager from indexer:", e);
    }
  }

  function formatPot(raw) {
    try {
      return BigInt(String(raw || "0")).toLocaleString("en-US");
    } catch {
      return String(raw || "0");
    }
  }

  function formatUtcSeconds(sec) {
    const n = Number(sec);
    if (!Number.isFinite(n) || n <= 0) return "—";
    try {
      return new Date(n * 1000).toISOString().replace("T", " ").replace(/\.\d{3}Z$/, " UTC");
    } catch {
      return String(sec);
    }
  }

  function netPotAfterFees(totalPotBn, feeBpsBn) {
    return totalPotBn - (totalPotBn * feeBpsBn) / 10000n;
  }

  function formatRatioBig(numerator, denominator, precision) {
    if (denominator === 0n) return "N/A";
    const p = BigInt(precision);
    const scale = 10n ** p;
    const scaled = (numerator * scale) / denominator;
    const whole = scaled / scale;
    const frac = (scaled % scale).toString().padStart(Number(precision), "0");
    return `${whole}.${frac}`;
  }

  function outcomeTotalsByIndex(outcomesArr) {
    const map = {};
    for (const o of outcomesArr || []) {
      map[Number(o.outcome_index)] = BigInt(String(o.outcome_total || "0"));
    }
    return map;
  }

  function renderOutcomesOddsTable(labels, outcomesArr, totalPotRaw, feeBpsRaw) {
    const tbody = $("betOutcomesTableBody");
    if (!tbody) return;

    const totalPot = BigInt(String(totalPotRaw || "0"));
    const feeBps = BigInt(String(feeBpsRaw || "0"));
    const net = netPotAfterFees(totalPot, feeBps);
    const byIdx = outcomeTotalsByIndex(outcomesArr);

    let sumStakes = 0n;
    for (let i = 0; i < labels.length; i++) {
      sumStakes += byIdx[i] ?? 0n;
    }

    tbody.innerHTML = "";
    for (let i = 0; i < labels.length; i++) {
      const label = labels[i] || `#${i}`;
      const stake = byIdx[i] ?? 0n;
      const poolPct =
        sumStakes > 0n ? Number((stake * 10000n) / sumStakes) / 100 : 0;
      const mult =
        stake > 0n ? `${formatRatioBig(net, stake, 4)}x` : "—";

      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${i}</td>
        <td class="bet-outcome-name-cell">${escapeHtml(label)}</td>
        <td>${formatPot(stake)}</td>
        <td>${poolPct.toFixed(1)}%</td>
        <td>${escapeHtml(mult)}</td>
      `;
      tbody.appendChild(tr);
    }
  }

  function renderOutcomeInputs(labels) {
    const host = $("betOutcomeRows");
    host.innerHTML = "";
    labels.forEach((label, index) => {
      const row = document.createElement("div");
      row.className = "bet-outcome-row";
      row.innerHTML = `
        <label class="bet-outcome-label">
          <span class="bet-outcome-name">${escapeHtml(label)}</span>
          <span class="bet-outcome-idx muted">#${index}</span>
          <input type="number" class="bet-amount-input" data-outcome-index="${index}" min="0" step="any" placeholder="0" />
        </label>
      `;
      host.appendChild(row);
    });
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function knownCollateralSymbol(addr) {
    if (!addr || expectedChainId == null) return null;
    const m = KNOWN_COLLATERAL_SYMBOLS[expectedChainId];
    return m ? m[String(addr).toLowerCase()] || null : null;
  }

  async function fetchCollateralSymbolFromChain(addr) {
    if (!provider || !ethers.isAddress(addr)) return null;
    const cStr = new ethers.Contract(addr, ERC20_SYMBOL_STRING_ABI, provider);
    try {
      const s = await cStr.symbol();
      if (typeof s === "string") {
        const t = s.trim();
        if (t) return t.slice(0, 32);
      }
    } catch (_) {}
    try {
      const cB = new ethers.Contract(addr, ERC20_SYMBOL_BYTES32_ABI, provider);
      const b = await cB.symbol();
      if (b != null && typeof ethers.decodeBytes32String === "function") {
        const t = ethers.decodeBytes32String(b).trim();
        if (t) return t.slice(0, 32);
      }
    } catch (_) {}
    return null;
  }

  async function updateBetCollateralDisplay() {
    const human = $("betCollateralHuman");
    const code = $("betCollateral");
    if (!code) return;
    const addr = collateralTokenAddr;
    if (!addr || !ethers.isAddress(addr)) {
      code.textContent = "—";
      if (human) {
        human.hidden = true;
        human.textContent = "";
      }
      return;
    }
    const checksum = ethers.getAddress(addr);
    code.textContent = checksum;
    let sym = knownCollateralSymbol(addr);
    if (!sym && provider) {
      try {
        sym = await fetchCollateralSymbolFromChain(addr);
      } catch (_) {
        sym = null;
      }
    }
    if (human) {
      if (sym) {
        human.hidden = false;
        human.textContent = `${sym} ·`;
      } else {
        human.hidden = true;
        human.textContent = "";
      }
    }
  }

  async function applyWagerDetail(address, detail) {
    const w = detail.wager;
    if (!w) throw new Error("Indexer response missing wager.");

    loadedWagerAddress = address;

    const state = String(w.state || "").toUpperCase();
    const proposition = String(w.proposition || "").trim() || "(empty proposition)";
    collateralTokenAddr = String(w.collateral_token || "").trim();

    let labels = [];
    try {
      const arr = JSON.parse(w.outcomes_json || "[]");
      if (Array.isArray(arr)) labels = arr.map(String);
    } catch {
      labels = [];
    }
    if (labels.length < 2) {
      throw new Error("Wager has fewer than two outcomes in the index.");
    }

    outcomeLabels = labels;
    const totals = detail.totals || {};
    const totalPotVal = totals.total_pot ?? "0";
    const feeBpsVal = totals.total_fee_bps ?? w.total_fee_bps ?? "0";

    clearLoading();
    showEl("betError", false);
    showEl("betSummary", true);
    showEl("betFormSection", true);

    $("betProposition").textContent = proposition;
    $("betState").textContent = state;
    $("betWagerAddress").textContent = address;
    $("betFactory").textContent = String(w.factory_address || "").trim() || "—";
    $("betProposer").textContent = String(w.proposer || "").trim() || "—";
    $("betResolver").textContent = String(w.resolver || "").trim() || "—";
    await updateBetCollateralDisplay();
    $("betPot").textContent = formatPot(totalPotVal);
    $("betFeeBps").textContent = String(feeBpsVal);
    $("betBettingClose").textContent = formatUtcSeconds(w.betting_close_time);
    $("betResolutionDeadline").textContent = formatUtcSeconds(w.resolution_deadline);
    $("betResolutionWindow").textContent =
      w.resolution_window != null && w.resolution_window !== "" ? String(w.resolution_window) : "—";

    const winRow = $("betWinningRow");
    const winOut = $("betWinningOutcome");
    if (
      state === "RESOLVED" &&
      totals &&
      totals.winning_outcome != null &&
      totals.winning_outcome !== ""
    ) {
      const wi = Number(totals.winning_outcome);
      const winLabel =
        !Number.isNaN(wi) && labels[wi] != null ? `${labels[wi]} (#${wi})` : `#${totals.winning_outcome}`;
      const winStake = formatPot(totals.total_winning_stake ?? "0");
      winOut.textContent = `${winLabel} · winning stake ${winStake} (raw)`;
      if (winRow) winRow.hidden = false;
    } else {
      if (winRow) winRow.hidden = true;
      if (winOut) winOut.textContent = "—";
    }

    const txShort = String(w.created_tx_hash || "").trim();
    const txDisp = txShort.length > 18 ? `${txShort.slice(0, 10)}…${txShort.slice(-6)}` : txShort;
    $("betCreatedMeta").textContent =
      w.created_block != null && txDisp
        ? `Block ${w.created_block} · ${txDisp}`
        : w.created_block != null
          ? `Block ${w.created_block}`
          : txDisp || "—";

    const scan = $("betBasescan");
    scan.href = basescanUrl(address);
    scan.textContent = "View on Basescan";

    renderOutcomesOddsTable(labels, detail.outcomes, totalPotVal, feeBpsVal);

    wagerContract = signer ? new ethers.Contract(address, wagerAbi, signer) : null;

    renderOutcomeInputs(labels);

    const open = state === "OPEN";
    $("betSubmitBtn").disabled = !open || !signer;
    if (!open) {
      let msg = "This wager is not open for new stakes.";
      if (state === "RESOLVED") msg = "Resolved — staking is closed. Winners can claim from the full dApp if applicable.";
      else if (state === "RETRACTED") msg = "Retracted — staking is closed.";
      $("betTxStatus").textContent = msg;
    } else {
      $("betTxStatus").textContent = "";
    }

    if (open && signer) {
      await refreshDecimals();
    } else {
      $("betDecimalsHint").textContent = open
        ? "Connect your wallet to read token decimals from the chain."
        : "";
    }
  }

  async function refreshDecimals() {
    if (!collateralTokenAddr || !ethers.isAddress(collateralTokenAddr)) {
      $("betDecimalsHint").textContent = "Invalid collateral token in index.";
      return;
    }
    if ($("betDecimalsManual").checked) {
      $("betDecimalsHint").textContent = "Using manual decimals below.";
      return;
    }
    if (!provider) {
      $("betDecimalsHint").textContent = "Connect wallet to read decimals().";
      return;
    }
    try {
      const c = new ethers.Contract(collateralTokenAddr, ERC20_DECIMALS_ABI, provider);
      const d = await c.decimals();
      const n = Number(d);
      if (!Number.isFinite(n) || n < 0 || n > 77) throw new Error("Unusual decimals()");
      $("betDecimals").value = String(n);
      $("betDecimalsHint").textContent = `Token decimals: ${n} (from chain).`;
    } catch (e) {
      $("betDecimalsHint").textContent = `Could not read decimals(): ${e.message} — enable manual decimals.`;
    }
  }

  async function ensureChain() {
    if (expectedChainId == null || Number.isNaN(expectedChainId)) return;
    const net = await provider.getNetwork();
    const cid = Number(net.chainId);
    if (cid !== expectedChainId) {
      throw new Error(
        `Switch your wallet to ${CHAIN_NAMES[expectedChainId] || "the configured network"} (chain ID ${expectedChainId}). Currently on ${cid}.`
      );
    }
  }

  async function connectWallet() {
    const eip1193 = resolveEip1193Provider();
    if (!eip1193?.request) {
      throw new Error(
        "No EIP-1193 wallet found. Use a browser wallet that injects window.ethereum (MetaMask, Rabby, Coinbase Wallet, …)."
      );
    }
    provider = new ethers.BrowserProvider(eip1193);
    await provider.send("eth_requestAccounts", []);
    signer = await provider.getSigner();
    const addr = await signer.getAddress();
    $("betWalletAddr").textContent = addr;
    await ensureChain();
    const net = await provider.getNetwork();
    $("betNetworkStatus").textContent = `Network: ${CHAIN_NAMES[Number(net.chainId)] || "chain"} (ID ${Number(net.chainId)})`;

    const wa = normalizeAddress($("wagerAddressInput").value) || getWagerFromQuery();
    if (wa && wagerAbi) {
      wagerContract = new ethers.Contract(wa, wagerAbi, signer);
      const st = String($("betState").textContent || "").toUpperCase();
      $("betSubmitBtn").disabled = st !== "OPEN";
      await refreshDecimals();
    }
    await updateBetCollateralDisplay();
    syncDecimalsReadonly();
  }

  function syncDecimalsReadonly() {
    const manual = $("betDecimalsManual").checked;
    $("betDecimals").readOnly = !manual;
  }

  function getWagerFromQuery() {
    const q = new URLSearchParams(window.location.search).get("wager");
    return q ? normalizeAddress(q) : null;
  }

  async function loadWager(address) {
    const addr = normalizeAddress(address);
    if (!addr) {
      showError("Enter a valid 0x wager address.");
      return;
    }

    showEl("betError", false);
    setLoading("Fetching wager from indexer…");
    $("wagerAddressInput").value = addr;
    history.replaceState(null, "", `${window.location.pathname}?wager=${encodeURIComponent(addr)}`);

    try {
      await loadDeployments();
      if (!wagerAbi) await loadWagerAbi();
      const detail = await fetchWagerFromIndexer(addr);
      await applyWagerDetail(addr, detail);
    } catch (e) {
      console.error(e);
      showError(e.message || String(e));
    }
  }

  function collectBets() {
    const decimals = Number($("betDecimals").value);
    if (!Number.isFinite(decimals) || decimals < 0 || decimals > 77) {
      throw new Error("Invalid decimals (0–77).");
    }
    const inputs = document.querySelectorAll(".bet-amount-input");
    const indices = [];
    const amounts = [];
    for (const inp of inputs) {
      const raw = String(inp.value || "").trim();
      if (raw === "" || raw === "0") continue;
      const n = Number(raw);
      if (!Number.isFinite(n) || n <= 0) throw new Error("Each non-empty amount must be a positive number.");
      const idx = Number(inp.getAttribute("data-outcome-index"));
      indices.push(idx);
      amounts.push(parseAmountHuman(n, decimals));
    }
    if (indices.length === 0) throw new Error("Enter at least one positive stake amount.");
    return { indices, amounts, decimals };
  }

  async function placeBets() {
    if (!signer || !wagerContract) throw new Error("Connect wallet first.");
    await ensureChain();
    const code = await provider.getCode(wagerContract.target);
    if (code === "0x") throw new Error("No contract at this address on the current network.");

    const { indices, amounts } = collectBets();
    let total = 0n;
    for (const a of amounts) total += a;

    const erc20Abi = ["function approve(address spender,uint256 amount) external returns (bool)"];
    const token = new ethers.Contract(collateralTokenAddr, erc20Abi, signer);

    $("betTxStatus").textContent = "Approving collateral…";
    const approveTx = await token.approve(wagerContract.target, total);
    await approveTx.wait();

    $("betTxStatus").textContent = "Submitting placeBets…";
    const c = wagerContract.connect(signer);
    const tx = await c.placeBets(indices, amounts);
    await tx.wait();
    $("betTxStatus").textContent = "Bets placed successfully.";
    await refreshWagerFromIndexerSilently();
  }

  async function copyLoadedWagerAddress() {
    if (!loadedWagerAddress || !navigator.clipboard?.writeText) {
      $("betTxStatus").textContent = "Copy not supported in this browser.";
      return;
    }
    try {
      await navigator.clipboard.writeText(loadedWagerAddress);
      const btn = $("betCopyAddressBtn");
      if (btn) {
        const prev = btn.textContent;
        btn.textContent = "Copied";
        setTimeout(() => {
          btn.textContent = prev;
        }, 2000);
      }
    } catch (e) {
      $("betTxStatus").textContent = e.message || String(e);
    }
  }

  async function init() {
    try {
      await loadDeployments();
      await loadWagerAbi();
    } catch (e) {
      console.warn(e);
    }

    $("betCopyAddressBtn")?.addEventListener("click", () => {
      copyLoadedWagerAddress().catch((e) => console.error(e));
    });

    $("loadWagerBtn").addEventListener("click", () => loadWager($("wagerAddressInput").value));
    $("wagerAddressInput").addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") {
        ev.preventDefault();
        loadWager($("wagerAddressInput").value);
      }
    });

    $("betConnectBtn").addEventListener("click", async () => {
      try {
        await connectWallet();
      } catch (e) {
        $("betNetworkStatus").textContent = e.message || String(e);
      }
    });

    $("betDecimalsManual").addEventListener("change", () => {
      syncDecimalsReadonly();
      refreshDecimals();
    });
    $("betDecimals").addEventListener("change", () => {
      if ($("betDecimalsManual").checked) $("betDecimalsHint").textContent = "Manual decimals.";
    });

    $("betSubmitBtn").addEventListener("click", async () => {
      try {
        if (!signer) await connectWallet();
        await placeBets();
      } catch (e) {
        $("betTxStatus").textContent = e.message || String(e);
      }
    });

    syncDecimalsReadonly();

    const fromQuery = getWagerFromQuery();
    if (fromQuery) {
      $("wagerAddressInput").value = fromQuery;
      loadWager(fromQuery);
    }

    const PSN = globalThis.ParamutuelSiteNetwork;
    if (PSN) {
      window.addEventListener(PSN.EVENT, () => {
        loadDeployments()
          .then(async () => {
            const st = $("betNetworkStatus");
            if (st && PSN.copy) st.textContent = PSN.copy.betSiteNetworkChanged;
            if (loadedWagerAddress) {
              await loadWager(loadedWagerAddress);
            }
          })
          .catch((e) => console.warn(e));
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
