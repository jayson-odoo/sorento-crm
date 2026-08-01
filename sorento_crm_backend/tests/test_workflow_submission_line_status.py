"""F1a gate - status on submission LINES, a per-line disposition, a DERIVED header.

F1 put the submission's status in the status engine. This file is its line-level
twin, and the reason it exists is one requirement: Customer Service **approves some
lines and rejects others** (`REQUIREMENTS-inbox-2026-08-01.md` R1/R3), each line
carries its own disposition, and the submission's status follows from its lines.

**The whole risk of the slice is that a derived value which is also writable is two
sources of truth.** Most of this file is not about adding a feature, it is about
stopping that. So the derived-header section comes FIRST: those are the tests that
catch the bugs. The shape and registration sections after it are cheap by comparison.

Five traps, each with its own test because each one passes a naive implementation:

1. **The empty set.** Zero lines satisfies "all lines terminal" vacuously, so a bare
   ``all(...)`` resolves an untouched submission. Same bug class as F0's empty
   ``rules[]`` matching everything.
2. **Derived but writable.** If ``apply_transition`` still moves a derived header,
   the column has two writers and they will disagree (ADR-0013 rule 11).
3. **Reopen.** Forward-only derivation is the likely half-implementation, and the
   precedent (`complaint_fulfilment_service`) implements both directions.
4. **Cancelled counted as done.** Counting an excluded line as complete resolves a
   submission whose real work never happened.
5. **Logging every recompute.** A derived value that appends history on each pass
   floods the trail, so idempotence is asserted on the log row COUNT.

Every test traces to an AC in
``documentation/plans/forms-platform/forms-platform-acceptance-criteria.md``,
Group F1a.
"""
from __future__ import annotations

import uuid
from collections import namedtuple
from pathlib import Path

import pytest
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.form_engine.schemas import FORM_SCHEMA_VERSION
from app.models.lookup import LookupBinding, LookupOption, LookupSet
from app.models.status import Status
from app.models.user import User
from app.models.workflow_forms import (
    WorkflowFormDefinition,
    WorkflowFormVersion,
    WorkflowSubmissionLine,
    WorkflowSubmissionTransitionLog,
)
from app.services import lookup_eligibility
from app.services.error_handler import AppException
from app.services.lookup_validator import _cache_clear as _lookup_cache_clear
from app.services.status_service import (
    assert_transition_allowed,
    fork_graph,
    initial_status,
    migrate_records,
    resolve_graph,
    validate_graph,
)
from app.services.workflow_forms_service import WorkflowFormsService
from app.services.workflow_submission_status_graph import (
    WORKFLOW_SUBMISSION_ENTITY_TYPE,
    register_workflow_submission_status_entity,
    seed_workflow_submission_status_graph,
)
from app.status_engine import registry as status_registry

from ._pg_fixture import TEST_PREFIX, blank_session, unique_code

APP = Path(__file__).resolve().parent.parent / "app"

# The three modules F1a adds.
from app.services.workflow_submission_derived_status import (
    DERIVED_TRANSITION_REMARK,
    definition_derives_status,
    derive_status_key,
    recompute_submission_status,
)
from app.services.workflow_submission_line_disposition import (
    LINE_DISPOSITION_COLUMN,
    LINE_DISPOSITION_OPTIONS,
    LINE_DISPOSITION_SET_KEY,
    LINE_DISPOSITION_TABLE,
    seed_workflow_submission_line_disposition_lookup,
)
from app.services.workflow_submission_line_status_graph import (
    WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE,
    WORKFLOW_SUBMISSION_LINE_STATUS_KEYS,
    WORKFLOW_SUBMISSION_LINE_TRANSITION_SEEDS,
    line_status_counts_by_key,
    register_workflow_submission_line_status_entity,
    seed_workflow_submission_line_status_graph,
)


# The vocabulary the DEFAULT line graph ships. Written out rather than derived from
# the seeds so widening it has to be done twice, on purpose (the same reasoning as
# F1's DEFAULT_GRAPH_KEYS). A line's lifecycle is a per-item decision, so the rungs
# are: undecided, the two decisions, and excluded.
LINE_GRAPH_KEYS = {"pending", "approved", "rejected", "cancelled"}

LINE_GRAPH_EDGES = {
    ("pending", "approved"),
    ("pending", "rejected"),
    ("pending", "cancelled"),
}

# The three modules F1a adds, for the "never branch on category" grep.
NEW_MODULES = (
    "services/workflow_submission_line_status_graph.py",
    "services/workflow_submission_line_disposition.py",
    "services/workflow_submission_derived_status.py",
)

# The repeater key every submission in this file files its lines under.
LINE_GROUP = "items"

# A publishable FormDocument carrying one header answer and one repeater, because a
# line row must name a repeater or table that exists in the document.
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

# The two header rungs a deriving definition in this file declares. Deliberately the
# DEFAULT graph's initial status as the open one, so no header fork is needed: the
# keys are configuration and derivation must not care which rungs they name. That the
# resolved one is TERMINAL is also deliberate -- reopening out of it is what proves
# derivation is not bound by the graph's edges.
OPEN_KEY = "draft"
RESOLVED_KEY = "approved"

Graphs = namedtuple("Graphs", "header line")


@pytest.fixture(autouse=True)
def _isolate_registry():
    """The status registry is process-global; snapshot and restore it."""
    saved = dict(status_registry._REGISTRY)
    yield
    status_registry._REGISTRY.clear()
    status_registry._REGISTRY.update(saved)


@pytest.fixture(autouse=True)
def _isolate_lookup_cache():
    """``validate_lookup_value`` memoises a binding's allowed values for 60s.

    A test that seeds the binding, reads it, then deactivates an option would
    otherwise keep validating against the warm copy and never see the change.
    """
    _lookup_cache_clear()
    yield
    _lookup_cache_clear()


# ------------------------------------------------------------------ helpers


def _seeded(db) -> Graphs:
    """Both default graphs seeded and both entities registered."""
    seed_workflow_submission_status_graph(db)
    seed_workflow_submission_line_status_graph(db)
    db.flush()
    register_workflow_submission_status_entity()
    register_workflow_submission_line_status_entity()
    return Graphs(
        resolve_graph(db, WORKFLOW_SUBMISSION_ENTITY_TYPE, None),
        resolve_graph(db, WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE, None),
    )


def _attribution_users(db):
    """Real ``users`` rows for the ids this file attributes writes to.

    F1 gave the attribution columns real foreign keys to ``users.id`` and Postgres
    enforces them at INSERT, so an invented id aborts the transaction.
    """
    for user_id in ("zzt-user", "zzt-other"):
        if db.query(User).filter(User.id == user_id).first() is None:
            db.add(
                User(
                    id=user_id,
                    email=f"{user_id}@{TEST_PREFIX.lower()}.invalid",
                    name=f"{TEST_PREFIX} tester",
                )
            )
    db.flush()


