"""ADR-0022: the hosted indexer runs on an Always Free Compute Engine VM behind its old Cloud Run URL.

On Cloud Run it kept its SQLite file in `/tmp` (lost whenever the instance scaled to zero, forcing a
16-million-block replay), synced only while a request held the CPU, and ran up to three instances with
three different databases. These tests pin the replacement:

- `deploy/gce/startup.sh` runs on the VM at every boot and update. It is run here in a sandbox, with
  stubs for the metadata server and systemd, against a real git repository.
- `deploy/gce/paramutuel-indexer.service` must keep the database on persistent state and run the same
  command as the container image.
- `script/deploy/gce_indexer.sh` and `script/deploy/cloud_run_indexer_proxy.sh` are run against a stub
  `gcloud` that records every call.
"""
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STARTUP = ROOT / "deploy" / "gce" / "startup.sh"
UNIT = ROOT / "deploy" / "gce" / "paramutuel-indexer.service"
DEPLOY = ROOT / "script" / "deploy" / "gce_indexer.sh"
PROXY = ROOT / "script" / "deploy" / "cloud_run_indexer_proxy.sh"
STUB_IP = "203.0.113.7"


def _stub(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text("#!/usr/bin/env bash\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def _git(repo: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
    }
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env).stdout.strip()


def _unit_settings() -> dict[str, list[str]]:
    """`Key=value` lines of the unit, keyed by name; repeated keys (Environment=) keep every value."""
    settings: dict[str, list[str]] = {}
    for line in UNIT.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith(("#", ";", "[")) and "=" in line:
            key, value = line.split("=", 1)
            settings.setdefault(key.strip(), []).append(value.strip())
    return settings


def _unit_env() -> dict[str, str]:
    env = {}
    for value in _unit_settings().get("Environment", []):
        for pair in shlex.split(value):
            key, _, val = pair.partition("=")
            env[key] = val
    return env


