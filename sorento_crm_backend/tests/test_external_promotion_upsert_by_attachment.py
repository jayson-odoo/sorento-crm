"""The external promotion upsert must key on the attachment, not the description.

n8n posts ``description = attachment_filename``. The upload path runs that name
through ``sanitize_storage_filename``, which strips ``@ ( ) , &`` -- so a promotion
created as ``@ CABANA COMBINE PROMO (OFFICE)_08072026.pdf`` is linked to an
attachment whose ``original_filename`` is ``CABANA COMBINE PROMO OFFICE_08072026.pdf``.

Matching on description alone therefore misses on every promotion whose name
contains a stripped character, and the endpoint silently creates a SECOND active
promotion for the same flyer. 14 of the 40 promotions queued for re-extraction
are in that state.

Every row here is created inside ``blank_session()`` -- a scratch schema whose
writes are discarded -- so the shared dev database is never touched.
"""
from __future__ import annotations

import uuid

import pytest

from app.api.v1.external.promotions import create_promotion
from app.models.marketing import Promotion, PromotionAttachment
from app.models.resources import Attachment
from app.schemas.external.marketing import PromotionRequest

from ._pg_fixture import blank_session, unique_code


def _user():
    """The integration principal. ``created_by`` carries no FK, so any id works."""
    return {"id": str(uuid.uuid4())}


def _attachment(db, original_filename: str) -> Attachment:
    """An uploaded flyer. ``original_filename`` is the sanitized name n8n echoes back."""
    att = Attachment(
        original_filename=original_filename,
        stored_filename=original_filename,
        file_path=f"https://cdn-sorento.com/promotion/{uuid.uuid4()}/{original_filename}",
    )
    db.add(att)
    db.flush()
    return att


def _promotion(db, description: str, attachment: Attachment | None = None) -> Promotion:
    promo = Promotion(description=description, is_active=True)
    db.add(promo)
    db.flush()
    if attachment is not None:
        db.add(PromotionAttachment(promotion_id=promo.id, attachment_id=attachment.id))
        db.flush()
    return promo


def _payload(description: str, attachment_id: str | None) -> PromotionRequest:
    """What n8n posts: the sanitized attachment filename as the root description.

    Built from a dict, not from model instances. ``_accept_n8n_shape`` runs
    ``mode="before"`` and replaces ``promotions`` with ``{}`` whenever it is not a
    dict, so handing it a ``PromotionHeader`` silently discards the header. A real
    request is always JSON, so this shape is also the faithful one.

    The schema requires a non-empty product list. The code is deliberately one that
    does not exist -- the endpoint treats unknown codes as a warning and still creates
    the promotion, which keeps these tests on identity resolution rather than linking.
    """
    body: dict = {
        "description": description,
        "promotions": {"is_active": True},
        "promotion_products": [{"product_code": unique_code("SKU")}],
    }
    if attachment_id is not None:
        body["attachment_id"] = attachment_id
    return PromotionRequest.model_validate(body)


def test_resubmit_by_attachment_updates_in_place_despite_sanitized_description():
    """The bug: stored description keeps '@' and '()', the filename does not."""
    with blank_session() as db:
        stem = unique_code("PROMO")
        stored_description = f"@ {stem} COMBINE PROMO (OFFICE).pdf"
        sanitized_filename = f"{stem} COMBINE PROMO OFFICE.pdf"

        att = _attachment(db, sanitized_filename)
        original = _promotion(db, stored_description, attachment=att)
        original_id = original.id

        result = create_promotion(
            payload=_payload(sanitized_filename, str(att.id)),
            current_user=_user(),
            db=db,
        )

        assert result.already_existed is True, "resubmit created a new promotion instead of updating"
        assert str(result.promotion.id) == str(original_id)

        rows = (
            db.query(Promotion)
            .filter(Promotion.description.in_([stored_description, sanitized_filename]))
            .all()
        )
        assert len(rows) == 1, f"expected one promotion for this flyer, found {len(rows)}"


def test_attachment_link_wins_over_a_description_that_matches_another_promotion():
    """The attachment is the identity; the description is a renameable display string."""
    with blank_session() as db:
        stem = unique_code("PROMO")
        linked_description = f"@ {stem} LINKED (OFFICE).pdf"
        colliding_description = f"{stem} LINKED OFFICE.pdf"

        att = _attachment(db, colliding_description)
        linked = _promotion(db, linked_description, attachment=att)
        decoy = _promotion(db, colliding_description)
        linked_id, decoy_id = linked.id, decoy.id

        result = create_promotion(
            payload=_payload(colliding_description, str(att.id)),
            current_user=_user(),
            db=db,
        )

        assert str(result.promotion.id) == str(linked_id), "description match beat the attachment link"
        assert str(result.promotion.id) != str(decoy_id)


def test_description_match_still_updates_when_the_promotion_has_no_attachment():
    """Regression: the description fallback stays for rows with no attachment link."""
    with blank_session() as db:
        description = f"{unique_code('PROMO')} NO ATTACHMENT.pdf"
        original_id = _promotion(db, description).id

        result = create_promotion(
            payload=_payload(description, None),
            current_user=_user(),
            db=db,
        )

        assert result.already_existed is True
        assert str(result.promotion.id) == str(original_id)
        assert db.query(Promotion).filter(Promotion.description == description).count() == 1


def test_unknown_attachment_and_unknown_description_creates_a_new_promotion():
    """No link, no name match: this really is a first-time create."""
    with blank_session() as db:
        att = _attachment(db, f"{unique_code('PROMO')} BRAND NEW.pdf")

        result = create_promotion(
            payload=_payload(att.original_filename, str(att.id)),
            current_user=_user(),
            db=db,
        )

        assert result.already_existed is False
        assert (
            db.query(Promotion).filter(Promotion.description == att.original_filename).count() == 1
        )
