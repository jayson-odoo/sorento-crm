"""Hold the supplier's proforma invoices, with the prices they actually state.

Two-step like every other upload channel here: `preview` and `validate` describe, `apply`
writes, and `?validate_only=true` returns the same `{valid, errors, warnings, summary}`
verdict a Test means everywhere else in this system.

What is particular to this channel:

  * **One file is several invoices.** Jinbaichuan's pre-loading list is five proforma
    invoices stacked down one sheet and states no document number for any of them, so a
    positional one is derived (`PI-<file stem>-<block>`) - stable across a re-upload, which
    is what makes the second upload update five invoices instead of creating five more.
  * **A price is never stored without its currency.** The document usually says (`RMB`,
    `单价(元)`), the supplier's price list sometimes says, and where neither does the upload
    is refused with the gap named rather than stored in a house default (AC-P3.2).
  * **Products are RESOLVED, never created**, on an exact case-insensitive code match. An
    unmatched line is still stored - it is a real charge on a real invoice - and named in
    the preview so somebody can go and fix the catalogue.
"""
from __future__ import annotations

import uuid
from datetime import date as _date
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.procurement import InboundShipment, InboundShipmentLine, Supplier
from app.models.scm import ProformaInvoice, ProformaInvoiceLine, ProformaInvoiceShipmentLink
from app.services.company_scope_sql import company_sql_predicate
from app.services.error_handler import AppException
from app.services.numbering_service import NumberingService
from app.services.scm.currency_resolution import resolve_currency
from app.services.scm.proforma_invoice_reader import (
    ProformaDocument,
    ProformaReadResult,
    read_workbook,
)
from app.services.scm.supplier_scope import (  # noqa: F401  (assert_supplier is re-exported)
    assert_supplier,
    is_uuid as _is_uuid,
    supplier_label as _supplier_label,
)
from app.services.scm.upload_validation import envelope, named

SOURCE_SYSTEM = "scm_proforma_invoice"

#: What an invoice is called when the document states no number of its own. Positional, so
#: the same file re-uploaded produces the same names and lands on the same invoices.
_DERIVED_PREFIX = "PI"

#: A stated total and the sum of the lines are money; a cent of rounding is not a discrepancy.
_TOTAL_TOLERANCE = 0.01

#: The sentence the operator has to be able to act on. Quoted in the UAC (AC-P3.2), so it is
#: one constant rather than two spellings that drift between Test and Apply.
_NO_CURRENCY = (
    "Nothing says which money these prices are in - state the currency this invoice is in."
)

# --- PI -> draft inbound shipment convert (packing-list amendment, 20 Aug evening) --------

#: Not-yet-a-real-packing-list. Distinct from every OTHER value in the column's vocabulary,
#: all of which describe a container the AGENT has actually loaded or shipped - this one
#: exists only because CRM lines were pre-filled from proforma invoices (AC per
#: PLAN-scm-proforma-to-spo.md's Amendment). The real packing list, when it arrives, is
#: uploaded through the existing `packing_list_service.apply` path same as any other.
_DRAFT_SHIPMENT_STATUS = "draft"

#: `NumberingService` doc_type for a draft shipment's own series - kept distinct from a real
#: container's number (usually the container number itself, or `PRELOAD-...`) so the two can
#: never collide. Falls back to a random suffix when no numbering rule is configured, same
#: shape as `decision_service._draft_po_for_supplier`'s `PO-DRAFT-<hex8>`.
_DRAFT_NUMBER_DOC_TYPE = "inbound_shipment_draft"
_DRAFT_NUMBER_PREFIX = "SHIP-DRAFT"


def _uuid() -> str:
    return str(uuid.uuid4())


def _f(value: Any) -> Optional[float]:
    return None if value is None else float(value)


def _parse(db: Session, data: bytes) -> ProformaReadResult:
    return read_workbook(data, db=db)


def pi_number_for(doc: ProformaDocument, *, source_ref: Optional[str]) -> str:
    """What this invoice is called, so two blocks in one file are two invoices.

    The document's own number when it states one, verbatim. Otherwise the file's own name
    plus the block's position: the pre-loading list numbers none of its five invoices, and
    deriving rather than generating is what makes a re-upload update them in place (AC-P2.5).
    """
    if doc.pi_number:
        return doc.pi_number.strip()[:100]
    # The STEM is truncated, not the composed name: a long filename would otherwise push the
    # block index off the end of a `String(100)` column and turn five distinct invoices into
    # one name that each block in turn overwrites.
    stem = (source_ref or "proforma").rsplit("/", 1)[-1].rsplit(".", 1)[0][:80]
    return f"{_DERIVED_PREFIX}-{stem}-{doc.index}"


