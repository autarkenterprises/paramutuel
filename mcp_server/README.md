# paramutuel-mcp

MCP server for the [Paramutuel](https://github.com/autarkenterprises/paramutuel) on-chain parimutuel betting protocol on Base.

Exposes 20+ tools that let LLM agents discover wagers, analyze odds, and prepare transactions — no private keys required on the server side.

**Adoption complement:** the repo ships a **bet scout subagent** (`agents/paramutuel_bettor`, JSON stdin/stdout) with a **machine manifest** at `agents/subagent-manifest.json` and human index [`AGENTS.md`](../AGENTS.md). See [`docs/BET-AGENT.md`](../docs/BET-AGENT.md); use MCP for final `quote_place_bet` (v1/v2) or `encode_place_bet_freeform` (ADR-0009) / calldata right before signing.

## Quick start

```bash
pip install paramutuel-mcp
paramutuel-mcp
```

Or run from the repo:

```bash
pip install -e mcp_server/
python -m mcp_server
```

### Claude Desktop / Claude Code

Add to your MCP client config:

```json
{
  "mcpServers": {
    "paramutuel": {
      "command": "paramutuel-mcp"
    }
  }
}
```

### With environment overrides

```bash
INDEXER_URL=https://paramutuel-git-406244230167.europe-west1.run.app \
FACTORY_ADDRESS=0x655f6c5a3dc4cb3bf68173952bca9dac1bb5bf39 \
CHAIN_ID=84532 \
paramutuel-mcp
```

## Tools

### Discovery

| Tool | Description |
|------|-------------|
| `get_protocol_info` | Factory address, chain ID, indexer URL, ABI summaries, protocol constants |
| `list_wagers` | List wagers from the indexer, filterable by state (OPEN/RESOLVED/RETRACTED) |
| `get_wager` | Full wager details: outcomes, ticket pools (v2 bitmask or freeform answer ids), totals, event history |
| `get_expire_candidates` | Wagers past their resolution deadline, callable by anyone via `expire()` |
| `get_indexer_health` | Indexer liveness/sync indicators (`/health`) |

### Analysis

| Tool | Description |
|------|-------------|
| `calculate_odds` | Compute pre/post-bet payout multiples and expected returns for a hypothetical bet |
| `quote_place_bet` | Fetch wager, compute odds, and return `placeBet` calldata + approval details (v2 maps outcome index → `1<<index` for single-bit tickets) |
| `quote_place_bets` | Fetch wager, compute batch odds, and return `placeBets` calldata + approval details (v2 uses ticket masks per leg) |

### Transaction encoding

All write tools return ABI-encoded calldata. The caller signs and submits the transaction.

| Tool | Description |
|------|-------------|
| `encode_create_wager` | Create a new **v1** wager (with optional seed liquidity) |
| `encode_create_wager_v2` | Create a new **v2** wager via `ParamutuelFactoryV2` (policy + optional seed ticket masks) |
| `encode_create_freeform_wager` | Create a new **freeform** wager (ADR-0009) via `ParamutuelFactoryFreeform` (no outcome list) |
| `encode_place_bet` | Bet on a single outcome |
| `encode_place_bet_freeform` | `placeBet(string,uint256)` on a freeform wager (exact UTF-8 answer bytes) |
| `encode_place_bets` | Batch bet across multiple outcomes in one tx |
| `encode_resolve` | Resolve a wager to a winning outcome (resolver only) |
| `encode_resolve_freeform` | `resolve(string)` on a freeform wager (exact winning answer string) |
| `encode_retract` | Invalidate a wager, enabling refunds (resolver only) |
| `encode_expire` | Expire an overdue wager (anyone can call) |
| `encode_close_betting` | Close the betting window early (betting closer only) |
| `encode_close_resolution_window` | Close the resolution window early (resolution closer only) |
| `encode_claim` | Claim payout (winners) or refund (retracted/expired) |
| `encode_withdraw_fees` | Withdraw accrued fee balance |

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `INDEXER_URL` | From `config/deployments.json` or `http://127.0.0.1:8090` | Indexer API base URL |
| `FACTORY_ADDRESS` | From `config/deployments.json` | v1 factory contract address |
| `FACTORY_V2_ADDRESS` | From `config/deployments.json` `factoryV2Address` | v2 factory (empty disables `encode_create_wager_v2` targeting) |
| `FACTORY_FREEFORM_ADDRESS` | From `config/deployments.json` `factoryFreeformAddress` | freeform factory (empty disables `encode_create_freeform_wager` targeting) |
| `CHAIN_ID` | From `config/deployments.json` or `84532` | Target chain ID |

When installed as a pip package, the server bundles its own ABI files and works standalone. When run from the repo, it also checks `dapp/abi/` and `out/` for ABIs.

## Protocol

Paramutuel is a permissionless, immutable parimutuel betting protocol on Base (Ethereum L2).

- **Anyone** can create a **v1** wager with 2–255 outcomes, a **v2** bitmask/policy wager, or a **freeform** (ADR-0009) text-answer wager using any ERC-20 as collateral
- **Bettors** deposit into outcome pools; winners split the net pot pro-rata
- **Resolution** is modular: creator-resolved (MVP), upgradeable to oracle/DAO
- **Fees** are configurable per wager (protocol fee + optional creator fee, capped at 100% for full-beneficiary/charity flows)

Live dApp: https://autarkenterprises.github.io/paramutuel/

## Development

```bash
# Run tests
python -m unittest mcp_server/tests/test_server.py

# Run server in dev mode
python -m mcp_server
```

## License

MIT
