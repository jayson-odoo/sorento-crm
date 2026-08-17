"""``asset_service.create_from_bytes`` stamps company_id on the Attachment it
creates, via ``resolve_write_company_id(get_company_scope(db), ambiguous=None)``.

Before that stamp, ``Attachment`` never got one: ``__company_shared__ = True``
tells the generic ``before_insert`` auto-stamp to leave it alone (a shared form
attachment is legitimately company-less), so a kit asset's attachment row
landed NULL no matter which company created it. NULL is exactly what the
company-scope read predicate treats as "shared, visible everywhere" -
``company_id IS NULL OR company_id IN (scope)`` - so a kit asset uploaded
inside company A was reachable through the generic attachment surfaces from
company B's scope too. The library row (``dealer_kit.Asset``, NOT shared) was
correctly scoped the whole time; only its attachment was leaking.

These pin three things:
  1. under a single-company scope, the Attachment lands in the SAME company as
     its Asset sibling (not NULL, not a different one).
  2. under scope None (the system / all-companies principal, e.g. an X-API-Key
     call with no resolved contact), both land on the incumbent company.
  3. the actual defect: an asset created under company A is invisible to a
     generic attachment read scoped to company B.

Postgres only, on a blank scratch schema. ZZT-prefixed rows only.
"""
from __future__ import annotations

import io
import uuid

import pytest
from PIL import Image

from app.models.base import company_scope
from app.models.dealer_kit import Asset
from app.models.company import Company
from app.models.resources import Attachment
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.dealer_kit import asset_service

from tests._fake_storage import patch_storage
from tests._pg_fixture import blank_session, unique_code


def _png_bytes() -> bytes:
    """A real PNG - ``store_thumbnail`` decodes what it is given."""
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 120, 60)).save(buffer, format="PNG")
    return buffer.getvalue()


def _attachment_of(db, asset: Asset) -> Attachment:
    """Fetch the sibling attachment under an ALL-COMPANIES read.

    This is a fixture helper reading back what the test just wrote, not the
    read path under test - the assertions below inspect ``company_id``, not
    whether the row is reachable. Scoping the lookup to a single company would
    only prove what ``TestTheLeakItCloses`` proves anyway, so it stays
    unscoped here on purpose.
    """
    with company_scope(db, None):
        return db.query(Attachment).filter(Attachment.id == asset.attachment_id).one()


def _second_company(db) -> str:
    """A throwaway second company - the scratch schema seeds only Sorento."""
    company = Company(
        id=str(uuid.uuid4()),
        name=unique_code("ZZT Company B"),
        code=f"ZB{uuid.uuid4().hex[:6]}",
    )
    db.add(company)
    db.flush()
    return company.id


class TestSingleCompanyScope:
    def test_the_attachment_lands_in_the_same_company_as_its_asset(self, monkeypatch) -> None:
        with blank_session() as db:
            storage = patch_storage(monkeypatch)
            company_id = _second_company(db)

            with company_scope(db, frozenset({company_id})):
                asset = asset_service.create_from_bytes(
                    db,
                    content=_png_bytes(),
                    name=unique_code("ZZT single-scope asset"),
                    mime="image/png",
                )
                db.flush()

            attachment = _attachment_of(db, asset)

            assert asset.company_id == company_id
            assert attachment.company_id == company_id
            assert storage.objects  # sanity: the upload actually ran


class TestSystemPrincipalScope:
    def test_scope_none_stamps_both_rows_to_the_incumbent_company(self, monkeypatch) -> None:
        """Scope ``None`` is the deliberate system / all-companies principal
        (an X-API-Key call with no resolved contact). An owned write under it
        lands in the incumbent company (Sorento), matching the pre-multi-company
        DB default and the ``before_insert`` auto-stamp's own rule for Asset."""
        with blank_session() as db:
            patch_storage(monkeypatch)

            with company_scope(db, None):
                asset = asset_service.create_from_bytes(
                    db,
                    content=_png_bytes(),
                    name=unique_code("ZZT system-scope asset"),
                    mime="image/png",
                )
                db.flush()

            attachment = _attachment_of(db, asset)

            assert asset.company_id == DEFAULT_COMPANY_ID
            assert attachment.company_id == DEFAULT_COMPANY_ID


class TestTheLeakItCloses:
    def test_an_asset_from_company_a_is_invisible_to_a_generic_read_under_company_b(
        self, monkeypatch
    ) -> None:
        """The real defect. Attachments are ``__company_shared__``, so the read
        predicate is ``company_id IS NULL OR company_id IN (scope)``. Before the
        fix the attachment was NULL regardless of which company created it, so
        it satisfied every scope's predicate - a kit asset uploaded inside one
        company was reachable through the generic attachment listing from a
        completely different company's scope. Stamping a real company_id closes
        that: company B's scope no longer matches company A's row."""
        with blank_session() as db:
            patch_storage(monkeypatch)
            company_a = _second_company(db)
            company_b = _second_company(db)

            with company_scope(db, frozenset({company_a})):
                asset = asset_service.create_from_bytes(
                    db,
                    content=_png_bytes(),
                    name=unique_code("ZZT company-a asset"),
                    mime="image/png",
                )
                db.flush()
            attachment_id = asset.attachment_id

            with company_scope(db, frozenset({company_b})):
                leaked = (
                    db.query(Attachment)
                    .filter(Attachment.id == attachment_id)
                    .all()
                )

            assert leaked == [], (
                "company B's scope read company A's kit asset attachment - "
                "the company_id stamp did not close the shared-NULL leak"
            )

            # Sanity: the SAME scoped read finds it from its own company.
            with company_scope(db, frozenset({company_a})):
                own = (
                    db.query(Attachment)
                    .filter(Attachment.id == attachment_id)
                    .all()
                )
            assert [row.id for row in own] == [attachment_id]
