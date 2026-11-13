"""Project import: revert (AC-PI-37..38).

RED tests, written before `app/services/project_import/service.py` exists
(PLAN-project-import-12nov.md, "Backend contract": `revert(db, run, *, user_id)` and the
record action `project_import_run.revert` parked through `/api/v1/pending-actions`).
Postgres via `blank_session`; everything seeded here.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from ._project_import_support import (  # noqa: F401  fixtures
    MARKER,
    make_book,
    memory_storage,
    new_run,
    row,
    seed_customer,
    snapshot,
    world,
)

C1 = "CUSTOMER 001 SDN BHD"
P1 = "PROJECT 001 SAMPLE NAME"


def _svc():
    from app.services.project_import import service

    return service


def _imported(w, rows, *, developer_create=False):
    s = _svc()
    customer = seed_customer(w.db, w.company_id, f"{MARKER} DEALER ONE")
    w.db.commit()
    run = new_run(w, make_book({"JAN'26": rows}))
    s.set_line(w.db, run, kind="customer", value_key=C1, action="link", target_id=customer.id,
               user_id=w.admin_id)
    for line in s.list_lines(w.db, run, kind="project"):
        s.set_line(w.db, run, kind="project", customer_value_key=line["customer_value_key"],
                   value_key=line["value_key"], action="create", new_title="ZZT REVERT TOWER",
                   user_id=w.admin_id)
    for line in s.list_lines(w.db, run, kind="developer"):
        s.set_line(w.db, run, kind="developer", value_key=line["value_key"],
                   action="create" if developer_create else "none", user_id=w.admin_id)
    for line in s.list_lines(w.db, run, kind="person"):
        s.set_line(w.db, run, kind="person", value_key=line["value_key"], action="none",
                   user_id=w.admin_id)
    w.db.commit()
    return run


def test_ac_pi_37_revert_removes_every_record_the_run_created(world):
    w = world
    before = snapshot(w.db)
    run = _imported(w, [row("PS26-0001", developer="ZZT DEV R"), row("PS26-0002")],
                    developer_create=True)
    _svc().apply(w.db, run, user_id=w.admin_id)
    w.db.commit()
    mid = snapshot(w.db)
    assert mid["projects"] == before["projects"] + 1
    assert mid["purchase_orders"] == before["purchase_orders"] + 2
    assert mid["parties"] == before["parties"] + 1

    result = _svc().revert(w.db, run, user_id=w.admin_id)
    w.db.commit()

    after = snapshot(w.db)
    for table in ("projects", "sales_profiles", "purchase_orders", "parties",
                  "project_sales_orders"):
        assert after[table] == before[table], table
    assert result["kept"] == []
    assert sum(result["removed"].values()) >= 5  # project, profile, 2 POs, party
    w.db.refresh(run)
    assert run.job_metadata["phase"] == "reverted"


def test_ac_pi_37_records_edited_or_grown_since_the_run_are_kept(world):
    from app.models.projects import Project, ProjectPurchaseOrder
    from app.services import project_po_service

    w = world
    run = _imported(w, [row("PS26-0001"), row("PS26-0002", po_number="PO-2")])
    _svc().apply(w.db, run, user_id=w.admin_id)
    w.db.commit()
    project = w.db.query(Project).one()
    edited = (w.db.query(ProjectPurchaseOrder)
              .filter(ProjectPurchaseOrder.admin_ref == "PS26-0001").one())
    untouched = (w.db.query(ProjectPurchaseOrder)
                 .filter(ProjectPurchaseOrder.admin_ref == "PS26-0002").one())
    # A person edits one PO after the run finished ...
    edited.po_amount = Decimal("9999.00")
    edited.updated_at = datetime.utcnow() + timedelta(minutes=5)
    # ... and keys a PO of their own onto the imported project (a child not made by the run).
    own = project_po_service.create_po(
        w.db, project=project, actor_user_id=w.admin_id,
        payload={"po_source": "contractor_direct", "po_number": "HAND-KEYED"},
    )
    w.db.commit()

    result = _svc().revert(w.db, run, user_id=w.admin_id)
    w.db.commit()

    kept_reasons = {k["reason"] for k in result["kept"]}
    assert kept_reasons == {"revert_kept_edited"}
    kept_types = [k["entity_type"] for k in result["kept"]]
    assert len(kept_types) >= 2  # the edited PO and the project with a foreign child
    for k in result["kept"]:
        assert k["label"]  # a readable label
        assert str(project.id) not in k["label"] and str(edited.id) not in k["label"]
    assert w.db.get(ProjectPurchaseOrder, edited.id) is not None
    assert w.db.get(Project, project.id) is not None
    assert w.db.get(ProjectPurchaseOrder, own.id) is not None
    assert w.db.get(ProjectPurchaseOrder, untouched.id) is None  # unedited: removed
    w.db.refresh(run)
    assert run.job_metadata["phase"] == "reverted"


def test_ac_pi_38_a_second_revert_changes_nothing(world):
    w = world
    run = _imported(w, [row("PS26-0001")])
    _svc().apply(w.db, run, user_id=w.admin_id)
    _svc().revert(w.db, run, user_id=w.admin_id)
    w.db.commit()
    before = snapshot(w.db)

    try:
        second = _svc().revert(w.db, run, user_id=w.admin_id)
    except Exception as exc:  # a refusal is also "changes nothing"
        from app.services.error_handler import AppException

        assert isinstance(exc, AppException)
        assert exc.status_code in (409, 422)
    else:
        assert sum(second["removed"].values()) == 0
    w.db.commit()
    assert snapshot(w.db) == before


def test_ac_pi_38_a_preview_only_run_cannot_be_reverted(world):
    from app.services.error_handler import AppException

    w = world
    run = _imported(w, [row("PS26-0001")])
    _svc().preview(w.db, run, user_id=w.admin_id)
    w.db.commit()

    with pytest.raises(AppException) as excinfo:
        _svc().revert(w.db, run, user_id=w.admin_id)
    assert excinfo.value.status_code in (409, 422)
    w.db.refresh(run)
    assert run.job_metadata["phase"] == "previewed"


def test_ac_pi_37_revert_is_a_registered_record_action():
    import app.services.record_actions  # noqa: F401  registers every action
    from app.services.form_action_registry import get_action

    action = get_action("project_import_run.revert")
    assert action is not None
    assert "project_import_run" in action.entity_types
    assert action.permission == "projects.import.run"
