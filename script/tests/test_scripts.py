"""ADR-0020: operational scripts rot silently because nothing runs them until the day they are needed.

`launch_testnet.sh` deployed through a script deleted months earlier, and the Cloud Run redeploy used a
`gcloud` flag that does not exist. These checks keep such failures from waiting for a real deployment.
"""
import json
import os
import re
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def shell_scripts():
    return sorted(p for p in (ROOT / "script").rglob("*.sh")) + sorted((ROOT / "deploy").rglob("*.sh"))


class StaticChecks(unittest.TestCase):
    def test_every_shell_script_parses(self):
        scripts = shell_scripts()
        self.assertGreater(len(scripts), 10)
        for script in scripts:
            with self.subTest(script=script.name):
                subprocess.run(["bash", "-n", str(script)], check=True, capture_output=True)

    def test_every_forge_script_reference_exists(self):
        """Scans scripts and docs a reader would follow."""
        pattern = re.compile(r"(?:script/|\bbroadcast/)[A-Za-z0-9_]+\.s\.sol")
        paths = shell_scripts() + list((ROOT / "docs").glob("*.md")) + [ROOT / "README.md"]
        found = 0
        for path in paths:
            if re.match(r"ADR-00\d\d", path.name):
                continue  # implementation notes are historical records
            for ref in pattern.findall(path.read_text(encoding="utf-8")):
                found += 1
                name = ref.split("/")[-1]
                with self.subTest(path=path.name, ref=ref):
                    self.assertTrue((ROOT / "script" / name).exists(), f"{path.name} references missing {ref}")
        self.assertGreater(found, 0)

    def test_gas_profile_matches_real_tests(self):
        """It filtered on the names of V1 tests deleted long ago, so it reported nothing at all."""
        text = (ROOT / "script" / "ops" / "gas-profile.sh").read_text(encoding="utf-8")
        for name in re.findall(r"\btest[A-Z][A-Za-z_]+", text):
            sources = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "test").glob("*.t.sol"))
            self.assertIn(name, sources, f"gas-profile.sh filters on a test that does not exist: {name}")


class DocumentedCommandsTest(unittest.TestCase):
    """README's CLI section once documented the deleted V1 ABI: every example reverted."""

    DOCS = ["README.md", "docs/WORKFLOWS.md", "docs/MACHINE.md", "docs/WAGER-LIFECYCLE.md", "docs/RESOLUTION-SERVICE.md"]
    # Standard token calls the docs use alongside the protocol's own.
    ERC20 = {"approve(address,uint256)", "transfer(address,uint256)", "balanceOf(address)"}

    @staticmethod
    def _canonical(item):
        def render(inp):
            if inp["type"].startswith("tuple"):
                return "(" + ",".join(render(c) for c in inp["components"]) + ")" + inp["type"][5:]
            return inp["type"]
        return f"{item['name']}({','.join(render(i) for i in item['inputs'])})"

    def _abi_signatures(self):
        signatures = set(self.ERC20)
        for name in ("ParamutuelFactoryV3", "ParamutuelWagerV3"):
            abi = json.loads((ROOT / "dapp" / "abi" / f"{name}.json").read_text())["abi"]
            signatures |= {self._canonical(i) for i in abi if i["type"] == "function"}
        return signatures

    def test_every_documented_signature_exists_in_the_abi(self):
        known = self._abi_signatures()
        # A quoted name(args) right after `cast send <target>` or `cast call <target>`.
        pattern = re.compile(r'cast (?:send|call)\s+(?:\\\s*)?\S+\s+(?:\\\s*)?"([A-Za-z_]\w*\([^"]*\))')
        checked = 0
        for doc in self.DOCS:
            text = (ROOT / doc).read_text(encoding="utf-8")
            for signature in pattern.findall(text):
                checked += 1
                bare = signature.split(")(")[0].rstrip(")") + ")"
                with self.subTest(doc=doc, signature=signature):
                    self.assertIn(bare, known, f"{doc} documents a function the contracts do not have")
        self.assertGreater(checked, 8, "scanner found suspiciously few commands")

    def test_no_provider_api_key_in_tracked_docs(self):
        """A provider key sat in the public README. The pattern is the URL shape, not any one key."""
        pattern = re.compile(r"(alchemy\.com/v2/|infura\.io/v3/)[A-Za-z0-9_-]{8,}")
        tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
        for name in tracked:
            if name.startswith("lib/") or not name.endswith((".md", ".json", ".sh", ".py", ".js", ".html", ".yml", ".yaml", ".example")):
                continue
            with self.subTest(name=name):
                self.assertIsNone(pattern.search((ROOT / name).read_text(encoding="utf-8", errors="replace")))


