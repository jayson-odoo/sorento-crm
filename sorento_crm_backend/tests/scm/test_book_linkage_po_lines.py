"""Slice A of `PLAN-scm-book-linkage-on-document-lines.md` - the AutoCount book's SO
linkage, on the purchase order's own Lines tab.

REWRITTEN 9 Sep 2026. The first cut of this file asserted a `scm.order_link_claim` read
(`so_links_by_po_line`); the owner reversed that ruling the same day, and the column now
reads the line's OWN `purchase_order_lines.from_so_line_ref`. The evidence behind the
reversal, measured on `sorento_ai_automation_0907`:

* PO `202607-S0082` carries `from_so_line_ref` on all 14 of its lines and a RESOLVED claim
  on none of them, so the old column printed a dash on every line the book had linked.
* The claim table is many-to-many with no quantity: one 3-unit line of `C-FH14` carried 36
  claims naming 36 different sales orders, `SO324265` claimed 52 different PO lines, and
  `qty` is NULL on all 36,397 claim rows. Only 2,365 of 5,613 linked lines had exactly one
  sales order. `from_so_line_ref` is a single column holding a single value, which is the
  owner's model: one PO line, one sales order.

The ref resolves at DOCUMENT level: its first two segments (`{database}:{DocKey}`) are
looked up in `sales_orders.source_ref`, and the `DtlKey` is unused. The number on screen
is a property of the ORDER, so no `sales_order_lines` row need exist to name it - which is
why the seeding below creates sales-order HEADERS with no lines at all.

Every Slice A acceptance criterion is named in the test that covers it. `scm_app`
(savepoint-per-test, rolled back) with every row behind the `ZZTBOOKPO` marker.
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import event

from app.models.base import set_company_scope
from app.models.company import Company
from app.services.scm import order_link_service
from tests.scm._book_linkage_fixtures import (
    book_ref,
    doc_key_ref,
    ref_fks,
    response_lines as _lines,
    seed_po,
    seed_sales_order,
)
from tests.scm.conftest import (
    SORENTO_COMPANY_ID,
    as_user,
    requires_pg,
    seed_user,
)

pytestmark = requires_pg

MARKER = "ZZTBOOKPO"

#: The database segment of every ref and document key this file seeds. Marker-prefixed, so
#: it can never collide with the real book's own `AED_SORENTO` rows on the prod copy.
BOOK = f"AED_{MARKER}"

#: Thin, file-local wrappers over `tests.scm._book_linkage_fixtures` (review of PR #764,
#: F8): the shared functions take `book`/`marker` explicitly rather than closing over a
#: module constant, so this suite's rows and `test_book_linkage_oi_po_lightbox.py`'s
#: cannot collide on the shared prod-copy database.


def _book_ref(doc_key: str, dtl_key: str) -> str:
    """A ref exactly as the book sends it: `"{database}:{DocKey}:{DtlKey}"`. A machine key,
    and the thing that must NEVER reach the wire."""
    return book_ref(BOOK, doc_key, dtl_key)


def _doc_key(doc_key: str) -> str:
    """The `"{database}:{DocKey}"` half a `sales_orders.source_ref` carries."""
    return doc_key_ref(BOOK, doc_key)


def _as(scm_app, role_slug="purchasing"):
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, role_slug)
    as_user(app, gcu, gcuak, uid)
    return app, db


def _seed_po(db, *, n_lines: int = 1, marker: str | None = None,
             refs: list[str | None] | None = None) -> tuple[str, list[str]]:
    """A purchase order this test owns, with ``n_lines`` open lines.

    ``refs`` sets each line's ``from_so_line_ref`` positionally (``None`` leaves the line
    with no book linkage at all). Returns ``(po_id, [line_ids])`` in line order.
    """
    return seed_po(
        db, marker=marker or f"{MARKER}-{uuid.uuid4().hex[:8]}", n_lines=n_lines, refs=refs,
    )


def _seed_sales_order(db, *, doc_key: str, so_number: str) -> str:
    """A sales order HEADER whose ``source_ref`` is the book's ``{database}:{DocKey}``, and
    deliberately NO lines.

    That is the whole contract of the document-level join: the number on screen belongs to
    the ORDER, so a held header is sufficient to name it and a missing line cannot suppress
    it. Seeded in full rather than borrowed off an existing row - CI's database has no
    data, and a `LIMIT 1` off `sales_orders` would pick up whatever the last suite left.
    """
    return seed_sales_order(db, book=BOOK, doc_key=doc_key, so_number=so_number)


def _seed_sales_order_line(db, *, sales_order_id: str) -> str:
    """One line under an already-seeded header, for the single test that proves lines make
    no difference either way."""
    from app.models.order import SalesOrderLine

    product_id, warehouse_id = ref_fks(db)
    line = SalesOrderLine(
        id=str(uuid.uuid4()), sales_order_id=sales_order_id, product_id=product_id,
        warehouse_id=warehouse_id, qty_ordered=10, qty_delivered=0, line_status="open",
    )
    db.add(line)
    db.flush()
    return str(line.id)


def test_line_whose_book_ref_resolves_prints_that_sales_order(scm_app):
    """AC-A1 - a line whose `from_so_line_ref` names a sales order this CRM holds prints
    that sales order's number.

    The header alone is seeded, with NO `sales_order_lines` row. That is the case the
    line-level join could not answer and this one can: the ref's `DtlKey` names a line we
    do not hold, and the number is still nameable because it belongs to the document.
    """
    app, db = _as(scm_app)
    _seed_sales_order(db, doc_key="45322312", so_number=f"{MARKER}SO391853")
    po_id, _ids = _seed_po(db, refs=[_book_ref("45322312", "45322332")])

    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/purchase-orders/{po_id}")
    line = _lines(res)[0]
    assert line["book_so_number"] == f"{MARKER}SO391853"
    assert line["book_so_unresolved"] is False


def test_the_detail_key_is_ignored_and_the_lines_we_hold_change_nothing(scm_app):
    """The `DtlKey` is not part of the question. Two lines of one purchase order pointing
    at two DIFFERENT details of the SAME sales order both name that order, and seeding an
    actual `sales_order_lines` row under the header changes no answer."""
    app, db = _as(scm_app)
    so_id = _seed_sales_order(db, doc_key="45307155", so_number=f"{MARKER}SODETAIL")
    _seed_sales_order_line(db, sales_order_id=so_id)
    po_id, _ids = _seed_po(
        db, n_lines=2,
        refs=[_book_ref("45307155", "45307156"), _book_ref("45307155", "45307223")],
    )

    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/purchase-orders/{po_id}")
    numbers = [ln["book_so_number"] for ln in _lines(res)]
    assert numbers == [f"{MARKER}SODETAIL", f"{MARKER}SODETAIL"]


def test_line_with_no_book_ref_names_no_sales_order(scm_app):
    """AC-A2 - a line the book links to nothing prints a muted dash on the screen: null
    number AND `book_so_unresolved` false, which is what the dash is rendered from. Never
    a guess and never a value invented from the document number."""
    app, db = _as(scm_app)
    po_id, _ids = _seed_po(db, refs=[None])

    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/purchase-orders/{po_id}")
    line = _lines(res)[0]
    assert line["book_so_number"] is None
    assert line["book_so_unresolved"] is False


def test_ref_whose_document_key_names_nothing_is_its_own_state_not_a_dash(scm_app):
    """AC-A3 - the book names a sales order this CRM does not hold. A THIRD state, and it
    must be distinguishable from "nothing linked": on the 7 Sep book copy 21,633 of 33,225
    refs land here (`202607-S0082`'s 14 of 14 among them), so collapsing them into the dash
    would report an unlinked document for one the book has linked line by line."""
    app, db = _as(scm_app)
    # Nothing seeded under this document key at all.
    po_id, _ids = _seed_po(db, refs=[_book_ref("99000001", "99000002")])

    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/purchase-orders/{po_id}")
    line = _lines(res)[0]
    assert line["book_so_number"] is None
    assert line["book_so_unresolved"] is True, (
        "an unresolved ref must not read as 'nothing linked'"
    )


def test_a_malformed_ref_reads_as_unresolved_rather_than_crashing(scm_app):
    """A value that is not the documented `{database}:{DocKey}:{DtlKey}` shape has no
    document key to look up. It reads as "linked, not held" - honest for something we
    cannot parse - and must never raise or leak."""
    app, db = _as(scm_app)
    po_id, _ids = _seed_po(db, n_lines=2, refs=["nocolonsatall", f"{BOOK}:"])

    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/purchase-orders/{po_id}")
    for line in _lines(res):
        assert line["book_so_number"] is None
        assert line["book_so_unresolved"] is True
    assert "nocolonsatall" not in res.text


def test_the_raw_autocount_ref_never_reaches_the_wire(scm_app):
    """AC-A4 - `from_so_line_ref` is a machine key (`AED_SORENTO:<DocKey>:<DtlKey>`) and no
    machine identifier reaches the UI, the same reason `from_po_line_ref` is never printed.
    Asserted over the WHOLE response body, so a future field that happens to carry it is
    caught too. The DOCUMENT key must not leak either - it is half the same machine key."""
    app, db = _as(scm_app)
    _seed_sales_order(db, doc_key="44563842", so_number=f"{MARKER}SO391900")
    po_id, _ids = _seed_po(
        db, n_lines=2,
        refs=[_book_ref("44563842", "44563894"), _book_ref("44332866", "44333036")],
    )

    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/purchase-orders/{po_id}")
    assert res.status_code == 200, res.text
    body = res.text
    assert BOOK not in body, "the raw book ref leaked into the response"
    assert "44563842" not in body, "the ref's DocKey leaked into the response"
    assert "44563894" not in body, "the ref's DtlKey leaked into the response"
    # And the fact itself still arrived - otherwise this test would pass on an empty body.
    assert {ln["book_so_number"] for ln in res.json()["lines"]} == {
        f"{MARKER}SO391900", None,
    }


def test_whole_document_costs_one_resolution_query_whatever_its_line_count(scm_app):
    """AC-A5 - the QUERY COUNT, not the wall time. A per-line query would be 584 round
    trips on `202405-S0046`; asserted on the SHAPE (constant regardless of how many lines
    are asked about), not on a specific line count."""
    app, db = _as(scm_app)
    small_refs = [_book_ref(f"4530{i:04d}", f"4531{i:04d}") for i in range(2)]
    large_refs = [_book_ref(f"4540{i:04d}", f"4541{i:04d}") for i in range(8)]
    for i, ref in enumerate(small_refs + large_refs):
        _seed_sales_order(db, doc_key=ref.split(":")[1], so_number=f"{MARKER}SOA5{i:03d}")
    db.flush()

    def _count_queries(fn):
        calls = {"n": 0}

        def _count(conn, cursor, statement, parameters, context, executemany):
            calls["n"] += 1

        connection = db.connection()
        event.listen(connection, "before_cursor_execute", _count)
        try:
            fn()
        finally:
            event.remove(connection, "before_cursor_execute", _count)
        return calls["n"]

    small_n = _count_queries(
        lambda: order_link_service.book_so_numbers_by_ref(db, small_refs)
    )
    large_n = _count_queries(
        lambda: order_link_service.book_so_numbers_by_ref(db, large_refs)
    )
    assert small_n == 1, "one document's worth of lines must cost exactly one query"
    assert large_n == 1, "a bigger document must not cost more queries than a small one"


def test_many_lines_sharing_one_sales_order_still_cost_one_query(scm_app):
    """The common real shape: several lines of one purchase order raised for the SAME
    sales order. They collapse to one document key, and still one query."""
    app, db = _as(scm_app)
    _seed_sales_order(db, doc_key="45134803", so_number=f"{MARKER}SOSHARED")
    refs = [_book_ref("45134803", f"4528{i:04d}") for i in range(6)]

    calls = {"n": 0}

    def _count(conn, cursor, statement, parameters, context, executemany):
        calls["n"] += 1

    connection = db.connection()
    event.listen(connection, "before_cursor_execute", _count)
    try:
        found = order_link_service.book_so_numbers_by_ref(db, refs)
    finally:
        event.remove(connection, "before_cursor_execute", _count)

    assert calls["n"] == 1
    assert set(found.values()) == {f"{MARKER}SOSHARED"}
    assert len(found) == 6, "every ref is answered, keyed by the FULL ref it came in as"


def test_a_document_of_only_unlinked_lines_costs_no_query_at_all(scm_app):
    """AC-A5's floor: most documents carry no ref at all, and an empty ask must not reach
    the database to say so. A ref with no usable document key counts as empty too."""
    app, db = _as(scm_app)

    calls = {"n": 0}

    def _count(conn, cursor, statement, parameters, context, executemany):
        calls["n"] += 1

    connection = db.connection()
    event.listen(connection, "before_cursor_execute", _count)
    try:
        assert order_link_service.book_so_numbers_by_ref(db, []) == {}
        assert order_link_service.book_so_numbers_by_ref(db, [None, ""]) == {}
        assert order_link_service.book_so_numbers_by_ref(db, ["nocolons"]) == {}
    finally:
        event.remove(connection, "before_cursor_execute", _count)
    assert calls["n"] == 0


def test_a_sales_order_in_another_company_is_invisible(scm_app):
    """AC-A6 - the resolution is company-scoped. `SalesOrder` is `CompanyScopedMixin`, so
    the plain ORM read goes through the `do_orm_execute` filter and never raw SQL: another
    company's sales order cannot be named on this company's line, and the ref reads as
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

    assert order_link_service.book_so_numbers_by_ref(db, [ref]) == {}, (
        "a sales order stamped to another company is invisible"
    )

    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/purchase-orders/{po_id}")
    line = _lines(res)[0]
    assert line["book_so_number"] is None
    # Still LINKED as far as the book is concerned - just not by anything we may read.
    assert line["book_so_unresolved"] is True
    assert f"{MARKER}SOFOREIGN" not in res.text


def test_field_survives_response_model_at_the_http_surface(scm_app):
    """AC-C2, named for the bug: `response_model` silently drops any field the schema does
    not DECLARE, and this feature has already been bitten by it twice. Both fields are
    declared on `PurchaseOrderLine`; this asserts it at the HTTP surface, not the
    service."""
    app, db = _as(scm_app)
    _seed_sales_order(db, doc_key="45287499", so_number=f"{MARKER}SORESPMODEL")
    po_id, _ids = _seed_po(db, refs=[_book_ref("45287499", "45287503")])

    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/purchase-orders/{po_id}")
    line = _lines(res)[0]
    assert "book_so_number" in line, "response_model dropped book_so_number"
    assert "book_so_unresolved" in line, "response_model dropped book_so_unresolved"
    assert line["book_so_number"] == f"{MARKER}SORESPMODEL", (
        "the field is declared but its VALUE was lost"
    )


def test_the_column_survives_an_edit_of_the_order(scm_app):
    """The update route re-serializes the document and the screen renders THAT response,
    so a resolution missing from it blanks the column the moment a buyer saves an
    unrelated change."""
    app, db = _as(scm_app)
    _seed_sales_order(db, doc_key="44333034", so_number=f"{MARKER}SOAFTEREDIT")
    po_id, _ids = _seed_po(db, refs=[_book_ref("44333034", "44333036")])

    with TestClient(app) as c:
        res = c.put(
            f"/api/v1/scm/purchase-orders/{po_id}", json={"expected_date": "2026-08-11"}
        )
    line = _lines(res)[0]
    assert line["book_so_number"] == f"{MARKER}SOAFTEREDIT"


def test_allocations_panel_is_unchanged_alongside_the_new_column(scm_app):
    """AC-A7 - the allocations panel below still answers "who reserved this line through
    our own order-inquiry flow", independently of the book's own linkage. A line can carry
    one fact, the other, both or neither; this seeds BOTH on one line, naming DIFFERENT
    sales orders, so they co-exist rather than one crowding the other out."""
    app, db = _as(scm_app, "purchasing")
    from tests.scm.test_channel_read_model import _core_so_line
    from tests.scm.test_m3_run import _mk_product
    from tests.scm.test_po_detail_dedication_route import _active_po, _project_bin

    bin_id = _project_bin(db)
    pid = _mk_product(db, f"{MARKER}-A7-{uuid.uuid4().hex[:6].upper()}")
    po_id, line_id, number = _active_po(db, product_id=pid, warehouse_id=bin_id, qty=114)

    # The OLD fact: an order-inquiry claim reserving the line.
    claiming, claiming_line = _core_so_line(
        db, product_id=pid, warehouse_id=bin_id, qty=114, demand_class="project",
    )
    order_link_service.claim_placed_on_po(
        db, company_id=None, so_number=claiming.so_number, po_number=number,
        item_code=None, so_line_id=str(claiming_line.id), po_line_id=line_id,
        source=order_link_service.SOURCE_PO_UPLOAD,
    )

    # The NEW fact, on the same line and pointing somewhere ELSE entirely: the book says
    # this line was raised for a DIFFERENT sales order. The two must not merge.
    from app.models.procurement import PurchaseOrderLine

    _seed_sales_order(db, doc_key="43464500", so_number=f"{MARKER}SOBOOKA7")
    db.query(PurchaseOrderLine).filter(PurchaseOrderLine.id == line_id).update(
        {"from_so_line_ref": _book_ref("43464500", "45510329")}
    )
    db.flush()

    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/purchase-orders/{po_id}")
    assert res.status_code == 200, res.text
    body = res.json()

    # The OLD fact, at its old address, unchanged.
    blocks = body.get("allocations") or []
    block = next(b for b in blocks if b["line_id"] == line_id)
    assert [d["so_number"] for d in block["dedicated_to"]] == [claiming.so_number]

    # The NEW fact, on the line itself, naming its own sales order independently.
    line = next(ln for ln in body["lines"] if ln["id"] == line_id)
    assert line["book_so_number"] == f"{MARKER}SOBOOKA7"
    assert line["book_so_number"] != claiming.so_number


def test_each_line_of_a_document_answers_for_itself(scm_app):
    """AC-A8's data half: a document mixing all three states keeps them apart per line, so
    the column can render three things rather than two. One line resolved, one linked but
    not held, one not linked at all."""
    app, db = _as(scm_app)
    _seed_sales_order(db, doc_key="45322330", so_number=f"{MARKER}SOMIX")
    po_id, line_ids = _seed_po(
        db, n_lines=3,
        refs=[_book_ref("45322330", "45322332"), _book_ref("99777001", "99777002"), None],
    )

    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/purchase-orders/{po_id}")
    by_id = {ln["id"]: ln for ln in _lines(res)}

    assert by_id[line_ids[0]]["book_so_number"] == f"{MARKER}SOMIX"
    assert by_id[line_ids[0]]["book_so_unresolved"] is False

    assert by_id[line_ids[1]]["book_so_number"] is None
    assert by_id[line_ids[1]]["book_so_unresolved"] is True

    assert by_id[line_ids[2]]["book_so_number"] is None
    assert by_id[line_ids[2]]["book_so_unresolved"] is False


def test_the_answer_is_one_sales_order_never_a_list(scm_app):
    """The whole point of the reversal: the column holds ONE value, so there is no overflow
    to render and no `+N more` on either screen. A scalar on the wire is what makes that
    structurally true rather than a frontend convention."""
    app, db = _as(scm_app)
    _seed_sales_order(db, doc_key="45510327", so_number=f"{MARKER}SOONLYONE")
    po_id, _ids = _seed_po(db, refs=[_book_ref("45510327", "45510329")])

    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/purchase-orders/{po_id}")
    line = _lines(res)[0]
    assert isinstance(line["book_so_number"], str)
    assert "so_links" not in line, "the claim-based list is gone, not merely unused"


def test_serialize_without_book_so_by_ref_raises_instead_of_lying(scm_app):
    """Review of PR #764, F2/F4. `book_so_by_ref` used to default to `{}`, so a caller
    that forgot the kwarg got `book_so_unresolved=True` on every linked line - "linked, not
    held" for orders the CRM actually holds - rather than a loud failure at the call site.
    It is now a REQUIRED keyword argument with no default, so a forgotten kwarg is a
    `TypeError`, immediately, at the call that forgot it."""
    import pytest

    from app.models.procurement import PurchaseOrder
    from app.services.scm.purchase_order_service import PurchaseOrderService

    app, db = _as(scm_app)
    _seed_sales_order(db, doc_key="45510331", so_number=f"{MARKER}SOF2")
    po_id, _ids = _seed_po(db, refs=[_book_ref("45510331", "45510333")])

    svc = PurchaseOrderService(db)
    po = svc._base_query().filter(PurchaseOrder.id == po_id).first()

    with pytest.raises(TypeError):
        svc.serialize(po)  # book_so_by_ref omitted


def test_list_route_never_resolves_and_says_so_on_every_line(scm_app):
    """Review of PR #764, F2/F4. The list route must not run the resolver at all - no list
    consumer reads `book_so_number` - so every line reads `book_so_unresolved: null`
    (Python `None`), the FOURTH state meaning "not computed on this path", never `false`
    (which would claim the linkage was checked and found nothing)."""
    app, db = _as(scm_app)
    _seed_sales_order(db, doc_key="45510335", so_number=f"{MARKER}SOF2LIST")
    marker = f"{MARKER}-F2LIST-{uuid.uuid4().hex[:6]}"
    po_id, _ids = _seed_po(
        db, marker=marker, n_lines=2, refs=[_book_ref("45510335", "45510337"), None],
    )

    with TestClient(app) as c:
        res = c.get(
            "/api/v1/scm/purchase-orders", params={"documents": marker, "limit": 50}
        )
    assert res.status_code == 200, res.text
    rows = [row for row in res.json()["data"] if row["id"] == po_id]
    assert rows, "the seeded order must be on the page"
    for line in rows[0]["lines"]:
        assert line["book_so_number"] is None
        assert line["book_so_unresolved"] is None, (
            "the list path must read as NOT COMPUTED, not as 'nothing linked'"
        )


def test_get_one_still_resolves_for_real_alongside_the_unresolving_list(scm_app):
    """The other half of F2/F4: the list route not resolving must not regress the detail
    route, which still must answer for real - `book_so_unresolved` is a `bool`, never the
    list's `None`, and a real linkage still prints its number."""
    app, db = _as(scm_app)
    _seed_sales_order(db, doc_key="45510339", so_number=f"{MARKER}SOF2DETAIL")
    po_id, _ids = _seed_po(db, refs=[_book_ref("45510339", "45510341")])

    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/purchase-orders/{po_id}")
    line = _lines(res)[0]
    assert line["book_so_number"] == f"{MARKER}SOF2DETAIL"
    assert line["book_so_unresolved"] is False, "the detail route must resolve for real"
