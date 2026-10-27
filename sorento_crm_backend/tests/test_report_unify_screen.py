"""Phase 2 RED tests - REPORT-UNIFY slice 4: the "Sales & outstanding" screen, backend half.

`documentation/plans/reports/PLAN-report-unify-27oct.md` section 3b (owner Q5 (a)): the six ask definitions
are registered on the generic reports API (`GET /api/v1/reports`, `GET /{key}`, `POST /{key}/run`) so staff can
check the bot's number. Postgres only, every row seeded here (CI's database has none).

Readings the tester PINNED where the plan is silent (flagged to the captain):
* Keys: the definitions already carry keys, so those are the registered keys (no `sales_ask_*` renames):
  invoiced `sales_invoiced_ask`, delivered `sales_order_lines_ask_delivered`, ordered
  `sales_order_lines_ask_ordered`, undelivered orders `sales_order_lines_ask_outstanding`, pending delivery
  `delivery_order_lines_pending`, unpaid invoices `unpaid_documents`. The tally test also asserts each key IS the
  definition `ask.CATALOGUE["sales"][basis]` runs, so the screen and the bot cannot drift to two definitions.
  (`delivery_order_lines` itself, the DO-date delivered report, is NOT one of the six.)
* Permission: `sales.reports.view` for invoiced; `order_management.orders.view` for the other five (unpaid
  included). The plan's "Outstanding / Sales report split" is read as the contact reveals of Q6, which the
  generic API (user permission slugs only) cannot express, so it is not tested here.
* The `spec` param's option values are `key:value` strings (the route's own `spec=` form) and its labels are
  "<registry label>: <value label>" ("Trap type: P-trap"); one option per enum registry value.
* Option values of customer, sales agent, brand and category are the row ids; labels are the customer name, the
  agent code, the brand name and the category name.
* The tally compares the screen's pivot grand total (rows = month, cols = all, measures qty and amount) with
  `GET /order-management/report-ask` for the same basis, September period and filters.
* A pivot row key the unpaid definition does not have (`product`) is 422.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.product import Brand, ProductCategory
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._pg_fixture import unique_code
from tests._report_unify_seed import make_product, seed_registry
from tests._sales_report_do_seed import (  # noqa: F401  (client / db are fixtures)
    _as_contact,
    _contact,
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
from tests._report_ask_so_seed import seed_so_line
from tests._sales_unified_seed import doc, line as bline
from tests.test_sales_yearly_routes import _client, _user
from tests.test_top_selling_report import _access

D = Decimal
SEP = date(2026, 9, 10)
PERIOD = {"kind": "custom", "from": "2026-09-01", "to": "2026-09-30"}
ASK = "/api/v1/order-management/report-ask"
KEYS = {
    "invoiced": "sales_invoiced_ask",
    "delivered": "sales_order_lines_ask_delivered",
    "ordered": "sales_order_lines_ask_ordered",
    "outstanding": "sales_order_lines_ask_outstanding",
    "pending_delivery": "delivery_order_lines_pending",
    "unpaid": "unpaid_documents",
}
ORDER_BASES = [b for b in KEYS if b != "invoiced"]
NO_SPEC = ["unpaid"]
ORDERS_VIEW, REPORTS_VIEW = "order_management.orders.view", "sales.reports.view"


# ------------------------------------------------------------------------- helpers


def _meta(client, key):
    return client.get(f"/api/v1/reports/{key}")


def _run(client, key, rows="month", **params):
    body = {
        "params": {"date_basis": "order_date", "period": PERIOD, **params},
        "view": {
            "params": {"date_basis": "order_date", "period": PERIOD, **params},
            "detail": {"columns": [], "order": []},
            "pivot": {"rows": rows, "cols": "all", "measures": ["qty", "amount"]},
        },
    }
    return client.post(f"/api/v1/reports/{key}/run", json=body)


def _grand(resp):
    assert resp.status_code == 200, resp.text
    grand = resp.json()["layouts"]["summary"]["grand_total"] or {}
    return int(D(str(grand.get("qty") or 0))), money(grand.get("amount") or 0)


def _param(meta, key):
    found = [p for p in meta.json()["params"] if p["key"] == key]
    return found[0] if found else None


def _staff(db):
    """A staff contact holding both reveals the route checks (Q6): Sales report for the sales bases, Outstanding
    for the three outstanding kinds."""
    from app.services.contact_field_reveal_service import set_granted_keys

    contact = _contact(db)
    set_granted_keys(db, contact.id, ["sales_orders.sales_report", "sales_orders.outstanding"], actor_id=None)
    _access(db, contact, "Sorento Office")
    db.commit()
    return contact


def _brand(db, name):
    row = Brand(id=str(uuid.uuid4()), brand_code=unique_code("BR")[:50], brand_name=name, company_id=DEFAULT_COMPANY_ID)
    db.add(row)
    db.flush()
    return row


def _category(db, name):
    row = ProductCategory(id=str(uuid.uuid4()), category_code=unique_code("CAT")[:50], category_name=name,
                          company_id=DEFAULT_COMPANY_ID)
    db.add(row)
    db.flush()
    return row


def _world(db):
    """One world for the six bases (September 2026). Products: pa brand A p_trap, pb brand B s_trap, pc brand A s_trap.

        SO lines (qty 10, 4 delivered; total):  c1 pa 1000 | c1 pb 500 | c2 pc 300
        undelivered DOs (qty / total):          c1 pa 2 / 100 | c1 pb 2 / 50 | c2 pc 2 / 30
        invoices (qty / net, outstanding):      c1 pa 3 / 300 (150) | c1 pb 2 / 200 (80) | c2 pc 4 / 400 (60)
    """
    seed_registry(db)
    w = SimpleNamespace()
    w.c1, w.c2 = seed_customer(db, name=unique_code("C1")), seed_customer(db, name=unique_code("C2"))
    w.agent = seed_agent(db, code=unique_code("AG"))
    w.wh = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("WH"))
    w.brand_a, w.brand_b = _brand(db, unique_code("BRA")), _brand(db, unique_code("BRB"))
    w.cat = _category(db, unique_code("CATX"))
    w.pa = make_product(db, unique_code("PA"), brand=w.brand_a, category=w.cat, specs={"trap_type": "p_trap"})
    w.pb = make_product(db, unique_code("PB"), brand=w.brand_b, category=w.cat, specs={"trap_type": "s_trap"})
    w.pc = make_product(db, unique_code("PC"), brand=w.brand_a, category=w.cat, specs={"trap_type": "s_trap"})
    for cust, prod, total in ((w.c1, w.pa, "1000.00"), (w.c1, w.pb, "500.00"), (w.c2, w.pc, "300.00")):
        seed_so_line(db, cust=cust, prod=prod, qty=10, delivered=4, total=total, agent=w.agent, wh=w.wh, order_date=SEP)
    so1 = seed_so(db, customer_id=w.c1.id, agent_id=w.agent.id, demand_class="retail")
    so2 = seed_so(db, customer_id=w.c2.id, agent_id=w.agent.id, demand_class="retail")
    seed_do(db, customer_id=w.c1.id, order_date=SEP, source_book="db1", sales_order_id=so1.id, lines=[
        line(w.pa.id, w.wh.id, 2, total="100.00"), line(w.pb.id, w.wh.id, 2, total="50.00")])
    seed_do(db, customer_id=w.c2.id, order_date=SEP, source_book="db1", sales_order_id=so2.id, lines=[
        line(w.pc.id, w.wh.id, 2, total="30.00")])
    for cust, prod, qty, net, owing in ((w.c1, w.pa, "3", "300.00", "150.00"), (w.c1, w.pb, "2", "200.00", "80.00"),
                                        (w.c2, w.pc, "4", "400.00", "60.00")):
        header = doc(db, "invoice", net, SEP, customer=cust, agent_row=w.agent, lines=[bline(qty=qty, net=net, prod=prod)])
        header.outstanding = D(owing)
    db.commit()
    return w


# ================================================================ the six definitions are on the generic reports API


@pytest.mark.parametrize("basis", list(KEYS))
def test_slice4_each_ask_definition_answers_the_meta_call(client, db, basis) -> None:
    """Slice 4 / plan 3b: GET /reports/<key> is 200 and names its own key, with a period param."""
    resp = _meta(client, KEYS[basis])
    assert resp.status_code == 200, resp.text
    assert resp.json()["key"] == KEYS[basis], resp.text
    assert _param(resp, "period") is not None, resp.text


@pytest.mark.parametrize("basis", list(KEYS))
def test_slice4_each_ask_definition_answers_the_run_call(client, db, basis) -> None:
    """Slice 4 / plan 3b: POST /reports/<key>/run is 200 and carries a summary layout."""
    _world(db)
    resp = _run(client, KEYS[basis])
    assert resp.status_code == 200, resp.text
    assert "summary" in resp.json()["layouts"], resp.text


def test_slice4_the_catalogue_lists_all_six(client, db) -> None:
    """Slice 4 / plan 3b: the reports catalogue holds the six keys."""
    keys = {r["key"] for r in client.get("/api/v1/reports").json()["reports"]}
    assert set(KEYS.values()) <= keys, keys


def test_slice4_the_registered_keys_are_the_definitions_the_bot_runs() -> None:
    """Slice 4 / plan 3b: one definition per basis, shared by the screen and `ask.CATALOGUE`."""
    from app.services.reports import ask, registry as reg

    for basis, key in KEYS.items():
        assert ask.CATALOGUE["sales"][basis]["definition"].key == key, basis
        assert reg.get(key) is ask.CATALOGUE["sales"][basis]["definition"], basis


# ================================================================ real option lists


@pytest.mark.parametrize("basis", list(KEYS))
def test_slice4_the_customer_and_sales_agent_params_list_the_seeded_rows(client, db, basis) -> None:
    """Slice 4 / plan 3b: customer and sales agent options are real rows (value = id, label = name / code)."""
    w = _world(db)
    meta = _meta(client, KEYS[basis])
    customers = {o["value"]: o["label"] for o in (_param(meta, "customer") or {}).get("options", [])}
    agents = {o["value"]: o["label"] for o in (_param(meta, "sales_agent") or {}).get("options", [])}
    assert customers.get(w.c1.id) == w.c1.customer_name and customers.get(w.c2.id) == w.c2.customer_name, customers
    assert agents.get(w.agent.id) == w.agent.sales_agent, agents


@pytest.mark.parametrize("basis", [b for b in KEYS if b not in NO_SPEC])
def test_slice4_the_brand_and_category_params_list_the_seeded_rows(client, db, basis) -> None:
    """Slice 4 / plan 3b: brand and category options are real rows (value = id, label = name)."""
    w = _world(db)
    meta = _meta(client, KEYS[basis])
    brands = {o["value"]: o["label"] for o in (_param(meta, "brand") or {}).get("options", [])}
    cats = {o["value"]: o["label"] for o in (_param(meta, "category") or {}).get("options", [])}
    assert brands.get(w.brand_a.id) == w.brand_a.brand_name and brands.get(w.brand_b.id) == w.brand_b.brand_name, brands
    assert cats.get(w.cat.id) == w.cat.category_name, cats


# ================================================================ permission (Q6)


def test_slice4_orders_view_alone_sees_and_runs_the_five_order_bases_and_not_invoiced(db) -> None:
    """Slice 4 / Q6: order_management.orders.view opens delivered, ordered, undelivered, pending, unpaid; 403 invoiced."""
    principal = _user(db, DEFAULT_COMPANY_ID)
    with _client(db, principal, allow=(ORDERS_VIEW,)) as c:
        listed = {r["key"] for r in c.get("/api/v1/reports").json()["reports"]}
        for basis in ORDER_BASES:
            assert KEYS[basis] in listed, (basis, listed)
            assert _meta(c, KEYS[basis]).status_code == 200, basis
            assert _run(c, KEYS[basis]).status_code == 200, basis
        assert KEYS["invoiced"] not in listed
        assert _meta(c, KEYS["invoiced"]).status_code == 403
        assert _run(c, KEYS["invoiced"]).status_code == 403


def test_slice4_sales_reports_view_opens_invoiced(db) -> None:
    """Slice 4 / Q6: invoiced needs sales.reports.view, and that slug alone opens it."""
    principal = _user(db, DEFAULT_COMPANY_ID)
    with _client(db, principal, allow=(REPORTS_VIEW,)) as c:
        assert KEYS["invoiced"] in {r["key"] for r in c.get("/api/v1/reports").json()["reports"]}
        assert _meta(c, KEYS["invoiced"]).status_code == 200
        assert _run(c, KEYS["invoiced"]).status_code == 200


@pytest.mark.parametrize("basis", list(KEYS))
def test_slice4_a_user_without_the_permission_gets_403_and_does_not_see_it_listed(db, basis) -> None:
    """Slice 4 / Q6: no permission, 403 on meta and run, and the key is absent from the catalogue."""
    principal = _user(db, DEFAULT_COMPANY_ID)
    with _client(db, principal, allow=()) as c:
        assert _meta(c, KEYS[basis]).status_code == 403
        assert _run(c, KEYS[basis]).status_code == 403
        assert KEYS[basis] not in {r["key"] for r in c.get("/api/v1/reports").json()["reports"]}


# ================================================================ spec on screen


@pytest.mark.parametrize("basis", [b for b in KEYS if b not in NO_SPEC])
def test_slice4_a_spec_select_param_is_offered_on_every_basis_but_unpaid(client, db, basis) -> None:
    """Slice 4 / plan 3b: `spec` is a select param with the registry's key:value options (label "Trap type: P-trap")."""
    _world(db)
    spec = _param(_meta(client, KEYS[basis]), "spec")
    assert spec is not None, basis
    labels = {o["value"]: o["label"] for o in spec["options"]}
    assert labels.get("trap_type:p_trap") == "Trap type: P-trap", labels
    assert "trap_type:s_trap" in labels, labels


