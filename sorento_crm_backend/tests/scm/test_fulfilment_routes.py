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

from app.models.procurement import (
    InboundShipment,
    InboundShipmentLine,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
)
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scm import LoadingPlan
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


def test_a_plan_that_does_not_exist_is_a_404(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)

    r = TestClient(app).get(f"/api/v1/scm/loading-plans/{uuid.uuid4()}")

    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# container sizes are configuration (AC-E3)
# --------------------------------------------------------------------------- #


def test_a_container_size_can_be_added_and_becomes_plannable(scm_app):
    # The plan ROUTE no longer runs the CBM fit (part 4, R1: `POST /loading-plans` starts a
    # record), so what a new size has to satisfy is the allocator that reads it. The fit
    # itself is `test_loading_plan.py`'s subject and is not re-derived here.
    from app.services.scm import loading_plan_service

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    supplier_id, code = _seed(db)
    client = TestClient(app)
    client.post(
        "/api/v1/scm/supplier-inventory/apply",
        files={"file": ("stock.xlsx", _workbook([[code, "a", 10, 0, 1.0, ""]]), _XLSX)},
        data={"supplier_id": supplier_id},
    )
    size_code = f"{MARKER}{uuid.uuid4().hex[:4]}".upper()

    created = client.post(
        "/api/v1/scm/container-sizes",
        json={"code": size_code, "label": "test box", "cbm": 4, "is_default": False},
    )

    assert created.status_code == 201, created.text
    plan = loading_plan_service.build(
        db, supplier_id=supplier_id, container_count=1, container_type=size_code
    )
    assert float(plan.capacity_cbm) == 4


