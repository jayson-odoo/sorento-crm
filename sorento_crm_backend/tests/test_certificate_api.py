"""Route-level tests for the certificate register: ingest (S3), merge (S4), CRUD (S5).

Substrate rules (non-negotiable, group T): Postgres only, on the shared blank
schema whose writes are discarded. Every test seeds its OWN chain - attachment
type, attachment, category, uom, product - under a ZZTCAPI marker. Nothing is
borrowed from an existing table and nothing asserts about a production row: CI's
database is empty, so a `LIMIT 1` off `products` there returns None and the
dependent insert dies on a not-null FK.

Auth: `app.main` is imported FIRST to break the circular import in
`app.modules.runtime.guards`, then the auth dependencies are overridden. Two
principals are seeded - a superadmin (every check short-circuits true) and a
plain user with no grants at all, which is what the denial tests act as.
"""
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

# MUST be the first app import - resolves the circular import in
# app.modules.runtime.guards.
from app.main import app  # noqa: E402

from app.models.certificate import (
    CERTIFICATE_SOURCE_AI,
    CERTIFICATE_SOURCE_MANUAL,
    Certificate,
    CertificateProduct,
    CertificateRevision,
)
from app.models.integration import IntegrationLog
from app.models.product import Product, ProductAttachment, ProductCategory, UnitOfMeasure
from app.models.resources import Attachment, AttachmentType
from tests._pg_fixture import blank_session, unique_code

MARKER = "ZZTCAPI"
BASE = "/api/v1/master-data/certificates"
EXTERNAL = "/api/v1/external/product-attachments"

_SUPERADMIN_USER_ID = "3a8b9c10-1111-4222-8333-444455556666"
# The incumbent company, auto-seeded into every test schema by conftest's
# after_create hook on the companies table.
_SORENTO_COMPANY_ID = "00000000-0000-0000-0000-000000000001"
_SUPERADMIN_ROLE_ID = "3a8b9c10-2222-4222-8333-444455556666"
_PLAIN_USER_ID = "3a8b9c10-3333-4222-8333-444455556666"
_PLAIN_ROLE_ID = "3a8b9c10-4444-4222-8333-444455556666"

TODAY = date.today()


# --------------------------------------------------------------------- fixtures
def _seed_principals(db) -> None:
    """A superadmin (bypasses every slug) and a plain user (holds nothing)."""
    from app.models.user import User, UserRole, UserRoleAssignment

    db.add_all(
        [
            UserRole(
                id=_SUPERADMIN_ROLE_ID,
                slug="superadmin",
                name=f"{MARKER} Superadmin",
                description="",
                is_protected=True,
                is_default=False,
            ),
            UserRole(
                id=_PLAIN_ROLE_ID,
                slug=f"{MARKER.lower()}_no_grants",
                name=f"{MARKER} No grants",
                description="",
                is_protected=False,
                is_default=False,
            ),
        ]
    )
    db.flush()
    db.add_all(
        [
            User(
                id=_SUPERADMIN_USER_ID,
                email=f"{MARKER.lower()}-admin@test.com",
                name="Admin",
                status="ACTIVE",
            ),
            User(
                id=_PLAIN_USER_ID,
                email=f"{MARKER.lower()}-plain@test.com",
                name="Plain",
                status="ACTIVE",
            ),
        ]
    )
    db.flush()
    db.add_all(
        [
            UserRoleAssignment(user_id=_SUPERADMIN_USER_ID, role_id=_SUPERADMIN_ROLE_ID),
            UserRoleAssignment(user_id=_PLAIN_USER_ID, role_id=_PLAIN_ROLE_ID),
        ]
    )
    db.commit()


