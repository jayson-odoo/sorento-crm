"""AC2-X1 and AC2-R3 - the external endpoints route by brand and say so.

Two halves, on purpose:

* the wire contract (what n8n sends and what it gets back) against a mocked
  service, like the other /external suites;
* the headline routing cases against a REAL seeded database, because "a Mocha
  promotion reaches Kia Yee" is the whole feature and a mock cannot prove it.

The team is the same whatever the brand is - one set, one team per tier. What the
brand decides is which MEMBERS of that team are in the round-robin pool, so every
assertion below is about who came back, never about which row was read.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.dependencies import get_external_api_user
from app.main import app
from app.models.access import AccessAgent, AgentTeam, Team, TeamMember, team_member_brands
from app.models.base import set_company_scope
from app.models.company import Company
from app.models.user import User
from app.services.company_routing_service import DEFAULT_COMPANY_ID, RoutingCompany
from tests._external_auth import external_permissions_granted
from tests._pg_fixture import blank_session, unique_code


SORENTO = DEFAULT_COMPANY_ID
PHONE = "+60120000042"
ASSIGNEE = {
    "id": "user-1",
    "email": "a@test.com",
    "name": "Agent A",
    "respond_user_id": "971724",
    "brand_matched": True,
}
SORENTO_DEFAULT = RoutingCompany(
    company_id=SORENTO, company_code="SRT", source="default"
)


# ------------------------------------------------------- wire contract (mocked)


@pytest.fixture
def client():
    def _user():
        return {"id": "system"}

    def _db():
        yield MagicMock()

    app.dependency_overrides[get_external_api_user] = _user
    app.dependency_overrides[get_db] = _db
    with external_permissions_granted():
        yield TestClient(app)
    app.dependency_overrides.clear()


def _mocks(mock_cal, mock_sla, mock_access, *, assignee=None):
    mock_cal.return_value.is_within_working_time.return_value = True
    mock_sla.return_value.get_tracking_by_contact_phone.return_value = None
    mock_access.return_value.get_agent_id_by_code.return_value = "agent-1"
    mock_access.return_value.get_team_id_by_tier.return_value = "team-1"
    mock_access.return_value.list_team_ids_for_agent_code.return_value = ["team-1"]
    mock_access.return_value.get_next_assignee.return_value = assignee or ASSIGNEE


BODY = {
    "contact_phone_number": PHONE,
    "agent_code": "general_enquiries",
    "team_code": "marketing_promotion",
    "tier": 1,
}


@patch(
    "app.api.v1.external.next_assignee._resolve_sla_policy_tier_for_next_assignee",
    return_value={
        "policy_id": None,
        "tier_response_hours": None,
        "tier_resolution_hours": None,
    },
)
@patch("app.api.v1.external.next_assignee.resolve_routing_company")
@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.ConversationSLATrackingService")
@patch("app.api.v1.external.next_assignee.CalendarService")
def test_response_echoes_the_brand_it_routed_with(
    mock_cal, mock_sla, mock_access, mock_resolve, _mock_policy, client: TestClient
):
    """AC2-X1 - a misrouting is diagnosable from the n8n execution log alone."""
    _mocks(mock_cal, mock_sla, mock_access)
    mock_resolve.return_value = SORENTO_DEFAULT

    r = client.post("/api/v1/external/next-assignee", json={**BODY, "brand_code": " MoChA "})

    assert r.status_code == 200
    data = r.json()
    assert data["brand_code"] == "mocha"
    assert data["brand_matched"] is True
    assert data["team_set_code"] == "marketing_promotion"
    # The tier row is brand-blind; the brand reaches the round-robin pool instead.
    mock_access.return_value.get_team_id_by_tier.assert_called_once_with(
        "agent-1", 1, team_set_code="marketing_promotion", company_id=SORENTO
    )
    assert (
        mock_access.return_value.get_next_assignee.call_args.kwargs["brand_code"]
        == "mocha"
    )


@patch(
    "app.api.v1.external.next_assignee._resolve_sla_policy_tier_for_next_assignee",
    return_value={
        "policy_id": None,
        "tier_response_hours": None,
        "tier_resolution_hours": None,
    },
)
@patch("app.api.v1.external.next_assignee.resolve_routing_company")
@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.ConversationSLATrackingService")
@patch("app.api.v1.external.next_assignee.CalendarService")
def test_the_untagged_fallback_reports_brand_matched_false(
    mock_cal, mock_sla, mock_access, mock_resolve, _mock_policy, client: TestClient
):
    """AC2-X1 - nobody is tagged for this brand, so the whole team answered."""
    _mocks(mock_cal, mock_sla, mock_access, assignee={**ASSIGNEE, "brand_matched": False})
    mock_resolve.return_value = SORENTO_DEFAULT

    r = client.post("/api/v1/external/next-assignee", json={**BODY, "brand_code": "cabana"})

    assert r.status_code == 200
    assert r.json()["brand_code"] == "cabana"
    assert r.json()["brand_matched"] is False


@patch(
    "app.api.v1.external.next_assignee._resolve_sla_policy_tier_for_next_assignee",
    return_value={
        "policy_id": None,
        "tier_response_hours": None,
        "tier_resolution_hours": None,
    },
)
@patch("app.api.v1.external.next_assignee.resolve_routing_company")
@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.ConversationSLATrackingService")
@patch("app.api.v1.external.next_assignee.CalendarService")
def test_blank_brand_is_null_not_empty_string(
    mock_cal, mock_sla, mock_access, mock_resolve, _mock_policy, client: TestClient
):
    _mocks(mock_cal, mock_sla, mock_access, assignee={**ASSIGNEE, "brand_matched": False})
    mock_resolve.return_value = SORENTO_DEFAULT

    r = client.post("/api/v1/external/next-assignee", json={**BODY, "brand_code": "   "})

    assert r.json()["brand_code"] is None
    assert r.json()["brand_matched"] is False
    assert (
        mock_access.return_value.get_next_assignee.call_args.kwargs["brand_code"] is None
    )


@patch(
    "app.api.v1.external.next_assignee._resolve_sla_policy_tier_for_next_assignee",
    return_value={
        "policy_id": None,
        "tier_response_hours": None,
        "tier_resolution_hours": None,
    },
)
@patch("app.api.v1.external.next_assignee.resolve_routing_company")
@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.ConversationSLATrackingService")
@patch("app.api.v1.external.next_assignee.CalendarService")
def test_legacy_suffixed_code_is_read_as_base_plus_brand(
    mock_cal, mock_sla, mock_access, mock_resolve, _mock_policy, client: TestClient
):
    """AC2-X1 - one release of compatibility for the un-updated workflow."""
    _mocks(mock_cal, mock_sla, mock_access)
    mock_resolve.return_value = SORENTO_DEFAULT

    r = client.post(
        "/api/v1/external/next-assignee",
        json={**BODY, "team_code": "marketing_promotion_mocha"},
    )

    assert r.status_code == 200
    assert r.json()["team_set_code"] == "marketing_promotion"
    assert r.json()["brand_code"] == "mocha"
    mock_access.return_value.get_team_id_by_tier.assert_called_once_with(
        "agent-1", 1, team_set_code="marketing_promotion", company_id=SORENTO
    )
    assert (
        mock_access.return_value.get_next_assignee.call_args.kwargs["brand_code"]
        == "mocha"
    )


@patch(
    "app.api.v1.external.next_assignee._resolve_sla_policy_tier_for_next_assignee",
    return_value={
        "policy_id": None,
        "tier_response_hours": None,
        "tier_resolution_hours": None,
    },
)
@patch("app.api.v1.external.next_assignee.resolve_routing_company")
@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.ConversationSLATrackingService")
@patch("app.api.v1.external.next_assignee.CalendarService")
def test_explicit_brand_beats_the_suffix(
    mock_cal, mock_sla, mock_access, mock_resolve, _mock_policy, client: TestClient
):
    _mocks(mock_cal, mock_sla, mock_access)
    mock_resolve.return_value = SORENTO_DEFAULT

    r = client.post(
        "/api/v1/external/next-assignee",
        json={**BODY, "team_code": "marketing_promotion_mocha", "brand_code": "cabana"},
    )

    assert r.json()["brand_code"] == "cabana"
    assert (
        mock_access.return_value.get_next_assignee.call_args.kwargs["brand_code"]
        == "cabana"
    )


@patch(
    "app.api.v1.external.next_assignee._resolve_sla_policy_tier_for_next_assignee",
    return_value={
        "policy_id": None,
        "tier_response_hours": None,
        "tier_resolution_hours": None,
    },
)
@patch("app.api.v1.external.next_assignee.resolve_routing_company")
@patch("app.api.v1.external.next_assignee.AccessAgentService")
@patch("app.api.v1.external.next_assignee.ConversationSLATrackingService")
@patch("app.api.v1.external.next_assignee.CalendarService")
def test_company_id_from_the_body_is_passed_to_the_resolver(
    mock_cal, mock_sla, mock_access, mock_resolve, _mock_policy, client: TestClient
):
    """AC2-X1 - n8n already resolved the company, so it may say so directly."""
    _mocks(mock_cal, mock_sla, mock_access)
    mock_resolve.return_value = SORENTO_DEFAULT
    company_id = str(uuid.uuid4())

    client.post("/api/v1/external/next-assignee", json={**BODY, "company_id": company_id})

    assert mock_resolve.call_args.kwargs["company_id"] == company_id


# ------------------------------------------------- routing company override


def test_body_company_id_beats_the_contact():
    from app.services.company_routing_service import resolve_routing_company

    with blank_session() as db:
        other = str(uuid.uuid4())
        db.add(
            Company(id=other, name="ZZT MochaCo", code=unique_code("MCH"), is_active=True)
        )
        db.flush()

        resolved = resolve_routing_company(db, company_id=other, phone=PHONE)

        assert resolved.company_id == other
        assert resolved.source == "body"


def test_unknown_company_id_is_ignored_and_resolution_continues():
    from app.services.company_routing_service import resolve_routing_company

    with blank_session() as db:
        resolved = resolve_routing_company(db, company_id=str(uuid.uuid4()))

        assert resolved.company_id == SORENTO
        assert resolved.source != "body"


def test_a_malformed_company_id_does_not_raise():
    """Routing must never break on a bad field - a typo cannot abort the request."""
    from app.services.company_routing_service import resolve_routing_company

    with blank_session() as db:
        assert resolve_routing_company(db, company_id="not-a-uuid").company_id == SORENTO


# ------------------------------------------------- headline cases (seeded DB)


@pytest.fixture
def seeded():
    """The live shape of the two companies' marketing routing, in miniature.

    ONE team per set per company; the brands sit on the people:
    product = Zhi Yang (sorento) + Kia Yee (mocha), promotion = Am (untagged, today's
    default handler) + Aqi (cabana).
    """
    with blank_session() as db:
        set_company_scope(db, frozenset({SORENTO}))
        mocha_company = str(uuid.uuid4())
        db.add(
            Company(
                id=mocha_company,
                name="ZZT MochaCo",
                code=unique_code("MCH"),
                is_active=True,
            )
        )

        agent_id = str(uuid.uuid4())
        agent_code = unique_code("agent")
        db.add(
            AccessAgent(id=agent_id, code=agent_code, name="ZZT Marketing", is_active=True)
        )
        db.flush()

        people: dict[str, str] = {}
        teams: dict[str, str] = {}

        def _team(label: str, company_id: str) -> str:
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
                    id=member_id,
                    team_id=team_id,
                    user_id=user_id,
                    sort_order=sort_order,
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

        def _link(code, team_id, company_id):
            db.add(
                AgentTeam(
                    id=str(uuid.uuid4()),
                    agent_id=agent_id,
                    code=code,
                    team_id=team_id,
                    tier=1,
                    company_id=company_id,
                )
            )
            db.flush()

        product = _team("product", SORENTO)
        _member(product, "Zhi Yang", ["sorento"], 1)
        _member(product, "Kia Yee", ["mocha"], 2)
        _link("marketing_product", product, SORENTO)

        promotion = _team("promotion", SORENTO)
        _member(promotion, "Am", [], 1)
        _member(promotion, "Aqi", ["cabana"], 2)
        _link("marketing_promotion", promotion, SORENTO)

        # The Mocha COMPANY carries Mocha only: one team, nobody tagged.
        mochaco = _team("mochaco_product", mocha_company)
        _member(mochaco, "Mocha CS", [], 1)
        _link("marketing_product", mochaco, mocha_company)

        def _override():
            yield db

        app.dependency_overrides[get_external_api_user] = lambda: {"id": "system"}
        app.dependency_overrides[get_db] = _override
        with external_permissions_granted():
            yield {
                "db": db,
                "client": TestClient(app),
                "agent_code": agent_code,
                "mocha_company": mocha_company,
                "people": people,
                "teams": teams,
            }
        app.dependency_overrides.clear()


def _post(seeded, **extra):
    body = {
        "contact_phone_number": PHONE,
        "agent_code": seeded["agent_code"],
        "team_code": "marketing_product",
        **extra,
    }
    return seeded["client"].post("/api/v1/external/next-assignee", json=body)


def test_mocha_company_routes_to_its_own_team(seeded):
    """AC2-R3 - the Mocha company's roster, brand or no brand."""
    for brand in (None, "mocha"):
        r = _post(seeded, company_id=seeded["mocha_company"], brand_code=brand)
        assert r.status_code == 200, r.text
        assert r.json()["assignee_id"] == seeded["people"]["Mocha CS"]
        assert r.json()["company_source"] == "body"


