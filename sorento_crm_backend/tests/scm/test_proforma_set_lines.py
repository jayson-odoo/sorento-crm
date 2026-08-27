"""F12 / R21 - a proforma line bound to a SET becomes one packing-list line per member.

TEST-FIRST: `convert_to_draft_shipment` skips a line with no `product_id` when this file is
written, so a set line would be reported as "no catalogue product matches" - every test here
is expected to be red until slot C lands.

`inbound_shipment_lines.product_id` is NOT NULL and stock lives on members, so a set has
nowhere to be written on a container. The conversion therefore EXPLODES it: one line per
member, `qty x member.quantity`, all of them pointing back at the same proforma line. The
invoice itself keeps the set code, because that is what the supplier reads and what the
document they sent actually says.

The set's own figures - its price and its volume - land on the FIRST member the author
listed, not on all of them: a set priced once must not become N priced lines, and a set that
takes one carton must not become N cartons, or the container reads as several times its real
size and the capacity gate refuses a box that fits.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.procurement import InboundShipmentLine
from app.models.product_set import ProductSet, ProductSetMember
from app.models.scm import ProformaInvoice, ProformaInvoiceLine, ProformaInvoiceShipmentLink
from app.services.scm import proforma_invoice_service as svc
from tests._pg_fixture import pg_session
from tests.scm.test_proforma_invoice_adjust import _seed_container_sizes
from tests.scm.test_proforma_invoice_import import World

MARKER = "ZZPS"


def _uid() -> str:
    return str(uuid.uuid4())


def _set(db, w: World, code: str, members: list) -> ProductSet:
    """`members` are `(product key, quantity, sort_order)` - the author's own order."""
    product_set = ProductSet(
        id=_uid(), set_code=f"{MARKER}-{code}-{w.tag}", name=code, is_active=True
    )
    db.add(product_set)
    db.flush()
    for key, quantity, sort_order in members:
        db.add(
            ProductSetMember(
                id=_uid(),
                product_set_id=product_set.id,
                product_id=w.product(key).id,
                quantity=quantity,
                sort_order=sort_order,
            )
        )
    db.flush()
    return product_set


def _invoice_with_set_line(
    db,
    w: World,
    product_set: ProductSet,
    *,
    qty: float = 10,
    unit_price: float | None = 250,
    cbm_per_unit: float | None = 0.19,
    cartons: float | None = 10,
) -> ProformaInvoice:
    invoice = ProformaInvoice(
        id=_uid(),
        supplier_id=w.supplier.id,
        pi_number=f"{MARKER}-PI-{uuid.uuid4().hex[:8]}",
        invoice_date=date(2026, 8, 1),
        currency="CNY",
        line_count=1,
        status="current",
    )
    db.add(invoice)
    db.flush()
    db.add(
        ProformaInvoiceLine(
            id=_uid(),
            invoice_id=invoice.id,
            line_no=1,
            item_code=product_set.set_code,
            product_id=None,
            product_set_id=product_set.id,
            qty=qty,
            unit_price=unit_price,
            cbm_per_unit=cbm_per_unit,
            cbm_total=(cbm_per_unit * qty) if cbm_per_unit is not None else None,
            cartons=cartons,
        )
    )
    db.flush()
    return invoice


def _shipment_lines(db, shipment_id: str) -> list[InboundShipmentLine]:
    return (
        db.query(InboundShipmentLine)
        .filter(InboundShipmentLine.shipment_id == str(shipment_id))
        .all()
    )


def _links(db, invoice_id: str) -> list[ProformaInvoiceShipmentLink]:
    return (
        db.query(ProformaInvoiceShipmentLink)
        .filter(ProformaInvoiceShipmentLink.proforma_invoice_id == str(invoice_id))
        .all()
    )


def _wc(db, w: World) -> ProductSet:
    """Pedestal first, cistern second - the order the author listed them in."""
    return _set(db, w, "CWC605-RL", [("CWCX605-RL", 1, 0), ("CWCY605", 1, 1)])


# --------------------------------------------------------------------------------- #
# The explosion (AC-F12.7)
# --------------------------------------------------------------------------------- #


def test_a_set_line_becomes_one_shipment_line_per_member():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _invoice_with_set_line(db, w, _wc(db, w), qty=10)

        out = svc.convert_to_draft_shipment(db, [str(invoice.id)])

        lines = _shipment_lines(db, out["shipment_id"])
        assert {str(l.product_id) for l in lines} == {
            str(w.product("CWCX605-RL").id),
            str(w.product("CWCY605").id),
        }
        assert {l.quantity_shipped for l in lines} == {10}
        assert out["lines_skipped"] == 0


