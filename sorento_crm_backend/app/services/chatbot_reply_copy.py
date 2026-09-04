"""The WhatsApp bot's canned sentences, verbatim from `escalate-catalog.js` (AC-302).

**Why this file sits OUTSIDE `app/services/chatbot/`.** `ai_prompt_registry` is a core
service and core must never import the chatbot package (AC-002, the import-boundary
test). The registry needs these strings as its fallback bodies, so they live here, next
to `chatbot_parser_prompt.py`, which exists for exactly the same reason. The package's
own `copy.py` imports them back the other way, which the boundary allows.

Journey B is what this is for: the owner opens Settings > AI Prompts, edits the
not-supported reply, publishes, and the next WhatsApp turn uses it. The strings below
are what ships and what a DB-unreachable turn falls back to - D8, parity before
improvement, so they are character-for-character today's `switch`.

**The escalate prefix is a contract, not a wording choice.** `output_exchange`'s
`offeredEscalation` matches `/would you like me to escalate/i` against the bot's OWN
persisted reply, which is how an accepted offer is recognised next turn. Reword the
prefix and ladder rank 2 dies silently on every accepted offer. R3's `pending` marker is
the structural replacement, and it is written from S2 - but the regex reader stays until
S8, so the prefix stays byte-stable until then.
"""
from __future__ import annotations

# `case 'demand_qty'`
CHATBOT_REPLY_DEMAND_QTY = "Please specify your demand quantity"

# `case 'not_supported'`. The DOMAIN LIST becomes
# `system_settings.chatbot_unsupported_domains` at S3 (AC-304); the SENTENCE is here.
CHATBOT_REPLY_NOT_SUPPORTED = (
    "Sorry, we don't support direct goods receive & SPO at the moment. You may ask "
    "about incoming stock for a specific product or container"
)

# `case 'clarify_menu'`. `{{user_goal}}` is n8n's `${qf.user_goal}` - the parser's own
# phrase for what the customer is trying to do.
CHATBOT_REPLY_CLARIFY_MENU = (
    "I see you're {{user_goal}}, Let me understand more.\n\n"
    "Are you asking about any of these?\n\n"
    "- Product (List Price, Dimension)\n"
    "- Photos, Technical Specs, Cert\n"
    "- Promotion\n"
    "- Forms\n"
    "- Stock\n"
    "- Delivery order\n"
    "- Incoming\n"
    "- Catalogue, Warranty\n\n"
    "I can help with the topics listed above."
)

# `case 'escalate_offer'`, both halves. TWO KEYS, not one with a blank: the no-team form
# is a DIFFERENT sentence ("this to our team"), and substituting an empty `{{team}}`
# would send "escalate to  team?" to a customer.
CHATBOT_REPLY_ESCALATE_OFFER = (
    "I am sorry the provided answer does not meet your requirements. Would you like me "
    "to escalate to {{team}} team?"
)
CHATBOT_REPLY_ESCALATE_OFFER_NO_TEAM = (
    "I am sorry the provided answer does not meet your requirements. Would you like me "
    "to escalate this to our team?"
)

# `case 'out_of_scope'` - a note for the human who picks the thread up, never sent to the
# customer (`includeResponse = false`). Its `{{team}}` is the RAW slug: the JS
# interpolates `qf.routing.suggested_team` directly here while the escalate-offer arm
# runs it through `_prettyTeam`, and this text is internal.
CHATBOT_REPLY_OUT_OF_SCOPE = (
    "Informed the user that request is out of scope and will proceed to escalate to "
    "the {{team}} team"
)
CHATBOT_REPLY_OUT_OF_SCOPE_NO_TEAM = (
    "Informed the user that request is out of scope and will proceed to escalate to "
    "the appropriate team"
)

# `case 'escalation_declined'` - FIXED canned reply, no LLM shaping.
CHATBOT_REPLY_ESCALATION_DECLINED = "Escalation declined."

# What the customer reads when a turn could not be finished - byte-identical to what the
# spine sends today when `sub-query-reformulator` fails (`sub-error-logger`).
#
# **It lives here, not in the package, because the ENDPOINT sends it.** The head returns
# it as an action on a failed parse and the tail's route returns it when the tail raises,
# so a copy inside `app/services/chatbot/` would have to be re-exported and the package's
# "one public entry point" rule (D3, `test_import_boundary.py`) would have to be widened
# for a string. NOT a registry key: an owner editing it in Settings could leave a failed
# turn with no words at all, and this is the one sentence that must always exist.
CHATBOT_TURN_ERROR_REPLY = (
    "Sorry, I ran into a problem understanding that. Please try again in a moment."
)


# `short name -> (registry key, template, declared {{tokens}})`. ONE table: the registry
# builds `PROMPT_KEYS` from it, the seed migration seeds from it, and the package's
# `copy.py` resolves against it, so the three can never list different keys (H28's
# lesson, applied to copy instead of to enums).
CHATBOT_REPLY_COPY: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "demand_qty": (
        "chatbot_reply_demand_qty",
        CHATBOT_REPLY_DEMAND_QTY,
        (),
    ),
    "not_supported": (
        "chatbot_reply_not_supported",
        CHATBOT_REPLY_NOT_SUPPORTED,
        (),
    ),
    "clarify_menu": (
        "chatbot_reply_clarify_menu",
        CHATBOT_REPLY_CLARIFY_MENU,
        ("user_goal",),
    ),
    "escalate_offer": (
        "chatbot_reply_escalate_offer",
        CHATBOT_REPLY_ESCALATE_OFFER,
        ("team",),
    ),
    "escalate_offer_no_team": (
        "chatbot_reply_escalate_offer_no_team",
        CHATBOT_REPLY_ESCALATE_OFFER_NO_TEAM,
        (),
    ),
    "out_of_scope": (
        "chatbot_reply_out_of_scope",
        CHATBOT_REPLY_OUT_OF_SCOPE,
        ("team",),
    ),
    "out_of_scope_no_team": (
        "chatbot_reply_out_of_scope_no_team",
        CHATBOT_REPLY_OUT_OF_SCOPE_NO_TEAM,
        (),
    ),
    "escalation_declined": (
        "chatbot_reply_escalation_declined",
        CHATBOT_REPLY_ESCALATION_DECLINED,
        (),
    ),
}
