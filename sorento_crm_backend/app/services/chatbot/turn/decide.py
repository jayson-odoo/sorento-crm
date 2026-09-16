# decide(): the ONE reading of a message against the open question and the standing
# subject (owner go, 18 Sep 2026 - "we have been fixing bugs in circles").
#
# Four places used to decide this between them, and they disagreed at the edges: the pick
# helper, the outstanding question's own arm, the focus rules' shared-axis eviction, and
# the generic pending path. They interact on every turn, and every hand pass since the
# second one found a path one of them missed. They all read a `Decision` now, and this
# module is the only place the rule lives.
#
# Four outcomes, and nothing else:
#
#   ANSWER   the message answers the open question - a position, an offered option named
#            by its exact label, a yes to an offer, or "all" over a numbered menu. An
#            escalation offer takes one explicit position or a yes, nothing weaker.
#   REFINE   the message keeps the standing subject and narrows it - the parser's own
#            "only" marker, entities that sit on axes the subject does not hold, or a
#            date window on its own (R15, R24).
#   NEW_ASK  the message names a subject of its own - `entity_op: replace`, an entity on
#            the subject's own axis, or a document named while an outstanding question is
#            open.
#   CARRY    nothing matched. The question stays open, unrepeated, and the message runs
#            as itself (owner ruling, S6 cluster 4).
#
# The Decision says WHAT the message is. Each arm keeps its own EFFECTS - what it writes
# to the focus, the pending and the trace - because those differ by arm and always did:
# a new ask drops an outstanding question but leaves a roster standing.
#
# Pure, like the rest of the package: no message text, no I/O, no imports from the old
# seams.
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.chatbot.turn.pending import ESCALATION_OFFER_KINDS, Pending
from app.services.chatbot.turn.state import KIND_FIELD_MAP, Focus

#: The four outcomes.
ANSWER = "answer"
REFINE = "refine"
NEW_ASK = "new_ask"
CARRY = "carry"

#: Contract 38 and 39: the outstanding report's own two questions. Business questions,
#: not escalation offers - answering one is a fetch.
OUTSTANDING_KINDS: frozenset[str] = frozenset({"outstanding_scope", "outstanding_detail"})

#: The scope an option names, as the documents the focus then carries. One table, read
#: both ways: a picked option becomes a `document` list, and a `document` the parser
#: emitted in WORDS ("sales order", "both") answers the same question.
DOCUMENT_BY_SCOPE: dict[str, list[str]] = {"so": ["SO"], "do": ["DO"], "both": ["SO", "DO"]}
SCOPE_BY_DOCUMENT: dict[tuple[str, ...], str] = {
    ("SO",): "so",
    ("DO",): "do",
    ("DO", "SO"): "both",
}


@dataclass(frozen=True)
class Decision:
    """What a message did to the open question and to the standing subject.

    `kind` is one of the four above and `why` names the single rule that decided it -
    together they are what the trace records and what the console drawer prints, so an
    operator reading a turn sees the decision itself, not a list of rules that fired.

    The rest are the facts the arms need and used to re-derive for themselves, each read
    off the verdict exactly once:

    * `positions` - the option numbers an ANSWER picked.
    * `entities` - the entities the message carries, as the arms see them.
    * `window` - the date window this message named, or None.
    * `scope` - the outstanding scope an ANSWER picked or a NEW_ASK named ("so", "do",
      "both"), and for a REFINE the scope the open question was already about.
    * `declined` - the parser's explicit "no thanks" flag.
    * `negated` - `is_affirmative` came back false, which is a weaker signal and is read
      with the entities beside it.
    * `replaces_every_axis` - `entity_op: replace`, the op a turn carries when its own
      entities ARE the whole scope on every axis.
    * `exclusive` - `scope_exclusive`, the parser's own "only" marker.
    """

    kind: str
    why: str
    positions: tuple[int, ...] = ()
    entities: tuple[dict[str, Any], ...] = ()
    window: dict[str, Any] | None = None
    scope: str | None = None
    declined: bool = False
    negated: bool = False
    replaces_every_axis: bool = False
    exclusive: bool = False

    @property
    def answers(self) -> bool:
        return self.kind == ANSWER

    @property
    def refines(self) -> bool:
        return self.kind == REFINE

    def as_trace(self) -> dict[str, str]:
        return {"kind": self.kind, "why": self.why}


