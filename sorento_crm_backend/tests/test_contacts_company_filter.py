"""Lane FILTER-MULTISELECT, PR 1: the contacts list's Company filter and Companies column.

Owner, 27 Oct: "here need to be able to filter by companies" and "show the companies column also".
A contact's companies are the companies of its linked customers (``respond_contact_customers`` ->
``customers.company_id``), read across every company the viewer is granted, the same reach as the
Customers column. The filter is multi-select: ``company`` repeats or comma-joins, values OR-ed.

Red tests written before the implementation. Postgres only (``blank_session``); every row is
seeded here. Assertions go through the HTTP response (``response_model`` drops undeclared fields).
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.models.access import RespondContact, RespondContactCustomer
from app.models.base import set_company_scope
from app.models.company import Company
from app.models.order import Customer
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.company_scope_resolver import apply_company_scope
from app.services.user_service import UserPermissionService

from tests._mc_lookup_seed import MOCHA_ID, seed_mocha
from tests._pg_fixture import blank_session, unique_code

SORENTO = DEFAULT_COMPANY_ID
CONTACTS = "/api/v1/user-management/contacts/"
CONTACT_VIEW = "user_management.contacts.view"


@pytest.fixture
def db():
    with blank_session() as session:
        seed_mocha(session)
        set_company_scope(session, frozenset({SORENTO, MOCHA_ID}))
        yield session


@pytest.fixture
def state():
    """Mutable scope the request override reads on every call."""
    return {"scope": frozenset({SORENTO, MOCHA_ID})}


@pytest.fixture
def client(db, state, monkeypatch):
    from app.models.user import User

    actor = User(id=str(uuid.uuid4()), email=f"zzt-{uuid.uuid4().hex[:8]}@test.com", name="ZZT Actor")
    db.add(actor)
    db.flush()
    principal = {"id": actor.id, "email": actor.email}

    def _override_db():
        yield db

    async def _override_scope():
        set_company_scope(db, state["scope"])
        return state["scope"]

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: principal
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
    app.dependency_overrides[apply_company_scope] = _override_scope
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug == CONTACT_VIEW,
    )
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _contact(db, tag: str) -> RespondContact:
    row = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"60{uuid.uuid4().int % 10**8 + 10**8}",
        name=f"ZZT {tag} {unique_code('c')}",
    )
    db.add(row)
    db.flush()
    return row


def _customer(db, company_id: str) -> Customer:
    code = f"ZZT-{unique_code('k')}"
    row = Customer(customer_code=code, customer_name=f"ZZT customer {code}", company_id=company_id)
    db.add(row)
    db.flush()
    return row


def _link(db, contact, customer) -> None:
    db.add(
        RespondContactCustomer(
            contact_id=contact.id, customer_id=customer.id, company_id=customer.company_id, source="manual"
        )
    )
    db.flush()


def _name(db, company_id: str) -> str:
    return db.query(Company.name).filter(Company.id == company_id).scalar()


@pytest.fixture
def seeded(db):
    """both: a Sorento and a Mocha customer (Mocha linked first); sorento / mocha: one each,
    sorento with two Sorento customers (one company, listed once); none: no customer."""
    tag = unique_code("T")
    both = _contact(db, f"{tag}-both")
    sorento = _contact(db, f"{tag}-srt")
    mocha = _contact(db, f"{tag}-mch")
    none = _contact(db, f"{tag}-none")
    _link(db, both, _customer(db, MOCHA_ID))
    _link(db, both, _customer(db, SORENTO))
    _link(db, sorento, _customer(db, SORENTO))
    _link(db, sorento, _customer(db, SORENTO))
    _link(db, mocha, _customer(db, MOCHA_ID))
    return dict(tag=tag, both=both, sorento=sorento, mocha=mocha, none=none)


def _list(client, params):
    """``params`` may be a list of pairs so a key can repeat."""
    if isinstance(params, dict):
        params = list(params.items())
    return client.get(CONTACTS, params=[("limit", 1000), *params])


def _ids(resp) -> set[str]:
    assert resp.status_code == 200, resp.text
    return {row["id"] for row in resp.json()["data"]}


# --- Companies column ---------------------------------------------------------------------


def test_rows_carry_distinct_sorted_customer_company_names(client, db, seeded):
    body = _list(client, {"query": seeded["tag"]}).json()
    by_id = {row["id"]: row for row in body["data"]}
    srt, mch = _name(db, SORENTO), _name(db, MOCHA_ID)
    assert by_id[seeded["both"].id]["customer_companies"] == sorted([srt, mch])
    # Two Sorento customers are one company, shown once.
    assert by_id[seeded["sorento"].id]["customer_companies"] == [srt]
    assert by_id[seeded["mocha"].id]["customer_companies"] == [mch]
    assert by_id[seeded["none"].id]["customer_companies"] == []


def test_column_reads_only_companies_the_viewer_can_see(client, state, seeded):
    state["scope"] = frozenset({SORENTO})
    body = _list(client, {"query": seeded["tag"]}).json()
    by_id = {row["id"]: row for row in body["data"]}
    assert by_id[seeded["mocha"].id]["customer_companies"] == []
    assert len(by_id[seeded["both"].id]["customer_companies"]) == 1


# --- Company filter -----------------------------------------------------------------------


def test_one_company_lists_contacts_with_a_customer_there(client, seeded):
    ids = _ids(_list(client, {"query": seeded["tag"], "company": MOCHA_ID}))
    assert ids == {seeded["both"].id, seeded["mocha"].id}


def test_repeated_company_values_are_or_ed(client, seeded):
    ids = _ids(_list(client, [("query", seeded["tag"]), ("company", MOCHA_ID), ("company", SORENTO)]))
    assert ids == {seeded["both"].id, seeded["sorento"].id, seeded["mocha"].id}


def test_comma_joined_company_values_are_or_ed(client, seeded):
    ids = _ids(_list(client, {"query": seeded["tag"], "company": f"{SORENTO},{MOCHA_ID}"}))
    assert ids == {seeded["both"].id, seeded["sorento"].id, seeded["mocha"].id}


def test_company_filter_ands_with_other_filters(client, seeded):
    ids = _ids(_list(client, {"query": seeded["tag"], "company": SORENTO, "customers": "none"}))
    assert ids == set()


def test_company_filter_total_matches_rows(client, seeded):
    body = _list(client, {"query": seeded["tag"], "company": SORENTO, "limit": 1, "page": 2}).json()
    assert body["pagination"]["total"] == 2
    assert len(body["data"]) == 1


def test_company_outside_the_viewers_reach_matches_nothing(client, state, seeded):
    """Fail closed: naming a company the viewer cannot see never reveals its links."""
    state["scope"] = frozenset({SORENTO})
    assert _ids(_list(client, {"query": seeded["tag"], "company": MOCHA_ID})) == set()


def test_malformed_company_value_is_422(client, seeded):
    assert _list(client, {"company": "not-a-uuid"}).status_code == 422


# --- Server-side sort ---------------------------------------------------------------------


def _order(client, tag, direction) -> list[str]:
    resp = _list(client, {"query": tag, "sort": "companies", "dir": direction})
    assert resp.status_code == 200, resp.text
    return [row["id"] for row in resp.json()["data"]]


def test_sort_by_companies_uses_first_company_name_and_empty_sorts_last(client, db, seeded):
    srt, mch = _name(db, SORENTO), _name(db, MOCHA_ID)
    assert srt != mch
    low_only, high_only = (seeded["mocha"], seeded["sorento"]) if mch < srt else (seeded["sorento"], seeded["mocha"])
    # `both` sorts by its first company, the lower one, so it groups with `low_only`.
    low = {seeded["both"].id, low_only.id}
    asc = _order(client, seeded["tag"], "asc")
    desc = _order(client, seeded["tag"], "desc")
    assert set(asc[:2]) == low and asc[2] == high_only.id and asc[3] == seeded["none"].id
    # An empty cell sorts last both ways.
    assert desc[0] == high_only.id and set(desc[1:3]) == low and desc[3] == seeded["none"].id
