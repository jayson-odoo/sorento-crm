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


def _lookup_binding(db: Session, tenant_id: Optional[str], table: str, column: str):
    key = (tenant_id, table, column)
    now = time.time()
    if key in _cache:
        ts, payload = _cache[key]
        if now - ts < _TTL:
            return payload
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
