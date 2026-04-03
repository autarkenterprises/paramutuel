from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class IndexerClient:
    def __init__(self, base_url: str, *, timeout: int = 25) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get(self, path: str) -> Any:
        url = f"{self.base_url}{path}"
        req = Request(url, headers={"User-Agent": "ParamutuelBetAgent/1.0", "Accept": "application/json"})
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"indexer HTTP {e.code}: {body[:500]}") from e
        except URLError as e:
            raise RuntimeError(f"indexer request failed: {e}") from e

    def health(self) -> dict[str, Any]:
        data = self._get("/health")
        return data if isinstance(data, dict) else {}

    def list_wagers(
        self,
        *,
        state: str | None = None,
        limit: int = 50,
        offset: int = 0,
        order: str = "desc",
        q: str | None = None,
    ) -> list[dict[str, Any]]:
        params = [f"limit={max(1, min(1000, limit))}", f"offset={max(0, offset)}", f"order={order}"]
        if state:
            params.append(f"state={state.upper()}")
        if q and q.strip():
            from urllib.parse import quote

            params.append(f"q={quote(q.strip())}")
        data = self._get("/wagers?" + "&".join(params))
        if not isinstance(data, dict):
            return []
        rows = data.get("wagers")
        return [dict(r) for r in rows] if isinstance(rows, list) else []

    def get_wager(self, wager_address: str) -> dict[str, Any]:
        w = wager_address.strip().lower()
        data = self._get(f"/wagers/{w}")
        return data if isinstance(data, dict) else {}
