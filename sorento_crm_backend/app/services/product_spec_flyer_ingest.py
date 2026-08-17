"""What a whole flyer says about the products it names, as a reviewable batch (PR 5).

One upload, two consumers. The dealer kit already reads a flyer into cards and matches
those cards to products; this module asks the second question about the same reading -
what does the paper SAY about each product's specifications, and how does that stand
against what the master holds today.

Nothing here writes a spec value. The write is `product_spec_write.apply_spec_values`,
the one choke point, called once per product from `apply_batch` and only for the rows a
person ticked. Everything before that is proposals: stored, classified, and refusable.

Four things it deliberately does NOT do:

  * **It does not read the PDF.** The reading is the dealer kit's, unchanged, and this
    runs off the stored reading (`report_for` + the cards' printed lines). A second
    reader would be a second answer to "what does this flyer print".
  * **It does not decide `kind` itself.** `classify_spec_proposal` is shared with the
    pasted-text panel, so a merchandiser reading one card and a merchandiser reading a
    whole flyer are told the same thing about the same product.
  * **It does not trust the snapshot at apply time.** Every ticked row is re-classified
    against the LIVE spec row first, so a batch proposed yesterday cannot overwrite
    what somebody set this morning (AC-C.2).
  * **It does not raise from the job.** The batch row is the record: `proposed` or
    `failed` with the reason, exactly the shape `read_flyer` follows.

Plan: `documentation/plans/master-data/PLAN-flyer-spec-ingestion.md` section 3.2.
UAC: `flyer-spec-ingestion-acceptance-criteria.md` sections A, B and C.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

import app.services.product_spec_write as spec_write
from app.models.dealer_kit import FlyerReadingRecord
from app.models.product import Product
from app.models.product_spec import (
    ProductSpecFlyerBatch,
    ProductSpecFlyerProposal,
    ProductSpecRegistry,
    ProductSpecifications,
)
from app.models.user import User
from app.services.dealer_kit import flyer_reading_service as flyer_svc
from app.services.dealer_kit.dimension_apply_service import (
    ALREADY_MATCHES,
    CONFLICT_NOT_CONFIRMED,
    PRODUCT_NOT_FOUND,
)
from app.services.error_handler import AppException
from app.services.product_spec_derivation import (
    configured_rules,
    configured_scopes,
    propose_from_text,
)
from app.services.product_spec_extract import _in_scope, classify_spec_proposal
from app.services.product_spec_registry import active_registry, value_for_registry

logger = logging.getLogger(__name__)

# Where a proposal pass is. `none` is not one of these: it is what the per-reading GET
# answers for a reading nobody has proposed from, and it is never stored.
PROPOSING = "proposing"
PROPOSED = "proposed"
FAILED = "failed"

# How a row ended, when somebody has decided about it. The first three are shared with
# `dimension_apply_service` because they mean exactly what they mean there - a row the
# master already agrees with, a value nobody confirmed overwriting, a code that is gone.
APPLIED = "applied"
BAD_VALUE = "product_spec_bad_value"
NOT_IN_BATCH = "not_in_batch"

# A ceiling on one apply. The real flyer prints 998 codes; at a handful of keys each
# this clears the largest honest selection several times over while still refusing a
# client that has decided to post its whole catalogue.
MAX_ROWS = 5000

# 15 minutes, matching the read's own ceiling. The pass is one report plus a rule pass
# per matched code, so this is a bound on a job that has gone wrong rather than a budget.
FLYER_SPEC_JOB_TIMEOUT = 900

# Where a product whose pages nobody recorded sorts. Products are ordered by the page
# they are printed on, so a product with no page has to go somewhere: last, because the
# reviewer is working through the paper in order and a card that names no page is not
# the first thing they turn to. Zero would have put it AHEAD of page 1.
_NO_PAGE = 10**9


def _now() -> datetime:
    """Naive UTC, matching every other timestamp column in this system."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --------------------------------------------------------------------------- #
