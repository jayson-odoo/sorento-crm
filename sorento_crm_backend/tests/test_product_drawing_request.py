"""QUOTE-DRAWING-ESCALATE Phase 2 red tests: the service and its hand-off notices.

Written BEFORE the implementation, from `PLAN-quote-drawing-escalate-29oct.md` (rules 1-11, the
Phase 2 contract and its test list) and the UAC (AC-1 to AC-13). Every test is red until
`app/services/product_drawing_request_service.py` exists and the form-SLA plumbing knows the
`product_drawing` type.

What is pinned here
-------------------
- `has_drawing`: a non-deleted file typed exactly "Technical Specifications", image OR PDF.
- `escalate`: one form-SLA task per PRODUCT from the configured step, requesters recorded as event
  log rows, joins instead of duplicating, locks the product row, never swallows a refusal.
- `escalation_states`: the cell's state for many products in O(1) queries.
- `respond` / `resolve`: the actor rule of the existing SLA routes, the events the step configures.
- `notify_drawing_linked` and the hand-off notices H1 to H4 (rule 10): in-app always, email and
  WhatsApp each gated by the recipient's own toggle and a linked WhatsApp contact. The assertions
  read `NotificationDelivery` rows by channel; nothing here ever sends (the enqueue and the
  WhatsApp sender are patched to fail loudly if reached).
- the quotation line read carries `technical_drawing.escalation` and the `pdf` state.

Postgres only, via ``blank_session``. Every row is seeded here (CI's database is empty) and every
name is a masked code.
"""
from __future__ import annotations

import inspect
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, text

from app.models.access import AccessAgent, AgentTeam, RespondContact, Team, TeamMember
from app.models.notification import Notification, NotificationDelivery
from app.models.sla import (
    ConversationSLAEventLog,
    ConversationSLATracking,
    FormSLAConfig,
    SLAPolicy,
    SLAPolicyTier,
)
from app.models.user import User
from app.services.error_handler import AppException

from ._pg_fixture import blank_session, unique_code
from .test_project_quotation_images import _priced_line, _product, _setup, _user
from .test_quotation_lines_grid import _drawing, _file, _photo, _scope

SOURCE = "product_drawing"
DRAWINGS = "Technical Specifications"
PHOTOS = "Product Photos"
FORM_SLA_NOTE_SOURCE = "form_sla_tracking"


def _uid() -> str:
    return str(uuid.uuid4())


def _svc():
    """Imported lazily so a missing module fails each test with ImportError, not collection."""
    from app.services import product_drawing_request_service as pdr

    return pdr


# ---------------------------------------------------------------------------------- fixtures


@pytest.fixture
def sent(monkeypatch):
    """Nothing leaves the process. Delivery rows are created by the notification service and
    drained by a worker; the enqueue and the Respond sender are the only exits, and a call to
    either is recorded (enqueue) or fails the test (a real WhatsApp send)."""
    import app.services.queue_service as queue_service
    import app.services.respond_messaging_service as respond_messaging

    enqueued: list = []
    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: enqueued.append((a, k)))

    def _no_real_send(*args, **kwargs):  # pragma: no cover - only reached by a defect
        raise AssertionError("a test reached a real WhatsApp send")

    monkeypatch.setattr(respond_messaging, "send_text_or_template", _no_real_send)
    return enqueued


@pytest.fixture
def db(sent):
    with blank_session() as session:
        yield session


@pytest.fixture
def env(db):
    """The quotation chain (project, owner, category, uom) every line test hangs off."""
    return _setup(db)


