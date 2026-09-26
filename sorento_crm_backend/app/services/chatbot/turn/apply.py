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
#   6. a `set_page` continuation - returns its own Plan.
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
    domain_in_message,
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
from app.services.chatbot.turn.state import EXTRA_KIND_ALIASES, KIND_FIELD_MAP, Focus, State

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


def _named_count(verdict: dict[str, Any]) -> int | None:
    """The count this message named (`top_n`), or None."""
    return contracts.named_count(verdict.get("top_n"))


def _names_a_subject(verdict: dict[str, Any]) -> bool:
    """Did this message name an entity of its own? Then it is a new question."""
    return any(
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
        # EXTRA_KIND_ALIASES: "customer_order"/"order_number" share the "order" bucket
        # (hand pass 12, Group B) - a pick REPLACES the whole bucket, which is what
        # retires the missed raws it settles rather than leaving them beside the answer.
        focus.extra[EXTRA_KIND_ALIASES.get(kind, kind)] = entities


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


def _picks_a_member_option(pending: Pending, decision: Decision) -> bool:
    """Hand pass 12 round 3, owner ruling R3: a position pick landing on a MEMBER-typed
    option reaches the escalation-acceptance path (`_answer_offer`) even when the
    pending's own KIND is not one of `ESCALATION_OFFER_KINDS`. The combined did-you-mean
    + CS-member pending this round mints (`answer_bridge.py::_miss_question`'s owner-R2
    combine) is a `{entity_kind}_pick` - a ROSTER kind, never `member_offer` - because
    its FIRST half is a business roster, not an escalation offer; only the SECOND half,
    the options this checks, is one."""
    # Worded to close on "is one" rather than on "are" plus a full stop: this package
    # carries a source scan (the S2 apply-is-pure suite's own regex-call guard) that
    # reads that pair of characters as a regex call, and it cannot tell prose from code.
    if not decision.positions:
        return False
    return any(
        o.get("position") in decision.positions and o.get("entity_type") == "member"
        for o in pending.options
    )


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
    # AC-1700: a POSITION over a `member_offer` names that SPECIFIC member -
    # `option["uuid"]` (a real `users.id`), never `option.payload.respond_user_id`
    # (hand pass 12 Phase 3 finding P2: `escalation_context` and
    # `/external/next-assignee`'s own `get_member_assignee` both match
    # `preferred_assignee_id` against a `users.id` - `TeamMember.user_id`
    # downstream, the roster row's own `uuid` upstream - never a respond.io id).
    # A bare "yes" (no position picked, `picked` stays `None`) leaves `picked` empty
    # and assigns nothing, which is what keeps the round-robin draw for that
    # acceptance unchanged.
    trace.assignee = (picked or {}).get("uuid")
    # Hand pass 11, blocker 2: the same rule for the COMPANY a numbered pick named
    # (`option.payload.company`, the company clarify's own options). A bare "yes" picks
    # no position, so this stays `None` and the pool travels instead - which is exactly
    # what makes the clarify ask happen rather than a blind assign.
    trace.company = option_payload.get("company")
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
    if filters.get("channel"):
        # Same rule, the sales report's own axis: a fresh ask that names no channel word
        # counts every channel, and inheriting a dead report's "Dealer" would answer a
        # different question under a header nobody asked for.
        focus.sales_channel = None


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
    if filters.get("channel") and not focus.sales_channel:
        # The sales report's own axis (S4 wiring point 2), settled the same way and for
        # the same reason: the turn that answers "1" says no channel word, and a re-run
        # that dropped it would count every channel under a header saying "Dealer".
        # A DEFAULT like the window above - `_focus_rules` runs next and a channel this
        # turn named itself ("for project only") wins.
        focus.sales_channel = str(filters["channel"])


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

    The scope question clears when it is answered; a detail offer does not (contract
    39, owner ruling 13 Sep 2026 - "after '1' (SO list), typing '2' must give the DO
    list"), so those are the offer kinds that stay on screen across their own pick.

    PLAN-chatbot-sales-report.md S4 wiring point 7: `sales_report_detail` runs through
    THIS arm, not a copy of it. Two facts differ and nothing else does - the status
    word this answer re-runs under (`sales_report`, which is what
    `turn_runtime.lane_parse_output` projects onto `order_status` and what
    `lanes/business.run_fetch`'s own override reads), and the document axis, which the
    sales report has no concept of at all (one bucket, confirmed AND outstanding, S4
    ruling 6: "no scope question exists here"). The `so` its one option carries is a
    `detail` argument, never a document.
    """
    asked_for = pending.payload.get("domain")
    sales_report = pending.kind == "sales_report_detail"
    #: The status word the re-run goes out under, and therefore which tool
    #: `run_fetch`'s order-domain override picks.
    status_word = "sales_report" if sales_report else "outstanding"

    if decision.refines:
        # The subject SETTLES exactly as an answer's does - the question's own resolved
        # product, customer ids and warehouses - and `_focus_rules` runs next and lays
        # this turn's own window or location over the top. `detail: None` is what makes
        # it a re-run of the REPORT rather than one of its lists: the customer narrowed
        # the search, they did not ask for a list.
        _settle_question_subject(focus, pending, trace)
        focus.status = status_word
        # The scope question has NOT been answered, only narrowed (AC-1158), so the
        # document axis stays empty and `lane_parse_output`'s `("", "outstanding")`
        # bucket re-arms the same question over the new filters through the arm that
        # armed it - one writer for the question's text, no second re-ask path. The
        # detail offer's scope is already known (a report ran, or it could not have
        # offered its lists), so its re-run carries it and never asks a question that
        # has been answered. The sales report has no document axis at all.
        focus.document = (
            []
            if sales_report
            else (list(DOCUMENT_BY_SCOPE[decision.scope]) if decision.scope else [])
        )
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
    focus.document = [] if sales_report else list(DOCUMENT_BY_SCOPE[decision.scope])
    focus.status = status_word
    if asked_for:
        # Contract 121: the answer goes back to the domain the question was asked for.
        focus.domains = [asked_for]
    # A document the message NAMED is a new scope, not a pick off the offer: the REPORT
    # re-runs for that document and the old question goes with it (row 5). A POSITION is
    # the offer's own answer and keeps contract 39's rule, where a detail offer is the
    # one kind that survives its own pick.
    answers_the_offer = pending.kind in contracts.DETAIL_OFFER_KINDS and not named_scope
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

    if pending.kind in ESCALATION_OFFER_KINDS or _picks_a_member_option(pending, decision):
        # BEFORE the roster path: an accepted escalation offer is a handover, never a
        # fetch, whichever of the three ways it was accepted. The second disjunct (hand
        # pass 12 round 3, R3) is the combined roster's own member half: its KIND is the
        # business roster's, not `member_offer`, but a pick landing on one of its
        # member-typed options is still an escalation acceptance, not an entity pick.
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
                # Hand pass 12, Group F: `name` only when this option is ONE identity
                # (a single uuid) - the resolver's own name for the one row it matched.
                # An option covering SEVERAL uuids (a ledger family/company rollup) has
                # no name of its own for any ONE of them, and stamping the family's
                # rollup label onto every ledger is what printed "Customer: ZZT-B094"
                # for three distinct ledgers - the code twice, no ledger ever named.
                # Left absent, `turn_runtime.fill_customer_names` (DB access, which
                # this pure module may not have) fills each row's OWN name by its uuid.
                if name and len(uuids) <= 1:
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
            #
            # The ALIASED kind, not the option's raw `entity_type` - `_narrow_and_plan`'s
            # `just_picked = kind in picked` reads the policy's own kind name ("order"),
            # and a "customer_order" pick that recorded itself under the unaliased name
            # would never match it (hand pass 12, Group B).
            trace.picked_kinds.append(str(EXTRA_KIND_ALIASES.get(kind_for_focus, kind_for_focus)))

        trace.rules_fired.append("answer_pending")
        # Contract 121: a pick never re-domains the turn. The question recorded the
        # domain it was asked for, so the answer goes back to it rather than leaving
        # a bare positional with nothing to be about.
        asked_for = pending.payload.get("domains") or (
            [pending.payload["domain"]] if pending.payload.get("domain") else []
        )
        if asked_for:
            focus.domains = [d for d in asked_for if isinstance(d, str) and d]
        # AC-1704: the SAME carry `_answer_outstanding` does for its own detail
        # offers (`focus.status`, projected onto `order_status` by `turn_runtime.
        # lane_parse_output`) - a roster pick (`customer_pick`, `product_pick`)
        # answering a SALES REPORT ask needs it too, since that status reached the
        # asking turn's verdict directly and the answering turn's own verdict never
        # repeats it.
        asked_status = pending.payload.get("status")
        if isinstance(asked_status, str) and asked_status:
            focus.status = asked_status
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
        if pending.kind in ESCALATION_OFFER_KINDS:
            # The offer was answered with a decline: that IS the turn (contract 42, the
            # `escalation_declined` lane), named here off the APPLY outcome rather than
            # off `escalation.escalation_declined` alone, which the parser emits only
            # for the explicit word - measured: all 19 recorded `escalation_declined`
            # turns carry `is_affirmative: false` and a null flag. Without this the
            # cleared pending fell through to a fetch of the carried focus and the
            # customer who said "no thanks" got the order list again.
            trace.lane = "escalation_declined"
            return focus, None, Plan(domains=[], fetch=[], ask=None, denied=[], trace=trace), False
        if pending.kind in OFFER_KINDS or pending.payload.get("escalate_offered") is True:
            # AC-1703's tail: `OFFER_KINDS` (`PENDING_KINDS - ROSTER_KINDS`) also holds
            # `tier_pick`, `outstanding_scope`, `outstanding_detail` and
            # `sales_report_detail` - the module's own comment on `ESCALATION_OFFER_
            # KINDS` names these three as BUSINESS questions, never a handover, so
            # declining one is not the customer refusing an escalation - it is "never
            # mind", R22(a)'s own `offer_declined` registry copy ("Okay, noted."). A
            # ROSTER kind's (`product_pick`, ...) own attached escalate offer reaches
            # the very same copy through `escalate_offered`, since a roster kind is
            # never IN `OFFER_KINDS` at all (roster kinds stay open across a pick,
            # contract 36, and used to fall all the way through to "the generic rules
            # settle it" below with no lane composed at all - silence, not an
            # acknowledgement).
            trace.lane = "offer_declined"
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

    # What each axis held BEFORE this message wrote to it. A `broaden_to: "family"` widens
    # the CURRENT CODE's family, and the current code is the carry - not the family word
    # the message typed, which is three characters the resolver substring-matches against
    # every product that contains them ("all variants of 286" offered BRBC22286W-1-ENG
    # and CB2863-BL, 17 Sep 2026).
    carried_rows = {kind: list(_kind_field(focus, kind)) for kind in KIND_FIELD_MAP}

    # AC-1704: `_answer_pending` already settled `trace.picked_kinds` this turn, from
    # the option the customer just picked - its own uuid on the focus. The SAME
    # message's raw entities can still carry that kind (a typed code answering a
    # roster IS an entity of the roster's own kind, hint and all, per `decide()`'s
    # own label match) with no uuid attached, and applying `by_kind` unconditionally
    # threw the picked, resolved row away for a fresh, unplaced guess at the very
    # word that picked it. One rule, every kind: a kind a pick just settled is not
    # replaced again by this same turn's own entities.
    picked_kinds = set(trace.picked_kinds)
    replaced_kinds = {kind for kind in by_kind if kind not in picked_kinds}
    for kind in replaced_kinds:
        _set_kind_field(focus, kind, by_kind[kind])
    if replaced_kinds:
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
            if focus.date_window:
                # Defect 3 (owner hand pass 6, 17 Sep 2026): the window is a focus axis
                # like any other, and a NEW ASK drops every axis it did not itself name
                # - "aug 2026" then "outstanding SO for chin chun" (a fresh customer,
                # `domain_in_message`) still ran the report over August, and a later
                # stock MISS on a different product printed an "Order date:" line that
                # turn never asked for. `_focus_rules`' own tail re-sets it below when
                # THIS message names a window of its own (N2's default-not-override
                # rule, unchanged).
                focus.date_window = None
                trace.rules_fired.append("new_ask_drops_date_window")
            # Hand pass 10 (owner ruling): the SAME rule, extended to the two axes
            # that hold no subject of their own - `tier` and `extra` are never a
            # SUBJECT (contract 121's `domain_in_message` table is unchanged: it
            # governs `products`/`customers`/`document` only), so a NEW ASK drops
            # them exactly like `date_window`, whatever domain it names. Not
            # promotion-specific: `narrow.decide`'s own `kind == "tier"` branch reads
            # `focus.tier` as its own CARRY whenever this turn resolved nothing fresh
            # for that kind, so a stale tier from an earlier roster pick answered a
            # brand new "promo for X" straight at the OLD tier with no ask at all
            # (live turns 42c2da52 tier ask -> a5dc8ded "2" Dealer -> ac576e8c "3" End
            # user, sticky and correct, then 3854f23a a fresh "promo for X" answered
            # Dealer straight). `focus.extra` is the same gap for a carried
            # `attachment_type` (the photo chain's own word bleeding into a later,
            # unrelated ask). Guarded by `by_kind` like every other axis here: a kind
            # THIS message resolves (the parser's own `access_levels`, resolver-gated
            # as today) is not a carry and is never dropped by this rule.
            if "tier" not in by_kind and focus.tier:
                focus.tier = []
                trace.rules_fired.append("new_ask_drops_tier")
            for extra_kind in list(focus.extra.keys()):
                if extra_kind in by_kind:
                    continue
                if focus.extra.get(extra_kind):
                    focus.extra[extra_kind] = []
                    trace.rules_fired.append(f"new_ask_drops_{extra_kind}")
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

    _broaden(focus, verdict, decision, by_kind, carried_rows, trace)

    document = verdict.get("document")
    status = verdict.get("status")
    if document:
        focus.document = list(document)
    if status:
        focus.status = status
    # S4 wiring point 2: the channel axis, written from the parser's own field and
    # nothing else (S12 - no word table in deterministic code). Only when the message
    # named one: a sales report ask with no channel word counts every channel, and a
    # turn that narrows an open one ("for project only") names it and wins here.
    if verdict.get("sales_channel"):
        focus.sales_channel = str(verdict["sales_channel"])
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
    carried_rows: dict[str, list[Any]],
    trace: Trace,
) -> None:
    """The ONE reader of `broaden_axis` + `broaden_to` (owner ruling, 17 Sep 2026).

    The parser says WHICH axis and HOW FAR; this decides nothing and only applies it.

    * `all` on a named axis - that axis is dropped. "okay nvm for all products" and "for
      any products", both over an order question carrying SRTWC286-SH, were answered for
      SRTWC286-SH (turns 6095ce66 / d8ab659e).
    * `all` with no axis named (`broaden_axis: "all"`) - every axis is dropped and the
      DOMAIN stays: the question is the same question, widened.
    * `family` on a named axis - the variant is dropped and the family stands. It widens
      the CARRIED code, never the word this message typed: "all variants of 286" names
      "286", and three characters substring-match every product that contains them. The
      uuid is what makes a focus row a VARIANT, so removing it (keeping the code) is the
      whole change - an unsettled carry is exactly what the engine hands the resolver,
      whose prefix probe answers with the family
      (`turn_runtime.with_carried_entities`, `unsettled_only`), and the narrower settles
      it again this same turn.

    Never when this message ANSWERED the open roster: the options the pick folded in are
    already the widened set (`decide.broadens_the_roster`, contract 31 / hand pass 2 item
    10). `all` never touches an axis this message also named outright - naming it IS the
    scope.

    Never when this message names its OWN set of domains (`verdict.get("asks")`,
    D5(a), hand pass 9): "the question is the same question, widened" is what
    `broaden_axis: "all"` with no axis means for a turn CONTINUING the open ask - but
    `asks` is a DOMAIN SWITCH (contract 121's own carrier of "every domain THIS
    message asked about"), a genuinely different question the standing subject
    answers next, per `turn/decide.py`'s own four-row table ("domain_in_message:
    true, entities: no" - "a domain switch over the standing subject"). Left
    unguarded, "stock and incoming and PO" (which also carries `broaden_axis: "all"`,
    since it is asking broadly across all three) wiped the roster's own carried
    products the SAME turn it switched to them, sending every domain an unscoped
    fetch instead of the standing subject (live turn
    554cf9c4-9249-4e45-ab2a-7a154b813009).
    """
    level = broaden_level(verdict)
    if level is None or decision.answers or verdict.get("asks"):
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
        if not attr:
            continue
        if level == EVERYTHING:
            if getattr(focus, attr, None) and kind not in by_kind:
                setattr(focus, attr, [])
                trace.rules_fired.append(f"broaden_all_clears_{kind}")
        elif level == FAMILY:
            rows = carried_rows.get(kind) or []
            widened = [
                {k: v for k, v in row.items() if k != "uuid"}
                for row in rows
                if isinstance(row, dict)
            ]
            if widened:
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
#: The ideation domain's own name - the same literal `route._domain_branch` and
#: `_HELP_EXEMPT_DOMAINS` already key on.
IDEATE_DOMAIN = "ideate"
# Domains that answer a request for help rather than escalating it (contract 21, 22).
_HELP_EXEMPT_DOMAINS = frozenset({"portal_link", IDEATE_DOMAIN})

#: The two lanes an OPEN IDEA DRAFT absorbs (issue #1178). `clarification` is contract
#: 50's domain menu, which `route.py` reserves for "a turn with no domain at all", and
#: `casual` is where `_is_idle_chat` sends a domainless "confirm" after emptying the
#: carried domains - both answered a customer mid-draft with something unrelated to the
#: idea (review of 24 Sep 2026, findings 2 and 3). Every other lane keeps its turn: an
#: escalation or a request for a human is still a handover, `not_supported` and the
#: business lanes only arise when the message named another domain.
_DRAFT_ABSORBS: frozenset[str] = frozenset({"clarification", "casual"})

#: Within the "casual" lane, the message types issue #1178 actually names (S1,
#: reviewer pass 1 on PR #1185): a bare "confirm" is `message_type: confirmation`, but
#: `_lane` sends `casual` and `unknown` typed turns to the very same lane, and those are
#: idle chat proper. The open draft pointer has no expiry - the intake keeps it on
#: `collecting`/`review` until `complete`/`duplicate` - so a contact who abandoned a
#: draft and later says "hi" or "thanks" must not have it resurrected and re-served
#: "Still need: ...". Kept separate from `_DRAFT_ABSORBS` (which still has to tell
#: `route()` a domain-menu turn from an idle-chat one for every OTHER lane) rather than
#: folded into it.
_DRAFT_MESSAGE_TYPES: frozenset[str] = frozenset({"clarification", "confirmation"})

#: Of `_IDLE_CHAT_DISQUALIFIERS`, the keys that can name the IDEA ITSELF rather than
#: another subject, so `_continues_open_draft` reads them on their own terms (the ideate
#: domain and its own intents pass) instead of as evidence the message is about
#: something else. `reference_positions` is deliberately NOT exempted (S3, reviewer
#: pass 1): the plan's own wording is "none of the subject signals
#: `_IDLE_CHAT_DISQUALIFIERS` already lists", with no carve-out, and an answer to an
#: actually open roster is already caught earlier by the `decision.answers` guard - a
#: stray position with no roster open is exactly the kind of thing the message named
#: for itself.
_DRAFT_OWN_KEYS: frozenset[str] = frozenset({"entities", "intent_hint", "domain_hint", "asks"})


def open_ideation_draft(ideation: Any) -> bool:
    """Is an idea draft open on this contact's session?

    The five-key `ideation` pointer with a `draft_id` on it. The intake tool is the
    pointer's only writer and pops it the moment a draft closes (`complete`,
    `duplicate` - `ideation_turn_service._TERMINAL_STATUSES`), so its presence IS the
    open draft; nothing here reads a status word.
    """
    return isinstance(ideation, dict) and bool(ideation.get("draft_id"))


def _continues_open_draft(
    ideation: Any,
    verdict: dict[str, Any],
    decision: Decision,
    focus: Focus,
    lane: str | None,
    policy: Policy,
) -> bool:
    """Issue #1178: does THIS turn belong to the idea draft the intake is still
    collecting?

    Yes when a draft is open, the verdict placed the turn on a lane the draft absorbs
    (`_DRAFT_ABSORBS`) via a message type the ruling actually names
    (`_DRAFT_MESSAGE_TYPES` - a question or a bare confirm, S1), the message names
    nothing of its own, and the standing subject is still the idea (or nothing). "Names
    nothing of its own" is the same structured reading `_is_idle_chat` makes - none of
    the parser's subject signals - with the ideate domain and its own intents allowed
    through, because those name the draft, not a rival subject. A decisive term from
    another domain (the prompt's own "asking stock/ETA/price mid-idea switches domain
    normally"), a current-message entity, an answer to an open roster, or a focus that
    has already moved to another domain all keep today's routing: the draft resumes by
    a fresh ideate turn, as the prompt says it does.

    Every input is the parser's structured verdict or persisted state (D1/AC-1520): no
    word of the message is read, and the parser's own domain is never overruled - the
    head is supplying the one fact the verdict could not carry, that a draft is open.
    """
    if lane not in _DRAFT_ABSORBS or not open_ideation_draft(ideation):
        return False
    if verdict.get("message_type") not in _DRAFT_MESSAGE_TYPES:
        return False
    if decision.answers:
        return False
    if any(d != IDEATE_DOMAIN for d in focus.domains):
        return False
    if any(
        isinstance(e, dict) and e.get("current_message") is True
        for e in (verdict.get("entities") or [])
    ):
        return False
    if any(verdict.get(key) for key in _IDLE_CHAT_DISQUALIFIERS if key not in _DRAFT_OWN_KEYS):
        return False
    if domain_in_message(verdict) is True:
        return False
    if any(
        isinstance(a, dict) and a.get("domain") != IDEATE_DOMAIN
        for a in (verdict.get("asks") or [])
    ):
        return False
    domain_hint = verdict.get("domain_hint")
    if domain_hint == IDEATE_DOMAIN:
        # The parser named the draft's own domain (the prompt's IDEATION CONTINUATION
        # rule); whatever intent rides beside it is that domain's.
        return True
    if domain_hint is not None:
        return False
    # No domain named: an intent of another domain's is a subject of its own, the
    # ideate row's own intents (`chatbot_domains.intents`) and no intent at all are not.
    row = policy.domain(IDEATE_DOMAIN)
    own_intents = set(row.intents) if row is not None else set()
    intent = verdict.get("intent_hint")
    return intent is None or intent in own_intents


#: Every structured signal that makes a message a QUESTION rather than idle chat. A
#: casual-typed turn carrying any one of them is still narrowing a live business ask -
#: "hanlim" (an entity), "1" (a reference position), "more" (a continuation) - and must
#: be planned, not swallowed. Listed by name, from the parser's own schema, so the rule
#: reads as what it is: nothing in the message but the greeting.
#:
#: `scope_intent` is deliberately absent (AC-1704 class, a casual-turn-over-an-open-
#: offer defect): it is a QUALIFIER of whatever a message is about ("specific" vs
#: "broaden"), never evidence a question exists - a bare "thanks" over an open
#: `sales_report_detail`/`outstanding_detail` offer still reads `scope_intent:
#: "specific"` off the parser's own common default, disqualifying idle chat for
#: literally nothing said and re-fetching the carried subject instead of leaving the
#: offer alone. Its one real reader (`_lane`'s own `scope_intent == "broaden"` ->
#: `"clarification"`) does not depend on this list at all, and the one value worth
#: disqualifying on (`"broaden"`) is already covered by `broaden_axis` below.
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
    "sales_channel",
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


def _is_idle_chat(
    verdict: dict[str, Any], entities: list[dict[str, Any]], decision: Decision
) -> bool:
    """A message that carries no question of its own - not even a subject.

    Every part of this is the PARSER's own structured verdict, never the words: a casual
    (or unknown / confirmation) message type and not one signal in the emission. The
    carried focus is what the CONVERSATION is about; it is not a question this message
    asked, so a greeting plans no fetch and the focus is left exactly as it was (owner
    ruling, S6 cluster 4, 16 Sep 2026 - browser pass 2 turn 9 replayed the previous
    business answer back, byte for byte, at a customer who had said "hello").

    Defect 5 (owner hand pass 6, 17 Sep 2026) is this rule's own extension, per the
    ruling's own words: "idle chat never fetches; extend it to the offer-open case."
    Whether this casual message ENGAGES the open question is exactly what `decide()`
    already computed (`decision.answers`) - read here instead of the two proxies this
    used to test for itself (`is_affirmative is not None`, any escalation value
    truthy), which can say "engaged" for a message `_answer_pending` itself already
    filed as `answer_pending_not_an_answer`. "good" over an open offer read that way
    and re-ran the very report the offer followed, byte for byte.
    """
    if verdict.get("message_type") not in _CASUAL_TYPES:
        return False
    if entities:
        return False
    if any(verdict.get(key) for key in _IDLE_CHAT_DISQUALIFIERS):
        return False
    if decision.answers:
        return False
    return True


def _names_an_unresolved_product(verdict: dict[str, Any]) -> bool:
    """Does THIS message type a product code the PARSER ITSELF is not confident about
    (contract 111, #866 port, hand pass 9 owner ruling)?

    `confident` is the parser's own per-entity field (`tests/chatbot/_turn_helpers.py::
    entity`'s default is `True` - a well-formed emission states it either way), read
    as-is (D1/AC-1520: the engine never re-derives a confidence score of its own from
    the word). A RESOLVED product ("SRTWC287", `confident: True`) is not this case -
    `test_brand_of_resolved_product_in_add_comment_body` still escalates straight
    through with the resolved product's own brand in the add_comment.
    """
    return any(
        isinstance(e, dict)
        and e.get("current_message") is True
        and e.get("hint") == "product"
        and e.get("confident") is False
        for e in (verdict.get("entities") or [])
    )


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
        # Contract 111 (#866 port, hand pass 9 owner ruling): a product token the
        # parser itself is not confident about must be settled BEFORE any team
        # question - `out_of_scope` only when the message names no product token at
        # all (or one the parser IS confident about, which still escalates straight
        # through with the resolved product's own brand, `test_brand_of_resolved_
        # product_in_add_comment_body`). `clarification` is the SAME lane (and the
        # SAME `clarify_menu` branch_kind) a casual-typed `scope_intent: "broaden"`
        # turn already reaches below - no new mechanism: this message type reaches
        # it for the same reason, what the turn is even about is unsettled, so the
        # generic clarifying question ("are you asking about Product, Stock,
        # ...?") runs before any lane-specific one does, rather than handing an
        # unrecognised code straight to a human. Only when NO domain is named
        # either (`not domains`) - a message that ALSO names its own domain still
        # reaches the ordinary business path below, where the resolver's own
        # did-you-mean (`miss_suggest.build_suggest_offer`'s D1 arm,
        # `ENTITY_MISS_SUGGEST_FLOOR` 0.30) is the one that runs.
        if not domains and _names_an_unresolved_product(verdict):
            return "clarification"
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
        # S3 (PLAN-chatbot-media-into-turn.md, general fix, Q1): bare entities this
        # message itself named - typed codes or a photo's raws, no domain word and
        # no carried focus to route them under - are a business question the
        # resolver can still answer ("what would you like me to do with it?"),
        # never idle chat. `casual` reaches the LLM clarifier, which cannot place
        # a product code at all; `entities_only` resolves the tokens directly.
        #
        # Review round B1(b): gated to a PRODUCT entity (or a no-hint token shaped
        # like one) - a customer/order/brand-only message (e.g. "Hanlim" alone) is
        # not a bare product ask and falls through to `casual` exactly as before;
        # the parser names nobody's kind wrong often enough that a bare customer
        # name here would otherwise misroute to a lane that can only resolve
        # products.
        current_message_entities = [
            e for e in (verdict.get("entities") or []) if isinstance(e, dict) and e.get("current_message") is True
        ]
        if any(is_product_shaped_entity(e) for e in current_message_entities):
            return "entities_only"
        return "casual"
    return None


def is_product_shaped_entity(entity: dict[str, Any]) -> bool:
    """A current-message entity this arm should resolve: `hint == "product"`, or no
    hint at all but a raw token SHAPED like a product code - letters and digits both
    (`"MBF-9902-ZZT"`), never a bare word (`"Hanlim"`) a no-hint parser output might
    otherwise carry."""
    if entity.get("hint") == "product":
        return True
    if entity.get("hint"):
        return False
    # No `re` (PLAN's own "apply is pure" rule - `test_turn_package_never_calls_re_
    # dot_or_reads_dot_text` greps for it): plain character-class checks instead.
    raw = str(entity.get("raw") or "")
    return any(c.isdigit() for c in raw) and any(c.isalpha() for c in raw)


# D5(b), hand pass 9: main's own `lanes/business/gate.py` `ALLOWS_EMPTY` (86-95) - a
# domain named False there refuses a fetch that would otherwise run with NO entity and
# NO filter at all, rather than answering broad and unscoped. `inventory` is the one
# row main's own zero-entity refusal (`run_gate`, 350-363: "no entities and 'inventory'
# requires a scoping entity") disagrees with this engine's `list_all` narrowing policy
# value on - a subject-less "stock and incoming and PO" ran every domain broad,
# printing 50 unrelated stock rows (live turn 554cf9c4-9249-4e45-ab2a-7a154b813009).
# Only this one row is ported, not main's whole dict: `master_products`/
# `product_attachment`/`order` all narrow on a `must_narrow_one`/`narrow_to_code`
# policy that already asks before falling through to an empty fetch, so nothing else
# is reachable with zero entities in practice today - a second domain earns its own
# entry when a live turn proves the same gap, not before.
_REFUSES_EMPTY_SUBJECT: frozenset[str] = frozenset({"inventory"})


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
                # AC-1710 / reviewer S4: the roster this kind is allowed to print is
                # `chatbot_entity_kinds.roster_cap`, the SAME column `gate.py`'s own
                # rosters already read through `roster_caps` - never `narrow.py`'s
                # module literal.
                roster_cap=getattr(policy.kind(kind), "roster_cap", None),
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
            date_window = focus.date_window if row and row.takes_date_filter else None
            if (
                len(domains) > 1
                and not entities
                and not filters
                and not date_window
                and name in _REFUSES_EMPTY_SUBJECT
            ):
                # D5(b): no entity, no filter, no date window - nothing to scope this
                # domain's fetch by at all, on a MULTI-domain ask ("stock and
                # incoming and PO", D5(b)'s own scenario - main's own `ALLOWS_EMPTY`
                # is read at exactly this fan-out seam, `gate.py`'s own per-domain
                # loop over an asks-shaped verdict). Refused outright rather than run
                # broad (`_REFUSES_EMPTY_SUBJECT`'s own docstring); the OTHER domains
                # this turn asked about (D5(b)'s own incoming/PO, allowed broad by
                # main's design) still fetch normally.
                #
                # `len(domains) > 1` deliberately excludes a SINGLE-domain inventory
                # ask with nothing to scope by (a "low stock report" with no
                # location/product named) - that shape already has its own
                # scope-needed miss arm downstream (`answer.not_found_error_message`'s
                # `needs_scope` branch, a team_pick offer, not a refusal here) and
                # regressed `test_turn_replay.py`'s `handbuilt-lsr-*` corpus when this
                # guard did not have it (measured: `branch_kind` fell to `low_signal`
                # with no fetch AND no ask raised at all).
                trace.rules_fired.append("refused_empty_subject")
                continue
            fetch.append(
                FetchSpec(
                    domain=name,
                    entities=entities,
                    filters=filters,
                    date_window=date_window,
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

    if state.pending is not None and _fully_answered_roster(state.pending):
        # Defect 2 (owner hand pass 6, 17 Sep 2026): a roster every option of which is
        # ALREADY answered, from an earlier turn, is a question the bot has finished
        # asking - contract 36's sticky roster is for a PICK STILL IN PROGRESS, not one
        # spent to the last option. Left open it answered a LATER, unrelated turn
        # instead of the one that named it: "hmm ok, any purchase cost" over a
        # ten-variant roster fully answered by "all" two turns earlier matched
        # `broaden_axis: "all"` again and re-ran the roster's own domains, purchase
        # cost never running; an escalate offer patched onto that same stale roster
        # (`compose._lane_question`) carried its long-superseded team rather than the
        # one THIS turn's own miss named. Closed on entry rather than only after its
        # own answering turn, so both readers - the next turn's `decide()` and
        # `compose.py`'s offer-patching - see no pending at all, the same as contract
        # 36's own "closed once the answering turn's fetch ran" wording allows.
        state = replace(state, pending=None)
        trace.rules_fired.append("stale_roster_closed")

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
    if domain_locked and focus.domains and not asks:
        # Contract 121 / AC-1522: a pick never re-domains the turn. `_answer_pending`
        # put the domain the question was ASKED under onto the focus and `_focus_rules`
        # left it alone, and this is the second half of that: re-reading `asks` or
        # `domain_hint` here would have undone it, because a bare "3" is parsed against
        # the whole message history and its verdict still carries the PREVIOUS turn's
        # domain hint. The answer belongs to the roster it was picked off.
        #
        # Defect 1 (owner hand pass 6, 17 Sep 2026): that is only true when this
        # message says nothing of its own. "stock, incoming and PO for all of them"
        # and "ok how about stock and PO only" both answered a roster AND named their
        # own domains in the same breath (`asks` non-empty on the SAME verdict), and
        # the lock rendered the roster's old domain set instead - two of three the
        # first time, three again (re-adding incoming) the second. `asks` is what THIS
        # message actually asked for; the lock exists to stop a message that asked for
        # nothing being read against stale history, not to overrule one that did ask.
        domains = list(focus.domains)
        trace.rules_fired.append("domain_locked_by_pick")
    elif asks:
        domains = [a["domain"] for a in asks if a.get("domain")]
    elif verdict.get("domain_hint"):
        domains = [verdict["domain_hint"]]
    elif focus.domains and not _is_idle_chat(verdict, entities, decision):
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

    new_state = State(
        focus=focus,
        pending=pending_after,
        profile=state.profile,
        turn_no=state.turn_no,
        ideation=state.ideation,
    )
    trace.lane = _lane(verdict, domains, policy)

    if _continues_open_draft(state.ideation, verdict, decision, focus, trace.lane, policy):
        # Issue #1178: a question about the intake's own question ("what do you mean
        # impact?") and the bare "confirm" its template asks for were leaving the
        # ideate lane - the first for the domain menu (`_lane` reads the message type
        # before the domain, so even a verdict carrying `domain_hint: ideate` landed on
        # `clarify_menu`), the second for the casual lane (`_is_idle_chat` emptied the
        # carried domain). The open draft is a question the ideate lane is still asking,
        # so the turn is planned as that lane's, and `route()` reaches `ideate` the way
        # it already does for a verdict that named the domain. The focus says so too, so
        # the next parse still reads "Current subject: domain ideate".
        domains = [IDEATE_DOMAIN]
        focus.domains = [IDEATE_DOMAIN]
        trace.lane = None
        trace.rules_fired.append("open_idea_draft_keeps_lane")

    # A did-you-mean is PRODUCTION's now (AC-1693, reviewer B1): `_did_you_mean` used to
    # run here, ahead of the narrower and the lane, and mint a `{kind}_pick` whose only
    # option was the customer's own unplaced WORD - one option, echoed back, and since
    # `engine.py` guards the bridge's miss arm on `plan.ask is None`, setting an ask here
    # was also what stopped the real answer from ever being composed. A token nobody
    # could place is a MISS, and production's own miss chain
    # (`answer.not_found_error_message` -> `miss_suggest.run_miss_lane`) is what says so,
    # with the did-you-mean roster built from the RESOLVER's own trigram neighbours
    # rather than from the guess itself. Measured red in 11 of the 13 supported domains
    # before the deletion; the other two (promotion, ideate) never reached it.

    # No paging (owner ruling, 26 Sep 2026). The one carried set is the one the LAST answer
    # was too long to list, and the one message that reads it is the answer to its own
    # question, "how many should I show?": a count (the parser's `top_n`) naming no new
    # subject lists that many of the same set. It never re-narrows and never re-asks.
    # Anything else - a "more", a new question - closes it; the engine re-arms it only
    # when a fresh answer is too long again.
    named_count = _named_count(verdict)
    carried_set = dict(focus.set_page) if isinstance(focus.set_page, dict) else None
    new_state.focus.set_page = None
    # Round 4 R5: a clarify is answered on the very next turn or not at all; the engine
    # re-arms it only when this turn asks another one.
    new_state.focus.set_clarify = None
    # W4 (owner hand test round 2): a set already LISTED in part (`shown` > 0) is carried
    # too, and continues only on the customer's own "another N"
    # (`turn_runtime.with_set_count_from_text` flags it); the bot never offers it.
    if carried_set and int((carried_set.get("set_key") or {}).get("shown") or 0) > 0:
        if not verdict.get("set_continue"):
            carried_set = None
    if carried_set and named_count and not _names_a_subject(verdict):
        domain = (carried_set.get("set_key") or {}).get("domain")
        if domain:
            trace.rules_fired.append("set_count_answered")
            return new_state, Plan(
                domains=[domain],
                fetch=[
                    FetchSpec(
                        domain=domain,
                        entities=[],
                        filters={"set_page": carried_set, "top_n": named_count},
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
        (decision.kind == NEW_ASK or domain_in_message(verdict) is True)
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
        # untouched. A DOMAIN SWITCH counts here even though the table reads it as a carry
        # of the subject: "any markeitng forms?" names no entity, so it is the table's row
        # 2, and the "1" under its list still escalated until this clause was added.
        new_state.pending = None
        trace.rules_fired.append("new_ask_closes_stale_roster")

    return new_state, plan


def _fully_answered_roster(pending: Pending) -> bool:
    """Every position this roster ever offered is already in `answered_positions` -
    defect 2's own test, read at `apply()`'s entry (`turn/pending.py::is_roster`,
    `with_answered_positions`).

    Only a ROSTER kind stays alive after its own pick at all (contract 36); an OFFER
    kind clears the same turn it is answered and never reaches here carrying anything
    to check.
    """
    if not is_roster(pending.kind):
        return False
    positions = {o.get("position") for o in pending.options if o.get("position") is not None}
    return bool(positions) and positions <= set(pending.answered_positions)


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
    # P5 (hand pass 12 Phase 3): the SAME fold `_set_kind_field` applies on the write
    # side - "customer_order"/"order_number" share the "order" bucket - or a
    # `customer_order_pick`'s own entities, written to `focus.extra["order"]`, read
    # back as an always-empty `focus.extra["customer_order"]`.
    value = focus.extra.get(EXTRA_KIND_ALIASES.get(kind, kind), [])
    return list(value) if isinstance(value, list) else []
