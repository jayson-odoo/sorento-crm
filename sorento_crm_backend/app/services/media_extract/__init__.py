"""Chatbot media extraction: the prompt, the output contract and the wording.

A sibling package to `ai_extract`, deliberately not an edit to it, so the live
portal extract route is untouched by anything here (PLAN section 4.2).

* `prompts.py` - the extraction system prompt, verbatim from PLAN Appendix A
* `schema.py`  - the strict output contract and its tolerant parse
* `service.py` - `MediaExtractService`, the composer for both lanes
* `transcribe.py`- voice, with the configurable language strategy
* `wording.py` - every customer-facing string

`service` is deliberately NOT imported here. It imports `media_access_service`
for `resolve_media_settings`, and `media_access_service` imports `wording` from
this package - re-exporting the service would close that into an import cycle.
Import it by path: `from app.services.media_extract.service import ...`.
"""
from app.services.media_extract import prompts, schema, wording
from app.services.media_extract.prompts import (
    ATTRIBUTE_KINDS,
    ENTITY_HINTS,
    IMAGE_KINDS,
    MEDIA_EXTRACTION_SYSTEM_PROMPT,
    build_messages,
    render_system_prompt,
)
from app.services.media_extract.schema import (
    MediaAttribute,
    MediaConflict,
    MediaConflictValue,
    MediaEntity,
    MediaExtraction,
    MediaExtractionParseError,
    empty_result_body,
    parse_extraction,
    parse_provider_json,
)

__all__ = [
    "ATTRIBUTE_KINDS",
    "ENTITY_HINTS",
    "IMAGE_KINDS",
    "MEDIA_EXTRACTION_SYSTEM_PROMPT",
    "MediaAttribute",
    "MediaConflict",
    "MediaConflictValue",
    "MediaEntity",
    "MediaExtraction",
    "MediaExtractionParseError",
    "build_messages",
    "empty_result_body",
    "parse_extraction",
    "parse_provider_json",
    "prompts",
    "render_system_prompt",
    "schema",
    "wording",
]
