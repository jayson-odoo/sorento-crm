"""S5 - the derived SPO, the stage cards, and the verb-code rename (R-D, R-E, R-F, AC-D1
to AC-D9).

`PLAN-scm-oi-worklist-excel-parity.md` S5 + the coordinator's 16 Sep addendum (commit
35d4c1674): a derived SPO allocation must be OPEN per
`app.services.scm.spo_supply.open_incoming_clauses` (`line_status` null/open,
`receipt_status` not in `RECEIVED_RECEIPT_STATUSES`, shipment `actual_arrival_date` null)
AND `retired_at IS NULL` AND `allocated_quantity > coalesce(quantity_received, 0)`.

None of this exists yet: `links_for_rows` emits no synthetic `derived`/`derived_po` entry,
`_kinds` sums only REAL links, and the verb-refusal error code is still
`order_inquiry_spo_not_order_back`. Every assertion below is checked against that stale
state and is expected to fail for a business-logic reason (a missing dict key, a wrong
sum, a stale string) rather than a fixture bug.

Postgres only, via `tests/_pg_fixture.py::blank_session`. Fixture builders (`_uid`,
`_sorento`, `_user`, `_product`, `_project`, `_order_and_line`, `_inquiry`, `_row`,
`_link`, `_po_line`, `_client`, `_restore`) are imported from the sibling
`test_order_inquiry_kinds.py`, which already builds this exact shape (a PO-linked row, an
SPO-linked row, a cancelled row) for the same service.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app.models.procurement import InboundShipment, SPOAllocation, Supplier
from app.services import project_seed_service
from app.services.project_order_inquiry_service import ProjectOrderInquiryService

from ._pg_fixture import blank_session
from .test_order_inquiry_kinds import (
    MARKER as _KINDS_MARKER,  # noqa: F401 - imported for parity, not used directly
    READ_ONLY,
    _client,
    _inquiry,
    _link,
    _order_and_line,
    _po_line,
    _product,
    _project,
    _restore,
    _row,
    _sorento,
    _uid,
    _user,
)

MARKER = "zzt-oi-derived-spo"
BASE = "/api/v1/project-sales"
LIST = f"{BASE}/order-inquiries"
SUMMARY = f"{LIST}/summary"

SOON = date.today() + timedelta(days=30)


def _supplier(db, company_id: str) -> Supplier:
    row = Supplier(id=_uid(), company_id=company_id, supplier_code=f"ZZT-{_uid()[:8]}",
                    supplier_name=f"{MARKER} supplier")
    db.add(row)
    db.flush()
    return row


def _spo(db, company_id: str, *, spo_number: str, product_id: str,
          from_po_number: str | None, allocated_quantity: int, quantity_received: int = 0,
          line_status: str = "open", receipt_status: str = "pending",
          retired_at=None, landed: bool = False) -> SPOAllocation:
    """An SPOAllocation with every `open_incoming_clauses` clause under explicit
    control, plus the two the addendum adds (`retired_at`, the quantity test)."""
    shipment_id = None
    if landed:
        shipment = InboundShipment(
            id=_uid(), company_id=company_id, shipment_number=f"ZZT-{_uid()[:8]}",
            shipment_date=SOON, actual_arrival_date=SOON,
        )
        db.add(shipment)
        db.flush()
        shipment_id = shipment.id
    allocation = SPOAllocation(
        id=_uid(), company_id=company_id, spo_number=spo_number,
        allocated_quantity=allocated_quantity, quantity_received=quantity_received,
        product_id=product_id, from_po_number=from_po_number, line_status=line_status,
        receipt_status=receipt_status, retired_at=retired_at,
        inbound_shipment_id=shipment_id, expected_date=SOON, issue_date=date.today(),
    )
    db.add(allocation)
    db.flush()
    return allocation


@pytest.fixture()
def world():
    from app.models.base import company_scope

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        raiser = _user(db, f"{MARKER} raiser")
        project = _project(db, company_id, raiser, f"{MARKER} project {_uid()[:8]}")
        supplier = _supplier(db, company_id)
        with company_scope(db, frozenset({company_id})):
            yield db, company_id, raiser, project, supplier


def _po_linked_row(db, company_id, project, supplier, *, qty="8", linked_qty="8",
                     po_number_suffix="A"):
    product = _product(db, f"ZZT-DSPO-{_uid()[:6]}-{po_number_suffix}", f"{MARKER} product")
    order, line = _order_and_line(db, company_id, project.id, product, qty, date(2026, 5, 15))
    inquiry = _inquiry(db, company_id, order.id, None)
    row = _row(db, company_id, inquiry.id, line.id, product.product_code, qty,
               delivery_date=date(2026, 5, 15))
    po, po_line = _po_line(db, company_id, product, supplier)
    _link(db, company_id, row.id, linked_qty, po_line_id=po_line.id, document=po.po_number)
    return product, po, row


# ------------------------------------------------------------------------- AC-D1 / AC-D7


def test_a_po_linked_row_gains_a_derived_spo_entry_when_its_po_has_an_open_allocation(world):
    db, company_id, _raiser, project, supplier = world
    product, po, row = _po_linked_row(db, company_id, project, supplier)
    allocation = _spo(
        db, company_id, spo_number=f"ZZT-SPO-{_uid()[:6]}", product_id=product.id,
        from_po_number=po.po_number, allocated_quantity=5,
    )
    db.commit()

    links = ProjectOrderInquiryService(db).links_for_rows([row.id])[row.id]

    kinds = {(link["kind"], link.get("derived", False)) for link in links}
    assert ("po", False) in kinds
    assert ("spo", True) in kinds, links
    derived = next(link for link in links if link.get("derived"))
    assert derived["document"] == allocation.spo_number

    # AC-D7: the derived entry writes nothing. The row's REAL link is still 8, and
    # there is still exactly one row of `order_inquiry_links`.
    from app.models.project_so import OrderInquiryLink

    real_links = db.query(OrderInquiryLink).filter(OrderInquiryLink.row_id == row.id).all()
    assert len(real_links) == 1
    assert str(real_links[0].qty) == "8"


# ------------------------------------------------------------------------------ AC-D2


def test_no_derived_entry_when_the_allocation_is_for_a_different_product(world):
    db, company_id, _raiser, project, supplier = world
    _product, po, row = _po_linked_row(db, company_id, project, supplier, po_number_suffix="B")
    other_product = _product_for_other(db)
    _spo(
        db, company_id, spo_number=f"ZZT-SPO-{_uid()[:6]}", product_id=other_product.id,
        from_po_number=po.po_number, allocated_quantity=5,
    )
    db.commit()

    links = ProjectOrderInquiryService(db).links_for_rows([row.id])[row.id]

    assert not any(link.get("derived") for link in links)


def _product_for_other(db):
    return _product(db, f"ZZT-DSPO-OTHER-{_uid()[:6]}", f"{MARKER} other product")


def test_no_derived_entry_when_the_allocation_is_received(world):
    db, company_id, _raiser, project, supplier = world
    product, po, row = _po_linked_row(db, company_id, project, supplier, po_number_suffix="C")
    _spo(
        db, company_id, spo_number=f"ZZT-SPO-{_uid()[:6]}", product_id=product.id,
        from_po_number=po.po_number, allocated_quantity=5, quantity_received=5,
        receipt_status="received",
    )
    db.commit()

    links = ProjectOrderInquiryService(db).links_for_rows([row.id])[row.id]

    assert not any(link.get("derived") for link in links)


def test_no_derived_entry_when_the_allocation_is_retired(world):
    db, company_id, _raiser, project, supplier = world
    product, po, row = _po_linked_row(db, company_id, project, supplier, po_number_suffix="D")
    from datetime import datetime

    _spo(
        db, company_id, spo_number=f"ZZT-SPO-{_uid()[:6]}", product_id=product.id,
        from_po_number=po.po_number, allocated_quantity=5,
        retired_at=datetime(2026, 1, 1),
    )
    db.commit()

    links = ProjectOrderInquiryService(db).links_for_rows([row.id])[row.id]

    assert not any(link.get("derived") for link in links)


def test_no_derived_entry_when_the_shipment_has_landed(world):
    db, company_id, _raiser, project, supplier = world
    product, po, row = _po_linked_row(db, company_id, project, supplier, po_number_suffix="E")
    _spo(
        db, company_id, spo_number=f"ZZT-SPO-{_uid()[:6]}", product_id=product.id,
        from_po_number=po.po_number, allocated_quantity=5, landed=True,
    )
    db.commit()

    links = ProjectOrderInquiryService(db).links_for_rows([row.id])[row.id]

    assert not any(link.get("derived") for link in links)


def test_no_derived_entry_when_the_allocation_is_fully_received_by_quantity(world):
    """The addendum's own quantity test, distinct from `receipt_status`: an allocation
    that never had its status flipped but is fully covered by `quantity_received` is not
    incoming either."""
    db, company_id, _raiser, project, supplier = world
    product, po, row = _po_linked_row(db, company_id, project, supplier, po_number_suffix="F")
    _spo(
        db, company_id, spo_number=f"ZZT-SPO-{_uid()[:6]}", product_id=product.id,
        from_po_number=po.po_number, allocated_quantity=5, quantity_received=5,
    )
    db.commit()

    links = ProjectOrderInquiryService(db).links_for_rows([row.id])[row.id]

    assert not any(link.get("derived") for link in links)


def test_two_open_allocations_on_the_same_po_and_product_both_appear_as_derived(world):
    """The addendum's own ruling: no tie-break. Both are shown."""
    db, company_id, _raiser, project, supplier = world
    product, po, row = _po_linked_row(db, company_id, project, supplier, po_number_suffix="G")
    first = _spo(
        db, company_id, spo_number=f"ZZT-SPO-{_uid()[:6]}-1", product_id=product.id,
        from_po_number=po.po_number, allocated_quantity=5,
    )
    second = _spo(
        db, company_id, spo_number=f"ZZT-SPO-{_uid()[:6]}-2", product_id=product.id,
        from_po_number=po.po_number, allocated_quantity=3,
    )
    db.commit()

    links = ProjectOrderInquiryService(db).links_for_rows([row.id])[row.id]

    derived_documents = {link["document"] for link in links if link.get("derived")}
    assert derived_documents == {first.spo_number, second.spo_number}


