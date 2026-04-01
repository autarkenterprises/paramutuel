from __future__ import annotations

import time
from typing import Any


def normalize_address(addr: str) -> str:
    return "0x" + addr.lower().replace("0x", "")[-40:]


def betting_is_closed(wager: dict[str, Any], now_ts: int | None = None) -> bool:
    if now_ts is None:
        now_ts = int(time.time())
    if int(wager.get("betting_closed_by_authority") or 0) == 1:
        return True
    close_time = int(wager.get("betting_close_time") or 0)
    return close_time > 0 and now_ts >= close_time


def resolution_window_is_over(wager: dict[str, Any], now_ts: int | None = None) -> bool:
    if now_ts is None:
        now_ts = int(time.time())
    if int(wager.get("resolution_window_closed") or 0) == 1:
        return True
    resolution_window = int(wager.get("resolution_window") or 0)
    if resolution_window <= 0:
        return False
    betting_closed_at = wager.get("betting_closed_at")
    if betting_closed_at is not None:
        base = int(betting_closed_at)
    else:
        close_time = int(wager.get("betting_close_time") or 0)
        if close_time <= 0:
            return False
        base = close_time
    return now_ts > (base + resolution_window)


def actionability_reason(
    wager: dict[str, Any],
    *,
    resolver_address: str,
    now_ts: int | None = None,
) -> str | None:
    if str(wager.get("state") or "").upper() != "OPEN":
        return "wager not OPEN"
    if normalize_address(str(wager.get("resolver") or "")) != normalize_address(resolver_address):
        return "resolver mismatch"
    if not betting_is_closed(wager, now_ts):
        return "betting still open"
    if resolution_window_is_over(wager, now_ts):
        return "resolution window over (use expire)"
    return None
