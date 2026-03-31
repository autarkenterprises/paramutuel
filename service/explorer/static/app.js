const params = new URLSearchParams(window.location.search);
const API_BASE = params.get("api") || window.EXPLORER_API_BASE || "";
const DEPLOYMENTS_CONFIG_URL = "../config/deployments.json";
const API_BASE_NORMALIZED = API_BASE.replace(/\/$/, "");
const PAGE_SIZE = 20;

let currentOffset = 0;
let lastQueryText = "";
let lastOrder = "desc";
let exhausted = false;
let includeRowDetails = true;
let lastIndexerHint = "";

const FIELD_DEFS = [
  { key: "wager_address", label: "Wager", core: true },
  { key: "state", label: "State", core: true },
  { key: "proposition", label: "Proposition", core: true },
  { key: "outcomes_json", label: "Outcomes", core: true },
  { key: "proposer", label: "Proposer", core: true },
  { key: "resolver", label: "Resolver", core: true },
  { key: "collateral_token", label: "Collateral", core: true },
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
  meta.textContent = `Loaded ${currentOffset} wager(s), ${orderLabel}${q}${tail}${lastIndexerHint}`;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function selectedFields() {
  return FIELD_DEFS.filter((f) => selectedFieldKeys.has(f.key));
}

function getFieldValue(record, key) {
  return record[key];
}

function formatFieldValue(key, value) {
  if (value === null || value === undefined || value === "") return '<span class="muted">—</span>';
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
  if (!node) return;
  try {
    const response = await fetch(DEPLOYMENTS_CONFIG_URL);
    if (!response.ok) return;
    const data = await response.json();
    const defaultNetwork = String((data?.defaultNetwork || "baseSepolia")).trim();
    const addr = String((data?.[defaultNetwork]?.factoryAddress || "")).trim();
    if (!addr) return;
    node.textContent = addr;
  } catch (_) {
    // Optional when explorer is served standalone without deployments config.
  }
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
    tr.innerHTML = fields
      .map((f) => `<td>${formatFieldValue(f.key, getFieldValue(m, f.key))}</td>`)
      .join("");
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
    tbody.innerHTML = `<tr><td colspan="${colspan}">No wagers found.</td></tr>`;
  }
}

async function loadWagers({ append = false } = {}) {
  const tbody = document.getElementById("wagers");
  const apiNode = document.getElementById("apiBaseDisplay");
  const queryText = (document.getElementById("wagerSearch")?.value || "").trim();
  const order = document.getElementById("wagerOrder")?.value || "desc";
  if (!append) {
    currentOffset = 0;
    exhausted = false;
    lastQueryText = queryText;
    lastOrder = order;
  }
  if (apiNode) {
    apiNode.textContent = API_BASE_NORMALIZED || "same origin";
  }
  setLoadMoreEnabled(false);
  let res;
  try {
    res = await fetchWagers({
      queryText: lastQueryText,
      order: lastOrder,
      limit: PAGE_SIZE,
      offset: currentOffset,
    });
  } catch (e) {
    lastIndexerHint = "";
    tbody.innerHTML = `<tr><td colspan="${Math.max(
      1,
      selectedFields().length
    )}">Indexer offline or unreachable. Run the indexer locally or provide <code>?api=URL</code>.</td></tr>`;
    updateResultMeta();
    return;
  }
  if (!res.ok) {
    lastIndexerHint = "";
    tbody.innerHTML = `<tr><td colspan="${Math.max(
      1,
      selectedFields().length
    )}">Indexer returned ${res.status}.</td></tr>`;
    updateResultMeta();
    return;
  }
  const data = await res.json();
  const wagers = data.wagers || [];
  lastIndexerHint = "";
  if (!append && wagers.length === 0 && API_BASE_NORMALIZED) {
    try {
      const hr = await fetch(apiUrl("/health"));
      if (hr.ok) {
        const hb = await hr.json();
        const wc = hb.wager_count ?? 0;
        const lb = hb.last_indexed_block;
        const head = hb.chain_head;
        const err = hb.last_sync_error;
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
    } catch (_) {
      // ignore
    }
  }
  renderWagers(wagers, { append });
  currentOffset += wagers.length;
  exhausted = wagers.length < PAGE_SIZE;
  setLoadMoreEnabled(!exhausted);
  updateResultMeta();
}

document.getElementById("refresh").addEventListener("click", () => {
  loadWagers({ append: false }).catch((e) => {
    console.error(e);
  });
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

loadConfiguredFactoryAddress().catch((e) => {
  console.error(e);
});
