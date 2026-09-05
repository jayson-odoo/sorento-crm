#!/usr/bin/env python3
"""Load gate 3b for the chatbot turn engine (AC-711).

The owner's burst, fired at once: 50 dealers x 2 questions. Green is p95 turn time under
12 s, zero errors, and every contact's replies in the order that contact sent them. That
last one is the point of the whole slice - S7 replaces n8n's one-contact-per-second
dispatcher with per-contact ordering inside the CRM, and "in order" is the property that
has to survive the change.

**Every run is a dry run (D14).** Every envelope carries `is_test: true` and a
`test_run_id`, always, in both modes: nothing outside `chatbot.turns` is written and no
WhatsApp message can leave. What `--live-llm` changes is the PARSER, not the containment.

Two modes, because they answer two different questions:

* default: the envelope also carries O2's `mock_reformulator_output` harness key, so the
  turn runs with no model call at all. This measures the CRM's own plumbing - ticket, wait,
  session reads, row writes - and it is the mode to run in a loop while wiring the cutover,
  because it is free and deterministic.
* `--live-llm`: the real parser call, still `is_test`. **This is the mode AC-711's 12 s p95
  applies to**, because the model call is most of a real turn. Point it at a lane backend,
  never production.

Usage:

    python scripts/chatbot_load.py --base-url http://localhost:8002 --contacts 50 --messages 2
    python scripts/chatbot_load.py --base-url http://localhost:8002 --contacts 50 --messages 6

Reads `EXTERNAL_API_KEY` from the environment (or `--api-key`).

**Cleanup is the operator's, for the turn rows.** The seeded contacts go in a `finally`;
`chatbot.turns` rows do not, because they ARE the evidence the run is graded from. Delete
them when the run has been read (the last line printed is the statement).

**The contacts are seeded, and that is not optional.** A turn's first act is to read the
contact's stored conversation state, and an unknown contact fails the turn at `received` -
which the ENDPOINT still answers 200 to, because a failed turn is a successful call. Fired
at synthetic ids that do not exist, this script would therefore report a cheerful green
while measuring nothing but the error path (it did, once, before this paragraph existed).
So it inserts N `ZZT-load-*` rows in `respond_contacts` first and deletes them at the end,
in a `finally`; `--keep-contacts` skips the cleanup when a run needs inspecting afterwards.
Everything it touches carries the `ZZT-load-` prefix and the deletes are scoped to it.

**The seeding goes through THIS checkout's `DATABASE_URL`, whatever `--base-url` points
at.** There is no way for the script to know the two match, so it refuses to run against a
non-local base URL unless `--i-know` says the operator has checked. Pointed at another
lane's backend from a checkout whose `.env` is the prod copy, it would otherwise write and
delete rows in one database while measuring another.

**How order is graded (AC-709, AC-711).** Not from the client's own send order - a client
that sends sequentially proves nothing, and one that fires in parallel cannot know which
request reached the CRM first. Each contact's N messages are fired CONCURRENTLY, one
thread each, `STAGGER_SECONDS` apart, so the whole burst (contacts x messages) is in flight
at once; then the grading reads `chatbot.turns` back and asks the SERVER two questions per
contact: do the rows sorted by `created_at` carry the message indexes in order, and does
each turn `finished_at` before the next one was `created_at`. The second question is the
one ordering exists to answer - no two turns for one contact may overlap.

The `chatbot.turns` rows are the evidence and are the one thing left behind:

    DELETE FROM chatbot.turns WHERE contact_respond_id LIKE 'ZZT-load-%';
"""
from __future__ import annotations

import argparse
import concurrent.futures
import os
import statistics
import sys
import threading
import time
import urllib.parse
import uuid
from dataclasses import dataclass
from typing import Any

# Allow `from app.*` imports when invoked from the backend directory, the same line
# `scripts/migrate_attachments_to_r2.py` carries for the same reason.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_CONTACTS = 50
DEFAULT_MESSAGES = 2

