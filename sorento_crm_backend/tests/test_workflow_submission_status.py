"""F1 gate - a submission's status lives on the submission, in the status engine.

The premise this file pins: ``workflow_submissions.current_state_code`` was a
``VARCHAR(64)`` fed by a state machine embedded in ``workflow_form_versions.schema``.
ADR-0001 puts the graph in the status engine, and after F0 there were **two**
validators describing that one JSONB column which disagreed with each other. F1
ends that, and all five ``workflow_*`` tables hold **0 rows**, so this is a reshape
with nothing to reconcile.

Contrast with the slice before this one. ``complaint`` registered on a key-valued
``VARCHAR`` because its column predates the engine and 51 live rows plus every
branch site read the key by name. ``workflow_submission`` has no such excuse: it
registers **FK-based natively** (``status_attr="status_id"``), which is also what
makes ``count_records`` exact under a forked graph -- an id belongs to exactly one
graph where a key is deliberately shared across all of them.

Every test traces to an AC in
``documentation/plans/forms-platform/forms-platform-acceptance-criteria.md``.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy import String

from app.form_engine.schemas import FORM_SCHEMA_VERSION
from app.models.status import TRIGGER_MANUAL, Status, StatusTransition
from app.models.workflow_forms import (
    WorkflowFormDefinition,
    WorkflowFormVersion,
    WorkflowSubmission,
    WorkflowSubmissionTransitionLog,
)
from app.services.error_handler import AppException
from app.services.status_service import (
    assert_status_deletable,
    available_transitions,
    fork_graph,
    graph_for_record,
    initial_status,
    migrate_records,
    resolve_graph,
    status_entities_payload,
    validate_graph,
)
from app.services.workflow_forms_service import WorkflowFormsService
from app.services.workflow_submission_status_graph import (
    WORKFLOW_SUBMISSION_ENTITY_TYPE,
    WORKFLOW_SUBMISSION_STATUS_KEYS,
    WORKFLOW_SUBMISSION_STATUS_SEEDS,
    WORKFLOW_SUBMISSION_TRANSITION_SEEDS,
    register_workflow_submission_status_entity,
    seed_workflow_submission_status_graph,
)
from app.status_engine import registry as status_registry

from ._pg_fixture import blank_session, unique_code

APP = Path(__file__).resolve().parent.parent / "app"

# The generic vocabulary the DEFAULT graph ships. Written out rather than derived
# from the seeds so widening it has to be done twice, on purpose, in two places
# (AC-F1-4). A real form is expected to FORK; the default is not the place to add
# "in_repair" or "awaiting_parts".
DEFAULT_GRAPH_KEYS = {"draft", "submitted", "approved", "rejected"}

# The four edges the retired ``default_draft_schema`` performed, re-expressed as
# engine edges. Nothing is added for symmetry.
DEFAULT_GRAPH_EDGES = {
    ("draft", "submitted"),  # Submit
    ("submitted", "approved"),  # Approve
    ("submitted", "rejected"),  # Reject
    ("submitted", "draft"),  # Send back
}

# A minimal publishable FormDocument: one page, one section, one answer-bearing
# field. Anything smaller fails the publish gate ("Page 1 is empty").
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
                        }
                    ],
                }
            ],
        }
    ],
}


@pytest.fixture(autouse=True)
def _isolate_registry():
    """The status registry is process-global; snapshot and restore it."""
    saved = dict(status_registry._REGISTRY)
    yield
    status_registry._REGISTRY.clear()
    status_registry._REGISTRY.update(saved)


# ------------------------------------------------------------------ helpers


def _seeded(db):
    seed_workflow_submission_status_graph(db)
    db.flush()
    return resolve_graph(db, WORKFLOW_SUBMISSION_ENTITY_TYPE, None)


def _definition(db, *, publish: bool = True, doc=None) -> WorkflowFormDefinition:
    """A definition with a published version, built by hand.

    Deliberately not via the service: the graph tests must not depend on the
    service's own contract, or one broken assumption reads as twenty failures.
    """
    document = doc if doc is not None else FORM_DOC
    definition = WorkflowFormDefinition(
        id=str(uuid.uuid4()),
        code=unique_code("wfdef").lower(),
        name=f"{unique_code('Form')} definition",
        draft_schema=document,
    )
    db.add(definition)
    db.flush()
    if publish:
        version = WorkflowFormVersion(
            id=str(uuid.uuid4()),
            definition_id=definition.id,
            version_number=1,
            schema=document,
        )
        db.add(version)
        db.flush()
        definition.published_version_id = version.id
        db.flush()
    return definition


def _version_of(db, definition) -> WorkflowFormVersion:
    return (
        db.query(WorkflowFormVersion)
        .filter(WorkflowFormVersion.id == definition.published_version_id)
        .one()
    )


def _submission(db, definition, status: Status) -> WorkflowSubmission:
    row = WorkflowSubmission(
        id=str(uuid.uuid4()),
        definition_id=definition.id,
        version_id=_version_of(db, definition).id,
        status_id=status.id,
        header_data={"title": f"{unique_code('answer')}"},
    )
    db.add(row)
    db.flush()
    return row


def _created(db, definition, *, user_id: str = "zzt-user", answers=None, lines=None):
    """A submission through the service, which is what stamps the initial status."""
    return WorkflowFormsService(db).create_submission(
        definition.id,
        answers if answers is not None else {"title": "ZZT answer"},
        lines if lines is not None else [],
        user_id,
    )


def _edge_keys(graph) -> set:
    by_id = {s.id: s.key for s in graph.statuses}
    return {(by_id[t.from_status_id], by_id[t.to_status_id]) for t in graph.transitions}


def _logs(db, submission):
    return (
        db.query(WorkflowSubmissionTransitionLog)
        .filter(WorkflowSubmissionTransitionLog.submission_id == submission.id)
        .order_by(WorkflowSubmissionTransitionLog.created_at)
        .all()
    )


def _python_sources():
    for path in APP.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        yield path


# ============================================================== AC-F1-1
# The column move itself.


def test_the_submission_carries_a_status_id_fk_to_statuses():
    """The engine loads records by this FK. A ``Column(String)`` here would
    reproduce the pg-UUID-vs-varchar drift that broke ``user_sessions.id`` on
    production, and a nullable one would let a status-less submission exist,
    which no graph could ever move."""
    column = WorkflowSubmission.__table__.c["status_id"]
    assert isinstance(column.type, PGUUID)
    assert column.type.as_uuid is False, "ids are str-valued UUIDs across this codebase"
    assert column.nullable is False
    assert {fk.target_fullname for fk in column.foreign_keys} == {"statuses.id"}


def test_the_retired_state_code_column_is_dropped_not_kept_beside_it():
    """0 rows means there is nothing to reconcile, so there is no dual-write and
    no compatibility column. Keeping both is how two sources of truth start."""
    assert "current_state_code" not in WorkflowSubmission.__table__.c


def test_status_id_is_indexed_because_every_listing_filters_on_it():
    """The retired column declared ``index=True`` and the list/export paths filter
    on the submission's state. Losing the index in the reshape turns every
    submissions listing into a sequential scan."""
    indexed = {
        column.name
        for index in WorkflowSubmission.__table__.indexes
        for column in index.columns
    }
    assert "status_id" in indexed


def test_a_submission_can_be_read_back_with_its_status_joined():
    """The FE may not render UUIDs, so a submission has to reach a serializer
    holding the status KEY and LABEL, not only the id. Pinning the relationship
    plus the two derived attributes is what lets ``WorkflowSubmissionOut`` be built
    straight off the ORM row in the list-query registry."""
    with blank_session() as db:
        graph = _seeded(db)
        definition = _definition(db)
        row = _submission(db, definition, graph.by_key("draft"))
        db.refresh(row)
        assert row.status is not None and row.status.key == "draft"
        assert row.status_key == "draft"
        assert row.status_label == graph.by_key("draft").label


# ============================================================== AC-F1-7
# The audit trail's columns.


def test_the_transition_log_keys_by_status_id_not_by_code():
    with blank_session():
        pass  # no database needed; the shape is the assertion
    columns = WorkflowSubmissionTransitionLog.__table__.c
    for name in ("from_status_id", "to_status_id"):
        assert isinstance(columns[name].type, PGUUID)
        assert columns[name].type.as_uuid is False
        assert {fk.target_fullname for fk in columns[name].foreign_keys} == {"statuses.id"}
    assert isinstance(columns["status_transition_id"].type, PGUUID)
    assert {
        fk.target_fullname for fk in columns["status_transition_id"].foreign_keys
    } == {"status_transitions.id"}


def test_from_status_id_is_nullable_and_to_status_id_is_not():
    """``from_status_id`` is nullable for the first entry into the graph; a log row
    with no destination would record nothing at all."""
    columns = WorkflowSubmissionTransitionLog.__table__.c
    assert columns["from_status_id"].nullable is True
    assert columns["to_status_id"].nullable is False


def test_the_authorising_edge_reference_survives_the_edge_being_deleted():
    """An admin editing a graph deletes ``status_transitions`` rows. History must
    outlive that edit, so the log's reference to the edge that authorised the move
    is nullable rather than a cascade that would erase the trail."""
    assert (
        WorkflowSubmissionTransitionLog.__table__.c["status_transition_id"].nullable
        is True
    )


def test_the_retired_log_columns_are_gone():
    columns = WorkflowSubmissionTransitionLog.__table__.c
    for name in ("from_state_code", "to_state_code", "transition_id"):
        assert name not in columns


# ============================================================== AC-F1-16
# Attribution columns gain the FK they were missing, and stay String.


def test_user_attribution_columns_declare_a_foreign_key_and_stay_string():
    """Free at 0 rows, and 35 other columns already declare it. They must stay
    ``String``: ``users.id`` is ``Column(String)``, and a ``uuid`` column cannot
    hold a foreign key to a ``text`` column."""
    targets = [
        (WorkflowFormDefinition, "created_by_user_id"),
        (WorkflowFormVersion, "created_by_user_id"),
        (WorkflowSubmission, "created_by_user_id"),
        (WorkflowSubmission, "updated_by_user_id"),
        (WorkflowSubmissionTransitionLog, "user_id"),
    ]
    for model, name in targets:
        column = model.__table__.c[name]
        assert isinstance(column.type, String), f"{model.__name__}.{name} must stay String"
        assert not isinstance(column.type, PGUUID)
        assert {fk.target_fullname for fk in column.foreign_keys} == {"users.id"}, (
            f"{model.__name__}.{name} must reference users.id"
        )
        assert all(
            fk.ondelete == "SET NULL" for fk in column.foreign_keys
        ), "deleting a user must not delete the record they created"


# ============================================================== AC-F1-2
# Registration: FK-native, unlike complaint's key-valued adapter.


def test_the_entity_registers_natively_on_the_status_id_fk():
    """``complaint`` needed ``status_attr="status"`` only because its column
    predates the engine. A new table has no such excuse, and going FK-native is
    what makes ``count_records`` exact under a fork."""
    register_workflow_submission_status_entity()
    entity = status_registry.get_status_entity(WORKFLOW_SUBMISSION_ENTITY_TYPE)
    assert entity is not None
    assert entity.status_attr == "status_id"
    assert entity.model is WorkflowSubmission
    assert WORKFLOW_SUBMISSION_ENTITY_TYPE == "workflow_submission"


def test_the_registry_advertises_scoped_graphs_for_this_entity():
    """The admin graph editor decides whether to offer a per-definition fork from
    this flag alone, so a missing ``scope_resolver`` hides the whole feature."""
    register_workflow_submission_status_entity()
    row = next(
        r
        for r in status_entities_payload()
        if r["entity_type"] == WORKFLOW_SUBMISSION_ENTITY_TYPE
    )
    assert row["supports_scoped_graphs"] is True
    assert row["scope_label"], "the admin copy needs a noun for the scope owner"


def test_records_are_counted_by_status_id():
    with blank_session() as db:
        graph = _seeded(db)
        register_workflow_submission_status_entity()
        entity = status_registry.get_status_entity(WORKFLOW_SUBMISSION_ENTITY_TYPE)
        definition = _definition(db)

        _submission(db, definition, graph.by_key("draft"))
        _submission(db, definition, graph.by_key("draft"))
        _submission(db, definition, graph.by_key("submitted"))

        assert entity.count_records(db, graph.by_key("draft").id) == 2
        assert entity.count_records(db, graph.by_key("submitted").id) == 1
        assert entity.count_records(db, graph.by_key("approved").id) == 0


def test_a_forked_definitions_rows_count_against_the_fork_not_the_default():
    """The reason FK-native beats key-valued here. Keys are shared across forks by
    design, so a key-based count would attribute a forked definition's rows to the
    default graph's status and let an admin delete a status out from under them."""
    with blank_session() as db:
        default = _seeded(db)
        register_workflow_submission_status_entity()
        entity = status_registry.get_status_entity(WORKFLOW_SUBMISSION_ENTITY_TYPE)

        forked_definition = _definition(db)
        fork = fork_graph(db, WORKFLOW_SUBMISSION_ENTITY_TYPE, forked_definition.id)
        _submission(db, forked_definition, fork.by_key("draft"))

        assert entity.count_records(db, fork.by_key("draft").id) == 1
        assert entity.count_records(db, default.by_key("draft").id) == 0


