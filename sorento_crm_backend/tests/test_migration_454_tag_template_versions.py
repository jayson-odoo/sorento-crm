"""AC-S5-4/AC-S5-7 - existing templates become v1 published, with no gap where
the request designer's published-only list would suddenly see nothing.

Driven through `upgrade()`/`downgrade()` against the real database inside a
rolled-back transaction, exactly as `test_migration_450_spec_rules_backfill.py`
does and for the same reason: the backfill is raw SQL against
`dealer_kit.tag_template`, which does not resolve through `blank_session`'s
schema-translate map, so a scratch copy would prove nothing about the live
9-template dataset this migration actually has to carry.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import inspect, text

from tests._pg_fixture import pg_session, unique_code

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "454_tag_template_versions.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("zzt_migration_454", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, direction: str = "upgrade") -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    module = _migration_module()
    context = MigrationContext.configure(connection=db.connection())
    with Operations.context(context):
        getattr(module, direction)()


def _has_column(db) -> bool:
    return "published_version_id" in {
        column["name"] for column in inspect(db.get_bind()).get_columns(
            "tag_template", schema="dealer_kit"
        )
    }


def _has_table(db) -> bool:
    return inspect(db.get_bind()).has_table("tag_template_version", schema="dealer_kit")


@pytest.fixture
def db():
    with pg_session() as session:
        if _has_column(session):
            _run(session, "downgrade")
        yield session


def _make_template(db, name: str) -> str:
    template_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO dealer_kit.tag_template (id, name, family, doc, print_size)"
            " VALUES (:id, :name, 'toilet', CAST(:doc AS jsonb), CAST(:ps AS jsonb))"
        ),
        {
            "id": template_id,
            "name": name,
            "doc": '{"layers": [], "width_mm": 85, "height_mm": 58}',
            "ps": '{"width_mm": 85, "height_mm": 58}',
        },
    )
    return template_id


def test_the_table_and_column_do_not_exist_before_upgrade(db):
    assert not _has_table(db)
    assert not _has_column(db)


def test_every_existing_template_becomes_v1_published(db):
    a = _make_template(db, unique_code("ZZT Tmpl A"))
    b = _make_template(db, unique_code("ZZT Tmpl B"))

    _run(db)

    rows = db.execute(
        text(
            "SELECT t.id, t.published_version_id, v.version_no, v.doc"
            " FROM dealer_kit.tag_template t"
            " JOIN dealer_kit.tag_template_version v ON v.id = t.published_version_id"
            " WHERE t.id IN (:a, :b)"
        ),
        {"a": a, "b": b},
    ).mappings().all()

    assert len(rows) == 2
    for row in rows:
        assert row["version_no"] == 1
        assert row["doc"]["width_mm"] == 85


def test_a_template_created_after_upgrade_is_unaffected(db):
    _run(db)
    fresh = _make_template(db, unique_code("ZZT Tmpl Fresh"))

    published_version_id = db.execute(
        text("SELECT published_version_id FROM dealer_kit.tag_template WHERE id = :id"),
        {"id": fresh},
    ).scalar()

    assert published_version_id is None


def test_the_downgrade_removes_the_table_and_column(db):
    _run(db)
    _run(db, "downgrade")

    assert not _has_table(db)
    assert not _has_column(db)
