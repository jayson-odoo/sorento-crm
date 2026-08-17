"""Migration 371 tested by running it, not by asserting on the live database.

Same shape as tests/test_migration_320_company_routing.py: the local database is a
copy of production and is already past this lineage, so "does the table exist"
there proves nothing. This builds the schema on a scratch schema, seeds the SHAPE of
today's Sorento promotion configuration, runs ``upgrade()`` against it and asserts
the collapse produced exactly the rows and the tags the UAC describes (AC2-M1,
AC2-M2).
"""
from __future__ import annotations

import importlib.util
import logging
import uuid
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from app.models.access import Team, TeamMember
from app.models.user import User
from tests._pg_fixture import blank_session


SORENTO = "00000000-0000-0000-0000-000000000001"
BASE = "marketing_promotion"
MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "371_brand_member_routing.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("m371", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_upgrade(db):
    module = _load_migration()
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        module.upgrade()
    return module


def _run_downgrade(db):
    module = _load_migration()
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        module.downgrade()


# ------------------------------------------------------------------ seeding


def _agent(db) -> str:
    # The scratch schema comes from create_all, which carries the models' Python-side
    # defaults but none of the server defaults the migrations add - so every NOT NULL
    # column has to be supplied by hand here.
    aid = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO access_agents (id, code, name, is_active, "
            "assign_to_new_internal_contacts, synced_to_excel) "
            "VALUES (:i, :c, 'ZZT Agent', true, false, false)"
        ),
        {"i": aid, "c": f"ZZT-agent-{uuid.uuid4().hex[:8]}"},
    )
    return aid


def _team(db, name: str, company_id: str = SORENTO) -> str:
    tid = str(uuid.uuid4())
    db.add(Team(id=tid, name=f"ZZT {name}", company_id=company_id))
    db.flush()
    return tid


def _person(db, team_id: str, name: str, *, sort_order=None, in_rr: bool = True) -> str:
    uid = str(uuid.uuid4())
    db.add(
        User(
            id=uid,
            email=f"{uuid.uuid4().hex[:10]}@zzt.test",
            name=f"ZZT {name}",
            status="ACTIVE",
        )
    )
    db.flush()
    db.add(
        TeamMember(
            id=str(uuid.uuid4()),
            team_id=team_id,
            user_id=uid,
            sort_order=sort_order,
            include_in_round_robin=in_rr,
        )
    )
    db.flush()
    return uid


def _policy(db) -> str:
    pid = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO sla_policies (id, code, name, is_active, company_id) "
            "VALUES (:i, :c, 'ZZT Policy', true, :co)"
        ),
        {"i": pid, "c": f"ZZT-pol-{uuid.uuid4().hex[:8]}", "co": SORENTO},
    )
    return pid


def _link(
    db,
    agent_id: str,
    code: str,
    team_id: str,
    tier,
    policy_id: str | None = None,
    company_id: str = SORENTO,
    notify_on_extension: bool = True,
) -> str:
    row_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO agent_teams (id, agent_id, code, team_id, tier, policy_id, "
            "company_id, notify_on_extension) "
            "VALUES (:i, :a, :c, :t, :tr, :p, :co, :n)"
        ),
        {
            "i": row_id,
            "a": agent_id,
            "c": code,
            "t": team_id,
            "tr": tier,
            "p": policy_id,
            "co": company_id,
            "n": notify_on_extension,
        },
    )
    return row_id


def _brand(db, code: str, company_id: str = SORENTO) -> str:
    bid = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO brands (id, brand_code, brand_name, is_active, access_levels, "
            "company_id) VALUES (:i, :c, :n, true, '[\"dealer\"]', :co)"
        ),
        {"i": bid, "c": code, "n": f"ZZT {code}", "co": company_id},
    )
    return bid