def _products_by_code(db: Session, codes: set[str]) -> dict[str, dict]:
    """Catalogue lookup, scoped to the caller's company.

    Raw SQL bypasses the ORM's company filter, and product codes are NOT unique across
    companies - so unscoped, an invoice line could resolve to another company's product.
    Exact and case-insensitive: no fuzzy match and no alias table (AC-P1.3).
    """
    if not codes:
        return {}
    predicate, params = company_sql_predicate(db, "p.company_id", param_prefix="c")
    rows = db.execute(
        text(
            "SELECT p.id, p.product_code FROM products p "
            " WHERE upper(p.product_code) = ANY(:codes) "
            f"   AND {predicate or 'true'}"
        ),
        {"codes": [c.upper() for c in codes], **params},
    ).mappings().all()
    return {str(r["product_code"]).upper(): dict(r) for r in rows}


def _currencies(
    db: Session,
    parsed: ProformaReadResult,
    *,
    supplier_id: Optional[str],
    requested: Optional[str],
) -> dict[int, tuple[Optional[str], str]]:
    """Per document, `(code, source)`. Per document because a file can hold several, and a
    currency shown against the wrong one is worse than no currency at all."""
    return {
        doc.index: resolve_currency(
            db, supplier_id=supplier_id, requested=requested, stated=doc.currency_hint
        )
        for doc in parsed.documents
    }


def _summarise(
    db: Session,
    parsed: ProformaReadResult,
    *,
    supplier_id: Optional[str],
    source_ref: Optional[str],
    requested_currency: Optional[str] = None,
    known: Optional[dict[str, dict]] = None,
    resolved: Optional[dict[int, tuple[Optional[str], str]]] = None,
) -> dict[str, Any]:
    """What the file holds, described. `known` and `resolved` are injectable so `apply`,
    which needs both to do the writing, does not pay for them a second time to describe
    what it wrote."""
    codes = {ln.item_code for d in parsed.documents for ln in d.lines}
    if known is None:
        known = _products_by_code(db, codes)
    unknown = sorted({c for c in codes if c.upper() not in known})
    if resolved is None:
        resolved = _currencies(
            db, parsed, supplier_id=supplier_id, requested=requested_currency
        )

    documents = []
    priced_without_currency = 0
    for doc in parsed.documents:
        currency, source = resolved.get(doc.index, (None, "none"))
        if doc.priced_lines and not currency:
            priced_without_currency += doc.priced_lines
        documents.append(
            {
                "index": doc.index,
                "pi_number": pi_number_for(doc, source_ref=source_ref),
                "pi_number_stated": bool(doc.pi_number),
                "invoice_date": doc.invoice_date.isoformat() if doc.invoice_date else None,
                "container_no": doc.container_no,
                "bl_no": doc.bl_no,
                "lines": len(doc.lines),
                "qty": doc.total_qty,
                "total": doc.line_total,
                "stated_total": doc.stated_total,
                "unmatched_items": sorted(
                    {ln.item_code for ln in doc.lines if ln.item_code.upper() not in known}
                )[:50],
                "currency": currency,
                "currency_source": source,
            }
        )

    supplier_code, supplier_name = _supplier_label(db, supplier_id)
    file_currency, file_source = next(
        (resolved[d.index] for d in parsed.documents if resolved.get(d.index, (None,))[0]),
        (None, "none"),
    )
    return {
        "supplier_id": supplier_id,
        "supplier_code": supplier_code,
        "supplier_name": supplier_name,
        "documents": documents,
        "document_count": len(documents),
        "line_count": parsed.line_count,
        "priced_lines": parsed.priced_line_count,
        "rows_read": parsed.total_rows,
        "unmatched_item_codes": unknown[:200],
        "unmatched_items": len(unknown),
        "unmapped_headers": parsed.unmapped_headers,
        "currency": file_currency,
        "currency_source": file_source,
        "priced_lines_without_currency": priced_without_currency,
    }


def preview(
    db: Session,
    data: bytes,
    *,
    supplier_id: str,
    currency: Optional[str] = None,
    source_ref: Optional[str] = None,
) -> dict:
    """What this file holds, and what it would create, before anything is written."""
    parsed = _parse(db, data)
    out = _summarise(
        db, parsed, supplier_id=supplier_id, source_ref=source_ref,
        requested_currency=currency,
    )
    out["ok"] = parsed.ok
    out["missing_columns"] = parsed.missing_columns
    out["problems"] = [p.reason for p in parsed.problems][:50]
    return out


