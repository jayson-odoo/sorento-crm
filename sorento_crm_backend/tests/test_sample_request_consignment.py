"""PS-SAMPLE-TRACKING Stage 2, red-first: the AutoCount consignment (CG) is the delivery.

Owner ruling 2 Nov (~21:40): "The sample delivery document is the consignment." The sample
team links one explicitly (no number or name matching); a live linked CG is the delivery, a
voided one undoes it. Plan: documentation/plans/project-sales/PLAN-sample-tracking-02nov.md.
"""
from __future__ import annotations

import uuid
from datetime import date

from .test_sample_requests_core import (  # noqa: F401  (world is a fixture)
    SR,
    _draft,
    _get,
    _move,
    _submitted,
    world,
)
from ._sample_request_seed import second_company

CG_DATE = date(2026, 11, 20)


def _cg(w, *, company_id=None, status="closed", doc_type="consignment", on=CG_DATE, debtor=None):
    from app.models.order import SalesOrder

    row = SalesOrder(
        id=str(uuid.uuid4()),
        company_id=company_id or w.company_id,
        so_number=f"CG-ZZT-{uuid.uuid4().hex[:8].upper()}",
        doc_type=doc_type,
        status=status,
        order_date=on,
        debtor_name=debtor or "ZZT consignee",
    )
    w.db.add(row)
    w.db.flush()
    return row


def _processing(w, **over):
    rid = _submitted(w, **over)
    assert _move(w, rid, "processing").status_code == 200
    return rid


def _link(w, rid, cg_id, user=None):
    return w.api.as_(user or w.coord).put(
        f"{SR}/{rid}/consignment", json={"consignment_order_id": cg_id}
    )


def _code(res):
    body = res.json()
    return body.get("code") or (body.get("error") or {}).get("code")


# ------------------------------------------------------------------ the picker


def test_picker_lists_live_consignments_of_the_company_only(world):
    rid = _processing(world)
    live = _cg(world, debtor="Picker Live Sdn Bhd")
    voided = _cg(world, status="cancelled")
    so = _cg(world, doc_type="sales_order")
    other = _cg(world, company_id=second_company(world.db))

    res = world.api.as_(world.coord).get(f"{SR}/{rid}/consignments", params={"q": "CG-ZZT"})
    assert res.status_code == 200, res.text
    ids = {r["id"] for r in res.json()}
    assert live.id in ids
    assert not ids & {voided.id, so.id, other.id}
    row = next(r for r in res.json() if r["id"] == live.id)
    assert row["so_number"] == live.so_number
    assert row["debtor_name"] == "Picker Live Sdn Bhd"
    assert row["order_date"] == CG_DATE.isoformat()


def test_picker_is_for_the_sample_team(world):
    rid = _processing(world)
    res = world.api.as_(world.sales).get(f"{SR}/{rid}/consignments")
    assert res.status_code == 403, res.text


# ------------------------------------------------------------------ linking delivers


def test_linking_a_live_consignment_delivers_on_its_date(world):
    rid = _processing(world)
    cg = _cg(world)
    res = _link(world, rid, cg.id)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "delivered"
    assert body["stage"] == "delivery"
    assert body["delivered_at"] == "2026-11-20"
    assert body["return_due"] == "2027-01-20"  # loan 2 months, the default
    assert body["consignment_no"] == cg.so_number
    assert body["consignment"] == {
        "id": cg.id,
        "so_number": cg.so_number,
        "order_date": "2026-11-20",
        "status": "closed",
    }


def test_linking_from_customer_confirmed_also_delivers(world):
    rid = _processing(world)
    assert _move(world, rid, "customer_confirmed", date="2026-11-18").status_code == 200
    res = _link(world, rid, _cg(world).id)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "delivered"


def test_salesperson_cannot_link(world):
    rid = _processing(world)
    assert _link(world, rid, _cg(world).id, user=world.sales).status_code == 403


def test_link_needs_processing_first(world):
    rid = _submitted(world)
    res = _link(world, rid, _cg(world).id)
    assert res.status_code == 409, res.text
    assert _code(res) == "SAMPLE_REQUEST_CONSIGNMENT_CLOSED"


def test_link_refuses_what_is_not_a_live_consignment_of_the_company(world):
    rid = _processing(world)
    for bad in (
        _cg(world, status="cancelled"),
        _cg(world, doc_type="sales_order"),
        _cg(world, company_id=second_company(world.db)),
    ):
        res = _link(world, rid, bad.id)
        assert res.status_code == 422, res.text
        assert _code(res) == "SAMPLE_REQUEST_CONSIGNMENT_INVALID"
    res = _link(world, rid, str(uuid.uuid4()))
    assert res.status_code == 422, res.text
    assert _get(world, rid)["status"] == "processing"


