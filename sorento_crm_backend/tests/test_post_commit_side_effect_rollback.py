"""A post-commit side effect that fails must not poison the session.

PRINCIPLES.md: "Post-commit side effects are best-effort (catch + warn, never
raise)". Catching is only half of it. When the thing that failed was a DB write,
the transaction is left in an aborted state and EVERY later statement on that
session raises ``PendingRollbackError`` - so the route that just committed a
successful resolve or a delivered message still answers 500, and the caller's
retry takes the idempotent short-circuit which never backfills the side effect.

``_write_event_log_best_effort`` (app/api/v1/sla/sla_tracking.py) already rolls
back for exactly this reason; the two outbox writers here did not.

Run:
    venv/bin/pytest tests/test_post_commit_side_effect_rollback.py -q
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.models.access import AccessAgent, AgentTeam, RespondContact, Team
from app.models.integration import IntegrationLog
from app.models.sla import SLAPolicy, SLAPolicyTier
from app.models.user import User
from app.schemas.sla import ConversationSLATrackingCreate, ConversationSLATrackingUpdate
from app.services.sla_service import ConversationSLATrackingService
from tests._pg_fixture import blank_session

PHONE = "+60123456789"
RESPOND_IO_ID = "10025531"
CLOSE_WEBHOOK_URL = "https://n8n.test/webhook/respond-close-convo"


@pytest.fixture
def db(monkeypatch):
    import app.services.queue_service as queue_service

    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: None)
    with blank_session() as session:
        schema = session.get_bind()._execution_options["schema_translate_map"][None]
        session.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        yield session


@pytest.fixture(autouse=True)
def _no_webhook_http():
    with patch("app.services.crm_close_convo_webhook.threading"):
        yield


@pytest.fixture(autouse=True)
def _close_webhook_configured(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(
        settings, "n8n_close_convo_webhook_url", CLOSE_WEBHOOK_URL, raising=False
    )


def _poison_the_outbox_write(monkeypatch):
    """Make the outbox INSERT fail the way it really fails: a database error,
    which aborts the surrounding transaction. A plain RuntimeError would not
    reproduce the bug - it is the aborted transaction that is the damage."""
    from app.services.integration_service import IntegrationLogService

    def _boom(self, *_a, **_k):
        self.db.execute(text("SELECT 1 / 0"))
        raise AssertionError("unreachable: the division should have raised")

    monkeypatch.setattr(IntegrationLogService, "create_integration_log", _boom)


def _seed(db):
    policy_id = str(uuid.uuid4())
    db.add(SLAPolicy(id=policy_id, code="ZZT-NORMAL", name="ZZT Normal"))
    db.add(
        SLAPolicyTier(
            id=str(uuid.uuid4()),
            policy_id=policy_id,
            tier_level=1,
            tier_name="Tier 1",
            response_hours=4,
            resolution_hours=24,
        )
    )
    contact_id = str(uuid.uuid4())
    db.add(
        RespondContact(
            id=contact_id,
            phone_number=PHONE,
            name="Aisyah Rahman",
            respond_io_id=RESPOND_IO_ID,
            session_vars={},
        )
    )
    assignee_id = str(uuid.uuid4())
    db.add(
        User(
            id=assignee_id,
            email="zzt-cs1@test.com",
            name="Agent One",
            respond_user_id="900001",
        )
    )
    agent_id = str(uuid.uuid4())
    db.add(AccessAgent(id=agent_id, code="ZZT_CS_AGENT", name="ZZT CS Agent"))
    team_id = str(uuid.uuid4())
    db.add(Team(id=team_id, name="ZZT Customer Service - Tier 1"))
    db.add(
        AgentTeam(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            code="zzt_cs_general",
            team_id=team_id,
            tier=1,
            policy_id=policy_id,
        )
    )
    db.commit()
    return {
        "policy_id": policy_id,
        "contact_id": contact_id,
        "assignee_id": assignee_id,
        "agent_code": "ZZT_CS_AGENT",
        "team_set_code": "zzt_cs_general",
    }


def _create_ticket(db, seed, *, source_message_id="wamid.msg-1"):
    return ConversationSLATrackingService(db).create_tracking(
        ConversationSLATrackingCreate(
            agent_code=seed["agent_code"],
            team_set_code=seed["team_set_code"],
            policy_id=seed["policy_id"],
            assigned_to_id=seed["assignee_id"],
            contact_phone_number=PHONE,
            source_message_id=source_message_id,
            source_message_text="Yes, please connect me to a person.",
        )
    )


# --------------------------------------------------------------------------- #
# notify_ticket_resolved_close (AC-M3)                                         #
# --------------------------------------------------------------------------- #


def test_a_failed_close_webhook_outbox_write_leaves_the_session_usable(db, monkeypatch):
    from app.services.crm_close_convo_webhook import notify_ticket_resolved_close

    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    _poison_the_outbox_write(monkeypatch)

    handed_off = notify_ticket_resolved_close(
        db,
        tracking_id=str(tracking.id),
        respond_contact_id=seed["contact_id"],
        resolved_by_user_id=seed["assignee_id"],
        resolved_at=None,
    )

    assert handed_off is False
    # Without the rollback this raises PendingRollbackError, and the resolve
    # that already committed answers 500.
    assert db.query(IntegrationLog).count() == 0


def test_a_resolve_still_succeeds_when_the_close_webhook_outbox_write_dies(
    db, monkeypatch
):
    """The resolve is committed BEFORE the webhook runs, so the caller must see
    a resolved ticket, not a 500 for work that landed."""
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    service = ConversationSLATrackingService(db)
    _poison_the_outbox_write(monkeypatch)

    updated = service.update_tracking(
        str(tracking.id),
        ConversationSLATrackingUpdate(
            is_resolved=True, resolved_by=seed["assignee_id"]
        ),
    )

    assert updated.is_resolved is True
    # The route re-reads the row to build its response; a dead session turns
    # this into the 500.
    assert service.get_tracking(str(tracking.id)).is_resolved is True


# --------------------------------------------------------------------------- #
# log_respond_send (the Respond outbox, AC-D3)                                 #
# --------------------------------------------------------------------------- #


def test_a_failed_respond_outbox_write_leaves_the_session_usable(db, monkeypatch):
    from app.services.integration_service import log_respond_send

    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    _poison_the_outbox_write(monkeypatch)

    log_respond_send(
        db,
        business_table="conversation_sla_tracking",
        business_id=str(tracking.id),
        identifier=RESPOND_IO_ID,
        request_payload={"message": {"type": "text", "text": "hello"}},
        response={"messageId": 1780751891000000},
    )

    # The message already reached the contact. The send route still has to
    # answer with the delivered state off this same session.
    assert db.query(IntegrationLog).count() == 0
    assert (
        ConversationSLATrackingService(db).get_tracking(str(tracking.id)) is not None
    )
