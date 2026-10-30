"""Phase 2 RED tests - the outstanding bases of `GET /api/v1/order-management/report-ask`
(lane REPORT-UNIFY, slice 1, engine).

`documentation/plans/reports/PLAN-report-unify-27oct.md` section 0 (Q2) and section 1 and
`report-unify-27oct-acceptance-criteria.md`: AC-RU-8, AC-RU-8a, AC-RU-8b, AC-RU-8c. The spec
filter, `group_by=spec:<key>` and the tally are in `test_report_unify_spec_route.py`.

Postgres only (`tests/_pg_fixture.py`), every row seeded here (CI's database has none).

Readings the tester PINNED where the contract is silent (flagged to the captain):
* `not_applied` is a TOP-LEVEL list of `{filter, value, reason}`; `filter` is the catalogue word
  (`product`, `brand`, `category`, `spec`, `location`, `channel`).
* `unpaid` rows: a customer row is named by the customer's name, a sales agent row by the agent's
  code (what every other basis prints). Month row names are not asserted, only the amounts.
* a `pending_delivery` / `unpaid` body for an absent period: the echoed `date_from` / `date_to`
  are not asserted.
* AC-RU-8 (outstanding RM) and the `period_required` pins for delivered / ordered pass today by
  design (the basis and the rule exist); they are regression pins, not red tests.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.finance import CANCELLED, POSTED, BillingDocument
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._pg_fixture import unique_code
from tests._report_ask_so_seed import seed_so_line
from tests._report_unify_seed import make_product, mark_delivered, seed_registry
from tests._sales_report_do_seed import (  # noqa: F401  (client / db are fixtures)
    _as_contact,
    _contact,
    _link,
    client,
    db,
    line,
    money,
    seed_agent,
    seed_customer,
    seed_do,
    seed_so,
    warehouse,
)
from tests._brand_scope_seed import api, world  # noqa: F401  (phase 3 S6 fixtures)
from tests.test_report_ask_route import _brand, _category
from tests.test_top_selling_report import _access

D = Decimal
ROUTE = "/api/v1/order-management/report-ask"
KEY = {"X-API-Key": "k"}
SEP_WINDOW = {"date_from": "2026-09-01", "date_to": "2026-09-30"}
SEP, AUG, OLD = date(2026, 9, 10), date(2026, 8, 15), date(2019, 3, 1)


# ------------------------------------------------------------------------- helpers


def _ask(client, contact, *, period=SEP_WINDOW, **params):
    q = {**(period or {}), **_as_contact(contact), **params}
    q = {k: v for k, v in q.items() if v is not None}
    return client.get(ROUTE, params=q, headers=KEY)


def _ok(client, contact, **params):
    resp = _ask(client, contact, **params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _grant(db, contact, *keys):
    """Exactly `keys` as the contact's reveals."""
    from app.services.contact_field_reveal_service import set_granted_keys

    set_granted_keys(db, contact.id, list(keys), actor_id=None)
    db.flush()


def _staff(db):
    contact = _contact(db)
    _access(db, contact, "Sorento Office")
    _grant(db, contact, "sales_orders.sales_report", "sales_orders.outstanding")  # both reveals (owner Q6)
    db.commit()
    return contact


def _tot(body):
    return body["total"]["qty"], money(body["total"]["amount"])


def _sum(body):
    return sum(r["qty"] for r in body["rows"]), sum(money(r["amount"]) for r in body["rows"])


def _na(body):
    return body.get("not_applied") or []


# ================================================================ AC-RU-8: outstanding carries qty and RM


def test_ac_ru_8_outstanding_carries_qty_and_rm_of_the_open_remainder(client, db):
    """AC-RU-8: qty 10, delivered 4, line_total 1000.00 -> qty 6 and RM 600.00 (line_total x open / ordered)."""
    cust = seed_customer(db, name=unique_code("Cust"))
    prod = make_product(db, unique_code("OUT"))
    seed_so_line(db, cust=cust, prod=prod, qty=10, delivered=4, total="1000.00", order_date=SEP)
    db.commit()
    body = _ok(client, _staff(db), basis="outstanding", customer_ids=[cust.id])
    assert body["basis"] == "outstanding", body
    assert _tot(body) == (6, D("600.00")), body["total"]


