"""A placeholder product is not a chat answer, even when its exact code is typed.

The reported turn (n8n clone exec 13880388): "sorento black kitchen tap" answered
with the five real SRTKT taps PLUS `Company: Mocha, Product Code: SORENTO,
"DESCRIPTION WILL AMEND, FOR SORENTO AND CABANA ORDER OR SAMPLE USE ONLY"`. That
row is booked on real orders, so it has to stay `is_active`; the lever is a
separate flag, at two levels:

- `product_categories.is_searchable = False` (MISC, PROJECT, SRTPART, VD,
  ACC-AT ...): a category with no class meaning is never a chat answer. It
  already gated spec search; now it gates the code probes too.
- `products.is_searchable = False`: the same for one row in an otherwise
  searchable category (SORENTOBAG sits in SAMPLE).

Both are read through ONE predicate, `chat_searchable_products()`, by the exact,
prefix and AND-mode product probes and by `search_specs`. Both fail closed only
on an explicit False, so every searchable product's response is byte-identical.

Issue: jayson-odoo/sorento-crm#300.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.dependencies import (
    get_current_user,
    get_current_user_or_api_key,
    get_db,
    get_external_api_user,
)
from app.main import app
from app.models.base import set_company_scope
from app.models.company import Company
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.services.company_scope_resolver import apply_company_scope
from app.services.entity_resolver import resolve_references, resolve_references_intersection

from ._pg_fixture import blank_session, unique_code

SORENTO_ID = DEFAULT_COMPANY_ID
MOCHA_ID = "00000000-0000-0000-0000-000000000002"

# Distinctive stem so nothing real can collide with a prefix probe.
STEM = "ZZTSRC"


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


@pytest.fixture
def db():
    with blank_session() as session:
        # pg_trgm lives in `public`; the did-you-mean tier is best-effort and
        # swallows its own error, but a swallowed error is not the same as the
        # tier running. Same pin as test_resolve_entity_company_scope.
        current = session.execute(text("SHOW search_path")).scalar()
        session.execute(text(f"SET LOCAL search_path TO {current}, public"))
        set_company_scope(session, None)
        session.add(Company(id=MOCHA_ID, name="Mocha", code=unique_code("MCH")[:20]))
        session.flush()
        yield session


class _World:
    """Two categories and a UOM per test, created lazily on the session."""

    def __init__(self, db):
        self.db = db
        self.uom = str(uuid.uuid4())
        db.add(UnitOfMeasure(id=self.uom, uom_code=unique_code("U")[:20], uom_name="Each"))
        self.searchable_cat = self.category(searchable=True)
        self.junk_cat = self.category(searchable=False)
        db.flush()

    def category(self, *, searchable: bool, company_id: str | None = None) -> str:
        cid = str(uuid.uuid4())
        self.db.add(
            ProductCategory(
                id=cid,
                category_code=unique_code("C")[:50],
                category_name="C",
                is_searchable=searchable,
                **({"company_id": company_id} if company_id else {}),
            )
        )
        self.db.flush()
        return cid

    def product(
        self,
        code: str,
        *,
        searchable: bool = True,
        category: str | None = None,
        company_id: str = SORENTO_ID,
        name: str | None = None,
    ) -> str:
        pid = str(uuid.uuid4())
        self.db.add(
            Product(
                id=pid,
                product_code=code,
                product_name=name or code,
                category_id=category or self.searchable_cat,
                base_uom_id=self.uom,
                list_price=Decimal("10.00"),
                is_active=True,
                is_searchable=searchable,
                company_id=company_id,
            )
        )
        self.db.flush()
        return pid


@pytest.fixture
def world(db):
    w = _World(db)
    db.commit()
    return w


def _product_codes(matches) -> set[str]:
    return {m.canonical_code if hasattr(m, "canonical_code") else m["canonical_code"]
            for m in matches
            if (m.entity_type if hasattr(m, "entity_type") else m["entity_type"]) == "product"}


def _resolution(db, token: str):
    result = resolve_references(db, [token], allowed_entity_types=["product"])
    for tr in result.resolutions:
        if tr.token.upper() == token.upper():
            return tr
    raise AssertionError(f"no resolution for {token!r}: {result.resolutions}")


# --------------------------------------------------------------------------- #
# Exact tier                                                                  #
# --------------------------------------------------------------------------- #
def test_exact_code_of_a_product_flagged_not_searchable_does_not_resolve(world, db):
    """The whole point: a customer typing the placeholder's own code gets nothing."""
    code = f"{STEM}LONE"
    world.product(code, searchable=False)
    db.commit()
    set_company_scope(db, frozenset({SORENTO_ID}))

    tr = _resolution(db, code)

    assert tr.matches == [], tr.matches
    assert tr.resolved is False


