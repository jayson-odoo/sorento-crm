# apply(): the pure core (PLAN-chatbot-turn-rearch.md "APPLY contract", AC-1520). One
# function; the order below is the order it runs, and the order IS the contract:
#
#   0. `decide()`         - ONE reading of this message against the open question and the
#                           standing subject (`turn/decide.py`): ANSWER, REFINE, NEW_ASK
#                           or CARRY. Every arm below reads that Decision; none of them
#                           decides for itself.
#   1. `_reconcile_step`  - an entity the resolver placed under one kind is rewritten to
#                           it; two kinds arm a `kind_pick` and nothing else runs.
#   2. `_answer_pending`  - the open question, resolved, re-printed or carried.
#   4. `_focus_rules`     - topic reset, replace-same-axis, the domain, document/status,
#                           the date window.
#   5. domain resolution  - the locked pick, else `asks`, else `domain_hint`, else the
#                           carried focus, else the document's own domain.
#   6. `_did_you_mean`, then a `set_page` continuation - each returns its own Plan.
#   7. `_narrow_and_plan` - the narrower and the fetch plan, folded into one per-domain
#                           loop because they share it.
#
# No message text read anywhere below - every input is already-structured (Verdict dict,
# Policy, State).
from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any

from app.services.chatbot import contracts
from app.services.chatbot.turn.decide import (
    ANSWER,
    DOCUMENT_BY_SCOPE,
    NEW_ASK,
    OUTSTANDING_KINDS,
    EVERYTHING,
    FAMILY,
    Decision,
    broaden_kind,
    broaden_level,
    decide,
)
from app.services.chatbot.turn.narrow import decide as narrow_decide
from app.services.chatbot.turn.pending import (
    ESCALATION_OFFER_KINDS,
    OFFER_KINDS,
    Pending,
    ask as pending_ask,
    is_roster,
    with_answered_positions,
)
from app.services.chatbot.turn.plan import FetchSpec, Plan, Trace
from app.services.chatbot.turn.policy import Policy
from app.services.chatbot.turn.reconcile import apply_reconciliation
from app.services.chatbot.turn.state import KIND_FIELD_MAP, Focus, State

RESET_KEEPS = {"tier", "brands"}

# D6, "domain follows the document": a turn that names a document kind and no domain is
# about the domain that OWNS that document. A dict rather than a policy column because it
# is five literals that follow from what the document IS - a migration for this would be a
# table with one true row shape and no second reader.
DOMAIN_BY_DOCUMENT: dict[str, str] = {
    "SO": "order",
    "DO": "order",
    "PO": "purchase_order",
    "SPO": "incoming",
    "GRN": "goods_receive",
}


def _is_continuation(verdict: dict[str, Any]) -> bool:
    """AC-1317: "show me the next page of the set you just counted".

    The parser's own `continuation` boolean, read as-is - matching free-text `user_goal`
    against a word list was still a text rule wearing the parser's clothes (captain
    ruling, 16 Sep 2026) - AND a message that named no entity of its own. Measured: the
    paging turn's own shape is `{message_type: "clarification", user_goal: "more",
    continuation: true}` with an empty `entities`
    (`test_rearch_s3_attribute_first.py::TestPagingByFive`), while the parser sets the
    same boolean on any ordinary follow-up: "wc287" and "srtwc287", each a product entity
    of its own typed after a counted answer, were both served the NEXT PAGE of it
    ("5,783 taps have stock. Showing 6 to 10.", turns b383d402 / 2e7ca929, 17 Sep 2026).
    A turn that names a new entity re-runs the ladder from the code tier, so it reads no
    cursor and leaves none behind.
    """
    if verdict.get("continuation") is not True:
        return False
    return not any(
        isinstance(e, dict) and e.get("current_message") is not False
        for e in (verdict.get("entities") or [])
    )


def _domain_of_document(document: list[str]) -> str | None:
    for kind in document:
        name = DOMAIN_BY_DOCUMENT.get(str(kind).strip().upper())
        if name:
            return name
    return None


#: Focus slots that hold plain CODES, not entity rows (`Focus.tier`, `Focus.brands`).
#: A pick or a parser entity for one of these kinds writes the code it names, because
#: that is what every reader of the slot expects - `narrow._candidates` rebuilds rows
#: from `focus.tier` itself, so writing entity dicts there made a tier the customer had
#: just picked invisible to the narrower, which asked for it again (hand pass 2 item 9,
#: turn 142dd695).
_CODE_ONLY_FIELDS: dict[str, str] = {"tier": "tier", "brand": "brands"}


def _code_of_entity(entity: dict[str, Any]) -> str | None:
    payload = entity.get("payload") if isinstance(entity.get("payload"), dict) else {}
    value = (
        entity.get("canonical_code")
        or entity.get("code")
        or payload.get("tier")
        or entity.get("raw")
    )
    return str(value) if value else None


def _set_kind_field(focus: Focus, kind: str, entities: list[dict[str, Any]]) -> None:
    code_field = _CODE_ONLY_FIELDS.get(kind)
    if code_field:
        codes = [c for c in (_code_of_entity(e) for e in entities) if c]
        setattr(focus, code_field, codes)
        return
    attr = KIND_FIELD_MAP.get(kind)
    if attr:
        setattr(focus, attr, entities)
    else:
        focus.extra[kind] = entities


def _names_a_subject(verdict: dict[str, Any]) -> bool:
    """Did THIS message name something of its own to be about?

    A carried entity does not count - a confirmation turn routinely still carries the
    previous product, and reading that as a new question would make every "yes" a fresh
    ask (owner report 8 Sep 2026, the half that must not move).
    """
    return any(
        isinstance(e, dict) and e.get("current_message") is True
        for e in (verdict.get("entities") or [])
    )


def _confirmation_defused(verdict: dict[str, Any], trace: Trace) -> dict[str, Any]:
    """A decisive intent plus an entity this message named outranks the parser's own
    `is_escalation_confirmation` (owner report, 8 Sep 2026).

    After a stock answer offered to escalate, "PO for SRTWC8517" came back
    `request_for_help` with `is_escalation_confirmation: true`, so a fresh product question
    confirmed an offer the customer had ignored. The flag is a MODEL judgement about a
    message that also carries the parser's own structured evidence of a new question, and
    the evidence wins.

    Retyped as well as cleared, which is what the retired `output_exchange` did: the flag
    has three readers (`_answer_offer`, `_answer_pending`'s accept arm and `_lane`) and
    `message_type: "request_for_help"` would send the same turn to the escalation lane
    through the other door. Decided ONCE here, at the verdict's entry into `apply()`,
    beside `domain_hint`'s own coercion, so every reader downstream sees one decision.
    """
    escalation = verdict.get("escalation") or {}
    if escalation.get("is_escalation_confirmation") is not True:
        return verdict
    decisive = verdict.get("intent_hint") or verdict.get("domain_hint")
    if not decisive or not _names_a_subject(verdict):
        return verdict
    trace.rules_fired.append("confirmation_defused_by_a_named_ask")
    return {
        **verdict,
        "escalation": {**escalation, "is_escalation_confirmation": False},
        "message_type": "business_query",
    }


