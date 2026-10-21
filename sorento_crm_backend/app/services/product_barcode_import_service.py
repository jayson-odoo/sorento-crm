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
import hashlib
import hmac
import io
import re
import zipfile
from typing import Any, Iterable, Optional

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models.base import get_company_scope
from app.models.company import Company
from app.models.product import Product
from app.services.audit_service import audit_event

MAX_BARCODE_LEN = 100  # products.barcode is String(100)
_MAX_UPLOAD_BYTES = 25 * 1024 * 1024
ALLOWED_EXTENSIONS = (".xlsx", ".csv")
#: Title lines above the table are allowed; the header is the first row naming both columns.
_HEADER_SCAN_ROWS = 20
_FLUSH_CHUNK = 1000
#: Excel's own row limit; a sheet reaching past it is malformed (openpyxl read-only would
#: fill the gap with empty rows, so one cell at r=30,000,000 costs seconds of CPU).
_MAX_SHEET_ROWS = 1_048_576
#: Non-empty data rows per file. The catalogue is ~12k products.
_MAX_DATA_ROWS = 50_000
#: Sum of the workbook archive's uncompressed members; guards a zip bomb under 25 MB.
_MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024

# Normalized header (lowercase, non-alphanumerics collapsed to one space).
_CODE_HEADERS = (
    "product code", "item code", "code", "stock code", "sku", "product", "item", "item no",
    "itemcode", "productcode",
)
_BARCODE_HEADERS = (
    "barcode", "bar code", "ean", "ean13", "ean 13", "upc", "gtin", "barcode no",
)
_NOTE_HEADERS = ("note", "notes", "remark", "remarks", "comment", "comments")
#: A header naming one of these is never the code or barcode column, however it starts:
#: the owner's sheet carries "Barcode Image" (pictures, empty cells) beside "Barcode (EAN-13)".
_NEVER_WORDS = {"image", "images", "picture", "photo", "img", "name", "description", "desc"}

#: Text Excel writes for a long number it re-saved as CSV ("9.55103E+12"); the digits are gone.
_SCIENTIFIC = re.compile(r"^\d+(?:\.\d+)?[eE]\+?\d+$")

