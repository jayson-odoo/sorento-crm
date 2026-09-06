"""Group V7 - line adoption at cutover (plan D11, `PLAN-autocount-document-ingest-v2.md`
section 1 decision D11 / section 3 row S1b).

  AC-V7-1  a matched ref-less row keeps its id, gains `source_ref` = the payload
           line's DtlKey and `source_system='autocount'`, has its values
           restated, and a stock_transfer / loading_plan_line dependent that
           pointed at it still points at it. Both sales orders (`qty_delivered`)
           and purchase orders (`qty_received`).
  AC-V7-2  two ref-less rows sharing (product, warehouse, outstanding) are told
           apart by position: incoming `line_number` order against the rows'
           own `created_at, id` order.
  AC-V7-3  step 2 (exactly one remaining row for the product/warehouse, no
           outstanding match - adopted anyway), step 3 (several remain, counts
           agree - position decides), and the "otherwise" fallback (counts
           disagree - the incoming line is created fresh and the leftover rows
           follow the existing delete-or-cancel rule).
  AC-V7-4  a row that already carries its OWN `source_ref` is never captured by
           a different incoming DtlKey, even when the (product, warehouse,
           outstanding) key matches - it is matched only by its own ref, exactly
           as today, and a ref-less row on the SAME document is still adopted by
           the new rule alongside it.
  AC-V7-5  the verdict carries `lines: {adopted, created, updated, deleted,
           cancelled}` for a document record, identically on `dry_run=true`,
           which writes nothing.
  AC-V7-6  `line_number` is an optional int accepted on every canonical line
           (SO and PO); a payload that omits it still adopts by steps 1-2 and
           falls back to payload order for step 3.

Substrate reused per the tester brief, nothing new: `env`, `_Env`,
`_so_record`, `_so_line`, `_po_record`, `_po_line`, `_ref`, `MARKER` from
`tests.test_ingest_documents`. "xlsx-era" lines are seeded by inserting
`sales_order_lines` / `purchase_order_lines` rows DIRECTLY (through the ORM,
never raw SQL naming a bare table the `projects` schema also owns) under a
header the payload adopts by number - `source_ref=NULL`,
`source_system='scm_upload'` by default, the shape the xlsx upload itself
leaves behind - with an explicit ascending `created_at` where position matters.

None of this exists yet, so every test below is expected to fail today for one
of three reasons, never a fixture bug:

* `_sync_lines` treats every ref-less row of a header adopted by number as
  stale - deleted when nothing points at it, cancelled in place when something
  does - and inserts the payload's lines fresh. Every "the SAME row id gains
  the ref" assertion here fails against a brand NEW row instead.
* `line_number` does not exist on `_CanonicalLine` yet, so a payload sending it
  is rejected outright by `extra="forbid"` (`outcome == "failed"`,
  `errors["lines.N.line_number"]` present).
* `RecordResult` / `IngestResult.as_dict()` carries no `lines` key at all, so
  `entry["lines"]` raises `KeyError` on every record.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func

from app.models.order import SalesOrder, SalesOrderLine
from app.models.procurement import PurchaseOrder, PurchaseOrderLine
from app.models.scm import LoadingPlanLine
from app.models.stock_transfer import StockTransfer

from tests.test_ingest_documents import (
    INGEST_PO,
    INGEST_SO,
    MARKER,
    _po_line,
    _po_record,
    _ref,
    _so_line,
    _so_record,
    env,  # noqa: F401 - pytest fixture, imported for reuse per the tester brief
)

__all__ = ["env"]

# Two explicit instants, far enough apart that ordering can never be a tie on
# clock resolution, used everywhere position (not the matching key) is what
# decides the outcome.
T0 = datetime(2026, 1, 1, 9, 0, 0)
T1 = T0 + timedelta(minutes=5)


def _seed_so_header(env, *, number: str) -> SalesOrder:
    """A sales order the xlsx upload (or the extract importer) already owns."""
    row = SalesOrder(
        id=str(uuid.uuid4()),
        so_number=number,
        status="open",
        company_id=env.company_a,
        source_system="import",
    )
    env.db.add(row)
    env.db.flush()
    return row


def _seed_po_header(env, *, number: str) -> PurchaseOrder:
    row = PurchaseOrder(
        id=str(uuid.uuid4()),
        po_number=number,
        status="active",
        company_id=env.company_a,
        source_system="import",
    )
    env.db.add(row)
    env.db.flush()
    return row


def _resolve(env, entity_type: str, source_ref) -> str | None:
    if not source_ref:
        return None
    return env.refs.resolve(entity_type=entity_type, source_ref=source_ref)


def _seed_line(
    env,
    model,
    *,
    header_id: str,
    fk_field: str,
    delivered_field: str,
    product_ref: str,
    warehouse_ref: str | None = None,
    qty_ordered,
    delivered=Decimal("0"),
    created_at: datetime | None = None,
    source_ref: str | None = None,
    source_system: str | None = "scm_upload",
):
    """One line, seeded directly - never through the ingest endpoint.

    Defaults to the xlsx-era shape (`source_ref=None`, `source_system=
    'scm_upload'`); AC-V7-4 overrides both to seed a line an EARLIER autocount
    push already claimed, alongside a genuinely ref-less one on the same
    document.
    """
    kwargs = {
        "id": str(uuid.uuid4()),
        fk_field: str(header_id),
        "product_id": _resolve(env, "products", product_ref),
        "warehouse_id": _resolve(env, "warehouses", warehouse_ref),
        "qty_ordered": Decimal(str(qty_ordered)),
        delivered_field: Decimal(str(delivered)),
        "line_status": "open",
        "company_id": env.company_a,
        "source_ref": source_ref,
        "source_system": source_system,
    }
    if created_at is not None:
        kwargs["created_at"] = created_at
    row = model(**kwargs)
    env.db.add(row)
    env.db.flush()
    return row


def _plan_line_count(env, plan_line_id: str) -> int:
    return (
        env.db.query(func.count())
        .select_from(LoadingPlanLine)
        .filter(LoadingPlanLine.id == plan_line_id)
        .scalar()
    )


# ================================================================== AC-V7-1
class TestMatchedRowKeepsItsId:
    def test_sales_order_lines_keep_their_ids_and_gain_the_ref(self, env):
        number = f"{MARKER}-SO-{uuid.uuid4().hex[:8]}"
        header = _seed_so_header(env, number=number)
        row_a = _seed_line(
            env,
            SalesOrderLine,
            header_id=header.id,
            fk_field="sales_order_id",
            delivered_field="qty_delivered",
            product_ref=env.product_ref,
            qty_ordered=10,
            delivered=Decimal("3"),  # outstanding 7
        )
        row_b = _seed_line(
            env,
            SalesOrderLine,
            header_id=header.id,
            fk_field="sales_order_id",
            delivered_field="qty_delivered",
            product_ref=env.product2_ref,
            qty_ordered=5,
            delivered=Decimal("0"),  # outstanding 5
        )
        transfer_id = env.stock_transfer(row_b.id)

        line_a = _so_line(env, product_ref=env.product_ref, qty_ordered=7, unit_price="99.00")
        line_b = _so_line(env, product_ref=env.product2_ref, qty_ordered=5, unit_price="88.00")
        record = _so_record(env, number=number, lines=[line_a, line_b])

        res = env.post(INGEST_SO, [record])

        assert res.status_code == 200, res.text
        assert res.json()["records"][0]["outcome"] == "updated", res.text
        lines = {str(l["id"]): l for l in env.so_lines(header.id)}
        assert len(lines) == 2
        assert str(row_a.id) in lines, "row A must keep its id, not be replaced"
        assert str(row_b.id) in lines, "row B must keep its id, not be replaced"
        adopted_a = lines[str(row_a.id)]
        adopted_b = lines[str(row_b.id)]
        assert adopted_a["source_ref"] == line_a["source_ref"]
        assert adopted_a["source_system"] == "autocount"
        assert adopted_a["unit_price"] == Decimal("99.00")
        assert adopted_b["source_ref"] == line_b["source_ref"]
        assert adopted_b["source_system"] == "autocount"
        assert adopted_b["unit_price"] == Decimal("88.00")
        still_attached = (
            env.db.query(StockTransfer.so_line_id)
            .filter(StockTransfer.id == transfer_id)
            .scalar()
        )
        assert str(still_attached) == str(row_b.id)

    def test_purchase_order_lines_keep_their_ids_and_gain_the_ref(self, env):
        number = f"{MARKER}-PO-{uuid.uuid4().hex[:8]}"
        header = _seed_po_header(env, number=number)
        row_a = _seed_line(
            env,
            PurchaseOrderLine,
            header_id=header.id,
            fk_field="purchase_order_id",
            delivered_field="qty_received",
            product_ref=env.product_ref,
            qty_ordered=10,
            delivered=Decimal("2"),  # outstanding 8
        )
        row_b = _seed_line(
            env,
            PurchaseOrderLine,
            header_id=header.id,
            fk_field="purchase_order_id",
            delivered_field="qty_received",
            product_ref=env.product2_ref,
            qty_ordered=6,
            delivered=Decimal("0"),  # outstanding 6
        )
        plan_line_id = env.loading_plan_line(row_b.id)

        line_a = _po_line(env, product_ref=env.product_ref, qty_ordered=8, unit_cost="15.00")
        line_b = _po_line(env, product_ref=env.product2_ref, qty_ordered=6, unit_cost="20.00")
        record = _po_record(env, number=number, lines=[line_a, line_b])

        res = env.post(INGEST_PO, [record])

        assert res.status_code == 200, res.text
        assert res.json()["records"][0]["outcome"] == "updated", res.text
        lines = {str(l["id"]): l for l in env.po_lines(header.id)}
        assert len(lines) == 2
        assert str(row_a.id) in lines
        assert str(row_b.id) in lines
        assert lines[str(row_a.id)]["source_ref"] == line_a["source_ref"]
        assert lines[str(row_a.id)]["source_system"] == "autocount"
        assert lines[str(row_a.id)]["unit_cost"] == Decimal("15.00")
        assert lines[str(row_b.id)]["source_ref"] == line_b["source_ref"]
        assert lines[str(row_b.id)]["unit_cost"] == Decimal("20.00")
        assert _plan_line_count(env, plan_line_id) == 1


# ================================================================== AC-V7-2
class TestPositionTieBreak:
    def test_line_number_order_matches_created_at_order_on_a_tied_key(self, env):
        number = f"{MARKER}-SO-{uuid.uuid4().hex[:8]}"
        header = _seed_so_header(env, number=number)
        row_t0 = _seed_line(
            env,
            SalesOrderLine,
            header_id=header.id,
            fk_field="sales_order_id",
            delivered_field="qty_delivered",
            product_ref=env.product_ref,
            qty_ordered=10,
            delivered=Decimal("0"),
            created_at=T0,
        )
        row_t1 = _seed_line(
            env,
            SalesOrderLine,
            header_id=header.id,
            fk_field="sales_order_id",
            delivered_field="qty_delivered",
            product_ref=env.product_ref,
            qty_ordered=10,
            delivered=Decimal("0"),
            created_at=T1,
        )
        line_1 = _so_line(env, product_ref=env.product_ref, qty_ordered=10, line_number=1)
        line_2 = _so_line(env, product_ref=env.product_ref, qty_ordered=10, line_number=2)
        record = _so_record(env, number=number, lines=[line_1, line_2])

        res = env.post(INGEST_SO, [record])

        assert res.status_code == 200, res.text
        lines = {l["source_ref"]: l for l in env.so_lines(header.id)}
        assert str(lines[line_1["source_ref"]]["id"]) == str(row_t0.id)
        assert str(lines[line_2["source_ref"]]["id"]) == str(row_t1.id)


# ================================================================== AC-V7-3
class TestRemainderRules:
    def test_step2_single_remaining_row_adopts_despite_outstanding_mismatch(self, env):
        number = f"{MARKER}-SO-{uuid.uuid4().hex[:8]}"
        header = _seed_so_header(env, number=number)
        row = _seed_line(
            env,
            SalesOrderLine,
            header_id=header.id,
            fk_field="sales_order_id",
            delivered_field="qty_delivered",
            product_ref=env.product_ref,
            qty_ordered=10,
            delivered=Decimal("0"),  # outstanding 10
        )
        # outstanding 6, matches nothing exactly - but it is the only ref-less
        # row left for this product, so step 2 adopts it anyway.
        line = _so_line(env, product_ref=env.product_ref, qty_ordered=6)
        record = _so_record(env, number=number, lines=[line])

        res = env.post(INGEST_SO, [record])

        assert res.status_code == 200, res.text
        lines = env.so_lines(header.id)
        assert len(lines) == 1
        assert str(lines[0]["id"]) == str(row.id)
        assert lines[0]["source_ref"] == line["source_ref"]
        assert lines[0]["source_system"] == "autocount"
        assert lines[0]["qty_ordered"] == Decimal("6")

    def test_step3_equal_counts_are_matched_by_position(self, env):
        number = f"{MARKER}-SO-{uuid.uuid4().hex[:8]}"
        header = _seed_so_header(env, number=number)
        row_t0 = _seed_line(
            env,
            SalesOrderLine,
            header_id=header.id,
            fk_field="sales_order_id",
            delivered_field="qty_delivered",
            product_ref=env.product_ref,
            qty_ordered=5,
            delivered=Decimal("0"),  # outstanding 5
            created_at=T0,
        )
        row_t1 = _seed_line(
            env,
            SalesOrderLine,
            header_id=header.id,
            fk_field="sales_order_id",
            delivered_field="qty_delivered",
            product_ref=env.product_ref,
            qty_ordered=8,
            delivered=Decimal("0"),  # outstanding 8
            created_at=T1,
        )
        # outstanding 3 and 4 - neither matches row_t0 (5) nor row_t1 (8), but
        # two rows remain for two incoming lines, so position decides.
        line_1 = _so_line(env, product_ref=env.product_ref, qty_ordered=3, line_number=1)
        line_2 = _so_line(env, product_ref=env.product_ref, qty_ordered=4, line_number=2)
        record = _so_record(env, number=number, lines=[line_1, line_2])

        res = env.post(INGEST_SO, [record])

        assert res.status_code == 200, res.text
        lines = {l["source_ref"]: l for l in env.so_lines(header.id)}
        assert str(lines[line_1["source_ref"]]["id"]) == str(row_t0.id)
        assert str(lines[line_2["source_ref"]]["id"]) == str(row_t1.id)

    def test_unequal_counts_create_a_new_line_and_leftovers_follow_delete_or_cancel(
        self, env
    ):
        number = f"{MARKER}-PO-{uuid.uuid4().hex[:8]}"
        header = _seed_po_header(env, number=number)
        row_unreferenced = _seed_line(
            env,
            PurchaseOrderLine,
            header_id=header.id,
            fk_field="purchase_order_id",
            delivered_field="qty_received",
            product_ref=env.product_ref,
            qty_ordered=5,
            delivered=Decimal("0"),  # outstanding 5
        )
        row_referenced = _seed_line(
            env,
            PurchaseOrderLine,
            header_id=header.id,
            fk_field="purchase_order_id",
            delivered_field="qty_received",
            product_ref=env.product_ref,
            qty_ordered=9,
            delivered=Decimal("0"),  # outstanding 9
        )
        plan_line_id = env.loading_plan_line(row_referenced.id)

        # Two rows remain, one incoming line - counts disagree, and outstanding
        # 3 matches neither 5 nor 9.
        line = _po_line(env, product_ref=env.product_ref, qty_ordered=3)
        record = _po_record(env, number=number, lines=[line])

        res = env.post(INGEST_PO, [record])

        assert res.status_code == 200, res.text
        lines = {str(l["id"]): l for l in env.po_lines(header.id)}
        assert len(lines) == 2
        new_row = next(l for l in lines.values() if l["source_ref"] == line["source_ref"])
        assert str(new_row["id"]) not in {str(row_unreferenced.id), str(row_referenced.id)}
        assert new_row["source_system"] == "autocount"
        assert str(row_unreferenced.id) not in lines, "unreferenced leftover is deleted"
        cancelled = lines[str(row_referenced.id)]
        assert cancelled["line_status"] == "cancelled"
        assert cancelled["qty_ordered"] == Decimal("9"), "cancelled row is untouched otherwise"
        assert _plan_line_count(env, plan_line_id) == 1


# ================================================================== AC-V7-4
class TestRefdRowMatchesOnlyItsOwnRef:
    def test_a_row_with_its_own_ref_is_not_captured_by_a_matching_key(self, env):
        number = f"{MARKER}-SO-{uuid.uuid4().hex[:8]}"
        header = _seed_so_header(env, number=number)
        existing_ref = _ref("XREF")
        row_x = _seed_line(
            env,
            SalesOrderLine,
            header_id=header.id,
            fk_field="sales_order_id",
            delivered_field="qty_delivered",
            product_ref=env.product_ref,
            qty_ordered=10,
            delivered=Decimal("3"),  # outstanding 7
            source_ref=existing_ref,
            source_system="autocount",
        )
        transfer_id = env.stock_transfer(row_x.id)
        row_plain = _seed_line(
            env,
            SalesOrderLine,
            header_id=header.id,
            fk_field="sales_order_id",
            delivered_field="qty_delivered",
            product_ref=env.product2_ref,
            qty_ordered=5,
            delivered=Decimal("0"),  # outstanding 5, genuinely ref-less
        )

        # Same product and same outstanding as row_x (7), under a DIFFERENT
        # DtlKey - must NOT be adopted onto row_x's id.
        line_y = _so_line(env, product_ref=env.product_ref, qty_ordered=7)
        line_match = _so_line(env, product_ref=env.product2_ref, qty_ordered=5)
        record = _so_record(env, number=number, lines=[line_y, line_match])

        res = env.post(INGEST_SO, [record])

        assert res.status_code == 200, res.text
        lines = {str(l["id"]): l for l in env.so_lines(header.id)}
        assert str(row_x.id) in lines, "row X is cancelled in place, not deleted"
        x_after = lines[str(row_x.id)]
        assert x_after["source_ref"] == existing_ref, "kept its OWN ref, not line_y's DtlKey"
        assert x_after["line_status"] == "cancelled"
        assert x_after["qty_ordered"] == Decimal("10"), "untouched, not restated"
        y_row = next(l for l in lines.values() if l["source_ref"] == line_y["source_ref"])
        assert str(y_row["id"]) != str(row_x.id), "line_y lands on a fresh row"
        assert str(row_plain.id) in lines, "the genuinely ref-less row is adopted by D11"
        adopted_plain = lines[str(row_plain.id)]
        assert adopted_plain["source_ref"] == line_match["source_ref"]
        assert adopted_plain["source_system"] == "autocount"
        still_attached = (
            env.db.query(StockTransfer.so_line_id)
            .filter(StockTransfer.id == transfer_id)
            .scalar()
        )
        assert str(still_attached) == str(row_x.id)


# ================================================================== AC-V7-5
def _seed_mixed_document(env):
    """adopted=1, created=1, updated=0, deleted=1, cancelled=1 in one push."""
    number = f"{MARKER}-SO-{uuid.uuid4().hex[:8]}"
    header = _seed_so_header(env, number=number)
    row_adopt = _seed_line(
        env,
        SalesOrderLine,
        header_id=header.id,
        fk_field="sales_order_id",
        delivered_field="qty_delivered",
        product_ref=env.product_ref,
        qty_ordered=5,
        delivered=Decimal("0"),  # outstanding 5
    )
    row_cancel = _seed_line(
        env,
        SalesOrderLine,
        header_id=header.id,
        fk_field="sales_order_id",
        delivered_field="qty_delivered",
        product_ref=env.product2_ref,
        qty_ordered=3,
        delivered=Decimal("0"),
    )
    env.stock_transfer(row_cancel.id)
    delete_product_ref = env.link_product(env.company_a)
    row_delete = _seed_line(
        env,
        SalesOrderLine,
        header_id=header.id,
        fk_field="sales_order_id",
        delivered_field="qty_delivered",
        product_ref=delete_product_ref,
        qty_ordered=2,
        delivered=Decimal("0"),
    )
    new_product_ref = env.link_product(env.company_a)
    line_adopt = _so_line(env, product_ref=env.product_ref, qty_ordered=5)
    line_new = _so_line(env, product_ref=new_product_ref, qty_ordered=7)
    record = _so_record(env, number=number, lines=[line_adopt, line_new])
    return header, record, {
        "row_adopt": row_adopt,
        "row_cancel": row_cancel,
        "row_delete": row_delete,
    }


class TestVerdictLineCounts:
    EXPECTED = {"adopted": 1, "created": 1, "updated": 0, "deleted": 1, "cancelled": 1}

    def test_real_run_reports_the_counts(self, env):
        header, record, rows = _seed_mixed_document(env)

        res = env.post(INGEST_SO, [record])

        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "updated", res.text
        assert entry["lines"] == self.EXPECTED

    def test_a_second_push_that_only_updates_a_line_reports_updated(self, env):
        """A partial second push still sweeps the lines it does not name - the
        document owns ALL of its lines, not just the ones a given push mentions
        - so the previously-created line is deleted (unreferenced) and the
        previously-cancelled line is swept into `cancelled` again (still
        referenced, still ref-less)."""
        header, record, rows = _seed_mixed_document(env)
        first = env.post(INGEST_SO, [record])
        adopted_ref = first.json()["records"][0]  # sanity: first push landed
        assert adopted_ref["outcome"] == "updated", first.text
        lines = {l["source_ref"]: l for l in env.so_lines(header.id)}
        # The line adopted in the first push now carries its own source_ref -
        # pushing it again with a changed quantity is an ordinary by-ref update,
        # not a fresh adoption.
        adopted_line_ref = next(
            source_ref
            for source_ref, row in lines.items()
            if str(row["id"]) == str(rows["row_adopt"].id)
        )
        second_line = dict(_so_line(env, product_ref=env.product_ref, qty_ordered=9))
        second_line["source_ref"] = adopted_line_ref

        res = env.post(INGEST_SO, [dict(record, lines=[second_line])])

        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "updated", res.text
        assert entry["lines"] == {
            "adopted": 0,
            "created": 0,
            "updated": 1,
            "deleted": 1,
            "cancelled": 1,
        }

    def test_dry_run_reports_the_same_counts_and_writes_nothing(self, env):
        header, record, rows = _seed_mixed_document(env)
        # Committed, not just flushed - a dry run's rollback must not also take
        # back the xlsx-era rows this test seeded, or "nothing changed" would be
        # true only because the fixture's own data disappeared too.
        env.db.commit()
        before_ids = {str(row.id) for row in rows.values()}
        before_refs = {
            str(row.id): row.source_ref for row in rows.values()
        }

        res = env.post(INGEST_SO, [record], dry_run=True)

        assert res.status_code == 200, res.text
        body = res.json()
        assert body["dry_run"] is True
        entry = body["records"][0]
        assert entry["lines"] == TestVerdictLineCounts.EXPECTED
        after = {str(l["id"]): l for l in env.so_lines(header.id)}
        assert set(after) == before_ids, "dry run must not delete, insert or reassign any row"
        for row_id, source_ref in before_refs.items():
            assert after[row_id]["source_ref"] == source_ref, "dry run must not stamp a ref"


# ================================================================== AC-V7-6
class TestLineNumberField:
    def test_line_number_is_accepted_on_sales_order_lines(self, env):
        line = _so_line(env, qty_ordered=10, line_number=7)
        record = _so_record(env, lines=[line])

        res = env.post(INGEST_SO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text
        assert "lines.0.line_number" not in entry.get("errors", {})

    def test_line_number_is_accepted_on_purchase_order_lines(self, env):
        line = _po_line(env, qty_ordered=4, line_number=3)
        record = _po_record(env, lines=[line])

        res = env.post(INGEST_PO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text
        assert "lines.0.line_number" not in entry.get("errors", {})

    def test_without_line_number_step3_falls_back_to_payload_order(self, env):
        number = f"{MARKER}-SO-{uuid.uuid4().hex[:8]}"
        header = _seed_so_header(env, number=number)
        row_t0 = _seed_line(
            env,
            SalesOrderLine,
            header_id=header.id,
            fk_field="sales_order_id",
            delivered_field="qty_delivered",
            product_ref=env.product_ref,
            qty_ordered=5,
            delivered=Decimal("0"),  # outstanding 5
            created_at=T0,
        )
        row_t1 = _seed_line(
            env,
            SalesOrderLine,
            header_id=header.id,
            fk_field="sales_order_id",
            delivered_field="qty_delivered",
            product_ref=env.product_ref,
            qty_ordered=8,
            delivered=Decimal("0"),  # outstanding 8
            created_at=T1,
        )
        # No `line_number` on either line - the payload's own list order is the
        # only position signal available.
        line_1 = _so_line(env, product_ref=env.product_ref, qty_ordered=3)
        line_2 = _so_line(env, product_ref=env.product_ref, qty_ordered=4)
        record = _so_record(env, number=number, lines=[line_1, line_2])

        res = env.post(INGEST_SO, [record])

        assert res.status_code == 200, res.text
        lines = {l["source_ref"]: l for l in env.so_lines(header.id)}
        assert str(lines[line_1["source_ref"]]["id"]) == str(row_t0.id)
        assert str(lines[line_2["source_ref"]]["id"]) == str(row_t1.id)
