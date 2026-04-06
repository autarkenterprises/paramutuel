# Protocol website (GitHub Pages)

The static site under `site/` is a **thin shell**: marketing copy, a testnet/mainnet **banner with an in-browser toggle** (persists in `localStorage`), and **iframes** that embed the self-custody dApp (`dapp/`) and the indexer-backed explorer (`service/explorer/static/`) without merging their codebases.

## Pages

| Path | Role |
|------|------|
| `/` | Landing: primary CTAs (propose / bet), live ticker, wager lifecycle, then protocol orientation + network |
| `/propose-a-wager.html` | Create path — copy + link into embedded dApp for factory deploy |
| `/place-a-bet.html` | Betting entry — indexer search + CTA into wallet staking (`bet.html`) |
| `/app.html` | Full dApp embedded via iframe |
| `/bet.html` | Wallet staking (`placeBets`; not in nav — reached from Place a Bet, feed, Explorer, or `?wager=`) |
| `/explorer.html` | Explorer UI with optional indexer URL override |
| `/operator.html` | **Operator hub** — indexer links, embedded explorer, outbound URLs for other services |
| `/dapp/` | Same dApp as embedded, for direct links and debugging |

Runtime configuration is read from `config/deployments.json` (copied to `_site/config/` in CI). Optional **`config/operator-hub.json`** supplies public base URLs for hosted operator panels (control, proposition, resolution) when you deploy them outside GitHub Pages.

## Testnet vs mainnet on the public site

**Visitors** use the **Network** control in the banner (`Testnet` = Base Sepolia, `Mainnet` = Base). The choice is stored in the browser as `localStorage.paramutuel_site_network` and drives the home ticker, **Place a Bet** search (`place-a-bet.html`), `bet.html` indexer URL, explorer default API field, embedded dApp (`?siteNetwork=…`), and operator hub indexer links.

**`site/network-context.js`** holds selection helpers, **`getSiteNetworkPresentation()`** (banner badge, banner line, hero caption, home “Network” card lines, explorer root), shared **`blockExplorerAddress`**, and static **`copy`** strings so the toggle only swaps data-driven text and endpoints — **one page layout, no duplicated shells**. **`site/network-banner.js`** only fetches `deployments.json` and renders the existing banner DOM using that presentation.

**`defaultNetwork`** in **`config/deployments.json`** is still used for:

- First-time visitors (no saved toggle yet).
- Fallback when the saved key is missing from the file.

### Turnkey checklist when Base mainnet is live

1. Edit **`config/deployments.json`**.
2. Under **`baseMainnet`**, set **`factoryAddress`**, **`explorerApiBase`**, and **`indexerFromBlock`** (for your indexer deployment). Keep **`chainId`** `8453`.
3. Optionally set **`defaultNetwork`** to `"baseMainnet"` if you want new visitors to land on mainnet by default.
4. Commit and push; **Deploy to GitHub Pages** rebuilds the site.

Until those fields are filled, the banner shows **Mainnet (stub)** and explains that the build is not ready for real funds.

The **dApp** (`dapp/app.js`) picks the factory address from `deployments.json` using the **connected wallet’s chain** when possible; when the wallet is not connected yet, it uses the **`siteNetwork`** query parameter set by `app.html`, then `defaultNetwork`.

## Operator hub

`site/operator.html` + `site/operator-hub.js` provide a **single navigation point** for operators:

- Derives **indexer `/health`** and sample **`/wagers`** links from `deployments.json`.
- Embeds the **explorer** with the indexer API query string prefilled.
- Uses **`operator-hub.json`** for optional `controlPanelBaseUrl`, `propositionBaseUrl`, `resolutionBaseUrl` (empty = disabled link with explanation).

Hosted panels usually require **authentication** and **HTTPS**; do not expose execution-enabled control or resolution UIs without the controls described in `service/README.md` and the respective service docs.

## Local smoke test

From repo root (after `forge build` if you need fresh ABIs):

```bash
mkdir -p _site/dapp/abi _site/explorer _site/config
python3 -c "
import json
for name in ['ParamutuelFactory', 'ParamutuelWager']:
    data = json.load(open(f'out/{name}.sol/{name}.json'))
    with open(f'_site/dapp/abi/{name}.json', 'w') as f:
        json.dump({'abi': data['abi']}, f, indent=2)
        f.write('\n')
"
cp site/*.html site/*.css site/*.js _site/
cp dapp/index.html dapp/app.js dapp/logic.js dapp/style.css _site/dapp/
cp service/explorer/static/* _site/explorer/
cp config/deployments.json config/operator-hub.json _site/config/
cd _site && python3 -m http.server 8080
```

Open `http://127.0.0.1:8080/` and confirm the banner, ticker, `operator.html`, and `app.html` iframe load.

## Related

- Root **`README.md`** — GitHub Pages deployment summary.
- **`service/README.md`** — service module responsibilities and ports.
- **`docs/PROJECT-REVIEW.md`** — product/engineering gap review.
