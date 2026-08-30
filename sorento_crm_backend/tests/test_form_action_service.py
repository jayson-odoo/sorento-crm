"""Form SLA Undo - deferral, cancel, commit (PLAN-form-sla-undo.md, S0/S2).

Written test-first. Every test seeds its own chain with a marker prefix and never
borrows an existing row - CI's database is empty, so a `LIMIT 1` off a live table
resolves to None there and the dependent INSERT dies on a NOT NULL FK.

Postgres only. `blank_session()` builds an isolated blank schema; the outer
transaction is rolled back, so committing code under test is still discarded.
"""

import uuid
from datetime import datetime, timedelta

import pytest

from tests._pg_fixture import blank_session
from app.models.sla import (
    FORM_ACTION_CANCELLED,
    FORM_ACTION_CHANNEL_IMMEDIATE,
    FORM_ACTION_CHANNEL_UI,
    FORM_ACTION_COMMITTED,
    FORM_ACTION_PENDING,
    SlaFormAction,
)

MARKER = "zzt-formaction-"


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


class _Spy:
    """Stands in for a real service method so a test can assert the deferred path
    runs EXACTLY what the immediate path runs, and runs it exactly once."""

    def __init__(self):
        self.calls: list[dict] = []
        self.prior = {"status": "submitted", "approval_status": None}

    def capture(self, _db, _payload):
        return dict(self.prior)

    def execute(self, _db, payload):
        self.calls.append(dict(payload))


def _register(monkeypatch, spy, *, key="zzt.test_action", tells_contact=False):
    from app.services import form_action_registry as reg

    action = reg.FormAction(
        key=key,
        entity_types=("purchase_request",),
        execute=spy.execute,
        capture=spy.capture,
        invert=None,
        resolve_event=lambda _payload: "approved",
        tells_contact=tells_contact,
    )
    monkeypatch.setitem(reg.REGISTRY, key, action)
    return action


def _service(db):
    from app.services.form_action_service import FormActionService

    return FormActionService(db)


def _entity_id() -> str:
    return str(uuid.uuid4())


# --------------------------------------------------------------------------------------
# AC-D-2 / AC-D-4 - the immediate path, and equivalence with the deferred one
# --------------------------------------------------------------------------------------


def test_zero_grace_executes_immediately_and_records_history(db, monkeypatch):
    """Grace 0 -> run now, and still write a `committed` row so a post-grace undo has
    history to read even though the action never deferred."""
    spy = _Spy()
    _register(monkeypatch, spy)
    entity_id = _entity_id()

    result = _service(db).dispatch(
        action_key="zzt.test_action",
        entity_type="purchase_request",
        entity_id=entity_id,
        payload={"action": "approved"},
        actor_id=None,
        channel=FORM_ACTION_CHANNEL_UI,
        grace_seconds=0,
    )

    assert result.deferred is False
    assert len(spy.calls) == 1

    row = db.query(SlaFormAction).filter(SlaFormAction.source_entity_id == entity_id).one()
    assert row.status == FORM_ACTION_COMMITTED
    assert row.prior_state_json == spy.prior


def test_non_ui_channel_never_defers(db, monkeypatch):
    """AC-D-3: portal / API-key / n8n / MCP execute immediately whatever the grace is,
    because there is no UI to show an Undo button in."""
    spy = _Spy()
    _register(monkeypatch, spy)

    result = _service(db).dispatch(
        action_key="zzt.test_action",
        entity_type="purchase_request",
        entity_id=_entity_id(),
        payload={},
        actor_id=None,
        channel=FORM_ACTION_CHANNEL_IMMEDIATE,
        grace_seconds=30,
    )

    assert result.deferred is False
    assert len(spy.calls) == 1


# --------------------------------------------------------------------------------------
# AC-D-1 - deferral changes nothing until it commits
# --------------------------------------------------------------------------------------


def test_deferred_dispatch_runs_nothing(db, monkeypatch):
    spy = _Spy()
    _register(monkeypatch, spy)
    entity_id = _entity_id()

    result = _service(db).dispatch(
        action_key="zzt.test_action",
        entity_type="purchase_request",
        entity_id=entity_id,
        payload={"action": "approved"},
        actor_id=None,
        channel=FORM_ACTION_CHANNEL_UI,
        grace_seconds=10,
    )

    assert result.deferred is True
    assert result.window_seconds == 10
    assert spy.calls == [], "the action must NOT run during its grace window"

    row = db.query(SlaFormAction).filter(SlaFormAction.source_entity_id == entity_id).one()
    assert row.status == FORM_ACTION_PENDING
    assert row.commit_at is not None
    # Captured up front so the inverse restores recorded values, not guessed ones.
    assert row.prior_state_json == spy.prior


def test_only_one_pending_action_per_form(db, monkeypatch):
    """AC-D-7: a second action while one is pending is refused."""
    from app.services.error_handler import AppException

    spy = _Spy()
    _register(monkeypatch, spy)
    entity_id = _entity_id()
    svc = _service(db)

    svc.dispatch(
        action_key="zzt.test_action",
        entity_type="purchase_request",
        entity_id=entity_id,
        payload={},
        actor_id=None,
        channel=FORM_ACTION_CHANNEL_UI,
        grace_seconds=10,
    )

    with pytest.raises(AppException):
        svc.dispatch(
            action_key="zzt.test_action",
            entity_type="purchase_request",
            entity_id=entity_id,
            payload={},
            actor_id=None,
            channel=FORM_ACTION_CHANNEL_UI,
            grace_seconds=10,
        )

    assert spy.calls == []


# --------------------------------------------------------------------------------------
# AC-IG - in-grace cancel
# --------------------------------------------------------------------------------------


def test_cancel_leaves_the_form_untouched(db, monkeypatch):
    """AC-IG-4/5: the action never ran, so there is nothing to reverse and nobody to tell."""
    spy = _Spy()
    _register(monkeypatch, spy)
    entity_id = _entity_id()
    svc = _service(db)

    pending = svc.dispatch(
        action_key="zzt.test_action",
        entity_type="purchase_request",
        entity_id=entity_id,
        payload={},
        actor_id=None,
        channel=FORM_ACTION_CHANNEL_UI,
        grace_seconds=10,
    )

    svc.cancel(pending.action_id, actor_id=None, actor_is_admin=True)

    row = db.query(SlaFormAction).filter(SlaFormAction.id == pending.action_id).one()
    assert row.status == FORM_ACTION_CANCELLED
    assert spy.calls == []


