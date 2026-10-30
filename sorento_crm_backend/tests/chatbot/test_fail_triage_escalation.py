"""CHATBOT-FAIL-TRIAGE AC-7 red tests: escalation routes to a reachable team, never a default.

UAC `documentation/plans/chatbot/chatbot-fail-triage-acceptance-criteria.md`, AC-7a to AC-7e
(AC-7f is a prompt change and is not tested here). Owner, 30 Oct 2026: "we shouldn't do no
topic escalate to marketing product, we should clarify". No default team, ever.

Every test drives `engine.run_turn` with the parser stubbed at its provider seam
(`test_engine.stub_parser`) and the escalation lane running for real. The lane's two CRM
calls are observed at their own boundary, the way `test_escalation_agent_carry.py` does:

* `/external/next-assignee` is WRAPPED, not replaced. The real handler runs over the
  `agent_teams` rows each test seeds for the contact's company, so an unreachable
  (agent, team) pair 404s exactly as it did in production (17 failed escalations,
  backup 1028). Every body is recorded with its outcome.
* `ConversationSLATrackingService.create_tracking` is stubbed (recorded), or made to raise
  the production SLA 400 for AC-7d.

Postgres only (the blank-schema `session_factory`); every company, contact, agent, team,
member and SLA policy is seeded here. No customer names or phones from production.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from sqlalchemy import text

import app.main  # noqa: F401  isort:skip - registers every model before any query

from app.services.chatbot import engine as engine_mod
from app.services.chatbot import label_catalog
from app.services.chatbot.contracts import DEFAULT_SUGGESTED_AGENT, DEFAULT_SUGGESTED_TEAM
from app.services.chatbot.tail.outcome import pretty_team
from app.services.chatbot.turn import pending as pending_mod
from tests.chatbot import fail_triage_texts as T
from tests.chatbot._turn_helpers import verdict
from tests.chatbot.test_engine import CONTACT_ID, _envelope, stub_access, stub_parser  # noqa: F401 - fixtures

SORENTO = "00000000-0000-0000-0000-000000000001"
SPACE_ID = "364817"  # the literal `stub_access()` points `engine.default_space_id` at
MS_TEXT = "tolong ya saya nak tahu"  # detected `ms` (`language.detect`), as in the R1 tests

# AC-7a: the parser's R-X-08 map, one (agent, team) PAIR per topic domain.
DOMAIN_PAIR: dict[str, tuple[str, str]] = {
    "order": ("order_enquiries", "customer_service"),
    "incoming": ("incoming_stock_enquiries", "purchasing"),
    "master_products": ("general_enquiries", "purchasing"),
    "inventory": ("general_enquiries", "warehouse"),
    "product_attachment": ("general_enquiries", "marketing_product"),
    "promotion": ("general_enquiries", "marketing_promotion"),
    "forms": ("marketing_form", "marketing_form"),
}

# AC-7c: the clarify's quick replies, worded as the UAC lists them (compared lower-case).
TOPIC_ORDERS = "orders & delivery"
TOPIC_STOCK = "stock & eta"
TOPIC_PRODUCT = "product info"
TOPIC_PROMOTIONS = "promotions"
TOPIC_FORMS = "forms"


# --------------------------------------------------------------------------- #
# Seeding
# --------------------------------------------------------------------------- #


def _db(session_factory, company_id: str = SORENTO):
    db = session_factory()
    db.info["company_scope"] = frozenset({company_id})
    return db


def _seed_company(session_factory, name: str) -> str:
    from app.models.company import Company

    db = _db(session_factory)
    company_id = str(uuid.uuid4())
    db.add(Company(id=company_id, name=name, code=f"Z{uuid.uuid4().hex[:7].upper()}"))
    db.commit()
    return company_id


def _seed_contact(session_factory, *, phone: str, company_id: str) -> None:
    """The contact, in the default workspace, belonging to ONE company (so both the turn's
    company scope and next-assignee's routing company resolve to it)."""
    from app.models.respond_workspace import RespondWorkspace

    db = _db(session_factory)
    workspace = RespondWorkspace(space_id=SPACE_ID, name="ZZT AC-7 workspace", api_key_ciphertext="ZZT-cipher")
    db.add(workspace)
    db.commit()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars, workspace_id) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb), :wid)"
        ),
        {"cid": str(CONTACT_ID), "phone": phone, "sv": json.dumps({}), "wid": workspace.id},
    )
    db.commit()
    row = db.execute(
        text("SELECT id FROM respond_contacts WHERE respond_io_id = :c"), {"c": str(CONTACT_ID)}
    ).first()
    db.execute(
        text(
            "INSERT INTO respond_contact_companies (id, respond_contact_id, company_id) "
            "VALUES (gen_random_uuid(), :rcid, :co)"
        ),
        {"rcid": row.id, "co": company_id},
    )
    db.commit()


