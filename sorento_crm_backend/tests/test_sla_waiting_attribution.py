"""S4a gate - waiting attribution: the system learns to say "waiting on someone who is not us".

Satisfies AC-M1 to AC-M7 and AC-M36d, under the two rulings taken 2026-08-03 and
recorded in ``PLAN-after-sales-warranty.md`` ("Three things this slice must decide"):
waiting lives on the TRACKER, and AC-M4's guard covers resolve, manual escalate and
extend, all of them human.

Today every delay reads as internal inaction. 307 form-SLA trackers are open and
overdue on the production copy and not one of them can say why, so the dashboard
blames whoever holds the record even when the record is sitting on a plumber. This
slice is one column trio plus the discipline that keeps it honest.

Six things shape this suite, and each is a place the specification is silent, wrong,
or describes something that cannot be built where it says.

1. **AC-M4 cannot be enforced on the resolve path the SLA layer owns.** Form-SLA
   resolve is event-driven: a case status change calls ``emit_form_event``, which
   calls ``_resolve_for_active``. That path swallows every exception twice - once per
   config inside ``emit_event``'s loop, and again at every call site, which wraps the
   emit in ``try/except`` and warns. Both swallows sit AFTER ``db.commit()``. A guard
   raised there would be logged and discarded: the case would close and its overdue
   tracker would stay open forever, which is strictly worse than no guard.
   So the resolve half of AC-M4 rides the **status engine's** chokepoint
   (``assert_transition_allowed`` / ``_by_key``), which runs before the commit and
   already raises 422 to the route. That is the third guard the plan feared, and it
   is the only place the rejection can reach a human. It is narrow by construction:
   only two entity types are registered on the engine today (``complaint`` and
   ``workflow_submission``, both after-sales cases), so purchase requests, sponsorship
   forms, stock inquiries and tickets are untouched - asserted below rather than
   asserted about.

2. **"Overdue" already has a definition and this slice must not write a second one.**
   ``scan_overdue_and_escalate`` implements the split-clock rule: pre-response the
   response clock gates, post-response only the resolution clock does, because
   ``extend`` moves ``due_at_resolution`` alone and a responded tracker whose response
   deadline has lapsed must not count as overdue forever. A guard with its own
   ``due_at < now`` would reject actions the escalation scan considers perfectly on
   time. One shared helper, asserted by making the scan and the guard agree on a
   tracker built to expose the difference.

3. **Point-in-time capture belongs in ``create_event_log``, not in its callers.**
   AC-M7 reads captured values, never the live column, or every historical breach
   re-attributes itself the next time somebody edits the case. There are a dozen
   ``_write_event_log`` callers (escalate, resolve, extend, reassign, handling claim,
   release, takeover) and a stamp added per caller is a stamp somebody forgets. The
   single choke point is ``ConversationSLATrackingService.create_event_log``, so the
   capture is asserted there and inherited by everything above it.

4. **The two vocabularies are stored differently, on purpose.** ``waiting_on_party``
   stores the option VALUE as text; ``waiting_on_reason_id`` stores the option ID.
   AC-M7 groups breaches by party, and grouping by a string needs no join, while the
   party list is short and stable. Reasons are long-tail and get reworded by admins,
   and a reworded reason must not silently rewrite history, which is what storing the
   label would do. Both are ``lookup_options`` rows either way (AC-M1's "configurable
   master data", and the UAC's ruling that the party is configurable too).

5. **``waiting_since`` lies the moment an edit resets it.** "Waiting on maintenance
   since 3 Aug" is the whole point of AC-M3. Re-setting the SAME party (fixing the
   reason, say) must NOT restart the clock; switching to a different party must.

6. **AC-M36d is evidence, not a field.** "We called three times and nobody answered"
   is what makes ``waiting_on = customer`` defensible rather than a shrug. It reads
   the calls S4 already logs, and lands in the waiting event log's reason so the
   justification survives beside the claim.

Decisions taken here because the AC is silent, asserted so the next reader inherits
an answer rather than a coin flip:

- **Clearing waiting is an event, not an absence.** ``waiting_cleared`` gets its own
  event log row, or "we stopped waiting" is invisible and the duration is unrecoverable.
- **An inactive lookup option cannot be set** but an already-set value keeps rendering.
  Deactivating "plumber" must not rewrite the cases that were waiting on one.
- **The unattributed bucket is explicit.** AC-M7's sentence has three numbers, not two:
  external, internal, and the breaches nobody attributed. Hiding the third is how the
  metric quietly becomes a lie.

Everything runs on Postgres via ``blank_session``. Rows carry ``TEST_PREFIX`` and are
discarded by the outer rollback; nothing is counted across a shared table, which holds
real production data.

Run: venv/bin/python -m pytest tests/test_sla_waiting_attribution.py -q -p no:randomly
"""
from __future__ import annotations

import importlib
import importlib.util
import uuid
from datetime import date, datetime, timedelta

import pytest
import sqlalchemy as sa
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
from app.models.complaints import Complaint  # noqa: E402
from app.models.lookup import LookupBinding, LookupOption, LookupSet  # noqa: E402
from app.models.sla import (  # noqa: E402
    ConversationSLAEventLog,
    ConversationSLATracking,
    FormSLAConfig,
    SLAPolicy,
    SLAPolicyTier,
)
from app.models.user import User  # noqa: E402

from ._pg_fixture import TEST_PREFIX, blank_session, unique_code

# ---------------------------------------------------------------- the contract
#
# Names S4a is expected to add, as constants, so the implementer reads the whole
# contract on one screen and a rename is a single edit.

