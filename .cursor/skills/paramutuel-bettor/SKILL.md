---
name: paramutuel-bettor
description: >-
  Delegate Paramutuel parimutuel betting discovery and planning to the repo's
  stdlib bet scout agent (agents.paramutuel_bettor); combine with MCP for
  calldata and signing. Use when the user wants an LLM subagent or automation
  to find open wagers, score outcomes, or produce JSON bet plans without
  holding private keys.
---

# Paramutuel bet scout (subagent skill)

## When to use

- User wants an **agent** (or you as a subagent) to **find open wagers** and **propose** where to bet.
- User wants a **small, auditable** process that **does not touch private keys**.
- User already uses or can use the **Paramutuel MCP** server for `quote_place_bet`, `encode_place_bet_freeform`, and related encoders.

## What to run

From the **repo root**, prefer the JSON bridge so a parent model can parse stdout only:

```bash
echo '{"op":"recommend","bet_amount_raw":1000000,"scan_limit":25,"top":5}' \
  | PYTHONPATH=. python3 -m agents.paramutuel_bettor json
```

Other `op` values: `health`, `scan`, `quote` (see `docs/BET-AGENT.md`).

Set `INDEXER_URL` if the indexer is not the default from `config/deployments.json`.

## How to combine with MCP (production-shaped loop)

1. Use this agent for **shortlisting + rationale** (strategies are naive; treat as hints).
2. For each chosen wager, call MCP **`quote_place_bet`** (v1/v2) or **`encode_place_bet_freeform`** (freeform / ADR-0009) immediately before execution so calldata matches chain state.
3. Pass `approve` + `placeBet` to the user's wallet / signer. Never ask for or embed private keys in prompts.

## Safety and disclosure

- Output must state that strategies are **not** investment advice and that **on-chain state changes** between quote and execution.
- If `betting_open` is false or `revert_hint` is non-empty, **do not** present the plan as executable without re-quote.

## Strategies (agent-native)

- `best_post_multiple` — maximize implied **post-bet** payout multiple for a fixed hypothetical size (naive).
- `min_liquidity` / `contrarian` — bet the **smallest** outcome pool (high variance; use with care).

If the user names a custom policy, map it explicitly to one of these or ask for clarification.
