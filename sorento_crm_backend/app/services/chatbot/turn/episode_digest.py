"""The episode digest: a deterministic, no-LLM summary of a closed episode's turns
(chatbot memory lane A, contract section 5.2 / PLAN-chatbot-memory-26sep.md section
5.2).

**No side effects.** No database library, no ORM handle, no database import of any
kind - `digest()` only looks at the turn dicts it is handed, so it is replayable in CI
and safe to call from both the live writer (`turn/memory.py::write_episode_for_reset`)
and the offline `scripts/backfill_chatbot_episodes.py`, over the identical range of
turns, and get the identical answer (AC-MEM029).

**No figures.** A stock count, a price or an ETA is stale by the next day - the summary
says WHAT was asked and HOW it ended, never the number. Outcome is read from structural
signals the engine really writes (reviewer pass at d89110c0, S5): `branch_kind`, the
`apply` record's `plan.ask` and `plan.denied`, the `looked_up` stage's status and its
`facts.missed` / `facts.sections`, and the `memory` record's open question - never from
a rendered reply, which can say anything.

Input: a list of turn dicts, oldest first, each shaped
`{id, created_at, branch_kind, status, message, trace, result_refs}` - the same shape
`chatbot.turns` rows project to (`created_at` a datetime, `trace` the same list of stage/
kind records the trace writer already produces: an `apply` kind record with
`verdict`/`plan`, a `looked_up` stage with `facts.missed`/`facts.sections`, a `tool`
kind record, a `memory` kind record whose `open_question.after` is the question the
reply left open, a `replied` stage whose rendered facts are never read here).
"""
from __future__ import annotations

from datetime import timezone
from typing import Any
from zoneinfo import ZoneInfo

#: One clause per outcome (AC-MEM022), read from structural data only.
_OUTCOME_WORDS: dict[str, str] = {
    "answered": "answered",
    "not_found": "not found",
    "asked_back": "asked back",
    "escalated": "escalated",
    "declined": "declined",
    "denied": "denied",
}

#: `branch_kind` values that decide the outcome outright, before any ask/lookup signal
#: is consulted (AC-MEM022).
_BRANCH_OUTCOME: dict[str, str] = {
    "out_of_scope": "escalated",
    "escalation_declined": "declined",
    "access_denied": "denied",
}

#: A turn with this branch is small talk, not an ask - excluded from `asks` entirely.
_SMALL_TALK_BRANCH = "low_signal"

#: The one close trigger there is today (contract section 3 / PLAN 5.1, Q2 ruling).
_CLOSE_REASON = "topic_switch"

_SUMMARY_CHAR_CAP = 240
_LAST_MESSAGE_CHAR_CAP = 200
#: A `raw` (unresolved) entity token is a customer's own typed text, not a
#: catalog-checked value - capped and whitespace-collapsed (security review 26
#: Sep 2026, S2) so a pasted block of text never turns one entity into a
#: multi-line digest entry or blows out the summary's own char cap.
_ENTITY_TOKEN_CHAR_CAP = 40

_MONTH_ABBR = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)
_WEEKDAY_ABBR = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

#: The dealers' clock (reviewer pass at d89110c0, S14): a message sent Fri 07:10 in
#: Kuala Lumpur is Thu 23:10 UTC, and must read "Fri".
_LOCAL_TZ = ZoneInfo("Asia/Kuala_Lumpur")

#: Open-question kinds that offer a team (`turn/pending.py::ESCALATION_OFFER_KINDS`).
_OFFER_KINDS = frozenset({"team_pick", "member_offer", "company_pick"})


def local_time(when: Any) -> Any:
    """`when` on the dealers' clock. A naive datetime is UTC (how `chatbot.turns`
    stores it)."""
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(_LOCAL_TZ)


def _trace(turn: dict[str, Any]) -> list[dict[str, Any]]:
    trace = turn.get("trace")
    return [r for r in trace if isinstance(r, dict)] if isinstance(trace, list) else []