# AC-711's own numbers. p95 rather than a mean because the burst's shape is the thing
# under test: a mean hides the last dealer served.
P95_TARGET_SECONDS = 12.0

# AC-709's wording, made literal: "two requests for one contact arriving 50 ms apart". Each
# of a contact's messages is fired on its own thread this far behind the previous one, so
# they are all in flight together and their ARRIVAL order at the CRM is still the order
# they were sent in.
STAGGER_SECONDS = 0.05

# How often the sampler counts connections to the database while the burst runs. AC-711
# asks for pool usage under 60%, and the only honest client-side measure of a server's
# pool is what Postgres itself sees.
POOL_SAMPLE_INTERVAL_SECONDS = 0.25

# Where a base URL may point before the seeding guard demands `--i-know`.
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}

# O2's harness emission: what the parser would have returned for the questions below. Sent
# only in the default (no-model) mode; `--live-llm` omits it and the parser runs for real.
MOCK_PARSER_OUTPUT = {
    "message_type": "business_query",
    "intent_hint": "check_product",
    "domain_hint": "master_products",
    "scope_intent": "specific",
    "is_affirmative": None,
    "user_goal": "checking a product",
    "access_levels": [],
    "broaden_axis": None,
    "date_mode": None,
    "date_filter_start": None,
    "date_filter_end": None,
    "match_mode": "and",
    "demand_qty": None,
    "entities": [
        {
            "raw": "SRTWC8517",
            "hint": "product",
            "canonical_code": None,
            "current_message": True,
            "confident": True,
        }
    ],
    "entity_op": "replace_combine",
    "scope_exclusive": False,
    "requested_attributes": [],
    "contains_flyer": False,
    "reference_positions": [],
    "reference_target": None,
    "person_mention": None,
    "is_active": None,
    "order_status": None,
    "correction": False,
    "routing": {"suggested_team": None, "suggested_agent": None, "team_source": None},
    "escalation": {"is_escalation_confirmation": False, "company_pick": None},
}

# The sentence a failed turn hands back. Imported from the CORE copy module, never from
# `app/services/chatbot/` - scripts are not on the import-boundary allowlist (AC-002).
from app.services.chatbot_reply_copy import CHATBOT_TURN_ERROR_REPLY as ERROR_REPLY

QUESTIONS = [
    "price for SRTWC8517",
    "do you have stock for M6103",
    "what is the dealer price on that",
    "any promotion this month",
    "send me the spec sheet",
    "when can it be delivered",
]


CONTACT_PREFIX = "ZZT-load-"


def _phone_for(run_id: str, index: int) -> str:
    """A phone number nobody else's run can collide with.

    `phone_number` is UNIQUE and the insert is `ON CONFLICT DO NOTHING`, so a collision is
    SILENT: the contact never exists, every turn for it fails at `received`, and the run
    grades the error path. It used to be `+6099{index:07d}` - identical on every run, so a
    leftover `--keep-contacts` run or a second concurrent one was enough. The run id is in
    it now, and `_seed_contacts` refuses to continue unless every row actually landed.
    """
    run_digits = int(run_id, 16) % 10_000
    return f"+6099{run_digits:04d}{index:03d}"


def _seed_contacts(contacts: list[str], run_id: str) -> None:
    """Insert the synthetic contacts the turns will read state for."""
    import json as _json

    from sqlalchemy import text

    db = _script_session()
    inserted = 0
    try:
        for index, contact in enumerate(contacts):
            result = db.execute(
                text(
                    "INSERT INTO respond_contacts (id, respond_io_id, phone_number, "
                    "session_vars) VALUES (gen_random_uuid()::text, :cid, :phone, "
                    "CAST(:sv AS jsonb)) ON CONFLICT DO NOTHING"
                ),
                {
                    "cid": contact,
                    "phone": _phone_for(run_id, index),
                    "sv": _json.dumps({"variables": {}}),
                },
            )
            inserted += result.rowcount or 0
        db.commit()
    finally:
        db.close()
    if inserted != len(contacts):
        raise SystemExit(
            f"seeded {inserted} of {len(contacts)} contacts - a respond_io_id or a phone "
            "number collided and the insert was skipped. Every turn for the missing "
            "contact would fail at `received` and the run would grade the error path. "
            "Clean up leftover ZZT-load- rows and try again."
        )