def _positions_by_label(pending: Pending, verdict: dict[str, Any]) -> list[int]:
    """The offered positions this message named by their own LABEL, exactly.

    Half of the pick rule (owner ruling, hand pass 3): a customer who types
    "SRTWC286-SH-150" back at a roster that offered it has answered position 2, and the
    parser emits that as an ENTITY, because an entity is what it is. The comparison is
    an exact string match against the option's own label, case-insensitive and nothing
    more: the engine matches labels, it never reads words (D1, AC-1520), so a paraphrase
    ("the SH one", "the DO list") stays the parser's job and arrives as
    `reference_positions`.

    Only an entity THIS message named counts. A carried one rides along on every turn of
    a conversation about it, and reading that as an answer would answer the question in
    the same breath it was asked.
    """
    named = {
        str(value).strip().lower()
        for e in (verdict.get("entities") or [])
        if isinstance(e, dict) and e.get("current_message") is True
        for value in (e.get("canonical_code"), e.get("raw"))
        if isinstance(value, str) and value.strip()
    }
    if not named:
        return []
    return [
        o["position"]
        for o in pending.options
        if o.get("position") is not None
        and isinstance(o.get("label"), str)
        and o["label"].strip().lower() in named
    ]


#: How far `broaden_to` widens the axis `broaden_axis` names (owner ruling, 17 Sep 2026).
FAMILY = "family"
EVERYTHING = "all"


def broaden_kind(verdict: dict[str, Any]) -> str | None:
    """The entity kind `broaden_axis` names, or None for "all" / nothing.

    Contract 31, R21. The parser emits the AXIS it was asked to widen, and "all" is only
    the commonest value of it: "okay nvm for all products" and "for any products" both
    emitted `broaden_axis: "product"` over an order question carrying SRTWC286-SH, and
    both were answered for SRTWC286-SH anyway (turns 6095ce66 / d8ab659e, 17 Sep 2026) -
    the key had exactly one reader and it tested for the string "all".
    """
    axis = verdict.get("broaden_axis")
    if not isinstance(axis, str):
        return None
    axis = axis.strip().lower()
    if not axis or axis == EVERYTHING:
        return None
    return axis


def broaden_level(verdict: dict[str, Any]) -> str | None:
    """`broaden_to`: "family", "all", or None - HOW FAR the axis is widened.

    A key of its own because the axis alone cannot tell "all variants of 286" (the
    family stands, the variant goes) from "for all products" (the axis goes). Absent
    reads as None, so a verdict recorded before the key existed behaves exactly as it
    did.
    """
    level = verdict.get("broaden_to")
    if not isinstance(level, str):
        return None
    level = level.strip().lower()
    return level if level in (FAMILY, EVERYTHING) else None


def broadens_the_roster(verdict: dict[str, Any], pending: Pending) -> bool:
    """Does this message widen the very axis the open roster is a choice of?

    `broaden_axis: "all"` widens every axis and therefore this one too - contract 31's
    own rule, unchanged. A NAMED axis does it when the roster is about that kind and the
    message asked for any widening at all, at EITHER level: a roster IS the family, so
    "all variants of 286" and "for all products" both come to the same thing over it
    (hand pass 2 item 10). "for all products" over a CUSTOMER picker answers nothing.
    """
    if verdict.get("broaden_axis") == EVERYTHING:
        return True
    axis = broaden_kind(verdict)
    return (
        axis is not None
        and broaden_level(verdict) is not None
        and pending.kind == f"{axis}_pick"
    )


