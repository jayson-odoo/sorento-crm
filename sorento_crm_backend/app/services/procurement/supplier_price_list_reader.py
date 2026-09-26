"""Reads a supplier's Excel price list into rows (#1288, Lane A, plan section 5).

Used by both the staff upload (`cost_price_change_service.py`) and, later, the supplier's own
upload (Lane B). Pure and synchronous: no database, no network - a 258-row real file parses in
well under a second (trigger to move this onto the `imports` queue: a real file over 2,000 rows
or a parse over 5 seconds, per the plan).

The reader takes NO `db`, so header aliasing here is a small hardcoded table, not
`app.services.import_alias_service`'s DB-backed `AliasResolver` - the two are shaped alike on
purpose (NFKC-fold, strip-and-lower) but this one never queries `import_field_alias`.
"""
from __future__ import annotations

import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Optional

import openpyxl

from app.services.error_handler import AppException
from app.services.scm.currency_resolution import currency_from_text

_MAX_FILE_BYTES = 25 * 1024 * 1024
#: Exported so the upload/probe routes can bound how much of the multipart body they
#: read off the wire (`file.read(MAX_FILE_BYTES + 1)`) instead of buffering an
#: attacker-sized upload into memory before this module ever gets to check it.
MAX_FILE_BYTES = _MAX_FILE_BYTES
_MAX_ROWS = 5000
_MAX_SHEET_CELLS = 20000
_HEADER_SCAN_ROWS = 20
_MAX_CONSECUTIVE_BLANK_ROWS = 5

#: S2 (security review): the ZIP container's OWN declared sizes, inspected BEFORE
#: openpyxl ever decompresses anything. A small, highly-compressible file (real zero
#: bytes compress ~1000:1) sails through the on-disk `_MAX_FILE_BYTES` cap above and
#: hands openpyxl tens of megabytes to decompress - these two catch that independent
#: of how small the upload looked on the wire.
_MAX_ZIP_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
_MAX_ZIP_COMPRESSION_RATIO = 100
#: An `.xlsx` carrying this member (or declaring a macro-enabled content type) is a
#: macro workbook renamed to look like a plain one - refused outright, never parsed.
_MACRO_MEMBER = "xl/vbaProject.bin"
_MACRO_CONTENT_TYPE_MARKER = b"macroEnabled"

#: Header aliases (plan 5.1's seeded `supplier_price_list` doc_type, reproduced as a static
#: table here since this reader has no `db` to read `import_field_alias` with).
_LINE_NO_ALIASES = {"序号", "no", "s/n", "no."}
_CODE_ALIASES = {"型号", "型號", "model", "item", "code"}
_DESC_ALIASES = {"产品配置", "配置", "description", "specification"}
_PRICE_ALIASES = {"价格", "單價", "单价", "price", "unit price"}

_BRACKET_RE = re.compile(r"^(.*?)\s*[\(（]([^()（）]*)[\)）]\s*$")
_PRICE_WORD_RE = re.compile(r"(?i)\b(rmb|cny|myr|usd)\b")
_PRICE_STRIP_RE = re.compile(r"[¥￥元,\s]")


@dataclass
class PriceListRow:
    sheet: str
    row_no: int
    line_no: Optional[str]
    supplier_code_raw: str
    supplier_code: str
    code_note: Optional[str]
    configuration: Optional[str]
    price: Optional[Decimal]
    flags: set[str] = field(default_factory=set)


@dataclass
class PriceListSheet:
    name: str
    header_row: Optional[int]
    skipped_reason: Optional[str]
    rows: list[PriceListRow]


@dataclass
class PriceListRead:
    sheets: list[PriceListSheet]
    letterhead: list[str]
    #: The currency the price header itself names (`RMB`, `单价(元)`), or None - AC-S1-07.
    header_currency: Optional[str]
    total_rows: int


def _norm_header(value) -> str:
    if value is None:
        return ""
    return unicodedata.normalize("NFKC", str(value)).strip().lower()


def _header_field(value) -> Optional[str]:
    text = _norm_header(value)
    if not text:
        return None
    if text in _LINE_NO_ALIASES:
        return "line_no"
    if any(a in text for a in _PRICE_ALIASES):
        return "price"
    if text in _CODE_ALIASES:
        return "item_code"
    if text in _DESC_ALIASES:
        return "description"
    return None


