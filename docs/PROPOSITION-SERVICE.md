# Proposition Service

The Proposition Service ingests headlines and market listings from configurable RSS, Hacker News, and JSON-array HTTP sources, turns each **new** item into a **pending** Yes/No draft wager in SQLite, and exposes an **operator-only** HTTP API plus a small static control panel to review, edit, approve, and optionally **dispatch** wagers to the Paramutuel factory via `cast send`.

## Layout

| Path | Role |
|------|------|
| `service/proposition/ingest.py` | Load `config/proposition-sources.json`, fetch sources, insert rows |
| `service/proposition/rss.py` | RSS/Atom parsing (stdlib `xml.etree`, `urllib`) |
| `service/proposition/json_sources.py` | HN + generic JSON list fetch |
| `service/proposition/synthesize.py` | Headline → proposition template + optional calendar drafts |
| `service/proposition/db.py` | SQLite persistence |
| `service/proposition/dispatch.py` | `build_create_wager_command` + `subprocess` |
| `service/proposition/server.py` | `ThreadingHTTPServer` + routes |
| `service/proposition/static/` | Operator UI (`index.html`, `app.js`, `style.css`) |

## Run locally

From the repo root (token is **required**):

```bash
export PROPOSITION_PANEL_TOKEN='your-long-random-secret'
PYTHONPATH=. python3 -m service.proposition.server --port 8094
```

Open `http://127.0.0.1:8094`, paste the same token, click **Save token (local)**, then **Run ingest** or use the API.

### Environment variables

| Variable | Purpose |
|----------|---------|
| `PROPOSITION_PANEL_TOKEN` | Bearer / `X-Proposition-Token` for all `/api/*` routes except `GET /health` |
| `PROPOSITION_SOURCES_PATH` | Override path to sources JSON (default `config/proposition-sources.json`) |
| `PROPOSITION_DB_PATH` | SQLite file (default `service/proposition/data/propositions.db`) |
| `FACTORY_ADDRESS` / `PROPOSITION_FACTORY` | Factory contract (else `config/deployments.json` + `defaultNetwork`) |
| `PROPOSITION_COLLATERAL_TOKEN` | Collateral `address` for `createWager` |
| `RPC_URL_BASE_SEPOLIA` / `RPC_URL` | RPC for `cast send` |
| `PRIVATE_KEY` / `PROPOSITION_PRIVATE_KEY` | Hot key for dispatch |
| `PROPOSITION_ALLOW_EXECUTE` | `1` / `true` to allow `POST .../dispatch`; override with `--allow-execute` or `--no-allow-execute` |
| `PROPOSITION_BETTING_CLOSE_OFFSET_SEC` | Seconds from “now” to betting close at dispatch (default 7 days) |
| `PROPOSITION_RESOLUTION_WINDOW_SEC` | Resolution window passed to factory (default 3 days) |
| `PROPOSITION_RESOLVER`, `PROPOSITION_BETTING_CLOSER`, `PROPOSITION_RESOLUTION_CLOSER` | Role addresses (optional; `0x0` if omitted) |
| `PROPOSITION_EXTRA_FEE_RECIPIENTS`, `PROPOSITION_EXTRA_FEE_BPS` | Comma-aligned lists for extra fee slots |

**Dispatch** shells out to `cast` (Foundry). The process running the server must have `cast` on `PATH` and a working RPC/key when execute is enabled.

## Sources configuration

`config/proposition-sources.json` is a list of objects (or `{ "sources": [ ... ] }`).

- **`type`**: `rss` (feed URL), `hackernews` (optional `limit`), `json_array` (remote JSON array or envelopes containing `data`, `markets`, `results`, `items`).
- **`id`**: Stable id for deduplication (`source_items.source_id` + `external_id`).
- **`category`**, **`label`**, **`enabled`**, **`default_cadence`**: Passed through to synthesis and stored on proposals.

`POST /api/ingest` accepts `?calendar=1` to append neutral **daily/weekly** calendar drafts. Identical calendar proposition text is **skipped** if it already exists (response includes `calendar_skipped_duplicates`).

## API (all authenticated except `/health`)

- `GET /health` — liveness.
- `GET /api/config` — non-secret deployment hints (factory set, RPC/key presence, execute flag).
- `GET /api/sources` — parsed sources config.
- `GET /api/proposals?status=pending&limit=100`
- `PATCH /api/proposals/{id}` — body `{ "proposition", "outcomes": ["Yes","No",...] }` (**pending** only).
- `POST /api/ingest?calendar=0|1`
- `POST /api/proposals/{id}/approve|reject|dispatch` — dispatch requires approved row + execute enabled + env.

## Docker

`Dockerfile.proposition` runs the HTTP server only (Python slim, no Foundry). For on-chain dispatch inside a container, extend the image to install Foundry or run dispatch from a host that has `cast`.

```bash
docker build -f Dockerfile.proposition -t paramutuel-proposition .
docker run --rm -e PROPOSITION_PANEL_TOKEN=... -p 8094:8094 paramutuel-proposition
```

## Operator workflow

1. Schedule `POST /api/ingest` (cron) or use the panel button.
2. Review **pending** proposals; follow **source** links; edit wording/outcomes if needed.
3. **Approve** acceptable drafts; **Reject** the rest.
4. When ready, **Dispatch** approved rows (with execute enabled) to create on-chain wagers.

Auto-generated text is intentionally conservative: the operator is responsible for rubric, resolver policy, and legal suitability before approval.
