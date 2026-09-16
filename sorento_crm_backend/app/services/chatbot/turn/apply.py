# apply(): the pure core (PLAN-chatbot-turn-rearch.md "APPLY contract", AC-1520). One
# function; the order below is the order it runs, and the order IS the contract:
#
#   1. `_reconcile_step`  - an entity the resolver placed under one kind is rewritten to
#                           it; two kinds arm a `kind_pick` and nothing else runs.
#   2. `_answer_pending`  - the open question, resolved, re-printed or carried.
#   3. `_exclusive`       - `scope_exclusive`, traced.
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


#: Kinds that scope the SAME THING under one domain, so naming one REPLACES the others
#: (hand pass 2 item 5, owner ruling 17 Sep 2026). The retired head carried this as
#: `output_exchange.AXIS_BY_DOMAIN`; only the row with evidence today is rebuilt, and the
#: evidence is turn c45e2929 - "Outstsnding DO for 7445" ran the report for HANLIM
#: [A/C III], a customer named six turns earlier, because product and customer sit in
#: different focus slots and the product named this turn replaced neither.
#:
#: Under an ORDER question there is one axis and it is WHICH ORDER: a product code, a
#: customer, a transporter and an order number all say which orders are meant, so the one
#: the customer just typed is the scope and the rest are last question's.
#:
#: A literal rather than a `chatbot_domains` column: one domain has this today, and the
#: trigger for promoting it is a SECOND domain whose kinds collapse differently (the old
#: table had `promotion` and `master_products` rows too, both of which the narrowing
#: policy now covers). Every other domain keeps one slot per kind, which is what
#: `KIND_FIELD_MAP` already gives it.
SHARED_AXIS_BY_DOMAIN: dict[str, frozenset[str]] = {
    "order": frozenset(
        {"product", "customer", "transporter", "order", "order_number", "customer_order"}
    ),
}


def _is_continuation(verdict: dict[str, Any]) -> bool:
    """AC-1317: "show me the next page of the set you just counted". The parser's own
    `continuation` schema key (bool), read as-is - matching free-text `user_goal`
    against a word list was still a text rule wearing the parser's clothes; a
    dedicated boolean is the deterministic signal (captain ruling, 16 Sep 2026)."""
    return verdict.get("continuation") is True


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


def _answer_offer(pending: Pending, verdict: dict[str, Any], focus: Focus, trace: Trace):
    """An escalation offer, ACCEPTED - the mirror of `answer_pending_decline`.

    "Would you like me to escalate?" is answered three ways and every one of them is an
    acceptance: a bare "yes" (`is_affirmative`), the parser's own escalation flag, and a
    NUMBER off a multi-team roster (`answers_open_question.resolved` with a pick). The
    third is why this runs before the roster path below: an accepted offer's option is a
    TEAM, not an entity to fetch with, and the roster path turned "yes" into a product
    pick, restored `payload.domain` and re-ran the very lookup that had just missed
    (browser pass 3, turns 9 and 12 - the same answer back, byte for byte, re-offering
    the same escalation).

    The turn short-circuits to the escalation lane with the accepted team on the trace;
    the lane then does its normal work (the assignee draw, the SLA row). Returns the
    four-tuple, or None when this message is not an acceptance - a decline, a miss and an
    aside are all settled by the generic rules below, in one place.
    """
    escalation = verdict.get("escalation") or {}
    if escalation.get("escalation_declined") is True or verdict.get("is_affirmative") is False:
        # A decline outranks every acceptance signal, and it already has a rule.
        return None

    answers = verdict.get("answers_open_question") or {}
    picked: dict[str, Any] | None = None
    positions = _picked_positions(pending, verdict)
    if answers.get("resolved") is True or positions:
        # ONE option, and only a POSITION. "all" (contract 31) expands a menu of things
        # to look up, and there is no such thing as handing one conversation to every
        # team at once - so it is not an acceptance and the menu rules below keep it.
        if answers.get("picks") == "all" or verdict.get("broaden_axis") == "all":
            return None
        picked = next((o for o in pending.options if o.get("position") in (positions or [])), None)
        if picked is None:
            # A position nobody offered: the re-print rule below owns it, the same as
            # for a roster.
            return None
    elif not (
        verdict.get("is_affirmative") is True
        or escalation.get("is_escalation_confirmation") is True
    ):
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


