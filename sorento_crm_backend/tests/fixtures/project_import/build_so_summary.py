"""Masked, full-size TOTAL SALES ORDER SUMMARY 2026 workbook (AC-PI-50).

Reproduces `documentation/plans/project-sales/project-import-file-shape.md`: the 9 sheets in
order (SUMMARY JAN-JUN 7th, with merged cells), the trailing-space sheet names, the headers
verbatim (line breaks and padding), PS26-0001..1398 contiguous with the per-sheet ranges,
1282 data rows + 116 AUG placeholders, the total SUM row, the salesperson roll-up block, the
Q8 whitespace junk, and every dirty pattern the shape doc lists.

Every name is FAKE (`CUSTOMER 001 SDN BHD`, `PROJECT 001 SAMPLE NAME`, `DEVELOPER 001`,
`ALVIN`, `KATE`). Nothing here comes from the real file.

Fully deterministic: no random module, the row values are index arithmetic, and the zip is
re-packed with fixed timestamps so two builds give identical bytes.

`EXPECTED` is derived from the builder's own row specs (`row_specs()`), never hand-typed:
it is what a preview of an UNMAPPED run (no lines set, no synced sales orders) must report.
The classification policy it encodes is spelled out in `unmapped_outcome()`.
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Optional, Union

import openpyxl
from openpyxl.styles import Font

# --------------------------------------------------------------------------- headers

#: Columns A..O, verbatim from the shape doc (`\n` is a real line break in the cell).
HEADERS: list[str] = [
    "RUNNING \nPS NUMBER",
    "SALES\nPERSON",
    "CUSTOMER SERVICE",
    "CUSTOMER ",
    "PROJECT NAME" + " " * 30 + "REF: ",
    "DEVELOPER" + " " * 33 + "REMARK 1 : ",
    "PO \nNUMBER",
    "TOTAL \nVALUE",
    "DATE",
    "AMENDED \nDATE",
    "SCHEDULE" + " " * 5 + "YES/NO",
    "DELIVERY DATE",
    "OUTSTANDING",
    "SO NUMBER",
    "REMARKS",
]

#: The contract's field keys, in column order A..O (PLAN "Field keys").
FIELDS: list[str] = [
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
]

#: {field: header as written}: the `columns` payload of `save_columns` for this file.
HEADER_BY_FIELD: dict[str, str] = dict(zip(FIELDS, HEADERS))

# --------------------------------------------------------------------------- sheets


@dataclass(frozen=True)
class SheetSpec:
    name: str  # as written, trailing space included
    month: int
    first_ps: int
    count: int  # PS numbers allocated
    filled: int  # rows that carry data (AUG: the rest are placeholders)
    blank_rows: int  # blank rows between the total row and the roll-up block
    rollup_title: str


MONTHLY_SHEETS: list[SheetSpec] = [
    SheetSpec("JAN'26", 1, 1, 170, 170, 7, "SALES ORDER SUMMARY JANUARY 2026"),
    SheetSpec("FEB'26", 2, 171, 128, 128, 7, "SALES ORDER SUMMARY FEBRUARY 2026"),
    SheetSpec("MAC'26 ", 3, 299, 173, 173, 7, "SALES ORDER SUMMARY MARCH 2026"),
    SheetSpec("APR'26", 4, 472, 216, 216, 7, "SALES ORDER SUMMARY APRIL 2026"),
    SheetSpec("MAY'26", 5, 688, 155, 155, 6, "SALES ORDER SUMMARY MAY 2026"),
    SheetSpec("JUN'26 ", 6, 843, 169, 169, 7, "SALES ORDER SUMMARY JUNE 2026"),
    SheetSpec("JUL'26 ", 7, 1012, 193, 193, 7, "SALES ORDER SUMMARY JULY 2026"),
    SheetSpec("AUG'26", 8, 1205, 194, 78, 7, "SALES ORDER SUMMARY AUGUST 2026"),
]

SUMMARY_SHEET = "SUMMARY JAN-JUN"

#: Workbook order: SUMMARY sits 7th, between JUN and JUL.
SHEET_ORDER: list[str] = [s.name for s in MONTHLY_SHEETS[:6]] + [SUMMARY_SHEET] + [
    s.name for s in MONTHLY_SHEETS[6:]
]

#: Merged ranges on the SUMMARY sheet (none on the monthly sheets).
SUMMARY_MERGES: list[str] = (
    ["F3:G4", "H3:H4", "I3:I4", "J3:J4", "K3:K4", "L3:L4"]
    + [f"F{r}:G{r}" for r in range(5, 23)]
    + ["F24:G24", "F25:G25"]
)

TOTAL_PS = 1398
DATA_ROWS = 1282
PLACEHOLDERS = TOTAL_PS - DATA_ROWS  # 116, all on AUG

# --------------------------------------------------------------------------- names (fake)

SALESPEOPLE = [
    "ALVIN", "BELLA", "CARL", "DIANA", "EVAN", "FIONA", "GARY", "HANNA", "IVAN",
    "JOYCE", "KEN", "LILY", "MARK", "NINA", "OSCAR", "PETER", "QUINN",
]
CUSTOMER_SERVICE = [
    "KATE", "LUNA", "MIKE", "NORA", "OLIVE", "PAUL", "QUEENIE", "ROSE", "SAM", "TINA",
    "UMA", "VERA",
]
N_CUSTOMERS = 202
N_PROJECTS = 577
N_PAIRS = 643


def customer_name(i: int) -> str:
    suffix = "SDN BHD" if i <= 190 else "SENDIRIAN BERHAD"
    return f"CUSTOMER {i:03d} {suffix}"


def project_name(i: int) -> str:
    return f"PROJECT {i:03d} SAMPLE NAME"


def developer_name(n: int) -> str:
    if n % 17 == 0:
        return "END USER"
    return f"DEVELOPER {((n * 13) % 203) + 1:03d}"


# --------------------------------------------------------------------------- row specs

Cell = Union[str, int, float, datetime, None]


@dataclass(frozen=True)
class RowSpec:
    sheet: str
    month: int
    row_number: int  # Excel row number on its sheet
    ps: str
    salesperson: Optional[str] = None
    customer_service: Optional[str] = None
    customer: Optional[str] = None
    project: Optional[str] = None
    developer: Optional[str] = None
    po: Cell = None
    value: Cell = None
    po_date: Optional[datetime] = None
    amended: Cell = None
    schedule: Optional[str] = None
    delivery: Cell = None
    outstanding: Optional[str] = None
    so_cell: Optional[str] = None
    remarks: Optional[str] = None

    @property
    def ps_int(self) -> int:
        return int(self.ps[-4:])

    def cells(self) -> list[Cell]:
        return [
            self.ps, self.salesperson, self.customer_service, self.customer, self.project,
            self.developer, self.po, self.value, self.po_date, self.amended, self.schedule,
            self.delivery, self.outstanding, self.so_cell, self.remarks,
        ]


_PERM_MOD = 1409  # prime above 1398, so n -> n * k mod p permutes the PS numbers


def _ranked(numbers, mult: int) -> list[int]:
    """A fixed, arithmetic shuffle of `numbers` (deterministic, no random module)."""
    return sorted(numbers, key=lambda n: ((n * mult) % _PERM_MOD, n))


#: Shape doc section 3, verbatim (masked) example rows.
EXAMPLE_ROWS: dict[int, dict] = {
    100: dict(salesperson="ALVIN", customer_service="KATE", customer="CUSTOMER 001 SDN BHD",
              project="PROJECT 001 SAMPLE NAME", developer=None, po="JV/PO/7430/75",
              value=25487, po_date=datetime(2025, 1, 2), amended=None, schedule="YES",
              delivery="1Q 2027", outstanding=None, so_cell="SO498152", remarks=None),
    113: dict(salesperson="BELLA", customer_service="LUNA", customer="CUSTOMER 002 SDN BHD",
              project="PROJECT 002 SAMPLE NAME", developer="DEVELOPER 001", po="HQ/75/30/303",
              value=49.68, po_date=datetime(2026, 1, 5), amended=None, schedule="YES",
              delivery=datetime(2026, 1, 6), outstanding=None, so_cell="SO498686",
              remarks=None),
    126: dict(salesperson="CARL", customer_service="KATE", customer="CUSTOMER 003 SDN BHD",
              project="PROJECT 003 SAMPLE NAME", developer="DEVELOPER 002", po=12119,
              value=10090, po_date=datetime(2026, 2, 3), amended=None, schedule="YES",
              delivery=datetime(2026, 7, 1), outstanding=None, so_cell="SO463179",
              remarks=None),
    139: dict(salesperson="DIANA", customer_service="MIKE", customer="CUSTOMER 004 SDN BHD",
              project=None, developer=None, po="OT35/7855", value="-",
              po_date=datetime(2026, 5, 4), amended=None, schedule="YES",
              delivery="IMMEDIATE", outstanding=None, so_cell="CANCELLED 11/5/2026",
              remarks=None),
    152: dict(salesperson="CARL", customer_service="NORA", customer="CUSTOMER 005 SDN BHD",
              project=None, developer=None, po="63481090/B7B", value=2240.99,
              po_date=datetime(2026, 3, 3), amended="amend 9/9/9999", schedule="YES",
              delivery="IMMEDIATE", outstanding=None, so_cell="SO464169", remarks=None),
    165: dict(salesperson="ALVIN", customer_service="KATE", customer="CUSTOMER 006 SDN BHD",
              project=None, developer=None, po="UT-PO301883", value=80286.66,
              po_date=datetime(2026, 4, 14), amended=None, schedule="YES",
              delivery="SCHEDULE", outstanding=None, so_cell="SO466355,SO466352, SO466351",
              remarks=None),
    178: dict(salesperson="BELLA", customer_service="LUNA", customer="CUSTOMER 007 SDN BHD",
              project="PROJECT 004 SAMPLE NAME", developer="DEVELOPER 003", po="EM/PO/7534320",
              value=581.15, po_date=datetime(2026, 4, 1), amended=None, schedule="YES",
              delivery=datetime(2026, 4, 2), outstanding=None, so_cell="SO462360",
              remarks="WAIVE TRANSPORT CHARGE"),
}

#: The 7 rows with `-` in TOTAL VALUE, and what else marks them cancelled.
DASH_ROWS: dict[int, dict] = {
    139: {},  # example row: N = CANCELLED 11/5/2026
    250: dict(so_cell="CANCELLED"),
    420: dict(outstanding="CANCELLED"),
    610: dict(outstanding="CANCELLED 12/6/2026"),
    777: dict(remarks="CANCELLED"),
    950: dict(so_cell="CANCELLED"),
    1100: {},  # only the dash
}
#: Cancelled by column O alone, with a real amount.
REMARK_CANCELS: dict[int, str] = {333: "CANCELLED BY CASH", 844: "CANCEL PS NO"}
#: Column M on hold (imported, text kept in the notes).
ON_HOLD: dict[int, str] = {505: "on hold 23/4/2026", 705: "ON HOLD", 1050: "on hold 2/5/2026"}
#: Column N non-SO text that is not a cancel: kept as an `SO note:`.
SO_NOTES: dict[int, str] = {23: "refer PS26-0022", 451: "refer PS26-0449"}
#: PO dated 2025 in the sheet's own month (16 rows; the first three JAN rows are the typo).
YEAR_2025_ROWS: list[int] = [1, 2, 3, 100, 180, 190, 300, 310, 480, 490, 700, 710, 850, 860,
                             1020, 1030]
#: PO dated 2026 in a month other than its sheet's (10 rows, 5 of them example rows).
OTHER_MONTH_ROWS: dict[int, int] = {126: 2, 139: 5, 152: 3, 165: 4, 178: 4,
                                    400: 5, 600: 6, 800: 4, 1150: 6, 1250: 7}
#: (first, repeat): the 3 repeated (customer, PO) pairs.
REPEATED_PAIRS: list[tuple[int, int]] = [(201, 202), (480, 481), (900, 960)]

_J_TEXTS = ["amend 9/4/2026", "AMEND 14/5/2026", "revised 3/4/2026", "REVISED", "amend",
            "AMEND 8/4/202"]
_L_OTHER = ["NEXTWEEK", "COURIER", "LALAMOVE", "AFTER CNY", "1Q 2027", "END JUL",
            "TBA/ FEB 2027", "IMMDIATE", "URGNT"]
_O_TEXTS = ["WAIVE TRANSPORT CHARGE", "WAIVE TRASNPORT CHARGE", "WAIVE TRASPORT CHARGE",
            "WAIVE TRANPORT CHARGE", "WAIVE TRANSPORT CHARGES", "HOLD", "@SO"]


def _sheet_of(n: int) -> SheetSpec:
    for spec in MONTHLY_SHEETS:
        if spec.first_ps <= n < spec.first_ps + spec.count:
            return spec
    raise ValueError(n)


def _so(n: int, k: int = 0) -> str:
    return f"SO{400000 + n * 7 + k:06d}"


def _po(n: int, numeric: bool) -> Cell:
    if numeric:
        return 10000 + n * 7  # an integer cell (the leading zero is gone)
    fmt = n % 4
    if fmt == 0:
        return f"PO-{n:05d}"
    if fmt == 1:
        return f"JV/{n % 90 + 10}/{n % 70 + 10}/{n:04d}"
    if fmt == 2:
        return f"UT{n % 90 + 10}/{n:04d}"
    return f"{63000000 + n}/B7B"


@lru_cache(maxsize=1)
def row_specs() -> tuple[RowSpec, ...]:
    """Every PS row of every monthly sheet, in PS order (1398 rows)."""
    data = list(range(1, DATA_ROWS + 1))

    no_project = set(_ranked(data, 37)[:DATA_ROWS - 937])  # 345 rows without a project name
    with_developer = set(_ranked(data, 53)[:524])
    numeric_po = set(_ranked(data, 101)[:154])
    float_value = set(_ranked(data, 71)[:577])
    spaced_customer = _ranked(data, 73)[:28]

    # The example rows are YES (shape doc section 3), so they sit outside the ranking.
    k_rank = _ranked([n for n in data if n not in EXAMPLE_ROWS], 41)
    schedule: dict[int, Optional[str]] = {n: "YES" for n in data}
    for n in k_rank[:207]:
        schedule[n] = "O/C"
    schedule[k_rank[207]] = "NO"
    schedule[k_rank[208]] = "YS"
    schedule[k_rank[209]] = "CBD"
    for n in k_rank[210:218]:
        schedule[n] = None

    l_rank = _ranked(data, 43)
    delivery: dict[int, Cell] = {}
    cut = [326, 485, 140, 59, 154]
    pos = 0
    for n in l_rank[pos:pos + cut[0]]:
        s = _sheet_of(n)
        delivery[n] = datetime(2026, s.month, min(28, (n % 28) + 3))
    pos += cut[0]
    for label, size in (("IMMEDIATE", cut[1]), ("SCHEDULE", cut[2]), ("URGENT", cut[3])):
        for n in l_rank[pos:pos + size]:
            delivery[n] = label
        pos += size
    for n in l_rank[pos:pos + cut[4]]:
        delivery[n] = None
    pos += cut[4]
    for i, n in enumerate(l_rank[pos:]):
        delivery[n] = _L_OTHER[i % len(_L_OTHER)]

    j_rank = _ranked(data, 47)[:154]
    amended: dict[int, Cell] = {}
    for i, n in enumerate(j_rank):
        if i < 6:
            amended[n] = datetime(2026, _sheet_of(n).month, 20)
        elif i == 6:
            amended[n] = " "  # a single space: junk whitespace
        else:
            amended[n] = _J_TEXTS[i % len(_J_TEXTS)]

    n_rank = _ranked(data, 59)
    so_blank = set(n_rank[:115])
    so_filled = [n for n in data if n not in so_blank and n not in EXAMPLE_ROWS]
    multi = _ranked(so_filled, 61)[:17]  # + example PS26-0165 = 18 multi-SO rows
    so_cell: dict[int, Optional[str]] = {}
    for n in data:
        so_cell[n] = None if n in so_blank else _so(n)
    for i, n in enumerate(multi):
        size = 2 + (i % 5)  # 2..6 SOs
        sep = "," if i % 2 == 0 else ", "
        so_cell[n] = sep.join(_so(n, k) for k in range(size))

    remarks: dict[int, Optional[str]] = {}
    for i, n in enumerate(_ranked(data, 67)[:55]):
        text = _O_TEXTS[i % len(_O_TEXTS)]
        remarks[n] = _so(n, 9) if text == "@SO" else text

    # (customer index, project index) pairs; pairs 577.. reuse projects 1..66 with another
    # customer, so 577 project names make 643 (customer, project) pairs.
    pairs: list[tuple[int, int]] = []
    for i in range(N_PAIRS):
        if i < N_PROJECTS:
            pairs.append(((i % N_CUSTOMERS) + 1, i + 1))
        else:
            pairs.append((((i * 3 + 50) % N_CUSTOMERS) + 1, (i - N_PROJECTS) + 1))
    project_rows = [n for n in data if n not in no_project]
    pair_of = {n: pairs[j % N_PAIRS] for j, n in enumerate(project_rows)}
    stray_project = set(_ranked(project_rows, 79)[:50])

    sp_rank = _ranked(data, 83)
    sp_of = {n: SALESPEOPLE[(n * 7) % len(SALESPEOPLE)] for n in data}
    trailing_sp: set[int] = set()
    for name, quota in (("ALVIN", 34), ("BELLA", 6), ("CARL", 5)):
        trailing_sp.update([n for n in sp_rank if sp_of[n] == name][:quota])

    rows: dict[int, dict] = {}
    for n in data:
        sheet = _sheet_of(n)
        if n in pair_of:
            c_idx, p_idx = pair_of[n]
            project = project_name(p_idx)
            if n in stray_project:
                project = (project.replace(" SAMPLE ", "  SAMPLE ") + " ") if n % 2 else (
                    " " + project)
        else:
            c_idx = ((n * 7) % N_CUSTOMERS) + 1
            project = None
        customer = customer_name(c_idx)
        value: Cell
        if n in float_value:
            value = round(100 + ((n * 7919) % 90000) + (n % 97) / 100 + 0.01, 2)
        else:
            value = 1000 + (n * 7919) % 90000
        rows[n] = dict(
            salesperson=sp_of[n] + (" " if n in trailing_sp else ""),
            customer_service=CUSTOMER_SERVICE[(n * 5) % len(CUSTOMER_SERVICE)],
            customer=customer,
            project=project,
            developer=developer_name(n) if n in with_developer else None,
            po=_po(n, n in numeric_po),
            value=value,
            po_date=datetime(2026, sheet.month, (n % 28) + 1),
            amended=amended.get(n),
            schedule=schedule[n],
            delivery=delivery[n],
            outstanding=None,
            so_cell=so_cell[n],
            remarks=remarks.get(n),
        )
    for i, n in enumerate(spaced_customer):
        rows[n]["customer"] = (" " + rows[n]["customer"]) if i % 2 else (rows[n]["customer"] + " ")

    # Explicit dirty patterns, applied last so they win.
    for n, values in EXAMPLE_ROWS.items():
        rows[n].update(values)
    for n, extra in DASH_ROWS.items():
        rows[n]["value"] = "-"
        rows[n].update(extra)
    for n, text in REMARK_CANCELS.items():
        rows[n]["remarks"] = text
    for n, text in ON_HOLD.items():
        rows[n]["outstanding"] = text
    for n, text in SO_NOTES.items():
        rows[n]["so_cell"] = text
    for n in YEAR_2025_ROWS:
        rows[n]["po_date"] = datetime(2025, _sheet_of(n).month, 2 if n <= 3 else (n % 28) + 1)
    for n, month in OTHER_MONTH_ROWS.items():
        rows[n]["po_date"] = datetime(2026, month, (n % 28) + 1)
    for first, repeat in REPEATED_PAIRS:
        for key in ("customer", "project", "developer", "po"):
            rows[repeat][key] = rows[first][key]

    out: list[RowSpec] = []
    for sheet in MONTHLY_SHEETS:
        for i in range(sheet.count):
            n = sheet.first_ps + i
            base = dict(sheet=sheet.name, month=sheet.month, row_number=2 + i, ps=f"PS26-{n:04d}")
            if n <= DATA_ROWS:
                out.append(RowSpec(**base, **rows[n]))
            else:
                out.append(RowSpec(**base))  # AUG placeholder: PS number only
    return tuple(out)


# --------------------------------------------------------------------------- reading rules

_SO_TOKEN = re.compile(r"^SO\d{6}$")
_PS = re.compile(r"^PS(\d\d)-\d{4}$")


def fold(value) -> str:
    """The contract's fold: trim, collapse inner whitespace, upper. None gives ''."""
    if value is None:
        return ""
    return " ".join(str(value).split()).upper()


