"""S0 gate - `complaint` as an entity on the ADOPTED status engine (ADR-0012).

The engine itself is a dependency here, not a deliverable: `tests/test_status_engine.py`
owns its contract. This file asserts only the complaint registration, and above all
that the registration is a **behavioural no-op**.

Why that matters more than usual: `complaints.status` is a bare
`VARCHAR(50) NOT NULL DEFAULT 'new'` holding the status **key** itself, with no FK and
no CHECK constraint, across 51 live rows -- and `complaint_fulfilment_service` branches
on `processed_by_cs` / `fulfilled` **by name**. So the vocabulary is pinned string by
string below: a rename that looks harmless in the seed would silently detach live rows
from the code that reads them.

Evidence for every edge and flag: `documentation/plans/after-sales/status-graph-evidence.md`.
"""
from __future__ import annotations

import pytest

from app.models.complaints import Complaint
from app.models.status import TRIGGER_MANUAL, Status
from app.schemas.complaints import ComplaintUpdate
from app.services.complaint_status_graph import (
    COMPLAINT_ENTITY_TYPE,
    COMPLAINT_ENTRY_POINT_KEYS,
    COMPLAINT_STATUS_KEYS,
    COMPLAINT_STATUS_SEEDS,
    COMPLAINT_TRANSITION_SEEDS,
    register_complaint_status_entity,
    seed_complaint_status_graph,
)
from app.services.complaints_service import ComplaintService
from app.services.error_handler import AppException
from app.services.status_service import (
    assert_status_deletable,
    assert_transition_allowed,
    assert_transition_allowed_by_key,
    initial_status,
    migrate_records,
    resolve_graph,
    status_entities_payload,
    validate_graph,
)
from app.status_engine import registry as status_registry

from ._pg_fixture import blank_session

# The twelve strings the live system spells. Written out rather than derived so a
# rename has to be made twice, on purpose, in two places.
LIVE_VOCABULARY = {
    "draft",
    "new",
    "submitted",
    "updated",
    "responded",
    "approved",
    "rejected",
    "processed_by_cs",
    "fulfilled",
    "closed",
    "voided",
    "resolved",
}


@pytest.fixture(autouse=True)
def _isolate_registry():
    """The status registry is process-global; snapshot and restore it."""
    saved = dict(status_registry._REGISTRY)
    yield
    status_registry._REGISTRY.clear()
    status_registry._REGISTRY.update(saved)


def _seeded(db):
    seed_complaint_status_graph(db)
    db.flush()
    return resolve_graph(db, COMPLAINT_ENTITY_TYPE, None)


def _complaint(db, status: str) -> Complaint:
    row = Complaint(status=status, customer_name="ZZT complaint probe")
    db.add(row)
    db.flush()
    return row


def _edge_keys(graph) -> set[tuple[str, str]]:
    by_id = {s.id: s.key for s in graph.statuses}
    return {(by_id[t.from_status_id], by_id[t.to_status_id]) for t in graph.transitions}


# --------------------------------------------------------------- vocabulary


def test_the_vocabulary_is_exactly_the_twelve_live_strings():
    """`resolved` is the one that gets dropped: it holds no rows, but it is a live
    comparison target in `_VOID_BLOCKED_STATUSES` and sits in both frontend pill
    maps. A graph missing a string leaves it spelled somewhere the registry claims
    to be the only place a status is spelled."""
    assert set(COMPLAINT_STATUS_KEYS) == LIVE_VOCABULARY
    assert len(COMPLAINT_STATUS_KEYS) == 12, "no duplicates"

    with blank_session() as db:
        graph = _seeded(db)
        assert {s.key for s in graph.statuses} == LIVE_VOCABULARY


