"""When a flyer banner dies, and when it must not.

Written before the fix.

S7.5 made every flyer upload put each page's banner in the asset library: a
``dealer_kit.asset`` row, a ``public.attachments`` row and real bytes in object
storage. Nothing undid any of it. Deleting the reading removed the reading and
left all three behind forever, and "forever" was literal - ``asset.attachment_id``
is ``ON DELETE RESTRICT``, so the attachment could not be deleted while the asset
row lived, and nothing deleted the asset. The bucket proved it: 1,356 objects
under ``dealer_kit_asset/`` with no row anywhere pointing at them.

The obvious fix is the wrong one. A banner is a section BACKGROUND in every
brochure seeded from that reading, and a reading is a working artefact people
tidy away - so "delete the reading, delete its assets" takes the artwork out of a
published catalogue somebody approved. A reader losing a background they can
currently see is far worse than an orphan row.

So the rule under test here is:

    **An asset dies when the last thing that names it dies, and not before.**

Naming it means a ``page_version.doc`` binding it as ``style.backgroundAssetId``
(ANY version - published, staging, or an unlabelled draft, because rollback is a
label move and an older version has to keep rendering), or a
``flyer_reading.reading_json`` still claiming it as a page banner. That makes the
delete order-independent: brochure first then reading, or reading first then
brochure, and either way the last one out purges what nothing else holds.

The BYTES go with the row, deliberately. Once the asset row is gone the object is
unreachable by every path this product has - nothing can find it, sign it, or
delete it - so keeping it buys no recovery, only a bucket nobody can audit and a
bill nobody can explain. The purge is best-effort and happens AFTER the commit:
a bucket outage must not block a delete the user asked for, and bytes must never
die for a transaction that then rolls back.

Postgres only, on a blank scratch schema, with storage faked in-process. Every
row is ZZT-scoped and nothing here touches the real bucket.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from tests._fake_storage import patch_storage
from tests._pg_fixture import blank_session, unique_code

FIXTURE_PDF = Path(__file__).parent / "fixtures" / "dealer_kit" / "flyer_sample.pdf"

# The fixture's three pages: the cover carries a full-bleed background, the
# bathtub spread's header is a vector rectangle, the water closet spread has a
# real image band. So two of the three seed a background.
PAGES_WITH_A_BANNER = 2

# One original plus one thumbnail per banner. The thumbnail is a separate object
# with its own key, which is exactly how half the bucket litter got there.
OBJECTS_PER_BANNER = 2

_SORENTO = "00000000-0000-0000-0000-000000000001"
_ADMIN_ID = "5c2e7b81-4a39-5f60-b8d2-1e7a4c9b3d05"
_ADMIN_ROLE = "8d4b6f29-3c17-5a82-9e50-2b7d1f4a6c93"


def _seed_roles(db) -> None:
    from app.models.user import User, UserRole, UserRoleAssignment

    db.add(
        UserRole(
            id=_ADMIN_ROLE,
            slug="superadmin",
            name="Superadmin",
            description="",
            is_protected=True,
            is_default=False,
        )
    )
    db.add(
        User(id=_ADMIN_ID, email="zzt-life-admin@test.com", name="Life Admin", status="ACTIVE")
    )
    db.flush()
    db.add(UserRoleAssignment(user_id=_ADMIN_ID, role_id=_ADMIN_ROLE))
    db.commit()


@pytest.fixture
def api(monkeypatch):
    """The route stack, a superadmin principal, and storage that keeps its bytes."""
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        _seed_roles(db)
        storage = patch_storage(monkeypatch)

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db

        async def _override_scope():
            scope = frozenset({_SORENTO})
            set_company_scope(db, scope)
            return scope

        app.dependency_overrides[apply_company_scope] = _override_scope

        principal = {"id": _ADMIN_ID, "email": "zzt-life-admin@test.com"}
        app.dependency_overrides[get_current_user] = lambda: principal
        app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        yield db, storage

        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Rows and objects
# --------------------------------------------------------------------------- #
def _upload(client: TestClient, *, filename: str = "zzt-flyer.pdf") -> str:
    res = client.post(
        "/api/v1/dealer-kit/flyer-readings",
        files={"file": (filename, FIXTURE_PDF.read_bytes(), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _seed(client: TestClient, reading_id: str) -> dict:
    res = client.post(
        f"/api/v1/dealer-kit/flyer-readings/{reading_id}/seed",
        json={"name": unique_code("ZZT Brochure"), "slug": unique_code("zzt-bro").lower()},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _delete_reading(client: TestClient, reading_id: str):
    return client.delete(f"/api/v1/dealer-kit/flyer-readings/{reading_id}")


def _delete_page(client: TestClient, page_id: str):
    return client.delete(f"/api/v1/dealer-kit/pages/{page_id}")


def _assets(db) -> list:
    from app.models.dealer_kit import Asset

    return db.query(Asset).all()


def _asset_ids(db) -> set[str]:
    return {asset.id for asset in _assets(db)}


def _attachments(db, attachment_ids) -> list:
    from app.models.resources import Attachment
    from app.services.dealer_kit import asset_service

    ids = set(attachment_ids)
    if not ids:
        return []
    return (
        db.query(Attachment)
        .filter(Attachment.entity_type == asset_service.STORAGE_ENTITY_TYPE)
        .filter(Attachment.id.in_(ids))
        .all()
    )


def _attachment_ids_of(db, asset_ids) -> set[str]:
    from app.models.dealer_kit import Asset

    ids = set(asset_ids)
    if not ids:
        return set()
    rows = db.query(Asset.attachment_id).filter(Asset.id.in_(ids)).all()
    return {row[0] for row in rows}


def _attachment_of(db, asset_id: str) -> str:
    from app.models.dealer_kit import Asset

    return db.query(Asset.attachment_id).filter(Asset.id == asset_id).scalar()


def _keys_under(storage, attachment_id: str) -> set[str]:
    """Every object stored for one attachment: the original AND its thumbnail.

    Keyed by ATTACHMENT id, not asset id - the uuid-segregated key scheme is
    ``{type}/{attachment_id}/{filename}``, so an assertion written against the
    asset id would match nothing and pass for the wrong reason.
    """
    return {
        key for key in storage.objects if key.startswith(f"dealer_kit_asset/{attachment_id}/")
    }


def _objects(storage) -> set[str]:
    from app.services.dealer_kit import asset_service

    return {
        key
        for key in storage.objects
        if key.startswith(f"{asset_service.STORAGE_ENTITY_TYPE}/")
    }


def _banner_ids(db, reading_id: str) -> set[str]:
    """The asset ids a stored reading claims as page banners."""
    from app.models.dealer_kit import FlyerReadingRecord

    row = (
        db.query(FlyerReadingRecord).filter(FlyerReadingRecord.id == reading_id).one()
    )
    return {
        page["banner_asset_id"]
        for page in (row.reading_json or {}).get("pages", [])
        if page.get("banner_asset_id")
    }


def _publish(db, page_id: str) -> None:
    from app.models.dealer_kit import PageLabel, PageVersion

    version = (
        db.query(PageVersion)
        .filter(PageVersion.page_id == page_id)
        .order_by(PageVersion.version.desc())
        .first()
    )
    db.add(PageLabel(page_id=page_id, label="published", version_id=version.id))
    db.commit()


def _bound_backgrounds(db, page_id: str) -> set[str]:
    from app.models.dealer_kit import PageVersion
    from app.services.dealer_kit import asset_service

    rows = db.query(PageVersion).filter(PageVersion.page_id == page_id).all()
    return {value for row in rows for value in asset_service.background_asset_ids(row.doc)}


# --------------------------------------------------------------------------- #
# Nothing else names it: it goes, bytes included
# --------------------------------------------------------------------------- #
class TestAnUnusedBannerGoesWithItsReading:
    def test_deleting_a_reading_takes_its_unreferenced_banners_with_it(self, api) -> None:
        """The defect, in one call.

        A flyer read and never seeded leaves two assets, two attachments and
        four objects. Deleting the reading used to leave every one of them, with
        no route that could ever remove them afterwards.
        """
        db, storage = api

        with TestClient(app) as client:
            reading_id = _upload(client)

            assert len(_assets(db)) == PAGES_WITH_A_BANNER
            banners = _banner_ids(db, reading_id)
            attachment_ids = _attachment_ids_of(db, banners)
            assert len(attachment_ids) == PAGES_WITH_A_BANNER

            removed = _delete_reading(client, reading_id)

        assert removed.status_code == 204, removed.text
        assert _assets(db) == []
        assert _attachments(db, attachment_ids) == []

    def test_the_bytes_go_too_thumbnail_included(self, api) -> None:
        """An object with no row is unreachable by every path this product has.

        Nothing can find it, sign it or delete it, so keeping it buys no
        recovery - only storage cost and a bucket nobody can audit. The
        thumbnail is a SEPARATE object with its own key, and forgetting it is
        how half the litter got there.
        """
        db, storage = api

        with TestClient(app) as client:
            reading_id = _upload(client)
            assert len(_objects(storage)) == PAGES_WITH_A_BANNER * OBJECTS_PER_BANNER
            assert any(key.endswith(".thumb.jpg") for key in _objects(storage))

            _delete_reading(client, reading_id)

        assert _objects(storage) == set()

    def test_a_reading_whose_banners_never_stored_deletes_cleanly(
        self, api, monkeypatch
    ) -> None:
        """No assets to sweep is a normal state, not an edge case to crash on.

        A storage outage during the upload is explicitly survivable, so the
        delete has to survive its aftermath too.
        """
        db, storage = api

        def _explode(**_kwargs):
            raise RuntimeError("bucket unreachable")

        monkeypatch.setattr(storage, "upload_file", _explode)

        with TestClient(app) as client:
            reading_id = _upload(client)
            assert _assets(db) == []
            removed = _delete_reading(client, reading_id)

        assert removed.status_code == 204, removed.text


# --------------------------------------------------------------------------- #
# Something still shows it: it stays
# --------------------------------------------------------------------------- #
class TestABoundBannerSurvives:
    def test_a_background_a_published_catalogue_shows_survives_its_reading(
        self, api
    ) -> None:
        """The reason this is not a cascade delete.

        Somebody tidying up the flyer list must not blank the artwork on a
        brochure that is live in front of every dealer. Asserted through the
        PUBLIC payload, because that is where the loss would be visible.
        """
        db, storage = api

        with TestClient(app) as client:
            reading_id = _upload(client)
            result = _seed(client, reading_id)
        _publish(db, result["pageId"])

        with TestClient(app) as client:
            before = client.get(f"/api/v1/public/c/SRT/{result['slug']}").json()
            assert len(before["assets"]) == PAGES_WITH_A_BANNER

            assert _delete_reading(client, reading_id).status_code == 204

            after = client.get(f"/api/v1/public/c/SRT/{result['slug']}")

        assert after.status_code == 200, after.text
        assert after.json()["assets"] == before["assets"]
        assert len(_assets(db)) == PAGES_WITH_A_BANNER
        assert len(_objects(storage)) == PAGES_WITH_A_BANNER * OBJECTS_PER_BANNER

    def test_a_background_only_an_unpublished_draft_binds_survives_too(self, api) -> None:
        """A draft is a version no label points at, and it still has to render.

        The reviewer opening that draft in the builder is the person this whole
        slice exists for. Rollback is a label move, so an unlabelled version is
        one click from being what readers see - "in use" therefore means bound
        by ANY version, never only by the published one.
        """
        db, storage = api

        with TestClient(app) as client:
            reading_id = _upload(client)
            result = _seed(client, reading_id)  # no label: a draft by construction

            assert _delete_reading(client, reading_id).status_code == 204

            detail = client.get(f"/api/v1/dealer-kit/pages/{result['pageId']}")

        assert detail.status_code == 200, detail.text
        assert len(detail.json()["assets"]) == PAGES_WITH_A_BANNER
        assert len(_assets(db)) == PAGES_WITH_A_BANNER

    def test_only_the_ones_nothing_binds_are_swept(self, api) -> None:
        """Partial, not all-or-nothing.

        Refusing the whole delete because one banner is in use would mean no
        reading that was ever seeded could be deleted at all, and the flyer list
        would fill up with rows nobody may remove. So the delete takes exactly
        what nothing names and leaves the rest.
        """
        db, storage = api

        with TestClient(app) as client:
            reading_id = _upload(client)
            banners = sorted(_banner_ids(db, reading_id))
            assert len(banners) == PAGES_WITH_A_BANNER
            kept, doomed = banners[0], banners[1]
            # Captured now: the row that names the doomed object is about to go.
            kept_keys = _keys_under(storage, _attachment_of(db, kept))
            doomed_keys = _keys_under(storage, _attachment_of(db, doomed))
            assert kept_keys and doomed_keys

            created = client.post(
                "/api/v1/dealer-kit/pages",
                json={
                    "name": unique_code("ZZT Half"),
                    "slug": unique_code("zzt-half").lower(),
                },
            )
            assert created.status_code == 201, created.text
            page_id = created.json()["id"]

            # A document binding ONE of the two, by hand: seeding would bind both.
            saved = client.post(
                f"/api/v1/dealer-kit/pages/{page_id}/versions",
                json={
                    "doc": {
                        "sections": [
                            {
                                "id": "sec-zzt",
                                "name": "ZZT",
                                "style": {"backgroundAssetId": kept},
                                "blocks": [],
                                "layouts": {},
                            }
                        ]
                    }
                },
            )
            assert saved.status_code == 201, saved.text

            assert _delete_reading(client, reading_id).status_code == 204

        assert _asset_ids(db) == {kept}
        assert _objects(storage) == kept_keys
        assert not (_objects(storage) & doomed_keys), "the unbound banner's bytes should be gone"


# --------------------------------------------------------------------------- #
# Either order leaves nothing behind
# --------------------------------------------------------------------------- #
class TestOrderIndependence:
    def test_brochure_first_then_reading_leaves_nothing(self, api) -> None:
        """The order the e2e specs tear down in.

        Deleting the brochure releases the binding; the reading still claims the
        banners, so they survive that step and go with the reading.
        """
        db, storage = api

        with TestClient(app) as client:
            reading_id = _upload(client)
            result = _seed(client, reading_id)

            assert _delete_page(client, result["pageId"]).status_code == 204
            assert len(_assets(db)) == PAGES_WITH_A_BANNER, (
                "the reading still names them, so the page delete must not take them"
            )

            assert _delete_reading(client, reading_id).status_code == 204

        assert _assets(db) == []
        assert _objects(storage) == set()

    def test_reading_first_then_brochure_leaves_nothing_either(self, api) -> None:
        """The other order, which is the one that used to strand them forever.

        Deleting the reading keeps a bound banner alive, correctly - and then
        nothing was left that could ever remove it, because the reading was the
        only thing that knew it existed. Deleting the last brochure that binds
        it has to finish the job.
        """
        db, storage = api

        with TestClient(app) as client:
            reading_id = _upload(client)
            result = _seed(client, reading_id)

            assert _delete_reading(client, reading_id).status_code == 204
            assert len(_assets(db)) == PAGES_WITH_A_BANNER

            assert _delete_page(client, result["pageId"]).status_code == 204

        assert _assets(db) == []
        assert _objects(storage) == set()

    def test_a_second_brochure_still_showing_it_keeps_it(self, api) -> None:
        """One flyer legitimately seeds two brochures, a dealer and a consumer one.

        Deleting one of them must not blank the other.
        """
        db, storage = api

        with TestClient(app) as client:
            reading_id = _upload(client)
            first = _seed(client, reading_id)
            second = _seed(client, reading_id)

            assert _delete_reading(client, reading_id).status_code == 204
            assert _delete_page(client, first["pageId"]).status_code == 204

        assert len(_assets(db)) == PAGES_WITH_A_BANNER
        assert _bound_backgrounds(db, second["pageId"]) == _asset_ids(db)


# --------------------------------------------------------------------------- #
# The constraint that made the litter unremovable
# --------------------------------------------------------------------------- #
class TestTheRestrictInteraction:
    def test_an_attachment_cannot_be_deleted_while_its_asset_lives(self, api) -> None:
        """``asset.attachment_id`` is ON DELETE RESTRICT, and stays that way.

        That is why the orphans could not be cleaned up through the ordinary
        attachment route: the delete was refused while the asset row lived, and
        nothing deleted the asset. The constraint is RIGHT - an attachment
        vanishing under a live asset is a library row pointing at nothing - so
        the fix is the ORDER, and this pins the constraint the order exists for.
        """
        from sqlalchemy.exc import IntegrityError

        from app.models.resources import Attachment

        db, _storage = api

        with TestClient(app) as client:
            reading_id = _upload(client)

        attachment_id = next(iter(_attachment_ids_of(db, _banner_ids(db, reading_id))))
        attachment = db.query(Attachment).filter(Attachment.id == attachment_id).one()

        with pytest.raises(IntegrityError):
            # A savepoint, so the aborted transaction does not take the rest of
            # the test with it.
            with db.begin_nested():
                db.delete(attachment)
                db.flush()

    def test_the_sweep_deletes_the_asset_before_the_attachment(self, api) -> None:
        """The same two rows, in the order the database accepts.

        A sweep that deleted them the other way round would raise, roll back the
        delete, and hand the caller a 500 for a reading that is still there.
        """
        db, storage = api

        with TestClient(app) as client:
            reading_id = _upload(client)
            attachment_ids = _attachment_ids_of(db, _banner_ids(db, reading_id))

            removed = _delete_reading(client, reading_id)

        assert removed.status_code == 204, removed.text
        assert _assets(db) == []
        assert _attachments(db, attachment_ids) == []


# --------------------------------------------------------------------------- #
# The bytes are best-effort, and they go last
# --------------------------------------------------------------------------- #
class TestTheBytesAreBestEffort:
    def test_a_bucket_that_refuses_still_loses_the_rows(self, api) -> None:
        """A storage outage costs an orphan object, never the delete.

        The user asked for the row to go. Failing their request because a bucket
        blinked leaves them with a reading they cannot remove and no way to tell
        why - and the retry hits the same wall.
        """
        db, storage = api
        storage.deleting_fails = True

        with TestClient(app) as client:
            reading_id = _upload(client)
            removed = _delete_reading(client, reading_id)

        assert removed.status_code == 204, removed.text
        assert _assets(db) == []

    def test_a_kept_asset_keeps_its_bytes(self, api) -> None:
        """The purge follows the rows exactly: nothing is deleted speculatively."""
        db, storage = api

        with TestClient(app) as client:
            reading_id = _upload(client)
            _seed(client, reading_id)
            before = _objects(storage)

            _delete_reading(client, reading_id)

        assert _objects(storage) == before

    def test_the_bytes_are_purged_after_the_rows_are_committed(
        self, api, monkeypatch
    ) -> None:
        """Never before.

        Deleting the objects first and then failing to commit would leave live
        asset rows pointing at nothing: an absent background, which the renderer
        has a designed state for, but a lie about a library the rows say is
        intact. Bytes are the one part of this that no rollback can undo, so
        they go last.
        """
        from app.services.dealer_kit import asset_service

        db, storage = api

        with TestClient(app) as client:
            reading_id = _upload(client)
            assert _banner_ids(db, reading_id)

            order: list[str] = []
            real_commit = db.commit
            real_purge = asset_service.purge_objects

            def _commit():
                order.append("commit")
                return real_commit()

            def _purge(objects):
                order.append("purge")
                return real_purge(objects)

            monkeypatch.setattr(db, "commit", _commit)
            monkeypatch.setattr(asset_service, "purge_objects", _purge)

            assert _delete_reading(client, reading_id).status_code == 204

        assert order.index("commit") < order.index("purge"), order
        assert _objects(storage) == set()


# --------------------------------------------------------------------------- #
# Company scope
# --------------------------------------------------------------------------- #
def test_the_sweep_only_ever_touches_the_readings_own_banners(api) -> None:
    """Two readings, one delete. The other one's artwork is untouched."""
    db, storage = api

    with TestClient(app) as client:
        first = _upload(client, filename="zzt-first.pdf")
        second = _upload(client, filename="zzt-second.pdf")

        kept = _banner_ids(db, second)
        assert len(_assets(db)) == PAGES_WITH_A_BANNER * 2

        assert _delete_reading(client, first).status_code == 204

    assert _asset_ids(db) == kept
    assert len(_objects(storage)) == PAGES_WITH_A_BANNER * OBJECTS_PER_BANNER