# ================================================================ AC-RU-8a: pending_delivery


def _pending_world(db):
    """Five DOs over three products (all AutoCount lines, so a line's amount is its own total):

        DO1 C1 SO1(A1, retail)   Sep   pA W1 3 / 300 | pC W2 2 / 200
        DO2 C2 SO2(A2, project)  Sep   pB W1 5 / 500
        DO3 C1 SO1               Sep   pA W1 7 / 700    DELIVERED (status + date): in nothing
        DO4 C1 SO1               Aug   pC W2 1 / 100
        DO5 C2 SO2               2019  pB W1 4 / 400

    pA, pB brand A cat X p_trap | pC brand B cat Y s_trap
    September: 10 / 1000. Every date: 15 / 1500. August: 1 / 100.
    """
    seed_registry(db)
    w = SimpleNamespace()
    w.c1, w.c2 = seed_customer(db, name=unique_code("C1")), seed_customer(db, name=unique_code("C2"))
    w.w1 = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("W1"))
    w.w2 = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("W2"))
    w.brand_a, w.brand_b = _brand(db, "ZZT-BRAND-A"), _brand(db, "ZZT-BRAND-B")
    w.cat_x, w.cat_y = _category(db, "ZZT-CAT-X"), _category(db, "ZZT-CAT-Y")
    w.a1, w.a2 = seed_agent(db, code=unique_code("AG1")), seed_agent(db, code=unique_code("AG2"))
    w.pa = make_product(db, unique_code("PA"), category=w.cat_x, brand=w.brand_a, specs={"trap_type": "p_trap"})
    w.pb = make_product(db, unique_code("PB"), category=w.cat_x, brand=w.brand_a, specs={"trap_type": "p_trap"})
    w.pc = make_product(db, unique_code("PC"), category=w.cat_y, brand=w.brand_b, specs={"trap_type": "s_trap"})
    so1 = seed_so(db, customer_id=w.c1.id, agent_id=w.a1.id, demand_class="retail")
    so2 = seed_so(db, customer_id=w.c2.id, agent_id=w.a2.id, demand_class="project")
    kw = dict(source_book="db1")
    seed_do(db, customer_id=w.c1.id, order_date=SEP, sales_order_id=so1.id, **kw, lines=[
        line(w.pa.id, w.w1.id, 3, total="300.00"), line(w.pc.id, w.w2.id, 2, total="200.00")])
    seed_do(db, customer_id=w.c2.id, order_date=SEP, sales_order_id=so2.id, **kw, lines=[
        line(w.pb.id, w.w1.id, 5, total="500.00")])
    done = seed_do(db, customer_id=w.c1.id, order_date=SEP, sales_order_id=so1.id, **kw, lines=[
        line(w.pa.id, w.w1.id, 7, total="700.00")])
    mark_delivered(db, done, SEP)
    seed_do(db, customer_id=w.c1.id, order_date=AUG, sales_order_id=so1.id, **kw, lines=[
        line(w.pc.id, w.w2.id, 1, total="100.00")])
    seed_do(db, customer_id=w.c2.id, order_date=OLD, sales_order_id=so2.id, **kw, lines=[
        line(w.pb.id, w.w1.id, 4, total="400.00")])
    w.done = done
    db.commit()
    return w


def test_ac_ru_8a_pending_delivery_counts_only_lines_of_undelivered_dos(client, db):
    """AC-RU-8a: the delivered DO (7 / 700) is in no total; September holds 10 / 1000."""
    _pending_world(db)
    body = _ok(client, _staff(db), basis="pending_delivery")
    assert body["status"] == "ok" and body["basis"] == "pending_delivery", body
    assert _tot(body) == (10, D("1000.00")), body["total"]


