"""The public pages in a real browser, wallet to chain (ADR-0020).

Pushing `master` deploys the site, and a person meets the protocol through these pages. The unit tests
cover their pure logic and `test_local_e2e.py` covers everything behind them, which left the wiring in
between: what a click really does. `browser/driver.mjs` drives Chrome through each flow. This file boots
the stack, then checks the outcome on the chain, because a page saying "success" proves little.

Skipped without Foundry, Node 22 or Chrome. Needs `dapp/node_modules` (`npm ci --prefix dapp`), which
holds the exact ethers file production loads. Nothing here touches a network.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time
import unittest
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import request

from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from eth_hash.auto import keccak

from service.control_panel.commands import (
    build_create_freeform_wager_command,
    build_create_wager_command,
    cast_send_argv,
    run_cast_send,
)
from service.explorer import server as explorer_server
from service.indexer import indexer as ix

ROOT = Path(__file__).resolve().parents[2]
DRIVER = Path(__file__).resolve().parent / "browser" / "driver.mjs"
ETHERS_FILE = ROOT / "dapp" / "node_modules" / "ethers" / "dist" / "ethers.umd.min.js"
ZERO = "0x" + "00" * 20
TREASURY = "0x000000000000000000000000000000000000fee1"
PROTOCOL_BPS = 100
# Contracts whose source file is not named after them. Looked up by exact path: a search by name once
# found a stale artifact of a deleted test on one machine and the real mock on another.
ARTIFACT_SOURCES = {"MockERC20": "MockTokens"}
ONE = 10**18

# Anvil's standard development accounts. Public, and worthless outside a local chain.
KEYS = {
    "deployer": "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
    "resolver": "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
    "alice": "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
    "bob": "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6",
    "carol": "0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a",
}
# Public pages that make up the site, as assembled by script/assemble-site.sh.
PAGES = [
    "index.html", "about.html", "app.html", "bet.html", "explorer.html", "operator.html", "place-a-bet.html",
    "propose-a-wager.html", "resonance.html", "resonance-bet.html", "resonance-explorer.html",
    "resonance-place.html", "resonance-propose.html", "dapp/index.html", "explorer/index.html",
]


def find_browser() -> str | None:
    return next(filter(None, map(shutil.which, ("chromium", "chromium-browser", "google-chrome", "chrome"))), None)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def answer_id(answer: str) -> bytes:
    return keccak(b"\x03" + answer.encode("utf-8"))


def encode_call(signature: str, types: list[str], values: list) -> str:
    return "0x" + (keccak(signature.encode())[:4] + abi_encode(types, values)).hex()


class QuietFiles(SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass


@unittest.skipUnless(
    all(shutil.which(tool) for tool in ("anvil", "cast", "node")) and find_browser() and ETHERS_FILE.exists(),
    "needs Foundry, Node, Chrome and `npm ci --prefix dapp`",
)
class BrowserE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="paramutuel-browser-")
        cls.rpc_port = free_port()
        cls.rpc = f"http://127.0.0.1:{cls.rpc_port}"
        # Chain 84532 is what the site expects of Base Sepolia, so its network checks run unchanged.
        cls.anvil = subprocess.Popen(
            ["anvil", "--port", str(cls.rpc_port), "--chain-id", "84532", "--silent", "--hardfork", "osaka", "--code-size-limit", "24576"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        cls._wait_for(lambda: ix.rpc_call(cls.rpc, "eth_blockNumber", []), "anvil")

        cls.addr = {
            name: subprocess.run(["cast", "wallet", "address", "--private-key", key], check=True, capture_output=True, text=True).stdout.strip()
            for name, key in KEYS.items()
        }
        cls.listed_token = cls._deploy("MockERC20")
        cls.unlisted_token = cls._deploy("MockERC20")
        ctor = abi_encode(["address", "uint16", "uint64", "uint64"], [TREASURY, PROTOCOL_BPS, 0, 0]).hex()
        cls.factory = cls._deploy("ParamutuelFactoryV3", ctor)
        for token in (cls.listed_token, cls.unlisted_token):
            for name in ("alice", "bob", "carol"):
                cls._send("deployer", token, encode_call("mint(address,uint256)", ["address", "uint256"], [cls.addr[name], 1_000 * ONE]))

        # The real read path: the same process Cloud Run runs, syncing over JSON-RPC.
        cls.api_port = free_port()
        cls.api = f"http://127.0.0.1:{cls.api_port}"
        cls.indexer_log = open(os.path.join(cls.tmp, "indexer.log"), "w")
        cls.indexer = subprocess.Popen(
            [
                "python3", "-m", "service.indexer.live_api",
                "--db-path", os.path.join(cls.tmp, "indexer.db"), "--rpc-url", cls.rpc, "--factory-address", cls.factory,
                "--from-block", "0", "--host", "127.0.0.1", "--port", str(cls.api_port),
                "--poll-interval-seconds", "1", "--confirmations", "0",
            ],
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": str(ROOT)},
            stdout=cls.indexer_log,
            stderr=subprocess.STDOUT,
        )
        cls._wait_for(lambda: request.urlopen(f"{cls.api}/health", timeout=2).read(), "indexer API")

        # The real site artifact, with only the deployment config pointed at this local stack.
        cls.site_dir = os.path.join(cls.tmp, "site")
        subprocess.run(["bash", str(ROOT / "script" / "assemble-site.sh"), cls.site_dir], check=True, capture_output=True)
        deployments = {
            "defaultNetwork": "baseSepolia",
            "baseSepolia": {"chainId": 84532, "factoryAddress": cls.factory, "indexerFromBlock": 0, "explorerApiBase": cls.api},
            "baseMainnet": {"chainId": 8453, "factoryAddress": "", "explorerApiBase": ""},
        }
        Path(cls.site_dir, "config", "deployments.json").write_text(json.dumps(deployments))
        allowlist_path = Path(cls.site_dir, "config", "collateral-allowlist.json")
        allowlist = json.loads(allowlist_path.read_text())
        allowlist["baseSepolia"]["tokens"].append(
            {"address": cls.listed_token, "symbol": "TUSD", "decimals": 18, "tier": 1, "class": "standard"}
        )
        allowlist_path.write_text(json.dumps(allowlist))
        cls.site_server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietFiles, directory=cls.site_dir))
        cls.site = f"http://127.0.0.1:{cls.site_server.server_address[1]}"
        threading.Thread(target=cls.site_server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.site_server.shutdown()
        cls.site_server.server_close()
        cls.indexer.terminate()
        cls.indexer.wait(timeout=10)
        cls.indexer_log.close()
        cls.anvil.terminate()
        cls.anvil.wait(timeout=10)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ---- Stack helpers ----

    @staticmethod
    def _wait_for(probe, what: str, timeout: float = 30.0):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            try:
                value = probe()
                if value:
                    return value
            except Exception as exc:  # noqa: BLE001 - not up yet
                last = exc
            time.sleep(0.1)
        raise AssertionError(f"timed out waiting for {what}: {last}")

    @classmethod
    def _send(cls, who: str, to: str, data: str) -> str:
        result = run_cast_send(cast_send_argv(to=to, calldata=data, rpc_url=cls.rpc, private_key=KEYS[who]))
        if not result.ok:
            raise AssertionError(f"transaction failed: {result.stderr}")
        return result.stdout

    @classmethod
    def _deploy(cls, name: str, ctor_hex: str = "") -> str:
        artifact = json.loads((ROOT / "out" / f"{ARTIFACT_SOURCES.get(name, name)}.sol" / f"{name}.json").read_text())
        proc = subprocess.run(
            ["cast", "send", "--json", "--rpc-url", cls.rpc, "--private-key", KEYS["deployer"], "--create", artifact["bytecode"]["object"] + ctor_hex],
            check=True, capture_output=True, text=True,
        )
        return json.loads(proc.stdout[proc.stdout.index("{"):].split("\n")[0])["contractAddress"]

    def view(self, to: str, signature: str, out_types: list[str], in_types: list[str] | None = None, values: list | None = None):
        data = encode_call(signature, in_types or [], values or [])
        decoded = abi_decode(out_types, bytes.fromhex(ix.rpc_call(self.rpc, "eth_call", [{"to": to, "data": data}, "latest"])[2:]))
        return decoded[0] if len(decoded) == 1 else decoded

    def balance(self, token: str, who: str) -> int:
        return self.view(token, "balanceOf(address)", ["uint256"], ["address"], [who])

    def _wager_from(self, stdout: str) -> str:
        receipt, _ = json.JSONDecoder().raw_decode(stdout[stdout.index("{"):])
        for log in receipt["logs"]:
            if log["address"].lower() == self.factory.lower():
                return "0x" + log["topics"][1][-40:]
        raise AssertionError("no creation event")

    def create_enumerated(self, token: str, *, betting_closer: str = ZERO, min_stake: int = 0, proposition: str = "Enumerated?") -> str:
        cmd = build_create_wager_command(
            factory=self.factory, collateral=token, proposition=proposition, outcomes=["Yes", "No"],
            betting_close_time=int(time.time()) + 86_400, resolution_window=86_400, resolver=self.addr["resolver"],
            betting_closer=betting_closer, resolution_closer=ZERO, extra_recipients=[], extra_bps=[],
            min_new_ticket_stake=min_stake, rpc_url=self.rpc, private_key=KEYS["alice"],
        )
        result = run_cast_send(cmd.command)
        self.assertTrue(result.ok, result.stderr)
        return self._wager_from(result.stdout)

    def create_freeform(self, token: str) -> str:
        cmd = build_create_freeform_wager_command(
            factory=self.factory, collateral=token, proposition="Freeform?", betting_close_time=int(time.time()) + 86_400,
            resolution_window=86_400, resolver=self.addr["resolver"], betting_closer=ZERO, resolution_closer=ZERO,
            extra_recipients=[], extra_bps=[], rpc_url=self.rpc, private_key=KEYS["alice"],
        )
        result = run_cast_send(cmd.command)
        self.assertTrue(result.ok, result.stderr)
        return self._wager_from(result.stdout)

    def stake_answer(self, who: str, token: str, wager: str, answer: str, amount: int) -> None:
        self._send(who, token, encode_call("approve(address,uint256)", ["address", "uint256"], [wager, amount]))
        self._send(who, wager, encode_call("placeBet(string,uint256)", ["string", "uint256"], [answer, amount]))

    def stake_mask(self, who: str, token: str, wager: str, mask: int, amount: int) -> None:
        self._send(who, token, encode_call("approve(address,uint256)", ["address", "uint256"], [wager, amount]))
        self._send(who, wager, encode_call("placeBet(uint256,uint256)", ["uint256", "uint256"], [mask, amount]))

    def api_get(self, path: str) -> dict:
        with request.urlopen(self.api + path, timeout=5) as resp:
            return json.loads(resp.read().decode())

    def wait_indexed(self, wager: str, predicate=lambda body: True) -> dict:
        def probe():
            body = self.api_get(f"/wagers/{wager.lower()}")
            return body if predicate(body) else None

        return self._wait_for(probe, f"indexer to reflect {wager}", timeout=30)

    def drive(self, scenario: str, **params) -> dict:
        cfg = {
            "site": self.site, "rpc": self.rpc, "browser": find_browser(), "ethersFile": str(ETHERS_FILE),
            "factory": self.factory, "listedToken": self.listed_token, "unlistedToken": self.unlisted_token,
            "accounts": self.addr, **params,
        }
        proc = subprocess.run(["node", str(DRIVER), scenario, json.dumps(cfg)], capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            self.fail(f"browser scenario {scenario} failed:\n{proc.stdout}\n{proc.stderr}")
        result = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual(result.pop("pageErrors"), [], f"page errors in {scenario}")
        return result

    # ---- Propose ----

    def test_propose_page_creates_the_wager_it_describes_after_refusing_bad_input(self):
        """D1: the hosted propose flow was dead. W5: a mistyped resolver silently became the proposer.
        W10: an unlisted token takes an explicit choice. Each refusal sends no transaction."""
        before = self.view(self.factory, "wagersCount()", ["uint256"])
        out = self.drive("propose_enumerated", proposition="Will the launch happen on time?")
        self.assertEqual(self.view(self.factory, "wagersCount()", ["uint256"]), before + 1, "the refusals created nothing")

        wager = out["wager"]
        self.assertEqual(self.view(wager, "proposition()", ["string"]), "Will the launch happen on time?")
        self.assertEqual(self.view(wager, "MODE()", ["uint8"]), 0)
        self.assertEqual(self.view(wager, "outcomesCount()", ["uint256"]), 2)
        self.assertEqual(self.view(wager, "proposer()", ["address"]).lower(), self.addr["alice"].lower())
        self.assertEqual(self.view(wager, "resolver()", ["address"]).lower(), self.addr["resolver"].lower())
        self.assertEqual(self.view(wager, "collateralToken()", ["address"]).lower(), self.unlisted_token.lower())
        self.assertIn(wager, out["link"], "the page links to the wager it just created")

    def test_propose_page_freeform_with_a_listed_token_needs_no_consent(self):
        out = self.drive("propose_freeform", proposition="Which city hosts the final?")
        self.assertEqual(self.view(out["wager"], "MODE()", ["uint8"]), 1)
        self.assertEqual(self.view(out["wager"], "collateralToken()", ["address"]).lower(), self.listed_token.lower())

    def test_propose_page_follows_a_wallet_account_change(self):
        out = self.drive("propose_after_account_switch", proposition="Created after switching accounts?")
        self.assertEqual(self.view(out["wager"], "proposer()", ["address"]).lower(), self.addr["bob"].lower())
        self.assertEqual(self.view(out["wager"], "resolver()", ["address"]).lower(), self.addr["bob"].lower())

    def test_propose_page_keeps_a_resolver_the_user_chose_when_the_account_changes(self):
        out = self.drive("propose_keeps_a_chosen_resolver_after_account_switch")
        self.assertEqual(out["resolver"].lower(), self.addr["resolver"].lower())

    def test_resonance_propose_page_works_the_same_way(self):
        out = self.drive("propose_freeform", page="resonance-propose.html", proposition="A resonance question?")
        self.assertEqual(self.view(out["wager"], "proposition()", ["string"]), "A resonance question?")

    # ---- Bet ----

    def test_bet_page_stakes_exact_amounts_and_says_so(self):
        """W3: 0.0000001 went through Number() and threw. The status line used to vanish on success."""
        wager = self.create_enumerated(self.unlisted_token)
        self.wait_indexed(wager)
        self.drive("bet_enumerated", wager=wager)
        self.assertEqual(self.view(wager, "ticketPoolByMask(uint256)", ["uint256"], ["uint256"], [2]), 3 * ONE // 2)
        self.assertEqual(self.view(wager, "ticketPoolByMask(uint256)", ["uint256"], ["uint256"], [1]), 10**11)
        self.assertEqual(self.view(wager, "totalPot()", ["uint256"]), 3 * ONE // 2 + 10**11)

    def test_resonance_bet_page_stakes_the_same_way(self):
        wager = self.create_enumerated(self.unlisted_token)
        self.wait_indexed(wager)
        self.drive("bet_enumerated", wager=wager, page="resonance-bet.html")
        self.assertEqual(self.view(wager, "totalPot()", ["uint256"]), 3 * ONE // 2 + 10**11)

    def test_bet_page_follows_a_wallet_account_change(self):
        """It kept the old signer, so the page showed one account and asked to spend from another."""
        wager = self.create_enumerated(self.listed_token)
        self.wait_indexed(wager)
        self.drive("bet_after_account_switch", wager=wager)
        bets = "betsByMask(address,uint256)"
        self.assertEqual(self.view(wager, bets, ["uint256"], ["address", "uint256"], [self.addr["bob"], 1]), 3 * ONE)
        self.assertEqual(self.view(wager, bets, ["uint256"], ["address", "uint256"], [self.addr["alice"], 1]), 0)

    def test_bet_page_backs_an_existing_answer_byte_exact_and_trims_typed_ones(self):
        """Picking " Paris " must land in that pool. Trimming it would create a separate "Paris" pool."""
        wager = self.create_freeform(self.unlisted_token)
        self.stake_answer("bob", self.unlisted_token, wager, " Paris ", 5 * ONE)
        self.wait_indexed(wager, lambda body: body["ticket_pools"])
        self.drive("bet_freeform", wager=wager)
        pool = "ticketPoolByAnswerId(bytes32)"
        self.assertEqual(self.view(wager, pool, ["uint256"], ["bytes32"], [answer_id(" Paris ")]), 6 * ONE)
        self.assertEqual(self.view(wager, pool, ["uint256"], ["bytes32"], [answer_id("Paris")]), 0)
        self.assertEqual(self.view(wager, pool, ["uint256"], ["bytes32"], [answer_id("Rome")]), 2 * ONE)
        self.assertEqual(self.view(wager, pool, ["uint256"], ["bytes32"], [answer_id("  Rome  ")]), 0)

    def test_bet_page_stays_blocked_after_betting_closes(self):
        """W1: loading the page then connecting a wallet re-enabled staking on a closed wager."""
        wager = self.create_enumerated(self.unlisted_token, betting_closer=self.addr["alice"])
        self._send("alice", wager, encode_call("closeBetting()", [], []))
        self.wait_indexed(wager, lambda body: body["wager"]["betting_closed_by_authority"] == 1)
        out = self.drive("bet_closed", wager=wager)
        self.assertIn("clos", out["status"].lower())
        self.assertEqual(self.view(wager, "totalPot()", ["uint256"]), 0)

    def test_bet_page_refuses_a_stake_below_the_minimum_before_any_approval(self):
        wager = self.create_enumerated(self.unlisted_token, min_stake=ONE)
        self.wait_indexed(wager)
        self.drive("bet_below_minimum", wager=wager)
        allowance = self.view(self.unlisted_token, "allowance(address,address)", ["uint256"], ["address", "address"], [self.addr["alice"], wager])
        self.assertEqual(allowance, 0, "no approve was paid for")
        self.drive("bet_above_minimum", wager=wager)
        self.assertEqual(self.view(wager, "ticketPoolByMask(uint256)", ["uint256"], ["uint256"], [1]), 2 * ONE)

    def test_bet_page_names_a_listed_token_and_does_not_warn(self):
        wager = self.create_enumerated(self.listed_token)
        self.wait_indexed(wager)
        out = self.drive("bet_listed_token", wager=wager)
        self.assertIn("TUSD", out["symbol"])
        self.assertIs(out["warningVisible"], False)

    # ---- dApp ----

    def test_dapp_runs_a_freeform_wager_to_payout_with_exact_bytes(self):
        """W4: resolve trimmed the answer, so " Paris " could not be resolved. W7: it kept the old signer."""
        out = self.drive("dapp_create_freeform", proposition="Where is the final?")
        wager = out["wager"]
        self.assertEqual(self.view(wager, "totalFeeBps()", ["uint256"]), PROTOCOL_BPS + 250)

        self.stake_answer("bob", self.unlisted_token, wager, " Paris ", 3 * ONE)
        bob_before = self.balance(self.unlisted_token, self.addr["bob"])
        carol_before = self.balance(self.unlisted_token, self.addr["carol"])
        self.drive("dapp_finish_freeform", wager=wager)

        self.assertEqual(self.view(wager, "state()", ["uint8"]), 1, "Resolved")
        self.assertEqual(self.view(wager, "winningAnswerId()", ["bytes32"]), answer_id(" Paris "))
        pot = 4 * ONE
        fees = pot * (PROTOCOL_BPS + 250) // 10_000
        self.assertEqual(self.balance(self.unlisted_token, self.addr["bob"]) - bob_before, pot - fees, "bob, after the account switch, was paid")
        self.assertTrue(self.view(wager, "hasClaimed(address)", ["bool"], ["address"], [self.addr["bob"]]))
        self.assertFalse(self.view(wager, "hasClaimed(address)", ["bool"], ["address"], [self.addr["alice"]]), "the claim did not come from the old account")
        carol_fee = fees - pot * PROTOCOL_BPS // 10_000
        self.assertEqual(self.balance(self.unlisted_token, self.addr["carol"]) - carol_before, carol_fee, "carol withdrew her fee slice")

    def test_dapp_runs_a_seeded_multi_outcome_wager_to_payout(self):
        alice_before = self.balance(self.listed_token, self.addr["alice"])
        out = self.drive("dapp_enumerated_lifecycle", proposition="Which direction?")
        wager = out["wager"]
        self.assertEqual(self.view(wager, "payoffPolicy()", ["uint8"]), 1, "ANY_OF")
        self.assertEqual(self.view(wager, "ticketPoolByMask(uint256)", ["uint256"], ["uint256"], [4]), ONE, "seeded on outcome 2")
        self.assertEqual(self.view(wager, "ticketPoolByMask(uint256)", ["uint256"], ["uint256"], [3]), 4 * ONE, "the indices 0,1 became mask 3")
        self.assertEqual(self.view(wager, "winningMask()", ["uint256"]), 2)
        pot = 5 * ONE
        net = pot - pot * PROTOCOL_BPS // 10_000
        self.assertEqual(self.balance(self.listed_token, self.addr["alice"]) - alice_before, net - pot, "all of the net pot came back")

    # ---- Everything else a visitor sees ----

    def test_public_listings_show_real_stakes(self):
        """X1: the home ticker and the bet search said "No stakes yet" for every enumerated wager."""
        wager = self.create_enumerated(self.listed_token, proposition="A distinctive listing question?")
        self.stake_mask("bob", self.listed_token, wager, 1, 3 * ONE)
        self.stake_mask("carol", self.listed_token, wager, 2, ONE)
        self.wait_indexed(wager, lambda body: body["totals"]["total_pot"] == str(4 * ONE) and body["wager"]["metadata_complete"] == 1)
        out = self.drive("public_listings", proposition="A distinctive listing question?")
        for where in ("ticker", "search"):
            self.assertNotIn("A distinctive listing question?No stakes yet", out[where].replace("\n", ""))
            self.assertIn("Yes 75%", out[where], where)
            self.assertIn("No 25%", out[where], where)

    def test_public_listings_never_claim_no_stakes_when_the_pot_has_some(self):
        """Found by the test above, intermittently: until the indexer has read a new wager's outcome
        labels, both pages said "No stakes yet" beside a pot of 4 tokens. Pinned here by putting the
        indexer in that state on purpose."""
        wager = self.create_enumerated(self.listed_token, proposition="Labels not read yet?")
        self.stake_mask("bob", self.listed_token, wager, 1, 3 * ONE)
        self.wait_indexed(wager, lambda body: body["totals"]["total_pot"] == str(3 * ONE) and body["wager"]["metadata_complete"] == 1)
        db = sqlite3.connect(os.path.join(self.tmp, "indexer.db"), timeout=10)
        with db:
            db.execute("UPDATE wagers SET outcomes_json = '[]' WHERE wager_address = ?", (wager.lower(),))
        db.close()
        out = self.drive("public_listings", proposition="Labels not read yet?")
        for where in ("ticker", "search"):
            entry = out[where].split("Labels not read yet?", 1)[1][:120]
            self.assertNotIn("No stakes", entry, where)
        self.assertIn("Pot 3,000,000,000,000,000,000 (raw)", out["ticker"])

    def test_every_page_loads_with_its_references_and_a_verified_ethers(self):
        """D1 and D7: nothing a page references is missing, and ethers passes its integrity check."""
        out = self.drive("every_page", pages=PAGES)["pages"]
        self.assertEqual(sorted(out), sorted(PAGES))
        for path, page in out.items():
            with self.subTest(path):
                self.assertEqual(page["localFailures"], [])
                if page["declaresEthers"]:
                    self.assertTrue(page["integrity"].startswith("sha384-"))
                    self.assertEqual(page["ethers"], "object", "the script ran, so its digest matched")

    def test_explorer_finds_the_indexer_when_opened_directly(self):
        """It only worked when a parent page passed ?api=. Visited directly it said "Indexer offline"."""
        wager = self.create_enumerated(self.listed_token, proposition="Listed in the explorer?")
        self.wait_indexed(wager)
        self.drive("explorer_lists", proposition="Listed in the explorer?")
        self.drive("explorer_lists", proposition="Listed in the explorer?", path="explorer/index.html?brand=resonance")

    def test_explorer_still_works_behind_its_own_proxy(self):
        """There the API is same-origin and no deployment config is served."""
        wager = self.create_enumerated(self.listed_token, proposition="Listed through the proxy?")
        self.wait_indexed(wager)
        explorer_server.Handler.indexer_base_url = self.api
        proxy = ThreadingHTTPServer(("127.0.0.1", 0), explorer_server.Handler)
        threading.Thread(target=proxy.serve_forever, daemon=True).start()
        self.addCleanup(proxy.server_close)
        self.addCleanup(proxy.shutdown)
        self.drive(
            "explorer_lists",
            proposition="Listed through the proxy?",
            site=f"http://127.0.0.1:{proxy.server_address[1]}",
            path="",
        )

    def test_a_browser_with_no_wallet_gets_an_explanation(self):
        wager = self.create_enumerated(self.listed_token)
        self.wait_indexed(wager)
        self.drive("no_wallet", wager=wager)


if __name__ == "__main__":
    unittest.main()