def test_sorento_company_with_brand_mocha_reaches_the_tagged_member(seeded):
    """AC2-R3 - a Mocha item inside the Sorento company reaches Kia Yee."""
    for _ in range(3):
        r = _post(seeded, brand_code="mocha")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["assignee_id"] == seeded["people"]["Kia Yee"]
        assert body["brand_matched"] is True


def test_sorento_brand_reaches_the_sorento_member(seeded):
    r = _post(seeded, brand_code="sorento")

    assert r.json()["assignee_id"] == seeded["people"]["Zhi Yang"]
    assert r.json()["brand_matched"] is True


@pytest.mark.parametrize("brand", [None, "unknown-brand"])
def test_a_brand_nobody_is_tagged_for_falls_back_to_the_whole_team(seeded, brand):
    """AC2-R3 - every member is tagged, so an unknown brand round-robins them all."""
    r = _post(seeded, brand_code=brand)

    assert r.status_code == 200, r.text
    assert r.json()["assignee_id"] in (
        seeded["people"]["Zhi Yang"],
        seeded["people"]["Kia Yee"],
    )
    assert r.json()["brand_matched"] is False


def test_promotion_brand_and_untagged_fallback(seeded):
    """AC2-R3 - cabana draws Aqi and Am (untagged serves all); mocha only Am."""
    cabana = [
        _post(seeded, team_code="marketing_promotion", brand_code="cabana").json()
        for _ in range(2)
    ]
    assert sorted(r["assignee_id"] for r in cabana) == sorted(
        [seeded["people"]["Am"], seeded["people"]["Aqi"]]
    )
    assert all(r["brand_matched"] is True for r in cabana)

    # Nobody in the promotion team is tagged mocha, so only the untagged member
    # is eligible - and that is not a brand match.
    for _ in range(2):
        mocha = _post(seeded, team_code="marketing_promotion", brand_code="mocha").json()
        assert mocha["assignee_id"] == seeded["people"]["Am"]
        assert mocha["brand_matched"] is False


