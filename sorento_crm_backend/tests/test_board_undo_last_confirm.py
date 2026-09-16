"""S2 (#979) - `undo_last_confirm` replay, the record action, refusal at commit.

RED for Phase 2 of `documentation/plans/scm/PLAN-board-undo-last-confirm.md`. Nothing in
this file has an implementation yet:

* `app.services.project_supply_undo_service` does not exist - importing `undo_last_confirm`
  raises `ModuleNotFoundError`, this file's "right reason" for most tests here.
* `app.services.record_actions` does not register `project_sales_order.undo_confirm` yet -
  `get_action(...)` returns `None`, and `POST /api/v1/pending-actions` answers 400 "Unknown
  action" rather than 202.
* `so_supply_decisions.undo_journal` does not exist either (S1's own column), so a decision
  read straight off the ORM has no journal to replay in the first place.

Postgres only, via `tests/_pg_fixture.py::blank_session` (through the `api` fixture imported
from `tests/test_so_supply_confirmation.py`), except the one batch-fork test, which reuses
`tests/test_planning_change_apply_on_board.py`'s own seeding against the REAL local database
(rolled back) - `scm.committed_v` is a view the blank scratch schema does not carry. Every row
is seeded behind the `ZZT` marker; nothing is borrowed from an existing table.

Testing seam agreed in the PLAN ("Testing seams"): exact restore is proven by snapshotting the
nine tables the confirm write-set touches to plain dicts (keyed by pk, `updated_at` dropped)
before the SECOND confirm, then diffing after undo - never asserting field by field, which
would silently miss a table the coder's replay forgot.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from app.models.procurement import PurchaseOrder, PurchaseOrderLine
from app.models.project_so import (
    INQUIRY_PLACED,
    IV_ORDER,
    AllocationClaim,
    OrderInquiry,
    OrderInquiryLink,
    OrderInquiryRow,
    SOLineAllocation,
    SOSupplyDecision,
    SOSupplyDecisionDraft,
)
from app.models.scm import OrderLinkClaim
from app.models.stock_transfer import StockTransfer
from app.services import project_line_draft_service
from app.services.error_handler import AppException

from .test_so_supply_confirmation import (  # noqa: F401  (api is a fixture)
    BASE,
    _core_line,
    _core_so,
    _line_payload,
    _product,
    _project_line,
    _project_so,
    _second_company,
    _stock,
    _suffix,
    _uid,
    _user,
    _warehouse,
    api,
)

MARKER = "zzt-undo-last-confirm"

SNAPSHOT_TABLES = [
    SOSupplyDecision.__table__,
    SOLineAllocation.__table__,
    AllocationClaim.__table__,
    StockTransfer.__table__,
    OrderInquiry.__table__,
    OrderInquiryRow.__table__,
    OrderInquiryLink.__table__,
    OrderLinkClaim.__table__,
    SOSupplyDecisionDraft.__table__,
]


def _snapshot(db, tables=SNAPSHOT_TABLES) -> dict:
    """Every row of `tables`, keyed by table then primary key, `updated_at` dropped.

    `undo_journal` is dropped too (UAC AC-UC-16, amended 17 Sep): R3 clears the
    REINSTATED decision's own journal on undo, so byte-equality on that one column is
    wrong by design - AC-UC-22 (which passes) is the test that pins the clearing itself.
    Only `so_supply_decisions` carries the column; popping it elsewhere is a no-op.
    """
    out: dict = {}
    for table in tables:
        pk_cols = [c.name for c in table.primary_key.columns]
        rows = db.execute(table.select()).mappings().all()
        keyed = {}
        for row in rows:
            row_dict = dict(row)
            row_dict.pop("updated_at", None)
            row_dict.pop("undo_journal", None)
            key = "|".join(str(row_dict[c]) for c in pk_cols)
            keyed[key] = row_dict
        out[f"{table.schema}.{table.name}" if table.schema else table.name] = keyed
    return out


def _po_line(db, world, *, qty, expected_date=None, qty_received="0", line_status="open"):
    po = PurchaseOrder(
        id=_uid(), company_id=world.company_id, po_number=f"ZZT-PO-{_suffix()}",
        issue_date=date.today(), status="active",
    )
    db.add(po)
    db.flush()
    line = PurchaseOrderLine(
        id=_uid(), company_id=world.company_id, purchase_order_id=po.id,
        product_id=world.product.id, warehouse_id=world.own_wh.id,
        qty_ordered=Decimal(str(qty)), qty_received=Decimal(str(qty_received)),
        expected_date=expected_date or date.today(), line_status=line_status,
    )
    db.add(line)
    db.flush()
    return po, line


def _link_with_claim(db, world, row, po_line, *, qty, auto=True, so_number="ZZT-SO"):
    claim = OrderLinkClaim(
        id=_uid(), company_id=world.company_id, so_number=so_number,
        po_number=po_line.purchase_order_id, item_code=world.product.product_code,
        source="order_inquiry", po_line_id=po_line.id,
    )
    db.add(claim)
    db.flush()
    link = OrderInquiryLink(
        id=_uid(), company_id=world.company_id, row_id=row.id, po_line_id=po_line.id,
        document=f"ZZT-{_suffix()}", qty=Decimal(str(qty)), linked_by=world.eling, auto=auto,
        claim_id=claim.id,
    )
    db.add(link)
    db.flush()
    return link, claim


def _confirm_linked_world(api, *, second_buy_qty):
    """One line, twice confirmed: rev1 raises+auto-links it (standing in for the raise-time
    cascade), rev2 re-confirms with `second_buy_qty` - "0" fully removes the link (and frees
    its claim), any other value settles the row in place with a qty/note change.

    Returns everything a test needs to assert against, before AND after the second confirm.
    """
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=200)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="20")
    order = _project_so(db, world.project, so_id=core_so.id)
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    first = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line.id, buy_qty="20")]},
    )
    assert first.status_code == 200, first.text
    decision1 = (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id)
        .one()
    )
    row = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id, OrderInquiryRow.verb == IV_ORDER)
        .one()
    )
    po, po_line = _po_line(db, world, qty=20)
    link, claim = _link_with_claim(db, world, row, po_line, qty=20, so_number=core_so.so_number)
    row.state = INQUIRY_PLACED
    db.commit()

    before = _snapshot(db)

    # The whole-line rule requires every component to sum to the line's OPEN qty (20):
    # the remainder not bought is Reserved from the pool, so `buy_qty` alone can move
    # (20 -> `second_buy_qty`) without the confirm being refused as unbalanced.
    remainder = Decimal("20") - Decimal(second_buy_qty)
    reserve = (
        [{"warehouse_id": world.pool_wh.id, "qty": str(remainder)}] if remainder > 0 else None
    )
    second = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line.id, buy_qty=second_buy_qty, reserve=reserve)]},
    )
    assert second.status_code == 200, second.text
    decision2 = (
        db.query(SOSupplyDecision)
        .filter(
            SOSupplyDecision.project_sales_order_id == order.id,
            SOSupplyDecision.revision_no == 2,
        )
        .one()
    )
    return {
        "client": client, "world": world, "db": db, "order": order, "line": line,
        "decision1": decision1, "decision2": decision2, "row": row, "link": link,
        "claim": claim, "po_line": po_line, "before": before,
    }


# --------------------------------------------------------------------------- AC-UC-16


def test_undo_restores_revision_one_column_for_column(api):
    fixture = _confirm_linked_world(api, second_buy_qty="15")
    db = fixture["db"]
    order = fixture["order"]

    from app.services.project_supply_undo_service import undo_last_confirm

    result = undo_last_confirm(db, order, actor_user_id=fixture["world"].eling)
    assert result["revision_no"] == fixture["decision2"].revision_no
    assert result["restored_to"] == fixture["decision1"].revision_no

    after = _snapshot(db)
    assert after == fixture["before"], "every seeded table must read back exactly as before"


# --------------------------------------------------------------------------- AC-UC-17


def test_undo_of_revision_one_leaves_no_active_decision_and_returns_the_drafts(api):
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="20")
    order = _project_so(db, world.project, so_id=core_so.id)
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    key = f"{core_so.id}|10|{world.product.product_code}|bkt"
    project_line_draft_service.save_draft(db, key, decision={"buy_qty": "20"}, actor_user_id=world.eling)
    db.commit()
    draft_id = (
        db.query(SOSupplyDecisionDraft)
        .filter(SOSupplyDecisionDraft.core_line_id == core_line.id)
        .one()
        .id
    )

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line.id, buy_qty="20")]},
    )
    assert response.status_code == 200, response.text
    decision = (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id)
        .one()
    )
    assert (
        db.query(SOSupplyDecisionDraft).filter(SOSupplyDecisionDraft.id == draft_id).first()
        is None
    ), "the confirm cleared the draft - the setup this test needs"

    from app.services.project_supply_undo_service import undo_last_confirm

    result = undo_last_confirm(db, order, actor_user_id=world.eling)
    assert result["restored_to"] is None, "revision 1 has no previous decision"

    assert (
        db.query(SOSupplyDecision).filter(SOSupplyDecision.project_sales_order_id == order.id).count()
        == 0
    )
    assert (
        db.query(OrderInquiryRow).filter(OrderInquiryRow.so_line_id == line.id).count() == 0
    )
    restored_draft = (
        db.query(SOSupplyDecisionDraft).filter(SOSupplyDecisionDraft.id == draft_id).first()
    )
    assert restored_draft is not None, "the planner's draft is back"
    assert restored_draft.decision == {"buy_qty": "20"}


# --------------------------------------------------------------------------- AC-UC-18


def test_undo_re_inserts_a_removed_link_and_its_claim_with_original_ids(api):
    fixture = _confirm_linked_world(api, second_buy_qty="0")
    db = fixture["db"]
    order = fixture["order"]
    link_id = fixture["link"].id
    claim_id = fixture["claim"].id

    assert db.query(OrderInquiryLink).filter(OrderInquiryLink.id == link_id).first() is None
    assert db.query(OrderLinkClaim).filter(OrderLinkClaim.id == claim_id).first() is None

    from app.services.project_supply_undo_service import undo_last_confirm

    undo_last_confirm(db, order, actor_user_id=fixture["world"].eling)

    restored_link = db.query(OrderInquiryLink).filter(OrderInquiryLink.id == link_id).one()
    assert restored_link.po_line_id == fixture["po_line"].id
    assert restored_link.qty == Decimal("20")
    assert restored_link.auto is True

    restored_claim = db.query(OrderLinkClaim).filter(OrderLinkClaim.id == claim_id).one()
    assert restored_claim.po_line_id == fixture["po_line"].id


# --------------------------------------------------------------------------- AC-UC-19


def test_undo_restores_a_settled_rows_note_previous_values_and_ack_stamps(api):
    fixture = _confirm_linked_world(api, second_buy_qty="15")
    db = fixture["db"]
    row_id = fixture["row"].id
    before_row = fixture["before"]["projects.order_inquiry_rows"][str(row_id)]

    db.expire_all()
    changed_row = db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row_id).one()
    assert changed_row.qty == Decimal("15"), "the settle actually changed it - the setup this test needs"
    assert changed_row.previous_qty == Decimal("20")

    from app.services.project_supply_undo_service import undo_last_confirm

    undo_last_confirm(db, fixture["order"], actor_user_id=fixture["world"].eling)

    db.expire_all()
    restored_row = db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row_id).one()
    assert restored_row.note == before_row["note"]
    assert restored_row.previous_qty == before_row["previous_qty"]
    assert restored_row.previous_delivery_date == before_row["previous_delivery_date"]
    assert restored_row.ack_state == before_row["ack_state"]
    assert restored_row.acknowledged_by == before_row["acknowledged_by"]
    assert restored_row.acknowledged_at == before_row["acknowledged_at"]
    assert restored_row.changed_at == before_row["changed_at"]
    assert restored_row.supply_decision_id == before_row["supply_decision_id"]


# --------------------------------------------------------------------------- AC-UC-20


def test_undo_clears_the_redirect_flag_and_re_inserts_the_removed_open_links(api):
    """A row linked to BOTH a fully-received document and a still-open one: the received
    document redirects the row to the pool and frees the open link (AC-RL-10..12,
    `_redirect_row_if_received`); undo restores the flag and the open link both."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=200)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="20")
    order = _project_so(db, world.project, so_id=core_so.id)
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    first = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line.id, buy_qty="20")]},
    )
    assert first.status_code == 200, first.text
    decision1 = (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id)
        .one()
    )
    row = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id, OrderInquiryRow.verb == IV_ORDER)
        .one()
    )
    _po_received, po_line_received = _po_line(
        db, world, qty=15, qty_received="15", line_status="open"
    )
    _po_open, po_line_open = _po_line(db, world, qty=5, qty_received="0", line_status="open")
    link_received, _claim_r = _link_with_claim(
        db, world, row, po_line_received, qty=15, so_number=core_so.so_number
    )
    link_open, _claim_o = _link_with_claim(
        db, world, row, po_line_open, qty=5, so_number=core_so.so_number
    )
    row.state = INQUIRY_PLACED
    db.commit()

    before = _snapshot(db)
    assert before["projects.order_inquiry_rows"][str(row.id)]["redirected_to_pool"] is False

    second = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line.id, buy_qty="20")]},
    )
    assert second.status_code == 200, second.text

    db.expire_all()
    redirected_row = db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row.id).one()
    assert redirected_row.redirected_to_pool is True, "the setup this test needs"
    assert (
        db.query(OrderInquiryLink).filter(OrderInquiryLink.id == link_open.id).first() is None
    ), "the open link was freed - the setup this test needs"
    assert (
        db.query(OrderInquiryLink).filter(OrderInquiryLink.id == link_received.id).first()
        is not None
    ), "the received link stays exactly as it was"

    from app.services.project_supply_undo_service import undo_last_confirm

    undo_last_confirm(db, order, actor_user_id=world.eling)

    after = _snapshot(db)
    assert after == before


