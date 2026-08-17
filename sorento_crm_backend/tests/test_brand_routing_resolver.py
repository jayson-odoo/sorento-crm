"""AC2-R1 - the brand narrows the MEMBER POOL, not the tier row.

One rule, the same one market segments already use: a member tagged with the brand
serves it, a member tagged with nothing serves every brand, and when nobody in the
team carries the brand the whole team round-robins. Routing therefore never
dead-ends on a brand the admin has not tagged anybody with, which is why there is
no "all brands" row to configure and no save-time guard to trip over.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.access import (
    AccessAgent,
    AgentTeam,
    AgentTeamRoundRobinCursor,
    MarketSegment,
    Team,
    TeamMember,
    team_member_brands,
)
from app.models.base import set_company_scope
from app.models.user import User
from app.services.user_service import (
    AccessAgentService,
    brand_pool_key,
    member_serves_brand,
    normalise_brand_code,
    split_legacy_team_set_code,
)
from tests._pg_fixture import blank_session, unique_code


SORENTO = "00000000-0000-0000-0000-000000000001"
SET = "zzt_marketing_promotion"


@pytest.fixture
def db():
    with blank_session() as session:
        set_company_scope(session, frozenset({SORENTO}))
        yield session


@pytest.fixture
def svc(db):
    return AccessAgentService(db)


def _agent(db) -> str:
    aid = str(uuid.uuid4())
    db.add(AccessAgent(id=aid, code=unique_code("agent"), name="ZZT Agent", is_active=True))
    db.flush()
    return aid


def _team(db, name: str, company_id: str = SORENTO) -> str:
    tid = str(uuid.uuid4())
    db.add(Team(id=tid, name=f"ZZT {name}", company_id=company_id))
    db.flush()
    return tid


def _user(db, name: str) -> str:
    uid = str(uuid.uuid4())
    db.add(
        User(
            id=uid,
            email=f"{unique_code('u').lower()}@zzt.test",
            name=f"ZZT {name}",
            status="ACTIVE",
        )
    )
    db.flush()
    return uid


def _member(
    db,
    team_id: str,
    user_id: str,
    *,
    brands: list[str] | None = None,
    segments: list[str] | None = None,
    sort_order: int | None = None,
    include_in_round_robin: bool = True,
) -> str:
    member_id = str(uuid.uuid4())
    member = TeamMember(
        id=member_id,
        team_id=team_id,
        user_id=user_id,
        sort_order=sort_order,
        include_in_round_robin=include_in_round_robin,
    )
    db.add(member)
    db.flush()
    for code in brands or []:
        db.execute(
            team_member_brands.insert().values(team_member_id=member_id, brand_code=code)
        )
    if segments:
        member.market_segments = _segments(db, segments)
    db.flush()
    return member_id


def _segments(db, codes: list[str]) -> list[MarketSegment]:
    out = []
    for code in codes:
        row = db.query(MarketSegment).filter(MarketSegment.code == code).first()
        if row is None:
            row = MarketSegment(id=str(uuid.uuid4()), code=code, name=code.title())
            db.add(row)
            db.flush()
        out.append(row)
    return out


def _link(db, agent_id: str, team_id: str, tier, code: str = SET) -> None:
    db.add(
        AgentTeam(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            code=code,
            team_id=team_id,
            tier=tier,
            company_id=SORENTO,
        )
    )
    db.flush()


@pytest.fixture
def promo_team(db):
    """One tier-1 team: Kia Yee tags mocha, Aqi tags cabana, Am is untagged."""
    agent_id = _agent(db)
    team_id = _team(db, "Promotion")
    _link(db, agent_id, team_id, 1)
    people = {
        "Am": _user(db, "Am"),
        "Kia Yee": _user(db, "Kia Yee"),
        "Aqi": _user(db, "Aqi"),
    }
    _member(db, team_id, people["Am"], sort_order=1)
    _member(db, team_id, people["Kia Yee"], brands=["mocha"], sort_order=2)
    _member(db, team_id, people["Aqi"], brands=["cabana"], sort_order=3)
    return {"agent_id": agent_id, "team_id": team_id, "people": people}


# ---------------------------------------------------------------- helpers


def test_normalise_brand_code_trims_lowercases_and_blanks_to_none():
    assert normalise_brand_code("  MoChA ") == "mocha"
    assert normalise_brand_code("") is None
    assert normalise_brand_code("   ") is None
    assert normalise_brand_code(None) is None


def test_split_legacy_team_set_code_reads_the_suffix_as_a_brand():
    """AC2-X1 - one release of compatibility for the old n8n workflow."""
    assert split_legacy_team_set_code("marketing_promotion_mocha") == (
        "marketing_promotion",
        "mocha",
    )
    assert split_legacy_team_set_code("marketing_promotion_sorento") == (
        "marketing_promotion",
        "sorento",
    )
    assert split_legacy_team_set_code("marketing_promotion_cabana") == (
        "marketing_promotion",
        "cabana",
    )
    # Anything else is left alone - including the base code itself.
    assert split_legacy_team_set_code("marketing_promotion") == (
        "marketing_promotion",
        None,
    )
    assert split_legacy_team_set_code("marketing_product") == ("marketing_product", None)
    assert split_legacy_team_set_code(None) == (None, None)
    # Case is not part of the key: n8n sends whatever the workflow typed.
    assert split_legacy_team_set_code("Marketing_Promotion_MOCHA") == (
        "marketing_promotion",
        "mocha",
    )


def test_member_serves_brand_is_the_untagged_serves_all_rule():
    assert member_serves_brand(["mocha"], "mocha") is True
    assert member_serves_brand(["MOCHA"], "mocha") is True
    assert member_serves_brand(["mocha"], "cabana") is False
    # Untagged serves every brand, and no brand asked for matches everybody.
    assert member_serves_brand([], "mocha") is True
    assert member_serves_brand(None, "mocha") is True
    assert member_serves_brand(["mocha"], None) is True


def test_brand_pool_key_is_empty_when_no_brand_narrowed_anything():
    assert brand_pool_key(None) == ""
    assert brand_pool_key("  ") == ""
    assert brand_pool_key(" MoChA ") == "~b:mocha"


# ------------------------------------------------------------------ AC2-R1


@pytest.fixture
def tagged_only(db):
    """Every member tagged, so a brand names exactly one of them."""
    agent_id = _agent(db)
    team_id = _team(db, "Tagged Only")
    _link(db, agent_id, team_id, 1)
    people = {"Kia Yee": _user(db, "Kia Yee"), "Aqi": _user(db, "Aqi")}
    _member(db, team_id, people["Kia Yee"], brands=["mocha"], sort_order=1)
    _member(db, team_id, people["Aqi"], brands=["cabana"], sort_order=2)
    return {"agent_id": agent_id, "team_id": team_id, "people": people}


def test_a_tagged_member_takes_their_own_brand(svc, tagged_only):
    mocha = svc.get_next_assignee(
        tagged_only["agent_id"], tagged_only["team_id"], brand_code="mocha"
    )
    cabana = svc.get_next_assignee(
        tagged_only["agent_id"], tagged_only["team_id"], brand_code="cabana"
    )

    assert mocha["id"] == tagged_only["people"]["Kia Yee"]
    assert mocha["brand_matched"] is True
    assert cabana["id"] == tagged_only["people"]["Aqi"]
    assert cabana["brand_matched"] is True


def test_the_brand_match_is_case_insensitive(svc, tagged_only):
    assignee = svc.get_next_assignee(
        tagged_only["agent_id"], tagged_only["team_id"], brand_code="MOCHA"
    )

    assert assignee["id"] == tagged_only["people"]["Kia Yee"]


def test_an_untagged_member_serves_a_brand_nobody_claimed(svc, promo_team):
    """Sorento is tagged on nobody, so only the untagged member is eligible."""
    for _ in range(3):
        assignee = svc.get_next_assignee(
            promo_team["agent_id"], promo_team["team_id"], brand_code="sorento"
        )
        assert assignee["id"] == promo_team["people"]["Am"]
        # The untagged fallback is not a brand match - n8n must be able to tell.
        assert assignee["brand_matched"] is False


def test_an_untagged_member_rotates_with_the_tagged_one(svc, promo_team):
    """The mocha pool is Kia Yee AND Am (untagged = serves every brand).

    Am comes first because the pool keeps the team's round-robin order; what the
    brand decides is who is IN the pool, never who is next. Aqi, tagged cabana,
    never appears.
    """
    picked = [
        svc.get_next_assignee(
            promo_team["agent_id"], promo_team["team_id"], brand_code="mocha"
        )["id"]
        for _ in range(4)
    ]

    people = promo_team["people"]
    assert picked == [
        people["Am"],
        people["Kia Yee"],
        people["Am"],
        people["Kia Yee"],
    ]


def test_an_empty_pool_falls_back_to_the_whole_team(svc, db):
    """Every member tagged, none with this brand: the whole team round-robins."""
    agent_id = _agent(db)
    team_id = _team(db, "All Tagged")
    _link(db, agent_id, team_id, 1)
    mocha_user = _user(db, "Kia Yee")
    cabana_user = _user(db, "Aqi")
    _member(db, team_id, mocha_user, brands=["mocha"], sort_order=1)
    _member(db, team_id, cabana_user, brands=["cabana"], sort_order=2)

    picked = [
        svc.get_next_assignee(agent_id, team_id, brand_code="sorento")["id"]
        for _ in range(2)
    ]

    assert sorted(picked) == sorted([mocha_user, cabana_user])
    assert (
        svc.get_next_assignee(agent_id, team_id, brand_code="sorento")["brand_matched"]
        is False
    )


def test_a_member_may_carry_several_brands(svc, db):
    agent_id = _agent(db)
    team_id = _team(db, "Multi")
    _link(db, agent_id, team_id, 1)
    zhi_yang = _user(db, "Zhi Yang")
    kia_yee = _user(db, "Kia Yee")
    _member(db, team_id, zhi_yang, brands=["sorento", "cabana"], sort_order=1)
    _member(db, team_id, kia_yee, brands=["mocha"], sort_order=2)

    assert svc.get_next_assignee(agent_id, team_id, brand_code="cabana")["id"] == zhi_yang
    assert svc.get_next_assignee(agent_id, team_id, brand_code="sorento")["id"] == zhi_yang
    assert svc.get_next_assignee(agent_id, team_id, brand_code="mocha")["id"] == kia_yee


def test_a_member_excluded_from_round_robin_is_never_drawn_by_brand(svc, db):
    """The brand filter narrows the RR-eligible pool; it cannot widen it."""
    agent_id = _agent(db)
    team_id = _team(db, "Excluded")
    _link(db, agent_id, team_id, 1)
    excluded = _user(db, "On Leave")
    working = _user(db, "Working")
    _member(db, team_id, excluded, brands=["mocha"], sort_order=1, include_in_round_robin=False)
    _member(db, team_id, working, sort_order=2)

    assignee = svc.get_next_assignee(agent_id, team_id, brand_code="mocha")

    assert assignee["id"] == working
    assert assignee["brand_matched"] is False


def test_no_brand_leaves_the_pool_and_the_cursor_exactly_as_before(svc, promo_team, db):
    """AC2-R1 - the legacy '' cursor is untouched when nothing narrowed."""
    picked = [
        svc.get_next_assignee(promo_team["agent_id"], promo_team["team_id"])["id"]
        for _ in range(3)
    ]

    people = promo_team["people"]
    assert picked == [people["Am"], people["Kia Yee"], people["Aqi"]]
    keys = [
        c.segment_key
        for c in db.query(AgentTeamRoundRobinCursor)
        .filter(AgentTeamRoundRobinCursor.team_id == promo_team["team_id"])
        .all()
    ]
    assert keys == [""]


# ------------------------------------------ brand AND market segment compose


def test_the_brand_and_the_segment_filter_are_anded(svc, db):
    agent_id = _agent(db)
    team_id = _team(db, "CS")
    _link(db, agent_id, team_id, 1)
    both = _user(db, "Mocha Retail")
    wrong_segment = _user(db, "Mocha Project")
    wrong_brand = _user(db, "Cabana Retail")
    _member(db, team_id, both, brands=["mocha"], segments=["zzt_retail"], sort_order=1)
    _member(
        db, team_id, wrong_segment, brands=["mocha"], segments=["zzt_project"], sort_order=2
    )
    _member(
        db, team_id, wrong_brand, brands=["cabana"], segments=["zzt_retail"], sort_order=3
    )

    for _ in range(3):
        assignee = svc.get_next_assignee(
            agent_id, team_id, {"zzt_retail"}, brand_code="mocha"
        )
        assert assignee["id"] == both


def test_an_untagged_member_passes_both_filters(svc, db):
    agent_id = _agent(db)
    team_id = _team(db, "CS")
    _link(db, agent_id, team_id, 1)
    generalist = _user(db, "Generalist")
    specialist = _user(db, "Cabana Project")
    _member(db, team_id, generalist, sort_order=1)
    _member(
        db, team_id, specialist, brands=["cabana"], segments=["zzt_project"], sort_order=2
    )

    assignee = svc.get_next_assignee(agent_id, team_id, {"zzt_retail"}, brand_code="mocha")

    assert assignee["id"] == generalist


# ---------------------------------------------------------- cursor scoping


def test_each_brand_pool_rotates_on_its_own_cursor(svc, promo_team, db):
    """Interleaved brands must not steal each other's turn."""
    people = promo_team["people"]
    agent_id, team_id = promo_team["agent_id"], promo_team["team_id"]

    assert svc.get_next_assignee(agent_id, team_id, brand_code="mocha")["id"] == people["Am"]
    assert svc.get_next_assignee(agent_id, team_id, brand_code="cabana")["id"] == people["Am"]
    # Each cursor is where its own brand left it, not where the other one moved it.
    assert (
        svc.get_next_assignee(agent_id, team_id, brand_code="mocha")["id"]
        == people["Kia Yee"]
    )
    assert svc.get_next_assignee(agent_id, team_id, brand_code="cabana")["id"] == people["Aqi"]

    keys = sorted(
        c.segment_key
        for c in db.query(AgentTeamRoundRobinCursor)
        .filter(AgentTeamRoundRobinCursor.team_id == team_id)
        .all()
    )
    assert keys == ["~b:cabana", "~b:mocha"]


