# Parser prompt change: a report of a CRM or assistant problem is ideate (WA-COMPLAINT-INTAKE)

- Why: crew pass CREW-PASSES-4 on df58e23d (14 Nov). The lane's rule lived only in
  `app/services/chatbot/head/parser_template.py`; production runs the stored `chatbot_semantic_parser`
  version 72, whose ideate bullet says "NOT ideate: ... a complaint about existing behaviour (stays
  portal_link/complaint)". A staff bug report went to `it_support` (access_denied) and a dealer bug report to
  a sales question.
- Base: production v72, md5 `d29c19830b22aa47403a88ddcb8e817d`, the exact file `prompt-prod-v72-d29c1983.txt`.
- Result: the exact file `prompt-wa-issue-ideate.txt`; its md5 is pinned in
  `tests/chatbot/test_wa_issue_parser_prompt.py`.
- Shipped by migration `wa_0002_parser_issue_ideate`: the SAME two edits (one function,
  `app/services/chatbot/head/issue_rule.py` `apply_issue_rule`) applied to the text of the version that holds
  the `production` label when the migration runs (so the rendered policy blocks stay as they are), published as
  the next `chatbot_semantic_parser` version, UNLABELLED. Idempotent; refuses (logs and publishes nothing) when
  an anchor is missing or the text already carries the rule. Only the owner moves the production label
  (Prompts page); rollback is the reverse move.
- Owner rule kept: slot rules only, no word lists, no gold-message examples.
- The shared phrase "a problem with the CRM system or the assistant itself" is in both this text and the code
  template's ideate line, so the two agree (pinned by the same test).

## Edits (apply by anchor, each anchor occurs exactly once in v72)

1. In the `ideate / submit_idea` bullet,
   `a complaint about existing behaviour (stays portal_link/complaint);` becomes
   `a complaint about a product or an order (stays portal_link/complaint);`
   and a new line is inserted directly after that bullet line:
   `    → ALSO ideate: the user REPORTS a problem with the CRM system or the assistant itself (an error, a screen or page that does not load, does not work or shows wrong data, an answer from the assistant that is wrong). That is an issue to log: domain_hint "ideate", intent_hint "submit_idea", message_type "business_query", no routing (null / null). It is never request_for_help, never an IT or support team, and never the domain of the screen or data it is about; only an explicit ask for a person to take it over is request_for_help.`
2. In `== ROUTING ==`,
   `  - ideate (an idea is never escalated), or none of these this turn -> NO routing: null / null` becomes
   `  - ideate (an idea or an issue report is never escalated), or none of these this turn -> NO routing: null / null`

## Gate (crew, on the Mac: this sandbox has no funded LLM key and no prod-copy DB)

Console dry-run turns with the new version pinned (or after the owner promotes it), staff and dealer contacts:
an EN bug report, a Malay bug report with a typo, a greeting-prefixed report, a Chinese report, a feature
request (still ideate), a product complaint (still portal_link), "get me IT support" (still request_for_help).