#: Statuses that write. Everything else is skipped by apply.
WRITES = ("new", "change")
STATUSES = (
    "new", "change", "same", "unknown_code", "ambiguous_code", "repeated_code",
    "blank_barcode", "too_long", "scientific",
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


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _guarded(rows: Iterable[tuple]) -> Iterable[tuple]:
    """Rows with the sheet-length cap applied and any reader failure turned into a 400."""
    try:
        for idx, row in enumerate(rows, start=1):
            if idx > _MAX_SHEET_ROWS:
                raise _bad_request("This sheet goes past row 1,048,576, the most Excel allows.")
            yield row
    except HTTPException:
        raise
    except Exception as exc:
        raise _bad_request("This file could not be read.") from exc


def _sheets(data: bytes, name: str) -> Iterable[Iterable[tuple]]:
    """Each sheet's rows. A workbook is searched sheet by sheet for the header row."""
    if name.endswith(".csv"):
        text_data = data.decode("utf-8-sig", errors="replace")
        return [_guarded(tuple(r) for r in csv.reader(io.StringIO(text_data)))]
    import openpyxl

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            if sum(i.file_size for i in zf.infolist()) > _MAX_UNCOMPRESSED_BYTES:
                raise _bad_request("This workbook is too large to read.")
    except HTTPException:
        raise
    except Exception as exc:
        raise _bad_request("This file could not be read as an Excel workbook.") from exc
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    except Exception as exc:
        raise _bad_request("This file could not be read as an Excel workbook.") from exc
    return [_guarded(ws.iter_rows(values_only=True)) for ws in wb.worksheets]


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


def _find_columns(row: tuple) -> tuple[Optional[int], Optional[int], Optional[int]]:
    """(code, barcode, note) column positions. An exact alias wins over one the header only
    starts with ("Barcode (EAN-13)"), and an earlier alias over a later one, so "Product
    Code" beats a bare "Code"."""
    normed = [_norm_header(c) for c in row]
    usable = [i for i, h in enumerate(normed) if h and not (set(h.split()) & _NEVER_WORDS)]

    def pick(names: tuple[str, ...], exclude: set[int]) -> Optional[int]:
        for n in names:
            for i in usable:
                if i not in exclude and normed[i] == n:
                    return i
        for n in names:
            for i in usable:
                if i not in exclude and normed[i].startswith(n + " "):
                    return i
        return None

    code = pick(_CODE_HEADERS, set())
    barcode = pick(_BARCODE_HEADERS, {code} if code is not None else set())
    taken = {i for i in (code, barcode) if i is not None}
    note = pick(_NOTE_HEADERS, taken)
    return code, barcode, note


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


def _barcode_holders(db: Session, barcodes: set[str]) -> dict[str, dict[str, str]]:
    """Products already holding each barcode, as {barcode: {product id: product code}}."""
    out: dict[str, dict[str, str]] = {}
    keys = list(barcodes)
    for i in range(0, len(keys), 1000):
        rows = (
            db.query(func.btrim(Product.barcode), Product.id, Product.product_code)
            .filter(func.btrim(Product.barcode).in_(keys[i:i + 1000]))
            .all()
        )
        for bc, pid, code in rows:
            out.setdefault(bc, {})[str(pid)] = code
    return out


def _companies_in_scope(db: Session) -> list[str]:
    """Names of the companies this import reads and writes, for the dialog's "Importing
    into" line. The owner runs the same file once per company (SRT, then MCH), so which
    one is active has to be on screen before anything is written."""
    scope = get_company_scope(db)
    query = db.query(Company.name).order_by(Company.name)
    if isinstance(scope, frozenset):
        if not scope:
            return []
        query = query.filter(Company.id.in_(list(scope)))
    elif scope is not None:  # UNSET: no request scope, nothing to name
        return []
    return [n for (n,) in query.all()]


def resolve(db: Session, data: bytes, name: str) -> dict[str, Any]:
    """Classify every line of the file. Writes nothing; `_writes` carries what apply would."""
    code_col = barcode_col = note_col = None
    header: tuple = ()
    header_row = 0
    rows: Iterable[tuple] = iter(())
    half: tuple[Optional[int], Optional[int]] = (None, None)
    for sheet in _sheets(data, name):
        rows = iter(sheet)
        for idx, row in enumerate(rows, start=1):
            if idx > _HEADER_SCAN_ROWS:
                break
            c, b, n = _find_columns(row or ())
            if c is not None and b is not None:
                code_col, barcode_col, note_col, header, header_row = c, b, n, row, idx
                break
            if (c is not None or b is not None) and half == (None, None):
                # Remember a half-match so the message can say which column is missing.
                half = (c, b)
        if header_row:
            break
    if header_row == 0:
        code_col, barcode_col = half
        missing = [n for n, col in (("product code", code_col), ("barcode", barcode_col))
                   if col is None]
        return {
            "readable": False, "missing_columns": missing or ["product code", "barcode"],
            "code_column": None, "barcode_column": None, "note_column": None, "total_rows": 0,
            "companies": _companies_in_scope(db),
            "counts": {k: 0 for k in STATUSES + WARNINGS}, "rows": [], "_writes": [],
        }

    def at(row: tuple, col: Optional[int]) -> str:
        return _cell(row[col]) if col is not None and col < len(row) else ""

    parsed: list[tuple[int, str, str, str]] = []
    for idx, row in enumerate(rows, start=header_row + 1):
        row = row or ()
        code, barcode = at(row, code_col), at(row, barcode_col)
        if not code and not barcode:
            continue
        parsed.append((idx, code, barcode, at(row, note_col)))
        if len(parsed) > _MAX_DATA_ROWS:
            raise _bad_request("This file has more than 50,000 rows. Split it and import in parts.")

    products = _products_by_code(db, {c.upper() for _, c, _, _ in parsed if c})
    holders = _barcode_holders(db, {b for _, _, b, _ in parsed if b and len(b) <= MAX_BARCODE_LEN})

    seen_codes: dict[str, int] = {}
    out_rows: list[dict[str, Any]] = []
    for row_no, code, barcode, note in parsed:
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
        elif _SCIENTIFIC.match(barcode):
            st = "scientific"
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
            "_product": product,
            "old_barcode": old,
            "new_barcode": barcode or None,
            "status": st,
            "warnings": [],
            "repeated_of_row": seen_codes.get(key) if st == "repeated_code" else None,
            "duplicate_of": [],
            "note": note or None,
        })

    # Warnings only on rows that carry a usable barcode for a known product.
    candidates = [r for r in out_rows if r["status"] in ("new", "change", "same")]
    in_file: dict[str, dict[str, str]] = {}
    for r in candidates:
        in_file.setdefault(r["new_barcode"], {})[r["product_id"]] = r["product_code"]
    for r in candidates:
        sharing = {**holders.get(r["new_barcode"], {}), **in_file[r["new_barcode"]]}
        sharing.pop(r["product_id"], None)
        if sharing:
            r["warnings"].append("duplicate")
            r["duplicate_of"] = sorted(sharing.values())[:5]
        if not is_valid_ean13(r["new_barcode"]):
            r["warnings"].append("not_ean13")

    counts = {k: 0 for k in STATUSES + WARNINGS}
    for r in out_rows:
        counts[r["status"]] += 1
        for w in r["warnings"]:
            counts[w] += 1
    writes = [(r["_product"], r["new_barcode"]) for r in out_rows if r["status"] in WRITES]
    for r in out_rows:
        r.pop("product_id")
        r.pop("_product")
    return {
        "readable": True,
        "missing_columns": [],
        "companies": _companies_in_scope(db),
        "code_column": _cell(header[code_col]),
        "barcode_column": _cell(header[barcode_col]),
        "note_column": _cell(header[note_col]) if note_col is not None else None,
        "total_rows": len(out_rows),
        "counts": counts,
        "rows": out_rows,
        "_writes": writes,
    }


