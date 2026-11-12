"""DEALER-ACCESS-SCREEN S1-S7 (UAC `documentation/plans/contacts/dealer-access-screen-09nov-acceptance-criteria.md`).

Red tests, written before the implementation. Each test name carries its UAC id. Backend of the salesperson
"Dealer access" screen: `app/services/dealer_access_screen.py` (`my_accounts`, `list_people`, `grant`, `update`),
the routes under `/api/v1/sales/dealer-access`, and the record action `dealer_access_link.unlink`.

World: salesperson 1 (the user of `own_world`, holds `user_management.contacts.edit_own` only) owns `cust_a`, `twin1`,
`twin2` (Sorento) and `cust_b` (Mocha); salesperson 2 (a user as well, built here) owns `theirs` (Sorento) and
`theirs_m` (Mocha). A shared dealer is linked under both. Postgres only (blank schema), every test seeds its own chain
(the owner tags included). Phones, names and codes are invented (public repo).

Contract shapes the tests pin (confirm with the coder; flagged in the red-run report):
- `AppException` has no `details` attribute: the extra data sits in `exc.detail["details"]` (constructor argument
  `details=`), so the row refusals are read from `exc.detail["details"]["rows"]`.
- `rows[].index` is the 0-based position in the submitted `people` list; the duplicate text names the 1-based row
  (`Same as row 1.` on the second person).
- The service returns plain `{"rows": [...], "total": n}` (people) and a list of `{id, code, name}` (accounts); the
  routes may wrap these in `{"data": ...}` (both accepted by `_unwrap`).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

import app.main  # noqa: F401  register every model and the app's listeners
from app.audit_context import AuditActor, clear_actor, stamp_actor
from app.dependencies import _load_user_dict_from_db, get_current_user, get_current_user_or_api_key, get_db
from app.main import app
from app.models.access import RespondContact, RespondContactCustomer
from app.models.audit import AuditLog
from app.models.base import company_scope, set_company_scope
from app.models.company import UserCompany
from app.models.order import Customer
from app.services.audit_service import register_audit_listeners
from app.services.company_scope import register_company_scope_listeners
from app.services.company_scope_resolver import apply_company_scope, resolve_user_grant_ids
from app.services.error_handler import AppException
from tests._ask_todo_seed import customer as seed_customer
from tests._pg_fixture import blank_session, unique_code
from tests.chatbot.agent._seed import seed_contact, seed_user
from tests.chatbot.agent.test_agent_bulk_grant import dealer, events, fake_phone, local, make_world, state
from tests.chatbot.agent.test_dealer_access_agent import (
    ALREADY,
    ALSO,
    DEMOTE_REFUSED,
    EDIT_OWN,
    MCH_TAG,
    NEITHER,
    SRT_TAG,
    STAFF,
    add_customer,
    ai_on,
    own_world,
    tag_contact,
    owner_tag,
    tags_of,
)

BASE = "/api/v1/sales/dealer-access"
PICK_OWN = "Pick one of your accounts."
SRT_OWNER_TYPES = ("end_user", "dealer", "cabana_dealer")
PEOPLE_KEYS = {
    "contact_id", "name", "phone", "company", "company_name", "accounts", "access", "owner_tag", "other_account",
}


# ------------------------------------------------------------------ fixtures


@pytest.fixture(autouse=True)
def _listeners():
    register_company_scope_listeners()
    register_audit_listeners()
    yield
    clear_actor()


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def jobs(monkeypatch):
    """Every `enqueue_job` call, recorded instead of reaching Redis."""
    calls: list[SimpleNamespace] = []

    def record(func, *args, **kwargs):
        calls.append(SimpleNamespace(func=func, args=args, kwargs=kwargs))
        return SimpleNamespace(id=f"zzt-job-{len(calls)}")

    import app.services.chatbot.agent.contact_grant as contact_grant
    import app.services.queue_service as queue_service

    monkeypatch.setattr(queue_service, "enqueue_job", record)
    monkeypatch.setattr(contact_grant, "enqueue_job", record, raising=False)
    return calls


def respond_jobs(calls) -> list:
    return [c for c in calls if getattr(c.func, "__name__", "") == "ensure_respond_contact"]


def _api_client(db, *, active_only: bool):
    """`as_user(uid)` -> a TestClient authenticated as that user. Permissions are the real ones (the user holds
    exactly the slugs it was seeded with); the audit actor is stamped the way `get_current_user` does. The request's
    company scope is every granted company, or (`active_only`) the user's ACTIVE company alone, as a real request."""
    who = {"uid": None}

    def _override_db():
        yield db

    def _override_user():
        uid = who["uid"]
        user = _load_user_dict_from_db(db, uid)
        stamp_actor(AuditActor(actor_type="user", user_id=uid, real_user_id=uid, auth_method="password"), db=db)
        return user

    async def _override_scope():
        if active_only:
            from app.models.user import User

            with company_scope(db, None):
                active = db.query(User.last_active_company_id).filter(User.id == who["uid"]).scalar()
            scope = frozenset({str(active)})
        else:
            scope = frozenset(resolve_user_grant_ids(db, who["uid"]))
        set_company_scope(db, scope)
        return scope

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_current_user_or_api_key] = _override_user
    app.dependency_overrides[apply_company_scope] = _override_scope
    http = TestClient(app)

    def as_user(uid: str) -> TestClient:
        who["uid"] = uid
        return http

    return SimpleNamespace(as_user=as_user)


@pytest.fixture()
def api(db):
    try:
        yield _api_client(db, active_only=False)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def api_active(db):
    """Like `api`, but the request scope is the user's active company only (what a real request carries)."""
    try:
        yield _api_client(db, active_only=True)
    finally:
        app.dependency_overrides.clear()


# ------------------------------------------------------------------ seeding


def two_sales(db) -> SimpleNamespace:
    """`own_world` plus salesperson 2 as a real user (edit_own, both companies) on the other agent's contact."""
    o = own_world(db)
    s2 = seed_user(db, contact_pk=o.other_contact, slugs=(EDIT_OWN,))
    for company_id in (o.w.srt, o.w.mch):
        db.add(UserCompany(user_id=s2, company_id=company_id))
    db.commit()
    o.s1 = o.w.user_id
    o.s2 = s2
    return o


def link_row(db, contact_id: str, customer_id: str) -> RespondContactCustomer:
    with company_scope(db, None):
        return db.query(RespondContactCustomer).filter(
            RespondContactCustomer.contact_id == str(contact_id), RespondContactCustomer.customer_id == str(customer_id)
        ).one()


def links_of(db, contact_id: str) -> set[str]:
    db.expire_all()
    with company_scope(db, None):
        return {
            str(c) for (c,) in db.query(RespondContactCustomer.customer_id)
            .filter(RespondContactCustomer.contact_id == str(contact_id))
        }


def link_to(db, contact_id: str, customer) -> RespondContactCustomer:
    row = RespondContactCustomer(
        id=str(uuid.uuid4()), contact_id=str(contact_id), customer_id=customer.id, company_id=customer.company_id,
    )
    db.add(row)
    db.commit()
    return row


