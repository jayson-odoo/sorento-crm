"""Bulk-set `products.barcode` from a sheet of product code + barcode (BARCODE-IMPORT).

Plan: documentation/plans/master-data/PLAN-barcode-import-21oct.md

The CRM owns the barcode (AutoCount's push writes it only when non-empty,
`master_ingest_service.py` D14), so this import is the one bulk path that sets it. The full
product bulk import cannot be reused: it needs item_group and rewrites name, brand and price.

Preview and apply run the same `resolve`, so Test and Apply cannot disagree about a file.
Apply writes only `new` and `change` rows; a blank cell never clears a barcode. The barcode is
not unique by design (`app/models/product.py`), so a duplicate is a warning, never a block.
"""
from __future__ import annotations

import csv
import io
import re
from typing import Any, Iterable, Optional

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.product import Product
from app.services.audit_service import audit_event

MAX_BARCODE_LEN = 100  # products.barcode is String(100)
_MAX_UPLOAD_BYTES = 25 * 1024 * 1024
ALLOWED_EXTENSIONS = (".xlsx", ".csv")
#: Title lines above the table are allowed; the header is the first row naming both columns.
_HEADER_SCAN_ROWS = 20

# Normalized header (lowercase, non-alphanumerics collapsed to one space).
_CODE_HEADERS = (
    "product code", "item code", "code", "stock code", "sku", "product", "item", "item no",
    "itemcode", "productcode",
)
_BARCODE_HEADERS = (
    "barcode", "bar code", "ean", "ean13", "ean 13", "upc", "gtin", "barcode no",
)

#: Statuses that write. Everything else is skipped by apply.
WRITES = ("new", "change")
STATUSES = (
    "new", "change", "same", "unknown_code", "ambiguous_code", "repeated_code",
    "blank_barcode", "too_long",
)
WARNINGS = ("duplicate", "not_ean13")


def is_valid_ean13(value: str) -> bool:
    """A checksum-valid EAN-13 (GS1 mod-10), same rule as `lib/dealer-kit/barcode.ts`."""
    v = (value or "").strip()
    if not re.fullmatch(r"\d{13}", v):
        return False
    digits = [int(c) for c in v]
    total = sum(d * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits[:12]))
    return (10 - total % 10) % 10 == digits[12]


async def read_barcode_upload(file: UploadFile) -> tuple[bytes, str]:
    """The uploaded bytes and lowercased name, refused when not .xlsx/.csv, empty or too big."""
    name = (file.filename or "").lower()
    if not name.endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type: {file.filename or 'unknown'}. Upload .xlsx or .csv.",
        )
    if file.size is not None and file.size > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                            detail="The uploaded file exceeds the 25 MB limit.")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="The uploaded file is empty")
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                            detail="The uploaded file exceeds the 25 MB limit.")
    return data, name


def _rows(data: bytes, name: str) -> Iterable[tuple]:
    if name.endswith(".csv"):
        text_data = data.decode("utf-8-sig", errors="replace")
        return (tuple(r) for r in csv.reader(io.StringIO(text_data)))
    import openpyxl

    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="This file could not be read as an Excel workbook.") from exc
    return wb.active.iter_rows(values_only=True)


def _cell(value: Any) -> str:
    """A cell as text. Excel stores a typed-in barcode as a number; keep its digits."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _norm_header(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _cell(value).lower()).strip()


def _find_columns(row: tuple) -> tuple[Optional[int], Optional[int]]:
    normed = [_norm_header(c) for c in row]

    def pick(names: tuple[str, ...]) -> Optional[int]:
        for n in names:  # earlier alias wins, so "Product Code" beats a bare "Code"
            if n in normed:
                return normed.index(n)
        return None

    return pick(_CODE_HEADERS), pick(_BARCODE_HEADERS)


def _products_by_code(db: Session, codes: set[str]) -> dict[str, list[Product]]:
    """Products in the caller's company scope (ORM auto-filter), by trimmed upper code."""
    out: dict[str, list[Product]] = {}
    keys = list(codes)
    for i in range(0, len(keys), 1000):
        rows = (
            db.query(Product)
            .filter(func.upper(func.btrim(Product.product_code)).in_(keys[i:i + 1000]))
            .all()
        )
        for p in rows:
            out.setdefault((p.product_code or "").strip().upper(), []).append(p)
    return out


def _barcode_holders(db: Session, barcodes: set[str]) -> dict[str, set[str]]:
    """Product ids already holding each barcode."""
    out: dict[str, set[str]] = {}
    keys = list(barcodes)
    for i in range(0, len(keys), 1000):
        rows = (
            db.query(func.btrim(Product.barcode), Product.id)
            .filter(func.btrim(Product.barcode).in_(keys[i:i + 1000]))
            .all()
        )
        for bc, pid in rows:
            out.setdefault(bc, set()).add(str(pid))
    return out


