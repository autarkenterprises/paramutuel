from __future__ import annotations

import json
import os
from pathlib import Path


def repo_root() -> Path:
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