#: Contract 38 and 39: the outstanding report's own two questions. Business questions,
#: not escalation offers - answering one is a fetch (see `ESCALATION_OFFER_KINDS`).
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


def _picked_positions(pending: Pending, verdict: dict[str, Any]) -> list[int] | None:
    """Which of the open question's positions this message picked, or None for "it did
    not pick".

    `answers_open_question` is the parser's verdict on its own question and it wins
    (owner ruling, S6 cluster 4): true = these picks, false = it tried and missed.
    `resolved` null is the parser saying nothing about the question - and the SAME
    prompt also says a position "still goes to reference_positions as well", which is
    the only signal an emission from an older prompt version (or a recorded verdict
    replayed from one) carries at all. Read as the fallback it is, never as a second
    opinion: a parser that HAS judged its own question is never second-guessed.
    """
    answers = verdict.get("answers_open_question") or {}
    resolved = answers.get("resolved")
    if resolved is True:
        picks = answers.get("picks")
        if picks == "all":
            return [o["position"] for o in pending.options]
        return [p for p in picks if isinstance(p, int)] if isinstance(picks, list) else []
    if resolved is False:
        return []
    if pending.kind in ESCALATION_OFFER_KINDS:
        # A handover is the most expensive thing the bot can do with a message, so it
        # takes the parser's EXPLICIT verdict and nothing weaker. Measured on the
        # recorded corpus (`console/handpass3-justin-escalation-offer.json` step 4): a
        # bare "1" typed over an open escalate offer, with the parser saying nothing
        # about the question, re-ran the order list and left the offer open - reading
        # the position as an acceptance instead assigned a human to a conversation
        # nobody had asked to escalate. The fallback below exists for READS.
        return None
    raw = verdict.get("reference_positions")
    positions = (
        [int(p) for p in raw if isinstance(p, (int, float)) and not isinstance(p, bool)]
        if isinstance(raw, list)
        else []
    )
    if positions:
        return positions
    if verdict.get("broaden_axis") == "all" and pending.options:
        # Contract 31, R21: "all" over a numbered menu is a pick of EVERY option, not a
        # widening of the search - the parser reads the word as a broaden (`entity_op:
        # "clear"`, `broaden_axis: "all"`) because that is what it means anywhere else,
        # and over an open roster it means the opposite. Read off the parser's own field
        # rather than the word; live, "all" over a three-family customer picker ran the
        # plain order list with no status and no dates, where "1" answered correctly.
        return [o["position"] for o in pending.options]
    return None


def _drop_question_subject(focus: Focus, pending: Pending) -> None:
    """R17: the offer dies, and its filters die with it.

    The scope question and the detail offer are asked about a SUBJECT the lane resolved
    for them (`pending.payload.filters`), and a turn that walks away with its own
    question must not inherit it - "sales order outstanding for SRTWC8517" typed under a
    question about another product kept the old customer and the old location and
    answered about the wrong thing (reviewer N2). Only the axes THAT QUESTION named are
    cleared; `_focus_rules` runs next and re-fills whatever this message named itself.
    """
    filters = pending.payload.get("filters")
    if not isinstance(filters, dict):
        return
    if filters.get("product_code"):
        focus.products = []
    if filters.get("customer_ids"):
        focus.customers = []
    if filters.get("warehouse_codes") or filters.get("location_token"):
        focus.warehouse = []
    if filters.get("date_filter_start") or filters.get("date_filter_end"):
        focus.date_window = None


def _settle_question_subject(focus: Focus, pending: Pending) -> None:
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
    code = filters.get("product_code")
    if code:
        focus.products = [
            {"raw": code, "hint": "product", "canonical_code": code, "current_message": False}
        ]
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


