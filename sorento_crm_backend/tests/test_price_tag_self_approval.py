"""PRICETAG-SELF-APPROVAL (owner rulings 2 Nov 2026).

The salesperson approves his own price tag: submit lands at ``proof_ready`` with
nobody assigned, Approve carries the tag sheet he saw and saves it as the design
version the PDF prints from, Edit (the revise path) returns the request to him with
no cap, and Escalate hands it to the form SLA config's assignee with his note.

Plan: documentation/plans/dealer-kit/PLAN-pricetag-self-approval-02nov.md (R1-R10),
UAC alongside (AC1-AC14).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves the circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402
from tests._pg_fixture import blank_session
from tests.test_price_tag_request_auto_assign import (
    _seed_contact_who_can_see_the_form,
    _seed_one_member_tier1_config,
    _seed_product,
    _submittable_payload,
)

_BASE = "/api/v1/public/portal/submissions/price_tag_request"
_REVISE = "/api/v1/public/portal/submissions/price_tag_request/{id}/revise"


@pytest.fixture(autouse=True)
def no_queue():
    with patch("app.services.queue_service.enqueue_job", return_value=None):
        yield


@pytest.fixture
def client():
    from app.api.v1.public.portal import get_portal_token
    from app.database import get_db
    from app.models.portal import PortalToken

    with blank_session() as db:
        contact_id = _seed_contact_who_can_see_the_form(db)
        # Every line needs a published price tag template to draw (and the
        # server rebuilds each placement from it, review B2): the family
        # default covers any product.
        state = {"contact_id": contact_id, "template_id": _published_template(db)}

        def _override_get_db():
            yield db

        def _override_portal_token():
            return PortalToken(
                id=str(uuid.uuid4()),
                token="zzt-token",
                contact_id=state["contact_id"],
                space_id="zzt-space",
                expires_at=datetime(2099, 1, 1),
                verified_at=datetime(2026, 1, 1),
            )

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_portal_token] = _override_portal_token
        try:
            with TestClient(app, headers={"X-Portal-Token": "zzt-token"}) as c:
                yield c, db, state
        finally:
            app.dependency_overrides.clear()


def _published_template(db) -> str:
    from tests.test_product_tag_templates import _template

    template_id = _template(db, "ZZT self tag")
    db.commit()
    return template_id


def _linked_product(db) -> str:
    """A product linked to this test's published template (#2100: an unlinked
    product has no template at all, so nothing would draw or approve)."""
    from app.models.dealer_kit import TagTemplate
    from tests.test_product_tag_templates import _link

    product_id = _seed_product(db)
    template = (
        db.query(TagTemplate)
        .filter(TagTemplate.name.ilike("%self tag%"))
        .order_by(TagTemplate.created_at.desc())
        .first()
    )
    _link(db, product_id, template.id)
    db.commit()
    return product_id


def _payload(product_id: str, print_by: str = "self") -> dict:
    body = _submittable_payload(product_id)
    body["print_by"] = print_by
    return body


def _submitted(c, db, *, print_by: str = "self") -> dict:
    product_id = _linked_product(db)
    created = c.post(_BASE, json=_payload(product_id, print_by)).json()
    res = c.post(f"{_BASE}/{created['id']}/submit")
    assert res.status_code == 200, res.text
    return res.json()


def _tag_ids(db, request_id: str) -> list[str]:
    from app.services.price_tag_request_service import PriceTagRequestService

    db.expire_all()
    req = PriceTagRequestService.get_request(db, request_id)
    return [tag.id for line in req.lines for tag in line.tags or []]


def _sheet(tag_ids: list[str]) -> dict:
    return {
        "kind": "tag_sheet",
        "imposition": {
            "preset": "auto",
            "page_width_mm": 210,
            "page_height_mm": 297,
            "bleed_mm": 5,
            "gap_mm": 0,
        },
        "sheets": [
            {
                "id": "sheet-1",
                "tags": [
                    {
                        "id": f"placed-{i}",
                        "template_id": "starter",
                        "request_tag_id": tag_id,
                        "x_mm": 0,
                        "y_mm": 0,
                        "width_mm": 90,
                        "height_mm": 60,
                        "layers": [],
                    }
                    for i, tag_id in enumerate(tag_ids)
                ],
            }
        ],
    }


def _placed_tag_ids(db, request_id: str) -> list[str]:
    """Each printed tag as many times as its quantity: what the client builder seats."""
    from app.services.price_tag_request_service import PriceTagRequestService

    db.expire_all()
    req = PriceTagRequestService.get_request(db, request_id)
    return [
        tag.id
        for line in req.lines
        for tag in line.tags or []
        if not tag.print_excluded
        for _ in range(max(tag.quantity or 0, 1))
    ]


def _approve(c, db, request_id: str, doc: dict | None = None):
    body = {"doc": doc if doc is not None else _sheet(_placed_tag_ids(db, request_id))}
    return c.post(f"{_BASE}/{request_id}/approve", json=body)


def _versions(db, request_id: str) -> list:
    from app.models.dealer_kit import PageVersion
    from app.models.price_tag import PriceTagRequest

    db.expire_all()
    req = db.query(PriceTagRequest).filter(PriceTagRequest.id == request_id).first()
    if not req.page_id:
        return []
    return (
        db.query(PageVersion)
        .filter(PageVersion.page_id == req.page_id)
        .order_by(PageVersion.version.asc())
        .all()
    )


def _row(db, request_id: str):
    from app.models.price_tag import PriceTagRequest

    db.expire_all()
    return db.query(PriceTagRequest).filter(PriceTagRequest.id == request_id).first()


def _revise(c, db, request_id: str, *, reason: str = "Price was wrong"):
    row = _row(db, request_id)
    product_id = row.lines[0].product_id
    return c.post(
        _REVISE.format(id=request_id),
        json={
            "expected_revision_no": row.revision_no or 0,
            "reason": reason,
            "fields": {"debtor_name": "ZZT Revised Dealer"},
            "products": [{"product_id": product_id, "quantity": 2}],
        },
    )


def _trackers(db, request_id: str) -> list:
    from app.models.sla import ConversationSLATracking

    return (
        db.query(ConversationSLATracking)
        .filter(
            ConversationSLATracking.source_entity_type == "price_tag_request",
            ConversationSLATracking.source_entity_id == str(request_id),
        )
        .all()
    )


# --------------------------------------------------------------------------- #
# R1 / AC1: submit waits for the salesperson, not marketing
# --------------------------------------------------------------------------- #


class TestSubmit:
    def test_submit_lands_at_proof_ready_with_nobody_assigned(self, client):
        c, db, _ = client
        _seed_one_member_tier1_config(db)

        body = _submitted(c, db)

        assert body["status"] == "proof_ready"
        assert body["assigned_to_id"] is None

    def test_submit_opens_no_form_sla_tracker(self, client):
        c, db, _ = client
        _seed_one_member_tier1_config(db)

        body = _submitted(c, db)

        assert _trackers(db, body["id"]) == []


# --------------------------------------------------------------------------- #
# R3 / AC2-AC5: approve saves the sheet he saw
# --------------------------------------------------------------------------- #


class TestApprove:
    def test_approve_saves_the_sheet_as_a_version_and_approves(self, client):
        c, db, _ = client
        body = _submitted(c, db)
        tag_ids = _tag_ids(db, body["id"])
        doc = _sheet(tag_ids)

        res = _approve(c, db, body["id"], doc)

        assert res.status_code == 200, res.text
        assert res.json()["status"] == "approved"
        versions = _versions(db, body["id"])
        assert len(versions) == 1
        placed = [t["request_tag_id"] for s in versions[0].doc["sheets"] for t in s["tags"]]
        assert placed == tag_ids

    def test_approve_pins_every_tag(self, client):
        c, db, _ = client
        body = _submitted(c, db)

        _approve(c, db, body["id"])

        row = _row(db, body["id"])
        tags = [tag for line in row.lines for tag in line.tags]
        assert tags and all(tag.pinned_tag_data is not None for tag in tags)

    def test_approve_queues_one_export_requested_by_the_contact(self, client):
        c, db, state = client
        body = _submitted(c, db)
        with patch(
            "app.services.dealer_kit.tag_sheet_export_service.request_tag_sheet_export"
        ) as export:
            _approve(c, db, body["id"])
        assert export.call_count == 1
        assert export.call_args.kwargs["user_id"] == state["contact_id"]

    def test_approve_without_a_doc_is_refused(self, client):
        c, db, _ = client
        body = _submitted(c, db)

        res = c.post(f"{_BASE}/{body['id']}/approve", json={})

        assert res.status_code == 422, res.text
        assert res.json().get("code") == "DOC_REQUIRED"
        assert _row(db, body["id"]).status == "proof_ready"
        assert _versions(db, body["id"]) == []

    def test_a_placement_for_another_requests_tag_is_refused(self, client):
        c, db, _ = client
        mine = _submitted(c, db)
        other = _submitted(c, db)
        doc = _sheet(_tag_ids(db, other["id"]))

        res = _approve(c, db, mine["id"], doc)

        assert res.status_code == 422, res.text
        assert _row(db, mine["id"]).status == "proof_ready"
        assert _versions(db, mine["id"]) == []

    def test_a_doc_that_is_not_a_tag_sheet_is_refused(self, client):
        c, db, _ = client
        body = _submitted(c, db)

        res = _approve(c, db, body["id"], {"kind": "page", "sheets": []})

        assert res.status_code == 422, res.text

    def test_approving_twice_is_refused_and_writes_one_version(self, client):
        c, db, _ = client
        body = _submitted(c, db)
        _approve(c, db, body["id"])

        res = _approve(c, db, body["id"])

        assert res.status_code == 409, res.text
        assert len(_versions(db, body["id"])) == 1

    def test_escalated_proof_approves_marketings_version_and_ignores_a_doc(self, client):
        """AC5: an assignee on a proof means marketing drew it."""
        from app.api.v1.dealer_kit.price_tag_requests import _snapshot_draft
        from app.models.dealer_kit import Page
        from app.services.price_tag_request_service import PriceTagRequestService

        c, db, _ = client
        member_id = _seed_one_member_tier1_config(db)
        body = _submitted(c, db)
        c.post(f"{_BASE}/{body['id']}/escalate", json={"note": "Photo is the old model"})
        row = _row(db, body["id"])
        assert row.assigned_to_id == member_id
        page = db.query(Page).filter(Page.id == row.page_id).first()
        marketing_doc = _sheet(_tag_ids(db, body["id"]))
        marketing_doc["sheets"][0]["id"] = "marketing-sheet"
        _snapshot_draft(db, page, marketing_doc, member_id, "Marketing")
        PriceTagRequestService.transition_status(db, body["id"], "proof_ready", user_id=member_id)

        res = _approve(c, db, body["id"])

        assert res.status_code == 200, res.text
        versions = _versions(db, body["id"])
        assert len(versions) == 1
        assert versions[0].doc["sheets"][0]["id"] == "marketing-sheet"


# --------------------------------------------------------------------------- #
# R4 / R5 / AC6-AC8: edit after approval, no cap, back to him
# --------------------------------------------------------------------------- #


class TestEditAfterApproval:
    def test_edit_after_approval_returns_it_to_him_with_a_revision(self, client):
        from app.models.portal import PortalFormRevision

        c, db, _ = client
        body = _submitted(c, db)
        _approve(c, db, body["id"])

        res = _revise(c, db, body["id"])

        assert res.status_code == 200, res.text
        row = _row(db, body["id"])
        assert row.status == "proof_ready"
        assert row.assigned_to_id is None
        assert row.revision_no == 1
        kinds = [
            r.kind
            for r in db.query(PortalFormRevision)
            .filter(PortalFormRevision.source_entity_id == str(body["id"]))
            .all()
        ]
        assert "revision" in kinds

    def test_edit_ignores_the_portal_revisions_settings_and_has_no_cap(self, client):
        from app.models.portal import PortalRevisionConfig
        from app.models.user import SystemSetting

        c, db, _ = client
        db.add(SystemSetting(id=str(uuid.uuid4()), portal_revisions_enabled=False, portal_max_revisions=1))
        db.add(
            PortalRevisionConfig(
                id=str(uuid.uuid4()),
                source_entity_type="price_tag_request",
                is_enabled=False,
                max_revisions=1,
                allowed_statuses=["new"],
            )
        )
        db.commit()
        body = _submitted(c, db)

        for round_no in range(1, 4):
            _approve(c, db, body["id"])
            res = _revise(c, db, body["id"], reason=f"Round {round_no}")
            assert res.status_code == 200, res.text

        assert _row(db, body["id"]).revision_no == 3

    def test_edit_opens_no_tracker_and_rings_no_one(self, client):
        c, db, _ = client
        _seed_one_member_tier1_config(db)
        body = _submitted(c, db)
        _approve(c, db, body["id"])

        with patch("app.services.form_sla_service.emit_form_event") as emit:
            _revise(c, db, body["id"])

        assert emit.call_count == 0
        assert _trackers(db, body["id"]) == []

    def test_edit_after_an_escalation_takes_it_back_from_marketing(self, client):
        c, db, _ = client
        member_id = _seed_one_member_tier1_config(db)
        body = _submitted(c, db)
        c.post(f"{_BASE}/{body['id']}/escalate", json={"note": "Wrong photo"})
        row = _row(db, body["id"])
        row.status = "approved"
        db.commit()
        assert row.assigned_to_id == member_id

        res = _revise(c, db, body["id"])

        assert res.status_code == 200, res.text
        row = _row(db, body["id"])
        assert row.status == "proof_ready"
        assert row.assigned_to_id is None

    @pytest.mark.parametrize("status", ["ready_for_collection", "collected", "void", "rejected"])
    def test_edit_is_refused_once_finished(self, client, status):
        c, db, _ = client
        body = _submitted(c, db)
        row = _row(db, body["id"])
        row.status = status
        db.commit()

        res = _revise(c, db, body["id"])

        assert res.status_code == 422, res.text
        assert _row(db, body["id"]).revision_no == 0

    @pytest.mark.parametrize("status", ["new", "designing", "changes_requested", "proof_ready"])
    def test_edit_is_refused_while_marketing_holds_it(self, client, status):
        c, db, _ = client
        member_id = _seed_one_member_tier1_config(db)
        body = _submitted(c, db)
        row = _row(db, body["id"])
        row.status = status
        row.assigned_to_id = member_id
        db.commit()

        res = _revise(c, db, body["id"])

        assert res.status_code == 422, res.text

    def test_the_old_pdf_is_not_served_after_an_edit(self, client):
        c, db, _ = client
        body = _submitted(c, db)
        _approve(c, db, body["id"])
        _revise(c, db, body["id"])

        with patch(
            "app.api.v1.public.portal_price_tag.latest_completed_export"
        ) as latest:
            res = c.get(f"{_BASE}/{body['id']}/download")

        assert res.status_code == 409, res.text
        assert latest.call_count == 0

    def test_re_approval_writes_a_second_version(self, client):
        c, db, _ = client
        body = _submitted(c, db)
        _approve(c, db, body["id"])
        _revise(c, db, body["id"])

        res = _approve(c, db, body["id"])

        assert res.status_code == 200, res.text
        assert [v.version for v in _versions(db, body["id"])] == [1, 2]


# --------------------------------------------------------------------------- #
# R6 / AC9-AC11: escalate to the configured assignee
# --------------------------------------------------------------------------- #


class TestEscalate:
    def test_escalate_goes_to_the_config_assignee_with_the_note(self, client):
        from app.services import price_tag_review_service

        c, db, _ = client
        member_id = _seed_one_member_tier1_config(db)
        body = _submitted(c, db)

        res = c.post(f"{_BASE}/{body['id']}/escalate", json={"note": "Photo is the old model"})

        assert res.status_code == 200, res.text
        row = _row(db, body["id"])
        assert row.status == "designing"
        assert row.assigned_to_id == member_id
        assert len(_trackers(db, body["id"])) == 1
        notes = [x.body for x in price_tag_review_service.list_comments(db, row.id)]
        assert "Photo is the old model" in notes

    def test_escalate_after_approval(self, client):
        c, db, _ = client
        member_id = _seed_one_member_tier1_config(db)
        body = _submitted(c, db)
        _approve(c, db, body["id"])

        res = c.post(f"{_BASE}/{body['id']}/escalate", json={"note": "Dealer wants a bigger tag"})

        assert res.status_code == 200, res.text
        row = _row(db, body["id"])
        assert row.status == "designing"
        assert row.assigned_to_id == member_id

    def test_escalate_with_no_config_waits_for_a_claim(self, client):
        c, db, _ = client
        body = _submitted(c, db)

        res = c.post(f"{_BASE}/{body['id']}/escalate", json={"note": "Help"})

        assert res.status_code == 200, res.text
        row = _row(db, body["id"])
        assert row.status == "new"
        assert row.assigned_to_id is None

    def test_escalate_needs_a_note(self, client):
        c, db, _ = client
        body = _submitted(c, db)

        res = c.post(f"{_BASE}/{body['id']}/escalate", json={"note": "   "})

        assert res.status_code == 422, res.text
        assert _row(db, body["id"]).status == "proof_ready"

    @pytest.mark.parametrize("status", ["ready_for_collection", "collected", "void", "designing"])
    def test_escalate_is_refused_outside_his_hands(self, client, status):
        c, db, _ = client
        body = _submitted(c, db)
        row = _row(db, body["id"])
        row.status = status
        db.commit()

        res = c.post(f"{_BASE}/{body['id']}/escalate", json={"note": "Help"})

        assert res.status_code == 409, res.text

    def test_escalating_someone_elses_request_is_404(self, client):
        c, db, state = client
        body = _submitted(c, db)
        state["contact_id"] = _seed_contact_who_can_see_the_form(db)

        res = c.post(f"{_BASE}/{body['id']}/escalate", json={"note": "Help"})

        assert res.status_code == 404, res.text


# --------------------------------------------------------------------------- #
# R8 / AC12: marketing has nothing to do on a request that is not escalated
# --------------------------------------------------------------------------- #


class TestMarketingGate:
    def test_design_save_is_refused_on_his_own_proof(self, client):
        from app.services.error_handler import AppException
        from app.services.price_tag_request_service import PriceTagRequestService

        c, db, _ = client
        body = _submitted(c, db)

        with pytest.raises(AppException) as exc:
            PriceTagRequestService.validate_designable(_row(db, body["id"]))
        assert exc.value.status_code == 409

    def test_design_save_is_allowed_on_an_escalated_proof(self, client):
        from app.services.price_tag_request_service import PriceTagRequestService

        c, db, _ = client
        member_id = _seed_one_member_tier1_config(db)
        body = _submitted(c, db)
        c.post(f"{_BASE}/{body['id']}/escalate", json={"note": "Help"})
        row = _row(db, body["id"])
        assert row.assigned_to_id == member_id

        PriceTagRequestService.validate_designable(row)


class TestDetailFlags:
    def test_own_proof_is_self_review_and_escalatable(self, client):
        c, db, _ = client
        body = _submitted(c, db)

        detail = c.get(f"{_BASE}/{body['id']}").json()

        assert detail["self_review"] is True
        assert detail["can_escalate"] is True

    def test_marketings_proof_is_neither(self, client):
        c, db, _ = client
        _seed_one_member_tier1_config(db)
        body = _submitted(c, db)
        c.post(f"{_BASE}/{body['id']}/escalate", json={"note": "Help"})

        detail = c.get(f"{_BASE}/{body['id']}").json()

        assert detail["self_review"] is False
        assert detail["can_escalate"] is False


class TestCopy:
    def test_submitted_says_the_tag_waits_for_him(self):
        from app.services.price_tag_notify import _copy

        line = _copy("submitted", doc_number="PT-1", link="", ctx={})
        assert line == "PT-1 received. Your tag is ready for you to check and approve."

    def test_escalation_is_confirmed(self):
        from app.services.price_tag_notify import _copy

        assert _copy("new", doc_number="PT-1", link="", ctx={}) == (
            "PT-1 sent to marketing with your note."
        )


# --------------------------------------------------------------------------- #
# Review round 1
# --------------------------------------------------------------------------- #


def _seed_ready_export(db, request_id: str) -> None:
    """A finished PDF of the request's CURRENT latest version."""
    from app.models.dealer_kit import ExportRequest
    from app.models.download import DownloadStatus, UserDownload

    versions = _versions(db, request_id)
    download = UserDownload(
        user_id=str(uuid.uuid4()),
        kind="dealer_kit_tag_sheet_pdf",
        source_entity_type="price_tag_request",
        source_entity_id=str(request_id),
        status=DownloadStatus.READY.value,
        filename="old.pdf",
        storage_key=f"zzt/{uuid.uuid4().hex}.pdf",
    )
    db.add(download)
    db.flush()
    db.add(
        ExportRequest(
            download_id=download.id,
            page_id=_row(db, request_id).page_id,
            page_version_id=versions[-1].id,
            audience="staff",
            show_invoice_price=False,
        )
    )
    db.commit()