def test_ac_ru_8a_a_fully_delivered_do_appears_in_no_row(client, db):
    """AC-RU-8a: group_by=product: pA is 3 / 300 (its delivered 7 / 700 line is nowhere)."""
    w = _pending_world(db)
    body = _ok(client, _staff(db), basis="pending_delivery", group_by="product", top_n=10)
    got = {r["name"]: (r["qty"], money(r["amount"])) for r in body["rows"]}
    assert got == {
        w.pb.product_code: (5, D("500.00")),
        w.pa.product_code: (3, D("300.00")),
        w.pc.product_code: (2, D("200.00")),
    }, body["rows"]
    assert [r["name"] for r in body["rows"]] == [w.pb.product_code, w.pa.product_code, w.pc.product_code]


def test_ac_ru_8a_total_equals_sum_by_customer_equals_sum_by_product(client, db):
    """AC-RU-8a: 10 / 1000 three ways; by customer C1 500, C2 500."""
    w = _pending_world(db)
    contact = _staff(db)
    total = _ok(client, contact, basis="pending_delivery")
    by_customer = _ok(client, contact, basis="pending_delivery", group_by="customer", top_n=10)
    by_product = _ok(client, contact, basis="pending_delivery", group_by="product", top_n=10)
    assert _tot(total) == _sum(by_customer) == _sum(by_product) == (10, D("1000.00"))
    assert {r["name"]: money(r["amount"]) for r in by_customer["rows"]} == {
        w.c1.customer_name: D("500.00"), w.c2.customer_name: D("500.00")}, by_customer["rows"]


def test_ac_ru_8a_a_delivered_status_without_a_delivery_date_is_still_pending(client, db):
    """AC-RU-8a: the predicate is `_outstanding_clause`: delivered status with no date is NOT delivered."""
    w = _pending_world(db)
    mark_delivered(db, w.done, SEP, with_date=False)
    db.commit()
    body = _ok(client, _staff(db), basis="pending_delivery")
    assert _tot(body) == (17, D("1700.00")), body["total"]  # the 7 / 700 line is pending again


def test_ac_ru_8a_the_amount_is_the_delivery_order_lines_own_line_amount(client, db):
    """AC-RU-8a: a legacy DO repeats its DOC total (300) on every line; the dataset counts it once
    (split by weight), so two lines sum to 300 and not 600."""
    seed_registry(db)
    cust = seed_customer(db, name=unique_code("Cust"))
    wh = warehouse(db, company_id=DEFAULT_COMPANY_ID)
    p1, p2 = make_product(db, unique_code("L1")), make_product(db, unique_code("L2"))
    seed_do(db, customer_id=cust.id, order_date=SEP, source_book=None, lines=[
        line(p1.id, wh.id, 1, price="100.00", total="300.00"), line(p2.id, wh.id, 2, price="100.00", total="300.00")])
    db.commit()
    body = _ok(client, _staff(db), basis="pending_delivery", customer_ids=[cust.id])
    assert _tot(body) == (3, D("300.00")), body["total"]


def _filter_cases(w):
    return {
        "customer": ({"customer_ids": [w.c1.id]}, (5, D("500.00"))),
        "product": ({"product_ids": [w.pa.id]}, (3, D("300.00"))),
        "brand": ({"brand_ids": [w.brand_b.id]}, (2, D("200.00"))),
        "category": ({"category_ids": [w.cat_y.id]}, (2, D("200.00"))),
        "sales_agent": ({"sales_agent_ids": [w.a2.id]}, (5, D("500.00"))),
        "location": ({"warehouse_codes": [w.w2.warehouse_code]}, (2, D("200.00"))),
        "channel_project": ({"channel": "project"}, (5, D("500.00"))),
        "channel_dealer": ({"channel": "dealer"}, (5, D("500.00"))),
        "spec": ({"spec": "trap_type:s_trap"}, (2, D("200.00"))),
        "spec_p_trap": ({"spec": "trap_type:p_trap"}, (8, D("800.00"))),
    }


