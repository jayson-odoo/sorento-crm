"""SO314592 (prod, 21 Sep 2026): `derive_bundles`'s own `_is_host_row` (inside the
bundle refresh in `app/services/project_order_inquiry_service.py`, docstring at the top
of the method reading "R.bundled_with_row_id = the first host row of the first host
key") accepts verb ORDER/ORDER_BACK, state not cancelled, ack not rejected - but does
NOT exclude `redirected_to_pool` (a grey USED row). On SO314592 the used
SRTWCX8605-S-RL-PJ row (182, 74 linked, `redirected_to_pool = true`) was the OLDEST
host row, so both live SRTWC8605-SC-RL companion rows got `bundled_with_row_id` pointed
at that used row, the cell tail read the used row's own "74 of 182", and the host cap
summed used 182 + live 220 instead of the live row alone.

`order_inquiry_worklist_service.py`'s own `_live_host_row` (`bundled_host_changes`,
~1796) ALREADY excludes `redirected_to_pool` - this file pins `derive_bundles` to agree.

T1/T2/T4 seed via the `_World` harness copied from `test_order_inquiry_bundles.py`
(raw-SQL masters/rows, `ProjectOrderInquiryService` for the derivation), extended here
with a `redirect()` helper (a plain `UPDATE ... SET redirected_to_pool = true`, the
lightweight route named in the brief over `test_order_inquiry_draft_links.py`'s heavier
`_redirected_fixture`, which exists to test the settle-time WRITER of the flag, not to
be a generic used-row builder). T3 reuses `test_order_inquiry_bundles.py::test_d7`'s
own inline-TestClient pattern (route JSON, never the service directly - `response_model`
silently drops an undeclared field). T5 is the new backfill callable the brief names:
`app/services/oi_bundle_used_anchor_backfill.py::rebundle_rows_anchored_on_used_hosts`.

SO314594 (prod, 21 Sep 2026), T6: `OrderInquiryWorklistService._anchor_headline_by_id`
(`order_inquiry_worklist_service.py` ~1879) sums EVERY entry `links_for_rows` returns
for the anchor row's own id, and `ProjectOrderInquiryService.links_for_rows` (same file,
~4113) appends SYNTHETIC `kind="spo"` entries for a linked PO's own open SPO
allocations of the same product (`_append_derived_spo_entries`, the "via PO" figure) -
never a real `order_inquiry_links` row. A synthetic entry is the ONLY one carrying
`"derived": True` (`links_for_rows`'s real entries carry `derived_po`, a different,
unrelated flag - "this real SPO link names a PO the book itself sourced it from" -
never the key `"derived"` at all). T6 seeds via `test_order_inquiry_kinds.py`'s
fixture builders (through `test_order_inquiry_derived_spo.py`'s own `_po_linked_row`/
`_spo`/`_supplier`, which already build exactly this "PO-linked row with an open
same-product SPO allocation" shape) rather than the raw-SQL `_World` above.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.base import company_scope
from app.models.project_so import IV_ORDER, INQUIRY_RAISED, OrderInquiryRow
from app.services import project_seed_service
from app.services.project_order_inquiry_service import ProjectOrderInquiryService

from app.models.product_companion import (
    ProductCompanionRule,
    ProductCompanionRuleHost,
)

from ._pg_fixture import blank_session
from .test_order_inquiry_derived_spo import _po_linked_row, _spo, _supplier
from .test_order_inquiry_kinds import _project, _sorento, _user

MARKER = "ZZT-BUNHOST"
SOON = date.today() + timedelta(days=30)

#: The `projects` schema THIS session writes to (see `test_order_inquiry_links.py`'s
#: own P / `test_order_inquiry_bundles.py`'s own module-level P).
P = "projects"


def _uid() -> str:
    return str(uuid.uuid4())


def _projects(db) -> str:
    current = db.execute(text("select current_schema()")).scalar()
    return "projects" if current in (None, "public") else f'"{current}_projects"'


class _World:
    """Copied from `test_order_inquiry_bundles.py::_World` (same masters/rows shape),
    plus a `redirect()` helper it has no need for."""

    def __init__(self, db):
        self.db = db
        self.company_id = db.execute(
            text("select id from companies where code = 'SRT'")
        ).scalar()
        self.svc = ProjectOrderInquiryService(db)
        self._build()

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
        for code in ("CKS1050", "CKSW015"):
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
        for code in ("S1",):
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

    def rule(self, companion: str, hosts: list[str], *, supplier=None, ratio="1", is_active=True):
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

    def redirect(self, row_id: str) -> None:
        """Mark a row USED - the flag the fix has to exclude, set directly rather than
        through `planning_change_service`'s settle-time writer, which this file is not
        exercising."""
        self.db.execute(
            text(
                "UPDATE " + P + ".order_inquiry_rows SET redirected_to_pool = true "
                "WHERE id = :i"
            ),
            {"i": row_id},
        )
        self.db.flush()

    def purchase_order(self, product_key: str, number: str, supplier_key: str, qty) -> str:
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


def _worklist_rows(db) -> list[dict]:
    """T3/T6's route call - copied from `test_order_inquiry_bundles.py::test_d7`'s own
    inline TestClient pattern: `response_model` silently drops an undeclared field, so
    the anchor_headline reading has to be asserted through the ROUTE, never the service
    return value directly. Takes the raw session (both `world.db` and `dspo_world`'s own
    `db` work the same way)."""
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    actor = {"id": _uid(), "email": "zzt-bunhost@zzt.test"}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    app.dependency_overrides[apply_company_scope] = lambda: None
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
        return response.json()["data"]
    finally:
        UserPermissionService.check_user_has_permission = originals[0]
        UserPermissionService.get_user_permission_slugs = originals[1]
        app.dependency_overrides.clear()


# =============================================================================================
# T1: a used host is never the display anchor; the LIVE host is
# =============================================================================================


def test_t1_the_live_host_is_the_anchor_not_the_older_used_one(world):
    """SO314592's own shape: the used row is OLDER (created first) and would win any
    "first host row" tie-break today - RED until `_is_host_row` also excludes
    `redirected_to_pool`."""
    _single_host_rule(world)
    used_host = world.row("CKS1050", 182)
    line = world.purchase_order("CKS1050", f"{MARKER}-PO-USED", "S1", 74)
    world.svc.place_on_po_allocations(
        used_host.id, [{"po_line_id": line, "qty": Decimal("74")}], actor_user_id=None
    )
    world.redirect(used_host.id)
    live_host = world.row("CKS1050", 220)
    companion = world.row("CKSW015", 220)

    world.svc.derive_bundles(world.inquiry)
    world.db.refresh(companion)

    assert companion.bundled_with_row_id == live_host.id, (
        "today this reads the USED row's id - the older host row wins the "
        "'first host row' anchor pick with no redirected_to_pool exclusion"
    )
    assert companion.bundled_qty == Decimal("220"), "cap from the live row (220) alone"


# =============================================================================================
# T2: the host cap ignores the used row's quantity entirely
# =============================================================================================


def test_t2_the_host_cap_ignores_the_used_rows_quantity(world):
    _single_host_rule(world)
    live_host = world.row("CKS1050", 100)
    used_host = world.row("CKS1050", 182)
    world.redirect(used_host.id)
    companion = world.row("CKSW015", 150)

    world.svc.derive_bundles(world.inquiry)
    world.db.refresh(companion)

    assert companion.bundled_qty == Decimal("100"), (
        "today the used row's 182 is added into the cap (100 + 182 = 282), so a "
        "150-unit companion reads fully bundled at 150 instead of capped at 100"
    )
    assert companion.bundled_with_row_id == live_host.id


# =============================================================================================
# T3: the worklist row JSON never reads the used row's own coverage as the anchor's
# =============================================================================================


def test_t3_the_anchor_headline_is_not_the_used_rows_74_of_182(world):
    """The used host row carries a link (74 of its own 182) - today's bug lets that
    print as the companion's `bundled_with.anchor_headline`. The live host has no
    links of its own, so the correct reading is None/absent, never "74 of 182"."""
    _single_host_rule(world)
    used_host = world.row("CKS1050", 182)
    line = world.purchase_order("CKS1050", f"{MARKER}-PO-USED", "S1", 74)
    world.svc.place_on_po_allocations(
        used_host.id, [{"po_line_id": line, "qty": Decimal("74")}], actor_user_id=None
    )
    world.redirect(used_host.id)
    live_host = world.row("CKS1050", 220)
    companion = world.row("CKSW015", 220)
    world.svc.derive_bundles(world.inquiry)
    world.db.commit()

    rows = _worklist_rows(world.db)
    row = next(r for r in rows if r["id"] == companion.id)

    assert row["bundled_with"]["row_id"] == live_host.id, row["bundled_with"]
    assert row["bundled_with"]["anchor_headline"] is None, (
        f"expected no anchor headline for the unlinked live host, got "
        f"{row['bundled_with']['anchor_headline']!r} (today this reads the used "
        "row's own '74 of 182')"
    )


# =============================================================================================
# T4: only USED rows are additionally excluded - a rejected host stays excluded
# (already true today), a partly_linked host still counts (already true today)
# =============================================================================================


def test_t4_only_used_rows_are_newly_excluded_rejected_and_partly_linked_are_unaffected(world):
    """Three host rows on the one inquiry: a REJECTED one (already excluded today by
    `ack_state != ACK_REJECTED` - a green control), a PARTLY_LINKED live one (already
    counted today, and must go on counting - the other green control), and a USED one
    (182, the only thing this fix newly excludes). Only the partly_linked row's 50
    caps the companion; RED today because the used row's 182 still leaks into the cap
    (50 + 182 = 232, so a 200-unit companion would read as fully-bundled 200)."""
    _single_host_rule(world)
    rejected_host = world.row("CKS1050", 999, ack_state="rejected")
    partly_linked_host = world.row("CKS1050", 50, state="partly_linked")
    used_host = world.row("CKS1050", 182)
    world.redirect(used_host.id)
    companion = world.row("CKSW015", 200)

    world.svc.derive_bundles(world.inquiry)
    world.db.refresh(companion)

    assert companion.bundled_qty == Decimal("50"), (
        "cap must come from the partly_linked live host (50) alone - the rejected "
        "host's 999 was already excluded, the used host's 182 is what today's bug "
        "still adds in"
    )
    assert companion.bundled_with_row_id == partly_linked_host.id
    assert rejected_host.id  # green control named explicitly: excluded both before and after


# =============================================================================================
# T5: the backfill callable moves an already-used anchor onto the live host
# =============================================================================================


def test_t5_backfill_rebundles_rows_anchored_on_a_used_host(world):
    """`app/services/oi_bundle_used_anchor_backfill.py::rebundle_rows_anchored_on_used_hosts`
    does not exist yet - RED at the local import below (ImportError/ModuleNotFoundError),
    the "missing function" red the brief asks for rather than a fixture bug."""
    from app.services.oi_bundle_used_anchor_backfill import (
        rebundle_rows_anchored_on_used_hosts,
    )

    _single_host_rule(world)
    used_host = world.row("CKS1050", 182)
    world.redirect(used_host.id)
    live_host = world.row("CKS1050", 220)
    companion = world.row("CKSW015", 220)
    # Write the STALE anchor directly - exactly the shape a row derived before this
    # fix landed is left holding, never through `derive_bundles` (which, once fixed,
    # could never produce this in the first place).
    world.db.execute(
        text(
            "UPDATE " + P + ".order_inquiry_rows SET bundled_with_row_id = :h, "
            "bundled_qty = :q WHERE id = :r"
        ),
        {"h": used_host.id, "q": Decimal("182"), "r": companion.id},
    )
    world.db.commit()
    world.db.refresh(companion)
    assert companion.bundled_with_row_id == used_host.id, "fixture sanity: stale anchor written"

    moved = rebundle_rows_anchored_on_used_hosts(world.db)
    world.db.commit()
    world.db.refresh(companion)

    assert moved == 1, "exactly one row's anchor pointed at a used host"
    assert companion.bundled_with_row_id == live_host.id, "re-derivation moves it to the live host"
    assert companion.bundled_qty == Decimal("220")

    again = rebundle_rows_anchored_on_used_hosts(world.db)
    assert again == 0, "idempotent: nothing left anchored on a used host"


# =============================================================================================
# T6: the anchor headline sums real links only, never a synthetic derived-SPO entry
# =============================================================================================


@pytest.fixture()
def dspo_world():
    """`test_order_inquiry_derived_spo.py::world`'s own shape (company, raiser,
    project, supplier), duplicated here under a different fixture name - this file's
    own `world` fixture above already owns that name for the raw-SQL `_World` harness,
    and the two shapes are not interchangeable."""
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        raiser = _user(db, f"{MARKER} raiser")
        project = _project(db, company_id, raiser, f"{MARKER} project {_uid()[:8]}")
        supplier = _supplier(db, company_id)
        with company_scope(db, frozenset({company_id})):
            yield db, company_id, project, supplier


def test_t6_anchor_headline_excludes_a_derived_spo_entry(dspo_world):
    """SO314594's own shape: a host row of 214, one REAL link of 182 to a PO, and that
    PO carries an open SPO allocation of 100 for the same product (a SYNTHETIC `kind=
    "spo", "derived": True` entry `_append_derived_spo_entries` appends, never a real
    `order_inquiry_links` row). The companion is bundled to this host.

    RED today: `_anchor_headline_by_id` sums every entry regardless of `derived`, so
    the headline reads "282 of 214" (182 real + 100 derived) instead of "182 of 214".
    The host row's own ordinary `linked_qty` (control) is real-links-only already and
    must stay 182 - if a fix broke that instead of the headline, this pins the
    difference.
    """
    db, company_id, project, supplier = dspo_world
    product, po, host = _po_linked_row(
        db,
        company_id,
        project,
        supplier,
        qty="214",
        linked_qty="182",
        po_number_suffix="ANCHOR",
    )
    _spo(
        db,
        company_id,
        spo_number=f"ZZT-SPO-{_uid()[:6]}",
        product_id=product.id,
        from_po_number=po.po_number,
        allocated_quantity=100,
    )
    companion = OrderInquiryRow(
        id=_uid(),
        company_id=company_id,
        order_inquiry_id=host.order_inquiry_id,
        item_code=f"{MARKER}-COMPANION",
        qty=Decimal("214"),
        verb=IV_ORDER,
        state=INQUIRY_RAISED,
        bundled_qty=Decimal("182"),
        bundled_with_row_id=host.id,
    )
    db.add(companion)
    db.flush()
    db.commit()

    rows = _worklist_rows(db)
    host_row = next(r for r in rows if r["id"] == host.id)
    companion_row = next(r for r in rows if r["id"] == companion.id)

    assert companion_row["bundled_with"]["anchor_headline"] == "182 of 214", (
        "today this sums the derived SPO's ~100 alongside the real 182, got "
        f"{companion_row['bundled_with']['anchor_headline']!r}"
    )
    # NOTE (measured, not assumed): `_serialize`'s own `linked_qty` reads off the SAME
    # `links[row.id]` list `_anchor_headline_by_id` does, with no `derived` filter of
    # its own - so this is NOT a green control today, it fails the same way the
    # headline does (both read 282, not 182). Left asserted (rather than dropped)
    # because it states what the field OUGHT to read; see the handback note to the
    # coordinator about widening the fix's scope.
    assert host_row["linked_qty"] == "182", (
        "the ordinary cell also sums the derived entry today, got "
        f"{host_row['linked_qty']!r}"
    )