class TestOnlyTheCurrentVersionsPdf:
    """B1: a PDF of the version before an edit is never served or reported ready."""

    def test_after_re_approval_the_old_pdf_is_not_served(self, client):
        from app.services.dealer_kit import tag_sheet_export_service as svc

        c, db, _ = client
        body = _submitted(c, db)
        _approve(c, db, body["id"])
        _seed_ready_export(db, body["id"])
        assert svc.latest_completed_export(db, body["id"]) is not None
        _revise(c, db, body["id"])
        with patch(
            "app.services.dealer_kit.tag_sheet_export_service.request_tag_sheet_export"
        ):
            _approve(c, db, body["id"])

        assert svc.latest_completed_export(db, body["id"]) is None
        assert svc.latest_export_status(db, body["id"]) is None
        res = c.get(f"{_BASE}/{body['id']}/download")
        assert res.status_code == 404, res.text

    def test_a_running_export_of_the_old_version_is_not_reused(self, client):
        from app.models.download import DownloadStatus, UserDownload
        from app.services.dealer_kit import tag_sheet_export_service as svc

        c, db, _ = client
        body = _submitted(c, db)
        _approve(c, db, body["id"])
        old = (
            db.query(UserDownload)
            .filter(UserDownload.source_entity_id == str(body["id"]))
            .first()
        )
        assert old is not None and old.status == DownloadStatus.PENDING.value
        _revise(c, db, body["id"])
        _approve(c, db, body["id"])

        downloads = (
            db.query(UserDownload)
            .filter(UserDownload.source_entity_id == str(body["id"]))
            .all()
        )
        assert len(downloads) == 2
        current = svc._request_downloads(db, body["id"]).all()
        assert [d.id for d in current] != [old.id]


