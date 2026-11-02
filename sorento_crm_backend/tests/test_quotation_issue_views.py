"""PS-QUOTE-VIEWS: the customer opening the sign link is counted, once per browser per 30 minutes.

Card: documentation/plans/project-sales/CARD-quote-views-2nov.md. The beacon is a POST the sign
page sends after it has loaded, so link-preview bots (which never run the page script) never reach
it; the user-agent refusal is the second line. Nothing that identifies a person is stored: no IP,
no user agent, only a coarse device and a hash of a random per-browser id.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import inspect

from app.models.projects import QuotationIssueView
from app.services import project_quotation_document_service as qdocs
from app.services import quotation_view_service as views

from ._pg_fixture import blank_session
from .test_project_quotation_signing import _setup, _sign_draft

IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
)
IPAD = (
    "Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
)
ANDROID_TABLET = (
    "Mozilla/5.0 (Linux; Android 13; SM-X200) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)
LAPTOP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)

T0 = datetime(2026, 11, 2, 13, 5, 0)


def _issued(db):
    project, document, owner, _scopes = _setup(db)
    _sign_draft(db, document, owner)
    record = qdocs.issue(db, document=document, actor_user_id=owner)
    return project, document, owner, record


def _count(db, record) -> int:
    return db.query(QuotationIssueView).filter(QuotationIssueView.issue_id == record.id).count()


# ------------------------------------------------------------------ device and bots


@pytest.mark.parametrize(
    "agent,device",
    [
        (IPHONE, "mobile"),
        (IPAD, "tablet"),
        (ANDROID_TABLET, "tablet"),
        (
            "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Mobile Safari/537.36",
            "mobile",
        ),
        (LAPTOP, "desktop"),
        (None, "desktop"),
    ],
)
def test_device_is_coarse(agent, device):
    assert views.device_of(agent) == device


@pytest.mark.parametrize(
    "agent",
    [
        "WhatsApp/2.23.20.0 A",
        "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
        "Slackbot-LinkExpanding 1.0 (+https://api.slack.com/robots)",
        "TelegramBot (like TwitterBot)",
        "Twitterbot/1.0",
        "LinkedInBot/1.0",
        "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
        "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
        "Mozilla/5.0 (Windows NT 10.0) GoogleImageProxy",
        "Skype-Url-Preview",
        "Mozilla/5.0 (compatible; Discordbot/2.0)",
        "curl/8.4.0",
        "python-requests/2.31",
        "HeadlessChrome/120.0",
        "",
        None,
    ],
)
def test_link_preview_bots_are_refused(agent):
    assert views.is_bot(agent) is True


@pytest.mark.parametrize("agent", [IPHONE, IPAD, LAPTOP, ANDROID_TABLET])
def test_real_browsers_are_not_bots(agent):
    assert views.is_bot(agent) is False


# ------------------------------------------------------------------ the 30-minute rule


def test_one_browser_counts_once_per_thirty_minutes():
    with blank_session() as db:
        _p, _d, _o, record = _issued(db)
        assert views.record_view(db, record=record, visitor_id="browser-a-123456", user_agent=IPHONE, now=T0)
        # Refresh at +5 and +29:59: same browser, inside the window.
        assert not views.record_view(
            db, record=record, visitor_id="browser-a-123456", user_agent=IPHONE, now=T0 + timedelta(minutes=5)
        )
        assert not views.record_view(
            db,
            record=record,
            visitor_id="browser-a-123456",
            user_agent=IPHONE,
            now=T0 + timedelta(minutes=29, seconds=59),
        )
        assert _count(db, record) == 1
        # 30 minutes after the last COUNTED view, it counts again.
        assert views.record_view(
            db, record=record, visitor_id="browser-a-123456", user_agent=IPHONE, now=T0 + timedelta(minutes=35)
        )
        assert _count(db, record) == 2


def test_a_different_browser_counts_at_once():
    with blank_session() as db:
        _p, _d, _o, record = _issued(db)
        assert views.record_view(db, record=record, visitor_id="browser-a-123456", user_agent=IPHONE, now=T0)
        assert views.record_view(
            db, record=record, visitor_id="browser-b-654321", user_agent=LAPTOP, now=T0 + timedelta(minutes=7)
        )
        assert _count(db, record) == 2


def test_a_bot_records_nothing():
    with blank_session() as db:
        _p, _d, _o, record = _issued(db)
        assert not views.record_view(
            db, record=record, visitor_id="browser-a-123456", user_agent="WhatsApp/2.23.20.0 A", now=T0
        )
        assert _count(db, record) == 0


def test_the_window_is_per_revision():
    with blank_session() as db:
        _p, document, owner, r1 = _issued(db)
        assert views.record_view(db, record=r1, visitor_id="browser-a-123456", user_agent=IPHONE, now=T0)
        r2 = qdocs.issue(db, document=document, actor_user_id=owner)
        assert r2.id != r1.id
        assert views.record_view(
            db, record=r2, visitor_id="browser-a-123456", user_agent=IPHONE, now=T0 + timedelta(minutes=1)
        )


# ------------------------------------------------------------------ what is stored


def test_only_time_device_and_a_hashed_browser_id_are_stored():
    columns = {c.name for c in inspect(QuotationIssueView).columns}
    assert columns == {"id", "company_id", "issue_id", "viewed_at", "device", "visitor_hash"}
    with blank_session() as db:
        _p, document, _o, record = _issued(db)
        views.record_view(db, record=record, visitor_id="browser-a-123456", user_agent=IPHONE, now=T0)
        row = db.query(QuotationIssueView).filter(QuotationIssueView.issue_id == record.id).one()
        assert row.device == "mobile"
        assert row.viewed_at == T0
        assert row.visitor_hash != "browser-a-123456"
        assert "browser-a" not in row.visitor_hash
        assert len(row.visitor_hash) == 32
        assert str(row.company_id) == str(document.company_id)


# ------------------------------------------------------------------ what the salesperson reads


def test_the_document_reports_views_of_the_revision_the_customer_holds():
    with blank_session() as db:
        _p, document, owner, r1 = _issued(db)
        assert qdocs.serialize_document(db, document)["view_count"] == 0
        assert qdocs.serialize_document(db, document)["last_viewed_at"] is None

        views.record_view(db, record=r1, visitor_id="browser-a-123456", user_agent=IPHONE, now=T0)
        views.record_view(
            db, record=r1, visitor_id="browser-b-654321", user_agent=LAPTOP, now=T0 + timedelta(minutes=7)
        )
        out = qdocs.serialize_document(db, document)
        assert out["view_count"] == 2
        assert out["last_viewed_at"] == T0 + timedelta(minutes=7)

        r2 = qdocs.issue(db, document=document, actor_user_id=owner)
        out = qdocs.serialize_document(db, document)
        assert out["view_count"] == 0, "the header follows the latest revision"
        assert out["last_viewed_at"] is None

        # A view on the OLD link lands on R1 and does not move R2's count.
        views.record_view(
            db, record=r1, visitor_id="browser-a-123456", user_agent=IPHONE, now=T0 + timedelta(hours=2)
        )
        assert qdocs.serialize_document(db, document)["view_count"] == 0

        log = views.log_for_document(db, document)
        assert [row["issue_no"] for row in log] == [r1.issue_no] * 3
        assert log[0]["viewed_at"] == T0 + timedelta(hours=2), "newest first"
        assert log[0]["device"] == "mobile"
        assert log[0]["our_ref"] == qdocs.quotation_no(document.document_no, r1.issue_no)
        assert r2.issue_no == r1.issue_no + 1


def test_a_document_never_issued_reports_no_count():
    with blank_session() as db:
        _p, document, _o, _scopes = _setup(db)
        out = qdocs.serialize_document(db, document)
        assert out["view_count"] == 0
        assert out["last_viewed_at"] is None
        assert views.log_for_document(db, document) == []


# ------------------------------------------------------------------ the public wire


def _client(db):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app), app


def test_the_beacon_counts_with_no_credential():
    with blank_session() as db:
        _p, _d, _o, record = _issued(db)
        token = qdocs.issue_sign_link(db, record=record)
        db.commit()
        client, app = _client(db)
        try:
            url = f"/api/v1/public/quotation-sign/{token}/view"
            first = client.post(url, json={"visitor_id": "browser-a-123456"}, headers={"User-Agent": IPHONE})
            assert first.status_code == 200, first.text
            assert first.json() == {"counted": True}
            again = client.post(url, json={"visitor_id": "browser-a-123456"}, headers={"User-Agent": IPHONE})
            assert again.json() == {"counted": False}
            bot = client.post(
                url, json={"visitor_id": "browser-z-999999"}, headers={"User-Agent": "WhatsApp/2.23.20.0 A"}
            )
            assert bot.status_code == 200
            assert bot.json() == {"counted": False}
            assert _count(db, record) == 1
        finally:
            app.dependency_overrides.clear()


def test_the_page_read_itself_records_nothing():
    """The GET stays read-only: scanners and prefetchers call GETs."""
    with blank_session() as db:
        _p, _d, _o, record = _issued(db)
        token = qdocs.issue_sign_link(db, record=record)
        db.commit()
        client, app = _client(db)
        try:
            assert client.get(f"/api/v1/public/quotation-sign/{token}", headers={"User-Agent": IPHONE}).status_code == 200
            assert _count(db, record) == 0
        finally:
            app.dependency_overrides.clear()


def test_an_unknown_or_expired_link_records_nothing():
    with blank_session() as db:
        _p, _d, _o, record = _issued(db)
        token = qdocs.issue_sign_link(db, record=record)
        record.sign_token_expires_at = datetime.utcnow() - timedelta(minutes=1)
        db.commit()
        client, app = _client(db)
        try:
            for t in (token, "zzt-not-a-real-token"):
                response = client.post(
                    f"/api/v1/public/quotation-sign/{t}/view",
                    json={"visitor_id": "browser-a-123456"},
                    headers={"User-Agent": IPHONE},
                )
                assert response.status_code == 404
                assert response.json().get("code") == "quotation_sign_link_invalid" or "no longer valid" in response.text
            assert _count(db, record) == 0
        finally:
            app.dependency_overrides.clear()


@pytest.mark.parametrize("visitor_id", ["", "short", "x" * 129])
def test_a_malformed_browser_id_is_refused(visitor_id):
    with blank_session() as db:
        _p, _d, _o, record = _issued(db)
        token = qdocs.issue_sign_link(db, record=record)
        db.commit()
        client, app = _client(db)
        try:
            response = client.post(
                f"/api/v1/public/quotation-sign/{token}/view",
                json={"visitor_id": visitor_id},
                headers={"User-Agent": IPHONE},
            )
            assert response.status_code == 422
            assert _count(db, record) == 0
        finally:
            app.dependency_overrides.clear()