def _seed_pair(session_factory, *, company_id: str, agent_code: str, team_code: str) -> str:
    """One `agent_teams` link (tier 1) for `company_id`, with a team, one active member and
    the company's NORMAL SLA policy - everything the real next-assignee draw needs.
    Returns the member's user id."""
    from app.models.access import AccessAgent, AgentTeam, Team, TeamMember
    from app.models.sla import SLAPolicy, SLAPolicyTier
    from app.models.user import User
    from app.services.chatbot.lanes.escalation import NEXT_ASSIGNEE_POLICY_CODE, NEXT_ASSIGNEE_TIER

    db = _db(session_factory, company_id)
    agent = db.query(AccessAgent).filter(AccessAgent.code == agent_code).first()
    if agent is None:
        agent = AccessAgent(id=str(uuid.uuid4()), code=agent_code, name=f"ZZT {agent_code}", is_active=True)
        db.add(agent)
        db.flush()
    policy = (
        db.query(SLAPolicy)
        .filter(SLAPolicy.code == NEXT_ASSIGNEE_POLICY_CODE, SLAPolicy.company_id == company_id)
        .first()
    )
    if policy is None:
        policy = SLAPolicy(
            id=str(uuid.uuid4()), code=NEXT_ASSIGNEE_POLICY_CODE, name="ZZT Normal", is_active=True, company_id=company_id
        )
        db.add(policy)
        db.flush()
        db.add(
            SLAPolicyTier(
                id=str(uuid.uuid4()),
                policy_id=policy.id,
                tier_level=NEXT_ASSIGNEE_TIER,
                tier_name="ZZT Tier 1",
                response_hours=4,
                resolution_hours=24,
            )
        )
        db.flush()
    team_id = str(uuid.uuid4())
    db.add(Team(id=team_id, name=f"ZZT {team_code}", company_id=company_id))
    user_id = str(uuid.uuid4())
    db.add(
        User(
            id=user_id,
            email=f"zzt-ac7-{uuid.uuid4().hex[:8]}@zzt.test",
            name=f"ZZT {team_code} PIC",
            status="ACTIVE",
            respond_user_id=str(uuid.uuid4().int)[:9],
        )
    )
    db.flush()
    db.add(TeamMember(id=str(uuid.uuid4()), team_id=team_id, user_id=user_id, sort_order=1))
    db.add(
        AgentTeam(
            id=str(uuid.uuid4()),
            agent_id=agent.id,
            code=team_code,
            team_id=team_id,
            tier=NEXT_ASSIGNEE_TIER,
            company_id=company_id,
        )
    )
    db.commit()
    return user_id


# --------------------------------------------------------------------------- #
# The lane's two CRM seams, observed
# --------------------------------------------------------------------------- #


class Seams:
    def __init__(self) -> None:
        self.assignee: list[dict[str, Any]] = []  # {"body", "response" | "error"}
        self.sla: list[Any] = []

    def live_bodies(self) -> list[dict[str, Any]]:
        """Every real (non-preview) draw the lane asked for."""
        return [c["body"] for c in self.assignee if c["body"].get("preview") is not True]

    def pairs(self) -> list[tuple[Any, Any]]:
        return [(b.get("agent_code"), b.get("team_code")) for b in self.live_bodies()]

    def errors(self) -> list[str]:
        return [c["error"] for c in self.assignee if "error" in c]


def _observe(monkeypatch, *, assignee_error: Exception | None = None, sla_error: Exception | None = None) -> Seams:
    import app.api.v1.external.next_assignee as next_assignee_mod
    from app.services.sla_service import ConversationSLATrackingService

    seams = Seams()
    real = next_assignee_mod.post_next_assignee

    def wrapped(body: dict, current_user: dict = None, db: Any = None):
        record: dict[str, Any] = {"body": dict(body)}
        seams.assignee.append(record)
        try:
            if assignee_error is not None and body.get("preview") is not True:
                raise assignee_error
            response = real(body=body, current_user=current_user, db=db)
        except Exception as exc:
            record["error"] = repr(exc)
            raise
        record["response"] = dict(response)
        return response

    def create_tracking(self, payload: Any) -> Any:
        seams.sla.append(payload)
        if sla_error is not None:
            raise sla_error
        return type("ZztSla", (), {"id": "zzt-sla", "initiated_at": None, "due_at": None, "due_at_resolution": None})()

    monkeypatch.setattr(next_assignee_mod, "post_next_assignee", wrapped)
    monkeypatch.setattr(ConversationSLATrackingService, "create_tracking", create_tracking)
    return seams


def _quiet_mcp(monkeypatch) -> None:
    """Any business fetch answers "nothing" (no network)."""
    from app.services.ai_assistant_service import MCPRuntimeClient

    monkeypatch.setattr(MCPRuntimeClient, "call_tool", lambda self, name, arguments: json.dumps({"answers": []}))


# --------------------------------------------------------------------------- #
# Turns
# --------------------------------------------------------------------------- #


def _say(message_id: str, words: str):
    return _envelope(
        message={
            "event_type": "message.received",
            "contact": {"id": CONTACT_ID},
            "message": {
                "messageId": message_id,
                "contactId": CONTACT_ID,
                "channelId": "whatsapp",
                "traffic": "incoming",
                "message": {"type": "text", "text": words},
            },
        }
    )


def _help(**overrides: Any) -> dict[str, Any]:
    """A request for a person; the parser routed nowhere unless a test says so."""
    return verdict(message_type="request_for_help", **overrides)


def _yes() -> dict[str, Any]:
    """A bare "Yes" over an open offer: no domain, no entities, no routing of its own."""
    return verdict(
        message_type="casual",
        is_affirmative=True,
        escalation={"is_escalation_confirmation": True, "escalation_declined": None, "company_pick": None},
    )


def _pick(position: int) -> dict[str, Any]:
    """A numbered pick ("1") over an open question: no domain, no routing of its own."""
    return verdict(message_type="casual", reference_positions=[position])


def _session_vars(session_factory) -> dict[str, Any]:
    row = session_factory().execute(
        text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :c"), {"c": str(CONTACT_ID)}
    ).first()
    return dict(row.session_vars or {})