# starting a pass
# --------------------------------------------------------------------------- #
def _enqueue(batch: ProductSpecFlyerBatch) -> Optional[str]:
    """Hand the pass to the worker. Returns the RQ job id.

    **The one seam the tests patch**, and deliberately thin for the same reason
    `flyer_reading_service._enqueue` is: a test replaces it with a recorder and then
    runs the job inline on its own session, exercising everything around it for real.

    Both imports are inside the function. The task module pulls in `SessionLocal` and
    `queue_service` pulls in Redis, and neither belongs in every module that happens to
    touch a flyer. Same queue as the read: no new worker configuration.
    """
    from app.services.queue_service import enqueue_job
    from app.tasks.flyer_spec_propose_tasks import propose_specs_for_flyer

    job = enqueue_job(
        propose_specs_for_flyer,
        str(batch.id),
        queue_name=flyer_svc.FLYER_READ_QUEUE,
        job_timeout=FLYER_SPEC_JOB_TIMEOUT,
    )
    return getattr(job, "id", None)


def batch_for(db: Session, record: FlyerReadingRecord) -> Optional[ProductSpecFlyerBatch]:
    """This reading's batch, or nothing. One batch per reading (AC-A.5)."""
    return (
        db.query(ProductSpecFlyerBatch)
        .filter(ProductSpecFlyerBatch.flyer_reading_id == record.id)
        .first()
    )


def list_batches(db: Session) -> list[tuple[ProductSpecFlyerBatch, FlyerReadingRecord]]:
    """Every batch the caller's scope can see, newest first, each with its reading.

    The reading comes back with it because the list screen names the flyer and the day
    it was read, and a second call per row to get them would be one query per line.

    `id` breaks ties: Postgres `now()` is transaction time, so two batches written
    inside one transaction share a timestamp and would otherwise come back in whatever
    order the planner felt like.
    """
    return (
        db.query(ProductSpecFlyerBatch, FlyerReadingRecord)
        .join(
            FlyerReadingRecord,
            FlyerReadingRecord.id == ProductSpecFlyerBatch.flyer_reading_id,
        )
        .order_by(
            ProductSpecFlyerBatch.created_at.desc(), ProductSpecFlyerBatch.id.desc()
        )
        .all()
    )


def _wipe_proposals(db: Session, batch_id: str) -> None:
    """Take the batch's rows away.

    Called from both halves of a re-propose on purpose: `start_batch` so nothing stale
    is reachable while the new pass runs, and `run_propose` so a job that runs twice
    (a retry, an operator re-queueing) recomputes rather than accumulates.
    """
    db.query(ProductSpecFlyerProposal).filter(
        ProductSpecFlyerProposal.batch_id == batch_id
    ).delete(synchronize_session=False)


def _reset(batch: ProductSpecFlyerBatch) -> None:
    """Put a settled batch back to the start of a fresh pass.

    The applied stamps go too, and that is not carelessness: they described rows that
    are being deleted, so keeping them would leave a batch claiming 12 applied rows it
    can no longer name. The record of what was actually written survives where it
    belongs - on the spec provenance, with the printed words as its evidence.
    """
    batch.status = PROPOSING
    batch.error_message = None
    batch.finished_at = None
    batch.product_count = 0
    batch.proposal_count = 0
    batch.new_count = 0
    batch.change_count = 0
    batch.conflict_count = 0
    batch.unchanged_count = 0
    batch.suppressed_count = 0
    batch.applied_count = 0
    batch.applied_at = None
    batch.applied_by = None


def start_batch(
    db: Session, record: FlyerReadingRecord, *, user_id: Optional[str] = None
) -> ProductSpecFlyerBatch:
    """Ask for a proposal pass over this reading, and queue it.

    Refuses a reading that has not been read (409 `FLYER_NOT_READ_YET`, the same words
    the seed and the sizes apply use) and a pass that is already running (409
    `FLYER_SPEC_PROPOSING`) - the second because two passes over one reading would race
    to write the same rows and one of them would lose without saying so.

    Anything else re-proposes: the old rows go and the pass runs against the master as
    it is NOW (AC-A.5). That is the point of pressing it again.

    Redis being down must not read as "your flyer is being proposed", so a failed
    enqueue marks the batch `failed` with the queue named, exactly as the read does.
    """
    flyer_svc.assert_read(record)

    batch = batch_for(db, record)
    if batch is not None and batch.status == PROPOSING:
        raise AppException(
            status_code=409,
            message=(
                "This flyer is already being read for specifications. "
                "Wait for it to finish, then propose again."
            ),
            code="FLYER_SPEC_PROPOSING",
        )

    if batch is None:
        batch = ProductSpecFlyerBatch(
            id=str(uuid.uuid4()),
            flyer_reading_id=record.id,
            status=PROPOSING,
        )
        # The batch belongs where the reading does. Copied rather than left to the
        # auto-stamp so a worker or an unscoped caller cannot land it elsewhere.
        if getattr(record, "company_id", None):
            batch.company_id = record.company_id
        db.add(batch)
    else:
        _wipe_proposals(db, batch.id)
        _reset(batch)
        db.add(batch)

    batch.created_by = user_id
    batch.created_at = _now()
    db.commit()
    db.refresh(batch)

    try:
        batch.job_id = _enqueue(batch)
    except Exception as exc:  # noqa: BLE001 - the queue's problem, said in words
        logger.exception("Flyer spec batch %s could not be queued", batch.id)
        batch.status = FAILED
        batch.error_message = f"Could not queue the specification pass: {exc}"
        batch.finished_at = _now()

    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