def test_legacy_suffixed_promotion_key_still_routes(seeded):
    """AC2-X1 end-to-end: the old key resolves against the collapsed set."""
    r = _post(seeded, team_code="marketing_promotion_cabana")

    assert r.status_code == 200, r.text
    assert r.json()["team_set_code"] == "marketing_promotion"
    assert r.json()["assignee_id"] in (
        seeded["people"]["Am"],
        seeded["people"]["Aqi"],
    )


def test_team_members_returns_the_same_pool(seeded):
    """AC2-X1 - the roster n8n reads is the pool next-assignee draws from."""
    r = seeded["client"].get(
        "/api/v1/external/team-members",
        params={
            "agent_code": seeded["agent_code"],
            "team_code": "marketing_product",
            "tier": 1,
            "brand_code": "mocha",
        },
    )

    assert r.status_code == 200, r.text
    assert [m["user_id"] for m in r.json()] == [seeded["people"]["Kia Yee"]]


def test_team_members_without_a_brand_returns_everybody(seeded):
    r = seeded["client"].get(
        "/api/v1/external/team-members",
        params={
            "agent_code": seeded["agent_code"],
            "team_code": "marketing_product",
            "tier": 1,
        },
    )

    assert sorted(m["user_id"] for m in r.json()) == sorted(
        [seeded["people"]["Zhi Yang"], seeded["people"]["Kia Yee"]]
    )