def so_numbers(cell) -> list[str]:
    """Each `SO` + 6 digits token of a column N cell split on `,`."""
    if not isinstance(cell, str):
        return []
    return [t.strip() for t in cell.split(",") if _SO_TOKEN.match(t.strip())]


def is_cancelled(spec: RowSpec) -> bool:
    """AC-PI-27: `-` in H, or M / N / O starting with CANCEL (case-insensitive)."""
    if isinstance(spec.value, str) and spec.value.strip() == "-":
        return True
    for cell in (spec.outstanding, spec.so_cell, spec.remarks):
        if isinstance(cell, str) and cell.strip().upper().startswith("CANCEL"):
            return True
    return False


def unmapped_outcome(spec: RowSpec) -> tuple[str, list[str]]:
    """(outcome, codes) of one PS row in a run with no line set and no synced SO.

    The reading this fixture asserts (listed in the tester report as a contract reading):

    1. year part not 26 -> skipped [other_year]
    2. no customer -> skipped [placeholder]
    3. cancelled -> skipped [cancelled]
    4. no project name -> skipped [no_project_name]
    5. otherwise needs_review, carrying EVERY blocking code (customer_unmapped,
       project_unmapped, developer_unmapped when column F has text), followed by the row's
       flags (po_number_numeric, date_other_year, date_other_month, so_not_synced).

    A skipped row carries exactly its one skip code. `date_other_month` compares the month
    only (02/01/2025 on JAN'26 is date_other_year, not date_other_month).
    """
    m = _PS.match(spec.ps.strip())
    if m and m.group(1) != "26":
        return "skipped", ["other_year"]
    if not fold(spec.customer):
        return "skipped", ["placeholder"]
    if is_cancelled(spec):
        return "skipped", ["cancelled"]
    if not fold(spec.project):
        return "skipped", ["no_project_name"]
    codes = ["customer_unmapped", "project_unmapped"]
    if fold(spec.developer):
        codes.append("developer_unmapped")
    codes.extend(row_flags(spec))
    return "needs_review", codes