def _help_request_is_an_ask(verdict: dict[str, Any]) -> bool:
    """A help request that names a SUBJECT and no intent of its own is that subject's ask.

    Owner turns 2d903c96 / 17d38019 / 3a56a48c, 8 Sep 2026: "delivery to hanlim" came back
    `request_for_help` with both hints null and one customer entity, and the bot handed a
    human a question it answers itself. The retired head read the domain SWITCH WORD out of
    the message to retype it; `apply()` reads no message text (AC-1520) and does not need
    to - the parser naming a subject while naming neither an intent nor a domain is the
    same statement in structured form, and the domain that subject's KIND belongs to is the
    one thing the question can be about.

    Narrow on purpose, both halves measured: a help request with no entity at all ("can
    someone help me with my order") stays a help request, and so does one the parser DID
    give a decisive intent - review round 2's ruling, that shape is the parser's to
    classify, not the gate's.
    """
    return (
        verdict.get("message_type") == "request_for_help"
        and not verdict.get("intent_hint")
        and not verdict.get("domain_hint")
        and _names_a_subject(verdict)
    )


def _domain_of_kind(policy: Policy, kind: str | None) -> str | None:
    """Which domain narrows on this entity kind - the policy's own answer, first row wins.

    The same lookup `_reconcile_step` makes when a rewritten kind has to name its domain.
    """
    if not kind:
        return None
    for row in policy.domains:
        if kind in row.narrowing:
            return row.name
    return None


def _answer_offer(pending: Pending, decision: Decision, focus: Focus, trace: Trace):
    """An escalation offer, ACCEPTED - the mirror of `answer_pending_decline`.

    "Would you like me to escalate?" is answered three ways and every one of them is an
    acceptance: a bare "yes" (`is_affirmative`), the parser's own escalation flag, and a
    NUMBER off a multi-team roster (an explicit `reference_positions` entry). The
    third is why this runs before the roster path below: an accepted offer's option is a
    TEAM, not an entity to fetch with, and the roster path turned "yes" into a product
    pick, restored `payload.domain` and re-ran the very lookup that had just missed
    (browser pass 3, turns 9 and 12 - the same answer back, byte for byte, re-offering
    the same escalation).

    `decide()` settles WHETHER this message accepted (the one-position rule and the
    decline veto both live there now); this arm owns only the EFFECT. The turn
    short-circuits to the escalation lane with the accepted team on the trace, and the
    lane then does its normal work (the assignee draw, the SLA row). Returns the
    four-tuple, or None when this message is not an acceptance - a decline, a miss and an
    aside are all settled by the generic rules below, in one place.
    """
    if decision.declined or decision.negated:
        # A decline outranks every acceptance signal, and it already has a rule below.
        # Both flags are `decide()`'s single reading of the verdict's two decline keys.
        return None
    if not decision.answers:
        return None

    picked: dict[str, Any] | None = None
    if decision.positions:
        picked = next(
            (o for o in pending.options if o.get("position") in decision.positions), None
        )
        if picked is None:
            # A position nobody offered: the re-print rule below owns it, the same as
            # for a roster.
            return None

    option_payload = (picked.get("payload") or {}) if picked else {}
    if option_payload.get("hold") is True:
        # Contract 43: "No it's okay" is on the roster precisely so it can be picked,
        # and picking it is a decline - the same lane the word "no" reaches.
        trace.rules_fired.append("answer_pending_decline")
        trace.lane = "escalation_declined"
        return focus, None, Plan(domains=[], fetch=[], ask=None, denied=[], trace=trace), False

    trace.rules_fired.append("answer_pending_accept")
    trace.lane = "escalation"
    # Contract 108: an acceptance names no team of its own, so the OFFER's team is what
    # the escalation lane routes by - the picked option's when the roster offered
    # several, the offer's own when it was a single-team yes/no.
    trace.team = option_payload.get("team") or pending.team
    return focus, None, Plan(domains=[], fetch=[], ask=None, denied=[], trace=trace), False


def _drop_question_subject(focus: Focus, pending: Pending) -> None:
    """R17: the offer dies, and its filters die with it.

    The scope question and the detail offer are asked about a SUBJECT the lane resolved
    for them (`pending.payload.filters`), and a turn that walks away with its own
    question must not inherit it - "sales order outstanding for SRTWC8517" typed under a
    question about another product kept the old customer and the old location and
    answered about the wrong thing (reviewer N2). Only the axes THAT QUESTION named are
    cleared; `_focus_rules` runs next and re-fills whatever this message named itself.

    It runs on a NEW ASK and on nothing else, so the "unless the turn is exclusive"
    carve-out this used to carry is gone: an exclusive turn is a REFINE at `decide()`,
    and a refinement never reaches this arm. "X only" narrows the standing subject and
    evicts nothing - measured on the owner's own turns, 16 Sep 2026: "i want to see
    fullshun only" typed under the DO detail offer for SRTWC286-SH-200 ran the report for
    Fullshun and `Product: all` (turn 78c7c428), and "ok i want to look at SRTKT1861SS
    only" typed under the DO detail offer for six HANLIM ledgers ran it for the product
    with `customer_ids: []` (turn b06e9ca8). Both lost exactly the half of the subject
    the dead question happened to be carrying.
    """
    filters = pending.payload.get("filters")
    if not isinstance(filters, dict):
        return
    if filters.get("product_code") or filters.get("product_codes"):
        focus.products = []
    if filters.get("customer_ids"):
        focus.customers = []
    if filters.get("warehouse_codes") or filters.get("location_token"):
        focus.warehouse = []
    if filters.get("date_filter_start") or filters.get("date_filter_end"):
        focus.date_window = None
    if filters.get("scope"):
        # The SCOPE is the dead question's too. A detail offer only exists because a report
        # ran, so its filter set carries the document that report was for - and leaving that
        # on the focus meant the next outstanding ask, about a different customer entirely,
        # inherited it and never asked which document it was about (AC-1160/R17, "a fresh
        # outstanding ask arms the scope question"). A turn that names its own document
        # writes it straight back in `_focus_rules`.
        focus.document = []
        focus.status = None


