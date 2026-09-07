"""RED tests for the SPO first-push supersede fix.

UAC: documentation/plans/autocount/spo-xlsx-supersede-acceptance-criteria.md (AC-X1..AC-X27).
PLAN: documentation/plans/autocount/PLAN-spo-xlsx-supersede.md (D25..D30).

Written BEFORE any implementation exists (Phase 2, test-first): `_split_rows` /
`_apply_scoped` in `app.services.shipping_order_ingest_service` carry none of
D25 (first-push supersede), D26 (receipt-carry-per-group) or D27
(links-move-rows-go) yet, so every test below is expected to fail against the
current tree, for the reason recorded in its own docstring - not for an
unrelated fixture defect.

Round 2 (AC-X13..AC-X22, security-review + reviewer rounds, 2026-09-07) adds
D25a (per-group, xlsx-only supersede eligibility), D26a (group-total guard +
merged-shipment warning), D28a (group-aware recompute for
`source_system='autocount'` rows), D30 (supersede needs `.delete`) and D27a
(shipment line-status refresh) - none of which exist in the tree this file is
written against either, same test-first rule.

Substrate reused wholesale from `tests/test_ingest_shipping_orders.py`
(imported, not copied, per the tester brief): the `env` fixture (itself
re-exported from `tests/test_ingest_documents.py`), `_spo_record`, `_spo_line`,
`_spo_rows`, `_seed_legacy_row` (extended there with an `inbound_shipment_id`
kwarg for AC-X6 and a `source_system` kwarg for AC-X13), `INGEST_SPO`,
`READ_SPO`, `MARKER`.

AC-X10, AC-X20 and AC-X21 (the dedupe script) are NOT here: they live in
`tests/test_dedupe_spo_xlsx_superseded.py`. AC-X12 is folded into this file as
a light contract-listing check since it needs no fixture beyond an HTTP GET.
"""
from __future__ import annotations

import logging
import uuid
from contextlib import contextmanager
from datetime import date

from sqlalchemy import text

from app.models.inventory import Warehouse
from app.models.procurement import InboundShipment, PickingHeader, PickingLine, SPOAllocation
from app.models.project_so import (
    IV_ORDER_BACK,
    OrderInquiry,
    OrderInquiryLink,
    OrderInquiryRow,
    ProjectSalesOrder,
)
from app.models.scm import OrderLinkClaim

from tests._pg_fixture import unique_code
from tests.test_ingest_shipping_orders import (
    INGEST_SPO,
    MARKER,
    READ_SPO,
    _seed_legacy_row,
    _spo_line,
    _spo_record,
    _spo_rows,
    env,  # noqa: F401 - pytest fixture, imported for reuse
)

__all__ = ["env"]

_SUPERSEDE_LOGGER = "app.services.shipping_order_ingest_service"


# --------------------------------------------------------------------- helpers
def _warehouse_code(env, warehouse_ref: str) -> str:
    wh_id = env.refs.resolve(entity_type="warehouses", source_ref=warehouse_ref)
    return env.db.execute(
        text("SELECT warehouse_code FROM warehouses WHERE id = :id"), {"id": wh_id}
    ).scalar()


def _picking_line_pointing_at(env, allocation_id: str, *, qty_picked: int = 5) -> PickingLine:
    """One approved GRN line drawing against `allocation_id` (AC-X2/AC-X8)."""
    header = PickingHeader(
        id=str(uuid.uuid4()),
        company_id=env.company_a,
        picking_number=unique_code(MARKER),
        picking_type="goods_received",
        picking_status="approved",
    )
    env.db.add(header)
    env.db.flush()
    product_id = env.refs.resolve(entity_type="products", source_ref=env.product_ref)
    line = PickingLine(
        id=str(uuid.uuid4()),
        company_id=env.company_a,
        picking_header_id=header.id,
        spo_allocation_id=allocation_id,
        product_id=product_id,
        quantity_expected=qty_picked,
        quantity_picked=qty_picked,
    )
    env.db.add(line)
    env.db.flush()
    return line


def _order_link_claim_pointing_at(env, allocation_id: str, spo_number: str) -> OrderLinkClaim:
    claim = OrderLinkClaim(
        company_id=env.company_a,
        so_number=f"{MARKER}-SO-{uuid.uuid4().hex[:8]}",
        po_number=spo_number,
        source="autocount",
        spo_allocation_id=allocation_id,
    )
    env.db.add(claim)
    env.db.flush()
    return claim


def _order_inquiry_link_pointing_at(
    env, allocation_id: str, *, qty: int = 10, null_company: bool = False
) -> OrderInquiryLink:
    """One `projects.order_inquiry_links` row on `allocation_id` (AC-X2/AC-X5).

    Mirrors `tests/scm/test_spo_allocation_documents.py::_project_link`'s
    chain, trimmed to what this fixture needs: no `Project` row (`project_id`
    is nullable on `ProjectSalesOrder`, and `env.stock_transfer` already seeds
    one the same way for the same reason). `null_company` (AC-X19, S4) leaves
    the LINK ROW's own `company_id` NULL - the column is nullable - while its
    parent chain (`ProjectSalesOrder`/`OrderInquiry`/`OrderInquiryRow`) stays
    scoped normally; only the dependant `repoint_allocation_dependants` reads
    is what AC-X19 is about.

    Forced NULL via a raw UPDATE, not by passing `company_id=None` to the
    constructor: `company_scope`'s `before_insert` auto-stamp treats an
    explicit `None` exactly like an omitted value - a live check confirmed
    it silently overwrites it with the ambient scope's own company on
    flush, which would make this fixture "pass" for the wrong reason (the
    dependant never actually ends up NULL at all).
    """
    pso = ProjectSalesOrder(
        id=str(uuid.uuid4()),
        provisional_ref=f"{MARKER}-PSO-{uuid.uuid4().hex[:8]}",
        company_id=env.company_a,
    )
    env.db.add(pso)
    env.db.flush()
    inquiry = OrderInquiry(
        id=str(uuid.uuid4()), project_sales_order_id=pso.id, company_id=env.company_a
    )
    env.db.add(inquiry)
    env.db.flush()
    from decimal import Decimal

    row = OrderInquiryRow(
        id=str(uuid.uuid4()),
        order_inquiry_id=inquiry.id,
        qty=Decimal(str(qty)),
        verb=IV_ORDER_BACK,
        company_id=env.company_a,
    )
    env.db.add(row)
    env.db.flush()
    link = OrderInquiryLink(
        id=str(uuid.uuid4()),
        row_id=row.id,
        spo_allocation_id=allocation_id,
        qty=Decimal(str(qty)),
        company_id=env.company_a,
    )
    env.db.add(link)
    env.db.flush()
    if null_company:
        env.db.execute(
            text("UPDATE order_inquiry_links SET company_id = NULL WHERE id = :id"),
            {"id": link.id},
        )
        env.db.flush()
    return link


def _seed_principal_with_permissions(env, slugs: list[str]) -> str:
    """A fresh user + role holding EXACTLY `slugs` - never superadmin (AC-X17,
    D30). `check_user_has_permission` bypasses every check for a superadmin
    role, and `env`'s own principal always is one, so a genuinely narrower
    principal has to be a different user entirely.
    """
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )

    user_id = str(uuid.uuid4())
    suffix = user_id[:8]
    user = User(
        id=user_id,
        name=f"{MARKER} principal {suffix}",
        email=f"{MARKER.lower()}-{suffix}@integrations.local",
        password="x",
        status="active",
    )
    env.db.add(user)
    env.db.flush()
    role = UserRole(
        id=str(uuid.uuid4()),
        slug=f"{MARKER.lower()}-role-{suffix}",
        name=f"{MARKER} role {suffix}",
    )
    env.db.add(role)
    env.db.flush()
    env.db.add(UserRoleAssignment(user_id=user_id, role_id=role.id))
    env.db.flush()
    for slug in slugs:
        perm = UserPermission(id=str(uuid.uuid4()), slug=slug, name=slug)
        env.db.add(perm)
        env.db.flush()
        env.db.add(UserRolePermission(role_id=role.id, permission_id=perm.id))
    env.db.flush()
    env.db.commit()
    return user_id


@contextmanager
def _as_principal(user_id: str):
    """Swap `get_external_api_user`'s override for one call (AC-X17).

    `env`'s own override always answers the fixed superadmin dict; this
    temporarily answers `user_id` instead, for the one `env.post` call inside
    the `with` block, then restores whatever was there.
    """
    from app.dependencies import get_external_api_user
    from app.main import app as fastapi_app

    def _override():
        return {"id": user_id, "email": f"{MARKER.lower()}-principal@integrations.local"}

    previous = fastapi_app.dependency_overrides.get(get_external_api_user)
    fastapi_app.dependency_overrides[get_external_api_user] = _override
    try:
        yield
    finally:
        if previous is not None:
            fastapi_app.dependency_overrides[get_external_api_user] = previous
        else:
            fastapi_app.dependency_overrides.pop(get_external_api_user, None)


