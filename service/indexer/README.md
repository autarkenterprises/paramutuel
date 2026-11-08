## Minimal Custom Indexer (v1)

This is a dependency-light Python indexer for Paramutuel, intended to satisfy early roadmap requirements:

- deterministic event ingestion
- idempotent event log storage
- wager state queries
- unresolved overdue wager scanning for expiry sweeper jobs

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
- `GET /wagers?state=OPEN|RESOLVED|RETRACTED&limit=100&offset=0&order=asc|desc&q=<text>&resolver=<address>`
- `GET /wagers/<wager_address>?pool_limit=500&events_limit=1000&answer_id=<freeform answer id>`
- `GET /sweeper/expire-candidates`

Every field and parameter is documented in [`docs/MACHINE.md`](../../docs/MACHINE.md).

### Notes

- Fees (`total_fee_bps`), the proposition and outcome labels are read from the wager by `eth_call` at creation. A failed read leaves the row incomplete, and it is retried with backoff (15 seconds doubling to an hour) until it succeeds.
- `total_winning_stake` is tokens on winning tickets; `payout_denominator` is the contract's divisor for payouts. They differ only under `WEIGHTED_OVERLAP`.