def picked_positions(pending: Pending, verdict: dict[str, Any]) -> tuple[list[int], str] | None:
    """Which of the open question's positions this message picked, and by which signal.

    Owner ruling, hand pass 3 (17 Sep 2026), superseding S6 cluster 4's
    `answers_open_question`: that key is retired from the schema, the prompt and here,
    and a message answers the open question in exactly three ways at this seam - a
    `reference_positions` entry (the parser resolves every paraphrase, every ordinal and
    every worded label onto a POSITION, which is the one signal every recorded verdict
    also carries), an entity matching an offered option by exact label, or
    `broaden_axis: "all"` over a numbered menu. Anything else is not an answer: the
    question stays open and the message runs as itself.

    A recorded verdict that still carries the retired key is simply not read at all.
    """
    raw = verdict.get("reference_positions")
    positions = (
        [int(p) for p in raw if isinstance(p, (int, float)) and not isinstance(p, bool)]
        if isinstance(raw, list)
        else []
    )
    broadens = broadens_the_roster(verdict, pending)
    if pending.kind in ESCALATION_OFFER_KINDS:
        # A handover is the most expensive thing the bot can do with a message, so it
        # takes an EXPLICIT signal and nothing weaker: ONE position the customer typed
        # (which is how a multi-team roster is answered at all, contract 108), or the
        # plain yes the acceptance arm reads for itself. A label match and a broaden are
        # both too weak to hand a conversation to a human on, and so is a SET of
        # positions: there is no handing one conversation to every team at once, which
        # is the rule contract 31 already keeps for "all". Measured on
        # `console/handpass3-owner-17sep-purchase-cost-po.json` step 3, where the ten
        # positions of a product roster, typed over an offer the live engine had left
        # open, assigned a human to a question about purchase orders.
        if broadens or len(positions) != 1:
            return None
        return positions, "positions"
    if positions:
        return positions, "positions"
    labelled = _positions_by_label(pending, verdict)
    if labelled:
        return labelled, "label_match"
    if broadens and pending.options:
        # Contract 31, R21: "all" over a numbered menu is a pick of EVERY option, not a
        # widening of the search - the parser reads the word as a broaden (`entity_op:
        # "clear"`, `broaden_axis: "all"`) because that is what it means anywhere else,
        # and over an open roster it means the opposite. Read off the parser's own field
        # rather than the word; live, "all" over a three-family customer picker ran the
        # plain order list with no status and no dates, where "1" answered correctly.
        return [o["position"] for o in pending.options], "broaden_all"
    return None


def _date_window(verdict: dict[str, Any]) -> dict[str, Any] | None:
    """The window this message named, as one value. `_focus_rules` writes it and the
    outstanding arm tests it, so it is derived once."""
    if not (
        verdict.get("date_mode")
        or verdict.get("date_filter_start")
        or verdict.get("date_filter_end")
    ):
        return None
    return {
        "mode": verdict.get("date_mode"),
        "start": verdict.get("date_filter_start"),
        "end": verdict.get("date_filter_end"),
    }


def _question_filters(pending: Pending | None) -> dict[str, Any]:
    if pending is None:
        return {}
    filters = pending.payload.get("filters")
    return filters if isinstance(filters, dict) else {}


def _question_subject_axes(pending: Pending | None) -> set[str]:
    """The focus slots the OPEN QUESTION's own subject occupies.

    The axis is `KIND_FIELD_MAP`'s - one slot per kind - deliberately NOT the order
    domain's shared "which order" axis, which collapses product, customer and order
    number into one. That collapse is the right answer for the order LIST (hand pass 2
    item 5, where the question is which orders are meant) and the wrong one when the
    question is which subject this turn narrows: a product report and a customer report
    are two different things a report can be about. Main's own
    `_outstanding_subject_axes` made the same carve-out for the same reason.
    """
    filters = _question_filters(pending)
    axes: set[str] = set()
    if filters.get("product_code") or filters.get("product_codes"):
        axes.add(KIND_FIELD_MAP["product"])
    if filters.get("customer_ids"):
        axes.add(KIND_FIELD_MAP["customer"])
    return axes


def _stored_scope(pending: Pending | None) -> str | None:
    scope = _question_filters(pending).get("scope")
    return scope if scope in DOCUMENT_BY_SCOPE else None


def _named_scope(verdict: dict[str, Any]) -> str | None:
    named = tuple(sorted(str(d).strip().upper() for d in (verdict.get("document") or [])))
    return SCOPE_BY_DOCUMENT.get(named)


