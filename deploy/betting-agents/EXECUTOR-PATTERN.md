# Executor pattern (on-chain activity / seeding)

The **bet scout** (`paramutuel-bettor`) is intentionally **read-only**: it never holds private keys and never broadcasts.

To **seed the network with real bets**, run a **separate executor tier** that:

1. Consumes **approved** bet intents (JSON from your queue, DB, or human-in-the-loop UI).
2. For each intent, calls **MCP `quote_place_bet`** (or `cast`) **immediately** before signing — state changes fast on-chain.
3. Submits `ERC20.approve` + `placeBet` / `placeBets` using **one distinct wallet per bot** (or per shard) with rate limits and monitoring.

## Wallet hygiene

- **Never** commit keys; use a secret manager (K8s Secret, GCP Secret Manager, Vault).
- Prefer **dedicated low-value EOAs** on testnet; on mainnet use explicit risk caps.
- Rotate keys if logs leak; isolate blast radius per bot identity.

## Scaling many independent “agents”

| Layer | Role | Scale |
|-------|------|--------|
| **Scout** | Cheap polling + JSON plans | Many replicas (Docker Compose `--scale`, K8s `replicas`, Cloud Run jobs) |
| **Policy / approval** | Filter spam, enforce budgets | Central service or human queue |
| **Executor** | Signs txs | Fewer, rate-limited, funded wallets |

## Suggested intake shape (executor input)

```json
{
  "wager_address": "0x…",
  "outcome_index": 0,
  "amount_raw": 1000000,
  "max_fee_gwei": 1,
  "idempotency_key": "uuid"
}
```

The executor should reject duplicates using `idempotency_key` and track nonces per wallet.

## Compliance

Automated betting may be regulated in your jurisdiction. Run testnet experiments first; obtain legal review before mainnet automation.