def seed_drawing_team(
    db,
    *,
    config: bool = True,
    active: bool = True,
    tiers: int = 1,
    email_on_assignment: bool = True,
    whatsapp_on_assignment: bool = False,
    link_whatsapp: bool = False,
    email_on_escalation: bool = True,
    whatsapp_on_escalation: bool = False,
    start_event: str = "escalate",
) -> dict:
    """An access agent, a team set of ``tiers`` tiers with one member each, an SLA policy with a
    tier row per level, and (``config``) the active `product_drawing` form-SLA step.

    Nothing is borrowed from the database: this is the chain the orchestrator reads, and it is
    the SAME shape an admin builds in SLA Management, so a hard-coded team in the service would
    not find it. The team set code is random on purpose.
    """
    company_id = db.execute(text("select id from companies where code = 'SRT'")).scalar()
    policy_id = _uid()
    db.add(SLAPolicy(id=policy_id, code=unique_code("POL"), name="ZZT drawing policy"))
    for level in range(1, tiers + 1):
        db.add(
            SLAPolicyTier(
                id=_uid(),
                policy_id=policy_id,
                tier_level=level,
                tier_name=f"Tier {level}",
                response_hours=4,
                resolution_hours=24,
            )
        )
    agent_id = _uid()
    agent_code = unique_code("agent")
    db.add(AccessAgent(id=agent_id, code=agent_code, name="ZZT Drawing Agent"))
    team_set_code = unique_code("teamset")

    members: dict[int, str] = {}
    for level in range(1, tiers + 1):
        team_id = _uid()
        db.add(Team(id=team_id, name=unique_code(f"Team{level}"), company_id=company_id))
        db.add(
            AgentTeam(
                id=_uid(),
                agent_id=agent_id,
                code=team_set_code,
                team_id=team_id,
                tier=level,
                company_id=company_id,
            )
        )
        db.flush()
        contact_id = None
        if link_whatsapp:
            contact_id = _uid()
            db.add(
                RespondContact(
                    id=contact_id,
                    phone_number=f"+6011{uuid.uuid4().int % 10**8:08d}",
                    name=f"ZZT WhatsApp T{level}",
                    respond_io_id=f"zzt-rio-{uuid.uuid4().hex[:8]}",
                    session_vars={},
                )
            )
            db.flush()
        member_id = _uid()
        db.add(
            User(
                id=member_id,
                email=f"{member_id}@t.zzt",
                name=f"ZZT Drawing Member T{level}",
                status="ACTIVE",
                respond_contact_id=contact_id,
                notify_email_on_assignment=email_on_assignment,
                notify_whatsapp_on_assignment=whatsapp_on_assignment,
                notify_email_on_escalation=email_on_escalation,
                notify_whatsapp_on_escalation=whatsapp_on_escalation,
            )
        )
        db.flush()
        db.add(TeamMember(id=_uid(), team_id=team_id, user_id=member_id))
        members[level] = member_id

    config_id = None
    if config:
        config_id = _uid()
        db.add(
            FormSLAConfig(
                id=config_id,
                source_entity_type=SOURCE,
                stage_code=unique_code("stage"),
                policy_id=policy_id,
                agent_code=agent_code,
                team_set_code=team_set_code,
                start_event=start_event,
                respond_event="respond",
                resolve_event="resolve",
                is_active=active,
                notify_assignee=True,
            )
        )
    db.commit()
    return {
        "policy_id": policy_id,
        "agent_id": agent_id,
        "agent_code": agent_code,
        "team_set_code": team_set_code,
        "members": members,
        "assignee": members[1],
        "config_id": config_id,
    }


def actor(user_id: str) -> dict:
    """The dict a route hands the service (`get_current_user`)."""
    return {"id": user_id, "email": f"{user_id}@zzt.test", "name": "Tester"}


def quoted_product(db, env, *, name: str = "wc"):
    """A product on a saved quotation line. Returns (product, version, line)."""
    from app.services import project_quotation_service as quotes

    product = _product(db, env)
    _document, scope = _scope(db, env)
    line = _priced_line(db, env, scope, product)
    version = quotes.current_version(db, scope.id)
    db.commit()
    return product, version, line


def trackers_for(db, product_id) -> list:
    return (
        db.query(ConversationSLATracking)
        .filter(
            ConversationSLATracking.source_entity_type == SOURCE,
            ConversationSLATracking.source_entity_id == str(product_id),
        )
        .all()
    )


def requester_rows(db, tracker_id) -> list:
    return (
        db.query(ConversationSLAEventLog)
        .filter(
            ConversationSLAEventLog.sla_tracking_id == str(tracker_id),
            ConversationSLAEventLog.event_type == "requester",
        )
        .all()
    )


def notes_for(db, user_id) -> list:
    return (
        db.query(Notification)
        .filter(Notification.user_id == str(user_id))
        .order_by(Notification.created_at.asc(), Notification.id.asc())
        .all()
    )


def channels(db, note) -> set:
    return {
        d.channel
        for d in db.query(NotificationDelivery).filter(NotificationDelivery.notification_id == note.id)
    }


def naive_utc(value):
    """A response datetime (aware or ISO string or naive) as naive UTC, to compare with columns."""
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


@contextmanager
def captured_sql(db):
    """Every SQL statement the session's connection runs inside the block, in order."""
    statements: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    connection = db.get_bind()
    event.listen(connection, "before_cursor_execute", _record)
    try:
        yield statements
    finally:
        event.remove(connection, "before_cursor_execute", _record)


# ---------------------------------------------------------------------------- AC-1 has_drawing


def test_an_image_typed_technical_specifications_is_a_drawing(db, env):
    product = _product(db, env)
    _drawing(db, env, product, "d.jpg")
    assert _svc().has_drawing(db, product.id) is True


def test_a_pdf_typed_technical_specifications_is_a_drawing(db, env):
    product = _product(db, env)
    _drawing(db, env, product, "d.pdf", mime="application/pdf")
    assert _svc().has_drawing(db, product.id) is True


def test_a_deleted_drawing_is_not_a_drawing(db, env):
    product = _product(db, env)
    _drawing(db, env, product, "gone.jpg", deleted=True)
    _drawing(db, env, product, "gone.pdf", mime="application/pdf", deleted=True)
    assert _svc().has_drawing(db, product.id) is False


def test_a_file_of_another_type_is_not_a_drawing_even_as_a_pdf_or_image(db, env):
    product = _product(db, env)
    _photo(db, env, product, "photo.jpg")
    _photo(db, env, product, "brochure.pdf", mime="application/pdf")
    assert _svc().has_drawing(db, product.id) is False


def test_a_drawing_of_another_product_is_not_this_products_drawing(db, env):
    mine, other = _product(db, env), _product(db, env)
    _drawing(db, env, other, "theirs.jpg")
    assert _svc().has_drawing(db, mine.id) is False
    assert _svc().has_drawing(db, other.id) is True


