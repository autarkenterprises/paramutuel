# Project review (snapshot)

Concise assessment of the repository as a **modular** system: protocol contracts, static end-user surfaces, service layer, and automation agents. Use this for investor or partner conversations and internal prioritization.

## Strengths

- **Clear separation of concerns:** contracts in `src/`; self-custody **dApp** in `dapp/`; **marketing + navigation shell** in `site/` (iframe embedding preserves boundaries); **indexer / explorer / control / proposition / resolution** as distinct Python services (`service/`).
- **Testnet-first with a documented mainnet switch:** `config/deployments.json` + `defaultNetwork`; site banner and docs describe the same lever (`docs/WEBSITE.md`).
- **Operator-facing surfaces:** CLI and token-gated web for sensitive actions; new **operator hub** page aggregates read-only and configurable links without entangling public Pages with private keys.
- **Agent story:** MCP server, bet scout package (`paramutuel-bettor-agent`), manifest JSON, and documented loops (`AGENTS.md`, `docs/AGENT-LOOP.md`).
- **CI:** contract build, site assembly, bettor-agent tests/publish workflows; path-filtered deploys.

## Gaps vs “production ready” for retail + investors

| Area | Gap | Suggested direction |
|------|-----|---------------------|
| **Mainnet** | Factory and indexer URLs empty for `baseMainnet` | Deploy audited contracts + hosted indexer; flip `defaultNetwork`; announce cutover |
| **Legal / compliance** | No terms, privacy, or jurisdiction copy on the public site | Add lightweight footer links and “testnet / not an offer” framing where appropriate |
| **Wallet breadth** | EIP-1193 only; no WalletConnect in static build | Optional connector module or hosted wallet modal for mobile |
| **Assisted UX** | Self-custody only on Pages | Track in `docs/TASKS.md` (assisted gateway); keep dApp as advanced escape hatch per ADR-0006/0007 |
| **Observability** | Services depend on operator-run logging | Dashboards for indexer lag, RPC errors, resolution job outcomes |
| **PyPI publish** | Tag push works; PyPI **Trusted Publishing** must be completed in the PyPI UI | See `docs/TASKS.md` — release engineering checklist; verify Actions after first tag |

## Polish (non-blocking)

- Favicon and social preview image for `og:image`.
- Consistent “Paramutuel” typography / brand lockup on landing.
- Lighthouse pass: accessibility labels on ticker items, contrast on muted text.
- End-to-end test (Playwright) against static ` _site` or Pages URL for connect + read-only paths.

## Organizational “single pane” for operators

The **operator hub** (`site/operator.html`) is the first consolidated **read-mostly** UI on the public site. Full **management** of proposition, resolution, and control-panel execution remains in **secured deployments** (private URLs, bearer tokens, `--allow-execute` flags). A future step could be a **private** dashboard repo or VPN-only deployment that iframes the same modules with SSO — out of scope for the public Pages bundle.

## References

- `docs/WEBSITE.md` — site architecture and testnet/mainnet switch.
- `docs/TASKS.md` — backlog and assisted-UX track.
- `research/execution-roadmap.md` — program-level sequencing.
- `service/README.md` — service org chart (components and ports).