class TestTheServerWritesTheTagContent:
    """B2: only positions come from the client; content is the line's template."""

    def test_layers_and_template_are_rebuilt_from_the_lines_template(self, client):
        c, db, state = client
        body = _submitted(c, db)
        doc = _sheet(_tag_ids(db, body["id"]))
        forged = doc["sheets"][0]["tags"][0]
        forged["template_id"] = "not-a-template"
        forged["layers"] = [{"id": "x", "type": "text", "props": {"kind": "text", "text": "RM 1.00 NETT"}}]
        forged["x_mm"] = 12
        doc["junk"] = "x" * 1000

        res = _approve(c, db, body["id"], doc)

        assert res.status_code == 200, res.text
        saved = _versions(db, body["id"])[0].doc
        placed = saved["sheets"][0]["tags"][0]
        assert placed["template_id"] == state["template_id"]
        assert "RM 1.00 NETT" not in str(placed["layers"])
        assert placed["x_mm"] == 12
        assert "junk" not in saved

    def test_the_saved_layers_are_the_templates_bound_to_the_line(self, client):
        """N2: the rebuild copies the published layers and binds groups to the line."""
        from app.models.dealer_kit import TagTemplate, TagTemplateVersion

        c, db, state = client
        template = db.query(TagTemplate).filter(TagTemplate.id == state["template_id"]).first()
        version = (
            db.query(TagTemplateVersion)
            .filter(TagTemplateVersion.id == template.published_version_id)
            .first()
        )
        group = {
            "id": "grp",
            "type": "group",
            "x_mm": 0,
            "y_mm": 0,
            "width_mm": 40,
            "height_mm": 20,
            "rotation_deg": 0,
            "z_index": 1,
            "props": {"kind": "group", "binding": {"product_id": "someone-else"}, "children": []},
        }
        version.doc = {**version.doc, "layers": [*version.doc["layers"], group]}
        db.commit()
        body = _submitted(c, db)
        product_id = _row(db, body["id"]).lines[0].product_id

        _approve(c, db, body["id"])

        placed = _versions(db, body["id"])[0].doc["sheets"][0]["tags"][0]
        expected = [*version.doc["layers"][:-1], {**group, "props": {**group["props"], "binding": {"product_id": product_id}}}]
        assert placed["layers"] == expected

    def test_a_sheet_that_leaves_a_tag_out_is_refused(self, client):
        """N1: every printed tag is placed exactly its quantity of times."""
        c, db, _ = client
        body = _submitted(c, db)
        row = _row(db, body["id"])
        row.lines[0].tags[0].quantity = 3
        db.commit()
        tag_id = _tag_ids(db, body["id"])[0]

        res = _approve(c, db, body["id"], _sheet([tag_id]))

        assert res.status_code == 422, res.text
        assert _versions(db, body["id"]) == []
        assert _approve(c, db, body["id"], _sheet([tag_id] * 3)).status_code == 200

    def test_a_not_printed_tag_may_be_left_out(self, client):
        c, db, _ = client
        product_a = _linked_product(db)
        product_b = _linked_product(db)
        payload = _payload(product_a)
        payload["lines"].append({"line_type": "product", "product_id": product_b})
        created = c.post(_BASE, json=payload).json()
        c.post(f"{_BASE}/{created['id']}/submit")
        row = _row(db, created["id"])
        row.lines[1].tags[0].print_excluded = True
        db.commit()
        printed = row.lines[0].tags[0].id

        res = _approve(c, db, created["id"], _sheet([printed]))

        assert res.status_code == 200, res.text

    def test_a_non_finite_position_is_clamped_not_a_500(self, client):
        c, db, _ = client
        body = _submitted(c, db)
        doc = _sheet(_tag_ids(db, body["id"]))
        doc["sheets"][0]["tags"][0]["x_mm"] = "nan"
        doc["sheets"][0]["tags"][0]["y_mm"] = "Infinity"

        res = _approve(c, db, body["id"], doc)

        assert res.status_code == 200, res.text
        placed = _versions(db, body["id"])[0].doc["sheets"][0]["tags"][0]
        assert (placed["x_mm"], placed["y_mm"]) == (0, 0)

    def test_a_tag_placed_more_often_than_its_quantity_is_refused(self, client):
        c, db, _ = client
        body = _submitted(c, db)
        tag_id = _tag_ids(db, body["id"])[0]

        res = _approve(c, db, body["id"], _sheet([tag_id] * 50))

        assert res.status_code == 422, res.text
        assert _versions(db, body["id"]) == []

    def test_too_many_sheets_is_refused(self, client):
        c, db, _ = client
        body = _submitted(c, db)
        doc = _sheet(_tag_ids(db, body["id"]))
        doc["sheets"] = doc["sheets"] + [{"id": f"s{i}", "tags": []} for i in range(60)]

        res = _approve(c, db, body["id"], doc)

        assert res.status_code == 422, res.text

    def test_a_line_with_no_template_cannot_be_approved(self, client):
        from app.models.dealer_kit import TagTemplate

        c, db, state = client
        body = _submitted(c, db)
        db.query(TagTemplate).filter(TagTemplate.id == state["template_id"]).update(
            {"published_version_id": None}
        )
        db.commit()

        res = _approve(c, db, body["id"])

        assert res.status_code == 422, res.text
        assert res.json().get("code") == "NO_TEMPLATE"
        assert res.json()["message"].startswith("No tag template yet for ")
        assert res.json()["message"].endswith("Escalate it to marketing.")


