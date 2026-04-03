# Agent and subagent integration

This repository is built for **bots, indexers, and LLM-driven workflows**. If you are an autonomous agent (or an engineer wiring one), start here.

## Canonical surfaces

| Surface | Purpose | Where |
|--------|---------|--------|
| **MCP server** | Full protocol tools: discovery, odds, ABI calldata (`quote_place_bet`, encoders). | `mcp_server/`, PyPI package **`paramutuel-mcp`**, [`docs/MACHINE.md`](docs/MACHINE.md) |
| **Bet scout subagent** | Small **stdlib** process: scan / recommend / quote with **JSON stdin → JSON stdout** for delegation. No private keys. | `agents/paramutuel_bettor/`, [`docs/BET-AGENT.md`](docs/BET-AGENT.md) |
| **Machine manifest** | Stable JSON listing subagent id, ops, and complementing MCP. For registries and automated discovery. | [`agents/subagent-manifest.json`](agents/subagent-manifest.json) |

## Recommended execution loop (betting)

1. Use the **bet scout** to shortlist `OPEN` wagers and rank outcomes (hypothetical size in **raw token units**).
2. Obtain **final** calldata with MCP **`quote_place_bet`** immediately before signing (chain state can change).
3. A separate **wallet / signer** submits `approve` and `placeBet`. Do not embed private keys in the scout or MCP server.

Details: [`docs/AGENT-LOOP.md`](docs/AGENT-LOOP.md).

## Running the bet scout (from a clone)

```bash
git clone https://github.com/autarkenterprises/paramutuel.git
cd paramutuel
export PYTHONPATH=.
python3 -m agents.paramutuel_bettor health
echo '{"op":"recommend","bet_amount_raw":1000000,"top":3}' | python3 -m agents.paramutuel_bettor json
```

`INDEXER_URL` overrides the default from `config/deployments.json` (see [`docs/BET-AGENT.md`](docs/BET-AGENT.md)).

## Claude Code / Cursor

Project skill (copy or symlink into your skill path if you fork): [`.cursor/skills/paramutuel-bettor/SKILL.md`](.cursor/skills/paramutuel-bettor/SKILL.md).

## Distributing awareness (for humans)

- Point integrators at **this file** and **`agents/subagent-manifest.json`**.
- GitHub **Topics** (on the repo): e.g. `mcp`, `parimutuel`, `prediction-markets`, `base`, `llm`, `agents`, `subagent`.
- Link from your site or docs to **`AGENTS.md`** and the **raw manifest URL** so crawlers and agent frameworks can ingest metadata without cloning.

Raw manifest (stable path on default branch):

`https://raw.githubusercontent.com/autarkenterprises/paramutuel/master/agents/subagent-manifest.json`

## Security

Strategies in the bet scout are **not** financial advice. All on-chain actions require explicit signer approval; treat every quote as stale after state changes.
