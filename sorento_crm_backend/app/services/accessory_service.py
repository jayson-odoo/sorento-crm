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
import re
import uuid
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.accessory import (
    Accessory,
    AccessoryImage,
    ProductAccessory,
    ProductComboAccessory,
)
from app.models.product import Product
from app.models.product_combo import ProductCombo
from app.models.resources import Attachment, AttachmentType
from app.utils.tag_rich_text import sanitise_tag_html
from app.services.error_handler import AppException, handle_not_found
from app.services.storage_router import (
    cdn_base_url,
    default_provider,
    delete_object_best_effort,
    get_backend,
    resolve_signed_url,
)

_UNSET = object()
IMAGE_TYPE_CODE = "accessory_image"
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGES = 12
MAX_SPEC_CHARS = 4000
MAX_REMARK_CHARS = 1000
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
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


def _clean_rich(value: Any, *, limit: int, label: str) -> Optional[str]:
    """Plain text or rich HTML through the tag sanitiser (script, style, on* attributes and links
    stripped); blank = None. Plain text keeps its old one-line collapse."""
    raw = str(value or "")
    if not raw.strip():
        return None
    cleaned = sanitise_tag_html(raw)
    if cleaned is None:
        return None
    if "<" not in cleaned:
        cleaned = " ".join(cleaned.split())
    if len(cleaned) > limit:
        raise AppException(status_code=422, message=f"The {label} is longer than {limit} characters")
    return cleaned or None


def _clean_spec(value: Any) -> Optional[str]:
    return _clean_rich(value, limit=MAX_SPEC_CHARS, label="spec")


def _clean_remark(value: Any) -> Optional[str]:
    return _clean_rich(value, limit=MAX_REMARK_CHARS, label="remark")


def _clean_override_name(value: Any) -> Optional[str]:
    cleaned = " ".join(str(value or "").split())
    if len(cleaned) > 200:
        raise AppException(status_code=422, message="The name is longer than 200 characters")
    return cleaned or None


def _clean_colour(name: Any, hex_value: Any) -> tuple:
    """`(colour_name, colour_hex)`: blank = None, a hex must be `#rrggbb` (stored lower case)."""
    clean_name = " ".join(str(name or "").split()) or None
    if clean_name and len(clean_name) > 40:
        raise AppException(status_code=422, message="The colour name is longer than 40 characters")
    clean_hex = str(hex_value).strip() if hex_value is not None else ""
    if clean_hex and not _HEX_RE.match(clean_hex):
        raise AppException(status_code=422, message="The colour must look like #1f2937")
    return clean_name, (clean_hex.lower() or None)


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


def _picture_rows(db: Session, accessory_id: str) -> List[Dict[str, Any]]:
    """The accessory's pictures in order, each with a fresh signed link (an unsignable one is left
    out rather than shipped as a link that 403s)."""
    rows = (
        db.query(AccessoryImage)
        .filter(AccessoryImage.accessory_id == accessory_id)
        .order_by(AccessoryImage.sort_order, AccessoryImage.created_at, AccessoryImage.id)
        .all()
    )
    out: List[Dict[str, Any]] = []
    for row in rows:
        picture = image_of(db, row.attachment_id)
        if picture is None:
            continue
        out.append(
            {
                "id": row.id,
                **picture,
                "colour_name": row.colour_name,
                "colour_hex": row.colour_hex,
            }
        )
    return out