def test_counting_an_unknown_status_id_is_zero_not_an_error():
    with blank_session() as db:
        _seeded(db)
        register_workflow_submission_status_entity()
        entity = status_registry.get_status_entity(WORKFLOW_SUBMISSION_ENTITY_TYPE)
        assert entity.count_records(db, "00000000-0000-0000-0000-0000000000ff") == 0


def test_delete_is_blocked_while_submissions_hold_the_status():
    with blank_session() as db:
        graph = _seeded(db)
        register_workflow_submission_status_entity()
        definition = _definition(db)
        _submission(db, definition, graph.by_key("submitted"))

        submitted = graph.by_key("submitted")
        # Take the system flag out of the way: this asserts the RECORD guard.
        submitted.is_system = False
        db.flush()
        with pytest.raises(AppException) as err:
            assert_status_deletable(db, submitted)
        assert err.value.detail["code"] == "status_in_use"


def test_migrate_rewrites_the_fk_and_leaves_other_rows_alone():
    with blank_session() as db:
        graph = _seeded(db)
        register_workflow_submission_status_entity()
        definition = _definition(db)
        moved = [_submission(db, definition, graph.by_key("draft")) for _ in range(2)]
        staying = _submission(db, definition, graph.by_key("submitted"))

        count = migrate_records(db, graph.by_key("draft"), graph.by_key("submitted"))
        db.flush()

        assert count == 2
        for row in moved:
            db.refresh(row)
            assert row.status_id == graph.by_key("submitted").id
        db.refresh(staying)
        assert staying.status_id == graph.by_key("submitted").id


