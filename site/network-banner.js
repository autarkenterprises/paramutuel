/**
 * Renders the deployment strip: same DOM shape every time; content comes from
 * ParamutuelSiteNetwork.getSiteNetworkPresentation (network-context.js).
 */
(function () {
  "use strict";

  const CONFIG_URL = "config/deployments.json";
  const PSN = window.ParamutuelSiteNetwork;

  function el(id) {
    return document.getElementById(id);
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

    group.querySelectorAll("button[data-network]").forEach((btn) => {
      const key = btn.getAttribute("data-network");
      const pressed = key === activeKey;
      btn.setAttribute("aria-pressed", pressed ? "true" : "false");
      btn.classList.toggle("network-banner__switch-btn--active", pressed);
    });

    group.onclick = (ev) => {
      const t = ev.target.closest("button[data-network]");
      if (!t || !cfg) return;
      PSN.setActiveNetworkKey(t.getAttribute("data-network"), cfg);
    };
  }

  function render(slot, cfg) {
    if (!PSN) {
      slot.innerHTML =
        '<div class="network-banner network-banner--warn" role="alert"><span class="network-banner__badge">Setup</span><span class="network-banner__text">Network selector failed to load (missing network-context.js). Hard-refresh the page; if this persists, the site bundle may be incomplete.</span></div>';
      document.body.classList.add("site-has-banner");
      return;
    }

    const p = PSN.getSiteNetworkPresentation(cfg);
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
      <div class="network-banner ${p.bannerVariantClass}" role="status">
        ${switchHtml}
        <span class="network-banner__badge">${escapeHtml(p.badgeText)}</span>
        <span class="network-banner__text">${escapeHtml(p.bannerLine)}</span>
        <span class="network-banner__links">
          <a href="${escapeHtml(p.explorerRoot)}" target="_blank" rel="noopener noreferrer">Block explorer</a>
        </span>
      </div>
    `.trim();

    document.body.classList.add("site-has-banner");
    if (canToggle) wireToggle(slot, cfg, p.activeKey);

    const ctx = el("deploymentContext");
    if (ctx) {
      if (p.heroCaption) {
        ctx.textContent = p.heroCaption;
        ctx.hidden = false;
      } else {
        ctx.hidden = true;
      }
    }

    const exp = el("homeExplorerLink");
    if (exp) {
      exp.href = p.explorerRoot;
      exp.textContent = p.explorerHostLabel;
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
