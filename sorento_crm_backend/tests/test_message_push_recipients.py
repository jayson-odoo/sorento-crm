"""Who a WhatsApp message buzzes, and with which link.

UAC: documentation/plans/notifications/message-push-acceptance-criteria.md
     AC-M7  (the assignee, gated by their own scope)
     AC-M8  (an active unexpired coverer, gated by theirs)
     AC-M9  (`all_contacts` hears everything, assigned or not)
     AC-M10 / AC-M10a / AC-M10b (a contact holds SEVERAL open tickets at once)
     AC-M11 (outgoing messages push nobody)
     AC-M12 (one user, one push, with the best link)
     AC-M13 (a form-SLA row is never mistaken for the conversation tracking)
     AC-M14 / AC-M14a / AC-M15 (title, truncated body, per-recipient link, tag)

The multi-open cases are the reason this file is long. Conversation SLA stopped
being one-open-per-contact, so the reduction `get_preferred_tracking_for_contact`
performs would silence every assignee but one - these tests pin that EVERY open
ticket's assignee is resolved, each to their own ticket.

Every row is marker-prefixed and seeded here through the ORM. Nothing is borrowed
with a `LIMIT 1`: CI's database is empty, so a borrowed policy resolves to None
there and takes the file down on a NOT NULL FK.

Run:
    venv/bin/pytest tests/test_message_push_recipients.py -q
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from app.models.access import RespondContact
from app.models.chat_history import ChatHistory
from app.models.notification import NotificationSubscription
from app.models.sla import ConversationSLATracking, SLAPolicy, SLAPolicyTier
from app.models.user import User
from tests._pg_fixture import TEST_PREFIX, blank_session

CONVERSATIONS_LINK = "/sla-management/conversations"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


# --------------------------------------------------------------------------- #
# Seeding - policy -> contact -> users -> trackings                            #
# --------------------------------------------------------------------------- #


def _marker(stem: str) -> str:
    return f"{TEST_PREFIX}-{stem}-{uuid.uuid4().hex[:8]}"


def _user(db, scope: str = "assigned_and_coverage", label: str = "user") -> str:
    uid = str(uuid.uuid4())
    db.add(
        User(
            id=uid,
            email=f"{TEST_PREFIX.lower()}-{uid[:8]}@test.invalid",
            name=f"{TEST_PREFIX} {label}",
            status="ACTIVE",
            notify_push_message_scope=scope,
        )
    )
    db.commit()
    return uid


def _policy(db) -> str:
    policy_id = str(uuid.uuid4())
    db.add(SLAPolicy(id=policy_id, code=_marker("POL"), name=f"{TEST_PREFIX} policy"))
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
    db.commit()
    return policy_id


def _contact(db, *, name: str = "Ah Meng") -> RespondContact:
    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=_marker("phone"),
        name=f"{TEST_PREFIX} {name}",
        respond_io_id=_marker("rio"),
        session_vars={},
    )
    db.add(contact)
    db.commit()
    return contact


def _tracking(
    db,
    *,
    policy_id: str,
    contact: RespondContact,
    assigned_to_id: str | None,
    is_resolved: bool = False,
    source_entity_type: str | None = None,
    updated_ago_minutes: int = 0,
) -> str:
    now = datetime.utcnow()
    tracking_id = str(uuid.uuid4())
    db.add(
        ConversationSLATracking(
            id=tracking_id,
            policy_id=policy_id,
            current_tier=1,
            initiated_at=now - timedelta(hours=2),
            current_tier_started_at=now - timedelta(hours=1),
            due_at=now + timedelta(hours=4),
            due_at_resolution=now + timedelta(hours=20),
            is_responded=False,
            is_resolved=is_resolved,
            respond_contact_id=contact.id,
            assigned_to_id=assigned_to_id,
            source_entity_type=source_entity_type,
            source_entity_id=str(uuid.uuid4()) if source_entity_type else None,
        )
    )
    db.commit()
    # `updated_at` carries onupdate=now(), so the ordering key is set explicitly
    # rather than by hoping the inserts land in a different millisecond.
    db.execute(
        text("UPDATE conversation_sla_tracking SET updated_at = :t WHERE id = :i"),
        {"t": now - timedelta(minutes=updated_ago_minutes), "i": tracking_id},
    )
    db.commit()
    return tracking_id


def _coverage(db, *, coverer: str, target: str, expires_at=None, is_active=True) -> None:
    db.add(
        NotificationSubscription(
            id=str(uuid.uuid4()),
            subscriber_id=coverer,
            target_user_id=target,
            is_active=is_active,
            expires_at=expires_at,
        )
    )
    db.commit()


def _message(
    db,
    contact: RespondContact,
    *,
    body: str = "Can I get the price for the 900mm hood?",
    type_: str = "incoming",
) -> ChatHistory:
    row = ChatHistory(
        channel="whatsapp",
        contact_id=contact.respond_io_id,
        phone_number=contact.phone_number,
        message=body,
        sent_at=datetime.utcnow(),
        type=type_,
        message_id=_marker("msg"),
    )
    db.add(row)
    db.commit()
    return row


def _resolve(db, row):
    from app.services.message_push_service import recipients_for_message

    return recipients_for_message(db, row)


def _by_user(recipients) -> dict:
    return {r.user_id: r.link for r in recipients}


# --------------------------------------------------------------------------- #
# AC-M7 - the assignee, gated by their own scope                               #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "scope", ["assigned_only", "assigned_and_coverage", "all_contacts"]
)
def test_the_assignee_hears_it_on_every_scope_but_off(db, scope):
    policy_id = _policy(db)
    contact = _contact(db)
    assignee = _user(db, scope, "assignee")
    tracking_id = _tracking(
        db, policy_id=policy_id, contact=contact, assigned_to_id=assignee
    )

    recipients = _resolve(db, _message(db, contact))

    assert _by_user(recipients) == {assignee: f"{CONVERSATIONS_LINK}?contact={contact.respond_io_id}"}


def test_an_assignee_who_turned_it_off_hears_nothing(db):
    policy_id = _policy(db)
    contact = _contact(db)
    assignee = _user(db, "off", "assignee")
    _tracking(db, policy_id=policy_id, contact=contact, assigned_to_id=assignee)

    assert _resolve(db, _message(db, contact)) == []


# --------------------------------------------------------------------------- #
# AC-M8 - coverage                                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("scope", ["assigned_and_coverage", "all_contacts"])
def test_an_active_coverer_hears_the_covered_assignee_s_message(db, scope):
    policy_id = _policy(db)
    contact = _contact(db)
    assignee = _user(db, "assigned_only", "assignee")
    coverer = _user(db, scope, "coverer")
    _coverage(db, coverer=coverer, target=assignee)
    tracking_id = _tracking(
        db, policy_id=policy_id, contact=contact, assigned_to_id=assignee
    )

    recipients = _by_user(_resolve(db, _message(db, contact)))

    assert recipients[coverer] == f"{CONVERSATIONS_LINK}?contact={contact.respond_io_id}"


@pytest.mark.parametrize("scope", ["assigned_only", "off"])
def test_a_coverer_who_did_not_ask_for_coverage_pushes_hears_nothing(db, scope):
    policy_id = _policy(db)
    contact = _contact(db)
    assignee = _user(db, "assigned_only", "assignee")
    coverer = _user(db, scope, "coverer")
    _coverage(db, coverer=coverer, target=assignee)
    _tracking(db, policy_id=policy_id, contact=contact, assigned_to_id=assignee)

    assert coverer not in _by_user(_resolve(db, _message(db, contact)))


def test_an_expired_coverage_hears_nothing(db):
    policy_id = _policy(db)
    contact = _contact(db)
    assignee = _user(db, "assigned_only", "assignee")
    coverer = _user(db, "assigned_and_coverage", "coverer")
    _coverage(
        db,
        coverer=coverer,
        target=assignee,
        expires_at=datetime.utcnow() - timedelta(days=1),
    )
    _tracking(db, policy_id=policy_id, contact=contact, assigned_to_id=assignee)

    assert coverer not in _by_user(_resolve(db, _message(db, contact)))


def test_an_inactive_coverage_hears_nothing(db):
    policy_id = _policy(db)
    contact = _contact(db)
    assignee = _user(db, "assigned_only", "assignee")
    coverer = _user(db, "assigned_and_coverage", "coverer")
    _coverage(db, coverer=coverer, target=assignee, is_active=False)
    _tracking(db, policy_id=policy_id, contact=contact, assigned_to_id=assignee)

    assert coverer not in _by_user(_resolve(db, _message(db, contact)))


# --------------------------------------------------------------------------- #
# AC-M9 / AC-M10b - all_contacts, and the no-assignee floor                    #
# --------------------------------------------------------------------------- #


def test_all_contacts_hears_a_contact_nobody_is_assigned(db):
    contact = _contact(db)
    manager = _user(db, "all_contacts", "manager")

    recipients = _by_user(_resolve(db, _message(db, contact)))

    assert recipients == {
        manager: f"{CONVERSATIONS_LINK}?contact={contact.respond_io_id}"
    }


def test_all_contacts_gets_the_most_recently_updated_open_ticket(db):
    policy_id = _policy(db)
    contact = _contact(db)
    assignee = _user(db, "assigned_only", "assignee")
    manager = _user(db, "all_contacts", "manager")
    _tracking(
        db,
        policy_id=policy_id,
        contact=contact,
        assigned_to_id=assignee,
        updated_ago_minutes=60,
    )
    newest = _tracking(
        db,
        policy_id=policy_id,
        contact=contact,
        assigned_to_id=assignee,
        updated_ago_minutes=1,
    )

    recipients = _by_user(_resolve(db, _message(db, contact)))

    assert recipients[manager] == f"{CONVERSATIONS_LINK}?contact={contact.respond_io_id}"


def test_an_unassigned_open_ticket_pushes_only_all_contacts_users(db):
    policy_id = _policy(db)
    contact = _contact(db)
    _user(db, "assigned_and_coverage", "bystander")
    manager = _user(db, "all_contacts", "manager")
    _tracking(db, policy_id=policy_id, contact=contact, assigned_to_id=None)

    assert list(_by_user(_resolve(db, _message(db, contact)))) == [manager]


def test_nobody_is_reached_by_a_team_or_tier_fallback(db):
    policy_id = _policy(db)
    contact = _contact(db)
    _user(db, "assigned_and_coverage", "teammate")
    _user(db, "assigned_only", "other")
    _tracking(db, policy_id=policy_id, contact=contact, assigned_to_id=None)

    assert _resolve(db, _message(db, contact)) == []


# --------------------------------------------------------------------------- #
# AC-M10 / AC-M10a - several open tickets on one contact                       #
# --------------------------------------------------------------------------- #


def test_every_open_ticket_s_assignee_gets_their_own_link(db):
    policy_id = _policy(db)
    contact = _contact(db)
    first = _user(db, "assigned_only", "first")
    second = _user(db, "assigned_only", "second")
    first_ticket = _tracking(
        db, policy_id=policy_id, contact=contact, assigned_to_id=first
    )
    second_ticket = _tracking(
        db, policy_id=policy_id, contact=contact, assigned_to_id=second
    )

    recipients = _by_user(_resolve(db, _message(db, contact)))

    assert recipients == {
        first: f"{CONVERSATIONS_LINK}?contact={contact.respond_io_id}",
        second: f"{CONVERSATIONS_LINK}?contact={contact.respond_io_id}",
    }


def test_each_multi_open_assignee_is_gated_by_their_own_scope(db):
    policy_id = _policy(db)
    contact = _contact(db)
    listening = _user(db, "assigned_only", "listening")
    silent = _user(db, "off", "silent")
    listening_ticket = _tracking(
        db, policy_id=policy_id, contact=contact, assigned_to_id=listening
    )
    _tracking(db, policy_id=policy_id, contact=contact, assigned_to_id=silent)

    recipients = _by_user(_resolve(db, _message(db, contact)))

    assert recipients == {listening: f"{CONVERSATIONS_LINK}?contact={contact.respond_io_id}"}


def test_a_resolved_ticket_s_assignee_drops_out_and_the_rest_stay(db):
    policy_id = _policy(db)
    contact = _contact(db)
    closed_owner = _user(db, "assigned_only", "closed")
    open_owner = _user(db, "assigned_only", "open")
    _tracking(
        db,
        policy_id=policy_id,
        contact=contact,
        assigned_to_id=closed_owner,
        is_resolved=True,
    )
    open_ticket = _tracking(
        db, policy_id=policy_id, contact=contact, assigned_to_id=open_owner
    )

    recipients = _by_user(_resolve(db, _message(db, contact)))

    assert recipients == {open_owner: f"{CONVERSATIONS_LINK}?contact={contact.respond_io_id}"}


# --------------------------------------------------------------------------- #
# AC-M11 - outgoing pushes nobody                                              #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("type_", ["outgoing", "OUTGOING", "note"])
def test_a_message_that_is_not_from_the_contact_pushes_nobody(db, type_):
    policy_id = _policy(db)
    contact = _contact(db)
    assignee = _user(db, "all_contacts", "assignee")
    _tracking(db, policy_id=policy_id, contact=contact, assigned_to_id=assignee)

    assert _resolve(db, _message(db, contact, type_=type_)) == []


# --------------------------------------------------------------------------- #
# AC-M12 - one user, one push                                                  #
# --------------------------------------------------------------------------- #


def test_assignee_and_coverer_of_the_same_person_is_one_push(db):
    """A user covering themselves is nonsense, so the real shape is: A assigns
    ticket 1, and A also covers B who assigns ticket 2. A hears once, on A's own."""
    policy_id = _policy(db)
    contact = _contact(db)
    a = _user(db, "assigned_and_coverage", "a")
    b = _user(db, "assigned_only", "b")
    _coverage(db, coverer=a, target=b)
    a_ticket = _tracking(
        db,
        policy_id=policy_id,
        contact=contact,
        assigned_to_id=a,
        updated_ago_minutes=90,
    )
    _tracking(
        db,
        policy_id=policy_id,
        contact=contact,
        assigned_to_id=b,
        updated_ago_minutes=1,
    )

    recipients = _resolve(db, _message(db, contact))

    assert [r.user_id for r in recipients].count(a) == 1
    assert _by_user(recipients)[a] == f"{CONVERSATIONS_LINK}?contact={contact.respond_io_id}"


