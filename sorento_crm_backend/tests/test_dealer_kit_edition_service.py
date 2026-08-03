"""Edition transitions (S2.5.2).

What is pinned here is the WORKFLOW, not the engine. The engine's own tests
cover whether an edge is legal; these cover what each move records, what it
clears, and the one thing that must never happen - a catalogue reading `done`
while readers still see the old one, or an approval surviving an edit.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest

from app.models.dealer_kit import Edition, Page, PageLabel, PageVersion
from app.services.dealer_kit import edition_service, page_service
from app.services.error_handler import AppException
from tests._pg_fixture import blank_session, unique_code

_MIG_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "318_dealer_kit_edition.py"
)
_spec = importlib.util.spec_from_file_location("mig_318_edition_svc", _MIG_PATH)
mig318 = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(mig318)

USER = str(uuid.uuid4())
APPROVER = str(uuid.uuid4())


@pytest.fixture
def db():
    with blank_session() as session:
        mig318._seed_graph(session.connection())
        session.flush()
        yield session


def _page(db) -> Page:
    page = Page(
        id=str(uuid.uuid4()),
        name=unique_code("ZZT Edition Page"),
        slug=unique_code("zzt-ed").lower(),
    )
    db.add(page)
    db.flush()
    return page


def _version(db, page: Page, number: int = 1) -> PageVersion:
    version = PageVersion(
        id=str(uuid.uuid4()),
        page_id=page.id,
        version=number,
        doc={"sections": []},
        created_by=USER,
    )
    db.add(version)
    db.flush()
    return version


def _started(db, page: Page) -> Edition:
    return edition_service.create_edition(
        db, page_id=page.id, name=unique_code("ZZT Edition"), user_id=USER
    )


def _through_to_approved(db, page: Page) -> Edition:
    edition = _started(db, page)
    edition_service.submit(db, edition.id, user_id=USER)
    return edition_service.approve(db, edition.id, user_id=APPROVER)


class TestStarting:
    def test_an_edition_starts_at_draft(self, db) -> None:
        edition = _started(db, _page(db))

        assert edition.status_key == "draft"
        assert edition.created_by == USER

    def test_a_second_open_edition_is_refused_in_words(self, db) -> None:
        """A 409 rather than an IntegrityError reaching the client as a 500.

        The message has to say what to do about it: "already has one" with no
        next step leaves somebody clicking the button again.
        """
        page = _page(db)
        _started(db, page)

        with pytest.raises(AppException) as caught:
            _started(db, page)

        assert caught.value.status_code == 409
        assert "already has an Edition in progress" in caught.value.detail["message"]

    def test_another_companys_page_is_a_404_before_anything_is_written(self, db) -> None:
        with pytest.raises(AppException) as caught:
            edition_service.create_edition(
                db, page_id=str(uuid.uuid4()), name="ZZT", user_id=USER
            )

        assert caught.value.status_code == 404
        assert db.query(Edition).count() == 0


class TestTheHappyPath:
    def test_submitting_stamps_who_and_when(self, db) -> None:
        edition = _started(db, _page(db))

        edition_service.submit(db, edition.id, user_id=USER)

        assert edition.status_key == "pending_approval"
        assert edition.submitted_by == USER
        assert edition.submitted_at is not None

    def test_approving_records_the_version_that_was_actually_read(self, db) -> None:
        """The Approver signs off a DOCUMENT, not a page id.

        Stamping the page's newest version is what makes a later edit provably
        a different document.
        """
        page = _page(db)
        _version(db, page, 1)
        second = _version(db, page, 2)

        edition = _through_to_approved(db, page)

        assert edition.status_key == "approved"
        assert edition.approved_by == APPROVER
        assert edition.approved_version_id == second.id

    def test_publishing_moves_the_published_label_and_finishes(self, db) -> None:
        """AC-L7: done is the only transition that publishes."""
        page = _page(db)
        version = _version(db, page, 1)
        edition = _through_to_approved(db, page)

        edition_service.publish(db, edition.id, user_id=APPROVER)

        assert edition.status_key == "done"
        assert edition.done_version_id == version.id
        label = (
            db.query(PageLabel)
            .filter(PageLabel.page_id == page.id, PageLabel.label == "published")
            .one()
        )
        assert label.version_id == version.id

    def test_approving_alone_publishes_nothing(self, db) -> None:
        """The failure this ordering exists to prevent: a catalogue going live
        the moment somebody says it reads well, rather than when they choose."""
        page = _page(db)
        _version(db, page, 1)

        _through_to_approved(db, page)

        assert (
            db.query(PageLabel)
            .filter(PageLabel.page_id == page.id, PageLabel.label == "published")
            .count()
            == 0
        )


class TestRejection:
    def test_rejecting_keeps_the_reason_the_designer_will_read(self, db) -> None:
        page = _page(db)
        edition = _started(db, page)
        edition_service.submit(db, edition.id, user_id=USER)

        edition_service.reject(
            db, edition.id, reason="  The bathtub page prices are last season.  ",
            user_id=APPROVER,
        )

        assert edition.status_key == "rejected"
        # Trimmed: leading whitespace from a textarea is not part of the reason.
        assert edition.rejection_reason == "The bathtub page prices are last season."

    @pytest.mark.parametrize("blank", ["", "   ", None])
    def test_a_rejection_with_no_reason_is_refused(self, db, blank) -> None:
        """The last place that can refuse one. A rejection with no reason is a
        rejection nobody can act on."""
        page = _page(db)
        edition = _started(db, page)
        edition_service.submit(db, edition.id, user_id=USER)

        with pytest.raises(AppException) as caught:
            edition_service.reject(db, edition.id, reason=blank, user_id=APPROVER)

        assert caught.value.status_code == 422
        assert edition.status_key == "pending_approval"

    def test_rejecting_clears_a_previous_approval(self, db) -> None:
        """An approved_by left behind on a rejected Edition reads as approved."""
        page = _page(db)
        _version(db, page, 1)
        edition = _through_to_approved(db, page)
        edition_service.submit(db, edition.id, user_id=USER)

        edition_service.reject(db, edition.id, reason="Changed my mind", user_id=APPROVER)

        assert edition.approved_by is None
        assert edition.approved_at is None

    def test_reopening_keeps_the_reason_on_screen(self, db) -> None:
        """A Designer editing rejected work should still see what they were
        told. The reason is cleared on the next SUBMISSION, not on pickup."""
        page = _page(db)
        edition = _started(db, page)
        edition_service.submit(db, edition.id, user_id=USER)
        edition_service.reject(db, edition.id, reason="Prices wrong", user_id=APPROVER)

        edition_service.reopen(db, edition.id, user_id=USER)

        assert edition.status_key == "draft"
        assert edition.rejection_reason == "Prices wrong"

    def test_resubmitting_clears_it(self, db) -> None:
        """Otherwise last round's reason sits beside a fresh submission and
        reads as a fresh rejection."""
        page = _page(db)
        edition = _started(db, page)
        edition_service.submit(db, edition.id, user_id=USER)
        edition_service.reject(db, edition.id, reason="Prices wrong", user_id=APPROVER)
        edition_service.reopen(db, edition.id, user_id=USER)

        edition_service.submit(db, edition.id, user_id=USER)

        assert edition.rejection_reason is None


class TestTheGraphIsTheAuthority:
    def test_approval_cannot_be_skipped(self, db) -> None:
        edition = _started(db, _page(db))

        with pytest.raises(AppException):
            edition_service.approve(db, edition.id, user_id=APPROVER)

        assert edition.status_key == "draft"

    def test_a_draft_cannot_be_published(self, db) -> None:
        page = _page(db)
        _version(db, page, 1)
        edition = _started(db, page)

        with pytest.raises(AppException):
            edition_service.publish(db, edition.id, user_id=APPROVER)

        assert edition.status_key == "draft"
        assert (
            db.query(PageLabel).filter(PageLabel.page_id == page.id).count() == 0
        ), "a refused publish must not have moved the label"

    def test_a_finished_edition_cannot_be_reopened(self, db) -> None:
        """done is terminal. AC-L8 was withdrawn: revising means a NEW Edition."""
        page = _page(db)
        _version(db, page, 1)
        edition = _through_to_approved(db, page)
        edition_service.publish(db, edition.id, user_id=APPROVER)

        for move in (edition_service.reopen, edition_service.submit):
            with pytest.raises(AppException):
                move(db, edition.id, user_id=USER)

        assert edition.status_key == "done"

    def test_a_refused_move_records_nothing(self, db) -> None:
        """`apply` runs only after the move is known to be legal, so a rejected
        transition cannot leave an approved_by on a record that never moved."""
        edition = _started(db, _page(db))

        with pytest.raises(AppException):
            edition_service.approve(db, edition.id, user_id=APPROVER)

        assert edition.approved_by is None
        assert edition.approved_at is None
        assert edition.approved_version_id is None


class TestFinishingFreesThePage:
    def test_the_next_edition_can_start_once_this_one_is_done(self, db) -> None:
        """AC-L9's mechanism, and the reason done had to free the index slot."""
        page = _page(db)
        _version(db, page, 1)
        first = _through_to_approved(db, page)
        edition_service.publish(db, first.id, user_id=APPROVER)

        second = edition_service.create_edition(
            db,
            page_id=page.id,
            name=unique_code("ZZT Next"),
            previous_edition_id=first.id,
            user_id=USER,
        )

        assert second.status_key == "draft"
        assert second.previous_edition_id == first.id

    def test_publishing_with_nothing_saved_is_refused_in_words(self, db) -> None:
        page = _page(db)
        edition = _through_to_approved(db, page)

        with pytest.raises(AppException) as caught:
            edition_service.publish(db, edition.id, user_id=APPROVER)

        assert caught.value.status_code == 422
        assert "no saved version" in caught.value.detail["message"]
        assert edition.status_key == "approved"
