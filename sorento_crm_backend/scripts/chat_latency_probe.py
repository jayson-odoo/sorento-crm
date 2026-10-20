"""CHAT-LATENCY-SCOUT probe: time one `check_stock` chatbot turn stage by stage.

Runs `engine.run_turn` in-process against whatever database `SORENTO_ENV_FILE` names, with
the parser LLM stubbed (the parser is measured in prod at a flat ~3.1 s and is NOT what this
probe looks at). The MCP server and the backend must be running locally
(`ai_assistant_mcp_url`, default http://localhost:8765/mcp, and the backend it calls), so
the stock read takes the same double HTTP hop it takes in production.

Prints:
  * the turn's own trace (stage -> ms) and its `tool` events,
  * every outbound HTTP request the engine process made (method, url, ms),
  * SQL statement count and total ms in the engine process, per stage,
  * any LLM request (blocked here, counted, so a hidden second model call shows up).

Synthetic data only; never point it at a shared database.

    SORENTO_ENV_FILE=.env.scout venv/bin/python -m scripts.chat_latency_probe --code SRT1001-BK --runs 3
"""
from __future__ import annotations

import argparse
import json
import time
import uuid
from collections import defaultdict
from typing import Any

import httpx
from sqlalchemy import event, text

import app.main  # noqa: F401 - registers every model
from app.database import SessionLocal, engine as db_engine
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.contracts import Envelope
from app.services.chatbot.head import parser as parser_mod

SQL: dict[str, list[float]] = defaultdict(list)
HTTP: list[dict[str, Any]] = []
LLM: list[dict[str, Any]] = []
STMTS: list[tuple[float, str, str]] = []
_current = {"label": "pre"}


def _install_sql_counter() -> None:
    @event.listens_for(db_engine, "before_cursor_execute")
    def _before(conn, cursor, statement, params, context, executemany):  # noqa: ANN001
        conn.info.setdefault("t0", []).append(time.perf_counter())

    @event.listens_for(db_engine, "after_cursor_execute")
    def _after(conn, cursor, statement, params, context, executemany):  # noqa: ANN001
        t0 = conn.info["t0"].pop()
        ms = (time.perf_counter() - t0) * 1000
        SQL[_current["label"]].append(ms)
        STMTS.append((ms, _current["label"], " ".join(statement.split())[:220]))


def _install_http_counter(live_llm: bool) -> None:
    """Wrap `send` on httpx AND httpx2 (the OpenAI SDK ships its own fork, `httpx2`, so a
    hook on httpx alone misses every chat completion)."""
    import httpx2

    for mod in (httpx, httpx2):
        real_send = mod.Client.send

        def send(self, request, *args, _real=real_send, _mod=mod, **kwargs):  # noqa: ANN001
            url = str(request.url)
            is_llm = "openai.com" in url or "anthropic.com" in url or "googleapis" in url
            if is_llm and not live_llm:
                LLM.append({"url": url, "ms": 0.0})
                raise _mod.ConnectError("blocked by chat_latency_probe", request=request)
            t0 = time.perf_counter()
            try:
                return _real(self, request, *args, **kwargs)
            finally:
                ms = round((time.perf_counter() - t0) * 1000, 1)
                if is_llm:
                    LLM.append({"url": url, "ms": ms})
                else:
                    body = request.content[:160].decode("utf-8", "replace") if request.content else ""
                    HTTP.append({"url": url, "ms": ms, "body": body})

        mod.Client.send = send  # type: ignore[assignment]


def _stub_parser(output: dict[str, Any]) -> None:
    parser_mod.resolve_config = lambda db, *, current_date, override_version_id=None: parser_mod.ParserConfig(  # type: ignore[assignment]
        system_prompt="stub", prompt_version=1, provider="openai", model="gpt-test", api_key="sk-test"
    )
    parser_mod.parse = lambda config, user_block: output  # type: ignore[assignment]


def _stub_access() -> None:
    engine_mod.check_access = lambda db, *, agent_code, contact_id, space_id: {  # type: ignore[assignment]
        "allowed": True, "decision": "allow", "agent_name": "General Enquiries",
        "attributes": None, "all_attributes_allowed": None,
    }
    engine_mod.default_space_id = lambda db: "364817"  # type: ignore[assignment]


def _parser_output(codes: list[str], text_: str, qty: int | None = None) -> dict[str, Any]:
    return {
        "message_type": "business_query", "intent_hint": "check_stock", "domain_hint": "inventory",
        "scope_intent": "specific", "is_affirmative": None, "user_goal": "checking stock",
        "access_levels": [], "broaden_axis": None, "date_mode": None, "date_filter_start": None,
        "date_filter_end": None, "match_mode": "and", "demand_qty": qty,
        "entities": [{"raw": code, "hint": "product", "canonical_code": None,
                      "current_message": True, "confident": True} for code in codes],
        "entity_op": "replace_combine", "scope_exclusive": False, "requested_attributes": [],
        "contains_flyer": False, "reference_positions": [], "reference_target": None,
    }


