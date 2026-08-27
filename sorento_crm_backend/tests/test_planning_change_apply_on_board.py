"""A changed sales order, applied from the board (`PLAN-scm-cs-planning-uat.md` part 3).

The fixture is SO381895 re-uploaded with form (3): SRTWCX7405-RL-S-PJ's three instalments -
10 on 25 August, 10 on 5 September, 5 on 10 September - become one line of 25 on 19 August.
What that costs the plan is eight rules, and each of them is one test here:

* AC-P3-5 the surviving line's inquiry row is UPDATED (same id, new quantity, new date, its
  links kept, the previous value on the row) and a second raised row is never created;
* AC-P3-6 a closed line's rows are CANCELLED, never deleted, and their links move first to
  the surviving raised row of the same product on the same order;
* AC-P3-7 a link whose document arrives after the new required date stays linked and reads
  "arrives late" - purchasing decides, nothing is unlinked for lateness;
* AC-P3-8 more linked than the new quantity unlinks the LATEST-dated link first, and writes
  no CANCEL_BALANCE for the drop;
* AC-P3-9 a transfer already MOVED for a line the book closed is flagged on the change row
  and no reverse transfer is created;
* AC-P3-10 a release of a wholly-Buy line moves a LINKED row to the pool with its links, and
  a row with none gets DELAY with the previous date;
* AC-P3-4 the board's Confirm carrying `batch_id` applies the batch and writes one revision,
  and a second call is refused with a message;
* AC-P3-11 `scm.committed_v` then counts 25 for the product on that order and nothing else.

Runs on the REAL database (`_pg_fixture.pg_session`), rolled back: `scm.committed_v` is a
view a migration installs and it does not exist in the blank scratch schema at all. Every
row is seeded here behind the marker - CI's database has no data.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import engine

from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.project_so import (
    INQUIRY_CANCELLED,
    INQUIRY_PARTLY_LINKED,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    IV_CANCEL_BALANCE,
    IV_ORDER,
    OrderInquiryLink,
    OrderInquiryRow,
)
from app.models.stock_transfer import TRANSFER_MOVED, StockTransfer
from app.services import planning_change_service, project_seed_service
from app.services.project_order_inquiry_service import ProjectOrderInquiryService
from app.services.scm.outstanding_diff import (
    CLOSED,
    DATE_AND_QTY_CHANGED,
    DATE_MOVED,
    QTY_CHANGED,
    Change,
    Diff,
    Line,
)

from .test_planning_changes import (
    BASE,
    MARKER,
    _client,
    _core_line,
    _core_so,
    _line_payload,
    _product,
    _project_line,
    _project_so,
    _restore,
    _sorento,
    _stock,
    _uid,
    _user,
    _warehouse,
)

# The fixture's own dates, so every assertion reads as the story does.
WAS_1 = date(2026, 8, 25)
WAS_2 = date(2026, 9, 5)
WAS_3 = date(2026, 9, 10)
NOW = date(2026, 8, 19)


class _World:
    def __init__(self, db, company_id, actor, project, product, own_wh, pool_wh):
        self.db = db
        self.company_id = company_id
        self.actor = actor
        self.project = project
        self.product = product
        self.own_wh = own_wh
        self.pool_wh = pool_wh


@contextmanager
def _real_db_session():
    """The REAL database, every write discarded, and a route's own `rollback()` survivable.

    `_pg_fixture.pg_session` cannot be used here. It joins the outer transaction in
    SQLAlchemy's `conditional_savepoint` mode, which on a plain (non-savepoint) outer
    transaction degrades to `rollback_only`: the first `db.rollback()` a ROUTE performs -
    and the refusal this file tests performs one - rolls the whole outer transaction back
    and takes the seeded world with it. `create_savepoint` is what `blank_session` already
    passes for exactly that reason; the only difference here is the schema, because
    `scm.committed_v` is a view a migration installs and the blank scratch schema has none.
    """
    connection = engine.connect()
    transaction = connection.begin()
    # `autoflush=False`, the way `app.database.SessionLocal` is built. An autoflushing test
    # session hides a whole class of defect: a service that mutates ORM state and then
    # QUERIES for it sees its own pending write under the test and an empty result in
    # production (measured live on SO381895, 26 August 2026 - both closed rows kept their
    # links while this suite was green).
    session = Session(
        bind=connection, join_transaction_mode="create_savepoint", autoflush=False
    )
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def world():
    from app.services.project_service import register_project

    with _real_db_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        actor = _user(db, f"{MARKER} Cyndi")
        project = register_project(
            db, company_id=company_id, actor_user_id=actor, developer_party_id=None,
            title=f"{MARKER} Yotu Builder {_uid()[:12]}",
        )
        product = _product(db)
        pool_wh = _warehouse(db, f"ZZT-BRW-{_uid()[:4]}", segment="dealer")
        own_wh = _warehouse(db, f"ZZT-IB-{_uid()[:4]}", segment="project",
                            pool_warehouse_id=pool_wh.id)
        db.flush()
        db.commit()
        yield _World(db, company_id, actor, project, product, own_wh, pool_wh)


@pytest.fixture()
def api(world):
    from app.models.base import company_scope

    client, originals = _client(world.db, world.actor)
    try:
        with company_scope(world.db, frozenset({world.company_id})):
            yield client, world
    finally:
        _restore(originals)


# ---------------------------------------------------------------------------
# seeding
# ---------------------------------------------------------------------------


def _supplier(world) -> Supplier:
    supplier = Supplier(
        id=_uid(), company_id=world.company_id, supplier_code=f"ZZT-{_uid()[:8]}",
        supplier_name=f"{MARKER} DAFUYUAN",
    )
    world.db.add(supplier)
    world.db.flush()
    return supplier


def _po_line(world, supplier, *, qty, expected_date, number=None):
    po = PurchaseOrder(
        id=_uid(), company_id=world.company_id,
        po_number=number or f"ZZT-PO-{_uid()[:8]}", supplier_id=supplier.id,
        issue_date=date(2026, 6, 1), status="active",
    )
    world.db.add(po)
    world.db.flush()
    line = PurchaseOrderLine(
        id=_uid(), company_id=world.company_id, purchase_order_id=po.id,
        product_id=world.product.id, warehouse_id=world.own_wh.id,
        qty_ordered=Decimal(str(qty)), qty_received=Decimal("0"),
        expected_date=expected_date, line_status="open",
    )
    world.db.add(line)
    world.db.flush()
    return po, line


def _link(world, row, po_line, *, qty, document):
    link = OrderInquiryLink(
        id=_uid(), company_id=world.company_id, row_id=row.id,
        po_line_id=po_line.id, document=document, qty=Decimal(str(qty)),
        linked_by=world.actor, linked_at=datetime.utcnow(),
    )
    world.db.add(link)
    world.db.flush()
    ProjectOrderInquiryService(world.db)._refresh_link_state([row])
    world.db.flush()
    return link


def _order_row(world, line):
    """The still-owed ORDER row this confirmation raised for `line`."""
    return (
        world.db.query(OrderInquiryRow)
        .filter(
            OrderInquiryRow.so_line_id == line.id,
            OrderInquiryRow.verb == IV_ORDER,
            OrderInquiryRow.state != INQUIRY_CANCELLED,
        )
        .one()
    )


def _rows_of(world, line):
    return (
        world.db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id)
        .order_by(OrderInquiryRow.created_at.asc())
        .all()
    )


def _confirm(client, order_id, lines, batch_id=None):
    body = {"lines": lines}
    if batch_id:
        body["batch_id"] = batch_id
    return client.post(f"{BASE}/sales-orders/{order_id}/confirm", json=body)


def _change(kind, core_line, *, so_number, old_date, new_date, old_qty, new_qty):
    before = Line(doc_number=so_number, item_code="ZZT-ITEM", location="ZZT",
                  qty=float(old_qty), required_date=old_date, row_ref=str(core_line.id))
    after = None
    if kind != CLOSED:
        after = Line(doc_number=so_number, item_code="ZZT-ITEM", location="ZZT",
                     qty=float(new_qty), required_date=new_date, row_ref="1")
    return Change(kind, so_number, "ZZT-ITEM", "ZZT", before=before, after=after)


def _build(world, changes, core_so, line_ids):
    diff = Diff(scope_documents=(core_so.so_number,), changes=changes)
    batch = planning_change_service.build_batch(
        world.db, diff,
        applied_line_ids={id(c): line_ids[i] for i, c in enumerate(changes)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="Outstanding SO 19 Aug.xlsx",
    )
    world.db.commit()
    return batch


def _form_three(api, *, link_expected=date(2026, 8, 10), with_transfer=False):
    """The fixture, up to the moment the board is opened on the batch.

    Three lines of one product, all confirmed as Buy and all three inquiry rows linked to
    real purchase-order lines. Then the book is re-uploaded: line 1 becomes 25 on 19 August
    and lines 2 and 3 are closed.
    """
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_1 = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10",
                        required_date=WAS_1)
    core_2 = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10",
                        required_date=WAS_2)
    core_3 = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="5",
                        required_date=WAS_3)
    order = _project_so(db, world.project, so_id=core_so.id,
                        autocount_doc_no=core_so.so_number)
    line_1 = _project_line(db, order, line_no=1, product=world.product, core_line=core_1)
    line_2 = _project_line(db, order, line_no=2, product=world.product, core_line=core_2)
    line_3 = _project_line(db, order, line_no=3, product=world.product, core_line=core_3)
    db.commit()

    response = _confirm(client, order.id, [
        _line_payload(line_1.id, buy_qty="10"),
        _line_payload(line_2.id, buy_qty="10"),
        _line_payload(line_3.id, buy_qty="5"),
    ])
    assert response.status_code == 200, response.text

    supplier = _supplier(world)
    row_1 = _order_row(world, line_1)
    row_2 = _order_row(world, line_2)
    row_3 = _order_row(world, line_3)
    _, po_line_1 = _po_line(world, supplier, qty=10, expected_date=link_expected)
    _, po_line_2 = _po_line(world, supplier, qty=10, expected_date=link_expected)
    _, po_line_3 = _po_line(world, supplier, qty=5, expected_date=link_expected)
    _link(world, row_1, po_line_1, qty=10, document="202604-S0083")
    _link(world, row_2, po_line_2, qty=10, document="202606-S0082")
    _link(world, row_3, po_line_3, qty=5, document="202607-S0031")

    if with_transfer:
        db.add(StockTransfer(
            id=_uid(), company_id=world.company_id, transfer_no=f"TR-{_uid()[:6]}",
            so_line_id=core_2.id, project_sales_order_id=order.id,
            product_id=world.product.id, from_warehouse_id=world.pool_wh.id,
            to_warehouse_id=world.own_wh.id, qty=Decimal("10"), kind="pool",
            state=TRANSFER_MOVED, moved_at=datetime.utcnow(),
        ))
    db.commit()

    # The book, re-uploaded. The mirror carries what the book now says.
    core_1.qty_ordered = Decimal("25")
    core_1.required_date = NOW
    line_1.qty = Decimal("25")
    line_1.delivery_date = NOW
    for core, line in ((core_2, line_2), (core_3, line_3)):
        core.line_status = "closed"
        line.qty = Decimal("0")
    db.commit()

    changes = [
        _change(DATE_AND_QTY_CHANGED, core_1, so_number=core_so.so_number,
                old_date=WAS_1, new_date=NOW, old_qty="10", new_qty="25"),
        _change(CLOSED, core_2, so_number=core_so.so_number, old_date=WAS_2,
                new_date=None, old_qty="10", new_qty="0"),
        _change(CLOSED, core_3, so_number=core_so.so_number, old_date=WAS_3,
                new_date=None, old_qty="5", new_qty="0"),
    ]
    batch = _build(world, changes, core_so,
                   [str(core_1.id), str(core_2.id), str(core_3.id)])
    assert batch is not None
    return {
        "client": client, "world": world, "order": order, "core_so": core_so,
        "batch": batch, "lines": (line_1, line_2, line_3),
        "core_lines": (core_1, core_2, core_3),
        "rows": (row_1, row_2, row_3),
    }


def _apply_from_board(fixture, *, qty="25"):
    """The board's own Confirm, carrying the batch (AC-P3-4)."""
    client = fixture["client"]
    order = fixture["order"]
    line_1 = fixture["lines"][0]
    return _confirm(
        client, order.id, [_line_payload(line_1.id, buy_qty=qty)],
        batch_id=str(fixture["batch"].id),
    )


