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


# --------------------------------------------------------------------------- #
# R1b (security re-check): one shared rule on every route that takes attachment ids directly
#
# Helpers pinned by the coder: `entity_attachment_service.is_private_to_others(attachment, viewer_id)` for a
# row already loaded and `entity_attachment_service.exclude_private_types(query)` for a query over
# `Attachment`. These tests go through HTTP, so they do not depend on the names.
# --------------------------------------------------------------------------- #

from types import SimpleNamespace

from sqlalchemy import text

from app.models.entity_attachment import EntityAttachmentLink
from app.rbac.permission_registry import PERMISSION_REGISTRY

ALL_ATTACHMENT_SLUGS = {e["slug"] for e in PERMISSION_REGISTRY if e["slug"].startswith("resource.attachment")}


def raw_row(db, attachment_id: str):
    """The whole `attachments` row as a dict (None when it is gone), for an exact before/after comparison."""
    got = db.execute(text("SELECT * FROM attachments WHERE id = :i"), {"i": attachment_id}).mappings().first()
    return dict(got) if got else None


@pytest.fixture()
def drive(world, monkeypatch):
    """B holds every attachment slug; extra targets (a folder, a second type) exist for the move and type routes."""
    from app.models.resources import AttachmentDirectory
    from app.services.user_service import UserPermissionService

    world.p.grants.update(ALL_ATTACHMENT_SLUGS)
    monkeypatch.setattr(UserPermissionService, "get_user_permission_slugs", lambda self, uid: set(world.p.grants))
    db = world.p.factory()
    folder = AttachmentDirectory(id=str(uuid.uuid4()), name=f"ZZT folder {uuid.uuid4().hex[:6]}")
    other_type = AttachmentType(
        id=str(uuid.uuid4()), type_name=f"ZZT other {uuid.uuid4().hex[:6]}", allowed_extensions="csv", max_file_size_mb=10
    )
    db.add_all([folder, other_type])
    db.commit()
    world.folder_id = str(folder.id)
    world.other_type_id = str(other_type.id)
    return world


def _cases(w):
    from app.services.contact_access_type_service import _FALLBACK_DEFAULT_CODES

    level = _FALLBACK_DEFAULT_CODES[0]
    return {
        "bulk-attachment-type": lambda ids: ("post", f"{ATT}/bulk-attachment-type",
                                             {"attachment_ids": ids, "attachment_type_id": w.other_type_id}),
        "bulk-move": lambda ids: ("post", f"{ATT}/bulk-move", {"attachment_ids": ids, "directory_id": w.folder_id}),
        "bulk-access-levels": lambda ids: ("post", f"{ATT}/bulk-access-levels/apply",
                                           {"attachment_ids": ids, "access_levels": [level]}),
        "bulk-archive": lambda ids: ("post", f"{ATT}/bulk-archive", {"attachment_ids": ids}),
        "bulk-delete": lambda ids: ("post", f"{ATT}/bulk-delete", {"attachment_ids": ids}),
        "reorder": lambda ids: ("post", f"{ATT}/reorder", {"attachment_ids": ids}),
        "bulk-company": lambda ids: ("post", f"{ATT}/bulk-company",
                                     {"attachment_ids": ids, "company_id": w.other.company_a}),
    }


CASE_NAMES = [
    "bulk-attachment-type", "bulk-move", "bulk-access-levels", "bulk-archive", "bulk-delete", "reorder", "bulk-company",
]


@pytest.mark.parametrize("name", CASE_NAMES)
def test_r1b_the_route_works_for_an_ordinary_file(drive, name):
    """Harness check: B holds the slugs, so a refusal of the panel file below is the type's doing."""
    as_reader(drive)
    method, url, body = _cases(drive)[name]([drive.control_id])

    resp = getattr(drive.p.client, method)(url, json=body)

    assert resp.status_code < 300, f"{name}: {resp.status_code} {resp.text[:300]}"


@pytest.mark.parametrize("name", CASE_NAMES)
def test_r1b_another_users_panel_file_is_left_untouched(drive, name):
    before = raw_row(drive.p.factory(), drive.panel_id)
    as_reader(drive)
    method, url, body = _cases(drive)[name]([drive.panel_id])

    resp = getattr(drive.p.client, method)(url, json=body)

    after = raw_row(drive.p.factory(), drive.panel_id)
    assert after is not None, f"{name} deleted another user's panel file (status {resp.status_code})"
    assert after == before, {k: (before[k], after[k]) for k in before if before[k] != after[k]}
    assert drive.p.store.deleted == [], f"{name} removed stored bytes"


