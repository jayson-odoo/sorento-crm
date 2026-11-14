"""Store UI v2 page views (UI-V2 phase 0, D10). Mirrors client_error_report_service.

Every limit lives here so a test can reach it without an HTTP round-trip:
- the raw body is refused above ``MAX_BODY_BYTES`` (checked by the route while streaming);
- a batch holds 1 to ``MAX_ITEMS`` items;
- a user gets ``RATE_LIMIT_PER_HOUR`` posts per rolling hour, counted from this table
  (the table is the counter: every row of one post shares one created_at, so the count is of
  DISTINCT created_at values, i.e. posts).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Iterable, Optional
from urllib.parse import urlsplit

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.ui_page_view import UiPageView

MAX_BODY_BYTES = 16 * 1024
MAX_ITEMS = 50
MAX_MS = 600000
MAX_ROUTE = 200
RATE_LIMIT_PER_HOUR = 120
# 120 posts x the hook's batch size of 10: a ceiling on rows, so a few 50-item posts cannot fill the table.
ROW_LIMIT_PER_HOUR = 1200
RETENTION_DAYS = 90
VIEWPORTS = ("phone", "tablet", "desktop")

_ROUTE_CHARS = re.compile(r"^[A-Za-z0-9/_\-\[\].]*$")


def route_path(raw: Optional[str]) -> str:
    """The path of a posted route, query and fragment dropped."""
    path = urlsplit(str(raw or "")).path or "/"
    return path if path.startswith("/") else "/" + path


def is_valid_route(raw: Optional[str]) -> bool:
    """Only `[A-Za-z0-9/_\-\[\].]` survive in the path; anything else is refused, never stored."""
    return bool(_ROUTE_CHARS.match(route_path(raw)))


def normalise_route(raw: Optional[str]) -> str:
    """Route pattern: no query, no fragment, and every segment that holds a digit (UUID, number,
    order number, code) stored as `[id]`, so no identifier reaches the table."""
    segments = ["[id]" if any(c.isdigit() for c in seg) else seg for seg in route_path(raw).split("/")]
    return "/".join(segments)[:MAX_ROUTE] or "/"


def is_rate_limited(db: Session, user_id: Optional[str], *, now: Optional[datetime] = None) -> bool:
    """True once the user has posted `RATE_LIMIT_PER_HOUR` times or stored `ROW_LIMIT_PER_HOUR`
    rows in the last hour. The count is read under a per-user advisory lock that lasts to the end
    of the request transaction, so parallel posts cannot all pass the same count."""
    if not user_id:
        return False
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:u))"), {"u": str(user_id)})
    since = (now or datetime.utcnow()) - timedelta(hours=1)
    posts, rows = (
        db.query(
            func.count(func.distinct(UiPageView.created_at)),
            func.count(UiPageView.id),
        )
        .filter(UiPageView.user_id == user_id, UiPageView.created_at >= since)
        .one()
    )
    return int(posts or 0) >= RATE_LIMIT_PER_HOUR or int(rows or 0) >= ROW_LIMIT_PER_HOUR


def _naive_utc(value: Optional[datetime]) -> datetime:
    if value is None:
        return datetime.utcnow()
    if value.tzinfo is not None:
        try:
            return value.replace(tzinfo=None) - (value.utcoffset() or timedelta(0))
        except OverflowError:
            return datetime.utcnow()
    return value


def record_batch(db: Session, *, user_id: str, items: Iterable) -> int:
    """One row per item; `items` carry route, viewport, ms_to_first_data, ui_version, at."""
    now = datetime.utcnow()
    rows = [
        UiPageView(
            user_id=user_id,
            route=normalise_route(item.route),
            viewport=item.viewport,
            ui_version=item.ui_version,
            ms_to_first_data=item.ms_to_first_data,
            viewed_at=_naive_utc(item.at),
            created_at=now,
        )
        for item in items
    ]
    db.add_all(rows)
    db.commit()
    return len(rows)


def prune_older_than(db: Session, *, days: int = RETENTION_DAYS) -> int:
    cutoff = datetime.utcnow() - timedelta(days=int(days))
    return (
        db.query(UiPageView)
        .filter(UiPageView.created_at < cutoff)
        .delete(synchronize_session=False)
    )
