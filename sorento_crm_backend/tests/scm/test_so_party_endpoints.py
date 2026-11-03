"""OI-UX-FILTER-SNAPSHOT: wherever a sales order is named, its customer and project come too.

Each case seeds a sales order carrying `debtor_name` (the customer the order was issued under)
and `project_label`, reads one endpoint's service, and asserts BOTH fields come back. A
`response_model` drops an undeclared field silently, so the schema-backed shapes are asserted
at the schema as well. One case per area asserts nulls for an order nobody could name.
"""
from __future__ import annotations

import json
import uuid
from datetime import date

from app.models.order import SalesOrder
from app.models.procurement import PurchaseOrderLine
from app.services.scm import spo_conversion_service as svc
from tests._pg_fixture import pg_session
from tests.scm.conftest import requires_pg, scm_app  # noqa: F401
from tests.scm.test_spo_conversion import MARKER, World, _u
from tests.scm.test_summary_order_service import chain as summary_chain  # noqa: F401
from tests.scm.test_coverage_service import chain, db  # noqa: F401
from tests.scm.test_trajectory import db_world  # noqa: F401
from tests.test_sales_opportunities_s2 import api, world  # noqa: F401
from tests.scm.test_spo_planner_selection import _project_chain, _retail_demand

pytestmark = requires_pg

DEBTOR = f"{MARKER} Debtor Sdn Bhd"
PROJECT = f"{MARKER} Tower Project"


def _name_order(so: SalesOrder, *, debtor=DEBTOR, project=PROJECT) -> None:
    so.debtor_name = f"  {debtor}  " if debtor else None
    so.project_label = project


def test_spo_planner_retail_coverage_carries_customer_and_project():
    with pg_session() as db:
        w = World(db)
        wh = w.warehouse("WH")
        line, so = _retail_demand(db, w, "P", wh, qty=5, required=date(2026, 9, 1))
        _name_order(so)
        db.flush()
        [row] = svc._retail_coverage(db, w.product("P").id)
        assert row["customer_name"] == DEBTOR
        assert row["project_label"] == PROJECT


def test_spo_planner_retail_coverage_without_party_is_null():
    with pg_session() as db:
        w = World(db)
        wh = w.warehouse("WH")
        line, so = _retail_demand(db, w, "P", wh, qty=5, required=date(2026, 9, 1))
        so.customer_id = None
        so.debtor_name = None
        so.project_label = None
        db.flush()
        [row] = svc._retail_coverage(db, w.product("P").id)
        assert row["customer_name"] is None
        assert row["project_label"] is None


def test_spo_planner_project_coverage_carries_customer_and_project():
    with pg_session() as db:
        w = World(db)
        row, pso = _project_chain(db, w, "P", qty=4, delivery=date(2026, 9, 1))
        core = SalesOrder(
            id=_u(), so_number=pso.autocount_doc_no, order_date=date(2026, 7, 1), status="open",
        )
        _name_order(core)
        db.add(core)
        db.flush()
        [out] = svc._project_coverage(db, w.product("P").id)
        assert out["document"] == pso.autocount_doc_no
        assert out["customer_name"] == DEBTOR
        assert out["project_label"] == PROJECT


def test_spo_planner_project_coverage_without_a_core_so_keeps_the_project_title():
    # Review round: before this lane `customer_name` held the inquiry's project title. An
    # order not synced from AutoCount yet (or named by its provisional ref) has no
    # `sales_orders` row to read, and must not lose that title to a pair of dashes: it is
    # the project, so it lands in `project_label`.
    from app.models.projects import Project

    with pg_session() as db:
        w = World(db)
        row, pso = _project_chain(db, w, "P", qty=4, delivery=date(2026, 9, 1))
        db.flush()
        title = db.query(Project.title).filter(Project.id == pso.project_id).scalar()
        [out] = svc._project_coverage(db, w.product("P").id)
        assert out["document"] == pso.autocount_doc_no
        assert out["customer_name"] is None
        assert out["project_label"] == title


