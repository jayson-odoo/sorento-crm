"""A submission header DERIVED from its lines, and the guards that keep it single-writer.

The whole risk of this slice is one thing: **a derived value that is also writable is two
sources of truth.** ADR-0013 rule 11 allows exactly one writer of a status column, so a
deriving definition's header is written HERE and nowhere else, and
``assert_manual_header_move_allowed`` refuses the human path into or out of the two rungs
this module owns.

**Opt-in, in columns.** ``derives_status_from_lines`` plus two status KEYS on the
definition. Columns rather than a key inside the versioned document, because a published
version is an immutable snapshot -- config living there could not be changed without
republishing, and the guard that refuses a manual move would have to parse a JSONB
document on every transition. Keys rather than ids, because a definition that forks its
header graph gets fresh ids for the same rungs.

**Derivation owns the declared pair and nothing else.** A header parked anywhere else
(closed, rejected, a rung an admin added) is never hijacked, or enabling derivation on an
existing form would drag every submission onto a rung the definition never asked for.
The precedent is explicit about this: ``complaint_fulfilment_service`` toggles
``processed_by_cs`` <-> ``fulfilled`` and leaves ``closed`` / ``rejected`` alone.

**Both directions.** Forward-only derivation is the likely half-implementation, and it
leaves a resolved submission that can never be corrected. The same precedent reopens a
``fulfilled`` complaint when one of its DOs stops being delivered; the reachable triggers
here are a line added, lines replaced, or an admin clearing ``is_terminal`` on a rung.
Derivation's contract is to NOTICE that the population changed, not to be the path that
changed it, so it recomputes from whatever state it finds.

**Trait flags, never key strings.** The population is "lines whose status is not
``is_archived``", and "decided" is ``is_terminal``. A definition may rename or re-cut its
line rungs; the flags are the engine's machine semantics and are the only thing this
module may read.

**The empty population is NOT derivable.** Zero lines, and every-line-excluded, both
land there. ``all(...)`` over an empty sequence is True, so a naive implementation
resolves a submission nobody has worked on -- the same bug class as an empty ``rules[]``
matching everything. "Not derivable" is a different answer from "derivable and open", and
the header stays put.

**A misconfiguration is loud.** A declared key its graph does not have degrades into "not
derivable", which reads as a working form that simply never closes (ADR-0013 rule 12), so
it raises instead. The same pair is validated when the definition is saved, where the
admin can still fix it.
"""
from __future__ import annotations

import uuid
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.status import Status
from app.models.workflow_forms import (
    WorkflowFormDefinition,
    WorkflowSubmission,
    WorkflowSubmissionLine,
    WorkflowSubmissionTransitionLog,
)
from app.services.error_handler import AppException
from app.services.status_service import resolve_graph
from app.services.workflow_submission_line_status_graph import (
    WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE,
)
from app.services.workflow_submission_status_graph import (
    WORKFLOW_SUBMISSION_ENTITY_TYPE,
)

# What a reviewer reads to tell one kind of log row from the other. The transition log's
# only actor column is ``user_id``, an FK to ``users.id``, so a sentinel actor string is
# impossible: a derived move is marked by a NULL user, a NULL edge and this remark.
DERIVED_TRANSITION_REMARK = "Derived from the submission's line statuses"


def definition_derives_status(definition: Optional[WorkflowFormDefinition]) -> bool:
    """Whether this definition's header is computed from its lines.

    The flag alone. A definition that declares derivation with a bad key is
    MISCONFIGURED, not non-deriving: answering False here would turn a broken form into a
    silently normal one, which is the failure this module is written to avoid.
    """
    if definition is None:
        return False
    return bool(getattr(definition, "derives_status_from_lines", False))


def _misconfigured(definition: WorkflowFormDefinition, problem: str) -> AppException:
    name = str(getattr(definition, "name", "") or getattr(definition, "code", "") or "")
    return AppException(
        status_code=422,
        message=(
            f"This form ('{name}') derives its status from its lines, but its "
            f"configuration cannot be used: {problem}"
        ),
        code="status_derivation_misconfigured",
    )


