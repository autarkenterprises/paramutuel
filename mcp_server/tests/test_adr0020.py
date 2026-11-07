"""ADR-0020 regressions for the MCP server."""
from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eth_abi import decode as abi_decode

import mcp_server.server as srv

ZERO = "0x" + "00" * 20
ADDR = "0x" + "11" * 20
WAGER = "0x" + "22" * 20
FUTURE = 9_999_999_999


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def detail(**kw):
    wager = {
        "state": "OPEN",
        "protocol_version": "enumerated",
        "payoff_policy": 0,
        "collateral_token": ADDR,
        "betting_closed_by_authority": 0,
        "betting_close_time": FUTURE,
        "outcomes_json": '["A","B"]',
        "min_new_ticket_stake": "0",
    }
    wager.update(kw)
    return {"wager": wager, "totals": {"total_pot": "1000", "total_fee_bps": "100"}, "ticket_pools": [{"ticket_mask": "1", "pool_total": "400"}]}


async def _fake_get(self_path, payload):
    return payload


class ByteExactAnswerTests(unittest.TestCase):
    """`quote_place_bet` stripped the answer while `encode_place_bet_freeform` did not, so the same
    input produced calldata for two different pools, while both documented "exact" bytes."""

    def _quote(self, answer):
        payload = detail(protocol_version="freeform")
        payload["ticket_pools"] = []

        async def fake(path):
            return payload

        with patch.object(srv, "_indexer_get", fake):
            return json.loads(run(srv.quote_place_bet(WAGER, amount=5, answer=answer)))

    def test_quote_sends_exactly_the_answer_it_was_given(self):
        body = self._quote(" Paris ")
        answer, amount = abi_decode(["string", "uint256"], bytes.fromhex(body["placeBet"]["calldata"][10:]))
        self.assertEqual(answer, " Paris ")
        self.assertEqual(amount, 5)
        self.assertEqual(body["answer"], " Paris ")

    def test_quote_and_encode_agree(self):
        quoted = self._quote(" Paris ")["placeBet"]["calldata"]
        encoded = json.loads(run(srv.encode_place_bet_freeform(WAGER, ADDR, " Paris ", 5)))["calldata"]
        self.assertEqual(quoted, encoded)

    def test_edge_whitespace_is_flagged_so_an_agent_can_notice(self):
        self.assertTrue(self._quote(" Paris ")["answer_has_edge_whitespace"])
        self.assertFalse(self._quote("Paris")["answer_has_edge_whitespace"])

    def test_empty_answer_rejected(self):
        with self.assertRaises(ValueError):
            self._quote("")

    def test_pool_lookup_uses_the_direct_answer_query(self):
        """The list response is truncated to the largest stakes, so a smaller pool would read as empty."""
        paths = []
        payload = detail(protocol_version="freeform")
        aid = srv._freeform_answer_id_hex("Paris")
        payload["ticket_pools"] = [{"ticket_mask": aid, "pool_total": "77"}]

        async def fake(path):
            paths.append(path)
            return payload

        with patch.object(srv, "_indexer_get", fake):
            body = json.loads(run(srv.quote_place_bet(WAGER, amount=5, answer="Paris")))
        self.assertIn(f"answer_id={aid}", paths[0])
        self.assertEqual(body["odds"]["post_bet_payout_multiple"], round((1005 - 10) / 82, 4))


