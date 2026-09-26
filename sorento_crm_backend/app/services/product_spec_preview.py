"""Preview: what a DRAFT rule list would change on the catalogue, before it is saved.

Same shape as `product_spec_rederive.py` on purpose - a background thread with a
status anyone can poll - because that plumbing already exists and a preview needs
nothing more from it: no new table, no queue, no worker restart (AC-B.2). The only
difference is scope: `reread-catalogue` re-reads everything with the RULES THAT ARE
LIVE; this compares one key's stored values against what an UNSAVED draft would read,
and never writes anything.

Jobs are in-process state, like the rederive run: they are progress for whoever
pressed "Preview", not a record. Kept for the last `_MAX_JOBS` runs so an old `jobId`
404s instead of resurrecting a stale result. Only one may run at a time (S4/AC-B.2) -
the same guard `product_spec_rederive.start()` runs, because a derivation pass over
the whole catalogue is expensive enough that a second one alongside the first serves
nobody.
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

_RUNNING_LOCK = threading.Lock()
_RUNNING_JOB_ID: str | None = None

# Paged over `product_code` rather than `.all()`-ed in one shot: the whole catalogue
# is ~23,000 rows joined three ways, and holding every one of them in memory at once
# is the only thing this module needed FROM `reread-catalogue`'s plumbing that it did
# not already copy.
_PAGE_SIZE = 500


def _remember(job_id: str, state: dict) -> None:
    with _JOBS_LOCK:
        _JOBS[job_id] = state
        while len(_JOBS) > _MAX_JOBS:
            _JOBS.popitem(last=False)


def get(job_id: str) -> dict | None:
    """`None` for an unknown job id - the route turns that into a 404.

    Carries `spec_key`, which the route strips before it reaches a client: it exists
    so `GET .../preview/{job_id}` can refuse a job that belongs to a different key,
    not to publish it a second time.
    """
    with _JOBS_LOCK:
        state = _JOBS.get(job_id)
        return dict(state) if state is not None else None


def _reading_keys(
    spec_key: str, rules_by_key: dict[str, list[dict]], scopes_by_key: dict[str, dict]
) -> set[str]:
    """The keys whose rules decide `spec_key`: itself, and every key its Only when or its
    scope reads, followed through. Everything else in the catalogue's rules cannot move
    this key's value, so it is not run - which is what lets a save compare the whole
    catalogue for one key inside the request."""
    from app.services.product_spec_rules import gate_keys

    wanted: set[str] = set()
    pending = [spec_key]
    while pending:
        key = pending.pop()
        if key in wanted:
            continue
        wanted.add(key)
        pending.extend(gate_keys({key: rules_by_key.get(key) or []}))
        pending.extend((scopes_by_key.get(key) or {}).keys())
    return wanted


def readings_for_key(
    db: Session,
    spec_key: str,
    *,
    rules_by_key: dict[str, list[dict]],
    scopes_by_key: dict[str, dict],
    max_values: dict[str, float],
):
    """Every active product's stored `spec_key` value beside what the given rules read,
    as `{"code", "before", "after"}` - the one comparison both "See what would change"
    (a draft) and a saved rule's re-read (AC-S1.16, D10) make, so the products a save
    re-reads are exactly the ones the preview counted as changing (`before != after`).

    A person's own answer is skipped: it is not derived, so no rule can change it
    (AUTHORED_SOURCES, product_spec_write). Yields one entry per product row, so a code
    held by two companies can appear twice.
    """
    import sqlalchemy as sa
    from app.models.base import company_scope
    from app.models.product import Product, ProductCategory
    from app.models.product_spec import ProductSpecifications
    from app.services.product_spec_derivation import derive
    from app.services.product_spec_write import AUTHORED_SOURCES

    keys = _reading_keys(spec_key, rules_by_key, scopes_by_key)
    reading_rules = {key: rules_by_key[key] for key in rules_by_key if key in keys}

    # ALL-COMPANIES, same reason `derive_product_specs` runs under it: a product code
    # exists once per company, and a session with no scope set sees NONE of them
    # (`CompanyScopedMixin` fails closed) - which reads as "nothing to compare" rather
    # than the missing scope it actually is.
    with company_scope(db, None):
        base = (
            db.query(Product, ProductCategory, ProductSpecifications)
            .outerjoin(ProductCategory, ProductCategory.id == Product.category_id)
            .outerjoin(ProductSpecifications, ProductSpecifications.product_id == Product.id)
            .filter(Product.is_active.is_(True))
        )

        # Keyset paging on `(product_code, id)`, not `product_code` alone: a code is
        # unique only WITHIN a company, so the same code can appear on adjacent rows
        # from different companies, and a cursor on `product_code` alone would skip
        # every row tied for the last code on a page (the classic tie bug - see
        # LESSONS-LEARNT's ordering-ties entry). `id` breaks the tie deterministically.
        cursor: tuple[str, str] | None = None
        while True:
            page_query = base
            if cursor is not None:
                page_query = page_query.filter(
                    sa.tuple_(Product.product_code, Product.id) > sa.tuple_(*cursor)
                )
            page = (
                page_query.order_by(Product.product_code, Product.id)
                .limit(_PAGE_SIZE)
                .all()
            )
            if not page:
                break

            for product, category, spec in page:
                existing_values = (spec.values if spec else {}) or {}
                existing_provenance = (spec.provenance if spec else {}) or {}
                provenance = existing_provenance.get(spec_key) or {}
                if provenance.get("source") in AUTHORED_SOURCES:
                    continue

                out = derive(
                    product,
                    category,
                    rules_by_key=reading_rules,
                    scopes_by_key=scopes_by_key,
                    max_values=max_values,
                )
                after = (out.values.get(spec_key) or {}).get("value")
                before = (existing_values.get(spec_key) or {}).get("value")
                yield {"code": product.product_code, "before": before, "after": after}

            last_product = page[-1][0]
            cursor = (last_product.product_code, last_product.id)
            if len(page) < _PAGE_SIZE:
                break


def _compare(db: Session, spec_key: str, rules: list[dict]) -> dict:
    from app.services.product_spec_derivation import (
        configured_max_values,
        configured_rules,
        configured_scopes,
    )

    rules_by_key = dict(configured_rules(db))
    rules_by_key[spec_key] = rules

    changed = added = removed = unchanged = 0
    sample: list[dict] = []
    for row in readings_for_key(
        db,
        spec_key,
        rules_by_key=rules_by_key,
        scopes_by_key=configured_scopes(db),
        max_values=configured_max_values(db),
    ):
        before, after = row["before"], row["after"]
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
            sample.append(row)

    return {
        "changed": changed,
        "added": added,
        "removed": removed,
        "unchanged": unchanged,
        "sample": sample,
    }


def _run_job(job_id: str, spec_key: str, rules: list[dict], db: Session | None = None) -> None:
    """Run the comparison and remember the result.

    The thread's own target (`db=None` opens a fresh `SessionLocal()` - a real
    connection this test's scratch-schema data, rolled back on a different
    connection, would be invisible to) AND what a test calls directly with its OWN
    session instead of polling a thread. One function either way, so a test proves
    what the thread actually runs rather than a hand-written stand-in for it.
    """
    global _RUNNING_JOB_ID
    from app.database import SessionLocal

    try:
        if db is not None:
            result = _compare(db, spec_key, rules)
        else:
            with SessionLocal() as owned:
                result = _compare(owned, spec_key, rules)
        _remember(job_id, {"status": "done", "spec_key": spec_key, **result})
        logger.info("spec preview %s (%s) finished: %s", job_id, spec_key, result)
    except Exception as exc:  # noqa: BLE001 - reported to the caller, never swallowed
        logger.exception("spec preview %s (%s) failed", job_id, spec_key)
        _remember(job_id, {"status": "failed", "spec_key": spec_key, "error": str(exc)})
    finally:
        with _RUNNING_LOCK:
            if _RUNNING_JOB_ID == job_id:
                _RUNNING_JOB_ID = None


def start(spec_key: str, rules: list[dict]) -> str:
    """Kick off a preview run. Returns the job id to poll.

    Refuses a second run while one is already in flight - 409 `spec_preview_running`,
    the running job's id in `detail` - the same single-run guard
    `product_spec_rederive.start()` already carries.
    """
    from app.services.error_handler import AppException

    global _RUNNING_JOB_ID
    with _RUNNING_LOCK:
        if _RUNNING_JOB_ID is not None:
            raise AppException(
                status_code=409,
                message="A preview is already running. Wait for it to finish.",
                code="spec_preview_running",
                detail=_RUNNING_JOB_ID,
            )
        job_id = uuid.uuid4().hex[:12]
        _RUNNING_JOB_ID = job_id

    _remember(job_id, {"status": "pending", "spec_key": spec_key})
    threading.Thread(target=_run_job, args=(job_id, spec_key, rules), daemon=True).start()
    return job_id
