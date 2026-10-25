"""FULFIL-SO-REMARK review round 1: findings pinned as red tests (saved-line queue, batch
confirm, two SOs in one press, split rows)."""
from __future__ import annotations

import pytest

from tests.scm.test_line_splits_outputs import (  # noqa: F401 - fixtures reused
    D_A,
    D_B,
    _order as _split_order,
    _on,
    _save,
    _sp,
    emails as split_emails,
)
from .test_oi_saved_line_email import _borrow_from, _donor, emails  # noqa: F401
from .test_planning_change_apply_on_board import (  # noqa: F401
    BASE,
    _form_three,
    api,
    world,
)
from .test_planning_changes import _line_payload
from .test_so_remark_email import _confirm_all, _line_remarks, _seed_order

import sqlalchemy as sa


def _entry(order, payloads, **extra):
    return {"pso_id": order.id, "lines": payloads, **extra}


def _post_all(api, entries, **body):
    client, world = api
    response = client.post(
        f"{BASE}/fulfilment-planning/confirm-all", json={"orders": entries, **body}
    )
    assert response.status_code == 200, response.text
    assert all(r["ok"] for r in response.json()["results"]), response.text
    world.db.commit()


def _flat(emails_):
    return [l for e in emails_ for l in e["lines"]]


def _orders(emails_):
    return {o["so_number"]: o for e in emails_ for o in e["orders"]}


# 1. saved-line queue (planner's own remark, Borrow) keeps is_mockup
def test_r1a_own_remark_on_a_mockup_line_reads_mockup_comma_own_text(api, emails):
    _c, world = api
    order, lines = _seed_order(world, flags=[True, False])
    own = _line_payload(lines[0].id, buy_qty="5")
    own["remark"] = "Urgent"

    _post_all(api, [_entry(order, [own, _line_payload(lines[1].id, buy_qty="5")])])

    assert sorted(_line_remarks(_flat(emails) and {"lines": _flat(emails)})) == ["Mockup, Urgent", "ORDER"]


def test_r1b_a_borrow_mockup_line_in_a_mixed_choice_is_labelled(api, emails):
    _c, world = api
    donor = _donor(world, "BM")
    order, lines = _seed_order(world, flags=[True, False])
    borrow = _line_payload(lines[0].id, borrow=_borrow_from(world, donor, "5"),
                           amend_reason="Donor has it.")

    _post_all(api, [_entry(order, [borrow, _line_payload(lines[1].id, buy_qty="5")])])

    remarks = [l["remark"] for l in _flat(emails)]
    assert sum(r.startswith("Mockup, ORDER BACK") for r in remarks) == 1, remarks
    assert "ORDER" in remarks, remarks


def test_r1c_only_the_mockup_line_chosen_gives_so_remark_mockup_and_no_label(api, emails):
    _c, world = api
    order, lines = _seed_order(world, flags=[True, False])
    own = _line_payload(lines[0].id, buy_qty="5")
    own["remark"] = "Urgent"

    _post_all(api, [_entry(order, [own])])

    assert _orders(emails)[order.autocount_doc_no]["remark"] == "Mockup"
    assert [l["remark"] for l in _flat(emails)] == ["Urgent"]


# 2. batch confirm honours so_remark
def test_r2_a_planning_change_batch_confirm_prints_the_typed_so_remark(api, emails):
    fixture = _form_three(api)
    world = fixture["world"]
    world.db.execute(sa.text("UPDATE sales_orders SET ship_info = 'SPONSORSHIP' WHERE id = :i"),
                     {"i": fixture["core_so"].id})
    world.db.commit()
    emails.clear()

    client = fixture["client"]
    response = client.post(
        f"{BASE}/fulfilment-planning/confirm-all",
        json={"orders": [{
            "pso_id": str(fixture["order"].id), "so_remark": "Typed by staff",
            "lines": [_line_payload(fixture["lines"][0].id, buy_qty="25")],
        }], "batch_id": str(fixture["batch"].id)},
    )
    assert response.status_code == 200, response.text
    world.db.commit()

    assert emails, "premise: the batch confirm sends a purchasing email"
    assert [o["remark"] for e in emails for o in e["orders"]] == ["Typed by staff"]


# (single-order confirm route: ConfirmSupplyBody has no so_remark, so no case)


# 3. two SOs in one press, no leak
def test_r3_two_orders_in_one_press_each_keep_their_own_remark_and_labels(api, emails):
    _c, world = api
    order_a, lines_a = _seed_order(world, flags=[False, False])
    order_b, lines_b = _seed_order(world, ship_info="SPONSORSHIP", flags=[True, False])

    _post_all(api, [
        _entry(order_a, [_line_payload(l.id, buy_qty="5") for l in lines_a], so_remark="A typed"),
        _entry(order_b, [_line_payload(l.id, buy_qty="5") for l in lines_b]),
    ])

    orders = _orders(emails)
    assert orders[order_a.autocount_doc_no]["remark"] == "A typed"
    assert orders[order_b.autocount_doc_no]["remark"] == "Sponsorship"
    by_so = {}
    for l in _flat(emails):
        by_so.setdefault(l["so_number"], []).append(l["remark"])
    assert sorted(by_so[order_a.autocount_doc_no]) == ["ORDER", "ORDER"]
    assert sorted(by_so[order_b.autocount_doc_no]) == ["Mockup, ORDER", "ORDER"]


# 4. split rows of a mockup line
def test_r4_each_split_row_of_a_mockup_line_is_labelled_in_a_mixed_choice(api, split_emails):
    s = _split_order(api, [(10, 10, D_A), (20, 6, D_A)])
    s.db.execute(sa.text("UPDATE sales_order_lines SET line_remark = 'MOCK UP' WHERE id = :i"),
                 {"i": s.line[10].core_sales_order_line_id})
    s.db.commit()
    _save(s, {10: [_sp(4, D_A, on=_on(s, 10)), _sp(6, D_B, on=_on(s, 10))]})

    _post_all(api, [_entry(s.order, [_line_payload(l.id, buy_qty=str(l.qty)) for l in s.line.values()])])

    remarks = [l["remark"] for l in _flat(split_emails)]
    assert len(remarks) == 3, remarks
    assert sum(r.startswith("Mockup, ") for r in remarks) == 2, remarks
    assert sum("Mockup" not in r for r in remarks) == 1, remarks