def _tracker(db, team_set_code: str, policy_id: str) -> str:
    tid = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO conversation_sla_tracking (id, policy_id, current_tier, "
            "due_at, is_responded, is_resolved, synced_to_excel, team_set_code, "
            "company_id) "
            "VALUES (:i, :p, 1, now(), false, false, false, :ts, :co)"
        ),
        {"i": tid, "p": policy_id, "ts": team_set_code, "co": SORENTO},
    )
    return tid


def _promotion_rows(db, agent_id: str) -> list[dict]:
    rows = db.execute(
        text(
            "SELECT code, tier, team_id, policy_id "
            "FROM agent_teams WHERE agent_id = :a AND code LIKE 'marketing_promotion%' "
            "ORDER BY tier NULLS FIRST, code"
        ),
        {"a": agent_id},
    ).mappings()
    return [dict(r) for r in rows]


def _roster(db, team_id: str) -> dict[str, dict]:
    """``{user_id: {sort_order, include_in_round_robin, brands}}`` for a team."""
    rows = db.execute(
        text(
            "SELECT tm.user_id, tm.sort_order, tm.include_in_round_robin, "
            "       coalesce(array_agg(tmb.brand_code ORDER BY tmb.brand_code) "
            "                FILTER (WHERE tmb.brand_code IS NOT NULL), '{}') AS brands "
            "FROM team_members tm "
            "LEFT JOIN team_member_brands tmb ON tmb.team_member_id = tm.id "
            "WHERE tm.team_id = :t "
            "GROUP BY tm.user_id, tm.sort_order, tm.include_in_round_robin"
        ),
        {"t": team_id},
    ).mappings()
    return {
        str(r["user_id"]): {
            "sort_order": r["sort_order"],
            "include_in_round_robin": r["include_in_round_robin"],
            "brands": list(r["brands"]),
        }
        for r in rows
    }


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def todays_config(db):
    """The shape of the Sorento promotion configuration: three suffixed sets that
    mean ONE set - distinct tier-1 teams per brand, one shared tier-2 team, one
    shared tier-3 team.

    The policy binding is NOT a mirror of the live rows: there all three suffixed
    sets carry ``policy_id`` NULL. It is bound on the _sorento set here so the
    policy-inheritance half of the collapse is exercised at all; the live all-NULL
    case has its own test below, as does the case where the sets disagree.
    """
    agent_id = _agent(db)
    policy = _policy(db)
    teams = {
        "sorento_t1": _team(db, "Promo Sorento T1"),
        "mocha_t1": _team(db, "Promo Mocha T1"),
        "cabana_t1": _team(db, "Promo Cabana T1"),
        "shared_t2": _team(db, "Promo T2"),
        "shared_t3": _team(db, "Promo T3"),
        "product_t1": _team(db, "Product T1"),
    }
    people = {
        "Am": _person(db, teams["sorento_t1"], "Am", sort_order=1),
        "Kia Yee": _person(db, teams["mocha_t1"], "Kia Yee", sort_order=1),
        "Aqi": _person(db, teams["cabana_t1"], "Aqi", sort_order=1),
        "Boss": _person(db, teams["shared_t2"], "Boss", sort_order=1),
    }
    for brand in ("sorento", "mocha", "cabana"):
        _link(
            db,
            agent_id,
            f"{BASE}_{brand}",
            teams[f"{brand}_t1"],
            1,
            policy_id=policy if brand == "sorento" else None,
        )
        _link(
            db,
            agent_id,
            f"{BASE}_{brand}",
            teams["shared_t2"],
            2,
            policy_id=policy if brand == "sorento" else None,
        )
        _link(
            db,
            agent_id,
            f"{BASE}_{brand}",
            teams["shared_t3"],
            3,
            policy_id=policy if brand == "sorento" else None,
        )
    # The control set: a different function, must come out byte-identical.
    _link(db, agent_id, "marketing_product", teams["product_t1"], 1, policy_id=policy)
    db.flush()
    return {"agent_id": agent_id, "policy": policy, "teams": teams, "people": people}


# ------------------------------------------------------------------ AC2-M1