# ============================================================== AC-F1-4
# The default graph: deliberately minimal and generic.


def test_the_default_graph_key_set_is_pinned():
    """A real form forks. Widening the default would push a form-specific rung
    onto every other definition that inherits it, so the key set is asserted here
    to make widening a conscious act rather than a side effect."""
    assert set(WORKFLOW_SUBMISSION_STATUS_KEYS) == DEFAULT_GRAPH_KEYS
    assert len(WORKFLOW_SUBMISSION_STATUS_KEYS) == len(DEFAULT_GRAPH_KEYS), "no duplicates"
    assert {s.key for s in WORKFLOW_SUBMISSION_STATUS_SEEDS} == DEFAULT_GRAPH_KEYS

    with blank_session() as db:
        graph = _seeded(db)
        assert {s.key for s in graph.statuses} == DEFAULT_GRAPH_KEYS


def test_the_default_edges_are_pinned_and_mirror_the_retired_state_machine():
    """The retired ``default_draft_schema`` shipped exactly submit / approve /
    reject / send-back. Re-expressing the same four edges is what makes this slice
    a reshape rather than a redesign."""
    assert {
        (t.from_key, t.to_key) for t in WORKFLOW_SUBMISSION_TRANSITION_SEEDS
    } == DEFAULT_GRAPH_EDGES
    with blank_session() as db:
        assert _edge_keys(_seeded(db)) == DEFAULT_GRAPH_EDGES