def test_cancel_after_commit_is_refused(db, monkeypatch):
    """AC-IG-3: no silent success once it has already committed."""
    from app.services.error_handler import AppException

    spy = _Spy()
    _register(monkeypatch, spy)
    svc = _service(db)

    pending = svc.dispatch(
        action_key="zzt.test_action",
        entity_type="purchase_request",
        entity_id=_entity_id(),
        payload={},
        actor_id=None,
        channel=FORM_ACTION_CHANNEL_UI,
        grace_seconds=10,
    )
    row = db.query(SlaFormAction).filter(SlaFormAction.id == pending.action_id).one()
    row.commit_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    svc.commit_one(row)

    with pytest.raises(AppException):
        svc.cancel(pending.action_id, actor_id=None, actor_is_admin=True)


# --------------------------------------------------------------------------------------
# AC-D-6 - commit is idempotent
# --------------------------------------------------------------------------------------


def test_commit_runs_once_under_a_double_sweep(db, monkeypatch):
    """The scheduler sweep and the lazy-commit-on-read can race. The conditional
    status transition is what makes the second caller a no-op."""
    spy = _Spy()
    _register(monkeypatch, spy)
    svc = _service(db)

    pending = svc.dispatch(
        action_key="zzt.test_action",
        entity_type="purchase_request",
        entity_id=_entity_id(),
        payload={},
        actor_id=None,
        channel=FORM_ACTION_CHANNEL_UI,
        grace_seconds=10,
    )
    row = db.query(SlaFormAction).filter(SlaFormAction.id == pending.action_id).one()
    row.commit_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()

    assert svc.commit_one(row) is True
    assert svc.commit_one(row) is False
    assert len(spy.calls) == 1


# --------------------------------------------------------------------------------------
# Grace resolution - per-stage overrides the global, NULL falls back (AC-S-1/AC-S-2)
# --------------------------------------------------------------------------------------


def _seed_config(db, *, source_entity_type, resolve_event, grace_seconds, team_set_code):
    """Seed our OWN policy -> config chain. Never borrow a live row: CI's database is
    empty, so `SELECT ... LIMIT 1` resolves to None there and the dependent INSERT dies
    on `policy_id` NOT NULL - the exact failure this rule exists to prevent."""
    from app.models.sla import FormSLAConfig, SLAPolicy

    policy = SLAPolicy(code=f"{MARKER}{team_set_code}", name=f"{MARKER}policy")
    db.add(policy)
    db.flush()

    config = FormSLAConfig(
        policy_id=policy.id,
        source_entity_type=source_entity_type,
        # Every NOT NULL column on form_sla_configs: source_entity_type, stage_code,
        # policy_id, agent_code, start_event. Postgres rejects the row without them.
        stage_code=team_set_code,
        agent_code=team_set_code,
        start_event="submit",
        team_set_code=team_set_code,
        resolve_event=resolve_event,
        grace_seconds=grace_seconds,
        is_active=True,
    )
    db.add(config)
    db.commit()
    return config


def test_stage_grace_overrides_the_global_default(db):
    from app.services.form_action_grace import grace_seconds_for

    _seed_config(
        db,
        source_entity_type="purchase_request",
        resolve_event="approved,approval_rejected",
        grace_seconds=15,
        team_set_code=MARKER + "mgr",
    )

    assert grace_seconds_for(db, "purchase_request", event_name="approved") == 15


def test_grace_falls_back_to_zero_when_no_stage_sets_one(db):
    """The shipped default: nothing defers until someone turns a stage on."""
    from app.services.form_action_grace import grace_seconds_for

    _seed_config(
        db,
        source_entity_type="complaint",
        resolve_event="resolved",
        grace_seconds=None,
        team_set_code=MARKER + "cs",
    )

    assert grace_seconds_for(db, "complaint", event_name="resolved") == 0


def test_grace_is_matched_per_stage_not_per_form(db):
    """A form type has several stages. The grace that applies belongs to the stage
    whose resolve_event lists this event, not to whichever row comes back first."""
    from app.services.form_action_grace import grace_seconds_for

    _seed_config(
        db,
        source_entity_type="stock_inquiry",
        resolve_event="project_sales_approve",
        grace_seconds=20,
        team_set_code=MARKER + "ps",
    )
    _seed_config(
        db,
        source_entity_type="stock_inquiry",
        resolve_event="purchasing_decide",
        grace_seconds=5,
        team_set_code=MARKER + "purch",
    )

    assert grace_seconds_for(db, "stock_inquiry", event_name="project_sales_approve") == 20
    assert grace_seconds_for(db, "stock_inquiry", event_name="purchasing_decide") == 5


# --------------------------------------------------------------------------------------
# Post-grace undo - the guardrail (AC-PG-1/2/3) and the reversal (AC-PGE-*)
#
# With no time limit on undo, the guardrail is the ONLY thing between a stale form and a
# rewind, so it carries the heaviest tests in this file.
# --------------------------------------------------------------------------------------


class _RevertSpy(_Spy):
    """Adds an inverse that restores whatever was captured, so a test can assert the
    inverse reads `prior_state_json` rather than writing a plausible default."""

    def __init__(self):
        super().__init__()
        self.restored: list[dict] = []

    def invert(self, _db, record):
        self.restored.append(dict(record.prior_state_json or {}))


def _register_invertible(monkeypatch, spy, *, key="zzt.undoable"):
    from app.services import form_action_registry as reg

    action = reg.FormAction(
        key=key,
        entity_types=("purchase_request",),
        execute=spy.execute,
        capture=spy.capture,
        invert=spy.invert,
        resolve_event=lambda _p: "approved",
        tells_contact=False,
        label="Approval",
    )
    monkeypatch.setitem(reg.REGISTRY, key, action)
    return action