def test_the_join_table_exists_with_the_pair_as_its_key(db):
    _run_upgrade(db)

    columns = {
        r[0]: (r[1], r[2])
        for r in db.execute(
            text(
                "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = 'team_member_brands'"
            )
        )
    }
    assert set(columns) == {"team_member_id", "brand_code", "created_at"}
    assert columns["brand_code"][0] == "text"
    assert columns["team_member_id"][1] == "NO"
    assert columns["brand_code"][1] == "NO"


def test_a_tag_dies_with_its_membership(db):
    """AC2-M1 - the FK cascades, so a removed member leaves no orphan tags."""
    _run_upgrade(db)
    team_id = _team(db, "Promo")
    _person(db, team_id, "Kia Yee")
    member_id = db.execute(
        text("SELECT id FROM team_members WHERE team_id = :t"), {"t": team_id}
    ).scalar()
    db.execute(
        text(
            "INSERT INTO team_member_brands (team_member_id, brand_code) "
            "VALUES (:m, 'mocha')"
        ),
        {"m": member_id},
    )

    db.execute(text("DELETE FROM team_members WHERE id = :m"), {"m": member_id})

    assert db.execute(text("SELECT count(*) FROM team_member_brands")).scalar() == 0


def test_the_same_brand_twice_on_one_member_is_a_duplicate(db):
    from sqlalchemy.exc import IntegrityError

    _run_upgrade(db)
    team_id = _team(db, "Promo")
    _person(db, team_id, "Kia Yee")
    member_id = db.execute(
        text("SELECT id FROM team_members WHERE team_id = :t"), {"t": team_id}
    ).scalar()
    for _ in range(1):
        db.execute(
            text(
                "INSERT INTO team_member_brands (team_member_id, brand_code) "
                "VALUES (:m, 'mocha')"
            ),
            {"m": member_id},
        )

    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO team_member_brands (team_member_id, brand_code) "
                "VALUES (:m, 'mocha')"
            ),
            {"m": member_id},
        )
    db.rollback()


def test_agent_teams_is_left_alone(db):
    """AC2-M2 - no brand column and the 320-era unique keys, unchanged."""
    def _defs():
        return {
            r[0]: r[1]
            for r in db.execute(
                text(
                    "SELECT indexname, indexdef FROM pg_indexes "
                    "WHERE schemaname = current_schema() AND tablename = 'agent_teams'"
                )
            )
        }

    before = _defs()
    _run_upgrade(db)

    assert _defs() == before
    assert all("coalesce" not in d.lower() for d in _defs().values())
    assert db.execute(
        text(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = 'agent_teams' "
            "AND column_name = 'brand_code'"
        )
    ).scalar() == 0


def test_the_tracker_keeps_its_brand_column(db):
    _run_upgrade(db)

    row = db.execute(
        text(
            "SELECT data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = 'conversation_sla_tracking' AND column_name = 'brand_code'"
        )
    ).first()

    assert row == ("text", "YES")


# ------------------------------------------------------------------ AC2-M2


def test_collapses_todays_three_promotion_sets_into_one(db, todays_config):
    """AC2-M2 - one set, one team per tier, the brands moved onto the people."""
    agent_id = todays_config["agent_id"]
    teams = todays_config["teams"]
    people = todays_config["people"]

    _run_upgrade(db)

    rows = _promotion_rows(db, agent_id)
    assert all(r["code"] == BASE for r in rows), rows
    assert {r["tier"]: str(r["team_id"]) for r in rows} == {
        1: teams["sorento_t1"],
        2: teams["shared_t2"],
        3: teams["shared_t3"],
    }
    # Every row of the collapsed set carries the former _sorento set's policy.
    assert {str(r["policy_id"]) for r in rows} == {todays_config["policy"]}

    roster = _roster(db, teams["sorento_t1"])
    assert set(roster) == {people["Am"], people["Kia Yee"], people["Aqi"]}
    # Am is today's default handler, so he stays untagged and serves every brand.
    assert roster[people["Am"]]["brands"] == []
    assert roster[people["Kia Yee"]]["brands"] == ["mocha"]
    assert roster[people["Aqi"]]["brands"] == ["cabana"]