# Stamped on every connection this SCRIPT opens, so the gauge can subtract itself: the
# seeding session and the sampler live in the same database as the backend under test, and
# counting them would inflate the number AC-711 puts a percentage on.
SCRIPT_APPLICATION_NAME = "chatbot-load-script"


def _script_session():
    """A session from this script's own pool, marked so the gauge can exclude it."""
    from sqlalchemy import text

    from app.database import SessionLocal

    db = SessionLocal()
    db.execute(text(f"SET application_name = '{SCRIPT_APPLICATION_NAME}'"))
    return db


def _database_name() -> str:
    """What the seeding writes to, for the refusal message."""
    from app.database import engine

    return f"{engine.url.host}/{engine.url.database}"


def _delete_contacts(contacts: list[str]) -> None:
    """Remove them again. Scoped to the prefix, so it can only ever hit its own rows."""
    from sqlalchemy import text

    db = _script_session()
    try:
        db.execute(
            text(
                "DELETE FROM respond_contacts WHERE respond_io_id = ANY(:ids) "
                "AND respond_io_id LIKE :prefix"
            ),
            {"ids": contacts, "prefix": f"{CONTACT_PREFIX}%"},
        )
        db.commit()
    finally:
        db.close()


@dataclass
class TurnOutcome:
    contact: str
    index: int
    seconds: float
    status_code: int
    turn_id: str | None
    error: str | None
    reply: str | None = None


def _envelope(contact: str, index: int, run_id: str, *, live: bool) -> dict[str, Any]:
    message_id = f"ZZT-load-{run_id}-{contact}-{index}"
    envelope: dict[str, Any] = {
        "contact": {"id": contact, "firstName": "ZZT Load", "custom_fields": []},
        "message": {
            "event_type": "message.received",
            "contact": {"id": contact},
            "message": {
                "messageId": message_id,
                "contactId": contact,
                "channelId": "whatsapp",
                "traffic": "incoming",
                "message": {"type": "text", "text": QUESTIONS[index % len(QUESTIONS)]},
            },
        },
        "ingress": "webhook",
    }
    # D14, ALWAYS. Both markers, because either one alone is enough for the engine and
    # sending both is what a clone turn looks like. A load generator that could answer a
    # real customer is not a load generator, it is an incident.
    envelope["is_test"] = True
    envelope["test_run_id"] = run_id
    if not live:
        # O2 / AC-112: a dry run may supply the emission instead of paying for it. The turn
        # still runs every stage after it, which is what this mode is measuring.
        envelope["mock_reformulator_output"] = MOCK_PARSER_OUTPUT
    return envelope