def _seed_entity(db, entity_id, *, status="submitted"):
    """A real purchase_requests row behind the action. The eligibility guardrail
    reads the entity's CURRENT status (a voided or deleted form refuses undo), so an
    undoable action needs its form to actually exist."""
    from app.models.procurement import PurchaseRequestHeader

    existing = (
        db.query(PurchaseRequestHeader)
        .filter(PurchaseRequestHeader.id == str(entity_id))
        .first()
    )
    if existing is not None:
        return existing
    header = PurchaseRequestHeader(
        id=str(entity_id),
        request_number=f"{MARKER}{str(entity_id)[:6]}",
        request_type="purchase_request",
        status=status,
    )
    db.add(header)
    db.commit()
    return header


def _commit_one(db, svc, entity_id, key="zzt.undoable"):
    """Dispatch at grace 0 so the action commits straight away and becomes undoable."""
    _seed_entity(db, entity_id)
    return svc.dispatch(
        action_key=key,
        entity_type="purchase_request",
        entity_id=entity_id,
        payload={"request_id": entity_id, "action": "approved"},
        actor_id=None,
        channel=FORM_ACTION_CHANNEL_UI,
        grace_seconds=0,
    )


def test_undo_restores_the_captured_prior_state(db, monkeypatch):
    """AC-PGE-1: the inverse writes back what was recorded, not a guessed default."""
    spy = _RevertSpy()
    _register_invertible(monkeypatch, spy)
    entity_id = _entity_id()
    svc = _service(db)
    _commit_one(db, svc, entity_id)

    svc.undo(
        source_entity_type="purchase_request",
        source_entity_id=entity_id,
        actor_id=None,
        reason="approved the wrong form",
        has_permission=True,
    )

    assert spy.restored == [spy.prior]
    row = db.query(SlaFormAction).filter(SlaFormAction.source_entity_id == entity_id).one()
    assert row.status == "undone"
    assert row.undo_reason == "approved the wrong form"


def test_undo_without_permission_is_refused(db, monkeypatch):
    """AC-PG-4 - and the refusal happens in the service, not only the route."""
    from app.services.error_handler import AppException

    spy = _RevertSpy()
    _register_invertible(monkeypatch, spy)
    entity_id = _entity_id()
    svc = _service(db)
    _commit_one(db, svc, entity_id)

    with pytest.raises(AppException):
        svc.undo(
            source_entity_type="purchase_request",
            source_entity_id=entity_id,
            actor_id=None,
            reason="because",
            has_permission=False,
        )
    assert spy.restored == []


def test_undo_is_refused_when_nothing_has_been_committed(db, monkeypatch):
    from app.services.error_handler import AppException

    svc = _service(db)
    with pytest.raises(AppException):
        svc.undo(
            source_entity_type="purchase_request",
            source_entity_id=_entity_id(),
            actor_id=None,
            reason="because",
            has_permission=True,
        )


def test_undo_is_refused_for_a_non_invertible_action(db, monkeypatch):
    """Deferral works without an inverse; undo must not pretend otherwise."""
    from app.services.error_handler import AppException

    spy = _Spy()  # plain spy -> invert=None
    _register(monkeypatch, spy, key="zzt.not_invertible")
    entity_id = _entity_id()
    svc = _service(db)
    _commit_one(db, svc, entity_id, key="zzt.not_invertible")

    with pytest.raises(AppException):
        svc.undo(
            source_entity_type="purchase_request",
            source_entity_id=entity_id,
            actor_id=None,
            reason="because",
            has_permission=True,
        )


def test_undo_only_reaches_the_last_committed_action(db, monkeypatch):
    """AC-PG-1/AC-PG-3: an older action is not undoable once another has landed on top."""
    from app.services.error_handler import AppException

    spy = _RevertSpy()
    _register_invertible(monkeypatch, spy)
    entity_id = _entity_id()
    svc = _service(db)

    first = _commit_one(db, svc, entity_id)
    second = _commit_one(db, svc, entity_id)
    # The newer action is what an undo targets...
    svc.undo(
        source_entity_type="purchase_request",
        source_entity_id=entity_id,
        actor_id=None,
        reason="second one was wrong",
        has_permission=True,
    )
    rows = {
        str(r.id): r.status
        for r in db.query(SlaFormAction)
        .filter(SlaFormAction.source_entity_id == entity_id)
        .all()
    }
    assert rows[second.action_id] == "undone"
    assert rows[first.action_id] == FORM_ACTION_COMMITTED


def test_two_undos_racing_leave_one_winner(db, monkeypatch):
    """AC-PGE-6: the second caller is refused rather than reversing it twice."""
    from app.services.error_handler import AppException

    spy = _RevertSpy()
    _register_invertible(monkeypatch, spy)
    entity_id = _entity_id()
    svc = _service(db)
    _commit_one(db, svc, entity_id)

    kwargs = dict(
        source_entity_type="purchase_request",
        source_entity_id=entity_id,
        actor_id=None,
        reason="mistake",
        has_permission=True,
    )
    svc.undo(**kwargs)
    with pytest.raises(AppException):
        svc.undo(**kwargs)

    assert len(spy.restored) == 1, "the inverse must run exactly once"


def _seed_tracker(db, *, entity_id, policy_id, is_responded=False, is_resolved=False):
    """A form-SLA stage tracker for this form. policy_id / current_tier / due_at are
    NOT NULL."""
    from app.models.sla import ConversationSLATracking

    tracker = ConversationSLATracking(
        policy_id=policy_id,
        current_tier=1,
        due_at=datetime.utcnow() + timedelta(hours=4),
        source_entity_type="purchase_request",
        source_entity_id=entity_id,
        is_responded=is_responded,
        is_resolved=is_resolved,
    )
    db.add(tracker)
    db.commit()
    return tracker


