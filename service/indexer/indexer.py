#!/usr/bin/env python3
"""Paramutuel indexer — V3 unified factory (ADR-0010).

Single factory, two wager modes:
  - `enumerated` — bitmask tickets + payoff policies (SINGLE_WINNER / ANY_OF /
    EXACT_SET / AT_LEAST_K / WEIGHTED_OVERLAP).
  - `freeform`   — UTF-8 answer strings hashed to `answerId` with domain byte 0x03.

The `protocol_version` column on `wagers` stores the wager mode (`enumerated`
or `freeform`). Earlier v1 / v2 / standalone-freeform contracts are not
supported.
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
WAGER_PROPOSITION_SELECTOR = "0xba002c61"  # proposition()
WAGER_OUTCOMES_COUNT_SELECTOR = "0x7deb9776"  # outcomesCount()
WAGER_OUTCOME_TEXT_SELECTOR = "0x811a3a4d"  # outcomeText(uint256)


def db_connect(path: str) -> sqlite3.Connection:
    # API server uses ThreadingHTTPServer; allow sqlite connection across handler threads.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    schema = Path(__file__).with_name("schema.sql").read_text()
    conn.executescript(schema)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_wagers_proposition ON wagers(proposition)")
    conn.commit()


def rpc_call(rpc_url: str, method: str, params: List[Any]) -> Any:
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


def _decode_abi_string(data_hex: str) -> str:
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
    proposition = ""
    outcomes: List[str] = []
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
        pass
    return {"proposition": proposition, "outcomes": outcomes}


def to_int(hex_value: str) -> int:
    return int(hex_value, 16)


def normalize_address(addr: str) -> str:
    return "0x" + addr.lower().replace("0x", "")[-40:]


def topic_to_address(topic_word: str) -> str:
    return normalize_address(topic_word)


def data_word(data_hex: str, idx: int) -> str:
    payload = data_hex[2:]
    start = idx * 64
    end = start + 64
    return "0x" + payload[start:end]


def event_id(tx_hash: str, log_index_hex: str) -> str:
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

    if event_name == "WagerCreatedV3Enumerated":
        if not factory or address != factory:
            return
        wager = topic_to_address(topics[1])
        proposer = topic_to_address(topics[2])
        resolver = topic_to_address(topics[3])
        collateral_token = topic_to_address(data_word(log["data"], 0))
        payoff_policy = to_int(data_word(log["data"], 1))
        policy_param = to_int(data_word(log["data"], 2))
        betting_close_time = to_int(data_word(log["data"], 3))
        resolution_window = to_int(data_word(log["data"], 4))
        resolution_deadline = to_int(data_word(log["data"], 5))
        betting_closer = topic_to_address(data_word(log["data"], 6))
        resolution_closer = topic_to_address(data_word(log["data"], 7))
        metadata = {"proposition": "", "outcomes": []}
        if rpc_url:
            metadata = fetch_wager_metadata(rpc_url, wager)

        inserted = insert_event_log(
            conn,
            eid,
            wager,
            event_name,
            block_number,
            tx_hash,
            log_index,
            {
                "wager": wager,
                "proposer": proposer,
                "resolver": resolver,
                "collateralToken": collateral_token,
                "payoffPolicy": payoff_policy,
                "policyParam": policy_param,
                "bettingCloseTime": betting_close_time,
                "resolutionWindow": resolution_window,
                "resolutionDeadline": resolution_deadline,
                "bettingCloser": betting_closer,
                "resolutionCloser": resolution_closer,
            },
        )
        if not inserted:
            return

        conn.execute(
            """
            INSERT OR IGNORE INTO wagers(
              wager_address, factory_address, proposer, resolver, betting_closer, resolution_closer,
              collateral_token, proposition, outcomes_json, betting_close_time, resolution_window, resolution_deadline,
              protocol_version, payoff_policy, policy_param, state, created_block, created_tx_hash
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'enumerated', ?, ?, 'OPEN', ?, ?)
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
                betting_close_time,
                resolution_window,
                resolution_deadline,
                payoff_policy,
                str(policy_param),
                block_number,
                tx_hash.lower(),
            ),
        )
        conn.execute(
            "INSERT OR IGNORE INTO wager_totals(wager_address, total_pot, total_fee_bps) VALUES (?, '0', '0')",
            (wager,),
        )
        return

    if event_name == "WagerCreatedV3Freeform":
        if not factory or address != factory:
            return
        wager = topic_to_address(topics[1])
        proposer = topic_to_address(topics[2])
        resolver = topic_to_address(topics[3])
        collateral_token = topic_to_address(data_word(log["data"], 0))
        betting_close_time = to_int(data_word(log["data"], 1))
        resolution_window = to_int(data_word(log["data"], 2))
        resolution_deadline = to_int(data_word(log["data"], 3))
        betting_closer = topic_to_address(data_word(log["data"], 4))
        resolution_closer = topic_to_address(data_word(log["data"], 5))
        metadata = {"proposition": "", "outcomes": []}
        if rpc_url:
            metadata = fetch_wager_metadata(rpc_url, wager)

        inserted = insert_event_log(
            conn,
            eid,
            wager,
            event_name,
            block_number,
            tx_hash,
            log_index,
            {
                "wager": wager,
                "proposer": proposer,
                "resolver": resolver,
                "collateralToken": collateral_token,
                "bettingCloseTime": betting_close_time,
                "resolutionWindow": resolution_window,
                "resolutionDeadline": resolution_deadline,
                "bettingCloser": betting_closer,
                "resolutionCloser": resolution_closer,
            },
        )
        if not inserted:
            return

        conn.execute(
            """
            INSERT OR IGNORE INTO wagers(
              wager_address, factory_address, proposer, resolver, betting_closer, resolution_closer,
              collateral_token, proposition, outcomes_json, betting_close_time, resolution_window, resolution_deadline,
              protocol_version, state, created_block, created_tx_hash
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'freeform', 'OPEN', ?, ?)
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
                betting_close_time,
                resolution_window,
                resolution_deadline,
                block_number,
                tx_hash.lower(),
            ),
        )
        conn.execute(
            "INSERT OR IGNORE INTO wager_totals(wager_address, total_pot, total_fee_bps) VALUES (?, '0', '0')",
            (wager,),
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

    if event_name == "BetPlacedV3Enumerated":
        bettor = topic_to_address(topics[1])
        ticket_mask = to_int(data_word(log["data"], 0))
        amount = to_int(data_word(log["data"], 1))
        mask_key = str(ticket_mask)
        payload: Dict[str, Any] = {"bettor": bettor, "ticketMask": ticket_mask, "amount": amount}
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
        conn.execute(
            "UPDATE wager_totals SET total_pot = CAST(total_pot AS INTEGER) + ? WHERE wager_address = ?",
            (amount, wager),
        )
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
        conn.execute(
            "UPDATE wager_totals SET total_pot = CAST(total_pot AS INTEGER) + ? WHERE wager_address = ?",
            (amount, wager),
        )
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
        conn.execute(
            "UPDATE wager_totals SET winning_outcome = ? WHERE wager_address = ?",
            (str(winning_val), wager),
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
        conn.execute(
            "UPDATE wager_totals SET winning_outcome = ? WHERE wager_address = ?",
            (winning_key, wager),
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


def get_expire_candidates(conn: sqlite3.Connection, now_ts: Optional[int] = None) -> List[sqlite3.Row]:
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
) -> List[Dict[str, Any]]:
    """Return logs for [start, end], recursively halving the block span on RPC failure."""
    if start > end:
        return []
    span = end - start + 1
    params = [{"fromBlock": hex(start), "toBlock": hex(end), "topics": topic_filter}]
    try:
        return rpc_call(rpc_url, "eth_getLogs", params)
    except Exception:
        if span <= min_span:
            raise
        mid = start + (span // 2) - 1
        left = _eth_get_logs_bisect(rpc_url, start, mid, topic_filter, min_span)
        right = _eth_get_logs_bisect(rpc_url, mid + 1, end, topic_filter, min_span)
        return left + right


def sync_logs(
    rpc_url: str,
    conn: sqlite3.Connection,
    factory_address: str,
    from_block: Optional[int],
    to_block: Optional[int],
    chunk_size: int,
    *,
    allow_genesis_start: bool = False,
) -> int:
    factory_address = normalize_address(factory_address) if factory_address else ""

    latest = to_int(rpc_call(rpc_url, "eth_blockNumber", []))
    set_meta_int(conn, "chain_head", latest)
    set_meta_str(conn, "last_sync_error", "")
    conn.commit()

    if to_block is None:
        to_block = latest
    to_block = min(to_block, latest)

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
        set_meta_str(
            conn,
            "last_sync_error",
            f"from_block {from_block} is ahead of chain head {to_block} (check INDEXER_FROM_BLOCK / indexerFromBlock)",
        )
        conn.commit()
        return 0

    topic_filter = [list(TOPICS.values())]
    processed = 0

    start = from_block
    while start <= to_block:
        end = min(start + chunk_size - 1, to_block)
        try:
            logs = _eth_get_logs_bisect(rpc_url, start, end, topic_filter, min_span=1)
        except Exception as exc:
            set_meta_str(
                conn,
                "last_sync_error",
                f"eth_getLogs blocks {start}-{end}: {exc}"[:800],
            )
            conn.commit()
            raise
        logs.sort(key=lambda l: (to_int(l["blockNumber"]), to_int(l["logIndex"])))
        for log in logs:
            try:
                apply_log(conn, factory_address, log, rpc_url=rpc_url)
                processed += 1
            except Exception as exc:
                tx = log.get("transactionHash", "?")
                li = log.get("logIndex", "?")
                print(f"[indexer-sync] skip log {tx}:{li}: {exc}")

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
    )
    print(f"Processed logs: {count}")


if __name__ == "__main__":
    main()
