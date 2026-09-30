"""Registry variables of the chatbot parser prompt (PLAN-prompt-dynamic-30sep D1-D5).

The owner edits the WORDING of `chatbot_semantic_parser`; every list the CRM owns sits in
that wording as a `{{name}}` token and is rendered HERE, from its table, when a turn
reads the prompt. A domain, status word, entity kind, spec, brand, team, agent or access
level saved on its admin page therefore reaches the next turn with no publish, and a
publish never rewrites the owner's text: removing a token is how he overrides a list,
and nothing puts it back.

Rendered values are cached per process for `CACHE_TTL_SECONDS`, and the cache is cleared
by an `after_commit` hook whenever the committing session wrote a row to one of
`REGISTRY_TABLES` (D5). Another process (the worker) converges within the TTL.

Core module on purpose (a sibling of `chatbot_parser_prompt.py`, which renders the same
domain and entity-kind lines): `ai_prompt_registry` calls it, and core never imports
`app/services/chatbot/` (AC-002), so the two code fallbacks come through
`app.modules.chatbot.lane_vocabulary`.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from sqlalchemy import event, text as sql
from sqlalchemy.orm import Session

PROMPT_KEY = "chatbot_semantic_parser"

CACHE_TTL_SECONDS = 30.0


@dataclass(frozen=True)
class RegistryVariable:
    name: str
    label: str
    source: str  # the admin page's name, as the chip says "from <source>"
    href: str
    tables: tuple[str, ...]
    render: Callable[[Session], str]
    count: Callable[[Session], int]


# --------------------------------------------------------------------------- #
# Readers. Raw SQL on purpose: `brands` is company scoped and the ORM scope filter would
# narrow the list to whoever happens to be asking; the prompt is one text for every turn.
# --------------------------------------------------------------------------- #


def _domain_names(db: Session) -> list[str]:
    return list(db.execute(sql("SELECT name FROM chatbot_domains ORDER BY sort_order, name")).scalars())


def _domain_words(db: Session) -> list[str]:
    words: list[str] = []
    for row in db.execute(sql("SELECT switch_words FROM chatbot_domains ORDER BY sort_order, name")):
        words.extend(row[0] or [])
    for row in _status_rows(db):
        words.extend(row["trigger_words"] or [])
    return _dedupe(words)


def _status_rows(db: Session) -> list[dict]:
    return [
        dict(r)
        for r in db.execute(
            sql(
                "SELECT domain, value, label, trigger_words FROM chatbot_status_words "
                "ORDER BY sort_order, value"
            )
        ).mappings()
    ]


def _entity_kinds(db: Session) -> list[str]:
    return list(db.execute(sql("SELECT kind FROM chatbot_entity_kinds ORDER BY sort_order, kind")).scalars())


def _brands(db: Session) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    rows = db.execute(
        sql(
            "SELECT brand_name, brand_code FROM brands WHERE is_active "
            "ORDER BY brand_name, brand_code"
        )
    )
    for name, code in rows:
        name = (name or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        code = (code or "").strip()
        out.append(f"{name} ({code})" if code else name)
    return out


def _teams(db: Session) -> list[str]:
    from app.modules.chatbot.lane_vocabulary import escalation_teams

    known = list(escalation_teams())
    codes = list(
        db.execute(
            sql(
                "SELECT DISTINCT t.code FROM agent_teams t "
                "JOIN access_agents a ON a.id = t.agent_id WHERE a.is_active"
            )
        ).scalars()
    )
    if not codes:
        return known
    order = {code: i for i, code in enumerate(known)}
    return sorted(codes, key=lambda c: (order.get(c, len(order)), c))


def _agents(db: Session) -> list[str]:
    from app.modules.chatbot.lane_vocabulary import suggested_agents

    known = list(suggested_agents())
    codes = list(db.execute(sql("SELECT code FROM access_agents WHERE is_active")).scalars())
    if not codes:
        return known
    order = {code: i for i, code in enumerate(known)}
    return sorted(codes, key=lambda c: (order.get(c, len(order)), c))


def _access_levels(db: Session) -> list[str]:
    return list(
        db.execute(
            sql(
                "SELECT name FROM contact_access_types WHERE is_active "
                "ORDER BY sort_order NULLS LAST, name"
            )
        ).scalars()
    )


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        key = (v or "").strip()
        if key and key.lower() not in seen:
            seen.add(key.lower())
            out.append(key)
    return out


# --------------------------------------------------------------------------- #
# Renderers: one text shape per variable, the shape the list had in the wording.
# --------------------------------------------------------------------------- #


def render_statuses(db: Session) -> str:
    lines = []
    for row in _status_rows(db):
        words = ", ".join(f'"{w}"' for w in row["trigger_words"] or [])
        line = f'  - "{row["value"]}" -> {row["label"]}'
        line += f": {words}." if words else "."
        if row["domain"] != "order":
            line += f' Domain "{row["domain"]}".'
        lines.append(line)
    return "\n".join(lines)


def _render_domains_detail(db: Session) -> str:
    from app.services.chatbot_parser_prompt import domain_line

    rows = db.execute(
        sql(
            "SELECT name, label, intents, switch_words, narrowing, takes_date_filter, "
            "escalation_team_code FROM chatbot_domains ORDER BY sort_order, name"
        )
    ).mappings()
    return "\n".join(domain_line(r) for r in rows)


def _render_entity_kinds_detail(db: Session) -> str:
    rows = db.execute(
        sql(
            "SELECT kind, resolver_source, did_you_mean, default_narrowing "
            "FROM chatbot_entity_kinds ORDER BY kind"
        )
    ).mappings()
    return "\n".join(
        f'Entity kind {r["kind"]}: resolver {r["resolver_source"]}. '
        f'Did-you-mean {"on" if r["did_you_mean"] else "off"}. '
        f'Default narrowing {r["default_narrowing"]}.'
        for r in rows
    )


def _render_specs(db: Session) -> str:
    from app.services.chatbot_parser_prompt import specification_lines

    return "\n".join(specification_lines(db))


def _count(query: str) -> Callable[[Session], int]:
    return lambda db: int(db.execute(sql(query)).scalar() or 0)


_DOMAINS_HREF = "/system-management/chatbot/domains"
_STATUS_HREF = "/system-management/chatbot/status-words"

VARIABLES: dict[str, RegistryVariable] = {
    v.name: v
    for v in (
        RegistryVariable(
            "domains", "Domains", "Chatbot Domains", _DOMAINS_HREF, ("chatbot_domains",),
            lambda db: " | ".join(_domain_names(db)), lambda db: len(_domain_names(db)),
        ),
        RegistryVariable(
            "domain_words", "Domain words", "Chatbot Domains + Status Words", _DOMAINS_HREF,
            ("chatbot_domains", "chatbot_status_words"),
            lambda db: ", ".join(_domain_words(db)), lambda db: len(_domain_words(db)),
        ),
        RegistryVariable(
            "domains_detail", "Domains - detail", "Chatbot Domains", _DOMAINS_HREF,
            ("chatbot_domains",), _render_domains_detail, lambda db: len(_domain_names(db)),
        ),
        RegistryVariable(
            "statuses", "Status words", "Chatbot Status Words", _STATUS_HREF,
            ("chatbot_status_words",), render_statuses, lambda db: len(_status_rows(db)),
        ),
        RegistryVariable(
            "status_values", "Status values", "Chatbot Status Words", _STATUS_HREF,
            ("chatbot_status_words",),
            lambda db: "|".join(r["value"] for r in _status_rows(db)),
            lambda db: len(_status_rows(db)),
        ),
        RegistryVariable(
            "entity_kinds", "Entity kinds", "Chatbot Entity Kinds", "/system-management/chatbot/entity-kinds",
            ("chatbot_entity_kinds",), lambda db: "|".join(_entity_kinds(db)),
            lambda db: len(_entity_kinds(db)),
        ),
        RegistryVariable(
            "entity_kinds_detail", "Entity kinds - detail", "Chatbot Entity Kinds",
            "/system-management/chatbot/entity-kinds", ("chatbot_entity_kinds",),
            _render_entity_kinds_detail, lambda db: len(_entity_kinds(db)),
        ),
        RegistryVariable(
            "specs", "Specifications", "Product Specifications", "/products/specifications",
            ("product_spec_registry",), _render_specs,
            _count("SELECT count(*) FROM product_spec_registry WHERE is_active"),
        ),
        RegistryVariable(
            "brands", "Brands", "Brands", "/master-data/brands", ("brands",),
            lambda db: ", ".join(_brands(db)), lambda db: len(_brands(db)),
        ),
        RegistryVariable(
            "teams", "Teams", "Agents and Teams", "/access-control/agents",
            ("agent_teams", "access_agents"), lambda db: "|".join(_teams(db)),
            lambda db: len(_teams(db)),
        ),
        RegistryVariable(
            "agents", "Agents", "Agents and Teams", "/access-control/agents", ("access_agents",),
            lambda db: "|".join(_agents(db)), lambda db: len(_agents(db)),
        ),
        RegistryVariable(
            "access_levels", "Access levels", "Contact Access Types",
            "/master-data/contact-access-types", ("contact_access_types",),
            lambda db: json.dumps(_access_levels(db), ensure_ascii=False, separators=(",", ":")),
            lambda db: len(_access_levels(db)),
        ),
    )
}

VARIABLE_NAMES: tuple[str, ...] = tuple(VARIABLES)

REGISTRY_TABLES: frozenset[str] = frozenset(t for v in VARIABLES.values() for t in v.tables)


# --------------------------------------------------------------------------- #
# Cache + invalidation (D5)
# --------------------------------------------------------------------------- #

_CACHE: dict[str, tuple[float, str]] = {}
_LOCK = threading.Lock()


def clear_cache() -> None:
    with _LOCK:
        _CACHE.clear()


def render_value(db: Session, name: str) -> str:
    """One variable's current text. Cached; a registry commit clears the cache."""
    now = time.monotonic()
    with _LOCK:
        hit = _CACHE.get(name)
    if hit is not None and hit[0] > now:
        return hit[1]
    value = VARIABLES[name].render(db)
    with _LOCK:
        _CACHE[name] = (now + CACHE_TTL_SECONDS, value)
    return value


