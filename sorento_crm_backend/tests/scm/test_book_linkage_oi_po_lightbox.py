"""Book linkage's SECOND surface: the order-inquiry worklist's PO lightbox ("PO no" cell's
popup), `GET /api/v1/project-sales/order-inquiries/po/{po_id}`.

REWRITTEN 9 Sep 2026 alongside `tests/scm/test_book_linkage_po_lines.py` - read that
file's docstring for the owner ruling this reverses and the numbers behind it. Both
surfaces now read the line's OWN `purchase_order_lines.from_so_line_ref`, resolved at
DOCUMENT level against `sales_orders.source_ref` (the ref's `{database}:{DocKey}` half;
the `DtlKey` is unused), rather than `scm.order_link_claim`. The two surfaces must answer
IDENTICALLY: one fact, one presentation.

The shape this file repeats from its sibling: `requires_pg`, a `MARKER` prefix on every
seeded code, its own seeded sales-order chain (never `LIMIT 1` off an existing table), the
`scm_app` savepoint fixture (rolled back), and `grant_permission` from
`tests/scm/conftest.py`.

Gated on `projects.projects.view` (`order_inquiries.VIEW`), not `scm.dashboard.view` -
the same permission gotcha the worklist itself already works around.
"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import event

from app.models.base import set_company_scope
from app.models.company import Company
from app.services.scm import order_link_service
from tests.scm._book_linkage_fixtures import (
    book_ref,
    doc_key_ref,
    response_lines as _lines,
    seed_po,
    seed_sales_order,
)
from tests.scm.conftest import (
    SORENTO_COMPANY_ID,
    _REF_PRODUCT_CODE,
    _REF_WAREHOUSE_CODE,
    as_user,
    grant_permission,
    requires_pg,
    seed_user,
)

pytestmark = requires_pg

MARKER = "ZZTBOOKOIPO"

VIEW = "projects.projects.view"
BASE = "/api/v1/project-sales"

#: The database segment of every ref and document key this file seeds. Marker-prefixed, so
#: it cannot collide with the real book's own `AED_SORENTO` rows on the prod copy.
BOOK = f"AED_{MARKER}"

#: Thin, file-local wrappers over `tests.scm._book_linkage_fixtures` (review of PR #764,
#: F8) - see that module and `test_book_linkage_po_lines.py`'s identical wrapper block.


def _book_ref(doc_key: str, dtl_key: str) -> str:
    """AutoCount's own `"{database}:{DocKey}:{DtlKey}"`. A machine key, and the thing that
    must NEVER reach the wire on this surface either."""
    return book_ref(BOOK, doc_key, dtl_key)


def _doc_key(doc_key: str) -> str:
    """The `"{database}:{DocKey}"` half a `sales_orders.source_ref` carries."""
    return doc_key_ref(BOOK, doc_key)


def _as(scm_app, role_slug="purchasing"):
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, role_slug)
    grant_permission(db, role_slug, VIEW)
    as_user(app, gcu, gcuak, uid)
    return app, db


def _seed_po(db, *, n_lines: int = 1, marker: str | None = None,
             refs: list[str | None] | None = None) -> tuple[str, list[str]]:
    """A purchase order this test owns, with ``n_lines`` open lines and each line's
    ``from_so_line_ref`` set positionally from ``refs``.

    Identical seeding to `test_book_linkage_po_lines.py`'s own `_seed_po` - both delegate to
    `tests.scm._book_linkage_fixtures.seed_po` - so the two surfaces are asked the same
    question about the same shape of document.
    """
    return seed_po(
        db, marker=marker or f"{MARKER}-{uuid.uuid4().hex[:8]}", n_lines=n_lines, refs=refs,
    )


def _seed_po_distinct_lines(
    db, marker: str, product_codes: list[str], refs: list[str | None],
) -> tuple[str, list[str]]:
    """A purchase order whose lines carry DISTINCT products, one per entry of
    `product_codes`, in ASCENDING code order - `get_po_detail` orders its lines by
    `Product.product_code.asc()`, and this is how a test tells which returned line is
    which without an id on the wire (`OrderInquiryPoDetailLine` carries none, by design).

    Reuses the reference category/uom `ensure_reference_data` already seeded, rather than
    a fresh `LIMIT 1` borrow.
    """
    from app.models.inventory import Warehouse
    from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
    from app.models.product import Product

    ref = db.query(Product).filter(Product.product_code == _REF_PRODUCT_CODE).one()
    warehouse = (
        db.query(Warehouse).filter(Warehouse.warehouse_code == _REF_WAREHOUSE_CODE).one()
    )
    supplier = Supplier(
        id=str(uuid.uuid4()), supplier_code=marker[:30], supplier_name=f"{marker} supplier",
    )
    db.add(supplier)
    db.flush()
    po = PurchaseOrder(
        id=str(uuid.uuid4()), po_number=marker, supplier_id=str(supplier.id),
        status="active", issue_date=date(2026, 7, 16), expected_date=date(2026, 8, 4),
    )
    db.add(po)
    db.flush()
    line_ids = []
    for i, code in enumerate(product_codes):
        product = Product(
            id=str(uuid.uuid4()), product_code=code, product_name=f"{marker} product {i}",
            category_id=ref.category_id, base_uom_id=ref.base_uom_id, list_price=0,
        )
        db.add(product)
        db.flush()
        line = PurchaseOrderLine(
            id=str(uuid.uuid4()), purchase_order_id=str(po.id), product_id=str(product.id),
            warehouse_id=str(warehouse.id), qty_ordered=100, qty_received=0,
            line_status="open", expected_date=date(2026, 8, 4), source_ref=str(i + 1),
            from_so_line_ref=refs[i],
        )
        db.add(line)
        db.flush()
        line_ids.append(str(line.id))
    return str(po.id), line_ids


def _seed_sales_order(db, *, doc_key: str, so_number: str) -> str:
    """A sales order HEADER whose ``source_ref`` is the book's ``{database}:{DocKey}``, and
    deliberately NO lines - the number belongs to the ORDER, so a held header is enough to
    name it."""
    return seed_sales_order(db, book=BOOK, doc_key=doc_key, so_number=so_number)


def _seed_placed_row(db, marker: str, po_line_id: str, *, qty=10) -> str:
    """An order-inquiry row + link occupying `po_line_id`, so the Allocated to panel has a
    real row to answer with - same shape `test_po_bulk_delete.py::_seed_placed_row` uses.
    Returns the row id (unused by these tests, kept for parity/readability)."""
    from app.models.project_so import (
        INQUIRY_PLACED,
        IV_ORDER,
        OrderInquiry,
        OrderInquiryLink,
        OrderInquiryRow,
        ProjectSalesOrder,
    )

    order = ProjectSalesOrder(id=str(uuid.uuid4()), provisional_ref=marker)
    db.add(order)
    db.flush()
    inquiry = OrderInquiry(id=str(uuid.uuid4()), project_sales_order_id=order.id)
    db.add(inquiry)
    db.flush()
    row = OrderInquiryRow(
        id=str(uuid.uuid4()), order_inquiry_id=inquiry.id, item_code=marker, qty=qty,
        verb=IV_ORDER, state=INQUIRY_PLACED, po_ref=marker, po_line_id=po_line_id,
        note="pre-existing note",
    )
    db.add(row)
    db.flush()
    db.add(
        OrderInquiryLink(
            id=str(uuid.uuid4()), row_id=row.id, po_line_id=po_line_id,
            document=marker, qty=qty, auto=True,
        )
    )
    db.flush()
    return str(row.id)


def test_line_whose_book_ref_resolves_names_the_sales_order(scm_app):
    """A line whose ref's DOCUMENT key names a sales order this CRM holds prints that
    number, exactly as the SCM purchase-order detail does. Header only, no
    `sales_order_lines` row: the case the line-level join could not answer."""
    app, db = _as(scm_app)
    _seed_sales_order(db, doc_key="45322312", so_number=f"{MARKER}SO391853")
    po_id, _ids = _seed_po(db, refs=[_book_ref("45322312", "45322332")])

    with TestClient(app) as c:
        res = c.get(f"{BASE}/order-inquiries/po/{po_id}")
    line = _lines(res)[0]
    assert line["book_so_number"] == f"{MARKER}SO391853"
    assert line["book_so_unresolved"] is False


def test_line_with_no_book_ref_names_nothing_and_never_fabricates(scm_app):
    """A line the book links to nothing prints a muted dash: null number, and NOT the
    unresolved state, which is what makes the dash distinguishable."""
    app, db = _as(scm_app)
    po_id, _ids = _seed_po(db, refs=[None])

    with TestClient(app) as c:
        res = c.get(f"{BASE}/order-inquiries/po/{po_id}")
    line = _lines(res)[0]
    assert line["book_so_number"] is None
    assert line["book_so_unresolved"] is False


def test_ref_whose_document_key_names_nothing_is_its_own_state_not_a_dash(scm_app):
    """The third state on this surface too: the book names a sales order this CRM does not
    hold. It must not collapse into "nothing linked" - on the current book that is most of
    the linked lines, `202607-S0082`'s 14 of 14 among them."""
    app, db = _as(scm_app)
    po_id, _ids = _seed_po(db, refs=[_book_ref("99000001", "99000002")])

    with TestClient(app) as c:
        res = c.get(f"{BASE}/order-inquiries/po/{po_id}")
    line = _lines(res)[0]
    assert line["book_so_number"] is None
    assert line["book_so_unresolved"] is True