@pytest.mark.parametrize("name", CASE_NAMES)
def test_r1b_a_mixed_selection_changes_only_the_files_the_caller_may_touch(drive, name):
    before = raw_row(drive.p.factory(), drive.panel_id)
    as_reader(drive)
    method, url, body = _cases(drive)[name]([drive.control_id, drive.panel_id])

    getattr(drive.p.client, method)(url, json=body)

    assert raw_row(drive.p.factory(), drive.panel_id) == before


# ---- bulk download ------------------------------------------------------------


@pytest.fixture()
def queued(monkeypatch):
    """The bulk-download job is recorded, not queued."""
    from app.services import queue_service

    jobs: list = []
    monkeypatch.setattr(queue_service, "enqueue_job", lambda func, *a, **k: jobs.append((a, k)) or SimpleNamespace(id="zzt-rq"))
    return jobs


def _download_jobs(w):
    from app.models.job import ImportJob

    return w.p.factory().query(ImportJob).filter(ImportJob.job_type == "attachment_bulk_download").all()


def test_r1b_bulk_download_of_another_users_panel_file_alone_is_refused_and_queues_nothing(drive, queued):
    as_reader(drive)

    resp = drive.p.client.post(f"{ATT}/bulk-download", json={"attachment_ids": [drive.panel_id]})

    assert resp.status_code == 404, resp.text
    assert queued == [] and _download_jobs(drive) == []


def test_r1b_bulk_download_leaves_another_users_panel_file_out_of_a_mixed_job(drive, queued):
    as_reader(drive)

    resp = drive.p.client.post(
        f"{ATT}/bulk-download", json={"attachment_ids": [drive.control_id, drive.panel_id]}
    )

    assert resp.status_code in (200, 202), resp.text
    (job,) = _download_jobs(drive)
    ids = (job.job_metadata or {}).get("attachment_ids")
    assert ids == [drive.control_id], f"the job would zip {ids}"


def test_r1b_the_uploader_can_still_bulk_download_their_own_panel_file(drive, queued):
    as_uploader(drive)

    resp = drive.p.client.post(f"{ATT}/bulk-download", json={"attachment_ids": [drive.panel_id]})

    assert resp.status_code in (200, 202), resp.text
    assert (_download_jobs(drive)[0].job_metadata or {}).get("attachment_ids") == [drive.panel_id]


# ---- the external link routes -----------------------------------------------------

EXT = "/api/v1/external"
UNKNOWN_ID_PHRASES = ("invalid attachment", "attachment not found")


@pytest.fixture()
def external(drive, monkeypatch):
    """The integration's principal is B; its endpoint permission check is open."""
    from app.api.v1.external import permissions as ext_permissions
    from app.dependencies import get_external_api_user
    from app.main import app

    monkeypatch.setattr(ext_permissions, "_holds_external_permission", lambda service, user, slug: True)
    app.dependency_overrides[get_external_api_user] = lambda: {"id": drive.other.user_id, "name": "ZZT integration"}
    return drive


def _external_calls(attachment_id: str):
    code = f"ZZT-{uuid.uuid4().hex[:8]}"
    return {
        "product-attachments/link-products": (
            f"{EXT}/product-attachments/link-products",
            {"attachment_id": attachment_id, "products": ["ZZT-NO-SUCH-PRODUCT"]},
        ),
        "product-attachments": (
            f"{EXT}/product-attachments/",
            {"attachment_id": attachment_id, "product_code": "ZZT-NO-SUCH-PRODUCT"},
        ),
        "forms": (
            f"{EXT}/forms/",
            {"form": {"code": code, "name": "ZZT form", "attachment_id": attachment_id}},
        ),
        "packing-lists": (
            f"{EXT}/packing-lists/",
            {"packing_list": {"shipment_date": "2026-11-08", "attachment_id": attachment_id}, "packing_list_products": []},
        ),
        "promotions": (
            f"{EXT}/promotions/",
            {
                "start_date": "2026-11-01", "end_date": "2026-11-30", "attachment_id": attachment_id,
                "promotion_products": [{"product_code": "ZZT-NO-SUCH-PRODUCT"}],
            },
        ),
    }


EXTERNAL_ROUTES = ["product-attachments/link-products", "product-attachments", "forms", "packing-lists", "promotions"]


