"""Replace {{ token }} placeholders using an explicit context dict (no arbitrary code execution)."""
from __future__ import annotations

import re
from typing import Any, Dict

_TOKEN_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def render_token_template(template: str | None, context: Dict[str, Any]) -> str:
    if not template:
        return ""

    def _repl(match: re.Match[str]) -> str:
        key = match.group(1)
        val = context.get(key)
        if val is None:
            return ""
        return str(val)

    return _TOKEN_RE.sub(_repl, template)
