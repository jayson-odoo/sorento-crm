# The dealer's stock ask never offers an escalation (owner ruling 26 Sep 2026, hand
# test F1: "dealer ask cannot have escalation, cannot have direct escalation to
# warehouse, their contact point is sales person").
#
# A dealer is an availability-only contact (`Profile.stock_availability_only`). Every
# place a stock ask would say "would you like me to escalate to warehouse team?" or
# store a team pick says "Please refer to your salesman." instead, with no pending
# question; a did-you-mean becomes a pick of the suggested code(s), carrying the typed
# quantity. Staff contacts (detailed / compact) never reach this module.
#
# Pure: no I/O. Lives outside `turn/` because it reads reply TEXT (the escalation
# sentence a composer already printed), which the turn package never does.
from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from app.services.chatbot import label_catalog
from app.services.chatbot.turn import refer
from app.services.chatbot.turn.pending import ESCALATION_OFFER_KINDS, Pending, ask
from app.services.chatbot.turn.state import token_key
from app.services.chatbot.turn.task import MAX_SLOTS, numbered

#: Every escalation sentence the stock ask's composers print
#: (`lanes/business/answer.py`, `turn/compose.py`), whole: the "reply with a code"
#: lead-in goes with it, since what it offered next is gone.
_ESCALATION = re.compile(
    r"\s*(?:Reply (?:with )?a (?:code|number|date) to (?:continue|pick), or )?"
    r"(?:[Ww]ould you like me|[Ss]hall I|[Dd]o you want me) to escalate[^?\n]*\?"
    r"|\s*Reply a number to pick, or 'yes' to escalate to [^.\n]*\."
)


def refers_to_salesman(text: str) -> tuple[str, bool]:
    """`text` with every escalation offer taken out, and whether one was."""
    stripped, count = _ESCALATION.subn("", text or "")
    return stripped.rstrip(), bool(count)


def without_escalation(
    text: str, question: Pending | None, *, localizer: Any = None
) -> tuple[str, Pending | None]:
    """The dealer's version of a stock reply: no escalation sentence, no escalation
    pending, and "Please refer to your salesman." wherever one was offered. A roster the
    reply also carried (a pick of products) stays, without its attached offer."""
    from app.services.chatbot.order_list import _picker_frame_lines, _without_picker
    from app.services.chatbot.turn.pending import without_escalation as strip_pending

    stripped, had_sentence = refers_to_salesman(text)
    offered = had_sentence
    # REFER-ONLY-FIXES (owner console, 3 Oct 2026): the routing picker the offer hung off
    # goes with it, its numbered staff rows included, never left under the refer line,
    # and the question loses the member options it no longer shows.
    whole, prefixes = _picker_frame_lines()
    if any(line.strip() in whole or line.strip().startswith(prefixes) for line in stripped.splitlines()):
        question, dropped = strip_pending(question)
        stripped = _without_picker(stripped, dropped or [])
        offered = True
    if question is not None:
        if question.kind in ESCALATION_OFFER_KINDS:
            question = None
            offered = True
        elif (question.payload or {}).get("escalate_offered") is True:
            question = replace(
                question, payload={**question.payload, "escalate_offered": False}
            )
            offered = True
    if not offered:
        return text, question
    body = stripped.strip()
    if any(line in body for line in label_catalog.refer_sentences(localizer)):
        # ESCALATION-CONTROL: a blocked contact's composer already printed the line.
        return body, question
    return refer.after(body), question


def _code_of(row: dict[str, Any]) -> Any:
    """A candidate row's code: a resolver roster row, or (`code`) a row of
    `answer.did_you_mean_by_token`, a missed code beside found ones."""
    return row.get("product") or row.get("value") or row.get("label") or row.get("code")