@pytest.mark.parametrize(
    "case",
    ["customer", "product", "brand", "category", "sales_agent", "location", "channel_project", "channel_dealer",
     "spec", "spec_p_trap"],
)
def test_ac_ru_8a_pending_delivery_takes_every_dataset_filter_and_spec(client, db, case):
    """AC-RU-8a: customer, product, brand, category, sales agent, location, channel and spec narrow it."""
    w = _pending_world(db)
    params, expected = _filter_cases(w)[case]
    body = _ok(client, _staff(db), basis="pending_delivery", **params)
    assert _tot(body) == expected, (case, body["total"])
    assert not _na(body), body


@pytest.mark.parametrize("dimension", ["customer", "product", "brand", "category", "sales_agent", "location", "channel", "month"])
def test_ac_ru_8a_pending_delivery_groups_by_every_dataset_dimension(client, db, dimension):
    """AC-RU-8a: every grouping sums to the 10 / 1000 total."""
    _pending_world(db)
    body = _ok(client, _staff(db), basis="pending_delivery", group_by=dimension, top_n=20)
    assert body["group_by"] == dimension, body
    assert _sum(body) == _tot(body) == (10, D("1000.00")), body["rows"]


# ================================================================ AC-RU-8b: unpaid


def _doc(db, *, cust, agent, when, outstanding, status=POSTED, document_type="invoice"):
    row = BillingDocument(
        id=str(uuid.uuid4()), company_id=DEFAULT_COMPANY_ID, document_type=document_type,
        doc_no=unique_code("IV"), doc_date=when, status=status, customer_id=cust.id,
        sales_agent_id=agent.id if agent is not None else None,
        net_total=D("1000.00"), tax_total=D("0"), total=D("1000.00"), local_net_total=D("1000.00"),
        outstanding=None if outstanding is None else D(str(outstanding)),
        source_ref=f"SRT_DB:{uuid.uuid4().hex}",
    )
    db.add(row)
    db.flush()
    return row


def _unpaid_world(db):
    """Billing documents (outstanding in RM):

        IV1 C1 A1 2026-09-05  400   posted               counts
        IV2 C2 A2 2026-09-20  250   posted               counts
        IV3 C1 A1 2026-08-15  100   posted               counts (August)
        IV4 C1 A2 2019-03-01   50   posted               counts (every date only)
        IV5 C1 A1 2026-09-06    0   posted, paid         out
        IV6 C1 A1 2026-09-07  NULL  posted, not synced   out
        IV7 C1 A1 2026-09-08  999   CANCELLED            out
        CN1 C2 A2 2026-09-09  -75   posted credit note   out (outstanding is not above 0)

    September: 650 | every date: 800 | by customer (every date) C1 550, C2 250 | by agent A1 500, A2 300.
    """
    seed_registry(db)
    w = SimpleNamespace()
    w.c1, w.c2 = seed_customer(db, name=unique_code("C1")), seed_customer(db, name=unique_code("C2"))
    w.a1, w.a2 = seed_agent(db, code=unique_code("AG1")), seed_agent(db, code=unique_code("AG2"))
    _doc(db, cust=w.c1, agent=w.a1, when=date(2026, 9, 5), outstanding="400.00")
    _doc(db, cust=w.c2, agent=w.a2, when=date(2026, 9, 20), outstanding="250.00")
    _doc(db, cust=w.c1, agent=w.a1, when=AUG, outstanding="100.00")
    _doc(db, cust=w.c1, agent=w.a2, when=OLD, outstanding="50.00")
    _doc(db, cust=w.c1, agent=w.a1, when=date(2026, 9, 6), outstanding="0.00")
    _doc(db, cust=w.c1, agent=w.a1, when=date(2026, 9, 7), outstanding=None)
    _doc(db, cust=w.c1, agent=w.a1, when=date(2026, 9, 8), outstanding="999.00", status=CANCELLED)
    _doc(db, cust=w.c2, agent=w.a2, when=date(2026, 9, 9), outstanding="-75.00", document_type="credit_note")
    w.brand, w.cat = _brand(db, "ZZT-UP-BRAND"), _category(db, "ZZT-UP-CAT")
    w.prod = make_product(db, unique_code("UP"), category=w.cat, brand=w.brand, specs={"trap_type": "p_trap"})
    w.wh = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("UW"))
    db.commit()
    return w