def test_po_plan_covers_carry_customer_and_project():
    with pg_session() as db:
        w = World(db)
        wh = w.warehouse("WH")
        line, so = _retail_demand(db, w, "P", wh, qty=5, required=date(2026, 9, 1))
        _name_order(so)
        po = w.po("PLAN", w.supplier(), [("P", 5, 0)])
        po.source_system = svc.SOURCE_SYSTEM
        pol = db.query(PurchaseOrderLine).filter(PurchaseOrderLine.purchase_order_id == po.id).one()
        pol.source_ref = json.dumps({"pulls": [], "so_coverage": [{"so_line_id": str(line.id), "qty": 5}]})
        db.flush()
        [cover] = svc.plan_of(db, po.id)["covers"]
        assert cover["so_number"] == so.so_number
        assert cover["customer_name"] == DEBTOR
        assert cover["project_label"] == PROJECT
        # Review round: and it reaches the wire. `GET /purchase-orders/{id}` answers through
        # `response_model=PurchaseOrder`, whose `spo_plan.covers` is `SpoPlanCover`; a field
        # it does not declare is dropped silently.
        from app.schemas.scm_orders import SpoPlan

        [wire] = SpoPlan(**svc.plan_of(db, po.id)).model_dump()["covers"]
        assert wire["customer_name"] == DEBTOR
        assert wire["project_label"] == PROJECT


def test_coverage_undated_demand_carries_customer_and_project(db, chain):
    from tests.scm.test_coverage_service import _so_line
    from app.services.scm.coverage_service import CoverageService

    so = _so_line(db, chain["product"], chain["bin_a"], 40, None)
    _name_order(so)
    db.flush()
    cov = CoverageService(db).coverage_for(chain["product"].id, pool_id=chain["pool"].id)
    [undated] = cov.undated_demand
    assert undated.customer_name == DEBTOR
    assert undated.project_label == PROJECT
    from app.schemas.scm_coverage import CoverageUndatedDemandOut

    assert {"customer_name", "project_label"} <= set(CoverageUndatedDemandOut.model_fields)


def test_explain_net_committed_sos_carry_customer_and_project():
    from app.services.scm import reorder_run_service as run_svc

    with pg_session() as db:
        w = World(db)
        wh = w.warehouse("WH")
        _line, named = _retail_demand(db, w, "P", wh, qty=12, required=date(2026, 9, 1))
        _name_order(named)
        _line2, plain = _retail_demand(db, w, "P", wh, qty=5, required=date(2026, 9, 2))
        db.flush()
        body = run_svc.net_breakdown(db, w.product("P").id, wh.id)
        by_so = {r["so_number"]: r for r in body["committed_sos"]}
        assert by_so[named.so_number]["customer_name"] == DEBTOR
        assert by_so[named.so_number]["project_label"] == PROJECT
        assert by_so[plain.so_number]["customer_name"] == f"{MARKER} dealer"
        assert by_so[plain.so_number]["project_label"] is None


def test_demand_drill_lines_carry_customer_and_project(db, summary_chain):
    from app.schemas.scm_order_summary import OrderSummaryDemandDrillOut
    from app.services.scm import summary_order_service as order_svc
    from tests.scm.test_summary_order_service import _so

    f = summary_chain
    for order_type, key in (("project", "project_lines"), ("dealer", "retail_lines")):
        so, _cust = _so(db, f["product"], f["bin"], 10, order_type=order_type)
        _name_order(so)
        db.flush()
        out = order_svc.demand_drill(db, f["product"].product_code, kind=order_type)
        [line] = out[key]
        assert line["customer_name"] == DEBTOR
        assert line["project_label"] == PROJECT
        shaped = OrderSummaryDemandDrillOut(**out).model_dump()
        assert shaped[key][0]["customer_name"] == DEBTOR
        assert shaped[key][0]["project_label"] == PROJECT


def test_plan_exception_candidate_so_carries_customer_and_project():
    from types import SimpleNamespace

    from app.services.scm import plan_exception_service as pe_svc
    from app.services.scm.so_party import so_parties

    with pg_session() as db:
        w = World(db)
        wh = w.warehouse("WH")
        _line, so = _retail_demand(db, w, "P", wh, qty=3, required=date(2026, 9, 1))
        _name_order(so)
        db.flush()
        row = SimpleNamespace(
            id=_u(), exception_type="shortfall_earlier", product_id=None, warehouse_id=None,
            pool_code=None, purchase_order_id=None, po_expected_date=None, quantity=3,
            timeline_json={}, reading_json={}, status="open", decided_by=None,
            decided_at=None, decided_action=None, decision_reason=None,
            actions_json=[
                {"code": "relink_so", "rank": 1, "rationale": "x",
                 "candidate_so_number": so.so_number},
                {"code": "hold", "rank": 2, "rationale": "y", "candidate_so_number": None},
            ],
        )
        parties = so_parties(db, numbers=[so.so_number])
        out = pe_svc._row_out(row, {}, {}, {}, {}, parties)
        relink, hold = out["actions"]
        assert relink["customer_name"] == DEBTOR
        assert relink["project_label"] == PROJECT
        assert hold["customer_name"] is None