def _links_to(w, attachment_id: str) -> dict:
    db = w.p.factory()
    one = lambda sql: db.execute(text(sql), {"i": attachment_id}).scalar()  # noqa: E731
    return {
        "product": one("SELECT count(*) FROM product_attachments WHERE attachment_id = :i"),
        "promotion": one("SELECT count(*) FROM promotion_attachments WHERE attachment_id = :i"),
        "form": one("SELECT count(*) FROM forms WHERE attachment_id = :i"),
        "shipment": one("SELECT count(*) FROM inbound_shipments WHERE attachment_id = :i"),
        "entity": one("SELECT count(*) FROM entity_attachment_links WHERE attachment_id = :i AND entity_type NOT LIKE 'ai_assistant_%%'"),
    }


@pytest.mark.parametrize("route", EXTERNAL_ROUTES)
def test_r1b_an_external_route_still_resolves_an_ordinary_attachment_id(external, route):
    """Harness check: the same call with an ordinary file is not answered as an unknown id."""
    url, body = _external_calls(external.control_id)[route]

    resp = external.p.client.post(url, json=body)

    assert not any(p in resp.text.lower() for p in UNKNOWN_ID_PHRASES), f"{route}: {resp.status_code} {resp.text[:300]}"


#: What each route already says for an id that matches no attachment. The promotions route checks existence only
#: after matching products and an active company, which this harness cannot reach, so it is held to "no link, 4xx".
UNKNOWN_ID_MESSAGE = {
    "product-attachments/link-products": "invalid attachment_id",
    "product-attachments": "invalid attachment_id",
    "forms": "attachment not found",
    "packing-lists": "invalid attachment_id",
    "promotions": None,
}


@pytest.mark.parametrize("route", EXTERNAL_ROUTES)
def test_r1b_an_external_route_answers_a_panel_file_id_like_an_unknown_id_and_links_nothing(external, route):
    before = _links_to(external, external.panel_id)
    url, body = _external_calls(external.panel_id)[route]

    resp = external.p.client.post(url, json=body)

    assert resp.status_code in (400, 404, 422), f"{route}: {resp.status_code} {resp.text[:300]}"
    expected = UNKNOWN_ID_MESSAGE[route]
    if expected:
        assert expected in resp.text.lower(), f"{route} refused for another reason: {resp.text[:300]}"
    assert _links_to(external, external.panel_id) == before, f"{route} linked another user's panel file"


# --------------------------------------------------------------------------- #
# R1c: linking an existing file by id (link-packing-list, complaint, stock inquiry,
# purchase request and NPA links all go through link_existing_attachment)
# --------------------------------------------------------------------------- #


def _links_of(session_factory, attachment_id):
    from app.models.entity_attachment import EntityAttachmentLink

    db = session_factory()
    try:
        return db.query(EntityAttachmentLink).filter(EntityAttachmentLink.attachment_id == attachment_id).count()
    finally:
        db.close()


def test_r1c_a_stranger_cannot_link_another_users_panel_file_to_a_record(world, session_factory):
    from app.services.entity_attachment_service import EntityAttachmentService

    before = _links_of(session_factory, world.panel_id)
    db = session_factory()
    try:
        with pytest.raises(Exception) as caught:
            EntityAttachmentService(db).link_existing_attachment(
                "complaint", str(uuid.uuid4()), world.panel_id, created_by=world.other.user_id
            )
        db.rollback()
    finally:
        db.close()

    assert getattr(caught.value, "status_code", None) == 404, repr(caught.value)
    assert _links_of(session_factory, world.panel_id) == before


def test_r1c_an_ordinary_file_still_links_for_anyone(world, session_factory):
    from app.services.entity_attachment_service import EntityAttachmentService

    db = session_factory()
    try:
        link = EntityAttachmentService(db).link_existing_attachment(
            "complaint", str(uuid.uuid4()), world.control_id, created_by=world.other.user_id
        )
        assert str(link.attachment_id) == world.control_id
        db.rollback()
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Round 3 kill-test guards (green on the code as it stands; each pins a mutation the reviewer left alive)
# --------------------------------------------------------------------------- #


def _edit_type_row(p, **columns):
    db = p.factory()
    row = db.query(AttachmentType).filter(AttachmentType.code == "ai_assistant_attachment").one()
    for key, value in columns.items():
        setattr(row, key, value)
    db.commit()