# ============================================================================ #
# AC-X1 (D25, D26)
# ============================================================================ #
class TestAcX1FirstPushSupersedesAClosedXlsxRow:
    def test_a_closed_xlsx_row_is_replaced_by_the_pushed_two_line_set(self, env):
        """AC-X1. One xlsx row (allocated 47, received 47, closed) for
        product P at location L; the first push names two lines for P at L
        (29 + 18, both qty_received 0). Expected: exactly two rows, both
        `source_ref` set, line 1 received 29 closed, line 2 received 18
        closed, both `fully_received`, the xlsx row gone, verdict `created` /
        `lines.created 2` / `lines.superseded 1`.

        RED today because `_split_rows` puts a CLOSED ref-less row into
        `already_closed` (S4), which never enters the adoption pool - both
        incoming lines are therefore created as brand new rows and the xlsx
        row is left exactly as it was, so the SPO ends up holding THREE rows
        (not two) and `entry["lines"]` carries no `superseded` key at all.
        This is the exact production incident (every xlsx SPO duplicated on
        its first ESB push).
        """
        wh_code = _warehouse_code(env, env.warehouse_ref)
        number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        legacy = _seed_legacy_row(
            env,
            spo_number=number,
            spo_line_number=1,
            location_code=wh_code,
            allocated_quantity=47,
            quantity_received=47,
            line_status="closed",
        )

        line1 = _spo_line(
            env, warehouse_ref=env.warehouse_ref, qty_ordered=29, qty_received=0, line_number=1
        )
        line2 = _spo_line(
            env, warehouse_ref=env.warehouse_ref, qty_ordered=18, qty_received=0, line_number=2
        )
        record = _spo_record(
            env, number=number, lines=[line1, line2], supplier_ref=env.supplier_ref
        )

        res = env.post(INGEST_SPO, [record])

        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text
        lines_summary = entry.get("lines") or {}
        assert lines_summary.get("created") == 2, lines_summary
        assert lines_summary.get("superseded") == 1, lines_summary

        rows = _spo_rows(env, number)
        assert len(rows) == 2, "the xlsx row must be gone, leaving exactly the two pushed lines"
        assert all(r["source_ref"] for r in rows)
        by_ref = {r["source_ref"]: r for r in rows}
        first = by_ref[line1["source_ref"]]
        second = by_ref[line2["source_ref"]]
        assert first["quantity_received"] == 29
        assert first["line_status"] == "closed"
        assert first["receipt_status"] == "fully_received"
        assert second["quantity_received"] == 18
        assert second["line_status"] == "closed"
        assert second["receipt_status"] == "fully_received"
        assert str(legacy.id) not in {str(r["id"]) for r in rows}


# ============================================================================ #
# AC-X2 (D27)
# ============================================================================ #
class TestAcX2LinksMoveToTheFirstIncomingLine:
    def test_picking_line_claim_and_order_inquiry_link_repoint_to_line_1(self, env):
        """AC-X2. AC-X1's xlsx row is referenced by one `picking_lines` row,
        one `scm.order_link_claim` row and one `projects.order_inquiry_links`
        row. After the push all three must point at the row for line 1 (the
        first line of the group by `line_number`), none NULL, none pointing
        at a deleted id.

        RED today for the same structural reason as AC-X1: the xlsx row is
        never touched (S4 excludes a closed ref-less row from adoption), so
        none of the three dependants move - they still point at the OLD
        (untouched) xlsx row's id, and that id is a THIRD, still-open row
        the assertion `len(rows) == 2` below never gets past.
        """
        wh_code = _warehouse_code(env, env.warehouse_ref)
        number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        legacy = _seed_legacy_row(
            env,
            spo_number=number,
            spo_line_number=1,
            location_code=wh_code,
            allocated_quantity=47,
            quantity_received=47,
            line_status="closed",
        )
        picking_line = _picking_line_pointing_at(env, legacy.id)
        claim = _order_link_claim_pointing_at(env, legacy.id, number)
        link = _order_inquiry_link_pointing_at(env, legacy.id)

        line1 = _spo_line(
            env, warehouse_ref=env.warehouse_ref, qty_ordered=29, qty_received=0, line_number=1
        )
        line2 = _spo_line(
            env, warehouse_ref=env.warehouse_ref, qty_ordered=18, qty_received=0, line_number=2
        )
        record = _spo_record(
            env, number=number, lines=[line1, line2], supplier_ref=env.supplier_ref
        )

        res = env.post(INGEST_SPO, [record])
        assert res.status_code == 200, res.text

        rows = {r["source_ref"]: r for r in _spo_rows(env, number)}
        assert len(rows) == 2, "AC-X1 must land first for this to hold"
        target_id = str(rows[line1["source_ref"]]["id"])

        picking_line_alloc = env.db.execute(
            text("SELECT spo_allocation_id FROM picking_lines WHERE id = :id"),
            {"id": picking_line.id},
        ).scalar()
        claim_alloc = env.db.execute(
            text("SELECT spo_allocation_id FROM order_link_claim WHERE id = :id"),
            {"id": claim.id},
        ).scalar()
        link_alloc = env.db.execute(
            text("SELECT spo_allocation_id FROM order_inquiry_links WHERE id = :id"),
            {"id": link.id},
        ).scalar()

        assert picking_line_alloc is not None and str(picking_line_alloc) == target_id
        assert claim_alloc is not None and str(claim_alloc) == target_id
        assert link_alloc is not None and str(link_alloc) == target_id


# ============================================================================ #
# AC-X3 (D26)
# ============================================================================ #
class TestAcX3PartialReceiptCarriesAcrossTheGroup:
    def test_a_partially_received_xlsx_row_distributes_its_received_qty_in_line_order(
        self, env
    ):
        """AC-X3. The xlsx row received 30 of 47 (open); after the same
        two-line push, line 1 is received 29 closed, line 2 received 1 open
        (30 - 29 carried over), `receipt_status` fully_received / pending.

        RED today for the same structural reason - no carry exists, so both
        new lines land at `quantity_received=0` (their own pushed value),
        both `open`.
        """
        wh_code = _warehouse_code(env, env.warehouse_ref)
        number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        _seed_legacy_row(
            env,
            spo_number=number,
            spo_line_number=1,
            location_code=wh_code,
            allocated_quantity=47,
            quantity_received=30,
            line_status="open",
        )

        line1 = _spo_line(
            env, warehouse_ref=env.warehouse_ref, qty_ordered=29, qty_received=0, line_number=1
        )
        line2 = _spo_line(
            env, warehouse_ref=env.warehouse_ref, qty_ordered=18, qty_received=0, line_number=2
        )
        record = _spo_record(
            env, number=number, lines=[line1, line2], supplier_ref=env.supplier_ref
        )

        res = env.post(INGEST_SPO, [record])
        assert res.status_code == 200, res.text

        rows = {r["source_ref"]: r for r in _spo_rows(env, number)}
        first = rows[line1["source_ref"]]
        second = rows[line2["source_ref"]]
        assert first["quantity_received"] == 29, first
        assert first["line_status"] == "closed", first
        assert first["receipt_status"] == "fully_received", first
        assert second["quantity_received"] == 1, second
        assert second["line_status"] == "open", second
        assert second["receipt_status"] == "pending", second