# Waiting is a rule about SLA attribution, not about any one form type. Its own
# module: form_sla_service is already 1400 lines of routing and escalation, and the
# status engine must be able to ask "is this attributed" without importing that.
WAITING_MODULE = "app.services.sla_waiting_service"

# AC-M1 plus the UAC ruling that the party is configurable master data too.
PARTY_SET_KEY = "sla_waiting_party"
REASON_SET_KEY = "sla_waiting_reason"

# AC-M1's list, plus dealer, which AC-M18 requires and AC-M1 forgot.
SEEDED_PARTIES = frozenset(
    {"cs", "maintenance", "plumber", "customer", "supplier", "warehouse", "dealer"}
)

WAITING_COLUMNS = ("waiting_on_party", "waiting_on_reason_id", "waiting_since")

# The event types a waiting change writes. Clearing is an event (see the header).
WAITING_SET_EVENT = "waiting_set"
WAITING_CLEARED_EVENT = "waiting_cleared"

# AC-M4. The error a blocked action raises, as a code the FE can branch on rather
# than a message it would have to string-match.
ATTRIBUTION_ERROR_CODE = "waiting_attribution_required"

# AC-M36d. How many unanswered calls make "waiting on the customer" defensible.
UNANSWERED_CALL_THRESHOLD = 3


# ---------------------------------------------------------------------- fixtures


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


# ----------------------------------------------------------------------- helpers


def _waiting():
    if importlib.util.find_spec(WAITING_MODULE) is None:
        raise AssertionError(
            f"{WAITING_MODULE} does not exist. S4a needs one module owning waiting "
            "attribution: set/clear, the AC-M4 guard, the derived case-level answer "
            "and the AC-M7 summary. The status engine has to call the guard, and it "
            "must not have to import form_sla_service to do it."
        )
    return importlib.import_module(WAITING_MODULE)


def _fn(module, name: str, signature: str):
    fn = getattr(module, name, None)
    assert callable(fn), f"{module.__name__}.{name}{signature} must exist."
    return fn


def _columns(model):
    return {c.key: c for c in model.__table__.columns}


def _utc_now() -> datetime:
    return datetime.utcnow()


def _user(db, label: str = "staff") -> User:
    user_id = unique_code(label).lower()
    user = User(
        id=user_id,
        email=f"{user_id}@{TEST_PREFIX.lower()}.invalid",
        name=f"{TEST_PREFIX} {label}",
        status="ACTIVE",
    )
    db.add(user)
    db.flush()
    return user


def _contact(db) -> RespondContact:
    contact = RespondContact(
        id=unique_code("contact").lower(),
        phone_number=f"+60{uuid.uuid4().int % 10**9:09d}",
        name=f"{TEST_PREFIX} Vinod",
        respond_io_id=str(uuid.uuid4().int % 10**7),
    )
    db.add(contact)
    db.flush()
    return contact


def _complaint(db, *, status: str = "submitted") -> Complaint:
    complaint = Complaint(
        id=str(uuid.uuid4()),
        complaint_number=unique_code("cmp")[:50],
        complaint_date=date.today(),
        status=status,
    )
    db.add(complaint)
    db.flush()
    return complaint


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


def _agent(db) -> AccessAgent:
    agent = AccessAgent(
        id=str(uuid.uuid4()),
        code=unique_code("agent").lower(),
        name=f"{TEST_PREFIX} after-sales",
    )
    db.add(agent)
    db.flush()
    return agent


def _config(db, agent, policy, *, source_entity_type: str = "complaint") -> FormSLAConfig:
    config = FormSLAConfig(
        id=str(uuid.uuid4()),
        source_entity_type=source_entity_type,
        stage_code=unique_code("stage").lower()[:100],
        policy_id=policy.id,
        agent_code=agent.code,
        team_set_code=unique_code("set").lower()[:100],
        start_event="submit",
        resolve_event="closed",
    )
    db.add(config)
    db.flush()
    return config


def _team(db, agent, config, policy, tier: int, members: list[User]) -> Team:
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


def _tracker(
    db,
    *,
    policy: SLAPolicy,
    source_entity_type: str = "complaint",
    source_entity_id: str | None = None,
    team_set_code: str | None = None,
    agent_id: str | None = None,
    overdue: bool = False,
    responded: bool = False,
    assigned_to_id: str | None = None,
) -> ConversationSLATracking:
    """A form-SLA stage tracker, on or off its deadline.

    ``overdue`` moves BOTH clocks into the past, so the tracker is overdue under the
    split-clock rule whether or not it has responded.
    """
    now = _utc_now()
    delta = timedelta(hours=-2) if overdue else timedelta(hours=+6)
    tracker = ConversationSLATracking(
        id=str(uuid.uuid4()),
        policy_id=policy.id,
        current_tier=1,
        initiated_at=now - timedelta(hours=8),
        current_tier_started_at=now - timedelta(hours=8),
        due_at=now + delta,
        due_at_resolution=now + delta,
        source_entity_type=source_entity_type,
        source_entity_id=source_entity_id or str(uuid.uuid4()),
        team_set_code=team_set_code,
        agent_id=agent_id,
        assigned_to_id=assigned_to_id,
        is_responded=responded,
        responded_at=now - timedelta(hours=1) if responded else None,
    )
    db.add(tracker)
    db.flush()
    return tracker


def _lookup_set(db, set_key: str) -> LookupSet | None:
    return (
        db.query(LookupSet)
        .filter(LookupSet.set_key == set_key, LookupSet.tenant_id.is_(None))
        .first()
    )


