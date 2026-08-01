"""F2a gate - the form-SLA machinery reaches ``workflow_submission``.

F1 put a submission's status in the status engine and F1a made a deriving
definition's header follow its lines. Neither of them told the SLA machinery that
``workflow_submission`` exists, so a submission has no clock, no assignee, no
escalation and no handling lock. F2a is that wiring, and almost all of its risk is
in four places that a naive implementation gets wrong in a way nothing shouts about:

1. **The type tuple is DUPLICATED.** ``FORM_SLA_TYPES`` in
   ``app/services/form_sla_service.py`` and ``_FORM_SLA_TYPES`` in
   ``app/schemas/sla.py`` list the same five strings. Adding a type to only one
   passes every service call and then 422s at the Pydantic boundary, which reads as
   a broken API rather than a half-finished change.
2. **Derivation is the only status writer for a deriving definition.** An SLA that
   hooks ``apply_transition`` alone would never start or resolve a clock on exactly
   the forms after-sales needs, because those forms never move their header by hand.
3. **``advance_on_event`` defaults to NULL, meaning "any resolve advances".** Leave
   it NULL and a REJECTION spawns the next stage. That is a live defect in the
   existing configs, so it is asserted here as behaviour, not as config shape.
4. **"Escalated" is ``escalated_at IS NOT NULL``, never ``current_tier > 1``.** A
   stage may legitimately START above tier 1, and a tier-based check locks a form
   nobody ever escalated and disables every CTA on it.

Plus the shared-table hazard: ``conversation_sla_tracking`` carries BOTH n8n
conversation rows and form stage rows, discriminated only by
``source_entity_type``. A sixth form type widens the set of rows a careless
contact-keyed conversation query would falsely match, so the scope filter is
re-asserted against the new type.

Every test traces to an AC in
``documentation/plans/forms-platform/forms-platform-acceptance-criteria.md``,
Group F2a.

Run: venv/bin/pytest tests/test_workflow_submission_sla.py -q -p no:randomly
"""
from __future__ import annotations

import importlib
import importlib.util
import uuid
from collections import namedtuple
from datetime import timedelta

import pytest

from app.models.access import (
    AccessAgent,
    AgentTeam,
    RespondContact,
    Team,
    TeamMember,
)
from app.models.sla import (
    ConversationSLATracking,
    FormSLAConfig,
    SLAPolicy,
    SLAPolicyTier,
)
from app.models.user import SystemSetting, User
from app.models.workflow_forms import (
    WorkflowFormDefinition,
    WorkflowFormVersion,
    WorkflowSubmissionLine,
)
from app.form_engine.schemas import FORM_SCHEMA_VERSION
from app.schemas.sla import FormSLAConfigCreate
from app.services import handling_lock_service
from app.services.error_handler import AppException
from app.services.form_sla_service import FORM_SLA_TYPES, _utc_naive_now
from app.services.sla_service import (
    ConversationSLATrackingService,
    conversation_tracking_scope,
)
from app.services.status_service import resolve_graph
from app.services.workflow_forms_service import WorkflowFormsService
from app.services.workflow_submission_line_status_graph import (
    WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE,
    register_workflow_submission_line_status_entity,
    seed_workflow_submission_line_status_graph,
)
from app.services.workflow_submission_status_graph import (
    WORKFLOW_SUBMISSION_ENTITY_TYPE,
    WORKFLOW_SUBMISSION_STATUS_KEYS,
    register_workflow_submission_status_entity,
    seed_workflow_submission_status_graph,
)
from app.status_engine import registry as status_registry

from ._pg_fixture import TEST_PREFIX, blank_session, unique_code

# The one module F2a is expected to add: it owns the stage seed AND the
# status-event naming, so the seeded config's ``start_event`` and the emitter that
# fires it cannot drift apart.
SLA_MODULE = "app.services.workflow_submission_sla"

# The repeater every submission in this file files its lines under.
LINE_GROUP = "items"

# A deriving definition's declared pair. ``draft`` is the default graph's INITIAL
# rung (``assert_derivation_config`` requires that) and ``submitted`` is NOT terminal
# (it requires that too), so no header fork is needed and the pair is a legal one.
OPEN_KEY = "draft"
RESOLVED_KEY = "submitted"

FORM_DOC = {
    "schemaVersion": FORM_SCHEMA_VERSION,
    "pages": [
        {
            "id": "p1",
            "title": "Details",
            "sections": [
                {
                    "id": "s1",
                    "title": "Main",
                    "fields": [
                        {
                            "id": "f1",
                            "type": "text",
                            "key": "title",
                            "label": "Title",
                            "required": True,
                        },
                        {
                            "id": "f2",
                            "type": "repeater",
                            "key": LINE_GROUP,
                            "label": "Items",
                            "repeater": {
                                "fields": [
                                    {
                                        "id": "sf1",
                                        "type": "text",
                                        "key": "model",
                                        "label": "Model",
                                    }
                                ]
                            },
                        },
                    ],
                }
            ],
        }
    ],
}

Chain = namedtuple("Chain", "agent_id first second policy_first policy_second users")
Stage = namedtuple("Stage", "config team_set team_id member_id")


# --------------------------------------------------------------------- fixtures


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _isolate_registry():
    """The status registry is process-global; snapshot and restore it."""
    saved = dict(status_registry._REGISTRY)
    yield
    status_registry._REGISTRY.clear()
    status_registry._REGISTRY.update(saved)


@pytest.fixture(autouse=True)
def notifications(monkeypatch):
    """Record every notification instead of sending one.

    This is the observable AC-F2a-4 is about: the duplicate-assignment bug was two
    "sla_assigned" WhatsApp messages for one form, so the assertion is on the number
    of assignment notifications, not on an internal call count.
    """
    from app.services.notification_service import NotificationService

    sent: list[dict] = []

    def _record(self, **kwargs):
        sent.append(kwargs)
        return None

    monkeypatch.setattr(
        NotificationService, "create_with_channel_preferences", _record
    )
    monkeypatch.setattr(
        NotificationService, "create", lambda self, **kwargs: sent.append(kwargs)
    )
    return sent


@pytest.fixture(autouse=True)
def _no_queue(monkeypatch):
    """Resolving a tracker enqueues a Respond.io close on the worker. Not this
    file's subject, and a live Redis is not a test dependency."""
    import app.services.queue_service as queue_service

    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: None)
    yield


# ---------------------------------------------------------------------- helpers


def _sla_module(*, required: bool = True):
    """Import the module F2a adds, or fail with the contract it is missing."""
    if importlib.util.find_spec(SLA_MODULE) is None:
        if required:
            raise AssertionError(
                f"{SLA_MODULE} does not exist. F2a needs one module owning the "
                "workflow_submission SLA stage seed and the status-event naming, so "
                "the seeded config's events and the emitter that fires them cannot "
                "drift apart."
            )
        return None
    return importlib.import_module(SLA_MODULE)