# --------------------------------------------------------------------------- #
# the pass itself
# --------------------------------------------------------------------------- #
def _card_text(record: FlyerReadingRecord) -> dict[str, str]:
    """`{code: every word printed under it}`, over the whole document.

    A code printed on two pages contributes BOTH cards: it is one product, and the
    flyer states its material on one spread and its size on the other often enough
    that reading only the first card loses half the answer.
    """
    texts: dict[str, list[str]] = {}
    for page in flyer_svc.to_reading(record).pages:
        for card in page.cards:
            texts.setdefault(card.code, []).extend(card.lines or [])
    return {code: " ".join(lines).strip() for code, lines in texts.items()}


def _stored(db: Session, product_ids: list[str]) -> dict[str, ProductSpecifications]:
    """Every matched product's spec row, in one query rather than one per product."""
    if not product_ids:
        return {}
    return {
        spec.product_id: spec
        for spec in db.query(ProductSpecifications)
        .filter(ProductSpecifications.product_id.in_(product_ids))
        .all()
    }


def _proposals_for_product(
    *,
    text: str,
    code: str,
    stored_values: dict,
    stored_provenance: dict,
    index: dict[str, ProductSpecRegistry],
    rules_by_key: dict,
    scopes_by_key: dict,
) -> list[dict]:
    """What this card says about this product, classified. Reads nothing, writes nothing.

    The three filters, in order, and each with its own reason:

      * a `code`-origin hit was read off the product's OWN code, which derivation reads
        on every run anyway - proposing it would present something the paper never said
        as a reading of the paper (PR 4's rule);
      * a key the registry does not define cannot be rendered, weighted or searched, so
        it is not a proposal, it is a typo with a value attached;
      * a key this product's class cannot carry is dropped by derivation's own
        `_apply_scope` gate, evaluated against what the PRODUCT holds - never against
        what the card says, because a card for a toilet seat states nothing about the
        class and a bundle card names its neighbour's.
    """
    hits = propose_from_text(
        text, code, rules_by_key=rules_by_key, scopes_by_key=scopes_by_key
    )

    candidates: list[dict] = []
    evidence: dict[str, str] = {}
    for hit in hits:
        key = hit["spec_key"]
        if hit.get("origin") == "code":
            continue
        if key not in index or key in evidence:
            continue
        evidence[key] = hit.get("evidence") or ""
        candidates.append({"key": key, "value": hit["value"]})

    candidates = _in_scope(candidates, stored_values, stored_provenance, scopes_by_key)

    out: list[dict] = []
    for entry in sorted(candidates, key=lambda item: item["key"]):
        key = entry["key"]
        row = index[key]
        stored_entry = stored_values.get(key)
        stored_stamp = stored_provenance.get(key) or {}

        proposed_entry: dict = {"value": entry["value"]}
        if row.unit:
            proposed_entry["unit"] = row.unit

        out.append(
            {
                "spec_key": key,
                "value": entry["value"],
                "unit": row.unit or None,
                "evidence": evidence.get(key, ""),
                "kind": classify_spec_proposal(
                    proposed_entry, stored_entry, stored_stamp, key
                ),
                "stored_value": _entry_field(stored_entry, "value"),
                "stored_unit": _entry_field(stored_entry, "unit"),
                "stored_source": stored_stamp.get("source") or None,
            }
        )
    return out


def _entry_field(entry, name: str):
    if isinstance(entry, dict):
        return entry.get(name)
    return entry if name == "value" else None


