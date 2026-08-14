"""Spec Registry API — the vocabulary both the CRM ranker and the n8n parser read.

One vocabulary, two consumers, so this endpoint is the thing that stops them drifting:
if the parser emits `wall_mounted` while the ranker looks for `wall_hung`, every query
quietly scores worse and nothing logs an error.

Writes exist, and they are shaped by that guarantee rather than around it:

  * a `seed` row is repaired on every deploy, so editing its vocabulary would be undone.
    Staff extend it instead — `user_synonyms` is merged in at read time, additive only,
    so a word added here can never remove one the parser depends on.
  * a `user` row has no seed to drift from and is left alone entirely.
  * calibration (`rank_weight`, `is_active`, the match window) has always been
    human-owned on both.

So: add words and tune weights freely; renaming a shipped VALUE is deliberately not
offered, because that is the one edit that breaks the two consumers apart.
"""
import hashlib
import re
import json
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.models.product_spec import ProductSpecRegistry, ProductSpecSearchPolicy
from app.services import product_spec_rederive
from app.services.error_handler import handle_internal_error, handle_not_found
from app.services.product_spec_registry import (
    SEARCH_POLICY_SEED,
    active_registry,
    default_match_window,
    merged_allowed_values,
    merged_synonyms,
    seed_search_policy,
)

router = APIRouter()


def _effective_rules(row) -> list[dict]:
    """The rules this key is actually read with: its own, or the shipped fallback.

    Derivation uses the shipped table whenever the stored column is empty (see
    `configured_rules`), so reporting the empty column as "no rules" is not a harmless
    simplification - it is the screen contradicting the data next to it.
    """
    from app.services.product_spec_derivation import shipped_rules

    # Reading a column IS a rule, and hiding it behind "there are no rules to edit" was
    # the screen refusing to explain the one key everybody asks about. Shown as a rule
    # of its own kind so the derivation is legible end to end - it is not editable yet,
    # but it is at least visible and named.
    if row.spec_key in _FROM_PRODUCT_RECORD:
        return [{"match": "product_column", "pattern": row.spec_key, "value": None}]

    stored = row.derivation_rules or []
    if stored:
        return stored
    return list(shipped_rules().get(row.spec_key) or [])


def _serialise(row) -> dict:
    return {
        "spec_key": row.spec_key,
        "label": row.label,
        "data_type": row.data_type,
        "unit": row.unit,
        # Shipped values + the ones staff added, minus the ones taken away: consumers
        # see one vocabulary.
        "allowed_values": merged_allowed_values(row),
        # The editable half, so the UI knows which chips it may remove.
        "user_values": list(row.user_values or []),
        # Shipped values this business has taken away. Returned so the UI can show them
        # struck through with a way back, rather than as a chip that silently vanished.
        "suppressed_values": list(row.suppressed_values or []),
        # Catalog values that exist but are not searchable (placeholder brands). Shown
        # so the UI can explain why a value in the data never comes back in a result.
        "excluded_values": row.excluded_values or [],
        # Standing preference for particular values of this key ({"SORENTO": 1.5}).
        "value_weights": {k: float(v) for k, v in (row.value_weights or {}).items()},
        # HOW this key is read out of a product's text. Editable, first match wins.
        #
        # `derivation_rules` is what is STORED; `effective_rules` is what actually runs.
        # They differ whenever a key has never been edited: derivation falls back to the
        # rules that ship in code, so an empty column meant the screen said "no rules
        # yet, so nothing will ever fill this in" about a key sitting on 74 products it
        # had filled in itself. Showing the shipped set is the difference between a
        # configuration screen and a decoration.
        "derivation_rules": row.derivation_rules or [],
        "effective_rules": _effective_rules(row),
        "rules_are_default": not (row.derivation_rules or []),
        # Merged view: consumers see one vocabulary, not the seed/user split.
        "synonyms": merged_synonyms(row),
        "applies_when": row.applies_when or {},
        # Whether rules are the thing that fills this key in. Brand comes off the
        # product's own brand row and the dimensions are parsed out of the measurement
        # block, so for those the rule editor was offering control it does not have -
        # and saying "no rules yet, so nothing will ever fill this in" next to a key
        # with thousands of values.
        "read_from": (
            "product_record"
            if row.spec_key in _FROM_PRODUCT_RECORD
            else "measurement_then_rules"
            if row.spec_key in _MEASUREMENT_KEYS
            else "rules"
        ),
        "rank_weight": float(row.rank_weight) if row.rank_weight is not None else None,
        "measured_coverage": row.measured_coverage,
        # Editing surface: which fields the UI may offer, and what it must not touch.
        "source": row.source or "seed",
        "user_synonyms": row.user_synonyms or {},
        # Shipped words this business has taken away, so the UI can show them struck
        # through rather than silently missing.
        "suppressed_synonyms": row.suppressed_synonyms or {},
        "match_tolerance": float(row.match_tolerance) if row.match_tolerance is not None else 0.0,
        "match_decay": float(row.match_decay) if row.match_decay is not None else 0.0,
        "is_active": bool(row.is_active),
    }


