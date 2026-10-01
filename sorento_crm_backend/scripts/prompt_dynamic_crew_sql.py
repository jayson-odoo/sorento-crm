"""Generate the PROMPT-DYNAMIC crew-migration SQL (crew copy, 1 Oct 2026).

The crew copy's dev DB is migrated with plain SQL, not alembic. This writes the SQL twin of
`pdyn_0001_status_words_sales` + `pdyn_0003_prod_identical` to
`documentation/plans/chatbot/crew-migration-prompt-dynamic.sql`:

- pdyn_0001: the status words table, its 8 seed rows and the `sales` domain row
  (idempotent, the statements crew already applied).
- pdyn_0003: ONE unlabelled `chatbot_semantic_parser` version from the owner's production
  text. Each hard-coded list becomes its `{{variable}}` only where the tables, when the
  SQL runs, render exactly that text; the SQL computes each rendering the way
  `chatbot_prompt_vars` does. Lists with no SQL renderer here stay literal. Skips when a
  version from the same snapshot (or with the same template) exists.

The text carries the owner's em dashes; the SQL writes them as a placeholder that
`chr(8212)` restores, so the file passes the repo dash guard.

    venv/bin/python -m scripts.prompt_dynamic_crew_sql          # write the file
    venv/bin/python -m scripts.prompt_dynamic_crew_sql --check  # exit 1 if stale
"""
from __future__ import annotations

import hashlib
import importlib.util
import pathlib
import re
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[1]
SNAPSHOT = BACKEND / "alembic" / "data" / "chatbot_semantic_parser.prod-20261001.txt"
OUT = BACKEND.parent / "documentation" / "plans" / "chatbot" / "crew-migration-prompt-dynamic.sql"
KEY = "chatbot_semantic_parser"
EM_DASH = "\u2014"
PLACEHOLDER = "<<EM_DASH>>"
QUOTE = "$pdyn$"


