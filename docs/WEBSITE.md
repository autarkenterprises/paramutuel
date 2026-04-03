# Protocol website (GitHub Pages)

The static site under `site/` is a **thin shell**: marketing copy, a testnet/mainnet **deployment banner**, and **iframes** that embed the self-custody dApp (`dapp/`) and the indexer-backed explorer (`service/explorer/static/`) without merging their codebases.

## Pages

| Path | Role |
|------|------|
| `/` | Landing, live ticker, onboarding |
| `/app.html` | Full dApp embedded via iframe |
| `/bet.html` | Short “place a bet” flow (standalone JS + ethers) |
| `/explorer.html` | Explorer UI with optional indexer URL override |
| `/operator.html` | **Operator hub** — indexer links, embedded explorer, outbound URLs for other services |
| `/dapp/` | Same dApp as embedded, for direct links and debugging |

Runtime configuration is read from `config/deployments.json` (copied to `_site/config/` in CI). Optional **`config/operator-hub.json`** supplies public base URLs for hosted operator panels (control, proposition, resolution) when you deploy them outside GitHub Pages.

## Switching testnet → mainnet

One switch for the **public site build**:

1. Edit **`config/deployments.json`**.
2. Set **`defaultNetwork`** to `"baseMainnet"`.
3. Fill **`baseMainnet.factoryAddress`** and **`baseMainnet.explorerApiBase`** (and `chainId` / `indexerFromBlock` as needed for your indexer deployment).
4. Commit and push; the **Deploy to GitHub Pages** workflow rebuilds the site.

The **banner** (`site/network-banner.js`) reflects the active entry:

- **Testnet** styling for Base Sepolia (`chainId` 84532).
- **Mainnet** styling for Base (`chainId` 8453) when factory and indexer URL are set.
- **Warning** styling if `defaultNetwork` is mainnet but factory or indexer base URL is missing.

The dApp (`dapp/app.js`) already picks the factory address from the same file keyed by the **wallet’s** chain when possible; keeping `defaultNetwork` aligned with your intended rollout avoids confusing defaults on the marketing site and bet page.

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
