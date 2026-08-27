"""F12 / R19 - a set on the loading plan, reading its DRIVER member's figures.

TEST-FIRST: `container_request_service.build` knows nothing about sets when this file is
written, so every test here is expected to be red until slot B lands.

The supplier's statement names `CWC605-RL`, which is our SET. We book sales orders on its
MEMBERS - the pedestal and the cistern - so the row has to show somebody's numbers, and R19
rules that it shows ONE member's: the driver, the member in the fewest sets.

Shared parts are ignored on purpose. `CWCY605` sits in six sets, so a minimum across members
would understate every one of them and a sum would count that cistern six times. The
pedestal belongs to one set, so its need, its stock and its dates describe this set and
nothing else.

Every figure the grid already shows travels under its EXISTING field name, so the frontend
needs no new columns: what is added is the set's own identity (`row_kind`, `product_set_id`,
`set_code`) and the driver's code, so the cell can say whose numbers these are.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.product_set import ProductSet, ProductSetMember
from app.models.scm import SupplierInventory
from app.services.scm import container_request_service as svc
from tests._pg_fixture import pg_session
from tests.scm.test_container_request import _on_hand, _so, _warehouse
from tests.scm.test_loading_plan import World

MARKER = "ZZCS"


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture(autouse=True)
def _no_pdf_no_storage(monkeypatch):
    """This suite is about the rows, not WeasyPrint - the same stub S13's own suite uses."""
    from app.services.scm import supplier_notice_service

    monkeypatch.setattr(
        supplier_notice_service, "render_document", lambda html: b"%PDF-1.4 stub"
    )
    monkeypatch.setattr(
        supplier_notice_service,
        "_store",
        lambda data, filename: ("s3", f"exports/test/{filename}"),
    )


def _set(db, w: World, code: str, members: list) -> ProductSet:
    """One of our sets: `members` are `(product key, quantity, sort_order)`."""
    product_set = ProductSet(
        id=_uid(), set_code=f"{MARKER}-{code}-{w.tag}", name=code, is_active=True
    )
    db.add(product_set)
    db.flush()
    for key, quantity, sort_order in members:
        db.add(
            ProductSetMember(
                id=_uid(),
                product_set_id=product_set.id,
                product_id=w.product(key).id,
                quantity=quantity,
                sort_order=sort_order,
            )
        )
    db.flush()
    return product_set


def _set_stock(
    db, w: World, product_set: ProductSet, *, packed: float, unfinished: float = 0, cbm=None
) -> None:
    """A stock row the supplier sent under the SET's code, bound to the set."""
    db.add(
        SupplierInventory(
            id=_uid(),
            supplier_id=w.supplier.id,
            item_code=product_set.set_code,
            product_id=None,
            product_set_id=product_set.id,
            qty_packed=packed,
            qty_unfinished=unfinished,
            cbm_per_unit=cbm,
            as_of=date(2026, 7, 31),
        )
    )
    db.flush()


def _wc(db, w: World, *, shared_sets: int = 5) -> ProductSet:
    """The real shape: a pedestal in one set, a cistern shared across several.

    The extra sets are what make the driver rule bite - without them the two members tie on
    set count and the test would pass on `sort_order` alone, proving nothing about R19.
    """
    product_set = _set(db, w, "CWC605-RL", [("CWCY605", 1, 0), ("CWCX605-RL", 1, 1)])
    for n in range(shared_sets):
        _set(db, w, f"SHARED{n}", [("CWCY605", 1, 0), (f"OTHER{n}", 1, 1)])
    return product_set


def _row_for(rows: list[dict], product_set: ProductSet) -> dict:
    return next(r for r in rows if r.get("product_set_id") == str(product_set.id))


# --------------------------------------------------------------------------------- #
# The set row, and whose numbers it shows (AC-F12.3)
# --------------------------------------------------------------------------------- #


