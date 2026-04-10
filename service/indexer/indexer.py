#!/usr/bin/env python3
import argparse
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import request

TOPICS = {
    # keccak256("WagerCreated(address,address,address,address,uint64,uint64,uint64,address,address)")
    "WagerCreated": "0x1b9545daed972e7de65f9c8b3445fdfd1af0c41cdc5774595c37bc7e35f28def",
    # keccak256("WagerCreatedV2(address,address,address,address,uint8,uint256,uint64,uint64,uint64,address,address)")
    "WagerCreatedV2": "0x7245d6cca974fb4447fd236c460f3aa281da5ffa682c9b5392e99c37bb3ca89a",
    # cast sig-event "WagerCreatedFreeform(address,address,address,address,uint64,uint64,uint64,address,address)"
    "WagerCreatedFreeform": "0x60df4ecdea5ae023d85c252f83dc6af864416587f18faf8390628be794f4591f",
    # cast sig-event "BetPlacedFreeform(address,bytes32,uint256)"
    "BetPlacedFreeform": "0xb4f2b7294a555732d5c73cc34940c46431b31aad34a947d1b6210a5cc5d1e6d5",
    # cast sig-event "ResolvedFreeform(bytes32)"
    "ResolvedFreeform": "0x9b6a781a3f554541bb561aebff6265bd272889b31a17ffc0cff68b587f1023f9",
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

# Mirrors `ParamutuelFactory` / `ParamutuelFactoryV2` `MAX_OUTCOMES` on-chain.
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
    _migrate_db(conn)
    conn.commit()


def _migrate_db(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(wagers)").fetchall()
    }
    if "proposition" not in columns:
        conn.execute("ALTER TABLE wagers ADD COLUMN proposition TEXT NOT NULL DEFAULT ''")
    if "outcomes_json" not in columns:
        conn.execute("ALTER TABLE wagers ADD COLUMN outcomes_json TEXT NOT NULL DEFAULT '[]'")
    if "protocol_version" not in columns:
        conn.execute("ALTER TABLE wagers ADD COLUMN protocol_version TEXT NOT NULL DEFAULT 'v1'")
    if "payoff_policy" not in columns:
        conn.execute("ALTER TABLE wagers ADD COLUMN payoff_policy INTEGER")
    if "policy_param" not in columns:
        conn.execute("ALTER TABLE wagers ADD COLUMN policy_param TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_wagers_proposition ON wagers(proposition)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS wager_ticket_pools (
          wager_address TEXT NOT NULL,
          ticket_mask TEXT NOT NULL,
          pool_total TEXT NOT NULL DEFAULT '0',
          PRIMARY KEY (wager_address, ticket_mask),
          FOREIGN KEY(wager_address) REFERENCES wagers(wager_address)
        )
        """
    )


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
        # Hard safety cap mirrors protocol-level max outcomes.
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
    factory_v1: str,
    factory_v2: str,
    log: Dict[str, Any],
    rpc_url: Optional[str] = None,
    factory_freeform: str = "",
) -> None:
    fac1 = normalize_address(factory_v1) if factory_v1 else ""
    fac2 = normalize_address(factory_v2) if factory_v2 else ""
    fac3 = normalize_address(factory_freeform) if factory_freeform else ""
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

    # WAGER CREATED v1 (from ParamutuelFactory only)
    if event_name == "WagerCreated":
        if not fac1 or address != fac1:
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'v1', 'OPEN', ?, ?)
            """,
            (
                wager,
                fac1,
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

    # WAGER CREATED v2 (from ParamutuelFactoryV2 only)
    if event_name == "WagerCreatedV2":
        if not fac2 or address != fac2:
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'v2', ?, ?, 'OPEN', ?, ?)
            """,
            (
                wager,
                fac2,
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

    # WAGER CREATED freeform (ParamutuelFactoryFreeform only)
    if event_name == "WagerCreatedFreeform":
        if not fac3 or address != fac3:
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
                fac3,
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

    # all other events are emitted by wager contracts
    wager = address
    if not conn.execute("SELECT 1 FROM wagers WHERE wager_address = ?", (wager,)).fetchone():
        # Skip orphan logs; indexer expects WagerCreated first.
        return

    if event_name == "BettingClosedByAuthority":
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

    if event_name == "ResolutionWindowClosedByAuthority":
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

    if event_name == "BetPlacedFreeform":
        bettor = topic_to_address(topics[1])
        answer_id_key = topics[2].lower()
        amount = to_int(data_word(log["data"], 0))
        payload_bf: Dict[str, Any] = {
            "bettor": bettor,
            "answerId": answer_id_key,
            "amount": amount,
        }
        inserted = insert_event_log(
            conn, eid, wager, event_name, block_number, tx_hash, log_index, payload_bf
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

    if event_name == "BetPlaced":
        bettor = topic_to_address(topics[1])
        # v1: BetPlaced(bettor indexed, outcomeIndex indexed, amount) — 3 topics
        # v2: BetPlaced(bettor indexed, ticketMask, amount) — 2 topics
        if len(topics) >= 3:
            outcome_index = to_int(topics[2])
            amount = to_int(data_word(log["data"], 0))
            payload_bet: Dict[str, Any] = {"bettor": bettor, "outcomeIndex": outcome_index, "amount": amount}
            inserted = insert_event_log(
                conn, eid, wager, event_name, block_number, tx_hash, log_index, payload_bet
            )
            if not inserted:
                return
            conn.execute(
                "INSERT OR IGNORE INTO wager_outcomes(wager_address, outcome_index, outcome_total) VALUES (?, ?, '0')",
                (wager, outcome_index),
            )
            conn.execute(
                "UPDATE wager_outcomes SET outcome_total = CAST(outcome_total AS INTEGER) + ? WHERE wager_address = ? AND outcome_index = ?",
                (amount, wager, outcome_index),
            )
        else:
            ticket_mask = to_int(data_word(log["data"], 0))
            amount = to_int(data_word(log["data"], 1))
            mask_key = str(ticket_mask)
            payload_bet = {"bettor": bettor, "ticketMask": ticket_mask, "amount": amount}
            inserted = insert_event_log(
                conn, eid, wager, event_name, block_number, tx_hash, log_index, payload_bet
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

    if event_name == "ResolvedFreeform":
        winning_key = topics[1].lower()
        res_payload_ff: Dict[str, Any] = {"winningAnswerId": winning_key, "layout": "freeform"}
        inserted = insert_event_log(
            conn,
            eid,
            wager,
            event_name,
            block_number,
            tx_hash,
            log_index,
            res_payload_ff,
        )
        if not inserted:
            return
        conn.execute("UPDATE wagers SET state = 'RESOLVED' WHERE wager_address = ?", (wager,))
        conn.execute(
            "UPDATE wager_totals SET winning_outcome = ? WHERE wager_address = ?",
            (winning_key, wager),
        )
        return

    if event_name == "Resolved":
        # v1: winning outcome in indexed topic; v2: winningMask non-indexed in data
        if len(topics) >= 2:
            winning_val = to_int(topics[1])
            res_payload: Dict[str, Any] = {"outcomeIndex": winning_val, "layout": "v1_indexed"}
        else:
            winning_val = to_int(data_word(log["data"], 0))
            res_payload = {"winningMask": winning_val, "layout": "v2_data"}
        inserted = insert_event_log(
            conn,
            eid,
            wager,
            event_name,
            block_number,
            tx_hash,
            log_index,
            res_payload,
        )
        if not inserted:
            return
        conn.execute("UPDATE wagers SET state = 'RESOLVED' WHERE wager_address = ?", (wager,))
        conn.execute("UPDATE wager_totals SET winning_outcome = ? WHERE wager_address = ?", (str(winning_val), wager))
        return

    if event_name in ("Retracted", "Expired"):
        inserted = insert_event_log(
            conn, eid, wager, event_name, block_number, tx_hash, log_index, {}
        )
        if not inserted:
            return
        conn.execute("UPDATE wagers SET state = 'RETRACTED' WHERE wager_address = ?", (wager,))
        return

    if event_name == "Claimed":
        bettor = topic_to_address(topics[1])
        amount = to_int(data_word(log["data"], 0))
        insert_event_log(
            conn,
            eid,
            wager,
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
            wager,
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
    """Return logs for [start, end], recursively halving the block span on RPC failure.

    Public RPCs (e.g. Base Sepolia) sometimes respond with HTTP 400 for wide getLogs
    windows even when smaller ranges succeed.
    """
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
    factory_v2_address: str = "",
    factory_freeform_address: str = "",
    allow_genesis_start: bool = False,
) -> int:
    factory_address = normalize_address(factory_address)
    factory_v2_norm = normalize_address(factory_v2_address) if factory_v2_address else ""
    factory_ff_norm = normalize_address(factory_freeform_address) if factory_freeform_address else ""

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
                apply_log(
                    conn,
                    factory_address,
                    factory_v2_norm,
                    log,
                    rpc_url=rpc_url,
                    factory_freeform=factory_ff_norm,
                )
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
    parser = argparse.ArgumentParser(description="Minimal Paramutuel indexer")
    parser.add_argument("--rpc-url", required=True)
    parser.add_argument("--db-path", default="service/indexer/indexer.db")
    parser.add_argument("--factory-address", required=True, help="ParamutuelFactory (v1) address")
    parser.add_argument("--factory-v2-address", default="", help="ParamutuelFactoryV2 address (optional)")
    parser.add_argument(
        "--factory-freeform-address",
        default="",
        help="ParamutuelFactoryFreeform address (optional, ADR-0009)",
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
        factory_v2_address=args.factory_v2_address,
        factory_freeform_address=args.factory_freeform_address,
        allow_genesis_start=True,
    )
    print(f"Processed logs: {count}")


if __name__ == "__main__":
    main()