def _picked_scope(pending: Pending, positions: list[int]) -> str | None:
    matched = [o for o in pending.options if o.get("position") in positions] if positions else []
    values = [(o.get("payload") or {}).get("value") for o in matched]
    # "all" over the scope question picks every option, and every option at once IS the
    # widest one - answering "both" rather than the first row on the list.
    scope = "both" if "both" in values else next((v for v in values if v), None)
    return scope if scope in DOCUMENT_BY_SCOPE else None


def _keeps_subject(
    verdict: dict[str, Any], pending: Pending, entities: list[dict[str, Any]]
) -> bool:
    """R15 (owner ruling, 13 Sep 2026): does the PARSER's own verdict say this turn kept
    the subject of the open question and merely narrowed it?

    Two signals, both the parser's, neither a word list:

    * `entity_op: "reuse"` - the parser read the turn as carrying no new value at all ("i
      want to see this month only" is `reuse` plus a date window), so whatever it names is
      a filter over the report already on screen.
    * `entity_op: "replace_combine"` whose entities all sit on axes OTHER than the stored
      subject's. There is only ever ONE subject, so an entity on the subject's own axis
      REPLACES it, and that is a new ask.

    R24 (owner round 9b) narrows it to the shape a refinement actually has: a turn the
    parser classifies as a business question OF ITS OWN - `business_query` with a non-null
    `domain_hint` - is a new ask whatever axes its entities sit on. The axis test alone
    called "delivery status for hanlim" (a customer under a PRODUCT-subject offer, so a
    different axis) a refinement of the old product's report: "I kind of can't escape this
    loop."
    """
    if verdict.get("entity_op") not in ("reuse", "replace_combine"):
        return False
    if verdict.get("message_type") == "business_query" and verdict.get("domain_hint"):
        return False
    subject_axes = _question_subject_axes(pending)
    if not subject_axes:
        # Nothing stored to keep. An entity would be NAMING the subject, not narrowing
        # it, so the turn is the new ask the arms below already call it.
        return False
    for entity in entities:
        axis = KIND_FIELD_MAP.get(entity.get("hint"))
        if axis is None or axis in subject_axes:
            return False
    return True


def _has_standing_subject(focus: Focus, pending: Pending | None) -> bool:
    """Is there anything to narrow? A refinement needs a subject to refine.

    The open question's own resolved subject comes first (it is what the question was
    asked ABOUT), and the focus stands in when no question is open.
    """
    if _question_subject_axes(pending):
        return True
    return any(getattr(focus, attr, None) for attr in set(KIND_FIELD_MAP.values()))


def _subject_reading(
    verdict: dict[str, Any],
    focus: Focus,
    pending: Pending | None,
    entities: list[dict[str, Any]],
    window: dict[str, Any] | None,
    facts: dict[str, Any],
) -> Decision:
    """The message read against the STANDING SUBJECT, once the open question is settled.

    This is the reading the shared-axis eviction in `_focus_rules` needs on every turn,
    open question or not, and the one the outstanding arm needs to tell a narrowing from
    a fresh question.
    """
    named = tuple(entities)
    if facts["replaces_every_axis"] and entities:
        # The retired head's own rule, kept: `replace` means this turn's entities ARE the
        # whole scope, on every axis. It is only ever stamped by a turn that has already
        # folded in whatever it means to keep, so it outranks the "only" marker below on
        # the one verdict that could carry both.
        return Decision(NEW_ASK, "entity_op_replace", entities=named, window=window, **facts)
    if facts["exclusive"] and (entities or window) and _has_standing_subject(focus, pending):
        # `scope_exclusive` is the parser's own "only" marker and the single
        # discriminator between the two turns that otherwise look identical. Both name a
        # product under an order subject that carries a customer, and both emit
        # `entity_op: replace_combine`, so the op alone cannot decide:
        #
        # * c45e2929 "Outstsnding DO for 7445" - `scope_intent: null`,
        #   `scope_exclusive: false`. A NEW ASK that states its own scope, and the
        #   customer named six turns earlier is last question's (hand pass 2 item 5).
        # * 67df5114 "For srtwc286 only" - `scope_intent: "specific"`,
        #   `scope_exclusive: true`. A refinement of "orders for CHIN CHUN HARDWARE", and
        #   evicting the customer re-asked a fresh roster and then answered globally
        #   (browser pass 6 item 3).
        return Decision(REFINE, "scope_exclusive", entities=named, window=window, **facts)
    if pending is not None and (entities or window) and _keeps_subject(verdict, pending, entities):
        return Decision(
            REFINE,
            "narrows_the_open_question",
            entities=named,
            window=window,
            scope=_stored_scope(pending),
            **facts,
        )
    if entities:
        return Decision(NEW_ASK, "names_its_own_entity", entities=named, window=window, **facts)
    return Decision(CARRY, "nothing_answered", window=window, **facts)