def _event(status_key: str) -> str:
    """The SLA event name a submission's status move emits, per the convention F2a
    declares.

    Falls back to the bare status key when the module is absent, deliberately: the
    behavioural tests below must fail on the behaviour they are about (no clock
    started, no clock resolved) rather than all reporting the same missing import.
    The convention itself is pinned by
    ``test_the_status_event_naming_lives_in_one_place``.
    """
    module = _sla_module(required=False)
    fn = getattr(module, "submission_status_event", None) if module else None
    return fn(status_key) if callable(fn) else status_key


def _seed_graphs(db):
    """Both default graphs seeded, both entities registered."""
    seed_workflow_submission_status_graph(db)
    seed_workflow_submission_line_status_graph(db)
    db.flush()
    register_workflow_submission_status_entity()
    register_workflow_submission_line_status_entity()


def _header_graph(db, scope=None):
    return resolve_graph(db, WORKFLOW_SUBMISSION_ENTITY_TYPE, scope)


def _line_graph(db, scope=None):
    return resolve_graph(db, WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE, scope)


def _user(db, label: str) -> str:
    """A real ``users`` row. F1 gave the attribution columns foreign keys to
    ``users.id`` and Postgres enforces them, so an invented id aborts the
    transaction."""
    user_id = unique_code(label).lower()
    db.add(
        User(
            id=user_id,
            email=f"{user_id}@{TEST_PREFIX.lower()}.invalid",
            name=f"{TEST_PREFIX} {label}",
            status="ACTIVE",
        )
    )
    db.flush()
    return user_id


def _definition(db, *, derives: bool = False) -> WorkflowFormDefinition:
    declared = (
        {
            "derives_status_from_lines": True,
            "derived_open_status_key": OPEN_KEY,
            "derived_resolved_status_key": RESOLVED_KEY,
        }
        if derives
        else {}
    )
    definition = WorkflowFormDefinition(
        id=str(uuid.uuid4()),
        code=unique_code("wfdef").lower(),
        name=f"{unique_code('Form')} definition",
        draft_schema=FORM_DOC,
        **declared,
    )
    db.add(definition)
    db.flush()
    version = WorkflowFormVersion(
        id=str(uuid.uuid4()),
        definition_id=definition.id,
        version_number=1,
        schema=FORM_DOC,
    )
    db.add(version)
    db.flush()
    definition.published_version_id = version.id
    db.flush()
    return definition


def _submission(db, definition, *, rows: int = 0, user_id: str):
    lines = [
        {"line_group_id": LINE_GROUP, "row_data": {"model": f"{TEST_PREFIX}-{i}"}}
        for i in range(rows)
    ]
    return WorkflowFormsService(db).create_submission(
        definition.id, {"title": f"{TEST_PREFIX} answer"}, lines, user_id
    )


def _policy(db, stem: str, *, tiers=(1, 2)) -> str:
    policy_id = str(uuid.uuid4())
    code = unique_code(stem).upper()
    db.add(SLAPolicy(id=policy_id, code=code, name=code))
    for level in tiers:
        db.add(
            SLAPolicyTier(
                id=str(uuid.uuid4()),
                policy_id=policy_id,
                tier_level=level,
                tier_name=f"Tier {level}",
                response_hours=4,
                resolution_hours=24,
            )
        )
    db.flush()
    return policy_id


def _team(db, agent_id: str, team_set: str, tier: int, member_id: str) -> str:
    team_id = str(uuid.uuid4())
    db.add(Team(id=team_id, name=f"{TEST_PREFIX} {team_set} t{tier}"))
    db.flush()
    db.add(
        AgentTeam(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            code=team_set,
            team_id=team_id,
            tier=tier,
        )
    )
    db.add(
        TeamMember(
            id=str(uuid.uuid4()),
            team_id=team_id,
            user_id=member_id,
            include_in_round_robin=True,
        )
    )
    db.flush()
    return team_id


def _chain(db, *, advance_on_event: str | None = "APPROVED") -> Chain:
    """A two-stage ``workflow_submission`` SLA chain, shaped like the live complaint
    pipeline: stage one starts on ``submitted`` and resolves on approve OR reject;
    stage two is spawned by the chain and also declares ``approved`` as its own
    start event, exactly as ``complaint``'s customer_service stage does.

    That overlap is the point. It is the configuration under which the known
    duplicate-assignment bug fires, so the assignment count is only meaningful here.

    ``advance_on_event="APPROVED"`` is a sentinel resolved to the real event name
    below; pass ``None`` to reproduce the NULL default.
    """
    agent_id = str(uuid.uuid4())
    db.add(
        AccessAgent(
            id=agent_id, code=unique_code("agent").lower(), name=f"{TEST_PREFIX} agent"
        )
    )
    db.flush()

    first_user = _user(db, "first")
    second_user = _user(db, "second")
    first_team = _team(db, agent_id, "stage_one", 1, first_user)
    second_team = _team(db, agent_id, "stage_two", 1, second_user)

    policy_first = _policy(db, "first")
    policy_second = _policy(db, "second")
    agent_code = db.query(AccessAgent).filter(AccessAgent.id == agent_id).one().code

    second_config = FormSLAConfig(
        id=str(uuid.uuid4()),
        source_entity_type=WORKFLOW_SUBMISSION_ENTITY_TYPE,
        stage_code="stage_two",
        policy_id=policy_second,
        agent_code=agent_code,
        team_set_code="stage_two",
        start_event=_event("approved"),
        resolve_event=_event("closed"),
        is_active=True,
        notify_assignee=True,
    )
    db.add(second_config)
    db.flush()

    advance = _event("approved") if advance_on_event == "APPROVED" else advance_on_event
    first_config = FormSLAConfig(
        id=str(uuid.uuid4()),
        source_entity_type=WORKFLOW_SUBMISSION_ENTITY_TYPE,
        stage_code="stage_one",
        policy_id=policy_first,
        agent_code=agent_code,
        team_set_code="stage_one",
        start_event=_event("submitted"),
        resolve_event=f"{_event('approved')},{_event('rejected')}",
        advance_on_event=advance,
        next_config_id=second_config.id,
        is_active=True,
        notify_assignee=True,
    )
    db.add(first_config)
    db.commit()

    return Chain(
        agent_id=agent_id,
        first=Stage(first_config, "stage_one", first_team, first_user),
        second=Stage(second_config, "stage_two", second_team, second_user),
        policy_first=policy_first,
        policy_second=policy_second,
        users=(first_user, second_user),
    )


