"""``entity_pins``: a caller that already disambiguated a token by uuid keeps that pick.

Codes are unique only PER COMPANY (LESSONS section 61c). Real incidents this closes:

- n8n exec 14659385 - the parser resolved the customer picker's pick to a uuid
  (`060f4eaf-...`), but `resolve-entity` re-derived customer code `300-C043`
  from the bare code, matching Mocha AND Sorento again - the ambiguity the
  customer had just closed reopened as a merged multi-company reply.
- n8n exec 14661446 - the identical class on a product code (`SRTBV110-DIY`):
  two companies both hold that exact code.

See sorento_crm_n8n/n8n-workflows-init/tests/diffs/rs-9-triage.md sections F5
and F7 (read-only evidence doc, not part of this repo).

Contract (`app/services/entity_resolver.py`): ``entity_pins`` (token -> uuid)
narrows that token's resolution to exactly the pinned row, checked against the
token's own SCOPED matches (run AFTER `_apply_company_scope`). ONE failure
mode, always `EntityPinMismatch` -> 400 `ENTITY_PIN_MISMATCH`: a bogus uuid, a
real uuid the caller's own company scope cannot see, a blank pin value, an
unparseable uuid, and an `entity_pins` key that binds to no token at all are
all the SAME error - never a silent misresolution, never a silent fallback to
plain token matching, and never a way to learn "this uuid exists somewhere I
can't see" from a 200.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.models.base import set_company_scope
from app.models.company import Company
from app.models.order import Customer
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.services.entity_resolver import EntityPinMismatch, resolve_references

from ._pg_fixture import blank_session, unique_code

MOCHA_ID = "00000000-0000-0000-0000-000000000002"
# Same shape as the real incident: one customer code, two companies.
SHARED_CODE = "300-C043"


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


@pytest.fixture
def db():
    with blank_session() as session:
        # pg_trgm lives in `public`; the trgm "did you mean" fallback probes it
        # even when the exact tier already answered, so it needs to be reachable
        # or those probes error out (best-effort, but noisy and pointless here).
        current = session.execute(text("SHOW search_path")).scalar()
        session.execute(text(f"SET LOCAL search_path TO {current}, public"))
        set_company_scope(session, None)
        session.add(Company(id=MOCHA_ID, name="Mocha", code=unique_code("MCH")[:20]))
        session.flush()
        yield session


def _customer(db, *, company_id: str, name: str) -> str:
    cid = str(uuid.uuid4())
    db.add(
        Customer(
            id=cid,
            customer_code=SHARED_CODE,
            customer_name=name,
            company_id=company_id,
            is_active=True,
        )
    )
    db.flush()
    return cid


def _seed_two_companies(db) -> tuple[str, str]:
    """Same code, seeded into both Sorento and Mocha - the incident's exact shape."""
    sorento_id = _customer(db, company_id=DEFAULT_COMPANY_ID, name="Sorento Customer")
    mocha_id = _customer(db, company_id=MOCHA_ID, name="Mocha Customer")
    db.commit()
    return sorento_id, mocha_id


def _resolution(result, token: str):
    for tr in result.resolutions:
        if tr.token.upper() == token.upper():
            return tr
    return None


def _product_refs(db):
    if not hasattr(db, "_refs"):
        cat, uom = str(uuid.uuid4()), str(uuid.uuid4())
        db.add(ProductCategory(id=cat, category_code=unique_code("C")[:50], category_name="C"))
        db.add(UnitOfMeasure(id=uom, uom_code=unique_code("U")[:20], uom_name="Each"))
        db.flush()
        db._refs = (cat, uom)
    return db._refs


def _product(db, *, code: str, company_id: str) -> str:
    cat, uom = _product_refs(db)
    pid = str(uuid.uuid4())
    db.add(
        Product(
            id=pid, product_code=code, product_name=code, category_id=cat,
            base_uom_id=uom, list_price=10, is_active=True, company_id=company_id,
        )
    )
    db.flush()
    return pid


# --------------------------------------------------------------------------- #
# Schema round-trip (no `response_model` on this route, but the request field
# itself has to survive Pydantic parsing to reach the resolver at all)
# --------------------------------------------------------------------------- #
def test_entity_pins_round_trips_through_the_request_schema():
    from app.api.v1.system.references import ResolveReferenceRequest

    req = ResolveReferenceRequest(
        **{"tokens": [SHARED_CODE], "entity_pins": {SHARED_CODE: "abc-uuid"}}
    )
    assert req.entity_pins == {SHARED_CODE: "abc-uuid"}


def test_entity_pins_defaults_to_none():
    from app.api.v1.system.references import ResolveReferenceRequest

    req = ResolveReferenceRequest(**{"query": "x"})
    assert req.entity_pins is None


