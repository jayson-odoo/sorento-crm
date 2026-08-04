"""S7: both sides sign, and the customer's signature WINS the quotation.

The decisive behaviour, and the one this file exists to pin, is the client's 2026-08-04 decision:
a counter-signature is a commitment, not paperwork. So acceptance marks every scope the issue
carried as won and the project's outcome follows through the rule that already existed.

The exception is deliberate and also pinned: a scope somebody already marked LOST is not flipped.
A signature on a document that still lists a scope must not silently overrule a human decision.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.projects import Project, ProjectQuotationIssue, QuotationSignature
from app.models.user import User
from app.services import project_quotation_document_service as qdocs
from app.services import project_quotation_service as quotes
from app.services import project_seed_service
from app.services.error_handler import AppException

from ._pg_fixture import blank_session

MARKER = "zzt-qsign"

PRICED_QTY = Decimal("1046")
PRICED_RATE = Decimal("250")
PRICED_TOTAL = Decimal("261500.00")

A_SIGNATURE = "data:image/png;base64,zzt-strokes"


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


def _sign_draft(db, document, owner):
    return qdocs.sign_as_sorento(
        db,
        document=document,
        actor_user_id=owner,
        payload={
            "signer_name": f"{MARKER} Baser",
            "mode": "draw",
            "image_data_uri": A_SIGNATURE,
            "ip_address": "203.0.113.7",
            "user_agent": "zzt-agent",
        },
    )


def _priced_scope(db, document, owner, label: str):
    scope = qdocs.add_scope(
        db, document=document, scope_label=label, actor_user_id=owner
    )
    product = _product(db, f"{MARKER}-{_uid()[:6]}")
    quotes.upsert_line(
        db,
        version=quotes.current_version(db, scope.id),
        actor_user_id=owner,
        payload={
            "product_id": product.id,
            "unit_price": str(PRICED_RATE),
            "quantity": str(PRICED_QTY),
        },
    )
    db.flush()
    return scope


def _setup(db, *, scopes=("Townhouse",)):
    company_id = _sorento(db)
    project_seed_service.run(db, company_id=company_id)
    owner = _user(db, f"{MARKER} Baser")
    project = _project(db, company_id, owner)
    document = qdocs.create_document(db, project=project, actor_user_id=owner)
    made = [_priced_scope(db, document, owner, f"{MARKER} {name}") for name in scopes]
    return project, document, owner, made


# ------------------------------------------------------------------ AC-H1


def test_an_unsigned_quotation_cannot_be_issued():
    """So an unsigned quotation never reaches a customer's inbox.

    Enforced at the service rather than left to a reviewer, because the failure is invisible after
    the fact: nobody can tell from the PDF whether anybody meant to send it.
    """
    with blank_session() as db:
        _project_row, document, owner, _scopes = _setup(db)

        with pytest.raises(AppException) as refused:
            qdocs.issue(db, document=document, actor_user_id=owner)
        assert refused.value.status_code == 422
        assert "sign" in refused.value.detail["message"].lower()

        _sign_draft(db, document, owner)
        record = qdocs.issue(db, document=document, actor_user_id=owner)
        assert record.issue_no == 1


def test_the_issue_keeps_the_signature_it_went_out_with():
    """Re-signing the draft later must not rewrite what an already-issued revision carried.

    The same snapshot rule as the lines and the rendered letter. Referencing the draft's signature
    would mean a fresh squiggle silently restamped every past revision.
    """
    with blank_session() as db:
        _project_row, document, owner, _scopes = _setup(db)
        first = _sign_draft(db, document, owner)
        record = qdocs.issue(db, document=document, actor_user_id=owner)
        assert record.sorento_signature_id == first.id

        # Sign again, as somebody would before issuing R2.
        second = _sign_draft(db, document, owner)
        assert second.id != first.id
        assert document.signatory_signature_id == second.id

        refreshed = (
            db.query(ProjectQuotationIssue)
            .filter(ProjectQuotationIssue.id == record.id)
            .one()
        )
        assert refreshed.sorento_signature_id == first.id


# ------------------------------------------------------------------ AC-H5, H7


def test_the_counter_sign_link_only_opens_the_issue_it_was_minted_for():
    """A public link is the whole credential, so it has to be narrow and expiring.

    An unknown token and an expired one answer identically: telling a caller that a token exists
    but has lapsed confirms the token to anybody guessing.
    """
    with blank_session() as db:
        _project_row, document, owner, _scopes = _setup(db)
        _sign_draft(db, document, owner)
        record = qdocs.issue(db, document=document, actor_user_id=owner)

        token = qdocs.issue_sign_link(db, record=record)
        assert qdocs.get_issue_by_sign_token(db, token).id == record.id

        # Re-minting keeps a live link working: the customer already has it in their inbox.
        assert qdocs.issue_sign_link(db, record=record) == token

        with pytest.raises(AppException) as unknown:
            qdocs.get_issue_by_sign_token(db, "zzt-not-a-real-token")
        assert unknown.value.status_code == 404

        # Expired reads exactly the same as unknown.
        record.sign_token_expires_at = record.issued_at.replace(year=2000)
        db.flush()
        with pytest.raises(AppException) as expired:
            qdocs.get_issue_by_sign_token(db, token)
        assert expired.value.status_code == 404
        assert expired.value.detail["message"] == unknown.value.detail["message"]


def test_the_customer_counter_signing_wins_the_quotation():
    """The client's decision, and the reason this slice exists.

    A counter-signature is the commitment, so every scope the issue carried becomes won and the
    project's outcome derives to won. Written the other way round first (evidence only); the
    client overruled that on 2026-08-04.
    """
    with blank_session() as db:
        project, document, owner, scopes = _setup(
            db, scopes=("Townhouse", "Guard house")
        )
        _sign_draft(db, document, owner)
        record = qdocs.issue(db, document=document, actor_user_id=owner)

        assert quotes.derive_project_outcome(db, project) == "open"

        qdocs.accept_issue(
            db,
            record=record,
            signer_name=f"{MARKER} Kelly",
            mode="draw",
            image_data_uri=A_SIGNATURE,
            ip_address="203.0.113.9",
            user_agent="zzt-customer",
        )

        assert record.accepted_at is not None
        for scope in scopes:
            db.refresh(scope)
            assert scope.outcome == "won"
            # Recorded, so "why is this won" is answerable without opening a signature blob.
            assert scope.decided_at is not None
        assert quotes.derive_project_outcome(db, project) == "won"
        db.refresh(project)
        assert project.outcome == "won"


def test_a_scope_already_lost_is_not_flipped_by_a_signature():
    """Somebody decided that deliberately, and a signature must not overrule a person silently.

    The acceptance is still recorded, and the other scopes still win. Pinned because the naive
    implementation - set every scope on the issue to won - loses that decision without a trace.
    """
    with blank_session() as db:
        project, document, owner, scopes = _setup(
            db, scopes=("Townhouse", "Guard house")
        )
        townhouse, guard_house = scopes
        quotes.set_outcome(
            db, quotation=townhouse, outcome="lost", loss_reason="price"
        )
        db.flush()

        _sign_draft(db, document, owner)
        record = qdocs.issue(db, document=document, actor_user_id=owner)
        qdocs.accept_issue(
            db,
            record=record,
            signer_name=f"{MARKER} Kelly",
            mode="type",
            image_data_uri=A_SIGNATURE,
        )

        db.refresh(townhouse)
        db.refresh(guard_house)
        assert townhouse.outcome == "lost"
        assert guard_house.outcome == "won"
        assert record.accepted_at is not None
        # Any-won wins, so the project is won even with one scope lost.
        assert quotes.derive_project_outcome(db, project) == "won"


def test_signing_twice_keeps_the_first_signature_and_the_first_timestamp():
    """A customer who double-taps has not agreed to two different things.

    Overwriting would move `accepted_at`, and that timestamp is the one fact anybody would quote in
    a dispute.
    """
    with blank_session() as db:
        _project_row, document, owner, _scopes = _setup(db)
        _sign_draft(db, document, owner)
        record = qdocs.issue(db, document=document, actor_user_id=owner)

        qdocs.accept_issue(
            db,
            record=record,
            signer_name=f"{MARKER} Kelly",
            mode="draw",
            image_data_uri=A_SIGNATURE,
        )
        first_signature = record.customer_signature_id
        first_accepted = record.accepted_at

        qdocs.accept_issue(
            db,
            record=record,
            signer_name=f"{MARKER} Somebody Else",
            mode="type",
            image_data_uri="data:image/png;base64,zzt-second",
        )

        assert record.customer_signature_id == first_signature
        assert record.accepted_at == first_accepted
        assert (
            db.query(QuotationSignature)
            .filter(QuotationSignature.owner_kind == "customer")
            .count()
            == 1
        )


# ------------------------------------------------------------------ AC-H4


def test_a_signature_records_what_can_be_observed_and_is_honest_about_the_rest():
    """GPS is null when a browser refuses, and that is stored as null rather than as zero.

    Zero is a real place off the coast of Africa. A screen showing "0, 0" reads as a location and
    would be worse than the dash the UAC asks for.
    """
    with blank_session() as db:
        _project_row, document, owner, _scopes = _setup(db)

        signature = qdocs.record_signature(
            db,
            company_id=document.company_id,
            owner_kind="customer",
            signer_name=f"{MARKER} Kelly",
            mode="initials",
            image_data_uri=A_SIGNATURE,
            ip_address="203.0.113.9",
            user_agent="zzt-agent",
            gps_lat=None,
            gps_lng=None,
        )

        assert signature.ip_address == "203.0.113.9"
        assert signature.gps_lat is None and signature.gps_lng is None
        assert signature.signed_at is not None
        assert signature.mode == "initials"

        with pytest.raises(AppException) as empty:
            qdocs.record_signature(
                db,
                company_id=document.company_id,
                owner_kind="customer",
                signer_name=None,
                mode="draw",
                image_data_uri=None,
            )
        assert empty.value.status_code == 422


def test_the_sign_page_shows_what_was_issued_not_what_changed_since():
    """A signing surface must never show a customer something different from the PDF they hold.

    So the page renders from the version each scope contributed to the ISSUE. Proven by revising a
    scope and re-pricing it after issuing, then asserting the page still carries the old money.
    """
    with blank_session() as db:
        _project_row, document, owner, scopes = _setup(db)
        scope = scopes[0]
        _sign_draft(db, document, owner)
        record = qdocs.issue(db, document=document, actor_user_id=owner)

        page = qdocs.serialize_sign_page(db, record)
        assert page["grand_total"] == PRICED_TOTAL
        assert page["scopes"][0]["scope_total"] == PRICED_TOTAL

        # Editing the issued version is refused, so move on to a revision and halve the price.
        nxt = quotes.revise(db, quotation=scope, actor_user_id=owner)
        for line in quotes.list_lines(db, nxt.id):
            quotes.upsert_line(
                db,
                version=nxt,
                actor_user_id=owner,
                line=line,
                payload={"unit_price": "125.00"},
            )
        db.flush()

        # The live scope has moved; the issued page has not.
        assert qdocs.scope_total(db, scope) != PRICED_TOTAL
        after = qdocs.serialize_sign_page(db, record)
        assert after["grand_total"] == PRICED_TOTAL
        assert after["scopes"][0]["scope_total"] == PRICED_TOTAL
