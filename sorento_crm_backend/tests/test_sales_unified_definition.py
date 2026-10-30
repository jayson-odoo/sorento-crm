"""SALES-UNIFIED S2/S3: the one invoiced definition, the sales type chain, set apart, and the
Sales by debtor type blocks (AC-7 to AC-14, AC-17, AC-19).

Engine level, over the `billing_documents` dataset through definition `sales_by_debtor_type`
(contract sections 2 to 4). Postgres only, every row seeded here.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.main import app  # noqa: F401  (import order)
from app.models.access import MarketSegment
from app.models.base import set_company_scope
from app.models.company import Company
from app.models.sales import SetApartCustomer
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._mc_lookup_seed import MOCHA_ID, seed_mocha
from tests._pg_fixture import blank_session, unique_code
from tests._sales_unified_seed import (
    ALL_TYPES, D, JAN, SALES_TYPE_LABELS, agent, by_agent, by_type, cust, delivery, doc, grand,
    line, run, six, so,
)

JAN15 = date(2026, 1, 15)
DEALER, PROJECT = SALES_TYPE_LABELS["dealer"], SALES_TYPE_LABELS["project"]
SET_APART, MIXED = SALES_TYPE_LABELS["set_apart"], SALES_TYPE_LABELS["mixed"]
NOT_SET, NO_SO = SALES_TYPE_LABELS["type_not_set"], SALES_TYPE_LABELS["no_sales_order"]


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, frozenset({DEFAULT_COMPANY_ID}))
        yield s


def _dealer_invoice(db, net="1000.00", when=JAN15, customer=None, **kw):
    """An invoice whose line is resolved onto a `retail` SO line."""
    header, (so_line,) = so(db, demand_class="retail", customer=customer)
    return doc(db, "invoice", net, when, customer=customer,
               lines=[line(so_line=so_line)], **kw)


# ------------------------------------------------------------------------------ AC-7


def _seed_ac7_month(db):
    c = cust(db)
    a = agent(db)
    doc(db, "invoice", "1000.00", JAN15, customer=c, agent_row=a)
    doc(db, "cash_sale", "200.00", JAN15, customer=c, agent_row=a)
    doc(db, "debit_note", "14.26", JAN15, customer=c, agent_row=a)
    doc(db, "credit_note", "300.00", JAN15, customer=c, agent_row=a)
    doc(db, "invoice", "5000.00", JAN15, customer=c, agent_row=a, status="cancelled")
    doc(db, "invoice", "1000.00", JAN15, customer=c, agent_row=a, tax="60.00")


def test_ac_7_sales_is_iv_plus_cs_plus_dn_minus_cn_net_of_tax_cancelled_out(db):
    _seed_ac7_month(db)
    result = run(db, "sales_by_debtor_type")
    assert result.layouts.summary.grand_total["sales_value"] == "1914.26"


def test_ac_7_every_invoiced_dataset_returns_the_same_figure(db):
    from app.schemas.report import ReportViewConfig
    from app.services.reports import engine
    from tests._sales_unified_seed import definition_of

    _seed_ac7_month(db)
    definition = definition_of("sales_yearly")

    view = ReportViewConfig.model_validate({
        "params": {"date_basis": "order_date", "period": JAN, "company": [DEFAULT_COMPANY_ID],
                   "basis": ["invoiced"], "channel": ALL_TYPES},
        "detail": {"columns": [], "order": []},
        "pivot": {"rows": "year", "cols": "month_of_year", "measures": ["sales_value"]},
    })
    result = engine.run(db, definition, view.params, view,
                        company_grants=frozenset({DEFAULT_COMPANY_ID}))
    assert result.layouts.summary.grand_total["sales_value"] == "1914.26"


# ------------------------------------------------------------------------------ AC-8


def test_ac_8_a_document_filed_on_31_jan_counts_in_january_and_1_feb_in_february(db):
    doc(db, "invoice", "100.00", date(2026, 1, 31))
    doc(db, "invoice", "40.00", date(2026, 2, 1))
    jan = run(db, "sales_by_debtor_type", period={"kind": "custom", "from": "2026-01-01", "to": "2026-01-31"})
    feb = run(db, "sales_by_debtor_type", period={"kind": "custom", "from": "2026-02-01", "to": "2026-02-28"})
    assert grand(jan) == D("100.00")
    assert grand(feb) == D("40.00")


# ------------------------------------------------------------------------------ AC-9


def test_ac_9_document_setting_credits_the_documents_agent_customer_setting_the_customers(db):
    doc_agent, cust_agent = agent(db, unique_code("ZZTDOC")), agent(db, unique_code("ZZTCUS"))
    customer = cust(db, agent_row=cust_agent)
    doc(db, "invoice", "100.00", JAN15, customer=customer, agent_row=doc_agent)

    assert by_agent(db) == {doc_agent.sales_agent: D("100.00")}

    company = db.get(Company, DEFAULT_COMPANY_ID)
    company.sales_agent_source = "customer"
    db.flush()
    assert by_agent(db) == {cust_agent.sales_agent: D("100.00")}


def test_ac_9_document_setting_shows_an_unresolved_code_as_sent_and_no_agent_as_blank(db):
    doc(db, "invoice", "30.00", JAN15, agent_code="ZZT-GONE")
    doc(db, "invoice", "5.00", JAN15)
    assert by_agent(db) == {"ZZT-GONE": D("30.00"), "(blank)": D("5.00")}


# ------------------------------------------------------------------------------ AC-10


def test_ac_10_a_line_resolved_onto_a_retail_so_line_is_dealer(db):
    _dealer_invoice(db)
    assert by_type(db) == {DEALER: D("1000.00")}


def test_ac_10_a_line_transferred_from_a_do_whose_so_is_project_is_project_team(db):
    _header, (so_line,) = so(db, demand_class="project")
    do = delivery(db, so_line=so_line)
    doc(db, "invoice", "700.00", JAN15, lines=[line(from_type="DO", from_no=do.order_number)])
    assert by_type(db) == {PROJECT: D("700.00")}


def test_ac_10_a_line_transferred_from_a_project_so_by_number_is_project_team(db):
    header, _ = so(db, demand_class="project")
    doc(db, "invoice", "250.00", JAN15, lines=[line(from_type="SO", from_no=header.so_number)])
    assert by_type(db) == {PROJECT: D("250.00")}


def test_ac_10_a_do_delivers_its_so_by_its_lines_from_number_or_by_its_header(db):
    by_number, _ = so(db, demand_class="retail")
    by_header, _ = so(db, demand_class="project")
    do_a = delivery(db, from_so_no=by_number.so_number, from_type=None)
    do_b = delivery(db, header_so=by_header)
    doc(db, "invoice", "11.00", JAN15, lines=[line(from_type="DO", from_no=do_a.order_number)])
    doc(db, "invoice", "22.00", JAN15, lines=[line(from_type="DO", from_no=do_b.order_number)])
    assert by_type(db) == {DEALER: D("11.00"), PROJECT: D("22.00")}


def test_ac_10_a_deleted_do_is_not_followed(db):
    header, (so_line,) = so(db, demand_class="retail")
    do = delivery(db, so_line=so_line, deleted=True)
    doc(db, "invoice", "9.00", JAN15, lines=[line(from_type="DO", from_no=do.order_number)])
    assert by_type(db) == {NO_SO: D("9.00")}


def test_ac_10_an_so_of_another_company_with_the_same_number_is_not_traced(db):
    seed_mocha(db)
    header, _ = so(db, demand_class="project", company_id=MOCHA_ID)
    doc(db, "invoice", "9.00", JAN15, lines=[line(from_type="SO", from_no=header.so_number)])
    assert by_type(db) == {NO_SO: D("9.00")}


# ------------------------------------------------------------------------------ AC-11


def test_ac_11_a_credit_or_debit_note_with_no_traced_line_inherits_its_invoices_sales_type(db):
    invoice = _dealer_invoice(db, net="1000.00")
    doc(db, "credit_note", "300.00", JAN15, against=invoice)
    doc(db, "debit_note", "14.26", JAN15, against=invoice)
    assert by_type(db) == {DEALER: D("714.26")}


def test_ac_11_a_note_with_its_own_traced_line_keeps_its_own_type(db):
    invoice = _dealer_invoice(db, net="1000.00")
    _header, (project_line,) = so(db, demand_class="project")
    doc(db, "credit_note", "300.00", JAN15, against=invoice, lines=[line(so_line=project_line)])
    assert by_type(db) == {DEALER: D("1000.00"), PROJECT: D("-300.00")}


# ------------------------------------------------------------------------------ AC-12


def _seed_every_bucket(db):
    _dealer_invoice(db, net="1000.00")
    _header, (p_line,) = so(db, demand_class="project")
    doc(db, "invoice", "2000.00", JAN15, lines=[line(so_line=p_line)])
    doc(db, "cash_sale", "200.00", JAN15)
    _h, (r_line,) = so(db, demand_class="retail")
    _h2, (p2_line,) = so(db, demand_class="project")
    doc(db, "invoice", "80.00", JAN15, lines=[line(net="50.00", so_line=r_line), line(net="30.00", so_line=p2_line)])
    _h3, (blank_line,) = so(db, demand_class=None)
    doc(db, "invoice", "60.00", JAN15, lines=[line(so_line=blank_line)])
    set_apart_customer = cust(db)
    db.add(SetApartCustomer(company_id=DEFAULT_COMPANY_ID, customer_id=set_apart_customer.id,
                            from_month=date(2026, 1, 1), to_month=None))
    db.flush()
    _dealer_invoice(db, net="500.00", customer=set_apart_customer)


def test_ac_12_every_sale_lands_in_exactly_one_bucket_and_the_buckets_add_up(db):
    _seed_every_bucket(db)
    buckets = by_type(db)
    assert buckets == {
        DEALER: D("1000.00"), PROJECT: D("2000.00"), SET_APART: D("500.00"),
        MIXED: D("80.00"), NOT_SET: D("60.00"), NO_SO: D("200.00"),
    }
    assert sum(buckets.values()) == grand(run(db, "sales_by_debtor_type")) == D("3840.00")


def test_ac_12_an_so_with_some_untyped_lines_and_one_known_type_takes_the_known_type(db):
    _h, (known,) = so(db, demand_class="retail")
    _h2, (untyped,) = so(db, demand_class=None)
    doc(db, "invoice", "90.00", JAN15, lines=[line(net="60.00", so_line=known), line(net="30.00", so_line=untyped)])
    assert by_type(db) == {DEALER: D("90.00")}


# ------------------------------------------------------------------------------ AC-13


def test_ac_13_the_stored_class_the_agents_class_and_the_segment_never_decide_the_type(db):
    seg = unique_code("ZZTPRJ")[:40]
    db.add(MarketSegment(id=str(uuid.uuid4()), code=seg, name=seg, is_active=True))
    db.flush()
    project_agent = agent(db, demand_class="project")
    customer = cust(db)
    customer.market_segment_code = seg
    db.flush()
    doc(db, "invoice", "100.00", JAN15, customer=customer, agent_row=project_agent,
        demand_class="project")
    assert by_type(db) == {NO_SO: D("100.00")}


def test_ac_13_a_stored_project_class_does_not_move_an_invoice_traced_to_a_retail_so(db):
    _dealer_invoice(db, net="100.00", demand_class="project")
    assert by_type(db) == {DEALER: D("100.00")}


# ------------------------------------------------------------------------------ AC-14


def _set_apart(db, customer, start, end=None):
    db.add(SetApartCustomer(company_id=DEFAULT_COMPANY_ID, customer_id=customer.id,
                            from_month=start, to_month=end))
    db.flush()


def _by_type_and_month(db, period):
    result = run(db, "sales_by_debtor_type", rows="channel", cols="year_month", period=period)
    return {(row, col): D(cell["sales_value"])
            for row, cols in result.layouts.summary.cells.items() for col, cell in cols.items()}


def test_ac_14_a_set_apart_customer_goes_to_set_apart_only_in_the_months_the_row_covers(db):
    customer = cust(db)
    _set_apart(db, customer, date(2026, 1, 1), date(2026, 1, 1))
    _dealer_invoice(db, net="100.00", when=date(2026, 1, 31), customer=customer)
    _dealer_invoice(db, net="40.00", when=date(2026, 2, 1), customer=customer)
    other = cust(db)
    _dealer_invoice(db, net="7.00", when=date(2026, 1, 10), customer=other)
    cells = _by_type_and_month(db, {"kind": "custom", "from": "2026-01-01", "to": "2026-02-28"})
    assert cells == {
        (SET_APART, "2026-01"): D("100.00"),
        (DEALER, "2026-01"): D("7.00"),
        (DEALER, "2026-02"): D("40.00"),
    }


def test_ac_14_an_open_ended_row_covers_every_later_month_and_not_earlier_ones(db):
    customer = cust(db)
    _set_apart(db, customer, date(2026, 2, 1), None)
    _dealer_invoice(db, net="10.00", when=date(2026, 1, 31), customer=customer)
    _dealer_invoice(db, net="20.00", when=date(2026, 2, 1), customer=customer)
    _dealer_invoice(db, net="30.00", when=date(2026, 6, 1), customer=customer)
    cells = _by_type_and_month(db, {"kind": "custom", "from": "2026-01-01", "to": "2026-06-30"})
    assert cells == {
        (DEALER, "2026-01"): D("10.00"),
        (SET_APART, "2026-02"): D("20.00"),
        (SET_APART, "2026-06"): D("30.00"),
    }


def test_ac_14_set_apart_beats_the_so_type_even_for_an_untraced_cash_sale(db):
    customer = cust(db)
    _set_apart(db, customer, date(2026, 1, 1), None)
    doc(db, "cash_sale", "55.00", JAN15, customer=customer)
    assert by_type(db) == {SET_APART: D("55.00")}


def test_ac_14_a_set_apart_row_of_another_company_is_ignored(db):
    seed_mocha(db)
    customer = cust(db)
    db.add(SetApartCustomer(company_id=MOCHA_ID, customer_id=customer.id,
                            from_month=date(2026, 1, 1), to_month=None))
    db.flush()
    _dealer_invoice(db, net="10.00", customer=customer)
    assert by_type(db) == {DEALER: D("10.00")}


# ------------------------------------------------------------------------------ AC-17


def test_ac_17_one_block_per_ticked_type_agents_down_debtor_types_and_blank_across(db):
    a1, a2 = agent(db, unique_code("ZZTA1")), agent(db, unique_code("ZZTA2"))
    t1, t2 = cust(db, debtor_type="ZZTT1"), cust(db, debtor_type="ZZTT2")
    no_type = cust(db)
    _dealer_invoice(db, net="100.00", customer=t1, agent_row=a1)
    _dealer_invoice(db, net="50.00", customer=t2, agent_row=a2)
    _dealer_invoice(db, net="5.00", customer=no_type, agent_row=a1)
    doc(db, "cash_sale", "40.00", JAN15, customer=t1, agent_row=a2)

    result = run(db, "sales_by_debtor_type")
    blocks = result.layouts.blocks
    assert six([b.key for b in blocks]) == ALL_TYPES
    dealer = next(b for b in blocks if b.key == "dealer").summary
    assert sorted(dealer.row_values) == sorted([a1.sales_agent, a2.sales_agent])
    assert set(dealer.col_dim.values) == {"ZZTT1", "ZZTT2", "(blank)"}
    assert dealer.cells[a1.sales_agent]["ZZTT1"]["sales_value"] == "100.00"
    assert dealer.cells[a1.sales_agent]["(blank)"]["sales_value"] == "5.00"
    assert dealer.grand_total["sales_value"] == "155.00"
    no_so = next(b for b in blocks if b.key == "no_sales_order").summary
    assert no_so.grand_total["sales_value"] == "40.00"

    assert D(result.layouts.summary.grand_total["sales_value"]) == sum(
        D(b.summary.grand_total.get("sales_value", "0")) for b in blocks) == D("195.00")


def test_ac_17_unticking_a_type_drops_its_block_and_its_sales_from_the_total(db):
    _dealer_invoice(db, net="100.00")
    doc(db, "cash_sale", "40.00", JAN15)
    result = run(db, "sales_by_debtor_type", channel=["dealer", "no_sales_order"])
    assert [b.key for b in result.layouts.blocks] == ["dealer", "no_sales_order"]
    assert grand(result) == D("140.00")
    only = run(db, "sales_by_debtor_type", channel=["dealer"])
    assert grand(only) == D("100.00")


def test_ac_17_the_definition_offers_the_six_types_all_ticked_and_opens_on_the_summary(db):
    from tests._sales_unified_seed import definition_of

    definition = definition_of("sales_by_debtor_type")
    channel = next(p for p in definition.params if p.key == "channel")
    assert six(list(channel.options(db))) == list(SALES_TYPE_LABELS.items())
    assert six(list(channel.default)) == ALL_TYPES and channel.multi is True
    assert definition.title == "Sales by debtor type"
    assert definition.module_key == "sales" and definition.permission == "sales.reports.view"
    assert definition.opens_on == "summary"
    assert definition.workbook.sheet_per == "channel" and definition.workbook.month_sheets is True
    assert definition.workbook.report_title == "WEEKLY SALES BY DEBTOR TYPE BY SALES AGENT"


def test_ac_17_the_agent_and_debtor_type_filters_narrow_the_run(db):
    a1, a2 = agent(db, unique_code("ZZTA1")), agent(db, unique_code("ZZTA2"))
    t1, t2 = cust(db, debtor_type="ZZTT1"), cust(db, debtor_type="ZZTT2")
    _dealer_invoice(db, net="100.00", customer=t1, agent_row=a1)
    _dealer_invoice(db, net="50.00", customer=t2, agent_row=a2)
    assert grand(run(db, "sales_by_debtor_type", debtor_type=["ZZTT2"])) == D("50.00")
    assert grand(run(db, "sales_by_debtor_type", agent=[a1.id])) == D("100.00")


# ------------------------------------------------------------------------------ AC-19


def test_ac_19_mocha_takes_agents_from_the_customers_and_its_own_debtor_types(db):
    seed_mocha(db)
    db.get(Company, MOCHA_ID).sales_agent_source = "customer"
    db.flush()
    owner, ignored = agent(db, unique_code("ZZTM1")), agent(db, unique_code("ZZTM2"))
    account = cust(db, debtor_type="ACCOUNT I", agent_row=owner, company_id=MOCHA_ID)
    other = cust(db, debtor_type="ACCOUNT II", company_id=MOCHA_ID)
    doc(db, "invoice", "300.00", JAN15, customer=account, agent_row=ignored, company_id=MOCHA_ID)
    doc(db, "invoice", "20.00", JAN15, customer=other, agent_code="ZZT-DOCCODE", company_id=MOCHA_ID)
    sorento = _dealer_invoice(db, net="9999.00")
    assert sorento is not None

    result = run(db, "sales_by_debtor_type", grants=frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}),
                 company=[MOCHA_ID])
    summary = result.layouts.summary
    assert D(summary.grand_total["sales_value"]) == D("320.00")
    assert summary.cells[owner.sales_agent]["ACCOUNT I"]["sales_value"] == "300.00"
    assert ignored.sales_agent not in summary.row_values
    assert "ZZT-DOCCODE" not in summary.row_values
    assert summary.cells["(blank)"]["ACCOUNT II"]["sales_value"] == "20.00"
    assert set(summary.col_dim.values) == {"ACCOUNT I", "ACCOUNT II"}