def test_ac_ru_8b_unpaid_sums_outstanding_of_posted_uncancelled_documents_owing_money(client, db):
    """AC-RU-8b: September 650 (IV1 + IV2); paid, unsynced, cancelled and credit rows are out; qty is 0."""
    _unpaid_world(db)
    body = _ok(client, _staff(db), basis="unpaid")
    assert body["status"] == "ok" and body["basis"] == "unpaid", body
    assert _tot(body) == (0, D("650.00")), body["total"]


def test_ac_ru_8b_unpaid_groups_by_customer(client, db):
    """AC-RU-8b: group_by=customer, every date: C1 550 (IV1 + IV3 + IV4), C2 250; rows sum to the total."""
    w = _unpaid_world(db)
    body = _ok(client, _staff(db), basis="unpaid", group_by="customer", top_n=10, period=None)
    assert [(r["name"], money(r["amount"])) for r in body["rows"]] == [
        (w.c1.customer_name, D("550.00")), (w.c2.customer_name, D("250.00"))], body["rows"]
    assert _sum(body)[1] == money(body["total"]["amount"]) == D("800.00")


def test_ac_ru_8b_unpaid_groups_by_sales_agent(client, db):
    """AC-RU-8b: group_by=sales_agent, every date: A1 500 (IV1 + IV3), A2 300 (IV2 + IV4)."""
    w = _unpaid_world(db)
    body = _ok(client, _staff(db), basis="unpaid", group_by="sales_agent", top_n=10, period=None)
    assert [(r["name"], money(r["amount"])) for r in body["rows"]] == [
        (w.a1.sales_agent, D("500.00")), (w.a2.sales_agent, D("300.00"))], body["rows"]


def test_ac_ru_8b_unpaid_groups_by_month_of_the_document_date(client, db):
    """AC-RU-8b: group_by=month, every date: 650 (Sep), 100 (Aug), 50 (2019), by document date."""
    _unpaid_world(db)
    body = _ok(client, _staff(db), basis="unpaid", group_by="month", top_n=12, period=None)
    assert sorted(money(r["amount"]) for r in body["rows"]) == [D("50.00"), D("100.00"), D("650.00")], body["rows"]
    assert _sum(body)[1] == money(body["total"]["amount"]) == D("800.00")


def test_ac_ru_8b_unpaid_takes_the_customer_and_sales_agent_filters(client, db):
    """AC-RU-8b: customer C2 -> 250; sales agent A1 (September) -> 400."""
    w = _unpaid_world(db)
    contact = _staff(db)
    assert _tot(_ok(client, contact, basis="unpaid", customer_ids=[w.c2.id])) == (0, D("250.00"))
    assert _tot(_ok(client, contact, basis="unpaid", sales_agent_ids=[w.a1.id])) == (0, D("400.00"))


def test_ac_ru_8b_unpaid_cannot_group_by_product(client, db):
    """AC-RU-8b: a document has no product: 422 unknown_group_by."""
    _unpaid_world(db)
    resp = _ask(client, _staff(db), basis="unpaid", group_by="product", top_n=5)
    assert resp.status_code == 422, resp.text
    assert resp.json().get("code") == "unknown_group_by", resp.text


@pytest.mark.parametrize("word", ["product", "brand", "category", "spec", "location", "channel"])
def test_ac_ru_8b_a_per_line_filter_on_unpaid_is_not_applied_and_the_total_is_still_returned(client, db, word):
    """AC-RU-8b: product / brand / category / spec / location / channel -> 200, echoed under
    not_applied (per_document), total = the unfiltered unpaid total (650 in September)."""
    w = _unpaid_world(db)
    params = {
        "product": {"product_ids": [w.prod.id]},
        "brand": {"brand_ids": [w.brand.id]},
        "category": {"category_ids": [w.cat.id]},
        "spec": {"spec": "trap_type:p_trap"},
        "location": {"warehouse_codes": [w.wh.warehouse_code]},
        "channel": {"channel": "project"},
    }[word]
    body = _ok(client, _staff(db), basis="unpaid", **params)
    assert any(n.get("filter") == word and n.get("reason") == "per_document" for n in _na(body)), body.get("not_applied")
    assert _tot(body) == (0, D("650.00")), body["total"]


