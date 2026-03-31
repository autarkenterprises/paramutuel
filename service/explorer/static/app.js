const params = new URLSearchParams(window.location.search);
const API_BASE = params.get("api") || window.EXPLORER_API_BASE || "";
const DEPLOYMENTS_CONFIG_URL = "../config/deployments.json";
const API_BASE_NORMALIZED = API_BASE.replace(/\/$/, "");
const PAGE_SIZE = 20;

let currentOffset = 0;
let lastQueryText = "";
let lastOrder = "desc";
let exhausted = false;

function apiUrl(path) {
  return `${API_BASE_NORMALIZED}${path}`;
}

function buildMarketsPath(prefix, { queryText = "", limit = PAGE_SIZE, offset = 0, order = "desc" } = {}) {
  const search = String(queryText || "").trim();
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
    order,
  });
  if (search) params.set("q", search);
  return `${prefix}/markets?${params.toString()}`;
}

async function fetchMarkets(options) {
  const candidates = [
    buildMarketsPath("/api", options),
    buildMarketsPath("", options),
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
  meta.textContent = `Loaded ${currentOffset} wager(s), ${orderLabel}${q}${tail}`;
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

function renderMarkets(markets, { append = false } = {}) {
  const tbody = document.getElementById("markets");
  if (!append) {
    tbody.innerHTML = "";
  }
  for (const m of markets) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${m.market_address}</td>
      <td>${m.state}</td>
      <td>${m.proposer}</td>
      <td>${m.resolver}</td>
      <td>${m.betting_closer}</td>
      <td>${m.resolution_closer}</td>
      <td>${m.betting_close_time}</td>
      <td>${m.resolution_window}</td>
      <td>${m.total_pot}</td>
    `;
    tbody.appendChild(tr);
  }
  if (!append && markets.length === 0) {
    tbody.innerHTML = '<tr><td colspan="9">No wagers found.</td></tr>';
  }
}

async function loadMarkets({ append = false } = {}) {
  const tbody = document.getElementById("markets");
  const apiNode = document.getElementById("apiBaseDisplay");
  const queryText = (document.getElementById("marketSearch")?.value || "").trim();
  const order = document.getElementById("marketOrder")?.value || "desc";
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
    res = await fetchMarkets({
      queryText: lastQueryText,
      order: lastOrder,
      limit: PAGE_SIZE,
      offset: currentOffset,
    });
  } catch (e) {
    tbody.innerHTML = '<tr><td colspan="9">Indexer offline or unreachable. Run the indexer locally or provide <code>?api=URL</code>.</td></tr>';
    updateResultMeta();
    return;
  }
  if (!res.ok) {
    tbody.innerHTML = `<tr><td colspan="9">Indexer returned ${res.status}.</td></tr>`;
    updateResultMeta();
    return;
  }
  const data = await res.json();
  const markets = data.markets || [];
  renderMarkets(markets, { append });
  currentOffset += markets.length;
  exhausted = markets.length < PAGE_SIZE;
  setLoadMoreEnabled(!exhausted);
  updateResultMeta();
}

document.getElementById("refresh").addEventListener("click", () => {
  loadMarkets({ append: false }).catch((e) => {
    console.error(e);
  });
});
document.getElementById("searchBtn").addEventListener("click", () => {
  loadMarkets({ append: false }).catch((e) => {
    console.error(e);
  });
});
document.getElementById("marketOrder").addEventListener("change", () => {
  loadMarkets({ append: false }).catch((e) => {
    console.error(e);
  });
});
document.getElementById("loadMore").addEventListener("click", () => {
  if (exhausted) return;
  loadMarkets({ append: true }).catch((e) => {
    console.error(e);
  });
});
document.getElementById("marketSearch").addEventListener("keydown", (ev) => {
  if (ev.key !== "Enter") return;
  ev.preventDefault();
  loadMarkets({ append: false }).catch((e) => {
    console.error(e);
  });
});

loadMarkets({ append: false }).catch((e) => {
  console.error(e);
});

loadConfiguredFactoryAddress().catch((e) => {
  console.error(e);
});
