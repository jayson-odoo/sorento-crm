"""Finance S1 - a billing document's sales order type, decided at ingest (#1309).

UAC: documentation/plans/finance/finance-billing-documents-27sep-acceptance-criteria.md, S1.
Plan 3.4, round 3: the DEALER and PROJECT TEAM blocks come from the sales order type (ruling
Q14), so each document stores a `demand_class`, decided by `classify_document`, the ladder
the weekly upload and the SO ingest already share:

  stored order type  the class of the SO its lowest-numbered linked line came from; for a
                     CN or DN with none, the class of the document it is against
  stated order type  none (a billing record carries no order type)
  agent              the document's OWN agent (ruling Q15)
  customer segment   by debtor code, within the company

  S1-1   the S0 fixture on Basis = Invoiced: IV + CS + DN - CN, net of tax, in MYR,
         the cancelled IV out, filed under the document date
  S1-4   the ladder, rung by rung, through the ingest route
  S1-9   nothing classifies: NULL, and no new warning in the contract's vocabulary
  S1-10  an IV whose own agent differs from its SO's: the SO's type, its own agent

Everything goes through the route with S0's harness (`env`), because the class is written by
the ingest and nowhere else.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from app.main import app  # noqa: F401  (first app import)

from app.models.finance import BillingDocument
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.sales_agent import SalesAgent
from app.services.company_scope import DEFAULT_COMPANY_ID

from .test_ingest_billing_documents import (  # noqa: F401  (`env` is a fixture)
    MARKER,
    _minimal,
    _outcomes,
    _record,
    env,
    load_fixture,
)


# ------------------------------------------------------------------ helpers
def _agent(env, code: str, demand_class=None) -> str:
    row = SalesAgent(sales_agent=code, demand_class=demand_class)
    env.db.add(row)
    env.db.flush()
    env.db.commit()
    return str(row.id)


def _order_line(env, *, demand_class, agent_id=None, ref=None) -> str:
    """A sales order of this class with one line; returns the line's `source_ref`."""
    ref = ref or f"SRT_DB:SO:{uuid.uuid4().hex[:8]}:1"
    order = SalesOrder(
        so_number=f"{MARKER}-SO-{uuid.uuid4().hex[:6]}",
        company_id=env.company_a,
        source_system="autocount",
        demand_class=demand_class,
        sales_agent_id=agent_id,
    )
    env.db.add(order)
    env.db.flush()
    env.db.add(
        SalesOrderLine(
            sales_order_id=order.id,
            product_id=env.product1_id,
            qty_ordered=1,
            source_ref=ref,
            company_id=env.company_a,
        )
    )
    env.db.flush()
    env.db.commit()
    return ref


def _lines(ref: str, *from_refs) -> list[dict]:
    """One line per `from_refs` entry (None = a line from no sales order), numbered 1..n."""
    return [
        {
            "source_ref": f"{ref}:{n}",
            "line_number": n,
            "product_code": "ZZFIN-P1",
            "quantity": 1,
            "unit_price": 10,
            "net_amount": 10,
            "tax_amount": 0,
            "line_total": 10,
            "from_line_ref": from_ref,
        }
        for n, from_ref in enumerate(from_refs, start=1)
    ]


def _doc(ref: str, *, from_refs=(None,), net=10, **extra) -> dict:
    lines = _lines(ref, *from_refs)
    total = Decimal(str(net))
    for line in lines:
        line["net_amount"] = line["line_total"] = line["unit_price"] = float(total / len(lines))
    return _minimal(
        ref,
        net_total=float(total),
        total=float(total),
        local_net_total=float(total),
        lines=lines,
        **extra,
    )


def _class_of(env, ref: str):
    return env.doc(ref).demand_class


def _fresh(prefix: str) -> str:
    return f"SRT_DB:{prefix}:{uuid.uuid4().hex[:8]}"


