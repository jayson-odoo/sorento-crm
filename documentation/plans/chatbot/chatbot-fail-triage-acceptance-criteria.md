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