def test_a_non_image_non_pdf_drawing_file_is_not_a_drawing(db, env):
    product = _product(db, env)
    _drawing(db, env, product, "sheet.xlsx", mime="application/vnd.ms-excel")
    assert _svc().has_drawing(db, product.id) is False


# --------------------------------------------------------------------- AC-3 one task per product


def test_escalate_opens_one_task_for_the_product_from_the_configured_step(db, env):
    team = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    caller = _user(db, "zzt Sales One")

    out = _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(caller))

    rows = trackers_for(db, product.id)
    assert len(rows) == 1
    tracker = rows[0]
    assert tracker.assigned_to_id == team["assignee"]
    assert tracker.agent_id == team["agent_id"]
    assert tracker.team_set_code == team["team_set_code"]
    assert str(tracker.policy_id) == team["policy_id"]
    assert tracker.current_tier == 1
    assert tracker.due_at is not None and tracker.due_at_resolution is not None
    assert tracker.is_resolved is False
    assert out["joined"] is False
    assert str(out["escalation"]["tracking_id"]) == str(tracker.id)
    assert out["escalation"]["requester_count"] == 1


def test_the_requester_is_an_event_log_row_naming_the_user_and_the_quotation(db, env):
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    caller = _user(db, "zzt Sales One")

    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(caller))

    (tracker,) = trackers_for(db, product.id)
    (row,) = requester_rows(db, tracker.id)
    assert row.triggered_by_id == caller
    assert row.reason == f"quotation_version:{version.id}"


def test_a_set_line_escalates_its_driver_part_not_the_set(db, env):
    from app.services import project_quotation_service as quotes

    seed_drawing_team(db)
    driver = _product(db, env)
    other_part = _product(db, env)
    _document, scope = _scope(db, env)
    version = quotes.current_version(db, scope.id)
    from app.models.projects import ProjectQuotationLine

    line = _priced_line(db, env, scope, driver)
    # Re-shape the saved line into a SET line: no own product, the parts frozen on it.
    line.product_id = None
    line.set_parts_snapshot = [
        {"product_id": str(other_part.id), "product_code": other_part.product_code, "quantity": "1", "is_driver": False},
        {"product_id": str(driver.id), "product_code": driver.product_code, "quantity": "1", "is_driver": True},
    ]
    db.flush()
    assert isinstance(line, ProjectQuotationLine)
    db.commit()
    caller = _user(db, "zzt Sales One")

    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(caller))

    assert len(trackers_for(db, driver.id)) == 1
    assert trackers_for(db, other_part.id) == []


# ---------------------------------------------------------------------------- AC-4 join, not dup


def test_a_second_user_joins_the_open_task_and_is_counted(db, env):
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    first, second = _user(db, "zzt Sales One"), _user(db, "zzt Sales Two")

    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(first))
    out = _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(second))

    rows = trackers_for(db, product.id)
    assert len(rows) == 1, "a second escalate must not open a second task"
    assert out["joined"] is True
    assert out["escalation"]["requester_count"] == 2
    assert {r.triggered_by_id for r in requester_rows(db, rows[0].id)} == {first, second}


def test_a_second_quotation_of_the_same_product_joins_the_same_task(db, env):
    from app.services import project_quotation_service as quotes

    seed_drawing_team(db)
    product, version_a, line_a = quoted_product(db, env)
    _document, scope_b = _scope(db, env)
    line_b = _priced_line(db, env, scope_b, product)
    version_b = quotes.current_version(db, scope_b.id)
    db.commit()
    first, second = _user(db, "zzt Sales One"), _user(db, "zzt Sales Two")

    _svc().escalate(db, version_id=version_a.id, line_id=line_a.id, user=actor(first))
    out = _svc().escalate(db, version_id=version_b.id, line_id=line_b.id, user=actor(second))

    assert len(trackers_for(db, product.id)) == 1
    assert out["joined"] is True
    reasons = {r.reason for r in requester_rows(db, trackers_for(db, product.id)[0].id)}
    assert reasons == {f"quotation_version:{version_a.id}", f"quotation_version:{version_b.id}"}


def test_the_same_user_twice_is_recorded_once(db, env):
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    caller = _user(db, "zzt Sales One")

    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(caller))
    out = _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(caller))

    (tracker,) = trackers_for(db, product.id)
    assert len(requester_rows(db, tracker.id)) == 1
    assert out["joined"] is True
    assert out["escalation"]["requester_count"] == 1


def test_escalate_locks_the_product_row_before_it_reads_or_opens_a_task(db, env):
    """Two clicks in the same second must open one task. The check "is there an open task" is
    read-then-write, so the product row is locked FOR UPDATE around it; a second click then waits
    for the first to commit and finds its task. A rolled-back single connection cannot race two
    sessions, so this pins the lock itself: a `FOR UPDATE` on products runs before the first
    INSERT into the tracker table."""
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    caller = _user(db, "zzt Sales One")

    with captured_sql(db) as statements:
        _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(caller))

    lowered = [s.lower() for s in statements]
    lock_at = next(
        (i for i, s in enumerate(lowered) if "for update" in s and "from products" in s), None
    )
    insert_at = next(
        # A scratch schema qualifies the table name, so match it anywhere in the INSERT.
        (
            i
            for i, s in enumerate(lowered)
            if s.lstrip().startswith("insert into") and "conversation_sla_tracking (" in s
        ),
        None,
    )
    assert lock_at is not None, "the product row is never locked FOR UPDATE"
    assert insert_at is not None, "no tracker was inserted"
    assert lock_at < insert_at, "the lock must be taken before the tracker is written"


