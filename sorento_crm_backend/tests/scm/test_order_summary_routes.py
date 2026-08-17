"""The four Summary Order Report endpoints: shape, ordering, RBAC, and the write.

What these add over `test_summary_order_service.py` is the wire: that the response schema does
not silently drop a field the frontend reads, that a nullable figure survives serialisation as
null rather than 0, that `decided_by` is a NAME and no id crosses the wire, and that the read
and write routes are gated on different permissions.

**Every principal, role, permission and grant is seeded here.** `tests.scm.conftest.seed_user`
asserts an existing role slug, which is seed data: on CI's empty database there are no roles
and no permission rows, so borrowing them is how a suite passes locally and dies in CI. The
chain is built per test under a marker instead, which also makes the denial case honest - the
denied user really has no grant, rather than relying on a role that happens not to hold one.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.models.inventory import Stock, Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scm import ReorderRecommendation, ReorderRun
from app.models.user import (
    User,
    UserPermission,
    UserRole,
    UserRoleAssignment,
    UserRolePermission,
)
from app.services.scm import summary_order_service as svc
from app.services.scm.demand import ORDER_INQUIRY_ORIGIN
from app.services.scm.demand_class import class_of
from app.services.sla_service import MALAYSIA_TZ, to_naive_datetime
from tests.scm.conftest import requires_pg, scm_app  # noqa: F401  (fixture)

pytestmark = requires_pg

MARKER = "ZZTSORT"

_VIEW_PERM = "scm.dashboard.view"
_RUN_PERM = "scm.reorder.run"


def _u() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}".upper()


def _today() -> date:
    return to_naive_datetime(datetime.now(MALAYSIA_TZ)).date()


def _company(app, db) -> frozenset:
    """Give the session an active company of this test's own making, and hold it for the route.

    Owned tables are company-scoped and fail CLOSED: with no active company the ORM refuses to
    stamp `company_id` on an insert and resolves nothing on a read. In a real request
    `apply_company_scope` derives it from the caller's token, which a dependency override
    replaces - so the override has to supply the company too, or the route reads an empty
    catalogue and the failure looks like a bug in the service.

    Created rather than borrowed: borrowing picks whichever company the database happens to
    hold, and when that is not the one the fixtures were stamped with, nothing resolves.
    """
    from app.models.base import set_company_scope
    from app.models.company import Company
    from app.services.company_scope_resolver import apply_company_scope

    company_id = _u()
    db.add(Company(
        id=company_id, name=f"{MARKER} company {company_id[:8]}",
        code=_code("CO")[:50], is_active=True,
    ))
    db.flush()
    scope = frozenset({company_id})
    set_company_scope(db, scope)

    async def _scope():
        set_company_scope(db, scope)
        return scope

    app.dependency_overrides[apply_company_scope] = _scope
    return scope


def _principal(app, db, gcu, gcuk, *, perms: list[str], name="Mr Loo") -> str:
    """A real user with a real role holding exactly `perms`, seeded here.

    The permission rows are seeded too (get-or-create, since the slug is globally unique and a
    prod-copy database already has them), so the grant chain exists on an empty database.
    """
    uid = _u()
    db.add(User(id=uid, email=f"{uid}@zzt-sor.test", name=name, status="ACTIVE"))
    # `user_roles.name` is UNIQUE, so the name is marker-prefixed AND unique: a test that
    # re-authenticates as a second principal (to check a denial) seeds a second role in the
    # same transaction, and a fixed name collides on the insert rather than in the assertion.
    role_code = _code("role")
    role = UserRole(id=_u(), slug=role_code.lower(), name=role_code)
    db.add(role)
    db.flush()
    for slug in perms:
        perm = (
            db.query(UserPermission).filter(UserPermission.slug == slug).one_or_none()
        )
        if perm is None:
            perm = UserPermission(id=_u(), slug=slug, name=slug)
            db.add(perm)
            db.flush()
        db.add(UserRolePermission(id=_u(), role_id=role.id, permission_id=perm.id))
    db.add(UserRoleAssignment(user_id=uid, role_id=role.id))
    db.flush()

    principal = {"id": uid, "email": f"{uid}@zzt-sor.test", "name": name}
    app.dependency_overrides[gcu] = lambda: principal
    app.dependency_overrides[gcuk] = lambda: principal
    return uid


@pytest.fixture()
def chain(scm_app):  # noqa: F811
    """A completed run with one planned product, some demand, and one supplier."""
    app, db, gcu, gcuk = scm_app
    # Set the scope BEFORE seeding, so every row below is stamped with the company the route
    # will read under.
    _company(app, db)

    cat = ProductCategory(
        id=_u(), category_code=_code("CAT")[:40], category_name=_code("cat")
    )
    uom = UnitOfMeasure(id=_u(), uom_name=_code("uom"), uom_code=_code("U")[:20])
    db.add_all([cat, uom])
    db.flush()
    product = Product(
        id=_u(), product_code=_code("SKU"), product_name="wall hung wc",
        category_id=cat.id, base_uom_id=uom.id, list_price=0,
        is_active=True, is_discontinued=False,
    )
    pool = Warehouse(
        id=_u(), warehouse_code=_code("POOL")[:30], warehouse_name="pool",
        is_active=True, counts_as_available=True,
    )
    db.add_all([product, pool])
    db.flush()
    bin_a = Warehouse(
        id=_u(), warehouse_code=_code("BIN")[:30], warehouse_name="bin",
        is_active=True, counts_as_available=True, pool_warehouse_id=pool.id,
    )
    pool.pool_warehouse_id = pool.id
    db.add(bin_a)
    db.flush()
    db.add(Stock(id=_u(), product_id=product.id, warehouse_id=bin_a.id, quantity_on_hand=40))

    supplier = Supplier(
        id=_u(), supplier_code=_code("S")[:30], supplier_name="guangdong sw"
    )
    db.add(supplier)
    db.flush()
    po = PurchaseOrder(
        id=_u(), po_number=_code("PO")[:50], supplier_id=supplier.id, status="active",
        issue_date=_today() - timedelta(days=30),
    )
    db.add(po)
    db.flush()
    db.add(PurchaseOrderLine(
        id=_u(), purchase_order_id=po.id, product_id=product.id, warehouse_id=bin_a.id,
        qty_ordered=25, qty_received=0, unit_cost=20, currency="USD",
        expected_date=_today() + timedelta(days=20), line_status="open",
    ))

    cust = Customer(id=_u(), customer_code=_code("C")[:30], customer_name="acme projects")
    db.add(cust)
    db.flush()
    so = SalesOrder(
        id=_u(), so_number=_code("SO")[:50], customer_id=cust.id, status="open",
        # Classified the way every stamp point classifies one (front planning 5.2): the
        # persisted `demand_class` is what the split and the demand drill read, and a
        # fixture that set only the source order type would be testing a row the importer
        # cannot produce. Inquiry-created because project demand reaches the plan ONLY
        # through the Order Inquiry (S13b) - without the origin this line would be set
        # aside and the dated shortfall below would not exist.
        order_type="project", demand_class=class_of("project"),
        demand_origin=ORDER_INQUIRY_ORIGIN,
        order_date=_today() - timedelta(days=3),
    )
    db.add(so)
    db.flush()
    db.add(SalesOrderLine(
        id=_u(), sales_order_id=so.id, product_id=product.id, warehouse_id=bin_a.id,
        qty_ordered=100, qty_delivered=0,
        required_date=_today() + timedelta(days=10), line_status="open",
    ))

    run = ReorderRun(
        id=_u(), status="completed", buy_scope="warehouse",
        started_at=to_naive_datetime(datetime.now(MALAYSIA_TZ)),
        source_system="scm", source_ref=_code("RUN"),
        # Stamped as a CURRENT product-grain run (front planning 5.4): `record_decision`
        # IS the Product-grain decision, and a run with no stamp is legacy and read-only.
        decision_grain="product", front_planning_contract_version=1,
    )
    db.add(run)
    db.flush()
    db.add(ReorderRecommendation(
        id=_u(), run_id=run.id, rec_type="buy", product_id=product.id,
        warehouse_id=bin_a.id, rounded_qty=120, status="proposed",
    ))
    db.flush()
    svc.write_rows(db, run.id)

    return {
        "app": app, "db": db, "gcu": gcu, "gcuk": gcuk,
        "product": product, "supplier": supplier, "run": run, "pool": pool,
    }


@pytest.fixture()
def channel_chain(scm_app):  # noqa: F811
    """A product-grain run frozen WITH the channel breakdown (project confirmed, retail,
    unclassified, and the unconfirmed sheet leg), at two warehouses, dp-0 UOM.

    `chain` above predates front planning: its one recommendation carries no `inputs`, so
    `write_rows` takes the legacy branch and freezes no channel field at all. The locations
    drill and the precision/grain-mismatch decision routes need a row that actually HAS a
    channel basis to reconcile against - that is what this fixture is for.
    """
    app, db, gcu, gcuk = scm_app
    _company(app, db)

    cat = ProductCategory(
        id=_u(), category_code=_code("CAT")[:40], category_name=_code("cat")
    )
    uom = UnitOfMeasure(
        id=_u(), uom_name=_code("uom"), uom_code=_code("U")[:20], decimal_places=0,
    )
    db.add_all([cat, uom])
    db.flush()
    product = Product(
        id=_u(), product_code=_code("SKU"), product_name="wall hung wc",
        category_id=cat.id, base_uom_id=uom.id, list_price=0,
        is_active=True, is_discontinued=False,
    )
    brw = Warehouse(
        id=_u(), warehouse_code=_code("BRW")[:30], warehouse_name="brw",
        is_active=True, counts_as_available=True,
    )
    jb = Warehouse(
        id=_u(), warehouse_code=_code("JB")[:30], warehouse_name="jb",
        is_active=True, counts_as_available=True,
    )
    db.add_all([product, brw, jb])
    db.flush()

    supplier = Supplier(
        id=_u(), supplier_code=_code("S")[:30], supplier_name="guangdong sw",
    )
    db.add(supplier)
    db.flush()

    run = ReorderRun(
        id=_u(), status="completed", buy_scope="warehouse",
        started_at=to_naive_datetime(datetime.now(MALAYSIA_TZ)),
        source_system="scm", source_ref=_code("RUN"),
        decision_grain="product", front_planning_contract_version=1,
    )
    db.add(run)
    db.flush()
    db.add(ReorderRecommendation(
        id=_u(), run_id=run.id, rec_type="buy", product_id=product.id,
        warehouse_id=brw.id, rounded_qty=6, status="proposed",
        inputs={"project_need": 4, "retail_need": 2, "unclassified_need": 1,
                "project_sheet_need": 5},
    ))
    db.add(ReorderRecommendation(
        id=_u(), run_id=run.id, rec_type="buy", product_id=product.id,
        warehouse_id=jb.id, rounded_qty=5, status="proposed",
        inputs={"project_need": 0, "retail_need": 3, "unclassified_need": 2},
    ))
    db.flush()
    svc.write_rows(db, run.id)

    return {
        "app": app, "db": db, "gcu": gcu, "gcuk": gcuk,
        "product": product, "supplier": supplier, "run": run, "brw": brw, "jb": jb,
    }


# --------------------------------------------------------------------------- #
# the report
# --------------------------------------------------------------------------- #


def test_the_report_serialises_every_field_the_screen_reads(chain):
    """A response model that drops a field is invisible until the column renders blank."""
    f = chain
    _principal(f["app"], f["db"], f["gcu"], f["gcuk"], perms=[_VIEW_PERM])
    client = TestClient(f["app"])

    res = client.get(f"/api/v1/scm/order-summary?run_id={f['run'].id}")

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["run_id"] == str(f["run"].id)
    assert body["as_of"] == _today().isoformat()
    row = next(r for r in body["rows"] if r["product_code"] == f["product"].product_code)
    for key in (
        "product_code", "product_name", "uom", "on_hand", "project_demand",
        "dealer_outstanding", "qty_on_order", "qty_in_transit", "shortfall",
        "suggested_qty", "chosen_qty", "chosen_supplier_code", "chosen_supplier_name",
        "decided_by", "decided_at", "avg_daily_demand", "unit_volume_cbm",
        "spare_lands_at", "project_demand_line_count", "dealer_outstanding_line_count",
        "max_days_outstanding",
    ):
        assert key in row, f"the response model dropped {key}"
    assert row["on_hand"] == 40
    assert row["qty_on_order"] == 25
    assert row["shortfall"] == 60


def test_a_missing_input_arrives_as_null_and_not_zero(chain):
    """The whole reason those fields are Optional.

    Pydantic coercing a None to 0.0 would turn "nobody measured this" into "already out of
    stock" and "no space needed" at the serialisation boundary, after the service got it right.
    """
    f = chain
    _principal(f["app"], f["db"], f["gcu"], f["gcuk"], perms=[_VIEW_PERM])
    client = TestClient(f["app"])

    row = next(
        r for r in client.get(
            f"/api/v1/scm/order-summary?run_id={f['run'].id}"
        ).json()["rows"]
        if r["product_code"] == f["product"].product_code
    )

    assert row["avg_daily_demand"] is None
    assert row["unit_volume_cbm"] is None
    assert row["chosen_qty"] is None
    assert row["max_days_outstanding"] is None


def test_no_identifier_reaches_the_wire(chain):
    """No UUID may reach a screen a planner reads aloud. `run_id` is the one exception."""
    f = chain
    _principal(f["app"], f["db"], f["gcu"], f["gcuk"], perms=[_VIEW_PERM])
    client = TestClient(f["app"])

    body = client.get(f"/api/v1/scm/order-summary?run_id={f['run'].id}").json()

    for row in body["rows"]:
        for key, value in row.items():
            assert "_id" not in key, f"{key} is an identifier"
            if isinstance(value, str):
                assert str(f["product"].id) not in value
                assert str(f["supplier"].id) not in value


def test_reading_the_report_requires_the_view_permission(chain):
    """A principal with the WRITE permission and no read grant must not read it."""
    f = chain
    _principal(f["app"], f["db"], f["gcu"], f["gcuk"], perms=[_RUN_PERM])
    client = TestClient(f["app"])

    res = client.get(f"/api/v1/scm/order-summary?run_id={f['run'].id}")

    assert res.status_code == 403, res.text


# --------------------------------------------------------------------------- #
# the drills and the suppliers
# --------------------------------------------------------------------------- #


def test_the_demand_drill_returns_the_lines_for_the_kind_asked_for(chain):
    f = chain
    _principal(f["app"], f["db"], f["gcu"], f["gcuk"], perms=[_VIEW_PERM])
    client = TestClient(f["app"])

    res = client.get(
        f"/api/v1/scm/order-summary/{f['product'].product_code}/demand?kind=project"
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["kind"] == "project"
    assert body["total_qty"] == 100
    assert len(body["project_lines"]) == 1
    assert body["project_lines"][0]["project_name"] == "acme projects"
    assert body["dealer_lines"] == []


def test_an_unknown_drill_kind_is_a_422(chain):
    f = chain
    _principal(f["app"], f["db"], f["gcu"], f["gcuk"], perms=[_VIEW_PERM])
    client = TestClient(f["app"])

    res = client.get(
        f"/api/v1/scm/order-summary/{f['product'].product_code}/demand?kind=everything"
    )

    assert res.status_code == 422, res.text


def test_the_supplier_list_carries_cost_beside_on_time_and_lead_time(chain):
    """AC-C3.5: cost alone cannot answer whether to change supplier."""
    f = chain
    _principal(f["app"], f["db"], f["gcu"], f["gcuk"], perms=[_VIEW_PERM])
    client = TestClient(f["app"])

    res = client.get(
        f"/api/v1/scm/order-summary/{f['product'].product_code}/suppliers"
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["stale_after_days"] == svc.DEFAULT_STALE_AFTER_DAYS
    c = next(
        c for c in body["candidates"]
        if c["supplier_code"] == f["supplier"].supplier_code
    )
    assert c["last_po_cost"] == 20
    assert c["currency"] == "USD"
    for key in ("on_time_rate", "lead_time_days", "delivered_line_count", "is_stale"):
        assert key in c
    # Never delivered this item: an open order is not a delivery.
    assert c["delivered_line_count"] == 0


def test_an_unknown_product_code_is_a_404(chain):
    f = chain
    _principal(f["app"], f["db"], f["gcu"], f["gcuk"], perms=[_VIEW_PERM])
    client = TestClient(f["app"])

    res = client.get(f"/api/v1/scm/order-summary/{_code('NOSUCH')}/suppliers")

    assert res.status_code == 404, res.text


# --------------------------------------------------------------------------- #
# the decision
# --------------------------------------------------------------------------- #


def test_recording_a_decision_echoes_it_and_names_the_person(chain):
    """`decided_by` is a NAME. The sibling decision routes pass a user id; this must not."""
    f = chain
    _principal(
        f["app"], f["db"], f["gcu"], f["gcuk"],
        perms=[_VIEW_PERM, _RUN_PERM], name="Mr Loo",
    )
    client = TestClient(f["app"])

    res = client.post(
        f"/api/v1/scm/order-summary/{f['product'].product_code}/decision",
        json={
            "run_id": str(f["run"].id),
            "chosen_qty": 500,
            "supplier_code": f["supplier"].supplier_code,
        },
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["chosen_qty"] == 500
    # Above the shortfall of 60 and not a warning state (AC-C2.7), with the engine's own
    # figure still beside it (AC-C2.8).
    assert body["suggested_qty"] == 120
    assert body["decided_by"] == "Mr Loo"
    assert "-" in body["decided_at"]
    # And it is visible to the next reader.
    row = next(
        r for r in client.get(
            f"/api/v1/scm/order-summary?run_id={f['run'].id}"
        ).json()["rows"]
        if r["product_code"] == f["product"].product_code
    )
    assert row["chosen_qty"] == 500
    assert row["decided_by"] == "Mr Loo"


def test_recording_a_decision_requires_the_run_permission(chain):
    """Reading the report must not be enough to decide on it."""
    f = chain
    _principal(f["app"], f["db"], f["gcu"], f["gcuk"], perms=[_VIEW_PERM])
    client = TestClient(f["app"])

    res = client.post(
        f"/api/v1/scm/order-summary/{f['product'].product_code}/decision",
        json={
            "run_id": str(f["run"].id),
            "chosen_qty": 10,
            "supplier_code": f["supplier"].supplier_code,
        },
    )

    assert res.status_code == 403, res.text


def test_a_negative_quantity_is_rejected_by_the_endpoint(chain):
    f = chain
    _principal(f["app"], f["db"], f["gcu"], f["gcuk"], perms=[_VIEW_PERM, _RUN_PERM])
    client = TestClient(f["app"])

    res = client.post(
        f"/api/v1/scm/order-summary/{f['product'].product_code}/decision",
        json={
            "run_id": str(f["run"].id),
            "chosen_qty": -1,
            "supplier_code": f["supplier"].supplier_code,
        },
    )

    assert res.status_code == 422, res.text


# --------------------------------------------------------------------------- #
# the locations drill (AC-F08), and precision/grain over HTTP (AC-F09, F12)
# --------------------------------------------------------------------------- #


def test_the_locations_drill_serialises_the_channel_breakdown_including_the_sheet_leg(
    channel_chain,
):
    """AC-F08: member locations, the channel split, the unconfirmed sheet leg named as
    evidence, and the once-rounded suggested figure the drill reconciles against."""
    f = channel_chain
    _principal(f["app"], f["db"], f["gcu"], f["gcuk"], perms=[_VIEW_PERM])
    client = TestClient(f["app"])

    res = client.get(
        f"/api/v1/scm/order-summary/{f['product'].product_code}/locations",
        params={"run_id": str(f["run"].id)},
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["product_code"] == f["product"].product_code
    assert body["decision_grain"] == "product"
    assert body["is_legacy"] is False
    assert body["uom_decimal_places"] == 0
    assert len(body["locations"]) == 2
    brw_loc = next(
        l for l in body["locations"] if l["warehouse_code"] == f["brw"].warehouse_code
    )
    assert brw_loc["project_need"] == 4
    assert brw_loc["retail_need"] == 2
    assert brw_loc["unclassified_need"] == 1
    assert brw_loc["project_sheet_need"] == 5, "the sheet leg must reach the drill too"
    assert sum(l["project_need"] for l in body["locations"]) == 4
    assert sum(l["retail_need"] for l in body["locations"]) == 5
    assert sum(l["unclassified_need"] for l in body["locations"]) == 3


def test_the_locations_drill_on_a_legacy_run_returns_none_channel_fields_not_zero(
    channel_chain,
):
    """AC-F10: a run with no `front_planning_contract_version` has no channel breakdown to
    show and none is inferred - the drill's locations come back empty and its precision
    field is NULL, never 0."""
    f = channel_chain
    legacy_run = ReorderRun(
        id=_u(), status="completed", buy_scope="warehouse",
        started_at=to_naive_datetime(datetime.now(MALAYSIA_TZ)),
        source_system="scm", source_ref=_code("RUN"),
        # no decision_grain / front_planning_contract_version -> legacy
    )
    f["db"].add(legacy_run)
    f["db"].flush()
    f["db"].add(ReorderRecommendation(
        id=_u(), run_id=legacy_run.id, rec_type="buy", product_id=f["product"].id,
        warehouse_id=f["brw"].id, rounded_qty=6, status="proposed",
    ))
    f["db"].flush()
    svc.write_rows(f["db"], legacy_run.id)

    _principal(f["app"], f["db"], f["gcu"], f["gcuk"], perms=[_VIEW_PERM])
    client = TestClient(f["app"])

    res = client.get(
        f"/api/v1/scm/order-summary/{f['product'].product_code}/locations",
        params={"run_id": str(legacy_run.id)},
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["is_legacy"] is True
    assert body["decision_grain"] is None
    assert body["uom_decimal_places"] is None
    assert body["locations"] == []


def test_reading_the_locations_drill_requires_the_view_permission(channel_chain):
    """A principal holding only the write permission must not read the drill."""
    f = channel_chain
    _principal(f["app"], f["db"], f["gcu"], f["gcuk"], perms=[_RUN_PERM])
    client = TestClient(f["app"])

    res = client.get(
        f"/api/v1/scm/order-summary/{f['product'].product_code}/locations",
        params={"run_id": str(f["run"].id)},
    )

    assert res.status_code == 403, res.text


def test_recording_a_decision_over_http_refuses_a_fraction_finer_than_the_frozen_uom(
    channel_chain,
):
    """AC-F12 at the wire: a dp-0 row refuses `2.5` with the precision code, not a generic
    422 - `test_a_negative_quantity_is_rejected_by_the_endpoint` above already covers the
    generic 422, this is the specific one."""
    f = channel_chain
    _principal(f["app"], f["db"], f["gcu"], f["gcuk"], perms=[_VIEW_PERM, _RUN_PERM])
    client = TestClient(f["app"])

    res = client.post(
        f"/api/v1/scm/order-summary/{f['product'].product_code}/decision",
        json={
            "run_id": str(f["run"].id),
            "chosen_qty": 2.5,
            "supplier_code": f["supplier"].supplier_code,
        },
    )

    assert res.status_code == 422, res.text
    assert res.json()["code"] == "chosen_qty_precision"


def test_recording_a_decision_over_http_refuses_a_location_grain_run(channel_chain):
    """AC-F09 at the wire: a run decided at Location grain must refuse the Product-grain
    write with 409, not silently accept it into the wrong grain's ownership."""
    f = channel_chain
    f["run"].decision_grain = "location"
    f["db"].add(f["run"])
    f["db"].commit()
    _principal(f["app"], f["db"], f["gcu"], f["gcuk"], perms=[_VIEW_PERM, _RUN_PERM])
    client = TestClient(f["app"])

    res = client.post(
        f"/api/v1/scm/order-summary/{f['product'].product_code}/decision",
        json={
            "run_id": str(f["run"].id),
            "chosen_qty": 4,
            "supplier_code": f["supplier"].supplier_code,
        },
    )

    assert res.status_code == 409, res.text
    assert res.json()["code"] == "decision_grain_mismatch"


