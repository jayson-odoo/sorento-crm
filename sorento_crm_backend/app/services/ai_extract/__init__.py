"""AI-assisted form prefill from attachments (images + PDFs).

The package exposes a generic `form_key -> schema -> extract` engine. New forms
register a schema in :mod:`form_schema_registry`; the extract service does the
rest (multimodal LLM call, lookup canonicalization, usage logging).
"""
from app.services.ai_extract.extract_service import (
    ExtractedProductLine,
    ExtractFieldMeta,
    ExtractResult,
    AIExtractService,
)
from app.services.ai_extract.form_schema_registry import (
    ExtractFieldSpec,
    FORM_SCHEMAS,
    get_form_schema,
)

__all__ = [
    "AIExtractService",
    "ExtractFieldMeta",
    "ExtractFieldSpec",
    "ExtractResult",
    "ExtractedProductLine",
    "FORM_SCHEMAS",
    "get_form_schema",
]