def did_you_mean_text(
    shown: str, labels: list[str], *, start: int | None = None, size_lines: list[str] | None = None
) -> str:
    """The did-you-mean sentence for one missed code. One code alone reads "Couldn't find
    ELP3753. Did you mean ELP3754?"; several, or a list sharing a message with others
    (`start`, where its numbers carry on), read one numbered code per line. PICKER-NO-CAP
    (owner, 2 Oct 2026): every option the pick carries is printed. CHATBOT-CODE-MATCH R4:
    each code's own size line (`size_lines`, from stored values only) sits under it."""
    from app.services.chatbot.lanes.business.answer import with_size_lines

    sizes = list(size_lines or []) + [""] * len(labels)
    if start is None and len(labels) == 1:
        return "\n".join(with_size_lines([f"Couldn't find {shown}. Did you mean {labels[0]}?"], sizes))
    lines = with_size_lines(numbered(labels, start or 1), sizes)
    return "\n".join([f"Couldn't find {shown}. Did you mean:", *lines])


def did_you_mean_lists(
    options: list[dict[str, Any]], groups: list[dict[str, Any]], owed: list[dict[str, Any]] | None = None
) -> tuple[str, dict[str, Any]]:
    """Several missed codes' did-you-mean lists in one message (`task.picks_question`'s
    did-you-mean twin): the text, one list per group numbered as its options are, and the
    pick (`task.stock_pick`, each group keeping its typed code and quantity, `did_you_mean`
    kept). Asked first by `did_you_mean_each`, and again with the lists still open
    (`apply`'s "yes" over it, `engine._stock_ask_reply` after one list is answered)."""
    from app.services.chatbot.turn.task import stock_pick

    stored = stock_pick(options, groups, owed)
    text = "\n\n".join(
        did_you_mean_text(
            str(group["typed"]),
            [str(o["label"]) for o in options if o.get("position") in group["positions"]],
            start=group["positions"][0],
            size_lines=[str(o.get("size_line") or "") for o in options if o.get("position") in group["positions"]],
        )
        for group in groups
        if group.get("positions")
    )
    return text, {**stored, "payload": {**stored["payload"], "did_you_mean": True}}


def did_you_mean(
    typed: str,
    candidates: list[dict[str, Any]],
    *,
    quantity: Any = None,
    asked_at_turn: int | None = None,
    size_asked: str = "",
) -> tuple[str, Pending] | None:
    """The dealer's did-you-mean: the suggested code(s) as a pick carrying the typed
    quantity, and no escalation. One candidate reads "Couldn't find ELP3753. Did you
    mean ELP3754?" and a "yes" answers ELP3754 (`apply._answer_pending`); a "no" refers
    the dealer to their salesman."""
    options: list[dict[str, Any]] = []
    for row in candidates or []:
        if not isinstance(row, dict):
            continue
        code = _code_of(row)
        if not code or not row.get("uuid"):
            continue
        # CHATBOT-CODE-MATCH R3: a close registered set is offered beside its members.
        if row.get("entity_type") not in (None, "product", "product_set"):
            continue
        options.append(
            {
                "position": len(options) + 1,
                "label": str(code),
                "code": str(code),
                "uuid": str(row["uuid"]),
                "entity_type": row.get("entity_type") or "product",
                # An offered set carries what its exact ask resolves to (`answer.set_members_of`).
                **({"members": list(row["members"])} if row.get("members") else {}),
                **({"size_line": str(row["size_line"])} if row.get("size_line") else {}),
            }
        )
    options = options[:MAX_SLOTS]
    if not options:
        return None
    shown = (typed or "").strip().upper() or "that"
    labels = [o["label"] for o in options]
    # CHATBOT-CODE-MATCH R4: a size nothing holds is what was not found ("with size 400 mm").
    said = f"{shown} {size_asked}".strip() if size_asked else shown
    text = did_you_mean_text(said, labels, size_lines=[str(o.get("size_line") or "") for o in options])
    pick = ask(
        "product_pick",
        options,
        asked_at_turn=asked_at_turn,
        payload={
            "domain": "inventory",
            "domains": ["inventory"],
            "stock_pick": True,
            "did_you_mean": True,
            "typed": shown,
            "count": len(labels),
            "stock_qty": quantity,
        },
    )
    return text, pick