def _single_stage(
    db,
    *,
    start_event: str | None,
    resolve_event: str | None,
    team_set: str = "only",
) -> Stage:
    """One stage, for the tests that need a clock but not a chain."""
    agent_id = str(uuid.uuid4())
    db.add(
        AccessAgent(
            id=agent_id, code=unique_code("agent").lower(), name=f"{TEST_PREFIX} agent"
        )
    )
    db.flush()
    member = _user(db, "member")
    team_id = _team(db, agent_id, team_set, 1, member)
    policy_id = _policy(db, "only")
    agent_code = db.query(AccessAgent).filter(AccessAgent.id == agent_id).one().code
    config = FormSLAConfig(
        id=str(uuid.uuid4()),
        source_entity_type=WORKFLOW_SUBMISSION_ENTITY_TYPE,
        stage_code=team_set,
        policy_id=policy_id,
        agent_code=agent_code,
        team_set_code=team_set,
        start_event=start_event or unique_code("never"),
        resolve_event=resolve_event,
        advance_on_event=None,
        is_active=True,
        notify_assignee=True,
    )
    db.add(config)
    db.commit()
    return Stage(config, team_set, team_id, member)


def _live_tracker(db, stage: Stage, submission_id: str) -> ConversationSLATracking:
    """An already-running stage tracker, inserted directly.

    Arrangement only. The question the derived-resolve test asks is whether a
    DERIVED header move resolves a running clock, so how the clock started is not
    part of it.
    """
    now = _utc_naive_now()
    tracker = ConversationSLATracking(
        id=str(uuid.uuid4()),
        policy_id=stage.config.policy_id,
        current_tier=1,
        initiated_at=now - timedelta(hours=2),
        current_tier_started_at=now - timedelta(hours=2),
        due_at=now + timedelta(hours=2),
        due_at_resolution=now + timedelta(hours=22),
        is_responded=False,
        is_resolved=False,
        source_entity_type=WORKFLOW_SUBMISSION_ENTITY_TYPE,
        source_entity_id=submission_id,
        agent_id=_agent_id_for(db, stage.config.agent_code),
        team_set_code=stage.team_set,
        assigned_to_id=stage.member_id,
    )
    db.add(tracker)
    db.commit()
    return tracker


def _agent_id_for(db, agent_code: str) -> str:
    return str(
        db.query(AccessAgent).filter(AccessAgent.code == agent_code).one().id
    )


def _trackers(db, submission_id: str) -> list[ConversationSLATracking]:
    return (
        db.query(ConversationSLATracking)
        .filter(ConversationSLATracking.source_entity_id == str(submission_id))
        .order_by(ConversationSLATracking.initiated_at.asc())
        .all()
    )


def _assignments(sent: list[dict]) -> list[dict]:
    return [row for row in sent if row.get("event_type") == "assigned"]


def _stage_name(tracker, chain: Chain) -> str:
    """Which stage of the chain a tracker belongs to, keyed on ``policy_id``.

    Deliberately NOT ``team_set_code``. That column exists to drive escalation and
    the resolve path NULLs it for a non-form tracker, so a closed stage may have no
    team set left to read. ``policy_id`` is the stable discriminator, which is the
    practical reason AC-F2a-4's one-policy-per-stage rule matters beyond keeping the
    deadlines independent.
    """
    if str(tracker.policy_id) == str(chain.policy_first):
        return chain.first.team_set
    if str(tracker.policy_id) == str(chain.policy_second):
        return chain.second.team_set
    return f"unknown:{tracker.policy_id}"


def _lines(db, submission):
    return (
        db.query(WorkflowSubmissionLine)
        .filter(WorkflowSubmissionLine.submission_id == submission.id)
        .order_by(WorkflowSubmissionLine.sort_order)
        .all()
    )


def _decide(db, line, status, *, user_id: str):
    return WorkflowFormsService(db).apply_line_transition(
        str(line.id), status.id, user_id
    )


def _seeded_configs(db) -> list[FormSLAConfig]:
    module = _sla_module()
    seeder = getattr(module, "seed_workflow_submission_sla_configs", None)
    assert callable(seeder), (
        f"{SLA_MODULE}.seed_workflow_submission_sla_configs(db) must exist: the stage "
        "config has to be creatable on a blank schema so the migration and the tests "
        "read the same rows."
    )
    seeder(db)
    db.flush()
    return (
        db.query(FormSLAConfig)
        .filter(
            FormSLAConfig.source_entity_type == WORKFLOW_SUBMISSION_ENTITY_TYPE
        )
        .order_by(FormSLAConfig.stage_code)
        .all()
    )


def _events_of(config: FormSLAConfig, field: str) -> set[str]:
    raw = str(getattr(config, field, None) or "")
    return {token.strip() for token in raw.split(",") if token.strip()}


# ==================================================================== AC-F2a-1
# The duplicated tuple. This is the cheapest test in the file and it prevents a
# whole class of confusing runtime failure.


def test_the_two_definitions_of_the_form_sla_type_tuple_are_equal():
    """``FORM_SLA_TYPES`` gates every service path; ``_FORM_SLA_TYPES`` drives a
    Pydantic validator. Adding a type to only one passes the service and then 422s
    at the schema boundary, which reads as a broken API rather than a half-finished
    change. Pinning equality is what stops the next person half-adding a type."""
    from app.schemas.sla import _FORM_SLA_TYPES

    assert tuple(_FORM_SLA_TYPES) == tuple(FORM_SLA_TYPES), (
        "the service tuple and the schema tuple have drifted apart"
    )


def test_workflow_submission_is_a_form_sla_type_in_both_definitions():
    """Everything else in F2a hangs off this membership: the overdue scan, the
    handling-lock scope, the manual-escalate guard and the conversation/form
    discriminator all test it."""
    from app.schemas.sla import _FORM_SLA_TYPES

    assert WORKFLOW_SUBMISSION_ENTITY_TYPE in FORM_SLA_TYPES
    assert WORKFLOW_SUBMISSION_ENTITY_TYPE in _FORM_SLA_TYPES


def test_a_workflow_submission_stage_config_passes_the_schema_boundary():
    """The 422 the duplication produces, reproduced at the exact boundary that
    produces it. An admin creating the stage through the API hits this validator
    before any service code runs."""
    payload = FormSLAConfigCreate(
        source_entity_type=WORKFLOW_SUBMISSION_ENTITY_TYPE,
        stage_code="stage_one",
        policy_id=str(uuid.uuid4()),
        agent_code="whatever",
        start_event="submitted",
    )
    assert payload.source_entity_type == WORKFLOW_SUBMISSION_ENTITY_TYPE