def _set_open_question(session_factory, open_question: dict[str, Any] | None, *, focus: Any = "keep") -> None:
    """Write the open question an earlier turn left, keeping whatever else that turn saved
    (its focus, i.e. the held topic) unless `focus` is given."""
    current = _session_vars(session_factory)
    base = {"focus": None, "ideation": None, "access_levels": [], "contains_flyer": False}
    merged = {**base, **current, "open_question": open_question}
    if focus != "keep":
        merged["focus"] = focus
    db = session_factory()
    db.execute(
        text("UPDATE respond_contacts SET session_vars = CAST(:sv AS jsonb) WHERE respond_io_id = :c"),
        {"sv": json.dumps(merged), "c": str(CONTACT_ID)},
    )
    db.commit()


def _sends(result) -> list[dict[str, Any]]:
    return [a for a in result.actions if a.get("kind") == "send_message"]


def _assigned(result) -> bool:
    return any(a.get("kind") == "assign_conversation" for a in result.actions)


def _reply_text(result) -> str:
    texts = [a.get("text") or "" for a in _sends(result)]
    return "\n".join(texts) or (result.reply or {}).get("text") or ""


def _quick_replies(result) -> list[str]:
    out: list[str] = []
    for action in _sends(result):
        raw = action.get("quick_replies")
        if isinstance(raw, str):
            out.extend(s.strip().lower() for s in raw.split(",") if s.strip())
        elif isinstance(raw, list):
            out.extend(str(s).strip().lower() for s in raw if str(s).strip())
    return out


def _is_esc_failure(words: str) -> bool:
    return "could not pass this to the" in words.lower() or "tidak dapat menyerahkan" in words.lower()


# --------------------------------------------------------------------------- #
# Fixture control (passes today): the seeded pair is drawable through the real handler
# --------------------------------------------------------------------------- #


def test_control_a_parser_named_reachable_pair_assigns_through_the_real_handler(
    session_factory, stub_parser, stub_access, monkeypatch
) -> None:
    """Not an AC: proves the seed (agent_teams + member + SLA policy per company) is enough
    for the real next-assignee draw, so the AC tests below are red for routing, not seeding."""
    company = _seed_company(session_factory, "ZZT Company Order")
    _seed_contact(session_factory, phone="+60970000001", company_id=company)
    _seed_pair(session_factory, company_id=company, agent_code="order_enquiries", team_code="customer_service")
    seams = _observe(monkeypatch)
    stub_parser(
        _help(domain_hint="order", routing={"suggested_team": "customer_service", "suggested_agent": "order_enquiries"})
    )
    stub_access()

    result = engine_mod.run_turn(_say("ac7-ctl-1", "please ask someone about my order"), session_factory=session_factory)

    assert seams.pairs() == [("order_enquiries", "customer_service")], seams.assignee
    assert not seams.errors(), seams.errors()
    assert _assigned(result), result.actions


# --------------------------------------------------------------------------- #
# AC-7a  one (agent, team) pair from the topic's domain, reachable for the company
# --------------------------------------------------------------------------- #


def test_ac7a_an_order_escalation_routes_to_order_enquiries_and_customer_service(
    session_factory, stub_parser, stub_access, monkeypatch
) -> None:
    company = _seed_company(session_factory, "ZZT Company Order")
    _seed_contact(session_factory, phone="+60970000002", company_id=company)
    _seed_pair(session_factory, company_id=company, agent_code="order_enquiries", team_code="customer_service")
    # The default agent exists, linked to another team only: general_enquiries has no
    # customer_service link here (the production shape behind the 404s).
    _seed_pair(session_factory, company_id=company, agent_code="general_enquiries", team_code="warehouse")
    seams = _observe(monkeypatch)
    stub_parser(_help(domain_hint="order"))  # the topic is order; the parser routed nowhere
    stub_access()

    result = engine_mod.run_turn(_say("ac7a-1", "can someone help me with my order"), session_factory=session_factory)

    assert seams.pairs() == [DOMAIN_PAIR["order"]], (
        f"an order escalation goes to the order pair, never the default agent "
        f"{DEFAULT_SUGGESTED_AGENT!r}: {seams.assignee!r}"
    )
    assert not seams.errors(), seams.errors()
    assert _assigned(result), result.actions
    assert not _is_esc_failure(_reply_text(result)), _reply_text(result)


@pytest.mark.parametrize(
    "routing",
    [
        {"suggested_team": None, "suggested_agent": None},
        # the parser filled the R-X-08 pair itself, which this company cannot reach
        {"suggested_team": "purchasing", "suggested_agent": "general_enquiries"},
    ],
    ids=["parser_routed_nowhere", "parser_filled_the_map_pair"],
)
def test_ac7a_an_unreachable_pair_is_never_sent_mocha_shape(
    session_factory, stub_parser, stub_access, monkeypatch, routing
) -> None:
    """Mocha (UAC AC-7a): general_enquiries is linked to purchasing_product there, NOT to
    purchasing, so the master_products pair (general_enquiries, purchasing) is unreachable
    for this contact. The same pair DOES exist in another company, so only a per-company
    check tells them apart. Offer a reachable pair or clarify; never the unreachable pair
    and never a next-assignee 404 failure reply."""
    mocha_like = _seed_company(session_factory, "ZZT Company Two")
    _seed_contact(session_factory, phone="+60970000003", company_id=mocha_like)
    _seed_pair(session_factory, company_id=mocha_like, agent_code="general_enquiries", team_code="purchasing_product")
    _seed_pair(session_factory, company_id=mocha_like, agent_code="order_enquiries", team_code="customer_service")
    _seed_pair(session_factory, company_id=SORENTO, agent_code="general_enquiries", team_code="purchasing")
    reachable = {("general_enquiries", "purchasing_product"), ("order_enquiries", "customer_service")}
    seams = _observe(monkeypatch)
    stub_parser(_help(domain_hint="master_products", routing=routing))
    stub_access()

    result = engine_mod.run_turn(
        _say("ac7a-2", "I need someone to check this product for me"), session_factory=session_factory
    )

    words = _reply_text(result)
    assert ("general_enquiries", "purchasing") not in seams.pairs(), seams.assignee
    assert set(seams.pairs()) <= reachable, f"only a pair linked for the contact's company: {seams.assignee!r}"
    assert not seams.errors(), f"no next-assignee failure: {seams.errors()!r}"
    assert not _is_esc_failure(words), words
    T.assert_no_banned_text(words)


