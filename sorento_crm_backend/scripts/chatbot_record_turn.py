#!/usr/bin/env python3
"""Record `chatbot.turns` rows into `tests/chatbot/replay_turns/<group>/<slug>.json`
for the S6 turn-replay gate (AC-1590, PLAN-chatbot-turn-rearch.md "Turn replay (the
gate)").

**Read-only.** Every query against `--db-url` is a SELECT; this script never writes to
the source database, and it never writes anywhere except under
`tests/chatbot/replay_turns/`.

    venv/bin/python scripts/chatbot_record_turn.py --db-url "$SOURCE_URL" \\
        --turn-id 19a27cfb-1d25-440e-9037-9ef9dc7b2577 --group contract --slug \\
        line-001-stock-by-location

    venv/bin/python scripts/chatbot_record_turn.py --db-url "$SOURCE_URL" \\
        --contact 437264483 --since 2026-09-15 --until 2026-09-16 --group console \\
        --slug-prefix owner-15sep

    venv/bin/python scripts/chatbot_record_turn.py --db-url "$SOURCE_URL" \\
        --test-run-id console-check-1789442546 --group console --slug-prefix run-1789442546

    venv/bin/python scripts/chatbot_record_turn.py --db-url "$SOURCE_URL" \\
        --branch-kind business_query --sample 40 --group prod_sample --is-test false

One JSON file per turn (`--contact`/`--test-run-id`/`--branch-kind` modes write one file
per matching row, numbered `<prefix>-<NNN>.json`; `--turn-id` writes exactly the file
named by `--slug`).

**Both trace shapes read the same way.** Measured against real rows in the 0915 prod
copy and this lane's own dev-stack turns (see `scripts/chatbot_record_turn.py`'s own
tests / the S6 handoff): `main` (pre-rearch) turns and turns run by this lane's engine
both put the parser's raw JSON at `trace[stage="understood"].raw.parser_raw` - the extra
S3+ verdict keys (`document`, `status`, `anaphora`) are simply absent on an older row,
never renamed or moved. No branch on trace shape is needed for the verdict read. Tool
calls are the trace entries with no `stage` and `kind == "tool"` in both shapes
(`{at, ms, kind, name, args, envelope}`); the `access` stage's own `raw` is the
`check_access()` return shape verbatim in both shapes too.

**Two fields beyond the brief's literal JSON shape, recorded for replay to work on a
BLANK test schema rather than a prod copy** (ambiguity flagged to the captain - the
brief's item 1 JSON shape names only `tool_results`; this script also writes `access`
and `resolutions`):

- `access`: the `access` stage's raw `check_access()` payload, so replay stubs
  `engine.check_access` with the SAME grant the original turn actually had, rather than
  a generic `stub_access()` default that would silently change which fields a turn was
  allowed to see.
- `resolutions`: derived, not captured directly (no trace event carries it verbatim) -
  built by pairing each verdict entity (`raw`/`canonical_code`) with any UUID that
  appears in a later tool call's args under a `*_id`/`*_ids` key. This is what lets
  `test_turn_replay.py` stub `ResolveGateServices.resolve_entity` (the seam
  `tests/chatbot/test_s6c_answer_lane.py::_stub_bundle` already uses for the same
  reason) with the SAME resolution the original turn got, instead of needing this
  lane's blank private schema to hold a matching row for every product/customer code
  a real prod turn ever mentioned - which it cannot, by the "CI's database has no
  data" rule (LESSONS-LEARNT). A token with no matching UUID anywhere downstream is
  recorded as unresolved. **This is a best-effort reconstruction, not a captured
  fact** - a domain whose tool never echoes the resolved UUID back in its args
  (none observed in the corpus this script has recorded so far) would resolve to
  nothing here; flagged for the captain rather than silently assumed complete.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import uuid as uuid_mod
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

REPLAY_ROOT = Path(__file__).resolve().parent.parent / "tests" / "chatbot" / "replay_turns"

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(value: str) -> str:
    value = _SLUG_RE.sub("-", value.lower()).strip("-")
    return value or "case"


def _stage(trace: list[dict[str, Any]] | None, name: str) -> dict[str, Any] | None:
    for entry in trace or []:
        if entry.get("stage") == name:
            return entry
    return None


def _tool_events(trace: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Every trace entry with no `stage` and `kind == "tool"` (both trace shapes)."""
    events = []
    for entry in trace or []:
        if entry.get("stage") is None and entry.get("kind") == "tool":
            events.append(entry)
    return events


