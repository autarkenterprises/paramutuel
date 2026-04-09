(function () {
  "use strict";

  const CONFIG_URL = "config/deployments.json";
  const PSN = window.ParamutuelSiteNetwork;
  const DEBOUNCE_MS = 320;
  const SEARCH_LIMIT = 15;
  const OPEN_DETAIL_CAP = 15;

  let apiBase = "";
  let chainId = null;
  let debounceTimer = null;
  let fetchGen = 0;

  function $(id) {
    return document.getElementById(id);
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function truncate(s, max) {
    const t = String(s || "").replace(/\s+/g, " ").trim();
    if (t.length <= max) return t;
    return `${t.slice(0, max - 1)}…`;
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
      return BigInt(String(raw || "0")).toLocaleString("en-US");
    } catch {
      return String(raw || "0");
    }
  }

  function betPageHref(wagerAddress) {
    const a = String(wagerAddress || "").trim();
    if (!a) return "#";
    return `bet.html?wager=${encodeURIComponent(a)}`;
  }

  function buildWagersPath(
    prefix,
    { queryText = "", limit = SEARCH_LIMIT, offset = 0, order = "desc", openOnly = true } = {}
  ) {
    const search = String(queryText || "").trim();
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
      order,
    });
    if (search) params.set("q", search);
    if (openOnly) params.set("state", "OPEN");
    return `${prefix}/wagers?${params.toString()}`;
  }

  async function fetchWagersList(options) {
    const base = apiBase.replace(/\/$/, "");
    const candidates = [buildWagersPath("/api", options), buildWagersPath("", options)];
    let lastRes = null;
    for (const path of candidates) {
      const url = `${base}${path}`;
      const res = await fetch(url);
      if (res.ok) return res;
      lastRes = res;
      if (res.status !== 404) return res;
    }
    return lastRes;
  }

  async function fetchWagerDetail(addr) {
    const base = apiBase.replace(/\/$/, "");
    const a = String(addr || "").toLowerCase();
    const url = `${base}/wagers/${encodeURIComponent(a)}`;
    const r = await fetch(url);
    if (!r.ok) return null;
    return r.json();
  }

  async function loadDeployments() {
    const response = await fetch(CONFIG_URL);
    if (!response.ok) throw new Error("deployments config unavailable");
    const data = await response.json();
    const netKey = PSN ? PSN.getActiveNetworkKey(data) : String(data?.defaultNetwork || "baseSepolia").trim();
    const net = (PSN ? PSN.getNetworkEntry(data, netKey) : data?.[netKey]) || {};
    apiBase = String(net.explorerApiBase || "").trim().replace(/\/$/, "");
    const cid = net.chainId;
    chainId = typeof cid === "number" ? cid : Number(cid);
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
        return { label: truncate(label, 18), pct };
      })
      .sort((a, b) => b.pct - a.pct)
      .slice(0, 4)
      .map((x) => `${x.label} ${x.pct.toFixed(0)}%`);
    return parts.join(" · ");
  }

  function resolvedSummary(w, labels) {
    const state = String(w.state || "").toUpperCase();
    const pot = formatPot(w.total_pot);
    const pv = String(w.protocol_version || "v1").trim().toLowerCase();
    if (state === "RESOLVED") {
      const wi = w.winning_outcome;
      let winLabel = "—";
      if (pv === "freeform") {
        const hx = wi === null || wi === undefined ? "" : String(wi).trim();
        winLabel = hx ? (hx.length > 20 ? `${hx.slice(0, 12)}…${hx.slice(-6)}` : hx) : "—";
      } else if (pv === "v2") {
        try {
          const wm = BigInt(String(wi ?? "0"));
          winLabel = `mask ${wm.toString()}`;
          for (let i = 0; i < labels.length; i++) {
            if (wm === 1n << BigInt(i)) {
              winLabel = `${truncate(String(labels[i]), 16)} · ${winLabel}`;
              break;
            }
          }
        } catch {
          winLabel = String(wi ?? "—");
        }
      } else {
        const idx = wi === null || wi === undefined || wi === "" ? null : Number(wi);
        winLabel =
          idx != null && !Number.isNaN(idx) && labels[idx] != null
            ? String(labels[idx])
            : idx != null && !Number.isNaN(idx)
              ? `#${idx}`
              : "—";
      }
      return `Winner: ${winLabel} · Pot ${pot} (raw)`;
    }
    if (state === "RETRACTED") {
      return `Retracted · Pot was ${pot} (raw)`;
    }
    return `Pot ${pot} (raw)`;
  }

  async function enrichOpenWagers(wagers) {
    const open = wagers
      .filter((w) => String(w.state || "").toUpperCase() === "OPEN")
      .slice(0, OPEN_DETAIL_CAP)
      .map((w) => String(w.wager_address || "").toLowerCase());
    const details = await Promise.all(open.map((a) => fetchWagerDetail(a)));
    const map = {};
    open.forEach((a, i) => {
      if (details[i]) map[a] = details[i];
    });
    return map;
  }

  function renderResults(wagers, detailByAddr, { openOnly } = { openOnly: true }) {
    const ul = $("homeBetSearchResults");
    const status = $("homeBetSearchStatus");
    if (!ul) return;

    ul.innerHTML = "";
    if (!wagers.length) {
      if (status) {
        status.textContent = openOnly
          ? "No open wagers match. Try a different search or include resolved and retracted."
          : "No matching wagers.";
      }
      return;
    }

    if (status) {
      const q = ($("homeBetSearchInput")?.value || "").trim();
      const scope = openOnly ? "open" : "all states";
      status.textContent = q
        ? `${wagers.length} match${wagers.length === 1 ? "" : "es"} (${scope}) · click to open bet page`
        : `Showing ${wagers.length} recent ${openOnly ? "open " : ""}wager${wagers.length === 1 ? "" : "s"} · click to bet`;
    }

    for (const w of wagers) {
      const addr = String(w.wager_address || "").trim();
      const labels = parseOutcomes(w.outcomes_json);
      const state = String(w.state || "—").toUpperCase();
      const stateSlug = state.toLowerCase().replace(/[^a-z0-9-]/g, "") || "unknown";
      const pv = String(w.protocol_version || "v1").trim().toLowerCase();
      const prop = truncate(w.proposition || "(no proposition)", 120);
      const href = betPageHref(addr);
      const key = addr.toLowerCase();
      let metaLine;
      if (state === "OPEN" && detailByAddr[key]) {
        if (pv === "freeform") {
          const pools = detailByAddr[key].ticket_pools || [];
          const n = pools.filter((p) => BigInt(String(p.pool_total || "0")) > 0n).length;
          metaLine = n > 0 ? `Freeform · ${n} staked answer id(s)` : "Freeform · no stakes in detail";
        } else {
          metaLine = oddsLine(detailByAddr[key].outcomes, labels);
        }
      } else {
        metaLine = resolvedSummary(w, labels);
      }

      const li = document.createElement("li");
      li.className = "home-bet-search-item";
      const shortAddr = addr.length > 14 ? `${addr.slice(0, 8)}…${addr.slice(-6)}` : addr;

      const a = document.createElement("a");
      a.className = "home-bet-search-link";
      a.href = href;
      a.innerHTML = `
        <span class="home-bet-search-pv muted">${escapeHtml(pv)}</span>
        <span class="home-bet-search-prop">${escapeHtml(prop)}</span>
        <span class="home-bet-search-badge home-bet-search-badge--${escapeHtml(stateSlug)}">${escapeHtml(state)}</span>
        <span class="home-bet-search-meta">${escapeHtml(metaLine)}</span>
        <span class="home-bet-search-addr muted">${escapeHtml(shortAddr)}</span>
      `;
      li.appendChild(a);
      ul.appendChild(li);
    }
  }

  async function runSearch() {
    const gen = ++fetchGen;
    const spinner = $("homeBetSearchSpinner");
    const status = $("homeBetSearchStatus");
    const ul = $("homeBetSearchResults");
    const q = ($("homeBetSearchInput")?.value || "").trim();
    const includeAll = $("homeBetSearchIncludeAll")?.checked === true;
    const openOnly = !includeAll;

    if (!apiBase) {
      if (status) status.textContent = "No indexer URL in config/deployments.json for this network.";
      if (ul) ul.innerHTML = "";
      if (spinner) spinner.hidden = true;
      return;
    }

    if (spinner) spinner.hidden = false;
    if (status) status.textContent = "Searching…";

    let res;
    try {
      res = await fetchWagersList({
        queryText: q,
        order: "desc",
        limit: SEARCH_LIMIT,
        offset: 0,
        openOnly,
      });
    } catch {
      if (gen !== fetchGen) return;
      if (status) status.textContent = "Indexer unreachable.";
      if (ul) ul.innerHTML = "";
      if (spinner) spinner.hidden = true;
      return;
    }

    if (gen !== fetchGen) return;

    if (!res.ok) {
      if (status) status.textContent = `Indexer returned ${res.status}.`;
      if (ul) ul.innerHTML = "";
      if (spinner) spinner.hidden = true;
      return;
    }

    const data = await res.json();
    if (gen !== fetchGen) return;

    const wagers = data.wagers || [];
    let detailByAddr = {};
    try {
      detailByAddr = await enrichOpenWagers(wagers);
    } catch {
      detailByAddr = {};
    }
    if (gen !== fetchGen) return;

    if (spinner) spinner.hidden = true;
    renderResults(wagers, detailByAddr, { openOnly });
  }

  function scheduleSearch() {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      debounceTimer = null;
      runSearch().catch((e) => console.error(e));
    }, DEBOUNCE_MS);
  }

  function syncSearchPlaceholder() {
    const input = $("homeBetSearchInput");
    if (!input) return;
    input.placeholder = $("homeBetSearchIncludeAll")?.checked ? "Search wagers…" : "Search open wagers…";
  }

  async function init() {
    const input = $("homeBetSearchInput");
    if (!input) return;

    try {
      await loadDeployments();
    } catch {
      const status = $("homeBetSearchStatus");
      if (status) status.textContent = "Could not load deployments config.";
      return;
    }

    input.addEventListener("input", () => scheduleSearch());
    input.addEventListener("search", () => scheduleSearch());

    $("homeBetSearchIncludeAll")?.addEventListener("change", () => {
      syncSearchPlaceholder();
      runSearch().catch((e) => console.error(e));
    });

    syncSearchPlaceholder();
    await runSearch();

    if (PSN) {
      window.addEventListener(PSN.EVENT, () => {
        loadDeployments()
          .then(() => runSearch())
          .catch((e) => console.error(e));
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      init().catch((e) => console.error(e));
    });
  } else {
    init().catch((e) => console.error(e));
  }
})();
