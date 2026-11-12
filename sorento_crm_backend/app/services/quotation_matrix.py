"""PS-QUOTE-MATRIX: the pure rules of a quotation scope with column headers.

A version's ``matrix_columns`` is ``[{"key", "label", "cols": [{"key", "label"}]}]``. A header
without ``cols`` is itself one quantity column (a leaf). A line's ``qty_cells`` holds one decimal
per leaf, and its ``quantity`` is their sum, so every reader of ``quantity`` stays correct.

No database here: the routes and the PDF / Excel services call these.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional

from app.services.error_handler import AppException

KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
MAX_HEADERS = 40
MAX_COLS_PER_HEADER = 60
MAX_LEAVES = 200
MAX_LABEL = 60
MAX_CELL = Decimal("9999999.99")
_CENTS = Decimal("0.01")
ZERO = Decimal("0")


def _bad_columns(message: str) -> AppException:
    return AppException(status_code=422, message=message, code="quotation_columns_invalid")


def _bad_cells(message: str) -> AppException:
    return AppException(status_code=422, message=message, code="quotation_cells_invalid")


def _node(raw: Any, seen: set, what: str) -> Dict[str, str]:
    if not isinstance(raw, dict):
        raise _bad_columns(f"Each {what} needs a key and a label.")
    key = raw.get("key")
    if not isinstance(key, str) or not KEY_RE.match(key):
        raise _bad_columns(f"A {what} key is 1 to 40 lowercase letters, digits, - or _.")
    if key in seen:
        raise _bad_columns(f"The column key '{key}' is used twice.")
    seen.add(key)
    label = raw.get("label")
    label = label.strip() if isinstance(label, str) else ""
    if not label or len(label) > MAX_LABEL:
        raise _bad_columns(f"A {what} label is 1 to {MAX_LABEL} characters.")
    return {"key": key, "label": label}


def validate_columns(columns: Any) -> List[Dict[str, Any]]:
    """The columns with labels trimmed; None or [] is no columns."""
    if columns is None or columns == []:
        return []
    if not isinstance(columns, list):
        raise _bad_columns("Columns must be a list of headers.")
    if len(columns) > MAX_HEADERS:
        raise _bad_columns(f"At most {MAX_HEADERS} column headers.")
    seen: set = set()
    out: List[Dict[str, Any]] = []
    leaves = 0
    for raw in columns:
        header = _node(raw, seen, "header")
        cols = raw.get("cols") if raw.get("cols") is not None else []
        if not isinstance(cols, list):
            raise _bad_columns("A header's columns must be a list.")
        if len(cols) > MAX_COLS_PER_HEADER:
            raise _bad_columns(f"At most {MAX_COLS_PER_HEADER} columns under a header.")
        header["cols"] = [_node(c, seen, "column") for c in cols]
        leaves += len(cols) or 1
        out.append(header)
    if leaves > MAX_LEAVES:
        raise _bad_columns(f"At most {MAX_LEAVES} quantity columns in a scope.")
    return out


def leaf_keys(columns: Optional[Iterable[Dict[str, Any]]]) -> List[str]:
    keys: List[str] = []
    for header in columns or []:
        cols = header.get("cols") or []
        if cols:
            keys.extend(c["key"] for c in cols)
        else:
            keys.append(header["key"])
    return keys


def cell_label(columns: Optional[Iterable[Dict[str, Any]]], key: str) -> Optional[str]:
    for header in columns or []:
        cols = header.get("cols") or []
        for col in cols:
            if col["key"] == key:
                return f"{header['label']} / {col['label']}"
        if not cols and header["key"] == key:
            return header["label"]
    return None


def normalise_cells(columns: Optional[Iterable[Dict[str, Any]]], cells: Any) -> Optional[Dict[str, str]]:
    """2 dp decimal strings, zero and blank dropped, {} stored as None."""
    if not cells:
        return None
    if not isinstance(cells, dict):
        raise _bad_cells("Quantities must be a key to number map.")
    leaves = set(leaf_keys(columns))
    out: Dict[str, str] = {}
    for key, raw in cells.items():
        if key not in leaves:
            raise _bad_cells("A quantity points at a column this scope does not have.")
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            continue
        if isinstance(raw, bool):
            raise _bad_cells("A quantity must be a number.")
        try:
            value = Decimal(str(raw).strip())
        except InvalidOperation:
            raise _bad_cells("A quantity must be a number.")
        if not value.is_finite() or value < 0 or value > MAX_CELL:
            raise _bad_cells("A quantity is between 0 and 9,999,999.99.")
        value = value.quantize(_CENTS)
        if value > MAX_CELL:  # rounding up past the ceiling
            raise _bad_cells("A quantity is between 0 and 9,999,999.99.")
        if value:
            out[key] = f"{value:.2f}"
    return out or None


def cells_total(cells: Optional[Dict[str, Any]]) -> Decimal:
    return sum((Decimal(str(v)) for v in (cells or {}).values()), ZERO)


def pair_headers(columns: Optional[List[Dict[str, Any]]]) -> List[str]:
    """Headers that get a QTY / AMOUNT pair: 2+ headers and that header has 2+ cols."""
    columns = columns or []
    if len(columns) < 2:
        return []
    return [h["key"] for h in columns if len(h.get("cols") or []) >= 2]


def matrix_summary(columns: Optional[List[Dict[str, Any]]], lines: Iterable[Any]) -> Dict[str, Any]:
    """Per-row pairs and totals plus the footer, derived for display and never stored."""
    columns = columns or []
    leaves = leaf_keys(columns)
    pairs = pair_headers(columns)
    members = {h["key"]: [c["key"] for c in h["cols"]] for h in columns if h["key"] in pairs}
    footer = {
        "leaf_qty": {k: ZERO for k in leaves},
        "pair_qty": {k: ZERO for k in pairs},
        "pair_amount": {k: ZERO for k in pairs},
        "total_qty": ZERO,
        "total_amount": ZERO,
    }
    rows = []
    for line in lines:
        cells = {k: Decimal(str(v)) for k, v in (getattr(line, "qty_cells", None) or {}).items()}
        # Rate-only prints its rate and cells but adds to no money total (R10).
        price = ZERO if line.is_rate_only else Decimal(str(line.unit_price or 0))
        row_pairs = {}
        for key in pairs:
            qty = sum((cells.get(k, ZERO) for k in members[key]), ZERO)
            amount = (qty * price).quantize(_CENTS) if price else ZERO
            row_pairs[key] = {"qty": qty, "amount": amount}
            if not line.is_rate_only:
                footer["pair_qty"][key] += qty
                footer["pair_amount"][key] += amount
        total = sum((cells.get(k, ZERO) for k in leaves), ZERO)
        amount = (total * price).quantize(_CENTS) if price else ZERO
        if not line.is_rate_only:
            for k in leaves:
                footer["leaf_qty"][k] += cells.get(k, ZERO)
            footer["total_qty"] += total
            footer["total_amount"] += amount
        rows.append({"pairs": row_pairs, "total_qty": total, "amount": amount})
    return {"leaf_keys": leaves, "pair_headers": pairs, "rows": rows, "footer": footer}
