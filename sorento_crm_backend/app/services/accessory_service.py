"""Accessories library + the product and combo lists (PRICETAG-ACCESSORIES).

Routes: `app/api/v1/master_data/accessories.py`. Plan:
documentation/plans/dealer-kit/PLAN-pricetag-accessories-06nov.md.

- The library is company scoped (`Accessory` carries the mixin), so a read under the caller's
  scope never sees another company's row. A list may only name accessories of the product's own
  company.
- Lists are replaced whole (`PUT` with the ordered ids): the screen drags and removes, then saves
  the order it shows. Product and combo lists are independent (owner ruling Q1).
- A picture is an `attachments` row of type `accessory_image`, the same pipeline the combo cover
  uses (`product_combo_service.upload_image`), stored with `entity_type = 'general'`.
"""
from __future__ import annotations

import hashlib
import uuid
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.accessory import Accessory, ProductAccessory, ProductComboAccessory
from app.models.product import Product
from app.models.product_combo import ProductCombo
from app.models.resources import Attachment, AttachmentType
from app.services.error_handler import AppException, handle_not_found
from app.services.storage_router import (
    cdn_base_url,
    default_provider,
    delete_object_best_effort,
    get_backend,
    resolve_signed_url,
)

IMAGE_TYPE_CODE = "accessory_image"
MAX_IMAGE_BYTES = 10 * 1024 * 1024
STORAGE_PREFIX = "accessory_image"
_IMAGE_MIME_BY_EXT = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def _validated_image_ext(filename: str) -> str:
    """The extension decides, never the client's Content-Type (as the combo picture)."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _IMAGE_MIME_BY_EXT:
        raise AppException(status_code=422, message=f"{filename} is not an image (jpg, jpeg, png or webp).")
    return ext


def _clean_name(value: Any) -> str:
    cleaned = " ".join(str(value or "").split())
    if not cleaned:
        raise AppException(status_code=422, message="An accessory needs a name")
    if len(cleaned) > 100:
        raise AppException(status_code=422, message="The name is longer than 100 characters")
    return cleaned


def _clean_spec(value: Any) -> Optional[str]:
    cleaned = " ".join(str(value or "").split())
    if len(cleaned) > 200:
        raise AppException(status_code=422, message="The spec is longer than 200 characters")
    return cleaned or None


def image_of(db: Session, attachment_id: Optional[str]) -> Optional[Dict[str, str]]:
    """`{attachment_id, url}` with a strict signed URL, or None (no picture, or one that cannot be
    signed: absent rather than a link that 403s)."""
    if not attachment_id:
        return None
    attachment = (
        db.query(Attachment)
        .filter(Attachment.id == attachment_id, Attachment.is_deleted.is_(False))
        .first()
    )
    if attachment is None:
        return None
    url = resolve_signed_url(attachment.file_path, provider=attachment.storage_provider, strict=True)
    if not url:
        return None
    return {"attachment_id": attachment.id, "url": url}


def tag_accessory(db: Session, accessory: Accessory) -> Dict[str, Any]:
    """One accessory as a price tag carries it."""
    return {
        "id": accessory.id,
        "name": accessory.name,
        "spec": accessory.spec,
        "image": image_of(db, accessory.image_attachment_id),
    }


def product_tag_accessories(db: Session, product_id: str) -> List[Dict[str, Any]]:
    """The product's own list, in order, as the tag carries it."""
    rows = (
        db.query(ProductAccessory)
        .filter(ProductAccessory.product_id == product_id)
        .order_by(ProductAccessory.sort_order, ProductAccessory.id)
        .all()
    )
    return [tag_accessory(db, row.accessory) for row in rows if row.accessory is not None]


def combo_tag_accessories(db: Session, combo_id: str) -> List[Dict[str, Any]]:
    """The combo's own list, in order. Never the host product's (owner ruling Q1)."""
    rows = (
        db.query(ProductComboAccessory)
        .filter(ProductComboAccessory.combo_id == combo_id)
        .order_by(ProductComboAccessory.sort_order, ProductComboAccessory.id)
        .all()
    )
    return [tag_accessory(db, row.accessory) for row in rows if row.accessory is not None]


