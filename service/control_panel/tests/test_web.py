"""ADR-0020: the web control panel, over real HTTP."""
import contextlib
import io
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock
from urllib import error, request

from eth_abi import decode as abi_decode

from service.control_panel import web

KEY = "0x" + "cd" * 32
ADDR = "0x" + "22" * 20


class WebTests(unittest.TestCase):
    def setUp(self):
        web.Handler.rpc_url = "http://r"
        web.Handler.private_key = KEY
        web.Handler.allow_execute = True
        web.Handler.auth_token = "tok"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def _post(self, path, body, headers=None, raw=None):
        data = raw if raw is not None else json.dumps(body).encode()
        req = request.Request(self.base + path, data=data, method="POST", headers=headers or {})
        try:
            with request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode())
        except error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode())

    def _create_body(self, **kw):
        body = {
            "factory": ADDR, "collateral": ADDR, "proposition": "Q?", "outcomes": ["A", "B", "C"],
            "bettingCloseTime": 1, "resolutionWindow": 1,
        }
        body.update(kw)
        return body

    def test_payoff_policy_and_param_are_not_dropped(self):
        """The panel used to ignore these, silently creating a SINGLE_WINNER wager."""
        code, body = self._post("/api/preview/create-wager", self._create_body(payoffPolicy=3, policyParam=2))
        self.assertEqual(code, 200)
        args = abi_decode(
            ["address", "string", "string[]", "uint8", "uint256"],
            bytes.fromhex(body["command"][-1][10:]),
        )
        self.assertEqual((args[3], args[4]), (3, 2))

    def test_min_new_ticket_stake_is_forwarded(self):
        code, body = self._post("/api/preview/create-wager", self._create_body(minNewTicketStake=9))
        self.assertEqual(code, 200)
        self.assertTrue(body["function"].endswith(",uint256)"))

    def test_preview_redacts_key_and_shows_decoded_arguments(self):
        code, body = self._post("/api/preview/action", {"wager": ADDR, "action": "resolve", "winningMask": "5"})
        self.assertEqual(code, 200)
        self.assertNotIn(KEY[2:], json.dumps(body))
        self.assertEqual(body["function"], "resolve(uint256)")
        self.assertEqual(body["args"], ["5"], "an operator reviews readable arguments, not hex")

    def test_large_mask_as_string_survives(self):
        mask = 2**200 + 1
        code, body = self._post("/api/preview/action", {"wager": ADDR, "action": "resolve", "winningMask": str(mask)})
        self.assertEqual(code, 200)
        self.assertEqual(abi_decode(["uint256"], bytes.fromhex(body["command"][-1][10:]))[0], mask)

    def test_invalid_input_is_400_not_a_reset(self):
        self.assertEqual(self._post("/api/preview/action", None, raw=b"{not json")[0], 400)
        self.assertEqual(self._post("/api/preview/action", {"wager": "0x123", "action": "retract"})[0], 400)
        self.assertEqual(self._post("/api/preview/create-wager", self._create_body(bettingCloseTime=None))[0], 400)
        self.assertEqual(self._post("/api/preview/create-wager", ["not", "an", "object"])[0], 400)

    def test_execute_needs_token_then_reports_mined_revert_as_not_ok(self):
        body = {"wager": ADDR, "action": "retract", "execute": True}
        self.assertEqual(self._post("/api/preview/action", body)[0], 401)
        receipt = json.dumps({"status": "0x0", "transactionHash": "0xfeed"})
        fake = mock.Mock(returncode=0, stdout=receipt, stderr="")
        with mock.patch("service.control_panel.commands.subprocess.run", return_value=fake):
            code, res = self._post("/api/preview/action", body, {"Authorization": "Bearer tok"})
        self.assertEqual(code, 200)
        self.assertFalse(res["ok"])
        self.assertEqual(res["tx_hash"], "0xfeed")

    def test_execute_can_be_disabled(self):
        web.Handler.allow_execute = False
        code, _ = self._post("/api/preview/action", {"wager": ADDR, "action": "retract", "execute": True})
        self.assertEqual(code, 403)