# --------------------------------------------------------------------------- #
# (b) baseline - absent pin is byte-identical to today
# --------------------------------------------------------------------------- #
def test_without_a_pin_the_shared_code_still_matches_both_companies(db):
    """Today's shape, unchanged by this feature: the resolver itself does not
    flag a Tier-1 exact multi-company hit `ambiguous` (that flag is reserved
    for Tier-2/3 fuzzy ambiguity and duplicate-scheme certificates) - it simply
    returns every company's row, which is exactly how the incident reopened:
    a caller reading only the first match silently picks whichever company's
    row Postgres returned first. Pinning (test below) is what closes it."""
    _seed_two_companies(db)
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}))

    result = resolve_references(db, [SHARED_CODE], allowed_entity_types=["customer"])
    tr = _resolution(result, SHARED_CODE)

    assert tr is not None
    assert len(tr.matches) == 2, "the exact incident shape: both companies match"
    assert {m.company_name for m in tr.matches} == {"Sorento", "Mocha"}


# --------------------------------------------------------------------------- #
# (a) a pin narrows a two-company match to exactly the pinned record
# --------------------------------------------------------------------------- #
def test_a_pin_narrows_a_two_company_match_to_exactly_the_pinned_row(db):
    sorento_id, _mocha_id = _seed_two_companies(db)
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}))

    result = resolve_references(
        db,
        [SHARED_CODE],
        allowed_entity_types=["customer"],
        entity_pins={SHARED_CODE: sorento_id},
    )
    tr = _resolution(result, SHARED_CODE)

    assert tr is not None
    assert [m.uuid for m in tr.matches] == [sorento_id]
    assert tr.ambiguous is False
    assert tr.resolved is True
    # Company scoping still applies normally to the single pinned match.
    assert tr.matches[0].company_id == DEFAULT_COMPANY_ID
    assert tr.matches[0].company_name == "Sorento"


def test_a_pin_for_the_other_companys_row_resolves_to_that_one_instead(db):
    """Symmetry check: the SAME request, pinned to Mocha's row instead, must
    resolve to Mocha's row - proves the narrowing follows the pin, not a fixed
    ordering / "first match wins" shortcut."""
    _sorento_id, mocha_id = _seed_two_companies(db)
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}))

    result = resolve_references(
        db,
        [SHARED_CODE],
        allowed_entity_types=["customer"],
        entity_pins={SHARED_CODE: mocha_id},
    )
    tr = _resolution(result, SHARED_CODE)

    assert tr is not None
    assert [m.uuid for m in tr.matches] == [mocha_id]
    assert tr.resolved is True
    assert tr.matches[0].company_name == "Mocha"


def test_a_pin_key_differing_in_case_and_whitespace_still_binds(db):
    """Key matching is case-insensitive on the stripped token - a caller that
    echoes the token back with different casing/whitespace must not lose the
    pin."""
    sorento_id, _mocha_id = _seed_two_companies(db)
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}))

    result = resolve_references(
        db,
        [SHARED_CODE],
        allowed_entity_types=["customer"],
        entity_pins={f"  {SHARED_CODE.lower()}  ": sorento_id},
    )
    tr = _resolution(result, SHARED_CODE)

    assert tr is not None
    assert [m.uuid for m in tr.matches] == [sorento_id]
    assert tr.resolved is True


def test_a_pin_on_a_tier_2_variant_expansion_match_narrows_to_it(db):
    """Product variant expansion (siblings like `-BL`/`-NEW`) surfaces as a
    Tier-2 prefix match beside the Tier-1 exact hit for the base code - the
    pin must be able to select EITHER row, not just a Tier-1 exact one (the
    deleted widened re-probe only ever checked Tier-1, which was wrong for
    exactly this shape)."""
    base_code = unique_code("BASE")
    variant_code = f"{base_code}-BL"
    base_id = _product(db, code=base_code, company_id=DEFAULT_COMPANY_ID)
    variant_id = _product(db, code=variant_code, company_id=DEFAULT_COMPANY_ID)
    db.commit()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))

    result = resolve_references(
        db,
        [base_code],
        allowed_entity_types=["product"],
        entity_pins={base_code: variant_id},
    )
    tr = _resolution(result, base_code)

    assert tr is not None
    assert [m.uuid for m in tr.matches] == [variant_id]
    assert tr.resolved is True
    assert base_id != variant_id


# --------------------------------------------------------------------------- #
# (c) a pin naming nothing the token resolved to -> explicit structured error
# --------------------------------------------------------------------------- #
def test_a_pin_mismatching_the_token_raises_entity_pin_mismatch(db):
    _seed_two_companies(db)
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}))
    bogus_uuid = str(uuid.uuid4())

    with pytest.raises(EntityPinMismatch) as exc_info:
        resolve_references(
            db,
            [SHARED_CODE],
            allowed_entity_types=["customer"],
            entity_pins={SHARED_CODE: bogus_uuid},
        )

    assert exc_info.value.token == SHARED_CODE
    assert exc_info.value.pinned_uuid == bogus_uuid


