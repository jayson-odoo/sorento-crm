"""Product specifications: what was derived, and what the ranker does with it.

Two read surfaces, both for staff:

  * the derived specs per product, so a human can see what the machine read out of
    the catalog and which rows need attention.
  * a spec-search PREVIEW, so the ranker can be judged by someone who sells this
    catalog rather than by the person who wrote the weights.

The preview is the point. The relevance floor and the per-key weights are currently
one engineer's judgement measured against a small eval set; they only become right
when a product person types real phrases and says which results are wrong.
"""
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.models.product import Product, ProductCategory
from app.models.product_spec import (
    ProductSpecRegistry,
    ProductSpecException,
    ProductSpecifications,
)
from app.schemas.common import MAX_PAGE_LIMIT
from app.services import product_spec_verification
from app.services.error_handler import AppException, handle_internal_error, handle_not_found
from app.services.product_class_signal import explain_code
from app.services.product_spec_search import RELEVANCE_FLOOR, search_specs

router = APIRouter()


def _spec_reject(message: str):
    """A refusal a person can act on, rather than a 500 with a stack trace."""
    from app.services.error_handler import AppException

    return AppException(status_code=400, message=message, code="product_spec_bad_value")


def _spec_reject_unprocessable(message: str):
    """The same refusal at 422, for a body that is the wrong size rather than wrong."""
    from app.services.error_handler import AppException

    return AppException(status_code=422, message=message, code="product_spec_bad_text")


def _value_for_registry(row: ProductSpecRegistry, raw: Any, reject) -> Any:
    """One value, forced into the shape the registry describes, or refused.

    Both write paths call this and neither keeps its own copy: a value a reviewer
    accepts off a pasted flyer card is written by the batch route, and the same value
    typed into the same field is written by the PUT. Two copies of the coercion would
    mean the batch could store a word the field itself refuses - an out-of-vocabulary
    enum, a "measurement" that is not a number - and the vocabulary is the whole
    reason the registry is shared with the parser and the ranker.

    `reject` builds the refusal, because the two callers are refusing different
    things: a value typed into one field is a bad business state (400), and a body
    naming a value the registry cannot accept is the wrong shape for the call (422).
    The blank case answers 400 either way - it is the write choke point's own refusal
    (`product_spec_write._prepare`), reproduced here only so the message can name the
    key's label instead of its slug.
    """
    from app.services.product_spec_registry import merged_allowed_values

    def _blank():
        # An empty value is not a value, it is a removal wearing one. Stored, it
        # canonicalises to nothing while derivation keeps producing something, so the
        # merge would raise the same conflict on every run forever - in a table whose
        # contract is exceptions only.
        return _spec_reject(
            f"{row.label} cannot be blank. To take the value away, remove the "
            f"specification instead."
        )

    if isinstance(raw, (list, tuple)):
        # A product can genuinely carry two of these at once: SRTWT9605-RG is "Rose
        # Gold + Matt Black", and derivation stores both. So the list is coerced
        # element-wise and KEPT as a list, or accepting a proposal would write a
        # different shape from the one a re-derivation of the same words produces.
        from app.services.product_spec_derivation import MULTI_VALUE_KEYS

        if row.spec_key not in MULTI_VALUE_KEYS:
            raise reject(f"{row.label} holds one value, not several.")
        items = [_value_for_registry(row, item, reject) for item in raw]
        if not items:
            raise _blank()
        # One tone is stored as the tone, exactly as `apply_rules` does it: a
        # one-element list and the value itself must not be two different answers.
        return items[0] if len(items) == 1 else items

    data_type = (row.data_type or "").lower()
    if data_type == "boolean":
        return str(raw).strip().lower() in {"true", "yes", "1"}

    if data_type == "numeric":
        try:
            number = float(raw)
        except (TypeError, ValueError):
            raise reject(f"{row.label} is a measurement, so it needs a number.")
        return int(number) if number.is_integer() else number

    value = str(raw).strip()
    if not value:
        raise _blank()

    allowed = merged_allowed_values(row)
    if allowed and value not in allowed:
        raise reject(
            f"{row.label} does not have a value called \"{value}\". "
            f"Add it to the specification first, or pick one of: {', '.join(allowed)}."
        )
    return value


