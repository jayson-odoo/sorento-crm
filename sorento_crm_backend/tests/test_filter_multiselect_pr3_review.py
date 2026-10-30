"""FILTER-MULTISELECT PR3 review round: the exports take the same several values the lists do, an own-scope
user never widens by picking, the promotions export honours Attachment state, the tickets board unions.
Red first; Postgres only; rows seeded here into a blank schema.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.finance import BillingDocument
from app.models.list_query_metadata import ListQueryField, ListQueryResource
from app.models.marketing import Promotion, PromotionAttachment
from app.models.order import Customer, Order, OrderStatus
from app.models.resources import Attachment
from app.models.sales_agent import SalesAgent
from app.services.user_service import UserPermissionService
from tests._multi_filter_client import get, open_client
from tests._pg_fixture import blank_session, unique_code

EXPORT = "/api/v1/list-query/export"
SEARCH = "/api/v1/list-query/search"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def client(db, monkeypatch):
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: {"admin"})
    with open_client(db, monkeypatch) as (c, _actor):
        yield c


def _resource(db, key, field_key, compile_key):
    res = ListQueryResource(id=str(uuid.uuid4()), resource_key=key, display_name=key, is_active=True)
    db.add(res)
    db.flush()
    db.add(ListQueryField(id=str(uuid.uuid4()), resource_id=res.id, field_key=field_key, label=field_key,
                          data_type="string", compile_key=compile_key, allowed_operators=["eq"],
                          filterable=True, exportable=True))
    db.flush()


# ---- 1. Delivery orders export: several statuses ------------------------------------------------------

def _status(db, label):
    row = OrderStatus(id=str(uuid.uuid4()), status_code=unique_code(label), status_name=f"ZZT {label}")
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def orders(db):
    _resource(db, "orders", "order_number", "order.order_number")
    s = (_status(db, "s1"), _status(db, "s2"), _status(db, "s3"))
    tag = unique_code("XO", alpha=True)
    for key, st in (("a", s[0]), ("b", s[1]), ("c", s[2])):
        db.add(Order(id=str(uuid.uuid4()), order_number=f"{tag}-{key}", order_status_id=st.id))
    db.flush()
    return dict(tag=tag, st=s)


def _export_orders(client, s, status_value):
    body = {"resource": "orders", "fields": [{"field_key": "order_number"}], "quick_search": s["tag"],
            "order_status_id": status_value}
    resp = client.post(EXPORT, json=body)
    assert resp.status_code == 200, resp.text
    return {r["order_number"] for r in resp.json()["data"]}


def test_orders_export_two_statuses_returns_rows_of_either(client, orders):
    s = orders
    got = _export_orders(client, s, f"{s['st'][0].id},{s['st'][1].id}")
    assert got == {f"{s['tag']}-a", f"{s['tag']}-b"}


def test_orders_export_accepts_status_codes_like_the_list(client, orders):
    s = orders
    got = _export_orders(client, s, f"{s['st'][1].status_code},{s['st'][2].id}")
    assert got == {f"{s['tag']}-b", f"{s['tag']}-c"}


def test_orders_export_single_status_still_works(client, orders):
    s = orders
    assert _export_orders(client, s, s["st"][2].id) == {f"{s['tag']}-c"}


# ---- 2. Billing documents export: several customers ---------------------------------------------------

def test_billing_export_two_customers_returns_both_customers_documents(client, db):
    tag = unique_code("XB", alpha=True)
    cust = []
    for i in range(3):
        c = Customer(id=str(uuid.uuid4()), customer_code=unique_code(f"c{i}"), customer_name=f"ZZT c{i}")
        db.add(c)
        cust.append(c)
    agent = SalesAgent(id=str(uuid.uuid4()), sales_agent=unique_code("ag"), description="ZZT ag", is_active=True)
    db.add(agent)
    db.flush()
    for i, c in enumerate(cust):
        db.add(BillingDocument(id=str(uuid.uuid4()), document_type="invoice", doc_no=f"{tag}-{i}",
                               doc_date=date(2026, 6, 1), customer_id=c.id, agent_code=agent.sales_agent,
                               status="posted", source_ref=unique_code("ref")))
    db.flush()
    body = {"resource": "finance_billing_documents", "fields": [{"field_key": "doc_no"}], "quick_search": tag,
            "customer_id": f"{cust[0].id},{cust[2].id}"}
    resp = client.post(EXPORT, json=body)
    assert resp.status_code == 200, resp.text
    assert {r["doc_no"] for r in resp.json()["data"]} == {f"{tag}-0", f"{tag}-2"}


# ---- 3. Own scope: picking never widens ---------------------------------------------------------------

def test_own_scope_opportunities_pick_own_and_foreign_agent_sees_only_own():
    from tests._own_scope_support import acting, world
    from tests.test_portal_p2_own_scope_modules import OPP, OPP_LIMITED, _opp_ids, _opportunity
    from app.models.base import company_scope
    from app.services import project_seed_service
    from app.services.sales import sales_seed_service

    with blank_session() as db:
        w = world(db)
        project_seed_service.run(db, company_id=w.company_id)
        sales_seed_service.run(db)
        with company_scope(db, frozenset({w.company_id})):
            own = _opportunity(db, w, w.ag_a.id, w.cust_a.id)
            foreign = _opportunity(db, w, w.ag_b.id, w.cust_b.id)
            with acting(db, w.a, OPP_LIMITED) as c:
                assert _opp_ids(c, sales_agent_id=f"{w.ag_a.id},{w.ag_b.id}") == {own}
                got = c.get(OPP, params=[("limit", 200), ("sales_agent_id", w.ag_a.id), ("sales_agent_id", w.ag_b.id)])
                assert {r["id"] for r in got.json()["data"]} == {own}
                assert foreign not in _opp_ids(c, sales_agent_id=f"{w.ag_b.id},{w.ag_a.id}")


# ---- 4. Promotions export honours Attachment state; unknown state is 422 ------------------------------

def _promo(db, label):
    row = Promotion(id=str(uuid.uuid4()), description=label, start_date=date(2026, 1, 1),
                    end_date=date(2030, 12, 31), is_active=True, access_levels=["dealer"])
    db.add(row)
    db.flush()
    return row


def _linked(db, promo, deleted):
    att = Attachment(id=str(uuid.uuid4()), original_filename="f.pdf", stored_filename=unique_code("f"),
                     file_path="x/f.pdf", is_deleted=deleted)
    db.add(att)
    db.flush()
    db.add(PromotionAttachment(id=str(uuid.uuid4()), promotion_id=promo.id, attachment_id=att.id))
    db.flush()


@pytest.fixture
def promos(db):
    _resource(db, "promotions", "description", "promotion.description")
    tag = unique_code("XP", alpha=True)
    unlinked, trashed, clean = (_promo(db, f"{tag}-{k}") for k in ("unlinked", "trashed", "clean"))
    _linked(db, trashed, True)
    _linked(db, clean, False)
    return tag


def _export_promos(client, tag, state):
    body = {"resource": "promotions", "fields": [{"field_key": "description"}], "quick_search": tag,
            "promotion_attachment_state": state}
    resp = client.post(EXPORT, json=body)
    assert resp.status_code == 200, resp.text
    return {r["description"] for r in resp.json()["data"]}


def test_promotions_export_attachment_state_single_and_union(client, promos):
    tag = promos
    assert _export_promos(client, tag, "unlinked") == {f"{tag}-unlinked"}
    assert _export_promos(client, tag, "unlinked,linked_to_trashed") == {f"{tag}-unlinked", f"{tag}-trashed"}


def test_unknown_attachment_state_is_422_on_export_and_search(client, promos):
    fields = [{"field_key": "description"}]
    assert client.post(EXPORT, json={"resource": "promotions", "fields": fields,
                                     "promotion_attachment_state": "bogus"}).status_code == 422
    assert client.post(EXPORT, json={"resource": "promotions", "fields": fields,
                                     "promotion_attachment_state": "unlinked,bogus"}).status_code == 422
    assert client.post(SEARCH, json={"resource": "promotions",
                                     "promotion_attachment_state": "bogus"}).status_code == 422


# ---- 7. Tickets board: one union test per param (guard; may already pass). The board sends no source. ----

KANBAN = "/api/v1/tickets-management/tickets/kanban"


@pytest.mark.parametrize("param,union,expect,single,single_expect", [
    ("status", "draft,resolved", ("r1", "r3"), "submitted", ("r2", "r4")),
    ("priority", "high,low", ("r1", "r2", "r4"), "medium", ("r3",)),
    ("category", "question,request", ("r1", "r3"), "bug", ("r2", "r4")),
])
def test_tickets_kanban_unions_each_param(client, db, param, union, expect, single, single_expect):
    from app.models.tickets import Ticket

    tag = unique_code("KB", alpha=True)
    rows = {}
    for key, st, pr, ca in (("r1", "draft", "high", "question"), ("r2", "submitted", "low", "bug"),
                            ("r3", "resolved", "medium", "request"), ("r4", "submitted", "high", "bug")):
        t = Ticket(id=str(uuid.uuid4()), ticket_number=f"{tag}-{key}", title=f"ZZT {tag} {key}", status=st,
                   priority=pr, category=ca, source_channel="manual", raised_by_kind="user")
        db.add(t)
        rows[key] = t.id
    db.flush()

    def ids(pairs):
        resp = get(client, KANBAN, pairs)
        assert resp.status_code == 200, resp.text
        return {t["id"] for col in resp.json()["columns"].values() for t in col} & set(rows.values())

    assert ids([(param, union)]) == {rows[k] for k in expect}
    assert ids([(param, single)]) == {rows[k] for k in single_expect}
    a, b = union.split(",")
    assert ids([(param, a), (param, b)]) == {rows[k] for k in expect}
