"""Resolution service routes, decision files and startup, over real HTTP (ADR-0020, AGENTS.md #2).

The decision file is edited by hand and decides where real money goes, so what happens when it is
wrong matters as much as what happens when it is right.
"""
import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib import error, request

from eth_abi import decode as abi_decode
from eth_hash.auto import keccak

from service.resolution import service as svc

KEY = "0x" + "cd" * 32
RESOLVER = "0xabc3000000000000000000000000000000000003"
ENUM_NO_MASK = "0xa000000000000000000000000000000000000001"
ENUM_RETRACT = "0xa000000000000000000000000000000000000002"
FREEFORM = "0xa000000000000000000000000000000000000003"
NO_DECISION = "0xa000000000000000000000000000000000000004"
ENUM_CLAIM = "0xa000000000000000000000000000000000000005"


def open_row(wager, protocol_version="enumerated"):
    return {
        "wager_address": wager,
        "state": "OPEN",
        "protocol_version": protocol_version,
        "resolver": RESOLVER,
        "betting_closed_by_authority": 1,
        "betting_close_time": 0,
        "resolution_window": 0,
        "resolution_window_closed": 0,
    }


class ReadDecisionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "decisions.json"

    def test_no_file_means_no_decisions(self):
        self.assertEqual(svc._read_decisions(str(self.path)), {})

    def test_non_object_file_means_no_decisions(self):
        self.path.write_text("[1, 2]")
        self.assertEqual(svc._read_decisions(str(self.path)), {})

    def test_comments_are_skipped_and_addresses_normalized(self):
        """The shipped example file carries a `_comment` key, and operators paste checksummed addresses."""
        self.path.write_text(json.dumps({"_comment": "ignored", ENUM_RETRACT.upper().replace("0X", "0x"): {"action": "retract"}}))
        self.assertEqual(svc._read_decisions(str(self.path)), {ENUM_RETRACT: {"action": "retract"}})

    def test_shipped_example_file_is_readable(self):
        path = Path(__file__).resolve().parents[3] / "config" / "resolution-decisions.base-sepolia.json"
        self.assertIsInstance(svc._read_decisions(str(path)), dict)


class ResolverAddressTests(unittest.TestCase):
    def test_explicit_address_is_normalized_without_touching_cast(self):
        with mock.patch.object(svc.subprocess, "run") as run:
            self.assertEqual(svc._extract_resolver_address(RESOLVER.upper().replace("0X", "0x"), KEY), RESOLVER)
        run.assert_not_called()

    def test_no_address_and_no_key_is_a_clear_error(self):
        with self.assertRaisesRegex(RuntimeError, "resolver address required"):
            svc._extract_resolver_address("", "")

    def test_derives_the_address_from_the_key(self):
        done = mock.Mock(returncode=0, stdout=RESOLVER.upper().replace("0X", "0x") + "\n", stderr="")
        with mock.patch.object(svc.subprocess, "run", return_value=done):
            self.assertEqual(svc._extract_resolver_address("", KEY), RESOLVER)

    def test_cast_failure_is_reported(self):
        done = mock.Mock(returncode=1, stdout="", stderr="invalid private key")
        with mock.patch.object(svc.subprocess, "run", return_value=done):
            with self.assertRaisesRegex(RuntimeError, "invalid private key"):
                svc._extract_resolver_address("", "nonsense")


class ActionCommandTests(unittest.TestCase):
    def test_a_decision_cannot_trigger_other_wager_actions(self):
        """The file only ever decides resolve or retract; it must not spend the key on anything else."""
        for action in ("claim", "withdraw-fees", "expire", "close-betting", ""):
            with self.subTest(action=action), self.assertRaisesRegex(ValueError, "unsupported"):
                svc._action_command(wager_address=FREEFORM, action=action, rpc_url="http://r", private_key=KEY)


class RouteBase(unittest.TestCase):
    decisions_text = "{}"
    wagers = ()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "decisions.json"
        self.path.write_text(self.decisions_text)
        patcher = mock.patch.object(svc, "_load_open_wagers", side_effect=lambda *a, **k: [dict(w) for w in self.wagers])
        patcher.start()
        self.addCleanup(patcher.stop)
        svc.Handler.indexer_base_url = "http://indexer.invalid"
        svc.Handler.decisions_path = str(self.path)
        svc.Handler.resolver_address = RESOLVER
        svc.Handler.rpc_url = "http://rpc.invalid"
        svc.Handler.private_key = KEY
        svc.Handler.auth_token = "s3cret"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), svc.Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        svc.Handler.auth_token = None

    def call(self, path, *, method="GET", body=None, raw=None, token="s3cret"):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        headers = {"X-Token": token} if token else {}
        req = request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with request.urlopen(req, timeout=10) as resp:
                text = resp.read().decode()
                return resp.status, json.loads(text) if text else {}, dict(resp.headers)
        except error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode()), dict(exc.headers)


