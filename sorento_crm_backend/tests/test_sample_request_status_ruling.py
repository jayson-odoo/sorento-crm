"""SAMPLE-REQUEST-V2, owner ruling 11 Nov ~19:55 (red-first): the sample request flow is
Submitted -> Processing -> Delivered, Cancel stays.

1. "Customer confirmed" is removed (status, move, button).
2. Delivered is set ONLY by linking the AutoCount consignment; nobody presses Delivered or types
   a delivered date.
3. A voided consignment STAYS voided: the request goes back to Processing, unlinked, until a new
   consignment is linked, and a "restored" voided consignment never delivers it again. The
   voided one stays in the request's History.
Existing customer_confirmed rows move to Processing with a History entry (migration
srv2_0002_status_ruling).
"""
from __future__ import annotations

import importlib.util
import pathlib

from app.models.audit import AuditLog
from app.models.sample_request import SampleRequest
from app.models.status import Status, StatusTransition
from app.services import sample_request_service as svc

from .test_sample_request_consignment import _cg, _code, _link, _processing
from .test_sample_requests_core import _get, _move, world  # noqa: F401  (fixture)


def _key(w, rid):
    return _get(w, rid)["status"]


# ------------------------------------------------------------------ 1. Customer confirmed is gone


def test_the_graph_has_no_customer_confirmed_move(world):
    w = world
    rid = _processing(w)
    res = _move(w, rid, "customer_confirmed", date="2026-11-18")
    assert res.status_code in (409, 422), res.text
    assert _key(w, rid) == "processing"


def test_a_fresh_install_seeds_no_customer_confirmed(world):
    edges = (
        world.db.query(StatusTransition)
        .join(Status, Status.id == StatusTransition.to_status_id)
        .filter(StatusTransition.entity_type == "sample_request", Status.key == "customer_confirmed")
        .count()
    )
    assert edges == 0


# ------------------------------------------------------------------ 2. Delivered only by the consignment


def test_nobody_marks_delivered_by_hand(world):
    w = world
    rid = _processing(w)
    res = _move(w, rid, "delivered", date="2026-11-20")
    assert res.status_code == 409, res.text
    assert _code(res) == "SAMPLE_REQUEST_DELIVERED_BY_CONSIGNMENT"
    assert _key(w, rid) == "processing"


def test_linking_a_live_consignment_from_processing_delivers(world):
    w = world
    rid = _processing(w)
    res = _link(w, rid, _cg(w).id)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "delivered"


# ------------------------------------------------------------------ 3. a voided consignment stays voided


def test_a_voided_consignment_unlinks_and_takes_the_request_back_to_processing(world):
    w = world
    rid = _processing(w)
    cg = _cg(w)
    assert _link(w, rid, cg.id).status_code == 200
    cg.status = "cancelled"
    w.db.flush()
    svc.sync_consignment(w.db, w.company_id, cg.so_number)
    got = _get(w, rid)
    assert got["status"] == "processing"
    assert got["delivered_at"] is None
    assert (got.get("consignment") or {}).get("id") in (None, "")
    row = w.db.get(SampleRequest, rid)
    assert row.consignment_order_id is None


def test_a_restored_voided_consignment_never_delivers_again(world):
    w = world
    rid = _processing(w)
    cg = _cg(w)
    assert _link(w, rid, cg.id).status_code == 200
    cg.status = "cancelled"
    w.db.flush()
    svc.sync_consignment(w.db, w.company_id, cg.so_number)
    cg.status = "closed"
    w.db.flush()
    svc.sync_consignment(w.db, w.company_id, cg.so_number)
    assert _key(w, rid) == "processing"


def test_a_voided_consignment_cannot_be_linked_again(world):
    w = world
    rid = _processing(w)
    res = _link(w, rid, _cg(w, status="cancelled").id)
    assert res.status_code == 422, res.text


def test_a_new_consignment_delivers_after_the_void(world):
    w = world
    rid = _processing(w)
    first = _cg(w)
    assert _link(w, rid, first.id).status_code == 200
    first.status = "cancelled"
    w.db.flush()
    svc.sync_consignment(w.db, w.company_id, first.so_number)
    second = _cg(w)
    res = _link(w, rid, second.id)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "delivered"


def test_the_void_is_in_the_requests_history(world):
    w = world
    rid = _processing(w)
    cg = _cg(w)
    assert _link(w, rid, cg.id).status_code == 200
    cg.status = "cancelled"
    w.db.flush()
    svc.sync_consignment(w.db, w.company_id, cg.so_number)
    w.db.flush()
    rows = (
        w.db.query(AuditLog)
        .filter(AuditLog.entity_id == rid, AuditLog.description.ilike(f"%{cg.so_number}%voided%"))
        .count()
    )
    assert rows >= 1


# ------------------------------------------------------------------ existing rows (migration)


def _migration():
    path = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions" / "srv2_0002_status_ruling.py"
    spec = importlib.util.spec_from_file_location("srv2_0002_status_ruling", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_existing_customer_confirmed_rows_move_to_processing_with_a_history_entry(world):
    w = world
    rid = _processing(w)
    # A row as the old graph left it.
    confirmed = (
        w.db.query(Status)
        .filter(Status.entity_type == "sample_request", Status.key == "customer_confirmed", Status.scope_id.is_(None))
        .first()
    )
    if confirmed is None:
        confirmed = Status(entity_type="sample_request", scope_id=None, key="customer_confirmed",
                           label="Customer confirmed", sort_order=3)
        w.db.add(confirmed)
        w.db.flush()
    w.db.get(SampleRequest, rid).status_id = confirmed.id
    w.db.flush()
    mig = _migration()
    assert mig.retire_customer_confirmed(w.db.connection()) >= 1
    w.db.expire_all()
    assert _key(w, rid) == "processing"
    assert (
        w.db.query(AuditLog)
        .filter(AuditLog.entity_id == rid, AuditLog.description.ilike("%Customer confirmed%"))
        .count()
        == 1
    )
