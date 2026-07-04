"""Round-trip test for the M2/M2.5 system-settings columns (PLAN §9 S4).

Asserts the general-settings PUT impl applies, and the GET serializer's
``getattr`` contract surfaces, the new AI-trace / role-split columns:
``ai_trace_ttl_days``, ``ai_trace_error_ttl_days``,
``ai_trace_max_payload_bytes``, ``ai_assistant_role_split_enabled``.

The full ``get_settings`` route is an async endpoint behind auth deps, so we
exercise the plain ``_update_general_settings_impl(settings_data, db)`` callable
against in-memory SQLite and read the persisted row back the same way the GET
serializer does (``getattr`` with defaults).
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.user_management.settings import (
    SystemSettingUpdate,
    _update_general_settings_impl,
)
from app.database import Base
from app.models.audit import AuditLog
from app.models.lookup import LookupBinding
from app.models.user import SystemSetting


@compiles(JSONB, "sqlite")  # type: ignore[misc]
def _jsonb_sqlite(_type_, _compiler, **_kw):  # noqa: D401, ANN001
    return "TEXT"


@compiles(ARRAY, "sqlite")  # type: ignore[misc]
def _array_sqlite(_type_, _compiler, **_kw):  # noqa: D401, ANN001
    return "TEXT"


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[SystemSetting.__table__, LookupBinding.__table__, AuditLog.__table__],
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_general_settings_put_round_trips_ai_trace_columns(db: Session):
    # Seed the singleton row with column defaults.
    db.add(SystemSetting(id="ss-1"))
    db.commit()

    payload = SystemSettingUpdate(
        ai_trace_ttl_days=14,
        ai_trace_error_ttl_days=45,
        ai_trace_max_payload_bytes=32768,
        ai_assistant_role_split_enabled=True,
    )
    result = _update_general_settings_impl(payload, db)
    assert result["message"] == "General settings updated successfully"

    # Read back exactly as the GET serializer does (getattr with defaults).
    row = db.query(SystemSetting).first()
    assert getattr(row, "ai_trace_ttl_days", 30) == 14
    assert getattr(row, "ai_trace_error_ttl_days", 90) == 45
    assert getattr(row, "ai_trace_max_payload_bytes", 16384) == 32768
    assert getattr(row, "ai_assistant_role_split_enabled", False) is True


def test_general_settings_put_partial_update_leaves_others(db: Session):
    db.add(
        SystemSetting(
            id="ss-1",
            ai_trace_ttl_days=30,
            ai_trace_error_ttl_days=90,
            ai_trace_max_payload_bytes=16384,
            ai_assistant_role_split_enabled=False,
        )
    )
    db.commit()

    # Only flip the role-split flag — exclude_unset must not clobber the rest.
    _update_general_settings_impl(
        SystemSettingUpdate(ai_assistant_role_split_enabled=True), db
    )

    row = db.query(SystemSetting).first()
    assert row.ai_assistant_role_split_enabled is True
    assert row.ai_trace_ttl_days == 30
    assert row.ai_trace_error_ttl_days == 90
    assert row.ai_trace_max_payload_bytes == 16384
