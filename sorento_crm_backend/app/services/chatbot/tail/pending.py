"""R3: what the bot is waiting for, RECORDED rather than re-read out of its own words.

H13 is the frozen string contract. The JS decided "is an escalation offer open?" by
matching `/would you like me to escalate/i` against the bot's OWN previous reply, and
"did the previous turn answer?" by matching `/^Previous turn \\(/`. D11 forbids both:
understanding text is the parser's job, everything after it works on structured state.

Two replacements, and they are deliberately different in kind:

* **Across turns** the answer is a persisted marker. `variables.pending` is written here
  and read by `output_exchange.offer_is_open`, which accepts BOTH forms during the
  migration window (AC-106) and loses the regex at S8.
* **Within a turn** there is nothing to persist. `crossdomain-compose`'s `isAnswered`
  asks whether THIS turn's own business-summary arm ran, and the compiler knows that
  directly - so `CompiledState.answered_domain` carries it as a value and no session key
  is invented for a question that never crosses a turn boundary.

**Two kinds are written today.** `escalation_offer` is the one that replaces a TEXT read.
`member_offer` joins it at S3 because the offer-hold lane RE-PERSISTS an open roster and
the marker is what says the offer is still open after S8 deletes the regex - the roster
itself is carried by `selection_context` + `last_result_set`, but neither of those says
"an escalation is still on the table". `team_clarify` joins them on
7 Sep 2026 (AC-822), which is S5's lane needing it exactly as this paragraph anticipated:
owner rule R-a narrows the ask to the teams the customer's own word named, so
`selection_context` alone no longer says WHICH teams were offered, and the answer to the
ask has nothing to resolve against without the list. The remaining two (`company_clarify`,
`tier_ask`) still have a structured reader already and no text read to replace, so writing
them would be machinery for a hypothetical.
"""
from __future__ import annotations

from typing import Any, Mapping

from app.services.chatbot import jsc


# How many turns an UNANSWERED member offer survives, counted down on the marker. The
# same 3 the did-you-mean offer uses, and the same rule for the same reason (owner ruling,
# 6 Sep 2026, AC-816 rule 1): an offer is what is on the customer's screen, and it stops
# being that when they move on. Living forever is what let a bare "yes" about something
# else assign a human off an offer the customer had ignored.
MEMBER_OFFER_TTL = 3


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
    selection_context: Any = None,
    member_offer_ttl: int | None = None,
    team_clarify_options: Any = None,
) -> dict[str, Any] | None:
    """`variables.pending`, or None when nothing is pending.

    `None` is written EXPLICITLY, never left to key absence. That is the same lesson the
    dym-offer lifecycle learned the hard way: a branch that relies on "the key just is not
    there" survives one refactor and then silently keeps a stale offer alive.
    """
    if selection_context == "team_clarify":
        # THE THIRD KIND (AC-822, owner rule R-b). The module docstring above says the
        # clarify kinds have a structured reader already and no text read to replace, so
        # writing them would be machinery for a hypothetical - and that held right up to
        # the turn that made it false. The ask offers a NARROWED set of teams now (R-a:
        # "marketing" offers three, not eight), and `selection_context` alone cannot say
        # WHICH three, so a tap on a quick reply had nothing to resolve against.
        #
        # MORE SPECIFIC than the offer kinds and it outranks them for the same reason
        # `member_offer` outranks `escalation_offer`: the next turn has to resolve an
        # answer against this list, and "an offer is open" does not say which list.
        return {
            "kind": "team_clarify",
            "team": escalation_team(qf, gate),
            "domain": jsc.get(qf, "domain_hint"),
            "options": list(jsc.array(team_clarify_options)),
        }
    if selection_context == "member_offer":
        # A numbered roster is on the customer's screen. MORE SPECIFIC than
        # `escalation_offer` and it outranks it: the next turn has to resolve a number
        # against that roster, and "an offer is open" does not say which.
        return {
            "kind": "member_offer",
            "team": escalation_team(qf, gate),
            "domain": jsc.get(qf, "domain_hint"),
            # The offer's remaining life. `None` means it was made THIS turn, so the clock
            # starts; a carried offer arrives with the decremented value already worked
            # out by `compile_state._offer_carry`, which is the block that decides whether
            # there is anything left to carry at all.
            "ttl": MEMBER_OFFER_TTL if member_offer_ttl is None else member_offer_ttl,
        }
    if not offer_open:
        return None
    return {
        "kind": "escalation_offer",
        "team": escalation_team(qf, gate),
        "domain": jsc.get(qf, "domain_hint"),
    }
