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
  applies to**, because the model call is most of a real turn. This is the SECOND burst of
  the owner's cutover-day pair (mocked first, then this) and, unlike every other mode here,
  IS allowed against production with `--production` - that pair is what live traffic looks
  like the day of the cutover. It still spends real model budget and shares workers with
  live customers, so it prints a warning and needs `--production`'s typed confirmation.

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

**Seeding an unknown contact is not enough - it also has to PASS the access gate, or the
same thing happens one stage later.** `head/route.py`'s `decide()` evaluates
`not access_allowed()` FIRST, before any other predicate, and `head/access.py`'s
`check_access` (`app.services.mcp_access_service.evaluate_agent`) denies an unknown
contact or an ungranted agent CLOSED. A contact with no workspace link and no
`contact_agent_access` row therefore routes to `branch_kind = "access_denied"` in a few
milliseconds flat, every time - which is exactly what happened here before this paragraph
existed: the load gate measured the access refusal, not the business answer path
(resolve, tier-gate, fetch, answer, compose) AC-711 is actually about. So seeding also
links each contact to the default `respond_workspaces` row and grants it every code in
`ACCESS_AGENT_CODES` - the agents `derive_routing`
(`app/services/chatbot/head/output_exchange.py`) resolves the mocked `master_products`
domain AND every QUESTION's live-parsed domain to (see that constant's own comment for
why it is more than one code) - the same facts a real dealer contact carries in
production.

**A granted contact still is not enough - the business lane itself has to be switched
on, or the turn is refused a stage further downstream.** `branch_kind = "business_query"`
is decided by `route.decide()` before either switch is read, so the row would carry it
either way; but `system_settings.chatbot_business_lane_enabled` AND
`TARGET_BRANCH_KIND in chatbot_completed_lanes` (AC-809/AC-810) are what decide whether the
head ANSWERS that turn in process or DELEGATES it to n8n's canned handoff. `main()` checks
both before seeding a single contact. Off a production database it refuses outright,
naming the Settings > Chatbot screen - this script never writes `system_settings` on a
live tenant. Off `--production` (shared dev state) it prints the exact SQL to flip them
and the exact values to restore afterward, and does not flip them itself either way.
`_grade_business_path`'s `branch_kind` histogram is the backstop for the same failure if
the switches were right but something else diverted the turn - AC-711 reads STRICT: every
turn has to land on the business lane, not merely one of them, and the run fails if it does
not.

**A run against a PRODUCTION database needs `--production` and a typed `yes`, never a
hostname check.** `--base-url` is where the BACKEND lives, and on the prod host that is
`http://localhost:8000` inside the `backend` container - indistinguishable, by hostname,
from a laptop's own dev server. What actually says "this writes to the live database" is
the CHECKOUT's own `ENVIRONMENT` (`app/config.py`), the same value the backend itself
boots with. `--production` prints exactly what will be written (and removed again) before
asking for confirmation; refused without it, and refused before seeding a single row.

**Grading and cleanup both wait for the SERVER to actually finish, not just for the
CLIENT to give up.** A single overloaded worker can still be draining a 100-turn backlog
minutes after the client's own timeout - measured, 21 rows landed 3 minutes late in this
fix's own evidence run. `_wait_for_turns_to_settle` polls `chatbot.turns` for this run
until none are non-terminal (`queued`/`processing`/`delegated`) or `SETTLE_TIMEOUT_SECONDS`
lapses, and runs BEFORE both grading and the contact cleanup - a contact deleted while its
turn is still mid-flight fails at `received` ("contact not found"), which is a
cleanup-timing artefact, not the turn's real outcome, and would otherwise pollute the
histogram with rows that mean nothing.

**The seeding goes through THIS checkout's `DATABASE_URL`, whatever `--base-url` points
at.** There is no way for the script to know the two match, so it refuses to run against a
non-local base URL unless `--i-know` says the operator has checked. Pointed at another
lane's backend from a checkout whose `.env` is the prod copy, it would otherwise write and
delete rows in one database while measuring another.

**The integration key's rate limit is 600/minute** (`app/services/integration_auth.py:66`
enforces `DEFAULT_LIMIT_PER_MINUTE` from `app/services/integration_rate_limit.py:36`),
per integration, not per run. Two `--contacts 50 --messages 6` runs (300 turns each) inside
the same minute is 600 requests on the nose and the second run's tail gets 429s that read
as turn failures; leave a minute between back-to-back big runs, or run smaller bursts.

