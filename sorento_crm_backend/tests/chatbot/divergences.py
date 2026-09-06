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


# Every entry here must name a hazard id or an owner decision from the plan, and be
# traceable to an AC. S1 shipped with none; S2 adds two - AC-202 authorises the `pending`
# marker, and AC-205 is the H29 fix, whose only capture records the DEFECT.
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
    # ------------------------------------------------------------------ #
    # S6c.
    # ------------------------------------------------------------------ #
    Divergence(
        node="crossdomain-render",
        fixture="exec-14131197",
        hazard="H62 (owner console pass, 6 Sep 2026)",
        reason=(
            "'positive facts only' dropped a requested code that came back empty on BOTH "
            "sides, so the reply named only the codes that had something to show. Owner "
            "ruling: name it ('no stock and no incoming') and offer the escalation. This "
            "capture is that case exactly - one probed missing code, zero probed rows - so "
            "the port emits the negative paragraph where n8n emitted nothing. Field-scoped "
            "to the two keys that carry it; every other byte is still compared, and the "
            "other four crossdomain-render captures are byte-equal. Pinned by "
            "tests/chatbot/test_s6c_answer_lane.py::"
            "TestThirdCodeWithNoStockAndNoIncomingIsNamedWithEscalation."
        ),
        strip_paths=(
            ("_xdBlock", "block"),
            ("_xdBlock", "any"),
        ),
    ),
    Divergence(
        node="build-suggest-offer",
        fixture="exec-14001140",
        hazard="D4 (AC-607) - the offer's identity is the TURN id",
        reason=(
            "the did-you-mean offer stamps `$execution.id` as its identity, and in the CRM "
            "that identity is the turn id. The offer only has to be stable WITHIN the "
            "session, so the successor is correct, but the value can never equal a captured "
            "n8n execution id - the same permanent difference already registered for the "
            "world replay as `worlds.WORLD_DROP_PATHS = (('dym_offer', 'id'),)`. This is "
            "the ONE graded `build-suggest-offer` capture whose only disagreement is that "
            "id (measured: 19 of 19 equal once the turn id is supplied), so the entry is "
            "per-fixture rather than node-wide - a node-wide one would pass every other "
            "capture unread."
        ),
        strip_paths=((("dym_offer", "id")),),
    ),
    *(
        Divergence(
            node="dym-transform",
            fixture=name,
            hazard="capture predates the body (S6a's CAPTURE_BODY_ADDITIONS class)",
            reason=(
                "the LIVE SPINE ships a STALE inline copy of `dym-transform` (421 lines, "
                "pre-Fix-4) while `sub-miss-suggest-live@f42de9c6` ships the 561-line body "
                "this port was made from and the 33 `sub-miss-suggest-live` captures were "
                "graded against. The three keys Fix 4 added - `dym_candidate_uuids`, "
                "`dym_probe_row_keys`, `probe_uuid_keyed` - do not exist in the older body, "
                "so this capture's `expected` cannot carry them. Measured: they are the "
                "ONLY disagreement on all three of these captures, and every other key is "
                "byte-equal. Retire the entry when the spine's inline copy is re-captured "
                "against the shipping body."
            ),
            strip_paths=(
                ("dym_candidate_uuids",),
                ("dym_probe_row_keys",),
                ("probe_uuid_keyed",),
            ),
        )
        for name in ("exec-13462354", "exec-13469053", "exec-13479632")
    ),
    Divergence(
        node="dym-annotate",
        fixture="exec-13469053",
        hazard="capture predates the body (S6a's CAPTURE_BODY_ADDITIONS class)",
        reason=(
            "the same stale-spine pair as the three `dym-transform` entries above: the live "
            "spine's inline `dym-annotate` is 169 lines (pre-Fix-4 / F1 / F8) while "
            "`sub-miss-suggest-live@f42de9c6` ships the 247-line body this port was made "
            "from. The older body emits neither `dym_ambiguous_codes` nor "
            "`dym_ambiguous_uuids` and stamps no `key_mode` on `dym_probe_meta`. Measured: "
            "those three keys are the ONLY disagreement, and the other 15 graded "
            "`dym-annotate` captures are byte-equal once the node's two by-name upstreams "
            "are supplied. Retire the entry when the spine's inline copy is re-captured."
        ),
        strip_paths=(
            ("dym_ambiguous_codes",),
            ("dym_ambiguous_uuids",),
            ("dym_probe_meta", "key_mode"),
        ),
    ),
]


