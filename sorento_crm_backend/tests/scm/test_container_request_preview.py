"""R9 - the request preview, the exact document Send would produce (AC-E2, AC-E3, AC-E6).

`POST /api/v1/scm/container-requests/preview` is the gear's own read (`build`'s permission,
`scm.dashboard.view`): it runs the SAME two builders `request_and_notify` does -
`supplier_notice_service._request_pack` then `_request_sheet` - and writes nothing, so the
document Ms Tee previews and the one a Send freezes into `sheet_json` can never disagree.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.models.scm import LoadingPlan
from app.models.supplier_notice import SupplierNotice
from app.services.scm import supplier_notice_service
from tests.scm.conftest import requires_pg
from tests.scm.test_loading_plan import World
from tests.scm.test_outstanding_import_routes import as_company_user

pytestmark = requires_pg

PREVIEW_URL = "/api/v1/scm/container-requests/preview"
SEND_URL = "/api/v1/scm/container-requests"


def _edits_url(plan_id: str) -> str:
    return f"/api/v1/scm/loading-plans/{plan_id}/edits"


@pytest.fixture(autouse=True)
def _no_pdf_no_storage(monkeypatch):
    """This suite is about the sheet model, not WeasyPrint - same stub as S8's own suite."""
    monkeypatch.setattr(
        supplier_notice_service, "render_document", lambda html: b"%PDF-1.4 stub"
    )
    monkeypatch.setattr(
        supplier_notice_service, "_store", lambda data, filename: ("s3", f"exports/test/{filename}")
    )


def _plan(db, w: World) -> str:
    # An address on file, or a send 422s `no_recipients` (AC-C2) - these tests are about the
    # document, not who it is addressed to.
    w.supplier.email = f"ZZCRP-supplier-{uuid.uuid4().hex[:8]}@example.test"
    db.flush()
    plan = LoadingPlan(
        id=str(uuid.uuid4()),
        supplier_id=str(w.supplier.id),
        status="planning",
        document_kind="stock_list",
        line_edits={},
    )
    db.add(plan)
    db.flush()
    return str(plan.id)


def test_the_preview_equals_the_model_a_send_freezes(scm_app):
    # AC-E2: the same document, whichever call built it.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    plan_id = _plan(db, w)
    client = TestClient(app)
    body = {"plan_id": plan_id, "lines": [{"product_id": str(w.product("A").id), "qty": 40}]}

    preview = client.post(PREVIEW_URL, json=body)
    assert preview.status_code == 200, preview.text

    sent = client.post(SEND_URL, json=body)
    assert sent.status_code == 201, sent.text
    notice = db.query(SupplierNotice).filter(SupplierNotice.loading_plan_id == plan_id).one()

    assert preview.json() == notice.sheet_json