@router.get("")
@router.get("/")
async def get_spec_registry(
    request: Request,
    response: Response,
    current_user: dict = Depends(
        # Reuses the product-master read permission rather than minting a new one:
        # a new permission needs a grant sweep across provisioned roles, and this is
        # product vocabulary that anyone who may read products may read.
        require_permission_with_api_key("master_data.products.view")
    ),
    db: Session = Depends(get_db),
):
    """The active spec vocabulary, with an ETag so the parser can skip re-reading it."""
    try:
        rows = active_registry(db)
        keys = [_serialise(row) for row in rows]
        stamps = [r.updated_at or r.created_at for r in rows]
        updated_at = max(stamps).isoformat() if stamps else None

        payload = {"keys": keys, "updated_at": updated_at}

        # Hash the payload itself rather than the max timestamp: an admin edit that
        # lands in the same second still changes the body, and a stale prompt is
        # worse than a re-read.
        etag = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()[:32]
        etag_header = f'"{etag}"'

        if request.headers.get("if-none-match") == etag_header:
            return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag_header})

        response.headers["ETag"] = etag_header
        response.headers["Cache-Control"] = "private, max-age=60"
        return payload
    except Exception as e:
        raise handle_internal_error(str(e))


# --------------------------------------------------------------------------- #
# writes
# --------------------------------------------------------------------------- #
_EDITABLE_DATA_TYPES = {"enum", "numeric", "boolean"}


class SpecKeyUpdate(BaseModel):
    """What a human may change on an existing key.

    Deliberately narrow. `spec_key`, `data_type` and `unit` are absent because changing
    them on a key that already has derived values against it would silently invalidate
    every stored spec — that is a migration, not an edit.
    """

    label: Optional[str] = Field(default=None, min_length=1, max_length=150)
    rank_weight: Optional[float] = Field(default=None, ge=0, le=100)
    is_active: Optional[bool] = None
    match_tolerance: Optional[float] = Field(default=None, ge=0)
    match_decay: Optional[float] = Field(default=None, ge=0)
    # value -> [extra customer phrasings]. Merged with the seed's, never replacing it.
    user_synonyms: Optional[dict[str, list[str]]] = None
    # value -> [shipped words to stop using for it]. The only way to take a word away.
    suppressed_synonyms: Optional[dict[str, list[str]]] = None
    # Only honoured on a `user` row; a seed row's closed list is the parser's contract.
    allowed_values: Optional[list[str]] = None
    # Calibration, editable on any row: which catalog values are not things a customer
    # searches for. Excluding one hides it from the understanding model and rejects it
    # if the model produces it anyway.
    excluded_values: Optional[list[str]] = None
    # {value: bonus}. A standing preference applied to any product carrying the value,
    # EXCEPT when the customer named this key themselves.
    value_weights: Optional[dict[str, float]] = None
    # Values added to a shipped key. Additive: the seed's own list is untouchable
    # because the n8n parser is held to it.
    user_values: Optional[list[str]] = None
    # Shipped values to stop using. The only way to take a value away, and the mirror
    # of user_values - nothing is deleted, so putting one back is one click.
    suppressed_values: Optional[list[str]] = None
    # Ordered rules that produce this key's value. Editable on ANY row, seed or user:
    # without it a key created here can never be populated, which made the "add a spec"
    # button a promise the engine could not keep.
    derivation_rules: Optional[list[dict]] = None
    # Which products may carry this key at all, as {other_key: [permitted values]}.
    # Calibration rather than vocabulary - "bowl count is not only for kitchen sinks"
    # is a merchandising call - so it is editable and no longer seed-repaired.
    applies_when: Optional[dict[str, list[str]]] = None


