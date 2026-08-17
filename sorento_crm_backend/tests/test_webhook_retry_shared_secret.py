"""The AC-J6 shared secret on the RETRY lanes, not just the first attempt.

UAC: documentation/plans/sla/conversation-intervention-tickets-acceptance-criteria.md
     AC-J6 (every direct CRM -> n8n webhook call carries X-CRM-Webhook-Secret;
            the n8n gate is fail-closed, so a call without it cannot arm the
            bot-pause lane - and the secret never sits at rest in the log row)

``send_webhook_for_log`` resets a FAILED send back to ``status=pending`` with a
``next_retry_at``, so the normal path for a webhook that did not get through the
first time is the scheduled sweeper (``process_pending_logs``) or the operator
"Retry" button - neither of which passed ``extra_headers``. Both therefore
resent the row UNAUTHENTICATED and n8n's fail-closed gate rejected it: the
bot-pause lane silently never armed for exactly the sends that needed a retry.

The header is resolved from the row's own ``integration_channel`` inside
``send_webhook_for_log``, so it cannot be forgotten by a new caller.

Run:
    venv/bin/pytest tests/test_webhook_retry_shared_secret.py -q
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta

import pytest

from app.models.integration import IntegrationLog
from app.services.integration_service import IntegrationLogService
from app.services.webhook_service import WebhookService
from tests._pg_fixture import blank_session

SECRET_HEADER = "X-CRM-Webhook-Secret"
WEBHOOK_SECRET = "zzt-retry-secret"
CHAT_CHANNEL = "n8n_crm_chat_outbound"
CLOSE_CHANNEL = "n8n_crm_close_convo"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _webhook_secret(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "n8n_crm_webhook_secret", WEBHOOK_SECRET, raising=False)
    monkeypatch.setenv("N8N_CRM_WEBHOOK_SECRET", WEBHOOK_SECRET)


@pytest.fixture
def sent(monkeypatch):
    """Every outgoing webhook request, as the HTTP boundary saw it."""
    calls: list[dict] = []

    def _fake_send(_self, url, payload, headers=None):
        calls.append({"url": url, "payload": payload, "headers": dict(headers or {})})
        return True, 200, {"ok": True}, None, None

    monkeypatch.setattr(WebhookService, "send_webhook", _fake_send)
    return calls


def _make_log(
    db,
    *,
    channel: str = CHAT_CHANNEL,
    status: str = "pending",
    next_retry_at: datetime | None = None,
    request_headers: str | None = None,
) -> IntegrationLog:
    log = IntegrationLog(
        id=str(uuid.uuid4()),
        integration_channel=channel,
        business_table="conversation_sla_tracking",
        business_id=str(uuid.uuid4()),
        direction="outbound",
        endpoint="https://n8n.test/webhook/respond-send-user",
        http_method="POST",
        status=status,
        request_headers=request_headers,
        request_payload=json.dumps([{"source": "User"}]),
        next_retry_at=next_retry_at,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


# --------------------------------------------------------------------------- #
# The scheduled sweeper - the lane a failed send actually comes back through   #
# --------------------------------------------------------------------------- #


def test_the_sweeper_resend_carries_the_shared_secret(db, sent):
    _make_log(db, next_retry_at=datetime.utcnow() - timedelta(minutes=5))

    result = IntegrationLogService(db).process_pending_logs()

    assert result["processed"] == 1
    assert len(sent) == 1
    assert sent[0]["headers"][SECRET_HEADER] == WEBHOOK_SECRET, (
        "a sweeper resend without the header is refused by the fail-closed n8n gate"
    )


def test_the_sweeper_resend_carries_the_secret_on_the_close_lane_too(db, sent):
    _make_log(
        db, channel=CLOSE_CHANNEL, next_retry_at=datetime.utcnow() - timedelta(minutes=5)
    )

    IntegrationLogService(db).process_pending_logs()

    assert sent[0]["headers"][SECRET_HEADER] == WEBHOOK_SECRET


def test_an_unrelated_channel_is_never_given_the_secret(db, sent):
    """The attachment lane has no shared-secret contract - handing it a
    credential it never asked for widens the blast radius for nothing."""
    _make_log(db, channel="n8n", next_retry_at=datetime.utcnow() - timedelta(minutes=5))

    IntegrationLogService(db).process_pending_logs()

    assert SECRET_HEADER not in sent[0]["headers"]


def test_the_secret_is_absent_from_the_row_before_and_after_a_resend(db, sent):
    log = _make_log(db, next_retry_at=datetime.utcnow() - timedelta(minutes=5))
    assert WEBHOOK_SECRET not in (log.request_headers or "")

    IntegrationLogService(db).process_pending_logs()

    db.refresh(log)
    assert WEBHOOK_SECRET not in (log.request_headers or ""), (
        "a credential written to request_headers is readable by anyone with "
        "log-view permission, and stays readable after a rotation"
    )
    assert sent[0]["headers"][SECRET_HEADER] == WEBHOOK_SECRET


def test_stored_headers_survive_alongside_the_injected_secret(db, sent):
    _make_log(
        db,
        next_retry_at=datetime.utcnow() - timedelta(minutes=5),
        request_headers=json.dumps({"X-Trace": "abc"}),
    )

    IntegrationLogService(db).process_pending_logs()

    assert sent[0]["headers"]["X-Trace"] == "abc"
    assert sent[0]["headers"][SECRET_HEADER] == WEBHOOK_SECRET


def test_an_explicit_extra_header_still_overrides_the_resolved_one(db, sent):
    log = _make_log(db)

    IntegrationLogService(db).send_webhook_for_log(
        str(log.id), extra_headers={SECRET_HEADER: "caller-wins"}
    )

    assert sent[0]["headers"][SECRET_HEADER] == "caller-wins"


# --------------------------------------------------------------------------- #
# The operator Retry button                                                    #
# --------------------------------------------------------------------------- #


def test_the_operator_retry_route_carries_the_shared_secret(db, sent):
    from app.api.v1.integrations.logs import retry_integration_log

    log = _make_log(db, status="failed")

    asyncio.run(
        retry_integration_log(
            str(log.id), current_user={"id": str(uuid.uuid4())}, db=db
        )
    )

    assert len(sent) == 1
    assert sent[0]["headers"][SECRET_HEADER] == WEBHOOK_SECRET


# --------------------------------------------------------------------------- #
# The daemon-thread vs sweeper race on a still-pending row                     #
# --------------------------------------------------------------------------- #


def test_the_sweeper_leaves_a_just_enqueued_row_to_its_own_send_thread(db, sent):
    """The direct lane commits the row `pending` and THEN starts the POST on a
    daemon thread. A sweeper tick landing in that gap used to grab the same row
    and send it twice. The row is held with a short `next_retry_at`, which is
    what that column already means: not before this time."""
    from app.services import integration_service

    log = _make_log(db, next_retry_at=None, status="pending")
    log.next_retry_at = integration_service.direct_send_retry_hold()
    db.commit()

    result = IntegrationLogService(db).process_pending_logs()

    assert result["processed"] == 0, "the send thread owns it for now"
    assert sent == []


def test_the_sweeper_picks_the_row_up_once_the_hold_expires(db, sent):
    """And if the thread died with the process, the row is not stranded."""
    _make_log(db, next_retry_at=datetime.utcnow() - timedelta(seconds=1))

    result = IntegrationLogService(db).process_pending_logs()

    assert result["processed"] == 1
    assert sent[0]["headers"][SECRET_HEADER] == WEBHOOK_SECRET
