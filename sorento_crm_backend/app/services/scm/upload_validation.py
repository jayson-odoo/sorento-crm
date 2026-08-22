"""The `{valid, errors, warnings, summary}` verdict every importer in this system returns.

`import-tracking` and the GRN import have carried a Test button since long before SCM existed,
and the shape behind it is this one. The SCM uploads were the odd ones out: they returned a
diff and left the operator to work out whether it was safe. Same contract here, so a Test
means the same thing wherever somebody presses it.

The distinction that makes the button worth anything:

* an ERROR blocks. The file cannot be applied, and applying it would either write nonsense or
  write nothing at all.
* a WARNING does not. Something in the file will not land, and the rest is still worth
  loading. A warning the operator ignores is a decision, not an accident, because it is on
  the screen before they press Confirm.

Derived on the SERVER from the same read `apply` performs, so the browser cannot show a
verdict that disagrees with what the write will actually do.
"""
from __future__ import annotations

from typing import Any, Optional


def envelope(
    *,
    ok: bool,
    problems: list[str],
    warnings: list[str],
    summary: dict[str, Any],
) -> dict:
    """The standard verdict. `ok` false means the file could not be read at all."""
    errors = list(problems) if not ok else []
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": [w for w in warnings if w],
        "summary": summary,
    }


def named(count: int, codes: list[str], *, one: str, many: str, limit: int = 12) -> Optional[str]:
    """A warning that NAMES what it is about, capped, and says how many were left out.

    A count alone ("2 items not found") tells somebody there is a problem; the codes tell them
    which one, and the codes are what they take to whoever owns the catalogue.
    """
    if not count:
        return None
    shown = ", ".join(codes[:limit])
    tail = f" and {count - limit:,} more" if count > limit else ""
    subject = one if count == 1 else many
    return f"{count:,} {subject}: {shown}{tail}" if shown else f"{count:,} {subject}"
