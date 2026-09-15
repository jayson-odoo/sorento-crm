"""SCM Sales Orders list sorts by its "Order inquiries" column.

Contract: `GET /api/v1/scm/sales-orders?sort=order_inquiries&dir=desc|asc` orders by the
NUMBER of order inquiries raised against each sales order (count of
`projects.order_inquiries` rows, reached via `projects.sales_orders.so_id ==
sales_orders.id`) - most first on `desc`, fewest (orders with none) first on `asc` - ties
broken by `sales_orders.id`, like every other sort (`_order_by`,
`app/services/scm/sales_order_service.py:150-171`). The list already attaches
`order_inquiries` per row (`with_order_inquiries`, same file ~927), so the assertion reads
`len(row["order_inquiries"])` off the real response alongside the exact so_number order.

Helpers (`api` fixture, `_core_so`, `_project_so`) are imported from
`tests/test_planning_changes.py` rather than copied - same world, same Postgres chain
(`tests/_pg_fixture.blank_session`, scratch schema, never sqlite). `api`'s TestClient
already patches `UserPermissionService.check_user_has_permission` to `True` for any slug,
so it satisfies this route's `scm.dashboard.view` gate with no further setup.
"""
from __future__ import annotations

from app.models.project_so import OrderInquiry, SOAmendment
from tests.test_planning_changes import _core_so, _project_so, api  # noqa: F401

MARKER = "ZZT-OISORT"


def _inquiry(db, order, *, amendment_id=None) -> OrderInquiry:
    inquiry = OrderInquiry(project_sales_order_id=order.id, amendment_id=amendment_id)
    db.add(inquiry)
    db.flush()
    return inquiry


def _amendment(db, order) -> SOAmendment:
    amendment = SOAmendment(project_sales_order_id=order.id)
    db.add(amendment)
    db.flush()
    return amendment


def _renamed_core_so(db, world, *, letter: str):
    """A core SO whose number carries the shared marker, so `query=` on it can never pick
    up another row in the scratch schema - belt and braces alongside `blank_session`'s own
    per-test isolation."""
    so = _core_so(db, world.company_id)
    so.so_number = f"{MARKER}-{letter}-{so.so_number}"
    db.flush()
    return so


def _seed(world):
    """Three sales orders sharing the marker: A gets 2 inquiries (one on an amendment),
    B gets 1, C gets 0. Created C, B, A - `created_at DESC` would read [A, B, C], the same
    order `desc` on `order_inquiries` must ALSO produce, so a passing `desc` alone would
    not prove the sort is real; `asc` (which must read [C, B, A], the reverse of
    created_at) is the assertion that actually exercises it."""
    db = world.db
    c_so = _renamed_core_so(db, world, letter="C")
    b_so = _renamed_core_so(db, world, letter="B")
    a_so = _renamed_core_so(db, world, letter="A")

    b_order = _project_so(db, world.project, so_id=b_so.id, autocount_doc_no=b_so.so_number)
    _inquiry(db, b_order)

    a_order = _project_so(db, world.project, so_id=a_so.id, autocount_doc_no=a_so.so_number)
    _inquiry(db, a_order)
    amendment = _amendment(db, a_order)
    _inquiry(db, a_order, amendment_id=amendment.id)

    db.commit()
    return a_so, b_so, c_so


def _list(client, *, direction):
    response = client.get(
        "/api/v1/scm/sales-orders",
        params={
            "sort": "order_inquiries", "dir": direction, "query": MARKER, "limit": 50,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_sort_order_inquiries_desc_most_first(api):
    client, world = api
    a_so, b_so, c_so = _seed(world)

    rows = _list(client, direction="desc")
    numbers = [r["so_number"] for r in rows]
    counts = [len(r["order_inquiries"]) for r in rows]

    assert numbers == [a_so.so_number, b_so.so_number, c_so.so_number], numbers
    assert counts == [2, 1, 0], counts


def test_sort_order_inquiries_asc_fewest_first(api):
    """The direction the shared-`created_at`/id fallback does NOT already produce by
    accident - `created_at DESC` would read [A, B, C] here too, so this is the assertion
    that actually fails today (unknown sort key falls back to the default order)."""
    client, world = api
    a_so, b_so, c_so = _seed(world)

    rows = _list(client, direction="asc")
    numbers = [r["so_number"] for r in rows]
    counts = [len(r["order_inquiries"]) for r in rows]

    assert numbers == [c_so.so_number, b_so.so_number, a_so.so_number], numbers
    assert counts == [0, 1, 2], counts
