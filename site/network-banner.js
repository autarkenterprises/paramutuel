/**
 * Deployment strip under nav: testnet/mainnet toggle + status line + explorer link.
 * Reads config/deployments.json; selection persists via network-context.js.
 */
(function () {
  "use strict";

  const CONFIG_URL = "config/deployments.json";
  const PSN = window.ParamutuelSiteNetwork;

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

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function wireToggle(slot, cfg, activeKey) {
    const group = slot.querySelector(".network-banner__switch");
    if (!group || !PSN) return;

    const buttons = group.querySelectorAll("button[data-network]");
    buttons.forEach((btn) => {
      const key = btn.getAttribute("data-network");
      const pressed = key === activeKey;
      btn.setAttribute("aria-pressed", pressed ? "true" : "false");
      btn.classList.toggle("network-banner__switch-btn--active", pressed);
    });

    group.onclick = (ev) => {
      const t = ev.target.closest("button[data-network]");
      if (!t || !cfg) return;
      const key = t.getAttribute("data-network");
      PSN.setActiveNetworkKey(key, cfg);
    };
  }

  function render(slot, cfg) {
    if (!PSN) {
      slot.innerHTML =
        '<div class="network-banner network-banner--warn" role="alert"><span class="network-banner__text">network-context.js must load before network-banner.js</span></div>';
      document.body.classList.add("site-has-banner");
      return;
    }

    const activeKey = PSN.getActiveNetworkKey(cfg);
    const net = PSN.getNetworkEntry(cfg, activeKey);
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
      badge = mainnetIncomplete ? "Mainnet (stub)" : "Mainnet";
      if (mainnetIncomplete) {
        line = `${chainLabel} — contracts not published in this build yet. Use testnet for live demos; fill baseMainnet in deployments.json when ready.`;
      } else {
        line = `${chainLabel} · ${apiBase ? "Markets connected" : "Market list offline"} · real funds — match your wallet to this network`;
      }
    }

    const root = blockExplorerRoot(chainId);
    const keys = PSN.validKeys(cfg);
    const canToggle = keys.length > 1;

    const switchHtml = canToggle
      ? `<div class="network-banner__switch" role="group" aria-label="Site network (saved in this browser)">
          <span class="network-banner__switch-label">Network</span>
          <button type="button" class="network-banner__switch-btn" data-network="baseSepolia" aria-pressed="false">Testnet</button>
          <button type="button" class="network-banner__switch-btn" data-network="baseMainnet" aria-pressed="false">Mainnet</button>
        </div>`
      : "";

    slot.innerHTML = `
      <div class="network-banner ${variant}" role="status">
        ${switchHtml}
        <span class="network-banner__badge">${escapeHtml(badge)}</span>
        <span class="network-banner__text">${escapeHtml(line)}</span>
        <span class="network-banner__links">
          <a href="${root}" target="_blank" rel="noopener noreferrer">Block explorer</a>
        </span>
      </div>
    `.trim();

    document.body.classList.add("site-has-banner");
    if (canToggle) wireToggle(slot, cfg, activeKey);

    const ctx = el("deploymentContext");
    if (ctx) {
      if (isTestnet) {
        ctx.textContent =
          "You are viewing Base Sepolia (testnet). Tokens are for practice — nothing here is a real-money offer.";
        ctx.hidden = false;
      } else if (isMainnet && factory && apiBase) {
        ctx.textContent =
          "You are viewing Base mainnet. Only continue if you intend to use real funds and you trust this deployment.";
        ctx.hidden = false;
      } else if (isMainnet) {
        ctx.textContent =
          "Mainnet mode is selected; this build has no factory or indexer URL yet — do not use real funds here.";
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

  function showError(slot, msg) {
    slot.innerHTML = `
      <div class="network-banner network-banner--warn" role="alert">
        <span class="network-banner__badge">Config</span>
        <span class="network-banner__text">${escapeHtml(msg)}</span>
      </div>
    `.trim();
    document.body.classList.add("site-has-banner");
  }

  let cachedCfg = null;

  async function run() {
    const slot = el("networkBannerSlot");
    if (!slot) return;
    try {
      cachedCfg = await loadJson(CONFIG_URL);
      render(slot, cachedCfg);
    } catch {
      showError(slot, "Could not load config/deployments.json — network banner unavailable.");
    }
  }

  function onNetworkChange(ev) {
    const slot = el("networkBannerSlot");
    if (!slot) return;
    const cfg = ev.detail?.config || cachedCfg;
    if (!cfg) return;
    cachedCfg = cfg;
    render(slot, cfg);
  }

  if (PSN) {
    window.addEventListener(PSN.EVENT, onNetworkChange);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();