def _answer_outstanding(state: State, pending: Pending, verdict: dict[str, Any], focus: Focus, trace: Trace):
    """Contracts 38 and 39: the outstanding report's scope question and detail offer,
    answered.

    The retired `head/output_exchange._apply_outstanding_pending` did this by rewriting
    the parser's emission; here the answer moves the FOCUS instead, which is the only
    place the next fetch reads its subject from. Three outcomes and nothing else:

    * a message that NAMES something of its own is a NEW ASK. The question is dropped
      rather than mis-resolved, so a customer can leave it by asking something else
      instead of only by answering it (D17 point 3: a stray position riding along with
      an entity is still a new ask, because the parser is told never to emit both).
    * an ANSWER (a picked option, or the scope named in words on `document`) writes
      `focus.document` - which is what `turn_runtime.lane_parse_output` projects back
      onto the order tools' one `order_status` bucket, so the SAME turn re-runs the
      report for the scope just named and the question cannot re-arm itself
      (`outstanding_scope_ask_candidate` reads that bucket).
    * anything else leaves the question open, untouched.

    The scope question clears when it is answered; the detail offer does not (contract
    39, owner ruling 13 Sep 2026 - "after '1' (SO list), typing '2' must give the DO
    list"), so it is the one offer kind that stays on screen across its own pick.
    """
    entities = [e for e in (verdict.get("entities") or []) if e]
    asked_for = pending.payload.get("domain")
    if entities:
        # A turn that NAMES something is a new ask, and D17 point 3's defensive guard is
        # this line: a stray position riding along with an entity ("2" + "delivery to
        # hanlim") is still a new ask, because the parser is told never to emit both.
        # A message that merely names another DOMAIN and nothing else is NOT dropped
        # here - the owner's S6 cluster 4 ruling keeps the question open across an
        # aside, and it is the entity that makes this one a different subject.
        trace.rules_fired.append("outstanding_pending_dropped")
        _drop_question_subject(focus, pending)
        return focus, None, None, False

    positions = _picked_positions(pending, verdict)
    matched = (
        [o for o in pending.options if o.get("position") in positions] if positions else []
    )
    values = [(o.get("payload") or {}).get("value") for o in matched]
    # "all" over the scope question picks every option, and every option at once IS the
    # widest one - answering "both" rather than the first row on the list.
    scope = "both" if "both" in values else next((v for v in values if v), None)
    if scope not in DOCUMENT_BY_SCOPE:
        scope = None
    if scope is None and pending.kind == "outstanding_scope":
        # The same question, answered in words. The parser emits a named document on its
        # own `document` slot ("sales order outstanding" and a bare "sales orders" are
        # the same emission), so there is no second vocabulary to teach it.
        named = tuple(sorted(str(d).strip().upper() for d in (verdict.get("document") or [])))
        scope = SCOPE_BY_DOCUMENT.get(named)

    if scope is None:
        # Not an answer to this question. Every other reading of the turn - the generic
        # re-print of an out-of-range position, the aside that carries the question
        # forward unrepeated (owner ruling, S6 cluster 4) - is the same rule for every
        # pending kind and is settled below, in one place.
        return None

    _settle_question_subject(focus, pending)
    focus.document = list(DOCUMENT_BY_SCOPE[scope])
    focus.status = "outstanding"
    if asked_for:
        # Contract 121: the answer goes back to the domain the question was asked for.
        focus.domains = [asked_for]
    trace.rules_fired.append("answer_outstanding")
    trace.outstanding = {
        "kind": pending.kind,
        "scope": scope,
        # Contract 39: "1" asks for one of the report's LISTS, which is the same tool
        # call with a `detail` argument. The scope question asks which document the
        # report itself is about, and that is the `document` axis alone.
        "detail": scope if pending.kind == "outstanding_detail" else None,
    }
    carried = pending if pending.kind == "outstanding_detail" else None
    return focus, carried, None, True