def test_draft_is_the_only_initial_status_and_the_two_decisions_are_terminal():
    with blank_session() as db:
        graph = _seeded(db)
        assert [s.key for s in graph.statuses if s.is_initial] == ["draft"]
        assert {s.key for s in graph.statuses if s.is_terminal} == {"approved", "rejected"}
        assert initial_status(db, WORKFLOW_SUBMISSION_ENTITY_TYPE, None).key == "draft"


def test_the_default_graph_passes_the_engines_structural_validation():
    """``validate_graph`` runs after every admin write. A default graph that could
    not pass it would 422 the first edit an admin made to any form's statuses."""
    with blank_session() as db:
        _seeded(db)
        validate_graph(db, WORKFLOW_SUBMISSION_ENTITY_TYPE, None)


def test_every_default_status_carries_a_colour_and_an_ordered_slot():
    """The graph editor renders a node per status; a colourless one reads as a
    rendering bug. Gaps of ten let an admin slot a rung between two others."""
    with blank_session() as db:
        graph = _seeded(db)
        assert all(s.color_hex for s in graph.statuses)
        orders = [s.sort_order for s in graph.statuses]
        assert orders == sorted(orders) and len(set(orders)) == len(orders)
        assert all(o % 10 == 0 for o in orders)


def test_every_default_edge_is_manual():
    """``trigger_mode='auto'`` means the ENGINE fires the edge from a
    ``conditions_json`` tree, and a CHECK constraint requires those conditions.
    Nothing in the generic graph has a condition to evaluate."""
    with blank_session() as db:
        graph = _seeded(db)
        assert all(t.trigger_mode == TRIGGER_MANUAL for t in graph.transitions)


def test_seeded_default_rows_are_system_rows_in_the_default_scope():
    """Code resolves the initial status by flag and reporting groups by key, so an
    admin must not be able to delete or rename these rows out from under it. A
    FORK is admin-owned and deliberately not system."""
    with blank_session() as db:
        graph = _seeded(db)
        assert all(s.is_system for s in graph.statuses)
        rows = (
            db.query(Status)
            .filter(Status.entity_type == WORKFLOW_SUBMISSION_ENTITY_TYPE)
            .all()
        )
        assert rows and all(r.scope_id is None and r.tenant_id is None for r in rows)


