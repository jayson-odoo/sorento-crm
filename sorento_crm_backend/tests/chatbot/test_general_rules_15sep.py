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
    _focus_slot,
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

#: The team span is `[^.?!\n]+?`, the same class the code's own `_ESCALATE_TEAM_RE` uses,
#: and NOT `.+?`: a token that echoes the offering clause ("would you like me to escalate
#: to purchasing team.") ends in a full stop, and a dot-matching span runs straight
#: through it into the REAL sentence's " team?" - which made this reader return
#: `'purchasing team." (order). Would you like me to escalate to customer service'` as
#: the printed promise. Stopping at the sentence end keeps each match to one sentence, and
#: `_printed_team` then takes the LAST of them.
_ESCALATE_SENTENCE_RE = re.compile(
    r"[Ww]ould you like me to escalate to (?:\*[^*]+\* )?([^.?!\n]+?) team\?"
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

    **LAST MATCH WINS, and the test's own reader needs it as much as the code does.** A
    customer token quoted back inside a not-found line can carry the whole offering clause
    ("would you like me to escalate to purchasing team."), and the bot's own sentence is
    always appended AFTER the echo - so the first match spans from the echo into the real
    sentence's " team?" and returns nonsense. Measured on the live order-domain line:
    searching forwards gave `'purchasing team." (order). Would you like me to escalate to
    customer service'`; the last match gives `customer service`, which is what the
    customer was promised.
    """
    matches = list(_ESCALATE_SENTENCE_RE.finditer(reply or ""))
    return matches[-1].group(1).strip() if matches else None


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
    capture_user_block: list[str] | None = None,
):
    """One real `engine.run_turn`. Returns `(result, calls)`.

    `calls` records every MCP call the turn made, fetch and probe alike, the probe
    prefixed `probe:` - the cross-domain ladder runs on the PROBE seam and the fetch on
    the tool seam, and a test about the ladder has to be able to tell them apart.

    `capture_user_block`, given a list, has this turn's `user_block` appended to it.

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

    def _parse(config, user_block):
        # D17's own reason for existing: the parser is meant to read the open question's
        # rows off THIS text, so a test asking what the model was actually shown reads the
        # block rather than guessing at an internal builder's name.
        if capture_user_block is not None:
            capture_user_block.append(user_block)
        return qf

    monkeypatch.setattr(parser_mod, "parse", _parse)

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
    token_log: list[str] | None = None,
) -> ResolveGateServices:
    """A `resolve_entity` seam keyed on EXACT tokens (see the module docstring).

    `multi` maps a token to the several rows it is ambiguous across; `single` maps a token
    to the one row it resolves to. A request that asks about neither resolves nothing,
    which is what a bare positional pick sends. `token_log`, given a list, records every
    token every call asked about.
    """

    def _resolve_entity(body: dict[str, Any]) -> dict[str, Any]:
        asked = _tokens_of(body)
        if token_log is not None:
            # WHAT THE RESOLVER WAS ASKED, which is the only honest way to prove a row
            # LABEL was never minted into an entity: a label that reaches resolution is a
            # label the head turned into a token (R-M).
            token_log.extend(sorted(asked))
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


#: A `customer_pick` roster with the escalate offer RIDING it (D19 rule 3), seeded rather
#: than driven through the gate. The kind and the rows are what this test is about, and
#: the gate's own arming is what group 2 grades: while `compatible_entities` still carries
#: the co-resolved siblings, that arm persists THIRTEEN rows and a `product_pick` kind, so
#: driving it here would grade group 2's defect a second time and never reach the re-pick.
_RIDDEN_CUSTOMER_ROSTER = {
    "kind": "customer_pick",
    "options": [
        {
            "idx": index,
            "label": f"{name} (SRT)",
            "code": code,
            "uuid": uuid,
            "entity_type": "customer",
            "family_uuids": [uuid],
        }
        for index, (uuid, code, name) in enumerate(CHIN_CHUN, start=1)
    ],
    "expects": "pick_or_yes_no",
    "asked_at_turn": 2,
    "asked_at": None,
    "payload": {
        "domain": "order",
        "keep": [],
        "offer": {
            "team": "customer_service",
            "domain": "order",
            "options": [{"idx": 1, "team": "customer_service", "label": "customer_service"}],
        },
    },
}