# ---------------------------------------------------------------------------
# AC-P3-5: the surviving line's row is updated in place
# ---------------------------------------------------------------------------


def test_apply_updates_the_surviving_lines_inquiry_row_in_place(api):
    fixture = _form_three(api)
    world = fixture["world"]
    line_1 = fixture["lines"][0]
    row_1 = fixture["rows"][0]
    row_1_id = str(row_1.id)

    response = _apply_from_board(fixture)
    assert response.status_code == 200, response.text
    world.db.commit()

    rows = [r for r in _rows_of(world, line_1) if r.verb == IV_ORDER]
    live = [r for r in rows if r.state != INQUIRY_CANCELLED]
    assert len(live) == 1, "one order inquiry row per sales-order line, always"
    survivor = live[0]
    assert str(survivor.id) == row_1_id, "the row keeps its id; it is never recreated"
    assert Decimal(str(survivor.qty)) == Decimal("25")
    assert survivor.delivery_date == NOW
    assert [str(link.document) for link in
            ProjectOrderInquiryService(world.db)._links_of(survivor.id)].count(
                "202604-S0083") == 1, "every link it had is kept"
    assert "10" in (survivor.note or "") and "2026-08-25" in (survivor.note or ""), (
        "the previous value travels with the row so purchasing can see what moved"
    )


# ---------------------------------------------------------------------------
# AC-P3-6: a closed line's rows are cancelled and its links shift
# ---------------------------------------------------------------------------


def test_a_closed_lines_rows_are_cancelled_and_their_links_move_to_the_survivor(api):
    fixture = _form_three(api)
    world = fixture["world"]
    line_1, line_2, line_3 = fixture["lines"]

    response = _apply_from_board(fixture)
    assert response.status_code == 200, response.text
    world.db.commit()

    for closed in (line_2, line_3):
        rows = _rows_of(world, closed)
        assert rows, "a cancelled row is kept, never deleted"
        assert all(r.state == INQUIRY_CANCELLED for r in rows)
        assert not ProjectOrderInquiryService(world.db)._links_of(rows[0].id), (
            "its links moved rather than being dropped"
        )

    survivor = _order_row(world, line_1)
    documents = sorted(
        link.document
        for link in ProjectOrderInquiryService(world.db)._links_of(survivor.id)
    )
    assert documents == ["202604-S0083", "202606-S0082", "202607-S0031"]
    assert survivor.state == INQUIRY_PLACED, "10 + 10 + 5 covers the whole 25"


# ---------------------------------------------------------------------------
# AC-P3-7: a document arriving after the new date is flagged, never unlinked
# ---------------------------------------------------------------------------