# --------------------------------------------------------------------------- AC-UC-21


def test_undo_of_a_batch_confirm_returns_the_batch_to_pending_and_leaves_the_book():
    """AC-UC-21: R4 - no book rewind. Undo returns the planning-change batch's rows to
    `pending` and clears `applied_at`/`applied_by`/`result_json`, but the AutoCount book
    values (`sales_order_lines.qty_ordered` / `required_date`) the batch already applied
    are left exactly where the confirm put them.

    Reuses `tests/test_planning_change_apply_on_board.py`'s own seeding wholesale, the same
    way `test_board_undo_journal.py::test_a_batch_confirm_journals_the_batch_rows_and_header`
    does - its `world`/`api` are pytest fixtures registered under those names, which would
    collide with this file's own `api` import.
    """
    from app.models.base import company_scope
    from app.models.planning_change import PlanningChangeBatch, PlanningChangeRow
    from app.services import project_seed_service
    from app.services.project_service import register_project

    from .test_planning_change_apply_on_board import (
        MARKER as BATCH_MARKER,
        _World,
        _apply_from_board,
        _client as batch_client,
        _form_three,
        _product as batch_product,
        _real_db_session,
        _restore as batch_restore,
        _sorento as batch_sorento,
        _uid as batch_uid,
        _user as batch_user,
        _warehouse as batch_warehouse,
    )

    with _real_db_session() as db:
        company_id = batch_sorento(db)
        project_seed_service.run(db, company_id=company_id)
        actor = batch_user(db, f"{BATCH_MARKER} Cyndi")
        project = register_project(
            db, company_id=company_id, actor_user_id=actor, developer_party_id=None,
            title=f"{BATCH_MARKER} Undo Batch World 2",
        )
        product = batch_product(db)
        pool_wh = batch_warehouse(db, f"ZZT-BRW-{batch_uid()[:4]}", segment="dealer")
        own_wh = batch_warehouse(
            db, f"ZZT-IB-{batch_uid()[:4]}", segment="project", pool_warehouse_id=pool_wh.id
        )
        db.flush()
        db.commit()
        world = _World(db, company_id, actor, project, product, own_wh, pool_wh)

        client, originals = batch_client(db, actor)
        try:
            with company_scope(db, frozenset({company_id})):
                fixture = _form_three((client, world))
                response = _apply_from_board(fixture)
                assert response.status_code == 200, response.text

                core_1 = fixture["core_lines"][0]
                assert core_1.qty_ordered == Decimal("25")

                decision = (
                    db.query(SOSupplyDecision)
                    .filter(SOSupplyDecision.project_sales_order_id == fixture["order"].id)
                    .order_by(SOSupplyDecision.revision_no.desc())
                    .first()
                )
                batch_id = fixture["batch"].id

                from app.services.project_supply_undo_service import undo_last_confirm

                undo_last_confirm(db, fixture["order"], actor_user_id=actor)

                db.expire_all()
                batch_rows = (
                    db.query(PlanningChangeRow)
                    .filter(PlanningChangeRow.batch_id == batch_id)
                    .all()
                )
                assert batch_rows, "the batch's own rows must still exist"
                assert all(row.applied_state == "pending" for row in batch_rows)

                batch = db.query(PlanningChangeBatch).filter(PlanningChangeBatch.id == batch_id).one()
                assert batch.applied_at is None
                assert batch.applied_by is None
                assert batch.result_json is None

                db.refresh(core_1)
                assert core_1.qty_ordered == Decimal("25"), "R4: the book is NOT rewound"
        finally:
            batch_restore(originals)