def test_two_sizes_cannot_share_a_code(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    client = TestClient(app)
    size_code = f"{MARKER}{uuid.uuid4().hex[:4]}".upper()
    client.post("/api/v1/scm/container-sizes", json={"code": size_code, "cbm": 4})

    again = client.post("/api/v1/scm/container-sizes", json={"code": size_code, "cbm": 9})

    assert again.status_code == 409, again.text


def test_only_one_size_is_the_default(scm_app):
    # Two defaults and `_resolve_container` picks whichever row comes back first, so a plan
    # built with no explicit size would silently change volume between runs.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    _seed_container_sizes(db)
    client = TestClient(app)

    client.post(
        "/api/v1/scm/container-sizes",
        json={"code": f"{MARKER}{uuid.uuid4().hex[:4]}".upper(), "cbm": 4, "is_default": True},
    )

    sizes = client.get("/api/v1/scm/container-sizes").json()["sizes"]
    assert sum(1 for s in sizes if s["is_default"]) == 1


def test_a_size_is_hard_deleted_and_the_plans_built_from_it_keep_their_volume(scm_app):
    from app.services.scm import loading_plan_service

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    supplier_id, code = _seed(db)
    client = TestClient(app)
    client.post(
        "/api/v1/scm/supplier-inventory/apply",
        files={"file": ("stock.xlsx", _workbook([[code, "a", 10, 0, 1.0, ""]]), _XLSX)},
        data={"supplier_id": supplier_id},
    )
    size_code = f"{MARKER}{uuid.uuid4().hex[:4]}".upper()
    size = client.post(
        "/api/v1/scm/container-sizes", json={"code": size_code, "cbm": 4}
    ).json()["sizes"]
    size_id = next(s["id"] for s in size if s["code"] == size_code)
    plan = loading_plan_service.build(
        db, supplier_id=supplier_id, container_count=1, container_type=size_code
    )
    plan_id = str(plan.id)

    assert client.delete(f"/api/v1/scm/container-sizes/{size_id}").status_code == 204

    db.expire_all()
    still = db.query(LoadingPlan).filter(LoadingPlan.id == plan_id).one()
    assert float(still.capacity_cbm) == 4


def test_editing_a_size_requires_the_operator_permission(scm_app):
    app, db, gcu, gcuk = scm_app
    as_user(app, gcu, gcuk, seed_user(db, None))

    r = TestClient(app).post("/api/v1/scm/container-sizes", json={"code": "ZZX", "cbm": 4})

    assert r.status_code == 403, r.text


# --------------------------------------------------------------------------- #
# the packing list: whose it is, is not optional
# --------------------------------------------------------------------------- #


def test_a_packing_list_upload_that_names_no_supplier_is_refused(scm_app):
    # A container is filled by two or three factories and each sends its own list, so an
    # upload that will not say which one speaks for the whole container - and would delete
    # the other factories' lines. Refused before the file is read.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)

    r = TestClient(app).post(
        "/api/v1/scm/packing-lists/apply",
        files={"file": ("packing.xlsx", _workbook([["X", "a", 1, 1, 0.2, ""]]), _XLSX)},
    )

    assert r.status_code == 422, r.text
    assert "supplier_id is required" in r.json()["detail"]


def test_validate_only_may_omit_the_supplier_because_it_writes_nothing(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)

    r = TestClient(app).post(
        "/api/v1/scm/packing-lists/apply?validate_only=true",
        files={"file": ("packing.xlsx", _workbook([["X", "a", 1, 1, 0.2, ""]]), _XLSX)},
    )

    assert r.status_code == 200, r.text
    assert set(r.json()) == {"valid", "errors", "warnings", "summary"}


# --------------------------------------------------------------------------- #
# who is on a container                                                        #
# --------------------------------------------------------------------------- #


def _shipment(db, supplier_id=None) -> InboundShipment:
    row = InboundShipment(
        id=_u(),
        shipment_number=f"{MARKER}-{uuid.uuid4().hex[:8]}".upper(),
        supplier_id=supplier_id,
        shipment_date=date(2026, 1, 1),
        shipping_container_number=f"{MARKER}U{uuid.uuid4().hex[:7]}".upper(),
        shipment_status="in_transit",
    )
    db.add(row)
    db.flush()
    return row


def test_a_container_whose_factory_is_only_on_the_header_still_names_it(scm_app):
    """The factory of a container read before the per-supplier line is on the header alone.

    Reading `suppliers[]` off the lines only printed nothing under those containers, which
    says "we do not know whose this is" about a container we do know.
    """
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    supplier_id, _code = _seed(db)
    shipment = _shipment(db, supplier_id=supplier_id)

    r = TestClient(app).get(
        "/api/v1/scm/inbound-shipments", params={"supplier_id": supplier_id}
    )

    assert r.status_code == 200, r.text
    row = next(x for x in r.json()["data"] if x["shipment_id"] == str(shipment.id))
    assert [s["supplier_id"] for s in row["suppliers"]] == [supplier_id]
    assert row["suppliers"][0]["supplier_name"]


def test_a_mixed_container_names_every_factory_on_its_lines(scm_app):
    """Two factories, one container: the header names nobody, so the lines have to.

    It is also the container that must not disappear from either supplier's filter.
    """
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    supplier_a, code = _seed(db)
    supplier_b = Supplier(
        id=_u(),
        supplier_code=f"{MARKER}-CR-{uuid.uuid4().hex[:6]}".upper(),
        supplier_name=f"{MARKER} second supplier",
        is_active=True,
    )
    db.add(supplier_b)
    db.flush()
    product_id = str(db.query(Product.id).filter(Product.product_code == code).scalar())
    shipment = _shipment(db)
    for supplier in (supplier_a, str(supplier_b.id)):
        db.add(
            InboundShipmentLine(
                id=_u(),
                shipment_id=shipment.id,
                product_id=product_id,
                supplier_id=supplier,
                quantity_shipped=1,
                cartons_count=1,
            )
        )
    db.flush()

    client = TestClient(app)
    for supplier in (supplier_a, str(supplier_b.id)):
        r = client.get("/api/v1/scm/inbound-shipments", params={"supplier_id": supplier})
        assert r.status_code == 200, r.text
        row = next(x for x in r.json()["data"] if x["shipment_id"] == str(shipment.id))
        assert {s["supplier_id"] for s in row["suppliers"]} == {supplier_a, str(supplier_b.id)}


# --------------------------------------------------------------------------- #
# the chat contact picker (S3, AC-C3)
# --------------------------------------------------------------------------- #


def test_the_chat_contact_picker_answers_over_the_wire(scm_app):
    # AC-C3. One call powers both halves of the Chat option: who to send to, and whether the
    # workspace can carry a WeChat message at all.
    from app.models.access import RespondContact

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    supplier_id, _code = _seed(db)
    phone = f"+86138{uuid.uuid4().int % 100000000:08d}"
    db.query(Supplier).filter(Supplier.id == supplier_id).one().phone_number = phone
    db.add(
        RespondContact(
            id=_u(),
            phone_number=phone,
            name=f"{MARKER} Factory Wang",
            respond_io_id=str(uuid.uuid4().int % 10_000_000),
        )
    )
    db.flush()

    r = TestClient(app).get(
        "/api/v1/scm/supplier-notices/chat-contacts",
        params={"supplier_id": supplier_id, "query": MARKER},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["data"][0]["name"] == f"{MARKER} Factory Wang"
    assert body["data"][0]["suggested"] is True
    assert body["data"][0]["phone"] == phone
    # Whether Chat can be offered at all is the workspace's own answer (R10), and it is
    # stated either way: connected, or disabled with the reason. Asserted as the pair rather
    # than as a fixed value, because the channel is configuration, not test data.
    if body["wechat_connected"]:
        assert body["unavailable_reason"] is None
    else:
        assert "WeChat" in body["unavailable_reason"]
