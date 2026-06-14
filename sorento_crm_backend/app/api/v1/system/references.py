"""Entity reference resolution endpoint.

Exposes the deterministic entity resolver as an HTTP API so the MCP layer (or any
external caller) can disambiguate codes mid-turn. The resolver itself lives in
`app.services.entity_resolver`.
"""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from sqlalchemy import String as _String
from sqlalchemy import cast as _cast
from sqlalchemy import func, or_
from sqlalchemy.dialects.postgresql import ARRAY as _ARRAY
from sqlalchemy.orm import Session

from sqlalchemy import or_ as _sa_or

from app.database import get_db
from app.dependencies import get_external_api_user
from app.models.access import ContactAccessType
from app.models.marketing import Promotion, PromotionProduct
from app.models.product import Brand, Product
from app.models.resources import Attachment, AttachmentType
from app.services.entity_resolver import (
    _canonical_entity_type,
    resolve_references,
    resolve_references_intersection,
)


# Canonical entity types the resolver understands. domain_hint matching one of
# these is treated as an entity-scope hint (merged into allowed_entity_types)
# rather than an AttachmentType lookup. Includes the brand / category fan-out
# aliases so callers can pass either the alias or the concrete type.
_RESOLVER_ENTITY_TYPES: frozenset[str] = frozenset({
    "product",
    "customer_order",
    "customer",
    "inbound_shipment",
    "spo_allocation",
    "grn",
    "warehouse",
    "supplier",
    "promotion",
    "transporter",
    "form",
    "attachment",
    "attachment_type",
    "brand",
    "category",
})
from app.services.query_normalizer import DOMAIN_STOPWORDS

router = APIRouter(prefix="/references")


_ALLOWED_MATCH_MODES = {"or", "and"}

# Union of every domain's noise words. Tokens like "order 202605-2651" come in
# from chatbot phrasing — the user means the order_number, not a literal
# substring. Cleaning leaves "202605-2651" so the exact-match probe succeeds.
_ENTITY_STOPWORDS: frozenset[str] = frozenset().union(*DOMAIN_STOPWORDS.values())
_TOKEN_PUNCT_STRIP = ".,!?;:\"'()[]{}"


def _resolve_attachment_type_for_hint(db: Session, hint: str):
    """Resolve a domain_hint string → AttachmentType row, or None.

    Mirrors the matcher in `AttachmentService.list_attachments(attachment_type_code=...)`
    so MCP / API callers get identical type-resolution behavior whether they
    pre-filter attachments or use this resolver.
    """
    if not hint or not hint.strip():
        return None
    code_norm = hint.strip()
    variants = {code_norm}
    low = code_norm.lower()
    if low == "catalog":
        variants.add("catalogue")
    elif low == "catalogue":
        variants.add("catalog")
    for variant in variants:
        row = (
            db.query(AttachmentType)
            .filter(AttachmentType.code.ilike(variant))
            .first()
            or db.query(AttachmentType)
            .filter(AttachmentType.type_name.ilike(variant))
            .first()
        )
        if row is not None:
            return row
    return None


def _resolve_with_domain_hint(
    db: Session,
    hint: str,
    tokens: list[str],
    query_text: str,
) -> dict[str, Any]:
    """Short-circuit resolver: ILIKE search within one AttachmentType bucket.

    Returns a ResolutionResult-shaped dict. Per-token search on filename +
    description, scoped to `attachment_type_id = <resolved hint type>`. When
    the hint resolves to no AttachmentType, returns an empty payload with
    `domain_hint_unresolved=True` so the agent knows the hint label was bad.
    """
    type_row = _resolve_attachment_type_for_hint(db, hint)
    base_empty: dict[str, Any] = {
        "tokens": list(tokens) if tokens else ([query_text] if query_text else []),
        "elapsed_ms": 0.0,
        "resolutions": [],
        "unresolved_tokens": [],
        "ambiguous_tokens": [],
        "domain_hint": hint,
    }
    if type_row is None:
        base_empty["domain_hint_unresolved"] = True
        return base_empty

    # Build search term list. Prefer explicit tokens; fall back to splitting
    # the free-text query on whitespace (≥3 chars per term).
    if tokens:
        terms = [t.strip() for t in tokens if t and t.strip()]
    else:
        terms = [w for w in (query_text or "").split() if len(w) >= 3]
    if not terms:
        # Empty input — return all attachments of this type capped at 20 so the
        # caller still gets the catalogue browse shape.
        terms = [""]

    type_id = str(type_row.id)
    PER_TOKEN_CAP = 20
    base_empty["domain_hint_attachment_type_id"] = type_id
    base_empty["domain_hint_attachment_type_name"] = type_row.type_name

    resolutions: list[dict[str, Any]] = []
    for term in terms:
        q = (
            db.query(
                Attachment.id,
                Attachment.original_filename,
                Attachment.description,
                Attachment.mime_type,
                Attachment.full_directory_path,
            )
            .filter(
                Attachment.attachment_type_id == type_id,
                Attachment.is_deleted.is_(False),
            )
        )
        if term:
            wild = f"%{term}%"
            q = q.filter(
                _sa_or(
                    Attachment.original_filename.ilike(wild),
                    Attachment.description.ilike(wild),
                )
            )
        rows = q.limit(PER_TOKEN_CAP).all()
        matches = [
            {
                "entity_type": "attachment",
                "canonical_code": filename,
                "uuid": str(aid) if aid else None,
                "match_field": "original_filename",
                "match_tier": "substring" if term else "scope",
                "similarity": None,
                "display": {
                    "filename": filename,
                    "description": description,
                    "attachment_type": type_row.type_name,
                    "mime_type": mime,
                    "directory": dir_path,
                },
            }
            for aid, filename, description, mime, dir_path in rows
        ]
        resolutions.append(
            {
                "token": term or hint,
                "resolved": len(matches) == 1,
                "ambiguous": len(matches) > 1,
                "matches": matches,
            }
        )
    base_empty["resolutions"] = resolutions
    base_empty["unresolved_tokens"] = [r["token"] for r in resolutions if not r["matches"]]
    base_empty["ambiguous_tokens"] = [r["token"] for r in resolutions if r["ambiguous"]]
    return base_empty


