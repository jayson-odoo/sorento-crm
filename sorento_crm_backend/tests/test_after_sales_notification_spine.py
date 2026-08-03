"""S4 gate - the notification spine, the Respond outbox, calls, assignment fallback.

Satisfies AC-H1 to AC-H14, AC-M33, AC-M34, AC-M35, plus the 2026-08-03 rulings
AC-M33a, AC-M33b, AC-M35a and AC-H8a.

S4 is the slice where a customer stops being a second-class recipient. Today a
``notifications`` row can only address a ``users.id``: the column is NOT NULL, so
"tell the contact" is implemented somewhere else entirely (F2c resolves a
``respond_io_id`` and sends, writing an outbox row and no notification). S4 makes
one spine carry both, which means the dedupe, the delivery fan-out, the outbox and
the worker all have to learn a second kind of recipient at once. Every one of those
is a place where a contact silently becomes a no-op instead of an error.

Nine things shape this suite, and each one is a place the specification is wrong,
silent, or describes something that cannot be built as written.

1. **The plan's own DDL cannot execute.** It says
   ``respond_contact_id uuid REFERENCES respond_contacts(id)`` and
   ``respond_contacts.id`` is ``TEXT`` (S1 pinned this; AC-A2 and AC-F2b-1 record
   the same trap two slices running). Postgres refuses a uuid foreign key onto a
   text primary key. The column must be text/varchar. Asserted as a type check, not
   just an existence check, because a uuid column would fail at migration time in
   production and pass every model-level test that only asks "is it there".

2. **The existing unique constraint stops working the moment ``user_id`` is
   nullable, and it stops working silently.** Postgres treats NULLs as distinct in
   a unique constraint, so ``(NULL, 'complaint', <id>, 'visit_confirmed')`` never
   collides with itself: every contact notification is unique, dedupe evaporates,
   and the symptom is a customer receiving the same WhatsApp message twice rather
   than an error anybody sees. Two partial unique indexes are the fix and BOTH
   halves are asserted by provoking a real IntegrityError, because an index that
   exists and does not dedupe looks identical to one that does.

3. **F2c's mechanism is replaced, not duplicated.** ``notify_submission_contact``
   currently sends and writes an outbox row with NO notification, precisely because
   ``user_id`` was NOT NULL. AC-H2 says exactly one spine records every
   notification, so once the column is nullable that reason is gone and the contact
   path moves onto the spine. Two mechanisms for "tell a contact" is the drift this
   build keeps finding. **The rows F2c already wrote keep ``correlation_id`` NULL
   forever**, which is why point 4 is not optional.

4. **The outbox is a LEFT JOIN (AC-H8a).** AI replies, n8n-initiated sends and every
   pre-S4 F2c row carry no notification. An inner join loses exactly the visibility
   the screen exists to give, and it loses it quietly - the rows are simply absent.

5. **AC-M33's "no assignee resolves" is TWO raise sites, not one.**
   ``_start_for_config`` raises when no team exists at or above the start tier AND
   again when the resolved team has no members. ``resolve_team_with_tier_fallback``
   already walks upward, so reaching either one means every tier failed. A fallback
   wired into only the first leaves the second crashing on exactly the
   configuration - a team row with nobody in it - that is most likely in practice.

6. **A fallback that is itself unresolvable must not move the crash one line
   down.** A configured user who was deleted or deactivated is the normal decay
   path for a backstop nobody looks at. The pinned behaviour is to fall through to
   the ORIGINAL raise, so the operator sees the message that names the real
   misconfiguration rather than an AttributeError from a None.

7. **AC-M33b's "bit-for-bit unchanged" is the whole safety argument for shipping
   this uniformly**, and it is asserted in the sibling guards file against a
   NON-after-sales form type, because that is the claim that matters: purchase
   requests, sponsorship forms and stock inquiries must behave identically until
   somebody configures a fallback.

8. **"Exactly one open case" needs a definition of open, and the status engine now
   owns one.** Open = ``not is_terminal`` on the complaint graph. It is NOT
   ``LINKABLE_STATUSES``, which answers a different question (which complaints a
   delivery order may fulfil) and would make a ``submitted`` complaint invisible to
   call attribution. See ``test_open_is_the_status_engines_terminality`` for the
   consequence this exposes: the complaint graph marks only ``closed`` and
   ``voided`` terminal, so ``rejected`` reads as open forever.

9. **A call that ended is not a call that connected.** The manual path here must
   already record ``answered`` / ``missed`` / ``no_answer`` plus duration, because
   S5's automatic path lands on the same vocabulary (AC-M36c) and a second
   vocabulary invented there is a migration nobody scheduled.

Decisions taken here because the AC is silent. Asserted rather than assumed, so the
next reader inherits an answer instead of a coin flip:

- **One spine means one function.** ``create_with_channel_preferences`` grows
  ``respond_contact_id`` and ``user_id`` becomes optional, rather than a parallel
  ``create_for_contact``. Two creators is how the dedupe rules drift apart.
- **Exactly one recipient.** Both set, or neither, is a programming error and
  raises. The CHECK constraint catches the database half; the service catches the
  half that would otherwise insert a row addressed to two different people.
- **A contact's channels are ``whatsapp`` + ``in_app``, always** (AC-H3). ``in_app``
  IS the portal record - the contact reads it through the portal, not the staff
  bell. No email, no web push, and the per-user preference attributes are ignored
  outright rather than defaulted, because a contact has no row to read them from.
- **``assignment_unresolved`` lives on the tracker**, not on the case. The flag is
  rendered on the pending-task row in S4a, and a pending-task row IS a tracker; a
  case-level column would paint one stage's routing failure onto every other stage.
- **An unattached call parks on the contact** (AC-M35a), ``entity_type`` =
  ``respond_contact``, ``entity_id`` = ``respond_contacts.id``, and attachment
  re-keys the SAME row so the activity id in an audit trail survives.
- **``activity_events.kind`` gains ``call``.** Not ``system`` (nobody's software did
  it) and not ``user_update`` (it is not a composer post, and it carries structured
  fields no composer produces).
- **The outbox's ``sent_as`` is derived from the stamped request payload**, so a
  closed-window failure reads as a template attempt (AC-H14) without a new column.

Everything runs on Postgres via ``blank_session``. Rows carry ``TEST_PREFIX`` and
are discarded by the outer rollback; nothing is counted across a shared table, which
holds real production data. Respond.io is never actually called: every send is
monkeypatched at ``send_text_or_template``, the one choke point every path goes
through.

Run: venv/bin/python -m pytest tests/test_after_sales_notification_spine.py -q -p no:randomly
"""
from __future__ import annotations

import importlib
import importlib.util
import inspect
import pathlib
import uuid
from datetime import date, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.exc import IntegrityError

# MUST be the first app import - resolves the circular import in
# app.modules.runtime.guards that bites any module importing app.services first.
from app.main import app  # noqa: E402,F401

from app.models.access import (  # noqa: E402
    AccessAgent,
    AgentTeam,
    RespondContact,
    Team,
    TeamMember,
)
from app.models.activities import ActivityEvent  # noqa: E402
from app.models.complaints import Complaint  # noqa: E402
from app.models.integration import IntegrationLog  # noqa: E402
from app.models.notification import Notification, NotificationDelivery  # noqa: E402
from app.models.sla import (  # noqa: E402
    ConversationSLATracking,
    FormSLAConfig,
    SLAPolicy,
    SLAPolicyTier,
)
from app.models.user import User  # noqa: E402