def test_a_link_arriving_after_the_new_date_stays_linked_and_reads_late(api):
    fixture = _form_three(api, link_expected=date(2026, 9, 30))
    client = fixture["client"]
    world = fixture["world"]
    line_1 = fixture["lines"][0]

    response = _apply_from_board(fixture)
    assert response.status_code == 200, response.text
    world.db.commit()

    survivor = _order_row(world, line_1)
    links = ProjectOrderInquiryService(world.db).links_for_rows([str(survivor.id)])
    assert links[str(survivor.id)], "nothing is unlinked for lateness"
    assert all(link["late"] for link in links[str(survivor.id)])

    # And it reaches the screen: `response_model` drops what the schema does not declare.
    listed = client.get(f"{BASE}/order-inquiries", params={"query": fixture["core_so"].so_number})
    assert listed.status_code == 200, listed.text
    rows = [r for r in listed.json()["data"] if r["id"] == str(survivor.id)]
    assert rows, listed.text
    assert rows[0]["links"], "the row still carries its links"
    assert all(link["late"] for link in rows[0]["links"])


def test_a_document_arriving_before_the_new_date_is_not_late(api):
    fixture = _form_three(api, link_expected=date(2026, 8, 10))
    world = fixture["world"]
    line_1 = fixture["lines"][0]

    assert _apply_from_board(fixture).status_code == 200
    world.db.commit()

    survivor = _order_row(world, line_1)
    links = ProjectOrderInquiryService(world.db).links_for_rows([str(survivor.id)])
    assert not any(link["late"] for link in links[str(survivor.id)])


# ---------------------------------------------------------------------------
# AC-P3-8: over-cover unlinks the latest-dated link first
# ---------------------------------------------------------------------------


def test_qty_down_unlinks_the_latest_dated_link_first_and_writes_no_cancel_balance(api):
    """The whole quantity is already linked across three documents and the book cuts the
    line to 12: the 5 arriving LAST is given back, then 3 of the next, and no exception
    row is written for the drop - the row is reduced in place."""
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="25",
                      required_date=WAS_1)
    order = _project_so(db, world.project, so_id=core_so.id,
                        autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core)
    db.commit()

    assert _confirm(client, order.id, [_line_payload(line.id, buy_qty="25")]).status_code == 200
    supplier = _supplier(world)
    row = _order_row(world, line)
    _, early = _po_line(world, supplier, qty=10, expected_date=date(2026, 7, 1))
    _, middle = _po_line(world, supplier, qty=10, expected_date=date(2026, 8, 1))
    _, latest = _po_line(world, supplier, qty=5, expected_date=date(2026, 9, 1))
    _link(world, row, early, qty=10, document="EARLY")
    _link(world, row, middle, qty=10, document="MIDDLE")
    _link(world, row, latest, qty=5, document="LATEST")
    db.commit()
    assert row.state == INQUIRY_PLACED

    core.qty_ordered = Decimal("12")
    line.qty = Decimal("12")
    db.commit()
    changes = [_change(QTY_CHANGED, core, so_number=core_so.so_number, old_date=WAS_1,
                       new_date=WAS_1, old_qty="25", new_qty="12")]
    batch = _build(world, changes, core_so, [str(core.id)])
    assert batch is not None

    response = _confirm(client, order.id, [_line_payload(line.id, buy_qty="12")],
                        batch_id=str(batch.id))
    assert response.status_code == 200, response.text
    db.commit()

    survivor = _order_row(world, line)
    assert Decimal(str(survivor.qty)) == Decimal("12")
    remaining = sorted(
        link.document
        for link in ProjectOrderInquiryService(db)._links_of(survivor.id)
    )
    assert remaining == ["EARLY", "MIDDLE"], "the latest-dated link is given back first"
    kept = sum(
        Decimal(str(link.qty))
        for link in ProjectOrderInquiryService(db)._links_of(survivor.id)
    )
    assert kept == Decimal("12"), "linked never exceeds the new quantity"
    assert not (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id,
                OrderInquiryRow.verb == IV_CANCEL_BALANCE)
        .all()
    ), "no CANCEL_BALANCE row for a drop the row absorbed in place"


# ---------------------------------------------------------------------------
# AC-P3-9: a transfer already moved is flagged, never reversed
# ---------------------------------------------------------------------------


def test_a_moved_transfer_on_a_closed_line_is_flagged_and_no_reverse_is_written(api):
    fixture = _form_three(api, with_transfer=True)
    world = fixture["world"]
    line_2 = fixture["lines"][1]

    out = planning_change_service.get_batch(world.db, str(fixture["batch"].id))
    rows = {r["line_no"]: r for r in out["orders"][0]["rows"]}
    assert rows[2]["moved_transfer"], "the change row says the stock already moved"
    assert "10" in rows[2]["moved_transfer"]
    assert world.pool_wh.warehouse_code in rows[2]["moved_transfer"]
    assert world.own_wh.warehouse_code in rows[2]["moved_transfer"]
    assert rows[1]["moved_transfer"] is None, "the surviving line moved nothing"

    before = world.db.query(StockTransfer).filter(
        StockTransfer.project_sales_order_id == fixture["order"].id
    ).count()
    assert _apply_from_board(fixture).status_code == 200
    world.db.commit()
    after = world.db.query(StockTransfer).filter(
        StockTransfer.project_sales_order_id == fixture["order"].id,
        StockTransfer.to_warehouse_id == world.pool_wh.id,
    ).count()
    assert after == 0, "a physical move is a person's decision; nothing reverses it"
    assert world.db.query(StockTransfer).filter(
        StockTransfer.so_line_id == str(fixture["core_lines"][1].id),
        StockTransfer.state == TRANSFER_MOVED,
    ).count() == 1
    assert before >= 1


# ---------------------------------------------------------------------------
# AC-P3-10: release of a wholly-Buy line
# ---------------------------------------------------------------------------


def _released_line(api, *, linked: bool):
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="40",
                      required_date=WAS_1)
    order = _project_so(db, world.project, so_id=core_so.id,
                        autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core)
    db.commit()
    assert _confirm(client, order.id, [_line_payload(line.id, buy_qty="40")]).status_code == 200
    row = _order_row(world, line)
    if linked:
        supplier = _supplier(world)
        _, po_line = _po_line(world, supplier, qty=40, expected_date=date(2026, 8, 1))
        _link(world, row, po_line, qty=40, document="202604-S0083")
    far = date(2027, 3, 10)
    core.required_date = far
    line.delivery_date = far
    db.commit()
    changes = [_change(DATE_MOVED, core, so_number=core_so.so_number, old_date=WAS_1,
                       new_date=far, old_qty="40", new_qty="40")]
    batch = _build(world, changes, core_so, [str(core.id)])
    assert batch is not None
    return {"client": client, "world": world, "order": order, "line": line,
            "core_so": core_so, "batch": batch, "row": row, "far": far}


def test_release_of_a_wholly_bought_line_is_suggested_beyond_the_window(api):
    fixture = _released_line(api, linked=True)
    out = planning_change_service.get_batch(fixture["world"].db, str(fixture["batch"].id))
    row = out["orders"][0]["rows"][0]
    assert row["suggested"] == "release", (
        "the dead release path: a wholly-Buy line delayed past the window releases"
    )


def test_release_moves_a_linked_row_to_the_pool_with_its_links_and_raises_nothing(api):
    fixture = _released_line(api, linked=True)
    world = fixture["world"]
    line = fixture["line"]
    row_id = str(fixture["row"].id)

    result = planning_change_service.apply(world.db, str(fixture["batch"].id), world.actor)
    world.db.commit()
    assert result["failed_orders"] == []

    row = world.db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row_id).one()
    assert row.state != INQUIRY_CANCELLED
    assert row.stock_location == world.pool_wh.warehouse_code, (
        "the purchase is for the pool now, not for this line"
    )
    assert ProjectOrderInquiryService(world.db)._links_of(row.id), "its links are kept"
    assert "2027-03-10" in (row.note or ""), "the note names the delay"
    raised = [
        r for r in _rows_of(world, line)
        if r.state != INQUIRY_CANCELLED and str(r.id) != row_id
    ]
    assert raised == [], "a release raises no new order inquiry row"


