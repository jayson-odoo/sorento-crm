# ESCALATION-CONTROL (owner, 30 Sep 2026): "we need to be able to control each contact
# that they cannot access the escalation: cannot force escalate, won't be offered
# escalation; this is for dealer".
#
# A barred contact (`turn.state.escalation_barred`, resolved by `app/services/
# escalation_policy.py`) is never offered a hand-off and cannot force one. The offer
# sites read `turn.state.offers_escalation` at source; this module is the backstop the
# engine runs on every composed reply (`strip_offers`), and the reply the forced path
# gives instead of a hand-off (`barred_reply`).
#
# Pure: no I/O.
from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.services.chatbot.dealer_stock import refers_to_salesman
from app.services.chatbot.turn.pending import ESCALATION_OFFER_KINDS

#: The owner's default wording until he rules otherwise (crew brief, 30 Sep 2026). The
#: stock ask's older dealer line is `turn/task.py::REFER_TO_SALESMAN` ("Please refer to
#: your salesman."); this one names the salesperson when the CRM knows them.
BARRED_REPLY = "For anything I can't answer here, please contact your salesperson"


def barred_reply(profile: Any) -> str:
    """The reply a barred contact gets where a hand-off (or an offer of one) would be."""
    name = (getattr(profile, "salesperson", None) or "").strip()
    return f"{BARRED_REPLY} {name}." if name else f"{BARRED_REPLY}."


def strip_pending(question: Any) -> tuple[Any, list[dict[str, Any]] | None]:
    """`question` with every escalation part taken out, and the options that went.

    An escalation offer kind goes whole; a roster keeps its business options and loses
    its member (routing) options, its `escalate_offered` stamp and its team."""
    if question is None:
        return None, None
    if question.kind in ESCALATION_OFFER_KINDS:
        return None, [o for o in (question.options or []) if isinstance(o, dict)]
    members = [o for o in (question.options or []) if isinstance(o, dict) and o.get("entity_type") == "member"]
    payload = dict(question.payload or {})
    offered = payload.pop("escalate_offered", None) is True
    if not members and not offered:
        return question, None
    kept = [o for o in (question.options or []) if not (isinstance(o, dict) and o.get("entity_type") == "member")]
    if not kept:
        return None, members
    return replace(question, options=kept, payload=payload, team=None), members


def strip_offers(answer: Any, profile: Any) -> Any:
    """A composed reply with no escalation offer in it: the offer sentence, a routing
    picker, an armed escalation question and the `offer` all go, and the barred reply
    stands where the offer was. A reply that offered nothing is returned unchanged."""
    from app.services.chatbot.order_list import _picker_frame_lines, _without_picker

    text = getattr(answer, "text", "") or ""
    stripped, had_sentence = refers_to_salesman(text)
    question, dropped = strip_pending(getattr(answer, "question", None))
    whole, prefixes = _picker_frame_lines()
    has_frame = any(
        line.strip() in whole or line.strip().startswith(prefixes) for line in stripped.splitlines()
    )
    if dropped or has_frame:
        companies = [
            str(row.get("company_name"))
            for row in ((answer.question.payload or {}).get("roster_plan") or [])
            if isinstance(row, dict) and row.get("company_name")
        ] if dropped else []
        stripped = _without_picker(stripped, dropped or [], companies=companies)
    offered = (
        had_sentence
        or has_frame
        or bool(dropped)
        or question is not getattr(answer, "question", None)
        or getattr(answer, "offer", None) is not None
    )
    if not offered:
        return answer
    referral = barred_reply(profile)
    body = stripped.strip()
    if referral not in body:
        body = f"{body}\n\n{referral}" if body else referral
    return replace(answer, text=body, question=question, offer=None)