def resolve(db: Session, data: bytes, name: str) -> dict[str, Any]:
    """Classify every line of the file. Writes nothing; `_writes` carries what apply would."""
    rows = iter(_rows(data, name))
    code_col = barcode_col = None
    header: tuple = ()
    header_row = 0
    for idx, row in enumerate(rows, start=1):
        if idx > _HEADER_SCAN_ROWS:
            break
        c, b = _find_columns(row or ())
        if c is not None and b is not None:
            code_col, barcode_col, header, header_row = c, b, row, idx
            break
        if c is not None or b is not None:
            # Remember a half-match so the message can say which column is missing.
            code_col, barcode_col = c, b
    if header_row == 0:
        missing = [n for n, col in (("product code", code_col), ("barcode", barcode_col))
                   if col is None]
        return {
            "readable": False, "missing_columns": missing or ["product code", "barcode"],
            "code_column": None, "barcode_column": None, "total_rows": 0,
            "counts": {k: 0 for k in STATUSES + WARNINGS}, "rows": [], "_writes": [],
        }

    parsed: list[tuple[int, str, str]] = []
    for idx, row in enumerate(rows, start=header_row + 1):
        row = row or ()
        code = _cell(row[code_col]) if code_col < len(row) else ""
        barcode = _cell(row[barcode_col]) if barcode_col < len(row) else ""
        if not code and not barcode:
            continue
        parsed.append((idx, code, barcode))

    products = _products_by_code(db, {c.upper() for _, c, _ in parsed if c})
    holders = _barcode_holders(db, {b for _, _, b in parsed if b and len(b) <= MAX_BARCODE_LEN})

    seen_codes: dict[str, int] = {}
    out_rows: list[dict[str, Any]] = []
    for row_no, code, barcode in parsed:
        key = code.upper()
        matches = products.get(key, []) if code else []
        product = matches[0] if len(matches) == 1 else None
        old = (product.barcode or "").strip() or None if product else None
        if not code or not matches:
            st = "unknown_code"
        elif len(matches) > 1:
            st = "ambiguous_code"
        elif key in seen_codes:
            st = "repeated_code"
        elif not barcode:
            st = "blank_barcode"
        elif len(barcode) > MAX_BARCODE_LEN:
            st = "too_long"
        elif old is None:
            st = "new"
        elif old == barcode:
            st = "same"
        else:
            st = "change"
        # A blank first row does not claim the code: a later row for it still writes.
        if code and barcode and key not in seen_codes:
            seen_codes[key] = row_no
        out_rows.append({
            "row": row_no,
            "product_code": product.product_code if product else code,
            "product_name": product.product_name if product else None,
            "product_id": str(product.id) if product else None,
            "old_barcode": old,
            "new_barcode": barcode or None,
            "status": st,
            "warnings": [],
            "repeated_of_row": seen_codes.get(key) if st == "repeated_code" else None,
        })

    # Warnings only on rows that carry a usable barcode for a known product.
    candidates = [r for r in out_rows if r["status"] in ("new", "change", "same")]
    in_file: dict[str, set[str]] = {}
    for r in candidates:
        in_file.setdefault(r["new_barcode"], set()).add(r["product_id"])
    for r in candidates:
        others = (holders.get(r["new_barcode"], set()) | in_file[r["new_barcode"]]) - {r["product_id"]}
        if others:
            r["warnings"].append("duplicate")
        if not is_valid_ean13(r["new_barcode"]):
            r["warnings"].append("not_ean13")

    counts = {k: 0 for k in STATUSES + WARNINGS}
    for r in out_rows:
        counts[r["status"]] += 1
        for w in r["warnings"]:
            counts[w] += 1
    writes = [(r["product_id"], r["new_barcode"]) for r in out_rows if r["status"] in WRITES]
    for r in out_rows:
        r.pop("product_id")
    return {
        "readable": True,
        "missing_columns": [],
        "code_column": _cell(header[code_col]),
        "barcode_column": _cell(header[barcode_col]),
        "total_rows": len(out_rows),
        "counts": counts,
        "rows": out_rows,
        "_writes": writes,
    }


def preview(db: Session, data: bytes, name: str) -> dict[str, Any]:
    out = resolve(db, data, name)
    out.pop("_writes")
    return out


@audit_event("product.barcode_import")
def apply(db: Session, data: bytes, name: str) -> dict[str, Any]:
    """Write the new and changed barcodes. Does not commit; the route owns the transaction.

    An ORM update per product, so the audit flush listener writes one `product` row each
    with the old and new barcode, labelled with this verb.
    """
    out = resolve(db, data, name)
    writes = out.pop("_writes")
    if writes:
        by_id = {
            str(p.id): p
            for p in db.query(Product).filter(Product.id.in_([pid for pid, _ in writes])).all()
        }
        for pid, barcode in writes:
            by_id[pid].barcode = barcode
        db.flush()
    out["applied"] = len(writes)
    return out
