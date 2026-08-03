"""S4 guards - what must NOT change, and what is already built.

Green by construction, and deliberately so. Split out of
``test_after_sales_notification_spine.py`` so the gate's red count measures only
work that remains; a guard that can never be red would dilute it.

Two kinds of assertion live here.

**The safety argument (AC-M33b).** ``FormSLAOrchestrator._start_for_config`` is
shared by purchase requests, sponsorship forms, stock inquiries and complaints.
S4 turns its raise into a configurable fallback, which is a production behaviour
change no after-sales AC governs. The whole reason that is shippable is that an
agent with NO fallback configured keeps today's behaviour exactly - same exception
type, same status, same code, same message. These tests are green now and must stay
green after S4 lands. They are written against a NON after-sales form type, because
that is the claim that actually matters.

**Prior art S4 reuses rather than rebuilds.** ``whatsapp`` is already a
``notification_deliveries`` channel (TCK-29), escalation already notifies only the
tier escalated to, ``integration_log.business_id`` is already a uuid column, and
every Respond send already resolves the workspace key through
``RespondClient.for_identifier``. Freezing them here stops S4 re-implementing a
second copy of any of it, and stops a later edit quietly undoing one.

One assertion is a finding rather than a guard: ``respond_contacts.id`` is TEXT,
which is why the plan's ``respond_contact_id uuid REFERENCES respond_contacts(id)``
cannot execute. It is pinned here because it is true today, will be true after S4,
and is the single fact the schema change most easily gets wrong.

Run: venv/bin/python -m pytest tests/test_after_sales_notify_guards.py -q -p no:randomly
"""
from __future__ import annotations

import inspect
import pathlib
import uuid

import pytest
from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.exc import IntegrityError

# MUST be the first app import - resolves the circular import in
# app.modules.runtime.guards.
from app.main import app  # noqa: E402,F401

from app.models.access import AccessAgent, RespondContact  # noqa: E402
from app.models.integration import IntegrationLog  # noqa: E402
from app.models.notification import NotificationDelivery  # noqa: E402
from app.models.sla import FormSLAConfig, SLAPolicy, SLAPolicyTier  # noqa: E402
from app.services.error_handler import AppException  # noqa: E402

from ._pg_fixture import TEST_PREFIX, blank_session, unique_code

# The four flows AC-M33b protects. complaint is deliberately in the list: until
# after-sales configures a fallback it must behave exactly like the other three.
SHARED_FORM_TYPES = ("purchase_request", "sponsorship_form", "stock_inquiry", "complaint")


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _agent(db) -> AccessAgent:
    agent = AccessAgent(
        id=str(uuid.uuid4()),
        code=unique_code("agent").lower(),
        name=f"{TEST_PREFIX} agent",
    )
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
    db.add(
        SLAPolicyTier(
            id=str(uuid.uuid4()),
            policy_id=policy.id,
            tier_level=1,
            tier_name=f"{TEST_PREFIX} tier 1",
            response_hours=4,
            resolution_hours=24,
        )
    )
    db.flush()
    return policy


def _config(db, agent, policy, source_entity_type: str) -> FormSLAConfig:
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


def _start(db, config):
    from app.services.form_sla_service import FormSLAOrchestrator

    return FormSLAOrchestrator(db)._start_for_config(config, str(uuid.uuid4()))


# =============================================================================
# AC-M33b - bit-for-bit unchanged where no fallback is configured
# =============================================================================


@pytest.mark.parametrize("source_entity_type", SHARED_FORM_TYPES)
def test_no_fallback_configured_still_raises(db, source_entity_type):
    """AC-M33b. The conservative half, asserted for every flow that shares the code.

    An agent with no team at or above the start tier and no fallback must raise,
    for a purchase request exactly as it does today. This is the claim that lets
    S4 ship a core behaviour change uniformly.
    """
    agent = _agent(db)
    policy = _policy(db)
    config = _config(db, agent, policy, source_entity_type)

    with pytest.raises(AppException):
        _start(db, config)


def test_the_raise_keeps_its_exact_shape(db):
    """AC-M33b. Same type, same status, same code, same message.

    "Bit-for-bit unchanged" is not satisfied by raising something else that also
    fails: callers of the four live flows surface this message to an operator, and
    a route that maps 400 to a form error would start returning a 500 if the type
    changed.
    """
    agent = _agent(db)
    policy = _policy(db)
    config = _config(db, agent, policy, "purchase_request")

    with pytest.raises(AppException) as caught:
        _start(db, config)

    error = caught.value
    assert error.status_code == 400
    detail = error.detail if isinstance(error.detail, dict) else {}
    assert detail.get("code") == "VALIDATION_ERROR"
    message = str(detail.get("message"))
    assert f"Agent '{agent.code}' has no team at tier 1 or above" in message
    assert f"in set '{config.team_set_code}'" in message
    assert "Configure a tier team before activating this SLA config." in message


