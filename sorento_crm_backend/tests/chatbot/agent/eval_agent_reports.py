"""AGENT-REPORTS live eval: the agent on the T1-T7 transcript and the totals-filters gold, on a DEV Gemini key.

Not a CI test (the file name is not `test_*`). Run it explicitly, on a local or sandbox throwaway database:

    AGENT_EVAL_GEMINI_KEY=<dev key> SORENTO_ENV_FILE=.env.ci-tests \\
        venv/bin/pytest tests/chatbot/agent/eval_agent_reports.py -q -s

Never a prod key. Only the model is live: `crm_resolve` is a fixed fake (Sorento = brand SORENTO, kitchen sink =
category, zqc trading = customer) and `crm_report_ask` answers a card built from the call's own arguments, so the
grade is the ARGUMENTS the agent chose, which is what the prod transcript got wrong. Hanlim is both a customer
and a supplier in the fake world; "delivery to hanlim" must land on the customer with no question, from the
agent's own reading (no special-case code exists for it, on purpose). It prints the pass rate and
the tokens per run, and USD at `AGENT_EVAL_PRICE` ("in,cached,out" per 1M) when given; gemini-3.5-flash has no
owner-approved price row yet (`app/services/analytics_connector/prices.py`).
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import app.main  # noqa: F401
from app.models.chatbot_turn import ChatbotTurn
from app.services.chatbot.agent import loop
from app.services.chatbot.agent import tools as agent_tools
from app.services.chatbot.agent.tools import ToolResult
from tests._pg_fixture import blank_session
from tests.chatbot.agent._seed import all_agent_slugs, seed_agent_contact
from tests.chatbot.agent.test_agent_reports import seed_held, switch

KEY = os.environ.get("AGENT_EVAL_GEMINI_KEY", "")
MODEL = os.environ.get("AGENT_EVAL_MODEL", loop.DEFAULT_MODEL)
GOLD = Path(__file__).resolve().parents[3] / "scripts" / "chatbot_eval" / "gold"
pytestmark = pytest.mark.skipif(not KEY, reason="AGENT_EVAL_GEMINI_KEY (a DEV key) is not set")

#: The fake resolver's world: (kind, name) -> id.
WORLD = {("brand", "SORENTO"), ("brand", "MOCHA"), ("category", "Kitchen Sink"), ("category", "Water Closet"),
         ("customer", "zqc trading"), ("customer", "Hanlim"), ("supplier", "Hanlim")}


def fake_id(kind: str, name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{kind}:{name.lower()}"))


NAMES = {fake_id(k, n): n for k, n in WORLD}


def fake_resolve(db, ctx, args, seen):
    results = []
    for term in args.get("terms") or []:
        folded = str(term).strip().lower()
        matches = [
            {"id": fake_id(k, n), "kind": k, "code": None, "name": n}
            for k, n in sorted(WORLD)
            if (not args.get("kinds") or k in args["kinds"]) and (folded == n.lower() or folded in n.lower())
        ]
        seen.update(m["id"] for m in matches)
        results.append({"term": term, "status": "found" if len(matches) == 1 else ("ambiguous" if matches else "not_found"),
                        "matches": matches})
    return ToolResult("ok", data={"results": results, "skipped_kinds": []})


def _dmy(iso: str | None) -> str:
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m/%Y") if iso else ""


def fake_card(args: dict) -> dict:
    lines = [f"Sales by {args.get('basis')} sales" + (f" by {args['group_by']}" if args.get("group_by") else "")]
    if args.get("company"):
        lines.append(f"Company: {args['company']}")
    for key, label in (("brand_ids", "Brand"), ("category_ids", "Category"), ("customer_ids", "Customer")):
        ids = args.get(key) or []
        if isinstance(ids, str):
            ids = [i.strip() for i in ids.split(",")]
        if ids:
            lines.append(f"{label}: " + ", ".join(NAMES.get(str(i).lower(), "?") for i in ids))
    if args.get("channel"):
        lines.append(f"Channel: {args['channel']}")
    lines.append(f"Period: {_dmy(args.get('date_from'))} - {_dmy(args.get('date_to'))}")
    if args.get("group_by") == "channel":
        lines += ["1. Dealer 1,900 pcs", "2. Project team 370 pcs"]
    lines.append("Total 2,270 pcs · RM 1,066,977.87")
    return {"result_type": "report_ask", "response": "\n".join(lines), "has_result": True, "drill_rows": None,
            "not_applied": []}


class Mcp:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, name, args):
        self.calls.append((name, dict(args)))
        return fake_card(args) if name == "crm_report_ask" else {"items": [], "has_result": False}


def _catalog() -> dict:
    path = os.environ.get("AGENT_EVAL_CATALOG")
    if path:
        return json.loads(Path(path).read_text())
    from sorento_crm_mcp.server import create_mcp_app
    from sorento_crm_mcp.settings import Settings
    import asyncio

    os.environ.setdefault("CRM_BASE_URL", "http://localhost:1")
    os.environ.setdefault("EXTERNAL_API_KEY", "eval-only")
    tools = asyncio.run(create_mcp_app(Settings()).list_tools())
    return {t.name: {"description": t.description or "", "inputSchema": t.inputSchema} for t in tools}


def _names(args: dict, key: str) -> list[str]:
    ids = args.get(key) or []
    if isinstance(ids, str):
        ids = [i.strip() for i in ids.split(",")]
    return sorted(NAMES.get(str(i).lower(), str(i)).lower() for i in ids)


def grade_party(expect: dict, all_calls: list[tuple[str, dict]], asked: bool) -> tuple[bool, str]:
    """`customer_side`: some call names the customer's id, none names the supplier's, and nothing was asked."""
    name = expect["customer_side"]
    customer, supplier = fake_id("customer", name), fake_id("supplier", name)
    flat = [json.dumps(a, default=str).lower() for _, a in all_calls]
    if asked:
        return False, "asked instead of reading the side"
    if any(supplier in f for f in flat):
        return False, "used the supplier"
    if not any(customer in f for f in flat):
        return False, f"no call named the customer ({[n for n, _ in all_calls]})"
    return True, "ok"


def grade(expect: dict, ok_calls: list[dict]) -> tuple[bool, str]:
    if expect.get("ask"):
        return (not ok_calls, "asked" if not ok_calls else f"answered without asking: {ok_calls[-1]}")
    if not ok_calls:
        return False, "no report answered"
    args = ok_calls[-1]
    for key, want in (expect.get("report") or {}).items():
        if key in ("brands", "categories", "customers"):
            got = _names(args, {"brands": "brand_ids", "categories": "category_ids", "customers": "customer_ids"}[key])
            ok = got == sorted(w.lower() for w in want)
        elif key == "measure" and want is None:
            got = args.get("measure")
            ok = got in (None, "", "amount")
        elif key == "company":
            got = args.get("company")
            ok = (got or None) == want if want is None else str(got or "").lower() == want.lower()
        else:
            got = args.get(key)
            ok = (got in (None, "", [])) if want is None else got == want
        if not ok:
            return False, f"{key}: want {want!r}, got {got!r}"
    if expect.get("sorento_named"):
        if str(args.get("company") or "").lower() != "sorento" and _names(args, "brand_ids") != ["sorento"]:
            return False, "Sorento named neither as company nor brand"
    return True, "ok"


def _parser_case(row: dict) -> tuple[dict | None, dict]:
    """The parser gold row as (held state, agent expectation)."""
    held = None
    if row.get("held"):
        label, _, body = row["held"].partition(": {")
        h = json.loads("{" + body)
        if "open question" in label:
            # The bot's open question becomes the agent's own last reply, which history replays.
            question = label.split("open question:", 1)[1].rstrip(")").strip()
            asked = {"company or brand": "Do you mean Sorento the company or the brand?",
                     "basis": "Which do you want: undelivered sales orders or pending delivery orders?"}
            h["_asked"] = asked.get(question, f"Which {question}?")
        args = {k: h.get(k) for k in ("basis", "date_from", "date_to", "group_by", "top_n", "measure", "channel", "company")}
        args["brand_ids"] = [fake_id("brand", b.upper()) for b in h.get("brands") or []]
        args["category_ids"] = [fake_id("category", c.title()) for c in h.get("categories") or []]
        args["customer_ids"] = [fake_id("customer", c.lower()) for c in h.get("customers") or []]
        if h.get("account_types"):
            args["account_types"] = h["account_types"]
        held = {"args": {k: v for k, v in args.items() if v not in (None, "", [])}, "head": ""}
        if h.get("_asked"):
            held["_asked"] = h["_asked"]
    want = row["expect"].get("report_ask") or {}
    if (want.get("kind") == "sales" and not want.get("basis")) or want.get("company_or_brand") or want.get(
        "brand_or_account_type"
    ) or (want.get("kind") == "outstanding" and not want.get("basis")):
        return held, {"ask": True}
    report = {k: want.get(k) for k in ("basis", "date_from", "date_to", "group_by", "channel", "company", "measure")}
    report.update({"brands": want.get("brands") or [], "categories": want.get("categories") or [],
                   "customers": want.get("customers") or []})
    if want.get("frame") == "ranking":
        report["top_n"] = want.get("top_n")
    return held, {"report": report}


def _price() -> tuple[float, float, float] | None:
    raw = os.environ.get("AGENT_EVAL_PRICE")
    return tuple(float(x) for x in raw.split(",")) if raw else None  # type: ignore[return-value]


def _turn(db, contact, text_, catalog, mcp, i):
    provider = loop._WrappedProvider("gemini", KEY, MODEL)
    result = loop.run_agent_turn(db, contact_respond_id=contact["respond_id"], text=text_, provider=provider,
                                 mcp_call=mcp, catalog=catalog)
    row = db.query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).one()
    row.created_at = datetime.now(timezone.utc) - timedelta(minutes=50 - i)
    db.commit()
    return result


def test_live_eval(monkeypatch):
    monkeypatch.setattr(agent_tools, "_resolve", fake_resolve)
    catalog = _catalog()
    outcomes: list[tuple[str, bool, str]] = []
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "cached_tokens": 0, "calls": 0}

    def tally(result):
        for k in usage:
            usage[k] += int(result.usage.get(k) or 0)

    with blank_session() as db:
        # The transcript: one contact, one conversation, turn after turn.
        contact = seed_agent_contact(db, slugs=all_agent_slugs())
        switch(db, True)
        for i, line in enumerate((GOLD / "agent_reports_transcript.jsonl").read_text().splitlines()):
            case = json.loads(line)
            mcp = Mcp()
            result = _turn(db, contact, case["message"], catalog, mcp, i)
            tally(result)
            ok_calls = [a for n, a in mcp.calls if n == "crm_report_ask"]
            passed, why = grade(case["expect"], ok_calls)
            outcomes.append((case["id"], passed, why))
        # The totals-filters gold: a fresh contact each, its held report seeded.
        for line in (GOLD / "parser_report_totals_filters.jsonl").read_text().splitlines():
            row = json.loads(line)
            contact = seed_agent_contact(db, slugs=all_agent_slugs())
            held, expect = _parser_case(row)
            if held:
                asked = held.pop("_asked", None)
                seed_held(db, contact, held, **({"reply": asked} if asked else {}))
            mcp = Mcp()
            result = _turn(db, contact, row["message"], catalog, mcp, 0)
            tally(result)
            ok_calls = [a for n, a in mcp.calls if n == "crm_report_ask"]
            passed, why = grade(expect, ok_calls)
            outcomes.append((row["id"], passed, why))

        # Party side: a fresh contact each, nothing held.
        for line in (GOLD / "agent_reports_party_side.jsonl").read_text().splitlines():
            case = json.loads(line)
            contact = seed_agent_contact(db, slugs=all_agent_slugs())
            mcp = Mcp()
            result = _turn(db, contact, case["message"], catalog, mcp, 0)
            tally(result)
            asked = bool((db.query(ChatbotTurn.response).filter(ChatbotTurn.id == result.turn_id).scalar() or {})
                         .get("asked_back"))
            passed, why = grade_party(case["expect"], mcp.calls, asked)
            outcomes.append((case["id"], passed, why))

    passed = sum(1 for _, p, _ in outcomes if p)
    print(f"\nagent-reports eval: {passed}/{len(outcomes)} passed on {MODEL}")
    for cid, p, why in outcomes:
        print(f"  {'PASS' if p else 'FAIL'} {cid}: {why}")
    print(f"tokens: {usage}")
    price = _price()
    if price:
        p_in, p_cached, p_out = price
        fresh = usage["prompt_tokens"] - usage["cached_tokens"]
        usd = (fresh * p_in + usage["cached_tokens"] * p_cached + usage["completion_tokens"] * p_out) / 1_000_000
        print(f"USD this run: {usd:.4f}")