# ------------------------------------------------------------------------------ AC-9 refusals


def test_a_product_that_has_a_drawing_is_refused_and_nothing_is_created(db, env):
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    _drawing(db, env, product, "d.jpg")
    db.commit()
    caller = _user(db, "zzt Sales One")

    with pytest.raises(AppException) as refused:
        _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(caller))

    assert refused.value.status_code == 409
    assert refused.value.code == "product_has_drawing"
    assert trackers_for(db, product.id) == []


def test_a_pdf_drawing_also_refuses_the_escalation(db, env):
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    _drawing(db, env, product, "d.pdf", mime="application/pdf")
    db.commit()
    caller = _user(db, "zzt Sales One")

    with pytest.raises(AppException) as refused:
        _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(caller))

    assert refused.value.status_code == 409
    assert refused.value.code == "product_has_drawing"
    assert trackers_for(db, product.id) == []


@pytest.mark.parametrize("variant", ["no_config", "inactive_config", "config_without_escalate_event"])
def test_no_configured_step_is_a_409_and_creates_nothing(db, env, variant):
    if variant == "no_config":
        seed_drawing_team(db, config=False)
    elif variant == "inactive_config":
        seed_drawing_team(db, active=False)
    else:
        seed_drawing_team(db, start_event="submit")
    product, version, line = quoted_product(db, env)
    caller = _user(db, "zzt Sales One")

    with pytest.raises(AppException) as refused:
        _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(caller))

    assert refused.value.status_code == 409
    assert refused.value.code == "drawing_requests_not_set_up"
    assert "No team is set up for drawing requests" in refused.value.message
    assert trackers_for(db, product.id) == []


def test_a_misconfigured_step_surfaces_its_error_instead_of_failing_silently(db, env):
    """`emit_event` swallows errors and skips without a word; `escalate` must not. A step whose
    agent code names no access agent has to come back as an error, never as a 200 that opened
    nothing."""
    seed = seed_drawing_team(db)
    config = db.query(FormSLAConfig).filter(FormSLAConfig.id == seed["config_id"]).one()
    config.agent_code = unique_code("no-such-agent")
    db.commit()
    product, version, line = quoted_product(db, env)
    caller = _user(db, "zzt Sales One")

    with pytest.raises(AppException) as refused:
        _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(caller))

    assert refused.value.status_code >= 400
    assert trackers_for(db, product.id) == []


def test_an_off_catalogue_line_is_refused_and_nothing_is_created(db, env):
    from app.services import project_quotation_service as quotes

    seed_drawing_team(db)
    _document, scope = _scope(db, env)
    line = _priced_line(db, env, scope)  # no product: a typed description
    version = quotes.current_version(db, scope.id)
    db.commit()
    caller = _user(db, "zzt Sales One")

    with pytest.raises(AppException) as refused:
        _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(caller))

    assert refused.value.status_code in (404, 409)
    assert (
        db.query(ConversationSLATracking)
        .filter(ConversationSLATracking.source_entity_type == SOURCE)
        .count()
        == 0
    )


def test_a_line_that_belongs_to_another_version_is_a_404(db, env):
    from app.services import project_quotation_service as quotes

    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    _document, other_scope = _scope(db, env)
    other_version = quotes.current_version(db, other_scope.id)
    db.commit()
    caller = _user(db, "zzt Sales One")

    with pytest.raises(AppException) as refused:
        _svc().escalate(db, version_id=other_version.id, line_id=line.id, user=actor(caller))

    assert refused.value.status_code == 404
    assert trackers_for(db, product.id) == []


@pytest.mark.parametrize("which", ["version", "line", "both"])
def test_an_unknown_version_or_line_is_a_404(db, env, which):
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    caller = _user(db, "zzt Sales One")
    version_id = _uid() if which in ("version", "both") else version.id
    line_id = _uid() if which in ("line", "both") else line.id

    with pytest.raises(AppException) as refused:
        _svc().escalate(db, version_id=version_id, line_id=line_id, user=actor(caller))

    assert refused.value.status_code == 404
    assert trackers_for(db, product.id) == []


def test_no_team_is_named_in_the_service():
    """Rule 4: the admin chooses the team in SLA Management, and `marketing_product` is only the
    FRONTEND's pre-fill. A team, agent or policy code in the service is a hard-coded route."""
    source = inspect.getsource(_svc())
    for needle in ("marketing_product", "purchasing", "'marketing'", '"marketing"'):
        assert needle not in source, f"{needle!r} is hard-coded in the service"


# ------------------------------------------------------------------- escalation_states (the cell)