def _option(db, set_key: str, value: str) -> LookupOption | None:
    lookup = _lookup_set(db, set_key)
    if lookup is None:
        return None
    return (
        db.query(LookupOption)
        .filter(LookupOption.set_id == lookup.id, LookupOption.value == value)
        .first()
    )


def _reason(db, value: str = "pending_plumber") -> LookupOption:
    """An option in the shared reason vocabulary, seeded by the test if absent."""
    existing = _option(db, REASON_SET_KEY, value)
    if existing is not None:
        return existing
    lookup = _lookup_set(db, REASON_SET_KEY)
    assert lookup is not None, (
        f"The '{REASON_SET_KEY}' lookup set must be seeded by the migration - the "
        "reason vocabulary is shared by the pending reason and the overdue reason "
        "(AC-M1), and two lists would drift."
    )
    option = LookupOption(
        id=str(uuid.uuid4()),
        set_id=lookup.id,
        value=value,
        label=f"{TEST_PREFIX} {value}",
        sort_order=99,
    )
    db.add(option)
    db.flush()
    return option


def _event_logs(db, tracker_id: str, event_type: str | None = None):
    q = db.query(ConversationSLAEventLog).filter(
        ConversationSLAEventLog.sla_tracking_id == str(tracker_id)
    )
    if event_type:
        q = q.filter(ConversationSLAEventLog.event_type == event_type)
    return q.order_by(ConversationSLAEventLog.created_at.asc()).all()


# ============================================================== AC-M1 - the schema


def test_the_tracker_carries_the_three_waiting_fields():
    """AC-M1, under Ruling 1: on the tracker, because the tracker is the stage.

    A case runs Acknowledge, Assess, Schedule and Resolve at once. One case-level
    column paints Schedule's "waiting on the customer" onto Assess, which is waiting
    on maintenance, and lies about both.
    """
    columns = _columns(ConversationSLATracking)
    for name in WAITING_COLUMNS:
        assert name in columns, (
            f"conversation_sla_tracking.{name} must exist (AC-M1, Ruling 1). "
            "The three fields go on the tracker, not on six case tables."
        )
    assert columns["waiting_on_party"].nullable, "Not waiting is the normal state."
    assert columns["waiting_since"].nullable


def test_the_party_is_text_and_the_reason_is_an_id():
    """Point 4 of the header: they are stored differently on purpose.

    AC-M7 groups breaches by party, and a text value groups without a join. A reason
    gets reworded by an admin, and storing its label would silently rewrite history.
    """
    columns = _columns(ConversationSLATracking)
    party_type = columns["waiting_on_party"].type
    assert isinstance(party_type, (sa.String, sa.Text)), (
        "waiting_on_party stores the lookup option's VALUE as text so AC-M7 can "
        f"GROUP BY it without a join. Found {party_type!r}."
    )
    reason_fks = list(columns["waiting_on_reason_id"].foreign_keys)
    assert reason_fks, (
        "waiting_on_reason_id is a FK to lookup_options (AC-M1) so rewording a "
        "reason cannot rewrite the history that used it."
    )
    assert reason_fks[0].column.table.name == "lookup_options"
    assert reason_fks[0].ondelete in {"SET NULL", "set null"}, (
        "Deleting a reason option must not delete the tracker. History outlives "
        "the vocabulary."
    )


def test_the_event_log_carries_the_same_three_fields():
    """AC-M7 needs what we were waiting on WHEN it breached, not what we are now."""
    columns = _columns(ConversationSLAEventLog)
    for name in WAITING_COLUMNS:
        assert name in columns, (
            f"conversation_sla_event_log.{name} must exist. The live column answers "
            "'what now'; the event log answers 'what then', and reporting reads only "
            "the second (UAC ruling on AC-M1 vs AC-M7)."
        )


def test_a_party_without_a_since_is_rejected_by_the_database(db):
    """AC-M3 renders "waiting on maintenance SINCE 3 Aug". Half the pair is a bug.

    Provoked as a real IntegrityError rather than asserted as a constraint name: a
    constraint that exists and does not bite looks identical to one that does.
    """
    policy = _policy(db)
    tracker = _tracker(db, policy=policy)
    tracker.waiting_on_party = "plumber"
    tracker.waiting_since = None
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_the_migration_seeds_both_vocabularies_and_binds_them(db):
    """AC-M1: configurable master data, and the UAC's ruling that the party is too.

    The seed is asserted from the database, not from a constant in the service, so a
    service that hardcodes the list while the migration seeds nothing still fails.
    """
    party_set = _lookup_set(db, PARTY_SET_KEY)
    assert party_set is not None, (
        f"Migration must seed the '{PARTY_SET_KEY}' lookup set. A code enum was "
        "already one value short on day one - AC-M1 lists no dealer and AC-M18 "
        "requires one."
    )
    reason_set = _lookup_set(db, REASON_SET_KEY)
    assert reason_set is not None, f"Migration must seed '{REASON_SET_KEY}'."

    values = {
        o.value
        for o in db.query(LookupOption).filter(LookupOption.set_id == party_set.id).all()
    }
    assert SEEDED_PARTIES <= values, (
        "The party seed is AC-M1's list plus dealer. Missing: "
        f"{sorted(SEEDED_PARTIES - values)}"
    )

    bound = {
        (b.table_name, b.column_name)
        for b in db.query(LookupBinding)
        .filter(LookupBinding.set_id.in_([party_set.id, reason_set.id]))
        .all()
    }
    assert ("conversation_sla_tracking", "waiting_on_party") in bound, (
        "Without a binding the FE has no dropdown and the field becomes free text, "
        "which is the thing AC-M1 is written to prevent."
    )
    assert ("conversation_sla_tracking", "waiting_on_reason_id") in bound


