"""`asks[]` in, three flat views out. The ONE place the parser's shape is unpacked.

AC-1021 (D3). Parser v3 emits what the dealer asked as a list of asks, each an
`{domain, entities}` pair in the order the message named them: "stock for A and eta for B"
is two asks, "stock and eta for A" is two asks over the same entity, and "SRTWT2634" on its
own is no ask at all. That shape is the truth, and it is also awkward to read from a lane
that wants "which products is this turn about" - so it is flattened exactly once, here, at
intake, into the three views everything downstream uses:

* `domains` - the domain names, deduped, in ASK ORDER. Lane 2 renders one section per
  entry in this order (D11), so the order is data and not presentation.
* `entities` - the ordered union of every ask's entities. A product named in two asks
  ("stock and eta for A") appears ONCE: it is one product the dealer mentioned, and a
  resolver that saw it twice would offer two pickers for it.
* `binding` - `{domain: [index into `entities`]}`, which says WHICH entity belongs to which
  ask when the message said so ("stock for A and eta for B"). It lasts one turn, by
  construction: it describes this message, and the next message says its own.

Nothing here calls a model, opens a session or reads the customer's words.
"""
from __future__ import annotations

from typing import Any


def flatten(parse: Any) -> dict[str, Any]:
    """`{domains, entities, binding}` from ONE emission, of either parser version.

    A v3 emission flattens its `asks` as described above. A v1 or v2 emission has no asks
    and never will (the label does not move until the owner moves it, D10), so it flattens
    through its own flat keys instead: `domains` is `[domain_hint]` or empty, `entities` is
    the list it already carries, and `binding` is empty because a flat emission never said
    which entity belonged to which domain. ONE function for both, so a reader never has to
    ask which prompt answered the turn - which is the same reason the engine derives
    `domain_hint` per turn rather than persisting it (AC-1026).

    Tolerant of everything: a parse with no `asks`, an ask with no domain, an ask with no
    entities, a non-dict in either list.
    """
    emission = parse if isinstance(parse, dict) else {}
    asks = emission.get("asks")
    if not isinstance(asks, list) or not asks:
        return _flatten_v1(emission)
    asks = asks if isinstance(asks, list) else []

    domains: list[str] = []
    entities: list[dict[str, Any]] = []
    index_by_identity: dict[tuple[str, str], int] = {}
    binding: dict[str, list[int]] = {}

    for ask in asks:
        if not isinstance(ask, dict):
            continue
        domain = ask.get("domain")
        domain = str(domain).strip() if isinstance(domain, str) and domain.strip() else None

        bound: list[int] = []
        for entity in ask.get("entities") or []:
            if not isinstance(entity, dict):
                continue
            identity = _identity(entity)
            position = index_by_identity.get(identity)
            if position is None:
                position = len(entities)
                index_by_identity[identity] = position
                entities.append(entity)
            if position not in bound:
                bound.append(position)

        if domain is None:
            # An UNBOUND ask: the dealer named entities without saying which domain they
            # belong to ("SRTWT2634" after a stock answer). Its entities are still part of
            # the turn's scope, which is why they were collected above; there is simply no
            # domain to bind them to.
            continue
        if domain not in domains:
            domains.append(domain)
        # A domain named twice merges, rather than the second ask replacing the first: two
        # asks for one domain is the dealer listing subjects, not changing their mind.
        binding[domain] = _merge(binding.get(domain), bound)

    return {"domains": domains, "entities": entities, "binding": binding}


def _flatten_v1(emission: dict[str, Any]) -> dict[str, Any]:
    """The same three views off a FLAT (v1 / v2) emission.

    `binding` is empty rather than "every entity under the one domain", and the difference
    matters: an empty binding means "the message did not say", which is what a flat
    emission is, and a full one would claim the dealer had bound each code to a domain when
    the prompt never asked them to.
    """
    domain = emission.get("domain_hint")
    domain = str(domain).strip() if isinstance(domain, str) and domain.strip() else None
    entities = [e for e in (emission.get("entities") or []) if isinstance(e, dict)]
    return {
        "domains": [domain] if domain else [],
        "entities": entities,
        "binding": {},
    }


def _identity(entity: dict[str, Any]) -> tuple[str, str]:
    """What makes two mentions the SAME entity: its code and its type.

    `canonical_code` where the parser resolved one, the raw token otherwise, lowercased -
    the same pair `focus` compares on, so the union here and a replacement there cannot
    disagree about whether the dealer named a new product.
    """
    code = entity.get("canonical_code") or entity.get("raw") or ""
    hint = entity.get("hint") or ""
    return (str(code).strip().lower(), str(hint).strip().lower())


def _merge(existing: list[int] | None, added: list[int]) -> list[int]:
    out = list(existing or [])
    for position in added:
        if position not in out:
            out.append(position)
    return out