def validate(
    db: Session,
    data: bytes,
    *,
    supplier_id: str,
    currency: Optional[str] = None,
    source_ref: Optional[str] = None,
) -> dict:
    """The `{valid, errors, warnings, summary}` verdict a Test means everywhere here."""
    parsed = _parse(db, data)
    summary = _summarise(
        db, parsed, supplier_id=supplier_id, source_ref=source_ref,
        requested_currency=currency,
    )

    # NOT the row problems: `apply` refuses only an unreadable file or an unresolved
    # currency, so anything else counted as an error here would make Test say no to a file
    # Apply would happily take - and the operator has no way to tell which one is lying.
    problems: list[str] = []
    if parsed.missing_columns:
        problems.append(
            "The file does not name "
            + named(len(parsed.missing_columns), parsed.missing_columns,
                    one="the column", many="the columns")
        )
    elif not parsed.documents:
        problems.append("No proforma invoice was found in this file.")
    elif summary["priced_lines_without_currency"]:
        problems.append(_NO_CURRENCY)

    warnings: list[str] = [p.reason for p in parsed.problems][:50]
    if summary["unmatched_items"]:
        warnings.append(
            "No product matches "
            + named(summary["unmatched_items"], summary["unmatched_item_codes"],
                    one="the code", many="the codes")
            + ". Those lines are still loaded, with no product against them."
        )
    if parsed.unmapped_headers:
        warnings.append(
            "Ignored " + named(len(parsed.unmapped_headers), parsed.unmapped_headers,
                               one="the column", many="the columns")
        )
    disagreeing = [
        d["pi_number"]
        for d in summary["documents"]
        if d["stated_total"] is not None
        and abs(float(d["stated_total"]) - float(d["total"])) > _TOTAL_TOLERANCE
    ]
    if disagreeing:
        warnings.append(
            "The stated total does not match the sum of the lines on "
            + named(len(disagreeing), disagreeing, one="invoice", many="invoices")
        )

    return envelope(ok=not problems, problems=problems, warnings=warnings, summary=summary)


def apply(
    db: Session,
    data: bytes,
    *,
    supplier_id: str,
    currency: Optional[str] = None,
    source_ref: Optional[str] = None,
    actor: Optional[str] = None,
) -> dict:
    """Write one proforma invoice per document in the file. Idempotent by identity.

    Idempotent because the invoice NUMBER is the document's own or derived from the file
    rather than generated: the same file uploaded twice resolves to the same invoices and
    replaces their lines, which is AC-P1.4 and is also what stops a nervous second click
    doubling an invoice. Does not commit.
    """
    parsed = _parse(db, data)
    if not parsed.ok:
        raise AppException(
            422,
            "This file could not be read as a proforma invoice.",
            detail=", ".join(parsed.missing_columns) or "no invoice was found in it",
        )

    resolved = _currencies(db, parsed, supplier_id=supplier_id, requested=currency)
    if any(d.priced_lines and not resolved.get(d.index, (None,))[0] for d in parsed.documents):
        raise AppException(422, _NO_CURRENCY, detail="currency")

    known = _products_by_code(
        db, {ln.item_code for d in parsed.documents for ln in d.lines}
    )
    # Built here, from the catalogue lookup and the currencies this apply is about to use,
    # rather than re-read afterwards: the summary then describes exactly what was written.
    summary = _summarise(
        db, parsed, supplier_id=supplier_id, source_ref=source_ref,
        requested_currency=currency, known=known, resolved=resolved,
    )

    created = updated = 0
    results: list[dict] = []

    for doc in parsed.documents:
        number = pi_number_for(doc, source_ref=source_ref)
        code, source = resolved.get(doc.index, (None, "none"))
        invoice = (
            db.query(ProformaInvoice)
            .filter(
                ProformaInvoice.supplier_id == supplier_id,
                ProformaInvoice.pi_number == number,
            )
            .first()
        )
        existed = invoice is not None
        if invoice is None:
            invoice = ProformaInvoice(id=_uuid(), supplier_id=supplier_id, pi_number=number)
            db.add(invoice)

        invoice.invoice_date = doc.invoice_date
        # A PRICED document without a currency never reaches here - it was refused above. An
        # unpriced one has nothing to denominate and stays NULL. Never a house default (AC-P3.3).
        invoice.currency = code or invoice.currency
        invoice.container_ref = doc.container_no
        invoice.bl_ref = doc.bl_no
        # The document's own total when it states one - it is the number on the paper the
        # supplier sent, and the line sum is what we make of it. Where it states none, the
        # sum is the honest stand-in.
        invoice.total_amount = doc.stated_total if doc.stated_total is not None else doc.line_total
        invoice.line_count = len(doc.lines)
        invoice.source_ref = source_ref
        invoice.block_index = doc.index
        invoice.uploaded_by = actor
        db.flush()

        # Replace rather than merge: the file is the document of record, and a line the new
        # version no longer carries is a line the supplier withdrew.
        db.query(ProformaInvoiceLine).filter(
            ProformaInvoiceLine.invoice_id == invoice.id
        ).delete(synchronize_session=False)
        db.flush()

        unmatched: list[str] = []
        for n, ln in enumerate(doc.lines, start=1):
            product = known.get(ln.item_code.upper())
            if product is None:
                unmatched.append(ln.item_code)
            db.add(
                ProformaInvoiceLine(
                    id=_uuid(),
                    invoice_id=invoice.id,
                    line_no=n,
                    row_number=ln.row_number,
                    item_code=ln.item_code[:100],
                    description=ln.description,
                    qty=ln.qty,
                    uom=ln.uom[:20] if ln.uom else None,
                    unit_price=ln.unit_price,
                    amount=ln.amount,
                    po_ref=ln.po_ref[:100] if ln.po_ref else None,
                    remark=ln.remark,
                    product_id=product["id"] if product else None,
                )
            )
        db.flush()

        created += 0 if existed else 1
        updated += 1 if existed else 0
        results.append(
            {
                "index": doc.index,
                "invoice_id": str(invoice.id),
                "pi_number": invoice.pi_number,
                "invoice_date": invoice.invoice_date.isoformat() if invoice.invoice_date else None,
                "currency": invoice.currency or None,
                "currency_source": source,
                "lines": len(doc.lines),
                "total_amount": _f(invoice.total_amount),
                "unmatched_items": sorted(set(unmatched))[:50],
                "created": not existed,
            }
        )

    summary.update(
        {
            "documents_created": created,
            "documents_updated": updated,
            "results": results,
        }
    )
    return {
        "documents_created": created,
        "documents_updated": updated,
        "results": results,
        "summary": summary,
    }