class SpecKeyCreate(BaseModel):
    """A brand-new key, owned by whoever created it and never seed-repaired."""

    spec_key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1, max_length=150)
    data_type: str
    unit: Optional[str] = Field(default=None, max_length=16)
    allowed_values: list[str] = Field(default_factory=list)
    user_synonyms: dict[str, list[str]] = Field(default_factory=dict)
    applies_when: dict[str, list[str]] = Field(default_factory=dict)
    rank_weight: float = Field(default=1.0, ge=0, le=100)
    is_active: bool = True


def _reject(message: str, code: str):
    from app.services.error_handler import AppException

    return AppException(status_code=400, message=message, code=code)


def _validate_reachable(data_type: str, allowed_values, synonyms) -> None:
    """An allowed value nobody can say is a value that can never be searched for.

    There is already a test asserting this invariant across the seeded registry; the UI
    must not be able to introduce a violation the seed forbids.
    """
    if data_type != "enum":
        return
    words = {v: list(w) for v, w in (synonyms or {}).items()}
    unreachable = [v for v in (allowed_values or []) if not words.get(v)]
    if unreachable:
        raise _reject(
            "These values have no words a customer could say, so nothing would ever "
            f"match them: {', '.join(unreachable)}. Add at least one synonym each.",
            "spec_registry_unreachable_value",
        )


class PolicyUpdate(BaseModel):
    """One scoring knob. Bounded so a typo cannot make the ranker meaningless."""

    value: float = Field(ge=0, le=100)


@router.get("/policy")
async def get_search_policy(
    current_user: dict = Depends(require_permission_with_api_key("master_data.spec_registry.view")),
    db: Session = Depends(get_db),
):
    """Every scoring knob, with the label and explanation shown beside it in the UI."""
    seed_search_policy(db, commit=True)
    rows = db.query(ProductSpecSearchPolicy).all()
    by_key = {row.policy_key: row for row in rows}
    return {
        "policy": [
            {
                "policy_key": entry["policy_key"],
                "label": entry["label"],
                "help_text": entry["help_text"],
                "value": float(by_key[entry["policy_key"]].value)
                if entry["policy_key"] in by_key
                else float(entry["value"]),
                "default_value": float(entry["value"]),
            }
            for entry in SEARCH_POLICY_SEED
        ]
    }


@router.patch("/policy/{policy_key}")
async def update_search_policy(
    policy_key: str,
    payload: PolicyUpdate,
    current_user: dict = Depends(require_permission_with_api_key("master_data.spec_registry.edit")),
    db: Session = Depends(get_db),
):
    try:
        seed_search_policy(db)
        row = db.query(ProductSpecSearchPolicy).filter_by(policy_key=policy_key).first()
        if row is None:
            raise handle_not_found("Search setting", policy_key)
        row.value = payload.value
        db.commit()
        return {"policy_key": row.policy_key, "value": float(row.value)}
    except Exception as e:
        if type(e).__name__ in {"AppException", "HTTPException"}:
            raise
        raise handle_internal_error(str(e))


# Keys no rule can produce. Only brand: it is read off the product's own brand row and
# there is no text involved at any point.
#
# The dimensions are NOT here. Their primary source is the measurement block in the
# description - an algorithm, not a token list - but rules do fill them in from the
# flyer where the description states no size at all, which is 96 products. Listing them
# here told people rules would do nothing, one screen away from a rule doing something.
_FROM_PRODUCT_RECORD = {"brand"}

# Keys whose PRIMARY source is the measurement block; rules fill the gap it leaves.
_MEASUREMENT_KEYS = {"dim_length", "dim_width", "dim_height", "diameter", "depth", "thickness"}

_RULE_KINDS = {
    "contains",
    "ends_with",
    "present",
    "regex",
    "code_suffix",
    # Read the product CODE rather than its prose. Some facts are only written there:
    # every seat cover carries SRTSC while the descriptions say "SEAT COVER", "SEAT &
    # COVER" or nothing recognisable.
    "code_contains",
    "code_starts_with",
}