def test_slice4_unpaid_has_no_spec_param(client, db) -> None:
    """Slice 4 / plan 3b: an invoice is per document, so unpaid offers no spec (nor product, brand, category, location, channel)."""
    meta = _meta(client, KEYS["unpaid"])
    present = {p["key"] for p in meta.json()["params"]}
    assert present.isdisjoint({"spec", "product", "brand", "category", "location", "channel"}), present
    assert {"customer", "sales_agent"} <= present, present


@pytest.mark.parametrize(
    "basis, expected",
    [
        ("delivered", (4, D("400.00"))),
        ("ordered", (10, D("1000.00"))),
        ("outstanding", (6, D("600.00"))),
        ("pending_delivery", (2, D("100.00"))),
        ("invoiced", (3, D("300.00"))),
    ],
)
def test_slice4_the_spec_condition_narrows_to_the_products_matching_it(client, db, basis, expected) -> None:
    """Slice 4 / plan 3b: spec trap_type:p_trap is product pa only (the same products as the route's spec filter)."""
    _world(db)
    assert _grand(_run(client, KEYS[basis], spec=["trap_type:p_trap"])) == expected


@pytest.mark.parametrize("basis", [b for b in KEYS if b not in NO_SPEC])
def test_slice4_a_spec_matching_no_product_is_zero_never_the_unfiltered_set(client, db, basis) -> None:
    """Slice 4 / plan 3b + AC-RU-4: trap_type:wall matches nothing, so the total is zero."""
    _world(db)
    assert _grand(_run(client, KEYS[basis], spec=["trap_type:wall"])) == (0, D("0.00"))