def test_n20_a_type_row_raised_to_50_mb_cannot_lift_the_10_mb_ceiling(panel):
    _edit_type_row(panel, max_file_size_mb=50)
    # Many short rows, not one long line: the csv reader refuses a 10 MB field as unreadable.
    at_ceiling = b"Phone,Name\n" + b"601,Ali\n" * 1_250_000  # 10.0 MB, under the 10 MiB ceiling
    over = b"Phone,Name\n" + b"601,Ali\n" * 1_450_000  # 11.6 MB
    assert len(at_ceiling) < 10 * 1024 * 1024 < len(over)

    ok = upload(panel.client, "ok.csv", at_ceiling, "text/csv")
    assert ok.status_code == 201, f"10 MB itself must still pass: {ok.text[:200]}"
    resp = upload(panel.client, "over.csv", over, "text/csv")

    assert resp.status_code == 422, resp.text
    assert "10 MB" in resp.text


def test_n20_the_size_limit_helper_is_capped_whatever_the_row_says():
    from app.services.chatbot import panel_files

    for mb in (None, 0, -5, 1, 10, 11, 50, 500):
        limit = panel_files.size_limit_bytes(SimpleNamespace(max_file_size_mb=mb))
        assert 0 < limit <= 10 * 1024 * 1024, (mb, limit)
    assert panel_files.size_limit_bytes(SimpleNamespace(max_file_size_mb=1)) == 1024 * 1024


def test_n21_a_type_row_raised_to_20_drafts_cannot_lift_the_5_draft_ceiling(panel):
    _edit_type_row(panel, max_count_per_entity=20)
    for i in range(5):
        assert upload(panel.client, f"f{i}.csv", csv_bytes(), "text/csv").status_code == 201

    resp = upload(panel.client, "f5.csv", csv_bytes(), "text/csv")

    assert resp.status_code == 422, resp.text


def test_n03_no_viewer_is_not_open_a_panel_file_is_404_and_an_ordinary_file_is_returned(world):
    from app.models.resources import Attachment
    from app.services.error_handler import AppException
    from app.services.resources_service import AttachmentService

    db = world.p.factory()
    service = AttachmentService(db)

    with pytest.raises(AppException) as raised:
        service.get_attachment(world.panel_id)
    assert raised.value.status_code == 404
    assert str(service.get_attachment(world.control_id).id) == world.control_id
    assert str(service.get_attachment(world.panel_id, viewer_id=world.p.staff.user_id).id) == world.panel_id
    with pytest.raises(AppException):
        service.get_attachment(world.panel_id, viewer_id=world.other.user_id)


def test_n03_is_private_to_others_treats_a_missing_viewer_as_a_stranger(world):
    from app.models.resources import Attachment
    from app.services.entity_attachment_service import is_private_to_others
    from sqlalchemy.orm import joinedload

    db = world.p.factory()
    panel_att = db.query(Attachment).options(joinedload(Attachment.attachment_type)).filter(Attachment.id == world.panel_id).one()
    control = db.query(Attachment).options(joinedload(Attachment.attachment_type)).filter(Attachment.id == world.control_id).one()

    assert is_private_to_others(panel_att, None) is True
    assert is_private_to_others(panel_att, "") is True
    assert is_private_to_others(panel_att, world.other.user_id) is True
    assert is_private_to_others(panel_att, world.p.staff.user_id) is False
    assert is_private_to_others(control, None) is False
    assert is_private_to_others(control, world.other.user_id) is False


@pytest.mark.parametrize("method,suffix,body", [
    ("put", "", {"description": "hijacked"}),
    ("put", "", {"original_filename": "hijacked.csv"}),
    ("post", "/resubmit", None),
])
def test_n09_n10_update_and_resubmit_of_another_users_panel_file_are_404_and_change_nothing(drive, method, suffix, body):
    before = raw_row(drive.p.factory(), drive.panel_id)
    as_reader(drive)

    resp = getattr(drive.p.client, method)(f"{ATT}/{drive.panel_id}{suffix}", **({"json": body} if body else {}))

    assert resp.status_code == 404, f"{method.upper()} {suffix or '/{id}'}: {resp.status_code} {resp.text[:200]}"
    assert raw_row(drive.p.factory(), drive.panel_id) == before


def test_n09_update_works_for_an_ordinary_file(drive):
    """Harness check for the 404 test above: B can edit a file that is not private."""
    as_reader(drive)
    assert drive.p.client.put(f"{ATT}/{drive.control_id}", json={"description": "ok"}).status_code == 200


def test_n10_resubmit_of_an_ordinary_file_is_not_a_404(drive):
    as_reader(drive)

    assert drive.p.client.post(f"{ATT}/{drive.control_id}/resubmit").status_code != 404
