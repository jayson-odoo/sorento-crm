"""r9 S2/D4-D6: pinned change requests (AC-S2-3, AC-S2-5, AC-S2-7, AC-S2-8).

A salesperson does not describe a change, they point at it. Send posts every
pin in ONE call, which creates ``price_tag_review_comments`` rows and moves the
request to ``changes_requested``; marketing ticks each one Done from the CRM.

Three things these tests pin down that a route can get wrong quietly:

* the pins land as ROWS. The old behaviour appended
  ``"\\n[Changes requested]: ..."`` to ``price_tag_requests.notes``, which is
  the salesperson's own notes field - so a change request overwrote the record
  it was commenting on. ``notes`` must come out of a Send untouched.
* ``round`` is STORED, not derived at read (D4). It is the number of
  ``Marked proof ready`` snapshots at SEND time, so a comment keeps saying
  which proof it was about after two more proofs have been sent.
* Done is a PROCESSOR's action. The portal contact who wrote the comment must
  not be able to tick their own change request off.

Red before the coder starts: the table, the service and all four routes are
absent, so the imports fail and the routes 404/422.
"""
from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from tests import _ptag_r9_seed as seed
from tests._pg_fixture import blank_session

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1", reason="SKIP_LIVE_DB_TESTS=1"
)

_PORTAL = "/api/v1/public/portal/submissions/price_tag_request/{id}"


@pytest.fixture(autouse=True)
def no_respond(monkeypatch):
    """S8: no test run reaches api.respond.io. See `_ptag_r9_seed.block_respond`."""
    return seed.block_respond(monkeypatch)

_CRM = "/api/v1/dealer-kit/price-tag-requests/{id}"


def _review_rows(db, request_id: str) -> list:
    from app.models.price_tag import PriceTagReviewComment

    return (
        db.query(PriceTagReviewComment)
        .filter(PriceTagReviewComment.request_id == request_id)
        .order_by(PriceTagReviewComment.created_at)
        .all()
    )


def _pin(line_id: str, body: str, *, x=0.25, y=0.5, w=0.0, h=0.0) -> dict:
    return {"line_id": line_id, "x": x, "y": y, "w": w, "h": h, "body": body}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def portal():
    from app.api.v1.public.portal import get_portal_token
    from app.database import get_db
    from app.models.portal import PortalToken

    with blank_session() as db:
        seed.seed_marketer(db)
        contact_id = seed.seed_portal_contact(db)

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_portal_token] = lambda: PortalToken(
            id=str(uuid.uuid4()), contact_id=contact_id, space_id="zzt-space"
        )
        try:
            with TestClient(app, headers={"X-Portal-Token": "zzt-token"}) as client:
                yield client, db, contact_id
        finally:
            app.dependency_overrides.clear()


@pytest.fixture
def crm():
    from app.dependencies import (
        get_current_user,
        get_current_user_or_api_key,
        get_db,
    )
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        seed.seed_marketer(db)

        def _override_get_db():
            yield db

        async def _override_scope():
            scope = frozenset({seed.SORENTO})
            set_company_scope(db, scope)
            return scope

        principal = {"id": seed.MARKETER_ID, "email": "zzt-ptag-r9-marketer@test.com"}
        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[apply_company_scope] = _override_scope
        app.dependency_overrides[get_current_user] = lambda: principal
        app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
        try:
            with TestClient(app) as client:
                yield client, db
        finally:
            app.dependency_overrides.clear()


def _proof_ready_request(db, contact_id):
    product = seed.seed_product(db)
    request = seed.seed_request(
        db,
        contact_id,
        status="proof_ready",
        products=[product],
        assigned_to_id=seed.MARKETER_ID,
    )
    page, doc = seed.attach_design(db, request)
    return request, page, doc


# ---------------------------------------------------------------------------
# AC-S2-3 - Send creates the rows and moves the request
# ---------------------------------------------------------------------------


