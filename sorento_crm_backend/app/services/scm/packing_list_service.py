"""Turn a multi-block packing list into inbound shipments, one per container.

The writing is NOT done here. `InboundShipmentService.create_shipment` already resolves a
shipment by number, then by the container triple, then by attachment, updates in place when it
finds one, and refuses a genuine duplicate of a received packing list. That is AC-G3 and AC-G2
already satisfied, and re-implementing it beside itself would give the workbook path and the
n8n PDF path two different ideas of what "the same shipment" means. So this module reads the
file, decides what each block IS, and hands each one to that service.

What it adds is the part that only exists here:

  * **A shipment number per block.** The file gives one document covering several containers, so
    the blocks need distinguishing from each other before the duplicate resolver ever sees them.
    A container number is used when the block has one; a pre-load block that has none is
    numbered by its position in the file, which is stable across a re-upload of the same file
    and is the only thing that distinguishes two otherwise identical blank blocks (AC-G3).
  * **Product resolution.** A code we do not hold is a NAMED problem, never an invented product,
    because `inbound_shipment_lines.product_id` is NOT NULL and the alternative to naming it is
    dropping the line silently.

Two-step like every other upload channel here: `preview` and `validate` describe, `apply`
writes, and `?validate_only=true` returns the same `{valid, errors, warnings, summary}` verdict
a Test means everywhere else in this system.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.procurement import InboundShipmentCreate, InboundShipmentLineCreate
from app.services.error_handler import AppException
from app.services.scm.currency_resolution import resolve_currency
from app.services.scm.packing_list_reader import (
    PackingBlock,
    PackingLine,
    PackingReadResult,
    read_workbook,
)
from app.services.scm.supplier_scope import assert_supplier
from app.services.scm.upload_validation import envelope, named

#: What a block is called when it has no container number of its own. Positional, so the same
#: file re-uploaded produces the same names and the duplicate resolver recognises them.
_PRELOAD_PREFIX = "PRELOAD"

#: The sentence the operator has to be able to act on when the file prices what it ships and
#: nothing says in what money. Shared with the proforma channel's wording (AC-P3.2).
_NO_CURRENCY = (
    "Nothing says which money these prices are in - state the currency this packing list is in."
)


def _priced(parsed: PackingReadResult) -> int:
    """How many lines carry a unit price. A price is what makes a currency compulsory."""
    return sum(1 for b in parsed.blocks for ln in b.lines if ln.unit_price is not None)


def _line_cbm(ln: PackingLine) -> Optional[Decimal]:
    """The volume of one line, in the unit the file states it in.

    The stated total when there is one, otherwise the per-unit figure times the quantity.
    `None` when the file measured neither: an unmeasured line must not be stored as 0, or a
    subtotal reads as complete when it is not.

    Through `str` rather than `Decimal(float)`, so 0.21 stays 0.21 instead of arriving as
    its binary approximation in a Numeric(12,4) column.
    """
    if ln.cbm_total is not None:
        return Decimal(str(ln.cbm_total))
    if ln.cbm_per_unit is not None and ln.qty:
        return Decimal(str(round(ln.cbm_per_unit * ln.qty, 6)))
    return None


def _parse(db: Session, data: bytes) -> PackingReadResult:
    return read_workbook(data, db=db)


def _check_supplier(db: Session, supplier_id: Optional[str]) -> None:
    """A STATED supplier has to be one we hold, same rule as the proforma channel.

    Optional on `preview` and `validate` (a pre-load list is read before anyone commits to
    whose it is), required on `apply`, so only a stated one is checked here and `apply`'s own
    signature does the requiring. It has to be checked before the currency resolution: the
    supplier price list is one of the currency sources, and a value that is not an id reached
    a UUID column there, which is a 500 with the session aborted rather than the 422 the
    operator can act on.
    """
    if supplier_id:
        assert_supplier(db, supplier_id)


def _products_by_code(db: Session, codes: set[str]) -> dict[str, dict]:
    """Catalogue lookup, scoped to the caller's company.

    Raw SQL bypasses the ORM's company filter, and product codes are NOT unique across
    companies - `BRACD7799CP-ENG` exists twice in this database. Unscoped, this matched
    whichever row came back first, so a packing list could be received against another
    company's product and then find no purchase order to draw down, which is how the bug
    presented: a container that imported cleanly and had nothing to allocate.
    """
    if not codes:
        return {}
    from app.services.company_scope_sql import company_sql_predicate

    predicate, params = company_sql_predicate(db, "p.company_id", param_prefix="c")
    rows = db.execute(
        text(
            "SELECT p.id, p.product_code, p.base_uom_id FROM products p "
            " WHERE upper(p.product_code) = ANY(:codes) "
            f"   AND {predicate or 'true'}"
        ),
        {"codes": [c.upper() for c in codes], **params},
    ).mappings().all()
    return {str(r["product_code"]).upper(): dict(r) for r in rows}


def shipment_number_for(block: PackingBlock, *, source_ref: Optional[str]) -> str:
    """What this block is called, so two blocks in one file are two shipments.

    A container number when there is one. Otherwise the file's own name plus the block's
    position: a pre-load list has no container yet (AC-G2), and its blocks are told apart by
    where they sit in the document. Deriving it rather than generating one is what makes a
    re-upload land on the same shipments instead of a second set (AC-G3).
    """
    if block.container_no:
        return block.container_no
    stem = (source_ref or "packing-list").rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return f"{_PRELOAD_PREFIX}-{stem}-{block.index}"[:100]


def _summarise(db: Session, parsed: PackingReadResult, *, source_ref: Optional[str]) -> dict:
    codes = {ln.item_code for b in parsed.blocks for ln in b.lines}
    known = _products_by_code(db, codes)
    unknown = sorted({c for c in codes if c.upper() not in known})

    blocks = [
        {
            "index": b.index,
            "shipment_number": shipment_number_for(b, source_ref=source_ref),
            "container_no": b.container_no,
            "bl_no": b.bl_no,
            "lines": len(b.lines),
            "qty": b.total_qty,
            "cartons": b.total_cartons,
            "unmatched_items": sorted(
                {ln.item_code for ln in b.lines if ln.item_code.upper() not in known}
            )[:50],
        }
        for b in parsed.blocks
    ]
    return {
        "blocks": blocks,
        "block_count": len(blocks),
        "line_count": parsed.line_count,
        "rows_read": parsed.total_rows,
        "unmatched_item_codes": unknown[:200],
        "unmatched_items": len(unknown),
        "unmapped_headers": parsed.unmapped_headers,
    }


def preview(
    db: Session,
    data: bytes,
    *,
    source_ref: Optional[str] = None,
    supplier_id: Optional[str] = None,
    currency: Optional[str] = None,
) -> dict:
    """What this file would create, before anything is written.

    Takes the same `supplier_id` / `currency` the apply will, and reports which currency
    resolved and where from: the preview is what the operator reads before pressing Confirm,
    and a preview that cannot say the file is priced in nothing would let them press it and
    only then be told (AC-P3.1).
    """
    _check_supplier(db, supplier_id)
    parsed = _parse(db, data)
    out = _summarise(db, parsed, source_ref=source_ref)
    code, source = resolve_currency(
        db, supplier_id=supplier_id, requested=currency, stated=parsed.currency_hint
    )
    out["currency"] = code
    out["currency_source"] = source
    out["priced_lines"] = _priced(parsed)
    out["ok"] = parsed.ok
    out["missing_columns"] = parsed.missing_columns
    out["problems"] = [p.reason for p in parsed.problems][:50]
    return out


def validate(
    db: Session,
    data: bytes,
    *,
    source_ref: Optional[str] = None,
    supplier_id: Optional[str] = None,
    currency: Optional[str] = None,
) -> dict:
    """The `{valid, errors, warnings, summary}` verdict a Test means everywhere here."""
    _check_supplier(db, supplier_id)
    parsed = _parse(db, data)
    summary = _summarise(db, parsed, source_ref=source_ref)
    code, source = resolve_currency(
        db, supplier_id=supplier_id, requested=currency, stated=parsed.currency_hint
    )
    summary["currency"] = code
    summary["currency_source"] = source
    summary["priced_lines"] = _priced(parsed)

    # Row problems are WARNINGS, mirroring the proforma channel: apply loads the readable
    # rows regardless, and a Test that says "invalid" about a file Confirm then accepts is
    # a verdict the operator learns to ignore. Errors are only what apply refuses.
    problems: list[str] = []
    if parsed.missing_columns:
        problems.append(
            "The file does not name "
            + named(len(parsed.missing_columns), parsed.missing_columns,
                    one="the column", many="the columns")
        )
    elif not parsed.blocks:
        problems.append("No container block was found in this file.")
    elif summary["priced_lines"] and not code:
        # A price parsed and then stored without its currency is a number with no meaning,
        # so it is refused here rather than landed as a bare figure (AC-P5.2).
        problems.append(_NO_CURRENCY)

    warnings: list[str] = [p.reason for p in parsed.problems][:50]
    if summary["unmatched_items"]:
        warnings.append(
            "No product matches "
            + named(summary["unmatched_items"], summary["unmatched_item_codes"],
                    one="the code", many="the codes")
            + ". Those lines will not be created."
        )
    if parsed.unmapped_headers:
        warnings.append(
            "Ignored " + named(len(parsed.unmapped_headers), parsed.unmapped_headers,
                               one="the column", many="the columns")
        )

    return envelope(ok=not problems, problems=problems, warnings=warnings, summary=summary)


def apply(
    db: Session,
    data: bytes,
    *,
    supplier_id: str,
    shipment_date: Optional[date] = None,
    currency: Optional[str] = None,
    source_ref: Optional[str] = None,
    attachment_id: Optional[str] = None,
    actor_id: Optional[str] = None,
) -> dict:
    """Create or update one inbound shipment per block. Idempotent by construction.

    Idempotent because the shipment NAME is derived from the file rather than generated: the
    same file uploaded twice resolves to the same shipments and updates them in place, which is
    AC-G3 and is also what stops a nervous second click doubling a container.

    `supplier_id` is REQUIRED. A packing list comes from one factory, and a container is
    routinely filled by two or three of them; an upload that does not say whose it is speaks
    for the whole container and would delete the other factories' lines.
    """
    _check_supplier(db, supplier_id)
    parsed = _parse(db, data)
    if not parsed.ok:
        raise AppException(
            422,
            "This file could not be read as a packing list.",
            detail=", ".join(parsed.missing_columns) or "no container block was found",
        )

    # The pre-loading list prices what it ships, and that price used to be parsed and then
    # dropped. It is kept now - on the shipment line, with the currency it belongs to - and a
    # priced file with no resolvable currency is refused rather than stored bare (AC-P5.1/2).
    resolved_currency, _source = resolve_currency(
        db, supplier_id=supplier_id, requested=currency, stated=parsed.currency_hint
    )
    if _priced(parsed) and not resolved_currency:
        raise AppException(422, _NO_CURRENCY, detail="currency")

    known = _products_by_code(
        db, {ln.item_code for b in parsed.blocks for ln in b.lines}
    )

    from app.services.procurement_service import InboundShipmentService

    service = InboundShipmentService(db)
    created = updated = 0
    skipped_lines = 0
    results: list[dict] = []

    for block in parsed.blocks:
        lines: list[InboundShipmentLineCreate] = []
        for ln in block.lines:
            product = known.get(ln.item_code.upper())
            if product is None:
                # Named in the summary, never invented: `product_id` is NOT NULL and a made-up
                # product is worse than a line somebody has to go and fix.
                skipped_lines += 1
                continue
            lines.append(
                InboundShipmentLineCreate(
                    product_id=str(product["id"]),
                    # Whose line this is, stated on the LINE and not only on the header:
                    # one container carries several factories, and a line that does not
                    # say which one is a line the next factory's upload would replace.
                    supplier_id=supplier_id,
                    quantity_shipped=int(ln.qty),
                    uom_id=str(product["base_uom_id"]) if product.get("base_uom_id") else None,
                    cartons_count=int(ln.cartons) if ln.cartons else 1,
                    # Both None on an unpriced list, and neither defaulted: a cost of zero
                    # would read as free, and a currency nobody stated would make the
                    # incoming figure look comparable to the ordered one when it is not.
                    unit_cost=ln.unit_price,
                    currency=resolved_currency if ln.unit_price is not None else None,
                    # The reader has always parsed volume and the supplier's remark and
                    # thrown both away. The total when the file states it, otherwise the
                    # per-unit figure times the quantity; never zero for an unmeasured
                    # item, because zero reads as "takes no space".
                    cbm=_line_cbm(ln),
                    remarks=ln.remark,
                )
            )

        if not lines:
            results.append(
                {
                    "index": block.index,
                    "shipment_number": shipment_number_for(block, source_ref=source_ref),
                    "created": False,
                    "reason": "no line in this block matched a product we hold",
                }
            )
            continue

        payload = InboundShipmentCreate(
            shipment_number=shipment_number_for(block, source_ref=source_ref),
            supplier_id=supplier_id,
            # Required by the schema. The packing list states a container, not a date, so the
            # caller's date is used and today is the honest fallback for "when we were told".
            shipment_date=shipment_date or date.today(),
            shipping_container_number=block.container_no,
            bill_of_lading_number=block.bl_no,
            attachment_id=attachment_id,
            total_items_shipped=int(block.total_qty),
            total_cartons=int(block.total_cartons) if block.total_cartons else None,
            shipment_lines=lines,
        )
        # `inbound_shipments.created_by` is a UUID column holding a USER ID, unlike the SCM
        # tables where `created_by` holds the person's name. Passing the name here is a
        # `invalid input syntax for type uuid` at insert time, so the two never mix.
        shipment = service.create_shipment(payload, created_by=actor_id)
        existed = bool(getattr(shipment, "_already_existed", False))
        created += 0 if existed else 1
        updated += 1 if existed else 0
        results.append(
            {
                "index": block.index,
                "shipment_id": str(shipment.id),
                "shipment_number": shipment.shipment_number,
                "container_no": shipment.shipping_container_number,
                "lines": len(lines),
                "created": not existed,
            }
        )

    summary = _summarise(db, parsed, source_ref=source_ref)
    summary.update(
        {
            "shipments_created": created,
            "shipments_updated": updated,
            "lines_skipped": skipped_lines,
            "currency": resolved_currency,
            "currency_source": _source,
            "results": results,
        }
    )
    return summary
