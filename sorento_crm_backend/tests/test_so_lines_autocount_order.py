"""S1 backend - sales order lines in AutoCount order, Source column, header source fix.

Plan: `documentation/plans/scm/PLAN-so-lines-autocount-order.md`.
UAC: `documentation/plans/scm/so-lines-autocount-order-acceptance-criteria.md`.

  AC-S1-1   migration adds `sales_order_lines.line_no` INTEGER NULL; single alembic head.
  AC-S1-2   a pushed line with `line_number: 7` is stored with `line_no = 7` on create.
  AC-S1-3   a re-push of the same `source_ref` with `line_number: 3` updates `line_no` to 3
            on the SAME row id.
  AC-S1-4   a re-push whose line omits `line_number` leaves `line_no` unchanged; an explicit
            `null` clears it.
  AC-S1-5   the D11 adopt path (ref-less pool row claimed by position) stores the incoming
            `line_no` on the claimed row.
  AC-S1-6   purchase-order lines still pop `line_number`; no `line_no` attribute exists on
            `purchase_order_lines`.
  AC-S1-7   `GET /sales-orders/{id}` lines carry `line_no` and `source`, surviving
            `response_model` (asserted on the wire, via the pydantic schema, not the dict).
  AC-S1-8   lines with `line_no` 1, 2, 10, 11, 3 come back ordered 1, 2, 3, 10, 11 (numeric).
  AC-S1-9   a closed line with `line_no` 1 sorts before an open line with `line_no` 2.
  AC-S1-10  lines with NULL `line_no` come after every numbered line, ordered among
            themselves by today's rule (open first, required_date nulls last, product code).
  AC-S1-11  `source` labels: autocount -> autocount, scm_order_inquiry -> inquiry,
            scm_upload -> upload, scm_so_history -> history, other -> manual.
  AC-S1-12  a line with NULL `source_system` under an `scm_upload` header reports
            `source = "manual"` (R2: the line's own provenance, never the header's).
  AC-S1-13  header: an `autocount` sales order reports `source = "autocount"` (was `manual`).
  AC-S1-14  list filter `source=autocount` returns AutoCount orders only; `source=manual`
            no longer returns them.

None of this exists yet, so every ordering/serialize test below is expected to fail today
for one of two reasons, never a fixture bug:

* `sales_order_lines` carries no `line_no` column, so a raw-SQL read of it
  (`SELECT * ... `) raises `KeyError` on that key - AC-S1-1/2/3/4/5/6's own red.
* `_line_sort_key` / `serialize()` / `_source_label` / `_SOURCE_SYSTEMS` do not know about
  `line_no` or `autocount` yet, so the ordering and label assertions fail on the CURRENT
  (open-first / manual-fallback) behaviour rather than on an exception.

Postgres only (`tests/_pg_fixture.py`). Ingest-surface tests reuse the `env` fixture and
record builders from `tests.test_ingest_documents` / `tests.test_ingest_documents_v2_adoption`
per the tester brief; serialize/sort/list tests use a bare `pg_session()` the same way
`tests/test_scm_sales_order_agent.py` already does for this same service. Every row is
seeded here, marker-prefixed, never borrowed - CI's database is empty.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.procurement import PurchaseOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.schemas.scm_orders import SalesOrder as SalesOrderSchema
from app.services.scm.sales_order_service import SalesOrderService

from tests._pg_fixture import pg_session, unique_code
from tests.test_ingest_documents import (
    INGEST_PO,
    INGEST_SO,
    MARKER,
    _po_line,
    _po_record,
    _ref,
    _so_line,
    _so_record,
    env,  # noqa: F401 - pytest fixture, imported for reuse
)
from tests.test_ingest_documents_v2_adoption import _seed_line, _seed_so_header

__all__ = ["env"]

# Two explicit instants for the position tie-break (AC-S1-5), the same convention
# `test_ingest_documents_v2_adoption.py::TestPositionTieBreak` uses.
T0 = datetime(2026, 1, 1, 9, 0, 0)
T1 = T0 + timedelta(minutes=5)


def _u() -> str:
    return str(uuid.uuid4())


# ============================================================= ingest (AC-S1-2..6)


class TestIngestLineNo:
    def test_ac_s1_2_create_stores_line_no(self, env):
        line = _so_line(env, qty_ordered=10, line_number=7)
        record = _so_record(env, lines=[line])

        res = env.post(INGEST_SO, [record])

        assert res.status_code == 200, res.text
        header = env.header("sales_orders", record["source_ref"])
        row = env.so_lines(header["id"])[0]
        assert row["line_no"] == 7

    def test_ac_s1_3_repush_same_ref_updates_line_no_on_the_same_row(self, env):
        line = _so_line(env, qty_ordered=10, line_number=7)
        record = _so_record(env, lines=[line])
        env.post(INGEST_SO, [record])
        header = env.header("sales_orders", record["source_ref"])
        original_id = env.so_lines(header["id"])[0]["id"]

        updated_line = dict(line, line_number=3)
        res = env.post(INGEST_SO, [dict(record, lines=[updated_line])])

        assert res.json()["records"][0]["outcome"] == "updated", res.text
        row = env.so_lines(header["id"])[0]
        assert str(row["id"]) == str(original_id)
        assert row["line_no"] == 3

    def test_ac_s1_4_absent_line_number_leaves_line_no_unchanged(self, env):
        line = _so_line(env, qty_ordered=10, line_number=7)
        record = _so_record(env, lines=[line])
        env.post(INGEST_SO, [record])
        header = env.header("sales_orders", record["source_ref"])

        omitted = dict(line, qty_ordered=12)
        omitted.pop("line_number", None)
        res = env.post(INGEST_SO, [dict(record, lines=[omitted])])

        assert res.json()["records"][0]["outcome"] == "updated", res.text
        row = env.so_lines(header["id"])[0]
        assert row["qty_ordered"] == 12
        assert row["line_no"] == 7

    def test_ac_s1_4_explicit_null_clears_line_no(self, env):
        line = _so_line(env, qty_ordered=10, line_number=7)
        record = _so_record(env, lines=[line])
        env.post(INGEST_SO, [record])
        header = env.header("sales_orders", record["source_ref"])

        cleared = dict(line, line_number=None)
        res = env.post(INGEST_SO, [dict(record, lines=[cleared])])

        assert res.json()["records"][0]["outcome"] == "updated", res.text
        row = env.so_lines(header["id"])[0]
        assert row["line_no"] is None

    def test_ac_s1_5_d11_adopt_by_position_stores_incoming_line_no(self, env):
        """The D11 adoption ladder's pass 3 (position): two ref-less rows sharing the same
        (product, warehouse, outstanding) key, told apart only by `created_at` order against
        the incoming lines' own `line_number` order - copied from
        `test_ingest_documents_v2_adoption.py::TestPositionTieBreak`, with the NEW assertion
        that the claimed row's `line_no` becomes the incoming position.
        """
        number = f"{MARKER}-SO-{uuid.uuid4().hex[:8]}"
        header = _seed_so_header(env, number=number)
        row_t0 = _seed_line(
            env, SalesOrderLine, header_id=header.id, fk_field="sales_order_id",
            delivered_field="qty_delivered", product_ref=env.product_ref,
            qty_ordered=10, delivered=Decimal("0"), created_at=T0,
        )
        row_t1 = _seed_line(
            env, SalesOrderLine, header_id=header.id, fk_field="sales_order_id",
            delivered_field="qty_delivered", product_ref=env.product_ref,
            qty_ordered=10, delivered=Decimal("0"), created_at=T1,
        )
        line_1 = _so_line(env, product_ref=env.product_ref, qty_ordered=10, line_number=1)
        line_2 = _so_line(env, product_ref=env.product_ref, qty_ordered=10, line_number=2)
        record = _so_record(env, number=number, lines=[line_1, line_2])

        res = env.post(INGEST_SO, [record])

        assert res.status_code == 200, res.text
        lines = {l["source_ref"]: l for l in env.so_lines(header.id)}
        claimed_t0 = lines[line_1["source_ref"]]
        claimed_t1 = lines[line_2["source_ref"]]
        assert str(claimed_t0["id"]) == str(row_t0.id)
        assert str(claimed_t1["id"]) == str(row_t1.id)
        assert claimed_t0["line_no"] == 1
        assert claimed_t1["line_no"] == 2

    def test_ac_s1_6_purchase_order_lines_have_no_line_no_column(self, env):
        """PO lines keep popping `line_number` - no column exists to hold it.

        Not expected to be red today: the plan's own answer for a PO line is "gets
        nothing" (no screen has asked for it), so this is a guard against the coder
        widening the wrong table, not a gap being closed.
        """
        assert hasattr(PurchaseOrderLine, "line_no") is False

        line = _po_line(env, qty_ordered=4, line_number=3)
        record = _po_record(env, lines=[line])

        res = env.post(INGEST_PO, [record])

        assert res.status_code == 200, res.text
        header = env.header("purchase_orders", record["source_ref"])
        row = env.po_lines(header["id"])[0]
        assert "line_no" not in row


# ================================================== serialize / sort / source (AC-S1-7..14)


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture()
def world(db):
    cat = ProductCategory(id=_u(), category_code=unique_code(MARKER), category_name=f"{MARKER} cat")
    uom = UnitOfMeasure(id=_u(), uom_code=unique_code("U")[:20], uom_name=f"{MARKER} u")
    db.add_all([cat, uom])
    db.flush()
    customer = Customer(id=_u(), customer_code=unique_code("C"), customer_name=f"{MARKER} Acme")
    db.add(customer)
    db.flush()

    def product(suffix: str) -> Product:
        row = Product(
            id=_u(), product_code=f"{MARKER}-{suffix}", product_name=f"{MARKER} {suffix}",
            category_id=cat.id, base_uom_id=uom.id, list_price=0,
            is_active=True, is_discontinued=False,
        )
        db.add(row)
        db.flush()
        return row

    return {"customer": customer, "product": product}


def _order(db, world, *, source_system=None, status="open") -> SalesOrder:
    so = SalesOrder(
        id=_u(), so_number=unique_code(MARKER), status=status,
        order_date=None, customer_id=world["customer"].id, source_system=source_system,
    )
    db.add(so)
    db.flush()
    return so


def _line(
    db, world, order, *, suffix, line_no=None, line_status="open",
    required_date=None, source_system=None, qty_ordered=10, qty_delivered=0,
) -> SalesOrderLine:
    row = SalesOrderLine(
        id=_u(), sales_order_id=order.id, product_id=world["product"](suffix).id,
        qty_ordered=Decimal(str(qty_ordered)), qty_delivered=Decimal(str(qty_delivered)),
        line_status=line_status, required_date=required_date, source_system=source_system,
    )
    db.add(row)
    db.flush()
    # `line_no` is set as a plain attribute rather than a constructor kwarg: before the
    # migration lands there is no mapped column at all, and the declarative constructor
    # rejects an unknown keyword outright (`TypeError`) rather than silently accepting it -
    # so a constructor kwarg here would fail every test in this file for the WRONG reason.
    # Once the column exists this is exactly how a real caller sets it (`row.line_no = 7`).
    row.line_no = line_no
    db.flush()
    return row


class TestSerializeWireAndOrder:
    def test_ac_s1_7_line_no_and_source_survive_response_model(self, world, db):
        so = _order(db, world, source_system="autocount")
        _line(db, world, so, suffix="A", line_no=7, source_system="autocount")

        row = SalesOrderService(db).serialize(SalesOrderService(db)._get_or_404(so.id))
        wire = SalesOrderSchema.model_validate(row)

        assert wire.lines[0].line_no == 7
        assert wire.lines[0].source == "autocount"

    def test_ac_s1_8_numeric_order_not_lexicographic(self, world, db):
        so = _order(db, world)
        for suffix, n in [("A", 1), ("B", 2), ("C", 10), ("D", 11), ("E", 3)]:
            _line(db, world, so, suffix=suffix, line_no=n)

        row = SalesOrderService(db).serialize(SalesOrderService(db)._get_or_404(so.id))

        numbers = [ln["line_no"] for ln in row["lines"]]
        assert numbers == [1, 2, 3, 10, 11]

    def test_ac_s1_9_closed_numbered_line_sorts_before_an_open_one(self, world, db):
        """R1: open-first is gone once a line carries a number - AutoCount's own order
        wins whatever the line's status."""
        so = _order(db, world)
        _line(db, world, so, suffix="OPEN", line_no=2, line_status="open")
        _line(db, world, so, suffix="CLOSED", line_no=1, line_status="closed")

        row = SalesOrderService(db).serialize(SalesOrderService(db)._get_or_404(so.id))

        assert [ln["sku"] for ln in row["lines"]] == [f"{MARKER}-CLOSED", f"{MARKER}-OPEN"]

    def test_ac_s1_10_null_line_no_lines_sort_after_every_numbered_line(self, world, db):
        """The nulls keep today's rule among themselves: open first, then required_date
        (nulls last), then product code."""
        so = _order(db, world)
        _line(db, world, so, suffix="N9", line_no=9)
        # Two NULL-line_no lines, ordered against EACH OTHER by the old rule: an open one
        # due sooner beats a closed one due later.
        _line(
            db, world, so, suffix="NULL-LATE", line_no=None, line_status="closed",
            required_date=date(2027, 6, 1),
        )
        _line(
            db, world, so, suffix="NULL-EARLY", line_no=None, line_status="open",
            required_date=date(2027, 1, 1),
        )

        row = SalesOrderService(db).serialize(SalesOrderService(db)._get_or_404(so.id))

        assert [ln["sku"] for ln in row["lines"]] == [
            f"{MARKER}-N9",
            f"{MARKER}-NULL-EARLY",
            f"{MARKER}-NULL-LATE",
        ]


