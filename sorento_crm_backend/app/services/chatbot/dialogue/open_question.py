"""The ONE thing the bot can be waiting for, and the one place an answer is resolved.

Growth r1 slice B4 (AC-944, AC-945, AC-947, AC-948, D7). Seven kinds, one table, one
handler each, and a dispatcher that never guesses:

| kind             | expects | options                          | outcome                       |
|------------------|---------|----------------------------------|-------------------------------|
| `product_pick`   | pick    | frozen rows: uuid, code, label   | focus.products, source `pick` |
| `customer_pick`  | pick    | family rows with company codes   | focus.customer                |
| `escalate_yes_no`| yes_no  | none                             | yes: escalate; no: declined   |
| `team_pick`      | pick    | the teams the ask OFFERED        | routing set, escalation on    |
| `company_pick`   | pick    | the ledgers the ask offered      | routing set, escalation on    |
| `tier_pick`      | pick    | tiers                            | focus.tier, promotion rerun   |
| `member_offer`   | yes_no  | family members                   | yes: business lane over them  |

**WHICH rows, on a partial-miss turn.** Two rosters can be live at once and they are not
interchangeable: the numbered suggestions the reply printed are `dym_last_result_set` and
`last_result_set` holds the ANSWER's own rows for the code that DID resolve. `_roster_of`
picks the one the legacy ladder resolves numbered picks against, by the same
discriminator.

**A position means the row the customer SAW.** `options` is frozen when the question is
asked - uuid, code and label carried verbatim - and `resolve` indexes into it. It is never
re-resolved, and that is the whole point of freezing it: "2" must mean the second row the
customer read, not the second row a fresh lookup would return today (AC-944).

**Issue #708 rides on `payload.keep`.** A numbered pick over a partial-miss roster must
keep the siblings that already resolved, so the turn that answers "SRTKS6091 and SRTKS8091
got stock" with a picker for the second code still answers for the first. The already
resolved entities are frozen into the payload with the options, so the handler returns
them beside the pick rather than re-deriving which token was answered.

**Direction of the mirror, stated because it is a deviation.** The plan asks for
`open_question` to be authoritative and the old keys (`pending`, `dym_offer`,
`selection_context`, `picker_*`) to be derived from it. It is derived from THEM for this
release, by `from_state` below, and the reason is written into the code that would have to
be rewritten: `tail/compile_state.py`'s did-you-mean lifecycle is a faithful port of the
n8n rule whose "eight-rule order is graded against captures", and `topic.py` says in as
many words that "rewriting it to call this function would be a behaviour change smuggled
in as a tidy-up". Thirteen registered divergences already pin that ladder. So this slice
takes the half that changes behaviour where the ACs ask for it - the typed slot, the
frozen options, one resolver, the trace - and leaves the ladder authoritative until it can
be replaced against a re-derived corpus. AC-951's stated purpose ("so every existing world
grades") is met either way; its letter is not, and the plan and the UAC are updated in the
same change.

Nothing here calls a model, opens a session or reads the customer's words.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.chatbot import jsc
from app.services.chatbot.contracts import OPEN_QUESTION_KINDS

# What each kind expects, and how many turns it stays on the customer's screen.
#
# The TTLs are not one number, and that is why they ride on the question rather than on a
# settings column. A member offer lives 3 turns (owner ruling, AC-816 rule 1: an offer is
# what is on the customer's screen, and a "yes" about something else twenty turns later
# once assigned a human off an offer nobody had answered). A did-you-mean roster lives 3
# for the same reason. A clarify is answered on the very next turn or not at all - it is a
# QUESTION, not a roster, and `compile_state` says why carrying one indefinitely masked
# every later offer.
KIND_SPEC: dict[str, dict[str, Any]] = {
    "product_pick": {"expects": "pick", "ttl_turns": 3},
    "customer_pick": {"expects": "pick", "ttl_turns": 3},
    "escalate_yes_no": {"expects": "yes_no", "ttl_turns": 1},
    "team_pick": {"expects": "pick", "ttl_turns": 1},
    "company_pick": {"expects": "pick", "ttl_turns": 1},
    "tier_pick": {"expects": "pick", "ttl_turns": 1},
    "member_offer": {"expects": "yes_no", "ttl_turns": 3},
}

# `selection_context` (and, with none, the `pending` marker) says WHICH question the last
# turn left open. One map, so a kind added to either vocabulary has exactly one place to
# be joined up.
KIND_BY_SELECTION_CONTEXT: dict[str, str] = {
    "disambiguation": "product_pick",
    "suggest_offer": "product_pick",
    "member_offer": "member_offer",
    "tier_offer": "tier_pick",
    "team_clarify": "team_pick",
    "company_clarify": "company_pick",
}
KIND_BY_PENDING_KIND: dict[str, str] = {
    "escalation_offer": "escalate_yes_no",
    "member_offer": "member_offer",
    "team_clarify": "team_pick",
    "company_clarify": "company_pick",
    "tier_ask": "tier_pick",
}
SELECTION_CONTEXT_BY_KIND: dict[str, str] = {
    "product_pick": "disambiguation",
    "customer_pick": "disambiguation",
    "member_offer": "member_offer",
    "tier_pick": "tier_offer",
    "team_pick": "team_clarify",
    "company_pick": "company_clarify",
}


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
    ttl_turns: int | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """THE constructor. One function, so every kind is armed the same way.

    `options` are frozen HERE - the row list the customer is about to be shown, carried
    verbatim - because this is the only moment the answer and the rows are known to belong
    together. Anything asked for later is a fresh lookup, and a fresh lookup is what makes
    "2" mean a different product than the one on the screen.
    """
    if kind not in OPEN_QUESTION_KINDS:
        raise ValueError(f"unknown open question kind {kind!r}")
    spec = KIND_SPEC[kind]
    return {
        "kind": kind,
        "options": _freeze(options),
        "expects": expects or spec["expects"],
        "asked_at_turn": int(turn_no),
        "ttl_turns": int(spec["ttl_turns"] if ttl_turns is None else ttl_turns),
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


def from_state(
    variables: Any,
    *,
    asked_at_turn: int,
    previous: Any = None,
    answered: bool = False,
) -> dict[str, Any] | None:
    """The MIRROR: the open question the legacy session keys describe.

    `selection_context` says which roster is on screen and `last_result_set` is that
    roster; with neither, the `pending` marker still says an escalation offer is open. Both
    are what the lifecycle in `tail/compile_state.py` decided, so this reads its answer
    rather than second-guessing it (see the module docstring for why that direction).

    **A PRESENT `open_question` key wins, `None` included.** `decay` has already run by the
    time a reader calls this, and it writes the key explicitly - so `None` means "it was
    there and it aged out", and falling through to the derivation would resurrect the very
    question that was just cleared. Only an ABSENT key means "this session predates the
    slot", and that is the one case the legacy keys answer.
    """
    stored = variables if isinstance(variables, dict) else {}
    if "open_question" in stored:
        existing = stored.get("open_question")
        if isinstance(existing, dict) and existing.get("kind") in OPEN_QUESTION_KINDS:
            return existing
        return None

    at = max(0, int(asked_at_turn))
    context = jsc.nullish_str(stored.get("selection_context") or "")
    rows = _roster_of(stored, context)
    pending = stored.get("pending") if isinstance(stored.get("pending"), dict) else {}
    dym_offer = stored.get("dym_offer") if isinstance(stored.get("dym_offer"), dict) else {}

    kind = KIND_BY_SELECTION_CONTEXT.get(context)
    if kind == "product_pick" and _rows_are_customers(rows):
        # The same roster label carries both, and the difference is what the pick SETS.
        kind = "customer_pick"
    if kind is None:
        kind = KIND_BY_PENDING_KIND.get(jsc.nullish_str(pending.get("kind") or ""))
    if kind is None:
        # THE QUESTION OUTLIVES THE LEGACY MARKER, and that is what makes its TTL real.
        # `pending.derive` re-emits an escalation offer only on the turn a lane offers one,
        # so a customer who asks something else instead would otherwise have the question
        # vanish on the very next turn - answered by nothing, cleared by nothing, and never
        # traced. AC-945 is explicit that an unanswered offer survives to its TTL and is
        # then cleared with a `decay` line, so it is carried here and killed by `decay`,
        # which is the one place that ages anything (D11).
        #
        # NOT carried once it has been ANSWERED: the handler consumed it this turn, and
        # re-arming a question the customer has already replied to is the hazard
        # `_picker_carry` names - a later bare "yes" assigning a human off an offer that
        # was closed. Nor is it carried when the legacy keys describe a different question,
        # because that branch returned above.
        return None if answered else (previous if isinstance(previous, dict) else None)

    ttl = pending.get("ttl") if kind == "member_offer" else None
    payload = {
        "domain": stored.get("domain_hint"),
        "team": pending.get("team"),
        # ISSUE #708: the siblings that already resolved, and ONLY when the offer records
        # which token it was made FOR. `dym_offer.candidates` carries `for_raw` /
        # `for_canonical` on exactly the partial-miss turns the issue is about, and without
        # that linkage there is nothing that says which token the pick answers - so a keep
        # list would be a guess, and the guess is what puts the very token the picker was
        # disambiguating back into scope beside its own answer. `head/output_exchange`'s
        # own #708 block draws the same line and says so at more length.
        "keep": _siblings_to_keep(stored, context, dym_offer),
    }
    if dym_offer:
        payload["offer_id"] = dym_offer.get("id")
        payload["picked"] = list(jsc.array(dym_offer.get("picked")))
    if kind == "team_pick" and isinstance(pending.get("options"), list):
        # A team clarify offers a NARROWED set (owner rule R-a), and `selection_context`
        # alone cannot say which - the marker's own list is the roster.
        rows = [r for r in pending["options"] if isinstance(r, dict)]
    question = ask(
        kind,
        options=rows,
        turn_no=at,
        ttl_turns=int(ttl) if isinstance(ttl, int) and ttl > 0 else None,
        payload=payload,
    )
    # THE CLOCK DOES NOT RESTART ON A CARRY. The legacy lifecycle keeps `selection_context`
    # and `last_result_set` alive across turns that build no offer of their own (owner
    # ruling K rule 1), so re-deriving the mirror stamps a fresh `asked_at_turn` on a
    # question nobody has answered - and the age is 1 forever. A question is NEW only when
    # its kind or its rows changed; otherwise it keeps the turn it was actually asked on.
    if same_question(question, previous):
        question["asked_at_turn"] = int(
            previous.get("asked_at_turn", question["asked_at_turn"])
        )
    return question


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
    """
    handler = _HANDLERS.get(kind)
    if handler is None:
        return Outcome(handler="unknown", outcome=f"No handler for {kind!r}.")
    return handler(answer or {}, _freeze(options), dict(payload or {}))