# ============================================================================ #
# AC-X5 (D27)
# ============================================================================ #
class TestAcX5AGroupWithNoIncomingCounterpartIsKeptNotSuperseded:
    def test_an_unnamed_product_group_stays_closed_and_keeps_its_link_and_is_not_counted(
        self, env
    ):
        """AC-X5. xlsx rows exist for products P and Q on SPO N; the first
        push names only P. After the push: Q's row still exists, is closed,
        keeps its link; the verdict counts `lines.superseded 1` (P only).

        RED today: since BOTH rows are ref-less (P and Q), both are CLOSED,
        both fall into `already_closed`, neither is superseded and P's own
        row is left behind too (a third, untouched row) alongside a brand
        new row created for the pushed P line - `str(legacy_p.id) not in
        rows` fails, and there is no `superseded` key at all.
        """
        wh_code = _warehouse_code(env, env.warehouse_ref)
        number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        legacy_p = _seed_legacy_row(
            env,
            spo_number=number,
            spo_line_number=1,
            product_ref=env.product_ref,
            location_code=wh_code,
            allocated_quantity=10,
            quantity_received=10,
            line_status="closed",
        )
        legacy_q = _seed_legacy_row(
            env,
            spo_number=number,
            spo_line_number=2,
            product_ref=env.product2_ref,
            location_code=wh_code,
            allocated_quantity=5,
            quantity_received=5,
            line_status="closed",
        )
        claim = _order_link_claim_pointing_at(env, legacy_q.id, number)

        line = _spo_line(
            env, warehouse_ref=env.warehouse_ref, product_ref=env.product_ref,
            qty_ordered=10, qty_received=0,
        )
        record = _spo_record(env, number=number, lines=[line], supplier_ref=env.supplier_ref)

        res = env.post(INGEST_SPO, [record])
        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        lines_summary = entry.get("lines") or {}
        assert lines_summary.get("superseded") == 1, lines_summary

        rows = {str(r["id"]): r for r in _spo_rows(env, number)}
        assert str(legacy_q.id) in rows, "Q's group had no incoming line and must be kept"
        assert rows[str(legacy_q.id)]["line_status"] == "closed"
        assert str(legacy_p.id) not in rows, "P's group had an incoming line and must be gone"

        claim_alloc = env.db.execute(
            text("SELECT spo_allocation_id FROM order_link_claim WHERE id = :id"),
            {"id": claim.id},
        ).scalar()
        assert str(claim_alloc) == str(legacy_q.id)


# ============================================================================ #
# AC-X6 (D26)
# ============================================================================ #
class TestAcX6ShipmentLinkCarriesToEveryLineOfTheGroup:
    def test_every_pushed_line_carries_the_xlsx_rows_shipment_when_the_container_does_not_resolve(
        self, env
    ):
        """AC-X6. The xlsx row carries `inbound_shipment_id`; the push's own
        `container_number` resolves to no shipment. After the push, every
        line of that group must carry the xlsx row's `inbound_shipment_id`.

        RED today: since nothing supersedes the row, no new row inherits
        anything from it - both created rows land with `inbound_shipment_id
        IS NULL` (the container this push named resolves to nothing, and
        there is no carry-forward from the xlsx row at all).
        """
        shipment = InboundShipment(
            id=str(uuid.uuid4()),
            shipment_number=f"{MARKER}-SH-{uuid.uuid4().hex[:6]}",
            shipping_container_number=f"{MARKER}-CONT-{uuid.uuid4().hex[:6]}",
            shipment_date=date(2026, 1, 1),
            shipment_status="pending",
        )
        env.db.add(shipment)
        env.db.flush()

        wh_code = _warehouse_code(env, env.warehouse_ref)
        number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        _seed_legacy_row(
            env,
            spo_number=number,
            spo_line_number=1,
            location_code=wh_code,
            allocated_quantity=47,
            quantity_received=47,
            line_status="closed",
            inbound_shipment_id=shipment.id,
        )

        line1 = _spo_line(env, warehouse_ref=env.warehouse_ref, qty_ordered=29, qty_received=0)
        line2 = _spo_line(env, warehouse_ref=env.warehouse_ref, qty_ordered=18, qty_received=0)
        record = _spo_record(
            env,
            number=number,
            lines=[line1, line2],
            supplier_ref=env.supplier_ref,
            container_number=f"{MARKER}-UNRESOLVED-{uuid.uuid4().hex[:6]}",
        )

        res = env.post(INGEST_SPO, [record])
        assert res.status_code == 200, res.text

        rows = _spo_rows(env, number)
        assert len(rows) == 2, "AC-X1 must land first for this to hold"
        for row in rows:
            assert row["inbound_shipment_id"] is not None
            assert str(row["inbound_shipment_id"]) == str(shipment.id), row


# ============================================================================ #
# AC-X7 (D25)
# ============================================================================ #
class TestAcX7AnOpenXlsxRowIsAlsoSuperseded:
    def test_an_open_xlsx_row_is_superseded_too_not_only_a_closed_one(self, env):
        """AC-X7. An OPEN xlsx row (received 0) for the same product +
        location; the first push supersedes it too (deleted), the pushed
        lines carry received 0, open.

        RED today: an OPEN ref-less row lands in `pool` (not
        `already_closed`), so the EXISTING (pre-D25) adoption ladder
        (AC-V3-4) claims it for ONE of the two incoming lines in place -
        the row keeps its OWN id (never deleted) and the other line is
        created fresh. `str(legacy.id) not in all_ids` therefore fails: the
        xlsx row's id is still present, just repurposed as one ESB line
        instead of the clean two-new-rows-and-delete D25/D27 mandate.
        """
        wh_code = _warehouse_code(env, env.warehouse_ref)
        number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        legacy = _seed_legacy_row(
            env,
            spo_number=number,
            spo_line_number=1,
            location_code=wh_code,
            allocated_quantity=47,
            quantity_received=0,
            line_status="open",
        )

        line1 = _spo_line(env, warehouse_ref=env.warehouse_ref, qty_ordered=29, qty_received=0)
        line2 = _spo_line(env, warehouse_ref=env.warehouse_ref, qty_ordered=18, qty_received=0)
        record = _spo_record(
            env, number=number, lines=[line1, line2], supplier_ref=env.supplier_ref
        )

        res = env.post(INGEST_SPO, [record])
        assert res.status_code == 200, res.text

        rows = _spo_rows(env, number)
        assert len(rows) == 2, rows
        for row in rows:
            assert row["quantity_received"] == 0, row
            assert row["line_status"] == "open", row
        all_ids = {str(r["id"]) for r in rows}
        assert str(legacy.id) not in all_ids, (
            "the xlsx row must be a deleted, superseded row - not adopted in place"
        )


# ============================================================================ #
# AC-X9 (D25)
# ============================================================================ #
class TestAcX9ARepushOfTheSameDockeyIsAPlainUpdate:
    def test_a_second_push_of_the_same_dockey_after_ac_x1_updates_without_re_superseding(
        self, env
    ):
        """AC-X9. A second push of the same DocKey after AC-X1 (same lines,
        qty_received still 0) answers `updated`, leaves both rows received
        29 / 18 closed (received never shrinks); `lines.superseded` absent.

        RED today: the first push doesn't even reach AC-X1's two-row shape
        (see that test) - it produces THREE rows, the two new ones at
        received 0. The second push then updates those two rows by their own
        `source_ref`, but since no carry-forward ever wrote 29/18 onto them
        in the first place, they still read 0 - `quantity_received == 29`
        fails.
        """
        wh_code = _warehouse_code(env, env.warehouse_ref)
        number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        _seed_legacy_row(
            env,
            spo_number=number,
            spo_line_number=1,
            location_code=wh_code,
            allocated_quantity=47,
            quantity_received=47,
            line_status="closed",
        )

        line1 = _spo_line(env, warehouse_ref=env.warehouse_ref, qty_ordered=29, qty_received=0)
        line2 = _spo_line(env, warehouse_ref=env.warehouse_ref, qty_ordered=18, qty_received=0)
        record = _spo_record(
            env, number=number, lines=[line1, line2], supplier_ref=env.supplier_ref
        )
        res1 = env.post(INGEST_SPO, [record])
        assert res1.status_code == 200, res1.text

        res2 = env.post(INGEST_SPO, [record])

        entry2 = res2.json()["records"][0]
        assert entry2["outcome"] == "updated", res2.text
        assert "superseded" not in (entry2.get("lines") or {}), entry2

        rows = {r["source_ref"]: r for r in _spo_rows(env, number)}
        assert rows[line1["source_ref"]]["quantity_received"] == 29, rows[line1["source_ref"]]
        assert rows[line1["source_ref"]]["line_status"] == "closed"
        assert rows[line2["source_ref"]]["quantity_received"] == 18, rows[line2["source_ref"]]
        assert rows[line2["source_ref"]]["line_status"] == "closed"


