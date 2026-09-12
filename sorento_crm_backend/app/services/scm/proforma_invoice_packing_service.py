"""Supplier packing rows on the invoice (S2, `scm-supplier-documents-pi-first-acceptance-
criteria.md` section B).

A packing list and its proforma invoice count differently - Kailu's 11 priced lines become
12 packing rows because SRTSC14-GM ships in two cartons of different sizes, and Jiexia's lid
row prices nothing and is a packing row with no invoice line at all. So the rows are their
own table (`ProformaInvoicePackingLine`, AC-B1), matched onto a line by resolved PRODUCT
(AC-B6) rather than merged with it, and rolled up onto the line's own carton/weight/volume
figures afterwards (AC-B8) so the Lines tab keeps reading one number per field regardless of
how many packing rows fed it.

`replace_packing_rows` is the one write this module offers to `supplier_document_service`:
delete whatever rows this PI already held, write the file's rows fresh, match, roll up. A
re-upload is a CORRECTION (AC-B5) - it never appends.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.scm import (
    ProformaInvoice,
    ProformaInvoiceLine,
    ProformaInvoicePackingLine,
    SupplierProductCodeAlias,
)
from app.services.error_handler import AppException
from app.services.scm import supplier_code_alias_service
from app.services.scm.packing_list_reader import PackingBlock, PackingLine

_DISMISSED = "dismissed"


def _uuid() -> str:
    return str(uuid.uuid4())


def _dismissed_codes(db: Session, supplier_id: str, codes: set[str]) -> set[str]:
    """Every code, upper-cased, this supplier has an active DISMISSAL for (AC-B6) - a
    ruling made once, from a Dismiss anywhere in this channel, never asked about again."""
    if not codes:
        return set()
    rows = (
        db.query(func.upper(SupplierProductCodeAlias.supplier_code))
        .filter(
            SupplierProductCodeAlias.supplier_id == str(supplier_id),
            SupplierProductCodeAlias.source == _DISMISSED,
            func.upper(SupplierProductCodeAlias.supplier_code).in_({c.upper() for c in codes}),
        )
        .all()
    )
    return {r[0] for r in rows}


def replace_packing_rows(
    db: Session,
    invoice: ProformaInvoice,
    lines: list[PackingLine],
    *,
    supplier_id: str,
    actor: Optional[str] = None,
) -> int:
    """Delete this PI's existing packing rows, write `lines` fresh, match, roll up.

    `lines` is already the flattened `PackingLine` list off however many blocks the file's
    read produced - the caller decides which blocks belong to THIS invoice (AC-B5); this
    function only ever writes onto the one PI it is handed.
    """
    from app.services.scm.proforma_invoice_service import _products_by_code, _with_supplier_codes

    codes = {ln.item_code for ln in lines}
    known = _products_by_code(db, codes)
    known = _with_supplier_codes(db, known, supplier_id=supplier_id, codes=codes, actor=actor)
    dismissed = _dismissed_codes(db, supplier_id, codes)

    inv_lines = (
        db.query(ProformaInvoiceLine)
        .filter(ProformaInvoiceLine.invoice_id == invoice.id)
        .all()
    )
    line_by_product = {str(l.product_id): l for l in inv_lines if l.product_id}
    line_by_set = {str(l.product_set_id): l for l in inv_lines if l.product_set_id}

    # A re-upload is a CORRECTION, never an append (AC-B5) - the whole set is replaced.
    db.query(ProformaInvoicePackingLine).filter(
        ProformaInvoicePackingLine.proforma_invoice_id == invoice.id
    ).delete(synchronize_session=False)
    db.flush()

    new_rows: list[ProformaInvoicePackingLine] = []
    for row_no, ln in enumerate(lines, start=1):
        code_upper = ln.item_code.upper()
        product = known.get(code_upper)
        row = ProformaInvoicePackingLine(
            id=_uuid(),
            proforma_invoice_id=invoice.id,
            row_no=row_no,
            item_code=ln.item_code,
            supplier_code=ln.supplier_code,
            description=ln.product_name,
            qty=ln.qty,
            cartons=ln.cartons,
            pcs_per_carton=ln.pcs_per_carton,
            carton_length_cm=ln.carton_length_cm,
            carton_width_cm=ln.carton_width_cm,
            carton_height_cm=ln.carton_height_cm,
            cbm_per_carton=ln.cbm_per_carton,
            cbm_total=ln.cbm_total,
            # PER CARTON (the class docstring's own trap) - never `ln.net_weight`/
            # `ln.gross_weight`, which are the OTHER shape's (Jiexia) per-LINE figure.
            net_weight=ln.carton_net_weight,
            gross_weight=ln.carton_gross_weight,
            total_net_weight=ln.total_net_weight,
            total_gross_weight=ln.total_gross_weight,
            material=ln.material,
            container_no=ln.container_no,
            remark=ln.remark,
        )
        # Product/line resolution happens REGARDLESS of dismissal (S4, AC-D3): a
        # dismissed row still names a real line when its code resolves to one - convert
        # needs `proforma_invoice_line_id` set so it can tell "this line's only row is
        # dismissed" apart from "this line has no packing list at all" - the dismissal
        # itself is applied on top, as the row's own `match_state`, and `rollup_invoice`
        # then leaves every dismissed row out of the figures it sums.
        if product:
            row.product_id = product.get("id")
            row.product_set_id = product.get("product_set_id")
        matched_line = None
        if product and product.get("id"):
            matched_line = line_by_product.get(str(product["id"]))
        elif product and product.get("product_set_id"):
            matched_line = line_by_set.get(str(product["product_set_id"]))
        if code_upper in dismissed:
            row.match_state = "dismissed"
            if matched_line is not None:
                row.proforma_invoice_line_id = matched_line.id
        elif matched_line is not None:
            row.match_state = "matched"
            row.proforma_invoice_line_id = matched_line.id
        else:
            # A resolved product no line of this PI holds, or no product at all - both
            # read the same to the operator: this row is not on the invoice (AC-B6).
            row.match_state = "unmatched"
        db.add(row)
        new_rows.append(row)

    # S2, text glossary lane (R3/R4): the English cache for `description` on every row
    # this replace just wrote, one batched memory lookup for the whole file.
    from app.services.scm import description_translation

    description_translation.fill(db, new_rows)
    db.flush()

    rollup_invoice(db, str(invoice.id))

    return len(lines)


def rebind_packing_rows(
    db: Session,
    *,
    supplier_id: str,
    code: str,
    product_id: Optional[str],
    product_set_id: Optional[str],
) -> int:
    """Point this supplier's packing rows under `code` at whatever it now means (S2 + R16).

    The third reader `supplier_code_alias_service._rebind` has to reach: a ruling made on
    the Packing tab (Match, Dismiss) or anywhere else in this channel has to land on the
    packing rows already uploaded under that code, or the tab goes on showing "Not in
    catalogue" for a code the operator has just answered.

    The row's LINE and its `match_state` follow from the product, never from the caller:
    a row whose product is on this PI is matched to that line, one whose product no line
    holds is `unmatched` (AC-B6's `not_on_invoice`), and a code carrying an active
    dismissal is `dismissed` whatever it resolves to. Every invoice a row moved on is
    re-rolled afterwards (AC-B8).
    """
    rows = (
        db.query(ProformaInvoicePackingLine)
        .join(
            ProformaInvoice,
            ProformaInvoice.id == ProformaInvoicePackingLine.proforma_invoice_id,
        )
        .filter(
            ProformaInvoice.supplier_id == str(supplier_id),
            ProformaInvoicePackingLine.item_code.ilike(code),
        )
        .all()
    )
    if not rows:
        return 0

    dismissed = bool(_dismissed_codes(db, str(supplier_id), {code}))
    invoice_ids = {str(r.proforma_invoice_id) for r in rows}
    lines_by_invoice: dict[str, list[ProformaInvoiceLine]] = {}
    for line in (
        db.query(ProformaInvoiceLine)
        .filter(ProformaInvoiceLine.invoice_id.in_(invoice_ids))
        .all()
    ):
        lines_by_invoice.setdefault(str(line.invoice_id), []).append(line)

    for row in rows:
        row.product_id = product_id
        row.product_set_id = product_set_id
        matched_line = None
        for line in lines_by_invoice.get(str(row.proforma_invoice_id), []):
            if product_id and str(line.product_id or "") == str(product_id):
                matched_line = line
                break
            if product_set_id and str(line.product_set_id or "") == str(product_set_id):
                matched_line = line
                break
        row.proforma_invoice_line_id = matched_line.id if matched_line is not None else None
        if dismissed:
            row.match_state = _DISMISSED
        else:
            row.match_state = "matched" if matched_line is not None else "unmatched"
    db.flush()

    for invoice_id in invoice_ids:
        rollup_invoice(db, invoice_id)
    return len(rows)


def rollup_invoice(db: Session, invoice_id: str) -> None:
    """Re-roll EVERY line of this PI from its own non-dismissed packing rows (AC-B8).

    Run after ANY packing write - replace, dismiss, undo, match - because all four change
    which rows feed which line, and re-rolling only the lines one write happened to touch
    left the OTHER lines carrying figures from rows that no longer feed them (a dismissed
    row's cartons stayed in its line's total until the next whole re-upload).

    A dismissed row is not a packing row for this purpose: it is the operator saying the
    invoice does not price it. A line left with no rows at all is not touched - it keeps
    whatever the PI document itself stated, which is the only figure anybody has for it.
    """
    rows_by_line: dict[str, list[ProformaInvoicePackingLine]] = {}
    for row in (
        db.query(ProformaInvoicePackingLine)
        .filter(
            ProformaInvoicePackingLine.proforma_invoice_id == str(invoice_id),
            ProformaInvoicePackingLine.match_state != _DISMISSED,
            ProformaInvoicePackingLine.proforma_invoice_line_id.isnot(None),
        )
        .all()
    ):
        rows_by_line.setdefault(str(row.proforma_invoice_line_id), []).append(row)

    for line in (
        db.query(ProformaInvoiceLine)
        .filter(ProformaInvoiceLine.invoice_id == str(invoice_id))
        .all()
    ):
        _rollup_packing(db, line, rows_by_line.get(str(line.id), []))


def _sum_or_none(values) -> Optional[float]:
    """A simple sum - never zero for a line no row measured (AC-B8's own "never zero for an
    unmeasured item" convention, same as every other reader in this channel)."""
    vals = [v for v in values if v is not None]
    return sum(vals) if vals else None


def _shared_or_none(values):
    """The rows' shared value when EVERY one states the SAME one, else `None` - a line built
    from rows that disagree, or that a row left unmeasured, has no one true figure to show."""
    vals = list(values)
    if not vals or any(v is None for v in vals):
        return None
    first = vals[0]
    return first if all(v == first for v in vals) else None


def _rollup_packing(
    db: Session, line: ProformaInvoiceLine, rows: list[ProformaInvoicePackingLine]
) -> None:
    """`cartons`/`cbm_total`/`net_weight`/`gross_weight` = sums over `rows`; `pcs_per_carton`
    and the carton dims = the rows' shared value when all agree, else `NULL` (AC-B8). Runs
    after every packing write and on packing-row dismiss/undo. A line with no packing row is
    never called - it keeps whatever the PI document itself stated."""
    if not rows:
        return
    line.cartons = _sum_or_none(r.cartons for r in rows)
    line.cbm_total = _sum_or_none(r.cbm_total for r in rows)
    line.net_weight = _sum_or_none(r.total_net_weight for r in rows)
    line.gross_weight = _sum_or_none(r.total_gross_weight for r in rows)
    line.pcs_per_carton = _shared_or_none(r.pcs_per_carton for r in rows)
    line.carton_length_cm = _shared_or_none(r.carton_length_cm for r in rows)
    line.carton_width_cm = _shared_or_none(r.carton_width_cm for r in rows)
    line.carton_height_cm = _shared_or_none(r.carton_height_cm for r in rows)


@dataclass
class AttachResolution:
    """Which PI a packing-list block attaches to, and why - one answer, shared by the
    preview (which SHOWS it and its refusal) and by apply (which acts on it). Server truth:
    the dialog never works this out for itself, it only overrides it (`attach_to`)."""

    invoice: Optional[ProformaInvoice] = None
    #: How it was decided - what the preview row says out loud beside the invoice.
    how: Optional[str] = None
    #: `{code, message}` when nothing resolved (AC-B5/B16), naming the supplier and the
    #: date the packing list itself states.
    refusal: Optional[dict] = None


def resolve_attach(
    db: Session,
    block: PackingBlock,
    *,
    supplier_id: str,
    attach_to: Optional[str] = None,
) -> AttachResolution:
    """Which PI this block attaches to (AC-B5), in order:

      1. The caller's own `attach_to` - the dialog's explicit pick, either the invoice a
         "Attach packing list" was started from (AC-B10, locked) or the one an operator
         chose on the preview row. Explicit beats derived: nothing the file states can
         overrule the person holding both documents.
      2. The block's own stated invoice number equals a PI's `supplier_ref` - bare, or
         suffixed with the block's own container (the same suffix `supplier_ref_for` gives
         a reference more than one document in a parse shares).
      3. The block's own container number equals exactly one CURRENT PI's `container_ref`
         for this supplier - the Jiexia shape, where the invoice number is stated once
         above the FIRST block and never repeated, but every container has its own PI and
         its own block here.
      4. Exactly one CURRENT PI of this supplier states the SAME DATE as the block.

    None of the four -> a refusal naming the supplier and the packing list's own stated
    date, so the operator knows what to search by (AC-B16). There is deliberately no
    "exactly one current PI of this supplier, whatever the dates" shortcut: an invoice
    that happens to be the only one on file is not evidence that THIS packing list belongs
    to it, and the picker is right there.
    """
    if attach_to:
        picked = (
            db.query(ProformaInvoice)
            .filter(
                ProformaInvoice.id == str(attach_to),
                ProformaInvoice.supplier_id == str(supplier_id),
            )
            .first()
        )
        if picked is not None:
            return AttachResolution(invoice=picked, how="explicit")

    if block.pi_number:
        candidates = [block.pi_number]
        if block.container_no:
            candidates.append(f"{block.pi_number}-{block.container_no}"[:100])
        by_ref = (
            db.query(ProformaInvoice)
            .filter(
                ProformaInvoice.supplier_id == str(supplier_id),
                ProformaInvoice.supplier_ref.in_(candidates),
            )
            .first()
        )
        if by_ref is not None:
            return AttachResolution(invoice=by_ref, how="invoice_number")

    if block.container_no:
        by_container = (
            db.query(ProformaInvoice)
            .filter(
                ProformaInvoice.supplier_id == str(supplier_id),
                ProformaInvoice.container_ref == block.container_no,
                func.coalesce(ProformaInvoice.status, "current") == "current",
            )
            .all()
        )
        if len(by_container) == 1:
            return AttachResolution(invoice=by_container[0], how="container")

    if block.invoice_date:
        by_date = (
            db.query(ProformaInvoice)
            .filter(
                ProformaInvoice.supplier_id == str(supplier_id),
                ProformaInvoice.invoice_date == block.invoice_date,
                func.coalesce(ProformaInvoice.status, "current") == "current",
            )
            .all()
        )
        if len(by_date) == 1:
            return AttachResolution(invoice=by_date[0], how="date")

    from app.models.procurement import Supplier

    supplier = db.query(Supplier).filter(Supplier.id == str(supplier_id)).first()
    supplier_name = supplier.supplier_name if supplier else "this supplier"
    dated = (
        f"dated {block.invoice_date.isoformat()}"
        if block.invoice_date
        else "with no date on it"
    )
    return AttachResolution(
        refusal={
            "code": "proforma_invoice_required",
            "message": (
                f"No proforma invoice on file for {supplier_name} matches this packing "
                f"list {dated}. Pick which invoice it belongs to."
            ),
        }
    )


def resolve_attach_pi(
    db: Session,
    block: PackingBlock,
    *,
    supplier_id: str,
    attach_to: Optional[str] = None,
) -> ProformaInvoice:
    """`resolve_attach`, for the write path: the invoice, or the refusal as a 409."""
    resolved = resolve_attach(db, block, supplier_id=supplier_id, attach_to=attach_to)
    if resolved.invoice is None:
        refusal = resolved.refusal or {}
        raise AppException(
            409,
            refusal.get("message", "No proforma invoice matches this packing list."),
            code=refusal.get("code", "proforma_invoice_required"),
        )
    return resolved.invoice


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def _row_or_404(db: Session, invoice_id: str, row_id: str) -> ProformaInvoicePackingLine:
    # A path segment that is not a uuid at all is a 404, not a 500: comparing it against a
    # uuid column raises a DataError out of the driver, which the operator reads as "the
    # server broke" for what is really a bad link.
    if not _is_uuid(row_id) or not _is_uuid(invoice_id):
        raise AppException(404, "That packing row does not exist.", detail="row_id")
    row = (
        db.query(ProformaInvoicePackingLine)
        .filter(
            ProformaInvoicePackingLine.id == str(row_id),
            ProformaInvoicePackingLine.proforma_invoice_id == str(invoice_id),
        )
        .first()
    )
    if row is None:
        raise AppException(404, "That packing row does not exist.", detail="row_id")
    return row


def dismiss_packing_line(
    db: Session, invoice_id: str, row_id: str, *, actor: Optional[str] = None
) -> ProformaInvoicePackingLine:
    """AC-B7: the SAME ruling a Dismiss anywhere in this channel makes - every later
    upload lands this code `dismissed` without asking again (AC-B6)."""
    from app.services.scm.proforma_invoice_service import get_or_404

    row = _row_or_404(db, invoice_id, row_id)
    invoice = get_or_404(db, invoice_id)
    supplier_code_alias_service.dismiss(
        db, supplier_id=str(invoice.supplier_id), supplier_code=row.item_code, actor=actor
    )
    row.match_state = "dismissed"
    db.flush()
    # Its line loses those cartons and that weight the moment it stops counting (AC-B8,
    # ruling 8): the roll-up is re-run for the whole invoice after EVERY packing write.
    rollup_invoice(db, str(invoice.id))
    return row


def undo_dismiss_packing_line(
    db: Session, invoice_id: str, row_id: str, *, actor: Optional[str] = None
) -> ProformaInvoicePackingLine:
    """The pending window's Undo (AC-B7): forgets the dismissal ruling itself (so the next
    upload does not immediately re-dismiss it) and puts this row back to unmatched."""
    from app.services.scm.proforma_invoice_service import get_or_404

    row = _row_or_404(db, invoice_id, row_id)
    invoice = get_or_404(db, invoice_id)
    alias = (
        db.query(SupplierProductCodeAlias)
        .filter(
            SupplierProductCodeAlias.supplier_id == str(invoice.supplier_id),
            func.upper(SupplierProductCodeAlias.supplier_code) == row.item_code.upper(),
            SupplierProductCodeAlias.source == _DISMISSED,
        )
        .first()
    )
    if alias is not None:
        supplier_code_alias_service.delete(db, str(alias.id), actor=actor)
    row.match_state = "unmatched"
    db.flush()
    rollup_invoice(db, str(invoice.id))
    return row


def match_packing_line(
    db: Session,
    invoice_id: str,
    row_id: str,
    *,
    product_id: Optional[str] = None,
    product_set_id: Optional[str] = None,
    actor: Optional[str] = None,
) -> ProformaInvoicePackingLine:
    """"It is this product after all" on a packing row (AC-B12).

    ONE decision, written where every other match in this channel is written: the
    supplier's own `manual` alias for the code. `supplier_code_alias_service.create` then
    rebinds every row already uploaded under it - stock rows, invoice lines and (S2) this
    packing row - which is what links it to the PI line of that product, sets its
    `match_state` and re-rolls the line's figures. Nothing here writes the row itself, so
    a match made on this tab and one made from the Lines tab cannot drift apart.
    """
    row = _row_or_404(db, invoice_id, row_id)
    from app.services.scm.proforma_invoice_service import get_or_404

    invoice = get_or_404(db, invoice_id)
    supplier_code_alias_service.create(
        db,
        supplier_id=str(invoice.supplier_id),
        supplier_code=row.item_code,
        product_id=product_id,
        product_set_id=product_set_id,
        actor=actor,
    )
    db.refresh(row)
    return row