def owner_dealer(db, w, *, customers, name, companies=None):
    """A Sorento Business owner: the owner types and the owner tag, linked to `customers`."""
    owner_tag(db, SRT_TAG)
    row = dealer(db, w, types=SRT_OWNER_TYPES, customers=customers, name=name, companies=companies)
    tag_contact(db, row.id, owner_tag(db, SRT_TAG))
    return row


def ids_of(*customers) -> list[str]:
    return [str(c.id) for c in customers]


def blob(value) -> str:
    return json.dumps(value, default=str)


def hidden_of(*customers) -> list[str]:
    out: list[str] = []
    for c in customers:
        out += [str(c.id), c.customer_code, c.customer_name]
    return out


def assert_no_leak(value, *customers) -> None:
    text = blob(value)
    for secret in hidden_of(*customers):
        assert secret not in text, f"another salesperson's {secret!r} leaked into the response"


def digits(phone: str) -> str:
    return "".join(ch for ch in str(phone) if ch.isdigit())


def refusal_rows(exc: AppException) -> list[dict]:
    return exc.detail["details"]["rows"]


def _unwrap(body):
    if isinstance(body, dict) and "data" in body and "rows" not in body:
        return body["data"]
    return body


def _find_rows(body):
    """The `rows: [{index, error}]` of a 422 body, wherever the handler nests `details`."""
    if isinstance(body, dict):
        rows = body.get("rows")
        if isinstance(rows, list) and rows and isinstance(rows[0], dict) and "error" in rows[0]:
            return rows
        for value in body.values():
            found = _find_rows(value)
            if found:
                return found
    return None


def service():
    from app.services import dealer_access_screen

    return dealer_access_screen


def person_rows(db, uid, **kw) -> list[dict]:
    return service().list_people(db, uid, **kw)["rows"]


# ================================================================== S1 permission


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("get", f"{BASE}/accounts?company=SRT", None),
        ("get", f"{BASE}/people", None),
        ("post", f"{BASE}/grant", {"company": "SRT", "account_ids": ["x"], "people": []}),
        ("put", f"{BASE}/people/00000000-0000-4000-8000-000000000001", {"company": "SRT", "role": "employee", "account_ids": ["x"]}),
    ],
)
def test_S1_every_route_is_403_without_edit_own(db, api, method, path, body):
    none = make_world(db, slugs=(NEITHER,), superadmin=False)

    resp = getattr(api.as_user(none.user_id), method)(path, **({"json": body} if body is not None else {}))

    assert resp.status_code == 403, resp.text


def test_S1_an_edit_own_holder_reaches_the_routes_under_the_sales_module(db, api):
    o = two_sales(db)

    resp = api.as_user(o.s1).get(f"{BASE}/accounts?company=SRT")

    assert resp.status_code == 200, resp.text
    assert {a["code"] for a in _unwrap(resp.json())} >= {o.w.cust_a.customer_code}


def test_S1_parking_the_unlink_action_without_edit_own_is_403(db, api):
    o = two_sales(db)
    none = make_world(db, slugs=(NEITHER,), superadmin=False)
    person = dealer(db, o.w, customers=(o.w.cust_a,))
    link = link_row(db, person.id, o.w.cust_a.id)

    resp = api.as_user(none.user_id).post(
        "/api/v1/pending-actions",
        json={"action_key": "dealer_access_link.unlink", "entity_type": "dealer_access_link", "entity_id": link.id, "payload": {}},
    )

    assert resp.status_code == 403, resp.text


# ================================================================== S2 my accounts


def test_S2_my_accounts_are_my_own_active_accounts_of_that_company_by_code(db):
    o = two_sales(db)
    w = o.w
    inactive = add_customer(db, w, unique_code("ZZT Inactive Shop"))
    with company_scope(db, None):
        db.query(Customer).filter(Customer.id == inactive.id).update({"is_active": False})
    db.commit()

    srt = service().my_accounts(db, o.s1, "SRT")
    mch = service().my_accounts(db, o.s1, "MCH")

    assert [a["code"] for a in srt] == sorted(c.customer_code for c in (w.cust_a, w.twin1, w.twin2))
    assert set(srt[0]) == {"id", "code", "name"}
    assert {a["id"] for a in srt} == set(ids_of(w.cust_a, w.twin1, w.twin2))
    assert [a["id"] for a in mch] == [str(w.cust_b.id)]
    assert_no_leak(srt + mch, o.theirs, o.theirs_m, inactive)


def test_S2_the_other_salespersons_account_of_the_same_dealer_never_appears(db):
    o = two_sales(db)

    mine = service().my_accounts(db, o.s1, "SRT")
    theirs = service().my_accounts(db, o.s2, "SRT")

    assert_no_leak(mine, o.theirs)
    assert [a["id"] for a in theirs] == [str(o.theirs.id)]
    assert_no_leak(theirs, o.w.cust_a, o.w.twin1, o.w.twin2)


def test_S2_a_company_i_am_not_granted_is_403_not_one_of_your_companies(db):
    o = two_sales(db)
    with company_scope(db, None):
        db.query(UserCompany).filter(UserCompany.user_id == o.s1, UserCompany.company_id == o.w.mch).delete()
    db.commit()

    with pytest.raises(AppException) as err:
        service().my_accounts(db, o.s1, "MCH")

    assert err.value.status_code == 403
    assert "not one of your companies" in err.value.message


def test_S2_a_user_with_no_linked_sales_agent_gets_an_empty_list(db):
    o = two_sales(db)
    contact = seed_contact(db)
    lone = seed_user(db, contact_pk=contact["pk"], slugs=(EDIT_OWN,))
    db.add(UserCompany(user_id=lone, company_id=o.w.srt))
    db.commit()

    assert service().my_accounts(db, lone, "SRT") == []


def test_S2_http_accounts_for_a_company_and_403_for_one_not_granted(db, api):
    o = two_sales(db)
    client = api.as_user(o.s1)

    ok = client.get(f"{BASE}/accounts", params={"company": "MCH"})
    assert ok.status_code == 200, ok.text
    assert [a["id"] for a in _unwrap(ok.json())] == [str(o.w.cust_b.id)]
    assert_no_leak(ok.json(), o.theirs, o.theirs_m)

    with company_scope(db, None):
        db.query(UserCompany).filter(UserCompany.user_id == o.s1, UserCompany.company_id == o.w.mch).delete()
    db.commit()
    refused = client.get(f"{BASE}/accounts", params={"company": "MCH"})
    assert refused.status_code == 403, refused.text


# ================================================================== S3 people


def shared_dealer(db, o):
    """One dealer under both salespeople: my Sorento account, their Sorento and Mocha accounts."""
    return dealer(
        db, o.w, customers=(o.w.cust_a, o.theirs, o.theirs_m), companies=(o.w.srt, o.w.mch), name="ZZT Shared Dealer"
    )


def test_S3_a_shared_dealer_shows_only_my_rows_flagged_other_account_and_leaks_nothing(db):
    o = two_sales(db)
    person = shared_dealer(db, o)

    out = service().list_people(db, o.s1)

    assert out["total"] == 1
    row = out["rows"][0]
    assert set(row) == PEOPLE_KEYS
    assert row["contact_id"] == str(person.id)
    assert row["company"] == "SRT" and row["company_name"]
    assert digits(row["phone"]) == digits(person.phone_number)
    assert row["accounts"] == [{
        "id": str(o.w.cust_a.id), "code": o.w.cust_a.customer_code, "name": o.w.cust_a.customer_name,
        "link_id": link_row(db, person.id, o.w.cust_a.id).id,
    }]
    assert row["other_account"] is True
    assert_no_leak(out, o.theirs, o.theirs_m)


