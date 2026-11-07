# `paramutuel_bettor`

Bet **scout / planner** for Paramutuel: indexer JSON in, ranked bet ideas and calldata out. Standard library only.

See [`docs/BET-AGENT.md`](../../docs/BET-AGENT.md) for full usage, JSON bridge, and safety notes.

Once published to PyPI (**not yet**; see `docs/TASKS.md`):

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
