"""Tests for the email rate limiter — global / per-recipient / per-event override.

DB fallback path is used so we don't need a Redis instance. The fallback counts
`email_outbox` rows with `status=sent` inside the window — same semantics as the Redis
sliding window when Redis is unavailable.
"""
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

from app.services.email_rate_limiter import check, RateCheckResult


def _query_count_chain(db, count_value: int):
    """Set up db.query(...).filter(...)....count() -> count_value."""
    chain = MagicMock()
    chain.count.return_value = count_value
    chain.filter.return_value = chain
    db.query.return_value = chain


def test_check_allows_when_under_all_caps():
    db = MagicMock()
    _query_count_chain(db, 0)
    with patch("app.services.email_rate_limiter._redis_conn", return_value=None):
        result = check(
            db,
            event_key="password_reset",
            recipient_email="u@example.com",
            global_rate=10,
            global_window_seconds=60,
            per_recipient_rate=5,
            per_recipient_window_seconds=3600,
        )
    assert isinstance(result, RateCheckResult)
    assert result.allowed is True
    assert result.reason is None


def test_check_blocks_when_global_cap_hit():
    db = MagicMock()
    _query_count_chain(db, 60)
    with patch("app.services.email_rate_limiter._redis_conn", return_value=None):
        result = check(
            db,
            event_key="password_reset",
            recipient_email="u@example.com",
            global_rate=10,
            global_window_seconds=60,
            per_recipient_rate=100,
            per_recipient_window_seconds=3600,
        )
    assert result.allowed is False
    assert "cap_exceeded" in (result.reason or "")
    assert result.retry_after_seconds and result.retry_after_seconds > 0


def test_check_blocks_when_per_recipient_cap_hit_even_if_global_open():
    db = MagicMock()
    chain = MagicMock()
    chain.filter.return_value = chain
    chain.count.side_effect = [0, 20]
    db.query.return_value = chain
    with patch("app.services.email_rate_limiter._redis_conn", return_value=None):
        result = check(
            db,
            event_key="password_reset",
            recipient_email="u@example.com",
            global_rate=1000,
            global_window_seconds=60,
            per_recipient_rate=10,
            per_recipient_window_seconds=3600,
        )
    assert result.allowed is False
    assert "recipient_cap_exceeded" in (result.reason or "")


def test_check_skips_scope_when_cap_zero_or_negative():
    db = MagicMock()
    _query_count_chain(db, 0)
    with patch("app.services.email_rate_limiter._redis_conn", return_value=None):
        result = check(
            db,
            event_key="password_reset",
            recipient_email="u@example.com",
            global_rate=0,
            global_window_seconds=60,
            per_recipient_rate=0,
            per_recipient_window_seconds=3600,
        )
    assert result.allowed is True


def test_check_event_override_applies_first():
    db = MagicMock()
    chain = MagicMock()
    chain.filter.return_value = chain
    chain.count.side_effect = [5, 0, 0]
    db.query.return_value = chain
    with patch("app.services.email_rate_limiter._redis_conn", return_value=None):
        result = check(
            db,
            event_key="external_product_attachment",
            recipient_email="u@example.com",
            global_rate=1000,
            global_window_seconds=60,
            per_recipient_rate=1000,
            per_recipient_window_seconds=3600,
            event_rate_override=3,
            event_window_seconds_override=60,
        )
    assert result.allowed is False
    assert "event_cap_exceeded" in (result.reason or "")