# --------------------------------------------------------------------------- AC-UC-22


def test_after_an_undo_the_reinstated_revision_is_not_undoable(api):
    fixture = _confirm_linked_world(api, second_buy_qty="15")
    db = fixture["db"]
    order = fixture["order"]

    from app.services.project_supply_undo_service import undo_last_confirm

    undo_last_confirm(db, order, actor_user_id=fixture["world"].eling)

    db.expire_all()
    reinstated = db.query(SOSupplyDecision).filter(
        SOSupplyDecision.id == fixture["decision1"].id
    ).one()
    assert reinstated.state == "active"
    assert reinstated.undo_journal is None, "R3: one revision back, once"

    with pytest.raises(AppException) as exc_info:
        undo_last_confirm(db, order, actor_user_id=fixture["world"].eling)
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "no_journal"


# --------------------------------------------------------------------------- AC-UC-23/24/25


@pytest.mark.parametrize(
    "arm",
    ["manual_link_after", "actioned_after", "step3_link_inside"],
)
def test_purchasing_action_after_the_confirm_refuses_the_undo_but_the_confirms_own_link_does_not(
    api, arm
):
    """AC-UC-23/24/25, one rule at one seam over three arms: a manual link or an actioned
    row written AFTER the confirm refuses undo; the confirm's OWN step-3 borrow link,
    written inside the same transaction (`linked_at` not later than `confirmed_at`), does
    not."""
    from app.models.project_so import INQUIRY_ACTIONED

    fixture = _confirm_linked_world(api, second_buy_qty="15")
    db = fixture["db"]
    order = fixture["order"]
    world = fixture["world"]
    row = fixture["row"]
    decision2 = fixture["decision2"]

    db.expire_all()
    row = db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row.id).one()
    decision2 = db.query(SOSupplyDecision).filter(SOSupplyDecision.id == decision2.id).one()

    from app.services.project_supply_undo_service import undo_last_confirm

    if arm == "manual_link_after":
        po, po_line = _po_line(db, world, qty=15)
        db.add(
            OrderInquiryLink(
                id=_uid(), company_id=world.company_id, row_id=row.id, po_line_id=po_line.id,
                document=po.po_number, qty=Decimal("5"), linked_by=world.eling, auto=False,
                linked_at=decision2.confirmed_at + timedelta(minutes=1),
            )
        )
        db.commit()
        with pytest.raises(AppException) as exc_info:
            undo_last_confirm(db, order, actor_user_id=world.eling)
        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "manual_link"
    elif arm == "actioned_after":
        row.state = INQUIRY_ACTIONED
        row.actioned_at = decision2.confirmed_at + timedelta(minutes=1)
        db.commit()
        with pytest.raises(AppException) as exc_info:
            undo_last_confirm(db, order, actor_user_id=world.eling)
        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "actioned"
    else:
        po, po_line = _po_line(db, world, qty=15)
        db.add(
            OrderInquiryLink(
                id=_uid(), company_id=world.company_id, row_id=row.id, po_line_id=po_line.id,
                document=po.po_number, qty=Decimal("5"), linked_by=world.eling, auto=False,
                linked_at=decision2.confirmed_at,
            )
        )
        db.commit()
        before = _snapshot(db)
        result = undo_last_confirm(db, order, actor_user_id=world.eling)
        assert result["revision_no"] == decision2.revision_no