# ============================================================================ #
# AC-X8 (D28)
# ============================================================================ #
class TestAcX8RecomputeRespectsOwnership:
    def test_an_allocation_with_no_picking_line_keeps_its_stored_value_on_recompute(
        self, env
    ):
        """AC-X8. An allocation with `quantity_received=29` and NO picking
        line, and a sibling allocation of the same SPO with one approved
        picking line of 5; after `sync_received_for_spo_number(N)`, the
        sibling reads 5 and the first still reads 29.

        RED today: `sync_received_for_spo_number` calls
        `compute_received_for_allocation` for EVERY allocation matching the
        SPO regardless of whether it has a picking line - an allocation with
        none sums to 0 and gets overwritten from 29 to 0.
        """
        from app.services.procurement_service import PickingHeaderService

        number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        product_id = env.refs.resolve(entity_type="products", source_ref=env.product_ref)
        product2_id = env.refs.resolve(entity_type="products", source_ref=env.product2_ref)

        no_picking = SPOAllocation(
            id=str(uuid.uuid4()),
            company_id=env.company_a,
            spo_number=number,
            spo_line_number=1,
            product_id=product_id,
            allocated_quantity=29,
            quantity_received=29,
            line_status="closed",
            receipt_status="fully_received",
            source_system="scm_upload",
        )
        env.db.add(no_picking)
        env.db.flush()

        with_picking = SPOAllocation(
            id=str(uuid.uuid4()),
            company_id=env.company_a,
            spo_number=number,
            spo_line_number=2,
            product_id=product2_id,
            allocated_quantity=5,
            quantity_received=0,
            line_status="open",
            receipt_status="pending",
            source_system="scm_upload",
        )
        env.db.add(with_picking)
        env.db.flush()
        _picking_line_pointing_at(env, with_picking.id, qty_picked=5)
        env.db.commit()

        PickingHeaderService(env.db).sync_received_for_spo_number(number)

        env.db.expire_all()
        received_no_picking = env.db.execute(
            text("SELECT quantity_received FROM spo_allocations WHERE id = :id"),
            {"id": no_picking.id},
        ).scalar()
        received_with_picking = env.db.execute(
            text("SELECT quantity_received FROM spo_allocations WHERE id = :id"),
            {"id": with_picking.id},
        ).scalar()

        assert received_with_picking == 5, received_with_picking
        assert received_no_picking == 29, (
            "an allocation with no picking line must keep its stored value, "
            f"not be recomputed to 0 - got {received_no_picking}"
        )


# ============================================================================ #
# AC-X11
# ============================================================================ #
class TestAcX11XlsxThenGrnThenPushMatchesPushThenGrn:
    """AC-X11. The AC-X1 outcome (two rows, 29 / 18 allocated, closed, same
    `quantity_received`) must be identical whether reached by (xlsx upload ->
    GRN -> first push, D26's carry) or by (first push -> GRN, the ordinary
    two-line receiving flow), for the same fixture in two separate companies
    so this compares row SHAPE, not the same rows twice. The GRN half is
    seeded directly (`quantity_received` / `line_status` set by hand) rather
    than driven through `PickingHeaderService`, the same simplification
    `tests/test_ingest_parity_s3_shipping_orders.py` uses for its own
    "already received via a GRN, out of scope here" fixture.

    RED today: company A's push (step 3 below) does not carry the closed
    xlsx row's receipt forward at all - it leaves the xlsx row untouched
    (a THIRD row) and creates two new rows at `quantity_received=0`, so the
    two companies' final row sets disagree on `quantity_received` and
    `line_status`, and company A holds 3 rows against company B's 2.
    """

    def _seed_company(self, db) -> str:
        from app.models.company import Company

        other = Company(
            id=str(uuid.uuid4()),
            name=f"{MARKER} PAR {uuid.uuid4().hex[:6]}",
            code=unique_code(MARKER)[:10],
        )
        db.add(other)
        db.flush()
        return str(other.id)

    def _seed_product_and_warehouse(self, db):
        from app.models.product import Product, ProductCategory, UnitOfMeasure

        category = ProductCategory(category_code=unique_code(MARKER), category_name="Cat")
        uom = UnitOfMeasure(uom_code=unique_code(MARKER), uom_name="Each")
        db.add_all([category, uom])
        db.flush()
        product = Product(
            product_code=unique_code(MARKER),
            product_name="Item",
            category_id=category.id,
            base_uom_id=uom.id,
            list_price=0,
        )
        db.add(product)
        db.flush()
        ref = f"{MARKER}:ITEM:{uuid.uuid4().hex[:8]}"
        from app.services.integration_reference_service import IntegrationReferenceService

        IntegrationReferenceService(db).link(
            entity_type="products", entity_id=product.id, source_ref=ref
        )
        warehouse = Warehouse(
            warehouse_code=f"{MARKER}WH{uuid.uuid4().hex[:6]}", warehouse_name="Main"
        )
        db.add(warehouse)
        db.flush()
        return product, ref, warehouse

    def test_the_supersede_outcome_matches_the_ordinary_receiving_order(self):
        from app.models.base import set_company_scope
        from app.services.company_scope import DEFAULT_COMPANY_ID
        from app.services.master_ingest_service import IngestOutcome
        from app.services.shipping_order_ingest_service import ShippingOrderIngestService

        from tests._pg_fixture import blank_session

        with blank_session() as db:
            spo_number = f"{MARKER}-SPOPAR-{uuid.uuid4().hex[:8]}"

            # ---- company A: xlsx -> GRN -> first push ----
            set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
            product_a, ref_a, wh_a = self._seed_product_and_warehouse(db)
            xlsx_row = SPOAllocation(
                id=str(uuid.uuid4()),
                company_id=DEFAULT_COMPANY_ID,
                spo_number=spo_number,
                spo_line_number=1,
                product_id=product_a.id,
                location_code=wh_a.warehouse_code,
                allocated_quantity=47,
                quantity_received=0,
                line_status="open",
                source_system="scm_upload",
            )
            db.add(xlsx_row)
            db.flush()
            # The GRN receives everything and closes it - seeded directly.
            xlsx_row.quantity_received = 47
            xlsx_row.line_status = "closed"
            xlsx_row.receipt_status = "fully_received"
            db.flush()

            svc_a = ShippingOrderIngestService(db, integration_id=None, company_id=DEFAULT_COMPANY_ID)
            result_a = svc_a.ingest(
                "shipping_orders",
                [
                    {
                        "source_ref": f"{MARKER}:SPO:{uuid.uuid4().hex[:8]}",
                        "spo_number": spo_number,
                        "status": "open",
                        "lines": [
                            {
                                "source_ref": f"{MARKER}:SPOL:{uuid.uuid4().hex[:8]}",
                                "product_ref": ref_a,
                                "warehouse_code": wh_a.warehouse_code,
                                "qty_ordered": "29",
                                "qty_received": "0",
                            },
                            {
                                "source_ref": f"{MARKER}:SPOL:{uuid.uuid4().hex[:8]}",
                                "product_ref": ref_a,
                                "warehouse_code": wh_a.warehouse_code,
                                "qty_ordered": "18",
                                "qty_received": "0",
                            },
                        ],
                    }
                ],
            )
            # AC-X1: a first push whose spo_number holds only ref-less rows
            # supersedes them - the verdict reads `created`, not `updated`.
            assert result_a.records[0].outcome is IngestOutcome.CREATED, result_a.records[0].errors

            # ---- company B: first push -> GRN ----
            company_b = self._seed_company(db)
            set_company_scope(db, frozenset({company_b}))
            product_b, ref_b, wh_b = self._seed_product_and_warehouse(db)

            svc_b = ShippingOrderIngestService(db, integration_id=None, company_id=company_b)
            result_b = svc_b.ingest(
                "shipping_orders",
                [
                    {
                        "source_ref": f"{MARKER}:SPOB:{uuid.uuid4().hex[:8]}",
                        "spo_number": spo_number,
                        "status": "open",
                        "lines": [
                            {
                                "source_ref": f"{MARKER}:SPOLB1:{uuid.uuid4().hex[:8]}",
                                "product_ref": ref_b,
                                "warehouse_code": wh_b.warehouse_code,
                                "qty_ordered": "29",
                                "qty_received": "0",
                            },
                            {
                                "source_ref": f"{MARKER}:SPOLB2:{uuid.uuid4().hex[:8]}",
                                "product_ref": ref_b,
                                "warehouse_code": wh_b.warehouse_code,
                                "qty_ordered": "18",
                                "qty_received": "0",
                            },
                        ],
                    }
                ],
            )
            assert result_b.records[0].outcome is IngestOutcome.CREATED, result_b.records[0].errors

            rows_b_ids = db.execute(
                text(
                    "SELECT id, allocated_quantity FROM spo_allocations "
                    "WHERE company_id = :c AND spo_number = :n ORDER BY allocated_quantity"
                ),
                {"c": company_b, "n": spo_number},
            ).mappings().all()
            for row in rows_b_ids:
                target = 29 if row["allocated_quantity"] == 29 else 18
                db.execute(
                    text(
                        "UPDATE spo_allocations SET quantity_received = :q, "
                        "line_status = 'closed', receipt_status = 'fully_received' "
                        "WHERE id = :id"
                    ),
                    {"q": target, "id": row["id"]},
                )
            db.flush()

            columns = "allocated_quantity, quantity_received, line_status, inbound_shipment_id"
            rows_a = (
                db.execute(
                    text(
                        f"SELECT {columns} FROM spo_allocations "
                        "WHERE company_id = :c AND spo_number = :n ORDER BY allocated_quantity"
                    ),
                    {"c": DEFAULT_COMPANY_ID, "n": spo_number},
                )
                .mappings()
                .all()
            )
            rows_b_final = (
                db.execute(
                    text(
                        f"SELECT {columns} FROM spo_allocations "
                        "WHERE company_id = :c AND spo_number = :n ORDER BY allocated_quantity"
                    ),
                    {"c": company_b, "n": spo_number},
                )
                .mappings()
                .all()
            )

            assert len(rows_a) == 2, (
                f"company A must hold exactly two rows after the supersede - got {len(rows_a)}"
            )
            assert len(rows_b_final) == 2

            for row_a, row_b in zip(rows_a, rows_b_final):
                diff = {k: (row_a[k], row_b[k]) for k in row_a.keys() if row_a[k] != row_b[k]}
                assert diff == {}, diff


