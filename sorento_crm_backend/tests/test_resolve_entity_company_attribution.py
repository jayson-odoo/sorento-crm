"""A resolved entity says which company it belongs to.

Why it exists: on this database EVERY Mocha product code is also a Sorento
product code (11,390 of them). A caller holding a multi-company scope therefore
gets two exact matches for one code and the resolver — correctly — reports
``ambiguous: true``. Without company attribution the caller can only offer the
user two identical-looking options ("MWCX8609-RL-S10" vs "MWCX8609-RL-S10"),
which is not a choice anyone can make.

With ``company_id`` / ``company_name`` on each match the caller can tell a REAL
ambiguity (two different products) from a cross-company duplicate (the same
product in each company) and decide for itself whether to prompt.

Attribution is additive: it must never change which rows resolve, only describe
them.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.base import set_company_scope
from app.models.company import Company
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.services.entity_resolver import resolve_references

from ._pg_fixture import blank_session, unique_code

MOCHA_ID = "00000000-0000-0000-0000-000000000002"
SHARED_CODE = "ZZTWC8609-RL-S10"


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


@pytest.fixture
def db():
    with blank_session() as session:
        set_company_scope(session, None)
        session.add(Company(id=MOCHA_ID, name="Mocha", code=unique_code("MCH")[:20]))
        session.flush()
        yield session


def _refs(db):
    if not hasattr(db, "_refs"):
        cat, uom = str(uuid.uuid4()), str(uuid.uuid4())
        db.add(ProductCategory(id=cat, category_code=unique_code("C")[:50], category_name="C"))
        db.add(UnitOfMeasure(id=uom, uom_code=unique_code("U")[:20], uom_name="Each"))
        db.flush()
        db._refs = (cat, uom)
    return db._refs


def _product(db, *, code: str, company_id: str) -> str:
    cat, uom = _refs(db)
    pid = str(uuid.uuid4())
    db.add(
        Product(
            id=pid, product_code=code, product_name=code, category_id=cat,
            base_uom_id=uom, list_price=10, is_active=True, company_id=company_id,
        )
    )
    db.flush()
    return pid


def _matches(db, token: str):
    result = resolve_references(db, token, allowed_entity_types=["product"])
    for tr in result.resolutions:
        if tr.token.upper() == token.upper():
            return tr
    return result.resolutions[0] if result.resolutions else None


def test_a_match_carries_its_owning_company(db):
    sorento_id = _product(db, code=SHARED_CODE, company_id=DEFAULT_COMPANY_ID)
    db.commit()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))

    tr = _matches(db, SHARED_CODE)

    assert tr is not None and tr.matches, "the product did not resolve at all"
    match = next(m for m in tr.matches if m.uuid == sorento_id)
    assert match.company_id == DEFAULT_COMPANY_ID
    assert match.company_name == "Sorento"


def test_a_cross_company_duplicate_is_distinguishable(db):
    """The reported case: one code, one row per company, ambiguous by count -
    but now separable, because each candidate names its company."""
    sorento_id = _product(db, code=SHARED_CODE, company_id=DEFAULT_COMPANY_ID)
    mocha_id = _product(db, code=SHARED_CODE, company_id=MOCHA_ID)
    db.commit()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}))

    tr = _matches(db, SHARED_CODE)

    assert tr is not None
    by_id = {m.uuid: m for m in tr.matches}
    assert {sorento_id, mocha_id} <= set(by_id), "both companies' rows should be visible"
    assert by_id[sorento_id].company_name == "Sorento"
    assert by_id[mocha_id].company_name == "Mocha"
    # The whole point: same code, same entity type, different company. A caller
    # can now collapse this instead of asking the user to pick between two
    # identical labels.
    assert by_id[sorento_id].canonical_code == by_id[mocha_id].canonical_code
    assert by_id[sorento_id].company_id != by_id[mocha_id].company_id


def test_attribution_does_not_change_what_resolves(db):
    """A single-company scope still sees exactly its own row - attribution
    describes the result, it must not widen or narrow it."""
    _product(db, code=SHARED_CODE, company_id=DEFAULT_COMPANY_ID)
    mocha_id = _product(db, code=SHARED_CODE, company_id=MOCHA_ID)
    db.commit()
    set_company_scope(db, frozenset({MOCHA_ID}))

    tr = _matches(db, SHARED_CODE)

    assert tr is not None
    assert [m.uuid for m in tr.matches] == [mocha_id], "scope leaked or narrowed"
    assert tr.matches[0].company_name == "Mocha"


def test_the_payload_exposes_the_company_fields(db):
    """as_dict is the n8n-facing contract - the keys must actually be in it."""
    _product(db, code=SHARED_CODE, company_id=DEFAULT_COMPANY_ID)
    db.commit()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))

    payload = resolve_references(
        db, SHARED_CODE, allowed_entity_types=["product"]
    ).as_dict()

    match = next(
        m for tr in payload["resolutions"] for m in tr["matches"]
        if m["canonical_code"] == SHARED_CODE
    )
    assert match["company_id"] == DEFAULT_COMPANY_ID
    assert match["company_name"] == "Sorento"
