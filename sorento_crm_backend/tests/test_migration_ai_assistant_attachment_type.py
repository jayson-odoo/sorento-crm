"""AGENT-PANEL-COMPOSER Phase 2 (red): the migration that seeds the `ai_assistant_attachment` type.

UAC contract section: allowed_extensions png,jpg,jpeg,webp,xlsx,xls,csv,pdf; max_file_size_mb 10;
max_count_per_entity 5; seeded idempotently. The migration's own `upgrade()` runs here against a blank
schema inside a rolled-back transaction (the pattern of test_migration_311_pr_approve_grants.py).
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from ._pg_fixture import blank_session

CODE = "ai_assistant_attachment"
VERSIONS = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _migration_path() -> pathlib.Path:
    files = [p for p in VERSIONS.glob("*.py") if f'"{CODE}"' in p.read_text() or f"'{CODE}'" in p.read_text()]
    assert len(files) == 1, f"expected exactly one migration seeding {CODE}, found {[p.name for p in files]}"
    return files[0]


def _run_upgrade(db) -> None:
    path = _migration_path()
    spec = importlib.util.spec_from_file_location("migration_ai_assistant_attachment", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert len(module.revision) <= 32, "alembic revision ids must be 32 chars or fewer"
    with Operations.context(MigrationContext.configure(db.connection())):
        module.upgrade()


def _rows(db):
    return db.execute(
        text(
            "SELECT allowed_extensions, max_file_size_mb, max_count_per_entity "
            "FROM attachment_types WHERE code = :c"
        ),
        {"c": CODE},
    ).all()


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


def test_the_migration_seeds_the_type_with_the_contract_values(db):
    _run_upgrade(db)

    (row,) = _rows(db)
    assert {e.strip().lstrip(".") for e in row[0].split(",")} == {
        "png", "jpg", "jpeg", "webp", "xlsx", "xls", "csv", "pdf"
    }
    assert row[1] == 10 and row[2] == 5


def test_running_it_twice_seeds_one_row(db):
    _run_upgrade(db)
    _run_upgrade(db)

    assert len(_rows(db)) == 1


def test_a_hand_edited_type_is_not_overwritten_by_a_second_run(db):
    _run_upgrade(db)
    db.execute(text("UPDATE attachment_types SET max_file_size_mb = 25 WHERE code = :c"), {"c": CODE})

    _run_upgrade(db)

    assert _rows(db)[0][1] == 25, "an admin's edit on Attachment Types was reset"


def test_ensure_attachment_type_agrees_with_the_migration_and_is_idempotent(db):
    from app.services.chatbot.panel_files import ATTACHMENT_TYPE_CODE, ensure_attachment_type

    first = ensure_attachment_type(db)
    second = ensure_attachment_type(db)

    assert ATTACHMENT_TYPE_CODE == CODE
    assert str(first.id) == str(second.id)
    assert len(_rows(db)) == 1
    assert first.max_file_size_mb == 10 and first.max_count_per_entity == 5
