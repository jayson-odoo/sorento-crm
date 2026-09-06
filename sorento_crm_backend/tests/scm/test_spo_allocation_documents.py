"""The SPO document list + form view HTTP contract (PLAN-spo-investigation-grid.md S2).

`GET /spo-allocations/documents` and `GET /spo-allocations/documents/{spo_number}`
(UAC AC-11..AC-16), test-first. Bulk delete (AC-16b) has no route of its own (review
B1) - it rides the pending-actions registry's `spo_document.delete`
(`app/services/record_actions.py`), so it is exercised here at the SERVICE method the
handler calls, unchanged.

**One rule, fifth reader.** `outstanding` line membership is
`spo_supply.open_incoming_clauses()` AND balance > 0 - this suite never restates those
clauses; it only seeds a line per exclusion reason and asserts the route's own verdict
(AC-12).

Seeding. Every product, warehouse, supplier, shipment and role is created by this suite
under the `ZZT` marker, inside the `scm_app` savepoint - nothing is borrowed with
`LIMIT 1` (CI's database is empty). Every list query is scoped with `query=<product
code>` so a shared, non-empty prod-copy database cannot leak real rows into a count this
suite asserts on.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import quote

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.inventory import Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.procurement import (
    InboundShipment, PurchaseOrder, PurchaseOrderLine, SPOAllocation, Supplier,
)
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import (
    INQUIRY_RAISED, IV_ORDER_BACK, OrderInquiry, OrderInquiryLink, OrderInquiryRow,
    ProjectSalesOrder, ProjectSalesOrderLine, SO_STATUS_DRAFT,
)
from app.models.projects import Project
from app.models.scm import OrderLinkClaim
from app.models.user import UserPermission, UserRole, UserRoleAssignment, UserRolePermission
from app.services.scm.spo_conversion_service import SOURCE_SYSTEM
from tests._pg_fixture import unique_code
from tests.scm.conftest import requires_pg
from tests.scm.test_outstanding_import_routes import as_company_user

pytestmark = requires_pg

DOCUMENTS_URL = "/api/v1/procurement/spo-allocations/documents"
VIEW_PERMISSION = "procurement.spo_allocations.view"
DELETE_PERMISSION = "procurement.spo_allocations.delete"


def _u() -> str:
    return str(uuid.uuid4())


# --------------------------------------------------------------------------------- #
# principal + permission grants
# --------------------------------------------------------------------------------- #


def _grant(db: Session, uid: str, slug: str) -> None:
    """Give `uid` the permission named `slug`, through a role this test owns.

    Get-or-create on the PERMISSION row: on a migrated database the slug already
    exists (seeded by `app.rbac.permission_registry`), and on a bare one it does not,
    so either way the grant resolves.
    """
    role = UserRole(id=_u(), slug=unique_code("spodocrole"), name=unique_code("SPO doc role"))
    db.add(role)
    db.flush()

    perm = db.query(UserPermission).filter(UserPermission.slug == slug).one_or_none()
    if perm is None:
        perm = UserPermission(id=_u(), slug=slug, name=slug)
        db.add(perm)
        db.flush()

    db.add(UserRolePermission(id=_u(), role_id=role.id, permission_id=perm.id))
    db.add(UserRoleAssignment(id=_u(), user_id=uid, role_id=role.id))
    db.flush()


def _client(scm_app, *, view: bool = True, delete: bool = False) -> tuple[TestClient, Session]:
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk, role=None)
    uid = app.dependency_overrides[gcu]()["id"]
    if view:
        _grant(db, uid, VIEW_PERMISSION)
    if delete:
        _grant(db, uid, DELETE_PERMISSION)
    return TestClient(app), db


# --------------------------------------------------------------------------------- #
# catalogue
# --------------------------------------------------------------------------------- #


def _chain(db: Session) -> dict:
    cat = ProductCategory(
        id=_u(), category_code=unique_code("CAT")[:40], category_name=unique_code("cat")
    )
    uom = UnitOfMeasure(id=_u(), uom_name=unique_code("uom"), uom_code=unique_code("U")[:20])
    db.add_all([cat, uom])
    db.flush()
    return {"category_id": cat.id, "uom_id": uom.id}


def _product(db: Session, chain: dict, code: str | None = None) -> Product:
    product = Product(
        id=_u(),
        product_code=code or unique_code("SKU"),
        product_name=unique_code("prod"),
        category_id=chain["category_id"],
        base_uom_id=chain["uom_id"],
        list_price=0,
    )
    db.add(product)
    db.flush()
    return product


def _warehouse(
    db: Session, *, active: bool = True, planning: bool = False, pool_of: str | None = None
) -> Warehouse:
    warehouse = Warehouse(
        id=_u(),
        warehouse_code=unique_code("WH"),
        warehouse_name=unique_code("wh"),
        is_active=active,
        fulfilment_planning=planning,
        pool_warehouse_id=pool_of,
    )
    db.add(warehouse)
    db.flush()
    return warehouse


def _supplier(db: Session, name: str | None = None) -> Supplier:
    supplier = Supplier(id=_u(), supplier_code=unique_code("SUP"), supplier_name=name or unique_code("sup"))
    db.add(supplier)
    db.flush()
    return supplier


def _shipment(
    db: Session,
    *,
    supplier: Supplier | None = None,
    eta_delay: date | None = None,
    estimated: date | None = None,
    actual: date | None = None,
) -> InboundShipment:
    shipment = InboundShipment(
        id=_u(),
        shipment_number=unique_code("SHP")[:50],
        supplier_id=supplier.id if supplier else None,
        shipment_date=date(2026, 7, 1),
        eta_delay_date=eta_delay,
        estimated_arrival_date=estimated,
        actual_arrival_date=actual,
        shipment_status="in_transit" if actual is None else "fully_received",
    )
    db.add(shipment)
    db.flush()
    return shipment


def _line(
    db: Session,
    *,
    spo_number: str,
    line_no: int,
    product: Product,
    warehouse: Warehouse | None = None,
    allocated: int = 10,
    received: int = 0,
    rejected: int = 0,
    receipt_status: str = "pending",
    line_status: str = "open",
    expected_date: date | None = None,
    shipment: InboundShipment | None = None,
    supplier: Supplier | None = None,
) -> SPOAllocation:
    allocation = SPOAllocation(
        id=_u(),
        spo_number=spo_number,
        spo_line_number=line_no,
        product_id=product.id,
        warehouse_id=warehouse.id if warehouse else None,
        allocated_quantity=allocated,
        quantity_received=received,
        quantity_rejected=rejected,
        receipt_status=receipt_status,
        line_status=line_status,
        expected_date=expected_date,
        inbound_shipment_id=shipment.id if shipment else None,
        supplier_id=supplier.id if supplier else None,
    )
    db.add(allocation)
    db.flush()
    return allocation


# =================================================================================== #
# AC-12: one rule, fifth reader
# =================================================================================== #


def test_outstanding_admits_exactly_open_incoming_and_positive_balance(scm_app):
    """One line per exclusion reason: closed line, fully_received, landed shipment,
    zero balance - each on its own document, so each document is entirely `completed`
    while exactly one document is `outstanding`."""
    client, db = _client(scm_app)
    chain = _chain(db)
    product = _product(db, chain)
    today = date.today()

    still_open = unique_code("SPO-OPEN")
    _line(db, spo_number=still_open, line_no=1, product=product, allocated=10, received=0,
          expected_date=today + timedelta(days=5))

    closed_doc = unique_code("SPO-CLOSED")
    _line(db, spo_number=closed_doc, line_no=1, product=product, allocated=10, received=0,
          line_status="closed", expected_date=today + timedelta(days=5))

    fully_received_doc = unique_code("SPO-FULLREC")
    _line(db, spo_number=fully_received_doc, line_no=1, product=product, allocated=10,
          received=10, receipt_status="fully_received", expected_date=today + timedelta(days=5))

    supplier = _supplier(db)
    landed_ship = _shipment(db, supplier=supplier, estimated=today - timedelta(days=2),
                             actual=today - timedelta(days=1))
    landed_doc = unique_code("SPO-LANDED")
    _line(db, spo_number=landed_doc, line_no=1, product=product, allocated=10, received=2,
          shipment=landed_ship, supplier=supplier)

    zero_balance_doc = unique_code("SPO-ZEROBAL")
    _line(db, spo_number=zero_balance_doc, line_no=1, product=product, allocated=10,
          received=10, expected_date=today + timedelta(days=5))

    outstanding = client.get(DOCUMENTS_URL, params={
        "state": "outstanding", "query": product.product_code, "limit": 100,
    })
    assert outstanding.status_code == 200, outstanding.text
    assert {r["spo_number"] for r in outstanding.json()["data"]} == {still_open}

    completed = client.get(DOCUMENTS_URL, params={
        "state": "completed", "query": product.product_code, "limit": 100,
    })
    assert completed.status_code == 200, completed.text
    assert {r["spo_number"] for r in completed.json()["data"]} == {
        closed_doc, fully_received_doc, landed_doc, zero_balance_doc,
    }

    everything = client.get(DOCUMENTS_URL, params={
        "state": "all", "query": product.product_code, "limit": 100,
    })
    assert everything.status_code == 200, everything.text
    assert len(everything.json()["data"]) == 5


def test_outstanding_line_membership_matches_on_the_document_detail_too(scm_app):
    """The detail route's own `outstanding` flag (drives the Lines-tab rollup) agrees
    with the list's rollup - the SAME import, read a second way."""
    client, db = _client(scm_app)
    chain = _chain(db)
    product = _product(db, chain)
    doc = unique_code("SPO-DETAIL-OUT")
    _line(db, spo_number=doc, line_no=1, product=product, allocated=10, received=0)
    _line(db, spo_number=doc, line_no=2, product=product, allocated=10, received=10,
          receipt_status="fully_received")

    r = client.get(f"{DOCUMENTS_URL}/{doc}")
    assert r.status_code == 200, r.text
    body = r.json()
    outstanding_flags = sorted(line["outstanding"] for line in body["lines"])
    assert outstanding_flags == [False, True]
    assert body["status"] == "outstanding"