**`--workers N` on the backend under test needs its pool cut**, or the burst can outrun
Postgres. Each worker process opens its own engine at `pool_size=10, max_overflow=20`
(`app/database.py:13`), so N workers can hold up to `N * 30` connections; that has to stay
under Postgres's `max_connections` alongside everything else already connected (this
script's own seeding/gauge session included). A single `--workers 1` backend is what every
run in this file's own evidence section was taken against.

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

# Every agent code a live parse of a QUESTION below could route to
# (`app/services/chatbot/head/output_exchange.py`'s `derive_routing`). `general_enquiries`
# is what `master_products` / `promotion` / `product_attachment` all resolve to - which
# covers five of the six QUESTIONS - but "when can it be delivered" is an `order` domain
# question, and `derive_routing`'s `order` case names `order_enquiries` instead. In the
# default (mocked) mode this never matters - `MOCK_PARSER_OUTPUT` below is the SAME fixed
# `master_products` output on every message regardless of which QUESTION text was sent -
# but `--live-llm` reads the real question, and a seeded contact ungranted for the agent a
# real parse actually names fails `access_denied` same as an unseeded one, just one
# question later. `check_access` denies an unknown agent CLOSED (`deny_unknown_agent`), so
# a code here has to exist and be active, or granting it buys nothing.
# `tests/chatbot/test_load_script_seeding.py` derives the required set from
# `derive_routing` itself and asserts this tuple still covers it, so the two cannot drift.
ACCESS_AGENT_CODES = ("general_enquiries", "order_enquiries")

# O2's harness emission: what the parser would have returned for the questions below. Sent
# only in the default (no-model) mode; `--live-llm` omits it and the parser runs for real.
#
# The entity is a real, active, in-stock product code (`SRTPTFE1315`), verified against
# the local dev database at the time this was written - the docstring's original example,
# `SRTWC8517`, does not exist there. A resolver miss on a phantom code would take the
# turn down the "not found" reply rather than through fetch/answer, which is the same
# class of problem this whole fix is about: the gate has to reach the code path it claims
# to measure.
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
            "raw": "SRTPTFE1315",
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
    "price for SRTPTFE1315",  # master_products - the same real code MOCK_PARSER_OUTPUT names
    "do you have stock for M6103",  # master_products (or inventory - both -> general_enquiries)
    "what is the dealer price on that",  # master_products
    "any promotion this month",  # promotion -> general_enquiries
    "send me the spec sheet",  # product_attachment -> general_enquiries
    "when can it be delivered",  # order -> order_enquiries (the one outlier, see ACCESS_AGENT_CODES)
]


CONTACT_PREFIX = "ZZT-load-"

# The three arms `lanes/business/` answers (resolve, gate, fetch, answer) - the set
# `chatbot.turns.branch_kind` has to land in for a run to have exercised the business
# path this script exists to measure, rather than a canned lane. Duplicated from
# `app/services/chatbot/contracts.BUSINESS_BRANCH_KINDS` rather than imported: this
# script sits outside the package's import boundary (AC-002,
# `tests/chatbot/test_import_boundary.py`), which everything outside the package's own
# doorways must respect, scripts included. `check_product` against `master_products`
# (`MOCK_PARSER_OUTPUT` above) always lands on `business_query`; the other two are the
# lane's remaining arms, kept here so a future question that trips `check_promotion` or
# a stock denial still counts.
BUSINESS_BRANCH_KINDS = frozenset({"business_query", "check_promotion", "stock_denied"})

# The one arm THIS script's mocked questions actually drive (see `ACCESS_AGENT_CODES`'s
# comment above) - what the pre-flight switch check in `main()` insists is enabled
# before firing, so a run cannot silently measure delegation-to-n8n instead.
TARGET_BRANCH_KIND = "business_query"


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


def _resolve_default_workspace_id(db: Any) -> str | None:
    """The one `is_default` `respond_workspaces` row's id, or `None` when there is none.

    The SAME row `check_access`'s own `default_space_id` reads (`head/access.py`) - the
    turn resolves `space_id` from it, then looks the contact up by
    `(respond_io_id, workspace_id)`. A contact with no link to this row is
    `deny_unknown_contact` regardless of any grant it holds.
    """
    from sqlalchemy import text

    row_id = db.execute(
        text("SELECT id FROM respond_workspaces WHERE is_default IS TRUE LIMIT 1")
    ).scalar()
    return str(row_id) if row_id is not None else None