def test_a_set_the_supplier_holds_becomes_a_row_named_by_its_set_code():
    with pg_session() as db:
        w = World(db)
        product_set = _wc(db, w)
        _set_stock(db, w, product_set, packed=40)

        out = svc.build(db, supplier_id=str(w.supplier.id))

        row = _row_for(out["rows"], product_set)
        assert row["row_kind"] == "set"
        assert row["item_code"] == product_set.set_code
        assert row["holding_qty"] == 40.0


def test_the_set_row_reads_the_driver_members_need_never_the_shared_parts():
    """The worked example. `CWC605-RL` reads `CWCX605-RL`'s figures, never `CWCY605`'s."""
    with pg_session() as db:
        w = World(db)
        product_set = _wc(db, w)
        _set_stock(db, w, product_set, packed=40)
        _so(db, w, "CWCX605-RL", 100)
        _so(db, w, "CWCY605", 900)

        out = svc.build(db, supplier_id=str(w.supplier.id))

        row = _row_for(out["rows"], product_set)
        assert row["driver_product_id"] == str(w.product("CWCX605-RL").id)
        assert row["driver_item_code"] == w.product("CWCX605-RL").product_code
        assert row["open_so_need"] == 100.0
        assert row["retail_qty"] == 100.0


def test_the_set_row_carries_the_drivers_earliest_need_by_and_so_count():
    with pg_session() as db:
        w = World(db)
        product_set = _wc(db, w)
        _set_stock(db, w, product_set, packed=40)
        _so(db, w, "CWCX605-RL", 60, required_date=date(2026, 9, 30))
        _so(db, w, "CWCX605-RL", 40, required_date=date(2026, 12, 31))

        row = _row_for(svc.build(db, supplier_id=str(w.supplier.id))["rows"], product_set)

        assert row["earliest_required_date"] == "2026-09-30"
        assert row["so_count"] == 2


def test_the_drills_behind_a_set_row_are_the_drivers_own_sales_order_lines():
    """The Open SOs cell drills into `lines` keyed on the row's `product_id`, so the driver's
    id has to travel there too or the cell opens an empty list."""
    with pg_session() as db:
        w = World(db)
        product_set = _wc(db, w)
        _set_stock(db, w, product_set, packed=40)
        _so(db, w, "CWCX605-RL", 100)

        out = svc.build(db, supplier_id=str(w.supplier.id), include_lines=True)

        row = _row_for(out["rows"], product_set)
        assert row["product_id"] == str(w.product("CWCX605-RL").id)
        behind = [l for l in out["lines"] if l["product_id"] == row["product_id"]]
        assert sum(l["qty"] for l in behind) == row["open_so_need"]


# --------------------------------------------------------------------------------- #
# The driver does not appear twice (AC-F12.4)
# --------------------------------------------------------------------------------- #


def test_the_driver_product_gets_no_row_of_its_own_beside_the_set():
    with pg_session() as db:
        w = World(db)
        product_set = _wc(db, w)
        _set_stock(db, w, product_set, packed=40)
        _so(db, w, "CWCX605-RL", 100)

        rows = svc.build(db, supplier_id=str(w.supplier.id))["rows"]

        driver_code = w.product("CWCX605-RL").product_code
        assert [r for r in rows if r["item_code"] == driver_code] == []
        assert len([r for r in rows if r.get("product_set_id") == str(product_set.id)]) == 1


def test_a_non_driver_member_still_gets_its_own_row_when_the_supplier_holds_it():
    """The cistern is stock in its own right - it is sold on its own - so a statement naming
    both the set and the cistern names two things to ask about."""
    with pg_session() as db:
        w = World(db)
        product_set = _wc(db, w)
        _set_stock(db, w, product_set, packed=40)
        w.stock("CWCY605", packed=12)
        _so(db, w, "CWCY605", 30)

        rows = svc.build(db, supplier_id=str(w.supplier.id))["rows"]

        cistern = next(
            r for r in rows if r["item_code"] == w.product("CWCY605").product_code
        )
        assert cistern["row_kind"] == "product"
        assert cistern["open_so_need"] == 30.0


# --------------------------------------------------------------------------------- #
# What to ask for (AC-F12.5)
# --------------------------------------------------------------------------------- #


