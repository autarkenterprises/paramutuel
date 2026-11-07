"""Proposition Service — outbound dispatch to the on-chain factory.

Bridges the operator-approved proposal records (managed in :mod:`service.proposition.db`)
to a ``cast send`` invocation that creates the wager. Calldata building is delegated
to :func:`service.control_panel.commands.build_create_wager_command` so the proposition
and control-panel services agree on encoding rules; this module's job is purely running
it and reporting what happened on-chain.

The dispatch path is single-shot per proposal: a re-dispatch of an already-dispatched
record would create a second wager on-chain. The gate lives in the HTTP handler
(:mod:`service.proposition.server`), which holds a lock across the status check and
this call so concurrent requests cannot both pass it.
"""
from __future__ import annotations

import json
from typing import Any

from service.control_panel.commands import build_create_wager_command, redact_argv, run_cast_send


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
        return {"ok": True, "dry_run": True, "command": redact_argv(cmd)}
    result = run_cast_send(cmd)
    if result.ok:
        return {"ok": True, "tx_hash": result.tx_hash, "stdout": result.stdout}
    return {"ok": False, "tx_hash": result.tx_hash, "stderr": result.stderr, "stdout": result.stdout}


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