def test_the_raw_autocount_ref_never_reaches_the_wire(scm_app):
    """`from_so_line_ref` is a machine key and no machine identifier reaches the UI - the
    same reason `from_po_line_ref` is never printed. Asserted over the WHOLE response body.
    The DOCUMENT key must not leak either: it is half the same machine key."""
    app, db = _as(scm_app)
    _seed_sales_order(db, doc_key="44563842", so_number=f"{MARKER}SOWIRE")
    po_id, _ids = _seed_po(
        db, n_lines=2,
        refs=[_book_ref("44563842", "44563894"), _book_ref("44332866", "44333036")],
    )

    with TestClient(app) as c:
        res = c.get(f"{BASE}/order-inquiries/po/{po_id}")
    assert res.status_code == 200, res.text
    assert BOOK not in res.text, "the raw book ref leaked into the response"
    assert "44563842" not in res.text, "the ref's DocKey leaked into the response"
    assert "44563894" not in res.text, "the ref's DtlKey leaked into the response"
    # And the fact still arrived, so this cannot pass on an empty body.
    assert {ln["book_so_number"] for ln in res.json()["lines"]} == {
        f"{MARKER}SOWIRE", None,
    }


def test_field_survives_response_model_at_the_http_surface(scm_app):
    """Named explicitly so it cannot silently regress: both fields are DECLARED on
    `OrderInquiryPoDetailLine`, so `response_model` does not silently drop them - the exact
    bug that has already hit this feature twice."""
    app, db = _as(scm_app)
    _seed_sales_order(db, doc_key="45287499", so_number=f"{MARKER}SORESPMODEL")
    po_id, _ids = _seed_po(db, refs=[_book_ref("45287499", "45287503")])

    with TestClient(app) as c:
        res = c.get(f"{BASE}/order-inquiries/po/{po_id}")
    line = _lines(res)[0]
    assert "book_so_number" in line, "response_model dropped book_so_number"
    assert "book_so_unresolved" in line, "response_model dropped book_so_unresolved"
    assert line["book_so_number"] == f"{MARKER}SORESPMODEL", (
        "the field is declared but its VALUE was lost"
    )


