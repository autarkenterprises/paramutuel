(function () {
  "use strict";

  const ethers = globalThis.ethers;
  // Pure open-for-stakes / odds-accuracy decisions (site/bet-logic.js, unit-tested; ADR-0019).
  const BetLogic = globalThis.ParamutuelBetLogic;
  const CONFIG_URL = "config/deployments.json";
  const COLLATERAL_ALLOWLIST_URL = "config/collateral-allowlist.json";
  const WAGER_ABI_V3_URL = "dapp/abi/ParamutuelWagerV3.json";

  const CHAIN_NAMES = {
    8453: "Base Mainnet",
    84532: "Base Sepolia",
  };

  const ERC20_DECIMALS_ABI = ["function decimals() view returns (uint8)"];
  let deployments = null;
  /** Parsed collateral allowlist (ADR-0018); null if it failed to load. */
  let collateralAllowlist = null;
  let activeNetworkKey = null;
  let expectedChainId = null;
  let wagerAbi = null;
  /** @type {"enumerated"|"freeform"} */
  let currentProtocolVersion = "enumerated";
  let indexerBase = "";
  let provider = null;
  let signer = null;
  let wagerContract = null;
  let collateralTokenAddr = "";
  let outcomeLabels = [];
  /** Checksum address of the wager currently shown (for copy / reload). */
  let loadedWagerAddress = null;
  /** Indexer row of the wager currently shown; drives whether it can take a stake. */
  let currentWagerRow = null;
  /** True once token decimals came from the chain or the user opted into manual entry. */
  let decimalsKnown = false;
  /** An answer picked from the list: sent byte-exact, since it may legitimately carry spaces. */
  let pickedAnswer = null;
  /** Wallet events are subscribed once, however many times the user connects. */
  let walletListenersAttached = false;
  /**
   * After a transaction, when to re-read the indexer. It only sees a block some way behind the chain
   * head (5 confirmations by default, so 10 seconds or more on Base), so one immediate read would show
   * the old figures and never correct them.
   */
  const REFRESH_AFTER_TX_MS = [0, 5000, 15000, 30000];
  const AFTER_TX_NOTE = "The figures above update once the indexer catches up, usually within 30 seconds.";

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

  function parseAmountHuman(amountText, decimals) {
    return ethers.parseUnits(BetLogic.parseHumanAmount(amountText), decimals);
  }

  /**
   * The single writer of the submit button's state, so that no path can re-enable staking on its own.
   * Called whenever the wager, the wallet, the decimals, or the wall clock might have changed the answer.
   */
  function syncSubmitState() {
    const reason = currentWagerRow
      ? BetLogic.stakeBlockReason({
          wager: currentWagerRow,
          nowSec: Math.floor(Date.now() / 1000),
          walletConnected: Boolean(signer),
          decimalsKnown,
        })
      : "Load a wager first.";
    $("betSubmitBtn").disabled = reason !== "";
    return reason;
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
    activeNetworkKey = netKey;
    try {
      collateralAllowlist = await loadJson(COLLATERAL_ALLOWLIST_URL);
    } catch (e) {
      console.warn("Collateral allowlist unavailable:", e);
      collateralAllowlist = null;
    }
    const net = PSN ? PSN.getNetworkEntry(data, netKey) : data?.[netKey] || {};
    indexerBase = String(net.explorerApiBase || "").trim().replace(/\/$/, "");
    const cid = net.chainId;
    expectedChainId = typeof cid === "number" ? cid : Number(cid);
    return { netKey, indexerBase, expectedChainId };
  }

  async function loadWagerAbiForProtocol(pv) {
    const p = String(pv || "enumerated").trim().toLowerCase();
    const j = await loadJson(WAGER_ABI_V3_URL);
    wagerAbi = j.abi;
    currentProtocolVersion = p === "freeform" ? "freeform" : "enumerated";
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
    currentWagerRow = null;
    syncSubmitState();
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

  /** Update the figures after a successful tx, leaving the form and its status message alone. */
  async function refreshWagerFromIndexerSilently() {
    const address = loadedWagerAddress;
    if (!address) return;
    try {
      await loadDeployments();
      const detail = await fetchWagerFromIndexer(address);
      // The user may have loaded a different wager while this was in flight.
      if (address === loadedWagerAddress) await applyWagerDetail(address, detail, { silent: true });
    } catch (e) {
      console.warn("Could not refresh wager from indexer:", e);
    }
  }

  function refreshAfterTransaction() {
    for (const delay of REFRESH_AFTER_TX_MS) setTimeout(refreshWagerFromIndexerSilently, delay);
  }

  /** Empties the form after a stake, so a second click cannot send the same stake again. */
  function clearStakeInputs() {
    document.querySelectorAll(".bet-amount-input").forEach((input) => {
      input.value = "";
    });
    const answer = $("betFreeformAnswerInput");
    if (answer) answer.value = "";
    pickedAnswer = null;
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

  function ticketPoolStakeRaw(ticketPoolsArr, outcomeIdx) {
    const mask = (1n << BigInt(outcomeIdx)).toString();
    for (const row of ticketPoolsArr || []) {
      if (String(row.ticket_mask) === mask) return BigInt(String(row.pool_total || "0"));
    }
    return 0n;
  }

  function renderFreeformPoolsTable(ticketPoolsArr, totalPotRaw, feeBpsRaw) {
    const tbody = $("betOutcomesTableBody");
    if (!tbody) return;
    const totalPot = BigInt(String(totalPotRaw || "0"));
    const feeBps = BigInt(String(feeBpsRaw || "0"));
    const net = netPotAfterFees(totalPot, feeBps);
    const rows = (ticketPoolsArr || []).filter((r) => BigInt(String(r.pool_total || "0")) > 0n);
    const sumStakes = totalPot;

    tbody.innerHTML = "";
    rows
      .map((r) => ({
        mask: String(r.ticket_mask || "").trim(),
        answer: r.answer_text === undefined ? null : r.answer_text,
        stake: BigInt(String(r.pool_total || "0")),
      }))
      .sort((a, b) => (a.stake > b.stake ? -1 : a.stake < b.stake ? 1 : 0))
      .forEach((row, i) => {
        const poolPct =
          sumStakes > 0n ? Number((row.stake * 10000n) / sumStakes) / 100 : 0;
        const mult =
          row.stake > 0n ? `${formatRatioBig(net, row.stake, 4)}x` : "—";
        const tr = document.createElement("tr");
        const note = BetLogic.answerNote(row.answer);
        // White-space is preserved because it is part of the answer. Text arrives from any bettor, so
        // it is escaped here, and handed to the form below through a closure, never through markup.
        tr.innerHTML = `
        <td>${i}</td>
        <td class="bet-outcome-name-cell">
          ${row.answer !== null ? `<span style="white-space:pre-wrap;">${escapeHtml(row.answer)}</span>` : `<code>${escapeHtml(row.mask)}</code>`}
          ${note ? `<div class="muted" style="font-size:0.85rem;">${escapeHtml(note)}</div>` : ""}
        </td>
        <td>${formatPot(row.stake)}</td>
        <td>${poolPct.toFixed(1)}%</td>
        <td>${escapeHtml(mult)}</td>
      `;
        if (row.answer !== null) {
          const pick = document.createElement("button");
          pick.type = "button";
          pick.className = "btn btn-secondary";
          pick.textContent = "Back this answer";
          pick.addEventListener("click", () => {
            const input = $("betFreeformAnswerInput");
            if (!input) return;
            input.value = row.answer;
            pickedAnswer = row.answer;
            input.focus();
          });
          tr.querySelector(".bet-outcome-name-cell").appendChild(pick);
        }
        tbody.appendChild(tr);
      });
    if (rows.length === 0) {
      const tr = document.createElement("tr");
      tr.innerHTML =
        '<td colspan="5" class="muted">No stakes yet — be the first to back an answer (exact text matters at resolution).</td>';
      tbody.appendChild(tr);
    }
  }

  function renderOutcomesOddsTable(labels, totalPotRaw, feeBpsRaw, ticketPoolsArr, payoffPolicy) {
    const tbody = $("betOutcomesTableBody");
    if (!tbody) return;

    const totalPot = BigInt(String(totalPotRaw || "0"));
    const feeBps = BigInt(String(feeBpsRaw || "0"));
    const net = netPotAfterFees(totalPot, feeBps);
    // Only SINGLE_WINNER pays `net / stake(1<<i)`; other policies divide by a
    // resolver-dependent winning-units total, so no honest per-outcome multiple exists.
    const multipleOk = BetLogic.perOutcomeMultipleSupported(payoffPolicy);

    let sumStakes = 0n;
    for (let i = 0; i < labels.length; i++) {
      sumStakes += ticketPoolStakeRaw(ticketPoolsArr, i);
    }

    tbody.innerHTML = "";
    for (let i = 0; i < labels.length; i++) {
      const label = labels[i] || `#${i}`;
      const stake = ticketPoolStakeRaw(ticketPoolsArr, i);
      const poolPct =
        sumStakes > 0n ? Number((stake * 10000n) / sumStakes) / 100 : 0;
      const mult = !multipleOk
        ? "n/a (policy)"
        : stake > 0n
          ? `${formatRatioBig(net, stake, 4)}x`
          : "—";

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

  function renderFreeformStakeInputs() {
    const host = $("betOutcomeRows");
    host.innerHTML = "";
    const row = document.createElement("div");
    row.className = "bet-outcome-row bet-freeform-row";
    row.innerHTML = `
      <label class="bet-outcome-label bet-freeform-answer-label">
        <span class="bet-outcome-name">Your answer (UTF-8)</span>
        <span class="muted" style="display:block;font-size:0.85rem;margin:4px 0 6px;">Must match resolver text <strong>exactly</strong> (bytes) if this side wins.</span>
        <input type="text" id="betFreeformAnswerInput" class="bet-freeform-text-input" autocomplete="off" spellcheck="true" placeholder="e.g. Team A · 42 · yes" />
      </label>
      <label class="bet-outcome-label">
        <span class="bet-outcome-name">Amount (human token units)</span>
        <input type="number" class="bet-amount-input" data-freeform-amount="1" min="0" step="any" placeholder="0" />
      </label>
    `;
    host.appendChild(row);
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
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
    // The name comes only from the curated list. A token's own symbol() is whatever its deployer
    // chose, so showing it would let a fake token present itself as USDC (ADR-0018).
    const trust = BetLogic.collateralTrust(collateralAllowlist, activeNetworkKey, addr);
    if (human) {
      human.hidden = !trust.symbol;
      human.textContent = trust.symbol ? `${trust.symbol} ·` : "";
    }
    const warningEl = $("betCollateralWarning");
    if (warningEl) {
      warningEl.textContent = trust.warning;
      warningEl.hidden = !trust.warning;
    }
  }

  function renderWagerWarnings(w) {
    const el = $("betLivenessWarning");
    if (!el) return;
    const warnings = BetLogic.livenessWarnings(w);
    el.textContent = warnings.join(" ");
    el.hidden = warnings.length === 0;
  }

  /**
   * Show a wager. With `silent`, as after the user's own transaction, only the figures change: the
   * form is not rebuilt and the status line stays, so a confirmation is not erased and text the user
   * has started typing is not lost.
   */
  async function applyWagerDetail(address, detail, { silent = false } = {}) {
    const w = detail.wager;
    if (!w) throw new Error("Indexer response missing wager.");

    loadedWagerAddress = address;
    currentWagerRow = w;
    if (!silent) {
      decimalsKnown = false;
      pickedAnswer = null;
    }

    const pvRaw = String(w.protocol_version || "").trim().toLowerCase();
    let pv = "enumerated";
    if (pvRaw === "freeform") pv = "freeform";
    else if (pvRaw === "enumerated") pv = "enumerated";
    else {
      clearLoading();
      showEl("betError", true);
      const errEl = $("betError");
      if (errEl) {
        errEl.textContent =
          "This wager is not indexed as a Paramutuel protocol market on this site. Open wagers from the live list or explorer, or verify the address with a block explorer.";
      }
      showEl("betSummary", false);
      showEl("betFormSection", false);
      return;
    }
    await loadWagerAbiForProtocol(pv);

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
    if (pv !== "freeform" && labels.length < 2) {
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
    const protEl = $("betProtocol");
    if (protEl) {
      if (pv === "enumerated") {
        protEl.textContent = `Paramutuel · enumerated · payoffPolicy ${w.payoff_policy != null ? w.payoff_policy : "—"} · policyParam ${
          w.policy_param != null && w.policy_param !== "" ? w.policy_param : "—"
        }`;
      } else {
        protEl.textContent = "Paramutuel · freeform";
      }
    }

    const titleEl = $("betOutcomesTableTitle");
    if (titleEl) {
      titleEl.textContent =
        pv === "freeform" ? "Answer IDs (hashed stakes) & implied odds" : "Outcomes & implied odds";
    }
    const footEl = $("betOutcomesTableFootnote");
    if (footEl) {
      footEl.textContent =
        pv === "freeform"
          ? "Freeform: each row is a domain-separated answer id (0x03 ‖ UTF-8 bytes, then keccak). Implied multiple assumes that answer wins and no further bets."
          : BetLogic.perOutcomeMultipleSupported(w.payoff_policy)
            ? "Pool share uses on-chain stake totals. Implied multiple is the approximate payout per 1 unit staked on that outcome if it wins, after protocol fees and assuming no further bets (integer rounding on-chain may differ slightly)."
            : "Pool share counts single-outcome tickets only. This wager's payoff policy splits the pot by the resolver's winning set (docs/PAYOUT-CALCULATION.md Part B), so no per-outcome multiple is shown.";
    }
    const formLead = $("betFormLead");
    if (formLead) {
      formLead.textContent =
        pv === "freeform"
          ? "Enter the exact UTF-8 answer you want to back and a human token amount. One stake per submit (call placeBet(string,uint256))."
          : "Enter a token amount next to each outcome you want to back (human units, e.g. 10 USDC). At least one positive amount is required. Batch stakes use placeBets with single-outcome ticket masks, matching the Paramutuel dApp.";
    }
    $("betWagerAddress").textContent = address;
    $("betFactory").textContent = String(w.factory_address || "").trim() || "—";
    $("betProposer").textContent = String(w.proposer || "").trim() || "—";
    $("betResolver").textContent = String(w.resolver || "").trim() || "—";
    await updateBetCollateralDisplay();
    $("betPot").textContent = formatPot(totalPotVal);
    $("betFeeBps").textContent = String(feeBpsVal);
    $("betBettingClose").textContent = formatUtcSeconds(w.betting_close_time);
    // Not `w.resolution_deadline`: that is fixed at creation, and an early closeBetting moves the real
    // deadline earlier.
    $("betResolutionDeadline").textContent = formatUtcSeconds(BetLogic.effectiveResolutionDeadline(w));
    renderWagerWarnings(w);
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
      let winLabel;
      if (pv === "freeform") {
        winLabel = `answerId ${String(totals.winning_outcome).trim()}`;
      } else {
        const wm = BigInt(String(totals.winning_outcome || "0"));
        winLabel = `mask ${wm.toString()}`;
        for (let i = 0; i < labels.length; i++) {
          if (wm === 1n << BigInt(i)) {
            winLabel = `${labels[i]} (#${i}) · mask ${wm.toString()}`;
            break;
          }
        }
      }
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

    const tPools = detail.ticket_pools || [];
    if (pv === "freeform") {
      renderFreeformPoolsTable(tPools, totalPotVal, feeBpsVal);
    } else {
      renderOutcomesOddsTable(labels, totalPotVal, feeBpsVal, tPools, w.payoff_policy);
    }

    if (silent) {
      // The refreshed row may show betting has since closed.
      syncSubmitState();
      return;
    }

    wagerContract = signer ? new ethers.Contract(address, wagerAbi, signer) : null;

    if (pv === "freeform") {
      renderFreeformStakeInputs();
    } else {
      renderOutcomeInputs(labels);
    }

    // `state === "OPEN"` persists after betting closes (by time or by the
    // betting closer), so mirror the contract's placeBet gates instead.
    const betStatus = BetLogic.bettingOpenStatus(w, Math.floor(Date.now() / 1000));
    const open = betStatus.open;
    syncSubmitState();
    if (!open) {
      let msg = betStatus.reason || "This wager is not open for new stakes.";
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
      decimalsKnown = true;
      $("betDecimalsHint").textContent = "Using manual decimals below.";
      syncSubmitState();
      return;
    }
    decimalsKnown = false;
    if (!provider) {
      $("betDecimalsHint").textContent = "Connect wallet to read decimals().";
      syncSubmitState();
      return;
    }
    try {
      const c = new ethers.Contract(collateralTokenAddr, ERC20_DECIMALS_ABI, provider);
      const d = await c.decimals();
      const n = Number(d);
      if (!Number.isFinite(n) || n < 0 || n > 77) throw new Error("Unusual decimals()");
      $("betDecimals").value = String(n);
      decimalsKnown = true;
      $("betDecimalsHint").textContent = `Token decimals: ${n} (from chain).`;
    } catch (e) {
      // The field's default stays in place, so without this block a stake could be wrong by many
      // orders of magnitude (6 assumed on an 18-decimal token).
      $("betDecimalsHint").textContent = `Could not read decimals(): ${e.message} — enable manual decimals to stake.`;
    }
    syncSubmitState();
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
    attachWalletListeners(eip1193);
    // The account or network may be changing, so decimals are unconfirmed until read again below, and
    // staking stays off until then.
    decimalsKnown = false;
    syncSubmitState();
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
      await refreshDecimals();
    }
    await updateBetCollateralDisplay();
    syncDecimalsReadonly();
    syncSubmitState();
  }

  /**
   * Follow the wallet. Without this the page keeps showing and signing as the old account, and ethers
   * fails every call on a provider whose network has changed.
   */
  function attachWalletListeners(eip1193) {
    if (walletListenersAttached || typeof eip1193.on !== "function") return;
    walletListenersAttached = true;
    const reconnect = () => {
      connectWallet().catch((e) => {
        $("betNetworkStatus").textContent = e.message || String(e);
      });
    };
    eip1193.on("accountsChanged", (accounts) => {
      if (accounts && accounts.length > 0) {
        reconnect();
        return;
      }
      signer = null;
      wagerContract = null;
      $("betWalletAddr").textContent = "";
      syncSubmitState();
    });
    eip1193.on("chainChanged", reconnect);
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
    if (currentProtocolVersion === "freeform") {
      const ansInp = $("betFreeformAnswerInput");
      const typed = ansInp ? String(ansInp.value || "") : "";
      // Trimming typed text forgives stray spaces, an off-chain convention ADR-0009 §5 allows. An
      // answer picked from the list is sent exactly, or it would land in a different pool.
      const answer = typed === pickedAnswer ? typed : typed.trim();
      if (!answer) throw new Error("Enter a non-empty answer string.");
      const amtInp = document.querySelector(".bet-amount-input[data-freeform-amount]");
      return {
        freeform: true,
        answer,
        amount: parseAmountHuman(amtInp ? amtInp.value : "", decimals),
        decimals,
      };
    }
    const inputs = document.querySelectorAll(".bet-amount-input");
    const indices = [];
    const amounts = [];
    for (const inp of inputs) {
      const raw = String(inp.value || "").trim();
      if (raw === "" || raw === "0") continue;
      const idx = Number(inp.getAttribute("data-outcome-index"));
      indices.push(idx);
      amounts.push(parseAmountHuman(raw, decimals));
    }
    if (indices.length === 0) throw new Error("Enter at least one positive stake amount.");
    return { indices, amounts, decimals, freeform: false };
  }

  async function placeBets() {
    if (!signer || !wagerContract) throw new Error("Connect wallet first.");
    await ensureChain();
    const code = await provider.getCode(wagerContract.target);
    if (code === "0x") throw new Error("No contract at this address on the current network.");

    // Time may have passed since the page loaded. Checking now avoids an approve the bet would waste.
    const blocked = syncSubmitState();
    if (blocked) throw new Error(blocked);

    const packed = collectBets();
    await assertMeetsMinimum(packed);
    const erc20Abi = ["function approve(address spender,uint256 amount) external returns (bool)"];
    const token = new ethers.Contract(collateralTokenAddr, erc20Abi, signer);
    const c = wagerContract.connect(signer);

    if (packed.freeform) {
      const total = packed.amount;
      $("betTxStatus").textContent = "Approving collateral…";
      const approveTx = await token.approve(wagerContract.target, total);
      await approveTx.wait();
      $("betTxStatus").textContent = "Submitting placeBet…";
      // Named in full: ethers v6 cannot pick between same-length overloads by value, and a bare
      // `c.placeBet(...)` throws "ambiguous function description" (ADR-0020).
      const tx = await c["placeBet(string,uint256)"](packed.answer, total);
      await tx.wait();
      $("betTxStatus").textContent = `Bet placed successfully. ${AFTER_TX_NOTE}`;
    } else {
      const { indices, amounts } = packed;
      let total = 0n;
      for (const a of amounts) total += a;
      $("betTxStatus").textContent = "Approving collateral…";
      const approveTx = await token.approve(wagerContract.target, total);
      await approveTx.wait();
      $("betTxStatus").textContent = "Submitting placeBets…";
      const firstArr = indices.map((i) => 1n << BigInt(i));
      const tx = await c.placeBets(firstArr, amounts);
      await tx.wait();
      $("betTxStatus").textContent = `Bets placed successfully. ${AFTER_TX_NOTE}`;
    }
    clearStakeInputs();
    refreshAfterTransaction();
  }

  /**
   * A new ticket below the wager's minimum would revert after the user paid for an approve. Wagers from
   * factories deployed before ADR-0020 have no `minNewTicketStake()`, so a revert means no minimum.
   */
  async function assertMeetsMinimum(packed) {
    let minStake = 0n;
    try {
      minStake = await wagerContract.minNewTicketStake();
    } catch (_) {
      return;
    }
    if (minStake === 0n) return;
    const legs = packed.freeform
      ? [{
          amount: packed.amount,
          pool: await wagerContract.ticketPoolByAnswerId(
            ethers.keccak256(ethers.concat([new Uint8Array([3]), ethers.toUtf8Bytes(packed.answer)]))
          ),
        }]
      : await Promise.all(
          packed.indices.map(async (i, n) => ({
            amount: packed.amounts[n],
            pool: await wagerContract.ticketPoolByMask(1n << BigInt(i)),
          }))
        );
    for (const leg of legs) {
      if (BetLogic.belowMinNewTicketStake({ minStake, poolTotal: leg.pool, amount: leg.amount })) {
        throw new Error(`Opening a new ticket on this wager needs at least ${minStake} raw token units.`);
      }
    }
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
