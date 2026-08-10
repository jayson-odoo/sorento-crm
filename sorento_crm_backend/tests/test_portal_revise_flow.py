"""The revise transaction: counters, snapshot, frozen fields, restart, replay.

Covers UAC C0-C5, AB1/AB2, D1, F1/F3, FB2/FB3, G1/G2/G4 for ALL THREE enabled types,
including the line items PR and SF carry and stock inquiry does not.

Run: pytest tests/test_portal_revise_flow.py -v
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.models.portal import PortalFormRevision
from app.models.procurement import PurchaseRequestHeader, PurchaseRequestLine, StockInquiry
from app.services.portal_revision_service import PortalRevisionService
from tests._pg_fixture import blank_session
from tests._revision_harness import (
    REVISABLE_TYPES,
    seed_config,
    seed_contact,
    seed_entity,
    seed_policy,
    seed_system_settings,
    seed_token,
    seed_tracker,
)


@pytest.fixture(autouse=True)
def no_queue():
    """Never enqueue a real RQ job from a test: a worker in another worktree would
    pick it up. Every enqueue in this path is already best-effort."""
    with patch("app.services.queue_service.enqueue_job", return_value=None):
        yield


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _revise_payload(kind: str) -> dict:
    if kind == "stock_inquiry":
        return {"item_description": "Revised description", "quantity": "9"}
    return {"project_title": "Revised project", "purpose": "Revised purpose"}


def _changed_field(kind: str) -> tuple[str, str]:
    if kind == "stock_inquiry":
        return "item_description", "Revised description"
    return "project_title", "Revised project"


def _setup(db, kind, **entity_kwargs):
    seed_system_settings(db, cap=3)
    seed_config(db, kind)
    contact = seed_contact(db)
    row = seed_entity(db, kind, contact, **entity_kwargs)
    return contact, seed_token(contact), row


def _revise(db, token, kind, row, *, reason="Wrong quantity, corrected it", expected=None, payload=None):
    return PortalRevisionService(db).revise(
        token,
        kind,
        str(row.id),
        _revise_payload(kind) if payload is None else payload,
        reason,
        row.revision_no if expected is None else expected,
    )


def _reload(db, kind, entity_id):
    db.expire_all()
    model = StockInquiry if kind == "stock_inquiry" else PurchaseRequestHeader
    return db.query(model).filter(model.id == entity_id).one()


def _revisions(db, kind, entity_id):
    return (
        db.query(PortalFormRevision)
        .filter(
            PortalFormRevision.source_entity_type == kind,
            PortalFormRevision.source_entity_id == entity_id,
        )
        .order_by(PortalFormRevision.version_no.asc())
        .all()
    )


# ------------------------------------------------------------------ happy path


@pytest.mark.parametrize("kind", REVISABLE_TYPES)
def test_revise_increments_the_counter_and_stamps_the_time(db, kind):
    _contact, token, row = _setup(db, kind)
    _revise(db, token, kind, row)

    fresh = _reload(db, kind, str(row.id))
    assert fresh.revision_no == 1
    assert fresh.last_revised_at is not None


@pytest.mark.parametrize("kind", REVISABLE_TYPES)
def test_revise_applies_the_payload_through_the_portal_whitelist(db, kind):
    _contact, token, row = _setup(db, kind)
    _revise(db, token, kind, row)

    field, value = _changed_field(kind)
    assert getattr(_reload(db, kind, str(row.id)), field) == value


@pytest.mark.parametrize("kind", REVISABLE_TYPES)
def test_revise_writes_a_history_row_carrying_the_post_edit_snapshot(db, kind):
    _contact, token, row = _setup(db, kind)
    _revise(db, token, kind, row)

    rows = _revisions(db, kind, str(row.id))
    assert [r.kind for r in rows] == ["original", "revision"]
    assert [r.version_no for r in rows] == [0, 1]
    assert [r.revision_no for r in rows] == [0, 1]
    field, value = _changed_field(kind)
    assert rows[1].snapshot_json[field] == value
    assert rows[1].reason == "Wrong quantity, corrected it"


@pytest.mark.parametrize("kind", REVISABLE_TYPES)
def test_revise_restarts_the_entity_at_the_first_stage_status(db, kind):
    """UAC F3: stock inquiry returns to project sales, PR/SF to submitted."""
    status = "responded" if kind == "stock_inquiry" else "approved"
    _contact, token, row = _setup(db, kind, status=status)
    _revise(db, token, kind, row)

    expected = "pending_project_sales" if kind == "stock_inquiry" else "submitted"
    assert _reload(db, kind, str(row.id)).status == expected


@pytest.mark.parametrize("kind", REVISABLE_TYPES)
def test_revise_returns_the_policy_after_the_revision(db, kind):
    _contact, token, row = _setup(db, kind)
    result = _revise(db, token, kind, row)
    assert result["revision_no"] == 1
    assert result["policy"]["used"] == 1
    assert result["policy"]["remaining"] == 2


# ------------------------------------------------------- reconstruction / rev 0


@pytest.mark.parametrize("kind", REVISABLE_TYPES)
def test_pre_feature_submission_backfills_a_reconstructed_original(db, kind):
    """UAC G2: a submission that predates the feature has no history, so revision 0
    is rebuilt from current state and flagged so nobody reads it as verbatim."""
    _contact, token, row = _setup(db, kind)
    assert _revisions(db, kind, str(row.id)) == []

    _revise(db, token, kind, row)

    original = _revisions(db, kind, str(row.id))[0]
    assert original.kind == "original"
    assert original.is_reconstructed is True


@pytest.mark.parametrize("kind", REVISABLE_TYPES)
def test_reconstructed_original_snapshots_the_version_being_superseded(db, kind):
    """The backfill runs BEFORE the payload is applied, or the "original" would hold
    the revised values and the diff would show nothing changed."""
    _contact, token, row = _setup(db, kind)
    field, new_value = _changed_field(kind)
    before = getattr(row, field)
    _revise(db, token, kind, row)

    original = _revisions(db, kind, str(row.id))[0]
    assert original.snapshot_json[field] == before
    assert original.snapshot_json[field] != new_value


# ------------------------------------------------------------- frozen requestor


@pytest.mark.parametrize("kind", REVISABLE_TYPES)
def test_a_revision_cannot_change_the_requestor(db, kind):
    """UAC AB2: the requestor FK is the CS pin routing key. Changing it is a
    reassignment disguised as an edit, so a revision may never do it."""
    _contact, token, row = _setup(db, kind)
    other = seed_contact(db, name="Somebody Else")
    fk = "salesperson_contact_id" if kind == "stock_inquiry" else "requested_by_contact_id"
    label = "salesperson" if kind == "stock_inquiry" else "requested_by"
    original_fk = getattr(row, fk)

    payload = dict(_revise_payload(kind))
    payload[fk] = other.id
    payload[label] = other.name
    _revise(db, token, kind, row, payload=payload)

    fresh = _reload(db, kind, str(row.id))
    assert getattr(fresh, fk) == original_fk
    assert getattr(fresh, label) != "Somebody Else"


# -------------------------------------------------------- invalidated stage output


def test_stock_inquiry_revision_clears_the_superseded_purchasing_answer(db):
    """UAC FB2/FB3: the answer priced the old version. Snapshotted, then cleared."""
    from datetime import datetime

    _contact, token, row = _setup(
        db,
        "stock_inquiry",
        status="responded",
        purchasing_response="In stock, 3 weeks",
        last_responded_by="someone",
        last_responded_at=datetime(2026, 8, 1, 9, 0),
    )
    _revise(db, token, "stock_inquiry", row)

    fresh = _reload(db, "stock_inquiry", str(row.id))
    assert fresh.purchasing_response is None
    assert fresh.last_responded_by is None
    assert fresh.last_responded_at is None

    revision = _revisions(db, "stock_inquiry", str(row.id))[1]
    assert revision.invalidated_json["purchasing_response"] == "In stock, 3 weeks"


@pytest.mark.parametrize("kind", ("purchase_request", "sponsorship_form"))
def test_request_revision_clears_the_approval_granted_to_the_old_version(db, kind):
    from datetime import datetime

    _contact, token, row = _setup(
        db,
        kind,
        status="approved",
        approval_status="approved",
        approved_by="A Manager",
        approved_at=datetime(2026, 8, 1, 9, 0),
        approval_comments="Fine by me",
    )
    _revise(db, token, kind, row)

    fresh = _reload(db, kind, str(row.id))
    assert fresh.approval_status is None
    assert fresh.approved_by is None
    assert fresh.approved_at is None

    revision = _revisions(db, kind, str(row.id))[1]
    assert revision.invalidated_json["approval_status"] == "approved"
    assert revision.invalidated_json["approved_by"] == "A Manager"


# ------------------------------------------------------------------- line items


@pytest.mark.parametrize("kind", ("purchase_request", "sponsorship_form"))
def test_line_items_are_snapshotted_and_diffed(db, kind):
    _contact, token, row = _setup(db, kind)
    payload = dict(_revise_payload(kind))
    payload["products"] = [
        {"item_code": "ITEM-A", "quantity": "5"},
        {"item_code": "ITEM-B", "quantity": "1"},
    ]
    _revise(db, token, kind, row, payload=payload)

    revision = _revisions(db, kind, str(row.id))[1]
    assert [line["item_code"] for line in revision.snapshot_json["products"]] == [
        "ITEM-A",
        "ITEM-B",
    ]

    entries = PortalRevisionService(db).list_revisions(kind, str(row.id))
    changes = {c["field"]: c for c in entries[1]["changes"]}
    assert "products[0].quantity" in changes  # 2 -> 5 on the existing line
    assert "products[1]" in changes  # ITEM-B added
    assert changes["products[1]"]["to"].startswith("ITEM-B")

    lines = (
        db.query(PurchaseRequestLine)
        .filter(PurchaseRequestLine.purchase_request_id == str(row.id))
        .all()
    )
    assert len(lines) == 2


def test_stock_inquiry_snapshot_has_no_products_key(db):
    _contact, token, row = _setup(db, "stock_inquiry")
    _revise(db, token, "stock_inquiry", row)
    assert "products" not in _revisions(db, "stock_inquiry", str(row.id))[1].snapshot_json


# ------------------------------------------------------------ replay / stale write


@pytest.mark.parametrize("kind", REVISABLE_TYPES)
def test_replaying_the_same_expected_revision_no_yields_one_revision(db, kind):
    """UAC C5: a double tap carries the SAME expected_revision_no twice. The second
    is refused with 409 and writes nothing - one revision, not two voids."""
    _contact, token, row = _setup(db, kind)
    _revise(db, token, kind, row, expected=0)

    with pytest.raises(HTTPException) as exc:
        _revise(db, token, kind, row, expected=0)
    assert exc.value.status_code == 409

    assert _reload(db, kind, str(row.id)).revision_no == 1
    assert len([r for r in _revisions(db, kind, str(row.id)) if r.kind == "revision"]) == 1


@pytest.mark.parametrize("kind", REVISABLE_TYPES)
def test_a_stale_expected_revision_no_is_refused(db, kind):
    _contact, token, row = _setup(db, kind, revision_no=2)
    with pytest.raises(HTTPException) as exc:
        _revise(db, token, kind, row, expected=1)
    assert exc.value.status_code == 409
    assert "revision 2" in str(exc.value.detail)


# ------------------------------------------------------------------ the reason


@pytest.mark.parametrize("reason", ["", "   ", "hi"])
@pytest.mark.parametrize("kind", ("stock_inquiry",))
def test_a_blank_or_too_short_reason_is_refused(db, kind, reason):
    _contact, token, row = _setup(db, kind)
    with pytest.raises(HTTPException) as exc:
        _revise(db, token, kind, row, reason=reason)
    assert exc.value.status_code == 422
    assert _reload(db, kind, str(row.id)).revision_no == 0


def test_an_over_long_reason_is_refused(db):
    _contact, token, row = _setup(db, "stock_inquiry")
    with pytest.raises(HTTPException) as exc:
        _revise(db, token, "stock_inquiry", row, reason="x" * 2001)
    assert exc.value.status_code == 422


# ------------------------------------------------------------------- policy gate


@pytest.mark.parametrize("kind", REVISABLE_TYPES)
def test_revise_re_checks_the_policy_server_side(db, kind):
    """UAC B4: the FE gate is a convenience. A blocked record is refused with the
    same human sentence even when the client asks anyway."""
    seed_system_settings(db, cap=2)
    seed_config(db, kind)
    contact = seed_contact(db)
    row = seed_entity(db, kind, contact, revision_no=2)  # cap reached
    with pytest.raises(HTTPException) as exc:
        _revise(db, seed_token(contact), kind, row, expected=2)
    assert exc.value.status_code == 422
    assert "used all 2 revisions" in str(exc.value.detail)


def test_complaint_cannot_be_revised(db):
    seed_config(db, "complaint", is_enabled=True, allowed_statuses=["submitted"])
    contact = seed_contact(db)
    from app.models.complaints import Complaint

    complaint = Complaint(id=str(uuid.uuid4()), status="submitted", contact_id=contact.id)
    db.add(complaint)
    db.commit()
    with pytest.raises(HTTPException) as exc:
        PortalRevisionService(db).revise(
            seed_token(contact), "complaint", str(complaint.id), {}, "Because reasons", 0
        )
    assert exc.value.status_code == 422
    assert "cannot be revised" in str(exc.value.detail)


# -------------------------------------------------------------------- ownership


@pytest.mark.parametrize("kind", REVISABLE_TYPES)
def test_another_contacts_token_cannot_revise(db, kind):
    _contact, _token, row = _setup(db, kind)
    intruder = seed_contact(db, name="Intruder")
    with pytest.raises(HTTPException) as exc:
        _revise(db, seed_token(intruder), kind, row)
    assert exc.value.status_code in (403, 404)
    assert _reload(db, kind, str(row.id)).revision_no == 0


# ------------------------------------------------------------------- the history


@pytest.mark.parametrize("kind", REVISABLE_TYPES)
def test_history_labels_and_changes(db, kind):
    _contact, token, row = _setup(db, kind)
    _revise(db, token, kind, row)

    entries = PortalRevisionService(db).list_revisions(kind, str(row.id))
    assert [e["label"] for e in entries] == ["Original (reconstructed)", "Revision 1"]
    assert entries[0]["changes"] == []  # nothing to compare the original against
    field, value = _changed_field(kind)
    changed = {c["field"]: c for c in entries[1]["changes"]}
    assert changed[field]["to"] == value
    assert changed[field]["label"]  # a human label, never the raw column name


@pytest.mark.parametrize("kind", REVISABLE_TYPES)
def test_history_entry_declares_every_contract_field(db, kind):
    _contact, token, row = _setup(db, kind)
    _revise(db, token, kind, row)
    entry = PortalRevisionService(db).list_revisions(kind, str(row.id))[1]
    assert {
        "id",
        "version_no",
        "revision_no",
        "kind",
        "label",
        "reason",
        "submitted_at",
        "submitted_by",
        "is_reconstructed",
        "snapshot",
        "attachments",
        "invalidated",
        "voided_stage_code",
        "voided_assignee_name",
        "changes",
    } <= set(entry)


def test_history_records_which_stage_the_revision_voided(db):
    """UAC H3: the office tab shows what stopped and who was on it."""
    _contact, token, row = _setup(db, "stock_inquiry")
    from tests._revision_harness import seed_stage_config, seed_user

    policy_id = seed_policy(db)
    seed_stage_config(
        db,
        "stock_inquiry",
        policy_id,
        stage_code="purchasing",
        team_set_code="purchasing",
        start_event="project_sales_approve",
    )
    handler = seed_user(db, name="Purchasing Pat")
    seed_tracker(
        db,
        "stock_inquiry",
        str(row.id),
        policy_id,
        team_set_code="purchasing",
        assigned_to_id=handler.id,
    )

    _revise(db, token, "stock_inquiry", row)

    revision = _revisions(db, "stock_inquiry", str(row.id))[1]
    assert revision.voided_stage_code == "purchasing"
    assert revision.voided_assignee_user_id == handler.id

    entry = PortalRevisionService(db).list_revisions("stock_inquiry", str(row.id))[1]
    assert entry["voided_assignee_name"] == "Purchasing Pat"


# ------------------------------------------------------- two counters, not one


@pytest.mark.parametrize("kind", REVISABLE_TYPES)
def test_a_resubmission_advances_version_but_not_the_cap(db, kind):
    """UAC C1/C4: an office reject that the contact answers is a new VERSION, not one
    of their revisions - and it must appear in the history all the same."""
    from app.services.portal_service import PortalService

    seed_system_settings(db, cap=2)
    seed_config(db, kind)
    contact = seed_contact(db)
    token = seed_token(contact)
    row = seed_entity(db, kind, contact, status="rejected")
    if kind != "stock_inquiry":
        row.approval_status = "rejected"
        row.approval_comments = "Missing the delivery address"
    else:
        row.rejection_reason = "Missing the delivery address"
    db.commit()

    service = PortalService(db)
    with patch.object(service, "get_submission", return_value={}), patch.object(
        service, "_post_submit_notify"
    ):
        service.submit_draft(token, kind, str(row.id))

    rows = _revisions(db, kind, str(row.id))
    assert [r.kind for r in rows] == ["original", "resubmission"]
    assert [r.version_no for r in rows] == [0, 1]
    assert [r.revision_no for r in rows] == [0, 0]  # the cap is untouched
    assert rows[1].reason == "Missing the delivery address"
    assert _reload(db, kind, str(row.id)).revision_no == 0


def test_a_failing_history_write_does_not_undo_the_submit(db):
    """The history row lives in a SAVEPOINT opened AFTER the submit's own changes are
    flushed. Without that flush, rolling the savepoint back would take the status
    transition with it - a lost submit to save a history row."""
    from app.services.portal_service import PortalService

    seed_config(db, "stock_inquiry")
    contact = seed_contact(db)
    token = seed_token(contact)
    from datetime import datetime

    row = seed_entity(
        db, "stock_inquiry", contact, status="draft", portal_draft_at=datetime.utcnow()
    )

    service = PortalService(db)
    with patch.object(service, "get_submission", return_value={}), patch.object(
        service, "_post_submit_notify"
    ), patch.object(
        PortalRevisionService, "record_submission", side_effect=RuntimeError("history down")
    ):
        service.submit_draft(token, "stock_inquiry", str(row.id))

    fresh = _reload(db, "stock_inquiry", str(row.id))
    assert fresh.status == "pending_project_sales"
    assert fresh.portal_draft_at is None
    assert _revisions(db, "stock_inquiry", str(row.id)) == []


@pytest.mark.parametrize("kind", REVISABLE_TYPES)
def test_first_submit_writes_the_original_once(db, kind):
    from app.services.portal_service import PortalService

    seed_config(db, kind)
    contact = seed_contact(db)
    token = seed_token(contact)
    from datetime import datetime

    row = seed_entity(db, kind, contact, status="draft", portal_draft_at=datetime.utcnow())

    service = PortalService(db)
    with patch.object(service, "get_submission", return_value={}), patch.object(
        service, "_post_submit_notify"
    ):
        service.submit_draft(token, kind, str(row.id))

    rows = _revisions(db, kind, str(row.id))
    assert [(r.kind, r.version_no, r.revision_no, r.is_reconstructed) for r in rows] == [
        ("original", 0, 0, False)
    ]