def test_states_are_keyed_by_every_product_asked_for(db, env):
    seed_drawing_team(db)
    open_product, version, line = quoted_product(db, env)
    never = _product(db, env)
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")))

    states = _svc().escalation_states(db, [open_product.id, never.id])

    assert set(states) == {str(open_product.id), str(never.id)}
    assert states[str(never.id)] is None


def test_an_open_task_state_carries_the_cell_fields(db, env):
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    first, second = _user(db, "zzt Sales One"), _user(db, "zzt Sales Two")
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(first))
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(second))
    (tracker,) = trackers_for(db, product.id)

    state = _svc().escalation_states(db, [product.id])[str(product.id)]

    assert set(state) >= {
        "tracking_id", "opened_at", "responded_at", "due_at", "requester_count", "last_resolved_at",
    }
    assert str(state["tracking_id"]) == str(tracker.id)
    assert naive_utc(state["opened_at"]) == tracker.initiated_at
    assert state["responded_at"] is None
    assert naive_utc(state["due_at"]) == tracker.due_at, "before a response the response clock governs"
    assert state["requester_count"] == 2
    assert state["last_resolved_at"] is None


def test_after_a_response_the_resolution_clock_governs_the_due_date(db, env):
    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")))
    (tracker,) = trackers_for(db, product.id)

    _svc().respond(db, tracker.id, actor(seed["assignee"]))
    db.refresh(tracker)
    state = _svc().escalation_states(db, [product.id])[str(product.id)]

    assert state["responded_at"] is not None
    assert naive_utc(state["due_at"]) == tracker.due_at_resolution


def test_a_resolved_task_leaves_only_when_it_was_last_resolved(db, env):
    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")))
    (tracker,) = trackers_for(db, product.id)
    _svc().resolve(db, tracker.id, actor(seed["assignee"]))
    db.refresh(tracker)

    state = _svc().escalation_states(db, [product.id])[str(product.id)]

    assert state is not None
    assert state["tracking_id"] is None
    assert state["opened_at"] is None and state["responded_at"] is None and state["due_at"] is None
    assert state["requester_count"] in (None, 0)
    assert naive_utc(state["last_resolved_at"]) == tracker.resolved_at


def test_states_cost_the_same_number_of_queries_for_one_product_or_many(db, env):
    seed_drawing_team(db)
    products = []
    for _ in range(5):
        product, version, line = quoted_product(db, env)
        _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")))
        products.append(product.id)
    _svc().escalation_states(db, products)  # warm any one-off lookup

    with captured_sql(db) as one:
        _svc().escalation_states(db, products[:1])
    with captured_sql(db) as many:
        _svc().escalation_states(db, products)

    assert len(many) == len(one), (len(one), len(many))


# ------------------------------------------------------------- AC-6 the normal SLA flow, respond/resolve


def test_respond_then_resolve_flip_the_task_and_the_my_pending_row(db, env):
    from app.services.sla_service import ConversationSLATrackingService

    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")))
    (tracker,) = trackers_for(db, product.id)
    pending = ConversationSLATrackingService(db)

    row = next(r for r in pending.list_my_pending(seed["assignee"]) if r["id"] == str(tracker.id))
    assert row["is_responded"] is False and row["due_kind"] == "respond"

    _svc().respond(db, tracker.id, actor(seed["assignee"]))
    db.refresh(tracker)
    assert tracker.is_responded is True and tracker.is_resolved is False
    row = next(r for r in pending.list_my_pending(seed["assignee"]) if r["id"] == str(tracker.id))
    assert row["is_responded"] is True and row["due_kind"] == "resolve"

    _svc().resolve(db, tracker.id, actor(seed["assignee"]))
    db.refresh(tracker)
    assert tracker.is_resolved is True
    assert [r for r in pending.list_my_pending(seed["assignee"]) if r["id"] == str(tracker.id)] == []


def test_resolve_without_a_prior_respond_also_marks_it_responded(db, env):
    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")))
    (tracker,) = trackers_for(db, product.id)

    _svc().resolve(db, tracker.id, actor(seed["assignee"]))

    db.refresh(tracker)
    assert tracker.is_resolved is True and tracker.is_responded is True


@pytest.mark.parametrize("action", ["respond", "resolve"])
def test_someone_who_is_not_the_assignee_cannot_act_and_nothing_changes(db, env, action):
    seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")))
    (tracker,) = trackers_for(db, product.id)
    stranger = _user(db, "zzt Stranger")

    with pytest.raises(AppException) as refused:
        getattr(_svc(), action)(db, tracker.id, actor(stranger))

    assert refused.value.status_code in (400, 404)
    db.refresh(tracker)
    assert tracker.is_resolved is False and tracker.is_responded is False


@pytest.mark.parametrize("action", ["respond", "resolve"])
def test_a_tracker_of_another_type_is_a_409(db, env, action):
    seed = seed_drawing_team(db)
    complaint_task = ConversationSLATracking(
        id=_uid(),
        policy_id=seed["policy_id"],
        current_tier=1,
        initiated_at=datetime.utcnow(),
        current_tier_started_at=datetime.utcnow(),
        due_at=datetime.utcnow() + timedelta(hours=4),
        due_at_resolution=datetime.utcnow() + timedelta(hours=24),
        is_resolved=False,
        source_entity_type="complaint",
        source_entity_id=_uid(),
        agent_id=seed["agent_id"],
        assigned_to_id=seed["assignee"],
    )
    db.add(complaint_task)
    db.commit()

    with pytest.raises(AppException) as refused:
        getattr(_svc(), action)(db, complaint_task.id, actor(seed["assignee"]))

    assert refused.value.status_code == 409
    db.refresh(complaint_task)
    assert complaint_task.is_resolved is False


