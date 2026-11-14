"""SPARE-PART-ORDER-REQUEST hand-test round 2 (owner 13 Nov), red-first (Phase 2).

F1  An Order Request (inquiry_type `spare_part_request`) has its OWN number series
    `OR-YYMM-NNNN` (YYMM of creation in Asia/Kuala_Lumpur, 4 digits, per company per month,
    independent of OI-). A sales-order inquiry keeps `OI-YYMM-NNNN`. The purchasing notice
    carries the OR- number.
F2  GET /api/v1/sla-management/conversation-sla-tracking/by-source answers the requester
    (create grant only) and a view-only stage approver with the active tracker; an unrelated
    user gets 403 or nothing.
F4  The words say "order request", never "spare part request", in what the service produces.

Internal keys stay (inquiry_type, slugs, routes): not asserted here.
"""
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from ._forms_chain_support import SORENTO, user
from ._spare_part_request_support import (  # noqa: F401  fixtures are imported by name
    CREATE,
    KIND,
    OI_RAISED_NOTICE,
    SPR,
    approve,
    create,
    reload,
    role_grant,
    sent,
    staged,
    submitted,
    svc,
    world,
)
from .test_spare_part_request_mirror import NEW_VIEW, _team_approver

BY_SOURCE = "/api/v1/sla-management/conversation-sla-tracking/by-source"
OR_RE = re.compile(r"^OR-(\d{4})-(\d{4})$")
OI_RE = re.compile(r"^OI-(\d{4})-(\d{4})$")


def _yymm() -> str:
    return datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).strftime("%y%m")


# =============================================================================
# F1 - its own number series
# =============================================================================


def test_F1_a_new_request_is_numbered_OR_yymm_nnnn(staged):
    inquiry = create(staged)
    match = OR_RE.match(inquiry.inquiry_no)
    assert match, f"expected OR-YYMM-NNNN, got {inquiry.inquiry_no!r}"
    assert match.group(1) == _yymm(), "the YYMM of creation (Kuala Lumpur)"


def test_F1_the_sequence_runs_on_within_the_month(staged):
    first = create(staged)
    second = create(staged)
    n1 = int(OR_RE.match(first.inquiry_no).group(2))
    n2 = int(OR_RE.match(second.inquiry_no).group(2))
    assert n2 == n1 + 1, (first.inquiry_no, second.inquiry_no)


def test_F1_the_number_survives_submit_and_approval(staged):
    w = staged
    inquiry = create(w)
    number = inquiry.inquiry_no
    svc().submit(w.db, inquiry, w.requester)
    w.db.commit()
    assert reload(w.db, inquiry).inquiry_no == number
    inquiry = approve(w, reload(w.db, inquiry), w.stage1.tier1)
    assert inquiry.inquiry_no == number and number.startswith("OR-")


def test_F1_a_sales_order_inquiry_keeps_OI_and_neither_series_moves_the_other(staged):
    from ._oi_one_date_seed import Chain

    w = staged
    first_request = create(w)
    so_inquiry = Chain(w.db, SORENTO).inquiry
    w.db.commit()
    assert OI_RE.match(so_inquiry.inquiry_no), so_inquiry.inquiry_no
    second_request = create(w)
    n1 = int(OR_RE.match(first_request.inquiry_no).group(2))
    n2 = int(OR_RE.match(second_request.inquiry_no).group(2))
    assert n2 == n1 + 1, "an OI- number issued in between does not consume an OR- number"
    so_two = Chain(w.db, SORENTO).inquiry
    w.db.commit()
    o1 = int(OI_RE.match(so_inquiry.inquiry_no).group(2))
    o2 = int(OI_RE.match(so_two.inquiry_no).group(2))
    assert o2 == o1 + 1, "an OR- number issued in between does not consume an OI- number"


def test_F1_the_purchasing_notice_names_the_OR_number(staged, monkeypatch):
    from app.services.notification_service import NotificationService

    w = staged
    seen: list = []
    monkeypatch.setattr(
        NotificationService, "create_with_channel_preferences", lambda self, *a, **kw: seen.append(kw)
    )
    inquiry = submitted(w)
    approve(w, inquiry, w.stage1.tier1)
    notices = [kw for kw in seen if kw.get("type") == OI_RAISED_NOTICE]
    assert notices, "purchasing is told once the request is approved"
    number = reload(w.db, inquiry).inquiry_no
    assert number.startswith("OR-"), number
    for kw in notices:
        assert number in kw["title"], kw["title"]
        assert "OI-" not in kw["title"] and "OI-" not in kw["body"]


def test_F1_the_form_sla_assignment_notice_names_the_OR_number(staged, monkeypatch):
    from app.services.notification_service import NotificationService

    seen: list = []
    monkeypatch.setattr(
        NotificationService, "create_with_channel_preferences", lambda self, *a, **kw: seen.append(kw)
    )
    inquiry = submitted(staged)
    assigned = [kw for kw in seen if kw.get("type") == "form_sla" and kw.get("user_id") == staged.stage1.tier1]
    assert assigned, "the stage-1 assignee is told"
    assert assigned[0]["data"]["whatsapp_context_vars"]["entity_number"].startswith("OR-")
    assert assigned[0]["data"]["whatsapp_context_vars"]["entity_number"] == inquiry.inquiry_no


# =============================================================================
# F2 - the by-source SLA tracker, read from the request's own page
# =============================================================================


def _by_source(w, who, inquiry):
    return w.as_user(who).get(
        BY_SOURCE, params={"source_entity_type": KIND, "source_entity_id": str(inquiry.id)}
    )


