"""The ONE thing the bot can be waiting for, and the one place an answer is resolved.

AC-944, AC-945, AC-947, AC-948, AC-1013, AC-1019 (D5, D7, D9). SIX kinds, one table, one
handler each, and a dispatcher that never guesses:

| kind             | expects     | options                        | outcome                       |
|------------------|-------------|--------------------------------|-------------------------------|
| `product_pick`   | pick (+)    | frozen rows: uuid, code, label | focus.products, source `pick` |
| `customer_pick`  | pick (+)    | family rows with company codes | focus.customer                |
| `team_pick`      | pick/yes_no | the teams the ask OFFERED      | routing set, escalation on    |
| `company_pick`   | pick        | the ledgers the ask offered    | routing set, escalation on    |
| `tier_pick`      | pick (+)    | tiers                          | focus.tier, promotion rerun   |
| `member_offer`   | yes_no      | family members                 | yes: business lane over them  |

(+) reads `pick_or_yes_no` while an escalate offer RIDES on the roster (D19, below).

**`escalate_yes_no` is gone, and nothing the customer sees changed** (D5). An escalate offer
naming ONE team is a `team_pick` carrying that one team as its single option, with
`expects: yes_no` - which is the yes/no question it always was. Two or more teams is the
same kind with `expects: pick` and a numbered quick reply each. One kind, one handler, and
the one-team and many-team offers can no longer disagree about what "yes" means.

**Nothing here has a lifetime** (D9, AC-1019). A question is cleared when it is answered,
when a newer one replaces it, or when the customer asks something else instead
(`dialogue/clearing.py`); `member_offer`'s TTL of 3 went with the rest. An offer the
customer can still see is still answerable, and a counter was only ever a guess at when
they stopped looking.

**A ROSTER IS NOT CONSUMED BY BEING PICKED FROM** (owner ruling D19, 13 Sep 2026, which
restores ruling K rule 1 of 6 Sep). The customer typed "1", read the answer, and the
numbered list is STILL ON THEIR SCREEN - so "2" and "3" have to go on meaning the second
and the third row, which is what the owner's console pass found broken: after the pick
the question was cleared, and the next two numbers were answered about the first product
all over again. `ROSTER_KINDS` names the three kinds it applies to; `carry_after_answer`
is the rule, and it lives here rather than in the tail so the tail stays a caller. The
roster is carried UNCHANGED - the same frozen rows, the same `asked_at_turn` - because a
list whose numbering moved is a different list (`same_question`). It still clears by
every existing route: a newer question of another kind, a topic reset, a message naming
its own subject, the conversation closing.

**AND THE OFFER THE PICK PRODUCED RIDES ON IT** (D19 rule 3). A pick whose rerun misses
ends with "Would you like me to escalate to purchasing team?", which is a second thing on
the same screen and used to REPLACE the roster - the whole list, gone, for one yes/no.
`with_offer` merges it instead: the roster keeps its kind, its rows and its clock,
`expects` becomes `pick_or_yes_no`, and `payload.offer` carries the team and the one
option row the plain offer would have carried. A number re-picks, a yes escalates and
consumes the whole question, a no declines and leaves the roster with the offer taken off
it. One question, two answers, and the numbers still cannot collide because there is
still only one question open.

**WHICH rows, on a partial-miss turn.** Two rosters can be live at once and they are not
interchangeable: the numbered suggestions the reply printed, and the ANSWER's own rows
for the code that DID resolve. The lane that PRINTED the suggestions is the one that
freezes them onto the question, so the ambiguity is decided where the rows are, once, and
no reader downstream has to guess which of two lists a "2" is counting.

**A position means the row the customer SAW.** `options` is frozen when the question is
asked - uuid, code and label carried verbatim - and `resolve` indexes into it. It is never
re-resolved, and that is the whole point of freezing it: "2" must mean the second row the
customer read, not the second row a fresh lookup would return today (AC-944).

**Issue #708 rides on `payload.keep`.** A numbered pick over a partial-miss roster must
keep the siblings that already resolved, so the turn that answers "SRTKS6091 and SRTKS8091
got stock" with a picker for the second code still answers for the first. The already
resolved entities are frozen into the payload with the options, so the handler returns
them beside the pick rather than re-deriving which token was answered.

**No mirror, in either direction, as of L1-S3d.** The lanes compose the question with `ask`
at the moment they show the rows, the tail persists it, and the engine resolves against it.
The legacy keys it used to be derived from (`pending`, `selection_context`, `dym_offer`, the
two result sets) are not written and not read: migration `517_chatbot_session_5key` converted
every stored session on deploy, which is what let the derivation go rather than live forever
behind an "if the key is absent" branch.

Nothing here calls a model, opens a session or reads the customer's words.
"""
from __future__ import annotations

import re

from dataclasses import dataclass, field
from typing import Any