class QuoteValidationTests(unittest.TestCase):
    def _quote(self, payload, **kw):
        async def fake(path):
            return payload

        with patch.object(srv, "_indexer_get", fake):
            return json.loads(run(srv.quote_place_bet(WAGER, amount=kw.pop("amount", 5), **kw)))

    def test_out_of_range_outcome_is_rejected(self):
        """It produced a mask the contract rejects, handed over as ready-to-sign calldata."""
        with self.assertRaises(ValueError):
            self._quote(detail(), outcome_index=2)
        with self.assertRaises(ValueError):
            self._quote(detail(), outcome_index=-1)

    def test_batch_out_of_range_outcome_is_rejected(self):
        async def fake(path):
            return detail()

        with patch.object(srv, "_indexer_get", fake), self.assertRaises(ValueError):
            run(srv.quote_place_bets(WAGER, [0, 5], [1, 1]))

    def test_new_ticket_below_minimum_is_not_executable(self):
        body = self._quote(detail(min_new_ticket_stake="100"), outcome_index=1, amount=99)
        self.assertFalse(body["execution_allowed"])
        self.assertIn("minNewTicketStake", body["revert_hint"])

    def test_existing_ticket_ignores_the_minimum(self):
        body = self._quote(detail(min_new_ticket_stake="100"), outcome_index=0, amount=1)
        self.assertTrue(body["execution_allowed"])

    def test_invalid_wager_address_is_rejected_before_any_request(self):
        for bad in ("../health", "0x123", WAGER + "/x", "not-hex"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                run(srv.get_wager(bad))


class CreateEncoderTests(unittest.TestCase):
    def setUp(self):
        self._patch = patch.object(srv, "FACTORY_ADDRESS", ADDR)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()

    def _enum(self, **kw):
        args = dict(
            collateral_token=ADDR, proposition="Q?", outcomes=["A", "B"], payoff_policy=0, policy_param=0,
            betting_close_time=FUTURE, resolution_window=100,
        )
        args.update(kw)
        return json.loads(run(srv.encode_create_enumerated_wager(**args)))

    def test_default_windows_are_rejected_rather_than_encoding_a_certain_revert(self):
        """Every default produced calldata the factory rejects with InvalidLifecycleConfig."""
        with self.assertRaises(ValueError) as ctx:
            run(srv.encode_create_enumerated_wager(ADDR, "Q?", ["A", "B"], 0, 0))
        self.assertIn("closer", str(ctx.exception))
        with self.assertRaises(ValueError):
            run(srv.encode_create_freeform_wager(ADDR, "Q?"))

    def test_zero_time_with_a_closer_is_allowed(self):
        body = self._enum(betting_close_time=0, resolution_window=0, betting_closer=ADDR, resolution_closer=ADDR)
        self.assertIn("calldata", body)

    def test_too_many_fee_recipients_rejected(self):
        with self.assertRaises(ValueError):
            self._enum(extra_fee_recipients=[ADDR] * 33, extra_fee_bps=[1] * 33)

    def test_fee_array_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            self._enum(extra_fee_recipients=[ADDR], extra_fee_bps=[])

    def test_min_stake_selects_the_new_overload(self):
        body = self._enum(min_new_ticket_stake=500)
        signature = (
            "createEnumeratedWager(address,string,string[],uint8,uint256,uint64,uint64,"
            "address,address,address,address[],uint16[],uint256[],uint256[],uint256)"
        )
        self.assertEqual(body["calldata"][:10], "0x" + srv._selector(signature).hex())
        types = ["address", "string", "string[]", "uint8", "uint256", "uint64", "uint64", "address", "address",
                 "address", "address[]", "uint16[]", "uint256[]", "uint256[]", "uint256"]
        self.assertEqual(abi_decode(types, bytes.fromhex(body["calldata"][10:]))[14], 500)

    def test_zero_min_stake_uses_the_overload_every_factory_has(self):
        signature = (
            "createEnumeratedWager(address,string,string[],uint8,uint256,uint64,uint64,"
            "address,address,address,address[],uint16[])"
        )
        self.assertEqual(self._enum()["calldata"][:10], "0x" + srv._selector(signature).hex())

    def test_freeform_min_stake(self):
        body = json.loads(run(srv.encode_create_freeform_wager(
            ADDR, "Q?", betting_close_time=FUTURE, resolution_window=100, min_new_ticket_stake=9
        )))
        signature = "createFreeformWager(address,string,uint64,uint64,address,address,address,address[],uint16[],uint256)"
        self.assertEqual(body["calldata"][:10], "0x" + srv._selector(signature).hex())

    def test_every_create_signature_exists_in_the_bundled_abi(self):
        def canon(item):
            return f"{item['name']}({','.join(i['type'] for i in item['inputs'])})"

        known = {canon(i) for i in srv.FACTORY_ABI if i["type"] == "function"}
        for signature in srv.CREATE_SIGNATURES:
            self.assertIn(signature, known)


class ProtocolInfoTests(unittest.TestCase):
    def test_constants_match_the_abi_surface(self):
        info = json.loads(run(srv.get_protocol_info()))
        self.assertNotIn("FREEFORM_MAX_DISTINCT_ANSWERS_CAP", info["constants"], "there is no such cap any more")
        self.assertEqual(info["constants"]["MAX_EXTRA_FEE_RECIPIENTS"], 32)
        self.assertEqual(info["constants"]["MAX_DISTINCT_TICKETS"], 1024)


class ToolCountTests(unittest.TestCase):
    def test_documented_tool_count_is_true(self):
        """Docs said 16 and 17 at once. It is checked here so it stays true."""
        tools = run(srv.mcp_server.list_tools())
        self.assertEqual(len(tools), 21)
        root = Path(__file__).resolve().parents[2]
        self.assertIn(f"{len(tools)} tools", (root / "README.md").read_text(encoding="utf-8"))
        self.assertIn(f"{len(tools)} tools", (root / "docs" / "MACHINE.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