# --------------------------------------------------------------------------- #
# AC-7b  the topic is carried from earlier turns
# --------------------------------------------------------------------------- #


def _order_turn_one(session_factory, stub_parser, stub_access, monkeypatch) -> Seams:
    """A real first turn about delivery orders; it leaves the order topic in the session."""
    company = _seed_company(session_factory, "ZZT Company Order")
    _seed_contact(session_factory, phone="+60970000004", company_id=company)
    _seed_pair(session_factory, company_id=company, agent_code="order_enquiries", team_code="customer_service")
    _seed_pair(session_factory, company_id=company, agent_code="general_enquiries", team_code="warehouse")
    _quiet_mcp(monkeypatch)
    seams = _observe(monkeypatch)
    stub_parser(verdict(domain_hint="order", intent_hint="check_order", status="pending", document=["delivery_order"]))
    stub_access()
    first = engine_mod.run_turn(_say("ac7b-1", "any pending delivery order"), session_factory=session_factory)
    assert first.branch_kind == "business_query", (first.branch_kind, _reply_text(first))
    assert seams.assignee == [], "turn 1 is a question, not an escalation"
    return seams


def test_ac7b_yes_to_an_offer_routes_by_the_held_order_topic(
    session_factory, stub_parser, stub_access, monkeypatch
) -> None:
    seams = _order_turn_one(session_factory, stub_parser, stub_access, monkeypatch)
    # The escalate offer the order answer put on screen ("Would you like me to escalate to
    # customer service team?"), minted by the real mint function with no agent recorded:
    # the topic, not a default, has to supply the agent on the "Yes".
    offer = pending_mod.ask(
        "team_pick",
        [{"position": 1, "label": "Yes", "entity_type": "team", "payload": {}}],
        team="customer_service",
        expects="yes_no",
        payload={"agent": None, "brand_code": None},
    )
    _set_open_question(session_factory, pending_mod.to_wire(offer))
    stub_parser(_yes())

    result = engine_mod.run_turn(_say("ac7b-2", "Yes"), session_factory=session_factory)

    assert seams.pairs() == [DOMAIN_PAIR["order"]], (
        f"the 'Yes' routes by the held order topic, never ({DEFAULT_SUGGESTED_AGENT!r}, ...): {seams.assignee!r}"
    )
    assert not seams.errors(), seams.errors()
    assert _assigned(result), result.actions


def test_ac7b_a_follow_up_asking_for_a_person_routes_by_the_held_order_topic(
    session_factory, stub_parser, stub_access, monkeypatch
) -> None:
    seams = _order_turn_one(session_factory, stub_parser, stub_access, monkeypatch)
    stub_parser(_help())  # "can someone call me": no domain, no routing this turn

    result = engine_mod.run_turn(_say("ac7b-3", "can someone call me about this"), session_factory=session_factory)

    assert seams.pairs() == [DOMAIN_PAIR["order"]], (
        f"no topic this turn, the held one is order: never the default {DEFAULT_SUGGESTED_TEAM!r}/"
        f"{DEFAULT_SUGGESTED_AGENT!r} pair: {seams.assignee!r}"
    )
    assert not seams.errors(), seams.errors()
    assert _assigned(result), result.actions


# --------------------------------------------------------------------------- #
# AC-7c  no topic, none held: ONE short clarifying question over the reachable topics
# --------------------------------------------------------------------------- #


def _no_topic_company(session_factory) -> None:
    company = _seed_company(session_factory, "ZZT Company Three")
    _seed_contact(session_factory, phone="+60970000005", company_id=company)
    # Reachable: orders & delivery, promotions, forms. NOT reachable: stock & ETA (no
    # warehouse, no incoming pair) and product info (no purchasing, no marketing_product).
    _seed_pair(session_factory, company_id=company, agent_code="order_enquiries", team_code="customer_service")
    _seed_pair(session_factory, company_id=company, agent_code="general_enquiries", team_code="marketing_promotion")
    _seed_pair(session_factory, company_id=company, agent_code="marketing_form", team_code="marketing_form")


def test_ac7c_no_topic_asks_one_question_with_the_reachable_topics(
    session_factory, stub_parser, stub_access, monkeypatch
) -> None:
    _no_topic_company(session_factory)
    seams = _observe(monkeypatch)
    stub_parser(_help())
    stub_access()

    result = engine_mod.run_turn(_say("ac7c-1", "I want to talk to a person"), session_factory=session_factory)

    assert seams.live_bodies() == [], (
        f"nothing is assigned on a turn with no topic (no {DEFAULT_SUGGESTED_TEAM!r} default): {seams.assignee!r}"
    )
    assert seams.sla == [], "no SLA row without an assignment"
    assert not _assigned(result), result.actions
    sends = _sends(result)
    assert len(sends) == 1, sends
    words = sends[0].get("text") or ""
    T.assert_no_banned_text(words)
    assert not _is_esc_failure(words), words
    assert words.count("?") == 1 and len(words) <= 200, f"one short clarifying question: {words!r}"
    offered = set(_quick_replies(result))
    assert {TOPIC_ORDERS, TOPIC_PROMOTIONS, TOPIC_FORMS} <= offered, offered
    assert not offered & {TOPIC_STOCK, TOPIC_PRODUCT}, f"only topics the company can reach: {offered!r}"