def test_the_preview_writes_nothing(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    plan_id = _plan(db, w)

    r = TestClient(app).post(
        PREVIEW_URL,
        json={"plan_id": plan_id, "lines": [{"product_id": str(w.product("A").id), "qty": 40}]},
    )

    assert r.status_code == 200, r.text
    assert (
        db.query(SupplierNotice).filter(SupplierNotice.loading_plan_id == plan_id).count() == 0
    )
    # S6, review round 1: a preview is a read, and the plan it read from must show it - not
    # just "no notice row", but the plan itself still `planning` and never `sent_at`.
    plan = db.query(LoadingPlan).filter(LoadingPlan.id == plan_id).one()
    assert plan.status == "planning"
    assert plan.sent_at is None


def test_the_preview_keeps_a_zeroed_row_with_its_row_key_and_no_highlight(scm_app):
    # B1, review round 1: `requestLinesFrom` (FE) drops a row edited down to 0 before it
    # reaches Send/the document, but the PREVIEW must not - a debounced refetch that dropped
    # the line lost the row's `row_key` too, so the input stopped being editable (or, on the
    # no-file document, the row vanished outright). `ContainerRequestPreviewLine` relaxes qty
    # to `ge=0` for exactly this call; `ContainerRequestLine` (Send) stays `gt=0`.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    plan_id = _plan(db, w)
    product_a = str(w.product("A").id)

    r = TestClient(app).post(
        PREVIEW_URL,
        json={"plan_id": plan_id, "lines": [{"product_id": product_a, "qty": 0}]},
    )

    assert r.status_code == 200, r.text
    sheet = r.json()
    assert len(sheet["rows"]) == 1
    row = sheet["rows"][0]
    assert row["row_key"] == product_a
    assert all(cell["fill"] is None for cell in row["cells"])


def test_sending_still_refuses_a_zero_qty_line(scm_app):
    # Send keeps `gt=0` (`ContainerRequestLine`): the preview's relaxed bound is scoped to
    # the preview endpoint only, per the plan.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    plan_id = _plan(db, w)

    r = TestClient(app).post(
        SEND_URL,
        json={"plan_id": plan_id, "lines": [{"product_id": str(w.product("A").id), "qty": 0}]},
    )

    assert r.status_code == 422, r.text


def test_the_preview_404s_on_another_companys_plan(scm_app):
    # S4, review round 1: `container_request_service._plan_or_404`'s plain ORM lookup is
    # already company-scoped by the global `do_orm_execute` listener
    # (`app.services.company_scope`) - this pins that, rather than adding a second, redundant
    # predicate with no evidence of a gap.
    from app.models.company import Company

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    plan_id = _plan(db, w)

    other = str(uuid.uuid4())
    db.add(
        Company(
            id=other,
            name=f"ZZCRP other company {other[:8]}",
            code=f"ZZCRP-{uuid.uuid4().hex[:6]}".upper()[:50],
            is_active=True,
        )
    )
    db.flush()
    plan = db.query(LoadingPlan).filter(LoadingPlan.id == plan_id).one()
    plan.company_id = other
    db.add(plan)
    db.flush()

    r = TestClient(app).post(
        PREVIEW_URL,
        json={"plan_id": plan_id, "lines": [{"product_id": str(w.product("A").id), "qty": 40}]},
    )

    assert r.status_code == 404, r.text


def test_the_preview_highlights_the_row_it_asked_for(scm_app):
    # AC-E3. Every row this endpoint returns was, by construction, an ask (a `ContainerRequestLine`
    # cannot name a zero qty), so what is checkable here is that the asked row carries our
    # highlight and no red font; `test_only_the_asked_row_is_highlighted`
    # (test_container_request_xlsx.py) and `test_our_highlight_replaces_their_fills_and_red_figures`
    # (test_supplier_document_model.py) cover the "some rows are NOT highlighted" half, which
    # needs a retained stock list naming more products than were asked for.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    plan_id = _plan(db, w)

    r = TestClient(app).post(
        PREVIEW_URL,
        json={"plan_id": plan_id, "lines": [{"product_id": str(w.product("A").id), "qty": 12}]},
    )

    assert r.status_code == 200, r.text
    sheet = r.json()
    assert len(sheet["rows"]) == 1
    row = sheet["rows"][0]
    assert row["cells"][-2]["value"] == 12  # qty to load, second-last column
    assert all(cell["fill"] == "highlight" and cell["red"] is False for cell in row["cells"])


def test_the_preview_carries_the_remark_and_a_later_edit_leaves_a_sent_notice_alone(scm_app):
    # AC-E6.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    plan_id = _plan(db, w)
    client = TestClient(app)
    product_a = str(w.product("A").id)

    client.put(
        _edits_url(plan_id),
        json={"line_edits": {product_a: {"qty": 40, "remark": "pack in 2 cartons"}}},
    )
    body = {"plan_id": plan_id, "lines": [{"product_id": product_a, "qty": 40}]}

    preview = client.post(PREVIEW_URL, json=body)
    assert preview.status_code == 200, preview.text
    sheet = preview.json()
    assert sheet["columns"][-1] == {"label": "备注", "label_en": "Remarks", "field": "line_remark"}
    assert sheet["rows"][0]["cells"][-1]["value"] == "pack in 2 cartons"

    sent = client.post(SEND_URL, json=body)
    assert sent.status_code == 201, sent.text
    notice = db.query(SupplierNotice).filter(SupplierNotice.loading_plan_id == plan_id).one()
    assert notice.sheet_json["rows"][0]["cells"][-1]["value"] == "pack in 2 cartons"

    # Editing the plan afterwards must not change the document already sent.
    client.put(
        _edits_url(plan_id),
        json={"line_edits": {product_a: {"qty": 40, "remark": "changed my mind"}}},
    )
    db.refresh(notice)
    assert notice.sheet_json["rows"][0]["cells"][-1]["value"] == "pack in 2 cartons"


def test_a_cancelled_plan_refuses_the_preview(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    plan_id = _plan(db, w)
    client = TestClient(app)
    client.post(f"/api/v1/scm/loading-plans/{plan_id}/cancel")

    r = client.post(
        PREVIEW_URL,
        json={"plan_id": plan_id, "lines": [{"product_id": str(w.product("A").id), "qty": 40}]},
    )

    assert r.status_code == 409, r.text
    assert r.json()["code"] == "plan_cancelled"
