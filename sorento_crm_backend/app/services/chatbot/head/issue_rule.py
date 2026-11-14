"""WA-COMPLAINT-INTAKE: a report of a CRM or assistant problem is ideate (an issue to log), in the STORED parser
prompt. Production runs the stored `chatbot_semantic_parser` version, not `parser_template.TEMPLATE`, so the rule
ships as two anchored edits of the stored text (documentation/plans/chatbot/PROMPT-wa-issue-ideate.md). One
function: the committed candidate file and migration `wa_0002_parser_issue_ideate` both come from it. Pure."""
from __future__ import annotations

#: In both this rule and `parser_template.TEMPLATE`'s ideate line, so the two agree. Its presence means the text
#: already carries the rule.
SHARED_PHRASE = "a problem with the CRM system or the assistant itself"

#: Edit 1, in the `ideate / submit_idea` bullet, plus the line inserted directly after that bullet line.
BULLET_OLD = "a complaint about existing behaviour (stays portal_link/complaint);"
BULLET_NEW = "a complaint about a product or an order (stays portal_link/complaint);"
INSERTED_LINE = (
    "    → ALSO ideate: the user REPORTS a problem with the CRM system or the assistant itself (an error, a "
    "screen or page that does not load or does not work, an answer from the assistant that is wrong). That "
    "is an issue to log: domain_hint \"ideate\", intent_hint \"submit_idea\", message_type \"business_query\", "
    "no routing (null / null). It is never request_for_help, never an IT or support team, and never the "
    "domain of the screen it is about; only an explicit ask for a person to take it over is "
    "request_for_help. Asking about or disputing a record's own data (an order's status, a stock figure, a "
    "price) is not a problem with the system: it stays in its own domain."
)
#: Edit 2, a whole line in `== ROUTING ==`.
ROUTING_OLD = "  - ideate (an idea is never escalated), or none of these this turn -> NO routing: null / null"
ROUTING_NEW = "  - ideate (an idea or an issue report is never escalated), or none of these this turn -> NO routing: null / null"


def _once(count: int, anchor: str) -> None:
    if count != 1:
        raise ValueError(f"issue rule anchor found {count} times, expected once: {anchor!r}")


def apply_issue_rule(text: str) -> str | None:
    """`text` with the two edits, None when it already carries the rule (`SHARED_PHRASE`). Raises ValueError
    when an anchor does not occur exactly once. Lines split and join on "\\n" only, so every other byte
    (a trailing newline included) is kept."""
    if SHARED_PHRASE in text:
        return None
    lines = text.split("\n")
    _once(text.count(BULLET_OLD), BULLET_OLD)
    _once(lines.count(ROUTING_OLD), ROUTING_OLD)
    bullet = next(n for n, line in enumerate(lines) if BULLET_OLD in line)
    routing = lines.index(ROUTING_OLD)
    lines[routing] = ROUTING_NEW
    lines[bullet] = lines[bullet].replace(BULLET_OLD, BULLET_NEW)
    lines.insert(bullet + 1, INSERTED_LINE)
    return "\n".join(lines)
