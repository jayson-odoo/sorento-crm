"""`derive_bundles` and everything downstream of `bundled_qty` (PLAN-scm-supplied-with-companions.md
S5). UAC groups B, C, D (D4-D8 only - D1-D3/D9/D10 are the worklist CELL's own rendering, pinned
by a vitest addition to `orderInquiryWorklistColumns.test.tsx`, not a backend concern) and E.

Written test-FIRST: `app/models/product_companion.py` does not exist yet (S3/S4), and neither does
`ProjectOrderInquiryService.derive_bundles` (S5), so importing the model below fails the WHOLE FILE
at collection with one `ImportError` - every case here is red for that reason until S3-S5 land.

Fixture sheet (UAC top): company C (Sorento, the blank schema's default), supplier S1 and S2,
products CKS1050 (host), CKSW015 (companion), X, Y (pair hosts), SC (pair companion). Two rules:
CKSW015 with CKS1050 (ratio 1, supplier NULL - "any"), SC with X + Y (ratio 1, supplier S1). A
THIRD pair - H2/C2 - exists only for B15's fractional ratio, so the shared ratio-1 rules stay
exactly what the UAC table describes.

**Demand.** `scm.committed_v` is a VIEW installed by a migration and does not exist in the blank
scratch schema `_pg_fixture.blank_session` builds (see `test_partial_decision_demand_invariants.py`
for the real-database alternative) - and building it here by hand is unsafe: `schema_translate_map`
rewrites ORM constructs only, so a literal `CREATE VIEW scm.committed_v` executed through this
session would write to the REAL `scm` schema (`_pg_fixture.py`'s own warning). Every case below is
ONE row of ONE product, so the view's per-(product, warehouse) aggregate and the row's own
`GREATEST(qty - linked - bundled_qty, 0)` are the same number - `demand.py`'s CONFIRMED and FORM
legs both reduce to exactly this before P3.4's bundled subtraction, which is the change under
test. `_demand_of` below states that formula directly against the row DB has just derived.

Seeding pattern copied from `test_order_inquiry_links.py`'s `_World` (raw SQL, `blank_session`,
`ProjectOrderInquiryService` for the derivation and the links) and `test_order_inquiry_worklist.py`
(the `_client`/`_row` route-test shape, for D7).
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.base import company_scope
from app.services.project_order_inquiry_service import ProjectOrderInquiryService

# THE red import. Every case below fails to collect until `app/models/product_companion.py`
# exists with these two names (PLAN section 3.1).
from app.models.product_companion import (  # noqa: E402
    ProductCompanionRule,
    ProductCompanionRuleHost,
)

from ._pg_fixture import blank_session

MARKER = "ZZT-BUNDLE"
SOON = date.today() + timedelta(days=30)

#: The `projects` schema THIS session writes to (see `test_order_inquiry_links.py`'s own P).
P = "projects"


def _uid() -> str:
    return str(uuid.uuid4())


def _projects(db) -> str:
    current = db.execute(text("select current_schema()")).scalar()
    return "projects" if current in (None, "public") else f'"{current}_projects"'


class _World:
    def __init__(self, db):
        self.db = db
        self.company_id = db.execute(
            text("select id from companies where code = 'SRT'")
        ).scalar()
        self.svc = ProjectOrderInquiryService(db)
        self._build()

    # -- masters ---------------------------------------------------------------

    def _build(self) -> None:
        db = self.db
        cat, uom = _uid(), _uid()
        db.execute(
            text(
                "INSERT INTO product_categories (id, category_code, category_name) "
                "VALUES (:i, :c, :c)"
            ),
            {"i": cat, "c": f"{MARKER}-CAT"},
        )
        db.execute(
            text("INSERT INTO units_of_measure (id, uom_code, uom_name) VALUES (:i, :c, :c)"),
            {"i": uom, "c": f"{MARKER}-UOM"},
        )
        self._cat, self._uom = cat, uom
        self.products: dict[str, str] = {}
        for code in ("CKS1050", "CKSW015", "X", "Y", "SC", "H2", "C2", "OTHER"):
            self.products[code] = self._product(code)

        self.warehouse = _uid()
        db.execute(
            text(
                "INSERT INTO warehouses (id, company_id, warehouse_code, warehouse_name, "
                "is_active, segment) VALUES (:i, :c, 'WH1', 'WH1', true, 'project')"
            ),
            {"i": self.warehouse, "c": self.company_id},
        )
        self.suppliers: dict[str, str] = {}
        for code in ("S1", "S2"):
            sid = _uid()
            db.execute(
                text(
                    "INSERT INTO suppliers (id, company_id, supplier_code, supplier_name, "
                    "is_active) VALUES (:i, :c, :code, :code, true)"
                ),
                {"i": sid, "c": self.company_id, "code": f"{MARKER}-{code}"},
            )
            self.suppliers[code] = sid

        self.pso, self.inquiry = _uid(), _uid()
        db.execute(
            text(
                "INSERT INTO " + P + ".sales_orders (id, company_id, provisional_ref, "
                "status, created_at, updated_at) "
                "VALUES (:i, :c, :ref, 'published', now(), now())"
            ),
            {"i": self.pso, "c": self.company_id, "ref": f"{MARKER}-PSO"},
        )
        db.execute(
            text(
                "INSERT INTO " + P + ".order_inquiries (id, company_id, inquiry_no, "
                "project_sales_order_id, state, raised_at) "
                "VALUES (:i, :c, :no, :p, 'raised', now())"
            ),
            {
                "i": self.inquiry,
                "c": self.company_id,
                "no": f"OI-{_uid()[:6].upper()}",
                "p": self.pso,
            },
        )
        db.flush()

    def _product(self, code: str) -> str:
        pid = _uid()
        self.db.execute(
            text(
                "INSERT INTO products (id, company_id, product_code, product_name, "
                "category_id, base_uom_id, list_price) "
                "VALUES (:i, :c, :code, :code, :cat, :uom, 0)"
            ),
            {
                "i": pid,
                "c": self.company_id,
                "code": f"{MARKER}-{code}",
                "cat": self._cat,
                "uom": self._uom,
            },
        )
        return pid

    # -- rules -------------------------------------------------------------

    def rule(self, companion: str, hosts: list[str], *, supplier=None, ratio="1", is_active=True):
        """`hosts` is a list of product KEYS (into `self.products`), in the order the
        plan's derivation reads them - the FIRST is the anchor `bundled_with_row_id`
        names when the rule applies (section 3.2: "the first host row")."""
        rule = ProductCompanionRule(
            id=_uid(),
            company_id=self.company_id,
            companion_product_id=self.products[companion],
            supplier_id=self.suppliers[supplier] if supplier else None,
            ratio=Decimal(ratio),
            is_active=is_active,
        )
        self.db.add(rule)
        self.db.flush()
        for host in hosts:
            self.db.add(
                ProductCompanionRuleHost(rule_id=rule.id, host_product_id=self.products[host])
            )
        self.db.flush()
        return rule

    def product_supplier(self, product_key: str, supplier_key: str, *, primary: bool) -> None:
        self.db.execute(
            text(
                "INSERT INTO product_suppliers (id, company_id, product_id, supplier_id, "
                "standard_lead_time_days, is_primary_supplier) "
                "VALUES (:i, :c, :p, :s, 7, :primary)"
            ),
            {
                "i": _uid(),
                "c": self.company_id,
                "p": self.products[product_key],
                "s": self.suppliers[supplier_key],
                "primary": primary,
            },
        )
        self.db.flush()

    # -- rows ----------------------------------------------------------------

    def row(self, product_key: str, qty, *, verb="ORDER", state="raised", ack_state="acknowledged"):
        rid = _uid()
        self.db.execute(
            text(
                "INSERT INTO " + P + ".order_inquiry_rows (id, company_id, "
                "order_inquiry_id, item_code, qty, verb, stock_location, state, "
                "ack_state, redirected_to_pool, created_at) "
                "VALUES (:i, :c, :inq, :code, :q, :v, 'WH1', :st, :ack, false, now())"
            ),
            {
                "i": rid,
                "c": self.company_id,
                "inq": self.inquiry,
                "code": f"{MARKER}-{product_key}",
                "q": Decimal(str(qty)),
                "v": verb,
                "st": state,
                "ack": ack_state,
            },
        )
        self.db.flush()
        return self.svc._row_or_404(rid)

    def cancel(self, row_id: str) -> None:
        self.db.execute(
            text(
                "UPDATE " + P + ".order_inquiry_rows SET state = 'cancelled' WHERE id = :i"
            ),
            {"i": row_id},
        )
        self.db.flush()

    # -- documents -------------------------------------------------------------

    def purchase_order(self, product_key: str, number: str, supplier_key: str, qty) -> str:
        """One purchase order, one open line, for the named product - so a host row can
        be LINKED to a supplier (3.3's linked-host reading)."""
        po = _uid()
        self.db.execute(
            text(
                "INSERT INTO purchase_orders (id, company_id, po_number, supplier_id, "
                "status, issue_date) VALUES (:i, :c, :n, :s, 'active', :d)"
            ),
            {
                "i": po,
                "c": self.company_id,
                "n": number,
                "s": self.suppliers[supplier_key],
                "d": date(2026, 8, 1),
            },
        )
        line = _uid()
        self.db.execute(
            text(
                "INSERT INTO purchase_order_lines (id, company_id, purchase_order_id, "
                "product_id, warehouse_id, qty_ordered, qty_received, line_status, "
                "expected_date, source_ref) "
                "VALUES (:i, :c, :po, :p, :w, :q, 0, 'open', :e, '1')"
            ),
            {
                "i": line,
                "c": self.company_id,
                "po": po,
                "p": self.products[product_key],
                "w": self.warehouse,
                "q": qty,
                "e": SOON,
            },
        )
        self.db.flush()
        return line

    def spo_allocation(self, product_key: str, number: str, qty) -> str:
        allocation = _uid()
        self.db.execute(
            text(
                "INSERT INTO spo_allocations (id, company_id, spo_number, "
                "spo_line_number, product_id, warehouse_id, allocated_quantity, "
                "quantity_received, quantity_rejected, receipt_status, line_status, "
                "issue_date, expected_date, synced_to_excel, created_at) "
                "VALUES (:i, :c, :n, 1, :p, :w, :q, 0, 0, 'pending', 'open', :iss, "
                ":exp, false, now())"
            ),
            {
                "i": allocation,
                "c": self.company_id,
                "n": number,
                "p": self.products[product_key],
                "w": self.warehouse,
                "q": qty,
                "iss": date(2026, 8, 1),
                "exp": SOON,
            },
        )
        self.db.flush()
        return allocation

    # -- reading ---------------------------------------------------------------

    def links_qty(self, row_id: str) -> Decimal:
        return Decimal(
            str(
                self.db.execute(
                    text(
                        "SELECT COALESCE(SUM(qty), 0) FROM " + P + ".order_inquiry_links "
                        "WHERE row_id = :r"
                    ),
                    {"r": row_id},
                ).scalar()
            )
        )

    def demand_of(self, row) -> Decimal:
        """The row-level formula `demand.py`'s legs share (see module docstring):
        `GREATEST(qty - linked - bundled_qty, 0)`."""
        self.db.refresh(row)
        linked = self.links_qty(row.id)
        bundled = Decimal(str(row.bundled_qty))
        return max(row.qty - linked - bundled, Decimal("0"))


@pytest.fixture()
def world():
    global P
    with blank_session() as db:
        P = _projects(db)
        built = _World(db)
        with company_scope(db, frozenset({built.company_id})):
            yield built


def _single_host_rule(world):
    return world.rule("CKSW015", ["CKS1050"], supplier=None, ratio="1")


def _pair_rule(world, **kwargs):
    return world.rule("SC", ["X", "Y"], supplier="S1", ratio=kwargs.pop("ratio", "1"), **kwargs)


# =============================================================================================
# B - derivation on the row
# =============================================================================================


def test_b1_a_single_host_bundles_the_companion_fully(world):
    _single_host_rule(world)
    host = world.row("CKS1050", 1)
    companion = world.row("CKSW015", 1)

    world.svc.derive_bundles(world.inquiry)
    world.db.refresh(companion)

    assert companion.bundled_qty == Decimal("1")
    # `host.id` off the ORM object (like B4/B5), not a raw `db.execute` scalar - the
    # latter comes back as a psycopg2 `uuid.UUID`, which never equals the ORM's str id.
    assert companion.bundled_with_row_id == host.id
    assert companion.state == "placed"
    assert world.demand_of(companion) == Decimal("0")


def test_b2_no_host_row_at_all_leaves_the_companion_ala_carte(world):
    _single_host_rule(world)
    companion = world.row("CKSW015", 1)

    world.svc.derive_bundles(world.inquiry)
    world.db.refresh(companion)

    assert companion.bundled_qty == Decimal("0")
    assert companion.state == "raised"
    assert world.demand_of(companion) == Decimal("1")


def test_b3_a_companion_bigger_than_its_host_is_partly_bundled(world):
    _single_host_rule(world)
    world.row("CKS1050", 1)
    companion = world.row("CKSW015", 3)

    world.svc.derive_bundles(world.inquiry)
    world.db.refresh(companion)

    assert companion.bundled_qty == Decimal("1")
    assert companion.state == "partly_linked"
    assert world.demand_of(companion) == Decimal("2")


def test_b4_two_hosts_of_one_leave_one_companion_fully_bundled(world):
    _single_host_rule(world)
    world.row("CKS1050", 2)
    companion = world.row("CKSW015", 1)

    world.svc.derive_bundles(world.inquiry)
    world.db.refresh(companion)

    assert companion.bundled_qty == Decimal("1")
    assert world.demand_of(companion) == Decimal("0")


def test_b5_a_pair_host_linked_to_the_matching_supplier_bundles_fully(world):
    _pair_rule(world)
    x_row = world.row("X", 2)
    y_row = world.row("Y", 2)
    line_x = world.purchase_order("X", f"{MARKER}-PO-X", "S1", 2)
    line_y = world.purchase_order("Y", f"{MARKER}-PO-Y", "S1", 2)
    world.svc.place_on_po_allocations(
        x_row.id, [{"po_line_id": line_x, "qty": Decimal("2")}], actor_user_id=None
    )
    world.svc.place_on_po_allocations(
        y_row.id, [{"po_line_id": line_y, "qty": Decimal("2")}], actor_user_id=None
    )
    world.db.flush()
    sc = world.row("SC", 2)

    world.svc.derive_bundles(world.inquiry)
    world.db.refresh(sc)

    assert sc.bundled_qty == Decimal("2")
    assert sc.bundled_with_row_id == x_row.id, "the FIRST host named on the rule is the anchor"
    assert world.demand_of(sc) == Decimal("0")


def test_b6_the_pair_cap_is_the_min_over_both_hosts(world):
    _pair_rule(world)
    x_row = world.row("X", 3)
    y_row = world.row("Y", 2)
    line_x = world.purchase_order("X", f"{MARKER}-PO-X", "S1", 3)
    line_y = world.purchase_order("Y", f"{MARKER}-PO-Y", "S1", 2)
    world.svc.place_on_po_allocations(
        x_row.id, [{"po_line_id": line_x, "qty": Decimal("3")}], actor_user_id=None
    )
    world.svc.place_on_po_allocations(
        y_row.id, [{"po_line_id": line_y, "qty": Decimal("2")}], actor_user_id=None
    )
    world.db.flush()
    sc = world.row("SC", 3)

    world.svc.derive_bundles(world.inquiry)
    world.db.refresh(sc)

    assert sc.bundled_qty == Decimal("2"), "3 X but only 2 Y bundles 2, min over both hosts"
    assert world.demand_of(sc) == Decimal("1")


def test_b7_a_pair_rule_with_only_one_host_present_bundles_nothing(world):
    _pair_rule(world)
    world.row("X", 2)
    sc = world.row("SC", 2)

    world.svc.derive_bundles(world.inquiry)
    world.db.refresh(sc)

    assert sc.bundled_qty == Decimal("0"), "no Y row at all - the pair rule does not apply"
    assert world.demand_of(sc) == Decimal("2")


def test_b8_a_supplier_mismatch_leaves_the_companion_ala_carte(world):
    _pair_rule(world)
    x_row = world.row("X", 2)
    y_row = world.row("Y", 2)
    line_x = world.purchase_order("X", f"{MARKER}-PO-X", "S2", 2)
    line_y = world.purchase_order("Y", f"{MARKER}-PO-Y", "S2", 2)
    world.svc.place_on_po_allocations(
        x_row.id, [{"po_line_id": line_x, "qty": Decimal("2")}], actor_user_id=None
    )
    world.svc.place_on_po_allocations(
        y_row.id, [{"po_line_id": line_y, "qty": Decimal("2")}], actor_user_id=None
    )
    world.db.flush()
    sc = world.row("SC", 2)

    world.svc.derive_bundles(world.inquiry)
    world.db.refresh(sc)

    assert sc.bundled_qty == Decimal("0"), "rule wants S1, hosts are on an S2 order"


def test_b9_an_unlinked_hosts_supplier_is_read_off_its_primary_supplier(world):
    _pair_rule(world)
    world.product_supplier("X", "S1", primary=True)
    world.product_supplier("Y", "S1", primary=True)
    world.row("X", 2)
    world.row("Y", 2)
    sc = world.row("SC", 2)

    world.svc.derive_bundles(world.inquiry)
    world.db.refresh(sc)

    assert sc.bundled_qty == Decimal("2"), (
        "neither host row is linked, so the match is against each host's PRIMARY supplier"
    )


def test_b10_a_cancelled_host_row_un_bundles_the_companion(world):
    _single_host_rule(world)
    host = world.row("CKS1050", 1)
    companion = world.row("CKSW015", 1)
    world.svc.derive_bundles(world.inquiry)
    world.db.refresh(companion)
    assert companion.bundled_qty == Decimal("1"), "sanity: B1 first"

    world.cancel(host.id)
    world.svc.derive_bundles(world.inquiry)
    world.db.refresh(companion)

    assert companion.bundled_qty == Decimal("0")
    assert companion.state == "raised"
    assert world.demand_of(companion) == Decimal("1")


def test_b11_a_manual_link_already_on_the_row_is_kept_and_the_rest_bundles(world):
    _pair_rule(world)
    x_row = world.row("X", 2)
    y_row = world.row("Y", 2)
    line_x = world.purchase_order("X", f"{MARKER}-PO-X", "S1", 2)
    line_y = world.purchase_order("Y", f"{MARKER}-PO-Y", "S1", 2)
    world.svc.place_on_po_allocations(
        x_row.id, [{"po_line_id": line_x, "qty": Decimal("2")}], actor_user_id=None
    )
    world.svc.place_on_po_allocations(
        y_row.id, [{"po_line_id": line_y, "qty": Decimal("2")}], actor_user_id=None
    )
    sc = world.row("SC", 2)
    allocation = world.spo_allocation("SC", f"{MARKER}-SPO-SC", 1)
    world.svc.place_on_po_allocations(
        sc.id, [{"spo_allocation_id": allocation, "qty": Decimal("1")}], actor_user_id=None
    )
    world.db.flush()

    world.svc.derive_bundles(world.inquiry)
    world.db.refresh(sc)

    assert world.links_qty(sc.id) == Decimal("1"), "production's manual link is untouched"
    assert sc.bundled_qty == Decimal("1"), "the bundle covers only what the link did not"
    assert sc.state == "placed"


def test_b12_an_inactive_rule_bundles_nothing(world):
    _single_host_rule(world)
    rule = world.db.query(ProductCompanionRule).filter(
        ProductCompanionRule.companion_product_id == world.products["CKSW015"]
    ).one()
    rule.is_active = False
    world.db.flush()
    world.row("CKS1050", 1)
    companion = world.row("CKSW015", 1)

    world.svc.derive_bundles(world.inquiry)
    world.db.refresh(companion)

    assert companion.bundled_qty == Decimal("0")


def test_b13_a_host_covered_from_stock_raises_no_row_so_the_companion_is_ala_carte(world):
    """The host's demand was covered before purchasing ever heard of it (Buy residual =
    0), so `refresh_for_decision` raised no row for it at all (plan section 2) - only
    CKSW015 was raised as a Buy."""
    _single_host_rule(world)
    companion = world.row("CKSW015", 1)

    world.svc.derive_bundles(world.inquiry)
    world.db.refresh(companion)

    assert companion.bundled_qty == Decimal("0")
    assert world.demand_of(companion) == Decimal("1")


def test_b14_deriving_twice_is_idempotent(world):
    _single_host_rule(world)
    world.row("CKS1050", 1)
    companion = world.row("CKSW015", 1)

    world.svc.derive_bundles(world.inquiry)
    world.db.refresh(companion)
    first_qty, first_anchor = companion.bundled_qty, companion.bundled_with_row_id

    world.svc.derive_bundles(world.inquiry)
    world.db.refresh(companion)

    assert companion.bundled_qty == first_qty
    assert companion.bundled_with_row_id == first_anchor
    total_rows = world.db.execute(
        text(
            "SELECT count(*) FROM " + P + ".order_inquiry_rows WHERE order_inquiry_id = :i"
        ),
        {"i": world.inquiry},
    ).scalar()
    assert total_rows == 2, "no duplicate anchor or companion row was created"


def test_b15_a_fractional_ratio_scales_the_host_cap(world):
    world.rule("C2", ["H2"], supplier=None, ratio="0.5")
    world.row("H2", 4)
    companion = world.row("C2", 3)

    world.svc.derive_bundles(world.inquiry)
    world.db.refresh(companion)

    assert companion.bundled_qty == Decimal("2"), "4 host units * 0.5 ratio = 2 companion units"
    assert world.demand_of(companion) == Decimal("1")


# =============================================================================================
# C - cascade and planner
# =============================================================================================


def test_c1_the_cascade_skips_a_fully_bundled_row_and_links_nothing(world):
    _single_host_rule(world)
    world.row("CKS1050", 1)
    companion = world.row("CKSW015", 1)
    # A real open PO line for CKSW015 at the row's own location: if the cascade's need
    # were still `qty - linked` (ignoring the bundle) this line would be linked to it,
    # which is exactly the regression this pins.
    world.purchase_order("CKSW015", f"{MARKER}-PO-DECOY", "S1", 5)
    world.svc.derive_bundles(world.inquiry)
    world.db.refresh(companion)
    assert world.svc._unlinked_need(companion) == Decimal("0")

    result = world.svc.auto_place_for_products(
        [world.products["CKSW015"]], actor_user_id=None, trigger="zzt-bundle"
    )
    world.db.refresh(companion)

    assert result["placed_rows"] == 0
    assert world.links_qty(companion.id) == Decimal("0")


def test_c2_a_partly_bundled_rows_cascade_need_is_the_ala_carte_remainder(world):
    _single_host_rule(world)
    world.row("CKS1050", 1)
    companion = world.row("CKSW015", 3)

    world.svc.derive_bundles(world.inquiry)
    world.db.refresh(companion)

    assert world.svc._unlinked_need(companion) == Decimal("2")


def test_c3_a_fully_bundled_row_carries_no_demand_for_the_reorder_run(world):
    _single_host_rule(world)
    world.row("CKS1050", 1)
    companion = world.row("CKSW015", 1)

    world.svc.derive_bundles(world.inquiry)

    assert world.demand_of(companion) == Decimal("0"), (
        "the figure `app/services/scm/demand.py`'s legs would net for this row - a "
        "bundled unit never reaches reorder planning (plan 3.4, ruling 6)"
    )


def test_c4_an_ala_carte_row_still_carries_its_own_demand(world):
    _single_host_rule(world)
    companion = world.row("CKSW015", 1)

    world.svc.derive_bundles(world.inquiry)

    assert world.demand_of(companion) == Decimal("1")


# =============================================================================================
# D - the worklist (D4-D8 only; D1-D3/D9/D10 are the cell's own frontend rendering)
# =============================================================================================


def _worklist(world):
    from app.services.order_inquiry_worklist_service import OrderInquiryWorklistService

    return OrderInquiryWorklistService(world.db)


def test_d4_a_fully_bundled_rows_quantity_is_in_none_of_the_three_cards(world):
    _single_host_rule(world)
    host = world.row("CKS1050", 1)
    companion = world.row("CKSW015", 1)
    line = world.purchase_order("CKS1050", f"{MARKER}-PO-HOST", "S1", 1)
    world.svc.place_on_po_allocations(
        host.id, [{"po_line_id": line, "qty": Decimal("1")}], actor_user_id=None
    )
    world.svc.derive_bundles(world.inquiry)
    world.db.flush()

    kinds = _worklist(world)._kinds({})

    assert Decimal(kinds["buy"]) == Decimal("0"), "the bundled unit is not owed as a Buy"
    assert Decimal(kinds["po"]) == Decimal("1"), "only the HOST's own PO quantity counts"


def test_d5_the_buy_card_still_counts_the_anchors_own_unlinked_buy(world):
    """UAC D5 "Buy counts 2, not 3" is about the CKSW015 ROW's own contribution - 1 of
    its 3 rides on CKS1050, so 2 are ala carte. The CARD totals EVERY row in view, and
    CKS1050's own unlinked buy (its own qty 1) still counts there too: ruling 7 excludes
    only the bundled QUANTITY, never the whole row a companion happens to ride on - the
    item CKS1050 itself still needs buying. Buy = 1 (host, unlinked) + 2 (companion's
    ala carte remainder) = 3, never 2."""
    _single_host_rule(world)
    host = world.row("CKS1050", 1)
    world.row("CKSW015", 3)
    world.svc.derive_bundles(world.inquiry)
    world.db.flush()

    kinds = _worklist(world)._kinds({})
    assert Decimal(kinds["buy"]) == Decimal("3"), (
        "the anchor's own unlinked buy (1) plus the companion's ala carte remainder (2)"
    )

    line = world.purchase_order("CKS1050", f"{MARKER}-PO-HOST", "S1", 1)
    world.svc.place_on_po_allocations(
        host.id, [{"po_line_id": line, "qty": Decimal("1")}], actor_user_id=None
    )
    world.db.flush()

    kinds = _worklist(world)._kinds({})
    assert Decimal(kinds["po"]) == Decimal("1"), "the host's own quantity is now on a PO"
    assert Decimal(kinds["buy"]) == Decimal("2"), (
        "once the host is covered, only the companion's ala carte remainder is left to buy"
    )


def test_d6_the_buy_filter_hides_a_fully_bundled_row_and_keeps_an_unlinked_host(world):
    _single_host_rule(world)
    host = world.row("CKS1050", 1)
    fully_bundled = world.row("CKSW015", 1)
    world.row("CKS1050", 1)
    partly_bundled = world.row("CKSW015", 3)
    world.svc.derive_bundles(world.inquiry)
    world.db.flush()

    ids = {entry["id"] for entry in _worklist(world).list_rows(limit=100, kind="buy")["data"]}

    assert fully_bundled.id not in ids
    assert partly_bundled.id in ids
    assert host.id in ids, "an unlinked host row still owes its own buy"


def test_d7_the_row_payload_carries_bundled_qty_and_bundled_with(world):
    """Asserted through the ROUTE (`GET {BASE}/order-inquiries`), not the service
    directly - `response_model` silently drops a field nobody declares."""
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope

    _single_host_rule(world)
    host = world.row("CKS1050", 1)
    companion = world.row("CKSW015", 1)
    world.svc.derive_bundles(world.inquiry)
    world.db.commit()

    actor = {"id": _uid(), "email": "zzt-bundle@zzt.test"}
    app.dependency_overrides[get_db] = lambda: world.db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    app.dependency_overrides[apply_company_scope] = lambda: None
    from app.services.user_service import UserPermissionService

    originals = (
        UserPermissionService.check_user_has_permission,
        UserPermissionService.get_user_permission_slugs,
    )
    UserPermissionService.check_user_has_permission = (
        lambda self, uid, slug: slug == "projects.projects.view"
    )
    UserPermissionService.get_user_permission_slugs = (
        lambda self, uid: ["projects.projects.view"]
    )
    try:
        client = TestClient(app)
        response = client.get("/api/v1/project-sales/order-inquiries", params={"limit": 100})
        assert response.status_code == 200, response.text
        body = next(
            row for row in response.json()["data"] if row["id"] == companion.id
        )
        assert body["bundled_qty"] == "1"
        assert body["bundled_with"]["row_id"] == host.id
        assert body["bundled_with"]["item_code"] == f"{MARKER}-CKS1050"
    finally:
        UserPermissionService.check_user_has_permission = originals[0]
        UserPermissionService.get_user_permission_slugs = originals[1]
        app.dependency_overrides.clear()


def test_d8_the_export_documents_column_names_the_host_for_a_bundled_row(world):
    import io

    import openpyxl

    _single_host_rule(world)
    world.row("CKS1050", 1)
    world.row("CKSW015", 1)
    world.svc.derive_bundles(world.inquiry)
    world.db.flush()

    _filename, content = _worklist(world).export_xlsx()
    workbook = openpyxl.load_workbook(io.BytesIO(content))
    header_row = 2
    headers = [cell.value for cell in workbook.worksheets[0][header_row]]
    po_col = headers.index("PO NO ") + 1
    code_col = headers.index("ITEM CODE") + 1
    values = {
        row[code_col - 1].value: row[po_col - 1].value
        for row in workbook.worksheets[0].iter_rows(min_row=header_row + 1)
    }
    assert "CKS1050" in (values.get(f"{MARKER}-CKSW015") or ""), (
        "the bundled row's document column names its host, not a blank"
    )


# =============================================================================================
# E - after deploy (no backfill)
# =============================================================================================


def test_e1_unplacing_then_relinking_an_open_row_re_derives_its_bundle(world):
    """The pre-deploy production shape: CKSW015 already carries a manual link (the old
    practice), and nobody has ever called `derive_bundles` for this inquiry - exactly
    "before the rule existed". Unplacing it (call site 2, `_refresh_link_state`) must
    derive the bundle on its own, and a fresh partial relink afterwards must re-derive
    again rather than leaving the first answer stale."""
    _single_host_rule(world)
    world.row("CKS1050", 1)
    companion = world.row("CKSW015", 3)
    stale_line = world.purchase_order("CKSW015", f"{MARKER}-PO-STALE", "S1", 3)
    world.svc.place_on_po_allocations(
        companion.id, [{"po_line_id": stale_line, "qty": Decimal("3")}], actor_user_id=None
    )
    world.db.flush()
    world.db.refresh(companion)
    assert companion.bundled_qty == Decimal("0"), (
        "sanity: nobody has derived a bundle for this row yet, exactly as production's "
        "existing open rows are today"
    )

    world.svc.unplace(companion.id, actor_user_id=None)
    world.db.refresh(companion)

    assert companion.bundled_qty == Decimal("1"), "the unplace call re-derives on its own"
    assert companion.state == "partly_linked"

    fresh_line = world.purchase_order("CKSW015", f"{MARKER}-PO-FRESH", "S1", 2)
    world.svc.place_on_po_allocations(
        companion.id, [{"po_line_id": fresh_line, "qty": Decimal("2")}], actor_user_id=None
    )
    world.db.refresh(companion)

    assert world.links_qty(companion.id) == Decimal("2")
    assert companion.bundled_qty == Decimal("1"), "the bundle survives the relink unchanged"
    assert companion.state == "placed", "2 linked + 1 bundled covers the row's 3"
