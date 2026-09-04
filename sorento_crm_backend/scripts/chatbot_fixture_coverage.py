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
        # Re-scanned 5 Sep: the on-version pool had grown from 567 to 581 and all 581
        # were captured (the batch also took 8 `media-gate` items, which is where the
        # media-shaped worlds come from; `media-gate` is not a ported node, so it adds
        # no cell of its own).
        "version_pool": 581,
        "scanned": 581,
        "all_versions": 946,
        "captured_on": "2026-09-05",
        "nodes": ("route-turn", "build-ctx"),
    },
    # The tail's own workflow, captured for the first time on 5 Sep. This is the pool
    # that matters for S2: `sub-output` runs the body the port implements, so unlike the
    # spine slugs it grades the port against what SHIPS rather than against an older
    # deployment. 907 executions since 1 Sep, 760 of them on the current version; all 760
    # were scanned, which is what earns `exhausted` for the arms that still read zero.
    "sub-output-live": {
        "version": "c32698c1",
        "version_pool": 760,
        "scanned": 760,
        "all_versions": 907,
        "captured_on": "2026-09-05",
        "nodes": (
            "compile-current-state",
            "crossdomain-compose",
            "build-outcome",
            "escalate-catalog",
            "cs-roster-plan",
            "build-cs-member-offer",
        ),
    },
    "sub-semantic-parser": {
        "version": "ab3ec985",
        "version_pool": 239,
        "scanned": 239,
        "all_versions": 3901,
        "captured_on": "2026-09-04",
        "nodes": ("output_exchange", "suggest-follow-up"),
    },
    # The LIVE `sub-resolve-and-gate` (`tKeQUkZK5cFK9BFa`), not the RS fork the 31 Aug
    # captures came from. Its node bodies are byte-identical to the export, so these are
    # the first captures that can grade `specific_options` and `tier_pick_domain` - the two
    # keys `tests/chatbot/_corpus.py::CAPTURE_BODY_ADDITIONS` has to strip from every older
    # capture. Every execution on the version was scanned, so a cell still under the bar is
    # exhausted, not short: the traffic does not exist. The thin ones and their real pools:
    # `access_ask` 0, `no_domain` 0, `portal_link` 1, `forms` 1, `master_products`
    # (not_found) 1, `customer-picker` 2, `resource_attachment` 2, `promotion` 3,
    # `tier-gate` 3. `build-ctx` is deliberately NOT listed: it already has a pool under
    # `spine-rs-1a`, and the one capture of it here only adds to that count.
    "sub-resolve-and-gate-rs": {
        "version": "4f367b1c",
        "version_pool": 682,
        "scanned": 682,
        "all_versions": 852,
        "captured_on": "2026-09-05",
        "nodes": (
            "disallowed-entity-gate",
            "tier-gate",
            "build-ctx-resolved",
            "annotate-incoming-picker",
            "annotate-customer-picker",
            "resolve-exit-continue",
            "resolve-exit-offer",
            "resolve-exit-not-found",
            "item",
            "sub-resolve-and-gate",
        ),
    },
}

