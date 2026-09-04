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
}


# Fixtures pinned to a node body that is NOT the one production runs. They are not
# divergences - nothing about the port disagrees with the live body - and they do not
# belong in `divergences.py`, which is reserved for deliberate hazard fixes.
#
# **What changed on 5 Sep 2026.** The port was made from the working-tree EXPORT of
# `sub-semantic-parser`, whose MANIFEST is flagged `locally_edited`. The n8n partner
# session then fetched the LIVE body read-only: 1,881 lines, sha `a837333a13a2`, saved at
# `output_exchange.live.js` in that session's scratchpad with
# `output_exchange.LIVE-vs-WORKTREE.diff` beside it. The export carries an UNPROMOTED lane
# change (B-TEAM-1': `routing.team_source`, a 4-rank team ladder replacing the
# `?? 'customer_service'` default, a `resource_attachment` routing row, a pending
# `team_clarify` completion block, and a state-only company-pick resolver with the
# deterministic word-match tier deleted; +241/-83 over 10 hunks). `head/output_exchange.py`
# was re-ported onto the LIVE body, and the five `parser-*` entries that used to sit here
# all replay EQUAL again - they were LIVE-faithful captures being graded against the wrong
# body, which is exactly the tell.
#
# **A version id is not sufficient evidence, and neither is an assertion.** The 19 entries
# below are the mirror image of the old five, and the evidence for each is mechanical and
# reproducible: the pre-re-port Python (`git show <the S1 commit>:...output_exchange.py`,
# faithful to the EXPORT) reproduces each fixture's `expected` exactly, and the live-
# faithful body does not. 19 of 19, with no "neither matches" residue. They are hand-built
# pins authored alongside the unpromoted change, not captures of a real execution, so there
# is no production turn they describe. Retire each one when the owner promotes the
# escalation-routing lane's B3 step and the port follows (plan, S1 "pending re-port").
#
# They are SKIPPED, not dropped: `test_replay.py` emits one skip per entry with its reason,
# so `pytest -rs` and the summary count show exactly how much of the corpus is not being
# graded.
_UNPROMOTED = (
    "pins the UNPROMOTED B-TEAM-1' export body, not the live one; the pre-re-port port "
    "reproduces it exactly and the live-faithful port does not (see the header note)"
)

STALE_FIXTURES: dict[tuple[str, str], str] = {
    ("build-ctx", "rs2-01-notsupported"): "RS-2 capture, predates the RS-4 `media` key",
    ("build-ctx", "rs2-02-escalation"): "RS-2 capture, predates the RS-4 `media` key",
    ("build-ctx", "rs2-03-happy"): "RS-2 capture, predates the RS-4 `media` key",
    ("build-ctx", "rs2-04-access-denied"): "RS-2 capture, predates the RS-4 `media` key",
    # Hand-built pins for the unpromoted lane change. EVERY real capture in the corpus is
    # graded; not one `parser-*` / `exec-*` fixture is excluded.
    **{
        ("output_exchange", name): _UNPROMOTED
        for name in (
            "casual-without-offer-engagement-wipes-entities",
            "date-filter-gated-records-null-domain",
            "escalation-offer-confirm-decline-and-pick",
            "legacy-suffixed-promotion-team-normalised-from-prior",
            "literal-string-null-hints-coerced",
            "member-offer-bare-number-reply",
            "member-offer-clarification-counts-as-a-new-query",
            "member-offer-long-reply-is-not-digit-scanned",
            "member-offer-ordinal-numeral-2nd",
            "member-offer-ordinal-word-first",
            "member-offer-ordinal-word-second",
            "member-offer-ordinal-word-third",
            "member-offer-precedence-arms",
            "menu-label-stock-enquiry",
            "pending-pick-from-a-single-row-roster",
            "request-for-help-llm-team-wins",
            "resource-attachment-corrected-when-product-present",
            "routing-domains-multi-item",
            "tier-offer-out-of-range-position-is-not-a-pick",
        )
    },
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
