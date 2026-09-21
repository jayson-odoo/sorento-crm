"""S2 - the order inquiry HEADER list (`PLAN-oi-header-list-detail.md`,
`oi-header-list-detail-acceptance-criteria.md`, AC-LS-01..07).

TEST-FIRST (Phase 2): written against the UAC + the plan's "Contract" section, with NO
implementation to look at - none of `OrderInquiryHeaderService`, the
`/order-inquiry-headers` route or the response schema exists yet. Every test below must
fail today for a real reason (404 - the route is not mounted - or a body key missing on a
404 payload), never an import typo or a fixture bug.

**Envelope shape** (captain's ruling): the module convention wins over the plan's own
draft "Contract" text. `GET /order-inquiry-headers` returns the SAME `ListResponse`
shape (`app/schemas/common.py`) every other list route in this module already uses,
including the worklist's own `GET /order-inquiries` - `{ data: [Header], pagination:
{ total, page, limit }, ... }`. Every assertion below reads `body["data"]` /
`body["pagination"]["total"]` / `["page"]` / `["limit"]`.

**Router prefix**: confirmed as `/api/v1/project-sales/order-inquiry-headers*` (not
`/api/v1/projects/...`) - `app/api/v1/__init__.py` mounts
`app/api/v1/projects/order_inquiries.py`'s router under `/project-sales`, and every
route inside it is declared bare. The worklist's own `GET /order-inquiries` lives at
`/api/v1/project-sales/order-inquiries` today (confirmed against `test_planning_changes.
py`'s own `BASE`). Used throughout below.

Postgres only, via `tests/_pg_fixture.py`'s `blank_session` - an EMPTY scratch schema, not
the shared prod-copy database. Several of these ACs need an EXACT partition/count over
"every header the state/query touches", which is only safe to assert against a schema
this test itself created (never `LIMIT 1` or a bare count against the real, populated
database). Every FK is seeded here, `zzt-oi-hdrlist`-prefixed.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import event, text

from app.models.order import Customer, SalesOrder
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    ACK_AWAITING,
    ACK_CHANGED,
    ACK_REJECTED,
    INQUIRY_CANCELLED,
    INQUIRY_RAISED,
    IV_ORDER,
    OrderInquiry,
    OrderInquiryRow,
    ProjectSalesOrder,
)
from app.models.sales_agent import SalesAgent

from ._pg_fixture import blank_session

MARKER = "zzt-oi-hdrlist"
BASE = "/api/v1/project-sales"
HEADERS = f"{BASE}/order-inquiry-headers"
VIEW = "projects.projects.view"


# ---------------------------------------------------------------------------
# seeding
# ---------------------------------------------------------------------------


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db, name: str) -> str:
    from app.models.user import User

    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _product(db, code: str | None = None) -> Product:
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:6]}", uom_name="Unit")
    category = ProductCategory(
        id=_uid(), category_code=f"ZZT-{_uid()[:8]}", category_name=f"{MARKER} cat"
    )
    db.add_all([uom, category])
    db.flush()
    row = Product(
        id=_uid(),
        product_code=code or f"{MARKER}-{_uid()[:8]}".upper(),
        product_name=f"{MARKER} product",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("100.00"),
    )
    db.add(row)
    db.flush()
    return row


def _customer(db, company_id: str, name: str) -> Customer:
    row = Customer(
        id=_uid(), company_id=company_id, customer_code=f"ZZT-{_uid()[:8]}", customer_name=name
    )
    db.add(row)
    db.flush()
    return row


def _agent(db, name: str) -> SalesAgent:
    row = SalesAgent(
        id=_uid(), sales_agent=f"ZZT{_uid()[:6]}".upper(), person_label=name
    )
    db.add(row)
    db.flush()
    return row


def _header(
    db,
    company_id: str,
    *,
    so_number: str | None = None,
    customer: Customer | None = None,
    agent: SalesAgent | None = None,
    project_id: str | None = None,
    project_label: str | None = None,
    so_date: date = date(2026, 1, 8),
    rows: list[dict] | None = None,
) -> dict:
    """One header: a core `SalesOrder`, an ADOPTED `ProjectSalesOrder` (no full project
    registration needed - `project_id` stays NULL unless a caller passes a real one,
    exactly `test_oi_project_label_from_so.py::_adopted_order`'s own shape), one
    `OrderInquiry`, and the given rows (`state`/`ack_state`/`qty`/`item_code`/
    `stock_location`, one dict per row - defaults to a single AWAITING row)."""
    core = SalesOrder(
        id=_uid(),
        company_id=company_id,
        so_number=so_number or f"{MARKER}SO{_uid()[:8]}".upper(),
        customer_id=customer.id if customer else None,
        sales_agent_id=agent.id if agent else None,
        order_date=so_date,
        project_label=project_label,
        project_label_source="inquiry" if project_label else None,
    )
    db.add(core)
    db.flush()
    order = ProjectSalesOrder(
        id=_uid(),
        company_id=company_id,
        project_id=project_id,
        so_id=core.id,
        provisional_ref=core.so_number,
        autocount_doc_no=core.so_number,
        status="adopted",
    )
    db.add(order)
    db.flush()
    inquiry = OrderInquiry(
        id=_uid(), company_id=company_id, project_sales_order_id=order.id, state=INQUIRY_RAISED
    )
    db.add(inquiry)
    db.flush()

    built_rows = []
    for spec in rows or [{}]:
        product = _product(db, spec.get("product_code"))
        row = OrderInquiryRow(
            id=_uid(),
            company_id=company_id,
            order_inquiry_id=inquiry.id,
            item_code=spec.get("item_code", product.product_code),
            stock_location=spec.get("stock_location"),
            qty=Decimal(str(spec.get("qty", "10"))),
            verb=IV_ORDER,
            state=spec.get("state", INQUIRY_RAISED),
            ack_state=spec.get("ack_state", ACK_AWAITING),
        )
        db.add(row)
        db.flush()
        built_rows.append(row)
    db.commit()
    return {"core": core, "pso": order, "inquiry": inquiry, "rows": built_rows}


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
    UserPermissionService.check_user_has_permission = lambda self, uid, slug: slug in granted
    UserPermissionService.get_user_permission_slugs = lambda self, uid: list(granted)
    return TestClient(app), originals


def _restore(originals) -> None:
    from app.main import app
    from app.services.user_service import UserPermissionService

    UserPermissionService.check_user_has_permission = originals[0]
    UserPermissionService.get_user_permission_slugs = originals[1]
    app.dependency_overrides.clear()


@pytest.fixture()
def api():
    from app.models.base import company_scope
    from app.services import project_seed_service

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        user_id = _user(db, f"{MARKER} Eling")
        db.commit()
        client, originals = _client(db, user_id, [VIEW])
        try:
            with company_scope(db, frozenset({company_id})):
                yield client, db, company_id
        finally:
            _restore(originals)


class _QueryCounter:
    """Counts SELECTs issued on one bind, for AC-LS-06 (bounded queries per page)."""

    def __init__(self, bind):
        self.bind = bind
        self.count = 0

    def __enter__(self):
        event.listen(self.bind, "before_cursor_execute", self._on)
        return self

    def __exit__(self, *exc):
        event.remove(self.bind, "before_cursor_execute", self._on)
        return False

    def _on(self, conn, cursor, statement, parameters, context, executemany):
        head = statement.strip().split(None, 1)[0].upper()
        if head in ("SELECT", "WITH"):
            self.count += 1


# =============================================================================
# AC-LS-01 - every contract field, 403 without the view permission
# =============================================================================


def test_every_contract_field_is_on_the_wire_AC_LS_01(api):
    client, db, company_id = api
    seeded = _header(db, company_id)

    response = client.get(HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert "data" in body, "the envelope is ListResponse, same as every other list route"
    assert "pagination" in body
    for key in ("total", "page", "limit"):
        assert key in body["pagination"], f"pagination.{key} missing from the envelope"
    row = next(item for item in body["data"] if item["id"] == seeded["inquiry"].id)

    # response_model silently drops a field it was not told about - assert each one.
    for key in (
        "id",
        "inquiry_no",
        "legacy_inquiry_no",
        "raised_at",
        "raised_by_name",
        "sales_order_id",
        "project_sales_order_id",
        "so_number",
        "so_date",
        "customer_name",
        "customer_code",
        "project_id",
        "project_title",
        "agent_name",
        "lines_total",
        "lines_to_confirm",
        "qty_total",
        "status",
    ):
        assert key in row, f"contract field {key!r} missing from the wire"


def test_403_without_the_view_permission_AC_LS_01(api):
    _client, db, company_id = api
    no_view, originals = _client_no_view(db)
    try:
        response = no_view.get(HEADERS)
        assert response.status_code == 403, response.text
    finally:
        _restore(originals)


def _client_no_view(db):
    user_id = _user(db, f"{MARKER} NoView")
    db.commit()
    return _client(db, user_id, [])


# =============================================================================
# AC-LS-02 - state partition
# =============================================================================


def test_state_partitions_outstanding_completed_and_all_AC_LS_02(api):
    client, db, company_id = api

    awaiting = _header(db, company_id, rows=[{"ack_state": ACK_AWAITING}])
    changed = _header(db, company_id, rows=[{"ack_state": ACK_CHANGED}])
    acknowledged = _header(db, company_id, rows=[{"ack_state": ACK_ACKNOWLEDGED}])
    only_cancelled = _header(
        db, company_id, rows=[{"ack_state": ACK_AWAITING, "state": INQUIRY_CANCELLED}]
    )
    rejected_remaining = _header(db, company_id, rows=[{"ack_state": ACK_REJECTED}])

    seeded = {
        "outstanding": {awaiting["inquiry"].id, changed["inquiry"].id},
        "completed": {
            acknowledged["inquiry"].id,
            only_cancelled["inquiry"].id,
            rejected_remaining["inquiry"].id,
        },
    }
    every_id = seeded["outstanding"] | seeded["completed"]

    default = client.get(HEADERS)
    assert default.status_code == 200, default.text
    default_ids = {item["id"] for item in default.json()["data"]} & every_id
    assert default_ids == seeded["outstanding"], "default is Outstanding"

    outstanding = client.get(HEADERS, params={"state": "outstanding"})
    assert outstanding.status_code == 200, outstanding.text
    ids = {item["id"] for item in outstanding.json()["data"]} & every_id
    assert ids == seeded["outstanding"]

    completed = client.get(HEADERS, params={"state": "completed"})
    assert completed.status_code == 200, completed.text
    ids = {item["id"] for item in completed.json()["data"]} & every_id
    assert ids == seeded["completed"]

    everything = client.get(HEADERS, params={"state": "all"})
    assert everything.status_code == 200, everything.text
    ids = {item["id"] for item in everything.json()["data"]} & every_id
    assert ids == every_id

    bogus = client.get(HEADERS, params={"state": "bogus"})
    assert bogus.status_code == 422, bogus.text


# =============================================================================
# AC-LS-03 - default order + sort vocabulary
# =============================================================================


def test_default_order_is_raised_at_asc_with_id_tiebreak_AC_LS_03(api):
    client, db, company_id = api
    same_time = datetime(2026, 9, 1, 8, 0)
    earlier = _header(db, company_id)
    earlier["inquiry"].raised_at = datetime(2026, 8, 1, 8, 0)
    tie_a = _header(db, company_id)
    tie_a["inquiry"].raised_at = same_time
    tie_b = _header(db, company_id)
    tie_b["inquiry"].raised_at = same_time
    db.commit()

    response = client.get(HEADERS, params={"state": "all"})
    assert response.status_code == 200, response.text
    ids_in_order = [item["id"] for item in response.json()["data"]]
    seeded_ids = {earlier["inquiry"].id, tie_a["inquiry"].id, tie_b["inquiry"].id}
    seeded_in_order = [i for i in ids_in_order if i in seeded_ids]

    expected_tie_order = sorted([tie_a["inquiry"].id, tie_b["inquiry"].id])
    assert seeded_in_order == [earlier["inquiry"].id] + expected_tie_order


@pytest.mark.parametrize(
    "sort_key",
    [
        "raised_at",
        "inquiry_no",
        "so_number",
        "raised_by",
        "lines_total",
        "qty_total",
        "customer",
        "project",
        "agent",
        "so_date",
        "status",
    ],
)
def test_every_documented_sort_key_is_accepted_AC_LS_03(api, sort_key):
    client, db, company_id = api
    _header(db, company_id)
    response = client.get(HEADERS, params={"sort": sort_key, "state": "all"})
    assert response.status_code == 200, f"{sort_key}: {response.text}"


def test_an_unknown_sort_key_is_422_AC_LS_03(api):
    client, db, company_id = api
    response = client.get(HEADERS, params={"sort": "bogus"})
    assert response.status_code == 422, response.text


# =============================================================================
# AC-LS-04 - query + exact filters
# =============================================================================


class TestQueryAndFilters:
    def test_query_matches_inquiry_no_AC_LS_04(self, api):
        client, db, company_id = api
        seeded = _header(db, company_id)
        needle = seeded["inquiry"].inquiry_no
        response = client.get(HEADERS, params={"query": needle, "state": "all"})
        assert response.status_code == 200, response.text
        ids = {item["id"] for item in response.json()["data"]}
        assert seeded["inquiry"].id in ids

    def test_query_matches_legacy_inquiry_no_AC_LS_04(self, api):
        """`legacy_inquiry_no` is `String(20)` by design - real legacy numbers look like
        `OI-000477` - so the fixture value has to fit that width, not the (much longer)
        MARKER-prefixed style every other seeded value here uses."""
        client, db, company_id = api
        seeded = _header(db, company_id)
        # 9 chars: well inside String(20), and unique enough not to collide with
        # anything else seeded in this test's own scratch schema.
        legacy_no = f"OI-9{str(uuid.uuid4().int)[-5:]}"
        seeded["inquiry"].legacy_inquiry_no = legacy_no
        db.commit()
        response = client.get(HEADERS, params={"query": legacy_no, "state": "all"})
        assert response.status_code == 200, response.text
        ids = {item["id"] for item in response.json()["data"]}
        assert seeded["inquiry"].id in ids

    def test_query_matches_so_number_customer_project_agent_AC_LS_04(self, api):
        client, db, company_id = api
        customer = _customer(db, company_id, f"{MARKER} Optad Sdn Bhd")
        agent = _agent(db, f"{MARKER} Sean")
        so_number = f"{MARKER}SO{_uid()[:8]}".upper()
        seeded = _header(
            db,
            company_id,
            so_number=so_number,
            customer=customer,
            agent=agent,
            project_label=f"{MARKER} Tuju Residences",
        )
        db.commit()

        for needle in (so_number, customer.customer_name, "Tuju Residences", "Sean"):
            response = client.get(HEADERS, params={"query": needle, "state": "all"})
            assert response.status_code == 200, response.text
            ids = {item["id"] for item in response.json()["data"]}
            assert seeded["inquiry"].id in ids, f"query {needle!r} should have matched"

    def test_query_matches_a_non_cancelled_rows_item_code_and_location_returned_once(
        self, api
    ):
        client, db, company_id = api
        item_code = f"{MARKER}-ITM-{_uid()[:6]}".upper()
        location = f"{MARKER}-LOC-{_uid()[:6]}".upper()
        seeded = _header(
            db,
            company_id,
            rows=[
                {"item_code": item_code, "stock_location": location},
                {"ack_state": ACK_AWAITING},
                {"ack_state": ACK_CHANGED},
            ],
        )

        for needle in (item_code, location):
            response = client.get(HEADERS, params={"query": needle, "state": "all"})
            assert response.status_code == 200, response.text
            items = response.json()["data"]
            matches = [item for item in items if item["id"] == seeded["inquiry"].id]
            assert len(matches) == 1, "one header, however many of its rows match"

    def test_query_matching_only_a_cancelled_row_does_not_return_the_header_AC_LS_04(
        self, api
    ):
        client, db, company_id = api
        item_code = f"{MARKER}-CANCELLED-{_uid()[:6]}".upper()
        seeded = _header(
            db, company_id, rows=[{"item_code": item_code, "state": INQUIRY_CANCELLED}]
        )
        response = client.get(HEADERS, params={"query": item_code, "state": "all"})
        assert response.status_code == 200, response.text
        ids = {item["id"] for item in response.json()["data"]}
        assert seeded["inquiry"].id not in ids

    def test_raised_by_agent_project_filter_exactly_AC_LS_04(self, api):
        client, db, company_id = api
        agent = _agent(db, f"{MARKER} Exact")
        raiser = _user(db, f"{MARKER} Raiser")
        project_label = f"{MARKER} Exact Project"
        seeded = _header(db, company_id, agent=agent, project_label=project_label)
        seeded["inquiry"].raised_by = raiser
        other = _header(db, company_id)
        db.commit()

        response = client.get(
            HEADERS, params={"raised_by": raiser, "state": "all"}
        )
        assert response.status_code == 200, response.text
        ids = {item["id"] for item in response.json()["data"]}
        assert seeded["inquiry"].id in ids
        assert other["inquiry"].id not in ids

        response = client.get(HEADERS, params={"agent": agent.person_label, "state": "all"})
        assert response.status_code == 200, response.text
        ids = {item["id"] for item in response.json()["data"]}
        assert seeded["inquiry"].id in ids
        assert other["inquiry"].id not in ids

        # B2 (reviewer): `project` is free TEXT on `_PROJECT_TITLE`, not
        # `ProjectSalesOrder.project_id` - an adopted order (this fixture's own shape)
        # never carries a registered project, so a uuid-shaped filter could never match
        # any header a real company has.
        response = client.get(HEADERS, params={"project": project_label, "state": "all"})
        assert response.status_code == 200, response.text
        ids = {item["id"] for item in response.json()["data"]}
        assert seeded["inquiry"].id in ids

    def test_agent_with_no_person_label_falls_back_to_the_agent_code_AC_LS_04(self, api):
        """B1 (reviewer): `person_label` is NULL for every one of the 80 agents on the
        prod copy - `sales_agents.sales_agent` is the name purchasing actually knows.
        Seeded directly rather than through `_agent()`, which always sets a label."""
        client, db, company_id = api
        agent = SalesAgent(
            id=_uid(), sales_agent=f"ZZT{_uid()[:6]}".upper(), person_label=None
        )
        db.add(agent)
        db.flush()
        seeded = _header(db, company_id, agent=agent)
        other = _header(db, company_id)
        db.commit()

        response = client.get(HEADERS, params={"state": "all"})
        assert response.status_code == 200, response.text
        row = next(item for item in response.json()["data"] if item["id"] == seeded["inquiry"].id)
        assert row["agent_name"] == agent.sales_agent

        response = client.get(HEADERS, params={"agent": agent.sales_agent, "state": "all"})
        assert response.status_code == 200, response.text
        ids = {item["id"] for item in response.json()["data"]}
        assert seeded["inquiry"].id in ids
        assert other["inquiry"].id not in ids

        response = client.get(HEADERS, params={"query": agent.sales_agent, "state": "all"})
        assert response.status_code == 200, response.text
        ids = {item["id"] for item in response.json()["data"]}
        assert seeded["inquiry"].id in ids
        assert other["inquiry"].id not in ids
        assert other["inquiry"].id not in ids


# =============================================================================
# AC-LS-05 - aggregates ignore cancelled rows
# =============================================================================


def test_aggregates_ignore_cancelled_rows_AC_LS_05(api):
    client, db, company_id = api
    seeded = _header(
        db,
        company_id,
        rows=[
            {"qty": "10", "ack_state": ACK_AWAITING},
            {"qty": "5", "ack_state": ACK_CHANGED},
            {"qty": "999", "ack_state": ACK_AWAITING, "state": INQUIRY_CANCELLED},
        ],
    )
    response = client.get(HEADERS, params={"state": "all"})
    assert response.status_code == 200, response.text
    row = next(item for item in response.json()["data"] if item["id"] == seeded["inquiry"].id)
    assert row["lines_total"] == 2, "the cancelled row is excluded"
    assert row["lines_to_confirm"] == 2
    assert Decimal(row["qty_total"]) == Decimal("15"), "999 (cancelled) excluded"


# =============================================================================
# AC-LS-06 - bounded query count regardless of page size
# =============================================================================


def test_query_count_is_bounded_regardless_of_page_size_AC_LS_06(api):
    client, db, company_id = api
    for _ in range(12):
        _header(db, company_id)

    bind = db.get_bind()
    with _QueryCounter(bind) as counter_small:
        small_page = client.get(HEADERS, params={"limit": 3, "state": "all"})
    assert small_page.status_code == 200, small_page.text
    small_count = counter_small.count

    with _QueryCounter(bind) as counter_big:
        big_page = client.get(HEADERS, params={"limit": 12, "state": "all"})
    assert big_page.status_code == 200, big_page.text
    big_count = counter_big.count

    assert small_count == big_count, (
        f"query count must not grow with page size: {small_count} vs {big_count}"
    )


# =============================================================================
# AC-LS-07 - company scoping
# =============================================================================


def test_a_header_from_another_company_is_invisible_AC_LS_07(api):
    from app.models.company import Company

    client, db, company_id = api
    mine = _header(db, company_id)

    other_company = Company(id=_uid(), name=f"{MARKER} Other Co", code=f"ZZT{_uid()[:6]}")
    db.add(other_company)
    db.flush()
    theirs = _header(db, other_company.id)

    response = client.get(HEADERS, params={"state": "all"})
    assert response.status_code == 200, response.text
    ids = {item["id"] for item in response.json()["data"]}
    assert mine["inquiry"].id in ids
    assert theirs["inquiry"].id not in ids