def _send(session: Any, url: str, headers: dict[str, str], envelope: dict[str, Any],
          contact: str, index: int, timeout: float) -> TurnOutcome:
    started = time.monotonic()
    try:
        response = session.post(url, json={"envelope": envelope}, headers=headers, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - a transport failure is a failed turn here
        return TurnOutcome(contact, index, time.monotonic() - started, 0, None, str(exc), None)
    seconds = time.monotonic() - started
    if response.status_code != 200:
        return TurnOutcome(
            contact, index, seconds, response.status_code, None, response.text[:200], None
        )
    body = response.json()
    reply = ((body.get("reply") or {}).get("text")) or ""
    # A FAILED turn is a successful CALL - the endpoint answers 200 and hands back the
    # error reply for the caller to send. The load gate has to count that as an error or
    # it grades the error path and calls it green.
    failed = reply.strip() == ERROR_REPLY
    return TurnOutcome(
        contact,
        index,
        seconds,
        200,
        body.get("turn_id"),
        "the turn failed (error reply returned)" if failed else None,
        reply,
    )


def _http_session(session_factory):
    """One `requests.Session`, with the environment's proxy settings OFF.

    `trust_env = False` is not tidiness. On macOS, `requests` asks SystemConfiguration for
    the proxy settings on the first request of every session, and a hundred threads doing
    that at once intermittently stalls the whole burst for about thirty seconds - measured
    here, repeatedly: the server's own log showed 0.3 s per request while the client
    reported a p50 of 31 s. It is the client-side twin of the `no_proxy='*'` prefix the
    worker already carries (CLAUDE.md). A load generator measuring its own proxy lookups
    is worse than no load generator.
    """
    session = session_factory()
    session.trust_env = False
    return session


def _one_message(session_factory, url, headers, contact, index, run_id, live, timeout):
    """One dealer's Nth question, fired `index * STAGGER_SECONDS` after their first.

    Concurrent ON PURPOSE, and this is the correction that makes the gate mean something.
    The previous version sent each contact's messages sequentially, blocking on each
    reply, so two turns for one contact were never in flight together: `wait_for_turn`
    always took its fast path and the ticket / wait / repair machinery this whole slice
    exists for was never entered. Every message now has its own thread, and the stagger is
    AC-709's own 50 ms, so the burst is `contacts x messages` in flight (AC-711's 100) and
    arrival order at the CRM is still send order.
    """
    if index:
        time.sleep(index * STAGGER_SECONDS)
    return _send(
        _http_session(session_factory),
        url,
        headers,
        _envelope(contact, index, run_id, live=live),
        contact,
        index,
        timeout,
    )


class _PoolGauge:
    """How many connections the database is holding while the burst runs (AC-711).

    Sampled from `pg_stat_activity` rather than from a SQLAlchemy pool object, because the
    pool that matters belongs to the BACKEND process and this script cannot see it. The
    baseline is taken before the burst and reported beside the peak, so the number the
    reader compares against the backend's pool size is the DELTA - the local database is
    shared with whatever else is running on this machine.
    """

    def __init__(self) -> None:
        self.baseline = 0
        self.peak = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _count(self) -> int:
        from sqlalchemy import text

        db = _script_session()
        try:
            return int(
                db.execute(
                    text(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE datname = current_database() "
                        "AND application_name <> :mine"
                    ),
                    {"mine": SCRIPT_APPLICATION_NAME},
                ).scalar()
                or 0
            )
        except Exception:  # noqa: BLE001 - a gauge must never fail the run
            return 0
        finally:
            db.close()

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.peak = max(self.peak, self._count())
            self._stop.wait(POOL_SAMPLE_INTERVAL_SECONDS)

    def start(self) -> None:
        self.baseline = self._count()
        self.peak = self.baseline
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)