class HealthyRouteTests(RouteBase):
    decisions_text = json.dumps({FREEFORM: {"action": "resolve", "winningAnswer": "x"}})
    wagers = (open_row(FREEFORM, "freeform"),)

    def test_health_reports_what_an_operator_needs_and_never_the_key(self):
        code, body, _ = self.call("/health", token=None)
        self.assertEqual(code, 200)
        self.assertEqual(body["resolver_address"], RESOLVER)
        self.assertEqual(body["decision_entries"], 1)
        self.assertEqual(body["open_wagers_sampled"], 1)
        self.assertIs(body["indexer_ok"], True)
        self.assertIsNone(body["indexer_error"])
        self.assertIs(body["decisions_ok"], True)
        self.assertNotIn(KEY[2:], json.dumps(body))

    def test_health_stays_up_when_the_indexer_is_down(self):
        with mock.patch.object(svc, "_load_open_wagers", side_effect=OSError("indexer unreachable")):
            code, body, _ = self.call("/health", token=None)
        self.assertEqual(code, 200)
        self.assertIs(body["indexer_ok"], False)
        self.assertIn("indexer unreachable", body["indexer_error"])

    def test_cors_preflight(self):
        code, _, headers = self.call("/run-once", method="OPTIONS", token=None)
        self.assertEqual(code, 204)
        self.assertIn("POST", headers["Access-Control-Allow-Methods"])

    def test_unknown_routes_are_not_found(self):
        self.assertEqual(self.call("/nope")[0], 404)
        self.assertEqual(self.call("/nope", method="POST", body={})[0], 404)

    def test_run_once_body_must_be_an_object(self):
        self.assertEqual(self.call("/run-once", method="POST", body=[1])[0], 400)


class MixedDecisionsTests(RouteBase):
    decisions_text = json.dumps(
        {
            ENUM_NO_MASK: {"action": "resolve"},
            ENUM_CLAIM: {"action": "claim"},
            ENUM_RETRACT: {"action": "retract"},
            FREEFORM: {"action": "resolve", "winningAnswer": 42},
        }
    )
    wagers = (
        open_row(ENUM_NO_MASK),
        open_row(ENUM_CLAIM),
        open_row(ENUM_RETRACT),
        open_row(FREEFORM, "freeform"),
        open_row(NO_DECISION),
    )

    def _dry_run(self):
        code, body, _ = self.call("/run-once", method="POST", body={"execute": False})
        self.assertEqual(code, 200)
        return body, {r["wager"]: r for r in body["results"]}

    def test_a_bad_decision_is_reported_and_does_not_stop_the_good_ones(self):
        body, results = self._dry_run()
        self.assertIs(results[ENUM_NO_MASK]["ok"], False)
        self.assertIn("outcomeIndex", results[ENUM_NO_MASK]["error"])
        self.assertIs(results[ENUM_CLAIM]["ok"], False)
        self.assertIn("unsupported", results[ENUM_CLAIM]["error"])
        self.assertEqual((body["attempted"], body["succeeded"], body["failed"]), (2, 2, 2))
        self.assertIs(results[ENUM_RETRACT]["ok"], True)

    def test_a_wager_with_no_decision_is_left_alone(self):
        _, results = self._dry_run()
        self.assertNotIn(NO_DECISION, results)

    def test_retract_targets_the_right_wager_and_function(self):
        _, results = self._dry_run()
        command = results[ENUM_RETRACT]["command"]
        self.assertIn(ENUM_RETRACT, command)
        self.assertEqual(command[-1], "0x" + keccak(b"retract()")[:4].hex())

    def test_a_non_string_answer_is_sent_as_its_text(self):
        """A bare `42` in hand-edited JSON means the answer "42", not a crash partway through a run."""
        _, results = self._dry_run()
        self.assertEqual(abi_decode(["string"], bytes.fromhex(results[FREEFORM]["command"][-1][10:]))[0], "42")

    def test_dry_run_is_the_default_and_sends_nothing(self):
        with mock.patch("service.control_panel.commands.subprocess.run") as run:
            code, body, _ = self.call("/run-once", method="POST", body={})
        self.assertEqual(code, 200)
        self.assertIs(body["execute"], False)
        run.assert_not_called()