def test_S3_the_other_salesperson_sees_their_own_two_company_rows_only(db):
    o = two_sales(db)
    shared_dealer(db, o)

    out = service().list_people(db, o.s2)

    assert out["total"] == 2
    by_company = {r["company"]: r for r in out["rows"]}
    assert set(by_company) == {"SRT", "MCH"}
    assert [a["id"] for a in by_company["SRT"]["accounts"]] == [str(o.theirs.id)]
    assert [a["id"] for a in by_company["MCH"]["accounts"]] == [str(o.theirs_m.id)]
    assert all(r["other_account"] is True for r in out["rows"])
    assert_no_leak(out, o.w.cust_a, o.w.twin1, o.w.twin2, o.w.cust_b)


def test_S3_a_contact_linked_only_to_my_accounts_is_not_other_account_and_one_row_per_company(db):
    o = two_sales(db)
    w = o.w
    person = dealer(db, w, customers=(w.cust_a, w.twin1, w.cust_b), companies=(w.srt, w.mch), name="ZZT Both Companies")

    rows = person_rows(db, o.s1)

    assert {r["company"] for r in rows} == {"SRT", "MCH"} and len(rows) == 2
    srt = next(r for r in rows if r["company"] == "SRT")
    assert {a["id"] for a in srt["accounts"]} == set(ids_of(w.cust_a, w.twin1))
    assert all(r["other_account"] is False and r["contact_id"] == str(person.id) for r in rows)


def test_S3_a_company_row_needs_a_link_to_one_of_my_accounts_of_that_company(db):
    o = two_sales(db)
    w = o.w
    dealer(db, w, customers=(w.cust_a, o.theirs_m), companies=(w.srt, w.mch), name="ZZT Srt Only For Me")

    rows = person_rows(db, o.s1)

    assert [r["company"] for r in rows] == ["SRT"]


def test_S3_my_own_contact_never_appears(db):
    o = two_sales(db)
    w = o.w
    link_to(db, w.contact["pk"], w.cust_a)
    other = dealer(db, w, customers=(w.cust_a,), name="ZZT Someone Else")

    rows = person_rows(db, o.s1)

    assert [r["contact_id"] for r in rows] == [str(other.id)]


def test_S3_access_is_owner_when_the_contact_holds_the_company_owner_tag_else_employee(db):
    o = two_sales(db)
    w = o.w
    owner = owner_dealer(db, w, customers=(w.cust_a, w.cust_b), name="ZZT Owner Person", companies=(w.srt, w.mch))
    employee = dealer(db, w, customers=(w.twin1,), name="ZZT Employee Person")

    rows = person_rows(db, o.s1)

    by = {(r["contact_id"], r["company"]): r for r in rows}
    assert by[(str(owner.id), "SRT")]["access"] == "owner"
    assert by[(str(owner.id), "SRT")]["owner_tag"] == SRT_TAG
    # holding the Sorento tag says nothing about Mocha
    assert by[(str(owner.id), "MCH")]["access"] == "employee"
    assert by[(str(owner.id), "MCH")]["owner_tag"] is None
    assert by[(str(employee.id), "SRT")]["access"] == "employee"
    assert by[(str(employee.id), "SRT")]["owner_tag"] is None


def test_S3_the_mocha_owner_tag_makes_the_mocha_row_an_owner(db):
    o = two_sales(db)
    w = o.w
    person = dealer(db, w, types=("end_user", "mocha_dealer"), customers=(w.cust_b,), companies=(w.mch,), name="ZZT Mocha Owner")
    tag_contact(db, person.id, owner_tag(db, MCH_TAG))

    rows = person_rows(db, o.s1)

    assert [(r["company"], r["access"], r["owner_tag"]) for r in rows] == [("MCH", "owner", MCH_TAG)]


def test_S3_filters_company_and_access(db):
    o = two_sales(db)
    w = o.w
    owner = owner_dealer(db, w, customers=(w.cust_a, w.cust_b), name="ZZT Owner Person", companies=(w.srt, w.mch))
    employee = dealer(db, w, customers=(w.twin1,), name="ZZT Employee Person")

    assert {r["contact_id"] for r in person_rows(db, o.s1, access="owner")} == {str(owner.id)}
    assert {r["contact_id"] for r in person_rows(db, o.s1, access="employee")} == {str(owner.id), str(employee.id)}
    assert {(r["contact_id"], r["company"]) for r in person_rows(db, o.s1, companies=["MCH"])} == {(str(owner.id), "MCH")}
    both = person_rows(db, o.s1, companies=["SRT", "MCH"], access="owner")
    assert {(r["contact_id"], r["company"]) for r in both} == {(str(owner.id), "SRT")}


def test_S3_query_matches_name_phone_digits_and_my_account_code(db):
    o = two_sales(db)
    w = o.w
    named = dealer(db, w, customers=(w.cust_a,), name="ZZT Quillon Findable")
    other = dealer(db, w, customers=(w.twin1,), name="ZZT Plain Person")

    assert [r["contact_id"] for r in person_rows(db, o.s1, query="quillon")] == [str(named.id)]
    assert [r["contact_id"] for r in person_rows(db, o.s1, query=digits(other.phone_number)[-8:])] == [str(other.id)]
    by_code = person_rows(db, o.s1, query=w.cust_a.customer_code)
    assert [r["contact_id"] for r in by_code] == [str(named.id)]


def test_S3_query_by_the_other_salespersons_code_finds_nothing(db):
    o = two_sales(db)
    shared_dealer(db, o)

    out = service().list_people(db, o.s1, query=o.theirs.customer_code)
    by_name = service().list_people(db, o.s1, query=o.theirs.customer_name)
    by_mocha = service().list_people(db, o.s1, query=o.theirs_m.customer_code)

    assert out["total"] == 0 and out["rows"] == []
    assert by_name["total"] == 0 and by_mocha["total"] == 0
    assert_no_leak([out, by_name, by_mocha], o.theirs, o.theirs_m)


def test_S3_rows_are_ordered_by_name_then_phone_and_total_counts_rows_across_pages(db):
    o = two_sales(db)
    w = o.w
    c = dealer(db, w, customers=(w.cust_a,), name="ZZT Cc Person")
    a = dealer(db, w, customers=(w.cust_a,), name="ZZT Aa Person")
    b = dealer(db, w, customers=(w.twin1,), name="ZZT Bb Person")

    first = service().list_people(db, o.s1, page=1, limit=2)
    second = service().list_people(db, o.s1, page=2, limit=2)

    assert first["total"] == 3 and second["total"] == 3
    assert [r["contact_id"] for r in first["rows"]] == [str(a.id), str(b.id)]
    assert [r["contact_id"] for r in second["rows"]] == [str(c.id)]


