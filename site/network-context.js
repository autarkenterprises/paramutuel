/**
 * Single source for site network selection, deployment-derived data, explorer URLs,
 * and user-facing copy. Pages keep one layout; the toggle only swaps presentation + endpoints.
 */
(function () {
  "use strict";

  const STORAGE_KEY = "paramutuel_site_network";
  const EVENT_NAME = "paramutuel:site-network";

  const SELECTABLE_KEYS = ["baseSepolia", "baseMainnet"];

  const CHAIN_META = {
    84532: { label: "Base Sepolia", isTestnet: true },
    8453: { label: "Base Mainnet", isTestnet: false },
  };

  /** Static captions (toggle only changes data; copy edits happen here). */
  const copy = {
    factoryNotPublished: "Not published for this network in this build",
    betSiteNetworkChanged:
      "Site network changed — confirm your wallet matches, then reload the wager if needed.",
    explorerIndexerDefault:
      "Default from deployments config (matches site network toggle). You can still override manually.",
    explorerIndexerAfterToggle: "Switched with site network toggle. Override manually if needed.",
    explorerIndexerMissing: "No indexer URL for this network in deployments.json.",
    explorerLeaveBlank: "Leave blank to use this site’s default wager indexer URL.",
    operatorHubStatus(netKey) {
      return `Showing ${netKey}. Use the network toggle in the banner to switch testnet vs mainnet. Optional service links use operator-hub.json.`;
    },
    operatorExplorerWithIndexer: "Explorer uses the indexer URL for the selected site network.",
    operatorExplorerNoIndexer:
      "Configure an indexer URL for this network in deployments.json to enable the embedded explorer.",
  };

  function validKeys(config) {
    if (!config || typeof config !== "object") return [];
    return SELECTABLE_KEYS.filter((k) => config[k] != null && typeof config[k] === "object");
  }

  function getActiveNetworkKey(config) {
    const valid = validKeys(config);
    if (valid.length === 0) return "baseSepolia";

    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored && valid.includes(stored)) return stored;

    const def = String(config.defaultNetwork || "").trim();
    if (def && valid.includes(def)) return def;

    return valid.includes("baseSepolia") ? "baseSepolia" : valid[0];
  }

  function setActiveNetworkKey(key, config) {
    const valid = validKeys(config);
    const k = valid.includes(String(key).trim()) ? String(key).trim() : getActiveNetworkKey(config);
    const prev = localStorage.getItem(STORAGE_KEY);
    localStorage.setItem(STORAGE_KEY, k);
    if (prev !== k) {
      window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: { networkKey: k, config } }));
    }
  }

  function getNetworkEntry(config, key) {
    const k = key || (config ? getActiveNetworkKey(config) : "baseSepolia");
    return (config && config[k]) || {};
  }

  function blockExplorerRoot(chainId) {
    const id = Number(chainId);
    if (id === 8453) return "https://basescan.org";
    return "https://sepolia.basescan.org";
  }

  function blockExplorerAddress(chainId, address) {
    const a = String(address || "").trim();
    if (!a) return "#";
    const root = blockExplorerRoot(chainId);
    return `${root}/address/${a}`;
  }

  /**
   * All banner / hero / home-card strings + classes for the active deployment entry.
   * @param {object} config — parsed deployments.json
   * @param {string} [networkKey] — override key (default: active selection)
   */
  function getSiteNetworkPresentation(config, networkKey) {
    const activeKey = networkKey != null ? String(networkKey).trim() : getActiveNetworkKey(config);
    const net = getNetworkEntry(config, activeKey);
    const chainId = Number(net.chainId);
    const meta = CHAIN_META[chainId] || { label: `Chain ${chainId}`, isTestnet: false };
    const factory = String(net.factoryAddress || "").trim();
    const apiBase = String(net.explorerApiBase || "").trim().replace(/\/$/, "");
    const isMainnetChain = chainId === 8453;
    const isTestnetChain = chainId === 84532;
    const mainnetIncomplete = isMainnetChain && (!factory || !apiBase);

    let bannerVariantClass = "network-banner--testnet";
    let badgeText = "Testnet";
    let bannerLine = `${meta.label} · ${apiBase ? "Wagers indexed" : "No wager indexer"} · practice tokens only`;

    if (isMainnetChain) {
      bannerVariantClass = mainnetIncomplete ? "network-banner--warn" : "network-banner--mainnet";
      badgeText = mainnetIncomplete ? "Mainnet (stub)" : "Mainnet";
      if (mainnetIncomplete) {
        bannerLine = `${meta.label} — contracts not published in this build yet. Use testnet for live demos; fill baseMainnet in deployments.json when ready.`;
      } else {
        bannerLine = `${meta.label} · ${apiBase ? "Wagers indexed" : "No wager indexer"} · real funds — match your wallet to this network`;
      }
    }

    const explorerRoot = blockExplorerRoot(chainId);
    let heroCaption = null;
    if (isTestnetChain) {
      heroCaption =
        "You are viewing Base Sepolia (testnet). Tokens are for practice — nothing here is a real-money offer.";
    } else if (isMainnetChain && factory && apiBase) {
      heroCaption =
        "You are viewing Base mainnet. Only continue if you intend to use real funds and you trust this deployment.";
    } else if (isMainnetChain) {
      heroCaption =
        "Mainnet mode is selected; this build has no factory or indexer URL yet — do not use real funds here.";
    }

    const homeNetworkSummaryLine = Number.isFinite(chainId)
      ? `${meta.label} (chain ID ${chainId})`
      : meta.label;
    const homeFactorySummaryText = factory || copy.factoryNotPublished;

    return {
      activeKey,
      chainId,
      chainLabel: meta.label,
      factoryAddress: factory,
      explorerApiBase: apiBase,
      explorerRoot,
      explorerHostLabel: explorerRoot.replace(/^https:\/\//, ""),
      bannerVariantClass,
      badgeText,
      bannerLine,
      heroCaption,
      homeNetworkSummaryLine,
      homeFactorySummaryText,
      mainnetIncomplete,
      isTestnetChain,
      isMainnetChain,
    };
  }

  window.ParamutuelSiteNetwork = {
    STORAGE_KEY,
    EVENT: EVENT_NAME,
    SELECTABLE_KEYS,
    validKeys,
    getActiveNetworkKey,
    setActiveNetworkKey,
    getNetworkEntry,
    getSiteNetworkPresentation,
    blockExplorerRoot,
    blockExplorerAddress,
    copy,
  };
})();