@pytest.mark.parametrize("action", ["respond", "resolve"])
def test_an_unknown_tracker_is_a_404(db, env, action):
    seed = seed_drawing_team(db)
    with pytest.raises(AppException) as refused:
        getattr(_svc(), action)(db, _uid(), actor(seed["assignee"]))
    assert refused.value.status_code == 404


def test_the_task_is_on_my_pending_as_a_form_row_with_the_product_code_as_its_reference(db, env):
    from app.services.sla_service import ConversationSLATrackingService

    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")))
    (tracker,) = trackers_for(db, product.id)

    rows = ConversationSLATrackingService(db).list_my_pending(seed["assignee"])

    row = next(r for r in rows if r["id"] == str(tracker.id))
    assert row["source_entity_type"] == SOURCE
    assert row["source_entity_id"] == str(product.id)
    assert row["is_form_sla"] is True
    assert row["reference"] == product.product_code
    assert row["current_tier"] == 1


# --------------------------------------------------------------------- AC-12 H1: opening the task


def _assigned_note(db, seed, tracker):
    notes = [
        n
        for n in notes_for(db, seed["assignee"])
        if n.source_entity_type == FORM_SLA_NOTE_SOURCE and str(n.source_entity_id) == str(tracker.id)
    ]
    assert len(notes) == 1, [n.title for n in notes]
    return notes[0]


def test_h1_opening_the_task_notifies_the_assignee_on_every_channel_they_allow(db, env):
    seed = seed_drawing_team(db, whatsapp_on_assignment=True, link_whatsapp=True)
    product, version, line = quoted_product(db, env)

    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")))

    (tracker,) = trackers_for(db, product.id)
    note = _assigned_note(db, seed, tracker)
    assert note.event_type == "assigned"
    assert note.title == f"New SLA assignment: {product.product_code}"
    assert channels(db, note) == {"in_app", "email", "whatsapp"}
    assert note.data["link"] == f"/master-data-management/products/{product.id}"
    assert note.data["whatsapp_use_case"] == "sla_assignment"
    assert f"/master-data-management/products/{product.id}" in note.data["whatsapp_context_vars"]["form_url"]


def test_h1_toggles_off_leave_only_the_in_app_notice(db, env):
    seed = seed_drawing_team(
        db, email_on_assignment=False, whatsapp_on_assignment=False, link_whatsapp=True
    )
    product, version, line = quoted_product(db, env)

    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")))

    (tracker,) = trackers_for(db, product.id)
    assert channels(db, _assigned_note(db, seed, tracker)) == {"in_app"}


def test_h1_whatsapp_needs_a_linked_contact_even_with_the_toggle_on(db, env):
    seed = seed_drawing_team(db, whatsapp_on_assignment=True, link_whatsapp=False)
    product, version, line = quoted_product(db, env)

    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")))

    (tracker,) = trackers_for(db, product.id)
    assert channels(db, _assigned_note(db, seed, tracker)) == {"in_app", "email"}


def test_a_join_does_not_notify_the_assignee_again(db, env):
    seed = seed_drawing_team(db, whatsapp_on_assignment=True, link_whatsapp=True)
    product, version, line = quoted_product(db, env)

    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")))
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales Two")))

    (tracker,) = trackers_for(db, product.id)
    _assigned_note(db, seed, tracker)  # exactly one


# ------------------------------------------------------------- AC-12 H2: the overdue scan escalates


def test_h2_the_overdue_scan_moves_a_drawing_task_up_and_notifies_the_new_assignee(db, env):
    from app.services.form_sla_service import FormSLAOrchestrator

    seed = seed_drawing_team(
        db, tiers=2, whatsapp_on_escalation=True, link_whatsapp=True, whatsapp_on_assignment=False
    )
    product, version, line = quoted_product(db, env)
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")))
    (tracker,) = trackers_for(db, product.id)
    tracker.due_at = datetime.utcnow() - timedelta(hours=1)
    tracker.due_at_resolution = datetime.utcnow() - timedelta(hours=1)
    db.commit()

    result = FormSLAOrchestrator(db).scan_overdue_and_escalate()

    db.refresh(tracker)
    assert result["escalated"] == 1, result
    assert tracker.current_tier == 2
    assert tracker.assigned_to_id == seed["members"][2]
    notes = [
        n
        for n in notes_for(db, seed["members"][2])
        if n.source_entity_type == FORM_SLA_NOTE_SOURCE and n.event_type == "escalated"
    ]
    assert len(notes) == 1
    assert notes[0].title == f"SLA escalated to you: {product.product_code}"
    assert channels(db, notes[0]) == {"in_app", "email", "whatsapp"}
    assert notes[0].data["whatsapp_use_case"] == "sla_escalation"