def test_S3_http_people_with_the_data_grid_params_and_filters(db, api):
    o = two_sales(db)
    w = o.w
    owner = owner_dealer(db, w, customers=(w.cust_a,), name="ZZT Http Owner")
    dealer(db, w, customers=(w.twin1,), name="ZZT Http Employee")
    shared_dealer(db, o)

    resp = api.as_user(o.s1).get(f"{BASE}/people", params={"company": "SRT", "access": "owner", "page": 1, "limit": 10})

    assert resp.status_code == 200, resp.text
    body = _unwrap(resp.json()) if "rows" not in resp.json() else resp.json()
    assert body["total"] == 1
    assert [r["contact_id"] for r in body["rows"]] == [str(owner.id)]
    assert set(body["rows"][0]) == PEOPLE_KEYS
    assert_no_leak(resp.json(), o.theirs, o.theirs_m)


def test_S3_http_repeated_company_param_and_no_leak_on_the_shared_dealer(db, api):
    o = two_sales(db)
    shared_dealer(db, o)

    resp = api.as_user(o.s1).get(f"{BASE}/people", params=[("company", "SRT"), ("company", "MCH")])

    assert resp.status_code == 200, resp.text
    assert_no_leak(resp.json(), o.theirs, o.theirs_m)
    rows = resp.json()["rows"] if "rows" in resp.json() else _unwrap(resp.json())["rows"]
    assert [r["company"] for r in rows] == ["SRT"]


# ================================================================== S4 grant


def person_of(phone, *, name="ZZT Fresh Person", role="employee") -> dict:
    return {"name": name, "phone": phone, "role": role}


def test_S4_a_new_phone_as_owner_creates_the_contact_links_both_accounts_and_holds_the_owner_tag(db, jobs):
    o = two_sales(db)
    w = o.w
    phone = fake_phone()

    out = service().grant(db, o.s1, "SRT", ids_of(w.cust_a, w.twin1), [person_of(phone, name="ZZT New Owner", role="owner")])

    assert len(out["rows"]) == 1
    row = out["rows"][0]
    assert row["index"] == 0 and row["created"] is True
    after = state(db, phone)
    assert after is not None and str(after["id"]) == str(row["contact_id"])
    assert after["name"] == "ZZT New Owner"
    assert after["links"] == sorted(ids_of(w.cust_a, w.twin1))
    assert SRT_TAG in tags_of(db, after["id"])
    assert len(respond_jobs(jobs)) == 1


def test_S4_an_employee_grant_holds_no_owner_tag_and_audits_once_per_contact(db):
    o = two_sales(db)
    w = o.w
    p1, p2 = fake_phone(), fake_phone()

    out = service().grant(db, o.s1, "SRT", ids_of(w.cust_a), [person_of(p1, name="ZZT One"), person_of(p2, name="ZZT Two")])

    assert [r["index"] for r in out["rows"]] == [0, 1]
    assert [r["created"] for r in out["rows"]] == [True, True]
    for phone in (p1, p2):
        after = state(db, phone)
        assert SRT_TAG not in tags_of(db, after["id"])
        assert len(events(db, after["id"])) == 1


def test_S4_an_account_that_is_not_mine_is_422_pick_one_of_your_accounts_and_nothing_is_written(db):
    o = two_sales(db)
    phone = fake_phone()

    with pytest.raises(AppException) as err:
        service().grant(db, o.s1, "SRT", ids_of(o.w.cust_a, o.theirs), [person_of(phone)])

    assert err.value.status_code == 422
    assert PICK_OWN in err.value.message
    assert state(db, phone) is None
    assert_no_leak(err.value.detail, o.theirs)


def test_S4_an_account_of_the_other_company_is_not_one_of_my_accounts_of_this_company(db):
    o = two_sales(db)
    phone = fake_phone()

    with pytest.raises(AppException) as err:
        service().grant(db, o.s1, "SRT", ids_of(o.w.cust_b), [person_of(phone)])

    assert err.value.status_code == 422 and PICK_OWN in err.value.message
    assert state(db, phone) is None


def test_S4_a_nonexistent_account_id_reads_like_another_salespersons(db):
    o = two_sales(db)

    with pytest.raises(AppException) as missing:
        service().grant(db, o.s1, "SRT", [str(uuid.uuid4())], [person_of(fake_phone())])
    with pytest.raises(AppException) as theirs:
        service().grant(db, o.s1, "SRT", ids_of(o.theirs), [person_of(fake_phone())])

    assert missing.value.status_code == theirs.value.status_code == 422
    assert missing.value.message == theirs.value.message == PICK_OWN


def test_S4_one_refused_row_refuses_the_whole_form_and_the_good_phone_is_not_created(db):
    o = two_sales(db)
    w = o.w
    staff_contact = RespondContact(id=str(uuid.uuid4()), phone_number=fake_phone(), name="ZZT Staff User")
    db.add(staff_contact)
    db.flush()
    seed_user(db, contact_pk=staff_contact.id, slugs=())
    db.commit()
    good = fake_phone()

    with pytest.raises(AppException) as err:
        service().grant(db, o.s1, "SRT", ids_of(w.cust_a), [
            person_of(staff_contact.phone_number, name="ZZT Staff"), person_of(good, name="ZZT Good"),
        ])

    assert err.value.status_code == 422
    rows = refusal_rows(err.value)
    assert rows == [{"index": 0, "error": STAFF}]
    assert state(db, good) is None
    assert state(db, staff_contact.phone_number)["links"] == []


def test_S4_a_duplicate_phone_in_the_form_is_refused_on_the_later_row_and_nothing_is_written(db):
    o = two_sales(db)
    phone = fake_phone()

    with pytest.raises(AppException) as err:
        service().grant(db, o.s1, "SRT", ids_of(o.w.cust_a), [
            person_of(phone, name="ZZT First"), person_of(local(phone), name="ZZT Again"),
        ])

    rows = refusal_rows(err.value)
    assert {"index": 1, "error": "Same as row 1."} in rows
    assert all(r["index"] != 0 for r in rows)
    assert state(db, phone) is None


def test_S4_an_unreadable_phone_is_refused_with_the_plans_own_text(db):
    o = two_sales(db)

    with pytest.raises(AppException) as err:
        service().grant(db, o.s1, "SRT", ids_of(o.w.cust_a), [person_of("12345")])

    rows = refusal_rows(err.value)
    assert rows[0]["index"] == 0 and "is not a Malaysian mobile number" in rows[0]["error"]


def test_S4_a_shared_contact_gets_the_own_link_add_only_and_the_note_also_has_access(db):
    o = two_sales(db)
    w = o.w
    person = dealer(db, w, customers=(o.theirs,), name="ZZT Shared Person")

    out = service().grant(db, o.s1, "SRT", ids_of(w.cust_a), [person_of(person.phone_number, role="employee")])

    row = out["rows"][0]
    assert row["created"] is False and str(row["contact_id"]) == str(person.id)
    assert ALSO in blob(row["notes"])
    assert links_of(db, person.id) == set(ids_of(o.theirs, w.cust_a))
    assert_no_leak(out, o.theirs)


def test_S4_promoting_a_shared_contact_is_refused_with_the_office_text(db):
    o = two_sales(db)
    person = dealer(db, o.w, customers=(o.theirs,), name="ZZT Shared Person")

    with pytest.raises(AppException) as err:
        service().grant(db, o.s1, "SRT", ids_of(o.w.cust_a), [person_of(person.phone_number, role="owner")])

    assert refusal_rows(err.value) == [{"index": 0, "error": DEMOTE_REFUSED}]
    assert links_of(db, person.id) == {str(o.theirs.id)}


