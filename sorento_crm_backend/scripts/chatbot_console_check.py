#!/usr/bin/env python3
"""The owner's console check: run a file of real turns and grade the replies.

One YAML file of cases, one line of output per case, exit 1 if any case fails. It is the
step between "the tests are green" and "the owner tries it in WhatsApp": pytest proves the
code does what the contract says, this proves a REAL turn through a REAL backend still says
the right thing to a customer.

    python scripts/chatbot_console_check.py tests/chatbot/console_cases/2026-09-06.yaml \\
        --base-url http://localhost:8004

Every turn is a DRY RUN (D14): the envelope carries `is_test: true` and a `test_run_id`, so
nothing outside `chatbot.turns` is written and no WhatsApp message can leave. The parser is
the REAL one unless `--mock-parser` is passed AND the case carries its own `parser:` block -
the point of the check is that the whole turn works, and the parse is most of a turn.

**The envelope is a real one, borrowed.** A turn's first act is to read the contact's stored
state, and an unknown contact fails at `received`; so rather than inventing a shape, the
script reads the LATEST `chatbot.turns.envelope` for the contact out of this checkout's own
`DATABASE_URL` and swaps the text and the message id. That is also why it refuses a
non-local `--base-url` without `--i-know`: the database it reads and the backend it posts to
are two different pieces of configuration, and nothing here can check they agree.

**A multi-turn case feeds its own memory forward.** Each turn's `reply.session_patch`
carries `variables`, and the next turn sends it as `previous_conversation_state` - the
harness key the engine honours on a dry run (`engine.HARNESS_KEYS`). That is what makes a
picker sequence ("check stock for X" then "1") checkable without writing session state.

Reads `EXTERNAL_API_KEY` from the environment (or `--api-key`).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from typing import Any
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
TURN_PATH = "/api/v1/external/chat/turn"
UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE
)


def _script_session():
    from app.database import SessionLocal

    return SessionLocal()


def _base_envelope(contact: str) -> dict[str, Any]:
    """The contact's most recent envelope, as the shape to borrow, with their phone on it.

    Raises rather than inventing one: a hand-built envelope that happens to be missing a
    field the engine reads fails the turn at `received`, and a check whose failures are its
    own is worse than no check. The PHONE is filled in from `respond_contacts` when the
    borrowed envelope has none - a real webhook always carries it, and the escalation lane's
    assignee read is a 400 without it, which would read as a routing defect.
    """
    from sqlalchemy import text

    db = _script_session()
    try:
        row = db.execute(
            text(
                "SELECT envelope FROM chatbot.turns WHERE contact_respond_id = :c "
                "AND envelope IS NOT NULL ORDER BY created_at DESC LIMIT 1"
            ),
            {"c": str(contact)},
        ).fetchone()
        phone = db.execute(
            text("SELECT phone_number FROM respond_contacts WHERE respond_io_id = :c"),
            {"c": str(contact)},
        ).scalar()
    finally:
        db.close()
    if row is None:
        raise SystemExit(
            f"no chatbot.turns envelope for contact {contact!r} in this checkout's "
            "database - run one turn for that contact first, or pass --contact"
        )
    envelope = dict(row[0])
    stored = envelope.get("contact") or {}
    if not stored.get("phone") and phone:
        envelope["contact"] = {**stored, "phone": phone}
    return envelope


def _envelope_for(
    base: dict[str, Any],
    *,
    contact: str,
    message: str,
    run_id: str,
    parser: Any = None,
    previous_state: Any = None,
) -> dict[str, Any]:
    """The borrowed envelope with this turn's words in it. Never mutates `base`."""
    envelope = json.loads(json.dumps(base))
    envelope["contact"] = {**(envelope.get("contact") or {}), "id": str(contact)}
    envelope.setdefault("message", {})
    envelope["message"]["contact"] = {"id": str(contact)}
    inner = envelope["message"].setdefault("message", {})
    inner["contactId"] = str(contact)
    inner["messageId"] = f"console-check-{uuid.uuid4().hex[:12]}"
    inner["message"] = {"type": "text", "text": message}
    envelope["message"]["event_type"] = "message.received"
    # D14, always both markers: a console check that could answer a real customer is not a
    # check, it is an incident.
    envelope["is_test"] = True
    envelope["test_run_id"] = run_id
    envelope["shadow_of"] = None
    if parser is not None:
        envelope["mock_reformulator_output"] = parser
    else:
        envelope.pop("mock_reformulator_output", None)
    if previous_state is not None:
        envelope["previous_conversation_state"] = previous_state
    else:
        envelope.pop("previous_conversation_state", None)
    return envelope


def _post(session: Any, url: str, api_key: str, envelope: dict[str, Any], timeout: float) -> dict:
    response = session.post(
        url,
        json={"envelope": envelope},
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        timeout=timeout,
    )
    if response.status_code != 200:
        return {"_http_error": f"HTTP {response.status_code}: {response.text[:200]}"}
    return response.json()


def _pending_kind(turn_id: str | None) -> str | None:
    """The escalation lane's `pending.kind`, off the row - it is not on the 200 body."""
    if not turn_id:
        return None
    from sqlalchemy import text

    db = _script_session()
    try:
        row = db.execute(
            text("SELECT response FROM chatbot.turns WHERE id = :id"), {"id": turn_id}
        ).fetchone()
    finally:
        db.close()
    response = (row[0] if row is not None else None) or {}
    pending = response.get("pending") or {}
    kind = pending.get("kind") if isinstance(pending, dict) else None
    return str(kind) if kind else None