def test_two_of_my_own_tickets_is_one_push_on_the_most_recent(db):
    policy_id = _policy(db)
    contact = _contact(db)
    owner = _user(db, "assigned_only", "owner")
    _tracking(
        db,
        policy_id=policy_id,
        contact=contact,
        assigned_to_id=owner,
        updated_ago_minutes=120,
    )
    newest = _tracking(
        db,
        policy_id=policy_id,
        contact=contact,
        assigned_to_id=owner,
        updated_ago_minutes=2,
    )

    recipients = _resolve(db, _message(db, contact))

    assert len(recipients) == 1
    assert recipients[0].link == f"{CONVERSATIONS_LINK}?contact={contact.respond_io_id}"


def test_an_assignee_who_also_chose_all_contacts_keeps_their_own_ticket_link(db):
    policy_id = _policy(db)
    contact = _contact(db)
    manager = _user(db, "all_contacts", "manager")
    other = _user(db, "assigned_only", "other")
    manager_ticket = _tracking(
        db,
        policy_id=policy_id,
        contact=contact,
        assigned_to_id=manager,
        updated_ago_minutes=90,
    )
    _tracking(
        db,
        policy_id=policy_id,
        contact=contact,
        assigned_to_id=other,
        updated_ago_minutes=1,
    )

    recipients = _resolve(db, _message(db, contact))

    assert len(recipients) == 2
    assert _by_user(recipients)[manager] == f"{CONVERSATIONS_LINK}?contact={contact.respond_io_id}"