# ============================================================================ #
# AC-X13 (D25a)
# ============================================================================ #
class TestAcX13OnlyScmUploadRowsAreSupersedeCandidates:
    def test_a_null_source_ref_less_row_is_never_a_supersede_candidate(self, env):
        """AC-X13 (D25a). A ref-less row written by the CRM UI / n8n
        packing-list route (`source_system` NULL) is not an xlsx-era
        supersede candidate - only `source_system='scm_upload'` rows are. On
        a first push naming its product + location, the row is adopted or
        left per the PRE-EXISTING (pre-D25) rules, never deleted, and
        `lines.superseded` is absent.

        RED today: D25a's per-group `source_system` filter does not exist -
        `_split_rows`'s `first_push` branch buckets EVERY ref-less row into
        `supersede_pool` regardless of `source_system`, so this NULL-source
        row is superseded exactly like an xlsx row would be: `lines.
        superseded` reads `1` and the row is gone.
        """
        wh_code = _warehouse_code(env, env.warehouse_ref)
        number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        legacy = _seed_legacy_row(
            env,
            spo_number=number,
            spo_line_number=1,
            location_code=wh_code,
            allocated_quantity=10,
            quantity_received=0,
            line_status="open",
            source_system=None,
        )

        line = _spo_line(env, warehouse_ref=env.warehouse_ref, qty_ordered=10, qty_received=0)
        record = _spo_record(env, number=number, lines=[line], supplier_ref=env.supplier_ref)

        res = env.post(INGEST_SPO, [record])

        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert "superseded" not in (entry.get("lines") or {}), entry

        rows = _spo_rows(env, number)
        assert str(legacy.id) in {str(r["id"]) for r in rows}, (
            "a NULL-source ref-less row must never be superseded/deleted - "
            "only scm_upload rows are supersede candidates"
        )


# ============================================================================ #
# AC-X14 (D25a, per-group)
# ============================================================================ #
class TestAcX14PerGroupEligibilitySurvivesAPriorPushsRefRow:
    def test_a_still_xlsx_group_is_superseded_on_the_push_that_first_names_it(self, env):
        """AC-X14 (D25a, per-group). xlsx rows for P and Q on SPO N; push 1
        (a DocKey) names P only - Q is kept, closed, untouched. Push 2 (the
        SAME DocKey) now ALSO names Q, at qty 20 / received 0, while Q's
        xlsx row carried received 20. After push 2, Q's group must hold
        EXACTLY ONE row - ref set, received 20, closed - the xlsx Q row
        gone (`lines.superseded 1` on push 2); no open Q row may exist.

        RED today: eligibility is decided per DOCUMENT
        (`_has_ref_row(payload)`, D25), not per group - after push 1 gave
        the spo_number a ref row (P's), push 2 sees `first_push=False` for
        the WHOLE document, so Q's still-xlsx-era, still-ref-less, CLOSED
        row falls into `already_closed` (S4) rather than the supersede
        pool: it is never superseded, and push 2's Q line is created as a
        brand new, OPEN row alongside it - TWO rows, not one, and an open
        row exists where none should.
        """
        wh_code = _warehouse_code(env, env.warehouse_ref)
        number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        _seed_legacy_row(
            env,
            spo_number=number,
            spo_line_number=1,
            product_ref=env.product_ref,
            location_code=wh_code,
            allocated_quantity=10,
            quantity_received=10,
            line_status="closed",
        )
        legacy_q = _seed_legacy_row(
            env,
            spo_number=number,
            spo_line_number=2,
            product_ref=env.product2_ref,
            location_code=wh_code,
            allocated_quantity=20,
            quantity_received=20,
            line_status="closed",
        )

        p_line = _spo_line(
            env, warehouse_ref=env.warehouse_ref, product_ref=env.product_ref,
            qty_ordered=10, qty_received=0,
        )
        record1 = _spo_record(env, number=number, lines=[p_line], supplier_ref=env.supplier_ref)
        res1 = env.post(INGEST_SPO, [record1])
        assert res1.status_code == 200, res1.text

        q_line = _spo_line(
            env, warehouse_ref=env.warehouse_ref, product_ref=env.product2_ref,
            qty_ordered=20, qty_received=0,
        )
        record2 = dict(record1, lines=[p_line, q_line])
        res2 = env.post(INGEST_SPO, [record2])

        assert res2.status_code == 200, res2.text
        entry2 = res2.json()["records"][0]
        assert entry2.get("lines", {}).get("superseded") == 1, entry2

        product2_id = env.refs.resolve(entity_type="products", source_ref=env.product2_ref)
        q_rows = [
            r for r in _spo_rows(env, number) if str(r["product_id"]) == str(product2_id)
        ]
        assert len(q_rows) == 1, ("Q's group must hold exactly one row after push 2", q_rows)
        q_row = q_rows[0]
        assert q_row["source_ref"] == q_line["source_ref"]
        assert q_row["quantity_received"] == 20
        assert q_row["line_status"] == "closed"
        assert str(legacy_q.id) not in {str(r["id"]) for r in q_rows}
        assert not any(r["line_status"] == "open" for r in q_rows)


# ============================================================================ #
# AC-X15 (D26a guard)
# ============================================================================ #
class TestAcX15GuardOnGroupTotalBelowCarriedReceipt:
    def test_a_first_push_undercutting_the_carried_receipt_is_not_superseded(self, env):
        """AC-X15 (D26a guard). The AC-X1 xlsx row (allocated 47, received
        47, closed) and a first push with ONE line for P at L, `qty_ordered
        1`, `qty_received 0` - the incoming group's own allocated total (1)
        is below the group's carried receipt (47). The group must NOT be
        superseded: the xlsx row stays (still present, closed), a new OPEN
        row of 1 is created normally (no carry), the record warns
        `received_locked`, and the xlsx row's own receipt never drops below
        what it held before the push.

        RED today: D26a's guard does not exist - `plan_xlsx_supersede`
        dumps the WHOLE carried receipt (47) onto the single incoming line
        regardless of its own allocated_quantity, so the group IS
        superseded: the xlsx row is deleted, and the new row lands
        `allocated_quantity=1`, `quantity_received=47`, CLOSED - not the
        open, uncarried row of 1 this AC wants - and no `received_locked`
        warning is emitted at all.
        """
        wh_code = _warehouse_code(env, env.warehouse_ref)
        number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        legacy = _seed_legacy_row(
            env,
            spo_number=number,
            spo_line_number=1,
            location_code=wh_code,
            allocated_quantity=47,
            quantity_received=47,
            line_status="closed",
        )

        line = _spo_line(env, warehouse_ref=env.warehouse_ref, qty_ordered=1, qty_received=0)
        record = _spo_record(env, number=number, lines=[line], supplier_ref=env.supplier_ref)

        res = env.post(INGEST_SPO, [record])

        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert "received_locked" in (entry.get("warnings") or []), entry

        rows = _spo_rows(env, number)
        by_id = {str(r["id"]): r for r in rows}
        assert str(legacy.id) in by_id, (
            "the xlsx row must not be deleted - the group total undercuts its receipt"
        )
        assert by_id[str(legacy.id)]["line_status"] == "closed"
        assert by_id[str(legacy.id)]["quantity_received"] == 47

        by_ref = {r["source_ref"]: r for r in rows if r["source_ref"]}
        new_row = by_ref[line["source_ref"]]
        assert new_row["allocated_quantity"] == 1
        assert new_row["quantity_received"] == 0
        assert new_row["line_status"] == "open"


