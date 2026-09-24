"""Alias-free header-row and column probe for the inline import column mapper (B2,
PLAN-import-column-mapper-24sep.md).

Every reader in this package finds ITS OWN header row by asking whether the row resolves
enough aliased columns to satisfy its own required set - which is exactly the chicken-and-egg
the mapper exists to break: a first-time supplier has no aliases yet, so the header row is
never recognised, so the mapper never has anything to show (the plan's "Measured" section).
This module answers a narrower question with no alias table in it at all: "which row LOOKS
like a table header, and what does each of its columns say" - text-shape and layout only.

Heuristic: the first row with >= 5 text cells, followed within 2 rows by a row with >= 3
numeric cells. Every one of the four real supplier files this lane measured a header row
against (a plain row, a row preceded by a merged title, and a row followed by its own
second header row) satisfies this without a single alias configured.

Two shapes are named rather than left blank, because a blank column can never be mapped to
anything (AC-M2):
  * A merged header cell with blank cells beside it (`外箱/木托尺寸` merged over three
    columns) - the blank ones become `<parent> [2]`, `<parent> [3]`, ...
  * A merged header cell whose SECOND row (immediately below it) is itself text, not data
    (DAFUYUAN's `箱子 CTN SIZE (CM)` merged over `L (长)` / `W (宽)` / `H (高)`) - every
    column IN that merge, including the merge's own anchor column, is spliced with its own
    sub-header text instead: `箱子 CTN SIZE (CM) L (长)`. The row below that then holds the
    header's true SECOND row, and every column's own sample comes from the row(s) after
    THAT, never from the sub-header text itself.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from app.services.scm.outstanding_reader import all_sheet_rows, sheet_merges


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    s = str(value).strip()
    return s or None


def _sample_text(value: Any) -> Optional[str]:
    """A sample cell's own display text (R10, review round 1): a NUMBER is formatted with
    `format(value, "g")` - Excel's own computed float (`6.5085120000000005`, 18 characters,
    a real value on row 17 of the NEW YANGGANG PI, not a typo) shortens to `6.50851`, which
    is what R5's whole point ("something a human is meant to read at a glance") actually
    needs. Text is returned AS IS - `_text`'s own job - never reformatted: a product name or
    remark is not a number no matter how long it runs.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return format(value, "g")
    s = str(value).strip()
    return s or None