def test_moved_members_land_after_the_existing_ones(db, todays_config):
    """AC2-M2 - the incoming people join the back of the round-robin queue."""
    teams = todays_config["teams"]
    people = todays_config["people"]

    _run_upgrade(db)

    roster = _roster(db, teams["sorento_t1"])
    assert roster[people["Am"]]["sort_order"] == 1
    assert sorted(
        [roster[people["Kia Yee"]]["sort_order"], roster[people["Aqi"]]["sort_order"]]
    ) == [2, 3]


def test_moved_members_land_behind_incumbents_with_no_sort_order(db):
    """Production shape: nobody in the surviving team has a sort_order at all.

    The resolver orders ``sort_order NULLS LAST``, so a NULL incumbent is ALREADY at
    the back; appending past ``max(sort_order)`` = 0 would hand the newcomer 1 and put
    them in FRONT of everybody, i.e. next in the rotation.
    """
    agent_id = _agent(db)
    sorento_t1, mocha_t1 = _team(db, "S1"), _team(db, "M1")
    am = _person(db, sorento_t1, "Am", sort_order=None)
    zhi_yang = _person(db, sorento_t1, "Zhi Yang", sort_order=None)
    kia_yee = _person(db, mocha_t1, "Kia Yee", sort_order=None)
    _link(db, agent_id, f"{BASE}_sorento", sorento_t1, 1)
    _link(db, agent_id, f"{BASE}_mocha", mocha_t1, 1)
    db.flush()

    _run_upgrade(db)

    roster = _roster(db, sorento_t1)
    incumbents = sorted([roster[am]["sort_order"], roster[zhi_yang]["sort_order"]])
    assert incumbents == [1, 2]
    assert roster[kia_yee]["sort_order"] > incumbents[-1]


def test_a_team_another_routing_row_still_points_at_is_not_emptied(db, caplog):
    """Moving those people would strip the OTHER set's pool to nobody.

    The mocha tier-1 team is also the team of a completely different agent_teams row,
    so its members stay where they are and the collapse says so.
    """
    agent_id = _agent(db)
    sorento_t1, mocha_t1 = _team(db, "S1"), _team(db, "M1")
    _person(db, sorento_t1, "Am", sort_order=1)
    kia_yee = _person(db, mocha_t1, "Kia Yee", sort_order=1)
    _link(db, agent_id, f"{BASE}_sorento", sorento_t1, 1)
    _link(db, agent_id, f"{BASE}_mocha", mocha_t1, 1)
    # The same team, used by another function entirely.
    _link(db, agent_id, "marketing_product", mocha_t1, 1)
    db.flush()

    with caplog.at_level(logging.WARNING, logger="alembic.runtime.migration"):
        _run_upgrade(db)

    assert list(_roster(db, mocha_t1)) == [kia_yee]
    assert _roster(db, mocha_t1)[kia_yee]["brands"] == []
    assert kia_yee not in _roster(db, sorento_t1)
    # The suffixed row still goes: the collapse is what it is, the people are not moved.
    assert [r["code"] for r in _promotion_rows(db, agent_id)] == [BASE]
    assert any(
        "another routing row" in r.getMessage() for r in caplog.records
    ), [r.getMessage() for r in caplog.records]


def test_the_round_robin_opt_out_survives_the_move(db):
    agent_id = _agent(db)
    sorento_t1, mocha_t1 = _team(db, "S1"), _team(db, "M1")
    _person(db, sorento_t1, "Am", sort_order=1)
    kia_yee = _person(db, mocha_t1, "Kia Yee", sort_order=1, in_rr=False)
    _link(db, agent_id, f"{BASE}_sorento", sorento_t1, 1)
    _link(db, agent_id, f"{BASE}_mocha", mocha_t1, 1)
    db.flush()

    _run_upgrade(db)

    assert _roster(db, sorento_t1)[kia_yee]["include_in_round_robin"] is False


