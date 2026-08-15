"""A many-to-one relationship reassignment is a real, audit-worthy change.

``_dirty_has_real_changes`` (the noise guard added so a no-op `session.dirty`
membership - e.g. reassigning a column to the value it already holds - stops
writing content-free UPDATE rows) checked only column history. That missed
relationship reassignment entirely: `edition.page = other_page` does not touch
`page_id`'s own attribute history at the point `before_flush` runs - the FK is
synchronised from the relationship later in the SAME flush, during the
unit-of-work's dependency processing - so the column-only guard reported no
change for an Edition whose relationship really did move, and the transition
silently wrote nothing.

That is a regression against `main`: before the guard existed, ANY dirty
tracked object wrote a row (old==new for every column, because the FK genuinely
has not synced yet at that point - a content-free "touch" row, but a row).
Restoring it here, scoped to MANYTOONE relationships only - a child appended to
a one-to-many collection is the CHILD's own audited change, not a content
change on the parent holding the collection.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from app.models.audit import AuditLog
from app.models.base import set_company_scope
from app.services.audit_service import register_audit_listeners
from app.services.dealer_kit import edition_service, page_service
from tests._pg_fixture import blank_session, unique_code

_SORENTO = "00000000-0000-0000-0000-000000000001"

_MIG_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "318_dealer_kit_edition.py"
)
_spec = importlib.util.spec_from_file_location("mig_318_relationship_audit", _MIG_PATH)
mig318 = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(mig318)

# Idempotent - safe to call outside the TestClient/startup-event path the other
# audit tests rely on to trigger it.
register_audit_listeners()


def _rows_for(db, entity_id: str) -> list[AuditLog]:
    return (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == "dealer_kit_edition", AuditLog.entity_id == entity_id)
        .order_by(AuditLog.changed_at.asc())
        .all()
    )


def _setup(db):
    mig318._seed_graph(db.connection())
    db.flush()
    set_company_scope(db, frozenset({_SORENTO}))
    page_a = page_service.create_page(
        db, name=unique_code("ZZT Rel Page A"), slug=unique_code("zzt-rel-a").lower(), user_id=None
    )
    page_b = page_service.create_page(
        db, name=unique_code("ZZT Rel Page B"), slug=unique_code("zzt-rel-b").lower(), user_id=None
    )
    edition = edition_service.create_edition(db, page_id=page_a.id, name=unique_code("ZZT Edition"))
    return page_a, page_b, edition


class TestRelationshipReassignmentIsAudited:
    def test_reassigning_the_page_relationship_alone_writes_one_update_row(self) -> None:
        with blank_session() as db:
            _page_a, page_b, edition = _setup(db)
            before = len(_rows_for(db, edition.id))

            # The relationship OBJECT, never the FK column directly - that is
            # the exact shape that missed the column-only guard.
            edition.page = page_b
            db.commit()

            rows = _rows_for(db, edition.id)
            update_rows = [r for r in rows if r.action == "UPDATE"]
            assert len(rows) == before + 1, [(r.action, r.old_values, r.new_values) for r in rows]
            assert len(update_rows) == 1, [(r.action, r.old_values, r.new_values) for r in rows]

    def test_reassigning_a_column_to_its_current_value_still_writes_nothing(self) -> None:
        """The existing no-op guard must not regress: this is what it exists
        for, and it must keep working alongside the relationship check above."""
        with blank_session() as db:
            _page_a, _page_b, edition = _setup(db)
            before = len(_rows_for(db, edition.id))

            edition.name = edition.name  # identical value, no real change
            db.commit()

            after = _rows_for(db, edition.id)
            assert len(after) == before, [(r.action, r.old_values, r.new_values) for r in after]