def test_undo_is_refused_once_the_next_stage_has_been_acted_on(db, monkeypatch):
    """AC-PG-2, the guardrail this whole feature leans on: once the stage the action
    opened has been worked, undoing it would throw that work away."""
    from app.models.sla import SLAPolicy
    from app.services.form_action_undo import BLOCK_NEXT_STAGE_ACTED, evaluate

    spy = _RevertSpy()
    _register_invertible(monkeypatch, spy)
    entity_id = _entity_id()
    svc = _service(db)

    policy = SLAPolicy(code=MARKER + "guard", name=MARKER + "guard")
    db.add(policy)
    db.flush()

    _commit_one(db, svc, entity_id)
    row = db.query(SlaFormAction).filter(SlaFormAction.source_entity_id == entity_id).one()

    # Pin a spawned stage onto the committed action, then have someone respond to it.
    spawned = _seed_tracker(db, entity_id=entity_id, policy_id=policy.id, is_responded=True)
    row.spawned_tracking_id = str(spawned.id)
    db.commit()

    verdict = evaluate(
        db,
        source_entity_type="purchase_request",
        source_entity_id=entity_id,
        has_permission=True,
    )
    assert verdict.can_undo is False
    assert verdict.blocked_reason == BLOCK_NEXT_STAGE_ACTED

    from app.services.error_handler import AppException

    with pytest.raises(AppException):
        svc.undo(
            source_entity_type="purchase_request",
            source_entity_id=entity_id,
            actor_id=None,
            reason="too late",
            has_permission=True,
        )
    assert spy.restored == [], "nothing may be reversed once the next stage was worked"


def test_undo_is_allowed_while_the_next_stage_is_untouched(db, monkeypatch):
    """The other side of the guardrail - an untouched spawned stage does not block."""
    from app.models.sla import SLAPolicy
    from app.services.form_action_undo import evaluate

    spy = _RevertSpy()
    _register_invertible(monkeypatch, spy)
    entity_id = _entity_id()
    svc = _service(db)

    policy = SLAPolicy(code=MARKER + "open", name=MARKER + "open")
    db.add(policy)
    db.flush()

    _commit_one(db, svc, entity_id)
    row = db.query(SlaFormAction).filter(SlaFormAction.source_entity_id == entity_id).one()
    spawned = _seed_tracker(db, entity_id=entity_id, policy_id=policy.id)
    row.spawned_tracking_id = str(spawned.id)
    db.commit()

    assert evaluate(
        db,
        source_entity_type="purchase_request",
        source_entity_id=entity_id,
        has_permission=True,
    ).can_undo is True


# --------------------------------------------------------------------------------------
# Registry integrity - the checks that stop a wrapped method drifting away from its
# declaration. Six of these runners had wrong kwargs when first written; introspection
# caught them, so it belongs in CI rather than in a one-off script.
# --------------------------------------------------------------------------------------


def test_every_registered_runner_passes_kwargs_the_real_method_accepts():
    import ast
    import inspect

    import app.services.form_actions  # noqa: F401  (registers the actions)
    from app.services.complaints_service import ComplaintService
    from app.services.procurement_service import (
        PurchaseRequestService,
        StockInquiryService,
    )
    import app.services.tickets_service as tickets_service

    wrapped = {
        "decide_approval", "set_pending_approval", "reject_submitted",
        "_finalize_request", "void_request", "project_sales_approve_inquiry",
        "project_sales_reject_inquiry", "purchasing_reject_inquiry",
        "update_inquiry_and_reply", "void_inquiry", "decide_complaint",
        "_finalize_complaint", "update_resolution_and_reply",
    }

    source = inspect.getsource(app.services.form_actions)
    passed: dict[str, set[str]] = {}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in wrapped:
                passed.setdefault(node.func.attr, set()).update(
                    k.arg for k in node.keywords if k.arg
                )

    owners = {}
    for cls in (PurchaseRequestService, StockInquiryService, ComplaintService):
        for name, fn in vars(cls).items():
            if name in wrapped:
                owners[name] = fn
    owners["update_resolution_and_reply"] = tickets_service.update_resolution_and_reply

    problems = []
    for name, kwargs in passed.items():
        fn = owners.get(name)
        assert fn is not None, f"{name} is wrapped but its owner was not found"
        accepted = set(inspect.signature(fn).parameters) - {"self", "db"}
        unknown = sorted(k for k in kwargs if k not in accepted)
        if unknown:
            problems.append(f"{name} passes {unknown}, accepts {sorted(accepted)}")

    assert not problems, "registry runners drifted from their methods:\n" + "\n".join(problems)


def test_every_registered_action_declares_a_known_form_type():
    """A FORM action's entity type has to be one the SLA engine knows.

    Only a form action: since S6b the same registry also holds RECORD actions - a
    product, a brand, a delivery order - and none of those is a form submission, so
    `FORM_SLA_TYPES` has nothing to say about them. A record action is the one that
    declares a `permission` (it is parked through the generic /pending-actions route,
    which has no slug of its own), which is the same split
    `tests/test_record_actions_s6b.py` makes.
    """
    import app.services.form_actions  # noqa: F401
    import app.services.record_actions  # noqa: F401
    from app.services.form_action_registry import REGISTRY
    from app.services.form_sla_service import FORM_SLA_TYPES

    for key, action in REGISTRY.items():
        assert action.entity_types, f"{key} declares no entity types"
        if action.permission:
            continue
        for entity_type in action.entity_types:
            assert entity_type in FORM_SLA_TYPES, f"{key} declares unknown type {entity_type}"