def _definition(
    db,
    *,
    derives: bool = False,
    open_key: str = OPEN_KEY,
    resolved_key: str = RESOLVED_KEY,
) -> WorkflowFormDefinition:
    """A definition with a published version, built by hand.

    ``derives=False`` passes none of the derivation columns, so it exercises the
    server defaults -- which is exactly AC-F1a-10's "keeps today's behaviour".
    """
    _attribution_users(db)
    declared = (
        {
            "derives_status_from_lines": True,
            "derived_open_status_key": open_key,
            "derived_resolved_status_key": resolved_key,
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


def _created(db, definition, *, rows: int = 1, user_id: str = "zzt-user"):
    """A submission through the service, which is what stamps initial statuses."""
    lines = [
        {"line_group_id": LINE_GROUP, "row_data": {"model": f"{TEST_PREFIX}-{i}"}}
        for i in range(rows)
    ]
    return WorkflowFormsService(db).create_submission(
        definition.id, {"title": f"{TEST_PREFIX} answer"}, lines, user_id
    )


def _lines(db, submission):
    return (
        db.query(WorkflowSubmissionLine)
        .filter(WorkflowSubmissionLine.submission_id == submission.id)
        .order_by(WorkflowSubmissionLine.sort_order)
        .all()
    )


def _decide(db, line, status: Status, *, user_id: str = "zzt-user"):
    return WorkflowFormsService(db).apply_line_transition(
        str(line.id), status.id, user_id
    )


def _stamp(db, line, status):
    """Put a line on a status WITHOUT the service.

    Arrangement only, never the writer under test: some states are unreachable
    through the engine on purpose (nothing may leave a terminal status), and the
    question those tests ask is whether derivation NOTICES a changed line, not how
    the line changed. The DO precedent has the same shape -- a delivered DO
    un-delivers by some other path and fulfilment merely recomputes.
    """
    line.status_id = None if status is None else status.id
    db.flush()


def _add_line(db, submission, status, *, sort_order: int = 99):
    row = WorkflowSubmissionLine(
        id=str(uuid.uuid4()),
        submission_id=submission.id,
        line_group_id=LINE_GROUP,
        sort_order=sort_order,
        row_data={"model": f"{TEST_PREFIX}-added"},
        status_id=None if status is None else status.id,
    )
    db.add(row)
    db.flush()
    return row


def _header_key(db, submission):
    db.refresh(submission)
    return submission.status_key


def _logs(db, submission):
    return (
        db.query(WorkflowSubmissionTransitionLog)
        .filter(WorkflowSubmissionTransitionLog.submission_id == submission.id)
        .order_by(WorkflowSubmissionTransitionLog.created_at)
        .all()
    )


def _edge_keys(graph) -> set:
    by_id = {s.id: s.key for s in graph.statuses}
    return {(by_id[t.from_status_id], by_id[t.to_status_id]) for t in graph.transitions}


def _seed_dispositions(db):
    seed_workflow_submission_line_disposition_lookup(db)
    db.flush()
    _lookup_cache_clear()


def _disposition_values():
    return [value for value, *_rest in LINE_DISPOSITION_OPTIONS]


def _option(db, value: str) -> LookupOption:
    return (
        db.query(LookupOption)
        .join(LookupSet, LookupSet.id == LookupOption.set_id)
        .filter(
            LookupSet.set_key == LINE_DISPOSITION_SET_KEY,
            LookupOption.value == value,
        )
        .one()
    )


# ==================================================== AC-F1a-9 to AC-F1a-16
# The derived header. Every trap in the slice lives in this section.


def test_zero_lines_is_not_derivable_and_the_header_stays_put():
    """The empty-set trap. ``all(...)`` over no lines is True, so a naive
    implementation resolves a submission nobody has worked on -- the same bug class
    as F0's empty ``rules[]`` matching everything. Zero lines means NOT derivable,
    which is a different answer from "derivable and open"."""
    with blank_session() as db:
        _seeded(db)
        definition = _definition(db, derives=True)
        submission = _created(db, definition, rows=0)

        assert _lines(db, submission) == []
        assert derive_status_key(db, submission) is None
        assert recompute_submission_status(db, submission) is False
        assert _header_key(db, submission) == OPEN_KEY
        assert _logs(db, submission) == []


def test_a_submission_whose_every_line_is_cancelled_is_not_derivable():
    """The empty set again, reached by exclusion rather than by having no rows. If
    cancelled lines are filtered out and the remainder fed to ``all(...)``, a
    submission whose whole content was cancelled resolves as though the work was
    done."""
    with blank_session() as db:
        graphs = _seeded(db)
        definition = _definition(db, derives=True)
        submission = _created(db, definition, rows=2)
        for line in _lines(db, submission):
            _decide(db, line, graphs.line.by_key("cancelled"))

        assert derive_status_key(db, submission) is None
        assert recompute_submission_status(db, submission) is False
        assert _header_key(db, submission) == OPEN_KEY
        assert _logs(db, submission) == []


def test_a_deriving_definitions_header_cannot_be_moved_out_of_the_derived_pair_by_hand():
    """The derived-but-writable trap, and the reason most of this section exists.
    ADR-0013 rule 11 allows exactly one writer of a status column. A header that is
    computed from its lines AND settable through ``apply_transition`` has two, and
    the moment they disagree neither is trustworthy. A distinct code is required so
    the FE can say why rather than showing a generic 422.

    The submission sits on the OPEN rung here, so every move it has available leaves
    the derived pair and every one of them is refused (AC-F1a-22)."""
    with blank_session() as db:
        graphs = _seeded(db)
        definition = _definition(db, derives=True)
        submission = _created(db, definition, rows=1)

        with pytest.raises(AppException) as err:
            WorkflowFormsService(db).apply_transition(
                str(submission.id),
                graphs.header.by_key("submitted").id,
                "ZZT by hand",
                "zzt-user",
            )
        assert err.value.status_code == 422
        assert err.value.detail["code"] == "status_derived_not_writable"
        assert _header_key(db, submission) == OPEN_KEY
        assert _logs(db, submission) == []


def test_a_deriving_definition_offers_no_manual_transitions_out_of_the_derived_pair():
    """The buttons must agree with the guard. Offering a move the server refuses is
    how a user learns the product is broken, and it is the same reasoning that makes
    ``allowed_transitions_for_user`` resolve the definition's own graph.

    On the open rung that leaves nothing to offer, because every edge out of it leaves
    the pair."""
    with blank_session() as db:
        _seeded(db)
        definition = _definition(db, derives=True)
        submission = _created(db, definition, rows=1)

        offered = WorkflowFormsService(db).allowed_transitions_for_user(
            str(submission.id), "zzt-user"
        )
        assert offered == []


def test_a_move_that_touches_neither_derived_rung_is_still_allowed_by_hand():
    """AC-F1a-22, which supersedes AC-F1a-9's blanket refusal. Derivation only ever
    moves the header between the two declared rungs, so refusing EVERY move would mean
    a deriving submission could never reach a terminal state at all: it could not be
    closed by hand even once every line was decided. The one-writer rule belongs to the
    values that are actually derived, and the rest of the lifecycle stays human-driven.

    The header is parked outside the pair by hand, which is the state a manual move into
    a non-derived rung leaves it in."""
    with blank_session() as db:
        graphs = _seeded(db)
        definition = _definition(db, derives=True)
        submission = _created(db, definition, rows=1)
        # Arrangement only: derivation owns the pair, so it never puts a submission here.
        submission.status_id = graphs.header.by_key("submitted").id
        db.flush()

        moved = WorkflowFormsService(db).apply_transition(
            str(submission.id),
            graphs.header.by_key("rejected").id,
            "ZZT closed by hand",
            "zzt-user",
        )

        db.refresh(moved)
        assert moved.status_key == "rejected"
        logs = _logs(db, submission)
        assert len(logs) == 1
        assert logs[0].user_id == "zzt-user", "a hand-made move has a human mover"
        assert logs[0].status_transition_id is not None, "and an edge that authorised it"

        offered = WorkflowFormsService(db).allowed_transitions_for_user(
            str(submission.id), "zzt-user"
        )
        assert offered == [], "'rejected' is final; nothing is offered out of it"


def test_all_non_cancelled_lines_terminal_moves_the_header_to_the_resolved_status():
    """The forward half of AC-F1a-12, and the only half a partial implementation
    tends to ship."""
    with blank_session() as db:
        graphs = _seeded(db)
        definition = _definition(db, derives=True)
        submission = _created(db, definition, rows=2)

        rows = _lines(db, submission)
        _decide(db, rows[0], graphs.line.by_key("approved"))
        assert _header_key(db, submission) == OPEN_KEY, (
            "one decided line out of two is not a decided submission"
        )

        _decide(db, rows[1], graphs.line.by_key("rejected"))
        assert derive_status_key(db, submission) == RESOLVED_KEY
        assert _header_key(db, submission) == RESOLVED_KEY


def test_a_cancelled_line_is_excluded_rather_than_counted_as_done():
    """Straight from the precedent: ``complaint_fulfilment_service`` drops cancelled
    DOs from the population instead of treating them as delivered. Counting them as
    done resolves a submission whose remaining work never happened, so both halves
    are asserted -- excluded beside a decided line still resolves, excluded beside an
    undecided line does not."""
    with blank_session() as db:
        graphs = _seeded(db)
        definition = _definition(db, derives=True)

        undecided = _created(db, definition, rows=2)
        rows = _lines(db, undecided)
        _decide(db, rows[0], graphs.line.by_key("cancelled"))
        assert derive_status_key(db, undecided) == OPEN_KEY
        assert _header_key(db, undecided) == OPEN_KEY

        decided = _created(db, definition, rows=2)
        rows = _lines(db, decided)
        _decide(db, rows[0], graphs.line.by_key("cancelled"))
        _decide(db, rows[1], graphs.line.by_key("approved"))
        assert derive_status_key(db, decided) == RESOLVED_KEY
        assert _header_key(db, decided) == RESOLVED_KEY


def test_a_line_leaving_terminal_reopens_the_header():
    """The reopen half of AC-F1a-12, which is not optional. A ``fulfilled`` complaint
    returns to ``processed_by_cs`` when one of its DOs stops being delivered; the same
    shape applies here. Forward-only derivation leaves a resolved submission that can
    never be corrected."""
    with blank_session() as db:
        graphs = _seeded(db)
        definition = _definition(db, derives=True)
        submission = _created(db, definition, rows=1)
        line = _lines(db, submission)[0]

        _decide(db, line, graphs.line.by_key("approved"))
        assert _header_key(db, submission) == RESOLVED_KEY

        _stamp(db, line, graphs.line.by_key("pending"))
        assert derive_status_key(db, submission) == OPEN_KEY
        assert recompute_submission_status(db, submission) is True
        assert _header_key(db, submission) == OPEN_KEY


def test_a_new_undecided_line_reopens_a_resolved_submission():
    """The other reopen trigger, and the one the SOP actually describes: "items can
    be added onto an existing RMA". The precedent's wording is "reopens if a
    non-delivered DO links" -- a submission is only resolved while its CURRENT set of
    lines is decided, never because it once was."""
    with blank_session() as db:
        graphs = _seeded(db)
        definition = _definition(db, derives=True)
        submission = _created(db, definition, rows=1)
        _decide(db, _lines(db, submission)[0], graphs.line.by_key("approved"))
        assert _header_key(db, submission) == RESOLVED_KEY

        _add_line(db, submission, graphs.line.by_key("pending"))
        assert recompute_submission_status(db, submission) is True
        assert _header_key(db, submission) == OPEN_KEY


def test_derivation_reopens_out_of_a_terminal_status_the_engine_would_refuse():
    """Derivation is not the transition guard, and this is where that stops being a
    detail. The declared resolved rung is terminal, so no edge can leave it and
    ``assert_transition_allowed`` says so. An implementation that recomputes by
    calling the guard therefore CANNOT reopen -- it would raise ``status_terminal``
    and leave the header wrong for good. The single writer of a derived header is the
    derivation, and it answers to the line statuses rather than to the edges."""
    with blank_session() as db:
        graphs = _seeded(db)
        definition = _definition(db, derives=True)
        submission = _created(db, definition, rows=1)
        line = _lines(db, submission)[0]
        _decide(db, line, graphs.line.by_key("approved"))

        resolved = graphs.header.by_key(RESOLVED_KEY)
        assert resolved.is_terminal is True
        with pytest.raises(AppException) as err:
            assert_transition_allowed(
                db,
                WORKFLOW_SUBMISSION_ENTITY_TYPE,
                resolved.id,
                graphs.header.by_key(OPEN_KEY).id,
                definition.id,
            )
        assert err.value.detail["code"] == "status_terminal"

        _stamp(db, line, graphs.line.by_key("pending"))
        assert recompute_submission_status(db, submission) is True
        assert _header_key(db, submission) == OPEN_KEY


def test_a_second_recompute_writes_nothing_and_appends_no_log_row():
    """Idempotence, asserted on the log row COUNT rather than on the status. A
    recompute that rewrites the same value and appends history every time floods the
    trail with rows a reviewer has to read past, and the status assertion alone would
    pass while it happened."""
    with blank_session() as db:
        graphs = _seeded(db)
        definition = _definition(db, derives=True)
        submission = _created(db, definition, rows=1)
        _decide(db, _lines(db, submission)[0], graphs.line.by_key("approved"))

        assert _header_key(db, submission) == RESOLVED_KEY
        assert len(_logs(db, submission)) == 1

        assert recompute_submission_status(db, submission) is False
        assert recompute_submission_status(db, submission) is False
        assert _header_key(db, submission) == RESOLVED_KEY
        assert len(_logs(db, submission)) == 1


def test_recompute_on_a_submission_that_should_not_move_writes_nothing():
    """The no-change path, which is the one that runs on nearly every call. An
    undecided submission already sits on the open rung, so the recompute has nothing
    to do and must say so rather than rewriting the same id."""
    with blank_session() as db:
        _seeded(db)
        definition = _definition(db, derives=True)
        submission = _created(db, definition, rows=2)

        assert derive_status_key(db, submission) == OPEN_KEY
        assert recompute_submission_status(db, submission) is False
        assert _header_key(db, submission) == OPEN_KEY
        assert _logs(db, submission) == []


def test_the_derived_move_is_not_attributed_to_whoever_touched_the_line():
    """AC-F1a-16. A derived move has no human mover, so naming one is a lie in the
    audit trail -- and the lie is plausible, because a person really did move a line
    a moment earlier. ``user_id`` stays NULL, and no edge is recorded either, because
    no edge authorised it (see the terminal-reopen test). The remark is what tells a
    reviewer which kind of row they are reading."""
    with blank_session() as db:
        graphs = _seeded(db)
        definition = _definition(db, derives=True)
        submission = _created(db, definition, rows=1)

        _decide(
            db,
            _lines(db, submission)[0],
            graphs.line.by_key("approved"),
            user_id="zzt-other",
        )

        logs = _logs(db, submission)
        assert len(logs) == 1
        entry = logs[0]
        assert entry.user_id is None, "a derived move has no human mover"
        assert entry.status_transition_id is None
        assert entry.remark == DERIVED_TRANSITION_REMARK
        assert entry.from_status_id == graphs.header.by_key(OPEN_KEY).id
        assert entry.to_status_id == graphs.header.by_key(RESOLVED_KEY).id


def test_derivation_reads_trait_flags_so_a_forked_line_graph_may_rename_its_keys():
    """AC-F1a-13. An implementation branching on ``"approved"`` passes every other
    test in this file and fails here. A definition owns its line graph and may rename
    or re-cut the rungs; ``is_terminal`` and ``is_archived`` are the engine's machine
    semantics and the only things derivation may read."""
    with blank_session() as db:
        _seeded(db)
        definition = _definition(db, derives=True)
        fork = fork_graph(db, WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE, definition.id)
        fork.by_key("pending").key = "awaiting_cs"
        fork.by_key("approved").key = "exchange_authorised"
        fork.by_key("cancelled").key = "withdrawn"
        db.flush()

        submission = _created(db, definition, rows=2)
        rows = _lines(db, submission)
        assert rows[0].status_key == "awaiting_cs", "lines start on the FORK's initial rung"

        _decide(db, rows[0], fork.by_key("exchange_authorised"))
        _decide(db, rows[1], fork.by_key("withdrawn"))

        assert derive_status_key(db, submission) == RESOLVED_KEY
        assert _header_key(db, submission) == RESOLVED_KEY


def test_partial_approval_is_a_first_class_state():
    """AC-F1a-14, and the requirement that forced the whole slice: "whole-request
    approval breaks as soon as one of three items is written off and another
    replaced". Disagreeing lines are normal, not an error: the header reads "decided"
    and each line keeps its own outcome, so nothing forces the lines to agree and
    nothing collapses them into a single verdict."""
    with blank_session() as db:
        graphs = _seeded(db)
        definition = _definition(db, derives=True)
        submission = _created(db, definition, rows=3)

        rows = _lines(db, submission)
        _decide(db, rows[0], graphs.line.by_key("approved"))
        _decide(db, rows[1], graphs.line.by_key("rejected"))
        _decide(db, rows[2], graphs.line.by_key("approved"))

        assert _header_key(db, submission) == RESOLVED_KEY
        assert [row.status_key for row in _lines(db, submission)] == [
            "approved",
            "rejected",
            "approved",
        ]


def test_a_definition_that_does_not_declare_derivation_keeps_todays_behaviour():
    """AC-F1a-10. Every form in production today is this definition, so "opt-in"
    has to mean bit-for-bit unchanged: the header moves by transition, the lines
    carry no status, and a recompute called on it does nothing at all."""
    with blank_session() as db:
        graphs = _seeded(db)
        definition = _definition(db)
        submission = _created(db, definition, rows=2)

        assert definition_derives_status(definition) is False
        assert [row.status_id for row in _lines(db, submission)] == [None, None]
        assert derive_status_key(db, submission) is None
        assert recompute_submission_status(db, submission) is False

        moved = WorkflowFormsService(db).apply_transition(
            str(submission.id), graphs.header.by_key("submitted").id, None, "zzt-user"
        )
        db.refresh(moved)
        assert moved.status_key == "submitted"
        logs = _logs(db, submission)
        assert len(logs) == 1 and logs[0].user_id == "zzt-user"


def test_a_line_with_no_status_keeps_the_header_open():
    """A statusless line is undecided, never absent. Filtering ``status_id IS NOT
    NULL`` out of the population is the empty-set trap wearing a different hat: it
    resolves a submission on the strength of the lines that happen to have been
    stamped, and the unstamped ones vanish."""
    with blank_session() as db:
        graphs = _seeded(db)
        definition = _definition(db, derives=True)
        submission = _created(db, definition, rows=1)
        _decide(db, _lines(db, submission)[0], graphs.line.by_key("approved"))
        assert _header_key(db, submission) == RESOLVED_KEY

        _add_line(db, submission, None)
        assert derive_status_key(db, submission) == OPEN_KEY
        assert recompute_submission_status(db, submission) is True
        assert _header_key(db, submission) == OPEN_KEY


def test_a_stranded_line_is_not_counted_as_done():
    """AC-F1a-5's consequence inside derivation. A line's ``Status`` row stays
    readable through the FK after its definition forks, so ``line.status.is_terminal``
    answers happily with a flag from a graph this line no longer belongs to. Lines
    multiply the exposure -- one fork strands every row of every submission at once --
    so derivation must resolve the graph and refuse what is not in it."""
    with blank_session() as db:
        graphs = _seeded(db)
        definition = _definition(db, derives=True)
        submission = _created(db, definition, rows=1)
        _decide(db, _lines(db, submission)[0], graphs.line.by_key("approved"))

        fork_graph(db, WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE, definition.id)
        with pytest.raises(AppException) as err:
            recompute_submission_status(db, submission)
        assert err.value.status_code == 422
        assert err.value.detail["code"] == "status_not_in_graph"


def test_a_header_parked_outside_the_declared_pair_is_never_hijacked():
    """The precedent is explicit that ``closed`` / ``rejected`` are sticky and never
    touched. Derivation toggles between the two rungs the definition declared and
    owns nothing else, or enabling it on an existing form would drag every submission
    onto a rung the definition never asked for."""
    with blank_session() as db:
        graphs = _seeded(db)
        definition = _definition(db, derives=True)
        submission = _created(db, definition, rows=1)
        # Arrangement only: the header's writer is the derivation, and it refuses to
        # put a submission here, which is precisely why this state has to be tested.
        submission.status_id = graphs.header.by_key("rejected").id
        db.flush()

        _decide(db, _lines(db, submission)[0], graphs.line.by_key("approved"))
        assert _header_key(db, submission) == "rejected"
        assert _logs(db, submission) == []


def test_a_definition_declaring_a_key_its_graph_does_not_have_fails_loudly():
    """A silent-empty result is worse than a crash (ADR-0013 rule 12). A declared rung
    that no longer exists -- an admin forked the header graph and deleted it, or the
    key was mistyped -- must not degrade into "not derivable", which reads as a working
    form that simply never closes. The break is applied after creation on purpose, so
    the test says nothing about whether creation itself recomputes."""
    with blank_session() as db:
        _seeded(db)
        definition = _definition(db, derives=True)
        submission = _created(db, definition, rows=1)

        definition.derived_resolved_status_key = "zzt_no_such_rung"
        db.flush()

        with pytest.raises(AppException) as err:
            recompute_submission_status(db, submission)
        assert err.value.status_code == 422
        assert err.value.detail["code"] == "status_derivation_misconfigured"


def test_the_definition_declares_derivation_in_columns_not_in_its_document():
    """How a definition opts in, pinned. Three columns rather than a key inside the
    versioned document: a published version is an immutable snapshot, so config living
    there could not be changed without republishing, and the guard that refuses a
    manual header move would have to parse a JSONB document on every transition.

    The two rungs are named by KEY, never by ``statuses.id``. A definition forks its
    header graph and the fork re-keys every id for the same rungs, so an id here would
    point at the default graph's row and resolve to nothing the moment it forked."""
    columns = WorkflowFormDefinition.__table__.c
    flag = columns["derives_status_from_lines"]
    assert flag.nullable is False
    assert flag.server_default is not None, "existing definitions must default to off"

    for name in ("derived_open_status_key", "derived_resolved_status_key"):
        column = columns[name]
        assert isinstance(column.type, String)
        assert not isinstance(column.type, PGUUID), "keys, never ids (AC-F1a-17)"
        assert column.nullable is True
        assert not column.foreign_keys


def test_a_valid_derivation_pair_saves():
    """The happy path for the save-time checks below, so they cannot pass by refusing
    everything. ``draft`` is the graph's starting state and ``submitted`` is not final,
    which is the only shape the two rules below both accept."""
    with blank_session() as db:
        _seeded(db)
        definition = _definition(db)
        assert definition_derives_status(definition) is False

        saved = WorkflowFormsService(db).update_definition(
            str(definition.id),
            name=None,
            description=None,
            is_active=None,
            draft_schema=None,
            derives_status_from_lines=True,
            derived_open_status_key="draft",
            derived_resolved_status_key="submitted",
        )

        db.refresh(saved)
        assert definition_derives_status(saved) is True
        assert saved.derived_open_status_key == "draft"
        assert saved.derived_resolved_status_key == "submitted"


def test_an_open_key_that_is_not_the_graphs_starting_state_is_refused_at_save():
    """AC-F1a-23. Otherwise the failure is silent and permanent: a submission is created
    on the graph's starting state, so if the open key names anything else the submission
    sits OUTSIDE the declared pair from birth. Derivation then correctly refuses to
    hijack it and the manual guard refuses every move into the pair, so the submission is
    stuck with no way back and the form looks like one that simply never closes."""
    with blank_session() as db:
        graphs = _seeded(db)
        definition = _definition(
            db, derives=True, open_key="draft", resolved_key="submitted"
        )
        assert graphs.header.by_key("submitted").is_initial is False

        with pytest.raises(AppException) as err:
            WorkflowFormsService(db).update_definition(
                str(definition.id),
                name=None,
                description=None,
                is_active=None,
                draft_schema=None,
                derived_open_status_key="submitted",
            )
        assert err.value.status_code == 422
        assert err.value.detail["code"] == "status_derivation_misconfigured"
        db.refresh(definition)
        assert definition.derived_open_status_key == "draft", (
            "a refused save must leave nothing behind"
        )


def test_a_terminal_resolved_key_is_refused_at_save():
    """AC-F1a-24. ``update_submission`` refuses to edit a submission whose header is
    final, and adding or replacing lines is the main reachable way to reopen one, so a
    terminal resolved rung freezes the submission the moment its lines are all decided.
    Closing for good is a separate manual move, which AC-F1a-22 permits."""
    with blank_session() as db:
        graphs = _seeded(db)
        definition = _definition(
            db, derives=True, open_key="draft", resolved_key="submitted"
        )
        assert graphs.header.by_key("approved").is_terminal is True

        with pytest.raises(AppException) as err:
            WorkflowFormsService(db).update_definition(
                str(definition.id),
                name=None,
                description=None,
                is_active=None,
                draft_schema=None,
                derived_resolved_status_key="approved",
            )
        assert err.value.status_code == 422
        assert err.value.detail["code"] == "status_derivation_misconfigured"
        db.refresh(definition)
        assert definition.derived_resolved_status_key == "submitted"


def test_a_declared_key_the_graph_does_not_have_is_refused_at_save_too():
    """The same misconfiguration ``recompute_submission_status`` raises on, caught one
    step earlier where an admin can still fix it. A definition saved with a rung that
    does not exist would 422 every submission of that form instead."""
    with blank_session() as db:
        _seeded(db)
        definition = _definition(
            db, derives=True, open_key="draft", resolved_key="submitted"
        )

        with pytest.raises(AppException) as err:
            WorkflowFormsService(db).update_definition(
                str(definition.id),
                name=None,
                description=None,
                is_active=None,
                draft_schema=None,
                derived_resolved_status_key="zzt_no_such_rung",
            )
        assert err.value.detail["code"] == "status_derivation_misconfigured"


def test_a_definition_that_does_not_derive_is_not_held_to_the_pair_rules():
    """The opt-in has to stay free. Every definition in production today declares no
    derivation, and validating rungs it never named would make an unrelated rename or
    draft save fail."""
    with blank_session() as db:
        _seeded(db)
        definition = _definition(db)

        saved = WorkflowFormsService(db).update_definition(
            str(definition.id),
            name=f"{TEST_PREFIX} renamed",
            description=None,
            is_active=None,
            draft_schema=None,
        )
        assert saved.name == f"{TEST_PREFIX} renamed"
        assert definition_derives_status(saved) is False


# ============================================================== AC-F1a-1
# The column on the line.


def test_the_line_carries_a_nullable_status_id_fk_to_statuses():
    """Nullable is the opt-in: most forms have lines that are just data, and forcing
    a status on them would mean seeding a graph for every form with a repeater. It is
    still a real FK, so a status cannot be deleted out from under a line, and it is a
    pg UUID rather than a ``String`` -- that drift is what broke ``user_sessions.id``
    on production."""
    column = WorkflowSubmissionLine.__table__.c["status_id"]
    assert isinstance(column.type, PGUUID)
    assert column.type.as_uuid is False
    assert column.nullable is True
    assert {fk.target_fullname for fk in column.foreign_keys} == {"statuses.id"}


def test_a_line_reads_back_its_status_key_and_label():
    """The FE may not render UUIDs, and reporting groups by key, so a line has to
    reach a serializer holding the key and the label the way the header does."""
    with blank_session() as db:
        graphs = _seeded(db)
        definition = _definition(db, derives=True)
        submission = _created(db, definition, rows=1)
        line = _lines(db, submission)[0]
        db.refresh(line)

        assert line.status is not None and line.status.key == "pending"
        assert line.status_key == "pending"
        assert line.status_label == graphs.line.by_key("pending").label


def test_a_deriving_definition_stamps_its_lines_with_the_line_graphs_initial_status():
    """The other half of the opt-in. A deriving definition whose lines arrive with no
    status could never resolve, and the value has to come from the LINE graph resolved
    for that definition rather than from the header's."""
    with blank_session() as db:
        graphs = _seeded(db)
        definition = _definition(db, derives=True)
        submission = _created(db, definition, rows=2)

        expected = initial_status(
            db, WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE, definition.id
        )
        assert expected.key == "pending"
        assert [row.status_id for row in _lines(db, submission)] == [
            expected.id,
            expected.id,
        ]
        assert expected.id not in {s.id for s in graphs.header.statuses}


def test_replacing_the_lines_stamps_the_new_rows_too():
    """``update_submission`` deletes every line and re-inserts, so the new rows go
    through a second code path. Missing it leaves a deriving submission holding
    statusless lines that no line transition can move."""
    with blank_session() as db:
        _seeded(db)
        definition = _definition(db, derives=True)
        submission = _created(db, definition, rows=1)

        WorkflowFormsService(db).update_submission(
            str(submission.id),
            {"title": f"{TEST_PREFIX} edited"},
            [{"line_group_id": LINE_GROUP, "row_data": {"model": "ZZT-new"}}],
            "zzt-user",
        )

        rows = _lines(db, submission)
        assert len(rows) == 1
        assert rows[0].status_key == "pending"


def test_replacing_the_lines_is_refused_once_a_line_has_been_decided():
    """AC-F1a-21, and the one defect in this slice that loses data rather than raising.
    ``update_submission`` replaces lines by deleting every row and re-inserting with
    fresh UUIDs, so an answer edit that happens to include ``lines`` would wipe every
    line status and disposition with no error at all.

    Refusing rather than merging is deliberate: a merge needs a stable per-row identity
    and the document supplies none (``row_data`` is free-form, the id is
    server-generated), so any matching rule would be a heuristic that mis-attributes a
    decision to the wrong row. Losing a decision quietly is worse than refusing an edit
    loudly."""
    with blank_session() as db:
        graphs = _seeded(db)
        definition = _definition(
            db, derives=True, open_key=OPEN_KEY, resolved_key="submitted"
        )
        submission = _created(db, definition, rows=2)
        rows = _lines(db, submission)
        _decide(db, rows[0], graphs.line.by_key("approved"))
        service = WorkflowFormsService(db)

        with pytest.raises(AppException) as err:
            service.update_submission(
                str(submission.id),
                {"title": f"{TEST_PREFIX} edited"},
                [{"line_group_id": LINE_GROUP, "row_data": {"model": "ZZT-new"}}],
                "zzt-user",
            )
        assert err.value.status_code == 422
        assert err.value.detail["code"] == "line_decided_not_replaceable"

        kept = _lines(db, submission)
        assert [row.status_key for row in kept] == ["approved", "pending"], (
            "the decision must survive the refused edit"
        )

        # A header-only edit is untouched by the rule: the lines are not being replaced,
        # so there is nothing to lose.
        service.update_submission(
            str(submission.id), {"title": f"{TEST_PREFIX} header only"}, None, "zzt-user"
        )
        db.refresh(submission)
        assert submission.header_data["title"] == f"{TEST_PREFIX} header only"
        assert [row.status_key for row in _lines(db, submission)] == [
            "approved",
            "pending",
        ]


def test_a_disposition_alone_also_blocks_replacing_the_lines():
    """The second signal in "decided", and it is not redundant: a disposition can be
    recorded before any line moves off the initial rung, and it is just as much a piece
    of somebody's work as a status. Checking only the status would silently drop it."""
    with blank_session() as db:
        _seeded(db)
        _seed_dispositions(db)
        definition = _definition(
            db, derives=True, open_key=OPEN_KEY, resolved_key="submitted"
        )
        submission = _created(db, definition, rows=1)
        line = _lines(db, submission)[0]
        service = WorkflowFormsService(db)
        service.set_line_disposition(str(line.id), _disposition_values()[0], "zzt-user")
        db.refresh(line)
        assert line.status_key == "pending", "still on the initial rung"

        with pytest.raises(AppException) as err:
            service.update_submission(
                str(submission.id),
                None,
                [{"line_group_id": LINE_GROUP, "row_data": {"model": "ZZT-new"}}],
                "zzt-user",
            )
        assert err.value.detail["code"] == "line_decided_not_replaceable"
        assert _lines(db, submission)[0].disposition == _disposition_values()[0]


def test_replacing_undecided_lines_is_still_allowed():
    """The rule has to bite only on decisions. A submission whose lines are all still
    undecided is an ordinary draft, and blocking its edits would make the slice a
    regression for every form that has a repeater."""
    with blank_session() as db:
        _seeded(db)
        definition = _definition(
            db, derives=True, open_key=OPEN_KEY, resolved_key="submitted"
        )
        submission = _created(db, definition, rows=2)

        WorkflowFormsService(db).update_submission(
            str(submission.id),
            {"title": f"{TEST_PREFIX} edited"},
            [{"line_group_id": LINE_GROUP, "row_data": {"model": "ZZT-new"}}],
            "zzt-user",
        )

        rows = _lines(db, submission)
        assert [row.row_data["model"] for row in rows] == ["ZZT-new"]
        assert [row.status_key for row in rows] == ["pending"]


# ============================================================== AC-F1a-2
# Registration: FK-based, with its own graph rather than the submission's.


def test_the_line_entity_registers_fk_based_on_its_own_status_id():
    """A new table has no legacy excuse, so ADR-0013 rule 1 applies: an FK column and
    an FK registration. Going FK-native is also what makes ``count_records`` exact
    under a fork, since an id belongs to exactly one graph where a key is shared
    across all of them."""
    with blank_session() as db:
        _seeded(db)
        entity = status_registry.get_status_entity(WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE)
        assert entity is not None
        assert entity.status_attr == "status_id"
        assert entity.model is WorkflowSubmissionLine
        assert entity.scope_resolver is not None
        assert entity.scope_label, "the admin copy needs a noun for the scope owner"
        assert WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE == "workflow_submission_line"


def test_the_line_graph_is_not_the_submissions_graph():
    """A line's lifecycle is a per-item decision (approve, reject, substitute) and
    the header's is a case lifecycle. One shared graph would force every header rung
    onto every line and every line rung onto every header, and no fork could separate
    them again because the entity type is what the graph hangs off."""
    with blank_session() as db:
        graphs = _seeded(db)
        assert WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE != WORKFLOW_SUBMISSION_ENTITY_TYPE
        assert {s.key for s in graphs.line.statuses} != {
            s.key for s in graphs.header.statuses
        }
        assert not (
            {s.id for s in graphs.line.statuses} & {s.id for s in graphs.header.statuses}
        )


def test_lines_are_counted_by_status_id_and_a_forks_rows_count_against_the_fork():
    """ADR-0013 rule 6: an entity that under-reports its own usage lets an admin
    delete a status out from under live records. Counting by KEY would attribute a
    forked definition's lines to the DEFAULT graph's row, which is the failure
    FK-native registration exists to prevent."""
    with blank_session() as db:
        graphs = _seeded(db)
        entity = status_registry.get_status_entity(WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE)

        plain = _definition(db, derives=True)
        _created(db, plain, rows=2)
        assert entity.count_records(db, graphs.line.by_key("pending").id) == 2

        forked = _definition(db, derives=True)
        fork = fork_graph(db, WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE, forked.id)
        _created(db, forked, rows=1)

        assert entity.count_records(db, fork.by_key("pending").id) == 1
        assert entity.count_records(db, graphs.line.by_key("pending").id) == 2
        assert entity.count_records(db, "00000000-0000-0000-0000-0000000000ff") == 0


def test_migrating_lines_rewrites_the_fk():
    """Backs the "migrate records" flow an admin uses to retire a rung. Row by row
    rather than a bulk UPDATE, so the audit listener sees each change."""
    with blank_session() as db:
        graphs = _seeded(db)
        definition = _definition(db, derives=True)
        submission = _created(db, definition, rows=2)

        moved = migrate_records(
            db, graphs.line.by_key("pending"), graphs.line.by_key("rejected")
        )
        db.flush()
        assert moved == 2
        for row in _lines(db, submission):
            db.refresh(row)
            assert row.status_id == graphs.line.by_key("rejected").id


# ============================================================== AC-F1a-3
# Scoping: the definition, one hop through the submission.


def test_the_line_scope_resolver_reaches_the_definition_through_the_submission():
    """The indirect case ``scope_resolver`` was designed for, and the reason it is a
    callable rather than a column name. A line has no ``definition_id`` of its own, so
    a ``scope_attr`` could not express this at all -- and without it every definition
    would share one line graph and forking one would re-cut the rungs for all."""
    with blank_session() as db:
        _seeded(db)
        definition = _definition(db, derives=True)
        submission = _created(db, definition, rows=1)
        line = _lines(db, submission)[0]

        entity = status_registry.get_status_entity(WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE)
        assert entity.scope_for(line) == definition.id


def test_a_forked_definition_resolves_its_own_line_graph():
    """Same keys, different ids: shared keys keep reporting able to group one rung
    across every definition, and separate ids stop one definition's admin edit
    rewriting another's graph."""
    with blank_session() as db:
        graphs = _seeded(db)
        definition = _definition(db, derives=True)
        fork = fork_graph(db, WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE, definition.id)

        assert {s.key for s in fork.statuses} == {s.key for s in graphs.line.statuses}
        assert not ({s.id for s in fork.statuses} & {s.id for s in graphs.line.statuses})
        assert _edge_keys(fork) == _edge_keys(graphs.line)
        assert all(s.scope_id == definition.id for s in fork.statuses)

        submission = _created(db, definition, rows=1)
        line = _lines(db, submission)[0]
        assert line.status_id == fork.by_key("pending").id


def test_an_unforked_definition_inherits_the_default_line_graph():
    """A brand new definition must work with no configuration at all, which is what
    makes the default graph worth keeping minimal."""
    with blank_session() as db:
        graphs = _seeded(db)
        definition = _definition(db, derives=True)
        resolved = resolve_graph(
            db, WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE, definition.id
        )
        assert resolved.is_fork is False
        assert resolved.resolved_scope_id is None
        assert {s.id for s in resolved.statuses} == {s.id for s in graphs.line.statuses}


# ============================================================== AC-F1a-2/13
# The default line graph: minimal, and carrying the flags derivation reads.


def test_the_default_line_graph_keys_and_edges_are_pinned():
    """Widening the default pushes a form-specific rung onto every definition that
    inherits it (ADR-0013 rule 4's corollary), so it has to be a conscious act in two
    places rather than a side effect in one."""
    assert set(WORKFLOW_SUBMISSION_LINE_STATUS_KEYS) == LINE_GRAPH_KEYS
    assert len(WORKFLOW_SUBMISSION_LINE_STATUS_KEYS) == len(LINE_GRAPH_KEYS)
    assert {
        (seed.from_key, seed.to_key) for seed in WORKFLOW_SUBMISSION_LINE_TRANSITION_SEEDS
    } == LINE_GRAPH_EDGES

    with blank_session() as db:
        graphs = _seeded(db)
        assert {s.key for s in graphs.line.statuses} == LINE_GRAPH_KEYS
        assert _edge_keys(graphs.line) == LINE_GRAPH_EDGES


def test_the_line_graphs_trait_flags_carry_the_derivation_semantics():
    """These flags ARE the contract derivation reads (AC-F1a-13), so they are pinned
    here rather than left to the seed. ``cancelled`` is archived because that is the
    engine's flag for "not part of the live population", which is what excluding a
    cancelled line means; it is terminal as well, since a withdrawn line is final."""
    with blank_session() as db:
        graphs = _seeded(db)
        line = graphs.line

        assert [s.key for s in line.statuses if s.is_initial] == ["pending"]
        assert {s.key for s in line.statuses if s.is_terminal} == {
            "approved",
            "rejected",
            "cancelled",
        }
        assert {s.key for s in line.statuses if s.is_archived} == {"cancelled"}
        assert all(s.is_active for s in line.statuses)
        assert all(s.is_system for s in line.statuses)
        assert all(s.color_hex for s in line.statuses)
        assert all(s.scope_id is None and s.tenant_id is None for s in line.statuses)

        validate_graph(db, WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE, None)
        assert (
            initial_status(db, WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE, None).key == "pending"
        )


def test_the_line_seed_corrects_drift_rather_than_skipping_it():
    """Idempotent here means "set where mismatch", not "insert where absent"
    (ADR-0013 rule 10): an insert-if-absent seed can never repair a prior bad run,
    which is the whole reason a seed gets re-run. Correcting in place keeps the row's
    id, so every line pointing at it follows the repair."""
    with blank_session() as db:
        first = seed_workflow_submission_line_status_graph(db)
        db.flush()
        assert first["statuses_created"] == len(LINE_GRAPH_KEYS)
        assert first["transitions_created"] == len(LINE_GRAPH_EDGES)

        graph = resolve_graph(db, WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE, None)
        drifted = graph.by_key("approved")
        original_id = drifted.id
        drifted.label = "Accepted"
        drifted.is_terminal = False
        db.flush()

        second = seed_workflow_submission_line_status_graph(db)
        db.flush()
        assert second["statuses_created"] == 0, "a re-run must not duplicate rows"
        assert second["statuses_updated"] == 1

        repaired = resolve_graph(
            db, WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE, None
        ).by_key("approved")
        assert repaired.id == original_id, "correct in place, never re-create"
        assert repaired.is_terminal is True


def test_a_clean_line_seed_re_run_reports_no_changes():
    with blank_session() as db:
        seed_workflow_submission_line_status_graph(db)
        db.flush()
        again = seed_workflow_submission_line_status_graph(db)
        db.flush()
        assert again == {
            "statuses_created": 0,
            "statuses_updated": 0,
            "transitions_created": 0,
            "transitions_updated": 0,
        }


# ============================================================== AC-F1a-4/5
# The engine authorises a line move, and a stranded line says so.


def test_an_in_graph_line_transition_moves_the_line():
    """One authority, not a second per-line rule engine. The same guard that moves a
    header moves a line, so a line's legal moves are configuration rather than code."""
    with blank_session() as db:
        graphs = _seeded(db)
        definition = _definition(db, derives=True)
        submission = _created(db, definition, rows=1)
        line = _lines(db, submission)[0]

        moved = _decide(db, line, graphs.line.by_key("approved"))
        db.refresh(moved)
        assert moved.status_id == graphs.line.by_key("approved").id


def test_a_line_move_the_definitions_fork_removed_is_422_and_changes_nothing():
    """The fork's edges are the authority once a definition has one. If the guard
    resolved the default graph it would keep authorising a move this definition
    deliberately removed, which is the whole point of forking."""
    with blank_session() as db:
        _seeded(db)
        definition = _definition(db, derives=True)
        fork = fork_graph(db, WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE, definition.id)
        approve_edge = next(
            t
            for t in fork.transitions
            if t.from_status_id == fork.by_key("pending").id
            and t.to_status_id == fork.by_key("approved").id
        )
        db.delete(approve_edge)
        db.flush()

        submission = _created(db, definition, rows=1)
        line = _lines(db, submission)[0]
        with pytest.raises(AppException) as err:
            _decide(db, line, fork.by_key("approved"))
        assert err.value.status_code == 422
        assert err.value.detail["code"] == "status_transition_not_allowed"
        db.refresh(line)
        assert line.status_id == fork.by_key("pending").id


def test_re_deciding_a_settled_line_is_422():
    """A decided line is final, so nothing may move out of it -- which is also why
    reopening a submission has to come from a new or replaced line rather than from
    re-deciding an old one (see the reopen tests)."""
    with blank_session() as db:
        graphs = _seeded(db)
        definition = _definition(db, derives=True)
        submission = _created(db, definition, rows=1)
        line = _lines(db, submission)[0]
        _decide(db, line, graphs.line.by_key("approved"))

        with pytest.raises(AppException) as err:
            _decide(db, line, graphs.line.by_key("rejected"))
        assert err.value.status_code == 422
        assert err.value.detail["code"] == "status_terminal"
        db.refresh(line)
        assert line.status_id == graphs.line.by_key("approved").id


def test_a_status_from_the_headers_graph_cannot_be_applied_to_a_line():
    """"Whatever the client sends" includes a real ``statuses.id`` -- the header's own
    ``approved`` is the most likely mistake of all, since the two graphs share the key.
    Resolving by entity type AND scope is what rejects it."""
    with blank_session() as db:
        graphs = _seeded(db)
        definition = _definition(db, derives=True)
        submission = _created(db, definition, rows=1)
        line = _lines(db, submission)[0]

        with pytest.raises(AppException) as err:
            _decide(db, line, graphs.header.by_key("approved"))
        assert err.value.status_code == 422
        assert err.value.detail["code"] == "status_not_in_graph"
        db.refresh(line)
        assert line.status_id == graphs.line.by_key("pending").id


def test_a_line_stranded_outside_its_resolved_graph_reports_status_not_in_graph():
    """AC-F1a-5. ``fork_graph`` does not remap lines that already point at the default
    graph, so forking strands every existing line at once. Reported as "that move is
    not allowed" it reads as a graph-configuration question and sends the admin to
    edit edges that are perfectly fine; the truth is that the RECORD is outside its
    graph, and only the record-side guard can say so."""
    with blank_session() as db:
        graphs = _seeded(db)
        definition = _definition(db, derives=True)
        submission = _created(db, definition, rows=1)
        line = _lines(db, submission)[0]
        assert line.status_id == graphs.line.by_key("pending").id

        fork = fork_graph(db, WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE, definition.id)
        with pytest.raises(AppException) as err:
            _decide(db, line, fork.by_key("approved"))
        assert err.value.status_code == 422
        assert err.value.detail["code"] == "status_not_in_graph", (
            "the line is out of its graph; the edge is not the problem"
        )


def test_a_statusless_line_cannot_be_transitioned():
    """A line of a definition that never opted in holds NULL, which is not a rung of
    any graph. Failing closed with the same code as a stranded line keeps one answer
    for one question: this record is not on the graph you are trying to move it
    through."""
    with blank_session() as db:
        graphs = _seeded(db)
        definition = _definition(db)
        submission = _created(db, definition, rows=1)
        line = _lines(db, submission)[0]
        assert line.status_id is None

        with pytest.raises(AppException) as err:
            _decide(db, line, graphs.line.by_key("approved"))
        assert err.value.status_code == 422
        assert err.value.detail["code"] == "status_not_in_graph"


def test_a_line_transition_writes_no_submission_transition_log_of_its_own():
    """``workflow_submission_transition_logs`` is the HEADER's companion log. A line
    move that appended a row there would put a status the submission never held into
    its trail; the only row a line move may produce is the derived header move, and
    that one carries no user (see the attribution test)."""
    with blank_session() as db:
        graphs = _seeded(db)
        definition = _definition(db, derives=True)
        submission = _created(db, definition, rows=2)
        rows = _lines(db, submission)

        _decide(db, rows[0], graphs.line.by_key("approved"))
        assert _logs(db, submission) == [], (
            "the header did not move, so nothing belongs in its log"
        )


# ============================================================== AC-F1a-6/7/8
# Disposition: the existing lookup system, not a status and not a new table.


def test_the_disposition_column_is_a_string_holding_an_option_value():
    """It matches the seven existing bindings (``complaints.complaint_type`` and
    friends): a plain string column, validated app-side, with no FK to the lookup
    tables. That shape is what the admin lookup UI, the keyword resolver and the
    default-value behaviour are all already written against."""
    column = WorkflowSubmissionLine.__table__.c["disposition"]
    assert isinstance(column.type, String)
    assert not isinstance(column.type, PGUUID)
    assert column.nullable is True
    assert not column.foreign_keys, "a lookup value is not a foreign key here"
    assert LINE_DISPOSITION_TABLE == "workflow_submission_lines"
    assert LINE_DISPOSITION_COLUMN == "disposition"


def test_the_line_carries_a_free_text_disposition_reason():
    """AC-F1a-27. "Nothing to collect" requires a reason and there was nowhere for one
    to land. Free text rather than a second lookup: the reason is an explanation, not a
    classification, so binding it would force an admin to enumerate excuses.

    Nullable, because most dispositions explain themselves."""
    column = WorkflowSubmissionLine.__table__.c["disposition_reason"]
    assert isinstance(column.type, String)
    assert not isinstance(column.type, PGUUID)
    assert column.nullable is True
    assert not column.foreign_keys

    with blank_session() as db:
        _seeded(db)
        _seed_dispositions(db)
        definition = _definition(db, derives=True)
        submission = _created(db, definition, rows=1)
        line = _lines(db, submission)[0]
        service = WorkflowFormsService(db)
        value = _disposition_values()[0]

        service.set_line_disposition(
            str(line.id), value, "zzt-user", disposition_reason="ZZT customer kept it"
        )
        db.refresh(line)
        assert line.disposition == value
        assert line.disposition_reason == "ZZT customer kept it"

        # Clearing the disposition clears its reason: an explanation with nothing to
        # explain is a leftover, and it would be read as current.
        service.set_line_disposition(str(line.id), None, "zzt-user")
        db.refresh(line)
        assert line.disposition is None
        assert line.disposition_reason is None


def test_the_disposition_set_options_and_binding_are_seeded():
    """A disposition is configurable master data, not a lifecycle: no new table and
    no statuses. The binding row is what makes the column a dropdown, and it is
    tenant-NULL like every existing binding while the tenant is a stub."""
    with blank_session() as db:
        _seed_dispositions(db)

        lookup_set = (
            db.query(LookupSet)
            .filter(
                LookupSet.set_key == LINE_DISPOSITION_SET_KEY,
                LookupSet.tenant_id.is_(None),
            )
            .one()
        )
        assert lookup_set.is_active is True

        options = (
            db.query(LookupOption).filter(LookupOption.set_id == lookup_set.id).all()
        )
        assert len(options) == len(LINE_DISPOSITION_OPTIONS)
        assert {o.value for o in options} == set(_disposition_values())
        assert all(o.is_active for o in options)
        assert all(o.label for o in options)
        assert len(_disposition_values()) >= 2, (
            "the six per-line dispositions are the requirement; one is not a choice"
        )

        binding = (
            db.query(LookupBinding)
            .filter(
                LookupBinding.tenant_id.is_(None),
                LookupBinding.table_name == LINE_DISPOSITION_TABLE,
                LookupBinding.column_name == LINE_DISPOSITION_COLUMN,
            )
            .one()
        )
        assert binding.set_id == lookup_set.id


def test_the_disposition_seed_converges_rather_than_duplicating():
    """Same rule as a graph seed: a re-run repairs drift in place and never inserts a
    second set. A duplicated set would give the binding two candidate option lists and
    the validator would pick one non-deterministically."""
    with blank_session() as db:
        _seed_dispositions(db)
        lookup_set = (
            db.query(LookupSet)
            .filter(LookupSet.set_key == LINE_DISPOSITION_SET_KEY)
            .one()
        )
        original_id = lookup_set.id
        first_value = _disposition_values()[0]
        drifted = _option(db, first_value)
        drifted.label = "ZZT drifted label"
        drifted.is_active = False
        db.flush()

        _seed_dispositions(db)

        assert (
            db.query(LookupSet)
            .filter(LookupSet.set_key == LINE_DISPOSITION_SET_KEY)
            .one()
            .id
            == original_id
        )
        repaired = _option(db, first_value)
        assert repaired.label != "ZZT drifted label"
        assert repaired.is_active is True
        assert (
            db.query(LookupBinding)
            .filter(
                LookupBinding.table_name == LINE_DISPOSITION_TABLE,
                LookupBinding.column_name == LINE_DISPOSITION_COLUMN,
            )
            .count()
            == 1
        )


def test_an_active_option_is_accepted_and_can_be_cleared_again():
    """Clearing matters as much as setting: a disposition chosen by mistake has to be
    removable, and the column is nullable precisely so "no disposition yet" is
    representable."""
    with blank_session() as db:
        _seeded(db)
        _seed_dispositions(db)
        definition = _definition(db, derives=True)
        submission = _created(db, definition, rows=1)
        line = _lines(db, submission)[0]
        value = _disposition_values()[0]
        service = WorkflowFormsService(db)

        service.set_line_disposition(str(line.id), value, "zzt-user")
        db.refresh(line)
        assert line.disposition == value

        service.set_line_disposition(str(line.id), None, "zzt-user")
        db.refresh(line)
        assert line.disposition is None


def test_an_unknown_disposition_is_rejected():
    """Validated app-side against the bound set, exactly as the existing bindings are.
    Without it the column is free text and the dropdown is decoration."""
    with blank_session() as db:
        _seeded(db)
        _seed_dispositions(db)
        definition = _definition(db, derives=True)
        submission = _created(db, definition, rows=1)
        line = _lines(db, submission)[0]

        with pytest.raises(AppException) as err:
            WorkflowFormsService(db).set_line_disposition(
                str(line.id), "zzt_not_an_option", "zzt-user"
            )
        assert err.value.status_code == 422
        assert err.value.detail["code"] == "invalid_lookup_value"
        db.refresh(line)
        assert line.disposition is None


def test_an_inactive_option_is_rejected():
    """Deactivating is the lookup system's way of saying "kept for existing rows,
    closed to new ones". Validating against every option rather than the ACTIVE ones
    would keep a retired disposition selectable forever."""
    with blank_session() as db:
        _seeded(db)
        _seed_dispositions(db)
        definition = _definition(db, derives=True)
        submission = _created(db, definition, rows=1)
        line = _lines(db, submission)[0]
        retired = _disposition_values()[0]
        _option(db, retired).is_active = False
        db.flush()
        _lookup_cache_clear()

        with pytest.raises(AppException) as err:
            WorkflowFormsService(db).set_line_disposition(
                str(line.id), retired, "zzt-user"
            )
        assert err.value.detail["code"] == "invalid_lookup_value"


def test_the_bound_column_is_lookup_eligible_so_the_admin_can_edit_the_set():
    """What "reuses the existing lookup system" buys. If the pair is not eligible the
    admin screen cannot offer the binding at all, and the set becomes seed-only data
    nobody can extend -- which is how a "configurable" list turns back into code."""
    # The registry is a test-only override that short-circuits metadata introspection
    # when non-empty, and another module may have populated it.
    original = dict(lookup_eligibility._REGISTRY)
    lookup_eligibility._REGISTRY.clear()
    try:
        eligibility = lookup_eligibility.get_eligibility(
            LINE_DISPOSITION_TABLE, LINE_DISPOSITION_COLUMN
        )
    finally:
        lookup_eligibility._REGISTRY.update(original)
    assert eligibility is not None, (
        "workflow_submission_lines.disposition must be bindable in the lookup admin"
    )
    assert eligibility.data_type == "string"


def test_disposition_and_line_status_are_orthogonal():
    """AC-F1a-8. Two lines on the SAME status carry different dispositions, and a
    rejected line carries none. Collapsing them into one column, or deriving either
    from the other, loses the distinction the requirement is built on: what was
    decided, and how it will be settled, are different questions."""
    with blank_session() as db:
        graphs = _seeded(db)
        _seed_dispositions(db)
        values = _disposition_values()
        definition = _definition(db, derives=True)
        submission = _created(db, definition, rows=3)
        service = WorkflowFormsService(db)
        rows = _lines(db, submission)

        _decide(db, rows[0], graphs.line.by_key("approved"))
        service.set_line_disposition(str(rows[0].id), values[0], "zzt-user")
        _decide(db, rows[1], graphs.line.by_key("approved"))
        service.set_line_disposition(str(rows[1].id), values[1], "zzt-user")
        _decide(db, rows[2], graphs.line.by_key("rejected"))

        rows = _lines(db, submission)
        assert [row.status_key for row in rows] == ["approved", "approved", "rejected"]
        assert rows[0].disposition != rows[1].disposition
        assert rows[2].disposition is None


def test_setting_a_disposition_does_not_move_the_line_or_the_header():
    """The other direction of the same rule. A disposition is not a decision, so
    recording one must not decide the line -- and if it did, the header could resolve
    on a submission whose lines were never approved."""
    with blank_session() as db:
        _seeded(db)
        _seed_dispositions(db)
        definition = _definition(db, derives=True)
        submission = _created(db, definition, rows=1)
        line = _lines(db, submission)[0]

        WorkflowFormsService(db).set_line_disposition(
            str(line.id), _disposition_values()[0], "zzt-user"
        )

        db.refresh(line)
        assert line.status_key == "pending"
        assert _header_key(db, submission) == OPEN_KEY
        assert _logs(db, submission) == []


# ============================================================== AC-F1a-17
# Reporting groups by key. Never by id, never by category.


def test_line_reporting_groups_by_key_across_a_forked_graph():
    """A fork re-keys the ids for the same rungs, so grouping by id silently splits
    one pipeline rung into two columns -- one per definition -- and the roll-up stops
    being a roll-up. Statusless lines contribute nothing: they are on no rung."""
    with blank_session() as db:
        graphs = _seeded(db)

        plain = _definition(db, derives=True)
        plain_submission = _created(db, plain, rows=2)
        _decide(db, _lines(db, plain_submission)[0], graphs.line.by_key("approved"))

        forked = _definition(db, derives=True)
        fork = fork_graph(db, WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE, forked.id)
        forked_submission = _created(db, forked, rows=2)
        for row in _lines(db, forked_submission):
            _decide(db, row, fork.by_key("approved"))

        without_status = _definition(db)
        statusless = _created(db, without_status, rows=1)

        counts = line_status_counts_by_key(
            db,
            [
                str(plain_submission.id),
                str(forked_submission.id),
                str(statusless.id),
            ],
        )
        assert counts == {"approved": 3, "pending": 1}


def test_the_new_modules_never_branch_on_category():
    """``category`` is a legacy cosmetic mirror ADR-0001 demoted, and the engine
    already carries a grep test to keep itself clean of it. F1a's modules inherit that
    rule: a definition may rename or re-cut its rungs, and ``category`` is not
    maintained across a fork, so anything reading it decides on stale cosmetics."""
    for relative in NEW_MODULES:
        path = APP / relative
        assert path.exists(), f"{relative} does not exist yet"
        offenders = [
            f"{relative}:{number}"
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            )
            if "category" in line
        ]
        assert not offenders, f"F1a must not mention status category: {offenders}"