def test_statuses_are_ordered_by_lifecycle_with_room_to_insert():
    """Declaration order is the lifecycle order, and `sort_order` is derived from it,
    so the graph editor and any picker read top to bottom the way the flow runs."""
    with blank_session() as db:
        graph = _seeded(db)
        assert [s.key for s in graph.statuses] == [s.key for s in COMPLAINT_STATUS_SEEDS]
        orders = [s.sort_order for s in graph.statuses]
        assert orders == sorted(orders) and len(set(orders)) == len(orders)
        assert all(o % 10 == 0 for o in orders), "gaps let an admin slot a status between rungs"


def test_resolved_is_kept_because_live_code_still_compares_against_it():
    assert "resolved" in ComplaintService._VOID_BLOCKED_STATUSES
    assert "resolved" in COMPLAINT_STATUS_KEYS


def test_labels_and_colours_mirror_the_frontend_presentation_map():
    """`lib/complaint-status.ts` is the presentation source of truth."""
    with blank_session() as db:
        graph = _seeded(db)
        assert graph.by_key("processed_by_cs").label == "Processed by CS"
        assert graph.by_key("new").label == "New"
        assert graph.by_key("fulfilled").label == "Fulfilled"
        # Every status carries a colour, so the graph editor never renders a
        # colourless node.
        assert all(s.color_hex for s in graph.statuses)


def test_voided_is_neutral_grey_not_red():
    """`lib/status-pill.ts:23-25` states it explicitly: voiding is administrative,
    not an error/rejection. The first port coloured it rose."""
    with blank_session() as db:
        graph = _seeded(db)
        voided = graph.by_key("voided")
        rejected = graph.by_key("rejected")
        assert voided.color_hex != rejected.color_hex
        assert voided.color_hex == graph.by_key("draft").color_hex, (
            "voided must share the neutral grey the muted states use"
        )


# ------------------------------------------------------------------- flags


def test_only_closed_and_voided_are_terminal():
    with blank_session() as db:
        graph = _seeded(db)
        assert {s.key for s in graph.statuses if s.is_terminal} == {"closed", "voided"}


def test_rejected_is_not_terminal_because_the_portal_resubmits_from_it():
    with blank_session() as db:
        graph = _seeded(db)
        assert graph.by_key("rejected").is_terminal is False
        assert assert_transition_allowed_by_key(
            db, COMPLAINT_ENTITY_TYPE, "rejected", "submitted"
        )


def test_resolved_is_deactivated_so_nothing_new_moves_into_it():
    """It is the pre-rename spelling of `processed_by_cs`: zero live rows, zero
    writers, one audit row from 2026-06-09. Deactivating is the engine's own way of
    saying "kept for existing records, closed to new ones"."""
    with blank_session() as db:
        graph = _seeded(db)
        assert graph.by_key("resolved").is_active is False
        with pytest.raises(AppException) as err:
            assert_transition_allowed_by_key(db, COMPLAINT_ENTITY_TYPE, "approved", "resolved")
        assert err.value.detail["code"] == "status_inactive"


def test_no_status_is_archived():
    """`is_archived` drops records out of the default list view. Nothing does that
    to complaints today, so setting it would change what the list shows."""
    with blank_session() as db:
        graph = _seeded(db)
        assert not [s.key for s in graph.statuses if s.is_archived]


def test_seeded_rows_are_system_rows():
    """Code branches on these keys and flags, so both are frozen by the admin API
    and the row cannot be deleted."""
    with blank_session() as db:
        graph = _seeded(db)
        assert all(s.is_system for s in graph.statuses)
        with pytest.raises(AppException) as err:
            assert_status_deletable(db, graph.by_key("approved"))
        assert err.value.detail["code"] == "status_is_system"


# ------------------------------------------------------------ entry points


def test_new_is_the_single_initial_status_and_matches_the_column_default():
    """Two genuine entry points exist (`draft` from the portal, `new` from the
    column default), but the engine allows exactly one `is_initial` -- see the test
    below. `new` gets it because that is where a bare create actually lands, so
    `initial_status()` and the column can never disagree."""
    with blank_session() as db:
        _seeded(db)
        assert initial_status(db, COMPLAINT_ENTITY_TYPE, None).key == "new"
    assert Complaint.__table__.c.status.default.arg == "new"


