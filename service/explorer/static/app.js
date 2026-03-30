const params = new URLSearchParams(window.location.search);
const API_BASE = params.get("api") || window.EXPLORER_API_BASE || "";
const DEPLOYMENTS_CONFIG_URL = "../config/deployments.json";
const API_BASE_NORMALIZED = API_BASE.replace(/\/$/, "");

function apiUrl(path) {
  return `${API_BASE_NORMALIZED}${path}`;
}

function buildMarketsPath(prefix, queryText) {
  const search = String(queryText || "").trim();
  const params = new URLSearchParams({ limit: "100" });
  if (search) params.set("q", search);
  return `${prefix}/markets?${params.toString()}`;
}

async function fetchMarkets(queryText) {
  const candidates = [
    buildMarketsPath("/api", queryText),
    buildMarketsPath("", queryText),
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

async function loadMarkets() {
  const tbody = document.getElementById("markets");
  const apiNode = document.getElementById("apiBaseDisplay");
  const queryText = (document.getElementById("marketSearch")?.value || "").trim();
  if (apiNode) {
    apiNode.textContent = API_BASE_NORMALIZED || "same origin";
  }
  let res;
  try {
    res = await fetchMarkets(queryText);
  } catch (e) {
    tbody.innerHTML = '<tr><td colspan="9">Indexer offline or unreachable. Run the indexer locally or provide <code>?api=URL</code>.</td></tr>';
    return;
  }
  if (!res.ok) {
    tbody.innerHTML = `<tr><td colspan="9">Indexer returned ${res.status}.</td></tr>`;
    return;
  }
  const data = await res.json();
  tbody.innerHTML = "";
  for (const m of data.markets || []) {
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
  if ((data.markets || []).length === 0) {
    tbody.innerHTML = '<tr><td colspan="9">No markets found.</td></tr>';
  }
}

document.getElementById("refresh").addEventListener("click", () => {
  loadMarkets().catch((e) => {
    console.error(e);
  });
});
document.getElementById("searchBtn").addEventListener("click", () => {
  loadMarkets().catch((e) => {
    console.error(e);
  });
});
document.getElementById("marketSearch").addEventListener("keydown", (ev) => {
  if (ev.key !== "Enter") return;
  ev.preventDefault();
  loadMarkets().catch((e) => {
    console.error(e);
  });
});

loadMarkets().catch((e) => {
  console.error(e);
});

loadConfiguredFactoryAddress().catch((e) => {
  console.error(e);
});