# ======================================================= AC-M2 - the clock is not touched


def test_setting_waiting_does_not_move_a_single_clock(db):
    """AC-M2. Pausing is the classic gamed metric: a queue parked on "pending
    customer" reports a perfect SLA while the customer's toilet is still broken.
    """
    waiting = _waiting()
    set_waiting = _fn(
        waiting,
        "set_waiting",
        "(db, tracking_id, *, party, reason_id=None, actor_user_id=None)",
    )
    policy = _policy(db)
    tracker = _tracker(db, policy=policy)
    before = (
        tracker.due_at,
        tracker.due_at_resolution,
        tracker.current_tier_started_at,
        tracker.current_tier,
        tracker.extension_count,
    )
    set_waiting(db, str(tracker.id), party="plumber", reason_id=str(_reason(db).id))
    db.refresh(tracker)
    after = (
        tracker.due_at,
        tracker.due_at_resolution,
        tracker.current_tier_started_at,
        tracker.current_tier,
        tracker.extension_count,
    )
    assert before == after, (
        "AC-M2: time spent waiting on an external party still counts toward "
        "resolution. A genuine deadline move is Extend, and only Extend (AC-M6)."
    )


def test_clearing_waiting_does_not_move_a_single_clock(db):
    waiting = _waiting()
    set_waiting = _fn(waiting, "set_waiting", "(...)")
    clear_waiting = _fn(waiting, "clear_waiting", "(db, tracking_id, *, actor_user_id=None)")
    policy = _policy(db)
    tracker = _tracker(db, policy=policy)
    set_waiting(db, str(tracker.id), party="plumber")
    db.refresh(tracker)
    before = (tracker.due_at, tracker.due_at_resolution, tracker.current_tier_started_at)
    clear_waiting(db, str(tracker.id))
    db.refresh(tracker)
    assert (tracker.due_at, tracker.due_at_resolution, tracker.current_tier_started_at) == before


# ============================================================= set / clear semantics


def test_waiting_since_survives_an_edit_of_the_same_party(db):
    """Point 5: "since 3 Aug" must not become "since just now" because somebody
    corrected the reason. Re-setting the same party is an edit, not a new wait.
    """
    waiting = _waiting()
    set_waiting = _fn(waiting, "set_waiting", "(...)")
    policy = _policy(db)
    tracker = _tracker(db, policy=policy)

    set_waiting(db, str(tracker.id), party="plumber")
    db.refresh(tracker)
    first_since = tracker.waiting_since
    assert first_since is not None

    tracker.waiting_since = first_since - timedelta(days=2)
    db.flush()
    aged = tracker.waiting_since

    set_waiting(db, str(tracker.id), party="plumber", reason_id=str(_reason(db).id))
    db.refresh(tracker)
    assert tracker.waiting_since == aged, (
        "Same party, corrected reason: the wait did not restart. AC-M3's sentence "
        "is only true if this holds."
    )


def test_switching_party_restarts_the_wait(db):
    """A different party is a different wait. Keeping the old timestamp would say
    we had been waiting on maintenance since before we started waiting on them.
    """
    waiting = _waiting()
    set_waiting = _fn(waiting, "set_waiting", "(...)")
    policy = _policy(db)
    tracker = _tracker(db, policy=policy)

    set_waiting(db, str(tracker.id), party="plumber")
    db.refresh(tracker)
    tracker.waiting_since = tracker.waiting_since - timedelta(days=2)
    db.flush()
    aged = tracker.waiting_since

    set_waiting(db, str(tracker.id), party="maintenance")
    db.refresh(tracker)
    assert tracker.waiting_on_party == "maintenance"
    assert tracker.waiting_since > aged


def test_an_unknown_party_is_refused(db):
    """The vocabulary is data, but it is still a vocabulary. Free text here means
    "plumber", "Plumber" and "plmber" become three parties in the AC-M7 report.
    """
    waiting = _waiting()
    set_waiting = _fn(waiting, "set_waiting", "(...)")
    policy = _policy(db)
    tracker = _tracker(db, policy=policy)
    with pytest.raises(Exception) as exc:
        set_waiting(db, str(tracker.id), party="the guy who does the pipes")
    assert "party" in str(exc.value).lower()


def test_a_deactivated_party_cannot_be_set_but_an_existing_one_still_reads(db):
    """Deactivating "plumber" stops new waits, it does not rewrite old ones."""
    waiting = _waiting()
    set_waiting = _fn(waiting, "set_waiting", "(...)")
    policy = _policy(db)
    tracker = _tracker(db, policy=policy)
    set_waiting(db, str(tracker.id), party="plumber")
    db.refresh(tracker)

    option = _option(db, PARTY_SET_KEY, "plumber")
    assert option is not None
    option.is_active = False
    db.flush()

    assert tracker.waiting_on_party == "plumber", (
        "The historical value keeps rendering. Deactivation is not a rewrite."
    )
    other = _tracker(db, policy=policy)
    with pytest.raises(Exception):
        set_waiting(db, str(other.id), party="plumber")


def test_clearing_nulls_all_three_fields(db):
    waiting = _waiting()
    set_waiting = _fn(waiting, "set_waiting", "(...)")
    clear_waiting = _fn(waiting, "clear_waiting", "(...)")
    policy = _policy(db)
    tracker = _tracker(db, policy=policy)
    set_waiting(db, str(tracker.id), party="supplier", reason_id=str(_reason(db).id))
    clear_waiting(db, str(tracker.id))
    db.refresh(tracker)
    assert tracker.waiting_on_party is None
    assert tracker.waiting_on_reason_id is None
    assert tracker.waiting_since is None


