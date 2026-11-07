"""Phase 2 RED tests - SALES-LEADERBOARD (`GET /api/v1/sales/leaderboard`).

Contract: `documentation/plans/sales/PLAN-sales-leaderboard-07nov.md` ("Contract", binding) and
`documentation/plans/sales/sales-leaderboard-07nov-acceptance-criteria.md` (L1 to L7).

Postgres only (`tests/_pg_fixture.py`), every row seeded here (CI's database is empty). No
implementation exists when this file is written: the route, the `sales_person` dimension and the
`sales.leaderboard.view` slug are all missing, so every test fails on a 404 / unknown dimension /
missing registry entry.

The world (`_world`), October 2026 against the previous window `ask.compare_window(
"previous_period", Oct 1, Oct 31)` = Aug 31 to Sep 30 (the contract's example JSON prints
2026-09-01, the helper it names gives 2026-08-31: pinned to the helper, see the report):

    person   codes            Oct net                         customers   Sep (previous) net
    ALPHA    A1 (SRT) A2(MCH) IV 1000 + CS 200.50 - CN 100    2           800.00
                              + (A2, MCH) IV 500.25 = 1600.75 (c1 is billed under both codes)
    GAMMA    G1               IV 1000.75 + IV 600 = 1600.75   1           none (prev 0 -> change null)
    (B1)     B1, no person    IV 1500 (+ a cancelled 5000)    1           CN 50 only (prev -50 -> null)
    DELTA    D1               nothing in Oct                  -           IV 900 (absent from Oct board)
    no agent                  IV 77.77                        -           none
    total Oct 4779.27, total previous 1650.00 -> +189.7%
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.models.access import RespondContact
from app.models.base import set_company_scope
from app.models.company import Company, UserCompany
from app.models.product import Brand, ProductCategory
from app.models.sales_agent import SalesAgent
from app.models.user import User
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.company_scope_resolver import apply_company_scope

from tests._mc_lookup_seed import MOCHA_ID, product, seed_mocha
from tests._pg_fixture import blank_session, unique_code
from tests._sales_unified_seed import cust, doc, line
from tests.test_top_selling_report import _access, _as_contact, _contact

D = Decimal
LB = "sales.leaderboard.view"
ROUTE = "/api/v1/sales/leaderboard"
OPTIONS = "/api/v1/sales/leaderboard/options"
ASK = "/api/v1/order-management/report-ask"
OCT = ("2026-10-01", "2026-10-31")
SEP = ("2026-09-01", "2026-09-30")
NO_AGENT = "(no agent)"
ROW_KEYS = {"rank", "person", "codes", "amount", "prev_amount", "change_pct", "customers", "is_me"}
TOP_KEYS = {
    "date_from", "date_to", "previous_from", "previous_to", "as_of", "total", "no_agent_amount", "rows", "me",
}


def _money(value) -> Decimal:
    return D(str(value))


# --------------------------------------------------------------------------------- fixtures


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, None)
        seed_mocha(s)
        yield s


@contextmanager
def make_client(db, *, allow=(LB,), grants=(DEFAULT_COMPANY_ID, MOCHA_ID), contact=None):
    """A TestClient for a non-admin user holding exactly the `allow` slugs and `grants` companies."""
    from app.services.user_service import UserPermissionService

    user = User(
        id=str(uuid.uuid4()), email=f"{unique_code('U')}@test.local", name="ZZT Staff", status="ACTIVE",
        respond_contact_id=contact.id if contact is not None else None,
    )
    db.add(user)
    db.flush()
    for company_id in grants:
        db.add(UserCompany(user_id=user.id, company_id=company_id))
    db.flush()
    principal = {"id": user.id, "email": user.email}

    def _override_db():
        yield db

    async def _scope():
        scope = frozenset(grants)
        set_company_scope(db, scope)
        return scope

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: principal
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
    app.dependency_overrides[apply_company_scope] = _scope
    original = UserPermissionService.check_user_has_permission
    UserPermissionService.check_user_has_permission = lambda self, uid, slug: slug in allow
    try:
        yield TestClient(app, headers={"X-API-Key": "k"})
    finally:
        UserPermissionService.check_user_has_permission = original
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------------- seeds


def _agent(db, code, *, person=None, company_id=None, contact=None) -> SalesAgent:
    row = SalesAgent(
        id=str(uuid.uuid4()), sales_agent=code, person_label=person, company_id=company_id, is_active=True,
        contact_id=contact.id if contact is not None else None,
    )
    db.add(row)
    db.flush()
    return row


def _sale(db, kind, net, when, *, agent=None, customer=None, company=DEFAULT_COMPANY_ID, prod=None,
          status="posted", synced=None):
    prod = prod or product(db, company_id=company)
    header = doc(db, kind, net, when, customer=customer, agent_row=agent, company_id=company, status=status,
                 lines=[line(prod=prod, net=net)])
    if synced is not None:
        header.last_synced_at = synced
        db.flush()
    return header


def _world(db):
    s = unique_code("W", alpha=True)[-8:]
    ns = type("World", (), {})()
    ns.alpha, ns.gamma, ns.delta = f"ZZTALPHA {s}", f"ZZTGAMMA {s}", f"ZZTDELTA {s}"
    ns.a1 = _agent(db, f"ZZT-A1-{s}", person=ns.alpha, company_id=DEFAULT_COMPANY_ID)
    ns.a2 = _agent(db, f"ZZT-A2-{s}", person=ns.alpha, company_id=MOCHA_ID)
    ns.g1 = _agent(db, f"ZZT-G1-{s}", person=ns.gamma, company_id=DEFAULT_COMPANY_ID)
    ns.b1 = _agent(db, f"ZZT-B1-{s}", person=None, company_id=DEFAULT_COMPANY_ID)  # its own row, under its code
    ns.d1 = _agent(db, f"ZZT-D1-{s}", person=ns.delta, company_id=DEFAULT_COMPANY_ID)
    c1, c2, c3, c4, c5 = (cust(db) for _ in range(5))
    ns.brand = Brand(id=str(uuid.uuid4()), brand_code=unique_code("BR")[:50], brand_name=f"ZZT Brand {s}",
                     company_id=DEFAULT_COMPANY_ID)
    ns.category = ProductCategory(id=str(uuid.uuid4()), category_code=unique_code("CAT")[:50],
                                  category_name=f"ZZT Category {s}", company_id=DEFAULT_COMPANY_ID)
    db.add_all([ns.brand, ns.category])
    db.flush()
    branded = product(db, company_id=DEFAULT_COMPANY_ID)
    branded.brand_id = ns.brand.id
    branded.category_id = ns.category.id
    db.flush()
    ns.branded = branded

    sync_sorento, sync_mocha = datetime(2026, 11, 4, 3, 10, 0), datetime(2026, 11, 5, 9, 0, 0)
    # October
    _sale(db, "invoice", "1000.00", date(2026, 10, 5), agent=ns.a1, customer=c1, prod=branded, synced=sync_sorento)
    _sale(db, "cash_sale", "200.50", date(2026, 10, 6), agent=ns.a1, customer=c2)
    _sale(db, "credit_note", "100.00", date(2026, 10, 7), agent=ns.a1, customer=c2)
    _sale(db, "invoice", "500.25", date(2026, 10, 8), agent=ns.a2, customer=c1, company=MOCHA_ID, synced=sync_mocha)
    _sale(db, "invoice", "1000.75", date(2026, 10, 9), agent=ns.g1, customer=c4)
    _sale(db, "invoice", "600.00", date(2026, 10, 10), agent=ns.g1, customer=c4)
    _sale(db, "invoice", "1500.00", date(2026, 10, 11), agent=ns.b1, customer=c3)
    _sale(db, "invoice", "5000.00", date(2026, 10, 12), agent=ns.b1, customer=c3, status="cancelled")
    _sale(db, "invoice", "77.77", date(2026, 10, 13), customer=c5)  # no agent at all
    _sale(db, "invoice", "999.00", date(2026, 11, 2), agent=ns.a1, customer=c1)  # outside the period
    # September (the previous window of October runs Aug 31 to Sep 30)
    _sale(db, "invoice", "800.00", date(2026, 9, 5), agent=ns.a1, customer=c1)
    _sale(db, "credit_note", "50.00", date(2026, 9, 6), agent=ns.b1, customer=c3)
    _sale(db, "invoice", "900.00", date(2026, 9, 10), agent=ns.d1, customer=c5)
    db.commit()
    return ns


def _get(client, frm_to=OCT, **extra):
    params = [("date_from", frm_to[0]), ("date_to", frm_to[1])]
    for key, value in extra.items():
        for item in (value if isinstance(value, (list, tuple)) else [value]):
            params.append((key, item))
    return client.get(ROUTE, params=params)


def _board(client, frm_to=OCT, **extra):
    resp = _get(client, frm_to, **extra)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _by_person(body):
    return {r["person"]: r for r in body["rows"]}


# ============================================================ L2 the figure, no second calculation


def test_l2_1_board_total_equals_run_ask_invoiced_total(db):
    from app.services.reports import ask

    world = _world(db)
    expected = ask.run_ask(
        db, basis="invoiced", measure="amount", group_by=None, date_from=date(2026, 10, 1),
        date_to=date(2026, 10, 31), filters={}, warehouse_codes=[], policy=None,
        company_grants=frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}),
    )
    assert _money(expected["total"]["amount"]) == D("4779.27")
    with make_client(db) as client:
        body = _board(client)
        assert _money(body["total"]["amount"]) == _money(expected["total"]["amount"])
        one = ask.run_ask(
            db, basis="invoiced", measure="amount", group_by=None, date_from=date(2026, 10, 1),
            date_to=date(2026, 10, 31), filters={}, warehouse_codes=[], policy=None,
            company_grants=frozenset({DEFAULT_COMPANY_ID}),
        )
        narrowed = _board(client, company=DEFAULT_COMPANY_ID)
        assert _money(narrowed["total"]["amount"]) == _money(one["total"]["amount"]) == D("4279.02")
    assert world.alpha


def test_l2_2_cancelled_never_counts_and_a_credit_note_subtracts(db):
    world = _world(db)
    with make_client(db) as client:
        rows = _by_person(_board(client))
    assert _money(rows[world.b1.sales_agent]["amount"]) == D("1500.00")  # the cancelled 5000 is out
    assert _money(rows[world.alpha]["amount"]) == D("1600.75")  # 1000 + 200.50 - 100 + 500.25


# ================================================================================ L3 ranking


def test_l3_1_agent_codes_sharing_a_person_label_across_companies_are_one_row(db):
    world = _world(db)
    with make_client(db) as client:
        rows = _by_person(_board(client))
    alpha = rows[world.alpha]
    assert alpha["codes"] == sorted([world.a1.sales_agent, world.a2.sales_agent])
    assert _money(alpha["amount"]) == D("1600.75")
    assert world.a1.sales_agent not in rows and world.a2.sales_agent not in rows


def test_l3_1_a_code_without_a_person_label_is_its_own_row_under_its_code(db):
    world = _world(db)
    with make_client(db) as client:
        rows = _by_person(_board(client))
    row = rows[world.b1.sales_agent]
    assert row["codes"] == [world.b1.sales_agent]
    assert _money(row["amount"]) == D("1500.00")


def test_l3_4_no_agent_sales_are_not_a_row_but_are_in_the_total(db):
    _world(db)
    with make_client(db) as client:
        body = _board(client)
    assert all(r["person"] != NO_AGENT for r in body["rows"])
    assert _money(body["no_agent_amount"]) == D("77.77")
    assert _money(body["total"]["amount"]) == D("4779.27")
    assert sum(_money(r["amount"]) for r in body["rows"]) + _money(body["no_agent_amount"]) == D("4779.27")


def test_l3_4_no_agent_amount_is_zero_when_there_are_none(db):
    _world(db)
    with make_client(db) as client:
        body = _board(client, ("2026-09-01", "2026-09-04"))  # nothing sold
    assert body["rows"] == []
    assert _money(body["no_agent_amount"]) == D("0")


def test_l3_3_l3_5_ranked_by_amount_desc_ties_by_person_dense_and_prev_only_person_absent(db):
    world = _world(db)
    with make_client(db) as client:
        body = _board(client)
    assert [(r["rank"], r["person"]) for r in body["rows"]] == [
        (1, world.alpha),  # 1600.75 ties GAMMA, ALPHA sorts first
        (2, world.gamma),
        (3, world.b1.sales_agent),
    ]
    assert world.delta not in _by_person(body)  # sold only in the previous window


# ================================================================================ L4 columns


def test_l4_2_change_pct_vs_the_previous_period_and_null_when_prev_is_not_positive(db):
    world = _world(db)
    with make_client(db) as client:
        body = _board(client)
    assert (body["previous_from"], body["previous_to"]) == ("2026-08-31", "2026-09-30")
    rows = _by_person(body)
    assert _money(rows[world.alpha]["prev_amount"]) == D("800.00")
    assert rows[world.alpha]["change_pct"] == 100.1  # (1600.75 - 800) / 800
    assert _money(rows[world.gamma]["prev_amount"]) == D("0")
    assert rows[world.gamma]["change_pct"] is None  # prev zero
    assert _money(rows[world.b1.sales_agent]["prev_amount"]) == D("-50.00")
    assert rows[world.b1.sales_agent]["change_pct"] is None  # prev negative
    assert _money(body["total"]["prev_amount"]) == D("1650.00")  # 800 - 50 + 900
    assert body["total"]["change_pct"] == 189.7


def test_l4_2_total_change_is_null_when_the_previous_total_is_zero(db):
    world = _world(db)
    with make_client(db) as client:
        body = _board(client, SEP)  # previous window Aug 2 to Aug 31: nothing sold
    assert _money(body["total"]["prev_amount"]) == D("0")
    assert body["total"]["change_pct"] is None
    assert [r["change_pct"] for r in body["rows"]] == [None, None, None]
    # DELTA 900 first, ALPHA 800, then B1 with its negative -50 (a non-zero amount stays listed)
    assert [r["person"] for r in body["rows"]] == [world.delta, world.alpha, world.b1.sales_agent]


def test_l4_1_customers_are_distinct_across_the_persons_codes(db):
    world = _world(db)
    with make_client(db) as client:
        rows = _by_person(_board(client))
    assert rows[world.alpha]["customers"] == 2  # c1 under A1 and A2 counts once, plus c2
    assert rows[world.gamma]["customers"] == 1  # two invoices, one customer
    assert rows[world.b1.sales_agent]["customers"] == 1


# ================================================================================== L6 me


def test_l6_1_a_user_linked_to_an_agent_gets_me_and_is_me_on_that_row(db):
    world = _world(db)
    contact = RespondContact(id=str(uuid.uuid4()), respond_io_id=unique_code("C"),
                             phone_number=f"+6010{uuid.uuid4().hex[:7]}", name="ZZT Gamma")
    db.add(contact)
    db.flush()
    world.g1.contact_id = contact.id
    db.flush()
    with make_client(db, contact=contact) as client:
        body = _board(client)
    assert body["me"] == {"person": world.gamma, "rank": 2}
    assert [r["person"] for r in body["rows"] if r["is_me"]] == [world.gamma]


def test_l6_1_an_unlinked_user_has_no_me_and_no_highlighted_row(db):
    _world(db)
    with make_client(db) as client:
        body = _board(client)
    assert body["me"] is None
    assert not any(r["is_me"] for r in body["rows"])


# ========================================================== L1 access, grants, validation


def test_l1_1_without_the_leaderboard_permission_it_is_403(db):
    _world(db)
    with make_client(db, allow=("sales.reports.view",)) as client:  # the reports slug is not enough
        assert _get(client).status_code == 403
        assert client.get(OPTIONS).status_code == 403


def test_l1_1_the_leaderboard_permission_alone_is_200(db):
    _world(db)
    with make_client(db, allow=(LB,)) as client:
        assert _get(client).status_code == 200
        assert client.get(OPTIONS).status_code == 200


def test_l1_2_a_company_outside_the_users_grants_is_403_and_a_granted_one_narrows(db):
    world = _world(db)
    with make_client(db, grants=(DEFAULT_COMPANY_ID,)) as client:
        assert _get(client, company=MOCHA_ID).status_code == 403
        body = _board(client)  # no filter: the granted companies only
        assert _money(body["total"]["amount"]) == D("4279.02")
        assert _by_person(body)[world.alpha]["codes"] == [world.a1.sales_agent]
        assert _money(_by_person(body)[world.alpha]["amount"]) == D("1100.50")
    with make_client(db) as client:
        body = _board(client, company=DEFAULT_COMPANY_ID)
        assert _money(body["total"]["amount"]) == D("4279.02")
        assert _by_person(body)[world.alpha]["codes"] == [world.a1.sales_agent]


def test_date_to_before_date_from_is_422(db):
    with make_client(db) as client:
        resp = _get(client, ("2026-10-31", "2026-10-01"))
        assert resp.status_code == 422
        assert client.get(ROUTE, params={"date_from": "2026-10-01"}).status_code == 422


# ================================================================================ L5 filters


def test_l5_2_a_brand_filter_ranks_the_matching_lines_only(db):
    world = _world(db)
    with make_client(db) as client:
        body = _board(client, brand=world.brand.id)
        assert [(r["person"], _money(r["amount"])) for r in body["rows"]] == [(world.alpha, D("1000.00"))]
        assert _money(body["total"]["amount"]) == D("1000.00")
        by_category = _board(client, category=world.category.id)
    assert [(r["person"], _money(r["amount"])) for r in by_category["rows"]] == [(world.alpha, D("1000.00"))]


# ============================================================================= the shape


def test_every_contract_field_is_in_the_response(db):
    world = _world(db)
    with make_client(db) as client:
        body = _board(client)
        narrow = None
    assert set(body) == TOP_KEYS
    assert (body["date_from"], body["date_to"]) == OCT
    assert set(body["total"]) == {"amount", "prev_amount", "change_pct"}
    assert all(set(r) == ROW_KEYS for r in body["rows"])
    assert isinstance(body["rows"][0]["codes"], list) and isinstance(body["rows"][0]["customers"], int)
    assert body["as_of"].startswith("2026-11-05T09:00:00")  # max last_synced_at over both granted companies
    with make_client(db, grants=(DEFAULT_COMPANY_ID,)) as client:
        narrow = _board(client)
    assert narrow["as_of"].startswith("2026-11-04T03:10:00")  # Mocha's later sync is not the user's to see
    assert world.alpha


def test_as_of_is_null_when_no_document_was_synced(db):
    _sale(db, "invoice", "10.00", date(2026, 10, 5))
    db.commit()
    with make_client(db, grants=(DEFAULT_COMPANY_ID,)) as client:
        assert _board(client)["as_of"] is None


# ================================================================================== options


def test_options_companies_are_the_callers_grants_only_and_brands_categories_are_listed(db):
    world = _world(db)
    sorento = db.get(Company, DEFAULT_COMPANY_ID)
    mocha = db.get(Company, MOCHA_ID)
    with make_client(db, grants=(DEFAULT_COMPANY_ID,)) as client:
        body = client.get(OPTIONS).json()
        assert body["companies"] == [{"value": DEFAULT_COMPANY_ID, "label": sorento.code}]
    with make_client(db) as client:
        body = client.get(OPTIONS).json()
    assert {(c["value"], c["label"]) for c in body["companies"]} == {
        (DEFAULT_COMPANY_ID, sorento.code), (MOCHA_ID, mocha.code),
    }
    assert {"value": world.brand.id, "label": world.brand.brand_name} in body["brands"]
    assert {"value": world.category.id, "label": world.category.category_name} in body["categories"]


# ================================================================================ permission


def test_the_permission_registry_holds_sales_leaderboard_view():
    from app.rbac.permission_registry import PERMISSION_REGISTRY

    entry = next((p for p in PERMISSION_REGISTRY if p["slug"] == LB), None)
    assert entry is not None, f"{LB} is not registered"
    assert entry["name"] == "View the sales leaderboard"


# ================================================================================ L7 assistant


def test_l7_1_sales_person_is_an_invoiced_dimension_only():
    from app.services.reports import ask

    assert "sales_person" in ask.CATALOGUE["sales"]["invoiced"]["dimensions"]
    for basis in ("delivered", "ordered", "outstanding"):
        assert "sales_person" not in ask.CATALOGUE["sales"][basis]["dimensions"]


def test_l7_1_run_ask_by_sales_person_returns_the_boards_rows_and_amounts(db):
    from app.services.reports import ask

    world = _world(db)
    ranked = ask.run_ask(
        db, basis="invoiced", measure="amount", group_by="sales_person", date_from=date(2026, 10, 1),
        date_to=date(2026, 10, 31), filters={}, warehouse_codes=[], policy=None, top_n=1000,
        company_grants=frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}),
    )
    asked = {r["name"]: _money(r["amount"]) for r in ranked["rows"]}
    assert _money(asked.pop(NO_AGENT)) == D("77.77")  # the no-agent sales are one named row here
    with make_client(db) as client:
        board = {r["person"]: _money(r["amount"]) for r in _board(client)["rows"]}
    assert asked == board
    assert board[world.alpha] == D("1600.75")


def _assistant_ask(client, contact, **params):
    q = {"date_from": OCT[0], "date_to": OCT[1], **_as_contact(contact), **params}
    return client.get(ASK, params=q, headers={"X-API-Key": "k"})


def test_l7_1_crm_report_ask_accepts_sales_person_on_invoiced_and_matches_the_board(db):
    world = _world(db)
    contact = _contact(db)
    _access(db, contact, "Sorento Office")
    db.commit()
    with make_client(db, allow=(LB, "sales.reports.view"), grants=(DEFAULT_COMPANY_ID,)) as client:
        resp = _assistant_ask(client, contact, basis="invoiced", group_by="sales_person", measure="amount",
                              top_n=50)
        assert resp.status_code == 200, resp.text
        asked = {r["name"]: _money(r["amount"]) for r in resp.json()["rows"]}
        asked.pop(NO_AGENT, None)
        board = {r["person"]: _money(r["amount"]) for r in _board(client, company=DEFAULT_COMPANY_ID)["rows"]}
    assert asked == board
    assert board[world.gamma] == D("1600.75")


def test_l7_1_sales_person_stays_unknown_group_by_on_the_ordered_basis(db):
    _world(db)
    contact = _contact(db)
    _access(db, contact, "Sorento Office")
    db.commit()
    with make_client(db, allow=(LB, "sales.reports.view"), grants=(DEFAULT_COMPANY_ID,)) as client:
        resp = _assistant_ask(client, contact, basis="ordered", group_by="sales_person", measure="amount")
    assert resp.status_code == 422
    assert resp.json().get("code") == "unknown_group_by"
