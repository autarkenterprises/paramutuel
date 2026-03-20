## Minimal Custom Indexer (v1)

This is a dependency-light Python indexer for Paramutuel, intended to satisfy early roadmap requirements:

- deterministic event ingestion
- idempotent event log storage
- market state queries
- unresolved overdue market scanning for expiry sweeper jobs

### Files

- `indexer.py`: log sync engine (`eth_getLogs`), SQLite writes
- `api.py`: simple HTTP API over indexed state
- `schema.sql`: SQLite schema
- `tests/`: unit tests for core state transitions and derived queries

### Run

```bash
# 1) Index logs
python3 service/indexer/indexer.py \
  --rpc-url "$RPC_URL" \
  --factory-address "0xFactoryAddress" \
  --db-path service/indexer/indexer.db

# 2) Start API
python3 service/indexer/api.py \
  --db-path service/indexer/indexer.db \
  --host 127.0.0.1 \
  --port 8090
```

### API endpoints

- `GET /health`
- `GET /markets?state=OPEN|RESOLVED|RETRACTED&limit=100`
- `GET /markets/<market_address>`
- `GET /sweeper/expire-candidates`

### Notes

- Current v1 keeps `total_fee_bps` at default `0` in indexed totals until extended with on-chain reads.
- Indexer is designed to be extended with richer market metadata once resolver/service layers are integrated.