class TestSourceLabels:
    @pytest.mark.parametrize(
        "source_system,expected",
        [
            ("autocount", "autocount"),
            ("scm_order_inquiry", "inquiry"),
            ("scm_upload", "upload"),
            ("scm_so_history", "history"),
            ("something_else", "manual"),
            (None, "manual"),
        ],
    )
    def test_ac_s1_11_line_source_label(self, world, db, source_system, expected):
        so = _order(db, world)
        _line(db, world, so, suffix="L", line_no=1, source_system=source_system)

        row = SalesOrderService(db).serialize(SalesOrderService(db)._get_or_404(so.id))

        assert row["lines"][0]["source"] == expected

    def test_ac_s1_12_null_line_source_system_under_an_upload_header_is_manual(self, world, db):
        """R2: the line's OWN provenance, never the header's - an `scm_upload` header must
        not make a ref-less line under it read as `upload`."""
        so = _order(db, world, source_system="scm_upload")
        _line(db, world, so, suffix="L", line_no=1, source_system=None)

        row = SalesOrderService(db).serialize(SalesOrderService(db)._get_or_404(so.id))

        assert row["source"] == "upload"
        assert row["lines"][0]["source"] == "manual"


class TestHeaderSourceAndListFilter:
    def test_ac_s1_13_autocount_header_reports_autocount_not_manual(self, world, db):
        so = _order(db, world, source_system="autocount")
        _line(db, world, so, suffix="L", line_no=1, source_system="autocount")

        row = SalesOrderService(db).serialize(SalesOrderService(db)._get_or_404(so.id))

        assert row["source"] == "autocount"

    def test_ac_s1_14_list_filter_autocount_vs_manual_split(self, world, db):
        autocount_order = _order(db, world, source_system="autocount")
        _line(db, world, autocount_order, suffix="AC", line_no=1, source_system="autocount")
        manual_order = _order(db, world, source_system=None)
        _line(db, world, manual_order, suffix="MAN", line_no=None, source_system=None)

        svc = SalesOrderService(db)
        autocount_result = svc.list(
            page=1, limit=50, sort="so_number", direction="asc",
            query=MARKER, status=None, priority=None, source="autocount",
        )
        manual_result = svc.list(
            page=1, limit=50, sort="so_number", direction="asc",
            query=MARKER, status=None, priority=None, source="manual",
        )

        autocount_numbers = {row["so_number"] for row in autocount_result["data"]}
        manual_numbers = {row["so_number"] for row in manual_result["data"]}
        assert autocount_order.so_number in autocount_numbers
        assert manual_order.so_number not in autocount_numbers
        assert manual_order.so_number in manual_numbers
        assert autocount_order.so_number not in manual_numbers
