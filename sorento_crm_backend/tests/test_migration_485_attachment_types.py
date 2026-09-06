"""Migration 485 - Shipment Line Photo, Proforma Invoice and Packing List attachment
types (browser-test round, finding 3; the latter two were added to this same,
unreleased migration - see `PLAN-scm-purchasing-consolidation-6sep.md`'s
`## Deviations (lane C)`).

`pg_session` (real database, rolled back on teardown) - the same substrate
`test_migration_454_tag_template_versions.py` uses - because the whole point under
test is idempotency against the SHARED dev DB's own real "Packing List" row (admin
data that predates this migration), which a scratch `blank_session` schema does not
carry.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text

from tests._pg_fixture import pg_session

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "485_shipment_line_photo_type.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("zzt_migration_485", _MIGRATION_PATH)
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


def _row(db, code: str):
    return db.execute(
        text(
            "SELECT code, type_name, allowed_extensions, max_file_size_mb, "
            "triggers_n8n_webhook FROM attachment_types WHERE code = :code"
        ),
        {"code": code},
    ).mappings().first()


@pytest.fixture
def db():
    with pg_session() as session:
        yield session


def test_upgrade_seeds_all_three_types(db):
    _run(db)

    photo = _row(db, "shipment_line_photo")
    assert photo is not None
    assert photo["type_name"] == "Shipment Line Photo"
    assert photo["allowed_extensions"] == "jpg,jpeg,png,webp,gif"

    proforma = _row(db, "proforma_invoice")
    assert proforma is not None
    assert proforma["type_name"] == "Proforma Invoice"
    assert proforma["allowed_extensions"] == "xlsx,xls,pdf"
    assert proforma["max_file_size_mb"] == 10
    assert proforma["triggers_n8n_webhook"] is False

    packing_list = _row(db, "packing_list")
    assert packing_list is not None
    assert packing_list["type_name"] == "Packing List"


def test_the_existing_packing_list_row_only_gets_its_code_set(db):
    """The shared dev DB already carries a real "Packing List" attachment type (admin
    data, R4's own note) - this migration must not touch its OTHER columns, in
    particular `triggers_n8n_webhook`, which an admin may have turned on. `pg_session`
    is the real database (rolled back on teardown), so the row already there is used
    directly rather than faked with a marker-prefixed duplicate.
    """
    before = db.execute(
        text(
            "SELECT max_file_size_mb, triggers_n8n_webhook FROM attachment_types "
            "WHERE type_name = 'Packing List'"
        )
    ).mappings().first()
    assert before is not None, "the shared dev DB is expected to already carry this row"

    _run(db)

    after = db.execute(
        text(
            "SELECT code, max_file_size_mb, triggers_n8n_webhook FROM attachment_types "
            "WHERE type_name = 'Packing List'"
        )
    ).mappings().one()
    assert after["code"] == "packing_list"
    assert after["max_file_size_mb"] == before["max_file_size_mb"]
    assert after["triggers_n8n_webhook"] == before["triggers_n8n_webhook"]


def test_upgrade_is_idempotent(db):
    _run(db)
    before = db.execute(
        text("SELECT count(*) FROM attachment_types WHERE code IN "
             "('shipment_line_photo', 'proforma_invoice', 'packing_list')")
    ).scalar()

    _run(db)  # replay - must not raise a duplicate-key error, must not double the rows

    after = db.execute(
        text("SELECT count(*) FROM attachment_types WHERE code IN "
             "('shipment_line_photo', 'proforma_invoice', 'packing_list')")
    ).scalar()
    assert after == before


def test_downgrade_deletes_the_two_fresh_rows_but_only_clears_packing_lists_code(db):
    _run(db)
    _run(db, "downgrade")

    assert _row(db, "shipment_line_photo") is None
    assert _row(db, "proforma_invoice") is None
    # Packing List's own row survives - only its code column reverts.
    row = db.execute(
        text("SELECT code FROM attachment_types WHERE type_name = 'Packing List'")
    ).mappings().first()
    assert row is not None
    assert row["code"] is None
