"""``entity_pins``: a caller that already disambiguated a token by uuid keeps that pick.

Codes are unique only PER COMPANY (LESSONS §61c). Real incidents this closes:

- n8n exec 14659385 - the parser resolved the customer picker's pick to a uuid
  (`060f4eaf-...`), but `resolve-entity` re-derived customer code `300-C043`
  from the bare code, matching Mocha AND Sorento again - the ambiguity the
  customer had just closed reopened as a merged multi-company reply.
- n8n exec 14661446 - the identical class on a product code (`SRTBV110-DIY`):
  two companies both hold that exact code.

See sorento_crm_n8n/n8n-workflows-init/tests/diffs/rs-9-triage.md sections F5
and F7 (read-only evidence doc, not part of this repo).

Fix (`app/services/entity_resolver.py::resolve_references`): an optional
``entity_pins`` mapping (token -> uuid) narrows that token's resolution to
exactly the pinned row, checked against the token's OWN candidate matches
before company-scope filtering runs.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.models.base import set_company_scope
from app.models.company import Company
from app.models.order import Customer
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
# (d) a pin for a real record the caller's own company scope cannot see
# --------------------------------------------------------------------------- #
def test_a_pin_the_callers_scope_cannot_see_fails_closed_not_an_error(db):
    sorento_id, mocha_id = _seed_two_companies(db)
    # Scope covers ONLY Sorento - Mocha's row (and its uuid) genuinely exists,
    # the caller simply cannot see it.
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))

    result = resolve_references(
        db,
        [SHARED_CODE],
        allowed_entity_types=["customer"],
        entity_pins={SHARED_CODE: mocha_id},
    )
    tr = _resolution(result, SHARED_CODE)

    assert tr is not None
    # Never a silent misresolution to a DIFFERENT company's row sharing the
    # same code (Sorento's), and never an exception either - just unresolved.
    assert tr.matches == [], (
        f"expected fail-closed (no matches), got {[m.uuid for m in tr.matches]}"
    )
    assert tr.ambiguous is False
    assert tr.resolved is False
    assert SHARED_CODE in result.unresolved_tokens
    # Guard against the same code being silently swapped for Sorento's own row.
    assert sorento_id not in [m.uuid for m in tr.matches]