# --------------------------------------------------------------------------- #
# AC-M13 - a form-SLA row is not the conversation tracking                     #
# --------------------------------------------------------------------------- #


def test_a_form_sla_row_on_the_same_contact_pushes_nobody(db):
    policy_id = _policy(db)
    contact = _contact(db)
    form_handler = _user(db, "all_contacts", "form-handler")
    _tracking(
        db,
        policy_id=policy_id,
        contact=contact,
        assigned_to_id=form_handler,
        source_entity_type="complaint",
    )

    recipients = _by_user(_resolve(db, _message(db, contact)))

    # `all_contacts` still hears it - but on the no-open-ticket fallback link,
    # which proves the form row was not read as the conversation tracking.
    assert recipients == {
        form_handler: f"{CONVERSATIONS_LINK}?contact={contact.respond_io_id}"
    }


def test_a_form_sla_row_does_not_win_the_all_contacts_link(db):
    policy_id = _policy(db)
    contact = _contact(db)
    manager = _user(db, "all_contacts", "manager")
    assignee = _user(db, "assigned_only", "assignee")
    conversation_ticket = _tracking(
        db,
        policy_id=policy_id,
        contact=contact,
        assigned_to_id=assignee,
        updated_ago_minutes=60,
    )
    _tracking(
        db,
        policy_id=policy_id,
        contact=contact,
        assigned_to_id=assignee,
        source_entity_type="stock_inquiry",
        updated_ago_minutes=1,
    )

    recipients = _by_user(_resolve(db, _message(db, contact)))

    assert recipients[manager] == f"{CONVERSATIONS_LINK}?contact={contact.respond_io_id}"


