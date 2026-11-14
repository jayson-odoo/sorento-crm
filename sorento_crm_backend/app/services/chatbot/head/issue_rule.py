"""WA-COMPLAINT-INTAKE: a report of a CRM or assistant problem is ideate (an issue to log), in the STORED parser
prompt. Production runs the stored `chatbot_semantic_parser` version, not `parser_template.TEMPLATE`, so the rule
ships as three anchored edits of the stored text (documentation/plans/chatbot/PROMPT-wa-issue-ideate.md). One
function: the committed candidate file and migration `wa_0002_parser_issue_ideate` both come from it. Pure."""
from __future__ import annotations

#: In both this rule and `parser_template.TEMPLATE`'s ideate line, so the two agree. Its presence means the text
#: already carries the rule.
SHARED_PHRASE = "a problem with the CRM system or the assistant itself"

#: Edit 1, in the `ideate / submit_idea` bullet.
BULLET_OLD = "a complaint about existing behaviour (stays portal_link/complaint);"
BULLET_NEW = "a complaint about a product or an order (stays portal_link/complaint);"
#: Edit 2, in the same bullet line: the rule itself, added in place (no new line next to the continuation rules).
HUMAN_OLD = "asking for a human (stays request_for_help)."
HUMAN_NEW = (
    "asking for a human (stays request_for_help). ALSO ideate: the user reports a problem with the CRM system "
    "or the assistant itself (it errors, does not work or answers wrongly), or says they want to report one "
    "before saying what it is: an issue to log, no routing, never request_for_help or an IT or support team."
)
#: Edit 3, a whole line in `== ROUTING ==`.
ROUTING_OLD = "  - ideate (an idea is never escalated), or none of these this turn -> NO routing: null / null"
ROUTING_NEW = "  - ideate (an idea or an issue report is never escalated), or none of these this turn -> NO routing: null / null"


def _once(count: int, anchor: str) -> None:
    if count != 1:
        raise ValueError(f"issue rule anchor found {count} times, expected once: {anchor!r}")


def apply_issue_rule(text: str) -> str | None:
    """`text` with the three edits, each a line changed in place (no line added). None when it already
    carries the rule (`SHARED_PHRASE`). Raises ValueError when an anchor does not occur exactly once or edit
    2's anchor is not on the ideate bullet's own line. Lines split and join on "\\n" only, so every other
    byte (a trailing newline included) is kept."""
    if SHARED_PHRASE in text:
        return None
    lines = text.split("\n")
    _once(text.count(BULLET_OLD), BULLET_OLD)
    _once(text.count(HUMAN_OLD), HUMAN_OLD)
    _once(lines.count(ROUTING_OLD), ROUTING_OLD)
    bullet = next(n for n, line in enumerate(lines) if BULLET_OLD in line)
    if HUMAN_OLD not in lines[bullet]:
        raise ValueError(f"issue rule anchor is not on the ideate bullet line: {HUMAN_OLD!r}")
    lines[lines.index(ROUTING_OLD)] = ROUTING_NEW
    lines[bullet] = lines[bullet].replace(BULLET_OLD, BULLET_NEW).replace(HUMAN_OLD, HUMAN_NEW)
    return "\n".join(lines)