def test_whole_document_costs_one_resolution_query_whatever_its_line_count(scm_app):
    """AC-A5's rule on this surface: the query count is CONSTANT in the number of lines.
    Counted around the route itself, not the reader, so an N+1 reintroduced anywhere
    between the router and the resolver is caught."""
    app, db = _as(scm_app)
    small_refs = [_book_ref(f"4530{i:04d}", f"4531{i:04d}") for i in range(2)]
    large_refs = [_book_ref(f"4540{i:04d}", f"4541{i:04d}") for i in range(8)]
    for i, ref in enumerate(small_refs + large_refs):
        _seed_sales_order(db, doc_key=ref.split(":")[1], so_number=f"{MARKER}SOQ{i:03d}")
    small_po, _s = _seed_po(
        db, n_lines=2, marker=f"{MARKER}-QS-{uuid.uuid4().hex[:6]}", refs=small_refs,
    )
    large_po, _l = _seed_po(
        db, n_lines=8, marker=f"{MARKER}-QL-{uuid.uuid4().hex[:6]}", refs=large_refs,
    )
    db.flush()

    def _count_resolution_queries(po_id: str) -> int:
        """Statements carrying `sales_orders.source_ref`, which is the RESOLVER's own
        signature - no other read on this route selects or filters that column. Counting
        every statement, or even every `sales_orders` one, would fold in the route's
        unrelated reads (the Allocated to panel queries `sales_orders` too) and make the
        assertion meaningless."""
        calls = {"n": 0}

        def _count(conn, cursor, statement, parameters, context, executemany):
            if "sales_orders.source_ref" in statement:
                calls["n"] += 1

        connection = db.connection()
        event.listen(connection, "before_cursor_execute", _count)
        try:
            with TestClient(app) as c:
                res = c.get(f"{BASE}/order-inquiries/po/{po_id}")
            assert res.status_code == 200, res.text
        finally:
            event.remove(connection, "before_cursor_execute", _count)
        return calls["n"]

    small_n = _count_resolution_queries(small_po)
    large_n = _count_resolution_queries(large_po)
    assert small_n == 1, f"a 2-line document must resolve in one query, took {small_n}"
    assert large_n == 1, (
        f"an 8-line document must cost no more than a 2-line one, took {large_n}"
    )