def test_the_seed_corrects_drift_rather_than_skipping_it():
    """Idempotent here means "set where mismatch", not "insert where absent": an
    insert-if-absent seed can never repair a prior bad run, which is the whole
    reason a seed gets re-run."""
    with blank_session() as db:
        first = seed_workflow_submission_status_graph(db)
        db.flush()
        assert first["statuses_created"] == len(DEFAULT_GRAPH_KEYS)
        assert first["transitions_created"] == len(WORKFLOW_SUBMISSION_TRANSITION_SEEDS)

        graph = resolve_graph(db, WORKFLOW_SUBMISSION_ENTITY_TYPE, None)
        drifted = graph.by_key("submitted")
        original_id = drifted.id
        drifted.label = "Sent"
        drifted.sort_order = 999
        db.flush()

        second = seed_workflow_submission_status_graph(db)
        db.flush()
        assert second["statuses_created"] == 0, "a re-run must not duplicate rows"
        assert second["statuses_updated"] == 1

        repaired = resolve_graph(
            db, WORKFLOW_SUBMISSION_ENTITY_TYPE, None
        ).by_key("submitted")
        assert repaired.id == original_id, "correct in place, never re-create"
        assert repaired.sort_order != 999


def test_a_clean_re_run_reports_no_changes():
    with blank_session() as db:
        seed_workflow_submission_status_graph(db)
        db.flush()
        again = seed_workflow_submission_status_graph(db)
        db.flush()
        assert again == {
            "statuses_created": 0,
            "statuses_updated": 0,
            "transitions_created": 0,
            "transitions_updated": 0,
        }


# ============================================================== AC-F1-3
# Scoping: one engine, a graph per definition.


def test_the_scope_resolver_returns_the_submissions_definition_id():
    """This one callable is what lets an exchange request and a service complaint
    hold different states on one engine."""
    register_workflow_submission_status_entity()
    entity = status_registry.get_status_entity(WORKFLOW_SUBMISSION_ENTITY_TYPE)
    assert entity.scope_resolver is not None

    with blank_session() as db:
        graph = _seeded(db)
        definition = _definition(db)
        row = _submission(db, definition, graph.by_key("draft"))
        assert entity.scope_for(row) == definition.id


def test_an_unforked_definition_resolves_the_default_graph():
    """A definition that never overrides keeps inheriting, so a later edit to the
    default does not silently rewrite a tuned fork -- and, more importantly here,
    a brand new definition works with no configuration at all."""
    with blank_session() as db:
        default = _seeded(db)
        register_workflow_submission_status_entity()
        definition = _definition(db)
        row = _submission(db, definition, default.by_key("draft"))

        graph = graph_for_record(db, WORKFLOW_SUBMISSION_ENTITY_TYPE, row)
        assert graph.is_fork is False
        assert graph.resolved_scope_id is None
        assert {s.id for s in graph.statuses} == {s.id for s in default.statuses}


def test_a_forked_definition_resolves_its_own_graph():
    with blank_session() as db:
        _seeded(db)
        register_workflow_submission_status_entity()
        definition = _definition(db)
        fork = fork_graph(db, WORKFLOW_SUBMISSION_ENTITY_TYPE, definition.id)
        row = _submission(db, definition, fork.by_key("draft"))

        graph = graph_for_record(db, WORKFLOW_SUBMISSION_ENTITY_TYPE, row)
        assert graph.is_fork is True
        assert graph.resolved_scope_id == definition.id


def test_a_fork_keeps_the_keys_and_changes_the_ids():
    """Both halves matter. Same KEYS is what keeps reporting able to group one rung
    across every definition; different IDS is what stops two definitions sharing a
    row, which is how one definition's admin edit would silently rewrite another's
    graph."""
    with blank_session() as db:
        default = _seeded(db)
        register_workflow_submission_status_entity()
        definition = _definition(db)
        fork = fork_graph(db, WORKFLOW_SUBMISSION_ENTITY_TYPE, definition.id)

        assert {s.key for s in fork.statuses} == {s.key for s in default.statuses}
        assert not ({s.id for s in fork.statuses} & {s.id for s in default.statuses})
        assert _edge_keys(fork) == _edge_keys(default)
        assert all(s.scope_id == definition.id for s in fork.statuses)


def test_two_definitions_can_hold_different_states_on_one_engine():
    """The point of the whole slice: an exchange request grows an ``in_repair``
    rung without a service complaint ever seeing it, and without a second engine."""
    with blank_session() as db:
        _seeded(db)
        register_workflow_submission_status_entity()
        forked_definition = _definition(db)
        plain_definition = _definition(db)

        fork = fork_graph(db, WORKFLOW_SUBMISSION_ENTITY_TYPE, forked_definition.id)
        extra = Status(
            id=str(uuid.uuid4()),
            entity_type=WORKFLOW_SUBMISSION_ENTITY_TYPE,
            key="in_repair",
            label="In repair",
            color_hex="#F59E0B",
            sort_order=15,
            scope_id=forked_definition.id,
        )
        db.add(extra)
        db.flush()
        db.add(
            StatusTransition(
                id=str(uuid.uuid4()),
                entity_type=WORKFLOW_SUBMISSION_ENTITY_TYPE,
                scope_id=forked_definition.id,
                from_status_id=fork.by_key("submitted").id,
                to_status_id=extra.id,
                label="Send to repair",
            )
        )
        db.flush()

        forked_graph = resolve_graph(
            db, WORKFLOW_SUBMISSION_ENTITY_TYPE, forked_definition.id
        )
        plain_graph = resolve_graph(
            db, WORKFLOW_SUBMISSION_ENTITY_TYPE, plain_definition.id
        )
        assert "in_repair" in {s.key for s in forked_graph.statuses}
        assert "in_repair" not in {s.key for s in plain_graph.statuses}


