from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection, schema_path: Path) -> None:
    sql = schema_path.read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.commit()


def upsert_source_item(
    conn: sqlite3.Connection,
    *,
    source_id: str,
    external_id: str,
    title: str,
    link: str,
    summary: str,
    published_at: int | None,
    raw: dict[str, Any],
) -> int | None:
    """Insert source item if new. Returns row id if inserted, else None."""
    now = int(time.time())
    try:
        cur = conn.execute(
            """
            INSERT INTO source_items (
              source_id, external_id, title, link, summary, published_at, fetched_at, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                external_id,
                title,
                link,
                summary,
                published_at,
                now,
                json.dumps(raw, ensure_ascii=False),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    except sqlite3.IntegrityError:
        conn.rollback()
        return None


def insert_proposal(
    conn: sqlite3.Connection,
    *,
    cadence: str,
    category: str,
    proposition: str,
    outcomes: list[str],
    rationale: str,
    source_refs: list[dict[str, str]],
    source_item_ids: list[int],
) -> int:
    now = int(time.time())
    cur = conn.execute(
        """
        INSERT INTO proposals (
          status, cadence, category, proposition, outcomes_json, rationale,
          source_refs_json, source_item_ids_json, created_at, updated_at
        ) VALUES ('pending', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            cadence,
            category,
            proposition,
            json.dumps(outcomes, ensure_ascii=False),
            rationale,
            json.dumps(source_refs, ensure_ascii=False),
            json.dumps(source_item_ids),
            now,
            now,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def proposition_exists(conn: sqlite3.Connection, *, proposition: str) -> bool:
    row = conn.execute("SELECT 1 FROM proposals WHERE proposition = ? LIMIT 1", (proposition,)).fetchone()
    return row is not None


def get_proposal(conn: sqlite3.Connection, proposal_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
    return dict(row) if row else None


def list_proposals(
    conn: sqlite3.Connection,
    *,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    limit = max(1, min(500, limit))
    offset = max(0, offset)
    if status:
        rows = conn.execute(
            "SELECT * FROM proposals WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (status, limit, offset),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM proposals ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    return [dict(r) for r in rows]


def update_proposal_status(
    conn: sqlite3.Connection,
    proposal_id: int,
    *,
    status: str,
    tx_hint: str | None = None,
    dispatch_error: str = "",
) -> None:
    now = int(time.time())
    if status == "approved":
        conn.execute(
            """
            UPDATE proposals
            SET status = ?, updated_at = ?, approved_at = ?, dispatch_error = ''
            WHERE id = ?
            """,
            (status, now, now, proposal_id),
        )
    elif status == "dispatched":
        conn.execute(
            """
            UPDATE proposals
            SET status = ?, updated_at = ?, dispatched_at = ?, tx_hint = ?, dispatch_error = ?
            WHERE id = ?
            """,
            (status, now, now, tx_hint or "", dispatch_error, proposal_id),
        )
    elif status == "dispatch_failed":
        conn.execute(
            """
            UPDATE proposals
            SET status = ?, updated_at = ?, dispatch_error = ?, tx_hint = ?
            WHERE id = ?
            """,
            (status, now, dispatch_error, tx_hint or "", proposal_id),
        )
    else:
        conn.execute(
            "UPDATE proposals SET status = ?, updated_at = ?, dispatch_error = ? WHERE id = ?",
            (status, now, dispatch_error, proposal_id),
        )
    conn.commit()


def update_proposal_content(
    conn: sqlite3.Connection,
    proposal_id: int,
    *,
    proposition: str,
    outcomes: list[str],
) -> bool:
    row = conn.execute("SELECT status FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
    if not row or row["status"] != "pending":
        return False
    now = int(time.time())
    conn.execute(
        "UPDATE proposals SET proposition = ?, outcomes_json = ?, updated_at = ? WHERE id = ?",
        (proposition, json.dumps(outcomes, ensure_ascii=False), now, proposal_id),
    )
    conn.commit()
    return True
