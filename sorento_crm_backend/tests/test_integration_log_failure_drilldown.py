"""Integration-log filters backing the health-dashboard failure drill-down.

Covers UAC OBS-S1-17 .. OBS-S1-20.

Clicking a specific cause on the dashboard has to land on exactly the rows that
produced that cause's count. Channel + status alone cannot do that — one channel
mixes several faults — so the list gains `status_code` and `error_contains`.

`error_contains` is a LIKE, which is why the wildcard-escaping test below is not
theoretical: real error messages contain `%` (percent-encoded urls) and `_`
(identifiers), and an unescaped one silently widens the result set.
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.integration import IntegrationLog
from app.services.integration_service import IntegrationLogService


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[IntegrationLog.__table__])
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _log(session, *, channel="respond_io", status="failed", status_code=None, error=None, minutes_ago=1):
    row = IntegrationLog(
        integration_channel=channel,
        business_table="complaints",
        business_id="3f2b1c4e-9a1d-4f7e-88aa-1b2c3d4e5f60",
        direction="outbound",
        endpoint="/message",
        http_method="POST",
        status=status,
        status_code=status_code,
        error_message=error,
        created_at=datetime.utcnow() - timedelta(minutes=minutes_ago),
    )
    session.add(row)
    session.commit()
    return row


def _total(session, **kwargs):
    """Row count matching the filters. `pagination` is a PaginationResponse
    object, not a dict."""
    result = IntegrationLogService(session).list_integration_logs(**kwargs)
    return result["pagination"].total


def test_status_code_narrows_to_one_fault(db):
    """The 401 group and the 403 group live on the same channel with the same
    status; only the code separates them."""
    for _ in range(3):
        _log(db, status_code=401, error="Client error '401 Unauthorized' for url '/contact/id:1/message'")
    _log(db, status_code=403, error="Client error '403 Forbidden' for url '/contact/id:2/message'")

    total = _total(db, integration_channel="respond_io", status="failed", status_code=401)
    assert total == 3


def test_error_contains_selects_the_whole_group_not_one_row(db):
    """The point of filtering on the stable substring rather than the sample
    message: the contact id differs per row."""
    _log(db, status_code=None, error="24h window closed and template send skipped for use case 'a'")
    _log(db, status_code=None, error="24h window closed and template send skipped for use case 'b'")
    _log(db, status_code=None, error="totally unrelated failure")

    total = _total(db, error_contains="window closed and template send skipped")
    assert total == 2


def test_error_contains_is_case_insensitive(db):
    _log(db, error="Connection Refused")
    assert _total(db, error_contains="connection refused") == 1


def test_like_wildcards_in_the_term_are_escaped(db):
    """A `%` in the search term must match a literal `%`, not "anything". Without
    escaping, searching for `100%` would also return `100 percent` etc."""
    _log(db, error="quota 100% exceeded")
    _log(db, error="quota 100 exceeded")

    assert _total(db, error_contains="100% exceeded") == 1


def test_underscore_wildcard_is_escaped(db):
    """`_` matches any single char in LIKE — an identifier like `sla_daily` would
    otherwise also match `sla-daily`."""
    _log(db, error="use case 'sla_daily_summary'")
    _log(db, error="use case 'slaXdailyXsummary'")

    assert _total(db, error_contains="sla_daily_summary") == 1


def test_filters_compose_with_channel_and_status(db):
    _log(db, channel="respond_io", status="failed", status_code=401, error="Unauthorized here")
    _log(db, channel="n8n", status="failed", status_code=401, error="Unauthorized here")

    total = _total(db, integration_channel="respond_io", status="failed", status_code=401,
                   error_contains="Unauthorized here")
    assert total == 1


def test_absent_filters_do_not_narrow(db):
    _log(db, status_code=401, error="whatever")
    _log(db, status_code=500, error=None)
    assert _total(db) == 2


def test_card_count_equals_link_count(db):
    """The invariant the whole drill-down rests on: the number rendered on the
    health card must equal the number of rows its link lands on.

    Seeds the exact live shape that broke it — two 401 faults on the same channel
    differing only by endpoint, where the longest single stable substring of one
    is also a substring of the other.
    """
    from app.api.v1.system.health import _integrations_health

    msg_message = (
        "Client error '401 Unauthorized' for url "
        "'https://api.respond.io/v2/contact/id:{}/message'"
    )
    msg_status = (
        "Client error '401 Unauthorized' for url "
        "'https://api.respond.io/v2/contact/id:{}/conversation/status'"
    )
    for i in range(7):
        _log(db, status_code=401, error=msg_message.format(1000 + i))
    for i in range(3):
        _log(db, status_code=401, error=msg_status.format(2000 + i))

    now = datetime.utcnow()
    health = _integrations_health(db, now - timedelta(days=1), now + timedelta(minutes=1))
    causes = health.channels[0].top_failures
    assert len(causes) == 2, "the two endpoints must not collapse into one cause"

    for cause in causes:
        landed = _total(
            db,
            integration_channel="respond_io",
            status="failed",
            status_code=cause.status_code,
            error_contains=cause.filter_terms,
        )
        assert landed == cause.count, (
            f"card showed {cause.count} but the link lands on {landed} "
            f"for {cause.sample_message!r}"
        )