def test_the_schema_boundary_still_rejects_a_type_nobody_declared():
    """The control. Widening the tuple must not turn into deleting the validator:
    ``source_entity_type`` is a free-text ``VARCHAR(50)`` in the database, so this
    validator is the only thing stopping a typo becoming a stage config that no
    emitter will ever match."""
    with pytest.raises(ValueError):
        FormSLAConfigCreate(
            source_entity_type="workflow_submissions",  # plural: a real typo
            stage_code="stage_one",
            policy_id=str(uuid.uuid4()),
            agent_code="whatever",
            start_event="submitted",
        )


# ==================================================================== AC-F2a-2
# The duplication is itself the defect.


def test_the_schema_module_imports_the_tuple_rather_than_restating_it():
    """Verified reachable: importing ``app.services.form_sla_service`` does not pull
    in ``app.schemas.sla`` at module scope, so there is no cycle to justify keeping
    two copies. Identity rather than equality, because equality is already pinned
    above and would pass a second literal that merely happens to agree today."""
    from app.schemas import sla as sla_schemas

    assert sla_schemas._FORM_SLA_TYPES is FORM_SLA_TYPES, (
        "app/schemas/sla.py must import FORM_SLA_TYPES from form_sla_service; "
        "restating the literal is the defect AC-F2a-2 removes"
    )


# ==================================================================== AC-F2a-3
# At least one stage is seeded, following the live shape.


def test_the_status_event_naming_lives_in_one_place():
    """The seeded config's ``start_event`` and the code that emits it have to agree
    on one string. Two hand-written copies of the convention is the same defect as
    the duplicated type tuple, one layer down."""
    module = _sla_module()
    fn = getattr(module, "submission_status_event", None)
    assert callable(fn), (
        f"{SLA_MODULE}.submission_status_event(status_key) must exist so the stage "
        "seed and the emitter cannot disagree about an event name"
    )
    for key in WORKFLOW_SUBMISSION_STATUS_KEYS:
        name = fn(key)
        assert isinstance(name, str) and name.strip(), (
            f"submission_status_event({key!r}) must return a non-empty name"
        )
    names = {fn(key) for key in WORKFLOW_SUBMISSION_STATUS_KEYS}
    assert len(names) == len(WORKFLOW_SUBMISSION_STATUS_KEYS), (
        "two status keys must not map to one event name, or one rung's move would "
        "fire another rung's stage"
    )


def test_at_least_one_stage_is_seeded_for_workflow_submission(db):
    """A submission with no stage config has no clock at all: ``emit_event`` finds
    nothing and returns. The seed is what makes the wiring observable."""
    _seed_graphs(db)
    configs = _seeded_configs(db)
    assert configs, "no form_sla_configs row was seeded for workflow_submission"
    assert all(bool(c.is_active) for c in configs), (
        "an inactive seeded stage is never evaluated by emit_event"
    )


def test_the_stage_seed_corrects_drift_instead_of_duplicating_rows(db):
    """Re-run safety, in the "set where mismatch" sense the rest of this codebase
    uses. An insert-if-absent seed can never repair a prior bad run, and a seed that
    duplicates a stage row gives one form two clocks on the same team set."""
    _seed_graphs(db)
    first = _seeded_configs(db)
    again = _seeded_configs(db)
    assert len(again) == len(first), "a re-run duplicated stage rows"
    assert {c.id for c in again} == {c.id for c in first}, (
        "a re-run replaced the rows; a live tracker's stage would be orphaned"
    )


def test_every_seeded_stage_declares_both_a_start_and_a_resolve_event(db):
    """A stage with no resolve event starts a clock that nothing can stop, and it
    escalates forever."""
    _seed_graphs(db)
    for config in _seeded_configs(db):
        assert _events_of(config, "start_event"), (
            f"stage {config.stage_code!r} has no start_event"
        )
        assert _events_of(config, "resolve_event"), (
            f"stage {config.stage_code!r} has no resolve_event, so its clock can "
            "never stop"
        )


def test_a_seeded_stage_starts_on_a_status_the_default_header_graph_actually_has(db):
    """The link between two vocabularies that are otherwise free text. If no seeded
    stage names a rung of the graph a brand new definition inherits, then no
    submission can ever start an SLA clock and the whole slice is inert."""
    _seed_graphs(db)
    reachable = {_event(key) for key in WORKFLOW_SUBMISSION_STATUS_KEYS}
    startable = [
        config
        for config in _seeded_configs(db)
        if _events_of(config, "start_event") & reachable
    ]
    assert startable, (
        "no seeded stage starts on an event the default submission graph can emit; "
        f"the graph can emit {sorted(reachable)}"
    )


def test_every_seeded_stage_can_actually_be_started(db):
    """``_start_for_config`` raises when the agent code names no row, and again when
    the policy has no tier for the starting tier. Both failures are swallowed and
    logged by ``emit_event``, so a mis-seeded stage looks exactly like a form with
    no SLA at all."""
    _seed_graphs(db)
    for config in _seeded_configs(db):
        agent = (
            db.query(AccessAgent)
            .filter(AccessAgent.code == config.agent_code)
            .first()
        )
        assert agent is not None, (
            f"stage {config.stage_code!r} names agent {config.agent_code!r}, which "
            "does not exist"
        )
        tier = (
            db.query(SLAPolicyTier)
            .filter(
                SLAPolicyTier.policy_id == config.policy_id,
                SLAPolicyTier.tier_level == 1,
            )
            .first()
        )
        assert tier is not None, (
            f"stage {config.stage_code!r} points at a policy with no tier 1"
        )


# ==================================================================== AC-F2a-4
# Stage identity is (source_entity_type, team_set_code), and stages get their own
# policy row.


def test_seeded_stages_do_not_share_a_team_set_code(db):
    """``_active_tracker`` separates one stage's tracker from another's by
    ``team_set_code`` alone. Two stages sharing it means one stage's resolve grabs
    the other stage's tracker, resolves it, and the second stage then re-creates
    it: a duplicate assignment and a duplicate notification for one form."""
    _seed_graphs(db)
    codes = [config.team_set_code for config in _seeded_configs(db)]
    assert len(codes) == len(set(codes)), f"stages share a team_set_code: {codes}"


def test_seeded_stages_do_not_share_a_policy_row(db):
    """Each stage owns its deadlines. A shared policy row means editing one stage's
    response hours silently re-times every other stage of the same form."""
    _seed_graphs(db)
    policies = [config.policy_id for config in _seeded_configs(db)]
    assert len(policies) == len(set(policies)), (
        f"stages share an sla_policies row: {policies}"
    )