def decide(
    verdict: dict[str, Any], focus: Focus, pending: Pending | None = None
) -> Decision:
    """One message, one reading. Pure: the same three inputs always give the same
    Decision, and nothing here writes to any of them.
    """
    escalation = verdict.get("escalation") or {}
    entities = [e for e in (verdict.get("entities") or []) if e]
    window = _date_window(verdict)
    facts: dict[str, Any] = {
        "declined": escalation.get("escalation_declined") is True,
        "negated": verdict.get("is_affirmative") is False,
        "replaces_every_axis": verdict.get("entity_op") == "replace",
        "exclusive": bool(verdict.get("scope_exclusive")),
    }

    if pending is None:
        return _subject_reading(verdict, focus, None, entities, window, facts)

    picked = picked_positions(pending, verdict)
    positions = list(picked[0]) if picked else []

    if pending.kind in OUTSTANDING_KINDS:
        # The outstanding question's own order, which is NOT the generic one: a turn that
        # narrows an open report names a filter too, so the refinement is read before
        # anything else, and a document named in words outranks a position riding along
        # with it (owner ruling, hand pass 3 row 5; browser pass 6 item 5, turn e0d6459c).
        reading = _subject_reading(verdict, focus, pending, entities, window, facts)
        if not positions and reading.refines:
            return reading
        if entities:
            # D17 point 3: a stray position riding along with an entity is still a new
            # ask, because the parser is told never to emit both.
            return Decision(
                NEW_ASK,
                reading.why if reading.kind == NEW_ASK else "names_its_own_entity",
                positions=tuple(positions),
                entities=tuple(entities),
                window=window,
                **facts,
            )
        named_scope = _named_scope(verdict)
        if named_scope is not None:
            # "Sales order", typed straight after the DO detail list, emitted
            # `document: ["SO"]` AND `reference_positions: [1]`, and the position won:
            # position 1 of that offer is its only option, "Delivery order list", so the
            # same twenty DO lines came back byte for byte at a customer who had just
            # said which paper they wanted.
            return Decision(
                NEW_ASK,
                "named_document",
                positions=tuple(positions),
                window=window,
                scope=named_scope,
                **facts,
            )
        picked_scope = _picked_scope(pending, positions)
        if picked_scope is not None:
            return Decision(
                ANSWER,
                "picked_scope",
                positions=tuple(positions),
                window=window,
                scope=picked_scope,
                **facts,
            )

    if positions:
        # A position nobody offered is still an ATTEMPT at this question - the arm
        # re-prints it rather than dropping it silently.
        return Decision(
            ANSWER,
            picked[1] if picked else "positions",
            positions=tuple(positions),
            entities=tuple(entities),
            window=window,
            **facts,
        )

    accepted = (
        verdict.get("is_affirmative") is True
        or escalation.get("is_escalation_confirmation") is True
    )
    if accepted and not (facts["declined"] or facts["negated"]):
        # A decline outranks every acceptance signal - the acceptance arm has always read
        # it that way, and now the generic path does too.
        return Decision(
            ANSWER, "affirmative", entities=tuple(entities), window=window, **facts
        )

    return _subject_reading(verdict, focus, pending, entities, window, facts)