def test_the_emptied_teams_are_left_in_place(db, todays_config):
    """The migration moves people, never deletes a team an admin may still be using."""
    teams = todays_config["teams"]

    _run_upgrade(db)

    assert db.execute(
        text("SELECT count(*) FROM teams WHERE id::text = ANY(:ids)"),
        {"ids": [teams["mocha_t1"], teams["cabana_t1"]]},
    ).scalar() == 2
    assert _roster(db, teams["mocha_t1"]) == {}


def test_no_suffixed_rows_survive(db, todays_config):
    """AC2-M2 - the admin sees ONE set afterwards."""
    _run_upgrade(db)

    assert db.execute(
        text(
            "SELECT count(*) FROM agent_teams WHERE code IN "
            "('marketing_promotion_sorento','marketing_promotion_mocha',"
            "'marketing_promotion_cabana')"
        )
    ).scalar() == 0


def test_control_set_is_untouched(db, todays_config):
    """A set outside the three promotion keys comes out byte-identical."""
    agent_id = todays_config["agent_id"]
    columns = (
        "id, agent_id, code, team_id, tier, policy_id, company_id, "
        "notify_on_extension, created_at"
    )

    def _read():
        rows = db.execute(
            text(
                f"SELECT {columns} FROM agent_teams "
                "WHERE agent_id = :a AND code = 'marketing_product'"
            ),
            {"a": agent_id},
        ).mappings().all()
        return [dict(r) for r in rows]

    before = _read()
    product_roster = _roster(db, todays_config["teams"]["product_t1"])

    _run_upgrade(db)

    assert _read() == before
    assert _roster(db, todays_config["teams"]["product_t1"]) == product_roster


def test_a_member_already_in_the_target_team_is_left_alone(db, caplog):
    """Tagging somebody who already serves every brand there would NARROW them.

    That is a routing change nobody asked for, so the duplicate membership is left
    exactly as it is and the migration says whose it was.
    """
    agent_id = _agent(db)
    sorento_t1, mocha_t1 = _team(db, "S1"), _team(db, "M1")
    shared = _person(db, sorento_t1, "Shared", sort_order=1)
    db.add(
        TeamMember(
            id=str(uuid.uuid4()), team_id=mocha_t1, user_id=shared, sort_order=1
        )
    )
    db.flush()
    _link(db, agent_id, f"{BASE}_sorento", sorento_t1, 1)
    _link(db, agent_id, f"{BASE}_mocha", mocha_t1, 1)
    db.flush()

    with caplog.at_level(logging.WARNING, logger="alembic.runtime.migration"):
        _run_upgrade(db)

    assert _roster(db, sorento_t1)[shared]["brands"] == []
    assert any("already" in r.getMessage() for r in caplog.records), [
        r.getMessage() for r in caplog.records
    ]


# --------------------------------------------------- AC2-M2, the policy binding


def _three_suffixed_sets(db, agent_id, policies: dict[str, str | None]) -> dict[str, str]:
    """One tier-1 team per brand plus a shared tier 2, each brand's policy as given."""
    teams = {brand: _team(db, f"Promo {brand} T1") for brand in policies}
    shared_t2 = _team(db, "Promo T2")
    for brand, policy_id in policies.items():
        _link(db, agent_id, f"{BASE}_{brand}", teams[brand], 1, policy_id=policy_id)
        _link(db, agent_id, f"{BASE}_{brand}", shared_t2, 2, policy_id=policy_id)
    db.flush()
    return {**teams, "shared_t2": shared_t2}


def test_a_policyless_collapse_leaves_every_row_null(db):
    """AC2-M2 - the actual production state: all three sets carry policy_id NULL.

    There is nothing to inherit, so the collapse must still run and must not write a
    policy onto the collapsed rows - an invented binding would put the whole set on
    somebody else's clocks.
    """
    agent_id = _agent(db)
    teams = _three_suffixed_sets(
        db, agent_id, {"sorento": None, "mocha": None, "cabana": None}
    )

    _run_upgrade(db)

    rows = _promotion_rows(db, agent_id)
    assert all(r["code"] == BASE for r in rows), rows
    assert all(r["policy_id"] is None for r in rows), rows
    assert {r["tier"]: str(r["team_id"]) for r in rows} == {
        1: teams["sorento"],
        2: teams["shared_t2"],
    }