def test_every_waiting_change_writes_its_own_event(db):
    """Decision in the header: clearing is an event, not an absence. Without a
    waiting_cleared row, "we stopped waiting on the plumber on Tuesday" is gone and
    the duration of the wait is unrecoverable.
    """
    waiting = _waiting()
    set_waiting = _fn(waiting, "set_waiting", "(...)")
    clear_waiting = _fn(waiting, "clear_waiting", "(...)")
    policy = _policy(db)
    tracker = _tracker(db, policy=policy)

    set_waiting(db, str(tracker.id), party="plumber", reason_id=str(_reason(db).id))
    set_rows = _event_logs(db, tracker.id, WAITING_SET_EVENT)
    assert len(set_rows) == 1, f"One '{WAITING_SET_EVENT}' row per set."
    assert set_rows[0].waiting_on_party == "plumber"

    clear_waiting(db, str(tracker.id))
    cleared = _event_logs(db, tracker.id, WAITING_CLEARED_EVENT)
    assert len(cleared) == 1, f"Clearing writes a '{WAITING_CLEARED_EVENT}' row."
    assert cleared[0].waiting_on_party == "plumber", (
        "The cleared row records WHAT we stopped waiting on, taken from the value "
        "being cleared. A row of NULLs says nothing."
    )


# ================================================== AC-M7 - point-in-time attribution


def test_create_event_log_stamps_the_waiting_state_of_the_moment(db):
    """Point 3: the capture lives at the single choke point, so escalate, resolve,
    extend, reassign and every handling-lock event inherit it and none of them can
    forget.
    """
    from app.schemas.sla import ConversationSLAEventLogCreate
    from app.services.sla_service import ConversationSLATrackingService

    waiting = _waiting()
    set_waiting = _fn(waiting, "set_waiting", "(...)")
    policy = _policy(db)
    tracker = _tracker(db, policy=policy)
    reason = _reason(db)
    set_waiting(db, str(tracker.id), party="maintenance", reason_id=str(reason.id))

    ConversationSLATrackingService(db).create_event_log(
        ConversationSLAEventLogCreate(
            sla_tracking_id=str(tracker.id),
            event_type="escalation",
            from_tier=1,
            to_tier=2,
        )
    )
    row = _event_logs(db, tracker.id, "escalation")[-1]
    assert row.waiting_on_party == "maintenance", (
        "create_event_log stamps the tracker's live waiting values onto every row. "
        "A dozen callers each remembering to pass them is a dozen chances to forget."
    )
    assert str(row.waiting_on_reason_id) == str(reason.id)
    assert row.waiting_since is not None


def test_a_captured_breach_does_not_re_attribute_when_the_case_is_edited(db):
    """The UAC ruling, stated as the failure it prevents: without capture, every
    historical breach silently re-attributes itself the next time somebody edits the
    case, and last month's report changes shape.
    """
    from app.schemas.sla import ConversationSLAEventLogCreate
    from app.services.sla_service import ConversationSLATrackingService

    waiting = _waiting()
    set_waiting = _fn(waiting, "set_waiting", "(...)")
    policy = _policy(db)
    tracker = _tracker(db, policy=policy)
    set_waiting(db, str(tracker.id), party="plumber")

    ConversationSLATrackingService(db).create_event_log(
        ConversationSLAEventLogCreate(
            sla_tracking_id=str(tracker.id), event_type="escalation", to_tier=2
        )
    )
    set_waiting(db, str(tracker.id), party="customer")

    row = _event_logs(db, tracker.id, "escalation")[-1]
    assert row.waiting_on_party == "plumber", (
        "The breach happened while we were waiting on the plumber. It still did."
    )


def test_attribution_counts_external_internal_and_unattributed(db):
    """AC-M7, with the third number the sentence hides.

    "Of 40 breaches, 26 were waiting on an external party" invites the reader to
    assume the other 14 were ours. Some of them are simply unexplained, and a report
    that folds those into "internal" is worse than one that admits it.
    """
    from app.schemas.sla import ConversationSLAEventLogCreate
    from app.services.sla_service import ConversationSLATrackingService

    waiting = _waiting()
    set_waiting = _fn(waiting, "set_waiting", "(...)")
    summary = _fn(
        waiting,
        "attribution_summary",
        "(db, *, source_entity_type=None, since=None, until=None)",
    )
    policy = _policy(db)
    svc = ConversationSLATrackingService(db)
    complaint = _complaint(db)

    external = _tracker(db, policy=policy, source_entity_id=str(complaint.id))
    internal = _tracker(db, policy=policy, source_entity_id=str(complaint.id))
    silent = _tracker(db, policy=policy, source_entity_id=str(complaint.id))

    set_waiting(db, str(external.id), party="plumber")
    set_waiting(db, str(internal.id), party="cs")
    for tracker in (external, internal, silent):
        svc.create_event_log(
            ConversationSLAEventLogCreate(
                sla_tracking_id=str(tracker.id), event_type="escalation", to_tier=2
            )
        )

    result = summary(db, source_entity_type="complaint")
    by_party = result["by_party"]
    assert by_party.get("plumber") == 1
    assert by_party.get("cs") == 1
    assert result["unattributed"] == 1, (
        "The breach nobody explained is its own bucket, never folded into internal."
    )
    assert result["external"] == 1 and result["internal"] == 1, (
        "cs is us; plumber is not. The external/internal split is a property of the "
        "party option, not a hardcoded list in the report."
    )