def _settle_question_subject(focus: Focus, pending: Pending, trace: Trace | None = None) -> None:
    """D10: the ANSWER is about what the QUESTION was about, exactly.

    The lane resolved the question's subject when it asked - the code the customer
    TYPED rather than a family sibling (AC-1119), the account ids behind a customer
    name, the warehouses a location word expands to - and stored it on the question
    itself (`turn/compose._lane_question`, from `fetch.outstanding_ask.filters`). The
    focus still holds the raw token the parser emitted, because the order domain does
    not narrow on product and nothing settled it. Settling it HERE, on the answer, is
    what stops the re-run re-resolving a token that can land somewhere else: the answer
    turn typed nothing, so there is nothing new to resolve.
    """
    filters = pending.payload.get("filters")
    if not isinstance(filters, dict):
        return
    # `product_codes` is the SEVERAL-code form of the same filter ("all" over a product
    # roster); `product_code` is the one-code case every other ask carries.
    codes = [c for c in (filters.get("product_codes") or []) if c]
    if not codes and filters.get("product_code"):
        codes = [filters["product_code"]]
    if codes:
        focus.products = [
            {"raw": code, "hint": "product", "canonical_code": code, "current_message": False}
            for code in codes
        ]
        if trace is not None:
            # D10 again, one layer down: a subject the ANSWER settled is not re-resolved
            # this turn. The rows written here carry a code and no uuid, so the fetch's
            # own carry hands them back to the resolver, whose prefix probe returns the
            # whole family - and `_narrow_and_plan` then wrote that family over the very
            # code the question had been asked about (AC-1119,
            # `test_the_answer_turn_reports_the_typed_code`).
            trace.picked_kinds.append("product")
    ids = [u for u in (filters.get("customer_ids") or []) if u]
    if ids:
        focus.customers = [
            {"uuid": uid, "hint": "customer", "current_message": False} for uid in ids
        ]
    codes = [c for c in (filters.get("warehouse_codes") or []) if c]
    token = filters.get("location_token")
    if codes or token:
        focus.warehouse = [
            {
                "raw": token,
                "hint": "warehouse",
                "canonical_code": token,
                "warehouse_codes": codes,
                "current_message": False,
            }
        ]
    if focus.date_window is None and (
        filters.get("date_filter_start") or filters.get("date_filter_end")
    ):
        # A DEFAULT: `_focus_rules` runs next and a window this turn named itself
        # overwrites it (N2 - "2, but only 2026" is answered over ITS dates).
        focus.date_window = {
            "mode": None,
            "start": filters.get("date_filter_start"),
            "end": filters.get("date_filter_end"),
        }


def _answer_outstanding(
    pending: Pending, decision: Decision, focus: Focus, trace: Trace
):
    """Contracts 38 and 39: the outstanding report's scope question and detail offer.

    The retired `head/output_exchange._apply_outstanding_pending` did this by rewriting
    the parser's emission; here the answer moves the FOCUS instead, which is the only
    place the next fetch reads its subject from. `decide()` says WHICH of the four
    readings this message is and this arm owns the effects, one per reading:

    * REFINE (R15): the turn picked nothing, named a filter of its own, and the parser's
      own verdict says it kept the subject. The same report re-runs over the narrower
      window and the same question is re-armed over it.
    * NEW ASK, by naming an entity: the question is dropped rather than mis-resolved, so
      a customer can leave it by asking something else instead of only by answering it
      (D17 point 3 - a stray position riding along with an entity is still a new ask,
      because the parser is told never to emit both).
    * NEW ASK, by naming a DOCUMENT: a new scope. The report re-runs for that document
      and the old question goes with it (owner ruling, hand pass 3 row 5).
    * ANSWER (a picked option) writes `focus.document` - which is what
      `turn_runtime.lane_parse_output` projects back onto the order tools' one
      `order_status` bucket, so the SAME turn re-runs the report for the scope just
      named and the question cannot re-arm itself (`outstanding_scope_ask_candidate`
      reads that bucket).

    Anything else returns None: the generic rules settle it, in one place.

    The scope question clears when it is answered; the detail offer does not (contract
    39, owner ruling 13 Sep 2026 - "after '1' (SO list), typing '2' must give the DO
    list"), so it is the one offer kind that stays on screen across its own pick.
    """
    asked_for = pending.payload.get("domain")

    if decision.refines:
        # The subject SETTLES exactly as an answer's does - the question's own resolved
        # product, customer ids and warehouses - and `_focus_rules` runs next and lays
        # this turn's own window or location over the top. `detail: None` is what makes
        # it a re-run of the REPORT rather than one of its lists: the customer narrowed
        # the search, they did not ask for a list.
        _settle_question_subject(focus, pending, trace)
        focus.status = "outstanding"
        # The scope question has NOT been answered, only narrowed (AC-1158), so the
        # document axis stays empty and `lane_parse_output`'s `("", "outstanding")`
        # bucket re-arms the same question over the new filters through the arm that
        # armed it - one writer for the question's text, no second re-ask path. The
        # detail offer's scope is already known (a report ran, or it could not have
        # offered its lists), so its re-run carries it and never asks a question that
        # has been answered.
        focus.document = list(DOCUMENT_BY_SCOPE[decision.scope]) if decision.scope else []
        if asked_for:
            focus.domains = [asked_for]
        trace.rules_fired.append("outstanding_refined")
        trace.outstanding = {"kind": pending.kind, "scope": decision.scope, "detail": None}
        return focus, pending, None, True

    if decision.kind == NEW_ASK and decision.why == "names_its_own_entity":
        trace.rules_fired.append("outstanding_pending_dropped")
        _drop_question_subject(focus, pending)
        return focus, None, None, False

    if decision.scope is None or decision.kind not in (ANSWER, NEW_ASK):
        return None

    named_scope = decision.why == "named_document"
    _settle_question_subject(focus, pending, trace)
    focus.document = list(DOCUMENT_BY_SCOPE[decision.scope])
    focus.status = "outstanding"
    if asked_for:
        # Contract 121: the answer goes back to the domain the question was asked for.
        focus.domains = [asked_for]
    # A document the message NAMED is a new scope, not a pick off the offer: the REPORT
    # re-runs for that document and the old question goes with it (row 5). A POSITION is
    # the offer's own answer and keeps contract 39's rule, where the detail offer is the
    # one kind that survives its own pick.
    answers_the_offer = pending.kind == "outstanding_detail" and not named_scope
    trace.rules_fired.append(
        "answer_outstanding" if not named_scope else "outstanding_pending_dropped"
    )
    trace.outstanding = {
        "kind": pending.kind,
        "scope": decision.scope,
        # Contract 39: "1" asks for one of the report's LISTS, which is the same tool
        # call with a `detail` argument. The scope question asks which document the
        # report itself is about, and that is the `document` axis alone.
        "detail": decision.scope if answers_the_offer else None,
    }
    carried = pending if answers_the_offer else None
    return focus, carried, None, True