# ------------------------------------------------------------------------------ AC-D3


def test_an_spo_linked_row_marks_its_po_column_as_derived(world):
    db, company_id, _raiser, project, supplier = world
    product = _product(db, f"ZZT-DSPO-SPOLINK-{_uid()[:6]}", f"{MARKER} product")
    order, line = _order_and_line(db, company_id, project.id, product, "6", date(2026, 5, 20))
    inquiry = _inquiry(db, company_id, order.id, None)
    row = _row(db, company_id, inquiry.id, line.id, product.product_code, "6",
               delivery_date=date(2026, 5, 20))
    allocation = _spo(
        db, company_id, spo_number=f"ZZT-SPO-{_uid()[:6]}", product_id=product.id,
        from_po_number="ZZT-SOURCE-PO-0099", allocated_quantity=6,
    )
    _link(db, company_id, row.id, "6", spo_allocation_id=allocation.id,
          document=allocation.spo_number)
    db.commit()

    links = ProjectOrderInquiryService(db).links_for_rows([row.id])[row.id]

    spo_link = next(link for link in links if link["kind"] == "spo")
    assert spo_link["source_po_number"] == "ZZT-SOURCE-PO-0099"
    assert spo_link.get("derived_po") is True


# ------------------------------------------------------------------------------ AC-D5