class TestSendCreatesTheRows:
    def test_pins_and_a_note_become_rows_and_the_status_moves(self, portal):
        client, db, contact_id = portal
        request, _page, _doc = _proof_ready_request(db, contact_id)
        line_id = request.lines[0].id
        notes_before = request.notes

        response = client.post(
            f"{_PORTAL.format(id=request.id)}/request-changes",
            json={
                "comments": [
                    _pin(line_id, "Make the price bigger"),
                    _pin(line_id, "Move the logo", x=0.1, y=0.1, w=0.3, h=0.2),
                ],
                "note": "Overall it is too busy",
            },
        )

        assert response.status_code == 200, response.text
        rows = _review_rows(db, request.id)
        # Two pins plus the general note = three rows (AC-S2-3's "N+1").
        assert len(rows) == 3, [row.body for row in rows]

        pinned = [row for row in rows if row.line_id is not None]
        assert len(pinned) == 2
        for row in pinned:
            assert row.line_id == line_id
            assert 0 <= float(row.x) <= 1 and 0 <= float(row.y) <= 1
            assert 0 <= float(row.w) <= 1 and 0 <= float(row.h) <= 1
            assert row.author_contact_id == contact_id
            assert row.author_user_id is None
            assert row.resolved_at is None

        general = [row for row in rows if row.line_id is None]
        assert len(general) == 1
        assert general[0].body == "Overall it is too busy"
        assert general[0].x is None and general[0].y is None

        db.expire_all()
        from app.models.price_tag import PriceTagRequest

        fresh = db.query(PriceTagRequest).filter(
            PriceTagRequest.id == request.id
        ).first()
        assert fresh.status == "changes_requested"
        assert fresh.notes == notes_before, (
            "the salesperson's own notes are not a comment log - the "
            '"\\n[Changes requested]: ..." append is retired'
        )

    def test_the_response_carries_the_created_comments_and_the_round(self, portal):
        client, db, contact_id = portal
        request, _page, _doc = _proof_ready_request(db, contact_id)

        body = client.post(
            f"{_PORTAL.format(id=request.id)}/request-changes",
            json={"comments": [_pin(request.lines[0].id, "Bigger price")]},
        ).json()

        assert body["status"] == "changes_requested"
        assert body["round"] >= 1
        assert len(body["comments"]) == 1
        assert body["comments"][0]["body"] == "Bigger price"

    def test_another_contacts_request_404s_and_writes_nothing(self, portal):
        client, db, _contact_id = portal
        other_contact = seed.seed_portal_contact(db)
        request, _page, _doc = _proof_ready_request(db, other_contact)

        response = client.post(
            f"{_PORTAL.format(id=request.id)}/request-changes",
            json={"comments": [_pin(request.lines[0].id, "Not mine")]},
        )

        assert response.status_code == 404, response.text
        assert _review_rows(db, request.id) == []

    def test_a_request_that_is_not_waiting_on_the_salesperson_409s(self, portal):
        """A design still being drawn cannot be commented on."""
        client, db, contact_id = portal
        product = seed.seed_product(db)
        request = seed.seed_request(
            db, contact_id, status="designing", products=[product]
        )
        seed.attach_design(db, request)

        response = client.post(
            f"{_PORTAL.format(id=request.id)}/request-changes",
            json={"comments": [_pin(request.lines[0].id, "Too early")]},
        )

        assert response.status_code == 409, response.text
        assert _review_rows(db, request.id) == []


# ---------------------------------------------------------------------------
# AC-S2-8 - the legacy body still works for one release
# ---------------------------------------------------------------------------


class TestTheLegacyNoteBodyStillWorks:
    def test_a_body_of_only_note_creates_one_general_row(self, portal):
        client, db, contact_id = portal
        request, _page, _doc = _proof_ready_request(db, contact_id)

        response = client.post(
            f"{_PORTAL.format(id=request.id)}/request-changes",
            json={"note": "Please redo the whole thing"},
        )

        assert response.status_code == 200, response.text
        rows = _review_rows(db, request.id)
        assert len(rows) == 1
        assert rows[0].line_id is None
        assert rows[0].x is None
        assert rows[0].body == "Please redo the whole thing"

    def test_an_empty_body_is_refused_rather_than_transitioning_silently(self, portal):
        client, db, contact_id = portal
        request, _page, _doc = _proof_ready_request(db, contact_id)

        response = client.post(
            f"{_PORTAL.format(id=request.id)}/request-changes",
            json={"comments": []},
        )

        assert response.status_code == 422, response.text
        assert _review_rows(db, request.id) == []


