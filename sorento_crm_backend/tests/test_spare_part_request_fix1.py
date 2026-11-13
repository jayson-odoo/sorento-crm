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

import re
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


# =============================================================================
# Security review fix round (scratchpad security-review.md): G4 B1, G5 S1, G6 S2, G7 S3
# =============================================================================

from ._forms_chain_support import open_tracker, sla_chain, trackers  # noqa: E402
from ._spare_part_request_support import (  # noqa: E402,F401  (fixture)
    KIND,
    OI_RAISED_NOTICE,
    TWO_STAGES,
    approve,
    role_grant,
    two_staged,
)


def _purchasing_notices(w) -> list:
    return [c for c in w.sent if c[0] == w.buyer and c[1] == OI_RAISED_NOTICE]


def test_G4_a_second_approve_racing_the_first_cannot_close_stage_two(two_staged, monkeypatch):
    """B1. Deterministic interleave of two approves by the SAME stage-1 member: request B
    passes its authorisation while stage 1 is open, then request A runs to completion
    (stage 1 resolved, stage 2 started), then B continues. B must be refused (403/409) and
    must not resolve stage 2: the decision is bound to the stage the actor was authorised
    on, re-checked under a row lock (security review fix)."""
    w = two_staged
    inquiry = submitted(w)
    module = svc()
    real_can_decide = module.can_decide
    state = {"interleaved": False, "inside_a": False}

    def racing_can_decide(db, inq, user_id):
        verdict = real_can_decide(db, inq, user_id)
        if not state["interleaved"] and not state["inside_a"]:
            state["interleaved"] = True
            state["inside_a"] = True
            try:
                module.approve(w.db, reload(w.db, inquiry), w.stage1.tier1)  # request A
                w.db.commit()
            finally:
                state["inside_a"] = False
        return verdict

    monkeypatch.setattr(module, "can_decide", racing_can_decide)
    with pytest.raises(AppException) as excinfo:
        module.approve(w.db, reload(w.db, inquiry), w.stage1.tier1)  # request B
    assert state["interleaved"], "approve authorises the actor through can_decide"
    assert excinfo.value.status_code in (403, 409)
    w.db.rollback()

    after = reload(w.db, inquiry)
    assert after.state == "pending_approval"
    tracker = open_tracker(w.db, KIND, inquiry.id)
    assert tracker.team_set_code == w.stage2.team_set, "stage 2 is still waiting for its own team"
    stage1 = [t for t in trackers(w.db, KIND, inquiry.id) if t.team_set_code == w.stage1.team_set]
    assert len(stage1) == 1 and stage1[0].is_resolved, "exactly one stage-1 approval recorded"
    assert all(r.state == "draft" for r in rows_of(w.db, inquiry))
    assert not _purchasing_notices(w)


def test_G4_approve_locks_the_inquiry_row(staged):
    """B1 contract: the decide path takes SELECT ... FOR UPDATE on the inquiry before it
    re-checks who may decide."""
    from sqlalchemy import event

    w = staged
    inquiry = submitted(w)
    seen: list[str] = []
    bind = w.db.connection()

    def capture(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement)

    event.listen(bind, "before_cursor_execute", capture)
    try:
        approve(w, inquiry, w.stage1.tier1)
    finally:
        event.remove(bind, "before_cursor_execute", capture)
    locked = re.compile(r"FROM\s+\S*order_inquiries\b.*\bFOR\s+(NO\s+KEY\s+)?UPDATE", re.I | re.S)
    assert any(locked.search(s) for s in seen), (
        "no SELECT ... FOR UPDATE on projects.order_inquiries during approve"
    )


def _parallel(w):
    """S1: two stages that BOTH start on 'submitted' (parallel sign-off), no chain."""
    chain = sla_chain(
        w.db, KIND,
        [
            {"start_event": "submitted", "resolve_event": "approved,rejected"},
            {"start_event": "submitted", "resolve_event": "approved,rejected"},
        ],
    )
    for stage in chain.stages:
        stage.config.next_config_id = None
        role_grant(w.db, stage.tier1, "projects.projects.view", "procurement.spare_part_requests.create")
        role_grant(w.db, stage.tier2, "projects.projects.view", "procurement.spare_part_requests.create")
    w.db.commit()
    return chain.stages


def test_G5_parallel_stages_one_teams_approval_closes_only_its_own_stage(world):
    w = world
    team_a, team_b = _parallel(w)
    inquiry = submitted(w)
    assert len(trackers(w.db, KIND, inquiry.id, open_only=True)) == 2

    inquiry = approve(w, inquiry, team_a.tier1)
    assert inquiry.state == "pending_approval", "team B has not decided"
    still_open = trackers(w.db, KIND, inquiry.id, open_only=True)
    assert [t.team_set_code for t in still_open] == [team_b.team_set]
    assert svc().can_decide(w.db, inquiry, team_a.tier1) is False
    assert not _purchasing_notices(w)

    inquiry = approve(w, inquiry, team_b.tier1)
    assert inquiry.state == "raised"
    assert len(_purchasing_notices(w)) == 1


