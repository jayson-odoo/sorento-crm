"""ptag_0005_price_mode_remarks (D5/D6, AC-S2-6): a header `price_mode`
column on `price_tag_requests` and a line-level `remarks` column on
`price_tag_request_lines`.

Driven through `upgrade()`/`downgrade()` against the real database inside a
rolled-back transaction, exactly as `test_migration_457_ptag_line_xco_repair
.py` and `test_migration_454_tag_template_versions.py` do and for the same
reason: this is additive DDL against real `price_tag_requests` /
`price_tag_request_lines` tables, and the shared local Postgres this repo
uses for tests converges through `Base.metadata.create_all`, never
`alembic upgrade` (see `sorento_crm_backend/CLAUDE.md`) - so the only way to
prove the migration itself is correct is to run it, not to inspect a schema
someone else already brought up to date.

RED note for the coder: this file imports
`alembic/versions/ptag_0005_price_mode_remarks.py` by path, which does not
exist yet - every test here fails on that import until the migration is
written with `revision = "ptag_0005"`, `down_revision` chained onto
whatever is `alembic heads` at merge time (measured on this branch: it was
`492_mcp_tool_chatbot_domain`, re-check before landing).
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import inspect, text

from app.models.access import RespondContact
from tests._pg_fixture import pg_session, unique_code

_SORENTO_COMPANY_ID = "00000000-0000-0000-0000-000000000001"

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "ptag_0005_price_mode_remarks.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location(
        "zzt_migration_ptag_0005", _MIGRATION_PATH
    )
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


@pytest.fixture
def db():
    with pg_session() as session:
        yield session


def _has_price_mode(db) -> bool:
    return "price_mode" in {
        column["name"]
        for column in inspect(db.get_bind()).get_columns("price_tag_requests")
    }


def _has_remarks(db) -> bool:
    return "remarks" in {
        column["name"]
        for column in inspect(db.get_bind()).get_columns("price_tag_request_lines")
    }


def _seed_request_via_raw_sql(db) -> str:
    """A minimal `price_tag_requests` row, inserted with raw SQL rather than
    the ORM: the ORM model may already declare `price_mode`/`remarks` (the
    coder adds both in the same slice) even on a connection where the DDL
    below has not run yet, and an ORM insert would then reference a column
    that does not exist on THIS transaction's view of the table.
    """
    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+60{uuid.uuid4().hex[:9]}",
        name=unique_code("ZZT contact"),
    )
    db.add(contact)
    db.flush()

    request_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO price_tag_requests "
            "(id, contact_id, company_id, doc_number, status) "
            "VALUES (:id, :contact_id, :company_id, :doc_number, 'new')"
        ),
        {
            "id": request_id,
            "contact_id": contact.id,
            "company_id": _SORENTO_COMPANY_ID,
            "doc_number": unique_code("PT"),
        },
    )
    return request_id


class TestUpgradeAddsBothColumns:
    def test_columns_absent_before_upgrade(self, db):
        assert not _has_price_mode(db)
        assert not _has_remarks(db)

    def test_upgrade_adds_price_mode_not_null_default_list(self, db):
        _run(db)

        assert _has_price_mode(db)
        columns = {
            c["name"]: c
            for c in inspect(db.get_bind()).get_columns("price_tag_requests")
        }
        assert columns["price_mode"]["nullable"] is False

    def test_upgrade_adds_remarks_nullable_text(self, db):
        _run(db)

        assert _has_remarks(db)
        columns = {
            c["name"]: c
            for c in inspect(db.get_bind()).get_columns("price_tag_request_lines")
        }
        assert columns["remarks"]["nullable"] is True

    def test_a_row_inserted_before_the_migration_backfills_to_list(self, db):
        """AC-S2-6: existing rows get `price_mode='list'` - proven by
        inserting the row BEFORE `upgrade()` runs, so the value on it after
        the migration can only have come from the backfill/default, never
        from an insert that named it."""
        request_id = _seed_request_via_raw_sql(db)

        _run(db)

        price_mode = db.execute(
            text("SELECT price_mode FROM price_tag_requests WHERE id = :id"),
            {"id": request_id},
        ).scalar()
        assert price_mode == "list"

    def test_a_row_inserted_after_the_migration_defaults_to_list_with_no_value_given(
        self, db
    ):
        _run(db)

        request_id = str(uuid.uuid4())
        contact = RespondContact(
            id=str(uuid.uuid4()),
            phone_number=f"+60{uuid.uuid4().hex[:9]}",
            name=unique_code("ZZT contact"),
        )
        db.add(contact)
        db.flush()
        db.execute(
            text(
                "INSERT INTO price_tag_requests "
                "(id, contact_id, company_id, doc_number, status) "
                "VALUES (:id, :contact_id, :company_id, :doc_number, 'new')"
            ),
            {
                "id": request_id,
                "contact_id": contact.id,
                "company_id": _SORENTO_COMPANY_ID,
                "doc_number": unique_code("PT"),
            },
        )

        price_mode = db.execute(
            text("SELECT price_mode FROM price_tag_requests WHERE id = :id"),
            {"id": request_id},
        ).scalar()
        assert price_mode == "list"

    def test_remarks_is_null_on_an_existing_line_after_upgrade(self, db):
        request_id = _seed_request_via_raw_sql(db)
        line_id = str(uuid.uuid4())
        # Seeded BEFORE upgrade, so the column literally cannot exist yet -
        # confirms upgrade() does not choke on rows it has to retrofit.
        db.execute(
            text(
                "INSERT INTO price_tag_request_lines "
                "(id, request_id, line_type, product_id, quantity) "
                "VALUES (:id, :request_id, 'product', NULL, 1)"
            ),
            {"id": line_id, "request_id": request_id},
        )

        _run(db)

        remarks = db.execute(
            text("SELECT remarks FROM price_tag_request_lines WHERE id = :id"),
            {"id": line_id},
        ).scalar()
        assert remarks is None


class TestDowngradeRemovesBothColumns:
    def test_downgrade_after_upgrade_removes_both_columns(self, db):
        _run(db)
        _run(db, "downgrade")

        assert not _has_price_mode(db)
        assert not _has_remarks(db)
