"""Ingest contract version for the ESB (D8, AC-V0-1).

The ESB gates every new key it sends behind `sorento_contract_version = 2` on
its consumer connection, so it needs one endpoint to ask Sorento what version
and which entities it currently accepts, without inferring either from trial
and error against `/ingest/{entity}`.

Guarded by its own `integration.contract.read` slug rather than a reused
master slug: reading the contract is not the same act as writing any one
entity, and an integration scoped to a single master should not need a grant
on every other master just to check the version.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.external.ingest import CONTRACT_VERSION, SUPPORTED_ENTITIES

router = APIRouter()


@router.get("")
def get_contract():
    """Version and entity list the ESB gates its integration on.

    `SUPPORTED_ENTITIES` directly (review nit) - `shipping_orders` (S3) is
    already a real member of it (folded in by `SHIPPING_ORDER_ENTITIES`), so
    a second, contract-local alias for the same set had nothing left to add.
    """
    return {"version": CONTRACT_VERSION, "entities": sorted(SUPPORTED_ENTITIES)}
