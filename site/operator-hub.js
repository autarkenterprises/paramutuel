/**
 * Operator hub: merges config/deployments.json + config/operator-hub.json
 * and wires the embedded explorer iframe plus outbound service links.
 */
(function () {
  "use strict";

  const DEPLOYMENTS_URL = "config/deployments.json";
  const HUB_URL = "config/operator-hub.json";

  function $(id) {
    return document.getElementById(id);
  }

  async function loadJson(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(url + " HTTP " + r.status);
    return r.json();
  }

  function setText(id, text) {
    const n = $(id);
    if (n) n.textContent = text;
  }

  function setHref(id, href, label) {
    const a = $(id);
    if (!a) return;
    a.onclick = null;
    if (!href) {
      a.href = "#";
      a.classList.add("operator-link--disabled");
      a.setAttribute("aria-disabled", "true");
      a.setAttribute("tabindex", "-1");
      a.textContent = label || "Not configured (set operator-hub.json)";
      a.onclick = (e) => e.preventDefault();
      return;
    }
    a.href = href;
    a.classList.remove("operator-link--disabled");
    a.removeAttribute("aria-disabled");
    a.removeAttribute("tabindex");
    a.textContent = label || href;
  }

  function joinUrl(base, path) {
    const b = String(base || "").replace(/\/$/, "");
    const p = String(path || "").replace(/^\//, "");
    if (!b) return "";
    return p ? `${b}/${p}` : b;
  }

  async function run() {
    let deployments;
    let hub = {};
    try {
      deployments = await loadJson(DEPLOYMENTS_URL);
    } catch (e) {
      setText("operatorHubStatus", "Could not load deployments.json: " + e.message);
      return;
    }
    try {
      hub = await loadJson(HUB_URL);
    } catch {
      /* optional file */
    }

    const netKey = String(deployments?.defaultNetwork || "baseSepolia").trim();
    const net = deployments?.[netKey] || {};
    const apiBase = String(net.explorerApiBase || "").trim().replace(/\/$/, "");

    setText("operatorHubNetwork", netKey + " (chain " + String(net.chainId ?? "—") + ")");
    setHref("operatorIndexerHealthLink", apiBase ? joinUrl(apiBase, "health") : "", "Open /health");

    const wagersUrl = apiBase ? joinUrl(apiBase, "wagers?limit=5") : "";
    setHref("operatorIndexerWagersLink", wagersUrl, "Sample /wagers");

    const frame = $("operatorExplorerFrame");
    if (frame) {
      frame.src = apiBase
        ? "explorer/index.html?api=" + encodeURIComponent(apiBase)
        : "explorer/index.html";
    }
    setText("operatorExplorerNote", apiBase ? "Indexer API prefilled from deployments.json." : "Set explorerApiBase in deployments.json.");

    const cp = String(hub.controlPanelBaseUrl || "").trim().replace(/\/$/, "");
    const prop = String(hub.propositionBaseUrl || "").trim().replace(/\/$/, "");
    const res = String(hub.resolutionBaseUrl || "").trim().replace(/\/$/, "");

    setHref("operatorControlPanelLink", cp || "", cp ? "Open control panel" : "");
    setHref("operatorPropositionLink", prop || "", prop ? "Open proposition service" : "");
    setHref("operatorResolutionLink", res || "", res ? "Open resolution service" : "");

    setText(
      "operatorHubStatus",
      "Loaded deployments for " +
        netKey +
        ". Hosted panels (control / proposition / resolution) use operator-hub.json when you deploy them."
    );
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();
