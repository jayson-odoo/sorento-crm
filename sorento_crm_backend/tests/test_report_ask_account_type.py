"""Phase 2 RED tests - the account type filter and split on the shared report ask (lane SALES-ACCOUNT-TYPE, PR 1).

`documentation/plans/sales/sales-account-type-acceptance-criteria.md` AT-1 to AT-16 and AT-18 (AT-17, the
master ingest fan-out, was dropped from PR 1; AT-19 is the MCP side, `sorento_crm_mcp/tests`).

Route: `GET /api/v1/order-management/report-ask`, new param `account_types`, new axis `group_by=account_type`.
A ledger's type is `customers.autocount_debtor_type`; its tag is `[A/C IV]` at the end of `customer_name`.
The number's type is derived per company (the type most ledgers carrying that tag hold).

Postgres only (`tests/_pg_fixture.py`), every row seeded here (CI's database has none). Fictional names and
codes only (`ZZT`).

Pinned where the contract is silent (flagged to the captain):
* the split's row names are the stored type words (`SORENTO`, ...) and `(blank)`;
* an unknown type NAME is refused the same way as an unknown number ("No account type <as asked>. ...").
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.models.company import RespondContactCompany
from app.models.product import Brand
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._mc_lookup_seed import product, seed_mocha, warehouse
from tests._pg_fixture import unique_code
from tests._report_ask_so_seed import seed_so_line
from tests._sales_report_do_seed import (  # noqa: F401  (client / db are fixtures)
    _as_contact,
    _contact,
    _link,
    client,
    db,
    line as do_line,
    money,
    seed_agent,
    seed_do,
)
from tests._sales_unified_seed import agent as shared_agent, cust, doc, line as doc_line
from tests.test_top_selling_report import _access

D = Decimal
ROUTE = "/api/v1/order-management/report-ask"
KEY = {"X-API-Key": "k"}
PERIOD = {"date_from": "2026-09-01", "date_to": "2026-09-30"}
JAN = {"date_from": "2026-01-01", "date_to": "2026-01-31"}
SEP = date(2026, 9, 10)
JAN15 = date(2026, 1, 15)
NOT_LOADED = "Account types are not loaded from AutoCount yet"
BASES = ["invoiced", "delivered", "ordered", "outstanding", "pending_delivery", "unpaid"]
DIALOG_BASES = ["delivered", "ordered", "outstanding", "pending_delivery", "unpaid"]


# ------------------------------------------------------------------------- helpers


def _staff(db, *, extra_company=None):
    """A grant holder with an office access type and both reveals (sales report + outstanding)."""
    from app.services.contact_field_reveal_service import set_granted_keys

    contact = _contact(db)
    _access(db, contact, "Sorento Office")
    set_granted_keys(db, contact.id, ["sales_orders.sales_report", "sales_orders.outstanding"], actor_id=None)
    if extra_company is not None:
        db.add(RespondContactCompany(id=str(uuid.uuid4()), respond_contact_id=contact.id, company_id=extra_company))
    db.commit()
    return contact


def _dealer(db, customer):
    from app.services.contact_field_reveal_service import set_granted_keys

    contact = _contact(db)
    set_granted_keys(db, contact.id, ["sales_orders.sales_report", "sales_orders.outstanding"], actor_id=None)
    _link(db, contact, customer)
    db.commit()
    return contact


def _ask(client, contact, *, period=PERIOD, basis="invoiced", **params):
    q = {**period, "basis": basis, **_as_contact(contact), **params}
    return client.get(ROUTE, params={k: v for k, v in q.items() if v is not None}, headers=KEY)


def _ok(client, contact, **params):
    resp = _ask(client, contact, **params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _amount(client, contact, **params):
    body = _ok(client, contact, **params)
    assert body["status"] == "ok", body
    return money(body["total"]["amount"])


def _code(resp):
    return resp.json().get("code")


def _ledger(db, tag=None, dtype=None, *, company_id=DEFAULT_COMPANY_ID, agent_row=None):
    """One customer ledger: `tag` is the roman numeral inside `[A/C ..]` (None = untagged)."""
    name = unique_code("ZZT CUSTOMER") + (f" [A/C {tag}]" if tag else "")
    return cust(db, debtor_type=dtype, name=name, company_id=company_id, agent_row=agent_row)


def _anchors(db, *, project=True, company_id=DEFAULT_COMPANY_ID):
    """The numbers 1, 3 and 4 as the AutoCount book holds them: two tagged ledgers each, typed
    SORENTO / CERAMIC / CABANA; plus (optionally) an untagged ledger typed PROJECT."""
    for tag, dtype in (("I", "SORENTO"), ("III", "CERAMIC"), ("IV", "CABANA")):
        _ledger(db, tag, dtype, company_id=company_id)
        _ledger(db, tag, dtype, company_id=company_id)
    if project:
        _ledger(db, None, "PROJECT", company_id=company_id)


def _sale(db, basis, customer, amount, *, prod=None, agent_row=None, when=SEP, kind="invoice",
          company_id=DEFAULT_COMPANY_ID):
    """One sale of `amount` RM on `basis` for `customer` (a credit note only on invoiced)."""
    amount = str(amount)
    prod = prod or product(db, company_id=company_id)
    if basis == "invoiced":
        return doc(db, kind, amount, when, customer=customer, agent_row=agent_row, company_id=company_id,
                   lines=[doc_line(prod=prod)])
    if basis == "unpaid":
        header = doc(db, "invoice", amount, when, customer=customer, agent_row=agent_row, company_id=company_id,
                     lines=[doc_line(prod=prod)])
        header.outstanding = D(amount)
        db.flush()
        return header
    if basis == "pending_delivery":
        wh = warehouse(db, company_id=company_id)
        return seed_do(db, customer_id=customer.id, order_date=when, source_book="db1", company_id=company_id,
                       lines=[do_line(prod.id, wh.id, 1, total=amount)])
    return seed_so_line(db, cust=customer, prod=prod, qty=1, total=amount, agent=agent_row, order_date=when,
                        delivered=1 if basis == "delivered" else 0, company_id=company_id)


def _brand(db, name, company_id=DEFAULT_COMPANY_ID):
    row = Brand(id=str(uuid.uuid4()), brand_code=unique_code("BR")[:50], brand_name=name, company_id=company_id)
    db.add(row)
    db.flush()
    return row


def _four_ledgers(db):
    """Typed CABANA [A/C IV], typed CERAMIC [A/C III], typed SORENTO [A/C I], and one with no type."""
    _anchors(db, project=False)
    return (
        _ledger(db, "IV", "CABANA"),
        _ledger(db, "III", "CERAMIC"),
        _ledger(db, "I", "SORENTO"),
        _ledger(db, None, None),
    )


# ================================================================ AT-1


def test_at_1_invoiced_account_4_counts_only_that_types_customers_and_a_credit_note_is_negative(client, db):
    cabana, ceramic, _sorento, untyped = _four_ledgers(db)
    _sale(db, "invoiced", cabana, "100.00")
    _sale(db, "invoiced", cabana, "30.00", kind="credit_note")
    _sale(db, "invoiced", ceramic, "50.00")
    _sale(db, "invoiced", untyped, "20.00")
    db.commit()
    assert _amount(client, _staff(db), account_types="4") == D("70.00")


# ================================================================ AT-2


@pytest.mark.parametrize("basis", DIALOG_BASES)
def test_at_2_the_same_filter_narrows_every_other_basis_to_that_types_customers(client, db, basis):
    cabana, ceramic, sorento, untyped = _four_ledgers(db)
    for ledger, amount in ((cabana, "100.00"), (ceramic, "200.00"), (untyped, "300.00"), (sorento, "400.00")):
        _sale(db, basis, ledger, amount)
    db.commit()
    contact = _staff(db)
    assert _amount(client, contact, basis=basis, account_types="4") == D("100.00")
    assert _amount(client, contact, basis=basis, account_types="3") == D("200.00")
    assert _amount(client, contact, basis=basis) == D("1000.00")


# ================================================================ AT-3


def test_at_3_the_filter_reads_the_type_not_the_ledgers_own_tag(client, db):
    _anchors(db)
    _ledger(db, "IV", "CABANA")  # CABANA is the majority of the [A/C IV] ledgers
    typed_no_tag = _ledger(db, None, "CABANA")
    tagged_wrong_type = _ledger(db, "IV", "SORENTO")
    _sale(db, "invoiced", typed_no_tag, "100.00")
    _sale(db, "invoiced", tagged_wrong_type, "10.00")
    db.commit()
    assert _amount(client, _staff(db), account_types="4") == D("100.00")


# ================================================================ AT-4


def test_at_4_the_agent_codes_suffix_never_decides_the_account(client, db):
    _anchors(db)
    agent_row = seed_agent(db, code=unique_code("ZZT AGENT") + " III")
    cabana = _ledger(db, None, "CABANA", agent_row=agent_row)
    _sale(db, "invoiced", cabana, "100.00", agent_row=agent_row)
    db.commit()
    contact = _staff(db)
    assert _amount(client, contact, account_types="4") == D("100.00")
    assert _amount(client, contact, account_types="3") == D("0.00")


# ================================================================ AT-5


@pytest.mark.parametrize("asked", ["4", "IV", "iv", "A/C IV", "a/c iv", "CABANA", "cabana"])
def test_at_5_every_spelling_of_the_account_gives_the_same_figure(client, db, asked):
    _anchors(db)
    _sale(db, "invoiced", _ledger(db, "IV", "CABANA"), "100.00")
    _sale(db, "invoiced", _ledger(db, "III", "CERAMIC"), "55.00")
    db.commit()
    assert _amount(client, _staff(db), account_types=asked) == D("100.00")


def test_at_5_a_comma_list_adds_the_accounts_up(client, db):
    _anchors(db)
    _sale(db, "invoiced", _ledger(db, "IV", "CABANA"), "100.00")
    _sale(db, "invoiced", _ledger(db, "III", "CERAMIC"), "55.00")
    db.commit()
    assert _amount(client, _staff(db), account_types="3,4") == D("155.00")


# ================================================================ AT-6


def test_at_6_one_stray_ledger_does_not_move_the_numbers_type(client, db):
    _anchors(db)  # two [A/C IV] ledgers typed CABANA
    _sale(db, "invoiced", _ledger(db, "IV", "SORENTO"), "10.00")  # the stray
    _sale(db, "invoiced", _ledger(db, None, "CABANA"), "100.00")
    db.commit()
    assert _amount(client, _staff(db), account_types="4") == D("100.00")


def test_at_6_a_made_up_type_on_the_tagged_ledgers_makes_the_number_mean_it(client, db):
    _ledger(db, "IV", "ZZT TYPE")
    _ledger(db, "IV", "ZZT TYPE")
    _sale(db, "invoiced", _ledger(db, None, "ZZT TYPE"), "70.00")
    _sale(db, "invoiced", _ledger(db, None, "CABANA"), "900.00")
    db.commit()
    contact = _staff(db)
    assert _amount(client, contact, account_types="4") == D("70.00")
    assert _amount(client, contact, account_types="ZZT TYPE") == D("70.00")


def test_at_6_a_tie_goes_to_the_first_type_by_name(client, db):
    _ledger(db, "IV", "ZZT B TYPE")
    _ledger(db, "IV", "ZZT A TYPE")
    _sale(db, "invoiced", _ledger(db, None, "ZZT A TYPE"), "40.00")
    _sale(db, "invoiced", _ledger(db, None, "ZZT B TYPE"), "500.00")
    db.commit()
    assert _amount(client, _staff(db), account_types="4") == D("40.00")


def test_at_6_each_company_maps_the_number_to_its_own_type(client, db):
    mocha = seed_mocha(db)
    _anchors(db, project=False)  # company A: 4 is CABANA
    _ledger(db, "IV", "ZZT TYPE B", company_id=mocha.id)
    _ledger(db, "IV", "ZZT TYPE B", company_id=mocha.id)
    _sale(db, "invoiced", _ledger(db, None, "CABANA"), "100.00")
    _sale(db, "invoiced", _ledger(db, None, "ZZT TYPE B", company_id=mocha.id), "7.00", company_id=mocha.id)
    _sale(db, "invoiced", _ledger(db, None, "CABANA", company_id=mocha.id), "1000.00", company_id=mocha.id)
    db.commit()
    contact = _staff(db, extra_company=mocha.id)
    assert _amount(client, contact, account_types="4") == D("107.00")


# ================================================================ AT-7


def test_at_7_the_echo_reads_the_account_as_asked_and_never_states_the_type(client, db):
    _anchors(db)
    _sale(db, "invoiced", _ledger(db, "IV", "CABANA"), "100.00")
    db.commit()
    resp = _ask(client, _staff(db), account_types="4")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert {"key": "account_type", "label": "Account type", "values": ["4"]} in body["filters"], body["filters"]
    assert "CABANA" not in resp.text.upper(), resp.text


def test_at_7_the_echo_trims_and_upper_cases_what_was_asked(client, db):
    _anchors(db)
    db.commit()
    body = _ok(client, _staff(db), account_types=" iv ")
    assert {"key": "account_type", "label": "Account type", "values": ["IV"]} in body["filters"], body["filters"]


# ================================================================ AT-8


@pytest.mark.parametrize("basis", BASES)
def test_at_8_the_split_is_one_row_per_stored_type_plus_blank_and_adds_up_to_the_total(client, db, basis):
    cabana, ceramic, sorento, untyped = _four_ledgers(db)
    for ledger, amount in ((cabana, "100.00"), (ceramic, "200.00"), (sorento, "400.00"), (untyped, "800.00")):
        _sale(db, basis, ledger, amount)
    db.commit()
    contact = _staff(db)
    total = _amount(client, contact, basis=basis)
    body = _ok(client, contact, basis=basis, group_by="account_type", top_n=20)
    assert body["status"] == "ok", body
    assert body["group_by"] == "account_type" and body["group_label"] == "Account type", body
    got = {r["name"]: money(r["amount"]) for r in body["rows"]}
    assert got == {"CABANA": D("100.00"), "CERAMIC": D("200.00"), "SORENTO": D("400.00"), "(blank)": D("800.00")}, body["rows"]
    assert sum(got.values()) == total == D("1500.00")


# ================================================================ AT-9


def test_at_9_the_account_filter_ands_with_the_brand_filter(client, db):
    _anchors(db)
    cabana_brand, other_brand = _brand(db, "CABANA"), _brand(db, "ZZT OTHER BRAND")
    on_3, on_4 = _ledger(db, "III", "CERAMIC"), _ledger(db, "IV", "CABANA")
    p_cab, p_other = product(db, company_id=DEFAULT_COMPANY_ID), product(db, company_id=DEFAULT_COMPANY_ID)
    p_cab.brand_id, p_other.brand_id = cabana_brand.id, other_brand.id
    db.flush()
    _sale(db, "invoiced", on_3, "100.00", prod=p_cab)
    _sale(db, "invoiced", on_3, "50.00", prod=p_other)
    _sale(db, "invoiced", on_4, "70.00", prod=p_cab)
    db.commit()
    assert _amount(client, _staff(db), account_types="3", brand_ids=[cabana_brand.id]) == D("100.00")


# ================================================================ AT-10


@pytest.mark.parametrize("params", [{"account_types": "4"}, {"group_by": "account_type", "top_n": 5}])
def test_at_10_nothing_loaded_is_refused_with_the_message_even_though_sales_exist(client, db, params):
    tagged_untyped = _ledger(db, "IV", None)
    _sale(db, "invoiced", tagged_untyped, "100.00")
    db.commit()
    body = _ok(client, _staff(db), **params)
    assert body["status"] == "refused" and body["message"] == NOT_LOADED, body
    assert body["rows"] == [], body


# ================================================================ AT-11


def test_at_11_an_unknown_number_lists_the_numbers_then_untagged_types(client, db):
    _anchors(db)  # numbers 1, 3, 4 and an untagged PROJECT
    db.commit()
    body = _ok(client, _staff(db), account_types="9")
    assert body["status"] == "refused" and body["rows"] == [], body
    assert body["message"] == "No account type 9. Account types: 1, 3, 4, PROJECT.", body["message"]


def test_at_11_a_number_that_exists_only_as_a_tag_on_an_untyped_ledger_is_unknown(client, db):
    _anchors(db)
    _ledger(db, "V", None)
    db.commit()
    body = _ok(client, _staff(db), account_types="5")
    assert body["status"] == "refused" and body["rows"] == [], body
    assert body["message"] == "No account type 5. Account types: 1, 3, 4, PROJECT.", body["message"]


# ================================================================ AT-12


@pytest.mark.parametrize("value", ["", "   "])
def test_at_12_an_empty_account_types_value_is_422_empty_filter(client, db, value):
    _anchors(db)
    db.commit()
    resp = _ask(client, _staff(db), account_types=value)
    assert resp.status_code == 422, resp.text
    assert _code(resp) == "empty_filter", resp.text


def test_at_12_more_than_50_values_is_422_too_many_values(client, db):
    _anchors(db)
    db.commit()
    resp = _ask(client, _staff(db), account_types=[f"ZZT{n}" for n in range(51)])
    assert resp.status_code == 422, resp.text
    assert _code(resp) == "too_many_values", resp.text


# ================================================================ AT-13


@pytest.mark.parametrize("params", [{"account_types": "4"}, {"group_by": "account_type", "top_n": 5}])
def test_at_13_a_customer_scoped_contact_is_refused_the_filter_and_the_split(client, db, params):
    _anchors(db)
    own = _ledger(db, "IV", "CABANA")
    _sale(db, "invoiced", own, "100.00")
    db.commit()
    resp = _ask(client, _dealer(db, own), **params)
    assert resp.status_code == 403, resp.text
    assert _code(resp) == "report_dimension_not_allowed", resp.text


# ================================================================ AT-14


def test_at_14_another_companys_types_and_numbers_are_neither_listed_nor_matched_nor_counted(client, db):
    mocha = seed_mocha(db)
    _anchors(db, project=False)  # company A: numbers 1, 3, 4
    _ledger(db, "V", "ZZT TYPE B", company_id=mocha.id)
    _ledger(db, "V", "ZZT TYPE B", company_id=mocha.id)
    mocha_four = _ledger(db, "IV", "CABANA", company_id=mocha.id)
    _sale(db, "invoiced", _ledger(db, "IV", "CABANA"), "100.00")
    _sale(db, "invoiced", mocha_four, "9999.00", company_id=mocha.id)
    _sale(db, "invoiced", _ledger(db, None, "ZZT TYPE B", company_id=mocha.id), "8888.00", company_id=mocha.id)
    db.commit()
    contact = _staff(db)  # company A only
    for asked in ("5", "ZZT TYPE B"):
        body = _ok(client, contact, account_types=asked)
        assert body["status"] == "refused" and body["rows"] == [], body
        assert body["message"] == f"No account type {asked}. Account types: 1, 3, 4.", body["message"]
        assert "ZZT TYPE B" not in body["message"].split("No account type")[1].split(".")[1], body["message"]
    assert _amount(client, contact, account_types="4") == D("100.00")
    split = _ok(client, contact, group_by="account_type", top_n=20)
    assert {r["name"] for r in split["rows"]} == {"CABANA"}, split["rows"]
    assert money(split["total"]["amount"]) == D("100.00"), split["total"]


# ================================================================ AT-15


def test_at_15_the_chat_dataset_does_not_take_account_types(client, db):
    from tests.test_report_ask_chat_route import _ask as chat_ask, _staff as chat_staff

    resp = chat_ask(client, chat_staff(db), group_by="topic", top_n=5, account_types="4")
    assert resp.status_code == 422 and _code(resp) == "unknown_param", resp.text
    assert resp.json()["detail"] == "account_types", resp.text


# ================================================================ AT-16


def test_at_16_the_tie_out_against_the_autocount_report_figures_to_the_cent(client, db):
    codes = [seed_agent(db, code=unique_code("ZZT AGENT")) for _ in range(3)]
    a1, a2, a3 = codes
    noise_agent = seed_agent(db, code=unique_code("ZZT NOISE"))
    brand_cab, brand_cer = _brand(db, "CABANA"), _brand(db, "CERAMIC")
    plain = product(db, company_id=DEFAULT_COMPANY_ID)
    p_cab, p_cer = product(db, company_id=DEFAULT_COMPANY_ID), product(db, company_id=DEFAULT_COMPANY_ID)
    p_cab.brand_id, p_cer.brand_id = brand_cab.id, brand_cer.id
    db.flush()
    _anchors(db, project=False)
    l_one = _ledger(db, "I", "SORENTO")
    l_one_untagged = _ledger(db, None, "SORENTO")
    l_three = _ledger(db, "III", "CERAMIC")
    l_four = _ledger(db, "IV", "CABANA")

    def inv(ledger, net, agent_row, lines=None):
        doc(db, "invoice", net, JAN15, customer=ledger, agent_row=agent_row,
            lines=lines or [doc_line(prod=plain)])

    inv(l_one, "281810.77", a1)
    inv(l_one_untagged, "393.00", a1)
    inv(l_three, "27717.93", a1, [doc_line(prod=p_cer)])
    # the 287,765.66 document holds a CABANA brand line and a CERAMIC brand line
    inv(l_three, "287765.66", a2, [doc_line(prod=p_cab, net="76877.71"), doc_line(prod=p_cer, net="210887.95")])
    inv(l_four, "6561.00", a1, [doc_line(prod=p_cab)])
    inv(l_four, "89855.80", a3, [doc_line(prod=p_cab)])
    inv(l_one, "1.00", noise_agent)  # another agent's sale: outside the ask
    db.commit()

    contact = _staff(db)
    mine = {"period": JAN, "sales_agent_ids": [a.id for a in codes]}
    assert _amount(client, contact, account_types="1", **mine) == D("282203.77")
    assert _amount(client, contact, account_types="3", **mine) == D("315483.59")
    assert _amount(client, contact, account_types="4", **mine) == D("96416.80")
    assert _amount(client, contact, **mine) == D("694104.16")

    split = _ok(client, contact, group_by="account_type", top_n=10, **mine)
    got = {r["name"]: money(r["amount"]) for r in split["rows"]}
    assert got == {"SORENTO": D("282203.77"), "CERAMIC": D("315483.59"), "CABANA": D("96416.80")}, split["rows"]
    assert sum(got.values()) == D("694104.16")

    assert _amount(client, contact, account_types="3", brand_ids=[brand_cab.id], **mine) == D("76877.71")
    assert _amount(client, contact, account_types="3", **mine) == D("315483.59")


# ================================================================ AT-18


SIX_KEYS = ["sales_invoiced_ask", "sales_order_lines_ask_delivered", "sales_order_lines_ask_ordered",
            "sales_order_lines_ask_outstanding", "delivery_order_lines_pending", "unpaid_documents"]


def _meta_param(client, key, name):
    resp = client.get(f"/api/v1/reports/{key}")
    assert resp.status_code == 200, resp.text
    found = [p for p in resp.json()["params"] if p["key"] == name]
    return found[0] if found else None


def test_at_18_the_six_sales_and_outstanding_definitions_show_the_param_and_the_column():
    from app.main import app  # noqa: F401  (import order)
    from app.services.reports.definitions.sales_and_outstanding import DEFINITIONS

    assert len(DEFINITIONS) == 6
    for definition in DEFINITIONS:
        params = {p.key: p for p in definition.params if hasattr(p, "key")}
        assert "account_type" in params, (definition.key, sorted(params))
        assert params["account_type"].hidden is False, definition.key
        assert params["account_type"].label == "Account type", definition.key
        for dataset in definition.datasets():
            col = dataset.column("account_type")
            assert col is not None, (definition.key, dataset)
            assert col.hidden is False, (definition.key, col)
            assert col.label == "Account type", (definition.key, col)


@pytest.mark.parametrize("key", SIX_KEYS)
def test_at_18_the_reports_metadata_lists_the_param_labelled_account_type(client, db, key):
    param = _meta_param(client, key, "account_type")
    assert param is not None, f"{key} metadata has no account_type param"
    assert param["label"] == "Account type", param


def test_at_18_the_options_are_the_stored_types_of_the_callers_company_only(client, db):
    mocha = seed_mocha(db)
    _anchors(db, project=False)
    _ledger(db, "V", "ZZT TYPE B", company_id=mocha.id)
    db.commit()
    param = _meta_param(client, "sales_invoiced_ask", "account_type")
    assert param is not None, "no account_type param in the metadata"
    assert {o["value"] for o in param["options"]} == {"SORENTO", "CERAMIC", "CABANA"}, param["options"]


def test_at_18_running_the_definition_with_account_type_equals_the_routes_account_types(client, db):
    _anchors(db)
    _sale(db, "invoiced", _ledger(db, "IV", "CABANA"), "100.00")
    _sale(db, "invoiced", _ledger(db, "III", "CERAMIC"), "55.00")
    db.commit()
    params = {"date_basis": "order_date", "period": {"kind": "custom", "from": "2026-09-01", "to": "2026-09-30"},
              "account_type": ["CABANA"]}
    body = {"params": params,
            "view": {"params": params, "detail": {"columns": [], "order": []},
                     "pivot": {"rows": "month", "cols": "all", "measures": ["qty", "amount"]}}}
    resp = client.post("/api/v1/reports/sales_invoiced_ask/run", json=body)
    assert resp.status_code == 200, resp.text
    grand = resp.json()["layouts"]["summary"]["grand_total"] or {}
    from_screen = money(grand.get("amount") or 0)
    from_route = _amount(client, _staff(db), account_types="CABANA")
    assert from_screen == from_route == D("100.00"), (from_screen, from_route)


def test_at_18_sales_by_debtor_type_keeps_its_visible_debtor_type_param():
    from app.main import app  # noqa: F401  (import order)
    from app.services.reports import registry as reg

    definition = reg.get("sales_by_debtor_type")
    param = next(p for p in definition.params if getattr(p, "key", None) == "debtor_type")
    assert param.label == "Debtor type" and param.hidden is False


def test_at_18_top_selling_items_still_reads_debtor_type():
    from app.main import app  # noqa: F401  (import order)
    from app.services.reports import registry as reg

    definition = reg.get("top_selling_items")
    labels = {col.label for ds in definition.datasets() for col in [ds.column("debtor_type")] if col is not None}
    assert labels == {"Debtor type"}, labels
