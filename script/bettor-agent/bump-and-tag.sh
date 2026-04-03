#!/usr/bin/env bash
set -euo pipefail
# Bump agents.paramutuel_bettor __version__ and prepare a release tag for CI publish.
#
# Usage (from repo root):
#   ./script/bettor-agent/bump-and-tag.sh 0.3.0
#
# Then:
#   git add agents/paramutuel_bettor/__init__.py
#   git commit -m "Release paramutuel-bettor-agent 0.3.0"
#   git tag bettor-agent-v0.3.0
#   git push origin HEAD bettor-agent-v0.3.0

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

NEW="${1:?new version required e.g. 0.3.0}"

export BETTOR_NEW_VERSION="$NEW"
python3 - <<'PY'
import os
import re
from pathlib import Path

new = os.environ["BETTOR_NEW_VERSION"]
path = Path("agents/paramutuel_bettor/__init__.py")
text = path.read_text(encoding="utf-8")
out, n = re.subn(
    r'__version__\s*=\s*"[^"]+"',
    f'__version__ = "{new}"',
    text,
    count=1,
)
if n != 1:
    raise SystemExit("could not find __version__ line")
path.write_text(out, encoding="utf-8")
PY

echo "Updated __version__ to $NEW"
echo "Next: git commit && git tag bettor-agent-v$NEW && git push origin HEAD bettor-agent-v$NEW"