# ================================================================ AC-RU-8c: the period is optional on outstanding bases


def test_ac_ru_8c_outstanding_with_no_period_means_all_dates(client, db):
    """AC-RU-8c: an open line dated 2019 counts with no dates and is out of a September window."""
    cust = seed_customer(db, name=unique_code("Cust"))
    prod = make_product(db, unique_code("OLD"))
    seed_so_line(db, cust=cust, prod=prod, qty=10, delivered=0, total="100.00", order_date=OLD)
    seed_so_line(db, cust=cust, prod=prod, qty=5, delivered=0, total="50.00", order_date=SEP)
    db.commit()
    contact = _staff(db)
    everything = _ask(client, contact, basis="outstanding", customer_ids=[cust.id], period=None)
    assert everything.status_code == 200, everything.text
    assert _tot(everything.json()) == (15, D("150.00")), everything.json()["total"]
    named = _ok(client, contact, basis="outstanding", customer_ids=[cust.id])
    assert _tot(named) == (5, D("50.00")), named["total"]


def test_ac_ru_8c_pending_delivery_with_no_period_means_all_dates(client, db):
    """AC-RU-8c: every date 15 / 1500 (August and 2019 DOs count); a named window filters the DO date."""
    _pending_world(db)
    contact = _staff(db)
    everything = _ask(client, contact, basis="pending_delivery", period=None)
    assert everything.status_code == 200, everything.text
    assert _tot(everything.json()) == (15, D("1500.00")), everything.json()["total"]
    assert _tot(_ok(client, contact, basis="pending_delivery")) == (10, D("1000.00"))
    august = _ok(client, contact, basis="pending_delivery", period={"date_from": "2026-08-01", "date_to": "2026-08-31"})
    assert _tot(august) == (1, D("100.00")), august["total"]


def test_ac_ru_8c_unpaid_with_no_period_means_all_dates(client, db):
    """AC-RU-8c: a 2019 document counts with no dates (800); September filters the document date (650)."""
    _unpaid_world(db)
    contact = _staff(db)
    everything = _ask(client, contact, basis="unpaid", period=None)
    assert everything.status_code == 200, everything.text
    assert _tot(everything.json()) == (0, D("800.00")), everything.json()["total"]
    assert _tot(_ok(client, contact, basis="unpaid")) == (0, D("650.00"))
    august = _ok(client, contact, basis="unpaid", period={"date_from": "2026-08-01", "date_to": "2026-08-31"})
    assert _tot(august) == (0, D("100.00")), august["total"]


@pytest.mark.parametrize("basis", ["delivered", "ordered"])
def test_ac_ru_8c_delivered_and_ordered_still_need_a_period(client, db, basis):
    """AC-RU-8c: only the outstanding bases relax the period; delivered / ordered stay 422 period_required.
    (Passes today: a regression pin.)"""
    resp = _ask(client, _staff(db), basis=basis, period=None)
    assert resp.status_code == 422, resp.text
    assert resp.json().get("code") == "period_required", resp.text


@pytest.mark.parametrize("basis", ["outstanding", "pending_delivery", "unpaid"])
@pytest.mark.parametrize("given", ["date_from", "date_to"])
def test_ac_ru_8c_one_date_alone_on_an_outstanding_basis_is_422_period_required(client, db, basis, given):
    """AC-RU-8c (plan section 1): both dates or neither; one alone is 422 period_required.
    (Passes today: the period check runs before the basis check; a regression pin.)"""
    resp = _ask(client, _staff(db), basis=basis, period={given: SEP_WINDOW[given]})
    assert resp.status_code == 422, resp.text
    assert resp.json().get("code") == "period_required", resp.text


