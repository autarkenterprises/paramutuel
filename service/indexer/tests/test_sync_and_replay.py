"""The sync driver: what keeps the index correct when the RPC misbehaves (ADR-0020, AGENTS.md #2).

`sync_logs` replays a chunk after any failure, so applying a log twice must change nothing, or a
flaky provider would double-count stakes. Until now only the local-chain end-to-end test reached this
code, and a healthy local node never fails, so none of these failure paths had ever run.
"""
import contextlib
import io
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from service.indexer import indexer as ix
from service.indexer.api import get_wager
from service.indexer.indexer import (
    FACTORY_TOPIC_FILTER,
    TOPICS,
    apply_log,
    get_expire_candidates,
    get_meta_int,
    get_meta_str,
    init_db,
    set_meta_int,
    sync_logs,
)

FACTORY = "0xfac7000000000000000000000000000000000004"
WAGER = "0xabc1000000000000000000000000000000000001"
PROPOSER = "0xabc2000000000000000000000000000000000002"
RESOLVER = "0xabc3000000000000000000000000000000000003"
TOKEN = "0xabc4000000000000000000000000000000000004"
BETTOR = "0xabc5000000000000000000000000000000000005"
ANSWER_ID = "0x" + "ab" * 32


def topic_addr(addr: str) -> str:
    return "0x" + ("0" * 24) + addr.lower().replace("0x", "")


def word(v: int) -> str:
    return f"{v:064x}"


def word_addr(addr: str) -> str:
    return ("0" * 24) + addr.lower().replace("0x", "")


class Logs:
    """Builds raw logs in chain order: by default each log lands in its own block."""

    def __init__(self, first_block: int = 10) -> None:
        self.next_block = first_block
        self.count = 0

    def make(self, event: str, address: str, *topics: str, data: str = "0x", block: int | None = None) -> dict:
        self.count += 1
        number = self.next_block if block is None else block
        self.next_block = number + 1
        return {
            "address": address,
            "topics": [TOPICS[event], *topics],
            "data": data,
            "blockNumber": hex(number),
            "transactionHash": f"0x{self.count:064x}",
            "logIndex": "0x0",
        }

    def created_enum(self, block: int | None = None) -> dict:
        data = "0x" + word_addr(TOKEN) + word(0) + word(0) + word(2_000) + word(3_000) + word(5_000) + word_addr(RESOLVER) * 2
        return self.make(
            "WagerCreatedV3Enumerated", FACTORY, topic_addr(WAGER), topic_addr(PROPOSER), topic_addr(RESOLVER), data=data, block=block
        )

    def created_freeform(self) -> dict:
        data = "0x" + word_addr(TOKEN) + word(2_000) + word(3_000) + word(5_000) + word_addr(RESOLVER) * 2
        return self.make("WagerCreatedV3Freeform", FACTORY, topic_addr(WAGER), topic_addr(PROPOSER), topic_addr(RESOLVER), data=data)

    def bet_enum(self, mask: int, amount: int, block: int | None = None) -> dict:
        return self.make("BetPlacedV3Enumerated", WAGER, topic_addr(BETTOR), data="0x" + word(mask) + word(amount), block=block)


def enumerated_resolved(logs: Logs) -> list[dict]:
    return [
        logs.created_enum(),
        logs.bet_enum(1, 700),
        logs.bet_enum(2, 300),
        logs.make("BettingClosedByAuthorityV3", WAGER, data="0x" + word(1_500)),
        logs.make("ResolvedV3Enumerated", WAGER, data="0x" + word(1)),
        logs.make("FeeAccruedV3", WAGER, topic_addr(TOKEN), data="0x" + word(10)),
        logs.make("ClaimedV3", WAGER, topic_addr(BETTOR), data="0x" + word(990)),
        logs.make("FeeWithdrawnV3", WAGER, topic_addr(TOKEN), data="0x" + word(10)),
    ]


def freeform_resolved(logs: Logs) -> list[dict]:
    answer = b"Paris"
    revealed = "0x" + word(32) + word(len(answer)) + answer.hex().ljust(64, "0")
    return [
        logs.created_freeform(),
        logs.make("FreeformAnswerRevealedV3", WAGER, ANSWER_ID, data=revealed),
        logs.make("BetPlacedV3Freeform", WAGER, topic_addr(BETTOR), ANSWER_ID, data="0x" + word(400)),
        logs.make("BetPlacedV3Freeform", WAGER, topic_addr(BETTOR), ANSWER_ID, data="0x" + word(600)),
        logs.make("ResolvedV3Freeform", WAGER, ANSWER_ID),
    ]


def retracted(logs: Logs) -> list[dict]:
    return [logs.created_enum(), logs.bet_enum(1, 1_000), logs.make("RetractedV3", WAGER)]


