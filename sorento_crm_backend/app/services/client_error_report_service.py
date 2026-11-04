"""Store and list browser crash reports (CLIENT-ERROR-REPORT).

Every limit lives here, not in the route, so a test can reach it without an HTTP
round-trip and a second writer cannot skip it.

Abuse bounds, all server-side (the browser is not trusted to truncate):
- the raw body is refused above ``MAX_BODY_BYTES``;
- every stored field is cut to its column cap;
- a user gets ``RATE_LIMIT_PER_HOUR`` rows per rolling hour, counted from this table
  (no Redis: the table is the counter, so the limit holds across every API process).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlsplit

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.client_error_report import ClientErrorReport
from app.utils.log_redaction import redact_url

MAX_BODY_BYTES = 16 * 1024
RATE_LIMIT_PER_HOUR = 20
RETENTION_DAYS = 30

MAX_NAME = 128
MAX_MESSAGE = 2000
MAX_STACK = 8000
MAX_DIGEST = 64
MAX_PATH = 512
MAX_BUILD_SHA = 64
MAX_USER_AGENT = 512

BOUNDARIES = ("global", "protected")


def _cut(value: Optional[object], limit: int) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:limit]


def clean_path(raw: Optional[str]) -> Optional[str]:
    """Path only. A query string can carry a search term, a record filter or a link
    token, so it never reaches the table; link tokens in the path are redacted too."""
    if not raw:
        return None
    path = urlsplit(str(raw)).path or "/"
    if not path.startswith("/"):
        path = "/" + path
    return _cut(redact_url(path), MAX_PATH)


def is_rate_limited(db: Session, user_id: Optional[str], *, now: Optional[datetime] = None) -> bool:
    if not user_id:
        return False
    since = (now or datetime.utcnow()) - timedelta(hours=1)
    count = (
        db.query(func.count(ClientErrorReport.id))
        .filter(ClientErrorReport.user_id == user_id, ClientErrorReport.created_at >= since)
        .scalar()
    )
    return int(count or 0) >= RATE_LIMIT_PER_HOUR


def record_report(
    db: Session,
    *,
    user_id: Optional[str],
    boundary: str,
    error_name: Optional[str],
    message: Optional[str],
    stack: Optional[str],
    digest: Optional[str],
    path: Optional[str],
    build_sha: Optional[str],
    user_agent: Optional[str],
    is_chunk_error: bool,
    client_ts: Optional[datetime],
) -> ClientErrorReport:
    if client_ts is not None and client_ts.tzinfo is not None:
        client_ts = client_ts.replace(tzinfo=None) - (client_ts.utcoffset() or timedelta(0))
    row = ClientErrorReport(
        user_id=user_id,
        boundary=boundary if boundary in BOUNDARIES else "global",
        error_name=_cut(error_name, MAX_NAME),
        message=_cut(message, MAX_MESSAGE),
        stack=_cut(stack, MAX_STACK),
        digest=_cut(digest, MAX_DIGEST),
        path=clean_path(path),
        build_sha=_cut(build_sha, MAX_BUILD_SHA),
        user_agent=_cut(user_agent, MAX_USER_AGENT),
        is_chunk_error=bool(is_chunk_error),
        client_ts=client_ts,
    )
    db.add(row)
    db.commit()
    return row


def list_reports(
    db: Session,
    *,
    date_from: Optional[datetime],
    date_to: Optional[datetime],
    chunk_only: Optional[bool],
    search: Optional[str],
    page: int,
    limit: int,
):
    q = db.query(ClientErrorReport)
    if date_from is not None:
        q = q.filter(ClientErrorReport.created_at >= date_from)
    if date_to is not None:
        q = q.filter(ClientErrorReport.created_at <= date_to)
    if chunk_only is not None:
        q = q.filter(ClientErrorReport.is_chunk_error.is_(chunk_only))
    if search:
        like = f"%{search.strip()}%"
        q = q.filter(
            or_(
                ClientErrorReport.message.ilike(like),
                ClientErrorReport.error_name.ilike(like),
                ClientErrorReport.path.ilike(like),
                ClientErrorReport.digest.ilike(like),
                ClientErrorReport.build_sha.ilike(like),
            )
        )
    total = q.count()
    rows = (
        q.order_by(ClientErrorReport.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return rows, total


def prune_client_error_reports(db: Session, *, retention_days: int = RETENTION_DAYS) -> int:
    cutoff = datetime.utcnow() - timedelta(days=int(retention_days))
    return (
        db.query(ClientErrorReport)
        .filter(ClientErrorReport.created_at < cutoff)
        .delete(synchronize_session=False)
    )