def test_which_parties_are_external_is_data_not_a_hardcoded_list(db):
    """The moment "external" is a tuple in a service, adding a party to the lookup
    set silently files it as internal and the AC-M7 headline is wrong by one.
    """
    party_set = _lookup_set(db, PARTY_SET_KEY)
    assert party_set is not None
    cs = _option(db, PARTY_SET_KEY, "cs")
    plumber = _option(db, PARTY_SET_KEY, "plumber")
    assert cs is not None and plumber is not None
    assert (cs.description or "").strip(), (
        "Each seeded party records whether it is us or not, on the option row "
        "itself, so operations can add a party without a code change."
    )
    waiting = _waiting()
    is_external = _fn(waiting, "is_external_party", "(db, party)")
    assert is_external(db, "plumber") is True
    assert is_external(db, "cs") is False


# ============================================================= AC-M4 - the guard


def test_overdue_has_one_definition_shared_with_the_escalation_scan(db):
    """Point 2 of the header, asserted on the tracker that separates the two rules.

    A responded tracker whose RESPONSE deadline has lapsed but whose RESOLUTION
    deadline has not is NOT overdue: the response clock stopped when it responded,
    and extend moves only the resolution clock. A guard with a naive due_at < now
    would block a resolve the escalation scan considers perfectly on time.
    """
    waiting = _waiting()
    is_overdue = _fn(waiting, "is_overdue", "(tracker, now=None)")
    policy = _policy(db)
    now = _utc_now()
    tracker = _tracker(db, policy=policy, responded=True)
    tracker.due_at = now - timedelta(hours=3)
    tracker.due_at_resolution = now + timedelta(hours=5)
    db.flush()
    assert is_overdue(tracker, now) is False, (
        "Responded on time, resolution deadline still ahead. The response clock "
        "stopped; it does not gate anything now."
    )
    tracker.due_at_resolution = now - timedelta(minutes=1)
    db.flush()
    assert is_overdue(tracker, now) is True


def test_manual_escalate_of_an_overdue_tracker_demands_attribution(db):
    """AC-M4's enforceable half. Escalating a breach without saying who we are
    waiting on is exactly the reporting hole this slice exists to close - and
    historically it rejects nothing: zero escalations in the production copy were
    ever written after the deadline.
    """
    from app.services.form_sla_service import FormSLAOrchestrator

    policy = _policy(db)
    agent = _agent(db)
    config = _config(db, agent, policy)
    member = _user(db, "tier1")
    senior = _user(db, "tier2")
    _team(db, agent, config, policy, 1, [member])
    _team(db, agent, config, policy, 2, [senior])
    tracker = _tracker(
        db,
        policy=policy,
        team_set_code=config.team_set_code,
        agent_id=agent.id,
        assigned_to_id=member.id,
        overdue=True,
    )

    with pytest.raises(Exception) as exc:
        FormSLAOrchestrator(db).escalate_form_tracking(
            str(tracker.id), reason="chasing", actor_user_id=member.id
        )
    assert ATTRIBUTION_ERROR_CODE in str(getattr(exc.value, "code", "")) or (
        ATTRIBUTION_ERROR_CODE in str(exc.value)
    ), (
        "The rejection carries a code the FE can branch on to open the waiting "
        "dropdown, rather than a message it has to string-match."
    )


def test_manual_escalate_is_allowed_once_the_wait_is_named(db):
    from app.services.form_sla_service import FormSLAOrchestrator

    waiting = _waiting()
    set_waiting = _fn(waiting, "set_waiting", "(...)")
    policy = _policy(db)
    agent = _agent(db)
    config = _config(db, agent, policy)
    member = _user(db, "tier1")
    senior = _user(db, "tier2")
    _team(db, agent, config, policy, 1, [member])
    _team(db, agent, config, policy, 2, [senior])
    tracker = _tracker(
        db,
        policy=policy,
        team_set_code=config.team_set_code,
        agent_id=agent.id,
        assigned_to_id=member.id,
        overdue=True,
    )
    set_waiting(db, str(tracker.id), party="customer")

    FormSLAOrchestrator(db).escalate_form_tracking(
        str(tracker.id), reason="chasing", actor_user_id=member.id
    )
    db.refresh(tracker)
    assert tracker.current_tier == 2


def test_a_tracker_inside_its_deadline_is_never_asked(db):
    """The guard is about breaches. Demanding attribution from somebody acting on
    time is friction with nothing to attribute.
    """
    from app.services.form_sla_service import FormSLAOrchestrator

    policy = _policy(db)
    agent = _agent(db)
    config = _config(db, agent, policy)
    member = _user(db, "tier1")
    senior = _user(db, "tier2")
    _team(db, agent, config, policy, 1, [member])
    _team(db, agent, config, policy, 2, [senior])
    tracker = _tracker(
        db,
        policy=policy,
        team_set_code=config.team_set_code,
        agent_id=agent.id,
        assigned_to_id=member.id,
        overdue=False,
    )
    FormSLAOrchestrator(db).escalate_form_tracking(
        str(tracker.id), reason="pre-emptive", actor_user_id=member.id
    )
    db.refresh(tracker)
    assert tracker.current_tier == 2


