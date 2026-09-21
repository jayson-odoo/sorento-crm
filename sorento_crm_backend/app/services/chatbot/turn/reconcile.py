# Reconciliation: the resolver is asked for the hinted kind first; a miss with exactly
# one other kind hitting rewrites the kind; two kinds hitting asks (PLAN-chatbot-turn-
# rearch.md "APPLY contract", AC-1527). `resolved` is a plain dict, built by hand in
# tests - `{raw: {kind: hit_count, ...}, ...}` - the real resolver seam lands in S3.
from __future__ import annotations

from typing import Any

from app.services.chatbot.turn.state import fold_token


def _key(value: Any) -> str:
    """The one join key both sides of the resolver's own by-token map fold to."""
    return fold_token(str(value).strip().casefold()) if value is not None else ""


def hits_for_token(resolved: dict[str, dict[str, int]] | None, raw: Any) -> dict[str, int] | None:
    """The resolver's own `{kind: hit count}` for the token a customer typed.

    Hand pass 12 round 4, R7: the map (`turn_runtime.resolve_kinds`'s own `by_token`)
    is keyed by the token the RESOLVER echoes back, which is the FOLDED one -
    `resolve_gate.resolve_entity_body` sends every entity through its own `[-\\s]+`
    fold before the resolver sees it, so "ZZT-CONT-9F" comes back as "ZZTCONT9F"
    (`turn_runtime._token_key`'s own docstring, measured on turn bb921451). Looking it
    up by the raw text a customer typed therefore found NOTHING for any token carrying
    a dash or a space, so a mishinted dashed record key was never rewritten to its
    resolved kind at all - the same class of silent-join failure R1 fixed for
    `unresolved_tokens`, in the one place that still had it.

    Exact text first (a hand-built map, and the common no-separator case), then the
    folded join. `setdefault` on the folded index so the FIRST key wins rather than a
    later one clobbering it, for the rare pair of typed tokens that fold alike.
    """
    if not resolved or raw is None:
        return None
    exact = resolved.get(raw) if isinstance(raw, str) else None
    if exact:
        return exact
    key = _key(raw)
    if not key:
        return None
    folded: dict[str, dict[str, int]] = {}
    for token, hits in resolved.items():
        folded.setdefault(_key(token), hits)
    return folded.get(key)


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
        hits = hits_for_token(resolved, raw)
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