def _validate_rules(
    rules: list, *, allowed_values: list | None = None, data_type: str = ""
) -> list[dict]:
    """Reject a rule the engine could not run, at the point someone types it.

    A bad regex is skipped silently at derivation time so one typo cannot stop the
    catalog deriving — which is right at 3am and wrong here, where the person is
    looking at the field and can fix it.
    """
    cleaned: list[dict] = []
    for index, rule in enumerate(rules, start=1):
        if not isinstance(rule, dict):
            raise _reject(f"Rule {index} is not a rule.", "spec_registry_bad_rule")
        kind = str(rule.get("match") or "contains").lower()
        pattern = str(rule.get("pattern") or "").strip()
        if kind not in _RULE_KINDS:
            raise _reject(
                f"Rule {index}: '{kind}' is not a way of matching. "
                f"Use one of {', '.join(sorted(_RULE_KINDS))}.",
                "spec_registry_bad_rule",
            )
        if not pattern:
            raise _reject(f"Rule {index} has nothing to match on.", "spec_registry_bad_rule")
        if kind in {"regex", "present"}:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise _reject(
                    f"Rule {index}: that pattern is not valid ({exc}).",
                    "spec_registry_bad_rule",
                )
        entry: dict = {"match": kind, "pattern": pattern}
        if rule.get("value") is not None:
            entry["value"] = rule["value"]
        if rule.get("capture"):
            entry["capture"] = int(rule["capture"])
        # Carried through, or saving a key from the editor would silently drop it: the
        # hose rule captures metres off the flyer and stores millimetres, and losing the
        # conversion turns 1200 into 1.2 the next time anybody presses Save.
        if rule.get("scale"):
            entry["scale"] = float(rule["scale"])
        if rule.get("unit"):
            entry["unit"] = str(rule["unit"])
        if rule.get("source") and str(rule["source"]).lower() != "any":
            entry["source"] = str(rule["source"]).lower()
        if kind not in {"regex", "present"} and "value" not in entry:
            raise _reject(
                f"Rule {index} needs the value it should produce.", "spec_registry_bad_rule"
            )
        cleaned.append(entry)

    # A rule may only produce a value this key actually has. Someone pointed a mounting
    # rule at `free_standing`, which is not one of the seven mounting values, so the
    # re-read would have written a value the ranker can never match and the search would
    # have silently got worse. Only for a CLOSED list - `brand` and `class` take their
    # values from the catalogue and have no list to check against.
    closed = [str(v) for v in (allowed_values or [])]
    if closed and (data_type or "").lower() == "enum":
        unknown = sorted(
            {
                str(entry["value"])
                for entry in cleaned
                if "value" in entry and str(entry["value"]) not in closed
            }
        )
        if unknown:
            raise _reject(
                f"This specification does not have the value(s) {', '.join(unknown)}. "
                f"It can be one of: {', '.join(closed)}. Point the rule at one of those, "
                "or add the value to this specification first.",
                "spec_registry_unknown_rule_value",
            )
    return cleaned


@router.get("/coverage")
async def get_spec_coverage(
    current_user: dict = Depends(require_permission_with_api_key("master_data.spec_registry.view")),
    db: Session = Depends(get_db),
):
    """How many products actually carry each key, right now.

    A separate call rather than a field on the registry payload: that payload is what
    the n8n parser reads to build its extraction prompt, it is ETag-cached, and a
    number that changes whenever anyone re-reads the catalogue would break the cache
    for a consumer that has no use for it.

    The registry's own `measured_coverage` is a figure recorded when the key was
    written, so it is a note about the past. Where the two disagree the screen should
    show this one — `bowl_count` says 106 and the catalogue holds 148.
    """
    from sqlalchemy import func, text as sql_text

    from app.models.product import Product
    from app.models.product_spec import ProductSpecifications

    rows = (
        db.query(
            func.jsonb_object_keys(ProductSpecifications.values).label("spec_key"),
            func.count().label("n"),
        )
        .join(Product, Product.id == ProductSpecifications.product_id)
        .filter(Product.is_active.is_(True))
        .group_by(sql_text("1"))
        .all()
    )
    return {"coverage": {key: n for key, n in rows}}


