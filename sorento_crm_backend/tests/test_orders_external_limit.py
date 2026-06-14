"""External/agent order-limit policy.

- date filter present  → lift to the date-scoped max (return the whole window)
- no date filter        → keep the tight top-N cap
- non-external caller   → limit unchanged
"""
from __future__ import annotations

from app.api.v1.order_management.orders import (
    _EXTERNAL_ORDERS_DATE_SCOPED_LIMIT,
    _external_orders_limit,
    _has_orders_date_filter,
)


class _Req:
    def __init__(self, key):
        self.headers = {"X-API-Key": key} if key else {}


def _patch_key(monkeypatch, value="test"):
    import app.api.v1.order_management.orders as mod
    monkeypatch.setattr(mod.app_settings, "external_api_key", value, raising=False)


def test_has_date_filter_detects_any_value():
    assert _has_orders_date_filter(None, "2026-01-01", None, None) is True
    assert _has_orders_date_filter("", "  ", None) is False
    assert _has_orders_date_filter(None, None) is False


def test_external_no_date_filter_capped(monkeypatch):
    _patch_key(monkeypatch)
    assert _external_orders_limit(_Req("test"), 50, cap=20, date_scoped=False) == 20
    assert _external_orders_limit(_Req("test"), 5, cap=20, date_scoped=False) == 5


def test_external_with_date_filter_lifts_cap(monkeypatch):
    _patch_key(monkeypatch)
    assert _external_orders_limit(_Req("test"), 50, cap=20, date_scoped=True) == _EXTERNAL_ORDERS_DATE_SCOPED_LIMIT


def test_non_external_caller_unchanged(monkeypatch):
    _patch_key(monkeypatch)
    # no api key header → not external → limit untouched even without a date filter
    assert _external_orders_limit(_Req(None), 500, cap=20, date_scoped=False) == 500