from app.services.chatbot import jsc
from app.services.chatbot.contracts import OPEN_QUESTION_KINDS

# What each kind expects by DEFAULT. A caller that knows better says so: a `team_pick`
# offering one team passes `expects="yes_no"`, which is the one-team escalate offer (D5).
KIND_SPEC: dict[str, dict[str, Any]] = {
    "product_pick": {"expects": "pick"},
    "customer_pick": {"expects": "pick"},
    "team_pick": {"expects": "pick"},
    "company_pick": {"expects": "pick"},
    "tier_pick": {"expects": "pick"},
    "member_offer": {"expects": "yes_no"},
    # The outstanding report's two numbered questions (merged from main, #862). They are
    # picks like the rest, and they are the two kinds this module ARMS but does not
    # RESOLVE: `head/output_exchange._apply_outstanding_pending` reads them, because a turn
    # taken under one of them has three readings - answered, refined, walked away from -
    # that a pick handler has no vocabulary for. `resolve` therefore has no handler for
    # either and returns an empty outcome, which is what leaves the head's reading standing.
    "outstanding_scope": {"expects": "pick"},
    "outstanding_detail": {"expects": "pick"},
}

# The kinds that are a NUMBERED LIST the customer can still see, and therefore the kinds
# a pick does not consume (D19). The other three are questions, not lists: a `team_pick`
# clarify and a `company_pick` are answered once and gone, and a `member_offer` is the
# arming pin on the CS-assign path, where re-arming it invisibly is how a later bare "yes"
# assigns a human to somebody who already declined (`tail/compile_state._picker_carry`).
ROSTER_KINDS = ("product_pick", "customer_pick", "tier_pick")

# The kinds this module ARMS but does not RESOLVE (see `KIND_SPEC` above): a turn taken
# under one of them has three readings - answered, refined, walked away from - that a pick
# handler has no vocabulary for, so `head/output_exchange._apply_outstanding_pending`
# reads the position instead and maps it to a SCOPE. Named here rather than repeated at
# each reader, because "who resolves this kind" is a fact about the kind.
#
# Their rows are MENU LABELS ("Sales orders", "Both", "Delivery order list"), not tokens,
# which is the second thing every reader has to know: minting an entity out of one sent
# "Delivery order list" to the resolver, where "list" matched six SPECIA-LIST customers
# and the report re-ran over companies nobody had named (R-B, then R-M on the other arm).
HEAD_RESOLVED_KINDS = ("outstanding_scope", "outstanding_detail")


# The three legacy JOIN MAPS are gone with `from_state` (L1-S3d step 4):
# `KIND_BY_SELECTION_CONTEXT`, `KIND_BY_PENDING_KIND` and `SELECTION_CONTEXT_BY_KIND`
# each translated between a kind and a key nothing writes or reads any more. The one
# place a legacy capture still has to be translated is the WORLD GRADER
# (`tests/chatbot/worlds.py`), and it carries its own map next to the corpus evidence
# that sized it.


@dataclass
class Outcome:
    """What the handler decided, in the vocabulary the rest of the turn already speaks.

    Every field is empty by default, so a handler sets only what its kind can produce and
    a reader never has to know which kind it came from.
    """

    handler: str = ""
    # Human words for the trace, composed from structured state and never from the
    # customer's own (D11).
    outcome: str = ""
    resolved: bool = False
    # The FROZEN rows the customer picked, verbatim.
    picked: list[dict[str, Any]] = field(default_factory=list)
    # Issue #708: siblings that already resolved and must survive the pick.
    keep: list[dict[str, Any]] = field(default_factory=list)
    # Focus writes, by slot name, for `dialogue/focus.py` to apply with source `pick`.
    focus: dict[str, Any] = field(default_factory=dict)
    escalate: bool = False
    declined: bool = False
    routing: dict[str, Any] = field(default_factory=dict)
    tiers: list[str] = field(default_factory=list)