def row_flags(spec: RowSpec) -> list[str]:
    flags = []
    if isinstance(spec.po, int) and not isinstance(spec.po, bool):
        flags.append("po_number_numeric")
    if isinstance(spec.po_date, datetime):
        if spec.po_date.year != 2026:
            flags.append("date_other_year")
        if spec.po_date.month != spec.month:
            flags.append("date_other_month")
    if so_numbers(spec.so_cell):
        flags.append("so_not_synced")
    return flags


SKIP_CODES = ("other_year", "placeholder", "cancelled", "no_project_name")
REVIEW_CODES = ("customer_unmapped", "project_unmapped", "developer_unmapped")
FLAG_CODES = ("po_number_numeric", "date_other_year", "date_other_month", "so_not_synced")
OUTCOMES = ("created", "updated", "unchanged", "skipped", "needs_review", "error")


def compute_expected(specs=None) -> dict:
    specs = row_specs() if specs is None else specs
    counts = {o: 0 for o in OUTCOMES}
    codes: dict[str, int] = {}
    for spec in specs:
        outcome, row_codes = unmapped_outcome(spec)
        counts[outcome] += 1
        for code in row_codes:
            codes[code] = codes.get(code, 0) + 1

    def pick(keys):
        return {k: codes[k] for k in keys if codes.get(k)}

    def pairs(kind: str) -> set:
        out = set()
        for s in specs:
            if not fold(s.customer):
                continue
            if kind == "customer":
                out.add(fold(s.customer))
            elif kind == "project" and fold(s.project):
                out.add((fold(s.customer), fold(s.project)))
            elif kind == "developer" and fold(s.developer):
                out.add(fold(s.developer))
        return out

    return {
        "ps_rows": len(specs),
        "data_rows": sum(1 for s in specs if fold(s.customer)),
        "counts": counts,
        "codes": {k: v for k, v in codes.items() if v},
        "skip_codes": pick(SKIP_CODES),
        "review_codes": pick(REVIEW_CODES),
        "flags": pick(FLAG_CODES),
        "rows_per_sheet": {
            sheet.name: sum(1 for s in specs if s.sheet == sheet.name and fold(s.customer))
            for sheet in MONTHLY_SHEETS
        },
        "distinct": {
            "customer": len(pairs("customer")),
            "project": len(pairs("project")),
            "developer": len(pairs("developer")),
        },
        "dash_rows": sum(1 for s in specs if s.value == "-"),
        "multi_so_rows": sum(1 for s in specs if len(so_numbers(s.so_cell)) > 1),
        "numeric_po_rows": sum(
            1 for s in specs if isinstance(s.po, int) and not isinstance(s.po, bool)
        ),
    }