class TestSlaStages:
    def test_a_second_escalation_starts_a_fresh_stage(self, client):
        c, db, _ = client
        _seed_one_member_tier1_config(db)
        body = _submitted(c, db)
        c.post(f"{_BASE}/{body['id']}/escalate", json={"note": "First"})
        row = _row(db, body["id"])
        row.status = "approved"
        db.commit()

        res = c.post(f"{_BASE}/{body['id']}/escalate", json={"note": "Second"})

        assert res.status_code == 200, res.text
        db.expire_all()
        trackers = _trackers(db, body["id"])
        assert len(trackers) == 2
        assert sum(1 for t in trackers if t.voided_at is None) == 1

    def test_edit_after_an_escalation_voids_the_open_stage(self, client):
        c, db, _ = client
        _seed_one_member_tier1_config(db)
        body = _submitted(c, db)
        c.post(f"{_BASE}/{body['id']}/escalate", json={"note": "Help"})
        row = _row(db, body["id"])
        row.status = "approved"
        db.commit()

        _revise(c, db, body["id"])

        db.expire_all()
        trackers = _trackers(db, body["id"])
        assert trackers and all(t.voided_at is not None for t in trackers)


class TestStaffCannotSendBackToNew:
    def test_the_staff_transition_route_refuses_new(self, client):
        from app.api.v1.dealer_kit.price_tag_requests import transition_price_tag_request
        from app.schemas.price_tag import TransitionPayload
        from app.services.error_handler import AppException

        c, db, _ = client
        body = _submitted(c, db)
        _approve(c, db, body["id"])

        with pytest.raises(AppException) as exc:
            transition_price_tag_request(
                body["id"], TransitionPayload(status="new"), db=db, user={"id": None}
            )

        assert exc.value.status_code == 409
        assert _row(db, body["id"]).status == "approved"