# ---------------------------------------------------------------------------
# AC-S2-7 - the round number
# ---------------------------------------------------------------------------


class TestRoundCountsTheProofsNotTheSends:
    def test_round_equals_the_number_of_proof_ready_snapshots_at_send(self, portal):
        client, db, contact_id = portal
        request, page, doc = _proof_ready_request(db, contact_id)
        seed.snapshot_proof_ready(db, page, doc, version=2)

        client.post(
            f"{_PORTAL.format(id=request.id)}/request-changes",
            json={"comments": [_pin(request.lines[0].id, "First round")]},
        )

        assert [row.round for row in _review_rows(db, request.id)] == [1]

        # Marketing revises and sends a second proof; the salesperson comments
        # again. The earlier round keeps its number.
        seed.snapshot_proof_ready(db, page, doc, version=3)
        from app.models.price_tag import PriceTagRequest

        db.query(PriceTagRequest).filter(PriceTagRequest.id == request.id).update(
            {"status": "proof_ready"}
        )
        db.commit()

        client.post(
            f"{_PORTAL.format(id=request.id)}/request-changes",
            json={"comments": [_pin(request.lines[0].id, "Second round")]},
        )

        assert sorted(row.round for row in _review_rows(db, request.id)) == [1, 2]

    def test_the_round_is_stored_not_recomputed_at_read(self, portal):
        """A third proof after the fact must not renumber round 1."""
        client, db, contact_id = portal
        request, page, doc = _proof_ready_request(db, contact_id)
        seed.snapshot_proof_ready(db, page, doc, version=2)
        client.post(
            f"{_PORTAL.format(id=request.id)}/request-changes",
            json={"comments": [_pin(request.lines[0].id, "Round one")]},
        )

        seed.snapshot_proof_ready(db, page, doc, version=3)
        seed.snapshot_proof_ready(db, page, doc, version=4)

        listed = client.get(f"{_PORTAL.format(id=request.id)}/review-comments").json()
        assert [row["round"] for row in listed] == [1]


# ---------------------------------------------------------------------------
# AC-S2-5 - who may tick Done, and what both surfaces list
# ---------------------------------------------------------------------------