# --------------------------------------------------------------------------- #
# The seven handlers
# --------------------------------------------------------------------------- #


def _product_pick(answer: dict, options: list, payload: dict) -> Outcome:
    picked = _rows_for(answer.get("picks"), options)
    if not picked:
        return Outcome(handler="product_pick", outcome="No offered row was named.")
    entities = [_entity_of(row, "product") for row in picked]
    # ISSUE #708. `payload.keep` is the scope that already resolved on the turn the
    # picker was offered, minus whatever the pick itself replaces. Without it the turn
    # answers about the pick alone and silently drops the sibling the customer asked
    # about in the same message.
    keep = [
        e
        for e in payload.get("keep") or []
        if isinstance(e, dict) and not _same_code(e, entities)
    ]
    return Outcome(
        handler="product_pick",
        outcome=f"Picked {', '.join(_label_of(r) for r in picked)}.",
        resolved=True,
        picked=picked,
        keep=keep,
        focus={"products": entities + [e for e in keep if _is_product(e)]},
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


def _escalate_yes_no(answer: dict, options: list, payload: dict) -> Outcome:
    if answer.get("yes_no") == "yes":
        return Outcome(
            handler="escalate_yes_no",
            outcome="The customer accepted the escalation.",
            resolved=True,
            escalate=True,
            routing={"suggested_team": payload.get("team")},
        )
    if answer.get("yes_no") == "no":
        return Outcome(
            handler="escalate_yes_no",
            outcome="The customer declined the escalation.",
            resolved=True,
            declined=True,
        )
    # AC-945: a question that is neither accepted nor declined is LEFT OPEN. It is not
    # answered by a stock question that happened to arrive next, and it is cleared by its
    # own TTL with a `decay` trace line rather than silently.
    return Outcome(handler="escalate_yes_no", outcome="Neither yes nor no.")


def _team_pick(answer: dict, options: list, payload: dict) -> Outcome:
    picked = _rows_for(answer.get("picks"), options)
    if not picked:
        return Outcome(handler="team_pick", outcome="No offered team was named.")
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
    "escalate_yes_no": _escalate_yes_no,
    "team_pick": _team_pick,
    "company_pick": _company_pick,
    "tier_pick": _tier_pick,
    "member_offer": _member_offer,
}


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #


