"""One dialog, several supplier documents: proforma invoice, packing list, or both (R12-R14,
purchasing consolidation batch, lane C).

The reading and the writing are NOT done here twice. `proforma_invoice_service` and
`packing_list_service` already parse their own doc type, resolve the catalogue, resolve the
currency, and write the invoice / the shipment (one per container block, already, for the
packing list). This module's own job is the THREE things neither of them does alone:

  * **Classify** which reader a file is for, by its title cell (`发票` / `PROFORMA INVOICE` /
    `INVOICE` vs `装箱单` / `PACKING LIST`), so ONE dialog can take either, or both together.
  * **One preview shape** across files of either kind, so the dialog renders one table
    regardless of what each file turned out to be.
  * **Price matching (R14).** A packing list's lines carry no price of their own; where a
    proforma invoice for the same supplier and the same container (or the same `pi_number`)
    exists, its lines' prices are copied onto the matching shipment lines by PRODUCT (not by
    the supplier's own item-code text, which the two documents do not always spell the same
    way) and a `proforma_invoice_shipment_link` row is written - same table, same columns as
    the "Convert to packing list" dialog writes, because that is what a linked line means
    everywhere else in this system. Never `convert_to_draft_shipment` itself: that function's
    whole job is minting a NEW shipment, and the shipment already exists here (the packing
    list's own apply already created it) - only the price and the link are new.

Runs for EVERY supplier + container pair this supplier currently holds, on every apply,
rather than only the files just uploaded: the upload order is not fixed (together, PL after
PI, PI after PL) and a small per-supplier scan is cheap next to getting one of the three
orders wrong.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.services import translation_service
from app.services.error_handler import AppException
from app.services.import_alias_service import AliasResolver
from app.services.scm import packing_list_service, proforma_invoice_service
from app.services.scm.outstanding_reader import every_sheet_rows, sheet_rows
from app.services.scm.packing_list_reader import DOC_TYPE as PL_DOC_TYPE
from app.services.scm.packing_list_reader import PackingReadResult
from app.services.scm.packing_list_reader import _PI_TITLE_MARKERS, _PL_TITLE_MARKERS
from app.services.scm.packing_list_reader import _header_map, _is_header
from app.services.scm.packing_list_reader import read_workbook as read_packing_list
from app.services.scm.proforma_invoice_reader import DOC_TYPE as PI_DOC_TYPE
from app.services.scm.proforma_invoice_reader import ProformaReadResult
from app.services.scm.proforma_invoice_reader import read_workbook as read_proforma_invoice
from app.services.scm.supplier_scope import assert_supplier

logger = logging.getLogger(__name__)

#: Title-cell markers that decide which reader a file is for (R12). Checked across the
#: first few rows, upper-cased - both real files write the title on its own row, well above
#: any labelled cell or table header. Bare "INVOICE" is deliberately NOT a marker: the
#: packing list's own labelled cell states "INVOICE NO.: ..." (the PI number both documents
#: share), which would otherwise misclassify every packing list as combined. Defined in
#: `packing_list_reader` (imported here, not duplicated) - `_shipper_of` there needs the
#: SAME list so a title row is never read as the letterhead either.
#: How many rows to scan for a title cell - both fixtures state it inside the first 10.
_TITLE_SCAN_ROWS = 15

#: The type each kind is filed under in Drive (R12/lane A's mechanism), looked up the same
#: case-insensitive `code OR type_name` way `packing_list_service.file_supplier_document`
#: already does for the packing list itself.
_PROFORMA_TYPE_CODE = "proforma_invoice"
_PROFORMA_TYPE_NAME = "Proforma Invoice"


def classify(data: bytes, db: Optional[Session] = None) -> Optional[str]:
    """`'proforma_invoice' | 'packing_list' | 'combined' | None` (unreadable/unclassifiable),
    by the file's own title cell. `None` never blocks the OTHER files in a batch - only
    itself, named, in the preview and in `apply`'s refusal.

    A titleless file falls back to what its HEADER promises, when `db` is given (review
    round 1): a header naming an item code and a quantity but no price is a packing list; a
    header that ALSO names a price is a proforma invoice; both shapes appearing somewhere in
    the workbook (on different sheets, or a sheet nobody titled at all) is combined. Every
    sheet is read for this, not only the first 15 rows of sheet 1 - a titleless workbook is
    exactly the one most likely to bury its real table on a later tab.
    """
    try:
        rows = list(sheet_rows(data))
    except Exception:  # noqa: BLE001 - an unreadable file classifies as None, not a 500
        return None
    text = " ".join(
        str(c).strip().upper() for row in rows[:_TITLE_SCAN_ROWS] for c in row if str(c).strip()
    )
    is_pi = any(marker in text for marker in _PI_TITLE_MARKERS)
    is_pl = any(marker in text for marker in _PL_TITLE_MARKERS)
    if is_pi and is_pl:
        return "combined"
    if is_pi:
        return "proforma_invoice"
    if is_pl:
        return "packing_list"
    if db is None:
        return None
    return _classify_by_header_shape(db, data)


def _classify_by_header_shape(db: Session, data: bytes) -> Optional[str]:
    """No title cell named either document - decide from the header row(s) instead. A PI's
    OWN required columns (item code, quantity, unit price - `proforma_invoice_reader`'s
    `_REQUIRED_COLUMNS`) are the stricter test, checked first: a header that satisfies them
    is proforma-invoice-shaped even though it would ALSO satisfy the packing list's own
    looser item-code-and-quantity test. Only a header that fails the stricter test but
    passes the looser one is packing-list-shaped."""
    try:
        sheets = every_sheet_rows(data)
    except Exception:  # noqa: BLE001
        return None
    pi_resolver = AliasResolver.for_doc_type(db, PI_DOC_TYPE)
    pl_resolver = AliasResolver.for_doc_type(db, PL_DOC_TYPE)
    saw_pi = saw_pl = False
    for rows in sheets:
        for raw in rows:
            if not raw:
                continue
            if _is_header(_header_map(raw, pi_resolver), required=("item_code", "qty", "unit_price")):
                saw_pi = True
                continue
            if _is_header(_header_map(raw, pl_resolver)):
                saw_pl = True
    if saw_pi and saw_pl:
        return "combined"
    if saw_pi:
        return "proforma_invoice"
    if saw_pl:
        return "packing_list"
    return None


def _text_item(text: Optional[str], translations: dict[str, Any]) -> Optional[dict[str, Any]]:
    """One translatable phrase in the preview shape (R16): the Chinese, the English the
    memory or the AI fill has for it (`None` when nobody has translated it yet), and who
    said so. `None` when there is no text at all - a line with nothing to translate
    carries no entry rather than an all-null one."""
    if not text:
        return None
    hit = translations.get(text)
    return {
        "text": text,
        "text_en": hit.text if hit else None,
        "text_en_source": hit.source if hit else None,
    }


def _pi_blocks(
    parsed: ProformaReadResult, known: dict[str, Any], translations: dict[str, Any]
) -> list[dict[str, Any]]:
    out = []
    for d in parsed.documents:
        lines = []
        for ln in d.lines:
            matched = ln.item_code.upper() in known
            # Ruling 5 (3 Sep batch): a MATCHED line shows the product master name
            # elsewhere in the UI, so only an unmatched line's own 品名 needs
            # translating here - it is the only description this preview ever shows.
            description = None if matched else ln.description
            item = _text_item(description, translations)
            if item is None:
                continue
            lines.append({"item_code": ln.item_code, "matched": matched, **item})
        out.append(
            {
                "container_no": d.container_no,
                "seal_no": d.seal_no,
                "cartons": (sum(ln.cartons for ln in d.lines if ln.cartons is not None) or None),
                "cbm_total": (
                    round(sum(ln.cbm_total for ln in d.lines if ln.cbm_total is not None), 4)
                    or None
                ),
                "amount": d.line_total or None,
                "line_count": len(d.lines),
                "note_count": 0,
                "lines": lines,
                "notes": [],
            }
        )
    return out


def _pl_blocks(
    parsed: PackingReadResult, known: dict[str, Any], translations: dict[str, Any]
) -> list[dict[str, Any]]:
    out = []
    for b in parsed.blocks:
        lines = []
        for ln in b.lines:
            matched = ln.item_code.upper() in known
            description = None if matched else ln.product_name
            # A remark only round-trips onto a shipment line for a MATCHED line - an
            # unmatched one is skipped entirely at apply time, so its remark is never
            # stored and translating it here would show a promise this screen cannot
            # keep.
            remark = ln.remark if matched else None
            desc_item = _text_item(description, translations)
            remark_item = _text_item(remark, translations)
            if desc_item is None and remark_item is None:
                continue
            lines.append(
                {
                    "item_code": ln.item_code,
                    "matched": matched,
                    "description": desc_item["text"] if desc_item else None,
                    "description_en": desc_item["text_en"] if desc_item else None,
                    "description_en_source": desc_item["text_en_source"] if desc_item else None,
                    "remark": remark_item["text"] if remark_item else None,
                    "remark_en": remark_item["text_en"] if remark_item else None,
                    "remark_en_source": remark_item["text_en_source"] if remark_item else None,
                }
            )
        notes = [
            item for note in (b.notes or []) if (item := _text_item(note, translations))
        ]
        out.append(
            {
                "container_no": b.container_no,
                "seal_no": b.seal_no,
                "cartons": b.total_cartons,
                "cbm_total": b.total_cbm,
                "amount": b.total_amount,
                "line_count": len(b.lines),
                "note_count": len(b.notes),
                "lines": lines,
                "notes": notes,
            }
        )
    return out


def _translate_preview_texts(
    db: Session,
    pi_result: Optional[ProformaReadResult],
    pl_result: Optional[PackingReadResult],
    known_pi: dict[str, Any],
    known_pl: dict[str, Any],
) -> dict[str, Any]:
    """Every Chinese phrase THIS file's preview is about to show - unmatched
    descriptions, matched-line remarks, block notes, the footer - translated in one
    batched call (R16)."""
    texts: list[str] = []
    if pi_result and pi_result.ok:
        for d in pi_result.documents:
            for ln in d.lines:
                if ln.description and ln.item_code.upper() not in known_pi:
                    texts.append(ln.description)
    if pl_result and pl_result.ok:
        for b in pl_result.blocks:
            for ln in b.lines:
                matched = ln.item_code.upper() in known_pl
                if not matched and ln.product_name:
                    texts.append(ln.product_name)
                if matched and ln.remark:
                    texts.append(ln.remark)
            texts.extend(b.notes or [])
        if pl_result.footer_notes:
            texts.append(pl_result.footer_notes)
    if not texts:
        return {}
    return translation_service.translate(db, texts)


def _pi_match_blocks(parsed: ProformaReadResult, known: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-container what a PI document would match against on the packing-list side:
    its OWN stated number and, for every LINE (not de-duplicated - two lines naming the
    same product are two separate things to match), which product it resolved to
    (`None` for a line the catalogue does not know). What `preview`'s `price_matches`
    counts against, by product rather than by how many lines happen to be on each side
    (S8, review round 1)."""
    out = []
    for d in parsed.documents:
        if not d.container_no:
            continue
        out.append(
            {
                "container_no": d.container_no,
                "pi_number": d.pi_number,
                "line_products": [
                    (known.get(ln.item_code.upper()) or {}).get("id") for ln in d.lines
                ],
            }
        )
    return out