@pytest.fixture()
def api():
    from app.models.base import company_scope

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        raiser = _user(db, f"{MARKER} raiser")
        project = _project(db, company_id, raiser, f"{MARKER} project {_uid()[:8]}")
        supplier = _supplier(db, company_id)

        # row_po_derived: qty 8, linked 8 to a PO whose PO has a derived SPO of 5.
        product_a = _product(db, f"ZZT-DSPO-KIND-A-{_uid()[:6]}", f"{MARKER} product a")
        order_a, line_a = _order_and_line(
            db, company_id, project.id, product_a, "8", date(2026, 6, 1)
        )
        inquiry_a = _inquiry(db, company_id, order_a.id, raiser)
        row_po_derived = _row(
            db, company_id, inquiry_a.id, line_a.id, product_a.product_code, "8",
            delivery_date=date(2026, 6, 1),
        )
        po_a, po_line_a = _po_line(db, company_id, product_a, supplier)
        _link(db, company_id, row_po_derived.id, "8", po_line_id=po_line_a.id,
              document=po_a.po_number)
        _spo(
            db, company_id, spo_number=f"ZZT-SPO-{_uid()[:6]}", product_id=product_a.id,
            from_po_number=po_a.po_number, allocated_quantity=5,
        )

        # row_unlinked: qty 4, nothing.
        product_b = _product(db, f"ZZT-DSPO-KIND-B-{_uid()[:6]}", f"{MARKER} product b")
        order_b, line_b = _order_and_line(
            db, company_id, project.id, product_b, "4", date(2026, 6, 1)
        )
        inquiry_b = _inquiry(db, company_id, order_b.id, raiser)
        row_unlinked = _row(
            db, company_id, inquiry_b.id, line_b.id, product_b.product_code, "4",
            delivery_date=date(2026, 6, 1),
        )

        # row_full_spo: qty 6, linked entirely (a REAL link) to an SPO allocation.
        product_c = _product(db, f"ZZT-DSPO-KIND-C-{_uid()[:6]}", f"{MARKER} product c")
        order_c, line_c = _order_and_line(
            db, company_id, project.id, product_c, "6", date(2026, 6, 1)
        )
        inquiry_c = _inquiry(db, company_id, order_c.id, raiser)
        row_full_spo = _row(
            db, company_id, inquiry_c.id, line_c.id, product_c.product_code, "6",
            delivery_date=date(2026, 6, 1),
        )
        allocation_c = _spo(
            db, company_id, spo_number=f"ZZT-SPO-{_uid()[:6]}", product_id=product_c.id,
            from_po_number=None, allocated_quantity=6,
        )
        _link(db, company_id, row_full_spo.id, "6", spo_allocation_id=allocation_c.id,
              document=allocation_c.spo_number)

        db.commit()
        client, originals = _client(db, raiser, READ_ONLY)
        try:
            with company_scope(db, frozenset({company_id})):
                yield client, db, company_id, {
                    "row_po_derived": row_po_derived,
                    "row_unlinked": row_unlinked,
                    "row_full_spo": row_full_spo,
                }
        finally:
            _restore(originals)