def _answer_pending(state: State, decision: Decision, trace: Trace):
    # Returns (focus_after, pending_after, short_circuit_plan, domain_locked).
    #
    # Every branch here is an EFFECT of the one Decision `decide()` already made; not one
    # of them re-reads the verdict to decide for itself.
    pending = state.pending
    focus = copy.deepcopy(state.focus)

    if pending is None:
        return focus, None, None, False

    if pending.kind in OUTSTANDING_KINDS:
        # BEFORE the generic roster path: these options are a SCOPE, not an entity to
        # fetch with, and building one into an entity sent "Both" to the resolver as an
        # order token (console run 4, finding 6).
        answered = _answer_outstanding(pending, decision, focus, trace)
        if answered is not None:
            return answered

    if pending.kind in ESCALATION_OFFER_KINDS:
        # BEFORE the roster path: an accepted escalation offer is a handover, never a
        # fetch, whichever of the three ways it was accepted.
        accepted = _answer_offer(pending, decision, focus, trace)
        if accepted is not None:
            return accepted

    positions = list(decision.positions) if decision.answers else []
    if positions:
        matched = [o for o in pending.options if o.get("position") in positions]
        if not matched:
            # The message picked a position, but nothing it picked is on the list - a
            # number off the end of the roster. That IS an attempt at this question, so
            # the SAME question is re-printed, state untouched. Clearing the pending
            # instead (which is what fell out of the `if matched:` guard before) dropped
            # the question silently and left the customer's next message with nothing to
            # answer.
            trace.rules_fired.append("answer_pending_unresolved")
            return (
                state.focus,
                pending,
                Plan(domains=[], fetch=[], ask=pending, denied=[], trace=trace),
                False,
            )
        built: list[dict[str, Any]] = []
        for option in matched:
            uuids = option.get("uuids") or ([option["uuid"]] if option.get("uuid") else [])
            # ONE rule for what a picked option becomes (browser pass 2, turns 4 / 8 / 6):
            # the CODE is the entity's `canonical_code` and the uuid is its `uuid`, which
            # is the same shape a resolver-matched entity reaches the fetch in
            # (`turn_runtime.candidates_by_kind`). Writing the uuid into `canonical_code`
            # sent it everywhere a code belongs: the answer's header named
            # `*incoming stock* for 65514803-...`, and the outstanding report was asked
            # for `product_code = <uuid>` and honestly found nothing. A customer option
            # carries both - the account code nobody typed AND the name the roster
            # printed - so the header can say the name while the tool filters on the id.
            option_payload = option.get("payload") if isinstance(option.get("payload"), dict) else {}
            # An option that is not a ROW has no uuid to carry, and its own machine value
            # is on its payload: a tier is "dealer", not a record anything can be fetched
            # by. Reading the payload first is what makes the value land rather than the
            # printed label ("end user" against "end_user").
            code = option.get("code") or (option_payload.get("value") if not uuids else None)
            code = code or option.get("label")
            name = option.get("name")
            if not uuids:
                # Hand pass 2 finding 9 / hand pass 3 row 1: a tier pick built NOTHING,
                # because the entity was assembled inside the uuid loop and a tier option
                # has no uuid - so `focus.tier` stayed empty, `narrow_by_tier` re-armed the
                # very question just answered, and the promotion fetch that should have run
                # for the carried product never ran at all (turns 9b5e241e / c7cb01fc).
                built.append(
                    {
                        "raw": code,
                        "hint": option.get("entity_type"),
                        "canonical_code": code,
                        "current_message": True,
                        "confident": True,
                        **({"name": name} if name else {}),
                    }
                )
            for u in uuids:
                entity: dict[str, Any] = {
                    "raw": code,
                    "hint": option.get("entity_type"),
                    "canonical_code": code,
                    "uuid": u,
                    "current_message": True,
                    "confident": True,
                }
                if name:
                    entity["name"] = name
                built.append(entity)
        kind_for_focus = matched[0].get("entity_type")
        if kind_for_focus:
            _set_kind_field(focus, kind_for_focus, built)
            # Item 10: what the customer just picked is settled, whatever the domain's
            # narrowing policy says about the same rows carried in from earlier. "All"
            # over a ten-variant roster is an explicit answer, and `narrow_to_code`'s
            # "ten codes is still ten codes" re-ask (written for a CARRY) printed the
            # very roster that had just been answered straight back.
            trace.picked_kinds.append(str(kind_for_focus))

        trace.rules_fired.append("answer_pending")
        # Contract 121: a pick never re-domains the turn. The question recorded the
        # domain it was asked for, so the answer goes back to it rather than leaving
        # a bare positional with nothing to be about.
        asked_for = pending.payload.get("domains") or (
            [pending.payload["domain"]] if pending.payload.get("domain") else []
        )
        if asked_for:
            focus.domains = [d for d in asked_for if isinstance(d, str) and d]
        if is_roster(pending.kind):
            return focus, with_answered_positions(pending, positions), None, True
        return focus, None, None, True

    if decision.answers and decision.why == "affirmative":
        trace.rules_fired.append("answer_pending_accept")
        if pending.payload.get("escalate_offered") is True:
            # Item 8's other half: the open question is the ROSTER, and the escalate
            # offer under it is a sentence, not a second question - so a plain "yes" over
            # this state is answering the OFFER and has to reach the escalation lane with
            # the team the offer named. Without this the roster simply cleared and the
            # customer who said yes got nothing.
            trace.lane = "escalation"
            trace.team = pending.team
            return focus, None, Plan(domains=[], fetch=[], ask=None, denied=[], trace=trace), False
        return focus, None, None, False

    if decision.declined or (decision.negated and not decision.entities):
        trace.rules_fired.append("answer_pending_decline")
        if pending.kind in OFFER_KINDS:
            # The offer was answered with a decline: that IS the turn (contract 42, the
            # `escalation_declined` lane), named here off the APPLY outcome rather than
            # off `escalation.escalation_declined` alone, which the parser emits only
            # for the explicit word - measured: all 19 recorded `escalation_declined`
            # turns carry `is_affirmative: false` and a null flag. Without this the
            # cleared pending fell through to a fetch of the carried focus and the
            # customer who said "no thanks" got the order list again.
            trace.lane = "escalation_declined"
            return focus, None, Plan(domains=[], fetch=[], ask=None, denied=[], trace=trace), False
        return focus, None, None, False

    if decision.negated and decision.entities:
        # A "no" carrying its own entities is not a decline - the offer stays open.
        trace.rules_fired.append("answer_pending_own_entities")
        return focus, pending, None, False

    # NOTHING matched the open question: no position, no offered label, no broaden, no
    # yes and no no. Owner ruling, hand pass 3 - the question stays open exactly as it
    # was and the message is planned as itself, whatever it is; the tail keeps the
    # carried pending (`answer.question or state.pending`). The old "the parser says it
    # tried and missed" arm went with `answers_open_question`, and with it the re-print
    # that re-asked the customer on every aside (finding 2a) and that argued with a turn
    # naming its own business subject over an escalation offer (growth r1).
    trace.rules_fired.append("answer_pending_not_an_answer")
    return focus, pending, None, False