# --------------------------------------------------------------------------- AC-UC-26


def test_a_revision_without_a_journal_refuses(api):
    client, world = api
    db = world.db
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="20")
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    # A decision minted directly (no board route, no journal) - stands in for a pre-lane
    # revision or one minted by `uncover_lines`.
    decision = SOSupplyDecision(
        id=_uid(), company_id=world.company_id, project_sales_order_id=order.id,
        revision_no=1, state="active",
        line_snapshots=[{"line_no": 10, "project_line_id": line.id}],
        confirmed_by=world.eling, confirmed_at=datetime.utcnow(),
    )
    db.add(decision)
    db.commit()

    from app.services.project_supply_undo_service import undo_last_confirm

    with pytest.raises(AppException) as exc_info:
        undo_last_confirm(db, order, actor_user_id=world.eling)
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "no_journal"


# --------------------------------------------------------------------------- AC-UC-27


def test_the_record_action_is_registered_reversible_with_confirms_permission_and_commits_on_lapse(
    api,
):
    from app.models.sla import SlaFormAction
    from app.services.form_action_grace import WINDOW_REVERSIBLE
    from app.services.form_action_registry import get_action
    from app.services.form_action_service import FormActionService

    action = get_action("project_sales_order.undo_confirm")
    assert action is not None, "the record action must be registered"
    assert action.entity_types == ("project_sales_order",)
    assert action.window == WINDOW_REVERSIBLE
    assert action.permission == "projects.projects.edit"

    client, world = api
    db = world.db
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="20")
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    confirm = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line.id, buy_qty="20")]},
    )
    assert confirm.status_code == 200, confirm.text
    decision = (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id)
        .one()
    )

    park = client.post(
        "/api/v1/pending-actions",
        json={
            "action_key": "project_sales_order.undo_confirm",
            "entity_type": "project_sales_order",
            "entity_id": str(order.id),
            "payload": {"decision_id": str(decision.id)},
        },
    )
    assert park.status_code == 202, park.text
    parked = park.json()

    db.query(SlaFormAction).filter(SlaFormAction.id == parked["id"]).update(
        {"commit_at": datetime.utcnow() - timedelta(seconds=1)}, synchronize_session=False,
    )
    db.commit()

    outcome = FormActionService(db).commit_due()
    assert outcome["committed"] >= 1, "the sweep must commit an undo nobody is watching"

    db.expire_all()
    assert (
        db.query(SOSupplyDecision).filter(SOSupplyDecision.project_sales_order_id == order.id).count()
        == 0
    ), "revision 1's own undo leaves the order with no active decision"


