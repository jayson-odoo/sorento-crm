"""STANDARD-HISTORY wave 5 (lane STANDARD-HISTORY-W5): one price tag request's History tab read.

Contract: `documentation/plans/audit/standard-history-w5-acceptance-criteria.md`, AC-W5-1 to W5-4.

    GET /api/v1/dealer-kit/price-tag-requests/{request_id}/history
        (dealer_kit.price_tag_requests.view OR .view_own, staff session only)

answers `{events: [...]}` in the wave 1 shape, newest first, from
`app/services/price_tag_request_history_service.py` (`history_for_price_tag_request(db, id)`).

The audit rows are seeded directly (`AuditLog`, the shape the generic listener writes: changed
keys only) so each case is deterministic; ONE test drives a real staff status change through
`PriceTagRequestService.transition_status` to prove the generic listener path reaches the tab.
The audit listeners are registered for the whole module, so every ORM write a fixture makes
(the request's own INSERT, its lines, the draft flag) lands in `audit_logs` as it does in
production, and the "not an event" cases see those rows too.

All names, phone numbers and prices here are fake.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime

import pytest
from sqlalchemy import func

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.audit_context import AuditActor, stamp_actor
from app.models.access import RespondContact
from app.models.audit import AuditLog
from app.models.dealer_kit import PageVersion
from app.models.marketing import Promotion
from app.models.portal import PortalFormRevision
from app.models.price_tag import PriceTagRequest, PriceTagReviewComment
from app.models.user import User
from app.services.audit_service import register_audit_listeners
from app.services.price_tag_request_service import (
    PRINT_BY_OFFICE,
    PRINT_BY_SELF,
    PriceTagRequestService,
)

from tests import _portal_p4_support as s
from tests import _ptag_r9_seed
from tests._pg_fixture import blank_session, unique_code
from tests._portal_p4_pt_support import STAFF, scene, submitted, world  # noqa: F401
from tests.test_order_inquiry_worklist_raised_by import _client, _restore

register_audit_listeners()

SORENTO = _ptag_r9_seed.SORENTO
BASE = "/api/v1/dealer-kit/price-tag-requests"
VIEW = "dealer_kit.price_tag_requests.view"
VIEW_OWN = "dealer_kit.price_tag_requests.view_own"
READ = [VIEW]

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)

STAFF_NAME = "ZZT Marketing Mei"
DESIGNER_NAME = "ZZT Designer Dee"
CONTACT_NAME = "ZZT Sales Sam"

# One clock per event, so "newest first" is decided by the data and not by insert order.
T_SUBMITTED = datetime(2026, 11, 1, 1, 0, 0)
T_ASSIGNED = datetime(2026, 11, 1, 2, 0, 0)
T_DESIGNING = datetime(2026, 11, 1, 2, 30, 0)
T_PRINT_OFFICE = datetime(2026, 11, 2, 1, 0, 0)
T_LINE_PRICE = datetime(2026, 11, 3, 1, 0, 0)
T_DESIGN_V1 = datetime(2026, 11, 4, 1, 0, 0)
T_PROOF = datetime(2026, 11, 5, 1, 0, 0)
T_ROUND1 = datetime(2026, 11, 6, 1, 0, 0)
T_REVISED = datetime(2026, 11, 7, 1, 0, 0)
T_RESUBMITTED = datetime(2026, 11, 8, 1, 0, 0)
T_DESIGN_V2 = datetime(2026, 11, 9, 1, 0, 0)
T_ROUND2 = datetime(2026, 11, 9, 6, 0, 0)
T_UNASSIGNED = datetime(2026, 11, 10, 1, 0, 0)
T_PRINT_SELF = datetime(2026, 11, 11, 1, 0, 0)
T_APPROVED = datetime(2026, 11, 12, 1, 0, 0)

ALL_LABELS = [
    ("new", "New"),
    ("designing", "Designing"),
    ("proof_ready", "Design Ready"),
    ("changes_requested", "Changes Requested"),
    ("approved", "Approved"),
    ("ready_for_collection", "Ready for collection"),
    ("collected", "Collected"),
    ("rejected", "Rejected"),
    ("void", "Void"),
]


def _uid() -> str:
    return str(uuid.uuid4())


def _url(request_id: str) -> str:
    return f"{BASE}/{request_id}/history"


def _rendered(line: dict) -> str:
    """A change line as the tab prints it (`AuditTrail` `lineText`): "<item>: <change>"."""
    return f"{line['item_code']}: {line['change']}" if line.get("item_code") else line["change"]


# --------------------------------------------------------------------------- seeding


@dataclass
class World:
    request: PriceTagRequest
    contact: RespondContact
    staff: User
    designer: User
    product: object
    line: object


def _user(db, name: str) -> User:
    user = User(id=_uid(), email=f"{unique_code('zzt-ptag-hist')}@example.test".lower(), name=name, status="ACTIVE")
    db.add(user)
    db.flush()
    return user


def _contact(db, name: str = CONTACT_NAME) -> RespondContact:
    contact = RespondContact(id=_uid(), phone_number=f"+6000{uuid.uuid4().int % 10**9:09d}", name=name)
    db.add(contact)
    db.flush()
    return contact


def _promotion(db, description: str) -> Promotion:
    promotion = Promotion(id=_uid(), description=description, is_active=True, company_id=SORENTO)
    db.add(promotion)
    db.flush()
    return promotion


def _world(db) -> World:
    """One submitted request (a contact's, one product line, quantity 2) and two staff users."""
    staff = _user(db, STAFF_NAME)
    designer = _user(db, DESIGNER_NAME)
    contact = _contact(db)
    product = _ptag_r9_seed.seed_product(db)
    request = PriceTagRequestService.create_request(
        db,
        contact_id=contact.id,
        company_id=SORENTO,
        data={
            "debtor_name": "ZZT Dealer",
            "notes": "ZZT first note",
            "lines": [{"line_type": "product", "product_id": product.id, "quantity": 2}],
        },
    )
    request.portal_draft_at = None
    db.commit()
    db.refresh(request)
    return World(
        request=request, contact=contact, staff=staff, designer=designer, product=product,
        line=request.lines[0],
    )


def _audit(db, world: World, *, at: datetime, entity_type: str = "price_tag_requests",
           entity_id: str | None = None, action: str = "UPDATE", old=None, new=None,
           user_id: str | None = None, contact_id: str | None = None,
           actor_type: str | None = None) -> AuditLog:
    """An audit row in the listener's own shape: changed keys only, rooted at the request."""
    row = AuditLog(
        id=_uid(),
        entity_type=entity_type,
        entity_id=entity_id or world.request.id,
        action=action,
        user_id=user_id,
        contact_id=contact_id,
        actor_type=actor_type or ("contact" if contact_id and not user_id else "user"),
        changed_at=at,
        old_values=old,
        new_values=new,
        company_id=SORENTO,
        root_entity_type="price_tag_requests",
        root_entity_id=world.request.id,
        ip_address="203.0.113.7",
        user_agent="ZZT-Agent/1.0",
    )
    db.add(row)
    db.flush()
    return row


def _snapshot(world: World, *, notes: str, quantity: int) -> dict:
    """A price tag revision snapshot, in the shape `_serialize_price_tag_lines` writes."""
    return {
        "debtor_code": None,
        "debtor_name": "ZZT Dealer",
        "customers": None,
        "needed_by_date": None,
        "notes": notes,
        "price_mode": "list",
        "doc_number": world.request.doc_number,
        "status": "new",
        "products": [
            {
                "product_id": world.product.id,
                "product_set_id": None,
                "quantity": quantity,
                "remarks": None,
                "promotion_id": None,
                "manual_sell_price": None,
                "price_type": None,
            }
        ],
    }


def _revision(db, world: World, *, version_no: int, revision_no: int, kind: str, at: datetime,
              snapshot: dict, reason: str | None = None) -> PortalFormRevision:
    row = PortalFormRevision(
        id=_uid(),
        source_entity_type="price_tag_request",
        source_entity_id=world.request.id,
        version_no=version_no,
        revision_no=revision_no,
        kind=kind,
        reason=reason,
        snapshot_json=snapshot,
        attachments_json=[],
        submitted_at=at,
        submitted_by_contact_id=world.contact.id,
    )
    db.add(row)
    db.flush()
    return row


def _page(db, world: World):
    PriceTagRequestService.ensure_tag_sheet_page(db, world.request, world.staff.id)
    db.flush()
    return world.request.page_id


def _version(db, page_id: str, *, version: int, at: datetime, user_id: str, message: str | None):
    row = PageVersion(
        page_id=page_id, version=version, doc={"sheets": []}, commit_message=message,
        created_by=user_id, created_at=at,
    )
    db.add(row)
    db.flush()
    return row


def _comments(db, world: World, *, round_no: int, count: int, first_at: datetime):
    for n in range(count):
        db.add(
            PriceTagReviewComment(
                id=_uid(), request_id=world.request.id, round=round_no, body=f"ZZT fix {n}",
                author_contact_id=world.contact.id, company_id=SORENTO,
                created_at=first_at.replace(minute=n),
            )
        )
    db.flush()


def _full_story(db, world: World) -> None:
    """Every event kind once (twice for the ones with two spellings), each at its own time."""
    staff, designer = world.staff.id, world.designer.id
    _revision(db, world, version_no=1, revision_no=0, kind="original", at=T_SUBMITTED,
              snapshot=_snapshot(world, notes="ZZT first note", quantity=2))
    _audit(db, world, at=T_ASSIGNED, user_id=staff,
           old={"assigned_to_id": None}, new={"assigned_to_id": designer})
    _audit(db, world, at=T_DESIGNING, user_id=staff, old={"status": "new"}, new={"status": "designing"})
    _audit(db, world, at=T_PRINT_OFFICE, user_id=staff, old={"print_by": None}, new={"print_by": PRINT_BY_OFFICE})
    promo_a = _promotion(db, "ZZT Promo Alpha")
    promo_b = _promotion(db, "ZZT Promo Beta")
    _audit(db, world, at=T_LINE_PRICE, user_id=designer, entity_type="price_tag_request_lines",
           entity_id=world.line.id,
           old={"promotion_id": promo_a.id, "manual_sell_price": "1299.00"},
           new={"promotion_id": promo_b.id, "manual_sell_price": "1199.00"})
    page_id = _page(db, world)
    _version(db, page_id, version=1, at=T_DESIGN_V1, user_id=designer, message=None)
    _audit(db, world, at=T_PROOF, user_id=designer, old={"status": "designing"}, new={"status": "proof_ready"})
    _comments(db, world, round_no=1, count=3, first_at=T_ROUND1)
    _revision(db, world, version_no=2, revision_no=1, kind="revision", at=T_REVISED,
              reason="ZZT dealer changed the qty",
              snapshot=_snapshot(world, notes="ZZT second note", quantity=5))
    _revision(db, world, version_no=3, revision_no=1, kind="resubmission", at=T_RESUBMITTED,
              reason="ZZT office asked for a fix",
              snapshot=_snapshot(world, notes="ZZT second note", quantity=5))
    _version(db, page_id, version=2, at=T_DESIGN_V2, user_id=designer, message="ZZT moved the logo")
    _comments(db, world, round_no=2, count=2, first_at=T_ROUND2)
    _audit(db, world, at=T_UNASSIGNED, user_id=staff,
           old={"assigned_to_id": designer}, new={"assigned_to_id": None})
    _audit(db, world, at=T_PRINT_SELF, user_id=None, contact_id=world.contact.id,
           old={"print_by": PRINT_BY_OFFICE}, new={"print_by": PRINT_BY_SELF})
    _audit(db, world, at=T_APPROVED, user_id=None, contact_id=world.contact.id,
           old={"status": "proof_ready"}, new={"status": "approved"})
    db.commit()


def _get(db, user_id: str, request_id: str, permissions=READ):
    client, originals = _client(db, user_id, permissions)
    try:
        return client.get(_url(request_id))
    finally:
        _restore(originals)


def _events(db, world: World) -> list[dict]:
    response = _get(db, world.staff.id, world.request.id)
    assert response.status_code == 200, response.text
    return response.json()["events"]


def _not_a_missing_route(response) -> None:
    s.not_a_missing_route(response)


# --------------------------------------------------------------------------- AC-W5-1, AC-W5-3


def test_every_event_kind_reads_its_title_and_actor_newest_first():
    """AC-W5-1, AC-W5-3: one of each kind, in the wave 1 shape, newest first."""
    with blank_session() as db:
        world = _world(db)
        _full_story(db, world)

        events = _events(db, world)

        for event in events:
            assert set(event) == {"id", "kind", "at", "actor", "title", "lines"}
            for line in event["lines"]:
                assert set(line) == {"row_id", "so_line_no", "item_code", "qty", "change"}
        assert len({e["id"] for e in events}) == len(events), "event ids are React keys"

        got = [(e["kind"], e["title"], e["actor"]) for e in events]
        assert got == [
            ("status_changed", "Status: Design Ready → Approved", CONTACT_NAME),
            ("print_by", "Printing: Salesperson prints", CONTACT_NAME),
            ("assigned", "Unassigned", STAFF_NAME),
            ("changes_requested", "Changes requested: 2 comments", CONTACT_NAME),
            ("design_saved", "Design saved, version 2: ZZT moved the logo", DESIGNER_NAME),
            ("resubmitted", "Resubmitted", CONTACT_NAME),
            ("revised", "Revised, revision 1: ZZT dealer changed the qty", CONTACT_NAME),
            ("changes_requested", "Changes requested: 3 comments", CONTACT_NAME),
            ("status_changed", "Status: Designing → Design Ready", DESIGNER_NAME),
            ("design_saved", "Design saved, version 1", DESIGNER_NAME),
            ("line_price", "Line price changed", DESIGNER_NAME),
            ("print_by", "Printing: Office prints", STAFF_NAME),
            ("status_changed", "Status: New → Designing", STAFF_NAME),
            ("assigned", f"Assigned to {DESIGNER_NAME}", STAFF_NAME),
            ("submitted", "Submitted", CONTACT_NAME),
        ]
        ats = [e["at"] for e in events]
        assert ats == sorted(ats, reverse=True)

        # A review round is dated by its earliest comment.
        rounds = [e for e in events if e["kind"] == "changes_requested"]
        assert rounds[1]["at"].startswith("2026-11-06T01:00")
        assert rounds[0]["at"].startswith("2026-11-09T06:00")


def test_the_service_answers_the_same_events_as_the_route():
    """AC-W5-1: `history_for_price_tag_request(db, request_id)` is the one read."""
    from app.services.price_tag_request_history_service import history_for_price_tag_request

    with blank_session() as db:
        world = _world(db)
        _full_story(db, world)
        events = history_for_price_tag_request(db, world.request.id)
        assert [e["kind"] for e in events][:3] == ["status_changed", "print_by", "assigned"]
        assert [e["title"] for e in events][-1] == "Submitted"
        assert events == _events(db, world)


@pytest.mark.parametrize("old,new", list(zip(ALL_LABELS, ALL_LABELS[1:] + ALL_LABELS[:1])))
def test_status_titles_use_the_screens_labels(old, new):
    """AC-W5-3: "Status: <old> → <new>" with `lib/price-tag-status.ts`'s labels, never codes."""
    with blank_session() as db:
        world = _world(db)
        _audit(db, world, at=T_DESIGNING, user_id=world.staff.id,
               old={"status": old[0]}, new={"status": new[0]})
        db.commit()
        status = [e for e in _events(db, world) if e["kind"] == "status_changed"]
        assert [e["title"] for e in status] == [f"Status: {old[1]} → {new[1]}"]


def test_a_claim_row_holding_status_and_assignee_is_two_events():
    """AC-W5-3: a claim writes ONE audit row with both keys; the tab shows both facts."""
    with blank_session() as db:
        world = _world(db)
        _audit(db, world, at=T_ASSIGNED, user_id=world.staff.id,
               old={"status": "new", "assigned_to_id": None},
               new={"status": "designing", "assigned_to_id": world.staff.id})
        db.commit()
        events = _events(db, world)
        titles = sorted(e["title"] for e in events)
        assert titles == sorted([f"Assigned to {STAFF_NAME}", "Status: New → Designing"])
        assert len({e["id"] for e in events}) == 2
        assert {e["actor"] for e in events} == {STAFF_NAME}


def test_line_price_lists_each_changed_field_with_the_promotion_by_name():
    """AC-W5-3: "<item>: promotion <old> → <new>", "<item>: price <old> → <new>"."""
    with blank_session() as db:
        world = _world(db)
        _full_story(db, world)
        event = next(e for e in _events(db, world) if e["kind"] == "line_price")
        code = world.product.product_code
        assert sorted(_rendered(line) for line in event["lines"]) == sorted([
            f"{code}: promotion ZZT Promo Alpha → ZZT Promo Beta",
            f"{code}: price 1299.00 → 1199.00",
        ])
        # `AuditTrail` keys a change line by `row_id`: two lines of one event must not share one.
        assert len({line["row_id"] for line in event["lines"]}) == len(event["lines"])


def test_a_line_price_type_change_is_a_line_price_event():
    """AC-W5-3: `price_type` is one of the three line columns that make a line_price event."""
    with blank_session() as db:
        world = _world(db)
        _audit(db, world, at=T_LINE_PRICE, user_id=world.staff.id,
               entity_type="price_tag_request_lines", entity_id=world.line.id,
               old={"price_type": "list"}, new={"price_type": "promotion"})
        db.commit()
        events = [e for e in _events(db, world) if e["kind"] == "line_price"]
        assert [e["title"] for e in events] == ["Line price changed"]
        assert len(events[0]["lines"]) == 1


# --------------------------------------------------------------------------- revisions


def test_revision_events_carry_the_versions_changes_and_the_original_none():
    """AC-W5-3: the lines are `PortalRevisionService.list_revisions`' `changes`, one per change,
    "<label>: <from> → <to>"; the original has no lines."""
    with blank_session() as db:
        world = _world(db)
        _full_story(db, world)
        events = _events(db, world)

        submitted_event = next(e for e in events if e["kind"] == "submitted")
        assert submitted_event["lines"] == []
        assert submitted_event["at"].startswith("2026-11-01T01:00")

        revised = next(e for e in events if e["kind"] == "revised")
        assert sorted(_rendered(line) for line in revised["lines"]) == sorted([
            "Notes: ZZT first note → ZZT second note",
            "Product line 1 quantity: 2 → 5",
        ])

        resubmitted = next(e for e in events if e["kind"] == "resubmitted")
        assert resubmitted["lines"] == []  # same snapshot as the revision before it


def test_revision_lines_match_list_revisions_exactly():
    """AC-W5-3: reused, not copied - the tab's lines are `list_revisions`' changes, in order."""
    from app.services.portal_revision_service import PortalRevisionService

    with blank_session() as db:
        world = _world(db)
        _full_story(db, world)
        revisions = PortalRevisionService(db).list_revisions("price_tag_request", world.request.id)
        changes = revisions[1]["changes"]
        expected = [f"{c['label']}: {c['from']} → {c['to']}" for c in changes]
        revised = next(e for e in _events(db, world) if e["kind"] == "revised")
        assert [_rendered(line) for line in revised["lines"]] == expected


def test_an_added_and_a_removed_product_line_read_with_one_side_only():
    """AC-W5-3: an added line reads "<label>: <to>", a removed one "<label>: <from>"."""
    with blank_session() as db:
        world = _world(db)
        one = _snapshot(world, notes="ZZT first note", quantity=2)
        two = _snapshot(world, notes="ZZT first note", quantity=2)
        two["products"] = two["products"] + [dict(two["products"][0], quantity=3)]
        _revision(db, world, version_no=1, revision_no=0, kind="original", at=T_SUBMITTED, snapshot=one)
        _revision(db, world, version_no=2, revision_no=1, kind="revision", at=T_REVISED, snapshot=two)
        _revision(db, world, version_no=3, revision_no=2, kind="revision", at=T_APPROVED, snapshot=one,
                  reason="ZZT dropped the extra line")
        db.commit()
        events = _events(db, world)
        added, removed = (
            next(e for e in events if e["title"] == "Revised, revision 1"),
            next(e for e in events if e["title"] == "Revised, revision 2: ZZT dropped the extra line"),
        )
        assert [_rendered(line) for line in added["lines"]] == [
            "Product line 2 added: (no item code) x3"
        ]
        assert [_rendered(line) for line in removed["lines"]] == [
            "Product line 2 removed: (no item code) x3"
        ]
        for event in (added, removed):
            assert "None" not in event["lines"][0]["change"]


# --------------------------------------------------------------------------- non-events


def test_counters_timestamps_and_line_or_tag_inserts_and_deletes_are_not_events():
    """AC-W5-3: any other column change, and line / tag / part INSERT or DELETE rows, are NOT
    events. The fixture's own ORM writes (the request's INSERT, its line, the draft flag) are in
    `audit_logs` too through the registered listener."""
    with blank_session() as db:
        world = _world(db)
        staff = world.staff.id
        assert db.query(AuditLog).filter(AuditLog.root_entity_id == world.request.id).count() > 0, (
            "the listener should have recorded the fixture's own writes"
        )
        for old, new in (
            ({"updated_at": "2026-11-01T00:00:00"}, {"updated_at": "2026-11-02T00:00:00"}),
            ({"data_changed_tag_count": 0}, {"data_changed_tag_count": 3}),
            ({"review_round": 1}, {"review_round": 2}),
            ({"data_checked_at": None}, {"data_checked_at": "2026-11-02T00:00:00"}),
            ({"portal_draft_at": "2026-11-01T00:00:00"}, {"portal_draft_at": None}),
            ({"notes": "ZZT a"}, {"notes": "ZZT b"}),
        ):
            _audit(db, world, at=T_PROOF, user_id=staff, old=old, new=new)
        line_id = world.line.id
        for entity_type, action, entity_id, old, new in (
            ("price_tag_request_lines", "CREATE", _uid(), None, {"quantity": 1, "promotion_id": None}),
            ("price_tag_request_lines", "DELETE", line_id, {"quantity": 2, "manual_sell_price": "10.00"}, None),
            ("price_tag_request_lines", "UPDATE", line_id, {"sort_order": 0}, {"sort_order": 1}),
            ("price_tag_request_lines", "UPDATE", line_id, {"quantity": 2}, {"quantity": 4}),
            ("price_tag_request_tags", "CREATE", _uid(), None, {"quantity": 1}),
            ("price_tag_request_tags", "DELETE", _uid(), {"quantity": 1}, None),
            ("price_tag_request_tags", "UPDATE", _uid(), {"print_excluded": False}, {"print_excluded": True}),
            ("price_tag_request_line_parts", "CREATE", _uid(), None, {"role": "ZZT basin"}),
            ("price_tag_request_line_parts", "DELETE", _uid(), {"role": "ZZT basin"}, None),
        ):
            _audit(db, world, at=T_PROOF, user_id=staff, entity_type=entity_type,
                   entity_id=entity_id, action=action, old=old, new=new)
        db.commit()

        assert _events(db, world) == []


def test_another_requests_rows_never_reach_this_tab():
    """AC-W5-3: only rows of THIS request (by root, comments and versions of its own page)."""
    with blank_session() as db:
        world = _world(db)
        other = _world(db)
        _full_story(db, other)
        assert _events(db, world) == []


# --------------------------------------------------------------------------- AC-W5-4


def test_a_portal_write_reads_the_contacts_name():
    """AC-W5-4: `actor_type = contact`, `contact_id` set, `user_id` null: the contact's name."""
    with blank_session() as db:
        world = _world(db)
        _audit(db, world, at=T_PRINT_SELF, user_id=None, contact_id=world.contact.id,
               actor_type="contact", old={"print_by": PRINT_BY_OFFICE}, new={"print_by": PRINT_BY_SELF})
        db.commit()
        events = _events(db, world)
        assert [(e["kind"], e["actor"]) for e in events] == [("print_by", CONTACT_NAME)]


def test_audit_actor_resolves_a_contact_actor_to_the_contacts_name():
    """AC-W5-4: the shared `history_common.audit_actor` gains the contact case; a user row reads
    as before (the OI / SO tests stay green unchanged)."""
    from app.services.history_common import audit_actor

    with blank_session() as db:
        world = _world(db)
        by_contact = _audit(db, world, at=T_PRINT_SELF, user_id=None, contact_id=world.contact.id,
                            actor_type="contact", old={"print_by": None}, new={"print_by": "self"})
        by_user = _audit(db, world, at=T_PRINT_OFFICE, user_id=world.staff.id,
                         old={"print_by": None}, new={"print_by": "office"})
        names = audit_actor(db, [by_contact, by_user])
        assert names == {by_contact.id: CONTACT_NAME, by_user.id: STAFF_NAME}


def test_no_uuid_ip_user_agent_or_raw_audit_json_in_the_response():
    """AC-W5-4: no IP, user agent, raw audit JSON, UUIDs or entity ids in any title or line."""
    with blank_session() as db:
        world = _world(db)
        _full_story(db, world)
        response = _get(db, world.staff.id, world.request.id)
        assert response.status_code == 200, response.text
        events = response.json()["events"]
        assert events
        for event in events:
            assert not UUID_RE.search(event["title"]), event["title"]
            assert not UUID_RE.search(event["actor"] or ""), event["actor"]
            for line in event["lines"]:
                assert not UUID_RE.search(line["change"]), line["change"]
                assert not UUID_RE.search(line["item_code"] or ""), line["item_code"]
        text = response.text
        for leaked in ("ip_address", "user_agent", "203.0.113.7", "ZZT-Agent", "old_values",
                       "new_values", "snapshot_json", "promotion_id", "manual_sell_price"):
            assert leaked not in text, leaked


# --------------------------------------------------------------------------- the generic listener


def test_a_real_staff_status_change_reaches_the_tab_through_the_generic_listener(monkeypatch):
    """AC-W5-3: nothing seeded by hand - a staff transition writes its audit row through the
    registered listener, and the tab reads it as a status_changed event."""
    from app.services import price_tag_notify

    monkeypatch.setattr(price_tag_notify, "notify_salesperson", lambda *a, **k: None)
    monkeypatch.setattr(price_tag_notify, "ring_assignee", lambda *a, **k: None)
    with blank_session() as db:
        world = _world(db)
        stamp_actor(
            AuditActor(actor_type="user", user_id=world.staff.id, real_user_id=world.staff.id), db=db
        )
        PriceTagRequestService.transition_status(db, world.request.id, "void", user_id=world.staff.id)
        db.commit()
        written = (
            db.query(AuditLog)
            .filter(AuditLog.entity_type == "price_tag_requests")
            .filter(AuditLog.entity_id == world.request.id)
            .filter(AuditLog.action == "UPDATE")
            .all()
        )
        assert any((row.new_values or {}).get("status") == "void" for row in written), (
            "the listener did not record the transition"
        )

        events = _events(db, world)
        status = [e for e in events if e["kind"] == "status_changed"]
        assert [(e["title"], e["actor"]) for e in status] == [("Status: New → Void", STAFF_NAME)]


# --------------------------------------------------------------------------- AC-W5-2


def test_without_view_or_view_own_the_read_is_refused():
    """AC-W5-2: neither slug held: 403."""
    with blank_session() as db:
        world = _world(db)
        response = _get(db, world.staff.id, world.request.id, permissions=[])
        assert response.status_code == 403, response.text
        _not_a_missing_route(response)


def test_an_unknown_or_malformed_id_is_404():
    """AC-W5-2: the same as `GET /{request_id}`."""
    with blank_session() as db:
        world = _world(db)
        for request_id in (_uid(), "not-a-uuid"):
            response = _get(db, world.staff.id, request_id)
            assert response.status_code == 404, (request_id, response.text)
            _not_a_missing_route(response)


def test_another_companys_request_is_404():
    """AC-W5-2: the session's company scope hides another company's request."""
    from app.models.base import set_company_scope

    with blank_session() as db:
        world = _world(db)
        _full_story(db, world)
        set_company_scope(db, frozenset({_uid()}))
        response = _get(db, world.staff.id, world.request.id)
        assert response.status_code == 404, response.text
        _not_a_missing_route(response)
        assert "ZZT" not in response.text


def test_an_api_key_principal_is_refused():
    """AC-W5-2: staff session only (`require_any_permission`, never `_with_api_key`)."""
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user_or_api_key

    with blank_session() as db:
        world = _world(db)
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user_or_api_key] = lambda: {
            "id": world.staff.id, "integration_id": _uid(), "role": "user",
        }
        try:
            response = TestClient(app).get(
                _url(world.request.id), headers={"X-API-Key": "zzt-not-a-real-key"}
            )
        finally:
            app.dependency_overrides.clear()
        assert response.status_code in (401, 403), response.text
        _not_a_missing_route(response)