def test_new_is_also_the_default_pick_in_a_status_picker():
    with blank_session() as db:
        graph = _seeded(db)
        assert [s.key for s in graph.statuses if s.is_default] == ["new"]


def test_the_seeded_graph_passes_the_engines_structural_validation():
    """This is what forbids two `is_initial` rows: `validate_graph` runs after every
    admin write, so a graph with two starting states would 422 on the first edit an
    admin made to any complaint status."""
    with blank_session() as db:
        _seeded(db)
        validate_graph(db, COMPLAINT_ENTITY_TYPE, None)


def test_a_second_initial_status_would_brick_the_admin_ui():
    """Evidence for the choice above, encoded rather than asserted in prose."""
    with blank_session() as db:
        graph = _seeded(db)
        graph.by_key("draft").is_initial = True
        db.flush()
        with pytest.raises(AppException) as err:
            validate_graph(db, COMPLAINT_ENTITY_TYPE, None)
        assert err.value.detail["code"] == "status_graph_multiple_initial"


def test_both_entry_points_are_declared_and_have_no_incoming_edge():
    """`draft` is the portal entry (`portal_service.py:1064`); `new` is the
    in-system and n8n entry. Neither has a parent, and nothing in the codebase
    moves a complaint between them."""
    assert COMPLAINT_ENTRY_POINT_KEYS == ("draft", "new")
    with blank_session() as db:
        graph = _seeded(db)
        incoming = {to for _, to in _edge_keys(graph)}
        for key in COMPLAINT_ENTRY_POINT_KEYS:
            assert key not in incoming, f"'{key}' is an entry point; it must have no parent"


# ------------------------------------------------------------------- edges


def test_the_declared_edges_are_exactly_what_live_code_performs():
    expected = {
        ("draft", "submitted"),  # portal_service.py:874-879
        ("rejected", "submitted"),  # same, resubmission
        ("new", "responded"),  # complaints_service.py:1686 + :1881
        ("submitted", "responded"),
        ("updated", "responded"),
        ("responded", "approved"),  # :1974-1977 + :2045
        ("responded", "rejected"),
        ("approved", "processed_by_cs"),  # :2133-2134 + :2252
        ("approved", "closed"),
        ("processed_by_cs", "fulfilled"),  # complaint_fulfilment_service.py:313-316
        ("fulfilled", "processed_by_cs"),  # :317-322, auto-reopen
    } | {
        (key, "voided")  # complement of _VOID_BLOCKED_STATUSES (:2303) + :2339
        for key in ("draft", "new", "submitted", "updated", "responded", "approved", "fulfilled")
    }
    assert {(t.from_key, t.to_key) for t in COMPLAINT_TRANSITION_SEEDS} == expected
    with blank_session() as db:
        assert _edge_keys(_seeded(db)) == expected


def test_the_two_invented_edges_from_the_first_port_are_absent():
    """`draft -> new` existed only to force a single entry point; nothing performs
    it. `submitted -> updated` resurrects an auto-flip that was deliberately removed
    (`complaints_service.py:1707-1711`)."""
    declared = {(t.from_key, t.to_key) for t in COMPLAINT_TRANSITION_SEEDS}
    assert ("draft", "new") not in declared
    assert ("submitted", "updated") not in declared


def test_voidable_states_are_exactly_the_complement_of_the_live_blocked_tuple():
    """Pins both sides together: adding a status to `_VOID_BLOCKED_STATUSES` without
    dropping its void edge (or the reverse) fails here."""
    expected = set(COMPLAINT_STATUS_KEYS) - set(ComplaintService._VOID_BLOCKED_STATUSES)
    declared = {t.from_key for t in COMPLAINT_TRANSITION_SEEDS if t.to_key == "voided"}
    assert declared == expected
    assert "fulfilled" in declared, "fulfilled is absent from the blocked list, so it IS voidable"
    assert declared.isdisjoint({"rejected", "processed_by_cs", "resolved", "closed", "voided"})


