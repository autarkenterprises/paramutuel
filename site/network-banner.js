/**
 * Reads config/deployments.json and renders a deployment strip under the main nav.
 * Testnet vs mainnet are visually distinct; warns when mainnet is selected but incomplete.
 */
(function () {
  "use strict";

  const CONFIG_URL = "config/deployments.json";

  const CHAIN_NAMES = {
    84532: "Base Sepolia",
    8453: "Base",
  };

  function el(id) {
    return document.getElementById(id);
  }

  function blockExplorerRoot(chainId) {
    if (chainId === 8453) return "https://basescan.org";
    return "https://sepolia.basescan.org";
  }

  async function loadJson(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(String(r.status));
    return r.json();
  }

  function render(slot, cfg) {
    const key = String(cfg?.defaultNetwork || "baseSepolia").trim();
    const net = cfg?.[key] || {};
    const chainId = Number(net.chainId);
    const factory = String(net.factoryAddress || "").trim();
    const apiBase = String(net.explorerApiBase || "").trim().replace(/\/$/, "");
    const chainLabel = CHAIN_NAMES[chainId] || `chain ${chainId}`;

    const isTestnet = chainId === 84532;
    const isMainnet = chainId === 8453;
    const mainnetIncomplete = isMainnet && (!factory || !apiBase);

    let variant = "network-banner--testnet";
    let badge = "Testnet";
    let line = `${chainLabel} · ${apiBase ? "Markets connected" : "Market list offline"} · practice tokens only`;

    if (isMainnet) {
      variant = mainnetIncomplete ? "network-banner--warn" : "network-banner--mainnet";
      badge = mainnetIncomplete ? "Mainnet (setup)" : "Mainnet";
      if (mainnetIncomplete) {
        line = `${chainLabel} — not ready for real funds yet. Prefer a testnet deployment for practice.`;
      } else {
        line = `${chainLabel} · ${apiBase ? "Markets connected" : "Market list offline"} · real funds — check your wallet matches this network`;
      }
    }

    const root = blockExplorerRoot(chainId);

    slot.innerHTML = `
      <div class="network-banner ${variant}" role="status">
        <span class="network-banner__badge">${escapeHtml(badge)}</span>
        <span class="network-banner__text">${escapeHtml(line)}</span>
        <span class="network-banner__links">
          <a href="${root}" target="_blank" rel="noopener noreferrer">Block explorer</a>
        </span>
      </div>
    `.trim();

    document.body.classList.add("site-has-banner");

    const ctx = el("deploymentContext");
    if (ctx) {
      if (isTestnet) {
        ctx.textContent =
          "You are on Base Sepolia (testnet). Tokens are for practice only — nothing here is a real-money offer.";
        ctx.hidden = false;
      } else if (isMainnet && factory && apiBase) {
        ctx.textContent =
          "You are on Base mainnet. Only continue if you intend to use real funds and you trust this deployment.";
        ctx.hidden = false;
      } else if (isMainnet) {
        ctx.textContent =
          "Mainnet is selected but this site is not fully configured — do not use real funds here until the banner shows a complete setup.";
        ctx.hidden = false;
      } else {
        ctx.hidden = true;
      }
    }

    const exp = el("homeExplorerLink");
    if (exp) {
      exp.href = root;
      exp.textContent = root.replace(/^https:\/\//, "");
    }
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function showError(slot, msg) {
    slot.innerHTML = `
      <div class="network-banner network-banner--warn" role="alert">
        <span class="network-banner__badge">Config</span>
        <span class="network-banner__text">${escapeHtml(msg)}</span>
      </div>
    `.trim();
    document.body.classList.add("site-has-banner");
  }

  async function run() {
    const slot = el("networkBannerSlot");
    if (!slot) return;
    try {
      const cfg = await loadJson(CONFIG_URL);
      render(slot, cfg);
    } catch {
      showError(slot, "Could not load config/deployments.json — network banner unavailable.");
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();