EXPECTED: dict = compute_expected()

# --------------------------------------------------------------------------- writing


def _write_monthly(ws, sheet: SheetSpec, specs: list[RowSpec]) -> None:
    for col, header in enumerate(HEADERS, start=1):
        ws.cell(row=1, column=col, value=header)
    for spec in specs:
        for col, value in enumerate(spec.cells(), start=1):
            if value is None:
                continue
            cell = ws.cell(row=spec.row_number, column=col, value=value)
            if isinstance(value, datetime):
                cell.number_format = "dd/mm/yyyy"
    last = 1 + len(specs)
    # Q8: a ~300-character string of spaces on every monthly sheet.
    ws["Q8"] = " " * 300
    # The total row: blank label, SUM of column H.
    total_row = last + 1
    ws.cell(row=total_row, column=8, value=f"=SUM(H2:H{last})")
    # The salesperson roll-up block in B:D. No PS number in A.
    title_row = total_row + sheet.blank_rows + 1
    ws.cell(row=title_row, column=2, value=sheet.rollup_title)
    ws.cell(row=title_row + 1, column=2, value="SALESPERSON")
    ws.cell(row=title_row + 1, column=3, value="TOTAL PO")
    ws.cell(row=title_row + 1, column=4, value="TOTAL AMOUNT")
    names = sorted(SALESPEOPLE)[:13]
    first = title_row + 2
    for i, name in enumerate(names):
        mine = [s for s in specs if fold(s.salesperson) == name]
        amount = sum(s.value for s in mine if isinstance(s.value, (int, float)))
        ws.cell(row=first + i, column=2, value=name)
        ws.cell(row=first + i, column=3, value=len(mine) if mine else "-")
        ws.cell(row=first + i, column=4, value=round(amount, 2))
    total = first + len(names)
    ws.cell(row=total, column=2, value="Total")
    ws.cell(row=total, column=3, value=f"=SUM(C{first}:C{total - 1})")
    ws.cell(row=total, column=4, value=f"=SUM(D{first}:D{total - 1})")
    # A styled empty AK1, so the used range reads A1:AK<n> like the real file.
    ws["AK1"].font = Font(bold=True)