def ask(
    kind: str,
    *,
    options: Any = None,
    turn_no: int,
    expects: str | None = None,
    domain: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """THE constructor. One function, so every kind is armed the same way.

    `options` are frozen HERE - the row list the customer is about to be shown, carried
    verbatim - because this is the only moment the answer and the rows are known to belong
    together. Anything asked for later is a fresh lookup, and a fresh lookup is what makes
    "2" mean a different product than the one on the screen.

    `idx` is assigned here and nowhere else, from 1, ACROSS THE WHOLE ROSTER (AC-1013): one
    question is open at a time, so "1" can only ever mean one row, and the numbering the
    customer reads is the numbering the resolver indexes.

    `domain` stamps the rows that do not carry one of their own, so a pick knows which
    domain it is answering for once lane 2 fans a turn out over several.
    """
    if kind not in OPEN_QUESTION_KINDS:
        raise ValueError(f"unknown open question kind {kind!r}")
    spec = KIND_SPEC[kind]
    return {
        "kind": kind,
        "options": _freeze(options, domain=domain),
        "expects": expects or spec["expects"],
        "asked_at_turn": int(turn_no),
        "asked_at": None,
        "payload": dict(payload or {}),
    }


def same_question(a: Any, b: Any) -> bool:
    """Is this the same question the previous turn left open, or a fresh one?

    Same KIND and the same option IDENTITIES, in the same order. The identity of a row is
    its uuid where it has one and its code or label where it does not, because those are
    what a customer can point at; `idx` is deliberately not in it, since a roster whose
    numbering is identical and whose contents changed is a DIFFERENT list.

    This is what gives an open question a real lifetime. `compile_state` re-derives the
    mirror on every turn, so stamping `asked_at_turn` each time would make the age
    permanently 1 and the TTL unreachable - which is the same class of defect the focus
    projection had, in the other half of the dialogue state.
    """
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False
    if a.get("kind") != b.get("kind"):
        return False
    return _identities(a.get("options")) == _identities(b.get("options"))


def _identities(options: Any) -> list[str]:
    out: list[str] = []
    for row in jsc.array(options):
        if not isinstance(row, dict):
            continue
        out.append(
            jsc.nullish_str(
                row.get("uuid")
                or row.get("code")
                or row.get("team")
                or row.get("value")
                or row.get("label")
            )
            .strip()
            .lower()
        )
    return out


def carry_after_answer(
    question: Any, outcome_handler: Any, answer: Any = None
) -> dict[str, Any] | None:
    """What is left open AFTER the customer answered - the whole of ruling D19.

    THE RULE, and it is three lines because it is three cases:

    * a ROSTER survives its own pick, unchanged, with any spent offer taken off it. The
      list is still on the customer's screen and the numbers still mean what they were
      printed to mean; a rerun that produces a NEW offer merges it back on through
      `with_offer`, which is why the spent one comes off here rather than being left to
      go stale.
    * a roster whose riding offer was ACCEPTED is consumed whole. The escalation lane
      runs, a human has the conversation, and a numbered list of products is not what the
      customer is looking at any more.
    * every other kind is consumed by being answered, exactly as before. A `team_pick`
      clarify, a `company_pick` and a `member_offer` are questions rather than lists, and
      the member offer in particular must never be re-armed by a carry (the hazard is
      written out on `tail/compile_state._picker_carry`: a later bare "yes" assigns a
      human to somebody who already declined).

    `answer` is the normalised `answers_open_question` the handler saw. Only its `yes_no`
    is read, and only to tell an accepted offer from a declined one.
    """
    if not isinstance(question, dict) or question.get("kind") not in ROSTER_KINDS:
        return None
    # `team_pick` OVER A ROSTER KIND CAN ONLY BE THE RIDING OFFER, and that holds because
    # `team_pick` is not in `ROSTER_KINDS`: the line above has already returned for a
    # question that IS a team_pick, so a team_pick HANDLER here means `resolve` dispatched
    # to it through `payload.offer` (D19 rule 3) rather than on the question's own kind.
    if outcome_handler == "team_pick" and (answer or {}).get("yes_no") == "yes":
        return None
    payload = {
        key: value
        for key, value in (question.get("payload") or {}).items()
        if key != "offer"
    }
    return {**question, "expects": "pick", "payload": payload}


#: The one sentence an escalate offer is made with - the frozen phrase `tail/compose`,
#: `offer_is_open` and the miss-company arm all hold. `team_from_reply` reads the promised
#: team back off it.
ESCALATE_PREFIX = "Would you like me to escalate to"
#: EVERY composer's OFFERING sentence, and the offer clause is part of the PATTERN rather
#: than a separate presence test (security review S1 + its end-to-end half, 15 Sep 2026): a
#: reply can carry BOTH a quoted customer token and a real offer - `Couldn't find these:
#: "escalate to purchasing." (product): not found.` above `Would you like me to escalate to
#: customer service team?` - and a bare "escalate to" search finds the echo first, so the
#: question recorded a team the reply never promised. Anchored on the clause that offers,
#: the first match IS the promise.
#: `compile_state`'s two miss arms and
#: `compose.crossdomain_compose` write the frozen prefix; `lanes/business/answer.py` writes
#: a lower-case "would you like me to escalate to X team?" on one arm and "Reply a number to
#: pick, or 'yes' to escalate to X." on another; and the miss-company arm inserts a BOLD
#: company ("escalate to *Sorento* customer service team?"). The offer must be recognised
#: from all of them (owner rule 1, tester 2's generality catch), so the anchor is the two
#: words that never vary - "escalate to" - and the team is whatever follows up to the end of
#: the sentence. Over-capture is harmless: `team_from_reply` only accepts a span that
#: reduces to a real catalogue team.
_ESCALATE_TEAM_RE = re.compile(
    r"(?:would you like me to escalate to|'yes' to escalate to)"
    r"\s+(?P<team>[^.?!\n]+?)(?:\s+team)?\s*[.?!]",
    re.IGNORECASE,
)


def team_from_reply(reply_text: Any) -> str | None:
    """The team a reply's offering sentence NAMES - the PARITY reader, not the source.

    **Not the source any more** (owner ruling, 15 Sep 2026, review S-1 / S-2). It was: the
    printed sentence and the recorded offer used to be derived separately - the text from
    `roster_plan[0].team` / `qf.routing.suggested_team` in `_miss_company_routing`, the
    record from `_escalation_team`, which prefers `gate.company_team` - so a reply could
    promise one team while the stored offer routed to another, and reading the team back
    off the final text closed that gap. Then the text turned out to be unreadable as a
    source at all: the customer's own token is echoed into the same reply by `raw_of_tok`
    and `_partial_dym_block`, it can carry the whole offering clause ("would you like me to
    escalate to purchasing team."), and it lands either side of the bot's own sentence - so
    neither the first nor the last "escalate to" in the text is reliably the promise. The
    offer is now recorded by the composer that PRINTS it (`answer._offering`, the two miss
    arms' `turn_state["offer_team"]`, `crossdomain_compose`'s own offer), and this function
    is what the tests compare printed against recorded with.

    **Echo-only safety no longer rests on this returning None** (S-3). It returns None for
    an echo that never reduces to a catalogue team, and it does NOT for an echo that quotes
    a real team back (one of the three measured tokens did, two did not). What makes an
    echo harmless is that nothing is recorded unless a composer says it printed an offer -
    by construction, not by this reader's luck.

    It parses the BOT's own frozen sentence, never the customer's words, so it is not the
    word-list-over-customer-text D11 forbids. Display form is `_prettyTeam`'s (underscores
    to spaces) so the reverse is spaces to underscores, and a COMPANY may sit in front of
    the team ("escalate to Mocha warehouse team?"), so leading words are dropped one at a
    time until what remains is a real catalogue team. No company list, and nothing invented:
    an unmatched phrase returns None.
    """
    text = jsc.js_string(reply_text or "")
    # THE LAST MATCH, not the first. Every composer appends its offering clause at the END,
    # so where a reply carries both an echoed token and the bot's own sentence the last span
    # that reduces to a catalogue team is the bot's. Measured on three live tokens
    # (`escalate to purchasing.`, `or 'yes' to escalate to warehouse.`, `would you like me
    # to escalate to purchasing team.`) quoted back above a real customer-service offer.
    match = None
    for candidate in _ESCALATE_TEAM_RE.finditer(text):
        if _catalogue_team(candidate.group("team")) is not None:
            match = candidate
    if match is None:
        return None
    # Bold markers come off (the company insert is written `*Sorento*`), then leading words
    # are dropped one at a time until what remains is a real catalogue team - which is how a
    # company prefix, a lower-case composer and the "or 'yes' to escalate to X." shape all
    # read the same without a list of companies or a list of sentences.
    return _catalogue_team(match.group("team"))


def _catalogue_team(span: Any) -> str | None:
    """A captured span reduced to a real catalogue team, or None.

    Bold markers come off (the company insert is written `*Sorento*`), then leading words
    are dropped one at a time until what remains is a `SUGGESTED_TEAMS` member - which is
    how a company prefix, a lower-case composer and the "or 'yes' to escalate to X." shape
    all read the same without a list of companies or a list of sentences. Nothing is
    invented: a span that never reduces returns None, and that is what makes taking the
    LAST matching span safe.
    """
    from app.services.chatbot.contracts import SUGGESTED_TEAMS

    words = [w for w in jsc.js_string(span or "").replace("*", " ").strip().lower().split() if w]
    for start in range(len(words)):
        team = "_".join(words[start:])
        if team in SUGGESTED_TEAMS:
            return team
    return None


def record_offer(
    question: Any,
    *,
    turn_no: int,
    team: Any = None,
    reply_text: Any = None,
    domain: Any = None,
) -> Any:
    """THE escalate offer, recorded on whatever question the turn leaves open. ONE RULE,
    ONE IMPLEMENTATION (owner ruling, 15 Sep 2026: "our fix needs to be general and not
    targeted to 1 scenario only").

    The rule: *an offer exists when the outgoing reply carries the frozen sentence and
    names a real team; it is recorded on the question that turn leaves open, from one team
    source.* No arm conditions - the caller does not say which shape it is, and there is
    nothing here that knows about did-you-mean, pickers, ladders or fan sections.

    Three tail arms and one engine arm used to try, each with its own conditions and its own
    team, and between them they covered the shapes somebody had hit: a hit with a
    cross-domain ladder armed nothing a "yes" could answer (R-I, owner turn
    cca6b365 -> 570610f0), which is what proved the per-arm approach wrong.

    **Called TWICE, because the reply is composed in two stages.** The tail composes the
    answer and `crossdomain_compose` may then append the escalate sentence, so the text is
    final at two different moments and a single call at either one is blind to the other.
    `with_offer` is idempotent by construction (a second offer REPLACES `payload.offer`
    rather than nesting), so the second call over the same question is a no-op when the
    sentence has not changed and an update when it has. One rule, one implementation, one
    team source, two invocations.

    What rides and what does not: a ROSTER takes the offer on board (D19 rule 3 - it keeps
    its kind, its rows and its clock and gains a yes and a no); NO question at all becomes
    the plain one-team yes/no (D5); and any OTHER question the turn armed is left exactly as
    it is, because a team clarify, a company clarify or a member offer is already what the
    customer is being asked and the escalate yes/no has nothing to add to it.

    **`team` IS THE SOURCE, and it comes from whoever PRINTED the sentence** (owner ruling,
    15 Sep 2026, review S-1 / S-2). It used to be read back out of `reply_text`, which
    cannot be done safely: the customer's own token is echoed into the same reply
    (`raw_of_tok`, `_partial_dym_block`) and lands either side of the bot's sentence, so
    neither the first nor the last "escalate to" in the text is reliably the promise.
    `team_from_reply` survives as the PARITY reader the tests compare printed against
    recorded with, and `reply_text` here is the direct-unit-call shape that uses it; no
    production caller passes it, and there is deliberately no text fallback for one that
    forgets the team - a composer that prints without recording un-arms its own offer,
    which is what the per-composer parity tests exist to catch loudly.
    """
    if not jsc.truthy(team):
        team = team_from_reply(reply_text)
    if not jsc.truthy(team):
        return question
    if isinstance(question, dict) and question.get("kind") and question.get("kind") not in ROSTER_KINDS:
        return question
    offer = ask(
        "team_pick",
        options=[{"idx": 1, "team": team, "label": team}],
        turn_no=turn_no,
        expects="yes_no",
        domain=jsc.js_string(domain) if jsc.truthy(domain) else None,
        payload={"team": team, "domain": domain},
    )
    if isinstance(question, dict) and question.get("kind") in ROSTER_KINDS:
        return with_offer(question, offer)
    return offer


def with_offer(roster: Any, offer_question: Any) -> dict[str, Any]:
    """The one-team escalate offer, merged ONTO the roster instead of over it (D19 r3).

    The roster wins every field that says WHICH QUESTION THIS IS - kind, options,
    `asked_at_turn` - because it is the same question it was before the offer arrived, and
    re-stamping the clock would say the bot asked for the list again when it did not. The
    offer contributes exactly what answering it needs: the team, the domain it was made
    about, and the single option row `_ask_for_turn` builds for the plain offer, so a
    customer who reads the numbered offer row and types "1" is not silently re-picking a
    product instead.

    Idempotent by construction: a second offer on the same roster REPLACES `payload.offer`
    rather than nesting, so the team the customer is being asked about is always this
    turn's.

    THE OFFER RECORDS ITS DOMAIN ONCE, on the offer and not again on every row. `ask`
    stamps the question's domain onto rows that carry none, which is right for a roster
    assembled across domains and pure duplication for an offer of one team; and a second
    copy of a fact is a second thing that can disagree with the first.
    """
    if not isinstance(roster, dict):
        return roster
    offer_payload = jsc.get(offer_question, "payload")
    offer_payload = offer_payload if isinstance(offer_payload, dict) else {}
    offer = {
        "team": offer_payload.get("team"),
        "domain": offer_payload.get("domain"),
        "options": [
            {key: value for key, value in row.items() if key != "domain"}
            for row in _freeze(jsc.get(offer_question, "options"))
        ],
    }
    return {
        **roster,
        "expects": "pick_or_yes_no",
        "payload": {**(roster.get("payload") or {}), "offer": offer},
    }


# `from_state` is DELETED (L1-S3d step 4). It derived the open question from the legacy
# session keys - `pending`, `selection_context`, `dym_offer`, the two result sets - for the
# release in which both shapes existed. Migration `517_chatbot_session_5key` converted every
# stored session on deploy, so there is no legacy shape left to read and the DIRECTION of the
# mirror stops being a question: the lanes compose the question with `ask` and the tail
# persists it.

def resolve(
    kind: str,
    answer: dict[str, Any],
    options: Any = None,
    payload: dict[str, Any] | None = None,
) -> Outcome:
    """One dispatcher, one handler per kind. Never a default and never a guess.

    `answer` is `output_exchange.v3_signals(...)["answers_open_question"]`, already
    normalised: `picks` is a list of positive 1-based integers and `yes_no` is exactly
    `"yes"`, `"no"` or None. An unknown kind returns an unresolved outcome rather than
    raising: the question came out of a customer's stored session, and a session written by
    a build this one does not know must not fail the turn.

    **`payload.offer` is the second answer** (D19). A roster with an escalate offer riding
    on it takes a NUMBER as a pick and a YES or NO as the answer to the offer, so the
    dispatch asks what the customer said before it asks what kind the question is. A
    number wins: it is unambiguous, and the roster is what the number was printed against.
    A yes or no on a roster with NO offer resolves nothing at all - there is nothing on
    that screen to say yes to - and the question stays open.
    """
    answer = answer or {}
    payload = dict(payload or {})
    offer = payload.get("offer")
    if (
        isinstance(offer, dict)
        and not (answer.get("picks") or [])
        and answer.get("yes_no") in ("yes", "no")
    ):
        # The offer's OWN row and the offer's OWN team, because `_team_pick` reads both:
        # the roster's options are products, and `payload.team` is what a yes assigns.
        return _team_pick(
            answer,
            _freeze(offer.get("options")),
            {**payload, "team": offer.get("team"), "domain": offer.get("domain")},
        )
    handler = _HANDLERS.get(kind)
    if handler is None:
        return Outcome(handler="unknown", outcome=f"No handler for {kind!r}.")
    return _apply_keep(handler(answer, _freeze(options), payload), payload)


def _apply_keep(outcome: Outcome, payload: dict) -> Outcome:
    """Issue #708's siblings, re-applied to EVERY resolved pick - one site (owner ruling,
    15 Sep 2026: "our fix needs to be general and not targeted to 1 scenario only").

    `payload.keep` is what the turn that armed the question had already resolved beside the
    ambiguous word (`gate.keep_entities`). It used to be applied inside `_product_pick` and
    then, for R-C, inside `_customer_pick` - two copies, and every other kind silently
    without it, so a sibling survived a product pick and died on a tier pick for no reason
    anybody chose. Applied here instead, after whichever handler ran, so the rule arrives
    with the dispatcher and no kind can be forgotten.

    Dropped from `keep`: anything the pick itself already produced, by code, so the same
    subject is never stated twice. A kept PRODUCT also joins `focus.products`, because that
    is its axis and the re-run has to be scoped by it; a sibling with no axis (an
    `attachment_type`) travels on `keep` alone, which
    `output_exchange.apply_open_question_outcome` puts back on the emission.
    """
    if not outcome.resolved:
        return outcome
    produced = [e for e in outcome.focus.values() if isinstance(e, dict)]
    produced += [
        e
        for value in outcome.focus.values()
        if isinstance(value, list)
        for e in value
        if isinstance(e, dict)
    ]
    keep = [
        e
        for e in payload.get("keep") or []
        if isinstance(e, dict) and not _same_code(e, produced)
    ]
    if not keep:
        return outcome
    outcome.keep = keep
    products = [e for e in keep if _is_product(e)]
    if products:
        existing = outcome.focus.get("products")
        existing = [e for e in existing if isinstance(e, dict)] if isinstance(existing, list) else []
        outcome.focus = {**outcome.focus, "products": existing + products}
    return outcome


# --------------------------------------------------------------------------- #
# The seven handlers
# --------------------------------------------------------------------------- #


def _product_pick(answer: dict, options: list, payload: dict) -> Outcome:
    picked = _rows_for(answer.get("picks"), options)
    if not picked:
        return Outcome(handler="product_pick", outcome="No offered row was named.")
    entities = [_entity_of(row, "product") for row in picked]
    # `payload.keep` is applied ONCE, in `resolve` - see `_apply_keep`. Issue #708's rule
    # belongs to every kind, not to the two handlers that happened to need it first.
    return Outcome(
        handler="product_pick",
        outcome=f"Picked {', '.join(_label_of(r) for r in picked)}.",
        resolved=True,
        picked=picked,
        focus={"products": entities},
    )


def _customer_pick(answer: dict, options: list, payload: dict) -> Outcome:
    picked = _rows_for(answer.get("picks"), options)
    if not picked:
        return Outcome(handler="customer_pick", outcome="No offered row was named.")
    return Outcome(
        handler="customer_pick",
        outcome=f"Picked customer {_label_of(picked[0])}.",
        resolved=True,
        picked=picked[:1],
        focus={"customer": _entity_of(picked[0], "customer")},
    )


def _team_pick(answer: dict, options: list, payload: dict) -> Outcome:
    """The escalate offer, whether it named one team or several (D5, AC-1051).

    ONE handler for both shapes, and the order of the two arms is the whole of it: a
    NUMBERED reply is a pick, and a bare yes or no answers the one-team offer. A yes on a
    two-team offer resolves nothing here - `expects` is `pick` there, the customer has not
    said which team, and the lane re-asks with the same buttons rather than guessing one.
    """
    picked = _rows_for(answer.get("picks"), options)
    if picked:
        row = picked[0]
        team = row.get("team") or row.get("value") or row.get("code")
        return Outcome(
            handler="team_pick",
            outcome=f"Routed to {team}.",
            resolved=True,
            picked=[row],
            escalate=True,
            routing={"suggested_team": team},
        )

    one_team = options[0] if len(options) == 1 and isinstance(options[0], dict) else None
    if answer.get("yes_no") == "yes" and one_team is not None:
        team = one_team.get("team") or one_team.get("value") or one_team.get("code")
        return Outcome(
            handler="team_pick",
            outcome="The customer accepted the escalation.",
            resolved=True,
            picked=[one_team],
            escalate=True,
            routing={"suggested_team": team or payload.get("team")},
        )
    if answer.get("yes_no") == "yes":
        # An offer with no roster at all is the legacy marker's shape: the team rides the
        # payload, and the customer said yes to the only thing on offer.
        return Outcome(
            handler="team_pick",
            outcome="The customer accepted the escalation.",
            resolved=True,
            escalate=True,
            routing={"suggested_team": payload.get("team")},
        )
    if answer.get("yes_no") == "no":
        return Outcome(
            handler="team_pick",
            outcome="The customer declined the escalation.",
            resolved=True,
            declined=True,
        )
    # AC-945 / AC-1020: neither accepted nor declined LEAVES IT OPEN. It is not answered by
    # a stock question that happened to arrive next; `clearing.apply` clears it, with a
    # trace line, on the turn the customer asks something else instead.
    return Outcome(handler="team_pick", outcome="No offered team was named.")


def _company_pick(answer: dict, options: list, payload: dict) -> Outcome:
    picked = _rows_for(answer.get("picks"), options)
    if not picked:
        return Outcome(handler="company_pick", outcome="No offered company was named.")
    row = picked[0]
    return Outcome(
        handler="company_pick",
        outcome=f"Routed to {_label_of(row)}.",
        resolved=True,
        picked=[row],
        escalate=True,
        routing={
            "company_pick": row.get("company_name") or row.get("label") or row.get("value"),
            "company_id": row.get("company_id") or row.get("uuid"),
        },
    )


def _tier_pick(answer: dict, options: list, payload: dict) -> Outcome:
    picked = _rows_for(answer.get("picks"), options)
    if not picked:
        return Outcome(handler="tier_pick", outcome="No offered tier was named.")
    tiers = [
        jsc.nullish_str(row.get("tier") or row.get("value") or row.get("label")).strip().lower()
        for row in picked
    ]
    tiers = [t for t in tiers if t]
    return Outcome(
        handler="tier_pick",
        outcome=f"Picked tier {', '.join(tiers)}.",
        resolved=True,
        picked=picked,
        tiers=tiers,
        focus={"tier": tiers},
    )


def _member_offer(answer: dict, options: list, payload: dict) -> Outcome:
    """Yes or no, and a POSITION also counts: the roster is on the screen beside the offer.

    That is not a widening for its own sake - `expects` is `yes_no` because a bare "yes"
    is the common answer, and the rows are numbered in the reply the customer is looking
    at, so a bare "2" is an answer to the same question. Anything else leaves it open.
    """
    picked = _rows_for(answer.get("picks"), options)
    if picked:
        row = picked[0]
        return Outcome(
            handler="member_offer",
            outcome=f"Picked {_label_of(row)} from the roster.",
            resolved=True,
            picked=[row],
            escalate=True,
            routing={
                "preferred_assignee_id": row.get("uuid") or row.get("user_id"),
                "company_id": row.get("company_id"),
            },
        )
    if answer.get("yes_no") == "yes":
        return Outcome(
            handler="member_offer",
            outcome="The customer accepted, with nobody named.",
            resolved=True,
            escalate=True,
            routing={"suggested_team": payload.get("team")},
        )
    if answer.get("yes_no") == "no":
        return Outcome(
            handler="member_offer",
            outcome="The customer declined the offer.",
            resolved=True,
            declined=True,
        )
    return Outcome(handler="member_offer", outcome="Neither a pick nor a yes or no.")


_HANDLERS = {
    "product_pick": _product_pick,
    "customer_pick": _customer_pick,
    "team_pick": _team_pick,
    "company_pick": _company_pick,
    "tier_pick": _tier_pick,
    "member_offer": _member_offer,
}


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #


def _freeze(options: Any, *, domain: str | None = None) -> list[dict[str, Any]]:
    """The rows, numbered as the customer saw them, each stamped with its domain.

    `idx` is taken from the row when it has one (every roster the lanes build stamps it)
    and supplied by position when it does not, so a position always resolves against the
    number that was printed.

    A row's OWN `domain` wins over the question's: a roster assembled across two domains
    already knows which row came from where, and the question-level value is the default
    for the rows that do not say.
    """
    frozen: list[dict[str, Any]] = []
    for position, row in enumerate(jsc.array(options), start=1):
        if not isinstance(row, dict):
            continue
        if domain is not None and row.get("domain") is None:
            row = {**row, "domain": domain}
        # `js_number(None)` is 0, which `is_integer` accepts, so "has no number" and
        # "is numbered zero" would read the same and every row would collapse onto 0.
        # A printed number is 1-based, so anything below 1 is an absent one.
        idx = jsc.js_number(row.get("idx"))
        numbered = jsc.is_integer(idx) and idx >= 1
        frozen.append({**row, "idx": int(idx) if numbered else position})
    return frozen


def _rows_for(picks: Any, options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The frozen rows those positions name. An out-of-range position is NOT a pick.

    Never re-resolved and never guessed at: a customer who typed a number the list did not
    show has not chosen anything, and answering for the nearest row would be worse than
    asking again.
    """
    by_idx = {int(row["idx"]): row for row in options if isinstance(row.get("idx"), int)}
    return [by_idx[p] for p in (picks or []) if p in by_idx]


def _entity_of(row: dict[str, Any], hint: str) -> dict[str, Any]:
    """A frozen row as an ENTITY, carrying the row's own uuid and code verbatim.

    `current_message: True` because the customer chose it on this turn, and `confident:
    True` because they chose it from rows we showed them - there is nothing left to be
    unsure about.

    **A CUSTOMER's `raw` is the LABEL, not the code** (R-E, owner merge test 15 Sep 2026).
    `raw` is what every renderer prints - the "Customer:" scope header reads it - and a
    customer row's code is a synthetic debtor id, so a picked row printed `Customer:
    300-C043` while the miss copy two lines below named the company correctly. The rule is
    already written down one layer in, at `gate.py`'s pin re-seat: "A picked customer's
    canonical_code is often a synthetic debtor id, which the miss/answer renderers print
    verbatim. The entity's raw IS the roster label we showed; products keep their canonical
    code." Main's own spine agreed - capture
    `nodes/clone-spine-RS/compile-current-state/b56-pick-turn.json` carries `{"raw": "CHIN
    CHUN HARDWARE SDN BHD", "canonical_code": "300-C043"}` for this exact pick. Products
    are untouched: there the code IS the name the customer reads.

    `family_uuids` rides along when the row has one (R-F): the ACCOUNT FAMILY a roster line
    stands for, so the report reaches every ledger the line promised. It lives on the pin
    rather than on the question because the captain's 2026-08-24 ruling is that the family
    outlives the roster - the pin does, and `focus.customer` carries it for as long as the
    customer keeps talking about that company.
    """
    code = row.get("code") or row.get("value") or row.get("product") or row.get("label")
    kind = row.get("entity_type") or hint
    label = row.get("label") or row.get("title")
    entity = {
        "raw": (label or code) if jsc.lower_or_empty(kind) == "customer" else code,
        "hint": kind,
        "canonical_code": code,
        "uuid": row.get("uuid") or None,
        "ordinal": row.get("idx"),
        "current_message": True,
        "confident": True,
    }
    # CUSTOMER rows only (security review n2, 15 Sep 2026). An account family is a fact
    # about a customer - `gate.run_gate` computes it from `_cust_base` over customer
    # matches, and `entity_ids_transformer` expands it into `customer_ids` - so copying the
    # key off any row that happened to carry one would hand an unowned list to a type that
    # has no notion of a family.
    family = row.get("family_uuids")
    if jsc.lower_or_empty(kind) == "customer" and isinstance(family, list) and len(family) > 0:
        entity["family_uuids"] = list(family)
    return entity


def _label_of(row: dict[str, Any]) -> str:
    return jsc.js_string(row.get("label") or row.get("code") or row.get("value") or "")


def _is_product(entity: Any) -> bool:
    return isinstance(entity, dict) and jsc.lower_or_empty(entity.get("hint")) == "product"


def _same_code(entity: dict[str, Any], picked: list[dict[str, Any]]) -> bool:
    key = _code_key(entity)
    return bool(key) and any(_code_key(p) == key for p in picked)


def _code_key(entity: Any) -> str:
    if not isinstance(entity, dict):
        return ""
    return jsc.nullish_str(entity.get("canonical_code") or entity.get("raw")).strip().lower()


# `_roster_of`, `_siblings_to_keep` and `_prior_entities` are DELETED with `from_state`
# (L1-S3d step 4). They each read a legacy roster key off the stored session -
# `last_result_set`, `dym_last_result_set`, `dym_offer.candidates`, `entities` - to work
# out which rows the customer was looking at and which siblings a pick must keep. The
# rows are FROZEN onto the question now, by the lane that printed them, and the #708
# keep list is frozen with them (`lanes/business/run_miss_lane._attach_question`), so
# there is nothing left to reconstruct.


def _rows_are_customers(rows: list[dict[str, Any]]) -> bool:
    return bool(rows) and all(
        jsc.lower_or_empty(r.get("entity_type")) == "customer" for r in rows
    )
