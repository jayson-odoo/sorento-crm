"""SIGN-TOKEN-LOG-REDACT: customer link tokens never reach a log line.

Crew browser pass on #2126 found the request log writing a customer's counter-sign token in
plain text. No database needed: the middleware and the access-log filter are exercised directly.
"""
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.logging_middleware import LoggingMiddleware
from app.utils.log_redaction import RedactUrlTokensFilter, redact_url

TOKEN = "Zq7sECRETsignTOKENvalue_0123456789abcdef"

TOKEN_PATHS = [
    f"/api/v1/public/quotation-sign/{TOKEN}",
    f"/api/v1/public/quotation-sign/{TOKEN}/accept",
    f"/api/v1/public/quotation-sign/{TOKEN}/view",
    f"/api/v1/public/ticket-drafts/{TOKEN}/submit",
    f"/api/v1/public/supplier-request/{TOKEN}/document/po",
    f"/api/v1/public/portal/ideas/{TOKEN}/comments",
    f"/api/v1/public/file-links/{TOKEN}/content",
]

TOKEN_QUERIES = [
    f"/api/v1/public/view/request?token={TOKEN}",
    f"/api/v1/public/approval/approve?token={TOKEN}&decision=yes",
    f"/api/v1/public/print/catalogue?page=1&token={TOKEN}",
    f"/api/v1/public/portal/token-info?token={TOKEN}",
    f"/api/v1/notifications/preferences/daily-sla-summary/unsubscribe?token={TOKEN}",
    f"/api/v1/x?access_token={TOKEN}",
]


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(LoggingMiddleware)

    @app.api_route("/{rest:path}", methods=["GET", "POST"])
    def catch_all(rest: str):
        return {"ok": True}

    return app


# The request line logs the path only, so the query cases guard against a future change that
# starts logging the full URL; query redaction itself is covered by the redact_url/filter tests.
@pytest.mark.parametrize("url", TOKEN_PATHS + TOKEN_QUERIES)
def test_request_log_carries_no_token(url, caplog):
    client = TestClient(_app())
    with caplog.at_level(logging.INFO, logger="app.middleware.logging_middleware"):
        resp = client.get(url)
    assert resp.status_code == 200  # no behaviour change for the caller
    lines = [r.getMessage() for r in caplog.records if r.name == "app.middleware.logging_middleware"]
    assert lines, "the request line is still written"
    assert all(TOKEN not in line for line in lines), lines
    assert all(TOKEN[:12] not in line for line in lines), lines
    if "?" not in url:  # the request line carries the path only; a path token shows its marker
        assert any("[redacted:" in line for line in lines), lines


@pytest.mark.parametrize("url", TOKEN_PATHS + TOKEN_QUERIES)
def test_redact_url_strips_token_keeps_shape(url):
    out = redact_url(url)
    assert TOKEN not in out
    assert TOKEN[:12] not in out
    assert "[redacted:" in out
    # Route shape survives for debugging.
    assert out.split("[redacted:")[0] == url.split(TOKEN)[0]


def test_same_token_same_marker_for_correlation():
    a = redact_url(f"/api/v1/public/quotation-sign/{TOKEN}")
    b = redact_url(f"/api/v1/public/quotation-sign/{TOKEN}/accept")
    c = redact_url("/api/v1/public/quotation-sign/another-token-value")
    marker = a.rsplit("/", 1)[1]
    assert b.split("/")[-2] == marker
    assert c.rsplit("/", 1)[1] != marker


@pytest.mark.parametrize(
    "url",
    [
        "/api/v1/orders/123?page=2&sort=name",
        "/api/v1/public/branding",
        "/api/v1/public/quotation-sign",
        "/api/v1/public/c/ACME/spring-catalogue",
        "/health",
    ],
)
def test_ordinary_urls_unchanged(url):
    assert redact_url(url) == url


def test_full_url_redacted():
    url = f"http://localhost:8000/api/v1/public/quotation-sign/{TOKEN}/accept?token={TOKEN}"
    out = redact_url(url)
    assert TOKEN not in out
    assert out.startswith("http://localhost:8000/api/v1/public/quotation-sign/[redacted:")


def test_uvicorn_access_filter_rewrites_path_arg():
    # uvicorn.access logs: '%s - "%s %s HTTP/%s" %d' % (client, method, path_with_query, version, status)
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("10.0.0.1:5000", "POST", f"/api/v1/public/quotation-sign/{TOKEN}/accept?token={TOKEN}", "1.1", 200),
        None,
    )
    assert RedactUrlTokensFilter().filter(record) is True
    message = record.getMessage()
    assert TOKEN not in message
    assert "/api/v1/public/quotation-sign/[redacted:" in message
    assert '" 200' in message


def test_access_filter_installed_on_uvicorn_access_logger():
    import app.main  # noqa: F401  (installs the filter at import)

    assert any(isinstance(f, RedactUrlTokensFilter) for f in logging.getLogger("uvicorn.access").filters)


@pytest.mark.parametrize(
    "url",
    [
        f"https://crm.example.com/quotation-sign/{TOKEN}",
        f"/portal/ideas/{TOKEN}",
        f"/portal/ticket-draft/{TOKEN}",
        f"/c/ACME/supplier-request/{TOKEN}",
        f"/onboarding/{TOKEN}",
        f"https://crm.example.com/f/{TOKEN}",
        f"https://crm.example.com/view/complaint?token={TOKEN}",
    ],
)
def test_customer_page_urls_redacted(url):
    out = redact_url(url)
    assert TOKEN not in out
    assert "[redacted:" in out


@pytest.mark.parametrize(
    "url",
    [
        "/api/v1/user-management/onboarding/requests",
        "/api/v1/public/onboarding/me",
        "/api/v1/master-data/f/thing",
    ],
)
def test_staff_routes_with_page_words_unchanged(url):
    assert redact_url(url) == url


def test_api_call_log_body_strips_link_urls():
    from app.services.api_call_log_service import sanitize_body

    body = (
        '{"view_url": "https://crm.example.com/view/complaint?token=%s",'
        ' "portal_url": "https://crm.example.com/portal/c/acme?token=%s",'
        ' "path": "/quotation-sign/%s", "token": "%s"}' % (TOKEN, TOKEN, TOKEN, TOKEN)
    )
    stored = sanitize_body(body)
    assert TOKEN not in stored
    assert "view/complaint?token=[redacted:" in stored
    assert TOKEN not in sanitize_body("plain text https://x.example.com/f/%s" % TOKEN)


def test_httpx_request_line_not_logged_at_info():
    import app.main  # noqa: F401

    # The logger's own level: pytest's capture handler leaves the root at WARNING, so the
    # effective level would pass without the fix.
    assert logging.getLogger("httpx").level >= logging.WARNING
    assert logging.getLogger("httpcore").level >= logging.WARNING


def test_db_errors_hide_bound_parameters():
    from app.config import settings
    from app.database import engine

    if not settings.debug:
        assert engine.hide_parameters is True


def test_error_handler_request_url_line_redacted(caplog):
    """The 422 handler's `Request URL:` line (app/main.py) carries no token (UAC 3)."""
    from app.main import app

    client = TestClient(app)
    with caplog.at_level(logging.ERROR, logger="app.main"):
        resp = client.post(f"/api/v1/public/quotation-sign/{TOKEN}/view?token={TOKEN}")
    assert resp.status_code == 422
    url_lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("Request URL:")]
    assert url_lines
    assert all(TOKEN not in line for line in url_lines), url_lines
    assert all("[redacted:" in line for line in url_lines), url_lines