# World-level allowances live in `tests/chatbot/worlds.py`, not here, and there are
# exactly two of them (`pending` and `dym_offer.id`). A world that differs anywhere else
# is either a defect or a NAMED body difference, and a body difference SKIPS the world
# rather than excusing a key - so there is no per-world delta table to keep honest.

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


# S4. n8n has NO reply on the low_signal lane's setup paths. `sub-casual-llm` binds its
# OpenAI credential to the node, so a missing API key, an unset AI-assistant config or a
# resolver that will not answer does not reach `sub-error-logger2` at all: the sub throws,
# the spine's caller has no error output on that edge, and the turn dies with the customer
# never told anything. Zero captures on the arm since 1 Sep, which is consistent with it
# never having produced an item to capture.
#
# The port fails that turn instead, at `stage = casual_llm` with `branch_kind` still
# `low_signal`, and sends a FIXED sentence (`casual.CLARIFIER_UNAVAILABLE_REPLY`) rather
# than interpolating the exception: those messages name providers and configuration keys,
# and none of it belongs in a WhatsApp reply. The CALL arm is unchanged and still sends
# `sub-error-logger`'s own interpolated text, which is why the two differ.
#
# Not fixture-visible - there is no capture of a path that never emitted one - so this is
# recorded here rather than against a replay.
CASUAL_SETUP_FAILURE_HAS_A_REPLY = Divergence(
    node="sub-casual-llm",
    fixture=None,
    hazard="H32",
    reason=(
        "n8n drops a low_signal turn whose clarifier could not be SET UP (no API key, no "
        "AI config, resolver error): the credential is node-bound, so nothing reaches "
        "sub-error-logger2 and the customer is told nothing. The port fails the turn at "
        "stage=casual_llm and sends a fixed sentence, never str(exc)."
    ),
)


# S6c. `crossdomain-zeroset`'s DOMAIN GUARD, and WHICH body it came from.
#
# Two live workflows ship a node called `crossdomain-zeroset` and they differ:
#
#   * `sub-main-processing-live` (id 53RxDSON8P3QSN22, version
#     53ca1c6b-a6b3-48ed-b094-2cddafb3185c) ships 151 lines, sha256
#     fb9d41cf64ea320bd016ef516fb4b0edd903cc1da9996fd01eabb4a00fc1c06d, and CARRIES the
#     guard ("DOMAIN GUARD (2026-09-01, exec 14769923)"). This is the body the plan's
#     S6c line count (151) names and the one the port was made from.
#   * `live-spine-sorento-consume-main` (id 9qVyfUxmRQqrpGRMDLRuz, version
#     c9fe3e68-b732-460d-b968-c1b4a5e5f038) ships 143 lines, sha256
#     a880d01e3629538bdde874f60875b481af7415acb6c7f12d4795171074518f92, and does NOT.
#     The spine is `active: true` and has no `Call 'sub-main-processing'` node, so IT is
#     the body answering turns today.
#
# So relative to the shipping path the guard is a CRM behaviour change, not parity, and
# it is registered as one rather than left to a comment. It only ever REMOVES codes from
# `_xd.requested` (a pick made under an order or promotion offer stops naming a product
# on an inventory turn, which printed "No stock records found for: CG-202608-051."), so
# the direction is fail-quiet, and the pick made THIS turn is unaffected.
#
# Not fixture-visible: all five graded `crossdomain-zeroset` captures predate the guard
# (22 Aug 2026) and none carries a foreign-domain `dym_offer`, so no replay changes.
# Pinned by tests/chatbot/test_s6c_answer_lane.py::TestH22H23DymOfferDomainCleared.
CROSSDOMAIN_DYM_OFFER_DOMAIN_GUARD = Divergence(
    node="crossdomain-zeroset",
    fixture=None,
    hazard="H22 / H23",
    reason=(
        "carried did-you-mean picks ride into the cross-domain read only when the offer's "
        "own domain is inventory / incoming. Present in sub-main-processing-live's 151-line "
        "body (sha fb9d41cf64ea320b), absent from the ACTIVE spine's 143-line one "
        "(sha a880d01e3629538b). Not fixture-visible: the five captures predate it."
    ),
)


