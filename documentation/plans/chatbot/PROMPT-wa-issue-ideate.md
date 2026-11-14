# Parser prompt change: a report of a CRM or assistant problem is ideate (WA-COMPLAINT-INTAKE)

- Why: crew pass CREW-PASSES-4 on df58e23d (14 Nov). The lane's rule lived only in
  `app/services/chatbot/head/parser_template.py`; production runs the stored `chatbot_semantic_parser`
  version 72, whose ideate bullet says "NOT ideate: ... a complaint about existing behaviour (stays
  portal_link/complaint)". A staff bug report went to `it_support` (access_denied) and a dealer bug report to
  a sales question.
- Base: production v72, md5 `d29c19830b22aa47403a88ddcb8e817d`, the exact file `prompt-prod-v72-d29c1983.txt`.
- Result: the exact file `prompt-wa-issue-ideate.txt`; its md5 is pinned in
  `tests/chatbot/test_wa_issue_parser_prompt.py`.
- Shipped by migration `wa_0002_parser_issue_ideate`: the SAME edits (one function,
  `app/services/chatbot/head/issue_rule.py` `apply_issue_rule`) applied to the text of the version that holds
  the `production` label when the migration runs (so the rendered policy blocks stay as they are), published as
  the next `chatbot_semantic_parser` version, UNLABELLED. Idempotent; refuses (logs and publishes nothing) when
  an anchor is missing or the text already carries the rule. Only the owner moves the production label
  (Prompts page); rollback is the reverse move.
- Owner rule kept: slot rules only, no word lists, no gold-message examples.
- Not in this change (predates the lane): the seeded fallback prompt a fresh install gets
  (`ai_prompt_registry` fallback, production v3 on an empty DB) does not carry the rule; on such a DB the migration
  logs "not published" and publishes nothing. The code template (`parser_template.py`) carries it.
- The shared phrase "a problem with the CRM system or the assistant itself" is in both this text and the code
  template's ideate line, so the two agree (pinned by the same test).

## Edits (apply by anchor, each anchor occurs exactly once in v72)

Round 11 (crew LIVE pass on v81, 14 Nov, F3): the round 9-10 text inserted a NEW line between the ideate bullet
and the bare-value continuation rules; on v81 a dealer's typed "WC8152" after a two-code offer was rewritten to
an offered code or lost its quantity (v72 kept "WC8152 x 5", 2 of 2). The rule now lives INSIDE the ideate
bullet's own line, short, and adds no line, so nothing new sits next to the continuation rules. The record-data
sentence is dropped: v72's own "NOT ideate: asking for existing data (stock, price, ETA, order status, a
document), which stays in its own domain" already says it.

1. In the `ideate / submit_idea` bullet,
   `a complaint about existing behaviour (stays portal_link/complaint);` becomes
   `a complaint about a product or an order (stays portal_link/complaint);`
2. In the same bullet line,
   `asking for a human (stays request_for_help).` becomes
   `asking for a human (stays request_for_help). ALSO ideate: the user reports a problem with the CRM system or the assistant itself (it errors, does not work or answers wrongly), or says they want to report one before saying what it is: an issue to log, no routing, never request_for_help or an IT or support team.`
3. In `== ROUTING ==`,
   `  - ideate (an idea is never escalated), or none of these this turn -> NO routing: null / null` becomes
   `  - ideate (an idea or an issue report is never escalated), or none of these this turn -> NO routing: null / null`

## Gate (crew, on the Mac: this sandbox has no funded LLM key and no prod-copy DB)

Console dry-run turns with the new version pinned (or after the owner promotes it), staff and dealer contacts:
an EN bug report, a Malay bug report with a typo, a greeting-prefixed report, a Chinese report, a feature
request (still ideate), a product complaint (still portal_link), "get me IT support" (still request_for_help),
a dealer disputing a record ("my order shows the wrong status", still order, not ideate), a stock figure
question (still inventory, not ideate), "I want to report a problem" (ideate, asks "What went wrong? ..."), the
first message of a new conversation (no "cleared" reply), and the frozen A-55 follow-ups (dealer "WC8152" after
a two-code offer, then "19": the typed code and its quantity kept, as on v72). Run x3 on the candidate vs v72.
