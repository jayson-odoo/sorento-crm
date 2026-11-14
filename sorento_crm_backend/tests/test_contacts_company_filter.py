"""The contacts list's Company filter, Companies column and sort (FILTER-MULTISELECT PR1, then
CONTACT-COMPANIES-COL).

Owner, 14 Nov (CONTACT-COMPANIES-COL), on the list showing one company and the detail two: "it
should follow the detail page". A contact's companies are its COMPANY ACCESS
(``respond_contact_companies``), the list read through the same function as the detail page's
``GET /contacts/{id}/companies``; linked customers no longer decide them. The read stays
superadmin-only (PLAN-user-management-read-gates.md:138): anyone else gets an empty list.
The filter is multi-select: ``company`` repeats or comma-joins, values OR-ed.

Postgres only (``blank_session``); every row is seeded here. Assertions go through the HTTP
response (``response_model`` drops undeclared fields).
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
from app.models.company import Company, RespondContactCompany
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
    return {"scope": frozenset({SORENTO, MOCHA_ID}), "superadmin": True}


@pytest.fixture
def client(db, state, monkeypatch):
    from app.models.user import User

    actor = User(id=str(uuid.uuid4()), email=f"zzt-{uuid.uuid4().hex[:8]}@test.com", name="ZZT Actor")
    db.add(actor)
    db.flush()
    principal = {"id": actor.id, "email": actor.email}
    state["actor_id"] = actor.id

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
    monkeypatch.setattr(
        UserPermissionService,
        "get_user_role_slugs",
        lambda self, uid: {"superadmin"} if state["superadmin"] else set(),
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


def _access(db, contact, *company_ids) -> None:
    for company_id in company_ids:
        db.add(RespondContactCompany(respond_contact_id=contact.id, company_id=company_id))
    db.flush()


def _name(db, company_id: str) -> str:
    return db.query(Company.name).filter(Company.id == company_id).scalar()


@pytest.fixture
def seeded(db):
    """The owner's case and its mirror images, access vs linked customers:
    owner: access Sorento + Mocha, linked customers only in Mocha (list showed 1, detail 2);
    sorento: access Sorento only, but a Mocha customer linked;
    mocha: access Mocha only, no customer;
    none: no access, but a Sorento customer linked."""
    tag = unique_code("T")
    owner = _contact(db, f"{tag}-own")
    sorento = _contact(db, f"{tag}-srt")
    mocha = _contact(db, f"{tag}-mch")
    none = _contact(db, f"{tag}-none")
    for _ in range(3):
        _link(db, owner, _customer(db, MOCHA_ID))
    _access(db, owner, MOCHA_ID, SORENTO)
    _link(db, sorento, _customer(db, MOCHA_ID))
    _access(db, sorento, SORENTO)
    _access(db, mocha, MOCHA_ID)
    _link(db, none, _customer(db, SORENTO))
    return dict(tag=tag, owner=owner, sorento=sorento, mocha=mocha, none=none)


def _list(client, params):
    """``params`` may be a list of pairs so a key can repeat."""
    if isinstance(params, dict):
        params = list(params.items())
    return client.get(CONTACTS, params=[("limit", 1000), *params])


def _ids(resp) -> set[str]:
    assert resp.status_code == 200, resp.text
    return {row["id"] for row in resp.json()["data"]}


def _rows(client, tag) -> dict[str, dict]:
    resp = _list(client, {"query": tag})
    assert resp.status_code == 200, resp.text
    return {row["id"]: row for row in resp.json()["data"]}


# --- Companies column ---------------------------------------------------------------------


def test_column_shows_company_access_not_linked_customers_companies(client, db, seeded):
    rows = _rows(client, seeded["tag"])
    srt, mch = _name(db, SORENTO), _name(db, MOCHA_ID)
    # The owner's case: three Mocha customers, access to both companies -> both, sorted.
    assert rows[seeded["owner"].id]["companies"] == sorted([srt, mch])
    assert rows[seeded["sorento"].id]["companies"] == [srt]
    assert rows[seeded["mocha"].id]["companies"] == [mch]
    # A linked customer alone grants nothing.
    assert rows[seeded["none"].id]["companies"] == []


def test_column_equals_the_detail_page_for_every_row(client, seeded):
    """One function, one answer: the list cell is the detail page's chips, row for row."""
    rows = _rows(client, seeded["tag"])
    assert len(rows) == 4
    for contact_id, row in rows.items():
        detail = client.get(f"{CONTACTS}{contact_id}/companies")
        assert detail.status_code == 200, detail.text
        assert row["companies"] == [c["name"] for c in detail.json()], contact_id