def test_capture_columns_exist_on_the_model_they_snapshot():
    """A typo in a capture list would snapshot None and 'restore' None over a real
    value - silently wrong, and exactly what an undo must never do."""
    import app.services.form_actions  # noqa: F401
    from app.models.complaints import Complaint
    from app.models.procurement import PurchaseRequestHeader, StockInquiry
    from app.models.tickets import Ticket

    expected = {
        "pr.approval_decision": (PurchaseRequestHeader, (
            "approval_status", "status", "approved_at", "approved_by",
            "rejected_by_id", "approval_signature_ref", "approval_comments")),
        "pr.send_for_approval": (PurchaseRequestHeader, (
            "approval_status", "approved_at", "approved_by",
            "approval_signature_ref", "approval_comments",
            "requested_approval_by_user_id")),
        "pr.finalize": (PurchaseRequestHeader, ("status",)),
        "pr.void": (PurchaseRequestHeader, ("status", "voided_by", "voided_at", "void_reason")),
        "si.project_sales_approve": (StockInquiry, (
            "status", "rejection_reason", "rejected_at", "rejected_by", "rejected_from")),
        "si.purchasing_respond": (StockInquiry, ("status", "last_responded_by", "last_responded_at")),
        "si.void": (StockInquiry, ("status", "voided_by", "voided_at", "void_reason")),
        "cx.finalize": (Complaint, ("status", "resolved_at", "resolved_by")),
        "tk.resolve": (Ticket, (
            "resolution_html", "resolution_text", "resolved_by", "resolved_at",
            "resolution_time_hours", "status")),
    }

    for key, (model, columns) in expected.items():
        mapped = {c.name for c in model.__table__.columns}
        missing = sorted(c for c in columns if c not in mapped)
        assert not missing, f"{key} captures columns absent from {model.__tablename__}: {missing}"


def test_audit_rows_are_actually_written(db, monkeypatch):
    """`audit_logs.action` carries a CHECK constraint (CREATE/READ/UPDATE/DELETE/IMPORT).
    A custom verb is rejected, and because audit failures are swallowed by design the
    breakage is invisible - every undo simply left no trail. Assert the rows land."""
    from app.models.audit import AuditLog

    spy = _RevertSpy()
    _register_invertible(monkeypatch, spy)
    entity_id = _entity_id()
    svc = _service(db)

    _commit_one(db, svc, entity_id)
    svc.undo(
        source_entity_type="purchase_request",
        source_entity_id=entity_id,
        actor_id=None,
        reason="wrong request",
        has_permission=True,
    )

    rows = (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == "purchase_request", AuditLog.entity_id == entity_id)
        .all()
    )
    descriptions = [r.description or "" for r in rows]
    assert any("Action applied" in d for d in descriptions), descriptions
    undo_line = [d for d in descriptions if d.startswith("Undo:")]
    assert undo_line, f"no undo audit row written: {descriptions}"
    assert "wrong request" in undo_line[0], "the undo reason must reach the audit trail"
    # Every row must satisfy the CHECK constraint, or it never made it to the table.
    assert {r.action for r in rows} <= {"CREATE", "READ", "UPDATE", "DELETE", "IMPORT"}


def test_eligibility_survives_a_row_committed_but_not_yet_stamped(db, monkeypatch):
    """`commit_one` flips status to 'committed' in its claim UPDATE, and `committed_at`
    is written a moment later by the execute. In that window the row is committed with a
    NULL timestamp - and Postgres DESC sorts NULLs FIRST, so `last_committed` picks it,
    then compares `committed_at > None` and raises:

        Only '=', '!=', 'is_()' ... operators can be used with None/True/False

    A user approving a form hits this whenever the eligibility poll lands mid-commit.
    """
    from app.services.form_action_undo import evaluate

    spy = _RevertSpy()
    _register_invertible(monkeypatch, spy)
    entity_id = _entity_id()
    svc = _service(db)

    _commit_one(db, svc, entity_id)
    # A second row caught mid-commit: claimed, not yet stamped.
    half = SlaFormAction(
        action_key="zzt.undoable",
        source_entity_type="purchase_request",
        source_entity_id=entity_id,
        payload_json={"request_id": entity_id},
        prior_state_json={},
        channel=FORM_ACTION_CHANNEL_UI,
        status=FORM_ACTION_COMMITTED,
        committed_at=None,
    )
    db.add(half)
    db.commit()

    verdict = evaluate(
        db,
        source_entity_type="purchase_request",
        source_entity_id=entity_id,
        has_permission=True,
    )
    assert verdict is not None


def test_contact_correction_names_the_restored_status_and_reason():
    """The contact was already told the form moved on, and that message cannot be
    unsent. The correction has to say what it went back to and why, or they are left
    guessing - "under review again" on its own says neither."""
    from app.services.form_action_notify import _status_label

    assert _status_label("pending_approval") == "Pending Approval"
    assert _status_label("processed_by_cs") == "Processed by Customer Service"
    # An unmapped code still reads as words, never as a raw column value.
    assert _status_label("awaiting_parts") == "Awaiting Parts"
    assert _status_label(None) == "its previous state"


def test_undo_notifies_the_contact_even_for_an_internal_only_action(db, monkeypatch):
    """AC-N-5 as revised: `tells_contact` describes the FORWARD action, and is not a
    reason to keep a reversal from the contact. Sending for approval never messages
    them, but undoing it moves the status they can see in the portal."""
    import app.services.form_action_notify as notify_mod

    sent: list[dict] = []
    monkeypatch.setattr(
        notify_mod,
        "_notify_contact",
        lambda db, record, *, number, reason: sent.append({"number": number, "reason": reason}),
    )

    spy = _RevertSpy()
    # tells_contact=False - an internal-only action, like pr.send_for_approval.
    from app.services import form_action_registry as reg

    monkeypatch.setitem(
        reg.REGISTRY,
        "zzt.internal",
        reg.FormAction(
            key="zzt.internal",
            entity_types=("purchase_request",),
            execute=spy.execute,
            capture=spy.capture,
            invert=spy.invert,
            resolve_event=lambda _p: "send_for_approval",
            tells_contact=False,
            label="Send for approval",
        ),
    )

    entity_id = _entity_id()
    svc = _service(db)
    _commit_one(db, svc, entity_id, key="zzt.internal")
    svc.undo(
        source_entity_type="purchase_request",
        source_entity_id=entity_id,
        actor_id=None,
        reason="sent it too early",
        has_permission=True,
    )

    assert sent, "the contact must be corrected even when the forward action was silent"
    assert sent[0]["reason"] == "sent it too early"