def test_ac7c_the_answer_to_the_topic_question_routes_to_that_topics_pair(
    session_factory, stub_parser, stub_access, monkeypatch
) -> None:
    _no_topic_company(session_factory)
    seams = _observe(monkeypatch)
    stub_parser(_help())
    stub_access()
    engine_mod.run_turn(_say("ac7c-2", "I want to talk to a person"), session_factory=session_factory)
    assert seams.live_bodies() == [], f"turn 1 assigns nobody: {seams.assignee!r}"

    open_question = _session_vars(session_factory).get("open_question") or {}
    orders = [
        o for o in (open_question.get("options") or [])
        if TOPIC_ORDERS in str(o.get("label") or "").lower()
    ]
    assert len(orders) == 1, f"the topic question stays open with an orders option: {open_question!r}"
    stub_parser(_pick(int(orders[0]["position"])))

    result = engine_mod.run_turn(_say("ac7c-3", "Orders & delivery"), session_factory=session_factory)

    assert seams.pairs() == [DOMAIN_PAIR["order"]], seams.assignee
    assert not seams.errors(), seams.errors()
    assert _assigned(result), result.actions


# --------------------------------------------------------------------------- #
# AC-7d  a failed escalation names the OFFERED team, in the contact's language
# --------------------------------------------------------------------------- #


def _failure(kind: str) -> dict[str, Exception]:
    from fastapi import HTTPException

    from app.services.error_handler import handle_validation_error

    if kind == "assignee_404":
        return {"assignee_error": HTTPException(status_code=404, detail="preferred assignee is not a member of the team")}
    return {
        "sla_error": handle_validation_error(
            "No SLA policy bound for agent 'general_enquiries' / team set 'marketing_promotion'."
        )
    }


@pytest.mark.parametrize("kind", ["assignee_404", "sla_400"])
def test_ac7d_a_failed_escalation_names_the_offered_team_in_malay(
    session_factory, stub_parser, stub_access, monkeypatch, kind
) -> None:
    company = _seed_company(session_factory, "ZZT Company Promo")
    _seed_contact(session_factory, phone="+60970000006", company_id=company)
    _seed_pair(session_factory, company_id=company, agent_code="general_enquiries", team_code="marketing_promotion")
    seams = _observe(monkeypatch, **_failure(kind))
    # The offer on screen named the marketing promotion team (a promotion answer's escalate
    # offer); the acceptance itself names no team.
    offer = pending_mod.ask(
        "team_pick",
        [{"position": 1, "label": "Yes", "entity_type": "team", "payload": {}}],
        team="marketing_promotion",
        expects="yes_no",
        payload={"agent": "general_enquiries", "brand_code": None},
    )
    _set_open_question(session_factory, pending_mod.to_wire(offer), focus={"domains": ["promotion"]})
    stub_parser(_yes())
    stub_access()

    result = engine_mod.run_turn(_say("ac7d-1", MS_TEXT), session_factory=session_factory)

    expected = label_catalog.LABELS[T.H_ESC]["ms"].format(team=pretty_team("marketing_promotion"))
    assert seams.pairs() == [DOMAIN_PAIR["promotion"]], seams.assignee
    assert not _assigned(result), result.actions
    assert result.reply["text"] == expected, result.reply["text"]
    assert [a.get("text") for a in _sends(result)] == [expected], result.actions


# --------------------------------------------------------------------------- #
# AC-7e  a company (or team) pick never becomes `preferred_assignee_id`
# --------------------------------------------------------------------------- #


def _offered(values: dict[str, Any], outcome: dict[str, Any] | None = None) -> dict[str, Any]:
    """The open question the escalation lane's own clarify leaves, minted by the real
    `engine._question_offered` (so each option carries the `uuid` it really carries)."""
    ctx = {
        "parse": {"output": {"routing": {"suggested_team": "customer_service", "suggested_agent": "order_enquiries"}}},
        "session": {},
    }
    question = engine_mod._question_offered(ctx, values, outcome or {}, {})
    assert question is not None
    return pending_mod.to_wire(question)


def test_ac7e_a_company_pick_is_never_sent_as_preferred_assignee_id(
    session_factory, stub_parser, stub_access, monkeypatch
) -> None:
    company = _seed_company(session_factory, "ZZT Company Order")
    other = _seed_company(session_factory, "ZZT Company Other")
    _seed_contact(session_factory, phone="+60970000007", company_id=company)
    _seed_pair(session_factory, company_id=company, agent_code="order_enquiries", team_code="customer_service")
    seams = _observe(monkeypatch)
    _set_open_question(
        session_factory,
        _offered(
            {
                "clarify": {
                    "clarify_text": "Both *ZZT Company Order* and *ZZT Company Other* teams are listed - reply with the company.",
                    "team": "customer_service",
                    "clarify_company_options": [
                        {"idx": 1, "company_id": company, "company_name": "ZZT Company Order", "brand_code": None},
                        {"idx": 2, "company_id": other, "company_name": "ZZT Company Other", "brand_code": None},
                    ],
                }
            }
        ),
    )
    stub_parser(_pick(1))
    stub_access()

    result = engine_mod.run_turn(_say("ac7e-1", "1"), session_factory=session_factory)

    bodies = seams.live_bodies()
    assert bodies, f"the company pick escalates: {result.actions!r}"
    for body in bodies:
        assert body.get("preferred_assignee_id") not in (company, other), body
        assert not body.get("preferred_assignee_id"), f"a company is not a person: {body!r}"
    assert not seams.errors(), seams.errors()
    assert _assigned(result), result.actions


