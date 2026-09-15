"""The THREE GENERAL RULES the owner's 15 Sep merge test asked for, parametrized.

Owner instruction this file exists to satisfy (15 Sep 2026): a fix is general or it is not
a fix. R-A to R-H were each reported as one scenario, and the coder's first passes closed
them one scenario at a time - so the same defect came back on the next arm (R-C's
`require_specific` narrowing, fixed, came back as R-D's customer arm; R-A's born-beside
merge, fixed for the did-you-mean roster, left the customer picker's own offer naming one
team while the question recorded another). Every test below is therefore
`pytest.mark.parametrize`d over the ARMS a rule has to hold on, driven through the REAL
turn path (`engine.run_turn`, parser / access / resolver / MCP faked at their own seams),
and each arm's shape was MEASURED on this head before the assertion was written.

The three rules, as the coder is implementing them:

1. **THE OFFER HAS ONE WRITER AND ONE TEAM.** As shipped: the arms keep their own
   selection condition and delegate CONSTRUCTION to `dialogue/open_question.record_offer`,
   which is the single implementation of what an offer is - called from two sites, the
   tail (over its own composed text) and the engine's post-compose arm (over the text
   `crossdomain_compose` may have appended), idempotent through `with_offer`. One team
   source: `team_from_reply` reads the team back off the sentence the customer will read.
   The team the SENTENCE prints and `payload.offer.team` /
   `payload.team` come from ONE source, and a `yes` routes to THAT team. A v1-shaped
   `yes` - the PROMOTED prompt's own shape, with `escalation.is_escalation_confirmation:
   true` and NO `answers_open_question` key at all - resolves the question through the
   same bridge a v3 `yes` does. Live: turn 570610f0-1223-4340-9c46-73503e678b8b answered
   "yes" to an offer that had printed "warehouse team" (armed on turn
   cca6b365-c99c-4382-8891-7e6598b2e83c, `expects: pick_or_yes_no`,
   `payload.offer.team: warehouse`; the standalone shape on turns eaacced5 / 9bff244b)
   and was escalated to CUSTOMER SERVICE with the question left open behind it.

2. **A PICK KEEPS WHAT THE SAME MESSAGE RESOLVED BESIDE IT.** The gate publishes the
   co-resolved siblings on `out["keep_entities"]`, `compatible_entities` goes back to
   being exactly the rows on offer, and ONE apply site in `dialogue/open_question.resolve`
   gives every handler the same keep. The frozen roster is therefore always exactly the
   rows the reply numbered, and a bare number can never reach a row the customer was
   never shown.

3. **NO ANSWER-OR-REFINEMENT DECISION READS `domain_hint`.** The live v20 model stamps a
   domain word on a filter as readily as on a question (R-B, R-H), so every decision about
   what a turn taken under an open question MEANS must read the same way whether
   `domain_hint` is null or `"order"`. Four branches carry that read today:
   `output_exchange.py` ~1618 (`_apply_outstanding_pending`'s `own_question`), ~1461
   (`_outstanding_leaves_the_offer`), ~3904 (the company-pick carry over an open offer)
   and ~3643/3666 (the member-offer pick gate).

ACs: AC-1060 (keep across a pick), AC-1061 (the offer rides a roster born beside it),
AC-1062 (a detail pick is not a new ask), AC-1065 (a narrowing is not a new ask, whatever
word the model stamped).

**Why this file has its own `_run_turn` rather than importing
`test_outstanding_lane._run_turn`**: two knobs that one does not have and every arm here
needs - `emits_v3` (the v1/v3 parity half of rule 1: the promoted prompt emits NO
`answers_open_question`, so the v1 and v3 shapes of the same "yes" must be driven through
`ParserConfig.emits_v3` both ways), and `is_test` (a dry-run escalation lane, which is the
only way a real turn's `add_comment` text can be read without seeding an SLA policy, a
team roster and a respond user - the live chain's own "Team: <team>" line is what the
customer's case is triaged by). Everything else - the contact seed, the session read, the
lane switches - is imported from that file rather than copied.

**The resolver stub matches a token EXACTLY, never as a substring** (tester 1's own bug,
recorded in the handoff): a stub that answered for "wc286" whenever the request mentioned
it re-resolved the ten-way family on the PICK turn too, because the picked row's label
contains the token, so the picker re-armed and the pick test failed for the wrong reason.

Postgres only, every row seeded here.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable

import pytest

from app.models.user import SystemSetting
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head.output_exchange import output_exchange
from app.services.chatbot.lanes.business.services import (
    AnswerServices,
    FetchServices,
    ResolveGateServices,
)
from tests.chatbot.conftest import set_chatbot_switches, validating_resolve_entity
from tests.chatbot.test_engine import CONTACT_ID, _envelope, _parser_output  # noqa: F401
from tests.chatbot.test_outstanding_lane import (
    REPORT_HIT,
    _capturing_mcp,
    _open_question,
    _seed_contact,
    _session_of,
    _stored_oq,
    _stored_oq_filters,
    _stored_oq_options,
)

# --------------------------------------------------------------------------- #
# Measured fixtures. Every code, uuid and company below is the live shape from
# `sorento_ai_automation_focus_full` (contact 437264483, 15 Sep 2026) or, for the
# stock ladder, the owner's own console chain.
# --------------------------------------------------------------------------- #

STOCK_CODE = "SRTWT2634"
STOCK_UUID = "11111111-1111-1111-1111-111111111111"
PROMO_CODE = "SRTWC286-SH"
PROMO_UUID = "55555555-1111-1111-1111-111111111111"
OUTSTANDING_CODE = "SRTWT7445"
OUTSTANDING_UUID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

#: The ten-way WC286 family, exactly as the resolver returned it on the live turn.
WC286_CODES = (
    "SRTWC286-SH", "SRTWC286-SH-P", "SRTWC286-SH-200", "SRTWC286-SH-NEW",
    "SRTWC286-SH-NEW-P", "SRTWC286-SH-NEW-200", "SRTWC286-S-150-RL",
    "SRTWC286A-P-RL", "SRTWC286A-RL-320", "SRTWC286-P",
)
#: The three real CHIN CHUN companies the customer token is ambiguous across.
CHIN_CHUN = (
    ("060f4eaf-88ca-486a-a203-b0b61eeb9cd8", "300-C043", "CHIN CHUN HARDWARE SDN BHD"),
    ("13eb525b-985c-44a5-abc4-4be5c7db6cd6", "300-C124", "CHIN CHUN HOMEMART SDN BHD"),
    ("fa32b334-fc47-4bec-96db-f0f59a4bcb0f", "300-C001", "CHIN CHUN HARDWARE AND TIMBER TRADING"),
)

EMPTY_STOCK = {
    "result_type": "stock", "intro": "No matching results found.", "items": [], "has_result": False,
}
NO_ROWS = {"answers": [], "has_result": False}
#: The cross-domain INCOMING rung's own rows - the shape that makes a stock miss end in
#: "But there is INCOMING stock (ETA) ..." and then the escalate sentence (turn cca6b365).
INCOMING_ROWS = {
    "answers": [
        {
            "fields": [
                {"key": "product_code", "label": "Product Code", "value": STOCK_CODE},
                {"key": "container_number", "label": "Container", "value": "CONT-1"},
                {"key": "expected_date", "label": "Expected Date", "value": "2026-10-01"},
                {"key": "qty", "label": "Qty", "value": 50},
            ]
        }
    ],
    "has_result": True,
}

_ESCALATE_SENTENCE_RE = re.compile(
    r"[Ww]ould you like me to escalate to (?:\*[^*]+\* )?(.+?) team\?"
)


def _printed_team(reply: str) -> str | None:
    """The team word the REPLY the customer read actually named, or None.

    Case-insensitive on the first word and tolerant of the bold company insert
    (`*Sorento* customer service team?`), deliberately: the point of this reader is to
    find out what the customer was PROMISED, and three different composers write this
    sentence today (`tail/compile_state`'s two miss arms, `tail/compose.crossdomain_
    compose`, and four arms in `lanes/business/answer.py`, one of which spells it with a
    lower-case "would"). A reader that only matched the frozen capitalised prefix would
    call an arm "no offer at all" when the customer can plainly read one.
    """
    match = _ESCALATE_SENTENCE_RE.search(reply or "")
    return match.group(1).strip() if match else None


def _pretty(team: Any) -> str:
    return str(team or "").replace("_", " ").strip()


def _recorded_team(question: Any) -> Any:
    """The team a `yes` on this persisted question would route to.

    Both shapes, because a merged roster carries it one level down (D19 rule 3): the
    offer's own team where an offer rides, else the question's own payload team.
    """
    payload = (question or {}).get("payload") or {}
    offer = payload.get("offer")
    if isinstance(offer, dict) and offer.get("team") is not None:
        return offer.get("team")
    return payload.get("team")


def _comment_teams(result: Any) -> list[str]:
    """Every team named by an `add_comment` action on this turn.

    The escalation lane's own triage note (`lanes/escalation._comment_text`): "Team:
    <slug>", the raw slug, which is what the person picking the case up searches by.
    """
    out = []
    for action in result.actions or []:
        if not isinstance(action, dict) or action.get("kind") != "add_comment":
            continue
        for line in str(action.get("text") or "").splitlines():
            if line.startswith("Team: "):
                out.append(line[len("Team: "):].strip())
    return out


# --------------------------------------------------------------------------- #
# The runner
# --------------------------------------------------------------------------- #

#: The completed-lane set every arm here needs: the business lane composes the offer, the
#: escalation lane answers the `yes` (`out_of_scope`) and the decline arm answers the `no`
#: (`escalation_declined`). A lane left out DELEGATES, and a delegated turn writes no
#: actions at all - which reads as "the escalation never ran" when in truth it was handed
#: to n8n (the first trap this file's exploration hit).
LANES = ("business_query", "out_of_scope", "escalation_declined")
PROMO_LANES = (*LANES, "check_promotion")


def _run_turn(
    session_factory,
    monkeypatch,
    *,
    qf: dict[str, Any],
    text_body: str,
    msg_id: str,
    attributes: list[str] | None = None,
    resolve_services: ResolveGateServices | None = None,
    fetch_response: Any = None,
    probe_response: Any = None,
    emits_v3: bool = False,
    is_test: bool = False,
    lanes: tuple[str, ...] = LANES,
    complete_delegated: bool = True,
):
    """One real `engine.run_turn`. Returns `(result, calls)`.

    `calls` records every MCP call the turn made, fetch and probe alike, the probe
    prefixed `probe:` - the cross-domain ladder runs on the PROBE seam and the fetch on
    the tool seam, and a test about the ladder has to be able to tell them apart.

    `is_test=True` makes the turn a DRY RUN: the escalation lane still runs and still
    composes its real reply and its real `add_comment` text, with `<preview>` where a
    write would have happened. It is how the "Team: <team>" line is read without seeding
    an SLA policy row.
    """
    set_chatbot_switches(session_factory, business_lane=True)
    db = session_factory()
    # EVERY row, not `.first()`: a blank schema can carry more than one settings row and
    # the engine reads its own (the trap `test_foundre_rung_end_to_end` documents).
    for row in db.query(SystemSetting).all():
        row.chatbot_completed_lanes = list(lanes)
        # Migration 491's shipped ladder, explicitly: the cross-domain arm below is the
        # rung every tenant ships with, not a test-only wiring.
        row.chatbot_crossdomain_ladder = {
            "inventory": ["incoming", "purchase_order"],
            "incoming": ["inventory", "purchase_order"],
        }
    db.commit()

    monkeypatch.setattr(
        engine_mod,
        "check_access",
        lambda db, *, agent_code, contact_id, space_id: {
            "allowed": True,
            "decision": "allow",
            "agent_name": "General",
            "attributes": attributes or [],
            "all_attributes_allowed": None,
        },
    )
    monkeypatch.setattr(engine_mod, "default_space_id", lambda db: "364817")

    from app.services.chatbot.head import parser as parser_mod

    def _config(db, *, current_date, override_version_id=None):
        # `emits_v3` is read off the resolved prompt TEXT in production
        # (`parser.V3_PROMPT_MARKER`); both are set here so a config built either way
        # agrees with itself.
        return parser_mod.ParserConfig(
            system_prompt='"answers_open_question"' if emits_v3 else "stub",
            prompt_version=3 if emits_v3 else 1,
            provider="openai",
            model="gpt-test",
            api_key="sk-test",
            emits_v3=emits_v3,
        )

    monkeypatch.setattr(parser_mod, "resolve_config", _config)
    monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: qf)

    calls: list[tuple[str, dict[str, Any]]] = []

    def _fetch(name: str, args: dict[str, Any]) -> Any:
        calls.append((name, dict(args)))
        if fetch_response is None:
            return json.dumps(EMPTY_STOCK)
        if callable(fetch_response):
            return fetch_response(name, args)
        if isinstance(fetch_response, str):
            return fetch_response
        return json.dumps(fetch_response)

    def _probe(name: str, args: dict[str, Any]) -> Any:
        calls.append((f"probe:{name}", dict(args)))
        if probe_response is None:
            return NO_ROWS
        if callable(probe_response):
            return probe_response(name, args)
        return probe_response

    monkeypatch.setattr(
        engine_mod.business_services,
        "production_services",
        lambda db, *, space_id=None: resolve_services or _exact_services(),
    )
    monkeypatch.setattr(
        engine_mod.business_services, "fetch_services", lambda db: FetchServices(mcp_call=_fetch)
    )
    monkeypatch.setattr(
        engine_mod.business_services,
        "answer_services_for",
        lambda session_factory: AnswerServices(
            mcp_probe=_probe, family_fetch=lambda query: {"data": []}
        ),
    )

    envelope = _envelope(is_test=is_test)
    # The escalation lane needs a phone on the envelope or it 400s before it composes
    # anything ("contact_phone_number (or contact_phone) is required") - infra, not a red.
    envelope.contact["phone"] = "+60000000009"
    envelope.message["contact"]["phone"] = "+60000000009"
    envelope.message["message"]["messageId"] = msg_id
    envelope.message["message"]["message"]["text"] = text_body
    result = engine_mod.run_turn(envelope, session_factory=session_factory)
    if result.delegate is not None and complete_delegated:
        # A turn whose branch kind is not in `chatbot_completed_lanes` DELEGATES, and a
        # delegated turn has not run the tail - so nothing has written the session yet and
        # a test reading `open_question` back would grade the PREVIOUS turn's state and
        # call it a pass. n8n answers such a turn with `sub-output`; the harness stands in
        # with that trigger's own minimal contract, exactly as `test_worlds.py` does for
        # its delegated worlds, so the tail runs and the session write happens.
        engine_mod.complete_turn(
            result.turn_id,
            {
                "item": {"branch_kind": "business_query", "allowed": True},
                "result": None, "resolved": None, "gate": None, "offer_hold": None,
                "suggest_offer": None, "not_found": None, "incoming_picker": None,
                "access_choice": None, "crossdomain_render": None, "answer": None,
                "clarify": None,
            },
            session_factory=session_factory,
        )
    return result, calls



def _final_vars(session_factory, result) -> dict[str, Any]:
    """The five-key session as THIS turn left it, dry run or not.

    **Not the contact row.** A dry-run turn (`is_test`, which is what the console and
    every assertion here that needs the escalation lane's real `add_comment` text uses)
    writes NOTHING: `complete_turn`'s own `written = (not dry_run) and ...`. So a test
    that read `respond_contacts.session_vars` after a dry-run answer turn would be
    reading the ARMING turn's state and grading it as the answer's - green or red for a
    reason that has nothing to do with the code under test.

    The engine records its would-be patch on the `remembered` stage instead
    ("Nothing was written: this is a test turn (D14)."), and that IS the value a live
    turn would have persisted, so it is what the answer-turn assertions read. A
    non-dry-run turn carries the same object there, so one reader serves both.
    """
    from app.models.chatbot_turn import ChatbotTurn

    row = (
        session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).first()
    )
    for entry in reversed(list((row.trace if row is not None else None) or [])):
        if not isinstance(entry, dict) or entry.get("stage") != "remembered":
            continue
        variables = ((entry.get("raw") or {}).get("session_patch") or {}).get("variables")
        if isinstance(variables, dict):
            return variables
    return _vars(session_factory)


def _report_call(report: dict[str, Any]):
    """A `mcp_call` that answers `crm_outstanding_report` the way PRODUCTION does.

    The lane always sends `view=render` (`fetch.entity_ids_transformer`), so what comes
    back from that tool is what `sorento_crm_mcp.presenters.present_response` rendered
    from the route body - never the body itself. `test_outstanding_lane._capturing_mcp`
    is the double that does that, and it is reused here rather than re-implemented: a
    test that hands the lane a raw dict feeds the reply composer a shape production never
    produces, which is precisely what hid six user-visible defects behind 33 green tests.
    """
    call, _captured = _capturing_mcp(report)
    return call

def _tokens_of(body: dict[str, Any]) -> set[str]:
    """The tokens THIS resolver request actually asked about, lower-cased and exact."""
    asked = [str(body.get("query") or "")] + [str(t) for t in (body.get("tokens") or [])]
    return {a.strip().lower() for a in asked if a and a.strip()}


def _exact_services(
    *,
    multi: dict[str, list[dict[str, Any]]] | None = None,
    single: dict[str, dict[str, Any]] | None = None,
    unresolved: tuple[str, ...] = (),
) -> ResolveGateServices:
    """A `resolve_entity` seam keyed on EXACT tokens (see the module docstring).

    `multi` maps a token to the several rows it is ambiguous across; `single` maps a token
    to the one row it resolves to. A request that asks about neither resolves nothing,
    which is what a bare positional pick sends.
    """

    def _resolve_entity(body: dict[str, Any]) -> dict[str, Any]:
        asked = _tokens_of(body)
        resolutions = []
        for token, rows in (multi or {}).items():
            if token.lower() in asked:
                resolutions.append(
                    {"raw": token, "token": token, "resolved": False, "matches": list(rows)}
                )
        for token, row in (single or {}).items():
            if token.lower() in asked:
                resolutions.append(
                    {"raw": token, "token": token, "resolved": True, "matches": [dict(row)]}
                )
        missed = [token for token in unresolved if token.lower() in asked]
        return {
            "tokens": [r["token"] for r in resolutions] + missed,
            "resolutions": resolutions
            + [{"raw": token, "token": token, "resolved": False, "matches": []} for token in missed],
            "unresolved_tokens": missed,
        }

    return ResolveGateServices(
        access_types=lambda **_: [{"name": "Sorento Dealer"}],
        resolve_entity=validating_resolve_entity(_resolve_entity),
        probe=lambda **_: None,
    )


def _product_rows(*codes: str) -> list[dict[str, Any]]:
    return [
        {
            "uuid": f"3333333{i}-1111-1111-1111-11111111111{i % 10}",
            "entity_type": "product",
            "canonical_code": code,
            "match_tier": "trgm",
            "company_name": "Sorento",
        }
        for i, code in enumerate(codes, start=1)
    ]


def _customer_rows() -> list[dict[str, Any]]:
    return [
        {
            "uuid": uuid,
            "entity_type": "customer",
            "canonical_code": code,
            "match_tier": "trgm",
            "company_name": "Sorento",
            "company_code": "SRT",
            "display": {"customer_name": name},
        }
        for uuid, code, name in CHIN_CHUN
    ]


def _entity(raw: str, hint: str) -> dict[str, Any]:
    return {
        "raw": raw, "hint": hint, "canonical_code": None,
        "current_message": True, "confident": True,
    }


def _qf(entities: list[dict[str, Any]], *, domain: str | None, **kw: Any) -> dict[str, Any]:
    """A v1-shaped emission, plus `asks` so the same shape also passes the v3 assertion.

    `asks` is inert under v1 (`_assert_emission` only requires it under v3) and is the
    flattening source under v3, so one builder serves both halves of rule 1's parity.
    """
    base = dict(
        message_type="business_query",
        domain_hint=domain,
        entities=entities,
        asks=[{"domain": domain, "entities": entities}],
        routing={"suggested_team": None, "suggested_agent": None, "team_source": None},
    )
    base.update(kw)
    return _parser_output(**base)


def _yes_v1() -> dict[str, Any]:
    """The PROMOTED prompt's own "yes": no `answers_open_question` key at all.

    Turn 570610f0-1223-4340-9c46-73503e678b8b, verbatim on the fields that decide:
    `message_type: casual`, `is_affirmative: true`,
    `escalation.is_escalation_confirmation: true`, `reference_positions: []`, and the
    three v3 keys ABSENT - which is why `v3_signals` returns the inert default and
    `_resolve_open_question`'s only bridge (positions) finds nothing to bridge.
    """
    return _parser_output(
        message_type="casual", intent_hint=None, domain_hint=None, entities=[], asks=[],
        is_affirmative=True, reference_positions=[],
        escalation={"is_escalation_confirmation": True, "company_pick": None},
        routing={"suggested_team": None, "suggested_agent": None, "team_source": None},
    )


def _no_v1() -> dict[str, Any]:
    return _parser_output(
        message_type="casual", intent_hint=None, domain_hint=None, entities=[], asks=[],
        is_affirmative=False, reference_positions=[],
        escalation={"is_escalation_confirmation": False, "company_pick": None},
        routing={"suggested_team": None, "suggested_agent": None, "team_source": None},
    )


def _yes_v3() -> dict[str, Any]:
    return _parser_output(
        message_type="casual", intent_hint=None, domain_hint=None, entities=[], asks=[],
        is_affirmative=True, reference_positions=[],
        escalation={"is_escalation_confirmation": True, "company_pick": None},
        routing={"suggested_team": None, "suggested_agent": None, "team_source": None},
        answers_open_question={"resolved": True, "picks": [], "yes_no": "yes", "free_text": None},
        anaphora=False, topic_reset=False,
    )


def _pick_v1(position: int) -> dict[str, Any]:
    return _parser_output(
        message_type="casual", intent_hint=None, domain_hint=None, entities=[], asks=[],
        reference_positions=[position],
        routing={"suggested_team": None, "suggested_agent": None, "team_source": None},
    )


def _vars(session_factory) -> dict[str, Any]:
    return _session_of(session_factory)["variables"]


# =========================================================================== #
# GROUP 1 - THE OFFER HAS ONE WRITER AND ONE TEAM (AC-1061)
#
# Four arms, each MEASURED on this head (9d5b66dd1 + the coder's R-A/R-H fixes):
#
# | arm                  | the reply says            | payload records      | roster |
# |----------------------|---------------------------|----------------------|--------|
# | miss                 | warehouse                 | warehouse            | no     |
# | crossdomain-ladder   | warehouse                 | warehouse            | no     |
# | company-team-promo   | marketing promotion       | marketing_promotion  | no     |
# | rides-customer-picker| customer service          | customer_service     | yes    |
#
# The `miss` arm deliberately has the PARSER name a different team (`purchasing`) from
# the one the reply prints, and the `company-team-promo` arm is the one where
# `gate.company_team` is set (`promotion` + one brand) and so `_escalation_team` prefers
# it over `routing.suggested_team` - the two cases the security review asked for, where
# the SENTENCE's composer and the OFFER's composer read different sources.
# =========================================================================== #


@dataclass(frozen=True)
class OfferArm:
    id: str
    #: Is there a numbered roster under the offer (D19 rule 3 - a number still re-picks)?
    roster: bool
    lanes: tuple[str, ...]
    #: `(session_factory, monkeypatch, tag) -> (reply_text, resolve_services)`
    build: Callable[..., tuple[str, ResolveGateServices]]


def _stock_services() -> ResolveGateServices:
    return _exact_services(
        single={
            STOCK_CODE: {
                "uuid": STOCK_UUID, "entity_type": "product", "canonical_code": STOCK_CODE,
                "match_tier": "exact", "company_name": "Sorento",
            }
        }
    )


def _build_miss_arm(session_factory, monkeypatch, tag: str):
    """A stock ask that finds nothing anywhere: the plain standalone offer."""
    _seed_contact(session_factory, variables={})
    services = _stock_services()
    result, _calls = _run_turn(
        session_factory, monkeypatch,
        # The PARSER names purchasing; the reply names warehouse (the domain's own team).
        # Whatever wins, the sentence and the record have to name the SAME one.
        qf=_qf([_entity(STOCK_CODE, "product")], domain="inventory", intent_hint="check_stock",
               routing={"suggested_team": "purchasing", "suggested_agent": None, "team_source": None}),
        text_body=f"check stock {STOCK_CODE}", msg_id=f"ZZT-gr-miss-{tag}",
        resolve_services=services,
    )
    return (result.reply or {}).get("text") or "", services


def _build_ladder_arm(session_factory, monkeypatch, tag: str):
    """Turn cca6b365's own shape: no stock, but the cross-domain INCOMING rung answers,
    and the reply ends in the escalate sentence anyway."""
    _seed_contact(session_factory, variables={})
    services = _stock_services()

    def _probe(name: str, args: dict[str, Any]) -> Any:
        return INCOMING_ROWS if name == "crm_incoming_stock_list" else NO_ROWS

    result, _calls = _run_turn(
        session_factory, monkeypatch,
        qf=_qf([_entity(STOCK_CODE, "product")], domain="inventory", intent_hint="check_stock"),
        text_body=f"check stock {STOCK_CODE}", msg_id=f"ZZT-gr-ladder-{tag}",
        resolve_services=services, probe_response=_probe,
    )
    reply = (result.reply or {}).get("text") or ""
    assert "INCOMING stock (ETA)" in reply, (
        f"this arm is only itself if the ladder actually answered: {reply!r}"
    )
    return reply, services


def _build_promo_arm(session_factory, monkeypatch, tag: str):
    """A promotion miss on a single brand, which is the ONE shape where
    `gate.company_team` is set (`marketing_promotion`) and so decides the recorded team
    while `lanes/business/answer.py`'s own not-found composer reads
    `routing.suggested_team`."""
    _seed_contact(session_factory, variables={})
    services = _exact_services(
        single={
            "srtwc286": {
                "uuid": PROMO_UUID, "entity_type": "product", "canonical_code": PROMO_CODE,
                "match_tier": "exact", "company_name": "Sorento",
            }
        }
    )
    result, _calls = _run_turn(
        session_factory, monkeypatch,
        qf=_qf([_entity("srtwc286", "product")], domain="promotion",
               intent_hint="check_promotion", access_levels=[]),
        text_body="promo for srtwc286", msg_id=f"ZZT-gr-promo-{tag}",
        resolve_services=services, lanes=PROMO_LANES,
    )
    return (result.reply or {}).get("text") or "", services


def _chin_chun_services() -> ResolveGateServices:
    return _exact_services(
        multi={"chin chun": _customer_rows(), "wc286": _product_rows(*WC286_CODES)}
    )


def _build_customer_picker_arm(session_factory, monkeypatch, tag: str):
    """R-D's own chain, one turn further: the ambiguous customer roster, then the pick,
    whose re-run finds no order and appends the escalate sentence - so the offer is born
    over a roster the customer is still looking at (D19 rule 3)."""
    _seed_contact(session_factory, variables={})
    services = _chin_chun_services()
    _run_turn(
        session_factory, monkeypatch,
        qf=_qf(
            [_entity("chin chun", "customer"), _entity("wc286", "product")],
            domain="order", intent_hint="check_order", entity_op="replace_combine",
            requested_attributes=["delivery"],
        ),
        text_body="delivery for chin chun product wc286", msg_id=f"ZZT-gr-cust-arm-{tag}",
        resolve_services=services,
    )
    result, _calls = _run_turn(
        session_factory, monkeypatch, qf=_pick_v1(1), text_body="1",
        msg_id=f"ZZT-gr-cust-pick-{tag}", resolve_services=services,
    )
    return (result.reply or {}).get("text") or "", services


OFFER_ARMS: tuple[OfferArm, ...] = (
    OfferArm("miss", roster=False, lanes=LANES, build=_build_miss_arm),
    OfferArm("crossdomain-ladder", roster=False, lanes=LANES, build=_build_ladder_arm),
    OfferArm("company-team-promo", roster=False, lanes=PROMO_LANES, build=_build_promo_arm),
    OfferArm("rides-customer-picker", roster=True, lanes=LANES, build=_build_customer_picker_arm),
)


@pytest.mark.parametrize("arm", OFFER_ARMS, ids=lambda a: a.id)
class TestTheOfferHasOneWriterAndOneTeam:
    """AC-1061 on every arm that can compose an escalate offer.

    `payload.offer.team` (a roster carrying an offer) or `payload.team` (the standalone
    one) is what `output_exchange._offered_team` reads and what a `yes` assigns, and the
    sentence is what the customer was promised. Three composers write that sentence and a
    fourth function records the team; the rule is that they cannot disagree.
    """

    def test_the_recorded_offer_names_the_team_the_sentence_printed(
        self, arm, session_factory, monkeypatch
    ) -> None:
        reply, _services = arm.build(session_factory, monkeypatch, "team")
        printed = _printed_team(reply)
        assert printed is not None, (
            f"arm {arm.id!r} composed no escalate offer at all, so there is nothing for a "
            f"'yes' to answer: {reply!r}"
        )
        question = _stored_oq(_vars(session_factory))
        assert question, (
            f"arm {arm.id!r} printed an offer ({printed!r}) and recorded no question - a "
            f"yes/no the customer can read must be answerable next turn (AC-1015)"
        )
        recorded = _recorded_team(question)
        assert recorded is not None, (
            f"arm {arm.id!r} recorded an offer with no team, so a 'yes' assigns nobody: "
            f"{question!r}"
        )
        assert _pretty(recorded) == printed, (
            f"arm {arm.id!r}: the reply promised {printed!r} and the question recorded "
            f"{recorded!r} - one team source, or the customer is told one team and handed "
            f"to another: {question!r}"
        )

    def test_a_v1_yes_escalates_to_the_offers_own_team(
        self, arm, session_factory, monkeypatch
    ) -> None:
        """The PROMOTED prompt's shape. Live: turn 570610f0 said yes to a warehouse offer
        and was routed to customer service, because `_resolve_open_question` bridges v1
        `reference_positions` into picks and has NO bridge for yes/no, so nothing
        resolved and the routing chain fell through to `DEFAULT_SUGGESTED_TEAM`."""
        reply, services = arm.build(session_factory, monkeypatch, "yes1")
        recorded = _recorded_team(_stored_oq(_vars(session_factory)))
        result, _calls = _run_turn(
            session_factory, monkeypatch, qf=_yes_v1(), text_body="yes",
            msg_id="ZZT-gr-yes1-answer", resolve_services=services, lanes=arm.lanes,
            is_test=True,
        )
        assert result.status == "done", (result.status, result.error)
        teams = _comment_teams(result)
        assert teams, (
            f"arm {arm.id!r}: a 'yes' to an open offer must escalate - no add_comment "
            f"means nobody was assigned: {result.actions!r}"
        )
        assert teams == [recorded], (
            f"arm {arm.id!r}: the reply promised {_printed_team(reply)!r} and the "
            f"escalation was filed against {teams!r}"
        )

    def test_a_v1_yes_consumes_the_whole_question(
        self, arm, session_factory, monkeypatch
    ) -> None:
        """A `yes` spends the question, roster and all.

        D19 rule 3 and `carry_after_answer`'s own second case: "a roster whose riding
        offer was ACCEPTED is consumed whole - the escalation lane runs, a human has the
        conversation, and a numbered list of products is not what the customer is looking
        at any more". The decline half is the one that keeps the roster (the test below).
        The invariant either way is that the same "yes" cannot escalate twice.
        """
        _reply, services = arm.build(session_factory, monkeypatch, "yes1c")
        result, _calls = _run_turn(
            session_factory, monkeypatch, qf=_yes_v1(), text_body="yes",
            msg_id="ZZT-gr-yes1c-answer", resolve_services=services, lanes=arm.lanes,
            is_test=True,
        )
        question = _stored_oq(_final_vars(session_factory, result))
        assert not question, (
            f"arm {arm.id!r}: the accepted offer is still open, so the next bare 'yes' "
            f"escalates the same thing again: {question!r}"
        )

    def test_a_v1_no_strips_the_offer_and_keeps_whatever_else_was_armed(
        self, arm, session_factory, monkeypatch
    ) -> None:
        """The decline half. Measured on this head: the turn branches
        `escalation_declined` and answers "Escalation declined.", and the offer is still
        sitting in the session - so the next bare "yes" escalates an offer the customer
        has already refused."""
        _reply, services = arm.build(session_factory, monkeypatch, "no1")
        result, _calls = _run_turn(
            session_factory, monkeypatch, qf=_no_v1(), text_body="no",
            msg_id="ZZT-gr-no1-answer", resolve_services=services, lanes=arm.lanes,
        )
        assert result.status == "done", (result.status, result.error)
        question = _stored_oq(_vars(session_factory))
        assert not (question.get("payload") or {}).get("offer"), (
            f"arm {arm.id!r}: 'no' declines the OFFER, so `payload.offer` must be gone: "
            f"{question!r}"
        )
        if arm.roster:
            assert question.get("kind"), (
                f"arm {arm.id!r}: 'no' declines the offer and NOT the numbered list the "
                f"customer is still looking at: {question!r}"
            )
            assert question.get("expects") == "pick", (
                f"arm {arm.id!r}: with the offer declined the question is a plain pick "
                f"again: {question!r}"
            )
        else:
            assert not question, (
                f"arm {arm.id!r}: nothing else was armed beside the offer, so the "
                f"declined question closes: {question!r}"
            )

    def test_a_v3_yes_behaves_identically(self, arm, session_factory, monkeypatch) -> None:
        """Parity, which is the whole point of the bridge: the two prompt versions differ
        in what the model emits, never in what the bot does."""
        reply, services = arm.build(session_factory, monkeypatch, "yes3")
        recorded = _recorded_team(_stored_oq(_vars(session_factory)))
        result, _calls = _run_turn(
            session_factory, monkeypatch, qf=_yes_v3(), text_body="yes",
            msg_id="ZZT-gr-yes3-answer", resolve_services=services, lanes=arm.lanes,
            is_test=True, emits_v3=True,
        )
        assert result.status == "done", (result.status, result.error)
        teams = _comment_teams(result)
        assert teams == [recorded], (
            f"arm {arm.id!r} under v3: the reply promised {_printed_team(reply)!r}, the "
            f"question recorded {recorded!r}, the escalation was filed against {teams!r}"
        )


@pytest.mark.parametrize("arm", [a for a in OFFER_ARMS if a.roster], ids=lambda a: a.id)
def test_a_number_still_repicks_under_a_riding_offer(arm, session_factory, monkeypatch) -> None:
    """D19 rule 1 and rule 3 together: with an offer riding the roster, a NUMBER is still
    a pick against the rows the reply numbered, and it wins over the yes/no (a number is
    unambiguous)."""
    _reply, services = arm.build(session_factory, monkeypatch, "repick")
    result, calls = _run_turn(
        session_factory, monkeypatch, qf=_pick_v1(2), text_body="2",
        msg_id="ZZT-gr-repick-answer", resolve_services=services, lanes=arm.lanes,
        fetch_response=_report_call(REPORT_HIT),
    )
    assert result.status == "done", (result.status, result.error)
    tool_calls = [c for c in calls if not c[0].startswith("probe:")]
    assert tool_calls, f"a re-pick must run the lane again: {calls!r}"
    _name, args = tool_calls[0]
    assert args.get("customer_ids") == [CHIN_CHUN[1][0]], (
        f"'2' must resolve the roster's own SECOND row (CHIN CHUN HOMEMART), never the "
        f"offer and never a row the reply did not number: {args!r}"
    )


class TestTheYesNoBridgeAnswersNothingItWasNotAsked:
    """The negatives, which is what keeps the bridge general rather than greedy.

    A bare "yes" is only an answer where something on the customer's screen asked one.
    Both cases are seeded state rather than an arming turn: the question is the INPUT
    here, not the thing under test.
    """

    def test_a_yes_over_a_roster_with_no_offer_resolves_nothing(
        self, session_factory, monkeypatch
    ) -> None:
        """`dialogue/open_question.resolve`'s own rule: a yes or no on a roster with NO
        offer resolves nothing at all - there is nothing on that screen to say yes to -
        and the roster stays open."""
        rows = [
            {"idx": i, "label": code, "code": code, "uuid": f"uuid-{code}", "entity_type": "product"}
            for i, code in enumerate(WC286_CODES[:3], start=1)
        ]
        _seed_contact(
            session_factory,
            variables={"open_question": _open_question("product_pick", options=rows)},
        )
        result, _calls = _run_turn(
            session_factory, monkeypatch, qf=_yes_v1(), text_body="yes",
            msg_id="ZZT-gr-neg-roster-yes", is_test=True,
        )
        assert result.status == "done", (result.status, result.error)
        final = _final_vars(session_factory, result)
        # Graded on the QUESTION, not on whether the turn escalated at all: this emission
        # carries the parser's own `is_escalation_confirmation: true`, and a turn the
        # parser reads as a confirmation reaching the escalation lane is main's behaviour
        # (D11 - the lane reads no words, it reads that flag) and is not what this round
        # changes. What the bridge may not do is ANSWER a question nobody asked: consume
        # the roster, or mint an offer onto it that was never printed.
        question = _stored_oq(final)
        assert question.get("kind") == "product_pick", (
            f"the roster the customer is still reading must survive a yes it was never "
            f"asked for: {question!r}"
        )
        assert len(_stored_oq_options(final)) == 3, question
        assert question.get("expects") == "pick", (
            f"no offer was ever printed over this roster, so nothing may have made it a "
            f"yes/no question: {question!r}"
        )
        assert not (question.get("payload") or {}).get("offer"), (
            f"an offer the customer never read must not be minted by the answer path: "
            f"{question!r}"
        )

    def test_a_yes_over_a_member_offer_is_answered_by_the_member_offer_itself(
        self, session_factory, monkeypatch
    ) -> None:
        """A `member_offer` owns its own yes/no (`_member_offer`, AC-816): "yes, with
        nobody named" escalates to the offer's OWN team and consumes the offer. The
        generalised yes/no bridge must not reach past it, and must not re-arm it - a
        re-armed member offer is how a later bare "yes" assigns a human to somebody who
        already declined."""
        _seed_contact(
            session_factory,
            variables={
                "open_question": {
                    "kind": "member_offer",
                    "options": [
                        {"idx": 1, "label": "Nurain", "uuid": "aaaaaaaa-0000-0000-0000-000000000001"},
                        {"idx": 2, "label": "Aina", "uuid": "aaaaaaaa-0000-0000-0000-000000000002"},
                    ],
                    "expects": "yes_no",
                    "asked_at_turn": 1,
                    "asked_at": None,
                    "payload": {"team": "warehouse", "domain": "inventory"},
                }
            },
        )
        result, _calls = _run_turn(
            session_factory, monkeypatch, qf=_yes_v1(), text_body="yes",
            msg_id="ZZT-gr-neg-member-yes", is_test=True,
        )
        assert result.status == "done", (result.status, result.error)
        assert _comment_teams(result) == ["warehouse"], (
            f"the member offer recorded `payload.team: warehouse` and its own handler "
            f"(`_member_offer`, 'the customer accepted, with nobody named') routes there "
            f"- under the promoted v1 prompt the handler never runs, so the routing chain "
            f"falls through to DEFAULT_SUGGESTED_TEAM instead: {result.actions!r}"
        )
        final = _stored_oq(_final_vars(session_factory, result))
        assert not final, (
            f"an answered member offer is consumed, never re-armed: {final!r}"
        )


# =========================================================================== #
# GROUP 2 - A PICK KEEPS WHAT THE SAME MESSAGE RESOLVED BESIDE IT (AC-1060)
#
# Three roster arms, each MEASURED on this head:
#
# | arm                       | reply numbers | question records            | keep |
# |---------------------------|---------------|-----------------------------|------|
# | attachment-type-sibling   | 10 products   | product_pick, 10 options    | the type |
# | customer-with-product     | 3 customers   | product_pick, THIRTEEN      | empty |
# | outstanding-with-product  | 3 customers   | product_pick, FOUR          | empty |
#
# The last two are the defect this group exists for, and it is the SAME defect twice:
# `gate.run_gate`'s customer-ambiguity arm appends the other axes' rows onto
# `compatible_entities`, which `tail/compile_state._picker_rows` falls back to on that arm
# (it has no `specific_options`), so the co-resolved sibling is numbered into the roster as
# rows the reply never printed - and `kind` flips off `customer_pick`, so `_customer_pick`
# never runs and `payload.keep` is never even read. `keep_entities` is the channel that
# separates the two facts: what is ON OFFER, and what already resolved beside it.
# =========================================================================== #

_NUMBERED_LINE_RE = re.compile(r"^\s*(\d+)\.\s+(.*?)\s*$")


def _numbered_rows(reply: str) -> list[tuple[int, str]]:
    """The rows the reply actually NUMBERED, in order, as the customer read them."""
    out = []
    for line in (reply or "").splitlines():
        match = _NUMBERED_LINE_RE.match(line)
        if match:
            out.append((int(match.group(1)), match.group(2)))
    return out



def _picked_labels(session_factory, turn_id: str) -> list[str]:
    """Every row the dialogue resolved a POSITION to on this turn, off the persisted trace.

    `engine._resolve_open_question` writes one `open_question` trace event per answered
    turn (`{before, answer, after, handler, outcome}`); `outcome` is the handler's own
    human sentence, composed from the frozen row ("Picked SRTWC286-SH-NEW." / "Picked
    customer CHIN CHUN HOMEMART SDN BHD (SRT)." / "No offered row was named."). Reading it
    is how a test asks "which row did that number mean" without guessing which focus axis
    the answer would have landed on.
    """
    from app.models.chatbot_turn import ChatbotTurn

    row = session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).first()
    out = []
    for entry in list((row.trace if row is not None else None) or []):
        if not isinstance(entry, dict) or entry.get("kind") != "open_question":
            continue
        outcome = str(entry.get("outcome") or "")
        if outcome.startswith("Picked"):
            out.append(outcome)
    return out

@dataclass(frozen=True)
class RosterArm:
    id: str
    #: The kind the ROWS the reply numbered make this question (never the sibling's).
    kind: str
    #: The sibling token that has to survive the pick, and the axis it sits on.
    sibling_raw: str | None
    sibling_hint: str | None
    lanes: tuple[str, ...]
    build: Callable[..., tuple[str, ResolveGateServices]]
    #: Does this arm have rows the reply did NOT print (the defect's own signature)?
    hidden_rows: bool


def _build_attachment_arm(session_factory, monkeypatch, tag: str):
    """R-C's own shape: "photo for srtwc286" - the ten-way product picker with the
    attachment TYPE the same message named beside it. `attachment_type` has no focus
    slot, so `payload.keep` is the only channel that can carry it to the pick."""
    _seed_contact(session_factory, variables={})
    services = _exact_services(
        multi={"srtwc286": _product_rows(*WC286_CODES)},
        single={
            "photo": {
                "uuid": "attach-photo", "entity_type": "attachment_type",
                "canonical_code": "Product Photos", "match_tier": "exact", "company_name": None,
            }
        },
    )
    result, _calls = _run_turn(
        session_factory, monkeypatch,
        qf=_qf(
            [_entity("srtwc286", "product"), _entity("photo", "attachment_type")],
            domain="product_attachment", intent_hint="check_product_attachment",
            requested_attributes=["attachment"],
        ),
        text_body="photo for srtwc286", msg_id=f"ZZT-gr-att-{tag}",
        resolve_services=services,
    )
    return (result.reply or {}).get("text") or "", services


def _build_customer_with_product_arm(session_factory, monkeypatch, tag: str):
    """R-D's own shape: "delivery for chin chun product wc286" - three customer rows
    printed, the ten-way WC286 family resolved beside them and never shown."""
    _seed_contact(session_factory, variables={})
    services = _chin_chun_services()
    result, _calls = _run_turn(
        session_factory, monkeypatch,
        qf=_qf(
            [_entity("chin chun", "customer"), _entity("wc286", "product")],
            domain="order", intent_hint="check_order", entity_op="replace_combine",
            requested_attributes=["delivery"],
        ),
        text_body="delivery for chin chun product wc286", msg_id=f"ZZT-gr-cwp-{tag}",
        resolve_services=services,
    )
    return (result.reply or {}).get("text") or "", services


def _build_outstanding_with_product_arm(session_factory, monkeypatch, tag: str):
    """The same seam on the OUTSTANDING arm: "outstanding for chin chun SRTWT7445" -
    three customer rows printed, one exactly-resolved product beside them. The pick has
    to reach the scope question with BOTH, and the report header prints the product."""
    _seed_contact(session_factory, variables={})
    services = _exact_services(
        multi={"chin chun": _customer_rows()},
        single={
            OUTSTANDING_CODE: {
                "uuid": OUTSTANDING_UUID, "entity_type": "product",
                "canonical_code": OUTSTANDING_CODE, "match_tier": "exact",
                "company_name": "Sorento",
            }
        },
    )
    result, _calls = _run_turn(
        session_factory, monkeypatch,
        qf=_qf(
            [_entity("chin chun", "customer"), _entity(OUTSTANDING_CODE, "product")],
            domain="order", intent_hint="check_order", order_status="outstanding",
            entity_op="replace_combine",
        ),
        text_body=f"outstanding for chin chun {OUTSTANDING_CODE}",
        msg_id=f"ZZT-gr-owp-{tag}", attributes=["sales_orders.outstanding"],
        resolve_services=services,
    )
    return (result.reply or {}).get("text") or "", services


ROSTER_ARMS: tuple[RosterArm, ...] = (
    RosterArm(
        "attachment-type-sibling", kind="product_pick", sibling_raw="Product Photos",
        sibling_hint="attachment_type", lanes=LANES, build=_build_attachment_arm,
        hidden_rows=False,
    ),
    RosterArm(
        "customer-with-product", kind="customer_pick", sibling_raw="wc286",
        sibling_hint="product", lanes=LANES, build=_build_customer_with_product_arm,
        hidden_rows=True,
    ),
    RosterArm(
        "outstanding-with-product", kind="customer_pick", sibling_raw=OUTSTANDING_CODE,
        sibling_hint="product", lanes=LANES, build=_build_outstanding_with_product_arm,
        hidden_rows=True,
    ),
)


@pytest.mark.parametrize("arm", ROSTER_ARMS, ids=lambda a: a.id)
class TestAPickKeepsWhatTheSameMessageResolvedBesideIt:
    def test_the_frozen_options_are_exactly_the_rows_the_reply_numbered(
        self, arm, session_factory, monkeypatch
    ) -> None:
        """AC-1060's own invariant, and the one a bare number depends on: "2" means the
        second row the customer READ. A roster carrying a row the reply never printed is
        a roster whose numbering the customer cannot see."""
        reply, _services = arm.build(session_factory, monkeypatch, "rows")
        printed = _numbered_rows(reply)
        assert printed, f"arm {arm.id!r} numbered nothing: {reply!r}"
        options = _stored_oq_options(_vars(session_factory))
        assert [o.get("label") for o in options] == [label for _idx, label in printed], (
            f"arm {arm.id!r}: the reply numbered {len(printed)} rows and the question "
            f"froze {len(options)} - the co-resolved sibling must ride `keep`, never the "
            f"roster: {[o.get('label') for o in options]!r}"
        )

    def test_the_roster_keeps_its_own_kind(self, arm, session_factory, monkeypatch) -> None:
        """A roster of customers is a `customer_pick` and anything else is a
        `product_pick` (`_rows_are_customers`, said the same way in two composers on
        purpose). The kind decides WHICH handler runs, so a kind flipped by a sibling
        skips `_customer_pick` - and with it `payload.keep`, the customer label and the
        account family."""
        _reply, _services = arm.build(session_factory, monkeypatch, "kind")
        question = _stored_oq(_vars(session_factory))
        assert question.get("kind") == arm.kind, (
            f"arm {arm.id!r}: the rows the reply numbered are {arm.kind!r} rows: "
            f"{question.get('kind')!r}"
        )

    def test_the_sibling_rides_the_questions_keep(
        self, arm, session_factory, monkeypatch
    ) -> None:
        """Issue #708 / AC-1017 on every arm, not one. What the SAME message resolved
        beside the ambiguous token survives the pick - the pick replaces the token it was
        raised for and nothing else."""
        _reply, _services = arm.build(session_factory, monkeypatch, "keep")
        question = _stored_oq(_vars(session_factory))
        keep = (question.get("payload") or {}).get("keep") or []
        raws = {
            str(k.get("raw") or "").lower() for k in keep if isinstance(k, dict)
        } | {
            str(k.get("canonical_code") or "").lower() for k in keep if isinstance(k, dict)
        }
        assert str(arm.sibling_raw).lower() in raws, (
            f"arm {arm.id!r}: the co-resolved {arm.sibling_hint} must be frozen onto the "
            f"question the pick answers: {keep!r}"
        )


@pytest.mark.parametrize(
    "arm", [a for a in ROSTER_ARMS if a.hidden_rows], ids=lambda a: a.id
)
def test_a_number_past_the_last_printed_row_picks_nobody(
    arm, session_factory, monkeypatch
) -> None:
    """S7a's class of blocker, generalised: the customer can only type a number they were
    shown. A roster carrying hidden rows lets a number resolve a row nobody printed - so
    the guard is that a position one past the printed list answers the question with
    nothing at all, rather than with a row the customer never saw."""
    reply, services = arm.build(session_factory, monkeypatch, "hidden")
    printed = _numbered_rows(reply)
    beyond = len(printed) + 1
    result, _calls = _run_turn(
        session_factory, monkeypatch, qf=_pick_v1(beyond), text_body=str(beyond),
        msg_id=f"ZZT-gr-hidden-{arm.id}", resolve_services=services, lanes=arm.lanes,
        attributes=["sales_orders.outstanding"], fetch_response=_report_call(REPORT_HIT),
    )
    assert result.status == "done", (result.status, result.error)
    # Graded on the DIALOGUE TRACE's own record of what the position resolved to, not on
    # a focus slot: with the sibling numbered into the roster, position 4 lands on a
    # PRODUCT row, so `focus.customer` stays empty and a test that read only that axis
    # would pass while the hidden row was picked - a false green of exactly the shape
    # this round is chasing.
    picked = _picked_labels(session_factory, result.turn_id)
    assert not picked, (
        f"arm {arm.id!r}: '{beyond}' is past the {len(printed)} rows the reply numbered, "
        f"so it can only resolve a row the customer was never shown - the dialogue "
        f"picked {picked!r}"
    )


# =========================================================================== #
# GROUP 3 - NO ANSWER-OR-REFINEMENT DECISION READS `domain_hint` (AC-1065)
#
# R-B and R-H are the same defect in two places and both are PRE-EXISTING: a rule keyed
# on whether the model happened to stamp a domain word on the turn. The live v20 parser
# stamps `domain_hint: "order"` on "only BRW" (turn 94639ef2) and on a bare "1" (turn
# 576e1057) as readily as it leaves it null, so a decision that reads it decides the same
# customer's same sentence two different ways on two different days.
#
# The matrix is the rule: for every refinement word, `domain_hint` null / "order" /
# "inventory" must all narrow the report already on the screen.
# =========================================================================== #

CARRIED_CUSTOMER_UUID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
CARRIED_CUSTOMER_NAME = "CNK HARDWARE"

#: The three domain words the live model has been measured stamping on a refinement, and
#: the null it is documented as emitting. `"inventory"` is the case nobody has built yet
#: and the one a domain-keyed rule gets most wrong: a location word is a stock word too.
DOMAIN_HINTS = (None, "order", "inventory")


def _seed_open_detail(session_factory, *, filters: dict[str, Any]) -> None:
    _seed_contact(
        session_factory,
        variables={
            "open_question": _open_question(
                "outstanding_detail",
                options=[
                    {"idx": 1, "label": "Sales order list", "value": "so"},
                    {"idx": 2, "label": "Delivery order list", "value": "do"},
                    {"idx": 3, "label": "Both lists", "value": "both"},
                ],
                filters=filters,
            )
        },
    )


def _customer_subject_filters() -> dict[str, Any]:
    return {
        "product_code": None,
        "date_filter_start": None,
        "date_filter_end": None,
        "customer_ids": [CARRIED_CUSTOMER_UUID],
        "warehouse_codes": [],
        "location_token": None,
        "scope": "both",
    }


def _carried_customer_entity() -> dict[str, Any]:
    """The question's OWN subject, riding `entities` with `current_message: False`.

    The live turn carries it (R-H: `CNK HARDWARE` beside the new `BRW`), and it is what a
    refinement KEEPS - so it must never be graded as an entity this turn brought.
    """
    return {
        "raw": CARRIED_CUSTOMER_NAME, "hint": "customer", "canonical_code": None,
        "current_message": False, "confident": True,
    }


def _location_refinement(domain_hint: str | None) -> dict[str, Any]:
    return _parser_output(
        message_type="business_query", intent_hint="check_order" if domain_hint else None,
        domain_hint=domain_hint, entity_op="replace_combine", order_status="outstanding",
        asks=[], reference_positions=[],
        entities=[_entity("BRW", "warehouse"), _carried_customer_entity()],
    )


def _date_window_refinement(domain_hint: str | None) -> dict[str, Any]:
    return _parser_output(
        message_type="business_query" if domain_hint else "casual",
        intent_hint="check_order" if domain_hint else None,
        domain_hint=domain_hint, entity_op="reuse", asks=[], reference_positions=[],
        broaden_axis="date", date_filter_start="2026-01-01", date_filter_end="2026-12-31",
        user_goal="trying to see 2026 only", entities=[_carried_customer_entity()],
    )


def _all_dates_refinement(domain_hint: str | None) -> dict[str, Any]:
    """"all dates": the date axis WIDENED rather than narrowed, which is the same kind of
    turn - it picks nothing and names only an axis that can never be this report's
    subject."""
    return _parser_output(
        message_type="business_query" if domain_hint else "casual",
        intent_hint="check_order" if domain_hint else None,
        domain_hint=domain_hint, entity_op="reuse", asks=[], reference_positions=[],
        broaden_axis="date", date_mode="all", date_filter_start=None, date_filter_end=None,
        user_goal="trying to see every date", entities=[_carried_customer_entity()],
    )


REFINEMENTS = (
    ("location-only-brw", "only BRW", _location_refinement),
    ("date-in-2026", "in 2026", _date_window_refinement),
    ("all-dates", "all dates", _all_dates_refinement),
)


def _seed_brw_warehouse(session_factory) -> None:
    import uuid as _uuid

    from app.models.inventory import Warehouse

    db = session_factory()
    db.add(
        Warehouse(
            id=str(_uuid.uuid4()), warehouse_code="BRW", warehouse_name="BRW", is_active=True
        )
    )
    db.commit()


@pytest.mark.parametrize("domain_hint", DOMAIN_HINTS, ids=lambda d: f"domain-{d or 'null'}")
@pytest.mark.parametrize("refinement", REFINEMENTS, ids=lambda r: r[0])
def test_a_refinement_narrows_the_report_whatever_word_the_model_stamped(
    refinement, domain_hint, session_factory, monkeypatch
) -> None:
    """AC-1065. A turn that PICKED nothing and names only axes this report can never take
    as its SUBJECT re-runs the same report with the stored filters overlaid, and leaves
    the same question open over the narrower window."""
    name, text_body, build = refinement
    _seed_brw_warehouse(session_factory)
    _seed_open_detail(session_factory, filters=_customer_subject_filters())
    result, calls = _run_turn(
        session_factory, monkeypatch, qf=build(domain_hint), text_body=text_body,
        msg_id=f"ZZT-gr3-{name}-{domain_hint or 'null'}",
        attributes=["sales_orders.outstanding"],
        resolve_services=_exact_services(
            single={
                CARRIED_CUSTOMER_NAME: {
                    "uuid": CARRIED_CUSTOMER_UUID, "entity_type": "customer",
                    "canonical_code": CARRIED_CUSTOMER_NAME, "match_tier": "exact",
                    "company_name": "Sorento",
                }
            }
        ),
        fetch_response=_report_call(REPORT_HIT),
    )
    assert result.status == "done", (result.status, result.error)
    tool_calls = [c for c in calls if not c[0].startswith("probe:")]
    assert len(tool_calls) == 1, (
        f"{name} with domain_hint {domain_hint!r}: the refinement re-runs the SAME report, "
        f"once: {calls!r}"
    )
    tool, args = tool_calls[0]
    assert tool == "crm_outstanding_report", (
        f"{name} with domain_hint {domain_hint!r}: a filter on the open report must not "
        f"become a brand new ask on another lane: {tool}"
    )
    assert args.get("customer_ids") == [CARRIED_CUSTOMER_UUID], (
        f"{name} with domain_hint {domain_hint!r}: the question's own subject survives the "
        f"narrowing: {args!r}"
    )
    assert args.get("scope") == "both", (
        f"{name} with domain_hint {domain_hint!r}: the answered scope survives: {args!r}"
    )
    assert "detail" not in args, (
        f"{name} with domain_hint {domain_hint!r}: a refinement re-runs the REPORT, it "
        f"does not pick a detail list: {args!r}"
    )
    question = _stored_oq(_vars(session_factory))
    assert question.get("kind") == "outstanding_detail", (
        f"{name} with domain_hint {domain_hint!r}: the same question is re-armed over the "
        f"narrower window, never dropped: {question!r}"
    )
    filters_out = _stored_oq_filters(_vars(session_factory))
    assert filters_out.get("customer_ids") == [CARRIED_CUSTOMER_UUID], filters_out


#: Both axes a subject can occupy (R13): this report takes a product OR a customer as its
#: subject, so an entity on either axis names a NEW question however the turn is stamped.
SUBJECTS = (
    ("customer-word", "delivery status for hanlim", ("hanlim", "customer")),
    ("product-code", f"stock for {STOCK_CODE}", (STOCK_CODE, "product")),
)


@pytest.mark.parametrize("domain_hint", DOMAIN_HINTS, ids=lambda d: f"domain-{d or 'null'}")
@pytest.mark.parametrize("subject", SUBJECTS, ids=lambda s: s[0])
def test_a_subject_capable_entity_is_a_new_ask_whatever_word_the_model_stamped(
    subject, domain_hint, session_factory, monkeypatch
) -> None:
    """R24's own case, kept for the reason that was always true of it: a customer or a
    product CAN be this report's subject, so naming one is a new question - and that has
    to hold with `domain_hint` null too, which is the shape R24's classification test
    could not see."""
    name, text_body, (raw, hint) = subject
    _seed_open_detail(
        session_factory,
        filters={
            "product_code": OUTSTANDING_CODE,
            "date_filter_start": None,
            "date_filter_end": None,
            "customer_ids": [],
            "warehouse_codes": [],
            "location_token": None,
            "scope": "so",
        },
    )
    result, calls = _run_turn(
        session_factory, monkeypatch,
        qf=_parser_output(
            message_type="business_query", intent_hint="check_order" if domain_hint else None,
            domain_hint=domain_hint, entity_op="replace_combine", asks=[],
            reference_positions=[], entities=[_entity(raw, hint)],
        ),
        text_body=text_body, msg_id=f"ZZT-gr3-subject-{name}-{domain_hint or 'null'}",
        attributes=["sales_orders.outstanding"],
        resolve_services=_exact_services(
            single={
                raw: {
                    "uuid": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                    "entity_type": hint,
                    "canonical_code": raw,
                    "match_tier": "exact",
                    "company_name": "Sorento",
                }
            }
        ),
        fetch_response=_report_call(REPORT_HIT),
    )
    assert result.status in ("done", "delegated"), (result.status, result.error)
    for tool, args in [c for c in calls if not c[0].startswith("probe:")]:
        assert args.get("product_code") != OUTSTANDING_CODE, (
            f"{name} with domain_hint {domain_hint!r}: the customer named their own "
            f"subject, so the OLD report's product must not be re-run: {tool} {args!r}"
        )
    question = _stored_oq(_vars(session_factory))
    assert question.get("kind") != "outstanding_detail" or _stored_oq_filters(
        _vars(session_factory)
    ).get("product_code") != OUTSTANDING_CODE, (
        f"{name} with domain_hint {domain_hint!r}: a new ask DROPS the old question's "
        f"filter set rather than answering the new ask with it: {question!r}"
    )


# --------------------------------------------------------------------------- #
# GROUP 3b - the four branches that still read `domain_hint`, one decision at a
# time. Driven at the post-processor seam (`output_exchange`, the way
# `test_output_exchange_rules.py` drives it) rather than through a turn, because
# the assertion IS "the same emission, differing only in `domain_hint`, decides
# the same way" - and the seam is where that comparison is exact rather than
# mediated by whatever lane the domain word then selects.
#
# Named sites on this head: `output_exchange.py` ~1618 (`own_question`), ~1461
# (`_outstanding_leaves_the_offer`), ~3904 (the company pick over an open offer),
# ~3643/3666 (the member-offer pick gate).
# --------------------------------------------------------------------------- #

#: The fields that ARE the decision. `domain_hint` and `message_type` are deliberately
#: excluded: the post-processor legitimately rewrites both on a turn it has decided is an
#: answer (it stamps `order` / `business_query` so the lane re-runs the report), so
#: comparing them would compare the inputs rather than the reading.
_DECISION_KEYS = (
    "outstanding_pending_dropped",
    "outstanding_refined",
    "outstanding_answer_applied",
    "outstanding_offer_declined",
    "escalation",
    "member_pick_context",
    "reference_positions",
)

_OPEN_DETAIL_STATE = {
    "open_question": {
        "kind": "outstanding_detail",
        "expects": "pick",
        "options": [
            {"idx": 1, "label": "Sales order list", "value": "so"},
            {"idx": 2, "label": "Delivery order list", "value": "do"},
        ],
        "asked_at_turn": 1,
        "asked_at": None,
        "payload": {
            "filters": {"product_code": OUTSTANDING_CODE, "customer_ids": [], "scope": "so"}
        },
    }
}

_OPEN_MEMBER_STATE = {
    "open_question": {
        "kind": "member_offer",
        "expects": "yes_no",
        "options": [
            {"idx": 1, "label": "Nurain", "uuid": "aaaaaaaa-0000-0000-0000-000000000001"},
            {"idx": 2, "label": "Aina", "uuid": "aaaaaaaa-0000-0000-0000-000000000002"},
        ],
        "asked_at_turn": 1,
        "asked_at": None,
        "payload": {"team": "warehouse"},
    }
}

#: An open plain escalate offer, plus the pool of companies it was made over. The pool
#: rides `routing_companies`, which is one of the keys the five-key session dropped - so
#: this state is the 34-key shape the replay captures carry, handed in directly. The rule
#: under test is about the domain word, and it has to hold wherever the pool comes from.
_OPEN_OFFER_STATE = {
    "open_question": {
        "kind": "team_pick",
        "expects": "yes_no",
        "options": [{"idx": 1, "team": "warehouse", "label": "warehouse"}],
        "asked_at_turn": 1,
        "asked_at": None,
        "payload": {"team": "warehouse"},
    },
    "routing_companies": [{"company_name": "Sorento", "company_code": "SRT"}],
}


def _ox(output: dict[str, Any], *, message: str, state: dict[str, Any]) -> dict[str, Any]:
    return output_exchange(
        {"output": json.dumps(output)},
        {
            "latest_user_message": message,
            "contact_id": "ZZT-general-rules",
            "previous_conversation_state": state,
        },
    )["output"]


def _decline_emission(domain_hint: str | None) -> dict[str, Any]:
    return _parser_output(
        message_type="business_query" if domain_hint else "casual", intent_hint=None,
        domain_hint=domain_hint, entity_op="reuse", is_affirmative=False,
        reference_positions=[], entities=[_carried_customer_entity()],
    )


def _unreadable_emission(domain_hint: str | None) -> dict[str, Any]:
    return _parser_output(
        message_type="business_query" if domain_hint else "casual", intent_hint=None,
        domain_hint=domain_hint, entity_op="clear", reference_positions=[], entities=[],
    )


def _member_pick_emission(domain_hint: str | None) -> dict[str, Any]:
    return _parser_output(
        message_type="business_query" if domain_hint else "casual", intent_hint=None,
        domain_hint=domain_hint, entity_op="reuse", reference_positions=[2], entities=[],
    )


def _company_word_emission(domain_hint: str | None) -> dict[str, Any]:
    return _parser_output(
        message_type="business_query" if domain_hint else "casual", intent_hint=None,
        domain_hint=domain_hint, entity_op="reuse", reference_positions=[], entities=[],
    )


DOMAIN_BLIND_DECISIONS = (
    ("a-decline-under-an-open-report", "no", _OPEN_DETAIL_STATE, _decline_emission),
    ("an-unreadable-turn-under-an-open-report", "hi", _OPEN_DETAIL_STATE, _unreadable_emission),
    ("a-numbered-pick-over-a-member-offer", "2", _OPEN_MEMBER_STATE, _member_pick_emission),
    ("a-company-word-over-an-open-offer", "sorento", _OPEN_OFFER_STATE, _company_word_emission),
)


@pytest.mark.parametrize(
    ("case_id", "message", "state", "build"), DOMAIN_BLIND_DECISIONS, ids=lambda x: x if isinstance(x, str) else ""
)
def test_the_reading_of_a_turn_does_not_change_with_the_domain_word(
    case_id, message, state, build
) -> None:
    """One emission, two stampings, one reading (AC-1065's general half).

    R-B and R-H both came down to this: the model's domain word is a hint about LANGUAGE,
    and four decisions about what an answer MEANS read it as if it were a statement about
    intent. The customer's own sentence is identical in both runs below.
    """
    without = _ox(build(None), message=message, state=state)
    with_word = _ox(build("order"), message=message, state=state)
    differ = {
        key: (without.get(key), with_word.get(key))
        for key in _DECISION_KEYS
        if without.get(key) != with_word.get(key)
    }
    assert not differ, (
        f"{case_id}: the same message read two ways depending on whether the model "
        f"stamped a domain word - {differ!r}"
    )


# =========================================================================== #
# GROUP 4 - the reviewer's own findings on 9d5b66dd1, as behaviour
#
# Every one of these stayed GREEN under a kill test of the hunk it belongs to, which is
# the reviewer's point: the hunk is right and nothing grades it, so the rewrite below can
# take it away silently. Three are guards (S2a, S2b, S2c) and two are reds (B2, S1).
# =========================================================================== #


def test_s2a_an_off_axis_keep_reaches_the_pick_turns_own_entities(
    session_factory, monkeypatch
) -> None:
    """S2a (`output_exchange.py:1229-1239`, `kept_off_axis`): an `Outcome.keep` member on
    an axis with NO focus slot must reach `o["entities"]` on the pick turn.

    `attachment_type` is the only such axis today, and it is R-C's own live symptom:
    "photo for srtwc286" then "4" re-asked "Please provide the attachment type" for the
    type the same message had already named. Graded end to end - the pick turn's reply
    has to name the type - because that is what the customer sees, and because the keep
    channel is being re-pointed at `keep_entities` in this round.
    """
    _reply, services = _build_attachment_arm(session_factory, monkeypatch, "s2a")
    result, calls = _run_turn(
        session_factory, monkeypatch, qf=_pick_v1(4), text_body="4",
        msg_id="ZZT-gr4-s2a-pick", resolve_services=services,
    )
    assert result.status == "done", (result.status, result.error)
    reply = (result.reply or {}).get("text") or ""
    assert "Product Photos" in reply, (
        f"the attachment type the SAME message named must survive the product pick - the "
        f"pick turn otherwise re-asks for it: {reply!r}"
    )
    assert "provide the attachment type" not in reply.lower(), reply
    emission = ((result.ctx or {}).get("parse") or {}).get("output") or {}
    hints = {
        str(e.get("hint")) for e in (emission.get("entities") or []) if isinstance(e, dict)
    }
    assert "attachment_type" in hints, (
        f"an off-axis keep has nowhere to live but the emission's own entity list: "
        f"{emission.get('entities')!r}"
    )
    assert calls, "the pick must re-run the attachment lookup"


def test_s2b_the_gates_customer_rows_carry_every_ledger_of_a_family(self=None) -> None:
    """S2b (`gate.py:1044-1046`): one rendered line can stand for accounts in more than
    one ledger ("CHIN CHUN HARDWARE SDN BHD (SRT, MCH)"), and the ROW is what carries the
    family - graded on `run_gate`'s own output, not on `_entity_of`, because the row is
    where the two ledgers are still known to belong together.
    """
    from app.services.chatbot.lanes.business.gate import run_gate

    rows = [
        {
            "uuid": "060f4eaf-88ca-486a-a203-b0b61eeb9cd8", "entity_type": "customer",
            "canonical_code": "300-C043", "match_tier": "trgm", "company_name": "Sorento",
            "company_code": "SRT",
            "display": {"customer_name": "CHIN CHUN HARDWARE SDN BHD - [A/C I]"},
        },
        {
            "uuid": "13eb525b-985c-44a5-abc4-4be5c7db6cd6", "entity_type": "customer",
            "canonical_code": "300-C125", "match_tier": "trgm", "company_name": "Mocha",
            "company_code": "MCH",
            "display": {"customer_name": "CHIN CHUN HARDWARE SDN BHD - [CERAMIC]"},
        },
        {
            "uuid": "fa32b334-fc47-4bec-96db-f0f59a4bcb0f", "entity_type": "customer",
            "canonical_code": "300-C001", "match_tier": "trgm", "company_name": "Sorento",
            "company_code": "SRT",
            "display": {"customer_name": "CHIN CHUN HOMEMART SDN BHD"},
        },
    ]
    resolver = {
        "tokens": ["chin chun"],
        "resolutions": [{"token": "chin chun", "resolved": False, "matches": rows}],
        "unresolved_tokens": [],
    }
    out = run_gate(
        dict(resolver),
        parser={
            "domain_hint": "order",
            "entities": [{"hint": "customer", "raw": "chin chun", "current_message": True}],
        },
        resolver=resolver,
    )
    assert out["require_specific"] is True, out.get("gate_reason")
    assert "CHIN CHUN HARDWARE SDN BHD (SRT, MCH)" in (out.get("gate_clarification") or ""), (
        f"the line the customer reads names every ledger it stands for: "
        f"{out.get('gate_clarification')!r}"
    )
    family = out["compatible_entities"][0].get("family_uuids")
    assert family == [rows[0]["uuid"], rows[1]["uuid"]], (
        f"the picked row has to reach BOTH ledgers, so the row carries both uuids in "
        f"first-seen order: {out['compatible_entities']!r}"
    )


def test_s2c_the_persisted_roster_row_keeps_its_family(session_factory, monkeypatch) -> None:
    """S2c (`compile_state.py:1040-1043`): the family survives the INDEXING the tail does
    when it freezes the roster onto the question.

    No capture can cover this - a recorded `ctx` carries the `picker_families` map this
    replaces - so it is driven through the real port: two ledgers in, one numbered line
    out, both uuids on the persisted option row.
    """
    _seed_contact(session_factory, variables={})
    two_ledger = [
        {
            "uuid": "060f4eaf-88ca-486a-a203-b0b61eeb9cd8", "entity_type": "customer",
            "canonical_code": "300-C043", "match_tier": "trgm", "company_name": "Sorento",
            "company_code": "SRT",
            "display": {"customer_name": "CHIN CHUN HARDWARE SDN BHD - [A/C I]"},
        },
        {
            "uuid": "13eb525b-985c-44a5-abc4-4be5c7db6cd6", "entity_type": "customer",
            "canonical_code": "300-C125", "match_tier": "trgm", "company_name": "Mocha",
            "company_code": "MCH",
            "display": {"customer_name": "CHIN CHUN HARDWARE SDN BHD - [CERAMIC]"},
        },
        {
            "uuid": "fa32b334-fc47-4bec-96db-f0f59a4bcb0f", "entity_type": "customer",
            "canonical_code": "300-C001", "match_tier": "trgm", "company_name": "Sorento",
            "company_code": "SRT",
            "display": {"customer_name": "CHIN CHUN HOMEMART SDN BHD"},
        },
    ]
    services = _exact_services(multi={"chin chun": two_ledger})
    result, _calls = _run_turn(
        session_factory, monkeypatch,
        qf=_qf([_entity("chin chun", "customer")], domain="order", intent_hint="check_order"),
        text_body="orders for chin chun", msg_id="ZZT-gr4-s2c",
        resolve_services=services,
    )
    reply = (result.reply or {}).get("text") or ""
    assert "(SRT, MCH)" in reply, reply
    options = _stored_oq_options(_vars(session_factory))
    assert options, f"the roster must be frozen onto the question: {reply!r}"
    assert options[0].get("family_uuids") == [
        two_ledger[0]["uuid"], two_ledger[1]["uuid"]
    ], (
        f"the indexed row the tail persisted lost the family the gate computed, so the "
        f"pick reaches one ledger of the two the line promised: {options[0]!r}"
    )


@pytest.mark.parametrize("domain_hint", (None, "order"), ids=lambda d: f"domain-{d or 'null'}")
def test_b2_a_decline_closes_the_open_report_and_fetches_nothing(
    domain_hint, session_factory, monkeypatch
) -> None:
    """B2 (reviewer, 9d5b66dd1): a `no` under an open outstanding question is the customer
    LEAVING it (R22's own way out), not a filter on it.

    Measured on this head: `_outstanding_keeps_subject` sees `entity_op: reuse` and the
    question's own carried subject in `entities`, calls the turn a refinement, and re-runs
    the whole report - so "no" is answered with the very report the customer just declined.
    Both stampings, because the reading may not depend on the domain word either.
    """
    _seed_open_detail(session_factory, filters=_customer_subject_filters())
    result, calls = _run_turn(
        session_factory, monkeypatch, qf=_decline_emission(domain_hint), text_body="no",
        msg_id=f"ZZT-gr4-b2-{domain_hint or 'null'}",
        attributes=["sales_orders.outstanding"],
        resolve_services=_exact_services(
            single={
                CARRIED_CUSTOMER_NAME: {
                    "uuid": CARRIED_CUSTOMER_UUID, "entity_type": "customer",
                    "canonical_code": CARRIED_CUSTOMER_NAME, "match_tier": "exact",
                    "company_name": "Sorento",
                }
            }
        ),
        fetch_response=_report_call(REPORT_HIT),
    )
    assert result.status in ("done", "delegated"), (result.status, result.error)
    tool_calls = [c for c in calls if not c[0].startswith("probe:")]
    assert tool_calls == [], (
        f"a decline is answered with one closing line, not with the report again "
        f"(domain_hint {domain_hint!r}): {tool_calls!r}"
    )
    question = _stored_oq(_vars(session_factory))
    assert question.get("kind") != "outstanding_detail", (
        f"the question the customer declined must close (domain_hint {domain_hint!r}): "
        f"{question!r}"
    )


@pytest.mark.parametrize("domain_hint", (None, "order"), ids=lambda d: f"domain-{d or 'null'}")
def test_s1_a_this_turn_entity_with_a_null_current_message_is_still_this_turns_ask(
    domain_hint, session_factory, monkeypatch
) -> None:
    """S1 (reviewer, 9d5b66dd1): `current_message` is nullable in the parser schema, and
    `_outstanding_keeps_subject` grades `is not True` - so a customer entity the turn
    really did name, emitted with a null flag, reads as the question's own carried subject
    and the refinement arm answers a NEW ask with the OLD product's report.

    "delivery status for hanlim" under a product-subject offer, with the flag left null.
    """
    _seed_open_detail(
        session_factory,
        filters={
            "product_code": OUTSTANDING_CODE,
            "date_filter_start": None,
            "date_filter_end": None,
            "customer_ids": [],
            "warehouse_codes": [],
            "location_token": None,
            "scope": "so",
        },
    )
    result, calls = _run_turn(
        session_factory, monkeypatch,
        qf=_parser_output(
            message_type="business_query", intent_hint="check_order" if domain_hint else None,
            domain_hint=domain_hint, entity_op="replace_combine", asks=[],
            reference_positions=[],
            entities=[
                {
                    "raw": "hanlim", "hint": "customer", "canonical_code": None,
                    # THE SCHEMA ALLOWS NULL, and the live model emits it.
                    "current_message": None, "confident": True,
                }
            ],
        ),
        text_body="delivery status for hanlim", msg_id=f"ZZT-gr4-s1-{domain_hint or 'null'}",
        attributes=["sales_orders.outstanding"],
        resolve_services=_exact_services(
            single={
                "hanlim": {
                    "uuid": "cccccccc-cccc-cccc-cccc-cccccccccccc", "entity_type": "customer",
                    "canonical_code": "HANLIM", "match_tier": "exact", "company_name": "Sorento",
                }
            }
        ),
        fetch_response=_report_call(REPORT_HIT),
    )
    assert result.status in ("done", "delegated"), (result.status, result.error)
    for tool, args in [c for c in calls if not c[0].startswith("probe:")]:
        assert args.get("product_code") != OUTSTANDING_CODE, (
            f"the customer named their own subject, so the OLD product's report must not "
            f"be what answers them (domain_hint {domain_hint!r}): {tool} {args!r}"
        )


# --------------------------------------------------------------------------- #
# GROUP 1c - the LANE's own read of the team, at the point it is chosen
#
# The tests above grade the `add_comment` TEXT, which is the customer's case as the
# person picking it up reads it. This one grades the INPUT to the writer, because that
# is where the wrong team is chosen and it is the only place a fix can be pinned
# unambiguously: `lanes/escalation._assignment_actions(ctx, team, ...)` composes BOTH
# the comment ("Team: <slug>", `_comment_text`) and the closing sentence
# ("... from <team> team", `ROUTED_TO_PIC_REPLY`) from that one argument, and `team`
# reaches it as `escalation_context(...)["team"]` =
# `ctx.parse.output.routing.suggested_team` (escalation.py:197).
#
# So the whole chain is: the offer records a team -> the answer resolves the offer and
# writes that team onto `routing.suggested_team` -> the lane reads it there. A break
# anywhere in it shows up as this one argument, whichever end the coder repairs.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class TeamCase:
    id: str
    #: The team the OFFER the customer answered had recorded.
    team: str
    lanes: tuple[str, ...]
    #: `(session_factory, monkeypatch, tag) -> resolve_services`
    setup: Callable[..., ResolveGateServices | None]


def _setup_standalone_offer(session_factory, monkeypatch, tag: str):
    _reply, services = _build_miss_arm(session_factory, monkeypatch, tag)
    return services


def _setup_riding_offer(session_factory, monkeypatch, tag: str):
    _reply, services = _build_customer_picker_arm(session_factory, monkeypatch, tag)
    return services


def _setup_member_offer(session_factory, monkeypatch, tag: str):
    """A member offer is an escalation offer with a roster attached (`offer_is_open`
    reads both kinds), and it carries its own team on `payload.team`."""
    _seed_contact(
        session_factory,
        variables={
            "open_question": {
                "kind": "member_offer",
                "options": [
                    {"idx": 1, "label": "Nurain", "uuid": "aaaaaaaa-0000-0000-0000-000000000001"},
                    {"idx": 2, "label": "Aina", "uuid": "aaaaaaaa-0000-0000-0000-000000000002"},
                ],
                "expects": "yes_no",
                "asked_at_turn": 1,
                "asked_at": None,
                "payload": {"team": "warehouse", "domain": "inventory"},
            }
        },
    )
    return None


TEAM_CASES: tuple[TeamCase, ...] = (
    TeamCase("standalone-offer", team="warehouse", lanes=LANES, setup=_setup_standalone_offer),
    TeamCase(
        "riding-offer", team="customer_service", lanes=LANES, setup=_setup_riding_offer
    ),
    TeamCase("member-offer", team="warehouse", lanes=LANES, setup=_setup_member_offer),
)


@pytest.mark.parametrize("case", TEAM_CASES, ids=lambda c: c.id)
def test_the_escalation_lane_is_handed_the_offers_own_team(
    case, session_factory, monkeypatch
) -> None:
    """The team the lane ASSIGNS is the team the offer promised.

    Measured on this head for the member offer: the emission the lane is handed comes back
    with the offer resolved (handler `member_offer`, `escalate: True`,
    `routing.suggested_team: warehouse`) and the case is still filed against
    `customer_service` - so a later reader of the team is overwriting or ignoring the
    answer's own routing before `_assignment_actions` sees it. Asserted on that argument,
    so the red names the seam rather than the symptom, and on both strings built from it,
    so a fix that repairs one and not the other cannot pass.
    """
    from app.services.chatbot.lanes import escalation as escalation_mod

    services = case.setup(session_factory, monkeypatch, "lane-team")

    handed: list[Any] = []
    original = escalation_mod._assignment_actions

    def _recording(ctx, team, **kwargs):
        handed.append(team)
        return original(ctx, team, **kwargs)

    monkeypatch.setattr(escalation_mod, "_assignment_actions", _recording)

    result, _calls = _run_turn(
        session_factory, monkeypatch, qf=_yes_v1(), text_body="yes",
        msg_id=f"ZZT-gr1c-{case.id}", resolve_services=services, lanes=case.lanes,
        is_test=True,
    )
    assert result.status == "done", (result.status, result.error)
    assert handed, (
        f"{case.id}: a 'yes' to an open offer must reach the lane's assignment arm - "
        f"nothing built the four actions: {result.actions!r}"
    )
    assert handed == [case.team], (
        f"{case.id}: the offer promised {case.team!r} and the escalation lane was handed "
        f"{handed!r} to file the case under"
    )
    assert _comment_teams(result) == [case.team], (
        f"{case.id}: the triage note is what the person picking the case up searches by: "
        f"{result.actions!r}"
    )
    closing = " ".join(
        str(a.get("text") or "")
        for a in (result.actions or [])
        if isinstance(a, dict) and a.get("kind") == "send_message"
    )
    assert f"from {_pretty(case.team)} team" in closing, (
        f"{case.id}: the customer is told which team has it, and it has to be the one the "
        f"offer named: {closing!r}"
    )


# =========================================================================== #
# GROUP 5 - WHEN A TURN BOTH ANSWERS AND ASKS, THE ASK WINS (AC-1062, chain e)
#
# Owner chain e on `sorento_ai_automation_focus_full`, 15 Sep 2026:
#
#   turn b4863e5d "DO outstanding for chin chun"  -> the customer picker
#   turn a509fbb0 "1"                             -> printed the six-ledger header AND
#                                                    "Outstanding for which document?",
#                                                    but PERSISTED `customer_pick` again
#   turn add34025 "1"                             -> only now armed `outstanding_scope`
#
# Two rules meet on that middle turn. D19 rule 1 says a roster survives its own pick;
# `_ask_for_turn` says the question THIS turn asked is what persists. The reply printed
# the scope question, so that is the question the customer is looking at - and the rule
# the coder is implementing is that the ask wins, always, over the roster that was merely
# answered.
#
# **Reproduction, stated plainly**: driven through this harness on the coder's head, every
# pick-emission shape measured (v1 `reference_positions`, v3 `answers_open_question.picks`,
# `entity_op` reuse / replace_combine, with and without `requested_attributes`, message_type
# casual / business_query) prints AND persists `outstanding_scope` correctly. The live
# defect did not reproduce from the emission alone, so these are written as the RULE rather
# than as a repro of that one turn, and the one shape that IS red here is the one the
# measurement found: a pick that arrives UNSTAMPED (no domain word, no order status - what
# the model emits when it reads the turn as nothing but an answer) loses the outstanding
# ask entirely and runs the plain order list.
#
# Red (1) is a GUARD on the emission, not on the phrase (the parser gap - v20 emitted a
# bare `order_status: "outstanding"` for "DO outstanding" - is the prompt's own half, and
# `test_outstanding_lane::TestScopeWordsBind` / `TestPromptTeachesScopeWordsInsideLongerSentences`
# hold it): GIVEN `do_outstanding` / `so_outstanding` / `outstanding_both`, the scope
# question must never be asked and the report runs at that scope.
# =========================================================================== #

#: `order_status` -> the `scope` the report must run at, from `_SCOPE_BY_ORDER_STATUS`.
PRE_SCOPED = (("do_outstanding", "do"), ("so_outstanding", "so"), ("outstanding_both", "both"))

#: The four ways a number reaches the engine, all four of which must resolve the same
#: question. `v1-stamped` is the live v20 shape (the model stamps the domain and the
#: status back onto a bare "1" - R-B's own note); `v1-unstamped` is the same prompt
#: reading the turn as a pure answer (`entity_op: reuse`); `v1-replace` is that same
#: answer emitted with `entity_op: replace_combine`, which is what R-D's own live pick
#: turn carried (d5851ed2: "the pick emitted `entity_op: replace` with the customer
#: alone") and what `ParseOutput`'s default is; `v3` is this lane's own parser.
ANSWER_CHANNELS = ("v1-stamped", "v1-unstamped", "v1-replace", "v3")


def _outstanding_ask_qf(status: str, *, customer_raw: str, v3: bool = False) -> dict[str, Any]:
    qf = _qf(
        [_entity(customer_raw, "customer")], domain="order", intent_hint="check_order",
        order_status=status, entity_op="replace_combine",
    )
    if v3:
        qf["answers_open_question"] = {
            "resolved": False, "picks": [], "yes_no": None, "free_text": None,
        }
        qf["anaphora"] = False
        qf["topic_reset"] = False
    return qf


def _numbered_answer_qf(position: int, *, channel: str, status: str) -> dict[str, Any]:
    """A bare number, in each of the three shapes the engine has to read it in."""
    if channel == "v3":
        return _parser_output(
            message_type="business_query", intent_hint="check_order", domain_hint="order",
            order_status=status, entity_op="reuse", entities=[], asks=[],
            reference_positions=[],
            answers_open_question={
                "resolved": True, "picks": [position], "yes_no": None, "free_text": None,
            },
            anaphora=False, topic_reset=False,
        )
    if channel == "v1-stamped":
        return _parser_output(
            message_type="business_query", intent_hint="check_order", domain_hint="order",
            order_status=status, entity_op="reuse", entities=[], asks=[],
            reference_positions=[position],
        )
    return _parser_output(
        message_type="casual", intent_hint=None, domain_hint=None, entities=[], asks=[],
        entity_op="reuse" if channel == "v1-unstamped" else "replace_combine",
        reference_positions=[position],
    )


def _report_tool_calls(calls: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    return [args for name, args in calls if name == "crm_outstanding_report"]


def _other_tool_calls(calls: list[tuple[str, dict[str, Any]]]) -> list[str]:
    return [
        name
        for name, _args in calls
        if not name.startswith("probe:") and name != "crm_outstanding_report"
    ]


@pytest.mark.parametrize(("status", "scope"), PRE_SCOPED, ids=lambda x: x)
def test_a_pre_scoped_outstanding_ask_never_asks_the_scope_question(
    status, scope, session_factory, monkeypatch
) -> None:
    """Red (1), the no-picker half: the document type was named, so there is nothing to
    ask. #862's own pre-scoping, guarded per status rather than per phrase."""
    _seed_contact(session_factory, variables={})
    services = _exact_services(
        single={
            "hanlim": {
                "uuid": CARRIED_CUSTOMER_UUID, "entity_type": "customer",
                "canonical_code": "HANLIM", "match_tier": "exact", "company_name": "Sorento",
            }
        }
    )
    result, calls = _run_turn(
        session_factory, monkeypatch,
        qf=_outstanding_ask_qf(status, customer_raw="hanlim"),
        text_body=f"{status} for hanlim", msg_id=f"ZZT-gr5-prescoped-{status}",
        attributes=["sales_orders.outstanding"], resolve_services=services,
        fetch_response=_report_call(REPORT_HIT),
    )
    assert result.status == "done", (result.status, result.error)
    reply = (result.reply or {}).get("text") or ""
    assert "Outstanding for which document?" not in reply, (
        f"{status} names the document type, so the scope question is answered before it "
        f"is asked: {reply!r}"
    )
    reports = _report_tool_calls(calls)
    assert len(reports) == 1, f"{status}: one report call: {calls!r}"
    assert reports[0].get("scope") == scope, (
        f"{status} must run the report at scope {scope!r}: {reports[0]!r}"
    )
    question = _stored_oq(_final_vars(session_factory, result))
    assert question.get("kind") != "outstanding_scope", (
        f"{status}: nothing is left to ask about the document type: {question!r}"
    )


@pytest.mark.parametrize("channel", ANSWER_CHANNELS, ids=lambda c: c)
@pytest.mark.parametrize(("status", "scope"), PRE_SCOPED, ids=lambda x: x)
def test_a_pre_scoped_ask_keeps_its_scope_across_a_customer_picker(
    status, scope, channel, session_factory, monkeypatch
) -> None:
    """Red (1), the picker half, which is chain e's own first two turns: the document type
    named in the ORIGINAL message has to survive the pick, so the pick answers with the
    report at that scope and still never asks which document.

    Measured red on `v1-unstamped`: a pick the model reads as a pure answer loses the
    outstanding ask altogether and the turn runs the plain order list.
    """
    _seed_contact(session_factory, variables={})
    services = _exact_services(multi={"chin chun": _customer_rows()})
    _run_turn(
        session_factory, monkeypatch,
        qf=_outstanding_ask_qf(status, customer_raw="chin chun", v3=channel == "v3"),
        text_body=f"{status} for chin chun",
        msg_id=f"ZZT-gr5-picker-{status}-{channel}-arm",
        attributes=["sales_orders.outstanding"], resolve_services=services,
        emits_v3=channel == "v3", fetch_response=_report_call(REPORT_HIT),
    )
    result, calls = _run_turn(
        session_factory, monkeypatch,
        qf=_numbered_answer_qf(1, channel=channel, status=status), text_body="1",
        msg_id=f"ZZT-gr5-picker-{status}-{channel}-pick",
        attributes=["sales_orders.outstanding"], resolve_services=services,
        emits_v3=channel == "v3", fetch_response=_report_call(REPORT_HIT),
    )
    assert result.status == "done", (result.status, result.error)
    reply = (result.reply or {}).get("text") or ""
    assert "Outstanding for which document?" not in reply, (
        f"{status} / {channel}: the document type was named before the picker and must "
        f"survive it: {reply!r}"
    )
    assert _other_tool_calls(calls) == [], (
        f"{status} / {channel}: the pick resumes the OUTSTANDING ask, so nothing else may "
        f"answer it: {calls!r}"
    )
    reports = _report_tool_calls(calls)
    assert len(reports) == 1, (
        f"{status} / {channel}: the pick runs the report once: {calls!r}"
    )
    assert reports[0].get("scope") == scope, (
        f"{status} / {channel}: at the scope the first message named: {reports[0]!r}"
    )
    assert reports[0].get("customer_ids") == [CHIN_CHUN[0][0]], (
        f"{status} / {channel}: for the customer the pick chose: {reports[0]!r}"
    )


@pytest.mark.parametrize("channel", ANSWER_CHANNELS, ids=lambda c: c)
class TestTheQuestionAPickTurnAsksIsTheOneThatPersists:
    """Red (2): the general rule, on both kinds a pick turn can newly ask.

    The reply is the contract. A turn that answers the roster AND asks a new question has
    put the new question on the customer's screen, so that is what the next message
    answers - and the roster it merely picked from cannot outlive it by surviving into the
    persisted slot (D19 rule 1 is about a roster nothing newer replaced).
    """

    def _arm_and_pick(self, session_factory, monkeypatch, *, status: str, channel: str, tag: str):
        _seed_contact(session_factory, variables={})
        services = _exact_services(multi={"chin chun": _customer_rows()})
        _run_turn(
            session_factory, monkeypatch,
            qf=_outstanding_ask_qf(status, customer_raw="chin chun", v3=channel == "v3"),
            text_body=f"{status} for chin chun", msg_id=f"ZZT-gr5-{tag}-{channel}-arm",
            attributes=["sales_orders.outstanding"], resolve_services=services,
            emits_v3=channel == "v3", fetch_response=_report_call(REPORT_HIT),
        )
        result, calls = _run_turn(
            session_factory, monkeypatch,
            qf=_numbered_answer_qf(1, channel=channel, status=status), text_body="1",
            msg_id=f"ZZT-gr5-{tag}-{channel}-pick",
            attributes=["sales_orders.outstanding"], resolve_services=services,
            emits_v3=channel == "v3", fetch_response=_report_call(REPORT_HIT),
        )
        return result, calls, services

    def test_a_pick_turn_that_asks_the_scope_question_persists_it(
        self, channel, session_factory, monkeypatch
    ) -> None:
        """Chain e's middle turn: a BARE `outstanding` ask, so the pick turn has to ask
        which document - and what it asked is what has to be waiting for the next number.
        """
        result, _calls, _services = self._arm_and_pick(
            session_factory, monkeypatch, status="outstanding", channel=channel, tag="scope"
        )
        assert result.status == "done", (result.status, result.error)
        reply = (result.reply or {}).get("text") or ""
        assert "Outstanding for which document?" in reply, (
            f"{channel}: a bare outstanding ask still needs its document type: {reply!r}"
        )
        question = _stored_oq(_final_vars(session_factory, result))
        assert question.get("kind") == "outstanding_scope", (
            f"{channel}: the reply asked the scope question, so the roster it picked FROM "
            f"must not be what is left waiting for the next number: {question!r}"
        )
        assert len(question.get("options") or []) == 3, question

    def test_a_pick_turn_that_asks_the_detail_question_persists_it(
        self, channel, session_factory, monkeypatch
    ) -> None:
        """The same rule on the other kind: the scope was already known, so the pick turn
        ANSWERS with the report and asks the detail question instead."""
        result, calls, _services = self._arm_and_pick(
            session_factory, monkeypatch, status="do_outstanding", channel=channel,
            tag="detail",
        )
        assert result.status == "done", (result.status, result.error)
        assert _report_tool_calls(calls), f"{channel}: the pick runs the report: {calls!r}"
        question = _stored_oq(_final_vars(session_factory, result))
        assert question.get("kind") == "outstanding_detail", (
            f"{channel}: the reply offered the detail list, so that is the question the "
            f"next number answers: {question!r}"
        )


@pytest.mark.parametrize("channel", ANSWER_CHANNELS, ids=lambda c: c)
@pytest.mark.parametrize(
    ("position", "scope"), ((1, "so"), (2, "do"), (3, "both")), ids=lambda x: str(x)
)
def test_a_numbered_answer_to_the_scope_question_resolves_after_a_customer_pick(
    position, scope, channel, session_factory, monkeypatch
) -> None:
    """Red (2)'s second half, chain e's third turn: the number the customer types against
    the question the previous turn asked has to RESOLVE - the report at that scope, and no
    third printing of the same three options."""
    _seed_contact(session_factory, variables={})
    services = _exact_services(multi={"chin chun": _customer_rows()})
    _run_turn(
        session_factory, monkeypatch,
        qf=_outstanding_ask_qf("outstanding", customer_raw="chin chun", v3=channel == "v3"),
        text_body="outstanding for chin chun",
        msg_id=f"ZZT-gr5-answer-{position}-{channel}-arm",
        attributes=["sales_orders.outstanding"], resolve_services=services,
        emits_v3=channel == "v3", fetch_response=_report_call(REPORT_HIT),
    )
    _run_turn(
        session_factory, monkeypatch,
        qf=_numbered_answer_qf(1, channel=channel, status="outstanding"), text_body="1",
        msg_id=f"ZZT-gr5-answer-{position}-{channel}-pick",
        attributes=["sales_orders.outstanding"], resolve_services=services,
        emits_v3=channel == "v3", fetch_response=_report_call(REPORT_HIT),
    )
    result, calls = _run_turn(
        session_factory, monkeypatch,
        qf=_numbered_answer_qf(position, channel=channel, status="outstanding"),
        text_body=str(position),
        msg_id=f"ZZT-gr5-answer-{position}-{channel}-scope",
        attributes=["sales_orders.outstanding"], resolve_services=services,
        emits_v3=channel == "v3", fetch_response=_report_call(REPORT_HIT),
    )
    assert result.status == "done", (result.status, result.error)
    reply = (result.reply or {}).get("text") or ""
    assert "Outstanding for which document?" not in reply, (
        f"{position} / {channel}: the customer answered the question - printing it a "
        f"third time is how chain e's owner could not leave it: {reply!r}"
    )
    reports = _report_tool_calls(calls)
    assert len(reports) == 1, f"{position} / {channel}: one report call: {calls!r}"
    assert reports[0].get("scope") == scope, (
        f"{position} / {channel}: '{position}' is the {scope!r} scope: {reports[0]!r}"
    )
    assert reports[0].get("customer_ids") == [CHIN_CHUN[0][0]], (
        f"{position} / {channel}: the customer the pick chose two turns ago is still the "
        f"report's subject: {reports[0]!r}"
    )


# =========================================================================== #
# GROUP 6 - the re-review's two blockers, and guards for the hunks the kill
# test found unguarded (reviewer, 15 Sep 2026, on the general-rule round)
# =========================================================================== #


def _decline_with_a_new_ask_qf(
    domain_hint: str | None, *, raw: str, hint: str
) -> dict[str, Any]:
    """"no, check stock SRTWT2634": a decline AND a question of its own, in one message.

    `is_affirmative: False` is the parser's own decline signal, and the entity is
    `current_message: True` - the customer named a new subject in the same breath.
    """
    return _parser_output(
        message_type="business_query",
        intent_hint="check_stock" if domain_hint == "inventory" else None,
        domain_hint=domain_hint, entity_op="replace_combine", is_affirmative=False,
        reference_positions=[], asks=[],
        entities=[_entity(raw, hint)],
    )


_NEW_SUBJECTS = (
    ("product", STOCK_CODE, "product", STOCK_UUID),
    ("customer", "hanlim", "customer", CARRIED_CUSTOMER_UUID),
)


@pytest.mark.parametrize("domain_hint", (None, "inventory"), ids=lambda d: f"domain-{d or 'null'}")
@pytest.mark.parametrize(
    ("subject_id", "raw", "hint", "uuid"), _NEW_SUBJECTS, ids=lambda x: str(x)
)
def test_b1_a_decline_that_brings_its_own_question_is_answered_not_just_acknowledged(
    subject_id, raw, hint, uuid, domain_hint, session_factory, monkeypatch
) -> None:
    """B1 (reviewer, NEW regression on the general-rule round): "no, check stock
    SRTWT2634" over an open outstanding question is a decline AND an ask.

    R22(a)'s way out reads `is_affirmative: False` on a turn that "picked nothing, named
    nothing and refined nothing" and answers with one line from the registry's
    `offer_declined` key ("Okay, noted.", `lanes/business/__init__._outstanding_offer_closed`).
    A turn that names its OWN subject is not that turn: closing the question is right, and
    stopping there leaves the customer's actual question unanswered.
    """
    _seed_open_detail(session_factory, filters=_customer_subject_filters())
    result, calls = _run_turn(
        session_factory, monkeypatch,
        qf=_decline_with_a_new_ask_qf(domain_hint, raw=raw, hint=hint),
        text_body=f"no, check stock {raw}",
        msg_id=f"ZZT-gr6-b1-{subject_id}-{domain_hint or 'null'}",
        attributes=["sales_orders.outstanding"],
        resolve_services=_exact_services(
            single={
                raw: {
                    "uuid": uuid, "entity_type": hint, "canonical_code": raw,
                    "match_tier": "exact", "company_name": "Sorento",
                }
            }
        ),
        fetch_response=_report_call(REPORT_HIT),
    )
    assert result.status in ("done", "delegated"), (result.status, result.error)
    reply = (result.reply or {}).get("text") or ""
    assert "Okay, noted." not in reply, (
        f"{subject_id} / {domain_hint!r}: the customer declined the offer AND asked "
        f"something - acknowledging the decline is not an answer to the question: {reply!r}"
    )
    tool_calls = [c for c in calls if not c[0].startswith("probe:")]
    assert tool_calls, (
        f"{subject_id} / {domain_hint!r}: the new subject must reach a tool - nothing ran: "
        f"{calls!r}"
    )
    for name, args in tool_calls:
        assert not (
            name == "crm_outstanding_report" and args.get("product_code") == PRODUCT_CODE_IN_OFFER
        ), (
            f"{subject_id} / {domain_hint!r}: the declined report must not be what answers "
            f"the new ask: {name} {args!r}"
        )
    if domain_hint == "inventory" and hint == "product":
        assert [name for name, _a in tool_calls] == ["crm_inventory_stock_balance_list"], (
            f"a stock ask is answered by the stock tool: {tool_calls!r}"
        )
    question = _stored_oq(_final_vars(session_factory, result))
    assert question.get("kind") != "outstanding_detail", (
        f"{subject_id} / {domain_hint!r}: the declined question still closes: {question!r}"
    )


#: The product the seeded offer is about, so B1 can assert the OLD report is not re-run.
PRODUCT_CODE_IN_OFFER = OUTSTANDING_CODE


@pytest.mark.parametrize(
    "domain_hint", (None, "order", "inventory"), ids=lambda d: f"domain-{d or 'null'}"
)
def test_b2_a_bare_no_closes_the_open_outstanding_question(
    domain_hint, session_factory, monkeypatch
) -> None:
    """B2 (reviewer): the fifth matrix cell - a bare "no" whose emission carries NO
    entities at all.

    The decline case earlier in this file carries the question's own subject on `entities`
    with `current_message: False` (the live R-H shape), which is a different turn: this one
    names nothing whatsoever, which is R22(a)'s own premise. Measured: under
    `domain_hint: "order"` the detail rows are re-printed and the question stays open, so
    "no" cannot close it - the same "wud i can't reset now?" the owner hit, back through
    the domain word.
    """
    _seed_open_detail(session_factory, filters=_customer_subject_filters())
    result, calls = _run_turn(
        session_factory, monkeypatch,
        qf=_parser_output(
            message_type="business_query" if domain_hint else "casual", intent_hint=None,
            domain_hint=domain_hint, entity_op="reuse", is_affirmative=False,
            reference_positions=[], entities=[], asks=[],
            escalation={"is_escalation_confirmation": False, "company_pick": None},
        ),
        text_body="no", msg_id=f"ZZT-gr6-b2-{domain_hint or 'null'}",
        attributes=["sales_orders.outstanding"],
        fetch_response=_report_call(REPORT_HIT),
    )
    assert result.status in ("done", "delegated"), (result.status, result.error)
    reports = _report_tool_calls(calls)
    assert reports == [], (
        f"domain_hint {domain_hint!r}: a decline is answered with one line, never by "
        f"running the report the customer just declined: {calls!r}"
    )
    reply = (result.reply or {}).get("text") or ""
    assert "Reply 1 for" not in reply and "1. Sales order list" not in reply, (
        f"domain_hint {domain_hint!r}: the declined question must not be printed back: "
        f"{reply!r}"
    )
    question = _stored_oq(_final_vars(session_factory, result))
    assert question.get("kind") not in ("outstanding_detail", "outstanding_scope"), (
        f"domain_hint {domain_hint!r}: 'no' closes it: {question!r}"
    )


# --------------------------------------------------------------------------- #
# S1 - an offer exists because the BOT offered, not because the words appear
# --------------------------------------------------------------------------- #

#: Replies that carry the bot's OWN offer sentence, one per composer shape that writes it
#: (`open_question.ESCALATE_PREFIX`'s own comment names all four).
REAL_OFFER_REPLIES = (
    ("frozen-prefix", "Would you like me to escalate to warehouse team?", "warehouse"),
    (
        "lower-case-variant",
        "Couldn't pin down \"wc286\". Here are the closest matches:\n1. A\n2. B\n"
        "Reply with a number to continue, or would you like me to escalate to warehouse team?",
        "warehouse",
    ),
    (
        "yes-to-escalate",
        "Couldn't find some items:\n\n\"wc286\" - did you mean:\n1. A\n2. B\n\n"
        "Reply a number to pick, or 'yes' to escalate to purchasing.",
        "purchasing",
    ),
    (
        "bold-company-insert",
        "Would you like me to escalate to *Sorento* customer service team?",
        "customer_service",
    ),
)

#: Replies where the phrase is the CUSTOMER's, quoted back at them. Measured live: a
#: not-found echo of the token "escalate to purchasing." records a `purchasing` offer, so
#: the next bare "yes" escalates something nobody offered.
ECHOED_OFFER_REPLIES = (
    (
        "not-found-echo",
        'Couldn\'t find these: "escalate to purchasing." (product): not found.',
    ),
    (
        "scope-header-echo",
        "Customer: all\nProduct: escalate to warehouse.\nDates: all dates\n\n"
        "Here are the orders I found.",
    ),
)


@pytest.mark.parametrize(("case_id", "reply", "team"), REAL_OFFER_REPLIES, ids=lambda x: str(x))
def test_s1_every_composer_shape_of_the_bots_own_offer_is_recorded(
    case_id, reply, team
) -> None:
    """One rule, four sentences. `record_offer` is the single implementation, so each
    composer's own wording has to reach it - a shape it cannot read is an offer the
    customer can act on and the bot cannot answer (that is R-I)."""
    from app.services.chatbot.dialogue import open_question as oq

    question = oq.record_offer(None, reply_text=reply, turn_no=1)
    assert isinstance(question, dict), f"{case_id}: no offer recorded: {reply!r}"
    assert (question.get("payload") or {}).get("team") == team, (
        f"{case_id}: the offer records the team the sentence named: {question!r}"
    )
    assert question.get("expects") == "yes_no", question


@pytest.mark.parametrize(("case_id", "reply"), ECHOED_OFFER_REPLIES, ids=lambda x: str(x))
def test_s1_a_reply_that_merely_echoes_the_customers_words_records_no_offer(
    case_id, reply
) -> None:
    """S1 (reviewer): the phrase appearing in the reply is not the same fact as the bot
    having offered.

    `team_from_reply` anchors on the two words that never vary ("escalate to"), which is
    what makes it read every composer - and a customer token quoted back inside a
    not-found line or a scope header carries those same two words. An offer nobody made
    must not be answerable: the next bare "yes" would escalate on the strength of the
    customer's own typing.
    """
    from app.services.chatbot.dialogue import open_question as oq

    assert oq.record_offer(None, reply_text=reply, turn_no=1) is None, (
        f"{case_id}: the bot did not offer anything here - the words are the customer's, "
        f"quoted back: {reply!r}"
    )


def test_s1_an_echoed_phrase_never_outranks_the_bots_own_offer(
    session_factory, monkeypatch
) -> None:
    """The same rule end to end, on the one turn shape that carries BOTH: the customer's
    unresolvable token quoted back ("escalate to purchasing.") and the bot's own offer
    sentence in the same reply.

    The live shape is the order-domain not-found line, measured on the console pass:
    `Couldn't find: "DO12345" (order). Would you like me to escalate to customer service
    team?`. The echo comes FIRST in the text, so a reader that takes the first "escalate
    to" it finds records `purchasing` - a team nobody offered - and the customer's next
    "yes" goes there.
    """
    _seed_contact(session_factory, variables={})
    token = "escalate to purchasing."
    result, _calls = _run_turn(
        session_factory, monkeypatch,
        qf=_qf([_entity(token, "order")], domain="order", intent_hint="check_order"),
        text_body=f'has my order "{token}" arrived', msg_id="ZZT-gr6-s1-echo",
        resolve_services=_exact_services(unresolved=(token,)),
    )
    reply = (result.reply or {}).get("text") or ""
    assert token in reply, (
        f"this test is only itself if the reply quotes the customer's token back: {reply!r}"
    )
    printed = _printed_team(reply)
    question = _stored_oq(_final_vars(session_factory, result))
    recorded = _recorded_team(question)
    assert recorded != "purchasing", (
        f"'purchasing' is the customer's own word, quoted back inside a not-found line - "
        f"the offer is whatever the BOT's own sentence named ({printed!r}): {question!r}"
    )
    if printed is not None:
        assert _pretty(recorded) == printed, (
            f"the reply promised {printed!r} and the question recorded {recorded!r}: "
            f"{question!r}"
        )


# --------------------------------------------------------------------------- #
# Guards for the three hunks the reviewer's kill test found unguarded
# --------------------------------------------------------------------------- #


def test_the_family_rides_only_a_customer_row() -> None:
    """`_entity_of` (security review n2): an account family is a fact about a CUSTOMER.

    `entity_ids_transformer` expands `family_uuids` into `customer_ids`, so copying the
    key off any row that happened to carry one would hand an unowned uuid list to a type
    with no notion of a family - a product pick that reached six customers' orders.
    """
    from app.services.chatbot.dialogue import open_question as oq

    customer = oq.resolve(
        "customer_pick",
        {**ox_no_answer(), "resolved": True, "picks": [1]},
        [
            {
                "idx": 1, "label": "CHIN CHUN HARDWARE SDN BHD (SRT, MCH)", "code": "300-C043",
                "uuid": CHIN_CHUN[0][0], "entity_type": "customer",
                "family_uuids": [CHIN_CHUN[0][0], CHIN_CHUN[1][0]],
            }
        ],
        {},
    )
    assert customer.focus["customer"].get("family_uuids") == [
        CHIN_CHUN[0][0], CHIN_CHUN[1][0]
    ], customer.focus

    product = oq.resolve(
        "product_pick",
        {**ox_no_answer(), "resolved": True, "picks": [1]},
        [
            {
                "idx": 1, "label": "SRTWC286-SH", "code": "SRTWC286-SH",
                "uuid": "33333331-1111-1111-1111-111111111111", "entity_type": "product",
                # A row that carries the key anyway: nothing downstream may act on it.
                "family_uuids": [CHIN_CHUN[0][0], CHIN_CHUN[1][0]],
            }
        ],
        {},
    )
    picked = product.focus["products"][0]
    assert "family_uuids" not in picked, (
        f"a product is not an account family: {picked!r}"
    )


def ox_no_answer() -> dict[str, Any]:
    from app.services.chatbot.head import output_exchange as ox

    return dict(ox.NO_OPEN_QUESTION_ANSWER)


def test_record_offer_leaves_a_non_roster_question_alone() -> None:
    """`record_offer`'s non-roster guard: a team clarify, a company clarify and a member
    offer are ALREADY what the customer is being asked, and the escalate yes/no has
    nothing to add to any of them.

    A roster takes the offer on board (D19 rule 3) and no question at all becomes the
    plain yes/no; those two are covered by the shapes above. This is the third branch,
    which the kill test found nothing grading.
    """
    from app.services.chatbot.dialogue import open_question as oq

    reply = "Would you like me to escalate to warehouse team?"
    for kind, options in (
        ("team_pick", [{"idx": 1, "team": "purchasing", "label": "purchasing"}]),
        ("company_pick", [{"idx": 1, "label": "Sorento", "company_id": "co-1"}]),
        ("member_offer", [{"idx": 1, "label": "Nurain", "uuid": "u-1"}]),
    ):
        question = oq.ask(kind, options=options, turn_no=3)
        after = oq.record_offer(question, reply_text=reply, turn_no=4)
        assert after == question, (
            f"{kind} is already the question on the customer's screen: {after!r}"
        )


def test_the_engines_post_compose_arm_never_replaces_an_open_member_offer(
    session_factory, monkeypatch
) -> None:
    """The engine's own arm, guarded end to end: a re-prompted member roster must survive
    a turn whose reply carries the escalate sentence.

    Measured cause in the engine's own comment: two owner worlds
    (`sub-output-live/out-14875019`, `out-15145655`) turned a six-person roster into a
    one-option team clarify as soon as this arm could read a team off the printed
    sentence. A member offer is an open offer with its own yes, its own no and its own
    re-prompt.
    """
    from app.services.chatbot import engine as engine_mod
    from app.services.chatbot.dialogue import open_question as oq

    member = oq.ask(
        "member_offer",
        options=[
            {"idx": 1, "label": "Nurain", "uuid": "aaaaaaaa-0000-0000-0000-000000000001"},
            {"idx": 2, "label": "Aina", "uuid": "aaaaaaaa-0000-0000-0000-000000000002"},
        ],
        turn_no=5,
        payload={"team": "warehouse"},
    )
    sealed = {
        "text": "No stock for SRTWT2634. Would you like me to escalate to warehouse team?",
        "session_patch": {"variables": {"open_question": member}},
    }
    ctx = {"parse": {"_turn_no": 6, "_open_question_before": member}}

    engine_mod._arm_cross_domain_offer(sealed, {"team": "warehouse"}, ctx=ctx, domain="inventory")

    after = sealed["session_patch"]["variables"]["open_question"]
    assert after == member, (
        f"the named people the customer is reading must still be the question: {after!r}"
    )
