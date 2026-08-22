"""Who may read a ticket's contact thread, and who may still read it after a resolve.

UAC: documentation/plans/sla/conversation-intervention-tickets-acceptance-criteria.md
     AC-L7 (scroll-back paging), AC-L8 (in-thread search),
     AC-M1/AC-M2 (the resolved drawer stays open and readable)

Three defects pinned here:

1. ``GET .../conversation/page`` and ``.../conversation/search`` were the only
   ticket-drawer reads with no viewer scope at all: any authenticated user could
   page and free-text search ANY contact's WhatsApp conversation by guessing a
   tracking id. Every sibling read (``/ticket``, ``/comments``, ``/ai-draft``,
   ``/message-snippets/select``) is assignee-or-manager scoped and 404s an
   outsider rather than 403-ing, so as not to confirm the row exists.
2. Resolving a conversation ticket NULLs ``assigned_to_id`` by design, and
   ``can_user_act_on_tracking`` refused everyone on an unassigned row - so the
   person who had just resolved the ticket instantly lost the comments, the AI
   draft, the snippet picker and (with the scope added above) the thread itself,
   while AC-M1/M2 keep that very drawer open in front of them.
3. The page read built a default-workspace ``RespondClient()`` instead of
   ``for_identifier``, so a contact on a non-default Respond workspace silently
   degraded to the text-only local lane.

Run:
    venv/bin/pytest tests/test_ticket_thread_read_scope.py -q
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.access import AccessAgent, AgentTeam, RespondContact, Team
from app.models.chat_history import ChatHistory
from app.models.sla import SLAPolicy, SLAPolicyTier
from app.models.user import User
from app.schemas.sla import ConversationSLATrackingCreate
from app.services.sla_service import ConversationSLATrackingService
from app.services.user_service import UserPermissionService
from tests._pg_fixture import blank_session

PHONE = "+60123456789"
RESPOND_IO_ID = "10025531"
BASE = "/api/v1/sla-management/conversation-sla-tracking"

_ADMINS: set[str] = set()


class _DeadRespondClient:
    """Respond is unreachable, so every read falls to the local lane. Keeps the
    scope assertions about scope and not about the network."""

    def list_messages(self, *a, **k):
        raise RuntimeError("Respond.io unreachable in tests")


@pytest.fixture
def db(monkeypatch):
    import app.services.queue_service as queue_service

    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: None)
    with blank_session() as session:
        schema = session.get_bind()._execution_options["schema_translate_map"][None]
        session.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        yield session


@pytest.fixture(autouse=True)
def _roles(monkeypatch):
    """No role tables are seeded; `_ADMINS` decides who is one."""
    _ADMINS.clear()
    monkeypatch.setattr(
        UserPermissionService,
        "get_user_role_slugs",
        lambda self, uid: {"admin"} if str(uid) in _ADMINS else set(),
    )
    yield
    _ADMINS.clear()


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
    outsider_id = str(uuid.uuid4())
    admin_id = str(uuid.uuid4())
    db.add(User(id=assignee_id, email="zzt-cs1@test.com", name="Agent One"))
    db.add(User(id=outsider_id, email="zzt-outsider@test.com", name="Someone Else"))
    db.add(User(id=admin_id, email="zzt-admin@test.com", name="An Admin"))
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
        "outsider_id": outsider_id,
        "admin_id": admin_id,
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


def _seed_messages(
    db,
    *,
    channel="whatsapp",
    contact_id=RESPOND_IO_ID,
    n=3,
    prefix="hello",
    first_message_id=1000,
):
    base = datetime.utcnow() - timedelta(hours=2)
    for i in range(n):
        db.add(
            ChatHistory(
                channel=channel,
                contact_id=contact_id,
                phone_number=PHONE,
                message=f"{prefix} {i}",
                sent_at=base + timedelta(minutes=i),
                type="incoming",
                # Respond message ids are numeric; the local lane only surfaces
                # a messageId it can parse as one.
                message_id=str(first_message_id + i),
            )
        )
    db.commit()


_ACTOR: dict = {"id": None}


@pytest.fixture
def client(db):
    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(_ACTOR)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(_ACTOR)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _act_as(user_id: str) -> None:
    _ACTOR["id"] = user_id
    _ACTOR["name"] = "Test Actor"


@pytest.fixture(autouse=True)
def _local_lane_only():
    """Respond is down on BOTH construction paths (default workspace and
    per-contact), so every read here answers from the local lane."""
    with patch("app.services.integration_service.RespondClient") as client_cls:
        client_cls.return_value = _DeadRespondClient()
        client_cls.for_identifier.return_value = _DeadRespondClient()
        client_cls.for_contact_id.return_value = _DeadRespondClient()
        yield client_cls


# --------------------------------------------------------------------------- #
# The scope that was missing entirely                                          #
# --------------------------------------------------------------------------- #


def test_the_assignee_can_page_and_search_their_own_ticket_thread(client, db):
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    _seed_messages(db)
    _act_as(seed["assignee_id"])

    page = client.get(f"{BASE}/{tracking.id}/conversation/page")
    assert page.status_code == 200, page.text
    assert [i["messageId"] for i in page.json()["items"]] == [1000, 1001, 1002]

    found = client.get(f"{BASE}/{tracking.id}/conversation/search", params={"q": "hello 1"})
    assert found.status_code == 200, found.text
    assert [i["message_id"] for i in found.json()["items"]] == ["1001"]


def test_an_outsider_cannot_page_someone_elses_contact_thread(client, db):
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    _seed_messages(db)
    _act_as(seed["outsider_id"])

    page = client.get(f"{BASE}/{tracking.id}/conversation/page")
    assert page.status_code == 404, page.text


def test_an_outsider_cannot_search_someone_elses_contact_thread(client, db):
    """The worse half of the leak: free text over a stranger's whole
    conversation, which is a search engine for other people's customers."""
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    _seed_messages(db)
    _act_as(seed["outsider_id"])

    found = client.get(f"{BASE}/{tracking.id}/conversation/search", params={"q": "hello"})
    assert found.status_code == 404, found.text


