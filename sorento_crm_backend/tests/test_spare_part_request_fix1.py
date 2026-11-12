"""SPARE-PART-ORDER-REQUEST fix round 1, red-first (Phase 2). Three gaps the lead named:

G1 Delete draft (CRUD standard D7: hard delete through the deferred pending-action pattern,
   never a confirm dialog). The requester hard-deletes their own spare part request while
   Draft or Rejected - header, rows and the rows' photo links all gone; 409 once Pending
   approval or later; 403 for anyone else; a sales-order inquiry is never deletable this way.
   NAMED ASSUMPTIONS (the NPA precedent, `new_product_application_service.assert_deletable /
   delete_draft` + record action `new_product_application.delete`):
     - record action key `spare_part_request.delete`, entity type `spare_part_request`,
       destructive window, refused at PARK time through `pending_actions._assert_entity_visible`
       (no countdown for a delete that would fail);
     - service `assert_deletable(db, inquiry_id, user_id)` and `delete_draft(db, inquiry_id,
       user_id)` in `spare_part_request_service`.
G2 The Approve popup lists photo changes. Nothing on the wire says what the approver did to
   the photos today, so this requires a NEW per-line field `photo_changes = {"added": n,
   "removed": n}`: photos added / removed on that line since the request was last submitted
   (photos the requester attached while drafting count as neither). On the SPR detail lines
   AND on the worklist rows (the OI page's Approve popup reads the worklist rows).
G3 Purchasing links a PO by hand to an approved (REPLENISH) row through the existing
   `POST /order-inquiry-rows/{row_id}/place-on-po` (what the Lines tab's link dialog calls):
   the row moves to placed / partly_linked like an ORDER row, and `scm.committed_v` for the
   product is unchanged. Runs on the MIGRATED db (the view), like test_spare_part_request_demand.

Postgres only; every row seeded here.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.error_handler import AppException

from ._forms_chain_support import SORENTO, uid
from ._spare_part_request_support import (  # noqa: F401  (fixtures)
    ONE_STAGE,
    ROW_ATT,
    SPR,
    TINY_PNG,
    WORKLIST,
    add_stages,
    create,
    raised,
    reload,
    row_for,
    rows_of,
    sent,
    staged,
    stub_storage,
    submitted,
    svc,
    world,
)
from .test_spare_part_request_demand import _committed, real  # noqa: F401  (fixture)

PENDING = "/api/v1/pending-actions"
DELETE_KEY = "spare_part_request.delete"
ENTITY = "spare_part_request"


@pytest.fixture
def photos(staged, monkeypatch):
    from app.models.resources import AttachmentType

    stub_storage(monkeypatch)
    staged.db.add(
        AttachmentType(
            id=uid(), type_name="Sales Order Line Attachment", code="so_line_attachment",
            allowed_extensions="jpg,jpeg,png,webp,gif,pdf,xlsx,xls", max_file_size_mb=10,
        )
    )
    staged.db.commit()
    return staged


def _upload(w, user_id, row_id, name="seal.png"):
    res = w.as_user(user_id).post(
        f"{ROW_ATT}/{row_id}/attachments", files=[("files", (name, TINY_PNG, "image/png"))]
    )
    assert res.status_code in (200, 201), res.text
    return res.json()


def _links(db, row_ids) -> list:
    from app.models.entity_attachment import EntityAttachmentLink

    db.expire_all()
    return (
        db.query(EntityAttachmentLink)
        .filter(EntityAttachmentLink.entity_id.in_([str(r) for r in row_ids]))
        .all()
    )


def _exists(db, inquiry_id) -> bool:
    from app.models.project_so import OrderInquiry

    db.expire_all()
    return db.query(OrderInquiry).filter(OrderInquiry.id == str(inquiry_id)).first() is not None


def _park(w, user_id, entity_id):
    return w.as_user(user_id).post(
        PENDING,
        json={"action_key": DELETE_KEY, "entity_type": ENTITY, "entity_id": str(entity_id), "payload": {}},
    )


def _commit_due(db) -> None:
    """The window lapsing: the parked row is made due and the scheduler sweep runs."""
    from app.models.sla import SlaFormAction
    from app.services.form_action_service import FormActionService

    for row in db.query(SlaFormAction).filter(SlaFormAction.status == "pending").all():
        row.commit_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    FormActionService(db).commit_due()
    db.commit()


# =============================================================================
# G1 - delete draft
# =============================================================================


def test_G1_delete_is_a_registered_destructive_record_action():
    import app.services.record_actions  # noqa: F401  (registers the actions)
    from app.services.form_action_grace import WINDOW_DESTRUCTIVE
    from app.services.form_action_registry import get_action

    action = get_action(DELETE_KEY)
    assert action is not None
    assert ENTITY in action.entity_types
    assert action.window == WINDOW_DESTRUCTIVE


def test_G1_the_requester_deletes_a_draft_through_the_countdown_header_rows_and_photos_gone(photos):
    w = photos
    draft = create(w)
    row_ids = [r.id for r in rows_of(w.db, draft)]
    _upload(w, w.requester, row_ids[0])
    assert _links(w.db, row_ids)

    res = _park(w, w.requester, draft.id)
    assert res.status_code == 202, res.text
    assert _exists(w.db, draft.id), "nothing happens until the window lapses"
    _commit_due(w.db)

    assert not _exists(w.db, draft.id)
    assert rows_of(w.db, draft) == []
    assert _links(w.db, row_ids) == []


def test_G1_a_rejected_request_is_deletable(staged):
    inquiry = submitted(staged)
    svc().reject(staged.db, inquiry, staged.stage1.tier1, "Wrong part")
    staged.db.commit()
    svc().delete_draft(staged.db, str(inquiry.id), staged.requester)
    staged.db.commit()
    assert not _exists(staged.db, inquiry.id)


def test_G1_pending_or_raised_is_409_at_park_and_in_the_service(staged):
    w = staged
    pending = submitted(w)
    done = raised(w)
    for inquiry in (pending, done):
        res = _park(w, w.requester, inquiry.id)
        assert res.status_code == 409, res.text
        with pytest.raises(AppException) as excinfo:
            svc().delete_draft(w.db, str(inquiry.id), w.requester)
        assert excinfo.value.status_code == 409
        w.db.rollback()
        assert _exists(w.db, inquiry.id)


def test_G1_anyone_but_the_requester_is_403(staged):
    w = staged
    draft = create(w)
    for who in (w.outsider, w.buyer, w.stage1.tier1):
        res = _park(w, who, draft.id)
        assert res.status_code == 403, res.text
        with pytest.raises(AppException) as excinfo:
            svc().assert_deletable(w.db, str(draft.id), who)
        assert excinfo.value.status_code == 403
        w.db.rollback()
    assert _exists(w.db, draft.id)


def test_G1_a_sales_order_inquiry_can_never_be_deleted_through_it(staged):
    from .test_oi_header_list import _header

    w = staged
    so_inquiry = _header(w.db, w.company_id)["inquiry"]
    res = _park(w, w.requester, so_inquiry.id)
    assert res.status_code in (403, 404, 409), res.text
    with pytest.raises(AppException) as excinfo:
        svc().delete_draft(w.db, str(so_inquiry.id), w.requester)
    assert excinfo.value.status_code in (403, 404, 409)
    w.db.rollback()
    assert _exists(w.db, so_inquiry.id)


def test_G1_a_draft_that_was_submitted_inside_the_window_is_not_deleted(staged):
    """Re-checked at commit: the state can change during the countdown."""
    w = staged
    draft = create(w)
    assert _park(w, w.requester, draft.id).status_code == 202
    svc().submit(w.db, reload(w.db, draft), w.requester)
    w.db.commit()
    _commit_due(w.db)
    assert _exists(w.db, draft.id)
    assert reload(w.db, draft).state == "pending_approval"


# =============================================================================
# G2 - the approver's photo changes are on the wire, per line
# =============================================================================


def _detail_line(w, user_id, inquiry, product) -> dict:
    res = w.as_user(user_id).get(f"{SPR}/{inquiry.id}")
    assert res.status_code == 200, res.text
    return next(item for item in res.json()["lines"] if item["product_id"] == str(product.id))


def _worklist_row(w, user_id, inquiry, product) -> dict:
    res = w.as_user(user_id).get(WORKLIST, params={"inquiry_id": str(inquiry.id), "limit": 100})
    assert res.status_code == 200, res.text
    return next(r for r in res.json()["data"] if r["product_id"] == str(product.id))


def test_G2_photos_added_and_removed_while_pending_are_counted_per_line(photos):
    w = photos
    draft = create(w)
    seal = row_for(w.db, draft, w.product_a)
    # The requester's own photo while drafting is part of the request, not a change.
    mine = _upload(w, w.requester, seal.id, name="requester.png")
    svc().submit(w.db, reload(w.db, draft), w.requester)
    w.db.commit()
    inquiry = reload(w.db, draft)
    hinge = row_for(w.db, inquiry, w.product_b)

    _upload(w, w.stage1.tier1, hinge.id, name="approver.png")
    res = w.as_user(w.stage1.tier1).delete(f"{ROW_ATT}/{seal.id}/attachments/{mine[0]['id']}")
    assert res.status_code == 200, res.text

    for read in (_detail_line, _worklist_row):
        assert read(w, w.stage1.tier1, inquiry, w.product_b)["photo_changes"] == {"added": 1, "removed": 0}
        assert read(w, w.stage1.tier1, inquiry, w.product_a)["photo_changes"] == {"added": 0, "removed": 1}


def test_G2_a_line_nobody_touched_reads_zero_changes(photos):
    w = photos
    inquiry = submitted(w)
    for read in (_detail_line, _worklist_row):
        assert read(w, w.stage1.tier1, inquiry, w.product_a)["photo_changes"] == {"added": 0, "removed": 0}


# =============================================================================
# G3 - purchasing links a PO by hand to a REPLENISH row; committed demand unchanged
# =============================================================================


def _po_line(db, product, warehouse, qty) -> SimpleNamespace:
    from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier

    supplier = Supplier(id=uid(), company_id=SORENTO, supplier_code=f"ZZT-{uid()[:8]}", supplier_name="ZZT spares supplier")
    db.add(supplier)
    db.flush()
    po = PurchaseOrder(id=uid(), company_id=SORENTO, po_number=f"ZZT-PO-{uid()[:8]}", supplier_id=supplier.id, status="active")
    db.add(po)
    db.flush()
    line = PurchaseOrderLine(
        id=uid(), company_id=SORENTO, purchase_order_id=po.id, product_id=product.id,
        warehouse_id=warehouse.id, qty_ordered=Decimal(str(qty)), qty_received=Decimal("0"),
        line_status="open",
    )
    db.add(line)
    db.flush()
    return SimpleNamespace(po=po, line=line)


@pytest.fixture
def buyer_api(real):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    actor = {"id": real.buyer, "email": f"{real.buyer}@zzt.test", "role": "staff"}
    app.dependency_overrides[get_db] = lambda: real.db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    app.dependency_overrides[apply_company_scope] = lambda: set_company_scope(real.db, frozenset({SORENTO}))
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _raised_row(real):
    add_stages(real, ONE_STAGE)
    inquiry = raised(real)
    return inquiry, row_for(real.db, inquiry, real.product_a)  # qty 10 at loc_a


def test_G3_purchasing_finds_and_links_a_po_line_and_the_row_is_placed(real, buyer_api):
    inquiry, row = _raised_row(real)
    po = _po_line(real.db, real.product_a, real.loc_a, qty=30)
    real.db.commit()
    pid, code = str(real.product_a.id), real.loc_a.warehouse_code
    before = _committed(real.db, pid, code)

    res = buyer_api.get(f"/api/v1/project-sales/order-inquiry-rows/{row.id}/po-candidates")
    assert res.status_code == 200, res.text
    assert str(po.line.id) in res.text, "the open PO line of the same product is offered"

    res = buyer_api.post(
        f"/api/v1/project-sales/order-inquiry-rows/{row.id}/place-on-po", json={"po_line_id": str(po.line.id)}
    )
    assert res.status_code == 200, res.text
    assert res.json()["state"] == "placed"
    assert res.json()["po_ref"] == po.po.po_number
    real.db.commit()
    assert _committed(real.db, pid, code) == before, "a spare part PO link moves no committed demand"


def test_G3_a_partial_link_reads_partly_linked(real, buyer_api):
    inquiry, row = _raised_row(real)
    po = _po_line(real.db, real.product_a, real.loc_a, qty=30)
    real.db.commit()
    pid, code = str(real.product_a.id), real.loc_a.warehouse_code
    before = _committed(real.db, pid, code)

    res = buyer_api.post(
        f"/api/v1/project-sales/order-inquiry-rows/{row.id}/place-on-po",
        json={"allocations": [{"po_line_id": str(po.line.id), "qty": "4"}]},
    )
    assert res.status_code == 200, res.text
    assert res.json()["state"] == "partly_linked"
    real.db.commit()
    assert reload(real.db, inquiry).state == "raised", "a partly linked row keeps its inquiry open"
    assert _committed(real.db, pid, code) == before
