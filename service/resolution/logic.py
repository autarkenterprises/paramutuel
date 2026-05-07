"""Pure helpers for the resolution daemon.

These functions consume indexer wager rows (the JSON shape returned by
`/wagers` and `/wagers/{address}`) and decide, without any I/O, whether
a wager is currently a candidate for `resolve` / `retract` by the
configured resolver address.

The split between this module and `service.py` exists so the rules
(state machine boundaries, time arithmetic, address comparison) can be
unit-tested without standing up an HTTP server or shelling out to
`cast`.

V3 lifecycle the predicates encode:

  1. Wager opens (`state == OPEN`).
  2. Betting closes either at `betting_close_time` or via an
     authority-issued `closeBetting()` (sets
     `betting_closed_by_authority`).
  3. The resolver has a `resolution_window` seconds budget — measured
     from `betting_closed_at` when known (authority-close path) and
     otherwise from `betting_close_time` — to call `resolve` or
     `retract`. After that window anyone may `expire()` and the
     resolver no longer can.
"""

from __future__ import annotations

import time
from typing import Any


def normalize_address(addr: str) -> str:
    """Lowercase the hex tail of an EVM address for case-insensitive equality.

    The indexer surfaces addresses as the tx sender originally encoded
    them, so checksums vary across rows. We compare on the bottom 40
    hex chars to avoid spurious "resolver mismatch" rejections.
    """
    return "0x" + addr.lower().replace("0x", "")[-40:]


def betting_is_closed(wager: dict[str, Any], now_ts: int | None = None) -> bool:
    """Return True iff bets can no longer be placed on `wager`.

    Two paths close betting in V3: an authority calling `closeBetting()`
    (mirrored by the indexer as `betting_closed_by_authority=1`), or
    `now_ts >= betting_close_time` for time-bounded wagers. A wager
    with `betting_close_time == 0` and no authority close is "open
    forever" until an authority closes it.
    """
    if now_ts is None:
        now_ts = int(time.time())
    if int(wager.get("betting_closed_by_authority") or 0) == 1:
        return True
    close_time = int(wager.get("betting_close_time") or 0)
    return close_time > 0 and now_ts >= close_time


def resolution_window_is_over(wager: dict[str, Any], now_ts: int | None = None) -> bool:
    """Return True iff the resolver can no longer act and `expire()` is the only path forward.

    The window starts at `betting_closed_at` when the indexer recorded
    it (authority-close path uses the on-chain block timestamp);
    otherwise the time-bounded `betting_close_time` is the start. If
    `resolution_window == 0` the window never expires and the resolver
    keeps custody indefinitely. Once `now_ts > base + window`, the
    daemon should refuse to act and let `expire()` flow run instead.
    """
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
    """Explain why `wager` is *not* actionable, or return None when it is.

    Used by the daemon to label every candidate row even when it cannot
    be resolved right now — the operator UI surfaces the reason so it
    is visible whether the blocker is the wager state, an unrelated
    resolver, betting still being open, or that the window has closed
    and only `expire()` applies. A None return means all four gates
    pass and the daemon may submit a tx if a decision JSON entry
    exists.
    """
    if str(wager.get("state") or "").upper() != "OPEN":
        return "wager not OPEN"
    if normalize_address(str(wager.get("resolver") or "")) != normalize_address(resolver_address):
        return "resolver mismatch"
    if not betting_is_closed(wager, now_ts):
        return "betting still open"
    if resolution_window_is_over(wager, now_ts):
        return "resolution window over (use expire)"
    return None
