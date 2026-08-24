"""Field-linkage registry - maps an entity_type (product/promotion/packing_list/form)
to the list of fields an attachment can be linked against, plus shared validation."""

from app.services.field_linkage.registry import (
    FieldSpec,
    SUPPORTED_ENTITY_TYPES,
    get_field_specs,
    get_field_spec,
    field_keys_for,
    validate_field_keys,
)

__all__ = [
    "FieldSpec",
    "SUPPORTED_ENTITY_TYPES",
    "get_field_specs",
    "get_field_spec",
    "field_keys_for",
    "validate_field_keys",
]
