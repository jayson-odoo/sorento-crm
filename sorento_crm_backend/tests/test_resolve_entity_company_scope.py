"""A resolve result never names another company's row - in matches OR alternatives.

The reported case: `/system/references/resolve?contact_id=..&space_id=..` for a
contact who belongs to Sorento only. The token `M2399-BL` came back
`resolved: false, matches: []` - correct, the Mocha row was hidden because the
exact probe is an ORM query and the `do_orm_execute` isolation filter saw it. But
`alternatives` then offered the Mocha product `M2399`, because the trigram tier is
raw `db.execute(text(...))` and the filter never fires on raw SQL. One request,
isolating on one tier and leaking on the next.

An alternative is an emitted row like any other: a suggestion the contact cannot
buy, price, or get a spec sheet for is a leak wearing a helpful hat. Same
boundary for `matches`, `alternatives` and the AND-mode `intersection`.

Second half of the same bug: attribution read the owner through the ORM, so an
out-of-scope row's `company_id` came back None - indistinguishable from a
legitimately shared row. `null` must mean shared, never "you should not be
seeing this".
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.base import UNSET, set_company_scope
from app.models.company import Company
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.services.entity_resolver import resolve_references, resolve_references_intersection

from ._pg_fixture import blank_session, unique_code

MOCHA_ID = "00000000-0000-0000-0000-000000000002"
# Real shape of the reported rows: a base code and its colour variant, both Mocha.
OWNED_CODE = "ZZT2399"
OWNED_VARIANT = "ZZT2399-BL"
# Close enough to trigram-match OWNED_CODE, and absent from every company.
MISSING_CODE = "ZZT2399-XL"


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


@pytest.fixture
def db():
    with blank_session() as session:
        # pg_trgm lives in `public`, and blank_session pins search_path to the
        # scratch schemas so raw-SQL probes hit scratch tables. Without `public`
        # on the path, `similarity()` / `%` raise, the trigram probe swallows the
        # error and returns [] - and an alternatives test would pass while
        # proving nothing.
        current = session.execute(text("SHOW search_path")).scalar()
        session.execute(text(f"SET LOCAL search_path TO {current}, public"))
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


def _product(db, *, code: str, company_id: str | None) -> str:
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


def _resolution(db, token: str):
    result = resolve_references(db, token, allowed_entity_types=["product"])
    for tr in result.resolutions:
        if tr.token.upper() == token.upper():
            return tr
    return result.resolutions[0] if result.resolutions else None


def _seed_mocha_pair(db) -> tuple[str, str]:
    base = _product(db, code=OWNED_CODE, company_id=MOCHA_ID)
    variant = _product(db, code=OWNED_VARIANT, company_id=MOCHA_ID)
    db.commit()
    return base, variant


# --------------------------------------------------------------------------- #
# Alternatives (the leak)
# --------------------------------------------------------------------------- #
def test_another_companys_product_is_not_offered_as_an_alternative(db):
    """The reported payload: Sorento-only contact, Mocha-only product, and the
    trigram tier suggested it anyway."""
    _seed_mocha_pair(db)
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))

    tr = _resolution(db, MISSING_CODE)

    assert tr is not None
    assert tr.matches == [], "exact tier leaked an out-of-scope row"
    assert tr.alternatives == [], (
        "trigram tier suggested a product the contact's company does not own: "
        f"{[a.canonical_code for a in tr.alternatives]}"
    )
    assert tr.resolved is False


def test_my_own_companys_product_is_still_offered(db):
    """Guard against over-blocking: the fix must not silence in-scope suggestions."""
    _product(db, code=OWNED_CODE, company_id=DEFAULT_COMPANY_ID)
    db.commit()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))

    tr = _resolution(db, MISSING_CODE)

    assert tr is not None
    assert [a.canonical_code for a in tr.alternatives] == [OWNED_CODE]
    assert tr.alternatives[0].company_name == "Sorento"


def test_a_multi_company_scope_sees_both(db):
    """Backward-compat for a contact who genuinely belongs to both companies."""
    _seed_mocha_pair(db)
    _product(db, code=OWNED_CODE + "-S", company_id=DEFAULT_COMPANY_ID)
    db.commit()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}))

    tr = _resolution(db, MISSING_CODE)

    assert tr is not None
    owners = {a.company_name for a in tr.alternatives}
    assert owners == {"Sorento", "Mocha"}, f"expected both companies, got {owners}"


def test_no_contact_identity_still_resolves_across_companies(db):
    """`scope is None` (X-API-Key with no contact params) keeps the legacy
    all-companies behaviour - the fix must not break n8n's existing calls."""
    _seed_mocha_pair(db)
    set_company_scope(db, None)

    tr = _resolution(db, MISSING_CODE)

    assert tr is not None
    assert {a.canonical_code for a in tr.alternatives} == {OWNED_CODE, OWNED_VARIANT}
    assert {a.company_name for a in tr.alternatives} == {"Mocha"}