# ===================================================================== S1-4
class TestTheLadder:
    def test_an_invoice_takes_the_class_of_the_order_it_was_billed_from(self, env):
        retail = _order_line(env, demand_class="retail")
        project = _order_line(env, demand_class="project")
        iv_r, iv_p = _fresh("IV"), _fresh("IV")
        res = env.push([_doc(iv_r, from_refs=(retail,)), _doc(iv_p, from_refs=(project,))])
        assert set(_outcomes(res).values()) == {"created"}
        assert _class_of(env, iv_r) == "retail"
        assert _class_of(env, iv_p) == "project"

    def test_the_lowest_numbered_linked_line_decides(self, env):
        retail = _order_line(env, demand_class="retail")
        project = _order_line(env, demand_class="project")
        ref = _fresh("IV")
        res = env.push([_doc(ref, from_refs=(None, project, retail))])
        assert _outcomes(res)[ref] == "created"
        assert _class_of(env, ref) == "project"

    def test_a_cash_sale_with_no_order_takes_its_own_agents_class(self, env):
        _agent(env, "ZZFIN-PROJ", demand_class="project")
        ref = _fresh("CS")
        res = env.push([_doc(ref, document_type="cash_sale", agent_code="ZZFIN-PROJ")])
        assert _outcomes(res)[ref] == "created"
        assert _class_of(env, ref) == "project"

    def test_the_order_outranks_the_agent(self, env):
        _agent(env, "ZZFIN-PROJ", demand_class="project")
        retail = _order_line(env, demand_class="retail")
        ref = _fresh("IV")
        env.push([_doc(ref, from_refs=(retail,), agent_code="ZZFIN-PROJ")])
        assert _class_of(env, ref) == "retail"

    def test_a_credit_note_takes_the_class_of_the_invoice_it_is_against(self, env):
        """A CN reduces the block its invoice counted in, whatever its own agent says."""
        _agent(env, "ZZFIN-RET", demand_class="retail")
        project = _order_line(env, demand_class="project")
        iv, cn = _fresh("IV"), _fresh("CN")
        iv_no = f"{MARKER}-IV-{uuid.uuid4().hex[:6]}"
        env.push([_doc(iv, doc_no=iv_no, from_refs=(project,))])
        res = env.push(
            [
                _doc(
                    cn,
                    document_type="credit_note",
                    against_doc_no=iv_no,
                    agent_code="ZZFIN-RET",
                )
            ]
        )
        assert _outcomes(res)[cn] == "created"
        assert _class_of(env, cn) == "project"

    def test_the_customers_market_segment_is_the_last_rung(self, env):
        row = env.db.get(Customer, env.customer_id)
        row.market_segment_code = "PROJECTS"
        env.db.commit()
        ref = _fresh("CS")
        env.push([_doc(ref, document_type="cash_sale", customer_code="ZZFIN-C1")])
        assert _class_of(env, ref) == "project"

    def test_it_is_re_decided_on_the_next_push_once_the_order_has_landed(self, env):
        """An invoice pushed before its sales order falls to the agent, then takes the
        order's class the next time AutoCount pushes it."""
        _agent(env, "ZZFIN-RET2", demand_class="retail")
        so_ref = f"SRT_DB:SO:{uuid.uuid4().hex[:8]}:1"
        ref = _fresh("IV")
        record = _doc(ref, from_refs=(so_ref,), agent_code="ZZFIN-RET2")
        env.push([record])
        assert _class_of(env, ref) == "retail"

        _order_line(env, demand_class="project", ref=so_ref)
        res = env.push([record])
        assert _outcomes(res)[ref] == "updated"
        assert _class_of(env, ref) == "project"

    def test_a_replay_that_changes_nothing_writes_nothing(self, env):
        """S0-5 still holds with the class stored."""
        project = _order_line(env, demand_class="project")
        ref = _fresh("IV")
        record = _doc(ref, from_refs=(project,))
        env.push([record])
        before = env.dump()
        res = env.push([record])
        assert _outcomes(res)[ref] == "unchanged"
        assert env.dump() == before