def test_disagreeing_policies_collapse_onto_the_sorento_one(db):
    """AC2-M2 - one code, one policy: the _sorento binding is cast over the set.

    ``resolve_policy_id_for`` 409s when one code maps to two policies, so leaving the
    other brands' bindings in place would break the set the moment it is used.
    """
    agent_id = _agent(db)
    sorento_policy, mocha_policy, cabana_policy = _policy(db), _policy(db), _policy(db)
    _three_suffixed_sets(
        db,
        agent_id,
        {"sorento": sorento_policy, "mocha": mocha_policy, "cabana": cabana_policy},
    )

    _run_upgrade(db)

    rows = _promotion_rows(db, agent_id)
    assert {str(r["policy_id"]) for r in rows} == {sorento_policy}


# ------------------------------------------------- AC2-M2, the shared tiers


def test_a_tier2_disagreement_folds_the_other_teams_people_in_tagged(db):
    """Nobody's escalation ladder silently changes: the mocha tier-2 people move
    into the one tier-2 team carrying the mocha tag, so a mocha escalation still
    reaches them."""
    agent_id = _agent(db)
    s_t1, m_t1 = _team(db, "S1"), _team(db, "M1")
    s_t2, m_t2 = _team(db, "S2"), _team(db, "M2")
    _person(db, s_t1, "Am", sort_order=1)
    _person(db, m_t1, "Kia Yee", sort_order=1)
    boss = _person(db, s_t2, "Boss", sort_order=1)
    mocha_boss = _person(db, m_t2, "Mocha Boss", sort_order=1)
    _link(db, agent_id, f"{BASE}_sorento", s_t1, 1)
    _link(db, agent_id, f"{BASE}_sorento", s_t2, 2)
    _link(db, agent_id, f"{BASE}_mocha", m_t1, 1)
    _link(db, agent_id, f"{BASE}_mocha", m_t2, 2)
    db.flush()

    _run_upgrade(db)

    tier2 = [r for r in _promotion_rows(db, agent_id) if r["tier"] == 2]
    assert len(tier2) == 1
    assert str(tier2[0]["team_id"]) == s_t2
    roster = _roster(db, s_t2)
    assert roster[boss]["brands"] == []
    assert roster[mocha_boss]["brands"] == ["mocha"]


def test_a_shared_tier2_team_just_loses_the_duplicate_rows(db, todays_config):
    """Today's data: all three sets point at the SAME tier-2 team, so there is
    nobody to move and nobody to tag."""
    teams = todays_config["teams"]
    people = todays_config["people"]

    _run_upgrade(db)

    assert _roster(db, teams["shared_t2"]) == {
        people["Boss"]: {"sort_order": 1, "include_in_round_robin": True, "brands": []}
    }


def test_an_existing_base_row_is_the_one_that_survives(db):
    """A base ``marketing_promotion`` row already at that tier wins the tier."""
    agent_id = _agent(db)
    base_t2 = _team(db, "Base T2")
    s_t1, s_t2 = _team(db, "S1"), _team(db, "S2")
    _person(db, base_t2, "Base Boss", sort_order=1)
    _person(db, s_t1, "Am", sort_order=1)
    sorento_boss = _person(db, s_t2, "Sorento Boss", sort_order=1)
    _link(db, agent_id, BASE, base_t2, 2)
    _link(db, agent_id, f"{BASE}_sorento", s_t1, 1)
    _link(db, agent_id, f"{BASE}_sorento", s_t2, 2)
    db.flush()

    _run_upgrade(db)

    tier2 = [r for r in _promotion_rows(db, agent_id) if r["tier"] == 2]
    assert len(tier2) == 1
    assert str(tier2[0]["team_id"]) == base_t2
    assert _roster(db, base_t2)[sorento_boss]["brands"] == ["sorento"]