def test_release_of_an_unlinked_row_hands_purchasing_a_delay_with_the_previous_date(api):
    fixture = _released_line(api, linked=False)
    world = fixture["world"]
    line = fixture["line"]

    result = planning_change_service.apply(world.db, str(fixture["batch"].id), world.actor)
    world.db.commit()
    assert result["failed_orders"] == []

    delays = [r for r in _rows_of(world, line) if r.verb == "DELAY"]
    assert len(delays) == 1, "an unlinked release reads as a delay to purchasing"
    assert "2026-08-25" in (delays[0].note or ""), "with the previous date"


# ---------------------------------------------------------------------------
# AC-P3-4: one call applies the batch, a second is refused
# ---------------------------------------------------------------------------


def test_board_confirm_with_a_batch_applies_it_and_writes_one_revision(api):
    fixture = _form_three(api)
    world = fixture["world"]

    response = _apply_from_board(fixture)
    assert response.status_code == 200, response.text
    world.db.commit()

    world.db.refresh(fixture["batch"])
    assert fixture["batch"].applied_at is not None
    assert str(fixture["batch"].applied_by) == str(world.actor)

    from app.models.project_so import SOSupplyDecision

    revisions = (
        world.db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == fixture["order"].id)
        .count()
    )
    assert revisions == 2, "the first confirmation, then exactly one more"


def test_a_second_confirm_on_the_same_batch_is_refused_with_a_message(api):
    fixture = _form_three(api)
    world = fixture["world"]
    # By id, held as a string: the refusal rolls the request's own transaction back and
    # expires every instance with it, so an ORM attribute read afterwards is a re-SELECT.
    order_id = str(fixture["order"].id)

    assert _apply_from_board(fixture).status_code == 200
    world.db.commit()

    again = _apply_from_board(fixture)
    assert again.status_code == 409, again.text
    assert "already" in again.text.lower()

    from app.models.project_so import SOSupplyDecision

    assert (
        world.db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order_id)
        .count()
    ) == 2, "no duplicate revision"


# ---------------------------------------------------------------------------
# AC-P3-11: what the plan then counts
# ---------------------------------------------------------------------------


def test_committed_v_counts_twenty_five_for_the_product_and_nothing_else(api):
    fixture = _form_three(api)
    world = fixture["world"]
    line_1, line_2, line_3 = fixture["lines"]

    assert _apply_from_board(fixture).status_code == 200
    world.db.commit()

    live = [
        r for r in world.db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id.in_([line_1.id, line_2.id, line_3.id]))
        .all()
        if r.state != INQUIRY_CANCELLED
    ]
    assert len(live) == 1
    assert Decimal(str(live[0].qty)) == Decimal("25")
    cancelled = [
        r for r in world.db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id.in_([line_2.id, line_3.id]))
        .all()
    ]
    assert len(cancelled) == 2 and all(r.state == INQUIRY_CANCELLED for r in cancelled)

    committed = world.db.execute(
        text(
            "SELECT COALESCE(SUM(project_confirmed_committed), 0) "
            "FROM scm.committed_v WHERE product_id = :pid"
        ),
        {"pid": world.product.id},
    ).scalar()
    assert Decimal(str(committed)) == Decimal("0"), (
        "every one of the 25 sits on a document, so nothing is left to buy"
    )


# ---------------------------------------------------------------------------
# AC-P3-1: the two entry points, on the wire
# ---------------------------------------------------------------------------


def test_the_batch_list_names_the_orders_its_plan_action_opens(api):
    """`response_model` drops what the schema does not declare, so the field the list row's
    Plan action is built from is asserted through the FastAPI client, never off the dict."""
    fixture = _form_three(api)
    client = fixture["client"]

    listed = client.get(f"{BASE}/planning-changes")
    assert listed.status_code == 200, listed.text
    rows = [r for r in listed.json()["data"] if r["id"] == str(fixture["batch"].id)]
    assert rows, listed.text
    assert rows[0]["so_numbers"] == [fixture["core_so"].so_number]


def test_a_changed_order_carries_its_pending_batch_on_the_sales_order_list(api):
    """AC-P3-1's Changed badge: the SO list says WHICH batch, so the badge opens the board
    on this order and that change."""
    fixture = _form_three(api)
    client = fixture["client"]
    world = fixture["world"]

    listed = client.get(
        "/api/v1/scm/sales-orders", params={"query": fixture["core_so"].so_number}
    )
    assert listed.status_code == 200, listed.text
    rows = [r for r in listed.json()["data"] if r["so_number"] == fixture["core_so"].so_number]
    assert rows, listed.text
    assert rows[0]["planning_change_batch_id"] == str(fixture["batch"].id)

    # Applied, the badge is gone: there is nothing left on that board to confirm.
    assert _apply_from_board(fixture).status_code == 200
    world.db.commit()
    again = client.get(
        "/api/v1/scm/sales-orders", params={"query": fixture["core_so"].so_number}
    )
    rows = [r for r in again.json()["data"] if r["so_number"] == fixture["core_so"].so_number]
    assert rows[0]["planning_change_batch_id"] is None


def test_the_batch_row_carries_its_planning_line_and_change_flags_on_the_wire(api):
    """AC-P3-2 / AC-P3-9 through the route: the board matches a cell on `project_line_id`
    and prints `moved_transfer`, and neither survives an undeclared schema field."""
    fixture = _form_three(api, with_transfer=True)
    client = fixture["client"]
    line_1, line_2, _line_3 = fixture["lines"]

    out = client.get(f"{BASE}/planning-changes/{fixture['batch'].id}")
    assert out.status_code == 200, out.text
    rows = {row["line_no"]: row for row in out.json()["orders"][0]["rows"]}
    assert rows[1]["project_line_id"] == str(line_1.id)
    assert rows[2]["project_line_id"] == str(line_2.id)
    assert rows[2]["moved_transfer"], out.text
    assert "line cancelled" in rows[2]["moved_transfer"]
    assert rows[1]["moved_transfer"] is None


# ---------------------------------------------------------------------------
# Gap 1: a line with TWO still-owed rows declines the settle-in-place seam and
# the old supersede path stands (`ProjectOrderInquiryService._settle_row_in_place`).
# ---------------------------------------------------------------------------