def test_ac7e_a_team_pick_is_never_sent_as_preferred_assignee_id(
    session_factory, stub_parser, stub_access, monkeypatch
) -> None:
    company = _seed_company(session_factory, "ZZT Company Order")
    _seed_contact(session_factory, phone="+60970000008", company_id=company)
    _seed_pair(session_factory, company_id=company, agent_code="order_enquiries", team_code="customer_service")
    seams = _observe(monkeypatch)
    _set_open_question(
        session_factory,
        _offered(
            {
                "clarify": {
                    "clarify_team": True,
                    "clarify_text": "Which team should I pass this to - customer service or warehouse?",
                    "clarify_team_options": [
                        {"team": "customer_service", "label": "customer service"},
                        {"team": "warehouse", "label": "warehouse"},
                    ],
                }
            }
        ),
    )
    stub_parser(_pick(1))
    stub_access()

    result = engine_mod.run_turn(_say("ac7e-2", "1"), session_factory=session_factory)

    bodies = seams.live_bodies()
    assert bodies, f"the team pick escalates: {result.actions!r}"
    for body in bodies:
        assert not body.get("preferred_assignee_id"), f"a team is not a person: {body!r}"
    assert not seams.errors(), seams.errors()
    assert _assigned(result), result.actions


def test_ac7e_control_a_member_pick_is_the_preferred_assignee(
    session_factory, stub_parser, stub_access, monkeypatch
) -> None:
    """The other half of AC-7e: a uuid IS taken from an assignee option."""
    company = _seed_company(session_factory, "ZZT Company Order")
    _seed_contact(session_factory, phone="+60970000009", company_id=company)
    member = _seed_pair(session_factory, company_id=company, agent_code="order_enquiries", team_code="customer_service")
    seams = _observe(monkeypatch)
    _set_open_question(
        session_factory,
        _offered({}, {"build-cs-member-offer": {"cs_last_result_set": [{"idx": 1, "label": "ZZT PIC", "uuid": member}]}}),
    )
    stub_parser(_pick(1))
    stub_access()

    result = engine_mod.run_turn(_say("ac7e-3", "1"), session_factory=session_factory)

    bodies = seams.live_bodies()
    assert [b.get("preferred_assignee_id") for b in bodies] == [member], seams.assignee
    assert not seams.errors(), seams.errors()
    assert _assigned(result), result.actions


# =========================================================================== #
# Review round 2 (NOT READY): B2, B3, B4, S1, S2, S3, S4
# =========================================================================== #

ZH_TEXT = "我想找人帮忙"  # detected `zh` (any CJK ideograph)
FREE_TEAM = "call 0123 for refund"  # a team word the parser copied verbatim (head/parser.py)


def _say_dry(message_id: str, words: str):
    """The chat console's turn: `is_test` makes it a dry run (D14)."""
    env = _say(message_id, words)
    env.is_test = True
    return env


def _named_customer_service(**overrides: Any) -> dict[str, Any]:
    """'escalate to the customer service team': the parser routed nowhere, the team is in
    its own reading of the message (`user_goal`)."""
    return _help(user_goal="escalate to the customer service team", **overrides)


def _unconfigured_company(session_factory, phone: str) -> None:
    """A company whose only link is outside the topic map: no topic pair is reachable."""
    company = _seed_company(session_factory, "ZZT Company Unmapped")
    _seed_contact(session_factory, phone=phone, company_id=company)
    _seed_pair(session_factory, company_id=company, agent_code="it_support", team_code="it_admin")


def _mocha_like(session_factory, phone: str) -> None:
    company = _seed_company(session_factory, "ZZT Company Two")
    _seed_contact(session_factory, phone=phone, company_id=company)
    _seed_pair(session_factory, company_id=company, agent_code="general_enquiries", team_code="purchasing_product")
    _seed_pair(session_factory, company_id=company, agent_code="order_enquiries", team_code="customer_service")


# --------------------------------------------------------------------------- #
# B2  a team the customer NAMES is kept, even when the chain filled the same team
# --------------------------------------------------------------------------- #


def test_b2_a_named_customer_service_team_routes_there_without_a_topic_question(
    session_factory, stub_parser, stub_access, monkeypatch
) -> None:
    company = _seed_company(session_factory, "ZZT Company Order")
    _seed_contact(session_factory, phone="+60970000010", company_id=company)
    _seed_pair(session_factory, company_id=company, agent_code="order_enquiries", team_code="customer_service")
    _seed_pair(session_factory, company_id=company, agent_code="general_enquiries", team_code="marketing_promotion")
    seams = _observe(monkeypatch)
    stub_parser(_named_customer_service())
    stub_access()

    result = engine_mod.run_turn(
        _say("b2-1", "please escalate to the customer service team"), session_factory=session_factory
    )

    assert seams.pairs() == [DOMAIN_PAIR["order"]], (
        f"the named team is the route, no topic question: {_reply_text(result)!r} {seams.assignee!r}"
    )
    assert not seams.errors(), seams.errors()
    assert _assigned(result), result.actions


def test_b2_a_held_promotion_topic_never_overrides_the_named_customer_service_team(
    session_factory, stub_parser, stub_access, monkeypatch
) -> None:
    company = _seed_company(session_factory, "ZZT Company Order")
    _seed_contact(session_factory, phone="+60970000011", company_id=company)
    _seed_pair(session_factory, company_id=company, agent_code="order_enquiries", team_code="customer_service")
    _seed_pair(session_factory, company_id=company, agent_code="general_enquiries", team_code="marketing_promotion")
    # An earlier turn was about promotions: the topic is held in the focus.
    _set_open_question(session_factory, None, focus={"domains": ["promotion"]})
    seams = _observe(monkeypatch)
    stub_parser(_named_customer_service())
    stub_access()

    result = engine_mod.run_turn(
        _say("b2-2", "please escalate to the customer service team"), session_factory=session_factory
    )

    assert ("general_enquiries", "marketing_promotion") not in seams.pairs(), seams.assignee
    assert seams.pairs() == [DOMAIN_PAIR["order"]], seams.assignee
    assert _assigned(result), result.actions


