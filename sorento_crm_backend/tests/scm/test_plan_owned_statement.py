"""S6 - a loading plan owns its statement.

`PLAN-scm-loading-plan-feedback-2sep.md` section 3.6, AC-F1 to AC-F7, AC-C7, AC-E0, AC-G1.

The defect this closes was measured on prod: a ROYAL MIRROR plan started with NO file showed
79 unknown supplier codes and a full set of holdings, because both reads were supplier-wide
and the supplier carried a 115-row stock list somebody had uploaded from a different plan. The
plan said "No file" while quietly running on that snapshot. The same shape hit the proforma
side from the other direction: one uploaded sheet holds five stacked invoice blocks, and the
build read exactly ONE of them, chosen by `ORDER BY invoice_date DESC, created_at DESC, id
DESC LIMIT 1` - which on five rows sharing a date and a timestamp is decided by the UUID.

So the rows an upload writes are STAMPED with the plan they were uploaded into, and every
read on the record - holdings, unknown codes, the document label - reads the plan's own rows.

TEST-FIRST: migration 454, `loading_plan_id` on `scm.supplier_inventory` /
`scm.proforma_invoice`, the `loading_plan_id` arguments on both applies, the plan legs in
`container_request_service.build`, `_document_label` off the plan's rows, `statement_as_of`
and the plan-scoped alias reads do not exist when this file is written. Red first, as a
missing column or a missing keyword, never as a wrong number quietly accepted.

Postgres via `pg_session` (rolled back at teardown), every chain seeded here under the `ZZPO`
marker - CI's database has no data and nothing may be borrowed from an existing table.
"""
from __future__ import annotations

import uuid
from datetime import date
from io import BytesIO
from pathlib import Path

import pytest
from sqlalchemy import text

from app.models.procurement import ProductSupplier, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.product_set import ProductSet, ProductSetMember
from app.models.scm import ProformaInvoice, ProformaInvoiceLine, SupplierInventory
from app.services.error_handler import AppException
from app.services.scm import container_request_service as build_svc
from app.services.scm import loading_plan_service as plan_svc
from app.services.scm import proforma_invoice_service as pi_svc
from app.services.scm import supplier_code_alias_service as alias_svc
from app.services.scm import supplier_inventory_service as stock_svc
from tests._pg_fixture import pg_session

#: `record_dict`'s "look this up yourself" sentinel.
_UNSET_ = plan_svc._UNSET

MARKER = "ZZPO"

#: The captain's own file: ONE sheet, five stacked invoice blocks (header rows 8, 18, 29, 57,
#: 70), 30 lines, a CHAOZHOU JINBAICHUAN letterhead, and SRTWC8354-SH-250 in TWO of the blocks
#: at 60 and 40. The golden numbers below are read off it, never typed from memory.
FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "scm" / "2026-7-31_SORENTO_preload_list.xlsx"
)


def _uid() -> str:
    return str(uuid.uuid4())