def test_each_stage_of_a_chain_is_assigned_exactly_once(db, notifications):
    """The regression AC-F2a-4 names, asserted on what the user actually saw: two
    "sla_assigned" messages for one form.

    The chain here is the configuration that produces it - stage two is BOTH the
    ``next_config_id`` of stage one and declares ``approved`` as its own start
    event, exactly as the live complaint pipeline does. One approval therefore
    reaches stage two twice, and only an idempotent per-stage lookup keeps that to a
    single assignment.
    """
    _seed_graphs(db)
    chain = _chain(db)
    graph = _header_graph(db)
    definition = _definition(db)
    actor = _user(db, "actor")
    submission = _submission(db, definition, user_id=actor)
    service = WorkflowFormsService(db)

    service.apply_transition(
        str(submission.id), graph.by_key("submitted").id, None, actor
    )
    service.apply_transition(
        str(submission.id), graph.by_key("approved").id, None, actor
    )

    trackers = _trackers(db, submission.id)
    by_stage = {_stage_name(t, chain): t for t in trackers}
    assert len(trackers) == 2, (
        f"expected one tracker per stage, got {len(trackers)}: "
        f"{[_stage_name(t, chain) for t in trackers]}"
    )
    assert set(by_stage) == {"stage_one", "stage_two"}
    assert by_stage["stage_one"].is_resolved is True
    assert by_stage["stage_two"].is_resolved is False

    assigned = _assignments(notifications)
    per_stage: dict[str, int] = {}
    for row in assigned:
        tracker_id = (row.get("data") or {}).get("tracking_id")
        stage = next(
            (_stage_name(t, chain) for t in trackers if str(t.id) == str(tracker_id)),
            "unknown",
        )
        per_stage[stage] = per_stage.get(stage, 0) + 1
    assert per_stage == {"stage_one": 1, "stage_two": 1}, (
        f"one assignment per stage expected, got {per_stage}"
    )


def test_a_stages_tracker_records_the_submission_it_belongs_to(db):
    """The tracker's ``source_entity_id`` is how every read path gets back from a
    clock to the form: the detail banner, the pending-tasks widget, the handling
    lock. A tracker that names the definition, or nothing, is invisible."""
    _seed_graphs(db)
    chain = _chain(db)
    graph = _header_graph(db)
    definition = _definition(db)
    actor = _user(db, "actor")
    submission = _submission(db, definition, user_id=actor)

    WorkflowFormsService(db).apply_transition(
        str(submission.id), graph.by_key("submitted").id, None, actor
    )

    trackers = _trackers(db, submission.id)
    assert len(trackers) == 1, "the submitted move did not start exactly one clock"
    tracker = trackers[0]
    assert tracker.source_entity_type == WORKFLOW_SUBMISSION_ENTITY_TYPE
    assert str(tracker.source_entity_id) == str(submission.id)
    assert tracker.team_set_code == chain.first.team_set
    assert str(tracker.assigned_to_id) == chain.first.member_id


# ==================================================================== AC-F2a-5
# A derived move emits the SLA event the same as a manual one.


def test_a_manual_header_move_starts_the_stages_clock(db):
    """The control for the derived tests below, and the whole feature for a form
    that does not derive: a human move has to reach the SLA machinery."""
    _seed_graphs(db)
    stage = _single_stage(
        db, start_event=_event("submitted"), resolve_event=_event("approved")
    )
    graph = _header_graph(db)
    definition = _definition(db)
    actor = _user(db, "actor")
    submission = _submission(db, definition, user_id=actor)

    WorkflowFormsService(db).apply_transition(
        str(submission.id), graph.by_key("submitted").id, None, actor
    )

    trackers = _trackers(db, submission.id)
    assert len(trackers) == 1, (
        "a manual move into the stage's start event started no clock"
    )
    assert trackers[0].is_resolved is False


def test_a_derived_resolve_fires_the_stages_resolve_event(db):
    """The test most likely to fail on a naive implementation.

    A deriving definition's header is written ONLY by
    ``recompute_submission_status`` - ``apply_transition`` refuses every move into
    the derived pair - so an SLA that hooks the manual path alone would never
    resolve a clock on exactly the forms after-sales needs. Here every line is
    decided, the header derives from ``draft`` to ``submitted``, and the stage
    configured to resolve on that rung must close.
    """
    _seed_graphs(db)
    stage = _single_stage(
        db, start_event=None, resolve_event=_event(RESOLVED_KEY)
    )
    definition = _definition(db, derives=True)
    actor = _user(db, "actor")
    submission = _submission(db, definition, rows=2, user_id=actor)
    tracker = _live_tracker(db, stage, str(submission.id))
    approved = _line_graph(db, str(definition.id)).by_key("approved")

    for line in _lines(db, submission):
        _decide(db, line, approved, user_id=actor)

    db.refresh(submission)
    assert submission.status_key == RESOLVED_KEY, (
        "arrangement failed: the header did not derive, so the SLA assertion below "
        "would prove nothing"
    )
    db.refresh(tracker)
    assert tracker.is_resolved is True, (
        "a DERIVED header move did not emit the stage's resolve event; the clock is "
        "still running on a completed submission"
    )
    assert tracker.is_responded is True, "resolve implies responded"
    assert tracker.resolved_at is not None


def test_a_partial_decision_that_leaves_the_header_put_fires_nothing(db):
    """The trap on the other side. ``recompute_submission_status`` runs on every
    line decision and returns False when the answer is unchanged, so an emitter
    that fires per RECOMPUTE rather than per MOVE resolves a submission on the
    strength of its first decided line."""
    _seed_graphs(db)
    stage = _single_stage(
        db, start_event=None, resolve_event=_event(RESOLVED_KEY)
    )
    definition = _definition(db, derives=True)
    actor = _user(db, "actor")
    submission = _submission(db, definition, rows=2, user_id=actor)
    tracker = _live_tracker(db, stage, str(submission.id))
    approved = _line_graph(db, str(definition.id)).by_key("approved")

    _decide(db, _lines(db, submission)[0], approved, user_id=actor)

    db.refresh(submission)
    assert submission.status_key == OPEN_KEY, "arrangement: the header must not move"
    db.refresh(tracker)
    assert tracker.is_resolved is False, (
        "one decided line of two resolved the clock; the emitter is firing on every "
        "recompute rather than on an actual header move"
    )


def test_a_derived_resolve_does_not_credit_the_person_who_decided_a_line(db):
    """A derived move has no mover. F1a deliberately writes no ``user_id`` on the
    header's transition log because a person really did move a LINE a moment
    earlier, and naming them on the header is a lie plausible enough to be believed.
    The SLA tracker's ``resolved_by`` is the same column with the same problem, so
    the derived path must not pass the line-decider through as the actor.

    Asserted as "not the line decider" rather than "NULL" on purpose:
    ``update_tracking`` defaults ``resolved_by`` to the tracker's own assignee when
    no actor is supplied, and changing that would change every form type's
    behaviour, which is outside this slice.
    """
    _seed_graphs(db)
    stage = _single_stage(
        db, start_event=None, resolve_event=_event(RESOLVED_KEY)
    )
    definition = _definition(db, derives=True)
    actor = _user(db, "actor")
    submission = _submission(db, definition, rows=1, user_id=actor)
    tracker = _live_tracker(db, stage, str(submission.id))
    approved = _line_graph(db, str(definition.id)).by_key("approved")

    _decide(db, _lines(db, submission)[0], approved, user_id=actor)

    db.refresh(tracker)
    assert tracker.is_resolved is True, "the derived move did not resolve the clock"
    assert str(tracker.resolved_by or "") != actor, (
        "a derived resolve was attributed to the person who decided a line"
    )