# ===================================================================== S1-9
class TestNothingClassifies:
    def test_the_class_is_null_and_the_record_lands_without_a_new_warning(self, env):
        _agent(env, "ZZFIN-NOCLASS", demand_class=None)
        ref = _fresh("CS")
        res = env.push([_doc(ref, document_type="cash_sale", agent_code="ZZFIN-NOCLASS")])
        record = _record(res, ref)
        assert record["outcome"] == "created"
        # The contract 2.6 warning vocabulary is unchanged: no `unclassified_demand` here.
        assert "warnings" not in record or record["warnings"] == []
        assert _class_of(env, ref) is None


# ===================================================================== S1-10
class TestOwnAgent:
    def test_an_invoice_counts_in_its_orders_block_for_its_own_agent(self, env):
        seller = _agent(env, "ZZFIN-SO-AG", demand_class="retail")
        _agent(env, "ZZFIN-IV-AG", demand_class="project")
        retail = _order_line(env, demand_class="retail", agent_id=seller)
        ref = _fresh("IV")
        env.push([_doc(ref, from_refs=(retail,), agent_code="ZZFIN-IV-AG")])
        doc = env.doc(ref)
        assert doc.demand_class == "retail"
        agent = env.db.get(SalesAgent, doc.sales_agent_id)
        assert agent.sales_agent == "ZZFIN-IV-AG"


# ===================================================================== S1-1
def _invoiced_total(db, *, channel=(), period=("2026-01-01", "2026-12-31")):
    from app.schemas.report import ReportViewConfig
    from app.services.reports import engine
    from app.services.reports import registry as reg

    definition = reg.get("sales_yearly")
    view = ReportViewConfig.model_validate(
        {
            "params": {
                "date_basis": "order_date",
                "period": {"kind": "custom", "from": period[0], "to": period[1]},
                "company": [DEFAULT_COMPANY_ID],
                "channel": list(channel),
                "basis": ["invoiced"],
            },
            "detail": {"columns": [], "order": []},
            "pivot": {"rows": "year", "cols": "month_of_year", "measures": ["sales_value"]},
        }
    )
    return engine.run(
        db, definition, view.params, view, company_grants=frozenset({DEFAULT_COMPANY_ID})
    )


class TestTheFixtureOnTheInvoicedBasis:
    def test_iv_plus_cs_plus_dn_less_cn_net_of_tax_in_myr_cancelled_out(self, env):
        res = env.push_fixture()
        assert set(_outcomes(res).values()) == {"created"}
        result = _invoiced_total(env.db)
        # IV 1500 + CS 90 + DN 50 - CN 100 + the USD IV at its MYR 420; the cancelled
        # IV-2609/0002 (200) is nowhere. Net of tax: the fixture's tax is never added.
        summary = result.layouts.summary
        assert summary.grand_total["sales_value"] == "1960.00"
        assert summary.cells["2026"]["09"]["sales_value"] == "1960.00"
        assert result.row_count == 5
        refs = {r["document_no"] for r in result.layouts.detail.rows}
        assert "IV-2609/0002" not in refs

    def test_the_fixture_has_no_order_type_so_it_is_blank_and_in_neither_block(self, env):
        """The fixture's order and agent carry no class: every document is `(blank)`, in
        the total with the Channel filter cleared and in neither block with both ticked."""
        env.push_fixture()
        cleared = _invoiced_total(env.db)
        assert cleared.layouts.summary.grand_total["sales_value"] == "1960.00"
        ticked = _invoiced_total(env.db, channel=("dealer", "project"))
        assert ticked.layouts.summary.grand_total == {}
        assert all(
            d.demand_class is None
            for d in env.db.query(BillingDocument).filter(
                BillingDocument.company_id == env.company_a
            )
        )