def clean_code(raw) -> tuple[str, Optional[str]]:
    """NFKC-fold, trim, collapse inner whitespace, split one trailing bracket group off as
    `code_note` (AC-S1-04). The bracket is shown, never matched."""
    if raw is None:
        return "", None
    text = unicodedata.normalize("NFKC", str(raw)).strip()
    text = re.sub(r"\s+", " ", text)
    match = _BRACKET_RE.match(text)
    if match:
        code = match.group(1).strip()
        note = match.group(2).strip() or None
        return code, note
    return text, None


def clean_price(value) -> Optional[Decimal]:
    """Numbers as numbers; strings stripped of currency symbols/words and thousands
    separators, then `Decimal`. Anything unparseable or negative is None (AC-S1-05)."""
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            dec = Decimal(str(value))
        except InvalidOperation:
            return None
        return dec if dec >= 0 else None
    text = unicodedata.normalize("NFKC", str(value)).strip()
    if not text:
        return None
    text = _PRICE_WORD_RE.sub("", text)
    text = _PRICE_STRIP_RE.sub("", text)
    if not text:
        return None
    try:
        dec = Decimal(text)
    except InvalidOperation:
        return None
    return dec if dec >= 0 else None


def _find_header(ws, max_row_cap: int) -> tuple[Optional[int], dict[int, str]]:
    """Row 1 to 20: the first row where at least two of the four fields resolve."""
    limit = min(max_row_cap, _HEADER_SCAN_ROWS)
    for row_idx in range(1, limit + 1):
        field_by_pos: dict[int, str] = {}
        seen_fields: set[str] = set()
        for col_idx in range(1, ws.max_column + 1):
            value = ws.cell(row=row_idx, column=col_idx).value
            f = _header_field(value)
            if f and f not in seen_fields:
                field_by_pos[col_idx] = f
                seen_fields.add(f)
        if len(seen_fields) >= 2:
            return row_idx, field_by_pos
    return None, {}


def _vertical_merge_anchors(ws, header_row: int) -> dict[tuple[int, int], tuple[int, int]]:
    """`{(row, col): (anchor_row, col)}` for every merge that spans MORE THAN ONE ROW in one
    column, below the header - a row-only merge (one row, several columns) never fills down."""
    anchors: dict[tuple[int, int], tuple[int, int]] = {}
    for rng in ws.merged_cells.ranges:
        if rng.min_col != rng.max_col or rng.max_row <= rng.min_row:
            continue
        if rng.min_row <= header_row:
            continue
        for row in range(rng.min_row + 1, rng.max_row + 1):
            anchors[(row, rng.min_col)] = (rng.min_row, rng.min_col)
    return anchors


def _letterhead_texts(ws, header_row: int) -> list[str]:
    texts: list[str] = []
    for row_idx in range(1, header_row):
        for col_idx in range(1, ws.max_column + 1):
            value = ws.cell(row=row_idx, column=col_idx).value
            if value is not None and str(value).strip():
                texts.append(str(value).strip())
    return texts


def _inspect_zip(data: bytes) -> None:
    """The zip pre-check S2 needs: summed declared uncompressed size, compression
    ratio, and a macro-project member/content type - all read from the archive's own
    directory, never by inflating a member. Deliberately does NOT use `read_only`
    on the eventual `openpyxl.load_workbook` call: that mode drops merged-cell
    metadata this reader depends on (`_vertical_merge_anchors`), so this check is the
    bound instead of a safer-but-lossier parse mode."""
    import io

    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise AppException(
            422, "That file could not be read as an Excel workbook.",
            detail={"code": "file_type"}, code="file_type",
        ) from exc

    try:
        total_uncompressed = 0
        total_compressed = 0
        has_macro_member = False
        content_types_xml: Optional[bytes] = None
        for info in zf.infolist():
            total_uncompressed += info.file_size
            total_compressed += info.compress_size
            if info.filename == _MACRO_MEMBER:
                has_macro_member = True
            if info.filename == "[Content_Types].xml":
                content_types_xml = zf.read(info.filename)

        if total_uncompressed > _MAX_ZIP_UNCOMPRESSED_BYTES:
            raise AppException(
                422, "The file is too large to process safely.",
                detail={"code": "file_too_large"}, code="file_too_large",
            )
        if total_compressed and (total_uncompressed / total_compressed) > _MAX_ZIP_COMPRESSION_RATIO:
            raise AppException(
                422, "The file is too large to process safely.",
                detail={"code": "file_too_large"}, code="file_too_large",
            )
        if has_macro_member or (content_types_xml and _MACRO_CONTENT_TYPE_MARKER in content_types_xml):
            raise AppException(
                422, "Macro-enabled workbooks are not accepted.",
                detail={"code": "file_type"}, code="file_type",
            )
    finally:
        zf.close()


