"""AC-18: `hidden_spec_keys` on the resolve route's spec fallback.

UAC `documentation/plans/chatbot/spec-visibility-policy-acceptance-criteria.md`
AC-18. PLAN `documentation/plans/chatbot/PLAN-spec-visibility-policy.md`
"Spec fallback".

Precedent copied mechanically from `tests/test_spec_values_on_rows.py` /
`tests/test_resolve_spec_fallback.py`: a real category/uom/product chain, a
description carrying a real thickness value, `derive_for_code` deriving it, and
`POST /references/resolve` with `spec_fallback: true`.

Postgres only, own product/category/uom chain (CI's database has none).
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text as sa_text

from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_derivation import derive_for_code
from app.services.product_spec_registry import seed_spec_registry
from tests._pg_fixture import blank_session, unique_code

RESOLVE = "/api/v1/system/references/resolve"
_USER = {"id": str(uuid.uuid4()), "email": "zzt-n8n@example.com"}
SENTENCE = "double bowl kitchen sink with thickness 1.2mm"


@pytest.fixture
def db():
    with blank_session() as s:
        stem = unique_code("ZZTSVP")
        cat = ProductCategory(id=str(uuid.uuid4()), category_code=stem, category_name=stem)
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=stem[:20], uom_name="Piece")
        s.add_all([cat, uom])
        s.flush()
        backfill_category_signals(s)
        seed_spec_registry(s)

        product = Product(
            id=str(uuid.uuid4()),
            product_code=stem,
            product_name=stem,
            description="SORENTO S/STEEL KITCHEN SINK DOUBLE BOWL (820X450X230X1.2MM)",
            category_id=cat.id,
            base_uom_id=uom.id,
            list_price=Decimal("1.00"),
        )
        s.add(product)
        s.flush()
        derive_for_code(s, stem)
        yield s


@pytest.fixture()
def client(db):
    from app.database import get_db
    from app.dependencies import (
        get_current_user,
        get_current_user_or_api_key,
        get_external_api_user,
    )
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_external_api_user] = lambda: _USER
    app.dependency_overrides[get_current_user_or_api_key] = lambda: _USER
    app.dependency_overrides[get_current_user] = lambda: _USER
    app.dependency_overrides[apply_company_scope] = lambda: None
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _spec_matches(body: dict) -> list[dict]:
    for resolution in body.get("resolutions") or []:
        matches = [
            m for m in resolution.get("matches") or [] if m.get("match_tier") == "spec_search"
        ]
        if matches:
            return matches
    return []


def test_hidden_spec_keys_drops_the_thickness_candidate_and_its_summary(client):
    """A retail contact's `hidden_spec_keys` (['thickness']) means the resolver
    neither ranks on the stated thickness nor prints it in any candidate's
    summary; the SAME sentence with no hidden keys ranks on it (a project
    contact, unaffected).

    Earns its name (code review): the candidate's rendered `summary` and the
    `display.product_name` `_emit_spec_matches` copies it into
    (app/api/v1/system/references.py ~:2191) are a SENTENCE built from the
    product's full stored values, a different surface from the `specifications`
    dict/`matched_specs` list checked above - "... 1.2 mm thick." must not go
    out through it either.
    """
    without_hidden = client.post(RESOLVE, json={"query": SENTENCE, "spec_fallback": True}).json()
    matches = _spec_matches(without_hidden)
    assert matches, "the fixture sentence must actually rank by thickness today"
    assert matches[0]["display"]["specifications"].get("thickness") == 1.2
    assert "thick" in matches[0]["display"]["product_name"].lower()

    with_hidden = client.post(
        RESOLVE,
        json={"query": SENTENCE, "spec_fallback": True, "hidden_spec_keys": ["thickness"]},
    ).json()
    hidden_matches = _spec_matches(with_hidden)
    assert hidden_matches, "hiding thickness must not empty the candidate list"
    for match in hidden_matches:
        assert "thickness" not in match["display"]["specifications"]
        assert "thickness" not in (match["display"].get("matched_specs") or [])
        product_name = match["display"]["product_name"].lower()
        assert "thick" not in product_name
        assert "1.2" not in product_name


def test_resolve_spec_fallback_resolves_hidden_keys_server_side_from_contact(client, db):
    """Security review B/S2: a caller that sends `contact_id` (+ `space_id`) but
    NO `hidden_spec_keys` at all must not leak a key that contact's OWN policy
    hides - the route resolves the policy itself (`resolve_policy` +
    `hidden_keys`, the same pair `check_access` uses) rather than trusting only
    a caller-supplied list. Keeps the existing caller-supplied-list test above
    unchanged: that path still narrows further, it just is not the only one."""
    from app.models.access import RespondContact

    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+60{uuid.uuid4().int % 10**9:09d}",
        name="ZZT Contact",
    )
    db.add(contact)
    db.flush()
    db.execute(
        sa_text(
            "INSERT INTO spec_visibility_policies (id, contact_id, spec_keys, excluded_spec_keys) "
            "VALUES (gen_random_uuid(), :cid, NULL, ARRAY['thickness'])"
        ),
        {"cid": contact.id},
    )
    db.commit()

    body = client.post(
        RESOLVE,
        json={"query": SENTENCE, "spec_fallback": True, "contact_id": contact.id},
    ).json()

    matches = _spec_matches(body)
    assert matches, "hiding thickness server-side must not empty the candidate list"
    for match in matches:
        assert "thickness" not in match["display"]["specifications"]
        assert "thickness" not in (match["display"].get("matched_specs") or [])