def _freeze(options: Any) -> list[dict[str, Any]]:
    """The rows, numbered as the customer saw them.

    `idx` is taken from the row when it has one (every roster the lanes build stamps it)
    and supplied by position when it does not, so a position always resolves against the
    number that was printed.
    """
    frozen: list[dict[str, Any]] = []
    for position, row in enumerate(jsc.array(options), start=1):
        if not isinstance(row, dict):
            continue
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
    """
    code = row.get("code") or row.get("value") or row.get("product") or row.get("label")
    return {
        "raw": code,
        "hint": row.get("entity_type") or hint,
        "canonical_code": code,
        "uuid": row.get("uuid") or None,
        "ordinal": row.get("idx"),
        "current_message": True,
        "confident": True,
    }


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


def _roster_of(stored: dict, context: str) -> list[dict[str, Any]]:
    """WHICH list the customer is looking at, decided the way the legacy ladder decides it.

    On a partial-miss / did-you-mean turn the numbered rows the reply printed are
    `dym_last_result_set`, and `last_result_set` holds the ANSWER's own rows - the stock
    lines for the code that DID resolve. `output_exchange`'s `dym_numbered_multi_select`
    resolves a numbered pick against the dym set on exactly those turns, and the "all over
    an active offer" block keys on the same array. Freezing `last_result_set` instead would
    make "2" the second stock line rather than the second suggestion: the wrong product,
    with no error anywhere.

    Same discriminator as the ladder - a non-empty `dym_last_result_set` under the
    `suggest_offer` label - and the same one `_siblings_to_keep` below already used, which
    is what made the mismatch visible: one half of this module was reading the dym shape
    and the other half was not.
    """
    dym_rows = [r for r in jsc.array(stored.get("dym_last_result_set")) if isinstance(r, dict)]
    if context == "suggest_offer" and dym_rows:
        return dym_rows
    return [r for r in jsc.array(stored.get("last_result_set")) if isinstance(r, dict)]


def _siblings_to_keep(stored: dict, context: str, dym_offer: dict) -> list[dict[str, Any]]:
    """The prior entities the pick must not throw away, minus the tokens it answers."""
    candidates = [c for c in jsc.array(dym_offer.get("candidates")) if isinstance(c, dict)]
    if context != "suggest_offer" or not candidates:
        return []
    source_keys = set()
    for candidate in candidates:
        source_keys |= {
            _code_key({"canonical_code": candidate.get("for_canonical")}),
            _code_key({"canonical_code": candidate.get("for_raw")}),
        }
    source_keys -= {""}
    return [
        e
        for e in jsc.array(stored.get("entities"))
        if isinstance(e, dict) and _code_key(e) not in source_keys
    ]


def _rows_are_customers(rows: list[dict[str, Any]]) -> bool:
    return bool(rows) and all(
        jsc.lower_or_empty(r.get("entity_type")) == "customer" for r in rows
    )
