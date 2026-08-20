"""Migration ed706a98ddc6 - the agent's ownership-group seed.

PLAN-demo-followups-19aug-ladder-v2.md workstream C3. `upgrade()` is imported by PATH and run
inside `blank_session`'s rolled-back transaction, per the project rule that a migration
touching seed data is tested against the CODE, not whatever the shared local database happens
to hold.

Scoped to `sales_agents.location_group` only. The same migration also adds three columns to
`scm.priority_policy`, but that table is asserted by the migration's OWN guards via a literal
`schema="scm"` / raw `scm.priority_policy` SQL, which - unlike ORM-compiled statements -
`blank_session`'s `schema_translate_map` does NOT rewrite (see `tests/scm/test_priority_fair_
policy.py`'s file docstring for the same gotcha on migration 385). So a `blank_session` test of
that half would silently read/write the REAL shared `scm.priority_policy` table by name rather
than the scratch one. `sales_agents` carries no schema, is unaffected, and is exactly what this
file exercises; the C1 admin-API tests (`tests/scm/test_fulfilment_priority_policy.py`) cover
the `scm.priority_policy` columns against the real, already-migrated stack database instead.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest

from app.models.sales_agent import SalesAgent
from tests._pg_fixture import blank_session, unique_code

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "ed706a98ddc6_fulfilment_policy_settings_and_agent_.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("zzt_migration_ed706a98ddc6", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_upgrade(db) -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    module = _migration_module()
    context = MigrationContext.configure(connection=db.connection())
    with Operations.context(context):
        module.upgrade()


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _seed_agent(db, code: str, **kwargs) -> SalesAgent:
    row = SalesAgent(id=str(uuid.uuid4()), sales_agent=code, source="manual", **kwargs)
    db.add(row)
    db.flush()
    return row


def test_the_nine_bb_names_are_seeded_case_and_whitespace_insensitively(db):
    control = _seed_agent(db, unique_code("NOT-A-BB-NAME"))
    tera = _seed_agent(db, "tera")  # lower-case, still matches TERA
    cindy = _seed_agent(db, "  CINDY LEE  ")  # padded, still matches CINDY LEE
    jay = _seed_agent(db, "Jay")

    _run_upgrade(db)

    db.expire_all()
    assert db.query(SalesAgent).filter(SalesAgent.id == control.id).one().location_group is None
    assert db.query(SalesAgent).filter(SalesAgent.id == tera.id).one().location_group == "BB"
    assert db.query(SalesAgent).filter(SalesAgent.id == cindy.id).one().location_group == "BB"
    assert db.query(SalesAgent).filter(SalesAgent.id == jay.id).one().location_group == "BB"


def test_a_name_outside_the_nine_is_left_alone(db):
    other = _seed_agent(db, unique_code("NOTBB"))

    _run_upgrade(db)

    db.expire_all()
    assert db.query(SalesAgent).filter(SalesAgent.id == other.id).one().location_group is None


def test_an_already_set_group_is_not_overwritten(db):
    """The seed is `WHERE location_group IS NULL` - a captain's own edit must survive a re-run."""
    tera = _seed_agent(db, "tera", location_group="HP")

    _run_upgrade(db)

    db.expire_all()
    assert db.query(SalesAgent).filter(SalesAgent.id == tera.id).one().location_group == "HP"


def test_running_the_seed_twice_is_idempotent(db):
    tera = _seed_agent(db, "tera")

    _run_upgrade(db)
    _run_upgrade(db)

    db.expire_all()
    assert db.query(SalesAgent).filter(SalesAgent.id == tera.id).one().location_group == "BB"
