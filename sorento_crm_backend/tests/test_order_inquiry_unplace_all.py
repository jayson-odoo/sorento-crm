""""Unplace all" for the worklist's own scope (PLAN captain, 20-21 Aug):
`GET /order-inquiries/unplace-all-preview` and `POST /order-inquiries/unplace-all`.

Shipped with zero tests (review gap). Both routes are thin: the real logic lives in
`OrderInquiryWorklistService.unplace_all_preview` / `.unplace_all`, which read the SAME
`_base()` filters the worklist list/summary already use, forced to `state = placed`, and
the write is `ProjectOrderInquiryService.unplace_rows` - the bulk half of the single-row
Untag already covered by `tests/test_order_inquiry_place_on_po.py`.

What is worth pinning here, that nothing else covers:

* the preview's own count and its "one product" labelling rule (null the moment more
  than one product is in scope);
* every filter `unplace-all-preview` and `unplace-all` accept narrows BOTH the same way,
  because the count a person confirms and the rows the POST actually touches must never
  disagree;
* no filters at all is "every placed row in the company" - the documented footgun, not a
  guess;
* company isolation, auth (this is a write action, `projects.order_inquiry.action`, and
  the preview is gated on it too - it is a preview of a write, not a browse);
* a malformed `project_id`/`supplier_id` fails clean, not with a 500 or a poisoned
  transaction.

Every test seeds its own chain with a `zzt-oi-unplace-all` marker (CI's database is
empty). Real `place-on-po` calls through the API build the placed rows, so the same
`OrderLinkClaim` writes production traffic makes are exercised here too.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.company import Company
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import (
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    IV_ORDER,
    SO_STATUS_DRAFT,
    OrderInquiry,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)
from app.models.scm import OrderLinkClaim
from app.models.user import User
from app.services import project_seed_service

from ._pg_fixture import blank_session

MARKER = "zzt-oi-unplace-all"
BASE = "/api/v1/project-sales"
PREVIEW = f"{BASE}/order-inquiries/unplace-all-preview"
UNPLACE_ALL = f"{BASE}/order-inquiries/unplace-all"

READ_ONLY = ["projects.projects.view"]
PURCHASING = ["projects.projects.view", "projects.order_inquiry.action"]


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _product(db, company_id: str, code: str) -> Product:
    uom = UnitOfMeasure(
        id=_uid(), company_id=company_id, uom_code=f"ZZT{_uid()[:6]}", uom_name="Unit"
    )
    category = ProductCategory(
        id=_uid(),
        company_id=company_id,
        category_code=f"ZZT-{_uid()[:8]}",
        category_name=f"{MARKER} cat",
    )
    db.add_all([uom, category])
    db.flush()
    row = Product(
        id=_uid(),
        company_id=company_id,
        product_code=code,
        product_name=f"{MARKER} {code}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("100.00"),
    )
    db.add(row)
    db.flush()
    return row


def _supplier(db, company_id: str, name: str) -> Supplier:
    row = Supplier(
        id=_uid(), company_id=company_id, supplier_code=f"ZZT-{_uid()[:8]}", supplier_name=name
    )
    db.add(row)
    db.flush()
    return row


def _po(db, company_id: str, supplier: Supplier) -> PurchaseOrder:
    row = PurchaseOrder(
        id=_uid(),
        company_id=company_id,
        po_number=f"ZZT-PO-{_uid()[:8]}",
        supplier_id=supplier.id,
    )
    db.add(row)
    db.flush()
    return row


def _po_line(db, company_id: str, po: PurchaseOrder, product: Product, *, qty_ordered) -> PurchaseOrderLine:
    row = PurchaseOrderLine(
        id=_uid(),
        company_id=company_id,
        purchase_order_id=po.id,
        product_id=product.id,
        qty_ordered=Decimal(str(qty_ordered)),
        line_status="open",
    )
    db.add(row)
    db.flush()
    return row


def _project_sales_order(db, company_id: str, project_id: str, *, doc_no: str) -> ProjectSalesOrder:
    row = ProjectSalesOrder(
        id=_uid(),
        company_id=company_id,
        project_id=project_id,
        area_group="TOWER",
        provisional_ref=f"ZZT-PSO-{_uid()[:8]}",
        autocount_doc_no=doc_no,
        status=SO_STATUS_DRAFT,
        grouping_origin="area",
        published_at=datetime(2026, 1, 2, 9, 0),
    )
    db.add(row)
    db.flush()
    return row


def _line(db, company_id: str, pso: ProjectSalesOrder, product: Product, *, qty, delivery_date, line_no=1) -> ProjectSalesOrderLine:
    row = ProjectSalesOrderLine(
        id=_uid(),
        company_id=company_id,
        project_sales_order_id=pso.id,
        line_no=line_no,
        product_id=product.id,
        description=f"{MARKER} line",
        qty=Decimal(str(qty)),
        uom="UNIT",
        unit_price=Decimal("10.00"),
        amount=Decimal(str(qty)) * Decimal("10.00"),
        delivery_date=delivery_date,
    )
    db.add(row)
    db.flush()
    return row


def _inquiry(db, company_id: str, pso: ProjectSalesOrder) -> OrderInquiry:
    row = OrderInquiry(
        id=_uid(), company_id=company_id, project_sales_order_id=pso.id, state=INQUIRY_RAISED
    )
    db.add(row)
    db.flush()
    return row


def _row(db, company_id: str, inquiry: OrderInquiry, line: ProjectSalesOrderLine, product: Product, *, qty, delivery_date, created_at) -> OrderInquiryRow:
    row = OrderInquiryRow(
        id=_uid(),
        company_id=company_id,
        order_inquiry_id=inquiry.id,
        so_line_id=line.id,
        item_code=product.product_code,
        qty=Decimal(str(qty)),
        delivery_date=delivery_date,
        verb=IV_ORDER,
        state=INQUIRY_RAISED,
        created_at=created_at,
    )
    db.add(row)
    db.flush()
    return row


def _client(db, user_id: str, permissions):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    actor = {"id": user_id, "email": f"{user_id}@zzt.test", "role": "user"}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    app.dependency_overrides[apply_company_scope] = lambda: None

    originals = (
        UserPermissionService.check_user_has_permission,
        UserPermissionService.get_user_permission_slugs,
    )
    granted = list(permissions)
    UserPermissionService.check_user_has_permission = (
        lambda self, uid, slug: slug in granted
    )
    UserPermissionService.get_user_permission_slugs = lambda self, uid: list(granted)
    return TestClient(app), originals


def _restore(originals) -> None:
    from app.main import app
    from app.services.user_service import UserPermissionService

    UserPermissionService.check_user_has_permission = originals[0]
    UserPermissionService.get_user_permission_slugs = originals[1]
    app.dependency_overrides.clear()


def _seed_world(db, company_id: str, user_id: str) -> dict:
    """Two projects, three placeable rows and one raised control.

    - `row1` and `row2` are BOTH product A, but on two DIFFERENT project sales orders
      (different `autocount_doc_no`) so their audit-claim identity (so_number, po_number,
      item_code) never collides - two rows sharing exactly that triple is an existing
      edge this fixture deliberately avoids poking, not something this file tests.
    - `row1`/`row2` are project1 + supplier X; `row3` is project2 + supplier B, a
      different product, a different delivery month and a different raised day - one
      lever per filter.
    - `row4` stays RAISED (never placed): the control that proves preview/POST only ever
      touch placed rows.
    """
    from app.services.project_service import register_project

    # Titles deliberately dissimilar (not "Project One"/"Project Two", which
    # differ by one word) AND `block_threshold` pinned above 1.0 - the maximum
    # possible trigram score - so `find_clashes`' `score >= block` path can
    # never fire regardless of what the random suffix draws. This test seeds
    # two projects for company-scoped isolation, not clash behaviour, and the
    # shared MARKER prefix already put "Project One"/"Project Two"'s score
    # close enough to the 0.70 block bar that the second registration
    # sometimes 409'd against the first before either row was ever placed
    # (project_already_registered, killed main's deploy attempt 3). Pinning
    # the threshold also immunises this seed against another xdist worker
    # concurrently mutating the shared `system_settings` clash-threshold row
    # (`resolve_thresholds` reads it live), which a title change alone would
    # not.
    project1 = register_project(
        db, company_id=company_id, actor_user_id=user_id, developer_party_id=None,
        title=f"{MARKER} Alpha Quay {_uid()[:12]}", block_threshold=2.0,
    )
    project2 = register_project(
        db, company_id=company_id, actor_user_id=user_id, developer_party_id=None,
        title=f"{MARKER} Zeta Ridge {_uid()[:12]}", block_threshold=2.0,
    )

    product_a = _product(db, company_id, f"ZZT-PA-{_uid()[:6]}")
    product_b = _product(db, company_id, f"ZZT-PB-{_uid()[:6]}")

    pso1a = _project_sales_order(db, company_id, project1.id, doc_no=f"SO{_uid()[:8].upper()}")
    pso1b = _project_sales_order(db, company_id, project1.id, doc_no=f"SO{_uid()[:8].upper()}")
    pso2 = _project_sales_order(db, company_id, project2.id, doc_no=f"SO{_uid()[:8].upper()}")

    line1 = _line(db, company_id, pso1a, product_a, qty="10", delivery_date=date(2026, 3, 2))
    line2 = _line(db, company_id, pso1b, product_a, qty="15", delivery_date=date(2026, 3, 10))
    line4 = _line(db, company_id, pso1a, product_a, qty="5", delivery_date=date(2026, 3, 15), line_no=2)
    line3 = _line(db, company_id, pso2, product_b, qty="20", delivery_date=date(2026, 4, 5))

    inquiry1a = _inquiry(db, company_id, pso1a)
    inquiry1b = _inquiry(db, company_id, pso1b)
    inquiry2 = _inquiry(db, company_id, pso2)

    row1 = _row(
        db, company_id, inquiry1a, line1, product_a,
        qty="10", delivery_date=date(2026, 3, 2), created_at=datetime(2026, 8, 1, 3, 0),
    )
    row2 = _row(
        db, company_id, inquiry1b, line2, product_a,
        qty="15", delivery_date=date(2026, 3, 10), created_at=datetime(2026, 8, 1, 4, 0),
    )
    row4 = _row(
        db, company_id, inquiry1a, line4, product_a,
        qty="5", delivery_date=date(2026, 3, 15), created_at=datetime(2026, 8, 1, 5, 0),
    )
    row3 = _row(
        db, company_id, inquiry2, line3, product_b,
        qty="20", delivery_date=date(2026, 4, 5), created_at=datetime(2026, 8, 5, 3, 0),
    )

    supplier_x = _supplier(db, company_id, f"{MARKER} Supplier X")
    supplier_y = _supplier(db, company_id, f"{MARKER} Supplier Y")
    po_x = _po(db, company_id, supplier_x)
    po_y = _po(db, company_id, supplier_y)
    po_line_x = _po_line(db, company_id, po_x, product_a, qty_ordered="100")
    po_line_y = _po_line(db, company_id, po_y, product_b, qty_ordered="100")

    db.commit()
    return {
        "project1": project1,
        "project2": project2,
        "product_a": product_a,
        "product_b": product_b,
        "row1": row1,
        "row2": row2,
        "row3": row3,
        "row4_raised": row4,
        "supplier_x": supplier_x,
        "supplier_y": supplier_y,
        "po_x": po_x,
        "po_y": po_y,
        "po_line_x": po_line_x,
        "po_line_y": po_line_y,
    }


def _place(client, row_id: str, po_line_id: str) -> None:
    response = client.post(
        f"{BASE}/order-inquiry-rows/{row_id}/place-on-po", json={"po_line_id": po_line_id}
    )
    assert response.status_code == 200, response.text


def _api(permissions):
    from app.models.base import company_scope

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        user_id = _user(db, f"{MARKER} Eling")
        world = _seed_world(db, company_id, user_id)
        client, originals = _client(db, user_id, permissions)
        try:
            with company_scope(db, frozenset({company_id})):
                yield client, db, company_id, world
        finally:
            _restore(originals)


@pytest.fixture()
def api():
    """PURCHASING permissions, all three rows PLACED, row4 left raised as a control."""
    gen = _api(PURCHASING)
    client, db, company_id, world = next(gen)
    _place(client, world["row1"].id, world["po_line_x"].id)
    _place(client, world["row2"].id, world["po_line_x"].id)
    _place(client, world["row3"].id, world["po_line_y"].id)
    for key in ("row1", "row2", "row3"):
        db.refresh(world[key])
    yield client, db, company_id, world
    try:
        next(gen)
    except StopIteration:
        pass


@pytest.fixture()
def api_unplaced():
    """Same world, but nothing has been placed - for validation/edge tests that never
    need a placed row and want to assert nothing at all moved."""
    yield from _api(PURCHASING)


@pytest.fixture()
def reader_api():
    """VIEW only, no `projects.order_inquiry.action` - the auth-denial fixture."""
    yield from _api(READ_ONLY)


# ------------------------------------------------------------------ preview


def test_preview_counts_the_placed_rows_in_scope_and_names_the_single_product(api):
    client, _db, _company_id, world = api

    response = client.get(PREVIEW, params={"project_id": world["project1"].id})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["count"] == 2
    assert body["product_code"] == world["product_a"].product_code
    assert body["product_name"] == world["product_a"].product_name


def test_preview_names_no_product_when_more_than_one_matches(api):
    client, _db, _company_id, _world = api

    response = client.get(PREVIEW)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["count"] == 3
    assert body["product_code"] is None
    assert body["product_name"] is None


def test_preview_never_counts_a_raised_row(api):
    client, _db, _company_id, world = api

    body = client.get(PREVIEW, params={"project_id": world["project1"].id}).json()

    # project1 holds row1 (placed), row2 (placed) and row4 (raised, same project). The
    # raised control must never inflate the count.
    assert body["count"] == 2


# ------------------------------------------------------------- filters narrow both

def test_the_delivery_month_filter_excludes_a_placed_row_from_preview_and_post(api):
    client, db, _company_id, world = api

    preview = client.get(PREVIEW, params={"delivery_month": "2026-03"}).json()
    assert preview["count"] == 2

    result = client.post(UNPLACE_ALL, json={"delivery_month": "2026-03"})
    assert result.status_code == 200, result.text
    assert result.json()["unplaced"] == 2

    db.refresh(world["row1"])
    db.refresh(world["row2"])
    db.refresh(world["row3"])
    assert world["row1"].state == INQUIRY_RAISED
    assert world["row2"].state == INQUIRY_RAISED
    # April's row was never in scope.
    assert world["row3"].state == INQUIRY_PLACED


def test_the_project_filter_excludes_a_placed_row_from_preview_and_post(api):
    client, db, _company_id, world = api

    preview = client.get(PREVIEW, params={"project_id": world["project2"].id}).json()
    assert preview["count"] == 1
    assert preview["product_code"] == world["product_b"].product_code

    result = client.post(UNPLACE_ALL, json={"project_id": world["project2"].id})
    assert result.json()["unplaced"] == 1

    db.refresh(world["row1"])
    db.refresh(world["row3"])
    assert world["row1"].state == INQUIRY_PLACED
    assert world["row3"].state == INQUIRY_RAISED


def test_the_supplier_filter_excludes_a_placed_row_from_preview_and_post(api):
    client, db, _company_id, world = api

    preview = client.get(PREVIEW, params={"supplier_id": world["supplier_x"].id}).json()
    assert preview["count"] == 2

    result = client.post(UNPLACE_ALL, json={"supplier_id": world["supplier_x"].id})
    assert result.json()["unplaced"] == 2

    db.refresh(world["row1"])
    db.refresh(world["row2"])
    db.refresh(world["row3"])
    assert world["row1"].state == INQUIRY_RAISED
    assert world["row2"].state == INQUIRY_RAISED
    # Supplier Y's row was never in scope.
    assert world["row3"].state == INQUIRY_PLACED


def test_the_query_filter_excludes_a_placed_row_from_preview_and_post(api):
    client, db, _company_id, world = api

    preview = client.get(PREVIEW, params={"query": world["product_b"].product_code}).json()
    assert preview["count"] == 1

    result = client.post(UNPLACE_ALL, json={"query": world["product_b"].product_code})
    assert result.json()["unplaced"] == 1

    db.refresh(world["row1"])
    db.refresh(world["row3"])
    assert world["row1"].state == INQUIRY_PLACED
    assert world["row3"].state == INQUIRY_RAISED


def test_the_raised_date_filter_excludes_a_placed_row_from_preview_and_post(api):
    client, db, _company_id, world = api

    preview = client.get(PREVIEW, params={"raised_date": "2026-08-01"}).json()
    assert preview["count"] == 2

    result = client.post(UNPLACE_ALL, json={"raised_date": "2026-08-01"})
    assert result.json()["unplaced"] == 2

    db.refresh(world["row1"])
    db.refresh(world["row2"])
    db.refresh(world["row3"])
    assert world["row1"].state == INQUIRY_RAISED
    assert world["row2"].state == INQUIRY_RAISED
    # Raised on the 5th, a different day - never in scope.
    assert world["row3"].state == INQUIRY_PLACED


# ------------------------------------------------------------- happy path / footgun


def test_no_filters_reverts_every_placed_row_in_the_company_and_is_idempotent(api):
    """The documented footgun: every field omitted means every placed row, whoever it
    belongs to, across BOTH projects and BOTH suppliers - and a second identical call
    does nothing more."""
    client, db, _company_id, world = api

    first = client.post(UNPLACE_ALL, json={})

    assert first.status_code == 200, first.text
    assert first.json() == {"unplaced": 3}

    for key in ("row1", "row2", "row3"):
        db.refresh(world[key])
        row = world[key]
        assert row.state == INQUIRY_RAISED
        assert row.po_ref is None
        assert row.po_line_id is None
        assert "Unplaced from" in (row.note or "")

    # The row that was never placed is untouched either way.
    db.refresh(world["row4_raised"])
    assert world["row4_raised"].state == INQUIRY_RAISED
    assert world["row4_raised"].note is None

    claims = (
        db.query(OrderLinkClaim)
        .filter(
            OrderLinkClaim.po_number.in_([world["po_x"].po_number, world["po_y"].po_number]),
            OrderLinkClaim.source == "order_inquiry",
        )
        .all()
    )
    assert claims == []

    second = client.post(UNPLACE_ALL, json={})
    assert second.status_code == 200, second.text
    assert second.json() == {"unplaced": 0}

    for key in ("row1", "row2", "row3"):
        db.refresh(world[key])
        assert world[key].state == INQUIRY_RAISED


def test_no_filters_preview_matches_no_filters_post(api):
    client, _db, _company_id, _world = api

    preview = client.get(PREVIEW).json()
    assert preview["count"] == 3

    result = client.post(UNPLACE_ALL, json={})
    assert result.json()["unplaced"] == preview["count"]


# --------------------------------------------------------------- company isolation


def test_another_companys_placed_row_is_neither_previewed_nor_touched(api):
    """Placed directly through the SERVICE (not a second `TestClient`): a nested
    `_client()`/`_restore()` pair shares the same `app.dependency_overrides` dict as the
    outer one, and `_restore` unconditionally `.clear()`s it - wiping the fixture's own
    client out from under the test it is still running in. Going through the service
    layer for the other company's setup sidesteps that entirely."""
    client, db, _company_id, world = api
    from app.models.base import company_scope
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    other_id = _uid()
    with company_scope(db, None):
        db.add(Company(id=other_id, name=f"{MARKER} Other", code=f"ZZ{_uid()[:6]}"))
        db.flush()
        other_user = _user(db, f"{MARKER} Other user")
        other_world = _seed_world(db, other_id, other_user)
        with company_scope(db, frozenset({other_id})):
            ProjectOrderInquiryService(db).place_on_po(
                other_world["row1"].id,
                other_world["po_line_x"].id,
                actor_user_id=other_user,
            )
            db.commit()
        db.refresh(other_world["row1"])
        assert other_world["row1"].state == INQUIRY_PLACED

    preview = client.get(PREVIEW).json()
    assert preview["count"] == 3  # only this company's three placed rows

    result = client.post(UNPLACE_ALL, json={})
    assert result.json()["unplaced"] == 3

    with company_scope(db, None):
        db.refresh(other_world["row1"])
        assert other_world["row1"].state == INQUIRY_PLACED