from ._pg_fixture import TEST_PREFIX, blank_session, unique_code

# ---------------------------------------------------------------- the contract
#
# Names S4 is expected to add, as constants so the implementer reads the whole
# contract on one screen and a rename is a single edit.

# The event-first outbox query. Its own module rather than another branch inside
# IntegrationLogService.list_integration_logs, because that method is already the
# generic log list with eleven filters and the outbox needs three joins it must
# never impose on the generic caller.
OUTBOX_MODULE = "app.services.respond_outbox_service"
OUTBOX_ROUTE = "/api/v1/integrations/respond-outbox"

# The manual call path (AC-M34). Its own module: attribution (AC-M35) is a rule
# about cases, and burying it in activities_service would make the generic feed
# depend on complaints.
CALL_MODULE = "app.services.call_activity_service"

# AC-M35a. Where a call with no attributable case parks.
UNATTACHED_ENTITY_TYPE = "respond_contact"

# AC-M34 / AC-M36c. One vocabulary, shared with S5's automatic path.
CALL_OUTCOMES = frozenset({"answered", "missed", "no_answer"})
CALL_DIRECTIONS = frozenset({"inbound", "outbound"})
CALL_ACTIVITY_KIND = "call"

# AC-H1. Two partial unique indexes replacing one whole-table unique constraint.
OLD_UNIQUE = "uq_notification_user_dedup_event"
USER_DEDUP_INDEX = "uq_notifications_user_dedup"
CONTACT_DEDUP_INDEX = "uq_notifications_contact_dedup"
RECIPIENT_CHECK = "notifications_recipient_present"

# AC-H3. What a contact recipient receives, exhaustively.
CONTACT_CHANNELS = frozenset({"whatsapp", "in_app"})

# AC-M33a. The backstop lives beside the resolution it backs up.
FALLBACK_COLUMN = "assignment_fallback_user_id"
UNRESOLVED_FLAG = "assignment_unresolved"


# ---------------------------------------------------------------------- fixtures


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


# ----------------------------------------------------------------------- helpers


def _module(dotted: str, why: str):
    if importlib.util.find_spec(dotted) is None:
        raise AssertionError(f"{dotted} does not exist. {why}")
    return importlib.import_module(dotted)


def _outbox():
    return _module(
        OUTBOX_MODULE,
        "S4 needs one module owning the event-first outbox query so the LEFT JOIN "
        "of AC-H8a is written once and cannot be regressed into an inner join by a "
        "second caller.",
    )


def _calls():
    return _module(
        CALL_MODULE,
        "S4 owns the manual call path: log_call, attach_call and the per-contact "
        "inbox. Attribution is a rule about open cases, so it does not belong in "
        "the generic activities service.",
    )


def _fn(module, name: str, signature: str):
    fn = getattr(module, name, None)
    assert callable(fn), f"{module.__name__}.{name}{signature} must exist."
    return fn


def _columns(model):
    return {c.key: c for c in model.__table__.columns}


def _index_names(model):
    return {ix.name for ix in model.__table__.indexes}


def _constraint_names(model):
    return {c.name for c in model.__table__.constraints if c.name}


def _user(db, label: str = "staff", **overrides) -> User:
    user_id = unique_code(label).lower()
    user = User(
        id=user_id,
        email=f"{user_id}@{TEST_PREFIX.lower()}.invalid",
        name=f"{TEST_PREFIX} {label}",
        status="ACTIVE",
    )
    for key, value in overrides.items():
        setattr(user, key, value)
    db.add(user)
    db.flush()
    return user


def _contact(db, *, respond_io_id: str | None = "1234567") -> RespondContact:
    """A respond_contacts row. ``id`` is TEXT and deliberately not uuid-shaped."""
    contact = RespondContact(
        id=unique_code("contact").lower(),
        phone_number=f"+60{uuid.uuid4().int % 10**9:09d}",
        name=f"{TEST_PREFIX} Vinod",
        respond_io_id=respond_io_id,
    )
    db.add(contact)
    db.flush()
    return contact


def _complaint(db, *, status: str = "submitted", contact: RespondContact | None = None) -> Complaint:
    complaint = Complaint(
        id=str(uuid.uuid4()),
        complaint_number=unique_code("cmp")[:50],
        complaint_date=date.today(),
        status=status,
        contact_id=contact.id if contact else None,
    )
    db.add(complaint)
    db.flush()
    return complaint


def _log(db, **overrides) -> IntegrationLog:
    values = {
        "id": str(uuid.uuid4()),
        "integration_channel": "respond_io",
        "business_table": "complaints",
        "business_id": str(uuid.uuid4()),
        "direction": "outbound",
        "endpoint": "https://api.respond.io/v2/contact/id:1234567/message",
        "http_method": "POST",
        "status": "success",
    }
    values.update(overrides)
    row = IntegrationLog(**values)
    db.add(row)
    db.flush()
    return row


def _agent(db, *, fallback: User | None = None) -> AccessAgent:
    agent = AccessAgent(
        id=str(uuid.uuid4()),
        code=unique_code("agent").lower(),
        name=f"{TEST_PREFIX} after-sales",
    )
    if fallback is not None:
        setattr(agent, FALLBACK_COLUMN, fallback.id)
    db.add(agent)
    db.flush()
    return agent


def _policy(db) -> SLAPolicy:
    policy = SLAPolicy(
        id=str(uuid.uuid4()),
        code=unique_code("pol").lower(),
        name=f"{TEST_PREFIX} policy",
    )
    db.add(policy)
    db.flush()
    for tier in (1, 2, 3):
        db.add(
            SLAPolicyTier(
                id=str(uuid.uuid4()),
                policy_id=policy.id,
                tier_level=tier,
                tier_name=f"{TEST_PREFIX} tier {tier}",
                response_hours=4,
                resolution_hours=24,
            )
        )
    db.flush()
    return policy


def _config(db, agent: AccessAgent, policy: SLAPolicy, *, source_entity_type: str = "complaint") -> FormSLAConfig:
    config = FormSLAConfig(
        id=str(uuid.uuid4()),
        source_entity_type=source_entity_type,
        stage_code=unique_code("stage").lower()[:100],
        policy_id=policy.id,
        agent_code=agent.code,
        team_set_code=unique_code("set").lower()[:100],
        start_event="submitted",
        resolve_event="closed",
    )
    db.add(config)
    db.flush()
    return config


def _team(db, agent: AccessAgent, config: FormSLAConfig, policy: SLAPolicy, tier: int, members: list[User]):
    team = Team(id=str(uuid.uuid4()), name=unique_code("team"))
    db.add(team)
    db.flush()
    for order, member in enumerate(members):
        db.add(
            TeamMember(
                id=str(uuid.uuid4()),
                team_id=team.id,
                user_id=member.id,
                sort_order=order,
            )
        )
    db.add(
        AgentTeam(
            id=str(uuid.uuid4()),
            agent_id=agent.id,
            code=config.team_set_code,
            team_id=team.id,
            tier=tier,
            policy_id=policy.id,
        )
    )
    db.flush()
    return team


def _orchestrator(db):
    from app.services.form_sla_service import FormSLAOrchestrator

    return FormSLAOrchestrator(db)