def names_text(accessories: Iterable[Dict[str, Any]]) -> str:
    """`DRAINER, PULL OUT DRAINER`: what the old free-text slots now print, built from the list."""
    return ", ".join(item["name"] for item in accessories if item.get("name"))


class AccessoryService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ library

    def serialize(self, accessory: Accessory, counts: Optional[Dict[str, tuple]] = None) -> Dict[str, Any]:
        if counts is None:
            counts = self._counts([accessory.id])
        product_count, combo_count = counts.get(accessory.id, (0, 0))
        return {
            **tag_accessory(self.db, accessory),
            "product_count": product_count,
            "combo_count": combo_count,
        }

    def list(self, *, page: int = 1, limit: int = 50, query: Optional[str] = None) -> Dict[str, Any]:
        statement = self.db.query(Accessory)
        if query and query.strip():
            needle = f"%{query.strip()}%"
            statement = statement.filter(Accessory.name.ilike(needle) | Accessory.spec.ilike(needle))
        total = statement.count()
        rows = (
            statement.order_by(func.lower(Accessory.name), Accessory.id)
            .offset((max(page, 1) - 1) * limit)
            .limit(limit)
            .all()
        )
        counts = self._counts([row.id for row in rows])
        return {
            "data": [self.serialize(row, counts) for row in rows],
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0,
        }

    def get(self, accessory_id: str) -> Dict[str, Any]:
        return self.serialize(self._or_404(accessory_id))

    def create(self, payload: Dict[str, Any], *, created_by: Optional[str]) -> Dict[str, Any]:
        name = _clean_name(payload.get("name"))
        self._refuse_taken(name)
        row = Accessory(name=name, spec=_clean_spec(payload.get("spec")), created_by=created_by)
        self.db.add(row)
        self.db.commit()
        return self.serialize(self._or_404(row.id))

    def update(self, accessory_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        row = self._or_404(accessory_id)
        if "name" in payload and payload["name"] is not None:
            name = _clean_name(payload["name"])
            self._refuse_taken(name, except_id=row.id, company_id=row.company_id)
            row.name = name
        if "spec" in payload:
            row.spec = _clean_spec(payload["spec"])
        self.db.commit()
        return self.serialize(self._or_404(row.id))

    def delete(self, accessory_id: str) -> None:
        """Hard delete. Refused while any product or combo lists it, naming the count."""
        row = self._or_404(accessory_id)
        product_count, combo_count = self._counts([row.id]).get(row.id, (0, 0))
        if product_count or combo_count:
            raise AppException(
                status_code=409,
                message=(
                    f"Used on {product_count} product{'s' if product_count != 1 else ''} and "
                    f"{combo_count} combo{'s' if combo_count != 1 else ''}: remove it there first."
                ),
                code="ACCESSORY_IN_USE",
            )
        attachment_id = row.image_attachment_id
        self.db.delete(row)
        self.db.flush()
        sweep = self._drop_attachment(attachment_id) if attachment_id else None
        self.db.commit()
        if sweep:
            delete_object_best_effort(*sweep)

    # ------------------------------------------------------------------ picture

    def upload_image(
        self,
        accessory_id: str,
        *,
        content: bytes,
        filename: str,
        content_type: Optional[str],
        user_id: Optional[str],
    ) -> Dict[str, str]:
        row = self._or_404(accessory_id)
        if not content:
            raise AppException(status_code=422, message="The uploaded file is empty.")
        if len(content) > MAX_IMAGE_BYTES:
            raise AppException(status_code=422, message="Images must be under 10 MB.")
        ext = _validated_image_ext(filename or "")
        mime = _IMAGE_MIME_BY_EXT[ext]

        attachment_id = str(uuid.uuid4())
        safe_name = (filename or "accessory").rsplit("/", 1)[-1][:255]
        key = f"{STORAGE_PREFIX}/{attachment_id}/{safe_name}"
        provider = default_provider()
        stored_key, _url = get_backend(provider).upload_file(
            file_content=content, file_path=key, content_type=mime
        )
        sweep = None
        try:
            self.db.add(
                Attachment(
                    id=attachment_id,
                    attachment_type_id=self._image_type().id,
                    original_filename=safe_name,
                    stored_filename=safe_name,
                    file_path=cdn_base_url(provider, stored_key),
                    file_size_bytes=len(content),
                    mime_type=mime,
                    file_hash=hashlib.sha256(content).hexdigest(),
                    entity_type="general",
                    uploaded_by=user_id,
                    uploader_kind="user" if user_id else "system",
                    storage_provider=provider,
                    company_id=row.company_id,
                )
            )
            self.db.flush()
            previous = row.image_attachment_id
            row.image_attachment_id = attachment_id
            self.db.flush()
            if previous and previous != attachment_id:
                sweep = self._drop_attachment(previous)
            self.db.commit()
        except Exception:
            delete_object_best_effort(provider, stored_key)
            raise
        if sweep:
            delete_object_best_effort(*sweep)

        image = image_of(self.db, attachment_id)
        if image is None:
            raise AppException(
                status_code=502, message="The image was stored but a preview URL could not be produced."
            )
        return image

    def delete_image(self, accessory_id: str) -> None:
        row = self._or_404(accessory_id)
        attachment_id = row.image_attachment_id
        row.image_attachment_id = None
        self.db.flush()
        sweep = self._drop_attachment(attachment_id) if attachment_id else None
        self.db.commit()
        if sweep:
            delete_object_best_effort(*sweep)

    # ------------------------------------------------------------------ lists

    def product_list(self, product_id: str) -> List[Dict[str, Any]]:
        self._product_or_404(product_id)
        rows = (
            self.db.query(ProductAccessory)
            .filter(ProductAccessory.product_id == product_id)
            .order_by(ProductAccessory.sort_order, ProductAccessory.id)
            .all()
        )
        return self._serialize_links(rows)

    def set_product_list(self, product_id: str, accessory_ids: List[str]) -> List[Dict[str, Any]]:
        product = self._product_or_404(product_id)
        accessories = self._resolve_ids(accessory_ids, product.company_id)
        self.db.query(ProductAccessory).filter(ProductAccessory.product_id == product_id).delete(
            synchronize_session=False
        )
        self.db.flush()
        for index, item in enumerate(accessories):
            self.db.add(ProductAccessory(product_id=product_id, accessory_id=item.id, sort_order=index))
        self.db.commit()
        return self.product_list(product_id)

    def combo_list(self, combo_id: str) -> List[Dict[str, Any]]:
        self._combo_or_404(combo_id)
        return self.combo_list_rows(combo_id)

    def combo_list_rows(self, combo_id: str) -> List[Dict[str, Any]]:
        """The combo's list with no scope check: for a caller that already resolved the combo."""
        rows = (
            self.db.query(ProductComboAccessory)
            .filter(ProductComboAccessory.combo_id == combo_id)
            .order_by(ProductComboAccessory.sort_order, ProductComboAccessory.id)
            .all()
        )
        return self._serialize_links(rows)

    def set_combo_list(self, combo_id: str, accessory_ids: List[str]) -> List[Dict[str, Any]]:
        combo = self._combo_or_404(combo_id)
        host = self._product_or_404(combo.host_product_id)
        accessories = self._resolve_ids(accessory_ids, host.company_id)
        self.db.query(ProductComboAccessory).filter(ProductComboAccessory.combo_id == combo_id).delete(
            synchronize_session=False
        )
        self.db.flush()
        for index, item in enumerate(accessories):
            self.db.add(ProductComboAccessory(combo_id=combo_id, accessory_id=item.id, sort_order=index))
        self.db.commit()
        return self.combo_list(combo_id)

    def find_or_create(self, name: str, company_id: Optional[str]) -> Accessory:
        """The library row named `name` (ignoring case) in `company_id`, created when missing.
        Used by the combo importer, which reads free items off the flyer by name."""
        cleaned = _clean_name(name)
        statement = self.db.query(Accessory).filter(func.lower(Accessory.name) == cleaned.lower())
        if company_id is not None:
            statement = statement.filter(Accessory.company_id == company_id)
        row = statement.first()
        if row is None:
            row = Accessory(name=cleaned, company_id=company_id)
            self.db.add(row)
            self.db.flush()
        return row

    # ------------------------------------------------------------------ helpers

    def _serialize_links(self, links) -> List[Dict[str, Any]]:
        items = [link.accessory for link in links if link.accessory is not None]
        counts = self._counts([item.id for item in items])
        return [self.serialize(item, counts) for item in items]

    def _resolve_ids(self, accessory_ids: List[str], company_id: Optional[str]) -> List[Accessory]:
        ids = [str(value) for value in accessory_ids or []]
        if len(set(ids)) != len(ids):
            raise AppException(status_code=422, message="An accessory can be listed only once")
        if not ids:
            return []
        found = {row.id: row for row in self.db.query(Accessory).filter(Accessory.id.in_(ids)).all()}
        out: List[Accessory] = []
        for value in ids:
            row = found.get(value)
            # Another company's accessory reads exactly like a missing one.
            if row is None or (company_id is not None and row.company_id not in (None, company_id)):
                raise handle_not_found("Accessory", value)
            out.append(row)
        return out

    def _counts(self, ids: List[str]) -> Dict[str, tuple]:
        if not ids:
            return {}
        products = dict(
            self.db.query(ProductAccessory.accessory_id, func.count(ProductAccessory.id))
            .filter(ProductAccessory.accessory_id.in_(ids))
            .group_by(ProductAccessory.accessory_id)
            .all()
        )
        combos = dict(
            self.db.query(ProductComboAccessory.accessory_id, func.count(ProductComboAccessory.id))
            .filter(ProductComboAccessory.accessory_id.in_(ids))
            .group_by(ProductComboAccessory.accessory_id)
            .all()
        )
        return {value: (products.get(value, 0), combos.get(value, 0)) for value in ids}

    def _refuse_taken(self, name: str, *, except_id: Optional[str] = None, company_id: Optional[str] = None):
        # `lower() = lower()`, never ilike: `%` and `_` in a name are LIKE wildcards.
        statement = self.db.query(Accessory.id).filter(func.lower(Accessory.name) == name.lower())
        if except_id:
            statement = statement.filter(Accessory.id != except_id)
        if company_id:
            statement = statement.filter(Accessory.company_id == company_id)
        if statement.first() is not None:
            raise AppException(
                status_code=409,
                message=f'An accessory called "{name}" already exists',
                code="ACCESSORY_NAME_TAKEN",
            )

    def _or_404(self, accessory_id: str) -> Accessory:
        row = self.db.query(Accessory).filter(Accessory.id == accessory_id).first()
        if row is None:
            raise handle_not_found("Accessory", accessory_id)
        return row

    def _product_or_404(self, product_id: str) -> Product:
        row = self.db.query(Product).filter(Product.id == product_id).first()
        if row is None:
            raise handle_not_found("Product", product_id)
        return row

    def _combo_or_404(self, combo_id: str) -> ProductCombo:
        combo = self.db.query(ProductCombo).filter(ProductCombo.id == combo_id).first()
        if combo is None:
            raise handle_not_found("Combo", combo_id)
        # Scoped through the host, as the combo routes are.
        self._product_or_404(combo.host_product_id)
        return combo

    def _image_type(self) -> AttachmentType:
        """Seeded by the migration; get-or-create here too because a test's blank schema never ran
        the migration's data step (same shape as the combo picture type)."""
        row = self.db.query(AttachmentType).filter(AttachmentType.code == IMAGE_TYPE_CODE).first()
        if row is None:
            row = AttachmentType(
                id=str(uuid.uuid4()),
                code=IMAGE_TYPE_CODE,
                type_name="Accessory Image",
                allowed_extensions="jpg,jpeg,png,webp",
                max_file_size_mb=MAX_IMAGE_BYTES // (1024 * 1024),
            )
            self.db.add(row)
            self.db.flush()
        return row

    def _drop_attachment(self, attachment_id: str) -> Optional[tuple]:
        """Delete the picture's row; return `(provider, key)` to sweep once the commit lands."""
        from app.services.storage_router import extract_key

        attachment = self.db.query(Attachment).filter(Attachment.id == attachment_id).first()
        if attachment is None:
            return None
        provider = attachment.storage_provider
        key = extract_key(attachment.file_path)
        self.db.delete(attachment)
        self.db.flush()
        return (provider, key) if key else None
