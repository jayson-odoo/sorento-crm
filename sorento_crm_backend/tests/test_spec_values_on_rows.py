"""S4: rows carry their spec values, and matched_specs tells the truth.

Two surfaces, one vocabulary. A shortlist that cannot say WHY each product is
offered is a list of codes: the customer asked for 1.2mm and has no way to see
which row is the 1.2mm one. So every ranked row carries its own values, and the
products listing can be asked for the same block by name.

The honesty split is the other half. `matched_specs` was carrying two different
claims at once - keys the customer's own words earned, and keys a standing house
preference added on their behalf - so a renderer reading "matched: brand" could
not tell "you asked for Sorento" from "we like Sorento". They are separated here:
`matched_specs` is what the customer earned, `preferred_specs` is what the house
put there.

The n8n renderer builds against these exact names, so they are frozen:
`display.specifications`, `display.preferred_specs`, `spec_asked`,
`specifications.{values,rendered_text,sources}`.

Plan: documentation/plans/PLAN-spec-raw-text-search.md (S4).
"""
from __future__ import annotations

import re
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import ProductSpecRegistry
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_derivation import derive_for_code
from app.services.product_spec_registry import (
    active_registry,
    merged_allowed_values,
    merged_synonyms,
    seed_spec_registry,
)
from app.services.product_spec_search import SELF_SYNONYM_KEY
from tests._pg_fixture import blank_session

RESOLVE = "/api/v1/system/references/resolve"
PREVIEW = "/api/v1/master-data/product-specifications/preview-search"
PRODUCTS = "/api/v1/master-data/products/"
_USER = {"id": str(uuid.uuid4()), "email": "n8n@example.com"}
_REFS: dict = {}


def _product(db, code, description, *, derive: bool = True, brand_id=None):
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        description=description,
        category_id=_REFS["cat"],
        brand_id=brand_id,
        base_uom_id=_REFS["uom"],
        list_price=Decimal("1.00"),
    )
    db.add(row)
    db.flush()
    if derive:
        derive_for_code(db, code)
    return row


@pytest.fixture
def db():
    with blank_session() as s:
        cat = ProductCategory(id=str(uuid.uuid4()), category_code="SRT-KS", category_name="SRT-KS")
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-PCS", uom_name="Piece")
        sorento = Brand(id=str(uuid.uuid4()), brand_code="ZZT-SRT", brand_name="SORENTO")
        cabana = Brand(id=str(uuid.uuid4()), brand_code="ZZT-CB", brand_name="CABANA")
        s.add_all([cat, uom, sorento, cabana])
        s.flush()
        backfill_category_signals(s)
        seed_spec_registry(s)
        _REFS.update({"cat": cat.id, "uom": uom.id, "sorento": sorento.id})

        # The preview + products endpoints enforce a permission against the acting
        # user; a superadmin role short-circuits the check true.
        from app.models.user import User, UserRole, UserRoleAssignment

        role = UserRole(
            id=str(uuid.uuid4()),
            slug="superadmin",
            name="ZZT Superadmin",
            description="",
            is_protected=True,
            is_default=False,
        )
        user = User(id=_USER["id"], email=_USER["email"], name="ZZT N8N", status="ACTIVE")
        s.add_all([role, user])
        s.flush()
        s.add(UserRoleAssignment(user_id=user.id, role_id=role.id))
        s.flush()

        # Descriptions copied from the live catalogue's shapes: the dimension quad's
        # 4th number is the thickness, "DOUBLE BOWL" is stated in words.
        _product(
            s,
            "ZZTKS12",
            "SORENTO S/STEEL KITCHEN SINK DOUBLE BOWL (820X450X230X1.2MM)",
            brand_id=sorento.id,
        )
        _product(
            s,
            "ZZTKS10",
            "SORENTO S/STEEL KITCHEN SINK DOUBLE BOWL (820X450X230X1.0MM)",
            brand_id=sorento.id,
        )
        # Never derived, so it has no product_specifications row at all: the
        # products listing must say so out loud rather than omit the key.
        _product(s, "ZZTKSNO", "SORENTO KITCHEN SINK NO SPECS DERIVED", derive=False)
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


