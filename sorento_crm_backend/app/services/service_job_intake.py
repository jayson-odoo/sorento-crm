"""S6 - raising a Service Job from the case that needs one.

The one place that knows a Complaint has a Site. `service_job_service` deliberately does not
(ADR-0009, AC-A6): the job is requester-agnostic, and that guarantee only survives if the
source-shaped knowledge lives somewhere else. Hence a registry keyed by source type rather
than an `if source_entity_type == "complaint"` buried in the service.

**The server reads the Site off the case; the client never sends it** (AC-B3, AC-M37). The
Site is whatever was REPORTED. A complaint routinely carries a dealer's shop in
`customer_address` and the house the fault is in as the Site, on the same row - a dealer's
owner reporting a fault in his own home is the ordinary case, not the edge one. Copying the
wrong field sends a van to a shop, and the mistake is invisible on screen because both are
real addresses. Letting the client post the address it happened to have on screen would make
that decision twice, and the second place is always the one that is wrong.

Adding a source type is one entry here plus a resolver. Nothing else in S6 changes, which is
the entire point of the polymorphic pair.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from sqlalchemy.orm import Session

from app.models.service_jobs import ServiceJob
from app.services.error_handler import AppException
from app.services.service_job_service import create_job

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SiteSnapshot:
    """The Site as the case reported it, at the moment the job was raised.

    A snapshot rather than a live read: the job holds its own copy so that editing the case
    afterwards does not silently redirect a technician who has already been told where to go.
    """

    address: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    latitude: Optional[Any] = None
    longitude: Optional[Any] = None
    place_id: Optional[str] = None


@dataclass(frozen=True)
class SourceType:
    """One kind of case a Service Job can be raised from."""

    key: str
    label: str
    load: Callable[[Session, str], Optional[Any]]
    site_of: Callable[[Any], SiteSnapshot]


def _load_complaint(db: Session, record_id: str) -> Optional[Any]:
    from app.models.complaints import Complaint

    return db.query(Complaint).filter(Complaint.id == record_id).first()


def _complaint_site(complaint: Any) -> SiteSnapshot:
    """The REPORTED site. Deliberately never `customer_address` - see the module docstring.

    Falls back to nothing rather than to the customer record. Most live complaints predate
    the Site columns and hold nothing in them; a blank site is a field CS fills in, whereas a
    confidently wrong one is a wasted van.
    """
    return SiteSnapshot(
        address=getattr(complaint, "site_address", None),
        contact_name=getattr(complaint, "site_contact_name", None)
        or getattr(complaint, "contact_person", None),
        contact_phone=getattr(complaint, "site_contact_phone", None)
        or getattr(complaint, "contact_number", None),
        latitude=getattr(complaint, "latitude", None),
        longitude=getattr(complaint, "longitude", None),
        place_id=getattr(complaint, "place_id", None),
    )


SOURCE_TYPES: Dict[str, SourceType] = {
    "complaint": SourceType(
        key="complaint",
        label="Complaint",
        load=_load_complaint,
        site_of=_complaint_site,
    ),
}


def raise_job_for_source(
    db: Session,
    *,
    source_entity_type: str,
    source_entity_id: str,
) -> ServiceJob:
    """Raise a job against a case, copying the site the case reported.

    NOT idempotent, deliberately. A revisit is a second visit rather than an edit of the
    first, and how many visits a case took is one of the few honest measures of how badly it
    went. Silently returning the existing job would erase that; the guard against
    double-raising is that the UI shows what already exists before offering the button.
    """
    source = SOURCE_TYPES.get(source_entity_type)
    if source is None:
        raise AppException(
            status_code=422,
            message=(
                f"A service job cannot be raised from '{source_entity_type}'. "
                f"Known sources: {', '.join(sorted(SOURCE_TYPES))}."
            ),
            code="service_job_source_unsupported",
        )

    record = source.load(db, source_entity_id)
    if record is None:
        raise AppException(
            status_code=404,
            message=f"{source.label} not found, so there is nothing to raise a job for.",
            code="service_job_source_not_found",
        )

    site = source.site_of(record)
    if not site.address:
        # Worth a line in the log: a job with no site is workable but somebody has to fill
        # it in, and a burst of them means an intake form is not capturing the address.
        logger.info(
            "Service job raised from %s %s with no reported site",
            source_entity_type,
            source_entity_id,
        )

    return create_job(
        db,
        source_entity_type=source.key,
        source_entity_id=source_entity_id,
        site_address=site.address,
        site_contact_name=site.contact_name,
        site_contact_phone=site.contact_phone,
        site_latitude=site.latitude,
        site_longitude=site.longitude,
        site_place_id=site.place_id,
    )


def supported_sources() -> Dict[str, str]:
    """key -> label, for anything that needs to offer the choice."""
    return {key: source.label for key, source in SOURCE_TYPES.items()}