def test_no_sorento_tier1_promotes_the_next_brand_and_warns(db, caplog):
    """No ``_sorento`` tier 1: the surviving team comes off the next brand in
    priority order, and its people keep serving everything (they are the fallback)."""
    agent_id = _agent(db)
    m_t1, c_t1 = _team(db, "M1"), _team(db, "C1")
    kia_yee = _person(db, m_t1, "Kia Yee", sort_order=1)
    aqi = _person(db, c_t1, "Aqi", sort_order=1)
    _link(db, agent_id, f"{BASE}_cabana", c_t1, 1)
    _link(db, agent_id, f"{BASE}_mocha", m_t1, 1)
    db.flush()

    with caplog.at_level(logging.WARNING, logger="alembic.runtime.migration"):
        _run_upgrade(db)

    tier1 = [r for r in _promotion_rows(db, agent_id) if r["tier"] == 1]
    # mocha beats cabana: BRAND_PRIORITY, not insertion order.
    assert len(tier1) == 1 and str(tier1[0]["team_id"]) == m_t1
    roster = _roster(db, m_t1)
    assert roster[kia_yee]["brands"] == ["mocha"]
    assert roster[aqi]["brands"] == ["cabana"]
    assert any("mocha" in r.getMessage() for r in caplog.records), [
        r.getMessage() for r in caplog.records
    ]


def test_the_surviving_teams_own_people_are_tagged_with_its_brand(db):
    """The winner team's members are tagged too - Kia Yee handles mocha whether or
    not her team happened to be the one that survived. Only the ``_sorento`` /
    fallback-default team stays untagged."""
    agent_id = _agent(db)
    s_t1, m_t1 = _team(db, "S1"), _team(db, "M1")
    am = _person(db, s_t1, "Am", sort_order=1)
    kia_yee = _person(db, m_t1, "Kia Yee", sort_order=1)
    _link(db, agent_id, f"{BASE}_sorento", s_t1, 1)
    _link(db, agent_id, f"{BASE}_mocha", m_t1, 1)
    db.flush()

    _run_upgrade(db)

    roster = _roster(db, s_t1)
    assert roster[am]["brands"] == []
    assert roster[kia_yee]["brands"] == ["mocha"]


# ------------------------------------------------ AC2-M2, the brand-code check


def test_a_brand_code_with_no_brands_row_warns(db, todays_config, caplog):
    """A collapse that tags a brand nobody defined tags a code that resolves to
    nothing - loud in the migration log, since the data is only checkable here."""
    with caplog.at_level(logging.WARNING, logger="alembic.runtime.migration"):
        _run_upgrade(db)

    messages = [r.getMessage() for r in caplog.records]
    for brand in ("mocha", "cabana"):
        assert any(brand in m and "brands" in m for m in messages), messages


def test_known_brand_codes_do_not_warn(db, todays_config, caplog):
    """Today's production data: SORENTO / MOCHA / CABANA all exist, case aside."""
    for code in ("SORENTO", "MOCHA", "CABANA"):
        _brand(db, code)
    db.flush()

    with caplog.at_level(logging.WARNING, logger="alembic.runtime.migration"):
        _run_upgrade(db)

    assert [r.getMessage() for r in caplog.records if "brands table" in r.getMessage()] == []


# ------------------------------------------------------- the tracker rewrite


def test_open_trackers_are_rewritten_to_base_plus_brand(db, todays_config):
    """An open tracker escalates correctly after the upgrade."""
    policy = todays_config["policy"]
    mocha_tracker = _tracker(db, f"{BASE}_mocha", policy)
    cabana_tracker = _tracker(db, f"{BASE}_cabana", policy)
    other_tracker = _tracker(db, "marketing_product", policy)
    db.flush()

    _run_upgrade(db)

    def _read(tracker_id):
        row = db.execute(
            text(
                "SELECT team_set_code, brand_code FROM conversation_sla_tracking "
                "WHERE id = :i"
            ),
            {"i": tracker_id},
        ).first()
        return row[0], row[1]

    assert _read(mocha_tracker) == (BASE, "mocha")
    assert _read(cabana_tracker) == (BASE, "cabana")
    assert _read(other_tracker) == ("marketing_product", None)