def test_an_admin_can_page_and_search_any_ticket_thread(client, db):
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    _seed_messages(db)
    _ADMINS.add(seed["admin_id"])
    _act_as(seed["admin_id"])

    assert client.get(f"{BASE}/{tracking.id}/conversation/page").status_code == 200
    assert (
        client.get(
            f"{BASE}/{tracking.id}/conversation/search", params={"q": "hello"}
        ).status_code
        == 200
    )


def test_a_form_sla_stage_is_not_a_ticket_thread(client, db):
    """Form SLA rows share the table and are read from the form record's own
    chat panel; the ticket thread routes must not serve them (AC-F3 family)."""
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    tracking.source_entity_type = "complaint"
    tracking.source_entity_id = str(uuid.uuid4())
    db.commit()
    _act_as(seed["assignee_id"])

    assert client.get(f"{BASE}/{tracking.id}/conversation/page").status_code == 404
    assert (
        client.get(
            f"{BASE}/{tracking.id}/conversation/search", params={"q": "hello"}
        ).status_code
        == 404
    )


# --------------------------------------------------------------------------- #
# The resolved ticket the resolver is still looking at (AC-M1 / AC-M2)         #
# --------------------------------------------------------------------------- #


def _resolve(db, tracking, resolver_id):
    from app.schemas.sla import ConversationSLATrackingUpdate

    ConversationSLATrackingService(db).update_tracking(
        str(tracking.id),
        ConversationSLATrackingUpdate(is_resolved=True, resolved_by=str(resolver_id)),
    )
    db.expire_all()