def _assert_active_tracker(res, w, inquiry):
    assert res.status_code == 200, f"{res.status_code} {res.text}"
    rows = res.json()
    active = [t for t in rows if not t["is_resolved"]]
    assert len(active) == 1, rows
    tracker = active[0]
    assert tracker["source_entity_type"] == KIND
    assert tracker["source_entity_id"] == str(inquiry.id)
    assert tracker["assigned_to_id"] == w.stage1.tier1, "who acts next"
    assert tracker.get("assigned_user_name"), "the assignee is named"
    assert "resolution_due_at" in tracker, "the due moment is part of the payload"


def test_F2_the_requester_with_only_the_create_grant_reads_the_active_tracker(staged):
    inquiry = submitted(staged)
    _assert_active_tracker(_by_source(staged, staged.requester, inquiry), staged, inquiry)


def test_F2_a_view_only_stage_approver_reads_the_active_tracker(staged):
    approver = _team_approver(staged)
    inquiry = submitted(staged)
    _assert_active_tracker(_by_source(staged, approver, inquiry), staged, inquiry)


def test_F2_the_requester_reads_the_resolved_tracker_after_the_decision(staged):
    inquiry = submitted(staged)
    approve(staged, inquiry, staged.stage1.tier1)
    res = _by_source(staged, staged.requester, inquiry)
    assert res.status_code == 200, f"{res.status_code} {res.text}"
    assert res.json() and all(t["is_resolved"] for t in res.json())


def test_F2_a_user_with_no_grants_does_not_get_it(staged):
    stranger = user(staged.db, "spr no-grant stranger")
    staged.db.commit()
    inquiry = submitted(staged)
    res = _by_source(staged, stranger, inquiry)
    assert res.status_code == 403 or (res.status_code == 200 and res.json() == []), res.text


def test_F2_another_requesters_create_grant_does_not_open_this_request(staged):
    """`outsider` holds create + projects view, is not the requester and sits on no stage team."""
    inquiry = submitted(staged)
    res = _by_source(staged, staged.outsider, inquiry)
    assert res.status_code == 403 or (res.status_code == 200 and res.json() == []), res.text


def test_F2_a_new_view_holder_on_no_stage_team_does_not_get_it(staged):
    stranger = user(staged.db, "spr view-only stranger")
    role_grant(staged.db, stranger, NEW_VIEW)
    staged.db.commit()
    inquiry = submitted(staged)
    res = _by_source(staged, stranger, inquiry)
    assert res.status_code == 403 or (res.status_code == 200 and res.json() == []), res.text


# =============================================================================
# F4 - the words: order request, not spare part request
# =============================================================================


def _no_spare_part_words(text: str, where: str) -> None:
    assert "spare part request" not in text.lower(), f"{where}: {text!r}"


def test_F4_permission_registry_labels():
    from app.rbac.permission_registry import PERMISSION_REGISTRY

    by_slug = {p["slug"]: p for p in PERMISSION_REGISTRY}
    assert by_slug["procurement.spare_part_requests.create"]["name"] == "Create Order Requests"
    assert by_slug["procurement.spare_part_requests.view"]["name"] == "View Order Requests"
    for slug in ("create", "view"):
        _no_spare_part_words(
            by_slug[f"procurement.spare_part_requests.{slug}"]["description"], f"registry {slug} description"
        )


def test_F4_the_spr_0001_migration_seeds_the_same_names():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "spr_0001_spare_part_request.py"
    spec = importlib.util.spec_from_file_location("spr_0001_for_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    seeded = {slug: (name, desc) for slug, name, desc in module._PERMISSIONS}
    assert seeded["procurement.spare_part_requests.create"][0] == "Create Order Requests"
    assert seeded["procurement.spare_part_requests.view"][0] == "View Order Requests"
    for slug, (_name, desc) in seeded.items():
        _no_spare_part_words(desc, f"migration {slug} description")


def test_F4_the_not_found_text(staged):
    import uuid

    res = staged.as_user(staged.requester).get(f"{SPR}/{uuid.uuid4()}")
    assert res.status_code == 404, res.text
    _no_spare_part_words(res.text, "404 body")
    assert "order request" in res.text.lower(), res.text


def test_F4_submitting_with_no_approval_level_says_order_request(world):
    inquiry = create(world)
    with pytest.raises(Exception) as excinfo:
        svc().submit(world.db, inquiry, world.requester)
    text = str(getattr(excinfo.value, "message", None) or excinfo.value)
    _no_spare_part_words(text, "no-stage error")
    assert "order request" in text.lower(), text


def test_F4_the_purchasing_notice_text(staged, monkeypatch):
    from app.services.notification_service import NotificationService

    w = staged
    seen: list = []
    monkeypatch.setattr(
        NotificationService, "create_with_channel_preferences", lambda self, *a, **kw: seen.append(kw)
    )
    approve(w, submitted(w), w.stage1.tier1)
    notices = [kw for kw in seen if kw.get("type") == OI_RAISED_NOTICE]
    assert notices, "purchasing is told"
    for kw in notices:
        _no_spare_part_words(kw["title"], "notice title")
        _no_spare_part_words(kw["body"], "notice body")
        assert "order request" in (kw["title"] + " " + kw["body"]).lower(), (kw["title"], kw["body"])


def test_F4_history_and_audit_texts_for_create_submit_approve_reject(staged):
    from app.models.audit import AuditLog

    w = staged
    inquiry = submitted(w)
    approve(w, inquiry, w.stage1.tier1)
    rejected = submitted(w)
    svc().reject(w.db, rejected, w.stage1.tier1, reason="too dear")
    w.db.commit()
    texts = [
        a.description or ""
        for a in w.db.query(AuditLog).filter(AuditLog.entity_type == "project_order_inquiries").all()
    ]
    assert len(texts) >= 6, texts
    for text in texts:
        _no_spare_part_words(text, "audit description")