def test_S4_granting_what_is_already_held_is_refused_nothing_to_change(db):
    o = two_sales(db)
    phone = fake_phone()
    service().grant(db, o.s1, "SRT", ids_of(o.w.cust_a), [person_of(phone)])

    with pytest.raises(AppException) as err:
        service().grant(db, o.s1, "SRT", ids_of(o.w.cust_a), [person_of(phone)])

    assert refusal_rows(err.value) == [{"index": 0, "error": ALREADY}]


def test_S4_a_company_i_am_not_granted_is_refused(db):
    o = two_sales(db)
    with company_scope(db, None):
        db.query(UserCompany).filter(UserCompany.user_id == o.s1, UserCompany.company_id == o.w.mch).delete()
    db.commit()
    phone = fake_phone()

    with pytest.raises(AppException) as err:
        service().grant(db, o.s1, "MCH", ids_of(o.w.cust_b), [person_of(phone)])

    assert err.value.status_code in (403, 422)
    assert state(db, phone) is None


def test_S4_http_grant_happy_path_audits_me_and_returns_rows(db, api, jobs):
    o = two_sales(db)
    w = o.w
    phone = fake_phone()

    resp = api.as_user(o.s1).post(f"{BASE}/grant", json={
        "company": "SRT", "account_ids": ids_of(w.cust_a, w.twin1),
        "people": [{"name": "ZZT Http New", "phone": phone, "role": "owner"}],
    })

    assert resp.status_code in (200, 201), resp.text
    rows = resp.json()["rows"] if "rows" in resp.json() else _unwrap(resp.json())["rows"]
    assert rows[0]["index"] == 0 and rows[0]["created"] is True
    after = state(db, phone)
    assert str(after["id"]) == str(rows[0]["contact_id"])
    assert after["links"] == sorted(ids_of(w.cust_a, w.twin1))
    assert SRT_TAG in tags_of(db, after["id"])
    audit = events(db, after["id"])
    assert len(audit) == 1 and str(audit[0].user_id) == str(o.s1)
    assert len(respond_jobs(jobs)) == 1


def test_S4_http_a_refused_row_is_422_with_rows_index_and_error(db, api):
    o = two_sales(db)
    good = fake_phone()
    staff_contact = RespondContact(id=str(uuid.uuid4()), phone_number=fake_phone(), name="ZZT Staff User")
    db.add(staff_contact)
    db.flush()
    seed_user(db, contact_pk=staff_contact.id, slugs=())
    db.commit()

    resp = api.as_user(o.s1).post(f"{BASE}/grant", json={
        "company": "SRT", "account_ids": ids_of(o.w.cust_a),
        "people": [
            {"name": "ZZT Staff", "phone": staff_contact.phone_number, "role": "employee"},
            {"name": "ZZT Good", "phone": good, "role": "employee"},
        ],
    })

    assert resp.status_code == 422, resp.text
    assert _find_rows(resp.json()) == [{"index": 0, "error": STAFF}]
    assert state(db, good) is None


def test_S4_http_a_foreign_account_id_is_422_pick_one_of_your_accounts(db, api):
    o = two_sales(db)
    phone = fake_phone()

    resp = api.as_user(o.s1).post(f"{BASE}/grant", json={
        "company": "SRT", "account_ids": ids_of(o.theirs),
        "people": [{"name": "ZZT Nobody", "phone": phone, "role": "employee"}],
    })

    assert resp.status_code == 422, resp.text
    assert PICK_OWN in resp.text
    assert_no_leak(resp.json(), o.theirs)
    assert state(db, phone) is None


@pytest.mark.parametrize("accounts,people", [(0, 1), (11, 1), (1, 0), (1, 21)])
def test_S4_http_the_form_bounds_are_422(db, api, accounts, people):
    o = two_sales(db)
    resp = api.as_user(o.s1).post(f"{BASE}/grant", json={
        "company": "SRT",
        "account_ids": [str(uuid.uuid4()) for _ in range(accounts)],
        "people": [{"name": f"ZZT P{i}", "phone": fake_phone(), "role": "employee"} for i in range(people)],
    })

    assert resp.status_code == 422, resp.text


# ================================================================== S5 update


def test_S5_the_link_diff_is_applied_to_my_accounts_of_the_company(db):
    o = two_sales(db)
    w = o.w
    person = dealer(db, w, customers=(w.cust_a, w.twin1), name="ZZT Edit Me")

    service().update(db, o.s1, str(person.id), "SRT", "employee", ids_of(w.twin1, w.twin2))

    assert links_of(db, person.id) == set(ids_of(w.twin1, w.twin2))


def test_S5_the_diff_never_touches_another_account_or_the_other_company(db):
    o = two_sales(db)
    w = o.w
    person = dealer(db, w, customers=(w.cust_a, o.theirs, w.cust_b), companies=(w.srt, w.mch), name="ZZT Edit Shared")

    service().update(db, o.s1, str(person.id), "SRT", "employee", ids_of(w.twin1))

    assert links_of(db, person.id) == set(ids_of(w.twin1, o.theirs, w.cust_b))


def test_S5_a_role_change_to_owner_adds_the_owner_tag_and_back_to_employee_removes_it(db):
    o = two_sales(db)
    w = o.w
    owner_tag(db, SRT_TAG)
    person = dealer(db, w, customers=(w.cust_a,), name="ZZT Role Change")

    service().update(db, o.s1, str(person.id), "SRT", "owner", ids_of(w.cust_a))
    assert SRT_TAG in tags_of(db, person.id)

    service().update(db, o.s1, str(person.id), "SRT", "employee", ids_of(w.cust_a))
    assert SRT_TAG not in tags_of(db, person.id)


def test_S5_a_shared_contact_with_an_unchanged_role_may_still_have_my_links_changed(db):
    o = two_sales(db)
    w = o.w
    person = dealer(db, w, customers=(w.cust_a, o.theirs), name="ZZT Shared Edit")

    service().update(db, o.s1, str(person.id), "SRT", "employee", ids_of(w.cust_a, w.twin1))

    assert links_of(db, person.id) == set(ids_of(w.cust_a, w.twin1, o.theirs))


@pytest.mark.parametrize("role", ["owner"])
def test_S5_promoting_a_shared_contact_is_refused_with_the_office_text(db, role):
    o = two_sales(db)
    w = o.w
    person = dealer(db, w, customers=(w.cust_a, o.theirs), name="ZZT Shared Promote")

    with pytest.raises(AppException) as err:
        service().update(db, o.s1, str(person.id), "SRT", role, ids_of(w.cust_a))

    assert err.value.status_code == 422 and err.value.message == DEMOTE_REFUSED
    assert SRT_TAG not in tags_of(db, person.id)
    assert_no_leak(err.value.detail, o.theirs)


def test_S5_demoting_a_shared_owner_is_refused_with_the_office_text(db):
    o = two_sales(db)
    w = o.w
    person = owner_dealer(db, w, customers=(w.cust_a, o.theirs), name="ZZT Shared Demote")

    with pytest.raises(AppException) as err:
        service().update(db, o.s1, str(person.id), "SRT", "employee", ids_of(w.cust_a))

    assert err.value.status_code == 422 and err.value.message == DEMOTE_REFUSED
    assert SRT_TAG in tags_of(db, person.id)


