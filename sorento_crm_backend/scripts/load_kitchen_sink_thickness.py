#!/usr/bin/env python3
"""Load the owner's "Kitchen Sink ( Thickness) .xlsx" onto products through
`product_spec_write.apply_spec_values` - the one sanctioned writer of spec values.

WORKBOOK LAYOUT (measured against the real file)
-------------------------------------------------
Four sheets: "Sorento " (trailing space), "Cabana ", "Mocha", "Iborn". Row 1 is the
header, column A is the model code.

  * Sorento / Cabana: column B is the thickness text, column C is the material text
    (only ever "Stainless Steel 201 " in the measured file).
  * Mocha / Iborn: the header prints Thickness / Material / Finish, but the DATA is
    shifted one column from the header - column B holds the steel grade ("SUS201" /
    "SUS304"), column C holds the thickness text, column D holds the finish.

Thickness text is read in millimetres. A number after "面板" (board, optionally
":" or spaces) is `board_thickness`; independently of that, a number after "盆胆"
(bowl), or - when there is no 盆胆 - "厚度 N" or a bare "N" / "Nmm" / a bare numeric
Excel cell such as `0.9` with no unit text at all, is `thickness`. A cell can carry
BOTH a 面板 figure and a 厚度 figure at once; both are read, not just the first
match. Anything that yields neither is a parse failure - the row is reported and
skipped, never guessed.

Steel grade ("SUS201" / "SUS304" / "Stainless Steel 201") sets BOTH `steel_grade`
("201" / "304") and `material` ("stainless_steel") - the two keys already exist in
`app.services.product_spec_registry.SPEC_REGISTRY_SEED`.

Finish (Mocha / Iborn column D only) is grouped by CELL FILL COLOUR, not by row:
contiguous rows sharing one solid fill form a group, and the group's finish is
every non-blank D label in that group, joined in row order and slugged (collapse
whitespace/newlines, lowercase, spaces to underscores). Measured against the real
file this reproduces exactly the groups the owner named - Mocha FFFFF2CC ->
andria_series, FFD9EAD3 -> normal, FFCFE2F3 -> honeycomb, FFF4CCCC -> nano_volcano,
FFFF9900 -> nano_grain; Iborn FFFFF2CC -> nano_grain, FFD0E0E3 -> nano_volcano (one
label "NANO" on one row, "VOLCANO" on another, joined) - without a hardcoded
colour-to-name table, so a colour the workbook adds later needs no code change.

A code is `str(cell).strip()`, a trailing parenthetical like " (new)" / " (dustbin)"
dropped, then upper-cased, and matched EXACTLY against `products.product_code`
(trimmed, upper-cased) - no fuzzy or suffix matching, so SRTKS7850 is never applied
to SRTKS7850-2. A cell that normalises to an empty code (blank, or nothing left
after the parenthetical is dropped) is reported as a parse failure and skipped.

A code appearing twice with IDENTICAL parsed values - on the SAME sheet or across
DIFFERENT sheets - is written once, from its first occurrence in workbook order.
Twice with DIFFERENT values, anywhere in the workbook, is a conflict: reported,
and it is not written at all, even where a single copy of it would otherwise have
been fine on its own.

REGISTRY KEYS
-------------
Two keys are created if missing, mirroring `create_spec_key`
(`app/api/v1/master_data/spec_registry.py`) - `source="user"`, `synonyms={}`,
`match_tolerance`/`match_decay` from `default_match_window(unit)`, and the same
`_validate_reachable` check the route runs before it ever adds a row:

  * `board_thickness` - numeric, mm, `applies_when {"class": ["Kitchen Sink"]}`,
    the same `rank_weight` as the seeded `thickness` key.
  * `surface_texture` - enum (normal / honeycomb / nano_volcano / nano_grain /
    andria_series), `applies_when {"class": ["Kitchen Sink"]}`, the same
    `rank_weight` as the seeded `finish` key, with a customer-language synonym for
    every value (so `_validate_reachable` accepts it, and term resolution in
    `product_spec_search.py` can actually find it).

`thickness`, `material` and `steel_grade` already exist in the seed and are only
read here, never created.

FOLLOW-UP: `board_thickness` and `surface_texture` do not yet reach the rendered
spec sentence - `product_spec_rendering.render_spec_sentence` reads a hardcoded
key list that does not name either one. Widening that list is a separate change.

SAFETY
------
Default is DRY RUN: the whole run - the registry INSERT attempt AND every
`apply_spec_values` call - happens inside one transaction that is rolled back at
the end, so a dry run reports exactly what `--apply` would do, validation
failures included. `--apply` commits instead. `--sheet NAME` limits the run to one
sheet (matched case-insensitively, trailing spaces ignored).

Never run `--apply` against the shared dev database without the owner's go-ahead.

REPORTING
---------
Writing a human-authored value can open a `product_spec_exceptions` row when
derivation disagrees with it (`human_override_conflict` - e.g. the sheet says
SUS201 but the product's own description says SUS304). Every code's exception set
is read before and after its own write, and anything new is printed with the
sheet's value against the value derivation would have picked. An unmatched code
also gets up to five `product_code LIKE '<code>%'` catalog matches printed beside
it, so the owner can see why (a suffix the sheet dropped, a variant it never had).

Run from sorento_crm_backend/:
    python scripts/load_kitchen_sink_thickness.py
    python scripts/load_kitchen_sink_thickness.py --xlsx "/path/to/file.xlsx"
    python scripts/load_kitchen_sink_thickness.py --sheet Mocha
    python scripts/load_kitchen_sink_thickness.py --apply
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Optional

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openpyxl
from sqlalchemy.orm import Session

WORKBOOK_LABEL = "Kitchen Sink (Thickness).xlsx"
DEFAULT_XLSX = "/Users/tehjayson/Desktop/Kitchen Sink ( Thickness) .xlsx"

ACTOR = {"email": "kitchen-sink-thickness-loader"}

SURFACE_TEXTURE_VALUES = ["normal", "honeycomb", "nano_volcano", "nano_grain", "andria_series"]

# Up to this many existing catalog codes are shown for an unmatched sheet code.
NEAR_VARIANT_LIMIT = 5


class SpecValueError(ValueError):
    """A parsed value the registry will not accept - reported, never forced in."""


def _reject(message: str) -> SpecValueError:
    return SpecValueError(message)


# --------------------------------------------------------------------------- #
# thickness text
# --------------------------------------------------------------------------- #
class ThicknessParseError(ValueError):
    """The thickness text is not one of the forms measured in the real workbook."""


_NUM = r"(\d+(?:\.\d+)?)"
_BOARD_RE = re.compile(r"面板\s*[:：]?\s*" + _NUM)
_BOWL_RE = re.compile(r"盆胆\s*[:：]?\s*" + _NUM)
_GENERAL_RE = re.compile(r"厚度\s*[:：]?\s*" + _NUM)
# The unit is optional: a numeric-typed Excel cell arrives as a bare number with no
# "mm" text at all (e.g. `str(0.9)` == "0.9"), and it means the same thing as "0.9mm".
_BARE_RE = re.compile(r"^" + _NUM + r"\s*(?:mm)?\s*$", re.IGNORECASE)


def parse_thickness_text(text: str) -> dict[str, float]:
    """{"board_thickness": ..., "thickness": ...} (either key may be absent).

    Forms measured in the real file: "面板3mm, 盆胆 0.8mm", "面板3.0mm, 盆胆 0.7mm",
    "面板2.5mm, 盆胆 0.7mm", "面板:2.7盆胆:0.7", "面板 3.0 + 盆胆 0.7", "厚度 0.5",
    "0.9mm", "0.9mm " (trailing space), "1.15mm", "2.5mm", and a bare numeric cell
    such as "0.9". 面板 and the bowl figure are read independently, so a cell that
    somehow carries both "面板 N" and "厚度 M" (no 盆胆) keeps both rather than the
    厚度 figure being silently dropped in favour of the board one. Anything that
    yields neither raises ThicknessParseError.
    """
    stripped = (text or "").strip()
    if not stripped:
        raise ThicknessParseError("blank")

    result: dict[str, float] = {}
    board_match = _BOARD_RE.search(stripped)
    if board_match:
        result["board_thickness"] = float(board_match.group(1))

    bowl_match = _BOWL_RE.search(stripped)
    if bowl_match:
        result["thickness"] = float(bowl_match.group(1))
    else:
        general_match = _GENERAL_RE.search(stripped)
        if general_match:
            result["thickness"] = float(general_match.group(1))
        else:
            bare_match = _BARE_RE.match(stripped)
            if bare_match:
                result["thickness"] = float(bare_match.group(1))

    if not result:
        raise ThicknessParseError(stripped)
    return result


# --------------------------------------------------------------------------- #
# steel grade
# --------------------------------------------------------------------------- #
class SteelGradeParseError(ValueError):
    """The steel/material text names neither 304 nor 201."""


def parse_steel_grade(text: str) -> str:
    """"304" or "201" out of "SUS201", "SUS304", or "Stainless Steel 201 " - the
    only forms measured in the real file, and the only two `steel_grade` allows.
    """
    stripped = (text or "").strip()
    if not stripped:
        raise SteelGradeParseError("blank")
    if "304" in stripped:
        return "304"
    if "201" in stripped:
        return "201"
    raise SteelGradeParseError(stripped)


# --------------------------------------------------------------------------- #
# finish, grouped by cell fill colour
# --------------------------------------------------------------------------- #
def slug_finish(text: str) -> str:
    collapsed = re.sub(r"\s+", " ", (text or "").strip())
    return collapsed.lower().replace(" ", "_")


def _fill_key(cell) -> Optional[str]:
    fill = cell.fill
    if fill is None or getattr(fill, "fill_type", None) != "solid":
        return None
    rgb = getattr(fill.fgColor, "rgb", None)
    return rgb if isinstance(rgb, str) else None


def finish_labels_by_row(ws, col: int, rows: list[int]) -> dict[int, Optional[str]]:
    """row -> slugged finish (or None), grouped by contiguous solid fill colour.

    `rows` is every data row IN ORDER with a code already present - contiguity is
    over THIS sequence, not raw spreadsheet row numbers, so a colour band that
    happens to skip a blank-code row in between is still read as one band. A
    group with no non-blank label anywhere in it writes no finish.
    """
    groups: list[list[int]] = []
    current_key: Any = object()
    current_group: list[int] = []
    for row in rows:
        key = _fill_key(ws.cell(row=row, column=col))
        if key != current_key:
            if current_group:
                groups.append(current_group)
            current_key = key
            current_group = [row]
        else:
            current_group.append(row)
    if current_group:
        groups.append(current_group)

    result: dict[int, Optional[str]] = {}
    for group in groups:
        labels = []
        for r in group:
            value = ws.cell(row=r, column=col).value
            if value not in (None, ""):
                labels.append(str(value).strip())
        finish = slug_finish(" ".join(labels)) if labels else None
        for r in group:
            result[r] = finish
    return result


# --------------------------------------------------------------------------- #
# codes
# --------------------------------------------------------------------------- #
_PAREN_SUFFIX_RE = re.compile(r"\s*\([^)]*\)\s*$")


def normalise_sheet_code(raw: Any) -> str:
    text = str(raw).strip() if raw is not None else ""
    text = _PAREN_SUFFIX_RE.sub("", text).strip()
    return text.upper()


# --------------------------------------------------------------------------- #
# sheet layouts
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SheetLayout:
    thickness_col: int
    steel_col: Optional[int] = None
    material_col: Optional[int] = None
    finish_col: Optional[int] = None


SHEET_LAYOUTS: dict[str, SheetLayout] = {
    "Sorento": SheetLayout(thickness_col=2, material_col=3),
    "Cabana": SheetLayout(thickness_col=2, material_col=3),
    "Mocha": SheetLayout(thickness_col=3, steel_col=2, finish_col=4),
    "Iborn": SheetLayout(thickness_col=3, steel_col=2, finish_col=4),
}


@dataclass
class RowResult:
    sheet: str
    row: int
    code: str
    entries: dict[str, Any] = field(default_factory=dict)
    parse_failure: Optional[str] = None
    blank: bool = False


def parse_sheet(ws, layout: SheetLayout, sheet_key: str) -> list[RowResult]:
    data_rows = [
        r for r in range(2, ws.max_row + 1)
        if ws.cell(row=r, column=1).value not in (None, "")
    ]
    finish_by_row: dict[int, Optional[str]] = {}
    if layout.finish_col:
        finish_by_row = finish_labels_by_row(ws, layout.finish_col, data_rows)

    results: list[RowResult] = []
    for r in data_rows:
        code = normalise_sheet_code(ws.cell(row=r, column=1).value)
        if not code:
            results.append(
                RowResult(
                    sheet=sheet_key, row=r, code="",
                    parse_failure="code is empty once normalised (blank, or nothing "
                    "left after the parenthetical suffix was dropped)",
                )
            )
            continue

        thickness_raw = ws.cell(row=r, column=layout.thickness_col).value
        thickness_text = str(thickness_raw).strip() if thickness_raw is not None else ""

        steel_text = ""
        if layout.steel_col:
            raw = ws.cell(row=r, column=layout.steel_col).value
            steel_text = str(raw).strip() if raw is not None else ""

        material_text = ""
        if layout.material_col:
            raw = ws.cell(row=r, column=layout.material_col).value
            material_text = str(raw).strip() if raw is not None else ""

        finish = finish_by_row.get(r)

        entries: dict[str, Any] = {}
        failures: list[str] = []

        if thickness_text:
            try:
                entries.update(parse_thickness_text(thickness_text))
            except ThicknessParseError:
                failures.append(f"thickness text {thickness_text!r} does not parse")

        steel_source = steel_text or material_text
        if steel_source:
            try:
                grade = parse_steel_grade(steel_source)
                entries["steel_grade"] = grade
                entries["material"] = "stainless_steel"
            except SteelGradeParseError:
                failures.append(f"steel/material text {steel_source!r} does not parse")

        if finish:
            entries["surface_texture"] = finish

        if failures:
            results.append(
                RowResult(sheet=sheet_key, row=r, code=code, parse_failure="; ".join(failures))
            )
            continue

        if not entries:
            results.append(RowResult(sheet=sheet_key, row=r, code=code, blank=True))
            continue

        results.append(RowResult(sheet=sheet_key, row=r, code=code, entries=entries))
    return results


def dedupe_rows(
    rows: list[RowResult],
) -> tuple[dict[str, dict], dict[str, tuple[str, int]], list[tuple[str, list[tuple[str, int]]]]]:
    """to_write (code -> entries), origin (code -> the (sheet, row) that writes it),
    conflicts (code -> every (sheet, row) that disagreed).

    Takes every row handed to it as ONE pool, so calling it with every sheet's rows
    together applies a single rule to a duplicate code whether its two copies sit
    on the same sheet or on different ones: seen more than once with IDENTICAL
    parsed entries, it writes once, from its first occurrence in the list. Seen
    with DIFFERENT entries anywhere, it is a conflict - reported, and it does not
    write at all, even where one of its copies would otherwise have been fine.
    """
    ok_rows = [r for r in rows if not r.parse_failure and not r.blank]
    by_code: dict[str, list[RowResult]] = {}
    for r in ok_rows:
        by_code.setdefault(r.code, []).append(r)

    to_write: dict[str, dict] = {}
    origin: dict[str, tuple[str, int]] = {}
    conflicts: list[tuple[str, list[tuple[str, int]]]] = []
    for code, group in by_code.items():
        first = group[0].entries
        if all(g.entries == first for g in group):
            to_write[code] = first
            origin[code] = (group[0].sheet, group[0].row)
        else:
            conflicts.append((code, [(g.sheet, g.row) for g in group]))
    return to_write, origin, conflicts


# --------------------------------------------------------------------------- #
# registry keys
# --------------------------------------------------------------------------- #
_NEW_KEY_DEFS: dict[str, dict] = {
    "board_thickness": {
        "spec_key": "board_thickness",
        "label": "Drainer board / countertop thickness",
        "data_type": "numeric",
        "unit": "mm",
        "allowed_values": [],
        "applies_when": {"class": ["Kitchen Sink"]},
        "user_synonyms": {
            "_self": [
                "board thickness", "drainer board thickness",
                "countertop thickness", "panel thickness", "面板",
            ]
        },
        "value_labels": {},
    },
    "surface_texture": {
        "spec_key": "surface_texture",
        "label": "Surface texture",
        "data_type": "enum",
        "unit": None,
        "allowed_values": SURFACE_TEXTURE_VALUES,
        "applies_when": {"class": ["Kitchen Sink"]},
        "user_synonyms": {
            "_self": ["surface texture", "texture", "surface finish"],
            "normal": ["normal", "plain", "smooth"],
            "honeycomb": ["honeycomb", "honey comb", "hc"],
            "nano_volcano": ["nano volcano", "volcano", "nano"],
            "nano_grain": ["nano grain", "nanograin", "grain"],
            "andria_series": ["andria", "andria series"],
        },
        "value_labels": {
            "normal": "Normal",
            "honeycomb": "Honeycomb",
            "nano_volcano": "Nano Volcano",
            "nano_grain": "Nano Grain",
            "andria_series": "Andria Series",
        },
    },
}


def ensure_registry_keys(db: Session) -> dict:
    """Create `board_thickness` / `surface_texture` if missing, ORM-only, mirroring
    `create_spec_key` (`app/api/v1/master_data/spec_registry.py`): `source="user"`,
    `synonyms={}`, `match_tolerance`/`match_decay` from `default_match_window(unit)`,
    and the same `_validate_reachable` gate the route runs before `db.add`. Never
    touches a key that already exists.

    Always attempted, dry run included - `run()` holds everything in one
    transaction and rolls it back when not applying, so this INSERT is part of
    what a dry run proves would happen, not skipped and reported on faith.
    """
    from app.api.v1.master_data.spec_registry import _validate_reachable
    from app.models.product_spec import ProductSpecRegistry
    from app.services.product_spec_registry import SPEC_REGISTRY_SEED, default_match_window

    seed_by_key = {row["spec_key"]: row for row in SPEC_REGISTRY_SEED}
    rank_weights = {
        "board_thickness": seed_by_key["thickness"]["rank_weight"],
        "surface_texture": seed_by_key["finish"]["rank_weight"],
    }

    created: list[str] = []
    existing: list[str] = []
    for spec_key, definition in _NEW_KEY_DEFS.items():
        row = db.query(ProductSpecRegistry).filter_by(spec_key=spec_key).first()
        if row is not None:
            existing.append(spec_key)
            continue

        _validate_reachable(
            definition["data_type"], definition["allowed_values"], definition["user_synonyms"]
        )

        created.append(spec_key)
        tolerance, decay = default_match_window(definition["unit"])
        db.add(
            ProductSpecRegistry(
                spec_key=spec_key,
                label=definition["label"],
                data_type=definition["data_type"],
                unit=definition["unit"],
                allowed_values=definition["allowed_values"],
                synonyms={},
                user_synonyms=definition["user_synonyms"],
                applies_when=definition["applies_when"],
                rank_weight=rank_weights[spec_key],
                is_active=True,
                match_tolerance=tolerance,
                match_decay=decay,
                source="user",
                value_labels=definition["value_labels"],
            )
        )
    if created:
        db.flush()
    return {"created": created, "existing": existing}


def _registry_row(db: Session, spec_key: str):
    """The live registry row. `ensure_registry_keys` has already created and
    flushed `board_thickness` / `surface_texture` by the time anything in this
    module calls this, so it is a plain lookup, never a fallback construction.
    """
    from app.models.product_spec import ProductSpecRegistry

    row = db.query(ProductSpecRegistry).filter_by(spec_key=spec_key).first()
    if row is None:
        raise SystemExit(
            f"no registry row for {spec_key!r} - run seed_spec_registry first for a "
            f"seeded key, or ensure_registry_keys for a key this loader creates."
        )
    return row


# --------------------------------------------------------------------------- #
# products
# --------------------------------------------------------------------------- #
def load_product_codes(db: Session) -> dict[str, str]:
    """normalised(code) -> the EXACT `product_code` stored in `products`, across
    every company - `apply_spec_values` fans a code out to every company copy
    itself, so existing in ANY one company is enough to say the code is real.
    """
    from app.models.product import Product

    codes: dict[str, str] = {}
    for (code,) in db.query(Product.product_code).distinct():
        if code is None:
            continue
        key = code.strip().upper()
        codes.setdefault(key, code.strip())
    return codes


def _near_variants(db: Session, code: str, limit: int = NEAR_VARIANT_LIMIT) -> list[str]:
    """Up to `limit` catalog codes starting with an unmatched sheet code, so the
    owner can see whether it is a suffix the sheet dropped or a variant that was
    never in the catalog at all, rather than a bare "unmatched"."""
    from app.models.product import Product

    rows = (
        db.query(Product.product_code)
        .filter(Product.product_code.ilike(f"{code}%"))
        .distinct()
        .order_by(Product.product_code)
        .limit(limit)
        .all()
    )
    return [r[0] for r in rows]


def _existing_thickness(db: Session, product_code: str) -> Optional[float]:
    from app.models.product import Product
    from app.models.product_spec import ProductSpecifications

    spec = (
        db.query(ProductSpecifications)
        .join(Product, Product.id == ProductSpecifications.product_id)
        .filter(Product.product_code == product_code)
        .order_by(Product.id)
        .first()
    )
    if spec is None or not spec.values:
        return None
    entry = spec.values.get("thickness")
    if not isinstance(entry, dict):
        return None
    try:
        return float(entry.get("value"))
    except (TypeError, ValueError):
        return None


def _exception_scalar(entry: Any) -> Any:
    if isinstance(entry, dict):
        return entry.get("value")
    return entry


def _open_conflict_exceptions(db: Session, product_code: str) -> dict[str, dict]:
    """spec_key -> {"proposed": ..., "stored": ...} for this code's OPEN
    `human_override_conflict` exceptions, right now. `derive_for_code` rebuilds a
    code's whole open-exception set on every write (delete, then re-add whatever
    is still true), so comparing this snapshot before and against after a write is
    what tells a conflict THIS run opened apart from one that already existed and
    was merely re-materialised with a new id.
    """
    from app.models.product_spec import ProductSpecException
    from app.services.product_spec_write import CONFLICT_REASON

    rows = (
        db.query(ProductSpecException)
        .filter(
            ProductSpecException.product_code == product_code,
            ProductSpecException.resolved_at.is_(None),
            ProductSpecException.reason == CONFLICT_REASON,
        )
        .all()
    )
    return {r.spec_key: {"proposed": r.proposed, "stored": r.stored} for r in rows}


# --------------------------------------------------------------------------- #
# the write
# --------------------------------------------------------------------------- #
def _entries_for(db: Session, sheet_display: str, row: int, spec_values: dict) -> list[dict]:
    from app.services.product_spec_registry import value_for_registry

    entries: list[dict] = []
    for spec_key, raw_value in spec_values.items():
        row_obj = _registry_row(db, spec_key)
        value = value_for_registry(row_obj, raw_value, _reject)
        entries.append(
            {
                "spec_key": spec_key,
                "op": "set",
                "value": value,
                "unit": row_obj.unit or None,
                "source": "human",
                "evidence": f"{WORKBOOK_LABEL} / {sheet_display} row {row}",
            }
        )
    return entries


@dataclass
class SheetReport:
    sheet: str
    rows: int = 0
    matched: int = 0
    written: int = 0
    unmatched: list[str] = field(default_factory=list)
    unmatched_near: dict[str, list[str]] = field(default_factory=dict)
    blank_rows: list[int] = field(default_factory=list)
    parse_failures: list[tuple[int, str, str]] = field(default_factory=list)
    conflicts: list[tuple[str, list[tuple[str, int]]]] = field(default_factory=list)
    write_failures: list[tuple[str, str]] = field(default_factory=list)
    differs_from_sheet: list[str] = field(default_factory=list)
    new_exceptions: list[tuple[str, str, Any, Any]] = field(default_factory=list)


def run(db: Session, xlsx_path: str, *, apply: bool, only_sheet: Optional[str] = None) -> dict:
    from app.models.base import company_scope
    from app.services.error_handler import AppException
    from app.services.product_spec_derivation import (
        configured_max_values,
        configured_rules,
        configured_scopes,
    )
    from app.services.product_spec_write import apply_spec_values

    with company_scope(db, None):
        wb = openpyxl.load_workbook(xlsx_path)

        registry_report = ensure_registry_keys(db)

        for key in ("thickness", "material", "steel_grade"):
            _registry_row(db, key)

        product_codes = load_product_codes(db)
        rules_by_key = configured_rules(db)
        scopes_by_key = configured_scopes(db)
        max_values = configured_max_values(db)

        only_key = only_sheet.strip() if only_sheet else None

        # Pass 1: parse every included sheet. Rows/blanks/parse-failures stay
        # per-sheet (they never need cross-sheet context); the pool of writable
        # rows is deduped as ONE list below, so a duplicate code is treated the
        # same whether its two copies share a sheet or not.
        per_sheet_rows: dict[str, list[RowResult]] = {}
        all_rows: list[RowResult] = []
        for sheet_name in wb.sheetnames:
            key = sheet_name.strip()
            if key not in SHEET_LAYOUTS:
                continue
            if only_key and key.lower() != only_key.lower():
                continue
            ws = wb[sheet_name]
            rows = parse_sheet(ws, SHEET_LAYOUTS[key], key)
            per_sheet_rows[key] = rows
            all_rows.extend(rows)

        to_write, origin, conflicts = dedupe_rows(all_rows)

        sheet_reports: dict[str, SheetReport] = {}
        any_parse_failure = False
        for key, rows in per_sheet_rows.items():
            report = SheetReport(sheet=key, rows=len(rows))
            report.blank_rows = [r.row for r in rows if r.blank]
            report.parse_failures = [
                (r.row, r.code, r.parse_failure) for r in rows if r.parse_failure
            ]
            if report.parse_failures:
                any_parse_failure = True
            sheet_reports[key] = report

        # A conflict is attributed to every sheet one of its copies touched, so
        # the owner sees it from whichever sheet's summary they read first.
        for code, locations in conflicts:
            for sheet_key in sorted({loc[0] for loc in locations}):
                sheet_reports[sheet_key].conflicts.append((code, locations))

        for code, spec_values in to_write.items():
            sheet_key, row = origin[code]
            report = sheet_reports[sheet_key]

            db_code = product_codes.get(code)
            if db_code is None:
                report.unmatched.append(code)
                report.unmatched_near[code] = _near_variants(db, code)
                continue
            report.matched += 1

            existing = _existing_thickness(db, db_code)
            if "thickness" in spec_values and existing is not None and existing != float(
                spec_values["thickness"]
            ):
                report.differs_from_sheet.append(db_code)

            before_exceptions = _open_conflict_exceptions(db, db_code)
            try:
                entries = _entries_for(db, sheet_key, row, spec_values)
                apply_spec_values(
                    db,
                    db_code,
                    entries,
                    actor=ACTOR,
                    commit=False,
                    rules_by_key=rules_by_key,
                    scopes_by_key=scopes_by_key,
                    max_values=max_values,
                )
            except (AppException, SpecValueError) as exc:
                message = exc.detail.get("message") if isinstance(exc, AppException) else str(exc)
                report.write_failures.append((db_code, str(message)))
                continue

            report.written += 1

            after_exceptions = _open_conflict_exceptions(db, db_code)
            for spec_key, data in after_exceptions.items():
                if before_exceptions.get(spec_key) != data:
                    report.new_exceptions.append(
                        (
                            db_code,
                            spec_key,
                            _exception_scalar(data["stored"]),
                            _exception_scalar(data["proposed"]),
                        )
                    )

        if apply:
            db.commit()
        else:
            db.rollback()

        return {
            "mode": "APPLIED" if apply else "DRY-RUN (rolled back)",
            "registry": registry_report,
            "sheets": list(sheet_reports.values()),
            "any_parse_failure": any_parse_failure,
        }


def _print_report(report: dict) -> None:
    print(f"mode: {report['mode']}")
    reg = report["registry"]
    print(f"registry keys created: {reg['created'] or 'none'}")
    print(f"registry keys already present: {reg['existing'] or 'none'}")

    write_label = "written" if report["mode"] == "APPLIED" else "would write"

    for s in report["sheets"]:
        print(f"\n=== {s.sheet} ===")
        print(f"rows:              {s.rows}")
        print(f"matched:           {s.matched}")
        print(f"{write_label + ':':<19}{s.written}")
        print(f"unmatched:         {len(s.unmatched)}")
        print(f"blank:             {len(s.blank_rows)}")
        print(f"parse failures:    {len(s.parse_failures)}")
        print(f"conflicts:         {len(s.conflicts)}")
        print(f"write failures:    {len(s.write_failures)}")
        print(f"exceptions opened: {len(s.new_exceptions)}")
        if s.differs_from_sheet:
            print(
                f"already carry a different thickness ({len(s.differs_from_sheet)}): "
                f"{', '.join(s.differs_from_sheet)}"
            )
        if s.unmatched:
            print("unmatched codes:")
            for code in s.unmatched:
                near = s.unmatched_near.get(code) or []
                if near:
                    print(f"  {code}: close matches in the catalog: {', '.join(near)}")
                else:
                    print(f"  {code}: no close matches in the catalog")
        if s.blank_rows:
            print(f"blank rows: {', '.join(str(r) for r in s.blank_rows)}")
        if s.parse_failures:
            print("parse failures:")
            for row, code, reason in s.parse_failures:
                print(f"  row {row} ({code}): {reason}")
        if s.conflicts:
            print("conflicts:")
            for code, locations in s.conflicts:
                where = ", ".join(f"{sheet} row {row}" for sheet, row in locations)
                print(f"  {code}: {where} disagree")
        if s.write_failures:
            print("write failures:")
            for code, reason in s.write_failures:
                print(f"  {code}: {reason}")
        if s.new_exceptions:
            print("exceptions opened (sheet value vs. what derivation would pick):")
            for code, spec_key, stored, proposed in s.new_exceptions:
                print(f"  {code}: {spec_key} - sheet says {stored!r}, derived says {proposed!r}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--xlsx", default=DEFAULT_XLSX, help="Path to the workbook.")
    parser.add_argument("--apply", action="store_true", help="Write the changes. Default is dry-run.")
    parser.add_argument("--sheet", default=None, help="Limit the run to one sheet (e.g. Mocha).")
    args = parser.parse_args()
    apply_changes = bool(args.apply)

    if not os.path.exists(args.xlsx):
        print(f"no workbook at {args.xlsx!r}")
        return 1

    from app.database import SessionLocal
    from app.services.company_scope import register_company_scope_listeners

    register_company_scope_listeners()

    db = SessionLocal()
    try:
        report = run(db, args.xlsx, apply=apply_changes, only_sheet=args.sheet)
        _print_report(report)
        return 1 if report["any_parse_failure"] else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