class World:
    """One supplier and whatever products a test names, all marker-prefixed."""

    def __init__(self, db):
        self.db = db
        tag = uuid.uuid4().hex[:8].upper()
        self.tag = tag
        self.cat = ProductCategory(
            id=_uid(),
            category_code=f"{MARKER}-CAT-{tag}",
            category_name=f"{MARKER} category",
        )
        self.uom = UnitOfMeasure(id=_uid(), uom_code=f"{MARKER}-U-{tag}"[:20], uom_name="pcs")
        db.add_all([self.cat, self.uom])
        db.flush()
        self.supplier = self.new_supplier("S")
        self.products: dict[str, Product] = {}

    def new_supplier(self, stem: str) -> Supplier:
        s = Supplier(
            id=_uid(),
            supplier_code=f"{MARKER}-{stem}-{self.tag}",
            supplier_name=f"{MARKER} {stem} {self.tag}",
            is_active=True,
        )
        self.db.add(s)
        self.db.flush()
        return s

    def product(self, key: str, *, code: str | None = None) -> Product:
        if key not in self.products:
            p = Product(
                id=_uid(),
                product_code=code or f"{MARKER}-{key}-{self.tag}",
                product_name=key,
                category_id=self.cat.id,
                base_uom_id=self.uom.id,
                list_price=0,
                is_active=True,
                is_discontinued=False,
            )
            self.db.add(p)
            self.db.flush()
            self.products[key] = p
        return self.products[key]

    def code(self, key: str) -> str:
        return self.product(key).product_code

    def link(self, key: str, supplier: Supplier | None = None) -> None:
        """We buy this product from this supplier - the universe's first leg."""
        self.db.add(
            ProductSupplier(
                id=_uid(),
                product_id=self.product(key).id,
                supplier_id=(supplier or self.supplier).id,
                standard_lead_time_days=30,
            )
        )
        self.db.flush()

    def plan(self, kind: str, supplier: Supplier | None = None):
        return plan_svc.create_record(
            self.db,
            supplier_id=str((supplier or self.supplier).id),
            plan_horizon_date=None,
            document_kind=kind,
            source_attachment_id=None,
            actor="Ms Tee",
        )

    def stock_row(
        self,
        key: str,
        *,
        packed: float,
        plan_id: str | None,
        as_of: date = date(2026, 7, 31),
        item_code: str | None = None,
        bound: bool = True,
    ) -> SupplierInventory:
        row = SupplierInventory(
            id=_uid(),
            supplier_id=self.supplier.id,
            item_code=item_code or self.code(key),
            product_id=self.product(key).id if bound else None,
            qty_packed=packed,
            qty_unfinished=0,
            as_of=as_of,
            loading_plan_id=plan_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def invoice(
        self,
        lines: list[tuple[str, float]],
        *,
        plan_id: str | None,
        invoice_date: date = date(2026, 7, 31),
        block: int = 1,
        source_ref: str = "preload.xlsx",
        status: str = "current",
        revision_of_id: str | None = None,
    ) -> ProformaInvoice:
        pi = ProformaInvoice(
            id=_uid(),
            supplier_id=self.supplier.id,
            pi_number=f"{MARKER}-PI-{uuid.uuid4().hex[:8]}",
            invoice_date=invoice_date,
            currency="CNY",
            line_count=len(lines),
            block_index=block,
            source_ref=source_ref,
            status=status,
            revision_of_id=revision_of_id,
            loading_plan_id=plan_id,
        )
        self.db.add(pi)
        self.db.flush()
        for i, (key, qty) in enumerate(lines, start=1):
            self.db.add(
                ProformaInvoiceLine(
                    id=_uid(),
                    invoice_id=pi.id,
                    line_no=i,
                    item_code=self.code(key),
                    product_id=self.product(key).id,
                    qty=qty,
                )
            )
        self.db.flush()
        return pi


def _retail_need(db, w: "World", key: str, qty: float) -> None:
    """Open retail demand on a product - what turns a candidate into a ranked row."""
    from app.models.order import SalesOrder, SalesOrderLine

    so = SalesOrder(
        id=_uid(),
        so_number=f"{MARKER}-SO-{uuid.uuid4().hex[:8]}",
        status="open",
        demand_class="retail",
        order_date=date(2026, 1, 1),
    )
    db.add(so)
    db.flush()
    db.add(
        SalesOrderLine(
            id=_uid(),
            sales_order_id=so.id,
            product_id=w.product(key).id,
            qty_ordered=qty,
            qty_delivered=0,
            line_status="open",
            purchasing_status="not_reviewed",
        )
    )
    db.flush()


#: The header the stock-list reader resolves, verbatim from `test_supplier_inventory_service`
#: so the two suites cannot come to disagree about what a readable file looks like.
_STOCK_HEADER = ["型号", "品名", "包装好库存", "空瓷", "体积(cbm)", "备注"]


def _stock_workbook(rows: list[tuple[str, float]]) -> bytes:
    """The supplier's stock list, in the shape the reader binds: model number + packed."""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(list(_STOCK_HEADER))
    for code, qty in rows:
        ws.append([code, code, qty, 0, None, None])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _remember(db, w: "World", supplier_code: str, key: str) -> None:
    """"This code of theirs is that product of ours" - rung 0 of the matching ladder."""
    alias_svc.create(
        db,
        supplier_id=str(w.supplier.id),
        supplier_code=supplier_code,
        product_id=str(w.product(key).id),
        actor="Ms Tee",
    )


def _row(result: dict, code: str) -> dict:
    return next(r for r in result["rows"] if r["item_code"] == code)


def _codes(rows: list[dict]) -> list[str]:
    return sorted(r["item_code"] for r in rows)


# --------------------------------------------------------------------------- #
# AC-F1 - the migration
# --------------------------------------------------------------------------- #


def test_both_statement_tables_carry_the_plan_they_belong_to():
    """AC-F1: `loading_plan_id` on the stock snapshot AND on the invoice, nullable, indexed.

    Nullable because every row that predates 454 is the legacy supplier-wide snapshot and has
    no plan to name; the reads below are what decide what a NULL means, not a backfill that
    would have to invent one.
    """
    with pg_session() as db:
        for table in ("supplier_inventory", "proforma_invoice"):
            column = db.execute(
                text(
                    "SELECT data_type, is_nullable FROM information_schema.columns "
                    "WHERE table_schema = 'scm' AND table_name = :t "
                    "AND column_name = 'loading_plan_id'"
                ),
                {"t": table},
            ).first()
            assert column is not None, f"scm.{table}.loading_plan_id is missing"
            assert column[0] == "uuid"
            assert column[1] == "YES"


def test_the_snapshot_identity_is_keyed_on_the_plan_too():
    """AC-F1: a plan's rows and a standalone upload's rows coexist for one item code.

    Without re-keying, the second plan to upload the same model number for one supplier
    collides with the first on `uq_scm_supplier_inventory_identity` and the upload fails.
    """
    with pg_session() as db:
        definition = db.execute(
            text(
                "SELECT indexdef FROM pg_indexes WHERE schemaname = 'scm' "
                "AND indexname = 'uq_scm_supplier_inventory_identity'"
            )
        ).scalar()
        assert definition is not None
        assert "loading_plan_id" in definition

        w = World(db)
        one, two = w.plan("stock_list"), w.plan("stock_list")
        w.stock_row("A", packed=10, plan_id=str(one.id))
        w.stock_row("A", packed=20, plan_id=str(two.id))
        w.stock_row("A", packed=30, plan_id=None)

        held = (
            db.query(SupplierInventory)
            .filter(SupplierInventory.supplier_id == w.supplier.id)
            .all()
        )
        assert sorted(float(r.qty_packed) for r in held) == [10.0, 20.0, 30.0]


# --------------------------------------------------------------------------- #
# AC-F3 - the applies stamp what they write
# --------------------------------------------------------------------------- #


def test_a_stock_list_applied_into_a_plan_replaces_only_that_plans_rows():
    with pg_session() as db:
        w = World(db)
        first, second = w.plan("stock_list"), w.plan("stock_list")
        w.stock_row("A", packed=10, plan_id=str(first.id))
        w.stock_row("A", packed=99, plan_id=None)  # the legacy supplier-wide snapshot

        out = stock_svc.apply(
            db,
            _stock_workbook([(w.code("B"), 5)]),
            supplier_id=str(w.supplier.id),
            loading_plan_id=str(second.id),
        )

        assert out["rows_written"] == 1
        # Its own rows, and nobody else's: the first plan and the standalone snapshot stand.
        assert out["rows_replaced"] == 0
        by_plan: dict[str | None, list[float]] = {}
        for r in (
            db.query(SupplierInventory)
            .filter(SupplierInventory.supplier_id == w.supplier.id)
            .all()
        ):
            key = str(r.loading_plan_id) if r.loading_plan_id else None
            by_plan.setdefault(key, []).append(float(r.qty_packed))
        assert by_plan[str(first.id)] == [10.0]
        assert by_plan[None] == [99.0]
        assert by_plan[str(second.id)] == [5.0]


def test_re_uploading_into_the_same_plan_is_still_a_replace():
    with pg_session() as db:
        w = World(db)
        plan = w.plan("stock_list")
        stock_svc.apply(
            db,
            _stock_workbook([(w.code("A"), 10)]),
            supplier_id=str(w.supplier.id),
            loading_plan_id=str(plan.id),
        )

        out = stock_svc.apply(
            db,
            _stock_workbook([(w.code("B"), 7)]),
            supplier_id=str(w.supplier.id),
            loading_plan_id=str(plan.id),
        )

        assert out["rows_replaced"] == 1
        rows = (
            db.query(SupplierInventory)
            .filter(SupplierInventory.loading_plan_id == str(plan.id))
            .all()
        )
        assert [r.item_code for r in rows] == [w.code("B")]


def test_the_standalone_upload_page_still_replaces_the_supplier_wide_snapshot():
    """AC-F3: no plan id, no change of behaviour. The stock-list page is not a plan."""
    with pg_session() as db:
        w = World(db)
        w.stock_row("A", packed=10, plan_id=None)

        out = stock_svc.apply(
            db, _stock_workbook([(w.code("B"), 5)]), supplier_id=str(w.supplier.id)
        )

        assert out["rows_replaced"] == 1
        rows = (
            db.query(SupplierInventory)
            .filter(SupplierInventory.supplier_id == w.supplier.id)
            .all()
        )
        assert [r.item_code for r in rows] == [w.code("B")]
        assert rows[0].loading_plan_id is None


def test_a_proforma_applied_into_a_plan_stamps_every_invoice_it_writes():
    with pg_session() as db:
        w = World(db)
        plan = w.plan("proforma")

        out = pi_svc.apply(
            db,
            FIXTURE.read_bytes(),
            supplier_id=str(w.supplier.id),
            source_ref=FIXTURE.name,
            loading_plan_id=str(plan.id),
        )

        assert out["documents_created"] == 5
        stamped = (
            db.query(ProformaInvoice)
            .filter(ProformaInvoice.loading_plan_id == str(plan.id))
            .all()
        )
        assert len(stamped) == 5


def test_a_revision_written_into_a_plan_is_stamped_with_it():
    """AC-F3: "every created OR revised invoice". A resend lands on the plan that took it."""
    with pg_session() as db:
        w = World(db)
        first, second = w.plan("proforma"), w.plan("proforma")
        data = _preloading_bytes()
        out = pi_svc.apply(
            db,
            data,
            supplier_id=str(w.supplier.id),
            source_ref="preload.xlsx",
            loading_plan_id=str(first.id),
        )
        prior = out["results"][0]["invoice_id"]

        again = pi_svc.apply(
            db,
            data,
            supplier_id=str(w.supplier.id),
            source_ref="preload.xlsx",
            revision_of={"1": prior},
            loading_plan_id=str(second.id),
        )

        revision = db.query(ProformaInvoice).get(again["results"][0]["invoice_id"])
        assert str(revision.revision_of_id) == prior
        assert str(revision.loading_plan_id) == str(second.id)
        # The superseded original stays where it was: the first plan keeps its own reading.
        assert str(db.query(ProformaInvoice).get(prior).loading_plan_id) == str(first.id)


def test_a_proforma_apply_refuses_a_plan_belonging_to_another_supplier():
    """422 `invoice_supplier_mismatch`: stamping it would bind one supplier's invoices to
    another supplier's plan, and every read on that plan would then be wrong."""
    with pg_session() as db:
        w = World(db)
        other = w.new_supplier("OTHER")
        theirs = w.plan("proforma", supplier=other)

        with pytest.raises(AppException) as exc:
            pi_svc.apply(
                db,
                _preloading_bytes(),
                supplier_id=str(w.supplier.id),
                source_ref="preload.xlsx",
                loading_plan_id=str(theirs.id),
            )

        assert exc.value.status_code == 422
        assert exc.value.detail["detail"] == "invoice_supplier_mismatch"


# --------------------------------------------------------------------------- #
# AC-F4 / AC-F6 - the build reads the plan's own rows
# --------------------------------------------------------------------------- #


def test_the_build_reads_the_plans_own_stock_rows_not_the_suppliers_latest():
    """AC-F6, and it retires p4 AC-A17: a newer list from a NEW plan used to move this one."""
    with pg_session() as db:
        w = World(db)
        mine = w.plan("stock_list")
        theirs = w.plan("stock_list")
        w.stock_row("A", packed=40, plan_id=str(mine.id), as_of=date(2026, 7, 31))
        w.stock_row("A", packed=900, plan_id=str(theirs.id), as_of=date(2026, 8, 28))

        out = build_svc.build(db, supplier_id=str(w.supplier.id), plan=mine)

        row = _row(out, w.code("A"))
        assert row["holding_source"] == "stock_list"
        assert row["holding_qty"] == 40.0
        assert row["holding_as_of"] == "2026-07-31"
        assert row["holding_blocks"] == 0
        assert row["blocks"] == []


def test_the_build_sums_every_invoice_bound_to_the_plan_and_names_the_split():
    """AC-F4: ALL bound invoices, summed per product, with the per-block split for the drill.

    The old rule took ONE invoice - `LIMIT 1` over five rows sharing an invoice date and a
    transaction timestamp, so the UUID decided which block a plan showed.
    """
    with pg_session() as db:
        w = World(db)
        plan = w.plan("proforma")
        four = w.invoice([("A", 60)], plan_id=str(plan.id), block=4)
        five = w.invoice([("A", 40), ("B", 5)], plan_id=str(plan.id), block=5)
        # Another plan's invoice for the same supplier and product: not this plan's business.
        w.invoice([("A", 999)], plan_id=str(w.plan("proforma").id), block=1)

        out = build_svc.build(db, supplier_id=str(w.supplier.id), plan=plan)

        row = _row(out, w.code("A"))
        assert row["holding_source"] == "proforma"
        assert row["holding_qty"] == 100.0
        assert row["holding_blocks"] == 2
        assert sorted((b["block_index"], b["qty"]) for b in row["blocks"]) == [
            (4, 60.0),
            (5, 40.0),
        ]
        assert {b["pi_number"] for b in row["blocks"]} == {four.pi_number, five.pi_number}
        assert _row(out, w.code("B"))["holding_qty"] == 5.0


def test_a_revision_inside_one_plan_is_read_once_at_its_current_shape():
    """AC-F4's "current revision": a plan holding both an invoice and its own R2 counts the
    R2 only, or the container is asked for twice over."""
    with pg_session() as db:
        w = World(db)
        plan = w.plan("proforma")
        original = w.invoice([("A", 60)], plan_id=str(plan.id), block=1, status="superseded")
        w.invoice(
            [("A", 80)],
            plan_id=str(plan.id),
            block=1,
            revision_of_id=str(original.id),
        )

        out = build_svc.build(db, supplier_id=str(w.supplier.id), plan=plan)

        assert _row(out, w.code("A"))["holding_qty"] == 80.0
        assert _row(out, w.code("A"))["holding_blocks"] == 1


def test_a_no_file_plan_reads_no_statement_at_all():
    """AC-F6 second half - the ROYAL MIRROR case, from the holdings side."""
    with pg_session() as db:
        w = World(db)
        w.link("A")
        _retail_need(db, w, "A", 20)
        # 500 packed, on file for this supplier, under somebody else's plan.
        w.stock_row("A", packed=500, plan_id=str(w.plan("stock_list").id))

        out = build_svc.build(db, supplier_id=str(w.supplier.id), plan=w.plan("none"))

        row = _row(out, w.code("A"))
        assert row["holding_source"] == "none"
        assert row["holding_qty"] is None
        assert row["qty_packed"] == 0.0
        assert row["holding_blocks"] == 0


def test_a_no_file_plans_universe_is_links_aliases_and_drivers():
    """AC-E0: membership and placement are separate questions.

    A plan with no statement still has a universe - what we buy from this supplier, and what
    we have ever ruled one of their codes to mean. A product with open demand and neither
    membership belongs to somebody else's supplier and is not asked of this one.

    S4/AC-D3 widens the alias leg to SETS: a code ruled onto one of our sets joins through the
    set's DRIVER, exactly as a set named by an actual statement would - the driver's own row
    is what "membership" resolves to when nothing on file has holdings for the set yet.
    """
    with pg_session() as db:
        w = World(db)
        w.link("LINKED")
        alias_svc.create(
            db,
            supplier_id=str(w.supplier.id),
            supplier_code=f"{MARKER}-THEIRS",
            product_id=str(w.product("ALIASED").id),
            actor="Ms Tee",
        )
        driver = w.product("SET-DRIVER")
        product_set = ProductSet(
            id=_uid(), set_code=f"{MARKER}-SET-{w.tag}", name="Aliased set", is_active=True
        )
        db.add(product_set)
        db.flush()
        db.add(
            ProductSetMember(
                id=_uid(), product_set_id=product_set.id, product_id=driver.id,
                quantity=1, sort_order=0,
            )
        )
        db.flush()
        alias_svc.create(
            db,
            supplier_id=str(w.supplier.id),
            supplier_code=f"{MARKER}-SETCODE",
            product_set_id=str(product_set.id),
            actor="Ms Tee",
        )
        # Owed to a customer, and this supplier makes none of it - somebody else's product.
        for key in ("LINKED", "ALIASED", "STRANGER", "SET-DRIVER"):
            _retail_need(db, w, key, 10)

        out = build_svc.build(db, supplier_id=str(w.supplier.id), plan=w.plan("none"))

        codes = _codes(out["rows"])
        assert w.code("LINKED") in codes
        assert w.code("ALIASED") in codes
        assert w.code("SET-DRIVER") in codes
        assert w.code("STRANGER") not in codes


def test_a_legacy_plan_with_nothing_stamped_still_reads_the_supplier_wide_snapshot():
    """AC-F4's last sentence. Every plan open when 454 lands has no stamped row of its own,
    and blanking those screens would be a worse answer than the drift they already carry."""
    with pg_session() as db:
        w = World(db)
        legacy = w.plan("stock_list")
        w.stock_row("A", packed=12, plan_id=None)

        out = build_svc.build(db, supplier_id=str(w.supplier.id), plan=legacy)

        assert _row(out, w.code("A"))["holding_qty"] == 12.0


# --------------------------------------------------------------------------- #
# AC-F5 - the golden set, off the captain's own file
# --------------------------------------------------------------------------- #


def test_the_five_block_fixture_lands_on_one_plan_and_sums_across_its_blocks():
    """AC-F5. SRTWC8354-SH-250 is in block 4 at 60 and block 5 at 40; the plan says 100."""
    with pg_session() as db:
        w = World(db)
        # SRTWC8354-SH-250 is bound to OUR code through the alias ladder's rung 0, which is
        # how a real upload binds it. The other 29 codes are deliberately left to resolve or
        # not on their own: several of them exist in the prod-copy database this suite runs
        # on and NOT in CI's empty one, so a test that pinned them would assert one thing
        # locally and another in CI. This code exists in neither, so the alias is the only
        # way it can bind and the number below means the same thing everywhere.
        _remember(db, w, "SRTWC8354-SH-250", "TOILET")
        plan = w.plan("proforma")

        out = pi_svc.apply(
            db,
            FIXTURE.read_bytes(),
            supplier_id=str(w.supplier.id),
            source_ref=FIXTURE.name,
            loading_plan_id=str(plan.id),
        )
        assert out["documents_created"] == 5
        assert sum(r["lines"] for r in out["results"]) == 30

        # The file's own two figures, read off what was written rather than typed here.
        written = sorted(
            float(line.qty)
            for line in db.query(ProformaInvoiceLine)
            .join(
                ProformaInvoice, ProformaInvoice.id == ProformaInvoiceLine.invoice_id
            )
            .filter(
                ProformaInvoice.loading_plan_id == str(plan.id),
                ProformaInvoiceLine.item_code == "SRTWC8354-SH-250",
            )
            .all()
        )
        assert written == [40.0, 60.0]

        built = build_svc.build(db, supplier_id=str(w.supplier.id), plan=plan)

        toilet = _row(built, w.code("TOILET"))
        assert toilet["holding_qty"] == 100.0
        assert sorted((b["block_index"], b["qty"]) for b in toilet["blocks"]) == [
            (4, 60.0),
            (5, 40.0),
        ]
        # Every row on this plan reports the same five-block statement it was read from.
        assert toilet["holding_blocks"] == 5


def test_the_same_file_uploaded_again_leaves_the_first_plan_reading_its_own():
    """AC-F5's second half: a second plan binds the R2 invoices, the first keeps its own."""
    with pg_session() as db:
        w = World(db)
        _remember(db, w, "SRTWC8354-SH-250", "TOILET")
        data = FIXTURE.read_bytes()
        first = w.plan("proforma")
        out = pi_svc.apply(
            db,
            data,
            supplier_id=str(w.supplier.id),
            source_ref=FIXTURE.name,
            loading_plan_id=str(first.id),
        )
        revisions = {str(r["index"]): r["invoice_id"] for r in out["results"]}

        second = w.plan("proforma")
        pi_svc.apply(
            db,
            data,
            supplier_id=str(w.supplier.id),
            source_ref=FIXTURE.name,
            revision_of=revisions,
            loading_plan_id=str(second.id),
        )

        for plan in (first, second):
            built = build_svc.build(db, supplier_id=str(w.supplier.id), plan=plan)
            assert _row(built, w.code("TOILET"))["holding_qty"] == 100.0


# --------------------------------------------------------------------------- #
# AC-F7 / AC-G1 - the record names its own statement
# --------------------------------------------------------------------------- #


def test_the_document_label_is_read_off_the_plans_own_rows():
    with pg_session() as db:
        w = World(db)

        none_plan = w.plan("none")
        assert plan_svc.record_dict(db, none_plan)["document_label"] == "No file"
        assert plan_svc.record_dict(db, none_plan)["statement_as_of"] is None

        stock_plan = w.plan("stock_list")
        w.stock_row("A", packed=1, plan_id=str(stock_plan.id), as_of=date(2026, 8, 28))
        stock = plan_svc.record_dict(db, stock_plan)
        assert stock["document_label"] == "Stock list 28/08/2026"
        assert stock["statement_as_of"] == "2026-08-28"

        one_pi = w.plan("proforma")
        invoice = w.invoice([("A", 1)], plan_id=str(one_pi.id), block=1)
        single = plan_svc.record_dict(db, one_pi)
        assert single["document_label"] == f"Proforma invoice {invoice.pi_number}"
        assert single["statement_as_of"] == "2026-07-31"

        many = w.plan("proforma")
        for block in (1, 2, 3):
            w.invoice(
                [("A", 1)],
                plan_id=str(many.id),
                block=block,
                source_ref="2026-7-31 SORENTO.xlsx",
            )
        assert (
            plan_svc.record_dict(db, many)["document_label"]
            == "Proforma invoice 2026-7-31 SORENTO · 3 blocks"
        )


def test_the_label_reads_only_this_companys_rows():
    """SF-6: `_plan_statements` is raw SQL over two company-scoped tables.

    The ORM's isolation filter runs on ORM execution only, so a raw SELECT sees every
    company's rows. Both statement tables carry `company_id`, and a plan named by another
    company's snapshot would put that company's date on this company's record.
    """
    from app.models.base import set_company_scope
    from app.models.company import Company

    with pg_session() as db:
        set_company_scope(db, None)
        mine = Company(id=_uid(), code=f"{MARKER}A{uuid.uuid4().hex[:6]}".upper()[:20],
                       name=f"{MARKER} company A")
        theirs = Company(id=_uid(), code=f"{MARKER}B{uuid.uuid4().hex[:6]}".upper()[:20],
                         name=f"{MARKER} company B")
        db.add_all([mine, theirs])
        db.flush()

        w = World(db)
        plan = w.plan("stock_list")
        plan.company_id = str(mine.id)
        row = w.stock_row("A", packed=1, plan_id=str(plan.id), as_of=date(2026, 8, 28))
        # Stamped to the OTHER company - the only shape in which this leaks, and the one the
        # predicate exists to answer.
        row.company_id = str(theirs.id)
        db.flush()

        set_company_scope(db, frozenset({str(mine.id)}))
        record = plan_svc.record_dict(db, plan, supplier_name="ignored", statement=_UNSET_)

        assert record["statement_as_of"] is None
        assert record["document_label"] == "Stock list"


def test_the_label_is_never_re_looked_up_from_the_supplier():
    """AC-F7: the supplier's newest invoice used to name every one of their plans."""
    with pg_session() as db:
        w = World(db)
        mine = w.plan("proforma")
        w.invoice([("A", 1)], plan_id=str(mine.id), invoice_date=date(2026, 7, 31))
        newer = w.invoice(
            [("A", 1)], plan_id=str(w.plan("proforma").id), invoice_date=date(2026, 8, 28)
        )

        label = plan_svc.record_dict(db, mine)["document_label"]

        assert newer.pi_number not in label


# --------------------------------------------------------------------------- #
# AC-C7 - the unknown codes are the plan's own
# --------------------------------------------------------------------------- #


def test_the_unknown_codes_queue_is_scoped_to_the_plan():
    with pg_session() as db:
        w = World(db)
        mine, theirs = w.plan("stock_list"), w.plan("stock_list")
        w.stock_row("A", packed=1, plan_id=str(mine.id), item_code=f"{MARKER}-MINE", bound=False)
        w.stock_row(
            "B", packed=1, plan_id=str(theirs.id), item_code=f"{MARKER}-THEIRS", bound=False
        )

        rows = alias_svc.unmatched_for_plan(db, str(mine.id))

        assert _codes(rows) == [f"{MARKER}-MINE"]


def test_a_no_file_plan_has_no_codes_to_answer_even_when_the_supplier_does():
    """AC-C7's ROYAL MIRROR case, exactly as measured: no file, 79 codes, all somebody
    else's."""
    with pg_session() as db:
        w = World(db)
        other = w.plan("stock_list")
        w.stock_row("A", packed=1, plan_id=str(other.id), item_code=f"{MARKER}-X", bound=False)

        assert alias_svc.unmatched_for_plan(db, str(w.plan("none").id)) == []


def test_a_proforma_plans_queue_reads_its_invoice_lines():
    """AC-C7: "stock list rows OR invoice lines". A proforma plan has no stock rows at all,
    and reading only those left its queue permanently empty."""
    with pg_session() as db:
        w = World(db)
        plan = w.plan("proforma")
        pi = w.invoice([("A", 1)], plan_id=str(plan.id), block=4)
        line = db.query(ProformaInvoiceLine).filter(
            ProformaInvoiceLine.invoice_id == pi.id
        ).one()
        line.product_id = None
        line.item_code = f"{MARKER}-UNKNOWN"
        db.flush()

        assert _codes(alias_svc.unmatched_for_plan(db, str(plan.id))) == [f"{MARKER}-UNKNOWN"]


def test_rematch_binds_only_this_plans_rows():
    with pg_session() as db:
        w = World(db)
        mine, theirs = w.plan("stock_list"), w.plan("stock_list")
        code = w.code("A")
        w.stock_row("A", packed=1, plan_id=str(mine.id), item_code=code, bound=False)
        w.stock_row("A", packed=1, plan_id=str(theirs.id), item_code=code, bound=False)

        out = alias_svc.rematch_for_plan(db, str(mine.id), actor="Ms Tee")

        assert out["inventory_bound"] == 1
        assert out["still_unmatched"] == 0
        bound = (
            db.query(SupplierInventory)
            .filter(
                SupplierInventory.loading_plan_id == str(theirs.id),
                SupplierInventory.product_id.isnot(None),
            )
            .count()
        )
        # The ALIAS the pass wrote is the supplier's and applies everywhere, but the pass
        # itself touched only the plan it was run from.
        assert bound == 0


def _preloading_bytes() -> bytes:
    """A two-block stand-in, for the tests that only need "more than one invoice".

    The committed fixture is used wherever the NUMBERS matter (AC-F5); it is 18 KB and five
    blocks, which is more file than a stamping assertion needs.
    """
    from tests.scm.fixtures.proforma_shapes import preloading_list_workbook

    return preloading_list_workbook({})
