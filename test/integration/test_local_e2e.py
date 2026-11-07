"""Every layer against a real chain (ADR-0020).

Runs an anvil node with the Osaka hardfork, so EIP-7825's per-transaction gas cap applies as it does on
Base, and drives it the way production does: real `cast` subprocesses, real calldata from the MCP server
and the bet scout, the real indexer syncing over JSON-RPC, and the real HTTP services.

Each test's assertions compare two independently derived views of the same fact, chain state and the
off-chain layer's report of it, because that agreement is what no unit test can show.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib import request

from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from eth_hash.auto import keccak

import mcp_server.server as mcp
from agents.paramutuel_bettor import planner as scout_planner
from agents.paramutuel_bettor.indexer_client import IndexerClient
from service.control_panel.commands import (
    build_create_freeform_wager_command,
    build_create_wager_command,
    build_wager_action_command,
    cast_send_argv,
    run_cast_send,
)
from service.indexer import api as indexer_api
from service.indexer import indexer as ix
from service.indexer import sweeper
from service.proposition import dispatch as proposition_dispatch
from service.resolution import service as resolution

ROOT = Path(__file__).resolve().parents[2]
ZERO = "0x" + "00" * 20
TX_GAS_CAP = 2**24

# Anvil's standard development accounts. Public, and worthless outside a local chain.
KEYS = {
    "deployer": "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
    "resolver": "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
    "alice": "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
    "bob": "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6",
    "carol": "0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a",
}
TREASURY = "0x000000000000000000000000000000000000fee1"
BENEFICIARY = "0x000000000000000000000000000000000000cafe"
PROTOCOL_BPS = 137
EXTRA_BPS = 251
TOTAL_BPS = PROTOCOL_BPS + EXTRA_BPS

SINGLE_WINNER, ANY_OF, EXACT_SET, AT_LEAST_K, WEIGHTED_OVERLAP = range(5)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def address_of(key: str) -> str:
    out = subprocess.run(["cast", "wallet", "address", "--private-key", key], check=True, capture_output=True, text=True)
    return out.stdout.strip()


def artifact(name: str) -> dict:
    path = next((ROOT / "out").rglob(f"{name}.json"))
    return json.loads(path.read_text())


def answer_id(answer: str) -> str:
    return "0x" + keccak(b"\x03" + answer.encode("utf-8")).hex()


def expected_units(policy: int, k: int, winning_mask: int, stakes: list[tuple[int, int]]) -> int:
    """An independent statement of docs/PAYOUT-CALCULATION.md Part B, written from the doc and not
    from either implementation."""
    total = 0
    for mask, amount in stakes:
        overlap = bin(mask & winning_mask).count("1")
        if overlap == 0:
            continue
        if policy in (SINGLE_WINNER, EXACT_SET):
            total += amount if mask == winning_mask else 0
        elif policy == ANY_OF:
            total += amount
        elif policy == AT_LEAST_K:
            total += amount if overlap >= k else 0
        elif policy == WEIGHTED_OVERLAP:
            total += amount * overlap
    return total


@unittest.skipUnless(shutil.which("anvil") and shutil.which("cast"), "Foundry is required")
class LocalChainE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = free_port()
        cls.rpc = f"http://127.0.0.1:{cls.port}"
        cls.anvil = subprocess.Popen(
            ["anvil", "--port", str(cls.port), "--silent", "--hardfork", "osaka", "--code-size-limit", "24576"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(100):
            try:
                ix.rpc_call(cls.rpc, "eth_blockNumber", [])
                break
            except Exception:
                time.sleep(0.1)
        else:
            raise RuntimeError("anvil did not start")

        cls.addr = {name: address_of(key) for name, key in KEYS.items()}
        cls.token = cls._deploy("MockERC20")
        ctor = abi_encode(["address", "uint16", "uint64", "uint64"], [TREASURY, PROTOCOL_BPS, 0, 0]).hex()
        cls.factory = cls._deploy("ParamutuelFactoryV3", ctor)
        cls.start_block = 0
        for name in ("alice", "bob", "carol", "deployer"):
            cls._send(KEYS["deployer"], cls.token, cls._encode("mint(address,uint256)", ["address", "uint256"], [cls.addr[name], 10**30]))

        cls.tmp = tempfile.mkdtemp(prefix="paramutuel-e2e-")
        cls.db_path = os.path.join(cls.tmp, "indexer.db")
        cls.conn = ix.db_connect(cls.db_path)
        ix.init_db(cls.conn)

        # The real read API over the database the indexer writes.
        indexer_api.Handler.conn = ix.db_connect(cls.db_path)
        indexer_api.Handler.indexer_factory_address = cls.factory.lower()
        cls.api = ThreadingHTTPServer(("127.0.0.1", 0), indexer_api.Handler)
        cls.api_url = f"http://127.0.0.1:{cls.api.server_address[1]}"
        threading.Thread(target=cls.api.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.api.shutdown()
        cls.api.server_close()
        cls.conn.close()
        cls.anvil.terminate()
        cls.anvil.wait(timeout=10)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ---- chain helpers ----

    @staticmethod
    def _encode(signature: str, types: list[str], values: list) -> str:
        return "0x" + (keccak(signature.encode())[:4] + abi_encode(types, values)).hex()

    @classmethod
    def _send(cls, key: str, to: str, data: str, *, expect_ok: bool = True):
        result = run_cast_send(cast_send_argv(to=to, calldata=data, rpc_url=cls.rpc, private_key=key))
        if expect_ok and not result.ok:
            raise AssertionError(f"transaction failed: {result.stderr}")
        return result

    @classmethod
    def _deploy(cls, name: str, ctor_hex: str = "") -> str:
        bytecode = artifact(name)["bytecode"]["object"]
        code = bytecode + ctor_hex
        proc = subprocess.run(
            ["cast", "send", "--json", "--rpc-url", cls.rpc, "--private-key", KEYS["deployer"], "--create", code],
            check=True, capture_output=True, text=True,
        )
        return json.loads(proc.stdout)["contractAddress"]

    def _view(self, to: str, signature: str, in_types: list[str], values: list, out_types: list[str]):
        data = self._encode(signature, in_types, values)
        result = ix.rpc_call(self.rpc, "eth_call", [{"to": to, "data": data}, "latest"])
        return abi_decode(out_types, bytes.fromhex(result[2:]))

    def _uint(self, to: str, signature: str, in_types=None, values=None) -> int:
        return self._view(to, signature, in_types or [], values or [], ["uint256"])[0]

    def _balance(self, who: str) -> int:
        return self._uint(self.token, "balanceOf(address)", ["address"], [who])

    def _now(self) -> int:
        return int(ix.rpc_call(self.rpc, "eth_getBlockByNumber", ["latest", False])["timestamp"], 16)

    def _warp(self, timestamp: int) -> None:
        ix.rpc_call(self.rpc, "evm_setNextBlockTimestamp", [hex(timestamp)])
        ix.rpc_call(self.rpc, "evm_mine", [])

    def _sync(self) -> None:
        ix.sync_logs(rpc_url=self.rpc, conn=self.conn, factory_address=self.factory, from_block=None, to_block=None, chunk_size=500, allow_genesis_start=True)

    def _api(self, path: str):
        with request.urlopen(self.api_url + path, timeout=10) as resp:
            return json.loads(resp.read().decode())

    def _new_wager_from_receipt(self, stdout: str) -> str:
        receipt, _ = json.JSONDecoder().raw_decode(stdout[stdout.index("{"):])
        for log in receipt["logs"]:
            if log["address"].lower() == self.factory.lower():
                return "0x" + log["topics"][1][-40:]
        raise AssertionError("no creation event")

    def _approve(self, who: str, spender: str) -> None:
        data = self._encode("approve(address,uint256)", ["address", "uint256"], [spender, 2**256 - 1])
        self._send(KEYS[who], self.token, data)

    def _create_enumerated(self, outcomes, policy=SINGLE_WINNER, k=0, **kw) -> tuple[str, int]:
        close = self._now() + 1000
        cmd = build_create_wager_command(
            factory=self.factory,
            collateral=self.token,
            proposition=kw.pop("proposition", "Will it?"),
            outcomes=outcomes,
            betting_close_time=close,
            resolution_window=500,
            resolver=self.addr["resolver"],
            betting_closer=ZERO,
            resolution_closer=ZERO,
            extra_recipients=[BENEFICIARY],
            extra_bps=[EXTRA_BPS],
            payoff_policy=policy,
            policy_param=k,
            rpc_url=self.rpc,
            private_key=KEYS["deployer"],
            **kw,
        )
        result = run_cast_send(cmd.command)
        self.assertTrue(result.ok, result.stderr)
        return self._new_wager_from_receipt(result.stdout), close

    def _create_freeform(self, **kw) -> tuple[str, int]:
        close = self._now() + 1000
        cmd = build_create_freeform_wager_command(
            factory=self.factory,
            collateral=self.token,
            proposition="Who wins?",
            betting_close_time=close,
            resolution_window=500,
            resolver=self.addr["resolver"],
            betting_closer=ZERO,
            resolution_closer=ZERO,
            extra_recipients=[BENEFICIARY],
            extra_bps=[EXTRA_BPS],
            rpc_url=self.rpc,
            private_key=KEYS["deployer"],
            **kw,
        )
        result = run_cast_send(cmd.command)
        self.assertTrue(result.ok, result.stderr)
        return self._new_wager_from_receipt(result.stdout), close

    def _bet_mask_via_mcp(self, who: str, wager: str, mask: int, amount: int) -> None:
        self._approve(who, wager)
        body = json.loads(asyncio.new_event_loop().run_until_complete(mcp.encode_place_bet(wager, self.token, amount=amount, ticket_mask=mask)))
        self._send(KEYS[who], body["to"], body["calldata"])

    def _bet_answer_via_mcp(self, who: str, wager: str, answer: str, amount: int) -> None:
        self._approve(who, wager)
        body = json.loads(asyncio.new_event_loop().run_until_complete(mcp.encode_place_bet_freeform(wager, self.token, answer, amount)))
        self._send(KEYS[who], body["to"], body["calldata"])

    def _run_resolution_service(self, decisions: dict, *, execute: bool = True, chain_now: int) -> dict:
        path = os.path.join(self.tmp, "decisions.json")
        Path(path).write_text(json.dumps(decisions))
        H = resolution.Handler
        H.indexer_base_url = self.api_url
        H.decisions_path = path
        H.resolver_address = self.addr["resolver"].lower()
        H.rpc_url = self.rpc
        H.private_key = KEYS["resolver"]
        H.auth_token = "e2e"
        server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            req = request.Request(
                f"http://127.0.0.1:{server.server_address[1]}/run-once",
                data=json.dumps({"execute": execute}).encode(),
                method="POST",
                headers={"Authorization": "Bearer e2e"},
            )
            # The service reads the wall clock; this chain's clock has been warped forward.
            with mock.patch.object(resolution.time, "time", return_value=chain_now), request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode())
        finally:
            server.shutdown()
            server.server_close()

    def _claim(self, who: str, wager: str) -> int:
        before = self._balance(self.addr[who])
        cmd = build_wager_action_command(wager=wager, action="claim", rpc_url=self.rpc, private_key=KEYS[who])
        result = run_cast_send(cmd.command)
        self.assertTrue(result.ok, result.stderr)
        return self._balance(self.addr[who]) - before

    # ---- tests ----

    def _assert_policy_settles(self, policy: int, k: int, outcomes: list[str], winning_mask: int, stakes: dict[str, list[tuple[int, int]]]):
        wager, close = self._create_enumerated(outcomes, policy, k)
        flat = []
        for who, legs in stakes.items():
            for mask, amount in legs:
                self._bet_mask_via_mcp(who, wager, mask, amount)
                flat.append((mask, amount))
        self._sync()

        pot = sum(a for _, a in flat)
        # While open, what the API reports must equal the chain.
        detail = self._api(f"/wagers/{wager}")
        self.assertEqual(int(detail["totals"]["total_pot"]), self._uint(wager, "totalPot()"))
        self.assertEqual(int(detail["totals"]["total_fee_bps"]), self._uint(wager, "totalFeeBps()"))
        self.assertEqual(int(detail["totals"]["total_fee_bps"]), TOTAL_BPS)
        for pool in detail["ticket_pools"]:
            mask = int(pool["ticket_mask"])
            self.assertEqual(int(pool["pool_total"]), self._uint(wager, "ticketPoolByMask(uint256)", ["uint256"], [mask]))
        self.assertEqual(len(detail["outcomes"]), len(outcomes))
        for row in detail["outcomes"]:
            bit = 1 << row["outcome_index"]
            self.assertEqual(int(row["outcome_total"]), sum(a for m, a in flat if m & bit))

        # Resolve through the real service with real `cast`.
        self._warp(close + 1)
        report = self._run_resolution_service({wager: {"action": "resolve", "winningMask": winning_mask}}, chain_now=close + 1)
        self.assertEqual(report["succeeded"], 1, report)
        self._sync()

        denominator = self._uint(wager, "payoutDenominator()")
        self.assertEqual(denominator, expected_units(policy, k, winning_mask, flat), "contract vs the documented formula")
        detail = self._api(f"/wagers/{wager}")
        self.assertEqual(detail["wager"]["state"], "RESOLVED")
        self.assertEqual(int(detail["totals"]["winning_outcome"]), winning_mask)
        self.assertEqual(int(detail["totals"]["total_winning_stake"]), denominator, "indexer vs chain")

        # Every claim pays exactly the documented amount, and custody ends as dust only.
        fees = pot * TOTAL_BPS // 10_000
        net = pot - fees
        paid_total = 0
        for who, legs in stakes.items():
            expected = 0
            for mask, amount in legs:
                overlap = bin(mask & winning_mask).count("1")
                wins = overlap > 0 and (
                    mask == winning_mask if policy in (SINGLE_WINNER, EXACT_SET)
                    else overlap >= k if policy == AT_LEAST_K
                    else True
                )
                if wins:
                    weight = amount * overlap if policy == WEIGHTED_OVERLAP else amount
                    expected += weight * net // denominator
            if expected:
                self.assertEqual(self._claim(who, wager), expected, f"{who}'s payout")
                paid_total += expected
        self.assertLessEqual(paid_total, net)
        self.assertLess(net - paid_total, len(flat) + 1, "only rounding dust may be left of the net pot")

    def test_single_winner_settles(self):
        self._assert_policy_settles(SINGLE_WINNER, 0, ["A", "B", "C"], 0b010, {"alice": [(0b010, 700)], "bob": [(0b001, 300)], "carol": [(0b010, 11), (0b100, 13)]})

    def test_any_of_settles(self):
        self._assert_policy_settles(ANY_OF, 0, ["A", "B", "C"], 0b011, {"alice": [(0b001, 700)], "bob": [(0b110, 301)], "carol": [(0b100, 13)]})

    def test_exact_set_settles(self):
        self._assert_policy_settles(EXACT_SET, 0, ["A", "B", "C"], 0b011, {"alice": [(0b011, 700)], "bob": [(0b001, 301)], "carol": [(0b011, 13)]})

    def test_at_least_k_settles(self):
        self._assert_policy_settles(AT_LEAST_K, 2, ["A", "B", "C", "D"], 0b0111, {"alice": [(0b0011, 700)], "bob": [(0b1001, 301)], "carol": [(0b0111, 13)]})

    def test_weighted_overlap_settles(self):
        self._assert_policy_settles(WEIGHTED_OVERLAP, 0, ["A", "B", "C", "D"], 0b0011, {"alice": [(0b0011, 701)], "bob": [(0b0001, 307)], "carol": [(0b0111, 13), (0b1000, 5)]})

    def test_outcome_index_decision_promotes_to_the_right_mask(self):
        """The ADR-0019 bug end to end: decision `outcomeIndex: 1` must pay outcome 1."""
        wager, close = self._create_enumerated(["A", "B"])
        self._bet_mask_via_mcp("alice", wager, 1, 100)
        self._bet_mask_via_mcp("bob", wager, 2, 100)
        self._sync()
        self._warp(close + 1)
        report = self._run_resolution_service({wager: {"action": "resolve", "outcomeIndex": 1}}, chain_now=close + 1)
        self.assertEqual(report["succeeded"], 1, report)
        self.assertEqual(self._uint(wager, "winningMask()"), 2)

    def test_outcome_labels_reach_the_chain_and_the_api_exactly(self):
        """`cast` array parsing stored `café` as the nine characters `caf\\u00e9`."""
        labels = ["café ☕", "a,b", 'say "hi"', "back\\slash", " padded ", "--flag"]
        proposition = ' "Quoted" and trailing '
        wager, _ = self._create_enumerated(labels, ANY_OF, proposition=proposition)
        for i, label in enumerate(labels):
            onchain = self._view(wager, "outcomeText(uint256)", ["uint256"], [i], ["string"])[0]
            self.assertEqual(onchain, label)
        self.assertEqual(self._view(wager, "proposition()", [], [], ["string"])[0], proposition)
        self._sync()
        row = self._api(f"/wagers/{wager}")["wager"]
        self.assertEqual(json.loads(row["outcomes_json"]), labels)
        self.assertEqual(row["proposition"], proposition)

    def test_freeform_every_awkward_answer_settles_through_the_service(self):
        """The bug behind ADR-0020 O0: `cast` turned these into different answers, so the service could
        have resolved another pool. Each runs through a decision file and the real service."""
        for winner in (" Paris ", "Paris ", '"Paris"', "'Paris'", "--help", "--gas-limit=1", "-5", "café ☕"):
            with self.subTest(winner=winner):
                wager, close = self._create_freeform()
                # The plain "Paris" pool is what `cast` would have wrongly resolved to.
                self._bet_answer_via_mcp("alice", wager, winner, 700)
                self._bet_answer_via_mcp("bob", wager, "Paris", 300)
                self._sync()

                detail = self._api(f"/wagers/{wager}")
                texts = {p["answer_text"]: p for p in detail["ticket_pools"]}
                self.assertEqual(int(texts[winner]["pool_total"]), 700)
                self.assertEqual(texts[winner]["ticket_mask"], answer_id(winner))
                self.assertEqual(int(texts["Paris"]["pool_total"]), 300)

                self._warp(close + 1)
                report = self._run_resolution_service({wager: {"action": "resolve", "winningAnswer": winner}}, chain_now=close + 1)
                self.assertEqual(report["succeeded"], 1, report)
                self.assertEqual(
                    "0x" + self._view(wager, "winningAnswerId()", [], [], ["bytes32"])[0].hex(),
                    answer_id(winner),
                    "resolved exactly the decision's bytes",
                )
                pot = 1000
                self.assertEqual(self._claim("alice", wager), pot - pot * TOTAL_BPS // 10_000)
                self._sync()
                self.assertEqual(self._api(f"/wagers/{wager}")["totals"]["total_winning_stake"], "700")

    def test_control_panel_resolve_is_byte_exact_on_chain(self):
        wager, close = self._create_freeform()
        self._bet_answer_via_mcp("alice", wager, '"exact" ', 5)
        self._warp(close + 1)
        cmd = build_wager_action_command(
            wager=wager, action="resolve", protocol_version="freeform", winning_answer='"exact" ',
            rpc_url=self.rpc, private_key=KEYS["resolver"],
        )
        result = run_cast_send(cmd.command)
        self.assertTrue(result.ok, result.stderr)
        self.assertEqual("0x" + self._view(wager, "winningAnswerId()", [], [], ["bytes32"])[0].hex(), answer_id('"exact" '))

    def test_scout_recommendation_is_directly_executable(self):
        """A recommendation for a freeform wager used to be unusable: the scout knew only a hash."""
        wager, _ = self._create_freeform()
        self._bet_answer_via_mcp("alice", wager, " spaced answer ", 100)
        self._sync()
        client = IndexerClient(self.api_url)
        quote = scout_planner.quote_wager(client, wager_address=wager, outcome_index=0, bet_amount_raw=5, freeform_answer=" spaced answer ")
        call = quote["quote"]["placeBet"]
        self.assertEqual(int(quote["outcome_total_raw"]), 100)
        self._approve("bob", wager)
        self._send(KEYS["bob"], call["to"], call["calldata"])
        pool = self._uint(wager, "ticketPoolByAnswerId(bytes32)", ["bytes32"], [bytes.fromhex(answer_id(" spaced answer ")[2:])])
        self.assertEqual(pool, 105, "the scout's calldata landed in the same pool")

    def test_min_new_ticket_stake_end_to_end(self):
        wager, _ = self._create_enumerated(["A", "B", "C"], ANY_OF, min_new_ticket_stake=500)
        self._sync()
        self.assertEqual(self._api(f"/wagers/{wager}")["wager"]["min_new_ticket_stake"], "500")
        self._approve("alice", wager)
        low = self._encode("placeBet(uint256,uint256)", ["uint256", "uint256"], [3, 499])
        self.assertFalse(self._send(KEYS["alice"], wager, low, expect_ok=False).ok)
        self._bet_mask_via_mcp("alice", wager, 3, 500)
        self._bet_mask_via_mcp("bob", wager, 3, 1)
        self.assertEqual(self._uint(wager, "ticketPoolByMask(uint256)", ["uint256"], [3]), 501)

    def test_mined_revert_is_reported_as_failure(self):
        """`cast send` exits 0 for this. It needs an explicit gas limit, because otherwise estimation
        fails first; on a live chain the same happens when state changes after estimation."""
        wager, _ = self._create_freeform()
        data = self._encode("expire()", [], [])
        argv = cast_send_argv(to=wager, calldata=data, rpc_url=self.rpc, private_key=KEYS["alice"]) + ["--gas-limit", "200000"]
        raw = subprocess.run(argv, capture_output=True, text=True)
        self.assertEqual(raw.returncode, 0, "the premise: cast reports success")
        receipt, _ = json.JSONDecoder().raw_decode(raw.stdout[raw.stdout.index("{"):])
        self.assertEqual(receipt["status"], "0x0", "the premise: the transaction reverted")
        result = run_cast_send(argv)
        self.assertFalse(result.ok)
        self.assertIn("reverted", result.stderr)

    def test_sweeper_expires_exactly_what_is_due_and_converges(self):
        wager, close = self._create_freeform()
        self._bet_answer_via_mcp("alice", wager, "x", 1000)
        self._sync()
        at = close + 501
        self.assertEqual(sweeper.sweep_once(db_path=self.db_path, rpc_url=self.rpc, private_key=KEYS["carol"], now_ts=close + 500, execute=True).attempted, self._due(close + 500))
        self._warp(at + 1)
        result = sweeper.sweep_once(db_path=self.db_path, rpc_url=self.rpc, private_key=KEYS["carol"], now_ts=at + 1, execute=True)
        self.assertGreaterEqual(result.succeeded, 1)
        self.assertEqual(self._uint(wager, "state()"), 2, "Retracted")
        self._sync()
        self.assertEqual(self._api(f"/wagers/{wager}")["wager"]["state"], "RETRACTED")
        self.assertEqual(self._claim("alice", wager), 1000 - 1000 * TOTAL_BPS // 10_000)
        # A second pass finds nothing left to do on this wager.
        rows = [r["wager_address"] for r in ix.get_expire_candidates(self.conn, now_ts=at + 2)]
        self.assertNotIn(wager.lower(), rows)

    def _due(self, now: int) -> int:
        return len(ix.get_expire_candidates(self.conn, now_ts=now))

    def test_expire_boundary_agrees_with_the_indexer(self):
        """The indexer's expire-candidate rule must flip at exactly the second the contract's does."""
        wager, close = self._create_freeform()
        self._bet_answer_via_mcp("alice", wager, "x", 10)
        self._sync()
        deadline = close + 500

        self._warp(deadline - 1)
        self.assertFalse(self._send(KEYS["carol"], wager, self._encode("expire()", [], []), expect_ok=False).ok)
        self.assertNotIn(wager.lower(), [r["wager_address"] for r in ix.get_expire_candidates(self.conn, now_ts=deadline)])

        self.assertIn(wager.lower(), [r["wager_address"] for r in ix.get_expire_candidates(self.conn, now_ts=deadline + 1)])
        ix.rpc_call(self.rpc, "evm_setNextBlockTimestamp", [hex(deadline + 1)])
        self.assertTrue(self._send(KEYS["carol"], wager, self._encode("expire()", [], [])).ok)

    def test_early_close_moves_the_deadline_for_every_layer(self):
        close_far = self._now() + 100_000
        cmd = build_create_freeform_wager_command(
            factory=self.factory, collateral=self.token, proposition="Early?", betting_close_time=close_far,
            resolution_window=500, resolver=self.addr["resolver"], betting_closer=self.addr["carol"], resolution_closer=ZERO,
            extra_recipients=[], extra_bps=[], rpc_url=self.rpc, private_key=KEYS["deployer"],
        )
        result = run_cast_send(cmd.command)
        wager = self._new_wager_from_receipt(result.stdout)
        self._bet_answer_via_mcp("alice", wager, "x", 10)
        closed = run_cast_send(build_wager_action_command(wager=wager, action="close-betting", rpc_url=self.rpc, private_key=KEYS["carol"]).command)
        self.assertTrue(closed.ok, closed.stderr)
        self._sync()
        closed_at = self._uint(wager, "bettingClosedAtByAuthority()")
        row = self._api(f"/wagers/{wager}")["wager"]
        self.assertEqual(row["betting_closed_at"], closed_at)
        self.assertEqual(row["resolution_deadline"], close_far + 500, "the immutable keeps its original value")
        self.assertIn(wager.lower(), [r["wager_address"] for r in ix.get_expire_candidates(self.conn, now_ts=closed_at + 501)])
        self._warp(closed_at + 501)
        self.assertTrue(self._send(KEYS["carol"], wager, self._encode("expire()", [], [])).ok)

    def test_proposition_dispatch_creates_a_real_wager(self):
        result = proposition_dispatch.dispatch_proposal(
            proposition="Headline — corroborated? ", outcomes=["Oui", "Non"], factory=self.factory, collateral=self.token,
            rpc_url=self.rpc, private_key=KEYS["deployer"], betting_close_time=self._now() + 1000, resolution_window=100,
            resolver=self.addr["resolver"], betting_closer=ZERO, resolution_closer=ZERO, extra_recipients=[], extra_bps=[],
        )
        self.assertTrue(result["ok"], result)
        wager = self._new_wager_from_receipt(result["stdout"])
        self.assertEqual(self._view(wager, "proposition()", [], [], ["string"])[0], "Headline — corroborated? ")

    def test_griefed_resolve_fits_the_real_per_transaction_gas_cap(self):
        """C1, in a real transaction on a chain enforcing EIP-7825, with no test-harness warm slots."""
        numOptions = 255
        full = (1 << numOptions) - 1
        wager, close = self._create_enumerated(["o"] * numOptions, WEIGHTED_OVERLAP)
        self._approve("carol", wager)
        placed = 0
        seq = 3
        while placed < 1024:
            size = min(64, 1024 - placed)
            masks = [full ^ (seq + i) for i in range(size)]
            seq += size
            data = self._encode("placeBets(uint256[],uint256[])", ["uint256[]", "uint256[]"], [masks, [1] * size])
            self._send(KEYS["carol"], wager, data)
            placed += size
        for i in range(numOptions):
            self._send(KEYS["carol"], wager, self._encode("placeBet(uint256,uint256)", ["uint256", "uint256"], [1 << i, 1]))
        self.assertEqual(self._uint(wager, "usedMasksCount()"), 1024 + numOptions)
        self._warp(close + 1)
        cmd = build_wager_action_command(wager=wager, action="resolve", winning_mask=full, rpc_url=self.rpc, private_key=KEYS["resolver"])
        result = run_cast_send(cmd.command)
        self.assertTrue(result.ok, result.stderr)
        receipt, _ = json.JSONDecoder().raw_decode(result.stdout[result.stdout.index("{"):])
        gas_used = int(receipt["gasUsed"], 16)
        print(f"\n  worst-case griefed resolve, real tx: {gas_used:,} gas")
        self.assertLess(gas_used, TX_GAS_CAP)

    def test_indexer_ignores_a_contract_spoofing_our_topics(self):
        """Any contract can emit the wager event topics. With address-filtered queries they never even
        reach the indexer. The token here stands in for such a contract: this asserts the filter sent."""
        seen = []
        real = ix.rpc_call

        def recording(url, method, params):
            if method == "eth_getLogs":
                seen.append(params[0])
            return real(url, method, params)

        with mock.patch.object(ix, "rpc_call", recording):
            self._sync()
        self.assertTrue(all("address" in f for f in seen))
        for f in seen:
            self.assertNotIn(self.token.lower(), [a.lower() for a in f["address"]])


if __name__ == "__main__":
    unittest.main()
