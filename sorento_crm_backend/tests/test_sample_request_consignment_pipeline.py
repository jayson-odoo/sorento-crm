"""PS-SAMPLE-TRACKING: the two re-sync hooks, driven through their real pipelines (review B1).

- The consignment ingest (`AutocountCancelIngestService._project_consignment`): a CG voided in
  AutoCount takes its linked sample request back to Stage 1; restored, it delivers again.
- The order tracking import (`OrderService.import_excel_tracking`): an Overall Tracking row for
  the CG's number moves the linked request's delivered date to the tracked one.
- Neither hook may break its host: a sample-request error is logged, the import / CG still lands.

Reuses the AutoCount ingest suite's `env` and CG builders. Every record is fake.
"""
from __future__ import annotations

from datetime import date
from io import BytesIO

import pytest
from openpyxl import Workbook

from app.models.order import Order
from app.models.sample_request import SampleRequest
from app.services import project_seed_service
from app.services import sample_request_service as svc

from tests.test_ingest_autocount_consignments import CG_INGEST, _cg, _cg_line, _order
from tests.test_ingest_autocount_do_grn import _records, env  # noqa: F401 - env is a fixture

SR_DATE = date(2026, 9, 25)


def _linked_request(env) -> SampleRequest:
    """A Customer confirmed request linked to the ingested CG ZZCG-0001 (so: Delivered)."""
    project_seed_service.run(env.db, company_id=env.company)
    req = SampleRequest(
        company_id=env.company,
        customer_name="ZZT pipeline customer",
        project_title="ZZT pipeline project",
        delivery_date=SR_DATE,
        confirmed_at=SR_DATE,
    )
    env.db.add(req)
    env.db.flush()
    svc._set_status(env.db, req, svc.CUSTOMER_CONFIRMED)
    cg = _order(env)
    svc.link_consignment(env.db, req, actor=svc.Actor(can_process=True), consignment_order_id=cg.id)
    env.db.commit()
    assert svc.status_key(env.db, req) == svc.DELIVERED
    assert req.delivered_at == date(2026, 10, 1)  # the CG's DocDate: no tracking row yet
    return req


def _fresh(env, req) -> SampleRequest:
    env.db.expire_all()
    return env.db.get(SampleRequest, req.id)


# ------------------------------------------------------------------ the consignment ingest


def test_a_cg_voided_in_autocount_takes_the_request_back(env):
    env.post(CG_INGEST, [_cg(details=[_cg_line(981001, transferred=0)])])
    req = _linked_request(env)

    res = env.post(CG_INGEST, [_cg(details=[_cg_line(981001, transferred=0)], cancelled="T",
                                   modified="2026-10-05T10:00:00.000")])
    assert _records(res)["db1:CSGN:980001"]["outcome"] != "failed"
    back = _fresh(env, req)
    assert svc.status_key(env.db, back) == svc.CUSTOMER_CONFIRMED
    assert back.delivered_at is None and back.return_due is None

    env.post(CG_INGEST, [_cg(details=[_cg_line(981001, transferred=0)], cancelled="F",
                             modified="2026-10-06T10:00:00.000")])
    again = _fresh(env, req)
    assert svc.status_key(env.db, again) == svc.DELIVERED
    assert again.delivered_at == date(2026, 10, 1)


def test_a_sample_request_error_never_fails_the_cg(env, monkeypatch):
    env.post(CG_INGEST, [_cg(details=[_cg_line(981001, transferred=0)])])
    _linked_request(env)

    def boom(*_a, **_k):
        raise KeyError("delivered")

    monkeypatch.setattr(svc, "_resync", boom)
    res = env.post(CG_INGEST, [_cg(details=[_cg_line(981001, transferred=0)], cancelled="T",
                                   modified="2026-10-05T10:00:00.000")])
    assert _records(res)["db1:CSGN:980001"]["outcome"] != "failed"
    assert _order(env).status == "cancelled"


# ------------------------------------------------------------------ the order tracking import


def _tracking_workbook(number: str, delivered: date) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    master = wb.create_sheet("Master")
    master.append(["Doc. No.", "Date"])
    master.append([number, date(2026, 10, 1)])
    tracking = wb.create_sheet("Overall Tracking")
    tracking.append(["Doc Number", "Delivery Date"])
    tracking.append([number, delivered])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _import(env, number: str, delivered: date) -> dict:
    from app.services.order_service import OrderService

    return OrderService(env.db).import_excel_tracking(
        _tracking_workbook(number, delivered), "11111111-1111-1111-1111-111111111111"
    )


def test_the_tracking_import_moves_the_delivered_date_to_the_tracked_one(env):
    env.post(CG_INGEST, [_cg(details=[_cg_line(981001, transferred=0)])])
    req = _linked_request(env)

    result = _import(env, "ZZCG-0001", date(2026, 10, 4))
    tracked = env.db.query(Order).filter(Order.order_number == "ZZCG-0001").one()
    assert tracked.actual_delivery_date is not None, result
    after = _fresh(env, req)
    assert after.delivered_at == date(2026, 10, 4)
    assert after.return_due == date(2026, 12, 4)  # the default 2-month loan
    assert svc.serialize_detail(env.db, after)["consignment"]["delivered_source"] == "tracking"


def test_a_sample_request_error_never_fails_the_tracking_import(env, monkeypatch):
    env.post(CG_INGEST, [_cg(details=[_cg_line(981001, transferred=0)])])
    _linked_request(env)

    def boom(*_a, **_k):
        raise KeyError("delivered")

    monkeypatch.setattr(svc, "_resync", boom)
    result = _import(env, "ZZCG-0001", date(2026, 10, 4))
    assert not [e for e in result.get("errors", []) if "Database error" in str(e)], result
    tracked = env.db.query(Order).filter(Order.order_number == "ZZCG-0001").one()
    assert tracked.actual_delivery_date is not None


@pytest.mark.parametrize("terminal", ["cancelled"])
def test_a_resync_never_pulls_a_closed_request_back_to_delivered(env, terminal):
    """Review S2: only a request in the consignment-open set follows its CG."""
    env.post(CG_INGEST, [_cg(details=[_cg_line(981001, transferred=0)])])
    req = _linked_request(env)
    env.post(CG_INGEST, [_cg(details=[_cg_line(981001, transferred=0)], cancelled="T",
                             modified="2026-10-05T10:00:00.000")])
    back = _fresh(env, req)
    svc._set_status(env.db, back, terminal)
    env.db.commit()

    env.post(CG_INGEST, [_cg(details=[_cg_line(981001, transferred=0)], cancelled="F",
                             modified="2026-10-06T10:00:00.000")])
    assert svc.status_key(env.db, _fresh(env, req)) == terminal
