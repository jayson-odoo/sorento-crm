"""R3: what the bot is waiting for, RECORDED rather than re-read out of its own words.

H13 is the frozen string contract. The JS decided "is an escalation offer open?" by
matching `/would you like me to escalate/i` against the bot's OWN previous reply, and
"did the previous turn answer?" by matching `/^Previous turn \\(/`. D11 forbids both:
understanding text is the parser's job, everything after it works on structured state.

Two replacements, and they are deliberately different in kind:

* **Across turns** the answer is a persisted marker. `variables.pending` is written here
  and read by `output_exchange._offer_is_open`, which accepts BOTH forms during the
  migration window (AC-106) and loses the regex at S8.
* **Within a turn** there is nothing to persist. `crossdomain-compose`'s `isAnswered`
  asks whether THIS turn's own business-summary arm ran, and the compiler knows that
  directly - so `CompiledState.answered_domain` carries it as a value and no session key
  is invented for a question that never crosses a turn boundary.

**Only `escalation_offer` is written today, and that is on purpose.** `PendingKind`
declares five, but the other four (`team_clarify`, `company_clarify`, `tier_ask`,
`member_offer`) each already have a structured reader: `selection_context` plus
`last_result_set`, which the parser post-processor reads without touching text. Writing a
marker nobody reads would be machinery for a hypothetical. S5 writes them when its
escalation lane needs them.
"""
from __future__ import annotations

from typing import Any, Mapping

from app.services.chatbot import jsc


def escalation_team(qf: Mapping[str, Any], gate: Any) -> Any:
    """The team an escalation offer names. ONE declaration, two callers.

    Issue #9: the RESOLVED entity's company team beats the parser's access-level guess.
    `escalate_catalog` interpolates it into the sentence and `derive` records it, so the
    marker and the copy can never name different teams.
    """
    company_team = jsc.get(gate, "company_team") if gate is not None else None
    if jsc.truthy(company_team):
        return company_team
    return jsc.get(jsc.get(qf, "routing"), "suggested_team")


def derive(
    *,
    offer_open: bool,
    qf: Mapping[str, Any],
    gate: Any = None,
) -> dict[str, Any] | None:
    """`variables.pending`, or None when nothing is pending.

    `None` is written EXPLICITLY, never left to key absence. That is the same lesson the
    dym-offer lifecycle learned the hard way: a branch that relies on "the key just is not
    there" survives one refactor and then silently keeps a stale offer alive.
    """
    if not offer_open:
        return None
    return {
        "kind": "escalation_offer",
        "team": escalation_team(qf, gate),
        "domain": jsc.get(qf, "domain_hint"),
    }
