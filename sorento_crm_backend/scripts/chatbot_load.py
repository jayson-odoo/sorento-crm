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

**The contacts are seeded, and that is not optional.** A turn's first act is to read the
contact's stored conversation state, and an unknown contact fails the turn at `received` -
which the ENDPOINT still answers 200 to, because a failed turn is a successful call. Fired
at synthetic ids that do not exist, this script would therefore report a cheerful green
while measuring nothing but the error path (it did, once, before this paragraph existed).
So it inserts N `ZZT-load-*` rows in `respond_contacts` first and deletes them at the end,
in a `finally`; `--keep-contacts` skips the cleanup when a run needs inspecting afterwards.
Everything it touches carries the `ZZT-load-` prefix and the deletes are scoped to it.

The `chatbot.turns` rows are the evidence and are the one thing left behind:

    DELETE FROM chatbot.turns WHERE contact_respond_id LIKE 'ZZT-load-%';
"""
from __future__ import annotations

import argparse
import concurrent.futures
import os
import statistics
import sys
import time
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


def _seed_contacts(contacts: list[str]) -> None:
    """Insert the synthetic contacts the turns will read state for."""
    import json as _json

    from sqlalchemy import text

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        for index, contact in enumerate(contacts):
            db.execute(
                text(
                    "INSERT INTO respond_contacts (id, respond_io_id, phone_number, "
                    "session_vars) VALUES (gen_random_uuid()::text, :cid, :phone, "
                    "CAST(:sv AS jsonb)) ON CONFLICT DO NOTHING"
                ),
                {
                    "cid": contact,
                    "phone": f"+6099{index:07d}",
                    "sv": _json.dumps({"variables": {}}),
                },
            )
        db.commit()
    finally:
        db.close()


def _delete_contacts(contacts: list[str]) -> None:
    """Remove them again. Scoped to the prefix, so it can only ever hit its own rows."""
    from sqlalchemy import text

    from app.database import SessionLocal

    db = SessionLocal()
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


def _one_contact(session_factory, url, headers, contact, messages, run_id, live, timeout):
    """One dealer, sending their questions back to back, in order.

    Sequential ON PURPOSE: AC-711 asks whether one contact's replies come back in the order
    they were sent, and a client that fires them in parallel would only be measuring redis.
    The concurrency under test is BETWEEN contacts.
    """
    session = session_factory()
    outcomes = []
    for index in range(messages):
        outcomes.append(
            _send(
                session,
                url,
                headers,
                _envelope(contact, index, run_id, live=live),
                contact,
                index,
                timeout,
            )
        )
    return outcomes


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
    args = parser.parse_args(argv)

    if not args.api_key:
        print("EXTERNAL_API_KEY is not set (or pass --api-key)", file=sys.stderr)
        return 2
    if args.live_llm and "fe-sorento" in args.base_url:
        print(
            "refusing --live-llm against what looks like production; point it at a lane "
            "backend",
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

    _seed_contacts(contacts)
    started = time.monotonic()
    outcomes: list[TurnOutcome] = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.contacts) as pool:
            futures = [
                pool.submit(
                    _one_contact,
                    requests.Session,
                    url,
                    headers,
                    contact,
                    args.messages,
                    run_id,
                    args.live_llm,
                    args.timeout,
                )
                for contact in contacts
            ]
            for future in concurrent.futures.as_completed(futures):
                outcomes.extend(future.result())
    finally:
        wall = time.monotonic() - started
        if not args.keep_contacts:
            _delete_contacts(contacts)

    errors = [o for o in outcomes if o.error is not None or o.status_code != 200]
    durations = sorted(o.seconds for o in outcomes)
    p95 = durations[max(0, int(len(durations) * 0.95) - 1)] if durations else 0.0
    p50 = statistics.median(durations) if durations else 0.0

    # Order, per contact: the reply to message N must have come back before the reply to
    # N+1 started. The client sent them sequentially, so a violation means the SERVER
    # answered out of order - which is the failure this gate exists to catch.
    out_of_order = []
    by_contact: dict[str, list[TurnOutcome]] = {}
    for outcome in outcomes:
        by_contact.setdefault(outcome.contact, []).append(outcome)
    for contact, rows in by_contact.items():
        indexes = [row.index for row in sorted(rows, key=lambda r: r.index)]
        if indexes != sorted(indexes):
            out_of_order.append(contact)

    print(f"wall {wall:.1f}s  turns {len(outcomes)}  p50 {p50:.2f}s  p95 {p95:.2f}s")
    print(f"errors {len(errors)}  out-of-order contacts {len(out_of_order)}")
    for outcome in errors[:10]:
        print(f"  ERROR {outcome.contact}#{outcome.index} {outcome.status_code} {outcome.error}")

    green = not errors and not out_of_order and p95 < P95_TARGET_SECONDS
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