# ============================================================================ #
# AC-X16 (D26a shipments)
# ============================================================================ #
class TestAcX16MergedShipmentsWarnAndLogTheDropped:
    def test_two_shipments_on_one_group_use_the_first_and_warn_and_log_the_dropped(
        self, env, caplog
    ):
        """AC-X16 (D26a shipments). Two xlsx rows for P at L on SPO N,
        linked to two DIFFERENT inbound shipments A (line 1) and B (line
        2); a first push naming P at L with two lines. Every new line must
        carry shipment A (D26's own "first non-null" rule - already
        correct), the record must ALSO warn `shipment_merged`, and the
        supersede must log at INFO the dropped shipment (B)'s identity.

        RED today: D26a's warning/log for a merged shipment does not exist
        - only the "use the first" behaviour (D26) is there. The
        `shipment_merged` warning is absent, and no INFO log line names
        shipment B at all.
        """
        shipment_a = InboundShipment(
            id=str(uuid.uuid4()),
            shipment_number=f"{MARKER}-SHA-{uuid.uuid4().hex[:6]}",
            shipping_container_number=f"{MARKER}-CONTA-{uuid.uuid4().hex[:6]}",
            shipment_date=date(2026, 1, 1),
            shipment_status="pending",
        )
        shipment_b = InboundShipment(
            id=str(uuid.uuid4()),
            shipment_number=f"{MARKER}-SHB-{uuid.uuid4().hex[:6]}",
            shipping_container_number=f"{MARKER}-CONTB-{uuid.uuid4().hex[:6]}",
            shipment_date=date(2026, 1, 1),
            shipment_status="pending",
        )
        env.db.add_all([shipment_a, shipment_b])
        env.db.flush()

        wh_code = _warehouse_code(env, env.warehouse_ref)
        number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        _seed_legacy_row(
            env,
            spo_number=number,
            spo_line_number=1,
            location_code=wh_code,
            allocated_quantity=29,
            quantity_received=0,
            line_status="open",
            inbound_shipment_id=shipment_a.id,
        )
        _seed_legacy_row(
            env,
            spo_number=number,
            spo_line_number=2,
            location_code=wh_code,
            allocated_quantity=18,
            quantity_received=0,
            line_status="open",
            inbound_shipment_id=shipment_b.id,
        )

        line1 = _spo_line(env, warehouse_ref=env.warehouse_ref, qty_ordered=29, qty_received=0, line_number=1)
        line2 = _spo_line(env, warehouse_ref=env.warehouse_ref, qty_ordered=18, qty_received=0, line_number=2)
        record = _spo_record(
            env, number=number, lines=[line1, line2], supplier_ref=env.supplier_ref
        )

        with caplog.at_level(logging.INFO, logger=_SUPERSEDE_LOGGER):
            res = env.post(INGEST_SPO, [record])

        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert "shipment_merged" in (entry.get("warnings") or []), entry

        rows = _spo_rows(env, number)
        for row in rows:
            assert str(row["inbound_shipment_id"]) == str(shipment_a.id), row

        assert (
            str(shipment_b.id) in caplog.text or shipment_b.shipment_number in caplog.text
        ), caplog.text


# ============================================================================ #
# AC-X17 (D30)
# ============================================================================ #
class TestAcX17SupersedeNeedsDeletePermission:
    """AC-X17 (D30). Only a principal holding `scm.shipping_orders.delete`
    may have the supersede actually DELETE the xlsx row; a principal with
    only `.edit` still gets the full carry (receipt, links) but the row is
    CLOSED, annotated and warned instead. Both cases log at INFO.
    """

    def _seed_ac_x1_fixture(self, env):
        wh_code = _warehouse_code(env, env.warehouse_ref)
        number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        legacy = _seed_legacy_row(
            env,
            spo_number=number,
            spo_line_number=1,
            location_code=wh_code,
            allocated_quantity=47,
            quantity_received=47,
            line_status="closed",
        )
        picking_line = _picking_line_pointing_at(env, legacy.id)
        claim = _order_link_claim_pointing_at(env, legacy.id, number)
        link = _order_inquiry_link_pointing_at(env, legacy.id)
        line1 = _spo_line(
            env, warehouse_ref=env.warehouse_ref, qty_ordered=29, qty_received=0, line_number=1
        )
        line2 = _spo_line(
            env, warehouse_ref=env.warehouse_ref, qty_ordered=18, qty_received=0, line_number=2
        )
        record = _spo_record(
            env, number=number, lines=[line1, line2], supplier_ref=env.supplier_ref
        )
        return number, legacy, picking_line, claim, link, record, line1, line2

    def test_without_delete_permission_the_xlsx_row_is_closed_not_deleted(self, env, caplog):
        """AC-X17, without `.delete`. Receipts carry and links move exactly
        as AC-X1/AC-X2, but the xlsx row is CLOSED, its `allocation_notes`
        reads `superseded by <DocKey>`, and the record warns
        `superseded_closed_only`.

        RED today: D30 does not exist - the service has no notion of the
        calling principal's grants at all, so the supersede deletes the row
        unconditionally regardless of the caller's permissions. The xlsx
        row's id is gone entirely, not closed, `allocation_notes` is never
        set, and no `superseded_closed_only` warning nor INFO log line
        exists.
        """
        number, legacy, picking_line, claim, link, record, line1, line2 = (
            self._seed_ac_x1_fixture(env)
        )
        user_id = _seed_principal_with_permissions(env, ["scm.shipping_orders.edit"])

        with caplog.at_level(logging.INFO, logger=_SUPERSEDE_LOGGER):
            with _as_principal(user_id):
                res = env.post(INGEST_SPO, [record])

        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert "superseded_closed_only" in (entry.get("warnings") or []), entry

        rows = _spo_rows(env, number)
        by_id = {str(r["id"]): r for r in rows}
        assert str(legacy.id) in by_id, "without .delete the xlsx row must be closed, not removed"
        closed_row = by_id[str(legacy.id)]
        assert closed_row["line_status"] == "closed"
        assert closed_row["allocation_notes"] == f"superseded by {record['source_ref']}", closed_row

        by_ref = {r["source_ref"]: r for r in rows if r["source_ref"]}
        target_id = str(by_ref[line1["source_ref"]]["id"])

        picking_line_alloc = env.db.execute(
            text("SELECT spo_allocation_id FROM picking_lines WHERE id = :id"),
            {"id": picking_line.id},
        ).scalar()
        claim_alloc = env.db.execute(
            text("SELECT spo_allocation_id FROM order_link_claim WHERE id = :id"),
            {"id": claim.id},
        ).scalar()
        link_alloc = env.db.execute(
            text("SELECT spo_allocation_id FROM order_inquiry_links WHERE id = :id"),
            {"id": link.id},
        ).scalar()
        assert str(picking_line_alloc) == target_id
        assert str(claim_alloc) == target_id
        assert str(link_alloc) == target_id

        assert str(legacy.id) in caplog.text, caplog.text

    def test_with_delete_permission_the_xlsx_row_is_deleted_as_ac_x1(self, env, caplog):
        """AC-X17, with `.delete` held too: AC-X1's own behaviour (deleted),
        no `superseded_closed_only` warning, and the supersede still logs
        at INFO.

        RED today: the row IS already deleted regardless of permissions
        (D30 doesn't check anything yet), so this half is a live control -
        only the INFO-log assertion is red (no logging exists at all yet).
        """
        number, legacy, picking_line, claim, link, record, line1, line2 = (
            self._seed_ac_x1_fixture(env)
        )
        user_id = _seed_principal_with_permissions(
            env, ["scm.shipping_orders.edit", "scm.shipping_orders.delete"]
        )

        with caplog.at_level(logging.INFO, logger=_SUPERSEDE_LOGGER):
            with _as_principal(user_id):
                res = env.post(INGEST_SPO, [record])

        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert "superseded_closed_only" not in (entry.get("warnings") or []), entry

        rows = _spo_rows(env, number)
        assert len(rows) == 2, "with .delete held the xlsx row must be gone, AC-X1's own shape"
        assert str(legacy.id) not in {str(r["id"]) for r in rows}

        assert str(legacy.id) in caplog.text, caplog.text


