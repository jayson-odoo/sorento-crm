"""S2 - migration 320 tested by running it, not by asserting on the live database.

The live database is a copy of production and is already past this revision's
lineage, so "does the column exist" there proves nothing. This builds the
pre-migration schema on a scratch schema, runs ``upgrade()`` against it, and
asserts the constraints actually behave: the anti-drift composite FK rejects a
mismatched link, and the reworked unique keys ACCEPT the row shape this feature
exists to allow.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests._pg_fixture import blank_session


SORENTO = "00000000-0000-0000-0000-000000000001"
MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "320_company_aware_routing.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("m320", MIGRATION)
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


def _mocha(db) -> str:
    cid = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO companies (id, name, code, is_active) "
            "VALUES (:i, 'ZZT Mocha', :c, true)"
        ),
        {"i": cid, "c": f"ZZT{uuid.uuid4().hex[:6]}"},
    )
    return cid


def _team(db, name: str = "ZZT Team") -> str:
    tid = str(uuid.uuid4())
    db.execute(
        text("INSERT INTO teams (id, name) VALUES (:i, :n)"), {"i": tid, "n": name}
    )
    return tid


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


def _policy(db, code: str | None = None) -> str:
    pid = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO sla_policies (id, code, name, is_active) "
            "VALUES (:i, :c, 'ZZT Policy', true)"
        ),
        {"i": pid, "c": code or f"ZZT-pol-{uuid.uuid4().hex[:8]}"},
    )
    return pid


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


# ------------------------------------------------------------------- backfill


def test_existing_rows_backfill_to_sorento(db):
    """AC-I1 - nothing about Sorento routing changes on deploy."""
    team_id = _team(db)
    agent_id = _agent(db)
    db.execute(
        text(
            "INSERT INTO agent_teams (id, agent_id, code, team_id, tier) "
            "VALUES (:i, :a, 'zzt_code', :t, 1)"
        ),
        {"i": str(uuid.uuid4()), "a": agent_id, "t": team_id},
    )

    _run_upgrade(db)

    assert str(
        db.execute(text("SELECT company_id FROM teams WHERE id = :i"), {"i": team_id}).scalar()
    ) == SORENTO
    assert str(
        db.execute(
            text("SELECT company_id FROM agent_teams WHERE team_id = :i"), {"i": team_id}
        ).scalar()
    ) == SORENTO


def test_company_id_is_not_null_everywhere(db):
    _run_upgrade(db)

    rows = db.execute(
        text(
            """
            SELECT table_name, is_nullable FROM information_schema.columns
            WHERE column_name = 'company_id' AND table_schema = current_schema()
              AND table_name IN ('teams','agent_teams','sla_policies',
                                 'conversation_sla_tracking')
            ORDER BY table_name
            """
        )
    ).all()

    assert {r[0] for r in rows} == {
        "agent_teams",
        "conversation_sla_tracking",
        "sla_policies",
        "teams",
    }
    assert all(r[1] == "NO" for r in rows), rows


def test_old_code_inserting_without_a_company_still_works(db):
    """The blue/green deploy window: old containers omit the column entirely.

    A bare NOT NULL would turn every insert from a not-yet-rolled container into an
    error for the length of the deploy, so the column carries a Sorento default.
    """
    _run_upgrade(db)

    team_id = str(uuid.uuid4())
    db.execute(
        text("INSERT INTO teams (id, name) VALUES (:i, 'ZZT Legacy Insert')"),
        {"i": team_id},
    )

    assert str(
        db.execute(text("SELECT company_id FROM teams WHERE id = :i"), {"i": team_id}).scalar()
    ) == SORENTO


# --------------------------------------------------------------- anti-drift


def test_link_cannot_claim_a_company_its_team_does_not_belong_to(db):
    """AC-C2 - the composite FK, i.e. the reason the denormalised column is safe."""
    team_id = _team(db)
    agent_id = _agent(db)
    _run_upgrade(db)
    mocha = _mocha(db)

    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO agent_teams (id, agent_id, code, team_id, tier, company_id) "
                "VALUES (:i, :a, 'zzt_bad', :t, 1, :c)"
            ),
            {"i": str(uuid.uuid4()), "a": agent_id, "t": team_id, "c": mocha},
        )
    db.rollback()


def test_link_cannot_point_at_another_companys_policy(db):
    """AC-C8 - same trick applied to policy_id."""
    team_id = _team(db)
    agent_id = _agent(db)
    policy_id = _policy(db)
    _run_upgrade(db)
    mocha = _mocha(db)
    # Move the policy to Mocha, leaving the (Sorento) team where it is.
    db.execute(
        text("UPDATE sla_policies SET company_id = :c WHERE id = :i"),
        {"c": mocha, "i": policy_id},
    )

    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO agent_teams (id, agent_id, code, team_id, tier, "
                "company_id, policy_id) VALUES (:i, :a, 'zzt_p', :t, 1, :c, :p)"
            ),
            {
                "i": str(uuid.uuid4()),
                "a": agent_id,
                "t": team_id,
                "c": SORENTO,
                "p": policy_id,
            },
        )
    db.rollback()


def test_null_policy_still_allowed(db):
    """MATCH SIMPLE: a NULL policy_id satisfies the composite FK."""
    team_id = _team(db)
    agent_id = _agent(db)
    _run_upgrade(db)

    db.execute(
        text(
            "INSERT INTO agent_teams (id, agent_id, code, team_id, tier, company_id) "
            "VALUES (:i, :a, 'zzt_nopolicy', :t, 1, :c)"
        ),
        {"i": str(uuid.uuid4()), "a": agent_id, "t": team_id, "c": SORENTO},
    )
    assert db.execute(
        text("SELECT count(*) FROM agent_teams WHERE code = 'zzt_nopolicy'")
    ).scalar() == 1


# ------------------------------------------------------------- uniqueness


def test_same_code_and_tier_in_two_companies_is_allowed(db):
    """AC-C3 - the whole point. The old key rejected exactly this."""
    sorento_team = _team(db, "ZZT Sorento Marketing")
    agent_id = _agent(db)
    _run_upgrade(db)
    mocha = _mocha(db)
    mocha_team = str(uuid.uuid4())
    db.execute(
        text("INSERT INTO teams (id, name, company_id) VALUES (:i, :n, :c)"),
        {"i": mocha_team, "n": "ZZT Mocha Marketing", "c": mocha},
    )

    for team_id, company_id in ((sorento_team, SORENTO), (mocha_team, mocha)):
        db.execute(
            text(
                "INSERT INTO agent_teams (id, agent_id, code, team_id, tier, company_id) "
                "VALUES (:i, :a, 'zzt_marketing', :t, 1, :c)"
            ),
            {"i": str(uuid.uuid4()), "a": agent_id, "t": team_id, "c": company_id},
        )

    assert db.execute(
        text("SELECT count(*) FROM agent_teams WHERE code = 'zzt_marketing'")
    ).scalar() == 2


def test_same_code_tier_and_company_is_still_rejected(db):
    """AC-H3 - loosening the key must not lose the duplicate guard."""
    team_id = _team(db)
    agent_id = _agent(db)
    _run_upgrade(db)

    for _ in range(1):
        db.execute(
            text(
                "INSERT INTO agent_teams (id, agent_id, code, team_id, tier, company_id) "
                "VALUES (:i, :a, 'zzt_dup', :t, 2, :c)"
            ),
            {"i": str(uuid.uuid4()), "a": agent_id, "t": team_id, "c": SORENTO},
        )

    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO agent_teams (id, agent_id, code, team_id, tier, company_id) "
                "VALUES (:i, :a, 'zzt_dup', :t, 2, :c)"
            ),
            {"i": str(uuid.uuid4()), "a": agent_id, "t": team_id, "c": SORENTO},
        )
    db.rollback()


def test_policy_code_is_unique_per_company_not_globally(db):
    """D5 - each company owns its policies; the global key is gone."""
    _run_upgrade(db)
    mocha = _mocha(db)
    shared_code = f"ZZT-shared-{uuid.uuid4().hex[:6]}"

    for company_id in (SORENTO, mocha):
        db.execute(
            text(
                "INSERT INTO sla_policies (id, code, name, is_active, company_id) "
                "VALUES (:i, :c, 'ZZT Policy', true, :co)"
            ),
            {"i": str(uuid.uuid4()), "c": shared_code, "co": company_id},
        )

    assert db.execute(
        text("SELECT count(*) FROM sla_policies WHERE code = :c"), {"c": shared_code}
    ).scalar() == 2

    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO sla_policies (id, code, name, is_active, company_id) "
                "VALUES (:i, :c, 'ZZT Dup', true, :co)"
            ),
            {"i": str(uuid.uuid4()), "c": shared_code, "co": SORENTO},
        )
    db.rollback()


# --------------------------------------------------------------- safety net


def test_cross_company_team_parent_aborts_the_migration(db):
    """AC-C7 - a parent team's members act on every descendant, so this must not pass."""
    parent = _team(db, "ZZT Parent")
    child = str(uuid.uuid4())
    db.execute(
        text("INSERT INTO teams (id, name, parent_team_id) VALUES (:i, 'ZZT Child', :p)"),
        {"i": child, "p": parent},
    )
    # Put the column in place, then force the illegal state the check exists for.
    _run_upgrade(db)
    mocha = _mocha(db)
    db.execute(
        text("UPDATE teams SET company_id = :c WHERE id = :i"), {"c": mocha, "i": child}
    )

    with pytest.raises(RuntimeError, match="parent in another company"):
        _run_upgrade(db)
    db.rollback()


