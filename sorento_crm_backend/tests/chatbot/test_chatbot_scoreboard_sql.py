"""CHATBOT-SCOREBOARD: the weekly scoreboard SQL measures what it says (AC-5, AC-6, AC-7).

Plan: documentation/plans/chatbot/PLAN-chatbot-scoreboard-12nov.md.

`app/services/chatbot/analytics/scoreboard.sql` is the read-only weekly scoreboard crew runs
on a copy of prod. This runs both statements on fake ZZT rows in a week no real data reaches
(the one parameter, `p.week_from`, is moved to 6 Jan 2031), inside a transaction that is
rolled back. Outcomes are written straight onto the fact rows: the classifier that stamps
them has its own tests (`test_chat_facts_outcome.py`).

The week, all dealer asks, reply 2.0 s each:
* 16 stock asks: 12 answered, 1 quantity question (`clarified`), 1 did-you-mean
  (`answered_empty`, reply asks `product_pick`), 1 dead end (`answered_empty`, nothing
  offered), 1 miss with only an escalation offer (`missed`, `team_pick`).
* 4 order asks, all `technical`: 1 engine failure, 1 send not confirmed whose outgoing row was
  read (delivered: not a failure), 1 send not confirmed with no outgoing row, 1 send not
  confirmed whose outgoing row failed.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests._pg_fixture import pg_session

# CREATE OR REPLACE VIEW on the shared analytics_connector schema (the SQL reads
# `analytics_connector.llm_calls`): same serial step as tests/analytics_connector/test_turn_costs.py.
pytestmark = pytest.mark.serial_ddl

SQL_PATH = Path(__file__).resolve().parents[2] / "app/services/chatbot/analytics/scoreboard.sql"
WEEK = "2031-01-06"  # a Monday no real row reaches
ASKED = datetime(2031, 1, 7, 2, 0, tzinfo=timezone.utc)  # Tue 10:00 Malaysia
CONTACT = f"ZZT-sb-{uuid.uuid4().hex[:8]}"


def _statements() -> tuple[str, str]:
    sql = SQL_PATH.read_text()
    first, second = sql.split("-- Statement 2", 1)
    out = []
    for stmt in (first, "-- Statement 2" + second):
        moved, n = re.subn(r"DATE '\d{4}-\d{2}-\d{2}' AS week_from", f"DATE '{WEEK}' AS week_from", stmt)
        assert n == 1, "each statement carries the one week_from parameter"
        out.append(moved.strip().rstrip(";"))
    return out[0], out[1]


def _run(db, sql: str) -> list[dict]:
    # The raw DBAPI cursor: no bind-parameter parsing of the `%` and `:` in the SQL text.
    cur = db.connection().connection.cursor()
    cur.execute(sql)
    names = [c[0] for c in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def _replied(asking: str | None) -> dict:
    return {"stage": "replied", "status": "ok", "facts": {"lane": "business_query", "asking": asking}}


def _ask(db, n: int, *, intent: str, outcome: str, asking: str | None = None, stage: str | None = None,
         status: str = "done", outgoing: str | None | bool = False) -> None:
    """One turn + its fact. `outgoing`: False = no outgoing chat row; a string or None = one
    outgoing row for the turn with that `delivery_status`."""
    from sqlalchemy import text

    turn_id = str(uuid.uuid4())
    at = ASKED + timedelta(minutes=n)
    db.execute(
        text(
            "INSERT INTO chatbot.turns (id, contact_respond_id, message_id, ingress, envelope, is_test, status, "
            "stage, attempt, trace, response, created_at, started_at, finished_at) VALUES (:id, :c, :m, 'webhook', "
            "CAST(:env AS jsonb), false, :st, :stage, 1, CAST(:trace AS jsonb), CAST(:resp AS jsonb), :at, :at, :fin)"
        ),
        {
            "id": turn_id, "c": CONTACT, "m": f"ZZT-sb-{uuid.uuid4().hex[:10]}", "env": json.dumps({}),
            "st": status, "stage": stage, "trace": json.dumps([_replied(asking)]),
            "resp": json.dumps({"reply": {"text": "ZZT reply"}}), "at": at, "fin": at + timedelta(seconds=2),
        },
    )
    db.execute(
        text(
            "INSERT INTO chatbot.chat_ask_facts (id, source, turn_id, ask_seq, contact_respond_id, audience, "
            "contact_type, asked_at, channel, intent, outcome, failure_reason, tools, reply_ms, is_media, "
            "phantom_dropped) VALUES (:id, 'trace', :t, 1, :c, 'dealer', 'customer', :at, 'whatsapp', :intent, "
            ":outcome, :fr, '{}', 2000, false, false)"
        ),
        {
            "id": str(uuid.uuid4()), "t": turn_id, "c": CONTACT, "at": at, "intent": intent, "outcome": outcome,
            "fr": outcome if outcome in ("technical", "missed") else None,
        },
    )
    if outgoing is not False:
        db.execute(
            text(
                "INSERT INTO chat_histories (channel, contact_id, phone_number, message, sent_at, type, "
                "delivery_status, chatbot_turn_id) VALUES ('whatsapp', :c, '+60190000000', 'ZZT reply', :sent, "
                "'outgoing', :ds, :t)"
            ),
            {"c": CONTACT, "sent": (at + timedelta(seconds=3)).replace(tzinfo=None), "ds": outgoing, "t": turn_id},
        )


def _seed(db) -> None:
    from app.services.analytics_connector.views import ensure_cost_views, ensure_views

    ensure_views(db)
    ensure_cost_views(db)
    n = 0
    for _ in range(12):
        n += 1
        _ask(db, n, intent="check_stock", outcome="answered")
    _ask(db, 13, intent="check_stock", outcome="clarified")  # "How many units of X?"
    _ask(db, 14, intent="check_stock", outcome="answered_empty", asking="product_pick")  # did you mean
    _ask(db, 15, intent="check_stock", outcome="answered_empty")  # dead end
    _ask(db, 16, intent="check_stock", outcome="missed", asking="team_pick")  # dead end + offer
    _ask(db, 17, intent="check_order", outcome="technical", status="failed", stage="understood")
    _ask(db, 18, intent="check_order", outcome="technical", status="failed", stage="send_unconfirmed",
         outgoing="read")
    _ask(db, 19, intent="check_order", outcome="technical", status="failed", stage="send_unconfirmed")
    _ask(db, 20, intent="check_order", outcome="technical", status="failed", stage="send_unconfirmed",
         outgoing="failed")


def _week_all(rows: list[dict], key: str, value: str) -> dict:
    hits = [r for r in rows if str(r["wk"]) == WEEK and r[key] == value]
    assert len(hits) == 1, rows
    return hits[0]


def test_statement_1_counts_a_delivered_send_as_no_failure_and_splits_technical():
    """AC-5: technical = engine + delivery; the read reply is not a failure."""
    with pg_session() as db:
        _seed(db)
        row = _week_all(_run(db, _statements()[0]), "audience", "all")
    assert row["asks"] == 20
    assert float(row["technical_pct"]) == 15.0
    assert float(row["tech_engine_pct"]) == 5.0
    assert float(row["tech_delivery_pct"]) == 10.0


def test_statement_1_reports_stock_couldnt_find_with_the_dead_end_line_beside_it():
    """AC-6: stock couldn't-find = stock asks ending answered_empty or missed (the quantity
    question is `clarified`, so out); dead end = those whose reply offered no product."""
    with pg_session() as db:
        _seed(db)
        row = _week_all(_run(db, _statements()[0]), "audience", "all")
    assert float(row["stock_nf_pct"]) == 18.8  # 3 of 16
    assert float(row["stock_dead_end_pct"]) == 12.5  # 2 of 16


def test_statement_1_carries_the_one_weekly_line_on_the_all_row_only():
    """AC-7: one line per week, dates dd/mm/yyyy, a value that cannot be worked out is "-"
    (no dealer ask named a product, so asked-again has no denominator)."""
    with pg_session() as db:
        _seed(db)
        rows = _run(db, _statements()[0])
    week = [r for r in rows if str(r["wk"]) == WEEK]
    assert _week_all(rows, "audience", "all")["weekly_line"] == (
        "wk 06/01/2031: stock not-found 18.8% (dead-end 12.5%), median 2.0 s, "
        "dealer asked-again -, technical 15.0%"
    )
    assert [r["weekly_line"] for r in week if r["audience"] != "all"] == [None]


def test_statement_2_uses_the_same_technical_split_by_topic():
    with pg_session() as db:
        _seed(db)
        rows = _run(db, _statements()[1])
    total = _week_all(rows, "topic", "ALL")
    order = _week_all(rows, "topic", "check_order")
    assert float(total["technical_pct"]) == 15.0
    assert float(order["technical_pct"]) == 75.0
    assert float(order["tech_delivery_pct"]) == 50.0


# ------------------------------------------------------------------ the daily reading
# Owner 12 Nov 2026: "how can we do this progressively for me to see some improvement day
# by day". Statement 3: one line per day, each measure next to its trailing 7-day figure and
# its target, from the same CTE block as the weekly statements; a measure whose denominator
# is under the minimum prints "too few (n=N)" instead of a noisy %.

DAY_TO = "2031-01-08"  # Wed; 7 Jan holds the data, 8 Jan has none


def _statement_3(day_to: str = DAY_TO, days: int = 2) -> str:
    sql = SQL_PATH.read_text()
    assert "-- Statement 3" in sql, "the daily statement exists"
    stmt = "-- Statement 3" + sql.split("-- Statement 3", 1)[1]
    stmt, n1 = re.subn(r"DATE '\d{4}-\d{2}-\d{2}' AS day_to", f"DATE '{day_to}' AS day_to", stmt)
    stmt, n2 = re.subn(r"\b\d+ AS days\b", f"{days} AS days", stmt)
    assert (n1, n2) == (1, 1), "statement 3 carries the day_to and days parameters once each"
    return stmt.strip().rstrip(";")


def _seed_daily(db) -> None:
    from app.services.analytics_connector.views import ensure_cost_views, ensure_views

    ensure_views(db)
    ensure_cost_views(db)
    # 7 Jan: 60 stock asks (6 dead ends), 10 promotion asks (4 answered with a question).
    for n in range(60):
        _ask(db, n, intent="check_stock", outcome="answered_empty" if n < 6 else "answered")
    for n in range(60, 70):
        _ask(db, n, intent="check_promotion", outcome="clarified" if n < 64 else "answered")


def test_cte_block_is_one_definition_across_all_three_statements():
    """Daily and weekly numbers come from the same per-ask rows: the CTE block from
    `went_out` to the end of `b` is identical in every statement."""
    sql = SQL_PATH.read_text()
    blocks = re.findall(r"went_out AS \(.*?\n   WHERE a\.day >= p\.week_from\n\)", sql, re.S)
    assert len(blocks) == 3
    assert blocks[0] == blocks[1] == blocks[2]


def test_statement_3_prints_one_line_per_day_with_the_7_day_figure_and_target():
    with pg_session() as db:
        _seed_daily(db)
        rows = _run(db, _statement_3())
    assert [str(r["day"]) for r in rows] == ["2031-01-07", "2031-01-08"]
    assert rows[0]["daily_line"] == (
        "07/01/2031: stock not-found 10.0% (dead-end 10.0%) [7d 10.0%, target 8%]; "
        "median 2.0 s [7d 2.0 s, target 5 s]; p90 2.0 s [7d 2.0 s]; "
        "dealer asked-again too few (n=0) [7d too few (n=0), target 9.5%]; "
        "promo answered with a question too few (n=10) [7d too few (n=10), target 30%]; "
        "wrong answers - (sample check)"
    )


def test_statement_3_a_day_with_too_few_asks_says_so_and_keeps_the_7_day_figure():
    with pg_session() as db:
        _seed_daily(db)
        rows = _run(db, _statement_3())
    line = rows[1]["daily_line"]
    assert line.startswith("08/01/2031: stock not-found too few (n=0) [7d 10.0%, target 8%]; ")
    assert "median too few (n=0) [7d 2.0 s, target 5 s]" in line


def test_statement_3_any_date_shows_its_window_only():
    with pg_session() as db:
        _seed_daily(db)
        rows = _run(db, _statement_3(day_to="2031-01-15", days=1))
    assert [str(r["day"]) for r in rows] == ["2031-01-15"]
    assert rows[0]["daily_line"].startswith(
        "15/01/2031: stock not-found too few (n=0) [7d too few (n=0), target 8%]; "
    )