def _answer_pending(state: State, verdict: dict[str, Any], trace: Trace):
    # Returns (focus_after, pending_after, short_circuit_plan, domain_locked).
    pending = state.pending
    focus = copy.deepcopy(state.focus)

    if pending is None:
        return focus, None, None, False

    if pending.kind in OUTSTANDING_KINDS:
        # BEFORE the generic roster path: these options are a SCOPE, not an entity to
        # fetch with, and building one into an entity sent "Both" to the resolver as an
        # order token (console run 4, finding 6).
        answered = _answer_outstanding(state, pending, verdict, focus, trace)
        if answered is not None:
            return answered

    if pending.kind in ESCALATION_OFFER_KINDS:
        # BEFORE the roster path: an accepted escalation offer is a handover, never a
        # fetch, whichever of the three ways it was accepted.
        accepted = _answer_offer(pending, verdict, focus, trace)
        if accepted is not None:
            return accepted

    answers = verdict.get("answers_open_question") or {}
    positions = _picked_positions(pending, verdict) or []
    if answers.get("resolved") is True or positions:
        matched = [o for o in pending.options if o.get("position") in positions]
        if not matched:
            # The parser said this WAS an answer, but nothing it picked is on the list -
            # a position off the end, or a label the roster does not carry. Same outcome
            # as `resolved: false` below: the SAME question is re-printed, state
            # untouched. Clearing the pending here (which is what fell out of the
            # `if matched:` guard before) dropped the question silently and left the
            # customer's next message with nothing to answer.
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
            code = option.get("code") or option.get("label")
            name = option.get("name")
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

    is_affirmative = verdict.get("is_affirmative")
    escalation = verdict.get("escalation") or {}
    verdict_entities = verdict.get("entities") or []

    if is_affirmative is True or escalation.get("is_escalation_confirmation") is True:
        trace.rules_fired.append("answer_pending_accept")
        return focus, None, None, False

    if escalation.get("escalation_declined") is True or (is_affirmative is False and not verdict_entities):
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

    if is_affirmative is False and verdict_entities:
        # A "no" carrying its own entities is not a decline - the offer stays open.
        trace.rules_fired.append("answer_pending_own_entities")
        return focus, pending, None, False

    if answers.get("resolved") is False:
        # The customer TRIED to answer and missed (a number off the list, a label that
        # matches nothing offered): the SAME question is re-printed, state untouched.
        trace.rules_fired.append("answer_pending_unresolved")
        short_circuit = Plan(domains=[], fetch=[], ask=pending, denied=[], trace=trace)
        return state.focus, pending, short_circuit, False

    # `resolved` null (or absent): the parser judged this message to be about something
    # else (cluster 4, owner ruling 16 Sep 2026 - the PARSER decides, no word lists). It
    # is not an answer, so the question stays open exactly as it was and the message is
    # planned as any other; the tail keeps the carried pending (`answer.question or
    # state.pending`). Before this rule every such message fell through to the re-print
    # above, which is what re-asked the customer on every aside the moment the question
    # survived a dry run (finding 2a).
    trace.rules_fired.append("answer_pending_not_an_answer")
    return focus, pending, None, False


def _domain_of_turn(
    focus: Focus,
    verdict: dict[str, Any],
    asks: list[dict[str, Any]],
    domain_override: str | None,
    *,
    domain_locked: bool,
) -> str | None:
    """Which domain this turn is ABOUT, read the same order `_focus_rules` resolves it.

    Needed one step earlier than that assignment, because whether two entities share an
    axis is a fact about the DOMAIN they are named under.
    """
    if domain_locked:
        return focus.domains[0] if focus.domains else None
    if domain_override:
        return domain_override
    for ask in asks:
        if ask.get("domain"):
            return str(ask["domain"])
    if verdict.get("domain_hint"):
        return str(verdict["domain_hint"])
    return focus.domains[0] if focus.domains else None


