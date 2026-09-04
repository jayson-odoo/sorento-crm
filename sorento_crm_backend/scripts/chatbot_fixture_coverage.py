#!/usr/bin/env python3
"""Regenerate `tests/chatbot/COVERAGE.md` - the fixture-coverage matrix (AC-008).

REPORT ONLY. This script reads what has already been captured; it never talks to n8n and
never captures anything. Fresh captures come from the n8n repo's own
`scripts/capture-fixtures.py` recipe, run against real live executions, because a
hand-written fixture proves the port agrees with whoever wrote the fixture and nothing
else.

Cutover gate 0 is what this report serves: before a slice PR opens, every branch of every
node that slice ports needs at least 5 real captures. An empty cell blocks the slice. The
report says which cells are short; the fix is always more captures, never a lowered bar.

Usage::

    python scripts/chatbot_fixture_coverage.py            # write the file
    python scripts/chatbot_fixture_coverage.py --check     # exit 1 if it is stale
    CHATBOT_FIXTURES_DIR=... python scripts/chatbot_fixture_coverage.py
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from tests.chatbot import _corpus  # noqa: E402

OUTPUT = BACKEND_ROOT / "tests" / "chatbot" / "COVERAGE.md"

# Gate 0's bar. Not a knob: it is the owner's stated floor.
CAPTURES_PER_BRANCH = 5

# What the capture agent actually scanned, per workflow, so "short" can be told apart from
# "there is no more to capture".
#
# `version_pool` is the number of live executions ON `version` - the only ones that can be
# graded against the body the export ships. `scanned` is how many of those were actually
# captured. `all_versions` is every execution the instance still holds, recorded for
# context only; the difference ran on OLDER workflow versions.
#
# **`exhausted` is earned by `scanned == version_pool`, not by appearing in this table.**
# A node whose pool was only partly scanned is SHORT and blocks, exactly as it should: the
# missing captures might be there and nobody looked. That distinction is the whole value of
# the state, and granting it by membership would have made the table a rubber stamp.
CAPTURE_REPORT: dict[str, dict] = {
    "spine-rs-1a": {
        "version": "51f7b0d2",
        "version_pool": 567,
        "scanned": 567,
        "all_versions": 946,
        "captured_on": "2026-09-04",
        "nodes": ("route-turn", "build-ctx"),
    },
    "sub-semantic-parser": {
        "version": "ab3ec985",
        "version_pool": 239,
        "scanned": 239,
        "all_versions": 3901,
        "captured_on": "2026-09-04",
        "nodes": ("output_exchange", "suggest-follow-up"),
    },
}

# Branches that CANNOT be captured because live never reaches them. H1: the spine tests
# `intent_hint === 'stock_check'` while the parser emits `check_stock`, so these two arms
# have never fired in production - 0 captures is the CORRECT number, and the port covers
# them with unit tests behind `chatbot_stock_denial_enabled` instead (AC-306, R1).
DEAD_BY_VOCABULARY: dict[tuple[str, str], str] = {
    ("route-turn", "demand_qty"): "H1: live tests `stock_check`, the parser emits `check_stock`",
    ("route-turn", "stock_denied"): "H1: live tests `stock_check`, the parser emits `check_stock`",
}


def _pool_for(node: str) -> dict | None:
    for report in CAPTURE_REPORT.values():
        if node in report["nodes"]:
            return report
    return None


def _pool_is_exhausted(report: dict | None) -> bool:
    """Was every execution on the current workflow version actually captured?"""
    return report is not None and report["scanned"] >= report["version_pool"]


def _cell_state(node: str, branch: str, real: int) -> tuple[str, bool]:
    """`(state, blocks_the_slice)` for one coverage cell."""
    if (node, branch) in DEAD_BY_VOCABULARY:
        return "dead by vocabulary", False
    if real >= CAPTURES_PER_BRANCH:
        return "met", False
    if _pool_is_exhausted(_pool_for(node)):
        # Every execution on this workflow version was captured, so this is all the
        # traffic there is and no further capturing produces more.
        return f"exhausted ({real})", False
    return "SHORT", True


def _expected_branch_kind(fixture: _corpus.Fixture) -> str | None:
    """The `branch_kind` a route-turn capture recorded."""
    for item in fixture.expected:
        kind = (item.get("json") or {}).get("branch_kind")
        if kind:
            return str(kind)
    return None


def _branch_of(fixture: _corpus.Fixture) -> str:
    """A coverage CELL for one fixture.

    `route-turn` is cut by the arm it decided, which is the vocabulary gate 0 is written
    in. The other nodes have no branch vocabulary of their own, so they are cut by the
    turn's DOMAIN, which is what actually varies the code path through them.
    """
    if fixture.node == "route-turn":
        return _expected_branch_kind(fixture) or "unknown"
    if fixture.node in ("output_exchange", "suggest-follow-up"):
        for item in fixture.expected:
            output = (item.get("json") or {}).get("output")
            if isinstance(output, dict):
                return str(output.get("domain_hint") or "no_domain")
        return "unknown"
    return "all"


def _provenance(fixture: _corpus.Fixture) -> str:
    """`runData` (a real execution said so) vs anything else (a frozen body run)."""
    source = fixture.data.get("source") or {}
    return str(source.get("expected_from") or "body-run")


def collect() -> dict:
    rows: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    totals: Counter = Counter()
    provenance: dict[str, Counter] = defaultdict(Counter)
    vendored_names: dict[str, set[str]] = defaultdict(set)

    for node in sorted(_corpus.NODE_SLUGS):
        # UNION by file stem, so a fixture that is only vendored (the world-derived
        # route-turn capture) is counted once and only once alongside the full corpus.
        seen: dict[str, _corpus.Fixture] = {}
        for fixture in _corpus.vendored(node):
            vendored_names[node].add(fixture.name)
            seen[fixture.name] = fixture
        for fixture in _corpus.full_corpus(node):
            seen.setdefault(fixture.name.split("/")[-1], fixture)
        # Seed every branch the node CAN produce, so a zero-capture arm is a visible row
        # rather than an absent one. An arm nobody has ever captured is exactly the cell
        # gate 0 exists to surface.
        for branch in _corpus.declared_branches(node):
            rows[node][branch]  # noqa: B018 - defaultdict, creates the empty cell
        for fixture in seen.values():
            rows[node][_branch_of(fixture)][_provenance(fixture)] += 1
            totals[node] += 1
            provenance[node][_provenance(fixture)] += 1
    return {
        "rows": rows,
        "totals": totals,
        "provenance": provenance,
        "vendored": {k: len(v) for k, v in vendored_names.items()},
        # NOT the absolute path: this file is committed, and every checkout resolves the
        # sibling n8n repo somewhere different, so an absolute path here makes the
        # freshness test red on someone else's machine for a reason that is not about
        # coverage at all.
        "corpus_root": "$CHATBOT_FIXTURES_DIR"
        if _corpus.corpus_root() is not None
        else "(absent - vendored subset only)",
    }


def render(data: dict) -> str:
    lines: list[str] = []
    lines.append("# Chatbot fixture coverage")
    lines.append("")
    lines.append(
        "Generated by `scripts/chatbot_fixture_coverage.py`. Do not edit by hand - re-run it. "
        "`tests/chatbot/test_coverage_fresh.py` fails when this file drifts from the corpus."
    )
    lines.append("")
    lines.append(
        f"Corpus: `{data['corpus_root']}` - the sibling n8n checkout's "
        "`n8n-workflows-init/tests/fixtures`, found by walking up from the backend or "
        "named explicitly by that environment variable."
    )
    lines.append("")
    lines.append(
        f"Gate 0 (plan, cutover ladder): every branch of every node a slice ports needs at "
        f"least **{CAPTURES_PER_BRANCH}** REAL captures (`expected_from: runData`) before that "
        "slice's PR opens. A short cell is fixed by capturing more turns with the n8n repo's "
        "`scripts/capture-fixtures.py`, never by lowering the bar or hand-writing a fixture."
    )
    lines.append("")

    # -- what was scanned, so "short" and "there is no more" are distinguishable --------- #
    lines.append("## Capture pools scanned")
    lines.append("")
    lines.append(
        "A branch under the bar is `exhausted` - not short - only when EVERY execution on "
        "the current workflow version was captured (`scanned == version pool`). Then the "
        "traffic does not exist, no further capturing produces it, and gate 0 must not "
        "block on it. A partly-scanned pool stays SHORT and blocks: the missing captures "
        "might be there and nobody looked. `all versions` is every execution the instance "
        "still holds; the difference ran on OLDER workflow versions and cannot be graded "
        "against the body the export ships."
    )
    lines.append("")
    lines.append(
        "| workflow | version | scanned | version pool | all versions | exhausted | captured | nodes |"
    )
    lines.append("| --- | --- | ---: | ---: | ---: | --- | --- | --- |")
    for slug, report in sorted(CAPTURE_REPORT.items()):
        lines.append(
            f"| `{slug}` | `{report['version']}` | {report['scanned']} | "
            f"{report['version_pool']} | {report['all_versions']} | "
            f"{'yes' if _pool_is_exhausted(report) else 'NO, partly scanned'} | "
            f"{report['captured_on']} | "
            + ", ".join(f"`{n}`" for n in report["nodes"])
            + " |"
        )
    lines.append("")

    lines.append("## Per node")
    lines.append("")
    lines.append("| node | fixtures | real captures | vendored (always run) |")
    lines.append("| --- | ---: | ---: | ---: |")
    for node in sorted(data["totals"]):
        real = data["provenance"][node].get("runData", 0)
        lines.append(
            f"| `{node}` | {data['totals'][node]} | {real} | {data['vendored'].get(node, 0)} |"
        )
    lines.append("")
    lines.append("## Per branch")
    lines.append("")
    lines.append("| node | branch | real captures | other | gate 0 |")
    lines.append("| --- | --- | ---: | ---: | --- |")
    blocking: list[str] = []
    exhausted: list[str] = []
    for node in sorted(data["rows"]):
        for branch in sorted(data["rows"][node]):
            counts = data["rows"][node][branch]
            real = counts.get("runData", 0)
            other = sum(counts.values()) - real
            state, blocks = _cell_state(node, branch, real)
            if blocks:
                blocking.append(f"{node}/{branch} ({real} of {CAPTURES_PER_BRANCH})")
            elif state.startswith("exhausted"):
                exhausted.append(f"{node}/{branch} ({real})")
            lines.append(f"| `{node}` | `{branch}` | {real} | {other} | {state} |")
    lines.append("")

    lines.append("## Gate 0 status")
    lines.append("")
    if blocking:
        lines.append(
            f"**BLOCKED: {len(blocking)} cell(s) short in a pool that was not fully scanned.** "
            "Capture more turns for: " + ", ".join(blocking) + "."
        )
    else:
        lines.append(
            "**Not blocked.** Every cell is either met, exhausted in a fully-scanned pool, "
            "or dead by vocabulary."
        )
    lines.append("")
    if exhausted:
        lines.append(
            f"Exhausted ({len(exhausted)}), under the bar with no more traffic to capture: "
            + ", ".join(sorted(exhausted))
            + "."
        )
        lines.append("")
    dead = sorted(f"{node}/{branch}" for node, branch in DEAD_BY_VOCABULARY)
    lines.append(
        "Dead by vocabulary, 0 captures is the correct number: "
        + ", ".join(dead)
        + ". These are covered by unit tests behind `chatbot_stock_denial_enabled` "
        "(AC-306, R1), never by a capture."
    )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="exit 1 when the file is stale")
    ap.add_argument("--json", action="store_true", help="print the raw counts instead")
    args = ap.parse_args()

    data = collect()
    if args.json:
        print(
            json.dumps(
                {
                    node: {branch: dict(counts) for branch, counts in branches.items()}
                    for node, branches in data["rows"].items()
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    rendered = render(data)
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != rendered:
            print(f"{OUTPUT} is stale - re-run scripts/chatbot_fixture_coverage.py")
            return 1
        return 0
    OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