# --------------------------------------------------------------------------- AC-UC-28


def test_a_confirm_written_during_the_countdown_makes_the_undo_refuse_superseded(api):
    fixture = _confirm_linked_world(api, second_buy_qty="15")
    db = fixture["db"]
    order = fixture["order"]
    world = fixture["world"]

    from app.services.project_supply_undo_service import undo_last_confirm

    # The pending action was created naming decision1 - stale by the time it commits,
    # because decision2 (the newer confirm) is now the active one.
    with pytest.raises(AppException) as exc_info:
        undo_last_confirm(
            db, order, actor_user_id=world.eling, expected_decision_id=str(fixture["decision1"].id)
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "superseded"


# --------------------------------------------------------------------------- AC-UC-29


def test_undo_writes_an_audit_delete_for_the_undone_decision(api):
    fixture = _confirm_linked_world(api, second_buy_qty="15")
    db = fixture["db"]
    order = fixture["order"]
    decision2_id = fixture["decision2"].id

    from app.models.audit import AuditLog

    from app.services.project_supply_undo_service import undo_last_confirm

    undo_last_confirm(db, order, actor_user_id=fixture["world"].eling)

    audit_row = (
        db.query(AuditLog)
        .filter(
            AuditLog.entity_type == "project_so_supply_decisions",
            AuditLog.entity_id == str(decision2_id),
            AuditLog.action == "DELETE",
        )
        .first()
    )
    assert audit_row is not None, "the undone decision's own DELETE must be audited"


# --------------------------------------------------------------------------- AC-UC-30


def test_a_view_only_user_cannot_create_the_undo_action(api):
    from app.models.sla import SlaFormAction
    from app.services.user_service import UserPermissionService

    client, world = api
    db = world.db
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="20")
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    confirm = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line.id, buy_qty="20")]},
    )
    assert confirm.status_code == 200, confirm.text
    decision = (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id)
        .one()
    )

    original = UserPermissionService.check_user_has_permission
    try:
        UserPermissionService.check_user_has_permission = (
            lambda self, uid, slug: slug != "projects.projects.edit"
        )
        response = client.post(
            "/api/v1/pending-actions",
            json={
                "action_key": "project_sales_order.undo_confirm",
                "entity_type": "project_sales_order",
                "entity_id": str(order.id),
                "payload": {"decision_id": str(decision.id)},
            },
        )
        assert response.status_code == 403, response.text
    finally:
        UserPermissionService.check_user_has_permission = original

    assert (
        db.query(SlaFormAction)
        .filter(SlaFormAction.source_entity_id == str(order.id))
        .count()
        == 0
    ), "no pending row was parked"


