"""AC-RL-15 (`PLAN-oi-replan-received-links.md` S3): `committed_v`'s confirmed leg must
not net a redirected row's quantity - the goods it names shipped to other orders a year
ago, and reading them as this line's own cover would silently understate what purchasing
still has to buy.

Reuses `tests/test_order_inquiry_handshake.py`'s harness (`world` / `api`,
`_raise_one_row`, `_settle`, `_project_committed`) and `tests/test_order_inquiry_draft_
links.py`'s `_redirected_fixture` (the settle-seam fixture builder), for the reason both
those files already state: one seeding chain, and the real database because `scm.
committed_v` lives in the migrated schema, not the blank scratch one.

TEST-FIRST: `demand.py`'s confirmed leg has no `redirected_to_pool` exclusion yet, so the
red state is `committed_v` netting the redirected row's own qty ON TOP OF the fresh row's,
never an import error.
"""
from __future__ import annotations

from decimal import Decimal

from tests.test_order_inquiry_draft_links import _redirected_fixture
from tests.test_order_inquiry_handshake import _project_committed, api, world

__all__ = ["api", "world"]  # re-exported fixtures; keeps linters from calling them unused


def test_committed_v_ignores_redirected_row(api):
    """The redirected row contributes nothing - neither its own qty nor its links - and
    the fresh row contributes its full replanned need."""
    _client, world = api

    _redirected_fixture(api)

    assert _project_committed(world, planned=False) == Decimal("220")


def _form_redirected_row(world, *, qty, linked_qty, redirected: bool):
    """AC-RL-15 rewrite (B1, code review 17 Sep): the FORM leg's own shape - a row
    with NO supply decision at all (`supply_decision_id IS NULL`), naming its
    product and location by CODE the way the CS form does - never via `_settle`
    (`ProjectSupplyService.confirm()`), whose own `supply_decision_id` points at a
    revision the confirmed leg's `d.state = 'active'` join ALREADY drops for an
    unrelated reason. This is what makes the row's exclusion genuinely turn on
    `redirected_to_pool` and nothing else - the kill test the reviewer's finding
    asked for."""
    from app.models.project_so import (
        ACK_ACKNOWLEDGED,
        INQUIRY_PARTLY_LINKED,
        IV_ORDER,
        OrderInquiry,
        OrderInquiryLink,
        OrderInquiryRow,
    )

    from tests.test_order_inquiry_handshake import _open_po_line, _project_so, _uid

    order = _project_so(world.db, world.project)
    inquiry = OrderInquiry(
        id=_uid(), company_id=world.company_id, project_sales_order_id=order.id,
        state="raised",
    )
    world.db.add(inquiry)
    world.db.flush()
    row = OrderInquiryRow(
        id=_uid(), company_id=world.company_id, order_inquiry_id=inquiry.id,
        so_line_id=None, item_code=world.product.product_code,
        stock_location=world.warehouse.warehouse_code, qty=Decimal(str(qty)),
        verb=IV_ORDER, state=INQUIRY_PARTLY_LINKED, ack_state=ACK_ACKNOWLEDGED,
        redirected_to_pool=redirected,
    )
    world.db.add(row)
    world.db.flush()
    if Decimal(str(linked_qty)) > 0:
        _po, po_line = _open_po_line(world, qty=linked_qty)
        world.db.add(OrderInquiryLink(
            id=_uid(), company_id=world.company_id, row_id=row.id,
            po_line_id=po_line.id, document=_po.po_number, qty=Decimal(str(linked_qty)),
        ))
        world.db.flush()
    world.db.commit()
    return row


def test_committed_v_ignores_a_form_raised_redirected_row(api):
    """AC-RL-15 rewrite (B1): the VIEW's (`scm.committed_v`, `planned=False`) own
    form leg must exclude a redirected row - toggling ONLY `redirected_to_pool` on
    the SAME row must move the read figure by exactly the row's own unlinked
    (owed) quantity, 24 (qty 182, linked 158)."""
    _client, world = api

    row = _form_redirected_row(world, qty="182", linked_qty="158", redirected=False)
    with_it_counted = _project_committed(world, planned=False)

    row.redirected_to_pool = True
    world.db.commit()
    with_it_excluded = _project_committed(world, planned=False)

    assert with_it_counted - with_it_excluded == Decimal("24")
    assert with_it_excluded == Decimal("0")


def test_committed_v_horizon_and_need_dates_ignore_a_form_raised_redirected_row(api):
    """AC-RL-15b (B2): the LIVE horizon path every reorder plan run actually reads
    (`horizon_committed_select_sql`) and its date companion (`horizon_project_need_
    dates_sql`) must ALSO exclude a redirected row - not only the view AC-RL-15
    pins. Both build their SQL fresh at call time off the module's own `NOT_
    REDIRECTED_SQL`, so both are genuinely killed by emptying that constant
    (verified with a throwaway monkeypatch, never committed) - unlike `scm.
    committed_v`, which is a frozen migration body a Python-level patch cannot
    reach."""
    from sqlalchemy import text

    from app.services.scm import demand

    _client, world = api
    row = _form_redirected_row(world, qty="182", linked_qty="158", redirected=True)

    committed = Decimal(str(
        world.db.execute(
            text(
                f"SELECT COALESCE(SUM(project_committed), 0) FROM "
                f"({demand.horizon_committed_select_sql()}) cv WHERE cv.product_id = :pid"
            ),
            {"pid": str(world.product.id), "horizon": None, "horizon_start": None},
        ).scalar() or 0
    ))
    assert committed == Decimal("0"), "the redirected row must not reach the plan's own figure"

    needed = world.db.execute(
        text(
            f"SELECT needed FROM ({demand.horizon_project_need_dates_sql()}) nd "
            "WHERE nd.product_id = :pid"
        ),
        {"pid": str(world.product.id), "horizon": None},
    ).scalar()
    assert needed is None, "a redirected row must date nothing either"