def test_a_line_with_two_still_owed_rows_declines_settle_in_place_and_the_old_path_stands(api):
    """`_settle_row_in_place` returns False when a line carries more than one still-owed
    row - it has no way to say which one the book moved (module docstring,
    `project_order_inquiry_service.py`). The old supersede path stands instead: both rows
    are left exactly as they were (still placed, links intact, no note written) and the
    outstanding remainder is raised as a THIRD row."""
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="20",
                      required_date=WAS_1)
    order = _project_so(db, world.project, so_id=core_so.id,
                        autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core)
    db.commit()

    assert _confirm(client, order.id, [_line_payload(line.id, buy_qty="20")]).status_code == 200
    supplier = _supplier(world)
    row_a = _order_row(world, line)
    # The confirmation above raised ONE row of 20 - shrunk to 10 here, so this fixture can
    # stand for the duplication defect it is testing: two 10-unit rows on one line rather
    # than the one row the service itself would ever create.
    row_a.qty = Decimal("10")
    db.commit()
    _, po_a = _po_line(world, supplier, qty=10, expected_date=date(2026, 8, 1))
    _link(world, row_a, po_a, qty=10, document="ROW-A")
    db.commit()

    # A second still-owed row on the SAME line - the shape a duplication defect leaves,
    # and the one `_settle_row_in_place` refuses to guess between.
    row_b = OrderInquiryRow(
        id=_uid(), company_id=world.company_id, order_inquiry_id=row_a.order_inquiry_id,
        so_line_id=line.id, item_code=row_a.item_code, qty=Decimal("10"),
        delivery_date=row_a.delivery_date, stock_location=row_a.stock_location,
        verb=IV_ORDER, state=INQUIRY_RAISED, supply_decision_id=row_a.supply_decision_id,
    )
    db.add(row_b)
    db.commit()
    _, po_b = _po_line(world, supplier, qty=10, expected_date=date(2026, 8, 1))
    _link(world, row_b, po_b, qty=10, document="ROW-B")
    db.commit()

    # A pure quantity change (no date move), so the only row this apply could raise
    # besides the Buy netting itself is the kind this test is about.
    core.qty_ordered = Decimal("25")
    line.qty = Decimal("25")
    db.commit()

    changes = [_change(QTY_CHANGED, core, so_number=core_so.so_number,
                       old_date=WAS_1, new_date=WAS_1, old_qty="20", new_qty="25")]
    batch = _build(world, changes, core_so, [str(core.id)])
    assert batch is not None

    response = _confirm(client, order.id, [_line_payload(line.id, buy_qty="25")],
                        batch_id=str(batch.id))
    assert response.status_code == 200, response.text
    db.commit()

    rows = _rows_of(world, line)
    live = [r for r in rows if r.state != INQUIRY_CANCELLED]
    assert len(live) == 3, "the two owed rows stand untouched, and the remainder is raised fresh"
    live_ids = {str(r.id) for r in live}
    assert str(row_a.id) in live_ids and str(row_b.id) in live_ids

    service = ProjectOrderInquiryService(db)
    assert [link.document for link in service._links_of(row_a.id)] == ["ROW-A"], (
        "the old supersede path never touches a placed row's links"
    )
    assert [link.document for link in service._links_of(row_b.id)] == ["ROW-B"]
    db.refresh(row_a)
    db.refresh(row_b)
    assert not row_a.note and not row_b.note, (
        "settle-in-place never ran on either row - no 'Was ...' note was written"
    )

    third = [r for r in live if str(r.id) not in (str(row_a.id), str(row_b.id))]
    assert len(third) == 1
    assert Decimal(str(third[0].qty)) == Decimal("5"), "20 already placed, 5 still outstanding"


# ---------------------------------------------------------------------------
# Gap 2: a borrow with no reason reaches `set_row_decision` via the board's own
# amend-through-confirm path, and the server refuses it.
# ---------------------------------------------------------------------------


def test_amend_with_a_borrow_that_carries_no_reason_is_refused(api):
    """Section 1c / `_check_borrow` (`project_supply_service.py`): a borrow with no
    stated reason refuses the whole confirmation. Reached from the board's own
    Confirm-with-`batch_id` route (`_confirm_a_planning_change`), which composes the
    line via `set_row_decision(..., "amend", composition)` before Apply re-checks it
    against live facts.

    And it says WHICH line and WHY. The batch-confirm path used to re-raise the per-order
    summary alone and drop `failing_lines`, so the same refusal that marks the row on an
    ordinary Confirm read "1 line cannot be confirmed" here with nothing to act on."""
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="40",
                      required_date=WAS_1)
    order = _project_so(db, world.project, so_id=core_so.id,
                        autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core)
    db.commit()
    assert _confirm(client, order.id, [_line_payload(line.id, buy_qty="40")]).status_code == 200

    core.qty_ordered = Decimal("60")
    line.qty = Decimal("60")
    db.commit()
    changes = [_change(QTY_CHANGED, core, so_number=core_so.so_number, old_date=WAS_1,
                       new_date=WAS_1, old_qty="40", new_qty="60")]
    batch = _build(world, changes, core_so, [str(core.id)])
    assert batch is not None

    response = _confirm(
        client, order.id,
        [_line_payload(
            line.id,
            borrow=[{
                "source": "other_location", "warehouse_id": world.pool_wh.id, "qty": "60",
            }],
            buy_qty="0",
        )],
        batch_id=str(batch.id),
    )
    assert response.status_code == 422, response.text
    assert "cannot be confirmed" in response.text.lower(), response.text
    failing = response.json().get("failing_lines")
    assert failing, response.text
    assert failing[0]["line_no"] == 1, failing
    assert "reason" in failing[0]["reason"].lower(), failing


# ---------------------------------------------------------------------------
# Gap 3: the board's Confirm on an order the batch never touched takes the
# `extra_confirm_lines` path and writes no batch row.
# ---------------------------------------------------------------------------


def test_a_batch_confirm_on_an_order_with_no_batch_rows_takes_the_extra_lines_path(api):
    """AC-P3-4's `extra_confirm_lines`: a board opened on `?batch=<id>` for an order the
    batch has no row for still lets that order confirm in the same call - it goes through
    as an ordinary confirmation (`extra_confirm_lines`) and writes no `PlanningChangeRow`
    for it."""
    client, world = api
    db = world.db

    # The batch's own order, built but never decided here.
    core_so_a = _core_so(db, world.company_id)
    core_a = _core_line(db, core_so_a, world.product, world.own_wh, qty_ordered="10",
                        required_date=WAS_1)
    order_a = _project_so(db, world.project, so_id=core_so_a.id,
                          autocount_doc_no=core_so_a.so_number)
    line_a = _project_line(db, order_a, line_no=1, product=world.product, core_line=core_a)
    db.commit()
    assert _confirm(client, order_a.id, [_line_payload(line_a.id, buy_qty="10")]).status_code == 200
    core_a.qty_ordered = Decimal("15")
    core_a.required_date = NOW
    line_a.qty = Decimal("15")
    line_a.delivery_date = NOW
    db.commit()
    changes = [_change(DATE_AND_QTY_CHANGED, core_a, so_number=core_so_a.so_number,
                       old_date=WAS_1, new_date=NOW, old_qty="10", new_qty="15")]
    batch = _build(world, changes, core_so_a, [str(core_a.id)])
    assert batch is not None

    # An unrelated order this batch never named at all.
    core_so_b = _core_so(db, world.company_id)
    core_b = _core_line(db, core_so_b, world.product, world.own_wh, qty_ordered="8",
                        required_date=WAS_1)
    order_b = _project_so(db, world.project, so_id=core_so_b.id,
                          autocount_doc_no=core_so_b.so_number)
    line_b = _project_line(db, order_b, line_no=1, product=world.product, core_line=core_b)
    db.commit()

    from app.models.planning_change import PlanningChangeRow as PlanningChangeRowModel

    before = (
        db.query(PlanningChangeRowModel)
        .filter(PlanningChangeRowModel.project_sales_order_id == order_b.id)
        .count()
    )
    assert before == 0, "order B has no row in this batch to begin with"

    response = _confirm(client, order_b.id, [_line_payload(line_b.id, buy_qty="8")],
                        batch_id=str(batch.id))
    assert response.status_code == 200, response.text
    db.commit()

    after = (
        db.query(PlanningChangeRowModel)
        .filter(PlanningChangeRowModel.project_sales_order_id == order_b.id)
        .count()
    )
    assert after == 0, "the extra_confirm_lines path writes no batch row for this order"

    from app.models.project_so import SOSupplyDecision

    active_b = (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order_b.id,
                SOSupplyDecision.state == "active")
        .one()
    )
    assert active_b.revision_no == 1, "confirmed normally, exactly as an ordinary Confirm would"