def test_exact_code_of_a_product_in_a_non_searchable_category_does_not_resolve(world, db):
    """SORENTO188 sits in ACC-AT (is_searchable False). Zero data entry needed."""
    code = f"{STEM}188"
    world.product(code, category=world.junk_cat)
    db.commit()
    set_company_scope(db, frozenset({SORENTO_ID}))

    tr = _resolution(db, code)

    assert tr.matches == [], tr.matches


def test_a_searchable_product_still_resolves_exactly_as_before(world, db):
    """The filter must be invisible to every row it does not hide."""
    code = f"{STEM}KT71-BL"
    pid = world.product(code)
    db.commit()
    set_company_scope(db, frozenset({SORENTO_ID}))

    tr = _resolution(db, code)

    assert tr.resolved is True
    assert [m.uuid for m in tr.matches] == [pid]
    assert tr.matches[0].match_field == "product_code"
    assert tr.matches[0].display["product_name"] == code
    assert tr.matches[0].display["is_active"] is True


# --------------------------------------------------------------------------- #
# Prefix / substring tier                                                     #
# --------------------------------------------------------------------------- #
def test_prefix_tier_never_offers_a_hidden_row(world, db):
    """`sorento` prefix-matched SORENTO / SORENTOBAG / SORENTO188. The stem of a
    hidden row must not surface it, whether hidden by flag or by category."""
    world.product(f"{STEM}", searchable=False)
    world.product(f"{STEM}BAG", searchable=False)
    world.product(f"{STEM}188", category=world.junk_cat)
    visible = world.product(f"{STEM}KT71-BL")
    db.commit()
    set_company_scope(db, frozenset({SORENTO_ID}))

    tr = _resolution(db, STEM)

    assert [m.uuid for m in tr.matches] == [visible]
    assert tr.matches[0].match_tier == "prefix"


def test_prefix_tier_with_only_hidden_candidates_resolves_nothing(world, db):
    """No visible sibling to fall back on: the token is simply unresolved, it
    does not degrade to the substring tier and pull the hidden row back in."""
    world.product(f"{STEM}188", category=world.junk_cat)
    world.product(f"{STEM}1X", searchable=False)
    db.commit()
    set_company_scope(db, frozenset({SORENTO_ID}))

    tr = _resolution(db, f"{STEM}1")

    assert tr.matches == [], tr.matches


def test_variant_expansion_after_an_exact_hit_skips_hidden_siblings(world, db):
    """Tier 1 hit on the base code fans out to prefix siblings; a hidden sibling
    stays out of that fan-out too."""
    base = world.product(f"{STEM}KS6145")
    new = world.product(f"{STEM}KS6145-NEW")
    world.product(f"{STEM}KS6145-OLD", searchable=False)
    db.commit()
    set_company_scope(db, frozenset({SORENTO_ID}))

    tr = _resolution(db, f"{STEM}KS6145")

    assert {m.uuid for m in tr.matches} == {base, new}


