"""Route-level tests for PR 2's spec-registry surface.

What is under test here is the part a service test structurally cannot reach:

1. **The two relaxations** (AC-A.13). `keys-for-product` and `{spec_key}/products` are
   asked BY THE PRODUCT PAGE, and both sat behind `master_data.spec_registry.view`,
   which is granted to zero roles. A merchandiser holding `master_data.products.view`
   must be able to call them; the precedent and its written reasoning already exist on
   `GET /spec-registry`.
2. **The duplicate guards are the SERVER'S** (D11, AC-A.10, AC-A.11). The dialog's
   check is a latency courtesy; these assert that a client which skips it is refused,
   and that there is no way to ask to be let past.
3. **The split-by-field PATCH permission.** Adding a word to a key's vocabulary from
   the product page is a merchandiser's job; retuning `rank_weight` is not. One route
   serves both, so the check has to be on the FIELDS, not on the route.
5. **Adding one word appends.** `POST {spec_key}/values` takes the word alone, so a
   client cannot hand back a list it read before somebody else added to it.
4. **Static paths beat parametric ones.** `/applicable-keys` and `/similar` sit on a
   router that already declares `GET /{spec_key}/products`; declared in the wrong
   order they would be read as a spec key forever.

Auth-override pattern from `test_brochure_image_routes.py`.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from tests._pg_fixture import blank_session

_MERCHANDISER = "5c28d9f3-7e6a-5b41-a095-2d3f8c1e4b76"
_MERCH_ROLE = "1b6e4a83-8d92-5f57-c3e1-9a2b7d5f0c84"
_REGISTRY_ADMIN = "7d39ea04-9f7b-5c62-b1a6-3e4a9d2f5c87"
_ADMIN_ROLE = "2c7f5b94-9ea3-5068-d4f2-0b3c8e6a1d95"
_OUTSIDER = "8e4afb15-0a8c-5d73-c2b7-4f5b0e3a6d98"
_SORENTO = "00000000-0000-0000-0000-000000000001"

_BASE = "/api/v1/master-data/spec-registry"

# The merchandiser holds ONLY the product permissions. That is the whole point: every
# assertion below about them reaching a registry read is an assertion about the
# relaxation, not about a grant the test quietly handed out.
_MERCH_SLUGS = ("master_data.products.view", "master_data.products.edit")
_ADMIN_SLUGS = (
    "master_data.spec_registry.view",
    "master_data.spec_registry.edit",
    "master_data.spec_registry.add",
)


def _grant(db: Session, role_id: str, slugs) -> None:
    from app.models.user import UserPermission, UserRolePermission

    for slug in slugs:
        existing = db.query(UserPermission).filter_by(slug=slug).first()
        if existing is None:
            existing = UserPermission(id=str(uuid.uuid4()), slug=slug, name=slug, description="")
            db.add(existing)
            db.flush()
        db.add(
            UserRolePermission(
                id=str(uuid.uuid4()), role_id=role_id, permission_id=existing.id
            )
        )


def _seed(db: Session) -> None:
    from app.models.user import User, UserRole, UserRoleAssignment

    for role_id, slug, name in (
        (_MERCH_ROLE, "zzt_spec_merchandiser", "ZZT Spec Merchandiser"),
        (_ADMIN_ROLE, "zzt_spec_registry_admin", "ZZT Spec Registry Admin"),
    ):
        db.add(
            UserRole(
                id=role_id,
                slug=slug,
                name=name,
                description="",
                is_protected=False,
                is_default=False,
            )
        )
    db.add(User(id=_MERCHANDISER, email="zzt-merch@test.com", name="Merch", status="ACTIVE"))
    db.add(User(id=_REGISTRY_ADMIN, email="zzt-regadmin@test.com", name="Reg", status="ACTIVE"))
    db.add(User(id=_OUTSIDER, email="zzt-outsider@test.com", name="Out", status="ACTIVE"))
    db.flush()

    db.add(UserRoleAssignment(user_id=_MERCHANDISER, role_id=_MERCH_ROLE))
    db.add(UserRoleAssignment(user_id=_REGISTRY_ADMIN, role_id=_ADMIN_ROLE))
    _grant(db, _MERCH_ROLE, _MERCH_SLUGS)
    _grant(db, _ADMIN_ROLE, _ADMIN_SLUGS)
    db.commit()


def _key(db: Session, spec_key: str, **kwargs):
    from app.models.product_spec import ProductSpecRegistry

    row = ProductSpecRegistry(
        spec_key=spec_key,
        label=kwargs.pop("label", spec_key.replace("_", " ").title()),
        data_type=kwargs.pop("data_type", "text"),
        unit=kwargs.pop("unit", None),
        allowed_values=kwargs.pop("allowed_values", []),
        synonyms=kwargs.pop("synonyms", {}),
        user_synonyms=kwargs.pop("user_synonyms", {}),
        user_values=kwargs.pop("user_values", []),
        applies_when=kwargs.pop("applies_when", {}),
        is_active=kwargs.pop("is_active", True),
        source=kwargs.pop("source", "user"),
        **kwargs,
    )
    db.add(row)
    db.flush()
    return row


def _product(db: Session, code: str | None = None):
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    stem = f"ZZTSR{uuid.uuid4().hex[:6]}"
    category = ProductCategory(category_code=stem, category_name=f"ZZT cat {stem}")
    uom = UnitOfMeasure(uom_code=stem[:20], uom_name=f"ZZT uom {stem}")
    db.add_all([category, uom])
    db.flush()
    product = Product(
        product_code=code or stem,
        product_name=f"ZZT product {stem}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("10.00"),
        company_id=_SORENTO,
    )
    db.add(product)
    db.flush()
    return product


def _spec(db: Session, product, values, provenance=None):
    from app.models.product_spec import ProductSpecifications

    row = ProductSpecifications(
        product_id=product.id,
        values=values,
        provenance=provenance or {},
        status="derived",
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def api():
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        _seed(db)

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db

        async def _override_scope():
            scope = frozenset({_SORENTO})
            set_company_scope(db, scope)
            return scope

        app.dependency_overrides[apply_company_scope] = _override_scope

        def _as(user_id: str):
            principal = {"id": user_id, "email": f"{user_id}@test.com"}
            app.dependency_overrides[get_current_user] = lambda: principal
            app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        yield db, _as

        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# AC-A.7 - the applicable-keys read
# --------------------------------------------------------------------------- #
def test_applicable_keys_is_reachable_with_only_products_view(api):
    db, _as = api
    _as(_MERCHANDISER)
    client = TestClient(app)
    _key(db, "zzt_finish", allowed_values=["chrome"])
    product = _product(db)

    response = client.get(f"{_BASE}/applicable-keys", params={"code": product.product_code})
    assert response.status_code == 200, response.text
    keys = {row["spec_key"]: row for row in response.json()["keys"]}
    assert keys["zzt_finish"]["applicable"] is True
    assert keys["zzt_finish"]["held"] is False


def test_applicable_keys_is_a_static_path_not_a_spec_key(api):
    """Declared after `GET /{spec_key}/products` it would 404 forever."""
    db, _as = api
    _as(_MERCHANDISER)
    client = TestClient(app)
    product = _product(db)

    response = client.get(f"{_BASE}/applicable-keys", params={"code": product.product_code})
    assert response.status_code == 200, response.text


def test_applicable_keys_refuses_a_caller_with_nothing(api):
    db, _as = api
    _as(_OUTSIDER)
    client = TestClient(app)
    product = _product(db)

    assert (
        client.get(f"{_BASE}/applicable-keys", params={"code": product.product_code}).status_code
        == 403
    )


def test_applicable_keys_404s_an_unknown_code(api):
    db, _as = api
    _as(_MERCHANDISER)
    client = TestClient(app)

    response = client.get(f"{_BASE}/applicable-keys", params={"code": "ZZT-NO-SUCH-CODE"})
    assert response.status_code == 404, response.text


# --------------------------------------------------------------------------- #
# AC-A.13 - the two relaxations
# --------------------------------------------------------------------------- #
def test_keys_for_product_is_reachable_with_only_products_view(api):
    db, _as = api
    _as(_MERCHANDISER)
    client = TestClient(app)
    product = _product(db)
    _spec(db, product, {"zzt_finish": {"value": "chrome"}}, {"zzt_finish": {"source": "derived"}})

    response = client.get(f"{_BASE}/keys-for-product", params={"code": product.product_code})
    assert response.status_code == 200, response.text
    assert response.json()["keys"]["zzt_finish"]["value"] == "chrome"


def test_products_carrying_a_key_is_reachable_with_only_products_view(api):
    db, _as = api
    _as(_MERCHANDISER)
    client = TestClient(app)
    _key(db, "zzt_finish", allowed_values=["chrome"])
    product = _product(db)
    _spec(db, product, {"zzt_finish": {"value": "chrome"}}, {"zzt_finish": {"source": "derived"}})

    response = client.get(f"{_BASE}/zzt_finish/products")
    assert response.status_code == 200, response.text


def test_the_relaxed_reads_still_refuse_a_caller_with_nothing(api):
    """Relaxed is not open. A user holding neither slug is still refused."""
    db, _as = api
    _as(_OUTSIDER)
    client = TestClient(app)
    _key(db, "zzt_finish")
    product = _product(db)

    assert (
        client.get(f"{_BASE}/keys-for-product", params={"code": product.product_code}).status_code
        == 403
    )
    assert client.get(f"{_BASE}/zzt_finish/products").status_code == 403


def test_a_registry_admin_keeps_the_relaxed_reads(api):
    """The relaxation must widen the door, not move it."""
    db, _as = api
    _as(_REGISTRY_ADMIN)
    client = TestClient(app)
    product = _product(db)

    assert (
        client.get(f"{_BASE}/keys-for-product", params={"code": product.product_code}).status_code
        == 200
    )


# --------------------------------------------------------------------------- #
# AC-A.10 - the `similar` read and the server-side key guard
# --------------------------------------------------------------------------- #
def test_similar_finds_an_existing_key_by_label(api):
    db, _as = api
    _as(_MERCHANDISER)
    client = TestClient(app)
    _key(db, "zzt_finish", label="Finish or colour")

    body = client.get(f"{_BASE}/similar", params={"label": "finish  or  COLOUR"}).json()
    assert body["match"]["spec_key"] == "zzt_finish"
    assert body["match"]["matched_on"] == "label"


def test_similar_finds_an_existing_key_by_synonym(api):
    db, _as = api
    _as(_MERCHANDISER)
    client = TestClient(app)
    _key(db, "zzt_finish", label="Finish", user_synonyms={"chrome": ["surface colour"]})

    body = client.get(f"{_BASE}/similar", params={"label": "Surface Colour"}).json()
    assert body["match"]["spec_key"] == "zzt_finish"
    assert body["match"]["matched_on"] == "synonym"


def test_similar_reports_nothing_for_a_new_word(api):
    db, _as = api
    _as(_MERCHANDISER)
    client = TestClient(app)
    _key(db, "zzt_finish", label="Finish")

    assert client.get(f"{_BASE}/similar", params={"label": "Seat hinge type"}).json()["match"] is None


def test_creating_a_near_duplicate_key_is_refused_server_side(api):
    """The dialog's check is a courtesy; another client must not walk past it."""
    db, _as = api
    _as(_REGISTRY_ADMIN)
    client = TestClient(app)
    _key(db, "zzt_finish", label="Finish or colour")

    response = client.post(
        _BASE,
        json={
            "spec_key": "zzt_finish_or_colour",
            "label": "Finish Or Colour",
            # `enum` with an empty vocabulary: the create dialog makes the KEY, and the
            # words arrive afterwards through the add-a-value flow, which is the path
            # AC-A.11 describes.
            "data_type": "enum",
            "allowed_values": [],
        },
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["match"]["spec_key"] == "zzt_finish"


def test_a_near_duplicate_key_cannot_be_acknowledged_past(api):
    """The refusal is the product answer, not a speed bump: two names for one thing
    leave a registry that answers half of every customer question each. A client that
    asks to override is refused exactly as one that does not."""
    db, _as = api
    _as(_REGISTRY_ADMIN)
    client = TestClient(app)
    _key(db, "zzt_finish", label="Finish or colour")

    response = client.post(
        _BASE,
        json={
            "spec_key": "zzt_finish_or_colour",
            "label": "Finish Or Colour",
            "data_type": "enum",
            "allowed_values": [],
            "acknowledge_similar": True,
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["match"]["spec_key"] == "zzt_finish"
    assert "acknowledge_field" not in response.json()


def test_a_genuinely_new_key_is_created(api):
    db, _as = api
    _as(_REGISTRY_ADMIN)
    client = TestClient(app)
    _key(db, "zzt_finish", label="Finish")

    response = client.post(
        _BASE,
        json={
            "spec_key": "zzt_seat_hinge",
            "label": "Seat hinge type",
            "data_type": "enum",
            "allowed_values": [],
        },
    )
    assert response.status_code == 201, response.text


# --------------------------------------------------------------------------- #
# AC-A.11 / D11 - the value guard, and the split-by-field permission
# --------------------------------------------------------------------------- #
def test_adding_a_near_duplicate_value_is_refused_server_side(api):
    db, _as = api
    _as(_MERCHANDISER)
    client = TestClient(app)
    _key(db, "zzt_finish", allowed_values=["brushed_brass"], source="user")

    response = client.patch(f"{_BASE}/zzt_finish", json={"user_values": ["Brushed Brass"]})
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["match"]["value"] == "brushed_brass"


def test_a_value_colliding_with_a_synonym_is_refused_too(api):
    """`matte black` is a WORD for `black`; as a value of its own nothing matches it."""
    db, _as = api
    _as(_MERCHANDISER)
    client = TestClient(app)
    _key(db, "zzt_finish", allowed_values=["black"], synonyms={"black": ["matte black"]})

    response = client.patch(f"{_BASE}/zzt_finish", json={"user_values": ["Matte Black"]})
    assert response.status_code == 422, response.text
    assert response.json()["match"]["value"] == "black"


def test_a_near_duplicate_value_cannot_be_acknowledged_past(api):
    """`matte black` as a value of its own is a value nothing can ever match. Asking
    to add it anyway does not make it matchable, so there is no way to ask."""
    db, _as = api
    _as(_MERCHANDISER)
    client = TestClient(app)
    _key(db, "zzt_finish", allowed_values=["brushed_brass"], source="user")

    response = client.patch(
        f"{_BASE}/zzt_finish",
        json={"user_values": ["Brushed Brass"], "acknowledge_similar": True},
    )
    assert response.status_code == 422, response.text
    assert response.json()["match"]["value"] == "brushed_brass"


def test_a_new_value_is_added(api):
    db, _as = api
    _as(_MERCHANDISER)
    client = TestClient(app)
    _key(db, "zzt_finish", allowed_values=["chrome"], source="user")

    response = client.patch(f"{_BASE}/zzt_finish", json={"user_values": ["brushed_brass"]})
    assert response.status_code == 200, response.text
    assert "brushed_brass" in response.json()["user_values"]


def test_resending_the_vocabulary_with_one_new_word_goes_through(api):
    """PATCH replaces `user_values`, so the FE re-sends the full merged list plus the
    new word - the resent words must not refuse themselves as near-duplicates."""
    db, _as = api
    _as(_MERCHANDISER)
    client = TestClient(app)
    _key(
        db,
        "zzt_finish",
        allowed_values=["chrome", "black"],
        user_values=["gunmetal"],
        source="user",
    )

    response = client.patch(
        f"{_BASE}/zzt_finish",
        json={"user_values": ["chrome", "black", "gunmetal", "brushed_brass"]},
    )
    assert response.status_code == 200, response.text
    assert "brushed_brass" in response.json()["user_values"]
    assert "gunmetal" in response.json()["user_values"]


def test_a_resend_does_not_smuggle_a_near_duplicate_past_the_guard(api):
    db, _as = api
    _as(_MERCHANDISER)
    client = TestClient(app)
    _key(db, "zzt_finish", allowed_values=["chrome"], source="user")

    response = client.patch(
        f"{_BASE}/zzt_finish", json={"user_values": ["chrome", "Chrome"]}
    )
    assert response.status_code == 422, response.text
    assert response.json()["match"]["value"] == "chrome"


def test_two_spellings_of_one_new_word_in_a_single_payload_are_refused(api):
    """The guard compares each proposal against the ones accepted earlier in the same
    payload, not just the stored row - otherwise one PATCH carrying "Brushed Brass"
    and "brushed-brass" stores both and splits the vocabulary."""
    db, _as = api
    _as(_MERCHANDISER)
    client = TestClient(app)
    _key(db, "zzt_finish", allowed_values=["chrome"], source="user")

    response = client.patch(
        f"{_BASE}/zzt_finish",
        json={"user_values": ["Brushed Brass", "brushed-brass"]},
    )
    assert response.status_code == 422, response.text
    assert response.json()["match"]["value"] == "Brushed Brass"


def test_a_merchandiser_may_add_a_value_without_the_registry_edit_grant(api):
    """Journey A step 3. The merchandiser holds products.edit and nothing else."""
    db, _as = api
    _as(_MERCHANDISER)
    client = TestClient(app)
    _key(db, "zzt_finish", allowed_values=["chrome"], source="user")

    assert (
        client.patch(f"{_BASE}/zzt_finish", json={"user_values": ["brushed_brass"]}).status_code
        == 200
    )


def test_a_merchandiser_may_not_retune_the_ranker(api):
    """Adding a word is vocabulary; `rank_weight` is calibration against an eval
    baseline. One route serves both, so the check is on the fields."""
    db, _as = api
    _as(_MERCHANDISER)
    client = TestClient(app)
    _key(db, "zzt_finish", allowed_values=["chrome"], source="user")

    response = client.patch(f"{_BASE}/zzt_finish", json={"rank_weight": 9.0})
    assert response.status_code == 403, response.text


def test_a_mixed_payload_is_held_to_the_stricter_grant(api):
    """Otherwise `user_values` becomes a passenger seat for every other field."""
    db, _as = api
    _as(_MERCHANDISER)
    client = TestClient(app)
    _key(db, "zzt_finish", allowed_values=["chrome"], source="user")

    response = client.patch(
        f"{_BASE}/zzt_finish", json={"user_values": ["brushed_brass"], "rank_weight": 9.0}
    )
    assert response.status_code == 403, response.text


def test_a_registry_admin_may_still_retune_the_ranker(api):
    db, _as = api
    _as(_REGISTRY_ADMIN)
    client = TestClient(app)
    _key(db, "zzt_finish", allowed_values=["chrome"], source="user")

    assert client.patch(f"{_BASE}/zzt_finish", json={"rank_weight": 9.0}).status_code == 200


def test_an_outsider_may_not_patch_at_all(api):
    db, _as = api
    _as(_OUTSIDER)
    client = TestClient(app)
    _key(db, "zzt_finish", allowed_values=["chrome"], source="user")

    assert (
        client.patch(f"{_BASE}/zzt_finish", json={"user_values": ["brushed_brass"]}).status_code
        == 403
    )


# --------------------------------------------------------------------------- #
# Adding ONE word - append server-side, never a list rebuilt from a stale read
# --------------------------------------------------------------------------- #
def test_adding_a_word_does_not_drop_a_word_added_since_the_page_loaded(api):
    """The data-loss case. Two people add a word to the same key from two product
    pages; the second page's registry snapshot predates the first person's write.

    Under the replacing PATCH the second request carried the whole list as that stale
    snapshot knew it, so the first person's word was deleted by a request that was
    only ever meant to add. Sending the word alone is what makes that impossible.
    """
    db, _as = api
    _as(_MERCHANDISER)
    client = TestClient(app)
    _key(db, "zzt_finish", allowed_values=[], user_values=["chrome"], source="user")

    assert client.post(f"{_BASE}/zzt_finish/values", json={"value": "gunmetal"}).status_code == 200

    # B never read `gunmetal`: its snapshot is the one taken before A wrote. The API
    # gives it no way to send that snapshot back.
    response = client.post(f"{_BASE}/zzt_finish/values", json={"value": "brushed_brass"})
    assert response.status_code == 200, response.text

    values = response.json()["user_values"]
    assert values == ["chrome", "gunmetal", "brushed_brass"]


def test_adding_a_near_duplicate_word_is_refused_with_the_match(api):
    db, _as = api
    _as(_MERCHANDISER)
    client = TestClient(app)
    _key(db, "zzt_finish", allowed_values=["black"], synonyms={"black": ["matte black"]})

    response = client.post(f"{_BASE}/zzt_finish/values", json={"value": "Matte Black"})
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["match"]["value"] == "black"
    assert "acknowledge_field" not in body


def test_a_near_duplicate_word_cannot_be_acknowledged_past_on_the_add_route(api):
    db, _as = api
    _as(_MERCHANDISER)
    client = TestClient(app)
    _key(db, "zzt_finish", allowed_values=["brushed_brass"], source="user")

    response = client.post(
        f"{_BASE}/zzt_finish/values",
        json={"value": "Brushed Brass", "acknowledge_similar": True},
    )
    assert response.status_code == 422, response.text


def test_adding_a_word_the_key_already_holds_verbatim_is_a_no_op(api):
    """A double click is not an error, and it must not store the word twice."""
    db, _as = api
    _as(_MERCHANDISER)
    client = TestClient(app)
    _key(db, "zzt_finish", allowed_values=[], user_values=["chrome"], source="user")

    response = client.post(f"{_BASE}/zzt_finish/values", json={"value": "chrome"})
    assert response.status_code == 200, response.text
    assert response.json()["user_values"] == ["chrome"]


def test_a_shipped_word_is_never_copied_into_the_staff_list(api):
    """It ships; owning it twice would leave the seed repair re-asserting its half."""
    db, _as = api
    _as(_MERCHANDISER)
    client = TestClient(app)
    _key(db, "zzt_finish", allowed_values=["chrome"], source="seed")

    response = client.post(f"{_BASE}/zzt_finish/values", json={"value": "chrome"})
    assert response.status_code == 200, response.text
    assert response.json()["user_values"] == []


def test_a_word_an_administrator_took_away_is_refused_rather_than_silently_dropped(api):
    """A suppressed shipped value is in neither the merged vocabulary nor the guard's
    reach, so the add used to answer 200 and store nothing - and the follow-on save
    then failed with "add it to the specification first", naming the action the toast
    had just reported. It is also not this route's decision to reverse: suppression is
    a statement made on the key, and every holder of `products.edit` can reach here.
    """
    db, _as = api
    _as(_MERCHANDISER)
    client = TestClient(app)
    _key(
        db,
        "zzt_finish",
        label="Finish",
        allowed_values=["brushed_brass"],
        suppressed_values=["brushed_brass"],
        synonyms={},
        source="seed",
    )

    response = client.post(f"{_BASE}/zzt_finish/values", json={"value": "brushed_brass"})
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["match"]["value"] == "brushed_brass"
    assert "was taken off Finish" in body["error"]

    from app.models.product_spec import ProductSpecRegistry

    db.expire_all()
    row = db.query(ProductSpecRegistry).filter_by(spec_key="zzt_finish").first()
    assert row.suppressed_values == ["brushed_brass"]
    assert row.user_values == []
    assert "brushed_brass" not in (row.user_synonyms or {})


def test_a_word_of_a_suppressed_value_is_an_ordinary_new_word(api):
    """The words go with the value. `antique brass` belonged to a value an administrator
    took away, so nothing means it any more and it is added like any other new word -
    rather than being refused by naming a value the dropdown does not offer.
    """
    db, _as = api
    _as(_MERCHANDISER)
    client = TestClient(app)
    _key(
        db,
        "zzt_finish",
        label="Finish",
        allowed_values=["brushed_brass", "chrome"],
        synonyms={"brushed_brass": ["brushed brass", "antique brass"]},
        suppressed_values=["brushed_brass"],
        source="seed",
    )

    response = client.post(f"{_BASE}/zzt_finish/values", json={"value": "antique brass"})
    assert response.status_code == 200, response.text
    assert "antique brass" in response.json()["user_values"]


def test_the_registry_read_does_not_advertise_words_for_a_suppressed_value(api):
    """One vocabulary, two consumers: a value reported as not allowed must not arrive
    with words the ranker and the n8n parser would both go on matching."""
    db, _as = api
    _as(_MERCHANDISER)
    client = TestClient(app)
    _key(
        db,
        "zzt_finish",
        allowed_values=["brushed_brass", "chrome"],
        synonyms={"brushed_brass": ["antique brass"], "chrome": ["chrome"]},
        suppressed_values=["brushed_brass"],
        source="seed",
    )

    response = client.get(_BASE)
    assert response.status_code == 200, response.text
    key = next(k for k in response.json()["keys"] if k["spec_key"] == "zzt_finish")
    assert "brushed_brass" not in key["allowed_values"]
    assert "brushed_brass" not in key["synonyms"]
    assert key["synonyms"]["chrome"] == ["chrome"]


def test_a_merchandiser_may_add_a_word_without_the_registry_edit_grant(api):
    """Journey A step 3, on the route that now carries it."""
    db, _as = api
    _as(_MERCHANDISER)
    client = TestClient(app)
    _key(db, "zzt_finish", allowed_values=["chrome"], source="user")

    response = client.post(f"{_BASE}/zzt_finish/values", json={"value": "brushed_brass"})
    assert response.status_code == 200, response.text
    assert "brushed_brass" in response.json()["user_values"]


def test_an_outsider_may_not_add_a_word(api):
    db, _as = api
    _as(_OUTSIDER)
    client = TestClient(app)
    _key(db, "zzt_finish", allowed_values=["chrome"], source="user")

    assert (
        client.post(f"{_BASE}/zzt_finish/values", json={"value": "brushed_brass"}).status_code
        == 403
    )


def test_adding_a_word_to_an_unknown_key_is_a_404(api):
    _db, _as = api
    _as(_MERCHANDISER)
    client = TestClient(app)

    response = client.post(f"{_BASE}/zzt_no_such_key/values", json={"value": "chrome"})
    assert response.status_code == 404, response.text


def test_renaming_a_value_in_one_save_is_not_refused_as_its_own_synonym(api):
    """Take `floor_standing` away and add `free_standing` in the SAME save. `free standing`
    ships as a WORD for `floor_standing`, so the near-duplicate guard, run against the
    row as it was before the save, refused the rename as already meaning the value being
    removed. The guard has to see the suppressions the same payload carries.
    """
    db, _as = api
    _as(_REGISTRY_ADMIN)
    client = TestClient(app)
    _key(
        db,
        "zzt_mounting",
        label="Mounting",
        allowed_values=["floor_standing", "wall_hung"],
        synonyms={"floor_standing": ["floor standing", "free standing"]},
        source="seed",
    )

    response = client.patch(
        f"{_BASE}/zzt_mounting",
        json={
            "user_values": ["free_standing"],
            "suppressed_values": ["floor_standing"],
            "suppressed_synonyms": {"floor_standing": ["floor standing", "free standing"]},
            "user_synonyms": {"free_standing": ["floor standing", "free standing"]},
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "free_standing" in body["user_values"]
    assert "floor_standing" not in body["allowed_values"]
    assert body["synonyms"]["free_standing"] == ["floor standing", "free standing"]


# --------------------------------------------------------------------------- #
# AC-A.7 - a rule built from a sentence round trips through the save
#
# The editor compiles the sentence to `match`/`pattern`/`capture` in the browser and
# sends both halves. The server compiles it again and refuses a disagreement, so the
# pattern the engine runs is never something the screen did not say.
# --------------------------------------------------------------------------- #
def test_a_sentence_rule_is_compiled_server_side(api):
    db, _as = api
    _as(_REGISTRY_ADMIN)
    client = TestClient(app)
    _key(db, "zzt_length", label="Length", data_type="numeric", unit="mm")

    response = client.patch(
        f"{_BASE}/zzt_length",
        json={"derivation_rules": [{"builder": {"kind": "number_after", "word": "L"}}]},
    )

    assert response.status_code == 200, response.text
    rule = response.json()["derivation_rules"][0]
    assert rule["match"] == "regex"
    assert rule["pattern"] == r"\bL\s*(\d+(?:\.\d+)?)"
    assert rule["capture"] == 1
    assert rule["builder"] == {"kind": "number_after", "word": "L"}


def test_a_pattern_rule_without_a_sentence_stays_a_pattern_rule(api):
    db, _as = api
    _as(_REGISTRY_ADMIN)
    client = TestClient(app)
    _key(db, "zzt_length2", label="Length", data_type="numeric", unit="mm")

    response = client.patch(
        f"{_BASE}/zzt_length2",
        json={
            "derivation_rules": [
                {"match": "regex", "pattern": r"(\d+)\s*MM", "capture": 1}
            ]
        },
    )

    assert response.status_code == 200, response.text
    rule = response.json()["derivation_rules"][0]
    assert rule["pattern"] == r"(\d+)\s*MM"
    assert "builder" not in rule


def test_a_sentence_that_disagrees_with_its_pattern_is_refused(api):
    """The two compilers must agree or the row is a lie on one of the two screens."""
    db, _as = api
    _as(_REGISTRY_ADMIN)
    client = TestClient(app)
    _key(db, "zzt_length3", label="Length", data_type="numeric", unit="mm")

    response = client.patch(
        f"{_BASE}/zzt_length3",
        json={
            "derivation_rules": [
                {
                    "match": "regex",
                    "pattern": r"\bW\s*(\d+)",
                    "capture": 1,
                    "builder": {"kind": "number_after", "word": "L"},
                }
            ]
        },
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "spec_rule_builder_mismatch"


def test_a_stale_value_from_a_previous_kind_does_not_survive_a_kind_change(api):
    """B2: changing a rule's sentence kind - Text contains to Number after a word -
    used to leave the old kind's `value` sitting on the row, because only the FIELDS
    the sender happened to include were compared/merged. A save carrying `value` from
    the row's previous life, alongside a `number_after` builder that produces none,
    is accepted and the stale field is dropped rather than stored."""
    db, _as = api
    _as(_REGISTRY_ADMIN)
    client = TestClient(app)
    _key(db, "zzt_length5", label="Length", data_type="numeric", unit="mm")

    response = client.patch(
        f"{_BASE}/zzt_length5",
        json={
            "derivation_rules": [
                {
                    "builder": {"kind": "number_after", "word": "L"},
                    "match": "regex",
                    "pattern": r"\bL\s*(\d+(?:\.\d+)?)",
                    "capture": 1,
                    # Left over from when this row was `text_contains` - the compare
                    # must not 422 on it, and the merge must not keep it.
                    "value": "PP",
                }
            ]
        },
    )

    assert response.status_code == 200, response.text
    rule = response.json()["derivation_rules"][0]
    assert rule["match"] == "regex"
    assert rule["pattern"] == r"\bL\s*(\d+(?:\.\d+)?)"
    assert rule["capture"] == 1
    assert "value" not in rule


# --------------------------------------------------------------------------- #
# B3 - `from_field column:<name>` is refused off a text column
# --------------------------------------------------------------------------- #
def test_a_from_field_rule_naming_a_text_column_is_refused(api):
    db, _as = api
    _as(_REGISTRY_ADMIN)
    client = TestClient(app)
    _key(db, "zzt_length6", label="Length", data_type="numeric", unit="mm")

    response = client.patch(
        f"{_BASE}/zzt_length6",
        json={
            "derivation_rules": [
                {"match": "from_field", "pattern": "column:currency"}
            ]
        },
    )

    assert response.status_code == 400, response.text
    assert "Rule 1" in response.json()["message"]


def test_a_from_field_rule_naming_a_numeric_column_is_accepted(api):
    db, _as = api
    _as(_REGISTRY_ADMIN)
    client = TestClient(app)
    _key(db, "zzt_length7", label="Length", data_type="numeric", unit="mm")

    response = client.patch(
        f"{_BASE}/zzt_length7",
        json={
            "derivation_rules": [
                {"match": "from_field", "pattern": "column:weight"}
            ]
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["derivation_rules"][0]["pattern"] == "column:weight"


def test_the_ignore_above_value_round_trips(api):
    """AC-A.5 - `max_value` is editable, and blank means no cap."""
    db, _as = api
    _as(_REGISTRY_ADMIN)
    client = TestClient(app)
    _key(db, "zzt_length4", label="Length", data_type="numeric", unit="mm")

    response = client.patch(f"{_BASE}/zzt_length4", json={"max_value": 5000})
    assert response.status_code == 200, response.text
    assert response.json()["max_value"] == 5000.0

    # The list read is the product page's, so it runs on `master_data.products.view`.
    # A new column has to reach it too: `response_model` drops what it does not declare,
    # and a field the FE never sees is a field nobody can edit.
    _as(_MERCHANDISER)
    listed = client.get(_BASE).json()["keys"]
    assert {"zzt_length4": 5000.0}.items() <= {
        key["spec_key"]: key["max_value"] for key in listed
    }.items()
    _as(_REGISTRY_ADMIN)

    response = client.patch(f"{_BASE}/zzt_length4", json={"max_value": None})
    assert response.status_code == 200, response.text
    assert response.json()["max_value"] is None


def test_a_shipped_row_says_so_on_the_way_out(api):
    """The rows that ship carry a tag; the stored column never does."""
    db, _as = api
    _as(_MERCHANDISER)
    client = TestClient(app)
    _key(db, "dim_length", label="Length", data_type="numeric", unit="mm")

    listed = {key["spec_key"]: key for key in client.get(_BASE).json()["keys"]}
    effective = listed["dim_length"]["effective_rules"]

    assert effective, "the shipped rules are what this key actually runs"
    assert all(rule.get("shipped") is True for rule in effective)
    assert effective[0]["builder"] == {
        "kind": "from_field",
        "field": "column:dimensions_length",
    }
    assert listed["dim_length"]["derivation_rules"] == []


def test_saving_the_shipped_list_back_keeps_every_field_the_engine_reads(api):
    """Open Length, press Save, change nothing: the list must still read the same.

    The save path rebuilds each rule from the fields it knows, so a field it does not
    know is silently deleted. That is how the round/square condition would disappear off
    the size rows - and 407 would go back to being a length on every round basin - by
    somebody opening the screen and saving it untouched.
    """
    from app.services.product_spec_derivation import shipped_rules

    db, _as = api
    _as(_REGISTRY_ADMIN)
    client = TestClient(app)
    _key(db, "dim_length", label="Length", data_type="numeric", unit="mm")

    effective = [dict(rule, shipped=True) for rule in shipped_rules()["dim_length"]]
    response = client.patch(f"{_BASE}/dim_length", json={"derivation_rules": effective})

    assert response.status_code == 200, response.text
    saved = response.json()["derivation_rules"]
    assert len(saved) == len(effective)
    for stored, shipped in zip(saved, effective):
        for field in ("match", "pattern", "capture", "source", "applies_when", "unless"):
            assert stored.get(field) == shipped.get(field), field
        assert stored.get("builder") == shipped.get("builder")
        # The tag is the API's, not the database's: a saved list belongs to the business.
        assert "shipped" not in stored