def test_a_sales_order_in_another_company_is_invisible(scm_app):
    """Company scoping holds on this surface too. `SalesOrder` is `CompanyScopedMixin`, so
    the plain ORM read is filtered by `do_orm_execute` and never raw SQL: the ref reads as
    unresolved rather than borrowing a stranger's number."""
    app, db = _as(scm_app)
    ref = _book_ref("45510140", "45510142")

    other_company = str(uuid.uuid4())
    db.add(Company(
        id=other_company, name=f"{MARKER} other company",
        code=f"{MARKER}-{uuid.uuid4().hex[:6]}".upper()[:50], is_active=True,
    ))
    db.flush()
    set_company_scope(db, frozenset({other_company}))
    _seed_sales_order(db, doc_key="45510140", so_number=f"{MARKER}SOFOREIGN")
    set_company_scope(db, frozenset({SORENTO_COMPANY_ID}))

    po_id, _ids = _seed_po(db, refs=[ref])

    assert order_link_service.book_so_numbers_by_ref(db, [ref]) == {}

    with TestClient(app) as c:
        res = c.get(f"{BASE}/order-inquiries/po/{po_id}")
    line = _lines(res)[0]
    assert line["book_so_number"] is None
    assert line["book_so_unresolved"] is True
    assert f"{MARKER}SOFOREIGN" not in res.text


def test_allocations_panel_unchanged_a_line_can_carry_link_allocation_both_or_neither(
    scm_app,
):
    """The existing `allocations` panel on the same response is unchanged and still
    populated independently - a line can carry a book link, an allocation, both, or
    neither."""
    app, db = _as(scm_app)
    marker = f"{MARKER}-BOTH-{uuid.uuid4().hex[:6]}"
    both_ref = _book_ref("44333034", "44333036")
    link_ref = _book_ref("45307155", "45307223")
    _seed_sales_order(db, doc_key="44333034", so_number=f"{MARKER}SOBOTH")
    _seed_sales_order(db, doc_key="45307155", so_number=f"{MARKER}SOLINKONLY")

    # Codes sorted ascending as written, so the response's line order (which carries no
    # id) is known: `get_po_detail` orders lines by `Product.product_code.asc()`.
    po_id, (both_line, link_only_line, alloc_only_line, neither_line) = (
        _seed_po_distinct_lines(
            db, marker,
            [f"{marker}-P1", f"{marker}-P2", f"{marker}-P3", f"{marker}-P4"],
            [both_ref, link_ref, None, None],
        )
    )

    # BOTH: a book linkage and an order-inquiry allocation on the same line.
    _seed_placed_row(db, f"{marker}-BOTH", both_line, qty=10)
    # Allocation only.
    _seed_placed_row(db, f"{marker}-ALLOC", alloc_only_line, qty=5)
    # The "neither" line gets nothing seeded.

    with TestClient(app) as c:
        res = c.get(f"{BASE}/order-inquiries/po/{po_id}")
    body = res.json()
    lines = _lines(res)

    by_id = {ln_id: ln for ln_id, ln in zip(
        (both_line, link_only_line, alloc_only_line, neither_line), lines
    )}

    assert by_id[both_line]["book_so_number"] == f"{MARKER}SOBOTH"
    assert by_id[link_only_line]["book_so_number"] == f"{MARKER}SOLINKONLY"
    assert by_id[alloc_only_line]["book_so_number"] is None
    assert by_id[alloc_only_line]["book_so_unresolved"] is False
    assert by_id[neither_line]["book_so_number"] is None
    assert by_id[neither_line]["book_so_unresolved"] is False

    allocation_docs = {a["so_number"] for a in body["allocations"]}
    assert f"{marker}-BOTH" in allocation_docs
    assert f"{marker}-ALLOC" in allocation_docs
    # The book-linkage-only line never wrote an order-inquiry allocation.
    assert f"{MARKER}SOLINKONLY" not in allocation_docs


def test_both_surfaces_answer_identically_for_the_same_line(scm_app):
    """One fact, one answer. The SCM purchase-order detail and this lightbox read the same
    column through the same resolver, so a line cannot come to say two different things
    depending on which screen opened it - the drift this whole rewrite exists to prevent.
    """
    app, db = _as(scm_app)
    _seed_sales_order(db, doc_key="45322330", so_number=f"{MARKER}SOPARITY")
    po_id, _ids = _seed_po(
        db, n_lines=3,
        refs=[_book_ref("45322330", "45322332"), _book_ref("99777001", "99777002"), None],
    )

    with TestClient(app) as c:
        lightbox = c.get(f"{BASE}/order-inquiries/po/{po_id}")
        detail = c.get(f"/api/v1/scm/purchase-orders/{po_id}")
    assert lightbox.status_code == 200, lightbox.text
    assert detail.status_code == 200, detail.text

    def _states(payload):
        pairs = [
            (ln["book_so_number"], ln["book_so_unresolved"]) for ln in payload["lines"]
        ]
        return sorted(pairs, key=lambda pair: (pair[0] or "", pair[1]))

    assert _states(lightbox.json()) == _states(detail.json())
    assert _states(lightbox.json()) == [
        (None, False), (None, True), (f"{MARKER}SOPARITY", False),
    ]
