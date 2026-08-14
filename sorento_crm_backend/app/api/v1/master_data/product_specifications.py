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
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, text as sql_text
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.models.product_spec import ProductFindabilityResult, ProductFindabilityRun
from app.services.spec_findability import run_findability
from app.models.product import Product, ProductCategory
from app.models.product_spec import (
    ProductSpecRegistry,
    ProductFlyerText,
    ProductSpecException,
    ProductSpecifications,
)
from app.schemas.common import MAX_PAGE_LIMIT
from app.services.error_handler import handle_internal_error, handle_not_found
from app.services.product_class_signal import explain_code
from app.services.product_spec_search import RELEVANCE_FLOOR, search_specs
from app.services.product_spec_understanding import understand_phrase

router = APIRouter()


def _spec_reject(message: str):
    """A refusal a person can act on, rather than a 500 with a stack trace."""
    from app.services.error_handler import AppException

    return AppException(status_code=400, message=message, code="product_spec_bad_value")

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
    status: Optional[str] = Query(None, description="derived | needs_review | approved"),
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
            # The OTHER text derivation reads. A value whose provenance says `flyer`
            # came from here and from nowhere the product master shows, so without it
            # the only honest answer to "where did massage jet come from" is a shrug.
            "flyer_text": (
                db.query(ProductFlyerText.text)
                .filter(ProductFlyerText.product_code == product.product_code)
                .scalar()
            ),
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
    from app.services.product_spec_registry import merged_allowed_values
    from app.services.product_spec_write import apply_spec_values

    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise handle_not_found("Product", product_id)

    row = db.query(ProductSpecRegistry).filter_by(spec_key=spec_key).first()
    if row is None:
        raise handle_not_found("Spec key", spec_key)

    value = payload.value
    data_type = (row.data_type or "").lower()
    if data_type == "boolean":
        value = str(value).strip().lower() in {"true", "yes", "1"}
    elif data_type == "numeric":
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise _spec_reject(f"{row.label} is a measurement, so it needs a number.")
        value = int(number) if number.is_integer() else number
    else:
        value = str(value).strip()
        allowed = merged_allowed_values(row)
        if allowed and value not in allowed:
            raise _spec_reject(
                f"{row.label} does not have a value called \"{value}\". "
                f"Add it to the specification first, or pick one of: {', '.join(allowed)}."
            )

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

    apply_spec_values(
        db,
        product.product_code,
        [{"spec_key": spec_key, "op": mode}],
        actor=current_user,
    )
    return {"spec_key": spec_key, "cleared": True, "mode": mode}


class FlyerTextEdit(BaseModel):
    """The flyer card's wording, as a person corrects it."""

    text: str


