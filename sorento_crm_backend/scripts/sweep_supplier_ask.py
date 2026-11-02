"""SUPPLIER-ASK robustness sweep (#2066 fix round 3): supplier phrasings x picks through the Chatbot Console.

Every turn is a console DRY RUN (`console_service.run_console_turn`, the same path the console page posts to:
`is_test`, zero writes outside `chatbot.turns`), pinned to one parser version (`--parser-version`, required; the
console pin also runs its paired span prompt, `engine._span_override`). Each case starts a new conversation
(`session_vars={}`) and its picks carry the turn's own `session_vars` forward, as the console does.

Spend: a dry run writes no usage row, so each turn is priced off its own trace (every `prompt_tokens` /
`completion_tokens` / `cached_tokens` the trace holds, the parser's `understood` facts and the span pass's
`span_extract` event included) against `llm_model_prices`. A model with no price row is charged
`--unpriced-usd` per call, and so is a turn whose trace reports no tokens at all (a call that writes none there,
such as the clarifier, would otherwise count as free). The sweep stops BEFORE the next turn once the running total
plus the dearest turn so far (at least `--unpriced-usd`) would pass `--cap-usd` (default 0.50). That is a
projection, not a meter: a turn dearer than every earlier one can still go past the cap, by at most its own cost. One ledger line per turn is appended to `--ledger`
(JSON lines: case, turn, text, model, tokens, usd, running usd).

Usage, from `sorento_crm_backend/` with the copy's backend env (`DATABASE_URL`, provider keys) in place:

    venv/bin/python -m scripts.sweep_supplier_ask --contact 487555417 --parser-version <the version publish_supplier_ask_prompts printed> \\
        --ledger ../state/ledger/supplier-ask-sweep.jsonl --out /tmp/supplier-sweep.md

Writes a Markdown table (case, turn, text, verdict, tool, supplier ids, window, reply first line, usd) to `--out`
and prints it. Exit 1 when any graded turn FAILs, 2 when the cap stopped the sweep, 3 when the pinned parser
version does not exist.

Grading (per turn, `expect`):
  ask        the reply asks (numbered lines, never the order-kind clarifier) and no PO / order list ran
  po:N       the PO list ran with exactly N supplier ids (po:N+ = at least N)
  miss       no PO / order list ran at all (a refusal or a not-found line)
  not_po     a control turn: the PO list did not run with a supplier
A turn whose message named a supplier FAILs whenever any PO or order list ran without `supplier_ids`, whatever the
expectation. `from` / `to` check the PO tool's `expected_date_from` / `expected_date_to`.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

PO_TOOL = "crm_procurement_po_placed_list"
ORDER_TOOLS = ("crm_report_ask", "crm_outstanding_report", "crm_orders_list", "crm_sales_report")


@dataclass
class Turn:
    text: str
    expect: str
    date_from: str | None = None
    date_to: str | None = None


@dataclass
class Case:
    name: str
    turns: list[Turn] = field(default_factory=list)
    names_supplier: bool = True


def _c(name: str, *turns: tuple, names_supplier: bool = True) -> Case:
    return Case(name, [Turn(*t) for t in turns], names_supplier)


#: The phrasing table: supplier in English / Chinese / typo; with and without a product code; a year, "after <year>",
#: a month; picks by number, by code, "all", "both"; outstanding vs PO vs order words. Dates assume today is in 2026.
CASES: list[Case] = [
    _c("en-outstanding-pick1", ("outstanding for taiyang", "ask"), ("1", "po:1")),
    _c("zh-po-all", ("outstanding PO for 太阳", "ask"), ("all", "po:3")),
    _c("typo-pos-1and2", ("POs for taiyng", "ask"), ("1 and 2", "po:2")),
    _c("zh-outstanding-bycode", ("the outstanding for 太阳", "ask"), ("400-X008", "po:1")),
    _c("en-product-all", ("outstanding for taiyang for SRTW2600", "ask"), ("all", "po:3")),
    _c("owner-turn1-after-year", ("outstaing for 太阳 for SRTW2600 after 2025", "ask"),
       ("all", "po:3", "2026-01-01")),
    _c("owner-turn4-in-year", ("outstaing for 太阳 for SRTW2600 in 2026", "ask"),
       ("1", "po:1", "2026-01-01", "2026-12-31")),
    _c("en-po-month", ("PO for taiyang in March", "ask"), ("2", "po:1", "2026-03-01", "2026-03-31")),
    _c("order-word-all", ("taiyang order outstanding", "ask"), ("all", "po:3")),
    _c("open-orders-spaced", ("open orders with tai yang", "ask"), ("3", "po:1")),
    _c("zh-after-2024", ("pending PO 太阳 after 2024", "ask"), ("all", "po:3", "2025-01-01")),
    _c("code-direct", ("outstanding PO for 400-X008", "po:1")),
    _c("code-direct-year", ("POs for 400-X006 in 2026", "po:1", "2026-01-01", "2026-12-31")),
    _c("placed-product-1and3", ("orders placed with taiyang for SRTW2600", "ask"), ("1 and 3", "po:2")),
    _c("since-year", ("outstanding for taiyang since 2025", "ask"), ("all", "po:3", "2025-01-01")),
    _c("before-year", ("outstanding for 太阳 before 2026", "ask"), ("1", "po:1", None, "2025-12-31")),
    _c("malay-zh-semua", ("ada PO pembekal 太阳 ke", "ask"), ("semua", "po:3")),
    _c("zh-only-all", ("太阳的未交货采购单", "ask"), ("全部", "po:3")),
    _c("both-over-three", ("outstanding for taiyang", "ask"), ("both", "ask")),
    _c("product-last-month", ("POs for taiyang SRTW2600 last month", "ask"), ("1", "po:1")),
    _c("typo-taiyan-2", ("outstanding PO taiyan", "ask"), ("2", "po:1")),
    _c("unknown-supplier", ("outstanding PO for zzqqxx supplier", "miss")),
    _c("zh-quarter-all", ("outstanding PO for 太阳 in Q1 2026", "ask"), ("all", "po:3", "2026-01-01", "2026-03-31")),
    # Fix round 4 (crew): the owner's turn 1, five times over (v194 asked on 2 of 5): each a new conversation.
    *[_c(f"owner-turn1-repeat-{n}", ("outstaing for 太阳 for SRTW2600 after 2025", "ask")) for n in range(1, 6)],
    _c("control-stock", ("stock SRTW2600", "not_po"), names_supplier=False),
    _c("control-order-outstanding", ("outstanding for SRTW2600", "not_po"), names_supplier=False),
]


def _token_calls(trace: Any) -> list[dict[str, Any]]:
    """Every LLM call the trace reports: a dict with integer `prompt_tokens`, with the nearest `model` above it."""
    out: list[dict[str, Any]] = []

    def walk(node: Any, model: Any) -> None:
        if isinstance(node, dict):
            here = node.get("model") or model
            if isinstance(node.get("prompt_tokens"), int) and node.get("prompt_tokens"):
                out.append({
                    "model": str(here or ""),
                    "prompt": int(node.get("prompt_tokens") or 0),
                    "completion": int(node.get("completion_tokens") or 0),
                    "cached": int(node.get("cached_tokens") or 0),
                })
                return
            for value in node.values():
                walk(value, here)
        elif isinstance(node, list):
            for value in node:
                walk(value, model)

    walk(trace, None)
    return out


def _price_table(db) -> dict[str, tuple[Decimal, Decimal, Decimal]]:
    """`llm_model_prices`, over the repo's own seeded prices (`analytics_connector.prices.SEED_PRICES`, which carry the
    Gemini parser model a copy's table may lack). A row in the table wins."""
    from sqlalchemy import text

    from app.services.analytics_connector.prices import SEED_PRICES

    out = {
        model: (Decimal(i), Decimal(c if c is not None else i), Decimal(o)) for model, (i, c, o, _n) in SEED_PRICES.items()
    }
    rows = db.execute(
        text("SELECT model, input_usd_per_1m, cached_input_usd_per_1m, output_usd_per_1m FROM llm_model_prices")
    ).all()
    out.update({str(m): (Decimal(i), Decimal(c if c is not None else i), Decimal(o)) for m, i, c, o in rows})
    return out


