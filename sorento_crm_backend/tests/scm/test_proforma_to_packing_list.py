"""F6 / F10 - what the packing list knows about the proforma invoices behind it.

TEST-FIRST: the cbm carry-over, the per-link quantity, the add-to-existing-draft option and
the "which packing list is this PI in" reads do not exist at the time this file is written,
so every test here is expected to be red until they land.

Postgres via `pg_session` (rolled back at teardown), same as the rest of this channel: the
reader resolves its header aliases from the alias table, so these suites also prove the
migrations were run rather than merely written. Nothing is borrowed from an existing table.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.procurement import InboundShipment, InboundShipmentLine
from app.models.scm import ProformaInvoiceShipmentLink
from app.services.error_handler import AppException
from app.services.scm import proforma_invoice_service as svc
from tests._pg_fixture import pg_session
from tests.scm.fixtures.proforma_shapes import (
    kailu_proforma_workbook,
    preloading_list_workbook,
)
from tests.scm.test_proforma_invoice_import import World, _invoices, _lines
from tests.scm.test_proforma_invoice_adjust import _seed_container_sizes


def _apply_preloading(db, w: World):
    data = preloading_list_workbook(
        {
            "SRTWC287A-RL-250": w.code("A"),
            "CWB242": w.code("B"),
            "SRTWC8357-RL-180": w.code("C"),
        }
    )
    svc.apply(db, data, supplier_id=str(w.supplier.id), actor="Ms Tee")
    return _invoices(db, w)


def _shipment_lines(db, shipment_id: str) -> list[InboundShipmentLine]:
    return (
        db.query(InboundShipmentLine)
        .filter(InboundShipmentLine.shipment_id == str(shipment_id))
        .all()
    )


# --------------------------------------------------------------------------------- #
# AC-F1 - the volume survives the conversion
# --------------------------------------------------------------------------------- #


def test_converting_copies_each_lines_volume_onto_the_shipment_line():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        # Block 5 is 27.1 cbm, inside a 65 cbm 40HQ, so no override is needed.
        invoice = _apply_preloading(db, w)[4]
        matched = [ln for ln in _lines(db, invoice.id) if ln.product_id]

        out = svc.convert_to_draft_shipment(db, [str(invoice.id)])

        lines = _shipment_lines(db, out["shipment_id"])
        assert len(lines) == len(matched)
        by_product = {str(ln.product_id): ln for ln in lines}
        for pi_line in matched:
            shipment_line = by_product[str(pi_line.product_id)]
            assert float(shipment_line.cbm) == pytest.approx(float(pi_line.cbm_total))
            assert shipment_line.cartons_count == int(pi_line.cartons)


def test_an_unmeasured_invoice_leaves_the_shipment_line_volume_null():
    """AC-H3 - a PI without cbm converts as before. NULL, never 0: 0 cbm would be summed as
    a container that takes no room."""
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        svc.apply(db, kailu_proforma_workbook({"SRTWT7443": w.code("A")}),
                  supplier_id=str(w.supplier.id))
        invoice = _invoices(db, w)[0]

        out = svc.convert_to_draft_shipment(db, [str(invoice.id)])

        for line in _shipment_lines(db, out["shipment_id"]):
            assert line.cbm is None


def test_two_invoice_lines_of_one_product_add_their_volumes_up():
    """The convert groups by (product, supplier), so two lines naming the same model become
    one shipment line - and its volume is both of them, not the first one."""
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        # Kailu name SRTWT7443 on two lines. Volume is added to both of them here, since
        # their real document states none at all.
        svc.apply(db, kailu_proforma_workbook({"SRTWT7443": w.code("A")}),
                  supplier_id=str(w.supplier.id))
        invoice = _invoices(db, w)[0]
        pi_lines = [ln for ln in _lines(db, invoice.id) if str(ln.product_id or "") == str(w.product("A").id)]
        assert len(pi_lines) >= 2
        for i, line in enumerate(pi_lines, start=1):
            # Small enough that the two lines together still fit a 65 cbm 40HQ - this test
            # is about the arithmetic of the merge, not about the capacity guard.
            line.cbm_per_unit = 0.01
            line.cbm_total = 0.01 * float(line.qty)
            line.cartons = i
        db.flush()
        expected_cbm = sum(float(ln.cbm_total) for ln in pi_lines)
        expected_cartons = sum(int(ln.cartons) for ln in pi_lines)

        out = svc.convert_to_draft_shipment(db, [str(invoice.id)])

        line = next(
            ln for ln in _shipment_lines(db, out["shipment_id"])
            if str(ln.product_id) == str(w.product("A").id)
        )
        assert float(line.cbm) == pytest.approx(expected_cbm)
        assert line.cartons_count == expected_cartons


# --------------------------------------------------------------------------------- #
# AC-F6 / AC-F8 - the invoice says where its goods went
# --------------------------------------------------------------------------------- #


def _kailu_bytes(w: World, *, pi_number=None) -> bytes:
    """The Kailu proforma, optionally renumbered.

    Kailu STATE their document number (`货单号：` in G6), and identity is
    (supplier, pi_number) - so a second upload under the same number updates the first
    invoice rather than creating a second one. A test that needs two documents has to
    renumber, exactly as a second real document would be.
    """
    import openpyxl
    from io import BytesIO

    wb = openpyxl.load_workbook(BytesIO(kailu_proforma_workbook({"SRTWT7443": w.code("A")})))
    if pi_number is not None:
        wb.active["G6"] = pi_number
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _kailu_invoice(db, w: World, *, pi_number=None, source_ref="kailu.xlsx"):
    svc.apply(db, _kailu_bytes(w, pi_number=pi_number), supplier_id=str(w.supplier.id),
              actor="Ms Tee", source_ref=source_ref)
    return _invoices(db, w)[0] if pi_number is None else next(
        inv for inv in _invoices(db, w) if inv.pi_number == pi_number
    )


def test_an_untouched_invoice_reads_not_converted():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _kailu_invoice(db, w)

        out = svc.serialize(db, invoice)

        assert out["placement"] == "not_converted"
        assert out["placed_qty"] == 0
        # What is LEFT is what could ever be placed, not what the document totals: Kailu's
        # proforma names codes this catalogue does not hold, and those lines can never go on
        # a container. Counting them as outstanding would leave the invoice reading Split
        # for ever, with a remainder nobody can place.
        assert out["remaining_qty"] == out["placeable_qty"] > 0
        assert out["total_qty"] > out["placeable_qty"]
        assert out["packing_lists"] == []


def test_a_fully_placed_invoice_reads_converted_and_names_its_packing_list():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _kailu_invoice(db, w)
        shipment = svc.convert_to_draft_shipment(db, [str(invoice.id)])

        out = svc.serialize(db, svc.get_or_404(db, str(invoice.id)))

        assert out["placement"] == "converted"
        assert out["remaining_qty"] == 0
        assert [p["shipment_id"] for p in out["packing_lists"]] == [shipment["shipment_id"]]
        assert out["packing_lists"][0]["shipment_number"] == shipment["shipment_number"]


def test_placing_part_of_a_line_reads_split_and_leaves_the_remainder():
    """Q9: one invoice may sit in two containers, and it reads Split until it is fully
    placed."""
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _kailu_invoice(db, w)
        line = next(ln for ln in _lines(db, invoice.id) if ln.product_id)
        half = int(float(line.qty) // 2)

        svc.convert_to_draft_shipment(
            db, [str(invoice.id)], line_quantities={str(line.id): half}
        )

        out = svc.serialize(db, svc.get_or_404(db, str(invoice.id)))
        assert out["placement"] == "split"
        assert out["remaining_qty"] > 0
        placed_line = next(ln for ln in out["lines"] if ln["id"] == str(line.id))
        assert placed_line["placed_qty"] == half
        assert placed_line["remaining_qty"] == float(line.qty) - half
        assert placed_line["packing_lists"][0]["qty"] == half


def test_the_link_row_records_how_much_went_there():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _kailu_invoice(db, w)
        line = next(ln for ln in _lines(db, invoice.id) if ln.product_id)

        svc.convert_to_draft_shipment(
            db, [str(invoice.id)], line_quantities={str(line.id): 5}
        )

        link = (
            db.query(ProformaInvoiceShipmentLink)
            .filter(ProformaInvoiceShipmentLink.proforma_invoice_line_id == line.id)
            .one()
        )
        assert float(link.qty) == 5


def test_the_list_filters_by_where_the_goods_went():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _kailu_invoice(db, w)

        before = svc.list_for_supplier(
            db, supplier_id=str(w.supplier.id), placement="not_converted"
        )
        assert [r["id"] for r in before["data"]] == [str(invoice.id)]

        svc.convert_to_draft_shipment(db, [str(invoice.id)])

        after = svc.list_for_supplier(
            db, supplier_id=str(w.supplier.id), placement="not_converted"
        )
        assert after["data"] == []
        assert after["total"] == 0
        converted = svc.list_for_supplier(
            db, supplier_id=str(w.supplier.id), placement="converted"
        )
        assert [r["id"] for r in converted["data"]] == [str(invoice.id)]


# --------------------------------------------------------------------------------- #
# AC-F10 - convert places a remainder, and can be added to an open draft
# --------------------------------------------------------------------------------- #


def test_converting_twice_places_the_remainder_the_second_time():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _kailu_invoice(db, w)
        line = next(ln for ln in _lines(db, invoice.id) if ln.product_id)
        total = float(line.qty)

        svc.convert_to_draft_shipment(db, [str(invoice.id)], line_quantities={str(line.id): 10})
        svc.convert_to_draft_shipment(db, [str(invoice.id)])

        out = svc.serialize(db, svc.get_or_404(db, str(invoice.id)))
        placed_line = next(ln for ln in out["lines"] if ln["id"] == str(line.id))
        assert placed_line["placed_qty"] == total
        assert placed_line["remaining_qty"] == 0
        assert out["placement"] == "converted"
        assert len(placed_line["packing_lists"]) == 2


def test_an_invoice_with_nothing_left_to_place_is_refused():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _kailu_invoice(db, w)
        svc.convert_to_draft_shipment(db, [str(invoice.id)])

        with pytest.raises(AppException) as exc:
            svc.convert_to_draft_shipment(db, [str(invoice.id)])
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "already_converted"


def test_placing_more_than_a_line_has_left_is_refused():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _kailu_invoice(db, w)
        line = next(ln for ln in _lines(db, invoice.id) if ln.product_id)

        with pytest.raises(AppException) as exc:
            svc.convert_to_draft_shipment(
                db, [str(invoice.id)], line_quantities={str(line.id): float(line.qty) + 1}
            )
        assert exc.value.status_code == 422


def test_a_convert_can_be_added_to_an_open_draft_instead_of_making_a_new_one():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        first = _kailu_invoice(db, w)
        draft = svc.convert_to_draft_shipment(db, [str(first.id)])
        # A second document from the same factory, for the same container.
        second = _kailu_invoice(db, w, pi_number="KL20260801", source_ref="second.xlsx")

        out = svc.convert_to_draft_shipment(
            db, [str(second.id)], target_shipment_id=draft["shipment_id"]
        )

        assert out["shipment_id"] == draft["shipment_id"]
        # One shipment, both invoices behind it.
        source = svc.source_proforma_invoices(db, draft["shipment_id"])
        assert {i["pi_number"] for i in source["invoices"]} == {
            first.pi_number, second.pi_number
        }


def test_only_a_draft_can_be_added_to():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _kailu_invoice(db, w)
        draft = svc.convert_to_draft_shipment(db, [str(invoice.id)])
        shipment = (
            db.query(InboundShipment)
            .filter(InboundShipment.id == draft["shipment_id"])
            .one()
        )
        shipment.shipment_status = "in_transit"
        db.flush()
        second = _kailu_invoice(db, w, pi_number="KL20260801", source_ref="second.xlsx")

        with pytest.raises(AppException) as exc:
            svc.convert_to_draft_shipment(
                db, [str(second.id)], target_shipment_id=str(shipment.id)
            )
        assert exc.value.status_code == 422


def test_the_open_drafts_are_listed_for_the_dialog_to_offer():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _kailu_invoice(db, w)
        draft = svc.convert_to_draft_shipment(db, [str(invoice.id)])

        offered = svc.draft_shipments(db, supplier_id=str(w.supplier.id))

        assert draft["shipment_id"] in [d["shipment_id"] for d in offered]
        row = next(d for d in offered if d["shipment_id"] == draft["shipment_id"])
        assert row["lines"] > 0
        assert w.supplier.supplier_name in row["supplier_names"]


# --------------------------------------------------------------------------------- #
# AC-F9 - the packing list says which invoices it was drafted from
# --------------------------------------------------------------------------------- #


def test_the_packing_list_names_its_source_invoices_with_what_came_from_each():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _kailu_invoice(db, w)
        matched = [ln for ln in _lines(db, invoice.id) if ln.product_id]
        # Every placeable line takes a stated share, so the card's figure is a number this
        # test chose rather than one it inherited.
        out = svc.convert_to_draft_shipment(
            db, [str(invoice.id)], line_quantities={str(ln.id): 7 for ln in matched}
        )

        source = svc.source_proforma_invoices(db, out["shipment_id"])

        assert len(source["invoices"]) == 1
        entry = source["invoices"][0]
        assert entry["pi_number"] == invoice.pi_number
        assert entry["supplier_name"] == w.supplier.supplier_name
        assert entry["qty"] == 7 * len(matched)
        assert entry["total_qty"] > entry["qty"]
        assert entry["lines"] == len(matched)
        assert entry["source_ref"]
        # And per shipment line, so the Lines tab can name the document per row.
        shipment_line = _shipment_lines(db, out["shipment_id"])[0]
        by_line = source["by_shipment_line"][str(shipment_line.id)]
        assert by_line[0]["pi_number"] == invoice.pi_number
        assert by_line[0]["qty"] == 7


def test_a_container_with_no_proforma_behind_it_answers_empty_rather_than_404():
    with pg_session() as db:
        w = World(db)
        shipment = InboundShipment(
            id=str(uuid.uuid4()),
            shipment_number=f"ZZPL-{uuid.uuid4().hex[:8]}",
            shipment_date="2026-08-01",
            shipment_status="in_transit",
        )
        db.add(shipment)
        db.flush()

        source = svc.source_proforma_invoices(db, str(shipment.id))

        assert source["invoices"] == []
        assert source["by_shipment_line"] == {}


# --------------------------------------------------------------------------------- #
# Review finding 2 - a link whose shipment line is gone is not a container
# --------------------------------------------------------------------------------- #


def test_deleting_a_shipment_line_takes_its_proforma_links_with_it():
    """The packing list's in-place editor deletes a line the payload no longer names. The
    FK is SET NULL, so the link survived as a phantom: no shipment line, no quantity that
    can ever be received, and every guard on the invoice still reading it as converted."""
    from app.schemas.procurement import InboundShipmentUpdate
    from app.services.procurement_service import InboundShipmentService

    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _kailu_invoice(db, w)
        out = svc.convert_to_draft_shipment(db, [str(invoice.id)])
        assert (
            db.query(ProformaInvoiceShipmentLink)
            .filter(
                ProformaInvoiceShipmentLink.proforma_invoice_id == invoice.id,
                ProformaInvoiceShipmentLink.inbound_shipment_line_id.isnot(None),
            )
            .count()
            > 0
        )

        # Save the packing list with no lines at all - what Remove-then-Save does.
        InboundShipmentService(db).update_shipment(
            out["shipment_id"], InboundShipmentUpdate(shipment_lines=[]), None
        )

        # Not one link naming a shipment line is left. The SKIP rows stay - they record
        # that the convert ran and could not carry those lines, which is still true.
        assert (
            db.query(ProformaInvoiceShipmentLink)
            .filter(
                ProformaInvoiceShipmentLink.proforma_invoice_id == invoice.id,
                ProformaInvoiceShipmentLink.inbound_shipment_line_id.isnot(None),
            )
            .count()
            == 0
        )


def test_an_invoice_whose_shipment_lines_were_deleted_can_be_converted_again():
    from app.schemas.procurement import InboundShipmentUpdate
    from app.services.procurement_service import InboundShipmentService

    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _kailu_invoice(db, w)
        out = svc.convert_to_draft_shipment(db, [str(invoice.id)])
        InboundShipmentService(db).update_shipment(
            out["shipment_id"], InboundShipmentUpdate(shipment_lines=[]), None
        )

        detail = svc.serialize(db, svc.get_or_404(db, str(invoice.id)))
        assert detail["placement"] == "not_converted"
        # And it is editable again - the goods are on no container.
        line = _lines(db, invoice.id)[0]
        svc.adjust_line(db, str(invoice.id), str(line.id), qty=1, actor="Ms Tee")


def test_an_invoice_matching_no_product_says_so_rather_than_already_converted():
    """Nothing has ever been placed, so "already converted" is the wrong sentence - and it
    sends the reader to look for a container that does not exist."""
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _kailu_invoice(db, w)
        # Every line names a code this catalogue does not hold. Set here rather than by
        # uploading un-mapped codes: the local database is a copy of production, so the
        # real file's own item codes DO resolve on it and the test would prove nothing.
        for line in _lines(db, invoice.id):
            line.product_id = None
        db.flush()

        with pytest.raises(AppException) as exc:
            svc.convert_to_draft_shipment(db, [str(invoice.id)])

        assert exc.value.status_code == 422
        assert exc.value.detail["detail"] == "unmatched"


# --------------------------------------------------------------------------------- #
# Review finding 6 - a fractional quantity is placed, not truncated
# --------------------------------------------------------------------------------- #


def test_a_fractional_line_is_fully_placed_rather_than_reading_split_for_ever():
    """`proforma_invoice_line.qty` is Numeric. Truncating the placement to a whole number
    left 0.5 outstanding on a line nothing else would ever place, so the invoice read Split
    for ever and could never be converted again."""
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _kailu_invoice(db, w)
        matched = [ln for ln in _lines(db, invoice.id) if ln.product_id]
        for ln in matched:
            ln.qty = Decimal("12.5")
            ln.cbm_per_unit = None
            ln.cbm_total = None
        for ln in _lines(db, invoice.id):
            if ln.product_id is None:
                ln.product_id = None
        db.flush()

        out = svc.convert_to_draft_shipment(db, [str(invoice.id)])

        detail = svc.serialize(db, svc.get_or_404(db, str(invoice.id)))
        placed = next(ln for ln in detail["lines"] if ln["id"] == str(matched[0].id))
        assert placed["placed_qty"] == 12.5
        assert placed["remaining_qty"] == 0
        assert detail["placement"] == "converted"
        # The link carries the fraction; the container's own line is whole pieces, as its
        # integer column has always been.
        link = (
            db.query(ProformaInvoiceShipmentLink)
            .filter(
                ProformaInvoiceShipmentLink.proforma_invoice_line_id == matched[0].id,
                ProformaInvoiceShipmentLink.inbound_shipment_line_id.isnot(None),
            )
            .one()
        )
        assert float(link.qty) == 12.5
        assert out["shipment_id"]


def test_a_fractional_split_places_exactly_what_was_asked_for():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _kailu_invoice(db, w)
        line = next(ln for ln in _lines(db, invoice.id) if ln.product_id)
        line.qty = Decimal("10")
        db.flush()

        svc.convert_to_draft_shipment(
            db, [str(invoice.id)], line_quantities={str(line.id): 2.5}
        )

        detail = svc.serialize(db, svc.get_or_404(db, str(invoice.id)))
        placed = next(ln for ln in detail["lines"] if ln["id"] == str(line.id))
        assert placed["placed_qty"] == 2.5
        assert placed["remaining_qty"] == 7.5


# --------------------------------------------------------------------------------- #
# Review finding 8 - two converts of one invoice cannot both win
# --------------------------------------------------------------------------------- #


def test_the_convert_locks_the_invoice_before_it_reads_what_is_placed():
    """Migration 429 dropped the unique index that made a double convert impossible, and
    the arithmetic that replaced it ("what is placed against what can be placed") is a READ
    - so two overlapping converts both saw an unplaced invoice and both placed it.

    The row is locked FOR UPDATE before that read, so the second one waits and then sees
    the first one's work. Asserted as "the lock is taken, and taken first" rather than with
    two live connections: this suite runs inside one rolled-back transaction, and a second
    connection contending for the same row would block on it until the test timed out.
    """
    from sqlalchemy import event

    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        invoice = _kailu_invoice(db, w)

        statements: list[str] = []

        def record(conn, cursor, statement, parameters, context, executemany):
            statements.append(" ".join(statement.split()))

        engine = db.get_bind()
        event.listen(engine, "before_cursor_execute", record)
        try:
            svc.convert_to_draft_shipment(db, [str(invoice.id)])
        finally:
            event.remove(engine, "before_cursor_execute", record)

        locks = [
            i for i, sql in enumerate(statements)
            if "FROM scm.proforma_invoice" in sql and "FOR UPDATE" in sql
        ]
        reads = [
            i for i, sql in enumerate(statements)
            if "scm.proforma_invoice_shipment_link" in sql
        ]
        assert locks, "the convert never locked the invoice it is about to place"
        assert reads, "the convert never read what is already placed"
        assert locks[0] < reads[0], "the placement was read before the row was locked"


def test_adding_to_a_draft_locks_the_draft_too():
    """Two converts adding to the SAME draft race on its contents - the capacity gate reads
    what the box already holds, and both would read it empty."""
    from sqlalchemy import event

    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        first = _kailu_invoice(db, w)
        draft = svc.convert_to_draft_shipment(db, [str(first.id)])
        second = _kailu_invoice(db, w, pi_number="KL20260801", source_ref="second.xlsx")

        statements: list[str] = []

        def record(conn, cursor, statement, parameters, context, executemany):
            statements.append(" ".join(statement.split()))

        engine = db.get_bind()
        event.listen(engine, "before_cursor_execute", record)
        try:
            svc.convert_to_draft_shipment(
                db, [str(second.id)], target_shipment_id=draft["shipment_id"]
            )
        finally:
            event.remove(engine, "before_cursor_execute", record)

        assert any(
            "FROM inbound_shipments" in sql and "FOR UPDATE" in sql for sql in statements
        ), "the draft everyone is loading into was never locked"


# --------------------------------------------------------------------------------- #
# Browser finding 1 - a SKIP row is not a container
# --------------------------------------------------------------------------------- #


def _skip_only_invoice(db, w: World):
    """An invoice whose only conversion outcome is a SKIP.

    Built the way the dev database produced it: two invoices converted in ONE action, one
    with a matched line and one without. The convert succeeds on the first and records why
    the second went nowhere - a link row with no shipment line and an `unmatched_reason`.
    """
    carrier = _kailu_invoice(db, w)
    skipped = _kailu_invoice(db, w, pi_number="KL20260801", source_ref="second.xlsx")
    for line in _lines(db, skipped.id):
        line.product_id = None
    db.flush()

    svc.convert_to_draft_shipment(db, [str(carrier.id), str(skipped.id)])

    links = (
        db.query(ProformaInvoiceShipmentLink)
        .filter(ProformaInvoiceShipmentLink.proforma_invoice_id == skipped.id)
        .all()
    )
    assert links and all(l.inbound_shipment_line_id is None for l in links)
    assert all(l.unmatched_reason for l in links)
    return skipped


def test_a_skip_only_invoice_reads_as_on_no_container_at_all():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        skipped = _skip_only_invoice(db, w)

        out = svc.serialize(db, svc.get_or_404(db, str(skipped.id)))

        assert out["placement"] == "not_converted"
        assert out["placed_qty"] == 0
        # The header's own list of containers - a skip names a shipment it never went on,
        # and the panel that reads this locked the invoice for editing because of it.
        assert out["converted_shipments"] == []


def test_a_skip_only_invoice_can_still_be_adjusted():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        skipped = _skip_only_invoice(db, w)
        line = _lines(db, skipped.id)[0]

        out = svc.adjust_line(db, str(skipped.id), str(line.id), qty=3, actor="Ms Tee")

        assert out["lines"][0]["qty"] == 3


def test_a_skipped_line_is_offered_again_once_its_product_is_matched():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        skipped = _skip_only_invoice(db, w)
        line = _lines(db, skipped.id)[0]
        # Somebody fixed the catalogue and the code now resolves.
        line.product_id = w.product("A").id
        db.flush()

        detail = svc.serialize(db, svc.get_or_404(db, str(skipped.id)))
        offered = next(ln for ln in detail["lines"] if ln["id"] == str(line.id))
        assert offered["remaining_qty"] == offered["qty"]
        assert offered["placed_qty"] == 0

        out = svc.convert_to_draft_shipment(db, [str(skipped.id)])
        assert out["shipment_id"]


def test_a_skipped_line_says_why_rather_than_reading_as_placed():
    with pg_session() as db:
        _seed_container_sizes(db)
        w = World(db)
        skipped = _skip_only_invoice(db, w)

        detail = svc.serialize(db, svc.get_or_404(db, str(skipped.id)))

        line = detail["lines"][0]
        assert line["matched"] is False
        assert line["unmatched_reason"]
        assert line["placed_qty"] == 0
        assert line["packing_lists"] == []
