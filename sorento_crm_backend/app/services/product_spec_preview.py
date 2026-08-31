"""Preview: what a DRAFT rule list would change on the catalogue, before it is saved.

Same shape as `product_spec_rederive.py` on purpose - a background thread with a
status anyone can poll - because that plumbing already exists and a preview needs
nothing more from it: no new table, no queue, no worker restart (AC-B.2). The only
difference is scope: `reread-catalogue` re-reads everything with the RULES THAT ARE
LIVE; this compares one key's stored values against what an UNSAVED draft would read,
and never writes anything.

Jobs are in-process state, like the rederive run: they are progress for whoever
pressed "Preview", not a record. Kept for the last `_MAX_JOBS` runs so an old `jobId`
404s instead of resurrecting a stale result.
"""
from __future__ import annotations

import logging
import threading
import uuid
from collections import OrderedDict

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_JOBS_LOCK = threading.Lock()
_JOBS: "OrderedDict[str, dict]" = OrderedDict()
_MAX_JOBS = 20


def _remember(job_id: str, state: dict) -> None:
    with _JOBS_LOCK:
        _JOBS[job_id] = state
        while len(_JOBS) > _MAX_JOBS:
            _JOBS.popitem(last=False)


def get(job_id: str) -> dict | None:
    """`None` for an unknown job id - the route turns that into a 404."""
    with _JOBS_LOCK:
        state = _JOBS.get(job_id)
        return dict(state) if state is not None else None


def _compare(db: Session, spec_key: str, rules: list[dict]) -> dict:
    from app.models.base import company_scope
    from app.models.product import Product, ProductCategory
    from app.models.product_spec import ProductSpecifications
    from app.services.product_spec_derivation import (
        configured_max_values,
        configured_rules,
        configured_scopes,
        derive,
    )
    from app.services.product_spec_write import AUTHORED_SOURCES

    rules_by_key = dict(configured_rules(db))
    rules_by_key[spec_key] = rules
    scopes_by_key = configured_scopes(db)
    max_values = configured_max_values(db)

    # ALL-COMPANIES, same reason `derive_product_specs` runs under it: a product code
    # exists once per company, and a session with no scope set sees NONE of them
    # (`CompanyScopedMixin` fails closed) - which reads as "nothing to compare" rather
    # than the missing scope it actually is.
    with company_scope(db, None):
        rows = (
            db.query(Product, ProductCategory, ProductSpecifications)
            .outerjoin(ProductCategory, ProductCategory.id == Product.category_id)
            .outerjoin(ProductSpecifications, ProductSpecifications.product_id == Product.id)
            .filter(Product.is_active.is_(True))
            .order_by(Product.product_code)
            .all()
        )

    changed = added = removed = unchanged = 0
    sample: list[dict] = []
    for product, category, spec in rows:
        existing_values = (spec.values if spec else {}) or {}
        existing_provenance = (spec.provenance if spec else {}) or {}

        # A person's own answer is not derived, so a draft rule cannot "change" it -
        # counting it either way would report a number nobody could act on: saving the
        # draft will not touch this row (AUTHORED_SOURCES, product_spec_write).
        provenance = existing_provenance.get(spec_key) or {}
        if provenance.get("source") in AUTHORED_SOURCES:
            continue

        out = derive(
            product,
            category,
            rules_by_key=rules_by_key,
            scopes_by_key=scopes_by_key,
            max_values=max_values,
        )
        after = (out.values.get(spec_key) or {}).get("value")
        before = (existing_values.get(spec_key) or {}).get("value")

        if before == after:
            unchanged += 1
            continue
        if before is None:
            added += 1
        elif after is None:
            removed += 1
        else:
            changed += 1
        if len(sample) < 20:
            sample.append({"code": product.product_code, "before": before, "after": after})

    return {
        "changed": changed,
        "added": added,
        "removed": removed,
        "unchanged": unchanged,
        "sample": sample,
    }


def _run(job_id: str, spec_key: str, rules: list[dict]) -> None:
    from app.database import SessionLocal

    try:
        with SessionLocal() as db:
            result = _compare(db, spec_key, rules)
        _remember(job_id, {"status": "done", **result})
        logger.info("spec preview %s (%s) finished: %s", job_id, spec_key, result)
    except Exception as exc:  # noqa: BLE001 - reported to the caller, never swallowed
        logger.exception("spec preview %s (%s) failed", job_id, spec_key)
        _remember(job_id, {"status": "failed", "error": str(exc)})


def start(spec_key: str, rules: list[dict]) -> str:
    """Kick off a preview run. Returns the job id to poll."""
    job_id = uuid.uuid4().hex[:12]
    _remember(job_id, {"status": "pending"})
    threading.Thread(target=_run, args=(job_id, spec_key, rules), daemon=True).start()
    return job_id


def run_inline(job_id: str, spec_key: str, rules: list[dict], db: Session) -> None:
    """Run synchronously in the caller's own session. Tests use this - it does the
    same work as `_run` above, without the thread and without sleep-polling a status
    dict from the test's own connection.
    """
    result = _compare(db, spec_key, rules)
    _remember(job_id, {"status": "done", **result})