# --------------------------------------------------------------------------- #
# AC-M14 / AC-M14a / AC-M15 - what the phone shows                             #
# --------------------------------------------------------------------------- #


def test_the_title_is_the_contact_and_the_body_is_the_message(db):
    from app.services.message_push_service import build_message_push

    policy_id = _policy(db)
    contact = _contact(db)
    assignee = _user(db, "assigned_only", "assignee")
    _tracking(db, policy_id=policy_id, contact=contact, assigned_to_id=assignee)

    push = build_message_push(db, _message(db, contact))

    assert push.title == contact.name
    assert push.body == "Can I get the price for the 900mm hood?"
    assert push.tag == f"contact-{contact.respond_io_id}"


def test_a_long_body_is_truncated_to_120_characters_with_an_ellipsis(db):
    from app.services.message_push_service import build_message_push

    contact = _contact(db)
    _user(db, "all_contacts", "manager")
    long_message = "x" * 400

    push = build_message_push(db, _message(db, contact, body=long_message))

    assert len(push.body) == 120
    assert push.body.endswith("...")


def test_a_body_of_exactly_120_characters_is_left_alone(db):
    from app.services.message_push_service import build_message_push

    contact = _contact(db)
    _user(db, "all_contacts", "manager")
    body = "y" * 120

    push = build_message_push(db, _message(db, contact, body=body))

    assert push.body == body


def test_an_unknown_contact_still_titles_the_push_with_something_readable(db):
    from app.services.message_push_service import build_message_push

    contact = _contact(db)
    contact_io_id = contact.respond_io_id
    db.delete(contact)
    db.commit()
    manager = _user(db, "all_contacts", "manager")
    row = ChatHistory(
        channel="whatsapp",
        contact_id=contact_io_id,
        phone_number=_marker("phone"),
        message="Hello",
        sent_at=datetime.utcnow(),
        type="incoming",
        first_name="Ah",
        last_name="Meng",
        message_id=_marker("msg"),
    )
    db.add(row)
    db.commit()

    push = build_message_push(db, row)

    assert push.title == "Ah Meng"
    assert [r.user_id for r in push.recipients] == [manager]


def test_an_outgoing_message_builds_no_push_at_all(db):
    from app.services.message_push_service import build_message_push

    contact = _contact(db)
    _user(db, "all_contacts", "manager")

    assert build_message_push(db, _message(db, contact, type_="outgoing")) is None
