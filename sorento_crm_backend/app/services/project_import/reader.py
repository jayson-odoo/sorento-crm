"""Read the PO register workbook (AC-PI-01..08).

Columns are found by HEADING on every sheet, never by position: each header cell goes
through `normalize_header`, then the saved column choices (`import_field_alias`, doc type
`project_po_register`), then the file's own headings below. A row is a data row only when
its PS number cell matches `PS<yy>-<nnnn>`, so total rows, the salesperson roll-up block and
its title rows are not rows at all.

Cells are read as written: a text date stays text, an integer PO number becomes its digits
(and is flagged), `-` in TOTAL VALUE gives no amount. Nothing here touches the database.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any, Callable, Optional, Union

from app.services.import_alias_service import IGNORE_FIELD, normalize_header
from app.services.scm.outstanding_reader import every_sheet_rows, to_date
from app.utils.date_format import fmt_date

DOC_TYPE = "project_po_register"

#: The contract's field keys, in the register's column order (PLAN "Field keys").
FIELDS: tuple[str, ...] = (
    "ps_number",
    "salesperson",
    "customer_service",
    "customer",
    "project_name",
    "developer",
    "po_number",
    "po_value",
    "po_date",
    "amended_date",
    "schedule",
    "delivery",
    "outstanding",
    "so_number",
    "remarks",
)
REQUIRED_FIELDS: tuple[str, ...] = ("ps_number", "customer", "po_number")
#: Screen labels for the field keys, sent to the frontend (`field_labels`) so it keeps no copy.
FIELD_LABELS: dict[str, str] = {
    "ps_number": "PS number",
    "salesperson": "Salesperson",
    "customer_service": "Customer service",
    "customer": "Customer",
    "project_name": "Project name",
    "developer": "Developer",
    "po_number": "PO number",
    "po_value": "PO value",
    "po_date": "PO date",
    "amended_date": "Amended date",
    "schedule": "Schedule",
    "delivery": "Delivery",
    "outstanding": "Outstanding",
    "so_number": "SO number",
    "remarks": "Remarks",
}

#: The register's own headings (and their plain spellings), so its first upload needs no
#: column choice. A saved choice in `import_field_alias` wins over these.
DEFAULT_HEADERS: dict[str, tuple[str, ...]] = {
    "ps_number": ("RUNNING PS NUMBER", "PS NUMBER", "PS NO"),
    "salesperson": ("SALES PERSON", "SALESPERSON"),
    "customer_service": ("CUSTOMER SERVICE",),
    "customer": ("CUSTOMER",),
    "project_name": ("PROJECT NAME REF:", "PROJECT NAME"),
    "developer": ("DEVELOPER REMARK 1 :", "DEVELOPER"),
    "po_number": ("PO NUMBER", "PO NO"),
    "po_value": ("TOTAL VALUE",),
    "po_date": ("DATE", "PO DATE"),
    "amended_date": ("AMENDED DATE",),
    "schedule": ("SCHEDULE YES/NO", "SCHEDULE"),
    "delivery": ("DELIVERY DATE",),
    "outstanding": ("OUTSTANDING",),
    "so_number": ("SO NUMBER", "SO NO"),
    "remarks": ("REMARKS", "REMARK"),
}

PS_RE = re.compile(r"^PS(\d\d)-\d{4}$")
SO_RE = re.compile(r"\bSO\d{6}\b", re.IGNORECASE)

# Upload caps (security review S1): what an xlsx may expand to before openpyxl touches it,
# and how much of each sheet is read. The register is about 1,400 rows over 9 sheets, AK wide.
MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
MAX_COLUMNS = 60
MAX_ROWS_PER_SHEET = 20_000
MAX_SHEETS = 30


class WorkbookRefused(ValueError):
    """An upload over a cap. The message is plain and safe to show."""

#: How far down a sheet the heading row may sit.
_HEADER_SCAN_ROWS = 30
#: How far below the heading a probe looks for a sample value.
_SAMPLE_SCAN_ROWS = 50

FieldFor = Callable[[Any], Optional[str]]


def fold(value: Any) -> str:
    """Trim, collapse inner whitespace to one space, upper-case. Nothing else changes."""
    if value is None:
        return ""
    return " ".join(str(value).split()).upper()


def field_resolver(db=None) -> FieldFor:
    """Header cell -> field key (or `ignore`): saved choices first, then the defaults."""
    defaults: dict[str, str] = {}
    for key, headings in DEFAULT_HEADERS.items():
        defaults.setdefault(normalize_header(key), key)
        for heading in headings:
            defaults.setdefault(normalize_header(heading), key)
    saved = None
    if db is not None:
        from app.services.import_alias_service import AliasResolver

        saved = AliasResolver.for_doc_type(db, DOC_TYPE)

    def field_for(header: Any) -> Optional[str]:
        if not normalize_header(header):
            return None
        if saved is not None:
            raw = saved.raw_field_for_header(header)
            if raw in FIELDS or raw == IGNORE_FIELD:
                return raw
        return defaults.get(normalize_header(header))

    return field_for


# --------------------------------------------------------------------------- shapes


@dataclass
class SheetProbe:
    name: str
    name_trimmed: str
    has_ps_heading: bool
    row_count: int
    columns: list[dict] = field(default_factory=list)


@dataclass
class SourceRow:
    sheet: str
    row_number: int
    ps_number: str
    salesperson: Optional[str] = None
    customer_service: Optional[str] = None
    customer: Optional[str] = None
    project_name: Optional[str] = None
    developer: Optional[str] = None
    po_number: Optional[str] = None
    po_number_numeric: bool = False
    po_value: Optional[Decimal] = None
    value_dash: bool = False
    po_date: Optional[date] = None
    #: The PO date cell as typed when it was text no format reads (flagged, never guessed).
    po_date_text: Optional[str] = None
    amended: Union[date, str, None] = None
    schedule: Optional[str] = None
    delivery: Union[date, str, None] = None
    outstanding: Optional[str] = None
    so_cell: Optional[str] = None
    so_numbers: list[str] = field(default_factory=list)
    #: Column N text that is not an SO number ("refer PS26-0022"), kept for the PO notes.
    so_note: Optional[str] = None
    remarks: Optional[str] = None


@dataclass
class ReadResult:
    rows: list[SourceRow] = field(default_factory=list)
    sheet_errors: list[dict] = field(default_factory=list)


# --------------------------------------------------------------------------- cells


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _text(value: Any) -> Optional[str]:
    if _blank(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (datetime, date)):
        return fmt_date(value.date() if isinstance(value, datetime) else value)
    text = str(value).strip()
    return text or None


def _date_or_text(value: Any) -> Union[date, str, None]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return _text(value)


def _po_number(value: Any) -> tuple[Optional[str], bool]:
    if isinstance(value, bool):
        return str(value), False
    if isinstance(value, int):
        return str(value), True
    if isinstance(value, float):
        return (str(int(value)) if value.is_integer() else str(value)), True
    return _text(value), False


def _amount(value: Any) -> tuple[Optional[Decimal], bool]:
    if isinstance(value, bool) or _blank(value):
        return None, False
    if isinstance(value, str):
        raw = value.strip()
        if raw == "-":
            return None, True
        try:
            return Decimal(raw.replace(",", "")), False
        except InvalidOperation:
            return None, False
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value)), False
    return None, False


def so_numbers(cell: Optional[str]) -> list[str]:
    """Each `SO` + 6 digits number in a column N cell, in order, once each."""
    if not cell:
        return []
    out: list[str] = []
    for token in SO_RE.findall(cell):
        if token.upper() not in out:
            out.append(token.upper())
    return out


def so_note(cell: Optional[str]) -> Optional[str]:
    """What a column N cell says besides its SO numbers ("refer PS26-0022"), or None."""
    if not cell:
        return None
    rest = SO_RE.sub(" ", cell)
    rest = " ".join(rest.replace(",", " ").split())
    return rest or None


def check_workbook(content: bytes) -> None:
    """Refuse an upload over a cap BEFORE openpyxl reads it (security review S1)."""
    import zipfile

    try:
        infos = zipfile.ZipFile(BytesIO(content)).infolist()
    except zipfile.BadZipFile as exc:
        raise WorkbookRefused("The file could not be read as a workbook.") from exc
    expanded = sum(i.file_size for i in infos)
    packed = sum(i.compress_size for i in infos) or 1
    if expanded > MAX_UNCOMPRESSED_BYTES or expanded / packed > MAX_COMPRESSION_RATIO:
        raise WorkbookRefused("The workbook is too large to read.")
    import openpyxl

    wb = openpyxl.load_workbook(BytesIO(content), read_only=True)
    try:
        if len(wb.sheetnames) > MAX_SHEETS:
            raise WorkbookRefused(f"The workbook has more than {MAX_SHEETS} sheets.")
        for ws in wb.worksheets:
            if (ws.max_row or 0) > MAX_ROWS_PER_SHEET:
                raise WorkbookRefused(
                    f"A sheet is larger than {MAX_ROWS_PER_SHEET:,} rows. Clear the unused rows and upload it again."
                )
    finally:
        wb.close()


# --------------------------------------------------------------------------- workbook


def _sheets(content: bytes) -> list[tuple[str, list[tuple]]]:
    """(name as written, rows) per sheet, in workbook order, within the caps."""
    import openpyxl

    check_workbook(content)

    wb = openpyxl.load_workbook(BytesIO(content), read_only=True)
    try:
        names = list(wb.sheetnames)
    finally:
        wb.close()
    return list(zip(names, every_sheet_rows(content, max_col=MAX_COLUMNS, max_row=MAX_ROWS_PER_SHEET)))


def _cell(row: tuple, pos: Optional[int]) -> Any:
    if pos is None or pos >= len(row):
        return None
    return row[pos]


def _ps_heading_row(rows: list[tuple], field_for: FieldFor) -> Optional[int]:
    for idx, row in enumerate(rows[:_HEADER_SCAN_ROWS]):
        if any(field_for(cell) == "ps_number" for cell in row if not _blank(cell)):
            return idx
    return None


def _sample(rows: list[tuple], start: int, pos: int) -> Optional[str]:
    for row in rows[start:start + _SAMPLE_SCAN_ROWS]:
        value = _cell(row, pos)
        if not _blank(value):
            return _text(value)
    return None


def probe(content: bytes, field_for: Optional[FieldFor] = None) -> list[SheetProbe]:
    """Every sheet with its headings as written, one sample each, and its PS row count."""
    field_for = field_for or field_resolver()
    out: list[SheetProbe] = []
    for name, rows in _sheets(content):
        header_idx = _ps_heading_row(rows, field_for)
        has_ps = header_idx is not None
        if header_idx is None:
            header_idx = next(
                (i for i, r in enumerate(rows[:_HEADER_SCAN_ROWS]) if any(not _blank(c) for c in r)),
                None,
            )
        columns: list[dict] = []
        row_count = 0
        if header_idx is not None:
            header = rows[header_idx]
            for pos, cell in enumerate(header):
                if _blank(cell):
                    continue
                columns.append({
                    "position": pos,
                    "header": str(cell),
                    "sample": _sample(rows, header_idx + 1, pos),
                    "field": field_for(cell),
                })
        if has_ps:
            ps_pos = next(c["position"] for c in columns if c["field"] == "ps_number")
            cust_pos = next((c["position"] for c in columns if c["field"] == "customer"), None)
            for row in rows[header_idx + 1:]:
                ps = _text(_cell(row, ps_pos))
                if ps and PS_RE.match(ps) and not _blank(_cell(row, cust_pos)):
                    row_count += 1
        out.append(SheetProbe(
            name=name, name_trimmed=name.strip(), has_ps_heading=has_ps, row_count=row_count,
            columns=columns,
        ))
    return out


def read_rows(content: bytes, *, sheets: list[str], columns: dict[str, str]) -> ReadResult:
    """The PS rows of the ticked sheets (matched after trimming), by the chosen headings."""
    wanted = {str(s).strip() for s in sheets}
    keys = {
        f: normalize_header(h) for f, h in (columns or {}).items()
        if f in FIELDS and h and h != IGNORE_FIELD and normalize_header(h)
    }
    result = ReadResult()
    for name, rows in _sheets(content):
        if name.strip() not in wanted:
            continue
        header_idx, best = None, 0
        for idx, row in enumerate(rows[:_HEADER_SCAN_ROWS]):
            hits = sum(1 for c in row if not _blank(c) and normalize_header(c) in keys.values())
            if hits > best:
                header_idx, best = idx, hits
        col_of: dict[str, int] = {}
        if header_idx is not None:
            for pos, cell in enumerate(rows[header_idx]):
                if _blank(cell):
                    continue
                key = normalize_header(cell)
                for f, k in keys.items():
                    if k == key and f not in col_of:
                        col_of[f] = pos
        missing = [f for f in REQUIRED_FIELDS if f not in col_of]
        if missing:
            f = missing[0]
            result.sheet_errors.append({
                "sheet": name, "code": "missing_header",
                "heading": (columns or {}).get(f) or f,
            })
            continue
        for offset, row in enumerate(rows[header_idx + 1:], start=header_idx + 2):
            ps = _text(_cell(row, col_of["ps_number"]))
            if not ps or not PS_RE.match(ps):
                continue
            get = lambda f: _cell(row, col_of.get(f))  # noqa: E731
            po_number, numeric = _po_number(get("po_number"))
            value, dash = _amount(get("po_value"))
            so_cell = _text(get("so_number"))
            po_date_cell = get("po_date")
            result.rows.append(SourceRow(
                sheet=name,
                row_number=offset,
                ps_number=ps,
                salesperson=_text(get("salesperson")),
                customer_service=_text(get("customer_service")),
                customer=_text(get("customer")),
                project_name=_text(get("project_name")),
                developer=_text(get("developer")),
                po_number=po_number,
                po_number_numeric=numeric,
                po_value=value,
                value_dash=dash,
                po_date=None if _blank(po_date_cell) else to_date(po_date_cell),
                po_date_text=(
                    _text(po_date_cell)
                    if not _blank(po_date_cell) and to_date(po_date_cell) is None
                    else None
                ),
                amended=_date_or_text(get("amended_date")),
                schedule=_text(get("schedule")),
                delivery=_date_or_text(get("delivery")),
                outstanding=_text(get("outstanding")),
                so_cell=so_cell,
                so_numbers=so_numbers(so_cell),
                so_note=so_note(so_cell),
                remarks=_text(get("remarks")),
            ))
    return result


_MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "MAC": 3, "APR": 4, "MAY": 5, "MEI": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "OGO": 8, "SEP": 9, "OCT": 10, "OKT": 10, "NOV": 11, "DEC": 12,
    "DIS": 12,
}


def sheet_month(name: str) -> Optional[int]:
    """The month a monthly sheet stands for (`MAC'26` is March), or None."""
    return _MONTHS.get((name or "").strip().upper()[:3])