def _resolve_agent_id(db: Any, code: str) -> str | None:
    """The active `access_agents.id` for `code`, or `None` when it does not exist.

    `evaluate_agent` (`app/services/mcp_access_service.py`) fails an unknown agent
    CLOSED (`deny_unknown_agent`), so a missing row here is a reason to refuse the
    whole run rather than seed a contact that cannot pass the gate.
    """
    from sqlalchemy import text

    agent_id = db.execute(
        text("SELECT id FROM access_agents WHERE code = :code AND is_active IS TRUE"),
        {"code": code},
    ).scalar()
    return str(agent_id) if agent_id is not None else None


def _seed_access_grants(db: Any, contacts: list[str], *, agent_id: str) -> None:
    """Grant every contact in `contacts` the agent the mocked turn will be checked
    against (AC-711's fix: see the module docstring's access-gate paragraph). Called
    once per code in `ACCESS_AGENT_CODES`.

    `valid_from` / `valid_to` are left `NULL` - `evaluate_agent`'s own `OR ... IS NULL`
    clauses treat that as "always valid", which is simpler than dating a synthetic grant
    that only needs to outlive one load run.

    `id` and `synced_to_excel` are supplied explicitly rather than left to the column's
    default: the shared local database has DB-level defaults for both (a migration set
    them there), but `ContactAgentAccess`'s MODEL only carries ORM-side `default=`
    values, which `create_all` never turns into a DB default - a schema built purely
    from the model (a test's blank schema, `tests/_pg_fixture.blank_schema_engine`) has
    neither, and this raw INSERT bypasses the ORM layer that would otherwise supply them.

    `ON CONFLICT DO NOTHING`, same reasoning as the contact INSERT below: a rerun with a
    collided phone/contact id would otherwise fail here on
    `uq_contact_agent_access_respond_contact_id_agent_id` instead of failing where the
    read run_id already explains itself.
    """
    from sqlalchemy import text

    db.execute(
        text(
            "INSERT INTO contact_agent_access "
            "(id, respond_contact_id, respond_contact_phone, agent_id, is_allowed, "
            "synced_to_excel) "
            "SELECT gen_random_uuid(), id, phone_number, :agent_id, true, false "
            "FROM respond_contacts WHERE respond_io_id = ANY(:ids) "
            "ON CONFLICT DO NOTHING"
        ),
        {"agent_id": agent_id, "ids": contacts},
    )