@router.get("/keys-for-product")
async def keys_for_product(
    code: str,
    current_user: dict = Depends(require_permission_with_api_key("master_data.spec_registry.view")),
    db: Session = Depends(get_db),
):
    """Which spec keys a given product code carries, and what each one says.

    So the keys table can be filtered by a product rather than only by a word. The
    question "why does SRTWC7614-RL not come back for rimless" is asked about a code,
    and answering it meant opening the product page in another tab and comparing by eye.
    """
    from sqlalchemy import func

    from app.models.product import Product
    from app.models.product_spec import ProductSpecifications

    code = (code or "").strip()
    if not code:
        return {"code": code, "matched_product": None, "keys": {}}

    row = (
        db.query(ProductSpecifications, Product)
        .join(Product, Product.id == ProductSpecifications.product_id)
        .filter(func.upper(Product.product_code) == code.upper())
        .first()
    )
    if row is None:
        return {"code": code, "matched_product": None, "keys": {}}

    spec, product = row
    values = spec.values or {}
    provenance = spec.provenance or {}
    return {
        "code": code,
        "matched_product": {"id": str(product.id), "product_code": product.product_code},
        "keys": {
            key: {
                "value": (entry or {}).get("value"),
                "source": (provenance.get(key) or {}).get("source"),
            }
            for key, entry in values.items()
        },
    }


@router.get("/catalogue-status")
async def get_catalogue_status(
    current_user: dict = Depends(require_permission_with_api_key("master_data.spec_registry.view")),
    db: Session = Depends(get_db),
):
    """Whether the stored specifications were read with the rules that are live now."""
    return product_spec_rederive.status(db)


@router.post("/reread-catalogue")
async def reread_catalogue(
    current_user: dict = Depends(require_permission_with_api_key("master_data.spec_registry.edit")),
    db: Session = Depends(get_db),
):
    """Re-read every product with the current rules.

    Editing a rule changes how a product WOULD be read; the stored values stay as they
    were until this runs. It takes minutes over 22,805 rows, so it runs in the
    background and `catalogue-status` reports on it.
    """
    return product_spec_rederive.start(db)


@router.get("/{spec_key}/products")
async def products_carrying_spec(
    spec_key: str,
    value: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    current_user: dict = Depends(require_permission_with_api_key("master_data.spec_registry.view")),
    db: Session = Depends(get_db),
):
    """Which products actually carry this specification, and what each one says.

    A count on its own ("seen in 106") is not reviewable: it says something happened
    without saying to what. This is how you check a rule did what you meant before
    trusting it in a search - and how you find the row that proves it did not.

    Grouped counts come back with the list so a whole key can be judged at a glance:
    `has_drainer` reading `true` on 74 bathtubs is obvious in the tally and invisible
    in a page of rows.
    """
    from sqlalchemy import func, or_

    from app.models.product import Product
    from app.models.product_spec import ProductSpecifications

    row = db.query(ProductSpecRegistry).filter_by(spec_key=spec_key).first()
    if row is None:
        raise handle_not_found("Spec key", spec_key)

    stored_value = ProductSpecifications.values[spec_key]["value"].astext
    stored_class = ProductSpecifications.values["class"]["value"].astext
    source = ProductSpecifications.provenance[spec_key]["source"].astext

    base = (
        db.query(ProductSpecifications, Product)
        .join(Product, Product.id == ProductSpecifications.product_id)
        .filter(ProductSpecifications.values.has_key(spec_key))  # noqa: W601
        .filter(Product.is_active.is_(True))
    )
    if value is not None:
        base = base.filter(stored_value == value)
    if q and q.strip():
        # Searched in the database rather than in the page, because the list is
        # paginated: filtering the hundred rows on screen would report "no matches" for
        # a product sitting on page three.
        needle = f"%{q.strip()}%"
        base = base.filter(
            or_(
                Product.product_code.ilike(needle),
                Product.description.ilike(needle),
                stored_value.ilike(needle),
                ProductSpecifications.provenance[spec_key]["evidence"].astext.ilike(needle),
            )
        )

    # Counted over the same filter the list uses, so the tally and the rows agree.
    tallies = {
        "by_value": [
            {"value": v, "count": n}
            for v, n in base.with_entities(stored_value, func.count()).group_by(stored_value)
            .order_by(func.count().desc()).limit(30).all()
        ],
        "by_class": [
            {"class": c, "count": n}
            for c, n in base.with_entities(stored_class, func.count()).group_by(stored_class)
            .order_by(func.count().desc()).limit(30).all()
        ],
        "by_source": [
            {"source": s, "count": n}
            for s, n in base.with_entities(source, func.count()).group_by(source)
            .order_by(func.count().desc()).all()
        ],
    }

    total = base.count()
    rows = (
        base.order_by(Product.product_code)
        .offset(max(0, offset))
        .limit(max(1, min(limit, 500)))
        .all()
    )

    return {
        "spec_key": spec_key,
        "label": row.label,
        "total": total,
        **tallies,
        "products": [
            {
                "id": str(product.id),
                "product_code": product.product_code,
                "description": product.description,
                "class": (spec.values.get("class") or {}).get("value"),
                "value": (spec.values.get(spec_key) or {}).get("value"),
                # WHERE it came from and the exact words it was read from, because
                # "why does this say that" is the only question worth asking here.
                "source": (spec.provenance.get(spec_key) or {}).get("source"),
                "evidence": (spec.provenance.get(spec_key) or {}).get("evidence"),
            }
            for spec, product in rows
        ],
    }