def test_S5_a_contact_not_in_my_scope_is_404_and_reads_like_one_that_does_not_exist(db):
    o = two_sales(db)
    w = o.w
    theirs_only = dealer(db, w, customers=(o.theirs,), name="ZZT Not Mine")

    with pytest.raises(AppException) as hidden:
        service().update(db, o.s1, str(theirs_only.id), "SRT", "employee", ids_of(w.cust_a))
    with pytest.raises(AppException) as gone:
        service().update(db, o.s1, str(uuid.uuid4()), "SRT", "employee", ids_of(w.cust_a))

    assert hidden.value.status_code == gone.value.status_code == 404
    assert hidden.value.message == gone.value.message
    assert links_of(db, theirs_only.id) == {str(o.theirs.id)}


def test_S5_my_own_contact_is_404(db):
    o = two_sales(db)
    link_to(db, o.w.contact["pk"], o.w.cust_a)

    with pytest.raises(AppException) as err:
        service().update(db, o.s1, str(o.w.contact["pk"]), "SRT", "employee", ids_of(o.w.twin1))

    assert err.value.status_code == 404


def test_S5_an_account_that_is_not_mine_is_422_pick_one_of_your_accounts_and_nothing_changes(db):
    o = two_sales(db)
    w = o.w
    person = dealer(db, w, customers=(w.cust_a,), name="ZZT Edit Foreign")

    with pytest.raises(AppException) as err:
        service().update(db, o.s1, str(person.id), "SRT", "employee", ids_of(w.cust_a, o.theirs))

    assert err.value.status_code == 422 and PICK_OWN in err.value.message
    assert links_of(db, person.id) == {str(w.cust_a.id)}


def test_S5_empty_account_ids_is_422_pick_one_of_your_accounts(db):
    o = two_sales(db)
    person = dealer(db, o.w, customers=(o.w.cust_a,), name="ZZT Edit Empty")

    with pytest.raises(AppException) as err:
        service().update(db, o.s1, str(person.id), "SRT", "employee", [])

    assert err.value.status_code == 422 and PICK_OWN in err.value.message
    assert links_of(db, person.id) == {str(o.w.cust_a.id)}


def test_S5_http_put_applies_the_diff_and_a_foreign_contact_is_404(db, api):
    o = two_sales(db)
    w = o.w
    person = dealer(db, w, customers=(w.cust_a,), name="ZZT Http Edit")
    theirs_only = dealer(db, w, customers=(o.theirs,), name="ZZT Http Not Mine")
    client = api.as_user(o.s1)

    ok = client.put(f"{BASE}/people/{person.id}", json={"company": "SRT", "role": "employee", "account_ids": ids_of(w.twin1)})
    assert ok.status_code == 200, ok.text
    assert links_of(db, person.id) == {str(w.twin1.id)}

    hidden = client.put(
        f"{BASE}/people/{theirs_only.id}", json={"company": "SRT", "role": "employee", "account_ids": ids_of(w.cust_a)}
    )
    assert hidden.status_code == 404, hidden.text
    assert_no_leak(hidden.json(), o.theirs)

    empty = client.put(f"{BASE}/people/{person.id}", json={"company": "SRT", "role": "employee", "account_ids": []})
    assert empty.status_code == 422, empty.text


# ================================================================== S6 deferred unlink


def park(client, link_id, key="dealer_access_link.unlink"):
    return client.post(
        "/api/v1/pending-actions",
        json={"action_key": key, "entity_type": "dealer_access_link", "entity_id": str(link_id), "payload": {}},
    )


def commit(client, db, parked, link_id) -> dict:
    """Lapse the window; the lazy commit on the `current` poll applies it, as the screen's poll would."""
    from app.models.sla import SlaFormAction

    assert parked.status_code == 202, parked.text
    db.query(SlaFormAction).filter(SlaFormAction.id == parked.json()["id"]).update(
        {"commit_at": datetime.utcnow() - timedelta(seconds=1)}, synchronize_session=False
    )
    db.commit()
    resp = client.get(
        "/api/v1/pending-actions/current", params={"entity_type": "dealer_access_link", "entity_id": str(link_id)}
    )
    return resp.json()


def test_S6_the_unlink_action_is_registered_reversible_and_gated():
    from app.services.form_action_grace import WINDOW_REVERSIBLE
    from app.services.form_action_registry import get_action

    action = get_action("dealer_access_link.unlink")

    assert action is not None, "dealer_access_link.unlink is not registered"
    assert action.permission == EDIT_OWN
    assert tuple(action.entity_types) == ("dealer_access_link",)
    assert action.window == WINDOW_REVERSIBLE


def test_S6_parking_and_committing_as_the_requester_removes_the_link_and_audits_me(db, api):
    o = two_sales(db)
    w = o.w
    person = dealer(db, w, customers=(w.cust_a, w.twin1), name="ZZT Unlink Me")
    link = link_row(db, person.id, w.cust_a.id)
    client = api.as_user(o.s1)

    parked = park(client, link.id)
    assert parked.status_code == 202, parked.text
    outcome = commit(client, db, parked, link.id)

    assert outcome["last_outcome"]["status"] == "committed", outcome
    assert links_of(db, person.id) == {str(w.twin1.id)}
    audit = events(db, person.id)
    assert len(audit) == 1 and str(audit[0].user_id) == str(o.s1)


def test_S6_unlinking_the_last_link_turns_ai_replies_off(db, api):
    o = two_sales(db)
    w = o.w
    person = ai_on(db, dealer(db, w, customers=(w.cust_a,), name="ZZT Last Link"))
    link = link_row(db, person.id, w.cust_a.id)
    client = api.as_user(o.s1)

    parked = park(client, link.id)
    assert parked.status_code == 202, parked.text
    outcome = commit(client, db, parked, link.id)

    assert outcome["last_outcome"]["status"] == "committed", outcome
    after = state(db, person.phone_number)
    assert after["links"] == [] and after["chatbot_allowed"] is False


def test_S6_unlinking_one_of_two_links_leaves_ai_replies_on(db, api):
    o = two_sales(db)
    w = o.w
    person = ai_on(db, dealer(db, w, customers=(w.cust_a, w.twin1), name="ZZT Two Links"))
    link = link_row(db, person.id, w.cust_a.id)
    client = api.as_user(o.s1)

    outcome = commit(client, db, park(client, link.id), link.id)

    assert outcome["last_outcome"]["status"] == "committed", outcome
    assert state(db, person.phone_number)["chatbot_allowed"] is True


def test_S6_a_link_still_held_by_the_other_salesperson_keeps_ai_replies_on(db, api):
    o = two_sales(db)
    w = o.w
    person = ai_on(db, dealer(db, w, customers=(w.cust_a, o.theirs), name="ZZT Shared Unlink"))
    link = link_row(db, person.id, w.cust_a.id)
    client = api.as_user(o.s1)

    outcome = commit(client, db, park(client, link.id), link.id)

    assert outcome["last_outcome"]["status"] == "committed", outcome
    after = state(db, person.phone_number)
    assert after["links"] == [str(o.theirs.id)] and after["chatbot_allowed"] is True