def _seed_contacts(contacts: list[str], run_id: str) -> str | None:
    """Insert the synthetic contacts the turns will read state for, linked to the
    default workspace and granted every agent in `ACCESS_AGENT_CODES` (see the module
    docstring's access-gate paragraph) - without both, every turn is refused at
    `access_denied` before resolve/tier-gate/fetch/answer ever runs.

    Returns an error message for the caller to print and exit on, or `None` on success -
    `main()`'s own style (`_check_business_lane_switches` set the precedent), rather than
    `SystemExit` from inside a helper a test also calls directly.
    """
    import json as _json

    from sqlalchemy import text

    db = _script_session()
    inserted = 0
    try:
        workspace_id = _resolve_default_workspace_id(db)
        if workspace_id is None:
            return (
                "no default respond_workspaces row (is_default = true) in "
                f"{_database_name()} - the access gate cannot resolve a space_id for "
                "the seeded contacts. Seed one (or point DATABASE_URL at a database "
                "that already has one) before running the load gate."
            )
        agent_ids: dict[str, str] = {}
        for code in ACCESS_AGENT_CODES:
            agent_id = _resolve_agent_id(db, code)
            if agent_id is None:
                return (
                    f"no active access_agents row with code={code!r} in "
                    f"{_database_name()} - this is one of the agents a live parse of "
                    "QUESTIONS can route to (app/services/chatbot/head/output_"
                    "exchange.py's derive_routing), and check_access denies an unknown "
                    "agent closed. Seed one before running the load gate."
                )
            agent_ids[code] = agent_id
        for index, contact in enumerate(contacts):
            result = db.execute(
                text(
                    "INSERT INTO respond_contacts (id, respond_io_id, phone_number, "
                    "workspace_id, session_vars) VALUES (gen_random_uuid()::text, :cid, "
                    ":phone, :ws, CAST(:sv AS jsonb)) ON CONFLICT DO NOTHING"
                ),
                {
                    "cid": contact,
                    "phone": _phone_for(run_id, index),
                    "ws": workspace_id,
                    "sv": _json.dumps({"variables": {}}),
                },
            )
            inserted += result.rowcount or 0
        for agent_id in agent_ids.values():
            _seed_access_grants(db, contacts, agent_id=agent_id)
        db.commit()
    finally:
        db.close()
    if inserted != len(contacts):
        # The commit above already landed the rows that DID insert, so take them out again
        # before giving up. A refusal that leaves its own half-seeded run behind makes the
        # next run collide on the same numbers and refuse as well.
        _delete_contacts(contacts)
        return (
            f"seeded {inserted} of {len(contacts)} contacts - a respond_io_id or a phone "
            "number collided and the insert was skipped. Every turn for the missing "
            "contact would fail at `received` and the run would grade the error path. "
            "This run's own rows have been removed again; clean up any other leftover "
            "ZZT-load- rows and try again."
        )
    return None


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
    """Remove them again, grant row first. Scoped to the prefix throughout, so it can
    only ever hit rows this run (or another `ZZT-load-` run) created.

    `contact_agent_access.respond_contact_id` carries `ON DELETE CASCADE`
    (`app/models/access.py`), so the second statement alone would already take the grant
    with it - this is explicit rather than relied-on, because a script's own cleanup
    should not depend on a constraint it does not itself state, and the FK-order comment
    this function exists to satisfy is worth more written down than implied.
    """
    from sqlalchemy import text

    db = _script_session()
    try:
        db.execute(
            text(
                "DELETE FROM contact_agent_access WHERE respond_contact_id IN "
                "(SELECT id FROM respond_contacts WHERE respond_io_id = ANY(:ids) "
                "AND respond_io_id LIKE :prefix)"
            ),
            {"ids": contacts, "prefix": f"{CONTACT_PREFIX}%"},
        )
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
class _OrderReport:
    """What the rows said about order, including how much of them was readable.

    `checked_pairs` and `skipped_pairs` are reported because a gate that cannot say how
    much it examined is a gate that can pass by examining nothing.
    """

    out_of_order: list[str]
    jitter: list[str]
    missing: int
    checked_pairs: int
    skipped_pairs: int


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


