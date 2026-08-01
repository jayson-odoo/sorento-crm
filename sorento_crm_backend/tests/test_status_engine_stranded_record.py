"""A record holding a status that is not in its own resolved graph.

This is reachable the moment `fork_graph` is used, which F1 made real: forking copies
statuses into a scope with FRESH ids, but does not remap records that already point at
the default graph. A submission created before its definition forked therefore holds a
default-graph `status_id` that its own scope no longer resolves.

The engine already refused to move such a record, so nothing unsafe happened. What it
got wrong was the REASON. `assert_transition_allowed` validated the target first and
only then looked for an outgoing edge, so a record whose current status the graph
cannot see reported `status_transition_not_allowed` -- "Moving from its current state to
'X' is not allowed" -- which tells an admin the graph is misconfigured when the real
problem is the record. Worse, the message says "its current state" because
`graph.by_id()` returned None and there was no label to print, so the one clue was
missing too.

These tests pin the honest failure: `status_not_in_graph`, naming the record's status.
They do NOT assert that forking remaps records; that is the other half of the fix and is
tracked separately. Getting the diagnosis right is what unblocks line-level status,
where one submission can strand many rows at once.
"""
from __future__ import annotations

import uuid

import pytest

from app.services.error_handler import AppException
from app.services.status_service import (
    assert_transition_allowed,
    assert_transition_allowed_by_key,
    available_transitions,
    fork_graph,
    resolve_graph,
)
from tests._pg_fixture import blank_session

_ENTITY = "zzt_stranded"


def _seed_two_rung_graph(db, scope_id=None):
    """`open -> done`, the smallest graph with a real edge.

    `trigger_mode` is left at its default because `assert_transition_allowed` only
    honours MANUAL edges; an auto edge here would make the guard look broken.
    """
    from app.models.status import Status, StatusTransition

    opened = Status(
        entity_type=_ENTITY, key="open", label="Open", color_hex="#888888",
        sort_order=0, is_initial=True, is_default=True, scope_id=scope_id,
    )
    done = Status(
        entity_type=_ENTITY, key="done", label="Done", color_hex="#22c55e",
        sort_order=1, is_terminal=True, scope_id=scope_id,
    )
    db.add_all([opened, done])
    db.flush()
    db.add(
        StatusTransition(
            entity_type=_ENTITY, from_status_id=opened.id, to_status_id=done.id,
            label="Finish", sort_order=0, scope_id=scope_id,
        )
    )
    db.flush()
    return opened, done


def test_a_status_outside_the_graph_is_reported_as_such_not_as_a_bad_transition():
    """The core fix. The record is wrong, so say the record is wrong.

    Before this, the code fell through to the edge lookup and blamed the transition,
    which sends whoever reads it to edit a graph that is fine.
    """
    with blank_session() as db:
        _opened, done = _seed_two_rung_graph(db)
        stranded = str(uuid.uuid4())  # an id no status in this graph carries

        with pytest.raises(AppException) as exc:
            assert_transition_allowed(db, _ENTITY, stranded, done.id)

        assert exc.value.detail["code"] == "status_not_in_graph"


def test_the_error_names_the_offending_status_id():
    """A bare "not in graph" is unactionable: you cannot find the record from it."""
    with blank_session() as db:
        _opened, done = _seed_two_rung_graph(db)
        stranded = str(uuid.uuid4())

        with pytest.raises(AppException) as exc:
            assert_transition_allowed(db, _ENTITY, stranded, done.id)

        assert stranded in str(exc.value.detail["message"])


def test_a_legitimate_illegal_move_still_reports_a_bad_transition():
    """The guard must not swallow the case it sits next to.

    Moving backwards from a terminal rung is a real transition error, and it must keep
    reporting as one. A guard that turned every refusal into `status_not_in_graph` would
    be just as misleading in the other direction.
    """
    with blank_session() as db:
        opened, done = _seed_two_rung_graph(db)

        with pytest.raises(AppException) as exc:
            assert_transition_allowed(db, _ENTITY, done.id, opened.id)

        assert exc.value.detail["code"] != "status_not_in_graph"


def test_no_current_status_is_still_allowed_to_enter_the_graph():
    """`from_status_id=None` is a first entry, not a stranded record.

    Conflating the two would block every record's creation, so this pins the boundary
    the guard must not cross.
    """
    with blank_session() as db:
        opened, _done = _seed_two_rung_graph(db)
        # Entering at the initial rung needs an edge INTO it, which a two-rung graph has
        # not got, so assert on the error rather than on success: the point is only that
        # it is not diagnosed as a stranded record.
        try:
            assert_transition_allowed(db, _ENTITY, None, opened.id)
        except AppException as exc:
            assert exc.detail["code"] != "status_not_in_graph"


def test_the_key_valued_adapter_reports_the_same_way():
    """Complaints ride the key-valued path, so it needs the same honesty.

    A complaint row holding a status string outside the graph is exactly the legacy case
    the adapter was written for, and it must not report a transition problem either.
    """
    with blank_session() as db:
        _opened, _done = _seed_two_rung_graph(db)

        with pytest.raises(AppException) as exc:
            assert_transition_allowed_by_key(db, _ENTITY, "not_a_real_key", "done")

        assert exc.value.detail["code"] == "status_not_in_graph"


def test_a_forked_scope_strands_a_default_graph_status():
    """The real-world route in, rather than a synthetic uuid.

    Forking gives the scope fresh ids for the same keys, so a record still pointing at
    the default graph's id is outside the graph its own scope resolves. This is the case
    that made the misleading message reachable.
    """
    scope = str(uuid.uuid4())
    with blank_session() as db:
        default_open, _default_done = _seed_two_rung_graph(db)
        fork_graph(db, _ENTITY, scope)
        db.flush()

        forked = resolve_graph(db, _ENTITY, scope)
        forked_done = next(s for s in forked.statuses if s.key == "done")

        # Same keys, different ids: that is what strands the record.
        assert default_open.id != next(s.id for s in forked.statuses if s.key == "open")

        with pytest.raises(AppException) as exc:
            assert_transition_allowed(db, _ENTITY, default_open.id, forked_done.id, scope)

        assert exc.value.detail["code"] == "status_not_in_graph"


def test_available_transitions_is_empty_for_a_stranded_record():
    """Documents the symptom an admin sees, so the fix is not mistaken for the cause.

    The empty list is correct and stays correct. What changed is that ACTING on such a
    record now explains itself.
    """
    with blank_session() as db:
        _seed_two_rung_graph(db)
        assert available_transitions(db, _ENTITY, str(uuid.uuid4())) == []