def test_every_edge_is_manual_because_no_auto_edge_has_engine_conditions():
    """The two fulfilment edges are fired by `complaint_fulfilment_service` in
    Python, not by the engine from a `conditions_json` tree. `trigger_mode='auto'`
    would require conditions the rule engine cannot evaluate (CHECK-enforced), so
    they stay manual."""
    with blank_session() as db:
        graph = _seeded(db)
        assert all(t.trigger_mode == TRIGGER_MANUAL for t in graph.transitions)


# ----------------------------------------------------------- the key guard


def test_the_key_guard_allows_a_live_edge_and_names_the_action():
    with blank_session() as db:
        _seeded(db)
        edge = assert_transition_allowed_by_key(
            db, COMPLAINT_ENTITY_TYPE, "responded", "approved"
        )
        assert edge.label


def test_the_key_guard_rejects_an_illegal_jump():
    with blank_session() as db:
        _seeded(db)
        with pytest.raises(AppException) as err:
            assert_transition_allowed_by_key(db, COMPLAINT_ENTITY_TYPE, "draft", "approved")
        assert err.value.status_code == 422
        assert err.value.detail["code"] == "status_transition_not_allowed"


def test_the_key_guard_rejects_a_status_key_the_graph_does_not_know():
    with blank_session() as db:
        _seeded(db)
        for unknown in ("in_progress", "Approved"):
            with pytest.raises(AppException) as err:
                assert_transition_allowed_by_key(
                    db, COMPLAINT_ENTITY_TYPE, "responded", unknown
                )
            assert err.value.detail["code"] == "status_not_in_graph"


def test_the_key_guard_refuses_to_leave_a_terminal_status():
    with blank_session() as db:
        _seeded(db)
        with pytest.raises(AppException) as err:
            assert_transition_allowed_by_key(db, COMPLAINT_ENTITY_TYPE, "closed", "submitted")
        assert err.value.detail["code"] == "status_terminal"


def test_an_unrecognised_current_status_can_go_nowhere():
    """Fail closed: a row holding a string outside the graph has no outgoing edge."""
    with blank_session() as db:
        _seeded(db)
        with pytest.raises(AppException) as err:
            assert_transition_allowed_by_key(db, COMPLAINT_ENTITY_TYPE, "legacy_junk", "responded")
        assert err.value.detail["code"] == "status_transition_not_allowed"


def test_the_key_guard_reports_an_unknown_status_identically_to_the_id_guard():
    """The two raise sites are separate (the key adapter has no id to hand the id
    guard), so their wording is pinned together here."""
    with blank_session() as db:
        _seeded(db)
        with pytest.raises(AppException) as by_key:
            assert_transition_allowed_by_key(db, COMPLAINT_ENTITY_TYPE, "responded", "nope")
        with pytest.raises(AppException) as by_id:
            assert_transition_allowed(
                db, COMPLAINT_ENTITY_TYPE, None, "00000000-0000-0000-0000-0000000000ff"
            )
        assert by_key.value.detail == by_id.value.detail


# ------------------------------------------- registration: counts + migrate


def test_the_entity_is_registered_on_the_key_valued_column():
    register_complaint_status_entity()
    entity = status_registry.get_status_entity(COMPLAINT_ENTITY_TYPE)
    assert entity is not None
    assert entity.status_attr == "status", (
        "complaints hold the status KEY in a VARCHAR; the engine's default "
        "'status_id' would point at a column that does not exist"
    )
    assert entity.model is Complaint
    assert entity.scope_resolver is None, "complaints have one graph, never a fork"

    row = next(r for r in status_entities_payload() if r["entity_type"] == COMPLAINT_ENTITY_TYPE)
    assert row["label"] == "Complaint"
    assert row["supports_scoped_graphs"] is False