def _focus_rules(
    focus: Focus,
    verdict: dict[str, Any],
    entities: list[dict[str, Any]],
    decision: Decision,
    *,
    domain_locked: bool,
    domain_override: str | None,
    trace: Trace,
) -> Focus:
    if verdict.get("topic_reset"):
        # Every axis the old topic filled goes; the tier and the brand are the contact's,
        # not the topic's, so they stay. The rules BELOW still run on the emptied focus -
        # a reset turn is a new topic, and it names that topic's own domain and entities
        # in the same breath ("never mind, promotions?"). Returning here left the new
        # topic with no domain at all, so the next reset had nothing to close an episode
        # on (AC-1546).
        kept = {k: getattr(focus, k) for k in RESET_KEEPS}
        focus = Focus(**kept)
        trace.rules_fired.append("reset_on_topic")

    confident_entities = [e for e in entities if e.get("confident") is not False]
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for e in confident_entities:
        hint = e.get("hint")
        if not hint:
            continue
        by_kind.setdefault(hint, []).append(e)

    for kind, group in by_kind.items():
        _set_kind_field(focus, kind, group)
    if by_kind:
        trace.rules_fired.append("replace_same_axis")
    else:
        trace.rules_fired.append("reuse_alive")

    asks = verdict.get("asks") or []
    if by_kind:
        if decision.starts_fresh:
            # A NEW ASK that says WHAT it is asking starts from that domain's defaults:
            # every carried kind this message did not name goes (owner ruling, 17 Sep
            # 2026). "Delivery to hanlim" then "outstanding DO for 7445" is a question
            # about 7445 and EVERY customer, where the carried HANLIM ledgers had been
            # answering it for one (turn c45e2929). A refinement never evicts: it
            # combines across kinds and replaces only within the kind it named, so
            # "orders for hanlim" then "for srtwc286" is hanlim AND srtwc286.
            #
            # This replaces `SHARED_AXIS_BY_DOMAIN`, a per-domain table of which kinds
            # "say the same thing", which could not tell those two apart at all - both
            # name a product on the order domain's own shared axis.
            for kind, attr in KIND_FIELD_MAP.items():
                if kind in by_kind:
                    continue
                if getattr(focus, attr, None):
                    setattr(focus, attr, [])
                    trace.rules_fired.append(f"new_ask_drops_{kind}")
        elif decision.refines:
            trace.rules_fired.append("refinement_keeps_subject")

    if not domain_locked:
        if domain_override:
            focus.domains = [domain_override]
            trace.rules_fired.append("domains_from_reconciliation")
        elif asks:
            focus.domains = [a["domain"] for a in asks if a.get("domain")]
            trace.rules_fired.append("domains_from_asks")
        elif verdict.get("domain_hint"):
            focus.domains = [verdict["domain_hint"]]
            trace.rules_fired.append("domains_from_asks")
        # else: no domain word this turn - focus.domains carries over unchanged.

    _broaden(focus, verdict, decision, by_kind, trace)

    document = verdict.get("document")
    status = verdict.get("status")
    if document:
        focus.document = list(document)
    if status:
        focus.status = status
    if verdict.get("date_mode") or verdict.get("date_filter_start") or verdict.get("date_filter_end"):
        focus.date_window = {
            "mode": verdict.get("date_mode"),
            "start": verdict.get("date_filter_start"),
            "end": verdict.get("date_filter_end"),
        }
        trace.rules_fired.append("date_restated_only")

    return focus


def _broaden(
    focus: Focus,
    verdict: dict[str, Any],
    decision: Decision,
    by_kind: dict[str, list[dict[str, Any]]],
    trace: Trace,
) -> None:
    """The ONE reader of `broaden_axis` + `broaden_to` (owner ruling, 17 Sep 2026).

    The parser says WHICH axis and HOW FAR; this decides nothing and only applies it.

    * `all` on a named axis - that axis is dropped. "okay nvm for all products" and "for
      any products", both over an order question carrying SRTWC286-SH, were answered for
      SRTWC286-SH (turns 6095ce66 / d8ab659e).
    * `all` with no axis named (`broaden_axis: "all"`) - every axis is dropped and the
      DOMAIN stays: the question is the same question, widened.
    * `family` on a named axis - the variant is dropped and the family stands. The uuid is
      what makes a focus row a VARIANT, so removing it (keeping the code) is the whole
      change: an unsettled carry is exactly what the engine hands the resolver, whose
      prefix probe answers with the family (`turn_runtime.with_carried_entities`,
      `unsettled_only`), and the narrower settles it again this same turn.

    Never when this message ANSWERED the open roster: the options the pick folded in are
    already the widened set (`decide.broadens_the_roster`, contract 31 / hand pass 2 item
    10). Never for an axis this message also named outright - naming it IS the scope.
    """
    level = broaden_level(verdict)
    if level is None or decision.answers:
        return
    axis = broaden_kind(verdict)
    if level == EVERYTHING and axis in (None, "date") and focus.date_window:
        # The date is an axis too ("all time", "any date"), and it is the one axis that
        # is a window rather than a list of rows - so it is cleared by name.
        focus.date_window = None
        trace.rules_fired.append("broaden_all_clears_date")
    axes = [axis] if axis else list(KIND_FIELD_MAP)
    for kind in axes:
        attr = KIND_FIELD_MAP.get(kind)
        rows = getattr(focus, attr, None) if attr else None
        if not attr or not rows or kind in by_kind:
            continue
        if level == EVERYTHING:
            setattr(focus, attr, [])
            trace.rules_fired.append(f"broaden_all_clears_{kind}")
        elif level == FAMILY:
            widened = [{k: v for k, v in row.items() if k != "uuid"} for row in rows if isinstance(row, dict)]
            if widened != rows:
                setattr(focus, attr, widened)
                trace.rules_fired.append(f"broaden_family_{kind}")


def _reconcile_step(
    entities: list[dict[str, Any]],
    resolved: dict[str, dict[str, int]] | None,
    policy: Policy,
    verdict: dict[str, Any],
    trace: Trace,
):
    result = apply_reconciliation(entities, resolved)
    trace.reconciled = result.reconciled

    if result.kind_pick_options is not None:
        pending = pending_ask("kind_pick", result.kind_pick_options, team=None, asked_at_turn=None)
        return result.entities, None, Plan(domains=[], fetch=[], ask=pending, denied=[], trace=trace)

    domain_override = None
    if result.reconciled and not verdict.get("domain_hint") and not verdict.get("asks"):
        _raw, _old, new_kind = result.reconciled[-1]
        for row in policy.domains:
            if new_kind in row.narrowing:
                domain_override = row.name
                break

    return result.entities, domain_override, None


# The message types that carry no business question of their own (contract 49, 51).
_CASUAL_TYPES = frozenset({"casual", "unknown", "confirmation"})
# Domains that answer a request for help rather than escalating it (contract 21, 22).
_HELP_EXEMPT_DOMAINS = frozenset({"portal_link", "ideate"})


#: Every structured signal that makes a message a QUESTION rather than idle chat. A
#: casual-typed turn carrying any one of them is still narrowing a live business ask -
#: "hanlim" (an entity), "1" (a reference position), "more" (a continuation) - and must
#: be planned, not swallowed. Listed by name, from the parser's own schema, so the rule
#: reads as what it is: nothing in the message but the greeting.
_IDLE_CHAT_DISQUALIFIERS = (
    "entities",
    "intent_hint",
    "domain_hint",
    "asks",
    "requested_attributes",
    "reference_positions",
    "reference_target",
    "document",
    "status",
    "scope_intent",
    "broaden_axis",
    "group_by",
    "top_n",
    "demand_qty",
    "date_mode",
    "date_filter_start",
    "date_filter_end",
    "person_mention",
    "correction",
    "continuation",
    "contains_flyer",
)


