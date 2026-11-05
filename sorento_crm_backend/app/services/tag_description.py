"""The one write-path cleaner for the two price tag text columns (`product_combos.description`,
`products.price_tag_description`): allow-list the stored HTML, then cap what is actually stored."""
from __future__ import annotations

from typing import Optional

from app.services.error_handler import AppException
from app.utils.tag_rich_text import sanitise_tag_html

MAX_DESCRIPTION_CHARS = 5000


def clean_description(raw: Optional[str], label: str = "Description") -> Optional[str]:
    cleaned = sanitise_tag_html(raw)
    if cleaned is not None and len(cleaned) > MAX_DESCRIPTION_CHARS:
        raise AppException(
            status_code=422,
            message=f"{label} must be {MAX_DESCRIPTION_CHARS} characters or fewer",
        )
    return cleaned
