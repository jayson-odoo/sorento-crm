"""Dealer Kit page lifecycle — immutable versions, movable labels.

Postgres only, per the hard rule: `schema="dealer_kit"` models cannot be created
on sqlite at all, so a sqlite run here would prove nothing.

Every row this file creates is named with the reserved ``ZZT`` prefix and every
session is rolled back, because the local database holds real records. Nothing
here counts rows globally and nothing here deletes by anything other than the
ids it created.
"""
from __future__ import annotations

import os

import pytest

from app.models.dealer_kit import Page, PageLabel, PageVersion
from app.services.dealer_kit import page_service as svc
from app.services.error_handler import AppException
from tests._pg_fixture import pg_session, unique_code

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)


def _page(db, slug_stem="page") -> Page:
    slug = unique_code(slug_stem).lower()
    return svc.create_page(db, name=f"ZZT {slug}", slug=slug, user_id=None)


def _doc(marker: str) -> dict:
    return {"sections": [{"id": "s1", "name": marker, "blocks": []}], "printProfile": None}


class TestVersioning:
    def test_first_save_is_version_one(self):
        with pg_session() as db:
            page = _page(db)
            v = svc.save_version(db, page.id, doc=_doc("a"), commit_message=None, user_id=None)
            assert v.version == 1

    def test_version_increments_per_page_not_globally(self):
        with pg_session() as db:
            first, second = _page(db, "one"), _page(db, "two")

            svc.save_version(db, first.id, doc=_doc("a"), commit_message=None, user_id=None)
            svc.save_version(db, first.id, doc=_doc("b"), commit_message=None, user_id=None)
            fresh = svc.save_version(db, second.id, doc=_doc("c"), commit_message=None, user_id=None)

            # A global sequence would make this 3, and "version 3" would stop
            # meaning "the third edit of this page".
            assert fresh.version == 1

    def test_saving_never_rewrites_an_existing_version(self):
        with pg_session() as db:
            page = _page(db)
            first = svc.save_version(db, page.id, doc=_doc("original"), commit_message=None, user_id=None)
            first_id = first.id

            svc.save_version(db, page.id, doc=_doc("replacement"), commit_message=None, user_id=None)

            kept = db.query(PageVersion).filter(PageVersion.id == first_id).one()
            assert kept.doc["sections"][0]["name"] == "original"
            assert db.query(PageVersion).filter(PageVersion.page_id == page.id).count() == 2

    def test_versions_are_listed_newest_first(self):
        with pg_session() as db:
            page = _page(db)
            for marker in ("a", "b", "c"):
                svc.save_version(db, page.id, doc=_doc(marker), commit_message=None, user_id=None)

            assert [v.version for v in svc.list_versions(db, page.id)] == [3, 2, 1]

    def test_saving_to_an_unknown_page_is_404(self):
        with pg_session() as db:
            with pytest.raises(AppException) as err:
                svc.save_version(
                    db, "00000000-0000-0000-0000-0000000000ff",
                    doc=_doc("x"), commit_message=None, user_id=None,
                )
            assert err.value.status_code == 404


