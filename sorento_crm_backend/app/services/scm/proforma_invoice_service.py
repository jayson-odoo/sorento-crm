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
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.scm import ProformaInvoice, ProformaInvoiceLine
from app.services.company_scope_sql import company_sql_predicate
from app.services.error_handler import AppException
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
    return {
        "data": [serialize(db, r, with_lines=False) for r in rows],
        "total": total,
        "limit": limit,
        "offset": max(offset, 0),
    }


def delete(db: Session, invoice_id: str) -> None:
    """Hard delete, with its lines (the FK cascades), per the CRUD standard. Does not commit."""
    db.delete(get_or_404(db, invoice_id))
    db.flush()


def serialize(db: Session, invoice: ProformaInvoice, *, with_lines: bool = True) -> dict:
    """One invoice as the API returns it: codes and names, never a bare identifier."""
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
        }
        for ln in lines
    ]
    return out


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