class TestDoneBelongsToMarketing:
    def _one_comment(self, db, contact_id):
        from app.models.price_tag import PriceTagReviewComment

        request, _page, _doc = _proof_ready_request(db, contact_id)
        comment = PriceTagReviewComment(
            id=str(uuid.uuid4()),
            request_id=request.id,
            line_id=request.lines[0].id,
            round=1,
            x=0.25,
            y=0.5,
            w=0,
            h=0,
            body="Make the price bigger",
            author_contact_id=contact_id,
            company_id=seed.SORENTO,
        )
        db.add(comment)
        db.flush()
        db.commit()
        return request, comment

    def test_a_processor_ticking_done_records_who_and_when(self, crm):
        client, db = crm
        contact_id = seed.seed_portal_contact(db)
        request, comment = self._one_comment(db, contact_id)

        response = client.patch(
            f"{_CRM.format(id=request.id)}/review-comments/{comment.id}",
            json={"resolved": True},
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["resolved_at"] is not None
        assert body["resolved_by_name"] == seed.MARKETER_NAME

        db.expire_all()
        row = _review_rows(db, request.id)[0]
        assert row.resolved_at is not None
        assert row.resolved_by_id == seed.MARKETER_ID

    def test_untick_puts_it_back(self, crm):
        client, db = crm
        contact_id = seed.seed_portal_contact(db)
        request, comment = self._one_comment(db, contact_id)
        url = f"{_CRM.format(id=request.id)}/review-comments/{comment.id}"

        client.patch(url, json={"resolved": True})
        client.patch(url, json={"resolved": False})

        db.expire_all()
        row = _review_rows(db, request.id)[0]
        assert row.resolved_at is None
        assert row.resolved_by_id is None

    def test_a_signed_in_user_without_the_permission_cannot_tick_it_off(self, crm):
        """AC-S2-5: 403, not 404 - the row is readable, not closeable.

        Asserted with a LOGGED IN user who lacks
        ``dealer_kit.price_tag_requests.process`` rather than with the portal
        contact: the portal carries no CRM principal at all, so that request is
        401 before the permission is ever consulted, which proves nothing about
        the gate.
        """
        client, db = crm
        contact_id = seed.seed_portal_contact(db)
        request, comment = self._one_comment(db, contact_id)

        from app.dependencies import get_current_user, get_current_user_or_api_key

        outsider = {"id": seed.OTHER_USER_ID, "email": "zzt-ptag-r9-other@test.com"}
        app.dependency_overrides[get_current_user] = lambda: outsider
        app.dependency_overrides[get_current_user_or_api_key] = lambda: outsider
        try:
            response = client.patch(
                f"{_CRM.format(id=request.id)}/review-comments/{comment.id}",
                json={"resolved": True},
            )
        finally:
            principal = {
                "id": seed.MARKETER_ID,
                "email": "zzt-ptag-r9-marketer@test.com",
            }
            app.dependency_overrides[get_current_user] = lambda: principal
            app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        assert response.status_code == 403, response.text
        db.expire_all()
        assert _review_rows(db, request.id)[0].resolved_at is None

    def test_both_surfaces_list_the_rows(self, portal):
        client, db, contact_id = portal
        request, comment = self._one_comment(db, contact_id)

        listed = client.get(f"{_PORTAL.format(id=request.id)}/review-comments")

        assert listed.status_code == 200, listed.text
        rows = listed.json()
        assert [row["id"] for row in rows] == [comment.id]
        assert rows[0]["line_id"] == request.lines[0].id
        assert rows[0]["x"] == pytest.approx(0.25)
        assert rows[0]["resolved_at"] is None

    def test_the_crm_lists_the_same_rows(self, crm):
        client, db = crm
        contact_id = seed.seed_portal_contact(db)
        request, comment = self._one_comment(db, contact_id)

        listed = client.get(f"{_CRM.format(id=request.id)}/review-comments")

        assert listed.status_code == 200, listed.text
        assert [row["id"] for row in listed.json()] == [comment.id]


# ---------------------------------------------------------------------------
# The counted review round (D4/R1) - the whole loop, end to end
# ---------------------------------------------------------------------------


class TestTheReviewRoundIsCounted:
    """`review_round` is a COLUMN, incremented on every entry into proof_ready.

    It used to be derived from the ``Marked proof ready`` page versions, and
    that snapshot is only written when a draft exists - the designer's own CTA
    saves first, so the send usually skipped it and every round after the first
    came back as 1. Three things went wrong at once and all of them silently:
    the comments were filed under round 1 forever, the assignee's bell
    deduplicated against round 1 and never rang again, and the salesperson's
    confirmation named the wrong round.

    This walks the real loop rather than asserting the counter on its own,
    because the counter is only interesting where it is read.
    """

    def _bells(self, db, request_id):
        from app.models.notification import Notification

        return (
            db.query(Notification)
            .filter(Notification.user_id == seed.MARKETER_ID)
            .filter(Notification.source_entity_type == "price_tag_request")
            .filter(Notification.source_entity_id == str(request_id))
            .all()
        )

    def test_it_counts_every_entry_into_proof_ready(self, portal):
        from app.models.price_tag import PriceTagRequest
        from app.services.price_tag_request_service import PriceTagRequestService

        _client, db, contact_id = portal
        product = seed.seed_product(db)
        request = seed.seed_request(
            db,
            contact_id,
            status="designing",
            products=[product],
            print_by="office",
            assigned_to_id=seed.MARKETER_ID,
        )
        assert (request.review_round or 0) == 0

        PriceTagRequestService.transition_status(
            db, request.id, "proof_ready", user_id=seed.MARKETER_ID
        )
        db.commit()
        db.expire_all()
        fresh = db.query(PriceTagRequest).filter(
            PriceTagRequest.id == request.id
        ).first()
        assert fresh.review_round == 1

        PriceTagRequestService.transition_status(
            db, request.id, "changes_requested", user_id=seed.MARKETER_ID
        )
        PriceTagRequestService.transition_status(
            db, request.id, "proof_ready", user_id=seed.MARKETER_ID
        )
        db.commit()
        db.expire_all()
        fresh = db.query(PriceTagRequest).filter(
            PriceTagRequest.id == request.id
        ).first()
        assert fresh.review_round == 2, (
            "a second proof is a second round; the version snapshot the old "
            "derivation read is not written when the CTA saved first"
        )

    def test_round_two_comments_the_bell_and_the_text_all_agree(self, portal, no_respond):
        from app.models.price_tag import PriceTagRequest
        from app.services.price_tag_request_service import PriceTagRequestService

        client, db, contact_id = portal
        product = seed.seed_product(db)
        request = seed.seed_request(
            db,
            contact_id,
            status="designing",
            products=[product],
            print_by="office",
            assigned_to_id=seed.MARKETER_ID,
        )
        seed.attach_design(db, request)
        line_id = request.lines[0].id
        url = f"{_PORTAL.format(id=request.id)}/request-changes"

        # Round one.
        PriceTagRequestService.transition_status(
            db, request.id, "proof_ready", user_id=seed.MARKETER_ID
        )
        db.commit()
        first = client.post(url, json={"comments": [_pin(line_id, "Round one")]})
        assert first.status_code == 200, first.text
        assert [row.round for row in _review_rows(db, request.id)] == [1]
        assert len(self._bells(db, request.id)) == 1

        # Marketing revises and sends the proof back.
        PriceTagRequestService.transition_status(
            db, request.id, "proof_ready", user_id=seed.MARKETER_ID
        )
        db.commit()

        # Round two, two pins this time.
        response = client.post(
            url,
            json={
                "comments": [
                    _pin(line_id, "Bigger price"),
                    _pin(line_id, "Move the logo"),
                ]
            },
        )

        assert response.status_code == 200, response.text
        assert response.json()["round"] == 2
        assert sorted(row.round for row in _review_rows(db, request.id)) == [1, 2, 2]

        bells = self._bells(db, request.id)
        assert len(bells) == 2, "round two rang no bell of its own"
        assert len({bell.dedup_key for bell in bells}) == 2

        sent = [row["text"] for row in no_respond]
        assert any("You sent 2 change requests" in text for text in sent), sent

    def test_a_row_whose_counter_is_zero_sends_round_one_never_the_snapshots(
        self, portal
    ):
        """r9 review-round leftover R2: `current_round` reads ONLY
        `request.review_round` now - the snapshot fallback is retired.

        A counter of 0 answers round 1 (`max(request.review_round, 1)`)
        whatever the page versions say, even when two "Marked proof ready"
        snapshots exist: a genuinely pre-deploy, already-reviewed row gets its
        real round from the migration's `backfill_review_round` (see
        `test_price_tag_print_collection.py`), not from a second, competing
        derivation living in the read path.
        """
        from app.models.price_tag import PriceTagRequest

        client, db, contact_id = portal
        product = seed.seed_product(db)
        request = seed.seed_request(
            db,
            contact_id,
            status="proof_ready",
            products=[product],
            print_by="office",
            assigned_to_id=seed.MARKETER_ID,
        )
        page, doc = seed.attach_design(db, request)
        # Two proofs exist, but the counter is 0 - they must NOT be read.
        seed.snapshot_proof_ready(db, page, doc, version=2)
        seed.snapshot_proof_ready(db, page, doc, version=3)
        db.query(PriceTagRequest).filter(PriceTagRequest.id == request.id).update(
            {"review_round": 0}
        )
        db.commit()

        body = client.post(
            f"{_PORTAL.format(id=request.id)}/request-changes",
            json={"comments": [_pin(request.lines[0].id, "Round one, really")]},
        ).json()

        assert body["round"] == 1, (
            "current_round must read ONLY request.review_round now - the two "
            "snapshots are a red herring the old fallback used to chase"
        )
        assert [row.round for row in _review_rows(db, request.id)] == [1]

    def test_a_counter_of_one_sends_round_one_and_a_resend_is_round_two(
        self, portal, no_respond
    ):
        """The live scenario the counter was built to fix: counter 0 at the
        FIRST send used to derive round 1 from the snapshots without ever
        setting the counter, so the SECOND send (counter now 1 after "Mark
        design ready") still read as round 1 - one bell, ever, and the
        salesperson's own confirmation never said "round 2".

        Walks it for real: proof_ready (counter -> 1), Send (round 1, one
        bell), Mark design ready again (counter -> 2), Send (round 2, a
        SECOND distinct bell).
        """
        from app.models.notification import Notification
        from app.models.price_tag import PriceTagRequest
        from app.services.price_tag_request_service import PriceTagRequestService

        client, db, contact_id = portal
        product = seed.seed_product(db)
        request = seed.seed_request(
            db,
            contact_id,
            status="designing",
            products=[product],
            print_by="office",
            assigned_to_id=seed.MARKETER_ID,
        )
        seed.attach_design(db, request)
        line_id = request.lines[0].id

        def bells():
            return (
                db.query(Notification)
                .filter(Notification.user_id == seed.MARKETER_ID)
                .filter(Notification.source_entity_type == "price_tag_request")
                .filter(Notification.source_entity_id == str(request.id))
                .all()
            )

        PriceTagRequestService.transition_status(
            db, request.id, "proof_ready", user_id=seed.MARKETER_ID
        )
        db.commit()
        db.expire_all()
        fresh = (
            db.query(PriceTagRequest).filter(PriceTagRequest.id == request.id).first()
        )
        assert fresh.review_round == 1, "counter should be 1 after the first proof"

        first = client.post(
            f"{_PORTAL.format(id=request.id)}/request-changes",
            json={"comments": [_pin(line_id, "Round one")]},
        )
        assert first.status_code == 200, first.text
        assert first.json()["round"] == 1
        assert len(bells()) == 1

        # Marketing marks the design ready again ("Mark design ready").
        PriceTagRequestService.transition_status(
            db, request.id, "proof_ready", user_id=seed.MARKETER_ID
        )
        db.commit()
        db.expire_all()
        fresh = (
            db.query(PriceTagRequest).filter(PriceTagRequest.id == request.id).first()
        )
        assert fresh.review_round == 2, "counter should be 2 after the second proof"

        second = client.post(
            f"{_PORTAL.format(id=request.id)}/request-changes",
            json={"comments": [_pin(line_id, "Round two")]},
        )
        assert second.status_code == 200, second.text
        assert second.json()["round"] == 2, (
            "the second send must not still read as round 1"
        )

        rung = bells()
        assert len(rung) == 2, "the second round rang no bell of its own"
        assert len({row.dedup_key for row in rung}) == 2

        # Two separate confirmations, one per round - not deduplicated or
        # silently dropped the way the second one used to be.
        sent_text = [row["text"] for row in no_respond]
        confirmations = [text for text in sent_text if "change request" in text]
        assert len(confirmations) == 2, sent_text

    def test_a_request_that_has_never_been_proofed_is_round_one(self, portal):
        """Numbering it 0 would read as "before the first round"."""
        from app.services import price_tag_review_service

        _client, db, contact_id = portal
        product = seed.seed_product(db)
        request = seed.seed_request(
            db, contact_id, status="designing", products=[product], print_by="office"
        )

        assert price_tag_review_service.current_round(db, request) == 1