def test_a_resolved_submission_stage_keeps_its_routing_for_audit(db):
    """A consequence of AC-F2a-1 that is easy to miss and impossible to notice
    later. ``update_tracking`` NULLs ``team_set_code`` and ``agent_id`` on resolve
    for a CONVERSATION row, and skips that clear only for a type inside
    ``FORM_SLA_TYPES``. Leave ``workflow_submission`` out of the tuple and every
    closed stage loses the stage and agent it belonged to, so the SLA history of a
    finished submission can no longer say which team handled which step."""
    _seed_graphs(db)
    chain = _chain(db)
    graph = _header_graph(db)
    definition = _definition(db)
    actor = _user(db, "actor")
    submission = _submission(db, definition, user_id=actor)
    service = WorkflowFormsService(db)

    service.apply_transition(
        str(submission.id), graph.by_key("submitted").id, None, actor
    )
    service.apply_transition(
        str(submission.id), graph.by_key("approved").id, None, actor
    )

    resolved = [t for t in _trackers(db, submission.id) if t.is_resolved]
    assert resolved, "nothing resolved, so there is no audit trail to check"
    for tracker in resolved:
        assert tracker.team_set_code == chain.first.team_set, (
            "a resolved submission stage lost its team_set_code"
        )
        assert tracker.agent_id is not None, (
            "a resolved submission stage lost its agent_id"
        )


def test_a_manual_resolve_does_name_its_actor(db):
    """The mirror of the test above, and the reason it is not simply "never set
    ``resolved_by``": a human move has an actor and the trail must carry it."""
    _seed_graphs(db)
    stage = _single_stage(
        db, start_event=_event("submitted"), resolve_event=_event("approved")
    )
    graph = _header_graph(db)
    definition = _definition(db)
    actor = _user(db, "actor")
    submission = _submission(db, definition, user_id=actor)
    service = WorkflowFormsService(db)

    service.apply_transition(
        str(submission.id), graph.by_key("submitted").id, None, actor
    )
    service.apply_transition(
        str(submission.id), graph.by_key("approved").id, None, actor
    )

    trackers = _trackers(db, submission.id)
    assert len(trackers) == 1, "the manual move started no clock"
    assert trackers[0].is_resolved is True
    assert str(trackers[0].resolved_by) == actor


def test_a_failing_sla_emit_does_not_break_the_status_move(db, monkeypatch):
    """The emit is a side effect of a move that has already been accepted. A
    submission that cannot be approved because its SLA stage is mis-configured is
    the worst outcome of this slice, so the emit is best-effort in both directions
    and the caller never sees the failure."""
    _seed_graphs(db)
    _single_stage(
        db, start_event=_event("submitted"), resolve_event=_event("approved")
    )
    graph = _header_graph(db)
    definition = _definition(db)
    actor = _user(db, "actor")
    submission = _submission(db, definition, user_id=actor)

    import app.services.form_sla_service as form_sla_service

    def _boom(*args, **kwargs):
        raise RuntimeError("ZZT: the SLA machinery is down")

    monkeypatch.setattr(form_sla_service, "emit_form_event", _boom)
    monkeypatch.setattr(
        form_sla_service.FormSLAOrchestrator, "emit_event", _boom
    )

    moved = WorkflowFormsService(db).apply_transition(
        str(submission.id), graph.by_key("submitted").id, None, actor
    )
    db.refresh(moved)
    assert moved.status_key == "submitted", (
        "an SLA failure rolled back or blocked a status move that had been accepted"
    )


# ==================================================================== AC-F2a-6
# advance_on_event, set explicitly, or a rejection spawns the next stage.


def test_a_rejecting_event_resolves_the_stage_without_advancing(db):
    """The live defect, as behaviour. Stage one resolves on approve OR reject, so
    with ``advance_on_event`` set to the approving event a rejection must close the
    stage and stop. Without it the rejected submission is handed to the next team as
    though it had been approved."""
    _seed_graphs(db)
    chain = _chain(db)
    graph = _header_graph(db)
    definition = _definition(db)
    actor = _user(db, "actor")
    submission = _submission(db, definition, user_id=actor)
    service = WorkflowFormsService(db)

    service.apply_transition(
        str(submission.id), graph.by_key("submitted").id, None, actor
    )
    service.apply_transition(
        str(submission.id), graph.by_key("rejected").id, None, actor
    )

    trackers = _trackers(db, submission.id)
    stages = [_stage_name(t, chain) for t in trackers]
    assert stages == ["stage_one"], (
        f"a rejection spawned the next stage: trackers exist for {stages}"
    )
    assert trackers[0].is_resolved is True, "the rejected stage must still close"


def test_the_approving_event_does_advance_the_chain(db):
    """The control. A guard that blocked every advance would pass the test above
    while breaking the pipeline outright."""
    _seed_graphs(db)
    chain = _chain(db)
    graph = _header_graph(db)
    definition = _definition(db)
    actor = _user(db, "actor")
    submission = _submission(db, definition, user_id=actor)
    service = WorkflowFormsService(db)

    service.apply_transition(
        str(submission.id), graph.by_key("submitted").id, None, actor
    )
    service.apply_transition(
        str(submission.id), graph.by_key("approved").id, None, actor
    )

    stages = sorted(_stage_name(t, chain) for t in _trackers(db, submission.id))
    assert stages == ["stage_one", "stage_two"], (
        f"approval did not advance the chain: {stages}"
    )


def test_a_null_advance_on_event_is_what_lets_a_rejection_advance(db):
    """Why AC-F2a-6 asks for an explicit value rather than trusting the default.
    NULL means "any resolve advances", so the same rejection that must stop the
    pipeline hands the form to the next team. Pinned so the default can never be
    mistaken for a safe one."""
    _seed_graphs(db)
    chain = _chain(db, advance_on_event=None)
    graph = _header_graph(db)
    definition = _definition(db)
    actor = _user(db, "actor")
    submission = _submission(db, definition, user_id=actor)
    service = WorkflowFormsService(db)

    service.apply_transition(
        str(submission.id), graph.by_key("submitted").id, None, actor
    )
    service.apply_transition(
        str(submission.id), graph.by_key("rejected").id, None, actor
    )

    stages = sorted(_stage_name(t, chain) for t in _trackers(db, submission.id))
    assert stages == ["stage_one", "stage_two"], (
        "with advance_on_event NULL a rejection is expected to advance; if this "
        "fails the NULL semantics changed and AC-F2a-6's premise needs revisiting"
    )


