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
from sqlalchemy import update

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
        page = _page(db)
        _version(db, page, 1)
        edition = _started(db, page)

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
        _version(db, page, 1)
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
        _version(db, page, 1)
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
        _version(db, page, 1)
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
        _version(db, page, 1)
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
        """Reached here by deleting the version AFTER approval, because submit
        now refuses first. The guard stays as the last line of defence: it is
        what stops the published label being moved to nothing."""
        page = _page(db)
        version = _version(db, page, 1)
        edition = _through_to_approved(db, page)
        db.delete(version)
        db.flush()

        with pytest.raises(AppException) as caught:
            edition_service.publish(db, edition.id, user_id=APPROVER)

        assert caught.value.status_code == 422
        assert "no saved version" in caught.value.detail["message"]
        assert edition.status_key == "approved"


class TestTheApprovalCannotBeSidesteppedByTheLabel:
    """`PUT /pages/{id}/labels/published` moves the label at any version and
    knew nothing about Editions, so the whole workflow was advisory.

    It is not a back door somebody has to look for: the page editor renders
    **Publish** as a header button wired straight to it, and migration 309 hands
    `page.publish` to marketing_manager and marketing_executive WITHOUT
    `edition.approve` - the exact population the split exists to constrain held
    the bypass.

    The rule is narrow on purpose. Publishing without an Edition is how S1 to S3
    shipped and stays legal; what is refused is sidestepping an approval cycle
    that is ALREADY OPEN on that page. Rollback to something an Edition did
    publish stays legal too, because that is returning to approved content, not
    shipping unapproved content.
    """

    def test_a_direct_publish_is_refused_while_an_edition_is_open(self, db) -> None:
        page = _page(db)
        _version(db, page, 1)
        second = _version(db, page, 2)
        _started(db, page)  # draft - not approved, not even submitted

        with pytest.raises(AppException) as caught:
            page_service.move_label(
                db, page.id, page_service.PUBLISHED, version_id=second.id, user_id=USER
            )

        assert caught.value.status_code == 422
        assert "edition" in caught.value.detail["message"].lower()
        assert db.query(PageLabel).filter(PageLabel.page_id == page.id).count() == 0

    def test_the_refusal_speaks_the_state_it_is_actually_in(self, db) -> None:
        """One message for all four states told the owner of an APPROVED
        Edition to publish it "so it goes past an approver" - which it already
        had - and otherwise to reject work somebody had just signed off.

        A refusal that misdescribes the situation reads as a refusal that is
        wrong, which is how this got reported.
        """
        page = _page(db)
        _version(db, page, 1)
        second = _version(db, page, 2)
        edition = _through_to_approved(db, page)
        assert edition.status_key == "approved"

        with pytest.raises(AppException) as caught:
            page_service.move_label(
                db, page.id, page_service.PUBLISHED, version_id=second.id, user_id=USER
            )

        message = caught.value.detail["message"]
        assert edition.name in message
        assert "approved and ready to publish" in message
        assert "goes past an approver" not in message
        assert "reject" not in message.lower()

    def test_a_draft_is_told_to_send_it_for_approval(self, db) -> None:
        page = _page(db)
        _version(db, page, 1)
        second = _version(db, page, 2)
        _started(db, page)

        with pytest.raises(AppException) as caught:
            page_service.move_label(
                db, page.id, page_service.PUBLISHED, version_id=second.id, user_id=USER
            )

        assert "still a draft" in caught.value.detail["message"]

    def test_a_page_with_no_edition_publishes_exactly_as_before(self, db) -> None:
        # S1 to S3 behaviour. Editions are not mandatory.
        page = _page(db)
        version = _version(db, page, 1)

        row = page_service.move_label(
            db, page.id, page_service.PUBLISHED, version_id=version.id, user_id=USER
        )

        assert row.version_id == version.id

    def test_the_edition_route_still_publishes_while_its_own_edition_is_open(
        self, db
    ) -> None:
        # The guard must not lock out the one path that is allowed to publish.
        page = _page(db)
        version = _version(db, page, 1)
        edition = _through_to_approved(db, page)

        edition_service.publish(db, edition.id, user_id=APPROVER)

        assert edition.status_key == "done"
        label = (
            db.query(PageLabel)
            .filter(PageLabel.page_id == page.id, PageLabel.label == "published")
            .one()
        )
        assert label.version_id == version.id

    def test_rolling_back_to_previously_published_content_stays_legal(self, db) -> None:
        # An emergency rollback during an open cycle is returning to a version
        # an Approver already signed off, so it is not the failure being guarded.
        page = _page(db)
        first = _version(db, page, 1)
        done = _through_to_approved(db, page)
        edition_service.publish(db, done.id, user_id=APPROVER)

        _version(db, page, 2)
        _started(db, page)  # a fresh cycle is now open

        row = page_service.move_label(
            db, page.id, page_service.PUBLISHED, version_id=first.id, user_id=USER
        )

        assert row.version_id == first.id

    def test_a_finished_edition_does_not_lock_the_page_forever(self, db) -> None:
        page = _page(db)
        _version(db, page, 1)
        edition = _through_to_approved(db, page)
        edition_service.publish(db, edition.id, user_id=APPROVER)

        third = _version(db, page, 3)
        row = page_service.move_label(
            db, page.id, page_service.PUBLISHED, version_id=third.id, user_id=USER
        )

        assert row.version_id == third.id

    def test_the_staging_label_is_not_restricted(self, db) -> None:
        # Only `published` is what readers see. Staging is for review.
        page = _page(db)
        version = _version(db, page, 1)
        _started(db, page)

        row = page_service.move_label(
            db, page.id, page_service.STAGING, version_id=version.id, user_id=USER
        )

        assert row.version_id == version.id


