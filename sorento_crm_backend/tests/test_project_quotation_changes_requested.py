"""S17: the customer asks for a revision instead of signing it.

The counter-sign page used to offer Accept and nothing else, so a customer who wanted a lower
price had to leave the system to say so and the feedback never reached the CRM. This pins the
other answer: the request is captured on the ISSUE the customer was holding, written to the
project's activity feed, and the salesperson is told.

Three behaviours here are the difference between "captured" and "a support call":

1. **An empty request is not a request.** A blank box is refused rather than stored as a silent
   "something is wrong", because a salesperson cannot act on nothing.
2. **A double-tap is one request.** Same care `accept_issue` already takes: submitting the same
   words twice must not stamp a second time or send a second notification, while genuinely NEW
   feedback must get through - the same property `floor_breach_dedup_key` exists for.
3. **Accepted is final.** A quotation the customer has already signed cannot then be sent back
   for changes: the signature won the scopes and moved the project's outcome, and a record that
   says both would be unanswerable. The reverse IS allowed - somebody who asked for changes can
   still decide to sign - and the request stays on record as history.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.notification import Notification
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.projects import Project
from app.models.user import User
from app.services import project_quotation_document_service as qdocs
from app.services import project_quotation_service as quotes
from app.services import project_seed_service
from app.services.error_handler import AppException

from ._pg_fixture import blank_session

MARKER = "zzt-qchg"

A_SIGNATURE = "data:image/png;base64,zzt-strokes"
FEEDBACK = "The townhouse rate is above our budget. Can you re-price the WC at 250?"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _product(db, code: str) -> Product:
    category = ProductCategory(
        id=_uid(), category_code=f"ZZT-{_uid()[:8]}", category_name=f"{MARKER} Sanitary"
    )
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:4]}", uom_name="Piece")
    db.add_all([category, uom])
    db.flush()
    product = Product(
        id=_uid(),
        product_code=code,
        product_name=f"{MARKER} {code}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("300.00"),
    )
    db.add(product)
    db.flush()
    return product


def _project(db, company_id: str, owner: str) -> Project:
    project = Project(
        id=_uid(),
        company_id=company_id,
        project_code=f"ZZT-{_uid()[:8]}",
        title=f"{MARKER} Cabana Elmina",
        normalised_title=f"{MARKER} cabana elmina {_uid()[:6]}",
        owner_user_id=owner,
    )
    db.add(project)
    db.flush()
    return project


def _priced_scope(db, document, owner, label: str):
    scope = qdocs.add_scope(db, document=document, scope_label=label, actor_user_id=owner)
    product = _product(db, f"{MARKER}-{_uid()[:6]}")
    quotes.upsert_line(
        db,
        version=quotes.current_version(db, scope.id),
        actor_user_id=owner,
        payload={
            "product_id": product.id,
            "unit_price": "250",
            "quantity": "1046",
        },
    )
    db.flush()
    return scope


def _issued(db):
    """A project with one priced scope, signed by Sorento and issued as R1."""
    company_id = _sorento(db)
    project_seed_service.run(db, company_id=company_id)
    owner = _user(db, f"{MARKER} Baser")
    project = _project(db, company_id, owner)
    document = qdocs.create_document(db, project=project, actor_user_id=owner)
    _priced_scope(db, document, owner, f"{MARKER} Townhouse")
    qdocs.sign_as_sorento(
        db,
        document=document,
        actor_user_id=owner,
        payload={
            "signer_name": f"{MARKER} Baser",
            "mode": "draw",
            "image_data_uri": A_SIGNATURE,
        },
    )
    record = qdocs.issue(db, document=document, actor_user_id=owner)
    db.flush()
    return project, document, owner, record


def _notifications(db, user_id: str):
    return (
        db.query(Notification)
        .filter(
            Notification.user_id == user_id,
            Notification.type == "project_quotation_changes_requested",
        )
        .all()
    )


# ------------------------------------------------------------------ capture


def test_the_request_captures_the_feedback_and_who_left_it():
    """The whole point of the slice: the words the customer typed end up in the CRM.

    On the ISSUE, beside `accepted_at`, because the thing they were reading when they objected is
    the revision they hold - not the live document, which the salesperson is about to change.
    """
    with blank_session() as db:
        _project_row, _document, _owner, record = _issued(db)

        qdocs.request_changes(
            db, record=record, note=FEEDBACK, requester_name=f"{MARKER} Kelly"
        )

        assert record.changes_requested_at is not None
        assert record.changes_requested_note == FEEDBACK
        assert record.changes_requested_by_name == f"{MARKER} Kelly"
        # Nothing about the quotation itself moved: the salesperson revises by hand.
        assert record.accepted_at is None


def test_an_empty_request_is_not_a_request():
    """A blank box tells the salesperson nothing, so it is refused rather than stored.

    Whitespace counts as blank: a customer who pressed send on an empty textarea has not asked
    for anything, and a stamped `changes_requested_at` with no words behind it would show on the
    page as a settled outcome nobody can act on.
    """
    with blank_session() as db:
        _project_row, _document, _owner, record = _issued(db)

        for empty in (None, "", "   \n  "):
            with pytest.raises(AppException) as refused:
                qdocs.request_changes(db, record=record, note=empty)
            assert refused.value.status_code == 422
            assert refused.value.detail["code"] == "quotation_changes_note_required"

        assert record.changes_requested_at is None


def test_the_same_words_twice_are_one_request_and_one_notification():
    """A customer who double-taps has not asked for two different things.

    The timestamp must not move (it is what the salesperson sees as "when did they say this")
    and the salesperson must not be told twice about one message.
    """
    with blank_session() as db:
        _project_row, _document, owner, record = _issued(db)

        qdocs.request_changes(db, record=record, note=FEEDBACK)
        first_at = record.changes_requested_at

        qdocs.request_changes(db, record=record, note=f"  {FEEDBACK}  ")

        assert record.changes_requested_at == first_at
        assert len(_notifications(db, owner)) == 1


def test_new_feedback_gets_through_and_tells_the_salesperson_again():
    """Different words are a different message, not a repeat.

    The same property `floor_breach_dedup_key` exists for: deduplicating the identical submission
    must not silence a customer who comes back with something new to say.
    """
    with blank_session() as db:
        _project_row, _document, owner, record = _issued(db)

        qdocs.request_changes(db, record=record, note=FEEDBACK)
        first_at = record.changes_requested_at

        qdocs.request_changes(db, record=record, note="Also drop the guard house basin.")

        assert record.changes_requested_note == "Also drop the guard house basin."
        assert record.changes_requested_at >= first_at
        assert len(_notifications(db, owner)) == 2


# ------------------------------------------------------------------ the two decisions


def test_changes_cannot_be_requested_once_the_quotation_is_accepted():
    """Accepted is final, so the two decisions cannot land in a contradictory state.

    The counter-signature won every scope on the issue and moved the project's outcome. A later
    "please lower the price" sitting next to it would leave a record nobody can read: won, signed,
    and asking for a revision. The page offers no request form after acceptance, so this is only
    reachable from a stale tab - and it is answered with a refusal that says why.
    """
    with blank_session() as db:
        _project_row, _document, owner, record = _issued(db)
        qdocs.accept_issue(
            db,
            record=record,
            signer_name=f"{MARKER} Kelly",
            mode="draw",
            image_data_uri=A_SIGNATURE,
        )

        with pytest.raises(AppException) as refused:
            qdocs.request_changes(db, record=record, note=FEEDBACK)
        assert refused.value.status_code == 409
        assert refused.value.detail["code"] == "quotation_already_accepted"

        assert record.changes_requested_at is None
        assert _notifications(db, owner) == []


def test_a_customer_who_asked_for_changes_can_still_sign():
    """The reverse is allowed, because refusing a signature the customer wants to give is worse.

    They asked, then thought better of it, or the salesperson called them. The request stays on
    the row as history - it happened - and acceptance is what the page then reports.
    """
    with blank_session() as db:
        _project_row, _document, _owner, record = _issued(db)
        qdocs.request_changes(db, record=record, note=FEEDBACK)

        qdocs.accept_issue(
            db,
            record=record,
            signer_name=f"{MARKER} Kelly",
            mode="draw",
            image_data_uri=A_SIGNATURE,
        )

        assert record.accepted_at is not None
        assert record.changes_requested_note == FEEDBACK
        page = qdocs.serialize_sign_page(db, record)
        assert page["is_accepted"] is True
        assert page["is_changes_requested"] is True


# ------------------------------------------------------------------ told and recorded


def test_the_request_lands_in_the_project_activity_feed():
    """So "why did this quotation get revised" is answerable a month later without a mailbox.

    The note travels as the activity body, not only as a payload key, because that is what the
    feed renders.
    """
    from app.models.activities import ActivityEvent

    with blank_session() as db:
        project, _document, _owner, record = _issued(db)
        qdocs.request_changes(
            db, record=record, note=FEEDBACK, requester_name=f"{MARKER} Kelly"
        )
        db.flush()

        rows = (
            db.query(ActivityEvent)
            .filter(
                ActivityEvent.entity_type == "project",
                ActivityEvent.entity_id == str(project.id),
                ActivityEvent.system_template == "quotation_changes_requested",
            )
            .all()
        )
        assert len(rows) == 1
        assert FEEDBACK in (rows[0].body_text or "")


def test_a_waiting_customer_does_not_reset_the_staleness_clock():
    """A request nobody has answered is EXACTLY when a project should look unattended.

    So this template stays off `MEANINGFUL_TEMPLATES`. Adding it would clear the Unattended badge
    the moment the customer complains, which is the opposite of what the ladder is for.
    """
    from app.services import project_activity_service as activity

    with blank_session() as db:
        project, _document, _owner, record = _issued(db)
        project.stale_level = 3
        project.last_meaningful_activity_at = None
        db.flush()

        assert activity.is_meaningful("quotation_changes_requested") is False

        qdocs.request_changes(db, record=record, note=FEEDBACK)
        db.flush()

        assert int(project.stale_level or 0) == 3
        assert project.last_meaningful_activity_at is None


def test_the_salesperson_assigned_to_the_project_is_the_one_told():
    """Not "management": this is a message addressed to whoever is running the pursuit.

    The note travels in the body, so the notification is readable without opening the CRM.
    """
    with blank_session() as db:
        _project_row, document, owner, record = _issued(db)

        qdocs.request_changes(
            db, record=record, note=FEEDBACK, requester_name=f"{MARKER} Kelly"
        )

        sent = _notifications(db, owner)
        assert len(sent) == 1
        assert FEEDBACK[:40] in (sent[0].body or "")
        assert document.document_no in (sent[0].title or "") + (sent[0].body or "")


# ------------------------------------------------------------------ serializers


def test_both_serializers_carry_the_request():
    """The customer's page has to settle, and the salesperson's panel has to show the words.

    Two manual dict builders, and a column added to one of them only is invisible on the other
    screen - the failure this codebase has been bitten by before.
    """
    with blank_session() as db:
        _project_row, _document, _owner, record = _issued(db)

        before_page = qdocs.serialize_sign_page(db, record)
        before_issue = qdocs.serialize_issue(db, record)
        assert before_page["is_changes_requested"] is False
        assert before_page["changes_requested_note"] is None
        assert before_issue["is_changes_requested"] is False

        qdocs.request_changes(
            db, record=record, note=FEEDBACK, requester_name=f"{MARKER} Kelly"
        )
        db.flush()

        page = qdocs.serialize_sign_page(db, record)
        assert page["is_changes_requested"] is True
        assert page["changes_requested_note"] == FEEDBACK
        assert page["changes_requested_by_name"] == f"{MARKER} Kelly"
        assert page["changes_requested_at"] is not None

        issue = qdocs.serialize_issue(db, record)
        assert issue["is_changes_requested"] is True
        assert issue["changes_requested_note"] == FEEDBACK
        assert issue["changes_requested_by_name"] == f"{MARKER} Kelly"
        assert issue["changes_requested_at"] is not None


# ------------------------------------------------------------------ the public wire


def test_the_public_route_answers_the_customer_with_no_credential_but_the_link():
    """The same surface Accept lives on: a stranger, a token, and nothing else.

    Covers the four answers the route owes: the request itself, a blank one, one on an already
    accepted quotation, and an unknown token (which reads identically to an expired one).
    """
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.main import app

    with blank_session() as db:
        _project_row, _document, _owner, record = _issued(db)
        token = qdocs.issue_sign_link(db, record=record)
        db.commit()

        app.dependency_overrides[get_db] = lambda: db
        try:
            client = TestClient(app)

            blank = client.post(
                f"/api/v1/public/quotation-sign/{token}/request-changes",
                json={"note": "   "},
            )
            assert blank.status_code == 422, blank.text

            unknown = client.post(
                "/api/v1/public/quotation-sign/zzt-not-a-real-token/request-changes",
                json={"note": FEEDBACK},
            )
            assert unknown.status_code == 404

            asked = client.post(
                f"/api/v1/public/quotation-sign/{token}/request-changes",
                json={"note": FEEDBACK, "requester_name": f"{MARKER} Kelly"},
            )
            assert asked.status_code == 200, asked.text
            body = asked.json()
            # The response IS the page, so the browser can settle without a second fetch.
            assert body["is_changes_requested"] is True
            assert body["changes_requested_note"] == FEEDBACK
            assert body["our_ref"] == record.our_ref_text

            # Signed afterwards, then asked again: accepted is final.
            client.post(
                f"/api/v1/public/quotation-sign/{token}/accept",
                json={
                    "signer_name": f"{MARKER} Kelly",
                    "mode": "draw",
                    "image_data_uri": A_SIGNATURE,
                },
            )
            late = client.post(
                f"/api/v1/public/quotation-sign/{token}/request-changes",
                json={"note": "Actually, lower it again."},
            )
            assert late.status_code == 409, late.text
        finally:
            app.dependency_overrides.clear()