# ============================================================== AC-F1-5
# A new submission's status comes from its definition's scope.


def test_a_new_submission_starts_on_the_default_graphs_initial_status():
    with blank_session() as db:
        default = _seeded(db)
        register_workflow_submission_status_entity()
        definition = _definition(db)

        row = _created(db, definition)
        assert row.status_id == default.by_key("draft").id
        assert row.status_key == "draft"


def test_a_forked_definition_starts_on_its_own_forks_initial_status():
    """The fork is the authority for this definition, so moving its starting rung
    must take effect without touching any other definition."""
    with blank_session() as db:
        default = _seeded(db)
        register_workflow_submission_status_entity()
        definition = _definition(db)
        fork = fork_graph(db, WORKFLOW_SUBMISSION_ENTITY_TYPE, definition.id)
        fork.by_key("draft").is_initial = False
        fork.by_key("submitted").is_initial = True
        db.flush()

        row = _created(db, definition)
        assert row.status_id == fork.by_key("submitted").id
        assert row.status_id != default.by_key("submitted").id
        assert row.status_key == "submitted"


def test_a_submission_cannot_be_created_when_no_graph_is_configured():
    """Fail closed. ``status_id`` is NOT NULL, so an unseeded environment has no
    legal value to write -- a 422 naming the missing graph beats an
    IntegrityError."""
    with blank_session() as db:
        register_workflow_submission_status_entity()
        definition = _definition(db)
        with pytest.raises(AppException) as err:
            _created(db, definition)
        assert err.value.status_code == 422
        assert err.value.detail["code"] == "status_graph_missing"


# ============================================================== AC-F1-6
# The engine, not the schema document, authorises a move.


def test_an_in_graph_transition_moves_the_submission():
    with blank_session() as db:
        graph = _seeded(db)
        register_workflow_submission_status_entity()
        definition = _definition(db)
        row = _created(db, definition)

        moved = WorkflowFormsService(db).apply_transition(
            str(row.id), graph.by_key("submitted").id, "ZZT moving on", "zzt-user"
        )
        db.refresh(moved)
        assert moved.status_id == graph.by_key("submitted").id
        assert moved.updated_by_user_id == "zzt-user"


def test_an_out_of_graph_transition_is_422_and_changes_nothing():
    """``draft -> approved`` skips the decision step. Before this the graph lived
    in a JSONB document and any client could send any move; the engine is the
    authority now."""
    with blank_session() as db:
        graph = _seeded(db)
        register_workflow_submission_status_entity()
        definition = _definition(db)
        row = _created(db, definition)

        with pytest.raises(AppException) as err:
            WorkflowFormsService(db).apply_transition(
                str(row.id), graph.by_key("approved").id, None, "zzt-user"
            )
        assert err.value.status_code == 422
        assert err.value.detail["code"] == "status_transition_not_allowed"
        db.refresh(row)
        assert row.status_id == graph.by_key("draft").id


def test_a_status_id_from_another_entitys_graph_is_422():
    """"Whatever the client sends" includes a real ``statuses.id`` that belongs to
    complaints. Resolving the graph by entity type AND scope is what rejects it."""
    from app.services.complaint_status_graph import seed_complaint_status_graph

    with blank_session() as db:
        _seeded(db)
        seed_complaint_status_graph(db)
        db.flush()
        register_workflow_submission_status_entity()
        definition = _definition(db)
        row = _created(db, definition)
        foreign = resolve_graph(db, "complaint", None).by_key("approved")

        with pytest.raises(AppException) as err:
            WorkflowFormsService(db).apply_transition(
                str(row.id), foreign.id, None, "zzt-user"
            )
        assert err.value.status_code == 422
        assert err.value.detail["code"] == "status_not_in_graph"


