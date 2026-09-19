# Reconciliation: the resolver is asked for the hinted kind first; a miss with exactly
# one other kind hitting rewrites the kind; two kinds hitting asks (PLAN-chatbot-turn-
# rearch.md "APPLY contract", AC-1527). `resolved` is a plain dict, built by hand in
# tests - `{raw: {kind: hit_count, ...}, ...}` - the real resolver seam lands in S3.
from __future__ import annotations

from typing import Any


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