def _focus_rules(
    focus: Focus,
    verdict: dict[str, Any],
    entities: list[dict[str, Any]],
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
        about = _domain_of_turn(focus, verdict, asks, domain_override, domain_locked=domain_locked)
        shared = SHARED_AXIS_BY_DOMAIN.get(about or "", frozenset())
        if verdict.get("entity_op") == "replace":
            # The retired head's own rule: `replace` means this turn's entities ARE the
            # whole scope, on every axis. It is only ever stamped by a pick that has
            # already folded in whatever it means to keep. `scope_exclusive` is NOT the
            # same thing here and stays a trace marker (`_exclusive`): the narrower
            # already restricts the axis a new entity named, and
            # `test_rearch_s2_exclusive.py` pins that "only BRW" keeps the product and
            # the customer it is narrowing.
            shared = frozenset(KIND_FIELD_MAP)
        for kind in shared - set(by_kind):
            attr = KIND_FIELD_MAP.get(kind)
            if attr and getattr(focus, attr, None):
                setattr(focus, attr, [])
                trace.rules_fired.append(f"same_axis_evicts_{kind}")

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


def _exclusive(verdict: dict[str, Any], trace: Trace) -> None:
    # `replace_same_axis` already narrows only the axis a new entity named (see
    # `_focus_rules` above) - `scope_exclusive` confirms the same reading rather than
    # changing it, so this step is a trace marker, not a second mutation.
    if verdict.get("scope_exclusive"):
        trace.rules_fired.append("exclusive")


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
    if (verdict.get("answers_open_question") or {}).get("resolved") is True:
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
    if message_type == "request_for_help" and verdict.get("domain_hint") not in _HELP_EXEMPT_DOMAINS:
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
            if outcome.entities and (candidates or {}).get(kind):
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
):
    trace = Trace()

    # F3 (contract 65): a `domain_hint` outside the declared enum must never reach a
    # reader - evidence turn b5b19cec-dccc-4eda-b766-1aeb1362957b emitted "purchasing"
    # (a TEAM name, not a domain) and it survived into a tool pick. `coerce_domain_hint`
    # existed but had no call site anywhere in the rearch (AC-1592 test triage);
    # coerced ONCE here, at the verdict's one entry point into apply(), so every
    # downstream read (`_reconcile_step`, `_answer_pending`, `_exclusive`,
    # `_focus_rules`, the `domains` build below, `_lane`) sees the same coerced value
    # rather than needing its own guard.
    coerced_domain_hint = contracts.coerce_domain_hint(verdict.get("domain_hint"))
    if coerced_domain_hint != verdict.get("domain_hint"):
        trace.rules_fired.append("domain_hint_coerced")
        verdict = {**verdict, "domain_hint": coerced_domain_hint}

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

    verdict_entities = list(verdict.get("entities") or [])
    entities, domain_override, reconcile_short_circuit = _reconcile_step(
        verdict_entities, resolved, policy, verdict, trace
    )
    if reconcile_short_circuit is not None:
        return state, reconcile_short_circuit

    focus_after_pending, pending_after, pending_short_circuit, domain_locked = _answer_pending(
        state, verdict, trace
    )
    if pending_short_circuit is not None:
        unchanged = replace(state, pending=pending_after)
        return unchanged, pending_short_circuit

    _exclusive(verdict, trace)

    focus = _focus_rules(
        focus_after_pending,
        verdict,
        entities,
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

    new_state = State(focus=focus, pending=pending_after, profile=state.profile, turn_no=state.turn_no)
    trace.lane = _lane(verdict, domains, policy)

    # A did-you-mean outranks both the narrower and the lane: an entity nobody could place
    # is the first thing worth asking about (contract 26, 111).
    answers = verdict.get("answers_open_question") or {}
    if answers.get("resolved") is not True:
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
    plan = _narrow_and_plan(focus, policy, domains, new_state, trace, attributes, candidates)

    if trace.outstanding is not None:
        # Contract 38/39: this fetch is the ANSWERED question's own report re-running.
        # Stamped on the spec rather than read off the focus by the runtime, because the
        # focus alone cannot tell "the customer just answered the question about this
        # product" from "this product is what the conversation happens to be about" -
        # and only the first may override the resolver's own read of a typed code (D10).
        for spec in plan.fetch:
            spec.filters["outstanding"] = dict(trace.outstanding)

    return new_state, plan