# ================================================================ the tally: screen total == the bot's number


def _ask_total(client, db, basis, **filters):
    contact = _staff(db)
    q = {"date_from": "2026-09-01", "date_to": "2026-09-30", "basis": basis, **_as_contact(contact), **filters}
    resp = client.get(ASK, params=q, headers={"X-API-Key": "k"})
    assert resp.status_code == 200, resp.text
    total = resp.json()["total"]
    return int(total["qty"]), money(total["amount"])


def _cases(w):
    """(label, screen params, route params)."""
    return [
        ("none", {}, {}),
        ("customer", {"customer": [w.c1.id]}, {"customer_ids": [w.c1.id]}),
        ("brand", {"brand": [w.brand_a.id]}, {"brand_ids": [w.brand_a.id]}),
        ("spec", {"spec": ["trap_type:s_trap"]}, {"spec": ["trap_type:s_trap"]}),
        ("customer_and_spec", {"customer": [w.c1.id], "spec": ["trap_type:p_trap"]},
         {"customer_ids": [w.c1.id], "spec": ["trap_type:p_trap"]}),
    ]


@pytest.mark.parametrize("basis", [b for b in KEYS if b not in NO_SPEC])
@pytest.mark.parametrize("case", ["none", "customer", "brand", "spec", "customer_and_spec"])
def test_slice4_tally_the_screen_total_equals_the_report_ask_total(client, db, basis, case) -> None:
    """Slice 4 / plan 3b tally: for one seeded world, screen grand total == `GET /report-ask` total for the same
    basis, period and filters (customer, brand, spec)."""
    w = _world(db)
    _label, screen, route = next(c for c in _cases(w) if c[0] == case)
    expected = _ask_total(client, db, basis, **route)
    got = _grand(_run(client, KEYS[basis], **screen))
    assert got == expected, (basis, case, got, expected)
    if case == "none":
        assert got[1] > 0, "an all-zero world would tally trivially"


