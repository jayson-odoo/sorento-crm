"""Schema for the rule-facts catalog (RuleBuilder fact picker)."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class RuleFactItem(BaseModel):
    key: str
    label: str
    type: str
    operators: list[str]
    source: str
    sourceLabel: str
    options: Optional[list[dict[str, Any]]] = None
