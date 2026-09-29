"""The seeded `scm_reorder_run` description names the scope the config page now sets (#1340).

Run over real rows: the update touches only the row still carrying the seeded wording, so a
description an admin already rewrote on the page survives the deploy.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from tests._pg_fixture import blank_session

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "scm_reorder_run_scope_desc.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("m_scm_scope_desc", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, direction: str = "upgrade"):
    module = _load_migration()
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        getattr(module, direction)()


@pytest.fixture
def db():
    with blank_session() as session:
        session.execute(text("DELETE FROM scheduled_tasks WHERE key = 'scm_reorder_run'"))
        yield session


def _seed(db, description: str) -> None:
    db.execute(
        text(
            "INSERT INTO scheduled_tasks (id, key, name, description, enabled, interval_unit, "
            "interval_value, timezone) VALUES (gen_random_uuid(), 'scm_reorder_run', "
            "'SCM Daily Reorder Run', :d, true, 'days', 1, 'Asia/Kuala_Lumpur')"
        ),
        {"d": description},
    )


def _description(db) -> str:
    return db.execute(
        text("SELECT description FROM scheduled_tasks WHERE key = 'scm_reorder_run'")
    ).scalar_one()


def test_revision_id_fits_alembic_version():
    assert len(_load_migration().revision) <= 32


def test_seeded_wording_is_replaced_and_restored(db):
    module = _load_migration()
    _seed(db, module.OLD_DESCRIPTION)

    _run(db)
    new = _description(db)
    assert new == module.NEW_DESCRIPTION
    for word in ("warehouses", "Project", "Dealer", "days from the run day", "products",
                 "budget", "market insight"):
        assert word in new, word

    _run(db, "downgrade")
    assert _description(db) == module.OLD_DESCRIPTION


def test_an_edited_description_is_left_alone(db):
    _seed(db, "Our own wording")
    _run(db)
    assert _description(db) == "Our own wording"


def test_no_row_is_a_no_op(db):
    _run(db)
    assert db.execute(
        text("SELECT count(*) FROM scheduled_tasks WHERE key = 'scm_reorder_run'")
    ).scalar_one() == 0


def test_old_description_is_exactly_what_284_seeded():
    """The guard only matches the seeded row if OLD_DESCRIPTION is 284's text to the byte;
    read it out of 284's SQL (adjacent literals concatenate) rather than trust a copy."""
    import re

    seed = (MIGRATION.parent / "284_seed_scm_reorder_run_task.py").read_text()
    block = seed.split("'SCM Daily Reorder Run',")[1].split("true,")[0]
    assert "".join(re.findall(r"'([^']*)'", block)) == _load_migration().OLD_DESCRIPTION