class CorruptDecisionsFileTests(RouteBase):
    """A typo in a hand-edited file used to reset the connection on every route, so the operator saw
    a network failure, with no hint at the real cause. The daemon must also refuse to act on it."""

    decisions_text = '{"0xabc": {"action": '
    wagers = (open_row(FREEFORM, "freeform"),)

    def test_health_reports_the_problem(self):
        code, body, _ = self.call("/health", token=None)
        self.assertEqual(code, 200)
        self.assertIs(body["decisions_ok"], False)
        self.assertTrue(body["decisions_error"])
        self.assertEqual(body["decision_entries"], 0)

    def test_candidates_explains_itself(self):
        code, body, _ = self.call("/candidates", token=None)
        self.assertEqual(code, 500)
        self.assertIn("decisions file", body["error"])

    def test_run_once_refuses_and_sends_nothing(self):
        with mock.patch("service.control_panel.commands.subprocess.run") as run:
            code, body, _ = self.call("/run-once", method="POST", body={"execute": True})
        self.assertEqual(code, 500)
        self.assertIn("decisions file", body["error"])
        run.assert_not_called()

    def test_the_error_never_echoes_decision_contents(self):
        """/candidates is unauthenticated, and pending decisions are insider information (O7)."""
        self.path.write_text('{"%s": {"action": "resolve", "winningAnswer": "SECRET-ANSWER"} oops' % FREEFORM)
        _, body, _ = self.call("/candidates", token=None)
        self.assertNotIn("SECRET-ANSWER", json.dumps(body))


class HttpGetJsonTests(unittest.TestCase):
    def test_reads_json_from_the_indexer(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"wagers": []}'
        with mock.patch.object(svc.request, "urlopen", return_value=response) as urlopen:
            self.assertEqual(svc._http_get_json("http://indexer/wagers"), {"wagers": []})
        self.assertEqual(urlopen.call_args.args[0].full_url, "http://indexer/wagers")


class StartupTests(unittest.TestCase):
    class FakeServer:
        served = []

        def __init__(self, address, handler):
            self.address = address

        def serve_forever(self):
            type(self).served.append(self.address)

    def _main(self, *argv, env=None):
        out = io.StringIO()
        with (
            mock.patch.dict(os.environ, env or {}, clear=True),
            mock.patch("sys.argv", ["service", *argv]),
            mock.patch.object(svc, "ThreadingHTTPServer", self.FakeServer),
            contextlib.redirect_stdout(out),
        ):
            svc.main()
        return out.getvalue()

    def test_each_required_setting_is_named_when_missing(self):
        with self.assertRaisesRegex(RuntimeError, "INDEXER_BASE_URL"):
            self._main()
        with self.assertRaisesRegex(RuntimeError, "RPC URL"):
            self._main(env={"INDEXER_BASE_URL": "http://i"})
        with self.assertRaisesRegex(RuntimeError, "PRIVATE_KEY"):
            self._main(env={"INDEXER_BASE_URL": "http://i", "RPC_URL": "http://r"})

    def test_environment_configures_the_handler(self):
        self.addCleanup(setattr, svc.Handler, "auth_token", None)
        env = {
            "INDEXER_BASE_URL": "http://i/",
            "RPC_URL": "http://r",
            "PRIVATE_KEY": KEY,
            "RESOLUTION_SERVICE_ADDRESS": RESOLVER,
            "RESOLUTION_SERVICE_TOKEN": "tok",
            "HOST": "127.0.0.1",
            "PORT": "9999",
        }
        out = self._main(env=env)
        self.assertEqual(svc.Handler.indexer_base_url, "http://i")
        self.assertEqual(svc.Handler.resolver_address, RESOLVER)
        self.assertEqual(svc.Handler.auth_token, "tok")
        self.assertEqual(self.FakeServer.served[-1], ("127.0.0.1", 9999))
        self.assertNotIn(KEY[2:], out)

    def test_no_token_warns_that_execution_is_disabled(self):
        env = {"INDEXER_BASE_URL": "http://i", "RPC_URL": "http://r", "PRIVATE_KEY": KEY, "RESOLUTION_SERVICE_ADDRESS": RESOLVER}
        out = self._main(env=env)
        self.assertIn("reject every request", out)
        self.assertIsNone(svc.Handler.auth_token)


if __name__ == "__main__":
    unittest.main()