def _grade_order(run_id: str, messages: int) -> tuple[list[str], list[str], int]:
    """Per contact, from the SERVER's own rows: in order, and never overlapping.

    Three questions, and the client's send order answers none of them - it fired the whole
    burst at once and cannot know which request the CRM took first:

    * did the turns ARRIVE in the order their contact sent them? `created_at` is the
      dedup session's transaction start, i.e. the moment the request reached the engine,
      and the messages left `STAGGER_SECONDS` apart. An inversion here is the network or
      the client, not the ordering - it is reported separately for that reason;
    * did the REPLIES come back in arrival order? `finished_at` ascending in `created_at`
      order. This is the customer-visible promise (journey A5) and the one that must be 0;
    * did any two turns for one contact RUN at the same time? The execution start is not a
      column - `started_at` is stamped at the insert, before the ticket wait - so it is
      read off the trace: the second record's `started_at` is written when the `received`
      stage ends, which is after the wait. `finished_at[i] <= execution_start[i+1]` is
      then exactly "no overlap".
    """
    from app.models.chatbot_turn import ChatbotTurn

    db = _script_session()
    try:
        rows = (
            db.query(ChatbotTurn)
            .filter(ChatbotTurn.contact_respond_id.like(f"{CONTACT_PREFIX}{run_id}-%"))
            .all()
        )
    finally:
        db.close()

    by_contact: dict[str, list[Any]] = {}
    for row in rows:
        by_contact.setdefault(row.contact_respond_id, []).append(row)

    out_of_order: list[str] = []
    jitter: list[str] = []
    for contact, turns in by_contact.items():
        turns.sort(key=lambda r: r.created_at)
        indexes = [_index_of(r.message_id) for r in turns]
        if indexes != sorted(indexes):
            # NOT a gate failure. The CRM's promise is arrival order; it cannot know which
            # message the customer typed first, only which one reached it first. A client
            # firing 300 threads out of one Python process reorders its own sends, and
            # counting that against the CRM would make the gate fail for the load
            # generator's scheduling. Reported so the reader can see how often it happened.
            jitter.append(f"{contact} arrived {indexes}, sent 0..{len(indexes) - 1}")
        finished = [r.finished_at for r in turns]
        if any(f is None for f in finished) or finished != sorted(finished):
            out_of_order.append(f"{contact} REPLIED out of arrival order {finished}")
            continue
        for earlier, later in zip(turns, turns[1:]):
            began = _execution_start(later)
            if began is not None and earlier.finished_at > began:
                out_of_order.append(
                    f"{contact} OVERLAPPED: turn {_index_of(earlier.message_id)} was "
                    f"still running when {_index_of(later.message_id)} started"
                )
                break
    missing = len(by_contact) * messages - len(rows)
    return out_of_order, jitter, missing


def _execution_start(row: Any):
    """When this turn's stages began, i.e. after its ticket wait. None when unreadable.

    The trace's SECOND record is written when the first one (`received`) ends, and the
    first one only runs once the wait is over, so its `started_at` is the first timestamp
    the row carries from inside the serialised region.
    """
    import datetime

    trace = row.trace if isinstance(row.trace, list) else []
    if len(trace) < 2 or not isinstance(trace[1], dict):
        return None
    try:
        return datetime.datetime.fromisoformat(str(trace[1].get("started_at")))
    except (TypeError, ValueError):
        return None