def run_propose(db: Session, batch_id: str) -> dict:
    """Compute the whole batch. The job body, and it never raises.

    The request that asked for this returned 202 and is long gone, so the row is the
    record: every way out of here leaves the batch `proposed` or `failed` with the
    reason in words a merchandiser can read (AC-A.4).

    A reading that vanished mid-pass is not an error. Deleting it cascades the batch
    away, so there is nothing left to write to and nothing to say.
    """
    batch = (
        db.query(ProductSpecFlyerBatch)
        .filter(ProductSpecFlyerBatch.id == batch_id)
        .first()
    )
    if batch is None:
        logger.info("propose_specs: batch %s is gone; nothing to do", batch_id)
        return {"batch_id": str(batch_id), "status": "gone"}

    try:
        record = (
            db.query(FlyerReadingRecord)
            .filter(FlyerReadingRecord.id == batch.flyer_reading_id)
            .first()
        )
        if record is None:
            logger.info(
                "propose_specs: reading behind batch %s is gone; nothing to do", batch_id
            )
            return {"batch_id": str(batch_id), "status": "gone"}

        counts = _propose(db, batch, record)
        batch.status = PROPOSED
        batch.error_message = None
        batch.finished_at = _now()
        for name, value in counts.items():
            setattr(batch, name, value)
        db.add(batch)
        db.commit()
        logger.info(
            "propose_specs: batch %s proposed %s values across %s products",
            batch_id,
            counts["proposal_count"],
            counts["product_count"],
        )
        return {"batch_id": str(batch_id), "status": PROPOSED, **counts}

    except Exception as exc:  # noqa: BLE001 - the row records it, the queue survives
        logger.exception("propose_specs: batch %s failed", batch_id)
        return _mark_failed(db, batch_id, f"The flyer could not be read for specifications: {exc}")


def _propose(
    db: Session, batch: ProductSpecFlyerBatch, record: FlyerReadingRecord
) -> dict[str, int]:
    """Every matched product's proposals, written as rows. Returns the counts."""
    _wipe_proposals(db, batch.id)
    db.flush()

    report = flyer_svc.report_for(db, record)
    matched = list(report.matched)
    texts = _card_text(record)

    # Loaded ONCE for the whole pass, not once per code: the real flyer matches
    # hundreds of products and these are three queries either way.
    rules_by_key = configured_rules(db)
    scopes_by_key = configured_scopes(db)
    index = {row.spec_key: row for row in active_registry(db)}
    stored = _stored(db, [entry.product_id for entry in matched])

    rows: list[ProductSpecFlyerProposal] = []
    counts = {kind: 0 for kind in ("new", "change", "conflict", "unchanged", "suppressed")}
    products = set()

    for entry in matched:
        text = texts.get(entry.code, "")
        if not text:
            continue
        spec = stored.get(entry.product_id)
        proposals = _proposals_for_product(
            text=text,
            code=entry.product_code or entry.code,
            stored_values=dict((spec.values if spec else None) or {}),
            stored_provenance=dict((spec.provenance if spec else None) or {}),
            index=index,
            rules_by_key=rules_by_key,
            scopes_by_key=scopes_by_key,
        )
        if not proposals:
            continue
        products.add(entry.product_id)
        for proposal in proposals:
            counts[proposal["kind"]] += 1
            rows.append(
                ProductSpecFlyerProposal(
                    id=str(uuid.uuid4()),
                    batch_id=batch.id,
                    product_id=entry.product_id,
                    product_code=entry.product_code,
                    pages=list(entry.pages),
                    **proposal,
                )
            )

    db.add_all(rows)
    return {
        "product_count": len(products),
        "proposal_count": len(rows),
        "new_count": counts["new"],
        "change_count": counts["change"],
        "conflict_count": counts["conflict"],
        "unchanged_count": counts["unchanged"],
        "suppressed_count": counts["suppressed"],
    }


def _mark_failed(db: Session, batch_id: str, message: str) -> dict:
    """Write the failure onto the row, whatever state the attempt left behind.

    The rollback is first and it is load-bearing: a failure part way through the pass
    can leave half the proposal rows in the session, and committing the status on top
    of them would persist a `failed` batch carrying rows nobody computed.
    """
    try:
        db.rollback()
    except Exception:  # noqa: BLE001
        logger.exception("propose_specs: rollback before failing %s did not work", batch_id)

    try:
        batch = (
            db.query(ProductSpecFlyerBatch)
            .filter(ProductSpecFlyerBatch.id == batch_id)
            .first()
        )
    except Exception:  # noqa: BLE001 - the database is gone; the queue still must not be
        logger.exception("propose_specs: batch %s could not be re-read to fail it", batch_id)
        return {"batch_id": str(batch_id), "status": "unrecorded", "error": message}

    if batch is None:
        return {"batch_id": str(batch_id), "status": "gone"}

    batch.status = FAILED
    batch.error_message = message
    batch.finished_at = _now()
    try:
        db.add(batch)
        db.commit()
    except Exception:  # noqa: BLE001 - nothing left to do but say so in the log
        logger.exception("propose_specs: could not mark batch %s failed", batch_id)
    return {"batch_id": str(batch_id), "status": FAILED, "error": message}