def derived_pair(
    db: Session, definition: WorkflowFormDefinition
) -> Tuple[Status, Status]:
    """The (open, resolved) statuses this definition declared. Raises when unusable.

    Resolved against the HEADER graph in force for this definition, so a forked graph's
    own rows are what the keys name.
    """
    open_key = str(getattr(definition, "derived_open_status_key", None) or "").strip()
    resolved_key = str(
        getattr(definition, "derived_resolved_status_key", None) or ""
    ).strip()
    if not open_key or not resolved_key:
        raise _misconfigured(
            definition,
            "it must declare both an open status and a resolved status.",
        )

    graph = resolve_graph(db, WORKFLOW_SUBMISSION_ENTITY_TYPE, str(definition.id))
    open_status = graph.by_key(open_key)
    resolved_status = graph.by_key(resolved_key)
    if open_status is None or resolved_status is None:
        missing = [
            key
            for key, status in ((open_key, open_status), (resolved_key, resolved_status))
            if status is None
        ]
        raise _misconfigured(
            definition,
            f"its status graph has no rung called {', '.join(repr(k) for k in missing)}.",
        )
    if str(open_status.id) == str(resolved_status.id):
        raise _misconfigured(
            definition,
            "the open and resolved statuses must be two different rungs.",
        )
    return open_status, resolved_status


def assert_derivation_config(db: Session, definition: WorkflowFormDefinition) -> None:
    """Validate the declared pair when a definition is SAVED. Raises 422.

    Two rules, both otherwise silent and both permanent once a submission exists:

    * The open key must be the graph's INITIAL rung. A submission is created on the
      initial rung, so if the open key is anything else the submission sits outside the
      declared pair forever, derivation correctly refuses to hijack it, and the manual
      guard refuses every move into the pair: permanently stuck.
    * The resolved key must NOT be terminal. ``update_submission`` refuses to edit a
      submission whose header is terminal, and adding a line is the main reachable way to
      reopen one, so a terminal resolved rung freezes the submission. Closing for good is
      a separate manual move, which the manual guard permits.
    """
    if not definition_derives_status(definition):
        return
    open_status, resolved_status = derived_pair(db, definition)
    if not bool(open_status.is_initial):
        raise _misconfigured(
            definition,
            (
                f"the open status must be the graph's starting state, and "
                f"'{open_status.label}' is not. A submission starts on the starting "
                "state, so it would never be inside the derived pair."
            ),
        )
    if bool(resolved_status.is_terminal):
        raise _misconfigured(
            definition,
            (
                f"the resolved status must not be a final status, and "
                f"'{resolved_status.label}' is. A final status cannot be edited or "
                "reopened, so adding a line could never reopen the submission."
            ),
        )


def derived_pair_ids(
    db: Session, definition: Optional[WorkflowFormDefinition]
) -> Optional[Tuple[str, str]]:
    """``(open_id, resolved_id)`` for a deriving definition, else None.

    None means "nothing is derived here", which is a different answer from a
    misconfiguration: a declared key the graph does not have still raises.
    """
    if not definition_derives_status(definition):
        return None
    open_status, resolved_status = derived_pair(db, definition)
    return str(open_status.id), str(resolved_status.id)


def assert_manual_header_move_allowed(
    db: Session,
    definition: WorkflowFormDefinition,
    from_status_id: Optional[str],
    to_status_id: str,
) -> None:
    """Refuse a hand-made move INTO the derived pair. Raises 422.

    Gated on the TARGET only, and that asymmetry is the whole design:

    * Moving **into** either derived rung is refused. Those two values are derivation's
      to write, and ADR-0013 rule 11 allows exactly one writer per derived value.
    * Moving **out** of the pair is allowed. Once the header is parked outside both
      declared rungs, `recompute_submission_status` leaves it alone, so there is no
      second writer to conflict with. That is the same shape as
      `complaint_fulfilment_service`, where `closed` and `rejected` are sticky and
      auto-fulfilment declines to touch them.

    An earlier version refused a move when EITHER endpoint was in the pair, which read as
    the safer choice and was in fact unusable: `assert_derivation_config` forces the open
    key to be the graph's initial rung, so a submission is always created ON a pair rung,
    so `from` was always in the pair, so every manual move was refused. The practical
    symptom was that `allowed-transitions` returned an empty list forever and a deriving
    submission had no action buttons at all -- the opposite of the "it can still be closed
    by hand" property the pair-scoping was introduced to provide.
    """
    if not definition_derives_status(definition):
        return
    open_status, resolved_status = derived_pair(db, definition)
    pair = {
        str(open_status.id): str(open_status.label),
        str(resolved_status.id): str(resolved_status.label),
    }
    target = str(to_status_id or "")
    if target not in pair:
        return
    labels = pair[target]
    raise AppException(
        status_code=422,
        message=(
            f"This submission's status follows its lines, so it cannot be moved into or "
            f"out of {labels} by hand. Decide the lines instead."
        ),
        code="status_derived_not_writable",
    )


