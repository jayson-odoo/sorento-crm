"""FULFIL-SO-REMARK-CHANGES (owner, 26 Oct 2026 ~21:10): the planning Confirm's popup carries the
per-SO Remark too, so the per-order route (`POST /sales-orders/{id}/confirm`, the planning
sheet's "Confirm Project SO") takes `so_remark` like confirm-all and the email's SO table prints
it. Absent keeps today's computed default.

Card: `documentation/plans/scm/CARD-fulfil-so-remark-changes-27oct.md` (Q4, Q5).

TEST-FIRST. Driven through the route; the dispatch is captured (nothing is sent).
"""
from __future__ import annotations

from .test_oi_saved_line_email import _one_line_order, emails  # noqa: F401 - fixture
from .test_planning_change_apply_on_board import BASE, api, world  # noqa: F401 - fixtures
from .test_planning_changes import _line_payload

__all__ = ["api", "world", "emails"]


def _press(api, order, line, **extra):
    client, world = api
    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line.id, buy_qty="10")], **extra},
    )
    assert response.status_code == 200, response.text
    world.db.commit()


def test_the_per_order_confirm_prints_the_typed_remark_in_the_so_table(api, emails):
    _client, world = api
    order, line, _core = _one_line_order(world, "10")

    _press(api, order, line, so_remark="Customer moved the site date")

    [email] = emails
    [so_row] = email["orders"]
    assert so_row["remark"] == "Customer moved the site date"


def test_the_per_order_confirm_with_no_remark_keeps_the_computed_default(api, emails):
    _client, world = api
    order, line, _core = _one_line_order(world, "10")

    _press(api, order, line)

    [email] = emails
    [so_row] = email["orders"]
    assert so_row["remark"] == ""


def test_the_per_order_remark_is_capped_at_100_characters(api):
    client, world = api
    order, line, _core = _one_line_order(world, "10")

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line.id, buy_qty="10")], "so_remark": "x" * 101},
    )

    assert response.status_code == 422, response.text