# ============================================================================ #
# AC-X18 (D28a)
# ============================================================================ #
class TestAcX18GroupAwareRecomputeForAutocountOwnedLines:
    def test_a_repointed_picking_lines_total_is_redistributed_not_dumped_on_one_line(self, env):
        """AC-X18 (D28a). After the AC-X1 supersede (line 1 = 29, line 2 =
        18), one picking line of 47 now points at line 1 (the group's own
        repointed GRN draw). Running `sync_received_for_spo_number(N)` and
        `sync_grn_received_to_spo(<that header>)` must leave line 1 at 29
        and line 2 at 18 - the group total (47) redistributed in Seq order,
        never 47 dumped onto line 1 alone. A sibling allocation whose
        `source_system` is `scm_upload`, with its own picking line of 5,
        still recomputes to 5 (D28's per-allocation rule, unaffected).

        RED today: D28a's group-aware recompute for `source_system=
        'autocount'` rows does not exist - both recompute methods still
        recompute PER ALLOCATION (`compute_received_for_allocation`, summing
        only the picking lines that point at THAT row): line 1 is
        overwritten to 47 (the whole picking line's quantity, since it is
        the only one pointing at line 1) - never 29.
        """
        from app.services.procurement_service import PickingHeaderService

        wh_code = _warehouse_code(env, env.warehouse_ref)
        number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        _seed_legacy_row(
            env,
            spo_number=number,
            spo_line_number=1,
            location_code=wh_code,
            allocated_quantity=47,
            quantity_received=47,
            line_status="closed",
        )
        line1 = _spo_line(
            env, warehouse_ref=env.warehouse_ref, qty_ordered=29, qty_received=0, line_number=1
        )
        line2 = _spo_line(
            env, warehouse_ref=env.warehouse_ref, qty_ordered=18, qty_received=0, line_number=2
        )
        record = _spo_record(
            env, number=number, lines=[line1, line2], supplier_ref=env.supplier_ref
        )
        res = env.post(INGEST_SPO, [record])
        assert res.status_code == 200, res.text

        rows = {r["source_ref"]: r for r in _spo_rows(env, number)}
        line1_id = rows[line1["source_ref"]]["id"]
        line2_id = rows[line2["source_ref"]]["id"]

        header = PickingHeader(
            id=str(uuid.uuid4()),
            company_id=env.company_a,
            picking_number=unique_code(MARKER),
            picking_type="goods_received",
            picking_status="approved",
            spo_number=number,
        )
        env.db.add(header)
        env.db.flush()
        product_id = env.refs.resolve(entity_type="products", source_ref=env.product_ref)
        env.db.add(
            PickingLine(
                id=str(uuid.uuid4()),
                company_id=env.company_a,
                picking_header_id=header.id,
                spo_allocation_id=line1_id,
                product_id=product_id,
                quantity_expected=47,
                quantity_picked=47,
            )
        )
        env.db.flush()

        # A sibling allocation (scm_upload), unrelated to the group above,
        # with its own picking line - the D28 per-allocation rule must be
        # left untouched by the D28a change.
        product2_id = env.refs.resolve(entity_type="products", source_ref=env.product2_ref)
        sibling = SPOAllocation(
            id=str(uuid.uuid4()),
            company_id=env.company_a,
            spo_number=number,
            spo_line_number=99,
            product_id=product2_id,
            allocated_quantity=5,
            quantity_received=0,
            line_status="open",
            receipt_status="pending",
            source_system="scm_upload",
        )
        env.db.add(sibling)
        env.db.flush()
        env.db.add(
            PickingLine(
                id=str(uuid.uuid4()),
                company_id=env.company_a,
                picking_header_id=header.id,
                spo_allocation_id=sibling.id,
                product_id=product2_id,
                quantity_expected=5,
                quantity_picked=5,
            )
        )
        env.db.flush()
        env.db.commit()

        svc = PickingHeaderService(env.db)
        svc.sync_grn_received_to_spo(header.id)
        svc.sync_received_for_spo_number(number)

        env.db.expire_all()
        final = (
            env.db.execute(
                text("SELECT id, quantity_received FROM spo_allocations WHERE spo_number = :n"),
                {"n": number},
            )
            .mappings()
            .all()
        )
        by_id = {str(r["id"]): r["quantity_received"] for r in final}

        assert by_id[str(line1_id)] == 29, (
            f"line 1 must recompute to 29 (its own share of the group), not 47 - "
            f"got {by_id[str(line1_id)]}"
        )
        assert by_id[str(line2_id)] == 18, by_id
        assert by_id[str(sibling.id)] == 5, by_id


# ============================================================================ #
# AC-X19 (S4)
# ============================================================================ #
class TestAcX19DependantsWithNullCompanyIdStillRepoint:
    def test_a_null_company_claim_and_link_still_repoint_to_line_1(self, env):
        """AC-X19 (S4). The xlsx row's `order_link_claim` and
        `order_inquiry_links` dependants carry `company_id` NULL (both
        columns are nullable); after the supersede both must still point at
        line 1, not NULL.

        RED today: `repoint_allocation_dependants`'s query is
        `if company_id: query.filter(model.company_id == company_id)` - SQL
        equality against NULL is never true, so a NULL-company dependant is
        excluded from the move entirely. Confirmed live: the failure mode is
        even sharper than a stale FK - `order_inquiry_links` carries
        `ck_order_inquiry_links_one_target` (exactly one of `po_line_id` /
        `spo_allocation_id` set), so when the superseded row is then DELETED
        and its `ON DELETE SET NULL` fires on the un-repointed link, the
        UPDATE that nulls `spo_allocation_id` violates the CHECK constraint
        outright and the whole push 500s with an uncaught `IntegrityError`
        instead of the record answering a clean per-record verdict.

        Forced NULL via a raw UPDATE after insert, not via the constructor:
        `company_scope`'s `before_insert` auto-stamp silently overwrites an
        explicit `company_id=None` with the ambient scope's own company on
        flush (confirmed live) - a fixture that let it do that would pass
        for the wrong reason, the dependant never actually being NULL.
        """
        wh_code = _warehouse_code(env, env.warehouse_ref)
        number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        legacy = _seed_legacy_row(
            env,
            spo_number=number,
            spo_line_number=1,
            location_code=wh_code,
            allocated_quantity=47,
            quantity_received=47,
            line_status="closed",
        )
        claim = OrderLinkClaim(
            company_id=env.company_a,
            so_number=f"{MARKER}-SO-{uuid.uuid4().hex[:8]}",
            po_number=number,
            source="autocount",
            spo_allocation_id=legacy.id,
        )
        env.db.add(claim)
        env.db.flush()
        env.db.execute(
            text("UPDATE order_link_claim SET company_id = NULL WHERE id = :id"),
            {"id": claim.id},
        )
        env.db.flush()
        link = _order_inquiry_link_pointing_at(env, legacy.id, null_company=True)

        line1 = _spo_line(
            env, warehouse_ref=env.warehouse_ref, qty_ordered=29, qty_received=0, line_number=1
        )
        line2 = _spo_line(
            env, warehouse_ref=env.warehouse_ref, qty_ordered=18, qty_received=0, line_number=2
        )
        record = _spo_record(
            env, number=number, lines=[line1, line2], supplier_ref=env.supplier_ref
        )

        res = env.post(INGEST_SPO, [record])
        assert res.status_code == 200, res.text

        rows = {r["source_ref"]: r for r in _spo_rows(env, number)}
        target_id = str(rows[line1["source_ref"]]["id"])

        claim_alloc = env.db.execute(
            text("SELECT spo_allocation_id FROM order_link_claim WHERE id = :id"),
            {"id": claim.id},
        ).scalar()
        link_alloc = env.db.execute(
            text("SELECT spo_allocation_id FROM order_inquiry_links WHERE id = :id"),
            {"id": link.id},
        ).scalar()

        assert claim_alloc is not None and str(claim_alloc) == target_id, claim_alloc
        assert link_alloc is not None and str(link_alloc) == target_id, link_alloc


# ============================================================================ #
# AC-X12
# ============================================================================ #
class TestAcX12ContractListsLinesSuperseded:
    def test_the_external_contract_names_lines_superseded_in_the_verdict_vocabulary(self, env):
        """AC-X12. `GET /api/v1/external/contract`'s verdict/warning note lists
        `lines.superseded` among the shipping-order line-outcome vocabulary.

        RED today: the note only ever documents `adopted` / `created` /
        `updated` / `deleted` / `cancelled` - `superseded` is nowhere in it
        yet (`app/api/v1/external/contract.py` unchanged).
        """
        res = env.client.get("/api/v1/external/contract")
        assert res.status_code == 200, res.text
        assert "superseded" in res.text, "contract note must list lines.superseded"


