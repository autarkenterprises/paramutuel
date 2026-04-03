# Betting agent fleet (scouts + executors)

## Scout (this folder)

- **`Dockerfile`** — installs `paramutuel-bettor-agent` from repo `pyproject.toml`.
- **`entrypoint-scout-loop.sh`** — prints periodic `recommend` JSON (stdout / container logs).
- **`docker-compose.fleet.yml`** — scale scouts:  
  `docker compose -f deploy/betting-agents/docker-compose.fleet.yml up --scale bettor-scout=25`
- **`k8s-scout-deployment.example.yaml`** — Kubernetes `Deployment` with `replicas`.

Set **`INDEXER_URL`** in production.

## Executor (on-chain)

See [`EXECUTOR-PATTERN.md`](EXECUTOR-PATTERN.md). Scouts do **not** place bets.

## Distribution

PyPI package **`paramutuel-bettor-agent`**, container **`ghcr.io/<owner>/paramutuel-bettor-agent`**. Full matrix: [`docs/BET-AGENT-DISTRIBUTION.md`](../../docs/BET-AGENT-DISTRIBUTION.md).