def test_every_seeded_stage_with_a_next_stage_sets_advance_on_event_explicitly(db):
    """The config half of the same rule, over whatever stages the seed declares.
    The value must also be one of the stage's own resolve events, or the chain can
    never advance at all - a silent dead end rather than a wrong advance."""
    _seed_graphs(db)
    for config in _seeded_configs(db):
        if not config.next_config_id:
            continue
        advance = str(config.advance_on_event or "").strip()
        assert advance, (
            f"stage {config.stage_code!r} chains to another stage with "
            "advance_on_event NULL, so a rejection would advance it"
        )
        assert advance in _events_of(config, "resolve_event"), (
            f"stage {config.stage_code!r} advances on {advance!r}, which is not one "
            f"of its resolve events {sorted(_events_of(config, 'resolve_event'))}; "
            "the chain can never advance"
        )


# ==================================================================== AC-F2a-7
# "Escalated" is escalated_at, never current_tier > 1.


def _tracker_row(db, stage: Stage, submission_id: str, *, tier: int, escalated: bool):
    now = _utc_naive_now()
    tracker = ConversationSLATracking(
        id=str(uuid.uuid4()),
        policy_id=stage.config.policy_id,
        current_tier=tier,
        initiated_at=now - timedelta(hours=5),
        current_tier_started_at=now - timedelta(hours=1),
        due_at=now + timedelta(hours=3),
        due_at_resolution=now + timedelta(hours=20),
        escalated_at=now - timedelta(minutes=30) if escalated else None,
        escalation_reason="ZZT overdue" if escalated else None,
        is_responded=False,
        is_resolved=False,
        source_entity_type=WORKFLOW_SUBMISSION_ENTITY_TYPE,
        source_entity_id=submission_id,
        agent_id=_agent_id_for(db, stage.config.agent_code),
        team_set_code=stage.team_set,
        assigned_to_id=stage.member_id,
    )
    db.add(tracker)
    db.commit()
    return tracker


def _enable_lock(db, *types: str):
    db.add(
        SystemSetting(
            id=str(uuid.uuid4()),
            name=f"{TEST_PREFIX} settings",
            handling_lock_enabled_types=",".join(types),
        )
    )
    db.commit()


def test_a_tier_two_tracker_that_never_escalated_does_not_read_as_escalated(db):
    """A stage can legitimately START above tier 1 - the live ``project_sales``
    stage has no tier-1 team, and the PR/SF approval stage routes to a default
    approver at THEIR tier. ``escalated_at`` is stamped only by
    ``_escalate_tracker``, so it is the only signal that separates a real breach
    from a high initial assignment."""
    _seed_graphs(db)
    stage = _single_stage(db, start_event=None, resolve_event=None)
    tracker = _tracker_row(
        db, stage, str(uuid.uuid4()), tier=2, escalated=False
    )
    assert handling_lock_service._is_escalated(tracker) is False


def test_an_escalated_tracker_reads_as_escalated_even_at_tier_one(db):
    """The other direction, and the reason a tier check is wrong rather than merely
    imprecise: tier and escalation are independent facts."""
    _seed_graphs(db)
    stage = _single_stage(db, start_event=None, resolve_event=None)
    tracker = _tracker_row(db, stage, str(uuid.uuid4()), tier=1, escalated=True)
    assert handling_lock_service._is_escalated(tracker) is True


def test_a_workflow_submission_tracker_is_inside_the_handling_lock_scope(db):
    """Everything below depends on this. The lock's tracker lookup filters on
    ``source_entity_type.in_(FORM_SLA_TYPES)``, so before F2a a submission's
    tracker is simply not found and every lock assertion would pass for the wrong
    reason."""
    _seed_graphs(db)
    stage = _single_stage(db, start_event=None, resolve_event=None)
    submission_id = str(uuid.uuid4())
    tracker = _tracker_row(db, stage, submission_id, tier=1, escalated=True)

    found = handling_lock_service._active_form_tracker(
        db, submission_id, WORKFLOW_SUBMISSION_ENTITY_TYPE
    )
    assert found is not None, (
        "a workflow_submission tracker is invisible to the handling lock"
    )
    assert str(found.id) == str(tracker.id)


def test_a_never_escalated_tier_two_submission_keeps_its_ctas(db):
    """The bug a tier-based check produces, from the user's side: a form nobody
    escalated shows the "claim it" banner and every action button is disabled."""
    _seed_graphs(db)
    stage = _single_stage(db, start_event=None, resolve_event=None)
    _enable_lock(db, WORKFLOW_SUBMISSION_ENTITY_TYPE)
    submission_id = str(uuid.uuid4())
    _tracker_row(db, stage, submission_id, tier=2, escalated=False)

    handling_lock_service.assert_can_act_on_form(
        db,
        submission_id,
        {"id": stage.member_id},
        source_entity_type=WORKFLOW_SUBMISSION_ENTITY_TYPE,
    )


def test_an_escalated_submission_locks_its_ctas_until_someone_claims(db):
    """The feature the lock exists for, on the new type. A 403 here is the correct
    answer; silence would mean the lock never reaches submissions at all."""
    _seed_graphs(db)
    stage = _single_stage(db, start_event=None, resolve_event=None)
    _enable_lock(db, WORKFLOW_SUBMISSION_ENTITY_TYPE)
    submission_id = str(uuid.uuid4())
    _tracker_row(db, stage, submission_id, tier=1, escalated=True)

    with pytest.raises(AppException) as err:
        handling_lock_service.assert_can_act_on_form(
            db,
            submission_id,
            {"id": stage.member_id},
            source_entity_type=WORKFLOW_SUBMISSION_ENTITY_TYPE,
        )
    assert err.value.status_code == 403


def test_a_never_escalated_tier_two_tracker_cannot_be_claimed(db):
    """The claim endpoint's own guard, which must key on the same signal. The
    message matters: before F2a the same 422 comes back saying "not a form SLA
    stage", which is a different bug with the same status code."""
    _seed_graphs(db)
    stage = _single_stage(db, start_event=None, resolve_event=None)
    _enable_lock(db, WORKFLOW_SUBMISSION_ENTITY_TYPE)
    tracker = _tracker_row(db, stage, str(uuid.uuid4()), tier=2, escalated=False)

    service = handling_lock_service.HandlingLockService(db)
    with pytest.raises(AppException) as err:
        service.claim_handling(str(tracker.id), {"id": stage.member_id})
    assert err.value.status_code == 422
    assert "not escalated" in str(err.value.detail.get("message", "")).lower(), (
        f"expected the not-escalated refusal, got {err.value.detail!r}"
    )