def test_a_status_id_from_the_default_graph_is_rejected_for_a_forked_definition():
    """The fork's rows are the only legal targets once a definition has forked.
    Accepting the default's id would put a submission on a status outside the graph
    its own definition resolves, and nothing could move it afterwards."""
    with blank_session() as db:
        default = _seeded(db)
        register_workflow_submission_status_entity()
        definition = _definition(db)
        fork_graph(db, WORKFLOW_SUBMISSION_ENTITY_TYPE, definition.id)
        row = _created(db, definition)

        with pytest.raises(AppException) as err:
            WorkflowFormsService(db).apply_transition(
                str(row.id), default.by_key("submitted").id, None, "zzt-user"
            )
        assert err.value.detail["code"] == "status_not_in_graph"


def test_a_transition_out_of_a_terminal_status_is_422():
    with blank_session() as db:
        graph = _seeded(db)
        register_workflow_submission_status_entity()
        definition = _definition(db)
        row = _created(db, definition)
        service = WorkflowFormsService(db)
        service.apply_transition(str(row.id), graph.by_key("submitted").id, None, "u")
        service.apply_transition(str(row.id), graph.by_key("approved").id, None, "u")

        with pytest.raises(AppException) as err:
            service.apply_transition(
                str(row.id), graph.by_key("draft").id, None, "zzt-user"
            )
        assert err.value.status_code == 422
        assert err.value.detail["code"] == "status_terminal"


def test_a_deactivated_status_cannot_be_moved_into():
    """The engine's way of saying "kept for existing records, closed to new ones".
    A form that retires a rung must stop accepting moves into it without deleting
    the rows that already hold it."""
    with blank_session() as db:
        graph = _seeded(db)
        register_workflow_submission_status_entity()
        definition = _definition(db)
        row = _created(db, definition)
        graph.by_key("submitted").is_active = False
        db.flush()

        with pytest.raises(AppException) as err:
            WorkflowFormsService(db).apply_transition(
                str(row.id), graph.by_key("submitted").id, None, "zzt-user"
            )
        assert err.value.detail["code"] == "status_inactive"


def test_the_forks_edges_are_the_authority_for_a_forked_definition():
    """A fork that removes an edge must actually forbid it. If the guard resolved
    the default graph it would keep authorising a move the definition's own graph
    no longer has."""
    with blank_session() as db:
        _seeded(db)
        register_workflow_submission_status_entity()
        definition = _definition(db)
        fork = fork_graph(db, WORKFLOW_SUBMISSION_ENTITY_TYPE, definition.id)
        submit_edge = next(
            t
            for t in fork.transitions
            if t.from_status_id == fork.by_key("draft").id
            and t.to_status_id == fork.by_key("submitted").id
        )
        db.delete(submit_edge)
        db.flush()

        row = _created(db, definition)
        with pytest.raises(AppException) as err:
            WorkflowFormsService(db).apply_transition(
                str(row.id), fork.by_key("submitted").id, None, "zzt-user"
            )
        assert err.value.detail["code"] == "status_transition_not_allowed"


def test_available_transitions_reads_the_definitions_own_graph():
    """What the FE offers as buttons. It has to come from the same resolution the
    guard uses, or a user is shown an action the server will refuse."""
    with blank_session() as db:
        graph = _seeded(db)
        register_workflow_submission_status_entity()
        definition = _definition(db)
        row = _created(db, definition)

        edges = available_transitions(
            db,
            WORKFLOW_SUBMISSION_ENTITY_TYPE,
            row.status_id,
            definition.id,
        )
        assert {t.to_status_id for t in edges} == {graph.by_key("submitted").id}


# ============================================================== AC-F1-8
# A rejected move is not history.


def test_an_accepted_transition_writes_one_log_row_naming_the_authorising_edge():
    with blank_session() as db:
        graph = _seeded(db)
        register_workflow_submission_status_entity()
        definition = _definition(db)
        row = _created(db, definition)

        WorkflowFormsService(db).apply_transition(
            str(row.id), graph.by_key("submitted").id, "ZZT remark", "zzt-user"
        )

        logs = _logs(db, row)
        assert len(logs) == 1
        entry = logs[0]
        assert entry.from_status_id == graph.by_key("draft").id
        assert entry.to_status_id == graph.by_key("submitted").id
        assert entry.remark == "ZZT remark"
        assert entry.user_id == "zzt-user"

        edge = next(
            t
            for t in graph.transitions
            if t.from_status_id == graph.by_key("draft").id
            and t.to_status_id == graph.by_key("submitted").id
        )
        assert entry.status_transition_id == edge.id, (
            "the log records WHICH edge authorised the move, not just the endpoints"
        )


def test_every_accepted_transition_appends_a_row():
    with blank_session() as db:
        graph = _seeded(db)
        register_workflow_submission_status_entity()
        definition = _definition(db)
        row = _created(db, definition)
        service = WorkflowFormsService(db)

        service.apply_transition(str(row.id), graph.by_key("submitted").id, None, "u")
        service.apply_transition(str(row.id), graph.by_key("rejected").id, None, "u")

        pairs = [(entry.from_status_id, entry.to_status_id) for entry in _logs(db, row)]
        assert pairs == [
            (graph.by_key("draft").id, graph.by_key("submitted").id),
            (graph.by_key("submitted").id, graph.by_key("rejected").id),
        ]


