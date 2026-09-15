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
    """One numbered row per candidate.

    `uuid` is the identity the pick resolves to and `uuids` is the FAMILY that identity
    stands for (contract 103): one code with several ledgers or several rows is still one
    thing to the person reading the list, and picking it must yield every member. A
    resolver row carries both; a focus entity has only its own code, which is its own
    family of one.

    `stamp` is what the picker probe already measured about that row ("has incoming"),
    kept as its OWN field rather than folded into `label` - `label` is the resolver's
    own code (contract 28's roster lists what the resolver found, not a sentence about
    it), what a pick resolves back onto (`apply._answer_pending`'s `raw`); the renderer
    is what prints `"{label} - {stamp}"` for the customer to read.
    """
    built = []
    for i, c in enumerate(candidates):
        code = c.get("canonical_code") or c.get("raw")
        identity = c.get("uuid") or code
        family = c.get("uuids")
        label = c.get("raw") or code
        stamp = c.get("stamp")
        option: dict[str, Any] = {
            "position": i + 1,
            "label": label,
            "uuid": identity,
            "uuids": list(family) if isinstance(family, list) and family else ([identity] if identity else []),
            "entity_type": kind,
            "payload": {},
        }
        if stamp:
            option["stamp"] = stamp
        built.append(option)
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
    resolved_candidates: list[dict[str, Any]] | None = None,
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

    # What the RESOLVER matched for the tokens this turn named. It outranks the focus
    # rows for a narrowing decision, because a roster the customer is asked to choose
    # from has to list things that exist: "wc286" is one focus entity and ten real
    # products, and offering the customer their own typo back is not a choice.
    if resolved_candidates:
        if policy_value in _ROSTER_POLICIES and kind != "tier":
            if len(resolved_candidates) == 1:
                # A code that resolves to exactly one thing IS narrowed to a code -
                # there is nothing left to ask.
                return NarrowOutcome(None, [], list(resolved_candidates), None)
            return NarrowOutcome(f"{kind}_pick", _options(resolved_candidates, kind), [], None)
        candidates = list(resolved_candidates)

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
        # a code", "customer under order asks for one family" - a NAMED candidate is
        # asked about, not assumed. What settles it is IDENTITY: a candidate carrying a
        # `uuid` is one the resolver matched or the customer picked off this very
        # roster, and asking again for a code you already hold re-prints the same
        # question forever (contract 36's own sticky roster is what feeds it back).
        if candidates and not all(c.get("uuid") for c in candidates):
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