# ------------------------------------------------------ re-runnable, downgrade


def test_a_legacy_code_stored_in_another_case_is_still_collapsed(db):
    """``code`` is free text an admin typed; the collapse must not miss a capital.

    A row left behind under ``Marketing_Promotion_Mocha`` would keep routing to a set
    the resolver no longer knows about, silently.
    """
    agent_id = _agent(db)
    sorento_t1, mocha_t1 = _team(db, "S1"), _team(db, "M1")
    _person(db, sorento_t1, "Am", sort_order=1)
    kia_yee = _person(db, mocha_t1, "Kia Yee", sort_order=1)
    _link(db, agent_id, f"{BASE}_sorento", sorento_t1, 1)
    _link(db, agent_id, "Marketing_Promotion_MOCHA", mocha_t1, 1)
    db.flush()

    _run_upgrade(db)

    rows = _promotion_rows(db, agent_id)
    assert [r["code"] for r in rows] == [BASE]
    assert str(rows[0]["team_id"]) == sorento_t1
    assert _roster(db, sorento_t1)[kia_yee]["brands"] == ["mocha"]


def test_a_tracker_carrying_a_legacy_code_in_another_case_is_rewritten(db, todays_config):
    tracker = _tracker(db, "Marketing_Promotion_Cabana", todays_config["policy"])
    db.flush()

    _run_upgrade(db)

    assert db.execute(
        text(
            "SELECT team_set_code, brand_code FROM conversation_sla_tracking "
            "WHERE id = :i"
        ),
        {"i": tracker},
    ).first() == (BASE, "cabana")


def test_revision_id_fits_alembic_version_num(db):
    """``alembic_version.version_num`` is varchar(32)."""
    module = _load_migration()
    assert len(module.revision) <= 32


def test_migration_is_rerunnable(db, todays_config):
    """A second upgrade is a no-op, not a second collapse."""
    _run_upgrade(db)
    rows = _promotion_rows(db, todays_config["agent_id"])
    roster = _roster(db, todays_config["teams"]["sorento_t1"])

    _run_upgrade(db)

    assert _promotion_rows(db, todays_config["agent_id"]) == rows
    assert _roster(db, todays_config["teams"]["sorento_t1"]) == roster


def test_downgrade_names_how_many_tags_it_drops(db, todays_config, caplog):
    """The tags are the only record of who serves which brand - say what is lost."""
    _run_upgrade(db)

    with caplog.at_level(logging.WARNING, logger="alembic.runtime.migration"):
        _run_downgrade(db)

    # Kia Yee (mocha) and Aqi (cabana) were tagged by the collapse.
    assert any(
        "2" in r.getMessage() and "tag" in r.getMessage() for r in caplog.records
    ), [r.getMessage() for r in caplog.records]


def test_downgrade_drops_the_table_and_the_tracker_column(db, todays_config):
    """The schema half is reversible; the collapse and the membership moves are not
    (documented in the migration's docstring)."""
    _run_upgrade(db)

    _run_downgrade(db)

    assert db.execute(
        text(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name = 'team_member_brands'"
        )
    ).scalar() == 0
    assert db.execute(
        text(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = 'conversation_sla_tracking' AND column_name = 'brand_code'"
        )
    ).scalar() == 0
    # The people stay where the upgrade moved them - that half is one-way. Read
    # without the join table, which downgrade has just dropped.
    survivors = {
        str(r[0])
        for r in db.execute(
            text("SELECT user_id FROM team_members WHERE team_id = :t"),
            {"t": todays_config["teams"]["sorento_t1"]},
        )
    }
    assert survivors == {
        todays_config["people"][name] for name in ("Am", "Kia Yee", "Aqi")
    }
