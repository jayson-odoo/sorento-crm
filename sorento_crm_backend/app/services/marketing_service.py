"""Marketing service for business logic."""
# ORM models declare Column[T] on the class; at runtime instance attributes are Python values.
# Pyright reports false positives here until models use SQLAlchemy 2.0 Mapped[] typing.
# pyright: reportAttributeAccessIssue=false
# pyright: reportGeneralTypeIssues=false
# pyright: reportArgumentType=false
# pyright: reportCallIssue=false
# pyright: reportReturnType=false
# pyright: reportOptionalMemberAccess=false
import math
import re
import uuid
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from sqlalchemy import and_, cast, func, or_, exists, select, text, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.exc import IntegrityError
from typing import Any, Optional
from decimal import Decimal

from app.models.marketing import Promotion, PromotionGroup, PromotionProduct, PromotionAttachment, CampaignType, MarketingCampaign
from app.models.product import Product, ProductCategory, Brand
from app.models.resources import Attachment, AttachmentType
from app.schemas.marketing import (
    PromotionCreate,
    PromotionUpdate,
    PromotionGroupCreate,
    PromotionGroupUpdate,
    PromotionProductCreate,
    PromotionProductUpdate,
    PromotionAttachmentCreate,
    PromotionAttachmentUpdate,
    CampaignTypeCreate,
    CampaignTypeUpdate,
    MarketingCampaignCreate,
    MarketingCampaignUpdate,
)
from app.services.error_handler import handle_not_found, handle_conflict, handle_internal_error, handle_validation_error
from app.services.contact_access_type_service import ContactAccessTypeService
from app.services.embedding_events import publish_embedding_event
from app.services.identifier_resolver import resolve_identifier

_MY_TZ = ZoneInfo("Asia/Kuala_Lumpur")


def _promotion_stored_boundary_date(dt: datetime | date) -> date:
    """Calendar day for a promotion boundary (DATE column, or legacy datetime)."""
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return dt
    if isinstance(dt, datetime):
        aware = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
        return aware.astimezone(_MY_TZ).date()
    raise TypeError(f"Expected date or datetime, got {type(dt)}")


def _resolve_promotion_id_for_filter(db: Session, raw: Optional[str]) -> Optional[str]:
    """Map API promotion id/path segments to ``Promotion.id`` (UUID string).

    Accepts a UUID string or ``Promotion.promo_code`` (case-insensitive exact match).
    Returns ``None`` if *raw* is blank or no row matches the code.
    Raises validation error if more than one promotion shares the same ``promo_code``.
    """
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    try:
        return str(uuid.UUID(s))
    except ValueError:
        pass
    rows = (
        db.query(Promotion.id)
        .filter(func.lower(Promotion.promo_code) == s.lower())
        .limit(2)
        .all()
    )
    if not rows:
        return None
    if len(rows) > 1:
        raise handle_validation_error(
            "Multiple promotions share this promo_code; pass promotion id (UUID)."
        )
    return str(rows[0].id)


def _product_display_label(db: Session, product_id: str) -> str:
    """Human-readable product label (code and name) for error messages."""
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        return product_id
    code = (p.product_code or "").strip()
    name = (p.product_name or "").strip()
    if code and name:
        return f"{code} — {name}"
    return code or name or product_id


def raise_promotion_product_unique_violation(db: Session, exc: Exception) -> None:
    """
    Turn promotion_products unique constraint failures into 409 with product details.
    Call after session.rollback() when handling IntegrityError from commit/flush.
    """
    if not isinstance(exc, IntegrityError):
        raise exc
    orig = str(getattr(exc, "orig", exc) or exc)
    if (
        "uq_promotion" not in orig.lower()
        and "promotion_products" not in orig.lower()
        and "group_product" not in orig.lower()
    ):
        raise handle_internal_error(
            "Could not save promotion product due to a database constraint."
        )
    m = re.search(
        r"Key \(promotion_group_id, product_id\)=\([^,]+,\s*([^)]+)\)", orig
    ) or re.search(r"Key \(promotion_id, product_id\)=\([^,]+,\s*([^)]+)\)", orig)
    if not m:
        raise handle_conflict(
            "This product is already linked to this promotion group, or the request contains duplicate products."
        )
    product_id = m.group(1).strip()
    label = _product_display_label(db, product_id)
    raise handle_conflict(
        f"Product already in this promotion group: {label}. Remove duplicate rows or use one line per product per group."
    )


# promotion_products.discount_percent is NUMERIC(5,2) → |value| must be < 10**3 (max ±999.99).
_MAX_DISCOUNT_PERCENT = 999.99


def _load_attachments_by_promotion_ids(
    db: Session, promotion_ids: list[str]
) -> dict[str, list[PromotionAttachment]]:
    """Eager-load promotion attachments for a batch of promotions, grouped by promotion_id.

    Shared between PromotionService (list/get) and PromotionProductService
    (line listings) so any tool that surfaces a promotion can carry the
    promotion document inline without a follow-up call.
    """
    from sqlalchemy.orm import joinedload as _joinedload

    result: dict[str, list[PromotionAttachment]] = {pid: [] for pid in promotion_ids}
    if not promotion_ids:
        return result
    rows = (
        db.query(PromotionAttachment)
        .options(
            _joinedload(PromotionAttachment.attachment).joinedload(Attachment.attachment_type)
        )
        .filter(PromotionAttachment.promotion_id.in_(promotion_ids))
        .order_by(
            PromotionAttachment.sort_order.asc().nulls_last(),
            PromotionAttachment.created_at.asc(),
        )
        .all()
    )
    for row in rows:
        result.setdefault(row.promotion_id, []).append(row)
    return result


def _tiers_from_create_data(data: PromotionGroupCreate) -> Optional[list[dict]]:
    """Build normalized foc_tiers JSON from create payload."""
    if not data.foc_tiers:
        return None
    out: list[dict] = []
    for t in data.foc_tiers:
        pq = int(t.purchase_quantity)
        fq = int(t.foc_quantity)
        if pq < 1:
            raise handle_conflict("FOC purchase quantity must be at least 1.")
        if fq < 0:
            raise handle_conflict("FOC free quantity cannot be negative.")
        out.append({"purchase_quantity": pq, "foc_quantity": fq})
    return out


def dealer_cost_and_margin_from_list(
    list_price: Optional[float],
    dealer_discount_percent: Optional[float],
) -> tuple[Optional[float], Optional[float]]:
    """
    dealer_discount_percent e.g. 0.37 => dealer pays (1-0.37) of list (dealer cost).
    Returns (dealer_cost, list_to_dealer_margin_amount).
    """
    if list_price is None or dealer_discount_percent is None:
        return None, None
    lp = float(list_price)
    dd = float(dealer_discount_percent)
    dealer_cost = lp * (1.0 - dd)
    margin = lp - dealer_cost
    return round(dealer_cost, 2), round(margin, 2)


