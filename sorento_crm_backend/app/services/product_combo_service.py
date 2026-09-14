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
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session, joinedload

from app.models.product import Product
from app.models.product_combo import ProductCombo, ProductComboPart
from app.services.error_handler import AppException, handle_not_found


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


def _serialize(combo: ProductCombo) -> Dict[str, Any]:
    return {
        "id": combo.id,
        "host_product_id": combo.host_product_id,
        "name": combo.name,
        "sort_order": combo.sort_order,
        "parts": [_serialize_part(part) for part in combo.parts],
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
        return [_serialize(combo) for combo in rows]

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

        taken = (
            self.db.query(ProductCombo)
            .filter(
                ProductCombo.host_product_id == host_product_id,
                ProductCombo.name.ilike(cleaned),
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
        return _serialize(self._combo_or_404(combo.id))

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
                    ProductCombo.name.ilike(cleaned),
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
        return _serialize(self._combo_or_404(combo.id))

    def delete(self, combo_id: str) -> None:
        """Hard delete, per the CRUD standard. The parts cascade with it; the
        products do not, and a request line pointing at it has its `combo_id`
        cleared by the FK's own SET NULL rather than being deleted (AC-S1-5)."""
        combo = self._combo_or_404(combo_id)
        self.db.delete(combo)
        self.db.commit()

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
