"""OI-PO-LINK owner ruling C (13 Nov): an AutoCount claim whose PO line was FREED stays unlinked.

db3 case: an `scm.order_link_claim` (source 'autocount') names SO + PO A + item and points at PO A's
line, but that line's `from_so_line_ref` is now NULL because the user unlinked it in AutoCount. The
follow-the-book pass (`pair_needs` Source 2) must not re-link the leftover unit to it. Controls: a
'po_upload' claim on a null-ref line still places, and an 'autocount' claim whose line still carries
the row's SO ref still places. Seeding is `test_oi_follow_book_chain.py`'s own.
"""
from __future__ import annotations

from decimal import Decimal

from app.models.scm import OrderLinkClaim
from app.services.scm import po_link_history
from app.services.project_order_inquiry_service import ProjectOrderInquiryService

from .test_oi_follow_book_chain import (  # noqa: F401  (ctx is a fixture)
    _links_of,
    _ref,
    _seed_po_line,
    _seed_product,
    _seed_row_and_mirror,
    _seed_so_line,
    ctx,
)


def _case(ctx, *, source, line_keeps_so_ref, freed_event=False, tied_elsewhere=False):
    db = ctx.db
    product = _seed_product(db, company_id=ctx.company_a)
    ref = _ref("SOL")
    so, core_line = _seed_so_line(db, company_id=ctx.company_a, product_id=product.id, source_ref=ref, qty="5")
    # PO B is tied to the line in the book: that is what makes the follow-the-book pass look at
    # this line at all, and it covers 4 of the 5, leaving the 1 unit the claim would be asked for.
    _po_b, _line_b = _seed_po_line(
        db, company_id=ctx.company_a, product_id=product.id, from_so_line_ref=ref, qty_ordered="4"
    )
    po, po_line = _seed_po_line(
        db, company_id=ctx.company_a, product_id=product.id,
        from_so_line_ref=ref if line_keeps_so_ref else (f"{ref}:other" if tied_elsewhere else None),
        qty_ordered="4",
    )
    if freed_event:
        # AutoCount tied this line to the row's SO line and then cleared it: the EVENT ingest logs.
        po_link_history.record_changes(db, [(po_line, ref, None)], purchase_order_id=po.id)
        db.flush()
    db.add(OrderLinkClaim(
        company_id=ctx.company_a, so_number=so.so_number, po_number=po.po_number,
        item_code=product.product_code, source=source, so_line_id=core_line.id, po_line_id=po_line.id,
    ))
    _pso, _mirror, _inquiry, row = _seed_row_and_mirror(
        db, company_id=ctx.company_a, core_line=core_line, product_id=product.id, qty="5"
    )
    db.commit()
    ProjectOrderInquiryService(db).follow_book_for_rows(
        [str(row.id)], trigger="autocount_ingest", company_id=ctx.company_a, actor_user_id=None
    )
    return po_line, _links_of(db, row.id), _line_b


def test_an_autocount_claim_on_a_freed_po_line_places_nothing(ctx):
    """Freed = tied to this row's SO ref, then cleared by AutoCount (the audit EVENT proves it)."""
    po_line, links, line_b = _case(ctx, source="autocount", line_keeps_so_ref=False, freed_event=True)
    assert [l.po_line_id for l in links] == [line_b.id]  # PO B's 4 units; nothing on the freed line


def test_control_a_po_upload_claim_on_a_null_ref_line_still_places(ctx):
    po_line, links, line_b = _case(ctx, source="po_upload", line_keeps_so_ref=False)
    assert {l.po_line_id: Decimal(str(l.qty)) for l in links}.get(po_line.id) == Decimal("1")


def test_control_an_autocount_claim_whose_line_still_carries_the_so_ref_still_places(ctx):
    po_line, links, line_b = _case(ctx, source="autocount", line_keeps_so_ref=True)
    assert po_line.id in {l.po_line_id for l in links}


def test_an_autocount_claim_on_a_line_whose_ref_was_never_known_still_places(ctx):
    """An older push carried no ref; the claim pins the pair by SO number only. No freed EVENT exists."""
    po_line, links, _line_b = _case(ctx, source="autocount", line_keeps_so_ref=False, freed_event=False)
    assert {l.po_line_id: Decimal(str(l.qty)) for l in links}.get(po_line.id) == Decimal("1")


def test_an_autocount_claim_on_a_line_now_tied_to_another_so_line_is_skipped(ctx):
    po_line, links, line_b = _case(ctx, source="autocount", line_keeps_so_ref=False, tied_elsewhere=True)
    assert po_line.id not in {l.po_line_id for l in links}
