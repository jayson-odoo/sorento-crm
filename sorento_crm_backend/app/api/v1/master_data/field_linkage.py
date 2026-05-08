"""Field-linkage schema endpoint.

Returns the registry rows for a given entity_type so the FE attachment-upload
modal and the per-row "Manage field links" dialog can render a dynamic
multi-select grouped by composite-field group_key.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from typing import Any

from app.dependencies import get_current_user_or_api_key
from app.services.error_handler import handle_validation_error
from app.services.field_linkage import (
    SUPPORTED_ENTITY_TYPES,
    get_field_specs,
)


router = APIRouter()


@router.get("/")
def list_field_linkage_schema(
    entity_type: str = Query(..., description="One of: product, promotion, packing_list, form."),
    current_user: dict = Depends(get_current_user_or_api_key),
) -> dict[str, Any]:
    """Return the field-linkage registry rows for ``entity_type``."""
    if entity_type not in SUPPORTED_ENTITY_TYPES:
        raise handle_validation_error(
            f"Unsupported entity_type '{entity_type}'. "
            f"Expected one of: {', '.join(SUPPORTED_ENTITY_TYPES)}."
        )
    specs = get_field_specs(entity_type)
    return {
        "entity_type": entity_type,
        "fields": [
            {
                "name": s.name,
                "label": s.label,
                "kind": s.kind,
                "unit": s.unit,
                "group_key": s.group_key,
                "extract_note": s.extract_note,
            }
            for s in specs
        ],
    }
