"""Export requests: the render context is decided at enqueue, never later.

Two failures this exists to prevent, both of which produce a WRONG file rather
than an error anyone would notice:

  * A worker with no snapshot has no answer to "who is this for", and the only
    fallback available to it is a system principal - which is a staff principal.
    It would print internal prices into a document a consumer asked for.
  * A page republished while its PDF is queued would change what that PDF
    contains, so the file someone downloads is not the thing they exported.
"""
from __future__ import annotations

import os
import uuid

import pytest

from app.models.dealer_kit import ExportRequest
from app.models.download import DownloadStatus
from app.services.dealer_kit import export_service, page_service
from app.services.error_handler import AppException
from tests._pg_fixture import pg_session, unique_code

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)

_USER = "00000000-0000-4000-8000-00000000e001"


def _published_page(db, marker="v1"):
    page = page_service.create_page(
        db, name=f"ZZT {unique_code('export')}", slug=unique_code("zzt-export").lower(), user_id=None
    )
    version = page_service.save_version(
        db, page.id, doc={"sections": [], "marker": marker}, commit_message=marker, user_id=None
    )
    page_service.move_label(db, page.id, "published", version_id=version.id, user_id=None)
    return page, version


# --------------------------------------------------------------------------
# What gets snapshotted
# --------------------------------------------------------------------------


def test_requesting_an_export_queues_a_download_and_snapshots_the_viewer():
    with pg_session() as db:
        page, version = _published_page(db)

        download = export_service.request_export(
            db, page_id=page.id, audience="dealer", show_invoice_price=False, user_id=_USER
        )

        assert download.status == DownloadStatus.PENDING.value
        assert download.kind == export_service.KIND
        assert download.filename.endswith(f"-v{version.version}.pdf")

        request = export_service.get_request(db, download.id)
        assert request.audience == "dealer"
        assert request.page_version_id == version.id


def test_the_version_is_pinned_so_republishing_cannot_change_the_file():
    with pg_session() as db:
        page, first = _published_page(db, marker="v1")
        download = export_service.request_export(db, page_id=page.id, user_id=_USER)

        # Someone publishes again while the export sits in the queue.
        second = page_service.save_version(
            db, page.id, doc={"sections": [], "marker": "v2"}, commit_message="v2", user_id=None
        )
        page_service.move_label(db, page.id, "published", version_id=second.id, user_id=None)

        inputs = export_service.render_inputs(db, download.id)
        assert inputs["version_id"] == first.id
        assert inputs["doc"]["marker"] == "v1"


def test_an_explicit_version_can_be_exported_for_review():
    with pg_session() as db:
        page, published = _published_page(db, marker="live")
        draft = page_service.save_version(
            db, page.id, doc={"sections": [], "marker": "draft"}, commit_message="draft", user_id=None
        )

        download = export_service.request_export(
            db, page_id=page.id, user_id=_USER, version_id=draft.id
        )
        assert export_service.render_inputs(db, download.id)["doc"]["marker"] == "draft"


def test_exporting_defaults_to_the_published_version_not_the_newest():
    with pg_session() as db:
        page, published = _published_page(db, marker="live")
        page_service.save_version(
            db, page.id, doc={"sections": [], "marker": "unpublished"}, commit_message="wip", user_id=None
        )

        download = export_service.request_export(db, page_id=page.id, user_id=_USER)
        # "Export this catalogue" means the one people can see.
        assert export_service.render_inputs(db, download.id)["doc"]["marker"] == "live"


# --------------------------------------------------------------------------
# The viewer the worker must use
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "audience,toggle,expect_invoice",
    [
        ("staff", True, True),
        ("staff", False, False),
        ("dealer", True, False),
        ("consumer", True, False),
    ],
)
def test_the_snapshot_decides_whether_invoice_price_renders(audience, toggle, expect_invoice):
    with pg_session() as db:
        page, _ = _published_page(db)
        download = export_service.request_export(
            db,
            page_id=page.id,
            audience=audience,
            show_invoice_price=toggle,
            user_id=_USER,
        )

        viewer = export_service.render_inputs(db, download.id)["viewer"]
        # Toggle AND entitlement, exactly as an on-screen render.
        assert viewer.invoice_price_visible is expect_invoice


def test_a_dealer_export_and_a_staff_export_of_one_page_differ():
    with pg_session() as db:
        page, _ = _published_page(db)

        staff = export_service.request_export(
            db, page_id=page.id, audience="staff", show_invoice_price=True, user_id=_USER
        )
        dealer = export_service.request_export(
            db, page_id=page.id, audience="dealer", show_invoice_price=True, user_id=_USER
        )

        assert export_service.render_inputs(db, staff.id)["viewer"].invoice_price_visible is True
        assert export_service.render_inputs(db, dealer.id)["viewer"].invoice_price_visible is False


def test_a_download_without_a_snapshot_refuses_to_render():
    """The gate item: the worker never falls back to a system principal."""
    from app.models.download import UserDownload

    with pg_session() as db:
        orphan = UserDownload(
            user_id=_USER,
            kind=export_service.KIND,
            status=DownloadStatus.PENDING.value,
            filename="zzt-orphan.pdf",
        )
        db.add(orphan)
        db.flush()

        with pytest.raises(AppException) as caught:
            export_service.render_inputs(db, orphan.id)
        assert caught.value.status_code == 404
        assert "guessing" in str(caught.value.detail)


# --------------------------------------------------------------------------
# Refusals
# --------------------------------------------------------------------------


def test_an_unpublished_page_cannot_be_exported_without_naming_a_version():
    with pg_session() as db:
        page = page_service.create_page(
            db, name="ZZT never live", slug=unique_code("zzt-nolive").lower(), user_id=None
        )
        page_service.save_version(
            db, page.id, doc={"sections": []}, commit_message=None, user_id=None
        )

        with pytest.raises(AppException) as caught:
            export_service.request_export(db, page_id=page.id, user_id=_USER)
        assert caught.value.status_code == 409


def test_an_unknown_audience_is_refused():
    with pg_session() as db:
        page, _ = _published_page(db)
        with pytest.raises(AppException) as caught:
            export_service.request_export(
                db, page_id=page.id, audience="everyone", user_id=_USER
            )
        assert caught.value.status_code == 422


def test_an_export_needs_a_requesting_user():
    with pg_session() as db:
        page, _ = _published_page(db)
        with pytest.raises(AppException):
            export_service.request_export(db, page_id=page.id, user_id="")


def test_a_version_from_another_page_cannot_be_exported():
    with pg_session() as db:
        page_a, _ = _published_page(db)
        _page_b, version_b = _published_page(db)

        with pytest.raises(AppException) as caught:
            export_service.request_export(
                db, page_id=page_a.id, user_id=_USER, version_id=version_b.id
            )
        assert caught.value.status_code == 404


def test_one_download_carries_at_most_one_snapshot():
    with pg_session() as db:
        page, version = _published_page(db)
        download = export_service.request_export(db, page_id=page.id, user_id=_USER)

        # Two snapshots would be two answers to "who is this for", and nothing
        # could say which the worker should believe.
        db.add(
            ExportRequest(
                download_id=download.id,
                page_id=page.id,
                page_version_id=version.id,
                audience="consumer",
            )
        )
        with pytest.raises(Exception):
            db.flush()


def test_an_unknown_page_is_404():
    with pg_session() as db:
        with pytest.raises(AppException) as caught:
            export_service.request_export(db, page_id=str(uuid.uuid4()), user_id=_USER)
        assert caught.value.status_code == 404
