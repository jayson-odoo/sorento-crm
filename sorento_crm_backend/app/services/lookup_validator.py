from __future__ import annotations
import time
from typing import Optional
from sqlalchemy.orm import Session
from fastapi import status

from app.models.lookup import LookupBinding, LookupOption, LookupSet
from app.services.error_handler import AppException

_TTL = 60.0  # seconds
_cache: dict[tuple[Optional[str], str, str], tuple[float, Optional[tuple[str, set[str]]]]] = {}


def _cache_clear() -> None:
    _cache.clear()


_table_cache: dict[int, bool] = {}


def _lookup_tables_exist(bind) -> bool:
    """Whether `lookup_bindings` exists on this bind. The lookup validator runs
    inside flush listeners on every tracked write; a sqlite test bind with a
    subset schema lacks the table and would raise "no such table" on unrelated
    tests. Prod always has it (no-op there). Cached per-engine."""
    if bind is None:
        return False
    key = id(bind.engine if hasattr(bind, "engine") else bind)
    cached = _table_cache.get(key)
    if cached is None:
        from sqlalchemy import inspect as _sa_inspect

        try:
            cached = _sa_inspect(bind).has_table("lookup_bindings")
        except Exception:
            cached = False
        _table_cache[key] = cached
    return cached


def _lookup_binding(db: Session, tenant_id: Optional[str], table: str, column: str):
    key = (tenant_id, table, column)
    now = time.time()
    if key in _cache:
        ts, payload = _cache[key]
        if now - ts < _TTL:
            return payload
    if not _lookup_tables_exist(db.get_bind()):
        return None  # unbound schema (e.g. sqlite subset in tests) → not validated
    b = db.query(LookupBinding).filter(
        LookupBinding.tenant_id.is_(tenant_id),
        LookupBinding.table_name == table,
        LookupBinding.column_name == column,
    ).first()
    if not b:
        _cache[key] = (now, None)
        return None
    set_obj = db.query(LookupSet).filter(LookupSet.id == b.set_id).first()
    values = {v for (v,) in db.query(LookupOption.value).filter(
        LookupOption.set_id == b.set_id, LookupOption.is_active.is_(True)).all()}
    payload = (set_obj.set_key if set_obj else "", values)
    _cache[key] = (now, payload)
    return payload


def validate_lookup_value(db: Session, *, table: str, column: str, value, tenant_id: Optional[str] = None) -> None:
    if value is None:
        return  # NULL handled by nullability of underlying column
    payload = _lookup_binding(db, tenant_id, table, column)
    if payload is None:
        return  # not bound
    set_key, allowed = payload
    if str(value) not in allowed:
        raise AppException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            message=f"'{value}' is not a valid value for {set_key}",
            detail=f"set_key={set_key} field={column} hint=Call POST /api/v1/lookup/resolve to map a raw keyword.",
            code="invalid_lookup_value",
        )
