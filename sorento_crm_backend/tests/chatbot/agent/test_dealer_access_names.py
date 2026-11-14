"""DEALER-ACCESS-NAMES N1-N5 (UAC `documentation/plans/contacts/dealer-access-names-14nov-acceptance-criteria.md`).

Red tests, written before the implementation. Each test name carries its UAC id. Backend of the salesperson
"Dealer access" screen after the 14 Nov owner answers: the wider list (`mine`), the Customer filter, Add people for
several companies with the "already has access" refusal, and Respond.io in the request (logged, retryable).

World (`names_world`): salesperson 1 (`o.s1`, `user_management.contacts.edit_own` only) owns `cust_a`, `twin1`,
`twin2` (Sorento) and `cust_b` (Mocha); salesperson 2 (`o.s2`) owns `theirs` (Sorento) and `theirs_m` (Mocha).
"ZZT Ali Test" is linked to `cust_a` and `theirs`; "ZZT Chong Test" to `theirs` only; "ZZT Dan Test" has no customer
link. `hidden_shop` is a customer of a company salesperson 1 is NOT granted. Postgres only (blank schema), every test
seeds its own chain. Names, phones and codes are invented (public repo). Respond.io is a fake (N5.6): every
`RespondClient` HTTP path is replaced, and with `respond.key = False` (the default) no client has an API key.

Contract shapes the tests pin (from the plan's Design section; flagged in the red-run report):
- `dealer_access_screen.list_people(db, uid, *, mine=True, customer_ids=None, companies, access, query, page, limit)`;
  rows carry `editable` and `in_respond`, no `other_account`; each account carries `mine` and, only when mine,
  `link_id`.
- `dealer_access_screen.customers(db, uid, *, query=None, mine=True, companies=None)` -> list of
  `{id, code, name, company}` (company = the company CODE).
- `dealer_access_screen.grant(db, uid, companies, account_ids, people)`: `companies` is a list of codes (a bare code
  string is the legacy single company). Result rows carry `respond` ("ok" | "failed") and `respond_error`.
- Refusal rows: `exc.detail["details"]["rows"][i] == {index, error, contact}`, `contact` None unless N4.3 visible.
- `dealer_access_screen.respond_retry(db, uid, contact_id)` -> `{respond, respond_error}`; route
  `POST /api/v1/sales/dealer-access/people/{contact_id}/respond`.
- `app.services.respond_contact_ensure.ensure_in_respond(db, contact_id)` -> `{status, error}`, the ONE shared
  function; `app.tasks.respond_io_tasks.ensure_respond_contact(contact_id)` calls it.
"""
from __future__ import annotations

import itertools
import uuid
from types import SimpleNamespace

import httpx
import pytest

import app.main  # noqa: F401  register every model and the app's listeners
from app.audit_context import clear_actor
from app.models.access import RespondContact
from app.models.base import company_scope
from app.models.company import UserCompany
from app.models.integration import IntegrationLog
from app.models.order import Customer
from app.services.audit_service import register_audit_listeners
from app.services.company_scope import register_company_scope_listeners
from app.services.error_handler import AppException
from app.main import app
from tests._ask_todo_seed import customer as seed_customer
from tests._pg_fixture import blank_session, unique_code
from tests.chatbot.agent._seed import seed_user
from tests.chatbot.agent.test_agent_bulk_grant import dealer, fake_phone, make_world, state
from tests.chatbot.agent.test_dealer_access_agent import (
    MCH_TAG,
    NEITHER,
    SRT_TAG,
    STAFF,
    _SharedSession,
    _http_error,
    add_customer,
    owner_tag,
    tag_contact,
    tags_of,
)
from tests.chatbot.agent.test_dealer_access_screen import (
    _api_client,
    _find_rows,
    _unwrap,
    assert_no_leak,
    ids_of,
    link_row,
    link_to,
    links_of,
    person_of,
    refusal_rows,
    respond_jobs,
    two_sales,
)

BASE = "/api/v1/sales/dealer-access"
PICK_OWN = "Pick one of your accounts."
OTHER_COMPANY = "This number already has access in another company."
PEOPLE_KEYS = {
    "contact_id", "name", "phone", "company", "company_name", "accounts", "access", "owner_tag", "editable",
    "in_respond",
}
_ids = itertools.count(910000001)


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


