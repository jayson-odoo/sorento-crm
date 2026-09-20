"""Product combo CRUD (PLAN-price-tag-combos D1, slice S1).

Company scope is NOT an argument. The HOST product is resolved through an ORM query,
so `do_orm_execute` applies the caller's scope; a host belonging to another company
simply is not found, and every entry point answers 404 rather than an empty list
(AC-S1-7). An empty list would read as "this cabinet has no packages" and invite
marketing to build a second set of combos on a product they cannot see.

The route contract (the frontend already mocks it, Phase 1, the header of
`productComboService.ts` is the authority):

    GET    /api/v1/master-data/products/{id}/combos          -> {"data": [...]}
    POST   /api/v1/master-data/products/{id}/combos          -> row (201), 409
    PATCH  /api/v1/master-data/product-combos/{combo_id}     -> row
    DELETE /api/v1/master-data/product-combos/{combo_id}     -> 204
    POST   /api/v1/master-data/product-combos/{id}/parts     -> row (201), 422
    PATCH  /api/v1/master-data/product-combo-parts/{id}      -> row
    DELETE /api/v1/master-data/product-combo-parts/{id}      -> 204
    GET    /api/v1/master-data/products/{id}/sold-with       -> {"data": [...]}
    POST   /api/v1/master-data/product-combos/{id}/image      multipart -> {attachment_id, url}
    DELETE /api/v1/master-data/product-combos/{id}/image      -> 204

The image pair (S5, PLAN-price-tag-r10.md) is the combo's OWN cover picture -
stored as an `attachments` row of type ``Combo Image``, linked to the HOST
product through `product_attachments` (so it shows up in that product's
gallery too, ranked last - `product_images.gallery_images`) and pointed at by
`ProductCombo.image_attachment_id`. A second upload REPLACES the first (old
row deleted, bytes swept); `DELETE` clears the pointer and deletes the row.
"""
from __future__ import annotations

import hashlib
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.product import Product, ProductAttachment
from app.models.product_combo import ProductCombo, ProductComboPart
from app.models.resources import Attachment, AttachmentType
from app.services.error_handler import AppException, handle_not_found
from app.services.company_scope import get_company_scope, resolve_write_company_id
from app.services.storage_router import (
    cdn_base_url,
    default_provider,
    delete_object_best_effort,
    get_backend,
    resolve_signed_url,
)

#: Combo Image (migration ptag_0013_r10) - images only, 10 MB.
COMBO_IMAGE_TYPE_CODE = "combo_image"
MAX_COMBO_IMAGE_BYTES = 10 * 1024 * 1024
STORAGE_ENTITY_TYPE = "product_combo_image"


def _dimensions(product: Optional[Product]) -> Optional[str]:
    """`800 x 500 x 220 mm`, through the ONE formatter the tag and the catalogue
    tile already share - a second one would eventually print a part with different
    punctuation on the tag than on the product page."""
    if product is None:
        return None
    # Imported here rather than at module import: the dealer-kit package pulls in
    # the whole tag data chain, and master data has no reason to load it just to
    # answer a list of combos.
    from app.services.dealer_kit.tag_data_service import format_dimensions_mm

    return format_dimensions_mm(
        product.dimensions_length, product.dimensions_width, product.dimensions_height
    )


def _serialize_part(part: ProductComboPart) -> Dict[str, Any]:
    product = part.part_product
    return {
        "id": part.id,
        "combo_id": part.combo_id,
        "product_id": part.part_product_id,
        "code": product.product_code if product else "",
        "product_name": product.product_name if product else "",
        "dimensions": _dimensions(product),
        "choice_group": part.choice_group,
        "sort_order": part.sort_order,
    }


def _serialize_image(db: Session, combo: ProductCombo) -> Optional[Dict[str, Any]]:
    """AC-S5-4: null with no picture, else `{attachment_id, url}` - a strict
    signed URL, same rule every other tag/catalogue photo follows: absent
    rather than a link that 403s."""
    if not combo.image_attachment_id:
        return None
    attachment = (
        db.query(Attachment)
        .filter(Attachment.id == combo.image_attachment_id, Attachment.is_deleted.is_(False))
        .first()
    )
    if attachment is None:
        return None
    url = resolve_signed_url(
        attachment.file_path, provider=attachment.storage_provider, strict=True
    )
    if not url:
        return None
    return {"attachment_id": attachment.id, "url": url}