def _resolve_raw(client, sentence: str) -> dict:
    return client.post(RESOLVE, json={"query": sentence, "spec_fallback": True}).json()


def _spec_matches(body: dict) -> list[dict]:
    """The spec_search resolution's matches, in rank order."""
    for resolution in body.get("resolutions") or []:
        matches = [
            m for m in resolution.get("matches") or []
            if m.get("match_tier") == "spec_search"
        ]
        if matches:
            return matches
    return []


def _weight(db, spec_key: str, value: str, bonus: float) -> None:
    """Give one VALUE of one key a standing house preference."""
    row = (
        db.query(ProductSpecRegistry)
        .filter(ProductSpecRegistry.spec_key == spec_key)
        .one()
    )
    row.value_weights = {value: bonus}
    db.flush()


def _listing(client, **params) -> dict:
    response = client.get(PRODUCTS, params={"query": "ZZTKS", "limit": 50, **params})
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------- #
# surface 1: the ranked row carries its own values                              #
# --------------------------------------------------------------------------- #
def test_a_ranked_row_shows_what_it_is(client):
    body = _resolve_raw(client, "double bowl kitchen sink with thickness 1.2mm")
    top = _spec_matches(body)[0]
    specifications = top["display"]["specifications"]

    # A number stays a number: a renderer that has to parse "1.2" out of a string
    # cannot compare it, and cannot say "this one is thicker".
    assert specifications["thickness"] == 1.2
    assert isinstance(specifications["thickness"], (int, float))
    assert isinstance(specifications["thickness"], bool) is False
    assert isinstance(specifications["class"], str)
    assert "thickness" in top["display"]["matched_specs"]


def test_the_values_block_holds_values_only(client):
    body = _resolve_raw(client, "double bowl kitchen sink with thickness 1.2mm")
    specifications = _spec_matches(body)[0]["display"]["specifications"]

    # `free_terms` is a scoring pseudo-key. It names no property of the product,
    # so it belongs in matched_specs and nowhere near the values block.
    assert "free_terms" not in specifications
    # Values only: no evidence / provenance / unit blobs on this surface.
    for value in specifications.values():
        assert not isinstance(value, dict)


def test_the_preview_candidate_carries_the_same_block(client):
    sentence = "double bowl kitchen sink with thickness 1.2mm"
    via_resolve = _spec_matches(_resolve_raw(client, sentence))[0]["display"]["specifications"]
    via_preview = client.post(PREVIEW, json={"phrase": sentence, "understand": False}).json()
    assert via_preview["candidates"][0]["specifications"] == via_resolve


# --------------------------------------------------------------------------- #
# the honesty split: earned vs preferred                                        #
# --------------------------------------------------------------------------- #
def test_a_house_preference_is_never_reported_as_a_match(client, db):
    # Nobody said "stainless steel" in the sentence below; the house did.
    _weight(db, "material", "stainless_steel", 1.5)
    top = _spec_matches(_resolve_raw(client, "double bowl kitchen sink"))[0]

    assert "material" in top["display"]["preferred_specs"]
    assert "material" not in top["display"]["matched_specs"]


def test_the_customers_own_words_still_earn_their_key(client, db):
    # A stated brand is the customer's, not the house's: even with the same value
    # weighted, "sorento" is scored the ordinary way (S2 binds it from the brands
    # table) and lands in matched_specs, never in preferred_specs.
    _weight(db, "brand", "SORENTO", 1.5)
    top = _spec_matches(_resolve_raw(client, "sorento double bowl kitchen sink"))[0]

    assert "brand" in top["display"]["matched_specs"]
    assert "brand" not in top["display"]["preferred_specs"]


def test_a_preference_can_never_satisfy_what_was_asked(client, db):
    # The unmet computation reads matched_specs as the satisfied set. A preference
    # only applies to a key the customer did NOT state, so moving preference keys
    # out of matched_specs cannot change the unmet arithmetic - and a brand the
    # catalogue does not carry is still reported as unmet while SORENTO is
    # weighted on every row shown.
    _weight(db, "brand", "SORENTO", 1.5)
    body = _resolve_raw(client, "cabana double bowl kitchen sink")

    assert [entry["key"] for entry in body["spec_unmet"]] == ["brand"]


