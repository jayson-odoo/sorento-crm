"""BL-2 - a plan with a statement of its own never falls back to the supplier's.

`container_request_service._statement` chose the legacy supplier-wide read on EMPTY
HOLDINGS rather than on ABSENT ROWS. A plan whose upload wrote 115 stamped rows that bound
to none of our products therefore dropped into the branch written for plans that predate
migration 454, and showed another upload's figures under its own name - the ROYAL MIRROR
shape from the other direction. The proforma leg was worse: an all-unmatched proforma plan
fell back to the supplier's STOCK LIST, a different document answering a different question.

The fix keys both legs on `plan_statement.has_stock_rows` / `has_invoices`, the row-existence
question `supplier_code_alias_service` already asked of the unknown-codes queue.

TEST-FIRST: the keying does not exist when this file is written, and each test fails by
reading the other statement's number rather than by any error.
"""
from __future__ import annotations

from app.models.scm import ProformaInvoiceLine
from app.services.scm import container_request_service as build_svc
from tests._pg_fixture import pg_session
from tests.scm.conftest import requires_pg
from tests.scm.test_plan_owned_statement import World, _retail_need, _row

pytestmark = requires_pg


def test_a_stock_plan_whose_rows_matched_nothing_reads_no_holdings():
    """115 stamped rows, none bound: the plan HAS a statement, and it holds nothing of ours.

    The old rule read "no holdings" as "no statement" and fell through to the supplier-wide
    snapshot, so the plan showed another upload's figures under its own name.
    """
    with pg_session() as db:
        w = World(db)
        plan = w.plan("stock_list")
        w.stock_row(
            "A", packed=1, plan_id=str(plan.id), item_code=f"ZZPO-UNKNOWN-{w.tag}", bound=False
        )
        # What the plan must NOT read: the supplier-wide snapshot, and a product that is only
        # in it. `A` is ours through the sourcing link, so it stays a candidate either way.
        w.link("A")
        w.stock_row("A", packed=500, plan_id=None)
        w.stock_row("STRANGER", packed=500, plan_id=None)
        for key in ("A", "STRANGER"):
            _retail_need(db, w, key, 10)

        out = build_svc.build(db, supplier_id=str(w.supplier.id), plan=plan)

        row = _row(out, w.code("A"))
        assert row["holding_source"] == "none"
        assert row["holding_qty"] is None
        assert row["qty_packed"] == 0.0
        # The universe is links, aliases and drivers only: a product known ONLY to the
        # snapshot this plan does not read has no business on its grid.
        assert w.code("STRANGER") not in {r["item_code"] for r in out["rows"]}


def test_a_proforma_plan_whose_lines_matched_nothing_never_falls_back_to_a_stock_list():
    """The worse half: an all-unmatched proforma plan read the supplier's STOCK LIST.

    Two different documents answering two different questions - what they promised for one
    container, and what sits in their warehouse today.
    """
    with pg_session() as db:
        w = World(db)
        plan = w.plan("proforma")
        invoice = w.invoice([("A", 60)], plan_id=str(plan.id), block=1)
        line = (
            db.query(ProformaInvoiceLine)
            .filter(ProformaInvoiceLine.invoice_id == invoice.id)
            .one()
        )
        line.product_id = None
        line.item_code = f"ZZPO-UNKNOWN-{w.tag}"
        db.flush()
        w.link("A")
        w.stock_row("A", packed=500, plan_id=None)
        _retail_need(db, w, "A", 10)

        out = build_svc.build(db, supplier_id=str(w.supplier.id), plan=plan)

        row = _row(out, w.code("A"))
        assert row["holding_source"] == "none"
        assert row["holding_qty"] is None
        assert row["qty_packed"] == 0.0