def test_the_resolver_still_reads_the_ticket_they_just_resolved(client, db):
    """Resolve NULLs `assigned_to_id`, so an assignee-keyed check locks the
    resolver out of the drawer AC-M1 deliberately leaves open in front of them."""
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    _seed_messages(db)
    _resolve(db, tracking, seed["assignee_id"])
    _act_as(seed["assignee_id"])

    assert client.get(f"{BASE}/{tracking.id}/ticket").status_code == 200
    assert client.get(f"{BASE}/{tracking.id}/comments").status_code == 200
    assert client.get(f"{BASE}/{tracking.id}/conversation/page").status_code == 200
    assert (
        client.get(
            f"{BASE}/{tracking.id}/conversation/search", params={"q": "hello"}
        ).status_code
        == 200
    )
    # The same gate the AI-draft and snippet-picker routes read before they do
    # any work - those two also need their own RBAC permission, which a blank
    # schema does not carry, so the gate itself is asserted here.
    db.refresh(tracking)
    assert tracking.assigned_to_id is None, "resolve NULLs the assignee by design"
    assert ConversationSLATrackingService(db).can_user_act_on_tracking(
        seed["assignee_id"], tracking
    )


def test_an_unrelated_user_still_gets_404_on_a_resolved_ticket(client, db):
    """Read access follows the resolver, not everybody: an unassigned row must
    not become a free-for-all."""
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    _seed_messages(db)
    _resolve(db, tracking, seed["assignee_id"])
    _act_as(seed["outsider_id"])

    assert client.get(f"{BASE}/{tracking.id}/ticket").status_code == 404
    assert client.get(f"{BASE}/{tracking.id}/comments").status_code == 404
    assert client.get(f"{BASE}/{tracking.id}/conversation/page").status_code == 404


def test_sending_on_a_resolved_ticket_is_still_refused_for_the_resolver(client, db):
    """Read access back, write access unchanged."""
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    _resolve(db, tracking, seed["assignee_id"])
    _act_as(seed["assignee_id"])

    sent = client.post(f"{BASE}/{tracking.id}/ticket/send", json={"text": "hello again"})
    assert sent.status_code == 400, sent.text


# --------------------------------------------------------------------------- #
# The workspace the page read talks to                                         #
# --------------------------------------------------------------------------- #


def test_the_page_read_uses_the_contacts_own_respond_workspace(db):
    """`RespondClient()` is the DEFAULT workspace. A contact belonging to any
    other workspace would 401 and silently fall back to the text-only local
    lane, which is precisely the degradation AC-L7 was revised to avoid."""
    seed = _seed(db)
    tracking = _create_ticket(db, seed)
    service = ConversationSLATrackingService(db)

    with patch("app.services.integration_service.RespondClient") as client_cls:
        client_cls.for_identifier.return_value.list_messages.return_value = {"items": []}
        service.fetch_conversation_thread_page(
            str(tracking.id), viewer_user_id=seed["assignee_id"], limit=10
        )

    client_cls.for_identifier.assert_called_once()
    args, _kwargs = client_cls.for_identifier.call_args
    assert args[1] == RESPOND_IO_ID, "resolved per contact, not per deployment default"
    assert client_cls.call_count == 0, "the bare default-workspace client is never built"


# --------------------------------------------------------------------------- #
# Thread lane: one contact can exist on more than one channel                  #
# --------------------------------------------------------------------------- #


def test_the_local_lane_pages_only_the_contacts_own_channel(db):
    """`ix_chat_histories_channel_contact_sent_id` leads on `channel`, so a
    contact-only predicate cannot use it - and a same-id contact on another
    channel would bleed into the thread."""
    from app.services import conversation_thread_service as thread_service

    _seed(db)
    _seed_messages(db, channel="whatsapp", n=2, prefix="wa", first_message_id=1000)
    _seed_messages(db, channel="telegram", n=2, prefix="tg", first_message_id=2000)

    contact = thread_service.ThreadContact(
        respond_io_id=RESPOND_IO_ID, phone_number=PHONE, channel="whatsapp"
    )
    page = thread_service.fetch_thread_page(db, contact, limit=50, client=_DeadRespondClient())

    assert [i["message"]["text"] for i in page["items"]] == ["wa 0", "wa 1"]

    found = thread_service.search_thread(db, contact, q=" 0")
    assert [i["message_id"] for i in found["items"]] == ["1000"]