def test_correction_reports_the_displayed_state_not_the_raw_column():
    """PR/SF carry `status` AND `approval_status`, so a form at "Pending Approval" still
    reads `status='submitted'`. Undoing an approval and telling the contact it went
    "back to Submitted" contradicts the screen in front of them, which says Pending
    Approval. Mirrors getDisplayStatus in PurchaseRequestsList.tsx."""
    from app.services.form_action_notify import _pr_display_status

    class _H:
        def __init__(self, status, approval_status):
            self.status = status
            self.approval_status = approval_status

    # The case that prompted this: undo an approval -> approval_status back to pending.
    assert _pr_display_status(_H("submitted", "pending")) == "Pending Approval"
    # No decision yet -> the lifecycle status is the truth.
    assert _pr_display_status(_H("submitted", None)) == "Submitted"
    # Terminal CS states outrank the approval decision, or an approved-then-processed
    # form would report "Approved" while every screen says "Processed by CS".
    assert _pr_display_status(_H("processed_by_cs", "approved")) == "Processed by Customer Service"
    assert _pr_display_status(_H("closed", "approved")) == "Closed"
    assert _pr_display_status(_H("voided", "pending")) == "Voided"
    assert _pr_display_status(_H("draft", None)) == "Draft"


# --------------------------------------------------------------------------------------
# Review hardening (2026-08-11): pending blocks undo; tracker void/reopen leave a trail
# --------------------------------------------------------------------------------------


def test_undo_is_refused_while_a_new_action_is_pending(db, monkeypatch):
    """A parked action makes the last committed one off-limits: reversing underneath it
    changes the premise the pending action was requested on. The FE hides Undo in this
    state; this pins the API refusing it too."""
    from app.services.form_action_undo import BLOCK_ACTION_PENDING, evaluate

    spy = _RevertSpy()
    _register_invertible(monkeypatch, spy)
    entity_id = _entity_id()
    svc = _service(db)

    _commit_one(db, svc, entity_id)  # the undoable action
    svc.dispatch(  # a NEW action parked on the same form
        action_key="zzt.undoable",
        entity_type="purchase_request",
        entity_id=entity_id,
        payload={"request_id": entity_id, "action": "approved"},
        actor_id=None,
        channel=FORM_ACTION_CHANNEL_UI,
        grace_seconds=60,
    )

    verdict = evaluate(
        db,
        source_entity_type="purchase_request",
        source_entity_id=entity_id,
        has_permission=True,
    )
    assert verdict.can_undo is False
    assert verdict.blocked_reason == BLOCK_ACTION_PENDING

    from app.services.error_handler import AppException

    with pytest.raises(AppException):
        svc.undo(
            source_entity_type="purchase_request",
            source_entity_id=entity_id,
            actor_id=None,
            reason="racing the pending action",
            has_permission=True,
        )
    assert spy.restored == []


def test_void_tracker_leaves_a_voided_event_and_no_completer(db):
    """The tracker table cannot say "voided" - is_resolved is its only terminal flag -
    so the event log is the ONLY record distinguishing an undo-swept stage from work
    somebody completed. resolved_by must stay NULL: nobody completed it."""
    from app.models.sla import ConversationSLAEventLog, SLAPolicy
    from app.services.form_action_undo import void_tracker

    policy = SLAPolicy(code=MARKER + "void", name=MARKER + "void")
    db.add(policy)
    db.flush()
    tracker = _seed_tracker(db, entity_id=_entity_id(), policy_id=policy.id)
    tracker.resolved_by = "someone"  # stale value that must be cleared, not kept
    db.commit()

    void_tracker(db, str(tracker.id), "undo of the approval")

    db.refresh(tracker)
    assert tracker.is_resolved is True
    assert tracker.resolved_by is None
    events = (
        db.query(ConversationSLAEventLog)
        .filter(ConversationSLAEventLog.sla_tracking_id == str(tracker.id))
        .all()
    )
    assert [e.event_type for e in events] == ["voided"]
    assert events[0].reason == "undo of the approval"


def test_reopen_tracker_writes_a_reopened_event(db):
    """The reopened stage carries an event-log entry so its history shows the rewind,
    not just a tracker that mysteriously became unresolved again."""
    from app.models.sla import ConversationSLAEventLog, SLAPolicy
    from app.services.form_action_undo import reopen_tracker

    policy = SLAPolicy(code=MARKER + "reopen", name=MARKER + "reopen")
    db.add(policy)
    db.flush()
    tracker = _seed_tracker(
        db, entity_id=_entity_id(), policy_id=policy.id, is_resolved=True
    )

    reopen_tracker(db, str(tracker.id))

    db.refresh(tracker)
    assert tracker.is_resolved is False
    assert tracker.resolved_at is None
    events = (
        db.query(ConversationSLAEventLog)
        .filter(ConversationSLAEventLog.sla_tracking_id == str(tracker.id))
        .all()
    )
    assert [e.event_type for e in events] == ["reopened"]


# --------------------------------------------------------------------------------------
# Ultra-review hardening (PR #123): immediate path, undo claim release, terminal forms
# --------------------------------------------------------------------------------------


def test_immediate_path_never_persists_a_pending_row(db, monkeypatch):
    """Services commit internally, and a durable pending row with commit_at=NULL is
    invisible to the sweep AND the lazy commit - a crash then bricks the form behind
    the one-pending unique index. So the immediate path must hold the row out of the
    session until the action has run."""
    observed: list[int] = []

    class _PeekSpy(_Spy):
        def execute(self, db_, payload):
            # What the wrapped method would see if it committed right now.
            observed.append(
                db_.query(SlaFormAction)
                .filter(SlaFormAction.source_entity_id == payload["request_id"])
                .count()
            )
            super().execute(db_, payload)

    spy = _PeekSpy()
    _register(monkeypatch, spy)
    entity_id = _entity_id()

    _service(db).dispatch(
        action_key="zzt.test_action",
        entity_type="purchase_request",
        entity_id=entity_id,
        payload={"request_id": entity_id},
        actor_id=None,
        channel=FORM_ACTION_CHANNEL_UI,
        grace_seconds=0,
    )

    assert observed == [0], "no history row may exist while the action runs"
    rows = (
        db.query(SlaFormAction)
        .filter(SlaFormAction.source_entity_id == entity_id)
        .all()
    )
    assert [r.status for r in rows] == [FORM_ACTION_COMMITTED]


