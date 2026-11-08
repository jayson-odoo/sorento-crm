"""AGENT-PANEL-COMPOSER review round 1 (red): R1, R5 (upload activity), R6, R7.

UAC: documentation/plans/chatbot/agent-panel-composer-8nov-acceptance-criteria.md, "Review round 1".

R1: a panel file reaches nobody but its uploader through the generic attachment surfaces (list, drive,
get, download, preview-url, metadata, ai-read). Every test pairs the panel file with a CONTROL file of an
ordinary type that the same reader CAN see, so a harness that hides everything cannot pass by accident.

The generic router mounts under /api/v1/resource-management/attachments.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.models.resources import Attachment, AttachmentType
from tests.chatbot._panel_files_helpers import (
    UPLOAD_URL,
    act_as,
    csv_bytes,
    panel,  # noqa: F401  (fixture)
    png_bytes,
    store,  # noqa: F401  (fixture)
    upload,
)
from tests.chatbot.test_panel_principal import (  # noqa: F401  (fixtures and helpers)
    _scope_listeners,
    grants,
    seed_staff,
    staff,
)

ATT = "/api/v1/resource-management/attachments"
ACTIVITY = "/api/v1/resource-management/upload-activity"
READER_SLUGS = (
    "resource.attachments.view",
    "resource.attachments.download",
    "resource.attachments.upload",
)


@pytest.fixture()
def world(panel, session_factory, monkeypatch):
    """User A (the uploader) has a panel file and an ordinary file; user B only reads."""
    from app.services.user_service import UserPermissionService

    panel.grants.update(READER_SLUGS)
    # The list and drive routes gate on the slug SET, not on a single-slug check.
    monkeypatch.setattr(UserPermissionService, "get_user_permission_slugs", lambda self, uid: set(panel.grants))
    made = upload(panel.client, "private.csv", csv_bytes(), "text/csv")
    assert made.status_code == 201, made.text
    panel_id = made.json()["id"]

    db = session_factory()
    kind = AttachmentType(
        id=str(uuid.uuid4()), type_name=f"ZZT control {uuid.uuid4().hex[:6]}", allowed_extensions="csv",
        max_file_size_mb=10,
    )
    db.add(kind)
    db.flush()
    key = f"zzt/control/{uuid.uuid4()}.csv"
    panel.store.objects[key] = csv_bytes()
    control = Attachment(
        attachment_type_id=kind.id, original_filename="control.csv", stored_filename="control.csv", file_path=key,
        file_size_bytes=len(csv_bytes()), storage_provider="s3", mime_type="text/csv", uploaded_by=panel.staff.user_id,
        uploader_kind="user",
    )
    db.add(control)
    db.commit()
    other = seed_staff(session_factory)
    return type(
        "World", (), {"p": panel, "panel_id": panel_id, "control_id": str(control.id), "other": other}
    )


def as_reader(w):
    act_as(w.other)


def as_uploader(w):
    act_as(w.p.staff)


# --------------------------------------------------------------------------- #
# R1: lists
# --------------------------------------------------------------------------- #


def test_r1_the_control_file_is_visible_to_the_other_reader(world):
    """Harness check: B can read an ordinary file, so a hidden panel file is hidden by the type."""
    as_reader(world)

    assert world.p.client.get(f"{ATT}/{world.control_id}").status_code == 200
    assert world.control_id in world.p.client.get(f"{ATT}/", params={"limit": 200}).text


def test_r1_the_generic_list_hides_a_panel_file_from_another_reader(world):
    as_reader(world)

    resp = world.p.client.get(f"{ATT}/", params={"limit": 200})

    assert resp.status_code == 200, resp.text
    assert world.panel_id not in resp.text


def test_r1_filtering_by_the_panel_type_code_still_hides_it(world):
    as_reader(world)

    for params in (
        {"attachment_type_code": "ai_assistant_attachment"},
        {"attachment_type_codes": ["ai_assistant_attachment"]},
    ):
        resp = world.p.client.get(f"{ATT}/", params={**params, "limit": 200})
        assert resp.status_code == 200, resp.text
        assert world.panel_id not in resp.text


def test_r1_searching_by_name_does_not_find_it(world):
    as_reader(world)

    resp = world.p.client.get(f"{ATT}/", params={"query": "private", "limit": 200})

    assert resp.status_code == 200, resp.text
    assert world.panel_id not in resp.text


def test_r1_the_files_drive_root_and_search_hide_it(world):
    as_reader(world)

    root = world.p.client.get(f"{ATT}/drive", params={"limit": 500})
    found = world.p.client.get(f"{ATT}/drive", params={"query": "private", "limit": 500})

    assert root.status_code == 200, root.text
    assert world.control_id in root.text, "harness: the ordinary file is in the drive root"
    assert world.panel_id not in root.text
    assert found.status_code == 200 and world.panel_id not in found.text


# --------------------------------------------------------------------------- #
# R1: single-file routes
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("suffix", ["", "/download", "/preview-url", "/metadata"])
def test_r1_single_file_routes_answer_404_to_another_reader(world, suffix):
    as_reader(world)

    resp = world.p.client.get(f"{ATT}/{world.panel_id}{suffix}")

    assert resp.status_code == 404, f"{suffix or '/{id}'}: {resp.status_code} {resp.text[:200]}"


@pytest.mark.parametrize("suffix", ["", "/download", "/preview-url", "/metadata"])
def test_r1_the_control_file_answers_200_on_the_same_routes(world, suffix):
    as_reader(world)

    resp = world.p.client.get(f"{ATT}/{world.control_id}{suffix}")

    assert resp.status_code == 200, f"{suffix}: {resp.status_code} {resp.text[:200]}"


def test_r1_ai_read_of_a_panel_file_by_another_reader_is_404(world):
    as_reader(world)

    resp = world.p.client.post(f"{ATT}/{world.panel_id}/ai-read")

    assert resp.status_code == 404, resp.text


def test_r1_the_uploader_can_still_get_their_own_file(world):
    as_uploader(world)

    assert world.p.client.get(f"{ATT}/{world.panel_id}").status_code == 200
    assert world.p.client.get(f"{ATT}/{world.panel_id}/metadata").status_code == 200


def test_r1_the_uploader_sees_the_same_404_for_a_panel_file_that_is_not_theirs(world):
    """B uploads their own; A (a different person) cannot read it either."""
    as_reader(world)
    mine = upload(world.p.client, "bs-own.csv", csv_bytes(), "text/csv").json()["id"]
    as_uploader(world)

    assert world.p.client.get(f"{ATT}/{mine}").status_code == 404


# --------------------------------------------------------------------------- #
# R5: the upload-activity drawer
# --------------------------------------------------------------------------- #


def test_r5_a_panel_upload_is_not_in_the_upload_activity_feed(world):
    as_uploader(world)

    resp = world.p.client.get(ACTIVITY)

    assert resp.status_code == 200, resp.text
    assert world.panel_id not in resp.text
    assert "private.csv" not in resp.text, "the draft shows in the drawer and would sit on Processing for ever"


def test_r5_the_type_row_does_not_trigger_the_n8n_webhook(world):
    db = world.p.factory()

    row = db.query(AttachmentType).filter(AttachmentType.code == "ai_assistant_attachment").one()

    assert row.triggers_n8n_webhook is False


# --------------------------------------------------------------------------- #
# R6: ceilings in code whatever the type row says
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("limit_mb", [0, 50])
def test_r6_an_edited_size_limit_cannot_lift_the_10_mb_ceiling(panel, limit_mb):
    db = panel.factory()
    row = db.query(AttachmentType).filter(AttachmentType.code == "ai_assistant_attachment").one()
    row.max_file_size_mb = limit_mb
    db.commit()
    big = b"Phone,Name\n" + b"x" * (11 * 1024 * 1024)

    resp = upload(panel.client, "big.csv", big, "text/csv")

    assert resp.status_code == 422, resp.text
    assert panel.store.objects == {}


def test_r6_a_null_count_limit_cannot_lift_the_five_draft_ceiling(panel):
    db = panel.factory()
    row = db.query(AttachmentType).filter(AttachmentType.code == "ai_assistant_attachment").one()
    row.max_count_per_entity = None
    db.commit()
    for i in range(5):
        assert upload(panel.client, f"f{i}.csv", csv_bytes(), "text/csv").status_code == 201

    resp = upload(panel.client, "f5.csv", csv_bytes(), "text/csv")

    assert resp.status_code == 422, resp.text


def test_r6_a_size_limit_below_ten_still_applies(panel):
    db = panel.factory()
    row = db.query(AttachmentType).filter(AttachmentType.code == "ai_assistant_attachment").one()
    row.max_file_size_mb = 1
    db.commit()
    two_mb = b"Phone,Name\n" + b"x" * (2 * 1024 * 1024)

    assert upload(panel.client, "two.csv", two_mb, "text/csv").status_code == 422
