"""SPARE-PART-OR-B C, red-first (Phase 2). The one additive migration.

Contract: documentation/plans/purchasing/spare-part-or-c-14nov-acceptance-criteria.md
"Migration": `order_inquiry_rows.revised_product_id` uuid FK products NULL,
`order_inquiry_rows.revised_delivery_date` date NULL, plus the guarded C2.4 template step;
id <= 32 chars, single head, nothing dropped. The schema half reads a `blank_session`
scratch schema (create_all off the models); the file half reads alembic's script directory.

NAMED CONTRACT CHOICE: the migration is found as the one revision file that mentions
`revised_product_id` (so a re-parent onto a newer main head does not break the test).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import text

from ._pg_fixture import blank_session

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "column, data_type",
    [("revised_product_id", "uuid"), ("revised_delivery_date", "date")],
)
def test_migration_the_new_row_columns_exist_and_are_nullable(column, data_type):
    with blank_session() as db:
        row = db.execute(
            text(
                "SELECT data_type, is_nullable FROM information_schema.columns "
                "WHERE table_schema = current_schema() || '_projects' "
                "AND table_name = 'order_inquiry_rows' AND column_name = :c"
            ),
            {"c": column},
        ).first()
        assert row is not None, f"projects.order_inquiry_rows.{column} exists"
        assert row.data_type == data_type, row
        assert row.is_nullable == "YES"


def test_migration_revised_product_id_is_a_foreign_key_to_products():
    from app.models.project_so import OrderInquiryRow

    column = OrderInquiryRow.__table__.c.get("revised_product_id")
    assert column is not None, "OrderInquiryRow.revised_product_id is mapped"
    targets = {fk.column.table.name for fk in column.foreign_keys}
    assert "products" in targets, targets


def _script():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    return ScriptDirectory.from_config(config)


def test_migration_one_additive_revision_on_a_single_head():
    script = _script()
    heads = script.get_heads()
    assert len(heads) == 1, f"single alembic head, got {heads}"
    adding = [
        rev for rev in script.walk_revisions()
        if "revised_product_id" in Path(rev.path).read_text()
    ]
    assert len(adding) == 1, f"exactly one migration adds revised_product_id: {adding}"
    revision = adding[0]
    assert len(revision.revision) <= 32, revision.revision
    source = Path(revision.path).read_text()
    assert "revised_delivery_date" in source, "the same migration adds revised_delivery_date"
    upgrade = source.split("def downgrade")[0]
    assert not re.search(r"\b(drop_table|drop_column|alter_column)\b", upgrade), (
        "upgrade is additive only"
    )
    assert "order_inquiry_handover_default" in source or "relabel_handover_template" in source, (
        "the guarded C2.4 template step rides in the same revision"
    )