def test_records_are_counted_by_key_not_by_id():
    """The whole point of the adapter. Counting by id would return 0 for every
    status and let an admin delete one out from under 51 live rows."""
    with blank_session() as db:
        graph = _seeded(db)
        register_complaint_status_entity()
        entity = status_registry.get_status_entity(COMPLAINT_ENTITY_TYPE)

        for status_key in ("approved", "approved", "draft"):
            _complaint(db, status_key)

        assert entity.count_records(db, graph.by_key("approved").id) == 2
        assert entity.count_records(db, graph.by_key("draft").id) == 1
        assert entity.count_records(db, graph.by_key("closed").id) == 0


def test_counting_an_unknown_status_id_is_zero_not_an_error():
    with blank_session() as db:
        _seeded(db)
        register_complaint_status_entity()
        entity = status_registry.get_status_entity(COMPLAINT_ENTITY_TYPE)
        assert entity.count_records(db, "00000000-0000-0000-0000-0000000000ff") == 0


def test_delete_is_blocked_while_complaints_hold_the_status():
    with blank_session() as db:
        graph = _seeded(db)
        register_complaint_status_entity()
        _complaint(db, "approved")

        approved = graph.by_key("approved")
        # Take the system flag out of the way: this asserts the RECORD guard, which
        # is the one that needs the key-valued count to be right.
        approved.is_system = False
        db.flush()
        with pytest.raises(AppException) as err:
            assert_status_deletable(db, approved)
        assert err.value.detail["code"] == "status_in_use"
        assert "1 record still use 'Approved'" in err.value.detail["message"]


def test_migrate_writes_the_target_key_into_the_varchar_column():
    with blank_session() as db:
        graph = _seeded(db)
        register_complaint_status_entity()
        moved_rows = [_complaint(db, "approved") for _ in range(2)]
        staying = _complaint(db, "draft")

        moved = migrate_records(db, graph.by_key("approved"), graph.by_key("closed"))
        db.flush()

        assert moved == 2
        for row in moved_rows:
            db.refresh(row)
            assert row.status == "closed", "the column must hold the KEY, never an id"
        db.refresh(staying)
        assert staying.status == "draft"


def test_migrate_from_a_status_nobody_holds_moves_nothing():
    with blank_session() as db:
        graph = _seeded(db)
        register_complaint_status_entity()
        _complaint(db, "draft")
        assert migrate_records(db, graph.by_key("closed"), graph.by_key("voided")) == 0


# -------------------------------------------------------------- seed itself


def test_the_seed_corrects_drift_rather_than_skipping_it():
    """Idempotent here means "set where mismatch", not "insert where absent": an
    insert-if-absent seed can never repair a prior bad run."""
    with blank_session() as db:
        first = seed_complaint_status_graph(db)
        db.flush()
        assert first["statuses_created"] == 12
        assert first["transitions_created"] == len(COMPLAINT_TRANSITION_SEEDS)

        graph = resolve_graph(db, COMPLAINT_ENTITY_TYPE, None)
        drifted = graph.by_key("processed_by_cs")
        original_id = drifted.id
        drifted.label = "Resolved by CS"
        drifted.color_hex = "#FF0000"
        drifted.sort_order = 999
        edge = graph.transitions[0]
        edge.label = "Drifted action"
        db.flush()

        second = seed_complaint_status_graph(db)
        db.flush()
        assert second["statuses_created"] == 0, "a re-run must not duplicate rows"
        assert second["statuses_updated"] == 1
        assert second["transitions_updated"] == 1

        repaired = resolve_graph(db, COMPLAINT_ENTITY_TYPE, None).by_key("processed_by_cs")
        assert repaired.id == original_id, "correct in place, never re-create"
        assert repaired.label == "Processed by CS"
        assert repaired.color_hex != "#FF0000"
        assert repaired.sort_order != 999


def test_a_clean_re_run_reports_no_changes():
    with blank_session() as db:
        seed_complaint_status_graph(db)
        db.flush()
        again = seed_complaint_status_graph(db)
        db.flush()
        assert again == {
            "statuses_created": 0,
            "statuses_updated": 0,
            "transitions_created": 0,
            "transitions_updated": 0,
        }


