const params = new URLSearchParams(window.location.search);
const BRAND = params.get("brand") || "paramutuel";
document.documentElement.dataset.brand = BRAND;

const API_BASE = params.get("api") || window.EXPLORER_API_BASE || "";
const BET_PAGE_HREF = BRAND === "resonance" ? "../resonance-bet.html" : "../bet.html";

if (BRAND === "resonance") {
  const fontLink = document.createElement("link");
  fontLink.rel = "stylesheet";
  fontLink.href =
    "https://fonts.googleapis.com/css2?family=VT323&family=Space+Mono:ital,wght@0,400;0,700;1,400&display=swap";
  document.head.appendChild(fontLink);
  const titleEl = document.getElementById("explorerTitle");
  const subEl = document.getElementById("explorerSubtitle");
  if (titleEl) titleEl.textContent = "// EXPLORE";
  if (subEl) subEl.textContent = "Listings on the public signal — search and refresh as the relay updates.";
  document.title = "Explore — Resonance Exchange";
} else if (BRAND !== "paramutuel") {
  const titleEl = document.getElementById("explorerTitle");
  const subEl = document.getElementById("explorerSubtitle");
  if (titleEl) titleEl.textContent = "Explorer";
  if (subEl) subEl.textContent = "Reads wager state from the indexer API.";
}
const DEPLOYMENTS_CONFIG_URL = "../config/deployments.json";
const API_BASE_NORMALIZED = API_BASE.replace(/\/$/, "");
const PAGE_SIZE = 20;

function wagerIsCurrentProtocol(w) {
  const pv = String(w.protocol_version || "").trim().toLowerCase();
  return pv === "enumerated" || pv === "freeform";
}

let currentOffset = 0;
let lastQueryText = "";
let lastOrder = "desc";
let exhausted = false;
let includeRowDetails = true;
let lastIndexerHint = "";

let loadGeneration = 0;
let pollTimer = null;

/** Used to label known ERC-20 collateral on Base / Base Sepolia (matches dApp presets). */
let explorerChainId = 84532;
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

const FIELD_DEFS = [
  { key: "wager_address", label: "Wager", core: true },
  { key: "state", label: "State", core: true },
  { key: "proposition", label: "Proposition", core: true },
  { key: "outcomes_json", label: "Outcomes", core: true },
  { key: "payoff_policy", label: "Payoff policy", core: false },
  { key: "policy_param", label: "Policy param", core: false },
  { key: "proposer", label: "Proposer", core: true },
  { key: "resolver", label: "Resolver", core: true },
  { key: "collateral_token", label: "Collateral token", core: true },
  { key: "total_pot", label: "Total Pot (raw)", core: true },
  { key: "total_fee_bps", label: "Total Fee BPS", core: false },
  { key: "winning_outcome", label: "Winning Outcome", core: false },
  { key: "total_winning_stake", label: "Winning Stake (raw)", core: false },
  { key: "factory_address", label: "Factory", core: false },
  { key: "betting_closer", label: "Betting Closer", core: false },
  { key: "resolution_closer", label: "Resolution Closer", core: false },
  { key: "betting_close_time", label: "Bet Close", core: false },
  { key: "resolution_window", label: "Resolution Window", core: false },
  { key: "resolution_deadline", label: "Resolution Deadline", core: false },
  { key: "betting_closed_by_authority", label: "Betting Closed By Authority", core: false },
  { key: "betting_closed_at", label: "Betting Closed At", core: false },
  { key: "resolution_window_closed", label: "Resolution Window Closed", core: false },
  { key: "resolution_window_closed_at", label: "Resolution Window Closed At", core: false },
  { key: "created_block", label: "Created Block", core: false },
  { key: "created_tx_hash", label: "Created Tx Hash", core: false },
];
const CORE_FIELD_KEYS = FIELD_DEFS.filter((f) => f.core).map((f) => f.key);
let selectedFieldKeys = new Set(CORE_FIELD_KEYS);

function apiUrl(path) {
  return `${API_BASE_NORMALIZED}${path}`;
}

function buildWagersPath(prefix, { queryText = "", limit = PAGE_SIZE, offset = 0, order = "desc" } = {}) {
  const search = String(queryText || "").trim();
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
    order,
  });
  if (search) params.set("q", search);
  return `${prefix}/wagers?${params.toString()}`;
}