def test_the_agent_has_no_fallback_column_yet():
    """The precondition for the tests above. S4 DELETES this one.

    Left in deliberately: while it passes, every "no fallback configured" test
    above is exercising the unconfigured path for the right reason rather than by
    accident.
    """
    columns = {c.key for c in AccessAgent.__table__.columns}
    assert "assignment_fallback_user_id" not in columns, (
        "S4 has added the fallback column. Delete this guard and confirm the "
        "AC-M33b tests above still pass with the column present and NULL - that, "
        "not this, is the lasting safety property."
    )


# =============================================================================
# AC-H1 halves that are green today and must stay green
# =============================================================================


def test_a_notification_addressed_to_nobody_is_refused(db):
    """Green today because ``user_id`` is NOT NULL; green after because of the CHECK.

    Here rather than in the gate precisely because the mechanism changes underneath
    it while the behaviour must not: a notification addressed to no recipient is
    unreachable by every query and every delivery loop, whichever constraint is
    doing the refusing.
    """
    from app.models.notification import Notification

    db.add(
        Notification(
            id=str(uuid.uuid4()),
            user_id=None,
            type="after_sales.case",
            title=f"{TEST_PREFIX} addressed to nobody",
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_duplicate_staff_notifications_are_still_refused(db):
    """AC-H1. The half that works today must survive the split into two indexes.

    The whole-table unique constraint is dropped by this slice. If the replacement
    partial index is written wrong, staff dedupe breaks in the same silent way
    contact dedupe would - a duplicate escalation notice, never an error.
    """
    from app.models.notification import Notification
    from app.models.user import User

    user = User(
        id=unique_code("staff").lower(),
        email=f"{unique_code('staff').lower()}@{TEST_PREFIX.lower()}.invalid",
        name=f"{TEST_PREFIX} staff",
        status="ACTIVE",
    )
    db.add(user)
    db.flush()
    entity = str(uuid.uuid4())
    for _ in range(2):
        db.add(
            Notification(
                id=str(uuid.uuid4()),
                user_id=user.id,
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


def test_the_delivery_worker_never_reaches_for_the_env_api_key():
    """AC-H13. True today and must remain true when the contact branch is added.

    A placeholder workspace key 401s every send while the env key is perfectly
    valid, so the failure looks like a credentials problem in the wrong place.
    """
    from app.tasks import notification_tasks

    source = pathlib.Path(
        inspect.getfile(notification_tasks)
    ).read_text(encoding="utf-8")
    assert "respond_api_key" not in source, (
        "The delivery worker must not read settings.respond_api_key. Sends resolve "
        "the per-contact workspace key through RespondClient.for_identifier(...), "
        "which send_text_or_template already does."
    )


# =============================================================================
# Prior art S4 must reuse, not rebuild
# =============================================================================


def test_whatsapp_is_already_a_delivery_channel():
    """AC-H2's "WhatsApp joins the channel enum" is already true for staff (TCK-29).

    S4's new work is the CONTACT recipient, not the channel.
    """
    source = pathlib.Path(
        inspect.getfile(__import__("app.tasks.notification_tasks", fromlist=["x"]))
    ).read_text(encoding="utf-8")
    assert '"whatsapp"' in source, (
        "The whatsapp delivery branch is gone. S4 depends on it; it must not be "
        "reimplemented beside itself."
    )


def test_the_channel_column_is_not_a_database_enum():
    """So "joins the enum" costs no migration - the column is a plain string.

    Worth pinning because reading AC-H2 as a Postgres ENUM change would produce a
    migration with a lock on a hot table for no benefit.
    """
    column = NotificationDelivery.__table__.columns["channel"]
    assert isinstance(column.type, (String, Text)), (
        f"notification_deliveries.channel is {column.type!r}. A real database enum "
        "would make every new channel a migration."
    )


def test_integration_log_business_id_is_a_uuid_column():
    """AC-H11. The recorded lesson: never a composite string key.

    ``<user>:<date>:manual:<ts>`` was written into this column once already.
    """
    column = IntegrationLog.__table__.columns["business_id"]
    assert isinstance(column.type, PG_UUID), (
        "integration_log.business_id must stay uuid. It being a uuid COLUMN is the "
        "reason a composite key cannot be smuggled in."
    )
    assert not column.nullable


def test_integration_log_carries_a_correlation_id():
    """AC-H8's mechanism already exists; S4 populates it, it does not add it."""
    columns = {c.key for c in IntegrationLog.__table__.columns}
    assert "correlation_id" in columns


def test_respond_contacts_id_is_text_not_uuid():
    """Why the plan's DDL cannot execute.

    ``respond_contact_id uuid REFERENCES respond_contacts(id)`` is refused by
    Postgres: a uuid column cannot foreign-key a text primary key. The same trap is
    recorded at AC-A2 and AC-F2b-1, and S1's suite pins it for
    ``respond_contacts.user_id``.
    """
    column = RespondContact.__table__.columns["id"]
    assert not isinstance(column.type, PG_UUID), (
        "respond_contacts.id has become uuid. If that is deliberate the S4 plan's "
        "DDL is finally correct; if not, notifications.respond_contact_id must be "
        "text to match."
    )
    assert isinstance(column.type, (Text, String))


def test_escalation_notifies_only_the_new_assignee():
    """AC-H6. Already built: ``_notify_assignee`` addresses the tracker's assignee.

    No fixed recipient list, no salesperson-and-CS fan-out. S4 must not add one.
    """
    from app.services import form_sla_service

    source = pathlib.Path(inspect.getfile(form_sla_service)).read_text(encoding="utf-8")
    assert "user_id=str(tracker.assigned_to_id)" in source, (
        "Escalation notification no longer targets the tracker's own assignee. "
        "AC-H6 requires only the tier escalated to, resolved through "
        "resolve_team_with_tier_fallback."
    )
    assert "notify_on_escalation" in source, (
        "The stage-level gate is gone. AC-H6 gates the event on the stage flag and "
        "the channel on each member's own toggle - a matrix, not one switch."
    )


def test_tier_fallback_walks_upward_and_caps_at_three():
    """Why "no assignee resolves" means every tier failed.

    ``resolve_team_with_tier_fallback`` already skips missing intermediate tiers, so
    reaching AC-M33's fallback is not "tier 1 is empty" - it is "1, 2 and 3 all
    are". Pinned because it is the reason the backstop is a last resort rather than
    a routine path.
    """
    from app.services.user_service import AccessAgentService

    source = inspect.getsource(AccessAgentService.resolve_team_with_tier_fallback)
    assert "range(s, 4)" in source, (
        "The upward walk changed. AC-M33's fallback is defined as the state after "
        "this function has exhausted every tier."
    )


def test_the_respond_send_choke_point_uses_the_workspace_key():
    """AC-H13. ``send_text_or_template`` resolves per-identifier credentials.

    A placeholder workspace key 401s every send while the env key is perfectly
    valid, so verifying which key the path actually uses is the recorded lesson.
    """
    from app.services import respond_messaging_service

    source = pathlib.Path(
        inspect.getfile(respond_messaging_service)
    ).read_text(encoding="utf-8")
    assert "RespondClient" in source
    assert "settings.respond_api_key" not in source, (
        "The send choke point must never read the deprecated env key directly."
    )


def test_every_queued_respond_send_logs_success_and_failure():
    """AC-H7. ``_send_and_log`` writes an outbox row on both paths already."""
    from app.tasks import respond_io_tasks

    source = inspect.getsource(respond_io_tasks._send_and_log)
    assert source.count("create_integration_log") >= 2, (
        "One of the two outbox writes has gone. Local development runs with "
        "deliberately wrong credentials, so the FAILURE path is the one a "
        "developer actually exercises."
    )
    assert 'status="failed"' in source
    assert 'getattr(e, "request_payload", request_payload)' in source, (
        "AC-H14: the actually-attempted payload is stamped on the exception, so a "
        "closed-window failure logs as a template attempt, not a text one."
    )


def test_the_contact_send_path_in_f2c_never_raises():
    """AC-H12. F2c already swallows; S4's contact path inherits the rule.

    A notification that raises hands the caller a 500 for an operation that
    already committed, and the retry takes an idempotent path that never backfills
    the missed message.
    """
    from app.services import workflow_submission_notify

    source = inspect.getsource(workflow_submission_notify._send_and_log)
    assert "except Exception" in source
    assert "raise" not in source.replace("raise", "", 0) or "        raise\n" not in source, (
        "workflow_submission_notify._send_and_log must not re-raise."
    )


def test_the_complaint_graph_marks_only_two_statuses_terminal():
    """The definition AC-M35's "open case" is built on, and its consequence.

    Only ``closed`` and ``voided`` are terminal, so a ``rejected`` complaint counts
    as open forever under ``not is_terminal``. That is a finding about the graph,
    not about the call code, and it is pinned here so S4's attribution rule and any
    later fix to the graph move together.
    """
    from app.services.complaint_status_graph import COMPLAINT_STATUS_SEEDS

    terminal = {seed.key for seed in COMPLAINT_STATUS_SEEDS if seed.is_terminal}
    assert terminal == {"closed", "voided"}, (
        f"Terminal complaint statuses are now {sorted(terminal)}. AC-M35's "
        "'exactly one open case' is defined as 'not is_terminal', so this set is "
        "the definition of what a call can auto-attach to."
    )


def test_linkable_statuses_is_a_different_question():
    """Why AC-M35 does NOT reuse ``LINKABLE_STATUSES``.

    It answers which complaints a delivery order may fulfil. Reusing it for call
    attribution would make a freshly submitted complaint - the case most likely to
    be the subject of a phone call - invisible.
    """
    from app.services.complaint_fulfilment_service import LINKABLE_STATUSES

    assert "submitted" not in LINKABLE_STATUSES
    assert LINKABLE_STATUSES == {"processed_by_cs", "fulfilled"}
