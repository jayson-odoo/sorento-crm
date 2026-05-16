"""Helpers for the configurable Excel uploader extension allow-list."""
from __future__ import annotations

from typing import Tuple

from sqlalchemy.orm import Session

from app.models.user import SystemSetting

_DEFAULT_RAW = ".xlsx,.xls,.xlsm"


def _normalize(raw: str | None) -> Tuple[str, ...]:
    if not raw:
        raw = _DEFAULT_RAW
    parts: list[str] = []
    for piece in str(raw).split(","):
        ext = piece.strip().lower()
        if not ext:
            continue
        if not ext.startswith("."):
            ext = "." + ext
        parts.append(ext)
    return tuple(parts) or (".xlsx", ".xls", ".xlsm")


def get_excel_accept_extensions(db: Session) -> Tuple[str, ...]:
    """Return tuple of accepted extensions (e.g. ('.xlsx', '.xls'))."""
    row = db.query(SystemSetting.excel_upload_accept_extensions).first()
    raw = row[0] if row else None
    return _normalize(raw)


def get_excel_accept_label(db: Session) -> str:
    """Human-readable label (e.g. '.xlsx or .xls')."""
    exts = get_excel_accept_extensions(db)
    if len(exts) == 1:
        return exts[0]
    return ", ".join(exts[:-1]) + f" or {exts[-1]}"