# --------------------------------------------------------------------------- #
# reading the batch back
# --------------------------------------------------------------------------- #
def grouped_proposals(db: Session, batch: ProductSpecFlyerBatch) -> list[dict]:
    """The batch's rows, grouped by product, in the order the flyer prints them.

    Page order rather than code order because the reviewer is holding the paper: the
    third product on the screen should be the third product they turn to. The code
    breaks ties within a page, so two products on one spread stay in a stable order.

    The registry is read once for the label and the type of each key. They are on the
    wire (AC-B.1) because the review component renders the value itself, and a screen
    that had to look up "what is dim_length" per row would be a second call per row.
    """
    rows = (
        db.query(ProductSpecFlyerProposal)
        .filter(ProductSpecFlyerProposal.batch_id == batch.id)
        .order_by(ProductSpecFlyerProposal.spec_key)
        .all()
    )
    if not rows:
        return []

    index = {row.spec_key: row for row in active_registry(db)}
    names = {
        product.id: product.product_name
        for product in db.query(Product)
        .filter(Product.id.in_({row.product_id for row in rows}))
        .all()
    }

    groups: dict[str, dict] = {}
    for row in rows:
        group = groups.get(row.product_id)
        if group is None:
            group = {
                "product_id": row.product_id,
                "product_code": row.product_code,
                "product_name": names.get(row.product_id) or row.product_code,
                "pages": list(row.pages or []),
                "proposals": [],
            }
            groups[row.product_id] = group
        registry_row = index.get(row.spec_key)
        group["proposals"].append(
            {
                "id": row.id,
                "spec_key": row.spec_key,
                "label": (registry_row.label if registry_row else None) or row.spec_key,
                "data_type": (registry_row.data_type if registry_row else None) or "enum",
                "value": row.value,
                "unit": row.unit,
                "evidence": row.evidence or "",
                "kind": row.kind,
                "stored_value": row.stored_value,
                "stored_unit": row.stored_unit,
                "stored_source": row.stored_source,
                "outcome": row.outcome,
                "applied_at": row.applied_at,
            }
        )

    return sorted(
        groups.values(),
        key=lambda group: (
            min(group["pages"]) if group["pages"] else _NO_PAGE,
            group["product_code"],
        ),
    )


def user_names(db: Session, user_ids: list[Optional[str]]) -> dict[str, str]:
    """`{user id: what to call them}` for the ids a batch carries.

    Resolved here rather than on the wire as ids, because no uuid reaches the UI
    (AC-B.3) and "proposed by" is a name a reviewer recognises. The email is the
    fallback for a user row with no name, which is still something a person can read.
    """
    wanted = {str(user_id) for user_id in user_ids if user_id}
    if not wanted:
        return {}
    return {
        user.id: (user.name or user.email or "")
        for user in db.query(User).filter(User.id.in_(wanted)).all()
    }


# --------------------------------------------------------------------------- #
# applying what was ticked
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AppliedSpec:
    """One row that is now on the product, named the way the reviewer ticked it."""

    proposal_id: str
    product_code: str
    spec_key: str
    value: Any


@dataclass(frozen=True)
class RefusedSpec:
    """One row that was ticked and not written, and why.

    `message` is written for a person reading a table, not for a log: "conflict" alone
    leaves a reviewer with no way to tell a refusal from a bug.
    """

    proposal_id: str
    product_code: str
    spec_key: str
    reason: str
    message: str


@dataclass(frozen=True)
class ApplyResult:
    applied: list[AppliedSpec] = field(default_factory=list)
    refused: list[RefusedSpec] = field(default_factory=list)


