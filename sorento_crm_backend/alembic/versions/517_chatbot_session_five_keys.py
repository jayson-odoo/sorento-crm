"""Convert every stored chatbot session to the five-key shape (AC-1001, AC-1033, D8).

`respond_contacts.session_vars` held a 34-key bag describing ONE TURN. L1-S3 made it five
keys describing the CONVERSATION - `focus`, `open_question`, `ideation`, `access_levels`,
`contains_flyer` - and the engine reads nothing else. Every contact who has ever written is
still carrying the old shape, so without this migration the first message after deploy finds
no focus and no open question: a customer looking at a numbered picker would have their "2"
answered as a new question. DoD gate 2 - existing rows are backfilled, not left to a
compatibility branch that would have to live forever.

**The conversion is the grader mapping, in Python** (`tests/chatbot/worlds.py::
map_expected_variables_to_five_keys` is the same translation for captured worlds), and it is
a pure function so it can be driven on literal dicts by
`tests/chatbot/test_session_five_keys_migration.py` rather than only through a database.

**Self-contained on purpose.** It imports nothing from `app.services.chatbot`: a migration is
frozen history, and a rule it borrowed would change under it the next time that package moves.

**KEYSET batches of 500, by id.** It used to SELECT every row with a `session_vars` at all
and hold the whole conversion in a list before writing any of it, so the memory it needed
grew with the contact table - on a tenant with a large one that is the migration itself
falling over on deploy, which is the worst possible moment. `WHERE id > :last ORDER BY id
LIMIT 500` reads and writes one bounded page at a time. One transaction still (alembic's
own), so a failure rolls the whole conversion back rather than leaving half the tenant in
each shape. No row locking: this runs with the API down.

Revision ID: 517_chatbot_session_5key
Revises: 516_chatbot_parser_v3_asks
"""
import json
import logging
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "517_chatbot_session_5key"
down_revision = "516_chatbot_parser_v3_asks"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

BATCH = 500

# The five keys, and the only keys, a converted session holds.
FIVE_KEYS = ("focus", "open_question", "ideation", "access_levels", "contains_flyer")

# `pending.kind` -> the open-question kind that replaced it (D5: an escalate offer IS a
# `team_pick` with one team).
KIND_BY_PENDING = {
    "escalation_offer": "team_pick",
    "team_clarify": "team_pick",
    "company_clarify": "company_pick",
    "tier_ask": "tier_pick",
    "member_offer": "member_offer",
}

# `selection_context` -> the same, for a session whose marker was never written (the context
# is what the did-you-mean lifecycle set, and it outlived `pending` on most turns).
KIND_BY_CONTEXT = {
    "disambiguation": "product_pick",
    "suggest_offer": "product_pick",
    "member_offer": "member_offer",
    "tier_offer": "tier_pick",
    "team_clarify": "team_pick",
    "company_clarify": "company_pick",
}


def _is_dict(value: Any) -> bool:
    return isinstance(value, dict)


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _slot(value: Any) -> dict[str, Any] | None:
    """One focus slot, or None when the legacy session said nothing about that axis.

    `set_at_turn` is 0 and `source` is `reuse`: a converted session has no turn number to
    date the slot to, and `reuse` is the honest source for a value this migration inferred
    rather than one a rule just wrote. `set_at` is None, as it is on every slot the engine
    writes (AC-206).
    """
    if value is None or value == [] or value == {} or value == "":
        return None
    return {"value": value, "set_at_turn": 0, "set_at": None, "source": "reuse"}


def _entities_of(variables: dict[str, Any], hint: str) -> list[dict[str, Any]]:
    return [
        e
        for e in _list(variables.get("entities"))
        if _is_dict(e) and str(e.get("hint") or "").strip().lower() == hint
    ]


def _rows_are_customers(rows: list) -> bool:
    return bool(rows) and all(
        str(r.get("entity_type") or "").strip().lower() == "customer"
        for r in rows
        if _is_dict(r)
    )


def _freeze(rows: Any) -> list[dict[str, Any]]:
    """The roster the customer was shown, numbered from 1 where it was not already."""
    frozen: list[dict[str, Any]] = []
    for position, row in enumerate(_list(rows), start=1):
        if not _is_dict(row):
            continue
        idx = row.get("idx")
        numbered = isinstance(idx, int) and idx >= 1
        frozen.append({**row, "idx": idx if numbered else position})
    return frozen


