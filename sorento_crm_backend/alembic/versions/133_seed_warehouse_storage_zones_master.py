"""Seed warehouse + storage zone master (Loc / warehouse / remarks).

Revision ID: 133_seed_warehouse_storage_zones_master
Revises: 132_conversation_sla_tracking_message_id
Create Date: 2026-04-07
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "133_seed_warehouse_storage_zones_master"
down_revision = "132_conversation_sla_tracking_message_id"
branch_labels = None
depends_on = None

# (loc_code, warehouse_key_from_sheet, remarks, remarks2)
# warehouse_key_from_sheet "-" -> logical warehouse code NA (unassigned)
_ROWS: list[tuple[str, str, str, str]] = [
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


def _ensure_warehouse(conn: sa.Connection, code: str, display_name: str) -> str:
    row = conn.execute(
        sa.text("SELECT id FROM warehouses WHERE warehouse_code = :c LIMIT 1"),
        {"c": code},
    ).fetchone()
    if row:
        return str(row[0])
    wid = str(uuid.uuid4())
    conn.execute(
        sa.text(
            """
            INSERT INTO warehouses (id, warehouse_code, warehouse_name, location, is_active)
            VALUES (:id, :code, :name, NULL, true)
            """
        ),
        {"id": wid, "code": code, "name": display_name},
    )
    return wid


def _zone_display_name(loc: str, remarks: str, r2: str) -> str:
    loc = loc.strip()
    r2 = (r2 or "").strip()
    remarks = (remarks or "").strip()
    base = f"{loc} ({r2})" if r2 else loc
    ru = remarks.upper()
    if remarks and ru not in ("STOCK", ""):
        return f"{base} — {remarks}"
    return base


def _db_zone_type(remarks: str) -> str:
    """Map spreadsheet remarks to storage_zones.zone_type (DB check allows shelf/rack/bin/pallet)."""
    r = (remarks or "").strip().upper()
    if r == "NOT ACTIVE":
        return "bin"
    if r == "NO STOCK":
        return "rack"
    # STOCK and anything else
    return "shelf"


def upgrade() -> None:
    conn = op.get_bind()

    distinct_codes = sorted({_wh_code(w) for _, w, _, _ in _ROWS})
    wh_ids: dict[str, str] = {}
    for code in distinct_codes:
        label = "N/A" if code == "NA" else code
        wh_ids[code] = _ensure_warehouse(conn, code, label)

    for loc, sheet_wh, remarks, r2 in _ROWS:
        wh_id = wh_ids[_wh_code(sheet_wh)]
        zname = _zone_display_name(loc, remarks, r2)
        ztype = _db_zone_type(remarks)
        exists = conn.execute(
            sa.text(
                "SELECT 1 FROM storage_zones WHERE warehouse_id = :wid AND zone_code = :zc LIMIT 1"
            ),
            {"wid": wh_id, "zc": loc},
        ).fetchone()
        if exists:
            continue
        zid = str(uuid.uuid4())
        conn.execute(
            sa.text(
                """
                INSERT INTO storage_zones (id, warehouse_id, zone_code, zone_name, zone_type, capacity)
                VALUES (:id, :wid, :code, :zname, :ztype, 0)
                """
            ),
            {"id": zid, "wid": wh_id, "code": loc, "zname": zname, "ztype": ztype},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for loc, sheet_wh, _, _ in _ROWS:
        code = _wh_code(sheet_wh)
        row = conn.execute(
            sa.text("SELECT id FROM warehouses WHERE warehouse_code = :c LIMIT 1"),
            {"c": code},
        ).fetchone()
        if not row:
            continue
        conn.execute(
            sa.text(
                "DELETE FROM storage_zones WHERE warehouse_id = :wid AND zone_code = :zc"
            ),
            {"wid": str(row[0]), "zc": loc},
        )
    codes_to_maybe_drop = sorted({_wh_code(w) for _, w, _, _ in _ROWS})
    for code in codes_to_maybe_drop:
        row = conn.execute(
            sa.text("SELECT id FROM warehouses WHERE warehouse_code = :c LIMIT 1"),
            {"c": code},
        ).fetchone()
        if not row:
            continue
        wid = str(row[0])
        remaining = conn.execute(
            sa.text("SELECT 1 FROM storage_zones WHERE warehouse_id = :wid LIMIT 1"),
            {"wid": wid},
        ).fetchone()
        if remaining:
            continue
        conn.execute(sa.text("DELETE FROM warehouses WHERE id = :id"), {"id": wid})
