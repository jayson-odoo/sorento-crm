"""The order inquiry sheet pairs on AutoCount's OWN line reference.

Contract: `documentation/plans/scm/scm-oi-sheet-pairing-repair-acceptance-criteria.md`,
AC-R-1 to AC-R-16, with `PLAN-scm-oi-sheet-pairing-repair.md` sections 2.1 to 2.4 for the
promised behaviour. One test per criterion, named for it.

TEST-FIRST, written before the importer was repaired. The red state is therefore the
SHIPPED behaviour of #875 - no link at all where AutoCount states one, the wrong sales
order line under a citation, two rows raised where the customer restated one - or a
`ModuleNotFoundError` for a rollback script that does not exist yet. Never an import typo
and never a fixture bug.

What changes, in the operator's words (owner rulings R1 to R3, 14 Sep 2026):

* **R1** the pairing is `purchase_order_lines.from_so_line_ref = sales_order_lines.source_ref`
  (and the `spo_allocations` twin, and `from_po_number` onwards to the shipping order).
  Claims become the FALLBACK, and `po_history` - the poisoned August Excel - pairs nothing.
* **R2** when several lines of the order fit, the line the CITED document names wins, and a
  cancelled ghost line loses to any real line that fits.
* **R3** a row that restates another on SO + item + qty + delivery date + location is a
  restatement whatever its remark says, and it lends its citation to the row it restates.

Fixture vocabulary, as the UAC spells it: a "ref" is `sales_order_lines.source_ref`
(`AED_SORENTO:41576559:41604391`); a PO line or SPO allocation "names" a line when its
`from_so_line_ref` equals that ref.

Postgres only (`tests/_pg_fixture.py`, `blank_session` through the parent file's `world()`).
Every chain is seeded here - company, uom, category, product, warehouse, supplier, sales
order + lines, purchase orders + lines, allocations, claims - because CI's database is
empty and nothing may be read off an existing row. The seed helpers are IMPORTED from
`tests/test_project_order_inquiry_import_migration.py` rather than copied, so the two files
cannot drift about what a seeded world is.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.models.order import SalesOrderLine
from app.models.procurement import PurchaseOrderLine
from app.models.project_so import (
    OrderInquiry,
    OrderInquiryLink,
    OrderInquiryRow,
)
from app.models.scm import OrderLinkClaim
from app.services import project_order_inquiry_import_service as importer
from app.services.import_outcome import ImportOutcome
from app.services.project_so_adoption_service import ProjectSOAdoptionService

from .test_project_order_inquiry_import_migration import (  # the seeded world, not copied
    D_NOV,
    D_OCT,
    World,
    _n,
    _uid,
    book,
    sheet,
    world,
)

#: The shape AutoCount writes into `sales_order_lines.source_ref`:
#: `AED_SORENTO:<document key>:<line key>`. The exact string from the 14 Sep prod
#: measurement is `AED_SORENTO:41576559:41604391`; these are minted in the same family so
#: nothing in the importer can special-case a test-looking value.
def _ref() -> str:
    return f"AED_SORENTO:{41576559 + _n()}:{41604391 + _n()}"


def _with_ref(w: World, line: SalesOrderLine, ref: str) -> SalesOrderLine:
    """The ref AutoCount stamped on this sales order line.

    `World.line` does not take one (the parent slice never read the column), so it is set
    here rather than by widening a helper 44 other tests depend on.
    """
    line.source_ref = ref
    w.db.flush()
    return line


def _names(w: World, target, ref: str):
    """This purchase-order line / allocation states it is for that sales order line."""
    target.from_so_line_ref = ref
    w.db.flush()
    return target


def _born_at(w: World, line: SalesOrderLine, when: datetime) -> SalesOrderLine:
    """`created_at` written explicitly, because it is the LAST tiebreak in the line pick.

    `server_default=func.now()` gives every line seeded in one transaction the SAME
    timestamp (Postgres freezes `now()` per transaction), and `sorted` is stable, so a test
    that relies on "the older line" without saying which is older would be measuring the
    order the SELECT happened to return.
    """
    line.created_at = when
    w.db.flush()
    return line


def _apply(w: World, data: bytes, *, file_name: str | None = None, outcome=None) -> dict:
    """`importer.apply` with the uploader the world seeded, and the file's own name.

    `World.apply` cannot pass `file_name`, and the rollback (AC-R-13 to AC-R-16) is keyed
    on the stamp that name leaves on every raised row.
    """
    return importer.apply(
        w.db, data, actor=w.actor, outcome=outcome, file_name=file_name
    )


def _link_row(
    w: World,
    *,
    po_line: PurchaseOrderLine,
    document: str,
    qty: str,
) -> OrderInquiryLink:
    """An EXISTING link from somebody else's row, occupying that PO line's capacity.

    Seeded through a second sales order and the board's own writer, so the occupied
    capacity is the same fact `_claimed_capacity` reads for any other link.
    """
    other = w.order()
    other_line = w.line(other, qty_ordered="50")
    ProjectSOAdoptionService(w.db).adopt(str(other.id), w.actor)
    held = w.board_row(w.mirror_of(other_line), qty=qty)
    link = OrderInquiryLink(
        id=_uid(),
        company_id=w.company_id,
        row_id=held.id,
        po_line_id=po_line.id,
        document=document,
        qty=Decimal(qty),
        linked_by=w.actor,
        linked_at=datetime(2026, 6, 3, 9, 0, 0),
        auto=False,
    )
    w.db.add(link)
    w.db.flush()
    return link


def _documents(links) -> list:
    return [link.document for link in links]


# --------------------------------------------------------------------------- #
# R1: the pairing is the ref AutoCount already wrote                           #
# --------------------------------------------------------------------------- #


def test_ac_r_1_po_line_ref_pairs_without_any_claim():
    """AC-R-1. A purchase order line that NAMES the sales order line pairs the row, with no
    `order_link_claim` row anywhere.

    This is the whole repair. On the 3am 14 Sep prod copy, 32,674 PO lines name a held sales
    order line and only 4,277 of them carry a claim saying so - the claim table is one row
    per `(so_number, po_number, item_code)` and never repoints, so the August `po_history`
    Excel had already taken the key for 28,397 of them. The column is exact, persisted, and
    is what the owner's own query reads.
    """
    with world() as w:
        ref = _ref()
        order = w.order()
        _with_ref(w, w.line(order, qty_ordered="50"), ref)
        po, po_line = w.po_line(qty_ordered="50")
        _names(w, po_line, ref)
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data)

        assert w.db.query(OrderLinkClaim).filter(
            OrderLinkClaim.source != "order_inquiry"
        ).count() == 0, "this criterion is about a pairing NO claim states"
        assert result["rows_raised"] == 1, result
        row = w.one_row()
        links = w.links(row)
        assert len(links) == 1, _documents(links)
        assert str(links[0].po_line_id) == str(po_line.id)
        assert links[0].document == po.po_number
        assert Decimal(str(links[0].qty)) == Decimal("30")
        assert links[0].auto is True, "a pairing the book states is not a person's click"
        assert f"auto: {importer._AUTOCOUNT_TRIGGER}" in (row.note or ""), row.note
        assert result["links_written"] == 1
        assert result["links_from_autocount"] == 1


def test_ac_r_2_ref_po_chains_to_spo_first():
    """AC-R-2. Reached through the ref, D10 still holds: the shipping order the purchase
    order became takes the quantity first, and the PO line takes only the remainder.

    87 is the owner's own case (SO347594 / CB2154-DIY): the allocation covers 30 of it and
    the purchase order line answers for the other 57.
    """
    with world() as w:
        ref = _ref()
        order = w.order()
        _with_ref(w, w.line(order, qty_ordered="100"), ref)
        po, po_line = w.po_line(qty_ordered="87")
        _names(w, po_line, ref)
        allocation = w.spo_allocation(quantity=30, from_po_number=po.po_number)
        data = sheet([
            (order.so_number, w.product.product_code, 87, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data)

        links = w.links(w.one_row())
        assert [str(link.spo_allocation_id or "") for link in links] == [
            str(allocation.id), "",
        ], _documents(links)
        assert [Decimal(str(link.qty)) for link in links] == [
            Decimal("30"), Decimal("57"),
        ]
        assert str(links[1].po_line_id) == str(po_line.id)
        assert result["links_from_autocount"] == 1


def test_ac_r_3_spo_direct_ref_before_po_ref():
    """AC-R-3. An allocation that names the line directly is taken before a purchase order
    line that also names it - "SPO first then PO" (R5 of `PLAN-scm-oi-draft-links.md`),
    unchanged, now reached through the ref rather than through a claim."""
    with world() as w:
        ref = _ref()
        order = w.order()
        _with_ref(w, w.line(order, qty_ordered="50"), ref)
        _po, po_line = w.po_line(qty_ordered="50")
        _names(w, po_line, ref)
        allocation = _names(w, w.spo_allocation(quantity=50), ref)
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        _apply(w, data)

        links = w.links(w.one_row())
        assert len(links) == 1, _documents(links)
        assert str(links[0].spo_allocation_id) == str(allocation.id)
        assert links[0].po_line_id is None


def test_ac_r_4_po_history_claim_alone_links_nothing():
    """AC-R-4. A `po_history` claim is not the book: it pairs NOTHING.

    Those 33,235 rows are one August Excel extract, and they hold the claim key for 28,397
    pairings AutoCount states exactly on the purchase side. The row is still raised - it is
    the instruction the sheet carries - and the sheet's own citation is still tried, so
    removing this source loses no pairing the operator asked for.
    """
    with world() as w:
        order = w.order()
        line = _with_ref(w, w.line(order, qty_ordered="50"), _ref())
        po, po_line = w.po_line(qty_ordered="50")
        w.claim(
            order=order, core_line=line, document=po.po_number,
            po_line=po_line, source="po_history",
        )
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data)

        assert result["rows_raised"] == 1, result
        assert w.links(w.one_row()) == [], "the August extract paired the row anyway"
        assert result["links_written"] == 0
        assert result["links_from_autocount"] == 0

    with world() as w:
        order = w.order()
        line = _with_ref(w, w.line(order, qty_ordered="50"), _ref())
        history, history_line = w.po_line(qty_ordered="50")
        w.claim(
            order=order, core_line=line, document=history.po_number,
            po_line=history_line, source="po_history",
        )
        cited, cited_line = w.po_line(qty_ordered="50")
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, cited.po_number),
        ])

        result = _apply(w, data)

        links = w.links(w.one_row())
        assert len(links) == 1, _documents(links)
        assert str(links[0].po_line_id) == str(cited_line.id), (
            "source 3 must still run once the August claim stops answering"
        )
        assert links[0].auto is False, "the sheet's remark is a person, not the book"
        assert result["links_from_autocount"] == 0


def test_ac_r_5_autocount_claim_without_ref_still_links():
    """AC-R-5. Source 2 survives. Where AutoCount stated only the document NUMBER, the
    ingest's resolved `autocount` claim is all there is, and it still pairs the row.

    Green before the repair as well as after: it is the half of D9 the repair must not take
    away while it demotes the claim table.
    """
    with world() as w:
        order = w.order()
        line = _with_ref(w, w.line(order, qty_ordered="50"), _ref())
        po, po_line = w.po_line(qty_ordered="50")
        assert po_line.from_so_line_ref is None, "the purchase side states no line here"
        w.claim(order=order, core_line=line, document=po.po_number, po_line=po_line)
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data)

        links = w.links(w.one_row())
        assert len(links) == 1, _documents(links)
        assert str(links[0].po_line_id) == str(po_line.id)
        assert Decimal(str(links[0].qty)) == Decimal("30")
        assert result["links_from_autocount"] == 1


def test_ac_r_6_ref_beats_claim_to_other_document():
    """AC-R-6. The ref outranks a claim that names a different document.

    Both have room for the whole need, so the only thing being measured is which source is
    asked first - and the claim key is exactly what the August extract poisoned.
    """
    with world() as w:
        ref = _ref()
        order = w.order()
        line = _with_ref(w, w.line(order, qty_ordered="50"), ref)
        named_po, named_line = w.po_line(qty_ordered="50")
        _names(w, named_line, ref)
        claimed_po, claimed_line = w.po_line(qty_ordered="50")
        w.claim(
            order=order, core_line=line, document=claimed_po.po_number,
            po_line=claimed_line,
        )
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        _apply(w, data)

        links = w.links(w.one_row())
        assert len(links) == 1, _documents(links)
        assert str(links[0].po_line_id) == str(named_line.id)
        assert links[0].document == named_po.po_number
        assert all(
            str(link.po_line_id) != str(claimed_line.id) for link in links
        ), "the claim's document took quantity the ref had already answered for"


def test_ac_r_7_named_line_with_no_capacity_is_skipped():
    """AC-R-7. The capacity rule is unchanged by the new source: a named line that existing
    links have already filled is SKIPPED, and the need falls through to the sheet's citation.

    Green before the repair too - source 1 does not exist yet, so nothing tries the named
    line at all. It is here so the repair cannot make the ref a special case that overruns a
    line other rows already hold.
    """
    with world() as w:
        ref = _ref()
        order = w.order()
        _with_ref(w, w.line(order, qty_ordered="50"), ref)
        full_po, full_line = w.po_line(qty_ordered="20")
        _names(w, full_line, ref)
        _link_row(w, po_line=full_line, document=full_po.po_number, qty="20")
        cited, cited_line = w.po_line(qty_ordered="50")
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, cited.po_number),
        ])

        result = _apply(w, data)

        raised = [row for row in w.rows() if row.cited_document == cited.po_number]
        assert len(raised) == 1, [row.item_code for row in raised]
        links = w.links(raised[0])
        assert len(links) == 1, _documents(links)
        assert str(links[0].po_line_id) == str(cited_line.id)
        assert Decimal(str(links[0].qty)) == Decimal("30")
        assert all(
            str(link.po_line_id) != str(full_line.id) for link in links
        ), "a line with no capacity was linked anyway"
        assert result["links_partial"] == 0


# --------------------------------------------------------------------------- #
# R2: which of the order's lines the row means                                 #
# --------------------------------------------------------------------------- #


def test_ac_r_8_cited_po_ref_picks_the_named_line():
    """AC-R-8. Two lines of the same item both fit; the cited purchase order names the
    second; the row is raised against the SECOND.

    This is prod row 113 of tab "JAN 26". The shipped ranking reads the required date and
    nothing else, so the row landed on a 90-qty line the cited PO says nothing about. The
    sheet's own delivery date is deliberately the FIRST line's, so only the citation can
    move the row.
    """
    with world() as w:
        order = w.order()
        first = w.line(order, qty_ordered="50", required_date=D_OCT)
        second = _with_ref(
            w, w.line(order, qty_ordered="50", required_date=D_NOV), _ref()
        )
        cited, cited_line = w.po_line(qty_ordered="50")
        _names(w, cited_line, second.source_ref)
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, cited.po_number),
        ])

        result = _apply(w, data)

        assert result["rows_raised"] == 1, result
        row = w.one_row()
        mirror = w.mirror_of(second)
        assert mirror is not None, "the line the citation names was never mirrored"
        assert str(row.so_line_id) == str(mirror.id), (
            "the row landed on the line the cited purchase order says nothing about"
        )
        assert w.mirror_of(first) is None or str(row.so_line_id) != str(
            w.mirror_of(first).id
        )
        links = w.links(row)
        assert len(links) == 1, _documents(links)
        assert str(links[0].po_line_id) == str(cited_line.id)


def test_ac_r_9_cited_spo_chain_picks_the_named_line():
    """AC-R-9. The same pick, with the chain read BACKWARDS: the sheet cites a shipping
    order, whose allocation carries `from_po_number`, whose purchase order line names the
    second sales order line.

    `SPO-2026/01-0140 <- 202511-S0097 <- AED_SORENTO:41576559:41604391` is the owner's own
    chain, stated in that direction by the two feeds.
    """
    with world() as w:
        order = w.order()
        first = w.line(order, qty_ordered="50", required_date=D_OCT)
        second = _with_ref(
            w, w.line(order, qty_ordered="50", required_date=D_NOV), _ref()
        )
        source_po, source_line = w.po_line(qty_ordered="50")
        _names(w, source_line, second.source_ref)
        allocation = w.spo_allocation(quantity=50, from_po_number=source_po.po_number)
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, allocation.spo_number),
        ])

        result = _apply(w, data)

        assert result["rows_raised"] == 1, result
        row = w.one_row()
        assert str(row.so_line_id) == str(w.mirror_of(second).id), (
            "the shipping order's own purchase order names the second line"
        )
        assert w.mirror_of(first) is None or str(row.so_line_id) != str(
            w.mirror_of(first).id
        )
        links = w.links(row)
        assert _documents(links) == [allocation.spo_number], _documents(links)


def test_ac_r_10_cancelled_ghost_loses_to_real_line():
    """AC-R-10. A cancelled August-extract ghost line loses to any real line that fits - and
    still matches when it is the only one that does (D1 kept).

    This is prod row 772 of tab "JAN - APR 26". 10,499 cancelled Aug-extract lines are still
    in the book with a `source_ref` like `'40'` rather than an `AED_SORENTO:` one, and 13,222
    claims point at them; the row landed on the ghost because it was the older row and
    nothing else told the two apart. `created_at` is stated explicitly here so the ghost IS
    the older one and the new rule is what moves the row, not a tie.
    """
    with world() as w:
        order = w.order()
        ghost = _born_at(
            w,
            _with_ref(
                w,
                w.line(order, qty_ordered="50", required_date=D_OCT,
                       line_status="cancelled"),
                "40",
            ),
            datetime(2026, 1, 5, 9, 0, 0),
        )
        real = _born_at(
            w,
            _with_ref(
                w,
                w.line(order, qty_ordered="50", required_date=D_OCT,
                       line_status="closed", qty_delivered="50"),
                _ref(),
            ),
            datetime(2026, 6, 5, 9, 0, 0),
        )
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data)

        assert result["rows_raised"] == 1, result
        mirror = w.mirror_of(real)
        assert mirror is not None, (
            "the real line was never even mirrored: the row landed on the cancelled "
            "Aug-extract ghost"
        )
        assert str(w.one_row().so_line_id) == str(mirror.id), (
            "the row landed on the cancelled Aug-extract ghost"
        )
        ghost_mirror = w.mirror_of(ghost)
        assert ghost_mirror is None or str(w.one_row().so_line_id) != str(ghost_mirror.id)

    with world() as w:
        order = w.order()
        lonely = _with_ref(
            w,
            w.line(order, qty_ordered="50", required_date=D_OCT, line_status="cancelled"),
            "41",
        )
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data)

        assert result["rows_raised"] == 1, result
        assert result["rows_line_not_found"] == 0, result
        assert str(w.one_row().so_line_id) == str(w.mirror_of(lonely).id), (
            "a lone cancelled line still matches - it is where the history is"
        )


# --------------------------------------------------------------------------- #
# R3: a restatement, whatever the remark says                                  #
# --------------------------------------------------------------------------- #


def test_ac_r_11_differing_remark_is_a_restatement():
    """AC-R-11. The restatement key is SO + item + qty + delivery date + location. The
    remark leaves it.

    The owner: "what we need from the order inquiries tab is just the sales order, location,
    quantity, delivery date, product ... the remark doesn't really matter, differing remark
    is same also as long as other keys are the same". A roll-up tab that carries the PO
    number the month tab left blank is the same instruction written twice, and raising it
    twice takes the line's quantity twice - which is how the third row here, for the
    quantity genuinely left, fails.

    Replaces the parent's AC-S1-38 reading of the remark.
    """
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="50")
        cited, _cited_line = w.po_line(qty_ordered="50")
        stated = (order.so_number, w.product.product_code, 30, D_OCT,
                  w.warehouse.warehouse_code, cited.po_number)
        restated = (order.so_number, w.product.product_code, 30, D_OCT,
                    w.warehouse.warehouse_code, "")
        remainder = (order.so_number, w.product.product_code, 20, D_OCT,
                     w.warehouse.warehouse_code, "")
        outcome = ImportOutcome(None, persist=False)

        result = _apply(
            w,
            book(JAN26=[stated, remainder], ROLLUP=[restated]),
            outcome=outcome,
        )

        assert result["rows"] == 3, "the file's own row count keeps all three"
        assert outcome.count_of("restates_an_instalment") == 1, outcome.breakdown()
        assert result["rows_raised"] == 2, result
        assert len(w.rows()) == 2, [str(row.qty) for row in w.rows()]
        assert sorted(Decimal(str(row.qty)) for row in w.rows()) == [
            Decimal("20"), Decimal("30"),
        ]
        assert result["rows_line_not_found"] == 0, (
            "the restatement charged the line's quantity twice"
        )


def test_ac_r_12_restatement_lends_its_citation():
    """AC-R-12. The FIRST row states the delivery with a blank remark and the SECOND names
    the purchase order: the one raised row is linked to it.

    Which tab carries the remark is an accident of how the customer keeps the book, so the
    citation is merged onto the match that was kept rather than discarded with the row that
    restated it. The sales order line here holds both quantities, so the shipped behaviour
    raises two rows rather than failing on capacity - what is measured is the count and the
    link, not a refusal.
    """
    with world() as w:
        order = w.order()
        _with_ref(w, w.line(order, qty_ordered="100"), _ref())
        cited, cited_line = w.po_line(qty_ordered="50")
        blank = (order.so_number, w.product.product_code, 30, D_OCT,
                 w.warehouse.warehouse_code, "")
        naming = (order.so_number, w.product.product_code, 30, D_OCT,
                  w.warehouse.warehouse_code, cited.po_number)

        result = _apply(w, book(JAN26=[blank], ROLLUP=[naming]))

        assert result["rows_raised"] == 1, result
        row = w.one_row()
        links = w.links(row)
        assert len(links) == 1, _documents(links)
        assert str(links[0].po_line_id) == str(cited_line.id)
        assert Decimal(str(links[0].qty)) == Decimal("30")
        assert row.cited_document == cited.po_number, (
            "the restatement's citation never reached the row it restates"
        )


# --------------------------------------------------------------------------- #
# S2: taking a wrong upload back out                                           #
# --------------------------------------------------------------------------- #
#
# `scripts/rollback_oi_sheet_upload.py` is a CLI
# (`--file-name "<name as stamped>" [--apply]`, dry-run by default), but the behaviour is
# tested at the function the CLI wraps:
#
#     run(db, file_name: str, apply: bool) -> dict
#
# with the four counts `{"rows", "links", "claims", "inquiries"}`. The CALLER owns the
# transaction, exactly as `scripts/delete_empty_order_inquiries.py::run` does - `run` must
# neither commit nor roll back, or a dry run would discard the caller's own session (and,
# here, the seeded world these tests are holding).


def _rollback():
    """The script under test, imported inside the test so its absence reds only S2."""
    import scripts.rollback_oi_sheet_upload as rollback

    return rollback


def _uploaded(w: World, *, file_name: str, qty: int = 30, product=None):
    """One sales order, one line, one cited purchase order - raised under `file_name`."""
    order = w.order()
    product = product or w.product
    w.line(order, product=product, qty_ordered="50")
    po, po_line = w.po_line(qty_ordered="50", product=product)
    result = _apply(
        w,
        sheet([
            (order.so_number, product.product_code, qty, D_OCT,
             w.warehouse.warehouse_code, po.po_number),
        ]),
        file_name=file_name,
    )
    assert result["rows_raised"] == 1, result
    assert result["links_written"] == 1, result
    return order, po_line


def _rows_of(w: World, file_name: str) -> list:
    stamp = f"{importer._MIGRATION_STAMP} {file_name}"
    return [row for row in w.db.query(OrderInquiryRow).all()
            if (row.note or "").startswith(stamp)]


def test_ac_r_13_rollback_deletes_only_the_named_file():
    """AC-R-13. The rollback takes out the named upload's rows, their links and the
    `order_inquiry` claims those links wrote - and nothing of any other upload.

    This is what the owner runs on prod before re-uploading the 14 Sep file. A rollback that
    cannot be trusted to stop at one file name is a rollback nobody will run.
    """
    with world() as w:
        _order_a, _line_a = _uploaded(w, file_name="a.xlsx")
        _order_b, _line_b = _uploaded(w, file_name="b.xlsx", product=w.product_row())

        rows_a = _rows_of(w, "a.xlsx")
        rows_b = _rows_of(w, "b.xlsx")
        assert len(rows_a) == 1 and len(rows_b) == 1
        links_a = w.links(rows_a[0])
        links_b = w.links(rows_b[0])
        claim_ids_a = [str(link.claim_id) for link in links_a if link.claim_id]
        claim_ids_b = [str(link.claim_id) for link in links_b if link.claim_id]
        assert claim_ids_a, "the seeded upload wrote no claim to delete"
        assert claim_ids_b
        row_a_id, row_b_id = str(rows_a[0].id), str(rows_b[0].id)
        link_a_ids = [str(link.id) for link in links_a]

        counts = _rollback().run(w.db, file_name="a.xlsx", apply=True)

        assert set(counts) == {"rows", "links", "claims", "inquiries"}, counts
        assert counts["rows"] == 1, counts
        assert counts["links"] == len(link_a_ids), counts
        assert counts["claims"] == len(claim_ids_a), counts
        assert w.db.query(OrderInquiryRow).filter(
            OrderInquiryRow.id == row_a_id
        ).count() == 0
        assert w.db.query(OrderInquiryLink).filter(
            OrderInquiryLink.id.in_(link_a_ids)
        ).count() == 0
        assert w.db.query(OrderLinkClaim).filter(
            OrderLinkClaim.id.in_(claim_ids_a)
        ).count() == 0
        assert w.db.query(OrderInquiryRow).filter(
            OrderInquiryRow.id == row_b_id
        ).count() == 1, "the other file's row went with it"
        assert len(w.links(rows_b[0])) == len(links_b)
        assert w.db.query(OrderLinkClaim).filter(
            OrderLinkClaim.id.in_(claim_ids_b)
        ).count() == len(claim_ids_b)


def test_ac_r_14_rollback_dry_run_deletes_nothing():
    """AC-R-14. Without `--apply` nothing is deleted, and the counts printed are the counts
    the real run would produce - which is the only reason to look at a dry run at all."""
    with world() as w:
        _uploaded(w, file_name="a.xlsx")
        _uploaded(w, file_name="b.xlsx", product=w.product_row())
        rows_a = _rows_of(w, "a.xlsx")
        row_a_id = str(rows_a[0].id)
        link_a_ids = [str(link.id) for link in w.links(rows_a[0])]

        dry = _rollback().run(w.db, file_name="a.xlsx", apply=False)

        assert w.db.query(OrderInquiryRow).filter(
            OrderInquiryRow.id == row_a_id
        ).count() == 1, "a dry run deleted the row"
        assert w.db.query(OrderInquiryLink).filter(
            OrderInquiryLink.id.in_(link_a_ids)
        ).count() == len(link_a_ids)
        assert len(_rows_of(w, "b.xlsx")) == 1, (
            "the dry run rolled the caller's transaction back"
        )

        applied = _rollback().run(w.db, file_name="a.xlsx", apply=True)

        assert dry == applied, (dry, applied)


def test_ac_r_15_rollback_drops_empty_headers_only():
    """AC-R-15. An inquiry header the rollback empties is deleted; one that still carries
    another file's rows stays.

    A header with nothing on it burns an OI number and leaves a dangling "Order inquiries"
    link on the sales order list - the exact defect
    `scripts/delete_empty_order_inquiries.py` exists to clean up after.
    """
    with world() as w:
        alone, _line = _uploaded(w, file_name="a.xlsx")
        # One sales order, two lines, two files: its header survives the rollback because
        # b.xlsx's row is still on it.
        mixed = w.order()
        other_product = w.product_row()
        w.line(mixed, qty_ordered="50")
        w.line(mixed, product=other_product, qty_ordered="50")
        _apply(w, sheet([
            (mixed.so_number, w.product.product_code, 10, D_OCT,
             w.warehouse.warehouse_code, ""),
        ]), file_name="a.xlsx")
        _apply(w, sheet([
            (mixed.so_number, other_product.product_code, 10, D_OCT,
             w.warehouse.warehouse_code, ""),
        ]), file_name="b.xlsx")

        headers = {
            str(row.order_inquiry_id)
            for row in _rows_of(w, "a.xlsx") + _rows_of(w, "b.xlsx")
        }
        assert len(headers) == 2, headers
        emptied = {str(row.order_inquiry_id) for row in _rows_of(w, "a.xlsx")} - {
            str(row.order_inquiry_id) for row in _rows_of(w, "b.xlsx")
        }
        kept = {str(row.order_inquiry_id) for row in _rows_of(w, "b.xlsx")}
        assert len(emptied) == 1 and len(kept) == 1, (emptied, kept)

        counts = _rollback().run(w.db, file_name="a.xlsx", apply=True)

        assert counts["rows"] == 2, counts
        assert counts["inquiries"] == 1, counts
        assert w.db.query(OrderInquiry).filter(
            OrderInquiry.id.in_(list(emptied))
        ).count() == 0, "the header the rollback emptied was left behind"
        assert w.db.query(OrderInquiry).filter(
            OrderInquiry.id.in_(list(kept))
        ).count() == 1, "a header still holding another file's rows was deleted"
        assert alone is not None


def test_ac_r_16_rows_raise_again_after_rollback():
    """AC-R-16. After the rollback the same sheet raises the same rows again: D2's
    "this line already carries a row, leave it alone" no longer stands in the way.

    Rolling back and re-uploading is the whole point of the script (owner step 1 and 2 after
    deploy), so a rollback that leaves the second upload with nothing to do would be worse
    than none at all.
    """
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="50")
        po, _po_line = w.po_line(qty_ordered="50")
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, po.po_number),
        ])

        first = _apply(w, data, file_name="a.xlsx")
        assert first["rows_raised"] == 1, first

        _rollback().run(w.db, file_name="a.xlsx", apply=True)
        again = _apply(w, data, file_name="a.xlsx")

        assert again["rows_raised"] == first["rows_raised"], again
        assert again["rows_already_raised"] == 0, again
        assert len(_rows_of(w, "a.xlsx")) == 1
        assert again["links_written"] == 1, again