def _envelope(contact_id: int, text_: str) -> Envelope:
    mid = f"ZZT-probe-{uuid.uuid4().hex[:8]}"
    return Envelope(**{
        "contact": {"id": contact_id, "firstName": "ZZT",
                    "custom_fields": [{"name": "is_human_intervened", "value": "false"}]},
        "message": {"event_type": "message.received", "contact": {"id": contact_id},
                    "message": {"messageId": mid, "contactId": contact_id, "channelId": "whatsapp",
                                "traffic": "incoming", "message": {"type": "text", "text": text_}}},
    })


def _ensure_contact(contact_id: int) -> None:
    db = SessionLocal()
    try:
        db.execute(text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "SELECT gen_random_uuid()::text, :cid, '+60000000001', '{}'::jsonb "
            "WHERE NOT EXISTS (SELECT 1 FROM respond_contacts WHERE respond_io_id = :cid)"
        ), {"cid": str(contact_id)})
        db.commit()
    finally:
        db.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", default="SRT1001-BK", help="product code; comma-separate for a multi-product ask")
    ap.add_argument("--top-sql", type=int, default=0, help="print the N slowest statements")
    ap.add_argument("--qty", type=int, default=None, help="demand_qty the parser reports")
    ap.add_argument("--text", default=None)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--contact", type=int, default=900000777)
    ap.add_argument("--live-llm", action="store_true",
                    help="let non-parser LLM calls (code reader, spec reader, embeddings) go out, timed")
    args = ap.parse_args()

    _install_sql_counter()
    _install_http_counter(args.live_llm)
    _stub_access()
    codes = [c.strip() for c in args.code.split(",") if c.strip()]
    msg = args.text or (f"{args.qty} pcs " if args.qty else "") + f"stock for {' '.join(codes)}?"
    _stub_parser(_parser_output(codes, msg, args.qty))
    _ensure_contact(args.contact)

    # Label each SQL statement with the stage in progress: TurnTrace.record closes a stage.
    from app.services.chatbot import trace as trace_mod
    real_record = trace_mod.TurnTrace.record

    def record(self, stage, **kw):  # noqa: ANN001
        _current["label"] = f"->{stage}"
        out = real_record(self, stage, **kw)
        _current["label"] = f"after {stage}"
        return out

    trace_mod.TurnTrace.record = record  # type: ignore[assignment]

    for run in range(args.runs):
        SQL.clear(); HTTP.clear(); LLM.clear(); STMTS.clear(); _current["label"] = "pre"
        t0 = time.perf_counter()
        result = engine_mod.run_turn(_envelope(args.contact, msg), session_factory=SessionLocal)
        wall = (time.perf_counter() - t0) * 1000
        db = SessionLocal()
        row = db.execute(text("SELECT trace, status, error FROM chatbot.turns WHERE id = :i"),
                         {"i": result.turn_id}).first()
        db.close()
        print(f"\n=== run {run + 1}: wall {wall:.0f} ms status={row.status if row else '?'} "
              f"err={(row.error or '')[:120] if row else ''}")
        for rec in (row.trace if row else []) or []:
            if rec.get("stage"):
                print(f"  stage {rec['stage']:<11} {rec['ms']:>6} ms  {rec.get('summary', '')[:90]}")
            else:
                slim = {k: v for k, v in rec.items() if k in ("kind", "name", "ms", "domain", "rung", "skipped")}
                print(f"  event {json.dumps(slim)[:160]}")
        print("  http:")
        for h in HTTP:
            print(f"    {h['ms']:>7} ms  {h['url']}  {h['body'][:110]}")
        print(f"  http total {sum(h['ms'] for h in HTTP):.0f} ms over {len(HTTP)} calls")
        print("  sql by stage (count / ms):")
        for label, times in SQL.items():
            print(f"    {label:<20} {len(times):>5} / {sum(times):8.1f}")
        print(f"  sql total {sum(len(v) for v in SQL.values())} stmts / {sum(sum(v) for v in SQL.values()):.0f} ms")
        for ms, label, stmt in sorted(STMTS, reverse=True)[: args.top_sql]:
            print(f"    {ms:7.1f} ms [{label}] {stmt}")
        print(f"  non-parser llm calls ({'live' if args.live_llm else 'blocked'}): {len(LLM)}, "
              f"{sum(c['ms'] for c in LLM):.0f} ms")
        for c in LLM:
            print(f"    {c['ms']:>7} ms  {c['url']}")
        reply = getattr(result, "reply", None) or (result.item or {}).get("reply") if hasattr(result, "item") else None
        print(f"  reply: {str(reply)[:300]}")


if __name__ == "__main__":
    main()