@pytest.fixture(autouse=True)
def respond(monkeypatch, db):
    """N5.6: a fake Respond.io. `key` (default False) decides whether any client has an API key; `lookup` decides what
    `get_contact_by_phone` does: "found", "missing" (404), "error" (HTTP 500) or "timeout". A raw HTTP client fails the
    test. `job(contact_id)` runs the worker task in-process on the test session."""
    import app.database as database
    from app.services import integration_service
    from app.services.integration_service import RespondClient

    rec = SimpleNamespace(calls=[], forbidden=[], lookup="found", key=False, ids={})

    def creds(*_a, **_k):
        return ("zzt-test-key", "https://respond.invalid", None) if rec.key else None

    monkeypatch.setattr(integration_service, "_resolve_workspace_credentials", creds)
    monkeypatch.setattr(integration_service.settings, "respond_api_key", None, raising=False)

    def forbid(name):
        def _f(*a, **k):
            rec.forbidden.append(name)
            raise AssertionError(f"RespondClient.{name} must not be called")
        return _f

    monkeypatch.setattr(RespondClient, "_http", staticmethod(forbid("_http")))
    for name in dir(RespondClient):
        if "send" in name or name == "_post_contact_message":
            monkeypatch.setattr(RespondClient, name, forbid(name))

    def _new_id(phone):
        rec.ids.setdefault(phone, next(_ids))
        return rec.ids[phone]

    def get_by_phone(self, phone):
        rec.calls.append(("get_contact_by_phone", phone))
        if not self.api_key:
            raise ValueError("Respond API key is not configured.")
        if rec.lookup == "found":
            return {"id": _new_id(phone), "phone": phone}
        if rec.lookup == "timeout":
            raise httpx.ReadTimeout("timed out", request=httpx.Request("GET", "https://respond.invalid/v2/contact/x"))
        raise _http_error(404 if rec.lookup == "missing" else 500)

    def create(self, phone, first_name=None, *a, **k):
        rec.calls.append(("create_contact", phone, first_name))
        return {"id": _new_id(phone)}

    def update(self, identifier, payload):
        rec.calls.append(("update_contact", identifier, payload))
        return {}

    monkeypatch.setattr(RespondClient, "get_contact_by_phone", get_by_phone)
    monkeypatch.setattr(RespondClient, "get_contact_by_identifier", forbid("get_contact_by_identifier"))
    monkeypatch.setattr(RespondClient, "create_contact", create, raising=False)
    monkeypatch.setattr(RespondClient, "update_contact", update)
    monkeypatch.setattr(database, "SessionLocal", lambda *a, **k: _SharedSession(db))

    def job(contact_id: str):
        import app.tasks.respond_io_tasks as tasks

        monkeypatch.setattr(tasks, "SessionLocal", lambda *a, **k: _SharedSession(db), raising=False)
        return tasks.ensure_respond_contact(contact_id)

    rec.job = job
    return rec


@pytest.fixture()
def api(db):
    try:
        yield _api_client(db, active_only=False)
    finally:
        app.dependency_overrides.clear()


# ------------------------------------------------------------------ seeding / helpers


def names_world(db) -> SimpleNamespace:
    o = two_sales(db)
    w = o.w
    o.ali = dealer(db, w, customers=(w.cust_a, o.theirs), name="ZZT Ali Test")
    o.chong = dealer(db, w, customers=(o.theirs,), name="ZZT Chong Test")
    o.dan = dealer(db, w, customers=(), name="ZZT Dan Test")
    o.hidden_shop = add_customer(db, w, unique_code("ZZT Hidden Shop"), agent=o.other, company=w.hidden)
    return o


def service():
    from app.services import dealer_access_screen

    return dealer_access_screen


def rows_of(db, uid, **kw) -> list[dict]:
    return service().list_people(db, uid, **kw)["rows"]


def by_contact(rows, company="SRT") -> dict[str, dict]:
    return {r["contact_id"]: r for r in rows if r["company"] == company}


def deactivate(db, customer) -> None:
    with company_scope(db, None):
        db.query(Customer).filter(Customer.id == customer.id).update({"is_active": False})
    db.commit()


def logs_of(db, contact_id) -> list[IntegrationLog]:
    db.expire_all()
    with company_scope(db, None):
        return (
            db.query(IntegrationLog)
            .filter(IntegrationLog.business_id == str(contact_id))
            .order_by(IntegrationLog.created_at)
            .all()
        )


def assert_logged(rows, n: int) -> None:
    assert len(rows) == n, [(r.endpoint, r.status) for r in rows]
    for r in rows:
        assert r.integration_channel == "respond_io"
        assert r.business_table == "respond_contacts"


def respond_id_of(db, contact_id):
    db.expire_all()
    with company_scope(db, None):
        return db.query(RespondContact.respond_io_id).filter(RespondContact.id == str(contact_id)).scalar()


def backend_id_written(rec) -> bool:
    return any(c[0] == "update_contact" and "backend_id" in str(c[2]) for c in rec.calls)


def assert_plain(text) -> None:
    assert isinstance(text, str) and text.strip(), text
    for raw in ("Traceback", "HTTPStatusError", "respond.invalid", "ReadTimeout", "Exception"):
        assert raw not in text, f"respond_error is not plain words: {text!r}"


def brief(rows) -> list[dict]:
    return [{"index": r["index"], "error": r["error"]} for r in rows]


# ================================================================== N2 the list


def test_N2_1_default_mine_lists_contacts_of_my_own_accounts_only(db):
    o = names_world(db)

    default = rows_of(db, o.s1)
    mine = rows_of(db, o.s1, mine=True)

    assert default == mine
    assert {r["contact_id"] for r in default} == {str(o.ali.id)}
    assert str(o.chong.id) not in {r["contact_id"] for r in default}


def test_N2_1_one_row_per_contact_and_company_under_mine(db):
    o = names_world(db)
    w = o.w
    both = dealer(db, w, customers=(w.cust_a, w.cust_b), companies=(w.srt, w.mch), name="ZZT Both Co")

    rows = [r for r in rows_of(db, o.s1) if r["contact_id"] == str(both.id)]

    assert sorted(r["company"] for r in rows) == ["MCH", "SRT"]