# ---------------------------------------------------------------------------
# Gap 4: `_shift_links_off_retired_lines` and a survivor with PARTIAL headroom.
# ---------------------------------------------------------------------------


def test_a_survivor_with_partial_headroom_splits_the_retired_links_qty_across_survivor_and_cascade(api):
    """What AC-P3-6 asks for when the survivor cannot take the whole link: "whatever that
    row cannot take goes back through the cascade" (PLAN part 3) is a SPLIT - the survivor
    takes as much as its own headroom allows and the remainder goes back to the cascade -
    not an all-or-nothing choice.

    Pinned against a survivor short by 4 of a 10-unit link: it takes its 6 on a link of
    its own naming the same document, and the other 4 is unlinked and free again.
    """
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_1 = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="25",
                        required_date=WAS_1)
    core_2 = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10",
                        required_date=WAS_2)
    order = _project_so(db, world.project, so_id=core_so.id,
                        autocount_doc_no=core_so.so_number)
    line_1 = _project_line(db, order, line_no=1, product=world.product, core_line=core_1)
    line_2 = _project_line(db, order, line_no=2, product=world.product, core_line=core_2)
    db.commit()

    response = _confirm(client, order.id, [
        _line_payload(line_1.id, buy_qty="25"),
        _line_payload(line_2.id, buy_qty="10"),
    ])
    assert response.status_code == 200, response.text

    supplier = _supplier(world)
    row_1 = _order_row(world, line_1)
    row_2 = _order_row(world, line_2)
    # The survivor already carries 19 of its own 25 on a document, leaving only 6 of
    # headroom - PARTIAL against the 10 the retiring line's link is about to offer it.
    _, po_1 = _po_line(world, supplier, qty=19, expected_date=date(2026, 8, 1))
    _link(world, row_1, po_1, qty=19, document="SURVIVOR-OWN")
    _, po_2 = _po_line(world, supplier, qty=10, expected_date=date(2026, 8, 1))
    _link(world, row_2, po_2, qty=10, document="RETIRING")
    db.commit()

    core_2.line_status = "closed"
    line_2.qty = Decimal("0")
    db.commit()

    changes = [_change(CLOSED, core_2, so_number=core_so.so_number, old_date=WAS_2,
                       new_date=None, old_qty="10", new_qty="0")]
    batch = _build(world, changes, core_so, [str(core_2.id)])
    assert batch is not None

    apply_response = _confirm(client, order.id, [_line_payload(line_1.id, buy_qty="25")],
                              batch_id=str(batch.id))
    assert apply_response.status_code == 200, apply_response.text
    db.commit()

    service = ProjectOrderInquiryService(db)
    # The surviving line's own live ORDER rows, whatever shape the confirmation left them
    # in: line 1 carries no batch row here (only the closed line does), so it goes through
    # as an ordinary confirmation and its partly-linked row is shrunk to what was on a
    # document with the remainder re-raised beside it. What the split is about is where the
    # RETIRING document ended up, so the documents are summed across the line.
    survivors = [
        r for r in _rows_of(world, line_1)
        if r.verb == IV_ORDER and r.state != INQUIRY_CANCELLED
    ]
    assert survivors, "the surviving line still owes something"
    survivor_docs: dict = {}
    for row in survivors:
        for link in service._links_of(row.id):
            survivor_docs[link.document] = survivor_docs.get(
                link.document, Decimal("0")
            ) + Decimal(str(link.qty))
    retiring_rows = [r for r in _rows_of(world, line_2) if r.state == INQUIRY_CANCELLED]
    assert retiring_rows, "the closed line's row is cancelled, never deleted"
    retiring_links = service._links_of(retiring_rows[-1].id)

    took = survivor_docs.get("RETIRING")
    assert took is not None, "the survivor takes what it can hold, never nothing at all"
    assert took == Decimal("6"), "the survivor takes exactly its own headroom, 6 of the 10"
    assert not retiring_links, "the retired row keeps no link of its own"
    # The other 4 goes back through the cascade (unlinked, free for the next row) rather
    # than vanishing - the total the link ever carried is preserved across the split.
    freed = Decimal("10") - took
    assert freed == Decimal("4")


# ---------------------------------------------------------------------------
# Gap 5: a second CONFIRM on the same batch, refused 409 with a message - reinforced
# with the structured error code and a GET afterwards, both on the wire.
# ---------------------------------------------------------------------------


def test_a_second_confirm_refusal_carries_a_stable_code_and_the_batch_still_reads_applied(api):
    """`test_a_second_confirm_on_the_same_batch_is_refused_with_a_message` already pins the
    409 + "already" text (AC-P3-4). This adds the two things that test does not: the
    refusal's structured `code`, so the FE need not string-match, and that a GET on the
    batch straight after still reads correctly through the wire - the failed second press
    left nothing behind for `get_batch`'s `response_model` to drop or corrupt."""
    fixture = _form_three(api)
    client = fixture["client"]
    world = fixture["world"]

    assert _apply_from_board(fixture).status_code == 200
    world.db.commit()

    again = _apply_from_board(fixture)
    assert again.status_code == 409, again.text
    body = again.json()
    assert body.get("code") == "planning_change_batch_applied", body

    detail = client.get(f"{BASE}/planning-changes/{fixture['batch'].id}")
    assert detail.status_code == 200, detail.text
    # The list envelope carries the summary shape (`applied_at` / `applied_by_name`); read
    # it here too, so the failed second press is confirmed not to have corrupted it.
    listed = client.get(f"{BASE}/planning-changes")
    assert listed.status_code == 200, listed.text
    row = next(r for r in listed.json()["data"] if r["id"] == str(fixture["batch"].id))
    assert row["applied_at"] is not None
    assert row["applied_by_name"], row


# ---------------------------------------------------------------------------
# Gap 6: `late` survives `response_model` on the SO detail's Linked to column too,
# not only on the order-inquiry list.
# ---------------------------------------------------------------------------


def test_the_late_flag_reaches_the_sales_order_detail_linked_to_column_on_the_wire(api):
    """`test_a_link_arriving_after_the_new_date_stays_linked_and_reads_late` already pins
    `late` through `/order-inquiries`. AC-P3-7 says "wherever the link is shown", and the
    SO detail's Lines tab is the other reader (`SalesOrderLineLink.late`,
    `app/schemas/scm_orders.py`) - a separate `response_model`, so the field surviving one
    does not prove it survives the other."""
    fixture = _form_three(api, link_expected=date(2026, 9, 30))
    client = fixture["client"]
    world = fixture["world"]
    core_so = fixture["core_so"]
    core_1 = fixture["core_lines"][0]

    assert _apply_from_board(fixture).status_code == 200
    world.db.commit()

    detail = client.get(f"/api/v1/scm/sales-orders/{core_so.id}")
    assert detail.status_code == 200, detail.text
    lines = {ln["id"]: ln for ln in detail.json()["lines"]}
    line_out = lines[str(core_1.id)]
    assert line_out["linked_to"], detail.text
    assert all(link["late"] for link in line_out["linked_to"]), detail.text


# ---------------------------------------------------------------------------
# Review B1: one press confirms ONE order of the batch, never the whole batch
# ---------------------------------------------------------------------------


