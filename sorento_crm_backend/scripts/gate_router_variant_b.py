"""Gate for the router wording "variant B" (AGENTIC-WA-W2, PROPOSAL-router-dealer-requests-01nov.md), read only.

Runs today's stored `chatbot_router` text (A) and A plus the variant B sentences (B) on the same rows:

- the router baseline rows crew keeps (the 50 + 30 AGENTIC-UNIFY used), from a JSONL file, once each per text;
- the 21 slice 1 rows of `measure_router_dealer_asks` (18 dealer asks, 3 stock-check controls), twice each per text.

Each baseline line is `{"set": "real" | "panel" | ..., "text": "...", "expected": "chat" | "agent"}`, optionally
with `"exchanges": [{"user", "reply", "answered_by"}]`, `"page": {...}` (a panel turn: its `current_page`, and the
open-page criteria lines the panel adds) and `"tools": [labels]` (the agent labels that row's principal had).

A row counts as right at the FLOOR when the side after the 0.70 cut-off (WhatsApp, console) is the expected
one, and on the PICK when Jev's own choice is (the panel trusts Jev's pick). The rule set before the run: on every
baseline set B gets no fewer right than A, at the floor and on the pick. The 21 rows are reported, not gated
(single runs drift). Nothing is written: no usage row, no turn, no prompt version, and the session is rolled back.

    python -m scripts.gate_router_variant_b --baseline <rows.jsonl> --contact <respond_io_id> [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict


def _load(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("expected") not in ("chat", "agent") or not str(row.get("text") or "").strip():
                raise SystemExit(f"line {n}: needs text and expected chat|agent")
            rows.append(row)
    return rows


def _criteria(base: dict, row: dict, open_page: str, open_record: str) -> dict:
    """The criteria Jev saw for this row: the text, the row's agent labels, and the panel's page lines."""
    import copy

    out = copy.deepcopy(base)
    agent = out.get("agent")
    if isinstance(agent, dict):
        if row.get("tools") is not None:
            agent["tools"] = list(row["tools"])
        page = row.get("page")
        if isinstance(page, dict):
            agent["open_page"] = open_page
            if page.get("record_ref"):
                agent["open_record"] = open_record
    return out


def _state(row: dict) -> dict:
    exchanges = list(row.get("exchanges") or [])
    state = {
        "latest_message": row["text"],
        "recent_exchanges": exchanges,
        "last_answered_by": exchanges[-1].get("answered_by") if exchanges else None,
    }
    if isinstance(row.get("page"), dict):
        state["current_page"] = row["page"]
    return state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--baseline", required=True, help="JSONL of crew's router baseline rows")
    parser.add_argument("--contact", required=True, help="respond.io id of the dealer contact used for the 21 rows")
    parser.add_argument("--json", help="write every row's answers to this file")
    args = parser.parse_args(argv)

    from app.database import SessionLocal
    from app.models.ai_assistant import AIAssistantConfig
    from app.models.user import SystemSetting
    from app.services.chatbot import jev_client
    from app.services.chatbot.router import (
        OPEN_PAGE_CRITERION, OPEN_RECORD_CRITERION, _router_prompt, agent_tool_labels,
    )
    from app.services.llm_provider import resolve_typesafe_key
    from scripts.measure_router_dealer_asks import ROWS, _state as dealer_state, _variant_b

    baseline = _load(args.baseline)
    db = SessionLocal()
    try:
        prompt = _router_prompt(db)
        key = resolve_typesafe_key(db.query(AIAssistantConfig).first())
        if prompt is None or not key:
            print("No production chatbot_router prompt or no Jev key on this database.")
            return 2
        instructions, stored, model = prompt
        settings = db.query(SystemSetting).first()
        floor = float(getattr(settings, "chatbot_router_min_score", None) or 0.70)
        dealer_tools = agent_tool_labels(db, None, contact_respond_id=args.contact)
        texts = {"A": stored, "B": _variant_b(stored)}

        calls, tokens = 0, [0, 0]
        out: list[dict] = []

        def ask(criteria: dict, state: dict) -> tuple[str | None, float | None]:
            nonlocal calls
            calls += 1
            try:
                ans = jev_client.classify(key, model=model, instructions=instructions, criteria=criteria, state=state)
            except jev_client.JevError as exc:
                return f"failed:{exc.kind}", None
            tokens[0] += ans.input_tokens
            tokens[1] += ans.output_tokens
            return ans.choice, ans.confidence

        for row in baseline:
            for name, text in texts.items():
                choice, conf = ask(_criteria(text, row, OPEN_PAGE_CRITERION, OPEN_RECORD_CRITERION), _state(row))
                out.append({"set": row.get("set") or "baseline", "text_version": name, "expected": row["expected"],
                            "message": row["text"], "choice": choice, "confidence": conf})
        for rid, lang, expected, message, reply in ROWS:
            for name, text in texts.items():
                criteria = _criteria(text, {"tools": dealer_tools}, OPEN_PAGE_CRITERION, OPEN_RECORD_CRITERION)
                for attempt in (1, 2):
                    choice, conf = ask(criteria, dealer_state(message, reply))
                    out.append({"set": "w2-dealer" if expected == "agent" else "w2-control", "id": rid, "lang": lang,
                                "attempt": attempt, "text_version": name, "expected": expected, "message": message,
                                "choice": choice, "confidence": conf})
    finally:
        db.rollback()
        db.close()

    score: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0])  # floor right, pick right, rows
    for r in out:
        pick = r["choice"] if r["choice"] in ("chat", "agent") else "chat"
        at_floor = pick if (r["confidence"] or 0) >= floor else "chat"
        s = score[(r["set"], r["text_version"])]
        s[0] += at_floor == r["expected"]
        s[1] += pick == r["expected"]
        s[2] += 1

    print(f"| set | A floor | B floor | A pick | B pick |   (floor {floor}, Jev calls {calls}, tokens in/out {tokens[0]}/{tokens[1]})")
    print("|---|---|---|---|---|")
    verdict = True
    for set_name in sorted({k[0] for k in score}):
        a, b = score[(set_name, "A")], score[(set_name, "B")]
        print(f"| {set_name} | {a[0]}/{a[2]} | {b[0]}/{b[2]} | {a[1]}/{a[2]} | {b[1]}/{b[2]} |")
        if not set_name.startswith("w2-") and (b[0] < a[0] or b[1] < a[1]):
            verdict = False
    print(f"GATE (no fewer right on any baseline set, floor and pick): {'PASS' if verdict else 'FAIL'}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"floor": floor, "calls": calls, "tokens": tokens, "rows": out}, fh, ensure_ascii=False, indent=2)
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())