def _strip_entity_stopwords(token: str) -> str:
    """Drop entity-type noise words from a multi-word token; preserve original on empty result."""
    if not token:
        return token
    raw = token.strip()
    if " " not in raw:
        return token
    parts = [p for p in raw.split() if p]
    kept = [p for p in parts if p.lower().strip(_TOKEN_PUNCT_STRIP) not in _ENTITY_STOPWORDS]
    cleaned = " ".join(kept).strip()
    return cleaned or token


# Entity types whose canonical labels are pure-alpha words ("catalogue",
# "brochure", "spec sheet") and therefore bypass the code-token regex used by
# `extract_candidate_tokens`. When the caller hints one of these types in
# `allowed_entity_types` but supplies no explicit `tokens`, we synthesize tokens
# by splitting the query on whitespace so the probes still receive candidates.
_ALPHA_TOKEN_TYPES: frozenset[str] = frozenset({"attachment_type"})


def _synthesize_alpha_tokens(query: str) -> list[str]:
    """Whitespace split → drop stopwords / punctuation / short noise.

    Mirrors `extract_candidate_tokens` semantics for pure-alpha entity types.
    Keeps each word as its own token (single-word lookup), plus the full
    cleaned phrase (multi-word lookup like "spec sheet") so both shapes match.
    """
    if not query or not query.strip():
        return []
    words = [
        w.strip(_TOKEN_PUNCT_STRIP)
        for w in query.split()
        if w.strip(_TOKEN_PUNCT_STRIP)
    ]
    out: list[str] = []
    seen: set[str] = set()
    cleaned_words = [w for w in words if len(w) >= 3 and w.lower() not in _ENTITY_STOPWORDS]
    if len(cleaned_words) >= 2:
        phrase = " ".join(cleaned_words).strip()
        if phrase:
            out.append(phrase)
            seen.add(phrase.lower())
    for w in cleaned_words:
        key = w.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(w)
    return out


_ACCESS_FILTERED_TYPES: frozenset[str] = frozenset({"promotion", "attachment"})


def _apply_limit(result: dict[str, Any], limit: int | None) -> dict[str, Any]:
    """Cap per-token `matches` and `intersection` to `limit`. None / <=0 = no cap.

    Re-derives `resolved` and `unresolved_tokens` after truncation so callers
    don't see stale flags. `by_entity_type` regrouped from the truncated
    intersection so AND-mode counts stay consistent.
    """
    if not isinstance(result, dict) or not limit or limit <= 0:
        return result
    new_result = dict(result)
    if isinstance(result.get("resolutions"), list):
        new_resolutions = []
        for tr in result["resolutions"]:
            new_tr = dict(tr)
            matches = list(tr.get("matches") or [])
            if len(matches) > limit:
                matches = matches[:limit]
            new_tr["matches"] = matches
            new_tr["resolved"] = len(matches) == 1 and not tr.get("ambiguous", False)
            new_resolutions.append(new_tr)
        new_result["resolutions"] = new_resolutions
        new_result["unresolved_tokens"] = [
            r["token"] for r in new_resolutions if not (r.get("matches") or [])
        ]
    if isinstance(result.get("intersection"), list):
        capped = list(result["intersection"])[:limit]
        new_result["intersection"] = capped
        new_result["empty"] = not capped
        by_type: dict[str, list[dict[str, Any]]] = {}
        for m in capped:
            by_type.setdefault(m.get("entity_type", ""), []).append(m)
        new_result["by_entity_type"] = by_type
    return new_result


def _resolve_promotion_ids_for_token(
    db: Session, token: str, allowed_access_codes: set[str] | None
) -> set[str]:
    """Find promotion UUIDs whose description matches `token`.

    Contiguous substring + per-word AND search on Promotion.description.
    When `allowed_access_codes` is non-empty, intersects with
    Promotion.access_levels JSONB so the agent only ever surfaces promos the
    contact can see.
    """
    tok = (token or "").strip()
    if not tok:
        return set()
    q = db.query(Promotion.id, Promotion.description, Promotion.access_levels)
    q = q.filter(Promotion.description.ilike(f"%{tok}%"))
    rows = q.limit(50).all()
    # Per-word AND fallback for multi-word phrases ("water closet promo").
    if not rows:
        words = [w for w in tok.split() if len(w) >= 3]
        if words:
            q2 = db.query(Promotion.id, Promotion.description, Promotion.access_levels)
            for w in words:
                q2 = q2.filter(Promotion.description.ilike(f"%{w}%"))
            rows = q2.limit(50).all()
    out: set[str] = set()
    for pid, _desc, levels in rows:
        if allowed_access_codes:
            if not isinstance(levels, list) or not allowed_access_codes.intersection(levels):
                continue
        out.add(str(pid))
    return out


def _build_promotion_resolutions(
    db: Session, promotion_ids: set[str]
) -> list[dict[str, Any]]:
    """Synthesize promotion ResolvedEntity dicts for the supplied promo UUIDs.

    Used when `domain_hint=promotion` and the resolver itself didn't run the
    promotion probe (e.g. caller's whitelist was `[product]`). Returns
    `entity_type=promotion` rows so the agent sees promotion candidates ranked
    first — domain_hint is highest priority.
    """
    if not promotion_ids:
        return []
    rows = (
        db.query(Promotion.id, Promotion.description, Promotion.is_active)
        .filter(Promotion.id.in_(promotion_ids))
        .all()
    )
    return [
        {
            "entity_type": "promotion",
            "canonical_code": str(pid),
            "uuid": str(pid),
            "match_field": "description",
            "match_tier": "domain_hint",
            "similarity": None,
            "display": {
                "description": desc,
                "is_active": bool(is_active),
            },
        }
        for pid, desc, is_active in rows
    ]