def test_N2_2_mine_false_lists_every_contact_of_an_active_customer_of_my_granted_companies(db):
    o = names_world(db)
    w = o.w
    hidden_person = dealer(db, w, customers=(o.hidden_shop,), companies=(w.hidden,), name="ZZT Hidden Person")
    gone = add_customer(db, w, unique_code("ZZT Closed Shop"), agent=o.other)
    deactivate(db, gone)
    inactive_only = dealer(db, w, customers=(gone,), name="ZZT Inactive Only")

    rows = rows_of(db, o.s1, mine=False)

    srt = by_contact(rows)
    assert {str(o.ali.id), str(o.chong.id)} <= set(srt)
    seen = {r["contact_id"] for r in rows}
    assert str(hidden_person.id) not in seen
    assert str(inactive_only.id) not in seen
    assert str(o.dan.id) not in seen
    assert all(r["company"] in {"SRT", "MCH"} for r in rows)
    assert_no_leak(rows, o.hidden_shop)


def test_N2_2_mine_false_never_shows_a_company_i_am_not_granted(db):
    o = names_world(db)
    w = o.w
    mocha_person = dealer(db, w, customers=(o.theirs_m,), companies=(w.mch,), name="ZZT Mocha Theirs")
    assert str(mocha_person.id) in {r["contact_id"] for r in rows_of(db, o.s1, mine=False)}
    with company_scope(db, None):
        db.query(UserCompany).filter(UserCompany.user_id == o.s1, UserCompany.company_id == w.mch).delete()
    db.commit()

    rows = rows_of(db, o.s1, mine=False)

    assert str(mocha_person.id) not in {r["contact_id"] for r in rows}
    assert all(r["company"] != "MCH" for r in rows)


def test_N2_2_my_own_contact_never_appears_with_mine_false(db):
    o = names_world(db)
    link_to(db, o.w.contact["pk"], o.theirs)

    rows = rows_of(db, o.s1, mine=False)

    assert str(o.w.contact["pk"]) not in {r["contact_id"] for r in rows}


@pytest.mark.parametrize("mine", [True, False])
def test_N2_3_accounts_list_every_active_linked_customer_with_mine_and_link_id_only_when_mine(db, mine):
    o = names_world(db)
    w = o.w
    gone = add_customer(db, w, unique_code("ZZT Closed Too"), agent=o.other)
    link_to(db, o.ali.id, gone)
    deactivate(db, gone)

    row = by_contact(rows_of(db, o.s1, mine=mine))[str(o.ali.id)]

    accounts = {a["id"]: a for a in row["accounts"]}
    assert set(accounts) == set(ids_of(w.cust_a, o.theirs))
    own, other = accounts[str(w.cust_a.id)], accounts[str(o.theirs.id)]
    assert own["mine"] is True and own["link_id"] == link_row(db, o.ali.id, w.cust_a.id).id
    assert own["code"] == w.cust_a.customer_code and own["name"] == w.cust_a.customer_name
    assert other["mine"] is False
    assert other.get("link_id") is None
    assert other["code"] == o.theirs.customer_code and other["name"] == o.theirs.customer_name
    assert link_row(db, o.ali.id, o.theirs.id).id not in str(row)


def test_N2_4_rows_carry_editable_from_contact_in_scope(db):
    o = names_world(db)

    srt = by_contact(rows_of(db, o.s1, mine=False))

    assert set(srt[str(o.ali.id)]) == PEOPLE_KEYS
    assert srt[str(o.ali.id)]["editable"] is True
    assert srt[str(o.chong.id)]["editable"] is False


def test_N2_4_a_non_editable_contact_still_cannot_be_changed_or_unlinked(db, api):
    o = names_world(db)
    client = api.as_user(o.s1)

    put = client.put(f"{BASE}/people/{o.chong.id}", json={"company": "SRT", "role": "employee", "account_ids": ids_of(o.w.cust_a)})
    park = client.post("/api/v1/pending-actions", json={
        "action_key": "dealer_access_link.unlink", "entity_type": "dealer_access_link",
        "entity_id": link_row(db, o.chong.id, o.theirs.id).id, "payload": {},
    })

    assert put.status_code == 404, put.text
    assert park.status_code == 404, park.text
    assert links_of(db, o.chong.id) == {str(o.theirs.id)}


@pytest.mark.parametrize("mine", [True, False])
def test_N2_6_other_account_is_gone_from_every_row(db, mine):
    o = names_world(db)

    rows = rows_of(db, o.s1, mine=mine)

    assert rows
    for r in rows:
        assert "other_account" not in r
        assert set(r) == PEOPLE_KEYS


def test_N2_http_people_mine_false_and_default(db, api):
    o = names_world(db)
    client = api.as_user(o.s1)

    default = client.get(f"{BASE}/people")
    wide = client.get(f"{BASE}/people", params={"mine": "false"})

    assert default.status_code == 200 and wide.status_code == 200, wide.text
    d_rows = _unwrap(default.json())["rows"]
    w_rows = _unwrap(wide.json())["rows"]
    assert {r["contact_id"] for r in d_rows} == {str(o.ali.id)}
    assert {str(o.ali.id), str(o.chong.id)} <= {r["contact_id"] for r in w_rows}
    chong = next(r for r in w_rows if r["contact_id"] == str(o.chong.id))
    assert set(chong) == PEOPLE_KEYS and chong["editable"] is False
    assert all(a["mine"] is False and a.get("link_id") is None for a in chong["accounts"])


def test_N5_4_rows_carry_in_respond(db):
    o = names_world(db)
    with company_scope(db, None):
        db.query(RespondContact).filter(RespondContact.id == o.ali.id).update({"respond_io_id": "910999001"})
    db.commit()

    srt = by_contact(rows_of(db, o.s1, mine=False))

    assert srt[str(o.ali.id)]["in_respond"] is True
    assert srt[str(o.chong.id)]["in_respond"] is False


