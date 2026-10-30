"""OI-AUTO-CONFIRM review round 1: item swap (AC-AC-10, blocker 3).

A link counts as cover only while its PO line / SPO allocation product is the row's CURRENT
item. Own file: the product-follow `api` / `world` fixtures differ from the handshake ones.
"""
from __future__ import annotations

from app.models.project_so import ACK_ACKNOWLEDGED, ACK_CHANGED
from app.services.project_order_inquiry_service import ProjectOrderInquiryService

from .test_oi_product_follow_apply import (  # noqa: F401  (fixtures + helpers)
    _apply,
    _live_order_rows,
    _swap_fixture,
    api,
)
from .test_planning_change_apply_on_board import world  # noqa: F401  (fixture)

def test_an_item_swap_keeps_the_old_link_but_it_no_longer_covers_the_row(api):
    fx = _swap_fixture(api, linked=True, acknowledged=True)
    link_id = str(fx["link"].id)

    response = _apply(fx)
    assert response.status_code == 200, response.text
    fx["world"].db.commit()
    fx["world"].db.expire_all()

    row = _live_order_rows(fx)[0]
    assert row.item_code == fx["new"].product_code
    assert row.ack_state == ACK_CHANGED, "the old product's PO does not cover the new item"
    assert row.acknowledged_at is None
    links = ProjectOrderInquiryService(fx["world"].db)._links_of(row.id)
    assert [str(link.id) for link in links] == [link_id], "the old link stays (R2)"


def test_an_item_swap_back_to_a_covering_document_is_done_again(api):
    """The link is judged against the row's CURRENT item at every write."""
    fx = _swap_fixture(api, linked=True, acknowledged=True)
    assert _apply(fx).status_code == 200
    db = fx["world"].db
    db.commit()
    row = _live_order_rows(fx)[0]
    svc = ProjectOrderInquiryService(db)

    row.item_code = fx["old"].product_code
    fx["line"].product_id = fx["old"].id
    db.flush()
    svc.auto_confirm([row.id])
    db.refresh(row)

    assert row.ack_state == ACK_ACKNOWLEDGED, "the old item is the row's item again"