class _Sent:
    """A recording stand-in for ``send_text_or_template``. Nothing leaves the box."""

    def __init__(self, *, raises: Exception | None = None, sent_as: str = "text"):
        self.raises = raises
        self.sent_as = sent_as
        self.calls: list[dict] = []

    def __call__(self, db, **kwargs):
        self.calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        return {
            "sent_as": self.sent_as,
            "response": {"messageId": 1},
            "window_state": {"open": True},
            "request_payload": {"message": {"type": "text", "text": kwargs.get("text")}},
        }


def _closed_window_error() -> Exception:
    """What the window-aware send raises when it had to fall back to a template.

    The payload it stamps on the exception is the TEMPLATE it actually attempted,
    which is the whole of AC-H14.
    """
    error = RuntimeError("401 Unauthorized")
    error.request_payload = {
        "message": {
            "type": "whatsapp_template",
            "template": {"name": "complaint_chat", "languageCode": "en"},
        }
    }

    class _Response:
        status_code = 401
        text = '{"message":"Unauthorized"}'

    error.response = _Response()
    return error


# =============================================================================
# AC-H1 - the schema, and the two ways it can be built so that it does nothing
# =============================================================================


def test_notifications_user_id_becomes_nullable():
    """AC-H1. A contact recipient has no ``users.id`` and never will."""
    column = _columns(Notification)["user_id"]
    assert column.nullable, (
        "notifications.user_id must be nullable. While it is NOT NULL there is no "
        "'no user' notification, which is exactly why F2c had to invent a second "
        "mechanism for telling a contact anything."
    )


def test_notifications_gains_respond_contact_id_as_text_not_uuid():
    """AC-H1, correcting the plan's DDL.

    The plan says ``respond_contact_id uuid REFERENCES respond_contacts(id)``.
    ``respond_contacts.id`` is TEXT. Postgres will not create that foreign key, so
    the migration fails on the way to production while a uuid column on the model
    passes every other assertion in this file.
    """
    columns = _columns(Notification)
    assert "respond_contact_id" in columns, (
        "notifications.respond_contact_id is missing. Without it the spine cannot "
        "address a contact and AC-H2's 'exactly one spine' is unachievable."
    )
    column = columns["respond_contact_id"]
    assert column.nullable, "A staff notification has no contact."
    assert not isinstance(column.type, PG_UUID), (
        "notifications.respond_contact_id must NOT be uuid. respond_contacts.id is "
        "TEXT (S1 pinned it; AC-A2 and AC-F2b-1 hit the same trap), and Postgres "
        "refuses a uuid foreign key onto a text primary key."
    )
    assert isinstance(column.type, (Text, String)), (
        "notifications.respond_contact_id must be text/varchar to match "
        f"respond_contacts.id, got {column.type!r}."
    )
    targets = {fk.target_fullname for fk in column.foreign_keys}
    assert "respond_contacts.id" in targets, (
        "notifications.respond_contact_id must foreign-key respond_contacts.id. "
        "The documented failure mode of a keyless recipient column is exactly what "
        "F2c's docstring describes: an id that inserts cleanly and addresses "
        "nobody."
    )


def test_the_recipient_check_constraint_exists():
    """AC-H1. Neither recipient set is a row nothing can ever deliver."""
    assert RECIPIENT_CHECK in _constraint_names(Notification), (
        f"CHECK constraint {RECIPIENT_CHECK} is missing. Both columns nullable and "
        "no check means a notification addressed to nobody inserts silently and "
        "sits unread forever."
    )