def _colours_of(pictures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Distinct `{name, hex}` of the pictures that carry a colour, in picture order."""
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for picture in pictures:
        hex_value = picture.get("colour_hex")
        if not hex_value or hex_value.lower() in seen:
            continue
        seen.add(hex_value.lower())
        out.append({"name": picture.get("colour_name"), "hex": hex_value})
    return out


def _tag_images(pictures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {key: picture[key] for key in ("attachment_id", "url", "colour_name", "colour_hex")}
        for picture in pictures
    ]


def _first_non_blank(*values: Optional[str]) -> Optional[str]:
    for value in values:
        if value is not None and str(value).strip():
            return value
    return None


def box_style_for(
    db: Session, *, product_id: Optional[str] = None, combo_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """The saved accessories template a product or a combo names as its own box style, as
    `{id, name, design}`, else None (the tag template's own box). A combo never inherits its host's."""
    from app.models.dealer_kit import AccessoryBoxPreset

    owner = None
    if combo_id:
        owner = db.query(ProductCombo.accessory_box_preset_id).filter(ProductCombo.id == combo_id).first()
    elif product_id:
        owner = db.query(Product.accessory_box_preset_id).filter(Product.id == product_id).first()
    if owner is None or not owner[0]:
        return None
    preset = db.query(AccessoryBoxPreset).filter(AccessoryBoxPreset.id == owner[0]).first()
    return {"id": preset.id, "name": preset.name, "design": preset.design} if preset else None


def tag_accessory(
    db: Session, accessory: Accessory, link=None, pictures: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """One library accessory as a price tag carries it. `link` (a list row) supplies the per-row
    picture choice and the name / spec / remark overrides, each used only when non-blank."""
    if pictures is None:
        pictures = _picture_rows(db, accessory.id)
    if not pictures and accessory.image_attachment_id:
        # A database where `ptag_0017`'s copy step never ran keeps the picture only on the old column:
        # still print it (no colour), so a legacy box and a card's picture element both show it.
        legacy = image_of(db, accessory.image_attachment_id)
        if legacy is not None:
            pictures = [{"id": None, **legacy, "colour_name": None, "colour_hex": None}]
    chosen = None
    if link is not None and link.image_id:
        chosen = next((picture for picture in pictures if picture["id"] == link.image_id), None)
    lead = chosen or (pictures[0] if pictures else None)
    return {
        "kind": "accessory",
        "id": accessory.id,
        "name": _first_non_blank(getattr(link, "name_override", None), accessory.name),
        "spec": _first_non_blank(getattr(link, "spec_override", None), accessory.spec),
        "remark": _first_non_blank(getattr(link, "remark_override", None), accessory.remark),
        "image": {"attachment_id": lead["attachment_id"], "url": lead["url"]} if lead else None,
        "images": _tag_images(pictures),
        "colours": _colours_of(pictures),
        "code": None,
        "list_price": None,
    }


def tag_product_entry(db: Session, product: Product, viewer=None, link=None) -> Dict[str, Any]:
    """A catalogue product listed as a free item (owner, 6 Nov ~10:45): its code, description
    (else name), lead photo and list price, all read live for this viewer. `spec` is the product's
    price tag description unless the list row overrides it."""
    from app.services.dealer_kit.pricing import resolve_prices
    from app.services.dealer_kit.product_images import gallery_images
    from app.services.dealer_kit.tag_data_service import staff_viewer

    viewer = viewer or staff_viewer()
    prices = resolve_prices(db, [product], viewer, None).get(product.id)
    images = gallery_images(db, product, viewer)
    lead = next((image for image in images if image.get("is_primary")), images[0] if images else None)
    picture = {"attachment_id": lead["attachment_id"], "url": lead["url"]} if lead else None
    return {
        "kind": "product",
        "id": product.id,
        "name": _first_non_blank(
            getattr(link, "name_override", None),
            (product.description or "").strip() or product.product_name or product.product_code,
        ),
        "spec": _first_non_blank(getattr(link, "spec_override", None), product.price_tag_description),
        "remark": _first_non_blank(getattr(link, "remark_override", None)),
        "image": picture,
        "images": [{**picture, "colour_name": None, "colour_hex": None}] if picture else [],
        "colours": [],
        "code": product.product_code,
        "list_price": prices.list_price if prices else None,
    }


def _tag_entries(db: Session, links, viewer=None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for link in links:
        if link.item_product_id:
            if link.item_product is not None:
                out.append(tag_product_entry(db, link.item_product, viewer, link))
        elif link.accessory is not None:
            out.append(tag_accessory(db, link.accessory, link))
    return out


def _product_links(db: Session, product_id: str):
    return (
        db.query(ProductAccessory)
        .filter(ProductAccessory.product_id == product_id)
        .order_by(ProductAccessory.sort_order, ProductAccessory.id)
        .all()
    )


def _combo_links(db: Session, combo_id: str):
    return (
        db.query(ProductComboAccessory)
        .filter(ProductComboAccessory.combo_id == combo_id)
        .order_by(ProductComboAccessory.sort_order, ProductComboAccessory.id)
        .all()
    )


def product_tag_accessories(db: Session, product_id: str, viewer=None) -> List[Dict[str, Any]]:
    """The product's own list, in order, as the tag carries it."""
    return _tag_entries(db, _product_links(db, product_id), viewer)


def combo_tag_accessories(db: Session, combo_id: str, viewer=None) -> List[Dict[str, Any]]:
    """The combo's own list, in order. Never the host product's (owner ruling Q1)."""
    return _tag_entries(db, _combo_links(db, combo_id), viewer)


def entry_text(item: Dict[str, Any]) -> str:
    """`DRAINER`, or `SRTW5000 Popup Waste 80mm` for a product entry."""
    if item.get("kind") == "product":
        return " ".join(part for part in (item.get("code"), item.get("name")) if part)
    return item.get("name") or ""


def names_text(accessories: Iterable[Dict[str, Any]]) -> str:
    """`DRAINER, PULL OUT DRAINER`: what the old free-text slots now print, built from the list."""
    return ", ".join(text for text in (entry_text(item) for item in accessories) if text)


class AccessoryService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ library

    def serialize(self, accessory: Accessory, counts: Optional[Dict[str, tuple]] = None, link=None) -> Dict[str, Any]:
        """The library row as the master data screen reads it (its OWN text; a list row's overrides
        ride in `entry`, never merged in)."""
        if counts is None:
            counts = self._counts([accessory.id])
        product_count, combo_count = counts.get(accessory.id, (0, 0))
        pictures = _picture_rows(self.db, accessory.id)
        out = {
            **tag_accessory(self.db, accessory, None, pictures),
            "images": pictures,
            "product_count": product_count,
            "combo_count": combo_count,
        }
        if link is not None:
            out["entry"] = self._entry_of(link)
        return out

    @staticmethod
    def _entry_of(link) -> Dict[str, Any]:
        return {
            "image_id": link.image_id,
            "name": link.name_override,
            "spec": link.spec_override,
            "remark": link.remark_override,
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
        row = Accessory(
            name=name,
            spec=_clean_spec(payload.get("spec")),
            remark=_clean_remark(payload.get("remark")),
            created_by=created_by,
        )
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
        if "remark" in payload:
            row.remark = _clean_remark(payload["remark"])
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
        attachment_ids = [
            value
            for (value,) in self.db.query(AccessoryImage.attachment_id)
            .filter(AccessoryImage.accessory_id == row.id)
            .all()
        ]
        if row.image_attachment_id and row.image_attachment_id not in attachment_ids:
            attachment_ids.append(row.image_attachment_id)
        self.db.delete(row)
        self.db.flush()
        sweeps = [self._drop_attachment(value) for value in attachment_ids]
        self.db.commit()
        for sweep in sweeps:
            if sweep:
                delete_object_best_effort(*sweep)

    # ------------------------------------------------------------------ pictures

    def _store(
        self, row: Accessory, *, content: bytes, filename: str, user_id: Optional[str]
    ) -> tuple:
        """Validate, upload and record the attachment. Returns `(attachment_id, provider, key)`; the
        caller attaches it to a picture row and commits (and removes the object if that fails)."""
        if not content:
            raise AppException(status_code=422, message="The uploaded file is empty.")
        if len(content) > MAX_IMAGE_BYTES:
            raise AppException(status_code=422, message="Images must be under 10 MB.")
        ext = _validated_image_ext(filename or "")
        mime = _IMAGE_MIME_BY_EXT[ext]

        attachment_id = str(uuid.uuid4())
        safe_name = (filename or "accessory").rsplit("/", 1)[-1][:255]
        # The client's filename never reaches the storage key (security review L1: `%2F`, `?`, `#`
        # survive into a key that `extract_key` later decodes); it is kept as the display name only.
        key = f"{STORAGE_PREFIX}/{attachment_id}.{ext}"
        provider = default_provider()
        stored_key, _url = get_backend(provider).upload_file(
            file_content=content, file_path=key, content_type=mime
        )
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
        except Exception:
            delete_object_best_effort(provider, stored_key)
            raise
        return attachment_id, provider, stored_key

    def _images(self, accessory_id: str) -> List[AccessoryImage]:
        return (
            self.db.query(AccessoryImage)
            .filter(AccessoryImage.accessory_id == accessory_id)
            .order_by(AccessoryImage.sort_order, AccessoryImage.created_at, AccessoryImage.id)
            .all()
        )

    def _image_out(self, image: AccessoryImage) -> Dict[str, Any]:
        picture = image_of(self.db, image.attachment_id)
        if picture is None:
            raise AppException(
                status_code=502, message="The image was stored but a preview URL could not be produced."
            )
        return {"id": image.id, **picture, "colour_name": image.colour_name, "colour_hex": image.colour_hex}

    def _image_or_404(self, accessory_id: str, image_id: str) -> AccessoryImage:
        image = (
            self.db.query(AccessoryImage)
            .filter(AccessoryImage.id == image_id, AccessoryImage.accessory_id == accessory_id)
            .first()
        )
        if image is None:
            raise handle_not_found("Image", image_id)
        return image

    def add_image(
        self,
        accessory_id: str,
        *,
        content: bytes,
        filename: str,
        user_id: Optional[str],
        colour_name: Optional[str] = None,
        colour_hex: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Append a picture (last in order), with an optional colour."""
        row = self._or_404(accessory_id)
        name, hex_value = _clean_colour(colour_name, colour_hex)
        # Serialise concurrent adds so the cap below cannot be passed by two requests at once.
        self.db.query(Accessory.id).filter(Accessory.id == row.id).with_for_update().first()
        existing = self._images(row.id)
        if len(existing) >= MAX_IMAGES:
            raise AppException(
                status_code=422, message=f"An accessory holds at most {MAX_IMAGES} pictures."
            )
        attachment_id, provider, stored_key = self._store(
            row, content=content, filename=filename, user_id=user_id
        )
        try:
            image = AccessoryImage(
                accessory_id=row.id,
                attachment_id=attachment_id,
                colour_name=name,
                colour_hex=hex_value,
                sort_order=(max(item.sort_order for item in existing) + 1) if existing else 0,
            )
            self.db.add(image)
            self.db.commit()
        except Exception:
            self.db.rollback()
            delete_object_best_effort(provider, stored_key)
            raise
        return self._image_out(image)

    def patch_image(self, accessory_id: str, image_id: str, changes: Dict[str, Any]) -> Dict[str, Any]:
        self._or_404(accessory_id)
        image = self._image_or_404(accessory_id, image_id)
        name, hex_value = _clean_colour(
            changes.get("colour_name", image.colour_name), changes.get("colour_hex", image.colour_hex)
        )
        if "colour_name" in changes:
            image.colour_name = name
        if "colour_hex" in changes:
            image.colour_hex = hex_value
        self.db.commit()
        return self._image_out(image)

    def delete_picture(self, accessory_id: str, image_id: str) -> None:
        """Remove one picture; list rows that chose it fall back to the first (FK SET NULL)."""
        self._or_404(accessory_id)
        image = self._image_or_404(accessory_id, image_id)
        attachment_id = image.attachment_id
        self.db.delete(image)
        self.db.flush()
        sweep = self._drop_attachment(attachment_id)
        self.db.commit()
        if sweep:
            delete_object_best_effort(*sweep)

    def picture_in_scope(self, image_id: str) -> Optional[AccessoryImage]:
        """The picture when its accessory is visible to the caller's company scope, else None."""
        return (
            self.db.query(AccessoryImage)
            .join(Accessory, Accessory.id == AccessoryImage.accessory_id)
            .filter(AccessoryImage.id == image_id)
            .first()
        )

    def delete_picture_by_id(self, image_id: str) -> None:
        """The deferred `accessory_image.delete`: the same removal as the route, found by picture id."""
        image = self.picture_in_scope(image_id)
        if image is None:
            raise handle_not_found("Image", image_id)
        self.delete_picture(image.accessory_id, image.id)

    def order_images(self, accessory_id: str, ids: List[str]) -> List[Dict[str, Any]]:
        self._or_404(accessory_id)
        images = {image.id: image for image in self._images(accessory_id)}
        if len(set(ids)) != len(ids) or set(ids) != set(images):
            raise AppException(status_code=422, message="The order must name every picture exactly once.")
        for index, image_id in enumerate(ids):
            images[image_id].sort_order = index
        self.db.commit()
        return [self._image_out(images[image_id]) for image_id in ids]

    # Old single-picture routes: image 1 (kept so an open old tab does not 404).

    def upload_image(
        self,
        accessory_id: str,
        *,
        content: bytes,
        filename: str,
        content_type: Optional[str],
        user_id: Optional[str],
    ) -> Dict[str, str]:
        """Replace picture 1, or create it."""
        row = self._or_404(accessory_id)
        attachment_id, provider, stored_key = self._store(
            row, content=content, filename=filename, user_id=user_id
        )
        sweep = None
        try:
            existing = self._images(row.id)
            if existing:
                first = existing[0]
                previous = first.attachment_id
                first.attachment_id = attachment_id
                self.db.flush()
                if previous != attachment_id:
                    sweep = self._drop_attachment(previous)
            else:
                self.db.add(AccessoryImage(accessory_id=row.id, attachment_id=attachment_id, sort_order=0))
            # The old column is no longer read, but the old route still keeps it in step (a seed
            # script and an old tab look at it).
            row.image_attachment_id = attachment_id
            self.db.commit()
        except Exception:
            self.db.rollback()
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
        """Remove picture 1 (the old route)."""
        row = self._or_404(accessory_id)
        existing = self._images(row.id)
        if not existing:
            return
        self.delete_picture(row.id, existing[0].id)

    # ------------------------------------------------------------------ lists

    def product_list(self, product_id: str) -> List[Dict[str, Any]]:
        self._product_or_404(product_id)
        return self._serialize_links(_product_links(self.db, product_id))

    def set_product_list(
        self, product_id: str, items: List[Dict[str, Any]], box_style: Any = _UNSET
    ) -> List[Dict[str, Any]]:
        product = self._product_or_404(product_id)
        style_id = self._resolve_box_style(box_style)
        resolved = self._resolve_items(items, product.company_id, refused={product.id: "A product cannot list itself"})
        self.db.query(ProductAccessory).filter(ProductAccessory.product_id == product_id).delete(
            synchronize_session=False
        )
        self.db.flush()
        for index, (kind, row, overrides) in enumerate(resolved):
            self.db.add(
                ProductAccessory(
                    product_id=product_id,
                    accessory_id=row.id if kind == "accessory" else None,
                    item_product_id=row.id if kind == "product" else None,
                    sort_order=index,
                    **overrides,
                )
            )
        if style_id is not _UNSET:
            product.accessory_box_preset_id = style_id
        self.db.commit()
        return self.product_list(product_id)

    def combo_list(self, combo_id: str) -> List[Dict[str, Any]]:
        self._combo_or_404(combo_id)
        return self.combo_list_rows(combo_id)

    def combo_list_rows(self, combo_id: str) -> List[Dict[str, Any]]:
        """The combo's list with no scope check: for a caller that already resolved the combo."""
        return self._serialize_links(_combo_links(self.db, combo_id))

    def set_combo_list(
        self, combo_id: str, items: List[Dict[str, Any]], box_style: Any = _UNSET
    ) -> List[Dict[str, Any]]:
        combo = self._combo_or_404(combo_id)
        style_id = self._resolve_box_style(box_style)
        host = self._product_or_404(combo.host_product_id)
        # One list of free products, never two: a product already IN the combo (a part) is not
        # also its free item, and the host is the combo itself.
        refused = {host.id: "The combo's own product cannot be its free item"}
        for part in combo.parts or []:
            refused.setdefault(part.part_product_id, "This product is already a part of this combo")
        resolved = self._resolve_items(items, host.company_id, refused=refused)
        self.db.query(ProductComboAccessory).filter(ProductComboAccessory.combo_id == combo_id).delete(
            synchronize_session=False
        )
        self.db.flush()
        for index, (kind, row, overrides) in enumerate(resolved):
            self.db.add(
                ProductComboAccessory(
                    combo_id=combo_id,
                    accessory_id=row.id if kind == "accessory" else None,
                    item_product_id=row.id if kind == "product" else None,
                    sort_order=index,
                    **overrides,
                )
            )
        if style_id is not _UNSET:
            combo.accessory_box_preset_id = style_id
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

    def _resolve_box_style(self, box_style: Any) -> Any:
        """`_UNSET` (leave alone), None (clear) or the id of a saved template visible to the caller."""
        from app.models.dealer_kit import AccessoryBoxPreset

        if box_style is _UNSET or box_style is None:
            return box_style
        row = self.db.query(AccessoryBoxPreset.id).filter(AccessoryBoxPreset.id == str(box_style)).first()
        if row is None:
            raise handle_not_found("Accessories template", str(box_style))
        return row[0]

    def box_style_id_of(self, *, product_id: Optional[str] = None, combo_id: Optional[str] = None) -> Optional[str]:
        if combo_id:
            row = self.db.query(ProductCombo.accessory_box_preset_id).filter(ProductCombo.id == combo_id).first()
        else:
            row = self.db.query(Product.accessory_box_preset_id).filter(Product.id == product_id).first()
        return row[0] if row else None

    def _serialize_links(self, links) -> List[Dict[str, Any]]:
        accessories = [link.accessory for link in links if not link.item_product_id and link.accessory]
        counts = self._counts([item.id for item in accessories])
        out: List[Dict[str, Any]] = []
        for link in links:
            if link.item_product_id:
                if link.item_product is not None:
                    out.append(
                        {
                            **tag_product_entry(self.db, link.item_product),
                            "product_count": 0,
                            "combo_count": 0,
                            "entry": self._entry_of(link),
                        }
                    )
            elif link.accessory is not None:
                out.append(self.serialize(link.accessory, counts, link))
        return out

    def _resolve_items(
        self, items: List[Dict[str, Any]], company_id: Optional[str], *, refused: Dict[str, str]
    ) -> List[tuple]:
        """`[("accessory", Accessory) | ("product", Product), overrides]` in order, each named once,
        each of the list owner's company (another company's id reads exactly like a missing one).
        `overrides` are the row's columns: a picture of THAT accessory, and cleaned text."""
        wanted: List[tuple] = []
        for item in items or []:
            accessory_id, product_id = item.get("accessory_id"), item.get("product_id")
            if bool(accessory_id) == bool(product_id):
                raise AppException(status_code=422, message="Each entry names one accessory or one product")
            wanted.append(("accessory", str(accessory_id)) if accessory_id else ("product", str(product_id)))
        if len(set(wanted)) != len(wanted):
            raise AppException(status_code=422, message="An entry can be listed only once")

        accessory_ids = [value for kind, value in wanted if kind == "accessory"]
        product_ids = [value for kind, value in wanted if kind == "product"]
        accessories = (
            {row.id: row for row in self.db.query(Accessory).filter(Accessory.id.in_(accessory_ids)).all()}
            if accessory_ids
            else {}
        )
        products = (
            {row.id: row for row in self.db.query(Product).filter(Product.id.in_(product_ids)).all()}
            if product_ids
            else {}
        )
        out: List[tuple] = []
        for (kind, value), item in zip(wanted, items or []):
            row = (accessories if kind == "accessory" else products).get(value)
            if row is None or (company_id is not None and row.company_id not in (None, company_id)):
                raise handle_not_found("Accessory" if kind == "accessory" else "Product", value)
            if kind == "product" and value in refused:
                raise AppException(status_code=422, message=refused[value])
            out.append((kind, row, self._overrides(kind, row, item)))
        return out

    def _overrides(self, kind: str, row, item: Dict[str, Any]) -> Dict[str, Any]:
        image_id = str(item.get("image_id") or "").strip() or None
        if image_id is not None:
            if kind == "product":
                raise AppException(status_code=422, message="A product entry has no picture to choose")
            try:
                uuid.UUID(image_id)
            except ValueError:
                raise AppException(status_code=422, message="That picture does not belong to this accessory")
            owned = (
                self.db.query(AccessoryImage.id)
                .filter(AccessoryImage.id == image_id, AccessoryImage.accessory_id == row.id)
                .first()
            )
            if owned is None:
                raise AppException(status_code=422, message="That picture does not belong to this accessory")
        return {
            "image_id": image_id,
            "name_override": _clean_override_name(item.get("name")),
            "spec_override": _clean_spec(item.get("spec")),
            "remark_override": _clean_remark(item.get("remark")),
        }

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
