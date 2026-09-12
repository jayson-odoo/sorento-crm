"""Slice A review round, R-S1 (`documentation/plans/scm/PLAN-scm-change-management-one
-engine.md`): `DocumentIngestService._capture_planning_diff_before` /
`_capture_planning_diff_after` (`app/services/document_ingest_service.py`, ~1105-1155)
build `outstanding_diff.Line` objects with `row_ref=str(row.id)` but no `line_id` - the
ESB/AutoCount ingest trigger therefore never gets the line-identity pairing Slice A's rule
5 gives the manual-edit and book-upload triggers, so a product swap arriving through
`document_ingest_service` still reads as a `closed` plus an unrelated `added` instead of one
`product_changed` row.

Smallest unit that reaches these two methods: constructed directly (no route, no full
`ingest()` batch, no parsed `DocumentPayload`) - `DocumentIngestService.__init__` needs only
`db` + `company_id` (see its own docstring: "same constructor... interchangeable"), and both
methods read only `header.id` and `payload.so_number` off their arguments, so a bare
`SimpleNamespace(so_number=...)` stands in for the payload. `tests/test_ingest_documents_v2
_hooks.py` builds the same service through the full route/spec machinery for a different
purpose and has pre-existing failures unrelated to this slice - not depended on here.

Postgres only (`tests/_pg_fixture.py`), every FK seeded here.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import text

from app.models.base import company_scope
from app.models.inventory import Warehouse
from app.models.order import SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.document_ingest_service import DocumentIngestService
from tests._pg_fixture import blank_session

from tests.scm.test_planning_change_diff_parity import (  # noqa: F401  (api is the fixture)
    _freeze_with_a_full_buy,
    _linked_line,
    _product,
    _rows_for,
    api,
)

MARKER = "zzt-ingestlineid"


def _uid() -> str:
    return str(uuid.uuid4())


def test_ingest_capture_carries_line_ids():
    with blank_session() as db:
        company_id = db.execute(text("select id from companies where code = 'SRT'")).scalar()
        with company_scope(db, frozenset({company_id})):
            uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:4]}", uom_name="Set")
            category = ProductCategory(
                id=_uid(), category_code=f"ZZT-{_uid()[:8]}", category_name=f"{MARKER} cat",
            )
            db.add_all([uom, category])
            db.flush()
            product = Product(
                id=_uid(), product_code=f"ZZT-{_uid()[:8]}", product_name=f"{MARKER} Basin",
                category_id=category.id, base_uom_id=uom.id, list_price=Decimal("120.00"),
            )
            warehouse = Warehouse(
                id=_uid(), warehouse_code=f"ZZT-WH-{_uid()[:4]}", warehouse_name="ZZT wh",
                location="ZZT", is_active=True, fulfilment_planning=True,
            )
            db.add_all([product, warehouse])
            db.flush()

            so = SalesOrder(
                id=_uid(), company_id=company_id, so_number=f"ZZT-INGEST-{_uid()[:8]}",
                status="open", demand_class="project",
            )
            db.add(so)
            db.flush()
            line = SalesOrderLine(
                id=_uid(), company_id=company_id, sales_order_id=so.id, product_id=product.id,
                warehouse_id=warehouse.id, qty_ordered=Decimal("72"), qty_delivered=Decimal("0"),
                required_date=date(2026, 8, 20), line_status="open",
            )
            db.add(line)
            db.commit()

            svc = DocumentIngestService(db, None, company_id=company_id)
            payload = SimpleNamespace(so_number=so.so_number)

            svc._capture_planning_diff_before(so, payload)
            svc._capture_planning_diff_after(so, payload)

    assert len(svc.so_diff_before) == 1, svc.so_diff_before
    assert len(svc.so_diff_after) == 1, svc.so_diff_after
    before_line = svc.so_diff_before[0]
    after_line = svc.so_diff_after[0]
    assert before_line.row_ref == str(line.id)
    assert after_line.row_ref == str(line.id)
    assert before_line.line_id == str(line.id), (
        "the BEFORE capture must carry line_id so a manual/ESB product swap pairs by "
        "identity, exactly as the manual-edit trigger's `_propagate_planning_change` does"
    )
    assert after_line.line_id == str(line.id), (
        "the AFTER capture must carry line_id too - `diff_lines` pairs a before/after "
        "sharing the SAME line_id first (Slice A rule 5)"
    )


# --------------------------------------------------------------------------- #
# R2-S1b (round 2): the ingest trigger reads a product swap as one
# product_changed row, exactly like the manual-edit trigger.
#
# Route taken: FALLBACK, as the brief invites. The pure HTTP route
# (`POST /external/ingest/sales_orders`) never ADOPTS the pushed order onto
# `projects.sales_orders` by itself - adoption is a separate step nothing in
# that call chain triggers - so `build_batch`'s held-or-inquiry gate
# (`app/services/planning_change_service.py`, `_build_row`) can never see a
# row to keep without ALSO driving project adoption AND a confirmed supply
# decision through `project_supply_service` on top of the ingest route: three
# services chained together for what this one test needs to prove, well past
# "smallest unit". Instead: `DocumentIngestService._capture_planning_diff
# _before` / `_after` - the exact methods `_run_planning_change_hook`
# (`app/api/v1/external/ingest.py` ~299-330) reads off the service - are
# called directly around an in-place product mutation on a HELD core line,
# then `diff_lines` and `build_batch` are called with the SAME arguments
# `_run_planning_change_hook` passes them. Everything downstream of the two
# capture calls is the real production code path; only the HTTP layer and
# project adoption are skipped.
#
# Expected today: GREEN. R-S1 (line_id on the captures, `fd618f6f7`) already
# landed, and AC-A5's line_id pairing / product_changed mapping already cover
# the rest (`test_outstanding_diff_line_identity.py`,
# `test_planning_change_batch_kind_parity.py`). Kept here as the AC-A5 guard
# for the INGEST trigger specifically - the one path none of those other
# files drives through the ingest service's own capture methods.
# --------------------------------------------------------------------------- #

def test_ingest_product_swap_reads_as_one_product_changed_row(api):
    from app.services import planning_change_service
    from app.services.scm.outstanding_diff import diff_lines

    world, project = api
    db = world.db
    core_so, core_line, product, order, mirror_line = _linked_line(
        world, project, qty_ordered=72,
    )
    _freeze_with_a_full_buy(db, world, order, mirror_line)
    new_product = _product(db)

    svc = DocumentIngestService(db, None, company_id=world.company_id)
    payload = SimpleNamespace(so_number=core_so.so_number)

    svc._capture_planning_diff_before(core_so, payload)
    core_line.product_id = new_product.id
    db.flush()
    svc._capture_planning_diff_after(core_so, payload)

    # The SAME two calls `_run_planning_change_hook` makes off the service's own
    # `so_diff_before`/`so_diff_after` and `so_header_id_by_number`.
    diff = diff_lines(svc.so_diff_before, svc.so_diff_after)
    applied_line_ids: dict[int, str] = {}
    for change in diff.changes:
        line_id = (change.after.row_ref if change.after else None) or (
            change.before.row_ref if change.before else None
        )
        if line_id:
            applied_line_ids[id(change)] = line_id
    batch = planning_change_service.build_batch(
        db, diff, applied_line_ids=applied_line_ids,
        order_ids={core_so.so_number: str(core_so.id)},
        actor=world.actor, import_job_id=None, file_name=None,
    )
    db.commit()

    assert batch is not None, "a held line's product swap must still raise a batch"
    rows = _rows_for(db, batch.id)
    assert len(rows) == 1, [r.kind for r in rows]
    row = rows[0]
    assert row.kind == "product_changed"
    assert row.from_json["item_code"] == product.product_code
    assert row.to_json["item_code"] == new_product.product_code
    assert not any(r.kind == "cancelled" for r in rows)
    assert not any(r.kind == "added" for r in rows)