_INTERNAL_ONLY_VALUE_KEYS: set[str] = set()


def _display_values(values: dict) -> dict:
    return {k: v for k, v in values.items() if k not in _INTERNAL_ONLY_VALUE_KEYS}


class SpecPreviewRequest(BaseModel):
    """A phrase as the ranker sees it, once the parser has done its half."""

    specs: list[dict] = Field(
        default_factory=list,
        description="[{key, value}] drawn from the Spec Registry.",
    )
    free_terms: list[str] = Field(
        default_factory=list,
        description="Words that did not map onto a registry key.",
    )
    floor: Optional[float] = Field(
        default=None,
        description="Override the relevance floor, to see what it is currently hiding.",
    )
    phrase: Optional[str] = Field(
        default=None,
        description=(
            "The customer's raw sentence. When present it is read semantically and the "
            "result is merged with `specs`/`free_terms`."
        ),
    )
    understand: bool = Field(
        default=True,
        description="Set false to see the deterministic reading alone, for comparison.",
    )


@router.get("/")
async def list_product_specifications(
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=MAX_PAGE_LIMIT),
    query: Optional[str] = Query(None, description="Match a product code or class."),
    status: Optional[str] = Query(None, description="derived | needs_review | authored"),
    current_user: dict = Depends(require_permission_with_api_key("master_data.products.view")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Derived specs, one row per product, newest derivation first."""
    try:
        q = (
            db.query(ProductSpecifications, Product, ProductCategory)
            .join(Product, Product.id == ProductSpecifications.product_id)
            .outerjoin(ProductCategory, ProductCategory.id == Product.category_id)
        )
        if query:
            wild = f"%{query.strip()}%"
            q = q.filter(
                or_(
                    Product.product_code.ilike(wild),
                    ProductCategory.class_label.ilike(wild),
                )
            )
        if status:
            q = q.filter(ProductSpecifications.status == status)

        total = q.count()
        rows = (
            q.order_by(Product.product_code)
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )

        # One grouped count rather than a query per row: this list is the first thing
        # a reviewer opens, and an N+1 here is felt immediately.
        codes = [product.product_code for _, product, _ in rows]
        exception_counts = dict(
            db.query(ProductSpecException.product_code, func.count(ProductSpecException.id))
            .filter(
                ProductSpecException.product_code.in_(codes or [""]),
                ProductSpecException.resolved_at.is_(None),
            )
            .group_by(ProductSpecException.product_code)
            .all()
        )

        data = []
        for spec, product, category in rows:
            values = spec.values or {}
            data.append(
                {
                    "product_id": str(product.id),
                    "product_code": product.product_code,
                    "class_label": (values.get("class") or {}).get("value")
                    or (category.class_label if category else None),
                    "brand_hint": (values.get("brand") or {}).get("value"),
                    "spec_count": len(
                        [k for k in values if k not in ("class", "brand")]
                    ),
                    "rendered_text": spec.rendered_text,
                    "status": spec.status,
                    "is_discontinued": bool(product.is_discontinued),
                    "open_exceptions": exception_counts.get(product.product_code, 0),
                    "values": _display_values(values),
                    "provenance": _display_values(spec.provenance or {}),
                }
            )

        return {
            "data": data,
            "pagination": {"total": total, "page": page, "limit": limit},
        }
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/by-product/{product_id}")
async def get_product_specification(
    product_id: str,
    current_user: dict = Depends(require_permission_with_api_key("master_data.products.view")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Everything derived for one product, plus WHY when nothing was.

    Opened from the product record itself, so it must answer the question actually
    being asked there — "is this product findable by description, and if not what is
    stopping it" — rather than only rendering whatever rows happen to exist. A product
    outside the enabled classes returns an empty spec and a reason, never a blank.
    """
    try:
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise handle_not_found("Product", product_id)

        category = (
            db.query(ProductCategory).filter(ProductCategory.id == product.category_id).first()
            if product.category_id
            else None
        )
        spec = (
            db.query(ProductSpecifications)
            .filter(ProductSpecifications.product_id == product.id)
            .first()
        )
        exceptions = (
            db.query(ProductSpecException)
            .filter(
                ProductSpecException.product_code == product.product_code,
                ProductSpecException.resolved_at.is_(None),
            )
            .order_by(ProductSpecException.spec_key)
            .all()
        )

        diagnosis = explain_code(category.category_code if category else None)
        # "Eligible" only describes the category. A product whose class IS enabled but
        # which still has no row means the derivation job has not covered it yet — a
        # different problem with a different fix, so it gets its own reason.
        if spec is None and diagnosis["reason"] == "eligible":
            diagnosis = {**diagnosis, "reason": "not_yet_derived"}

        return {
            "product_id": str(product.id),
            "product_code": product.product_code,
            "category_code": category.category_code if category else None,
            "searchable": bool(spec),
            "diagnosis": diagnosis,
            # Both from the CODE, so the two company copies of a model show the
            # identical badge and the Specifications tab needs no second round trip
            # (AC-D.14). `values_hash` is what a single Verify echoes back.
            "verification": product_spec_verification.verification_block(
                db, product.product_code
            ),
            "values_hash": product_spec_verification.current_values_hash(
                db, product.product_code
            ),
            "spec": (
                {
                    "values": _display_values(spec.values or {}),
                    "provenance": _display_values(spec.provenance or {}),
                    "rendered_text": spec.rendered_text,
                    "status": spec.status,
                    "derived_at": (spec.updated_at or spec.created_at).isoformat(),
                }
                if spec
                else None
            ),
            "exceptions": [
                {
                    "id": str(row.id),
                    "spec_key": row.spec_key,
                    "reason": row.reason,
                    "proposed": row.proposed,
                    "stored": row.stored,
                }
                for row in exceptions
            ],
            "source_text": product.description or product.product_name or "",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/exceptions")
async def list_spec_exceptions(
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=MAX_PAGE_LIMIT),
    current_user: dict = Depends(require_permission_with_api_key("master_data.products.view")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Open exceptions only. If routine successes ever appear here, the filter is wrong."""
    try:
        q = db.query(ProductSpecException).filter(ProductSpecException.resolved_at.is_(None))
        total = q.count()
        rows = (
            q.order_by(ProductSpecException.product_code)
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )
        return {
            "data": [
                {
                    "id": str(row.id),
                    "product_code": row.product_code,
                    "spec_key": row.spec_key,
                    "reason": row.reason,
                    "proposed": row.proposed,
                    "stored": row.stored,
                }
                for row in rows
            ],
            "pagination": {"total": total, "page": page, "limit": limit},
        }
    except Exception as e:
        raise handle_internal_error(str(e))


class ManualSpecValue(BaseModel):
    """A value a person sets by hand, because the catalog does not state it anywhere."""

    value: Any


@router.post("/by-product/{product_id}/rederive")
async def rederive_one_product(
    product_id: str,
    current_user: dict = Depends(require_permission_with_api_key("master_data.products.edit")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Read THIS product again with the rules that are live now.

    The catalogue-wide job takes minutes over 22,805 rows, which is the wrong tool when
    you have just changed one rule and want to see what it did to one product.
    """
    from app.services.product_spec_derivation import derive_for_code

    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise handle_not_found("Product", product_id)
    try:
        result = derive_for_code(db, product.product_code, commit=True)
        return {"product_code": product.product_code, **result}
    except Exception as e:
        raise handle_internal_error(str(e))


class SpecExtractRequest(BaseModel):
    """The text a person pasted. Held in the request body and nowhere else."""

    text: str = Field(description="A flyer card, a leaflet paragraph, a supplier blurb.")


class SpecBatchEntry(BaseModel):
    """One accepted proposal, on its way to the write choke point."""

    # Bounded rather than free: a `spec_key` is a registry column and an `evidence`
    # string is one sentence a value was read from. Neither is a place for a pasted
    # document, and an unbounded string here would be written into `provenance` on
    # every company copy of the code and rendered in a table cell for ever after.
    spec_key: str = Field(max_length=100)
    value: Any
    unit: Optional[str] = None
    evidence: str = Field(default="", max_length=500)


class SpecBatchRequest(BaseModel):
    entries: list[SpecBatchEntry] = Field(min_length=1, max_length=50)


@router.post("/by-product/{product_id}/extract")
def extract_spec_proposals_from_text(
    product_id: str,
    payload: SpecExtractRequest,
    current_user: dict = Depends(require_permission_with_api_key("master_data.products.edit")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Read pasted text and PROPOSE. Writes no specification data, anywhere.

    Not a shortcut for the batch write below: the whole point is that a machine reading
    of marketing copy is shown to a person beside what is already stored, and only what
    they tick is written. The pasted text lives in this request and in the component's
    own state, and is never persisted (AC-B.1).

    The one row a call can write is the usage-log row the model call books against
    itself, stamped with the caller so a reading made here is counted beside every
    other model call. Telemetry about the call, never a claim about the product.

    Plain ``def``, so FastAPI runs it in a thread: the model round trip is blocking, and
    on the event loop it freezes the whole worker (same fix as the preview route).
    """
    from app.services.product_spec_extract import MAX_TEXT_LENGTH, extract_spec_proposals

    text = (payload.text or "").strip()
    if not text:
        raise _spec_reject_unprocessable(
            "There is nothing to read. Paste the text about this product first."
        )
    if len(text) > MAX_TEXT_LENGTH:
        # Refused rather than truncated: reading half a document and proposing from it
        # looks like a complete answer and is not one.
        raise _spec_reject_unprocessable(
            f"That text is {len(text):,} characters, and this reads up to "
            f"{MAX_TEXT_LENGTH:,}. Paste the part that describes this product."
        )

    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise handle_not_found("Product", product_id)

    try:
        return extract_spec_proposals(
            db, product, text, user_id=(current_user or {}).get("id")
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/by-product/{product_id}/values/batch")
def set_spec_values_in_one_batch(
    product_id: str,
    payload: SpecBatchRequest,
    current_user: dict = Depends(require_permission_with_api_key("master_data.products.edit")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Write every accepted proposal in ONE call (AC-B.9).

    One call per key would produce one fan-out, one rendered-sentence rebuild and one
    verification diff PER KEY for what the user experienced as a single action, and a
    partial failure would leave the table half-applied. So the batch is the shape and a
    batch of one is the narrow case.

    Every entry is validated against the registry exactly as the single PUT validates
    the one it is given (`_value_for_registry`), because a value a person accepted off
    a flyer card is the same claim as one they typed, and only the shared helper keeps
    the two from drifting.

    Plain ``def``, so FastAPI runs it in a thread: up to fifty keys, a fan-out to every
    company copy and a full re-derive of the code is real synchronous work, and on the
    event loop it holds up every other request the worker is serving.
    """
    from app.services.product_spec_write import apply_spec_values

    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise handle_not_found("Product", product_id)

    # Pre-flight, before anything is written: the choke point validates the operation
    # and the value but knows nothing about the registry, so an unknown key would
    # otherwise be written as a permanent provenance entry no screen can render, and an
    # out-of-vocabulary value would be written as a word the ranker has never heard of.
    # Every entry is checked first, so one bad entry writes none of the batch.
    keys = [entry.spec_key.strip() for entry in payload.entries]
    # One key twice in one batch is two different claims about the same thing, and the
    # choke point would apply them in list order and keep the last silently - the user
    # ticked two rows and one of them would vanish without a word. Refused whole.
    duplicated = sorted({key for key in keys if keys.count(key) > 1})
    if duplicated:
        raise _spec_reject_unprocessable(
            "The same specification appears more than once in this batch: "
            + ", ".join(duplicated)
            + ". Send one value per specification."
        )
    known = {
        row.spec_key: row
        for row in db.query(ProductSpecRegistry)
        .filter(ProductSpecRegistry.spec_key.in_(keys or [""]))
        .all()
    }
    for key in keys:
        if key not in known:
            raise handle_not_found("Spec key", key)

    prepared: list[dict] = []
    for entry in payload.entries:
        row = known[entry.spec_key.strip()]
        # The words the text was read from, kept on the row: a value a person accepted
        # off a flyer is still traceable to the sentence that proposed it, which is
        # what makes the badge honest a year later. A dangling "read from text: " with
        # nothing after it says less than the phrase alone, so it collapses.
        evidence = (entry.evidence or "").strip()
        prepared.append(
            {
                "spec_key": row.spec_key,
                "op": "set",
                "value": _value_for_registry(row, entry.value, _spec_reject_unprocessable),
                # The registry's unit, never the caller's: the unit belongs to the key
                # and a batch that could smuggle in its own would store 250 cm under a
                # millimetre measurement.
                "unit": row.unit or None,
                "source": "human",
                "evidence": f"read from text: {evidence}" if evidence else "read from text",
            }
        )

    return apply_spec_values(db, product.product_code, prepared, actor=current_user)


@router.put("/by-product/{product_id}/values/{spec_key}")
async def set_spec_value_by_hand(
    product_id: str,
    spec_key: str,
    payload: ManualSpecValue,
    current_user: dict = Depends(require_permission_with_api_key("master_data.products.edit")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Set a value the catalog never states, and hold it against re-derivation.

    A blue WC is blue in the photograph and nowhere in the text. No rule can read it,
    so the only honest source is a person - and derivation already promises that a
    `human` value outranks anything derivable and is carried through every later run.

    The value is checked against the registry so a hand-set spec cannot introduce a
    word the ranker and the parser have never heard of, which is the whole reason the
    vocabulary is shared.
    """
    from app.services.product_spec_write import apply_spec_values

    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise handle_not_found("Product", product_id)

    row = db.query(ProductSpecRegistry).filter_by(spec_key=spec_key).first()
    if row is None:
        raise handle_not_found("Spec key", spec_key)

    # The same coercion the batch route runs, from the same helper: a value a person
    # types and a value they tick off a proposal are the same claim about the product.
    value = _value_for_registry(row, payload.value, _spec_reject)

    # The write itself belongs to the spec write service: it fans the value out to every
    # company copy of the code, holds it against the re-derivation it triggers, and
    # raises the disagreement if the rules read something else.
    apply_spec_values(
        db,
        product.product_code,
        [
            {
                "spec_key": spec_key,
                "op": "set",
                "value": value,
                "unit": row.unit or None,
                "source": "human",
            }
        ],
        actor=current_user,
    )
    return {"spec_key": spec_key, "value": value, "source": "human"}


@router.delete("/by-product/{product_id}/values/{spec_key}")
async def clear_hand_set_spec_value(
    product_id: str,
    spec_key: str,
    mode: str = Query(
        "revert",
        description=(
            "revert - hand the key back to derivation. "
            "absent - record that this product does not have this spec."
        ),
    ),
    current_user: dict = Depends(require_permission_with_api_key("master_data.products.edit")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Remove a value, one of two ways, because they mean different things.

    "Use what the rules read" hands the key back to derivation and it comes back with
    whatever the catalogue says. "This product does not have this spec" is a statement
    of fact that must survive every later run, so it is stored as a tombstone rather
    than as an absence, which derivation would simply fill in again.

    `revert` is the default because it is what the shipped screen has always done.
    """
    from app.services.product_spec_write import apply_spec_values

    mode = (mode or "revert").strip().lower()
    if mode not in {"revert", "absent"}:
        raise _spec_reject(
            f"\"{mode}\" is not a way to remove a specification. Use revert or absent."
        )

    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise handle_not_found("Product", product_id)

    if mode == "absent":
        # A tombstone pins `status='authored'` on every copy of the code for good, so
        # the key it names has to be one the registry knows - otherwise a typo writes a
        # permanent provenance entry no registry-driven screen will ever show.
        # `revert` is deliberately NOT checked: a key the registry has since dropped is
        # still stored on rows, and handing it back to derivation must stay possible.
        if db.query(ProductSpecRegistry).filter_by(spec_key=spec_key).first() is None:
            raise handle_not_found("Spec key", spec_key)

    apply_spec_values(
        db,
        product.product_code,
        [{"spec_key": spec_key, "op": mode}],
        actor=current_user,
    )
    return {"spec_key": spec_key, "cleared": True, "mode": mode}


@router.post("/preview-search")
def preview_spec_search(
    payload: SpecPreviewRequest,
    current_user: dict = Depends(require_permission_with_api_key("master_data.products.view")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Run the ranker exactly as the chatbot would, and show its working.

    Returns the score and the matched keys per candidate so a reviewer can see WHY a
    result placed where it did, rather than only that it did.

    Plain ``def``, so FastAPI runs it in a thread: ``understand_phrase`` does a
    blocking LLM round trip, which on the event loop froze the whole worker. Same
    fix as the portal ai-extract route and PR #164.
    """
    try:
        # The same helper the resolve endpoint calls, so the two readings of one
        # sentence cannot drift apart again (see derive_search_inputs).
        from app.services import product_spec_understanding

        specs, free_terms, exclusions, understanding = (
            product_spec_understanding.derive_search_inputs(
                db,
                payload.phrase,
                specs=list(payload.specs),
                free_terms=list(payload.free_terms),
                allow_model=payload.understand,
                user_id=current_user.get("id"),
            )
        )

        result = search_specs(
            db,
            specs=specs,
            exclusions=exclusions,
            free_terms=free_terms,
            floor=payload.floor if payload.floor is not None else RELEVANCE_FLOOR,
        )
        return {
            "candidates": result["candidates"],
            "floor_missed": result["floor_missed"],
            # What was asked for that nothing offered can satisfy, so the screen can say
            # "no Cabana one — here are Sorento" rather than substituting in silence.
            "unmet": result["unmet"],
            "top_score": result["top_score"],
            "floor": payload.floor if payload.floor is not None else RELEVANCE_FLOOR,
            # What the phrase was understood to mean, so a wrong result can be blamed
            # on the reading or on the ranking rather than guessed at.
            "understanding": (
                {
                    "source": understanding.source,
                    "model": understanding.model,
                    "elapsed_ms": understanding.elapsed_ms,
                    "specs": understanding.specs,
                    # Shown separately on screen: a reader who sees "material = glass"
                    # next to a phrase that said "not glass" has every reason to think
                    # the search is broken.
                    "exclusions": understanding.exclusions,
                    "free_terms": understanding.free_terms,
                    "notes": understanding.notes,
                }
                if understanding
                else None
            ),
        }
    except Exception as e:
        raise handle_internal_error(str(e))


# --- Verification: who vouched for a code's specs, and the queue of what is left ---
#
# Same router, same module guard, and the same two permissions the product screens
# already use - `.view` to read the queue, `.edit` to stamp or withdraw one. No new
# slug is minted: a dedicated one would ship the feature 403'd to everyone, which is
# exactly what happened to the spec registry (AC-D.15).


class SpecVerifyRequest(BaseModel):
    """One code, and the hash of the values the person was actually looking at."""

    product_code: str = Field(..., min_length=1)
    values_hash: str = Field(..., min_length=1)


class SpecVerifyBulkRequest(BaseModel):
    """The rows a reviewer ticked. Capped because selection is page-scoped."""

    items: list[SpecVerifyRequest] = Field(..., min_length=1, max_length=500)


class SpecUnverifyRequest(BaseModel):
    """A withdrawal takes no hash: a claim is being removed, not made."""

    product_code: str = Field(..., min_length=1)


class SpecUnverifyBulkRequest(BaseModel):
    product_codes: list[str] = Field(..., min_length=1, max_length=500)


def _verification_conflict(payload: dict) -> AppException:
    """A 409 whose body IS the refusal, rather than a sentence about it.

    The global handler serialises `AppException.detail` straight to the response body,
    so replacing the standard envelope is how a route says something the client must
    branch on - and the two refusals are deliberately distinguishable (AC-D.4): one
    means "re-read the values", the other "answer the exceptions first". `message` is
    kept alongside so a generic error reader still has something to show.

    Encoded HERE, because that handler hands the detail to `JSONResponse` as-is rather
    than through FastAPI's response encoding. A VerificationBlock carries datetimes, so
    an unencoded payload raised TypeError inside the handler and turned the refusal into
    a 500 - in exactly the case the refusal exists for, a stamped code whose values
    moved. A code with no ledger history has nothing but strings in it, which is why
    the first tests of this path passed.
    """
    payload = jsonable_encoder(payload)
    exc = AppException(status_code=409, message=payload["message"], code=payload["error"])
    exc.detail = payload
    return exc


@router.get("/verification/worklist")
def spec_verification_worklist(
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=MAX_PAGE_LIMIT),
    query: Optional[str] = Query(None, description="Match a product code or name."),
    # Literal rather than str: an unknown state or sort is a client bug, and silently
    # serving the unfiltered list instead of 422ing hides it.
    state: Optional[Literal["unverified", "verified", "needs_reverify"]] = Query(None),
    class_label: Optional[str] = Query(None),
    include_discontinued: bool = Query(False),
    sort: Literal["default", "coverage", "code"] = Query("default"),
    direction: str = Query("asc", alias="dir", description="asc | desc"),
    current_user: dict = Depends(require_permission_with_api_key("master_data.products.view")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """The codes waiting to be confirmed, worst first, in the caller's companies.

    `summary` counts the same set the list does minus the state filter, so the progress
    line stays honest while the reviewer is filtered down (AC-D.6). `classes` carries
    the class filter's own options, so the screen needs no second call for a dropdown.
    """
    return product_spec_verification.worklist(
        db,
        page=page,
        limit=limit,
        query=query,
        state=state,
        class_label=class_label,
        include_discontinued=include_discontinued,
        sort=sort,
        direction=direction,
    )


@router.post("/verification/verify")
def verify_spec_code(
    payload: SpecVerifyRequest,
    current_user: dict = Depends(require_permission_with_api_key("master_data.products.edit")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Confirm one code's specs, against the values the person was shown."""
    result = product_spec_verification.verify_code(
        db,
        payload.product_code,
        values_hash=payload.values_hash,
        actor=current_user,
    )
    if result["outcome"] == "not_found":
        raise handle_not_found("Product", payload.product_code)
    if result["outcome"] == "values_changed":
        raise _verification_conflict(
            {
                "error": "values_changed",
                "message": (
                    "These specifications changed while you were reviewing them. "
                    "Read them again before confirming."
                ),
                "values_hash": result["values_hash"],
                "verification": result["verification"],
            }
        )
    if result["outcome"] == "exceptions_open":
        raise _verification_conflict(
            {
                "error": "exceptions_open",
                "message": "Answer the open specification questions before confirming this product.",
                "exceptions": result["exceptions"],
            }
        )

    db.commit()
    return {
        "product_code": result["product_code"],
        "outcome": result["outcome"],
        "values_hash": result["values_hash"],
        "verification": result["verification"],
    }


@router.post("/verification/verify-bulk")
def verify_spec_codes_bulk(
    payload: SpecVerifyBulkRequest,
    current_user: dict = Depends(require_permission_with_api_key("master_data.products.edit")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """The same guards, per code. A refused code is reported, never fails the batch.

    Also what the per-row button calls, with one item: one code path to keep honest
    (AC-D.16, AC-D.23).
    """
    # The service commits per code (it locks up to 500 of them, and a code decided is
    # a code the reviewer was told about), so there is nothing left to commit here.
    results = product_spec_verification.verify_codes_bulk(
        db,
        [item.model_dump() for item in payload.items],
        actor=current_user,
    )

    verified = sum(1 for r in results if r["outcome"] in ("verified", "already_verified"))
    return {
        "results": [
            {
                # The hash comes back on a refused code too, so the row can refresh
                # itself without a reload (AC-D.24).
                "product_code": r["product_code"],
                "outcome": r["outcome"],
                "values_hash": r["values_hash"],
                "verification": r["verification"],
            }
            for r in results
        ],
        "counts": {"verified": verified, "skipped": len(results) - verified},
    }


@router.post("/verification/unverify")
def unverify_spec_code(
    payload: SpecUnverifyRequest,
    current_user: dict = Depends(require_permission_with_api_key("master_data.products.edit")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Withdraw a confirmation. A user may withdraw a stamp that is not their own -
    the recorded actor is what makes that accountable (AC-D.26)."""
    result = product_spec_verification.unverify_code(
        db, payload.product_code, actor=current_user
    )
    db.commit()
    return result


@router.post("/verification/unverify-bulk")
def unverify_spec_codes_bulk(
    payload: SpecUnverifyBulkRequest,
    current_user: dict = Depends(require_permission_with_api_key("master_data.products.edit")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    # Commits per code, like verify-bulk. The single-code routes still commit themselves.
    results = product_spec_verification.unverify_codes_bulk(
        db, payload.product_codes, actor=current_user
    )

    unverified = sum(1 for r in results if r["outcome"] == "unverified")
    return {
        "results": results,
        "counts": {"unverified": unverified, "no_change": len(results) - unverified},
    }