def _grade(expect: dict[str, Any], body: dict[str, Any], pending: str | None) -> list[str]:
    """Every expectation that did NOT hold, as sentences. Empty list is a pass."""
    failures: list[str] = []
    if "_http_error" in body:
        return [body["_http_error"]]
    reply = ((body.get("reply") or {}).get("text")) or ""
    branch = body.get("branch_kind")

    wanted_branch = expect.get("branch_kind")
    if wanted_branch and branch != wanted_branch:
        failures.append(f"branch_kind is {branch!r}, expected {wanted_branch!r}")
    for needle in expect.get("reply_contains") or []:
        if str(needle).lower() not in reply.lower():
            failures.append(f"reply does not contain {needle!r}")
    for needle in expect.get("reply_not_contains") or []:
        if str(needle).lower() in reply.lower():
            failures.append(f"reply contains {needle!r} and must not")
    if expect.get("no_uuid") is True:
        found = UUID_RE.search(reply)
        if found:
            failures.append(f"reply prints a uuid: {found.group(0)}")
    wanted_pending = expect.get("pending_kind")
    if wanted_pending and pending != wanted_pending:
        failures.append(f"pending kind is {pending!r}, expected {wanted_pending!r}")
    return failures


def _turns_of(case: dict[str, Any]) -> list[dict[str, Any]]:
    """A single-turn case and a `turns:` case, as one list of turns."""
    if isinstance(case.get("turns"), list):
        return [t for t in case["turns"] if isinstance(t, dict)]
    return [{"text": case.get("text"), "expect": case.get("expect") or {}}]


def _next_state(body: dict[str, Any]) -> Any:
    """What the NEXT turn of this case remembers: the seal's own `variables`."""
    patch = (body.get("reply") or {}).get("session_patch")
    if not isinstance(patch, dict):
        patch = body.get("session_patch")
    if not isinstance(patch, dict):
        return None
    variables = patch.get("variables")
    return variables if isinstance(variables, dict) else patch


def main(argv: list[str] | None = None) -> int:
    import requests
    import yaml

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", help="the YAML case file")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--contact", default=None, help="default respond.io contact id")
    parser.add_argument("--api-key", default=os.getenv("EXTERNAL_API_KEY"))
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument(
        "--mock-parser",
        action="store_true",
        help="use each case's own `parser:` block instead of calling the model",
    )
    parser.add_argument(
        "--i-know",
        action="store_true",
        help="allow a non-local --base-url (the database read is this checkout's own)",
    )
    args = parser.parse_args(argv)

    if not args.api_key:
        print("EXTERNAL_API_KEY is not set (or pass --api-key)", file=sys.stderr)
        return 2
    host = urlparse(args.base_url).hostname or ""
    if host not in LOCAL_HOSTS and not args.i_know:
        print(
            f"--base-url points at {host!r}, which is not local. The envelopes are read "
            "from THIS checkout's DATABASE_URL, and nothing here can check the two match; "
            "pass --i-know once you have.",
            file=sys.stderr,
        )
        return 2

    with open(args.cases, encoding="utf-8") as handle:
        document = yaml.safe_load(handle) or {}
    default_contact = args.contact or document.get("contact")
    cases = [c for c in (document.get("cases") or []) if isinstance(c, dict)]
    if not cases:
        print(f"{args.cases} has no cases", file=sys.stderr)
        return 2

    run_id = f"console-check-{int(time.time())}"
    url = args.base_url.rstrip("/") + TURN_PATH
    session = requests.Session()
    session.trust_env = False

    print(f"{run_id}  {len(cases)} cases against {args.base_url}")
    failed = 0
    for case in cases:
        name = str(case.get("name") or case.get("text") or "case")
        contact = str(case.get("contact") or default_contact or "")
        if not contact:
            print(f"FAIL  {name}\n      - no contact (pass --contact or set one in the file)")
            failed += 1
            continue
        base = _base_envelope(contact)
        previous_state = case.get("previous_conversation_state")
        case_failures: list[str] = []
        last_line = ""
        last_branch = None
        for index, turn in enumerate(_turns_of(case)):
            envelope = _envelope_for(
                base,
                contact=contact,
                message=str(turn.get("text") or ""),
                run_id=run_id,
                parser=(turn.get("parser") or case.get("parser")) if args.mock_parser else None,
                previous_state=previous_state,
            )
            body = _post(session, url, args.api_key, envelope, args.timeout)
            pending = _pending_kind(body.get("turn_id"))
            reply = ((body.get("reply") or {}).get("text")) or ""
            last_branch = body.get("branch_kind")
            last_line = reply.replace("\n", " ")[:120]
            prefix = f"turn {index + 1}: " if len(_turns_of(case)) > 1 else ""
            case_failures += [prefix + f for f in _grade(turn.get("expect") or {}, body, pending)]
            previous_state = _next_state(body)
        verdict = "FAIL" if case_failures else "PASS"
        failed += 1 if case_failures else 0
        print(f"{verdict}  {name:<44} branch={last_branch}  {last_line!r}")
        for failure in case_failures:
            print(f"      - {failure}")

    print(f"\n{len(cases) - failed} passed, {failed} failed  ({run_id})")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
