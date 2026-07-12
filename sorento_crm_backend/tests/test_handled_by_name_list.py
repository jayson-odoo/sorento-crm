"""List-view "Handled By" column resolution.

The form-handling-lock holder (`handled_by_id`) lives on the active form-SLA
tracker, NOT on the form row. The list services batch-load the latest unresolved
tracker per row and resolve its `handled_by_id` -> user display name into a
`handled_by_name` field (separate from `assigned_to_name`).

Covers:
  - Complaint list: `handled_by_name` = the holder's display name when the
    tracker has `handled_by_id`, and None when unheld.
  - Purchase-request list (analogous): `_attach_sla_assignees` sets
    `handled_by_name` from the tracker.

Run: venv/bin/pytest tests/test_handled_by_name_list.py -q
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.models.complaints import Complaint
from app.models.sla import ConversationSLATracking
from app.models.user import User
from app.services.complaints_service import ComplaintService
from app.services.procurement_service import PurchaseRequestService


def _complaint_service_over(complaints, tracker_map, name_map):
    """Build a ComplaintService whose list query yields ``complaints`` and whose
    batched enrichment helpers return the given tracker / display-name maps.
    """
    q = MagicMock()
    q.filter.return_value = q
    q.order_by.return_value = q
    q.options.return_value = q
    q.count.return_value = len(complaints)
    q.offset.return_value = q
    q.limit.return_value = q
    q.all.return_value = complaints

    db = MagicMock()
    db.query.return_value = q

    svc = ComplaintService(db)
    # Neutralize the other per-page batches so the test isolates handled_by.
    svc._batch_complaint_view_urls = lambda ids: {}
    svc._batch_latest_unresolved_sla_trackers = lambda ids: tracker_map
    svc._batch_user_display_names = lambda ids: name_map
    svc.entity_attachment_service.list_links_for_entities = lambda *a, **k: {}
    return svc


def test_complaint_list_resolves_handled_by_name():
    complaint = Complaint(id="c1")
    tracker = SimpleNamespace(
        source_entity_id="c1",
        assigned_to_id=None,
        assigned_to=None,
        handled_by_id="u-handler",
    )
    svc = _complaint_service_over(
        [complaint],
        tracker_map={"c1": tracker},
        name_map={"u-handler": "Alice Handler"},
    )
    result = svc.list_complaints(viewer_user_id=None)
    row = result["data"][0]
    assert row["handled_by_name"] == "Alice Handler"


def test_complaint_list_handled_by_name_none_when_unheld():
    complaint = Complaint(id="c1")
    tracker = SimpleNamespace(
        source_entity_id="c1",
        assigned_to_id="u-assignee",
        assigned_to=None,
        handled_by_id=None,  # nobody has claimed the handling lock
    )
    svc = _complaint_service_over(
        [complaint],
        tracker_map={"c1": tracker},
        name_map={"u-assignee": "Bob Assignee"},
    )
    result = svc.list_complaints(viewer_user_id=None)
    row = result["data"][0]
    assert row["handled_by_name"] is None
    # The assignee column is unaffected by the handling lock.
    assert row["assigned_to_name"] == "Bob Assignee"


def _pr_query_returning(rows_by_model):
    db = MagicMock()

    def _query(model):
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value = q
        q.all.return_value = rows_by_model.get(model, [])
        q.first.return_value = (rows_by_model.get(model) or [None])[0]
        return q

    db.query.side_effect = _query
    return db


def test_pr_attach_resolves_handled_by_name():
    tracker = SimpleNamespace(
        source_entity_id="pr1",
        assigned_to_id="u-assignee",
        handled_by_id="u-handler",
        initiated_at=2,
    )
    assignee = SimpleNamespace(id="u-assignee", name="Bob Assignee", email="b@x.com")
    handler = SimpleNamespace(id="u-handler", name="Alice Handler", email="a@x.com")
    db = _pr_query_returning(
        {ConversationSLATracking: [tracker], User: [assignee, handler]}
    )
    svc = PurchaseRequestService(db)
    item = SimpleNamespace(id="pr1")
    svc._attach_sla_assignees([item])
    assert item.handled_by_name == "Alice Handler"
    assert item.assigned_to_name == "Bob Assignee"


def test_pr_attach_handled_by_name_none_when_unheld():
    tracker = SimpleNamespace(
        source_entity_id="pr1",
        assigned_to_id="u-assignee",
        handled_by_id=None,
        initiated_at=2,
    )
    assignee = SimpleNamespace(id="u-assignee", name="Bob Assignee", email="b@x.com")
    db = _pr_query_returning(
        {ConversationSLATracking: [tracker], User: [assignee]}
    )
    svc = PurchaseRequestService(db)
    item = SimpleNamespace(id="pr1")
    svc._attach_sla_assignees([item])
    assert item.handled_by_name is None