def _price_of(model: str, prices: dict[str, tuple[Decimal, Decimal, Decimal]]):
    """The price row for a model id as a trace writes it: exact, without a `models/` prefix, else the longest priced
    id it starts with (a dated or preview suffix). None when nothing matches."""
    name = (model or "").strip().removeprefix("models/")
    if name in prices:
        return prices[name]
    best = max((k for k in prices if name.startswith(k)), key=len, default=None)
    return prices[best] if best else None


def _usd(calls: list[dict[str, Any]], prices: dict[str, tuple[Decimal, Decimal, Decimal]], unpriced: Decimal) -> Decimal:
    total = Decimal(0)
    for call in calls:
        price = _price_of(call["model"], prices)
        if price is None:
            total += unpriced
            continue
        inp, cached, out = price
        fresh = max(call["prompt"] - call["cached"], 0)
        total += (fresh * inp + call["cached"] * cached + call["completion"] * out) / Decimal(1_000_000)
    return total


def _cap_reached(spent: Decimal, dearest: Decimal, floor: Decimal, cap: Decimal) -> bool:
    """Whether the next turn may not run: the total so far plus the dearest turn so far (never less than `floor`)."""
    return spent + max(dearest, floor) > cap


def _tool_events(trace: Any) -> list[tuple[str, dict[str, Any]]]:
    out = []
    for e in trace or []:
        if isinstance(e, dict) and e.get("kind") == "tool":
            # `TurnTrace.add` spreads its payload beside `kind` (crew, round 4); an older nested `payload` still reads.
            payload = e.get("payload") if isinstance(e.get("payload"), dict) else e
            out.append((str(payload.get("name") or ""), dict(payload.get("args") or {})))
    return out


