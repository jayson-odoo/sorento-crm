"""STOCK-DEBT-LENDABLE over the wire: which landed pins lend, the cell's wording, view
independence, board parity and the Rebalance preview + confirm.

    GET  /api/v1/project-sales/stock-debt/{product_id}/cell?month=
    GET  /api/v1/project-sales/stock-debt/{product_id}/rebalance
    POST /api/v1/project-sales/fulfilment-planning/confirm-all   (the existing write)

The arithmetic is `test_stock_debt_lendable.py`'s; what is proved here is the READ that
decides lendability (the line's required date against `as_of + lead + 14`, the board's own
borrow-donor window, off the batched lead-time read), that the view's filters never move
stock (R2), that the board path is untouched (R3), every new wire field by name (R4), and
that the Rebalance preview composes exactly what the fulfilment board's Confirm posts (R5).

Postgres via `tests/scm/conftest.py::scm_app`; every test seeds its own chain.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.project_so import IV_ORDER_BACK, OrderInquiryRow
from app.services.scm.front_planning_engine import RESERVE_BUFFER_DAYS
from app.services.scm.supply_assignment import month_key
from tests.scm.conftest import (
    SORENTO_COMPANY_ID,
    as_user,
    ensure_reference_data,
    requires_pg,
    seed_user,
)
from tests.scm.test_stock_debt_routes import (  # noqa: F401 (helpers, not tests)
    BASE,
    VIEW,
    _demand,
    _product,
    _project_line_for,
    _row_of,
    _stock,
    _u,
    _warehouse,
)

pytestmark = requires_pg

EDIT = "projects.projects.edit"
TODAY = date.today()
#: `DEFAULT_LEAD_TIME_DAYS` (90) + the buffer: a line due on or after this can wait.
DEFAULT_WINDOW = TODAY + timedelta(days=90 + RESERVE_BUFFER_DAYS)


def _client(scm_app, *permissions):
    """`test_stock_debt_routes._client` with several permissions on the one role."""
    app, db, gcu, gcuak = scm_app
    ensure_reference_data(db)
    uid = seed_user(db, None)
    role_id = _u()
    db.execute(
        text(
            "INSERT INTO user_roles (id, slug, name, is_trashed, is_protected, "
            "is_default, created_at) VALUES (:id, :slug, 'ZZT lendable', false, "
            "false, false, now())"
        ),
        {"id": role_id, "slug": f"zzt-lendable-{role_id[:8]}"},
    )
    for permission in permissions:
        permission_id = db.execute(
            text("SELECT id FROM user_permissions WHERE slug = :s"), {"s": permission}
        ).scalar()
        assert permission_id, f"{permission} must exist"
        db.execute(
            text(
                "INSERT INTO user_role_permissions (id, role_id, permission_id, "
                "assigned_at) VALUES (:id, :r, :p, now())"
            ),
            {"id": _u(), "r": role_id, "p": permission_id},
        )
    from app.models.user import UserRoleAssignment

    db.add(UserRoleAssignment(user_id=uid, role_id=role_id))
    db.flush()
    as_user(app, gcu, gcuak, uid)
    return app, db, uid


def _landed_for(db, core_line, product, warehouse, *, qty, marker):
    """What R7's tier 1 reads as LANDED for `core_line`: its own purchase
    (`purchase_order_lines.from_so_line_ref` = the line's `source_ref`), received on an
    SPO row (`spo_allocations.from_po_line_ref` = the PO line's `source_ref`,
    `quantity_received`). The SPO row is fully received, so it is no longer incoming."""
    from app.models.procurement import PurchaseOrder, PurchaseOrderLine, SPOAllocation

    so_ref = f"ZZTBOOK:{marker}:{core_line.id[:8]}"
    core_line.source_ref = so_ref
    po = PurchaseOrder(
        id=_u(), po_number=f"{marker}-PO", issue_date=TODAY - timedelta(days=120),
        status="active", company_id=SORENTO_COMPANY_ID,
    )
    db.add(po)
    db.flush()
    po_ref = f"ZZTPO:{marker}:{core_line.id[:8]}"
    po_line = PurchaseOrderLine(
        id=_u(), purchase_order_id=po.id, product_id=product.id,
        warehouse_id=warehouse.id, qty_ordered=Decimal(str(qty)),
        qty_received=Decimal(str(qty)), line_status="closed",
        expected_date=TODAY - timedelta(days=30), from_so_line_ref=so_ref,
        source_ref=po_ref, company_id=SORENTO_COMPANY_ID,
    )
    db.add(po_line)
    db.flush()
    db.add(
        SPOAllocation(
            id=_u(), spo_number=f"{marker}-SPO", spo_line_number=1,
            product_id=product.id, warehouse_id=warehouse.id,
            allocated_quantity=qty, quantity_received=qty, receipt_status="received",
            line_status="closed", expected_date=TODAY - timedelta(days=20),
            from_po_line_ref=po_ref, company_id=SORENTO_COMPANY_ID,
        )
    )
    db.flush()


def _lead(db, product, days: int):
    """A stated supplier lead time - the second of `lead_times`' two sources."""
    from app.models.procurement import ProductSupplier, Supplier

    supplier = Supplier(
        id=_u(), supplier_code=f"ZZTSUP{_u()[:6]}".upper(), supplier_name="ZZT supplier",
        company_id=SORENTO_COMPANY_ID,
    )
    db.add(supplier)
    db.flush()
    db.add(
        ProductSupplier(
            id=_u(), product_id=product.id, supplier_id=supplier.id,
            standard_lead_time_days=days, company_id=SORENTO_COMPANY_ID,
        )
    )
    db.flush()


def _owner_case(db, *, far_due, near_due=None, near_qty=32, lead=None, stock=88):
    """SRTSS8710 in miniature: 88 landed for the far line at BRW-BB, a nearer line short."""
    marker = f"ZZTLEND{_u()[:6]}".upper()
    warehouse = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    product = _product(db, f"{marker}-SRTSS8710")
    if lead is not None:
        _lead(db, product, lead)
    _stock(db, product, warehouse, stock)
    far_order, far_line = _demand(
        db, product, warehouse, qty=88, required_date=far_due,
        so_number=f"{marker}-SO381065",
    )
    near_order, near_line = _demand(
        db, product, warehouse, qty=near_qty,
        required_date=near_due or (TODAY + timedelta(days=20)),
        so_number=f"{marker}-SO396071",
    )
    _landed_for(db, far_line, product, warehouse, qty=88, marker=marker)
    db.flush()
    return {
        "marker": marker, "warehouse": warehouse, "product": product,
        "far": (far_order, far_line), "near": (near_order, near_line),
    }


def _cell(client, product, month, **params):
    got = client.get(f"{BASE}/{product.id}/cell", params={"month": month, **params})
    assert got.status_code == 200, got.text
    return got.json()


def _by_so(cell, suffix):
    rows = [row for row in cell["demand"] if row["so_number"].endswith(suffix)]
    assert len(rows) == 1, cell["demand"]
    return rows[0]


# --------------------------------------------------------------------------- R1 / R4


def test_a_landed_pin_beyond_the_window_lends_to_the_nearer_line(scm_app):
    """AC-R1 / AC-R4: far line due after `today + 90 + 14` (no stated lead, so the
    default), nearer line short 32. The nearer line reads covered off the far line's landed
    stock, named; the far line reads `order_back` with the receiver named."""
    app, db, _uid = _client(scm_app, VIEW)
    far_due = DEFAULT_WINDOW + timedelta(days=60)
    world = _owner_case(db, far_due=far_due)
    product = world["product"]

    with TestClient(app) as c:
        near_cell = _cell(c, product, month_key(TODAY + timedelta(days=20)))
        far_cell = _cell(c, product, month_key(far_due))

    near = _by_so(near_cell, "SO396071")
    assert near["status"] == "covered"
    assert near["assigned_qty"] == 32
    assert near["short_qty"] == 0
    assert near["lent_qty"] == 0
    [entry] = near["assigned_from"]
    assert entry["kind"] == "on_hand"
    assert entry["qty"] == 32
    assert entry["lent_from_so_number"] == f"{world['marker']}-SO381065"
    assert entry["ref"] == f"On hand {world['warehouse'].warehouse_code} (from {world['marker']}-SO381065)"

    far = _by_so(far_cell, "SO381065")
    assert far["status"] == "order_back"
    assert far["lent_qty"] == 32
    assert far["short_qty"] == 32
    # 56 stay pinned to the far line, on its own floor.
    assert far["assigned_qty"] == 56
    kinds = {entry["kind"]: entry for entry in far["assigned_from"]}
    assert kinds["on_hand"]["qty"] == 56
    assert kinds["on_hand"]["lent_from_so_number"] is None
    lent = kinds["lent"]
    assert lent["qty"] == 32
    assert lent["so_number"] == f"{world['marker']}-SO396071"
    assert lent["sales_order_id"] == str(world["near"][0].id)
    assert lent["ref"] == f"Lent to {world['marker']}-SO396071 (32)"

    # Supply tab unchanged: the on-hand row names both lines in Assigned to.
    [floor] = [row for row in near_cell["supply"] if row["kind"] == "on_hand"]
    assert {(row["so_number"][-8:], row["qty"]) for row in floor["assigned_to"]} == {
        ("SO396071", 32), ("SO381065", 56),
    }
    assert floor["free_qty"] == 0


def test_a_landed_pin_inside_the_window_stays_pinned(scm_app):
    """AC-R3: a line due inside `today + lead + 14` cannot re-buy in time, so its landed
    goods stay with it - today's behaviour, byte for byte."""
    app, db, _uid = _client(scm_app, VIEW)
    far_due = DEFAULT_WINDOW - timedelta(days=1)
    world = _owner_case(db, far_due=far_due)
    product = world["product"]

    with TestClient(app) as c:
        near_cell = _cell(c, product, month_key(TODAY + timedelta(days=20)))
        far_cell = _cell(c, product, month_key(far_due))

    near = _by_so(near_cell, "SO396071")
    assert near["status"] == "short"
    assert near["short_qty"] == 32
    assert near["assigned_from"] == []
    far = _by_so(far_cell, "SO381065")
    assert far["status"] == "pinned"
    assert far["lent_qty"] == 0
    assert far["assigned_qty"] == 88


def test_the_products_own_lead_time_decides_the_window(scm_app):
    """AC-R1b / R7: the window reads the product's stated lead off the batched
    `lead_times` read, not the 90-day default. Lead 30: a line due in 60 days is beyond
    30 + 14 and lends; under the default it would sit inside 104 and stay pinned."""
    app, db, _uid = _client(scm_app, VIEW)
    far_due = TODAY + timedelta(days=60)
    world = _owner_case(db, far_due=far_due, lead=30)
    product = world["product"]

    with TestClient(app) as c:
        far_cell = _cell(c, product, month_key(far_due))
    assert _by_so(far_cell, "SO381065")["status"] == "order_back"


def test_the_day_on_the_window_itself_lends(scm_app):
    """The board's donor rule reads `required_date >= window` (`_eligible_donor`); the
    lend reads the same boundary, so the two cannot disagree by one day."""
    app, db, _uid = _client(scm_app, VIEW)
    world = _owner_case(db, far_due=DEFAULT_WINDOW)
    with TestClient(app) as c:
        far_cell = _cell(c, world["product"], month_key(DEFAULT_WINDOW))
    assert _by_so(far_cell, "SO381065")["status"] == "order_back"


def test_a_tba_or_undated_far_line_never_lends(scm_app):
    """A TBA line draws nothing and holds nothing (R14); an undated one has no date to
    test. Neither is pinned today, so neither lends - the 88 is simply free on hand."""
    app, db, _uid = _client(scm_app, VIEW)
    world = _owner_case(db, far_due=date(2030, 6, 1))
    with TestClient(app) as c:
        near_cell = _cell(c, world["product"], month_key(TODAY + timedelta(days=20)))
        tba_cell = _cell(c, world["product"], "tba")
    near = _by_so(near_cell, "SO396071")
    assert near["status"] == "covered"
    assert near["assigned_from"][0]["lent_from_so_number"] is None
    far = _by_so(tba_cell, "SO381065")
    assert far["status"] == "short"
    assert far["lent_qty"] == 0
    assert far["assigned_from"] == []


# --------------------------------------------------------------------------- R2


def test_the_cell_value_is_the_same_with_and_without_date_to(scm_app):
    """R2: `date_to` hides rows and never moves stock. The nearer month's balance, and the
    nearer line's own row, read the same whether the far line is on the page or not."""
    app, db, _uid = _client(scm_app, VIEW)
    far_due = DEFAULT_WINDOW + timedelta(days=60)
    world = _owner_case(db, far_due=far_due, near_qty=50)
    product, marker = world["product"], world["marker"]
    near_month = month_key(TODAY + timedelta(days=20))
    date_to = (TODAY + timedelta(days=45)).isoformat()

    with TestClient(app) as c:
        whole = c.get(BASE, params={"query": marker, "only_debt": False}).json()
        narrowed = c.get(
            BASE, params={"query": marker, "only_debt": False, "date_to": date_to}
        ).json()
        whole_cell = _cell(c, product, near_month)
        narrowed_cell = _cell(c, product, near_month, date_to=date_to)

    whole_balance = {m["key"]: m["balance"] for m in _row_of(whole, product.product_code)["months"]}
    narrowed_balance = {
        m["key"]: m["balance"] for m in _row_of(narrowed, product.product_code)["months"]
    }
    assert whole_balance[near_month] == narrowed_balance[near_month] == 0
    assert month_key(far_due) not in narrowed_balance
    assert whole_balance[month_key(far_due)] == -50

    whole_near = _by_so(whole_cell, "SO396071")
    narrowed_near = _by_so(narrowed_cell, "SO396071")
    assert whole_near["status"] == narrowed_near["status"] == "covered"
    assert whole_near["assigned_from"] == narrowed_near["assigned_from"]
    assert whole_near["assigned_from"][0]["lent_from_so_number"] == f"{marker}-SO381065"


def test_date_from_never_frees_a_pin_that_cannot_wait(scm_app):
    """The other half of R2: narrowing the page to a later start does not turn a
    non-lendable pin into free stock for the lines that remain."""
    app, db, _uid = _client(scm_app, VIEW)
    far_due = DEFAULT_WINDOW - timedelta(days=1)
    world = _owner_case(db, far_due=far_due, near_due=TODAY + timedelta(days=40))
    near_month = month_key(TODAY + timedelta(days=40))
    with TestClient(app) as c:
        cell = _cell(
            c, world["product"], near_month,
            date_from=(TODAY + timedelta(days=30)).isoformat(),
        )
    assert _by_so(cell, "SO396071")["status"] == "short"


# --------------------------------------------------------------------------- R3 board


def test_the_board_path_still_pins_the_landed_goods(scm_app):
    """R3 / R21: `assignments_for` (the board and the ladder) never lends. There the far
    line stays `pinned` and the nearer line `short`, so the board's own Borrow step keeps
    offering the far line as a DONOR (its cover is on hand and it can wait) with the
    order-back the Confirm raises - which is what Rebalance runs."""
    from app.services.scm.stock_debt_service import StockDebtService

    app, db, _uid = _client(scm_app, VIEW)
    far_due = DEFAULT_WINDOW + timedelta(days=60)
    world = _owner_case(db, far_due=far_due)
    service = StockDebtService(db)
    warehouses = {str(world["warehouse"].id): world["warehouse"]}
    result = service.assignments_for([str(world["product"].id)], warehouses)[
        str(world["product"].id)
    ]
    rows = {row.line.key: row for row in result.lines}
    far = rows[str(world["far"][1].id)]
    near = rows[str(world["near"][1].id)]
    assert far.status == "pinned"
    assert far.lent_qty == 0
    assert near.status == "short"


# --------------------------------------------------------------------------- R5


def test_the_rebalance_preview_composes_the_boards_own_borrow_and_order_back(scm_app):
    """AC-R5a: one read, nothing written. For each receiving sales order adopted onto
    fulfilment planning: a Borrow component naming the far line as donor (the same
    `order_borrow` component the board's Confirm posts), a Buy for whatever the lend does
    not cover, and the order-back the donor gets at its own required date. The body the
    Confirm would post travels back verbatim (`confirm_body`) so the FE never composes."""
    app, db, _uid = _client(scm_app, VIEW, EDIT)
    far_due = DEFAULT_WINDOW + timedelta(days=60)
    world = _owner_case(db, far_due=far_due, near_qty=50)
    product, marker = world["product"], world["marker"]
    near_order, near_line = world["near"]
    # A second, later receiver that is NOT adopted onto the board: named, not composed.
    _demand(
        db, product, world["warehouse"], qty=20,
        required_date=TODAY + timedelta(days=30), so_number=f"{marker}-SO405511",
    )
    pso, mirror = _project_line_for(db, near_line)
    db.flush()

    with TestClient(app) as c:
        got = c.get(f"{BASE}/{product.id}/rebalance")
    assert got.status_code == 200, got.text
    body = got.json()

    assert body["lent_qty"] == 70
    [order] = body["orders"]
    assert order["pso_id"] == str(pso.id)
    assert order["so_number"] == f"{marker}-SO396071"
    [line] = order["lines"]
    assert line["project_line_id"] == str(mirror.id)
    assert line["line_no"] == 1
    assert line["required_date"] == (TODAY + timedelta(days=20)).isoformat()
    [borrow] = line["borrow"]
    assert borrow["qty"] == 50
    assert borrow["warehouse_code"] == world["warehouse"].warehouse_code
    assert borrow["donor_so_number"] == f"{marker}-SO381065"
    assert borrow["donor_required_date"] == far_due.isoformat()
    assert "from " + f"{marker}-SO381065" in borrow["reason"]
    assert line["buy_qty"] == 0
    [back] = order["order_backs"]
    assert back["donor_so_number"] == f"{marker}-SO381065"
    assert back["qty"] == 50
    assert back["required_date"] == far_due.isoformat()

    [skipped] = body["skipped"]
    assert skipped["so_number"] == f"{marker}-SO405511"
    assert skipped["qty"] == 20
    assert "adopt" in skipped["reason"].lower()

    # The confirm body is `POST .../fulfilment-planning/confirm-all`'s own shape.
    [entry] = body["confirm_body"]["orders"]
    assert entry["pso_id"] == str(pso.id)
    [confirm_line] = entry["lines"]
    assert confirm_line["project_line_id"] == str(mirror.id)
    [component] = confirm_line["borrow"]
    assert component["source"] == "other_location"
    assert component["warehouse_id"] == str(world["warehouse"].id)
    assert Decimal(str(component["qty"])) == 50
    assert component["donor_core_line_id"] == str(world["far"][1].id)
    assert component["donor_so_number"] == f"{marker}-SO381065"
    assert component["donor_required_date"] == far_due.isoformat()
    assert Decimal(str(confirm_line["buy_qty"])) == 0

    # Nothing written.
    assert db.query(OrderInquiryRow).filter(OrderInquiryRow.verb == IV_ORDER_BACK).count() == 0


def test_a_partly_lent_receiver_is_posted_as_borrow_plus_buy_with_a_reason(scm_app):
    """AC-R5b: a receiving line the lend covers only in part gets Borrow N + Buy the rest,
    with the server's own amend reason - the split a planner amending on the board posts."""
    app, db, _uid = _client(scm_app, VIEW, EDIT)
    far_due = DEFAULT_WINDOW + timedelta(days=60)
    world = _owner_case(db, far_due=far_due, near_qty=207)
    _project_line_for(db, world["near"][1])
    db.flush()

    with TestClient(app) as c:
        body = c.get(f"{BASE}/{world['product'].id}/rebalance").json()
    [line] = body["orders"][0]["lines"]
    assert line["borrow"][0]["qty"] == 88
    assert line["buy_qty"] == 119
    [confirm_line] = body["confirm_body"]["orders"][0]["lines"]
    assert Decimal(str(confirm_line["buy_qty"])) == 119
    assert confirm_line["amend_reason"]
    assert confirm_line["buy_reason"]


def test_a_product_with_no_lend_previews_nothing(scm_app):
    app, db, _uid = _client(scm_app, VIEW, EDIT)
    world = _owner_case(db, far_due=DEFAULT_WINDOW - timedelta(days=1))
    with TestClient(app) as c:
        body = c.get(f"{BASE}/{world['product'].id}/rebalance").json()
    assert body == {
        "lent_qty": 0, "orders": [], "skipped": [], "confirm_body": {"orders": []},
    }


def test_the_rebalance_preview_needs_the_fulfilment_edit_permission(scm_app):
    """Same gate as the board's Confirm: `projects.projects.edit`, the stock-debt view
    right alone is not enough."""
    app, db, _uid = _client(scm_app, VIEW)
    world = _owner_case(db, far_due=DEFAULT_WINDOW + timedelta(days=60))
    with TestClient(app) as c:
        got = c.get(f"{BASE}/{world['product'].id}/rebalance")
    assert got.status_code == 403, got.text


def test_the_rebalance_confirm_raises_the_order_back_for_the_far_line(scm_app):
    """AC-R5c, end to end through the EXISTING write: the preview's `confirm_body` posted
    to `confirm-all` confirms the receiving order with the borrow, and the donor gets an
    ORDER_BACK inquiry row for the lent quantity at ITS OWN required date - the row the
    hand test checks. Afterwards the view reads the receiver `pinned` off the confirmed
    hold and the far line still `order_back`."""
    app, db, _uid = _client(scm_app, VIEW, EDIT)
    far_due = DEFAULT_WINDOW + timedelta(days=60)
    world = _owner_case(db, far_due=far_due, near_qty=50)
    product, marker = world["product"], world["marker"]
    _far_order, far_line = world["far"]
    pso, _mirror = _project_line_for(db, world["near"][1])
    # The donor is adopted too, so the order-back hangs off ITS line (`_borrow_shortfalls`
    # falls back to the asker's line only for a donor with no mirror).
    _far_pso, far_mirror = _project_line_for(db, far_line)
    db.flush()

    with TestClient(app) as c:
        preview = c.get(f"{BASE}/{product.id}/rebalance").json()
        posted = c.post(
            "/api/v1/project-sales/fulfilment-planning/confirm-all",
            json=preview["confirm_body"],
        )
        assert posted.status_code == 200, posted.text
        [result] = posted.json()["results"]
        assert result["ok"] is True, result
        assert result["pso_id"] == str(pso.id)

        after_near = _cell(c, product, month_key(TODAY + timedelta(days=20)))
        after_far = _cell(c, product, month_key(far_due))

    rows = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.verb == IV_ORDER_BACK)
        .all()
    )
    assert len(rows) == 1, [(row.verb, row.qty, row.delivery_date) for row in rows]
    [back] = rows
    assert Decimal(back.qty) == 50
    assert back.delivery_date == far_due
    assert back.state == "raised"
    # On the DONOR's own project line.
    assert str(back.so_line_id) == str(far_mirror.id)

    near = _by_so(after_near, "SO396071")
    assert near["status"] == "pinned"
    assert near["assigned_qty"] == 50
    far = _by_so(after_far, "SO381065")
    assert far["status"] in {"order_back", "short"}
    assert far["assigned_qty"] == 38