def _draft_shipment_number(db: Session) -> str:
    number = NumberingService(db).get_next_number(
        _DRAFT_NUMBER_DOC_TYPE, _date.today(), commit_rule=False
    )
    return number or f"{_DRAFT_NUMBER_PREFIX}-{uuid.uuid4().hex[:8]}"


def _product_base_uoms(db: Session, product_ids: set[str]) -> dict[str, Optional[str]]:
    if not product_ids:
        return {}
    from app.models.product import Product

    rows = (
        db.query(Product.id, Product.base_uom_id)
        .filter(Product.id.in_(product_ids))
        .all()
    )
    return {str(pid): (str(uom_id) if uom_id else None) for pid, uom_id in rows}


def convert_to_draft_shipment(
    db: Session, invoice_ids: list[str], *, created_by: Optional[str] = None
) -> dict:
    """One or more proforma invoices become ONE draft inbound shipment (the packing-list
    amendment, `PLAN-scm-proforma-to-spo.md`): "pick one or more PIs -> the system creates a
    DRAFT inbound shipment pre-filled with their lines". Several PIs are allowed to come from
    DIFFERENT suppliers on purpose - a container is routinely one factory's PI joining three
    others' inside the same box (the real KAILU + FSCU8103365 documents this was built
    against) - so every shipment line carries its OWN `supplier_id`, never the header's.

    Not built here: the real packing list replacing/reconciling this draft (that is the
    EXISTING upload path, `packing_list_service.apply`, unchanged by this function - a draft's
    `shipment_number` is its own series so it never collides with what a real upload derives,
    and nothing here teaches that upload to find this row; reconciling onto the exact draft
    is follow-up work) and the "Create SPO" action off the shipment (the next slice).

    Idempotent by refusal, not by silently updating: a PI that has ANY conversion outcome
    recorded already (`ProformaInvoiceShipmentLink`, matched or skipped) is refused with a 409
    naming the shipment it already went to - converting it again would double what counts as
    incoming stock until somebody notices two drafts.

    A line with no catalogue product match, or a non-positive quantity, is reported and
    SKIPPED rather than dropped silently - `inbound_shipment_lines.product_id` is NOT NULL,
    so there is nowhere to write it, and a skip is recorded (`unmatched_reason`) so the PI
    detail page can still say what happened to it. Refuses only when NOTHING in the whole
    selection can convert; a partial match still creates the shipment.
    """
    ids = list(dict.fromkeys(str(i).strip() for i in (invoice_ids or []) if str(i).strip()))
    if not ids:
        raise AppException(
            422, "Select at least one proforma invoice to convert.", detail="proforma_invoice_ids"
        )

    invoices = db.query(ProformaInvoice).filter(ProformaInvoice.id.in_(ids)).all()
    found_by_id = {str(inv.id): inv for inv in invoices}
    missing = [i for i in ids if i not in found_by_id]
    if missing:
        raise AppException(
            404,
            "One or more proforma invoices could not be found.",
            detail=", ".join(missing),
        )

    # Idempotency: a PI already converted names the shipment it went to rather than
    # converting again. Checked before anything is read further, so a caller re-submitting a
    # mixed batch (some new, some already-done) gets one clear refusal naming all of them.
    already = (
        db.query(ProformaInvoiceShipmentLink, InboundShipment.shipment_number)
        .join(
            InboundShipment,
            InboundShipment.id == ProformaInvoiceShipmentLink.inbound_shipment_id,
        )
        .filter(ProformaInvoiceShipmentLink.proforma_invoice_id.in_(ids))
        .all()
    )
    if already:
        by_invoice: dict[str, str] = {}
        for link, shipment_number in already:
            by_invoice.setdefault(str(link.proforma_invoice_id), shipment_number or "?")
        named_parts = [
            f"{found_by_id[i].pi_number} -> {num}"
            for i, num in by_invoice.items()
            if i in found_by_id
        ]
        raise AppException(
            409,
            "Already converted: " + "; ".join(sorted(named_parts)) + ".",
            detail="already_converted",
        )

    lines: list[ProformaInvoiceLine] = (
        db.query(ProformaInvoiceLine)
        .filter(ProformaInvoiceLine.invoice_id.in_(ids))
        .order_by(ProformaInvoiceLine.invoice_id, ProformaInvoiceLine.line_no)
        .all()
    )

    # Group by (product, supplier) - the same grain a real packing list writes on, and the
    # one that lets two PIs from the same factory naming the same model become one shipment
    # line rather than two. `source_lines` is what makes the provenance link total: every PI
    # line that fed a group links to whatever ONE shipment line the group becomes.
    groups: dict[tuple[str, Optional[str]], dict[str, Any]] = {}
    skipped: list[tuple[ProformaInvoiceLine, str]] = []
    product_ids: set[str] = set()

    for ln in lines:
        invoice = found_by_id[str(ln.invoice_id)]
        if ln.product_id is None:
            skipped.append((ln, "No catalogue product matches this line's item code."))
            continue
        qty = int(ln.qty or 0)
        if qty <= 0:
            skipped.append((ln, "This line has no positive quantity to ship."))
            continue
        product_ids.add(str(ln.product_id))
        key = (str(ln.product_id), str(invoice.supplier_id) if invoice.supplier_id else None)
        group = groups.get(key)
        if group is None:
            group = {
                "product_id": str(ln.product_id),
                "supplier_id": str(invoice.supplier_id) if invoice.supplier_id else None,
                "quantity_shipped": 0,
                "unit_cost": None,
                "currency": None,
                "remarks": [],
                "source_lines": [],
            }
            groups[key] = group
        prev_qty = group["quantity_shipped"]
        group["quantity_shipped"] = prev_qty + qty
        if ln.unit_price is not None:
            if group["unit_cost"] is None:
                group["unit_cost"] = ln.unit_price
                group["currency"] = invoice.currency
            elif (group["currency"] or None) == (invoice.currency or None):
                total_qty = Decimal(str(prev_qty)) + Decimal(str(qty))
                if total_qty > 0:
                    group["unit_cost"] = (
                        Decimal(str(group["unit_cost"])) * Decimal(str(prev_qty))
                        + Decimal(str(ln.unit_price)) * Decimal(str(qty))
                    ) / total_qty
            # A currency mismatch across the merged lines is not arithmetic - the first
            # price stands and the disagreement is visible on the PI lines themselves.
        if ln.remark:
            group["remarks"].append(ln.remark)
        group["source_lines"].append(ln)

    if not groups:
        raise AppException(
            422,
            "None of the selected invoices' lines match a product we hold, so there is "
            "nothing to draft a shipment from.",
            detail="unmatched",
        )

    uoms = _product_base_uoms(db, product_ids)

    shipment_number = _draft_shipment_number(db)
    invoice_dates = [inv.invoice_date for inv in invoices if inv.invoice_date]
    pi_numbers = sorted({inv.pi_number for inv in invoices})

    shipment = InboundShipment(
        id=_uuid(),
        shipment_number=shipment_number,
        shipment_date=min(invoice_dates) if invoice_dates else _date.today(),
        shipment_status=_DRAFT_SHIPMENT_STATUS,
        created_by=created_by,
        notes="Draft from proforma invoice(s): " + ", ".join(pi_numbers),
    )
    db.add(shipment)
    db.flush()

    shipment_lines_by_key: dict[tuple[str, Optional[str]], InboundShipmentLine] = {}
    for key, group in groups.items():
        line = InboundShipmentLine(
            id=_uuid(),
            shipment_id=shipment.id,
            product_id=group["product_id"],
            supplier_id=group["supplier_id"],
            quantity_shipped=group["quantity_shipped"],
            uom_id=uoms.get(group["product_id"]),
            unit_cost=group["unit_cost"],
            currency=group["currency"],
            remarks="; ".join(group["remarks"]) if group["remarks"] else None,
        )
        db.add(line)
        shipment_lines_by_key[key] = line
    db.flush()

    # Header supplier: whatever the written lines agree on, else none - the same rule
    # `InboundShipmentService._derive_header_supplier` applies to a real packing list.
    line_suppliers = {g["supplier_id"] for g in groups.values() if g["supplier_id"]}
    shipment.supplier_id = next(iter(line_suppliers)) if len(line_suppliers) == 1 else None

    total_qty = sum(g["quantity_shipped"] for g in groups.values())
    shipment.total_items_shipped = total_qty

    for key, group in groups.items():
        shipment_line = shipment_lines_by_key[key]
        for source_line in group["source_lines"]:
            db.add(
                ProformaInvoiceShipmentLink(
                    id=_uuid(),
                    proforma_invoice_id=source_line.invoice_id,
                    proforma_invoice_line_id=source_line.id,
                    inbound_shipment_id=shipment.id,
                    inbound_shipment_line_id=shipment_line.id,
                )
            )
    for source_line, reason in skipped:
        db.add(
            ProformaInvoiceShipmentLink(
                id=_uuid(),
                proforma_invoice_id=source_line.invoice_id,
                proforma_invoice_line_id=source_line.id,
                inbound_shipment_id=shipment.id,
                inbound_shipment_line_id=None,
                unmatched_reason=reason,
            )
        )
    db.flush()

    from app.services.procurement_service import InboundShipmentService

    # Flushes its own changes; does not commit - same "the caller commits" contract as
    # every other write in this module (`apply` above).
    InboundShipmentService(db).refresh_shipment_line_statuses(shipment.id)

    return {
        "shipment_id": str(shipment.id),
        "shipment_number": shipment.shipment_number,
        "shipment_status": shipment.shipment_status,
        "supplier_id": str(shipment.supplier_id) if shipment.supplier_id else None,
        "lines_created": len(groups),
        "lines_skipped": len(skipped),
        "invoices": [
            {
                "id": str(inv.id),
                "pi_number": inv.pi_number,
                "supplier_id": str(inv.supplier_id) if inv.supplier_id else None,
                "supplier_name": _supplier_label(db, str(inv.supplier_id))[1],
            }
            for inv in invoices
        ],
        "unmatched": [
            {
                "proforma_invoice_id": str(source_line.invoice_id),
                "pi_number": found_by_id[str(source_line.invoice_id)].pi_number,
                "line_no": source_line.line_no,
                "item_code": source_line.item_code,
                "reason": reason,
            }
            for source_line, reason in skipped
        ],
    }