def _grade(turn: Turn, reply: str, tools: list[tuple[str, dict[str, Any]]], names_supplier: bool) -> tuple[str, str]:
    po = [a for n, a in tools if n == PO_TOOL]
    lists = [(n, a) for n, a in tools if n == PO_TOOL or n in ORDER_TOOLS or n.startswith("crm_order")]
    asked = any(ln[:1].isdigit() and ". " in ln for ln in reply.splitlines())
    if names_supplier and any(not a.get("supplier_ids") for _n, a in lists):
        return "FAIL", "a list ran without a supplier filter"
    kind, _, count = turn.expect.partition(":")
    if kind == "ask":
        from app.services.chatbot.lanes.business.report_ask import KIND_QUESTION

        ok = asked and not lists and KIND_QUESTION not in reply
        why = "" if ok else "expected the supplier question and no list"
    elif kind == "po":
        n = len(po[0].get("supplier_ids") or []) if po else 0
        want = int(count.rstrip("+"))
        ok = bool(po) and (n >= want if count.endswith("+") else n == want)
        why = "" if ok else f"expected the PO list with {count} supplier(s), got {n if po else 'no PO list'}"
        if ok and turn.date_from is not None and po[0].get("expected_date_from") != turn.date_from:
            ok, why = False, f"expected_date_from {po[0].get('expected_date_from')} != {turn.date_from}"
        if ok and turn.date_to is not None and po[0].get("expected_date_to") != turn.date_to:
            ok, why = False, f"expected_date_to {po[0].get('expected_date_to')} != {turn.date_to}"
    elif kind == "miss":
        ok = not lists
        why = "" if ok else "expected no list for a supplier nothing matches"
    elif kind == "not_po":
        ok = not [a for a in po if a.get("supplier_ids")]
        why = "" if ok else "a control turn ran the PO list with a supplier"
    else:
        ok, why = False, f"unknown expectation {turn.expect!r}"
    return ("PASS" if ok else "FAIL"), why


