# Service Layer

Service layer components:

- `indexer/` — deterministic chain event indexer + JSON API.
- `explorer/` — web explorer for market status, backed by indexer API.
- `control_panel/` — operator controls (CLI + web) for full market lifecycle roles.

## Explorer

```bash
python3 -m service.explorer.server --indexer-base-url http://127.0.0.1:8090 --port 8091
```

Open `http://127.0.0.1:8091`.

### Can this be modularly appended to the dApp?

Yes. It is already modular:

- can run as standalone (`service/explorer/server.py`)
- can be linked from dApp navigation
- can be embedded into dApp shell as an iframe or copied as a route view

## Control panel (CLI)

Print (dry-run) command:

```bash
python3 -m service.control_panel.cli \
  --rpc-url "$RPC_URL" \
  --private-key "$PRIVATE_KEY" \
  market-action \
  --market "$MARKET" \
  --action close-betting
```

Execute for real:

```bash
python3 -m service.control_panel.cli \
  --rpc-url "$RPC_URL" \
  --private-key "$PRIVATE_KEY" \
  --execute \
  market-action \
  --market "$MARKET" \
  --action close-betting
```

`create-market` is also supported in CLI with full role and fee fields.

## Control panel (web)

```bash
python3 -m service.control_panel.web \
  --rpc-url "$RPC_URL" \
  --private-key "$PRIVATE_KEY" \
  --allow-execute \
  --auth-token "$CONTROL_PANEL_TOKEN" \
  --port 8092
```

Open `http://127.0.0.1:8092`.

By default, web API returns command previews.

- Add `--allow-execute` to allow direct execution.
- Execution requests require auth token (`Authorization: Bearer ...` or `X-Control-Token`) matching `--auth-token`.

## Expiry sweeper daemon + scheduler

Run one dry-run sweep:

```bash
python3 -m service.indexer.sweeper \
  --db-path service/indexer/indexer.db \
  --rpc-url "$RPC_URL" \
  --private-key "$PRIVATE_KEY"
```

Run continuously every 60s and execute transactions:

```bash
python3 -m service.indexer.sweeper \
  --db-path service/indexer/indexer.db \
  --rpc-url "$RPC_URL" \
  --private-key "$PRIVATE_KEY" \
  --execute \
  --loop \
  --interval-seconds 60
```

## Launch shortcut

Use the full launch helper from repo root:

```bash
chmod +x script/testnet/launch_testnet.sh
RPC_URL_BASE_SEPOLIA=... PRIVATE_KEY=... TREASURY_ADDRESS=... ./script/testnet/launch_testnet.sh
```

## Tests

Run service-layer tests independently:

```bash
PYTHONPATH=. python3 -m unittest discover -s service/indexer/tests -p "test_*.py" -q
PYTHONPATH=. python3 -m unittest discover -s service/explorer/tests -p "test_*.py" -q
PYTHONPATH=. python3 -m unittest discover -s service/control_panel/tests -p "test_*.py" -q
PYTHONPATH=. python3 -m unittest discover -s service/indexer/tests -p "test_sweeper.py" -q
```