# --------------------------------------------------------------------------- #
# B3 (AC-4)  the topic clarify is in the contact's language, labels and joiner included
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("lang", "words"), [("ms", MS_TEXT), ("zh", ZH_TEXT)])
def test_b3_the_topic_question_and_its_quick_replies_are_in_the_contacts_language(
    session_factory, stub_parser, stub_access, monkeypatch, lang, words
) -> None:
    company = _seed_company(session_factory, "ZZT Company Three")
    _seed_contact(session_factory, phone="+60970000012", company_id=company)
    _seed_pair(session_factory, company_id=company, agent_code="order_enquiries", team_code="customer_service")
    _seed_pair(session_factory, company_id=company, agent_code="general_enquiries", team_code="marketing_promotion")
    seams = _observe(monkeypatch)
    stub_parser(_help())
    stub_access()

    result = engine_mod.run_turn(_say(f"b3-{lang}", words), session_factory=session_factory)

    assert seams.live_bodies() == [], seams.assignee
    sends = _sends(result)
    assert len(sends) == 1, sends
    said = sends[0].get("text") or ""
    lead = label_catalog.LABELS[T.ESC_TOPIC_ASK][lang].split("{topics}")[0]
    assert said.startswith(lead), (lead, said)
    english = [label for label in T.ESC_TOPIC_LABELS if label.lower() in said.lower()]
    assert not english, f"English topic labels in a {lang} reply: {english!r} in {said!r}"
    assert " or " not in said, f"the English joiner in a {lang} reply: {said!r}"
    offered = _quick_replies(result)
    assert not [q for q in offered if q in {label.lower() for label in T.ESC_TOPIC_LABELS}], offered
    wanted = {(label_catalog.LABELS.get(label) or {}).get(lang) for label in ("Orders & delivery", "Promotions")}
    assert None not in wanted, f"no {lang} label for the topics in label_catalog"
    assert set(offered) == {w.lower() for w in wanted}, offered


@pytest.mark.parametrize("english", T.NEW_EN_LABELS)
def test_b3_every_topic_label_has_ms_and_zh_in_the_catalog(english: str) -> None:
    from app.services.chatbot.lanes.escalation import ESCALATION_TOPICS

    assert english in [label for label, _ in ESCALATION_TOPICS], "the lane's own topic labels"
    entry = label_catalog.LABELS.get(english)
    assert entry, f"no label_catalog entry for {english!r}"
    for lang in ("ms", "zh"):
        assert entry.get(lang, "").strip() and entry[lang] != english, (lang, english)
        assert english in label_catalog.defaults(lang), (lang, english)


# --------------------------------------------------------------------------- #
# B4  the failure reply names the team the customer named and the draw was for
# --------------------------------------------------------------------------- #


def test_b4_a_failed_draw_for_the_named_warehouse_team_never_names_the_parsers_team(
    session_factory, stub_parser, stub_access, monkeypatch
) -> None:
    company = _seed_company(session_factory, "ZZT Company Stock")
    _seed_contact(session_factory, phone="+60970000013", company_id=company)
    _seed_pair(session_factory, company_id=company, agent_code="general_enquiries", team_code="warehouse")
    _seed_pair(session_factory, company_id=company, agent_code="general_enquiries", team_code="purchasing")
    seams = _observe(monkeypatch, **_failure("assignee_404"))
    stub_parser(
        _help(
            user_goal="escalate to the warehouse team",
            routing={"suggested_team": "purchasing", "suggested_agent": "general_enquiries"},
        )
    )
    stub_access()

    result = engine_mod.run_turn(_say("b4-1", "please escalate to the warehouse team"), session_factory=session_factory)

    assert seams.pairs() == [DOMAIN_PAIR["inventory"]], seams.assignee
    assert result.reply["text"] == T.H_ESC.format(team="warehouse"), result.reply["text"]
    assert "purchasing" not in result.reply["text"], result.reply["text"]


# --------------------------------------------------------------------------- #
# S1 + security nit  a failure names no team unless it is a reachable topic-map team
# --------------------------------------------------------------------------- #


def _neutral(lang: str) -> str:
    return T.H_ESC_NEUTRAL if lang == "en" else (label_catalog.LABELS.get(T.H_ESC_NEUTRAL) or {}).get(lang)


@pytest.mark.parametrize(("lang", "words"), [("en", "I want to talk to a person"), ("ms", MS_TEXT)])
def test_s1_no_reachable_topic_fails_with_the_neutral_text(
    session_factory, stub_parser, stub_access, monkeypatch, lang, words
) -> None:
    _unconfigured_company(session_factory, "+60970000014")
    seams = _observe(monkeypatch)
    stub_parser(_help())
    stub_access()

    result = engine_mod.run_turn(_say(f"s1-a-{lang}", words), session_factory=session_factory)

    said = result.reply["text"]
    assert seams.live_bodies() == [], seams.assignee
    assert not _assigned(result), result.actions
    assert pretty_team(DEFAULT_SUGGESTED_TEAM) not in said.lower(), said
    assert said == _neutral(lang), said