# --------------------------------------------------------------------------- #
# AND mode                                                                    #
# --------------------------------------------------------------------------- #
def test_and_mode_intersection_and_by_entity_type_exclude_hidden_rows(world, db):
    world.product(f"{STEM}", searchable=False)
    world.product(f"{STEM}188", category=world.junk_cat)
    visible = world.product(f"{STEM}KT71-BL")
    db.commit()
    set_company_scope(db, frozenset({SORENTO_ID}))

    out = resolve_references_intersection(db, [STEM], allowed_entity_types=["product"]).as_dict()

    assert [m["uuid"] for m in out["intersection"]] == [visible]
    assert [m["uuid"] for m in out["by_entity_type"]["product"]] == [visible]
    assert out["empty"] is False


def test_and_mode_a_hidden_row_cannot_set_the_bar_the_visible_rows_must_reach(world, db):
    """AND keeps rows at each token's GLOBAL max match count. If the hidden row
    were counted, "BAG" would have a max of 1 that no visible row reaches - the
    filter has to sit on the base query, before the max is taken."""
    world.product(f"{STEM}BAG", searchable=False)
    world.product(f"{STEM}KT71-BL")
    db.commit()
    set_company_scope(db, frozenset({SORENTO_ID}))

    out = resolve_references_intersection(
        db, [STEM, "BAG"], allowed_entity_types=["product"]
    ).as_dict()

    assert out["intersection"] == []
    assert out["by_entity_type"] == {}
    assert out["empty"] is True


# --------------------------------------------------------------------------- #
# Two companies                                                               #
# --------------------------------------------------------------------------- #
def test_two_companies_the_flag_belongs_to_the_row_not_the_code(world, db):
    """Codes are unique PER COMPANY. Hiding Mocha's SORENTOBAG must not hide
    Sorento's, and Sorento's staying visible must not leak Mocha's back."""
    code = f"{STEM}DUAL"
    sorento_row = world.product(code, company_id=SORENTO_ID)
    world.product(code, company_id=MOCHA_ID, searchable=False)
    db.commit()

    set_company_scope(db, frozenset({SORENTO_ID, MOCHA_ID}))
    tr = _resolution(db, code)
    assert [m.uuid for m in tr.matches] == [sorento_row]
    assert tr.matches[0].company_id == SORENTO_ID

    set_company_scope(db, frozenset({MOCHA_ID}))
    assert _resolution(db, code).matches == []

    set_company_scope(db, frozenset({SORENTO_ID}))
    assert [m.uuid for m in _resolution(db, code).matches] == [sorento_row]

    # The same boundary on the prefix tier and in AND mode, under the dealer's
    # two-company scope: still exactly Sorento's row, never Mocha's.
    set_company_scope(db, frozenset({SORENTO_ID, MOCHA_ID}))
    assert [m.uuid for m in _resolution(db, f"{STEM}DU").matches] == [sorento_row]
    out = resolve_references_intersection(db, [code], allowed_entity_types=["product"]).as_dict()
    assert [m["uuid"] for m in out["intersection"]] == [sorento_row]
    assert [m["company_id"] for m in out["by_entity_type"]["product"]] == [SORENTO_ID]


def test_did_you_mean_never_offers_a_hidden_product(world, db):
    """The trigram tier is raw SQL and used to sit outside every ORM filter; a
    placeholder refused as a match must not come straight back as a suggestion."""
    world.product(f"{STEM}WC8088-HID", searchable=False)
    visible = world.product(f"{STEM}WC8088-OK")
    db.commit()
    set_company_scope(db, frozenset({SORENTO_ID}))

    # A typo (letter O for zero) that no exact / prefix / substring tier can
    # match, so the trigram alternatives are what answers.
    tr = _resolution(db, f"{STEM}WC8O88")
    assert tr.matches == [], tr.matches
    offered = {a.uuid for a in tr.alternatives}
    assert visible in offered, tr.alternatives
    assert len(offered) == 1, tr.alternatives


