#!/usr/bin/env python3
"""Paramutuel indexer — V3 unified factory (ADR-0010).

Single factory, two wager modes:
  - `enumerated` — bitmask tickets + payoff policies (SINGLE_WINNER / ANY_OF /
    EXACT_SET / AT_LEAST_K / WEIGHTED_OVERLAP).
  - `freeform`   — UTF-8 answer strings hashed to `answerId` with domain byte 0x03.

The `protocol_version` column on `wagers` stores the wager mode (`enumerated`
or `freeform`). Earlier v1 / v2 / standalone-freeform contracts are not
supported.

Idempotency contract
--------------------
Every event is keyed by ``event_id = "<txHash>:<logIndex>"``. ``apply_log``
performs an ``INSERT OR IGNORE`` into ``events_log`` and only mutates the
derived tables (``wagers``, ``wager_totals``, ``wager_ticket_pools``) when
that insert actually wrote a new row. Replaying the same RPC response — or
re-syncing an overlapping block window after a restart — is therefore safe
and produces no double counting. ``apply_log`` also drops any wager-scoped
event whose ``WagerCreatedV3*`` parent row is not yet present, so partial /
out-of-order log batches reconcile on the next sync pass.

Event topic schema
------------------
``TOPICS`` is the canonical V3 keccak topic table. The two factory topics
are scoped to the configured factory address (out-of-factory ``WagerCreated``
events are ignored); all other events are address-scoped to the wager that
emitted them and require the corresponding ``wagers`` row to exist.

Sync loop
---------
``sync_logs`` walks ``[from_block, to_block]`` in ``chunk_size`` slices,
bisecting on RPC error so a single hot range cannot stall progress. Each chunk
is one address-filtered query over the factory and every wager it created
(batched, since providers cap the address list), plus a follow-up only for
wagers created inside that chunk (ADR-0021 U4). Filtering by address matters
because anyone can deploy a contract that emits our topics; an unfiltered scan
would pull that spam into every response. The ``meta`` table tracks the cursor
(``last_indexed_block``), the chain head (``chain_head``), the most recent
transient error (``last_sync_error``), and logs that could not be applied
(``skipped_log_count``, ``last_skipped_log``) for the ``/health`` endpoint.

Reorg handling
--------------
Derived state is insert-only: there is no rewinder. A reorg that moves a log to
a new position would be ingested as a new event, and one that drops a transaction
leaves a ghost, so stakes could be double-counted or overstated until the database
is rebuilt from chain. ``sync_logs`` therefore stays ``confirmations`` blocks
behind the head (``INDEXER_CONFIRMATIONS``, default 5 in ``live_api``), which
removes the practical risk on Base without making the UI noticeably stale. A reorg
deeper than that requires a rebuild; see ``docs/INDEXER-HOSTING.md``.
"""
import argparse
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import request

TOPICS = {
    # Factory (ParamutuelFactoryV3)
    "WagerCreatedV3Enumerated": "0xff766b6fc8dd2e2b1c7be675a874f160c4cada5bf32dac8b1b2e0d6ae7bdb0da",
    "WagerCreatedV3Freeform": "0xf59da875d5b5de3b09728f042bebc2a20357ee08ca31bbaf584efd9cb0ec4c53",
    # Wager (ParamutuelWagerV3)
    "BetPlacedV3Enumerated": "0xd49e0d995d5bc2e9cc268a6a482b0d8ec9ed18ddeae89fc67001c2efa6fee5b0",
    "BetPlacedV3Freeform": "0xecda6e726cfee6e62f696fb6fc02e680aa5742138f2635d615d7b8bca3db15c4",
    "FreeformAnswerRevealedV3": "0xc592882ab1e5cbea3e2ffcba0e57150521e332df9ffb0d024f58b4ee738b6906",
    "ResolvedV3Enumerated": "0x0a2e969cad318ad34168d32c8cbce850c7903442301e6e8d824116385833f290",
    "ResolvedV3Freeform": "0xfeae22eca71fbae658ba63b5add1f9f5371e7fd5bf7597f8b97cdaf24a29a922",
    "BettingClosedByAuthorityV3": "0x309f6e1169f98c711fa766027cd3ca7a3faa5d73827678a743758b5e0a19593f",
    "ResolutionWindowClosedByAuthorityV3": "0xee6e1578965b067c63388674310a835bfa8973df58b6fe92892eee8ddf9c03fa",
    "RetractedV3": "0xebabcf541ed74aefa8ba4e51e11c11b14add951948fb15973a044658cf583ba3",
    "ExpiredV3": "0x2cd032a0386e334d4ec0a27e3922b8673bbc85a3938f1d9e39aaf827ee803cbc",
    "ClaimedV3": "0x18f56b95da8109fe45e8ff222168c73ba869a66cdb44a1d68d00576efc4377f6",
    "FeeAccruedV3": "0x61e2d065e1dccf6ff8fc518812577d7c01bb33d905b7975c1776a9c2b386cf16",
    "FeeWithdrawnV3": "0xa1f7a7f54e12a1df5b55a8b583db7040559f7fa32576e9ecdacf7dbd49c99e75",
}

# Mirrors `ParamutuelFactoryV3.MAX_OUTCOMES` on-chain.
MAX_WAGER_OUTCOMES = 255

