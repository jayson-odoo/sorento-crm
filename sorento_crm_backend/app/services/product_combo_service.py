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

#: AC-S5-12: the allowlist is the FILENAME extension, never the client's own
#: `Content-Type` header - a `.svg` claiming `image/svg+xml` is refused, and
#: an `.exe` claiming `image/png` is refused by its extension regardless of
#: what it says it is. Mirrors `shipment_line_photos._validated_image_ext`.
_IMAGE_EXTS = {"jpg", "jpeg", "png", "webp"}
_IMAGE_MIME_BY_EXT = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


def _validated_image_ext(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _IMAGE_EXTS:
        raise AppException(
            status_code=422,
            message=f"{filename} is not an image (jpg, jpeg, png or webp).",
        )
    return ext


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


def _serialize(combo: ProductCombo, db: Session) -> Dict[str, Any]:
    return {
        "id": combo.id,
        "host_product_id": combo.host_product_id,
        "name": combo.name,
        "sort_order": combo.sort_order,
        "parts": [_serialize_part(part) for part in combo.parts],
        "image": _serialize_image(db, combo),
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
        # AC-S5-12: the extension decides, never the client's `Content-Type` -
        # the stored mime is DERIVED from it too, below.
        ext = _validated_image_ext(filename or "")
        stored_content_type = _IMAGE_MIME_BY_EXT[ext]

        combo_type = self._combo_image_type()
        attachment_id = str(uuid.uuid4())
        safe_name = (filename or "combo-image").rsplit("/", 1)[-1][:255]
        key = f"{STORAGE_ENTITY_TYPE}/{attachment_id}/{safe_name}"
        # AC-S5-12: the host product's own company, not the caller's write
        # scope - a combo image is data of the host it pictures.
        host_company_id = combo.host_product.company_id

        provider = default_provider()
        backend = get_backend(provider)
        stored_key, _url = backend.upload_file(
            file_content=content, file_path=key, content_type=stored_content_type
        )

        sweep: Optional[tuple] = None
        try:
            attachment = Attachment(
                id=attachment_id,
                attachment_type_id=combo_type.id,
                original_filename=safe_name,
                stored_filename=safe_name,
                file_path=cdn_base_url(provider, stored_key),
                file_size_bytes=len(content),
                mime_type=stored_content_type,
                file_hash=hashlib.sha256(content).hexdigest(),
                entity_type=STORAGE_ENTITY_TYPE,
                uploaded_by=user_id,
                uploader_kind="user" if user_id else "system",
                storage_provider=provider,
                company_id=host_company_id,
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
                    company_id=host_company_id,
                )
            )

            # AC-S5-3/S5-12: a second upload replaces the first - the combo's
            # OWN link to the old attachment is dropped, and the row (plus its
            # bytes) is swept only when no other product's own link still
            # points at it.
            previous_attachment_id = combo.image_attachment_id
            combo.image_attachment_id = attachment.id
            self.db.flush()
            if previous_attachment_id and previous_attachment_id != attachment.id:
                sweep = self._unlink_combo_image(combo, previous_attachment_id)

            self.db.commit()
        except Exception:
            delete_object_best_effort(provider, stored_key)
            raise

        # AC-S5-12: the old bytes are swept only AFTER the commit that
        # dropped the row lands - deleting them ahead of a commit that could
        # still roll back would lose a picture another product still shows.
        if sweep:
            delete_object_best_effort(*sweep)

        image = _serialize_image(self.db, self._combo_or_404(combo.id))
        if image is None:
            # AC-S5-12: the response model is not Optional - a signed URL
            # that could not be produced for the picture we just stored is a
            # storage-layer failure, not "no picture".
            raise AppException(
                status_code=502,
                message="The image was stored but a preview URL could not be produced.",
            )
        return image

    def delete_image(self, combo_id: str) -> None:
        """AC-S5-3/S5-12: clears the pointer and drops the combo's OWN link -
        the attachment row (and its bytes) is swept only when no other
        product's own link still points at it."""
        combo = self._combo_or_404(combo_id)
        attachment_id = combo.image_attachment_id
        combo.image_attachment_id = None
        self.db.flush()
        sweep = None
        if attachment_id:
            sweep = self._unlink_combo_image(combo, attachment_id)
        self.db.commit()
        if sweep:
            delete_object_best_effort(*sweep)

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

    def _unlink_combo_image(
        self, combo: ProductCombo, attachment_id: str
    ) -> Optional[tuple]:
        """AC-S5-12: drop the combo's OWN link to `attachment_id` (its host
        product's `product_attachments` row) and, only when no OTHER
        `product_attachments` row still links it, the attachment row itself.

        A combo image is shared into the host's own gallery (AC-S5-2), and
        nothing stops a caller from separately attaching the same picture
        elsewhere - a replace/clear here must never hard-delete a row
        something else still shows.

        Returns ``(provider, key)`` to sweep from storage once the caller's
        own commit has landed, or ``None`` when nothing was deleted - the
        bytes must survive until the transaction that dropped the row is
        durable, since an undo of that delete cannot undo a storage sweep.
        """
        from app.services.storage_router import extract_key

        self.db.query(ProductAttachment).filter(
            ProductAttachment.product_id == combo.host_product_id,
            ProductAttachment.attachment_id == attachment_id,
        ).delete(synchronize_session=False)
        self.db.flush()

        still_linked = (
            self.db.query(ProductAttachment.id)
            .filter(ProductAttachment.attachment_id == attachment_id)
            .first()
            is not None
        )
        if still_linked:
            return None

        attachment = self.db.query(Attachment).filter(Attachment.id == attachment_id).first()
        if attachment is None:
            return None
        provider = attachment.storage_provider
        key = extract_key(attachment.file_path)
        self.db.delete(attachment)
        self.db.flush()
        return (provider, key) if key else None

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