def _is_idle_chat(verdict: dict[str, Any], entities: list[dict[str, Any]]) -> bool:
    """A message that carries no question of its own - not even a subject.

    Every part of this is the PARSER's own structured verdict, never the words: a casual
    (or unknown / confirmation) message type and not one signal in the emission. The
    carried focus is what the CONVERSATION is about; it is not a question this message
    asked, so a greeting plans no fetch and the focus is left exactly as it was (owner
    ruling, S6 cluster 4, 16 Sep 2026 - browser pass 2 turn 9 replayed the previous
    business answer back, byte for byte, at a customer who had said "hello").
    """
    if verdict.get("message_type") not in _CASUAL_TYPES:
        return False
    if entities:
        return False
    if any(verdict.get(key) for key in _IDLE_CHAT_DISQUALIFIERS):
        return False
    # A yes, a no, or a pick ENGAGES the open question - "yes" to "shall I list the
    # DOs?" is the fetch, not idle chat. (`resolved: true` never reaches here anyway:
    # the locked-domain branch runs first.)
    if verdict.get("is_affirmative") is not None:
        return False
    if any((verdict.get("escalation") or {}).values()):
        return False
    return True


def _lane(verdict: dict[str, Any], domains: list[str], policy: Policy) -> str | None:
    """Which NON-business lane this turn belongs to, or None for a business question.

    Read off the verdict's own structured signals and the policy's `supported` flag -
    never off the message. `route()` is the only reader (AC-1528: the router takes a plan
    and nothing else), so the decision is made here, where the verdict is.
    """
    escalation = verdict.get("escalation") or {}
    message_type = verdict.get("message_type")

    if escalation.get("escalation_declined") is True:
        return "escalation_declined"
    if escalation.get("is_escalation_confirmation") is True:
        return "escalation"
    if message_type == "escalation":
        return "escalation"
    if (
        message_type == "request_for_help"
        and verdict.get("domain_hint") not in _HELP_EXEMPT_DOMAINS
        and not _help_request_is_an_ask(verdict)
    ):
        return "escalation"
    if domains and all(
        (policy.domain(name) is not None and not policy.domain(name).supported) for name in domains
    ):
        return "not_supported"
    if message_type == "clarification":
        return "clarification"
    if message_type in _CASUAL_TYPES:
        # Owner console pass 4 item E (`member_offer_filter_modification` in the old
        # ladder): a casual-typed turn that still names or carries a domain is
        # narrowing a LIVE business question, not idle chat - the customer's own
        # words were the whole reason `domains` resolved to something, and swallowing
        # it here would answer "hanlim" with small talk instead of the order it names.
        if domains:
            return None
        # Owner console defect E: `scope_intent: "broaden"` on a casual/no-domain turn
        # asks to see MORE, not less - that is a clarifying question, never idle chat.
        if verdict.get("scope_intent") == "broaden":
            return "clarification"
        return "casual"
    if message_type == "business_query" and not domains:
        return "casual"
    return None


def _did_you_mean(
    entities: list[dict[str, Any]],
    policy: Policy,
    state: State,
    trace: Trace,
    candidates: dict[str, list[dict[str, Any]]] | None = None,
):
    """An entity the parser could not place asks before anything else does (contract 26,
    111: did-you-mean before the team question).

    `confident is False` is the parser's own "I read a token here and could not pin it".
    The kind's `did_you_mean` flag (AC-1502) decides whether that kind is worth asking
    about at all; a kind that is not stays silent and simply does not narrow.

    A kind the RESOLVER already found real candidates for (the second `apply()` pass,
    `candidates` non-empty for this kind) defers to the narrower instead of asking the
    raw guess back: "wc286" is one typed word and ten real products, and a roster of the
    resolver's own matches is a better question than "did you mean wc286?" - the
    narrower's `narrow_to_code` ask is what actually lists them (contract 28).
    """
    unsure = [e for e in entities if e.get("confident") is False and e.get("hint")]
    if not unsure:
        return None
    kind = unsure[0]["hint"]
    if (candidates or {}).get(kind):
        return None
    row = policy.kind(kind)
    if row is not None and not row.did_you_mean:
        return None
    options = [
        {
            "position": i + 1,
            "label": e.get("raw"),
            "code": e.get("canonical_code") or e.get("raw"),
            "uuid": e.get("canonical_code") or e.get("raw"),
            "uuids": [e.get("canonical_code") or e.get("raw")],
            "entity_type": kind,
            "payload": {"did_you_mean": True},
        }
        for i, e in enumerate(unsure)
    ]
    trace.rules_fired.append("did_you_mean")
    return pending_ask(f"{kind}_pick", options, asked_at_turn=state.turn_no, expects="pick")