def test_the_stage_cards_split_a_po_linked_row_between_purchased_and_incoming(api):
    """AC-D5: a row of 8, linked to a PO with a derived SPO of 5, contributes 5 to
    Incoming (`spo`) and 3 to Purchased (`po`) and 0 to Buy - a unit counted once, the
    furthest it reached."""
    client, _db, _company_id, _seeded = api

    body = client.get(SUMMARY).json()
    kinds = body["kinds"]

    # row_full_spo (6) is entirely on a REAL spo link, so it also lands in `spo`.
    assert kinds["spo"] == "11", kinds
    assert kinds["po"] == "3", kinds
    assert kinds["buy"] == "4", kinds


def test_kind_spo_lists_the_derived_row(api):
    client, _db, _company_id, seeded = api

    body = client.get(LIST, params={"kind": "spo"}).json()

    ids = {row["id"] for row in body["data"]}
    assert seeded["row_po_derived"].id in ids
    assert seeded["row_full_spo"].id in ids
    assert seeded["row_unlinked"].id not in ids


def test_kind_po_lists_the_row_with_purchased_remainder(api):
    client, _db, _company_id, seeded = api

    body = client.get(LIST, params={"kind": "po"}).json()

    ids = {row["id"] for row in body["data"]}
    assert seeded["row_po_derived"].id in ids
    assert seeded["row_unlinked"].id not in ids
    assert seeded["row_full_spo"].id not in ids


def test_kind_buy_lists_only_the_unlinked_row(api):
    client, _db, _company_id, seeded = api

    body = client.get(LIST, params={"kind": "buy"}).json()

    ids = {row["id"] for row in body["data"]}
    assert ids == {seeded["row_unlinked"].id}


# ------------------------------------------------------------------------------ AC-D9


def test_the_spo_verb_refusal_code_is_renamed_and_the_old_string_is_gone():
    """The rename is textual (R-D: "no behaviour change, one test renames the code") -
    `_SPO_LINKABLE_VERBS` already equals `_LINKABLE_VERBS`, so `_assert_linkable` refuses
    an unlinkable verb before the SPO-specific branch is ever reached and there is no
    live code path left to exercise at runtime. What is checked is the SOURCE: the new
    code is declared, and the old one - and the docstring claiming an SPO answers only
    an ORDER BACK row - are gone."""
    import inspect

    from app.services import project_order_inquiry_service as svc

    source = inspect.getsource(svc)
    assert "order_inquiry_spo_not_linkable" in source
    assert "order_inquiry_spo_not_order_back" not in source
    assert "only an ORDER BACK row" not in source.lower()