def _two_order_batch(api):
    """One upload, two changed orders, one line each. The shape a book re-upload has."""
    client, world = api
    db = world.db
    built = []
    changes = []
    line_ids = []
    for _ in range(2):
        core_so = _core_so(db, world.company_id)
        core = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10",
                          required_date=WAS_1)
        order = _project_so(db, world.project, so_id=core_so.id,
                            autocount_doc_no=core_so.so_number)
        line = _project_line(db, order, line_no=1, product=world.product, core_line=core)
        db.commit()
        assert _confirm(
            client, order.id, [_line_payload(line.id, buy_qty="10")]
        ).status_code == 200
        core.qty_ordered = Decimal("25")
        line.qty = Decimal("25")
        db.commit()
        built.append({"core_so": core_so, "core": core, "order": order, "line": line})
        changes.append(
            _change(QTY_CHANGED, core, so_number=core_so.so_number, old_date=WAS_1,
                    new_date=WAS_1, old_qty="10", new_qty="25")
        )
        line_ids.append(str(core.id))

    diff = Diff(
        scope_documents=tuple(entry["core_so"].so_number for entry in built),
        changes=changes,
    )
    batch = planning_change_service.build_batch(
        world.db, diff,
        applied_line_ids={id(c): line_ids[i] for i, c in enumerate(changes)},
        order_ids={
            entry["core_so"].so_number: str(entry["order"].id) for entry in built
        },
        actor=world.actor, import_job_id=None,
        file_name="Outstanding SO 19 Aug.xlsx",
    )
    db.commit()
    assert batch is not None
    return client, world, batch, built


def _batch_rows_for(world, batch, order):
    from app.models.planning_change import PlanningChangeRow as PlanningChangeRowModel

    return (
        world.db.query(PlanningChangeRowModel)
        .filter(
            PlanningChangeRowModel.batch_id == batch.id,
            PlanningChangeRowModel.project_sales_order_id == str(order.id),
        )
        .all()
    )


def test_confirming_one_order_of_a_batch_applies_that_order_alone(api):
    """The board presses Confirm PER ORDER, so an apply carries one order (B1, review of
    part 3). Applying the whole batch off one press wrote a revision for an order nobody
    had confirmed and stamped `applied_at`, which locked every other order's rows: the
    row-decision PUT answered 409 and the second order's own Confirm had nothing left to
    do."""
    client, world, batch, built = _two_order_batch(api)
    first, second = built
    db = world.db

    from app.models.project_so import SOSupplyDecision

    response = _confirm(
        client, first["order"].id, [_line_payload(first["line"].id, buy_qty="25")],
        batch_id=str(batch.id),
    )
    assert response.status_code == 200, response.text
    db.commit()
    db.refresh(batch)

    assert batch.applied_at is None, (
        "the batch is not done while another order of it is still waiting"
    )
    assert all(r.applied_state == "applied" for r in _batch_rows_for(world, batch, first["order"]))
    assert all(
        r.applied_state == "pending"
        for r in _batch_rows_for(world, batch, second["order"])
    ), "the order nobody confirmed keeps its rows exactly as they were"
    assert (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == second["order"].id)
        .count()
    ) == 1, "no revision is written for an order nobody confirmed"

    # And the second order's own decisions are still editable, which `applied_at` would
    # have refused (409, `planning_change_batch_applied`).
    row = _batch_rows_for(world, batch, second["order"])[0]
    edited = client.put(
        f"{BASE}/planning-changes/{batch.id}/rows/{row.id}", json={"decision": "accept"}
    )
    assert edited.status_code == 200, edited.text

    # Then the second press, and only now is the batch itself done.
    again = _confirm(
        client, second["order"].id, [_line_payload(second["line"].id, buy_qty="25")],
        batch_id=str(batch.id),
    )
    assert again.status_code == 200, again.text
    db.commit()
    db.refresh(batch)
    assert batch.applied_at is not None
    assert str(batch.applied_by) == str(world.actor)


def test_a_second_press_on_an_order_already_applied_from_the_batch_is_refused(api):
    """Per ORDER, before the batch as a whole reads applied: pressing Confirm twice on the
    first order of a two-order batch says the change is already applied rather than
    answering 422 "nothing could be confirmed"."""
    client, world, batch, built = _two_order_batch(api)
    first = built[0]

    assert _confirm(
        client, first["order"].id, [_line_payload(first["line"].id, buy_qty="25")],
        batch_id=str(batch.id),
    ).status_code == 200
    world.db.commit()

    again = _confirm(
        client, first["order"].id, [_line_payload(first["line"].id, buy_qty="25")],
        batch_id=str(batch.id),
    )
    assert again.status_code == 409, again.text
    assert again.json().get("code") == "planning_change_batch_applied", again.text


# ---------------------------------------------------------------------------
# Review S5: a release row confirmed FROM THE BOARD takes the release path
# ---------------------------------------------------------------------------


def test_a_release_row_confirmed_from_the_board_reaches_the_pool_path(api):
    """AC-P3-10 through the board's own Confirm. The board pre-marks every changed line
    and posts it, and the route used to record each as an `amend` - which sent a `release`
    row down the confirm branch, so the RELEASE rule never fired from the screen it is
    decided on. A release is "yes, do what the book did", not an amendment of the line's
    supply."""
    fixture = _released_line(api, linked=True)
    client = fixture["client"]
    world = fixture["world"]
    line = fixture["line"]
    row_id = str(fixture["row"].id)

    response = _confirm(
        client, fixture["order"].id, [_line_payload(line.id, buy_qty="40")],
        batch_id=str(fixture["batch"].id),
    )
    assert response.status_code == 200, response.text
    world.db.commit()

    row = world.db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row_id).one()
    assert row.state != INQUIRY_CANCELLED
    assert row.stock_location == world.pool_wh.warehouse_code, (
        "the purchase is for the pool now, not for this line"
    )
    assert ProjectOrderInquiryService(world.db)._links_of(row.id), "its links are kept"
    assert "2027-03-10" in (row.note or ""), "the note names the delay"
    raised = [
        r for r in _rows_of(world, line)
        if r.state != INQUIRY_CANCELLED and str(r.id) != row_id
    ]
    assert raised == [], "a release raises no new order inquiry row"


# ---------------------------------------------------------------------------
# Review B3: the closed lines' documents reach the survivor BEFORE the cascade
# ---------------------------------------------------------------------------


def test_the_survivor_takes_the_closed_lines_documents_not_a_strangers(api):
    """Order of operations inside one apply (B3, review of part 3).

    The confirmation settles the survivor at 25 with its own 10 already linked, which
    leaves 15 of headroom. The cascade used to run INSIDE `confirm`, so it filled that 15
    from any free purchase-order line it could find, and the closed lines' own 10 + 5
    arrived a moment later to a row with nothing left to give them - unlinked and re-dealt
    to a stranger, the opposite of AC-P3-6. The cancel and the shift now run first."""
    fixture = _form_three(api)
    world = fixture["world"]
    line_1 = fixture["lines"][0]

    # A free purchase order for the same product, big enough to swallow the whole
    # headroom, and nobody's yet.
    supplier = _supplier(world)
    _po_line(world, supplier, qty=15, expected_date=date(2026, 8, 5), number="ZZT-PO-FREE")
    world.db.commit()

    assert _apply_from_board(fixture).status_code == 200
    world.db.commit()

    survivor = _order_row(world, line_1)
    documents = sorted(
        link.document
        for link in ProjectOrderInquiryService(world.db)._links_of(survivor.id)
    )
    assert documents == ["202604-S0083", "202606-S0082", "202607-S0031"], (
        "the closed lines' own placements follow the line that still needs them"
    )
    assert "ZZT-PO-FREE" not in documents, (
        "a free purchase order is not dealt in ahead of the order's own supply"
    )


# ---------------------------------------------------------------------------
# Review S2: a settle answers the CANCEL_BALANCE an earlier revision raised
# ---------------------------------------------------------------------------