@router.post("", status_code=status.HTTP_201_CREATED)
@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_spec_key(
    payload: SpecKeyCreate,
    current_user: dict = Depends(require_permission_with_api_key("master_data.spec_registry.add")),
    db: Session = Depends(get_db),
):
    """Register a new spec key. It is `user`-owned, so no deploy will overwrite it.

    A new key changes what a customer PHRASE can resolve to immediately, but no product
    carries it until a derivation rule exists and the catalog is re-derived. The UI says
    so; this endpoint does not pretend otherwise.
    """
    try:
        if payload.data_type not in _EDITABLE_DATA_TYPES:
            raise _reject(
                f"data_type must be one of {sorted(_EDITABLE_DATA_TYPES)}.",
                "spec_registry_bad_type",
            )
        if db.query(ProductSpecRegistry).filter_by(spec_key=payload.spec_key).first():
            raise _reject(
                f"A spec key named '{payload.spec_key}' already exists.",
                "spec_registry_duplicate",
            )
        _validate_reachable(payload.data_type, payload.allowed_values, payload.user_synonyms)

        tolerance, decay = default_match_window(payload.unit)
        row = ProductSpecRegistry(
            spec_key=payload.spec_key,
            label=payload.label,
            data_type=payload.data_type,
            unit=payload.unit,
            allowed_values=payload.allowed_values,
            synonyms={},
            user_synonyms=payload.user_synonyms,
            applies_when=payload.applies_when,
            rank_weight=payload.rank_weight,
            is_active=payload.is_active,
            match_tolerance=tolerance,
            match_decay=decay,
            source="user",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return _serialise(row)
    except Exception as e:
        if type(e).__name__ == "AppException":
            raise
        raise handle_internal_error(str(e))


@router.patch("/{spec_key}")
async def update_spec_key(
    spec_key: str,
    payload: SpecKeyUpdate = Body(...),
    current_user: dict = Depends(require_permission_with_api_key("master_data.spec_registry.edit")),
    db: Session = Depends(get_db),
):
    """Edit calibration and extend vocabulary. Seed-owned vocabulary stays seed-owned."""
    try:
        row = db.query(ProductSpecRegistry).filter_by(spec_key=spec_key).first()
        if row is None:
            raise handle_not_found("Spec key", spec_key)

        fields = payload.model_dump(exclude_unset=True)

        if "allowed_values" in fields:
            if (row.source or "seed") == "seed":
                raise _reject(
                    "This key's values ship with the product and are kept in step with "
                    "the chatbot parser, so they cannot be edited here. Add customer "
                    "wording instead, or create your own key.",
                    "spec_registry_seed_values_immutable",
                )
            row.allowed_values = fields["allowed_values"]

        if "user_synonyms" in fields:
            row.user_synonyms = {
                value: [w.strip() for w in words if w and w.strip()]
                for value, words in (fields["user_synonyms"] or {}).items()
            }

        if "suppressed_synonyms" in fields:
            row.suppressed_synonyms = {
                value: [w.strip() for w in words if w and w.strip()]
                for value, words in (fields["suppressed_synonyms"] or {}).items()
                if [w for w in words if w and w.strip()]
            }

        if "user_values" in fields:
            shipped = {str(v) for v in (row.allowed_values or [])}
            row.user_values = [
                v.strip()
                for v in (fields["user_values"] or [])
                if v and v.strip() and v.strip() not in shipped
            ]

        if "suppressed_values" in fields:
            # Only shipped values can be suppressed. A staff-added value is removed by
            # dropping it from user_values, and recording it here as well would leave a
            # tombstone that silently blocks re-adding it under the same name.
            shipped = {str(v) for v in (row.allowed_values or [])}
            row.suppressed_values = [
                v.strip()
                for v in (fields["suppressed_values"] or [])
                if v and v.strip() and v.strip() in shipped
            ]

        if "derivation_rules" in fields:
            row.derivation_rules = _validate_rules(
                fields["derivation_rules"] or [],
                # Merged, so a value staff just added is immediately usable in a rule -
                # and INCLUDING the suppressed ones, so taking a value away does not
                # invalidate the rules that read it. Those rules stay stored and stop
                # firing (see configured_rules), which is what makes suppression
                # reversible instead of a one-way delete of somebody's rule.
                allowed_values=[
                    *merged_allowed_values(row),
                    *[str(v) for v in (row.suppressed_values or [])],
                ],
                data_type=row.data_type,
            )

        if "value_weights" in fields:
            row.value_weights = {
                str(value).strip(): float(bonus)
                for value, bonus in (fields["value_weights"] or {}).items()
                if str(value).strip() and float(bonus) != 0
            }

        if "excluded_values" in fields:
            row.excluded_values = [
                v.strip() for v in (fields["excluded_values"] or []) if v and v.strip()
            ]

        if "applies_when" in fields:
            row.applies_when = {
                str(key).strip(): [str(v).strip() for v in (values or []) if str(v).strip()]
                for key, values in (fields["applies_when"] or {}).items()
                if str(key).strip() and [v for v in (values or []) if str(v).strip()]
            }

        for field in ("label", "rank_weight", "is_active", "match_tolerance", "match_decay"):
            if field in fields and fields[field] is not None:
                setattr(row, field, fields[field])

        # A value nobody can say is unsearchable, and a newly added one has no words
        # yet. Rather than refusing the save, give it the obvious word - its own name,
        # readably - which is what the person adding "free_standing" meant anyway. They
        # can add more beside it.
        if row.user_values:
            words = dict(row.user_synonyms or {})
            for value in row.user_values:
                if not words.get(value) and not (row.synonyms or {}).get(value):
                    words[value] = [str(value).replace("_", " ")]
            row.user_synonyms = words

        _validate_reachable(row.data_type, merged_allowed_values(row), merged_synonyms(row))

        db.commit()
        db.refresh(row)
        return _serialise(row)
    except Exception as e:
        if type(e).__name__ in {"AppException", "HTTPException"}:
            raise
        raise handle_internal_error(str(e))


@router.delete("/{spec_key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_spec_key(
    spec_key: str,
    current_user: dict = Depends(
        require_permission_with_api_key("master_data.spec_registry.delete")
    ),
    db: Session = Depends(get_db),
):
    """Delete a user-created key. Seeded keys are deactivated, never deleted.

    A seeded key would simply reappear on the next deploy, so offering "delete" for one
    would be a button that silently does nothing.
    """
    try:
        row = db.query(ProductSpecRegistry).filter_by(spec_key=spec_key).first()
        if row is None:
            raise handle_not_found("Spec key", spec_key)
        if (row.source or "seed") == "seed":
            raise _reject(
                "This key ships with the product and would come back on the next "
                "deploy. Switch it off instead.",
                "spec_registry_seed_undeletable",
            )
        db.delete(row)
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as e:
        if type(e).__name__ in {"AppException", "HTTPException"}:
            raise
        raise handle_internal_error(str(e))