def test_the_segment_and_brand_cursor_keys_compose(svc, db):
    agent_id = _agent(db)
    team_id = _team(db, "CS")
    _link(db, agent_id, team_id, 1)
    _member(
        db,
        team_id,
        _user(db, "Mocha Retail"),
        brands=["mocha"],
        segments=["zzt_retail"],
        sort_order=1,
    )

    svc.get_next_assignee(agent_id, team_id, {"zzt_retail"}, brand_code="mocha")

    keys = [
        c.segment_key
        for c in db.query(AgentTeamRoundRobinCursor)
        .filter(AgentTeamRoundRobinCursor.team_id == team_id)
        .all()
    ]
    assert keys == ["zzt_retail~b:mocha"]


def test_a_team_nobody_tagged_keeps_the_legacy_cursor(svc, db):
    """A brand that narrowed nothing must not split an existing rotation in two."""
    agent_id = _agent(db)
    team_id = _team(db, "Untagged")
    _link(db, agent_id, team_id, 1)
    _member(db, team_id, _user(db, "A"), sort_order=1)
    _member(db, team_id, _user(db, "B"), sort_order=2)

    svc.get_next_assignee(agent_id, team_id, brand_code="mocha")
    svc.get_next_assignee(agent_id, team_id, brand_code="cabana")

    keys = [
        c.segment_key
        for c in db.query(AgentTeamRoundRobinCursor)
        .filter(AgentTeamRoundRobinCursor.team_id == team_id)
        .all()
    ]
    assert keys == [""]


# --------------------------------------------------------------- the roster


def test_the_roster_filters_on_the_same_pool_rule(svc, promo_team):
    """AC2-X1 - team-members is the pool next-assignee draws from."""
    people = promo_team["people"]

    mocha = svc.list_active_team_members_detail(promo_team["team_id"], brand_code="mocha")
    assert sorted(m["user_id"] for m in mocha) == sorted(
        [people["Am"], people["Kia Yee"]]
    )

    sorento = svc.list_active_team_members_detail(
        promo_team["team_id"], brand_code="sorento"
    )
    assert [m["user_id"] for m in sorento] == [people["Am"]]

    everyone = svc.list_active_team_members_detail(promo_team["team_id"])
    assert len(everyone) == 3


def test_the_roster_falls_back_to_everybody_when_nobody_matches(svc, db):
    agent_id = _agent(db)
    team_id = _team(db, "All Tagged")
    _link(db, agent_id, team_id, 1)
    _member(db, team_id, _user(db, "Kia Yee"), brands=["mocha"], sort_order=1)
    _member(db, team_id, _user(db, "Aqi"), brands=["cabana"], sort_order=2)

    rows = svc.list_active_team_members_detail(team_id, brand_code="sorento")

    assert len(rows) == 2