def test_team_members_reads_the_brand_off_a_legacy_suffixed_code(seeded):
    """AC2-X1 / AC2-X3 - the old key narrows the roster exactly as it narrows the pool.

    Without the suffix-derived brand the roster answers with everybody, and n8n then
    offers a preferred_assignee_id that next-assignee (which DOES read the suffix)
    would never have drawn.
    """
    db = seeded["db"]
    hasni_id = str(uuid.uuid4())
    db.add(
        User(
            id=hasni_id,
            email=f"{unique_code('u').lower()}@zzt.test",
            name="ZZT Hasni",
            status="ACTIVE",
        )
    )
    db.flush()
    member_id = str(uuid.uuid4())
    db.add(
        TeamMember(
            id=member_id,
            team_id=seeded["teams"]["promotion"],
            user_id=hasni_id,
            sort_order=3,
        )
    )
    db.flush()
    db.execute(
        team_member_brands.insert().values(team_member_id=member_id, brand_code="mocha")
    )
    db.flush()

    r = seeded["client"].get(
        "/api/v1/external/team-members",
        params={
            "agent_code": seeded["agent_code"],
            "team_code": "marketing_promotion_cabana",
            "tier": 1,
        },
    )

    assert r.status_code == 200, r.text
    # Am (untagged, serves all) and Aqi (cabana) - never the mocha specialist.
    assert sorted(m["user_id"] for m in r.json()) == sorted(
        [seeded["people"]["Am"], seeded["people"]["Aqi"]]
    )


def test_team_members_lets_an_explicit_brand_beat_the_suffix(seeded):
    """AC2-X3 - the explicit param wins here too, or the two endpoints disagree."""
    r = seeded["client"].get(
        "/api/v1/external/team-members",
        params={
            "agent_code": seeded["agent_code"],
            "team_code": "marketing_promotion_cabana",
            "tier": 1,
            "brand_code": "mocha",
        },
    )

    assert r.status_code == 200, r.text
    # Mocha, not cabana: only the untagged member serves it, so Aqi is out.
    assert [m["user_id"] for m in r.json()] == [seeded["people"]["Am"]]


def test_team_members_honours_the_company_override(seeded):
    """AC2-X1 - same company resolution as next-assignee, or the ids disagree."""
    r = seeded["client"].get(
        "/api/v1/external/team-members",
        params={
            "agent_code": seeded["agent_code"],
            "team_code": "marketing_product",
            "tier": 1,
            "company_id": seeded["mocha_company"],
        },
    )

    assert r.status_code == 200, r.text
    assert [m["user_id"] for m in r.json()] == [seeded["people"]["Mocha CS"]]