def _narrow_and_plan(
    focus: Focus,
    policy: Policy,
    domains: list[str],
    state: State,
    trace: Trace,
    attributes: tuple[str, ...] = (),
    candidates: dict[str, list[dict[str, Any]]] | None = None,
    unplaced: frozenset[str] | set[str] | None = None,
) -> Plan:
    denied: list[str] = []
    ask: Pending | None = None
    fetch: list[FetchSpec] = []

    picked = set(trace.picked_kinds)
    outcomes = []
    for name in domains:
        row = policy.domain(name)
        if row is None:
            continue
        if not row.supported:
            # The bot refuses this domain out of the box (contract 63). Nothing is
            # fetched and nothing is asked; `_lane` has already routed the turn.
            continue
        if state.profile.grants is not None:
            required = row.reveal_key or row.name
            if required not in state.profile.grants:
                denied.append(name)
                continue
        entities: list[dict[str, Any]] = []
        filters: dict[str, Any] = {}
        domain_ask_kind = None
        domain_ask_options: list[dict[str, Any]] = []
        for kind, policy_value in row.narrowing.items():
            outcome = narrow_decide(
                kind=kind,
                policy_value=policy_value,
                focus=focus,
                profile=state.profile,
                attributes=attributes,
                resolved_candidates=(candidates or {}).get(kind),
                just_picked=kind in picked,
                family_grouping=getattr(policy.kind(kind), "family_grouping", None),
                unplaced=unplaced,
            )
            trace.narrowing.append(f"{name}.{kind}:{outcome.note or policy_value}")
            if outcome.ask_kind:
                domain_ask_kind = outcome.ask_kind
                domain_ask_options = outcome.ask_options
                break
            entities.extend(outcome.entities)
            if outcome.filter_value is not None:
                filters[kind] = outcome.filter_value
            # The focus carries what the ANSWER was about, not what the customer typed
            # (contract 33 / 35, browser pass 2 turn 2). "check stock srtwc286" is one
            # raw token and ten real variants: leaving the token in the focus meant the
            # next turn ("incoming", no product) narrowed against a word nobody could
            # fetch, and asked a one-option roster naming the family root. Written HERE,
            # at the seam that decides what this fetch is about, and only from what the
            # RESOLVER matched this turn - a carry that was already settled is already
            # in the focus.
            if outcome.entities and (candidates or {}).get(kind) and kind not in picked:
                _set_kind_field(focus, kind, list(outcome.entities))
                trace.rules_fired.append(f"focus_settles_{kind}")
        # Attribute-first (AC-1534): a HAS turn ("which taps have certificates") names
        # its scope with a `product_type`/`category` entity, not a `product` one - the
        # resolver's own class-word match is what carries the real product candidates
        # (`turn_runtime.candidates_by_kind`'s "product" bucket), and a domain whose
        # `narrowing` map has no "product" key (most domains never narrow on it) would
        # otherwise leave the fetch with NO entities at all, which falls through to
        # every compatible entity the resolver matched for ANY token this turn -
        # including ones the class word coincidentally also hit (contract 114). Only
        # fires when nothing already claimed "product" and this domain did not ask.
        if (
            attributes
            and domain_ask_kind is None
            and "product" not in row.narrowing
            and not entities
        ):
            product_candidates = (candidates or {}).get("product")
            if product_candidates:
                entities.extend(product_candidates)
        outcomes.append((name, domain_ask_kind, domain_ask_options, entities, filters))

    asking = next((o for o in outcomes if o[1]), None)
    if asking:
        name, ask_kind, ask_options, _entities, _filters = asking
        team = policy.domain(name).escalation_team_code if policy.domain(name) else None
        if ask_kind == "tier_pick" and not ask_options:
            # The tier menu is the policy's own order (AC-1502), not a hand-built list:
            # the narrower knows a tier is missing, the policy knows which tiers exist.
            ask_options = [
                {
                    "position": i + 1,
                    "label": tier.replace("_", " "),
                    "code": tier,
                    "uuid": tier,
                    "uuids": [tier],
                    "entity_type": "tier",
                    "payload": {"tier": tier},
                }
                for i, tier in enumerate(policy.tier_order)
            ]
        ask = pending_ask(
            ask_kind,
            ask_options,
            team=team,
            asked_at_turn=state.turn_no,
            expects="pick",
            payload={
                # The domain this question is being asked FOR: what the answer goes back
                # to next turn (contract 121), since the answer itself is a bare number.
                "domain": name,
                # And EVERY domain the ask was asked for (owner hand pass 2, item 11).
                # "Last purchase cost and stock" is one question about two domains, and
                # the narrowing that stops it is one roster; recording only the domain
                # that happened to ask meant the pick answered that one and dropped the
                # other (turns 78f34206, cac3f42e). Contract 121 locks the turn to this
                # SET, not to one member of it.
                "domains": list(domains),
            },
        )
    else:
        for name, _ask_kind, _ask_options, entities, filters in outcomes:
            row = policy.domain(name)
            fetch.append(
                FetchSpec(
                    domain=name,
                    entities=entities,
                    filters=filters,
                    date_window=focus.date_window if row and row.takes_date_filter else None,
                )
            )

    return Plan(domains=list(domains), fetch=fetch, ask=ask, denied=denied, trace=trace)


