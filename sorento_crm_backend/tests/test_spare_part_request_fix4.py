"""SPARE-PART-ORDER-REQUEST fix round 4 (security re-check), red-first (Phase 2).

C1 GET /fulfilment-planning/stock-detail for a caller WITHOUT projects.projects.view (a
   create-grant holder; a view_own user holding the create grant) carries per-location
   quantities only: `sales_orders` / `incoming` / `holds` empty or absent, and no customer,
   project, agent or supplier name and no document number anywhere in the payload. A
   projects.projects.view holder still gets the full payload (positive control: the seeded sales
   order and its customer are on it).
C2 Fail closed: stage 1 configured, plus a SECOND active spare_part_request config whose
   start_event includes 'approved' and which is NOT chained via next_config_id. Approving stage 1
   must not raise the request (it stays pending_approval, or a plain 409/422), and purchasing is
   told nothing.
C3 After the decision re-lock, approve re-checks the request is still pending: an admin reject
   forced in between the stage resolution and the finalise (the G4 interleave technique, hooked
   on `FormSLAOrchestrator.resolve_stage`) leaves the request rejected, never raised.

Postgres only (`blank_session`); every row seeded here.
"""
from __future__ import annotations

import json
from decimal import Decimal

import pytest

from app.services.error_handler import AppException

from ._forms_chain_support import sla_chain, uid, user
from ._spare_part_request_support import (  # noqa: F401  (fixtures)
    CREATE,
    KIND,
    OI_RAISED_NOTICE,
    VIEW,
    reload,
    role_grant,
    rows_of,
    sent,
    staged,
    submitted,
    svc,
    world,
)

STOCK_DETAIL = "/api/v1/project-sales/fulfilment-planning/stock-detail"


def _purchasing_notices(w) -> list:
    return [c for c in w.sent if c[0] == w.buyer and c[1] == OI_RAISED_NOTICE]


# =============================================================================
# C1 - stock-detail without projects.projects.view: quantities only
# =============================================================================


@pytest.fixture
def stock_world(staged):
    """A real open sales order for product A at loc A, with a named customer, so the full
    payload has document detail to hide."""
    from app.models.order import Customer, SalesOrder, SalesOrderLine

    w = staged
    customer = Customer(
        id=uid(), company_id=w.company_id, customer_code=f"ZZT-C{uid()[:8]}",
        customer_name="ZZT Hidden Customer Sdn Bhd",
    )
    w.db.add(customer)
    w.db.flush()
    so = SalesOrder(
        id=uid(), company_id=w.company_id, so_number=f"ZZTSO{uid()[:8]}".upper(),
        customer_id=customer.id, status="open", demand_class="project",
    )
    w.db.add(so)
    w.db.flush()
    w.db.add(
        SalesOrderLine(
            id=uid(), company_id=w.company_id, sales_order_id=so.id, product_id=w.product_a.id,
            warehouse_id=w.loc_a.id, qty_ordered=Decimal("7"), qty_delivered=Decimal("0"),
            line_status="open",
        )
    )
    w.own_user = user(w.db, "spr view_own requester")
    role_grant(w.db, w.own_user, "projects.projects.view_own", CREATE)
    w.db.commit()
    w.so_number = so.so_number
    w.customer_name = customer.customer_name
    return w


def _stock(w, user_id):
    res = w.as_user(user_id).get(
        STOCK_DETAIL, params={"product_id": str(w.product_a.id), "warehouse_id": str(w.loc_a.id)}
    )
    assert res.status_code == 200, res.text
    return res.json()


def test_C1_a_projects_viewer_still_gets_the_full_payload(stock_world):
    w = stock_world
    body = _stock(w, w.outsider)  # holds projects.projects.view
    assert any(so.get("so_number") == w.so_number for so in body.get("sales_orders", []))
    assert w.customer_name in json.dumps(body)
    assert Decimal(str(body["so_qty"])) == Decimal("7")


@pytest.mark.parametrize("who", ["requester", "own_user"])
def test_C1_without_projects_view_the_stock_detail_carries_quantities_only(stock_world, who):
    w = stock_world
    body = _stock(w, getattr(w, who))
    for key in ("sales_orders", "incoming", "holds"):
        assert not body.get(key), f"{key} must be empty or absent, got {body.get(key)!r}"
    text = json.dumps(body)
    assert w.so_number not in text, "no document number"
    assert w.customer_name not in text, "no customer name"
    assert Decimal(str(body["so_qty"])) == Decimal("7"), "the per-location quantities are still there"
    assert "qty_on_hand" in body and "available_qty" in body


# =============================================================================
# C2 - an unchained config that starts on 'approved' keeps the request from raising
# =============================================================================


def test_C2_an_unchained_stage_starting_on_approved_fails_closed(staged):
    w = staged
    extra = sla_chain(w.db, KIND, [{"start_event": "approved,submitted_level_x", "resolve_event": "completed"}])
    extra.stages[0].config.next_config_id = None
    w.stage1.config.next_config_id = None
    w.db.commit()

    inquiry = submitted(w)
    try:
        svc().approve(w.db, inquiry, w.stage1.tier1)
        w.db.commit()
    except AppException as exc:
        assert exc.status_code in (409, 422), exc.status_code
        assert exc.message and "_" not in exc.message, "a plain message for the admin"
        w.db.rollback()

    after = reload(w.db, inquiry)
    assert after.state == "pending_approval", "never raised while a further level is configured"
    assert all(r.state == "draft" for r in rows_of(w.db, after))
    assert not _purchasing_notices(w)


# =============================================================================
# C3 - an admin reject landing between the stage commit and the finalise wins
# =============================================================================


def test_C3_a_reject_landing_after_the_stage_commit_leaves_the_request_rejected(staged, monkeypatch):
    from app.services.form_sla_service import FormSLAOrchestrator

    w = staged
    inquiry = submitted(w)
    real_resolve = FormSLAOrchestrator.resolve_stage
    state = {"interleaved": False}

    def racing_resolve(self, tracker, event_name, **kw):
        real_resolve(self, tracker, event_name, **kw)
        if not state["interleaved"]:
            state["interleaved"] = True
            w.db.commit()  # the stage commit
            svc().reject(w.db, reload(w.db, inquiry), w.admin, "Budget frozen")  # the admin's reject
            w.db.commit()

    monkeypatch.setattr(FormSLAOrchestrator, "resolve_stage", racing_resolve)
    try:
        svc().approve(w.db, reload(w.db, inquiry), w.stage1.tier1)
        w.db.commit()
    except AppException as exc:
        assert exc.status_code in (409, 422), exc.status_code
        w.db.rollback()
    assert state["interleaved"], "approve resolves its stage through FormSLAOrchestrator.resolve_stage"

    after = reload(w.db, inquiry)
    assert after.state == "rejected"
    assert after.reject_reason == "Budget frozen"
    assert after.approved_at is None
    assert all(r.state == "draft" for r in rows_of(w.db, after))
    assert not _purchasing_notices(w)
