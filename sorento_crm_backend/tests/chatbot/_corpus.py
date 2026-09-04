"""Fixture corpus loader for the node-replay suite (AC-004).

Two sources, always both:

* the VENDORED subset under ``tests/fixtures/chatbot/nodes/<node>/*.json`` - committed,
  under 3 MB, one fixture per node per branch kind plus the regression guards and the
  named canaries. It runs everywhere, CI included, and it is what makes a red replay a
  merge blocker rather than a local curiosity.
* the FULL corpus in the sibling n8n checkout, pointed at by ``CHATBOT_FIXTURES_DIR``
  (default ``../../sorento_crm_n8n/n8n-workflows-init/tests/fixtures`` relative to the
  monorepo root). Absent = those tests skip with a message; present = every capture for
  a ported node replays.

A fixture is the n8n harness's own shape::

    {source, ctx, input, expected, runIndex, execution, ran}

``ctx`` maps an upstream node name to the item list it emitted, ``input`` is the node's
own input item list, and ``expected`` is the normalised output item list. Comparison is
after a JSON round trip on both sides, exactly as ``tests/harness/n8n-shim.js``'s
``assertOutputEquals`` does it - an in-process ``undefined`` can never survive to n8n, so
it must not survive to the assertion either.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
VENDORED_ROOT = BACKEND_ROOT / "tests" / "fixtures" / "chatbot" / "nodes"

# The n8n checkout is a sibling of the monorepo root - but a lane runs from a git
# worktree several directories deeper, so the sibling is found by walking up rather than
# by counting parents (which is how this silently skipped in every worktree).
_CORPUS_SUFFIX = Path("sorento_crm_n8n") / "n8n-workflows-init" / "tests" / "fixtures"

# Which capture slugs hold each ported node. A node can live under more than one slug
# (the live spine and the fail-closed clone capture the same node names), so the loader
# unions them and prefixes the fixture id with the slug to keep ids unique.
NODE_SLUGS: dict[str, tuple[str, ...]] = {
    "route-turn": ("clone-spine-RS", "spine-rs-1a", "live-spine-sorento-consume-main"),
    "build-ctx": ("clone-spine-RS", "spine-rs-1a", "live-spine-sorento-consume-main"),
    "output_exchange": ("sub-semantic-parser",),
    "suggest-follow-up": ("sub-semantic-parser",),
    # S2, the tail. `clone-sub-output` is the RS-9 split-out sub; the two spine slugs
    # captured the same node names before and after the split, which is why the loader
    # unions them and prefixes each id with its slug.
    "build-outcome": ("clone-sub-output", "clone-spine-RS"),
    "escalate-catalog": ("live-spine-sorento-consume-main", "clone-spine-RS"),
    "cs-roster-plan": ("live-spine-sorento-consume-main",),
    "build-cs-member-offer": ("live-spine-sorento-consume-main",),
    "compile-current-state": ("live-spine-sorento-consume-main", "clone-spine-RS"),
    "crossdomain-compose": ("live-spine-sorento-consume-main", "clone-spine-RS"),
}


# Captures taken against a node body that is NOT the one the export ships. These are not
# divergences - nothing about the port disagrees with what ships - and they do not belong
# in `divergences.py`, which is reserved for deliberate hazard fixes. They are the
# "fixture staleness" risk the plan names.
#
# **A version id is not sufficient evidence.** The five `parser-*` entries below carry the
# SAME `source.workflow_version` as the export (`ab3ec985`), and still disagree; the
# workflow is flagged `locally_edited` in its own MANIFEST, so a deployed edit reached the
# running body without moving the id. The evidence used instead is direct and reproducible:
# the exported `output_exchange.js` was run against each of these fixtures through the n8n
# repo's own harness (`tests/harness/n8n-shim.js`), and IT produces what the Python port
# produces, character for character, not what the fixture expects. The port is faithful to
# the body that ships; the fixture grades a different one.
#
# They are SKIPPED, not dropped: `test_replay.py` emits one skip per entry with its reason,
# so `pytest -rs` and the summary count show exactly how much of the corpus is not being
# graded. Re-capture against the current export retires an entry.
STALE_FIXTURES: dict[tuple[str, str], str] = {
    ("build-ctx", "rs2-01-notsupported"): "RS-2 capture, predates the RS-4 `media` key",
    ("build-ctx", "rs2-02-escalation"): "RS-2 capture, predates the RS-4 `media` key",
    ("build-ctx", "rs2-03-happy"): "RS-2 capture, predates the RS-4 `media` key",
    ("build-ctx", "rs2-04-access-denied"): "RS-2 capture, predates the RS-4 `media` key",
    # Routing-ladder rank differences. The exported body agrees with the port (verified
    # through the n8n harness), so the deployed body that produced these differed.
    ("output_exchange", "parser-15024720"): (
        "exported output_exchange.js emits suggested_team null, the fixture expects "
        "'purchasing' (the LLM's own team with no team_source); verified against the "
        "export via the n8n harness"
    ),
    ("output_exchange", "parser-15130185"): (
        "exported body emits suggested_team null, fixture expects 'marketing_product'; "
        "same routing-ladder rank difference as parser-15024720"
    ),
    ("output_exchange", "parser-15151918"): (
        "exported body emits suggested_team null, fixture expects 'warehouse'; same "
        "routing-ladder rank difference as parser-15024720"
    ),
    ("output_exchange", "parser-15158411"): (
        "exported body emits suggested_team null, fixture expects 'warehouse'; same "
        "routing-ladder rank difference as parser-15024720"
    ),
    # S2, the tail. Six captures that predate the RS-9 "Fix 6" tier-menu block (owner
    # decision, 2026-09-01). The block is a pure ADDITION in the body the export ships -
    # visible as a `>`-only hunk in `diff live-spine.../compile-current-state.js
    # sub-output-live/compile-current-state.js` - so these captures were graded against a
    # body that could not write `tier_menu` at all. Nothing about the port disagrees with
    # what ships; re-capturing an access-choice turn retires all six.
    ("compile-current-state", "exec-14087671"): (
        "captured before the RS-9 Fix 6 tier_menu block; the live body has no such block"
    ),
    ("compile-current-state", "exec-14113654"): (
        "captured before the RS-9 Fix 6 tier_menu block; the live body has no such block"
    ),
    ("compile-current-state", "exec-14120751"): (
        "captured before the RS-9 Fix 6 tier_menu block; the live body has no such block"
    ),
    ("compile-current-state", "hand-tier-ask-roster-and-null-quick-reply"): (
        "hand-built against the live body, which has no RS-9 Fix 6 tier_menu block"
    ),
    ("compile-current-state", "rs34-04-accesschoice"): (
        "clone capture at workflow version 38cb225d, before the tier_menu block landed"
    ),
    ("compile-current-state", "rs6-02-accesschoice"): (
        "clone capture at workflow version 15495426, before the tier_menu block landed"
    ),
    ("output_exchange", "parser-15164413"): (
        "exported body derives marketing_product/general_enquiries from the turn's own "
        "resource_attachment domain, fixture expects the PRIOR turn's "
        "purchasing/incoming_stock_enquiries carried forward"
    ),
}


def stale_entries() -> list[tuple[str, str, str]]:
    """`(node, fixture, reason)` for every registered stale capture, sorted."""
    return sorted((node, name, reason) for (node, name), reason in STALE_FIXTURES.items())


@dataclass(frozen=True)
class Fixture:
    node: str
    name: str
    path: Path
    data: dict

    @property
    def ctx(self) -> dict:
        return self.data.get("ctx") or {}

    @property
    def input(self) -> list:
        return self.data.get("input") or []

    @property
    def expected(self) -> list:
        return self.data.get("expected") or []

    def upstream(self, node_name: str) -> list:
        """The item list a named upstream node emitted, or [] when it did not run."""
        return self.ctx.get(node_name) or []

    def first(self, node_name: str) -> dict:
        """``$('node').first().json`` - raises the way the n8n shim does when unstubbed."""
        items = self.upstream(node_name)
        if not items:
            raise KeyError(
                f"$('{node_name}').first(): zero items in fixture {self.name} "
                f"(known: {', '.join(sorted(self.ctx))})"
            )
        return items[0].get("json")


def corpus_root() -> Path | None:
    """The full n8n corpus root, or None when this checkout has no sibling n8n repo."""
    raw = os.environ.get("CHATBOT_FIXTURES_DIR")
    if raw:
        root = Path(raw).expanduser()
        return root if (root / "nodes").is_dir() else None
    for ancestor in BACKEND_ROOT.parents:
        candidate = ancestor / _CORPUS_SUFFIX
        if (candidate / "nodes").is_dir():
            return candidate
    return None


def corpus_skip_reason() -> str:
    return (
        "full n8n fixture corpus not found - set CHATBOT_FIXTURES_DIR to "
        "<n8n checkout>/n8n-workflows-init/tests/fixtures (the vendored subset still ran)"
    )


def _load_dir(node: str, directory: Path, prefix: str = "") -> list[Fixture]:
    if not directory.is_dir():
        return []
    out: list[Fixture] = []
    for path in sorted(directory.glob("*.json")):
        if (node, path.stem) in STALE_FIXTURES:
            continue
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        out.append(Fixture(node=node, name=f"{prefix}{path.stem}", path=path, data=data))
    return out


def vendored(node: str) -> list[Fixture]:
    """The committed subset for one node. Always runs."""
    return _load_dir(node, VENDORED_ROOT / node)


def full_corpus(node: str) -> list[Fixture]:
    """Every capture for one node across its slugs. Empty when the corpus is absent."""
    root = corpus_root()
    if root is None:
        return []
    out: list[Fixture] = []
    for slug in NODE_SLUGS.get(node, ()):  # noqa: B007 - explicit slug list, not discovery
        out.extend(_load_dir(node, root / "nodes" / slug / node, prefix=f"{slug}/"))
    return out


def json_round_trip(value):
    """What n8n's own comparison does to both sides before diffing them."""
    return json.loads(json.dumps(value))


def declared_branches(node: str) -> tuple[str, ...]:
    """Every branch this node CAN produce, whether or not anything captured it.

    Seeded into the coverage matrix so an arm nobody has ever captured is a visible zero
    rather than an absent row - which is exactly the cell gate 0 exists to surface. Only
    `route-turn` has a closed vocabulary; the parser nodes are cut by domain, and the set
    of domains a capture window happens to contain is not a contract.

    Lives here rather than in `scripts/chatbot_fixture_coverage.py` because this file is
    inside the module's import boundary (AC-002) and the script is not.
    """
    if node == "route-turn":
        from app.services.chatbot.contracts import BRANCH_KINDS

        return BRANCH_KINDS
    return ()