def test_po_dedicated_rows_carry_customer_and_project(scm_app):
    from fastapi.testclient import TestClient

    from app.services.scm import order_link_service
    from tests.scm import test_po_detail_dedication_route as d
    from tests.scm.test_channel_read_model import _core_so_line
    from tests.scm.test_m3_run import _mk_product

    app, db, _ = d._as(scm_app, "purchasing")
    bin_id = d._project_bin(db)
    pid = _mk_product(db, f"{d.MARKER}-{uuid.uuid4().hex[:6].upper()}")
    po_id, line_id, number = d._active_po(db, product_id=pid, warehouse_id=bin_id, qty=114)
    claiming, claiming_line = _core_so_line(
        db, product_id=pid, warehouse_id=bin_id, qty=114, demand_class="project",
    )
    _name_order(claiming)
    order_link_service.claim_placed_on_po(
        db, company_id=None, so_number=claiming.so_number, po_number=number,
        item_code=None, so_line_id=str(claiming_line.id), po_line_id=line_id,
        source=order_link_service.SOURCE_PO_UPLOAD,
    )
    db.flush()
    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/purchase-orders/{po_id}")
    assert res.status_code == 200, res.text
    block = next(b for b in res.json()["allocations"] if b["line_id"] == line_id)
    [dedicated] = block["dedicated_to"]
    assert dedicated["customer_name"] == DEBTOR
    assert dedicated["project_label"] == PROJECT
    from app.schemas.scm_orders import PurchaseOrderPlacement

    assert {"customer_name", "project_label"} <= set(PurchaseOrderPlacement.model_fields)


def test_po_line_book_so_carries_customer_and_project():
    from app.services.scm.purchase_order_service import PurchaseOrderService

    with pg_session() as db:
        w = World(db)
        wh = w.warehouse("WH")
        _line, so = _retail_demand(db, w, "P", wh, qty=3, required=date(2026, 9, 1))
        _name_order(so)
        doc = f"AED_TEST:{uuid.uuid4().hex[:10]}"
        so.source_ref = doc
        po = w.po("BK", w.supplier(), [("P", 5, 0), ("P", 1, 0)])
        linked, unlinked = po.lines
        linked.from_so_line_ref = f"{doc}:7"
        db.flush()
        svc_po = PurchaseOrderService(db)
        out = svc_po.serialize(po, None, book_so_by_ref=svc_po._book_so_for(po.lines))
        by_id = {ln["id"]: ln for ln in out["lines"]}
        hit = by_id[str(linked.id)]
        assert hit["book_so_number"] == so.so_number
        assert hit["book_so_customer_name"] == DEBTOR
        assert hit["book_so_project_label"] == PROJECT
        miss = by_id[str(unlinked.id)]
        assert miss["book_so_customer_name"] is None
        assert miss["book_so_project_label"] is None


def test_opportunity_detail_and_options_carry_customer_and_project(api):
    from tests import test_sales_opportunities_s2 as o

    client, db, company_id = api
    customer = o._customer(db, company_id, name="ZZT Master Cust")
    order = o._sales_order(db, company_id, customer.id, so_number="ZZT-SO-PARTY")
    _name_order(order)
    db.flush()
    created = o._create(client, customer_id=customer.id)

    options = client.get(f"{o.BASE}/{created['id']}/sales-order-options").json()["data"]
    [option] = [x for x in options if x["id"] == order.id]
    assert option["customer_name"] == DEBTOR
    assert option["project_label"] == PROJECT

    won = client.patch(
        f"{o.BASE}/{created['id']}",
        json={"status_id": o._status_id(db, "won"), "sales_order_id": order.id},
    )
    assert won.status_code == 200, won.text
    detail = client.get(f"{o.BASE}/{created['id']}").json()
    assert detail["sales_order_customer_name"] == DEBTOR
    assert detail["sales_order_project_label"] == PROJECT