def _build_product_resolutions_from_promotions(
    db: Session, token: str, promotion_ids: set[str]
) -> list[dict[str, Any]]:
    """For each product in the given promotions, build a ResolvedEntity dict.

    Tagged `entity_type=product`, `match_tier=through_promotion`,
    `match_field=promotion_membership`. Display carries the promotion
    description(s) the product is linked to so the agent can answer "X is in
    these promos" without an extra round-trip.
    """
    if not promotion_ids:
        return []
    rows = (
        db.query(
            Product.id,
            Product.product_code,
            Product.product_name,
            PromotionProduct.promotion_id,
            Promotion.description,
        )
        .join(PromotionProduct, PromotionProduct.product_id == Product.id)
        .join(Promotion, Promotion.id == PromotionProduct.promotion_id)
        .filter(PromotionProduct.promotion_id.in_(promotion_ids))
        .all()
    )
    by_product: dict[str, dict[str, Any]] = {}
    for pid, code, name, promo_id, promo_desc in rows:
        key = str(pid)
        entry = by_product.setdefault(
            key,
            {
                "entity_type": "product",
                "canonical_code": code,
                "uuid": key,
                "match_field": "promotion_membership",
                "match_tier": "through_promotion",
                "similarity": None,
                "display": {
                    "product_name": name,
                    "via_token": token,
                    "promotions": [],
                },
            },
        )
        promos = entry["display"]["promotions"]
        if {"promotion_id": str(promo_id), "description": promo_desc} not in promos:
            promos.append({"promotion_id": str(promo_id), "description": promo_desc})
    return list(by_product.values())


def _translate_access_names_to_codes(
    db: Session, names: list[str] | None
) -> set[str]:
    """Lowercase-name lookup against contact_access_types.code. Empty in → empty out."""
    if not names:
        return set()
    lowered = {n.strip().lower() for n in names if n and n.strip()}
    if not lowered:
        return set()
    return {
        r[0]
        for r in db.query(ContactAccessType.code)
        .filter(func.lower(ContactAccessType.name).in_(lowered))
        .all()
    }


