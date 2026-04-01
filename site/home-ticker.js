(function () {
  "use strict";

  const CONFIG_URL = "config/deployments.json";
  const REFRESH_MS = 90_000;
  const LIST_LIMIT = 14;
  const OPEN_DETAIL_CAP = 8;

  function blockExplorerAddress(chainId, address) {
    const a = String(address || "").trim();
    if (!a) return "#";
    if (chainId === 8453) return `https://basescan.org/address/${a}`;
    return `https://sepolia.basescan.org/address/${a}`;
  }

  function parseOutcomes(jsonStr) {
    try {
      const v = JSON.parse(jsonStr || "[]");
      return Array.isArray(v) ? v.map(String) : [];
    } catch {
      return [];
    }
  }

  function formatPot(raw) {
    try {
      const n = BigInt(String(raw || "0"));
      return n.toLocaleString("en-US");
    } catch {
      return String(raw || "0");
    }
  }

  function truncate(s, max) {
    const t = String(s || "").replace(/\s+/g, " ").trim();
    if (t.length <= max) return t;
    return t.slice(0, max - 1) + "…";
  }

  function oddsLine(outcomesRows, labels) {
    const rows = (outcomesRows || []).map((o) => ({
      idx: Number(o.outcome_index),
      t: BigInt(String(o.outcome_total || "0")),
    }));
    const sum = rows.reduce((a, o) => a + o.t, 0n);
    if (sum === 0n) return "No stakes yet";
    const parts = rows
      .map((o) => {
        const label = labels[o.idx] != null ? String(labels[o.idx]) : `#${o.idx}`;
        const pct = Number((o.t * 10000n) / sum) / 100;
        return { label: truncate(label, 14), pct };
      })
      .sort((a, b) => b.pct - a.pct)
      .slice(0, 3)
      .map((x) => `${x.label} ${x.pct.toFixed(0)}%`);
    return parts.join(" · ");
  }

  function stateMeta(w, detailByAddr, labels) {
    const state = String(w.state || "").toUpperCase();
    const pot = formatPot(w.total_pot);
    const addr = String(w.wager_address || "").toLowerCase();

    if (state === "OPEN") {
      const d = detailByAddr[addr];
      if (d && d.outcomes) {
        const line = oddsLine(d.outcomes, labels);
        return `Pot ${pot} (raw) · ${line}`;
      }
      return `Pot ${pot} (raw)`;
    }
    if (state === "RESOLVED") {
      const wo = w.winning_outcome;
      const wi = wo === null || wo === undefined || wo === "" ? null : Number(wo);
      const winLabel =
        wi != null && !Number.isNaN(wi) && labels[wi] != null
          ? String(labels[wi])
          : wi != null && !Number.isNaN(wi)
            ? `#${wi}`
            : "—";
      const winStake = formatPot(w.total_winning_stake);
      return `Winner: ${winLabel} · Winning stake ${winStake} (raw) · Pot ${pot} (raw)`;
    }
    if (state === "RETRACTED") {
      return `Retracted · Pot was ${pot} (raw)`;
    }
    return `Pot ${pot} (raw)`;
  }

  async function loadDeployments() {
    const response = await fetch(CONFIG_URL);
    if (!response.ok) throw new Error("deployments config unavailable");
    const data = await response.json();
    const defaultNetwork = String(data?.defaultNetwork || "baseSepolia").trim();
    const net = data?.[defaultNetwork] || {};
    const apiBase = String(net.explorerApiBase || "").trim().replace(/\/$/, "");
    const chainId = net.chainId;
    return { apiBase, chainId: typeof chainId === "number" ? chainId : Number(chainId), defaultNetwork };
  }

  async function fetchJson(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  }

  async function fetchWagerDetail(apiBase, addr) {
    const url = `${apiBase}/wagers/${encodeURIComponent(addr)}`;
    try {
      return await fetchJson(url);
    } catch {
      return null;
    }
  }

  function renderItem(w, detailByAddr, chainId) {
    const labels = parseOutcomes(w.outcomes_json);
    const prop = truncate(w.proposition || "(no proposition)", 80);
    const state = String(w.state || "—").toLowerCase();
    const meta = stateMeta(w, detailByAddr, labels);
    const shortAddr = String(w.wager_address || "").slice(0, 10);
    const href = blockExplorerAddress(chainId, w.wager_address);
    const stateClass = (state.replace(/[^a-z0-9_-]/g, "") || "unknown").slice(0, 24);

    const el = document.createElement("a");
    el.className = "ticker-item";
    el.href = href;
    el.target = "_blank";
    el.rel = "noopener noreferrer";
    el.innerHTML = `
      <span class="ticker-item-prop">${escapeHtml(prop)}</span>
      <span class="ticker-item-badge ticker-state-${escapeHtml(stateClass)}">${escapeHtml(state)}</span>
      <span class="ticker-item-meta">${escapeHtml(meta)}</span>
      <span class="ticker-item-addr">${escapeHtml(shortAddr)}…</span>
    `;
    return el;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  let refreshTimer = null;

  async function run() {
    const track = document.getElementById("tickerTrack");
    const viewport = document.getElementById("tickerViewport");
    const status = document.getElementById("tickerStatus");
    if (!track || !status || !viewport) return;

    status.textContent = "Loading wagers…";
    track.innerHTML = "";
    viewport.classList.remove("ticker-animate");

    let cfg;
    try {
      cfg = await loadDeployments();
    } catch {
      status.textContent = "Add explorerApiBase in config/deployments.json to show live wagers.";
      return;
    }

    if (!cfg.apiBase) {
      status.textContent = "No indexer URL configured for this network.";
      return;
    }

    let body;
    try {
      body = await fetchJson(`${cfg.apiBase}/wagers?limit=${LIST_LIMIT}&order=desc`);
    } catch {
      status.textContent = "Could not reach the indexer. Try again later.";
      return;
    }

    const wagers = body?.wagers || [];
    if (!wagers.length) {
      status.textContent = "No wagers indexed yet. Create one in the app.";
      return;
    }

    const openAddrs = wagers
      .filter((w) => String(w.state || "").toUpperCase() === "OPEN")
      .slice(0, OPEN_DETAIL_CAP)
      .map((w) => String(w.wager_address || "").toLowerCase());

    const details = await Promise.all(openAddrs.map((a) => fetchWagerDetail(cfg.apiBase, a)));
    const detailByAddr = {};
    openAddrs.forEach((a, i) => {
      if (details[i]) detailByAddr[a] = details[i];
    });

    wagers.forEach((w) => track.appendChild(renderItem(w, detailByAddr, cfg.chainId)));

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!reduceMotion && track.children.length > 0) {
      const nodes = [...track.children];
      nodes.forEach((node) => track.appendChild(node.cloneNode(true)));
      viewport.classList.add("ticker-animate");
    }

    status.textContent = `${wagers.length} recent · open a row for Basescan · raw = token smallest units`;

    if (!refreshTimer) {
      refreshTimer = setInterval(run, REFRESH_MS);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();
