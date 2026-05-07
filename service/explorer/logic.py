"""Explorer service — pure data-shape helpers.

Stateless transforms over indexer-shaped wager dicts. Pulled into a separate
module so they are unit-testable without standing up the HTTP server, and
because the dApp's JS-side equivalents (in ``dapp/logic.js``) need to agree
on the same classification rules — drift between the two would silently
mislabel wagers in the explorer vs the dApp.
"""
from __future__ import annotations


def classify_wager_state(wager: dict) -> str:
    state = wager.get("state", "OPEN")
    if state == "RESOLVED":
        return "resolved"
    if state == "RETRACTED":
        return "retracted"
    return "open"


def can_expire_candidate_row(row: dict, now_ts: int) -> bool:
    if bool(row.get("resolution_window_closed")):
        return True
    resolution_window = int(row.get("resolution_window", 0))
    if resolution_window == 0:
        return False
    closed_at = row.get("betting_closed_at")
    if closed_at is not None:
        return int(closed_at) + resolution_window < now_ts
    close_time = int(row.get("betting_close_time", 0))
    return close_time > 0 and close_time + resolution_window < now_ts
