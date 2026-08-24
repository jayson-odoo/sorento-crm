"""AI-assistant self-challenge harness.

Drives ``AIAssistantChatService.respond()`` over a broad question bank (how-to,
data lookup, analytical, novice/how-to-use, definition, edge/vague, write) for a
seeded admin user, capturing per-question: parser intent + confidence, bound
tool, tool calls + their ok/error, whether it clarified/hedged, latency, and the
answer. Writes a markdown + JSON report for grading.

This is the measurement loop for the M3 push AND the seed for the M3b eval
dataset. Baseline runs use ``dry_run=True`` so write-capable tools are suppressed
(a "file a complaint" question can never submit a real record).

Usage:
    venv/bin/python scripts/ai_self_challenge.py [--category how_to] [--limit N] \
        [--out scratch/report] [--live-writes]
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text

from app.database import SessionLocal
from app.services.ai_assistant_service import AIAssistantChatService

# The act-as user (EXTERNAL_API_KEY_ACT_AS_USER_ID) - has the view permissions
# the assistant/MCP need. Override with --user.
DEFAULT_USER_ID = "a4b15bc3-5f65-4ff3-aed8-785575a59ce3"


@dataclass
class Q:
    q: str
    category: str
    note: str = ""  # what a satisfactory answer looks like / why it's here


# --------------------------------------------------------------------------- #
# Variety question bank - the acceptance surface for "satisfactory answers".    #
# --------------------------------------------------------------------------- #
BANK: list[Q] = [
    # --- how_to (guide-backed) ---
    Q("how do I upload a packing list?", "how_to", "guide steps + FE links"),
    Q("how to submit a stock inquiry", "how_to"),
    Q("how do I send a purchase request for approval?", "how_to"),
    Q("how do I approve a purchase request from the email link?", "how_to"),
    Q("how do I attach a photo to a complaint?", "how_to"),
    Q("how do I access the portal with OTP?", "how_to"),
    Q("how do I replace an attachment on a product?", "how_to"),
    # --- data lookup ---
    Q("which products are on promotion right now?", "data"),
    Q("how many Hanlim orders were placed in 2026?", "data", "name→uuid coercion"),
    Q("what incoming shipments are arriving this month?", "data"),
    Q("list delivery orders for Hanlim last month", "data"),
    Q("what is the stock on hand for water closets?", "data"),
    Q("show me open complaints", "data"),
    # --- analytical / aggregate (some may have NO tool → gap) ---
    Q("analyze the sponsorship value for our top sponsors", "analytical", "likely MISSING tool"),
    Q("who are the top 5 customers by order count?", "analytical"),
    Q("what is the average delivery time for Hanlim orders?", "analytical"),
    Q("which product has the most complaints?", "analytical"),
    Q("what is the total order value in 2026 for Hanlim?", "analytical"),
    Q("how many complaints were resolved last month?", "analytical"),
    # --- novice / how-to-use / capability ---
    Q("what can you do?", "capability"),
    Q("what kind of questions can I ask you?", "capability"),
    Q("I'm new here, how do I use this system?", "how_to_use"),
    # --- definition ---
    Q("what does 'processed by cs' mean?", "definition"),
    Q("what is a GRN?", "definition"),
    Q("what's the difference between a DO and an SO?", "definition"),
    # --- edge / vague (SHOULD clarify, not guess) ---
    Q("do the thing", "vague", "must clarify"),
    Q("show me the stuck one", "vague", "must clarify which record"),
    Q("what about last month?", "vague", "must clarify subject"),
    Q("the hanlim one", "vague", "must clarify which/what"),
    # --- write (SHOULD confirm before submitting) ---
    Q("I want to file a complaint about a broken tap", "write", "guide fields, no submit w/o confirm"),
    Q("raise a stock inquiry for me", "write"),
    Q("close complaint C-1042", "write", "record_action → confirm"),
    Q("submit a purchase request", "write"),
]


@dataclass
class Result:
    q: str
    category: str
    note: str
    intent: str | None = None
    confidence: float | None = None
    needs_clarification: bool | None = None
    bound_tools: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_errors: list[str] = field(default_factory=list)
    answer: str = ""
    latency_ms: int = 0
    error: str | None = None


def _read_parse(db, message_id: str) -> tuple[str | None, float | None, bool | None]:
    """Pull intent/confidence/needs_clarification from the semantic_parser span."""
    row = db.execute(
        text(
            "select s.output_json from ai_assistant_spans s "
            "join ai_assistant_traces t on s.trace_id = t.id "
            "where t.message_id = :m and s.name = 'semantic_parser' limit 1"
        ),
        {"m": message_id},
    ).first()
    if not row or not row[0]:
        return None, None, None
    try:
        payload = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        content = payload.get("content")
        parsed = content if isinstance(content, dict) else json.loads(content)
        return (
            parsed.get("intent"),
            parsed.get("confidence"),
            (parsed.get("signals") or {}).get("needs_clarification"),
        )
    except Exception:
        return None, None, None


def run(bank: list[Q], user_id: str, dry_run: bool) -> list[Result]:
    results: list[Result] = []
    for i, item in enumerate(bank, 1):
        db = SessionLocal()
        r = Result(q=item.q, category=item.category, note=item.note)
        started = time.perf_counter()
        try:
            svc = AIAssistantChatService(db)
            _conv, msg = svc.respond(
                user_id=user_id,
                conversation_id=None,
                message=item.q,
                page_snapshot=None,
                dry_run=dry_run,
            )
            r.latency_ms = int((time.perf_counter() - started) * 1000)
            r.answer = (msg.content or "").strip()
            meta = msg.metadata_json or {}
            r.bound_tools = [
                s.get("title") for s in (meta.get("sources") or []) if s.get("is_current")
            ]
            for tc in meta.get("tool_calls") or []:
                if isinstance(tc, dict):
                    r.tool_calls.append({"tool": tc.get("tool_name"), "ok": tc.get("ok")})
                    if tc.get("ok") is False:
                        r.tool_errors.append(str(tc.get("tool_name")))
            r.intent, r.confidence, r.needs_clarification = _read_parse(db, str(msg.id))
        except Exception as exc:  # noqa: BLE001
            r.error = f"{type(exc).__name__}: {exc}"
            r.latency_ms = int((time.perf_counter() - started) * 1000)
        finally:
            db.close()
        results.append(r)
        print(f"[{i}/{len(bank)}] ({item.category}) {item.q[:55]!r} "
              f"intent={r.intent} tool={r.bound_tools} err={r.tool_errors or r.error or '-'} "
              f"{r.latency_ms}ms")
    return results


def to_markdown(results: list[Result]) -> str:
    lines = ["# AI self-challenge report", ""]
    by_cat: dict[str, list[Result]] = {}
    for r in results:
        by_cat.setdefault(r.category, []).append(r)
    for cat, rs in by_cat.items():
        lines.append(f"## {cat}  ({len(rs)})")
        for r in rs:
            lines.append(f"### Q: {r.q}")
            if r.note:
                lines.append(f"_expect: {r.note}_")
            lines.append(
                f"- intent=`{r.intent}` conf=`{r.confidence}` "
                f"needs_clarify=`{r.needs_clarification}` bound_tool=`{r.bound_tools}` "
                f"tool_calls=`{r.tool_calls}` errors=`{r.tool_errors or r.error}` "
                f"latency=`{r.latency_ms}ms`"
            )
            ans = (r.answer or "").replace("\n", "\n  ")
            lines.append(f"- answer:\n\n  {ans[:1200]}")
            lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", default=None, help="filter to one category")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--user", default=DEFAULT_USER_ID)
    ap.add_argument("--out", default="scratch/ai_self_challenge")
    ap.add_argument("--live-writes", action="store_true", help="allow write tools (DANGER)")
    args = ap.parse_args()

    bank = BANK
    if args.category:
        bank = [q for q in bank if q.category == args.category]
    if args.limit:
        bank = bank[: args.limit]

    results = run(bank, args.user, dry_run=not args.live_writes)

    md = to_markdown(results)
    with open(f"{args.out}.md", "w") as f:
        f.write(md)
    with open(f"{args.out}.json", "w") as f:
        json.dump([r.__dict__ for r in results], f, indent=2, default=str)
    print(f"\nwrote {args.out}.md and {args.out}.json ({len(results)} questions)")


if __name__ == "__main__":
    main()