def quantity_of(entities: Any, token: Any) -> int | None:
    """The quantity the message stated for the product it typed as `token` (separators and
    case folded), None when it stated none."""
    key = token_key(token)
    for e in entities or []:
        if not isinstance(e, dict) or not key:
            continue
        qty = e.get("quantity")
        if (
            isinstance(qty, (int, float))
            and not isinstance(qty, bool)
            and key in (token_key(e.get("raw")), token_key(e.get("canonical_code")))
        ):
            return int(qty)
    return None


def did_you_mean_each(
    groups: list[tuple[str, list[dict[str, Any]], Any]],
    *,
    answered: set[str] | frozenset[str] = frozenset(),
    asked_at_turn: int | None = None,
    before: dict[str, Any] | None = None,
) -> tuple[str, Pending, list[str]] | None:
    """CHATBOT-CODE-MATCH R7: every missed code of one message gets its own did-you-mean,
    in one reply. `groups` is `(typed, candidates, quantity)` per missed code. A code this
    reply already `answered` (folded by `token_key`), or one an earlier code offered, is not
    offered again. One code with candidates left reads exactly as `did_you_mean`; several
    read one numbered list each, numbers running on, stored as one pick whose `groups`
    keep each code's quantity (`task.stock_pick`). Returns the text, the pick and the typed
    codes it offered for; None when no candidate is left.

    `before` (CHATBOT-CLOSE-CODES C3, crew Q3 (a)): a which-one pick the same reply already
    asks (`task.stock_pick` shape). The offer's lists number on after its options and the
    returned pick holds both, so a number answers either; the text is the offer's alone."""
    seen = set(answered)
    blocks: list[tuple[str, Any, Pending, str]] = []
    for typed, candidates, quantity in groups:
        fresh = [r for r in candidates or [] if isinstance(r, dict) and token_key(_code_of(r)) not in seen]
        one = did_you_mean(typed, fresh, quantity=quantity, asked_at_turn=asked_at_turn)
        if one is None:
            continue
        seen.update(token_key(o["code"]) for o in one[1].options)
        blocks.append((typed, quantity, one[1], one[0]))
    if not blocks:
        return None
    if len(blocks) == 1 and before is None:
        typed, _quantity, pick, text = blocks[0]
        return text, pick, [typed]
    asked = before or {}
    options: list[dict[str, Any]] = [dict(o) for o in asked.get("options") or [] if isinstance(o, dict)]
    asked_payload = asked.get("payload") or {}
    pick_groups: list[dict[str, Any]] = [dict(g) for g in asked_payload.get("groups") or [] if isinstance(g, dict)]
    if options and not pick_groups:
        # A single which-one list stored before `groups` (`task.stock_pick` writes them now).
        pick_groups = [
            {
                "typed": asked_payload.get("typed"),
                "count": len(options),
                "qty": asked_payload.get("stock_qty"),
                "positions": [o.get("position") for o in options],
            }
        ]
    asked_options, asked_groups = len(options), len(pick_groups)
    for _typed, quantity, one, _text in blocks:
        start = len(options) + 1
        options.extend({**o, "position": start + i} for i, o in enumerate(one.options))
        positions = list(range(start, len(options) + 1))
        pick_groups.append({"typed": one.payload["typed"], "count": len(positions), "qty": quantity, "positions": positions})
    text, stored = did_you_mean_lists(options[asked_options:], pick_groups[asked_groups:])
    if before is not None:
        from app.services.chatbot.turn.task import OWED, stock_pick

        merged = stock_pick(options, pick_groups, asked_payload.get(OWED))
        stored = {"options": merged["options"], "payload": {**asked_payload, **merged["payload"]}}
    pick = ask("product_pick", stored["options"], asked_at_turn=asked_at_turn, payload=stored["payload"])
    return text, pick, [b[0] for b in blocks]