# --------------------------------------------------------------------------- #
# S4 - the PO worklist endpoints
# --------------------------------------------------------------------------- #


def _decide(client, f, *, qty):
    return client.post(
        f"/api/v1/scm/order-summary/{f['product'].product_code}/decision",
        json={
            "run_id": str(f["run"].id),
            "chosen_qty": qty,
            "supplier_code": f["supplier"].supplier_code,
        },
    )


def test_the_worklist_serialises_every_field_the_screen_reads(chain):
    """A response model that drops a field is invisible until the column renders blank."""
    f = chain
    _principal(f["app"], f["db"], f["gcu"], f["gcuk"], perms=[_VIEW_PERM, _RUN_PERM])
    client = TestClient(f["app"])
    assert _decide(client, f, qty=250).status_code == 200, "the decision must land first"

    res = client.get(f"/api/v1/scm/po-worklist?run_id={f['run'].id}")

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["run_id"] == str(f["run"].id)
    row = next(r for r in body["rows"] if r["product_code"] == f["product"].product_code)
    for key in (
        "product_code", "product_name", "uom", "chosen_qty", "suggested_qty",
        "chosen_supplier_code", "chosen_supplier_name", "decided_by", "decided_at",
        "need_by", "place_by", "lead_time_days", "is_late", "last_po_cost",
        "last_po_currency", "cash_committed", "keyed_status", "keyed_by", "keyed_at",
    ):
        assert key in row, f"the response model dropped {key}"
    assert row["chosen_qty"] == 250
    assert row["keyed_status"] == "not_keyed"
    # 40 on hand against 100 due in 10 days, so there IS a dated shortfall here.
    assert row["need_by"]