_REFUSAL_WORDS = {
    ALREADY_MATCHES: "The product master already holds this value.",
    CONFLICT_NOT_CONFIRMED: (
        "This disagrees with a value somebody set, or with a specification they "
        "removed. Change it on the product's own Specifications tab."
    ),
    NOT_IN_BATCH: "That proposal is not part of this flyer's batch.",
}


def _reject(message: str) -> AppException:
    """The refusal `value_for_registry` raises for a value this registry cannot take."""
    return AppException(status_code=400, message=message, code=BAD_VALUE)


def apply_batch(
    db: Session,
    batch: ProductSpecFlyerBatch,
    record: FlyerReadingRecord,
    *,
    proposal_ids: list[str],
    user: Optional[dict] = None,
) -> ApplyResult:
    """Write the ticked rows, one `apply_spec_values` call per product, one commit.

    **The request names ids; it never carries a value.** The values come off the stored
    proposals, which came off the reading, which is the whole security model of this
    route - the same one `dimension_apply_service` has (L8).

    Every row is re-classified against the live spec row before anything is written,
    because the master may have moved since the pass ran: a row that now matches is
    refused `already_matches` with no write at all (which is what makes re-applying the
    same flyer cost nothing, AC-C.6), and one that now disagrees with a value a person
    set is refused `conflict_not_confirmed` (L7 - bulk never overwrites authorship).

    One call per product and one commit for the request: per-key calls would produce one
    fan-out, one rendered-sentence rebuild and one re-derivation PER KEY for what the
    reviewer experienced as a single action.
    """
    wanted: list[str] = []
    for raw in proposal_ids:
        text = str(raw or "").strip()
        if text and text not in wanted:
            wanted.append(text)

    if len(wanted) > MAX_ROWS:
        raise AppException(
            status_code=422,
            message=(
                f"That is {len(wanted)} proposals. Apply at most {MAX_ROWS} at a time."
            ),
            code="product_spec_batch_too_large",
        )

    rows = (
        db.query(ProductSpecFlyerProposal)
        .filter(
            ProductSpecFlyerProposal.batch_id == batch.id,
            ProductSpecFlyerProposal.id.in_(wanted or [""]),
        )
        .all()
    )
    by_id = {str(row.id): row for row in rows}

    applied: list[AppliedSpec] = []
    refused: list[RefusedSpec] = []

    # An id this batch does not hold is answered, never ignored: a screen that ticked a
    # row and heard nothing about it cannot tell "written" from "lost".
    for proposal_id in wanted:
        if proposal_id not in by_id:
            refused.append(
                RefusedSpec(
                    proposal_id=proposal_id,
                    product_code="",
                    spec_key="",
                    reason=NOT_IN_BATCH,
                    message=_REFUSAL_WORDS[NOT_IN_BATCH],
                )
            )

    index = {row.spec_key: row for row in active_registry(db)}
    stored = _stored(db, [row.product_id for row in rows])

    per_product: dict[str, list[ProductSpecFlyerProposal]] = {}
    for row in rows:
        per_product.setdefault(row.product_id, []).append(row)

    stamped_at = _now()
    actor_id = (user or {}).get("id")

    for product_id, product_rows in per_product.items():
        spec = stored.get(product_id)
        stored_values = dict((spec.values if spec else None) or {})
        stored_provenance = dict((spec.provenance if spec else None) or {})

        entries: list[dict] = []
        writing: list[ProductSpecFlyerProposal] = []

        for row in product_rows:
            registry_row = index.get(row.spec_key)
            if registry_row is None:
                refused.append(
                    _refuse(
                        row,
                        BAD_VALUE,
                        f"{row.spec_key} is not a specification this system holds.",
                        stamped_at,
                    )
                )
                continue

            proposed_entry: dict = {"value": row.value}
            if registry_row.unit:
                proposed_entry["unit"] = registry_row.unit

            kind = classify_spec_proposal(
                proposed_entry,
                stored_values.get(row.spec_key),
                stored_provenance.get(row.spec_key) or {},
                row.spec_key,
            )
            if kind == "unchanged":
                refused.append(
                    _refuse(row, ALREADY_MATCHES, _REFUSAL_WORDS[ALREADY_MATCHES], stamped_at)
                )
                continue
            if kind in ("conflict", "suppressed"):
                refused.append(
                    _refuse(
                        row,
                        CONFLICT_NOT_CONFIRMED,
                        _REFUSAL_WORDS[CONFLICT_NOT_CONFIRMED],
                        stamped_at,
                    )
                )
                continue

            try:
                value = value_for_registry(registry_row, row.value, _reject)
            except AppException as exc:
                refused.append(
                    _refuse(row, BAD_VALUE, _words(exc), stamped_at)
                )
                continue

            entries.append(
                {
                    "spec_key": row.spec_key,
                    "op": "set",
                    "value": value,
                    # The registry's unit, never the flyer's: the unit belongs to the
                    # key, and a card that could smuggle its own would store 250 cm
                    # under a millimetre measurement.
                    "unit": registry_row.unit or None,
                    "source": "flyer",
                    "evidence": _evidence(record, row),
                }
            )
            writing.append(row)

        if not entries:
            continue

        code = writing[0].product_code
        try:
            spec_write.apply_spec_values(
                db, code, entries, actor=user, commit=False
            )
        except AppException as exc:
            # One product's write failing is not the request failing. Its rows are
            # refused with the reason and the other products still apply (AC-C.4).
            reason = _reason_for(exc)
            for row in writing:
                refused.append(_refuse(row, reason, _words(exc), stamped_at))
            continue

        for row, entry in zip(writing, entries):
            row.outcome = APPLIED
            row.applied_at = stamped_at
            row.applied_by = actor_id
            db.add(row)
            applied.append(
                AppliedSpec(
                    proposal_id=str(row.id),
                    product_code=row.product_code,
                    spec_key=row.spec_key,
                    value=entry["value"],
                )
            )

    if applied:
        batch.applied_at = stamped_at
        batch.applied_by = actor_id
    batch.applied_count = _applied_count(db, batch)
    db.add(batch)

    db.commit()
    return ApplyResult(applied=applied, refused=refused)


