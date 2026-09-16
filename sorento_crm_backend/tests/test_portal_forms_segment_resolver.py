"""Resolver rule (D3, r2): visible = SUPPORTED_TYPES (base four) UNION the
contact's market segments' ``portal_form_types``, then per-contact overrides
win. Access types play no part any more (D1).
"""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.models.access import ContactAccessType, respond_contact_access_types
from app.models.price_tag import ContactPortalFormOverride
from app.services.portal_form_visibility_service import resolve_visible_form_types
from app.services.portal_service import SUPPORTED_TYPES
from tests._pg_fixture import blank_session, unique_code
from tests._portal_grant import link_contact_segment, seed_segment


def _contact(db) -> str:
    contact_id = str(uuid.uuid4())
    db.execute(
        text("INSERT INTO respond_contacts (id, phone_number, name) VALUES (:i, :p, :n)"),
        {"i": contact_id, "p": f"+60{uuid.uuid4().hex[:9]}", "n": unique_code("contact")},
    )
    db.flush()
    return contact_id


# --------------------------------------------------------------------------- AC-R1


def test_resolver_is_base_four_plus_segment_union_and_ignores_access_types():
    with blank_session() as db:
        contact_id = _contact(db)
        seg_a = seed_segment(db, kinds=["price_tag_request"])
        seg_b = seed_segment(db, kinds=[])
        link_contact_segment(db, contact_id, seg_a.code)
        link_contact_segment(db, contact_id, seg_b.code)

        # An access type assignment must be INERT (D1/AC-R1): the resolver
        # never consults respond_contact_access_types any more, so assigning
        # one changes nothing about what the contact sees.
        access_type = ContactAccessType(code=unique_code("at").lower(), name="ZZT AT")
        db.add(access_type)
        db.flush()
        db.execute(
            respond_contact_access_types.insert().values(
                contact_id=contact_id, access_type_code=access_type.code
            )
        )
        db.flush()

        visible = resolve_visible_form_types(db, contact_id)

        assert visible == set(SUPPORTED_TYPES) | {"price_tag_request"}


# --------------------------------------------------------------------------- AC-R2


def test_resolver_override_false_hides_a_base_kind_and_true_shows_price_tag():
    with blank_session() as db:
        contact_id = _contact(db)
        db.add(
            ContactPortalFormOverride(
                id=str(uuid.uuid4()),
                contact_id=contact_id,
                form_type="complaint",
                is_enabled=False,
            )
        )
        db.add(
            ContactPortalFormOverride(
                id=str(uuid.uuid4()),
                contact_id=contact_id,
                form_type="price_tag_request",
                is_enabled=True,
            )
        )
        db.flush()

        visible = resolve_visible_form_types(db, contact_id)

        assert "complaint" not in visible
        assert "price_tag_request" in visible
        assert visible == (set(SUPPORTED_TYPES) - {"complaint"}) | {"price_tag_request"}


# --------------------------------------------------------------------------- AC-R6


def test_resolver_ignores_an_inactive_segments_grant():
    """r4/SEC3: deactivating a segment revokes what it granted, without
    needing to also unassign every contact from it first."""
    with blank_session() as db:
        contact_id = _contact(db)
        segment = seed_segment(db, kinds=["price_tag_request"], is_active=False)
        link_contact_segment(db, contact_id, segment.code)

        visible = resolve_visible_form_types(db, contact_id)

        assert "price_tag_request" not in visible
        assert visible == set(SUPPORTED_TYPES)
