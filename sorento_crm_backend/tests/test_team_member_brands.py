"""AC2-M1 / AC2-F1 - reading and writing a member's brand tags.

Mirrors the market-segment assignment tests: the tags are keyed by (team, user),
replaced wholesale, stored lower-case, and an unknown brand code is refused so a
typo cannot silently create a tag nobody routes to.

The seeded brands carry UPPER-CASE codes on purpose: that is the shape production
holds (MOCHA, CABANA), and a fixture seeding them lower-case hides a validator that
only matches an exact-case code.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.access import Team, TeamMember, team_member_brands
from app.models.base import set_company_scope
from app.models.product import Brand
from app.models.user import User
from app.services.error_handler import AppException
from app.services.team_member_brand_service import TeamMemberBrandService
from tests._pg_fixture import blank_session, unique_code


SORENTO = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def world():
    with blank_session() as db:
        set_company_scope(db, frozenset({SORENTO}))
        for code, name in (("ZZT_MOCHA", "ZZT Mocha"), ("ZZT_CABANA", "ZZT Cabana")):
            db.add(
                Brand(
                    id=str(uuid.uuid4()),
                    brand_code=code,
                    brand_name=name,
                    company_id=SORENTO,
                )
            )
        team_id = str(uuid.uuid4())
        db.add(Team(id=team_id, name="ZZT Promotion", company_id=SORENTO))
        user_id = str(uuid.uuid4())
        db.add(
            User(
                id=user_id,
                email=f"{unique_code('u').lower()}@zzt.test",
                name="ZZT Kia Yee",
                status="ACTIVE",
            )
        )
        db.flush()
        member_id = str(uuid.uuid4())
        db.add(TeamMember(id=member_id, team_id=team_id, user_id=user_id))
        db.flush()
        yield {
            "db": db,
            "team_id": team_id,
            "user_id": user_id,
            "member_id": member_id,
            "svc": TeamMemberBrandService(db),
        }


def test_a_member_starts_untagged(world):
    assert world["svc"].get_member_brand_codes_by_team_user(
        world["team_id"], world["user_id"]
    ) == []


def test_tags_are_stored_lower_case_and_read_back_sorted(world):
    saved = world["svc"].set_member_brands_by_team_user(
        world["team_id"], world["user_id"], [" ZZT_Mocha ", "ZZT_CABANA"]
    )

    assert saved == ["zzt_cabana", "zzt_mocha"]
    assert world["svc"].get_member_brand_codes_by_team_user(
        world["team_id"], world["user_id"]
    ) == ["zzt_cabana", "zzt_mocha"]


def test_saving_replaces_the_whole_set(world):
    svc = world["svc"]
    svc.set_member_brands_by_team_user(
        world["team_id"], world["user_id"], ["zzt_mocha", "zzt_cabana"]
    )

    assert svc.set_member_brands_by_team_user(
        world["team_id"], world["user_id"], ["zzt_mocha"]
    ) == ["zzt_mocha"]


def test_an_empty_list_clears_the_tags_back_to_serves_all(world):
    svc = world["svc"]
    svc.set_member_brands_by_team_user(world["team_id"], world["user_id"], ["zzt_mocha"])

    assert svc.set_member_brands_by_team_user(world["team_id"], world["user_id"], []) == []
    rows = world["db"].query(team_member_brands).all()
    assert rows == []


def test_a_repeated_code_is_stored_once(world):
    assert world["svc"].set_member_brands_by_team_user(
        world["team_id"], world["user_id"], ["zzt_mocha", "ZZT_MOCHA"]
    ) == ["zzt_mocha"]


def test_an_unknown_brand_code_is_refused(world):
    with pytest.raises(AppException) as exc:
        world["svc"].set_member_brands_by_team_user(
            world["team_id"], world["user_id"], ["zzt_mocha", "not_a_brand"]
        )

    assert "not_a_brand" in str(exc.value.detail)
    # Only the typo is named - the real brand validates despite the seeded code
    # being upper-case.
    assert "zzt_mocha" not in str(exc.value.detail)
    # Nothing was written: validation runs before the replace.
    assert world["svc"].get_member_brand_codes_by_team_user(
        world["team_id"], world["user_id"]
    ) == []


def test_an_unknown_membership_is_a_404(world):
    with pytest.raises(AppException) as exc:
        world["svc"].get_member_brand_codes_by_team_user(
            world["team_id"], str(uuid.uuid4())
        )

    assert exc.value.status_code == 404


def test_deleting_the_membership_takes_its_tags_with_it(world):
    db = world["db"]
    world["svc"].set_member_brands_by_team_user(
        world["team_id"], world["user_id"], ["zzt_mocha"]
    )

    db.query(TeamMember).filter(TeamMember.id == world["member_id"]).delete()
    db.flush()

    assert db.query(team_member_brands).all() == []