def render_values(db: Session, names: set[str] | list[str] | None = None) -> dict[str, str]:
    wanted = VARIABLE_NAMES if names is None else [n for n in VARIABLE_NAMES if n in set(names)]
    return {name: render_value(db, name) for name in wanted}


_DIRTY_FLAG = "chatbot_prompt_vars_dirty"


def _touches_registry(session: Session) -> bool:
    for obj in (*session.new, *session.dirty, *session.deleted):
        table = getattr(getattr(obj, "__table__", None), "name", None)
        if table in REGISTRY_TABLES:
            return True
    return False


@event.listens_for(Session, "after_flush")
def _mark_dirty(session: Session, _ctx) -> None:
    if _touches_registry(session):
        session.info[_DIRTY_FLAG] = True


@event.listens_for(Session, "after_commit")
def _clear_on_commit(session: Session) -> None:
    if session.info.pop(_DIRTY_FLAG, False):
        clear_cache()


@event.listens_for(Session, "after_rollback")
def _forget_on_rollback(session: Session) -> None:
    session.info.pop(_DIRTY_FLAG, None)


# --------------------------------------------------------------------------- #
# The editor's "Wired to this agent" panel (R5a)
# --------------------------------------------------------------------------- #


def _last_changed(db: Session, tables: tuple[str, ...]) -> datetime | None:
    latest: datetime | None = None
    for table in tables:
        has_col = db.execute(
            sql(
                "SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' "
                "AND table_name = :t AND column_name = 'updated_at'"
            ),
            {"t": table},
        ).first()
        if not has_col:
            continue
        value = db.execute(sql(f"SELECT max(updated_at) FROM {table}")).scalar()
        if value is not None and (latest is None or value > latest):
            latest = value
    return latest


def describe(db: Session, template: str | None = None) -> list[dict]:
    """Every variable with its source, count, last change, rendered text, and whether
    `template` uses it. Uncached reads: this backs an admin screen, not a turn."""
    from app.services.ai_prompt_registry import extract_tokens

    used = extract_tokens(template or "")
    return [
        {
            "name": v.name,
            "label": v.label,
            "source": v.source,
            "href": v.href,
            "count": v.count(db),
            "last_changed": _last_changed(db, v.tables),
            "rendered": v.render(db),
            "used": v.name in used,
        }
        for v in VARIABLES.values()
    ]