def _scope_marker(db: Session) -> str:
    """The caller's company scope as text, so a token minted in one company is void in another."""
    scope = get_company_scope(db)
    if isinstance(scope, frozenset):
        return ",".join(sorted(str(c) for c in scope))
    return "all" if scope is None else "unset"


def preview_token(data: bytes, user_id: Any, db: Session) -> str:
    """Proof that this user previewed exactly these bytes in this company scope. Apply
    refuses a file without one, so nothing is written that nobody has seen the per-row
    statuses of."""
    digest = hashlib.sha256(data).hexdigest()
    key = (settings.jwt_secret or "").encode()
    msg = f"barcode-import:{user_id}:{_scope_marker(db)}:{digest}"
    return hmac.new(key, msg.encode(), hashlib.sha256).hexdigest()


def check_preview_token(data: bytes, user_id: Any, token: Optional[str], db: Session) -> None:
    expected = preview_token(data, user_id, db).encode()
    if not token or not hmac.compare_digest(token.encode(), expected):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Test this file before applying it.",
        )


def preview(db: Session, data: bytes, name: str, user_id: Any = None) -> dict[str, Any]:
    out = resolve(db, data, name)
    out.pop("_writes")
    out["preview_token"] = preview_token(data, user_id, db)
    return out


@audit_event("product.barcode_import")
def apply(db: Session, data: bytes, name: str) -> dict[str, Any]:
    """Write the new and changed barcodes. Does not commit; the route owns the transaction.

    An ORM update per product, so the audit flush listener writes one `product` row each
    with the old and new barcode, labelled with this verb. The bulk ORM paths would not do:
    they itemise only `BULK_AUDIT_CAP` rows per statement. Flushed in chunks so a full
    catalogue (~12k rows) never holds every pending change and audit row at once.
    """
    out = resolve(db, data, name)
    writes = out.pop("_writes")
    for i in range(0, len(writes), _FLUSH_CHUNK):
        for product, barcode in writes[i:i + _FLUSH_CHUNK]:
            product.barcode = barcode
        db.flush()
    out["applied"] = len(writes)
    return out
