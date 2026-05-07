"""Bet scout — runtime configuration helpers.

Two responsibilities: (a) locate the repository root so the agent can
read ``config/deployments.json`` when installed from source, and (b)
resolve the indexer URL the agent should query. Resolution order is
``INDEXER_URL`` env var, then the ``baseSepolia.explorerApiBase`` /
``baseMainnet.explorerApiBase`` field in ``config/deployments.json``,
then a documented public fallback.

The agent is intentionally network-only — it holds no private keys and
takes no signing path — so misconfiguration here can only produce stale
or empty quotes, never a wrong-chain transaction.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def repo_root() -> Path:
    """Return the paramutuel repo root.

    Used to locate ``config/deployments.json`` when the agent is run from
    a clone (``python3 -m agents.paramutuel_bettor``); when installed
    from PyPI, the env var path takes precedence and this fallback is
    not exercised.
    """
    return Path(__file__).resolve().parents[2]


def load_default_indexer_url() -> str:
    url = os.environ.get("INDEXER_URL", "").strip()
    if url:
        return url.rstrip("/")
    path = repo_root() / "config" / "deployments.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            net = str(data.get("defaultNetwork") or "baseSepolia").strip()
            base = str((data.get(net) or {}).get("explorerApiBase") or "").strip()
            if base:
                return base.rstrip("/")
        except (json.JSONDecodeError, TypeError):
            pass
    return "http://127.0.0.1:8090"
