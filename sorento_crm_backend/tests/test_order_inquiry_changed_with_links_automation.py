"""AC-1.7 (`PLAN-scm-reorder-oi-feedback-1sep.md` S1, G6): the `order_inquiry_changed_with_links`
automation trigger.

Fires when a row THAT HAS LINKS is amended (a settle-in-place changing qty/date, a settle
that zeroes the row out and gives its link back, or a dropped line's cascade-linked row
being retired); fires nothing for a linkless amendment. Queued by
`ProjectOrderInquiryService._dispatch_changed_with_links` and drained by
`_fire_pending_changed_with_links`, a module-level `after_commit` listener (S5, review of
PR #471): `AutomationService.dispatch_event` commits internally, so it cannot run
synchronously inside the still-open confirm transaction without either releasing every
savepoint above it or (worse) prematurely committing a multi-line confirm mid-loop - it has
to run on a FRESH session, after this one's write is durable.

That fresh-session hand-off is exactly why these tests verify the DISPATCH CALL
(monkeypatched `AutomationService.dispatch_event`) rather than a real `Notification` row:
the fresh session opens a genuinely separate connection, and this suite's own test
isolation (`tests/test_order_inquiry_handshake.py`'s rolled-back outer transaction) is
invisible to any connection but its own - a second connection can never see a `commit()`
that is really a savepoint release inside a transaction nothing ever really commits. The
automation pipeline's OWN rendering/recipient-resolution behaviour is
`test_automation_service.py`'s job, not this file's.

Reuses `tests/test_order_inquiry_handshake.py`'s harness wholesale (`world` / `api`,
`_raise_one_row`, `_raise_two_rows`, `_open_po_line`, `_settle`), for the same reason the
sibling draft-links suite does: one seeding chain, and the real database because
`scm.committed_v` and the handshake columns both live in the migrated schema.
"""
from __future__ import annotations

from app.services.project_order_inquiry_service import ProjectOrderInquiryService

from .test_order_inquiry_handshake import (
    _open_po_line,
    _raise_one_row,
    _raise_two_rows,
    _settle,
    api,
    world,
)

__all__ = ["api", "world"]  # re-exported fixtures; keeps linters from calling them unused

TRIGGER = "order_inquiry_changed_with_links"


def _captured_dispatches(monkeypatch) -> list[dict]:
    """Intercepts `AutomationService.dispatch_event` - the seam
    `_fire_pending_changed_with_links` calls on its own fresh session - so a test can
    assert WHAT this service handed off without needing a second connection to see it."""
    calls: list[dict] = []

    def _fake_dispatch(self, trigger_type, *, context, source_kind, source_id):
        calls.append(
            {
                "trigger_type": trigger_type,
                "context": context,
                "source_kind": source_kind,
                "source_id": source_id,
            }
        )
        return {"trigger_type": trigger_type, "fired": 0, "results": []}

    monkeypatch.setattr(
        "app.services.automation_service.AutomationService.dispatch_event",
        _fake_dispatch,
    )
    return calls


def _register(world) -> None:
    # Idempotent (S5): the dispatch is queued on `Session.info` mid-transaction and only
    # fires from this listener once the session commits - registered once per process
    # normally (`app.main`'s startup event), called directly here the same way
    # `test_product_spec_write_backstop.py` calls its own sibling listener, since
    # `TestClient(app)` without `with` never runs FastAPI's lifespan in this suite.
    from app.services.project_order_inquiry_service import (
        register_order_inquiry_post_commit_dispatch,
    )

    register_order_inquiry_post_commit_dispatch()


def _for_row(calls: list[dict], row_id: str) -> list[dict]:
    return [call for call in calls if call["source_id"] == str(row_id)]


def test_a_settle_with_a_link_dispatches_the_automation(api, monkeypatch):
    """AC-1.7: a row THAT HAS LINKS is amended (settled in place) -> the trigger fires
    with both the Now and the Was."""
    _client, world = api
    _register(world)
    calls = _captured_dispatches(monkeypatch)
    _open_po_line(world, qty=50)
    fixture = _raise_one_row(api)
    row = fixture["row"]
    world.db.flush()
    assert ProjectOrderInquiryService(world.db)._links_of(row.id), (
        "the raise-time cascade has to have linked it for this test to mean anything"
    )

    _settle(world, fixture, qty="25")
    world.db.commit()

    matches = _for_row(calls, row.id)
    assert matches, "a settle on a linked row must dispatch the automation"
    ctx = matches[0]["context"]["order_inquiry_row"]
    assert ctx["qty"] == "25" and ctx["previous_qty"] == "10.0000"


def test_a_linkless_settle_dispatches_nothing(api, monkeypatch):
    """AC-1.7's other half: a linkless amendment fires nothing."""
    _client, world = api
    _register(world)
    calls = _captured_dispatches(monkeypatch)
    # No open PO line - the raise finds nothing to link.
    fixture = _raise_one_row(api)
    row = fixture["row"]
    world.db.flush()
    assert ProjectOrderInquiryService(world.db)._links_of(row.id) == [], (
        "the row has to be linkless for this test to mean anything"
    )

    _settle(world, fixture, qty="25")
    world.db.commit()

    assert _for_row(calls, row.id) == []


def test_a_zeroed_settle_that_gives_back_a_link_dispatches_too(api, monkeypatch):
    """S4 (review of PR #471). The book reduced the line to nothing: `_settle_row_in_place`
    cancels the row and gives its link back - a row that carried real supply and now
    carries none is exactly the case G6 exists for, not only a quantity/date edit."""
    _client, world = api
    _register(world)
    calls = _captured_dispatches(monkeypatch)
    _open_po_line(world, qty=50)
    fixture = _raise_one_row(api, qty="10")
    row = fixture["row"]
    world.db.flush()
    assert ProjectOrderInquiryService(world.db)._links_of(row.id), (
        "the raise-time cascade has to have linked it for this test to mean anything"
    )

    _settle(world, fixture, qty="0")
    world.db.commit()

    world.db.refresh(row)
    assert row.state == "cancelled", "the book left nothing to buy"
    assert ProjectOrderInquiryService(world.db)._links_of(row.id) == [], (
        "the link went back to the pool"
    )
    assert _for_row(calls, row.id), "a row that carried supply and lost it must still be reported"


def test_a_dropped_lines_cascade_linked_row_dispatches_when_retired(api, monkeypatch):
    """S4's other half. `_retire_uncovered_rows` cancels a cascade-linked row when its
    LINE leaves the revision entirely (the line was covered, then CS un-decided it) -
    the document goes back to the pool exactly as a zeroed settle-in-place does, and
    purchasing has to hear about it the same way."""
    from app.services.project_supply_service import ProjectSupplyService

    _client, world = api
    _register(world)
    calls = _captured_dispatches(monkeypatch)
    _open_po_line(world, qty=50)
    fixture = _raise_two_rows(api)
    dropped = fixture["first"]["row"]
    assert ProjectOrderInquiryService(world.db)._links_of(dropped.id), (
        "the draft has to exist for this test to mean anything"
    )

    ProjectSupplyService(world.db).uncover_lines(
        fixture["order"],
        [str(fixture["first"]["line"].id)],
        actor_user_id=world.cs_user,
        reason="CS took the line back.",
    )
    world.db.commit()

    world.db.refresh(dropped)
    assert dropped.state == "cancelled"
    assert _for_row(calls, dropped.id), (
        "a dropped line's cascade-linked row must still be reported"
    )
