"""AC-A8 - migration 323 tested by running it, not by asserting on the live database.

CI's database has no data, so "does every Container Status row already carry a
company_id" there proves nothing - there are no rows. This builds the
pre-migration state on a scratch schema (a blank schema already carries every
table via ``create_all``; this migration is data-only, no DDL) and runs
``upgrade()`` against it, exactly like the ``test_migration_320_*`` precedent.
"""
from __future__ import annotations

import importlib.util
import uuid
from datetime import datetime
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from app.services.container_status_document import ensure_attachment_type
from tests._pg_fixture import blank_session, unique_code

SORENTO_ID = "00000000-0000-0000-0000-000000000001"
MOCHA_ID = "00000000-0000-0000-0000-000000000002"

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "323_container_status_company_backfill.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("m323", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_upgrade(db):
    module = _load_migration()
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        module.upgrade()


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _mocha(db) -> None:
    db.execute(
        text("INSERT INTO companies (id, name, code, is_active) VALUES (:i, 'ZZT Mocha', :c, true)"),
        {"i": MOCHA_ID, "c": unique_code("MCH")[:20]},
    )
    db.flush()


def _workbook(
    db,
    *,
    company_id: str | None,
    is_deleted: bool = False,
    uploaded_at: datetime | None = None,
) -> str:
    type_id = ensure_attachment_type(db)
    att_id = str(uuid.uuid4())
    db.execute(
        text(
            """
            INSERT INTO attachments (
                id, attachment_type_id, original_filename, stored_filename,
                file_path, mime_type, uploaded_at, is_deleted, deleted_at, company_id
            ) VALUES (:id, :t, :n, :n, :k, :m, :u, :del, :del_at, :c)
            """
        ),
        {
            "id": att_id,
            "t": type_id,
            "n": "Container Status 2026.xlsx",
            "k": f"import-sources/{unique_code('key')}/Container Status 2026.xlsx",
            "m": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "u": uploaded_at or datetime(2026, 8, 7, 10, 0, 0),
            "del": is_deleted,
            "del_at": datetime(2026, 8, 8, 0, 0, 0) if is_deleted else None,
            "c": company_id,
        },
    )
    db.flush()
    return att_id


def _company_id_of(db, att_id: str):
    return db.execute(
        text("SELECT company_id FROM attachments WHERE id = :id"), {"id": att_id}
    ).scalar()


def _is_deleted_of(db, att_id: str):
    return db.execute(
        text("SELECT is_deleted FROM attachments WHERE id = :id"), {"id": att_id}
    ).scalar()


def test_null_live_and_null_trashed_rows_are_both_stamped_to_the_incumbent(db):
    """AC-A8 - live or already-trashed, a NULL-company row is attributed to
    Sorento, and `is_deleted` is untouched on either."""
    live_null = _workbook(db, company_id=None, is_deleted=False)
    trashed_null = _workbook(db, company_id=None, is_deleted=True)

    _run_upgrade(db)

    assert str(_company_id_of(db, live_null)) == SORENTO_ID
    assert str(_company_id_of(db, trashed_null)) == SORENTO_ID
    assert _is_deleted_of(db, live_null) is False
    assert _is_deleted_of(db, trashed_null) is True


def test_a_row_already_attributed_to_another_company_is_left_alone(db):
    """A real Mocha workbook must not be re-pointed at Sorento - the mismatch
    this migration corrects is "unattributed", not "attributed elsewhere"."""
    _mocha(db)
    mocha_owned = _workbook(db, company_id=MOCHA_ID)
    null_row = _workbook(db, company_id=None)

    _run_upgrade(db)

    assert str(_company_id_of(db, mocha_owned)) == MOCHA_ID
    assert str(_company_id_of(db, null_row)) == SORENTO_ID


def test_running_it_twice_changes_nothing(db):
    """Idempotent: a second run finds nothing left to stamp."""
    _mocha(db)
    null_row = _workbook(db, company_id=None)
    mocha_owned = _workbook(db, company_id=MOCHA_ID)

    _run_upgrade(db)
    first_pass_null = _company_id_of(db, null_row)
    first_pass_mocha = _company_id_of(db, mocha_owned)

    _run_upgrade(db)

    assert _company_id_of(db, null_row) == first_pass_null
    assert _company_id_of(db, mocha_owned) == first_pass_mocha
    assert str(_company_id_of(db, null_row)) == SORENTO_ID
    assert str(_company_id_of(db, mocha_owned)) == MOCHA_ID


def test_other_attachment_types_are_never_touched(db):
    """The JOIN is against attachment_types by code/name - a NULL-company row
    of some OTHER type must stay NULL."""
    from app.models.resources import Attachment, AttachmentType

    other_type = AttachmentType(
        id=str(uuid.uuid4()), type_name=unique_code("Packing List"), allowed_extensions="pdf",
    )
    db.add(other_type)
    db.flush()
    bystander = Attachment(
        id=str(uuid.uuid4()), original_filename="pl.pdf", stored_filename="pl.pdf",
        file_path="x/pl.pdf", attachment_type_id=str(other_type.id), is_deleted=False,
        company_id=None,
    )
    db.add(bystander)
    db.flush()

    _run_upgrade(db)

    db.refresh(bystander)
    assert bystander.company_id is None
