#!/usr/bin/env python3
"""Fail when a tracked file holds personal data. The repo is PUBLIC.

Flags, in every tracked text file:
  - a Malaysian mobile number (+60 1x / 60 1x / 01x, spaces or dashes allowed)
    that is not an agreed fake value (see `is_fake_phone`);
  - a lorry plate written next to a plate label ("Lorry Plate", lorry_plate,
    vehicle no) that is not a fake `PLATE-<n>`;
  - a tracked raw capture path (`.playwright-mcp/`, `*.har`, `*.rdb`), which
    carries prod-copy pages, auth headers or queue payloads.

Use fake values in fixtures, tests and docs: phones `+60100000001`-style (a
`0000` run after the 601x prefix) or the classic `012-345 6789`; plates
`PLATE-1`; names `CUSTOMER A`, `DRIVER B`, `CONTACT C`; emails
`*@example.com`. Findings print the path, line and kind only, never the value.

Stdlib only, so the CI fast gate runs it without installing anything:
    python3 scripts/pii_guard.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Optional +60 / 60 / 0 trunk prefix, then 1x, then 7 or 8 subscriber digits.
# The lookarounds keep a match from starting or ending inside a longer number.
_PHONE = re.compile(
    r"(?<![\w+])(?:\+?60[\s-]?|0)(1\d)[\s-]?(\d{3,4})[\s-]?(\d{4})(?!\d)"
)

_PLATE_LABEL = r"(?:lorry[\s_]?plate|vehicle[\s_]?(?:no|number)|no\.?\s?kenderaan)"
_PLATE = re.compile(
    _PLATE_LABEL
    + r"[^A-Za-z0-9\n]{0,25}(?:value[^A-Za-z0-9\n]{0,8})?"
    + r"([A-Z]{1,3}\s?\d{1,4}(?:\s?[A-Z]{1,2})?)(?![A-Za-z0-9-])",
    re.IGNORECASE,
)

_RUNS = ("01234", "12345", "23456", "34567", "45678", "56789", "98765", "87654", "76543", "65432")

_FORBIDDEN_PREFIXES = (".playwright-mcp/",)
_FORBIDDEN_SUFFIXES = (".har", ".rdb")

_BINARY_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".xlsx", ".xls",
    ".woff", ".woff2", ".ttf", ".otf", ".zip", ".gz", ".mp4", ".mov", ".svg",
)
# This guard's own sources describe the patterns.
_SKIP = ("scripts/pii_guard.py",)


@dataclass(frozen=True)
class Finding:
    kind: str
    line: int


def is_fake_phone(digits: str) -> bool:
    """True for an agreed fake: after the 601x prefix, a zero run of four or a
    five-digit ascending/descending run (0123456789-style), or one digit four
    times in a row."""
    sub = re.sub(r"\D", "", digits)
    if sub.startswith("0"):
        sub = "6" + sub
    tail = sub[4:]
    if "0000" in tail or any(r in sub[3:] for r in _RUNS):
        return True
    return re.search(r"(\d)\1{3}", tail) is not None


def scan_text(text: str) -> list[Finding]:
    found: list[Finding] = []
    for lineno, line in enumerate(text.split("\n"), 1):
        for m in _PHONE.finditer(line):
            if not is_fake_phone("601" + m.group(1)[1] + m.group(2) + m.group(3)):
                found.append(Finding("phone", lineno))
        for _ in _PLATE.finditer(line):
            found.append(Finding("plate", lineno))
    return found


def forbidden_path(path: str) -> bool:
    return path.startswith(_FORBIDDEN_PREFIXES) or path.endswith(_FORBIDDEN_SUFFIXES)


def format_finding(path: str, finding: Finding) -> str:
    return f"{path}:{finding.line}: {finding.kind}"


def scan_repo(root: Path) -> list[tuple[str, Finding]]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True
    ).stdout.decode()
    problems: list[tuple[str, Finding]] = []
    for path in filter(None, out.split("\0")):
        if forbidden_path(path):
            problems.append((path, Finding("raw-capture-path", 0)))
            continue
        if path in _SKIP or path.lower().endswith(_BINARY_SUFFIXES):
            continue
        try:
            text = (root / path).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        problems.extend((path, f) for f in scan_text(text))
    return problems


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    problems = scan_repo(root)
    for path, finding in problems:
        print(format_finding(path, finding))
    if problems:
        print(
            f"pii-guard: {len(problems)} finding(s). The repo is public: replace with "
            "fake values (see scripts/pii_guard.py docstring).",
            file=sys.stderr,
        )
        return 1
    print("pii-guard: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
