"""CERT-LINK-CLEANUP: read certificate PDFs once and stamp each link's verdict (queue `flyer_read`).

Queued by `POST /master-data/certificate-links/check` (`certificate_link_report_service.queue_pending`).
Runs with the scope OFF (`set_company_scope(db, None)`, as `flyer_read_tasks` does): UNSET is
fail-closed and would read zero rows. The ids were already chosen inside the requester's scope, and
a verdict is a fact about the PDF, not about who asked.
"""
from __future__ import annotations

import logging
from typing import Sequence

logger = logging.getLogger(__name__)


def check_certificate_links(certificate_ids: Sequence[str]) -> dict:
    import app.database as database
    from app.services import certificate_link_report_service as report
    from app.services.company_scope import set_company_scope

    with database.SessionLocal() as db:
        set_company_scope(db, None)
        result = report.check_certificates(db, certificate_ids)
    logger.info("certificate link check: %s", result)
    return result