def test_a_nullable_worklist_field_arrives_as_null_and_not_zero(chain):
    """A place-by date coerced to a string, or a lead time to 0, would both be acted on."""
    f = chain
    _principal(f["app"], f["db"], f["gcu"], f["gcuk"], perms=[_VIEW_PERM, _RUN_PERM])
    client = TestClient(f["app"])
    _decide(client, f, qty=250)

    row = next(
        r for r in client.get(f"/api/v1/scm/po-worklist?run_id={f['run'].id}").json()["rows"]
        if r["product_code"] == f["product"].product_code
    )

    # No product_suppliers link and no supplier_performance row, so the lead time is
    # genuinely unknown and the place-by date cannot be derived from it.
    assert row["lead_time_days"] is None
    assert row["place_by"] is None
    assert row["is_late"] is False
    assert row["keyed_by"] is None


def test_reading_the_worklist_requires_the_view_permission(chain):
    f = chain
    _principal(f["app"], f["db"], f["gcu"], f["gcuk"], perms=[_RUN_PERM])
    client = TestClient(f["app"])

    res = client.get(f"/api/v1/scm/po-worklist?run_id={f['run'].id}")

    assert res.status_code == 403, res.text


def test_setting_the_keyed_status_echoes_it_and_names_the_person(chain):
    """`keyed_by` is a NAME: it is rendered beside the row on a shared queue."""
    f = chain
    _principal(
        f["app"], f["db"], f["gcu"], f["gcuk"],
        perms=[_VIEW_PERM, _RUN_PERM], name="Joey",
    )
    client = TestClient(f["app"])
    _decide(client, f, qty=250)

    res = client.post(
        f"/api/v1/scm/po-worklist/{f['product'].product_code}/keyed-status",
        json={"run_id": str(f["run"].id), "keyed_status": "keying"},
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["keyed_status"] == "keying"
    assert body["keyed_by"] == "Joey"
    # And the next reader sees it, which is the point on a queue two people work.
    row = next(
        r for r in client.get(f"/api/v1/scm/po-worklist?run_id={f['run'].id}").json()["rows"]
        if r["product_code"] == f["product"].product_code
    )
    assert row["keyed_status"] == "keying"
    assert row["keyed_by"] == "Joey"


def test_setting_the_keyed_status_requires_the_run_permission(chain):
    """Reading the worklist must not be enough to claim a row on it."""
    f = chain
    _principal(f["app"], f["db"], f["gcu"], f["gcuk"], perms=[_VIEW_PERM, _RUN_PERM])
    client = TestClient(f["app"])
    _decide(client, f, qty=250)
    # Re-authenticate as a read-only principal.
    _principal(f["app"], f["db"], f["gcu"], f["gcuk"], perms=[_VIEW_PERM])

    res = client.post(
        f"/api/v1/scm/po-worklist/{f['product'].product_code}/keyed-status",
        json={"run_id": str(f["run"].id), "keyed_status": "keyed"},
    )

    assert res.status_code == 403, res.text


def test_an_unknown_keyed_status_is_rejected_by_the_endpoint(chain):
    f = chain
    _principal(f["app"], f["db"], f["gcu"], f["gcuk"], perms=[_VIEW_PERM, _RUN_PERM])
    client = TestClient(f["app"])
    _decide(client, f, qty=250)

    res = client.post(
        f"/api/v1/scm/po-worklist/{f['product'].product_code}/keyed-status",
        json={"run_id": str(f["run"].id), "keyed_status": "done"},
    )

    assert res.status_code == 422, res.text