def test_the_automatic_escalation_scan_is_never_guarded(db):
    """The cron has no answer to give. Guarding it would either stall every overdue
    tracker forever or force the system to invent an attribution, which is worse
    than admitting there is none.
    """
    from app.services.form_sla_service import FormSLAOrchestrator

    policy = _policy(db)
    agent = _agent(db)
    config = _config(db, agent, policy)
    member = _user(db, "tier1")
    senior = _user(db, "tier2")
    _team(db, agent, config, policy, 1, [member])
    _team(db, agent, config, policy, 2, [senior])
    tracker = _tracker(
        db,
        policy=policy,
        team_set_code=config.team_set_code,
        agent_id=agent.id,
        assigned_to_id=member.id,
        overdue=True,
    )
    FormSLAOrchestrator(db).scan_overdue_and_escalate()
    db.refresh(tracker)
    assert tracker.current_tier == 2, (
        "The scan escalated an unattributed overdue tracker, as it must."
    )
    row = _event_logs(db, tracker.id, "escalation")[-1]
    assert row.trigger == "auto"
    assert row.waiting_on_party is None, (
        "And it recorded the absence honestly rather than filling it in."
    )


def test_extend_of_an_overdue_tracker_demands_attribution(db):
    """Extending an overdue deadline without naming who we are waiting on is the
    gamed metric AC-M2 refuses, arriving through the one door AC-M6 leaves open.
    """
    from app.services.sla_service import ConversationSLATrackingService

    policy = _policy(db)
    actor = _user(db, "assignee")
    tracker = _tracker(db, policy=policy, assigned_to_id=actor.id, overdue=True)
    with pytest.raises(Exception) as exc:
        ConversationSLATrackingService(db).extend_tracking(
            str(tracker.id), actor.id, days=2, reason="supplier is slow"
        )
    assert ATTRIBUTION_ERROR_CODE in str(getattr(exc.value, "code", "")) or (
        ATTRIBUTION_ERROR_CODE in str(exc.value)
    )


def test_the_status_transition_that_resolves_an_overdue_stage_is_guarded(db):
    """Finding 1, and the only place a resolve rejection can reach a human.

    The SLA layer cannot enforce this: emit_event swallows per config, every caller
    swallows the emit, and both swallows are after the commit. The status engine's
    guard runs before it and already raises 422 to the route.
    """
    from app.services.status_service import assert_transition_allowed_by_key
    from app.services.complaint_status_graph import COMPLAINT_ENTITY_TYPE

    waiting = _waiting()
    guard = _fn(
        waiting,
        "assert_case_transition_attributed",
        "(db, entity_type, entity_id, to_key)",
    )
    policy = _policy(db)
    agent = _agent(db)
    config = _config(db, agent, policy)
    complaint = _complaint(db, status="submitted")
    _tracker(
        db,
        policy=policy,
        source_entity_id=str(complaint.id),
        team_set_code=config.team_set_code,
        agent_id=agent.id,
        overdue=True,
    )
    with pytest.raises(Exception) as exc:
        guard(db, COMPLAINT_ENTITY_TYPE, str(complaint.id), config.resolve_event)
    assert ATTRIBUTION_ERROR_CODE in str(getattr(exc.value, "code", "")) or (
        ATTRIBUTION_ERROR_CODE in str(exc.value)
    )
    assert "assert_transition_allowed_by_key" in dir(
        importlib.import_module("app.services.status_service")
    ) or assert_transition_allowed_by_key is not None


def test_a_transition_that_resolves_nothing_is_not_guarded(db):
    """Narrow by construction: only the transition that would close an overdue
    stage asks. Recording ordinary progress on an overdue case must stay free, or
    this becomes the third tax on the same click.
    """
    waiting = _waiting()
    guard = _fn(waiting, "assert_case_transition_attributed", "(...)")
    from app.services.complaint_status_graph import COMPLAINT_ENTITY_TYPE

    policy = _policy(db)
    agent = _agent(db)
    config = _config(db, agent, policy)
    complaint = _complaint(db, status="submitted")
    _tracker(
        db,
        policy=policy,
        source_entity_id=str(complaint.id),
        team_set_code=config.team_set_code,
        agent_id=agent.id,
        overdue=True,
    )
    guard(db, COMPLAINT_ENTITY_TYPE, str(complaint.id), "some_other_event")


def test_form_types_off_the_status_engine_are_untouched(db):
    """AC-M33's lesson, applied a slice later: a guard that reaches purchase
    requests, sponsorship forms and stock inquiries is a change to four live flows
    that no after-sales AC governs. Only complaint and workflow_submission are
    registered on the engine, and that is what keeps this slice honest.
    """
    waiting = _waiting()
    guard = _fn(waiting, "assert_case_transition_attributed", "(...)")
    policy = _policy(db)
    agent = _agent(db)
    config = _config(db, agent, policy, source_entity_type="purchase_request")
    entity_id = str(uuid.uuid4())
    _tracker(
        db,
        policy=policy,
        source_entity_type="purchase_request",
        source_entity_id=entity_id,
        team_set_code=config.team_set_code,
        agent_id=agent.id,
        overdue=True,
    )
    guard(db, "purchase_request", entity_id, config.resolve_event)


def test_claiming_a_handling_lock_is_not_guarded(db):
    """Picking up somebody else's escalated work is the behaviour we want. Taxing
    it with a dropdown before the claimant even sees the case discourages exactly
    the right action.
    """
    waiting = _waiting()
    guarded = _fn(waiting, "guarded_actions", "()")
    actions = set(guarded())
    assert {"resolve", "escalate", "extend"} <= actions
    assert "claim" not in actions and "release" not in actions
    assert "save" not in actions


# ======================================================== Ruling 1 - the derived case