def apply(
    state: State,
    verdict: dict[str, Any],
    policy: Policy,
    resolved: dict[str, dict[str, int]] | None = None,
    candidates: dict[str, list[dict[str, Any]]] | None = None,
    unplaced: frozenset[str] | set[str] | None = None,
):
    """`unplaced` is the resolver's own verdict about the tokens THIS message named and
    could not place (`turn_runtime.unplaced_tokens`, folded). It is read at one seam
    only: a roster is never built out of a word that matched nothing."""
    trace = Trace()

    # F3 (contract 65): a `domain_hint` outside the declared enum must never reach a
    # reader - evidence turn b5b19cec-dccc-4eda-b766-1aeb1362957b emitted "purchasing"
    # (a TEAM name, not a domain) and it survived into a tool pick. `coerce_domain_hint`
    # existed but had no call site anywhere in the rearch (AC-1592 test triage);
    # coerced ONCE here, at the verdict's one entry point into apply(), so every
    # downstream read (`_reconcile_step`, `_answer_pending`, `_focus_rules`, the
    # `domains` build below, `_lane`) sees the same coerced value
    # rather than needing its own guard.
    coerced_domain_hint = contracts.coerce_domain_hint(verdict.get("domain_hint"))
    if coerced_domain_hint != verdict.get("domain_hint"):
        trace.rules_fired.append("domain_hint_coerced")
        verdict = {**verdict, "domain_hint": coerced_domain_hint}

    # The same shape, one line down: a hallucinated escalation confirmation over a message
    # that names its own question (owner report, 8 Sep 2026). Decided here so the three
    # readers of that flag cannot disagree about one turn.
    verdict = _confirmation_defused(verdict, trace)

    # AC-1592 test triage: the old `head/output_exchange.py::_assert_emission` named
    # a malformed emission's bad KEY and expected TYPE before anything downstream ever
    # touched it; the S3 rewrite dropped it with no equivalent, so a malformed
    # `entities` (a real LLM call cannot produce one - `head/parser.py::parse` passes
    # `json_schema=PARSE_OUTPUT_JSON_SCHEMA` straight to the provider - this is a
    # harness-injected-mock hazard only) surfaced as an unnamed `AttributeError` deep
    # in a helper instead of a clear, named failure. `entities` is the one declared
    # ARRAY key this module actually reads item-by-item.
    raw_entities = verdict.get("entities")
    if raw_entities is not None and not isinstance(raw_entities, list):
        raise contracts.ParserOutputError(
            f"parser emission key 'entities' must be an array, got "
            f"{type(raw_entities).__name__}"
        )

    # ONE reading of this message, before any arm acts on it: did it answer the open
    # question, narrow the standing subject, name a new one, or none of the three
    # (`turn/decide.py`). Every arm below reads this Decision; the four that used to
    # decide for themselves disagreed at the edges, and each hand pass since the second
    # found a path one of them missed.
    decision = decide(verdict, state.focus, state.pending)
    trace.decision = decision.as_trace()

    verdict_entities = list(verdict.get("entities") or [])
    entities, domain_override, reconcile_short_circuit = _reconcile_step(
        verdict_entities, resolved, policy, verdict, trace
    )
    if reconcile_short_circuit is not None:
        return state, reconcile_short_circuit

    focus_after_pending, pending_after, pending_short_circuit, domain_locked = _answer_pending(
        state, decision, trace
    )
    if pending_short_circuit is not None:
        unchanged = replace(state, pending=pending_after)
        return unchanged, pending_short_circuit

    focus = _focus_rules(
        focus_after_pending,
        verdict,
        entities,
        decision,
        domain_locked=domain_locked,
        domain_override=domain_override,
        trace=trace,
    )

    asks = verdict.get("asks") or []
    if domain_locked and focus.domains:
        # Contract 121 / AC-1522: a pick never re-domains the turn. `_answer_pending`
        # put the domain the question was ASKED under onto the focus and `_focus_rules`
        # left it alone, and this is the second half of that: re-reading `asks` or
        # `domain_hint` here would have undone it, because a bare "3" is parsed against
        # the whole message history and its verdict still carries the PREVIOUS turn's
        # domain hint. The answer belongs to the roster it was picked off.
        domains = list(focus.domains)
        trace.rules_fired.append("domain_locked_by_pick")
    elif asks:
        domains = [a["domain"] for a in asks if a.get("domain")]
    elif verdict.get("domain_hint"):
        domains = [verdict["domain_hint"]]
    elif focus.domains and not _is_idle_chat(verdict, entities):
        domains = list(focus.domains)
    elif focus.domains:
        # S6 cluster 4 (owner ruling, 16 Sep 2026): the pending is carried unchanged and
        # the MESSAGE is planned as ITSELF. "hello" typed while an offer is open names
        # nothing, asks nothing and answers nothing, so it plans no fetch - the carried
        # focus is what the conversation is ABOUT, not what this turn asked for. Before
        # this the greeting re-fetched the carried domain and the customer got the
        # previous answer back, byte for byte (browser pass 2, turn 9). The focus itself
        # is untouched: the next real question still resumes from it.
        domains = []
        trace.rules_fired.append("idle_chat_plans_nothing")
    else:
        # D6: nothing named a domain and nothing is carried, but the focus knows what
        # DOCUMENT the conversation is about, and a document belongs to one domain.
        carried = _domain_of_document(focus.document)
        domains = [carried] if carried else []
        if carried:
            focus.domains = [carried]
            trace.rules_fired.append("domain_follows_document")

    if not domains and _help_request_is_an_ask(verdict):
        # "delivery to hanlim" (owner turns 2d903c96 / 17d38019 / 3a56a48c): the parser
        # named a subject and no domain, so the domain is the one that NARROWS that
        # subject's kind. Last in the chain deliberately - anything the parser or the
        # conversation actually said about the domain outranks a lookup from a kind.
        named = next(
            (e for e in entities if isinstance(e, dict) and e.get("current_message") is True),
            None,
        )
        by_kind = _domain_of_kind(policy, (named or {}).get("hint"))
        if by_kind:
            domains = [by_kind]
            focus.domains = [by_kind]
            trace.rules_fired.append("help_request_names_its_own_ask")

    new_state = State(focus=focus, pending=pending_after, profile=state.profile, turn_no=state.turn_no)
    trace.lane = _lane(verdict, domains, policy)

    # A did-you-mean outranks both the narrower and the lane: an entity nobody could place
    # is the first thing worth asking about (contract 26, 111) - unless this turn ANSWERED
    # the open question, which is what `domain_locked` records. The answer is about what
    # the question was about, so there is nothing new to fail to place.
    if not domain_locked:
        dym = _did_you_mean(entities, policy, new_state, trace, candidates)
        if dym is not None:
            return new_state, Plan(
                domains=list(domains), fetch=[], ask=dym, denied=[], trace=trace
            )

    # A continuation pages the set the LAST answer described: same domain, same
    # description, one page further on (AC-1317). It never re-narrows and never re-asks -
    # the customer has already answered every question this set needed.
    if _is_continuation(verdict) and focus.set_page:
        carried = focus.set_page.get("set_key") or {}
        domain = carried.get("domain")
        if domain:
            trace.rules_fired.append("set_page_continuation")
            return new_state, Plan(
                domains=[domain],
                fetch=[
                    FetchSpec(
                        domain=domain,
                        entities=[],
                        filters={"set_page": dict(focus.set_page)},
                        date_window=None,
                    )
                ],
                ask=None,
                denied=[],
                trace=trace,
            )

    attributes = tuple(
        a for a in (verdict.get("requested_attributes") or []) if isinstance(a, str) and a
    )
    plan = _narrow_and_plan(
        focus, policy, domains, new_state, trace, attributes, candidates, unplaced
    )

    if trace.outstanding is not None:
        # Contract 38/39: this fetch is the ANSWERED question's own report re-running.
        # Stamped on the spec rather than read off the focus by the runtime, because the
        # focus alone cannot tell "the customer just answered the question about this
        # product" from "this product is what the conversation happens to be about" -
        # and only the first may override the resolver's own read of a typed code (D10).
        for spec in plan.fetch:
            spec.filters["outstanding"] = dict(trace.outstanding)

    if (
        decision.kind == NEW_ASK
        and plan.fetch
        and plan.ask is None
        and new_state.pending is not None
        # The outstanding question's own arm decides its own survival (contracts 38, 39,
        # and hand pass 3's named-document rule); every other open question is this
        # rule's.
        and new_state.pending.kind not in OUTSTANDING_KINDS
        and not _roster_is_about(new_state.pending, focus)
    ):
        # A NEW ASK that got its own answer closes a roster about something else. S6
        # cluster 4's sticky carry is for a CARRY - an aside, a greeting, a message that
        # answered nothing - not for a question the bot has just finished answering.
        # Measured: a `product_pick` of "cb2805q" opened at 05:27 survived "Incoming and
        # stock CB2805A", "incoming and stock and PO", "IBWC8315 (Mocha) Stock" and "any
        # markeitng forms?", and the "1" the customer then typed under a list of twenty
        # forms answered THAT roster instead (turns e69a0b1b to 543b9a02, 17 Sep 2026).
        # The roster survives only while it is still about the subject - which is why
        # this is a test on the options, not on the domain: "incoming CB2805A" fetches
        # the very domain the stale question was asked under. An escalate OFFER is closed
        # the same way and for the same reason - driven on :8099, a bare "1" typed under
        # a list of twenty forms handed the conversation to purchasing, because the offer
        # two asks earlier was still open. The sticky-offer rule (contract 43, AC-1167)
        # is about a CARRY - "thanks", "no" - and those turns fetch nothing, so they are
        # untouched.
        new_state.pending = None
        trace.rules_fired.append("new_ask_closes_stale_roster")

    return new_state, plan


def _roster_is_about(pending: Pending, focus: Focus) -> bool:
    """Is any option this question offered still on the focus axis it is a choice of?

    The engine matches labels and codes, never message words (D1/AC-1520): an option is
    "still the subject" when the focus's own rows for that option's kind carry its code.
    """
    for option in pending.options:
        kind = option.get("entity_type")
        if not kind:
            continue
        code = str(option.get("code") or option.get("label") or "").strip().casefold()
        if not code:
            continue
        for row in _kind_field(focus, str(kind)):
            if not isinstance(row, dict):
                continue
            for name in ("canonical_code", "code", "raw"):
                if str(row.get(name) or "").strip().casefold() == code:
                    return True
    return False


def _kind_field(focus: Focus, kind: str) -> list[Any]:
    attr = KIND_FIELD_MAP.get(kind)
    if attr:
        value = getattr(focus, attr, [])
        return list(value) if isinstance(value, list) else []
    value = focus.extra.get(kind, [])
    return list(value) if isinstance(value, list) else []
