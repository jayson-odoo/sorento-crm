"""Registered divergences between the Python port and the captured n8n fixtures.

AC-005. A replayed fixture whose output disagrees with `expected` FAILS, unless the
pair `(node, fixture)` is listed here with the hazard id it belongs to and a one-line
reason. That is how "parity before improvement" (D8) is enforced mechanically rather
than by reviewer memory: a hazard fix has to be written down as a divergence before it
can turn a red replay green, and an accidental behaviour change has nowhere to hide.

`node` is the fixture directory name (`route-turn`, `output_exchange`, ...), NOT the
Python module. `fixture` is the file stem. A `None` fixture registers the divergence for
every fixture of that node - use it only for a hazard that genuinely changes the node's
whole contract, and say so in the reason.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Divergence:
    node: str
    fixture: str | None
    hazard: str
    reason: str
    # A FIELD-scoped divergence: these paths are removed from both sides before the
    # comparison, and everything else must still be byte-equal. A blanket entry (empty
    # tuple) passes the whole fixture, which is right for a hazard that changes a node's
    # whole contract and WRONG for one that adds a key - the blanket form would make the
    # gate vacuous for that node forever. `path` is walked inside each item's `json`.
    strip_paths: tuple[tuple[str, ...], ...] = ()


# Every entry must name a hazard id from the plan's hazard table and be traceable to an
# AC. S1 shipped with none; S2 adds exactly the one AC-202 authorises.
DIVERGENCES: list[Divergence] = [
    Divergence(
        node="compile-current-state",
        fixture="b56-roster-turn",
        hazard="H29 (AC-205)",
        reason=(
            "born roster beats carried picker. The capture IS the defect: on clone exec "
            "14400735 the turn rendered a nine-member CS roster and persisted the "
            "PREVIOUS turn's three-row customer picker with selection_context "
            "'disambiguation', so the next '1' re-ran the order query and the escalation "
            "was dropped. The body the export ships carries the fix "
            "(`_cpOfferBornThisTurn`); this capture predates it. Pinned by "
            "tests/chatbot/test_tail_units.py::TestBornRosterWins."
        ),
    ),
    Divergence(
        node="compile-current-state",
        fixture=None,
        hazard="H13/H14 (R3)",
        reason=(
            "the port writes the `pending` marker the JS had no equivalent of, so the "
            "next turn can ask 'is an escalation offer open?' of state instead of of the "
            "bot's own previous words (D11). Field-scoped: every other byte of the "
            "session patch is still compared, and AC-203's own test asserts the marker."
        ),
        strip_paths=(
            ("reply", "session_patch", "variables", "pending"),  # the shipping seal
            ("variables", "pending"),  # a pre-RS-3 capture, unwrapped by the runner
        ),
    ),
]


# World-level deltas: session keys a WORLD is allowed to differ on, per world id, with
# the reason. Deliberately per-world and per-KEY rather than a blanket skip - a world that
# is allowed to differ everywhere proves nothing, and the point of a world is that the
# wiring produced the same reply and the same memory as the execution it was derived from.
#
# `pending` is dropped for every world without an entry here: it is the R3 marker the JS
# had no equivalent of, already registered as a field-scoped divergence for the node
# replay above.
WORLD_DELTAS: dict[str, tuple[str, ...]] = {}


def find(node: str, fixture: str) -> Divergence | None:
    """The registered divergence covering this replay, or None."""
    for d in DIVERGENCES:
        if d.node == node and (d.fixture is None or d.fixture == fixture):
            return d
    return None


def strip(items: list, paths: tuple[tuple[str, ...], ...]) -> list:
    """Remove each path from every item's `json`. A path that is not there is a no-op."""
    for item in items:
        for path in paths:
            node = item.get("json") if isinstance(item, dict) else None
            for key in path[:-1]:
                node = node.get(key) if isinstance(node, dict) else None
            if isinstance(node, dict):
                node.pop(path[-1], None)
    return items