def _kind_records(turn: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [r for r in _trace(turn) if r.get("kind") == kind]


def _stage_record(turn: dict[str, Any], stage: str) -> dict[str, Any] | None:
    for r in _trace(turn):
        if r.get("kind") is None and r.get("stage") == stage:
            return r
    return None


def _apply_record(turn: dict[str, Any]) -> dict[str, Any] | None:
    entries = _kind_records(turn, "apply")
    return entries[-1] if entries else None


def _verdict(turn: dict[str, Any]) -> dict[str, Any]:
    apply_record = _apply_record(turn)
    verdict = (apply_record or {}).get("verdict")
    return verdict if isinstance(verdict, dict) else {}


def _plan(turn: dict[str, Any]) -> dict[str, Any]:
    apply_record = _apply_record(turn)
    plan = (apply_record or {}).get("plan")
    return plan if isinstance(plan, dict) else {}


def _turn_domain(turn: dict[str, Any]) -> str | None:
    domain = _verdict(turn).get("domain_hint")
    if domain:
        return domain
    domains = _plan(turn).get("domains") or []
    return domains[0] if domains else None


def turn_verdict(turn: dict[str, Any]) -> dict[str, Any]:
    """The parser verdict a turn's `apply` record carries (`{}` when it has none)."""
    return _verdict(turn)


def topic_domain(turn: dict[str, Any]) -> str | None:
    """The domain a turn's PLAN acted on, off its `apply` record: the reading the
    topic-switch detector compares (fix lane round 3, R1). The plan, not the parser's
    `domain_hint`: a history question or small talk can carry a hint ("product") while
    planning no domain at all, and must never read as a switch."""
    domains = _plan(turn).get("domains") or []
    return str(domains[0]) if domains else None


def close_trigger(verdict: dict[str, Any], domain: str | None, open_domain: str | None) -> str | None:
    """Why this turn closes the open conversation, or None when it does not (Q2 ruling:
    a conversation ends on a topic switch only). Two readings of a switch, one rule for
    the live engine and the backfill:

    * `topic_reset`: the parser says the message drops the subject ("never mind").
    * `domain_switch`: the turn plans a domain and the open conversation's newest
      planned domain is a different one ("check stock X" then "incoming X"). The
      parser's `topic_reset` stays false there, because the product is the same
      (owner hand test, 28 Sep 2026), so the flag alone never closed it.

    A turn that plans no domain (small talk, a history question, a menu) never
    switches; neither does one with no open domain to switch from."""
    if verdict.get("topic_reset") is True:
        return "topic_reset"
    if domain and open_domain and domain != open_domain:
        return "domain_switch"
    return None


def _entity_token(value: Any) -> str:
    """Whitespace-collapsed and capped at `_ENTITY_TOKEN_CHAR_CAP` (S2) - a
    `canonical_code` is already a short catalog code, but `raw` is whatever the
    customer typed, unbounded and possibly multi-line."""
    return " ".join(str(value).split())[:_ENTITY_TOKEN_CHAR_CAP]


def _entity_display(entities: list[Any]) -> list[str]:
    out: list[str] = []
    for e in entities or []:
        if not isinstance(e, dict):
            continue
        value = e.get("canonical_code") or e.get("raw")
        if not value:
            continue
        token = _entity_token(value)
        if token and token not in out:
            out.append(token)
    return out


def _entity_bucket(entities: list[Any]) -> dict[str, list[str]]:
    """Grouped by entity kind (`hint`), falling back to a generic bucket when a turn's
    entities carry none - the digest's own construction, since `entities` on the wire
    does not always carry `hint` (a synthetic/backfilled turn need not)."""
    buckets: dict[str, list[str]] = {}
    for e in entities or []:
        if not isinstance(e, dict):
            continue
        value = e.get("canonical_code") or e.get("raw")
        if not value:
            continue
        token = _entity_token(value)
        if not token:
            continue
        key = str(e.get("hint") or "entity")
        bucket = buckets.setdefault(key, [])
        if token not in bucket:
            bucket.append(token)
    return buckets


def _merge_entities(target: dict[str, list[str]], source: dict[str, list[str]]) -> None:
    for key, values in source.items():
        bucket = target.setdefault(key, [])
        for v in values:
            if v not in bucket:
                bucket.append(v)


def _open_question(turn: dict[str, Any]) -> dict[str, Any] | None:
    """The question this turn's reply left open, off its `memory` record."""
    entries = _kind_records(turn, "memory")
    after = (entries[-1].get("open_question") or {}).get("after") if entries else None
    return after if isinstance(after, dict) else None


def _outcome(turn: dict[str, Any]) -> str:
    branch_kind = turn.get("branch_kind")
    if branch_kind in _BRANCH_OUTCOME:
        return _BRANCH_OUTCOME[branch_kind]
    plan = _plan(turn)
    if plan.get("denied") and not plan.get("fetch"):
        return "denied"
    if plan.get("ask"):
        return "asked_back"
    looked_up = _stage_record(turn, "looked_up")
    if looked_up is not None:
        facts = looked_up.get("facts") or {}
        if looked_up.get("status") == "failed" or facts.get("missed") or facts.get("sections") == 0:
            return "not_found"
    question = _open_question(turn)
    if question is not None and question.get("kind") not in _OFFER_KINDS:
        return "asked_back"
    return "answered"


def _tools_used(turns: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for turn in turns:
        for entry in _kind_records(turn, "tool"):
            name = entry.get("name")
            if name and name not in out:
                out.append(str(name))
    return out


def _offers(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A team offered in a reply, and what the next turn in the episode did with it:
    accepted (the escalation ran), declined, or no answer."""
    out: list[dict[str, Any]] = []
    for index, turn in enumerate(turns):
        question = _open_question(turn)
        if question is None or question.get("kind") not in _OFFER_KINDS or not question.get("team"):
            continue
        following = turns[index + 1].get("branch_kind") if index + 1 < len(turns) else None
        answer = (
            "accepted"
            if following == "out_of_scope"
            else "declined"
            if following == "escalation_declined"
            else None
        )
        out.append({"team": question.get("team"), "answer": answer})
    return out


def _asks_and_small_talk(turns: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    asks: list[dict[str, Any]] = []
    small_talk = 0
    for turn in turns:
        if turn.get("branch_kind") == _SMALL_TALK_BRANCH:
            small_talk += 1
            continue
        asks.append(
            {
                "domain": _turn_domain(turn),
                "entities": _entity_display(_verdict(turn).get("entities") or []),
                "outcome": _outcome(turn),
            }
        )
    return asks, small_talk


def _date_prefix(when: Any) -> str:
    """`Thu 25 Sep` - the weekday tells the parser (and the staff screen) a line is
    old with no clock math at all (PLAN 5.1: "the day tells the parser a line is
    old")."""
    when = local_time(when)
    weekday = _WEEKDAY_ABBR[when.weekday()]
    month = _MONTH_ABBR[when.month - 1]
    return f"{weekday} {when.day} {month}"


def _summary(turns: list[dict[str, Any]], asks: list[dict[str, Any]], offers: list[dict[str, Any]]) -> str:
    # "1 turn", never "1 turns": the history reply shows this line to the dealer (S4).
    header = f"{_date_prefix(turns[0]['created_at'])}, {len(turns)} turn{'' if len(turns) == 1 else 's'}"

    # Collapse consecutive/repeated asks about the same (domain, entities, outcome)
    # into one clause - two turns both asking "stock SRTWB1455" and both answered read
    # as one line, not two.
    seen: set[tuple[Any, ...]] = set()
    clauses: list[str] = []
    for ask in asks:
        key = (ask["domain"], tuple(ask["entities"]), ask["outcome"])
        if key in seen:
            continue
        seen.add(key)
        entities_words = ", ".join(ask["entities"])
        domain_words = ask["domain"] or ""
        subject = " ".join(w for w in (domain_words, entities_words) if w)
        if not subject and ask["outcome"] in ("answered", "asked_back"):
            # A menu or a history question names nothing: a bare "(asked back)" says
            # nothing a staff reader or the parser can use (fix lane round 3).
            continue
        outcome_word = _OUTCOME_WORDS.get(ask["outcome"], ask["outcome"])
        clauses.append(f"{subject} ({outcome_word})".strip())

    for offer in offers:
        if not offer.get("team"):
            continue
        clauses.append(f"offered {offer['team']} team, {offer.get('answer') or 'no answer'}")

    body = "; ".join(clauses) if clauses else "small talk"
    summary = f"{header}: {body}."
    if len(summary) > _SUMMARY_CHAR_CAP:
        summary = summary[: _SUMMARY_CHAR_CAP - 1].rstrip() + "."
    return summary


def digest(turns: list[dict[str, Any]]) -> dict[str, Any]:
    """One episode's digest, from its turns (oldest first). Never empty - the caller
    (`write_episode_for_reset`) already checked the range is non-empty."""
    domains: list[str] = []
    entities: dict[str, list[str]] = {}
    tools_used: list[str] = []
    result_refs: list[Any] = []

    for turn in turns:
        domain = _turn_domain(turn)
        if domain and domain not in domains:
            domains.append(domain)
        _merge_entities(entities, _entity_bucket(_verdict(turn).get("entities") or []))
        for ref in turn.get("result_refs") or []:
            if ref not in result_refs:
                result_refs.append(ref)

    tools_used = _tools_used(turns)
    offers = _offers(turns)
    asks, small_talk_turns = _asks_and_small_talk(turns)
    summary = _summary(turns, asks, offers)

    first_turn = turns[0]
    last_turn = turns[-1]
    last_message = str(last_turn.get("message") or "")[:_LAST_MESSAGE_CHAR_CAP]

    return {
        "domains": domains,
        "entities": entities,
        "asks": asks,
        "offers": offers,
        "small_talk_turns": small_talk_turns,
        "turn_count": len(turns),
        "first_at": first_turn.get("created_at"),
        "last_at": last_turn.get("created_at"),
        "close_reason": _CLOSE_REASON,
        "summary": summary,
        # Extra fields the frame row needs beyond the documented minimum (PLAN 5.2):
        # written into `conversation_frames.domain` / `.intent` / `.tools_used` /
        # `.result_refs` / `.last_user_message` by the caller.
        "domain": domains[0] if domains else None,
        "intent": _verdict(first_turn).get("intent_hint"),
        "tools_used": tools_used,
        "result_refs": result_refs,
        "last_user_message": last_message,
    }