def test_an_unparseable_pin_value_raises(db):
    _seed_two_companies(db)
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}))

    with pytest.raises(EntityPinMismatch):
        resolve_references(
            db,
            [SHARED_CODE],
            allowed_entity_types=["customer"],
            entity_pins={SHARED_CODE: "not-a-uuid"},
        )


def test_a_blank_pin_value_raises_never_a_silent_skip(db):
    _seed_two_companies(db)
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}))

    with pytest.raises(EntityPinMismatch):
        resolve_references(
            db,
            [SHARED_CODE],
            allowed_entity_types=["customer"],
            entity_pins={SHARED_CODE: "   "},
        )


def test_an_entity_pins_key_binding_to_no_token_raises(db):
    """A key that does not correspond to ANY token in the request - a typo, a
    stale key from an earlier turn - must never be silently ignored."""
    _seed_two_companies(db)
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}))

    with pytest.raises(EntityPinMismatch) as exc_info:
        resolve_references(
            db,
            [SHARED_CODE],
            allowed_entity_types=["customer"],
            entity_pins={"NOT-THE-REQUESTED-TOKEN": str(uuid.uuid4())},
        )

    assert exc_info.value.token == "NOT-THE-REQUESTED-TOKEN"


def test_the_route_converts_a_pin_mismatch_into_an_explicit_400(db):
    """Same scenario, exercised through the endpoint's own conversion - the
    route must NEVER let a mismatch pass through as a silent empty/ambiguous
    result; consistent with the endpoint's existing error convention (a bare
    400, matching the pre-existing ``match_mode`` validation in the same
    module)."""
    from app.api.v1.system.references import ResolveReferenceRequest, resolve_reference_post

    _seed_two_companies(db)
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}))
    bogus_uuid = str(uuid.uuid4())

    payload = ResolveReferenceRequest(
        **{
            "tokens": [SHARED_CODE],
            "allowed_entity_types": ["customer"],
            "entity_pins": {SHARED_CODE: bogus_uuid},
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        resolve_reference_post(payload, current_user={}, db=db)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "ENTITY_PIN_MISMATCH"


# --------------------------------------------------------------------------- #
# (d) a pin for a real record the caller's own company scope cannot see is
# treated EXACTLY the same as a bogus pin - a 400, never a silent fail-close.
# --------------------------------------------------------------------------- #
def test_out_of_scope_pin_raises_same_as_bogus(db):
    sorento_id, mocha_id = _seed_two_companies(db)
    # Scope covers ONLY Sorento - Mocha's row (and its uuid) genuinely exists,
    # the caller simply cannot see it. Deliberately NOT distinguished from a
    # bogus uuid - see `EntityPinMismatch`'s docstring for why the widened
    # re-probe that used to tell them apart was removed.
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))

    with pytest.raises(EntityPinMismatch) as exc_info:
        resolve_references(
            db,
            [SHARED_CODE],
            allowed_entity_types=["customer"],
            entity_pins={SHARED_CODE: mocha_id},
        )

    assert exc_info.value.token == SHARED_CODE
    assert exc_info.value.pinned_uuid == mocha_id
    assert sorento_id != mocha_id


# --------------------------------------------------------------------------- #
# match_mode="and" + entity_pins -> 400 (AND-mode has no per-token view to
# pin, and the force_mode="or" retry would otherwise apply pins by surprise)
# --------------------------------------------------------------------------- #
def test_and_mode_with_entity_pins_is_rejected(db):
    from app.api.v1.system.references import _resolve_input

    with pytest.raises(HTTPException) as exc_info:
        _resolve_input(
            db,
            "",
            [SHARED_CODE],
            match_mode="and",
            entity_pins={SHARED_CODE: str(uuid.uuid4())},
        )

    assert exc_info.value.status_code == 400


# --------------------------------------------------------------------------- #
# fallback_to_all_types: a pinned token resolves in the primary pass; an
# UNRELATED unresolved token must still reach the per-token fallback re-probe
# without the already-consumed pin poisoning that second call.
# --------------------------------------------------------------------------- #
def test_fallback_to_all_types_does_not_choke_on_an_already_consumed_pin(db):
    from app.models.inventory import Warehouse

    from app.api.v1.system.references import _resolve_input

    sorento_id, _mocha_id = _seed_two_companies(db)
    wh_code = unique_code("WH")
    db.add(
        Warehouse(
            id=str(uuid.uuid4()), warehouse_code=wh_code, is_active=True,
            company_id=DEFAULT_COMPANY_ID,
        )
    )
    db.commit()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}))

    result = _resolve_input(
        db,
        "",
        [SHARED_CODE, wh_code],
        match_mode="or",
        allowed_entity_types=["customer"],
        fallback_to_all_types=True,
        entity_pins={SHARED_CODE: sorento_id},
    )

    by_token = {r["token"]: r for r in result.get("resolutions", [])}
    assert [m["uuid"] for m in by_token[SHARED_CODE]["matches"]] == [sorento_id]
    assert any(m["entity_type"] == "warehouse" for m in by_token[wh_code]["matches"])
    assert result.get("fallback_applied") is True
