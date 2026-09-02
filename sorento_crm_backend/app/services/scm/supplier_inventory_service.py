"""Hold one supplier's current stock list, so a container can be planned against it.

A SNAPSHOT, replaced whole on every upload. The alternative - merging the new file into the
old rows - keeps an item the supplier no longer lists as loadable stock forever, and the first
symptom is a container planned around something that is not in their warehouse. Replacement is
stated in the result (`rows_replaced`) rather than done quietly, because it is the one
destructive thing this upload does.

A snapshot per PLAN since S6, when the upload names one (`loading_plan_id`); per supplier when
it does not, which is the standalone stock-list page. It was per supplier alone, and that is
what let a plan started with no file at all run on a stock list somebody had uploaded from a
different plan for the same supplier - while its own subtitle read "No file".

Which supplier the file describes cannot be derived: the sheet carries model numbers and
quantities, never the name of who wrote it. So it is asked for, once, in the dialog - the only
question this upload puts to the user.

Products are RESOLVED, never created (the rule the Order Inquiry feed established): an
unmatched model number is real stock at the supplier, so the row is kept and reported, but it
cannot join a loading plan, whose lines hang off our own purchase-order lines.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.scm import SupplierInventory
from app.services.scm.supplier_inventory_reader import InventoryReadResult, read_workbook
from app.services.scm.supplier_scope import (
    supplier_check as _supplier_check,
    supplier_mismatch_warning as _supplier_mismatch_warning,
)
from app.services.scm.upload_validation import envelope, named

logger = logging.getLogger(__name__)

SOURCE_SYSTEM = "scm_supplier_inventory"

#: The entity_type on the `attachments` row that holds the supplier's OWN sheet, keyed by
#: entity_id=supplier_id. Same generic table Resource Management uses, so it gets the same
#: preview/download endpoints for free rather than a bespoke viewer for one xlsx a week.
STOCK_LIST_ENTITY_TYPE = "supplier_stock_list"

#: How many sample rows the preview shows. Enough to recognise the file, short enough to read.
_SAMPLE = 25


def _uuid() -> str:
    return str(uuid.uuid4())


def _parse(db: Session, data: bytes) -> InventoryReadResult:
    return read_workbook(data, db=db)


def _products_by_code(
    db: Session, codes: set[str], *, supplier_id: Optional[str] = None,
    remember: bool = True, actor: Optional[str] = None,
) -> dict[str, dict]:
    """What each supplier code means - a product, or since R19 a product SET.

    `{code: {"product_id": ..., "product_set_id": ...}}`, exactly one of the two set. A dict
    rather than a bare id because the supplier sells the whole WC: `CWC605-RL` is our SET,
    no product carries that code, and a mapping that could only hold a product id had
    nowhere to put the answer.

    Through the shared ladder rather than an exact match: the supplier writes their own
    spelling - reordered tokens, a trap size ours omits - and 79 codes on the uploaded
    JINBAICHUAN list bound to nothing until this went through `supplier_code_matcher`.
    `supplier_id` is what makes an alias readable at all, since an alias belongs to the
    supplier who wrote the code; without one this falls back to exact, which is what a
    preview with no supplier chosen can honestly answer.
    """
    if not codes:
        return {}
    if not supplier_id:
        rows = (
            db.query(Product.product_code, Product.id)
            .filter(Product.product_code.in_(list(codes)))
            .all()
        )
        return {
            str(code): {"product_id": str(pid), "product_set_id": None}
            for code, pid in rows
        }

    from app.services.scm.supplier_code_matcher import resolve

    return {
        code: {"product_id": match.product_id, "product_set_id": match.product_set_id}
        for code, match in resolve(
            db, supplier_id, codes, remember=remember, actor=actor
        ).items()
    }


def _supplier_label(db: Session, supplier_id: str) -> Optional[str]:
    row = db.execute(
        text("SELECT supplier_name FROM suppliers WHERE id = :i"), {"i": supplier_id}
    ).first()
    return row[0] if row else None


def _summarise(
    db: Session, parsed: InventoryReadResult, supplier_id: Optional[str] = None
) -> dict[str, Any]:
    """What the file holds, described. `rows` is what the verdict card calls "L rows" and
    `items_unmatched` is its "U codes unknown" (AC-G4) - both already computed below.
    `supplier_check` (AC-G3) is `{letterhead, chosen_supplier_name, other_supplier_name |
    null}`, or `None` when the file states no letterhead above its header row.
    """
    codes = {r.item_code for r in parsed.rows}
    known = _products_by_code(db, codes, supplier_id=supplier_id, remember=False)
    unmatched = sorted(c for c in codes if c not in known)
    unmeasured = [r.item_code for r in parsed.rows if r.cbm_per_unit is None]
    packed = sum(r.qty_packed for r in parsed.rows)
    unfinished = sum(r.qty_unfinished for r in parsed.rows)
    return {
        "rows": len(parsed.rows),
        "items_matched": len(codes) - len(unmatched),
        "items_unmatched": len(unmatched),
        "unmatched_item_codes": unmatched[:50],
        "qty_packed": packed,
        "qty_unfinished": unfinished,
        # Loadable volume is what the plan spends, so it is stated here rather than left to be
        # discovered when a plan comes back half empty.
        "loadable_cbm": round(
            sum(
                (r.cbm_per_unit or 0) * r.qty_packed
                for r in parsed.rows
                if r.cbm_per_unit is not None
            ),
            3,
        ),
        "items_unmeasured": len(unmeasured),
        "unmeasured_item_codes": sorted(set(unmeasured))[:50],
        "unmapped_headers": parsed.unmapped_headers,
        "unreadable_rows": len(parsed.problems),
        "supplier_check": _supplier_check(db, parsed.letterhead, supplier_id=supplier_id),
    }


def preview(db: Session, data: bytes, *, supplier_id: str) -> dict:
    """What the file says, and what it would replace, before anything is written."""
    parsed = _parse(db, data)
    summary = _summarise(db, parsed, supplier_id) if parsed.ok else {}
    held = (
        db.query(SupplierInventory)
        .filter(SupplierInventory.supplier_id == supplier_id)
        .count()
    )
    return {
        "readable": parsed.ok,
        "missing_columns": parsed.missing_columns,
        "problems": [{"row": p.row_number, "reason": p.reason} for p in parsed.problems[:50]],
        "supplier_id": supplier_id,
        "supplier_name": _supplier_label(db, supplier_id),
        "rows_held_now": held,
        "sample": [
            {
                "item_code": r.item_code,
                "product_name": r.product_name,
                "qty_packed": r.qty_packed,
                "qty_unfinished": r.qty_unfinished,
                "cbm_per_unit": r.cbm_per_unit,
            }
            for r in parsed.rows[:_SAMPLE]
        ],
        "summary": summary,
    }


def validate(db: Session, data: bytes, *, supplier_id: str) -> dict:
    """The Test verdict: the same read `apply` performs, with nothing written."""
    parsed = _parse(db, data)
    if not parsed.ok:
        missing = ", ".join(parsed.missing_columns)
        reason = (
            f"the file has no {missing} column"
            if parsed.missing_columns
            else "the file could not be read"
        )
        problems = [reason] + [f"row {p.row_number}: {p.reason}" for p in parsed.problems[:5]]
        return envelope(ok=False, problems=problems, warnings=[], summary={})

    summary = _summarise(db, parsed, supplier_id)
    warnings = [
        named(
            summary["items_unmatched"],
            summary["unmatched_item_codes"],
            one="model number is not in the catalogue, so it cannot be loaded",
            many="model numbers are not in the catalogue, so they cannot be loaded",
        ),
        named(
            summary["items_unmeasured"],
            summary["unmeasured_item_codes"],
            one="row has no volume, so it cannot be fitted to a container",
            many="rows have no volume, so they cannot be fitted to a container",
        ),
        named(
            len(parsed.problems),
            [f"row {p.row_number}" for p in parsed.problems],
            one="row could not be read",
            many="rows could not be read",
        ),
        named(
            len(parsed.unmapped_headers),
            parsed.unmapped_headers,
            one="column is not recognised and will be ignored",
            many="columns are not recognised and will be ignored",
        ),
    ]
    mismatch = _supplier_mismatch_warning(summary.get("supplier_check"))
    if mismatch:
        warnings.append(mismatch)
    if not summary["rows"]:
        return envelope(
            ok=False,
            problems=["the file has a header but no stock rows"],
            warnings=[],
            summary=summary,
        )
    return envelope(ok=True, problems=[], warnings=warnings, summary=summary)


def apply(
    db: Session,
    data: bytes,
    *,
    supplier_id: str,
    as_of: Optional[date] = None,
    actor: Optional[str] = None,
    loading_plan_id: Optional[str] = None,
) -> dict:
    """Replace a snapshot with the file. Does not commit.

    WHOSE snapshot is what `loading_plan_id` decides (S6, AC-F3). Stated, this replaces only
    that plan's rows and stamps the new ones with it, so a re-upload into the same plan is
    still a replace and no other plan's figures move. Absent - the standalone stock-list page
    - it keeps the supplier-wide replace it always did.
    """
    parsed = _parse(db, data)
    if not parsed.ok:
        return {
            "readable": False,
            "missing_columns": parsed.missing_columns,
            "rows_written": 0,
            "rows_replaced": 0,
            "summary": {},
        }

    summary = _summarise(db, parsed, supplier_id)
    stamp = as_of or datetime.now().date()
    known = _products_by_code(
        db, {r.item_code for r in parsed.rows}, supplier_id=supplier_id, actor=actor
    )

    scope = db.query(SupplierInventory).filter(
        SupplierInventory.supplier_id == supplier_id
    )
    scope = (
        scope.filter(SupplierInventory.loading_plan_id == loading_plan_id)
        if loading_plan_id
        else scope.filter(SupplierInventory.loading_plan_id.is_(None))
    )
    replaced = scope.delete(synchronize_session=False)
    # The delete has to reach the database before the inserts, or the unique identity index
    # rejects a model number that appears in both the old snapshot and the new one.
    db.flush()

    # A supplier who lists the same model twice (two spec lines of one body) is one row here:
    # the loading plan asks "how many can I load", and two rows would answer it twice.
    merged: dict[str, dict] = {}
    for r in parsed.rows:
        cur = merged.setdefault(
            r.item_code,
            {
                "qty_packed": 0.0,
                "qty_unfinished": 0.0,
                "cbm_per_unit": None,
                "product_name": None,
                "brand": None,
                "spec": None,
                "remark": None,
            },
        )
        cur["qty_packed"] += r.qty_packed
        cur["qty_unfinished"] += r.qty_unfinished
        if cur["cbm_per_unit"] is None and r.cbm_per_unit is not None:
            cur["cbm_per_unit"] = r.cbm_per_unit
        for f in ("product_name", "brand", "spec", "remark"):
            if cur[f] is None:
                cur[f] = getattr(r, f)

    written = 0
    for code, v in merged.items():
        db.add(
            SupplierInventory(
                id=_uuid(),
                supplier_id=supplier_id,
                item_code=code,
                product_id=(known.get(code) or {}).get("product_id"),
                product_set_id=(known.get(code) or {}).get("product_set_id"),
                qty_packed=v["qty_packed"],
                qty_unfinished=v["qty_unfinished"],
                cbm_per_unit=v["cbm_per_unit"],
                product_name=v["product_name"],
                brand=v["brand"],
                spec=v["spec"],
                remark=v["remark"],
                as_of=stamp,
                loading_plan_id=loading_plan_id,
                uploaded_by=actor,
                source_system=SOURCE_SYSTEM,
                source_ref="supplier_inventory",
            )
        )
        written += 1
    db.flush()

    return {
        "readable": True,
        "missing_columns": [],
        "supplier_id": supplier_id,
        "supplier_name": _supplier_label(db, supplier_id),
        "as_of": stamp.isoformat(),
        "rows_written": written,
        "rows_replaced": replaced,
        "duplicate_models_merged": len(parsed.rows) - written,
        "problems": [{"row": p.row_number, "reason": p.reason} for p in parsed.problems[:50]],
        "summary": summary,
    }


def store_stock_list_attachment(
    db: Session,
    file_bytes: Optional[bytes],
    *,
    filename: Optional[str],
    content_type: Optional[str],
    supplier_id: str,
    uploaded_by: Optional[str],
) -> Optional[str]:
    """Keep the supplier's own sheet retrievable, the same way any other resource attachment
    is - so Ms Tee can cross-check the loading plan against it without opening Excel.

    Called AFTER `apply()` has already committed the inventory rows, so a storage hiccup here
    must never turn a successful upload into a failed request (same rule as
    `import_source_store.store_import_source_file`). On any error this logs and returns
    None; there is nothing left for the caller to roll back.
    """
    if not file_bytes:
        return None
    try:
        from app.schemas.resources import AttachmentCreate
        from app.services.resources_service import AttachmentService
        from app.services.storage_router import (
            cdn_base_url,
            default_provider,
            get_backend,
            sanitize_storage_filename,
        )

        display_name = (filename or "").strip() or "stock_list.xlsx"
        original_filename = sanitize_storage_filename(display_name)
        attachment_id = _uuid()
        provider = default_provider()
        key = f"{STOCK_LIST_ENTITY_TYPE}/{supplier_id}/{attachment_id}/{original_filename}"
        s3_key, _ = get_backend(provider).upload_file(
            file_content=file_bytes,
            file_path=key,
            content_type=content_type or "application/octet-stream",
        )
        stored_file_path = cdn_base_url(provider, s3_key)

        service = AttachmentService(db)
        attachment = service.create_attachment(
            AttachmentCreate(
                id=attachment_id,
                attachment_type_id=None,
                original_filename=original_filename,
                stored_filename=display_name,
                file_path=stored_file_path,
                file_size_bytes=len(file_bytes),
                mime_type=content_type or "application/octet-stream",
                entity_type=STOCK_LIST_ENTITY_TYPE,
                entity_id=supplier_id,
                storage_provider=provider,
            ),
            uploaded_by,
        )
        return str(attachment.id)
    except Exception as exc:  # noqa: BLE001 - best-effort, the apply already committed
        # A failed insert/flush leaves the session's transaction dead until rolled back - the
        # caller's `db` must come out of this usable, since the apply already committed on it.
        db.rollback()
        logger.warning(
            "store_stock_list_attachment: failed to retain the stock list for supplier %s "
            "(%s); the inventory apply already succeeded and continues without it",
            supplier_id,
            exc,
        )
        return None


def latest_stock_list_attachment(db: Session, *, supplier_id: str) -> Optional[dict]:
    """The most recently stored copy of the supplier's own sheet, if one was retained."""
    from app.models.resources import Attachment

    row = (
        db.query(Attachment)
        .filter(
            Attachment.entity_type == STOCK_LIST_ENTITY_TYPE,
            Attachment.entity_id == supplier_id,
            Attachment.is_deleted.is_(False),
        )
        .order_by(Attachment.uploaded_at.desc())
        .first()
    )
    if row is None:
        return None
    return {
        "attachment_id": str(row.id),
        "filename": row.stored_filename or row.original_filename,
        "uploaded_at": row.uploaded_at,
    }