# ================================================================== N3 customer filter and search


def customers_of(db, uid, **kw) -> list[dict]:
    return service().customers(db, uid, **kw)


def test_N3_1_customers_mine_true_are_my_own_active_customers_with_id_code_name_company(db):
    o = names_world(db)
    w = o.w
    gone = add_customer(db, w, unique_code("ZZT Closed Mine"))
    deactivate(db, gone)

    out = customers_of(db, o.s1, mine=True)

    assert {c["id"] for c in out} == set(ids_of(w.cust_a, w.twin1, w.twin2, w.cust_b))
    assert set(out[0]) == {"id", "code", "name", "company"}
    by_id = {c["id"]: c for c in out}
    assert by_id[str(w.cust_a.id)]["company"] == "SRT" and by_id[str(w.cust_b.id)]["company"] == "MCH"
    assert by_id[str(w.cust_a.id)]["code"] == w.cust_a.customer_code
    assert [c["name"] for c in out] == sorted(c["name"] for c in out)
    assert_no_leak(out, o.theirs, o.theirs_m, o.hidden_shop, gone)


def test_N3_1_customers_mine_false_adds_every_active_customer_of_my_granted_companies(db):
    o = names_world(db)

    out = customers_of(db, o.s1, mine=False)

    ids = {c["id"] for c in out}
    assert set(ids_of(o.w.cust_a, o.theirs, o.theirs_m)) <= ids
    assert str(o.hidden_shop.id) not in ids


def test_N3_1_customers_match_name_or_code_case_insensitively_and_filter_by_company(db):
    o = names_world(db)
    w = o.w

    by_name = customers_of(db, o.s1, query=w.cust_a.customer_name.upper(), mine=True)
    by_code = customers_of(db, o.s1, query=w.cust_a.customer_code.lower(), mine=True)
    mocha = customers_of(db, o.s1, mine=True, companies=["MCH"])

    assert [c["id"] for c in by_name] == [str(w.cust_a.id)]
    assert [c["id"] for c in by_code] == [str(w.cust_a.id)]
    assert [c["id"] for c in mocha] == [str(w.cust_b.id)]


def test_N3_1_customers_are_capped_at_50_sorted_by_name(db):
    o = names_world(db)
    w = o.w
    from app.models.sales_agent import SalesAgent

    me = db.query(SalesAgent).filter(SalesAgent.contact_id == w.contact["pk"]).first()
    with company_scope(db, None):
        for i in range(55):
            seed_customer(db, f"ZZT Cap Shop {i:02d}", me, company_id=w.srt)
    db.commit()

    out = customers_of(db, o.s1, query="zzt cap shop", mine=True)

    assert len(out) == 50
    assert [c["name"] for c in out] == [f"ZZT Cap Shop {i:02d}" for i in range(50)]


def test_N3_1_http_customers_with_query_mine_and_company(db, api):
    o = names_world(db)
    client = api.as_user(o.s1)

    resp = client.get(f"{BASE}/customers", params=[("query", o.theirs.customer_name), ("mine", "false"), ("company", "SRT")])

    assert resp.status_code == 200, resp.text
    body = _unwrap(resp.json())
    assert [c["id"] for c in body] == [str(o.theirs.id)]
    assert body[0]["company"] == "SRT"


def test_N3_1_http_customers_is_403_without_edit_own(db, api):
    none = make_world(db, slugs=(NEITHER,), superadmin=False)

    resp = api.as_user(none.user_id).get(f"{BASE}/customers")

    assert resp.status_code == 403, resp.text


def test_N3_2_customer_filter_keeps_rows_linked_to_either_customer(db):
    o = names_world(db)
    w = o.w
    eve = dealer(db, w, customers=(w.twin1,), name="ZZT Eve Test")

    only_a = rows_of(db, o.s1, mine=False, customer_ids=ids_of(w.cust_a))
    either = rows_of(db, o.s1, mine=False, customer_ids=ids_of(w.twin1, o.theirs))

    assert {r["contact_id"] for r in only_a} == {str(o.ali.id)}
    assert {r["contact_id"] for r in either} == {str(o.ali.id), str(o.chong.id), str(eve.id)}


def test_N3_2_customer_filter_combines_with_company_access_and_query(db):
    o = names_world(db)
    w = o.w
    owner_tag(db, SRT_TAG)
    tag_contact(db, o.chong.id, owner_tag(db, SRT_TAG))

    with_query = rows_of(db, o.s1, mine=False, customer_ids=ids_of(o.theirs), query="chong")
    with_access = rows_of(db, o.s1, mine=False, customer_ids=ids_of(o.theirs), access="owner")
    with_company = rows_of(db, o.s1, mine=False, customer_ids=ids_of(w.cust_a), companies=["MCH"])

    assert [r["contact_id"] for r in with_query] == [str(o.chong.id)]
    assert [r["contact_id"] for r in with_access] == [str(o.chong.id)]
    assert with_company == []