def _is_number(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    raw = str(value).strip().replace(",", "")
    if not raw:
        return False
    try:
        float(raw)
        return True
    except ValueError:
        return False


def _is_text_cell(value: Any) -> bool:
    """A real piece of TEXT, not a number written in a cell - the distinction the second-
    header-row splice needs (a numeric data row below a merge must never read as one)."""
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return False
    s = _text(value)
    return s is not None and not _is_number(s)


@dataclass
class HeaderColumn:
    position: int
    #: The full header text, line breaks and all - never re-typed, never truncated.
    header: str
    #: One sample value, the first non-blank cell below the header (owner override, 24 Sep
    #: evening - was up to two, R5). List shape kept (length <= 1).
    samples: list[str] = field(default_factory=list)


@dataclass
class HeaderProbe:
    #: `None` when no row satisfied the heuristic (AC-M16) - the caller's own stepper
    #: still has to start somewhere (row 1), which is a starting point, not a guess this
    #: module is making on its behalf.
    header_row: Optional[int]
    columns: list[HeaderColumn] = field(default_factory=list)
    #: The sheet's own last row number (review round 1, item 12) - the stepper's own
    #: ceiling, so "move header row down" has somewhere to stop rather than stepping past
    #: the last real row forever. `0` for a sheet with no rows at all.
    row_count: int = 0


def _guess_header_row(rows: list[tuple]) -> Optional[int]:
    for idx, row in enumerate(rows):
        text_count = sum(1 for c in row if _is_text_cell(c))
        if text_count < 5:
            continue
        for nxt_idx in range(idx + 1, min(idx + 3, len(rows))):
            numeric_count = sum(1 for c in rows[nxt_idx] if _is_number(c))
            if numeric_count >= 3:
                return idx + 1
    return None


def probe(file_data: bytes, header_row: Optional[int] = None) -> HeaderProbe:
    """`header_row` overrides the guess (AC-M3, the stepper) - given, it is read exactly as
    stated, merges and all, never just relabelled onto the guessed row's own columns."""
    rows = all_sheet_rows(file_data)
    merges = sheet_merges(file_data)

    resolved_row = header_row if header_row is not None else _guess_header_row(rows)
    if resolved_row is None:
        return HeaderProbe(header_row=None, columns=[], row_count=len(rows))

    header_idx = resolved_row - 1
    if header_idx < 0 or header_idx >= len(rows):
        return HeaderProbe(header_row=resolved_row, columns=[], row_count=len(rows))
    header_raw = rows[header_idx]
    width = len(header_raw)

    # Every merge whose ENTIRE span sits on the header row itself, anchor position (0-based)
    # -> its continuation positions (0-based), sorted. A merge spanning more than one row
    # (a data cell merged down a family, common on the stock list) is not a header shape at
    # all and is deliberately left out here.
    spans: dict[int, list[int]] = {}
    for (r, c), (ar, ac) in merges.items():
        if r == resolved_row and ar == resolved_row:
            spans.setdefault(ac - 1, []).append(c - 1)
    for cont in spans.values():
        cont.sort()

    # Does the row directly below splice in as a SECOND header row? Decided per merge: only
    # when every column the merge covers (its anchor included) holds real TEXT there, never
    # a number - a numeric row is DATA, not a sub-header (AC-M2 vs the ordinary [n] case).
    next_row = rows[header_idx + 1] if header_idx + 1 < len(rows) else ()
    splice_text: dict[int, str] = {}
    spliced_any = False
    for anchor_pos, continuations in spans.items():
        cols = [anchor_pos, *continuations]
        sub_values = [next_row[p] if p < len(next_row) else None for p in cols]
        if all(_is_text_cell(v) for v in sub_values):
            spliced_any = True
            for p, v in zip(cols, sub_values):
                splice_text[p] = _text(v) or ""

    # A spliced second header row is consumed as HEADER, not data - every column's own
    # samples start one row further down than usual.
    data_start_idx = header_idx + (2 if spliced_any else 1)

    continuation_positions = {p for cont in spans.values() for p in cont}

    columns: list[HeaderColumn] = []
    for pos in range(width):
        anchor_text = _text(header_raw[pos])
        if pos in splice_text:
            parent_pos = pos if pos in spans else next(
                a for a, cont in spans.items() if pos in cont
            )
            parent_text = _text(header_raw[parent_pos]) or ""
            header_text = f"{parent_text} {splice_text[pos]}".strip()
        elif anchor_text is not None:
            header_text = anchor_text
        elif pos in continuation_positions:
            parent_pos = next(a for a, cont in spans.items() if pos in cont)
            parent_text = _text(header_raw[parent_pos]) or ""
            ordinal = spans[parent_pos].index(pos) + 2  # the anchor itself carries no [1]
            header_text = f"{parent_text} [{ordinal}]"
        else:
            header_text = ""

        # One sample per column (owner override, 24 Sep evening - was up to two, R5): the
        # FIRST non-blank cell below the header, list shape kept (length <= 1) so a
        # caller iterating `samples` needs no special case for "none on file yet".
        samples: list[str] = []
        for data_row in rows[data_start_idx:]:
            if pos >= len(data_row):
                continue
            value = _sample_text(data_row[pos])
            if value is None:
                continue
            samples.append(value)
            break

        columns.append(HeaderColumn(position=pos, header=header_text, samples=samples))

    # Trailing columns with NO HEADER TEXT (openpyxl pads every row to the SHEET's own
    # `max_column`, which formatting-only cells - a border, a fill, with never a value -
    # inflate well past the header row's own printed width) are not columns anyone can
    # map: nothing names them, whatever a stray cell beneath one holds (a footer line, a
    # totals row bleeding into a column the table itself never used). Trimmed from the end
    # only, and by header text ALONE (not samples) - a genuinely blank column in the
    # MIDDLE of the table is either a merge continuation (already named `<parent> [n]`) or
    # real data the caller should still see; only a column with no name AT THE EDGE, real
    # data or not, is noise a save can never accept anyway (its header is what gets saved).
    while columns and not columns[-1].header:
        columns.pop()

    return HeaderProbe(header_row=resolved_row, columns=columns, row_count=len(rows))
