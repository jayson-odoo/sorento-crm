# Reconciliation: the resolver is asked for the hinted kind first; a miss with exactly
# one other kind hitting rewrites the kind; two kinds hitting asks (PLAN-chatbot-turn-
# rearch.md "APPLY contract", AC-1527). `resolved` is a plain dict, built by hand in
# tests - `{raw: {kind: hit_count, ...}, ...}` - the real resolver seam lands in S3.
from __future__ import annotations

from typing import Any

#: Hand pass 11, defect 4 (owner ruling, "cabana catalog" -> a kind_pick over a brand
#: word): a SCOPE hint names a company/brand filter, never a subject the resolver could
#: offer a choice between. "cabana" (hint "brand") hitting both `promotion` and
#: `attachment` in the resolver's per-token count is not the customer choosing between
#: two THINGS named "cabana" - it is one brand word that happens to also match file
#: names - so it is left exactly as the parser hinted it, the same as a token with no
#: hits at all. Reconciliation exists to settle what a SUBJECT word IS (an order, a
#: product, ...); it has no job to do on a word that only ever scopes one.
_SCOPE_HINTS = frozenset({"brand", "company"})


class ReconcileResult:
    def __init__(self) -> None:
        self.entities: list[dict[str, Any]] = []
        self.reconciled: list[tuple[str, str, str]] = []
        self.kind_pick_options: list[dict[str, Any]] | None = None


def apply_reconciliation(
    entities: list[dict[str, Any]], resolved: dict[str, dict[str, int]] | None
) -> ReconcileResult:
    result = ReconcileResult()
    if not resolved:
        result.entities = list(entities)
        return result

    for e in entities:
        if e.get("hint") in _SCOPE_HINTS:
            result.entities.append(e)
            continue
        raw = e.get("raw")
        hits = resolved.get(raw) if raw is not None else None
        if not hits:
            result.entities.append(e)
            continue
        matched = [k for k, count in hits.items() if count and count > 0]
        if len(matched) == 0:
            result.entities.append(e)
        elif len(matched) == 1:
            new_kind = matched[0]
            old_kind = e.get("hint")
            if new_kind != old_kind:
                result.reconciled.append((raw, old_kind, new_kind))
                rewritten = dict(e)
                rewritten["hint"] = new_kind
                result.entities.append(rewritten)
            else:
                result.entities.append(e)
        else:
            options = [
                {
                    "position": i + 1,
                    "label": f"{raw} ({k})",
                    "uuid": None,
                    "uuids": [],
                    "entity_type": k,
                    "payload": {"kind": k},
                }
                for i, k in enumerate(matched)
            ]
            result.kind_pick_options = options
            result.entities.append(e)

    return result
