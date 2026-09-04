"""Fixture corpus loader for the node-replay suite (AC-004).

Two sources, always both:

* the VENDORED subset under ``tests/fixtures/chatbot/nodes/<node>/*.json`` - committed,
  about 3.5 MB, one fixture per node per branch kind plus the regression guards and the
  named canaries. It grew past the original 3 MB note at S6a and the reason is worth
  stating: a resolve+gate capture carries the WHOLE resolver response in its `ctx`, and
  the `offer` exit carries it four times over (the item, `gate`, `ctx_resolved` and
  `ctx_resolved.ctx.gate`), so the single smallest capture of that arm is 430 KB. The
  alternative was to stop grading the arm in CI, which is worse. It runs everywhere, CI included, and it is what makes a red replay a
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
    # S6a - the business lane's resolve + gate. Two slugs that DO carry directories with
    # these names are deliberately absent, because the node they captured is not this one:
    # `sub-answer-rs/disallowed-entity-gate` and `sub-fetch-results-rs/{tier-gate,
    # build-ctx-resolved}` are RS-8 name-preserving STAND-INS (`return [{json: $json.gate}]`
    # and friends), whose input is their sub's trigger and whose expected is a re-emission.
    # Measured: the stand-in's expected has the gate's keys and its input has none of them.
    "disallowed-entity-gate": (
        "sub-resolve-and-gate-rs",
        "live-spine-sorento-consume-main",
        "clone-spine-RS",
    ),
    "tier-gate": ("sub-resolve-and-gate-rs", "live-spine-sorento-consume-main", "clone-spine-RS"),
    "build-ctx-resolved": ("sub-resolve-and-gate-rs", "clone-spine-RS"),
    "annotate-incoming-picker": ("sub-resolve-and-gate-rs", "live-spine-sorento-consume-main"),
    "annotate-customer-picker": ("live-spine-sorento-consume-main",),
    "resolve-exit-continue": ("sub-resolve-and-gate-rs",),
    "resolve-exit-offer": ("sub-resolve-and-gate-rs",),
    "resolve-exit-not-found": ("sub-resolve-and-gate-rs",),
    "item": ("sub-resolve-and-gate-rs",),
    # Synthetic: the WHOLE sub replayed from a captured trigger, graded against the exit
    # arm's own capture. It reuses the `resolve-exit-*` directories rather than having one
    # of its own, so no fixture is invented - see `sub_run_fixtures()`.
    "sub-resolve-and-gate": (),
}

# Output keys the SHIPPING node body emits that the body every capture was taken against
# could not. NOT divergences - the port agrees with the export, and the fixture grades an
# older body - and not staleness either, because everything else about the capture still
# grades: the whole rest of the item is compared as normal.
#
# Evidence, direct and reproducible (n8n repo `git show <rev>:...`):
#
# * every `sub-resolve-and-gate*` capture carries `workflow_version` 70fa92bf, and the
#   export ships 43a37c05; every `live-spine-sorento-consume-main` capture ran the spine's
#   own 934-line copy of the gate;
# * `f1cee5b` (2026-08-31) is that 934-line body, `a4da785` + `f4c8f02` (2026-09-01) are
#   the two commits that added these keys - `out.specific_options` (RS-9 Fix 5) and
#   `tier_pick_domain` (RS-9 Fix 8);
# * diffing the two bodies gives FIVE changes, and only these two are unconditional. The
#   other three (a `company` key inside `specific_options`, the F16 company-suffixed label,
#   and the `_dfSpecAnswered` refinement of the dropped-filter gate) are reachable only
#   through inputs the older captures do not contain, and the replay run proves it: 212 of
#   212 gate captures and 7 of 7 tier-gate captures differ from the port by these keys and
#   NOTHING else.
#
# Because the keys are ungradeable by any capture, they carry unit coverage of their own in
# `tests/chatbot/test_resolve_gate_unit.py` rather than being trusted.
CAPTURE_BODY_ADDITIONS: dict[str, tuple[str, ...]] = {
    "disallowed-entity-gate": ("specific_options",),
    "tier-gate": ("tier_pick_domain",),
    # The whole-sub replay carries both, nested in the exit item's contract fields.
    "sub-resolve-and-gate": ("specific_options", "tier_pick_domain"),
}


def strip_body_additions(value, node: str):
    """Drop the keys the capture's body version could not emit, at every depth.

    Recursive because the exit arms carry the gate's and tier-gate's items nested under
    `gate` / `ctx_resolved` / `tier_gate`, so a top-level-only strip would leave the same
    delta three levels down and grade nothing.
    """
    keys = CAPTURE_BODY_ADDITIONS.get(node, ())
    if not keys:
        return value
    if isinstance(value, dict):
        return {k: strip_body_additions(v, node) for k, v in value.items() if k not in keys}
    if isinstance(value, list):
        return [strip_body_additions(v, node) for v in value]
    return value


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
    if node in ("sub-resolve-and-gate", "resolve-exit-access-ask"):
        # The sub's exits ARE a closed vocabulary (`resolve-arm`'s four Switch arms), and
        # one of them - `access_ask` - has never been captured in any slug. Seeded so that
        # reads as a zero rather than as an absent row.
        from app.services.chatbot.contracts import EXIT_KINDS

        return EXIT_KINDS
    return ()


# The `resolve-exit-*` directories every whole-sub replay is built from. One capture per
# exit arm per turn, and each one carries the trigger, the resolver response and any probe
# response in its own `ctx`, so the sub can be run end to end with nothing stubbed by hand.
SUB_RUN_SOURCE_NODES = (
    "resolve-exit-continue",
    "resolve-exit-offer",
    "resolve-exit-not-found",
    "resolve-exit-access-ask",
)


def sub_run_fixtures(*, vendored_only: bool) -> list[Fixture]:
    """Every `resolve-exit-*` capture, relabelled as a whole-sub replay.

    `node` is rewritten to `sub-resolve-and-gate` so the divergence register and the
    body-addition strip key on the thing being graded (the sub) rather than on the
    directory the JSON happens to live in.
    """
    out: list[Fixture] = []
    for node in SUB_RUN_SOURCE_NODES:
        source = vendored(node) if vendored_only else full_corpus(node)
        for fixture in source:
            out.append(
                Fixture(
                    node="sub-resolve-and-gate",
                    name=f"{node}/{fixture.name}",
                    path=fixture.path,
                    data=fixture.data,
                )
            )
    return out