def test_S6_parking_a_link_of_the_other_salespersons_account_is_404(db, api):
    o = two_sales(db)
    person = shared_dealer(db, o)
    theirs_link = link_row(db, person.id, o.theirs.id)

    resp = park(api.as_user(o.s1), theirs_link.id)

    assert resp.status_code == 404, resp.text
    assert resp.json() != {"detail": "Not Found"}, "a missing route, not the domain 404"
    assert_no_leak(resp.json(), o.theirs)
    assert str(o.theirs.id) in links_of(db, person.id)


def test_S6_parking_an_unknown_link_and_my_own_contacts_link_is_404(db, api):
    o = two_sales(db)
    own_link = link_to(db, o.w.contact["pk"], o.w.cust_a)
    client = api.as_user(o.s1)

    unknown = park(client, uuid.uuid4())
    own = park(client, own_link.id)

    assert unknown.status_code == 404 and unknown.json() != {"detail": "Not Found"}, unknown.text
    assert own.status_code == 404, own.text


def test_S6_a_link_that_stopped_being_mine_during_the_window_fails_at_commit_and_stays(db, api):
    o = two_sales(db)
    w = o.w
    person = dealer(db, w, customers=(w.cust_a,), name="ZZT Reassigned")
    link = link_row(db, person.id, w.cust_a.id)
    client = api.as_user(o.s1)
    parked = park(client, link.id)
    assert parked.status_code == 202, parked.text
    with company_scope(db, None):
        db.query(Customer).filter(Customer.id == w.cust_a.id).update({"sales_agent_id": o.other.id})
    db.commit()

    outcome = commit(client, db, parked, link.id)

    assert outcome["last_outcome"]["status"] == "failed", outcome
    assert links_of(db, person.id) == {str(w.cust_a.id)}


# ================================================================== S7 one write path


def spy(monkeypatch, module, name):
    calls: list = []
    real = getattr(module, name)

    def wrapper(*args, **kwargs):
        calls.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(module, name, wrapper)
    return calls


def test_S7_grant_executes_each_person_through_the_agents_contact_grant_execute(db, monkeypatch):
    from app.services.chatbot.agent import contact_grant

    o = two_sales(db)
    executed = spy(monkeypatch, contact_grant, "_execute")
    planned = spy(monkeypatch, contact_grant, "plan")

    service().grant(db, o.s1, "SRT", ids_of(o.w.cust_a), [
        person_of(fake_phone(), name="ZZT Seven A"), person_of(fake_phone(), name="ZZT Seven B"),
    ])

    assert len(executed) == 2
    assert len(planned) >= 2  # every row checked with the grant plan
    for call in executed:
        args = call[2]
        assert args["companies"] == ["SRT"] and args["customer_codes"] == [o.w.cust_a.customer_code]


def test_S7_a_refused_form_runs_the_plan_for_the_rows_and_executes_nothing(db, monkeypatch):
    from app.services.chatbot.agent import contact_grant

    o = two_sales(db)
    executed = spy(monkeypatch, contact_grant, "_execute")
    phone = fake_phone()

    with pytest.raises(AppException):
        service().grant(db, o.s1, "SRT", ids_of(o.w.cust_a), [person_of(phone), person_of(phone)])

    assert executed == []


def test_S7_update_links_through_the_grant_and_calls_the_access_update_only_for_unlinks_or_a_role(db, monkeypatch):
    from app.services.chatbot.agent import contact_grant, writes

    o = two_sales(db)
    w = o.w
    person = dealer(db, w, customers=(w.cust_a,), name="ZZT Seven Update")
    granted = spy(monkeypatch, contact_grant, "_execute")
    changed = spy(monkeypatch, writes, "_contact_execute")

    service().update(db, o.s1, str(person.id), "SRT", "employee", ids_of(w.cust_a, w.twin1))

    assert len(granted) == 1
    args = granted[0][2]
    assert args["role"] == "employee" and args["companies"] == ["SRT"]
    assert args["customer_codes"] == [w.twin1.customer_code]
    assert changed == []  # nothing to unlink and the role did not differ


def test_S7_update_sends_the_role_only_when_it_differs_and_unlinks_my_unpicked_accounts(db, monkeypatch):
    from app.services.chatbot.agent import writes

    o = two_sales(db)
    w = o.w
    owner_tag(db, SRT_TAG)
    person = dealer(db, w, customers=(w.cust_a, w.twin1), name="ZZT Seven Role")
    executed = spy(monkeypatch, writes, "_contact_execute")

    service().update(db, o.s1, str(person.id), "SRT", "owner", ids_of(w.twin1))

    args = executed[0][2]
    assert args["role"] == "owner"
    assert args["unlink_customer_ids"] == [str(w.cust_a.id)]


def test_S7_the_unlink_action_commits_through_the_agents_contact_execute(db, api, monkeypatch):
    from app.services.chatbot.agent import writes

    o = two_sales(db)
    w = o.w
    person = dealer(db, w, customers=(w.cust_a, w.twin1), name="ZZT Seven Unlink")
    link = link_row(db, person.id, w.cust_a.id)
    executed = spy(monkeypatch, writes, "_contact_execute")
    client = api.as_user(o.s1)

    outcome = commit(client, db, park(client, link.id), link.id)

    assert outcome["last_outcome"]["status"] == "committed", outcome
    assert len(executed) == 1
    assert executed[0][2]["unlink_customer_ids"] == [str(w.cust_a.id)]


def test_S7_the_route_module_writes_nothing_itself():
    path = Path(__file__).resolve().parents[3] / "app" / "api" / "v1" / "sales" / "dealer_access.py"
    source = path.read_text()

    for forbidden in (
        ".add(", ".commit(", ".delete(", "link_customer", "unlink_customer", "change_tags", "access_types",
        "RespondContactCustomer(", "chatbot_allowed",
    ):
        assert forbidden not in source, f"the route module must not write a contact itself: {forbidden!r}"
    assert "require_permission" in source and "user_management.contacts.edit_own" in source


# ================================================================== S8 two-company salesperson (all granted companies)


def set_active(db, uid, company_id) -> None:
    from app.models.user import User

    with company_scope(db, None):
        db.query(User).filter(User.id == uid).update({"last_active_company_id": company_id})
    db.commit()


def both_companies_person(db, o, name, types=("end_user",)):
    return dealer(db, o.w, types=types, customers=(o.w.cust_a, o.w.cust_b), companies=(o.w.srt, o.w.mch), name=name)


def test_S8_with_sorento_active_a_person_linked_only_to_my_mocha_account_can_be_edited_and_unlinked(db, api_active):
    o = two_sales(db)
    w = o.w
    set_active(db, o.s1, w.srt)
    owner_tag(db, MCH_TAG)
    person = dealer(db, w, types=("end_user",), customers=(w.cust_b,), companies=(w.mch,), name="ZZT Mocha Only")
    link = link_row(db, person.id, w.cust_b.id)

    service().update(db, o.s1, str(person.id), "MCH", "owner", ids_of(w.cust_b))
    assert MCH_TAG in tags_of(db, person.id)

    client = api_active.as_user(o.s1)
    outcome = commit(client, db, park(client, link.id), link.id)

    assert outcome["last_outcome"]["status"] == "committed", outcome
    assert links_of(db, person.id) == set()