class ConfigTests(unittest.TestCase):
    def test_flags_fall_back_to_documented_environment_variables(self):
        """The module docstring promised CONTROL_PANEL_TOKEN; only a flag existed, so a deployment
        following the docs failed closed on every execute."""
        env = {"CONTROL_PANEL_TOKEN": "t", "PRIVATE_KEY": "k", "RPC_URL": "http://r"}
        with mock.patch.dict("os.environ", env), mock.patch("sys.argv", ["web"]):
            args = web.parse_args()
        self.assertEqual((args.auth_token, args.private_key, args.rpc_url), ("t", "k", "http://r"))


class WebRouteTests(WebTests):
    """Serving the panel itself, the freeform path, and startup."""

    def _get(self, path):
        try:
            with request.urlopen(self.base + path, timeout=10) as resp:
                return resp.status, resp.headers.get("Content-Type"), resp.read()
        except error.HTTPError as exc:
            return exc.code, exc.headers.get("Content-Type"), exc.read()

    def test_serves_the_panel_and_its_script(self):
        code, ctype, body = self._get("/")
        self.assertEqual((code, ctype), (200, "text/html"))
        self.assertIn(b"<html", body.lower())
        code, ctype, _ = self._get("/app.js")
        self.assertEqual((code, ctype), (200, "application/javascript"))

    def test_health_needs_no_token_and_reveals_nothing(self):
        code, _, body = self._get("/health")
        self.assertEqual((code, json.loads(body)), (200, {"ok": True}))

    def test_unknown_routes_are_not_found(self):
        self.assertEqual(self._get("/nope")[0], 404)
        self.assertEqual(self._post("/api/nope", {})[0], 404)

    def test_a_missing_asset_is_not_found(self):
        with mock.patch.object(web, "STATIC_DIR", web.Path("/nonexistent")):
            self.assertEqual(self._get("/")[0], 404)

    def test_freeform_create_preview_encodes_exactly_what_was_given(self):
        body = {
            "factory": ADDR, "collateral": ADDR, "proposition": ' "Quoted" question ',
            "bettingCloseTime": 5, "resolutionWindow": 6, "minNewTicketStake": 9,
        }
        code, out = self._post("/api/preview/create-freeform-wager", body)
        self.assertEqual(code, 200)
        self.assertTrue(out["function"].startswith("createFreeformWager("))
        decoded = abi_decode(
            ["address", "string", "uint64", "uint64", "address", "address", "address", "address[]", "uint16[]", "uint256"],
            bytes.fromhex(out["command"][-1][10:]),
        )
        self.assertEqual(decoded[1], ' "Quoted" question ')
        self.assertEqual((decoded[2], decoded[3], decoded[-1]), (5, 6, 9))


class WebStartupTests(unittest.TestCase):
    class FakeServer:
        served = []

        def __init__(self, address, handler):
            self.address = address

        def serve_forever(self):
            type(self).served.append(self.address)

    def _main(self, *argv, env=None):
        with (
            mock.patch.dict(web.os.environ, env or {}, clear=True),
            mock.patch("sys.argv", ["web", *argv]),
            mock.patch.object(web, "ThreadingHTTPServer", self.FakeServer),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            web.main()

    def test_refuses_to_start_without_rpc_and_key(self):
        for env in ({}, {"RPC_URL": "http://r"}, {"PRIVATE_KEY": KEY}):
            with self.subTest(env=sorted(env)), self.assertRaisesRegex(SystemExit, "required"):
                self._main(env=env)

    def test_settings_reach_the_handler_and_execution_stays_off_by_default(self):
        self._main("--port", "9", env={"RPC_URL": "http://r", "PRIVATE_KEY": KEY, "CONTROL_PANEL_TOKEN": "tok"})
        H = web.Handler
        self.assertEqual((H.rpc_url, H.private_key, H.auth_token), ("http://r", KEY, "tok"))
        self.assertIs(H.allow_execute, False)
        self.assertEqual(self.FakeServer.served[-1], ("127.0.0.1", 9), "binds to loopback unless told otherwise")


if __name__ == "__main__":
    unittest.main()