def clamp_discount_percent_for_db(value: Optional[float]) -> Optional[float]:
    """Clamp discount % to DB range so bulk inserts do not raise NumericValueOutOfRange."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    v = max(-_MAX_DISCOUNT_PERCENT, min(_MAX_DISCOUNT_PERCENT, v))
    return round(v, 2)


class PromotionService:
    """Service for promotion operations."""
    
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _canonical_access_levels(access_levels: Optional[list[str]]) -> tuple[str, ...]:
        """Canonicalize access levels for uniqueness checks (order-insensitive, deduplicated)."""
        if not access_levels:
            return tuple()
        return tuple(sorted({(a or "").strip() for a in access_levels if (a or "").strip()}))

    def _load_attachments_for_promotion_ids(
        self, promotion_ids: list[str]
    ) -> dict[str, list[PromotionAttachment]]:
        return _load_attachments_by_promotion_ids(self.db, promotion_ids)

    @staticmethod
    def _filter_attachments_by_codes(
        attachments: list[PromotionAttachment],
        codes: Optional[list[str]],
    ) -> list[PromotionAttachment]:
        """Drop inline attachments whose underlying file's access_levels does not overlap ``codes``.

        ``codes is None`` means no per-attachment filter (FE/admin path). ``codes=[]``
        hides every attachment (contact has no assigned access types).
        """
        if codes is None:
            return attachments
        if not codes:
            return []
        code_set = set(codes)
        out: list[PromotionAttachment] = []
        for pa in attachments:
            att = getattr(pa, "attachment", None)
            levels = getattr(att, "access_levels", None) if att is not None else None
            if isinstance(levels, list) and code_set.intersection(levels):
                out.append(pa)
        return out

    def _ensure_promo_code_access_levels_unique(
        self,
        promo_code: str,
        access_levels: list[str],
        exclude_id: Optional[str] = None,
    ) -> None:
        """
        Enforce uniqueness on (promo_code + access level set).
        Same promo_code is allowed only when access level set is different.
        """
        target = self._canonical_access_levels(access_levels)
        q = self.db.query(Promotion).filter(Promotion.promo_code == promo_code)
        if exclude_id:
            q = q.filter(Promotion.id != exclude_id)
        for existing in q.all():
            if self._canonical_access_levels(existing.access_levels) == target:
                raise handle_conflict(
                    "Promo code already exists for the same access types. "
                    "Use a different promo code or change access types."
                )
    
    def list_promotions(
        self,
        page: int = 1,
        limit: int = 50,
        user_type: Optional[str] = None,
        contact_access_codes: Optional[list[str]] = None,
        query: Optional[str] = None,
        status: Optional[str] = None,
        promo_type: Optional[str] = None,
        active: Optional[bool] = None,
        period_from: Optional[date] = None,
        period_to: Optional[date] = None,
        sort_field: Optional[str] = None,
        sort_dir: Optional[str] = "desc",
        advanced_filter_clause: Optional[Any] = None,
    ):
        """List promotions with active-first fallback semantics.

        active=None (default): return active rows; if a narrowing filter is
        present and zero active match, fall back to inactive rows.
        active=True: same as default — find active first, fall back to inactive
        when narrowing filter is present and active set is empty.
        active=False: return only inactive rows (no fallback).

        Active definition: Promotion.is_active is True AND today falls within
        [start_date, end_date]. Anything outside that window — even if the
        boolean flag is True — is treated as inactive.

        period_from/period_to: optional date bounds. Filters to promotions
        whose [start_date, end_date] overlaps with the requested window.
        """
        # Back-compat: legacy `status` query param translates to `active`.
        if active is None and status and status != "all":
            if status == "active":
                active = True
            elif status == "inactive":
                active = False

        query_norm = (query or "").strip() or None
        promo_type_norm = (promo_type or "").strip() or None
        narrowing_filter_present = bool(
            query_norm
            or promo_type_norm
            or user_type
            or contact_access_codes
            or period_from
            or period_to
        )

        today = datetime.utcnow().date()
        is_within_window = and_(
            Promotion.start_date <= today,
            Promotion.end_date >= today,
        )
        active_clause = and_(Promotion.is_active.is_(True), is_within_window)

        def _apply_common_filters(q):
            if query_norm:
                search_term = f"%{query_norm}%"
                has_product_match = exists().where(
                    PromotionProduct.promotion_id == Promotion.id
                ).where(
                    PromotionProduct.product_id == Product.id
                ).where(
                    Product.product_code.ilike(search_term)
                )
                has_attachment_match = exists().where(
                    PromotionAttachment.promotion_id == Promotion.id
                ).where(
                    PromotionAttachment.attachment_id == Attachment.id
                ).where(
                    or_(
                        Attachment.original_filename.ilike(search_term),
                        Attachment.stored_filename.ilike(search_term),
                    )
                )
                q = q.filter(
                    or_(
                        Promotion.promo_code.ilike(search_term),
                        Promotion.name.ilike(search_term),
                        has_product_match,
                        has_attachment_match,
                    )
                )
            if promo_type_norm:
                q = q.filter(Promotion.promo_type == promo_type_norm)
            if user_type:
                q = q.filter(Promotion.access_levels.contains([user_type]))
            if contact_access_codes is not None:
                # Empty access_levels (=[]) is invisible to any contact (no overlap possible).
                # Empty contact_access_codes (contact has no assigned types) returns nothing.
                if not contact_access_codes:
                    q = q.filter(text("false"))
                else:
                    q = q.filter(
                        Promotion.access_levels.op("?|")(
                            cast(contact_access_codes, ARRAY(String))
                        )
                    )
            if period_from is not None:
                q = q.filter(Promotion.end_date >= period_from)
            if period_to is not None:
                q = q.filter(Promotion.start_date <= period_to)
            if advanced_filter_clause is not None:
                q = q.filter(advanced_filter_clause)
            return q

        sort_key = (sort_field or "created_at").strip() or "created_at"
        dir_norm = (sort_dir or "desc").lower()
        if dir_norm not in ("asc", "desc"):
            dir_norm = "desc"
        sort_map = {
            "promo_code": Promotion.promo_code,
            "name": Promotion.name,
            "promo_type": Promotion.promo_type,
            "start_date": Promotion.start_date,
            "end_date": Promotion.end_date,
            "is_active": Promotion.is_active,
            "created_at": Promotion.created_at,
            "access_levels": Promotion.access_levels,
        }

        def _ordered_query(active_mode: Optional[bool]):
            q = self.db.query(Promotion)
            q = _apply_common_filters(q)
            if active_mode is True:
                q = q.filter(active_clause)
            elif active_mode is False:
                q = q.filter(~active_clause)
            if sort_key == "products_count":
                pc_subq = (
                    select(
                        PromotionProduct.promotion_id.label("pid"),
                        func.count(PromotionProduct.id).label("pcnt"),
                    )
                    .group_by(PromotionProduct.promotion_id)
                    .subquery()
                )
                q = q.outerjoin(pc_subq, Promotion.id == pc_subq.c.pid)
                order_col = func.coalesce(pc_subq.c.pcnt, 0)
            else:
                order_col = sort_map.get(sort_key, Promotion.created_at)
            return q.order_by(order_col.asc() if dir_norm == "asc" else order_col.desc())

        primary_active_mode: Optional[bool] = True if active is None else active
        q = _ordered_query(primary_active_mode)
        total = q.count()
        fallback_used = False

        if total == 0 and narrowing_filter_present and active is not False:
            q = _ordered_query(False)
            total = q.count()
            fallback_used = total > 0

        offset = (page - 1) * limit
        promotions = q.offset(offset).limit(limit).all()

        attachments_by_promotion = self._load_attachments_for_promotion_ids(
            [p.id for p in promotions]
        )
        for promotion in promotions:
            products_count = self.db.query(func.count(PromotionProduct.id)).filter(
                PromotionProduct.promotion_id == promotion.id
            ).scalar() or 0
            promotion.products_count = products_count
            promotion.attachments = self._filter_attachments_by_codes(
                attachments_by_promotion.get(promotion.id, []),
                contact_access_codes,
            )

        return {
            "data": promotions,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0,
            "fallback_used": fallback_used,
        }
    
    def get_promotion(
        self,
        promotion_id: str,
        *,
        include_products: bool = True,
        contact_access_codes: Optional[list[str]] = None,
    ):
        """Get a promotion by UUID or promo_code.

        When *include_products* is False, loads groups without promotion product lines (no nested Product rows).
        When *contact_access_codes* is supplied, inline attachments are filtered to those whose
        ``access_levels`` overlaps the contact's codes.
        """
        from sqlalchemy.orm import joinedload, noload

        resolved_pid = _resolve_promotion_id_for_filter(self.db, promotion_id)
        if not resolved_pid:
            raise handle_not_found("Promotion", promotion_id)

        if not include_products:
            promotion = (
                self.db.query(Promotion)
                .options(
                    joinedload(Promotion.promotion_groups).options(
                        noload(PromotionGroup.promotion_products)
                    ),
                )
                .filter(Promotion.id == resolved_pid)
                .first()
            )
            if not promotion:
                raise handle_not_found("Promotion", promotion_id)

            groups = sorted(promotion.promotion_groups or [], key=lambda g: (g.sort_order, g.created_at))
            promotion.products_count = (
                self.db.query(func.count(PromotionProduct.id))
                .filter(PromotionProduct.promotion_id == resolved_pid)
                .scalar()
                or 0
            )
            promotion.products = None
            promotion.promotion_groups = groups
            promotion.attachments = self._filter_attachments_by_codes(
                self._load_attachments_for_promotion_ids([resolved_pid]).get(resolved_pid, []),
                contact_access_codes,
            )
            return promotion

        promotion = (
            self.db.query(Promotion)
            .options(
                joinedload(Promotion.promotion_groups).joinedload(PromotionGroup.promotion_products).joinedload(
                    PromotionProduct.product
                ),
            )
            .filter(Promotion.id == resolved_pid)
            .first()
        )
        if not promotion:
            raise handle_not_found("Promotion", promotion_id)

        groups = sorted(promotion.promotion_groups or [], key=lambda g: (g.sort_order, g.created_at))
        flat: list = []
        for g in groups:
            for pp in sorted(g.promotion_products or [], key=lambda x: x.created_at):
                flat.append(pp)

        promotion.products_count = len(flat)
        promotion.products = flat
        # Expose sorted groups for API (nested products on each group)
        promotion.promotion_groups = groups
        promotion.attachments = self._filter_attachments_by_codes(
            self._load_attachments_for_promotion_ids([resolved_pid]).get(resolved_pid, []),
            contact_access_codes,
        )

        return promotion
    
    def create_promotion(self, promotion_data: PromotionCreate, created_by: str):
        """Create a new promotion. Validates access_levels against catalog; defaults to all active types if missing."""
        access_svc = ContactAccessTypeService(self.db)
        promotion_dict = promotion_data.model_dump()
        promotion_dict["promo_code"] = (promotion_dict.get("promo_code") or "").strip()
        if not promotion_dict["promo_code"]:
            raise handle_conflict("Promo code cannot be empty.")
        promotion_dict["created_by"] = created_by
        if promotion_dict.get("access_levels"):
            promotion_dict["access_levels"] = access_svc.validate_access_levels(
                promotion_dict["access_levels"], field_name="access_levels"
            )
        else:
            promotion_dict["access_levels"] = access_svc.get_default_access_levels()
        self._ensure_promo_code_access_levels_unique(
            promo_code=promotion_dict["promo_code"],
            access_levels=promotion_dict["access_levels"],
        )
        promotion = Promotion(**promotion_dict)
        self.db.add(promotion)
        self.db.commit()
        self.db.refresh(promotion)
        publish_embedding_event(
            self.db,
            source_type="promotion",
            source_id=promotion.id,
            source_key=promotion.promo_code,
            source_updated_at=promotion.updated_at or promotion.created_at,
            event_type="promotion.created",
            changed_fields=["promo_code", "name", "description", "promo_type", "start_date", "end_date", "access_levels"],
            triggered_by=created_by,
        )
        return promotion
    
    def update_promotion(self, promotion_id: str, promotion_data: PromotionUpdate):
        """Update a promotion. Enforces uniqueness on promo_code + access level set."""
        promotion = self.get_promotion(promotion_id)

        update_data = promotion_data.model_dump(exclude_unset=True)
        access_svc = ContactAccessTypeService(self.db)
        if "access_levels" in update_data and update_data["access_levels"]:
            update_data["access_levels"] = access_svc.validate_access_levels(
                update_data["access_levels"], field_name="access_levels"
            )

        if "promo_code" in update_data:
            new_code = (update_data["promo_code"] or "").strip()
            if not new_code:
                raise handle_conflict("Promo code cannot be empty.")
            update_data["promo_code"] = new_code

        final_code = update_data.get("promo_code", promotion.promo_code)
        final_access_levels = update_data.get("access_levels", promotion.access_levels)
        self._ensure_promo_code_access_levels_unique(
            promo_code=final_code,
            access_levels=final_access_levels or [],
            exclude_id=promotion_id,
        )

        for key, value in update_data.items():
            setattr(promotion, key, value)

        self.db.commit()
        self.db.refresh(promotion)
        publish_embedding_event(
            self.db,
            source_type="promotion",
            source_id=promotion.id,
            source_key=promotion.promo_code,
            source_updated_at=promotion.updated_at or promotion.created_at,
            event_type="promotion.updated" if promotion.is_active else "promotion.deactivated",
            changed_fields=list(update_data.keys()),
        )
        return promotion

    def delete_promotion(self, promotion_id: str):
        """Delete a promotion (cascade deletes promotion_products and promotion_attachments)."""
        promotion = self.get_promotion(promotion_id)
        self.db.delete(promotion)
        self.db.commit()

    def bulk_delete_promotions(self, promotion_ids: list[str]):
        """Delete multiple promotions. Returns count deleted."""
        if not promotion_ids:
            return {"message": "No promotions to delete", "deleted_count": 0}
        deleted = self.db.query(Promotion).filter(Promotion.id.in_(promotion_ids)).delete(synchronize_session=False)
        self.db.commit()
        return {"message": f"{deleted} promotion(s) deleted", "deleted_count": deleted}

    def bulk_update_access_levels(self, promotion_ids: list[str], access_levels: list[str]):
        """Set access_levels on multiple promotions. Returns count updated. Validates against contact access type catalog."""
        if not promotion_ids:
            return {"message": "No promotions selected", "updated_count": 0}
        access_svc = ContactAccessTypeService(self.db)
        normalized = access_svc.validate_access_levels(access_levels, field_name="access_levels")
        target_canonical = self._canonical_access_levels(normalized)

        selected_promotions = self.db.query(Promotion).filter(Promotion.id.in_(promotion_ids)).all()
        selected_ids = {p.id for p in selected_promotions}
        selected_codes = {p.promo_code for p in selected_promotions}

        if selected_codes:
            code_conflict_scope = self.db.query(Promotion).filter(Promotion.promo_code.in_(selected_codes)).all()
            by_code: dict[str, list[tuple[str, tuple[str, ...]]]] = {}
            for p in code_conflict_scope:
                canonical = target_canonical if p.id in selected_ids else self._canonical_access_levels(p.access_levels)
                by_code.setdefault(p.promo_code, []).append((p.id, canonical))

            for code, rows in by_code.items():
                seen: dict[tuple[str, ...], str] = {}
                for row_id, canonical in rows:
                    existing_id = seen.get(canonical)
                    if existing_id and existing_id != row_id:
                        raise handle_conflict(
                            f"Bulk update would create duplicate promo code/access types for code '{code}'. "
                            "Adjust selection or access types."
                        )
                    seen[canonical] = row_id

        updated = (
            self.db.query(Promotion)
            .filter(Promotion.id.in_(promotion_ids))
            .update({"access_levels": normalized}, synchronize_session=False)
        )
        self.db.commit()
        return {"message": f"Access levels set for {updated} promotion(s).", "updated_count": updated}

    def sync_promotion_active_by_calendar_window(self) -> dict[str, Any]:
        """
        Align ``is_active`` with Malaysia calendar today vs inclusive [start_date, end_date]:
        activate when in range, deactivate when before start or after end.
        """
        now = datetime.now(timezone.utc)
        today_my = now.astimezone(_MY_TZ).date()
        rows = self.db.query(Promotion).all()
        activated = 0
        deactivated = 0
        for p in rows:
            start_my = _promotion_stored_boundary_date(p.start_date)
            end_my = _promotion_stored_boundary_date(p.end_date)
            in_window = start_my <= today_my <= end_my
            if in_window:
                if not p.is_active:
                    p.is_active = True
                    activated += 1
            else:
                if p.is_active:
                    p.is_active = False
                    deactivated += 1
        if activated or deactivated:
            self.db.commit()
        return {
            "scanned": len(rows),
            "activated": activated,
            "deactivated": deactivated,
            "today_malaysia": today_my.isoformat(),
        }

    def create_promotion_group(self, promotion_id: str, data: PromotionGroupCreate) -> PromotionGroup:
        """Add a bundle / FOC group to a promotion."""
        if not self.db.query(Promotion.id).filter(Promotion.id == promotion_id).first():
            raise handle_not_found("Promotion", promotion_id)
        name = (data.group_name or "").strip()
        if not name:
            raise handle_conflict("Group name cannot be empty.")
        max_so = (
            self.db.query(func.coalesce(func.max(PromotionGroup.sort_order), -1))
            .filter(PromotionGroup.promotion_id == promotion_id)
            .scalar()
        )
        sort_order = data.sort_order if data.sort_order is not None else (int(max_so) + 1)
        tiers = _tiers_from_create_data(data)
        g = PromotionGroup(
            promotion_id=promotion_id,
            group_name=name,
            sort_order=sort_order,
            foc_tiers=tiers,
        )
        self.db.add(g)
        self.db.commit()
        self.db.refresh(g)
        return g

    def update_promotion_group(self, promotion_id: str, group_id: str, data: PromotionGroupUpdate) -> PromotionGroup:
        """Update group name, sort order, or FOC fields."""
        g = (
            self.db.query(PromotionGroup)
            .filter(PromotionGroup.id == group_id, PromotionGroup.promotion_id == promotion_id)
            .first()
        )
        if not g:
            raise handle_not_found("Promotion group", group_id)
        update_data = data.model_dump(exclude_unset=True)
        if "group_name" in update_data and update_data["group_name"] is not None:
            nm = str(update_data["group_name"]).strip()
            if not nm:
                raise handle_conflict("Group name cannot be empty.")
            update_data["group_name"] = nm

        if "foc_tiers" in update_data:
            raw = update_data.pop("foc_tiers")
            if raw is None or raw == []:
                g.foc_tiers = None
            else:
                tiers: list[dict] = []
                for t in raw:
                    if isinstance(t, dict):
                        pq = int(t["purchase_quantity"])
                        fq = int(t["foc_quantity"])
                    else:
                        pq = int(t.purchase_quantity)
                        fq = int(t.foc_quantity)
                    if pq < 1:
                        raise handle_conflict("FOC purchase quantity must be at least 1.")
                    if fq < 0:
                        raise handle_conflict("FOC free quantity cannot be negative.")
                    tiers.append({"purchase_quantity": pq, "foc_quantity": fq})
                g.foc_tiers = tiers

        for key, value in update_data.items():
            setattr(g, key, value)
        self.db.commit()
        self.db.refresh(g)
        return g

    def delete_promotion_group(self, promotion_id: str, group_id: str) -> dict:
        """
        Delete a promotion group (cascade deletes promotion product lines in that group).
        Cannot remove the last remaining group.
        """
        g = (
            self.db.query(PromotionGroup)
            .filter(PromotionGroup.id == group_id, PromotionGroup.promotion_id == promotion_id)
            .first()
        )
        if not g:
            raise handle_not_found("Promotion group", group_id)
        total = (
            self.db.query(func.count(PromotionGroup.id))
            .filter(PromotionGroup.promotion_id == promotion_id)
            .scalar()
        )
        if (total or 0) <= 1:
            raise handle_conflict(
                "Cannot delete the only promotion group. Create another group first, or delete the promotion."
            )
        line_count = (
            self.db.query(func.count(PromotionProduct.id))
            .filter(PromotionProduct.promotion_group_id == group_id)
            .scalar()
            or 0
        )
        self.db.delete(g)
        self.db.commit()
        return {
            "message": "Promotion group deleted",
            "deleted_product_lines": int(line_count),
        }


class PromotionProductService:
    """Service for promotion product operations."""
    
    def __init__(self, db: Session):
        self.db = db

    def get_or_create_default_promotion_group(self, promotion_id: str) -> PromotionGroup:
        """Legacy / simple promotions: one unnamed default group for flat product lists."""
        g = (
            self.db.query(PromotionGroup)
            .filter(
                PromotionGroup.promotion_id == promotion_id,
                PromotionGroup.group_name == "Default",
            )
            .first()
        )
        if g:
            return g
        g = PromotionGroup(
            promotion_id=promotion_id,
            group_name="Default",
            sort_order=0,
            foc_tiers=None,
        )
        self.db.add(g)
        self.db.flush()
        return g

    def _compute_discount_values(self, list_price: float, promo_price: float) -> tuple[float, float]:
        """Compute discount amount/percent; clamp percent to NUMERIC(5,2) range."""
        discount_amount = list_price - promo_price
        discount_percent = (discount_amount / list_price * 100) if list_price > 0 else 0
        discount_percent = clamp_discount_percent_for_db(discount_percent)
        if discount_percent is None:
            discount_percent = 0.0
        return discount_amount, discount_percent
    
    def list_promotion_products(
        self,
        promotion_id: Optional[str] = None,
        promotion_ids: Optional[list[str]] = None,
        product_id: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
        sort_field: str = "created_at",
        sort_dir: str = "asc",
        query: Optional[str] = None,
        category_id: Optional[str] = None,
        brand_id: Optional[str] = None,
        item_type: Optional[str] = None,
        status: Optional[str] = None,
        price_min: Optional[float] = None,
        price_max: Optional[float] = None,
        length_min: Optional[float] = None,
        length_max: Optional[float] = None,
        width_min: Optional[float] = None,
        width_max: Optional[float] = None,
        height_min: Optional[float] = None,
        height_max: Optional[float] = None,
        any_dimension_min: Optional[float] = None,
        any_dimension_max: Optional[float] = None,
    ):
        """List products for a promotion, several promotions, or all promotion products.

        Text `query` is tokenized on whitespace; every token must match (case-insensitive)
        somewhere across Product.product_code, product_name, description, item_type, or
        Promotion.promo_code. Structured filters (category_id, brand_id, dimensions, price,
        item_type, status) are AND-combined with the text query.
        """
        from sqlalchemy.orm import joinedload
        from sqlalchemy import or_, and_
        import logging
        logger = logging.getLogger(__name__)

        q = self.db.query(PromotionProduct).options(
            joinedload(PromotionProduct.product).joinedload(Product.category),
            joinedload(PromotionProduct.product).joinedload(Product.brand),
            joinedload(PromotionProduct.promotion),
        )

        if promotion_ids:
            resolved_bulk: list[str] = []
            for raw in promotion_ids:
                resolved = _resolve_promotion_id_for_filter(self.db, raw)
                if resolved:
                    resolved_bulk.append(resolved)
            if not resolved_bulk:
                return {
                    "data": [],
                    "pagination": {"total": 0, "page": page, "limit": limit},
                    "empty": True,
                }
            q = q.filter(PromotionProduct.promotion_id.in_(resolved_bulk))
            logger.debug("Filtering by promotion_ids count=%s", len(resolved_bulk))
        elif promotion_id:
            resolved_pid = _resolve_promotion_id_for_filter(self.db, promotion_id)
            if not resolved_pid:
                return {
                    "data": [],
                    "pagination": {"total": 0, "page": page, "limit": limit},
                    "empty": True,
                }
            logger.debug(f"Filtering by resolved promotion_id: {resolved_pid}")
            q = q.filter(PromotionProduct.promotion_id == resolved_pid)

        if product_id:
            pid = str(product_id).strip()
            if pid:
                q = q.filter(PromotionProduct.product_id == pid)

        # Resolve category / brand (UUID or code/name) before joining.
        category_uuids = resolve_identifier(
            self.db,
            category_id,
            ProductCategory,
            code_fields=("category_code", "category_name"),
        )
        if category_uuids is not None and not category_uuids:
            return {
                "data": [],
                "pagination": {"total": 0, "page": page, "limit": limit},
                "empty": True,
            }
        brand_uuids = resolve_identifier(
            self.db,
            brand_id,
            Brand,
            code_fields=("brand_code", "brand_name"),
        )
        if brand_uuids is not None and not brand_uuids:
            return {
                "data": [],
                "pagination": {"total": 0, "page": page, "limit": limit},
                "empty": True,
            }

        needs_product_join = (
            bool(query)
            or category_uuids is not None
            or brand_uuids is not None
            or item_type is not None
            or status is not None
            or price_min is not None
            or price_max is not None
            or length_min is not None
            or length_max is not None
            or width_min is not None
            or width_max is not None
            or height_min is not None
            or height_max is not None
            or any_dimension_min is not None
            or any_dimension_max is not None
        )
        needs_promotion_join = bool(query)

        if needs_product_join:
            q = q.join(Product, PromotionProduct.product_id == Product.id)
        if needs_promotion_join:
            q = q.join(Promotion, PromotionProduct.promotion_id == Promotion.id)

        if category_uuids is not None:
            q = q.filter(Product.category_id.in_(category_uuids))
        if brand_uuids is not None:
            q = q.filter(Product.brand_id.in_(brand_uuids))
        if item_type:
            q = q.filter(Product.item_type == item_type)
        if status and status != "all":
            q = q.filter(Product.is_active == (status == "active"))
        if price_min is not None:
            q = q.filter(Product.list_price >= Decimal(str(price_min)))
        if price_max is not None:
            q = q.filter(Product.list_price <= Decimal(str(price_max)))
        if length_min is not None:
            q = q.filter(Product.dimensions_length >= Decimal(str(length_min)))
        if length_max is not None:
            q = q.filter(Product.dimensions_length <= Decimal(str(length_max)))
        if width_min is not None:
            q = q.filter(Product.dimensions_width >= Decimal(str(width_min)))
        if width_max is not None:
            q = q.filter(Product.dimensions_width <= Decimal(str(width_max)))
        if height_min is not None:
            q = q.filter(Product.dimensions_height >= Decimal(str(height_min)))
        if height_max is not None:
            q = q.filter(Product.dimensions_height <= Decimal(str(height_max)))
        if any_dimension_min is not None:
            v = Decimal(str(any_dimension_min))
            q = q.filter(or_(
                Product.dimensions_length >= v,
                Product.dimensions_width >= v,
                Product.dimensions_height >= v,
            ))
        if any_dimension_max is not None:
            v = Decimal(str(any_dimension_max))
            q = q.filter(or_(
                Product.dimensions_length <= v,
                Product.dimensions_width <= v,
                Product.dimensions_height <= v,
            ))

        if query:
            tokens = [t for t in str(query).split() if t]
            for tok in tokens:
                like = f"%{tok}%"
                q = q.filter(or_(
                    Product.product_code.ilike(like),
                    Product.product_name.ilike(like),
                    Product.description.ilike(like),
                    Product.item_type.ilike(like),
                    Promotion.promo_code.ilike(like),
                ))

        # Sorting
        sort_map = {
            "created_at": PromotionProduct.created_at,
        }
        sort_column = sort_map.get(sort_field, PromotionProduct.created_at)
        if sort_dir == "desc":
            q = q.order_by(sort_column.desc())
        else:
            q = q.order_by(sort_column.asc())
        
        total = q.count()
        offset = (page - 1) * limit
        products = q.offset(offset).limit(limit).all()

        # Inline parent-promotion attachments per line so callers (esp. MCP
        # agents) don't need a follow-up tool call to fetch the promotion
        # document for the SKU they just asked about.
        parent_pids = list({p.promotion_id for p in products})
        attachments_map = _load_attachments_by_promotion_ids(self.db, parent_pids)
        for line in products:
            line.promotion_attachments = attachments_map.get(line.promotion_id, [])

        return {
            "data": products,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }

    def get_promotion_line(self, promotion_id: str, line_id: str):
        """Get a promotion product row by junction id (supports same SKU in multiple groups)."""
        from sqlalchemy.orm import joinedload

        row = (
            self.db.query(PromotionProduct)
            .options(
                joinedload(PromotionProduct.product),
                joinedload(PromotionProduct.promotion),
                joinedload(PromotionProduct.promotion_group),
            )
            .filter(
                PromotionProduct.id == line_id,
                PromotionProduct.promotion_id == promotion_id,
            )
            .first()
        )
        if not row:
            raise handle_not_found("Promotion product line", f"{promotion_id}/{line_id}")
        return row

    def get_promotion_product(self, promotion_id: str, product_id: str):
        """Deprecated: use get_promotion_line. Returns first matching row if duplicates exist."""
        from sqlalchemy.orm import joinedload

        row = (
            self.db.query(PromotionProduct)
            .options(joinedload(PromotionProduct.product), joinedload(PromotionProduct.promotion))
            .filter(
                PromotionProduct.promotion_id == promotion_id,
                PromotionProduct.product_id == product_id,
            )
            .first()
        )
        if not row:
            raise handle_not_found("Promotion Product", f"{promotion_id}/{product_id}")
        return row
    
    def create_promotion_product(self, product_data: PromotionProductCreate):
        """Add a product to a promotion (within a group; default group if omitted)."""
        from sqlalchemy.orm import joinedload
        from app.models.product import Product

        pdata = product_data.model_dump()
        group_id = pdata.get("promotion_group_id")
        if not group_id:
            g = self.get_or_create_default_promotion_group(product_data.promotion_id)
            group_id = g.id
        else:
            g = (
                self.db.query(PromotionGroup)
                .filter(
                    PromotionGroup.id == group_id,
                    PromotionGroup.promotion_id == product_data.promotion_id,
                )
                .first()
            )
            if not g:
                raise handle_not_found("Promotion group", str(group_id))
        
        existing = self.db.query(PromotionProduct).filter(
            PromotionProduct.promotion_group_id == group_id,
            PromotionProduct.product_id == product_data.product_id
        ).first()
        if existing:
            label = _product_display_label(self.db, product_data.product_id)
            raise handle_conflict(f"Product already in this promotion group: {label}.")
        
        # Get the product to calculate discount
        product = self.db.query(Product).filter(Product.id == product_data.product_id).first()
        if not product:
            raise handle_not_found("Product", product_data.product_id)
        
        promo_selling_price = product_data.promo_selling_price
        discount_amount = None
        discount_percent = None
        
        if promo_selling_price and product.list_price:
            list_price = float(product.list_price)
            promo_price = float(promo_selling_price)
            discount_amount, discount_percent = self._compute_discount_values(list_price, promo_price)

        dd = product_data.dealer_discount_percent
        dd_f = float(dd) if dd is not None else None
        dealer_cost, list_to_dealer_margin = dealer_cost_and_margin_from_list(
            float(product.list_price) if product.list_price is not None else None,
            dd_f,
        )
        
        promotion_product = PromotionProduct(
            promotion_id=product_data.promotion_id,
            promotion_group_id=group_id,
            product_id=product_data.product_id,
            promo_selling_price=promo_selling_price,
            discount_amount=discount_amount,
            discount_percent=discount_percent,
            dealer_discount_percent=dd,
            dealer_cost=dealer_cost,
            list_to_dealer_margin_amount=list_to_dealer_margin,
        )
        self.db.add(promotion_product)
        try:
            self.db.commit()
            self.db.refresh(promotion_product)
        except IntegrityError as e:
            self.db.rollback()
            raise_promotion_product_unique_violation(self.db, e)

        # Reload with product and promotion relationships
        return self.db.query(PromotionProduct).options(
            joinedload(PromotionProduct.product),
            joinedload(PromotionProduct.promotion)
        ).filter(PromotionProduct.id == promotion_product.id).first()
    
    def update_promotion_product(self, promotion_id: str, line_id: str, product_data: PromotionProductUpdate):
        """Update a promotion product line (by promotion_products.id)."""
        from sqlalchemy.orm import joinedload
        from app.models.product import Product
        
        promotion_product = self.get_promotion_line(promotion_id, line_id)
        product = self.db.query(Product).filter(Product.id == promotion_product.product_id).first()
        
        update_data = product_data.model_dump(exclude_unset=True)

        list_price_new = update_data.pop('list_price', None)
        if list_price_new is not None:
            if product is None:
                raise handle_not_found("Product", promotion_product.product_id)
            lp_dec = list_price_new
            if lp_dec < 0:
                raise handle_validation_error("List price cannot be negative.")
            product.list_price = lp_dec

        recompute_discount = (
            ('promo_selling_price' in update_data or list_price_new is not None)
            and product
            and product.list_price is not None
        )
        if recompute_discount:
            promo_src = update_data.get('promo_selling_price', promotion_product.promo_selling_price)
            if promo_src is not None:
                promo_price = float(promo_src)
                list_price = float(product.list_price)
                discount_amount, discount_percent = self._compute_discount_values(list_price, promo_price)
                update_data['discount_amount'] = discount_amount
                update_data['discount_percent'] = discount_percent

        recompute_dealer = ('dealer_discount_percent' in update_data or list_price_new is not None) and product
        if recompute_dealer:
            dd = (
                update_data['dealer_discount_percent']
                if 'dealer_discount_percent' in update_data
                else promotion_product.dealer_discount_percent
            )
            dd_f = float(dd) if dd is not None else None
            dc, margin = dealer_cost_and_margin_from_list(
                float(product.list_price) if product.list_price is not None else None,
                dd_f,
            )
            update_data['dealer_cost'] = dc
            update_data['list_to_dealer_margin_amount'] = margin

        for key, value in update_data.items():
            setattr(promotion_product, key, value)
        
        self.db.commit()
        self.db.refresh(promotion_product)
        
        return self.db.query(PromotionProduct).options(
            joinedload(PromotionProduct.product),
            joinedload(PromotionProduct.promotion)
        ).filter(PromotionProduct.id == promotion_product.id).first()
    
    def delete_promotion_product(self, promotion_id: str, line_id: str):
        """Remove a promotion product line from a promotion."""
        row = self.get_promotion_line(promotion_id, line_id)
        self.db.delete(row)
        self.db.commit()
        return {"message": "Product removed from promotion"}


class CampaignTypeService:
    """Service for campaign type operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_campaign_types(self):
        """List all campaign types."""
        try:
            return self.db.query(CampaignType).all()
        except Exception as exc:
            # Backward-compat for environments where campaign_types.type_code is missing.
            if "campaign_types.type_code" not in str(exc):
                raise
            self.db.rollback()
            rows = self._fallback_campaign_type_rows()
            fallback = []
            for row in rows:
                fallback.append(
                    {
                        "id": str(row.id),
                        "type_code": str(row.type_name or row.id),
                        "type_name": row.type_name,
                        "description": row.description,
                        "created_at": row.created_at,
                        "updated_at": row.updated_at or row.created_at,
                    }
                )
            return fallback
    
    def get_campaign_type(self, type_id: str):
        """Get a campaign type by ID."""
        try:
            campaign_type = self.db.query(CampaignType).filter(CampaignType.id == type_id).first()
            if not campaign_type:
                raise handle_not_found("Campaign Type", type_id)
            return campaign_type
        except Exception as exc:
            if "campaign_types.type_code" not in str(exc):
                raise
            self.db.rollback()
            rows = self._fallback_campaign_type_rows(type_id=type_id)
            row = rows[0] if rows else None
            if not row:
                raise handle_not_found("Campaign Type", type_id)
            return {
                "id": str(row.id),
                "type_code": str(row.type_name or row.id),
                "type_name": row.type_name,
                "description": row.description,
                "created_at": row.created_at,
                "updated_at": row.updated_at or row.created_at,
            }

    def _fallback_campaign_type_rows(self, type_id: str | None = None):
        """Read campaign_types using only columns that exist in older DBs."""
        cols = self.db.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'campaign_types'"
            )
        ).all()
        existing = {c[0] for c in cols}
        select_parts = [
            "id",
            "type_name",
            "description" if "description" in existing else "NULL::text AS description",
            "created_at" if "created_at" in existing else "NOW() AS created_at",
            "updated_at" if "updated_at" in existing else "NULL::timestamp AS updated_at",
        ]
        sql = "SELECT " + ", ".join(select_parts) + " FROM campaign_types"
        params = {}
        if type_id is not None:
            sql += " WHERE id = :type_id"
            params["type_id"] = type_id
        return self.db.execute(text(sql), params).all()
    
    def create_campaign_type(self, type_data: CampaignTypeCreate):
        """Create a new campaign type."""
        existing = self.db.query(CampaignType).filter(
            CampaignType.type_code == type_data.type_code
        ).first()
        if existing:
            raise handle_conflict("Campaign type code already exists.")
        
        campaign_type = CampaignType(**type_data.model_dump())
        self.db.add(campaign_type)
        self.db.commit()
        self.db.refresh(campaign_type)
        return campaign_type
    
    def update_campaign_type(self, type_id: str, type_data: CampaignTypeUpdate):
        """Update a campaign type."""
        campaign_type = self.get_campaign_type(type_id)
        
        update_data = type_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(campaign_type, key, value)
        
        self.db.commit()
        self.db.refresh(campaign_type)
        return campaign_type