async function fetchWagers(options) {
  const candidates = [
    buildWagersPath("/api", options),
    buildWagersPath("", options),
  ];
  let lastResponse = null;
  for (const path of candidates) {
    const response = await fetch(apiUrl(path));
    if (response.ok) return response;
    lastResponse = response;
    if (response.status !== 404) return response;
  }
  return lastResponse;
}

function updateResultMeta() {
  const meta = document.getElementById("resultMeta");
  if (!meta) return;
  const orderLabel = lastOrder === "asc" ? "oldest first" : "newest first";
  const q = lastQueryText ? `, query: "${lastQueryText}"` : "";
  const tail = exhausted ? " (end reached)" : "";
  const unit = BRAND === "resonance" ? "listing" : "wager";
  meta.textContent = `Loaded ${currentOffset} ${unit}(s), ${orderLabel}${q}${tail}${lastIndexerHint}`;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatCollateralTokenCell(addr) {
  const raw = String(addr || "").trim();
  if (!raw) return '<span class="muted">—</span>';
  const sym = KNOWN_COLLATERAL_SYMBOLS[explorerChainId]?.[raw.toLowerCase()];
  const code = `<code>${escapeHtml(raw)}</code>`;
  if (sym) {
    return `<span class="token-symbol-label">${escapeHtml(sym)}</span> · ${code}`;
  }
  return code;
}

function selectedFields() {
  return FIELD_DEFS.filter((f) => selectedFieldKeys.has(f.key));
}

function getFieldValue(record, key) {
  return record[key];
}

function formatFieldValue(key, value) {
  if (value === null || value === undefined || value === "") return '<span class="muted">—</span>';
  if (key === "collateral_token") {
    return formatCollateralTokenCell(value);
  }
  if (key === "outcomes_json") {
    try {
      const parsed = typeof value === "string" ? JSON.parse(value) : value;
      if (Array.isArray(parsed)) {
        return parsed.map((v) => `<code>${escapeHtml(v)}</code>`).join(", ");
      }
    } catch (_) {}
  }
  if (typeof value === "number") return String(value);
  if (value === 0 || value === 1) {
    if (key === "betting_closed_by_authority" || key === "resolution_window_closed") {
      return value === 1 ? "true" : "false";
    }
  }
  return escapeHtml(value);
}

function renderHeader() {
  const headerRow = document.getElementById("wagerHeader") || document.querySelector("thead tr");
  if (!headerRow) return;
  const fields = selectedFields();
  headerRow.innerHTML = fields.map((f) => `<th>${f.label}</th>`).join("");
}

function applyFieldPreset(keys) {
  selectedFieldKeys = new Set(keys);
  syncFieldPickerChecks();
  renderHeader();
}

function syncFieldPickerChecks() {
  const checkboxes = document.querySelectorAll('input[name="fieldKey"]');
  for (const cb of checkboxes) {
    cb.checked = selectedFieldKeys.has(cb.value);
  }
}

function setupFieldPicker() {
  const picker = document.getElementById("fieldPicker");
  if (!picker) return;
  picker.innerHTML = FIELD_DEFS.map(
    (f) =>
      `<label><input type="checkbox" name="fieldKey" value="${f.key}" ${
        selectedFieldKeys.has(f.key) ? "checked" : ""
      } /> ${f.label}</label>`
  ).join("");
  picker.addEventListener("change", (ev) => {
    const target = ev.target;
    if (!target || target.name !== "fieldKey") return;
    if (target.checked) {
      selectedFieldKeys.add(target.value);
    } else {
      selectedFieldKeys.delete(target.value);
    }
    if (selectedFieldKeys.size === 0) {
      selectedFieldKeys.add("wager_address");
    }
    renderHeader();
    loadWagers({ append: false }).catch((e) => console.error(e));
  });

  document.getElementById("fieldsCore")?.addEventListener("click", () => {
    applyFieldPreset(CORE_FIELD_KEYS);
    loadWagers({ append: false }).catch((e) => console.error(e));
  });
  document.getElementById("fieldsAll")?.addEventListener("click", () => {
    applyFieldPreset(FIELD_DEFS.map((f) => f.key));
    loadWagers({ append: false }).catch((e) => console.error(e));
  });
  document.getElementById("includeRowDetails")?.addEventListener("change", (ev) => {
    includeRowDetails = !!ev.target.checked;
    loadWagers({ append: false }).catch((e) => console.error(e));
  });
}

function setLoadMoreEnabled(enabled) {
  const button = document.getElementById("loadMore");
  if (!button) return;
  button.disabled = !enabled;
}

async function loadConfiguredFactoryAddress() {
  const node = document.getElementById("factoryAddressDisplay");
  try {
    const response = await fetch(DEPLOYMENTS_CONFIG_URL);
    if (!response.ok) return;
    const data = await response.json();
    const defaultNetwork = String((data?.defaultNetwork || "baseSepolia")).trim();
    const net = data?.[defaultNetwork] || {};
    const cid = net.chainId;
    const parsed = typeof cid === "number" ? cid : Number(cid);
    if (!Number.isNaN(parsed)) explorerChainId = parsed;
    const addr = String((net.factoryAddress || "")).trim();
    if (node && addr) node.textContent = addr;
  } catch (_) {
    // Optional when explorer is served standalone without deployments config.
  }
}

function renderWagerCells(m, fields) {
  return fields
    .map((f) => {
      const v = getFieldValue(m, f.key);
      if (f.key === "wager_address" && v) {
        const addr = String(v).trim();
        const enc = encodeURIComponent(addr);
        return `<td class="wager-cell"><a class="bet-link" href="${BET_PAGE_HREF}?wager=${enc}" title="Open wallet staking">Bet</a> <code>${escapeHtml(
          addr
        )}</code></td>`;
      }
      return `<td>${formatFieldValue(f.key, v)}</td>`;
    })
    .join("");
}

function renderWagers(wagers, { append = false } = {}) {
  const tbody = document.getElementById("wagers");
  const fields = selectedFields();
  const colspan = Math.max(1, fields.length);
  if (!append) {
    tbody.innerHTML = "";
  }
  for (const m of wagers) {
    const tr = document.createElement("tr");
    tr.innerHTML = renderWagerCells(m, fields);
    tbody.appendChild(tr);
    if (includeRowDetails) {
      const detailsRow = document.createElement("tr");
      detailsRow.className = "details-row";
      detailsRow.innerHTML = `
        <td colspan="${colspan}">
          <details>
            <summary>All indexed fields</summary>
            <pre>${escapeHtml(JSON.stringify(m, null, 2))}</pre>
          </details>
        </td>
      `;
      tbody.appendChild(detailsRow);
    }
  }
  if (!append && wagers.length === 0) {
    const emptyMsg =
      BRAND === "paramutuel"
        ? "No Paramutuel protocol wagers in this result page."
        : "No wagers in this result page.";
    tbody.innerHTML = `<tr><td colspan="${colspan}">${emptyMsg}</td></tr>`;
  }
}

function setIndexerBusy(message) {
  const el = document.getElementById("indexerBusy");
  if (el) el.textContent = message || "";
}

function syncAutoRefresh() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  const el = document.getElementById("autoRefresh");
  if (!el || !el.checked) return;
  pollTimer = setInterval(() => {
    if (document.visibilityState === "visible") {
      loadWagers({ append: false }).catch((e) => console.error(e));
    }
  }, 45000);
}