TOPIC_TO_EVENT = {v: k for k, v in TOPICS.items()}
# Who can emit what: the factory emits creation events, wagers emit the rest. A chunk's main query
# covers both under ALL_TOPIC_FILTER; ``apply_log`` still accepts a creation only from the factory.
# See "Sync loop" above for why each query is address-filtered.
FACTORY_TOPIC_FILTER = [[v for k, v in TOPICS.items() if k.startswith("WagerCreated")]]
WAGER_TOPIC_FILTER = [[v for k, v in TOPICS.items() if not k.startswith("WagerCreated")]]
ALL_TOPIC_FILTER = [FACTORY_TOPIC_FILTER[0] + WAGER_TOPIC_FILTER[0]]
CREATION_TOPICS = frozenset(FACTORY_TOPIC_FILTER[0])
# eth_getLogs takes an address list, but providers limit its length, so known wagers are queried in
# batches of this size.
WAGER_ADDRESS_BATCH = 200
# `uint64` timestamps above this do not fit SQLite's signed 64-bit INTEGER. Such values mean
# "effectively never", so clamping preserves their meaning, and the exact value stays in the event log.
SQLITE_INT_MAX = 2**63 - 1
WAGER_PROPOSITION_SELECTOR = "0xba002c61"  # proposition()
WAGER_OUTCOMES_COUNT_SELECTOR = "0x7deb9776"  # outcomesCount()
WAGER_OUTCOME_TEXT_SELECTOR = "0x811a3a4d"  # outcomeText(uint256)
# totalFeeBps() — immutable per wager (protocol slot + proposer extras), but
# absent from the V3 creation events, so it must be read via eth_call
# (ADR-0019). Stored in `wager_totals.total_fee_bps` for fee-aware previews.
WAGER_TOTAL_FEE_BPS_SELECTOR = "0xc56f84cf"
# minNewTicketStake(): absent on wagers from factories deployed before ADR-0020, where the call
# reverts; that reads as "no minimum".
WAGER_MIN_NEW_TICKET_STAKE_SELECTOR = "0x314a4939"