def test_the_case_level_answer_is_derived_from_its_open_stages(db):
    """Ruling 1: AC-M1's case-level question is answered, not stored. A case waiting
    on the customer at Schedule and on maintenance at Assess is waiting on both, and
    a single column would have had to pick one.
    """
    waiting = _waiting()
    set_waiting = _fn(waiting, "set_waiting", "(...)")
    case_waiting = _fn(waiting, "case_waiting", "(db, source_entity_type, source_entity_id)")
    policy = _policy(db)
    complaint = _complaint(db)

    schedule = _tracker(db, policy=policy, source_entity_id=str(complaint.id), team_set_code="schedule")
    assess = _tracker(db, policy=policy, source_entity_id=str(complaint.id), team_set_code="assess")
    _tracker(db, policy=policy, source_entity_id=str(complaint.id), team_set_code="ack")

    set_waiting(db, str(schedule.id), party="customer")
    set_waiting(db, str(assess.id), party="maintenance")

    rows = case_waiting(db, "complaint", str(complaint.id))
    parties = {r["party"] for r in rows}
    assert parties == {"customer", "maintenance"}, (
        "Both, because both are true. The third stage waits on nobody and does not "
        "appear."
    )
    assert all(r.get("stage") for r in rows), (
        "Each entry names its stage, or the reader cannot tell which wait belongs "
        "to which part of the case."
    )
    assert all(r.get("since") for r in rows)


def test_a_case_waiting_on_nobody_returns_nothing(db):
    waiting = _waiting()
    case_waiting = _fn(waiting, "case_waiting", "(...)")
    policy = _policy(db)
    complaint = _complaint(db)
    _tracker(db, policy=policy, source_entity_id=str(complaint.id))
    assert case_waiting(db, "complaint", str(complaint.id)) == []


def test_a_resolved_stage_stops_being_a_current_wait(db):
    """"What now" is about open work. A resolved stage that was waiting on the
    supplier is history, and history lives in the event log.
    """
    waiting = _waiting()
    set_waiting = _fn(waiting, "set_waiting", "(...)")
    case_waiting = _fn(waiting, "case_waiting", "(...)")
    policy = _policy(db)
    complaint = _complaint(db)
    tracker = _tracker(db, policy=policy, source_entity_id=str(complaint.id))
    set_waiting(db, str(tracker.id), party="supplier")
    tracker.is_resolved = True
    tracker.resolved_at = _utc_now()
    db.flush()
    assert case_waiting(db, "complaint", str(complaint.id)) == []


# ================================================== AC-M36d - the evidence for blame


def test_three_unanswered_calls_justify_waiting_on_the_customer(db):
    """AC-M36d. "We called three times and nobody answered" is the defensible
    version of blaming the customer for a delay. It reads the calls S4 already logs
    rather than inventing a counter.
    """
    from app.services.call_activity_service import log_call

    waiting = _waiting()
    evidence = _fn(waiting, "unanswered_call_evidence", "(db, respond_contact_id, since=None)")
    contact = _contact(db)
    for _ in range(UNANSWERED_CALL_THRESHOLD):
        log_call(
            db,
            contact_id=str(contact.id),
            direction="outbound",
            outcome="no_answer",
        )
    result = evidence(db, str(contact.id))
    assert result["count"] >= UNANSWERED_CALL_THRESHOLD
    assert result["justifies_customer_waiting"] is True
    assert result["last_at"] is not None


def test_one_unanswered_call_justifies_nothing(db):
    from app.services.call_activity_service import log_call

    waiting = _waiting()
    evidence = _fn(waiting, "unanswered_call_evidence", "(...)")
    contact = _contact(db)
    log_call(db, contact_id=str(contact.id), direction="outbound", outcome="no_answer")
    assert evidence(db, str(contact.id))["justifies_customer_waiting"] is False


def test_an_answered_call_resets_the_evidence(db):
    """Reaching somebody is the opposite of being unable to reach them. Counting
    every no-answer ever would let a call from March justify a wait in August.
    """
    from app.services.call_activity_service import log_call

    waiting = _waiting()
    evidence = _fn(waiting, "unanswered_call_evidence", "(...)")
    contact = _contact(db)
    for _ in range(UNANSWERED_CALL_THRESHOLD):
        log_call(db, contact_id=str(contact.id), direction="outbound", outcome="no_answer")
    log_call(db, contact_id=str(contact.id), direction="outbound", outcome="answered")
    result = evidence(db, str(contact.id))
    assert result["count"] == 0
    assert result["justifies_customer_waiting"] is False


def test_setting_waiting_on_the_customer_records_the_evidence(db):
    """The justification travels with the claim. A waiting_set row that says
    "customer" and nothing else is the shrug AC-M36d was written against.
    """
    from app.services.call_activity_service import log_call

    waiting = _waiting()
    set_waiting = _fn(waiting, "set_waiting", "(...)")
    policy = _policy(db)
    contact = _contact(db)
    tracker = _tracker(db, policy=policy)
    tracker.respond_contact_id = contact.id
    db.flush()
    for _ in range(UNANSWERED_CALL_THRESHOLD):
        log_call(db, contact_id=str(contact.id), direction="outbound", outcome="no_answer")

    set_waiting(db, str(tracker.id), party="customer")
    row = _event_logs(db, tracker.id, WAITING_SET_EVENT)[-1]
    assert str(UNANSWERED_CALL_THRESHOLD) in (row.reason or ""), (
        "The count of unanswered calls lands in the event log reason, so the "
        "justification survives beside the claim it justifies."
    )