def test_the_ranker_names_what_was_asked_for(client, db):
    # `spec_asked` is the ranker's own reading of the sentence, emitted verbatim
    # so a renderer can say "you asked for 1.2mm" without re-parsing the text.
    _weight(db, "material", "stainless_steel", 1.5)
    body = _resolve_raw(client, "double bowl kitchen sink with thickness 1.2mm")
    asked = {entry["key"]: entry["value"] for entry in body["spec_asked"]}

    assert asked["thickness"] == 1.2
    # Both halves of the sentence the ranker resolved, values included.
    assert asked["bowl_count"] == 2
    # A house preference is not something the customer asked for.
    assert "material" not in asked
    # The CLASS is deliberately absent from the ask. "kitchen sink" reaches the
    # ranker as a free term, not as a spec entry, so `spec_asked` is exactly the
    # ranker's resolved ask - the same list the unmet arithmetic runs on. What
    # each row IS still reads off its own values block.
    assert "class" not in asked
    assert _spec_matches(body)[0]["display"]["specifications"]["class"]


# --------------------------------------------------------------------------- #
# surface 2: the products listing, opt-in                                       #
# --------------------------------------------------------------------------- #
def test_the_listing_is_unchanged_for_a_caller_that_does_not_ask(client):
    plain = client.get(PRODUCTS, params={"query": "ZZTKS", "limit": 50})
    opted_out = client.get(
        PRODUCTS, params={"query": "ZZTKS", "limit": 50, "include_specifications": "false"}
    )
    assert plain.status_code == 200, plain.text
    assert opted_out.text == plain.text
    assert "specifications" not in plain.text
    for row in plain.json()["data"]:
        assert "specifications" not in row


def test_asking_for_specifications_adds_them_to_every_row(client):
    rows = {row["product_code"]: row for row in _listing(client, include_specifications="true")["data"]}
    assert set(rows) == {"ZZTKS12", "ZZTKS10", "ZZTKSNO"}

    block = rows["ZZTKS12"]["specifications"]
    assert block["values"]["thickness"] == 1.2
    assert isinstance(block["rendered_text"], str) and block["rendered_text"]
    assert block["sources"]["thickness"] == "derived"


def test_the_row_keys_are_otherwise_untouched(client):
    plain = {row["product_code"]: row for row in _listing(client)["data"]}
    opted_in = {row["product_code"]: row for row in _listing(client, include_specifications="true")["data"]}

    for code, row in plain.items():
        assert set(opted_in[code]) - set(row) == {"specifications"}


def test_a_product_with_no_specs_says_so(client):
    rows = {row["product_code"]: row for row in _listing(client, include_specifications="true")["data"]}
    # Present and null, not absent: absence of data is a fact worth stating, and a
    # missing key reads to a renderer as a field it forgot to request.
    assert "specifications" in rows["ZZTKSNO"]
    assert rows["ZZTKSNO"]["specifications"] is None


# --------------------------------------------------------------------------- #
# the enum-token format pin                                                     #
# --------------------------------------------------------------------------- #
_TOKEN_RE = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*$")


def test_every_enum_token_is_lowercase_underscore_separated(db):
    """The n8n renderer humanises a token blind: underscore -> space, title case.

    That rule only holds while the underscore is ONLY ever a separator. A future
    value that needs a semantic underscore is a BREAKING change to the render
    contract and requires a cross-team ping, not a quiet seed edit.

    `class` is exempt (its values are category labels, "Kitchen Sink") and so is
    `brand` (display-cased brand names, "SORENTO").
    """
    exempt = {"class", "brand"}
    offenders: list[str] = []
    for row in active_registry(db):
        if row.spec_key in exempt:
            continue
        tokens = [
            value for value in merged_synonyms(row) if value != SELF_SYNONYM_KEY
        ] + [str(value) for value in merged_allowed_values(row)]
        offenders += [
            f"{row.spec_key}={token}" for token in tokens if not _TOKEN_RE.match(str(token))
        ]

    assert offenders == []
