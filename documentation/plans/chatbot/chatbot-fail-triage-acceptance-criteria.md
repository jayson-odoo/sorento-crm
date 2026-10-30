# UAC: chatbot failure replies (CHATBOT-FAIL-TRIAGE)

Plan: `PLAN-chatbot-fail-triage-30oct.md`. Owner rule (30 Oct 2026, ~21:15): the bot must NEVER reply
"Sorry, I am busy right now..." or "Sorry, I ran into a problem understanding that...". Every failure
path gets an honest, specific reply instead. "Couldn't find X" is fine.

Gold cases come from the real failing turns in `sorento_prod_1028` (28 Sep - 28 Oct 2026); names and
phones are never copied into fixtures.

## Batch 1

### AC-1 No generic failure text on any path

For every path below, the contact's reply (all languages: EN, MS, ZH) never contains
`CHATBOT_TURN_ERROR_REPLY` (`chatbot_reply_copy.py:96-97`, MS "menghadapi masalah memahami", ZH
"暂时无法理解") or `RATE_LIMITED_REPLY` (`llm_call.py:39`), and the turn row keeps the real reason in
`chatbot.turns.error`.

| Path (emitter today) | Trigger | Reply instead |
|---|---|---|
| AC-1a parser failed (`engine.py:5348-5402`) | provider timeout, 429, 403, empty / non-JSON / non-object answer, no config, no key | H-AI: "I could not read your message just now because our AI service did not answer. Please send it again." |
| AC-1b low-signal clarifier failed (`engine.py:10153,10159`) | clarifier LLM raised or timed out | the canned offer already used when the clarifier has nothing (`chatbot_reply_copy.py` CHATBOT_REPLY_FALLBACK_*): "What can I check for you? Stock, incoming, delivery orders, promotions or product details." |
| AC-1c lane / fetch error (`engine.py:8556,8621`) | a lane raised after the parser read the message | H-FETCH with what was asked: "I could not fetch {label} for {codes} just now, please try again." (`compose.py` wording, already translated, `label_catalog.py:340`) |
| AC-1d escalation failed (`engine.py:10407-10475`) | next-assignee 404 (no team), SLA 400 (no policy), assignee not in team | H-ESC: "I could not pass this to the {team} team just now. Please contact them directly." |
| AC-1e any other exception (`engine.py:2534,3765`) | unhandled error at any stage | H-ERROR: "I hit an error while answering this and could not finish it. Please send it again." |
| AC-1f queue wait (`engine.py:3950`) | the contact's previous turn still running past the queue wait | H-QUEUE: "I was still answering your previous message, so I could not take this one. Please send it again." |
| AC-1g tail failed (`api/v1/external/chat.py:551,566`) | `/complete` raised after the answer was composed | the composed answer is sent; the failure is only logged. With no composed answer: H-ERROR. |
| AC-1h contact not found at `received` (`engine.py:3262,3272`) | first message arrives before the respond contact row commits | one re-read of the contact after a short wait; still missing: H-ERROR |

### AC-2 Honest outcome per fetch reason (C4, `turn/compose.py:662,689,715`)

| Reason (trace `error`) | Real example (backup) | Reply |
|---|---|---|
| AC-2a "the described set qualifies nothing" | "Sorento floor grating promotion" | "No current {label} found for {subject}." |
| AC-2b report HTTP 422 `subject_required` | "Total sale deliver for 1/10-9/10/26 Sorento brand" | ask for the missing subject: "Which customer or salesperson should I check the {label} for?" |
| AC-2c attachments on a held set over the attachment cap | "send me picture" after a 201-product list | ask which product: "Which product do you want the {label} for? Send me the code." |
| AC-2d MCP tool timed out (`chatbot_mcp_timeout_seconds`, `config.py:203`) | "CB2838 x10" stock | one retry of the same call; still failing: "I could not fetch {label} just now, please try again." |
| AC-2e report HTTP 403 `customer_not_permitted` | top-selling report | "That report is not available on your account." |

### AC-3 Price tag request portal link (C9)

