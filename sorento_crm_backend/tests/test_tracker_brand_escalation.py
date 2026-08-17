"""The tracker remembers the brand, and escalation climbs with it.

The brand is stamped once at creation, exactly like the company (320), because
escalation runs from a scheduler tick that has no request context to re-derive it
from. Without the stamp a Mocha conversation would escalate into the general pool
and land on somebody who has never seen the brand.

It is stamped ONCE and never re-stamped: the brand describes the ENQUIRY, not who
is handling it, so a takeover or a manual reassign leaves it exactly as it is.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.models.access import (
    AccessAgent,
    AgentTeam,
    RespondContact,
    Team,
    TeamMember,
    team_member_brands,
)
from app.models.base import set_company_scope
from app.models.company import Company
from app.models.sla import ConversationSLATracking, SLAPolicy, SLAPolicyTier
from app.models.user import User
from app.schemas.sla import ConversationSLATrackingCreate
from app.services.sla_service import ConversationSLATrackingService
from tests._pg_fixture import blank_session, unique_code


SORENTO = "00000000-0000-0000-0000-000000000001"
SET = "marketing_promotion"
PHONE = "+60120000077"


@pytest.fixture
def world():
    """ONE promotion set, one team per tier, the brands on the people.

    Tier 1: Zhi Yang (sorento) and Kia Yee (mocha) - both tagged, so an unknown or
    absent brand falls back to the whole team and starts at Zhi Yang.
    Tier 2: Boss (untagged, catches everything nobody is tagged for), Mocha Boss
    (mocha) and Cabana Boss (cabana).
    """
    with blank_session() as db:
        set_company_scope(db, frozenset({SORENTO}))

        agent_id = str(uuid.uuid4())
        agent_code = unique_code("agent")
        db.add(AccessAgent(id=agent_id, code=agent_code, name="ZZT Marketing", is_active=True))

        policy_id = str(uuid.uuid4())
        db.add(
            SLAPolicy(
                id=policy_id,
                code=unique_code("pol"),
                name="ZZT Promo Policy",
                is_active=True,
                company_id=SORENTO,
            )
        )
        db.flush()
        for tier_level in (1, 2, 3):
            db.add(
                SLAPolicyTier(
                    id=str(uuid.uuid4()),
                    policy_id=policy_id,
                    tier_level=tier_level,
                    tier_name=f"ZZT Tier {tier_level}",
                    response_hours=4,
                    resolution_hours=24,
                )
            )
        db.flush()

        people: dict[str, str] = {}
        teams: dict[str, str] = {}

        def _team(label: str, company_id: str = SORENTO) -> str:
            team_id = str(uuid.uuid4())
            db.add(Team(id=team_id, name=f"ZZT {label}", company_id=company_id))
            db.flush()
            teams[label] = team_id
            return team_id

        def _member(team_id: str, person: str, brands: list[str], sort_order: int) -> str:
            user_id = str(uuid.uuid4())
            db.add(
                User(
                    id=user_id,
                    email=f"{unique_code('u').lower()}@zzt.test",
                    name=f"ZZT {person}",
                    status="ACTIVE",
                )
            )
            db.flush()
            member_id = str(uuid.uuid4())
            db.add(
                TeamMember(
                    id=member_id, team_id=team_id, user_id=user_id, sort_order=sort_order
                )
            )
            db.flush()
            for code in brands:
                db.execute(
                    team_member_brands.insert().values(
                        team_member_id=member_id, brand_code=code
                    )
                )
            db.flush()
            people[person] = user_id
            return user_id

        def _link(team_id, tier, company_id=SORENTO, policy=policy_id):
            db.add(
                AgentTeam(
                    id=str(uuid.uuid4()),
                    agent_id=agent_id,
                    code=SET,
                    team_id=team_id,
                    tier=tier,
                    company_id=company_id,
                    policy_id=policy,
                )
            )
            db.flush()

        t1 = _team("t1")
        _member(t1, "Zhi Yang", ["sorento"], 1)
        _member(t1, "Kia Yee", ["mocha"], 2)
        _link(t1, 1)

        t2 = _team("t2")
        _member(t2, "Boss", [], 1)
        _member(t2, "Mocha Boss", ["mocha"], 2)
        _member(t2, "Cabana Boss", ["cabana"], 3)
        _link(t2, 2)

        contact_id = str(uuid.uuid4())
        db.add(RespondContact(id=contact_id, phone_number=PHONE, name="ZZT Contact"))
        db.flush()

        yield {
            "db": db,
            "agent_code": agent_code,
            "agent_id": agent_id,
            "policy_id": policy_id,
            "contact_id": contact_id,
            "people": people,
            "teams": teams,
        }


def _create(world, **extra):
    payload = ConversationSLATrackingCreate(
        agent_code=world["agent_code"],
        team_set_code=SET,
        contact_phone_number=PHONE,
        **extra,
    )
    return ConversationSLATrackingService(world["db"]).create_tracking(payload)


# ------------------------------------------------------- the stamp at creation


def test_the_brand_is_stored_lower_case(world):
    tracking = _create(world, brand_code=" MoChA ")

    assert tracking.brand_code == "mocha"


def test_no_brand_stores_null(world):
    tracking = _create(world, brand_code="  ")

    assert tracking.brand_code is None


def test_a_legacy_suffixed_team_set_code_is_split(world):
    """AC2-X1 at the tracker: the row stores the BASE code plus the brand."""
    payload = ConversationSLATrackingCreate(
        agent_code=world["agent_code"],
        team_set_code="marketing_promotion_mocha",
        contact_phone_number=PHONE,
    )

    tracking = ConversationSLATrackingService(world["db"]).create_tracking(payload)

    assert tracking.team_set_code == SET
    assert tracking.brand_code == "mocha"


def test_an_explicit_brand_beats_the_suffix(world):
    payload = ConversationSLATrackingCreate(
        agent_code=world["agent_code"],
        team_set_code="marketing_promotion_mocha",
        contact_phone_number=PHONE,
        brand_code="cabana",
    )

    tracking = ConversationSLATrackingService(world["db"]).create_tracking(payload)

    assert tracking.brand_code == "cabana"


def test_a_valid_company_id_in_the_body_wins_over_the_contact(world):
    """n8n already resolved the company; the tracker records that one."""
    db = world["db"]
    mocha_company = str(uuid.uuid4())
    db.add(
        Company(id=mocha_company, name="ZZT MochaCo", code=unique_code("MCH"), is_active=True)
    )
    db.flush()
    # The other company needs its own ladder, or the create has nothing to assign to.
    policy_id = str(uuid.uuid4())
    db.add(
        SLAPolicy(
            id=policy_id,
            code=unique_code("pol"),
            name="ZZT MochaCo Policy",
            is_active=True,
            company_id=mocha_company,
        )
    )
    db.flush()
    db.add(
        SLAPolicyTier(
            id=str(uuid.uuid4()),
            policy_id=policy_id,
            tier_level=1,
            tier_name="ZZT Tier 1",
            response_hours=4,
            resolution_hours=24,
        )
    )
    team_id = str(uuid.uuid4())
    db.add(Team(id=team_id, name="ZZT MochaCo Marketing", company_id=mocha_company))
    user_id = str(uuid.uuid4())
    db.add(
        User(
            id=user_id,
            email=f"{unique_code('u').lower()}@zzt.test",
            name="ZZT MochaCo CS",
            status="ACTIVE",
        )
    )
    db.flush()
    db.add(TeamMember(id=str(uuid.uuid4()), team_id=team_id, user_id=user_id))
    db.add(
        AgentTeam(
            id=str(uuid.uuid4()),
            agent_id=world["agent_id"],
            code=SET,
            team_id=team_id,
            tier=1,
            company_id=mocha_company,
            policy_id=policy_id,
        )
    )
    db.flush()
    # n8n calls this with the API-key principal, which carries no active company -
    # so the ambient scope is unset. Mirrored here because the fixture pins Sorento
    # for the other tests, and an ambient Sorento scope would hide the other
    # company's policy binding (AgentTeam is company-scoped).
    set_company_scope(db, None)

    tracking = _create(world, company_id=mocha_company)

    assert str(tracking.company_id) == mocha_company
    assert str(tracking.assigned_to_id) == user_id


def test_an_unknown_company_id_falls_back_to_the_contact(world):
    """Routing must never break on a bad field."""
    tracking = _create(world, company_id=str(uuid.uuid4()))

    assert str(tracking.company_id) == SORENTO


# ----------------------------------------------- the pool at initial assignment


def test_round_robin_creation_draws_from_the_brands_pool(world):
    """AC2-R3 - a Mocha item lands on the member tagged mocha."""
    tracking = _create(world, brand_code="mocha")

    assert str(tracking.assigned_to_id) == world["people"]["Kia Yee"]


def test_round_robin_creation_without_a_brand_uses_the_whole_team(world):
    tracking = _create(world)

    assert str(tracking.assigned_to_id) == world["people"]["Zhi Yang"]


def test_a_brand_nobody_is_tagged_for_uses_the_whole_team(world):
    tracking = _create(world, brand_code="cabana")

    assert str(tracking.assigned_to_id) == world["people"]["Zhi Yang"]


# ------------------------------------------------------- the pool at escalation


def _escalate(world, brand_code):
    return ConversationSLATrackingService(world["db"]).get_escalation_assignee_for_tier(
        None,
        2,
        SET,
        agent_id_override=world["agent_id"],
        company_id=SORENTO,
        brand_code=brand_code,
    )


def test_escalation_draws_from_the_brands_pool_at_tier_two(world):
    """AC2-R2 - the tier-2 team is the same one; the mocha members are the pool.

    Boss is untagged and therefore serves every brand, so the mocha pool is Boss AND
    Mocha Boss - what must never happen is the CABANA member taking a mocha
    escalation.
    """
    picked = {str(_escalate(world, "mocha")["id"]) for _ in range(4)}

    assert picked == {world["people"]["Boss"], world["people"]["Mocha Boss"]}


def test_a_brand_nobody_is_tagged_for_at_tier_two_reaches_the_untagged_member(world):
    """AC2-R2 - the untagged member catches everything nobody is tagged for."""
    for _ in range(3):
        assert str(_escalate(world, "sorento")["id"]) == world["people"]["Boss"]


def test_escalation_without_a_brand_round_robins_the_whole_tier(world):
    picked = {str(_escalate(world, None)["id"]) for _ in range(6)}

    assert picked == {
        world["people"]["Boss"],
        world["people"]["Mocha Boss"],
        world["people"]["Cabana Boss"],
    }


# --------------------------------------------- the routes pass the row's brand


@pytest.fixture
def client():
    from app.database import get_db as database_get_db
    from app.dependencies import (
        get_db as dependencies_get_db,
        get_current_user,
        get_current_user_or_api_key,
    )
    from app.main import app

    def _user():
        return {"id": "system"}

    def _db():
        yield MagicMock()

    app.dependency_overrides[get_current_user_or_api_key] = _user
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[database_get_db] = _db
    app.dependency_overrides[dependencies_get_db] = _db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _tracking_mock(brand_code):
    tracking = MagicMock()
    tracking.id = "tracking-1"
    tracking.is_resolved = False
    tracking.current_tier = 1
    tracking.agent_id = "agent-a"
    tracking.team_set_code = SET
    tracking.brand_code = brand_code
    tracking.company_id = SORENTO
    tracking.source_entity_type = None
    tracking.message_id = 1
    tracking.assigned_to_id = "user-1"
    tracking.assigned_to = "777"
    tracking.assigned_user = None
    tracking.respond_contact_id = "contact-1"
    tracking.policy_id = "policy-1"
    tracking.due_at = datetime.now(timezone.utc) + timedelta(hours=4)
    tracking.due_at_resolution = datetime.now(timezone.utc) + timedelta(hours=24)
    return tracking


ASSIGNEE = {"id": "user-2", "email": "b@zzt.test", "name": "ZZT T2", "respond_user_id": "888"}


@patch("app.services.market_segment_service.MarketSegmentService")
@patch("app.api.v1.sla.sla_tracking.IntegrationLogService")
@patch("app.api.v1.sla.sla_tracking.ConversationSLATrackingService")
def test_integration_escalate_passes_the_trackers_brand(
    mock_service_cls, _mock_log, mock_segments, client
):
    """AC2-R2 - the escalation climbs with the brand the assignment came off."""
    svc = mock_service_cls.return_value
    svc.resolve_internal_respond_contact_id.return_value = "contact-1"
    svc.get_open_tracking_by_contact.return_value = _tracking_mock("mocha")
    svc.get_escalation_assignee_for_tier.return_value = ASSIGNEE
    svc.escalate_tracking.return_value = _tracking_mock("mocha")
    mock_segments.return_value.resolve_segments_for_contact_id.return_value = set()

    r = client.post(
        "/api/v1/sla-management/conversation-sla-tracking/integration/escalate",
        json={"respond_contact_id": "contact-1"},
    )

    assert r.status_code == 200, r.text
    assert svc.get_escalation_assignee_for_tier.call_args.kwargs["brand_code"] == "mocha"


@patch("app.services.market_segment_service.MarketSegmentService")
@patch("app.api.v1.sla.sla_tracking.IntegrationLogService")
@patch("app.api.v1.sla.sla_tracking.ConversationSLATrackingService")
def test_integration_escalate_of_an_unbranded_tracker_passes_none(
    mock_service_cls, _mock_log, mock_segments, client
):
    svc = mock_service_cls.return_value
    svc.resolve_internal_respond_contact_id.return_value = "contact-1"
    svc.get_open_tracking_by_contact.return_value = _tracking_mock(None)
    svc.get_escalation_assignee_for_tier.return_value = ASSIGNEE
    svc.escalate_tracking.return_value = _tracking_mock(None)
    mock_segments.return_value.resolve_segments_for_contact_id.return_value = set()

    r = client.post(
        "/api/v1/sla-management/conversation-sla-tracking/integration/escalate",
        json={"respond_contact_id": "contact-1"},
    )

    assert r.status_code == 200, r.text
    assert svc.get_escalation_assignee_for_tier.call_args.kwargs["brand_code"] is None


# ------------------------------------------------------------------ response


def test_the_response_carries_the_brand_the_tracker_routed_with(world):
    """n8n reads back what the CRM routed with, off a real tracker row."""
    from app.api.v1.sla.sla_tracking import build_conversation_sla_tracking_response

    tracking = _create(world, brand_code="MOCHA")

    response = build_conversation_sla_tracking_response(world["db"], tracking)

    assert response.brand_code == "mocha"


def test_the_response_of_an_unbranded_tracker_carries_null(world):
    from app.api.v1.sla.sla_tracking import build_conversation_sla_tracking_response

    tracking = _create(world)

    response = build_conversation_sla_tracking_response(world["db"], tracking)

    assert response.brand_code is None


def test_the_create_schema_accepts_the_brand():
    assert "brand_code" in ConversationSLATrackingCreate.model_fields


# ---------------------------------------- the brand is the enquiry's, not the
#                                          handler's (BL-016, revised)


def test_a_manual_reassign_leaves_the_brand_alone(world):
    """The brand describes what the customer asked about.

    Handing the conversation to somebody else does not turn a Mocha question into a
    Sorento one, so ``apply_assignee_team_derivation`` must not touch the stamp -
    and the next escalation still draws from the Mocha pool.
    """
    tracking = _create(world, brand_code="mocha")
    assert str(tracking.assigned_to_id) == world["people"]["Kia Yee"]
    service = ConversationSLATrackingService(world["db"])

    service.apply_assignee_team_derivation(
        str(tracking.id), world["people"]["Zhi Yang"], source="conversation-assignee"
    )

    assert (
        world["db"]
        .query(ConversationSLATracking)
        .filter(ConversationSLATracking.id == str(tracking.id))
        .first()
        .brand_code
        == "mocha"
    )


# ------------------------------------------- idempotent create, brand mismatch


def test_a_brand_mismatch_on_the_idempotent_create_is_logged(world, caplog):
    """The open tracker's brand wins; the disagreement must be visible in the log."""
    import logging

    _create(world, brand_code="mocha")

    with caplog.at_level(logging.INFO, logger="app.services.sla_service"):
        again = _create(world, brand_code="cabana")

    assert again.brand_code == "mocha"
    messages = [record.getMessage() for record in caplog.records]
    assert any("cabana" in m and "mocha" in m for m in messages), messages