class _Env:
    """The TestClient plus the session it shares, and a switchable principal."""

    def __init__(self, client: TestClient, db, acting: dict):
        self.client = client
        self.db = db
        self._acting = acting

    def act_as_plain_user(self) -> None:
        """Switch every auth dependency to the grantless user (denial tests)."""
        self._acting["user"] = {"id": _PLAIN_USER_ID, "email": "plain@test.com"}

    # ---- chain seeding (each test builds its own) ----
    def attachment_type(self, *, is_certificate: bool, name: str, max_months=None) -> Any:
        row = AttachmentType(
            type_name=f"{MARKER} {name} {unique_code()}",
            allowed_extensions="pdf",
            max_file_size_mb=10,
            is_certificate=is_certificate,
            max_validity_months=max_months,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def product(self, code_stem: str, *, code: str | None = None) -> Any:
        """Seed one product. Pass ``code`` to control the code exactly - the
        fan-out tests need a family that shares a substring."""
        if not hasattr(self, "_category"):
            self._category = ProductCategory(
                category_code=unique_code(MARKER), category_name=f"{MARKER} category"
            )
            self._uom = UnitOfMeasure(uom_code=unique_code(MARKER), uom_name=f"{MARKER} unit")
            self.db.add_all([self._category, self._uom])
            self.db.flush()
        row = Product(
            product_code=code or unique_code(f"{MARKER}-{code_stem}"),
            product_name=f"{MARKER} {code_stem}",
            category_id=self._category.id,
            base_uom_id=self._uom.id,
            list_price=10,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def attachment(self, attachment_type, name: str, *, is_deleted: bool = False) -> Any:
        row = Attachment(
            attachment_type_id=attachment_type.id,
            original_filename=f"{MARKER}-{name}.pdf",
            stored_filename=f"{MARKER}-{name}.pdf",
            file_path=f"https://cdn.example/{MARKER}/{name}.pdf",
            access_levels=["dealer"],
            is_deleted=is_deleted,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def projection(self, attachment_id) -> list[Any]:
        return (
            self.db.query(ProductAttachment)
            .filter(ProductAttachment.attachment_id == str(attachment_id))
            .all()
        )


@pytest.fixture
def env():
    from app.dependencies import (  # safe: app.main is already loaded
        get_current_user,
        get_current_user_or_api_key,
        get_db,
        get_external_api_user,
    )
    from app.services.company_scope import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        _seed_principals(db)
        acting = {"user": {"id": _SUPERADMIN_USER_ID, "email": "admin@test.com"}}

        def _override_get_db():
            yield db

        def _override_current_user():
            return dict(acting["user"])

        # The api_router carries `apply_company_scope` as a router-level dependency,
        # which re-resolves the scope from the acting user and stamps it onto the
        # request session - overwriting whatever the fixture set. The seeded test
        # principals hold no company membership, so it resolves to UNSET and every
        # owned insert is refused by the auto-stamp guard (AC-D4). Pin the incumbent
        # company here so the tests declare their own company context explicitly.
        def _override_company_scope():
            set_company_scope(db, frozenset({_SORENTO_COMPANY_ID}))
            return frozenset({_SORENTO_COMPANY_ID})

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = _override_current_user
        app.dependency_overrides[get_current_user_or_api_key] = _override_current_user
        app.dependency_overrides[get_external_api_user] = _override_current_user
        app.dependency_overrides[apply_company_scope] = _override_company_scope
        try:
            with TestClient(app) as client:
                yield _Env(client, db, acting)
        finally:
            app.dependency_overrides.clear()


def _create(env: _Env, **overrides) -> dict:
    """POST a certificate and return the body. Raises on anything but 201."""
    payload = {
        "scheme": f"{MARKER}PPS",
        "certificate_number": unique_code("NUM"),
        "certifying_body": "IKRAM",
        "valid_until": (TODAY + timedelta(days=400)).isoformat(),
    }
    payload.update(overrides)
    response = env.client.post(f"{BASE}/", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ===================================================================== S5: CRUD
def test_create_list_get_update_delete(env):
    attachment_type = env.attachment_type(is_certificate=True, name="Certification")
    attachment = env.attachment(attachment_type, "crud")
    product = env.product("CRUD")

    created = _create(
        env,
        certificate_number="CRUD 001",
        attachment_type_id=str(attachment_type.id),
        attachment_id=str(attachment.id),
        product_ids=[str(product.id)],
        valid_from=(TODAY - timedelta(days=10)).isoformat(),
        valid_until=(TODAY + timedelta(days=400)).isoformat(),
    )
    assert created["validity_state"] == "valid"
    assert created["is_expired"] is False
    assert created["covered_product_count"] == 1
    assert created["status"] == "active"
    certificate_id = created["id"]

    listing = env.client.get(f"{BASE}/", params={"certificate_ids": certificate_id})
    assert listing.status_code == 200, listing.text
    body = listing.json()
    assert body["pagination"]["total"] == 1
    assert body["data"][0]["id"] == certificate_id
    # Detail-only expansions must not be paid for on a list row.
    assert body["data"][0]["revisions"] is None

    detail = env.client.get(f"{BASE}/{certificate_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["revision_no"] == 1

    updated = env.client.put(
        f"{BASE}/{certificate_id}", json={"issuer": "IKRAM QA", "status": "archived"}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["issuer"] == "IKRAM QA"
    assert updated.json()["status"] == "archived"

    deleted = env.client.delete(f"{BASE}/{certificate_id}")
    assert deleted.status_code == 200, deleted.text
    assert env.client.get(f"{BASE}/{certificate_id}").status_code == 404
    # COV-5: the file outlives the register row that indexed it.
    assert env.db.query(Attachment).filter(Attachment.id == attachment.id).count() == 1
    assert env.projection(attachment.id) == []


def test_detail_renders_every_section(env):
    """The detail page always renders each section, so each key is always present."""
    attachment_type = env.attachment_type(is_certificate=True, name="Certification")
    original = _create(env, certificate_number="WCM PC 000321")
    near_match = _create(env, certificate_number="WCM PC 0O0321")

    detail = env.client.get(f"{BASE}/{near_match['id']}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    for key in ("revisions", "products", "unmatched_products", "reminders", "current_revision"):
        assert key in body, key
    assert body["reminders"] == []
    assert body["products"] == []
    # DUP-3: resolved to something renderable, never a bare id.
    assert body["possible_duplicate_of"] == {
        "id": original["id"],
        "scheme": original["scheme"],
        "certificate_number": original["certificate_number"],
    }


def test_detail_lists_revisions_newest_first(env):
    from app.services.certificate_service import CertificateService

    attachment_type = env.attachment_type(is_certificate=True, name="Certification")
    created = _create(env, certificate_number="REVORDER 1")
    CertificateService(env.db).add_revision(
        created["id"], valid_until=(TODAY + timedelta(days=800)).isoformat() and TODAY + timedelta(days=800)
    )

    body = env.client.get(f"{BASE}/{created['id']}").json()
    assert [r["revision_no"] for r in body["revisions"]] == [2, 1]
    assert body["current_revision"]["revision_no"] == 2


def test_partial_update_does_not_null_the_other_dates(env):
    """`update_revision` nulls whatever it is handed as omitted, so the route must
    forward only the keys the caller actually sent."""
    created = _create(
        env,
        certificate_number="PARTIAL 1",
        issued_at=(TODAY - timedelta(days=30)).isoformat(),
        valid_from=(TODAY - timedelta(days=20)).isoformat(),
        valid_until=(TODAY + timedelta(days=400)).isoformat(),
    )

    response = env.client.put(f"{BASE}/{created['id']}", json={"certifying_body": "JBC"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["certifying_body"] == "JBC"
    assert body["issued_at"] == (TODAY - timedelta(days=30)).isoformat()
    assert body["valid_from"] == (TODAY - timedelta(days=20)).isoformat()
    assert body["valid_until"] == (TODAY + timedelta(days=400)).isoformat()

    # And a date edit really does land on the current revision.
    response = env.client.put(
        f"{BASE}/{created['id']}", json={"valid_until": (TODAY + timedelta(days=900)).isoformat()}
    )
    assert response.status_code == 200, response.text
    assert response.json()["valid_until"] == (TODAY + timedelta(days=900)).isoformat()
    assert response.json()["issued_at"] == (TODAY - timedelta(days=30)).isoformat()


def test_bulk_delete(env):
    first = _create(env, certificate_number="BULK 1")
    second = _create(env, certificate_number="BULK 2")

    response = env.client.request(
        "DELETE", f"{BASE}/bulk", json={"ids": [first["id"], second["id"]]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["deleted_count"] == 2
    assert env.client.get(f"{BASE}/{first['id']}").status_code == 404
    assert env.client.get(f"{BASE}/{second['id']}").status_code == 404


def test_add_and_remove_covered_product(env):
    attachment_type = env.attachment_type(is_certificate=True, name="Certification")
    attachment = env.attachment(attachment_type, "coverage")
    product = env.product("COVER")
    created = _create(
        env,
        certificate_number="COVERAGE 1",
        attachment_id=str(attachment.id),
        valid_until=(TODAY + timedelta(days=400)).isoformat(),
    )

    added = env.client.post(
        f"{BASE}/{created['id']}/products", json={"product_id": str(product.id)}
    )
    assert added.status_code == 201, added.text
    body = added.json()
    assert body["covered_product_count"] == 1
    coverage = body["products"][0]
    # COV-2: a human-added link is 'manual', never presented as inferred.
    assert coverage["source"] == CERTIFICATE_SOURCE_MANUAL
    assert coverage["product_code"] == product.product_code
    # COV-3: the projection row for the current revision's attachment came with it.
    assert {str(r.product_id) for r in env.projection(attachment.id)} == {str(product.id)}

    removed = env.client.delete(f"{BASE}/{created['id']}/products/{coverage['id']}")
    assert removed.status_code == 200, removed.text
    assert env.projection(attachment.id) == []


def test_covered_products_include_company_name(env):
    """The Products tab must show every coverage row with a Company column -
    not just the ones matching the viewer's company scope (captain's ruling,
    1 Sep 2026). ``response_model`` silently drops undeclared fields, so this
    asserts ``company_name`` lands in the ROUTE json, not just the service
    return."""
    from app.models.company import Company

    mocha_id = "00000000-0000-0000-0000-000000000002"
    if env.db.query(Company).filter(Company.id == mocha_id).first() is None:
        env.db.add(Company(id=mocha_id, name=f"{MARKER} Mocha", code=unique_code("MCH")[:20]))
        env.db.flush()

    attachment_type = env.attachment_type(is_certificate=True, name="Certification")
    attachment = env.attachment(attachment_type, "companycol")
    sorento_product = env.product("COMPCOLA")
    mocha_product = Product(
        product_code=unique_code(f"{MARKER}-COMPCOLB"),
        product_name=f"{MARKER} compcol b",
        category_id=env._category.id,
        base_uom_id=env._uom.id,
        list_price=10,
        company_id=mocha_id,
    )
    env.db.add(mocha_product)
    env.db.flush()

    created = _create(
        env,
        certificate_number="COMPCOL 1",
        attachment_id=str(attachment.id),
        product_ids=[str(sorento_product.id)],
        valid_until=(TODAY + timedelta(days=400)).isoformat(),
    )
    # AI extraction can also write coverage for the OTHER company's product -
    # add_coverage's own lookup is scoped, so this mirrors that path directly
    # rather than going through the endpoint.
    env.db.add(
        CertificateProduct(
            certificate_id=created["id"],
            product_id=str(mocha_product.id),
            source=CERTIFICATE_SOURCE_AI,
        )
    )
    env.db.commit()

    detail = env.client.get(f"{BASE}/{created['id']}")
    assert detail.status_code == 200, detail.text
    by_product = {row["product_id"]: row for row in detail.json()["products"]}
    assert len(by_product) == 2
    # No blank rows: the other company's product still resolves code/name.
    assert by_product[str(sorento_product.id)]["product_code"] == sorento_product.product_code
    assert by_product[str(sorento_product.id)]["company_name"] == "Sorento"
    assert by_product[str(mocha_product.id)]["product_code"] == mocha_product.product_code
    assert by_product[str(mocha_product.id)]["company_name"] == f"{MARKER} Mocha"


def test_remove_coverage_from_another_certificate_is_404(env):
    """certificate_products is not company-scoped, so the row is resolved through
    its certificate - a coverage id belonging elsewhere must not delete."""
    product = env.product("CROSSCOV")
    owner = _create(env, certificate_number="OWNER 1")
    other = _create(env, certificate_number="OTHER 1")
    added = env.client.post(f"{BASE}/{owner['id']}/products", json={"product_id": str(product.id)})
    coverage_id = added.json()["products"][0]["id"]

    response = env.client.delete(f"{BASE}/{other['id']}/products/{coverage_id}")
    assert response.status_code == 404, response.text
    assert (
        env.db.query(CertificateProduct).filter(CertificateProduct.id == coverage_id).count() == 1
    )


# ------------------------------------------------------------------ S5: filters
def test_validity_state_accepts_a_comma_separated_list(env):
    """The default view sends `expiring_soon,expired`, so the filter is a LIST."""
    expiring = _create(
        env,
        certificate_number="VS EXPIRING",
        valid_until=(TODAY + timedelta(days=10)).isoformat(),
    )
    expired = _create(
        env, certificate_number="VS EXPIRED", valid_until=(TODAY - timedelta(days=5)).isoformat()
    )
    live = _create(
        env, certificate_number="VS VALID", valid_until=(TODAY + timedelta(days=400)).isoformat()
    )
    unknown = _create(env, certificate_number="VS UNKNOWN", valid_until=None)

    response = env.client.get(f"{BASE}/", params={"validity_state": "expiring_soon,expired"})
    assert response.status_code == 200, response.text
    got = {row["id"] for row in response.json()["data"]}
    assert {expiring["id"], expired["id"]} <= got
    assert live["id"] not in got
    assert unknown["id"] not in got

    single = env.client.get(f"{BASE}/", params={"validity_state": "unknown"})
    assert {row["id"] for row in single.json()["data"]} >= {unknown["id"]}
    assert expired["id"] not in {row["id"] for row in single.json()["data"]}


def test_validity_state_rejects_an_unknown_value(env):
    response = env.client.get(f"{BASE}/", params={"validity_state": "expiring_soon,banana"})
    assert response.status_code == 400, response.text
    assert "banana" in response.text


def test_certificate_number_is_normalized_server_side(env):
    created = _create(env, certificate_number="PPS 0119")

    for probe in ("PPS 0119", "pps-0119", "PPS0119"):
        response = env.client.get(f"{BASE}/", params={"certificate_number": probe})
        assert response.status_code == 200, response.text
        assert created["id"] in {row["id"] for row in response.json()["data"]}, probe

    miss = env.client.get(f"{BASE}/", params={"certificate_number": "PPS 9999"})
    assert created["id"] not in {row["id"] for row in miss.json()["data"]}


def test_filter_by_product_ids_and_expiring_within_days(env):
    covered = env.product("FILTERED")
    other = env.product("UNRELATED")
    soon = _create(
        env,
        certificate_number="FILTER SOON",
        product_ids=[str(covered.id)],
        valid_until=(TODAY + timedelta(days=20)).isoformat(),
    )
    later = _create(
        env,
        certificate_number="FILTER LATER",
        product_ids=[str(other.id)],
        valid_until=(TODAY + timedelta(days=400)).isoformat(),
    )

    by_product = env.client.get(f"{BASE}/", params={"product_ids": str(covered.id)})
    assert by_product.status_code == 200, by_product.text
    assert {row["id"] for row in by_product.json()["data"]} == {soon["id"]}

    expiring = env.client.get(f"{BASE}/", params={"expiring_within_days": 30})
    got = {row["id"] for row in expiring.json()["data"]}
    assert soon["id"] in got and later["id"] not in got


def test_needs_review_and_status_filters(env):
    """A NULL expiry is `unknown` AND flagged; a complete one is not."""
    flagged = _create(env, certificate_number="REVIEW FLAGGED", valid_until=None)
    clean = _create(
        env,
        certificate_number="REVIEW CLEAN",
        product_ids=[str(env.product("REVIEWED").id)],
        valid_until=(TODAY + timedelta(days=400)).isoformat(),
    )
    assert clean["needs_review"] is False

    response = env.client.get(f"{BASE}/", params={"needs_review": "true"})
    got = {row["id"] for row in response.json()["data"]}
    assert flagged["id"] in got and clean["id"] not in got

    env.client.put(f"{BASE}/{clean['id']}", json={"status": "archived"})
    archived = env.client.get(f"{BASE}/", params={"status": "archived"})
    assert {row["id"] for row in archived.json()["data"]} == {clean["id"]}


def test_status_filter_rejects_a_validity_value(env):
    """SCH-7: no validity value is ever a status."""
    response = env.client.get(f"{BASE}/", params={"status": "expired"})
    assert response.status_code == 400, response.text


def test_resolve_signed_urls_only_ever_signs_the_current_revision(env):
    """MCP-7 / MCP-8: the live document, or nothing. Never the superseded one."""
    from app.services.certificate_service import CertificateService

    attachment_type = env.attachment_type(is_certificate=True, name="Certification")
    first = env.attachment(attachment_type, "signed-rev1")
    second = env.attachment(attachment_type, "signed-rev2")
    created = _create(
        env,
        certificate_number="SIGNED 1",
        attachment_id=str(first.id),
        valid_until=(TODAY + timedelta(days=400)).isoformat(),
    )
    CertificateService(env.db).add_revision(
        created["id"],
        attachment_id=str(second.id),
        valid_until=TODAY + timedelta(days=800),
    )

    response = env.client.get(
        f"{BASE}/", params={"certificate_ids": created["id"], "resolve_signed_urls": "true"}
    )
    assert response.status_code == 200, response.text
    row = response.json()["data"][0]
    assert row["preview_url"] and row["download_url"]
    assert "signed-rev2" in row["preview_url"]
    assert "signed-rev1" not in row["preview_url"]

    # Off by default: an unsigned listing carries no URLs at all.
    plain = env.client.get(f"{BASE}/", params={"certificate_ids": created["id"]})
    assert plain.json()["data"][0]["preview_url"] is None


def test_signed_urls_are_null_for_a_trashed_or_missing_file(env):
    attachment_type = env.attachment_type(is_certificate=True, name="Certification")
    trashed = env.attachment(attachment_type, "trashed", is_deleted=True)
    with_file = _create(
        env,
        certificate_number="TRASHED 1",
        attachment_id=str(trashed.id),
        valid_until=(TODAY + timedelta(days=400)).isoformat(),
    )
    no_file = _create(
        env, certificate_number="NOFILE 1", valid_until=(TODAY + timedelta(days=400)).isoformat()
    )

    for certificate_id in (with_file["id"], no_file["id"]):
        response = env.client.get(
            f"{BASE}/{certificate_id}", params={"resolve_signed_urls": "true"}
        )
        assert response.status_code == 200, response.text
        assert response.json()["preview_url"] is None
        assert response.json()["download_url"] is None


def test_list_sorts_from_an_allowlist_and_ignores_unknown_columns(env):
    early = _create(
        env, certificate_number="SORT EARLY", valid_until=(TODAY + timedelta(days=10)).isoformat()
    )
    late = _create(
        env, certificate_number="SORT LATE", valid_until=(TODAY + timedelta(days=900)).isoformat()
    )
    ids = {early["id"], late["id"]}

    ascending = [
        row["id"]
        for row in env.client.get(
            f"{BASE}/", params={"sort": "valid_until", "dir": "asc", "limit": 1000}
        ).json()["data"]
        if row["id"] in ids
    ]
    assert ascending == [early["id"], late["id"]]

    descending = [
        row["id"]
        for row in env.client.get(
            f"{BASE}/", params={"sort": "valid_until", "dir": "desc", "limit": 1000}
        ).json()["data"]
        if row["id"] in ids
    ]
    assert descending == [late["id"], early["id"]]

    # An unknown column falls back to the default rather than 500-ing on getattr.
    response = env.client.get(f"{BASE}/", params={"sort": "drop table certificates"})
    assert response.status_code == 200, response.text


# ------------------------------------------------------------ S5: validation
def test_create_rejects_a_missing_scheme(env):
    response = env.client.post(f"{BASE}/", json={"certificate_number": "NOSCHEME 1"})
    assert response.status_code == 422, response.text


def test_create_rejects_an_unknown_status(env):
    response = env.client.post(
        f"{BASE}/",
        json={"scheme": f"{MARKER}PPS", "certificate_number": "BADSTATUS 1", "status": "expired"},
    )
    assert response.status_code == 422, response.text


def test_create_rejects_a_duplicate_identity(env):
    _create(env, certificate_number="DUPE 1")
    response = env.client.post(
        f"{BASE}/", json={"scheme": f"{MARKER}pps", "certificate_number": "dupe-1"}
    )
    assert response.status_code == 400, response.text


def test_unknown_and_malformed_ids_are_404(env):
    assert env.client.get(f"{BASE}/not-a-uuid").status_code == 404
    assert (
        env.client.get(f"{BASE}/11111111-2222-4333-8444-555566667777").status_code == 404
    )


# ----------------------------------------------------------------- S5: denial
@pytest.mark.parametrize(
    "method,path_suffix,body",
    [
        ("get", "/", None),
        ("post", "/", {"scheme": "PPS", "certificate_number": "DENIED 1"}),
    ],
)
def test_collection_routes_deny_a_user_without_grants(env, method, path_suffix, body):
    env.act_as_plain_user()
    # TestClient.get() takes no `json` kwarg, so only pass a body when there is one.
    kwargs = {"json": body} if body is not None else {}
    response = getattr(env.client, method)(f"{BASE}{path_suffix}", **kwargs)
    assert response.status_code == 403, response.text


def test_detail_routes_deny_a_user_without_grants(env):
    created = _create(env, certificate_number="DENIED DETAIL")
    product = env.product("DENIED")
    env.act_as_plain_user()

    assert env.client.get(f"{BASE}/{created['id']}").status_code == 403
    assert env.client.put(f"{BASE}/{created['id']}", json={"issuer": "x"}).status_code == 403
    assert env.client.delete(f"{BASE}/{created['id']}").status_code == 403
    assert (
        env.client.post(
            f"{BASE}/{created['id']}/products", json={"product_id": str(product.id)}
        ).status_code
        == 403
    )
    assert (
        env.client.request("DELETE", f"{BASE}/bulk", json={"ids": [created["id"]]}).status_code
        == 403
    )
    assert (
        env.client.post(f"{BASE}/{created['id']}/merge-into/{created['id']}").status_code == 403
    )


# =================================================================== S4: merge
def test_merge_into_folds_the_source_into_the_target(env):
    attachment_type = env.attachment_type(is_certificate=True, name="Certification")
    target_file = env.attachment(attachment_type, "merge-target")
    source_file = env.attachment(attachment_type, "merge-source")
    shared = env.product("MERGESHARED")
    only_source = env.product("MERGESOURCE")

    target = _create(
        env,
        certificate_number="MERGE TARGET",
        attachment_id=str(target_file.id),
        product_ids=[str(shared.id)],
        valid_until=(TODAY + timedelta(days=200)).isoformat(),
    )
    source = _create(
        env,
        certificate_number="MERGE SOURCE",
        attachment_id=str(source_file.id),
        product_ids=[str(shared.id), str(only_source.id)],
        valid_until=(TODAY + timedelta(days=900)).isoformat(),
    )

    response = env.client.post(f"{BASE}/{source['id']}/merge-into/{target['id']}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == target["id"]
    assert [r["revision_no"] for r in body["revisions"]] == [2, 1]
    assert body["covered_product_count"] == 2
    assert env.client.get(f"{BASE}/{source['id']}").status_code == 404
    # The projection follows whichever revision ends up current.
    assert env.projection(target_file.id) == []
    assert {str(r.product_id) for r in env.projection(source_file.id)} == {
        str(shared.id),
        str(only_source.id),
    }


def test_merge_into_itself_is_422(env):
    created = _create(env, certificate_number="SELFMERGE 1")
    response = env.client.post(f"{BASE}/{created['id']}/merge-into/{created['id']}")
    assert response.status_code == 422, response.text


def test_merge_with_an_unknown_target_is_404(env):
    created = _create(env, certificate_number="MERGEMISSING 1")
    response = env.client.post(
        f"{BASE}/{created['id']}/merge-into/11111111-2222-4333-8444-555566667777"
    )
    assert response.status_code == 404, response.text


# ================================================================== S3: ingest
def _cert_payload(attachment, products, **overrides) -> dict:
    payload = {
        "attachment_id": str(attachment.id),
        "products": [p.product_code for p in products],
        "scheme": "PPS",
        "certifying_body": "IKRAM",
        "certificate_number": "04424FC",
        # Deliberately not ISO: the reader really does emit this form.
        "valid_until": "23/12/2026",
    }
    payload.update(overrides)
    return payload


def test_ingest_files_identity_revision_coverage_and_projection(env):
    """ING-3: one call, one transaction, all four artefacts."""
    attachment_type = env.attachment_type(is_certificate=True, name="Certification")
    attachment = env.attachment(attachment_type, "ingest")
    products = [env.product("ING1"), env.product("ING2")]

    # An unmatchable code rides along so RVW-3 has something to record verbatim.
    payload = _cert_payload(attachment, products)
    payload["products"] = [p.product_code for p in products] + ["WC 9999"]

    response = env.client.post(EXTERNAL, json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert {x["product_code"] for x in body["linked"]} == {p.product_code for p in products}
    assert body["skipped_product_codes"] == ["WC 9999"]

    certificate: Any = (
        env.db.query(Certificate)
        .filter(Certificate.certificate_number == "04424FC")
        .one()
    )
    revision: Any = (
        env.db.query(CertificateRevision)
        .filter(CertificateRevision.certificate_id == certificate.id)
        .one()
    )
    assert revision.revision_no == 1
    assert bool(revision.is_current) is True
    assert revision.valid_until == date(2026, 12, 23)
    assert revision.source == CERTIFICATE_SOURCE_AI
    # RVW-3 / ING-7: the string that matched nothing, and the raw reader output.
    assert revision.unmatched_products == ["WC 9999"]
    assert revision.extracted_json["certificate_number"] == "04424FC"

    coverage = (
        env.db.query(CertificateProduct)
        .filter(CertificateProduct.certificate_id == certificate.id)
        .all()
    )
    assert {str(c.product_id) for c in coverage} == {str(p.id) for p in products}
    assert {str(r.product_id) for r in env.projection(attachment.id)} == {
        str(p.id) for p in products
    }
    # SEC-3: the projection inherits the current revision's attachment access levels.
    assert all(r.access_levels == ["dealer"] for r in env.projection(attachment.id))


def test_ingest_ignores_cert_fields_on_a_non_cert_bearing_type(env):
    """ING-4, the load-bearing guard. A Technical Specifications sheet quoting
    "cert PPS 0119" must not mint a certificate."""
    attachment_type = env.attachment_type(is_certificate=False, name="Technical Specifications")
    attachment = env.attachment(attachment_type, "specsheet")
    product = env.product("SPEC")

    response = env.client.post(
        EXTERNAL,
        json=_cert_payload(attachment, [product], certificate_number="PPS 0119"),
    )
    assert response.status_code == 200, response.text
    assert {x["product_code"] for x in response.json()["linked"]} == {product.product_code}

    assert env.db.query(Certificate).count() == 0
    assert env.db.query(CertificateRevision).count() == 0
    # The ordinary linking still happened, unchanged.
    assert {str(r.product_id) for r in env.projection(attachment.id)} == {str(product.id)}


def test_ingest_without_cert_fields_behaves_exactly_as_before(env):
    """ING-5: the regression guard the 951 spec sheets and every photo rely on."""
    attachment_type = env.attachment_type(is_certificate=True, name="Certification")
    attachment = env.attachment(attachment_type, "nocertfields")
    product = env.product("NOCERT")

    response = env.client.post(
        EXTERNAL, json={"attachment_id": str(attachment.id), "products": [product.product_code]}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"attachment_id", "linked", "skipped_product_codes", "already_linked"}
    assert {x["product_code"] for x in body["linked"]} == {product.product_code}

    assert env.db.query(Certificate).count() == 0
    assert env.db.query(IntegrationLog).count() == 0
    assert {str(r.product_id) for r in env.projection(attachment.id)} == {str(product.id)}


def test_ingest_without_a_certificate_number_links_and_logs_why(env):
    """ING-6: no regression on the linking, and the reason is recorded."""
    attachment_type = env.attachment_type(is_certificate=True, name="Certification")
    attachment = env.attachment(attachment_type, "nonumber")
    product = env.product("NONUMBER")

    response = env.client.post(
        EXTERNAL,
        json=_cert_payload(attachment, [product], certificate_number="   "),
    )
    assert response.status_code == 200, response.text
    assert {x["product_code"] for x in response.json()["linked"]} == {product.product_code}
    assert env.db.query(Certificate).count() == 0
    assert {str(r.product_id) for r in env.projection(attachment.id)} == {str(product.id)}

    log: Any = env.db.query(IntegrationLog).one()
    assert str(log.business_id) == str(attachment.id)
    assert log.business_table == "attachments"
    assert log.error_code == "certificate_not_created"
    assert "certificate_number" in (log.error_message or "")


def test_ingest_a_renewal_appends_a_revision_and_repoints_the_projection(env):
    """REV-1 / REV-3 through the real endpoint: one identity, two documents."""
    attachment_type = env.attachment_type(is_certificate=True, name="Certification")
    first = env.attachment(attachment_type, "renewal-1")
    second = env.attachment(attachment_type, "renewal-2")
    products = [env.product("REN1"), env.product("REN2")]

    env.client.post(EXTERNAL, json=_cert_payload(first, products))
    # A renewal PDF naming only one product must not shrink coverage (REV-2).
    renewal_payload = _cert_payload(second, products, valid_until="23/12/2028")
    renewal_payload["products"] = [products[0].product_code]
    renewal = env.client.post(EXTERNAL, json=renewal_payload)
    assert renewal.status_code == 200, renewal.text
    assert renewal.json()["already_linked"] == [products[0].product_code]

    certificate: Any = env.db.query(Certificate).one()
    revisions = (
        env.db.query(CertificateRevision)
        .filter(CertificateRevision.certificate_id == certificate.id)
        .order_by(CertificateRevision.revision_no.desc())
        .all()
    )
    assert [r.revision_no for r in revisions] == [2, 1]
    assert [bool(r.is_current) for r in revisions] == [True, False]
    assert str(certificate.current_revision_id) == str(revisions[0].id)

    # REV-2: 2 links survive with zero coverage writes.
    assert (
        env.db.query(CertificateProduct)
        .filter(CertificateProduct.certificate_id == certificate.id)
        .count()
        == 2
    )
    # REV-3 / REV-4: the superseded PDF serves nothing, but still exists.
    assert env.projection(first.id) == []
    assert {str(r.product_id) for r in env.projection(second.id)} == {str(p.id) for p in products}
    assert env.db.query(Attachment).filter(Attachment.id == first.id).count() == 1


def test_ingest_single_product_code_returns_the_projection_row(env):
    """The legacy single-code node keeps the shape it always received."""
    attachment_type = env.attachment_type(is_certificate=True, name="Certification")
    attachment = env.attachment(attachment_type, "single")
    product = env.product("SINGLE")

    response = env.client.post(
        EXTERNAL,
        json={
            "attachment_id": str(attachment.id),
            "product_code": product.product_code,
            "scheme": "SPAN",
            "certificate_number": "04124FC",
            "valid_until": "2029-04-05",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["product_id"] == str(product.id)
    assert body["attachment_id"] == str(attachment.id)
    assert env.db.query(Certificate).filter(Certificate.scheme == "SPAN").count() == 1


def test_ingest_carries_the_title_the_reader_extracted(env):
    """The service always accepted `title`, but the external payload did not
    declare it, so every AI-filed certificate read "Not recorded" on the detail
    page. It has to survive the round trip."""
    attachment_type = env.attachment_type(is_certificate=True, name="Certification")
    attachment = env.attachment(attachment_type, "titled")
    products = [env.product("TITLE1")]

    payload = _cert_payload(attachment, products)
    payload["title"] = "Product Certification Scheme - sanitary ware"
    payload["issuer"] = "IKRAM QA Services Sdn Bhd"

    response = env.client.post(EXTERNAL, json=payload)
    assert response.status_code == 200, response.text

    cert = (
        env.db.query(Certificate)
        .filter(Certificate.certificate_number == "04424FC")
        .first()
    )
    assert cert is not None
    assert cert.title == "Product Certification Scheme - sanitary ware"
    assert cert.issuer == "IKRAM QA Services Sdn Bhd"
    # ING-7: the raw reader output is kept for attribution, title included.
    revision = (
        env.db.query(CertificateRevision)
        .filter(CertificateRevision.id == cert.current_revision_id)
        .first()
    )
    assert (revision.extracted_json or {}).get("title") == (
        "Product Certification Scheme - sanitary ware"
    )


def test_ingest_treats_a_blank_title_as_absent(env):
    attachment_type = env.attachment_type(is_certificate=True, name="Certification")
    attachment = env.attachment(attachment_type, "blanktitle")
    products = [env.product("TITLE2")]

    payload = _cert_payload(attachment, products)
    payload["title"] = "   "

    response = env.client.post(EXTERNAL, json=payload)
    assert response.status_code == 200, response.text
    cert = (
        env.db.query(Certificate)
        .filter(Certificate.certificate_number == "04424FC")
        .first()
    )
    assert cert.title is None


# ------------------------------------------------- product-code fan-out (BL-045)
# A product code is a SUBSTRING pattern, not a key: "WC7601" names MWC7601-RL-S12,
# IBWC7601-RL-S10 and every other product carrying it. Every path used to take
# `.first()` of that match, so a certificate covered one arbitrary sibling and the
# rest of the family silently held no file at all.
def _fan_out_family(env, stem: str) -> tuple[str, list[Any]]:
    """Three products sharing one code substring, plus one that does not."""
    root = f"{MARKER}{stem}{unique_code('')[-6:]}"
    family = [
        env.product(stem, code=f"M{root}-RL-S12"),
        env.product(stem, code=f"IB{root}-RL-S10"),
        env.product(stem, code=f"{root}-PP"),
    ]
    env.product(stem, code=f"{MARKER}UNRELATED{unique_code('')[-6:]}")
    return root, family


def test_single_product_code_links_every_matching_product(env):
    attachment_type = env.attachment_type(is_certificate=False, name="Product Photos")
    attachment = env.attachment(attachment_type, "fanoutsingle")
    root, family = _fan_out_family(env, "FANS")

    response = env.client.post(
        EXTERNAL, json={"attachment_id": str(attachment.id), "product_code": root}
    )
    assert response.status_code == 200, response.text

    assert {str(r.product_id) for r in env.projection(attachment.id)} == {
        str(p.id) for p in family
    }


def test_single_product_code_answers_with_the_link_row_not_the_bulk_envelope(env):
    """The single-code form must not start answering with the BULK envelope just
    because the code now names several products - the n8n node that posts it has
    never parsed `linked`/`skipped_product_codes`. It answers with a link row.

    That row must be re-read after the commits. `db.commit()` expires the instance
    the service returned, an expired ORM row has an empty `__dict__`, and this
    route carries no `response_model` - so FastAPI encoded it as `{}` and the node
    received nothing at all.
    """
    attachment_type = env.attachment_type(is_certificate=False, name="Product Photos")
    attachment = env.attachment(attachment_type, "fanoutshape")
    root, family = _fan_out_family(env, "SHAP")

    body = env.client.post(
        EXTERNAL, json={"attachment_id": str(attachment.id), "product_code": root}
    ).json()

    assert "linked" not in body
    assert "skipped_product_codes" not in body
    assert body["attachment_id"] == str(attachment.id)
    # `order_by(product_code)` makes "the first" the same row on every call.
    first = sorted(family, key=lambda p: p.product_code)[0]
    assert body["product_id"] == str(first.id)
    # Every sibling got the file, not just the one the response names.
    assert {str(r.product_id) for r in env.projection(attachment.id)} == {
        str(p.id) for p in family
    }


def test_a_single_match_also_answers_with_a_populated_row(env):
    """The `{}` was not specific to the fan-out: one product, one link, one
    commit, and the row came back empty just the same."""
    attachment_type = env.attachment_type(is_certificate=False, name="Product Photos")
    attachment = env.attachment(attachment_type, "fanoutone")
    product = env.product("ONE")

    body = env.client.post(
        EXTERNAL,
        json={"attachment_id": str(attachment.id), "product_code": product.product_code},
    ).json()

    assert body["product_id"] == str(product.id)
    assert body["attachment_id"] == str(attachment.id)
    assert body["id"]


def test_single_product_code_that_matches_nothing_is_still_400(env):
    attachment_type = env.attachment_type(is_certificate=False, name="Product Photos")
    attachment = env.attachment(attachment_type, "fanoutmiss")

    response = env.client.post(
        EXTERNAL,
        json={"attachment_id": str(attachment.id), "product_code": f"{MARKER}NOSUCHCODE"},
    )
    assert response.status_code == 400, response.text


def test_bulk_link_links_every_product_matching_the_code(env):
    attachment_type = env.attachment_type(is_certificate=False, name="Product Photos")
    attachment = env.attachment(attachment_type, "fanoutbulk")
    root, family = _fan_out_family(env, "FANB")

    body = env.client.post(
        EXTERNAL, json={"attachment_id": str(attachment.id), "products": [root]}
    ).json()

    assert {x["product_code"] for x in body["linked"]} == {p.product_code for p in family}
    assert body["skipped_product_codes"] == []
    assert {str(r.product_id) for r in env.projection(attachment.id)} == {
        str(p.id) for p in family
    }


def test_bulk_link_reports_a_product_two_codes_both_name_as_already_linked(env):
    """Overlapping codes ("WC601" and "CWC601") reach the same product. The
    upsert in `create_product_attachment` makes the repeat harmless; the response
    says so rather than pretending the second code linked nothing."""
    attachment_type = env.attachment_type(is_certificate=False, name="Product Photos")
    attachment = env.attachment(attachment_type, "fanoutoverlap")
    stem = unique_code("")[-6:]
    narrow = f"C{MARKER}OVL{stem}"
    product = env.product("OVL", code=narrow)

    body = env.client.post(
        EXTERNAL,
        json={
            "attachment_id": str(attachment.id),
            "products": [narrow, f"{MARKER}OVL{stem}"],
        },
    ).json()

    assert [x["product_code"] for x in body["linked"]] == [narrow]
    assert body["already_linked"] == [narrow]
    assert len(env.projection(attachment.id)) == 1
    assert str(env.projection(attachment.id)[0].product_id) == str(product.id)


def test_certificate_ingest_covers_every_product_matching_the_code(env):
    """The cert path resolves codes through the same matcher, so a certificate
    filed against "WC7601" covers the whole family, not one sibling."""
    attachment_type = env.attachment_type(is_certificate=True, name="Certification")
    attachment = env.attachment(attachment_type, "fanoutcert")
    root, family = _fan_out_family(env, "FANC")

    payload = _cert_payload(attachment, [])
    payload["products"] = [root]
    response = env.client.post(EXTERNAL, json=payload)
    assert response.status_code == 200, response.text

    cert = env.db.query(Certificate).one()
    covered = {
        str(r.product_id)
        for r in env.db.query(CertificateProduct).filter(
            CertificateProduct.certificate_id == cert.id
        )
    }
    assert covered == {str(p.id) for p in family}
    assert {str(r.product_id) for r in env.projection(attachment.id)} == {
        str(p.id) for p in family
    }
