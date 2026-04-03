# `paramutuel_bettor`

Bet **scout / planner** for Paramutuel: indexer JSON in, ranked bet ideas + optional `cast calldata` out.

See [`docs/BET-AGENT.md`](../../docs/BET-AGENT.md) for full usage, JSON bridge, and safety notes.

Quick start (installed package):

```bash
pip install paramutuel-bettor-agent
paramutuel-bettor health
paramutuel-bettor recommend --bet-amount-raw 1000000 --top 3
```

From a clone (repo root):

```bash
PYTHONPATH=. python3 -m agents.paramutuel_bettor health
PYTHONPATH=. python3 -m agents.paramutuel_bettor recommend --bet-amount-raw 1000000 --top 3
```