class TestATransitionChecksTheCommittedState:
    """`_move` used to check legality against whatever the session had cached
    and then UPDATE unconditionally, with no `WHERE status_key = <from>`.

    Two concurrent transitions both passed against the same pre-state and the
    second commit won. The reachable one is Publish racing Save: the Edition
    lands on `pending_approval` while holding a `done_version_id` and a moved
    published label, having taken `done -> pending_approval` - an edge the graph
    does not have and `test_a_finished_edition_cannot_be_reopened` asserts is
    impossible.

    Simulated here by moving the row underneath the session, which is what the
    losing transaction sees once the winner commits.
    """

    def test_a_stale_session_does_not_get_a_move_the_graph_forbids(self, db) -> None:
        page = _page(db)
        _version(db, page, 1)
        edition = _through_to_approved(db, page)
        assert edition.status_key == "approved"

        # The winning transaction, applied straight to the row.
        #
        # A Core UPDATE through the mapped class, NOT hand-written SQL naming
        # `dealer_kit.edition`: blank_session runs in a scratch schema, so a
        # hardcoded schema name does not resolve to this test's table at all -
        # it silently matches nothing and the test passes while proving nothing.
        # synchronize_session=False leaves the in-memory copy stale, which is
        # the whole point; assigning to the object instead would mark it dirty
        # and autoflush would push that value out ahead of the re-read.
        db.execute(
            update(Edition)
            .where(Edition.id == edition.id)
            .values(status_id=_status_id(db, "done"), status_key="done")
            .execution_options(synchronize_session=False)
        )

        # The loser still believes it holds an approved Edition.
        assert edition.status_key == "approved"

        with pytest.raises(AppException):
            edition_service.submit(db, edition.id, user_id=USER)

        db.refresh(edition)
        assert edition.status_key == "done", "a terminal Edition was reopened"


def _status_id(db, key: str) -> str:
    from app.models.status import Status

    return (
        db.query(Status.id)
        .filter(Status.entity_type == "dealer_kit_edition", Status.key == key)
        .scalar()
    )


class TestSubmitClearsAnApprovalToo:
    """`submit` serves TWO edges - draft -> pending_approval and
    approved -> pending_approval - and only cleared the rejection reason.

    So an Edition sent back round after approval kept approved_by / approved_at
    / approved_version_id, and the detail page renders "Approved: <date>" beside
    a "Pending approval" pill. Exactly what send_back_on_edit._void was written
    to prevent, one function away in the same file.
    """

    def test_resubmitting_an_approved_edition_voids_the_approval(self, db) -> None:
        page = _page(db)
        _version(db, page, 1)
        edition = _through_to_approved(db, page)

        edition_service.submit(db, edition.id, user_id=USER)

        assert edition.status_key == "pending_approval"
        assert edition.approved_by is None
        assert edition.approved_at is None
        assert edition.approved_version_id is None

    def test_rejecting_clears_the_approved_version_too(self, db) -> None:
        # reject cleared approved_by and approved_at but left the version id,
        # where _void clears all three.
        page = _page(db)
        _version(db, page, 1)
        edition = _through_to_approved(db, page)
        edition_service.submit(db, edition.id, user_id=USER)

        edition_service.reject(db, edition.id, reason="No", user_id=APPROVER)

        assert edition.approved_version_id is None


