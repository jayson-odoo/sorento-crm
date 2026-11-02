"""Measure where the router sends a dealer's slice 1 asks (AGENTIC-WA-W2), read only.

Builds exactly what `router.decide_route` sends to Jev for a contact principal: the stored production
`chatbot_router` prompt, `_with_open_page`, and the contact's own agent labels (dealer requests
included). It then calls Jev ONCE per row. The state is a fresh one, as after a console Reset; an undo
row carries one prior agent reply, as on WhatsApp. Nothing is written: no usage row, no turn, and the
session is rolled back.

    DATABASE_URL=... python -m scripts.measure_router_dealer_asks --contact <respond_io_id> [--variant b] [--json]

`--variant b` appends the candidate wording (`VARIANT_B`) to the stored criteria and scores the same rows,
so a prompt change is measured before anyone edits the stored prompt. The cut-off is the stored
`chatbot_router_min_score` (owner ruling: stays 0.70).
"""
from __future__ import annotations

import argparse
import copy
import json
import sys

#: (id, language, expected side, message, last agent reply or None). Product codes are catalogue codes; no
#: real names, phones or figures.
AGENT_REPLY_SENT = (
    "Stock inquiry SI-26-0001 is with the project sales team. Reply undo within 10 minutes to withdraw it."
)
ROWS: list[tuple[str, str, str, str, str | None]] = [
    ("si-1", "en", "agent", "can I get 40 pcs SRT5733 by 15 Dec 2026 for project Test Tower?", None),
    ("si-2", "en", "agent", "please send a stock inquiry for SRT5733, 40 pcs, needed by 15 Dec", None),
    ("si-3", "en", "agent", "raise a lead time enquiry for 40 pcs SRT5733 for my project", None),
    ("si-4", "en", "agent", "ask your project sales team when 40 pcs SRT5733 can be ready", None),
    ("si-5", "en", "agent", "I need 120 pcs SRT5733 for a project in January, can your team check and confirm the lead time?", None),
    ("si-6", "bm", "agent", "boleh tolong buat stock inquiry SRT5733 40 pcs, perlu sebelum 15 Dis", None),
    ("si-7", "bm", "agent", "tolong tanya team project sales bila boleh dapat 40 pcs SRT5733", None),
    ("si-8", "zh", "agent", "帮我开一个库存询价，SRT5733 要40个，12月15号前要", None),
    ("si-9", "zh", "agent", "SRT5733 我要40个，帮我问一下项目销售团队交期", None),
    ("note-1", "en", "agent", "for my stock inquiry last week, the customer can only take delivery on Tuesday, please add that", None),
    ("note-2", "bm", "agent", "untuk inquiry saya minggu lepas, tolong tambah nota: customer hanya boleh terima hari Selasa", None),
    ("note-3", "zh", "agent", "我上星期的询价，帮我加备注：客户只能星期二收货", None),
    ("undo-1", "en", "agent", "undo that inquiry please", AGENT_REPLY_SENT),
    ("undo-2", "bm", "agent", "batalkan inquiry tadi", AGENT_REPLY_SENT),
    ("undo-3", "zh", "agent", "刚才那个询价取消掉", AGENT_REPLY_SENT),
    ("list-1", "en", "agent", "what requests have I sent you and what is their status?", None),
    ("list-2", "bm", "agent", "apa status inquiry yang saya hantar?", None),
    ("list-3", "zh", "agent", "我提交过的询价现在什么状态？", None),
    ("ctl-1", "en", "chat", "stock SRT5733?", None),
    ("ctl-2", "bm", "chat", "SRT5733 ada stok?", None),
    ("ctl-3", "zh", "chat", "SRT5733 有货吗", None),
]

#: Candidate wording, appended to the stored text (never a word list: Jev reads it as criteria).
VARIANT_B = {
    "agent.also": (
        " Also any request for the team to act for the person: send, raise or file something (a stock or lead "
        "time inquiry to a team), add a note to one of their own requests, withdraw or undo what they just "
        "sent, and a question about the requests they sent."
    ),
    "agent.not_for": " (A check of what is in stock is the bot's; asking the team to check or confirm is not.)",
    "chat.not_for": " A request to send or file something to a team, or to change or undo something already sent.",
}


