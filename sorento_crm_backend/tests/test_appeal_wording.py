"""COMPLAINT-APPEAL-WORDING: every form reads "Appealed" / "Appeal", never "Resubmitted".

Owner, 28 Oct 2026. Display only: the stored value stays `resubmitted`. The status-engine
graphs (quotation, dealer-kit edition) hold their labels in rows, so migration
appeal_0001_appeal_labels relabels them; it runs here against a blank schema inside a
transaction that is rolled back.
"""
from __future__ import annotations

import importlib.util
import pathlib
from types import SimpleNamespace

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from ._pg_fixture import blank_session

_MIGRATION = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic" / "versions" / "appeal_0001_appeal_labels.py"
)


def _migration():
    spec = importlib.util.spec_from_file_location("migration_appeal_0001", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, step: str) -> None:
    context = MigrationContext.configure(db.connection())
    with Operations.context(context):
        getattr(_migration(), step)()


def _labels(db) -> tuple[str, str]:
    status = db.execute(
        text("SELECT label FROM statuses WHERE entity_type = 'quotation' AND key = 'resubmitted'")
    ).scalar()
    edge = db.execute(
        text(
            "SELECT t.label FROM status_transitions t JOIN statuses s ON s.id = t.to_status_id "
            "WHERE t.entity_type = 'quotation' AND s.key = 'resubmitted' "
            "AND t.from_status_id IN (SELECT id FROM statuses WHERE key = 'draft')"
        )
    ).scalar()
    return status, edge


def _as_seeded_before(db) -> None:
    """The rows the resub_0001 seed wrote, before this lane."""
    db.execute(text("UPDATE statuses SET label = 'Resubmitted' WHERE key = 'resubmitted'"))
    db.execute(
        text(
            "UPDATE status_transitions SET label = 'Resubmit for approval' WHERE to_status_id IN "
            "(SELECT id FROM statuses WHERE key = 'resubmitted') "
            "AND from_status_id IN (SELECT id FROM statuses WHERE key = 'draft')"
        )
    )


def test_a_fresh_quotation_graph_is_seeded_appealed():
    from app.services.project_seed_service import seed_quotation_approval_graph

    with blank_session() as db:
        seed_quotation_approval_graph(db)
        db.flush()
        assert _labels(db) == ("Appealed", "Appeal")


def test_the_migration_relabels_the_seeded_rows_and_downgrade_puts_them_back():
    from app.services.project_seed_service import seed_quotation_approval_graph

    with blank_session() as db:
        seed_quotation_approval_graph(db)
        db.flush()
        _as_seeded_before(db)
        assert _labels(db) == ("Resubmitted", "Resubmit for approval")

        _run(db, "upgrade")
        assert _labels(db) == ("Appealed", "Appeal")
        _run(db, "upgrade")  # idempotent
        assert _labels(db) == ("Appealed", "Appeal")

        _run(db, "downgrade")
        assert _labels(db) == ("Resubmitted", "Resubmit for approval")


def test_a_label_an_admin_renamed_is_left_alone():
    from app.services.project_seed_service import seed_quotation_approval_graph

    with blank_session() as db:
        seed_quotation_approval_graph(db)
        db.flush()
        db.execute(text("UPDATE statuses SET label = 'Second look' WHERE key = 'resubmitted'"))
        _run(db, "upgrade")
        assert _labels(db)[0] == "Second look"


def test_revision_history_and_its_file_name_say_appealed():
    from app.services.pdf_revision_support import _entry_filename_marker
    from app.services.portal_revision_service import KIND_RESUBMISSION, _revision_label

    assert _revision_label(SimpleNamespace(kind=KIND_RESUBMISSION)) == "Appealed"
    marker = _entry_filename_marker({"kind": KIND_RESUBMISSION, "version_no": 3})
    assert marker == "appealed-v3"


def test_every_label_map_reads_appealed():
    from app.services import form_action_notify, new_product_application_service as npa
    from app.services.reports.datasets.sponsorship_forms import STATUS_LABELS as SF_REPORT
    from app.services.stock_inquiry_pdf_service import _STATUS_LABELS as SI_PDF

    assert dict(SF_REPORT)["resubmitted"] == "Appealed"
    assert SI_PDF["resubmitted"] == "Appealed"
    assert npa.STATUS_LABELS["resubmitted"] == "Appealed"
    assert form_action_notify._status_label("resubmitted") == "Appealed"
    assert npa._EVENTS["resubmitted"][0] == "was appealed and waits for your approval"