@pytest.mark.parametrize("dimension", ["brand", "category", "location", "channel"])
def test_ac_ru_8b_unpaid_cannot_group_by_a_per_line_dimension(client, db, dimension):
    """AC-RU-8b (plan section 1): brand / category / location / channel are 422 unknown_group_by like product."""
    _unpaid_world(db)
    resp = _ask(client, _staff(db), basis="unpaid", group_by=dimension, top_n=5)
    assert resp.status_code == 422, resp.text
    assert resp.json().get("code") == "unknown_group_by", resp.text


# ================================================================ AC-RU-9a: the reveal depends on the basis (owner Q6)


def _holder(db, *keys, office=True):
    contact = _contact(db, granted=False)
    if office:
        _access(db, contact, "Sorento Office")
    _grant(db, contact, *keys)
    db.commit()
    return contact


@pytest.mark.parametrize("basis", ["outstanding", "pending_delivery", "unpaid"])
def test_ac_ru_9a_a_contact_with_the_outstanding_reveal_only_gets_every_outstanding_kind(client, db, basis):
    """AC-RU-9a: the outstanding kinds need `sales_orders.outstanding` and no Sales report reveal."""
    _unpaid_world(db)
    contact = _holder(db, "sales_orders.outstanding")
    body = _ok(client, contact, basis=basis, period=None)
    assert body["status"] == "ok" and body["basis"] == basis, body


@pytest.mark.parametrize("basis", ["delivered", "ordered"])
def test_ac_ru_9a_a_contact_with_the_outstanding_reveal_only_is_refused_a_sales_basis(client, db, basis):
    """AC-RU-9a: a sales basis keeps the Sales report reveal and its existing refusal."""
    _unpaid_world(db)
    contact = _holder(db, "sales_orders.outstanding")
    resp = _ask(client, contact, basis=basis)
    assert resp.status_code == 403, resp.text
    assert resp.json().get("code") == "sales_report_not_enabled", resp.text


@pytest.mark.parametrize("basis", ["outstanding", "unpaid"])
def test_ac_ru_9a_a_contact_with_the_sales_report_reveal_only_is_refused_an_outstanding_kind(client, db, basis):
    """AC-RU-9a: the refusal has the route's shape (403, a code) and names the Outstanding reveal. Pending delivery is
    open to office staff without the reveal (owner 29 Oct, REPORT-OUTSTANDING-SUMMARY, as before #1922)."""
    _unpaid_world(db)
    contact = _holder(db, "sales_orders.sales_report")
    resp = _ask(client, contact, basis=basis, period=None)
    assert resp.status_code == 403, resp.text
    assert resp.json().get("code") == "outstanding_not_enabled", resp.text
    assert "outstanding" in resp.text.lower(), resp.text


def test_ac_ru_9a_a_linked_dealer_with_the_outstanding_reveal_sees_only_its_own_unpaid_documents(client, db):
    """AC-RU-9a: a customer-scoped contact stays forced to its links on unpaid (C1 only: 550 of the 800)."""
    w = _unpaid_world(db)
    contact = _holder(db, "sales_orders.outstanding", office=False)
    _link(db, contact, w.c1)
    db.commit()
    body = _ok(client, contact, basis="unpaid", period=None)
    assert _tot(body) == (0, D("550.00")), body["total"]
    named = _ask(client, contact, basis="unpaid", period=None, customer_ids=[w.c2.id])
    assert named.status_code == 403, named.text  # another customer's documents are not its own


# ================================================================ security S1: unpaid is receivables, finance data


def test_unpaid_on_the_report_ask_needs_both_the_contacts_outstanding_reveal_and_the_act_as_finance_view(db) -> None:
    """Owner 28 Oct: `basis=unpaid` on the chatbot route needs BOTH the contact's Outstanding reveal AND
    `finance.billing_documents.view` on the act-as user. The other outstanding kinds need the reveal only."""
    from tests.test_sales_yearly_routes import _client, _user

    holder = _holder(db, "sales_orders.outstanding")
    sales_only = _holder(db, "sales_orders.sales_report")
    principal = _user(db, DEFAULT_COMPANY_ID)
    with _client(db, principal, allow=("order_management.orders.view",)) as c:  # reveal, but no finance view
        refused = _ask(c, holder, basis="unpaid")
        assert refused.status_code == 403 and refused.json()["code"] == "unpaid_needs_finance_view", refused.text
        for basis in ("outstanding", "pending_delivery"):
            assert _ask(c, holder, basis=basis).status_code == 200, basis
        assert c.get("/api/v1/reports/unpaid_documents").status_code == 403  # the screen still needs the finance slug
    finance = ("order_management.orders.view", "finance.billing_documents.view")
    with _client(db, principal, allow=finance) as c:
        assert _ask(c, holder, basis="unpaid").status_code == 200  # both
        no_reveal = _ask(c, sales_only, basis="unpaid")  # the slug without the contact's reveal
        assert no_reveal.status_code == 403 and no_reveal.json()["code"] == "outstanding_not_enabled", no_reveal.text


