"""Pure helpers for the multi-domain fan-out (lane 2).

Three things the plan names as pure and testable, kept out of the big `run_fetch` /
`complete_answer` bodies so each has its own pytest (`tests/chatbot/test_fanout.py`):

* `escalation_teams(missed)` - `{DOMAIN_SPEC[d].escalation_team for d in MISSED} - {None}`,
  deduped, in section order. The offer over the domains a fan-out turn missed.
* `Consumed` - the ONE general deduper, keyed `(entity id, domain)` (D12). Shared by every
  section and every ladder rung; a pair prints once and is skipped thereafter, and the same
  entity under a different domain is a different fact.
* `ladder_rungs_outside(asked, ladder)` - the closing ladder climbs only to rungs OUTSIDE
  the asked set, so a domain the turn already asked is never re-climbed as a "new" rung.

No I/O, no session, no model calls.
"""
from __future__ import annotations

from typing import Any

from app.services.chatbot.contracts import DOMAIN_SPEC


def escalation_teams(missed_domains: list[str]) -> list[str]:
    """The deduped escalation teams over the MISSED domains, in section order (AC-1051).

    `DOMAIN_SPEC[d].escalation_team` for each missed domain, `None` dropped (a domain with
    no team contributes nothing), duplicates collapsed keeping first-seen order: two missed
    domains that route to the same team (incoming and purchase_order both -> purchasing)
    offer that team once.
    """
    teams: list[str] = []
    for domain in missed_domains or []:
        spec = DOMAIN_SPEC.get(str(domain)) if domain is not None else None
        team = spec.escalation_team if spec is not None else None
        if team and team not in teams:
            teams.append(team)
    return teams


class Consumed:
    """The one shared deduper, keyed `(entity id, domain)` (D12, AC-1047).

    `add`/`seen` on the exact pair: a fact for entity X under domain D prints once whichever
    section or rung produced it first, and any later renderer skips the pair. The SAME
    entity under a DIFFERENT domain is a different fact (a stock line and an incoming line
    for one product are both wanted), so the key is the pair, never the entity alone.
    """

    def __init__(self) -> None:
        self._seen: set[tuple[str, str]] = set()

    def _key(self, entity_id: Any, domain: Any) -> tuple[str, str]:
        return (str(entity_id), str(domain))

    def add(self, entity_id: Any, domain: Any) -> None:
        self._seen.add(self._key(entity_id, domain))

    def seen(self, entity_id: Any, domain: Any) -> bool:
        return self._key(entity_id, domain) in self._seen


def ladder_rungs_outside(asked: list[str], ladder: dict[str, list[str]]) -> list[str]:
    """The ladder rungs OUTSIDE the asked set, in order, deduped (AC-1047).

    After the sections, the ladder climbs once to whatever rungs the asked domains would
    normally step to that were NOT themselves asked - a domain the turn already covered is
    not a "new" rung. Walk the asked domains in order, take each one's ladder rungs in
    order, and keep the ones neither asked nor already collected.
    """
    asked_set = {str(d) for d in (asked or [])}
    rungs: list[str] = []
    for domain in asked or []:
        for rung in ladder.get(str(domain)) or []:
            rung = str(rung)
            if rung not in asked_set and rung not in rungs:
                rungs.append(rung)
    return rungs