def _pl_match_blocks(parsed: PackingReadResult, known: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-container which products a packing-list block's lines resolved to - the set a
    PI document's own lines are matched against (S8, review round 1)."""
    out = []
    for b in parsed.blocks:
        if not b.container_no:
            continue
        out.append(
            {
                "container_no": b.container_no,
                "products": {
                    pid
                    for ln in b.lines
                    if (pid := (known.get(ln.item_code.upper()) or {}).get("id"))
                },
            }
        )
    return out


def _header_of(
    pi: Optional[ProformaReadResult], pl: Optional[PackingReadResult]
) -> dict[str, Any]:
    first_doc = pi.documents[0] if pi and pi.documents else None
    first_block = pl.blocks[0] if pl and pl.blocks else None
    return {
        "pi_number": first_doc.pi_number if first_doc else None,
        "invoice_date": (
            first_doc.invoice_date.isoformat() if first_doc and first_doc.invoice_date else None
        ),
        "consignee": (first_doc.consignee if first_doc else None) or (
            first_block.consignee if first_block else None
        ),
        "shipper": (pi.shipper if pi else None) or (pl.shipper if pl else None),
        # Q1 ruling: `提单号` (`bl_no`) fills the SO field, never `bill_of_lading_number`.
        "so_ref": (first_doc.bl_no if first_doc else None) or (
            first_block.bl_no if first_block else None
        ),
    }


def _file_preview(db: Session, name: str, data: bytes) -> dict[str, Any]:
    kind = classify(data, db)
    if kind is None:
        return {
            "name": name,
            "kind": "unreadable",
            "blocks": [],
            "header": _header_of(None, None),
            "unmatched": [],
            "errors": ["Could not tell whether this is a proforma invoice or a packing list."],
            "footer_note": None,
        }

    pi_result: Optional[ProformaReadResult] = None
    pl_result: Optional[PackingReadResult] = None
    errors: list[str] = []
    unmatched: list[str] = []
    known_pi: dict[str, Any] = {}
    known_pl: dict[str, Any] = {}

    if kind in ("proforma_invoice", "combined"):
        pi_resolver = AliasResolver.for_doc_type(db, PI_DOC_TYPE)
        pi_result = read_proforma_invoice(data, pi_resolver)
        if not pi_result.ok:
            errors.append(
                "This file has no "
                + ", ".join(pi_result.missing_columns or ["invoice"])
                + " column."
                if pi_result.missing_columns
                else "No proforma invoice was found in this file."
            )
        else:
            known_pi = proforma_invoice_service._products_by_code(
                db, {ln.item_code for d in pi_result.documents for ln in d.lines}
            )
            unmatched += sorted(
                {
                    ln.item_code
                    for d in pi_result.documents
                    for ln in d.lines
                    if ln.item_code.upper() not in known_pi
                }
            )

    if kind in ("packing_list", "combined"):
        pl_resolver = AliasResolver.for_doc_type(db, PL_DOC_TYPE)
        pl_result = read_packing_list(data, pl_resolver)
        if not pl_result.ok:
            errors.append(
                "This file has no "
                + ", ".join(pl_result.missing_columns or ["container block"])
                + " column."
                if pl_result.missing_columns
                else "No container block was found in this file."
            )
        else:
            known_pl = packing_list_service._products_by_code(
                db, {ln.item_code for b in pl_result.blocks for ln in b.lines}
            )
            unmatched += sorted(
                {
                    ln.item_code
                    for b in pl_result.blocks
                    for ln in b.lines
                    if ln.item_code.upper() not in known_pl
                }
            )

    translations = _translate_preview_texts(db, pi_result, pl_result, known_pi, known_pl)

    blocks = (
        _pi_blocks(pi_result, known_pi, translations) if pi_result and pi_result.ok else []
    ) + (
        _pl_blocks(pl_result, known_pl, translations) if pl_result and pl_result.ok else []
    )

    # The `备注：` footer (R13) applies to the whole file, not one block - shown once
    # here rather than repeated inside every block's own notes, even though every
    # shipment this file creates stores it (`packing_list_service._block_notes`).
    footer_note = (
        _text_item(pl_result.footer_notes, translations)
        if pl_result and pl_result.ok
        else None
    )

    return {
        "name": name,
        "kind": kind if not errors else "unreadable",
        "blocks": blocks,
        "header": _header_of(pi_result, pl_result),
        "unmatched": sorted(set(unmatched))[:200],
        "errors": errors,
        "footer_note": footer_note,
        # Popped by `preview()` before the response goes out - kept OFF the block dicts
        # above so a PI-shaped block can never also be read as a PL-shaped one (S8): the
        # two used to share one flat `blocks` list, keyed only by the FILE's kind, so a
        # combined file's own PI block landed in `pl_blocks` too (and vice versa) and
        # matched against itself.
        "_pi_match": _pi_match_blocks(pi_result, known_pi) if pi_result and pi_result.ok else [],
        "_pl_match": _pl_match_blocks(pl_result, known_pl) if pl_result and pl_result.ok else [],
    }


def preview(
    db: Session,
    files: list[tuple[str, bytes]],
    *,
    supplier_id: Optional[str] = None,
    currency: Optional[str] = None,
) -> dict[str, Any]:
    """What each file is, and what it would create - writes nothing."""
    if supplier_id:
        assert_supplier(db, supplier_id)

    out_files = [_file_preview(db, name, data) for name, data in files]

    # Price matches: a PI document and a PL block sharing a container in THIS batch.
    # Uploaded separately (PL after PI, PI after PL) is answered by `apply`'s own DB-wide
    # match, not here - the preview only describes what THIS upload states about itself.
    # Drawn from `_pi_match`/`_pl_match` (popped off each file below), never from the
    # display `blocks` list - a combined file's PI part and PL part are TAGGED by which
    # helper built them, so one can never be read back as the other and matched against
    # itself (S8, review round 1).
    pi_entries = [e for f in out_files for e in f.pop("_pi_match")]
    pl_entries = [e for f in out_files for e in f.pop("_pl_match")]

    price_matches: list[dict[str, Any]] = []
    for pi in pi_entries:
        for pl in pl_entries:
            if pl["container_no"] != pi["container_no"]:
                continue
            products = pl["products"]
            matched = sum(1 for pid in pi["line_products"] if pid and pid in products)
            price_matches.append(
                {
                    "container_no": pi["container_no"],
                    "pi_number": pi["pi_number"],
                    "matched_lines": matched,
                    "unmatched_lines": len(pi["line_products"]) - matched,
                }
            )

    return {"files": out_files, "price_matches": price_matches}


def _match_prices(db: Session, *, supplier_id: str) -> int:
    """Copy proforma-invoice prices onto the packing-list lines they match, by PRODUCT, for
    every container this supplier holds on both sides (R14). Mirrors
    `convert_to_draft_shipment`'s own semantics rather than a shape of its own (review
    round 1, captain's ruling): `qty` on the link is how much is on THIS shipment line,
    never the PI line's own quantity (which may span more than one container); a PI line
    with no shipment line to bind to still gets a row, `unmatched_reason` set, so the PI
    detail page can say where it went; a container carrying TWO shipment lines for the same
    product (rare - two blocks of one container each writing it) consumes them in order,
    so a second PI line naming that product takes the SECOND line rather than the same one
    every time. Idempotent: ANY existing row for a PI line - matched or unmatched - is a
    recorded outcome and is never written again, same rule `convert_to_draft_shipment` uses
    (and the reason a PI placed through this path is correctly refused by that function and
    dropped from its own revision candidates - the outcome here is exactly as permanent).
    """
    from app.models.procurement import InboundShipment, InboundShipmentLine
    from app.models.scm import ProformaInvoice, ProformaInvoiceLine, ProformaInvoiceShipmentLink
    from app.services.procurement_service import _container_match_key

    invoices = (
        db.query(ProformaInvoice).filter(ProformaInvoice.supplier_id == supplier_id).all()
    )
    if not invoices:
        return 0
    shipments = (
        db.query(InboundShipment).filter(InboundShipment.supplier_id == supplier_id).all()
    )
    if not shipments:
        return 0

    by_container: dict[str, list[InboundShipment]] = {}
    for s in shipments:
        key = _container_match_key(s.shipping_container_number)
        if key:
            by_container.setdefault(key, []).append(s)

    # ANY existing row - matched (a real link) or skipped (`unmatched_reason` set) - is a
    # recorded outcome, not only a matched one; re-checking every apply would otherwise
    # write a second `unmatched_reason` row for the same line on every subsequent upload.
    already_linked = {
        str(r[0]) for r in db.query(ProformaInvoiceShipmentLink.proforma_invoice_line_id).all()
    }

    links_written = 0
    for inv in invoices:
        key = _container_match_key(inv.container_ref)
        if not key:
            continue
        candidates = by_container.get(key)
        if not candidates:
            continue
        pi_lines = (
            db.query(ProformaInvoiceLine)
            .filter(ProformaInvoiceLine.invoice_id == inv.id, ProformaInvoiceLine.product_id.isnot(None))
            .order_by(ProformaInvoiceLine.line_no)
            .all()
        )
        if not pi_lines:
            continue
        for shipment in candidates:
            # Consumed in order (`list.pop(0)`, below) - a second shipment line for the
            # same product takes the NEXT PI line naming it, not the first one twice.
            lines_by_product: dict[str, list[InboundShipmentLine]] = {}
            for ln in (
                db.query(InboundShipmentLine)
                .filter(InboundShipmentLine.shipment_id == shipment.id)
                .order_by(InboundShipmentLine.created_at, InboundShipmentLine.id)
                .all()
            ):
                if ln.product_id:
                    lines_by_product.setdefault(str(ln.product_id), []).append(ln)

            for pi_line in pi_lines:
                if str(pi_line.id) in already_linked:
                    continue
                targets = lines_by_product.get(str(pi_line.product_id))
                if not targets:
                    db.add(
                        ProformaInvoiceShipmentLink(
                            id=str(uuid.uuid4()),
                            proforma_invoice_id=inv.id,
                            proforma_invoice_line_id=pi_line.id,
                            inbound_shipment_id=shipment.id,
                            inbound_shipment_line_id=None,
                            unmatched_reason=(
                                "No shipment line for this product on this container."
                            ),
                        )
                    )
                    already_linked.add(str(pi_line.id))
                    continue
                target = targets.pop(0)
                if pi_line.unit_price is not None:
                    target.unit_cost = pi_line.unit_price
                    target.currency = inv.currency
                db.add(
                    ProformaInvoiceShipmentLink(
                        id=str(uuid.uuid4()),
                        proforma_invoice_id=inv.id,
                        proforma_invoice_line_id=pi_line.id,
                        inbound_shipment_id=shipment.id,
                        inbound_shipment_line_id=target.id,
                        # How much is on THIS shipment - the target line's OWN quantity,
                        # not the PI line's (which is not split here, but may still name
                        # more than what a single container actually carries).
                        qty=target.quantity_shipped,
                    )
                )
                already_linked.add(str(pi_line.id))
                links_written += 1
    if links_written:
        db.flush()
    return links_written


def apply(
    db: Session,
    files: list[tuple[str, bytes, Optional[str]]],
    *,
    supplier_id: str,
    currency: Optional[str] = None,
    actor_id: Optional[str] = None,
    actor_name: Optional[str] = None,
    translations: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Proforma invoices first, then packing lists, then price links (R12).

    `files` is `[(filename, data, content_type)]`. Refuses the WHOLE upload when any file is
    unclassifiable, named, rather than silently applying the others and leaving the operator
    to notice one file never showed up.

    `translations` (R16) is `[{source_text, target_text}]` off the preview's edited
    cells - written as MANUAL rows FIRST, before `packing_list_service.apply` runs its
    own translate-and-compose pass, so an edit made in the preview is what a remark or
    a note is stored with, never the AI's unedited guess.
    """
    assert_supplier(db, supplier_id)
    if translations:
        translation_service.remember(db, translations, user_id=actor_id)

    kinds = [(name, data, ctype, classify(data, db)) for name, data, ctype in files]
    unreadable = [name for name, _d, _c, kind in kinds if kind is None]
    if unreadable:
        raise AppException(
            422,
            "Could not tell whether "
            + (unreadable[0] if len(unreadable) == 1 else f"{len(unreadable)} files")
            + " state a proforma invoice or a packing list: "
            + ", ".join(unreadable),
            detail="files",
        )

    proforma_invoice_ids: list[str] = []
    shipment_ids: list[str] = []
    attachment_ids: list[str] = []
    # A COMBINED file is one upload, so it is filed in Drive ONCE - by name, so the packing
    # list loop below can bind the shipment it creates to the SAME attachment rather than
    # filing the same bytes a second time under a second type (S7, review round 1).
    filed_attachment_by_name: dict[str, str] = {}

    for name, data, ctype, kind in kinds:
        if kind not in ("proforma_invoice", "combined"):
            continue
        result = proforma_invoice_service.apply(
            db, data, supplier_id=supplier_id, currency=currency, source_ref=name,
            actor=actor_name,
        )
        proforma_invoice_ids += [r["invoice_id"] for r in result.get("results", [])]
        attachment_id = packing_list_service.file_supplier_document(
            db, data=data, filename=name, content_type=ctype, actor_id=actor_id,
            type_code=_PROFORMA_TYPE_CODE, type_name=_PROFORMA_TYPE_NAME,
        )
        if attachment_id:
            attachment_ids.append(attachment_id)
            filed_attachment_by_name[name] = attachment_id

    for name, data, ctype, kind in kinds:
        if kind not in ("packing_list", "combined"):
            continue
        already_filed = filed_attachment_by_name.get(name)
        result = packing_list_service.apply(
            db, data, supplier_id=supplier_id, currency=currency, source_ref=name,
            content_type=ctype, attachment_id=already_filed,
            file_in_drive=already_filed is None, actor_id=actor_id,
        )
        for r in result.get("results", []):
            if r.get("shipment_id"):
                shipment_ids.append(r["shipment_id"])

    if shipment_ids:
        from app.models.procurement import InboundShipment

        for row in (
            db.query(InboundShipment.attachment_id)
            .filter(InboundShipment.id.in_(shipment_ids), InboundShipment.attachment_id.isnot(None))
            .all()
        ):
            attachment_ids.append(str(row[0]))

    links_written = _match_prices(db, supplier_id=supplier_id)

    return {
        "proforma_invoice_ids": sorted(set(proforma_invoice_ids)),
        "shipment_ids": sorted(set(shipment_ids)),
        "links_written": links_written,
        "attachment_ids": sorted(set(attachment_ids)),
    }