# =================================================================================== #
# AC-13: computed line fields (drop-guard)
# =================================================================================== #


def test_line_computed_fields_are_present_on_the_document_response(scm_app):
    client, db = _client(scm_app)
    chain = _chain(db)
    product = _product(db, chain)
    warehouse = _warehouse(db, active=True, planning=True)
    supplier = _supplier(db, name="Shipment Supplier Co")
    shipment = _shipment(db, supplier=supplier, estimated=date.today() - timedelta(days=3))
    doc = unique_code("SPO-FIELDS")
    _line(db, spo_number=doc, line_no=1, product=product, warehouse=warehouse,
          allocated=20, received=5, shipment=shipment, supplier=supplier)

    r = client.get(f"{DOCUMENTS_URL}/{doc}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["lines"], body
    line = body["lines"][0]
    for field in ("balance", "arrival_date", "overdue_days", "supplier_name", "planning_span"):
        assert field in line, (field, line)
    assert line["balance"] == 15
    assert line["overdue_days"] == 3
    assert line["supplier_name"] == "Shipment Supplier Co"
    assert line["planning_span"] == "in_plan"


def test_arrival_date_coalesce_prefers_eta_delay_over_estimate_and_expected(scm_app):
    """The one coalesce (plan Q3/S1, review S6): `eta_delay_date` ->
    `estimated_arrival_date` -> line `expected_date`. Seeded together, on the SAME
    line, so a coalesce that silently reordered its arms would still pass a test
    that only ever set one of the three."""
    client, db = _client(scm_app)
    chain = _chain(db)
    product = _product(db, chain)
    supplier = _supplier(db)
    today = date.today()
    eta_delay = today + timedelta(days=1)
    estimated = today + timedelta(days=9)
    shipment = _shipment(db, supplier=supplier, eta_delay=eta_delay, estimated=estimated)
    doc = unique_code("SPO-ARRIVAL")
    _line(
        db, spo_number=doc, line_no=1, product=product, allocated=10, received=0,
        shipment=shipment, supplier=supplier,
        expected_date=today + timedelta(days=20),
    )

    r = client.get(f"{DOCUMENTS_URL}/{doc}")
    assert r.status_code == 200, r.text
    line = r.json()["lines"][0]
    assert line["arrival_date"] == eta_delay.isoformat()

    list_r = client.get(DOCUMENTS_URL, params={
        "state": "all", "query": product.product_code, "limit": 100,
    })
    assert list_r.status_code == 200, list_r.text
    row = next(r for r in list_r.json()["data"] if r["spo_number"] == doc)
    assert row["earliest_eta"] == eta_delay.isoformat()


def test_document_row_declares_every_ac2_field(scm_app):
    """`response_model` drops an undeclared field silently - assert the row's own set."""
    client, db = _client(scm_app)
    chain = _chain(db)
    product = _product(db, chain)
    doc = unique_code("SPO-ROWFIELDS")
    _line(db, spo_number=doc, line_no=1, product=product, allocated=5, received=0)

    r = client.get(DOCUMENTS_URL, params={"query": product.product_code, "limit": 10})
    assert r.status_code == 200, r.text
    rows = [row for row in r.json()["data"] if row["spo_number"] == doc]
    assert len(rows) == 1
    row = rows[0]
    for field in (
        "id", "spo_number", "doc_date", "supplier_name", "supplier_extra_count",
        "status", "earliest_eta", "total_allocated", "total_received", "balance",
        "line_count", "worst_overdue_days",
    ):
        assert field in row, (field, row)


# =================================================================================== #
# AC-14: planning_span, all four values
# =================================================================================== #


def test_planning_span_covers_all_four_states(scm_app):
    client, db = _client(scm_app)
    chain = _chain(db)
    product = _product(db, chain)

    in_plan_wh = _warehouse(db, active=True, planning=True)
    off_wh = _warehouse(db, active=True, planning=False)
    pool_wh = _warehouse(db, active=True, planning=False)
    # A second, unflagged, active warehouse pointing at `pool_wh` is what makes it
    # "somebody's pool_warehouse_id" - the bin itself is never asserted on here.
    _warehouse(db, active=True, planning=False, pool_of=pool_wh.id)

    doc = unique_code("SPO-SPAN")
    _line(db, spo_number=doc, line_no=1, product=product, warehouse=in_plan_wh)
    _line(db, spo_number=doc, line_no=2, product=product, warehouse=off_wh)
    _line(db, spo_number=doc, line_no=3, product=product, warehouse=pool_wh)
    _line(db, spo_number=doc, line_no=4, product=product, warehouse=None)

    r = client.get(f"{DOCUMENTS_URL}/{doc}")
    assert r.status_code == 200, r.text
    spans = {line["warehouse_id"]: line["planning_span"] for line in r.json()["lines"]}
    assert spans[in_plan_wh.id] == "in_plan"
    assert spans[off_wh.id] == "off"
    assert spans[pool_wh.id] == "pool"
    assert spans[None] == "none"


# =================================================================================== #
# AC-15: header rollups
# =================================================================================== #


def test_header_rollups_and_majority_supplier(scm_app):
    client, db = _client(scm_app)
    chain = _chain(db)
    product = _product(db, chain)
    today = date.today()

    supplier_a = _supplier(db, name="Majority Co")
    supplier_b = _supplier(db, name="Minority Co")

    doc = unique_code("SPO-ROLLUP")
    _line(db, spo_number=doc, line_no=1, product=product, allocated=100, received=0,
          supplier=supplier_a, expected_date=today - timedelta(days=10))
    _line(db, spo_number=doc, line_no=2, product=product, allocated=50, received=0,
          supplier=supplier_a, expected_date=today - timedelta(days=3))
    _line(db, spo_number=doc, line_no=3, product=product, allocated=20, received=20,
          receipt_status="fully_received", supplier=supplier_b)

    r = client.get(DOCUMENTS_URL, params={
        "state": "all", "query": product.product_code, "limit": 100,
    })
    assert r.status_code == 200, r.text
    rows = {row["spo_number"]: row for row in r.json()["data"]}
    row = rows[doc]
    assert row["status"] == "outstanding"
    # Balance sums OUTSTANDING lines only: the fully-received line's balance (0) does
    # not net against it, and it is excluded entirely, not zeroed in.
    assert row["balance"] == 150
    assert row["worst_overdue_days"] == 10
    assert row["supplier_name"] == "Majority Co"
    assert row["supplier_extra_count"] == 1
    assert row["total_allocated"] == 170
    assert row["total_received"] == 20
    assert row["line_count"] == 3

    detail = client.get(f"{DOCUMENTS_URL}/{doc}")
    assert detail.status_code == 200, detail.text
    detail_body = detail.json()
    assert detail_body["status"] == row["status"]
    assert detail_body["balance"] == row["balance"]
    assert detail_body["supplier_name"] == row["supplier_name"]
    assert detail_body["supplier_extra_count"] == row["supplier_extra_count"]


def test_state_completed_document_has_no_outstanding_line(scm_app):
    client, db = _client(scm_app)
    chain = _chain(db)
    product = _product(db, chain)
    doc = unique_code("SPO-ALLDONE")
    _line(db, spo_number=doc, line_no=1, product=product, allocated=10, received=10,
          receipt_status="fully_received")

    r = client.get(DOCUMENTS_URL, params={
        "state": "completed", "query": product.product_code, "limit": 100,
    })
    assert r.status_code == 200, r.text
    rows = {row["spo_number"]: row for row in r.json()["data"]}
    assert rows[doc]["status"] == "completed"
    assert rows[doc]["balance"] == 0
    assert rows[doc]["worst_overdue_days"] == 0


# =================================================================================== #
# AC-11: filters
# =================================================================================== #


def test_product_and_warehouse_filters_match_lines_but_the_document_shows_every_line(scm_app):
    client, db = _client(scm_app)
    chain = _chain(db)
    matching_product = _product(db, chain)
    other_product = _product(db, chain)
    matching_wh = _warehouse(db, active=True)
    other_wh = _warehouse(db, active=True)

    doc = unique_code("SPO-FILTERDOC")
    _line(db, spo_number=doc, line_no=1, product=matching_product, warehouse=matching_wh)
    _line(db, spo_number=doc, line_no=2, product=other_product, warehouse=other_wh)

    unrelated_doc = unique_code("SPO-UNRELATED")
    _line(db, spo_number=unrelated_doc, line_no=1, product=other_product, warehouse=other_wh)

    r = client.get(DOCUMENTS_URL, params={
        "state": "all", "product_id": matching_product.id, "warehouse_id": matching_wh.id,
        "limit": 100,
    })
    assert r.status_code == 200, r.text
    numbers = {row["spo_number"] for row in r.json()["data"]}
    assert doc in numbers
    assert unrelated_doc not in numbers
    # `line_count` on the matched row still counts BOTH lines - filters find the
    # document, they do not shrink it (Q10).
    matched_row = next(row for row in r.json()["data"] if row["spo_number"] == doc)
    assert matched_row["line_count"] == 2


def test_query_matches_warehouse_code_and_packing_list_container_number(scm_app):
    """AC-25 (UAT batch): the free-text search also finds a document by its
    warehouse's CODE and by its packing list's container number - not just SPO
    number or product. One doc findable ONLY by warehouse code, another findable
    ONLY by container number."""
    client, db = _client(scm_app)
    chain = _chain(db)
    product = _product(db, chain)
    other_product = _product(db, chain)
    supplier = _supplier(db)

    findable_wh = _warehouse(db, active=True)
    wh_doc = unique_code("SPO-BYWHCODE")
    _line(db, spo_number=wh_doc, line_no=1, product=product, warehouse=findable_wh)

    findable_shipment = _shipment(db, supplier=supplier)
    findable_shipment.shipping_container_number = unique_code("CTN")
    db.flush()
    pl_doc = unique_code("SPO-BYPACKLIST")
    _line(db, spo_number=pl_doc, line_no=1, product=other_product, shipment=findable_shipment)

    unrelated_doc = unique_code("SPO-UNRELATEDQ")
    _line(db, spo_number=unrelated_doc, line_no=1, product=other_product)

    wh_result = client.get(DOCUMENTS_URL, params={
        "state": "all", "query": findable_wh.warehouse_code, "limit": 100,
    })
    assert wh_result.status_code == 200, wh_result.text
    wh_numbers = {row["spo_number"] for row in wh_result.json()["data"]}
    assert wh_numbers == {wh_doc}

    pl_result = client.get(DOCUMENTS_URL, params={
        "state": "all", "query": findable_shipment.shipping_container_number, "limit": 100,
    })
    assert pl_result.status_code == 200, pl_result.text
    pl_numbers = {row["spo_number"] for row in pl_result.json()["data"]}
    assert pl_numbers == {pl_doc}


def test_overdue_only_keeps_documents_with_a_late_outstanding_line(scm_app):
    client, db = _client(scm_app)
    chain = _chain(db)
    product = _product(db, chain)
    today = date.today()

    overdue_doc = unique_code("SPO-OVERDUE")
    _line(db, spo_number=overdue_doc, line_no=1, product=product, allocated=5, received=0,
          expected_date=today - timedelta(days=7))

    ontime_doc = unique_code("SPO-ONTIME")
    _line(db, spo_number=ontime_doc, line_no=1, product=product, allocated=5, received=0,
          expected_date=today + timedelta(days=7))

    r = client.get(DOCUMENTS_URL, params={
        "state": "outstanding", "query": product.product_code, "overdue_only": True, "limit": 100,
    })
    assert r.status_code == 200, r.text
    numbers = {row["spo_number"] for row in r.json()["data"]}
    assert numbers == {overdue_doc}


# =================================================================================== #
# AC-16 / AC-16b: detail 404, bulk delete
# =================================================================================== #


def test_unknown_spo_number_is_a_404(scm_app):
    client, db = _client(scm_app)
    r = client.get(f"{DOCUMENTS_URL}/{unique_code('SPO-MISSING')}")
    assert r.status_code == 404, r.text


def test_slash_bearing_spo_number_resolves_end_to_end(scm_app):
    """The `:path` converter, exercised with a REAL literal slash (plan Q7, review S5) -
    the shape an actual SPO number takes (`SPO-2026/08-0061`), requested the way the
    frontend sends it: `encodeURIComponent`ed once, so the slash arrives as `%2F` on
    the wire, exactly as `getSPODocument` builds the URL."""
    client, db = _client(scm_app)
    chain = _chain(db)
    product = _product(db, chain)
    doc = f"{unique_code('SPO')}/08-0061"
    _line(db, spo_number=doc, line_no=1, product=product, allocated=10, received=0)

    r = client.get(f"{DOCUMENTS_URL}/{quote(doc, safe='')}")
    assert r.status_code == 200, r.text
    assert r.json()["spo_number"] == doc


# =================================================================================== #
# AC-16b: `spo_document.delete` (record-actions registry, review B1) - no route of its
# own any more. Exercised at the SERVICE method the handler calls, unchanged, per the
# registry's own load-bearing rule (`app/services/record_actions.py`'s module doc).
# =================================================================================== #


def test_delete_document_removes_only_the_named_document(scm_app):
    from app.services.procurement_service import SPOAllocationService

    client, db = _client(scm_app, delete=True)
    chain = _chain(db)
    product = _product(db, chain)
    doc_a = unique_code("SPO-DELA")
    doc_b = unique_code("SPO-DELB")
    _line(db, spo_number=doc_a, line_no=1, product=product)
    _line(db, spo_number=doc_a, line_no=2, product=product)
    _line(db, spo_number=doc_b, line_no=1, product=product)

    result = SPOAllocationService(db).delete_document(doc_a)
    assert result["deleted_count"] == 2

    remaining = (
        db.query(SPOAllocation.spo_number)
        .filter(SPOAllocation.spo_number.in_([doc_a, doc_b]))
        .all()
    )
    assert {row[0] for row in remaining} == {doc_b}


def test_delete_document_with_unknown_spo_number_is_a_safe_no_op(scm_app):
    from app.services.procurement_service import SPOAllocationService

    client, db = _client(scm_app, delete=True)
    result = SPOAllocationService(db).delete_document(unique_code("SPO-GHOST"))
    assert result["deleted_count"] == 0


def test_delete_document_is_scoped_to_the_callers_company(scm_app):
    """B1: `spo_number` is unique per `(company_id, spo_number, spo_line_number)`, not
    globally - two companies can each own a document numbered identically. The bulk ORM
    delete this replaced filtered on `spo_number` ALONE and bypassed the company-scope
    filter entirely (`do_orm_execute` only rewrites SELECTs, never a bulk
    `.filter(...).delete()`), so company B could delete company A's document.
    `delete_document` resolves the ids under a plain SELECT first - which IS scoped -
    and only ever deletes by id, so company A's delete cannot reach company B's rows."""
    from app.models.base import set_company_scope
    from app.models.company import Company
    from app.services.procurement_service import SPOAllocationService

    _app, db, _gcu, _gcuk = scm_app
    company_a = _u()
    company_b = _u()
    db.add_all([
        Company(id=company_a, name=f"ZZT company A {company_a[:8]}",
                code=f"ZZT-{uuid.uuid4().hex[:6]}".upper()[:50], is_active=True),
        Company(id=company_b, name=f"ZZT company B {company_b[:8]}",
                code=f"ZZT-{uuid.uuid4().hex[:6]}".upper()[:50], is_active=True),
    ])
    db.flush()

    same_spo_number = unique_code("SPO-SHARED")

    set_company_scope(db, frozenset({company_a}))
    chain_a = _chain(db)
    product_a = _product(db, chain_a)
    _line(db, spo_number=same_spo_number, line_no=1, product=product_a)

    set_company_scope(db, frozenset({company_b}))
    chain_b = _chain(db)
    product_b = _product(db, chain_b)
    _line(db, spo_number=same_spo_number, line_no=1, product=product_b)

    # Delete AS COMPANY A.
    set_company_scope(db, frozenset({company_a}))
    result = SPOAllocationService(db).delete_document(same_spo_number)
    assert result["deleted_count"] == 1

    # Read back UNSCOPED (None = all companies) so the assertion is not itself hidden
    # by the same filter the fix relies on.
    set_company_scope(db, None)
    remaining = (
        db.query(SPOAllocation.company_id)
        .filter(SPOAllocation.spo_number == same_spo_number)
        .all()
    )
    assert [str(row[0]) for row in remaining] == [company_b]


# =================================================================================== #
# AC-24 (UAT batch): the Lines-tab line editors - product, warehouse, ETA and supplier
# all write through the SAME `PUT /spo-allocations/{id}` (no new route), so this pins
# the round trip at that endpoint and the document read agreeing with it afterwards.
# =================================================================================== #


ALLOCATION_URL = "/api/v1/procurement/spo-allocations"


def test_document_line_declares_supplier_id_and_expected_date(scm_app):
    """Drop-guard (LESSONS-LEARNT): `response_model` silently drops an undeclared
    field - both are needed to SEED the Lines-tab editors (AC-24 parts 2/3)."""
    client, db = _client(scm_app)
    chain = _chain(db)
    product = _product(db, chain)
    supplier = _supplier(db)
    expected = date.today() + timedelta(days=12)
    doc = unique_code("SPO-LINEFIELDS")
    _line(db, spo_number=doc, line_no=1, product=product, supplier=supplier,
          expected_date=expected)

    r = client.get(f"{DOCUMENTS_URL}/{doc}")
    assert r.status_code == 200, r.text
    line = r.json()["lines"][0]
    assert line["supplier_id"] == supplier.id
    assert line["expected_date"] == expected.isoformat()


def test_update_allocation_round_trips_product_warehouse_eta_and_supplier(scm_app):
    """AC-24 parts 1-3: product, warehouse, ETA (`expected_date`) and supplier all
    persist through the existing update endpoint, and the document read (what the
    Lines tab re-fetches after Save) reflects every one of them."""
    client, db = _client(scm_app)
    chain = _chain(db)
    original_product = _product(db, chain)
    new_product = _product(db, chain)
    original_wh = _warehouse(db, active=True)
    new_wh = _warehouse(db, active=True)
    new_supplier = _supplier(db)
    doc = unique_code("SPO-EDITLINE")
    allocation = _line(db, spo_number=doc, line_no=1, product=original_product,
                        warehouse=original_wh)

    new_expected = date.today() + timedelta(days=21)
    r = client.put(f"{ALLOCATION_URL}/{allocation.id}", json={
        "product_id": new_product.id,
        "warehouse_id": new_wh.id,
        "expected_date": new_expected.isoformat(),
        "supplier_id": new_supplier.id,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["product_id"] == new_product.id
    assert body["warehouse_id"] == new_wh.id
    assert body["supplier_id"] == new_supplier.id
    assert body["expected_date"] == new_expected.isoformat()

    detail = client.get(f"{DOCUMENTS_URL}/{doc}")
    assert detail.status_code == 200, detail.text
    line = detail.json()["lines"][0]
    assert line["product_id"] == new_product.id
    assert line["warehouse_id"] == new_wh.id
    assert line["supplier_id"] == new_supplier.id
    assert line["expected_date"] == new_expected.isoformat()


# =================================================================================== #
# AC-17: auth
# =================================================================================== #


def test_list_denies_without_the_view_permission(scm_app):
    client, db = _client(scm_app, view=False)
    r = client.get(DOCUMENTS_URL)
    assert r.status_code == 403, r.text
    assert VIEW_PERMISSION in r.text


def test_detail_denies_without_the_view_permission(scm_app):
    client, db = _client(scm_app, view=False)
    r = client.get(f"{DOCUMENTS_URL}/{unique_code('SPO-DENY')}")
    assert r.status_code == 403, r.text
    assert VIEW_PERMISSION in r.text


# =================================================================================== #
# R23, AC-J2/AC-J3 - lines carry `po` and `so_covered`; the header carries `linkage`.
# =================================================================================== #


def _project_link(db: Session, *, product: Product, allocation: SPOAllocation, qty: str):
    """One `order_inquiry_links` row on `allocation`, the project half of R23's
    `so_covered` (mirrors `test_spo_planner_selection._project_chain`'s own chain, built
    directly here rather than imported - this suite owns its own fixtures)."""
    project = Project(
        id=_u(), title="ZZT linkage project", normalised_title="zzt linkage project",
        project_code=unique_code("PRJ"),
    )
    db.add(project)
    db.flush()
    pso = ProjectSalesOrder(
        id=_u(), project_id=project.id, area_group="TOWER",
        provisional_ref=unique_code("PSO"), status=SO_STATUS_DRAFT, grouping_origin="area",
    )
    db.add(pso)
    db.flush()
    pso_line = ProjectSalesOrderLine(
        id=_u(), project_sales_order_id=pso.id, line_no=1, product_id=product.id,
        description="ZZT line", qty=Decimal(qty), uom="UNIT", unit_price=Decimal("1"),
        amount=Decimal(qty),
    )
    db.add(pso_line)
    db.flush()
    inquiry = OrderInquiry(id=_u(), project_sales_order_id=pso.id, state=INQUIRY_RAISED)
    db.add(inquiry)
    db.flush()
    row = OrderInquiryRow(
        id=_u(), order_inquiry_id=inquiry.id, so_line_id=pso_line.id,
        item_code=product.product_code, qty=Decimal(qty), verb=IV_ORDER_BACK,
        state=INQUIRY_RAISED,
    )
    db.add(row)
    db.flush()
    db.add(OrderInquiryLink(
        id=_u(), row_id=row.id, spo_allocation_id=allocation.id,
        document=allocation.spo_number, qty=Decimal(qty),
    ))
    db.flush()
    return pso, project


def _spo_line(db: Session, *, product: Product, supplier: Supplier, qty: str = "100"):
    """A CRM SPO's OWN purchase-order line - the row `spo_allocations.po_line_id` points at
    (`spo_conversion_service.create` writes its new line's id there, never the source PO's).
    Its `source_ref` JSON is where a retail take is recorded."""
    po = PurchaseOrder(
        id=_u(), po_number=unique_code("PO"), supplier_id=supplier.id,
        issue_date=date.today(), status="active", source_system=SOURCE_SYSTEM,
    )
    db.add(po)
    db.flush()
    po_line = PurchaseOrderLine(
        id=_u(), purchase_order_id=po.id, product_id=product.id, qty_ordered=Decimal(qty),
        qty_received=0, source_system=SOURCE_SYSTEM,
        source_ref=json.dumps({"pulls": [], "so_coverage": [], "no_po_qty": 0.0}),
    )
    db.add(po_line)
    db.flush()
    return po, po_line


def _retail_sales_order(db: Session, *, product: Product, warehouse: Warehouse, qty: str):
    """An open retail sales-order line, with its customer."""
    customer = Customer(
        id=_u(), customer_code=unique_code("CUS"), customer_name="ZZT linkage dealer",
    )
    db.add(customer)
    db.flush()
    so = SalesOrder(
        id=_u(), so_number=unique_code("SO"), customer_id=customer.id,
        order_date=date.today(), status="open",
    )
    db.add(so)
    db.flush()
    so_line = SalesOrderLine(
        id=_u(), sales_order_id=so.id, product_id=product.id, warehouse_id=warehouse.id,
        qty_ordered=Decimal(qty), qty_delivered=0, required_date=date.today(),
        line_status="open",
    )
    db.add(so_line)
    db.flush()
    return so, customer, so_line


def _cover(db: Session, po_line: PurchaseOrderLine, so_line: SalesOrderLine, qty: float):
    """Record a retail take on the SPO line's own `source_ref.so_coverage` - THE record of
    a retail take (R20 as amended, review round 1), which is what `get_document` reads."""
    parsed = json.loads(po_line.source_ref or "{}")
    parsed.setdefault("so_coverage", []).append({"so_line_id": str(so_line.id), "qty": qty})
    po_line.source_ref = json.dumps(parsed)
    db.flush()


def test_document_line_carries_po_and_so_covered_ac_j2(scm_app):
    """R23, AC-J2: the Lines tab's PO column resolves `po_line_id` to `{po_number,
    purchase_order_id}`; the SO covered column lists every sales order the allocation
    covers - project (`order_inquiry_links`) and retail (the SPO line's own
    `source_ref.so_coverage`, B1/B2 review round 1) both."""
    client, db = _client(scm_app)
    chain = _chain(db)
    product = _product(db, chain)
    warehouse = _warehouse(db)
    supplier = _supplier(db)

    po, po_line = _spo_line(db, product=product, supplier=supplier)

    doc = unique_code("SPO-J2")
    allocation = _line(
        db, spo_number=doc, line_no=1, product=product, warehouse=warehouse, allocated=30,
    )
    allocation.po_line_id = po_line.id
    db.flush()

    pso, project = _project_link(db, product=product, allocation=allocation, qty="10")
    so, customer, so_line = _retail_sales_order(
        db, product=product, warehouse=warehouse, qty="20",
    )
    _cover(db, po_line, so_line, 20.0)

    r = client.get(f"{DOCUMENTS_URL}/{doc}")
    assert r.status_code == 200, r.text
    line = r.json()["lines"][0]
    assert line["po"] == {
        "po_number": po.po_number, "purchase_order_id": str(po.id), "line_no": None,
    }
    covered = sorted(line["so_covered"], key=lambda c: c["demand_class"])
    assert covered == [
        {
            "document": pso.autocount_doc_no or pso.provisional_ref,
            "customer": project.title,
            "demand_class": "project",
            "qty": 10.0,
        },
        {
            "document": so.so_number,
            "customer": customer.customer_name,
            "demand_class": "retail",
            "qty": 20.0,
        },
    ]


def test_so_covered_reads_the_coverage_record_not_the_planner_claim(scm_app):
    """B2 (review round 1): `order_link_claim(source='planner')` is an audit echo, and
    nothing here reads it for quantities.

    Two halves of one assertion: a take recorded on `source_ref.so_coverage` with NO claim
    row beside it (the claim write is best-effort and can be refused) is still reported, and
    a claim row naming a sales order the coverage record does not is NOT."""
    client, db = _client(scm_app)
    chain = _chain(db)
    product = _product(db, chain)
    warehouse = _warehouse(db)
    supplier = _supplier(db)

    po, po_line = _spo_line(db, product=product, supplier=supplier)
    doc = unique_code("SPO-J2CLAIM")
    allocation = _line(
        db, spo_number=doc, line_no=1, product=product, warehouse=warehouse, allocated=30,
    )
    allocation.po_line_id = po_line.id
    db.flush()

    covered_so, customer, covered_line = _retail_sales_order(
        db, product=product, warehouse=warehouse, qty="20",
    )
    _cover(db, po_line, covered_line, 20.0)
    # A claim for a DIFFERENT sales order, of the kind a stale or mis-keyed echo would be.
    ghost_so, _ghost_customer, ghost_line = _retail_sales_order(
        db, product=product, warehouse=warehouse, qty="15",
    )
    db.add(OrderLinkClaim(
        id=_u(), so_number=ghost_so.so_number, po_number=doc,
        item_code=product.product_code, source="planner", so_line_id=ghost_line.id,
        spo_allocation_id=allocation.id, qty=Decimal("15"),
    ))
    db.flush()

    r = client.get(f"{DOCUMENTS_URL}/{doc}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["lines"][0]["so_covered"] == [
        {
            "document": covered_so.so_number,
            "customer": customer.customer_name,
            "demand_class": "retail",
            "qty": 20.0,
        },
    ]
    assert body["linkage"]["so_count"] == 1
    assert body["linkage"]["so_qty"] == 20.0


def test_two_spo_lines_of_one_product_each_show_their_own_take_of_one_sales_order(scm_app):
    """B1 (review round 1): two shipment lines of the same product on ONE SPO, each taking
    the same retail sales-order row, show BOTH quantities.

    The claim table keys one row per sales-order line, so reading it kept only whichever
    write landed last; the coverage record lives on each SPO LINE and states both."""
    client, db = _client(scm_app)
    chain = _chain(db)
    product = _product(db, chain)
    warehouse = _warehouse(db)
    supplier = _supplier(db)

    doc = unique_code("SPO-J2TWO")
    po, first_po_line = _spo_line(db, product=product, supplier=supplier)
    second_po_line = PurchaseOrderLine(
        id=_u(), purchase_order_id=po.id, product_id=product.id, qty_ordered=Decimal("100"),
        qty_received=0, source_system=SOURCE_SYSTEM,
        source_ref=json.dumps({"pulls": [], "so_coverage": [], "no_po_qty": 0.0}),
    )
    db.add(second_po_line)
    db.flush()

    first = _line(
        db, spo_number=doc, line_no=1, product=product, warehouse=warehouse, allocated=30,
    )
    first.po_line_id = first_po_line.id
    second = _line(
        db, spo_number=doc, line_no=2, product=product, warehouse=warehouse, allocated=40,
    )
    second.po_line_id = second_po_line.id
    db.flush()

    so, customer, so_line = _retail_sales_order(
        db, product=product, warehouse=warehouse, qty="70",
    )
    _cover(db, first_po_line, so_line, 30.0)
    _cover(db, second_po_line, so_line, 40.0)

    r = client.get(f"{DOCUMENTS_URL}/{doc}")
    assert r.status_code == 200, r.text
    body = r.json()
    by_line = {ln["id"]: ln["so_covered"] for ln in body["lines"]}
    assert by_line[str(first.id)] == [
        {
            "document": so.so_number, "customer": customer.customer_name,
            "demand_class": "retail", "qty": 30.0,
        },
    ]
    assert by_line[str(second.id)] == [
        {
            "document": so.so_number, "customer": customer.customer_name,
            "demand_class": "retail", "qty": 40.0,
        },
    ]
    assert body["linkage"]["so_count"] == 2
    assert body["linkage"]["so_qty"] == 70.0


def test_header_linkage_strip_fields_ac_j3(scm_app):
    """R23, AC-J3: the header linkage strip - `PO n · SPO lines n · SO covered n · qty ·
    Packing list <container> · GRN n`, computed across every line on the document."""
    client, db = _client(scm_app)
    chain = _chain(db)
    product = _product(db, chain)
    warehouse = _warehouse(db)
    supplier = _supplier(db)

    po, po_line = _spo_line(db, product=product, supplier=supplier)

    shipment = _shipment(db, supplier=supplier, estimated=date.today() - timedelta(days=3))
    shipment.shipping_container_number = "ZZTU1234567"
    db.flush()

    doc = unique_code("SPO-J3")
    allocation = _line(
        db, spo_number=doc, line_no=1, product=product, warehouse=warehouse, allocated=30,
        shipment=shipment, supplier=supplier,
    )
    allocation.po_line_id = po_line.id
    db.flush()

    _project_link(db, product=product, allocation=allocation, qty="10")
    _so, _customer, so_line = _retail_sales_order(
        db, product=product, warehouse=warehouse, qty="20",
    )
    _cover(db, po_line, so_line, 20.0)

    r = client.get(f"{DOCUMENTS_URL}/{doc}")
    assert r.status_code == 200, r.text
    linkage = r.json()["linkage"]
    assert linkage == {
        "po_count": 1,
        "line_count": 1,
        "so_count": 2,
        "so_qty": 30.0,
        "packing_list": {"id": str(shipment.id), "container": "ZZTU1234567"},
        "grn_count": 0,
    }
