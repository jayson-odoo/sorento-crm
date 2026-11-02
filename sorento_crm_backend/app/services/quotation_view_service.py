"""PS-QUOTE-VIEWS: count the customer's opens of a quotation sign link.

Card: documentation/plans/project-sales/CARD-quote-views-2nov.md.

What counts: the sign page, after it has loaded, sends a beacon with a random id it keeps in the
browser. Link-preview bots (WhatsApp, Gmail, Slack ...) fetch the HTML and never run the page
script, so they never send it; `is_bot` refuses the ones that do. A browser signed in to the CRM
does not send it at all (the page checks). The same browser on the same issue counts again only
30 minutes after its last COUNTED open.

What is stored: time, coarse device, and a digest of the random browser id. No IP address and no
user agent: the user agent is read for the device class and the bot check, then dropped.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.projects import (
    ProjectQuotationDocument,
    ProjectQuotationIssue,
    QuotationIssueView,
)

UNIQUE_WINDOW = timedelta(minutes=30)
# Counted opens per issue per hour, checked in the database so it holds when the Redis limiter
# fails open. No real customer opens one quotation this often; past it the count stops moving.
MAX_PER_ISSUE_PER_HOUR = 20
LOG_LIMIT = 50

# Link previewers, crawlers and scripted clients. Lower-cased substring match. An empty or missing
# user agent is refused too: every real browser sends one.
_BOT_MARKERS = (
    "crawler",
    "spider",
    "preview",
    "whatsapp",
    "facebookexternalhit",
    "facebookcatalog",
    "embedly",
    "googleimageproxy",
    "google-read-aloud",
    "headless",
    "curl/",
    "wget/",
    "python-requests",
    "python-urllib",
    "httpx",
    "okhttp",
    "go-http-client",
    "java/",
    "node-fetch",
    "axios/",
)

_TABLET = re.compile(r"ipad|tablet|kindle|silk|playbook", re.IGNORECASE)
_MOBILE = re.compile(r"mobi|iphone|ipod|windows phone|blackberry", re.IGNORECASE)


# "...bot" as a word end (Googlebot/, Slackbot-, TelegramBot ), but not the CUBOT phone brand.
_BOT_WORD = re.compile(r"(?<!cu)bot(?![a-z])")


def is_bot(user_agent: Optional[str]) -> bool:
    agent = (user_agent or "").strip().lower()
    if not agent:
        return True
    return bool(_BOT_WORD.search(agent)) or any(marker in agent for marker in _BOT_MARKERS)


def device_of(user_agent: Optional[str]) -> str:
    """mobile | tablet | desktop. Android without "Mobile" is a tablet by Google's own convention."""
    agent = user_agent or ""
    if _TABLET.search(agent):
        return "tablet"
    if _MOBILE.search(agent):
        return "mobile"
    if "android" in agent.lower():
        return "tablet"
    return "desktop"


def _visitor_hash(visitor_id: str) -> str:
    return hashlib.sha256(visitor_id.encode()).hexdigest()[:32]


def record_view(
    db: Session,
    *,
    record: ProjectQuotationIssue,
    visitor_id: str,
    user_agent: Optional[str],
    now: Optional[datetime] = None,
) -> bool:
    """Record one open if it counts. Answers whether it did."""
    if is_bot(user_agent):
        return False
    now = now or datetime.utcnow()
    digest = _visitor_hash(visitor_id)
    recent = (
        db.query(QuotationIssueView.id)
        .filter(
            QuotationIssueView.issue_id == record.id,
            QuotationIssueView.visitor_hash == digest,
            QuotationIssueView.viewed_at > now - UNIQUE_WINDOW,
            QuotationIssueView.viewed_at <= now,
        )
        .first()
    )
    if recent is not None:
        return False
    last_hour = (
        db.query(func.count(QuotationIssueView.id))
        .filter(
            QuotationIssueView.issue_id == record.id,
            QuotationIssueView.viewed_at > now - timedelta(hours=1),
            QuotationIssueView.viewed_at <= now,
        )
        .scalar()
        or 0
    )
    if last_hour >= MAX_PER_ISSUE_PER_HOUR:
        return False
    db.add(
        QuotationIssueView(
            issue_id=record.id,
            company_id=record.company_id,
            viewed_at=now,
            device=device_of(user_agent),
            visitor_hash=digest,
        )
    )
    db.flush()
    return True


def summary_for_issue(db: Session, record: Optional[ProjectQuotationIssue]) -> Dict[str, Any]:
    """`view_count` and `last_viewed_at` for one issue (the document header reads the latest)."""
    if record is None:
        return {"view_count": 0, "last_viewed_at": None}
    count, last = (
        db.query(func.count(QuotationIssueView.id), func.max(QuotationIssueView.viewed_at))
        .filter(QuotationIssueView.issue_id == record.id)
        .one()
    )
    return {"view_count": int(count or 0), "last_viewed_at": last}


def log_for_document(
    db: Session, document: ProjectQuotationDocument, *, limit: int = LOG_LIMIT
) -> List[Dict[str, Any]]:
    """Every revision's counted opens, newest first."""
    from app.services.project_quotation_document_service import quotation_no

    rows = (
        db.query(QuotationIssueView, ProjectQuotationIssue.issue_no)
        .join(ProjectQuotationIssue, ProjectQuotationIssue.id == QuotationIssueView.issue_id)
        .filter(ProjectQuotationIssue.document_id == document.id)
        .order_by(QuotationIssueView.viewed_at.desc(), QuotationIssueView.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": str(view.id),
            "viewed_at": view.viewed_at,
            "issue_no": issue_no,
            "our_ref": quotation_no(document.document_no, issue_no),
            "device": view.device,
        }
        for view, issue_no in rows
    ]