# ============================================================================ #
# AC-X22 (S9)
# ============================================================================ #
class TestAcX22RecomputeNeverCrossesCompanyScope:
    def test_sync_received_for_spo_number_under_company_a_never_writes_company_b(self, env):
        """AC-X22 (S9). Company B holds an allocation sharing the SAME
        `spo_number` as company A's, with its own picking line; calling
        `sync_received_for_spo_number(N)` UNDER COMPANY A's SCOPE must
        never write company B's row.

        RED today: `sync_received_for_spo_number` queries
        `self.db.query(SPOAllocation).filter(SPOAllocation.spo_number.
        isnot(None)).all()` with no explicit `company_id` predicate of its
        own - it relies ENTIRELY on whatever ambient ORM scope the caller's
        session happens to carry. Called here under company A's scope, the
        ambient auto-filter is exactly what should stop company B's row
        being read at all; if it does not, company B's row is recomputed
        too - see the assertion for the actual observed value.
        """
        from app.models.base import set_company_scope
        from app.models.company import Company
        from app.services.procurement_service import PickingHeaderService

        number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        product_id = env.refs.resolve(entity_type="products", source_ref=env.product_ref)

        row_a = SPOAllocation(
            id=str(uuid.uuid4()),
            company_id=env.company_a,
            spo_number=number,
            spo_line_number=1,
            product_id=product_id,
            allocated_quantity=10,
            quantity_received=0,
            line_status="open",
            receipt_status="pending",
            source_system="scm_upload",
        )
        env.db.add(row_a)
        env.db.flush()

        other = Company(
            id=str(uuid.uuid4()),
            name=f"{MARKER} B {uuid.uuid4().hex[:6]}",
            code=unique_code(MARKER)[:10],
        )
        env.db.add(other)
        env.db.flush()
        company_b = str(other.id)

        row_b = SPOAllocation(
            id=str(uuid.uuid4()),
            company_id=company_b,
            spo_number=number,
            spo_line_number=1,
            product_id=product_id,
            allocated_quantity=10,
            quantity_received=0,
            line_status="open",
            receipt_status="pending",
            source_system="scm_upload",
        )
        env.db.add(row_b)
        env.db.flush()

        header = PickingHeader(
            id=str(uuid.uuid4()),
            company_id=company_b,
            picking_number=unique_code(MARKER),
            picking_type="goods_received",
            picking_status="approved",
            spo_number=number,
        )
        env.db.add(header)
        env.db.flush()
        env.db.add(
            PickingLine(
                id=str(uuid.uuid4()),
                company_id=company_b,
                picking_header_id=header.id,
                spo_allocation_id=row_b.id,
                product_id=product_id,
                quantity_expected=6,
                quantity_picked=6,
            )
        )
        env.db.flush()
        env.db.commit()

        set_company_scope(env.db, frozenset({env.company_a}))
        PickingHeaderService(env.db).sync_received_for_spo_number(number)

        env.db.expire_all()
        after_b = env.db.execute(
            text("SELECT quantity_received FROM spo_allocations WHERE id = :id"),
            {"id": row_b.id},
        ).scalar()
        assert after_b == 0, (
            "sync_received_for_spo_number under company A's scope must never "
            f"write company B's allocation - got {after_b}"
        )


# ============================================================================ #
# AC-X23 (D26 Seq order)
# ============================================================================ #
class TestAcX23DistributionFollowsLineNumberNotPayloadPosition:
    def test_reverse_payload_order_still_distributes_by_line_number(self, env):
        """AC-X23 (D26 Seq order, reviewer kill test). The AC-X1 push with
        its two lines sent in REVERSE payload order (line_number 2 first,
        then line_number 1) must still yield line 1 = 29 and line 2 = 18 -
        distribution follows `line_number`, not payload position.
        """
        wh_code = _warehouse_code(env, env.warehouse_ref)
        number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        _seed_legacy_row(
            env,
            spo_number=number,
            spo_line_number=1,
            location_code=wh_code,
            allocated_quantity=47,
            quantity_received=47,
            line_status="closed",
        )

        line1 = _spo_line(
            env, warehouse_ref=env.warehouse_ref, qty_ordered=29, qty_received=0, line_number=1
        )
        line2 = _spo_line(
            env, warehouse_ref=env.warehouse_ref, qty_ordered=18, qty_received=0, line_number=2
        )
        # REVERSE payload order: line_number 2 first, then 1.
        record = _spo_record(
            env, number=number, lines=[line2, line1], supplier_ref=env.supplier_ref
        )

        res = env.post(INGEST_SPO, [record])

        assert res.status_code == 200, res.text
        rows = {r["source_ref"]: r for r in _spo_rows(env, number)}
        first = rows[line1["source_ref"]]
        second = rows[line2["source_ref"]]
        assert first["quantity_received"] == 29, (
            "line_number 1 must carry 29 regardless of payload position", first
        )
        assert first["line_status"] == "closed"
        assert second["quantity_received"] == 18, (
            "line_number 2 must carry 18 regardless of payload position", second
        )
        assert second["line_status"] == "closed"


# ============================================================================ #
# AC-X24 (D26 max rule, AutoCount side)
# ============================================================================ #
class TestAcX24AutocountAboveTheCarryWins:
    def test_an_incoming_qty_received_above_the_carry_wins_on_that_line(self, env):
        """AC-X24 (D26 max rule, reviewer kill test). The xlsx row received
        10 of 47; a first push whose line 1 states `qty_received 25` and
        line 2 states `qty_received 0`. Line 1 must read 25 (AutoCount's
        own stated figure, above the 10 carried onto it, wins), line 2
        reads 0, and the group's total received never drops below the 10
        the xlsx row carried before the push.
        """
        wh_code = _warehouse_code(env, env.warehouse_ref)
        number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        _seed_legacy_row(
            env,
            spo_number=number,
            spo_line_number=1,
            location_code=wh_code,
            allocated_quantity=47,
            quantity_received=10,
            line_status="open",
        )

        line1 = _spo_line(
            env, warehouse_ref=env.warehouse_ref, qty_ordered=29, qty_received=25, line_number=1
        )
        line2 = _spo_line(
            env, warehouse_ref=env.warehouse_ref, qty_ordered=18, qty_received=0, line_number=2
        )
        record = _spo_record(
            env, number=number, lines=[line1, line2], supplier_ref=env.supplier_ref
        )

        res = env.post(INGEST_SPO, [record])

        assert res.status_code == 200, res.text
        rows = {r["source_ref"]: r for r in _spo_rows(env, number)}
        first = rows[line1["source_ref"]]
        second = rows[line2["source_ref"]]
        assert first["quantity_received"] == 25, first
        assert second["quantity_received"] == 0, second
        assert first["quantity_received"] + second["quantity_received"] >= 10, (
            "the group's total received must never drop below the 10 the xlsx "
            "row carried before the push",
            first,
            second,
        )


# ============================================================================ #
# AC-X26 (D27a)
# ============================================================================ #
class TestAcX26ShipmentLineStatusRefreshedAfterSupersede:
    def test_the_ingest_supersede_refreshes_the_linked_shipments_line_status(
        self, env, monkeypatch
    ):
        """AC-X26 (D27a). After the AC-X1 supersede,
        `InboundShipmentService.refresh_shipment_line_statuses` must run for
        the linked shipment - same as every other writer of allocations
        already does.

        RED today: `_supersede_xlsx_rows` never calls it at all.
        """
        import app.services.procurement_service as procurement_service

        calls: list[str] = []
        real = procurement_service.InboundShipmentService.refresh_shipment_line_statuses

        def _spy(self, shipment_id):
            calls.append(str(shipment_id))
            return real(self, shipment_id)

        monkeypatch.setattr(
            procurement_service.InboundShipmentService, "refresh_shipment_line_statuses", _spy
        )

        shipment = InboundShipment(
            id=str(uuid.uuid4()),
            shipment_number=f"{MARKER}-SH-{uuid.uuid4().hex[:6]}",
            shipping_container_number=f"{MARKER}-CONT-{uuid.uuid4().hex[:6]}",
            shipment_date=date(2026, 1, 1),
            shipment_status="pending",
        )
        env.db.add(shipment)
        env.db.flush()

        wh_code = _warehouse_code(env, env.warehouse_ref)
        number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        _seed_legacy_row(
            env,
            spo_number=number,
            spo_line_number=1,
            location_code=wh_code,
            allocated_quantity=47,
            quantity_received=47,
            line_status="closed",
            inbound_shipment_id=shipment.id,
        )
        line1 = _spo_line(
            env, warehouse_ref=env.warehouse_ref, qty_ordered=29, qty_received=0, line_number=1
        )
        line2 = _spo_line(
            env, warehouse_ref=env.warehouse_ref, qty_ordered=18, qty_received=0, line_number=2
        )
        record = _spo_record(
            env, number=number, lines=[line1, line2], supplier_ref=env.supplier_ref
        )

        res = env.post(INGEST_SPO, [record])
        assert res.status_code == 200, res.text

        assert str(shipment.id) in calls, (
            "the supersede must refresh the linked shipment's line statuses, "
            f"same as every other allocation writer - calls: {calls}"
        )