def _write_summary(ws) -> None:
    ws["B2"] = "WITH SCHEDULE"
    ws["F2"] = "WITHOUT SCHEDULE"
    ws["B3"] = "SALES ORDER SUMMARY JANUARY -  JUNE 2026"
    ws["B4"], ws["C4"], ws["D4"] = "SALESPERSON", "TOTAL PO", "TOTAL AMOUNT"
    for i in range(15):
        row = 5 + i
        first = SALESPEOPLE[i]
        ws.cell(row=row, column=2, value=f"{first} SURNAME{i + 1:02d}")
        ws.cell(row=row, column=3, value=40 + i)
        ws.cell(row=row, column=4, value=100000 + i * 1234.5)
    ws["B20"] = "Total"
    ws["C20"] = "=SUM(C5:C19)"
    ws["D20"] = "=SUM(D5:D19)"
    ws["F3"] = "SALES PERSON"
    ws["H3"], ws["I3"], ws["J3"], ws["K3"], ws["L3"] = (
        "CUSTOMER NAME", "PROJECT NAME", "PO NO", "PO DATE", "VALUE",
    )
    for i in range(18):
        row = 5 + i
        month = 6 + i  # 2025-06 .. 2026-11, capped to 2026-08
        year, month = (2025, month) if month <= 12 else (2026, min(month - 12, 8))
        ws.cell(row=row, column=6, value=f"{SALESPEOPLE[i % 17]} SURNAME{i + 1:02d}")
        ws.cell(row=row, column=8, value=customer_name(i + 1))
        ws.cell(row=row, column=9, value=project_name(i + 1))
        ws.cell(row=row, column=10, value=f"PO-BIG-{i + 1:03d}")
        cell = ws.cell(row=row, column=11, value=datetime(year, month, 15))
        cell.number_format = "dd/mm/yyyy"
        ws.cell(row=row, column=12, value=250000 + i * 1000)
    ws["L24"] = "."
    ws["B25"] = "REVENUE TOTALS"
    for rng in SUMMARY_MERGES:
        ws.merge_cells(rng)
    ws["P26"].font = Font(bold=True)  # used range B2:P26


