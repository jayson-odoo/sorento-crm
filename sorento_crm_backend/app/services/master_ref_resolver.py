"""The ref/code/name/back-create resolution ladder shared by every AutoCount
ingest surface (D1/D2/D10, S1 originally, extracted in S3).

`DocumentIngestService` (sales_orders/purchase_orders) and
`ShippingOrderIngestService` (shipping_orders) both resolve the same five
masters - customer, supplier, sales agent, product, warehouse - by the same
ladder: ref, then code, then (supplier only) name, then back-create. Lifted
out to a base class rather than duplicated, so a shipping order and a
document can never resolve the same code two different ways. A base class
rather than free functions because every step reads `self.db` /
`self.company_id` / `self.integration_id` / `self.refs`, set up once by
`__init__` - a caller composes those four things once and every rung uses
them, exactly as `DocumentIngestService` already did before this extraction.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.inventory import Warehouse
from app.models.order import Customer
from app.models.procurement import Supplier
from app.models.product import Product
from app.models.sales_agent import SalesAgent
from app.services.integration_reference_service import (
    IntegrationReferenceService,
    ReferenceConflict,
)
from app.services.master_ingest_service import MissingReference, _is_company_scoped
from app.services.scm import customer_back_create, sales_agent_service
from app.services.scm.outstanding_import_service import _clean_supplier_name
from app.services.scm.supplier_back_create import back_create_supplier, supplier_slug

# Fixed verdict-warning vocabulary (D9). Module constants rather than literals
# at each call site, for the same reason the status maps are: this IS the
# cross-repo contract, and the ESB's log renders these strings verbatim.
WARN_CUSTOMER_CREATED = "customer_created"
WARN_CUSTOMER_UNRESOLVED = "customer_unresolved"
WARN_SUPPLIER_CREATED = "supplier_created"
WARN_AGENT_CREATED = "agent_created"
WARN_WAREHOUSE_UNRESOLVED = "warehouse_unresolved"
#: D4/S2 - a sales order `classify_document` could not classify, and nothing
#: was stored before this push either. Declared here (not `demand_class`-
#: specific) alongside its siblings, even though only `DocumentIngestService`
#: emits it today.
WARN_UNCLASSIFIED_DEMAND = "unclassified_demand"

# The exact-match code column per master the ref/code ladder resolves through.
# `sales_agents` is absent on purpose: it is shared (no company scope) and
# matched through `sales_agent_service`, which owns its own normalisation.
_CODE_COLUMNS: dict[type, Any] = {
    Customer: Customer.customer_code,
    Supplier: Supplier.supplier_code,
    Product: Product.product_code,
    Warehouse: Warehouse.warehouse_code,
}


class MasterRefResolver:
    """Base class providing the ref/code/name/back-create ladder.

    `db`, `integration_id`, `company_id` and `refs` are the only state every
    rung needs; a subclass's own `__init__` calls `super().__init__(...)` and
    adds whatever else it needs (a dry-run flag, for instance).
    """

    def __init__(self, db: Session, integration_id: Optional[str], *, company_id: str):
        self.db = db
        self.integration_id = integration_id
        self.company_id = company_id
        self.refs = IntegrationReferenceService(db)

    def _resolve_ref(
        self, field: str, source_ref: Optional[str], model: type
    ) -> Optional[str]:
        """The local id an integration reference names, inside the anchor company.

        Absent is not the same as unknown. An optional ref nobody sent leaves the
        FK NULL - an order whose debtor Sorento does not hold is still an order.
        A ref that WAS sent and does not resolve is a sequencing artefact: the
        master push has not drained yet, so the whole document is retryable
        rather than written with the attribution silently dropped.
        """
        if source_ref is None or source_ref == "":
            return None
        entity_id = self.refs.resolve(
            entity_type=model.__tablename__, source_ref=source_ref
        )
        if entity_id is None:
            raise MissingReference(field, source_ref)
        self._require_same_company(
            model, entity_id, f"{field} {source_ref!r}", field_name=field
        )
        return entity_id

    def _require_same_company(
        self, model: type, entity_id: str, subject: str, *, field_name: str = "source_ref"
    ) -> None:
        """Refuse a reference that resolves into another company.

        `integration_references` is global, so a ref finds its row whatever
        company the request anchored to. Binding this document to it - or
        updating it - would be a cross-company write wearing the clothes of an
        ordinary re-sync. Shared masters (`sales_agents`) carry no company at all
        and are visible from either anchor, so they are exempt.

        `field_name` (AC-V1-8) is the verdict-error key the conflict is filed
        under: the document's own `source_ref` for the header's own adoption
        check (the default, unchanged), or the specific master field (e.g.
        `"customer_ref"`) when this guards a v2 ladder resolution - so the ESB
        sees WHICH reference conflicted, not just that the record failed.
        """
        if not _is_company_scoped(model.__tablename__):
            return
        mine = (
            self.db.query(model.id)
            .filter(model.id == str(entity_id), model.company_id == self.company_id)
            .first()
        )
        if mine is None:
            raise ReferenceConflict(
                f"{subject} is linked to a record in another company",
                field_name=field_name,
            )

    # -------------------------------------------------------- v2 resolution
    def _resolve_master(
        self,
        *,
        model: type,
        ref_field: str,
        ref: Optional[str],
        code_field: Optional[str],
        code: Optional[str],
        name: Optional[str],
        warnings: list[str],
    ) -> Optional[str]:
        """Ref, then code, then (supplier only) name, then back-create (D1/D2/D10).

        A SENT ref that does not resolve is `MissingReference` on its own -
        unchanged from v1 - but ONLY when there is nothing else to try: the
        moment `code` or `name` is also present, an unresolved ref falls
        through to them rather than failing the whole record, because sending
        MORE identifying information must never make a push worse off than
        sending the ref alone (AC-V1-3, AC-V1-5). `warehouse` is the one
        exception end to end (D10): it never raises, a miss is always a NULL
        FK plus a warning, ref or code alike.
        """
        ref = (ref or "").strip() or None
        code = (code or "").strip() or None
        name = (name or "").strip() or None

        if ref:
            try:
                return self._resolve_ref(ref_field, ref, model)
            except MissingReference:
                if model is Warehouse:
                    warnings.append(WARN_WAREHOUSE_UNRESOLVED)
                    return None
                if not code and not name:
                    raise

        entity_id = self._resolve_by_fallback(model, code, name, warnings)
        if entity_id is not None:
            if ref:
                # The ref did not resolve above, but the row it names now
                # exists (or was just found by code/name) - register it so
                # the NEXT push is a step-1 ref match (D1).
                self.refs.link(
                    entity_type=model.__tablename__,
                    entity_id=entity_id,
                    source_ref=ref,
                    integration_id=self.integration_id,
                )
            return entity_id

        if model is Warehouse:
            warnings.append(WARN_WAREHOUSE_UNRESOLVED)
            return None
        if model is Product:
            raise MissingReference(code_field if code else ref_field, code or ref)
        if model is Customer:
            if code:
                warnings.append(WARN_CUSTOMER_UNRESOLVED)
                return None
            if ref:
                raise MissingReference(ref_field, ref)
            return None
        if ref:
            # Supplier / sales agent: nothing was sent to fall back on, so this
            # is exactly the v1 shape - a sent ref that never resolved.
            raise MissingReference(ref_field, ref)
        return None

    def _resolve_by_fallback(
        self, model: type, code: Optional[str], name: Optional[str], warnings: list[str]
    ) -> Optional[str]:
        """Code, then (supplier only) name, then back-create. Never touches ref."""
        if model in (Product, Warehouse):
            return self._resolve_by_code(model, code) if code else None

        if model is SalesAgent:
            if not code:
                return None
            agent = sales_agent_service.resolve(self.db, code)
            if agent is None:
                agent = sales_agent_service.resolve_or_create(self.db, code)
                if agent is not None:
                    warnings.append(WARN_AGENT_CREATED)
            return str(agent.id) if agent is not None else None

        if model is Supplier:
            entity_id = self._resolve_by_code(model, code) if code else None
            if entity_id is None and name:
                entity_id = self._resolve_supplier_by_name(name)
            if entity_id is not None:
                return entity_id
            if code or name:
                supplier = back_create_supplier(
                    self.db,
                    code=code or supplier_slug(self.db, name),
                    name=name or code,
                )
                if supplier is not None:
                    warnings.append(WARN_SUPPLIER_CREATED)
                    return str(supplier.id)
            return None

        if model is Customer:
            entity_id = self._resolve_by_code(model, code) if code else None
            if entity_id is not None:
                return entity_id
            # D2: only when BOTH are sent - the unique index is on the pair,
            # and a code-only row would collide with a later named one.
            if code and name:
                customer = customer_back_create.get_or_create(self.db, code=code, name=name)
                if customer is not None:
                    warnings.append(WARN_CUSTOMER_CREATED)
                    return str(customer.id)
            return None

        return None

    def _resolve_by_code(self, model: type, code: str) -> Optional[str]:
        """Exact match on the model's code column, case/whitespace-insensitive.

        `order_by(id.desc())` rather than an unqualified `.scalar()`: a code is
        unique per company for every model here EXCEPT `customers` (D2 - one
        debtor code routinely carries more than one legal name), and a query
        that raises on more than one row would turn that into a 500 instead of
        a deterministic pick.
        """
        column = _CODE_COLUMNS[model]
        query = (
            self.db.query(model.id)
            .filter(func.upper(func.btrim(column)) == code.upper())
            .order_by(model.id.desc())
        )
        if _is_company_scoped(model.__tablename__):
            query = query.filter(model.company_id == self.company_id)
        row = query.first()
        return str(row[0]) if row else None

    def _resolve_supplier_by_name(self, name: str) -> Optional[str]:
        """The upload's own name-fallback rule: cleaned name, order by id desc.

        `supplier_name` carries no uniqueness constraint, so more than one row
        can share one - ordered so the pick is deterministic rather than
        whatever order Postgres happens to return (`outstanding_import_service
        ._resolve_parties_by_name`, which this mirrors).
        """
        cleaned = _clean_supplier_name(name)
        if not cleaned:
            return None
        row = (
            self.db.query(Supplier.id)
            .filter(func.upper(Supplier.supplier_name) == cleaned.upper())
            .filter(Supplier.company_id == self.company_id)
            .order_by(Supplier.id.desc())
            .first()
        )
        return str(row[0]) if row else None