def test_s1_an_unreachable_topic_team_is_never_named(session_factory, stub_parser, stub_access, monkeypatch) -> None:
    """The stock topic's team is warehouse; this company has no warehouse link."""
    _unconfigured_company(session_factory, "+60970000015")
    seams = _observe(monkeypatch)
    stub_parser(_help(domain_hint="inventory"))
    stub_access()

    result = engine_mod.run_turn(_say("s1-b", "can someone help me with stock"), session_factory=session_factory)

    said = result.reply["text"]
    assert seams.live_bodies() == [], seams.assignee
    assert "warehouse" not in said.lower(), said
    assert said == T.H_ESC_NEUTRAL, said


def test_s1_a_free_string_team_from_the_parser_is_never_echoed(
    session_factory, stub_parser, stub_access, monkeypatch
) -> None:
    """Security nit: `routing.suggested_team` may be the customer's own words verbatim."""
    _unconfigured_company(session_factory, "+60970000016")
    seams = _observe(monkeypatch)
    stub_parser(
        _help(
            user_goal=f"escalate to the {FREE_TEAM} team",
            routing={"suggested_team": FREE_TEAM, "suggested_agent": None},
            escalation={"is_escalation_confirmation": True, "escalation_declined": None, "company_pick": None},
        )
    )
    stub_access()

    result = engine_mod.run_turn(
        _say("s1-c", f"escalate to the '{FREE_TEAM}' team"), session_factory=session_factory
    )

    said = _reply_text(result)
    assert seams.live_bodies() == [], seams.assignee
    assert "0123" not in said and "refund" not in said.lower(), said
    assert said == T.H_ESC_NEUTRAL, said


# --------------------------------------------------------------------------- #
# S2  an explicit team draws with its map agent before a default-filled agent
# --------------------------------------------------------------------------- #


def test_s2_an_explicit_customer_service_team_draws_with_order_enquiries_not_the_default_agent(
    session_factory, stub_parser, stub_access, monkeypatch
) -> None:
    company = _seed_company(session_factory, "ZZT Company Both")
    _seed_contact(session_factory, phone="+60970000017", company_id=company)
    _seed_pair(session_factory, company_id=company, agent_code="general_enquiries", team_code="customer_service")
    _seed_pair(session_factory, company_id=company, agent_code="order_enquiries", team_code="customer_service")
    seams = _observe(monkeypatch)
    # The parser named the team, not the agent: the agent the turn carries is the default fill.
    stub_parser(_help(routing={"suggested_team": "customer_service", "suggested_agent": None}))
    stub_access()

    result = engine_mod.run_turn(_say("s2-1", "customer service please"), session_factory=session_factory)

    assert seams.pairs() == [DOMAIN_PAIR["order"]], (
        f"never the default agent {DEFAULT_SUGGESTED_AGENT!r}: {seams.assignee!r}"
    )
    assert _assigned(result), result.actions


# --------------------------------------------------------------------------- #
# S3  a dry run (chat console) shows the outcome the live turn has
# --------------------------------------------------------------------------- #


def test_s3_a_dry_run_shows_the_same_failure_as_the_live_turn(
    session_factory, stub_parser, stub_access, monkeypatch
) -> None:
    _unconfigured_company(session_factory, "+60970000018")
    _observe(monkeypatch)
    stub_parser(_help())
    stub_access()

    dry = engine_mod.run_turn(_say_dry("s3-dry", "I want to talk to a person"), session_factory=session_factory)
    live = engine_mod.run_turn(_say("s3-live", "I want to talk to a person"), session_factory=session_factory)

    assert not _assigned(live), live.actions
    kinds = [a.get("kind") for a in dry.actions]
    assert "assign_conversation" not in kinds and "add_comment" not in kinds, (
        f"no previewed assignment to the chain's team: {dry.actions!r}"
    )
    assert _reply_text(dry) == _reply_text(live), (_reply_text(dry), _reply_text(live))


# --------------------------------------------------------------------------- #
# S4  Mocha: general_enquiries is linked to purchasing_product, not purchasing
# --------------------------------------------------------------------------- #


def test_s4_mocha_a_product_info_escalation_routes_to_purchasing_product(
    session_factory, stub_parser, stub_access, monkeypatch
) -> None:
    _mocha_like(session_factory, "+60970000019")
    seams = _observe(monkeypatch)
    stub_parser(_help(domain_hint="master_products"))
    stub_access()

    result = engine_mod.run_turn(
        _say("s4-1", "I need someone to check this product for me"), session_factory=session_factory
    )

    assert seams.pairs() == [("general_enquiries", "purchasing_product")], (_reply_text(result), seams.assignee)
    assert not seams.errors(), seams.errors()
    assert _assigned(result), result.actions


def test_s4_mocha_the_topic_question_offers_product_info_and_routes_it(
    session_factory, stub_parser, stub_access, monkeypatch
) -> None:
    _mocha_like(session_factory, "+60970000020")
    seams = _observe(monkeypatch)
    stub_parser(_help())
    stub_access()

    first = engine_mod.run_turn(_say("s4-2", "I want to talk to a person"), session_factory=session_factory)

    assert seams.live_bodies() == [], seams.assignee
    assert TOPIC_PRODUCT in set(_quick_replies(first)), (_reply_text(first), _quick_replies(first))
    open_question = _session_vars(session_factory).get("open_question") or {}
    product = [o for o in (open_question.get("options") or []) if TOPIC_PRODUCT in str(o.get("label") or "").lower()]
    assert len(product) == 1, open_question
    stub_parser(_pick(int(product[0]["position"])))

    engine_mod.run_turn(_say("s4-3", "Product info"), session_factory=session_factory)

    assert seams.pairs() == [("general_enquiries", "purchasing_product")], seams.assignee