async function loadWagers({ append = false } = {}) {
  const gen = ++loadGeneration;
  const tbody = document.getElementById("wagers");
  const apiNode = document.getElementById("apiBaseDisplay");
  const queryText = (document.getElementById("wagerSearch")?.value || "").trim();
  const order = document.getElementById("wagerOrder")?.value || "desc";
  const colspan = Math.max(1, selectedFields().length);
  if (!append) {
    currentOffset = 0;
    exhausted = false;
    lastQueryText = queryText;
    lastOrder = order;
  }
  if (apiNode && BRAND !== "resonance") {
    apiNode.textContent = API_BASE_NORMALIZED || "same origin";
  }
  setLoadMoreEnabled(false);
  if (!append) {
    const fetchLabel = BRAND === "resonance" ? "Fetching listings…" : "Fetching from indexer…";
    tbody.innerHTML = `<tr><td colspan="${colspan}"><span class="load-indicator"><span class="load-spinner" aria-hidden="true"></span> ${fetchLabel}</span></td></tr>`;
    setIndexerBusy("Loading…");
  }
  let res;
  try {
    res = await fetchWagers({
      queryText: lastQueryText,
      order: lastOrder,
      limit: PAGE_SIZE,
      offset: currentOffset,
    });
  } catch (e) {
    if (gen !== loadGeneration) return;
    lastIndexerHint = "";
    if (!append) {
      const offlineMsg =
        BRAND === "resonance"
          ? "Signal lost — the listing relay is unreachable. Try again later."
          : "Indexer offline or unreachable. Run the indexer locally or provide <code>?api=URL</code>.";
      tbody.innerHTML = `<tr><td colspan="${colspan}">${offlineMsg}</td></tr>`;
    }
    setIndexerBusy("");
    updateResultMeta();
    return;
  }
  if (!res.ok) {
    if (gen !== loadGeneration) return;
    lastIndexerHint = "";
    if (!append) {
      tbody.innerHTML = `<tr><td colspan="${colspan}">Indexer returned ${res.status}.</td></tr>`;
    }
    setIndexerBusy("");
    updateResultMeta();
    return;
  }
  const data = await res.json();
  if (gen !== loadGeneration) return;
  const rawWagers = data.wagers || [];
  const wagers = rawWagers.filter(wagerIsCurrentProtocol);
  lastIndexerHint = "";
  if (!append && rawWagers.length === 0 && API_BASE_NORMALIZED) {
    try {
      const hr = await fetch(apiUrl("/health"));
      if (hr.ok) {
        const hb = await hr.json();
        const wc = hb.wager_count ?? 0;
        const lb = hb.last_indexed_block;
        const head = hb.chain_head;
        const err = hb.last_sync_error;
        if (BRAND === "resonance") {
          lastIndexerHint = wc === 0 ? "" : ` — ${wc} on relay`;
          if (err) lastIndexerHint += ` — relay fault: ${err}`;
        } else {
          lastIndexerHint =
            ` — indexer: ${wc} wager(s) stored` +
            (lb != null ? `, last indexed block ${lb}` : "") +
            (head != null ? `, chain head ${head}` : "") +
            ".";
          if (err) {
            lastIndexerHint += ` Sync error: ${err}`;
          } else if (wc === 0 && lb != null && lb > 0) {
            lastIndexerHint +=
              " Chain has been scanned but no wagers were ingested; redeploy Cloud Run from the latest master (indexer event topics must match the factory).";
          } else if (wc === 0 && lb == null && head != null) {
            lastIndexerHint +=
              " RPC is reachable but no blocks were indexed yet (first sync may still be running).";
          } else if (wc === 0 && (lb == null || lb === 0) && head == null) {
            lastIndexerHint +=
              " RPC or sync not initialized; confirm INDEXER_FROM_BLOCK / indexerFromBlock in deployments and redeploy Cloud Run.";
          }
        }
      }
    } catch (_) {
      // ignore
    }
  }
  renderWagers(wagers, { append });
  currentOffset += rawWagers.length;
  exhausted = rawWagers.length < PAGE_SIZE;
  setLoadMoreEnabled(!exhausted);
  setIndexerBusy("");
  updateResultMeta();
}