def test_the_seed_writes_only_the_default_graph():
    with blank_session() as db:
        _seeded(db)
        rows = db.query(Status).filter(Status.entity_type == COMPLAINT_ENTITY_TYPE).all()
        assert rows and all(r.scope_id is None and r.tenant_id is None for r in rows)


def test_the_seed_leaves_the_complaints_table_untouched():
    """The no-op property. 51 live rows carry these strings; seeding a graph must
    not rewrite a single one of them."""
    with blank_session() as db:
        rows = [_complaint(db, key) for key in ("draft", "approved", "fulfilled")]
        _seeded(db)
        for row in rows:
            db.refresh(row)
        assert [r.status for r in rows] == ["draft", "approved", "fulfilled"]


# ---------------------------------------------------- the unguarded PUT hole


def _update(db, complaint, **payload):
    ComplaintService(db).update_complaint(str(complaint.id), ComplaintUpdate(**payload))


def test_update_complaint_rejects_an_out_of_graph_status_jump():
    """`PUT /complaints/{id}` applies `status` through a blind setattr loop, so
    before this the graph was advisory: any caller could jump any state to any
    other. Guarding the generic write path is what makes it enforcement."""
    with blank_session() as db:
        _seeded(db)
        complaint = _complaint(db, "draft")
        with pytest.raises(AppException) as err:
            _update(db, complaint, status="approved")
        assert err.value.status_code == 422
        assert err.value.detail["code"] == "status_transition_not_allowed"
        db.refresh(complaint)
        assert complaint.status == "draft"


def test_update_complaint_still_allows_an_in_graph_status_change():
    with blank_session() as db:
        _seeded(db)
        complaint = _complaint(db, "responded")
        _update(db, complaint, status="approved")
        db.refresh(complaint)
        assert complaint.status == "approved"


def test_update_complaint_accepts_a_write_that_repeats_the_current_status():
    """A caller echoing a whole record back sends the status it already holds. That
    is not a transition, and it leaves no audit diff -- so it is invisible in the
    historical evidence and must keep working."""
    with blank_session() as db:
        _seeded(db)
        complaint = _complaint(db, "processed_by_cs")
        _update(db, complaint, status="processed_by_cs", customer_name="ZZT echo")
        db.refresh(complaint)
        assert complaint.status == "processed_by_cs"


def test_update_complaint_is_unguarded_when_no_graph_is_seeded():
    """Fail OPEN on an unconfigured graph. Enforcement depends on seeded rows that
    arrive in a migration; failing closed would reject every status write in any
    environment where that migration has not run yet."""
    with blank_session() as db:
        complaint = _complaint(db, "draft")
        _update(db, complaint, status="approved")
        db.refresh(complaint)
        assert complaint.status == "approved"


def test_update_complaint_leaves_non_status_writes_alone():
    with blank_session() as db:
        _seeded(db)
        complaint = _complaint(db, "approved")
        _update(db, complaint, customer_name="ZZT renamed")
        db.refresh(complaint)
        assert complaint.status == "approved"
        assert complaint.customer_name == "ZZT renamed"


def test_update_and_reply_guards_the_same_hole():
    """`update_complaint_and_reply` has its OWN blind setattr loop
    (`complaints_service.py:1795`), reached from `POST /{id}/update-and-reply` with
    the same `ComplaintUpdate` schema. Guarding only the PUT would leave the hole
    open one route over."""
    with blank_session() as db:
        _seeded(db)
        complaint = _complaint(db, "draft")
        with pytest.raises(AppException) as err:
            ComplaintService(db).update_complaint_and_reply(
                str(complaint.id),
                ComplaintUpdate(status="approved", technical_team_response="ZZT reply"),
                respond_user_id="zzt-user",
            )
        assert err.value.detail["code"] == "status_transition_not_allowed"
        db.refresh(complaint)
        assert complaint.status == "draft"
