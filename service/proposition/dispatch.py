from __future__ import annotations

import json
import subprocess
from typing import Any

from service.control_panel.commands import build_create_wager_command


def dispatch_proposal(
    *,
    proposition: str,
    outcomes: list[str],
    factory: str,
    collateral: str,
    rpc_url: str,
    private_key: str,
    betting_close_time: int,
    resolution_window: int,
    resolver: str,
    betting_closer: str,
    resolution_closer: str,
    extra_recipients: list[str],
    extra_bps: list[int],
    dry_run: bool = False,
) -> dict[str, Any]:
    cmd = build_create_wager_command(
        factory=factory,
        collateral=collateral,
        proposition=proposition,
        outcomes=outcomes,
        betting_close_time=betting_close_time,
        resolution_window=resolution_window,
        resolver=resolver,
        betting_closer=betting_closer,
        resolution_closer=resolution_closer,
        extra_recipients=extra_recipients,
        extra_bps=extra_bps,
        seed_outcome_indices=[],
        seed_amounts=[],
        rpc_url=rpc_url,
        private_key=private_key,
    ).command
    if dry_run:
        return {"ok": True, "dry_run": True, "command": cmd}
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode == 0:
        return {"ok": True, "stdout": proc.stdout}
    return {"ok": False, "stderr": proc.stderr, "stdout": proc.stdout}


def proposal_to_preview_dict(row: dict[str, Any]) -> dict[str, Any]:
    tx = str(row["tx_hint"] or "")
    err = str(row["dispatch_error"] or "")
    return {
        "id": row["id"],
        "proposition": row["proposition"],
        "outcomes": json.loads(row["outcomes_json"] or "[]"),
        "cadence": row["cadence"],
        "category": row["category"],
        "rationale": row["rationale"],
        "source_refs": json.loads(row["source_refs_json"] or "[]"),
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "tx_hint": (tx[:2000] + "…") if len(tx) > 2000 else tx,
        "dispatch_error": (err[:2000] + "…") if len(err) > 2000 else err,
    }