def _variant_b(criteria: dict) -> dict:
    out = copy.deepcopy(criteria)
    for path, extra in VARIANT_B.items():
        side, key = path.split(".")
        entry = out.get(side)
        if isinstance(entry, dict):
            entry[key] = f"{str(entry.get(key) or '').rstrip()}{extra}"
    return out


def _state(text: str, agent_reply: str | None) -> dict:
    exchanges = (
        [{"user": "can I get 40 pcs SRT5733?", "reply": agent_reply, "answered_by": "agent"}] if agent_reply else []
    )
    return {
        "latest_message": text,
        "recent_exchanges": exchanges,
        "last_answered_by": exchanges[-1]["answered_by"] if exchanges else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--contact", required=True, help="respond.io id of a contact principal (agent on, no linked user)")
    parser.add_argument("--variant", choices=("a", "b"), default="a", help="a = stored prompt, b = stored + VARIANT_B")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    from app.database import SessionLocal
    from app.models.ai_assistant import AIAssistantConfig
    from app.models.user import SystemSetting
    from app.services.chatbot import jev_client
    from app.services.chatbot.agent import portal_writes
    from app.services.chatbot.router import _router_prompt, _with_agent_tools, _with_open_page, agent_tool_labels
    from app.services.llm_provider import resolve_typesafe_key

    db = SessionLocal()
    try:
        offered = portal_writes.offered_for_contact(db, args.contact)
        if not offered:
            print("This contact is offered no dealer tool (linked user, namesake row, agent off or form hidden).")
            return 2
        prompt = _router_prompt(db)
        key = resolve_typesafe_key(db.query(AIAssistantConfig).first())
        if prompt is None or not key:
            print("No production chatbot_router prompt or no Jev key on this database.")
            return 2
        instructions, criteria, model = prompt
        criteria = _with_agent_tools(_with_open_page(criteria), agent_tool_labels(db, None, contact_respond_id=args.contact))
        if args.variant == "b":
            criteria = _variant_b(criteria)
        settings = db.query(SystemSetting).first()
        floor = float(getattr(settings, "chatbot_router_min_score", None) or 0.70)

        results, tokens_in, tokens_out = [], 0, 0
        for rid, lang, expected, text, reply in ROWS:
            try:
                answer = jev_client.classify(
                    key, model=model, instructions=instructions, criteria=criteria, state=_state(text, reply)
                )
            except jev_client.JevError as exc:
                results.append({"id": rid, "lang": lang, "expected": expected, "side": "chat", "why": f"router_failed:{exc.kind}"})
                continue
            tokens_in += answer.input_tokens
            tokens_out += answer.output_tokens
            # The same rule as decide_route on WhatsApp: below the floor goes to the bot.
            side = answer.choice if answer.confidence >= floor else "chat"
            results.append({
                "id": rid, "lang": lang, "expected": expected, "jev": answer.choice,
                "confidence": round(answer.confidence, 2), "side": side,
                "why": "classified" if answer.confidence >= floor else "low_confidence",
            })
    finally:
        db.rollback()
        db.close()

    writes = [r for r in results if r["expected"] == "agent"]
    controls = [r for r in results if r["expected"] == "chat"]
    summary = {
        "variant": args.variant,
        "floor": floor,
        "dealer_asks_to_agent": f"{sum(r['side'] == 'agent' for r in writes)}/{len(writes)}",
        "controls_on_bot": f"{sum(r['side'] == 'chat' for r in controls)}/{len(controls)}",
        "jev_tokens": {"input": tokens_in, "output": tokens_out},
    }
    if args.json:
        print(json.dumps({"summary": summary, "rows": results}, ensure_ascii=False, indent=2))
    else:
        print("| id | lang | expected | jev | conf | side |")
        print("|---|---|---|---|---|---|")
        for r in results:
            print(f"| {r['id']} | {r['lang']} | {r['expected']} | {r.get('jev', '-')} | {r.get('confidence', '-')} | {r['side']} ({r['why']}) |")
        print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
