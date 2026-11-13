"""CHATBOT-SPEED hand test: old-vs-new reply time per question, from the Console turns already stored (read-only).

The owner asks the same questions in the Chatbot Console on the copy running main ("old") and on the copy running
the CHATBOT-SPEED branch ("new"). Every Console turn is stored in `chatbot.turns` with its trace; this script reads
them back and prints one Markdown row per question:

  question | before the parser old | new | saved | whole turn old | new | saved | same answer

"Before the parser" is the `understood` stage minus the parser's own call (`facts.latency_ms`): the part these fixes
speed up, with the model's run-to-run noise left out. A turn is "new" when its `span_extract` event carries
`prep_ms` (only the new code writes it). Each cell is the median of every run of that question on that code (ask the
questions in 3 rounds); the warm-up message ("hi") is left out.
Reads only; makes no model call; prints the question and reply text on the machine it runs on, nothing else.

    SORENTO_ENV_FILE=<copy env> venv/bin/python -m scripts.chatbot_eval.speed_table --minutes 120
"""
from __future__ import annotations

import argparse
import statistics
from typing import Any


def arm(trace: list[dict[str, Any]]) -> str:
    """'new' when the turn's span event carries `prep_ms` (this lane's code), else 'old'."""
    for entry in trace or []:
        if isinstance(entry, dict) and entry.get("kind") == "span_extract":
            return "new" if "prep_ms" in entry else "old"
    return "old"


def measure(turn: dict[str, Any]) -> dict[str, Any]:
    """One stored turn -> its times in ms (`before_parser_ms` = understood stage minus the parser call)."""
    und = par = None
    for entry in turn.get("trace") or []:
        if isinstance(entry, dict) and entry.get("stage") == "understood":
            und = entry.get("ms")
            par = (entry.get("facts") or {}).get("latency_ms")
    before = und - par if isinstance(und, int) and isinstance(par, int) else None
    return {"turn_ms": turn.get("turn_ms"), "before_parser_ms": before, "reply": turn.get("reply") or ""}


#: The warm-up message sent after each restart; not a question, never counted.
WARMUPS = ("hi",)


def _median(values: list[Any]) -> Any:
    values = [v for v in values if isinstance(v, (int, float))]
    return int(statistics.median(values)) if values else None


def _summary(measured: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not measured:
        return None
    return {
        "runs": len(measured),
        "turn_ms": _median([m["turn_ms"] for m in measured]),
        "before_parser_ms": _median([m["before_parser_ms"] for m in measured]),
        "replies": {m["reply"].strip() for m in measured},
    }


def pair(turns: list[dict[str, Any]], warmups: tuple[str, ...] = WARMUPS) -> list[dict[str, Any]]:
    """Per question (first-seen order): the median of every old and every new run, the savings, and the answer check
    (every reply the new code gave also came back from the old code: model wording that varies inside one arm is not
    a change). The warm-up message is left out."""
    runs: dict[str, dict[str, list[dict[str, Any]]]] = {}
    order: list[str] = []
    skip = {w.strip().lower() for w in warmups}
    for turn in sorted(turns, key=lambda t: t.get("at") or 0):
        question = (turn.get("text") or "").strip()
        if not question or question.lower() in skip:
            continue
        if question not in runs:
            runs[question] = {"old": [], "new": []}
            order.append(question)
        runs[question][arm(turn.get("trace") or [])].append(measure(turn))
    rows = []
    for question in order:
        old, new = _summary(runs[question]["old"]), _summary(runs[question]["new"])

        def saved(key: str) -> Any:
            if old and new and old[key] is not None and new[key] is not None:
                return old[key] - new[key]
            return None

        same = new["replies"] <= old["replies"] if old and new else None
        rows.append({
            "question": question, "old": old, "new": new, "answer_same": same,
            "saved_before_parser_ms": saved("before_parser_ms"), "saved_turn_ms": saved("turn_ms"),
        })
    return rows


def _s(ms: Any) -> str:
    return f"{ms / 1000:.1f}" if isinstance(ms, (int, float)) else "-"


def render(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| Question | Before the parser, old (s) | new (s) | Saved (s) | Whole turn, old (s) | new (s) | Saved (s) "
        "| Same answer |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        old, new = r["old"] or {}, r["new"] or {}
        same = {True: "yes", False: "NO", None: "-"}[r["answer_same"]]
        lines.append(
            f"| {r['question']} | {_s(old.get('before_parser_ms'))} | {_s(new.get('before_parser_ms'))} | "
            f"{_s(r['saved_before_parser_ms'])} | {_s(old.get('turn_ms'))} | {_s(new.get('turn_ms'))} | "
            f"{_s(r['saved_turn_ms'])} | {same} |"
        )

    def col(get: Any) -> str:
        return _s(_median([get(r) for r in rows]))

    lines.append(
        f"| **Median** | {col(lambda r: (r['old'] or {}).get('before_parser_ms'))} | "
        f"{col(lambda r: (r['new'] or {}).get('before_parser_ms'))} | {col(lambda r: r['saved_before_parser_ms'])} | "
        f"{col(lambda r: (r['old'] or {}).get('turn_ms'))} | {col(lambda r: (r['new'] or {}).get('turn_ms'))} | "
        f"{col(lambda r: r['saved_turn_ms'])} | |"
    )
    return "\n".join(lines)


def load(minutes: int) -> list[dict[str, Any]]:
    """The Console turns of the last `minutes`, in the shape `pair` reads."""
    from datetime import datetime, timedelta, timezone

    import app.main  # noqa: F401 - registers every model
    from app.database import SessionLocal
    from app.models.chatbot_turn import ChatbotTurn
    from app.services.chatbot.analytics.labeller import _reply_text
    from app.services.chatbot.turn.memory import _turn_message_text

    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    db = SessionLocal()
    try:
        rows = (
            db.query(ChatbotTurn)
            .filter(ChatbotTurn.ingress == "console", ChatbotTurn.status == "done", ChatbotTurn.created_at >= since)
            .order_by(ChatbotTurn.created_at)
            .all()
        )
        return [
            {
                "text": _turn_message_text(r),
                "reply": _reply_text(r),
                "turn_ms": int((r.finished_at - r.started_at).total_seconds() * 1000)
                if r.started_at and r.finished_at else None,
                "at": r.created_at.timestamp() if r.created_at else 0,
                "trace": r.trace if isinstance(r.trace, list) else [],
            }
            for r in rows
        ]
    finally:
        db.rollback()
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--minutes", type=int, default=120, help="read Console turns of the last N minutes")
    args = parser.parse_args()
    print(render(pair(load(args.minutes))))


if __name__ == "__main__":
    main()
