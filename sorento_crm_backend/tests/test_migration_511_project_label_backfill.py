"""Migration 511's own backfill helper (AC-M2).

`backfill_project_labels(connection)` derives `project_label`/`project_label_source` from
whatever plain-text note a row already carries, respecting the same precedence gate every
other writer goes through (`apply_project_label`) - so re-running it after a manual
correction or a later importer run cannot regress anything.

AC-M1 (the two columns, chained on `510_strip_rtf_so_notes`, single alembic head, revision id
<= 32 chars) and AC-M3 (downgrade drops both columns) are the coder's own `alembic heads`
check and are not exercised here, per the brief.

Substrate: `pg_session()` against the REAL database, rolled back - raw SQL does not resolve
through `blank_session`'s schema-translate map (see `test_migration_450_spec_rules_backfill.py`
and `test_rtf_note_strip.py::TestBackfillHelper`, which reads the sibling migration 510's own
helper the same way), so a scratch copy would prove nothing about what this migration does to
the real table.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from app.models.order import SalesOrder
from tests._pg_fixture import pg_session, unique_code

MARKER = "ZZTPL511"

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent / "alembic" / "versions" / "511_so_project_label.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("zzt_migration_511", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def db():
    with pg_session() as session:
        yield session


def _so(db, *, note) -> str:
    row = SalesOrder(
        id=str(uuid.uuid4()), so_number=unique_code(MARKER), status="open", internal_note=note,
    )
    db.add(row)
    db.flush()
    return str(row.id)


def _labelled(db, so_id):
    return (
        db.execute(
            text("SELECT project_label, project_label_source FROM sales_orders WHERE id = :id"),
            {"id": so_id},
        )
        .mappings()
        .first()
    )


class TestBackfillProjectLabels:
    def test_a_plain_project_note_backfills_a_note_label(self, db):
        so_id = _so(db, note="***PROJECT : PINE LEGACY")

        _migration_module().backfill_project_labels(db.connection())

        row = _labelled(db, so_id)
        assert row["project_label"] == "PINE LEGACY"
        assert row["project_label_source"] == "note"

    def test_a_delivery_block_note_backfills_a_delivery_label(self, db):
        so_id = _so(
            db,
            note=(
                "DELIVERY ADDRESS\n"
                "A-25-07 MAYA ARA RESIDENCES\n"
                "1 JALAN PJU 1A/1, ARA DAMANSARA"
            ),
        )

        _migration_module().backfill_project_labels(db.connection())

        row = _labelled(db, so_id)
        assert row["project_label"] == "MAYA ARA RESIDENCES"
        assert row["project_label_source"] == "delivery"

    def test_an_order_inquiry_note_backfills_the_inquiry_label(self, db):
        so_id = _so(
            db,
            note="Order Inquiry project: PEMBINAAN TEGUH MAJU / TAIGA RESIDENCE / KUALA LUMPUR",
        )

        _migration_module().backfill_project_labels(db.connection())

        row = _labelled(db, so_id)
        assert row["project_label"] == "TAIGA RESIDENCE / KUALA LUMPUR"
        assert row["project_label_source"] == "inquiry"

    def test_an_own_collect_note_stays_null(self, db):
        so_id = _so(db, note="***OWN COLLECT")

        _migration_module().backfill_project_labels(db.connection())

        row = _labelled(db, so_id)
        assert row["project_label"] is None
        assert row["project_label_source"] is None

    def test_a_row_that_already_has_an_inquiry_label_is_untouched(self, db):
        so_id = _so(db, note="***PROJECT : SHOULD NOT WIN")
        db.execute(
            text(
                "UPDATE sales_orders SET project_label = :label, "
                "project_label_source = 'inquiry' WHERE id = :id"
            ),
            {"label": "ALREADY SET", "id": so_id},
        )
        db.flush()

        _migration_module().backfill_project_labels(db.connection())

        row = _labelled(db, so_id)
        assert row["project_label"] == "ALREADY SET"
        assert row["project_label_source"] == "inquiry"
