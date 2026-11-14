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

Round 12 (crew LIVE pass CREW-PASSES-5 on v82 = cbc7364a, 14 Nov; owner ruling 14 Nov ~19:00): the owner's turn
"i want to report this is not the answer i want to the IT team" (and "i want to report to the IT team") came back
`request_for_help` / `it_admin` / `it_support` on v82 exactly as on v72, G05 "hi good morning, the sales order list
keeps loading and never opens" fell to the PIC escalation, G01 was 1 of 2. Cause: MESSAGE TYPE rule 1 (a named team
means request_for_help) and the "request_for_help outranks ..." line decide message_type BEFORE the model weighs the
ideate bullet, and nothing there says an issue report is exempt. Owner ruling: reporting a problem, even when the user
names "the IT team", files an issue; only a plain ask for IT support that reports nothing (G09 "get me IT support")
stays a help request. The fix is semantic, in place, no word list and no post-parse override:

- Edit 2's new text is widened (same anchor, same line): `... (it errors, keeps loading, does not work or answers
  wrongly, whatever screen or list it is on), or says they want to report one before saying what it is: an issue to
  log, no routing, never request_for_help or an IT or support team, also when the user names IT or a team to report
  it to.`
- Edit 4, MESSAGE TYPE rule 1 (line 157), appended in place after
  `Customer/company names (e.g. "today plumbing", "total home") are NOT departments and never trigger request_for_help.`:
  ` A report of a problem with the CRM system or the assistant is NOT request_for_help, even when it names IT, the IT
  team or a support team, or asks to report or send it to them: it is ideate (an issue to log, see the ideate
  bullet), message_type business_query, no routing. Only an ask to be put through to IT or a person that neither
  reports a problem nor says the user wants to report one stays request_for_help.`
- Edit 5 (line 164), appended in place after
  `"request_for_help" outranks business_query, clarification and casual, even when the message also mentions a product or order.`:
  ` It never outranks a report of a CRM system or assistant problem (rule 1).`
- Still no line added: the candidate keeps v72's 1037 lines (F3). The code template mirrors edit 4 in R-P3-04 rule 1
  and the widened ideate line; the rule-1 phrase "is NOT request_for_help, even when it names IT" is in both texts.
- The routing code needs no change: `turn/apply.py:1730` `_HELP_EXEMPT_DOMAINS` already sends a `request_for_help`
  verdict whose `domain_hint` is ideate to the ideate lane, never to escalation (pinned by a test this round).
- The gate turns are frozen in `sorento_crm_backend/tests/chatbot/fixtures/wa_issue_gate_turns.json` (owner turns,
  G01, G03, G05, G08, G09) and run live by `tests/chatbot/test_wa_issue_parser_gate_live.py` (opt-in,
  `CHATBOT_LIVE_LLM=1`, `WA_ISSUE_PROMPT_FILE` points it at a stored version's exported text).

Round 13 (crew LIVE x1 on v83 = 6caef14e, 14 Nov, crew-note 6877017702): the owner turns and the 16 gate turns
pass. Two misses and one possible regression:

- L2 "hi, the AI bot gave me the wrong stok number for my oder yesterday" went to the order lane. Cause: the
  DECISIVE signal-word rule (line 58) lets "stok" / "oder" set the domain, and nothing exempts a report that the
  assistant got it wrong. Edit 6, appended in place after
  `Only with NO decisive term AND a genuinely ambiguous domain → domain_hint and intent_hint null.`:
  ` One exception: when the user says the assistant (the bot, the AI, its answer) or a CRM screen got something
  wrong, a signal word only names what the problem was about and sets no domain; that report is ideate (see the
  ideate bullet). A user who questions or disputes a record's own figure or status, without blaming the assistant
  or a screen, keeps the domain.`
  Still no line added (1037 lines). GD2 "my order shows the wrong status" (order) and G10 (inventory) are the
  frozen guards that the exception stays narrow.
- L3 (Malay bug report) was filed with NO title. A title is always required (owner). Two fixes, both at the one
  shared place: the extractor schema's `title` description says it is never empty once there is a problem
  statement, whatever the language; and `ideation_capture_service.build_create_payload` (shared by the WhatsApp
  capture and the agent's `crm_idea_create`) falls back to the problem statement cut by `normalise_title` when the
  title is empty, so no item is ever filed untitled. The reply's title line uses the same value.
- A-222 "SRTWC 8366-S (300MM) picture" gave a 42-row list on v83 (1 of 1) where an earlier v72 run gave the
  did-you-mean. None of the round 12 edits touches attachments, product codes or lists. Crew runs A-222 x3 on v74
  AND v83 at the same head: if v74 also gives the list it is code-side (like A-55's lost quantity, which both
  prompts lose on this head), not this prompt.
- The frozen file gains L2 (ideate), L3 (ideate) and A-222 (product_attachment, the 8366 product as an entity).

- On a copy that already ran `wa_0001`/`wa_0002` on the old chain (before the 14 Nov re-parent onto
  `dbr_0001_retention_settings`), do NOT run `alembic downgrade -1 && alembic upgrade head`: that leaves
  `plr_0001` and `dbr_0001` unapplied. Either `alembic stamp agent_0001_proposal_insights && alembic upgrade head`
  (`wa_0001` is idempotent; `wa_0002` publishes the round 12 text unlabelled), or publish only the prompt with
  `documentation/plans/chatbot/sql/wa-issue-r12-publish.sql` (psql from the repo root; it checks both md5s and
  publishes once). Name the new version by its md5 `46e16236`, not by a number: version numbers are reused after a
  downgrade.

## Gate (crew, on the Mac: this sandbox has no funded LLM key and no prod-copy DB)

Console dry-run turns with the new version pinned (or after the owner promotes it), staff and dealer contacts:
an EN bug report, a Malay bug report with a typo, a greeting-prefixed report, a Chinese report, a feature
request (still ideate), a product complaint (still portal_link), "get me IT support" (still request_for_help),
a dealer disputing a record ("my order shows the wrong status", still order, not ideate), a stock figure
question (still inventory, not ideate), "I want to report a problem" (ideate, asks "What went wrong? ..."), the
first message of a new conversation (no "cleared" reply), and the frozen A-55 follow-ups (dealer "WC8152" after
a two-code offer, then "19": the typed code and its quantity kept, as on v72). Round 12 adds the owner turns and
G01/G05/G08 from the frozen file above. Run x3 on the candidate vs v72.