# --------------------------------------------------------------------------- AC-UC-31


def test_another_companys_user_gets_404_on_undo():
    """The record action's own `execute` resolves the order through
    `ProjectSupplyService.get_order` under company scope (PLAN "Permissions and scope") -
    called directly here (bypassing the pending-action machinery) so this test does not
    depend on the exact private wiring inside `record_actions.py`, only on the CONTRACT it
    owes: a foreign company's order 404s before anything changes.
    """
    from app.models.base import company_scope
    from app.services import project_seed_service
    from app.services.form_action_registry import get_action
    from app.services.project_service import register_project

    from .test_so_supply_confirmation import _client, _restore, _sorento
    from ._pg_fixture import blank_session

    with blank_session() as db:
        sorento_id = _sorento(db)
        other_id = _second_company(db)
        project_seed_service.run(db, company_id=sorento_id)
        project_seed_service.run(db, company_id=other_id)

        eling = _user(db, f"{MARKER} Eling")
        farah = _user(db, f"{MARKER} Farah")
        other_project = register_project(
            db, company_id=other_id, actor_user_id=farah, developer_party_id=None,
            title=f"{MARKER} Mocha Residences",
        )
        other_product = _product(db)
        other_wh = _warehouse(db, f"ZZT-OTHWH-{_suffix()}")
        other_core_so = _core_so(db, other_id)
        other_core_line = _core_line(
            db, other_core_so, other_product, other_wh, qty_ordered="10"
        )
        other_order = _project_so(db, other_project, so_id=other_core_so.id)
        other_line = _project_line(
            db, other_order, line_no=10, product=other_product, core_line=other_core_line
        )
        db.commit()

        client, originals = _client(db, farah)
        try:
            with company_scope(db, frozenset({other_id})):
                confirm = client.post(
                    f"{BASE}/sales-orders/{other_order.id}/confirm",
                    json={"lines": [_line_payload(other_line.id, buy_qty="10")]},
                )
                assert confirm.status_code == 200, confirm.text
                decision = (
                    db.query(SOSupplyDecision)
                    .filter(SOSupplyDecision.project_sales_order_id == other_order.id)
                    .one()
                )
        finally:
            _restore(originals)

        action = get_action("project_sales_order.undo_confirm")
        assert action is not None, "the record action must be registered"

        with company_scope(db, frozenset({sorento_id})):
            with pytest.raises(AppException) as exc_info:
                action.execute(
                    db,
                    {"entity_id": str(other_order.id), "decision_id": str(decision.id)},
                )
            assert exc_info.value.status_code == 404

        db.expire_all()
        # The read has to run inside the OWNING company's own scope, the same as the
        # seed above: a fail-closed scope filter (no scope active at all) returns zero
        # rows for every company, and `.one()` would raise regardless of whether the
        # 404 above left the decision untouched or not.
        with company_scope(db, frozenset({other_id})):
            untouched = (
                db.query(SOSupplyDecision)
                .filter(SOSupplyDecision.project_sales_order_id == other_order.id)
                .one()
            )
            assert untouched.state == "active"
            assert untouched.revision_no == 1