def test_a_number_still_repicks_under_a_riding_offer(session_factory, monkeypatch) -> None:
    """D19 rule 1 and rule 3 together: with an offer riding the roster, a NUMBER is still
    a pick against the rows the reply numbered, and it wins over the yes/no (a number is
    unambiguous).

    **Graded on the PICK, not on the fetch** (coordinator's ruling, R-J round): what the
    lane does with the re-picked customer depends on which axes the focus carries into
    that turn - under R16's broad `order_status` carry an inherited `outstanding` sends it
    to the report and a missing grant can then refuse it - and none of that is what this
    test is about. So: the dialogue resolved the SECOND row, the turn SAID something, and
    any tool it did reach is scoped to that row.

    **A refused pick may never be SILENT** (D13): the customer typed a number off a list
    the bot printed, and a turn that answers nothing at all is a defect whichever lane
    declined it.
    """
    _seed_contact(
        session_factory, variables={"open_question": dict(_RIDDEN_CUSTOMER_ROSTER)}
    )
    result, calls = _run_turn(
        session_factory, monkeypatch, qf=_pick_v1(2), text_body="2",
        msg_id="ZZT-gr-repick-answer", attributes=["sales_orders.outstanding"],
        resolve_services=_exact_services(), fetch_response=_report_call(REPORT_HIT),
    )
    assert result.status in ("done", "delegated"), (result.status, result.error)
    said = ((result.reply or {}).get("text") or "").strip() or " ".join(
        str(a.get("text") or "")
        for a in (result.actions or [])
        if isinstance(a, dict) and a.get("kind") == "send_message"
    ).strip()
    assert said, (
        f"the customer picked row 2 off a list the bot printed and the turn said nothing "
        f"at all: actions={result.actions!r}"
    )
    picked = _picked_labels(session_factory, result.turn_id)
    assert any(CHIN_CHUN[1][2] in label for label in picked), (
        f"'2' must resolve the roster's own SECOND row (CHIN CHUN HOMEMART), never the "
        f"offer and never a row the reply did not number: {picked!r}"
    )
    for name, args in [c for c in calls if not c[0].startswith("probe:")]:
        assert args.get("customer_ids") in (None, [CHIN_CHUN[1][0]]), (
            f"whatever the re-pick fetched must be scoped to the row the customer chose: "
            f"{name} {args!r}"
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


def _seed_open_detail(
    session_factory, *, filters: dict[str, Any], domains: list[str] | None = None
) -> None:
    variables: dict[str, Any] = {
        "open_question": _open_question(
            "outstanding_detail",
            options=[
                {"idx": 1, "label": "Sales order list", "value": "so"},
                {"idx": 2, "label": "Delivery order list", "value": "do"},
                {"idx": 3, "label": "Both lists", "value": "both"},
            ],
            filters=filters,
        )
    }
    if domains:
        variables["focus"] = {"domains": _focus_slot(list(domains))}
    _seed_contact(session_factory, variables=variables)


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


#: The four B1 cases, and what the EXISTING rules owe each of them once the decline stops
#: swallowing the ask (coordinator's ruling, R-J round - no new domain-inheritance rule is
#: being asked for):
#:
#: * a domain WORD is present -> that domain answers: the stock tool for a product, and
#:   the gate's own refusal for a customer, which is not a stock axis.
#: * NO domain word -> the ALIVE domains re-run for the new entity, and under an open
#:   outstanding question the alive domain is `order`. So the order lane re-runs for
#:   SRTWT2634 here; the STOCK tool for a bare "check stock X" is the parser's own half
#:   and belongs to #928's class, not to this one.
_B1_CASES = (
    ("product-inventory", STOCK_CODE, "product", STOCK_UUID, "inventory", "stock-tool"),
    ("product-null", STOCK_CODE, "product", STOCK_UUID, None, "order-domain"),
    ("customer-null", "hanlim", "customer", CARRIED_CUSTOMER_UUID, None, "order-domain"),
    ("customer-inventory", "hanlim", "customer", CARRIED_CUSTOMER_UUID, "inventory", "gate-refusal"),
)

#: Every tool the ORDER domain answers with. `crm_outstanding_report` is in here because a
#: new product named under an open outstanding ask can legitimately re-run the report for
#: THAT product - what it may never do is re-run it for the OLD one.
_ORDER_DOMAIN_TOOLS = (
    "crm_order_management_orders_list",
    "crm_order_management_orders_by_product_list",
    "crm_outstanding_report",
)


@pytest.mark.parametrize(
    ("case_id", "raw", "hint", "uuid", "domain_hint", "expect"), _B1_CASES,
    ids=lambda x: str(x),
)
def test_b1_a_decline_that_brings_its_own_question_is_answered_not_just_acknowledged(
    case_id, raw, hint, uuid, domain_hint, expect, session_factory, monkeypatch
) -> None:
    """B1 (reviewer, NEW regression on the general-rule round): "no, check stock
    SRTWT2634" over an open outstanding question is a decline AND an ask.

    R22(a)'s way out reads `is_affirmative: False` on a turn that "picked nothing, named
    nothing and refined nothing" and answers with one line from the registry's
    `offer_declined` key ("Okay, noted.",
    `lanes/business/__init__._outstanding_offer_closed`). A turn that names its OWN
    subject is not that turn: closing the question is right, and stopping there leaves the
    customer's actual question unanswered. Measured on all four shapes below - every one
    of them replies `"Okay, noted."`, stamps `outstanding_offer_declined`, and calls
    nothing.

    The DEFECT is that one reading, so that is what the first three assertions grade; the
    fourth says only what the rules that already exist owe this turn afterwards.
    """
    # AN ALIVE DOMAIN, because that is the rule being relied on (coordinator's ruling):
    # with no domain word of its own the turn re-runs the domains the conversation is
    # already about, and a fixture whose focus carries none leaves it nothing to re-run -
    # the turn then delegates as low_signal and the test would be grading the fixture.
    _seed_open_detail(
        session_factory, filters=_customer_subject_filters(),
        domains=["order"],
    )
    result, calls = _run_turn(
        session_factory, monkeypatch,
        qf=_decline_with_a_new_ask_qf(domain_hint, raw=raw, hint=hint),
        text_body=f"no, check stock {raw}", msg_id=f"ZZT-gr6-b1-{case_id}",
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
    said = reply.strip() or " ".join(
        str(a.get("text") or "")
        for a in (result.actions or [])
        if isinstance(a, dict) and a.get("kind") == "send_message"
    ).strip()
    emission = ((result.ctx or {}).get("parse") or {}).get("output") or {}

    # THE DEFECT, three ways of saying the same thing.
    assert "Okay, noted." not in said, (
        f"{case_id}: the customer declined the offer AND asked something - acknowledging "
        f"the decline is not an answer to the question: {said!r}"
    )
    assert not jsc_truthy(emission.get("outstanding_offer_declined")), (
        f"{case_id}: this turn is not the bare decline R22(a) is for - it named its own "
        f"subject: {emission.get('outstanding_offer_declined')!r}"
    )
    assert said, f"{case_id}: the turn answered nothing at all: {result.actions!r}"

    # The old question still closes, which is the half that was always right.
    question = _stored_oq(_final_vars(session_factory, result))
    assert question.get("kind") != "outstanding_detail", (
        f"{case_id}: the declined question still closes: {question!r}"
    )

    tool_calls = [c for c in calls if not c[0].startswith("probe:")]
    for name, args in tool_calls:
        assert not (
            name == "crm_outstanding_report"
            and args.get("product_code") == PRODUCT_CODE_IN_OFFER
        ), (
            f"{case_id}: the declined report must not be what answers the new ask: "
            f"{name} {args!r}"
        )

    if expect == "stock-tool":
        assert [name for name, _a in tool_calls] == ["crm_inventory_stock_balance_list"], (
            f"{case_id}: the message named the stock domain, so the stock tool answers it: "
            f"{tool_calls!r}"
        )
    elif expect == "order-domain":
        assert tool_calls, (
            f"{case_id}: no domain word, so the ALIVE domain (order, from the question "
            f"that was open) re-runs for the new entity: {calls!r}"
        )
        name, args = tool_calls[0]
        assert name in _ORDER_DOMAIN_TOOLS, (
            f"{case_id}: the alive domain is `order`; a stock answer here would be a new "
            f"domain-inheritance rule nobody asked for: {name}"
        )
        if hint == "product":
            # UUIDS, not the raw code: the order tools take resolved ids, exactly as the
            # customer branch below asserts for `customer_ids`.
            assert args.get("product_ids") == [uuid], (
                f"{case_id}: the re-run is for the entity THIS turn named: {args!r}"
            )
        else:
            assert args.get("customer_ids") == [uuid], (
                f"{case_id}: the re-run is for the customer THIS turn named: {args!r}"
            )
    else:  # gate-refusal
        assert tool_calls == [], (
            f"{case_id}: a customer is not a stock axis, so the gate refuses before any "
            f"tool runs: {tool_calls!r}"
        )
        assert said, f"{case_id}: and it says so rather than going quiet: {said!r}"


def jsc_truthy(value: Any) -> bool:
    """`None` / `False` / empty all read as "not stamped", which is what the emission's
    optional markers mean when the arm that writes them did not run."""
    return bool(value)


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

#: The CUSTOMER's own words, quoted back at them. Three of them carry the whole offering
#: clause, not merely the two anchor words, which is what the final review found still
#: open: the token IS the sentence, so a reader that takes the first match it sees cannot
#: tell the echo from the promise. Measured live on the order-domain not-found line.
ECHOED_CUSTOMER_TOKENS = (
    "escalate to purchasing.",
    "or 'yes' to escalate to warehouse.",
    "would you like me to escalate to purchasing team.",
)

#: The same tokens as the bot actually renders them: the echo FIRST, inside the not-found
#: line, and the bot's own offer appended after it.
ECHO_THEN_REAL_OFFER = tuple(
    (
        token,
        f'Couldn\'t find: "{token}" (order). '
        "Would you like me to escalate to customer service team?",
    )
    for token in ECHOED_CUSTOMER_TOKENS
)

#: Echo-ONLY replies: the customer's token quoted back with NO offer appended (a turn that
#: ANSWERED something and merely could not resolve one token). There is nothing here for a
#: "yes" to accept.
ECHO_ONLY_REPLIES = tuple(
    (
        token,
        "Here are the matching products.\n\n1. *Product Code:* SRTWT2634\n\n"
        f'Couldn\'t find these: "{token}" (product): not found.',
    )
    for token in ECHOED_CUSTOMER_TOKENS
) + (
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


@pytest.mark.parametrize(("token", "reply"), ECHO_THEN_REAL_OFFER, ids=lambda x: str(x)[:40])
def test_s1_the_bots_own_sentence_wins_over_the_echo_above_it(token, reply) -> None:
    """S1's first half, and the half `team_from_reply` owns: LAST MATCH WINS.

    Every composer appends its offer to the end of the text, so the bot's own promise is
    always the last "escalate to" in the reply. The echo above it is the customer's, and
    on these three tokens it carries the offering clause itself - so "the first one found"
    reads the customer's word as the promise, and their next "yes" goes to the team THEY
    typed.
    """
    from app.services.chatbot.dialogue import open_question as oq

    assert oq.team_from_reply(reply) == "customer_service", (
        f"the promise is the LAST sentence, not the echoed token {token!r}: {reply!r}"
    )
    question = oq.record_offer(None, reply_text=reply, turn_no=1)
    assert (question or {}).get("payload", {}).get("team") == "customer_service", (
        f"the recorded offer is what the customer was promised, not what they typed: "
        f"{question!r}"
    )


@pytest.mark.parametrize(("case_id", "reply"), ECHO_ONLY_REPLIES, ids=lambda x: str(x)[:40])
def test_s1_an_echo_with_no_offer_behind_it_arms_nothing(case_id, reply) -> None:
    """S1's second half, at the seam that owns it: the ENGINE's post-compose arm.

    `record_offer` is handed a reply and a fallback team; it cannot know whether the bot
    offered anything, and that is not its job - the CALLER knows, because the tail gates
    its call on `offer_open` and `crossdomain_compose` hands the engine an offer only when
    it appended one. Measured on this head: the engine arm reads a team off a pure echo and
    arms a `team_pick` out of it, so a following bare "yes" escalates on the strength of
    the customer's own typing.
    """
    from app.services.chatbot import engine as engine_mod

    sealed = {"text": reply, "session_patch": {"variables": {"open_question": None}}}
    engine_mod._arm_cross_domain_offer(
        # No offer from `crossdomain_compose`: nothing appended an escalate sentence this
        # turn, which is the whole premise.
        sealed, {}, ctx={"parse": {"_turn_no": 3}}, domain="master_products",
    )
    armed = sealed["session_patch"]["variables"]["open_question"]
    assert not armed, (
        f"{case_id}: no offer was made on this turn - the words are the customer's, "
        f"quoted back - and a question was armed anyway: {armed!r}"
    )


@pytest.mark.parametrize("token", ECHOED_CUSTOMER_TOKENS, ids=lambda t: t[:32])
def test_s1_an_echoed_phrase_never_outranks_the_bots_own_offer(
    token, session_factory, monkeypatch
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
    result, _calls = _run_turn(
        session_factory, monkeypatch,
        qf=_qf([_entity(token, "order")], domain="order", intent_hint="check_order"),
        text_body=f'has my order "{token}" arrived',
        msg_id=f"ZZT-gr6-s1-echo-{abs(hash(token)) % 10000}",
        resolve_services=_exact_services(unresolved=(token,)),
    )
    reply = (result.reply or {}).get("text") or ""
    assert token in reply, (
        f"this test is only itself if the reply quotes the customer's token back: {reply!r}"
    )
    printed = _printed_team(reply)
    question = _stored_oq(_final_vars(session_factory, result))
    recorded = _recorded_team(question)
    assert printed == "customer service", (
        f"this test is only itself if the BOT's own sentence named customer service: "
        f"{reply!r}"
    )
    assert recorded == "customer_service", (
        f"the team in {token!r} is the customer's own word, quoted back inside a "
        f"not-found line - the offer is whatever the BOT's own sentence named "
        f"({printed!r}): {question!r}"
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


# =========================================================================== #
# GROUP 7 - R-K, merge blocker: a bare number over a STICKY roster, once casual
# turns have intervened, is not read as a pick under the PROMOTED prompt
#
# Live chain on 92f0c081b (`sorento_ai_automation_focus_full`):
#
#   `incoming wc286`  -> the ten-row picker            (turn 2, correct)
#   `8`               -> row 8, scoped to it           (correct)
#   `another one`     -> low_signal                    (turn ab73f52b, correct)
#   `thanks`          -> low_signal                    (turn 8440c1ff, correct)
#   `10`              -> **low_signal**                (turn 3fd0d37c) instead of
#                                                       SRTWC286-SH-NEW
#
# Measured on those three rows, and it says where the defect is NOT:
#
# * the STICKY ROSTER IS FINE. All three turns were handed
#   `_open_question_before = {kind: product_pick, options: 10, asked_at_turn: 2}` - the
#   roster survived every casual turn, which is D19 rule 1 working.
# * the ENGINE's resolver is fine. It bridges v1 `reference_positions` into picks, and
#   turn 3fd0d37c's emission carries `reference_positions: []`.
# * the PARSER never emitted the position, while saying in the same breath what the
#   message was: `user_goal: "trying to pick option 10"`, `message_type: "casual"`, the
#   three v3 keys absent (this is the v1-shaped promoted prompt).
#
# So the question is what the model was SHOWN. `engine._pending_options` surfaces an open
# question's numbered rows to the parser's user block - and only for
# `_OPTION_PENDING_KINDS = ("outstanding_scope", "outstanding_detail")`. A `product_pick`
# is told `Pending: the assistant is waiting for a product_pick reply.` and nothing else,
# so the only place its rows ever appeared was the `Previous response:` line - which after
# one casual turn is the casual reply, and the list is gone from the input entirely.
#
# The two tests below split on exactly that seam: one grades the RESOLUTION given the
# position (the roster and the head), the other grades the parser's INPUT (the projection).
# =========================================================================== #


def _casual_v1(goal: str) -> dict[str, Any]:
    """The live v20 emission for "another one" / "thanks", verbatim on every field the
    rows carry (turns ab73f52b / 8440c1ff)."""
    return _parser_output(
        message_type="casual", intent_hint=None, domain_hint=None, entity_op="reuse",
        entities=[], reference_positions=[], reference_target=None, is_affirmative=None,
        correction=False, scope_intent=None, order_status=None, user_goal=goal,
    )


def _number_v1(position: int, *, goal: str | None = None) -> dict[str, Any]:
    """A bare number, v1-shaped, WITH the position the parser emits when it can see the
    rows. Turn 3fd0d37c's own emission is this minus `reference_positions`, and that
    absence is what group 7's second test is about."""
    return _parser_output(
        message_type="casual", intent_hint=None, domain_hint=None, entity_op="reuse",
        entities=[], reference_positions=[position], reference_target=None,
        is_affirmative=None, correction=False, scope_intent=None, order_status=None,
        user_goal=goal or f"trying to pick option {position}",
    )


#: The live v20 emission for the "10" turn, verbatim: the model says it is a pick and
#: emits no position, because it was never shown a list to count.
_LIVE_NUMBER_NO_POSITION = "trying to pick option 10"


def _roster_rows(*codes: str) -> list[dict[str, Any]]:
    return [
        {
            "idx": i, "label": code, "code": code, "product": code,
            "uuid": f"3333333{i}-1111-1111-1111-11111111111{i % 10}",
            "entity_type": "product",
        }
        for i, code in enumerate(codes, start=1)
    ]


def _customer_roster_rows() -> list[dict[str, Any]]:
    return [
        {
            "idx": i, "label": f"{name} (SRT)", "code": code, "uuid": uuid,
            "entity_type": "customer", "family_uuids": [uuid],
        }
        for i, (uuid, code, name) in enumerate(CHIN_CHUN, start=1)
    ]


@dataclass(frozen=True)
class StickyRoster:
    id: str
    question: dict[str, Any]
    #: The position the customer types, and the row label it has to resolve to.
    position: int
    label: str
    #: `dialogue` kinds resolve through `open_question.resolve` and land on the trace;
    #: `outstanding_scope` is resolved by the head instead, so it is graded on the report.
    channel: str
    #: HOW MANY intervening casual turns this roster can be graded over, and it is not the
    #: same number for every kind. A casual turn over an OUTSTANDING question is already
    #: ruled on (R22, owner round 9): the first unreadable reply re-prints the question and
    #: the second closes it, so "the roster is still there two turns later" is not true of
    #: that kind by design - measured here too (one "another one" closes it). R-K is about
    #: the kinds D19 makes sticky, so the outstanding one is graded at 0 and says why.
    casual_counts: tuple[int, ...] = (0, 1, 2)
    #: Answer this roster's number as a DRY RUN. Only the member offer needs it: its pick
    #: escalates, and a live escalation opens an SLA row, which a blank schema has no
    #: policy for ("404: No SLA policy found with code='NORMAL'") - infrastructure, not
    #: behaviour. The lane still composes its real actions on a dry run.
    dry_run: bool = False
    #: The completed-lane set the ANSWER turn needs. A member pick is answered by the
    #: `offer_hold` lane (the re-prompt / assign path), and a lane left out of the set
    #: DELEGATES - a delegated turn writes no actions, which reads as "the pick resolved
    #: nothing" when in truth it was handed to n8n.
    lanes: tuple[str, ...] = LANES


STICKY_ROSTERS: tuple[StickyRoster, ...] = (
    StickyRoster(
        "multi-match-product",
        _open_question(
            "product_pick", options=_roster_rows(*WC286_CODES),
            filters=None, turn_no=2,
        ) | {"payload": {"domain": "incoming", "keep": []}},
        position=10, label="SRTWC286-P", channel="dialogue",
    ),
    StickyRoster(
        "did-you-mean-product",
        _open_question(
            "product_pick", options=_roster_rows("SRTWT2632", "SRTWT2633", "SRTWT2634"),
            filters=None, turn_no=2,
        ) | {
            # `miss_suggest._attach_question`'s own payload: the did-you-mean roster is a
            # product_pick that also carries the offer's identity.
            "payload": {"domain": "inventory", "keep": [], "offer_id": "exec-1", "picked": []}
        },
        position=3, label="SRTWT2634", channel="dialogue",
    ),
    StickyRoster(
        "customer-picker",
        _open_question(
            "customer_pick", options=_customer_roster_rows(), filters=None, turn_no=2,
        ) | {"payload": {"domain": "order", "keep": []}},
        position=2, label="CHIN CHUN HOMEMART", channel="dialogue",
    ),
    StickyRoster(
        "outstanding-scope",
        _open_question(
            "outstanding_scope",
            options=[
                {"idx": 1, "label": "Sales orders", "value": "so"},
                {"idx": 2, "label": "Delivery orders", "value": "do"},
                {"idx": 3, "label": "Both", "value": "both"},
            ],
            filters={
                "product_code": OUTSTANDING_CODE,
                "date_filter_start": None, "date_filter_end": None,
                "customer_ids": [], "warehouse_codes": [], "location_token": None,
            },
            turn_no=2,
        ),
        position=2, label="Delivery orders", channel="head", casual_counts=(0,),
    ),
    StickyRoster(
        # (b) THE GUARD the coordinator asked for: a member offer is answered by a
        # position too (`_member_offer`: "the roster is on the screen beside the offer, so
        # a bare '2' is an answer to the same question"), and it is NOT one of
        # `ROSTER_KINDS`, so nothing about D19's stickiness applies to it. If this arm is
        # red, member_offer belongs in `_OPTION_PENDING_KINDS` with the other three.
        "member-offer",
        {
            "kind": "member_offer",
            "options": [
                {"idx": 1, "label": "Nurain", "uuid": "aaaaaaaa-0000-0000-0000-000000000001"},
                {"idx": 2, "label": "Aina", "uuid": "aaaaaaaa-0000-0000-0000-000000000002"},
            ],
            "expects": "yes_no",
            "asked_at_turn": 2,
            "asked_at": None,
            "payload": {"team": "warehouse", "domain": "inventory"},
        },
        position=2, label="Aina", channel="dialogue", dry_run=True,
        lanes=(*LANES, "offer_hold", "low_signal"),
    ),
)


def _sticky_cases() -> list[tuple[StickyRoster, int]]:
    """Every (roster, intervening-casual-turns) pair, so a kind whose casual behaviour is
    ruled elsewhere is graded over the counts that are its own."""
    return [(roster, count) for roster in STICKY_ROSTERS for count in roster.casual_counts]

#: The live chain had TWO casual turns between the pick and the number; 0 and 1 are there
#: because the number of them is exactly what the defect is keyed on.
CASUAL_RUNS = (0, 1, 2)
_CASUAL_GOALS = ("trying to ask for another one", "trying to thank the assistant")


def _run_casual_turns(
    session_factory,
    monkeypatch,
    *,
    count: int,
    tag: str,
    blocks: list[str] | None = None,
    lanes: tuple[str, ...] = LANES,
) -> None:
    for index in range(count):
        _run_turn(
            session_factory, monkeypatch, qf=_casual_v1(_CASUAL_GOALS[index % 2]),
            text_body=("another one", "thanks")[index % 2],
            msg_id=f"ZZT-gr7-{tag}-casual-{index}",
            lanes=(*lanes, "low_signal", "offer_hold"), capture_user_block=blocks,
        )



def _open_question_options_fact(session_factory, turn_id: str) -> Any:
    """`understood.facts.open_question_options` off the persisted trace - WHICH options
    the parser was shown, which the engine records for exactly this diagnosis."""
    from app.models.chatbot_turn import ChatbotTurn

    row = (
        session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).first()
    )
    for entry in list((row.trace if row is not None else None) or []):
        if isinstance(entry, dict) and entry.get("stage") == "understood":
            return ((entry.get("facts") or {}).get("open_question_options"))
    return None

@pytest.mark.parametrize(
    ("roster", "casual_turns"), _sticky_cases(), ids=lambda x: x.id if isinstance(x, StickyRoster) else f"{x}-casual"
)
def test_a_bare_number_resolves_the_frozen_row_however_many_casual_turns_intervened(
    roster, casual_turns, session_factory, monkeypatch
) -> None:
    """R-K, the resolution half: the roster the customer can still see answers a number,
    and small talk in between changes nothing about which row that number means.

    Given the position (which is what the parser emits when it can see the rows - the
    other half of R-K, below), this grades the roster's own lifetime and the handler that
    resolves against it.
    """
    _seed_contact(session_factory, variables={"open_question": dict(roster.question)})
    _run_casual_turns(
        session_factory, monkeypatch, count=casual_turns,
        tag=f"{roster.id}-{casual_turns}", lanes=roster.lanes,
    )
    # THE ROWS, BEFORE the number arrives - because a question that kept its kind and lost
    # its rows resolves nothing, and the symptom below would not say why. Measured on the
    # member offer: one casual turn comes back `kind: member_offer` with `options: []`
    # (the `offer_hold` re-prompt re-arms it empty), so the customer's "2" picks nobody -
    # and projecting THAT list to the parser would project nothing.
    alive = _stored_oq(_vars(session_factory))
    assert len(alive.get("options") or []) == len(roster.question.get("options") or []), (
        f"{roster.id} after {casual_turns} casual turn(s): the question is still open and "
        f"the rows the customer is looking at are gone: {alive!r}"
    )
    # B-2 (light review): THE TEAM IS HALF OF THE SAME FACT and nothing guarded it -
    # deleting `_re_armed`'s `live_team` block left the suite green while a member offer
    # seeded `payload.team: warehouse` came back `customer_service` after one casual turn.
    # A re-prompt keeps the rows AND the team it was asked under; where the roster was
    # asked without one there is nothing to keep and this reads as absent on both sides.
    asked_team = (roster.question.get("payload") or {}).get("team")
    assert (alive.get("payload") or {}).get("team") == asked_team, (
        f"{roster.id} after {casual_turns} casual turn(s): the question was asked under "
        f"team {asked_team!r} and the re-prompt re-derived "
        f"{(alive.get('payload') or {}).get('team')!r}: {alive!r}"
    )
    result, calls = _run_turn(
        session_factory, monkeypatch, qf=_number_v1(roster.position),
        text_body=str(roster.position),
        msg_id=f"ZZT-gr7-{roster.id}-{casual_turns}-number",
        attributes=["sales_orders.outstanding"],
        resolve_services=_exact_services(),
        fetch_response=_report_call(REPORT_HIT),
        is_test=roster.dry_run, lanes=roster.lanes,
    )
    assert result.status in ("done", "delegated"), (result.status, result.error)
    if roster.channel == "dialogue":
        picked = _picked_labels(session_factory, result.turn_id)
        assert any(roster.label in label for label in picked), (
            f"{roster.id} after {casual_turns} casual turn(s): "
            f"'{roster.position}' means the row the customer read, whatever was said in "
            f"between: {picked!r}"
        )
    else:
        reports = _report_tool_calls(calls)
        assert reports, (
            f"{roster.id} after {casual_turns} casual turn(s): the scope answer must run "
            f"the report: {calls!r}"
        )
        assert reports[0].get("scope") == "do", (
            f"{roster.id} after {casual_turns} casual turn(s): '2' is the DO scope: "
            f"{reports[0]!r}"
        )


@pytest.mark.parametrize(
    ("roster", "casual_turns"), _sticky_cases(), ids=lambda x: x.id if isinstance(x, StickyRoster) else f"{x}-casual"
)
def test_the_parser_is_still_shown_the_frozen_rows_after_casual_turns(
    roster, casual_turns, session_factory, monkeypatch
) -> None:
    """R-K's own defect, at the seam the live rows point at: what the PARSER was shown.

    Under the promoted v1 prompt the model's only sight of a roster is the user block. It
    is handed `Pending: the assistant is waiting for a <kind> reply.` on every open
    question, and the numbered rows ONLY for `engine._OPTION_PENDING_KINDS`
    (`outstanding_scope`, `outstanding_detail`) - so a `product_pick` or `customer_pick`
    roster reaches the model only through the `Previous response:` line, which one casual
    turn replaces with the casual reply. Live: turn 3fd0d37c said
    `user_goal: "trying to pick option 10"` and `reference_positions: []` - the model knew
    it was a pick and had no list to count.

    The assertion is the projection, not the wording: the block must name the rows the
    question froze (their labels), on the turn the number arrives AND on every casual turn
    before it, because the roster is open on all of them.
    """
    _seed_contact(session_factory, variables={"open_question": dict(roster.question)})
    blocks: list[str] = []
    _run_casual_turns(
        session_factory, monkeypatch, count=casual_turns,
        tag=f"{roster.id}-{casual_turns}-blocks", blocks=blocks, lanes=roster.lanes,
    )
    result, _calls = _run_turn(
        session_factory, monkeypatch, qf=_number_v1(roster.position),
        text_body=str(roster.position),
        msg_id=f"ZZT-gr7-{roster.id}-{casual_turns}-block",
        attributes=["sales_orders.outstanding"],
        resolve_services=_exact_services(),
        fetch_response=_report_call(REPORT_HIT),
        capture_user_block=blocks, is_test=roster.dry_run, lanes=roster.lanes,
    )
    assert len(blocks) == casual_turns + 1, blocks
    expected_rows = [
        str(row.get("label")) for row in (roster.question.get("options") or [])
    ]
    # THE ENGINE'S OWN RECORD FIRST. `understood.facts.open_question_options` exists for
    # exactly this question ("diagnosing 'the model answered casual' needs to separate
    # 'it was never told what was on offer' from 'it was told and did not take it'"), and
    # on all three live turns it is empty.
    recorded = _open_question_options_fact(session_factory, result.turn_id)
    assert recorded, (
        f"{roster.id} after {casual_turns} casual turn(s): the turn recorded no "
        f"`open_question_options` at all, so the parser was never shown the rows it is "
        f"meant to count - live turn 3fd0d37c's own shape: {recorded!r}"
    )
    for label in expected_rows:
        assert any(label in str(row) for row in recorded), (
            f"{roster.id}: the rows shown to the parser must be the rows the question "
            f"froze - {label!r} missing from {recorded!r}"
        )
    # AND THE BLOCK, because the record is only worth having if it reaches the model.
    for index, block in enumerate(blocks):
        missing = [label for label in expected_rows if label not in block]
        assert not missing, (
            f"{roster.id}, parser input on turn {index + 1} of "
            f"{casual_turns + 1}: the question is open and the model cannot see the rows "
            f"it is supposed to count - missing {missing[:3]!r} from:\n{block}"
        )


def test_showing_the_parser_a_roster_adds_exactly_one_line_to_the_v1_block() -> None:
    """The parity half (c): the extra line is ADDITIVE and nothing else about the block
    moves.

    `test_parser_user_block_parity.py` holds the v1 block byte-for-byte against the
    captured n8n run, and its fixture turn has NO open question - so this states the
    property that file cannot: the same block, for the same turn, with a roster open,
    differs by exactly one line and that line is the options.
    """
    from app.services.chatbot.head import parser as parser_mod

    common = dict(
        previous_response="Previous turn (inventory): stock for SRTWC286-SH.",
        latest_user_message="10\n",
        pending_kind="product_pick",
    )
    without = parser_mod.build_user_block(**common)
    with_rows = parser_mod.build_user_block(
        **common, pending_options=["1. SRTWC286-SH", "10. SRTWC286-P"]
    )
    before, after = without.split("\n"), with_rows.split("\n")
    assert after[: len(before)] == before, (
        f"the block the promoted prompt already reads must not move:\n{without!r}\n"
        f"{with_rows!r}"
    )
    assert len(after) == len(before) + 1, (with_rows, without)
    assert after[-1].startswith("Open question options: "), after[-1]


# =========================================================================== #
# GROUP 8 - R-K's real cause: a riding offer hides the roster from the parser
#
# `engine._pending_kind` (engine.py:448-450) answers `"team_pick"` for ANY question whose
# `payload.offer` is set, which is a deliberate choice for the one line a v1 prompt gets
# ("on that turn the thing the customer is most likely answering is the yes/no question
# the reply ended with"). `_pending_options` then reads THAT word against
# `_OPTION_PENDING_KINDS`, and a roster carrying an offer is therefore shown no rows at
# all - so D19 rule 3's own promise ("a number re-picks, a yes/no answers the offer") is
# true of the engine and invisible to the model.
#
# Live, on the same contact and the same ten-row roster:
#
# | turn | question before | open_question_options |
# |---|---|---|
# | 7e14db69 | `product_pick`, `expects: pick`, 10 rows | all ten rows |
# | 34000918 | `product_pick`, `expects: pick_or_yes_no`, 10 rows + `payload.offer` | **null** |
#
# The second turn's message was "10" and it answered `low_signal`.
# =========================================================================== #


def _with_offer_payload(question: dict[str, Any], team: str = "purchasing") -> dict[str, Any]:
    """The same question with an escalate offer riding it (D19 rule 3), exactly as
    `open_question.with_offer` composes it."""
    payload = dict(question.get("payload") or {})
    payload["offer"] = {
        "team": team,
        "domain": payload.get("domain"),
        "options": [{"idx": 1, "team": team, "label": team}],
    }
    return {**question, "expects": "pick_or_yes_no", "payload": payload}


def _tier_rows() -> list[dict[str, Any]]:
    return [
        {"idx": 1, "tier": "office", "label": "Office", "value": "office"},
        {"idx": 2, "tier": "dealer", "label": "Dealer", "value": "dealer"},
    ]


#: The three kinds D19 makes sticky, each with an offer riding it. `tier_pick` is in here
#: because the tier menu takes an offer the same way (`_offer_carry`'s tier arm) and its
#: rows are the ones a "2" counts against.
RIDDEN_ROSTERS = (
    (
        "product_pick",
        _with_offer_payload(
            _open_question("product_pick", options=_roster_rows(*WC286_CODES), turn_no=2)
            | {"payload": {"domain": "incoming", "keep": []}}
        ),
    ),
    (
        "customer_pick",
        _with_offer_payload(
            _open_question("customer_pick", options=_customer_roster_rows(), turn_no=2)
            | {"payload": {"domain": "order", "keep": []}}
        ),
    ),
    (
        "tier_pick",
        _with_offer_payload(
            _open_question("tier_pick", options=_tier_rows(), turn_no=2)
            | {"payload": {"domain": "promotion", "keep": []}}
        ),
    ),
)


def _pending_line(block: str) -> str | None:
    for line in (block or "").splitlines():
        if line.startswith("Pending: "):
            return line
    return None


@pytest.mark.parametrize("casual_turns", (0, 1, 2), ids=lambda n: f"{n}-casual")
@pytest.mark.parametrize(("kind", "question"), RIDDEN_ROSTERS, ids=lambda x: x if isinstance(x, str) else "")
def test_a_roster_carrying_an_offer_still_shows_the_parser_its_rows(
    kind, question, casual_turns, session_factory, monkeypatch
) -> None:
    """R-K's real cause. The rows are what a NUMBER is counted against, and a number is
    still an answer to a roster carrying an offer - D19 rule 3 says so and
    `dialogue/open_question.resolve` implements it ("a number wins: it is unambiguous").
    So the model has to be shown them, and the `Pending:` line has to name the question
    the rows belong to, not the yes/no riding on it.
    """
    _seed_contact(session_factory, variables={"open_question": dict(question)})
    _run_casual_turns(
        session_factory, monkeypatch, count=casual_turns, tag=f"gr8-{kind}-{casual_turns}"
    )
    blocks: list[str] = []
    result, _calls = _run_turn(
        session_factory, monkeypatch, qf=_number_v1(2), text_body="2",
        msg_id=f"ZZT-gr8-{kind}-{casual_turns}", attributes=["sales_orders.outstanding"],
        resolve_services=_exact_services(), capture_user_block=blocks,
        lanes=(*LANES, "low_signal", "check_promotion"),
    )
    assert result.status in ("done", "delegated"), (result.status, result.error)
    recorded = _open_question_options_fact(session_factory, result.turn_id)
    expected_rows = [str(row.get("label")) for row in (question.get("options") or [])]
    assert recorded, (
        f"{kind} with an offer riding it, after {casual_turns} casual turn(s): no rows "
        f"were shown to the parser, so a bare number has nothing to be counted against - "
        f"live turn 34000918's own shape: {recorded!r}"
    )
    for label in expected_rows:
        assert any(label in str(row) for row in recorded), (
            f"{kind}: {label!r} missing from the rows the parser was shown: {recorded!r}"
        )
    pending = _pending_line(blocks[-1] if blocks else "")
    assert pending and kind in pending, (
        f"{kind}: the Pending line must name the question the ROWS belong to - a roster "
        f"carrying an offer is still that roster (D19 rule 3): {pending!r}"
    )


def test_a_plain_escalate_offer_sends_no_options_line(session_factory, monkeypatch) -> None:
    """The negative, and it is why `_pending_kind`'s collapse exists in the first place: a
    one-team yes/no offer has no roster to count against, so it sends no rows and names
    itself. Nothing about R-K's fix may change this turn."""
    _seed_contact(
        session_factory,
        variables={
            "open_question": {
                "kind": "team_pick",
                "options": [{"idx": 1, "team": "warehouse", "label": "warehouse"}],
                "expects": "yes_no",
                "asked_at_turn": 2,
                "asked_at": None,
                "payload": {"team": "warehouse", "domain": "inventory"},
            }
        },
    )
    blocks: list[str] = []
    result, _calls = _run_turn(
        session_factory, monkeypatch, qf=_yes_v1(), text_body="yes",
        msg_id="ZZT-gr8-plain-offer", resolve_services=_exact_services(),
        capture_user_block=blocks, is_test=True,
    )
    assert result.status == "done", (result.status, result.error)
    assert not _open_question_options_fact(session_factory, result.turn_id), (
        "a one-team offer numbers nothing, so there is no roster to show"
    )
    assert "Open question options:" not in (blocks[-1] if blocks else ""), blocks
    pending = _pending_line(blocks[-1] if blocks else "")
    assert pending and "team_pick" in pending, pending


@pytest.mark.xfail(
    strict=False,
    reason=(
        "v20 prompt over-eager pick, issue filed. Turn 7e14db69: 'another one' over the "
        "ten-row incoming roster came back message_type casual, entities [], "
        "reference_positions [2], reference_target dym, entity_op reuse, user_goal "
        "'trying to pick another product option' - and the turn answered SRTWC286-SH-P, "
        "which is the re-pick AC-1020 and focus.yaml case H both forbid. It is written as "
        "an xfail rather than a red because NO head rule can separate it from a real pick "
        "without reading the customer's words (D11): under v20 a bare '8' is ALSO "
        "message_type casual with a position and nothing else - byte-identical shape, "
        "opposite meaning. The fix is the prompt's, not the engine's."
    ),
)
def test_a_casual_turn_that_names_nothing_mints_no_pick(session_factory, monkeypatch) -> None:
    """Turn 7e14db69's exact emission, pasted. The roster stays and nothing is picked."""
    roster = next(r for r in STICKY_ROSTERS if r.id == "multi-match-product")
    _seed_contact(session_factory, variables={"open_question": dict(roster.question)})
    result, _calls = _run_turn(
        session_factory, monkeypatch,
        qf=_parser_output(
            message_type="casual", intent_hint=None, domain_hint=None, entity_op="reuse",
            entities=[], asks=[], reference_positions=[2], reference_target="dym",
            is_affirmative=None, order_status=None,
            user_goal="trying to pick another product option",
        ),
        text_body="another one", msg_id="ZZT-gr7-another-one",
        resolve_services=_exact_services(), lanes=(*LANES, "low_signal"),
    )
    assert result.status in ("done", "delegated"), (result.status, result.error)
    assert not _picked_labels(session_factory, result.turn_id), (
        "'another one' names no row - the position the model volunteered for it must not "
        "become a pick"
    )
    alive = _stored_oq(_final_vars(session_factory, result))
    assert alive.get("kind") == "product_pick" and len(alive.get("options") or []) == 10, (
        f"and the roster the customer is still reading stays: {alive!r}"
    )


# =========================================================================== #
# GROUP 9 - R-M: a stray position over a head-resolved question mints a row
# LABEL into the turn's entities
#
# Turn 0b610e47, "only BRW" over an open `outstanding_detail` whose options were
# ["1. Delivery order list"]. The v20 emission (raw, verbatim):
#
#   message_type casual, domain_hint null, entity_op replace_combine, reference_target
#   "result", reference_positions [1],
#   entities [{raw "BRW", hint "warehouse", canonical_code null, current_message true}]
#
# and what the turn ENDED with:
#
#   entities [{raw "Delivery order list", hint "order", ordinal 1, canonical_code
#   "Delivery order list", current_message true}], outstanding_pending_dropped true
#
# Three steps, in order:
#
# 1. arm 1 (`output_exchange.py:1692`) vetoes the refinement because something was picked
#    (`picked is None` is part of its premise), so "only BRW" is not read as the narrowing
#    it plainly is;
# 2. arm 2 (:1706) then closes the question as a new ask on `names_entity`;
# 3. the generic REFERENCE POSITIONS -> ENTITIES block (:2648-2713) maps position 1 to the
#    row LABEL and overwrites `o["entities"]` wholesale (:2713) - so BRW is gone and
#    "Delivery order list" goes to the resolver, where "list" matches every SPECIALIST
#    customer. That is R-B's mechanism, and the good turn 40c57419 escaped it only because
#    arm 3's second pass happened to reset `entities` to [].
#
# The rulings, as the coder is implementing them: a position over a HEAD-RESOLVED kind
# (`outstanding_scope`, `outstanding_detail`) is never converted into an entity, keyed on
# the live question's kind; and what the MESSAGE NAMES decides the reading - only
# off-subject axes is a refinement whatever stray position rode along, nothing named plus
# a position is an answer, a subject-capable entity is a new ask.
# =========================================================================== #

_HEAD_RESOLVED_KINDS = ("outstanding_scope", "outstanding_detail")

#: The label of the row the stray position lands on, per kind - the token that must never
#: reach `o["entities"]` or the resolver.
_ROW_LABELS = {
    "outstanding_scope": "Sales orders",
    "outstanding_detail": "Sales order list",
}


def _seed_head_question(
    session_factory, kind: str, *, filters: dict[str, Any] | None = None
) -> None:
    options = (
        [
            {"idx": 1, "label": "Sales orders", "value": "so"},
            {"idx": 2, "label": "Delivery orders", "value": "do"},
            {"idx": 3, "label": "Both", "value": "both"},
        ]
        if kind == "outstanding_scope"
        else [
            {"idx": 1, "label": "Sales order list", "value": "so"},
            {"idx": 2, "label": "Delivery order list", "value": "do"},
            {"idx": 3, "label": "Both lists", "value": "both"},
        ]
    )
    _seed_contact(
        session_factory,
        variables={
            "open_question": _open_question(
                kind,
                options=options,
                filters=filters
                or {
                    "product_code": None,
                    "date_filter_start": None,
                    "date_filter_end": None,
                    "customer_ids": [CARRIED_CUSTOMER_UUID],
                    "warehouse_codes": [],
                    "location_token": None,
                    "scope": "both",
                },
            ),
            "focus": {"domains": _focus_slot(["order"])},
        },
    )


def _entities_of(result: Any) -> list[dict[str, Any]]:
    emission = ((result.ctx or {}).get("parse") or {}).get("output") or {}
    return [e for e in (emission.get("entities") or []) if isinstance(e, dict)]


def _no_row_label_anywhere(result: Any, tokens: list[str], *, label: str, case: str) -> None:
    """The label may not become an entity, and it may not be resolved as a token.

    Two readings of the same rule, and both are needed: the emission says whether the head
    MINTED it, the resolver log says whether it was ACTED on. Live turn 0b610e47 carries
    it on the emission to the very end, and that is how "list" reached six SPECIALIST
    customers.
    """
    minted = [
        e
        for e in _entities_of(result)
        if label.lower() in f"{e.get('raw')} {e.get('canonical_code')}".lower()
    ]
    assert not minted, (
        f"{case}: the row LABEL {label!r} was minted into this turn's entities - live "
        f"turn 0b610e47's own defect: {minted!r}"
    )
    asked = [t for t in tokens if label.lower() in t.lower()]
    assert not asked, (
        f"{case}: the row label {label!r} reached the resolver as a token, which is how "
        f"'list' matched every SPECIALIST customer (R-B): {tokens!r}"
    )


#: Whether (a)'s emission carries the volunteered position, PER KIND - and the difference
#: is not a convenience, it is what the live shape actually was.
#:
#: Turn 0b610e47 rode an `outstanding_detail` question whose options were ONE row
#: ("1. Delivery order list"), so a `[1]` beside "only BRW" is the model pointing at the
#: only thing on the screen while the customer narrows it. Over the THREE-option scope
#: question the same `[1]` would be the model choosing "Sales orders" out of nowhere -
#: prompt noise (issue #933), and the pin-consistent rule says a position ANSWERS
#: (`test_outstanding_lane::TestScopeAnswerRunsReportWithCarriedFilters::
#: test_a_date_in_the_answering_turn_wins_over_the_carried_one` and
#: `TestDateNarrowingUnderAnOpenOffer::test_a_pick_carrying_its_own_dates_still_picks`:
#: a position plus an off-subject filter answers WITH the filter applied, which is also
#: what this group's own (d) case requires). Keeping the noise here would have made (a)
#: and (d) demand opposite things of one emission, so the scope arm drops it and stays a
#: test about NARROWING. The answering-with-a-filter reading is (d)'s.
_A_POSITIONS = {"outstanding_detail": [1], "outstanding_scope": []}


@pytest.mark.parametrize("kind", _HEAD_RESOLVED_KINDS, ids=lambda k: k)
def test_rm_a_location_with_a_stray_position_narrows_and_mints_no_label(
    kind, session_factory, monkeypatch
) -> None:
    """(a) Turn 0b610e47's own shape: a warehouse entity the customer really named, over a
    question whose rows are on the screen. Only off-subject axes are named, so it is the
    refinement it looks like - and over the detail question, whose single row the model
    volunteered a position for, that holds whatever the stray position says."""
    _seed_brw_warehouse(session_factory)
    _seed_head_question(session_factory, kind)
    tokens: list[str] = []
    result, calls = _run_turn(
        session_factory, monkeypatch,
        qf=_parser_output(
            message_type="casual", intent_hint=None, domain_hint=None,
            entity_op="replace_combine", reference_positions=_A_POSITIONS[kind],
            reference_target="result",
            asks=[], entities=[_entity("BRW", "warehouse")],
            user_goal="trying to narrow it to BRW",
        ),
        text_body="only BRW", msg_id=f"ZZT-gr9-a-{kind}",
        attributes=["sales_orders.outstanding"],
        resolve_services=_exact_services(token_log=tokens),
        fetch_response=_report_call(REPORT_HIT),
    )
    assert result.status in ("done", "delegated"), (result.status, result.error)
    _no_row_label_anywhere(result, tokens, label=_ROW_LABELS[kind], case=f"{kind}/(a)")
    reply = (result.reply or {}).get("text") or ""
    final = _final_vars(session_factory, result)
    question = _stored_oq(final)
    assert question.get("kind") == kind, (
        f"{kind}: a refinement re-arms the same question over the narrower window "
        f"(AC-1157/AC-1158): {question!r}"
    )
    if kind == "outstanding_detail":
        # The scope is already known, so the narrowed report is what answers.
        reports = _report_tool_calls(calls)
        assert len(reports) == 1, (
            f"{kind}: the narrowing re-runs the report once: {calls!r}"
        )
        assert reports[0].get("warehouse_codes") == ["BRW"], (
            f"{kind}: narrowed to the location the customer named: {reports[0]!r}"
        )
        assert reports[0].get("customer_ids") == [CARRIED_CUSTOMER_UUID], (
            f"{kind}: with the stored subject intact: {reports[0]!r}"
        )
    else:
        # AC-1157's own shape for the SCOPE question, and the same thing
        # `test_outstanding_lane::test_a_date_only_turn_under_the_scope_question_reasks_
        # with_the_new_window` pins for a date: the document type is still unknown, so
        # nothing can be fetched - the question is re-asked with the filter overlaid on
        # its header, and the filter is what is carried.
        assert _report_tool_calls(calls) == [], (
            f"{kind}: the document type is still unknown, so a narrowing cannot fetch: "
            f"{calls!r}"
        )
        assert "Outstanding for which document?" in reply, reply
        assert "Location: BRW" in reply, (
            f"{kind}: the re-asked question shows the narrowing the customer just made: "
            f"{reply!r}"
        )
        filters_out = _stored_oq_filters(final)
        assert filters_out.get("warehouse_codes") == ["BRW"], filters_out
        assert filters_out.get("customer_ids") == [CARRIED_CUSTOMER_UUID], filters_out


@pytest.mark.parametrize("kind", _HEAD_RESOLVED_KINDS, ids=lambda k: k)
def test_rm_a_customer_with_a_stray_position_is_a_new_ask(
    kind, session_factory, monkeypatch
) -> None:
    """(b) D17 point 3, unchanged: a customer CAN be this report's subject, so naming one
    is a new question even with a position riding along - and the row label still never
    becomes an entity."""
    _seed_head_question(session_factory, kind)
    tokens: list[str] = []
    result, calls = _run_turn(
        session_factory, monkeypatch,
        qf=_parser_output(
            message_type="business_query", intent_hint=None, domain_hint=None,
            entity_op="replace_combine", reference_positions=[1], reference_target="result",
            asks=[], entities=[_entity("hanlim", "customer")],
            user_goal="trying to ask about hanlim's deliveries",
        ),
        text_body="1, delivery status for hanlim", msg_id=f"ZZT-gr9-b-{kind}",
        attributes=["sales_orders.outstanding"],
        resolve_services=_exact_services(
            single={
                "hanlim": {
                    "uuid": "cccccccc-cccc-cccc-cccc-cccccccccccc", "entity_type": "customer",
                    "canonical_code": "HANLIM", "match_tier": "exact", "company_name": "Sorento",
                }
            },
            token_log=tokens,
        ),
        fetch_response=_report_call(REPORT_HIT),
    )
    assert result.status in ("done", "delegated"), (result.status, result.error)
    _no_row_label_anywhere(result, tokens, label=_ROW_LABELS[kind], case=f"{kind}/(b)")
    for _name, args in _report_tool_calls(calls) and [
        (n, a) for n, a in calls if not n.startswith("probe:")
    ]:
        assert args.get("customer_ids") != [CARRIED_CUSTOMER_UUID], (
            f"{kind}: the customer named THIS turn is the new subject, not the stored one: "
            f"{args!r}"
        )
    question = _stored_oq(_final_vars(session_factory, result))
    assert question.get("kind") != kind or _stored_oq_filters(
        _final_vars(session_factory, result)
    ).get("customer_ids") != [CARRIED_CUSTOMER_UUID], (
        f"{kind}: a new ask drops the old question's filter set: {question!r}"
    )


@pytest.mark.parametrize("kind", _HEAD_RESOLVED_KINDS, ids=lambda k: k)
def test_rm_a_pure_position_is_the_answer_and_mints_no_label(
    kind, session_factory, monkeypatch
) -> None:
    """(c) Nothing named plus a position is the answer it has always been - and the row it
    lands on is read as a SCOPE, never minted as an entity to go looking for."""
    _seed_head_question(session_factory, kind)
    tokens: list[str] = []
    result, calls = _run_turn(
        session_factory, monkeypatch,
        qf=_parser_output(
            message_type="casual", intent_hint=None, domain_hint=None, entity_op="reuse",
            reference_positions=[2], reference_target="dym", asks=[], entities=[],
            user_goal="trying to choose delivery orders",
        ),
        text_body="2", msg_id=f"ZZT-gr9-c-{kind}",
        attributes=["sales_orders.outstanding"],
        resolve_services=_exact_services(token_log=tokens),
        fetch_response=_report_call(REPORT_HIT),
    )
    assert result.status in ("done", "delegated"), (result.status, result.error)
    _no_row_label_anywhere(
        result, tokens, label="Delivery order", case=f"{kind}/(c)"
    )
    reports = _report_tool_calls(calls)
    assert reports, f"{kind}: the answer runs the report: {calls!r}"
    if kind == "outstanding_scope":
        assert reports[0].get("scope") == "do", reports[0]
    else:
        assert reports[0].get("detail") == "do", reports[0]
    assert reports[0].get("customer_ids") == [CARRIED_CUSTOMER_UUID], reports[0]


def test_rm_a_scope_word_and_a_location_in_one_message_are_both_applied(
    session_factory, monkeypatch
) -> None:
    """(d) "2, only BRW" over the scope question: the customer answered AND narrowed in
    one message, and both halves have to land."""
    _seed_brw_warehouse(session_factory)
    _seed_head_question(session_factory, "outstanding_scope")
    tokens: list[str] = []
    result, calls = _run_turn(
        session_factory, monkeypatch,
        qf=_parser_output(
            message_type="casual", intent_hint=None, domain_hint=None,
            entity_op="replace_combine", reference_positions=[2], reference_target="result",
            asks=[], entities=[_entity("BRW", "warehouse")],
            user_goal="trying to choose delivery orders and narrow to BRW",
        ),
        text_body="2, only BRW", msg_id="ZZT-gr9-d",
        attributes=["sales_orders.outstanding"],
        resolve_services=_exact_services(token_log=tokens),
        fetch_response=_report_call(REPORT_HIT),
    )
    assert result.status in ("done", "delegated"), (result.status, result.error)
    _no_row_label_anywhere(result, tokens, label="Delivery orders", case="scope/(d)")
    reports = _report_tool_calls(calls)
    assert len(reports) == 1, f"one report call: {calls!r}"
    assert reports[0].get("scope") == "do", (
        f"'2' is the DO scope, and it was answered: {reports[0]!r}"
    )
    assert reports[0].get("warehouse_codes") == ["BRW"], (
        f"and the location the same message named was applied: {reports[0]!r}"
    )
    assert reports[0].get("customer_ids") == [CARRIED_CUSTOMER_UUID], (
        f"with the stored subject intact: {reports[0]!r}"
    )
    question = _stored_oq(_final_vars(session_factory, result))
    assert question.get("kind") != "outstanding_scope", (
        f"the scope question was ANSWERED, so it is not re-asked: {question!r}"
    )


# =========================================================================== #
# GROUP 10 - S-1: every composer that PRINTS the sentence records the offer
#
# The fix records the offer at the COMPOSER, and deliberately with NO text fallback: the
# team travels with the fact instead of being read back out of the reply, so
# `team_from_reply` becomes a parity check rather than the source. That makes a composer
# which prints the sentence and records nothing a SILENT failure - the customer reads an
# offer and their "yes" resolves nothing (which is R-I all over again). One case per
# top-level composer, each driven through the real turn path with a shape that makes it
# print, so a new composer cannot be added without one.
#
# The seven declared sites, and where each is covered:
#
# | composer | covered by |
# |---|---|
# | `answer.promo_picker` (~1576, `esc_team` ~1618) | `promo-entitlement-miss` below |
# | `answer.not_found_error_message` (~2388, `team` ~2550) | `stock-miss` below |
# | `answer.build_suggest_offer` (~3304, `team` ~3344) | `did-you-mean` below |
# | `compile_state`'s two miss arms (:2903 / :2942) | group 1's `miss` arm (the plain arm appends the phrase there) |
# | `compose.crossdomain_compose` (:104) | group 1's `crossdomain-ladder` arm |
# | `member_offer.py` (:294) | group 1c's `member-offer` case |
# =========================================================================== #


def _build_promo_entitlement_miss(session_factory, monkeypatch, tag: str):
    """`promo_picker`'s own arm: the promotion RESOLVED and is not available at this
    contact's level, so the picker composes the refusal and the offer itself."""
    _seed_contact(session_factory, variables={})
    services = _exact_services(
        single={
            "a3 flyer": {
                "uuid": "66666666-1111-1111-1111-111111111111",
                "entity_type": "promotion",
                "canonical_code": "PROMO-1",
                "match_tier": "exact",
                "company_name": "Sorento",
                "display": {"description": "SORENTO A3 FLYER 2026", "is_active": True},
            }
        }
    )
    result, _calls = _run_turn(
        session_factory, monkeypatch,
        qf=_qf([_entity("a3 flyer", "promotion")], domain="promotion",
               intent_hint="check_promotion", access_levels=["Dealer"]),
        text_body="promo a3 flyer", msg_id=f"ZZT-gr10-promo-{tag}", lanes=PROMO_LANES,
        resolve_services=services,
        fetch_response={
            "result_type": "promotion", "intro": "I found 1 promotion.",
            "items": [], "answers": [], "has_result": False,
        },
    )
    return (result.reply or {}).get("text") or "", services


def _build_did_you_mean_offer(session_factory, monkeypatch, tag: str):
    """`build_suggest_offer`: a near-miss ATTACHMENT TYPE beside a resolved product.

    `attachment_type` is not one of `_QUERIED_TYPES`, so its candidates are not treated as
    "already answered over" and survive into the did-you-mean offer - which is how this
    composer's own sentence ("or would you like me to escalate to X team?", the lower-case
    variant) gets printed on a turn a test can drive.
    """
    _seed_contact(session_factory, variables={})
    services = _exact_services(
        single={
            PROMO_CODE: {
                "uuid": PROMO_UUID, "entity_type": "product", "canonical_code": PROMO_CODE,
                "match_tier": "exact", "company_name": "Sorento",
            }
        },
        multi={
            "photoo": [
                {
                    "uuid": f"7777777{i}-1111-1111-1111-111111111111",
                    "entity_type": "attachment_type",
                    "canonical_code": name,
                    "match_tier": "trgm",
                    "company_name": None,
                    "display": {"description": name},
                }
                for i, name in enumerate(("Product Photos", "Product Photos 3D"), start=1)
            ]
        },
    )
    result, _calls = _run_turn(
        session_factory, monkeypatch,
        qf=_qf([_entity(PROMO_CODE, "product"), _entity("photoo", "attachment_type")],
               domain="product_attachment", intent_hint="check_product_attachment",
               requested_attributes=["attachment"]),
        text_body=f"photoo for {PROMO_CODE}", msg_id=f"ZZT-gr10-dym-{tag}",
        resolve_services=services,
    )
    return (result.reply or {}).get("text") or "", services


COMPOSER_ARMS = (
    OfferArm("stock-miss", roster=False, lanes=LANES, build=_build_miss_arm),
    OfferArm(
        "promo-entitlement-miss", roster=False, lanes=PROMO_LANES,
        build=_build_promo_entitlement_miss,
    ),
    OfferArm("did-you-mean", roster=True, lanes=LANES, build=_build_did_you_mean_offer),
)


@pytest.mark.parametrize("arm", COMPOSER_ARMS, ids=lambda a: a.id)
def test_s1_the_composer_that_printed_the_offer_recorded_it(
    arm, session_factory, monkeypatch
) -> None:
    """Printed and recorded, per composer. `_printed_team` is the READER used to say what
    the customer was promised; the assertion is on the RECORDED question, because that is
    what the fix moves - so this stays true when the text stops being the source."""
    reply, _services = arm.build(session_factory, monkeypatch, "rec")
    printed = _printed_team(reply)
    assert printed, (
        f"arm {arm.id!r} is only itself if this composer printed its offer: {reply!r}"
    )
    question = _stored_oq(_vars(session_factory))
    recorded = _recorded_team(question)
    assert recorded, (
        f"arm {arm.id!r}: the composer printed an offer for {printed!r} and recorded "
        f"nothing - with no text fallback the customer's yes resolves nothing: "
        f"{question!r}"
    )
    assert _pretty(recorded) == printed, (
        f"arm {arm.id!r}: printed {printed!r}, recorded {recorded!r}: {question!r}"
    )


@pytest.mark.parametrize("arm", COMPOSER_ARMS, ids=lambda a: a.id)
def test_s1_a_yes_after_each_composers_offer_routes_to_its_team(
    arm, session_factory, monkeypatch
) -> None:
    """And the whole point of recording it: the next bare "yes" reaches that team."""
    reply, services = arm.build(session_factory, monkeypatch, "yes")
    printed = _printed_team(reply)
    result, _calls = _run_turn(
        session_factory, monkeypatch, qf=_yes_v1(), text_body="yes",
        msg_id=f"ZZT-gr10-yes-{arm.id}", resolve_services=services, lanes=arm.lanes,
        is_test=True,
    )
    assert result.status == "done", (result.status, result.error)
    teams = _comment_teams(result)
    assert teams == [_pretty(printed).replace(" ", "_")], (
        f"arm {arm.id!r}: the reply promised {printed!r} and the escalation was filed "
        f"against {teams!r}"
    )