def test_a_contact_with_no_company_membership_gets_nothing(db):
    """An empty frozenset is the fail-closed scope (contact matched, no company
    rows). It emptied the ORM tiers already; now it empties the raw ones too."""
    _seed_mocha_pair(db)
    set_company_scope(db, frozenset())

    tr = _resolution(db, MISSING_CODE)

    assert tr is not None
    assert tr.matches == []
    assert tr.alternatives == []


def test_an_unresolved_scope_gets_nothing(db):
    """UNSET means the request-entry resolver never ran. Fail closed."""
    _seed_mocha_pair(db)
    set_company_scope(db, UNSET)

    tr = _resolution(db, MISSING_CODE)

    assert tr is not None
    assert tr.matches == []
    assert tr.alternatives == []


# --------------------------------------------------------------------------- #
# Matches, ambiguity, AND-mode
# --------------------------------------------------------------------------- #
def test_an_exact_out_of_scope_match_is_absent_and_the_token_reads_unresolved(db):
    _seed_mocha_pair(db)
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))

    result = resolve_references(db, OWNED_VARIANT, allowed_entity_types=["product"])
    payload = result.as_dict()

    tr = next(t for t in payload["resolutions"] if t["token"].upper() == OWNED_VARIANT)
    assert tr["matches"] == []
    assert tr["alternatives"] == []
    assert tr["resolved"] is False
    assert OWNED_VARIANT in [t.upper() for t in payload["unresolved_tokens"]]


def test_dropping_a_candidate_clears_the_ambiguous_flag(db):
    """Same code in both companies is `ambiguous` under a two-company scope. Under
    a one-company scope one candidate survives, so the token is resolved - not
    'ambiguous' with a single option the agent then refuses to act on."""
    sorento_id = _product(db, code=OWNED_CODE, company_id=DEFAULT_COMPANY_ID)
    _product(db, code=OWNED_CODE, company_id=MOCHA_ID)
    db.commit()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))

    tr = _resolution(db, OWNED_CODE)

    assert tr is not None
    assert [m.uuid for m in tr.matches] == [sorento_id]
    assert tr.ambiguous is False
    assert tr.resolved is True


def test_and_mode_alternatives_are_scoped_too(db):
    """AND-mode probes are ORM (already filtered) but its `alternatives` come from
    the same raw trigram lookup, so they need the same gate."""
    _seed_mocha_pair(db)
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))

    result = resolve_references_intersection(
        db, [MISSING_CODE], allowed_entity_types=["product"]
    )

    assert result.intersection == []
    assert result.alternatives == []
    assert result.as_dict()["empty"] is True


# --------------------------------------------------------------------------- #
# Attribution honesty
# --------------------------------------------------------------------------- #
def test_a_null_company_id_means_shared_not_out_of_scope(db):
    """Attribution reads the owner with raw SQL so it bypasses the isolation
    filter. Read through the ORM instead, an out-of-scope row reports
    `company_id: null` and the caller mistakes a leak for a global product."""
    _seed_mocha_pair(db)
    set_company_scope(db, None)

    tr = _resolution(db, MISSING_CODE)

    assert tr is not None and tr.alternatives, "nothing to attribute"
    for alternative in tr.alternatives:
        assert alternative.company_id == MOCHA_ID
        assert alternative.company_name == "Mocha"


def test_every_emitted_product_row_names_its_company(db):
    """Products are an OWNED type: under any scope, an emitted product must carry
    an owner. A None here is the masking bug returning."""
    _product(db, code=OWNED_CODE, company_id=DEFAULT_COMPANY_ID)
    _product(db, code=OWNED_CODE + "-S", company_id=DEFAULT_COMPANY_ID)
    db.commit()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))

    result = resolve_references(db, MISSING_CODE, allowed_entity_types=["product"])

    emitted = [
        row
        for tr in result.resolutions
        for row in list(tr.matches) + list(tr.alternatives)
        if row.entity_type == "product"
    ]
    assert emitted, "no product rows emitted, nothing asserted"
    assert all(row.company_id == DEFAULT_COMPANY_ID for row in emitted)
