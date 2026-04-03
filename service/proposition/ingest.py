from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from . import db as dbm
from . import json_sources
from . import rss
from . import synthesize


def load_sources_config(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "sources" in data:
        data = data["sources"]
    if not isinstance(data, list):
        return []
    return [s for s in data if isinstance(s, dict)]


def run_ingest(
    *,
    conn,
    sources_path: Path,
    include_calendar: bool = False,
) -> dict[str, Any]:
    sources = load_sources_config(sources_path)
    created_items = 0
    created_proposals = 0
    errors: list[str] = []

    for src in sources:
        if not src.get("enabled", True):
            continue
        sid = str(src.get("id") or "unknown")
        typ = str(src.get("type") or "").lower()
        category = str(src.get("category") or "general")
        label = str(src.get("label") or sid)
        cadence = synthesize.infer_cadence(src)

        try:
            if typ == "rss":
                url = str(src.get("url") or "")
                if not url:
                    continue
                for it in rss.fetch_rss_items(url):
                    row_id = dbm.upsert_source_item(
                        conn,
                        source_id=sid,
                        external_id=it.external_id,
                        title=it.title,
                        link=it.link,
                        summary=it.summary,
                        published_at=rss.published_ts(it.published_raw),
                        raw=it.raw,
                    )
                    if row_id is None:
                        continue
                    created_items += 1
                    prop, outs, rationale, refs = synthesize.build_proposition_bundle(
                        headline=it.title,
                        source_label=label,
                        category=category,
                        link=it.link or url,
                        cadence=cadence,
                    )
                    dbm.insert_proposal(
                        conn,
                        cadence=cadence,
                        category=category,
                        proposition=prop,
                        outcomes=outs,
                        rationale=rationale,
                        source_refs=refs,
                        source_item_ids=[row_id],
                    )
                    created_proposals += 1

            elif typ == "hackernews":
                limit = int(src.get("limit") or 20)
                for it in json_sources.fetch_hackernews_top(limit=limit):
                    row_id = dbm.upsert_source_item(
                        conn,
                        source_id=sid,
                        external_id=it.external_id,
                        title=it.title,
                        link=it.link,
                        summary=it.summary,
                        published_at=None,
                        raw=it.raw,
                    )
                    if row_id is None:
                        continue
                    created_items += 1
                    prop, outs, rationale, refs = synthesize.build_proposition_bundle(
                        headline=it.title,
                        source_label=label,
                        category=category,
                        link=it.link,
                        cadence=cadence,
                    )
                    dbm.insert_proposal(
                        conn,
                        cadence=cadence,
                        category=category,
                        proposition=prop,
                        outcomes=outs,
                        rationale=rationale,
                        source_refs=refs,
                        source_item_ids=[row_id],
                    )
                    created_proposals += 1

            elif typ == "json_array":
                url = str(src.get("url") or "")
                if not url:
                    continue
                items = json_sources.fetch_json_array(
                    url,
                    title_key=str(src.get("title_key") or "title"),
                    link_key=str(src.get("link_key") or "url"),
                    id_key=str(src.get("id_key") or "id"),
                    link_prefix=str(src.get("link_prefix") or ""),
                )
                for it in items:
                    row_id = dbm.upsert_source_item(
                        conn,
                        source_id=sid,
                        external_id=it.external_id,
                        title=it.title,
                        link=it.link,
                        summary=it.summary,
                        published_at=None,
                        raw=it.raw,
                    )
                    if row_id is None:
                        continue
                    created_items += 1
                    prop, outs, rationale, refs = synthesize.build_proposition_bundle(
                        headline=it.title,
                        source_label=label,
                        category=category,
                        link=it.link or url,
                        cadence=cadence,
                    )
                    dbm.insert_proposal(
                        conn,
                        cadence=cadence,
                        category=category,
                        proposition=prop,
                        outcomes=outs,
                        rationale=rationale,
                        source_refs=refs,
                        source_item_ids=[row_id],
                    )
                    created_proposals += 1

        except Exception as exc:
            errors.append(f"{sid}: {exc}")

    calendar_skipped_duplicates = 0
    if include_calendar:
        for kind in ("daily", "weekly"):
            for prop, outs, rationale, refs in synthesize.template_calendar_propositions(kind=kind):
                if dbm.proposition_exists(conn, proposition=prop):
                    calendar_skipped_duplicates += 1
                    continue
                dbm.insert_proposal(
                    conn,
                    cadence=kind,
                    category="macro",
                    proposition=prop,
                    outcomes=outs,
                    rationale=rationale,
                    source_refs=refs,
                    source_item_ids=[],
                )
                created_proposals += 1

    return {
        "ts": int(time.time()),
        "sources": len(sources),
        "new_source_rows": created_items,
        "new_proposals": created_proposals,
        "calendar_skipped_duplicates": calendar_skipped_duplicates,
        "errors": errors,
    }


def ensure_db(db_path: str, schema_path: Path) -> Any:
    conn = dbm.connect(db_path)
    dbm.init_schema(conn, schema_path)
    return conn