def test_N3_2_a_customer_id_outside_what_i_may_see_returns_no_rows_not_an_error(db):
    o = names_world(db)
    w = o.w
    dealer(db, w, customers=(o.hidden_shop,), companies=(w.hidden,), name="ZZT Hidden Person")

    hidden = service().list_people(db, o.s1, mine=False, customer_ids=ids_of(o.hidden_shop))
    unknown = service().list_people(db, o.s1, mine=False, customer_ids=[str(uuid.uuid4())])

    assert hidden == {"rows": [], "total": 0}
    assert unknown == {"rows": [], "total": 0}


def test_N3_2_http_repeated_customer_param(db, api):
    o = names_world(db)
    w = o.w

    resp = api.as_user(o.s1).get(
        f"{BASE}/people", params=[("mine", "false"), ("customer", str(w.cust_a.id)), ("customer", str(o.theirs.id))]
    )

    assert resp.status_code == 200, resp.text
    rows = _unwrap(resp.json())["rows"]
    assert {r["contact_id"] for r in rows} == {str(o.ali.id), str(o.chong.id)}


def test_N3_4_search_matches_any_customer_name_or_code_of_the_row(db):
    o = names_world(db)
    w = o.w

    by_my_name = rows_of(db, o.s1, query=w.cust_a.customer_name)
    by_their_name = rows_of(db, o.s1, mine=False, query=o.theirs.customer_name.lower())
    by_their_code = rows_of(db, o.s1, mine=False, query=o.theirs.customer_code)

    assert {r["contact_id"] for r in by_my_name} == {str(o.ali.id)}
    assert {r["contact_id"] for r in by_their_name} == {str(o.ali.id), str(o.chong.id)}
    assert {r["contact_id"] for r in by_their_code} == {str(o.ali.id), str(o.chong.id)}


# ================================================================== N4 Add people


def test_N4_1_two_companies_grant_links_accounts_of_each_and_the_owner_level_applies_to_both(db):
    o = names_world(db)
    w = o.w
    owner_tag(db, SRT_TAG)
    owner_tag(db, MCH_TAG)
    phone = fake_phone()

    out = service().grant(db, o.s1, ["SRT", "MCH"], ids_of(w.cust_a, w.cust_b), [person_of(phone, name="ZZT Two Co", role="owner")])

    after = state(db, phone)
    assert after is not None
    assert after["links"] == sorted(ids_of(w.cust_a, w.cust_b))
    assert {SRT_TAG, MCH_TAG} <= set(tags_of(db, after["id"]))
    assert [r["index"] for r in out["rows"]] == [0]
    assert str(out["rows"][0]["contact_id"]) == after["id"]


def test_N4_1_every_picked_company_needs_one_of_my_accounts(db):
    o = names_world(db)
    phone = fake_phone()

    with pytest.raises(AppException) as err:
        service().grant(db, o.s1, ["SRT", "MCH"], ids_of(o.w.cust_a), [person_of(phone)])

    assert err.value.status_code == 422 and PICK_OWN in err.value.message
    assert state(db, phone) is None


def test_N4_1_an_account_of_a_company_not_picked_is_refused(db):
    o = names_world(db)
    phone = fake_phone()

    with pytest.raises(AppException) as err:
        service().grant(db, o.s1, ["SRT"], ids_of(o.w.cust_a, o.w.cust_b), [person_of(phone)])

    assert err.value.status_code == 422 and PICK_OWN in err.value.message
    assert state(db, phone) is None


def test_N4_1_http_grant_with_companies_list(db, api):
    o = names_world(db)
    w = o.w
    phone = fake_phone()

    resp = api.as_user(o.s1).post(f"{BASE}/grant", json={
        "companies": ["SRT", "MCH"], "account_ids": ids_of(w.cust_a, w.cust_b),
        "people": [{"name": "ZZT Http Two Co", "phone": phone, "role": "employee"}],
    })

    assert resp.status_code in (200, 201), resp.text
    assert state(db, phone)["links"] == sorted(ids_of(w.cust_a, w.cust_b))


def test_N4_1_http_legacy_single_company_still_accepted(db, api):
    o = names_world(db)
    phone = fake_phone()

    resp = api.as_user(o.s1).post(f"{BASE}/grant", json={
        "company": "SRT", "account_ids": ids_of(o.w.cust_a),
        "people": [{"name": "ZZT Http Legacy", "phone": phone, "role": "employee"}],
    })

    assert resp.status_code in (200, 201), resp.text
    assert state(db, phone)["links"] == [str(o.w.cust_a.id)]


@pytest.mark.parametrize("companies", [[], ["SRT", "MCH", "ZZH"]])
def test_N4_1_http_companies_must_be_one_or_two(db, api, companies):
    o = names_world(db)
    phone = fake_phone()

    resp = api.as_user(o.s1).post(f"{BASE}/grant", json={
        "companies": companies, "account_ids": ids_of(o.w.cust_a),
        "people": [{"name": "ZZT Bounds", "phone": phone, "role": "employee"}],
    })

    assert resp.status_code == 422, resp.text
    # Refused for its `companies`, not because the legacy `company` field is (still) required.
    assert '"loc":["body","company"]' not in resp.text.replace(" ", ""), resp.text
    assert state(db, phone) is None


def test_N4_1_http_no_company_at_all_is_422(db, api):
    o = names_world(db)

    resp = api.as_user(o.s1).post(f"{BASE}/grant", json={
        "account_ids": ids_of(o.w.cust_a), "people": [{"name": "ZZT None", "phone": fake_phone(), "role": "employee"}],
    })

    assert resp.status_code == 422, resp.text


