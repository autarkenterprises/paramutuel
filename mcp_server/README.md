# paramutuel-mcp

MCP server for the [Paramutuel](https://github.com/autarkenterprises/paramutuel) on-chain parimutuel betting protocol on Base.

Exposes 16 tools that let LLM agents discover wagers, analyze odds, and prepare transactions — no private keys required on the server side.

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
INDEXER_URL=https://paramutuel-indexer.onrender.com \
FACTORY_ADDRESS=0x8FBB3ab4BBCAEA196f7847e6c2fe575Eadc18B36 \
CHAIN_ID=84532 \
paramutuel-mcp
```

## Tools

### Discovery

| Tool | Description |
|------|-------------|
| `get_protocol_info` | Factory address, chain ID, indexer URL, ABI summaries, protocol constants |
| `list_markets` | List wagers from the indexer, filterable by state (OPEN/RESOLVED/RETRACTED) |
| `get_market` | Full wager details: outcomes, totals, event history |
| `get_expire_candidates` | Wagers past their resolution deadline, callable by anyone via `expire()` |

### Analysis

| Tool | Description |
|------|-------------|
| `calculate_odds` | Compute pre/post-bet payout multiples and expected returns for a hypothetical bet |

### Transaction encoding

All write tools return ABI-encoded calldata. The caller signs and submits the transaction.

| Tool | Description |
|------|-------------|
| `encode_create_market` | Create a new wager (with optional seed liquidity) |
| `encode_place_bet` | Bet on a single outcome |
| `encode_place_bets` | Batch bet across multiple outcomes in one tx |
| `encode_resolve` | Resolve a wager to a winning outcome (resolver only) |
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
| `FACTORY_ADDRESS` | From `config/deployments.json` | Factory contract address |
| `CHAIN_ID` | From `config/deployments.json` or `84532` | Target chain ID |

When installed as a pip package, the server bundles its own ABI files and works standalone. When run from the repo, it also checks `dapp/abi/` and `out/` for ABIs.

## Protocol

Paramutuel is a permissionless, immutable parimutuel betting protocol on Base (Ethereum L2).

- **Anyone** can create a wager with 2-64 outcomes using any ERC-20 as collateral
- **Bettors** deposit into outcome pools; winners split the net pot pro-rata
- **Resolution** is modular: creator-resolved (MVP), upgradeable to oracle/DAO
- **Fees** are configurable per wager (protocol fee + optional creator fee, capped at 10%)

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