def _applied_count(db: Session, batch: ProductSpecFlyerBatch) -> int:
    """How many of this batch's rows have ever been written.

    Counted off the rows rather than accumulated on the batch, so the number on the
    list screen and the rows on the review screen cannot disagree.
    """
    return (
        db.query(ProductSpecFlyerProposal)
        .filter(
            ProductSpecFlyerProposal.batch_id == batch.id,
            ProductSpecFlyerProposal.outcome == APPLIED,
        )
        .count()
    )


def _refuse(
    row: ProductSpecFlyerProposal, reason: str, message: str, stamped_at: datetime
) -> RefusedSpec:
    """Record the refusal on the row as well as in the answer.

    The row keeps it so the review screen can show, next time it is opened, what was
    decided about every proposal - a batch applied over several sittings is unreadable
    otherwise.

    A row that was already WRITTEN keeps its `applied` outcome and the moment it was
    written. Re-ticking it is the normal second apply (AC-C.6): the master now agrees, so
    it comes back `already_matches` in the answer, but stamping that over the row would
    erase the fact that this flyer is where the value came from - `applied_count` would
    fall to zero and the list screen would flip a batch from Applied back to Proposed for
    a request that changed nothing (AC-C.5).
    """
    if row.outcome != APPLIED:
        row.outcome = reason
        row.applied_at = stamped_at
    return RefusedSpec(
        proposal_id=str(row.id),
        product_code=row.product_code,
        spec_key=row.spec_key,
        reason=reason,
        message=message,
    )


def _evidence(record: FlyerReadingRecord, row: ProductSpecFlyerProposal) -> str:
    """`flyer <filename>: <the printed words>`.

    The filename is in it because a value badged `Flyer` a year later must say WHICH
    flyer, and the printed words are in it because that is what makes the badge honest.
    A card that stated the value without any words to quote collapses to the filename
    rather than leaving a dangling colon.
    """
    printed = (row.evidence or "").strip()
    label = f"flyer {record.filename}"
    return f"{label}: {printed}" if printed else label


def _words(exc: AppException) -> str:
    """The sentence an AppException carries. Not `exc.message`, which does not exist."""
    detail = getattr(exc, "detail", None)
    if isinstance(detail, dict):
        return str(detail.get("message") or detail)
    return str(detail or exc)


def _reason_for(exc: AppException) -> str:
    """The outcome a refused write is recorded under.

    `product_not_found` is its own reason because it sends the reviewer to the product
    master, where every other refusal from the choke point sends them to the value.
    """
    detail = getattr(exc, "detail", None)
    code = detail.get("code") if isinstance(detail, dict) else None
    return PRODUCT_NOT_FOUND if code == PRODUCT_NOT_FOUND else BAD_VALUE
