"""ADR-0019 regression tests for the resolution service.

Three verified defects are pinned here:

1. ``outcomeIndex`` was passed to ``resolve(uint256)`` verbatim instead of
   being promoted to the single-bit mask ``1 << i`` the module docstring and
   the shipped decisions template promise. ``outcomeIndex: 1`` therefore
   resolved *outcome 0* (mask ``0b01``) — paying the wrong side.
2. The freeform winning answer was ``.strip()``-ed before ``resolve(string)``.
   V3 matches answers byte-exactly (ADR-0009 §5 forbids trimming), so an
   answer bettors staked with surrounding whitespace could never be resolved,
   and could collide with a different, trimmed pool.
3. ``POST /run-once`` had no authentication and echoed the full ``cast send``
   argv — including ``--private-key <secret>`` — in its dry-run response,
   with ``Access-Control-Allow-Origin: *``. Any caller (or any web page an
   operator visited) could exfiltrate the resolver key or trigger resolver
   transactions.
"""
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock
from urllib import error, request

from service.resolution import service as svc

KEY = "0x" + "cd" * 32
RESOLVER = "0xabc3000000000000000000000000000000000003"
WAGER = "0xabc1000000000000000000000000000000000001"


class TestResolveArgFromDecision(unittest.TestCase):
    def test_outcome_index_is_promoted_to_single_bit_mask(self) -> None:
        self.assertEqual(svc.resolve_uint256_from_decision({"outcomeIndex": 0}), 1)
        self.assertEqual(svc.resolve_uint256_from_decision({"outcomeIndex": 1}), 2)
        self.assertEqual(svc.resolve_uint256_from_decision({"outcomeIndex": 5}), 32)

    def test_winning_mask_takes_precedence_and_is_passed_raw(self) -> None:
        self.assertEqual(svc.resolve_uint256_from_decision({"outcomeIndex": 1, "winningMask": 5}), 5)

    def test_missing_value_returns_none(self) -> None:
        self.assertIsNone(svc.resolve_uint256_from_decision({"action": "resolve"}))

    def test_rejects_out_of_range_or_non_integer(self) -> None:
        for bad in ({"outcomeIndex": -1}, {"outcomeIndex": 255}, {"outcomeIndex": 1.5},
                    {"outcomeIndex": True}, {"winningMask": 0}, {"winningMask": -3}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                svc.resolve_uint256_from_decision(bad)


class TestFreeformAnswerIsByteExact(unittest.TestCase):
    def test_surrounding_whitespace_is_preserved(self) -> None:
        cmd = svc._action_command(
            wager_address=WAGER,
            action="resolve",
            rpc_url="http://localhost:8545",
            private_key=KEY,
            protocol_version="freeform",
            winning_answer=" Paris ",
        )
        # Decode what reaches the chain: `cast` itself alters strings, so an argv check proves nothing.
        data = cmd[-1]
        self.assertEqual(int.from_bytes(bytes.fromhex(data[10:])[32:64], "big"), len(" Paris "))
        self.assertEqual(bytes.fromhex(data[10:])[64:71], b" Paris ")


class TestRunOnceEndpoint(unittest.TestCase):
    """Drives the real HTTP handler on an ephemeral localhost port."""

    OPEN_WAGER = {
        "wager_address": WAGER,
        "state": "OPEN",
        "protocol_version": "enumerated",
        "resolver": RESOLVER,
        "betting_closed_by_authority": 1,
        "betting_close_time": 0,
        "resolution_window": 0,
        "resolution_window_closed": 0,
    }

    def setUp(self) -> None:
        self._patches = [
            mock.patch.object(svc, "_load_open_wagers", return_value=([dict(self.OPEN_WAGER)], False)),
            mock.patch.object(svc, "_read_decisions", return_value={WAGER: {"action": "resolve", "outcomeIndex": 1}}),
            mock.patch.object(svc.subprocess, "run", side_effect=AssertionError("must not execute")),
        ]
        for p in self._patches:
            p.start()
        svc.Handler.indexer_base_url = "http://indexer.invalid"
        svc.Handler.decisions_path = "unused.json"
        svc.Handler.resolver_address = RESOLVER
        svc.Handler.rpc_url = "http://rpc.invalid"
        svc.Handler.private_key = KEY
        svc.Handler.auth_token = "s3cret"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), svc.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/run-once"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        for p in self._patches:
            p.stop()
        svc.Handler.auth_token = None

    def _post(self, body: dict, headers: dict | None = None) -> tuple[int, str]:
        req = request.Request(self.url, data=json.dumps(body).encode(), method="POST", headers=headers or {})
        try:
            with request.urlopen(req, timeout=10) as resp:
                return resp.status, resp.read().decode()
        except error.HTTPError as exc:
            return exc.code, exc.read().decode()

    def test_run_once_without_token_is_rejected(self) -> None:
        code, body = self._post({"execute": True})
        self.assertEqual(code, 401)
        self.assertNotIn(KEY[2:], body)

    def test_run_once_with_wrong_token_is_rejected(self) -> None:
        code, _ = self._post({"execute": False}, {"Authorization": "Bearer nope"})
        self.assertEqual(code, 401)

    def test_run_once_fails_closed_when_no_token_configured(self) -> None:
        svc.Handler.auth_token = None
        code, _ = self._post({"execute": False}, {"Authorization": "Bearer "})
        self.assertEqual(code, 401)

    def test_dry_run_redacts_private_key_and_promotes_outcome_index(self) -> None:
        code, body = self._post({"execute": False}, {"X-Token": "s3cret"})
        self.assertEqual(code, 200)
        self.assertNotIn(KEY[2:], body)
        data = json.loads(body)
        self.assertEqual(data["attempted"], 1)
        cmd = data["results"][0]["command"]
        self.assertIn("<redacted>", cmd)
        # outcomeIndex 1 -> mask 2 (outcome #1), never raw 1 (outcome #0).
        self.assertEqual(int(cmd[-1][10:], 16), 2)


if __name__ == "__main__":
    unittest.main()
