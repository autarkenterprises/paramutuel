#!/usr/bin/env python3
import argparse
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import request

TOPICS = {
    "MarketCreated": "0x142b571a3c036b6753710f2ec81868c8ee6e9b3fffc642f94783cf8778ea7388",
    "BettingClosedByAuthority": "0xee66a0cc21397ffefe70cadd94333bb96aa93548aaf0d7680d09ee50a5112898",
    "ResolutionWindowClosedByAuthority": "0x3a016249126bba7044eec394afa8eba111d1ea6bda5a42b663f7d86944fd1f87",
    "BetPlaced": "0x001ecf1d0c4d22f324b3ecb9cdf0e5f772bc74ac104e6626f4b3845433d03105",
    "Resolved": "0x148a25ee2a7671350ab878ff183447de8ae5afa2ee0ae7d5ee1ad6b25c4868c2",
    "Retracted": "0x6c8d8af1eb7d9e8ea2f489b8d39cc78f924042413d0e15ce70f8cdb53afab46a",
    "Expired": "0x203d82d8d99f63bfecc8335216735e0271df4249ea752b030f9ab305b94e5afe",
    "Claimed": "0xd8138f8a3f377c5259ca548e70e4c2de94f129f5a11036a15b69513cba2b426a",
    "FeeAccrued": "0x5c0ce1b1916761250fab78a3ec6e398bbaabd1537003983889748c0c1e5644e3",
    "FeeWithdrawn": "0x78473f3f373f7673597f4f0fa5873cb4d375fea6d4339ad6b56dbd411513cb3f",
}

TOPIC_TO_EVENT = {v: k for k, v in TOPICS.items()}


def db_connect(path: str) -> sqlite3.Connection:
    # API server uses ThreadingHTTPServer; allow sqlite connection across handler threads.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    schema = Path(__file__).with_name("schema.sql").read_text()
    conn.executescript(schema)
    conn.commit()


def rpc_call(rpc_url: str, method: str, params: List[Any]) -> Any:
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = request.Request(rpc_url, data=payload, headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode())
    if "error" in body:
        raise RuntimeError(f"RPC error: {body['error']}")
    return body["result"]


def to_int(hex_value: str) -> int:
    return int(hex_value, 16)


def normalize_address(addr: str) -> str:
    return "0x" + addr.lower().replace("0x", "")[-40:]


def topic_to_address(topic_word: str) -> str:
    return normalize_address(topic_word)


def data_word(data_hex: str, idx: int) -> str:
    # data is 0x + N*64 hex chars
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


def insert_event_log(
    conn: sqlite3.Connection,
    eid: str,
    market_address: Optional[str],
    event_name: str,
    block_number: int,
    tx_hash: str,
    log_index: int,
    payload: Dict[str, Any],
) -> bool:
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO events_log(event_id, market_address, event_name, block_number, tx_hash, log_index, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (eid, market_address, event_name, block_number, tx_hash.lower(), log_index, json.dumps(payload)),
    )
    return cur.rowcount == 1