def test_stock_detail_hold_declares_customer_and_project():
    """`response_model` drops undeclared fields. Holds are empty on the live book since
    BORROW-NO-HOLD, so the wire shape is pinned at the schema."""
    from app.schemas.project_board import StockDetailHold

    hold = StockDetailHold(
        so_number="SO1", customer_name=DEBTOR, project_label=PROJECT, qty="3"
    ).model_dump()
    assert hold["customer_name"] == DEBTOR
    assert hold["project_label"] == PROJECT


def test_donor_debt_and_lent_to_orders_are_named_in_a_planning_payload():
    from app.schemas import project_board as board
    from app.schemas import project_supply as supply
    from app.services.scm.so_party_payload import attach_donor_parties

    with pg_session() as db:
        w = World(db)
        wh = w.warehouse("WH")
        _line, so = _retail_demand(db, w, "P", wh, qty=3, required=date(2026, 9, 1))
        _name_order(so)
        db.flush()
        payload = {
            "rows": [{
                "sources": [{"donor_so_number": so.so_number}, {"donor_so_number": None}],
                "options": [{"debt_so_number": so.so_number, "debt_month": "2026-09"}],
                "lent_to": [{"qty": "3", "so_number": so.so_number, "line_no": 1}],
                "unknown": [{"donor_so_number": f"{MARKER}-NOPE"}],
            }]
        }
        out = attach_donor_parties(db, payload)
        row = out["rows"][0]
        assert row["sources"][0]["donor_customer_name"] == DEBTOR
        assert row["sources"][0]["donor_project_label"] == PROJECT
        assert "donor_customer_name" not in row["sources"][1]
        assert row["options"][0]["debt_customer_name"] == DEBTOR
        assert row["options"][0]["debt_project_label"] == PROJECT
        assert row["lent_to"][0]["customer_name"] == DEBTOR
        assert row["lent_to"][0]["project_label"] == PROJECT
        assert row["unknown"][0]["donor_customer_name"] is None
        # The input is left as it was: a frozen decision's JSON must not pick up the keys.
        assert "donor_customer_name" not in payload["rows"][0]["sources"][0]

    # `response_model` drops undeclared fields: every carrier declares the new ones.
    for model in (board.BoardSource, board.BoardDecisionBorrow, board.BorrowCandidate,
                  supply.SupplyComponent, supply.BorrowCandidate):
        assert {"donor_customer_name", "donor_project_label"} <= set(model.model_fields), model
    for model in (board.BoardLadderOption, supply.SupplyLadderOption):
        assert {"debt_customer_name", "debt_project_label"} <= set(model.model_fields), model
    assert {"customer_name", "project_label"} <= set(board.BoardLineLending.model_fields)


def test_trend_customer_orders_carry_customer_and_project(db_world):
    from sqlalchemy import text

    from tests.scm.test_trajectory import _orders

    first = db_world["vivo_orders"][0]
    db_world["db"].execute(text(
        "UPDATE sales_orders SET debtor_name = :d, project_label = :p WHERE so_number = :n"
    ), {"d": DEBTOR, "p": PROJECT, "n": first})
    db_world["db"].flush()
    out = _orders(db_world, db_world["customer_id"])
    by_so = {l["so_number"]: l for l in out["lines"]}
    assert by_so[first]["customer_name"] == DEBTOR
    assert by_so[first]["project_label"] == PROJECT
    other = by_so[db_world["vivo_orders"][1]]
    assert other["project_label"] is None


def test_spo_document_so_covered_carries_customer_and_project(scm_app):
    from tests.scm import test_spo_allocation_documents as d

    client, db = d._client(scm_app)
    chain = d._chain(db)
    product = d._product(db, chain)
    warehouse = d._warehouse(db)
    supplier = d._supplier(db)
    po, po_line = d._spo_line(db, product=product, supplier=supplier)
    doc = d.unique_code("SPO-PARTY")
    allocation = d._line(
        db, spo_number=doc, line_no=1, product=product, warehouse=warehouse, allocated=30,
    )
    allocation.po_line_id = po_line.id
    db.flush()
    so, _customer, so_line = d._retail_sales_order(db, product=product, warehouse=warehouse, qty="20")
    _name_order(so)
    d._cover(db, po_line, so_line, 20.0)

    r = client.get(f"{d.DOCUMENTS_URL}/{doc}")
    assert r.status_code == 200, r.text
    [covered] = r.json()["lines"][0]["so_covered"]
    assert covered["customer_name"] == DEBTOR
    assert covered["project_label"] == PROJECT