def bulk_delete(db: Session, invoice_ids: list[str]) -> dict:
    """Hard delete several proforma invoices at once, same shape as the PO book's bulk
    delete (`PurchaseOrderService.bulk_delete`): ids not found (already deleted, or another
    company's) are skipped rather than failing the whole batch.

    A PI that has already been converted (any `ProformaInvoiceShipmentLink` row against it)
    is REFUSED rather than deleted - the safer of the two choices the plan named. Cascading
    the link instead would silently sever a draft shipment's line from the document that
    justified it, and a shipment already visible on `/scm/incoming` losing its "why" with no
    trace is worse than a delete the operator has to go and untangle by hand (delete the
    shipment first, or accept the PI stays on file). Named per invoice so the caller knows
    exactly which ones were blocked and why, rather than the batch failing outright.
    """
    ids = list(dict.fromkeys(str(i).strip() for i in (invoice_ids or []) if str(i).strip()))
    if not ids:
        raise AppException(422, "Select at least one proforma invoice to delete.")

    invoices = db.query(ProformaInvoice).filter(ProformaInvoice.id.in_(ids)).all()
    if not invoices:
        return {"deleted": 0, "blocked": []}

    converted_invoice_ids = {
        str(row[0])
        for row in (
            db.query(ProformaInvoiceShipmentLink.proforma_invoice_id)
            .filter(ProformaInvoiceShipmentLink.proforma_invoice_id.in_([str(i.id) for i in invoices]))
            .distinct()
            .all()
        )
    }
    shipment_numbers: dict[str, str] = {}
    if converted_invoice_ids:
        rows = (
            db.query(ProformaInvoiceShipmentLink.proforma_invoice_id, InboundShipment.shipment_number)
            .join(InboundShipment, InboundShipment.id == ProformaInvoiceShipmentLink.inbound_shipment_id)
            .filter(ProformaInvoiceShipmentLink.proforma_invoice_id.in_(converted_invoice_ids))
            .all()
        )
        for inv_id, number in rows:
            shipment_numbers.setdefault(str(inv_id), number or "?")

    blocked: list[dict] = []
    deleted = 0
    for invoice in invoices:
        inv_id = str(invoice.id)
        if inv_id in converted_invoice_ids:
            blocked.append(
                {
                    "id": inv_id,
                    "pi_number": invoice.pi_number,
                    "shipment_number": shipment_numbers.get(inv_id),
                }
            )
            continue
        db.delete(invoice)
        deleted += 1
    db.flush()
    return {"deleted": deleted, "blocked": blocked}