# ------------------------------------------------------------------ no manual Delivered with a CG


def test_manual_delivered_is_refused_while_a_consignment_is_linked(world):
    from app.models.order import SalesOrder
    from app.services import sample_request_service as svc

    rid = _processing(world)
    assert _move(world, rid, "customer_confirmed", date="2026-11-18").status_code == 200
    cg = _cg(world)
    assert _link(world, rid, cg.id).status_code == 200
    # The CG is voided: the request goes back, the link stays.
    world.db.query(SalesOrder).filter(SalesOrder.id == cg.id).update({"status": "cancelled"})
    svc.sync_consignment(world.db, world.company_id, cg.so_number)
    assert _get(world, rid)["status"] == "customer_confirmed"

    res = _move(world, rid, "delivered", date="2026-11-25")
    assert res.status_code == 409, res.text
    assert _code(res) == "SAMPLE_REQUEST_DELIVERED_BY_CONSIGNMENT"


def test_manual_delivered_still_works_without_a_consignment(world):
    """Edge: a board-only request, or goods that never went through AutoCount."""
    rid = _processing(world)
    assert _move(world, rid, "customer_confirmed", date="2026-11-18").status_code == 200
    assert _move(world, rid, "delivered", date="2026-11-25").status_code == 200


# ------------------------------------------------------------------ void / restore / unlink


def test_voided_consignment_reverts_and_a_restored_one_delivers_again(world):
    from app.models.order import SalesOrder
    from app.services import sample_request_service as svc

    rid = _processing(world)
    assert _move(world, rid, "customer_confirmed", date="2026-11-18").status_code == 200
    cg = _cg(world)
    assert _link(world, rid, cg.id).status_code == 200

    world.db.query(SalesOrder).filter(SalesOrder.id == cg.id).update({"status": "cancelled"})
    svc.sync_consignment(world.db, world.company_id, cg.so_number)
    back = _get(world, rid)
    assert back["status"] == "customer_confirmed"
    assert back["delivered_at"] is None and back["return_due"] is None
    assert back["consignment"]["status"] == "cancelled"

    world.db.query(SalesOrder).filter(SalesOrder.id == cg.id).update({"status": "closed"})
    svc.sync_consignment(world.db, world.company_id, cg.so_number)
    again = _get(world, rid)
    assert again["status"] == "delivered"
    assert again["delivered_at"] == "2026-11-20"


def test_void_reverts_to_processing_when_never_confirmed(world):
    from app.models.order import SalesOrder
    from app.services import sample_request_service as svc

    rid = _processing(world)
    cg = _cg(world)
    assert _link(world, rid, cg.id).status_code == 200
    world.db.query(SalesOrder).filter(SalesOrder.id == cg.id).update({"status": "cancelled"})
    svc.sync_consignment(world.db, world.company_id, cg.so_number)
    assert _get(world, rid)["status"] == "processing"


def test_sync_ignores_other_companies_and_unlinked_requests(world):
    from app.services import sample_request_service as svc

    rid = _processing(world)
    cg = _cg(world)
    # Nothing linked yet: a sync of that number changes nothing.
    svc.sync_consignment(world.db, world.company_id, cg.so_number)
    assert _get(world, rid)["status"] == "processing"


def test_unlink_undoes_the_delivery(world):
    rid = _processing(world)
    assert _move(world, rid, "customer_confirmed", date="2026-11-18").status_code == 200
    assert _link(world, rid, _cg(world).id).status_code == 200
    res = _link(world, rid, None)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "customer_confirmed"
    assert body["consignment"] is None
    assert body["consignment_no"] is None
    assert body["delivered_at"] is None


def test_manual_delivered_then_link_takes_the_consignment_date(world):
    rid = _processing(world)
    assert _move(world, rid, "customer_confirmed", date="2026-11-18").status_code == 200
    assert _move(world, rid, "delivered", date="2026-11-25").status_code == 200
    res = _link(world, rid, _cg(world).id)
    assert res.status_code == 200, res.text
    assert res.json()["delivered_at"] == "2026-11-20"


def test_cancelled_request_cannot_be_linked(world):
    d = _draft(world)
    assert _move(world, d["id"], "cancelled").status_code == 200
    res = _link(world, d["id"], _cg(world).id)
    assert res.status_code == 409, res.text