@pytest.mark.parametrize("active", ["srt", "mch"])
def test_S8_a_person_linked_to_my_sorento_and_my_mocha_accounts_is_not_another_account(db, active):
    o = two_sales(db)
    w = o.w
    set_active(db, o.s1, getattr(w, active))
    owner_tag(db, SRT_TAG)
    person = both_companies_person(db, o, "ZZT Both Mine")

    rows = person_rows(db, o.s1)
    assert rows and all(r["other_account"] is False for r in rows)

    service().update(db, o.s1, str(person.id), "SRT", "owner", ids_of(w.cust_a))

    assert SRT_TAG in tags_of(db, person.id)


# ================================================================== S5 the level is per company


def test_S5_demoting_on_the_sorento_row_leaves_the_mocha_owner_tag_and_types(db):
    from app.models.access import ContactAccessType  # noqa: F401

    o = two_sales(db)
    w = o.w
    owner_tag(db, SRT_TAG)
    owner_tag(db, MCH_TAG)
    person = both_companies_person(
        db, o, "ZZT Owner Of Both", types=("end_user", "dealer", "cabana_dealer", "mocha_dealer")
    )
    tag_contact(db, person.id, owner_tag(db, SRT_TAG))
    tag_contact(db, person.id, owner_tag(db, MCH_TAG))
    service().update(db, o.s1, str(person.id), "SRT", "employee", ids_of(w.cust_a))

    assert tags_of(db, person.id) == [MCH_TAG]
    types = state(db, person.phone_number)["types"]
    assert "mocha_dealer" in types
    assert not ({"dealer", "cabana_dealer"} & set(types))


def test_S5_promoting_on_the_sorento_row_adds_only_the_sorento_tag(db):
    o = two_sales(db)
    w = o.w
    owner_tag(db, SRT_TAG)
    owner_tag(db, MCH_TAG)
    person = both_companies_person(db, o, "ZZT Promote Sorento Only")

    service().update(db, o.s1, str(person.id), "SRT", "owner", ids_of(w.cust_a))

    assert tags_of(db, person.id) == [SRT_TAG]
    assert "mocha_dealer" not in state(db, person.phone_number)["types"]


def test_S8_update_unlinking_my_mocha_account_with_a_sorento_only_request_scope(db):
    o = two_sales(db)
    w = o.w
    set_active(db, o.s1, w.srt)
    extra = add_customer(db, w, unique_code("ZZT Extra Mocha"), company=w.mch)
    person = dealer(db, w, customers=(w.cust_b, extra), companies=(w.mch,), name="ZZT Two Mocha Accounts")
    set_company_scope(db, frozenset({w.srt}))

    service().update(db, o.s1, str(person.id), "MCH", "employee", ids_of(extra))

    assert links_of(db, person.id) == {str(extra.id)}


def test_S8_grant_for_mocha_with_a_sorento_only_request_scope(db):
    o = two_sales(db)
    w = o.w
    set_active(db, o.s1, w.srt)
    phone = fake_phone()
    set_company_scope(db, frozenset({w.srt}))

    out = service().grant(db, o.s1, "MCH", ids_of(w.cust_b), [person_of(phone, name="ZZT Mocha New")])

    assert out["rows"][0]["created"] is True
    assert state(db, phone)["links"] == [str(w.cust_b.id)]


# ================================================================== S5 the level is the owner TAG


NOTHING = "Nothing to change"
LEGACY_TYPES = ("end_user", "dealer", "cabana_dealer")


def legacy_dealer(db, o, *, customers, name="ZZT Legacy Dealer"):
    """Dealer types but no owner tag: the 33 of 44 real rows the crew found."""
    owner_tag(db, SRT_TAG)
    return dealer(db, o.w, types=LEGACY_TYPES, customers=customers, name=name)


def test_S5_tag_a_contact_with_dealer_types_but_no_owner_tag_lists_as_employee_and_promote_adds_the_tag(db):
    o = two_sales(db)
    w = o.w
    person = legacy_dealer(db, o, customers=(w.cust_a,))

    assert [r["access"] for r in person_rows(db, o.s1)] == ["employee"]
    service().update(db, o.s1, str(person.id), "SRT", "owner", ids_of(w.cust_a))

    assert SRT_TAG in tags_of(db, person.id)
    assert [r["access"] for r in person_rows(db, o.s1)] == ["owner"]


def test_S5_tag_demoting_that_contact_removes_the_dealer_types_and_keeps_end_user(db):
    o = two_sales(db)
    w = o.w
    person = legacy_dealer(db, o, customers=(w.cust_a,))

    out = service().update(db, o.s1, str(person.id), "SRT", "employee", ids_of(w.cust_a))

    assert out["id"] == str(person.id)
    assert state(db, person.phone_number)["types"] == ["end_user"]


def test_S5_tag_the_agent_demote_of_that_contact_removes_the_dealer_types(db):
    from app.services.chatbot.agent import writes

    o = two_sales(db)
    w = o.w
    person = legacy_dealer(db, o, customers=(w.cust_a,))
    user = _load_user_dict_from_db(db, o.s1)

    out = writes._contact_execute(db, user, {"contact_id": str(person.id), "role": "employee"})

    assert out["id"] == str(person.id)
    assert state(db, person.phone_number)["types"] == ["end_user"]


def test_S5_tag_promoting_that_contact_when_another_salesperson_also_has_it_is_refused(db):
    o = two_sales(db)
    w = o.w
    person = legacy_dealer(db, o, customers=(w.cust_a, o.theirs))

    with pytest.raises(AppException) as err:
        service().update(db, o.s1, str(person.id), "SRT", "owner", ids_of(w.cust_a))

    assert err.value.status_code == 422 and err.value.message == DEMOTE_REFUSED
    assert SRT_TAG not in tags_of(db, person.id)


def test_S5_tag_a_contact_that_already_holds_the_tag_has_nothing_to_promote(db):
    from app.services.chatbot.agent import writes

    o = two_sales(db)
    w = o.w
    person = owner_dealer(db, w, customers=(w.cust_a,), name="ZZT Already Owner")
    user = _load_user_dict_from_db(db, o.s1)

    with pytest.raises(AppException) as err:
        writes._contact_execute(db, user, {"contact_id": str(person.id), "role": "owner"})

    assert NOTHING in err.value.message


def test_S6_an_admin_viewing_as_the_salesperson_is_the_real_user_of_the_unlink_audit(db, api):
    o = two_sales(db)
    w = o.w
    admin = make_world(db, slugs=(NEITHER,), superadmin=True).user_id
    person = dealer(db, w, customers=(w.cust_a, w.twin1), name="ZZT Viewed As")
    link = link_row(db, person.id, w.cust_a.id)
    client = api.as_user(o.s1)

    def impersonated(request: Request):
        request.state.real_user = {"id": admin}
        return _load_user_dict_from_db(db, o.s1)

    app.dependency_overrides[get_current_user] = impersonated
    try:
        outcome = commit(client, db, park(client, link.id), link.id)
    finally:
        clear_actor()

    assert outcome["last_outcome"]["status"] == "committed", outcome
    audit = events(db, person.id)
    assert len(audit) == 1
    assert str(audit[0].user_id) == str(o.s1) and str(audit[0].real_user_id) == str(admin)