def test_immediate_failure_records_a_failed_row_not_a_pending_one(db, monkeypatch):
    """The failure still lands in history - but terminal, never pending."""

    class _BoomSpy(_Spy):
        def execute(self, _db, _payload):
            raise RuntimeError("wrapped method exploded")

    spy = _BoomSpy()
    _register(monkeypatch, spy)
    entity_id = _entity_id()

    with pytest.raises(RuntimeError):
        _service(db).dispatch(
            action_key="zzt.test_action",
            entity_type="purchase_request",
            entity_id=entity_id,
            payload={"request_id": entity_id},
            actor_id=None,
            channel=FORM_ACTION_CHANNEL_UI,
            grace_seconds=0,
        )

    rows = (
        db.query(SlaFormAction)
        .filter(SlaFormAction.source_entity_id == entity_id)
        .all()
    )
    assert [r.status for r in rows] == ["failed"]
    assert "exploded" in rows[0].error_text


def test_failed_undo_releases_the_claim_so_a_retry_can_succeed(db, monkeypatch):
    """The claim commits before the reversal runs (needed for the two-undo race), so
    a failing invert must hand the claim BACK - otherwise the row reads `undone`, the
    domain was never reversed, and every retry is refused as already-undone forever."""

    class _FlakySpy(_RevertSpy):
        def __init__(self):
            super().__init__()
            self.attempts = 0

        def invert(self, db_, record):
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError("connection dropped mid-reversal")
            super().invert(db_, record)

    spy = _FlakySpy()
    _register_invertible(monkeypatch, spy)
    entity_id = _entity_id()
    svc = _service(db)
    _commit_one(db, svc, entity_id)

    with pytest.raises(RuntimeError):
        svc.undo(
            source_entity_type="purchase_request",
            source_entity_id=entity_id,
            actor_id=None,
            reason="first try",
            has_permission=True,
        )

    row = db.query(SlaFormAction).filter(SlaFormAction.source_entity_id == entity_id).one()
    assert row.status == FORM_ACTION_COMMITTED, "claim must be released on failure"
    assert row.undone_at is None and row.undo_reason is None

    # The retry now runs the whole reversal.
    svc.undo(
        source_entity_type="purchase_request",
        source_entity_id=entity_id,
        actor_id=None,
        reason="second try",
        has_permission=True,
    )
    db.refresh(row)
    assert row.status == "undone"
    assert spy.restored, "the retry actually reversed the state"


def test_undo_is_refused_on_a_voided_form(db, monkeypatch):
    """The void routes do not go through the dispatcher, so the guardrail cannot see
    the transition in sibling action rows - it must read the entity itself. Undoing
    on top would silently un-void the form."""
    from app.models.procurement import PurchaseRequestHeader
    from app.services.form_action_undo import BLOCK_STATUS_MOVED, evaluate

    spy = _RevertSpy()
    _register_invertible(monkeypatch, spy)
    entity_id = _entity_id()
    svc = _service(db)
    _commit_one(db, svc, entity_id)

    db.query(PurchaseRequestHeader).filter(
        PurchaseRequestHeader.id == entity_id
    ).update({"status": "voided"}, synchronize_session=False)
    db.commit()

    verdict = evaluate(
        db,
        source_entity_type="purchase_request",
        source_entity_id=entity_id,
        has_permission=True,
    )
    assert verdict.can_undo is False
    assert verdict.blocked_reason == BLOCK_STATUS_MOVED

    from app.services.error_handler import AppException

    with pytest.raises(AppException):
        svc.undo(
            source_entity_type="purchase_request",
            source_entity_id=entity_id,
            actor_id=None,
            reason="should be refused",
            has_permission=True,
        )
    assert spy.restored == []


def test_undo_is_refused_when_the_form_row_is_gone(db, monkeypatch):
    """A hard-deleted form has nothing to restore onto - refuse instead of half-running
    the tracker side effects."""
    from app.models.procurement import PurchaseRequestHeader
    from app.services.form_action_undo import BLOCK_STATUS_MOVED, evaluate

    spy = _RevertSpy()
    _register_invertible(monkeypatch, spy)
    entity_id = _entity_id()
    svc = _service(db)
    _commit_one(db, svc, entity_id)

    db.query(PurchaseRequestHeader).filter(
        PurchaseRequestHeader.id == entity_id
    ).delete(synchronize_session=False)
    db.commit()

    verdict = evaluate(
        db,
        source_entity_type="purchase_request",
        source_entity_id=entity_id,
        has_permission=True,
    )
    assert verdict.can_undo is False
    assert verdict.blocked_reason == BLOCK_STATUS_MOVED


def test_send_for_approval_declares_it_tells_the_contact():
    """set_pending_approval messages the contact since the 2026-08 fix; the undo
    dialog keys its disclosure off this flag, so a stale False hides the one
    consequence the dialog exists to disclose."""
    import app.services.form_actions  # noqa: F401
    from app.services.form_action_registry import get_action

    assert get_action("pr.send_for_approval").tells_contact is True


def test_si_respond_capture_widens_to_the_submitted_fields(db):
    """update_inquiry_and_reply writes every submitted field, so the snapshot must
    cover them - a fixed 3-column capture makes undo restore a half-reverted record."""
    import app.services.form_actions  # noqa: F401
    from app.services.form_action_registry import get_action
    from app.models.procurement import StockInquiry

    inquiry = StockInquiry(
        id=str(uuid.uuid4()),
        inquiry_number=f"{MARKER}si",
        status="pending_purchasing",
        remark="original remark",
        quantity=5,
    )
    db.add(inquiry)
    db.commit()

    action = get_action("si.purchasing_respond")
    snapshot = action.capture(
        db,
        {
            "inquiry_id": str(inquiry.id),
            "inquiry_data": {"remark": "edited remark", "quantity": 12},
        },
    )

    # Declared columns AND the payload-touched ones.
    assert snapshot["status"] == "pending_purchasing"
    assert snapshot["remark"] == "original remark"
    assert str(snapshot["quantity"]) == "5"
    assert "respond_inbox_url" in snapshot