def read_supplier_price_list(data: bytes, filename: str) -> PriceListRead:
    name = (filename or "").lower()
    if not name.endswith(".xlsx"):
        raise AppException(422, "Upload an .xlsx file.", detail={"code": "file_type"}, code="file_type")
    if len(data) > _MAX_FILE_BYTES:
        raise AppException(
            422, "The file exceeds the 25 MB limit.",
            detail={"code": "file_too_large"}, code="file_too_large",
        )
    _inspect_zip(data)

    import io

    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    except Exception as exc:  # noqa: BLE001 - any unreadable file is a file_type refusal
        raise AppException(
            422, "That file could not be read as an Excel workbook.",
            detail={"code": "file_type"}, code="file_type",
        ) from exc

    sheets: list[PriceListSheet] = []
    letterhead: list[str] = []
    price_header_texts: list[str] = []
    total_rows = 0

    for ws in wb.worksheets:
        max_row = ws.max_row or 0
        max_col = ws.max_column or 0
        if max_col and max_row and max_col * max_row > _MAX_SHEET_CELLS:
            raise AppException(
                422, "One sheet has too many cells to parse safely.",
                detail={"code": "too_many_rows"}, code="too_many_rows",
            )

        header_row, field_by_pos = _find_header(ws, max_row)
        if header_row is None:
            sheets.append(PriceListSheet(name=ws.title, header_row=None, skipped_reason="no_header", rows=[]))
            continue

        pos_for = {f: pos for pos, f in field_by_pos.items()}
        price_pos = pos_for.get("price")
        if price_pos:
            header_text = ws.cell(row=header_row, column=price_pos).value
            if header_text is not None:
                price_header_texts.append(str(header_text))

        merge_anchors = _vertical_merge_anchors(ws, header_row)
        letterhead.extend(_letterhead_texts(ws, header_row))

        rows: list[PriceListRow] = []
        blank_run = 0
        row_idx = header_row + 1
        while row_idx <= max_row and blank_run < _MAX_CONSECUTIVE_BLANK_ROWS:
            def _raw(field_name: str):
                pos = pos_for.get(field_name)
                if not pos:
                    return None
                return ws.cell(row=row_idx, column=pos).value

            line_no_raw = _raw("line_no")
            code_raw = _raw("item_code")
            desc_raw = _raw("description")
            price_raw = _raw("price")

            if all(
                v is None or (isinstance(v, str) and not v.strip())
                for v in (line_no_raw, code_raw, desc_raw, price_raw)
            ):
                blank_run += 1
                row_idx += 1
                continue
            blank_run = 0

            flags: set[str] = set()
            desc_pos = pos_for.get("description")
            if desc_raw in (None, "") and desc_pos and (row_idx, desc_pos) in merge_anchors:
                anchor_row, anchor_col = merge_anchors[(row_idx, desc_pos)]
                desc_raw = ws.cell(row=anchor_row, column=anchor_col).value
                flags.add("configuration_from_merge")

            price_source = price_raw
            if price_raw in (None, "") and price_pos and (row_idx, price_pos) in merge_anchors:
                anchor_row, anchor_col = merge_anchors[(row_idx, price_pos)]
                price_source = ws.cell(row=anchor_row, column=anchor_col).value
                if price_source is not None:
                    flags.add("price_from_merge")

            supplier_code, code_note = clean_code(code_raw)
            price = clean_price(price_source)

            if not supplier_code and price is None:
                row_idx += 1
                continue

            total_rows += 1
            if total_rows > _MAX_ROWS:
                raise AppException(
                    422, "The file has more than 5,000 rows.",
                    detail={"code": "too_many_rows"}, code="too_many_rows",
                )

            rows.append(
                PriceListRow(
                    sheet=ws.title,
                    row_no=row_idx,
                    line_no=(str(line_no_raw).strip() if line_no_raw not in (None, "") else None),
                    supplier_code_raw=str(code_raw) if code_raw is not None else "",
                    supplier_code=supplier_code,
                    code_note=code_note,
                    configuration=(str(desc_raw).strip() if desc_raw not in (None, "") else None),
                    price=price,
                    flags=flags,
                )
            )
            row_idx += 1

        sheets.append(PriceListSheet(name=ws.title, header_row=header_row, skipped_reason=None, rows=rows))

    # Deduped, order preserved.
    seen: set[str] = set()
    letterhead = [t for t in letterhead if not (t in seen or seen.add(t))]

    return PriceListRead(
        sheets=sheets,
        letterhead=letterhead,
        header_currency=currency_from_text(price_header_texts),
        total_rows=total_rows,
    )