document.getElementById("autoRefresh")?.addEventListener("change", () => syncAutoRefresh());

document.getElementById("refresh").addEventListener("click", () => {
  loadWagers({ append: false }).catch((e) => {
    console.error(e);
  });
});

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState !== "visible") return;
  const el = document.getElementById("autoRefresh");
  if (el?.checked) {
    loadWagers({ append: false }).catch((e) => console.error(e));
  }
});
document.getElementById("searchBtn").addEventListener("click", () => {
  loadWagers({ append: false }).catch((e) => {
    console.error(e);
  });
});
document.getElementById("wagerOrder").addEventListener("change", () => {
  loadWagers({ append: false }).catch((e) => {
    console.error(e);
  });
});
document.getElementById("loadMore").addEventListener("click", () => {
  if (exhausted) return;
  loadWagers({ append: true }).catch((e) => {
    console.error(e);
  });
});
document.getElementById("wagerSearch").addEventListener("keydown", (ev) => {
  if (ev.key !== "Enter") return;
  ev.preventDefault();
  loadWagers({ append: false }).catch((e) => {
    console.error(e);
  });
});

setupFieldPicker();
renderHeader();
loadWagers({ append: false }).catch((e) => {
  console.error(e);
});

syncAutoRefresh();

loadConfiguredFactoryAddress().catch((e) => {
  console.error(e);
});