def expired(logs: Logs) -> list[dict]:
    return [
        logs.created_enum(),
        logs.bet_enum(1, 1_000),
        logs.make("ResolutionWindowClosedByAuthorityV3", WAGER, data="0x" + word(1_700)),
        logs.make("ExpiredV3", WAGER),
    ]


def snapshot(conn: sqlite3.Connection) -> dict[str, list[str]]:
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    return {t: sorted(repr(tuple(r)) for r in conn.execute(f"SELECT * FROM {t}")) for t in tables}


class Db(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def pot(self) -> str:
        return self.conn.execute("SELECT total_pot FROM wager_totals WHERE wager_address = ?", (WAGER,)).fetchone()[0]


class ReplayTests(Db):
    def test_applying_every_log_a_second_time_changes_nothing(self) -> None:
        """The whole safety of retrying a chunk rests on this. Each event type has its own guard."""
        for name, build, pot, state in (
            ("enumerated", enumerated_resolved, "1000", "RESOLVED"),
            ("freeform", freeform_resolved, "1000", "RESOLVED"),
            ("retracted", retracted, "1000", "RETRACTED"),
            ("expired", expired, "1000", "RETRACTED"),
        ):
            with self.subTest(name):
                self.tearDown()
                self.setUp()
                logs = build(Logs())
                for log in logs:
                    apply_log(self.conn, FACTORY, log, rpc_url=None)
                self.assertEqual(self.pot(), pot)
                row = self.conn.execute("SELECT state FROM wagers WHERE wager_address = ?", (WAGER,)).fetchone()
                self.assertEqual(row[0], state)
                before = snapshot(self.conn)
                for log in logs:
                    apply_log(self.conn, FACTORY, log, rpc_url=None)
                self.assertEqual(snapshot(self.conn), before)

    def test_replayed_creation_does_not_repeat_its_metadata_calls(self) -> None:
        """Each creation costs several eth_calls per outcome; a retry loop must not repeat them."""
        log = Logs().created_enum()
        with mock.patch.object(ix, "fetch_wager_metadata", return_value=dict(ix._NO_METADATA)) as fetch:
            apply_log(self.conn, FACTORY, log, rpc_url="http://rpc")
            apply_log(self.conn, FACTORY, log, rpc_url="http://rpc")
        self.assertEqual(fetch.call_count, 1)

    def test_logs_without_a_recognised_topic_are_ignored(self) -> None:
        before = snapshot(self.conn)
        common = {"address": WAGER, "data": "0x", "blockNumber": "0x1", "transactionHash": "0x1", "logIndex": "0x0"}
        apply_log(self.conn, FACTORY, {**common, "topics": []}, rpc_url=None)
        apply_log(self.conn, FACTORY, {**common, "topics": ["0x" + "ee" * 32]}, rpc_url=None)
        self.assertEqual(snapshot(self.conn), before)


class AccountingEventTests(Db):
    def test_claim_and_fee_events_reach_the_api_with_exact_amounts(self) -> None:
        """Never read by the unit tests. A JS client would corrupt these amounts if they were numbers."""
        logs = Logs()
        huge = 2**200 + 1
        apply_log(self.conn, FACTORY, logs.created_enum(), rpc_url=None)
        apply_log(self.conn, FACTORY, logs.make("ClaimedV3", WAGER, topic_addr(BETTOR), data="0x" + word(huge)), rpc_url=None)
        apply_log(self.conn, FACTORY, logs.make("FeeAccruedV3", WAGER, topic_addr(TOKEN), data="0x" + word(huge)), rpc_url=None)
        apply_log(self.conn, FACTORY, logs.make("FeeWithdrawnV3", WAGER, topic_addr(TOKEN), data="0x" + word(huge)), rpc_url=None)

        events = {e["event_name"]: e["payload_json"] for e in get_wager(self.conn, WAGER)["events"]}
        self.assertEqual(events["ClaimedV3"], {"bettor": BETTOR, "amount": str(huge)})
        self.assertEqual(events["FeeAccruedV3"], {"recipient": TOKEN, "amount": str(huge)})
        self.assertEqual(events["FeeWithdrawnV3"], {"recipient": TOKEN, "amount": str(huge)})
        self.assertEqual(self.pot(), "0", "claims and fees move money out; they must not touch the pot")

    def test_stake_for_a_wager_with_no_totals_row_is_not_invented(self) -> None:
        ix._add_to_total_pot(self.conn, "0xmissing", 5)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM wager_totals").fetchone()[0], 0)

    def test_expire_candidates_default_to_the_current_time(self) -> None:
        apply_log(self.conn, FACTORY, Logs().created_enum(), rpc_url=None)
        rows = get_expire_candidates(self.conn)  # the test wager's window ended at timestamp 5000
        self.assertEqual([r["wager_address"] for r in rows], [WAGER])


class FakeChain:
    """A JSON-RPC provider: a head, some logs, and a programmable failure rule."""

    def __init__(self, head: int, logs=(), fail=None) -> None:
        self.head = head
        self.logs = list(logs)
        self.fail = fail or (lambda start, end, flt: False)
        self.ranges: list[tuple[int, int]] = []

    def __call__(self, rpc_url: str, method: str, params: list):
        if method == "eth_blockNumber":
            return hex(self.head)
        assert method == "eth_getLogs", method
        flt = params[0]
        start, end = int(flt["fromBlock"], 16), int(flt["toBlock"], 16)
        self.ranges.append((start, end))
        if self.fail(start, end, flt):
            raise RuntimeError("query returned more than 10000 results")
        return [
            log
            for log in self.logs
            if start <= int(log["blockNumber"], 16) <= end
            and log["topics"][0] in flt["topics"][0]
            and log["address"] in flt["address"]
        ]


class SyncTests(Db):
    def setUp(self) -> None:
        super().setUp()
        patcher = mock.patch.object(ix, "fetch_wager_metadata", return_value=dict(ix._NO_METADATA))
        patcher.start()
        self.addCleanup(patcher.stop)

    def sync(self, chain: FakeChain, *, from_block=None, to_block=None, chunk_size=5, **kw) -> int:
        with mock.patch.object(ix, "rpc_call", chain):
            return sync_logs("http://rpc", self.conn, FACTORY, from_block, to_block, chunk_size, **kw)

    def test_resumes_just_after_the_cursor_in_consecutive_chunks(self) -> None:
        set_meta_int(self.conn, "last_indexed_block", 100)
        chain = FakeChain(head=112)
        self.sync(chain)
        self.assertEqual(chain.ranges, [(101, 105), (106, 110), (111, 112)])
        self.assertEqual(get_meta_int(self.conn, "last_indexed_block"), 112)

    def test_a_long_running_sync_needs_a_start_block(self) -> None:
        """Starting at block 0 by accident would burn the RPC quota on a chain's whole history."""
        chain = FakeChain(head=3)
        with self.assertRaisesRegex(RuntimeError, "INDEXER_FROM_BLOCK"):
            self.sync(chain)
        self.assertEqual(chain.ranges, [])

    def test_the_one_shot_cli_may_start_at_genesis(self) -> None:
        chain = FakeChain(head=3)
        self.sync(chain, allow_genesis_start=True)
        self.assertEqual(chain.ranges[0][0], 0)

    def test_a_failed_chunk_keeps_earlier_work_reports_the_error_and_recovers(self) -> None:
        logs = Logs()
        chain = FakeChain(
            head=110,
            logs=[logs.created_enum(block=101), logs.bet_enum(1, 5, block=103), logs.bet_enum(1, 7, block=107)],
            fail=lambda start, end, flt: start <= 107 <= end,
        )
        with self.assertRaises(RuntimeError):
            self.sync(chain, from_block=101)
        self.assertEqual(get_meta_int(self.conn, "last_indexed_block"), 105, "the good chunk is kept")
        self.assertEqual(self.pot(), "5")
        self.assertIn("blocks 106-110", get_meta_str(self.conn, "last_sync_error"))

        chain.fail = lambda start, end, flt: False
        self.sync(chain)
        self.assertEqual(self.pot(), "12", "each stake counted exactly once")
        self.assertEqual(get_meta_int(self.conn, "last_indexed_block"), 110)
        self.assertEqual(get_meta_str(self.conn, "last_sync_error"), "", "a recovered sync clears the error")

    def test_a_failure_part_way_through_a_chunk_replays_it_safely(self) -> None:
        """The factory query succeeds, then the wager query fails. The next pass repeats the creation."""
        logs = Logs()
        trip = {"armed": True}

        def fail(start, end, flt):
            is_wager_query = WAGER in flt["address"]
            return is_wager_query and trip["armed"]

        chain = FakeChain(head=102, logs=[logs.created_enum(block=101), logs.bet_enum(1, 5, block=102)], fail=fail)
        with self.assertRaises(RuntimeError):
            self.sync(chain, from_block=101)
        self.assertIsNone(get_meta_int(self.conn, "last_indexed_block"), "the cursor must not pass unread logs")
        self.assertEqual(self.pot(), "0")

        trip["armed"] = False
        self.sync(chain, from_block=101)
        self.assertEqual(self.pot(), "5")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM wagers").fetchone()[0], 1)

    def test_bisection_recovers_every_log_when_a_provider_rejects_wide_ranges(self) -> None:
        """Providers refuse big answers with no hint at the limit, so the range is split until it works."""
        logs = Logs()
        entries = [logs.created_enum(block=101)] + [logs.bet_enum(1, 10, block=b) for b in range(102, 109)]
        chain = FakeChain(head=108, logs=entries, fail=lambda start, end, flt: end - start + 1 > 2)
        self.sync(chain, from_block=101, chunk_size=8)
        self.assertEqual(self.pot(), "70")
        self.assertEqual(get_meta_int(self.conn, "last_indexed_block"), 108)
        self.assertIn((101, 108), chain.ranges, "it tried the whole range first")

    def test_one_block_that_always_fails_is_surfaced_not_skipped(self) -> None:
        chain = FakeChain(head=10, fail=lambda start, end, flt: start <= 6 <= end)
        with mock.patch.object(ix, "rpc_call", chain), self.assertRaises(RuntimeError):
            ix._eth_get_logs_bisect("http://rpc", 5, 8, FACTORY_TOPIC_FILTER, min_span=1, address=[FACTORY])
        self.assertIn((6, 6), chain.ranges)

    def test_an_empty_range_asks_the_provider_nothing(self) -> None:
        chain = FakeChain(head=10)
        with mock.patch.object(ix, "rpc_call", chain):
            self.assertEqual(ix._eth_get_logs_bisect("http://rpc", 9, 8, FACTORY_TOPIC_FILTER, min_span=1), [])
        self.assertEqual(chain.ranges, [])


class RpcStub(BaseHTTPRequestHandler):
    reply: dict = {}
    seen: list = []

    def log_message(self, *a) -> None:
        pass

    def do_POST(self) -> None:  # noqa: N802
        body = self.rfile.read(int(self.headers["Content-Length"]))
        type(self).seen.append((self.headers.get("User-Agent"), json.loads(body)))
        payload = json.dumps(type(self).reply).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class RpcCallTests(unittest.TestCase):
    def setUp(self) -> None:
        RpcStub.seen = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), RpcStub)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def test_sends_a_json_rpc_request_with_a_user_agent(self) -> None:
        """The public Base Sepolia RPC rejects urllib's default user agent."""
        RpcStub.reply = {"jsonrpc": "2.0", "id": 1, "result": "0x10"}
        self.assertEqual(ix.rpc_call(self.url, "eth_blockNumber", []), "0x10")
        agent, body = RpcStub.seen[0]
        self.assertEqual(agent, "paramutuel-indexer/1.0")
        self.assertEqual((body["method"], body["params"], body["jsonrpc"]), ("eth_blockNumber", [], "2.0"))

    def test_an_error_response_raises_with_the_detail(self) -> None:
        RpcStub.reply = {"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "limit exceeded"}}
        with self.assertRaisesRegex(RuntimeError, "limit exceeded"):
            ix.rpc_call(self.url, "eth_getLogs", [{}])


class AbiDecodingTests(unittest.TestCase):
    def test_short_uint_response_is_an_error(self) -> None:
        with self.assertRaises(ValueError):
            ix._decode_u256_word("0x12")

    def test_truncated_dynamic_bytes_are_an_error(self) -> None:
        """A silently short answer would hash to a different id than the one on-chain."""
        with self.assertRaises(ValueError):
            ix._decode_abi_bytes("0x" + word(32) + word(5) + "aabb")

    def test_malformed_string_responses_read_as_empty(self) -> None:
        """A half-deployed wager must not crash enrichment. The retry path picks up the real value."""
        self.assertEqual(ix._decode_abi_string("0x"), "")
        self.assertEqual(ix._decode_abi_string("0x" + word(9_999) + word(0)), "", "offset past the end")
        self.assertEqual(ix._decode_abi_string("0x" + word(32) + word(9_999)), "", "length past the end")


class IndexerCliTests(unittest.TestCase):
    def test_one_shot_sync_writes_the_database(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "i.db")
            chain = FakeChain(head=6, logs=[Logs().created_enum(block=5)])
            argv = ["indexer", "--rpc-url", "http://rpc", "--factory-address", FACTORY, "--db-path", db_path, "--confirmations", "0"]
            out = io.StringIO()
            with (
                mock.patch.object(ix, "rpc_call", chain),
                mock.patch.object(ix, "fetch_wager_metadata", return_value=dict(ix._NO_METADATA)),
                mock.patch("sys.argv", argv),
                contextlib.redirect_stdout(out),
            ):
                ix.main()
            self.assertIn("Processed logs: 1", out.getvalue())
            self.assertEqual(chain.ranges[0][0], 0, "the CLI may start from genesis")
            conn = sqlite3.connect(db_path)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM wagers").fetchone()[0], 1)
            conn.close()


if __name__ == "__main__":
    unittest.main()
