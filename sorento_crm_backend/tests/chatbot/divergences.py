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
    # ------------------------------------------------------------------ #
    # OWNER RULING K, rule 1 (6 Sep 2026): an offer roster lives until the topic
    # changes. Thirteen captures record the OLD lifetime, in which the ladder
    # recomputed `selection_context` from THIS turn's outcome alone, so a turn
    # that built no offer of its own wrote `null` plus the ANSWER's own rows -
    # and the customer's second pick ("2" after "1") had nothing to resolve
    # against. `_offer_carry` now keeps the previous label and roster on exactly
    # those turns.
    #
    # This is the owner REVERSING a decision, not a port defect: the old n8n
    # spine's own `compile-current-state.js` carries the same `... || null` reset
    # the port reproduced, so no capture can show the new behaviour and every
    # capture of the shape shows the old one. Pinned by
    # test_tail_units.py::TestTierAndPromoOffersCarryUntilOverwritten and
    # ::TestTheMemberOfferCarryStopsAtTheAnswer.
    #
    # FIELD-SCOPED, deliberately: only the two fields the rule moves come off,
    # in both the sealed and the unwrapped shape, plus the `pending` marker the
    # blanket H13/H14 entry below would otherwise have handled (a per-fixture
    # entry wins the `find` lookup, so it has to carry that strip itself).
    # Every other byte of these thirteen captures is still graded.
    *(
        Divergence(
            node="compile-current-state",
            fixture=name,
            hazard="owner ruling K rule 1 (AC-816)",
            reason=(
                "the capture records the pre-ruling lifetime: the offer roster died the "
                "moment a turn built no offer of its own, so a sequential pick had no "
                "list to resolve against. Owner-ruled on 6 Sep 2026; the old spine's own "
                "compile-current-state.js has the same reset, so this is a new rule, not "
                "a port bug."
            ),
            strip_paths=(
                ("reply", "session_patch", "variables", "selection_context"),
                ("reply", "session_patch", "variables", "last_result_set"),
                ("reply", "session_patch", "variables", "pending"),
                ("variables", "selection_context"),
                ("variables", "last_result_set"),
                ("variables", "pending"),
            ),
        )
        for name in (
            "rs34-02-escalation",
            "rs34-05-promopicker",
            "rs51-02-promoattach",
            "rs51-03-escalation",
            "rs6-04-promopicker",
            "rs6-05-escalation",
            "s57-t1",
            "s57-t2",
            "exec-14001191",
            "exec-14119800",
            "exec-14123374",
            "exec-14126915",
            "out-15143898",
        )
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
    # ------------------------------------------------------------------ #
    # OWNER RULING K, rule 4 (6 Sep 2026): a BARE entity turn is typed by the
    # carried domain, not by the model's guess at the token's shape. Four
    # captures show the old typing, and all THREE are one class: a
    # product-shaped code under a carried `order` thread, retyped `customer`
    # (`srtwc286`, `CSK11A`, `ib2700ss rta`). The retype only changes which type
    # the resolver tries FIRST - `resolve_entity_body` sends
    # `fallback_to_all_types: true`, which is the "the resolver then decides"
    # half of the ruling - so no answer is closed off by it. The cost is named
    # rather than hidden: those three reach the resolver as customers first, and
    # unfolded, because the separator fold in `_token_of` is product-hint-only.
    #
    # A FOURTH capture was registered here on the first pass and is now graded
    # again: `parser-15129616` is a positional pick ("17" against a numbered
    # list of orders) that qualified as bare only because the fork's token test
    # asks whether the raw CONTAINS the token, and "17" is inside `M2609-0173`.
    # It was a defect wearing a ruling's clothes. `_message_is_only_these_entities`
    # now matches by equality against the raw's own tokens and an entity carrying
    # an `ordinal` is never bare, so the capture is byte-equal.
    #
    # This is a deliberate divergence from the LIVE parser body: the hunk it
    # comes from (`_bareEntityTurn`) exists only on the unpromoted
    # `sub-semantic-parser-FORK`, and even there it does not RETYPE - the retype
    # is the owner's addition. Pinned by
    # test_output_exchange_rules.py::test_a_bare_entity_inherits_the_carried_domain_and_is_retyped_by_it
    # and its `order` twin, with the resolve-time guard in
    # test_resolve_gate_unit.py::TestBareEntityInheritanceIsBlockedAtResolveTime.
    *(
        Divergence(
            node="output_exchange",
            fixture=name,
            hazard="owner ruling K rule 4 (AC-816)",
            reason=(
                "the capture records the model's own hint for a bare entity under a "
                "carried business domain; the port types it by the domain and lets the "
                "resolver decide. Field-scoped to the entity list."
            ),
            strip_paths=(
                ("output", "entities"),
                ("output", "bare_entity_retyped"),
            ),
        )
        for name in (
            "s57-ok-parser",
            "parser-15101983",
            "parser-15115339",
        )
    ),
    # OWNER RULING K, rule 2 (6 Sep 2026): carried entities die on a topic
    # change. TWO captures in the whole corpus change their entity list, and
    # both are the shape the rule exists for - an explicit new query, in a
    # different domain, bringing its own scope, with a carried entity from the
    # old subject still narrowing it (`customer_order:M2609-0086` on an incoming
    # question, `category:faucets for bath tub` on a stock question). Everything
    # the domain blocklist already removed it still removes: this pass runs
    # AFTER it and only sees what the blocklist cannot, which is why the other
    # captures of the shape are byte-equal.
    *(
        Divergence(
            node="output_exchange",
            fixture=name,
            hazard="owner ruling K rule 2 (AC-816)",
            reason=(
                "the capture keeps an entity carried from the previous subject into an "
                "explicit new-domain query. Owner-ruled to die with the topic (H61). "
                "Field-scoped to the entity list."
            ),
            strip_paths=(
                ("output", "entities"),
                ("output", "entities_dropped_on_topic_change"),
            ),
        )
        for name in ("parser-15124806", "parser-15151771")
    ),
    # The three keys rules 2, 3 and 4 ADD to `output_exchange`'s emission. No
    # capture can contain a key the node did not emit when it was taken, so this
    # is the same class as the `pending` marker above and is handled the same
    # way: FIELD-SCOPED and blanket, so every other byte of every
    # `output_exchange` capture is still graded. Listed LAST on purpose - `find`
    # returns the first matching entry, so the per-fixture entries above win for
    # the captures whose behaviour genuinely moved.
    Divergence(
        node="output_exchange",
        fixture=None,
        hazard="owner ruling K rules 2/3/4 (AC-816) - added diagnostics",
        reason=(
            "`member_offer_filter_modification`, `bare_entity_retyped` and "
            "`entities_dropped_on_topic_change` are diagnostics the port emits and n8n "
            "has no equivalent of. Field-scoped: the rest of every capture still grades, "
            "and the behaviour behind each key is pinned by its own unit test. Only the "
            "first is reached by the corpus today (3 captures, all of them turns where "
            "the filter arm and n8n's Tier 3 both touch nothing, so the key is the whole "
            "difference); the other two are listed with it because they are the same "
            "class - a key no capture can contain - and a capture that reached one would "
            "otherwise fail on a diagnostic rather than on behaviour."
        ),
        strip_paths=(
            ("output", "member_offer_filter_modification"),
            ("output", "bare_entity_retyped"),
            ("output", "entities_dropped_on_topic_change"),
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
