"""Shared Loc → warehouses master seed (one CRM warehouse row per location code)."""
from __future__ import annotations

import uuid
import sqlalchemy as sa

# (loc_code, warehouse_key_from_sheet, remarks, remarks2) — sheet Warehouse "-" → N/A
WAREHOUSE_MASTER_ROWS: list[tuple[str, str, str, str]] = [
    ("ACT-S", "WH3", "STOCK", ""),
    ("BRW", "BRW", "STOCK", "SHOW"),
    ("BRW-ACTS", "BRW", "STOCK", ""),
    ("BRW-AM", "BRW", "STOCK", ""),
    ("BRW-BB", "BRW", "STOCK", ""),
    ("BRW-CLR", "BRW", "STOCK", ""),
    ("BRW-DFCT", "BRW", "STOCK", ""),
    ("BRW-DISP", "BRW", "STOCK", ""),
    ("BRW-HOLD", "BRW", "STOCK", ""),
    ("BRW-HP", "BRW", "STOCK", ""),
    ("BRW-IB", "BRW", "STOCK", ""),
    ("BRW-IR", "BRW", "STOCK", ""),
    ("BRW-NTC", "BRW", "STOCK", ""),
    ("BRW-REWO", "BRW", "STOCK", ""),
    ("BRW-RSV", "BRW", "STOCK", ""),
    ("BRW-S/L", "BRW", "STOCK", ""),
    ("BRW-SMC", "BRW", "STOCK", ""),
    ("BRW-SYNT", "BRW", "STOCK", ""),
    ("CON", "BRW", "STOCK", ""),
    ("DC1", "DC1", "STOCK", ""),
    ("DC1-AM", "DC1", "STOCK", ""),
    ("DC1-BB", "DC1", "STOCK", ""),
    ("DC1-HOLD", "DC1", "STOCK", ""),
    ("DC1-HP", "DC1", "STOCK", ""),
    ("DC1-IB", "DC1", "STOCK", ""),
    ("DC1-IR", "DC1", "STOCK", ""),
    ("DC1-NTC", "DC1", "STOCK", ""),
    ("DC1-RSV", "DC1", "STOCK", ""),
    ("DC1-S/L", "DC1", "STOCK", ""),
    ("DC1-SMC", "DC1", "STOCK", ""),
    ("DISPLAY", "DC1", "STOCK", ""),
    ("HQ", "WH3", "STOCK", ""),
    ("JB SHOWR", "JB", "STOCK", ""),
    ("LOC1", "-", "NOT ACTIVE", ""),
    ("MAINTANC", "BRW", "STOCK", ""),
    ("MKT-D", "BRW", "STOCK", ""),
    ("MWH", "MWH", "STOCK", ""),
    ("MWH-ACT", "MWH", "STOCK", ""),
    ("MWH-AM", "MWH", "STOCK", ""),
    ("MWH-BB", "MWH", "STOCK", ""),
    ("MWH-DFCT", "MWH", "STOCK", ""),
    ("MWH-HOLD", "MWH", "STOCK", ""),
    ("MWH-HP", "MWH", "STOCK", ""),
    ("MWH-IB", "MWH", "STOCK", ""),
    ("MWH-IR", "MWH", "STOCK", ""),
    ("MWH-MOC", "MWH", "STOCK", ""),
    ("MWH-NTC", "MWH", "STOCK", ""),
    ("MWH-RSV", "MWH", "STOCK", ""),
    ("MWH-S/L", "MWH", "STOCK", ""),
    ("MWH-SMC", "MWH", "STOCK", ""),
    ("PARTS", "-", "NO STOCK", ""),
    ("PRJ-ACT", "WH3", "STOCK", ""),
    ("PRJ-JW", "WH3", "NOT ACTIVE", ""),
    ("REJ100%", "-", "NO STOCK", ""),
    ("REPAIR", "-", "NO STOCK", ""),
    ("RESERVE", "BRW", "STOCK", ""),
    ("REWORK", "-", "STOCK", ""),
    ("SHOWROOM", "BRW", "STOCK", ""),
    ("SPARE/P", "-", "NO STOCK", ""),
    ("STAGING", "BRW", "STOCK", ""),
    ("WH3", "WH3", "STOCK", ""),
    ("WH3-ACT", "WH3", "STOCK", ""),
    ("WH3-AM", "WH3", "STOCK", ""),
    ("WH3-BB", "WH3", "STOCK", ""),
    ("WH3-DFCT", "WH3", "STOCK", ""),
    ("WH3-HOLD", "WH3", "STOCK", ""),
    ("WH3-HP", "WH3", "STOCK", ""),
    ("WH3-IB", "WH3", "STOCK", ""),
    ("WH3-IR", "WH3", "STOCK", ""),
    ("WH3-NTC", "WH3", "STOCK", ""),
    ("WH3-RSV", "WH3", "STOCK", ""),
    ("WH3-S/L", "WH3", "STOCK", ""),
    ("WH3-SMC", "WH3", "STOCK", ""),
]


def _wh_code(sheet_wh: str) -> str:
    s = (sheet_wh or "").strip()
    if s == "-" or not s:
        return "NA"
    return s


def _warehouse_display_name(loc: str, remarks: str, r2: str) -> str:
    loc = loc.strip()
    r2 = (r2 or "").strip()
    remarks = (remarks or "").strip()
    base = f"{loc} ({r2})" if r2 else loc
    ru = remarks.upper()
    if remarks and ru not in ("STOCK", ""):
        return f"{base} — {remarks}"
    return base


def _location_value(sheet_wh: str) -> str:
    code = _wh_code(sheet_wh)
    return "N/A" if code == "NA" else code


def run_warehouse_master_seed(conn: sa.Connection, rows: list[tuple[str, str, str, str]] | None = None) -> None:
    """Idempotent: delete mistaken storage_zones (zone_code = Loc), upsert warehouses one per Loc."""
    data = rows if rows is not None else WAREHOUSE_MASTER_ROWS
    seed_locs = [loc for loc, _, _, _ in data]

    for zc in seed_locs:
        conn.execute(sa.text("DELETE FROM storage_zones WHERE zone_code = :zc"), {"zc": zc})

    for loc, sheet_wh, remarks, r2 in data:
        name = _warehouse_display_name(loc, remarks, r2)
        loc_val = _location_value(sheet_wh)
        row = conn.execute(
            sa.text("SELECT id FROM warehouses WHERE warehouse_code = :c LIMIT 1"),
            {"c": loc},
        ).fetchone()
        if row:
            # Keep existing display names; only align site grouping (sheet Warehouse column).
            conn.execute(
                sa.text("UPDATE warehouses SET location = :loc WHERE id = :id"),
                {"loc": loc_val, "id": str(row[0])},
            )
            continue
        wid = str(uuid.uuid4())
        conn.execute(
            sa.text(
                """
                INSERT INTO warehouses (id, warehouse_code, warehouse_name, location, is_active)
                VALUES (:id, :code, :name, :loc, true)
                """
            ),
            {"id": wid, "code": loc, "name": name, "loc": loc_val},
        )


def downgrade_warehouse_master_seed(conn: sa.Connection, rows: list[tuple[str, str, str, str]] | None = None) -> None:
    data = rows if rows is not None else WAREHOUSE_MASTER_ROWS
    for loc, _, _, _ in data:
        conn.execute(
            sa.text("DELETE FROM warehouses WHERE warehouse_code = :c"),
            {"c": loc},
        )