def test_the_read_writes_nothing():
    """AC-W5-2: read-only - no audit row, no `updated_at` / `data_changed_tag_count` /
    `data_checked_at` refresh, no row anywhere."""
    with blank_session() as db:
        world = _world(db)
        _full_story(db, world)
        db.expire_all()
        before = db.query(PriceTagRequest).filter(PriceTagRequest.id == world.request.id).one()
        stamp = (before.updated_at, before.data_changed_tag_count, before.data_checked_at)
        audits = db.query(func.count(AuditLog.id)).scalar()
        revisions = db.query(func.count(PortalFormRevision.id)).scalar()
        versions = db.query(func.count(PageVersion.id)).scalar()

        assert _get(db, world.staff.id, world.request.id).status_code == 200

        db.expire_all()
        after = db.query(PriceTagRequest).filter(PriceTagRequest.id == world.request.id).one()
        assert (after.updated_at, after.data_changed_tag_count, after.data_checked_at) == stamp
        assert db.query(func.count(AuditLog.id)).scalar() == audits
        assert db.query(func.count(PortalFormRevision.id)).scalar() == revisions
        assert db.query(func.count(PageVersion.id)).scalar() == versions


def test_view_own_reads_their_own_request_and_404s_someone_elses(world):  # noqa: F811
    """AC-W5-2: real Bearer sessions. A `view_own` salesperson reads the History of a request
    their contact raised; another salesperson's is 404, as `GET /{request_id}` answers; staff
    holding `.view` read both."""
    w = world
    own = submitted(w.rep.portal, w)
    foreign = submitted(w.other.portal, w)

    mine = w.staff(w.rep.actor, "GET", f"{STAFF}/{own}/history")
    assert mine.status_code == 200, mine.text
    assert isinstance(mine.json()["events"], list)

    theirs = w.staff(w.rep.actor, "GET", f"{STAFF}/{foreign}/history")
    assert theirs.status_code == 404, theirs.text
    s.not_a_missing_route(theirs)
    # The detail route answers the same for the same row (the contract the read copies).
    assert w.staff(w.rep.actor, "GET", f"{STAFF}/{foreign}").status_code == 404

    staff = s.make_user(w.sc.db, perms=[VIEW], name="ZZT Staff Viewer")
    for rid in (own, foreign):
        response = w.staff(staff, "GET", f"{STAFF}/{rid}/history")
        assert response.status_code == 200, response.text

    nobody = s.make_user(w.sc.db, perms=[], name="ZZT No Access")
    refused = w.staff(nobody, "GET", f"{STAFF}/{own}/history")
    assert refused.status_code == 403, refused.text
    s.not_a_missing_route(refused)