@pytest.mark.parametrize("case", ["none", "customer"])
def test_slice4_tally_unpaid_screen_total_equals_the_report_ask_total(client, db, case) -> None:
    """Slice 4 / plan 3b tally on unpaid: 290 for everyone (150 + 80 + 60), 230 for customer c1."""
    w = _world(db)
    screen = {} if case == "none" else {"customer": [w.c1.id]}
    route = {} if case == "none" else {"customer_ids": [w.c1.id]}
    got = _grand(_run(client, KEYS["unpaid"], **screen))
    assert got == _ask_total(client, db, "unpaid", **route), case
    assert got == (0, D("290.00") if case == "none" else D("230.00")), got


# ================================================================ unpaid on screen: customer / sales agent / month only


def test_slice4_unpaid_offers_only_customer_sales_agent_and_month_to_group_by(client, db) -> None:
    """Slice 4 / AC-RU-8b on screen: the unpaid dimensions are customer, sales agent, month (and the `all` total)."""
    dims = {c["key"] for c in _meta(client, KEYS["unpaid"]).json()["catalog"] if c["tag"] == "dimension"}
    assert dims == {"customer", "sales_agent", "month", "all"}, dims


@pytest.mark.parametrize("rows", ["customer", "sales_agent", "month"])
def test_slice4_unpaid_groups_by_each_of_its_dimensions_and_the_rows_sum_to_the_total(client, db, rows) -> None:
    """Slice 4 / AC-RU-8b on screen: every grouping sums to 290 (the grand total)."""
    _world(db)
    resp = _run(client, KEYS["unpaid"], rows=rows)
    assert _grand(resp) == (0, D("290.00")), resp.text
    summary = resp.json()["layouts"]["summary"]
    cells = summary["row_totals"]
    assert sum(money(v.get("amount") or 0) for v in cells.values()) == D("290.00"), cells


def test_slice4_unpaid_cannot_group_by_product(client, db) -> None:
    """Slice 4 / AC-RU-8b on screen: a document has no product, so a product pivot row is 422."""
    _world(db)
    assert _run(client, KEYS["unpaid"], rows="product").status_code == 422
