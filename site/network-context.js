/**
 * Shared site network selection (testnet vs mainnet).
 * Persists to localStorage; coordinates banner + pages that read deployments.json.
 */
(function () {
  "use strict";

  const STORAGE_KEY = "paramutuel_site_network";
  const EVENT_NAME = "paramutuel:site-network";

  /** Keys we treat as selectable when present on deployments.json */
  const SELECTABLE_KEYS = ["baseSepolia", "baseMainnet"];

  function validKeys(config) {
    if (!config || typeof config !== "object") return [];
    return SELECTABLE_KEYS.filter((k) => config[k] != null && typeof config[k] === "object");
  }

  /**
   * @param {object} config parsed deployments.json
   * @returns {string} network key (e.g. baseSepolia)
   */
  function getActiveNetworkKey(config) {
    const valid = validKeys(config);
    if (valid.length === 0) return "baseSepolia";

    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored && valid.includes(stored)) return stored;

    const def = String(config.defaultNetwork || "").trim();
    if (def && valid.includes(def)) return def;

    return valid.includes("baseSepolia") ? "baseSepolia" : valid[0];
  }

  /**
   * @param {string} key
   * @param {object} config
   */
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

  window.ParamutuelSiteNetwork = {
    STORAGE_KEY,
    EVENT: EVENT_NAME,
    SELECTABLE_KEYS,
    validKeys,
    getActiveNetworkKey,
    setActiveNetworkKey,
    getNetworkEntry,
  };
})();
