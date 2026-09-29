"""The SystemTemplate record shared by the system email registries (#1349)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class SystemTemplate:
    code: str
    name: str
    description: str
    subject: str
    blocks: list[dict[str, Any]]
    preheader: Optional[str] = None
    body_text: Optional[str] = None
    variables: list[dict[str, str]] = field(default_factory=list)
    sample: dict[str, Any] = field(default_factory=dict)

    def document(self) -> dict[str, Any]:
        return {"version": 1, "blocks": [dict(b) for b in self.blocks]}