def test_a_member_quantity_multiplies_the_line():
    """Two seat covers per set is two per set on the container, not one."""
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        product_set = _set(
            db, w, "CWC605-RL", [("CWCX605-RL", 1, 0), ("CWC605-SC", 2, 1)]
        )
        invoice = _invoice_with_set_line(db, w, product_set, qty=10)

        out = svc.convert_to_draft_shipment(db, [str(invoice.id)])

        by_product = {str(l.product_id): l for l in _shipment_lines(db, out["shipment_id"])}
        assert by_product[str(w.product("CWCX605-RL").id)].quantity_shipped == 10
        assert by_product[str(w.product("CWC605-SC").id)].quantity_shipped == 20


def test_every_member_line_points_back_at_the_same_proforma_line():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _invoice_with_set_line(db, w, _wc(db, w), qty=10)
        pi_line = db.query(ProformaInvoiceLine).filter(
            ProformaInvoiceLine.invoice_id == invoice.id
        ).one()

        out = svc.convert_to_draft_shipment(db, [str(invoice.id)])

        links = _links(db, str(invoice.id))
        assert len(links) == 2
        assert {str(l.proforma_invoice_line_id) for l in links} == {str(pi_line.id)}
        assert {str(l.inbound_shipment_line_id) for l in links} == {
            str(l.id) for l in _shipment_lines(db, out["shipment_id"])
        }


def test_the_invoice_reads_as_converted_not_as_double_placed():
    """The placed quantity is the SET's, recorded once. Ten sets going onto one container as
    twenty pieces is still ten sets placed, and an invoice reporting twenty would be finished
    twice over."""
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _invoice_with_set_line(db, w, _wc(db, w), qty=10)

        svc.convert_to_draft_shipment(db, [str(invoice.id)])

        serialized = svc.serialize(db, svc.get_or_404(db, str(invoice.id)))
        assert serialized["placed_qty"] == 10.0
        assert serialized["remaining_qty"] == 0.0
        assert serialized["placement"] == "converted"
        assert len(serialized["lines"]) == 1


def test_the_set_line_keeps_the_set_code_on_the_invoice():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        product_set = _wc(db, w)
        invoice = _invoice_with_set_line(db, w, product_set, qty=10)

        svc.convert_to_draft_shipment(db, [str(invoice.id)])

        line = db.query(ProformaInvoiceLine).filter(
            ProformaInvoiceLine.invoice_id == invoice.id
        ).one()
        assert line.item_code == product_set.set_code
        assert str(line.product_set_id) == str(product_set.id)


# --------------------------------------------------------------------------------- #
# The set's own figures land once
# --------------------------------------------------------------------------------- #


def test_the_volume_and_the_cartons_are_the_sets_not_every_members():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _invoice_with_set_line(
            db, w, _wc(db, w), qty=10, cbm_per_unit=0.19, cartons=10
        )

        out = svc.convert_to_draft_shipment(db, [str(invoice.id)])

        lines = _shipment_lines(db, out["shipment_id"])
        assert sum(float(l.cbm or 0) for l in lines) == pytest.approx(1.9)
        # `cartons_count` is NOT NULL with a default of 1, so the sibling keeps that default
        # rather than reading as a line that shipped in no box at all.
        assert max(l.cartons_count for l in lines) == 10


def test_the_price_lands_on_the_first_member_and_is_not_charged_twice():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _invoice_with_set_line(db, w, _wc(db, w), qty=10, unit_price=250)

        out = svc.convert_to_draft_shipment(db, [str(invoice.id)])

        by_product = {str(l.product_id): l for l in _shipment_lines(db, out["shipment_id"])}
        assert float(by_product[str(w.product("CWCX605-RL").id)].unit_cost) == 250.0
        assert by_product[str(w.product("CWCY605").id)].unit_cost is None


# --------------------------------------------------------------------------------- #
# What is still refused
# --------------------------------------------------------------------------------- #


def test_a_set_with_no_members_is_skipped_and_says_why():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        empty = _set(db, w, "EMPTY", [])
        w.product("OTHER")
        invoice = _invoice_with_set_line(db, w, empty, qty=10)
        db.add(
            ProformaInvoiceLine(
                id=_uid(),
                invoice_id=invoice.id,
                line_no=2,
                item_code=w.product("OTHER").product_code,
                product_id=w.product("OTHER").id,
                qty=5,
            )
        )
        db.flush()

        out = svc.convert_to_draft_shipment(db, [str(invoice.id)])

        assert out["lines_skipped"] == 1
        assert "member" in out["unmatched"][0]["reason"].lower()


def test_a_set_line_counts_as_placeable_so_the_invoice_is_not_stuck_unconverted():
    """`_placeable` used to answer 0 for any line without a product id, which would have
    left a set-only invoice reading "nothing can ever be placed" and refused outright."""
    with pg_session() as db:
        w = World(db)
        line = ProformaInvoiceLine(
            id=_uid(),
            invoice_id=_uid(),
            line_no=1,
            item_code="X",
            product_id=None,
            product_set_id=_uid(),
            qty=10,
        )

        assert svc._placeable(line) == 10.0