def test_restore_never_coerces_date_like_free_text(db, monkeypatch):
    """An approver whose comment is '2025-10-01' must get their STRING back on undo,
    not a datetime written into a String column. Only values that were datetimes at
    capture time round-trip as datetimes (the $dt marker)."""
    from app.services.form_actions import _jsonable, _restore

    assert _restore(_jsonable("2025-10-01")) == "2025-10-01"
    assert _restore(_jsonable("plain text")) == "plain text"
    stamp = datetime(2026, 8, 11, 9, 30, 0)
    assert _restore(_jsonable(stamp)) == stamp
    # Legacy snapshots stored datetimes as bare ISO text - passes through unchanged
    # (Postgres casts it on write to a timestamp column).
    assert _restore("2026-08-11T09:30:00") == "2026-08-11T09:30:00"


def test_contact_corrections_resolve_the_send_identifier(db, monkeypatch):
    """`contact_id` is the internal respond_contacts UUID; the send API needs the
    resolved identifier. Passing the raw FK 400s every correction, silently."""
    from app.models.procurement import StockInquiry
    from app.services import form_action_notify
    from app.services.procurement_service import StockInquiryService

    from app.models.access import RespondContact

    # The resolver verifies against respond_contacts, so seed the real chain: an
    # internal UUID row whose respond_io_id is what the send API actually needs.
    internal_uuid = str(uuid.uuid4())
    db.add(RespondContact(id=internal_uuid, respond_io_id="123456789", phone_number="+60123456789"))
    db.commit()
    inquiry = StockInquiry(
        id=str(uuid.uuid4()),
        inquiry_number=f"{MARKER}si-notify",
        status="pending_purchasing",
        contact_id=internal_uuid,
        respond_inbox_url=f"https://app.respond.io/space/sp_x/inbox/{internal_uuid}",
    )
    db.add(inquiry)
    db.commit()

    sent: list[dict] = []
    monkeypatch.setattr(
        StockInquiryService,
        "_enqueue_stock_inquiry_respond_message",
        lambda self, **kwargs: sent.append(kwargs),
    )

    class _Record:
        source_entity_type = "stock_inquiry"
        source_entity_id = str(inquiry.id)
        id = str(uuid.uuid4())

    form_action_notify._notify_contact(
        db, _Record(), number=f"{MARKER}si-notify", reason="testing"
    )

    assert len(sent) == 1
    identifier = sent[0]["identifier"]
    # A legacy inbox URL carries the INTERNAL uuid; the resolver must still hand the
    # send path the numeric respond_io_id, never the raw FK.
    assert identifier != internal_uuid
    assert identifier == "123456789"


def test_last_terminal_outcome_surfaces_the_voided_action(db, monkeypatch):
    """A parked action that was voided (or failed) must be reportable - `pending`
    going null looks identical to success otherwise, and the user walks away
    believing their action applied (AC-U-4)."""
    spy = _Spy()
    _register(monkeypatch, spy)
    entity_id = _entity_id()
    svc = _service(db)

    parked = svc.dispatch(
        action_key="zzt.test_action",
        entity_type="purchase_request",
        entity_id=entity_id,
        payload={"request_id": entity_id},
        actor_id=None,
        channel=FORM_ACTION_CHANNEL_UI,
        grace_seconds=30,
    )
    row = db.query(SlaFormAction).filter(SlaFormAction.id == parked.action_id).one()
    svc.void_as_ineligible(row, "someone else decided the form")

    terminal = svc.last_terminal_outcome("purchase_request", entity_id)
    assert terminal is not None
    assert str(terminal.id) == parked.action_id
    assert terminal.status == "ineligible"
    assert "someone else decided" in terminal.error_text


def test_undo_notifications_carry_whatsapp_template_data(db, monkeypatch):
    """Out-of-window WhatsApp can only send an APPROVED template, chosen by
    `whatsapp_use_case` and filled from `whatsapp_context_vars`. Without these keys
    the delivery falls back to the sla_assignment use case with no vars - the
    escalation template filled with dashes."""
    import uuid as _uuid

    from app.models.sla import SLAPolicy
    from app.models.user import User
    from app.services import form_action_notify

    # A recipient distinct from the actor, or the self-notify guard drops the send.
    recipient = User(
        id=str(_uuid.uuid4()),
        email=f"{MARKER}undo-wa@example.com",
        name="Recipient",
    )
    db.add(recipient)
    policy = SLAPolicy(code=MARKER + "wa", name=MARKER + "wa")
    db.add(policy)
    db.flush()

    entity_id = _entity_id()
    _seed_entity(db, entity_id)
    reopened = _seed_tracker(db, entity_id=entity_id, policy_id=policy.id)
    reopened.assigned_to_id = str(recipient.id)
    db.commit()

    captured: list[dict] = []
    from app.services.notification_service import NotificationService

    monkeypatch.setattr(
        NotificationService,
        "create_with_channel_preferences",
        lambda self, **kwargs: captured.append(kwargs),
    )

    class _Record:
        action_key = "pr.approval_decision"
        source_entity_type = "purchase_request"
        source_entity_id = entity_id
        spawned_tracking_id = None
        prior_tracking_id = str(reopened.id)
        id = str(_uuid.uuid4())

    form_action_notify.notify_undo(db, _Record(), actor_id=None, reason="tested")

    staff = [k for k in captured if k.get("type") == "sla_form_action_undone"]
    assert len(staff) == 1
    data = staff[0]["data"]
    assert data["whatsapp_use_case"] == "form_action_reopened"
    assert data["whatsapp_context_vars"]["message"]
    assert data["whatsapp_context_vars"]["entity_number"]


def test_undo_use_cases_are_admin_configurable():
    """The two undo WhatsApp use cases must be in TEMPLATE_DEFAULT_USE_CASES, or the
    WhatsApp Templates admin page cannot list them and set_default refuses them -
    the seeded defaults would be frozen at whatever migration 312c chose."""
    from app.models.respond_template import TEMPLATE_DEFAULT_USE_CASES

    assert "form_action_voided" in TEMPLATE_DEFAULT_USE_CASES
    assert "form_action_reopened" in TEMPLATE_DEFAULT_USE_CASES