def _line_population(
    db: Session, submission: WorkflowSubmission, definition: WorkflowFormDefinition
) -> List[bool]:
    """One ``is_terminal`` answer per line that counts, excluded lines dropped.

    A line with NO status is a member and counts as undecided: a statusless line is
    undecided, never absent, and filtering ``status_id IS NOT NULL`` out of the
    population would resolve a submission on the strength of whichever lines happen to
    have been stamped.

    A line holding a status the resolved graph does not contain is REFUSED rather than
    guessed at. ``fork_graph`` does not remap records that already point at the default
    graph, so forking a definition strands every existing line at once, and
    ``line.status.is_terminal`` would answer happily with a flag from a graph the line no
    longer belongs to.
    """
    lines: List[WorkflowSubmissionLine] = (
        db.query(WorkflowSubmissionLine)
        .filter(WorkflowSubmissionLine.submission_id == submission.id)
        .all()
    )
    if not lines:
        return []

    graph = resolve_graph(
        db, WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE, str(definition.id)
    )
    population: List[bool] = []
    for line in lines:
        status_id = getattr(line, "status_id", None)
        if status_id is None:
            population.append(False)
            continue
        status = graph.by_id(str(status_id))
        if status is None:
            raise AppException(
                status_code=422,
                message=(
                    f"A line of this submission holds a status ({status_id}) that is not "
                    "part of the line status graph in force for its form, so the "
                    "submission's status cannot be worked out. Its status was most "
                    "likely set before that graph was forked."
                ),
                code="status_not_in_graph",
            )
        if bool(status.is_archived):
            continue  # excluded, not done
        population.append(bool(status.is_terminal))
    return population


def _definition_for(
    db: Session, submission: WorkflowSubmission
) -> Optional[WorkflowFormDefinition]:
    definition = getattr(submission, "definition", None)
    if definition is not None:
        return definition
    return (
        db.query(WorkflowFormDefinition)
        .filter(WorkflowFormDefinition.id == submission.definition_id)
        .first()
    )


def derive_status_key(db: Session, submission: WorkflowSubmission) -> Optional[str]:
    """The status key this submission's lines imply, or None when they imply nothing.

    None means "not derivable" and is returned for a definition that never opted in and
    for an empty population. It is deliberately NOT the open key: "we cannot say" and
    "we say it is open" are different answers, and conflating them resolves or reopens
    submissions on the strength of nothing.
    """
    definition = _definition_for(db, submission)
    if not definition_derives_status(definition):
        return None
    open_status, resolved_status = derived_pair(db, definition)

    population = _line_population(db, submission, definition)
    if not population:
        return None
    return str(resolved_status.key) if all(population) else str(open_status.key)


def recompute_submission_status(db: Session, submission: WorkflowSubmission) -> bool:
    """Move the header if its lines now say something else. True when it moved.

    No ``user_id`` parameter: a derived move has no human mover, and naming one is a lie
    in the audit trail that is plausible enough to be believed, because a person really
    did move a line a moment earlier.

    **Not routed through ``assert_transition_allowed``.** The declared resolved rung is
    reached and left without any edge authorising it: in a normal graph nothing leaves a
    final status at all, so an edge-bound implementation could never reopen and would
    raise ``status_terminal`` instead. The single writer of a derived header answers to
    the line statuses, not to the edges. That is also why the log row carries no
    ``status_transition_id``.

    Writes nothing and logs nothing when the answer is unchanged: a derived value that
    appends history on every pass floods the trail with rows a reviewer has to read past.
    Flushes but never commits, so the caller owns the transaction boundary.
    """
    definition = _definition_for(db, submission)
    if not definition_derives_status(definition):
        return False

    open_status, resolved_status = derived_pair(db, definition)
    key = derive_status_key(db, submission)
    if key is None:
        return False

    target = resolved_status if key == str(resolved_status.key) else open_status
    target_id = str(target.id)
    current_id = str(getattr(submission, "status_id", "") or "")
    if current_id == target_id:
        return False
    if current_id not in {str(open_status.id), str(resolved_status.id)}:
        # Parked outside the pair: closed, rejected, or a rung this definition added.
        # Derivation owns the pair and nothing else, so it leaves this alone rather than
        # dragging the submission back onto a rung nobody asked for.
        return False

    setattr(submission, "status_id", target_id)
    # ``updated_by_user_id`` is deliberately untouched for the same reason the log row
    # carries no user: nobody made this move.
    db.add(
        WorkflowSubmissionTransitionLog(
            id=str(uuid.uuid4()),
            submission_id=str(getattr(submission, "id", "") or ""),
            from_status_id=current_id or None,
            to_status_id=target_id,
            status_transition_id=None,
            remark=DERIVED_TRANSITION_REMARK,
            user_id=None,
        )
    )
    db.flush()
    return True
