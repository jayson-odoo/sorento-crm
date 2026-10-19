"""Does the message name its own class: parser hints only, shared by the turn and head packages."""
from __future__ import annotations

from typing import Any


def names_own_class(entities: list[dict[str, Any]]) -> bool:
    """True when the message names its own subject by class: a current-message entity the
    parser hinted `category` or `product_type` (kept as `class_hint` when grounding turned it into a spec). Parser hints only, no word is read."""
    return any(
        e.get("current_message") is not False
        and (
            str(e.get("hint") or "").strip().lower() in ("category", "product_type")
            or str(e.get("class_hint") or "").strip().lower() in ("category", "product_type")
        )
        for e in entities
        if isinstance(e, dict)
    )