def test_h2_escalation_toggles_off_leave_only_in_app(db, env):
    from app.services.form_sla_service import FormSLAOrchestrator

    seed = seed_drawing_team(
        db, tiers=2, email_on_escalation=False, whatsapp_on_escalation=False, link_whatsapp=True
    )
    product, version, line = quoted_product(db, env)
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")))
    (tracker,) = trackers_for(db, product.id)
    tracker.due_at = datetime.utcnow() - timedelta(hours=1)
    db.commit()

    FormSLAOrchestrator(db).scan_overdue_and_escalate()

    notes = [
        n
        for n in notes_for(db, seed["members"][2])
        if n.source_entity_type == FORM_SLA_NOTE_SOURCE and n.event_type == "escalated"
    ]
    assert len(notes) == 1
    assert channels(db, notes[0]) == {"in_app"}


# -------------------------------------------------------- AC-7 / AC-12 H3: a drawing linked while open


def _link_through_the_product_service(db, product, attachment):
    from app.schemas.product import ProductAttachmentCreate
    from app.services.product_service import ProductAttachmentService

    return ProductAttachmentService(db).create_product_attachment(
        ProductAttachmentCreate(product_id=str(product.id), attachment_id=str(attachment.id))
    )


def _drawing_added_notes(db, user_id) -> list:
    return [
        n for n in notes_for(db, user_id) if "Drawing added" in f"{n.title} {n.body or ''}"
    ]


@pytest.mark.parametrize("mime", ["image/png", "application/pdf"])
def test_h3_linking_a_drawing_while_the_task_is_open_notifies_the_assignee_and_leaves_it_open(
    db, env, mime
):
    seed = seed_drawing_team(db, whatsapp_on_assignment=True, link_whatsapp=True)
    product, version, line = quoted_product(db, env)
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")))
    (tracker,) = trackers_for(db, product.id)
    attachment = _file(db, env["company_id"], DRAWINGS, f"late.{mime.split('/')[1]}", mime=mime)

    _link_through_the_product_service(db, product, attachment)

    db.refresh(tracker)
    assert tracker.is_resolved is False and tracker.voided_at is None, "adding a drawing must not close the task"
    (note,) = _drawing_added_notes(db, seed["assignee"])
    assert product.product_code in f"{note.title} {note.body or ''}"
    assert "resolve" in (note.body or "").lower()
    assert channels(db, note) == {"in_app", "email", "whatsapp"}
    assert note.data["whatsapp_use_case"] == "sla_assignment"


def test_h3_toggles_off_leave_only_in_app(db, env):
    seed = seed_drawing_team(db, email_on_assignment=False, whatsapp_on_assignment=False, link_whatsapp=True)
    product, version, line = quoted_product(db, env)
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")))
    attachment = _file(db, env["company_id"], DRAWINGS, "late.png")

    _link_through_the_product_service(db, product, attachment)

    (note,) = _drawing_added_notes(db, seed["assignee"])
    assert channels(db, note) == {"in_app"}


def test_h3_a_file_that_is_not_a_drawing_notifies_nobody(db, env):
    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")))
    photo = _file(db, env["company_id"], PHOTOS, "photo.jpg")
    other_type_pdf = _file(db, env["company_id"], PHOTOS, "brochure.pdf", mime="application/pdf")

    _link_through_the_product_service(db, product, photo)
    _link_through_the_product_service(db, product, other_type_pdf)

    assert _drawing_added_notes(db, seed["assignee"]) == []


def test_h3_a_drawing_with_no_open_task_notifies_nobody(db, env):
    seed = seed_drawing_team(db)
    product = _product(db, env)
    attachment = _file(db, env["company_id"], DRAWINGS, "early.png")

    _link_through_the_product_service(db, product, attachment)

    assert _drawing_added_notes(db, seed["assignee"]) == []
    assert trackers_for(db, product.id) == []


def test_notify_drawing_linked_is_a_noop_without_an_open_task_and_notifies_with_one(db, env):
    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)

    _svc().notify_drawing_linked(db, product.id)
    assert _drawing_added_notes(db, seed["assignee"]) == []

    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")))
    _svc().notify_drawing_linked(db, product.id)
    assert len(_drawing_added_notes(db, seed["assignee"])) == 1


# ----------------------------------------------------------- AC-8 / AC-12 H4: resolve tells requesters


def test_h4_resolving_tells_every_requester_once_on_every_channel_they_allow(db, env):
    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    # Requesters are salespeople, each with their own toggles and WhatsApp link.
    contact = RespondContact(
        id=_uid(), phone_number="+60110000777", name="ZZT Sales WhatsApp",
        respond_io_id=f"zzt-rio-{uuid.uuid4().hex[:8]}", session_vars={},
    )
    db.add(contact)
    db.flush()
    first = _user(db, "zzt Sales One")
    second = _user(db, "zzt Sales Two")
    one = db.query(User).filter(User.id == first).one()
    one.respond_contact_id = contact.id
    one.notify_whatsapp_on_assignment = True
    one.notify_email_on_assignment = True
    two = db.query(User).filter(User.id == second).one()
    two.notify_email_on_assignment = False
    db.commit()
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(first))
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(second))
    (tracker,) = trackers_for(db, product.id)

    _svc().resolve(db, tracker.id, actor(seed["assignee"]))

    title = f"Drawing request for {product.product_code} resolved"
    for requester, expected in ((first, {"in_app", "email", "whatsapp"}), (second, {"in_app"})):
        notes = [n for n in notes_for(db, requester) if n.title == title]
        assert len(notes) == 1, (requester, [n.title for n in notes_for(db, requester)])
        assert channels(db, notes[0]) == expected
    # It names the project the requester escalated from, so the bell opens their quotation.
    one_note = [n for n in notes_for(db, first) if n.title == title][0]
    assert str(env["project"].id) in (one_note.data or {}).get("link", "")
    # The assignee closed it; they are not a requester and hear nothing about it.
    assert [n for n in notes_for(db, seed["assignee"]) if n.title == title] == []