def get_or_404(db: Session, invoice_id: str) -> ProformaInvoice:
    """One invoice, or a refusal. Never another company's.

    A 404 rather than an empty document: the id came from somewhere, and rendering an invoice
    the caller's company does not own would be worse than saying no. The ORM query carries
    the company filter, so an id belonging to another company reads as "not found" here -
    which is the honest answer to a caller who cannot see it.
    """
    if not _is_uuid(invoice_id):
        raise AppException(404, "Proforma invoice not found.", detail="invoice_id")
    invoice = db.query(ProformaInvoice).filter(ProformaInvoice.id == str(invoice_id)).first()
    if invoice is None:
        raise AppException(404, "Proforma invoice not found.", detail="invoice_id")
    return invoice


def list_for_supplier(
    db: Session, *, supplier_id: Optional[str] = None, limit: int = 25, offset: int = 0
) -> dict:
    """Invoices we have read, newest first. `supplier_id` narrows it to one supplier.

    `total` is counted separately from the page, so it is how many invoices are held rather
    than how many came back: `len(rows)` after a `LIMIT` can never exceed the page size, and a
    supplier with more invoices than one page would have read as having exactly a page of them.
    `offset` is what makes the rest of them reachable.

    The id breaks ties in the sort, and the ties are guaranteed rather than unlikely:
    `created_at` defaults to `now()`, which is the TRANSACTION timestamp, so all five invoices
    of one stacked pre-loading list share it to the microsecond. Postgres promises no order
    among equal keys, so without the tiebreaker a caller walking offset=0 then offset=25 can
    be handed one invoice twice and never shown another.
    """
    if supplier_id and not _is_uuid(supplier_id):
        raise AppException(422, "That supplier does not exist.", detail="supplier_id")

    q = db.query(ProformaInvoice)
    if supplier_id:
        q = q.filter(ProformaInvoice.supplier_id == str(supplier_id))
    total = q.count()
    rows = (
        q.order_by(ProformaInvoice.created_at.desc(), ProformaInvoice.id.desc())
        .offset(max(offset, 0))
        .limit(limit)
        .all()
    )
    labels = _supplier_labels(db, [str(r.supplier_id) for r in rows])
    return {
        "data": [
            serialize(db, r, with_lines=False, supplier_labels=labels) for r in rows
        ],
        "total": total,
        "limit": limit,
        "offset": max(offset, 0),
    }