# ================================================================ phase 3 S6: unpaid for a brand-scoped contact


def test_s6_a_brand_scoped_contact_is_refused_unpaid_because_an_invoice_has_no_brand(world, api) -> None:
    """Phase 3 S6 (mutation K6): an invoice carries no brand, so `unpaid` cannot be held to a brand-scoped contact's brands:
    403 `report_dimension_not_allowed`. The unscoped contact reads it, and the scoped one still reads the other kinds."""
    window = {"date_from": "2026-01-01", "date_to": "2026-12-31"}
    refused = api.get("/api/v1/order-management/report-ask", world.scoped, basis="unpaid", **window)
    assert refused.status_code == 403, refused.text
    assert refused.json()["code"] == "report_dimension_not_allowed", refused.text
    assert api.get("/api/v1/order-management/report-ask", world.unscoped, basis="unpaid", **window).status_code == 200
    assert api.get("/api/v1/order-management/report-ask", world.scoped, basis="outstanding", **window).status_code == 200


def test_tbc_a_class_only_contact_keeps_unpaid(world, api, db) -> None:
    """TAG-BRAND-CLASS crew ruling (b): a contact limited by item class alone (All brands + "No class",
    the Serene tag) names no brand, and an invoice total names no product: unpaid is answered."""
    from app.models.access import RespondContact
    from tests._brand_scope_seed import contact

    window = {"date_from": "2026-01-01", "date_to": "2026-12-31"}
    class_only = contact(db, access_code=world.access_code)
    db.query(RespondContact).filter(RespondContact.id == class_only.id).update(
        {"allowed_item_class_codes": ["__NONE__"]}, synchronize_session=False
    )
    db.commit()
    resp = api.get("/api/v1/order-management/report-ask", class_only, basis="unpaid", **window)
    assert resp.status_code == 200, resp.text


# ================================================================ the year dimension (crew 28 Oct): rows sum to the total


def test_unpaid_year_rows_sum_to_the_total_across_two_years(client, db):
    """Every date: 2026 holds IV1 + IV2 + IV3 (750), 2019 holds IV4 (50); the rows add up to the 800 total."""
    _unpaid_world(db)
    contact = _staff(db)
    whole = _ok(client, contact, basis="unpaid", period=None)
    body = _ok(client, contact, basis="unpaid", group_by="year", top_n=10, period=None)
    assert {r["name"]: money(r["amount"]) for r in body["rows"]} == {"2026": D("750.00"), "2019": D("50.00")}, body["rows"]
    assert sum(money(r["amount"]) for r in body["rows"]) == money(whole["total"]["amount"]) == D("800.00"), body


def test_pending_delivery_year_rows_sum_to_the_total_across_two_years(client, db):
    """Every date: 2026 holds the September and August DOs (11 / 1100), 2019 the old one (4 / 400); 15 / 1500 in all."""
    _pending_world(db)
    contact = _staff(db)
    whole = _ok(client, contact, basis="pending_delivery", period=None)
    body = _ok(client, contact, basis="pending_delivery", group_by="year", top_n=10, period=None)
    assert {r["name"]: (r["qty"], money(r["amount"])) for r in body["rows"]} == {
        "2026": (11, D("1100.00")), "2019": (4, D("400.00")),
    }, body["rows"]
    assert sum(r["qty"] for r in body["rows"]) == whole["total"]["qty"] == 15, body
