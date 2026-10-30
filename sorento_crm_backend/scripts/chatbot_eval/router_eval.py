"""AGENTIC-P2 gold-set eval for the Jev router (plan "Gold set and eval").

Reads a JSONL gold file (`{id, text, previous_3, label, language}`), asks Jev about each message
exactly as the live router does, and writes `results.jsonl` and `summary.json` into `--out`.
No database. The key comes from env `JEV_API_KEY` and is never written anywhere. `--max-input-tokens`
is the spend guard: the run stops before the next call once the summed input tokens reach it.

    JEV_API_KEY=... python -m scripts.chatbot_eval.router_eval --gold gold.jsonl --out out/
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable

DEFAULT_THRESHOLD = 0.7


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(pct / 100 * len(ordered)) - 1)]


def _rate(wrong: int, of: int) -> float:
    return wrong / of if of else 0.0


def summarise(rows: list[dict]) -> dict[str, Any]:
    agent = [r for r in rows if r["label"] == "agent"]
    chat = [r for r in rows if r["label"] == "chat"]
    per_language: dict[str, dict[str, Any]] = {}
    for r in rows:
        lang = per_language.setdefault(r["language"], {"n": 0, "hits": 0, "agent": 0, "missed": 0, "chat": 0, "wasted": 0})
        lang["n"] += 1
        lang["hits"] += r["route"] == r["label"]
        if r["label"] == "agent":
            lang["agent"] += 1
            lang["missed"] += r["route"] != "agent"
        else:
            lang["chat"] += 1
            lang["wasted"] += r["route"] == "agent"
    times = [r["ms"] for r in rows]
    return {
        "n": len(rows),
        "agreement": _rate(sum(r["route"] == r["label"] for r in rows), len(rows)),
        "missed_agent_rate": _rate(sum(r["route"] != "agent" for r in agent), len(agent)),
        "wasted_agent_rate": _rate(sum(r["route"] == "agent" for r in chat), len(chat)),
        "per_language": {
            k: {
                "n": v["n"],
                "agreement": _rate(v["hits"], v["n"]),
                "missed_agent_rate": _rate(v["missed"], v["agent"]),
                "wasted_agent_rate": _rate(v["wasted"], v["chat"]),
            }
            for k, v in sorted(per_language.items())
        },
        "failures": sum(r.get("reason") == "router_failed" for r in rows),
        "p50_ms": _percentile(times, 50),
        "p95_ms": _percentile(times, 95),
        "input_tokens": sum(r["input_tokens"] for r in rows),
    }


def main(argv: list[str] | None = None, *, choose: Callable[..., dict] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Jev router over a labelled gold set.")
    parser.add_argument("--gold", required=True, help="JSONL: id, text, previous_3, label, language")
    parser.add_argument("--out", required=True, help="directory for results.jsonl and summary.json")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--max-input-tokens", type=int, default=None)
    args = parser.parse_args(argv)

    key = os.environ.get("JEV_API_KEY", "").strip()
    if choose is None and not key:
        print("JEV_API_KEY is not set; refusing to run.", file=sys.stderr)
        return 2

    from app.services import ai_prompt_registry
    from app.services.chatbot import jev_client, router

    instructions = ai_prompt_registry.PROMPT_KEYS[router.PROMPT_KEY].fallback()
    call = choose or jev_client.choose  # looked up at call time

    items = [json.loads(line) for line in Path(args.gold).read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit is not None:
        items = items[: args.limit]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    spent = 0
    # One line per item as it finishes, so a crash keeps the earlier rows.
    with (out / "results.jsonl").open("w", encoding="utf-8") as results:
        for item in items:
            if args.max_input_tokens is not None and spent >= args.max_input_tokens:
                print(f"Spend guard: stopped after {len(rows)} items at {spent} input tokens.", file=sys.stderr)
                break
            history = [{**ex, "answered_by": ex.get("answered_by") or "bot"} for ex in item.get("previous_3") or []]
            base = {"id": item["id"], "label": item["label"], "language": item.get("language") or "unknown"}
            started = time.monotonic()
            try:
                answer = call(
                    key,
                    state=router.build_state(item["text"], history),
                    instructions=instructions,
                    criteria=router.CRITERIA,
                )
                score = float(answer["probabilities"]["agent"])
            except (jev_client.JevError, KeyError, TypeError, ValueError):
                # A failed call or an answer without the `agent` probability: the live router sends it to the
                # bot as `router_failed` and the eval counts it the same way. Anything else is a bug and stops the run.
                row = {**base, "route": "chat", "reason": "router_failed", "score": None,
                       "ms": (time.monotonic() - started) * 1000, "input_tokens": 0}
            else:
                tokens = int(answer.get("input_tokens") or 0)
                spent += tokens
                row = {**base, "route": "agent" if score >= args.threshold else "chat", "reason": "jev",
                       "score": score, "ms": (time.monotonic() - started) * 1000, "input_tokens": tokens}
            rows.append(row)
            results.write(json.dumps(row, ensure_ascii=False) + "\n")
            results.flush()

    (out / "summary.json").write_text(
        json.dumps(summarise(rows), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