def _index_of(message_id: str | None) -> int:
    """The message index off `ZZT-load-{run}-{contact}-{index}`. -1 when unreadable."""
    try:
        return int(str(message_id).rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return -1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.getenv("CHATBOT_LOAD_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--contacts", type=int, default=DEFAULT_CONTACTS)
    parser.add_argument("--messages", type=int, default=DEFAULT_MESSAGES)
    parser.add_argument("--api-key", default=os.getenv("EXTERNAL_API_KEY", ""))
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument(
        "--keep-contacts",
        action="store_true",
        help="leave the seeded ZZT-load- contacts behind (for inspecting a run)",
    )
    parser.add_argument(
        "--live-llm",
        action="store_true",
        help=(
            "make the parser call real (still is_test, still no side effects). This is the "
            "mode AC-711's 12s p95 applies to. Never against production."
        ),
    )
    parser.add_argument(
        "--i-know",
        action="store_true",
        help=(
            "I have checked that this checkout's DATABASE_URL is the database the "
            "--base-url backend reads. Required for a non-local base URL, because the "
            "contacts are seeded locally and the turns are not."
        ),
    )
    args = parser.parse_args(argv)

    if not args.api_key:
        print("EXTERNAL_API_KEY is not set (or pass --api-key)", file=sys.stderr)
        return 2
    if "fe-sorento" in args.base_url:
        # BOTH modes, not just `--live-llm`. The parser is what `--live-llm` changes; the
        # writes to `respond_contacts` and the load on the backend are the same either way.
        print(
            "refusing to run against what looks like production; point it at a lane backend",
            file=sys.stderr,
        )
        return 2
    host = (urllib.parse.urlparse(args.base_url).hostname or "").lower()
    if host not in LOCAL_HOSTS and not args.i_know:
        # The seeding goes through THIS checkout's DATABASE_URL and the turns go to
        # --base-url; nothing here can prove they are the same database. Pointed at another
        # lane from a checkout whose .env is the prod copy, this would write and delete
        # respond_contacts rows in one database while measuring another.
        print(
            f"--base-url points at {host!r}, but the contacts are seeded through this "
            f"checkout's DATABASE_URL ({_database_name()}). Confirm the two are the same "
            "database and pass --i-know.",
            file=sys.stderr,
        )
        return 2

    import requests

    run_id = uuid.uuid4().hex[:8]
    url = f"{args.base_url.rstrip('/')}/api/v1/external/chat/turn"
    headers = {"X-API-Key": args.api_key, "Content-Type": "application/json"}
    contacts = [f"ZZT-load-{run_id}-{i:03d}" for i in range(args.contacts)]

    print(
        f"chatbot load: {args.contacts} contacts x {args.messages} messages = "
        f"{args.contacts * args.messages} turns against {url} "
        f"({'dry run, LIVE parser' if args.live_llm else 'dry run, mocked parser'})"
    )

    _seed_contacts(contacts, run_id)
    gauge = _PoolGauge()
    gauge.start()
    started = time.monotonic()
    outcomes: list[TurnOutcome] = []
    try:
        # One thread per MESSAGE, not per contact: the whole burst is in flight at once
        # (AC-711's "50 contacts x 2 messages fired at once") and each contact's messages
        # are only STAGGER_SECONDS apart, so the CRM is the thing deciding their order.
        in_flight = args.contacts * args.messages
        with concurrent.futures.ThreadPoolExecutor(max_workers=in_flight) as pool:
            futures = [
                pool.submit(
                    _one_message,
                    requests.Session,
                    url,
                    headers,
                    contact,
                    index,
                    run_id,
                    args.live_llm,
                    args.timeout,
                )
                for contact in contacts
                for index in range(args.messages)
            ]
            for future in concurrent.futures.as_completed(futures):
                outcomes.append(future.result())
    finally:
        wall = time.monotonic() - started
        gauge.stop()
        if not args.keep_contacts:
            _delete_contacts(contacts)

    errors = [o for o in outcomes if o.error is not None or o.status_code != 200]
    durations = sorted(o.seconds for o in outcomes)
    p95 = durations[max(0, int(len(durations) * 0.95) - 1)] if durations else 0.0
    p50 = statistics.median(durations) if durations else 0.0

    # Order, per contact, graded from the SERVER's rows - see `_grade_order`. The client's
    # own send order cannot answer this: it fired the whole burst at once.
    out_of_order, jitter, missing = _grade_order(run_id, args.messages)

    print(f"wall {wall:.1f}s  turns {len(outcomes)}  p50 {p50:.2f}s  p95 {p95:.2f}s")
    print(f"errors {len(errors)}  out-of-order contacts {len(out_of_order)}")
    print(
        f"db connections: baseline {gauge.baseline}  peak {gauge.peak}  "
        f"delta {gauge.peak - gauge.baseline} (pg_stat_activity, whole database)"
    )
    for outcome in errors[:10]:
        print(f"  ERROR {outcome.contact}#{outcome.index} {outcome.status_code} {outcome.error}")
    for entry in out_of_order[:10]:
        print(f"  OUT OF ORDER {entry}")
    if jitter:
        print(
            f"  (client jitter: {len(jitter)} contact(s) whose messages ARRIVED out of "
            f"send order - the CRM answers in arrival order, so this is not a failure)"
        )
    if missing:
        print(f"  {missing} turn row(s) missing - the burst did not all reach chatbot.turns")

    green = not errors and not out_of_order and not missing and p95 < P95_TARGET_SECONDS
    print("GREEN" if green else "RED")
    if not green and p95 >= P95_TARGET_SECONDS:
        print(f"  p95 {p95:.2f}s is over the {P95_TARGET_SECONDS}s target")
    print(
        "clean up with: DELETE FROM chatbot.turns WHERE contact_respond_id "
        f"LIKE 'ZZT-load-{run_id}-%';"
    )
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())