class MarketingCampaignService:
    """Service for marketing campaign operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_campaigns(self, page: int = 1, limit: int = 50):
        """List marketing campaigns."""
        q = self.db.query(MarketingCampaign).order_by(MarketingCampaign.created_at.desc())
        
        total = q.count()
        offset = (page - 1) * limit
        campaigns = q.offset(offset).limit(limit).all()
        
        return {
            "data": campaigns,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_campaign(self, campaign_id: str):
        """Get a campaign by ID."""
        campaign = self.db.query(MarketingCampaign).filter(MarketingCampaign.id == campaign_id).first()
        if not campaign:
            raise handle_not_found("Marketing Campaign", campaign_id)
        return campaign
    
    def create_campaign(self, campaign_data: MarketingCampaignCreate, created_by: str):
        """Create a new marketing campaign."""
        existing = self.db.query(MarketingCampaign).filter(
            MarketingCampaign.campaign_code == campaign_data.campaign_code
        ).first()
        if existing:
            raise handle_conflict("Campaign code already exists.")
        
        campaign_dict = campaign_data.model_dump()
        campaign_dict["created_by"] = created_by
        campaign = MarketingCampaign(**campaign_dict)
        self.db.add(campaign)
        self.db.commit()
        self.db.refresh(campaign)
        return campaign
    
    def update_campaign(self, campaign_id: str, campaign_data: MarketingCampaignUpdate):
        """Update a marketing campaign."""
        campaign = self.get_campaign(campaign_id)
        
        update_data = campaign_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(campaign, key, value)
        
        self.db.commit()
        self.db.refresh(campaign)
        return campaign


class PromotionAttachmentService:
    """Service for promotion attachment operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_promotion_attachments(
        self,
        page: int = 1,
        limit: int = 50,
        sort_field: str = "created_at",
        sort_dir: str = "asc",
        promotion_id: Optional[str] = None,
        attachment_id: Optional[str] = None,
        query: Optional[str] = None,
        contact_access_codes: Optional[list[str]] = None,
    ):
        """List promotion attachments with pagination and filtering.

        When *contact_access_codes* is supplied the result is restricted to attachments
        whose underlying file's ``access_levels`` overlaps the contact's codes (and whose
        parent promotion's ``access_levels`` also overlaps). ``contact_access_codes=[]``
        returns nothing (contact has no assigned access types).
        """
        from sqlalchemy.orm import joinedload
        from sqlalchemy import or_
        from app.schemas.common import PaginationResponse

        q = self.db.query(PromotionAttachment).options(
            joinedload(PromotionAttachment.promotion),
            joinedload(PromotionAttachment.attachment).joinedload(Attachment.attachment_type)
        )

        if contact_access_codes is not None:
            if not contact_access_codes:
                q = q.filter(text("false"))
            else:
                codes_arr = cast(contact_access_codes, ARRAY(String))
                q = q.filter(
                    PromotionAttachment.promotion.has(
                        Promotion.access_levels.op("?|")(codes_arr)
                    ),
                    PromotionAttachment.attachment.has(
                        Attachment.access_levels.op("?|")(codes_arr)
                    ),
                )

        fallback_query = query
        if promotion_id:
            resolved_pid = _resolve_promotion_id_for_filter(self.db, promotion_id)
            if resolved_pid is None:
                # If caller passed a product/promo search token in promotion_id by mistake,
                # treat it as a text search instead of returning empty.
                fallback_query = str(promotion_id).strip()
            else:
                q = q.filter(PromotionAttachment.promotion_id == resolved_pid)
        if attachment_id:
            q = q.filter(PromotionAttachment.attachment_id == attachment_id)
        if fallback_query:
            term = f"%{fallback_query.strip()}%"
            q = (
                q.join(Promotion, PromotionAttachment.promotion_id == Promotion.id)
                .outerjoin(PromotionProduct, PromotionProduct.promotion_id == Promotion.id)
                .outerjoin(Product, PromotionProduct.product_id == Product.id)
                .outerjoin(PromotionGroup, PromotionProduct.promotion_group_id == PromotionGroup.id)
                .outerjoin(Attachment, PromotionAttachment.attachment_id == Attachment.id)
                .filter(
                    or_(
                        Promotion.promo_code.ilike(term),
                        Promotion.name.ilike(term),
                        Promotion.description.ilike(term),
                        Product.product_code.ilike(term),
                        Product.product_name.ilike(term),
                        PromotionGroup.group_name.ilike(term),
                        Attachment.original_filename.ilike(term),
                        Attachment.description.ilike(term),
                    )
                )
            )
        
        # Sorting
        sort_map = {
            "created_at": PromotionAttachment.created_at,
            "sort_order": PromotionAttachment.sort_order,
        }
        sort_column = sort_map.get(sort_field, PromotionAttachment.created_at)
        if sort_dir == "desc":
            q = q.order_by(sort_column.desc())
        else:
            q = q.order_by(sort_column.asc())
        
        total = q.count()
        offset = (page - 1) * limit
        promotion_attachments = q.offset(offset).limit(limit).all()

        return {
            "data": promotion_attachments,
            "pagination": PaginationResponse(total=total, page=page, limit=limit),
            "empty": total == 0
        }
    
    def get_promotion_attachment(self, promotion_attachment_id: str):
        """Get a promotion attachment by ID."""
        from sqlalchemy.orm import joinedload
        promotion_attachment = self.db.query(PromotionAttachment).options(
            joinedload(PromotionAttachment.promotion),
            joinedload(PromotionAttachment.attachment).joinedload(Attachment.attachment_type)
        ).filter(PromotionAttachment.id == promotion_attachment_id).first()
        if not promotion_attachment:
            raise handle_not_found("Promotion Attachment", promotion_attachment_id)
        return promotion_attachment
    
    def create_promotion_attachment(self, promotion_attachment_data: PromotionAttachmentCreate, created_by: Optional[str] = None):
        """Create a new promotion attachment relationship."""
        # Check if relationship already exists
        existing = self.db.query(PromotionAttachment).filter(
            PromotionAttachment.promotion_id == promotion_attachment_data.promotion_id,
            PromotionAttachment.attachment_id == promotion_attachment_data.attachment_id
        ).first()
        if existing:
            raise handle_conflict("Promotion attachment relationship already exists.")
        
        attachment_dict = promotion_attachment_data.model_dump()
        if created_by:
            attachment_dict["created_by"] = created_by
        
        promotion_attachment = PromotionAttachment(**attachment_dict)
        self.db.add(promotion_attachment)
        self.db.commit()
        self.db.refresh(promotion_attachment)
        
        # Reload with relationships
        from sqlalchemy.orm import joinedload
        return self.db.query(PromotionAttachment).options(
            joinedload(PromotionAttachment.promotion),
            joinedload(PromotionAttachment.attachment).joinedload(Attachment.attachment_type)
        ).filter(PromotionAttachment.id == promotion_attachment.id).first()
    
    def update_promotion_attachment(self, promotion_attachment_id: str, promotion_attachment_data: PromotionAttachmentUpdate):
        """Update a promotion attachment relationship."""
        promotion_attachment = self.get_promotion_attachment(promotion_attachment_id)
        
        update_data = promotion_attachment_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(promotion_attachment, key, value)
        
        from datetime import datetime
        promotion_attachment.updated_at = datetime.now()
        
        self.db.commit()
        self.db.refresh(promotion_attachment)
        
        # Reload with relationships
        from sqlalchemy.orm import joinedload
        return self.db.query(PromotionAttachment).options(
            joinedload(PromotionAttachment.promotion),
            joinedload(PromotionAttachment.attachment).joinedload(Attachment.attachment_type)
        ).filter(PromotionAttachment.id == promotion_attachment.id).first()
    
    def delete_promotion_attachment(self, promotion_attachment_id: str):
        """Delete a promotion attachment relationship."""
        promotion_attachment = self.get_promotion_attachment(promotion_attachment_id)
        self.db.delete(promotion_attachment)
        self.db.commit()
        return {"message": "Promotion attachment deleted successfully"}
    
    def get_promotion_attachments_by_promotion(
        self,
        promotion_id: str,
        contact_access_codes: Optional[list[str]] = None,
    ):
        """Get all attachments for a specific promotion.

        When *contact_access_codes* is supplied, filters out the entire result if the
        parent promotion's ``access_levels`` does not overlap, then drops individual
        attachments whose own ``access_levels`` does not overlap.
        """
        from sqlalchemy.orm import joinedload

        resolved_pid = _resolve_promotion_id_for_filter(self.db, promotion_id)
        if resolved_pid is None:
            return []

        if contact_access_codes is not None:
            if not contact_access_codes:
                return []
            promotion = (
                self.db.query(Promotion)
                .filter(Promotion.id == resolved_pid)
                .first()
            )
            promo_levels = getattr(promotion, "access_levels", None) if promotion else None
            if not isinstance(promo_levels, list) or not set(contact_access_codes).intersection(promo_levels):
                return []

        promotion_attachments = self.db.query(PromotionAttachment).options(
            joinedload(PromotionAttachment.promotion),
            joinedload(PromotionAttachment.attachment).joinedload(Attachment.attachment_type)
        ).filter(PromotionAttachment.promotion_id == resolved_pid).order_by(
            PromotionAttachment.sort_order.asc().nulls_last(),
            PromotionAttachment.created_at.asc()
        ).all()
        if contact_access_codes is not None:
            promotion_attachments = PromotionService._filter_attachments_by_codes(
                promotion_attachments, contact_access_codes
            )
        return promotion_attachments
