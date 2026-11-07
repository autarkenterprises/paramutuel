# Paramutuel bet scout agent (`agents/paramutuel_bettor`)

Paramutuel treats **agents** (human or artificial) as first-class participants: the same permissionless markets and on-chain rules apply, with no separate “bot API” gate. This agent is a small, **stdlib-only** helper for **adoption-oriented workflows**: discover open wagers from the indexer, score outcomes with the same parimutuel math as the MCP server, and emit a **JSON plan** a parent model (or wallet UI) can review before signing.

This complements the MCP server (`mcp_server/`): MCP remains the canonical **tooling surface** for calldata and rich protocol coverage; the bet agent focuses on a **tight loop** suitable for subagents and scripted delegation.

## Design principles

- **No private keys** in the agent process; it never broadcasts transactions.
- **Indexer-first** reads (`GET /wagers`, `GET /wagers/{addr}`), same as MCP discovery.
- **Built-in calldata**: the agent encodes `placeBet` and `approve` itself, with no Foundry dependency. Freeform answers are byte-exact.
- **Strategies are intentionally naive** (`best_post_multiple`, `min_liquidity`); they are hooks for human or model judgment, not financial advice.

## CLI

Once published to PyPI (**not yet**; console script `paramutuel-bettor`; until then use the repo-root commands below):

```bash
pip install paramutuel-bettor-agent
paramutuel-bettor health
paramutuel-bettor scan --state OPEN --limit 20
paramutuel-bettor recommend --bet-amount-raw 1000000 --scan-limit 30 --top 5
paramutuel-bettor quote --wager 0x... --outcome-index 0 --bet-amount-raw 1000000
# ADR-0009 freeform: optional exact answer string for placeBet calldata
paramutuel-bettor quote --wager 0x... --outcome-index 0 --bet-amount-raw 1000000 --freeform-answer "Paris"
```

From repo root:

```bash
PYTHONPATH=. python3 -m agents.paramutuel_bettor health
PYTHONPATH=. python3 -m agents.paramutuel_bettor scan --state OPEN --limit 20
PYTHONPATH=. python3 -m agents.paramutuel_bettor recommend --bet-amount-raw 1000000 --scan-limit 30 --top 5
PYTHONPATH=. python3 -m agents.paramutuel_bettor quote --wager 0x... --outcome-index 0 --bet-amount-raw 1000000
# Freeform: add --freeform-answer "..." when you know the exact UTF-8 string
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
| `recommend` | `bet_amount_raw`, `strategy?`, `scan_limit?`, `min_total_pot_raw?`, `proposition_contains?`, `top?` | Ranked suggestions. Freeform ideas carry calldata when the answer text is known |
| `quote` | `wager_address`, `outcome_index`, `bet_amount_raw`, `freeform_answer?` | Quote, with `odds_model_exact` (false means the multiple is not a payout estimate for this policy). **Freeform** uses `outcome_index` as index into sorted `ticket_pools`; pass `freeform_answer` for `placeBet` calldata, sent byte-exact |

Example:

```bash
echo '{"op":"recommend","bet_amount_raw":1000000,"scan_limit":15,"top":3}' \
  | PYTHONPATH=. python3 -m agents.paramutuel_bettor json
```

## Parent-agent workflow (recommended)

1. Run `recommend` or `scan` to shortlist `OPEN` wagers.
2. For each candidate, inspect `proposition`, fees, and `betting_open`.
3. Re-quote with agent `quote` or MCP `quote_place_bet` to get final calldata immediately before signing, since state changes between quote and execution.
4. Executor wallet signs `approve` then `placeBet` (see [`AGENT-LOOP.md`](AGENT-LOOP.md)).

## Claude Code / Cursor

Project skill: `.cursor/skills/paramutuel-bettor/SKILL.md` — instructs when to delegate to this agent and how to combine it with MCP.

## Distribution and discoverability

**Humans and orgs**

- Share **[`MACHINE.md`](MACHINE.md)** as the single entry page for “how to automate Paramutuel.”
- The MCP package **`paramutuel-mcp`** is the intended install path for Claude Desktop / IDE MCP configs, and the bet scout is **`paramutuel-bettor-agent`** (CLI **`paramutuel-bettor`**). **Neither is on PyPI yet**, so for now both run **in-repo** (clone + `PYTHONPATH=.`).
- Full channel list, CI/CD, and fleet rollout: **[`BET-AGENT-DISTRIBUTION.md`](BET-AGENT-DISTRIBUTION.md)**.

**Autonomous agents and registries**

- **[`agents/subagent-manifest.json`](../agents/subagent-manifest.json)** is a small, versioned JSON document listing:
  - stable **`id`** (`io.github.autarkenterprises.paramutuel.bettor`),
  - **invocation** hint (`python3 -m agents.paramutuel_bettor json`),
  - supported **`operations`** (`op` values and fields),
  - **complements** (link to MCP / `quote_place_bet`).
- Hosts, catalogs, or parent agents can **fetch the raw manifest** (no clone) to advertise or spawn the subagent:
  - `https://raw.githubusercontent.com/autarkenterprises/paramutuel/master/agents/subagent-manifest.json`
- Add GitHub **repository topics** (e.g. `mcp`, `agents`, `subagent`, `parimutuel`, `base`) so discovery search surfaces the project.

**Forks**

- Update `repository` / `human_docs` URLs in the manifest if you publish a long-lived fork, or keep pointing to upstream for “official” semantics.

## Tests

```bash
PYTHONPATH=. python3 -m unittest discover -s agents/paramutuel_bettor/tests -p "test_*.py" -q
```
