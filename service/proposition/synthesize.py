"""Proposition Service — draft proposal synthesis.

Renders raw source items (RSS / JSON) into operator-reviewable proposal drafts:
proposition prose, candidate outcomes, default windows, and a coarse cadence
label. The cadence label informs operator filtering; it is not authoritative
on-chain (the wager's ``bettingCloseTime`` is what matters).

This module is deliberately rule-based rather than LLM-backed at the time of
writing — every call is deterministic for a given input and clock. An
LLM-backed branch is reserved for future expansion under a feature flag and
would route through :mod:`service.proposition.dispatch`'s synthesis hook.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any


def _truncate(s: str, max_len: int) -> str:
    """Truncate ``s`` to ``max_len`` characters with a single-ellipsis suffix.

    Used to fit synthesised propositions inside the on-chain string limits
    that the V3 factory imposes via :class:`service.control_panel.commands`
    validators. Non-strict — callers that need byte-exact bounds should
    measure UTF-8 byte length separately.
    """
    s = s.strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def infer_cadence(source: dict[str, Any], *, now: datetime | None = None) -> str:
    """Map source config + wall-clock to a coarse cadence label for filtering."""
    explicit = str(source.get("default_cadence") or "").strip().lower()
    if explicit in ("daily", "weekly", "monthly", "yearly", "event", "rolling"):
        return explicit
    now = now or datetime.now(timezone.utc)
    wd = now.weekday()
    if wd == 0:
        return "weekly"
    if now.day == 1:
        return "monthly"
    return "event"


def build_proposition_bundle(
    *,
    headline: str,
    source_label: str,
    category: str,
    link: str,
    cadence: str,
) -> tuple[str, list[str], str, list[dict[str, str]]]:
    """
    Returns (proposition, outcomes, rationale, source_refs).

    The default template is intentionally conservative: YES/NO on whether the
    headline's claim will be broadly corroborated — the operator must still
    judge fitness and edit text before dispatch.
    """
    head = _truncate(headline, 400)
    if not head.endswith("?"):
        prop = f"{head} — will this be corroborated by credible sources before resolution?"
    else:
        prop = f"{head} (corroboration before resolution?)"

    outcomes = ["Yes", "No"]
    rationale = (
        f"Auto-draft from {source_label} ({category}). "
        "Operator must verify wording, outcome rubric, and resolver policy before approval."
    )
    refs = [
        {"label": source_label, "url": link},
    ]
    return prop, outcomes, rationale, refs


def weekly_anchor_title(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    iso = now.date().isocalendar()
    return f"Week {iso[1]} {iso[0]} — macro & crypto snapshot (manual follow-up)"


def template_calendar_propositions(
    *,
    kind: str,
    now: datetime | None = None,
) -> list[tuple[str, list[str], str, list[dict[str, str]]]]:
    """
    Generate neutral calendar-style drafts (operator-curated cadence), not tied
    to a single RSS item.
    """
    now = now or datetime.now(timezone.utc)
    refs = [{"label": "calendar", "url": "https://www.timeanddate.com/calendar/"}]
    if kind == "weekly":
        t = weekly_anchor_title(now)
        prop = f"{t}: will US headline CPI (YoY) for the next print be above consensus as of bet close?"
        return [(prop, ["Above consensus", "At or below consensus"], "Weekly macro template.", refs)]
    if kind == "daily":
        d = now.strftime("%Y-%m-%d")
        prop = f"By end of UTC day {d}, will BTC/USD (major index) close higher than at day open?"
        return [(prop, ["Higher", "Lower or unchanged"], "Daily crypto move template (define oracle).", refs)]
    return []