class TestLabels:
    def test_publishing_moves_the_label_without_touching_versions(self):
        with pg_session() as db:
            page = _page(db)
            v1 = svc.save_version(db, page.id, doc=_doc("a"), commit_message=None, user_id=None)
            before = db.query(PageVersion).filter(PageVersion.id == v1.id).one().doc

            svc.move_label(db, page.id, svc.PUBLISHED, version_id=v1.id, user_id=None)

            after = db.query(PageVersion).filter(PageVersion.id == v1.id).one().doc
            assert after == before
            label = db.query(PageLabel).filter(
                PageLabel.page_id == page.id, PageLabel.label == svc.PUBLISHED
            ).one()
            assert label.version_id == v1.id

    def test_rollback_is_the_same_move_aimed_at_an_older_version(self):
        with pg_session() as db:
            page = _page(db)
            v1 = svc.save_version(db, page.id, doc=_doc("old"), commit_message=None, user_id=None)
            v2 = svc.save_version(db, page.id, doc=_doc("new"), commit_message=None, user_id=None)

            svc.move_label(db, page.id, svc.PUBLISHED, version_id=v2.id, user_id=None)
            assert svc.published_doc(db, page.slug)["version"] == 2

            svc.move_label(db, page.id, svc.PUBLISHED, version_id=v1.id, user_id=None)

            live = svc.published_doc(db, page.slug)
            assert live["version"] == 1
            assert live["doc"]["sections"][0]["name"] == "old"
            # Both versions survive a rollback - that is what makes it cheap.
            assert db.query(PageVersion).filter(PageVersion.page_id == page.id).count() == 2

    def test_moving_a_label_twice_keeps_exactly_one_row(self):
        with pg_session() as db:
            page = _page(db)
            v1 = svc.save_version(db, page.id, doc=_doc("a"), commit_message=None, user_id=None)
            v2 = svc.save_version(db, page.id, doc=_doc("b"), commit_message=None, user_id=None)

            svc.move_label(db, page.id, svc.PUBLISHED, version_id=v1.id, user_id=None)
            svc.move_label(db, page.id, svc.PUBLISHED, version_id=v2.id, user_id=None)

            rows = db.query(PageLabel).filter(
                PageLabel.page_id == page.id, PageLabel.label == svc.PUBLISHED
            ).all()
            assert len(rows) == 1
            assert rows[0].version_id == v2.id

    def test_published_and_staging_coexist(self):
        with pg_session() as db:
            page = _page(db)
            v1 = svc.save_version(db, page.id, doc=_doc("live"), commit_message=None, user_id=None)
            v2 = svc.save_version(db, page.id, doc=_doc("draft"), commit_message=None, user_id=None)

            svc.move_label(db, page.id, svc.PUBLISHED, version_id=v1.id, user_id=None)
            svc.move_label(db, page.id, svc.STAGING, version_id=v2.id, user_id=None)

            # A reviewer looking at staging must not change what readers see.
            assert svc.published_doc(db, page.slug)["version"] == 1
            assert svc.labels_for(db, page.id)[v2.id] == [svc.STAGING]

    def test_a_label_cannot_point_at_another_pages_version(self):
        with pg_session() as db:
            mine, theirs = _page(db, "mine"), _page(db, "theirs")
            other = svc.save_version(db, theirs.id, doc=_doc("x"), commit_message=None, user_id=None)

            with pytest.raises(AppException) as err:
                svc.move_label(db, mine.id, svc.PUBLISHED, version_id=other.id, user_id=None)
            assert err.value.status_code == 404

    def test_unknown_label_is_rejected(self):
        with pg_session() as db:
            page = _page(db)
            v1 = svc.save_version(db, page.id, doc=_doc("a"), commit_message=None, user_id=None)

            with pytest.raises(AppException) as err:
                svc.move_label(db, page.id, "live", version_id=v1.id, user_id=None)
            assert err.value.status_code == 422


class TestPublicRead:
    def test_an_unpublished_page_is_404_and_never_falls_through(self):
        with pg_session() as db:
            page = _page(db)
            svc.save_version(db, page.id, doc=_doc("secret draft"), commit_message=None, user_id=None)

            # The version exists. Serving it because "there is something there"
            # would leak an unpublished draft, which is worse than a 404 because
            # nobody would notice it happened.
            with pytest.raises(AppException) as err:
                svc.published_doc(db, page.slug)
            assert err.value.status_code == 404

    def test_staging_alone_does_not_make_a_page_public(self):
        with pg_session() as db:
            page = _page(db)
            v1 = svc.save_version(db, page.id, doc=_doc("draft"), commit_message=None, user_id=None)
            svc.move_label(db, page.id, svc.STAGING, version_id=v1.id, user_id=None)

            with pytest.raises(AppException) as err:
                svc.published_doc(db, page.slug)
            assert err.value.status_code == 404

    def test_unknown_slug_is_404(self):
        with pg_session() as db:
            with pytest.raises(AppException) as err:
                svc.published_doc(db, unique_code("nope").lower())
            assert err.value.status_code == 404


class TestPages:
    def test_duplicate_slug_is_rejected(self):
        with pg_session() as db:
            page = _page(db)
            with pytest.raises(AppException) as err:
                svc.create_page(db, name="ZZT clash", slug=page.slug, user_id=None)
            assert err.value.status_code == 409

    def test_listing_reports_live_and_latest_separately(self):
        with pg_session() as db:
            page = _page(db)
            v1 = svc.save_version(db, page.id, doc=_doc("a"), commit_message=None, user_id=None)
            svc.save_version(db, page.id, doc=_doc("b"), commit_message=None, user_id=None)
            svc.move_label(db, page.id, svc.PUBLISHED, version_id=v1.id, user_id=None)

            row = next(r for r in svc.list_pages(db) if r["id"] == page.id)
            # The gap between these two IS the unpublished work, so they must
            # not be collapsed into one number.
            assert row["published_version"] == 1
            assert row["latest_version"] == 2

    def test_deleting_a_page_takes_its_versions_and_labels(self):
        with pg_session() as db:
            page = _page(db)
            page_id = page.id
            v1 = svc.save_version(db, page_id, doc=_doc("a"), commit_message=None, user_id=None)
            svc.move_label(db, page_id, svc.PUBLISHED, version_id=v1.id, user_id=None)

            svc.delete_page(db, page_id)

            assert db.query(Page).filter(Page.id == page_id).count() == 0
            assert db.query(PageVersion).filter(PageVersion.page_id == page_id).count() == 0
            assert db.query(PageLabel).filter(PageLabel.page_id == page_id).count() == 0