def _serialize(combo: ProductCombo, db: Optional[Session] = None) -> Dict[str, Any]:
    return {
        "id": combo.id,
        "host_product_id": combo.host_product_id,
        "name": combo.name,
        "sort_order": combo.sort_order,
        "parts": [_serialize_part(part) for part in combo.parts],
        "image": _serialize_image(db, combo) if db is not None else None,
        "created_at": combo.created_at,
        "updated_at": combo.updated_at,
    }


class ProductComboService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ reads

    def list_for_host(self, host_product_id: str) -> List[Dict[str, Any]]:
        self._host_or_404(host_product_id)
        rows = (
            self._query()
            .filter(ProductCombo.host_product_id == host_product_id)
            .order_by(ProductCombo.sort_order.asc(), ProductCombo.name.asc())
            .all()
        )
        return [_serialize(combo, self.db) for combo in rows]

    def list_sold_with(self, part_product_id: str) -> List[Dict[str, Any]]:
        """Every host + combo naming this product, across hosts (AC-S1-6).

        A basin sold with two different cabinets is exactly what this list exists
        for; one row would quietly hide the other cabinet.
        """
        self._host_or_404(part_product_id)
        # Joined to `Product` on purpose, not just eager-loaded: `ProductCombo`
        # is not company-scoped on its own (it hangs off the host, which is), so
        # without a scoped entity in the query the company predicate never
        # attaches and another company's combo comes back - with an empty code
        # and name, because the eager load IS scoped, which leaked a bare host
        # uuid onto the page (security review S1, and the no-UUID rule).
        rows = (
            self.db.query(ProductCombo, Product)
            .join(Product, Product.id == ProductCombo.host_product_id)
            .join(ProductComboPart, ProductComboPart.combo_id == ProductCombo.id)
            .filter(ProductComboPart.part_product_id == part_product_id)
            .order_by(ProductCombo.sort_order.asc(), ProductCombo.name.asc())
            .all()
        )
        out: List[Dict[str, Any]] = []
        for combo, host in rows:
            if host is None:
                continue
            out.append(
                {
                    "host_product_id": combo.host_product_id,
                    "host_code": host.product_code,
                    "host_name": host.product_name,
                    "combo_id": combo.id,
                    "combo_name": combo.name,
                }
            )
        return out

    # ----------------------------------------------------------------- combos

    def create(self, host_product_id: str, name: str, *, created_by: Optional[str]) -> Dict[str, Any]:
        self._host_or_404(host_product_id)
        cleaned = (name or "").strip()
        if not cleaned:
            raise AppException(status_code=422, message="A combo needs a name")

        # `lower(name) = lower(...)`, not `ilike`: a name containing `%` or `_`
        # is a LIKE wildcard, so "3 in 1%" would have matched every other combo
        # on the host and refused a name nobody had taken.
        taken = (
            self.db.query(ProductCombo)
            .filter(
                ProductCombo.host_product_id == host_product_id,
                func.lower(ProductCombo.name) == cleaned.lower(),
            )
            .first()
        )
        if taken is not None:
            raise AppException(
                status_code=409,
                message=f'This product already has a combo called "{cleaned}"',
                code="COMBO_NAME_TAKEN",
            )

        next_order = (
            self.db.query(ProductCombo)
            .filter(ProductCombo.host_product_id == host_product_id)
            .count()
        )
        combo = ProductCombo(
            host_product_id=host_product_id,
            name=cleaned,
            sort_order=next_order,
            created_by=created_by,
        )
        self.db.add(combo)
        self.db.commit()
        return _serialize(self._combo_or_404(combo.id), self.db)

    def update(self, combo_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        combo = self._combo_or_404(combo_id)
        if "name" in payload and payload["name"] is not None:
            cleaned = str(payload["name"]).strip()
            if not cleaned:
                raise AppException(status_code=422, message="A combo needs a name")
            taken = (
                self.db.query(ProductCombo)
                .filter(
                    ProductCombo.host_product_id == combo.host_product_id,
                    func.lower(ProductCombo.name) == cleaned.lower(),
                    ProductCombo.id != combo.id,
                )
                .first()
            )
            if taken is not None:
                raise AppException(
                    status_code=409,
                    message=f'This product already has a combo called "{cleaned}"',
                    code="COMBO_NAME_TAKEN",
                )
            combo.name = cleaned
        if payload.get("sort_order") is not None:
            combo.sort_order = int(payload["sort_order"])
        self.db.commit()
        return _serialize(self._combo_or_404(combo.id), self.db)

    def delete(self, combo_id: str) -> None:
        """Hard delete, per the CRUD standard. The parts cascade with it; the
        products do not, and a request line pointing at it has its `combo_id`
        cleared by the FK's own SET NULL rather than being deleted (AC-S1-5)."""
        combo = self._combo_or_404(combo_id)
        self.db.delete(combo)
        self.db.commit()

    # ------------------------------------------------------------------ image

    def upload_image(
        self,
        combo_id: str,
        *,
        content: bytes,
        filename: str,
        content_type: Optional[str],
        user_id: Optional[str],
    ) -> Dict[str, Any]:
        """AC-S5-2/S5-3: put the picture in storage, link it to the HOST
        product (so it shows in that product's own gallery too, ranked last),
        and point the combo at it - replacing whatever it pointed at before.
        """
        combo = self._combo_or_404(combo_id)

        if not content:
            raise AppException(status_code=422, message="The uploaded file is empty.")
        if len(content) > MAX_COMBO_IMAGE_BYTES:
            raise AppException(
                status_code=422,
                message=f"Images must be under {MAX_COMBO_IMAGE_BYTES // (1024 * 1024)} MB.",
            )
        if not (content_type or "").lower().startswith("image/"):
            raise AppException(status_code=422, message="Only image files are accepted.")

        combo_type = self._combo_image_type()
        attachment_id = str(uuid.uuid4())
        safe_name = (filename or "combo-image").rsplit("/", 1)[-1][:255]
        key = f"{STORAGE_ENTITY_TYPE}/{attachment_id}/{safe_name}"

        provider = default_provider()
        backend = get_backend(provider)
        stored_key, _url = backend.upload_file(
            file_content=content, file_path=key, content_type=content_type
        )

        try:
            attachment = Attachment(
                id=attachment_id,
                attachment_type_id=combo_type.id,
                original_filename=safe_name,
                stored_filename=safe_name,
                file_path=cdn_base_url(provider, stored_key),
                file_size_bytes=len(content),
                mime_type=content_type,
                file_hash=hashlib.sha256(content).hexdigest(),
                entity_type=STORAGE_ENTITY_TYPE,
                uploaded_by=user_id,
                uploader_kind="user" if user_id else "system",
                storage_provider=provider,
                company_id=resolve_write_company_id(get_company_scope(self.db), ambiguous=None),
            )
            self.db.add(attachment)
            self.db.flush()

            # AC-S5-2: linked to the HOST product, the same table every other
            # product photo lives in - `gallery_images` already ranks a Combo
            # Image last (AC-S5-11), so the combo's own picture shows up in
            # the host's gallery too, just never leading it by accident.
            self.db.add(
                ProductAttachment(
                    id=str(uuid.uuid4()),
                    product_id=combo.host_product_id,
                    attachment_id=attachment.id,
                    is_primary=False,
                    access_levels=["dealer", "end_user"],
                    company_id=resolve_write_company_id(
                        get_company_scope(self.db), ambiguous=None
                    ),
                )
            )

            # AC-S5-3: a second upload replaces the first - old row deleted,
            # its bytes swept, so a combo never accumulates orphaned pictures.
            previous_attachment_id = combo.image_attachment_id
            combo.image_attachment_id = attachment.id
            self.db.flush()
            if previous_attachment_id and previous_attachment_id != attachment.id:
                self._delete_attachment(previous_attachment_id)

            self.db.commit()
        except Exception:
            delete_object_best_effort(provider, stored_key)
            raise

        return _serialize_image(self.db, self._combo_or_404(combo.id))

    def delete_image(self, combo_id: str) -> None:
        """AC-S5-3: clears the pointer and deletes the attachment row - the
        picture is the combo's own, not shared with anything that should
        survive it."""
        combo = self._combo_or_404(combo_id)
        attachment_id = combo.image_attachment_id
        combo.image_attachment_id = None
        self.db.flush()
        if attachment_id:
            self._delete_attachment(attachment_id)
        self.db.commit()

    def _combo_image_type(self) -> AttachmentType:
        """The `Combo Image` type row, seeded idempotently by the migration in
        production - get-or-create here too, the same shape
        `test_dealer_kit_product_images.py`'s own `_typed_image` helper
        follows, since a test's blank schema never ran the migration's data
        step."""
        row = (
            self.db.query(AttachmentType)
            .filter(AttachmentType.code == COMBO_IMAGE_TYPE_CODE)
            .first()
        )
        if row is not None:
            return row
        row = AttachmentType(
            id=str(uuid.uuid4()),
            code=COMBO_IMAGE_TYPE_CODE,
            type_name="Combo Image",
            allowed_extensions="jpg,jpeg,png,webp",
            max_file_size_mb=MAX_COMBO_IMAGE_BYTES // (1024 * 1024),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _delete_attachment(self, attachment_id: str) -> None:
        """Hard delete: the row, its product link, and its stored bytes."""
        from app.services.storage_router import extract_key

        attachment = self.db.query(Attachment).filter(Attachment.id == attachment_id).first()
        if attachment is None:
            return
        self.db.query(ProductAttachment).filter(
            ProductAttachment.attachment_id == attachment_id
        ).delete(synchronize_session=False)
        provider = attachment.storage_provider
        key = extract_key(attachment.file_path)
        self.db.delete(attachment)
        self.db.flush()
        if key:
            delete_object_best_effort(provider, key)

    # ------------------------------------------------------------------ parts

    def add_part(
        self, combo_id: str, part_product_id: str, choice_group: Optional[str]
    ) -> Dict[str, Any]:
        combo = self._combo_or_404(combo_id)
        if part_product_id == combo.host_product_id:
            raise AppException(
                status_code=422,
                message="A product cannot be a part of its own combo",
                code="COMBO_PART_IS_HOST",
            )
        # Scoped, so a well-formed id naming a product in another company reads
        # exactly like one that does not exist - which is the correct answer.
        product = self.db.query(Product).filter(Product.id == part_product_id).first()
        if product is None:
            raise handle_not_found("Product", part_product_id)

        duplicate = (
            self.db.query(ProductComboPart)
            .filter(
                ProductComboPart.combo_id == combo_id,
                ProductComboPart.part_product_id == part_product_id,
            )
            .first()
        )
        if duplicate is not None:
            raise AppException(
                status_code=422,
                message="That product is already on this combo",
                code="COMBO_PART_DUPLICATE",
            )

        part = ProductComboPart(
            combo_id=combo_id,
            part_product_id=part_product_id,
            choice_group=(choice_group or "").strip() or None,
            sort_order=len(combo.parts),
        )
        self.db.add(part)
        self.db.commit()
        return _serialize_part(self._part_or_404(part.id))

    def update_part(self, part_id: str, payload: Dict[str, Any], *, fields_set) -> Dict[str, Any]:
        part = self._part_or_404(part_id)
        if "choice_group" in fields_set:
            raw = payload.get("choice_group")
            part.choice_group = (raw or "").strip() or None
        if payload.get("sort_order") is not None:
            part.sort_order = int(payload["sort_order"])
        self.db.commit()
        return _serialize_part(self._part_or_404(part.id))

    def delete_part(self, part_id: str) -> None:
        part = self._part_or_404(part_id)
        self.db.delete(part)
        self.db.commit()

    # -------------------------------------------------------------- internals

    def _query(self):
        return self.db.query(ProductCombo).options(
            joinedload(ProductCombo.parts).joinedload(ProductComboPart.part_product)
        )

    def _host_or_404(self, product_id: str) -> Product:
        """The scope gate. Every entry point goes through it, including the two
        that only read, so a cross-company id never answers with an empty list."""
        product = self.db.query(Product).filter(Product.id == product_id).first()
        if product is None:
            raise handle_not_found("Product", product_id)
        return product

    def _combo_or_404(self, combo_id: str) -> ProductCombo:
        combo = self._query().filter(ProductCombo.id == combo_id).first()
        if combo is None:
            raise handle_not_found("Combo", combo_id)
        # Scoped through the host, the same rule the list takes.
        self._host_or_404(combo.host_product_id)
        return combo

    def _part_or_404(self, part_id: str) -> ProductComboPart:
        part = (
            self.db.query(ProductComboPart)
            .options(joinedload(ProductComboPart.part_product))
            .filter(ProductComboPart.id == part_id)
            .first()
        )
        if part is None:
            raise handle_not_found("Combo part", part_id)
        self._combo_or_404(part.combo_id)
        return part