class TestAnApprovalDoesNotSurviveAnEdit:
    """The graph has carried an ``approved -> pending_approval`` edge since
    migration 318, whose docstring says "ANY edit to an approved Edition sends
    it back". Nothing performed that transition.

    So: an Approver approves version 3, the Designer saves version 4, and
    publish shipped version 4 - a document nobody had read. The row even
    recorded the discrepancy (``approved_version_id`` 3, ``done_version_id`` 4)
    and no screen looked at it.

    Two halves. Saving sends the Edition back, which is the part that puts it in
    front of the Approver again. Publish refuses a version that was not the one
    approved, which is the part that holds even if the send-back never ran.
    """

    def test_saving_the_page_sends_an_approved_edition_back(self, db) -> None:
        page = _page(db)
        _version(db, page, 1)
        edition = _through_to_approved(db, page)

        page_service.save_version(
            db, page.id, doc={"sections": []}, commit_message=None, user_id=USER
        )

        assert edition.status_key == "pending_approval"

    def test_the_void_approval_is_cleared_rather_than_left_lying(self, db) -> None:
        page = _page(db)
        _version(db, page, 1)
        edition = _through_to_approved(db, page)

        page_service.save_version(
            db, page.id, doc={"sections": []}, commit_message=None, user_id=USER
        )

        assert edition.approved_by is None
        assert edition.approved_at is None
        assert edition.approved_version_id is None

    def test_a_draft_edition_is_left_alone(self, db) -> None:
        # Saving while still drafting is the normal thing to do. Only an
        # approval is invalidated by an edit.
        page = _page(db)
        _version(db, page, 1)
        edition = _started(db, page)

        page_service.save_version(
            db, page.id, doc={"sections": []}, commit_message=None, user_id=USER
        )

        assert edition.status_key == "draft"

    def test_a_page_with_no_edition_saves_normally(self, db) -> None:
        page = _page(db)

        version = page_service.save_version(
            db, page.id, doc={"sections": []}, commit_message=None, user_id=USER
        )

        assert version.version == 1

    def test_publishing_a_version_nobody_approved_is_refused(self, db) -> None:
        """The backstop. Reached by approving, then writing a newer version
        without going through save_version's send-back."""
        page = _page(db)
        _version(db, page, 1)
        edition = _through_to_approved(db, page)
        _version(db, page, 2)

        with pytest.raises(AppException) as caught:
            edition_service.publish(db, edition.id, user_id=APPROVER)

        assert caught.value.status_code == 422
        assert "approved" in caught.value.detail["message"].lower()
        assert edition.status_key == "approved"
        assert (
            db.query(PageLabel).filter(PageLabel.page_id == page.id).count() == 0
        ), "a refused publish must not have moved the label"

    def test_publishing_the_approved_version_still_works(self, db) -> None:
        page = _page(db)
        version = _version(db, page, 1)
        edition = _through_to_approved(db, page)

        edition_service.publish(db, edition.id, user_id=APPROVER)

        assert edition.status_key == "done"
        assert edition.done_version_id == version.id


class TestACatalogueWithNothingSavedNeverReachesAnApprover:
    """The walkthrough that found this: a brand new page, an Edition started on
    it, sent for approval, approved, and only THEN refused at publish because
    the page had never been saved.

    Three things were wrong with failing that late. The Approver had already
    spent their attention on it. ``approved_version_id`` was stamped NULL, so
    the record claimed somebody had read a document that did not exist. And the
    person who could fix it was not the person holding the error - worse, the
    editor's Save button is disabled on an untouched page, so the obvious
    remedy looked unavailable.

    The refusal belongs at submit, where the Designer is still holding it.
    """

    def test_sending_a_catalogue_with_nothing_saved_is_refused(self, db) -> None:
        edition = _started(db, _page(db))

        with pytest.raises(AppException) as caught:
            edition_service.submit(db, edition.id, user_id=USER)

        assert caught.value.status_code == 422
        assert edition.status_key == "draft"

    def test_the_refusal_says_what_to_do_about_it(self, db) -> None:
        edition = _started(db, _page(db))

        with pytest.raises(AppException) as caught:
            edition_service.submit(db, edition.id, user_id=USER)

        message = caught.value.detail["message"]
        assert "no saved version" in message
        assert "save" in message.lower()

    def test_it_records_nothing_on_the_way_out(self, db) -> None:
        edition = _started(db, _page(db))

        with pytest.raises(AppException):
            edition_service.submit(db, edition.id, user_id=USER)

        assert edition.submitted_at is None
        assert edition.submitted_by is None

    def test_saving_the_page_is_all_it_takes(self, db) -> None:
        page = _page(db)
        edition = _started(db, page)
        _version(db, page, 1)

        edition_service.submit(db, edition.id, user_id=USER)

        assert edition.status_key == "pending_approval"

    def test_an_approved_edition_always_names_the_version_that_was_read(
        self, db
    ) -> None:
        # The integrity half of the same defect: with the submit guard in
        # place there is no route to an approved Edition whose
        # approved_version_id is NULL.
        page = _page(db)
        version = _version(db, page, 1)

        edition = _through_to_approved(db, page)

        assert edition.approved_version_id == version.id
