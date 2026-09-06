"""Ingest contract version for the ESB (D8, AC-V0-1; v2.1 shape added S4 of
ingest-parity-standardisation).

The ESB gates every new key it sends behind `sorento_contract_version = 2` on
its consumer connection, so it needs one endpoint to ask Sorento what version
and which entities it currently accepts, without inferring either from trial
and error against `/ingest/{entity}`.

Guarded by its own `integration.contract.read` slug rather than a reused
master slug: reading the contract is not the same act as writing any one
entity, and an integration scoped to a single master should not need a grant
on every other master just to check the version.

v2.1 adds four keys describing WHAT changed since v2, so an ESB integrator
reads the diff off this endpoint rather than a changelog: `fields_added`
(new optional fields, per entity - never required, so a v2-shaped payload
still ingests unchanged), `fields_removed` (D15 end state - these now fail
validation, never accepted-and-warned), `status_optional` (which documents
now derive their own status when the field is absent), and `absent_vs_null`
(D14 - true everywhere: an OMITTED field never overwrites a stored value,
only an explicit `null` does). `warnings` is the fixed vocabulary every
verdict's `warnings`/`lines` keys draw from, imported from the modules that
actually raise each one rather than restated here, so this list cannot drift
from what a real response emits.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.external.ingest import CONTRACT_VERSION, SUPPORTED_ENTITIES
from app.services.master_ref_resolver import (
    WARN_AGENT_CREATED,
    WARN_CUSTOMER_CREATED,
    WARN_CUSTOMER_UNRESOLVED,
    WARN_REF_MISMATCH,
    WARN_SUPPLIER_AMBIGUOUS,
    WARN_SUPPLIER_CREATED,
    WARN_UNCLASSIFIED_DEMAND,
    WARN_WAREHOUSE_UNRESOLVED,
)
from app.services.shipping_order_ingest_service import (
    WARN_CONTAINER_UNRESOLVED,
    WARN_RECEIVED_LOCKED,
)

router = APIRouter()

# New OPTIONAL fields per entity since v2 - additive only (D-final: nothing
# here was ever required, so a v2-shaped payload still ingests unchanged).
# `is_shipping_order` lives ONLY under `purchase_orders` (review S1, 2026-09-06):
# it is parsed off the `purchase_orders` payload to REFUSE a push there and
# redirect it to `shipping_orders` (D6/AC-P3-7) - `CanonicalShippingOrder`
# itself has no such field and `extra="forbid"` would reject it outright, so
# an earlier "documented under shipping_orders too, since that is the family
# it names" note here was wrong and has been removed.
FIELDS_ADDED: dict[str, list[str]] = {
    "products": ["is_discontinued", "remark", "brand_code"],
    "customers": ["market_segment_code", "region"],
    "sales_orders": ["customer_segment", "customer_region"],
    "purchase_orders": ["is_shipping_order"],
    "shipping_orders": ["container_number"],
}

# D15 end state (AC-P0-4): these now FAIL validation (extra=forbid), never
# accepted-and-warned - see `deprecated_field` in `WARNINGS` below, which
# stays in the vocabulary as the value a pre-2.1 integration may still be
# checking for, even though nothing emits it any more.
FIELDS_REMOVED: dict[str, list[str]] = {
    "customers": ["credit_limit", "payment_terms_days", "payment_terms_code"],
    "suppliers": ["payment_terms_code"],
}

# Which documents now derive their own `status` when the payload omits it
# (`document_rules.derive_document_status`) rather than requiring it.
STATUS_OPTIONAL: dict[str, bool] = {
    "sales_orders": True,
    "purchase_orders": True,
    "shipping_orders": True,
}

# The fixed warning vocabulary, drawn from the constants each producing
# module actually raises, plus the handful of masters-push warnings that are
# still plain literals in `master_ingest_service` (never promoted to their
# own constants - there was exactly one call site for each) and two
# documentation-only entries: `lines.dropped` names the `lines.dropped` COUNT
# key a document verdict carries (D9), not a `warnings` list entry itself;
# `deprecated_field` is retired code (D15 end state) kept here so a pre-2.1
# integration checking for it by name still finds it documented.
WARNINGS: list[str] = sorted(
    {
        WARN_CUSTOMER_CREATED,
        WARN_CUSTOMER_UNRESOLVED,
        WARN_SUPPLIER_CREATED,
        WARN_AGENT_CREATED,
        WARN_WAREHOUSE_UNRESOLVED,
        WARN_REF_MISMATCH,
        WARN_UNCLASSIFIED_DEMAND,
        WARN_SUPPLIER_AMBIGUOUS,
        WARN_CONTAINER_UNRESOLVED,
        WARN_RECEIVED_LOCKED,
        "category_created",
        "uom_created",
        "brand_created",
        "segment_unknown",
        "lines.dropped",
        "deprecated_field",
    }
)


@router.get("")
def get_contract():
    """Version, entity list and the v2.1 diff the ESB gates its integration on.

    `SUPPORTED_ENTITIES` directly (review nit) - `shipping_orders` (S3) is
    already a real member of it (folded in by `SHIPPING_ORDER_ENTITIES`), so
    a second, contract-local alias for the same set had nothing left to add.
    """
    return {
        "version": CONTRACT_VERSION,
        "entities": sorted(SUPPORTED_ENTITIES),
        "fields_added": FIELDS_ADDED,
        "fields_removed": FIELDS_REMOVED,
        "status_optional": STATUS_OPTIONAL,
        # D14: absent-vs-null holds across every master, not per-entity - one
        # bool, not a dict of trues.
        "absent_vs_null": True,
        "warnings": WARNINGS,
    }