def _resolve_products_by_brand_access(
    db: Session,
    token: str,
    access_codes: set[str],
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Find products whose brand.access_levels intersect `access_codes` AND
    whose code / name / description matches `token` (substring + per-word AND).

    Used by the promotion-domain fallback: when no promotion matches the
    token under the caller's access levels, surface products from brands the
    contact can see — gives the agent enough context to answer "no promo
    found, but here are matching products".

    `access_codes` is REQUIRED for this helper to run. Callers must scope to
    the promotion-domain path; other domains should use the regular product
    probes (no brand-access gating).
    """
    if not token or not access_codes:
        return []
    tok = token.strip()
    base = (
        db.query(
            Product.id,
            Product.product_code,
            Product.product_name,
            Brand.id.label("brand_id"),
            Brand.brand_code,
            Brand.brand_name,
        )
        .join(Brand, Brand.id == Product.brand_id)
        .filter(
            Brand.access_levels.op("?|")(
                _cast(list(access_codes), _ARRAY(_String))
            )
        )
    )
    # Contiguous substring on code/name/description.
    sub = f"%{tok}%"
    rows = (
        base.filter(
            or_(
                Product.product_code.ilike(sub),
                Product.product_name.ilike(sub),
                Product.description.ilike(sub),
            )
        )
        .limit(limit)
        .all()
    )
    # Per-word AND fallback for multi-word phrases that don't match
    # contiguously (e.g. "wash basin promo" vs a name with extra words).
    if not rows:
        words = [w for w in tok.split() if len(w) >= 3]
        if words:
            q = base
            for w in words:
                ws = f"%{w}%"
                q = q.filter(
                    or_(
                        Product.product_name.ilike(ws),
                        Product.description.ilike(ws),
                    )
                )
            rows = q.limit(limit).all()
    out: list[dict[str, Any]] = []
    for pid, code, name, brand_id, brand_code, brand_name in rows:
        out.append(
            {
                "entity_type": "product",
                "canonical_code": code,
                "uuid": str(pid) if pid else None,
                "match_field": "brand_access",
                "match_tier": "brand_access_fallback",
                "similarity": None,
                "display": {
                    "product_name": name,
                    "via_token": tok,
                    "brand": {
                        "brand_id": str(brand_id) if brand_id else None,
                        "brand_code": brand_code,
                        "brand_name": brand_name,
                    },
                },
            }
        )
    return out


def _caller_wants_products(allowed_entity_types: list[str] | None) -> bool:
    """True only when the caller's RAW whitelist canonicalizes to `product`.

    Brand / category aliases also canonicalize to `product` via
    `_DOMAIN_HINT_EXPANSIONS`, but the caller did NOT explicitly ask for
    products in those cases — they want promotion headers. We use this flag
    to gate the through-promotion product expansion so a `brand` hint with
    matched promotions stays at promotion-level only.
    """
    if not allowed_entity_types:
        return False
    from app.services.entity_resolver import _canonical_entity_type as _canon  # local to avoid cycles
    for raw in allowed_entity_types:
        if (raw or "").strip().lower() in {"product", "products", "master_product", "master_products", "product_attachment", "product_attachments"}:
            return True
    return False


def _expand_products_via_promotions(
    db: Session,
    result: dict[str, Any],
    tokens: list[str],
    access_level_names: list[str] | None,
    wants_products: bool = True,
) -> dict[str, Any]:
    """Replace product matches with products surfaced via the matched promos.

    Strategy when domain_hint=promotion:
      1. For each token, find promotion UUIDs whose description matches.
      2. Optionally filter promos by access_levels intersection.
      3. Look up all products in those promotions.
      4. Replace the token's `product` matches with these — they are the
         products the user actually wants ("send me water closet promotion"
         means "give me products in water-closet promos").

    Non-product entities (attachments, promotions themselves, etc.) stay
    untouched so the agent can still surface promo headers / flyers alongside
    the products.
    """
    if not isinstance(result, dict):
        return result

    # Translate access-level names to codes once.
    allowed_codes: set[str] = set()
    if access_level_names:
        names_lower = {n.strip().lower() for n in access_level_names if n and n.strip()}
        if names_lower:
            allowed_codes = {
                r[0]
                for r in db.query(ContactAccessType.code)
                .filter(func.lower(ContactAccessType.name).in_(names_lower))
                .all()
            }

    new_result = dict(result)

    # Ordering rule: domain_hint=promotion makes promotion the highest-priority
    # entity. Surface promotion entries FIRST (synthesized from matched
    # promo UUIDs, dedup-safe vs ones already present), then the
    # through-promotion products. Non-promotion / non-product entities (e.g.
    # attachments) keep their original position at the tail.
    if isinstance(result.get("resolutions"), list):
        new_resolutions = []
        for tr in result["resolutions"]:
            tok = tr.get("token") or ""
            promo_ids = _resolve_promotion_ids_for_token(db, tok, allowed_codes or None)
            promo_matches = _build_promotion_resolutions(db, promo_ids)

            existing = tr.get("matches", []) or []
            existing_promo_uuids = {
                str(m.get("uuid"))
                for m in existing
                if m.get("entity_type") == "promotion" and m.get("uuid")
            }
            kept_other = [
                m for m in existing
                if m.get("entity_type") not in ("product", "promotion")
            ]
            kept_existing_promos = [
                m for m in existing if m.get("entity_type") == "promotion"
            ]
            new_promo_matches = [
                m for m in promo_matches if str(m.get("uuid")) not in existing_promo_uuids
            ]

            # Promo-first short-circuit: when any promotion matches exist
            # (existing or synthesized), DON'T expand to through-promotion
            # products. domain_hint=promotion makes promotion the answer the
            # caller wants — product enumeration would be noise.
            has_promo = bool(kept_existing_promos or new_promo_matches)
            if has_promo:
                product_matches: list[dict[str, Any]] = []
            elif promo_ids and wants_products:
                product_matches = _build_product_resolutions_from_promotions(
                    db, tok, promo_ids
                )
            elif not promo_ids and allowed_codes:
                # Rescue path: no promo for this token under active access
                # levels → surface products from brands the contact can see.
                # Runs even when caller didn't ask for products so the agent
                # has SOMETHING to answer with rather than empty.
                product_matches = _resolve_products_by_brand_access(
                    db, tok, allowed_codes
                )
            else:
                product_matches = []

            new_matches = (
                kept_existing_promos
                + new_promo_matches
                + product_matches
                + kept_other
            )
            new_tr = dict(tr)
            new_tr["matches"] = new_matches
            new_tr["resolved"] = len(new_matches) == 1 and not tr.get("ambiguous", False)
            if len(new_matches) > 1:
                new_tr["ambiguous"] = True
            new_resolutions.append(new_tr)
        new_result["resolutions"] = new_resolutions
        new_result["unresolved_tokens"] = [
            r["token"] for r in new_resolutions if not (r.get("matches") or [])
        ]

    if isinstance(result.get("intersection"), list):
        # AND-mode: INTERSECT promo sets across tokens. Caller chose AND mode
        # because they want promotions matching EVERY token ("kitchen tap"
        # AND "Sorento"). Earlier union behaviour returned the OR of token
        # results which surfaced unrelated Sorento promos.
        promo_sets: list[set[str]] = [
            _resolve_promotion_ids_for_token(db, tok, allowed_codes or None)
            for tok in tokens
            if tok
        ]
        if promo_sets:
            union_promos = set.intersection(*promo_sets)
        else:
            union_promos = set()
        promo_matches = _build_promotion_resolutions(db, union_promos)
        existing_inter = result["intersection"] or []
        existing_promo_uuids = {
            str(m.get("uuid"))
            for m in existing_inter
            if m.get("entity_type") == "promotion" and m.get("uuid")
        }
        kept_other = [
            m for m in existing_inter
            if m.get("entity_type") not in ("product", "promotion")
        ]
        kept_existing_promos = [
            m for m in existing_inter if m.get("entity_type") == "promotion"
        ]
        new_promo_matches = [
            m for m in promo_matches if str(m.get("uuid")) not in existing_promo_uuids
        ]
        # Same promo-first short-circuit as the OR-mode branch above.
        has_promo = bool(kept_existing_promos or new_promo_matches)
        if has_promo:
            product_matches = []
        elif union_promos and wants_products:
            product_matches = _build_product_resolutions_from_promotions(
                db, " ".join(tokens), union_promos
            )
        elif not union_promos and allowed_codes:
            # AND-mode brand-access fallback: intersect per-token brand-access
            # product sets so the answer set still respects every token.
            per_token_sets: list[list[dict[str, Any]]] = []
            for tok in tokens:
                if not tok:
                    continue
                per_token_sets.append(
                    _resolve_products_by_brand_access(db, tok, allowed_codes)
                )
            if not per_token_sets:
                product_matches = []
            else:
                shared_ids: set[str] | None = None
                for lst in per_token_sets:
                    ids = {str(m["uuid"]) for m in lst if m.get("uuid")}
                    shared_ids = ids if shared_ids is None else shared_ids & ids
                product_matches = []
                if shared_ids:
                    seen: set[str] = set()
                    for lst in per_token_sets:
                        for m in lst:
                            uid = str(m.get("uuid") or "")
                            if uid in shared_ids and uid not in seen:
                                seen.add(uid)
                                product_matches.append(m)
        else:
            product_matches = []
        new_intersection = (
            kept_existing_promos
            + new_promo_matches
            + product_matches
            + kept_other
        )
        new_result["intersection"] = new_intersection
        new_result["empty"] = not new_intersection

    return new_result


def _filter_products_in_promotions(db: Session, result: dict[str, Any]) -> dict[str, Any]:
    """When domain_hint=promotion, drop product matches not linked to any promotion.

    The agent's intent under a promotion domain is "find products that have an
    active promo" — surfacing products that aren't in any `promotion_products`
    row wastes context. Walks resolutions + intersection, collects product
    UUIDs, queries `promotion_products.product_id` once, and filters out the
    misses. Non-product entities untouched. Idempotent: re-running on an
    already-filtered payload is a no-op.
    """
    if not isinstance(result, dict):
        return result

    # Collect product UUIDs across both shapes.
    product_ids: set[str] = set()

    def _collect_from_matches(matches: Any) -> None:
        if not isinstance(matches, list):
            return
        for m in matches:
            if isinstance(m, dict) and m.get("entity_type") == "product" and m.get("uuid"):
                product_ids.add(str(m["uuid"]))

    for tr in result.get("resolutions", []) or []:
        _collect_from_matches(tr.get("matches"))
    _collect_from_matches(result.get("intersection"))

    if not product_ids:
        return result

    rows = (
        db.query(PromotionProduct.product_id)
        .filter(PromotionProduct.product_id.in_(product_ids))
        .distinct()
        .all()
    )
    kept_ids: set[str] = {str(r[0]) for r in rows if r[0]}

    if kept_ids == product_ids:
        return result  # everything already linked — no-op

    def _filter_matches(matches: Any) -> list[Any]:
        if not isinstance(matches, list):
            return matches if matches is not None else []
        out: list[Any] = []
        for m in matches:
            if (
                isinstance(m, dict)
                and m.get("entity_type") == "product"
                and m.get("uuid")
                and str(m["uuid"]) not in kept_ids
            ):
                continue
            out.append(m)
        return out

    new_result = dict(result)
    new_resolutions: list[dict[str, Any]] = []
    for tr in result.get("resolutions", []) or []:
        new_tr = dict(tr)
        new_matches = _filter_matches(tr.get("matches"))
        new_tr["matches"] = new_matches
        new_tr["resolved"] = len(new_matches) == 1 and not tr.get("ambiguous", False)
        new_resolutions.append(new_tr)
    if new_resolutions:
        new_result["resolutions"] = new_resolutions
        new_result["unresolved_tokens"] = [
            r["token"] for r in new_resolutions if not (r.get("matches") or [])
        ]
    if "intersection" in result:
        new_result["intersection"] = _filter_matches(result.get("intersection"))
        new_result["empty"] = not new_result["intersection"]
    return new_result


def _apply_promotion_access_levels_filter(
    db: Session,
    result: dict[str, Any],
    access_level_names: list[str] | None,
) -> dict[str, Any]:
    """Drop promotion / attachment matches whose `access_levels` JSONB does not
    intersect the caller-supplied access-level NAMES.

    Names are translated to canonical `contact_access_types.code` values (case-
    insensitive name match) before intersection, because both
    `Promotion.access_levels` and `Attachment.access_levels` store codes. Other
    entity types are untouched. Empty / missing `access_level_names` is a no-op.
    """
    if not access_level_names:
        return result
    names_lower = {n.strip().lower() for n in access_level_names if n and n.strip()}
    if not names_lower:
        return result

    code_rows = (
        db.query(ContactAccessType.code)
        .filter(func.lower(ContactAccessType.name).in_(names_lower))
        .all()
    )
    allowed_codes: set[str] = {r[0] for r in code_rows}

    def _collect_ids_by_type() -> dict[str, set[str]]:
        bucket: dict[str, set[str]] = {t: set() for t in _ACCESS_FILTERED_TYPES}
        for tr in result.get("resolutions", []) or []:
            for m in tr.get("matches", []) or []:
                et = m.get("entity_type")
                if et in _ACCESS_FILTERED_TYPES and m.get("uuid"):
                    bucket[et].add(str(m["uuid"]))
        for m in result.get("intersection", []) or []:
            et = m.get("entity_type")
            if et in _ACCESS_FILTERED_TYPES and m.get("uuid"):
                bucket[et].add(str(m["uuid"]))
        return bucket

    ids_by_type = _collect_ids_by_type()
    keep_by_type: dict[str, set[str]] = {t: set() for t in _ACCESS_FILTERED_TYPES}

    if allowed_codes and ids_by_type["promotion"]:
        for pid, levels in (
            db.query(Promotion.id, Promotion.access_levels)
            .filter(Promotion.id.in_(list(ids_by_type["promotion"])))
            .all()
        ):
            if isinstance(levels, list) and allowed_codes.intersection(levels):
                keep_by_type["promotion"].add(str(pid))

    if allowed_codes and ids_by_type["attachment"]:
        for aid, levels in (
            db.query(Attachment.id, Attachment.access_levels)
            .filter(Attachment.id.in_(list(ids_by_type["attachment"])))
            .all()
        ):
            if isinstance(levels, list) and allowed_codes.intersection(levels):
                keep_by_type["attachment"].add(str(aid))

    def _keep(m: dict[str, Any]) -> bool:
        et = m.get("entity_type")
        if et not in _ACCESS_FILTERED_TYPES:
            return True
        return str(m.get("uuid") or "") in keep_by_type.get(et, set())

    if "resolutions" in result:
        for tr in result["resolutions"]:
            tr["matches"] = [m for m in tr.get("matches", []) if _keep(m)]
            tr["resolved"] = bool(tr["matches"]) and not tr.get("ambiguous", False)
        result["unresolved_tokens"] = [
            tr["token"] for tr in result["resolutions"] if not tr["matches"]
        ]

    if "intersection" in result:
        result["intersection"] = [m for m in result["intersection"] if _keep(m)]
        by_type: dict[str, list[dict[str, Any]]] = {}
        for m in result["intersection"]:
            by_type.setdefault(m["entity_type"], []).append(m)
        result["by_entity_type"] = by_type
        result["empty"] = not result["intersection"]
        if result["empty"]:
            result["unresolved_tokens"] = list(result.get("tokens", []))

    return result


class ResolveReferenceRequest(BaseModel):
    """POST body for /references/resolve."""

    model_config = ConfigDict(populate_by_name=True)

    query: str = Field(default="", description="Free-text query or a single code to resolve.")
    tokens: list[str] | None = Field(
        default=None,
        description="Optional pre-extracted tokens. If provided, resolver skips regex extraction.",
    )
    match_mode: str = Field(
        default="or",
        description=(
            "'or' (default): each token resolves independently — per-token candidate lists, "
            "ambiguity surfaced per token. 'and': cross-token intersection — returns ONLY rows "
            "whose concatenated searchable columns contain EVERY token. Use 'and' for compound "
            "filters like 'cabana filter tap promotion'. Code-only entity types (SPO / GRN / "
            "inbound shipment) are skipped in 'and' mode."
        ),
    )
    allowed_entity_types: list[str] | None = Field(
        default=None,
        description=(
            "Restrict resolution to these entity types. Always treated as a set "
            "filter / whitelist: every token is probed against EVERY supplied type "
            "(cross product). Example — tokens=['Sorento water closet','latest "
            "promo'] with allowed_entity_types=['product','promotion'] resolves "
            "both tokens against both product and promotion probes. Callers that "
            "need 1:1 positional pairing (token[i] resolved only against "
            "allowed_entity_types[i]) must issue one resolve call per pair.\n\n"
            "Canonical types: product, customer_order, customer, inbound_shipment, "
            "spo_allocation, grn, warehouse, supplier, promotion, transporter, "
            "form, attachment, attachment_type. `attachment_type` resolves a doc-"
            "class label (e.g. 'catalogue', 'brochure', 'spec sheet') to the "
            "AttachmentType UUID for downstream `attachment_type_ids` filters; "
            "pure-alpha labels bypass the code-token regex so callers may pass "
            "them via `query` (auto-split on whitespace) or `tokens` explicitly."
        ),
    )
    access_levels: list[str] | None = Field(
        default=None,
        description=(
            "Post-filter for promotion AND attachment matches. Array of contact-"
            "access-type NAMES (e.g. ['Dealer','End User']) — translated to codes "
            "via contact_access_types.name and intersected with the entity's "
            "`access_levels` JSONB column. A match survives only when at least one "
            "of its stored access codes is in the translated set. Non-promotion / "
            "non-attachment matches are untouched. Empty / null → no-op."
        ),
    )
    fallback_to_all_types: bool = Field(
        default=False,
        description=(
            "Safety net for wrong entity-type guesses by the upstream agent. When "
            "`allowed_entity_types` is set AND the first pass yields zero resolved "
            "tokens, the resolver re-runs with `allowed_entity_types=None` and tags "
            "the response with `fallback_applied: true` + `fallback_types_found` "
            "(the entity types of the recovered matches). Lets the agent recover "
            "from picking 'order' when the user actually meant 'customer'."
        ),
    )
    limit: int | None = Field(
        default=None,
        ge=1,
        le=200,
        description=(
            "Cap returned matches. Applied per-token (each resolution's "
            "`matches` truncated to `limit`) AND to `intersection` in AND-mode. "
            "Omit / null = no cap (current default behaviour)."
        ),
    )
    domain_hint: str | None = Field(
        default=None,
        validation_alias=AliasChoices("domain_hint", "domain"),
        description=(
            "Accepts `domain_hint` or its alias `domain`. "
            "Scope the resolution to attachments of a specific AttachmentType "
            "(matched case-insensitively against `code` then `type_name`, with "
            "catalog ↔ catalogue spelling variants). When set, the resolver "
            "SHORT-CIRCUITS the normal entity probes and ILIKE-matches the "
            "supplied tokens / query against `Attachment.original_filename` / "
            "`description` filtered to that type. Returns ResolvedEntity rows "
            "with `entity_type='attachment'` whose UUIDs feed downstream tools "
            "like `crm_resource_attachments_catalogue`. Example: domain_hint="
            "'catalogue' + tokens=['Sorento'] returns catalogue attachments "
            "containing 'Sorento'."
        ),
    )


def _result_has_zero_matches(result: dict[str, Any]) -> bool:
    """True when neither OR-mode nor AND-mode produced any match."""
    if "intersection" in result:
        return not result.get("intersection")
    for tr in result.get("resolutions", []) or []:
        if tr.get("matches"):
            return False
    return True


def _collect_match_types(result: dict[str, Any]) -> list[str]:
    """Distinct `entity_type` values across resolutions / intersection."""
    types: set[str] = set()
    for tr in result.get("resolutions", []) or []:
        for m in tr.get("matches", []) or []:
            t = m.get("entity_type")
            if t:
                types.add(t)
    for m in result.get("intersection", []) or []:
        t = m.get("entity_type")
        if t:
            types.add(t)
    return sorted(types)


def _resolve_input(
    db: Session,
    query: str,
    tokens: list[str] | None,
    match_mode: str = "or",
    allowed_entity_types: list[str] | None = None,
    access_levels: list[str] | None = None,
    fallback_to_all_types: bool = False,
    domain_hint: str | None = None,
    limit: int | None = None,
):
    mode = (match_mode or "or").strip().lower()
    if mode not in _ALLOWED_MATCH_MODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"match_mode must be one of {sorted(_ALLOWED_MATCH_MODES)}",
        )

    # Treat literal strings "null" / "none" / "undefined" as empty so callers
    # that JSON-encode a missing query as the string "null" don't trip the
    # "no input" path with a deceptively non-empty value.
    _q_norm = (query or "").strip()
    if _q_norm.lower() in {"null", "none", "undefined"}:
        _q_norm = ""

    # Domain-hint dispatch — entity-type takes precedence over AttachmentType
    # because labels collide (e.g. AttachmentType code='promotion' for
    # promotion-attached files vs `promotion` entity-type).
    #   1. Entity-type label (`order`, `product`, `promotion`, `customer`,
    #      `brand`, `category`, ...):
    #         - When `allowed_entity_types` is empty → merge hint as sole scope.
    #         - When `allowed_entity_types` is set → hint is CONTEXT ONLY (no
    #           additive expansion). Caller's whitelist stays authoritative;
    #           hint only informs brand/category expansion overrides via
    #           `_DOMAIN_HINT_EXPANSIONS` inside the resolver.
    #   2. Otherwise try AttachmentType match (`catalogue`, `brochure`, ...).
    #      Short-circuits to attachment-scoped ILIKE search.
    if domain_hint and domain_hint.strip():
        hint_clean = domain_hint.strip()
        hint_canon = _canonical_entity_type(hint_clean)
        if hint_canon in _RESOLVER_ENTITY_TYPES:
            if not (allowed_entity_types or []):
                allowed_entity_types = [hint_clean]
            # else: keep caller's whitelist, hint flows through as context
            # via `_resolve_input` → `_run` → resolver's `domain_hint` kwarg.
        else:
            type_row = _resolve_attachment_type_for_hint(db, hint_clean)
            if type_row is not None:
                hint_tokens = [t for t in (tokens or []) if t]
                return _apply_limit(
                    _resolve_with_domain_hint(db, hint_clean, hint_tokens, _q_norm),
                    limit,
                )
            # Unknown hint — same "context-only when whitelist set" rule.
            if not (allowed_entity_types or []):
                allowed_entity_types = [hint_clean]

    # Local return-wrapper so every exit path gets `limit` applied
    # consistently. Skip the wrap for raw empty-shape payloads (they have no
    # rows; the cap is a no-op there anyway).
    def _ret(result: dict[str, Any]) -> dict[str, Any]:
        return _apply_limit(result, limit)

    if tokens:
        filtered = [t for t in tokens if t]
    else:
        filtered = []

    # Empty-in → empty-out. Callers that send {tokens:[], query:""} (or "null")
    # get an empty ResolutionResult-shaped payload instead of a 400; matches the
    # "nothing resolved, nothing unresolved" semantic the agent expects.
    if not filtered and not _q_norm:
        return {
            "tokens": [],
            "elapsed_ms": 0.0,
            "resolutions": [],
            "unresolved_tokens": [],
            "ambiguous_tokens": [],
        }

    if filtered:
        # Strip entity-type noise words ("order 202605-2651" → "202605-2651")
        # so callers can pass conversational phrasing verbatim. Alignment with
        # positional `allowed_entity_types` is preserved (in-place clean).
        filtered = [_strip_entity_stopwords(t) for t in filtered]
        prepared_tokens: list[str] = filtered
        input_for_or: list[str] | str = filtered
    else:
        # AND-mode is per-row intersection, undefined without explicit tokens.
        # Silently degrade to empty result so callers that always send
        # `match_mode='and'` regardless of token shape don't hit a 400 — they
        # get the "nothing matched" payload the agent already knows how to
        # handle. Whitespace splitting a free-text `query` for AND-mode would
        # over-tokenize compound entity names ("sorento latest promo office
        # use" → 5 tokens, intersection guaranteed empty) — not worth doing.
        if mode == "and":
            return {
                "tokens": [],
                "elapsed_ms": 0.0,
                "resolutions": [],
                "unresolved_tokens": [],
                "ambiguous_tokens": [],
            }
        prepared_tokens = []
        input_for_or = _q_norm
        # Pure-alpha entity types (e.g. attachment_type) bypass the code-token
        # regex used inside `resolve_references`. If the caller hinted such a
        # type but did NOT pass `tokens`, synthesize tokens from the query
        # whitespace split so the probes receive candidates.
        if allowed_entity_types:
            wanted = {(t or "").strip().lower() for t in allowed_entity_types if (t or "").strip()}
            if wanted & _ALPHA_TOKEN_TYPES:
                alpha_tokens = _synthesize_alpha_tokens(_q_norm)
                if alpha_tokens:
                    prepared_tokens = alpha_tokens
                    input_for_or = alpha_tokens

    def _run(
        allowed: list[str] | None,
        cross_type_expand: bool = False,
        force_mode: str | None = None,
        tokens_override: list[str] | None = None,
    ) -> dict[str, Any]:
        effective_mode = (force_mode or mode).strip().lower()
        toks = tokens_override if tokens_override is not None else prepared_tokens
        text_input = tokens_override if tokens_override is not None else input_for_or
        # `domain_hint` reaches the resolver so brand / category expansions are
        # scoped to the caller's domain (e.g. domain_hint="order" → category
        # maps to {customer, customer_order, transporter} instead of promotion).
        hint = (domain_hint or "").strip() or None
        if effective_mode == "and":
            raw = resolve_references_intersection(
                db,
                toks,
                allowed_entity_types=allowed,
                domain_hint=hint,
            ).as_dict()
        else:
            raw = resolve_references(
                db,
                text_input,
                allowed_entity_types=allowed,
                cross_type_expand=cross_type_expand,
                domain_hint=hint,
            ).as_dict()
        raw = _apply_promotion_access_levels_filter(db, raw, access_levels)
        # Promotion-domain hint: run the expander. It owns the dispatch:
        #   - promo matches found → return promotion entries only
        #     (regardless of whether caller asked for products).
        #   - no promo matches → if caller wants products, surface
        #     through-promotion products; else (and access_levels present)
        #     fallback to brand-access-scoped products as a rescue path.
        if hint and _canonical_entity_type(hint) == "promotion":
            raw = _expand_products_via_promotions(
                db,
                raw,
                list(toks) if isinstance(toks, list) else [],
                access_levels,
                wants_products=_caller_wants_products(allowed_entity_types),
            )
        return raw

    # ------------------------------------------------------------------
    # Primary pass — caller's mode + whitelist applied as-is.
    # ------------------------------------------------------------------
    result = _run(allowed_entity_types)

    if not (fallback_to_all_types and allowed_entity_types):
        return result

    # ------------------------------------------------------------------
    # Per-token fallback (only for tokens unresolved under the whitelist).
    # Tokens that DID resolve under the whitelist stay untouched — caller's
    # hint is respected and we never expand "technical drawing" into
    # `attachment` matches when they explicitly asked for `attachment_type`.
    #
    # AND-mode shape has no per-token visibility (only `intersection`). When
    # AND failed entirely, degrade to OR-mode-under-whitelist so we can reason
    # per-token. AND that succeeded is returned untouched.
    # ------------------------------------------------------------------
    fallback_match_mode_override: str | None = None
    fallback_reason: str | None = None

    if mode == "and":
        if not _result_has_zero_matches(result):
            return _ret(result)
        result = _run(allowed_entity_types, force_mode="or")
        fallback_match_mode_override = "or"
        fallback_reason = (
            "AND-mode produced zero intersection; switched to OR-mode under "
            "the whitelist so per-token fallback can apply only to unresolved tokens."
        )

    unresolved = [
        r["token"]
        for r in result.get("resolutions", []) or []
        if not (r.get("matches") or [])
    ]
    if not unresolved:
        # Tag and return — at least we've already noted the AND→OR switch.
        if fallback_match_mode_override:
            result["fallback_match_mode"] = fallback_match_mode_override
            result["fallback_reason"] = fallback_reason
        return _ret(result)

    # Cross-type fallback for tokens that didn't resolve under the whitelist.
    # The promotion-domain product expansion (with brand-access gating) already
    # handles the "no promo found → suggest brand-scoped products" path, so
    # this branch fires for non-promotion hints or callers that didn't ask for
    # promotion-domain at all.
    fb_raw = resolve_references(
        db,
        unresolved,
        allowed_entity_types=None,
        cross_type_expand=True,
    ).as_dict()
    fb = _apply_promotion_access_levels_filter(db, fb_raw, access_levels)
    # Per-token fallback bypasses `_run`, so the promotion-domain product
    # expansion / brand-access rescue must be applied here too.
    if domain_hint and _canonical_entity_type(domain_hint.strip()) == "promotion":
        fb = _expand_products_via_promotions(
            db,
            fb,
            list(unresolved),
            access_levels,
            wants_products=_caller_wants_products(allowed_entity_types),
        )
    fb_by_token: dict[str, dict[str, Any]] = {
        r["token"]: r for r in fb.get("resolutions", []) or []
    }

    merged: list[dict[str, Any]] = []
    found_any_fallback = False
    for r in result.get("resolutions", []) or []:
        tok = r.get("token")
        has_matches = bool(r.get("matches") or [])
        fb_entry = fb_by_token.get(tok) if tok else None
        if not has_matches and fb_entry and (fb_entry.get("matches") or []):
            merged.append(fb_entry)
            found_any_fallback = True
        else:
            merged.append(r)
    result["resolutions"] = merged
    result["unresolved_tokens"] = [
        m["token"] for m in merged if not (m.get("matches") or [])
    ]

    if found_any_fallback:
        result["fallback_applied"] = True
        result["fallback_requested_types"] = list(allowed_entity_types)
        result["fallback_types_found"] = _collect_match_types(result)
        result["fallback_per_token"] = True
        if fallback_match_mode_override:
            result["fallback_match_mode"] = fallback_match_mode_override
            result["fallback_reason"] = fallback_reason
    elif fallback_match_mode_override:
        # AND→OR switch happened but nothing new came from the per-token fallback.
        result["fallback_match_mode"] = fallback_match_mode_override
        result["fallback_reason"] = fallback_reason

    return _ret(result)


@router.get("/resolve")
def resolve_reference(
    query: str = Query(..., description="Free-text query or a single code to resolve."),
    tokens: list[str] | None = Query(
        None,
        description=(
            "Optional pre-extracted tokens. If provided, the resolver skips regex extraction and "
            "looks up each token verbatim."
        ),
    ),
    match_mode: str = Query(
        "or",
        description=(
            "'or' (default) returns per-token candidates. 'and' returns cross-token intersection "
            "— rows matching every token. AND-mode requires `tokens` (cannot use `query`)."
        ),
    ),
    allowed_entity_types: list[str] | None = Query(
        None,
        description=(
            "Entity-type whitelist. Always a global set filter — every token is "
            "resolved against EVERY supplied type (cross product). Positional 1:1 "
            "pairing is not auto-triggered on equal-length lists; issue one resolve "
            "call per (token, type) pair if you need it. Canonical types include "
            "`attachment_type` (resolves doc-class labels like 'catalogue', "
            "'brochure', 'spec sheet' to AttachmentType UUIDs)."
        ),
    ),
    access_levels: list[str] | None = Query(
        None,
        description=(
            "Post-filter for promotion AND attachment matches. Array of "
            "contact-access-type NAMES (translated to codes via "
            "contact_access_types.name and intersected with the entity's "
            "`access_levels` JSONB column). Matches survive only on intersection; "
            "non-promotion / non-attachment matches untouched. Empty / omitted → no-op."
        ),
    ),
    fallback_to_all_types: bool = Query(
        False,
        description=(
            "When `allowed_entity_types` is set and the first pass returns zero "
            "matches, retry without the whitelist. Response is tagged with "
            "`fallback_applied: true` + `fallback_types_found`."
        ),
    ),
    domain_hint: str | None = Query(
        None,
        description=(
            "Scope resolution to attachments of one AttachmentType (e.g. "
            "'catalogue'). Short-circuits the normal probes and returns "
            "`entity_type='attachment'` rows whose UUIDs feed domain-specific "
            "tools like `crm_resource_attachments_catalogue`. Alias: `domain`."
        ),
    ),
    domain: str | None = Query(None, description="Alias for `domain_hint`."),
    limit: int | None = Query(
        None,
        ge=1,
        le=200,
        description=(
            "Cap returned matches. Applied per-token (each resolution's "
            "`matches` truncated to `limit`) AND to `intersection` in AND-mode. "
            "Omit / null = no cap."
        ),
    ),
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """Resolve free-text entity references (product codes, order numbers, shipment numbers, ...)
    to their canonical entity types.

    OR mode (default): per-token, returns canonical UUIDs + display payload + ambiguity signals.
    AND mode: cross-token intersection across each entity's concatenated searchable columns.
    """
    return _resolve_input(
        db,
        query,
        tokens,
        match_mode=match_mode,
        allowed_entity_types=allowed_entity_types,
        access_levels=access_levels,
        fallback_to_all_types=fallback_to_all_types,
        domain_hint=domain_hint or domain,
        limit=limit,
    )


@router.post("/resolve")
def resolve_reference_post(
    payload: ResolveReferenceRequest,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """POST variant for external callers that send JSON body (e.g. n8n HTTP node)."""
    return _resolve_input(
        db,
        payload.query,
        payload.tokens,
        match_mode=payload.match_mode,
        allowed_entity_types=payload.allowed_entity_types,
        access_levels=payload.access_levels,
        fallback_to_all_types=payload.fallback_to_all_types,
        domain_hint=payload.domain_hint,
        limit=payload.limit,
    )