A staff or dealer contact who asks for a link to request a price tag ("give me link to request
pricetag", "can i get portal link to request pricetag") gets a portal link that opens on the price tag
request form, never "Could not find portal link for attachment price tag template". Not prompt-only:
the chat portal tool accepts only complaint / stock_inquiry / purchase_request / sponsorship_form
(`schemas/ai_semantic_parser.py:38,131`, `mcp_tool_capability_service.py:1442`,
`portal_service.py:82,475-479`), while the price tag form has its own link builder
(`price_tag_notify.py:94-97`, `PortalService.submission_link(contact, "price_tag_request", ...)`).

### AC-4 Translations

Every new text has MS and ZH entries in `label_catalog.py`, and a test asserts the catalog covers it.

### AC-7 Escalation routes to a reachable team, never a default (owner, 30 Oct ~22:05)

Owner: "we shouldn't do no topic escalate to marketing product, we should clarify". No default team.
Evidence (17 failed escalations, backup 1028): 1 truly topic-less, 2 named team missed by the
parser, 2 topic in the message with parser routing null, 5 follow-ups whose topic was in earlier
turns, 3 unroutable agent+team pairs, 3 marketing_form SLA unbound (owner bound it in prod 30 Oct ~22:50, no code), 1 company uuid
sent as assignee.

- AC-7a agent + team are chosen as ONE pair from the topic's domain (the parser's R-X-08 map:
  order -> order_enquiries/customer_service, incoming -> incoming_stock_enquiries/purchasing,
  master_products -> general_enquiries/purchasing, inventory -> general_enquiries/warehouse,
  product_attachment -> general_enquiries/marketing_product, promotion ->
  general_enquiries/marketing_promotion, forms -> marketing_form/marketing_form), and a pair is
  offered only when it exists in `agent_teams` for the contact's company (Mocha:
  general_enquiries has purchasing_product, not purchasing; cover it).
- AC-7b the topic is carried from earlier turns: a follow-up ("Yes" to an offer, "9" picking from an
  order list, "Eta" after a PO line, "mocha mch" after a DO reply) routes by the held topic.
- AC-7c no topic this turn and none held: the bot asks one short clarifying question with the
  reachable topics as quick replies (orders & delivery, stock & ETA, product info, promotions,
  forms) and routes from the answer. Never DEFAULT_SUGGESTED_TEAM (`contracts.py:264`) and never a
  default agent (`contracts.py:282`) for the route.
- AC-7d failure text names the OFFERED team and is localized (H-ESC; review finding 6).
- AC-7e a company pick never becomes `preferred_assignee_id`: `turn/apply.py:393` takes a uuid
  only from an assignee option.
- AC-7f (prompt, md5 pin, owner publishes, eval gate) the parser fills a team the user names:
  "Please escalate to product marketing team" -> marketing_product; "escalate marketing" ->
  ambiguous marketing team -> AC-7c clarify among the marketing teams.

### Review round 1 findings (30 Oct, reviewer + security-reviewer on b5345cb5c6)

Blockers:
- R1 AC-3 never reaches WhatsApp: `lanes/business/fetch.py:1648-1656` `portal_submission_type`
  filters on SUPPORTED_TYPES; `PORTAL_LINK_COPY` (`fetch.py:1640`) lacks price_tag_request; the
  prompt addendum `alembic/data/chatbot_semantic_parser.portal-form.addendum.txt` lists four forms
  (prompt change: md5 pin + owner publish). The `schemas/ai_semantic_parser.py` change is the
  in-app assistant's schema, not the chatbot's. Needs a chatbot-path test.
- R2 AC-2c real case: the 201-product turn ran `crm_master_product_attachments_list` and answered
  with a withheld over-cap set; the reply comes from `turn/compose.py:760` (never-stuck arm). Word
  that arm ("which product?"), test with a 201-set fixture.
Should-fix:
- R3 AC-1b `engine.py:10178,10185`: language unset on failure, MS/ZH contacts get English; call
  `_fallback_language(...)` first.
- R4 AC-1f `engine.py:3971` `_worker_failed`: callers 3895/3901 (job returned no turn / crashed)
  must say H-ERROR; H-QUEUE only for the timeout at 3915.
- R5 retry `lanes/business/services.py:279,366-372`: skip for side-effecting tools on the
  read-only allowlist (`crm_low_stock_report` creates a run + workbook, `crm_portal_link_get`
  mints a token) and when the agent loop passes `timeout_seconds` (`agent/loop.py:1057`).