def test_an_escalated_submission_can_be_claimed_by_an_eligible_member(db):
    """The happy path, so the guard above is not satisfied by refusing everything."""
    _seed_graphs(db)
    stage = _single_stage(db, start_event=None, resolve_event=None)
    _enable_lock(db, WORKFLOW_SUBMISSION_ENTITY_TYPE)
    tracker = _tracker_row(db, stage, str(uuid.uuid4()), tier=1, escalated=True)

    service = handling_lock_service.HandlingLockService(db)
    claimed = service.claim_handling(str(tracker.id), {"id": stage.member_id})
    assert str(claimed.handled_by_id) == stage.member_id
    assert claimed.handled_at is not None


# ==================================================================== AC-F2a-8
# conversation_sla_tracking is shared. The scope filter must exclude the new type.


def _contact(db) -> str:
    contact_id = str(uuid.uuid4())
    db.add(
        RespondContact(
            id=contact_id,
            phone_number=f"+6019{uuid.uuid4().int % 10_000_000:07d}",
            name=f"{TEST_PREFIX} contact",
        )
    )
    db.flush()
    return contact_id


def _conversation_tracker(db, stage: Stage, contact_id: str):
    """An n8n-style conversation row: contact-keyed, no ``source_entity_type``."""
    now = _utc_naive_now()
    tracker = ConversationSLATracking(
        id=str(uuid.uuid4()),
        policy_id=stage.config.policy_id,
        current_tier=1,
        initiated_at=now,
        current_tier_started_at=now,
        due_at=now + timedelta(hours=4),
        due_at_resolution=now + timedelta(hours=24),
        is_responded=False,
        is_resolved=False,
        respond_contact_id=contact_id,
        source_entity_type=None,
        assigned_to_id=stage.member_id,
    )
    db.add(tracker)
    db.commit()
    return tracker


def test_a_workflow_submission_tracker_is_not_a_conversation_row(db):
    """One table, two systems, discriminated only by ``source_entity_type``. Adding
    a sixth form type widens what a contact-keyed conversation query falsely
    matches, and the symptom is remote: n8n's conversation create sees an active row
    that is not a conversation and refuses, or a thread-assignee lookup returns a
    form stage's assignee."""
    _seed_graphs(db)
    stage = _single_stage(db, start_event=None, resolve_event=None)
    contact_id = _contact(db)
    now = _utc_naive_now()
    form_row = ConversationSLATracking(
        id=str(uuid.uuid4()),
        policy_id=stage.config.policy_id,
        current_tier=1,
        initiated_at=now,
        current_tier_started_at=now,
        due_at=now + timedelta(hours=4),
        due_at_resolution=now + timedelta(hours=24),
        is_responded=False,
        is_resolved=False,
        respond_contact_id=contact_id,
        source_entity_type=WORKFLOW_SUBMISSION_ENTITY_TYPE,
        source_entity_id=str(uuid.uuid4()),
        team_set_code=stage.team_set,
        assigned_to_id=stage.member_id,
    )
    db.add(form_row)
    db.commit()

    rows = (
        db.query(ConversationSLATracking)
        .filter(
            ConversationSLATracking.respond_contact_id == contact_id,
            conversation_tracking_scope(),
        )
        .all()
    )
    assert [str(r.id) for r in rows] == [], (
        "a workflow_submission stage row is being read as a conversation row"
    )


def test_the_contact_keyed_conversation_lookup_skips_a_submission_stage(db):
    """The same rule through a real caller rather than the filter alone. This is the
    lookup that decides whether a contact already has an open conversation."""
    _seed_graphs(db)
    stage = _single_stage(db, start_event=None, resolve_event=None)
    contact_id = _contact(db)
    now = _utc_naive_now()
    db.add(
        ConversationSLATracking(
            id=str(uuid.uuid4()),
            policy_id=stage.config.policy_id,
            current_tier=1,
            initiated_at=now,
            current_tier_started_at=now,
            due_at=now + timedelta(hours=4),
            due_at_resolution=now + timedelta(hours=24),
            is_responded=False,
            is_resolved=False,
            respond_contact_id=contact_id,
            source_entity_type=WORKFLOW_SUBMISSION_ENTITY_TYPE,
            source_entity_id=str(uuid.uuid4()),
            team_set_code=stage.team_set,
            assigned_to_id=stage.member_id,
        )
    )
    db.commit()

    found = ConversationSLATrackingService(db).get_open_tracking_by_contact(contact_id)
    assert found is None, (
        "a submission's stage row answered a conversation-SLA lookup for its contact"
    )


def test_a_real_conversation_row_for_the_same_contact_is_still_found(db):
    """The control: the scope filter must exclude form rows without excluding the
    conversation rows it exists to select."""
    _seed_graphs(db)
    stage = _single_stage(db, start_event=None, resolve_event=None)
    contact_id = _contact(db)
    conversation = _conversation_tracker(db, stage, contact_id)

    found = ConversationSLATrackingService(db).get_open_tracking_by_contact(contact_id)
    assert found is not None and str(found.id) == str(conversation.id)


def test_the_overdue_scan_sees_a_workflow_submission_tracker(db):
    """``scan_overdue_and_escalate`` selects candidates by
    ``source_entity_type.in_(FORM_SLA_TYPES)``. Outside the tuple a submission's
    clock runs past its deadline and nothing ever escalates it - the failure is
    total silence, which is why it needs its own assertion."""
    from app.services.form_sla_service import FormSLAOrchestrator

    _seed_graphs(db)
    stage = _single_stage(db, start_event=None, resolve_event=None)
    now = _utc_naive_now()
    db.add(
        ConversationSLATracking(
            id=str(uuid.uuid4()),
            policy_id=stage.config.policy_id,
            current_tier=1,
            initiated_at=now - timedelta(days=2),
            current_tier_started_at=now - timedelta(days=2),
            due_at=now - timedelta(days=1),
            due_at_resolution=now - timedelta(days=1),
            is_responded=False,
            is_resolved=False,
            source_entity_type=WORKFLOW_SUBMISSION_ENTITY_TYPE,
            source_entity_id=str(uuid.uuid4()),
            agent_id=_agent_id_for(db, stage.config.agent_code),
            team_set_code=stage.team_set,
            assigned_to_id=stage.member_id,
        )
    )
    db.commit()

    summary = FormSLAOrchestrator(db).scan_overdue_and_escalate()
    assert summary["scanned"] >= 1, (
        "the overdue scan does not consider workflow_submission trackers at all"
    )
    assert summary["escalated"] + summary["skipped"] >= 1, (
        "an overdue submission tracker was scanned but neither escalated nor "
        "recorded as skipped"
    )
