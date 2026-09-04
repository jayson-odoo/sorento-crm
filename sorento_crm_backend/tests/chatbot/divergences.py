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


# Every entry here must name a hazard id or an owner decision from the plan, and be
# traceable to an AC.
DIVERGENCES: list[Divergence] = []

# ---------------------------------------------------------------------------- #
# Deliberate behaviour differences that are NOT per-fixture, recorded here because
# `DIVERGENCES` above is per-fixture and these have no fixture to attach to.
# ---------------------------------------------------------------------------- #

# D5 (S6a): n8n hard-codes the respond.io workspace as `space_id: "364817"` in FOUR places
# inside `sub-resolve-and-gate` - the `get-access-types` URL, the `resolve-entity` URL, and
# both probes' `semantic_input` / `user_prompt`. The port reads it from the default respond
# workspace row instead (`head/access.py::default_space_id`), which is the whole of D5:
# "the respond.io `space_id` comes from the default respond workspace row".
#
# NOT a replay divergence, and that is worth stating rather than leaving to inference:
# every replay passes `space_id` in explicitly (`test_replay.SUB_REPLAY_SPACE_ID = "364817"`,
# and the node runners never touch it at all), so the captures grade the same value n8n
# produced. The difference is only reachable in production, and only on an install whose
# default workspace is not 364817 - which is exactly the install D5 exists for.
#
# The one behaviour to know about: an install with NO default respond workspace row gets
# `space_id = None`, and `resolve_active_access_levels_for_contact` then 404s rather than
# silently answering for the wrong workspace. That is fail-closed on purpose.
SPACE_ID_FROM_THE_WORKSPACE_ROW = Divergence(
    node="sub-resolve-and-gate",
    fixture=None,
    hazard="D5",
    reason=(
        "n8n hard-codes space_id 364817; the port reads the default respond workspace row. "
        "Not fixture-visible: every replay pins 364817 explicitly."
    ),
)


def find(node: str, fixture: str) -> Divergence | None:
    """The registered divergence covering this replay, or None."""
    for d in DIVERGENCES:
        if d.node == node and (d.fixture is None or d.fixture == fixture):
            return d
    return None
