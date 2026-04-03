# Paramutuel bet scout agent (`agents/paramutuel_bettor`)

Small, **stdlib-only** helper for **adoption-oriented agent workflows**: discover open wagers from the indexer, score outcomes with the same parimutuel math as the MCP server, and emit a **JSON plan** a parent model (or wallet UI) can review before signing.

This complements the MCP server (`mcp_server/`): MCP remains the canonical **tooling surface** for calldata and rich protocol coverage; the bet agent focuses on a **tight loop** suitable for subagents and scripted delegation.

## Design principles

- **No private keys** in the agent process; it never broadcasts transactions.
- **Indexer-first** reads (`GET /wagers`, `GET /wagers/{addr}`), same as MCP discovery.
- **Optional calldata**: if `cast` is on `PATH`, the agent fills `placeBet` / `approve` calldata via `cast calldata`. Otherwise it returns a note to use MCP `quote_place_bet`.
- **Strategies are intentionally naive** (`best_post_multiple`, `min_liquidity`); they are hooks for human or model judgment, not financial advice.

## CLI

From repo root:

```bash
PYTHONPATH=. python3 -m agents.paramutuel_bettor health
PYTHONPATH=. python3 -m agents.paramutuel_bettor scan --state OPEN --limit 20
PYTHONPATH=. python3 -m agents.paramutuel_bettor recommend --bet-amount-raw 1000000 --scan-limit 30 --top 5
PYTHONPATH=. python3 -m agents.paramutuel_bettor quote --wager 0x... --outcome-index 0 --bet-amount-raw 1000000
```

Environment:

- `INDEXER_URL` — overrides default from `config/deployments.json` (`explorerApiBase`) or `http://127.0.0.1:8090`.

## JSON / subagent bridge

The `json` subcommand reads **one JSON object** from stdin and prints a JSON result. Intended for frontier models spawning a subprocess or thin wrapper.

Operations:

| `op` | Fields | Description |
|------|--------|-------------|
| `health` | — | Indexer `/health` |
| `scan` | `state?`, `limit?`, `order?`, `q?` | Wager list summaries |
| `recommend` | `bet_amount_raw`, `strategy?`, `scan_limit?`, `min_total_pot_raw?`, `proposition_contains?`, `top?` | Ranked suggestions |
| `quote` | `wager_address`, `outcome_index`, `bet_amount_raw` | Fixed-outcome quote |

Example:

```bash
echo '{"op":"recommend","bet_amount_raw":1000000,"scan_limit":15,"top":3}' \
  | PYTHONPATH=. python3 -m agents.paramutuel_bettor json
```

## Parent-agent workflow (recommended)

1. Run `recommend` or `scan` to shortlist `OPEN` wagers.
2. For each candidate, inspect `proposition`, fees, and `betting_open`.
3. Use MCP `quote_place_bet` (or agent `quote` + `cast`) to obtain final calldata immediately before signing.
4. Executor wallet signs `approve` then `placeBet` (see [`AGENT-LOOP.md`](AGENT-LOOP.md)).

## Claude Code / Cursor

Project skill: `.cursor/skills/paramutuel-bettor/SKILL.md` — instructs when to delegate to this agent and how to combine it with MCP.

## Tests

```bash
PYTHONPATH=. python3 -m unittest discover -s agents/paramutuel_bettor/tests -p "test_*.py" -q
```