def delete(db: Session, invoice_id: str) -> None:
    """Hard delete, with its lines (the FK cascades), per the CRUD standard. Does not commit.

    Refused when this invoice has already been converted to a draft shipment (any
    `ProformaInvoiceShipmentLink` row against it) - `bulk_delete`'s docstring has the reasoning
    for refusing rather than cascading the link away silently.
    """
    invoice = get_or_404(db, invoice_id)
    link = (
        db.query(InboundShipment.shipment_number)
        .join(
            ProformaInvoiceShipmentLink,
            ProformaInvoiceShipmentLink.inbound_shipment_id == InboundShipment.id,
        )
        .filter(ProformaInvoiceShipmentLink.proforma_invoice_id == invoice.id)
        .first()
    )
    if link:
        raise AppException(
            409,
            f"'{invoice.pi_number}' has already been converted to shipment "
            f"'{link[0] or '?'}' and cannot be deleted.",
            detail="already_converted",
        )
    db.delete(invoice)
    db.flush()


def serialize(
    db: Session,
    invoice: ProformaInvoice,
    *,
    with_lines: bool = True,
    supplier_labels: Optional[dict[str, tuple[Optional[str], Optional[str]]]] = None,
) -> dict:
    """One invoice as the API returns it: codes and names, never a bare identifier.

    `supplier_labels` is the page's `{supplier_id: (code, name)}`, resolved once by the
    caller listing several invoices; a single serialization resolves its own.
    """
    if supplier_labels is not None:
        supplier_code, supplier_name = supplier_labels.get(
            str(invoice.supplier_id), (None, None)
        )
    else:
        supplier_code, supplier_name = _supplier_label(db, str(invoice.supplier_id))
    out: dict[str, Any] = {
        "id": str(invoice.id),
        "supplier_id": str(invoice.supplier_id),
        "supplier_code": supplier_code,
        "supplier_name": supplier_name,
        "pi_number": invoice.pi_number,
        "invoice_date": invoice.invoice_date.isoformat() if invoice.invoice_date else None,
        "currency": invoice.currency or None,
        "container_no": invoice.container_ref,
        "bl_no": invoice.bl_ref,
        "total_amount": _f(invoice.total_amount),
        "line_count": invoice.line_count,
        "source_ref": invoice.source_ref,
        "block_index": invoice.block_index,
        "uploaded_by": invoice.uploaded_by,
        "created_at": invoice.created_at.isoformat() if invoice.created_at else None,
        "updated_at": invoice.updated_at.isoformat() if invoice.updated_at else None,
    }
    if not with_lines:
        return out

    lines = (
        db.query(ProformaInvoiceLine)
        .filter(ProformaInvoiceLine.invoice_id == invoice.id)
        .order_by(ProformaInvoiceLine.line_no)
        .all()
    )
    codes = _product_codes(db, [str(ln.product_id) for ln in lines if ln.product_id])

    # Where each line went, if it has been converted (the PI -> draft-shipment convert):
    # `(shipment_id, shipment_number)` when it became a real shipment line, or an
    # `unmatched_reason` when the convert ran but this line was skipped. A line absent from
    # this map has simply never been converted.
    link_rows = (
        db.query(ProformaInvoiceShipmentLink, InboundShipment.shipment_number)
        .join(
            InboundShipment,
            InboundShipment.id == ProformaInvoiceShipmentLink.inbound_shipment_id,
        )
        .filter(ProformaInvoiceShipmentLink.proforma_invoice_id == invoice.id)
        .all()
    )
    links_by_line: dict[str, tuple[Any, str]] = {
        str(link.proforma_invoice_line_id): (link, shipment_number)
        for link, shipment_number in link_rows
    }
    # Header summary: every DISTINCT shipment this invoice's lines went to - normally one,
    # since a convert refuses a re-run, but shown as a list rather than assuming it.
    seen_shipments: dict[str, str] = {}
    for link, shipment_number in link_rows:
        seen_shipments[str(link.inbound_shipment_id)] = shipment_number
    out["converted_shipments"] = [
        {"shipment_id": sid, "shipment_number": num} for sid, num in seen_shipments.items()
    ]

    out["lines"] = [
        {
            "id": str(ln.id),
            "line_no": ln.line_no,
            "row_number": ln.row_number,
            "item_code": ln.item_code,
            "description": ln.description,
            "qty": _f(ln.qty),
            "uom": ln.uom,
            "unit_price": _f(ln.unit_price),
            "amount": _f(ln.amount),
            "po_ref": ln.po_ref,
            "remark": ln.remark,
            # The product we hold, by CODE. A line that matched nothing says so rather than
            # carrying an id nobody can read.
            "product_code": codes.get(str(ln.product_id)) if ln.product_id else None,
            "matched": ln.product_id is not None,
            # Where this line went, once converted - null on every line until the first
            # convert. `shipment_number`/`shipment_id` are set only when it became a real
            # shipment line; `unmatched_reason` is set only when the convert skipped it.
            "shipment_id": (
                str(links_by_line[str(ln.id)][0].inbound_shipment_id)
                if str(ln.id) in links_by_line and links_by_line[str(ln.id)][0].inbound_shipment_line_id
                else None
            ),
            "shipment_number": (
                links_by_line[str(ln.id)][1]
                if str(ln.id) in links_by_line and links_by_line[str(ln.id)][0].inbound_shipment_line_id
                else None
            ),
            "unmatched_reason": (
                links_by_line[str(ln.id)][0].unmatched_reason
                if str(ln.id) in links_by_line
                else None
            ),
        }
        for ln in lines
    ]
    return out


def _supplier_labels(
    db: Session, supplier_ids: list[str]
) -> dict[str, tuple[Optional[str], Optional[str]]]:
    """`(supplier_code, supplier_name)` per id in one query, company-scoped by the ORM."""
    ids = [sid for sid in set(supplier_ids) if _is_uuid(sid)]
    if not ids:
        return {}
    rows = (
        db.query(Supplier.id, Supplier.supplier_code, Supplier.supplier_name)
        .filter(Supplier.id.in_(ids))
        .all()
    )
    return {str(sid): (code, name) for sid, code, name in rows}


def _product_codes(db: Session, product_ids: list[str]) -> dict[str, str]:
    """Product code per id, for the lines that matched one. Through the ORM, so the company
    filter applies without restating it - and because `id = ANY(:ids)` on a uuid column with
    string parameters is `operator does not exist: uuid = text`."""
    if not product_ids:
        return {}
    from app.models.product import Product

    rows = (
        db.query(Product.id, Product.product_code)
        .filter(Product.id.in_(list(set(product_ids))))
        .all()
    )
    return {str(pid): code for pid, code in rows}