def test_column_does_not_depend_on_the_viewers_active_company(client, db, state, seeded):
    """Like the detail page: access is the contact's, whatever company the viewer works in."""
    state["scope"] = frozenset({SORENTO})
    rows = _rows(client, seeded["tag"])
    assert rows[seeded["mocha"].id]["companies"] == [_name(db, MOCHA_ID)]
    assert len(rows[seeded["owner"].id]["companies"]) == 2


def test_non_superadmin_gets_no_company_access_values(client, state, seeded):
    """The access read stays superadmin-only (read-gates plan :138): withheld, not guessed."""
    state["superadmin"] = False
    rows = _rows(client, seeded["tag"])
    assert all(row["companies"] == [] for row in rows.values())


def test_old_customer_companies_field_is_gone(client, seeded):
    rows = _rows(client, seeded["tag"])
    assert all("customer_companies" not in row for row in rows.values())


# --- Company filter -----------------------------------------------------------------------


def test_one_company_lists_contacts_with_access_there(client, seeded):
    ids = _ids(_list(client, {"query": seeded["tag"], "company": MOCHA_ID}))
    # `sorento` has a Mocha customer but no Mocha access: out.
    assert ids == {seeded["owner"].id, seeded["mocha"].id}


def test_filter_ignores_linked_customers(client, seeded):
    ids = _ids(_list(client, {"query": seeded["tag"], "company": SORENTO}))
    # `none` has a Sorento customer but no access: out.
    assert ids == {seeded["owner"].id, seeded["sorento"].id}


def test_repeated_company_values_are_or_ed(client, seeded):
    ids = _ids(_list(client, [("query", seeded["tag"]), ("company", MOCHA_ID), ("company", SORENTO)]))
    assert ids == {seeded["owner"].id, seeded["sorento"].id, seeded["mocha"].id}


def test_comma_joined_company_values_are_or_ed(client, seeded):
    ids = _ids(_list(client, {"query": seeded["tag"], "company": f"{SORENTO},{MOCHA_ID}"}))
    assert ids == {seeded["owner"].id, seeded["sorento"].id, seeded["mocha"].id}


def test_company_filter_ands_with_other_filters(client, seeded):
    ids = _ids(_list(client, {"query": seeded["tag"], "company": MOCHA_ID, "customers": "none"}))
    assert ids == {seeded["mocha"].id}


def test_company_filter_total_matches_rows(client, seeded):
    body = _list(client, {"query": seeded["tag"], "company": SORENTO, "limit": 1, "page": 2}).json()
    assert body["pagination"]["total"] == 2
    assert len(body["data"]) == 1


def test_company_filter_matches_nothing_for_a_non_superadmin(client, state, seeded):
    """Fail closed: a viewer who may not read access cannot learn it through the filter either."""
    state["superadmin"] = False
    assert _ids(_list(client, {"query": seeded["tag"], "company": MOCHA_ID})) == set()


def test_malformed_company_value_is_422(client, seeded):
    assert _list(client, {"company": "not-a-uuid"}).status_code == 422


# --- Server-side sort ---------------------------------------------------------------------


def _order(client, tag, direction) -> list[str]:
    resp = _list(client, {"query": tag, "sort": "companies", "dir": direction})
    assert resp.status_code == 200, resp.text
    return [row["id"] for row in resp.json()["data"]]


def test_sort_by_companies_uses_first_access_company_and_empty_sorts_last(client, db, seeded):
    srt, mch = _name(db, SORENTO), _name(db, MOCHA_ID)
    assert srt != mch
    low_only, high_only = (seeded["mocha"], seeded["sorento"]) if mch < srt else (seeded["sorento"], seeded["mocha"])
    # `owner` holds both, so it sorts by the lower name and groups with `low_only`.
    low = {seeded["owner"].id, low_only.id}
    asc = _order(client, seeded["tag"], "asc")
    desc = _order(client, seeded["tag"], "desc")
    assert set(asc[:2]) == low and asc[2] == high_only.id and asc[3] == seeded["none"].id
    # An empty cell sorts last both ways; `none`'s linked customer does not count.
    assert desc[0] == high_only.id and set(desc[1:3]) == low and desc[3] == seeded["none"].id


def test_sort_by_companies_reveals_nothing_to_a_non_superadmin(client, state, seeded):
    """Withheld values must not leak through the order: a non-superadmin sorting by Companies gets
    the list's default order (created_at, then name, then id), whichever direction."""
    state["superadmin"] = False
    for direction in ("asc", "desc"):
        default = _list(client, {"query": seeded["tag"], "sort": "created_at", "dir": direction})
        assert default.status_code == 200, default.text
        expected = [row["id"] for row in default.json()["data"]]
        assert _order(client, seeded["tag"], direction) == expected, direction