def test_a_short_sheet_refusal_carries_no_ids(client):
    """The toast reads `detail` before `message`; ids never reach the UI."""
    c, db, _ = client
    body = _submitted(c, db)
    row = _row(db, body["id"])
    row.lines[0].tags[0].quantity = 2
    db.commit()

    res = _approve(c, db, body["id"], _sheet(_tag_ids(db, body["id"])))

    assert res.status_code == 422
    assert res.json().get("detail") in (None, "")
    assert "leaves out" in res.json()["message"]


# --------------------------------------------------------------------------- #
# Owner ruling 3 Nov 14:10: no plain Submit on the form. A draft is approved or
# escalated in ONE step from the create screen.
# --------------------------------------------------------------------------- #


def _draft(c, db, *, product_id=None) -> dict:
    created = c.post(_BASE, json=_payload(product_id or _linked_product(db)))
    assert created.status_code == 201, created.text
    return created.json()


class TestApproveFromTheDraft:
    def test_a_draft_is_submitted_and_approved_in_one_call(self, client):
        c, db, _ = client
        draft = _draft(c, db)

        res = c.post(
            f"{_BASE}/{draft['id']}/submit-approve",
            json={"doc": _sheet(_placed_tag_ids(db, draft["id"]))},
        )

        assert res.status_code == 200, res.text
        row = _row(db, draft["id"])
        assert row.portal_draft_at is None
        assert row.status == "approved"
        assert row.assigned_to_id is None
        assert len(_versions(db, draft["id"])) == 1
        assert _trackers(db, draft["id"]) == []

    def test_a_bad_sheet_leaves_it_a_draft(self, client):
        c, db, _ = client
        draft = _draft(c, db)
        other = _draft(c, db)

        res = c.post(
            f"{_BASE}/{draft['id']}/submit-approve",
            json={"doc": _sheet(_placed_tag_ids(db, other["id"]))},
        )

        assert res.status_code == 422, res.text
        row = _row(db, draft["id"])
        assert row.portal_draft_at is not None
        assert _versions(db, draft["id"]) == []

    def test_an_incomplete_draft_is_refused_and_stays_a_draft(self, client):
        c, db, _ = client
        draft = _draft(c, db)
        row = _row(db, draft["id"])
        row.debtor_name = None
        db.commit()

        res = c.post(
            f"{_BASE}/{draft['id']}/submit-approve",
            json={"doc": _sheet(_placed_tag_ids(db, draft["id"]))},
        )

        assert res.status_code == 422, res.text
        assert res.json().get("code") == "SUBMIT_INCOMPLETE"
        assert _row(db, draft["id"]).portal_draft_at is not None

    def test_a_line_with_no_template_is_refused_and_stays_a_draft(self, client):
        c, db, _ = client
        draft = _draft(c, db, product_id=_seed_product(db))

        res = c.post(
            f"{_BASE}/{draft['id']}/submit-approve",
            json={"doc": _sheet(_placed_tag_ids(db, draft["id"]))},
        )

        assert res.status_code == 422, res.text
        assert res.json().get("code") == "NO_TEMPLATE"
        assert _row(db, draft["id"]).portal_draft_at is not None

    def test_an_already_submitted_request_is_refused(self, client):
        c, db, _ = client
        body = _submitted(c, db)

        res = c.post(
            f"{_BASE}/{body['id']}/submit-approve",
            json={"doc": _sheet(_placed_tag_ids(db, body["id"]))},
        )

        assert res.status_code == 409, res.text