def test_h4_a_second_resolve_does_not_tell_the_requesters_again(db, env):
    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    caller = _user(db, "zzt Sales One")
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(caller))
    (tracker,) = trackers_for(db, product.id)

    _svc().resolve(db, tracker.id, actor(seed["assignee"]))
    try:
        _svc().resolve(db, tracker.id, actor(seed["assignee"]))
    except AppException:
        pass  # refusing the repeat is as good as ignoring it

    title = f"Drawing request for {product.product_code} resolved"
    assert len([n for n in notes_for(db, caller) if n.title == title]) == 1


def test_h4_after_resolve_without_a_drawing_a_new_escalate_opens_a_new_task(db, env):
    seed = seed_drawing_team(db)
    product, version, line = quoted_product(db, env)
    caller = _user(db, "zzt Sales One")
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(caller))
    (first,) = trackers_for(db, product.id)
    _svc().resolve(db, first.id, actor(seed["assignee"]))

    out = _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(caller))

    assert out["joined"] is False
    open_tasks = [t for t in trackers_for(db, product.id) if not t.is_resolved]
    assert len(open_tasks) == 1 and str(open_tasks[0].id) != str(first.id)
    assert out["escalation"]["requester_count"] == 1, "a new task starts its own requester list"


# ------------------------------------------------------------- the quotation line read (cell state)


def test_a_line_read_carries_the_escalation_state_and_null_when_there_is_none(db, env):
    from app.services import project_quotation_service as quotes

    seed_drawing_team(db)
    asked, version, line = quoted_product(db, env)
    quiet_product = _product(db, env)
    _document, scope = _scope(db, env)
    quiet_line = _priced_line(db, env, scope, quiet_product)
    _svc().escalate(db, version_id=version.id, line_id=line.id, user=actor(_user(db, "zzt Sales One")))

    cells = {r["id"]: r["technical_drawing"] for r in quotes.serialize_lines(db, [line, quiet_line])}

    escalation = cells[line.id]["escalation"]
    assert set(escalation) >= {"opened_at", "responded_at", "due_at", "requester_count", "last_resolved_at"}
    assert escalation["requester_count"] == 1
    assert "escalation" in cells[quiet_line.id] and cells[quiet_line.id]["escalation"] is None


def test_every_line_of_every_quotation_with_the_product_shows_the_same_state(db, env):
    from app.services import project_quotation_service as quotes

    seed_drawing_team(db)
    product, version_a, line_a = quoted_product(db, env)
    _document, scope_b = _scope(db, env)
    line_b = _priced_line(db, env, scope_b, product)
    _svc().escalate(db, version_id=version_a.id, line_id=line_a.id, user=actor(_user(db, "zzt Sales One")))

    cells = {r["id"]: r["technical_drawing"] for r in quotes.serialize_lines(db, [line_a, line_b])}

    assert cells[line_a.id]["escalation"] == cells[line_b.id]["escalation"]
    assert cells[line_b.id]["escalation"] is not None


def test_a_pdf_only_product_reads_the_pdf_state_with_its_signed_url_and_filename(db, env):
    from app.services import project_quotation_service as quotes

    product, version, line = quoted_product(db, env)
    pdf = _drawing(db, env, product, "TS-0002.pdf", mime="application/pdf")
    db.commit()

    cell = quotes.serialize_lines(db, [line])[0]["technical_drawing"]

    assert cell["state"] == "pdf"
    assert cell["url"]
    assert cell["filename"] == pdf.original_filename
    assert "escalation" in cell


def test_an_image_drawing_wins_over_a_pdf_drawing_in_the_cell(db, env):
    from app.services import project_quotation_service as quotes

    product, version, line = quoted_product(db, env)
    _drawing(db, env, product, "TS-0002.pdf", mime="application/pdf")
    image = _drawing(db, env, product, "TS-0001.png")
    db.commit()

    cell = quotes.serialize_lines(db, [line])[0]["technical_drawing"]

    assert cell["state"] == "default"
    assert cell["attachment_id"] == image.id


def test_a_pdf_is_never_stamped_on_the_line_at_issue(db, env):
    from app.services import project_quotation_image_service as quotation_images

    product, version, line = quoted_product(db, env)
    _drawing(db, env, product, "TS-0002.pdf", mime="application/pdf")
    db.commit()

    quotation_images.freeze_version_images(db, version.id)

    db.refresh(line)
    assert line.drawing_attachment_id is None, "the quotation documents embed images only"
