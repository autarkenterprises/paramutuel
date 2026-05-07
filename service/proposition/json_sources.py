"""Proposition Service — JSON-source ingestor.

Pulls structured items (events, races, scheduled drops) from configured JSON
endpoints. Each source supplies a JSONPath-shaped extraction config; this
module flattens the response into :class:`JsonItem` records that the
:mod:`service.proposition.synthesize` step can render into proposal drafts.

External IDs are computed from the source-specific identity field so the
upstream :func:`service.proposition.db.insert_source_item` dedupe survives
a rerun against a partly-overlapping snapshot — important for endpoints
that reflect a rolling window rather than monotonically appended events.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import request


@dataclass
class JsonItem:
    external_id: str
    title: str
    link: str
    summary: str
    raw: dict[str, Any]


def _http_get(url: str, timeout: int = 25) -> Any:
    req = request.Request(url, headers={"User-Agent": "ParamutuelPropositionService/1.0", "Accept": "application/json"})
    with request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_hackernews_top(*, limit: int = 25, timeout: int = 25) -> list[JsonItem]:
    ids = _http_get("https://hacker-news.firebaseio.com/v0/topstories.json", timeout=timeout)
    if not isinstance(ids, list):
        return []
    out: list[JsonItem] = []
    for story_id in ids[: max(1, min(50, limit))]:
        item = _http_get(f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json", timeout=timeout)
        if not isinstance(item, dict):
            continue
        if item.get("type") != "story":
            continue
        title = str(item.get("title") or "").strip() or "(no title)"
        sid = str(item.get("id") or story_id)
        url = str(item.get("url") or "").strip()
        if not url:
            url = f"https://news.ycombinator.com/item?id={sid}"
        out.append(
            JsonItem(
                external_id=sid,
                title=title[:2000],
                link=url[:2000],
                summary=str(item.get("text") or "")[:8000],
                raw=item,
            )
        )
    return out


def fetch_json_array(
    url: str,
    *,
    title_key: str = "title",
    link_key: str = "url",
    id_key: str = "id",
    link_prefix: str = "",
    timeout: int = 25,
) -> list[JsonItem]:
    data = _http_get(url, timeout=timeout)
    if isinstance(data, dict):
        for key in ("data", "markets", "results", "items"):
            if key in data and isinstance(data[key], list):
                data = data[key]
                break
    if not isinstance(data, list):
        return []
    out: list[JsonItem] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        title = str(row.get(title_key) or "").strip() or "(no title)"
        rid = row.get(id_key)
        ext = str(rid) if rid is not None else title[:200]
        link_val = row.get(link_key)
        link = ""
        if isinstance(link_val, str):
            link = link_val.strip()
        elif link_val is not None:
            link = str(link_val)
        if link_prefix and link and not link.startswith("http"):
            link = link_prefix.rstrip("/") + "/" + link.lstrip("/")
        elif link_prefix and not link:
            slug = row.get("slug")
            if isinstance(slug, str) and slug:
                link = link_prefix.rstrip("/") + "/" + slug.lstrip("/")
        out.append(
            JsonItem(
                external_id=ext[:512],
                title=title[:2000],
                link=link[:2000],
                summary="",
                raw=row,
            )
        )
    return out