class StartupScriptTests(unittest.TestCase):
    """The VM's startup script: pinned checkout, unit install, restart; and nothing at all on bad input."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(subprocess.run, ["rm", "-rf", str(self.tmp)])
        # A stand-in for the GitHub repository, with two releases of the unit file.
        self.origin = self.tmp / "origin"
        self.origin.mkdir()
        _git(self.origin, "init", "-q", "-b", "master")
        unit = self.origin / "deploy" / "gce" / "paramutuel-indexer.service"
        unit.parent.mkdir(parents=True)
        unit.write_text("[Service]\nExecStart=/bin/true # release A\n")
        _git(self.origin, "add", ".")
        _git(self.origin, "commit", "-q", "-m", "A")
        self.ref_a = _git(self.origin, "rev-parse", "HEAD")
        unit.write_text("[Service]\nExecStart=/bin/true # release B\n")
        _git(self.origin, "commit", "-q", "-am", "B")
        self.ref_b = _git(self.origin, "rev-parse", "HEAD")

        self.root = self.tmp / "root"  # stands in for the VM's /
        self.meta = self.tmp / "meta"  # one file per metadata attribute
        self.meta.mkdir()
        self.calls = self.tmp / "calls.log"
        self.stubs = stubs = self.tmp / "bin"
        stubs.mkdir()
        # curl: serve metadata attributes from files; fail like `curl -f` on a 404.
        _stub(stubs, "curl", f'f="{self.meta}/$(basename "${{@: -1}}")"; [[ -f "$f" ]] || exit 22; cat "$f"\n')
        _stub(stubs, "systemctl", f'echo "systemctl $*" >> "{self.calls}"\n')
        _stub(stubs, "apt-get", f'echo "apt-get $*" >> "{self.calls}"\n')
        self.env = {**os.environ, "PATH": f"{stubs}:{os.environ['PATH']}", "PARAMUTUEL_PREFIX": str(self.root)}

    def set_meta(self, **attrs):
        for name, value in attrs.items():
            (self.meta / name.replace("_", "-")).write_text(value)

    def run_startup(self):
        return subprocess.run(["bash", str(STARTUP)], env=self.env, capture_output=True, text=True)

    def checkout(self) -> Path:
        return self.root / "opt" / "paramutuel"

    def installed_unit(self) -> str:
        return (self.root / "etc" / "systemd" / "system" / "paramutuel-indexer.service").read_text()

    def calls_log(self) -> str:
        return self.calls.read_text() if self.calls.exists() else ""

    def test_first_boot_checks_out_the_pinned_commit_and_starts_the_service(self):
        self.set_meta(indexer_repo=str(self.origin), indexer_ref=self.ref_a)
        result = self.run_startup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(_git(self.checkout(), "rev-parse", "HEAD"), self.ref_a)
        self.assertIn("release A", self.installed_unit())
        log = self.calls_log()
        self.assertIn("systemctl daemon-reload", log)
        self.assertIn("systemctl enable", log)
        self.assertRegex(log, r"systemctl restart\b.*paramutuel-indexer")
        self.assertNotIn("apt-get", log, "git and python3 are present, so nothing is installed")

    def test_an_update_moves_to_the_new_commit_and_keeps_the_database(self):
        self.set_meta(indexer_repo=str(self.origin), indexer_ref=self.ref_a)
        self.assertEqual(self.run_startup().returncode, 0)
        state = self.root / "var" / "lib" / "paramutuel"
        state.mkdir(parents=True)
        (state / "indexer.db").write_bytes(b"sixteen million blocks of work")
        self.set_meta(indexer_ref=self.ref_b)
        result = self.run_startup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(_git(self.checkout(), "rev-parse", "HEAD"), self.ref_b)
        self.assertIn("release B", self.installed_unit())
        self.assertEqual((state / "indexer.db").read_bytes(), b"sixteen million blocks of work")

    def test_no_pinned_commit_means_nothing_runs(self):
        self.set_meta(indexer_repo=str(self.origin))
        result = self.run_startup()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("indexer-ref", result.stderr)
        self.assertNotIn("restart", self.calls_log())
        self.assertFalse(self.checkout().exists())

    def test_a_branch_name_is_refused(self):
        """A branch moves under the VM; only a full commit hash says exactly what runs."""
        self.set_meta(indexer_repo=str(self.origin), indexer_ref="master")
        result = self.run_startup()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("restart", self.calls_log())

    def test_an_unknown_commit_leaves_the_running_release_alone(self):
        self.set_meta(indexer_repo=str(self.origin), indexer_ref=self.ref_a)
        self.assertEqual(self.run_startup().returncode, 0)
        self.calls.unlink()
        self.set_meta(indexer_ref="f" * 40)
        result = self.run_startup()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(_git(self.checkout(), "rev-parse", "HEAD"), self.ref_a)
        self.assertIn("release A", self.installed_unit())
        self.assertNotIn("restart", self.calls_log())

    def test_missing_tools_are_installed(self):
        """Ubuntu minimal ships without git. Here PATH holds only what the script needs, and git appears
        only once apt-get has "installed" it."""
        self.set_meta(indexer_repo=str(self.origin), indexer_ref=self.ref_a)
        sandbox = self.tmp / "sandbox-bin"
        sandbox.mkdir()
        for tool in ("bash", "cat", "basename", "install", "ln", "python3"):
            (sandbox / tool).symlink_to(shutil.which(tool))
        for tool in ("curl", "systemctl"):
            (sandbox / tool).symlink_to(self.stubs / tool)
        _stub(sandbox, "apt-get", (
            f'echo "apt-get $*" >> "{self.calls}"\n'
            f'[[ " $* " == *" install "* ]] && ln -sf "{shutil.which("git")}" "{sandbox}/git"\n'
            'exit 0\n'
        ))
        result = subprocess.run(["bash", str(STARTUP)], env={**self.env, "PATH": str(sandbox)}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(self.calls_log(), r"apt-get .*install.*\bgit\b")
        self.assertEqual(_git(self.checkout(), "rev-parse", "HEAD"), self.ref_a)


class UnitFileTests(unittest.TestCase):
    def test_the_database_lives_on_persistent_state(self):
        """`/tmp` is what lost the index on Cloud Run; the systemd state directory survives reboots."""
        settings, env = _unit_settings(), _unit_env()
        state_dir = settings["StateDirectory"][0]
        db_path = env["INDEXER_DB_PATH"]
        self.assertTrue(db_path.startswith(f"/var/lib/{state_dir}/"), db_path)
        self.assertFalse(db_path.startswith("/tmp"))

    def test_it_runs_the_container_command(self):
        """Two hosting paths must not drift into two different indexers."""
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        cmd = json.loads(re.search(r"(?m)^CMD\s+(\[.*\])\s*$", dockerfile).group(1))
        exec_start = shlex.split(_unit_settings()["ExecStart"][0])
        self.assertEqual(Path(exec_start[0]).name, "python3")
        self.assertEqual(exec_start[1:3], cmd[1:3])  # -m service.indexer.live_api

        def flag(argv, name):
            return argv[argv.index(name) + 1]

        for name in ("--network", "--deployments-config-path"):
            self.assertEqual(flag(exec_start, name), flag(cmd, name), name)
        self.assertEqual(flag(exec_start, "--port"), "8080")

    def test_chunks_fit_the_public_rpc_and_no_secret_is_needed(self):
        """sepolia.base.org answers `eth_getLogs is limited to a 200 range` to anything wider."""
        env = _unit_env()
        self.assertLessEqual(int(env["INDEXER_CHUNK_SIZE"]), 200)
        self.assertEqual(env["RPC_URL_BASE_SEPOLIA"], "https://sepolia.base.org")

    def test_it_runs_unprivileged_and_restarts(self):
        settings = _unit_settings()
        self.assertEqual(settings.get("DynamicUser"), ["yes"])
        self.assertEqual(settings.get("Restart"), ["always"])


class GcloudStub:
    """A `gcloud` that logs each call and answers `describe` for the resources listed as existing."""

    def __init__(self, tmp: Path, existing: tuple[str, ...] = ()):
        self.log = tmp / "gcloud.log"
        self.files = tmp / "metadata-files"
        state = tmp / "state"  # one file per resource that exists; `create` adds one
        state.mkdir()
        for name in existing:
            (state / name).touch()
        _stub(tmp, "gcloud", (
            f'echo "$*" >> "{self.log}"\n'
            # Keep a copy of any --metadata-from-file source so tests can read what was sent.
            'for a in "$@"; do case "$a" in --metadata-from-file=*) f="${a#*=}"; f="${f#*=}"; '
            f'cp "$f" "{self.files}";; esac; done\n'
            'case "$*" in\n'
            f'  *"addresses create"*) touch "{state}/address";;\n'
            f'  *"firewall-rules create"*) touch "{state}/firewall";;\n'
            f'  *"instances create"*) touch "{state}/instance";;\n'
            f'  *"addresses describe"*) [[ -f "{state}/address" ]] || exit 1; echo {STUB_IP};;\n'
            f'  *"firewall-rules describe"*) [[ -f "{state}/firewall" ]] || exit 1;;\n'
            f'  *"instances describe"*) [[ -f "{state}/instance" ]] || exit 1;;\n'
            'esac\n'
        ))

    def calls(self) -> list[str]:
        return self.log.read_text().splitlines() if self.log.exists() else []


class DeployScriptTests(unittest.TestCase):
    REF = "a" * 40

    def run_deploy(self, existing=(), ref=REF):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(subprocess.run, ["rm", "-rf", str(tmp)])
        stub = GcloudStub(tmp, existing)
        env = {**os.environ, "PATH": f"{tmp}:{os.environ['PATH']}", "GCP_PROJECT_ID": "proj", "INDEXER_REF": ref}
        result = subprocess.run(["bash", str(DEPLOY)], env=env, capture_output=True, text=True, cwd=ROOT)
        return result, stub

    def test_a_first_deploy_creates_a_free_tier_vm_pinned_to_the_commit(self):
        result, stub = self.run_deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = stub.calls()
        create = [c for c in calls if "instances create" in c]
        self.assertEqual(len(create), 1, calls)
        vm = create[0]
        self.assertIn("--machine-type=e2-micro", vm)
        self.assertRegex(vm, r"--zone=(us-west1|us-central1|us-east1)-[a-z]\b")
        self.assertIn("--boot-disk-type=pd-standard", vm)
        size = int(re.search(r"--boot-disk-size=(\d+)GB", vm).group(1))
        self.assertLessEqual(size, 30)  # the free tier's 30 GB-months
        self.assertIn("--no-service-account", vm)
        self.assertIn(f"indexer-ref={self.REF}", vm)
        self.assertIn(f"--address={STUB_IP}", vm)
        self.assertEqual(stub.files.read_text(), STARTUP.read_text())
        self.assertTrue(any("addresses create" in c for c in calls))
        firewall = [c for c in calls if "firewall-rules create" in c]
        self.assertEqual(len(firewall), 1)
        self.assertIn("--allow=tcp:8080", firewall[0])
        self.assertIn("--target-tags=paramutuel-indexer", firewall[0])
        self.assertTrue(all("--project=proj" in c for c in calls))

    def test_a_redeploy_updates_the_pin_and_reruns_startup_without_recreating(self):
        result, stub = self.run_deploy(existing=("address", "firewall", "instance"))
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = stub.calls()
        self.assertFalse([c for c in calls if " create " in f" {c} "], calls)
        self.assertTrue(any("add-metadata" in c and f"indexer-ref={self.REF}" in c for c in calls), calls)
        self.assertTrue(any("compute ssh" in c and "google_metadata_script_runner startup" in c for c in calls), calls)

    def test_a_ref_that_is_not_a_commit_hash_is_refused_before_any_change(self):
        result, stub = self.run_deploy(ref="master")
        self.assertNotEqual(result.returncode, 0)
        mutating = [c for c in stub.calls() if re.search(r"\b(create|add-metadata|ssh)\b", c)]
        self.assertEqual(mutating, [])


class ProxyScriptTests(unittest.TestCase):
    def test_the_public_service_becomes_a_pinned_single_instance_proxy_to_the_vm(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(subprocess.run, ["rm", "-rf", str(tmp)])
        stub = GcloudStub(tmp, existing=("address",))
        env = {**os.environ, "PATH": f"{tmp}:{os.environ['PATH']}", "GCP_PROJECT_ID": "proj"}
        result = subprocess.run(["bash", str(PROXY)], env=env, capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        deploy = [c for c in stub.calls() if "run deploy" in c]
        self.assertEqual(len(deploy), 1, stub.calls())
        call = deploy[0]
        self.assertIn("run deploy paramutuel-git", call)
        self.assertIn("--region=europe-west1", call)  # the public URL encodes the region
        self.assertRegex(call, r"--image=docker\.io/library/caddy:\d+\.\d+\.\d+\b")
        self.assertIn(f"--to,http://{STUB_IP}:8080", call)
        self.assertIn("--max-instances=1", call)
        self.assertIn("--clear-env-vars", call)  # drops the provider RPC URL the indexer image carried
        self.assertIn("--allow-unauthenticated", call)

    def test_no_vm_address_means_no_deploy(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(subprocess.run, ["rm", "-rf", str(tmp)])
        stub = GcloudStub(tmp)
        env = {**os.environ, "PATH": f"{tmp}:{os.environ['PATH']}", "GCP_PROJECT_ID": "proj"}
        result = subprocess.run(["bash", str(PROXY)], env=env, capture_output=True, text=True, cwd=ROOT)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse([c for c in stub.calls() if "run deploy" in c])


class OldRedeployScriptTests(unittest.TestCase):
    """`redeploy_cloud_run_indexer.sh` defaulted to `paramutuel-git`, which is now the proxy. Following
    the old runbook would have replaced it with the in-memory indexer the VM exists to avoid."""

    def run_old(self, **env_overrides):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(subprocess.run, ["rm", "-rf", str(tmp)])
        stub = GcloudStub(tmp)
        env = {**os.environ, "PATH": f"{tmp}:{os.environ['PATH']}", "GCP_PROJECT_ID": "proj"}
        env.pop("GCP_SERVICE", None)
        env.update(env_overrides)
        script = ROOT / "script" / "deploy" / "redeploy_cloud_run_indexer.sh"
        return subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True, cwd=ROOT), stub

    def test_no_default_service(self):
        result, stub = self.run_old()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("gce_indexer.sh", result.stderr)
        self.assertEqual(stub.calls(), [])

    def test_the_public_proxy_is_refused(self):
        result, stub = self.run_old(GCP_SERVICE="paramutuel-git")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ADR-0022", result.stderr)
        self.assertEqual(stub.calls(), [])

    def test_a_named_standalone_service_still_deploys(self):
        result, stub = self.run_old(GCP_SERVICE="my-indexer")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any(c.startswith("run deploy my-indexer") and "--source=." in c for c in stub.calls()), stub.calls())


if __name__ == "__main__":
    unittest.main()