def _verdict_of(trace: list[dict[str, Any]] | None) -> dict[str, Any]:
    understood = _stage(trace, "understood")
    if understood is None:
        return {}
    raw = understood.get("raw") or {}
    return raw.get("parser_raw") or raw.get("parsed") or {}


def _access_of(trace: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    access = _stage(trace, "access")
    return access.get("raw") if access else None


_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


def _is_uuid(value: Any) -> bool:
    return isinstance(value, str) and bool(_UUID_RE.match(value))


def _entity_uuids_from_tool_args(tool_events: list[dict[str, Any]]) -> set[str]:
    found: set[str] = set()
    for event in tool_events:
        args = event.get("args") or {}
        for key, value in args.items():
            if not (key.endswith("_id") or key.endswith("_ids")):
                continue
            values = value if isinstance(value, list) else [value]
            for v in values:
                if _is_uuid(v):
                    found.add(v)
    return found


def _derive_resolutions(verdict: dict[str, Any], tool_events: list[dict[str, Any]]) -> dict[str, Any]:
    """Best-effort `resolve_entity` response, from the verdict's entities and the
    UUIDs the recorded tool calls actually used (see module docstring).

    Shape MUST match the real `resolve-entity` HTTP response `resolve_gate.py` (and
    `gate.py`) consume: `{"resolutions": [{"token", "resolved", "matches": [{"uuid",
    "entity_type", "canonical_code"}, ...]}], ...}` - ONE entry per token, each
    carrying a LIST of matches, never a flat token->match record. Found this session
    (tester, 16 Sep 2026): the prior shape (`{"token", "uuid", "entity_type",
    "canonical_code"}` with no `matches` wrapper) fed straight through
    `_install_stubs`'s `_fake_resolve_entity` stub made every recorded resolution
    read back as ZERO matches (`resolve_gate.py:373`'s own `jsc.get(resolutions[0],
    "matches")` finds nothing on a flat dict), so a turn that resolved a real
    product live replayed as if nothing had resolved at all - the narrower asked to
    narrow instead of fetching, and `route()`'s `_ASK_BRANCH.get(kind,
    "clarify_menu")` catch-all turned that into a `branch_kind` divergence on
    almost every case with a confident entity, corpus-wide.
    """
    entity_uuids = sorted(_entity_uuids_from_tool_args(tool_events))
    entities = verdict.get("entities") or []
    resolutions: list[dict[str, Any]] = []
    unresolved: list[str] = []
    for idx, entity in enumerate(entities):
        if not isinstance(entity, dict):
            continue
        token = entity.get("canonical_code") or entity.get("raw")
        # No captured link from a token to ITS OWN uuid (see docstring): pair
        # positionally against the recorded tool uuids as a best effort, which is
        # exact for the (overwhelmingly common) single-entity turn and approximate
        # for a multi-entity one - flagged, not hidden.
        if idx < len(entity_uuids):
            resolutions.append(
                {
                    "token": token,
                    "resolved": True,
                    "matches": [
                        {
                            "uuid": entity_uuids[idx],
                            "entity_type": entity.get("hint"),
                            "canonical_code": entity.get("canonical_code") or entity.get("raw"),
                        }
                    ],
                }
            )
        elif token:
            resolutions.append({"token": token, "resolved": False, "matches": []})
            unresolved.append(token)
    return {
        "tokens": [e.get("raw") for e in entities if isinstance(e, dict)],
        "resolutions": resolutions,
        "unresolved_tokens": unresolved,
    }


def _pending_of(trace: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The ACTUAL open question this turn left, from the `remembered` stage's own
    `session_patch` - never from `reply.result_set`, which also carries a plain
    multi-row ANSWER listing (measured: a real 11-row stock answer with no question
    at all still populates `reply.result_set`, and grading against it produced two
    false divergences before this fix - `git log` on this script for the before/
    after). Two trace shapes, two nesting paths for the SAME fact (main's pre-rearch
    `session_patch.variables.pending`, this lane's own `session_patch.open_question`
    - measured on real rows of each shape); whichever is present wins, and a case
    genuinely asking nothing records `pending: null`, not an empty dict.
    """
    remembered = _stage(trace, "remembered")
    if remembered is None:
        return None
    session_patch = (remembered.get("raw") or {}).get("session_patch") or {}
    open_question = session_patch.get("open_question")
    if open_question is None:
        open_question = (session_patch.get("variables") or {}).get("pending")
    if not open_question:
        return None
    options = (
        open_question.get("options")
        or open_question.get("roster")
        or open_question.get("candidates")
        or []
    )
    labels = [
        (o.get("label") or o.get("code") or o.get("name"))
        for o in options
        if isinstance(o, dict)
    ]
    return {"kind": open_question.get("kind") or open_question.get("type"), "option_labels": labels}


def _expected_of(row: dict[str, Any], trace: list[dict[str, Any]], tool_events: list[dict[str, Any]]) -> dict[str, Any]:
    response = row.get("response") or {}
    actions = response.get("actions") or []
    reply = response.get("reply") or {}
    tools = []
    entity_ids: set[str] = set()
    for event in tool_events:
        args = event.get("args") or {}
        tools.append({"tool": event.get("name"), "args_keys": sorted(args.keys())})
        for key, value in args.items():
            if key.endswith("_id") or key.endswith("_ids"):
                values = value if isinstance(value, list) else [value]
                entity_ids.update(v for v in values if _is_uuid(v))
    action_kinds = [a.get("kind") for a in actions if isinstance(a, dict)]
    canned = []
    text_value = reply.get("text")
    return {
        "branch_kind": row.get("branch_kind"),
        "tools": tools,
        "entity_ids": sorted(entity_ids),
        "action_kinds": action_kinds,
        "pending": _pending_of(trace),
        "focus_after": None,  # not captured on a dry-run/test row - see script docstring
        "canned": canned,
        "text": text_value,
    }


def _scrub_pii(envelope: dict[str, Any] | None) -> dict[str, Any] | None:
    """Real names, phone numbers and emails out of a recorded envelope before it is
    ever written to disk (this corpus is committed to git).

    Contact 437264483 (`test_engine.py::CONTACT_ID`, "Jayson"/"ZZT") is the team's
    OWN standing console-test contact, already hardcoded across dozens of committed
    test files - scrubbing it too keeps ONE rule ("every envelope is scrubbed") over
    a carve-out, and costs nothing since no test reads a name/phone value. Every
    other id in a `--branch-kind` `prod_sample` is a REAL customer sampled from the
    0915 prod copy (measured: 32 distinct real names/phone numbers across one
    `--sample 40` run before this function existed) - scrubbing keeps the ENGINE
    behaviour (branch routing, tool args, reply shape) the corpus exists to gate,
    while removing what a real person could be identified by. `contact.id` itself
    is kept: it is an opaque respond.io integer the engine uses as a lookup key and
    identifies nobody on its own.
    """
    if not envelope:
        return envelope
    envelope = json.loads(json.dumps(envelope))  # deep copy, JSON-safe values only

    def _scrub_contact(contact: dict[str, Any] | None) -> None:
        if not isinstance(contact, dict):
            return
        contact_id = contact.get("id")
        if "firstName" in contact:
            contact["firstName"] = f"ZZT-{contact_id}"
        if "lastName" in contact:
            contact["lastName"] = ""
        if "phone" in contact and contact["phone"]:
            contact["phone"] = f"+60{str(contact_id)[-9:].rjust(9, '0')}"
        if "email" in contact and contact["email"]:
            contact["email"] = f"zzt-{contact_id}@example.invalid"
        assignee = contact.get("assignee")
        if isinstance(assignee, dict):
            assignee["firstName"] = "ZZT-agent"
            assignee["lastName"] = ""
            if assignee.get("email"):
                assignee["email"] = "zzt-agent@example.invalid"
        for field in ("profilePic",):
            if contact.get(field):
                contact[field] = None

    _scrub_contact(envelope.get("contact"))
    message = envelope.get("message") or {}
    _scrub_contact(message.get("contact"))
    channel = message.get("channel") or {}
    if isinstance(channel.get("meta"), str):
        # A JSON string embedding `profile.name` / `wa_id` (WhatsApp's own webhook
        # shape) - real name/phone AGAIN, one level down as text rather than a key.
        try:
            meta = json.loads(channel["meta"])
        except (TypeError, ValueError):
            meta = None
        if isinstance(meta, dict):
            profile = ((meta.get("meta") or {}).get("profile")) or {}
            if "name" in profile:
                profile["name"] = "ZZT"
            if "wa_id" in (meta.get("meta") or {}):
                meta["meta"]["wa_id"] = "60100000000"
            if "firstName" in (meta.get("meta") or {}):
                meta["meta"]["firstName"] = "ZZT"
            channel["meta"] = json.dumps(meta)
    return envelope


def _record_row(row: dict[str, Any], *, db_label: str) -> dict[str, Any]:
    trace = row.get("trace") or []
    tool_events = _tool_events(trace)
    verdict = _verdict_of(trace)
    return {
        "source": {
            "db": db_label,
            "turn_id": str(row["id"]),
            "recorded_at": row["created_at"].isoformat() if row.get("created_at") else None,
            "prompt_version": (_stage(trace, "understood") or {}).get("facts", {}).get("prompt_version"),
            "expected_from": "recorded",
        },
        "envelope": _scrub_pii(row.get("envelope")),
        "verdict": verdict,
        "tool_results": [
            {"tool": e.get("name"), "args": e.get("args"), "envelope": e.get("envelope")}
            for e in tool_events
        ],
        "access": _access_of(trace),
        "resolutions": _derive_resolutions(verdict, tool_events),
        "expected": _expected_of(row, trace, tool_events),
    }


def _write(group: str, slug: str, turns: list[dict[str, Any]]) -> Path:
    """Every file is `{"turns": [...]}` - a length-1 list for a standalone case, a
    longer list for a CHAIN replayed sequentially (state carried by the real engine
    run between steps, `test_turn_replay.py`'s own design - see that file's
    docstring). One shape for both, so the harness has one reader."""
    out_dir = REPLAY_ROOT / group
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{_slugify(slug)}.json"
    out_path.write_text(json.dumps({"turns": turns}, indent=2, sort_keys=True, default=str) + "\n")
    return out_path


_ROW_COLUMNS = (
    "id, contact_respond_id, message_id, envelope, is_test, status, branch_kind, "
    "trace, response, created_at"
)


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "contact_respond_id": row.contact_respond_id,
        "message_id": row.message_id,
        "envelope": row.envelope,
        "is_test": row.is_test,
        "status": row.status,
        "branch_kind": row.branch_kind,
        "trace": row.trace,
        "response": row.response,
        "created_at": row.created_at,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db-url", required=True, help="Source Postgres URL (read-only)")
    parser.add_argument("--group", required=True, choices=["contract", "console", "prod_sample"])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--turn-id")
    mode.add_argument("--turn-ids", help="Comma-separated turn ids, IN ORDER, as one chain")
    mode.add_argument("--contact")
    mode.add_argument("--test-run-id")
    mode.add_argument("--branch-kind")
    parser.add_argument("--slug", help="Required with --turn-id/--turn-ids: the output file's slug")
    parser.add_argument("--slug-prefix", help="Prefix for --contact/--test-run-id/--branch-kind output files")
    parser.add_argument("--since", help="ISO date/timestamp, inclusive, with --contact")
    parser.add_argument("--until", help="ISO date/timestamp, exclusive, with --contact")
    parser.add_argument("--sample", type=int, default=40, help="Row cap for --branch-kind (default 40)")
    parser.add_argument("--is-test", choices=["true", "false"], help="Filter is_test (e.g. false for prod_sample)")
    parser.add_argument("--limit", type=int, default=200, help="Row cap for --contact/--test-run-id")
    parser.add_argument(
        "--chain-by",
        choices=["test_run_id", "none"],
        default="test_run_id",
        help="With --contact: group matching rows into one chain file per "
        "envelope.test_run_id (default), or 'none' for one file per row",
    )
    args = parser.parse_args(argv)

    if args.turn_id and not args.slug:
        parser.error("--turn-id requires --slug")
    if args.turn_ids and not args.slug:
        parser.error("--turn-ids requires --slug")

    engine = create_engine(args.db_url)
    db_label = engine.url.database or "unknown"
    written: list[Path] = []

    with engine.connect() as conn:
        if args.turn_id:
            row = conn.execute(
                text(f"SELECT {_ROW_COLUMNS} FROM chatbot.turns WHERE id = :id"),
                {"id": args.turn_id},
            ).first()
            if row is None:
                print(f"no turn found for id={args.turn_id}", file=sys.stderr)
                return 1
            turn = _record_row(_row_to_dict(row), db_label=db_label)
            written.append(_write(args.group, args.slug, [turn]))
        elif args.turn_ids:
            ids = [i.strip() for i in args.turn_ids.split(",") if i.strip()]
            by_id: dict[str, Any] = {}
            rows = conn.execute(
                text(f"SELECT {_ROW_COLUMNS} FROM chatbot.turns WHERE id::text = ANY(:ids)"),
                {"ids": ids},
            ).fetchall()
            for r in rows:
                by_id[str(r.id)] = r
            missing = [i for i in ids if i not in by_id]
            if missing:
                print(f"turn id(s) not found: {missing}", file=sys.stderr)
                return 1
            turns = [_record_row(_row_to_dict(by_id[i]), db_label=db_label) for i in ids]
            written.append(_write(args.group, args.slug, turns))
        elif args.test_run_id:
            rows = conn.execute(
                text(
                    f"SELECT {_ROW_COLUMNS} FROM chatbot.turns "
                    "WHERE envelope->>'test_run_id' = :run_id ORDER BY created_at ASC LIMIT :limit"
                ),
                {"run_id": args.test_run_id, "limit": args.limit},
            ).fetchall()
            if not rows:
                print(f"no turns found for test_run_id={args.test_run_id}", file=sys.stderr)
                return 1
            turns = [_record_row(_row_to_dict(r), db_label=db_label) for r in rows]
            slug = args.slug_prefix or _slugify(args.test_run_id)
            written.append(_write(args.group, slug, turns))
        elif args.contact:
            clauses = ["contact_respond_id = :contact"]
            params: dict[str, Any] = {"contact": args.contact}
            if args.since:
                clauses.append("created_at >= :since")
                params["since"] = args.since
            if args.until:
                clauses.append("created_at < :until")
                params["until"] = args.until
            if args.is_test is not None:
                clauses.append("is_test = :is_test")
                params["is_test"] = args.is_test == "true"
            where = " AND ".join(clauses)
            rows = conn.execute(
                text(
                    f"SELECT {_ROW_COLUMNS} FROM chatbot.turns WHERE {where} "
                    "ORDER BY created_at ASC LIMIT :limit"
                ),
                {**params, "limit": args.limit},
            ).fetchall()
            prefix = args.slug_prefix or _slugify(f"contact-{args.contact}")
            if args.chain_by == "none":
                for i, row in enumerate(rows, start=1):
                    turn = _record_row(_row_to_dict(row), db_label=db_label)
                    written.append(_write(args.group, f"{prefix}-{i:03d}", [turn]))
            else:
                chains: dict[str, list[Any]] = {}
                for row in rows:
                    run_id = (row.envelope or {}).get("test_run_id") or "no-run-id"
                    chains.setdefault(run_id, []).append(row)
                for i, (run_id, chain_rows) in enumerate(sorted(chains.items()), start=1):
                    turns = [_record_row(_row_to_dict(r), db_label=db_label) for r in chain_rows]
                    written.append(_write(args.group, f"{prefix}-chain-{i:03d}-{_slugify(run_id)}", turns))
        else:  # --branch-kind (prod_sample): independent real turns, one per file
            clauses = ["branch_kind = :branch_kind"]
            params = {"branch_kind": args.branch_kind}
            if args.is_test is not None:
                clauses.append("is_test = :is_test")
                params["is_test"] = args.is_test == "true"
            where = " AND ".join(clauses)
            rows = conn.execute(
                text(
                    f"SELECT {_ROW_COLUMNS} FROM chatbot.turns WHERE {where} "
                    "ORDER BY created_at DESC LIMIT :limit"
                ),
                {**params, "limit": args.sample},
            ).fetchall()
            prefix = args.slug_prefix or _slugify(args.branch_kind)
            for i, row in enumerate(rows, start=1):
                turn = _record_row(_row_to_dict(row), db_label=db_label)
                written.append(_write(args.group, f"{prefix}-{i:03d}", [turn]))

    for path in written:
        print(f"wrote {path.relative_to(REPLAY_ROOT.parent.parent.parent)}")
    print(f"{len(written)} case(s) written to {args.group}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
