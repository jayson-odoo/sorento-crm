"""The public catalogue reader: GET /api/v1/public/c/{company_code}/{slug}.

Three things have to hold here, and only one of them is obvious.

1. A reader with no credentials can read a PUBLISHED page. Obvious.
2. A page with no ``published`` label is a 404. It must never fall through to
   the newest version - an unfinished draft reaching a dealer is worse than a
   missing page, because nobody would find out.
3. Two companies may hold the SAME slug, and the reader must get the one they
   asked for. This is why the address carries a company code at all, and it is
   the case a single-company test would never catch.
"""
from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.models.base import company_scope
from app.models.company import Company
from app.models.dealer_kit import Page, PageLabel, PageVersion
from tests._pg_fixture import pg_session, unique_code

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)


def _company(db, label: str) -> Company:
    code = unique_code(f"ZZT{label}")[:20]
    company = Company(id=str(uuid.uuid4()), name=f"ZZT {label}", code=code, is_active=True)
    db.add(company)
    db.flush()
    return company


def _published_page(db, company: Company, slug: str, marker: str) -> Page:
    """A page owned by ``company``, published, carrying ``marker`` in its doc."""
    with company_scope(db, frozenset({company.id})):
        page = Page(name=f"ZZT {marker}", slug=slug, print_profile=None)
        db.add(page)
        db.flush()
        version = PageVersion(
            page_id=page.id,
            version=1,
            doc={"sections": [{"id": "s1", "name": marker, "blocks": []}]},
        )
        db.add(version)
        db.flush()
        db.add(PageLabel(page_id=page.id, label="published", version_id=version.id))
        db.flush()
    return page


def _client(db) -> TestClient:
    """A TestClient with NO principal - exactly what an anonymous reader has."""
    from app.database import get_db

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    return TestClient(app)


def test_an_anonymous_reader_gets_the_published_page():
    with pg_session() as db:
        company = _company(db, "SOLO")
        slug = unique_code("zzt-live").lower()
        _published_page(db, company, slug, "LIVE CONTENT")
        try:
            with _client(db) as c:
                res = c.get(f"/api/v1/public/c/{company.code}/{slug}")
            assert res.status_code == 200, res.text
            body = res.json()
            assert body["slug"] == slug
            assert body["doc"]["sections"][0]["name"] == "LIVE CONTENT"
            # History is internal: a reader has no use for version numbers or
            # commit messages, so they are not in the response at all.
            assert "versions" not in body and "version" not in body
        finally:
            app.dependency_overrides.clear()


def test_two_companies_may_hold_the_same_slug_and_each_reader_gets_theirs():
    """The case the company segment in the URL exists for."""
    with pg_session() as db:
        sorento = _company(db, "SRTX")
        mocha = _company(db, "MCHX")
        slug = unique_code("zzt-shared").lower()
        _published_page(db, sorento, slug, "SORENTO EDITION")
        _published_page(db, mocha, slug, "MOCHA EDITION")
        try:
            with _client(db) as c:
                a = c.get(f"/api/v1/public/c/{sorento.code}/{slug}")
                b = c.get(f"/api/v1/public/c/{mocha.code}/{slug}")
            assert a.status_code == 200 and b.status_code == 200
            assert a.json()["doc"]["sections"][0]["name"] == "SORENTO EDITION"
            assert b.json()["doc"]["sections"][0]["name"] == "MOCHA EDITION"
        finally:
            app.dependency_overrides.clear()


def test_an_unpublished_page_is_404_not_a_draft():
    with pg_session() as db:
        company = _company(db, "DRAFT")
        slug = unique_code("zzt-draft").lower()
        with company_scope(db, frozenset({company.id})):
            page = Page(name="ZZT draft", slug=slug, print_profile=None)
            db.add(page)
            db.flush()
            # A saved version exists - it just was never published.
            db.add(PageVersion(page_id=page.id, version=1, doc={"sections": [], "secret": True}))
            db.flush()
        try:
            with _client(db) as c:
                res = c.get(f"/api/v1/public/c/{company.code}/{slug}")
            assert res.status_code == 404, res.text
            assert "secret" not in res.text
        finally:
            app.dependency_overrides.clear()


def test_a_staging_label_alone_does_not_make_a_page_public():
    with pg_session() as db:
        company = _company(db, "STAGE")
        slug = unique_code("zzt-stage").lower()
        with company_scope(db, frozenset({company.id})):
            page = Page(name="ZZT stage", slug=slug, print_profile=None)
            db.add(page)
            db.flush()
            version = PageVersion(page_id=page.id, version=1, doc={"sections": []})
            db.add(version)
            db.flush()
            db.add(PageLabel(page_id=page.id, label="staging", version_id=version.id))
            db.flush()
        try:
            with _client(db) as c:
                res = c.get(f"/api/v1/public/c/{company.code}/{slug}")
            assert res.status_code == 404, res.text
        finally:
            app.dependency_overrides.clear()


def test_an_unknown_company_code_is_404_and_reveals_nothing():
    with pg_session() as db:
        company = _company(db, "REAL")
        slug = unique_code("zzt-real").lower()
        _published_page(db, company, slug, "REAL CONTENT")
        try:
            with _client(db) as c:
                res = c.get(f"/api/v1/public/c/ZZT-NO-SUCH-CO/{slug}")
            assert res.status_code == 404, res.text
            assert "REAL CONTENT" not in res.text
        finally:
            app.dependency_overrides.clear()


def test_an_inactive_company_stops_serving():
    with pg_session() as db:
        company = _company(db, "GONE")
        slug = unique_code("zzt-gone").lower()
        _published_page(db, company, slug, "ARCHIVED")
        company.is_active = False
        db.flush()
        try:
            with _client(db) as c:
                res = c.get(f"/api/v1/public/c/{company.code}/{slug}")
            assert res.status_code == 404, res.text
        finally:
            app.dependency_overrides.clear()


def test_the_address_is_case_insensitive_on_the_company_code():
    """A code shared over WhatsApp gets its case mangled; that must still resolve."""
    with pg_session() as db:
        company = _company(db, "CASE")
        slug = unique_code("zzt-case").lower()
        _published_page(db, company, slug, "CASE CONTENT")
        try:
            with _client(db) as c:
                res = c.get(f"/api/v1/public/c/{company.code.lower()}/{slug}")
            assert res.status_code == 200, res.text
        finally:
            app.dependency_overrides.clear()
