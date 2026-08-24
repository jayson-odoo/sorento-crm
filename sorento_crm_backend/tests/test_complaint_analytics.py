"""Service + endpoint tests for complaint aggregation analytics.

Covers GET /api/v1/complaints-management/complaints/analytics and
ComplaintService.complaint_analytics:
 - metric=count happy path (overall + group_by)
 - group_by=product ranks products by complaint count descending
    ('which product has the most complaints')
 - date_field=resolved_at + date window counts resolved complaints
    ('how many complaints were resolved last month') and ignores unresolved rows
 - group_by=status / month bucketing
 - validation: unknown metric / group_by / date_field raise 422 (AppException)
 - endpoint enforces auth (401/403 with no principal)

Runs against the live Postgres test DB: seed rows with a unique complaint_number
prefix, assert, clean up.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.main import app
from app.models.complaints import Complaint
from app.services.complaints_service import ComplaintService
from app.services.error_handler import AppException

PREFIX = "CANLY-"


def _cleanup() -> None:
    with engine.connect() as conn:
        try:
            conn.execute(
                text("DELETE FROM complaints WHERE complaint_number LIKE 'CANLY-%'")
            )
            conn.commit()
        except Exception:
            conn.rollback()


@pytest.fixture(autouse=True)
def _clean_state():
    _cleanup()
    yield
    _cleanup()


@pytest.fixture
def db() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _seed_one(
    db: Session,
    number: str,
    *,
    product_code: str,
    status: str = "new",
    complaint_date=None,
    resolved_at=None,
) -> Complaint:
    c = Complaint(
        id=str(uuid.uuid4()),
        complaint_number=number,
        product_code=product_code,
        status=status,
        complaint_date=complaint_date,
        resolved_at=resolved_at,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _seed(db: Session) -> None:
    # WIDGET-A: 3 complaints; WIDGET-B: 1 complaint (product ranking).
    _seed_one(db, f"{PREFIX}0001", product_code="WIDGET-A", complaint_date=date(2026, 6, 3))
    _seed_one(db, f"{PREFIX}0002", product_code="WIDGET-A", complaint_date=date(2026, 6, 9))
    _seed_one(
        db,
        f"{PREFIX}0003",
        product_code="WIDGET-A",
        status="closed",
        complaint_date=date(2026, 6, 20),
        resolved_at=datetime(2026, 6, 25, 10, 0, 0),
    )
    _seed_one(
        db,
        f"{PREFIX}0004",
        product_code="WIDGET-B",
        status="processed_by_cs",
        complaint_date=date(2026, 7, 1),
        resolved_at=datetime(2026, 7, 2, 9, 0, 0),
    )


def _only_prefixed(res: dict) -> dict:
    """Filter grouped rows down to WIDGET-* products so shared-DB noise can't
    perturb the assertions."""
    return {
        g["group_key"]: g["value"]
        for g in res["groups"]
        if str(g["group_key"]).lower().startswith("widget")
    }


def test_group_by_product_ranked_desc(db: Session) -> None:
    _seed(db)
    res = ComplaintService(db).complaint_analytics(metric="count", group_by="product")
    counts = _only_prefixed(res)
    assert counts.get("widget-a") == 3
    assert counts.get("widget-b") == 1
    # WIDGET-A must outrank WIDGET-B within the returned (desc-sorted) groups.
    widget_rows = [
        g for g in res["groups"] if str(g["group_key"]).lower().startswith("widget")
    ]
    assert widget_rows[0]["group_key"] == "widget-a"


def test_resolved_last_month_count(db: Session) -> None:
    _seed(db)
    # Complaints RESOLVED in June 2026 → only CANLY-0003 (WIDGET-A). CANLY-0004
    # resolved in July. Scoped by group_by=product so shared-DB rows can't leak
    # into the assertion.
    res = ComplaintService(db).complaint_analytics(
        metric="count",
        group_by="product",
        date_field="resolved_at",
        date_from="2026-06-01",
        date_to="2026-06-30",
    )
    assert res["date_field"] == "resolved_at"
    counts = _only_prefixed(res)
    assert counts.get("widget-a") == 1
    assert "widget-b" not in counts


def test_resolved_ignores_unresolved(db: Session) -> None:
    _seed(db)
    # Whole-year resolved window → one resolved row per widget (0003 + 0004); the
    # two UNRESOLVED WIDGET-A rows are excluded because resolved_at IS NULL (so
    # WIDGET-A counts 1 here, vs 3 when counting by complaint_date).
    res = ComplaintService(db).complaint_analytics(
        metric="count",
        group_by="product",
        date_field="resolved_at",
        date_from="2026",
        date_to="2026",
    )
    counts = _only_prefixed(res)
    assert counts.get("widget-a") == 1
    assert counts.get("widget-b") == 1


def test_group_by_status(db: Session) -> None:
    _seed(db)
    res = ComplaintService(db).complaint_analytics(metric="count", group_by="status")
    by_status = {g["group_key"]: g["value"] for g in res["groups"]}
    assert by_status.get("closed", 0) >= 1
    assert by_status.get("processed_by_cs", 0) >= 1


def test_group_by_month_on_complaint_date(db: Session) -> None:
    _seed(db)
    res = ComplaintService(db).complaint_analytics(metric="count", group_by="month")
    by_month = {g["group_key"]: g["value"] for g in res["groups"]}
    assert by_month.get("2026-06", 0) >= 3
    assert by_month.get("2026-07", 0) >= 1


def test_bad_metric_raises_422(db: Session) -> None:
    with pytest.raises(AppException) as exc:
        ComplaintService(db).complaint_analytics(metric="total_value")
    assert exc.value.status_code == 422


def test_bad_group_by_raises_422(db: Session) -> None:
    with pytest.raises(AppException) as exc:
        ComplaintService(db).complaint_analytics(metric="count", group_by="galaxy")
    assert exc.value.status_code == 422


def test_bad_date_field_raises_422(db: Session) -> None:
    with pytest.raises(AppException) as exc:
        ComplaintService(db).complaint_analytics(metric="count", date_field="whenever")
    assert exc.value.status_code == 422


def test_endpoint_requires_auth() -> None:
    with TestClient(app) as client:
        res = client.get(
            "/api/v1/complaints-management/complaints/analytics?metric=count"
        )
    assert res.status_code in (401, 403), res.text