def _load(name: str):
    path = BACKEND / "alembic" / "versions" / name
    spec = importlib.util.spec_from_file_location(f"_crew_sql_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _lit(value: str) -> str:
    """A SQL text literal for any piece of the owner's text."""
    assert QUOTE not in value and PLACEHOLDER not in value
    body = f"{QUOTE}{value.replace(EM_DASH, PLACEHOLDER)}{QUOTE}"
    return f"replace({body}, '{PLACEHOLDER}', chr(8212))" if EM_DASH in value else body


def _q(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _array(values) -> str:
    return "ARRAY[" + ", ".join(_q(v) for v in values) + "]::text[]"


def _renderers() -> dict[str, str]:
    """SQL for each variable, matching `chatbot_prompt_vars.VARIABLES[...].render` on any
    row whose rendering equals a clean literal (the only case that swaps)."""
    from app.modules.chatbot.lane_vocabulary import escalation_teams, suggested_agents

    known = list(suggested_agents())
    return {
        "teams": _q("|".join(escalation_teams())),
        "domains": "(SELECT string_agg(name, ' | ' ORDER BY sort_order, name) FROM chatbot_domains)",
        "status_values": "(SELECT string_agg(value, '|' ORDER BY sort_order, value) FROM chatbot_status_words)",
        "entity_kinds": "(SELECT string_agg(kind, '|' ORDER BY sort_order, kind) FROM chatbot_entity_kinds)",
        "agents": (
            "COALESCE((SELECT string_agg(code, '|' ORDER BY COALESCE(array_position("
            f"{_array(known)}, code), {len(known)}), code COLLATE \"C\") FROM access_agents WHERE is_active), "
            f"{_q('|'.join(known))})"
        ),
        "access_levels": (
            "(SELECT CASE WHEN bool_and(position('\"' in name) = 0 AND position(chr(92) in name) = 0 "
            "AND name !~ '[[:cntrl:]]') THEN '[' || string_agg('\"' || name || '\"', ',' "
            "ORDER BY sort_order NULLS LAST, name) || ']' END FROM contact_access_types WHERE is_active)"
        ),
        "entity_kinds_detail": (
            "(SELECT string_agg(format('Entity kind %s: resolver %s. Did-you-mean %s. Default narrowing %s.', "
            "kind, resolver_source, CASE WHEN did_you_mean THEN 'on' ELSE 'off' END, default_narrowing), "
            "chr(10) ORDER BY kind) FROM chatbot_entity_kinds)"
        ),
    }


def _candidates(source: str) -> list[tuple[int, int, str]]:
    """(start, end, variable) of every list `identical_wording_layer` looks at, in the
    original text, sorted by position."""
    from app.services import chatbot_prompt_vars as pv
    from app.services.chatbot_parser_prompt import BLOCKS_BEGIN, BLOCKS_END

    spans: list[tuple[int, int, str]] = []
    taken: set[tuple[int, int]] = set()
    for variable, pattern in pv._IDENTICAL_CANDIDATES:
        for m in re.finditer(pattern, source, flags=re.S):
            span = (m.start("list"), m.end("list"))
            if span not in taken:
                taken.add(span)
                spans.append((span[0], span[1], variable))
                break
    if BLOCKS_BEGIN in source and BLOCKS_END in source:
        start = source.index(BLOCKS_BEGIN) + len(BLOCKS_BEGIN)
        block = source[start : source.index(BLOCKS_END)]
        lead = len(block) - len(block.lstrip("\n"))
        offset = start + lead
        for variable, part in zip(["domains_detail", "entity_kinds_detail", "specs"], block.strip("\n").split("\n\n")):
            spans.append((offset, offset + len(part), variable))
            offset += len(part) + 2
    spans.sort()
    for (_, a_end, _), (b_start, _, _) in zip(spans, spans[1:]):
        assert a_end <= b_start, "overlapping candidate lists"
    return spans


def _pdyn_0001_sql() -> str:
    mod = _load("pdyn_0001_status_words_sales.py")
    lines = [
        "-- pdyn_0001_status_words_sales: status words table, 8 seed rows, the sales domain.",
        "CREATE TABLE IF NOT EXISTS chatbot_status_words (",
        "    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),",
        "    domain text NOT NULL,",
        "    value text NOT NULL UNIQUE,",
        "    label text NOT NULL,",
        "    trigger_words text[] NOT NULL DEFAULT '{}',",
        "    sort_order integer NOT NULL DEFAULT 0,",
        "    created_at timestamp without time zone NOT NULL DEFAULT now(),",
        "    updated_at timestamp without time zone NOT NULL DEFAULT now()",
        ");",
    ]
    for i, (domain, value, label, words) in enumerate(mod.STATUS_WORDS):
        lines.append(
            "INSERT INTO chatbot_status_words (id, domain, value, label, trigger_words, sort_order) "
            f"VALUES (gen_random_uuid(), {_q(domain)}, {_q(value)}, {_q(label)}, {_array(words)}, {i}) "
            "ON CONFLICT (value) DO NOTHING;"
        )
    d = mod.SALES_DOMAIN
    lines += [
        "INSERT INTO chatbot_domains (id, name, label, intents, tools, primary_tool, escalation_team_code, "
        "switch_words, narrowing, takes_date_filter, reveal_key, supported, ladder, sort_order)",
        f"SELECT gen_random_uuid(), {_q(d['name'])}, {_q(d['label'])}, {_array(d['intents'])}, {_array(d['tools'])}, "
        f"NULL, {_q(d['escalation_team_code'])}, {_array(d['switch_words'])},",
        "       COALESCE((SELECT narrowing FROM chatbot_domains WHERE name = 'order'), '{}'::jsonb), true, "
        f"{_q(d['reveal_key'])}, true, '{{}}',",
        "       COALESCE((SELECT max(sort_order) + 1 FROM chatbot_domains), 0)",
        f"WHERE NOT EXISTS (SELECT 1 FROM chatbot_domains WHERE name = {_q(d['name'])});",
    ]
    return "\n".join(lines)


def build_sql() -> str:
    return "\n".join(
        [
            "-- crew-migration for PROMPT-DYNAMIC (#1405). GENERATED by",
            "-- `sorento_crm_backend/scripts/prompt_dynamic_crew_sql.py`; do not edit by hand.",
            "-- Additive only. Idempotent: safe to apply twice. Never sets or moves a label.",
            "-- pdyn_0002_wording_layer has no SQL twin (its transform is Python over the copy's own",
            "-- production text); run `venv/bin/python -m scripts.publish_parser_wording_layer` for it.",
            "",
            _pdyn_0001_sql(),
            "",
            pdyn_0003_sql(),
        ]
    )


def pdyn_0003_sql() -> str:
    mod3 = _load("pdyn_0003_prod_identical.py")
    raw = SNAPSHOT.read_bytes()
    source = raw.decode("utf-8")
    sha = hashlib.sha256(raw).hexdigest()
    renderers = _renderers()
    spans = _candidates(source)

    declare = [f"    r_{name} text := {sql};" for name, sql in renderers.items()]
    pieces: list[str] = []
    report: list[str] = []
    pos = 0
    for start, end, variable in spans:
        if pos < start:
            pieces.append(_lit(source[pos:start]))
        literal = source[start:end]
        line = source[:start].count("\n") + 1
        if variable in renderers:
            cond = f"r_{variable} IS NOT DISTINCT FROM {_lit(literal)}"
            pieces.append(f"CASE WHEN {cond} THEN {_q('{{' + variable + '}}')} ELSE {_lit(literal)} END")
            action = f"CASE WHEN {cond} THEN 'replaced' ELSE 'kept literal' END"
            reason = "CASE WHEN {c} THEN NULL ELSE 'the registry renders different text' END".format(c=cond)
        else:
            pieces.append(_lit(literal))
            action = "'kept literal'"
            reason = "'no SQL renderer: the alembic migration decides this list from the tables'"
        report.append(
            f"        jsonb_build_object('variable', {_q(variable)}, 'line', {line}, 'action', {action}, 'reason', {reason})"
        )
        pos = end
    if pos < len(source):
        pieces.append(_lit(source[pos:]))

    message = mod3.MESSAGE
    body = "\n".join(
        [
            "-- pdyn_0003_prod_identical: the owner's production text of 1 Oct 2026,",
            f"-- sha256 {sha}, as ONE unlabelled version.",
            "DO $crew$",
            "DECLARE",
            *declare,
            "    t text;",
            "    rep jsonb;",
            "    v integer;",
            "    vars jsonb;",
            "    item jsonb;",
            "BEGIN",
            f"    IF EXISTS (SELECT 1 FROM ai_prompt_versions WHERE name = {_q(KEY)} "
            f"AND config_json->>'prod_snapshot_sha256' = {_q(sha)}) THEN",
            "        RAISE NOTICE 'prod snapshot already published; nothing to do';",
            "        RETURN;",
            "    END IF;",
            "    t := " + "\n      || ".join(pieces) + ";",
            "    rep := jsonb_build_array(\n" + ",\n".join(report) + "\n    );",
            f"    IF EXISTS (SELECT 1 FROM ai_prompt_versions WHERE name = {_q(KEY)} AND template = t) THEN",
            "        RAISE NOTICE 'an identical template already exists; nothing to do';",
            "        RETURN;",
            "    END IF;",
            f"    SELECT COALESCE(max(version), 0) + 1 INTO v FROM ai_prompt_versions WHERE name = {_q(KEY)};",
            "    SELECT pv.variables INTO vars FROM ai_prompt_versions pv JOIN ai_prompt_labels l ON l.version_id = pv.id",
            f"        WHERE l.name = {_q(KEY)} AND l.label = 'production';",
            "    INSERT INTO ai_prompt_versions (id, name, version, type, template, variables, config_json, commit_message, created_at)",
            f"    VALUES (gen_random_uuid(), {_q(KEY)}, v, 'text', t, COALESCE(vars, '[\"current_date\"]'::jsonb),",
            f"        jsonb_build_object('prod_snapshot', {_q(SNAPSHOT.name)}, 'prod_snapshot_sha256', {_q(sha)},",
            "            'rendered_identical', true, 'identical_report', rep, 'source', 'crew-migration SQL'),",
            f"        {_q(message)}, now());",
            "    RAISE NOTICE 'prod snapshot v%: published unlabelled', v;",
            "    FOR item IN SELECT * FROM jsonb_array_elements(rep) LOOP",
            "        RAISE NOTICE 'prod snapshot v%: {{%}} line % %', v, item->>'variable', item->>'line', item->>'action';",
            "    END LOOP;",
            "END",
            "$crew$;",
            "",
        ]
    )
    return body


def main() -> int:
    sql = build_sql()
    if "--check" in sys.argv[1:]:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != sql:
            print(f"stale: regenerate {OUT}")
            return 1
        print("up to date")
        return 0
    OUT.write_text(sql, encoding="utf-8")
    print(f"wrote {OUT} ({len(sql)} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
