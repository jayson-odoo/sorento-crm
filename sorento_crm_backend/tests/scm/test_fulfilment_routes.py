"""S7 over the wire: the stock-list upload and the loading plan.

The service suites (`test_supplier_inventory_service`, `test_loading_plan`) already prove the
snapshot semantics, the ranking and every deferral reason. Nothing is re-derived here. What is
proved is only what the WIRE has to carry: the supplier travels with the file, a Test writes
nothing, an unreadable file is refused rather than half-applied, the container count can be
changed without re-uploading, and the operator permission is required.
"""
from __future__ import annotations

import importlib.util
import uuid
from datetime import date
from io import BytesIO

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from tests.scm.conftest import as_user, requires_pg, seed_user
from tests.scm.test_outstanding_import_routes import as_company_user

pytestmark = requires_pg

MARKER = "ZZFULR"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
HEADER = ["型号", "品名", "包装好库存", "空瓷", "体积(cbm)", "备注"]


def _u() -> str:
    return str(uuid.uuid4())


def _workbook(rows, header=None) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(list(header or HEADER))
    for r in rows:
        ws.append(list(r))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _seed_container_sizes(db) -> None:
    spec = importlib.util.spec_from_file_location(
        "m336r", "alembic/versions/336_scm_supplier_inventory_loading_plan.py"
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.seed_container_sizes(db.connection())


def _seed(db) -> tuple[str, str]:
    """One supplier with one open purchase-order line. Returns (supplier_id, item_code)."""
    cat = ProductCategory(
        id=_u(), category_code=f"{MARKER}-C-{uuid.uuid4().hex[:6]}", category_name=f"{MARKER} cat"
    )
    uom = UnitOfMeasure(
        id=_u(), uom_code=f"{MARKER[:4]}{uuid.uuid4().hex[:6]}", uom_name=f"{MARKER} unit"
    )
    db.add_all([cat, uom])
    db.flush()
    code = f"{MARKER}-ITEM-{uuid.uuid4().hex[:6]}".upper()
    product = Product(
        id=_u(), product_code=code, product_name=code, category_id=cat.id,
        base_uom_id=uom.id, list_price=0, is_active=True, is_discontinued=False,
    )
    supplier = Supplier(
        id=_u(), supplier_code=f"{MARKER}-CR-{uuid.uuid4().hex[:6]}".upper(),
        supplier_name=f"{MARKER} supplier", is_active=True,
    )
    db.add_all([product, supplier])
    db.flush()
    po = PurchaseOrder(
        id=_u(), po_number=f"{MARKER}-PO-{uuid.uuid4().hex[:6]}".upper(),
        supplier_id=supplier.id, issue_date=date(2026, 1, 1), status="active",
    )
    db.add(po)
    db.flush()
    db.add(
        PurchaseOrderLine(
            id=_u(), purchase_order_id=po.id, product_id=product.id,
            qty_ordered=10, qty_received=0, line_status="open",
        )
    )
    db.flush()
    return str(supplier.id), code


def _held(db, supplier_id: str) -> int:
    return db.execute(
        text("SELECT count(*) FROM scm.supplier_inventory WHERE supplier_id = :s"),
        {"s": supplier_id},
    ).scalar()


# --------------------------------------------------------------------------- #
# the stock list
# --------------------------------------------------------------------------- #


def test_preview_says_what_it_would_replace_and_writes_nothing(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    supplier_id, code = _seed(db)

    r = TestClient(app).post(
        "/api/v1/scm/supplier-inventory/preview",
        files={"file": ("stock.xlsx", _workbook([[code, "a", 10, 4, 0.2, ""]]), _XLSX)},
        data={"supplier_id": supplier_id},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["readable"] is True
    assert body["rows_held_now"] == 0
    assert body["summary"]["qty_packed"] == 10
    assert _held(db, supplier_id) == 0, "preview wrote rows"


def test_apply_writes_the_snapshot(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    supplier_id, code = _seed(db)

    r = TestClient(app).post(
        "/api/v1/scm/supplier-inventory/apply",
        files={"file": ("stock.xlsx", _workbook([[code, "a", 10, 4, 0.2, ""]]), _XLSX)},
        data={"supplier_id": supplier_id},
    )

    assert r.status_code == 200, r.text
    assert r.json()["rows_written"] == 1
    assert _held(db, supplier_id) == 1


def test_validate_only_returns_the_verdict_and_writes_nothing(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    supplier_id, code = _seed(db)

    r = TestClient(app).post(
        "/api/v1/scm/supplier-inventory/apply?validate_only=true",
        files={"file": ("stock.xlsx", _workbook([[code, "a", 10, 0, 0.2, ""]]), _XLSX)},
        data={"supplier_id": supplier_id},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"valid", "errors", "warnings", "summary"}
    assert body["valid"] is True
    assert _held(db, supplier_id) == 0


def test_applying_a_file_with_no_packed_column_is_refused_and_names_it(scm_app):
    # It matters that this is a refusal: apply REPLACES, so a half-understood file would
    # delete the supplier's snapshot.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    supplier_id, code = _seed(db)

    r = TestClient(app).post(
        "/api/v1/scm/supplier-inventory/apply",
        files={"file": ("stock.xlsx", _workbook([[code, 3]], header=["型号", "空瓷"]), _XLSX)},
        data={"supplier_id": supplier_id},
    )

    assert r.status_code == 400, r.text
    assert "qty_packed" in r.json()["detail"]


def test_the_upload_requires_the_operator_permission(scm_app):
    # No role, so no grants. Nothing is seeded on purpose: the denial has to happen before the
    # file is read, which is the difference between refusing an upload and parsing it first.
    app, db, gcu, gcuk = scm_app
    as_user(app, gcu, gcuk, seed_user(db, None))

    r = TestClient(app).post(
        "/api/v1/scm/supplier-inventory/apply",
        files={"file": ("stock.xlsx", _workbook([["X", "a", 1, 0, 0.2, ""]]), _XLSX)},
        data={"supplier_id": str(uuid.uuid4())},
    )

    assert r.status_code == 403, r.text


def test_the_held_snapshot_is_readable_back(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    supplier_id, code = _seed(db)
    client = TestClient(app)
    client.post(
        "/api/v1/scm/supplier-inventory/apply",
        files={"file": ("stock.xlsx", _workbook([[code, "a", 10, 4, 0.2, ""]]), _XLSX)},
        data={"supplier_id": supplier_id},
    )

    r = client.get("/api/v1/scm/supplier-inventory", params={"supplier_id": supplier_id})

    assert r.status_code == 200, r.text
    rows = r.json()["rows"]
    assert [x["item_code"] for x in rows] == [code]
    assert rows[0]["matched"] is True


def test_unfinished_stock_has_its_own_list(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    supplier_id, code = _seed(db)
    client = TestClient(app)
    client.post(
        "/api/v1/scm/supplier-inventory/apply",
        files={"file": ("stock.xlsx", _workbook([[code, "a", 1, 140, 0.2, ""]]), _XLSX)},
        data={"supplier_id": supplier_id},
    )

    r = client.get("/api/v1/scm/supplier-inventory/unfinished", params={"supplier_id": supplier_id})

    assert r.status_code == 200, r.text
    assert r.json()["rows"][0]["qty_unfinished"] == 140


# --------------------------------------------------------------------------- #
# the loading plan
# --------------------------------------------------------------------------- #


def test_container_sizes_are_configured_not_hardcoded(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    _seed_container_sizes(db)

    r = TestClient(app).get("/api/v1/scm/container-sizes")

    assert r.status_code == 200, r.text
    sizes = r.json()["sizes"]
    assert sizes and all({"code", "cbm", "is_default"} <= set(s) for s in sizes)


def test_a_plan_is_created_with_its_lines_and_fill_rate(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    supplier_id, code = _seed(db)
    client = TestClient(app)
    client.post(
        "/api/v1/scm/supplier-inventory/apply",
        files={"file": ("stock.xlsx", _workbook([[code, "a", 10, 0, 1.0, ""]]), _XLSX)},
        data={"supplier_id": supplier_id},
    )

    r = client.post(
        "/api/v1/scm/loading-plans",
        json={"supplier_id": supplier_id, "container_count": 1, "container_cbm": 6},
    )

    assert r.status_code == 201, r.text
    body = r.json()
    assert body["capacity_cbm"] == 6
    assert body["planned_cbm"] == 6
    assert body["fill_rate"] == 1.0
    assert body["lines"][0]["status"] == "partial"
    assert body["lines"][0]["deferral_reason"] == "over_capacity"


def test_changing_the_container_count_re_runs_without_re_uploading(scm_app):
    # AC-E6, over the wire: same plan id, more capacity, no file in the request.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    supplier_id, code = _seed(db)
    client = TestClient(app)
    client.post(
        "/api/v1/scm/supplier-inventory/apply",
        files={"file": ("stock.xlsx", _workbook([[code, "a", 10, 0, 1.0, ""]]), _XLSX)},
        data={"supplier_id": supplier_id},
    )
    plan = client.post(
        "/api/v1/scm/loading-plans",
        json={"supplier_id": supplier_id, "container_count": 1, "container_cbm": 6},
    ).json()

    r = client.patch(f"/api/v1/scm/loading-plans/{plan['id']}", json={"container_count": 2})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == plan["id"]
    assert body["capacity_cbm"] == 12
    assert body["lines"][0]["status"] == "allocated"


def test_a_container_size_nobody_configured_is_a_400_not_a_silent_default(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    supplier_id, _ = _seed(db)

    r = TestClient(app).post(
        "/api/v1/scm/loading-plans",
        json={"supplier_id": supplier_id, "container_type": "45ZZ"},
    )

    assert r.status_code == 400, r.text


def test_a_plan_that_does_not_exist_is_a_404(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)

    r = TestClient(app).get(f"/api/v1/scm/loading-plans/{uuid.uuid4()}")

    assert r.status_code == 404


def test_a_plan_is_hard_deleted_with_its_lines(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    supplier_id, code = _seed(db)
    client = TestClient(app)
    client.post(
        "/api/v1/scm/supplier-inventory/apply",
        files={"file": ("stock.xlsx", _workbook([[code, "a", 10, 0, 1.0, ""]]), _XLSX)},
        data={"supplier_id": supplier_id},
    )
    plan = client.post(
        "/api/v1/scm/loading-plans",
        json={"supplier_id": supplier_id, "container_count": 1, "container_cbm": 6},
    ).json()

    r = client.delete(f"/api/v1/scm/loading-plans/{plan['id']}")

    assert r.status_code == 204
    assert db.execute(
        text("SELECT count(*) FROM scm.loading_plan_line WHERE plan_id = :p"), {"p": plan["id"]}
    ).scalar() == 0


def test_creating_a_plan_requires_the_operator_permission(scm_app):
    app, db, gcu, gcuk = scm_app
    as_user(app, gcu, gcuk, seed_user(db, None))

    r = TestClient(app).post(
        "/api/v1/scm/loading-plans",
        json={"supplier_id": str(uuid.uuid4()), "container_count": 1, "container_cbm": 6},
    )

    assert r.status_code == 403, r.text


def test_a_plan_with_no_containers_is_rejected_by_validation(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    supplier_id, _ = _seed(db)

    r = TestClient(app).post(
        "/api/v1/scm/loading-plans",
        json={"supplier_id": supplier_id, "container_count": 0, "container_cbm": 6},
    )

    assert r.status_code == 422, r.text