- R6 AC-1d `engine.py:10505`: pass `item=lane_item` so the reply localizes; prefer the offered team.
- R7 `lanes/casual.py:62`: setup failure still sends "Sorry, I can't reply to that right now"; H-AI.
Nits: `scripts/chatbot_load.py:231,546` counts by old text; `api/v1/external/chat.py:572-578`
drops `send_attachments` (reuse `_send_actions`); stale comments `llm_call.py:39`,
`casual.py:337`, `head/parser.py:61,87`; `compose.py:407` label stays English.

### Review round 2 findings (30 Oct, reviewer + security-reviewer on e84c0f3686)

Security: ready, three nits (folded in below). Reviewer: NOT READY.

Blockers:
- B1 `tests/chatbot/test_dev_failures_portal_form.py:52` still pins `price_tag_request` as no form
  (red on HEAD); it moves to the named forms (owner Q5, R1 code side).
- B2 a team the contact names is lost when it equals the team the routing chain filled
  (`escalation.py:1269`, `_team_is_explicit` `escalation.py:771`): "escalate to the customer
  service team" asks the topic instead of routing.
- B3 AC-4: the clarify question's topic names, the " or " joiner (`escalation.py:853`) and the
  quick replies stay English for MS / ZH contacts; the new texts need catalog coverage.
- B4 `exc.escalation_team` (`escalation.py:1564`) is not pinned by any test.

Should-fix:
- S1 + security nit: H-ESC names a team only when it is a topic-map team reachable for the
  company. A parser free-string team (`head/parser.py:421`), a team the company lacks, or the code
  default gets the neutral text "I could not pass this to our team just now. Please contact us
  directly." (MS / ZH in the catalog).
- S2 the routing-filled agent (can be the code default, `turn_runtime.py:1910`) never picks the
  pair ahead of the team's map agents (`escalation.py:820`).
- S3 a dry run (console) shows the same failure a live turn would (`escalation.py:1530`).
- S4 AC-7a "cover it": Mocha product info routes to general_enquiries / purchasing_product.
- S5 (lead decision, no change): the R2 ask keys on the product count. The only withholding is
  the over-cap rule (`lanes/business/fetch.py:3949`, `set_withheld`, never carried to compose),
  so count and reason select the same sets today; a second withholding reason pays for keying on it.
- AC-3 gating (security nit): a contact without the price tag form grant gets "That form is not
  available on your account." and no link (the portal tab would refuse it,
  `public/portal_price_tag.py:69-77`).
- Retry (security nit): `crm_sales_analysis` joins the never-retried tools.
- Nit: `sorento_crm_mcp/catalog.py:1250` portal tool description lists the price tag form.

Local note: an "out of shared memory" error under `-n 2` is the shared dev Postgres lock table
(`max_locks_per_transaction` 64) during blank-schema `create_all`, not a test defect.

## Batch 2 (after its own red tests; eval gate; prompt via md5 pin, owner publishes)

### AC-5 Dealer cost = dealer promotion (Q2)

A dealer contact (access type `*dealer`) asking "my cost", "dealer cost", "cost price" or "costing" for
a product gets the `promotion_products.dealer_cost` of the promotion(s) live today whose
`access_levels` include one of the contact's access types, within the contact's brand and company
scope. Staff (`*_office`) keep supplier purchase cost.

| Edge | Data (28 Oct) | Recommended reply |
|---|---|---|
| E1 product in no live promotion | SRTKS1248, SRTWC8036-SH-200, SRTWT5828 | "SRTKS1248 is not in a current dealer promotion, so I have no dealer cost for it. Please ask your salesman." |
| E2 several live promotions, different dealer costs | 239 of 1,106 products | one line per promotion: name, dealer cost, end date |
| E3 only expired promotions | CSS8811-GM, SRT1369-3-GY, SRTKS1035 | same as E1 (an expired cost is never shown) |
| E4 end user asks "my cost" | | list price answer (end users have no dealer cost) |
| E5 promotion not open to the contact's access types | | treated as E1 |

### AC-6 Code + size (Q4)

"SRTWC286 250MM", "SRTWC286200MM", "srtwc286-200mm": the parser emits the code head (SRTWC286) and the
size as a spec; the size is the trap length (`product_specifications`: SRTWC286-SH trap_length 250,
SRTWC286-SH-150 150, SRTWC286-SH-200 200), matched semantically per the 28 Oct "dimension = any" rule.
The reply answers the matching variant (SRTWC286-SH-200 for 200), never "Couldn't find".
