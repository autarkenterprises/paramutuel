#!/usr/bin/env python3
"""Revert-path coverage backstop for the Solidity contracts (ADR-0019 / LESSONS L-009).

`forge coverage` cannot instrument `ParamutuelWagerV3` (stack-too-deep in the
17-argument constructor's ABI decoder, even under `--ir-minimum`; see
docs/COVERAGE-BASELINE.md), so branch coverage of the contracts is invisible
to tooling. That gap let commit b2a2f28 delete every test of the V3 lifecycle
/ access-control guards unnoticed.

This check is the cheap structural substitute: every custom error raised with
`revert Name()` and every string `require(..., "REASON")` in `src/**/*.sol`
must be named by at least one `vm.expectRevert(...)` in `test/**/*.sol`
(as `.Name.selector` or `bytes("REASON")`). It proves a test *targets* each
revert path; test/ParamutuelV3Lifecycle.t.sol plus the mutation run recorded
in docs/ADR-0019-IMPLEMENTATION.md prove those tests are behavioural.

Usage: python3 script/check-revert-coverage.py [--src DIR] [--test DIR]
Exit 0 when every revert reason is asserted, 1 otherwise (missing names listed).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# `revert Name();` / `revert Name(args)` — custom errors actually raised.
REVERT_RE = re.compile(r"\brevert\s+([A-Z][A-Za-z0-9_]*)\s*\(")
# `require(cond, "REASON")` — string reasons.
REQUIRE_RE = re.compile(r"\brequire\s*\([^;]*?,\s*\"([^\"]+)\"\s*\)")
# What a test must contain to count as asserting the reason.
EXPECT_SELECTOR_RE = re.compile(r"expectRevert\(\s*[A-Za-z0-9_]+\.([A-Za-z0-9_]+)\.selector")
EXPECT_STRING_RE = re.compile(r"expectRevert\(\s*bytes\(\s*\"([^\"]+)\"\s*\)")


def _read_all(directory: Path) -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(directory.rglob("*.sol")))


def revert_reasons(src_text: str) -> tuple[set[str], set[str]]:
    """Return (custom error names, require strings) raised in the sources."""
    return set(REVERT_RE.findall(src_text)), set(REQUIRE_RE.findall(src_text))


def asserted_reasons(test_text: str) -> tuple[set[str], set[str]]:
    """Return (error names, strings) that some `vm.expectRevert` targets."""
    return set(EXPECT_SELECTOR_RE.findall(test_text)), set(EXPECT_STRING_RE.findall(test_text))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", type=Path, default=ROOT / "src")
    ap.add_argument("--test", type=Path, default=ROOT / "test")
    args = ap.parse_args(argv)

    errors, strings = revert_reasons(_read_all(args.src))
    t_errors, t_strings = asserted_reasons(_read_all(args.test))
    missing = sorted(errors - t_errors) + sorted(f'"{s}"' for s in strings - t_strings)
    if missing:
        print("Revert paths in src/ with no asserting vm.expectRevert in test/:")
        for name in missing:
            print(f"  - {name}")
        return 1
    print(f"revert coverage OK: {len(errors)} custom errors, {len(strings)} require strings asserted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