def db_connect(path: str) -> sqlite3.Connection:
    """Open the indexer SQLite DB with cross-thread access enabled.

    The HTTP API server uses ``ThreadingHTTPServer`` and the live daemon
    runs the sync loop on a separate thread; both share a single
    connection per process, so ``check_same_thread=False`` is required.
    Concurrent writers are avoided by giving the sync loop its own
    connection (see ``live_api.main``).
    """
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Apply ``schema.sql`` and ensure derived indices.

    Idempotent, so this is safe to call on every process boot, both from
    the read API and from the sync loop. ``CREATE TABLE IF NOT EXISTS`` does
    not add columns to an existing table, so columns added since a database
    was created are applied here. The dropped ``wager_outcomes`` table was
    never written; per-outcome totals are now derived on read.
    """
    schema = Path(__file__).with_name("schema.sql").read_text()
    conn.executescript(schema)
    existing = {row[1] for row in conn.execute("PRAGMA table_info(wagers)")}
    for column, definition in (
        ("min_new_ticket_stake", "TEXT NOT NULL DEFAULT '0'"),
        ("metadata_complete", "INTEGER NOT NULL DEFAULT 1"),
        ("metadata_attempts", "INTEGER NOT NULL DEFAULT 0"),
        ("metadata_retry_at", "INTEGER NOT NULL DEFAULT 0"),
    ):
        if column not in existing:
            conn.execute(f"ALTER TABLE wagers ADD COLUMN {column} {definition}")
    totals_columns = {row[1] for row in conn.execute("PRAGMA table_info(wager_totals)")}
    if "payout_denominator" not in totals_columns:
        # Before ADR-0021 total_winning_stake held the weighted denominator; split it exactly once.
        conn.execute("ALTER TABLE wager_totals ADD COLUMN payout_denominator TEXT")
        _recompute_resolved_totals(conn)
    conn.execute("DROP TABLE IF EXISTS wager_outcomes")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_wagers_proposition ON wagers(proposition)")
    conn.commit()


def rpc_call(rpc_url: str, method: str, params: List[Any]) -> Any:
    """Issue a single JSON-RPC call and return the ``result`` field.

    Raises ``RuntimeError`` on a JSON-RPC error response so the caller
    can surface it via ``last_sync_error`` rather than silently dropping
    it. The 30-second timeout matches Base Sepolia public-RPC latency
    expectations; longer chunk fetches should be sliced upstream.
    """
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = request.Request(
        rpc_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            # Base Sepolia public RPC can reject default urllib requests without a UA header.
            "User-Agent": "paramutuel-indexer/1.0",
        },
    )
    with request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode())
    if "error" in body:
        raise RuntimeError(f"RPC error: {body['error']}")
    return body["result"]


def _encode_u256(v: int) -> str:
    return f"{v:064x}"


def _decode_u256_word(data_hex: str) -> int:
    payload = data_hex[2:] if data_hex.startswith("0x") else data_hex
    if len(payload) < 64:
        raise ValueError("short uint256 response")
    return int(payload[:64], 16)


def _decode_abi_bytes(data_hex: str) -> bytes:
    """Decode a single ABI-encoded dynamic ``string``/``bytes`` to its exact raw bytes."""
    payload = data_hex[2:] if data_hex.startswith("0x") else data_hex
    offset = int(payload[:64], 16) * 2
    length = int(payload[offset : offset + 64], 16)
    start = offset + 64
    raw = bytes.fromhex(payload[start : start + length * 2])
    if len(raw) != length:
        raise ValueError("truncated dynamic bytes")
    return raw


def _decode_abi_string(data_hex: str) -> str:
    """Decode a single ABI-encoded ``string`` returned by ``eth_call``.

    The dynamic ``string`` layout is ``offset(uint256) | length(uint256) |
    payload(bytes, padded)``; we read the offset, then the length, then
    extract that many bytes. Any short / malformed response is treated
    as an empty string so a partially-deployed wager cannot crash the
    enrichment path.
    """
    payload = data_hex[2:] if data_hex.startswith("0x") else data_hex
    if len(payload) < 128:
        return ""
    offset = int(payload[:64], 16) * 2
    if offset + 64 > len(payload):
        return ""
    length = int(payload[offset : offset + 64], 16)
    start = offset + 64
    end = start + (length * 2)
    if end > len(payload):
        return ""
    raw = bytes.fromhex(payload[start:end])
    return raw.decode("utf-8", errors="replace")


def _eth_call_hex(rpc_url: str, to_addr: str, data_hex: str) -> str:
    return rpc_call(
        rpc_url,
        "eth_call",
        [{"to": to_addr, "data": data_hex}, "latest"],
    )


def fetch_wager_metadata(rpc_url: str, wager_address: str) -> Dict[str, Any]:
    """Read a wager's proposition, outcome labels, fee and minimum stake via ``eth_call``.

    The proposition string and outcome labels live in storage, not in
    events, because they are too large to emit cheaply on every
    creation. The factory creation event tells the indexer the wager
    address; this helper enriches the row with human-readable text the
    explorer / agent can render. Errors are swallowed so an RPC failure
    cannot block log application, but they are reported as
    ``complete: False`` so :func:`backfill_incomplete_metadata` can retry.
    Otherwise one hiccup would blank the wager and zero its fee for good.
    Each read has its own ``try`` so a failure in one cannot lose another.
    """
    proposition = ""
    outcomes: List[str] = []
    total_fee_bps: Optional[int] = None
    min_new_ticket_stake = 0
    complete = True
    try:
        total_fee_bps = _decode_u256_word(
            _eth_call_hex(rpc_url, wager_address, WAGER_TOTAL_FEE_BPS_SELECTOR)
        )
    except Exception:
        total_fee_bps = None
        complete = False
    try:
        min_new_ticket_stake = _decode_u256_word(
            _eth_call_hex(rpc_url, wager_address, WAGER_MIN_NEW_TICKET_STAKE_SELECTOR)
        )
    except Exception as exc:
        # A revert is a definite answer: this wager predates the getter, so it has no minimum.
        # Anything else (timeout, connection reset) means we do not know yet.
        if "revert" not in str(exc).lower():
            complete = False
    try:
        proposition_hex = _eth_call_hex(rpc_url, wager_address, WAGER_PROPOSITION_SELECTOR)
        proposition = _decode_abi_string(proposition_hex)
        count_hex = _eth_call_hex(rpc_url, wager_address, WAGER_OUTCOMES_COUNT_SELECTOR)
        outcomes_count = _decode_u256_word(count_hex)
        outcomes_count = min(outcomes_count, MAX_WAGER_OUTCOMES)
        for i in range(outcomes_count):
            data_hex = WAGER_OUTCOME_TEXT_SELECTOR + _encode_u256(i)
            out_hex = _eth_call_hex(rpc_url, wager_address, data_hex)
            outcomes.append(_decode_abi_string(out_hex))
    except Exception:
        # Metadata enrichment is best-effort and must not block core indexing.
        complete = False
    return {
        "proposition": proposition,
        "outcomes": outcomes,
        "total_fee_bps": total_fee_bps,
        "min_new_ticket_stake": min_new_ticket_stake,
        "complete": complete,
    }


# Defaults when there is no RPC to read from (`rpc_url=None`, used by unit tests driving synthetic
# logs). Marked complete because a retry could not do any better.
_NO_METADATA: Dict[str, Any] = {
    "proposition": "",
    "outcomes": [],
    "total_fee_bps": None,
    "min_new_ticket_stake": 0,
    "complete": True,
}


# Retry schedule for incomplete metadata (ADR-0021 U2): 15 s, doubling, capped at an hour. Never
# abandoned, because an RPC outage ends and a dropped row would blank its wager for good.
METADATA_RETRY_BASE_SECONDS = 15
METADATA_RETRY_MAX_SECONDS = 3_600


def metadata_retry_delay(attempts: int) -> int:
    """Seconds to wait after the ``attempts``-th consecutive failure (1-based)."""
    return min(METADATA_RETRY_BASE_SECONDS << min(max(attempts - 1, 0), 20), METADATA_RETRY_MAX_SECONDS)


def backfill_incomplete_metadata(
    conn: sqlite3.Connection, rpc_url: str, limit: int = 25, now: Optional[int] = None
) -> int:
    """Retry enrichment for wagers whose creation-time reads failed; returns how many were repaired.

    Called on every sync pass, bounded by ``limit`` so a long outage cannot turn each pass into
    thousands of calls. Rows stay untouched until a complete read succeeds, so a partial read never
    overwrites anything. A failed retry pushes the row's ``metadata_retry_at`` back, and rows are
    taken in that order, so rows that keep failing move behind the rest instead of being re-read in
    full on every pass while newer rows wait forever.
    """
    now = int(time.time()) if now is None else now
    rows = conn.execute(
        """
        SELECT wager_address, metadata_attempts FROM wagers
        WHERE metadata_complete = 0 AND metadata_retry_at <= ?
        ORDER BY metadata_retry_at, created_block LIMIT ?
        """,
        (now, limit),
    ).fetchall()
    repaired = 0
    for row in rows:
        wager = row["wager_address"]
        metadata = fetch_wager_metadata(rpc_url, wager)
        if not metadata["complete"]:
            attempts = int(row["metadata_attempts"]) + 1
            conn.execute(
                "UPDATE wagers SET metadata_attempts = ?, metadata_retry_at = ? WHERE wager_address = ?",
                (attempts, now + metadata_retry_delay(attempts), wager),
            )
            continue
        conn.execute(
            """
            UPDATE wagers
            SET proposition = ?, outcomes_json = ?, min_new_ticket_stake = ?, metadata_complete = 1,
                metadata_attempts = 0, metadata_retry_at = 0
            WHERE wager_address = ?
            """,
            (metadata["proposition"], json.dumps(metadata["outcomes"]), str(metadata["min_new_ticket_stake"]), wager),
        )
        conn.execute(
            "UPDATE wager_totals SET total_fee_bps = ? WHERE wager_address = ?",
            (str(metadata["total_fee_bps"] or 0), wager),
        )
        repaired += 1
    conn.commit()
    return repaired


def _winning_pools(policy: int, policy_param: int, winning_mask: int, pools: Dict[int, int]):
    """Yield ``(pool, overlap_size)`` for every ticket that wins under ``policy``.

    The one place the win rule lives, so the stake and the denominator below cannot disagree about
    which tickets won. ``policy`` is the ``PayoffPolicy`` ordinal.
    """
    for mask, pool in pools.items():
        overlap = mask & winning_mask
        if overlap == 0:
            continue
        overlap_size = bin(overlap).count("1")
        if policy in (0, 2):  # SINGLE_WINNER, EXACT_SET
            wins = mask == winning_mask
        elif policy == 3:  # AT_LEAST_K
            wins = overlap_size >= policy_param
        else:  # ANY_OF, WEIGHTED_OVERLAP
            wins = True
        if wins:
            yield pool, overlap_size


def compute_winning_units(policy: int, policy_param: int, winning_mask: int, pools: Dict[int, int]) -> int:
    """Port of ``ParamutuelWagerV3._accumulateWinningUnits``: the on-chain ``payoutDenominator``.

    Clients need this to turn a stake into a payout (``stake * netPot / units``). Under
    WEIGHTED_OVERLAP (4) a ticket counts once per overlapping outcome, so this is units, not tokens.
    The local end-to-end suite compares this with the contract's own value for every policy, so the
    two cannot drift silently.
    """
    return sum(pool * overlap_size if policy == 4 else pool for pool, overlap_size in _winning_pools(policy, policy_param, winning_mask, pools))


def compute_winning_stake(policy: int, policy_param: int, winning_mask: int, pools: Dict[int, int]) -> int:
    """Tokens staked on winning tickets: what ``total_winning_stake`` means to every reader.

    Equal to :func:`compute_winning_units` except under WEIGHTED_OVERLAP, where the site once printed
    the weighted units as a token amount larger than the pot (ADR-0021 U3).
    """
    return sum(pool for pool, _ in _winning_pools(policy, policy_param, winning_mask, pools))


def _ticket_pools(conn: sqlite3.Connection, wager: str) -> Dict[int, int]:
    return {
        int(row["ticket_mask"]): int(row["pool_total"])
        for row in conn.execute("SELECT ticket_mask, pool_total FROM wager_ticket_pools WHERE wager_address = ?", (wager,))
    }


def _recompute_resolved_totals(conn: sqlite3.Connection) -> None:
    """Rewrite the winning stake and denominator of every resolved wager from its stored pools.

    Run once, when ``payout_denominator`` is added to a database written before ADR-0021. Pools are
    final once a wager resolves, so this gives exactly what a fresh index would. A freeform wager's
    denominator is its winning pool, which ``total_winning_stake`` already holds.
    """
    resolved = conn.execute(
        """
        SELECT w.wager_address, w.protocol_version, w.payoff_policy, w.policy_param, t.winning_outcome,
               t.total_winning_stake
        FROM wagers w JOIN wager_totals t ON t.wager_address = w.wager_address
        WHERE w.state = 'RESOLVED' AND t.winning_outcome IS NOT NULL
        """
    ).fetchall()
    for row in resolved:
        wager = row["wager_address"]
        if row["protocol_version"] == "freeform":
            conn.execute(
                "UPDATE wager_totals SET payout_denominator = total_winning_stake WHERE wager_address = ?", (wager,)
            )
            continue
        policy, param = int(row["payoff_policy"] or 0), int(row["policy_param"] or 0)
        mask, pools = int(row["winning_outcome"]), _ticket_pools(conn, wager)
        conn.execute(
            "UPDATE wager_totals SET total_winning_stake = ?, payout_denominator = ? WHERE wager_address = ?",
            (
                str(compute_winning_stake(policy, param, mask, pools)),
                str(compute_winning_units(policy, param, mask, pools)),
                wager,
            ),
        )


def to_int(hex_value: str) -> int:
    return int(hex_value, 16)


def normalize_address(addr: str) -> str:
    """Lower-case 20-byte hex address with a single ``0x`` prefix.

    Topics carry left-padded 32-byte values; the trailing 20 bytes are
    the address. SQLite primary keys are case-sensitive, so every write
    and lookup must run through this helper to keep keys stable.
    """
    return "0x" + addr.lower().replace("0x", "")[-40:]


def topic_to_address(topic_word: str) -> str:
    return normalize_address(topic_word)


def data_word(data_hex: str, idx: int) -> str:
    """Slice the ``idx``-th 32-byte word out of a packed ABI ``data`` blob.

    ``data`` is the non-indexed event payload, hex-encoded with a ``0x``
    prefix; words are 64 hex chars each. Used for static-layout events
    only — dynamic types (``string``, ``bytes``) are not present in V3
    event ABIs and therefore not handled.
    """
    payload = data_hex[2:]
    start = idx * 64
    end = start + 64
    return "0x" + payload[start:end]


def event_id(tx_hash: str, log_index_hex: str) -> str:
    """Build the canonical idempotency key for an on-chain log.

    ``tx_hash`` is lowercased so casing variation between RPC providers
    cannot create duplicate rows; ``log_index_hex`` is converted to a
    decimal integer so the key sorts naturally and matches the
    ``events_log.event_id`` column.
    """
    return f"{tx_hash.lower()}:{to_int(log_index_hex)}"


def get_meta_int(conn: sqlite3.Connection, key: str) -> Optional[int]:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    if not row:
        return None
    return int(row["value"])


def set_meta_int(conn: sqlite3.Connection, key: str, value: int) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )


def get_meta_str(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    if not row:
        return None
    return str(row["value"])


def set_meta_str(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def insert_event_log(
    conn: sqlite3.Connection,
    eid: str,
    wager_address: Optional[str],
    event_name: str,
    block_number: int,
    tx_hash: str,
    log_index: int,
    payload: Dict[str, Any],
) -> bool:
    """Append to ``events_log`` and report whether the write was new.

    Returns ``True`` only when this exact ``event_id`` had not been seen
    before. Callers gate their derived-table mutations on that boolean,
    which is the foundation of the indexer's idempotency contract: a
    replayed log can never double-count pots, totals, or state
    transitions.
    """
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO events_log(event_id, wager_address, event_name, block_number, tx_hash, log_index, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (eid, wager_address, event_name, block_number, tx_hash.lower(), log_index, json.dumps(payload)),
    )
    return cur.rowcount == 1


def apply_log(
    conn: sqlite3.Connection,
    factory_address: str,
    log: Dict[str, Any],
    rpc_url: Optional[str] = None,
) -> None:
    """Decode one ``eth_getLogs`` entry and update derived state.

    The function is the indexer's event-application state machine. Each
    branch:

    1. Identifies the event by its ``topic0`` against ``TOPIC_TO_EVENT``;
       unknown topics are silently dropped (forward-compatibility with
       upstream contract additions).
    2. For factory events (``WagerCreatedV3*``), confirms the emitting
       address matches the configured factory; off-factory creations are
       ignored.
    3. For wager-scoped events, requires the parent ``wagers`` row to
       exist and otherwise drops the log as orphan (the parent
       ``WagerCreated`` will arrive in a subsequent pass and the event
       will be replayed because its row was never written).
    4. Calls :func:`insert_event_log` first; only mutates derived tables
       when that returned ``True``. This is what keeps replays safe.

    ``rpc_url`` is optional so unit tests can drive the function with
    synthetic logs and no network. When provided, the wager-creation
    branches enrich the row with off-chain ``proposition`` /
    ``outcomeText[]`` via :func:`fetch_wager_metadata`; failures there
    are swallowed and the row still lands.
    """
    factory = normalize_address(factory_address) if factory_address else ""
    address = normalize_address(log["address"])
    topics = log.get("topics", [])
    if not topics:
        return
    topic0 = topics[0].lower()
    event_name = TOPIC_TO_EVENT.get(topic0)
    if not event_name:
        return

    block_number = to_int(log["blockNumber"])
    tx_hash = log["transactionHash"]
    log_index = to_int(log["logIndex"])
    eid = event_id(tx_hash, log["logIndex"])

    if event_name in ("WagerCreatedV3Enumerated", "WagerCreatedV3Freeform"):
        if not factory or address != factory:
            return
        # Replays must not repeat the (many) metadata RPC calls below.
        if conn.execute("SELECT 1 FROM events_log WHERE event_id = ?", (eid,)).fetchone():
            return
        enumerated = event_name == "WagerCreatedV3Enumerated"
        wager = topic_to_address(topics[1])
        proposer = topic_to_address(topics[2])
        resolver = topic_to_address(topics[3])
        collateral_token = topic_to_address(data_word(log["data"], 0))
        # The enumerated event carries two extra leading words (payoffPolicy, policyParam).
        payoff_policy = to_int(data_word(log["data"], 1)) if enumerated else None
        policy_param = to_int(data_word(log["data"], 2)) if enumerated else None
        first = 3 if enumerated else 1
        betting_close_time = to_int(data_word(log["data"], first))
        resolution_window = to_int(data_word(log["data"], first + 1))
        resolution_deadline = to_int(data_word(log["data"], first + 2))
        betting_closer = topic_to_address(data_word(log["data"], first + 3))
        resolution_closer = topic_to_address(data_word(log["data"], first + 4))
        metadata = fetch_wager_metadata(rpc_url, wager) if rpc_url else _NO_METADATA

        payload: Dict[str, Any] = {
            "wager": wager,
            "proposer": proposer,
            "resolver": resolver,
            "collateralToken": collateral_token,
            "bettingCloseTime": betting_close_time,
            "resolutionWindow": resolution_window,
            "resolutionDeadline": resolution_deadline,
            "bettingCloser": betting_closer,
            "resolutionCloser": resolution_closer,
        }
        if enumerated:
            payload["payoffPolicy"] = payoff_policy
            payload["policyParam"] = policy_param
        insert_event_log(conn, eid, wager, event_name, block_number, tx_hash, log_index, payload)

        conn.execute(
            """
            INSERT OR IGNORE INTO wagers(
              wager_address, factory_address, proposer, resolver, betting_closer, resolution_closer,
              collateral_token, proposition, outcomes_json, betting_close_time, resolution_window, resolution_deadline,
              protocol_version, payoff_policy, policy_param, min_new_ticket_stake, metadata_complete,
              state, created_block, created_tx_hash
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?)
            """,
            (
                wager,
                factory,
                proposer,
                resolver,
                betting_closer,
                resolution_closer,
                collateral_token,
                metadata["proposition"],
                json.dumps(metadata["outcomes"]),
                min(betting_close_time, SQLITE_INT_MAX),
                min(resolution_window, SQLITE_INT_MAX),
                min(resolution_deadline, SQLITE_INT_MAX),
                "enumerated" if enumerated else "freeform",
                payoff_policy,
                str(policy_param) if enumerated else None,
                str(metadata["min_new_ticket_stake"]),
                1 if metadata["complete"] else 0,
                block_number,
                tx_hash.lower(),
            ),
        )
        conn.execute(
            "INSERT OR IGNORE INTO wager_totals(wager_address, total_pot, total_fee_bps) VALUES (?, '0', ?)",
            (wager, str(metadata["total_fee_bps"] or 0)),
        )
        return

    # all remaining events are emitted by wager contracts
    wager = address
    if not conn.execute("SELECT 1 FROM wagers WHERE wager_address = ?", (wager,)).fetchone():
        # Skip orphan logs; indexer expects WagerCreated first.
        return

    if event_name == "BettingClosedByAuthorityV3":
        closed_at = to_int(data_word(log["data"], 0))
        inserted = insert_event_log(
            conn, eid, wager, event_name, block_number, tx_hash, log_index, {"closedAt": closed_at}
        )
        if not inserted:
            return
        conn.execute(
            "UPDATE wagers SET betting_closed_by_authority = 1, betting_closed_at = ? WHERE wager_address = ?",
            (closed_at, wager),
        )
        return

    if event_name == "ResolutionWindowClosedByAuthorityV3":
        closed_at = to_int(data_word(log["data"], 0))
        inserted = insert_event_log(
            conn, eid, wager, event_name, block_number, tx_hash, log_index, {"closedAt": closed_at}
        )
        if not inserted:
            return
        conn.execute(
            "UPDATE wagers SET resolution_window_closed = 1, resolution_window_closed_at = ? WHERE wager_address = ?",
            (closed_at, wager),
        )
        return

    if event_name == "FreeformAnswerRevealedV3":
        answer_id = topics[1].lower()
        raw = _decode_abi_bytes(log["data"])
        # `string` on-chain can hold any bytes. Lossy decoding would produce text that hashes to a
        # different answer id, so invalid UTF-8 keeps only the exact hex.
        try:
            answer_text: Optional[str] = raw.decode("utf-8")
        except UnicodeDecodeError:
            answer_text = None
        answer_hex = "0x" + raw.hex()
        inserted = insert_event_log(
            conn, eid, wager, event_name, block_number, tx_hash, log_index,
            {"answerId": answer_id, "answer": answer_text, "answerHex": answer_hex},
        )
        if not inserted:
            return
        conn.execute(
            "INSERT OR IGNORE INTO wager_answers(wager_address, answer_id, answer_text, answer_hex) VALUES (?, ?, ?, ?)",
            (wager, answer_id, answer_text, answer_hex),
        )
        return

    if event_name == "BetPlacedV3Enumerated":
        bettor = topic_to_address(topics[1])
        ticket_mask = to_int(data_word(log["data"], 0))
        amount = to_int(data_word(log["data"], 1))
        mask_key = str(ticket_mask)
        payload = {"bettor": bettor, "ticketMask": ticket_mask, "amount": amount}
        inserted = insert_event_log(
            conn, eid, wager, event_name, block_number, tx_hash, log_index, payload
        )
        if not inserted:
            return
        conn.execute(
            "INSERT OR IGNORE INTO wager_ticket_pools(wager_address, ticket_mask, pool_total) VALUES (?, ?, '0')",
            (wager, mask_key),
        )
        row = conn.execute(
            "SELECT pool_total FROM wager_ticket_pools WHERE wager_address = ? AND ticket_mask = ?",
            (wager, mask_key),
        ).fetchone()
        prev = int(row["pool_total"] or 0) if row else 0
        conn.execute(
            "UPDATE wager_ticket_pools SET pool_total = ? WHERE wager_address = ? AND ticket_mask = ?",
            (str(prev + amount), wager, mask_key),
        )
        _add_to_total_pot(conn, wager, amount)
        return

    if event_name == "BetPlacedV3Freeform":
        bettor = topic_to_address(topics[1])
        answer_id_key = topics[2].lower()
        amount = to_int(data_word(log["data"], 0))
        payload = {"bettor": bettor, "answerId": answer_id_key, "amount": amount}
        inserted = insert_event_log(
            conn, eid, wager, event_name, block_number, tx_hash, log_index, payload
        )
        if not inserted:
            return
        conn.execute(
            "INSERT OR IGNORE INTO wager_ticket_pools(wager_address, ticket_mask, pool_total) VALUES (?, ?, '0')",
            (wager, answer_id_key),
        )
        row = conn.execute(
            "SELECT pool_total FROM wager_ticket_pools WHERE wager_address = ? AND ticket_mask = ?",
            (wager, answer_id_key),
        ).fetchone()
        prev = int(row["pool_total"] or 0) if row else 0
        conn.execute(
            "UPDATE wager_ticket_pools SET pool_total = ? WHERE wager_address = ? AND ticket_mask = ?",
            (str(prev + amount), wager, answer_id_key),
        )
        _add_to_total_pot(conn, wager, amount)
        return

    if event_name == "ResolvedV3Enumerated":
        winning_val = to_int(data_word(log["data"], 0))
        res_payload = {"winningMask": winning_val, "mode": "enumerated"}
        inserted = insert_event_log(
            conn, eid, wager, event_name, block_number, tx_hash, log_index, res_payload
        )
        if not inserted:
            return
        conn.execute("UPDATE wagers SET state = 'RESOLVED' WHERE wager_address = ?", (wager,))
        policy_row = conn.execute(
            "SELECT payoff_policy, policy_param FROM wagers WHERE wager_address = ?", (wager,)
        ).fetchone()
        policy, param = int(policy_row["payoff_policy"] or 0), int(policy_row["policy_param"] or 0)
        pools = _ticket_pools(conn, wager)
        conn.execute(
            """
            UPDATE wager_totals SET winning_outcome = ?, total_winning_stake = ?, payout_denominator = ?
            WHERE wager_address = ?
            """,
            (
                str(winning_val),
                str(compute_winning_stake(policy, param, winning_val, pools)),
                str(compute_winning_units(policy, param, winning_val, pools)),
                wager,
            ),
        )
        return

    if event_name == "ResolvedV3Freeform":
        winning_key = topics[1].lower()
        res_payload = {"winningAnswerId": winning_key, "mode": "freeform"}
        inserted = insert_event_log(
            conn, eid, wager, event_name, block_number, tx_hash, log_index, res_payload
        )
        if not inserted:
            return
        conn.execute("UPDATE wagers SET state = 'RESOLVED' WHERE wager_address = ?", (wager,))
        pool_row = conn.execute(
            "SELECT pool_total FROM wager_ticket_pools WHERE wager_address = ? AND ticket_mask = ?",
            (wager, winning_key),
        ).fetchone()
        winning_pool = str(pool_row["pool_total"]) if pool_row else "0"
        conn.execute(
            """
            UPDATE wager_totals SET winning_outcome = ?, total_winning_stake = ?, payout_denominator = ?
            WHERE wager_address = ?
            """,
            (winning_key, winning_pool, winning_pool, wager),
        )
        return

    if event_name in ("RetractedV3", "ExpiredV3"):
        inserted = insert_event_log(
            conn, eid, wager, event_name, block_number, tx_hash, log_index, {}
        )
        if not inserted:
            return
        conn.execute("UPDATE wagers SET state = 'RETRACTED' WHERE wager_address = ?", (wager,))
        return

    if event_name == "ClaimedV3":
        bettor = topic_to_address(topics[1])
        amount = to_int(data_word(log["data"], 0))
        insert_event_log(
            conn, eid, wager, event_name, block_number, tx_hash, log_index,
            {"bettor": bettor, "amount": amount},
        )
        return

    if event_name in ("FeeAccruedV3", "FeeWithdrawnV3"):
        recipient = topic_to_address(topics[1])
        amount = to_int(data_word(log["data"], 0))
        insert_event_log(
            conn, eid, wager, event_name, block_number, tx_hash, log_index,
            {"recipient": recipient, "amount": amount},
        )
        return


def _add_to_total_pot(conn: sqlite3.Connection, wager: str, amount: int) -> None:
    """Add ``amount`` to ``wager_totals.total_pot`` with exact big-int math.

    Amounts are uint256 and stored as decimal TEXT. The arithmetic must
    happen in Python: SQLite integers are signed 64-bit (~9.22 tokens at
    18 decimals), and the former ``CAST(total_pot AS INTEGER) + ?`` both
    degraded the pot to a REAL (``'1.0e+19'``) past 2**63 and raised
    ``OverflowError`` binding a single amount >= 2**63 (ADR-0019).
    """
    row = conn.execute(
        "SELECT total_pot FROM wager_totals WHERE wager_address = ?", (wager,)
    ).fetchone()
    if row is None:
        return
    conn.execute(
        "UPDATE wager_totals SET total_pot = ? WHERE wager_address = ?",
        (str(int(row["total_pot"] or 0) + amount), wager),
    )


def get_expire_candidates(conn: sqlite3.Connection, now_ts: Optional[int] = None) -> List[sqlite3.Row]:
    """Return ``OPEN`` wagers whose resolution window has elapsed.

    Two paths qualify a wager as a candidate:

    * The resolution closer explicitly closed the window
      (``resolution_window_closed = 1``); the on-chain expire check then
      only verifies the marker, regardless of clock.
    * The wall-clock has passed ``betting_close_at + resolution_window``
      (or ``betting_close_time + resolution_window`` if the authority
      never explicitly closed betting). The fallback to the configured
      ``betting_close_time`` matches the contract's expire path for
      wagers where betting has not been authority-closed.

    Used by the sweeper (``--execute`` calls ``expire()``) and by the
    ``/sweeper/expire-candidates`` endpoint for operator preview.
    """
    if now_ts is None:
        now_ts = int(time.time())
    return conn.execute(
        """
        SELECT wager_address, resolver, resolution_window, resolution_deadline, betting_closed_at, resolution_window_closed
        FROM wagers
        WHERE state = 'OPEN' AND (
          resolution_window_closed = 1
          OR (
            resolution_window > 0
            AND (
              (betting_closed_at IS NOT NULL AND betting_closed_at + resolution_window < ?)
              OR (betting_closed_at IS NULL AND betting_close_time > 0 AND betting_close_time + resolution_window < ?)
            )
          )
        )
        ORDER BY resolution_deadline ASC
        """,
        (now_ts, now_ts),
    ).fetchall()


def _eth_get_logs_bisect(
    rpc_url: str,
    start: int,
    end: int,
    topic_filter: List[List[str]],
    min_span: int = 1,
    address: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Return logs for ``[start, end]``, halving on RPC failure.

    Public RPCs (notably Base Sepolia's free tier) reject ``eth_getLogs``
    requests whose response would exceed an internal byte limit, with
    no precise hint about the threshold. Bisecting on failure keeps the
    sync loop progressing without forcing the operator to lower
    ``--chunk-size`` for the entire run. ``min_span=1`` means a single
    block that still fails will surface its exception to the caller,
    where it lands in ``last_sync_error`` and aborts the chunk.
    """
    if start > end:
        return []
    span = end - start + 1
    log_filter: Dict[str, Any] = {"fromBlock": hex(start), "toBlock": hex(end), "topics": topic_filter}
    if address is not None:
        log_filter["address"] = address
    try:
        return rpc_call(rpc_url, "eth_getLogs", [log_filter])
    except Exception:
        if span <= min_span:
            raise
        mid = start + (span // 2) - 1
        left = _eth_get_logs_bisect(rpc_url, start, mid, topic_filter, min_span, address)
        right = _eth_get_logs_bisect(rpc_url, mid + 1, end, topic_filter, min_span, address)
        return left + right


def _apply_logs(conn: sqlite3.Connection, factory_address: str, logs: List[Dict[str, Any]], rpc_url: str) -> int:
    """Apply logs in chain order, each atomically, and return how many landed.

    Each log gets its own SAVEPOINT so a failure part way through ``apply_log`` rolls back *all* of
    that log's writes instead of committing a torn state with the chunk. One malformed log must not
    stop the sync, but it is lost once the cursor moves past it, so it is counted and described for
    ``/health`` instead of vanishing.
    """
    applied = 0
    logs = sorted(logs, key=lambda l: (to_int(l["blockNumber"]), to_int(l["logIndex"])))
    for log in logs:
        conn.execute("SAVEPOINT apply_one_log")
        try:
            apply_log(conn, factory_address, log, rpc_url=rpc_url)
            conn.execute("RELEASE SAVEPOINT apply_one_log")
            applied += 1
        except Exception as exc:
            conn.execute("ROLLBACK TO SAVEPOINT apply_one_log")
            conn.execute("RELEASE SAVEPOINT apply_one_log")
            where = f"{log.get('transactionHash', '?')}:{log.get('logIndex', '?')}"
            print(f"[indexer-sync] skip log {where}: {exc}")
            set_meta_int(conn, "skipped_log_count", (get_meta_int(conn, "skipped_log_count") or 0) + 1)
            set_meta_str(conn, "last_skipped_log", f"{where}: {exc}"[:800])
    return applied


def _is_creation(log: Any) -> bool:
    """True when a raw log carries a wager-creation topic. Tolerates malformed logs, which
    ``_apply_logs`` counts as skipped rather than letting them stop the sync."""
    topics = log.get("topics") if isinstance(log, dict) else None
    return bool(topics) and str(topics[0]).lower() in CREATION_TOPICS


def _known_wagers(conn: sqlite3.Connection) -> List[str]:
    """Every indexed wager address, in a stable order so batches are deterministic."""
    return [row[0] for row in conn.execute("SELECT wager_address FROM wagers ORDER BY wager_address")]


def sync_logs(
    rpc_url: str,
    conn: sqlite3.Connection,
    factory_address: str,
    from_block: Optional[int],
    to_block: Optional[int],
    chunk_size: int,
    *,
    allow_genesis_start: bool = False,
    confirmations: int = 0,
) -> int:
    """Pull and apply factory + wager logs for the requested block range.

    Cursor resolution:

    * ``from_block`` is taken explicitly when given, else from the
      ``last_indexed_block`` meta row, else (only when
      ``allow_genesis_start`` is true, i.e. the CLI entrypoint) from
      block 0. The ``live_api`` daemon never sets ``allow_genesis_start``
      because starting a long-running sync at block 0 against Base
      mainnet would burn RPC quota; it requires an explicit
      ``INDEXER_FROM_BLOCK`` / ``indexerFromBlock`` instead.
    * ``to_block`` defaults to the chain head minus ``confirmations``, and
      is capped to it (see "Reorg handling" in the module docstring).

    Each chunk makes one query over the factory and the known wagers
    (``ceil((wagers + 1) / WAGER_ADDRESS_BATCH)`` once there are many), then
    a follow-up only for wagers that chunk created, because a wager's seed
    bets land in its creation transaction and it was not yet in the address
    list. Most chunks create nothing, so most cost one call (ADR-0021 U4;
    before, every chunk cost at least two). It then commits the cursor and
    clears ``last_sync_error``. A failure while fetching commits what was
    applied and re-raises; the next pass replays the chunk, which is safe
    because application is idempotent. Returns the number of logs
    successfully applied (useful for the live daemon's heartbeat output).
    """
    factory_address = normalize_address(factory_address) if factory_address else ""

    latest = to_int(rpc_call(rpc_url, "eth_blockNumber", []))
    set_meta_int(conn, "chain_head", latest)
    set_meta_str(conn, "last_sync_error", "")
    conn.commit()

    backfill_incomplete_metadata(conn, rpc_url)

    safe_head = max(0, latest - confirmations)
    if to_block is None:
        to_block = safe_head
    to_block = min(to_block, safe_head)

    if from_block is None:
        last_indexed = get_meta_int(conn, "last_indexed_block")
        if last_indexed is not None:
            from_block = last_indexed + 1
        elif allow_genesis_start:
            from_block = 0
        else:
            raise RuntimeError(
                "Indexer has no last_indexed_block cursor and from_block was not supplied "
                "(set INDEXER_FROM_BLOCK or indexerFromBlock in deployments for live_api)"
            )

    if from_block > to_block:
        # Being caught up (cursor one past the safe head) is the normal idle state. A cursor past
        # the actual head means the configured start block or network is wrong.
        if from_block > latest + 1:
            set_meta_str(
                conn,
                "last_sync_error",
                f"from_block {from_block} is ahead of chain head {latest} (check INDEXER_FROM_BLOCK / indexerFromBlock)",
            )
        conn.commit()
        return 0

    processed = 0
    # Only this loop adds wagers, so the list is read once and extended as chunks create wagers,
    # rather than re-read on each of what can be ~100k chunks in a cold-start replay.
    known = _known_wagers(conn)

    start = from_block
    while start <= to_block:
        end = min(start + chunk_size - 1, to_block)
        try:
            addresses = ([factory_address] if factory_address else []) + known
            saw_creation = False
            for i in range(0, len(addresses), WAGER_ADDRESS_BATCH):
                logs = _eth_get_logs_bisect(
                    rpc_url, start, end, ALL_TOPIC_FILTER, min_span=1, address=addresses[i : i + WAGER_ADDRESS_BATCH]
                )
                saw_creation = saw_creation or any(_is_creation(log) for log in logs)
                processed += _apply_logs(conn, factory_address, logs, rpc_url)
            if saw_creation:
                already_known = set(known)
                created = [w for w in _known_wagers(conn) if w not in already_known]
                for i in range(0, len(created), WAGER_ADDRESS_BATCH):
                    logs = _eth_get_logs_bisect(
                        rpc_url, start, end, WAGER_TOPIC_FILTER, min_span=1, address=created[i : i + WAGER_ADDRESS_BATCH]
                    )
                    processed += _apply_logs(conn, factory_address, logs, rpc_url)
                known = known + created
        except Exception as exc:
            set_meta_str(
                conn,
                "last_sync_error",
                f"eth_getLogs blocks {start}-{end}: {exc}"[:800],
            )
            conn.commit()
            raise

        set_meta_int(conn, "last_indexed_block", end)
        set_meta_str(conn, "last_sync_error", "")
        conn.commit()
        start = end + 1

    return processed


def main() -> None:
    parser = argparse.ArgumentParser(description="Paramutuel indexer (V3 unified)")
    parser.add_argument("--rpc-url", required=True)
    parser.add_argument("--db-path", default="service/indexer/indexer.db")
    parser.add_argument(
        "--factory-address",
        required=True,
        help="ParamutuelFactoryV3 address (ADR-0010 unified factory).",
    )
    parser.add_argument("--from-block", type=int, default=None)
    parser.add_argument("--to-block", type=int, default=None)
    parser.add_argument("--chunk-size", type=int, default=2_000)
    parser.add_argument("--confirmations", type=int, default=5, help="Stay this many blocks behind the head (reorg safety).")
    args = parser.parse_args()

    conn = db_connect(args.db_path)
    init_db(conn)
    count = sync_logs(
        rpc_url=args.rpc_url,
        conn=conn,
        factory_address=args.factory_address,
        from_block=args.from_block,
        to_block=args.to_block,
        chunk_size=args.chunk_size,
        allow_genesis_start=True,
        confirmations=args.confirmations,
    )
    print(f"Processed logs: {count}")


if __name__ == "__main__":
    main()