class TestEscalateFromTheDraft:
    def test_a_draft_goes_to_the_config_assignee_with_the_note(self, client):
        from app.services import price_tag_review_service

        c, db, _ = client
        member_id = _seed_one_member_tier1_config(db)
        draft = _draft(c, db)

        res = c.post(f"{_BASE}/{draft['id']}/submit-escalate", json={"note": "Wrong photo"})

        assert res.status_code == 200, res.text
        row = _row(db, draft["id"])
        assert row.portal_draft_at is None
        assert row.status == "designing"
        assert row.assigned_to_id == member_id
        assert len(_trackers(db, draft["id"])) == 1
        notes = [x.body for x in price_tag_review_service.list_comments(db, row.id)]
        assert "Wrong photo" in notes

    def test_a_line_with_no_template_can_still_be_escalated(self, client):
        c, db, _ = client
        draft = _draft(c, db, product_id=_seed_product(db))

        res = c.post(f"{_BASE}/{draft['id']}/submit-escalate", json={"note": "No template"})

        assert res.status_code == 200, res.text
        assert _row(db, draft["id"]).status == "new"

    def test_no_note_leaves_it_a_draft(self, client):
        c, db, _ = client
        draft = _draft(c, db)

        res = c.post(f"{_BASE}/{draft['id']}/submit-escalate", json={"note": "  "})

        assert res.status_code == 422, res.text
        assert _row(db, draft["id"]).portal_draft_at is not None

    def test_someone_elses_draft_is_404(self, client):
        c, db, state = client
        draft = _draft(c, db)
        state["contact_id"] = _seed_contact_who_can_see_the_form(db)

        res = c.post(f"{_BASE}/{draft['id']}/submit-escalate", json={"note": "x"})

        assert res.status_code == 404, res.text
