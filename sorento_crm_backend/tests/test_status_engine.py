"""S1 gate - status engine (UAC Group B, ADR-0001).

Covers the engine contract: graph resolution, the two-tier default/fork model,
the server-side transition guard, structural validation, and the
delete-blocked-if-referenced flow.

Record counting and migration are tested against a SYNTHETIC registered entity.
That is deliberate: S1 owns the engine's *contract* (does the guard consult the
entity? does migrate delegate?), while the first real DB-backed entity arrives with
`projects` in S2 and is tested there against real rows.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.status import TRIGGER_AUTO, TRIGGER_MANUAL, Status, StatusTransition
from app.services.error_handler import AppException
from app.services.status_service import (
    assert_edge_valid,
    assert_status_deletable,
    assert_transition_allowed,
    available_transitions,
    fork_graph,
    initial_status,
    keys_by_entity,
    migrate_records,
    resolve_graph,
    validate_graph,
)
from app.status_engine import registry as status_registry
from app.status_engine.registry import StatusEntity, register_status_entity

from ._pg_fixture import blank_session

ENTITY = "zzt_pipeline"


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture(autouse=True)
def _isolate_registry():
    """The status registry is process-global; snapshot and restore it.

    ``list_status_entities()`` first, to force the lazy module discovery to run
    BEFORE the snapshot is taken. Population is lazy and fires once per process, so
    snapshotting an empty registry and then restoring it would wipe every real
    module entity for the rest of the session -- and ``lazy_once`` would never
    re-populate it. That shows up as another test file failing only when run after
    this one.
    """
    status_registry.list_status_entities()
    saved = dict(status_registry._REGISTRY)
    yield
    status_registry._REGISTRY.clear()
    status_registry._REGISTRY.update(saved)


def _status(db, key, label, *, scope_id=None, order=0, initial=False, terminal=False,
            active=True, system=False):
    row = Status(
        id=_uid(),
        entity_type=ENTITY,
        key=key,
        label=label,
        sort_order=order,
        is_initial=initial,
        is_terminal=terminal,
        is_active=active,
        is_system=system,
        scope_id=scope_id,
    )
    db.add(row)
    db.flush()
    return row


def _edge(db, src, dst, label, *, mode=TRIGGER_MANUAL, conditions=None, scope_id=None):
    row = StatusTransition(
        id=_uid(),
        entity_type=ENTITY,
        from_status_id=src.id,
        to_status_id=dst.id,
        label=label,
        trigger_mode=mode,
        conditions_json=conditions,
        scope_id=scope_id if scope_id is not None else src.scope_id,
    )
    db.add(row)
    db.flush()
    return row


def _ladder(db, scope_id=None):
    """registered -> quoted -> po_received, matching the real project ladder."""
    registered = _status(db, "registered", "Registered", order=0, initial=True, scope_id=scope_id)
    quoted = _status(db, "quoted", "Quoted", order=1, scope_id=scope_id)
    won = _status(db, "po_received", "PO Received", order=2, terminal=True, scope_id=scope_id)
    _edge(db, registered, quoted, "Quote issued")
    _edge(db, quoted, won, "PO received")
    return registered, quoted, won


# ------------------------------------------------------------- AC-B1 / B2a


def test_statuses_are_global_and_uuid_keyed():
    """AC-B2a. A company_id here would fork the pipeline definition per company;
    ADR-0001 decided SRT and MOCHA share one."""
    assert not hasattr(Status, "company_id")
    assert not hasattr(StatusTransition, "company_id")
    for model in (Status, StatusTransition):
        assert model.__table__.c.id.type.__class__.__name__ == "UUID", (
            f"{model.__name__}.id must be UUID, not String -- the pg-UUID-vs-varchar "
            "drift is what broke user_sessions.id auth on production."
        )


def test_workflow_stages_table_is_gone():
    """AC-B1/B6. Superseded by the engine; it held zero rows and zero readers."""
    from sqlalchemy import inspect

    from app.database import engine

    assert "workflow_stages" not in inspect(engine).get_table_names()


# ------------------------------------------------------------------- AC-B2


def test_forked_graph_rolls_up_by_key_not_id():
    """AC-B2. A fork has different ids for the same rung, so reporting MUST group
    by key. This is the test that would fail if someone switched the roll-up axis
    back to id (or to the cosmetic `category`)."""
    with blank_session() as db:
        _ladder(db)
        template = _uid()
        fork_graph(db, ENTITY, template)

        default = resolve_graph(db, ENTITY, None)
        forked = resolve_graph(db, ENTITY, template)

        default_ids = {s.id for s in default.statuses}
        forked_ids = {s.id for s in forked.statuses}
        assert default_ids.isdisjoint(forked_ids), "a fork must own distinct rows"

        # Same rungs, same keys -> one roll-up bucket per rung across both graphs.
        assert {s.key for s in default.statuses} == {s.key for s in forked.statuses}
        assert sorted(keys_by_entity(db, ENTITY)) == ["po_received", "quoted", "registered"]


def test_category_is_cosmetic_and_optional():
    """AC-B2. The source marks category a legacy cosmetic mirror; a graph must be
    fully functional without it."""
    with blank_session() as db:
        _ladder(db)
        graph = resolve_graph(db, ENTITY, None)
        assert all(s.category is None for s in graph.statuses)
        assert graph.initial is not None
        validate_graph(db, ENTITY, None)


# ------------------------------------------------------------------- AC-B3


def test_unforked_scope_inherits_the_default_graph():
    with blank_session() as db:
        _ladder(db)
        graph = resolve_graph(db, ENTITY, _uid())
        assert graph.is_fork is False
        assert graph.resolved_scope_id is None
        assert len(graph.statuses) == 3


def test_fork_is_copy_on_write_and_idempotent():
    with blank_session() as db:
        _ladder(db)
        template = _uid()

        first = fork_graph(db, ENTITY, template)
        assert first.is_fork is True
        assert len(first.statuses) == 3
        assert len(first.transitions) == 2
        # Edges must be remapped onto the CLONED statuses, never left pointing at
        # the default graph's rows.
        cloned_ids = {s.id for s in first.statuses}
        assert all(
            t.from_status_id in cloned_ids and t.to_status_id in cloned_ids
            for t in first.transitions
        )

        again = fork_graph(db, ENTITY, template)
        assert {s.id for s in again.statuses} == cloned_ids, "fork must not duplicate"


def test_editing_the_default_does_not_rewrite_an_existing_fork():
    """AC-B3. The whole point of copy-on-write: a tuned fork is not silently
    overwritten when the default changes."""
    with blank_session() as db:
        registered, _, _ = _ladder(db)
        template = _uid()
        fork_graph(db, ENTITY, template)

        registered.label = "Renamed In Default"
        db.flush()

        forked = resolve_graph(db, ENTITY, template)
        assert forked.by_key("registered").label == "Registered"


def test_fork_without_a_default_graph_is_rejected():
    with blank_session() as db:
        with pytest.raises(AppException) as err:
            fork_graph(db, ENTITY, _uid())
        assert err.value.status_code == 422


def test_a_fork_is_editable_so_clones_are_never_system_rows():
    with blank_session() as db:
        _status(db, "registered", "Registered", initial=True, system=True)
        _status(db, "done", "Done", order=1, terminal=True, system=True)
        template = _uid()
        forked = fork_graph(db, ENTITY, template)
        assert all(s.is_system is False for s in forked.statuses)


# ------------------------------------------------------------------- AC-B4


def test_illegal_transition_is_rejected_server_side():
    """AC-B4. Registered -> PO Received has no edge; dragging a card there fails
    here, not in the browser."""
    with blank_session() as db:
        registered, _, won = _ladder(db)
        with pytest.raises(AppException) as err:
            assert_transition_allowed(db, ENTITY, registered.id, won.id)
        assert err.value.status_code == 422
        assert err.value.detail["code"] == "status_transition_not_allowed"


def test_legal_transition_returns_the_authorising_edge():
    with blank_session() as db:
        registered, quoted, _ = _ladder(db)
        edge = assert_transition_allowed(db, ENTITY, registered.id, quoted.id)
        assert edge.label == "Quote issued"


def test_cannot_move_out_of_a_terminal_status():
    with blank_session() as db:
        registered, quoted, won = _ladder(db)
        # An edge out of a terminal status should not exist, but if one is forced
        # into the DB the guard must still refuse to fire it.
        _edge(db, won, registered, "Reopen")
        with pytest.raises(AppException) as err:
            assert_transition_allowed(db, ENTITY, won.id, registered.id)
        assert err.value.detail["code"] == "status_terminal"


def test_cannot_move_into_a_deactivated_status():
    with blank_session() as db:
        registered, quoted, _ = _ladder(db)
        quoted.is_active = False
        db.flush()
        with pytest.raises(AppException) as err:
            assert_transition_allowed(db, ENTITY, registered.id, quoted.id)
        assert err.value.detail["code"] == "status_inactive"


def test_status_from_another_graph_is_rejected():
    with blank_session() as db:
        registered, _, _ = _ladder(db)
        outsider = Status(
            id=_uid(), entity_type="zzt_other", key="x", label="Outsider", is_initial=True
        )
        db.add(outsider)
        db.flush()
        with pytest.raises(AppException) as err:
            assert_transition_allowed(db, ENTITY, registered.id, outsider.id)
        assert err.value.detail["code"] == "status_not_in_graph"


def test_auto_edges_are_not_offered_as_user_actions():
    """An auto edge belongs to the engine. Offering it as a button would let a
    user bypass its conditions."""
    with blank_session() as db:
        registered, quoted, won = _ladder(db)
        _edge(
            db, registered, won, "Auto win",
            mode=TRIGGER_AUTO, conditions={"all": [{"fact": "record.pos.count", "op": "gte", "value": 1}]},
        )
        offered = available_transitions(db, ENTITY, registered.id)
        assert [t.label for t in offered] == ["Quote issued"]

        # ...and it cannot be fired manually either.
        with pytest.raises(AppException) as err:
            assert_transition_allowed(db, ENTITY, registered.id, won.id)
        assert err.value.detail["code"] == "status_transition_not_allowed"


def test_no_transitions_offered_from_a_terminal_status():
    with blank_session() as db:
        _, _, won = _ladder(db)
        assert available_transitions(db, ENTITY, won.id) == []


# ----------------------------------------------------------- edge validation


def test_auto_edge_without_conditions_is_rejected():
    """An unconditional auto edge would fire immediately and unconditionally."""
    with blank_session() as db:
        registered, quoted, _ = _ladder(db)
        with pytest.raises(AppException) as err:
            assert_edge_valid(db, ENTITY, registered.id, quoted.id, TRIGGER_AUTO, None)
        assert err.value.detail["code"] == "status_auto_needs_conditions"


def test_self_loop_edge_is_rejected():
    with blank_session() as db:
        registered, _, _ = _ladder(db)
        with pytest.raises(AppException) as err:
            assert_edge_valid(db, ENTITY, registered.id, registered.id, TRIGGER_MANUAL, None)
        assert err.value.detail["code"] == "status_self_loop"


def test_edge_cannot_cross_graphs():
    with blank_session() as db:
        registered, _, _ = _ladder(db)
        template = _uid()
        forked = fork_graph(db, ENTITY, template)
        with pytest.raises(AppException) as err:
            assert_edge_valid(
                db, ENTITY, registered.id, forked.by_key("quoted").id, TRIGGER_MANUAL, None
            )
        assert err.value.detail["code"] == "status_scope_mismatch"


# ------------------------------------------------------ structural validation


def test_graph_needs_exactly_one_initial_status():
    with blank_session() as db:
        _ladder(db)
        extra = _status(db, "extra", "Extra", order=9, initial=True)
        with pytest.raises(AppException) as err:
            validate_graph(db, ENTITY, None)
        assert err.value.detail["code"] == "status_graph_multiple_initial"

        extra.is_initial = False
        db.flush()
        validate_graph(db, ENTITY, None)


def test_graph_without_an_initial_status_is_rejected():
    with blank_session() as db:
        registered, _, _ = _ladder(db)
        registered.is_initial = False
        db.flush()
        with pytest.raises(AppException) as err:
            validate_graph(db, ENTITY, None)
        assert err.value.detail["code"] == "status_graph_no_initial"


def test_terminal_status_cannot_have_outgoing_edges():
    with blank_session() as db:
        registered, _, won = _ladder(db)
        _edge(db, won, registered, "Reopen")
        with pytest.raises(AppException) as err:
            validate_graph(db, ENTITY, None)
        assert err.value.detail["code"] == "status_terminal_has_outgoing"


def test_initial_status_returns_the_starting_state():
    with blank_session() as db:
        _ladder(db)
        assert initial_status(db, ENTITY, None).key == "registered"


def test_initial_status_raises_when_no_graph_configured():
    with blank_session() as db:
        with pytest.raises(AppException) as err:
            initial_status(db, "zzt_unconfigured", None)
        assert err.value.detail["code"] == "status_graph_missing"


# --------------------------------------------------- AC-B5 delete + migrate


def _register_synthetic_entity(counts: dict):
    """A registered entity whose record store is a plain dict, so the engine's
    delegation can be asserted without a domain table."""

    def count_records(db, status_id):
        return counts.get(status_id, 0)

    def migrate(db, from_id, to_id):
        moved = counts.pop(from_id, 0)
        counts[to_id] = counts.get(to_id, 0) + moved
        return moved

    register_status_entity(
        StatusEntity(
            entity_type=ENTITY,
            label="Pipeline probe",
            module="zzt",
            count_records=count_records,
            migrate_records=migrate,
        )
    )


def test_delete_is_blocked_while_records_hold_the_status():
    with blank_session() as db:
        _, quoted, _ = _ladder(db)
        _register_synthetic_entity({quoted.id: 4})
        with pytest.raises(AppException) as err:
            assert_status_deletable(db, quoted)
        assert err.value.status_code == 422
        assert err.value.detail["code"] == "status_in_use"
        assert err.value.detail["message"] == (
            "4 records still use 'Quoted'. Move them to another status first."
        )


def test_blocked_delete_message_is_singular_for_one_record():
    with blank_session() as db:
        _, quoted, _ = _ladder(db)
        _register_synthetic_entity({quoted.id: 1})
        with pytest.raises(AppException) as err:
            assert_status_deletable(db, quoted)
        assert err.value.detail["message"] == (
            "1 record still use 'Quoted'. Move them to another status first."
        )


def test_user_facing_errors_never_hide_their_message_behind_detail():
    """Guards a frontend trap that is invisible from the backend.

    ``extractApiError`` returns ``error.detail`` in preference to
    ``error.message``, so any AppException that sets ``detail`` shows the user the
    detail INSTEAD of the message. Two errors here originally did that: the
    blocked-delete hid its record count behind an internal hint, and the conflict
    handler would have shown a raw Postgres constraint violation.
    """
    with blank_session() as db:
        registered, quoted, won = _ladder(db)
        _register_synthetic_entity({quoted.id: 2})

        raised: list[AppException] = []
        for call in (
            lambda: assert_status_deletable(db, quoted),
            lambda: assert_transition_allowed(db, ENTITY, registered.id, won.id),
            lambda: assert_edge_valid(db, ENTITY, registered.id, quoted.id, TRIGGER_AUTO, None),
            lambda: migrate_records(db, quoted, quoted),
            lambda: initial_status(db, "zzt_unconfigured", None),
        ):
            with pytest.raises(AppException) as err:
                call()
            raised.append(err.value)

        for exc in raised:
            assert exc.detail["message"], "every error needs a readable message"
            assert exc.detail["detail"] is None, (
                f"'{exc.detail['code']}' sets detail={exc.detail['detail']!r}, which the "
                "frontend shows INSTEAD of the message. Fold it into the message."
            )


def test_delete_allowed_once_no_records_hold_it():
    with blank_session() as db:
        _, quoted, _ = _ladder(db)
        _register_synthetic_entity({})
        assert_status_deletable(db, quoted)  # no raise


def test_system_status_cannot_be_deleted():
    with blank_session() as db:
        _ladder(db)
        seeded = _status(db, "seeded", "Seeded", order=8, system=True)
        _register_synthetic_entity({})
        with pytest.raises(AppException) as err:
            assert_status_deletable(db, seeded)
        assert err.value.detail["code"] == "status_is_system"


def test_delete_guard_is_permissive_when_no_module_registered_the_entity():
    """An unregistered entity reports zero usage. That is correct: if no module
    claims the entity, no live records can be holding its statuses."""
    with blank_session() as db:
        _, quoted, _ = _ladder(db)
        assert_status_deletable(db, quoted)


def test_migrate_records_delegates_to_the_entity():
    with blank_session() as db:
        _, quoted, won = _ladder(db)
        counts = {quoted.id: 7}
        _register_synthetic_entity(counts)
        assert migrate_records(db, quoted, won) == 7
        assert counts == {won.id: 7}
        assert_status_deletable(db, quoted)  # now free to delete


def test_migrate_into_the_same_status_is_rejected():
    with blank_session() as db:
        _, quoted, _ = _ladder(db)
        _register_synthetic_entity({quoted.id: 1})
        with pytest.raises(AppException) as err:
            migrate_records(db, quoted, quoted)
        assert err.value.detail["code"] == "status_migrate_same"


def test_migrate_across_entity_types_is_rejected():
    with blank_session() as db:
        _, quoted, _ = _ladder(db)
        other = Status(
            id=_uid(), entity_type="zzt_other", key="x", label="Other", is_initial=True
        )
        db.add(other)
        db.flush()
        _register_synthetic_entity({quoted.id: 1})
        with pytest.raises(AppException) as err:
            migrate_records(db, quoted, other)
        assert err.value.detail["code"] == "status_entity_mismatch"


# ---------------------------------------------------------- registry surface


def test_status_entities_payload_reports_scope_support():
    from app.services.status_service import status_entities_payload

    register_status_entity(
        StatusEntity(
            entity_type=ENTITY,
            label="Pipeline probe",
            module="zzt",
            count_records=lambda db, s: 0,
            migrate_records=lambda db, f, t: 0,
            scope_resolver=lambda record: getattr(record, "template_id", None),
            scope_label="Template",
        )
    )
    row = next(r for r in status_entities_payload() if r["entity_type"] == ENTITY)
    assert row["supports_scoped_graphs"] is True
    assert row["scope_label"] == "Template"


def test_entity_without_scope_resolver_always_resolves_the_default():
    entity = StatusEntity(
        entity_type=ENTITY,
        label="Pipeline probe",
        module="zzt",
        count_records=lambda db, s: 0,
        migrate_records=lambda db, f, t: 0,
    )
    assert entity.scope_for(object()) is None