def test_the_category_rule_follows_the_foreign_key_not_the_company_scope(world, db):
    """498 live products point at a category row owned by the other company.
    Under a single-company scope that category row is invisible to an ORM read;
    the predicate must still see it, or the product slips back in."""
    mocha_junk = world.category(searchable=False, company_id=MOCHA_ID)
    world.product(f"{STEM}XCO", category=mocha_junk, company_id=SORENTO_ID)
    db.commit()
    set_company_scope(db, frozenset({SORENTO_ID}))

    assert _resolution(db, f"{STEM}XCO").matches == []


# --------------------------------------------------------------------------- #
# Spec search                                                                 #
# --------------------------------------------------------------------------- #
def test_search_specs_never_ranks_a_hidden_product(db):
    from app.services.product_class_signal import backfill_category_signals
    from app.services.product_spec_derivation import derive_for_code
    from app.services.product_spec_registry import seed_spec_registry
    from app.services.product_spec_search import search_specs

    ks = ProductCategory(id=str(uuid.uuid4()), category_code="SRT-KS", category_name="SRT-KS")
    misc = ProductCategory(id=str(uuid.uuid4()), category_code="MISC", category_name="MISC")
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-PCS", uom_name="Piece")
    db.add_all([ks, misc, uom])
    db.flush()
    backfill_category_signals(db)
    seed_spec_registry(db)
    # The class signal decides searchability from the code; pin the fact this
    # test depends on rather than trusting the decoder's opinion of "MISC".
    misc.is_searchable = False
    db.flush()

    description = "STAINLESS STEEL KITCHEN SINK DOUBLE BOWL 1.2MM"

    def product(code, *, category, searchable=True):
        db.add(
            Product(
                id=str(uuid.uuid4()),
                product_code=code,
                product_name=code,
                description=description,
                category_id=category.id,
                base_uom_id=uom.id,
                list_price=Decimal("1.00"),
                is_searchable=searchable,
            )
        )
        db.flush()
        derive_for_code(db, code)

    product(f"{STEM}KS-OK", category=ks)
    product(f"{STEM}KS-HIDDEN", category=ks, searchable=False)
    product(f"{STEM}KS-MISC", category=misc)
    db.commit()
    set_company_scope(db, frozenset({SORENTO_ID}))

    found = search_specs(db, free_terms=["stainless steel kitchen sink"])
    codes = {c["product_code"] for c in found["candidates"]}

    assert f"{STEM}KS-OK" in codes, found
    assert f"{STEM}KS-HIDDEN" not in codes
    assert f"{STEM}KS-MISC" not in codes


# --------------------------------------------------------------------------- #
# Routes                                                                      #
# --------------------------------------------------------------------------- #
@pytest.fixture
def api(db, world):
    def _override_get_db():
        yield db

    principal = {"id": str(uuid.uuid4()), "email": "zzt-is-searchable@test.com"}

    async def _override_scope():
        scope = frozenset({SORENTO_ID, MOCHA_ID})
        set_company_scope(db, scope)
        return scope

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = lambda: principal
    # The module guard on every router authenticates through this one.
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
    app.dependency_overrides[get_external_api_user] = lambda: principal
    app.dependency_overrides[apply_company_scope] = _override_scope
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def test_bulk_update_flips_the_flag_and_the_detail_reads_it_back(api, world, db):
    a = world.product(f"{STEM}BULK-A")
    b = world.product(f"{STEM}BULK-B")
    untouched = world.product(f"{STEM}BULK-C")
    db.commit()

    res = api.put(
        "/api/v1/master-data/products/bulk",
        json={"ids": [a, b], "updates": {"is_searchable": False}},
    )
    assert res.status_code == 200, res.text
    assert res.json()["updated_count"] == 2

    for pid, expected in ((a, False), (b, False), (untouched, True)):
        detail = api.get(f"/api/v1/master-data/products/{pid}")
        assert detail.status_code == 200, detail.text
        assert detail.json()["is_searchable"] is expected, pid
        # The category's own flag rides along, so the UI can say "hidden by
        # category" for a row whose product flag is still true.
        assert detail.json()["category"]["is_searchable"] is True

    # And back on again, through the same action.
    res = api.put(
        "/api/v1/master-data/products/bulk",
        json={"ids": [a], "updates": {"is_searchable": True}},
    )
    assert res.status_code == 200, res.text
    assert api.get(f"/api/v1/master-data/products/{a}").json()["is_searchable"] is True


