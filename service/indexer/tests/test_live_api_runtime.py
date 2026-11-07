"""The hosted indexer process: configuration, the background sync loop, and startup (ADR-0020).

This is what runs on Cloud Run, and it was 23% covered. Its start block, confirmations and factory
all arrive through this code, so a wiring slip here means a silently empty or wrong index.
"""
import contextlib
import io
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from service.indexer import live_api
from service.indexer.indexer import init_db, set_meta_int

FACTORY = "0xfac7000000000000000000000000000000000004"
OTHER = "0x00000000000000000000000000000000000000aa"


class ConfigFile(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "deployments.json"

    def write(self, text: str) -> str:
        self.path.write_text(text, encoding="utf-8")
        return str(self.path)


class FromBlockConfigTests(ConfigFile):
    def test_reads_the_entry_for_the_network_alias(self) -> None:
        path = self.write(json.dumps({"baseSepolia": {"indexerFromBlock": 123}, "baseMainnet": {"indexerFromBlock": 456}}))
        self.assertEqual(live_api._indexer_from_block_from_config(path, "base-sepolia"), 123)
        self.assertEqual(live_api._indexer_from_block_from_config(path, "base"), 456)

    def test_accepts_a_numeric_string(self) -> None:
        path = self.write(json.dumps({"baseSepolia": {"indexerFromBlock": "789"}}))
        self.assertEqual(live_api._indexer_from_block_from_config(path, "base-sepolia"), 789)

    def test_anything_unusable_means_not_configured(self) -> None:
        self.assertIsNone(live_api._indexer_from_block_from_config(str(self.path), "base-sepolia"), "no file")
        self.assertIsNone(live_api._indexer_from_block_from_config(self.write("{nope"), "base-sepolia"), "bad JSON")
        for value in ('""', "null"):
            path = self.write('{"baseSepolia": {"indexerFromBlock": %s}}' % value)
            self.assertIsNone(live_api._indexer_from_block_from_config(path, "base-sepolia"), value)
        self.assertIsNone(live_api._indexer_from_block_from_config(self.write("{}"), "base-sepolia"), "no network entry")


class FactoryResolutionTests(ConfigFile):
    def test_missing_or_bad_config_is_empty(self) -> None:
        self.assertEqual(live_api._factory_from_config(str(self.path), "base-sepolia"), "")
        self.assertEqual(live_api._factory_from_config(self.write("{nope"), "base-sepolia"), "")

    def test_precedence_is_argument_then_environment_then_config(self) -> None:
        path = self.write(json.dumps({"baseSepolia": {"factoryAddress": FACTORY.upper().replace("0X", "0x")}}))
        with mock.patch.dict(os.environ, {"FACTORY_ADDRESS": OTHER}, clear=True):
            self.assertEqual(live_api._resolve_factory_address("0x" + "bb" * 20, "base-sepolia", path), "0x" + "bb" * 20)
            self.assertEqual(live_api._resolve_factory_address("", "base-sepolia", path), OTHER)
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(live_api._resolve_factory_address("", "base-sepolia", path), FACTORY, "normalized to lower case")
            self.assertEqual(live_api._resolve_factory_address("", "base", path), "", "no entry for that network")


class RpcAndIntResolutionTests(unittest.TestCase):
    def test_rpc_precedence(self) -> None:
        env = {"RPC_URL_BASE_SEPOLIA": "http://a", "RPC_URL_SEPOLIA": "http://b", "RPC_URL": "http://c"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(live_api._resolve_rpc_url("http://explicit"), "http://explicit")
            self.assertEqual(live_api._resolve_rpc_url(""), "http://a")
        with mock.patch.dict(os.environ, {"RPC_URL": "http://c"}, clear=True):
            self.assertEqual(live_api._resolve_rpc_url(""), "http://c")

    def test_no_rpc_is_a_clear_error(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(RuntimeError, "RPC URL is required"):
            live_api._resolve_rpc_url("")

    def test_int_environment_helpers(self) -> None:
        with mock.patch.dict(os.environ, {"N": " 42 ", "EMPTY": "  "}, clear=True):
            self.assertEqual(live_api._resolve_int_env("N", 1), 42)
            self.assertEqual(live_api._resolve_int_env("EMPTY", 1), 1)
            self.assertEqual(live_api._resolve_int_env("ABSENT", 1), 1)
            self.assertEqual(live_api._resolve_optional_int_env("N"), 42)
            self.assertIsNone(live_api._resolve_optional_int_env("EMPTY"))


class TicksThenStops:
    """A stop event that lets the loop run a set number of times without really waiting."""

    def __init__(self, ticks: int) -> None:
        self.ticks = ticks
        self.waits: list[int] = []

    def is_set(self) -> bool:
        return self.ticks <= 0

    def wait(self, seconds: int) -> None:
        self.waits.append(seconds)
        self.ticks -= 1


class SyncLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.addCleanup(self.conn.close)
        init_db(self.conn)

    def run_loop(self, sync, ticks=2, poll=0):
        stop = TicksThenStops(ticks)
        out = io.StringIO()
        with mock.patch.object(live_api, "sync_logs", sync), contextlib.redirect_stdout(out):
            live_api._sync_loop(stop, "http://rpc", self.conn, FACTORY, poll, 10, 123, confirmations=7)
        return stop, out.getvalue()

    def test_uses_the_start_block_once_then_the_cursor(self) -> None:
        calls = []

        def sync(**kw):
            calls.append(kw)
            set_meta_int(self.conn, "last_indexed_block", 500)
            return 3

        stop, out = self.run_loop(sync)
        self.assertEqual([c["from_block"] for c in calls], [123, None])
        self.assertEqual(calls[0]["confirmations"], 7)
        self.assertEqual(calls[0]["chunk_size"], 10)
        self.assertEqual(calls[0]["factory_address"], FACTORY)
        self.assertEqual(stop.waits, [1, 1], "a zero poll interval must not spin")
        self.assertIn("processed logs: 3", out)

    def test_a_failure_does_not_kill_the_loop(self) -> None:
        """An RPC outage would otherwise leave the API serving ever-staler data until redeployed."""
        calls = []

        def sync(**kw):
            calls.append(kw)
            if len(calls) == 1:
                raise RuntimeError("rpc down")
            return 0

        _, out = self.run_loop(sync, poll=9)
        self.assertEqual(len(calls), 2)
        self.assertIn("rpc down", out)
        self.assertNotIn("processed logs", out)


class FakeServer:
    """Stands in for the HTTP server so `main` can run to completion."""

    served = threading.Event()
    synced = threading.Event()

    def __init__(self, address, handler) -> None:
        self.address = address

    def serve_forever(self) -> None:
        # Hold "serving" until the background sync has really run.
        FakeServer.synced.wait(timeout=10)
        FakeServer.served.set()


class MainTests(ConfigFile):
    def setUp(self) -> None:
        super().setUp()
        FakeServer.served.clear()
        FakeServer.synced.clear()
        self.db_path = str(Path(self.tmp.name) / "i.db")
        self.addCleanup(self._reset_handler)

    def _reset_handler(self) -> None:
        live_api.Handler.conn = None
        live_api.Handler.indexer_factory_address = None

    def main(self, *argv: str, env: dict | None = None, sync=None) -> None:
        full = ["live_api", "--db-path", self.db_path, *argv]
        with (
            mock.patch.dict(os.environ, env or {}, clear=True),
            mock.patch("sys.argv", full),
            mock.patch.object(live_api, "ThreadingHTTPServer", FakeServer),
            mock.patch.object(live_api, "sync_logs", sync or mock.Mock(return_value=0)),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            live_api.main()

    def test_refuses_to_start_without_an_rpc_url(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "RPC URL is required"):
            self.main("--deployments-config-path", str(self.path))

    def test_refuses_to_start_without_a_factory(self) -> None:
        path = self.write("{}")
        with self.assertRaisesRegex(RuntimeError, "(?i)factory"):
            self.main("--rpc-url", "http://rpc", "--deployments-config-path", path)

    def test_refuses_to_start_without_a_start_block(self) -> None:
        """Starting from block 0 would burn the RPC quota on the whole chain's history."""
        path = self.write(json.dumps({"baseSepolia": {"factoryAddress": FACTORY}}))
        with self.assertRaisesRegex(RuntimeError, "(?i)from.?block"):
            self.main("--rpc-url", "http://rpc", "--deployments-config-path", path)

    def _capturing_sync(self):
        calls = []

        def sync(**kw):
            calls.append(kw)
            FakeServer.synced.set()
            return 0

        return calls, sync

    def test_config_reaches_the_sync_loop_and_the_health_route(self) -> None:
        path = self.write(json.dumps({"baseSepolia": {"factoryAddress": FACTORY, "indexerFromBlock": 77}}))
        calls, sync = self._capturing_sync()
        self.main("--deployments-config-path", path, env={"RPC_URL": "http://rpc"}, sync=sync)
        self.assertEqual(calls[0]["rpc_url"], "http://rpc")
        self.assertEqual(calls[0]["factory_address"], FACTORY)
        self.assertEqual(calls[0]["from_block"], 77)
        self.assertEqual(calls[0]["confirmations"], 5, "reorg protection is on by default")
        self.assertEqual(live_api.Handler.indexer_factory_address, FACTORY)
        self.assertTrue(FakeServer.served.is_set())

    def test_environment_overrides_confirmations_and_start_block(self) -> None:
        path = self.write(json.dumps({"baseSepolia": {"factoryAddress": FACTORY, "indexerFromBlock": 77}}))
        calls, sync = self._capturing_sync()
        env = {"RPC_URL": "http://rpc", "INDEXER_CONFIRMATIONS": "12", "INDEXER_FROM_BLOCK": "99"}
        self.main("--deployments-config-path", path, env=env, sync=sync)
        self.assertEqual(calls[0]["confirmations"], 12)
        self.assertEqual(calls[0]["from_block"], 99)


if __name__ == "__main__":
    unittest.main()