def test_a_settle_cancels_the_still_raised_cancel_balance_for_the_same_line(api):
    """A `CANCEL_BALANCE` says "placed X, new need Y" about a quantity the settle has just
    restated in place, so left raised it asks purchasing to answer a question about a
    figure that no longer exists - beside the row that now carries the true one. The
    supersede path cancels it on every reconfirm; the settle path skipped it."""
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="20",
                      required_date=WAS_1)
    order = _project_so(db, world.project, so_id=core_so.id,
                        autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core)
    db.commit()
    assert _confirm(client, order.id, [_line_payload(line.id, buy_qty="20")]).status_code == 200

    supplier = _supplier(world)
    row = _order_row(world, line)
    _, po_line = _po_line(world, supplier, qty=20, expected_date=date(2026, 8, 1))
    _link(world, row, po_line, qty=20, document="ALREADY-BOUGHT")
    # The exception an earlier revision raised for this line, still waiting on an answer.
    exception = OrderInquiryRow(
        id=_uid(), company_id=world.company_id, order_inquiry_id=row.order_inquiry_id,
        so_line_id=line.id, item_code=row.item_code, qty=Decimal("4"),
        delivery_date=row.delivery_date, stock_location=row.stock_location,
        verb=IV_CANCEL_BALANCE, state=INQUIRY_RAISED,
        supply_decision_id=row.supply_decision_id, note="Placed 20, new need 16",
    )
    db.add(exception)
    db.commit()

    core.qty_ordered = Decimal("16")
    line.qty = Decimal("16")
    db.commit()
    changes = [_change(QTY_CHANGED, core, so_number=core_so.so_number, old_date=WAS_1,
                       new_date=WAS_1, old_qty="20", new_qty="16")]
    batch = _build(world, changes, core_so, [str(core.id)])
    assert batch is not None

    response = _confirm(client, order.id, [_line_payload(line.id, buy_qty="16")],
                        batch_id=str(batch.id))
    assert response.status_code == 200, response.text
    db.commit()

    db.refresh(exception)
    assert exception.state == INQUIRY_CANCELLED, (
        "the settle answers the exception rather than leaving it beside the true figure"
    )
    assert "Superseded by revision" in (exception.note or "")


# ---------------------------------------------------------------------------
# Review S3: a lone PLACED row with NO link declines the settle (SO349754)
# ---------------------------------------------------------------------------


def test_a_placed_row_with_no_link_declines_settle_and_keeps_its_placed_quantity(api):
    """The SO349754 WESERP10B shape: purchasing placed 5 through a path that wrote no link
    row. Settling that row in place would have restated it at the new need and demoted it
    back to raised through `_refresh_link_state` - losing the netting that says 5 of it is
    already bought. The caller's own path nets `placed` off the need and raises only the
    difference, which is the honest answer."""
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="5",
                      required_date=WAS_1)
    order = _project_so(db, world.project, so_id=core_so.id,
                        autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core)
    db.commit()
    assert _confirm(client, order.id, [_line_payload(line.id, buy_qty="5")]).status_code == 200

    row = _order_row(world, line)
    row_id = str(row.id)
    # Placed, with no link row behind it - the live "Place on PO" shape this predates.
    row.state = INQUIRY_PLACED
    db.commit()

    core.qty_ordered = Decimal("10")
    line.qty = Decimal("10")
    db.commit()
    changes = [_change(QTY_CHANGED, core, so_number=core_so.so_number, old_date=WAS_1,
                       new_date=WAS_1, old_qty="5", new_qty="10")]
    batch = _build(world, changes, core_so, [str(core.id)])
    assert batch is not None

    response = _confirm(client, order.id, [_line_payload(line.id, buy_qty="10")],
                        batch_id=str(batch.id))
    assert response.status_code == 200, response.text
    db.commit()

    placed = db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row_id).one()
    assert placed.state == INQUIRY_PLACED, "placed supply is not demoted back to raised"
    assert Decimal(str(placed.qty)) == Decimal("5"), "and it still says what was bought"
    fresh = [
        r for r in _rows_of(world, line)
        if str(r.id) != row_id and r.state != INQUIRY_CANCELLED and r.verb == IV_ORDER
    ]
    assert len(fresh) == 1
    assert Decimal(str(fresh[0].qty)) == Decimal("5"), (
        "5 already placed, 5 still outstanding - never the full 10 on top of it"
    )


# ---------------------------------------------------------------------------
# Review S6: AC-P3-11 when part of the new quantity sits on no document at all
# ---------------------------------------------------------------------------


def test_committed_v_counts_the_part_of_the_new_quantity_nobody_has_bought(api):
    """The AC-P3-11 companion. `test_committed_v_counts_twenty_five_for_the_product_and_
    nothing_else` pins the fully-covered case, where every one of the 25 sits on a
    document and the plan has nothing left to buy - which cannot tell a correct residual
    from a residual of zero. Here the closed line brought no placement with it, so 10 of
    the 25 is bought and 15 is not, and `committed_v` says 15."""
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_1 = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10",
                        required_date=WAS_1)
    core_2 = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10",
                        required_date=WAS_2)
    order = _project_so(db, world.project, so_id=core_so.id,
                        autocount_doc_no=core_so.so_number)
    line_1 = _project_line(db, order, line_no=1, product=world.product, core_line=core_1)
    line_2 = _project_line(db, order, line_no=2, product=world.product, core_line=core_2)
    db.commit()

    assert _confirm(client, order.id, [
        _line_payload(line_1.id, buy_qty="10"),
        _line_payload(line_2.id, buy_qty="10"),
    ]).status_code == 200

    # Only line 1 was ever put on a purchase order. Line 2's row is raised and bare, so
    # the retire has nothing to shift and the survivor's extra 15 stays unbought.
    supplier = _supplier(world)
    row_1 = _order_row(world, line_1)
    _, po_line_1 = _po_line(world, supplier, qty=10, expected_date=date(2026, 8, 10))
    _link(world, row_1, po_line_1, qty=10, document="202604-S0083")
    db.commit()

    core_1.qty_ordered = Decimal("25")
    core_1.required_date = NOW
    line_1.qty = Decimal("25")
    line_1.delivery_date = NOW
    core_2.line_status = "closed"
    line_2.qty = Decimal("0")
    db.commit()

    changes = [
        _change(DATE_AND_QTY_CHANGED, core_1, so_number=core_so.so_number,
                old_date=WAS_1, new_date=NOW, old_qty="10", new_qty="25"),
        _change(CLOSED, core_2, so_number=core_so.so_number, old_date=WAS_2,
                new_date=None, old_qty="10", new_qty="0"),
    ]
    batch = _build(world, changes, core_so, [str(core_1.id), str(core_2.id)])
    assert batch is not None

    response = _confirm(client, order.id, [_line_payload(line_1.id, buy_qty="25")],
                        batch_id=str(batch.id))
    assert response.status_code == 200, response.text
    db.commit()

    survivor = _order_row(world, line_1)
    assert Decimal(str(survivor.qty)) == Decimal("25")
    linked = sum(
        Decimal(str(link.qty))
        for link in ProjectOrderInquiryService(db)._links_of(survivor.id)
    )
    assert linked == Decimal("10"), "only the placement line 1 already had"

    committed = db.execute(
        text(
            "SELECT COALESCE(SUM(project_confirmed_committed), 0) "
            "FROM scm.committed_v WHERE product_id = :pid"
        ),
        {"pid": world.product.id},
    ).scalar()
    assert Decimal(str(committed)) == Decimal("15"), (
        "the part of the new quantity nobody has bought is exactly what is left to buy"
    )