def test_bulk_update_is_company_scoped(world, db):
    """An id from a company outside the caller's scope is not found, not written."""
    from app.schemas.product import ProductBulkUpdates
    from app.services.product_service import ProductService

    sorento_row = world.product(f"{STEM}SCOPE", company_id=SORENTO_ID)
    mocha_row = world.product(f"{STEM}SCOPE", company_id=MOCHA_ID)
    db.commit()
    set_company_scope(db, frozenset({SORENTO_ID}))

    out = ProductService(db).bulk_update_products(
        [sorento_row, mocha_row], ProductBulkUpdates(is_searchable=False), str(uuid.uuid4())
    )

    assert out["updated_count"] == 1
    set_company_scope(db, None)
    flags = {
        pid: flag
        for pid, flag in db.query(Product.id, Product.is_searchable)
        .filter(Product.id.in_([sorento_row, mocha_row]))
        .all()
    }
    assert flags == {sorento_row: False, mocha_row: True}


def test_single_product_update_accepts_the_flag(api, world, db):
    pid = world.product(f"{STEM}ONE")
    db.commit()

    res = api.put(f"/api/v1/master-data/products/{pid}", json={"is_searchable": False})
    assert res.status_code == 200, res.text
    assert res.json()["is_searchable"] is False

    listed = api.get("/api/v1/master-data/products/", params={"query": f"{STEM}ONE"})
    assert listed.status_code == 200, listed.text
    rows = {r["id"]: r for r in listed.json()["data"]}
    assert rows[pid]["is_searchable"] is False


def test_resolve_route_the_three_placeholders_no_longer_answer_sorento(api, world, db):
    """The acceptance call, end to end through POST /system/references/resolve,
    with the three named codes seeded the way they sit in the catalogue:
    SORENTO and SORENTOBAG flagged off by hand, SORENTO188 hidden by ACC-AT.
    Both companies in scope, as for the dealer contact who reported it."""
    for company in (SORENTO_ID, MOCHA_ID):
        world.product(
            "SORENTO",
            searchable=False,
            company_id=company,
            name="**DESCRIPTION WILL AMEND** FOR SORENTO AND CABANA ORDER OR SAMPLE USE ONLY",
        )
        world.product("SORENTOBAG", searchable=False, company_id=company)
        world.product("SORENTO188", category=world.junk_cat, company_id=company)
    real_tap = world.product(f"{STEM}KT71SS-BL", name="SORENTO BLACK KITCHEN TAP")
    db.commit()

    res = api.post(
        "/api/v1/system/references/resolve",
        json={
            "query": "sorento black kitchen tap",
            "tokens": ["sorento"],
            "allowed_entity_types": ["product"],
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()

    offered = {
        m["canonical_code"]
        for tr in body["resolutions"]
        for m in tr["matches"]
        if m["entity_type"] == "product"
    }
    assert offered.isdisjoint({"SORENTO", "SORENTOBAG", "SORENTO188"}), body
    assert "sorento" in body["unresolved_tokens"]

    # The real tap is untouched by all of this.
    res = api.post(
        "/api/v1/system/references/resolve",
        json={"query": f"{STEM}KT71SS-BL", "tokens": [f"{STEM}KT71SS-BL"], "allowed_entity_types": ["product"]},
    )
    assert res.status_code == 200, res.text
    assert [m["uuid"] for m in res.json()["resolutions"][0]["matches"]] == [real_tap]