def _order_spy(monkeypatch):
    from app.services.chatbot.agent import contact_grant

    events: list[tuple[str, dict]] = []
    real_plan, real_exec = contact_grant.plan, contact_grant._execute

    def plan(db, user, args, *a, **k):
        events.append(("plan", args))
        return real_plan(db, user, args, *a, **k)

    def execute(db, user, args, *a, **k):
        events.append(("execute", args))
        return real_exec(db, user, args, *a, **k)

    monkeypatch.setattr(contact_grant, "plan", plan)
    monkeypatch.setattr(contact_grant, "_execute", execute)
    return events


def test_N4_2_the_same_grant_service_runs_once_per_person_and_company_and_every_plan_runs_first(db, monkeypatch):
    o = names_world(db)
    w = o.w
    events = _order_spy(monkeypatch)
    p1, p2 = fake_phone(), fake_phone()

    service().grant(db, o.s1, ["SRT", "MCH"], ids_of(w.cust_a, w.cust_b), [
        person_of(p1, name="ZZT Order One"), person_of(p2, name="ZZT Order Two"),
    ])

    executed = [args for kind, args in events if kind == "execute"]
    assert len(executed) == 4
    assert all(len(a["companies"]) == 1 for a in executed)
    assert {(a["phone"], a["companies"][0]) for a in executed} == {(p, c) for p in (p1, p2) for c in ("SRT", "MCH")}
    first_exec = next(i for i, (kind, _) in enumerate(events) if kind == "execute")
    assert sum(1 for kind, _ in events[:first_exec] if kind == "plan") >= 4
    codes = {a["companies"][0]: a["customer_codes"] for a in executed}
    assert codes == {"SRT": [w.cust_a.customer_code], "MCH": [w.cust_b.customer_code]}


def test_N4_2_one_refused_row_in_a_two_company_form_writes_nothing(db, monkeypatch):
    o = names_world(db)
    w = o.w
    events = _order_spy(monkeypatch)
    good = fake_phone()

    with pytest.raises(AppException) as err:
        service().grant(db, o.s1, ["SRT", "MCH"], ids_of(w.cust_a, w.cust_b), [
            person_of(good, name="ZZT Good"), person_of(o.ali.phone_number, name="ZZT Ali Again"),
        ])

    assert err.value.status_code == 422
    assert [kind for kind, _ in events if kind == "execute"] == []
    assert state(db, good) is None
    assert links_of(db, o.ali.id) == set(ids_of(w.cust_a, o.theirs))


def test_N4_3_a_phone_visible_on_my_list_and_editable_is_refused_with_the_contact(db):
    o = names_world(db)
    good = fake_phone()

    with pytest.raises(AppException) as err:
        service().grant(db, o.s1, ["SRT"], ids_of(o.w.twin1), [
            person_of(good, name="ZZT Good"), person_of(o.ali.phone_number, name="ZZT Typed Name"),
        ])

    assert err.value.status_code == 422
    assert refusal_rows(err.value) == [{
        "index": 1, "error": "ZZT Ali Test already has access.",
        "contact": {"id": str(o.ali.id), "name": "ZZT Ali Test", "company": "SRT", "editable": True},
    }]
    assert state(db, good) is None
    assert links_of(db, o.ali.id) == set(ids_of(o.w.cust_a, o.theirs))


def test_N4_3_a_phone_visible_on_my_list_but_not_editable_is_refused_with_editable_false(db):
    o = names_world(db)

    with pytest.raises(AppException) as err:
        service().grant(db, o.s1, ["SRT"], ids_of(o.w.cust_a), [person_of(o.chong.phone_number, name="ZZT Chong")])

    assert refusal_rows(err.value) == [{
        "index": 0, "error": "ZZT Chong Test already has access.",
        "contact": {"id": str(o.chong.id), "name": "ZZT Chong Test", "company": "SRT", "editable": False},
    }]
    assert links_of(db, o.chong.id) == {str(o.theirs.id)}


def test_N4_3_a_phone_linked_only_outside_my_companies_is_refused_without_a_name(db):
    o = names_world(db)
    w = o.w
    outside = dealer(db, w, customers=(o.hidden_shop,), companies=(w.hidden,), name="ZZT Outside Person")

    with pytest.raises(AppException) as err:
        service().grant(db, o.s1, ["SRT"], ids_of(w.cust_a), [person_of(outside.phone_number, name="ZZT Typed")])

    assert refusal_rows(err.value) == [{"index": 0, "error": OTHER_COMPANY, "contact": None}]
    assert "ZZT Outside Person" not in str(err.value.detail)
    assert str(outside.id) not in str(err.value.detail)
    assert_no_leak(err.value.detail, o.hidden_shop)
    assert links_of(db, outside.id) == {str(o.hidden_shop.id)}


def test_N4_3_http_refusal_rows_carry_index_error_and_contact(db, api):
    o = names_world(db)

    resp = api.as_user(o.s1).post(f"{BASE}/grant", json={
        "companies": ["SRT"], "account_ids": ids_of(o.w.cust_a),
        "people": [{"name": "ZZT Typed", "phone": o.chong.phone_number, "role": "employee"}],
    })

    assert resp.status_code == 422, resp.text
    assert _find_rows(resp.json()) == [{
        "index": 0, "error": "ZZT Chong Test already has access.",
        "contact": {"id": str(o.chong.id), "name": "ZZT Chong Test", "company": "SRT", "editable": False},
    }]