def test_a_rejected_transition_writes_nothing():
    """A rejected move is not history. Logging the attempt would put a state the
    submission never held into the audit trail."""
    with blank_session() as db:
        graph = _seeded(db)
        register_workflow_submission_status_entity()
        definition = _definition(db)
        row = _created(db, definition)

        with pytest.raises(AppException):
            WorkflowFormsService(db).apply_transition(
                str(row.id), graph.by_key("approved").id, "ZZT illegal", "zzt-user"
            )

        assert _logs(db, row) == []


def test_creating_a_submission_writes_no_transition_log():
    """Entering the graph is not a transition: nothing authorised it, so there is
    no edge to record. The log's ``from_status_id`` is nullable for a first entry
    that a later slice may choose to record, not because creation records one now."""
    with blank_session() as db:
        _seeded(db)
        register_workflow_submission_status_entity()
        definition = _definition(db)
        row = _created(db, definition)
        assert _logs(db, row) == []


# ============================================================== AC-F1-9
# Retiring the old shape: removed, not left beside it.


RETIRED_SERVICE_NAMES = (
    "validate_schema",
    "default_draft_schema",
    "validate_submission_payload",
    "_state_id_to_code",
    "_state_by_code",
    "_initial_state_code",
    "_header_fields_flat",
    "_collect_field_defs",
    "_validate_data_against_fields",
    "_find_transition",
    "_parse_iso_date",
)


def test_the_old_shape_surface_is_removed_from_the_service():
    """After F0 there were two validators describing one JSONB column and they
    disagreed. No release ships with both, so the older one goes rather than
    sitting beside the new one waiting to be called by mistake."""
    from app.services import workflow_forms_service

    present = [n for n in RETIRED_SERVICE_NAMES if hasattr(workflow_forms_service, n)]
    assert not present, f"retired old-shape surface still exported: {present}"


def test_nothing_under_app_still_references_the_retired_helpers():
    """``hasattr`` alone would pass while another module kept importing them --
    ``workflow_submission_dynamic_list_query`` imports ``_collect_field_defs``
    today, so removal is a two-file change."""
    offenders = []
    pattern = re.compile(r"\b(" + "|".join(RETIRED_SERVICE_NAMES) + r")\b")
    for path in _python_sources():
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if pattern.search(line):
                offenders.append(f"{path.relative_to(APP.parent)}:{number}")
    assert not offenders, f"retired old-shape helpers are still referenced: {offenders}"


def test_nothing_under_app_still_reads_current_state_code():
    """The column is dropped, so a surviving reader is a production error rather
    than a test failure. Known sites beyond the model: the submissions service, the
    output schema, and ``list_query_export_service``."""
    offenders = []
    for path in _python_sources():
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if "current_state_code" in line:
                offenders.append(f"{path.relative_to(APP.parent)}:{number}")
    assert not offenders, f"current_state_code is dropped but still read: {offenders}"


def test_the_workflow_files_no_longer_speak_state_codes():
    """The retired vocabulary in full. Scoped to the four workflow-forms files
    because ``transition_id`` is a legitimate path parameter on the engine's own
    admin routes."""
    pattern = re.compile(r"\b(from_state_code|to_state_code|transition_id)\b")
    offenders = []
    for relative in (
        "models/workflow_forms.py",
        "schemas/workflow_forms.py",
        "api/v1/workflow_forms/router.py",
        "services/workflow_forms_service.py",
    ):
        path = APP / relative
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if pattern.search(line):
                offenders.append(f"{relative}:{number}")
    assert not offenders, f"retired state-code vocabulary survives: {offenders}"


def test_the_workflow_service_no_longer_reads_states_out_of_the_schema_document():
    """The document model has no ``states`` array at all (``extra="forbid"`` would
    reject one), so a surviving ``schema.get("states")`` is dead code that returns
    an empty graph and looks like a rendering bug."""
    offenders = []
    for path in _python_sources():
        text = path.read_text(encoding="utf-8")
        if 'get("states")' in text or "get('states')" in text:
            offenders.append(str(path.relative_to(APP.parent)))
    assert not offenders, (
        f"these files still read the retired embedded state machine: {offenders}"
    )


def test_the_submission_router_still_imports_cleanly():
    """It imported ``validate_schema`` from the service and exposed it as a route.
    Removing the function without touching the router is an ImportError at app
    startup, which no unit test would otherwise catch."""
    import importlib

    module = importlib.import_module("app.api.v1.workflow_forms.router")
    assert module.router is not None
