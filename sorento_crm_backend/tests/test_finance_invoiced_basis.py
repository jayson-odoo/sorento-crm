"""Finance S1 (#1309): Basis = Invoiced on the Yearly comparison, and the chatbot's seam.

UAC: documentation/plans/finance/finance-billing-documents-27sep-acceptance-criteria.md, S1.
Plan 3.4 (round 3): one report, two datasets. Basis = Invoiced reads
`finance.billing_documents` (IV + CS + DN - CN, `local_net_total`, posted only, by document
date), in the DEALER and PROJECT TEAM blocks by the stored `demand_class` through the SAME
channel label and filter the order bases use (ruling Q14), each document credited to its own
agent (Q15).

  S1-2   a CN counts in its own month, never its invoice's
  S1-3   Basis offers Delivered, Ordered, Invoiced; Delivered stays the default
  S1-4   the blocks come from `demand_class`; the Channel filter narrows them
  S1-5   the basis line
  S1-6   the chatbot's `GET /sales/analysis` answers basis=invoiced from the same dataset
  S1-7   `sales.reports.view` alone runs it; no finance slug is needed
  S1-9   an unclassified document is retail S1's `(blank)` row: last, in the cleared total
  kernel a detail column only the other basis holds is left out, an unknown one is 422

Postgres only, every row seeded here (CI's database holds none). Engine-level seeds write
`billing_documents` rows directly: the ingest's side of the class is in
`test_ingest_billing_documents_demand_class.py`.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.main import app  # noqa: F401  (import order: resolves the guards cycle)
from app.models.base import set_company_scope
from app.models.finance import BillingDocument
from app.models.sales_agent import SalesAgent
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._mc_lookup_seed import MOCHA_ID, seed_mocha
from tests._pg_fixture import blank_session, unique_code

KEY = "sales_yearly"
NOTE = (
    "Basis: Invoiced (invoices, cash sales and debit notes less credit notes, excluding tax), "
    "by document date, grouped by the sales order type."
)


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, frozenset({DEFAULT_COMPANY_ID}))
        yield s


@pytest.fixture
def definition():
    from app.services.reports import registry as reg

    return reg.get(KEY)


def _doc(
    db,
    *,
    net,
    when,
    document_type="invoice",
    demand_class="retail",
    status="posted",
    company_id=DEFAULT_COMPANY_ID,
    agent_id=None,
    doc_no=None,
):
    row = BillingDocument(
        id=str(uuid.uuid4()),
        company_id=company_id,
        document_type=document_type,
        doc_no=doc_no or unique_code("IV"),
        doc_date=when,
        status=status,
        net_total=Decimal(net),
        tax_total=Decimal("0"),
        total=Decimal(net),
        local_net_total=Decimal(net),
        demand_class=demand_class,
        sales_agent_id=agent_id,
        source_ref=f"SRT_DB:{uuid.uuid4().hex}",
    )
    db.add(row)
    db.flush()
    return row


def _params(**over):
    params = {
        "date_basis": "order_date",
        "period": {"kind": "custom", "from": "2024-01-01", "to": "2026-09-26"},
        "company": [DEFAULT_COMPANY_ID],
        "channel": ["dealer", "project"],
        "basis": ["invoiced"],
    }
    params.update(over)
    return params


def _view(rows="year", cols="month_of_year", measures=("sales_value",), columns=(), **params):
    from app.schemas.report import ReportViewConfig

    return ReportViewConfig.model_validate(
        {
            "params": _params(**params),
            "detail": {"columns": list(columns), "order": list(columns)},
            "pivot": {"rows": rows, "cols": cols, "measures": list(measures)},
        }
    )


def _run(db, definition, grants=frozenset({DEFAULT_COMPANY_ID}), **kw):
    from app.services.reports import engine

    view = _view(**kw)
    return engine.run(db, definition, view.params, view, company_grants=grants)


# ====================================================================== S1-2
def test_s1_2_a_credit_note_reduces_its_own_month_never_its_invoices(db, definition):
    _doc(db, net="500.00", when=date(2026, 1, 20))
    _doc(db, net="100.00", when=date(2026, 3, 2), document_type="credit_note")
    cells = _run(db, definition).layouts.summary.cells["2026"]
    assert cells["01"]["sales_value"] == "500.00"
    assert cells["03"]["sales_value"] == "-100.00"


def test_s1_1_every_type_signed_cancelled_out_by_document_date(db, definition):
    _doc(db, net="1000.00", when=date(2025, 6, 1))
    _doc(db, net="90.00", when=date(2025, 6, 2), document_type="cash_sale")
    _doc(db, net="50.00", when=date(2025, 6, 3), document_type="debit_note")
    _doc(db, net="100.00", when=date(2025, 6, 4), document_type="credit_note")
    _doc(db, net="777.00", when=date(2025, 6, 5), status="cancelled")
    summary = _run(db, definition).layouts.summary
    assert summary.cells["2025"]["06"]["sales_value"] == "1040.00"


# ====================================================================== S1-3
def test_s1_3_basis_offers_delivered_ordered_invoiced_and_delivered_is_the_default(
    db, definition
):
    basis = next(p for p in definition.params if p.key == "basis")
    assert list(basis.options(db)) == [
        ("delivered", "Delivered"),
        ("ordered", "Ordered"),
        ("invoiced", "Invoiced"),
    ]
    assert basis.default == ("delivered",)
    assert definition.default_view["params"]["basis"] == ["delivered"]


def test_s1_3_an_unknown_basis_is_still_422(db, definition):
    from app.services.error_handler import AppException

    with pytest.raises(AppException) as refused:
        _run(db, definition, basis=["shipped"])
    assert refused.value.status_code == 422


# ====================================================================== S1-4
def test_s1_4_the_blocks_are_the_sales_order_type(db, definition):
    _doc(db, net="300.00", when=date(2026, 2, 1), demand_class="retail")
    _doc(db, net="700.00", when=date(2026, 2, 1), demand_class="project")
    _doc(db, net="50.00", when=date(2026, 2, 9), demand_class="project",
         document_type="credit_note")
    result = _run(db, definition, rows="channel", cols="year")
    summary = result.layouts.summary
    assert summary.row_values == ["Dealer", "Project team"]
    assert summary.cells["Dealer"]["2026"]["sales_value"] == "300.00"
    assert summary.cells["Project team"]["2026"]["sales_value"] == "650.00"
    assert [b.title for b in result.layouts.blocks] == [
        "SORENTO - DEALER",
        "SORENTO - PROJECT TEAM",
    ]
    assert result.layouts.blocks[1].summary.grand_total["sales_value"] == "650.00"


def test_s1_4_the_channel_filter_narrows_to_one_block(db, definition):
    _doc(db, net="300.00", when=date(2026, 2, 1), demand_class="retail")
    _doc(db, net="700.00", when=date(2026, 2, 1), demand_class="project")
    dealer = _run(db, definition, channel=["dealer"])
    assert dealer.layouts.summary.grand_total["sales_value"] == "300.00"
    project = _run(db, definition, channel=["project"])
    assert project.layouts.summary.grand_total["sales_value"] == "700.00"


def test_s1_4_an_unknown_channel_is_422_on_invoiced_too(db, definition):
    from app.services.error_handler import AppException

    with pytest.raises(AppException) as refused:
        _run(db, definition, channel=["wholesale"])
    assert refused.value.status_code == 422


# ====================================================================== S1-5
def test_s1_5_the_basis_line(db, definition):
    assert _run(db, definition).note == NOTE


def test_s1_5_the_order_bases_keep_their_own_line(db, definition):
    assert _run(db, definition, basis=["delivered"]).note == (
        "Basis: Delivered (transferred to DO), by sales order date. Sales orders, not invoices."
    )


def test_s1_5_the_workbook_title_block_carries_the_basis_line(db, definition):
    from app.services.reports import engine

    _doc(db, net="10.00", when=date(2026, 1, 5))
    view = _view()
    data = engine.run_workbook(
        db, definition, view.params, view, company_grants=frozenset({DEFAULT_COMPANY_ID})
    )
    assert data.note == NOTE
    assert data.summary.grand_total["sales_value"] == "10.00"


# ====================================================================== S1-9
def test_s1_9_an_unclassified_document_is_the_blank_row_last_and_in_the_cleared_total(
    db, definition
):
    """Retail S1's own fallback (its AC-S1-4): `(blank)`, sorted last, in the total when the
    Channel filter is cleared, and in neither block when both are ticked."""
    _doc(db, net="10.00", when=date(2026, 1, 5), demand_class="retail")
    _doc(db, net="20.00", when=date(2026, 1, 5), demand_class="project")
    _doc(db, net="5.00", when=date(2026, 1, 5), demand_class=None)
    cleared = _run(db, definition, rows="channel", cols="year", channel=[]).layouts.summary
    assert cleared.row_values == ["Dealer", "Project team", "(blank)"]
    assert cleared.grand_total["sales_value"] == "35.00"
    ticked = _run(db, definition, rows="channel", cols="year").layouts.summary
    assert ticked.row_values == ["Dealer", "Project team"]
    assert ticked.grand_total["sales_value"] == "30.00"


def test_s1_9_the_cleared_total_equals_the_ungrouped_invoiced_sum(db, definition):
    import sqlalchemy as sa

    for net, cls, kind in (
        ("120.00", "retail", "invoice"),
        ("40.00", None, "cash_sale"),
        ("15.00", "project", "credit_note"),
        ("8.00", None, "debit_note"),
    ):
        _doc(db, net=net, when=date(2026, 4, 1), demand_class=cls, document_type=kind)
    ungrouped = db.execute(
        sa.select(
            sa.func.sum(
                sa.case(
                    (BillingDocument.document_type == "credit_note",
                     -BillingDocument.local_net_total),
                    else_=BillingDocument.local_net_total,
                )
            )
        ).where(
            BillingDocument.company_id == DEFAULT_COMPANY_ID,
            BillingDocument.status == "posted",
            BillingDocument.doc_date >= date(2024, 1, 1),
        )
    ).scalar()
    total = _run(db, definition, channel=[]).layouts.summary.grand_total["sales_value"]
    assert Decimal(total) == ungrouped == Decimal("153.00")


# ===================================================================== S1-10
def test_s1_10_the_agent_column_is_the_documents_own_agent(db, definition):
    agent = SalesAgent(sales_agent=unique_code("AGIV"))
    db.add(agent)
    db.flush()
    _doc(db, net="10.00", when=date(2026, 1, 5), agent_id=str(agent.id),
         doc_no="IV-OWN-AGENT")
    rows = _run(db, definition, columns=("document_no", "agent_code")).layouts.detail.rows
    assert rows == [{"document_no": "IV-OWN-AGENT", "agent_code": agent.sales_agent}]


# ================================================================ the kernel
def test_a_column_only_the_order_basis_holds_is_left_out_of_an_invoiced_run(db, definition):
    """A view saved on Delivered names `so_number` and `product_code`; on Invoiced they are
    not refused, they are not there."""
    _doc(db, net="10.00", when=date(2026, 1, 5), doc_no="IV-SAVED-VIEW")
    detail = _run(
        db, definition, columns=("so_number", "document_no", "product_code", "sales_value")
    ).layouts.detail
    assert [c.key for c in detail.columns] == ["document_no", "sales_value"]
    assert detail.rows == [{"document_no": "IV-SAVED-VIEW", "sales_value": "10.00"}]


def test_a_column_no_basis_holds_is_still_422(db, definition):
    from app.services.error_handler import AppException

    with pytest.raises(AppException) as refused:
        _run(db, definition, columns=("shoe_size",))
    assert refused.value.status_code == 422


def test_the_invoiced_detail_is_one_row_per_document_newest_first(db, definition):
    _doc(db, net="10.00", when=date(2026, 1, 5), doc_no="IV-OLD")
    _doc(db, net="7.00", when=date(2026, 2, 5), doc_no="CN-NEW", document_type="credit_note")
    rows = _run(
        db, definition, columns=("document_no", "document_date", "document_type", "sales_value")
    ).layouts.detail.rows
    assert rows == [
        {"document_no": "CN-NEW", "document_date": "2026-02-05",
         "document_type": "Credit note", "sales_value": "-7.00"},
        {"document_no": "IV-OLD", "document_date": "2026-01-05",
         "document_type": "Invoice", "sales_value": "10.00"},
    ]


def test_the_order_basis_is_untouched_by_billing_documents(db, definition):
    _doc(db, net="999.00", when=date(2026, 1, 5))
    result = _run(db, definition, basis=["delivered"])
    assert result.layouts.summary.grand_total == {}
    assert result.row_count == 0


def test_company_isolation_and_a_company_outside_the_grant_is_403(db, definition):
    from app.services.error_handler import AppException

    seed_mocha(db)
    _doc(db, net="10.00", when=date(2026, 1, 5))
    _doc(db, net="700.00", when=date(2026, 1, 5), company_id=MOCHA_ID)
    assert _run(db, definition).layouts.summary.grand_total["sales_value"] == "10.00"
    with pytest.raises(AppException) as refused:
        _run(db, definition, company=[MOCHA_ID])
    assert refused.value.status_code == 403
    both = frozenset({DEFAULT_COMPANY_ID, MOCHA_ID})
    mocha = _run(db, definition, grants=both, company=[MOCHA_ID])
    assert mocha.layouts.summary.grand_total["sales_value"] == "700.00"


def test_no_scope_is_no_rows_on_invoiced_too(db, definition):
    from app.models.base import UNSET

    _doc(db, net="10.00", when=date(2026, 1, 5))
    for grants in (UNSET, frozenset()):
        result = _run(db, definition, grants=grants, company=[])
        assert result.row_count == 0
        assert result.layouts.summary.grand_total == {}


# ================================================================ the routes
def test_s1_3_s1_7_the_meta_offers_invoiced_and_its_columns_to_a_sales_reports_holder():
    """S1-7: `sales.reports.view` alone; no `finance.billing_documents.view`."""
    from tests.test_sales_yearly_routes import BASE, _client, _user

    with blank_session() as s:
        set_company_scope(s, frozenset({DEFAULT_COMPANY_ID}))
        seed_mocha(s)
        principal = _user(s, DEFAULT_COMPANY_ID)
        with _client(s, principal, allow=("sales.reports.view",)) as client:
            meta = client.get(BASE).json()
    basis = next(p for p in meta["params"] if p["key"] == "basis")
    assert [o["value"] for o in basis["options"]] == ["delivered", "ordered", "invoiced"]
    keys = [c["key"] for c in meta["catalog"]]
    assert {"so_number", "document_no", "document_type", "sales_value"} <= set(keys)
    assert len(keys) == len(set(keys))


def test_s1_7_a_run_on_invoiced_needs_only_sales_reports_view():
    from tests.test_sales_yearly_routes import BASE, _body, _client, _user

    with blank_session() as s:
        set_company_scope(s, frozenset({DEFAULT_COMPANY_ID}))
        seed_mocha(s)
        _doc(s, net="42.00", when=date(2026, 3, 3))
        principal = _user(s, DEFAULT_COMPANY_ID)
        with _client(s, principal, allow=("sales.reports.view",)) as client:
            response = client.post(f"{BASE}/run", json=_body(basis=["invoiced"]))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["layouts"]["summary"]["grand_total"]["sales_value"] == "42.00"
    assert body["note"] == NOTE


def test_s1_7_an_export_view_on_invoiced_is_checked_as_the_run_checks_it(definition):
    """The export validates the view at the button: a column only the order basis holds is
    accepted on Invoiced, as the run accepts it; a column no basis holds is refused."""
    from app.services.error_handler import AppException
    from app.services.reports import engine

    engine.validate_view(definition, _view(columns=("so_number", "document_no")))
    engine.validate_view(definition, _view(measures=("sales_value",), basis=["delivered"]))
    with pytest.raises(AppException):
        engine.validate_view(definition, _view(columns=("shoe_size",)))
    with pytest.raises(AppException):
        # `ordered_value` is a measure of the order basis only: an Invoiced pivot cannot sum it.
        engine.validate_view(definition, _view(measures=("ordered_value",)))


# =============================================================== the chatbot
def test_s1_6_the_chatbot_answers_invoiced_from_the_same_dataset(monkeypatch):
    from tests import test_sales_analysis_route as sa_route

    monkeypatch.setattr(
        "app.services.storage_router.get_backend", lambda provider: sa_route._CdnBackend()
    )
    from app.services import queue_service

    monkeypatch.setattr(
        queue_service, "enqueue_job", lambda fn, *a, **k: type("J", (), {"id": "job"})()
    )
    with blank_session() as s:
        set_company_scope(s, None)
        seed_mocha(s)
        _doc(s, net="100.00", when=date(2026, 1, 10), demand_class="retail")
        _doc(s, net="30.00", when=date(2026, 1, 20), demand_class="retail",
             document_type="credit_note")
        _doc(s, net="999.00", when=date(2026, 1, 10), demand_class="project")
        contact = sa_route._contact(s)
        sa_route._patch_wait(monkeypatch, None)
        with sa_route._client(s, sa_route._actor(s), [DEFAULT_COMPANY_ID]) as client:
            body = client.get(
                sa_route.ROUTE, params=sa_route._q(contact, basis="invoiced")
            ).json()
    assert body["status"] in ("ready", "pending"), body
    assert body["channel"] == "Dealer"
    assert body["basis"] == (
        "Invoiced (invoices, cash sales and debit notes less credit notes, excluding tax)"
    )
    assert body["rows"][0]["label"] == "JAN"
    assert body["rows"][0]["values"][1] == "70.00"
    assert body["totals"]["total"] == "70.00"


def test_s1_6_the_parser_can_say_invoiced():
    from app.services.chatbot.head.parser import PARSE_OUTPUT_JSON_SCHEMA
    from app.services.chatbot_parser_prompt import SEMANTIC_PARSER_PROMPT

    props = PARSE_OUTPUT_JSON_SCHEMA["properties"]
    assert props["sales_basis"]["enum"] == ["ordered", "delivered", "invoiced", None]
    assert '"invoiced", "invoices", "billed" -> "invoiced"' in SEMANTIC_PARSER_PROMPT


def test_s1_6_the_fetch_lane_passes_invoiced_through():
    from app.services.chatbot.lanes.business import fetch

    assert "invoiced" in fetch.SALES_ANALYSIS_BASES