def test_the_suggestion_nets_the_drivers_site_pool_stock_off_the_drivers_need():
    with pg_session() as db:
        w = World(db)
        product_set = _wc(db, w)
        _set_stock(db, w, product_set, packed=400)
        _so(db, w, "CWCX605-RL", 100)
        _on_hand(db, w, "CWCX605-RL", _warehouse(db), 30)

        row = _row_for(svc.build(db, supplier_id=str(w.supplier.id))["rows"], product_set)

        assert row["on_hand"] == 30.0
        assert row["suggested_qty"] == 70.0


def test_a_set_held_with_nothing_owed_is_still_a_row_but_unranked():
    with pg_session() as db:
        w = World(db)
        product_set = _wc(db, w)
        _set_stock(db, w, product_set, packed=40)

        row = _row_for(svc.build(db, supplier_id=str(w.supplier.id))["rows"], product_set)

        assert row["has_demand"] is False
        assert row["rank"] is None
        assert row["suggested_qty"] == 0.0


def test_a_set_with_no_members_yet_is_left_out_rather_than_shown_with_nobodys_numbers():
    with pg_session() as db:
        w = World(db)
        empty = _set(db, w, "EMPTY", [])
        _set_stock(db, w, empty, packed=40)

        rows = svc.build(db, supplier_id=str(w.supplier.id))["rows"]

        assert [r for r in rows if r.get("product_set_id") == str(empty.id)] == []


# --------------------------------------------------------------------------------- #
# The stand-in proforma states holdings the same way (Q2)
# --------------------------------------------------------------------------------- #


def test_a_set_line_on_the_stand_in_proforma_becomes_a_set_row():
    from app.models.scm import ProformaInvoice, ProformaInvoiceLine

    with pg_session() as db:
        w = World(db)
        product_set = _wc(db, w)
        _so(db, w, "CWCX605-RL", 100)
        pi = ProformaInvoice(
            id=_uid(),
            supplier_id=w.supplier.id,
            pi_number=f"{MARKER}-PI-{uuid.uuid4().hex[:8]}",
            invoice_date=date(2026, 7, 31),
            currency="CNY",
            line_count=1,
            status="current",
        )
        db.add(pi)
        db.flush()
        db.add(
            ProformaInvoiceLine(
                id=_uid(),
                invoice_id=pi.id,
                line_no=1,
                item_code=product_set.set_code,
                product_id=None,
                product_set_id=product_set.id,
                qty=55,
            )
        )
        db.flush()

        row = _row_for(svc.build(db, supplier_id=str(w.supplier.id))["rows"], product_set)

        assert row["holding_source"] == "proforma"
        assert row["holding_qty"] == 55.0
        assert row["open_so_need"] == 100.0


# --------------------------------------------------------------------------------- #
# Sending it (AC-F12.6)
# --------------------------------------------------------------------------------- #


def test_a_set_line_is_sent_under_the_set_code_with_no_product_behind_it():
    from app.models.scm import LoadingPlan
    from app.models.supplier_notice import SupplierNoticeLine

    with pg_session() as db:
        w = World(db)
        product_set = _wc(db, w)
        _set_stock(db, w, product_set, packed=40)
        # The send belongs to a PLAN since part 4 (R2); the supplier is read off the row.
        plan = LoadingPlan(
            id=str(uuid.uuid4()),
            supplier_id=str(w.supplier.id),
            status="planning",
            document_kind="stock_list",
            line_edits={},
        )
        db.add(plan)
        db.flush()

        out = svc.send(
            db,
            plan_id=str(plan.id),
            lines=[{"product_set_id": str(product_set.id), "qty": 40}],
            actor="Ms Tee",
            # A send names at least one recipient since R9 (AC-C2).
            recipients=["sets@example.test"],
        )

        written = (
            db.query(SupplierNoticeLine)
            .filter(SupplierNoticeLine.notice_id.in_([n["id"] for n in out["notices"]]))
            .all()
        )
        assert written, "the send wrote no lines at all"
        assert {l.item_code for l in written} == {product_set.set_code}
        assert {l.product_id for l in written} == {None}