def test_migration_is_rerunnable(db):
    """The shared dev database gets this DDL applied by hand, so it runs twice."""
    _team(db)
    _run_upgrade(db)
    _run_upgrade(db)

    assert db.execute(
        text(
            "SELECT count(*) FROM pg_indexes WHERE schemaname = current_schema() "
            "AND indexname = 'uq_agent_teams_agent_code_company_tier'"
        )
    ).scalar() == 1


# ---------------------------------------------------------------- downgrade


def test_downgrade_restores_the_prior_shape(db):
    """AC-I4."""
    _team(db)
    _run_upgrade(db)
    _run_downgrade(db)

    cols = db.execute(
        text(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE column_name = 'company_id' AND table_schema = current_schema() "
            "AND table_name IN ('teams','agent_teams','sla_policies',"
            "'conversation_sla_tracking')"
        )
    ).scalar()
    assert cols == 0

    names = {
        r[0]
        for r in db.execute(
            text(
                "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema() "
                "AND tablename = 'agent_teams'"
            )
        )
    }
    assert "uq_agent_teams_agent_code_tier_null" in names
    assert "uq_agent_teams_agent_code_tier_not_null" in names
    assert "uq_agent_teams_agent_code_company_tier" not in names

    # Scoped to this scratch schema: the live public schema has its own copy of
    # every one of these names, so an unqualified pg_constraint count is always 2.
    assert db.execute(
        text(
            """
            SELECT count(*) FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            JOIN pg_namespace ns ON ns.oid = rel.relnamespace
            WHERE con.conname = 'sla_policies_code_key'
              AND ns.nspname = current_schema()
            """
        )
    ).scalar() == 1
