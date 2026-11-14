"""WA-COMPLAINT-INTAKE: a report of a CRM or assistant problem is ideate (an issue to log), in the STORED parser
prompt. Production runs the stored `chatbot_semantic_parser` version, not `parser_template.TEMPLATE`, so the rule
ships as six anchored edits of the stored text (documentation/plans/chatbot/PROMPT-wa-issue-ideate.md). One
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
    "or the assistant itself (it errors, keeps loading, does not work or answers wrongly, whatever screen or "
    "list it is on), or says they want to report one before saying what it is: an issue to log, no routing, "
    "never request_for_help or an IT or support team, also when the user names IT or a team to report it to."
)
#: Edit 3, a whole line in `== ROUTING ==`.
ROUTING_OLD = "  - ideate (an idea is never escalated), or none of these this turn -> NO routing: null / null"
ROUTING_NEW = "  - ideate (an idea or an issue report is never escalated), or none of these this turn -> NO routing: null / null"
#: Edit 4, MESSAGE TYPE rule 1: an issue report is exempt from the named-team rule, appended in place.
RULE1_OLD = (
    'Customer/company names (e.g. "today plumbing", "total home") are NOT departments and never trigger '
    "request_for_help."
)
RULE1_NEW = RULE1_OLD + (
    " A report of a problem with the CRM system or the assistant is NOT request_for_help, even when it names "
    "IT, the IT team or a support team, or asks to report or send it to them: it is ideate (an issue to log, "
    "see the ideate bullet), message_type business_query, no routing. Only an ask to be put through to IT or "
    "a person that neither reports a problem nor says the user wants to report one stays request_for_help."
)
#: Edit 5, the "outranks" line: request_for_help never outranks an issue report, appended in place.
OUTRANK_OLD = (
    '"request_for_help" outranks business_query, clarification and casual, even when the message also '
    "mentions a product or order."
)
OUTRANK_NEW = OUTRANK_OLD + " It never outranks a report of a CRM system or assistant problem (rule 1)."
#: Edit 6, the DECISIVE signal-word rule: a report that the assistant or a screen got it wrong sets no domain,
#: appended in place.
DECISIVE_OLD = "Only with NO decisive term AND a genuinely ambiguous domain \u2192 domain_hint and intent_hint null."
DECISIVE_NEW = DECISIVE_OLD + (
    " One exception: when the user says the assistant (the bot, the AI, its answer) or a CRM screen got "
    "something wrong, a signal word only names what the problem was about and sets no domain; that report is "
    "ideate (see the ideate bullet). A user who questions or disputes a record's own figure or status, without "
    "blaming the assistant or a screen, keeps the domain."
)


def _once(count: int, anchor: str) -> None:
    if count != 1:
        raise ValueError(f"issue rule anchor found {count} times, expected once: {anchor!r}")


def apply_issue_rule(text: str) -> str | None:
    """`text` with the six edits, each changing a line in place (no line added). None when it already
    carries the rule (`SHARED_PHRASE`). Raises ValueError when an anchor does not occur exactly once or edit
    2's anchor is not on the ideate bullet's own line. Lines split and join on "\\n" only, so every other
    byte (a trailing newline included) is kept."""
    if SHARED_PHRASE in text:
        return None
    lines = text.split("\n")
    _once(text.count(BULLET_OLD), BULLET_OLD)
    _once(text.count(HUMAN_OLD), HUMAN_OLD)
    _once(lines.count(ROUTING_OLD), ROUTING_OLD)
    _once(text.count(RULE1_OLD), RULE1_OLD)
    _once(text.count(OUTRANK_OLD), OUTRANK_OLD)
    _once(text.count(DECISIVE_OLD), DECISIVE_OLD)
    bullet = next(n for n, line in enumerate(lines) if BULLET_OLD in line)
    if HUMAN_OLD not in lines[bullet]:
        raise ValueError(f"issue rule anchor is not on the ideate bullet line: {HUMAN_OLD!r}")
    lines[lines.index(ROUTING_OLD)] = ROUTING_NEW
    lines[bullet] = lines[bullet].replace(BULLET_OLD, BULLET_NEW).replace(HUMAN_OLD, HUMAN_NEW)
    for old, new in ((RULE1_OLD, RULE1_NEW), (OUTRANK_OLD, OUTRANK_NEW), (DECISIVE_OLD, DECISIVE_NEW)):
        n = next(n for n, line in enumerate(lines) if old in line)
        lines[n] = lines[n].replace(old, new)
    return "\n".join(lines)
