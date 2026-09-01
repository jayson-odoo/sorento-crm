"""AC-1.7 (`PLAN-scm-reorder-oi-feedback-1sep.md` S1, G6): the `order_inquiry_changed_with_links`
automation trigger.

Fires when a CS amendment settles a row IN PLACE and that row already carries a link;
fires nothing for a linkless amendment. Dispatched from
`ProjectOrderInquiryService._dispatch_changed_with_links`, called by `_settle_row_in_place`
- the one place a row's quantity/date changes without a fresh raise.

Reuses `tests/test_order_inquiry_handshake.py`'s harness wholesale (`world` / `api`,
`_raise_one_row`, `_open_po_line`, `_settle`), for the same reason the sibling draft-links
suite does: one seeding chain, and the real database because `scm.committed_v` and the
handshake columns both live in the migrated schema.
"""
from __future__ import annotations

import uuid

from app.models.automation import Automation
from app.models.email_template import EmailTemplate
from app.models.notification import Notification

from .test_order_inquiry_handshake import (
    MARKER,
    _open_po_line,
    _raise_one_row,
    _settle,
    api,
    world,
)

__all__ = ["api", "world"]  # re-exported fixtures; keeps linters from calling them unused

TRIGGER = "order_inquiry_changed_with_links"


def _template(world) -> EmailTemplate:
    template = EmailTemplate(
        id=str(uuid.uuid4()),
        code=f"tpl-oichg-{uuid.uuid4().hex[:6]}",
        name=f"{MARKER} OI changed with links",
        subject="Order inquiry {{ order_inquiry_row.item_code }} changed",
        body_html=(
            "<p>{{ order_inquiry_row.so_number }} / {{ order_inquiry_row.item_code }} "
            "changed - now {{ order_inquiry_row.qty }}, was "
            "{{ order_inquiry_row.previous_qty }}.</p>"
            "<p><a href='{{ order_inquiry_row.link }}'>Open</a></p>"
        ),
        body_text=None,
        is_active=True,
    )
    world.db.add(template)
    world.db.flush()
    automation = Automation(
        id=str(uuid.uuid4()),
        name=f"{MARKER} OI changed with links",
        enabled=True,
        trigger_type=TRIGGER,
        trigger_config={},
        action_type="send_email",
        email_template_id=template.id,
        recipient_config={
            "user_ids": [],
            "role_ids": [],
            "extra_emails": ["e2e@test.local"],
        },
        schedule_type="manual",
        timezone="Asia/Kuala_Lumpur",
    )
    world.db.add(automation)
    world.db.flush()
    return template


def _matches(world, row_id: str) -> list[Notification]:
    rows = (
        world.db.query(Notification)
        .filter(Notification.source_entity_type == "automation_run")
        .all()
    )
    return [n for n in rows if (n.data or {}).get("source_id") == str(row_id)]


def test_a_settle_with_a_link_dispatches_the_automation(api):
    """AC-1.7: a row THAT HAS LINKS is amended (settled in place) -> configured
    recipients are notified."""
    _client, world = api
    _template(world)
    _open_po_line(world, qty=50)
    fixture = _raise_one_row(api)
    row = fixture["row"]
    world.db.flush()
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    assert ProjectOrderInquiryService(world.db)._links_of(row.id), (
        "the raise-time cascade has to have linked it for this test to mean anything"
    )

    _settle(world, fixture, qty="25")

    world.db.commit()
    matches = _matches(world, row.id)
    assert matches, "a settle on a linked row must dispatch the automation"
    notif = matches[0]
    body_html = (notif.data or {}).get("body_html") or ""
    assert "25" in body_html and "10" in body_html, (
        "the Now and the Was both reach the template"
    )


def test_a_linkless_settle_dispatches_nothing(api):
    """AC-1.7's other half: a linkless amendment fires nothing."""
    _client, world = api
    _template(world)
    # No open PO line - the raise finds nothing to link.
    fixture = _raise_one_row(api)
    row = fixture["row"]
    world.db.flush()
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    assert ProjectOrderInquiryService(world.db)._links_of(row.id) == [], (
        "the row has to be linkless for this test to mean anything"
    )

    _settle(world, fixture, qty="25")

    world.db.commit()
    assert _matches(world, row.id) == []