# ------------------------------------------------------------------------ auth


def test_a_reader_without_the_action_permission_is_refused_the_preview(reader_api):
    client, _db, _company_id, _world = reader_api

    response = client.get(PREVIEW)

    assert response.status_code == 403


def test_a_reader_without_the_action_permission_is_refused_the_post(reader_api):
    client, _db, _company_id, _world = reader_api

    response = client.post(UNPLACE_ALL, json={})

    assert response.status_code == 403


# ------------------------------------------------------------------ validation


def test_a_malformed_project_id_on_preview_fails_clean_not_500(api_unplaced):
    client, db, _company_id, world = api_unplaced

    response = client.get(PREVIEW, params={"project_id": "not-a-uuid"})

    # `validate_uuid_path` treats a malformed id as a guaranteed-missing row - 404, not
    # 422 - which is this codebase's documented behaviour for every route that uses it
    # (see app/services/uuid_path_param.py). What matters here is that it is a clean,
    # typed failure and not a 500.
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"

    # And the session is not poisoned: a well-formed call right after still works.
    follow_up = client.get(PREVIEW, params={"project_id": world["project1"].id})
    assert follow_up.status_code == 200, follow_up.text


def test_a_malformed_supplier_id_on_post_fails_clean_and_does_not_poison_the_transaction(api_unplaced):
    client, db, _company_id, world = api_unplaced

    response = client.post(UNPLACE_ALL, json={"supplier_id": "not-a-uuid"})

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"

    follow_up = client.post(UNPLACE_ALL, json={"project_id": world["project1"].id})
    assert follow_up.status_code == 200, follow_up.text
    assert follow_up.json()["unplaced"] == 0  # nothing was ever placed in this fixture
