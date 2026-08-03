"""The Edition's status graph and its one-open-per-page rule (S2.5.1).

The graph is SEEDED CONFIG, so these tests run the migration's own seeding
function against a blank schema rather than asserting rows in the shared dev
database. That database carries graphs applied from other worktrees, so an
assertion about a live row would pass here and fail on a freshly migrated CI
database - which is exactly the failure the seed-data rule exists to prevent.

What is being pinned is the shape a human decided on, not the engine: the engine
has its own tests. Specifically that ``done`` is a dead end, that ``draft`` is
the only way in, and that a page cannot carry two open Editions.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.dealer_kit import Edition, Page
from app.models.status import Status, StatusTransition
from app.services import status_service
from app.services.error_handler import AppException
from tests._pg_fixture import blank_session, unique_code

ENTITY = "dealer_kit_edition"

_MIG_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "318_dealer_kit_edition.py"
)
_spec = importlib.util.spec_from_file_location("mig_318_edition", _MIG_PATH)
mig318 = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(mig318)


@pytest.fixture
def db():
    with blank_session() as session:
        # The migration's OWN seeding code, against a blank schema. Testing a
        # reimplementation of it here would pass while the migration was broken.
        mig318._seed_graph(session.connection())
        session.flush()
        yield session


def _graph(db):
    return status_service.resolve_graph(db, ENTITY, None)


def _status(db, key: str) -> Status:
    return (
        db.query(Status)
        .filter(Status.entity_type == ENTITY, Status.key == key)
        .one()
    )


def _page(db) -> Page:
    page = Page(
        id=str(uuid.uuid4()),
        name=unique_code("ZZT Edition Page"),
        slug=unique_code("zzt-ed").lower(),
    )
    db.add(page)
    db.flush()
    return page


def _edition(db, page: Page, key: str = "draft", **kwargs) -> Edition:
    status = _status(db, key)
    edition = Edition(
        id=str(uuid.uuid4()),
        page_id=page.id,
        name=unique_code("ZZT Edition"),
        status_id=status.id,
        status_key=status.key,
        **kwargs,
    )
    db.add(edition)
    db.flush()
    return edition


class TestTheGraph:
    def test_the_five_states_are_seeded_in_reading_order(self, db) -> None:
        graph = _graph(db)

        assert [s.key for s in sorted(graph.statuses, key=lambda s: s.sort_order)] == [
            "draft",
            "pending_approval",
            "approved",
            "rejected",
            "done",
        ]

    def test_every_seeded_status_is_a_system_row(self, db) -> None:
        """`edition_service._status_by_key` reads all five BY KEY.

        `update_status` freezes the key only on system rows, so without the flag
        an admin renaming "draft" in the status UI bricks the workflow - and the
        500 it produces says the graph "has not been seeded", which sends
        whoever hits it to the migration instead of to the rename they just did.
        This is the first seeded graph in the system, so it sets the convention.
        """
        assert [s.key for s in _graph(db).statuses if not s.is_system] == []

    def test_draft_is_the_only_way_in(self, db) -> None:
        """The engine asserts one initial per graph; this asserts WHICH one.

        An Edition that started at `approved` would be a catalogue nobody signed
        off, and the seeding is the only thing deciding that.
        """
        initials = [s.key for s in _graph(db).statuses if s.is_initial]

        assert initials == ["draft"]

    def test_done_is_terminal_and_has_no_way_out(self, db) -> None:
        """AC-L8 (done -> draft) was withdrawn on 2026-08-03.

        Revising a live catalogue duplicates the Edition into a new one at
        `draft` (AC-L9); the finished record stays finished. Asserted as BOTH
        the flag and the absence of edges, because the flag alone is a promise
        and the edge list is the thing that would actually let it happen.
        """
        graph = _graph(db)
        done = graph.by_key("done")

        assert done.is_terminal is True
        assert graph.outgoing(done.id) == []

    def test_exactly_the_edges_that_were_decided(self, db) -> None:
        graph = _graph(db)
        by_id = {s.id: s.key for s in graph.statuses}
        edges = {(by_id[t.from_status_id], by_id[t.to_status_id]) for t in graph.transitions}

        assert edges == {
            ("draft", "pending_approval"),
            ("pending_approval", "approved"),
            ("pending_approval", "rejected"),
            ("rejected", "draft"),
            ("approved", "done"),
            ("approved", "pending_approval"),
        }

    def test_every_edge_is_manual(self, db) -> None:
        """An auto edge fires on a condition. Approval is a human act by
        definition, so an auto edge in here would approve a catalogue on a
        timer."""
        assert {t.trigger_mode for t in _graph(db).transitions} == {"manual"}

    def test_approval_cannot_be_skipped(self, db) -> None:
        """The one transition nobody may have: draft straight to approved."""
        db_graph = _graph(db)
        draft = db_graph.by_key("draft")
        approved = db_graph.by_key("approved")

        with pytest.raises(AppException):
            status_service.assert_transition_allowed(
                db, ENTITY, from_status_id=draft.id, to_status_id=approved.id
            )

    def test_a_rejected_edition_goes_back_to_draft_and_not_onward(self, db) -> None:
        """`rejected` is a STATE, not an event: the reason stays on screen until
        the Designer picks the work up, and picking it up is an edge they take.
        So rejected reaches draft and nothing else."""
        graph = _graph(db)
        rejected = graph.by_key("rejected")
        by_id = {s.id: s.key for s in graph.statuses}

        assert [by_id[t.to_status_id] for t in graph.outgoing(rejected.id)] == ["draft"]

    def test_seeding_twice_changes_nothing(self, db) -> None:
        """The dev database is shared across worktrees and this migration runs
        against schemas that already hold the graph."""
        before = db.query(Status).filter(Status.entity_type == ENTITY).count()
        before_edges = (
            db.query(StatusTransition)
            .filter(StatusTransition.entity_type == ENTITY)
            .count()
        )

        mig318._seed_graph(db.connection())
        db.flush()

        assert db.query(Status).filter(Status.entity_type == ENTITY).count() == before
        assert (
            db.query(StatusTransition)
            .filter(StatusTransition.entity_type == ENTITY)
            .count()
            == before_edges
        )


class TestOneOpenEditionPerPage:
    """Two people revising one catalogue against each other has no story: the
    one published second would silently discard the first. Enforced in the
    DATABASE, because a service check races itself."""

    @pytest.mark.parametrize("second_key", ["draft", "pending_approval", "approved", "rejected"])
    def test_a_page_cannot_carry_two_open_editions(self, db, second_key) -> None:
        page = _page(db)
        _edition(db, page, "draft")

        with pytest.raises(IntegrityError):
            _edition(db, page, second_key)

    def test_a_finished_edition_frees_the_page_for_the_next_one(self, db) -> None:
        """AC-L9's mechanism. Without this the index would make a catalogue
        publishable exactly once."""
        page = _page(db)
        first = _edition(db, page, "done")

        second = _edition(db, page, "draft", previous_edition_id=first.id)

        assert second.id != first.id
        assert second.previous_edition_id == first.id

    def test_two_pages_each_get_their_own_open_edition(self, db) -> None:
        """The index is per PAGE. Scoping it wider would let one catalogue in
        revision block every other catalogue in the company."""
        first, second = _page(db), _page(db)

        _edition(db, first, "draft")
        _edition(db, second, "draft")

        assert db.query(Edition).count() == 2


class TestTheRegisteredEntity:
    """The Edition is the first entity in this system to ride the engine, so
    the registration itself is worth pinning."""

    def test_the_entity_is_registered_with_its_model(self) -> None:
        from app.status_engine.registry import get_status_entity

        entity = get_status_entity(ENTITY)

        assert entity is not None
        assert entity.model is Edition
        assert entity.module == "dealer_kit"
        # No fork: a per-page graph would let one catalogue invent its own
        # approval rules.
        assert entity.scope_resolver is None

    def test_it_reports_editions_holding_a_status(self, db) -> None:
        """Backs block-delete-if-referenced. A status still worn by a live
        Edition must not be deletable out from under it."""
        from app.status_engine.registry import get_status_entity

        entity = get_status_entity(ENTITY)
        draft = _status(db, "draft")
        _edition(db, _page(db), "draft")

        assert entity.count_records(db, draft.id) == 1

    def test_migrating_records_carries_the_denormalised_key(self, db) -> None:
        """status_id and status_key are two copies of one fact, and the partial
        unique index reads the KEY. Moving the id alone leaves a row that is
        done by foreign key and draft by index, and a second open Edition could
        then be created against the same page.
        """
        from app.status_engine.registry import get_status_entity

        entity = get_status_entity(ENTITY)
        draft, done = _status(db, "draft"), _status(db, "done")
        edition = _edition(db, _page(db), "draft")

        moved = entity.migrate_records(db, draft.id, done.id)
        db.expire_all()

        assert moved == 1
        refreshed = db.query(Edition).filter(Edition.id == edition.id).one()
        assert refreshed.status_id == done.id
        assert refreshed.status_key == "done"
