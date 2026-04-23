(function () {
  "use strict";

  const CONFIG_URL = "config/deployments.json";
  const PSN = window.ParamutuelSiteNetwork;
  const REFRESH_MS = 45_000;
  const LIST_LIMIT = 40;
  const OPEN_DETAIL_CAP = 8;

  let runGeneration = 0;
  let refreshTimer = null;

  function wagerIsCurrentProtocol(w) {
    const pv = String(w.protocol_version || "").trim().toLowerCase();
    return pv === "enumerated" || pv === "freeform";
  }

  function betPageHref(wagerAddress) {
    const a = String(wagerAddress || "").trim();
    if (!a) return "#";
    return `bet.html?wager=${encodeURIComponent(a)}`;
  }

  function blockExplorerAddress(chainId, address) {
    if (PSN && typeof PSN.blockExplorerAddress === "function") {
      return PSN.blockExplorerAddress(chainId, address);
    }
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
    const pv = String(w.protocol_version || "enumerated").trim().toLowerCase();

    if (state === "OPEN") {
      const d = detailByAddr[addr];
      if (pv === "freeform") {
        const n = (d && d.ticket_pools && d.ticket_pools.length) || 0;
        const sub =
          n > 0 ? `${n} pooled answer id(s)` : "no stakes in indexer detail";
        return `Pot ${pot} (raw) · ${sub}`;
      }
      if (d && d.outcomes) {
        const line = oddsLine(d.outcomes, labels);
        return `Pot ${pot} (raw) · ${line}`;
      }
      return `Pot ${pot} (raw)`;
    }
    if (state === "RESOLVED") {
      const wo = w.winning_outcome;
      let winLabel = "—";
      if (pv === "freeform") {
        const hx = wo === null || wo === undefined ? "" : String(wo).trim();
        winLabel = hx ? (hx.length > 18 ? `${hx.slice(0, 10)}…${hx.slice(-6)}` : hx) : "—";
      } else {
        try {
          const wm = BigInt(String(wo ?? "0"));
          winLabel = `mask ${wm.toString()}`;
          for (let i = 0; i < labels.length; i++) {
            if (wm === 1n << BigInt(i)) {
              winLabel = `${labels[i]} · ${winLabel}`;
              break;
            }
          }
        } catch {
          winLabel = String(wo ?? "—");
        }
      }
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
    const netKey = PSN ? PSN.getActiveNetworkKey(data) : String(data?.defaultNetwork || "baseSepolia").trim();
    const net = (PSN ? PSN.getNetworkEntry(data, netKey) : data?.[netKey]) || {};
    const apiBase = String(net.explorerApiBase || "").trim().replace(/\/$/, "");
    const chainId = net.chainId;
    return {
      apiBase,
      chainId: typeof chainId === "number" ? chainId : Number(chainId),
      networkKey: netKey,
    };
  }

  async function fetchJson(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  }

  /** Match Explorer / home search: some hosts only expose `/api/wagers`, others `/wagers`. */
  async function fetchWagersList(apiBase, limit) {
    const base = String(apiBase || "").replace(/\/$/, "");
    const q = `limit=${limit}&order=desc`;
    const paths = [`/api/wagers?${q}`, `/wagers?${q}`];
    let lastErr = null;
    for (const p of paths) {
      try {
        const r = await fetch(`${base}${p}`);
        if (r.ok) return r.json();
        if (r.status !== 404) lastErr = new Error(`HTTP ${r.status}`);
      } catch (e) {
        lastErr = e;
      }
    }
    throw lastErr || new Error("wagers list unreachable");
  }

  async function fetchWagerDetail(apiBase, addr) {
    const base = String(apiBase || "").replace(/\/$/, "");
    const a = encodeURIComponent(String(addr).toLowerCase());
    const paths = [`/api/wagers/${a}`, `/wagers/${a}`];
    for (const p of paths) {
      try {
        const r = await fetch(`${base}${p}`);
        if (r.ok) return r.json();
      } catch {
        /* try next */
      }
    }
    return null;
  }

  async function withRetries(fn, { attempts = 4, delayMs = 500 } = {}) {
    let last;
    for (let i = 0; i < attempts; i++) {
      try {
        return await fn();
      } catch (e) {
        last = e;
        if (i < attempts - 1) {
          await new Promise((r) => setTimeout(r, delayMs));
        }
      }
    }
    throw last;
  }

  function showSkeleton(track) {
    track.innerHTML = "";
    for (let i = 0; i < 5; i++) {
      const d = document.createElement("div");
      d.className = "ticker-skeleton-item";
      d.setAttribute("aria-hidden", "true");
      d.innerHTML = '<span class="ticker-sk-line ticker-sk-a"></span><span class="ticker-sk-line ticker-sk-b"></span>';
      track.appendChild(d);
    }
  }

  function renderItem(w, detailByAddr, chainId) {
    const labels = parseOutcomes(w.outcomes_json);
    const prop = truncate(w.proposition || "(no proposition)", 72);
    const state = String(w.state || "—").toLowerCase();
    const meta = stateMeta(w, detailByAddr, labels);
    const shortAddr = String(w.wager_address || "").slice(0, 10);
    const href = betPageHref(w.wager_address);
    const bs = blockExplorerAddress(chainId, w.wager_address);
    const stateClass = (state.replace(/[^a-z0-9_-]/g, "") || "unknown").slice(0, 24);

    const wrap = document.createElement("div");
    wrap.className = "ticker-item-wrap";

    const main = document.createElement("a");
    main.className = "ticker-item";
    main.href = href;
    main.innerHTML = `
      <span class="ticker-item-prop">${escapeHtml(prop)}</span>
      <span class="ticker-item-badge ticker-state-${escapeHtml(stateClass)}">${escapeHtml(state)}</span>
      <span class="ticker-item-meta">${escapeHtml(meta)}</span>
      <span class="ticker-item-addr">${escapeHtml(shortAddr)}… · Place a bet →</span>
    `;

    const ext = document.createElement("a");
    ext.className = "ticker-item-chain";
    ext.href = bs;
    ext.target = "_blank";
    ext.rel = "noopener noreferrer";
    ext.title = "View contract on block explorer";
    ext.setAttribute("aria-label", "Block explorer");
    ext.textContent = "↗";

    wrap.appendChild(main);
    wrap.appendChild(ext);
    return wrap;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function startRefreshLoop() {
    if (refreshTimer != null) return;
    refreshTimer = setInterval(() => {
      if (document.visibilityState === "visible") run();
    }, REFRESH_MS);
  }

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") run();
  });

  function paintTickerTrack(wagers, detailByAddr, cfg, viewport, track, statusMessage) {
    const statusEl = document.getElementById("tickerStatus");
    viewport.classList.remove("ticker-updating");
    track.innerHTML = "";
    wagers.forEach((w) => track.appendChild(renderItem(w, detailByAddr, cfg.chainId)));

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!reduceMotion && track.children.length > 0) {
      const nodes = [...track.children];
      nodes.forEach((node) => track.appendChild(node.cloneNode(true)));
      viewport.classList.add("ticker-animate");
    } else {
      viewport.classList.remove("ticker-animate");
    }

    if (statusEl) statusEl.textContent = statusMessage;
  }

  async function run() {
    const track = document.getElementById("tickerTrack");
    const viewport = document.getElementById("tickerViewport");
    const status = document.getElementById("tickerStatus");
    if (!track || !status || !viewport) return;

    const gen = ++runGeneration;

    const hasLiveContent =
      track.childElementCount > 0 && !track.querySelector(".ticker-skeleton-item");
    viewport.classList.remove("ticker-animate");
    if (!hasLiveContent) {
      showSkeleton(track);
      status.textContent = "Contacting indexer…";
    } else {
      viewport.classList.add("ticker-updating");
      status.textContent = "Refreshing odds and pool data…";
    }

    let cfg;
    try {
      cfg = await loadDeployments();
    } catch {
      if (gen !== runGeneration) return;
      viewport.classList.remove("ticker-updating");
      if (!hasLiveContent) track.innerHTML = "";
      status.textContent = "Add explorerApiBase in config/deployments.json to show live wagers.";
      startRefreshLoop();
      return;
    }

    if (!cfg.apiBase) {
      if (gen !== runGeneration) return;
      viewport.classList.remove("ticker-updating");
      if (!hasLiveContent) track.innerHTML = "";
      status.textContent = "No indexer URL configured for this network.";
      startRefreshLoop();
      return;
    }

    let body;
    try {
      body = await withRetries(() => fetchWagersList(cfg.apiBase, LIST_LIMIT), {
        attempts: hasLiveContent ? 2 : 4,
        delayMs: 550,
      });
    } catch {
      if (gen !== runGeneration) return;
      viewport.classList.remove("ticker-updating");
      if (!hasLiveContent) track.innerHTML = "";
      status.textContent =
        "Indexer unreachable (cold start can take a few seconds). Retrying automatically…";
      startRefreshLoop();
      return;
    }

    const wagers = (body?.wagers || []).filter(wagerIsCurrentProtocol);
    if (!wagers.length) {
      if (gen !== runGeneration) return;
      viewport.classList.remove("ticker-updating");
      track.innerHTML = "";
      status.textContent =
        "No Paramutuel protocol wagers in the latest indexer page. Create one in the app or wait for sync.";
      startRefreshLoop();
      return;
    }

    const openAddrs = wagers
      .filter((w) => String(w.state || "").toUpperCase() === "OPEN")
      .slice(0, OPEN_DETAIL_CAP)
      .map((w) => String(w.wager_address || "").toLowerCase());

    const fullStatus = `${wagers.length} recent · click a card to bet · ↗ block explorer · raw = smallest token units · auto-refresh ~${Math.round(
      REFRESH_MS / 1000
    )}s`;

    /** First visit: paint list as soon as it returns; enrich odds in a second pass (avoids blank wait during N+1 fetches + cold starts). */
    if (!hasLiveContent && openAddrs.length > 0) {
      if (gen !== runGeneration) return;
      paintTickerTrack(wagers, {}, cfg, viewport, track, `${wagers.length} recent · loading live odds…`);
    }

    const details = await Promise.all(openAddrs.map((a) => fetchWagerDetail(cfg.apiBase, a)));
    const detailByAddr = {};
    openAddrs.forEach((a, i) => {
      if (details[i]) detailByAddr[a] = details[i];
    });

    if (gen !== runGeneration) return;

    paintTickerTrack(wagers, detailByAddr, cfg, viewport, track, fullStatus);

    startRefreshLoop();
  }

  function bindNetworkRefresh() {
    if (!PSN) return;
    window.addEventListener(PSN.EVENT, () => {
      runGeneration += 1;
      run();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      bindNetworkRefresh();
      run();
    });
  } else {
    bindNetworkRefresh();
    run();
  }
})();