def test_N4_4_an_existing_contact_with_no_customer_link_is_linked_never_a_second_contact(db):
    o = names_world(db)

    out = service().grant(db, o.s1, ["SRT"], ids_of(o.w.cust_a), [person_of(o.dan.phone_number, name="ZZT Dan Typed")])

    row = out["rows"][0]
    assert row["created"] is False and str(row["contact_id"]) == str(o.dan.id)
    assert state(db, o.dan.phone_number)["links"] == [str(o.w.cust_a.id)]


def test_N4_5_staff_and_duplicate_refusals_keep_their_texts_and_carry_contact_none(db):
    o = names_world(db)
    staff_contact = RespondContact(id=str(uuid.uuid4()), phone_number=fake_phone(), name="ZZT Staff User")
    db.add(staff_contact)
    db.flush()
    seed_user(db, contact_pk=staff_contact.id, slugs=())
    db.commit()
    phone = fake_phone()

    with pytest.raises(AppException) as err:
        service().grant(db, o.s1, ["SRT"], ids_of(o.w.cust_a), [
            person_of(staff_contact.phone_number), person_of(phone), person_of(phone),
        ])

    rows = refusal_rows(err.value)
    assert brief(rows) == [{"index": 0, "error": STAFF}, {"index": 2, "error": "Same as row 2."}]
    assert all("contact" in r and r["contact"] is None for r in rows)


# ================================================================== N5 Respond.io in the request


def _grant_one(db, o, phone, name="ZZT Respond Person", companies=("SRT",), accounts=None):
    return service().grant(db, o.s1, list(companies), accounts or ids_of(o.w.cust_a), [person_of(phone, name=name)])


def test_N5_1_a_person_found_in_respond_is_linked_not_created_inside_the_request(db, respond, jobs):
    o = names_world(db)
    respond.key, respond.lookup = True, "found"
    phone = fake_phone()

    out = _grant_one(db, o, phone)

    row = out["rows"][0]
    assert row["respond"] == "ok" and row["respond_error"] is None
    cid = row["contact_id"]
    assert str(respond_id_of(db, cid)) == str(respond.ids[next(iter(respond.ids))])
    assert not any(c[0] == "create_contact" for c in respond.calls)
    assert backend_id_written(respond)
    assert respond_jobs(jobs) == []
    assert respond.forbidden == []


def test_N5_1_a_404_creates_the_person_in_respond_once(db, respond, jobs):
    o = names_world(db)
    respond.key, respond.lookup = True, "missing"
    phone = fake_phone()

    out = _grant_one(db, o, phone, name="ZZT Made Here")

    row = out["rows"][0]
    assert row["respond"] == "ok"
    created = [c for c in respond.calls if c[0] == "create_contact"]
    assert len(created) == 1 and created[0][2] == "ZZT Made Here"
    assert respond_id_of(db, row["contact_id"]) is not None
    assert respond_jobs(jobs) == []


def test_N5_1_a_two_company_grant_asks_respond_once_per_person(db, respond):
    o = names_world(db)
    respond.key, respond.lookup = True, "missing"

    out = _grant_one(db, o, fake_phone(), companies=("SRT", "MCH"), accounts=ids_of(o.w.cust_a, o.w.cust_b))

    assert [c[0] for c in respond.calls].count("get_contact_by_phone") == 1
    assert [c[0] for c in respond.calls].count("create_contact") == 1
    assert {r["respond"] for r in out["rows"]} == {"ok"}


def test_N5_1_the_screen_path_never_enqueues_the_worker_job_even_when_respond_fails(db, respond, jobs):
    o = names_world(db)
    respond.key = False

    _grant_one(db, o, fake_phone())

    assert respond_jobs(jobs) == []


def test_N5_2_every_call_writes_an_integration_log_row_found(db, respond):
    o = names_world(db)
    respond.key, respond.lookup = True, "found"

    cid = _grant_one(db, o, fake_phone())["rows"][0]["contact_id"]

    rows = logs_of(db, cid)
    assert_logged(rows, 2)  # lookup + backend_id update
    assert all(r.status == "success" for r in rows)


def test_N5_2_every_call_writes_an_integration_log_row_created(db, respond):
    o = names_world(db)
    respond.key, respond.lookup = True, "missing"

    cid = _grant_one(db, o, fake_phone())["rows"][0]["contact_id"]

    assert_logged(logs_of(db, cid), 3)  # lookup (404) + create + backend_id update


@pytest.mark.parametrize("lookup", ["error", "timeout"])
def test_N5_2_N5_3_a_failed_call_is_logged_failed_and_access_stays_saved(db, respond, lookup):
    o = names_world(db)
    respond.key, respond.lookup = True, lookup
    phone = fake_phone()

    out = _grant_one(db, o, phone)

    row = out["rows"][0]
    assert row["respond"] == "failed"
    assert_plain(row["respond_error"])
    assert state(db, phone)["links"] == [str(o.w.cust_a.id)]
    assert respond_id_of(db, row["contact_id"]) is None
    rows = logs_of(db, row["contact_id"])
    assert_logged(rows, 1)
    assert rows[0].status == "failed"
    assert not any(c[0] == "create_contact" for c in respond.calls)


def test_N5_3_no_api_key_keeps_access_and_says_failed_in_plain_words(db, respond):
    o = names_world(db)
    respond.key = False
    phone = fake_phone()

    out = _grant_one(db, o, phone)

    row = out["rows"][0]
    assert row["respond"] == "failed"
    assert_plain(row["respond_error"])
    assert state(db, phone)["links"] == [str(o.w.cust_a.id)]
    assert respond.forbidden == []


