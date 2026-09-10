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

import logging
import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.scm.currency_resolution import resolve_currency
from app.services.scm.packing_list_reader import (
    PackingBlock,
    PackingReadResult,
    read_workbook,
)
from app.services.scm.supplier_scope import assert_supplier
from app.services.scm.upload_validation import envelope, named

logger = logging.getLogger(__name__)

#: What a block is called when it has no container number of its own. Positional, so the same
#: file re-uploaded produces the same names and the duplicate resolver recognises them.
_PRELOAD_PREFIX = "PRELOAD"

#: The sentence the operator has to be able to act on when the file prices what it ships and
#: nothing says in what money. Shared with the proforma channel's wording (AC-P3.2).
_NO_CURRENCY = (
    "Nothing says which money these prices are in - state the currency this packing list is in."
)

#: The type this upload files itself under (R3, purchasing consolidation batch 6 Sep 2026).
#: Admin data, not seeded - the captain sets the code (or just the name) and the default
#: folder on it after deploy, same convention `container_status_document.py` reads by.
_PACKING_LIST_TYPE_CODE = "packing_list"
_PACKING_LIST_TYPE_NAME = "Packing List"


def file_supplier_document(
    db: Session,
    *,
    data: bytes,
    filename: Optional[str],
    content_type: Optional[str],
    actor_id: Optional[str],
    type_code: str = _PACKING_LIST_TYPE_CODE,
    type_name: str = _PACKING_LIST_TYPE_NAME,
) -> Optional[str]:
    """Store an uploaded workbook as an attachment of the given type. Never raises.

    `type_code`/`type_name` default to Packing List so every existing caller of this
    function (originally `_file_the_upload`, private to this module) is unaffected;
    `supplier_document_service` passes the Proforma Invoice type for a PI file (R12/R14,
    purchasing consolidation batch, lane C) - same lookup, same "never fail an otherwise
    successful apply" contract, just a different admin-set type.

    Returns the new attachment id, or None when there is nothing to file - a missing
    type (R4 is admin-set, not guaranteed to exist yet) is a named gap in the response,
    never a reason to fail an apply that otherwise succeeded.

    Deliberately NOT `attachment_webhook_helper.create_and_send_webhook`: this reader
    already produced the shipment/invoice, so firing the n8n intake webhook would create a
    SECOND one through the external route (R3) - and that is also why this attachment
    carries no `integration_log` row.
    """
    row = db.execute(
        text(
            "SELECT id, default_directory_id FROM attachment_types "
            "WHERE code = :code OR lower(type_name) = lower(:name) LIMIT 1"
        ),
        {"code": type_code, "name": type_name},
    ).fetchone()
    if not row:
        logger.warning(
            "No attachment type named %r (or code %r) - the uploaded file will "
            "not be filed in Drive",
            type_name,
            type_code,
        )
        return None
    type_id, default_directory_id = str(row[0]), (str(row[1]) if row[1] else None)

    try:
        from app.schemas.resources import AttachmentCreate
        from app.services.resources_service import AttachmentService
        from app.services.storage_router import (
            cdn_base_url,
            default_provider,
            get_backend,
            sanitize_storage_filename,
        )

        attachment_id = str(uuid.uuid4())
        original_filename = sanitize_storage_filename(filename or f"{type_code}.xlsx")
        provider = default_provider()
        backend = get_backend(provider)
        s3_key, _ = backend.upload_file(
            file_content=data,
            file_path=f"{type_code}/{attachment_id}/{original_filename}",
            content_type=content_type,
        )
        attachment_data = AttachmentCreate(
            id=attachment_id,
            attachment_type_id=type_id,
            original_filename=original_filename,
            stored_filename=filename or original_filename,
            file_path=cdn_base_url(provider, s3_key),
            file_size_bytes=len(data),
            mime_type=content_type or "application/octet-stream",
            directory_id=default_directory_id,
            # Without this the row reads `s3` (the schema default) regardless of where the
            # bytes actually went - `storage_router`'s reads (preview, download, presigned
            # URL) dispatch on this column, so a wrong value 404s the very file just filed.
            storage_provider=provider,
        )
        # `attachment_id` was already minted above and handed to `AttachmentCreate.id`, so
        # it IS the new row's PK - no need to read it back off whatever the service returns.
        AttachmentService(db).create_attachment(attachment_data, actor_id)
        return attachment_id
    except Exception:  # noqa: BLE001 - a filing failure must not fail the apply itself
        logger.warning("Could not file the uploaded document as an attachment", exc_info=True)
        # A failed INSERT (or the upload call itself) can leave the session in
        # `PendingRollbackError` for every statement after it, which turned "no filed
        # copy" into a 500 on the apply that was otherwise fine. Roll back so the caller's
        # session is usable again.
        db.rollback()
        return None


def _priced(parsed: PackingReadResult) -> int:
    """How many lines carry a unit price. A price is what makes a currency compulsory."""
    return sum(1 for b in parsed.blocks for ln in b.lines if ln.unit_price is not None)


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
