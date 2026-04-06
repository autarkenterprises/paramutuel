/**
 * Operator hub: merges config/deployments.json + config/operator-hub.json
 * and wires the embedded explorer iframe plus outbound service links.
 */
(function () {
  "use strict";

  const DEPLOYMENTS_URL = "config/deployments.json";
  const HUB_URL = "config/operator-hub.json";
  const PSN = window.ParamutuelSiteNetwork;

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

  let hubCached = {};

  function paintOperatorHub(deployments, hub) {
    const netKey = PSN ? PSN.getActiveNetworkKey(deployments) : String(deployments?.defaultNetwork || "baseSepolia").trim();
    const net = PSN ? PSN.getNetworkEntry(deployments, netKey) : deployments?.[netKey] || {};
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
    setText(
      "operatorExplorerNote",
      apiBase ? "Explorer uses the indexer URL for the selected site network." : "Configure an indexer URL for this network in deployments.json to enable the embedded explorer."
    );

    const cp = String(hub.controlPanelBaseUrl || "").trim().replace(/\/$/, "");
    const prop = String(hub.propositionBaseUrl || "").trim().replace(/\/$/, "");
    const res = String(hub.resolutionBaseUrl || "").trim().replace(/\/$/, "");

    setHref("operatorControlPanelLink", cp || "", cp ? "Open control panel" : "");
    setHref("operatorPropositionLink", prop || "", prop ? "Open proposition service" : "");
    setHref("operatorResolutionLink", res || "", res ? "Open resolution service" : "");

    setText(
      "operatorHubStatus",
      "Showing " + netKey + ". Use the network toggle in the banner to switch testnet vs mainnet. Optional service links use operator-hub.json."
    );
  }

  async function run() {
    let deployments;
    try {
      deployments = await loadJson(DEPLOYMENTS_URL);
    } catch (e) {
      setText("operatorHubStatus", "Could not load deployment configuration: " + e.message);
      return;
    }
    try {
      hubCached = await loadJson(HUB_URL);
    } catch {
      hubCached = {};
    }

    paintOperatorHub(deployments, hubCached);

    if (PSN) {
      window.addEventListener(PSN.EVENT, (ev) => {
        const cfg = ev.detail && ev.detail.config;
        if (cfg) paintOperatorHub(cfg, hubCached);
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();