def _grade_order(run_id: str, contacts_requested: int, messages: int) -> "_OrderReport":
    """Per contact, from the SERVER's own rows: in order, and never overlapping.

    Three questions, and the client's send order answers none of them - it fired the whole
    burst at once and cannot know which request the CRM took first:

    * did the turns ARRIVE in the order their contact sent them? `created_at` is the
      dedup session's transaction start, i.e. the moment the request reached the engine,
      and the messages left `STAGGER_SECONDS` apart. An inversion here is the network or
      the client, not the ordering - it is reported separately for that reason;
      (`created_at` is a proxy for the ticket, taken one statement earlier. Under heavy
      contention the two can disagree, so a lone reply-order violation with everything
      else clean is worth re-running before it is believed. Across 100 and 300 turn runs
      on 5 Sep 2026 there were none.)
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
    checked_pairs = 0
    skipped_pairs = 0
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
            if began is None or earlier.finished_at is None:
                # COUNTED, not passed over. A pair that cannot be evaluated is a pair this
                # gate did not check, and a silent skip is how a green run comes to mean
                # less than it says - if the trace shape ever changes, every pair skips and
                # the overlap clause quietly stops existing.
                skipped_pairs += 1
                continue
            checked_pairs += 1
            if earlier.finished_at > began:
                out_of_order.append(
                    f"{contact} OVERLAPPED: turn {_index_of(earlier.message_id)} was "
                    f"still running when {_index_of(later.message_id)} started"
                )
                break
    # From what was ASKED FOR, not from what came back: a contact with zero rows has no
    # entry in `by_contact` at all, and counting its own keys would make it invisible -
    # the one failure most worth catching.
    missing = contacts_requested * messages - len(rows)
    return _OrderReport(
        out_of_order=out_of_order,
        jitter=jitter,
        missing=missing,
        checked_pairs=checked_pairs,
        skipped_pairs=skipped_pairs,
    )


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


@dataclass
class _BusinessPathReport:
    """Did the mocked `business_query` turns actually reach the business answer path -
    the thing this whole fix is about (see the module docstring's access-gate
    paragraph). `branch_kind_counts` is printed unconditionally so a reader never has
    to take "green" on faith: a run where every turn is `access_denied` would still
    show 0 errors and perfect ordering, because a refused turn is a fast, well-formed,
    correctly-ordered non-answer.
    """

    branch_kind_counts: dict[str, int]
    access_denied: int
    total: int
    business_count: int
    business_incomplete: list[str]


def _grade_business_path(run_id: str) -> _BusinessPathReport:
    """`branch_kind` distribution for this run's turns, plus which of the BUSINESS lane's
    turns did NOT finish at `stage=remembered, status=done` - `_run_business_answer`'s own
    terminal write (`engine.py`, S6c), the same close every `BUSINESS_BRANCH_KINDS` arm
    uses (`business.complete_answer` for all three). NOT `stage="sent"`: that stage closes
    the CANNED lanes (`canned_lanes.COMPLETED_BRANCH_KINDS`, a disjoint set from
    `BUSINESS_BRANCH_KINDS` below) - a first version of this check used it, on the
    strength of the incident report that named it, and it turned every
    successfully-answered `business_query` row into a false "BUSINESS PATH INCOMPLETE",
    caught by reading the actual column values off a real run (see the PR's evidence
    section) rather than by inference from the code. A turn that stops anywhere else
    (most tellingly `access_denied`) proves the gate measured a refusal, not an answer.

    `business_count` sums `BUSINESS_BRANCH_KINDS`, not just `TARGET_BRANCH_KIND`, and
    `business_incomplete` checks every row whose `branch_kind` is IN that set (not just
    `TARGET_BRANCH_KIND`) for the same reason: a run this script fires only ever reaches
    `business_query` today, but both checks are written against every arm the lane owns
    so neither quietly stops meaning anything the day a different question is added.
    `total` is what `main()` compares `business_count` against for AC-711's STRICT
    reading - every turn lands on the business lane, not merely "at least one did".
    """
    from collections import Counter

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

    counts = Counter(row.branch_kind or "(none)" for row in rows)
    business_incomplete = [
        f"{row.contact_respond_id}#{_index_of(row.message_id)} "
        f"stage={row.stage} status={row.status}"
        for row in rows
        if row.branch_kind in BUSINESS_BRANCH_KINDS
        and not (row.stage == "remembered" and row.status == "done")
    ]
    return _BusinessPathReport(
        branch_kind_counts=dict(counts),
        access_denied=counts.get("access_denied", 0),
        total=len(rows),
        business_count=sum(counts.get(k, 0) for k in BUSINESS_BRANCH_KINDS),
        business_incomplete=business_incomplete,
    )


def _business_lane_switches() -> tuple[bool, list[str]]:
    """`(chatbot_business_lane_enabled, chatbot_completed_lanes)` off THIS checkout's
    `system_settings` singleton row - the same row `engine.py`'s `_read_switches` /
    `_settings_row` reads once per turn (`db.query(SystemSetting).first()`)."""
    from app.models.user import SystemSetting

    db = _script_session()
    try:
        row = db.query(SystemSetting).first()
    finally:
        db.close()
    if row is None:
        return False, []
    lanes = getattr(row, "chatbot_completed_lanes", None)
    return bool(getattr(row, "chatbot_business_lane_enabled", False)), list(lanes or [])


def _check_business_lane_switches(*, production: bool = False) -> str | None:
    """`None` when the business lane may both RUN and ANSWER `TARGET_BRANCH_KIND`;
    otherwise the refusal message for `main()` to print and exit on.

    Both `system_settings.chatbot_business_lane_enabled` and `TARGET_BRANCH_KIND` being a
    member of `chatbot_completed_lanes` are required (AC-809/AC-810,
    `_business_lane_enabled` / `_enabled_lanes` in `app/services/chatbot/engine.py`) - off
    either one, every turn this script fires still gets `branch_kind = "business_query"`
    stamped on it (`route.decide` runs before either switch is consulted), but the head
    DELEGATES rather than answers, so the run would silently measure n8n's canned handoff
    again with a business-looking `branch_kind` on the row - the exact failure mode this
    whole fix exists to catch, one config flip further downstream.

    `production=True` (the `--production` run) never prints the `UPDATE` statement: this
    script does not flip a LIVE tenant's lane switches by SQL under any circumstance, and
    a refusal that hands the operator a working statement is an invitation to run it. The
    Settings > Chatbot screen is the only sanctioned way to flip them on a live database,
    and refusing there is the whole of the response. Off `--production`, this is shared
    DEV state instead, and printing the exact flip (with the exact restore) is what makes
    "run the gate, then put it back" a copy-paste rather than a guess.
    """
    enabled, lanes = _business_lane_switches()
    if enabled and TARGET_BRANCH_KIND in lanes:
        return None
    if production:
        return (
            f"system_settings has chatbot_business_lane_enabled={enabled} and "
            f"chatbot_completed_lanes={lanes!r} - {TARGET_BRANCH_KIND!r} must be in both "
            "before this can run against production. Flip the lane switches on the "
            "Settings > Chatbot screen first (this script never writes system_settings "
            "on a production database, by SQL or otherwise)."
        )
    import json as _json

    return (
        f"system_settings has chatbot_business_lane_enabled={enabled} and "
        f"chatbot_completed_lanes={lanes!r} in {_database_name()} - {TARGET_BRANCH_KIND!r} "
        "must be in both for the CRM to ANSWER this script's turns instead of delegating "
        "them to n8n. Flip both on, run the gate, then restore these EXACT values "
        "(printed here so the restore is not a guess):\n"
        "  UPDATE system_settings SET chatbot_business_lane_enabled = true, "
        "chatbot_completed_lanes = (SELECT COALESCE(jsonb_agg(DISTINCT e), '[]'::jsonb) "
        "FROM jsonb_array_elements(chatbot_completed_lanes || "
        f"'[\"{TARGET_BRANCH_KIND}\"]'::jsonb) e);\n"
        f"  -- restore after: UPDATE system_settings SET chatbot_business_lane_enabled = "
        f"{str(enabled).lower()}, chatbot_completed_lanes = "
        f"'{_json.dumps(lanes)}'::jsonb;"
    )


# Mirrors `chatbot.turns.status`'s own comment in `app/models/chatbot_turn.py`: a turn
# closes at `done` or `failed`; `queued` / `processing` / `delegated` are all still open.
NON_TERMINAL_STATUSES = ("queued", "processing", "delegated")

# How long `_wait_for_turns_to_settle` polls before grading anyway. Generous on purpose:
# a single dev worker draining a 100-turn backlog past its own client's 120 s timeout is
# exactly the shape this exists to wait out (measured, this fix's own evidence section -
# 21 rows still landed 3 minutes after the client gave up).
SETTLE_TIMEOUT_SECONDS = 180.0
SETTLE_POLL_INTERVAL_SECONDS = 2.0


def _wait_for_turns_to_settle(
    run_id: str, timeout: float = SETTLE_TIMEOUT_SECONDS
) -> tuple[float, int]:
    """Poll `chatbot.turns` for this run until none are non-terminal, or `timeout` lapses.
    Returns `(seconds waited, rows still non-terminal)`.

    Grading and cleanup used to run the instant the CLIENT gave up waiting - but a single
    overloaded worker keeps draining its backlog long after that, and `_delete_contacts`
    running while it does deletes a contact the SERVER is still mid-turn for. The next
    request for it then fails at `received` ("contact not found") instead of recording
    whatever the turn was actually doing, which is a different failure with a different
    cause, mixed into the same report. Measured on this fix's own evidence run: 21 turns
    landed as `branch_kind=None, stage=received, status=failed` for exactly this reason,
    3 minutes after the client's 120 s timeout and after cleanup had already run.

    `main()` waits HERE, before grading, and cleans up AFTER grading - so grading and
    cleanup see the same settled rows, and neither races the backend's own drain.
    """
    from app.models.chatbot_turn import ChatbotTurn

    deadline = time.monotonic() + timeout
    started = time.monotonic()
    remaining = 0
    while True:
        db = _script_session()
        try:
            remaining = (
                db.query(ChatbotTurn)
                .filter(
                    ChatbotTurn.contact_respond_id.like(f"{CONTACT_PREFIX}{run_id}-%"),
                    ChatbotTurn.status.in_(NON_TERMINAL_STATUSES),
                )
                .count()
            )
        finally:
            db.close()
        if remaining == 0 or time.monotonic() >= deadline:
            return time.monotonic() - started, remaining
        time.sleep(SETTLE_POLL_INTERVAL_SECONDS)


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
            "SECOND, owner-run burst - mocked first, then this - and the mode AC-711's 12s "
            "p95 applies to. Allowed with --production (that pair IS what cutover-day "
            "traffic looks like): it spends real model budget and runs on the same workers "
            "as live customers, so it prints a warning and still needs --production's "
            "typed confirmation."
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
    parser.add_argument(
        "--production",
        action="store_true",
        help=(
            "Acknowledge this checkout's ENVIRONMENT is production and confirm "
            "interactively before writing to it. Required to run at all when "
            "ENVIRONMENT=production - refused without it. The settings precheck also "
            "refuses outright in this mode rather than printing an UPDATE: this script "
            "never writes system_settings on a live database."
        ),
    )
    args = parser.parse_args(argv)

    if not args.api_key:
        print("EXTERNAL_API_KEY is not set (or pass --api-key)", file=sys.stderr)
        return 2

    # A DATABASE-level guard, not a hostname substring: `--base-url` is where the
    # BACKEND lives, and on the prod host that is `http://localhost:8000` inside the
    # `backend` container - a hostname check localhost trivially bypasses. What actually
    # says "this writes to the live database" is the CHECKOUT's own `ENVIRONMENT`
    # (`app/config.py`, `ENVIRONMENT=production` in compose), the same value the backend
    # itself boots with.
    from app.config import settings as app_settings

    is_production = app_settings.environment == "production"
    if is_production and not args.production:
        print(
            f"this checkout's ENVIRONMENT is {app_settings.environment!r} - refusing to "
            "run against a production database without --production. Point this at a "
            "lane backend instead, or pass --production if this really is the owner's "
            "cutover-day run.",
            file=sys.stderr,
        )
        return 2
    if is_production:
        # Printed BEFORE seeding, and named in full: `--keep-contacts` on a live database
        # is not a debugging convenience, it is rows left in a customer-facing table, so
        # the operator confirms having read exactly what lands and what does not.
        print(
            "PRODUCTION RUN. This will write, then remove again in a `finally` (unless "
            "--keep-contacts is also passed, in which case only the chatbot.turns rows "
            "are left - see the module docstring):\n"
            f"  - {args.contacts} respond_contacts rows, respond_io_id LIKE 'ZZT-load-%'\n"
            f"  - {args.contacts * len(ACCESS_AGENT_CODES)} contact_agent_access grants "
            f"({', '.join(ACCESS_AGENT_CODES)})\n"
            f"  - up to {args.contacts * args.messages} chatbot.turns rows (kept as "
            "evidence until deleted by hand - the exit prints the statement)\n"
        )
        if args.live_llm:
            print(
                "--live-llm on production: this spends real model budget and runs on the "
                "same workers as live customer traffic."
            )
        try:
            confirmation = input("Type 'yes' to continue: ")
        except EOFError:
            confirmation = ""
        if confirmation.strip() != "yes":
            print("refused - confirmation was not 'yes'", file=sys.stderr)
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
    switch_problem = _check_business_lane_switches(production=is_production)
    if switch_problem:
        # Checked BEFORE any contact is seeded: a run that fires 100 turns only to have
        # every one of them delegate to n8n has spent the burst, the pool sampling and the
        # rate-limit budget on nothing this script can grade.
        print(switch_problem, file=sys.stderr)
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

    seed_problem = _seed_contacts(contacts, run_id)
    if seed_problem:
        print(seed_problem, file=sys.stderr)
        return 2
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

    # Wait for the SERVER to actually finish every turn before grading OR cleaning up -
    # see `_wait_for_turns_to_settle`'s own docstring for the incident this fixes (a
    # contact deleted mid-drain fails its still-in-flight turn at `received`, which is a
    # cleanup-timing artefact, not the turn's real outcome).
    settle_elapsed, still_pending = _wait_for_turns_to_settle(run_id)
    if still_pending:
        print(
            f"  {still_pending} turn(s) still non-terminal after waiting "
            f"{settle_elapsed:.1f}s - grading anyway (they may still land later)"
        )
    elif settle_elapsed > 1.0:
        print(f"waited {settle_elapsed:.1f}s for the backend to finish draining before grading")

    try:
        errors = [o for o in outcomes if o.error is not None or o.status_code != 200]
        durations = sorted(o.seconds for o in outcomes)
        p95 = durations[max(0, int(len(durations) * 0.95) - 1)] if durations else 0.0
        p50 = statistics.median(durations) if durations else 0.0

        # Order, per contact, graded from the SERVER's rows - see `_grade_order`. The
        # client's own send order cannot answer this: it fired the whole burst at once.
        report = _grade_order(run_id, args.contacts, args.messages)
        out_of_order, jitter, missing = report.out_of_order, report.jitter, report.missing

        # Did the turns reach the BUSINESS answer path, or just the access gate in front
        # of it (this fix - see the module docstring). Printed unconditionally, same
        # reasoning as `_BusinessPathReport`'s own docstring: a refused turn is fast and
        # well-ordered, so ordering and error counts alone cannot tell the reader this
        # gate measured anything.
        business = _grade_business_path(run_id)

        print(f"wall {wall:.1f}s  turns {len(outcomes)}  p50 {p50:.2f}s  p95 {p95:.2f}s")
        print(f"errors {len(errors)}  out-of-order contacts {len(out_of_order)}")
        print(
            f"overlap pairs checked {report.checked_pairs}  skipped {report.skipped_pairs}"
        )
        print(
            f"db connections: baseline {gauge.baseline}  peak {gauge.peak}  "
            f"delta {gauge.peak - gauge.baseline} (pg_stat_activity, whole database)"
        )
        print(f"branch_kind: {business.branch_kind_counts}")
        for outcome in errors[:10]:
            print(
                f"  ERROR {outcome.contact}#{outcome.index} {outcome.status_code} {outcome.error}"
            )
        for entry in out_of_order[:10]:
            print(f"  OUT OF ORDER {entry}")
        if jitter:
            print(
                f"  (client jitter: {len(jitter)} contact(s) whose messages ARRIVED out of "
                f"send order - the CRM answers in arrival order, so this is not a failure)"
            )
        if missing:
            print(f"  {missing} turn row(s) missing - the burst did not all reach chatbot.turns")
        if report.skipped_pairs:
            print(
                f"  {report.skipped_pairs} overlap pair(s) could not be evaluated (no "
                "execution start on the trace) - the no-overlap clause did not cover them"
            )
        if business.access_denied:
            print(
                f"  {business.access_denied} turn(s) ended access_denied - the access gate "
                "refused them before resolve/tier-gate/fetch/answer ever ran. Check the "
                "seeded contacts' workspace link and contact_agent_access grant."
            )
        for entry in business.business_incomplete[:10]:
            print(f"  BUSINESS PATH INCOMPLETE {entry}")
        off_business = business.total - business.business_count
        if outcomes and off_business:
            # STRICT, per AC-711's own wording: every turn lands on the business lane, not
            # merely "at least one did". `access_denied` and `business_incomplete` each
            # name their own failure; this is the general case - any row whose branch_kind
            # is not in BUSINESS_BRANCH_KINDS, for any reason, printed against the
            # histogram above so the reader sees exactly where it went instead of just a
            # count.
            print(
                f"  {off_business} of {business.total} turn(s) did not land on a business "
                f"branch ({sorted(BUSINESS_BRANCH_KINDS)}) - see the branch_kind counts "
                "above for where they actually went."
            )

        green = (
            not errors
            and not out_of_order
            and not missing
            and not report.skipped_pairs
            and not business.business_incomplete
            and (not outcomes or off_business == 0)
            and p95 < P95_TARGET_SECONDS
        )
        print("GREEN" if green else "RED")
        if not green and p95 >= P95_TARGET_SECONDS:
            print(f"  p95 {p95:.2f}s is over the {P95_TARGET_SECONDS}s target")
        if args.keep_contacts:
            print(
                "clean up with:\n"
                f"  DELETE FROM chatbot.turns WHERE contact_respond_id LIKE "
                f"'ZZT-load-{run_id}-%';\n"
                "  DELETE FROM contact_agent_access WHERE respond_contact_id IN "
                "(SELECT id FROM respond_contacts WHERE respond_io_id LIKE "
                f"'ZZT-load-{run_id}-%');\n"
                f"  DELETE FROM respond_contacts WHERE respond_io_id LIKE "
                f"'ZZT-load-{run_id}-%';"
            )
        else:
            print(
                "clean up with: DELETE FROM chatbot.turns WHERE contact_respond_id "
                f"LIKE 'ZZT-load-{run_id}-%';"
            )
        return 0 if green else 1
    finally:
        if not args.keep_contacts:
            _delete_contacts(contacts)


if __name__ == "__main__":
    raise SystemExit(main())