# Branches that CANNOT be captured because live never reaches them. H1: the spine tests
# `intent_hint === 'stock_check'` while the parser emits `check_stock`, so these two arms
# have never fired in production - 0 captures is the CORRECT number, and the port covers
# them with unit tests behind `chatbot_stock_denial_enabled` instead (AC-306, R1).
DEAD_BY_VOCABULARY: dict[tuple[str, str], str] = {
    ("route-turn", "demand_qty"): "H1: live tests `stock_check`, the parser emits `check_stock`",
    ("route-turn", "stock_denied"): "H1: live tests `stock_check`, the parser emits `check_stock`",
    # The same H1 typo one node downstream: `route-turn` never emits `demand_qty`, so
    # `escalate-catalog`'s own `demand_qty` arm has never been reached either. Its copy is
    # unit-tested instead (`tests/chatbot/test_tail_units.py`).
    ("escalate-catalog", "demand_qty"): "H1: the route-turn arm that feeds it is dead",
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


# The S6a nodes, cut by the turn's DOMAIN. That is the axis their code path actually
# turns on: `ALLOWED` / `ALLOWS_EMPTY` / `REQUIRED_TYPES` / `REQUIRE_SPECIFIC_DOMAINS` are
# all keyed by domain, so "five captures of `incoming`" says something and "five captures"
# says nothing.
_DOMAIN_CUT_NODES = frozenset(
    {
        "disallowed-entity-gate",
        "build-ctx-resolved",
        "annotate-incoming-picker",
        "annotate-customer-picker",
        "item",
    }
)

# The exits, cut by the arm they took. Same argument, different vocabulary.
_EXIT_CUT_NODES = frozenset(
    {
        "resolve-exit-continue",
        "resolve-exit-access-ask",
        "resolve-exit-not-found",
        "resolve-exit-offer",
        "sub-resolve-and-gate",
    }
)


def _expected_domain(fixture: _corpus.Fixture) -> str | None:
    """`gate_debug.domain` off whatever level of the item this node's output carries it."""
    for item in fixture.expected:
        json_body = item.get("json") or {}
        for block in (
            json_body,
            (json_body.get("gate") or {}),
            ((json_body.get("ctx") or {}).get("gate") or {}),
        ):
            debug = block.get("gate_debug") if isinstance(block, dict) else None
            if isinstance(debug, dict) and debug.get("domain"):
                return str(debug["domain"])
    return None


# Nodes cut by `branch_kind` rather than by domain: their code path IS the arm. The tail
# pair is `escalate-catalog` (a nine-arm switch) and `build-outcome` (which forwards the
# item the arm produced).
_BRANCH_KIND_NODES = ("route-turn", "escalate-catalog", "build-outcome")
# Nodes cut by the turn's DOMAIN, because they have no branch vocabulary of their own and
# the domain is what actually varies the path through them.
_DOMAIN_NODES = (
    "output_exchange",
    "suggest-follow-up",
    "compile-current-state",
    "crossdomain-compose",
)
# The CS roster pair turns on ONE axis and it is not the domain: how many companies the
# offer spans, and whether anybody was in it. Cutting them by `all` hid three zeros that
# matter - the multi-company grouped renderer, the shared-member dedupe and the
# empty-roster fallback are the three arms with no capture at all, and a single `all`
# cell reading "met" said the opposite.
_ROSTER_NODES = ("cs-roster-plan", "build-cs-member-offer")


def _session_variables(fixture: _corpus.Fixture) -> dict:
    """`variables`, through either output shape a capture can carry.

    The live spine's `compile-current-state` predates RS-3 half H2 and emits the patch
    bare; the body the export ships re-seals it as `{reply: {..., session_patch}}`.
    """
    for item in fixture.expected:
        body = item.get("json") or {}
        if "reply" in body:
            body = (body.get("reply") or {}).get("session_patch") or {}
        variables = body.get("variables")
        if isinstance(variables, dict):
            return variables
    return {}


def _roster_cell(fixture: _corpus.Fixture) -> str:
    """`single_company` / `multi_company` / `empty_roster` for the CS roster pair."""
    items = fixture.expected
    if fixture.node == "cs-roster-plan":
        return "multi_company" if len(items) > 1 else "single_company"
    body = (items[0] or {}).get("json") or {} if items else {}
    if not (body.get("cs_last_result_set") or []):
        return "empty_roster"
    return "multi_company" if len(body.get("routing_companies") or []) > 1 else "single_company"


def _branch_of(fixture: _corpus.Fixture) -> str:
    """A coverage CELL for one fixture."""
    if fixture.node in _ROSTER_NODES:
        return _roster_cell(fixture)
    if fixture.node in _BRANCH_KIND_NODES:
        # `build-outcome` FORWARDS the item, so the arm is on its input as well as its
        # output; `escalate-catalog` stamps its answer onto the same item it received.
        kind = _expected_branch_kind(fixture)
        if kind:
            return kind
        for item in fixture.input:
            kind = (item.get("json") or {}).get("branch_kind")
            if kind:
                return str(kind)
        return "no_branch_kind" if fixture.node != "route-turn" else "unknown"
    if fixture.node in _DOMAIN_NODES:
        for item in fixture.expected:
            output = (item.get("json") or {}).get("output")
            if isinstance(output, dict):
                return str(output.get("domain_hint") or "no_domain")
        variables = _session_variables(fixture)
        if variables:
            return str(variables.get("domain_hint") or "no_domain")
        return "unknown"
    if fixture.node in _EXIT_CUT_NODES:
        for item in fixture.expected:
            kind = (item.get("json") or {}).get("_exit_kind")
            if kind:
                return str(kind)
        return "unknown"
    if fixture.node == "tier-gate":
        # The one branch this node has: does it ASK, or does it proceed?
        for item in fixture.expected:
            return "tier_ask" if (item.get("json") or {}).get("tier_ask") else "tier_proceed"
        return "unknown"
    if fixture.node in _DOMAIN_CUT_NODES:
        return _expected_domain(fixture) or "no_domain"
    return "all"


def _provenance(fixture: _corpus.Fixture) -> str:
    """`runData` (a real execution said so) vs anything else (a frozen body run)."""
    source = fixture.data.get("source") or {}
    return str(source.get("expected_from") or "body-run")


def blocking_cells(data: dict) -> list[str]:
    """`node/branch (n of N)` for every cell gate 0 blocks on.

    Exposed as data, not only as a markdown line, so `test_coverage_fresh.py` can PIN the
    set rather than assert "nothing blocks". A slice whose captures are outstanding is a
    real state - the pinned list is what makes it auditable and what makes a NEW short
    cell a failure instead of one more line in a table nobody diffs.
    """
    out: list[str] = []
    for node in sorted(data["rows"]):
        for branch in sorted(data["rows"][node]):
            real = data["rows"][node][branch].get("runData", 0)
            _, blocks = _cell_state(node, branch, real)
            if blocks:
                out.append(f"{node}/{branch} ({real} of {CAPTURES_PER_BRANCH})")
    return out


def world_matrix() -> dict:
    """The world corpus, counted by branch kind and by shape (AC-009).

    Worlds are DERIVED from spine captures rather than captured, so this is a projection
    of the same corpus the node matrix above counts - which is the point: growing the
    node corpus grows the world corpus for free.
    """
    from tests.chatbot import worlds as worlds_mod

    derived = worlds_mod.derive_worlds()
    chains = worlds_mod.multi_turn_worlds(derived)
    matrix = worlds_mod.matrix(derived)
    return {
        "total": len(derived),
        "ungradeable": sum(1 for world in derived if world.missing_inputs),
        "chains": len(chains),
        "chain_turns": sum(len(chain.turns) for chain in chains),
        "branch_kind": matrix["branch_kind"],
        "shape": {shape: matrix["shape"].get(shape, 0) for shape in worlds_mod.SHAPES},
    }


def collect() -> dict:
    rows: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    totals: Counter = Counter()
    provenance: dict[str, Counter] = defaultdict(Counter)
    vendored_names: dict[str, set[str]] = defaultdict(set)

    for node in sorted(_corpus.NODE_SLUGS):
        # UNION by file stem, so a fixture that is only vendored (the world-derived
        # route-turn capture) is counted once and only once alongside the full corpus.
        seen: dict[str, _corpus.Fixture] = {}
        if node == "sub-resolve-and-gate":
            # The synthetic whole-sub replay has no directory: it reuses the four
            # `resolve-exit-*` captures. Counted here so its `access_ask` arm shows up as
            # the zero cell it is.
            for fixture in _corpus.sub_run_fixtures(vendored_only=True):
                vendored_names[node].add(fixture.name)
                seen[fixture.name] = fixture
            for fixture in _corpus.sub_run_fixtures(vendored_only=False):
                seen.setdefault(fixture.name.split("/")[-1], fixture)
        else:
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
        "worlds": world_matrix(),
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
        "**This file was rendered against a corpus that includes the 5 Sep "
        "`sub-resolve-and-gate` capture run, which lives on an n8n WORKTREE and not yet in "
        "that repo's main checkout.** Until those 84 files land there, reproducing this "
        "report needs `CHATBOT_FIXTURES_DIR=<n8n worktree>/n8n-workflows-init/tests/"
        "fixtures`; without it `test_coverage_md_is_not_stale` fails because the loader "
        "sees a smaller corpus, not because anything drifted. CI is unaffected: it has the "
        "vendored subset only and skips the comparison."
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

    # -- worlds (AC-009) ---------------------------------------------------------------- #
    worlds = data["worlds"]
    lines.append("## World replay (AC-009)")
    lines.append("")
    lines.append(
        "A WORLD is one whole captured turn replayed through `run_turn` + `complete_turn` "
        "with the parser, the access check and the CS roster read stubbed from that "
        "execution's own node outputs. Worlds are DERIVED from spine captures, not "
        "captured separately - a spine capture already carries every node output of its "
        "execution - so growing the node corpus grows this one for free."
    )
    lines.append("")
    lines.append(
        f"**{worlds['total']} worlds** ({worlds['ungradeable']} of them ungradeable in this "
        "corpus: a spine-only capture whose resolver and entity gate ran inside a sub the "
        f"fixture never recorded). **{worlds['chains']} multi-turn chains** covering "
        f"{worlds['chain_turns']} turns, each replayed on the CRM's OWN written memory."
    )
    lines.append("")
    lines.append("| axis | value | worlds |")
    lines.append("| --- | --- | ---: |")
    for kind, count in worlds["branch_kind"].items():
        lines.append(f"| branch kind | `{kind}` | {count} |")
    for shape, count in worlds["shape"].items():
        lines.append(f"| shape | `{shape}` | {count} |")
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
