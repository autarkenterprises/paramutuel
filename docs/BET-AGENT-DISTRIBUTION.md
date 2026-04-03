# Bet scout agent — distribution, awareness, and release pipeline

This document compiles **distribution channels**, **awareness tactics**, and the **upgrade pipeline** for `paramutuel-bettor-agent` (PyPI) / `paramutuel-bettor` (CLI) and the optional **container fleet**.

## 1. Primary artifacts

| Artifact | Role |
|----------|------|
| **PyPI** `paramutuel-bettor-agent` | `pip install paramutuel-bettor-agent` → console `paramutuel-bettor` |
| **Git tag** `bettor-agent-vX.Y.Z` | Triggers PyPI + GHCR workflows (see below) |
| **GHCR image** `ghcr.io/<owner>/paramutuel-bettor-agent:<version>` | Docker / K8s / Compose fleets |
| **Git clone** | `PYTHONPATH=.` development path |
| **Raw manifest** | `https://raw.githubusercontent.com/autarkenterprises/paramutuel/master/agents/subagent-manifest.json` |

## 2. Additional distribution methods (checklist)

Use any subset; combine for reach.

### Registries and package managers

- **PyPI** (Python) — default for agents running in Python ecosystems.
- **GitHub Container Registry (GHCR)** — versioned OCI images for Compose/K8s/Cloud Run.
- **GitHub Releases** — attach `sdist`/`wheel` from CI artifacts (optional enhancement).
- **Conda / conda-forge** — if you need conda-native consumers (extra feedstock maintenance).
- **Nix flake / nixpkgs** — reproducible dev envs for advanced integrators.
- **Homebrew** (macOS) — thin formula wrapping `pipx` or shipping a tarball (maintenance cost).
- **Debian/Ubuntu PPA / apt** — rare for small libraries; only if you have distro packaging capacity.
- **Windows winget / Chocolatey** — only if you ship a standalone binary (not applicable today).

### Discovery and awareness (non-package)

- **Repository topics** on GitHub: e.g. `mcp`, `agents`, `subagent`, `parimutuel`, `prediction-markets`, `base`, `llm`, `ethereum`, `defi`.
- **Awesome-* lists** — PRs to curated agent / MCP / prediction-market lists (follow each list’s contribution rules).
- **MCP server directories** — wherever MCP servers are catalogued; list both **`paramutuel-mcp`** and the **bet scout** as complementary.
- **Blog / changelog posts** — short “how to run a scout fleet + executor pattern” linking `AGENTS.md`.
- **Discord / Farcaster / X** — release threads with tag + PyPI link.
- **Docs site** — single landing page linking `AGENTS.md`, `BET-AGENT.md`, and this file.

### Machine-readable discovery

- **`agents/subagent-manifest.json`** — stable `id`, ops, complements; fetchable without clone.
- **`AGENTS.md`** — human index; link from root `README.md` (already linked).

### Hosted execution (operators)

- **Docker Compose** — `deploy/betting-agents/docker-compose.fleet.yml` + `--scale`.
- **Kubernetes** — `deploy/betting-agents/k8s-scout-deployment.example.yaml`.
- **Cloud Run / Fly.io / ECS** — run the same image with env vars; scale instances.
- **Nomad / systemd** — run `paramutuel-bettor json` on timers.

### Enterprise / internal

- **Private PyPI** (DevPI, Artifactory, CodeArtifact) — `twine upload` mirror of the same wheel.
- **Internal Helm chart** — wrap Deployment + ServiceMonitor; pin image digest in values.

## 3. Upgrade / rollout pipeline (implemented in CI)

### Continuous integration

Workflow: **`.github/workflows/bettor-agent-ci.yml`**

- Runs on PRs / pushes touching `agents/**`, `pyproject.toml`, `deploy/betting-agents/**`.
- Executes unit tests and `python -m build`.
- Smoke-installs the wheel and runs `paramutuel-bettor --help`.

### Publishing (version gate)

1. Bump `agents/paramutuel_bettor/__init__.py` → `__version__ = "X.Y.Z"`.
2. Commit to `master`.
3. Tag **`bettor-agent-vX.Y.Z`** (must match `__version__`).

Workflows:

| Workflow | Trigger | Output |
|----------|---------|--------|
| **`bettor-agent-publish-pypi.yml`** | push tag `bettor-agent-v*` | PyPI upload via **Trusted Publishing (OIDC)** |
| **`bettor-agent-publish-ghcr.yml`** | same tag | `ghcr.io/<owner>/paramutuel-bettor-agent:X.Y.Z` + `:latest` |

### PyPI authentication

- **Preferred:** [Trusted Publishing (OIDC)](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-pypi) — configure the PyPI project to trust this repository and workflow (`Publish bet scout agent (PyPI)`).
- **Optional hardening:** wrap the publish job in a GitHub **Environment** (e.g. `pypi`) for required reviewers or deployment branches; add `environment: { name: pypi }` to the job if you use that.
- **Fallback:** add `with: password: ${{ secrets.PYPI_API_TOKEN }}` to `pypa/gh-action-pypi-publish` or run `twine upload` locally (not committed).

### Post-release

- Update **`agents/subagent-manifest.json`** `distribution` notes if URLs change (optional per release).
- Announce: PyPI version + GHCR digest; link `docs/BET-AGENT.md`.

### Helper script

`script/bettor-agent/bump-and-tag.sh` — edits `__version__`, commits, and prints the `git tag` command (see script header).

## 4. Fleet architecture (many scouts + optional executors)

**Scouts** — cheap, read-only, horizontally scaled (Compose scale, K8s replicas, Cloud Run instances). They emit JSON recommendations to logs or your telemetry pipeline.

**Executors** — separate tier with keys, rate limits, and idempotency; see **`deploy/betting-agents/EXECUTOR-PATTERN.md`**.

This split avoids putting private material in the scout image and matches safe automation practice.

## 5. References

- [`AGENTS.md`](../AGENTS.md)
- [`BET-AGENT.md`](BET-AGENT.md)
- [`deploy/betting-agents/README.md`](../deploy/betting-agents/README.md)
- [`pypa/gh-action-pypi-publish`](https://github.com/pypa/gh-action-pypi-publish)