def _cell(value: Any, limit: int = 70) -> str:
    text = str(value if value is not None else "").replace("|", "/").replace("\n", " / ")
    return text if len(text) <= limit else text[: limit - 1] + "~"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--contact", required=True, help="respond id of an office staff contact holding the reveals")
    parser.add_argument(
        "--parser-version", type=int, required=True,
        help="the parser version `scripts.publish_supplier_ask_prompts` printed (it carries the after-year sentence)",
    )
    parser.add_argument("--cap-usd", type=Decimal, default=Decimal("0.50"))
    parser.add_argument("--unpriced-usd", type=Decimal, default=Decimal("0.01"))
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--only", nargs="*", help="case names to run (default: all)")
    args = parser.parse_args(argv)

    from app.database import SessionLocal
    from app.models.ai_prompt import AIPromptVersion
    from app.models.chatbot_turn import ChatbotTurn
    from app.services.chatbot import console_service

    db = SessionLocal()
    pinned = (
        db.query(AIPromptVersion)
        .filter(AIPromptVersion.name == "chatbot_semantic_parser", AIPromptVersion.version == args.parser_version)
        .first()
    )
    if pinned is None:
        print(f"refused: no chatbot_semantic_parser v{args.parser_version}", file=sys.stderr)
        return 3
    prices = _price_table(db)
    run_id = f"supplier-sweep-{uuid.uuid4().hex[:8]}"
    rows: list[str] = [
        "| case | turn | text | verdict | why | tool | supplier ids | window | reply (first line) | usd |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    spent, dearest, failed, capped = Decimal(0), Decimal(0), 0, False
    args.ledger.parent.mkdir(parents=True, exist_ok=True)
    cases = [c for c in CASES if not args.only or c.name in args.only]
    try:
        for case in cases:
            session_vars: dict[str, Any] | None = {}
            for i, turn in enumerate(case.turns, 1):
                if _cap_reached(spent, dearest, args.unpriced_usd, args.cap_usd):
                    capped = True
                    break
                result = console_service.run_console_turn(
                    db, contact_respond_id=args.contact, text=turn.text, session_vars=session_vars,
                    prompt_version_id=str(pinned.id), run_id=f"{run_id}-{case.name}",
                )
                row = db.query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).first() if result.turn_id else None
                trace = (row.trace if row is not None else None) or []
                calls = _token_calls(trace)
                usd = _usd(calls, prices, args.unpriced_usd) if calls else args.unpriced_usd
                spent += usd
                dearest = max(dearest, usd)
                tools = _tool_events(trace)
                verdict, why = _grade(turn, result.reply_text or "", tools, case.names_supplier)
                failed += verdict == "FAIL"
                po = next((a for n, a in tools if n == PO_TOOL), None)
                window = f"{(po or {}).get('expected_date_from') or ''}..{(po or {}).get('expected_date_to') or ''}" if po else ""
                with args.ledger.open("a", encoding="utf-8") as ledger:
                    ledger.write(json.dumps({
                        "run": run_id, "case": case.name, "turn": i, "text": turn.text, "turn_id": result.turn_id,
                        "calls": calls, "usd": str(usd), "running_usd": str(spent),
                    }, ensure_ascii=False) + "\n")
                rows.append(
                    f"| {case.name} | {i} | {_cell(turn.text, 50)} | {verdict} | {_cell(why, 60)} | "
                    f"{_cell(tools[0][0] if tools else '')} | {len((po or {}).get('supplier_ids') or []) if po else ''} | "
                    f"{window} | {_cell((result.reply_text or '').splitlines()[0] if result.reply_text else '')} | "
                    f"{usd:.4f} |"
                )
                session_vars = result.session_vars if result.session_vars is not None else session_vars
            if capped:
                break
    finally:
        db.close()
    rows.append("")
    rows.append(
        f"run {run_id}, parser v{args.parser_version}, contact {args.contact}: {len(rows) - 3} turns, "
        f"{failed} FAIL, spent USD {spent:.4f} of {args.cap_usd}{' (CAP REACHED, sweep stopped)' if capped else ''}"
    )
    table = "\n".join(rows)
    args.out.write_text(table + "\n", encoding="utf-8")
    print(table)
    return 2 if capped else (1 if failed else 0)


if __name__ == "__main__":
    sys.exit(main())
