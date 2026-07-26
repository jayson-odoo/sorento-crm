"""Public (unauthenticated) catalogue page rendering.

This is what a dealer or a consumer opens when they follow a shared link. It
lives under ``/api/v1/public`` rather than the Dealer Kit router because that
router sits behind the module guard, which needs a principal - and a reader has
none.

**Why the URL carries a company code.** ``dealer_kit.page.slug`` is unique PER
COMPANY, on purpose: Sorento and Mocha may each publish a "bathroom-2026". A
bare ``/c/{slug}`` therefore cannot resolve deterministically the moment a
second company exists, and resolving it by "whichever one matches" would be a
cross-company leak - precisely what the isolation work exists to prevent. So
the address is ``/c/{company_code}/{slug}``: the code (``SRT``, ``MCH``) is
short, stable, already unique, human-readable, and not a UUID.

**How scope works here.** An unauthenticated request resolves to the fail-closed
UNSET scope, under which every owned read returns zero rows. This route resolves
the company from the code FIRST, then reads inside a scope pinned to exactly
that one company. The lookup can never span companies, and an unknown code is
indistinguishable from an unpublished page: both are 404.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.base import company_scope
from app.models.company import Company
from app.schemas.dealer_kit import PublicPage
from app.services.dealer_kit import page_service as svc
from app.services.error_handler import AppException

router = APIRouter()


@router.get("/{company_code}/{slug}", response_model=PublicPage)
def read_published_page(company_code: str, slug: str, db: Session = Depends(get_db)):
    company = (
        db.query(Company)
        .filter(
            func.lower(Company.code) == company_code.strip().lower(),
            Company.is_active.is_(True),
        )
        .first()
    )
    if company is None:
        # Deliberately the same answer as "no such page": whether a company
        # exists is not something an anonymous reader gets to probe.
        raise AppException(status_code=404, message="Page not found")

    with company_scope(db, frozenset({company.id})):
        live = svc.published_doc(db, slug.strip().lower())

    return PublicPage(name=live["name"], slug=live["slug"], doc=live["doc"])