def test_G6_approval_fails_closed_when_the_next_stage_cannot_start(two_staged):
    """S2: stage 2's team is emptied; approving stage 1 must not raise the request."""
    from app.models.access import AgentTeam, TeamMember

    w = two_staged
    inquiry = submitted(w)
    team_ids = [t.team_id for t in w.db.query(AgentTeam).filter(AgentTeam.code == w.stage2.team_set).all()]
    w.db.query(TeamMember).filter(TeamMember.team_id.in_(team_ids)).delete(synchronize_session=False)
    w.db.commit()

    try:
        svc().approve(w.db, reload(w.db, inquiry), w.stage1.tier1)
        w.db.commit()
    except AppException as exc:
        assert exc.status_code in (409, 422)
        assert exc.message and "_" not in exc.message, "a plain message for the admin"
        w.db.rollback()

    after = reload(w.db, inquiry)
    assert after.state == "pending_approval", "never raised on one level of sign-off"
    assert all(r.state == "draft" for r in rows_of(w.db, inquiry))
    assert not _purchasing_notices(w)


def test_G7_a_draft_or_pending_row_cannot_be_linked_to_a_po(staged):
    w = staged
    po = _po_line(w.db, w.product_a, w.loc_a, qty=30)
    w.db.commit()
    draft = create(w)
    pending = submitted(w)
    for inquiry in (draft, pending):
        row = row_for(w.db, inquiry, w.product_a)
        res = w.as_user(w.buyer).post(
            f"/api/v1/project-sales/order-inquiry-rows/{row.id}/place-on-po",
            json={"po_line_id": str(po.line.id)},
        )
        assert res.status_code == 409, res.text
        res = w.as_user(w.buyer).get(f"/api/v1/project-sales/order-inquiry-rows/{row.id}/po-candidates")
        assert res.status_code == 409, res.text
        assert row_for(w.db, inquiry, w.product_a).state == "draft"


def test_G7_the_service_link_guard_refuses_a_draft_row(staged):
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    w = staged
    row = row_for(w.db, submitted(w), w.product_a)
    with pytest.raises(AppException) as excinfo:
        ProjectOrderInquiryService(w.db)._assert_linkable(row)
    assert excinfo.value.status_code == 409


# =============================================================================
# S1 (security review gap) - a create-only requester on `company_scope=grants`
# =============================================================================

_DOC_TOP = ("sales_orders", "purchase_orders", "spos", "incoming_pl", "incoming", "holds")


@pytest.fixture
def create_only_grants():
    """A requester holding ONLY the spare part create grant, granted companies A and B; a third
    company C is not granted. B and C each own a bin carrying stock of one product."""
    from fastapi.testclient import TestClient

    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.main import app
    from app.models.base import company_scope
    from app.services.company_scope_resolver import apply_company_scope
    from tests import test_stock_detail_company_grants as sd
    from tests._pg_fixture import blank_session
    from tests.chatbot.agent._seed import seed_user

    with blank_session() as db:
        with company_scope(db, frozenset({sd.COMPANY_A})):
            company_b = sd._company(db)
            company_c = sd._company(db)
            requester = seed_user(
                db, contact_pk=None, slugs=("procurement.spare_part_requests.create",)
            )
            sd._grant(db, requester, sd.COMPANY_A)
            sd._grant(db, requester, company_b)
            product = sd._product(db)
            with company_scope(db, frozenset({company_b})):
                bin_b = sd._warehouse(db, company_b)
                sd._stock(db, product, bin_b, on_hand=7)
            with company_scope(db, frozenset({company_c})):
                bin_c = sd._warehouse(db, company_c)
                sd._stock(db, product, bin_c, on_hand=9)
            who = {"user": {"id": requester, "email": "r@zzt.test", "auth_method": "password"}}

            def _db():
                yield db

            app.dependency_overrides[get_db] = _db
            app.dependency_overrides[get_current_user] = lambda: who["user"]
            app.dependency_overrides[get_current_user_or_api_key] = lambda: who["user"]
            app.dependency_overrides[apply_company_scope] = lambda: frozenset({sd.COMPANY_A})
            try:
                with TestClient(app) as c:
                    yield SimpleNamespace(c=c, product=product, bin_b=bin_b, bin_c=bin_c)
            finally:
                app.dependency_overrides.clear()


def _assert_no_documents(body: dict) -> None:
    for key in _DOC_TOP:
        assert not body.get(key), f"{key} must be empty for a create-only requester: {body.get(key)!r}"
    for loc in body.get("locations") or []:
        for key in _DOC_TOP:
            assert not loc.get(key), f"locations[].{key} must be empty: {loc.get(key)!r}"


def test_S1_guard_stock_status_grants_gives_a_create_only_requester_no_documents(create_only_grants):
    g = create_only_grants
    res = g.c.get(
        "/api/v1/inventory/stock-status",
        params={"product_id": str(g.product.id), "company_scope": "grants"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    _assert_no_documents(body)
    ids = {loc["warehouse_id"] for loc in body["locations"]}
    assert str(g.bin_b.id) in ids, "the granted company's bin is listed (quantities)"
    assert str(g.bin_c.id) not in ids, "an ungranted company's bin never is"


def test_S1_guard_stock_detail_grants_gives_a_create_only_requester_no_documents(create_only_grants):
    g = create_only_grants
    url = "/api/v1/project-sales/fulfilment-planning/stock-detail"
    ok = g.c.get(
        url,
        params={"product_id": str(g.product.id), "warehouse_id": str(g.bin_b.id), "company_scope": "grants"},
    )
    assert ok.status_code == 200, ok.text
    _assert_no_documents(ok.json())
    denied = g.c.get(
        url,
        params={"product_id": str(g.product.id), "warehouse_id": str(g.bin_c.id), "company_scope": "grants"},
    )
    assert denied.status_code == 404, denied.text