# S6c. `build-suggest-offer`'s sibling picker breaks a has-incoming tie with
# `String(a.code).localeCompare(String(b.code))`; the port uses Python's code-point
# order. ICU treats punctuation and case differently: node sorts
# `SRT_100, SRT-100, SRT1, srt100, SRT100, SRTA`, Python sorts
# `SRT-100, SRT1, SRT100, SRTA, SRT_100, srt100`. Only reachable when one product family
# holds two codes differing solely in punctuation or case, which no captured turn does -
# every graded `build-suggest-offer` replay is byte-equal. Recorded rather than fixed
# because the fix is a new dependency (PyICU) for a tiebreak inside one family; the
# trigger to pay for it is a real family of that shape.
SIBLING_TIEBREAK_IS_CODE_POINT = Divergence(
    node="build-suggest-offer",
    fixture=None,
    hazard="platform (localeCompare vs code-point order)",
    reason=(
        "the sibling picker's tiebreak is ICU collation in n8n and code-point order in "
        "Python. Not fixture-visible: no captured family holds two codes differing only "
        "in punctuation or case."
    ),
)


# Owner console pass, 6 Sep 2026. `route-turn`'s `wants_escalation_or_help` fires on
# `message_type === 'request_for_help'` (portal_link exempted) ONE ARM BEFORE
# `is_ideate_domain`, so a turn the parser tagged `domain_hint: 'ideate'` never reached the
# ideate lane at all - the console run answered "I have an idea for you" with `out_of_scope`.
# The ladder order is faithful to the live workflow; it hid the ideate arm the moment access
# flipped to `allow`, which is a defect in the ORIGINAL, not in the port. The port therefore
# exempts `ideate` beside `portal_link` rather than reproducing the shadow.
#
# Not fixture-visible: no captured `route-turn` turn carries `domain_hint: 'ideate'` (the
# ideate lane shipped after the capture window), so no replay changes. Pinned by
# tests/chatbot/test_route_unit.py::TestIdeateNeverShadowedByHelpRequest.
IDEATE_NOT_SHADOWED_BY_REQUEST_FOR_HELP = Divergence(
    node="route-turn",
    fixture=None,
    hazard="H59 (owner console pass, 6 Sep 2026)",
    reason=(
        "`domain_hint: 'ideate'` is exempted from the request_for_help arm so the ideate "
        "lane is reachable. Live's ladder order shadows it permanently. Not "
        "fixture-visible: no capture carries an ideate domain hint."
    ),
)


# Owner console pass, 6 Sep 2026. A cold "all of them" - the customer answering a
# clarification menu with the broadest option - comes back `message_type: 'casual'` with a
# null `domain_hint`, alongside the `scope_intent: 'broaden'` / `broaden_axis: 'all'` the
# parser reads correctly. `is_low_signal` fires on `casual` ALONE and sits above
# `is_clarification`, so the turn was answered "Hi!". The port reads the two scope keys in
# `is_clarification` and moves that arm above `is_low_signal`; the two message_type sets are
# disjoint, so nothing the live ladder ever saw changes branch.
#
# A ROUTER backstop rather than a parser change on purpose: the scope keys are already
# right, and re-teaching the prompt to stop stamping `casual` on a two-word reply is a
# retune with no upper bound. Not fixture-visible: no captured `route-turn` turn carries
# `broaden_axis: 'all'` with a null domain. Pinned by
# tests/chatbot/test_route_unit.py::TestBroadenAllNeverReadAsLowSignal.
BROADEN_ALL_IS_A_CLARIFICATION = Divergence(
    node="route-turn",
    fixture=None,
    hazard="H60 (owner console pass, 6 Sep 2026)",
    reason=(
        "scope_intent 'broaden' + broaden_axis 'all' + null domain routes clarify_menu "
        "instead of low_signal, and the clarification arm moves above the low-signal one. "
        "Not fixture-visible: no capture carries that shape."
    ),
)


# Owner console pass, 6 Sep 2026. `not-found-error-message`'s status-aware arm derives
# `eta` (` (estimated delivery <date>)`) and then never uses it - the JS computes the string
# and drops it on the floor. The owner's ruling wants the date said: "Order <code>
# (<customer>) hasn't been delivered yet - current status: <status> (estimated delivery
# <date>)". The value is on the resolved order's own display, so nothing extra is read.
#
# Not fixture-visible: no graded `not-found-error-message` capture reaches the
# `order_status: 'delivered'` arm with an estimated delivery date on the match. Pinned by
# tests/chatbot/test_s6c_answer_lane.py::TestStatusAwareMissMessageIncludesTheEtaDate.
STATUS_MISS_MESSAGE_STATES_THE_ETA = Divergence(
    node="not-found-error-message",
    fixture=None,
    hazard="H61 (owner console pass, 6 Sep 2026)",
    reason=(
        "the delivered-status miss message states the estimated delivery date the JS "
        "derives and discards. Not fixture-visible: no capture reaches that arm with a "
        "date on the resolved order."
    ),
)


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