def _open_question_of(variables: dict[str, Any]) -> dict[str, Any] | None:
    """What the bot was waiting for, off the marker and the context, exactly as the grader
    mapping reads them. `None` when the session describes no question at all."""
    pending = variables.get("pending") if _is_dict(variables.get("pending")) else {}
    context = str(variables.get("selection_context") or "").strip()
    kind = KIND_BY_PENDING.get(str(pending.get("kind") or "")) or KIND_BY_CONTEXT.get(context)
    if kind is None:
        return None

    # The dym roster wins when both are present: it is the one the reply NUMBERED, so it is
    # the one the customer is looking at.
    rows = _freeze(variables.get("dym_last_result_set") or variables.get("last_result_set"))
    if kind == "product_pick" and _rows_are_customers(rows):
        kind = "customer_pick"

    expects = "pick"
    if kind == "member_offer":
        expects = "yes_no"
    if str(pending.get("kind") or "") == "escalation_offer":
        # ONE team, answered yes or no - the escalate offer as the customer sees it (D5).
        expects = "yes_no"
        team = pending.get("team")
        rows = [{"idx": 1, "team": team, "label": team}] if team else []
    if context == "team_clarify" and _list(pending.get("options")):
        rows = _freeze(pending.get("options"))

    return {
        "kind": kind,
        "options": rows,
        "expects": expects,
        "asked_at_turn": 0,
        "asked_at": None,
        "payload": {
            "team": pending.get("team"),
            "domain": pending.get("domain") or variables.get("domain_hint"),
            "keep": [],
        },
    }


def convert(session_vars: Any) -> dict[str, Any] | None:
    """One stored `session_vars` blob, in the five-key shape. `None` = leave the row alone.

    The engine stores `{"variables": {...}}`; a blob written through
    `PUT /external/conversation-variables` is flat. Both are handled, and the wrapper is
    preserved, because the reader that follows this migration reads whichever it finds.
    """
    if not _is_dict(session_vars):
        return None
    wrapped = _is_dict(session_vars.get("variables"))
    variables = session_vars["variables"] if wrapped else session_vars
    if not _is_dict(variables):
        return None
    if "open_question" in variables:
        return None  # already converted; never rewrite a session twice

    focus: dict[str, Any] = {}
    products = _entities_of(variables, "product")
    if products:
        focus["products"] = _slot(products)
    domain = variables.get("domain_hint")
    if domain:
        focus["domains"] = _slot([domain])
    for hint in ("customer", "transporter", "warehouse"):
        named = _entities_of(variables, hint)
        if named:
            focus[hint] = _slot(named[0])
    window = {
        "start": variables.get("date_filter_start"),
        "end": variables.get("date_filter_end"),
        "mode": variables.get("date_mode"),
    }
    if window["start"] or window["end"]:
        focus["date_window"] = _slot(window)
    attributes = [a for a in _list(variables.get("requested_attributes")) if a]
    if attributes:
        focus["attributes"] = _slot(attributes)
    tier = [t for t in _list(variables.get("tier_menu")) if t]
    if tier:
        focus["tier"] = _slot(tier)
    brands = [b for b in _list(variables.get("query_brands")) if b]
    if brands:
        focus["brands"] = _slot(brands)

    converted = {
        "focus": focus or None,
        "open_question": _open_question_of(variables),
        # Carried verbatim: an open draft the contact may come back to, what they are
        # allowed to see, and whether their last message carried a flyer.
        "ideation": variables.get("ideation"),
        "access_levels": variables.get("access_levels") or [],
        "contains_flyer": bool(variables.get("contains_flyer")),
    }
    return {"variables": converted} if wrapped else converted


def upgrade() -> None:
    bind = op.get_bind()
    seen = converted_count = 0
    last_id: Any = None

    while True:
        page = bind.execute(
            sa.text(
                "SELECT id, session_vars FROM respond_contacts "
                "WHERE session_vars IS NOT NULL "
                + ("AND id > :last " if last_id is not None else "")
                + "ORDER BY id LIMIT :limit"
            ),
            {"limit": BATCH, **({"last": last_id} if last_id is not None else {})},
        ).fetchall()
        if not page:
            break
        last_id = page[-1].id
        seen += len(page)

        for row in page:
            raw = row.session_vars
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except Exception:
                    continue
            converted = convert(raw)
            if converted is None:
                continue
            bind.execute(
                sa.text(
                    "UPDATE respond_contacts SET session_vars = CAST(:sv AS jsonb) "
                    "WHERE id = :id"
                ),
                {"id": row.id, "sv": json.dumps(converted)},
            )
            converted_count += 1

    logger.info(
        "converted %s of %s stored chatbot sessions to the five-key shape",
        converted_count,
        seen,
    )


def downgrade() -> None:
    """A NO-OP, deliberately.

    The 34 keys described one turn and the conversion drops them; there is nothing to
    restore them from, and inventing a turn's worth of diagnostics to satisfy a downgrade
    would write fiction into a customer's session. A rollback of this release runs the old
    engine against five-key sessions, which reads as a contact whose conversation has just
    been closed - the state the old engine handles every day.
    """
