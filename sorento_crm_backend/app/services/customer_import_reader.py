"""Read a customer (debtor) listing export.

Same reader shape as the SCM uploads: the header is the first row that resolves a customer
code, because AutoCount exports carry title lines above the table, and every column is
resolved through `import_field_alias` under doc type ``customer`` so a client's own spelling
is an alias row rather than a release (UAC AC-4.1).

Two columns are required, `customer_code` and `customer_name`, because together they ARE the
upsert key: one code legally carries many debtor names (`301-S007` holds 225), so a row that
names only the code identifies nothing. A row missing either is skipped and named.

A blank cell means "not supplied", never "clear the field" (AC-3.2), so only non-blank cells
reach `CustomerRow.values` at all. That is the single most likely way a customer importer
destroys real data: a sparse export wiping populated columns.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.services.import_alias_service import AliasResolver, normalize_header

# One workbook entry point for the whole system: `sheet_rows` also reads the OLE2 `.xls`
# files AutoCount still emits, which a bare openpyxl call cannot open at all.
from app.services.scm.outstanding_reader import RowProblem, sheet_rows

DOC_TYPE = "customer"

#: Without both of these the row identifies no customer (AC-4).
REQUIRED_COLUMNS = ("customer_code", "customer_name")

#: Every field the importer will read off a row. Anything else in the alias table for this
#: doc type is ignored rather than silently written somewhere.
READABLE_FIELDS = (
    "customer_code",
    "customer_name",
    "email",
    "phone_number",
    "mobile_number",
    "registered_name",
    "trading_name",
    "registration_number",
    "industry",
    "website",
    "country",
    "tax_id",
    "salutation",
    "first_name",
    "last_name",
    "customer_type",
    "market_segment_code",
)


#: Report furniture AutoCount prints UNDER the table. The committed sample export ends
#: with `*** END OF REPORT ***` sitting in the debtor-NAME column, so without this the
#: last line of every real export is counted as a data row and reported as a bad one.
_FOOTER_PHRASES = frozenset(
    {
        "end of report",
        "end of the report",
        "end of listing",
        "grand total",
        "total",
        "sub total",
        "subtotal",
        "continued",
        "continued next page",
    }
)
_FOOTER_PAGE = re.compile(r"^page\s+\d+(\s+of\s+\d+)?$")


def _is_report_furniture(value: str) -> bool:
    """Whether a cell is a report footer rather than data.

    Matched on the WHOLE cell once decoration is stripped, never on a prefix: a debtor
    genuinely called "Total Home Solutions" must still be reported as a bad row rather
    than disappearing, and the cost of being strict here is only that an unlisted
    footer phrase keeps its old behaviour.
    """
    cleaned = " ".join(re.sub(r"[^0-9a-z ]+", " ", value.lower()).split())
    if not cleaned:
        return True  # a rule line: "-----", "======", "***"
    return cleaned in _FOOTER_PHRASES or bool(_FOOTER_PAGE.match(cleaned))


@dataclass
class CustomerRow:
    row_number: int
    customer_code: str
    customer_name: str
    #: Canonical field -> value, holding ONLY the cells the file actually filled in.
    values: dict[str, str] = field(default_factory=dict)


@dataclass
class CustomerReadResult:
    rows: list[CustomerRow] = field(default_factory=list)
    problems: list[RowProblem] = field(default_factory=list)
    unmapped_headers: list[str] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)
    total_rows: int = 0

    @property
    def ok(self) -> bool:
        return not self.missing_columns


def _text(value: Any) -> Optional[str]:
    """A cell as trimmed text, or None when it is blank.

    Whole floats are rendered without the trailing `.0`: Excel reads a numeric-looking
    phone number or account code as a float, and `60123456789.0` is not a phone number.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    s = str(value).strip()
    return s or None


def read_workbook(
    file_data: bytes, resolver: Optional[AliasResolver] = None, *, db: Optional[Session] = None
) -> CustomerReadResult:
    """Parse the first sheet of a customer listing."""
    if resolver is None:
        if db is None:
            raise ValueError("read_workbook needs either a resolver or a session")
        resolver = AliasResolver.for_doc_type(db, DOC_TYPE)

    result = CustomerReadResult()
    try:
        rows = list(sheet_rows(file_data))
    except Exception as exc:  # noqa: BLE001 - the message is for the person who uploaded it
        result.problems.append(RowProblem(0, f"could not read the workbook: {exc}"))
        result.missing_columns = list(REQUIRED_COLUMNS)
        return result

    header_idx: Optional[int] = None
    col_field: dict[int, str] = {}
    for idx, raw in enumerate(rows):
        mapped: dict[int, str] = {}
        for pos, cell in enumerate(raw):
            resolved = resolver.field_for_header(cell)
            if resolved in READABLE_FIELDS:
                # First column wins for a field named twice, matching the resolver's own
                # first-alias-wins rule rather than depending on column order.
                if resolved not in mapped.values():
                    mapped[pos] = resolved
        if "customer_code" in mapped.values():
            header_idx = idx
            col_field = mapped
            result.unmapped_headers = [
                str(cell).strip()
                for pos, cell in enumerate(raw)
                if pos not in mapped and normalize_header(cell)
            ]
            break

    if header_idx is None:
        result.missing_columns = list(REQUIRED_COLUMNS)
        return result

    present = set(col_field.values())
    result.missing_columns = [c for c in REQUIRED_COLUMNS if c not in present]
    if result.missing_columns:
        return result

    for offset, raw in enumerate(rows[header_idx + 1 :], start=header_idx + 2):
        values: dict[str, str] = {}
        for pos, canonical in col_field.items():
            if pos < len(raw):
                text = _text(raw[pos])
                if text is not None:
                    values[canonical] = text

        code = values.get("customer_code")
        name = values.get("customer_name")
        if code is None and name is None:
            # Spacing, a total line, or a note. Nothing was meant by it, so it is not
            # counted as a data row either.
            continue

        if (code is None or name is None) and all(
            _is_report_furniture(v) for v in values.values()
        ):
            # The footer under the table: `*** END OF REPORT ***`, a page number, a
            # totals line. Only ever considered for a row that is already missing half
            # the key, so a real customer can never be swallowed by it.
            continue

        # Every row that named something is a data row, whether or not it survives:
        # "900 rows, 897 imported, 3 skipped" only adds up if the skipped ones are in.
        result.total_rows += 1
        if code is None:
            result.problems.append(RowProblem(offset, "no customer code", name or ""))
            continue
        if name is None:
            # Name is half the key, so a code on its own cannot be matched OR inserted.
            result.problems.append(RowProblem(offset, "no customer name", code))
            continue

        result.rows.append(
            CustomerRow(
                row_number=offset,
                customer_code=code,
                customer_name=name,
                values=values,
            )
        )
    return result