class CloudRunRedeployTest(unittest.TestCase):
    def test_resolution_redeploy_builds_the_right_dockerfile_with_real_flags(self):
        """`gcloud builds submit` has no --file flag, so this script could never have run."""
        with tempfile.TemporaryDirectory() as tmp:
            calls = Path(tmp) / "calls.log"
            configs = Path(tmp) / "config.yaml"
            stub = Path(tmp) / "gcloud"
            stub.write_text(
                "#!/usr/bin/env bash\n"
                f'echo "$@" >> "{calls}"\n'
                'for a in "$@"; do case "$a" in --config=*) cp "${a#--config=}" '
                f'"{configs}";; --file*) echo "unrecognized arguments: $a" >&2; exit 2;; esac; done\n'
            )
            stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
            env = {**os.environ, "PATH": f"{tmp}:{os.environ['PATH']}", "GCP_PROJECT_ID": "proj"}
            subprocess.run(
                ["bash", str(ROOT / "script" / "deploy" / "redeploy_cloud_run_resolution.sh")],
                check=True, env=env, capture_output=True, cwd=ROOT,
            )
            log = calls.read_text()
            self.assertIn("builds submit", log)
            self.assertIn("--config=", log)
            self.assertIn("run deploy", log)
            config = configs.read_text()
            self.assertIn("Dockerfile.resolution", config)
            self.assertIn("gcr.io/proj/paramutuel-resolution:latest", config)


class ContainerChecks(unittest.TestCase):
    def test_images_that_send_transactions_install_a_pinned_cast(self):
        """The resolution image had no `cast`, so it could not resolve anything and crashed at startup
        unless RESOLUTION_SERVICE_ADDRESS happened to be set."""
        for name in ("Dockerfile.resolution", "Dockerfile.proposition"):
            with self.subTest(dockerfile=name):
                text = (ROOT / name).read_text(encoding="utf-8")
                self.assertRegex(text, r"foundry_v\d+\.\d+\.\d+_linux_amd64\.tar\.gz", "pinned release")
                self.assertRegex(text, r"[0-9a-f]{64}\s+\S*foundry", "checksum verified")
                self.assertIn("/usr/local/bin", text)

    def test_indexer_image_takes_start_block_from_deployments_config(self):
        """A second copy in the Dockerfile silently overrides the config after a factory cutover."""
        self.assertNotRegex((ROOT / "Dockerfile").read_text(encoding="utf-8"), r"(?m)^ENV\s+INDEXER_FROM_BLOCK")


class LaunchScriptTest(unittest.TestCase):
    def test_set_factory_address_records_the_start_block(self):
        """A new factory with an old indexerFromBlock rescans millions of empty blocks on every cold start."""
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "deployments.json"
            config.write_text(json.dumps({"baseSepolia": {"factoryAddress": "0x0", "indexerFromBlock": 1}}))
            env = {**os.environ, "DEPLOYMENTS_CONFIG_PATH": str(config)}
            subprocess.run(
                ["bash", str(ROOT / "script" / "testnet" / "set_factory_address.sh"), "0x" + "ab" * 20, "base-sepolia", "1234"],
                check=True, env=env, capture_output=True, cwd=ROOT,
            )
            data = json.loads(config.read_text())["baseSepolia"]
            self.assertEqual(data["factoryAddress"], "0x" + "ab" * 20)
            self.assertEqual(data["indexerFromBlock"], 1234)

    def test_launch_uses_the_v3_deploy_script_and_contract_name(self):
        text = (ROOT / "script" / "testnet" / "launch_testnet.sh").read_text(encoding="utf-8")
        self.assertIn("script/DeployFactoryV3.s.sol", text)
        self.assertIn('"ParamutuelFactoryV3"', text)
        self.assertNotIn("DeployFactory.s.sol", text)


if __name__ == "__main__":
    unittest.main()