def test_N5_3_http_grant_rows_carry_respond_and_respond_error(db, api, respond):
    o = names_world(db)
    respond.key, respond.lookup = True, "error"

    resp = api.as_user(o.s1).post(f"{BASE}/grant", json={
        "companies": ["SRT"], "account_ids": ids_of(o.w.cust_a),
        "people": [{"name": "ZZT Http Respond", "phone": fake_phone(), "role": "employee"}],
    })

    assert resp.status_code in (200, 201), resp.text
    row = _unwrap(resp.json())["rows"][0]
    assert row["respond"] == "failed"
    assert_plain(row["respond_error"])


def test_N5_5_retry_runs_the_shared_function_for_an_editable_contact(db, respond):
    o = names_world(db)
    respond.key, respond.lookup = True, "found"

    out = service().respond_retry(db, o.s1, str(o.ali.id))

    assert out == {"respond": "ok", "respond_error": None}
    assert respond_id_of(db, o.ali.id) is not None
    assert_logged(logs_of(db, o.ali.id), 2)


def test_N5_5_retry_failure_is_reported_not_raised(db, respond):
    o = names_world(db)
    respond.key, respond.lookup = True, "error"

    out = service().respond_retry(db, o.s1, str(o.ali.id))

    assert out["respond"] == "failed"
    assert_plain(out["respond_error"])


def test_N5_5_http_retry_endpoint_and_404_for_a_non_editable_or_unknown_contact(db, api, respond):
    o = names_world(db)
    respond.key, respond.lookup = True, "missing"
    client = api.as_user(o.s1)

    ok = client.post(f"{BASE}/people/{o.ali.id}/respond")
    assert ok.status_code == 200, ok.text
    assert _unwrap(ok.json()) == {"respond": "ok", "respond_error": None}

    calls_before = len(respond.calls)
    hidden = client.post(f"{BASE}/people/{o.chong.id}/respond")
    unknown = client.post(f"{BASE}/people/{uuid.uuid4()}/respond")
    assert hidden.status_code == 404 and unknown.status_code == 404, hidden.text
    assert hidden.json() != {"detail": "Not Found"}, "a missing route, not the domain 404"
    assert len(respond.calls) == calls_before
    assert respond_id_of(db, o.chong.id) is None


def test_N5_5_http_retry_is_403_without_edit_own(db, api):
    o = names_world(db)
    none = make_world(db, slugs=(NEITHER,), superadmin=False)

    resp = api.as_user(none.user_id).post(f"{BASE}/people/{o.ali.id}/respond")

    assert resp.status_code == 403, resp.text


def _shared():
    from app.services import respond_contact_ensure

    return respond_contact_ensure


def test_N5_1_the_shared_function_found_and_failed(db, respond):
    o = names_world(db)
    respond.key, respond.lookup = True, "found"

    ok = _shared().ensure_in_respond(db, str(o.ali.id))
    respond.lookup = "error"
    failed = _shared().ensure_in_respond(db, str(o.dan.id))

    assert not ok.get("error") and ok.get("status") != "failed"
    assert respond_id_of(db, o.ali.id) is not None
    assert failed["status"] == "failed" and failed["error"]


def test_N5_1_the_worker_task_calls_the_shared_function(db, respond, monkeypatch):
    import app.tasks.respond_io_tasks as tasks

    o = names_world(db)
    respond.key, respond.lookup = True, "found"
    module = _shared()
    calls: list = []
    real = module.ensure_in_respond

    def spy(*a, **k):
        calls.append(a)
        return real(*a, **k)

    monkeypatch.setattr(module, "ensure_in_respond", spy)
    if hasattr(tasks, "ensure_in_respond"):
        monkeypatch.setattr(tasks, "ensure_in_respond", spy)

    respond.job(str(o.ali.id))

    assert len(calls) == 1 and str(o.ali.id) in [str(x) for x in calls[0]]
    assert respond_id_of(db, o.ali.id) is not None


def test_N5_1_N5_2_the_worker_found_path_stores_the_id_and_logs_each_call(db, respond):
    o = names_world(db)
    respond.key, respond.lookup = True, "found"

    respond.job(str(o.ali.id))

    assert respond_id_of(db, o.ali.id) is not None
    assert not any(c[0] == "create_contact" for c in respond.calls)
    assert backend_id_written(respond)
    assert_logged(logs_of(db, o.ali.id), 2)


def test_N5_1_N5_2_the_worker_404_path_creates_once_and_logs_each_call(db, respond):
    o = names_world(db)
    respond.key, respond.lookup = True, "missing"

    respond.job(str(o.ali.id))

    assert [c[0] for c in respond.calls].count("create_contact") == 1
    assert respond_id_of(db, o.ali.id) is not None
    assert_logged(logs_of(db, o.ali.id), 3)


def test_N5_2_the_worker_still_raises_on_a_respond_error_and_logs_it_failed(db, respond):
    o = names_world(db)
    respond.key, respond.lookup = True, "error"

    with pytest.raises(Exception) as caught:
        respond.job(str(o.ali.id))

    assert not isinstance(caught.value, (ImportError, AssertionError)), caught.value
    rows = logs_of(db, o.ali.id)
    assert_logged(rows, 1)
    assert rows[0].status == "failed"