_FIXED_TS = (2026, 1, 1, 0, 0, 0)
_FIXED_ISO = "2026-01-01T00:00:00Z"


def _repack(raw: bytes) -> bytes:
    """Same zip entries, fixed timestamps (zip headers and docProps/core.xml)."""
    src = zipfile.ZipFile(io.BytesIO(raw))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == "docProps/core.xml":
                text = data.decode("utf-8")
                text = re.sub(
                    r"(<dcterms:(created|modified)[^>]*>)[^<]*(</dcterms:\2>)",
                    lambda m: m.group(1) + _FIXED_ISO + m.group(3),
                    text,
                )
                data = text.encode("utf-8")
            entry = zipfile.ZipInfo(info.filename, date_time=_FIXED_TS)
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o600 << 16
            dst.writestr(entry, data)
    return out.getvalue()


@lru_cache(maxsize=1)
def _build_bytes() -> bytes:
    specs = row_specs()
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    wb.properties.creator = "fixture"
    by_sheet = {s.name: [r for r in specs if r.sheet == s.name] for s in MONTHLY_SHEETS}
    for name in SHEET_ORDER:
        ws = wb.create_sheet(title=name)
        if name == SUMMARY_SHEET:
            _write_summary(ws)
        else:
            sheet = next(s for s in MONTHLY_SHEETS if s.name == name)
            _write_monthly(ws, sheet, by_sheet[name])
    buffer = io.BytesIO()
    wb.save(buffer)
    return _repack(buffer.getvalue())


def build_workbook(path=None) -> bytes:
    """The masked workbook as xlsx bytes; also written to `path` when one is given."""
    content = _build_bytes()
    if path is not None:
        with open(path, "wb") as fh:
            fh.write(content)
    return content


if __name__ == "__main__":  # pragma: no cover - manual inspection aid
    import json
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else None
    data = build_workbook(target)
    print(len(data), "bytes")
    print(json.dumps(EXPECTED, indent=2, default=str))