def test_a_notification_addressed_to_both_is_refused_by_the_database(db):
    """A row naming a user AND a contact is two recipients in one delivery fan-out.

    The AC does not say this, and it is asserted rather than left open because the
    alternative is a delivery loop that has to pick one and will pick differently
    in the worker than in the outbox renderer.
    """
    user = _user(db)
    contact = _contact(db)
    db.add(
        Notification(
            id=str(uuid.uuid4()),
            user_id=user.id,
            respond_contact_id=contact.id,
            type="after_sales.case",
            title=f"{TEST_PREFIX} two recipients",
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_the_whole_table_unique_constraint_is_gone():
    """AC-H1. It is not merely redundant once user_id is nullable - it is broken.

    Postgres treats NULLs as distinct, so the constraint stops deduplicating every
    contact notification the instant the column becomes nullable, without erroring
    and without any other signal.
    """
    names = _constraint_names(Notification) | _index_names(Notification)
    assert OLD_UNIQUE not in names, (
        f"{OLD_UNIQUE} still spans the whole table. With a nullable user_id it "
        "silently stops deduplicating contact notifications: the failure is a "
        "customer receiving the same WhatsApp twice, never an exception."
    )


def test_both_partial_dedupe_indexes_exist():
    """AC-H1. One per recipient kind, or one kind does not dedupe at all."""
    names = _index_names(Notification)
    for expected in (USER_DEDUP_INDEX, CONTACT_DEDUP_INDEX):
        assert expected in names, (
            f"Partial unique index {expected} is missing (present: {sorted(names)}). "
            "Two indexes, because one whole-table index cannot dedupe a column that "
            "is NULL for half the rows."
        )


def test_the_user_partial_index_is_declared_partial():
    """A non-partial index over a nullable column dedupes nothing on the NULL side."""
    index = next(
        (ix for ix in Notification.__table__.indexes if ix.name == USER_DEDUP_INDEX),
        None,
    )
    assert index is not None, f"{USER_DEDUP_INDEX} is missing."
    assert index.unique, f"{USER_DEDUP_INDEX} must be unique."
    where = index.dialect_options["postgresql"].get("where")
    assert where is not None, (
        f"{USER_DEDUP_INDEX} must carry postgresql_where='user_id IS NOT NULL'. "
        "Without the predicate it covers contact rows too, where every value is "
        "NULL and therefore distinct from every other."
    )


def test_the_contact_partial_index_is_declared_partial():
    index = next(
        (ix for ix in Notification.__table__.indexes if ix.name == CONTACT_DEDUP_INDEX),
        None,
    )
    assert index is not None, f"{CONTACT_DEDUP_INDEX} is missing."
    assert index.unique, f"{CONTACT_DEDUP_INDEX} must be unique."
    where = index.dialect_options["postgresql"].get("where")
    assert where is not None, (
        f"{CONTACT_DEDUP_INDEX} must carry "
        "postgresql_where='respond_contact_id IS NOT NULL'."
    )


def test_duplicate_contact_notifications_are_refused(db):
    """AC-H1, the half that silently stops working. This is the point of the slice.

    Two identical contact notifications must collide. If they do not, a retried
    send delivers the same WhatsApp message to a customer twice and nothing
    anywhere reports a fault.
    """
    contact = _contact(db)
    entity = str(uuid.uuid4())
    for _ in range(2):
        db.add(
            Notification(
                id=str(uuid.uuid4()),
                user_id=None,
                respond_contact_id=contact.id,
                type="after_sales.case",
                title=f"{TEST_PREFIX} visit confirmed",
                source_entity_type="complaint",
                dedup_key=entity,
                event_type="visit_confirmed",
            )
        )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_two_contacts_on_the_same_event_do_not_collide(db):
    """The Submitter and the Consumer are told about the same case (AC-H4).

    A dedupe index that keyed on the event alone would deliver to whichever of them
    the code reached first and drop the other.
    """
    entity = str(uuid.uuid4())
    for _ in range(2):
        contact = _contact(db)
        db.add(
            Notification(
                id=str(uuid.uuid4()),
                user_id=None,
                respond_contact_id=contact.id,
                type="after_sales.case",
                title=f"{TEST_PREFIX} visit confirmed",
                source_entity_type="complaint",
                dedup_key=entity,
                event_type="visit_confirmed",
            )
        )
    db.flush()
    rows = (
        db.query(Notification)
        .filter(Notification.dedup_key == entity)
        .all()
    )
    assert len(rows) == 2, (
        "Two different contacts on one event are two notifications. The dedupe "
        "scope is the recipient plus the event, never the event alone."
    )


def test_the_schema_change_is_in_a_migration_not_only_on_the_model():
    """The ADR-0012 failure, pinned.

    ``blank_session`` builds from ``Base.metadata``, so a model-only change passes
    every other test here and is absent in production.
    """
    versions = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"
    sources = [p.read_text(encoding="utf-8", errors="ignore") for p in versions.glob("*.py")]
    blob = "\n".join(sources)

    missing = [
        needle
        for needle in (
            "respond_contact_id",
            RECIPIENT_CHECK,
            USER_DEDUP_INDEX,
            CONTACT_DEDUP_INDEX,
            OLD_UNIQUE,
            FALLBACK_COLUMN,
            UNRESOLVED_FLAG,
        )
        if needle not in blob
    ]
    assert not missing, (
        "No alembic revision mentions " + ", ".join(missing) + ". A column, index "
        "or constraint that exists only on the model is green in every test here "
        "and absent in production - the exact failure ADR-0012 records. "
        f"{OLD_UNIQUE} must appear because the migration has to DROP it."
    )


# =============================================================================
# AC-H2, AC-H3 - one spine, two kinds of recipient
# =============================================================================


def _create(db, **kwargs):
    from app.services.notification_service import NotificationService

    return NotificationService(db).create_with_channel_preferences(**kwargs)


def _base_payload(**overrides) -> dict:
    payload = {
        "type": "after_sales.case",
        "title": f"{TEST_PREFIX} Visit confirmed",
        "body": "Your technician arrives Tuesday.",
        "source_entity_type": "complaint",
        "source_entity_id": str(uuid.uuid4()),
        "event_type": "visit_confirmed",
    }
    payload.update(overrides)
    return payload


def test_the_spine_accepts_a_contact_recipient(db):
    """AC-H2. One function records both kinds, or there are two spines."""
    contact = _contact(db)
    notification = _create(db, respond_contact_id=contact.id, **_base_payload())
    assert notification is not None
    assert notification.respond_contact_id == contact.id
    assert notification.user_id is None, (
        "A contact notification must leave user_id NULL. Writing the contact id "
        "into user_id is the bug F2c's docstring documents: it type-checks at "
        "every layer and addresses a principal who can never log in."
    )


def test_user_id_is_optional_in_the_signature():
    """AC-H2. A positional-only required user_id makes the contact call impossible."""
    from app.services.notification_service import NotificationService

    signature = inspect.signature(NotificationService.create_with_channel_preferences)
    assert "respond_contact_id" in signature.parameters, (
        "create_with_channel_preferences must take respond_contact_id. AC-H2 asks "
        "for one spine; a second create_for_contact() forks the dedupe rules."
    )
    user_param = signature.parameters["user_id"]
    assert user_param.default is not inspect.Parameter.empty, (
        "user_id must have a default now that it is optional, or every contact "
        "call has to pass user_id=None positionally."
    )


def test_the_spine_refuses_two_recipients(db):
    """Both set is a programming error, and the row would fan out to two people."""
    user = _user(db)
    contact = _contact(db)
    with pytest.raises(ValueError):
        _create(db, user_id=user.id, respond_contact_id=contact.id, **_base_payload())


def test_the_spine_refuses_no_recipient(db):
    with pytest.raises(ValueError):
        _create(db, **_base_payload())


def test_a_contact_gets_whatsapp_and_the_portal_and_nothing_else(db):
    """AC-H3. WhatsApp plus the portal, always. No email, no web push."""
    contact = _contact(db)
    notification = _create(db, respond_contact_id=contact.id, **_base_payload())
    channels = {
        row.channel
        for row in db.query(NotificationDelivery)
        .filter(NotificationDelivery.notification_id == notification.id)
        .all()
    }
    assert channels == CONTACT_CHANNELS, (
        f"A contact recipient must get exactly {sorted(CONTACT_CHANNELS)}, got "
        f"{sorted(channels)}. in_app IS the portal record the contact reads; email "
        "and web push address a staff surface a contact cannot reach."
    )


def test_a_contact_ignores_the_staff_preference_toggles(db):
    """AC-H3. Toggles stay staff-only.

    ``create_with_channel_preferences`` gates WhatsApp on
    ``getattr(user, whatsapp_pref_attr)`` and email on ``email_pref_attr``. Both
    read a ``users`` row. For a contact there is no row, so today's code resolves
    the user to None and turns WhatsApp OFF - the contact silently receives
    nothing. The attrs must be ignored outright for a contact.
    """
    contact = _contact(db)
    notification = _create(
        db,
        respond_contact_id=contact.id,
        send_whatsapp=True,
        whatsapp_pref_attr="notify_whatsapp_on_assignment",
        email_pref_attr="notify_email_on_assignment",
        **_base_payload(),
    )
    channels = {
        row.channel
        for row in db.query(NotificationDelivery)
        .filter(NotificationDelivery.notification_id == notification.id)
        .all()
    }
    assert "whatsapp" in channels, (
        "A contact's WhatsApp delivery must not be gated on a users-table "
        "preference lookup. The recipient has no users row, so the lookup resolves "
        "to None and the channel is dropped without a word."
    )


def test_a_contact_without_a_respond_id_still_gets_the_portal_record(db):
    """No address is not no notification.

    A contact synced without a ``respond_io_id`` cannot be messaged, but the portal
    record is the thing that lets them see the update when they next open the link.
    """
    contact = _contact(db, respond_io_id=None)
    notification = _create(db, respond_contact_id=contact.id, **_base_payload())
    channels = {
        row.channel
        for row in db.query(NotificationDelivery)
        .filter(NotificationDelivery.notification_id == notification.id)
        .all()
    }
    assert "in_app" in channels
    assert "whatsapp" not in channels, (
        "There is no address, so a pending whatsapp delivery would sit failed "
        "forever and pollute the outbox with a send that was never possible."
    )


def test_the_contact_spine_is_idempotent_on_the_dedup_scope(db):
    """AC-H1 as service behaviour, not merely as an index.

    The index is the backstop; the service must return the existing row rather
    than let the caller take an IntegrityError on a post-commit side effect.
    """
    contact = _contact(db)
    payload = _base_payload()
    first = _create(db, respond_contact_id=contact.id, **payload)
    second = _create(db, respond_contact_id=contact.id, **payload)
    assert first.id == second.id, (
        "A repeated contact notification must resolve to the existing row. Today's "
        "idempotency query filters on Notification.user_id == user_id, which for a "
        "contact is 'user_id IS NULL' at best and matches nothing at worst."
    )


def test_the_worker_does_not_drop_a_contacts_deliveries(db, monkeypatch):
    """AC-H2. ``send_notification_deliveries`` early-returns when no user resolves.

    ``user = db.query(User)...; if not user: return`` is correct today because
    every notification has a user. With a nullable column it silently discards
    every contact delivery - the notification row exists, the outbox is empty, and
    nothing logs an error above WARNING.
    """
    from app.tasks import notification_tasks

    contact = _contact(db)
    notification = _create(db, respond_contact_id=contact.id, **_base_payload())

    sent = _Sent()
    monkeypatch.setattr(
        "app.services.respond_messaging_service.send_text_or_template", sent
    )
    monkeypatch.setattr(notification_tasks, "SessionLocal", lambda: db)

    notification_tasks.send_notification_deliveries(str(notification.id))

    assert sent.calls, (
        "No send was attempted for a contact notification. The worker resolves the "
        "recipient through the users table and returns early when it finds "
        "nothing, so every contact delivery is discarded without an error."
    )


# =============================================================================
# AC-H7, AC-H8, AC-H11, AC-H12, AC-H13, AC-H14 - what a send leaves behind
# =============================================================================


def test_a_successful_contact_send_writes_an_outbox_row(db, monkeypatch):
    """AC-H7. Log on success as well as failure."""
    from app.tasks import notification_tasks

    contact = _contact(db)
    complaint = _complaint(db, contact=contact)
    notification = _create(
        db,
        respond_contact_id=contact.id,
        **_base_payload(source_entity_id=complaint.id),
    )
    monkeypatch.setattr(
        "app.services.respond_messaging_service.send_text_or_template", _Sent()
    )
    monkeypatch.setattr(notification_tasks, "SessionLocal", lambda: db)
    notification_tasks.send_notification_deliveries(str(notification.id))

    rows = (
        db.query(IntegrationLog)
        .filter(IntegrationLog.correlation_id == str(notification.id))
        .all()
    )
    assert len(rows) == 1, "One send, one outbox row, on the success path too."
    assert rows[0].status == "success"


def test_a_failed_contact_send_still_writes_an_outbox_row(db, monkeypatch):
    """AC-H7. Local development runs deliberately-wrong credentials.

    A 401 that logs nothing makes the outbox look healthy precisely when nothing
    is being delivered.
    """
    from app.tasks import notification_tasks

    contact = _contact(db)
    complaint = _complaint(db, contact=contact)
    notification = _create(
        db,
        respond_contact_id=contact.id,
        **_base_payload(source_entity_id=complaint.id),
    )
    monkeypatch.setattr(
        "app.services.respond_messaging_service.send_text_or_template",
        _Sent(raises=_closed_window_error()),
    )
    monkeypatch.setattr(notification_tasks, "SessionLocal", lambda: db)
    notification_tasks.send_notification_deliveries(str(notification.id))

    row = (
        db.query(IntegrationLog)
        .filter(IntegrationLog.correlation_id == str(notification.id))
        .first()
    )
    assert row is not None, "A failed send must appear in the outbox."
    assert row.status == "failed"
    assert row.status_code == 401, (
        "Respond.io's own status belongs on the row. A bare '401 Unauthorized' "
        "string cannot be told apart from a WAF block at the screen."
    )


def test_the_outbox_row_points_at_the_notification_and_the_case(db, monkeypatch):
    """AC-H8 and AC-H11 together.

    ``correlation_id`` = the notification id, ``business_table`` / ``business_id``
    = the Complaint. ``business_id`` is a uuid COLUMN, so it is one row's primary
    key and never a composite string - the recorded lesson from the daily-summary
    ``<user>:<date>:manual:<ts>`` key.
    """
    from app.tasks import notification_tasks

    contact = _contact(db)
    complaint = _complaint(db, contact=contact)
    notification = _create(
        db,
        respond_contact_id=contact.id,
        **_base_payload(source_entity_id=complaint.id),
    )
    monkeypatch.setattr(
        "app.services.respond_messaging_service.send_text_or_template", _Sent()
    )
    monkeypatch.setattr(notification_tasks, "SessionLocal", lambda: db)
    notification_tasks.send_notification_deliveries(str(notification.id))

    row = (
        db.query(IntegrationLog)
        .filter(IntegrationLog.correlation_id == str(notification.id))
        .first()
    )
    assert row is not None
    assert row.business_table == Complaint.__tablename__, (
        "The outbox renders event-first, so the row must name the Complaint, not "
        "a generic 'respond_notification' bucket."
    )
    assert row.business_id == complaint.id
    uuid.UUID(str(row.business_id))  # a real uuid, never a composite key


def test_a_closed_window_failure_is_recorded_as_a_template_attempt(db, monkeypatch):
    """AC-H14. Stamp what was ACTUALLY attempted.

    The window-aware send puts the real payload on the exception. Logging the
    default text payload instead makes a template failure read as a text failure,
    and the operator debugs the wrong thing.
    """
    from app.tasks import notification_tasks

    contact = _contact(db)
    complaint = _complaint(db, contact=contact)
    notification = _create(
        db,
        respond_contact_id=contact.id,
        **_base_payload(source_entity_id=complaint.id),
    )
    monkeypatch.setattr(
        "app.services.respond_messaging_service.send_text_or_template",
        _Sent(raises=_closed_window_error()),
    )
    monkeypatch.setattr(notification_tasks, "SessionLocal", lambda: db)
    notification_tasks.send_notification_deliveries(str(notification.id))

    row = (
        db.query(IntegrationLog)
        .filter(IntegrationLog.correlation_id == str(notification.id))
        .first()
    )
    assert row is not None
    assert "whatsapp_template" in str(row.request_payload or ""), (
        "The logged payload must be the template that was attempted, taken from "
        "exc.request_payload, not the default text payload built before the send."
    )


def test_a_contact_send_failure_never_raises(db, monkeypatch):
    """AC-H12. Every notification here is a post-commit side effect.

    The case has already moved. A raise hands the caller a 500 for an operation
    that succeeded, and the retry takes an idempotent path that never backfills
    the missed message.
    """
    from app.tasks import notification_tasks

    contact = _contact(db)
    notification = _create(db, respond_contact_id=contact.id, **_base_payload())
    monkeypatch.setattr(
        "app.services.respond_messaging_service.send_text_or_template",
        _Sent(raises=RuntimeError("respond.io is down")),
    )
    monkeypatch.setattr(notification_tasks, "SessionLocal", lambda: db)
    notification_tasks.send_notification_deliveries(str(notification.id))  # must not raise


# =============================================================================
# AC-H8a, AC-H9, AC-H10 - the outbox is a LEFT JOIN
# =============================================================================


def test_the_outbox_service_exists():
    _fn(_outbox(), "list_outbox", "(db, *, page, limit, ...)")


def test_a_send_with_no_notification_still_appears(db):
    """AC-H8a and AC-H10. The pinned one, because it is easy to regress.

    AI replies, n8n-initiated sends and every outbox row F2c wrote before S4 carry
    no notification. An inner join drops them, and the drop is invisible: the rows
    are simply not there.
    """
    complaint = _complaint(db)
    orphan = _log(db, business_id=complaint.id, correlation_id=None)
    db.commit()

    result = _fn(_outbox(), "list_outbox", "(db, ...)")(db, business_id=complaint.id)
    ids = {str(row["id"]) for row in result["data"]}
    assert str(orphan.id) in ids, (
        "An integration_log with correlation_id NULL is missing from the outbox. "
        "The query is an INNER JOIN onto notifications, which loses exactly the "
        "AI and n8n traffic the outbox exists to make visible (AC-H8a)."
    )


def test_the_outbox_renders_event_context_when_a_notification_exists(db):
    """AC-H9. "Complaint CMP... - Visit confirmed - to Mr Vinod - template - FAILED 401"."""
    contact = _contact(db)
    complaint = _complaint(db, contact=contact)
    notification = _create(
        db,
        respond_contact_id=contact.id,
        **_base_payload(source_entity_id=complaint.id),
    )
    _log(
        db,
        business_id=complaint.id,
        correlation_id=str(notification.id),
        status="failed",
        status_code=401,
        request_payload='{"message": {"type": "whatsapp_template"}}',
    )
    db.commit()

    result = _fn(_outbox(), "list_outbox", "(db, ...)")(db, business_id=complaint.id)
    row = next(r for r in result["data"] if str(r.get("notification_id") or "") == str(notification.id))

    assert row["case_number"] == complaint.complaint_number, (
        "The screen leads with the case, so the query resolves the number rather "
        "than making the frontend fetch each complaint by id."
    )
    assert row["event_type"] == "visit_confirmed"
    assert row["recipient_label"], (
        "The row must name who it went to. A uuid is not a recipient label - the "
        "cursor rule forbids uuids in the UI, so the resolution happens here."
    )
    assert row["sent_as"] == "template", (
        "sent_as is derived from the stamped request payload, so a closed-window "
        "failure reads as a template attempt (AC-H14) with no extra column."
    )
    assert row["status"] == "failed"
    assert row["status_code"] == 401


def test_the_outbox_row_for_an_orphan_send_has_no_event_but_still_renders(db):
    """AC-H10. Missing event context is empty, never a crash and never a filter."""
    complaint = _complaint(db)
    _log(db, business_id=complaint.id, correlation_id=None)
    db.commit()

    result = _fn(_outbox(), "list_outbox", "(db, ...)")(db, business_id=complaint.id)
    row = result["data"][0]
    assert row.get("notification_id") in (None, ""), (
        "An orphan send has no notification. It must render with an empty event, "
        "not be excluded and not raise."
    )
    assert row["case_number"] == complaint.complaint_number


def test_the_outbox_route_requires_authentication():
    """Auth denial. The outbox carries customer phone numbers and message bodies."""
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        response = client.get(OUTBOX_ROUTE)
    assert response.status_code in (401, 403), (
        f"{OUTBOX_ROUTE} answered {response.status_code} unauthenticated. The "
        "outbox exposes contact identities and message payloads."
    )


# =============================================================================
# AC-M33 / AC-M33a - nobody assignable is a routing outcome, not an exception
# =============================================================================


def test_the_fallback_is_configured_on_the_agent():
    """AC-M33a. Beside the resolution it backs up, not on every stage config."""
    columns = _columns(AccessAgent)
    assert FALLBACK_COLUMN in columns, (
        f"access_agents.{FALLBACK_COLUMN} is missing. AC-M33a puts the backstop at "
        "agent level because resolve_team_with_tier_fallback(agent, ...) is already "
        "where team resolution happens."
    )
    column = columns[FALLBACK_COLUMN]
    assert column.nullable, (
        "Nullable is what makes AC-M33b true: an agent with no fallback keeps "
        "today's raise, so the four live flows are unchanged until somebody "
        "configures one."
    )
    targets = {fk.target_fullname for fk in column.foreign_keys}
    assert "users.id" in targets, (
        f"access_agents.{FALLBACK_COLUMN} must foreign-key users.id, or the "
        "backstop can name a user who does not exist."
    )


def test_the_tracker_carries_the_unresolved_flag():
    """AC-M33. Flagged, never silently unassigned. S4a renders it."""
    columns = _columns(ConversationSLATracking)
    assert UNRESOLVED_FLAG in columns, (
        f"conversation_sla_tracking.{UNRESOLVED_FLAG} is missing. The flag lives "
        "on the tracker because the pending-task row S4a renders IS a tracker; a "
        "case-level column paints one stage's routing failure onto every stage."
    )
    column = columns[UNRESOLVED_FLAG]
    assert not column.nullable, "Three-valued 'maybe unresolved' has no meaning."
    assert column.server_default is not None, (
        "A server_default of false is what keeps every existing tracker row "
        "readable after the migration."
    )


def test_no_team_at_or_above_the_start_tier_routes_to_the_fallback(db):
    """AC-M33. The first raise site: resolve_team_with_tier_fallback found nothing.

    It already walks upward through tiers 1..3, so reaching here means every tier
    failed. That is a routing outcome, and the case must still exist.
    """
    lead = _user(db, "lead")
    agent = _agent(db, fallback=lead)
    policy = _policy(db)
    config = _config(db, agent, policy)
    complaint = _complaint(db)

    tracker = _orchestrator(db)._start_for_config(config, complaint.id)

    assert tracker is not None, (
        "A complaint that cannot be assigned is still a complaint. Raising here "
        "makes the existence of the case depend on team configuration."
    )
    assert tracker.assigned_to_id == lead.id
    assert getattr(tracker, UNRESOLVED_FLAG) is True, (
        "Routing to the backstop is not normal assignment. Without the flag the "
        "case looks correctly assigned and nobody ever fixes the team."
    )


def test_a_resolved_team_with_no_members_routes_to_the_fallback(db):
    """AC-M33, the SECOND raise site.

    ``_start_for_config`` raises twice: once when no team exists, and again when
    the team it found has no members. A team row with nobody in it is the more
    likely misconfiguration of the two, and wiring the fallback into only the
    first leaves it crashing.
    """
    lead = _user(db, "lead")
    agent = _agent(db, fallback=lead)
    policy = _policy(db)
    config = _config(db, agent, policy)
    _team(db, agent, config, policy, tier=1, members=[])
    complaint = _complaint(db)

    tracker = _orchestrator(db)._start_for_config(config, complaint.id)

    assert tracker is not None, (
        "An empty tier-1 team must reach the same fallback. AC-M33 says 'no "
        "assignee resolves', which is both raise sites, not just the first."
    )
    assert tracker.assigned_to_id == lead.id
    assert getattr(tracker, UNRESOLVED_FLAG) is True


def test_a_normal_assignment_leaves_the_flag_false(db):
    """The flag must mean something. Setting it always makes S4a's label noise."""
    member = _user(db, "member")
    agent = _agent(db, fallback=_user(db, "lead"))
    policy = _policy(db)
    config = _config(db, agent, policy)
    _team(db, agent, config, policy, tier=1, members=[member])
    complaint = _complaint(db)

    tracker = _orchestrator(db)._start_for_config(config, complaint.id)

    assert tracker.assigned_to_id == member.id
    assert getattr(tracker, UNRESOLVED_FLAG) is False


def test_an_unresolvable_fallback_raises_the_original_error(db):
    """The backstop decays. A configured user who was deleted is the normal path.

    ``resolve_team_with_tier_fallback`` already walked every tier, so if the
    fallback is also unresolvable there is genuinely nobody. The pinned behaviour
    is the ORIGINAL message, which names the real misconfiguration, rather than an
    AttributeError from a None one line further down.
    """
    from app.services.error_handler import AppException

    assert FALLBACK_COLUMN in _columns(AccessAgent), (
        f"access_agents.{FALLBACK_COLUMN} does not exist yet, so this test would "
        "pass vacuously - the raise below would be the ordinary unconfigured one."
    )
    agent = _agent(db)
    setattr(agent, FALLBACK_COLUMN, f"{TEST_PREFIX}-does-not-exist".lower())
    db.flush()
    policy = _policy(db)
    config = _config(db, agent, policy)
    complaint = _complaint(db)

    with pytest.raises(AppException) as caught:
        _orchestrator(db)._start_for_config(config, complaint.id)
    detail = caught.value.detail if isinstance(caught.value.detail, dict) else {}
    assert "no team at tier" in str(detail.get("message")).lower(), (
        "A dangling fallback must fall through to the original error. Anything "
        "else moves the crash one line down and hides which thing is misconfigured."
    )


def test_an_inactive_fallback_user_is_not_assignable(db):
    """A deactivated backstop is not a recipient. Assigning to one is silent loss."""
    from app.services.error_handler import AppException

    assert FALLBACK_COLUMN in _columns(AccessAgent), (
        f"access_agents.{FALLBACK_COLUMN} does not exist yet, so _agent() would "
        "silently set a plain Python attribute and this test would pass vacuously."
    )
    lead = _user(db, "lead", status="INACTIVE")
    agent = _agent(db, fallback=lead)
    policy = _policy(db)
    config = _config(db, agent, policy)
    complaint = _complaint(db)

    with pytest.raises(AppException):
        _orchestrator(db)._start_for_config(config, complaint.id)


def test_the_fallback_path_is_uniform_across_form_types(db):
    """AC-M33a. No branching on form type. Purchase requests get it too.

    Branching is how this kind of guard rots: two behaviours inside one function
    and nobody remembers which type is which. Configure a fallback on the agent a
    purchase-request stage uses, and it must behave identically.
    """
    lead = _user(db, "lead")
    agent = _agent(db, fallback=lead)
    policy = _policy(db)
    config = _config(db, agent, policy, source_entity_type="purchase_request")

    tracker = _orchestrator(db)._start_for_config(config, str(uuid.uuid4()))

    assert tracker is not None
    assert tracker.assigned_to_id == lead.id
    assert getattr(tracker, UNRESOLVED_FLAG) is True, (
        "The mechanism ships uniformly (AC-M33a). What keeps the four live flows "
        "unchanged is that none of them has a fallback configured (AC-M33b), not a "
        "type check inside the function."
    )


# =============================================================================
# AC-M34, AC-M35, AC-M35a - calls are the third channel
# =============================================================================


def test_the_call_module_exposes_its_three_operations():
    module = _calls()
    _fn(module, "log_call", "(db, *, contact_id, direction, outcome, ...)")
    _fn(module, "attach_call", "(db, *, activity_id, complaint_id, actor_id)")
    _fn(module, "list_unattached_calls", "(db, *, contact_id)")


def test_the_call_vocabulary_is_declared_as_data():
    """AC-M36c. S5's automatic path lands on this same vocabulary.

    Declared as a constant rather than inferred from a validator branch, because
    the thing a later reader must not re-decide by accident is precisely the set.
    """
    module = _calls()
    assert frozenset(getattr(module, "CALL_OUTCOMES", ())) == CALL_OUTCOMES, (
        "answered / missed / no_answer, exactly. 'A call that ended is not a call "
        "that connected' is the entire requirement: the evidence Fanny's complaint "
        "needed was whether contact was actually made."
    )
    assert frozenset(getattr(module, "CALL_DIRECTIONS", ())) == CALL_DIRECTIONS


def test_a_logged_call_is_an_activity_with_a_call_kind(db):
    """AC-M34. No new table. It joins the feed that already carries notes."""
    contact = _contact(db)
    complaint = _complaint(db, contact=contact)
    actor = _user(db, "cs")

    event = _fn(_calls(), "log_call", "(...)")(
        db,
        contact_id=contact.id,
        direction="outbound",
        outcome="answered",
        duration_seconds=95,
        next_action="Technician visit Tuesday",
        actor_id=None,
    )

    row = db.query(ActivityEvent).filter(ActivityEvent.id == str(event.id)).first()
    assert row is not None
    assert row.kind == CALL_ACTIVITY_KIND, (
        "A call is neither 'system' (no software did it) nor 'user_update' (it is "
        "not a composer post and carries structured fields no composer produces)."
    )
    assert row.entity_type == Complaint.__audit_entity_type__
    assert row.entity_id == complaint.id
    payload = row.system_payload or {}
    assert payload.get("outcome") == "answered"
    assert payload.get("duration_seconds") == 95, (
        "Duration lives in system_payload for now. Whether reporting needs it as a "
        "column is an S9 question, not an S4 one."
    )
    assert payload.get("direction") == "outbound"
    assert payload.get("next_action") == "Technician visit Tuesday", (
        "AC-M34 says the activity carries outcome AND next action."
    )
    assert actor is not None  # the fixture is used by the actor-attribution test below


def test_an_unknown_outcome_is_refused(db):
    """A free-text outcome makes AC-M36c's evidence unqueryable.

    ``log_call`` is resolved BEFORE the raises block on purpose: resolving it
    inside would let the "module does not exist" AssertionError satisfy
    ``pytest.raises`` and the test would pass without an implementation.
    """
    log_call = _fn(_calls(), "log_call", "(...)")
    contact = _contact(db)
    _complaint(db, contact=contact)
    with pytest.raises(Exception):
        log_call(
            db,
            contact_id=contact.id,
            direction="outbound",
            outcome="ended",
            duration_seconds=0,
        )


def test_an_unknown_direction_is_refused(db):
    log_call = _fn(_calls(), "log_call", "(...)")
    contact = _contact(db)
    _complaint(db, contact=contact)
    with pytest.raises(Exception):
        log_call(
            db,
            contact_id=contact.id,
            direction="sideways",
            outcome="answered",
            duration_seconds=10,
        )


def test_exactly_one_open_case_auto_attaches(db):
    """AC-M35. One open case is the only safe attribution."""
    contact = _contact(db)
    complaint = _complaint(db, status="submitted", contact=contact)

    event = _fn(_calls(), "log_call", "(...)")(
        db, contact_id=contact.id, direction="inbound", outcome="answered", duration_seconds=30
    )

    assert event.entity_type == Complaint.__audit_entity_type__
    assert event.entity_id == complaint.id


def test_two_open_cases_park_on_the_contact(db):
    """AC-M35 and AC-M35a. Never auto-attributed.

    A wrong attribution puts false evidence into the record CS relies on, so the
    call waits in the per-contact inbox for one click.
    """
    contact = _contact(db)
    _complaint(db, status="submitted", contact=contact)
    _complaint(db, status="approved", contact=contact)

    event = _fn(_calls(), "log_call", "(...)")(
        db, contact_id=contact.id, direction="inbound", outcome="missed", duration_seconds=0
    )

    assert event.entity_type == UNATTACHED_ENTITY_TYPE, (
        "activity_events.entity_type and entity_id are both NOT NULL, so an "
        "unattached call parks as entity_type='respond_contact' and is re-keyed on "
        "attachment (AC-M35a)."
    )
    assert event.entity_id == contact.id


def test_no_open_case_parks_on_the_contact(db):
    """A cold call to a customer with nothing open is still evidence worth keeping."""
    contact = _contact(db)
    event = _fn(_calls(), "log_call", "(...)")(
        db, contact_id=contact.id, direction="outbound", outcome="no_answer", duration_seconds=0
    )
    assert event.entity_type == UNATTACHED_ENTITY_TYPE
    assert event.entity_id == contact.id


def test_open_is_the_status_engines_terminality(db):
    """AC-M35's "open" defined against ``is_terminal``, not ``LINKABLE_STATUSES``.

    ``LINKABLE_STATUSES`` = {processed_by_cs, fulfilled} answers a different
    question (which complaints a delivery order may fulfil); reusing it would make
    a freshly submitted complaint invisible to call attribution, which is the one
    case that matters most.

    NOTE the consequence, which is a finding rather than a design: the complaint
    graph marks only ``closed`` and ``voided`` terminal, so ``rejected`` reads as
    open forever. A contact whose only case was rejected in 2024 auto-attaches
    today's call to it.
    """
    contact = _contact(db)
    _complaint(db, status="closed", contact=contact)
    _complaint(db, status="voided", contact=contact)
    live = _complaint(db, status="processed_by_cs", contact=contact)

    event = _fn(_calls(), "log_call", "(...)")(
        db, contact_id=contact.id, direction="inbound", outcome="answered", duration_seconds=12
    )

    assert event.entity_id == live.id, (
        "Terminal cases do not count toward 'exactly one open case'. Two closed "
        "complaints beside one live one is one open case, not three."
    )


def test_attaching_re_keys_the_same_activity_row(db):
    """AC-M35a. Re-keyed in place, not copied.

    A new row would leave the parked one behind and double-count the call in the
    feed, and it would break any audit reference to the original id.
    """
    contact = _contact(db)
    first = _complaint(db, status="submitted", contact=contact)
    _complaint(db, status="approved", contact=contact)
    actor = _user(db, "cs")

    event = _fn(_calls(), "log_call", "(...)")(
        db, contact_id=contact.id, direction="inbound", outcome="answered", duration_seconds=44
    )
    original_id = str(event.id)

    attached = _fn(_calls(), "attach_call", "(...)")(
        db, activity_id=original_id, complaint_id=first.id, actor_id=actor.id
    )

    assert str(attached.id) == original_id, "Re-key the row; never write a second one."
    assert attached.entity_type == Complaint.__audit_entity_type__
    assert attached.entity_id == first.id
    assert (
        db.query(ActivityEvent)
        .filter(
            ActivityEvent.entity_type == UNATTACHED_ENTITY_TYPE,
            ActivityEvent.entity_id == contact.id,
        )
        .count()
        == 0
    ), "The parked row must be gone, not duplicated."


def test_attaching_an_already_attached_call_is_refused(db):
    """Re-attribution is a rewrite of evidence. It needs its own deliberate action."""
    contact = _contact(db)
    first = _complaint(db, status="submitted", contact=contact)
    second = _complaint(db, status="approved", contact=contact)
    actor = _user(db, "cs")

    attach_call = _fn(_calls(), "attach_call", "(...)")
    event = _fn(_calls(), "log_call", "(...)")(
        db, contact_id=contact.id, direction="inbound", outcome="answered", duration_seconds=44
    )
    attach_call(db, activity_id=str(event.id), complaint_id=first.id, actor_id=actor.id)
    with pytest.raises(Exception):
        attach_call(
            db, activity_id=str(event.id), complaint_id=second.id, actor_id=actor.id
        )


def test_attaching_to_a_case_the_contact_does_not_own_is_refused(db):
    """One click must not be able to file a call against a stranger's case."""
    contact = _contact(db)
    _complaint(db, status="submitted", contact=contact)
    _complaint(db, status="approved", contact=contact)
    stranger_case = _complaint(db, status="submitted", contact=_contact(db))
    actor = _user(db, "cs")

    attach_call = _fn(_calls(), "attach_call", "(...)")
    event = _fn(_calls(), "log_call", "(...)")(
        db, contact_id=contact.id, direction="inbound", outcome="answered", duration_seconds=9
    )
    with pytest.raises(Exception):
        attach_call(
            db, activity_id=str(event.id), complaint_id=stranger_case.id, actor_id=actor.id
        )


def test_the_per_contact_inbox_lists_only_unattached_calls(db):
    """AC-M35. The inbox is what makes "never auto-attributed" workable."""
    contact = _contact(db)
    attached_case = _complaint(db, status="submitted", contact=contact)
    _complaint(db, status="approved", contact=contact)
    actor = _user(db, "cs")

    parked = _fn(_calls(), "log_call", "(...)")(
        db, contact_id=contact.id, direction="inbound", outcome="missed", duration_seconds=0
    )
    done = _fn(_calls(), "log_call", "(...)")(
        db, contact_id=contact.id, direction="inbound", outcome="answered", duration_seconds=61
    )
    _fn(_calls(), "attach_call", "(...)")(
        db, activity_id=str(done.id), complaint_id=attached_case.id, actor_id=actor.id
    )

    rows = _fn(_calls(), "list_unattached_calls", "(...)")(db, contact_id=contact.id)
    ids = {str(getattr(row, "id", row.get("id") if isinstance(row, dict) else row)) for row in rows}
    assert str(parked.id) in ids
    assert str(done.id) not in ids


def test_logging_a_call_records_who_logged_it(db):
    """Evidence without attribution is not evidence. ``actor_id`` is on the row."""
    contact = _contact(db)
    _complaint(db, status="submitted", contact=contact)
    actor = _user(db, "cs")

    event = _fn(_calls(), "log_call", "(...)")(
        db,
        contact_id=contact.id,
        direction="outbound",
        outcome="answered",
        duration_seconds=20,
        actor_id=actor.id,
    )
    assert str(event.actor_id) == str(actor.id)


def test_a_call_is_never_logged_against_an_unknown_contact(db):
    """entity_id is NOT NULL. An invented contact id parks a row nothing can reach."""
    log_call = _fn(_calls(), "log_call", "(...)")
    with pytest.raises(Exception):
        log_call(
            db,
            contact_id=f"{TEST_PREFIX}-nobody".lower(),
            direction="inbound",
            outcome="answered",
            duration_seconds=5,
        )


# =============================================================================
# F2c - which mechanism for "tell a contact" survives
# =============================================================================


def test_the_submission_contact_path_moves_onto_the_spine(db, monkeypatch):
    """AC-H2. Exactly one spine, so F2c's parallel path is retired.

    F2c deliberately did NOT write a notifications row: ``user_id`` was NOT NULL
    with no foreign key, so a contact id would have inserted cleanly and addressed
    a principal who can never log in. S4 removes that reason. Two mechanisms for
    "tell a contact" is the drift this build keeps finding, so the spine wins and
    F2c's sender becomes a caller of it.

    The rows F2c already wrote keep ``correlation_id`` NULL forever, which is
    exactly why AC-H8a's LEFT JOIN is not optional.
    """
    from types import SimpleNamespace

    from app.services import workflow_submission_notify

    contact = _contact(db)
    # Duck-typed on purpose: notify_submission_contact reads its argument entirely
    # through getattr, and a real WorkflowSubmission needs a published version and a
    # status row that have nothing to do with what is asserted here.
    submission = SimpleNamespace(
        id=str(uuid.uuid4()),
        definition_id=str(uuid.uuid4()),
        respondent_contact_id=contact.id,
        status_label="Approved",
    )

    monkeypatch.setattr(
        "app.services.respond_messaging_service.send_text_or_template", _Sent()
    )
    log = workflow_submission_notify.notify_submission_contact(
        db, submission, title=f"{TEST_PREFIX} Approved", body="Your claim is approved.",
        event_type="approved",
    )

    assert log is not None, "The send was attempted, so there is an outbox row."
    assert log.correlation_id, (
        "The submission's contact message left no notification behind. Once "
        "notifications.user_id is nullable the reason for F2c's second mechanism "
        "is gone, and AC-H2 asks for exactly one spine. correlation_id is what "
        "ties the outbox row to it (AC-H8)."
    )
    notification = (
        db.query(Notification)
        .filter(Notification.id == str(log.correlation_id))
        .first()
    )
    assert notification is not None
    assert notification.respond_contact_id == contact.id
    assert notification.user_id is None
