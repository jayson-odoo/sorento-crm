# The narrower: per (domain, entity kind) policy, proceed / ask roster / ask type /
# ask tier / filter optional (PLAN-chatbot-turn-rearch.md "The policy", AC-1526).
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.chatbot.turn.state import KIND_FIELD_MAP, Focus, Profile

# Which suffix an ask carries, by policy value.
_ROSTER_POLICIES = {"narrow_to_code", "must_narrow_one", "narrow_by_tier"}
_TYPE_POLICIES = {"narrow_by_type"}


def _candidates(focus: Focus, kind: str) -> list[dict[str, Any]]:
    if kind == "tier":
        return [{"raw": t, "canonical_code": t} for t in focus.tier]
    attr = KIND_FIELD_MAP.get(kind)
    if attr:
        value = getattr(focus, attr, [])
        return list(value) if isinstance(value, list) else []
    return list(focus.extra.get(kind, []))


def _options(candidates: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    built = []
    for i, c in enumerate(candidates):
        code = c.get("canonical_code") or c.get("raw")
        built.append(
            {
                "position": i + 1,
                "label": c.get("raw") or code,
                "uuid": code,
                "uuids": [code] if code else [],
                "entity_type": kind,
                "payload": {},
            }
        )
    return built


@dataclass
class NarrowOutcome:
    ask_kind: str | None
    ask_options: list[dict[str, Any]]
    entities: list[dict[str, Any]]
    filter_value: Any


def decide(
    *,
    kind: str,
    policy_value: str,
    focus: Focus,
    profile: Profile,
    attributes: tuple[str, ...] | list[str] = (),
) -> NarrowOutcome:
    """`attributes` is the verdict's `requested_attributes` - what the question asked ABOUT.

    A question that names its own attribute has already answered the narrower's question
    (contract 114 to 120): "which taps have a certificate" needs no "which kind of file?",
    and a count of what this contact may see needs no tier pick before it can be counted.
    So a named attribute satisfies `narrow_by_type` and silences `narrow_by_tier`, and
    changes nothing for any other policy value.
    """
    if policy_value == "not_applicable":
        return NarrowOutcome(None, [], [], None)

    candidates = _candidates(focus, kind)

    if policy_value == "list_all":
        return NarrowOutcome(None, [], candidates, None)

    if policy_value in _ROSTER_POLICIES:
        if policy_value == "narrow_by_tier" and kind == "tier":
            if attributes and not candidates:
                return NarrowOutcome(None, [], [], profile.tier)
            if candidates:
                one = candidates[-1]
                value = one.get("canonical_code") or one.get("raw")
                return NarrowOutcome(None, [], [], value)
            if profile.tier:
                return NarrowOutcome(None, [], [], profile.tier)
            return NarrowOutcome("tier_pick", [], [], None)
        # AC-1526's own wording: "product under incoming and purchase cost asks for
        # a code", "customer under order asks for one family" - unconditional, not
        # "asks only when there is more than one candidate". Any candidate at all
        # asks for the confirming pick; none named proceeds with nothing to filter.
        if candidates:
            return NarrowOutcome(f"{kind}_pick", _options(candidates, kind), [], None)
        return NarrowOutcome(None, [], [], None)

    if policy_value in _TYPE_POLICIES:
        if not candidates:
            if attributes:
                return NarrowOutcome(None, [], [], attributes[0])
            return NarrowOutcome(f"{kind}_ask", [], [], None)
        return NarrowOutcome(None, [], candidates, None)

    # "optional_filter" and anything unrecognised: narrow when named, never asked.
    value = candidates[0].get("canonical_code") or candidates[0].get("raw") if candidates else None
    return NarrowOutcome(None, [], candidates, value)