def apply_log(conn: sqlite3.Connection, factory_address: str, log: Dict[str, Any]) -> None:
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

    # MARKET CREATED (from factory only)
    if event_name == "MarketCreated":
        if address != factory_address:
            return
        market = topic_to_address(topics[1])
        proposer = topic_to_address(topics[2])
        resolver = topic_to_address(topics[3])
        collateral_token = topic_to_address(data_word(log["data"], 0))
        betting_close_time = to_int(data_word(log["data"], 1))
        resolution_window = to_int(data_word(log["data"], 2))
        resolution_deadline = to_int(data_word(log["data"], 3))
        betting_closer = topic_to_address(data_word(log["data"], 4))
        resolution_closer = topic_to_address(data_word(log["data"], 5))

        inserted = insert_event_log(
            conn,
            eid,
            market,
            event_name,
            block_number,
            tx_hash,
            log_index,
            {
                "market": market,
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
            INSERT OR IGNORE INTO markets(
              market_address, factory_address, proposer, resolver, betting_closer, resolution_closer,
              collateral_token, betting_close_time, resolution_window, resolution_deadline, state, created_block, created_tx_hash
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?)
            """,
            (
                market,
                factory_address,
                proposer,
                resolver,
                betting_closer,
                resolution_closer,
                collateral_token,
                betting_close_time,
                resolution_window,
                resolution_deadline,
                block_number,
                tx_hash.lower(),
            ),
        )
        conn.execute(
            "INSERT OR IGNORE INTO market_totals(market_address, total_pot, total_fee_bps) VALUES (?, '0', '0')",
            (market,),
        )
        return

    # all other events are emitted by market contracts
    market = address
    if not conn.execute("SELECT 1 FROM markets WHERE market_address = ?", (market,)).fetchone():
        # Skip orphan logs; indexer expects MarketCreated first.
        return

    if event_name == "BettingClosedByAuthority":
        closed_at = to_int(data_word(log["data"], 0))
        inserted = insert_event_log(
            conn, eid, market, event_name, block_number, tx_hash, log_index, {"closedAt": closed_at}
        )
        if not inserted:
            return
        conn.execute(
            "UPDATE markets SET betting_closed_by_authority = 1, betting_closed_at = ? WHERE market_address = ?",
            (closed_at, market),
        )
        return

    if event_name == "ResolutionWindowClosedByAuthority":
        closed_at = to_int(data_word(log["data"], 0))
        inserted = insert_event_log(
            conn, eid, market, event_name, block_number, tx_hash, log_index, {"closedAt": closed_at}
        )
        if not inserted:
            return
        conn.execute(
            "UPDATE markets SET resolution_window_closed = 1, resolution_window_closed_at = ? WHERE market_address = ?",
            (closed_at, market),
        )
        return

    if event_name == "BetPlaced":
        bettor = topic_to_address(topics[1])
        outcome_index = to_int(topics[2])
        amount = to_int(data_word(log["data"], 0))
        inserted = insert_event_log(
            conn,
            eid,
            market,
            event_name,
            block_number,
            tx_hash,
            log_index,
            {"bettor": bettor, "outcomeIndex": outcome_index, "amount": amount},
        )
        if not inserted:
            return
        conn.execute(
            "INSERT OR IGNORE INTO market_outcomes(market_address, outcome_index, outcome_total) VALUES (?, ?, '0')",
            (market, outcome_index),
        )
        conn.execute(
            "UPDATE market_outcomes SET outcome_total = CAST(outcome_total AS INTEGER) + ? WHERE market_address = ? AND outcome_index = ?",
            (amount, market, outcome_index),
        )
        conn.execute(
            "UPDATE market_totals SET total_pot = CAST(total_pot AS INTEGER) + ? WHERE market_address = ?",
            (amount, market),
        )
        return

    if event_name == "Resolved":
        outcome_index = to_int(topics[1])
        inserted = insert_event_log(
            conn,
            eid,
            market,
            event_name,
            block_number,
            tx_hash,
            log_index,
            {"outcomeIndex": outcome_index},
        )
        if not inserted:
            return
        conn.execute("UPDATE markets SET state = 'RESOLVED' WHERE market_address = ?", (market,))
        conn.execute("UPDATE market_totals SET winning_outcome = ? WHERE market_address = ?", (str(outcome_index), market))
        return

    if event_name in ("Retracted", "Expired"):
        inserted = insert_event_log(
            conn, eid, market, event_name, block_number, tx_hash, log_index, {}
        )
        if not inserted:
            return
        conn.execute("UPDATE markets SET state = 'RETRACTED' WHERE market_address = ?", (market,))
        return

    if event_name == "Claimed":
        bettor = topic_to_address(topics[1])
        amount = to_int(data_word(log["data"], 0))
        insert_event_log(
            conn,
            eid,
            market,
            event_name,
            block_number,
            tx_hash,
            log_index,
            {"bettor": bettor, "amount": amount},
        )
        return

    if event_name in ("FeeAccrued", "FeeWithdrawn"):
        recipient = topic_to_address(topics[1])
        amount = to_int(data_word(log["data"], 0))
        insert_event_log(
            conn,
            eid,
            market,
            event_name,
            block_number,
            tx_hash,
            log_index,
            {"recipient": recipient, "amount": amount},
        )
        return


def get_expire_candidates(conn: sqlite3.Connection, now_ts: Optional[int] = None) -> List[sqlite3.Row]:
    if now_ts is None:
        now_ts = int(time.time())
    return conn.execute(
        """
        SELECT market_address, resolver, resolution_window, resolution_deadline, betting_closed_at, resolution_window_closed
        FROM markets
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


def sync_logs(
    rpc_url: str,
    conn: sqlite3.Connection,
    factory_address: str,
    from_block: Optional[int],
    to_block: Optional[int],
    chunk_size: int,
) -> int:
    factory_address = normalize_address(factory_address)

    latest = to_int(rpc_call(rpc_url, "eth_blockNumber", []))
    if to_block is None:
        to_block = latest
    to_block = min(to_block, latest)

    if from_block is None:
        last_indexed = get_meta_int(conn, "last_indexed_block")
        from_block = (last_indexed + 1) if last_indexed is not None else 0
    if from_block > to_block:
        return 0

    topic_filter = [list(TOPICS.values())]
    processed = 0

    start = from_block
    while start <= to_block:
        end = min(start + chunk_size - 1, to_block)
        params = [
            {
                "fromBlock": hex(start),
                "toBlock": hex(end),
                "topics": topic_filter,
            }
        ]
        logs = rpc_call(rpc_url, "eth_getLogs", params)
        logs.sort(key=lambda l: (to_int(l["blockNumber"]), to_int(l["logIndex"])))
        for log in logs:
            apply_log(conn, factory_address, log)
            processed += 1

        set_meta_int(conn, "last_indexed_block", end)
        conn.commit()
        start = end + 1

    return processed


def main() -> None:
    parser = argparse.ArgumentParser(description="Minimal Paramutuel indexer")
    parser.add_argument("--rpc-url", required=True)
    parser.add_argument("--db-path", default="service/indexer/indexer.db")
    parser.add_argument("--factory-address", required=True)
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
    )
    print(f"Processed logs: {count}")


if __name__ == "__main__":
    main()

