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
from app.services.scm.outstanding_reader import sheet_rows
from app.services.scm.packing_list_reader import DOC_TYPE as PL_DOC_TYPE
from app.services.scm.packing_list_reader import PackingReadResult
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
#: share), which would otherwise misclassify every packing list as combined.
_PI_TITLE_MARKERS = ("发票", "PROFORMA INVOICE")
_PL_TITLE_MARKERS = ("装箱单", "PACKING LIST")
#: How many rows to scan for a title cell - both fixtures state it inside the first 10.
_TITLE_SCAN_ROWS = 15

#: The type each kind is filed under in Drive (R12/lane A's mechanism), looked up the same
#: case-insensitive `code OR type_name` way `packing_list_service.file_supplier_document`
#: already does for the packing list itself.
_PROFORMA_TYPE_CODE = "proforma_invoice"
_PROFORMA_TYPE_NAME = "Proforma Invoice"


def classify(data: bytes) -> Optional[str]:
    """`'proforma_invoice' | 'packing_list' | 'combined' | None` (unreadable/unclassifiable),
    by the file's own title cell. `None` never blocks the OTHER files in a batch - only
    itself, named, in the preview and in `apply`'s refusal."""
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
    kind = classify(data)
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

    # Price matches: a PI block and a PL block sharing a container in THIS batch. Uploaded
    # separately (PL after PI, PI after PL) is answered by `apply`'s own DB-wide match, not
    # here - the preview only describes what THIS upload states about itself.
    price_matches: list[dict[str, Any]] = []
    pi_blocks = [
        (f["name"], b) for f in out_files if f["kind"] in ("proforma_invoice", "combined")
        for b in f["blocks"]
    ]
    pl_blocks = [
        (f["name"], b) for f in out_files if f["kind"] in ("packing_list", "combined")
        for b in f["blocks"]
    ]
    for _pi_name, pi_block in pi_blocks:
        if not pi_block.get("container_no"):
            continue
        for _pl_name, pl_block in pl_blocks:
            if pl_block.get("container_no") != pi_block.get("container_no"):
                continue
            price_matches.append(
                {
                    "container_no": pi_block["container_no"],
                    "pi_number": None,
                    "matched_lines": min(pi_block["line_count"], pl_block["line_count"]),
                    "unmatched_lines": abs(pi_block["line_count"] - pl_block["line_count"]),
                }
            )

    return {"files": out_files, "price_matches": price_matches}


def _match_prices(db: Session, *, supplier_id: str) -> int:
    """Copy proforma-invoice prices onto the packing-list lines they match, by PRODUCT, for
    every container this supplier holds on both sides (R14). Idempotent: a PI line already
    linked to a shipment line is never re-linked, same rule `convert_to_draft_shipment` uses.
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

    already_linked = {
        str(r[0])
        for r in db.query(ProformaInvoiceShipmentLink.proforma_invoice_line_id)
        .filter(ProformaInvoiceShipmentLink.inbound_shipment_line_id.isnot(None))
        .all()
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
            .all()
        )
        if not pi_lines:
            continue
        for shipment in candidates:
            lines_by_product: dict[str, list[InboundShipmentLine]] = {}
            for ln in (
                db.query(InboundShipmentLine)
                .filter(InboundShipmentLine.shipment_id == shipment.id)
                .all()
            ):
                if ln.product_id:
                    lines_by_product.setdefault(str(ln.product_id), []).append(ln)

            for pi_line in pi_lines:
                if str(pi_line.id) in already_linked:
                    continue
                targets = lines_by_product.get(str(pi_line.product_id))
                if not targets:
                    continue
                target = targets[0]
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
                        qty=pi_line.qty,
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

    kinds = [(name, data, ctype, classify(data)) for name, data, ctype in files]
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

    for name, data, ctype, kind in kinds:
        if kind not in ("packing_list", "combined"):
            continue
        result = packing_list_service.apply(
            db, data, supplier_id=supplier_id, currency=currency, source_ref=name,
            content_type=ctype, file_in_drive=True, actor_id=actor_id,
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