@router.put("/by-product/{product_id}/flyer-text")
async def set_flyer_text(
    product_id: str,
    payload: FlyerTextEdit,
    current_user: dict = Depends(require_permission_with_api_key("master_data.products.edit")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Correct the flyer card this product's specs are read from.

    The card text comes from a machine reading of the printed flyer, and that reading is
    not complete: a card the layout split across a column break, or one whose code the
    reading could not place, leaves a product with no flyer text and therefore no
    dimensions, no seat material, no flush type. Until now the only fix was to re-run
    the reading, which is neither quick nor something a merchandiser can do.

    The corrected text is stored as the product's flyer card and the product is read
    again immediately, so the specs move in the same click rather than waiting for the
    next catalogue run.
    """
    from app.services.product_spec_derivation import derive_for_code

    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise handle_not_found("Product", product_id)

    text = (payload.text or "").strip()
    row = (
        db.query(ProductFlyerText)
        .filter(ProductFlyerText.product_code == product.product_code)
        .first()
    )
    if row is None:
        if not text:
            return {"product_code": product.product_code, "flyer_text": None, "cleared": True}
        row = ProductFlyerText(product_code=product.product_code)
        db.add(row)

    if not text:
        # Emptying the box means "this product has no flyer card", not "store a blank
        # one" - a blank row would keep answering for a card the flyer never printed.
        db.delete(row)
    else:
        row.text = text
        # `lines` is what the importer stored sentence by sentence; keep the two in step
        # so a later import diffing against it sees the corrected wording.
        row.lines = [part.strip() for part in text.split(".") if part.strip()]
        row.source_label = "Edited by hand"
        row.source_id = None

    db.flush()
    result = derive_for_code(db, product.product_code, commit=True)
    return {
        "product_code": product.product_code,
        "flyer_text": text or None,
        "rederived": result,
    }


@router.post("/preview-search")
async def preview_spec_search(
    payload: SpecPreviewRequest,
    current_user: dict = Depends(require_permission_with_api_key("master_data.products.view")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Run the ranker exactly as the chatbot would, and show its working.

    Returns the score and the matched keys per candidate so a reviewer can see WHY a
    result placed where it did, rather than only that it did.
    """
    try:
        specs = list(payload.specs)
        free_terms = list(payload.free_terms)
        exclusions: list[dict] = []
        understanding = None

        if payload.phrase and payload.phrase.strip():
            understanding = understand_phrase(
                db,
                payload.phrase,
                user_id=current_user.get("id"),
                allow_model=payload.understand,
            )
            # A spec the caller pinned by hand always wins: they are looking at the
            # screen, the model is guessing from one sentence.
            pinned = {str(e.get("key")) for e in specs if e.get("key")}
            specs = specs + [e for e in understanding.specs if e["key"] not in pinned]
            free_terms = free_terms + [t for t in understanding.free_terms if t not in free_terms]
            exclusions = list(understanding.exclusions)

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


# --- Findability: can a customer find this product by describing it? ---------------
#
# The business's own test, automated. Open a flyer, read a card, say what is printed on
# it, expect that product back. Run per flyer so the Cabana and Mocha flyers that follow
# are new rows rather than new code.


@router.get("/findability/flyers")
def list_flyers(
    current_user: dict = Depends(require_permission_with_api_key("master_data.products.view")),
    db: Session = Depends(get_db),
):
    """Every flyer we hold card text for, and whether it has been swept."""
    try:
        rows = db.execute(
            sql_text(
                "SELECT f.source_id, f.source_label, COUNT(DISTINCT f.product_code) AS cards,"
                "       MAX(r.created_at) AS last_run"
                "  FROM product_flyer_text f"
                "  LEFT JOIN product_findability_runs r ON r.source_id = f.source_id"
                " GROUP BY f.source_id, f.source_label"
                " ORDER BY f.source_label"
            )
        ).fetchall()
        return {
            "flyers": [
                {
                    "source_id": r.source_id,
                    "source_label": r.source_label,
                    "cards": r.cards,
                    "last_run": r.last_run.isoformat() if r.last_run else None,
                }
                for r in rows
            ]
        }
    except Exception as e:
        raise handle_internal_error(str(e))


def _sweep_in_background(source_id: str | None, window: int, limit: int | None) -> None:
    """Its own session: the request that started this is long gone."""
    from app.database import SessionLocal

    with SessionLocal() as session:
        try:
            run_findability(session, source_id=source_id, window=window, limit=limit)
        except Exception as exc:  # noqa: BLE001 - recorded on the run, not swallowed
            logging.exception("findability sweep failed")
            session.rollback()
            latest = (
                session.query(ProductFindabilityRun)
                .order_by(ProductFindabilityRun.created_at.desc())
                .first()
            )
            if latest and latest.status == "running":
                latest.status = "failed"
                latest.error = str(exc)[:2000]
                session.commit()


@router.post("/findability/run")
def start_findability_run(
    background: BackgroundTasks,
    source_id: str | None = Query(None, description="Which flyer. Omitted means all."),
    window: int = Query(25, ge=1, le=100),
    limit: int | None = Query(None, description="First N cards only, for a quick look."),
    current_user: dict = Depends(require_permission_with_api_key("master_data.products.edit")),
    db: Session = Depends(get_db),
):
    """Start a sweep. Returns immediately; a full flyer takes about half an hour."""
    try:
        background.add_task(_sweep_in_background, source_id, window, limit)
        return {"started": True, "source_id": source_id}
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/findability/runs")
def list_findability_runs(
    source_id: str | None = Query(None),
    current_user: dict = Depends(require_permission_with_api_key("master_data.products.view")),
    db: Session = Depends(get_db),
):
    """Past sweeps, newest first. The comparison is the point."""
    try:
        query = db.query(ProductFindabilityRun)
        if source_id:
            query = query.filter(ProductFindabilityRun.source_id == source_id)
        runs = query.order_by(ProductFindabilityRun.created_at.desc()).limit(30).all()
        return {
            "runs": [
                {
                    "id": r.id,
                    "source_label": r.source_label,
                    "window": r.window,
                    "cards": r.cards,
                    "found_by_card": r.found_by_card,
                    "found_by_specs": r.found_by_specs,
                    "not_found": r.not_found,
                    "status": r.status,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in runs
            ]
        }
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/findability/runs/{run_id}")
def findability_run_detail(
    run_id: str,
    boundary: str | None = Query(None, description="Filter, e.g. 'none' for the gaps."),
    q: str | None = Query(None, description="Product code contains."),
    current_user: dict = Depends(require_permission_with_api_key("master_data.products.view")),
    db: Session = Depends(get_db),
):
    """One sweep, card by card, with every angle that was tried."""
    try:
        run = db.query(ProductFindabilityRun).filter_by(id=run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")

        query = db.query(ProductFindabilityResult).filter_by(run_id=run_id)
        if boundary:
            query = query.filter(ProductFindabilityResult.boundary == boundary)
        if q:
            query = query.filter(ProductFindabilityResult.product_code.ilike(f"%{q}%"))
        results = query.order_by(ProductFindabilityResult.product_code).all()

        return {
            "run": {
                "id": run.id,
                "source_label": run.source_label,
                "window": run.window,
                "cards": run.cards,
                "found_by_card": run.found_by_card,
                "found_by_specs": run.found_by_specs,
                "not_found": run.not_found,
                "status": run.status,
                "error": run.error,
                "created_at": run.created_at.isoformat() if run.created_at else None,
            },
            "results": [
                {
                    "product_code": r.product_code,
                    "is_discontinued": r.is_discontinued,
                    "phrase": r.phrase,
                    "boundary": r.boundary,
                    "ranks": r.ranks or {},
                }
                for r in results
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
