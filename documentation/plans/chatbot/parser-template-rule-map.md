# PARSER-TEMPLATE rule map (F1 input)

Status: map only, no template written. Lane CHAT-CODE-LOOKUP, plan `PLAN-parser-template-20oct.md`, arch review M1 / F1.
Read-only: no code edits, no LLM calls, no DB writes.

The lane head moved while this was mapped (7a0ec17eb7 -> 86d095400b: #1755 round 6 merged in, and the F1-A red tests
`tests/chatbot/test_parser_template.py` at 91b5c97c89). Code line numbers below are at 86d095400b. Rule ids follow
those tests: `R-<step>-NN` (R-P1-01, R-X-01), one id line per block, marker `== PARSER TEMPLATE ==`.

Inputs, measured on 20 Oct:

- v178: the lane template (v63 base, `{{specs}}` token, the R2-5 when-deliver insertion, CLOSED LISTS, CODE LOOKUP),
  1,884 lines, 137,132 chars (139,938 bytes). Cited as `vN` (line N of v178.txt).
- STATE: `STATE_SECTION` of `origin/crew/chat-state-r2` (#1772 head d45781dbf), 57 lines, 5,352 chars. Cited as `SN`
  (line N of the section; `chat_state_prompt.py` line = N + 6, so r2-D at S35 is `chat_state_prompt.py:41`).
  The lane's own copy of `chat_state_prompt.py` is older (no r2-D, no "(answered)"); F1 folds from #1772.
- v63 (production label) differs from v178 only by the inline spec lines (now `{{specs}}`), the R2-5 insertion
  (v647-649) and the two appended sections (v1804-1884).
- Rendered on top of the raw text at each turn: `{{specs}}` 10,246 chars, `{{find_filters}}` 4,458 chars (FIND_RULE
  plus filter lines), `{{attachment_types}}` and `{{certification_types}}` (DB rows, not measured here).

Totals: 176 blocks, 142,484 chars. Verdicts: KEEP 43, MERGE 119, DELETE 14.
Absolute words in v178 + STATE: never/NEVER 175, always/ALWAYS 26, ONLY 38, overrides/OVERRIDING/OUTRANKS 7,
DECISIVE 7, MUST 2.

## 0. Target rule ids (the procedure)

The template is read in this order; a later step never re-decides an earlier step's field. An exception is written
only as "see <id>". One rule owns each schema field (the lint's field index). The name after each id is its block
title; ids are numbered in procedure order. Elsewhere in this map an id appears as `R-P1-02 (CARRY)`.

| step | id | owns | one line |
|---|---|---|---|
| P1 | R-P1-01 STATE | state_changes (shape, ops table) | what the State block holds; ops carry no values, the fields do |
| P1 | R-P1-02 CARRY | set / keep ops; held domain on a value-only message | a message naming only values continues the held ask; title keeps the words "BARE ENTITY CONTINUATION" (section 5) |
| P1 | R-P1-03 DOM-QTY | domain of a quantity-only ask (R-DOM-QTY, approved) | a stated quantity continues the last answer's domain when it takes a quantity (stock, incoming, order), else stock |
| P1 | R-P1-04 SWITCH | switch_domain, new_subject | an own ask word on the held subject switches; an own subject and measure is a new subject |
| P1 | R-P1-05 PICK | pick ops (mirrored to reference_positions, open_question_answer.picked) | a number, ordinal or listed name points at an option or a last-list row |
| P1 | R-P1-06 ANSWER | answer op; open_question_answer value (mode, items, qty_for_all); is_affirmative | the value an answer carries, per open question kind |
| P1 | R-P1-07 CLOSE | close_question | when an owed question is left unanswered |
| P1 | R-P1-08 ESC | escalation.is_escalation_confirmation, company_pick | a hand-over offer is answered only by a reply that is the answer |
| P1 | R-P1-09 SLOTS | keep / skip / clear / unclear on customer and period | held customer and period |
| P1 | R-P1-10 UNSURE | [] and small talk | when the relation cannot be told |
| P2 | R-P2-01 ENT | entities[], hint, current_message | only what THIS message names; hint table |
| P2 | R-P2-02 CAND | canonical_code, spec_key, spec_value from the candidates block | pick a listed candidate or none; near / set codes |
| P2 | R-P2-03 SHAPE | hint by token shape | product code, order number, container, warehouse token, customer name |
| P2 | R-P2-04 CONF | confident | one referent or a mash |
| P2 | R-P2-05 QTY | entities[].quantity, demand_qty | the count beside a product, or one count for the turn |
| P2 | R-P2-06 FILE | attachment_type entities, listed_item | one entity per listed file type / cert kind / listed scheme |
| P2 | R-P2-07 RESOURCE | attachment entity canonical class | catalogue, warranty, price tag template, brand guarantee, container status |
| P2 | R-P2-08 SPEC | specification entities | a property the product is described by |
| P2 | R-P2-09 BRAND | brand entities | the Known brands line only |
| P2 | R-P2-10 PARTIES | sales_agent / customer / category in a ranking | who sold, who bought, what kind |
| P2 | R-P2-11 PERSON | person_mention | a person named |
| P2 | R-P2-12 ACCESS | access_levels | a tier selected in this message |
| P2 | R-P2-13 PRONOUN | anaphora.backward_reference | a pointer is never an entity; the held subject as a whole is `keep` |
| P3 | R-P3-01 DOM | domain_hint, intent_hint | the meaning of this message's ask words (one table, no word lists) |
| P3 | R-P3-02 PRICE | list / promo / purchase cost | what the product costs to buy, under an offer, or what we paid |
| P3 | R-P3-03 DIM | domain_in_message | does this message name what kind of fact it asks |
| P3 | R-P3-04 MSGTYPE | message_type | request_for_help, business_query, clarification, casual |
| P3 | R-P3-05 ATTR | requested_attributes | what is asked about, nothing else |
| P3 | R-P3-06 STATUS | order_status, status | orders not yet delivered (incl. when-deliver), bucket by paper |
| P3 | R-P3-07 PAPER | document | the paper words |
| P3 | R-P3-08 ACTIVE | is_active | lifecycle words |
| P3 | R-P3-09 BROADEN | scope_intent, broaden_axis, broaden_to | widening one axis or all |
| P3 | R-P3-10 ASKS | asks | two or more domains in this message |
| P3 | R-P3-11 LOWSTOCK | low_stock.* | the low stock report's filters |
| P3 | R-P3-12 RPT | sales_report / sales_analysis / sales_ranking / top_selling keys | which order report and its keys |
| P3 | R-P3-13 GROUPBY | group_by | the axis the answer is broken down by |
| P3 | R-P3-14 TOPN | top_n | rows asked for |
| P3 | R-P3-15 FLYER, R-P3-16 SELF, R-P3-17 CORR, R-P3-18 MATCH | contains_flyer, self_reference, correction, match_mode | one line each |
| X | R-X-01 FRAME, R-X-02 DATE, R-X-03 THIS-MESSAGE, R-X-04 MEANING | inputs; dates; "fields hold THIS message only"; "read words for meaning, misspelt or not" | stated once, replacing about 14 "never carry over" and 3 "read for meaning" copies |
| X | R-X-05 MIRROR | entity_op, topic_reset, ranking_refine, reference_positions, open_question_answer.mode | filled from the ops by a fixed table while blocker B1 stands (section 2, C4) |
| X | R-X-06 OUT, R-X-07 GOAL, R-X-08 ROUTING, R-X-09 POLICY | key index with values; user_goal; routing; policy block | the OUTPUT block and every "IN ADDITION" header become one key index |

## 1. Rule table (v178 + STATE)

Columns: `lines` vN = v178.txt, SN = STATE section. `chars` includes newlines. `abs`: A always, N never, O ONLY
(upper case only; lower-case "only" is ordinary prose), V overrides / OVERRIDING / OUTRANKS, M MUST, D DECISIVE.
`rule id` is the target the block's decision lives in; for DELETE it is `none` and the reason names the successor.
KEEP marks the block that is the home text of its id (compressed to the budget in section 4).

| # | lines | block | rule id | chars | decides (schema fields) | abs | verdict |
|---|---|---|---|---|---|---|---|
| 1 | v1-9 | Preamble: inputs, one JSON, read in context | R-X-01 | 495 | all; entities[].raw | A1 | MERGE INTO R-X-01: previous_conversation_state (v3) is not sent by code; "always interpret in context" is P1's job |
| 2 | v10-17 | CURRENT DATE | R-X-02 | 262 | date_filter_* | - | KEEP: drop "before calling the MCP tool" |
| 3 | v18-22 | PRICE TERMINOLOGY | R-P3-02 | 710 | domain_hint, intent_hint | V1 D1 | MERGE INTO R-P3-02: duplicate of v116-123 and v1002-1005 |
| 4 | v23-26 | AFFIRMATION | R-P1-06 | 267 | is_affirmative | - | MERGE INTO R-P1-06: yes/no is the value of an `answer` |
| 5 | v27-32 | ESCALATE-WORD | R-P1-08 | 537 | is_affirmative, message_type | - | MERGE INTO R-P1-08: 9-item word list; meaning: the offer's own verb is a yes |
| 6 | v33-41 | READING IN CONTEXT: (A) asked / (B) delivered | none | 461 | (relation) | A1 | DELETE: superseded by state_changes under the state gate (open question is a State line) |
| 7 | v42-45 | Current subject line is context only | none | 309 | entities | N1 | DELETE: the line is not printed under the gate (context.py _assemble_off / _render_l2); R-P2-01 says THIS message only |
| 8 | v46-52 | Domain-only message switches, value refines | R-P1-04 | 514 | domain_hint, entities, entity_op | O1 | MERGE INTO R-P1-04: = switch_domain / set |
| 9 | v53-59 | Subject domains are the weakest signal; oustaning example | R-P3-01 | 488 | domain_hint | A1 N1 | MERGE INTO R-P3-01: example duplicates v675 |
| 10 | v60-61 | SO / DO word alone fills document | R-P3-07 | 178 | document | - | MERGE INTO R-P3-07: duplicate of v717-722 |
| 11 | v62-66 | Number words are positions | R-P1-05 | 249 | reference_positions | - | MERGE INTO R-P1-05: 9-item word list; meaning: a number in any language or written as a word is a number |
| 12 | v67-84 | INTENT & DOMAIN list | R-X-06 | 860 | intent_hint, domain_hint | - | MERGE INTO R-X-06: the domain list misses purchase_order (v922), the intents miss check_po and low_stock_report; render from the registry (C11) |
| 13 | v85-103 | DOMAIN IN MESSAGE | R-P3-03 | 1313 | domain_in_message | N1 | KEEP: keep 3 of 9 examples; 20-word list becomes "a word naming what kind of fact is asked" |
| 14 | v104-115 | DECISIVE DOMAIN TERMS preamble | R-P3-01 | 802 | domain_hint, intent_hint | V1 D2 | MERGE INTO R-P3-01: DECISIVE/OVERRIDING x5; one sentence in R-P3-01; carried product on a switch is P1 |
| 15 | v116-120 | master_products terms | R-P3-01 | 398 | domain_hint | - | MERGE INTO R-P3-01: 15-word list -> meaning row |
| 16 | v121-125 | promotion terms | R-P3-02 | 310 | domain_hint | N2 | MERGE INTO R-P3-02: 9-word list -> meaning row |
| 17 | v126-128 | product_attachment terms | R-P3-01 | 216 | domain_hint | - | MERGE INTO R-P3-01: 10-word list -> meaning row |
| 18 | v129-141 | resource_attachment + container status | R-P3-01 | 1278 | domain_hint, requested_attributes | N1 D1 | MERGE INTO R-P3-01: 12-word list; container-status-of-a-shipment -> R-P3-05 __all__ |
| 19 | v142-143 | inventory terms | R-P3-01 | 101 | domain_hint | - | MERGE INTO R-P3-01 |
| 20 | v144-162 | order terms + have-take / have-sales | R-P3-01 | 1607 | domain_hint, order_status, entities, requested_attributes | N3 D1 | MERGE INTO R-P3-01: meaning row: goods going out to a customer, or what a customer took |
| 21 | v163-176 | incoming terms + clearance checkpoints | R-P3-01 | 1020 | domain_hint | D1 | MERGE INTO R-P3-01: 23-word checkpoint list -> meaning row; container token shape -> R-P2-03 |
| 22 | v177-184 | forms / portal / GR / SPO terms | R-P3-01 | 287 | domain_hint | - | MERGE INTO R-P3-01 |
| 23 | v185-195 | ideate terms | R-P3-01 | 738 | domain_hint, message_type | - | MERGE INTO R-P3-01 |
| 24 | v196-198 | No decisive term: keep previous domain | R-P1-02 | 155 | domain_hint | - | MERGE INTO R-P1-02: = keep |
| 25 | v199-208 | BARE ENTITY CONTINUATION: same question, new value | R-P1-02 | 762 | domain_hint, intent_hint, message_type, entity_op, entities | A1 N1 O1 | MERGE INTO R-P1-02: ALWAYS/NEVER; = set <axis>, domain stays; the words stay in R-P1-02's title for FIND_RULE (section 5.4) |
| 26 | v209-213 | BEC: no previous domain / a decisive term wins | R-P1-02 | 375 | domain_hint | N1 | MERGE INTO R-P1-02: restates R-P3-01 |
| 27 | v214-221 | BEC: not for a pick; an unoffered value re-scopes | R-P1-05 | 559 | reference_positions, entities | N1 | MERGE INTO R-P1-05 |
| 28 | v222-234 | IDEATION CONTINUATION | R-P1-06 | 904 | domain_hint, intent_hint, message_type | D1 | MERGE INTO R-P1-06: a reply to the bot's own question is an `answer` |
| 29 | v235-240 | Standalone DO is a delivery order view | R-P3-07 | 417 | domain_hint, entity_op | - | MERGE INTO R-P3-07: entity_op reuse -> P1 keep |
| 30 | v241-248 | REQUESTED ATTRIBUTES: closed vocabulary + whole phrase | R-P3-05 | 732 | requested_attributes | N3 O2 | KEEP: closed-vocabulary sentence (v246-247) DELETED: conflicts with v244 and v1860-1863 |
| 31 | v249-252 | master_products vocabulary (price, dimension, discontinued) | none | 158 | requested_attributes | - | DELETE: superseded: the engine matches any word by token containment (fetch.py:1997-2006) |
| 32 | v253-262 | order vocabulary (delivery, items, quantity) | R-P3-05 | 733 | requested_attributes | - | MERGE INTO R-P3-05: keep as a 3-row key table |
| 33 | v263-290 | incoming CRM keys + worked examples | R-P3-05 | 2565 | requested_attributes | - | MERGE INTO R-P3-05: keys are a value vocabulary code reads: keep the 20 keys, one meaning each, 2 examples |
| 34 | v291-299 | FULL TIMELINE __all__ | R-P3-05 | 746 | requested_attributes | - | MERGE INTO R-P3-05 |
| 35 | v300-301 | Other domains: [] | R-P3-05 | 89 | requested_attributes | - | MERGE INTO R-P3-05 |
| 36 | v302-311 | SCOPE INTENT | R-P3-09 | 578 | scope_intent | - | MERGE INTO R-P3-09: three fields for one decision (scope_intent, broaden_axis all, entity_op clear) |
| 37 | v312-320 | MESSAGE TYPE: order of tests | R-P3-04 | 2184 | message_type | A1 N2 O1 M1 | KEEP |
| 38 | v321-322 | clarification is the agent's doubt | R-P3-04 | 433 | message_type | - | MERGE INTO R-P3-04 |
| 39 | v323-326 | request_for_help is only a human + delivery word plus a name | R-P3-04 | 856 | message_type, domain_hint, entities, is_escalation_confirmation | O1 | MERGE INTO R-P3-04: third copy (v316, v982-983) |
| 40 | v327-329 | USER GOAL | R-X-07 | 331 | user_goal | A3 | KEEP |
| 41 | v330-342 | ATTACHMENT TYPE EXTRACTION (canonical taxonomy) | none | 1027 | entities[attachment_type].canonical_code | A1 N1 | DELETE: superseded by R-P2-06 listed_item; 10-word photo list -> meaning |
| 42 | v343-349 | FLYER FLAG | R-P3-15 | 338 | contains_flyer, domain_hint | - | KEEP: v347-348 garbled; merge with the promotion row |
| 43 | v350-371 | ACCESS LEVELS | R-P2-12 | 1426 | access_levels | N2 O2 | KEEP: literal list -> {{access_levels}} (drift pattern access_levels) |
| 44 | v372-381 | ENTITY OPERATIONS: hint table | R-P2-01 | 744 | entities[].hint | N1 | KEEP |
| 45 | v382-390 | attachment (document class) entity | R-P2-07 | 779 | entities[attachment].canonical_code | A2 N1 O1 | KEEP |
| 46 | v391 | attachment_type canonical + cert-scheme EXCEPTION | none | 697 | entities[attachment_type].canonical_code | A1 | DELETE: conflict: EXCEPTION (one entity, canonical null) vs CLOSED LISTS v1826-1829 (scheme = second entity) |
| 47 | v392-395 | form / inbound_shipment / warehouse hints | R-P2-01 | 184 | entities[].hint | - | MERGE INTO R-P2-01 |
| 48 | v396-401 | Extract when unsure; a filter value is an entity | R-P2-01 | 306 | entities | N1 | MERGE INTO R-P2-01 |
| 49 | v402-403 | Entity JSON shape | none | 682 | entities[] | - | DELETE: strict schema enforces shape; its attachment_type list omits video (vs v341) |
| 50 | v404-409 | Grammar particles never an entity | R-P2-01 | 400 | entities | A1 N3 | MERGE INTO R-P2-01: 10-word particle list -> meaning: a word with no referent |
| 51 | v410-418 | Bare family code is always a product | R-P2-03 | 640 | entities[].hint, entity_op | A1 N3 | MERGE INTO R-P2-03: entity_op part -> R-X-05 |
| 52 | v419-424 | PRONOUN REFERENCE | R-P2-13 | 1020 | anaphora.backward_reference, entities | N4 | KEEP |
| 53 | v425-445 | ENTITY CONFIDENCE | R-P2-04 | 1526 | entities[].confident | O1 | KEEP: keep 1 example |
| 54 | v446-456 | entity_op semantics | none | 1849 | entity_op | - | DELETE: continuation channel; under the gate filled by R-X-05 (blocked, section 2 C4) |
| 55 | v457-459 | MATCH MODE | R-P3-18 | 145 | match_mode | - | KEEP |
| 56 | v460-480 | BROADEN AXIS: broaden_axis | R-P3-09 | 1485 | broaden_axis | A1 N2 | KEEP |
| 57 | v481-493 | broaden_to | R-P3-09 | 908 | broaden_to | - | MERGE INTO R-P3-09 |
| 58 | v494-503 | broaden worked examples | R-P3-09 | 634 | broaden_*, entity_op | - | MERGE INTO R-P3-09: keep 2 |
| 59 | v504-514 | Broaden keeps the domain; no domain -> catalogue | R-P3-09 | 815 | domain_hint, scope_intent, entity_op | - | MERGE INTO R-P3-09: entity_op reuse -> R-X-05 |
| 60 | v515-517 | DEMAND QTY | R-P2-05 | 78 | demand_qty | - | MERGE INTO R-P2-05 |
| 61 | v518-520 | CORRECTION / DOUBT | R-P3-17 | 116 | correction | - | KEEP |
| 62 | v521-544 | ROUTING | R-X-08 | 1945 | routing.suggested_team, routing.suggested_agent | A1 N1 O1 | KEEP: team map duplicates the policy block's "Escalates to"; conflict on certificate (v535 vs v1771) |
| 63 | v545-562 | DATE FILTER | R-X-02 | 1465 | date_filter_start, date_filter_end | A1 N2 O1 M1 | MERGE INTO R-X-02: NEVER carry -> R-X-03 |
| 64 | v563-570 | date_mode | R-X-02 | 913 | date_mode | N1 O2 | MERGE INTO R-X-02 |
| 65 | v571-582 | POSITIONAL REFERENCES | R-P1-05 | 895 | reference_positions | O1 | MERGE INTO R-P1-05 |
| 66 | v583-586 | Bare number <= count is a position | R-P1-05 | 782 | reference_positions | N2 O1 | MERGE INTO R-P1-05 |
| 67 | v587-592 | REFERENCE TARGET | none | 717 | reference_target | - | DELETE: dead trigger: no code emits "[<N> did-you-mean suggestions active]"; field stays null via R-X-06 |
| 68 | v593-605 | PERSON-NAME MENTION | R-P2-11 | 1010 | person_mention | A1 N2 | KEEP: 10-honorific list -> meaning |
| 69 | v606-626 | COMPANY-NAME REPLY ON AN ESCALATION OFFER | R-P1-08 | 2049 | escalation.company_pick, is_escalation_confirmation | N2 | MERGE INTO R-P1-08: "whatever the message_type" line OUTRANKED by v1735 |
| 70 | v627-639 | A value is not a fragment / casual fragment | R-P1-08 | 1169 | entities, message_type, is_affirmative | N1 | MERGE INTO R-P1-08: value = set / close_question |
| 71 | v640-646 | ORDER_STATUS: outstanding words | R-P3-06 | 449 | order_status | N1 O2 | MERGE INTO R-P3-06: 10-word list -> meaning (section 3) |
| 72 | v647-649 | R2-5 when-deliver insertion (publisher) | R-P3-06 | 244 | order_status | - | MERGE INTO R-P3-06: word list; delete the OUTSTANDING_ANCHOR insertion (scripts/publish_code_lookup_prompt.py:22-59) |
| 73 | v650-653 | delivered / null / never infer | R-P3-06 | 274 | order_status | N1 | MERGE INTO R-P3-06: never infer -> R-X-03 |
| 74 | v654-666 | A status value means the order domain | R-P3-06 | 1088 | domain_hint, status, order_status | N1 | KEEP: SPO -> incoming (v659) conflicts with spo_allocation (v183, v942, v1780) |
| 75 | v667-681 | READ FOR MEANING, NOT SPELLING | R-X-04 | 1084 | order_status, requested_attributes | N1 | MERGE INTO R-X-04: stated once for every field |
| 76 | v682-694 | IS_ACTIVE FILTER | R-P3-08 | 844 | is_active | N1 O1 | KEEP |
| 77 | v695-716 | DOCUMENT | R-P3-07 | 1526 | document | N1 | KEEP |
| 78 | v717-724 | Paper word alone; "both" over an offer | R-P3-07 | 647 | document, message_type, reference_positions | N2 O1 | MERGE INTO R-P3-07: "both" not a position -> R-P1-05 |
| 79 | v725-740 | ASKS | R-P3-10 | 1437 | asks | N2 | KEEP |
| 80 | v741-747 | TOPIC RESET | none | 376 | topic_reset | N1 | DELETE: = new_subject; filled by R-X-05 |
| 81 | v748-788 | OUTPUT block | R-X-06 | 2647 | all | O2 | MERGE INTO R-X-06: invalid JSON (v768, v781-784); strict schema already enforces keys |
| 82 | v789-798 | TWO MORE OUTPUT KEYS header | R-X-06 | 371 | group_by, top_n | - | MERGE INTO R-X-06 |
| 83 | v799-809 | GROUP_BY | R-P3-13 | 697 | group_by | N1 | KEEP: one table for every report |
| 84 | v810-817 | TOP_N | R-P3-14 | 236 | top_n | N1 | KEEP |
| 85 | v818-827 | ORDER_STATUS gains so_outstanding | R-P3-06 | 871 | order_status | N1 | MERGE INTO R-P3-06: bucket = outstanding word x paper word (table) |
| 86 | v828-853 | ORDER_STATUS gains do_outstanding / outstanding_both | R-P3-06 | 1768 | order_status | N4 | MERGE INTO R-P3-06: document-anywhere text duplicates v707-716 |
| 87 | v854-873 | OPEN NUMBERED QUESTION -> reference_positions | R-P1-05 | 1428 | reference_positions, domain fields | - | MERGE INTO R-P1-05: "Open question options:" is not printed under the gate |
| 88 | v874-887 | Paraphrase is an answer; ALL is every number | R-P1-05 | 1009 | reference_positions | - | MERGE INTO R-P1-05 |
| 89 | v888-904 | A new ask is not an answer; a listed code is its position | R-P1-05 | 1175 | reference_positions, entities | N1 | MERGE INTO R-P1-05: internal conflict: v894-899 (position AND entity) vs v903 (never both) |
| 90 | v905-921 | SHORT TOKEN IS A LOCATION | R-P2-03 | 1155 | entities[].hint | N2 | KEEP: token shapes |
| 91 | v922-938 | PURCHASE ORDERS | R-P3-01 | 1081 | domain_hint, intent_hint, asks | N5 | MERGE INTO R-P3-01 |
| 92 | v939-948 | SPO LAST RECEIPT | R-P3-01 | 501 | domain_hint, intent_hint, top_n | - | MERGE INTO R-P3-01 |
| 93 | v949-960 | A BARE SPEC ASKS FOR ALL | R-P3-05 | 836 | requested_attributes | A1 | MERGE INTO R-P3-05: example "steel_grade" (a key) vs v244 whole phrase |
| 94 | v961-969 | IN A PO ASK THE CODE IS THE PRODUCT | R-P2-03 | 582 | entities[].hint | N1 | MERGE INTO R-P2-03 |
| 95 | v970-981 | A NEW QUESTION IS NEVER A YES | R-P1-08 | 757 | is_escalation_confirmation | N1 | MERGE INTO R-P1-08: duplicate of v1723-1730 |
| 96 | v982-984 | A DELIVERY WORD PLUS A NAME IS AN ORDER ASK | none | 418 | message_type | O1 | DELETE: verbatim duplicate of v323 |
| 97 | v985-988 | THE ATTRIBUTE PHRASE, WHOLE | none | 316 | requested_attributes | N2 O1 | DELETE: verbatim duplicate of v244 |
| 98 | v989-1009 | LAST PURCHASE COST | R-P3-02 | 1188 | domain_hint, intent_hint, top_n, group_by | N3 | MERGE INTO R-P3-02: 11-word list -> meaning |
| 99 | v1010-1050 | LOW STOCK REPORT FILTERS | R-P3-11 | 2774 | low_stock.* | N5 O1 | KEEP: translations -> meaning |
| 100 | v1051-1056 | Refining the low stock report just shown | R-P1-02 | 477 | intent_hint, domain_in_message, low_stock | - | MERGE INTO R-P1-02: = set on the held report |
| 101 | v1057-1065 | Answering the bot's low stock question | R-P1-06 | 694 | open_question_answer, topic_reset | N1 | MERGE INTO R-P1-06 |
| 102 | v1066-1096 | SALES RANKING: definition, business model, ranked noun | R-P3-12 | 2836 | order_status, group_by, top_n, measure, basis, sales_channel, entities | A1 N6 | KEEP |
| 103 | v1097-1124 | Follow-up to a sales ranking (refine) | R-P1-02 | 2417 | ranking_refine, top_n, basis, measure, sales_channel | A1 N5 O2 | MERGE INTO R-P1-02: ranking_refine = a set on a held ranking (R-X-05) |
| 104 | v1125-1134 | NOT a sales ranking | R-P3-12 | 500 | order_status | - | MERGE INTO R-P3-12 |
| 105 | v1135-1143 | SALES REPORT header | R-X-06 | 256 | sales_channel | - | MERGE INTO R-X-06 |
| 106 | v1144-1169 | SALES REPORT | R-P3-12 | 1776 | order_status, domain_hint, requested_attributes | A1 N2 O2 | MERGE INTO R-P3-12: 8-word list -> meaning |
| 107 | v1170-1197 | SALES_CHANNEL + code-shape after a channel word | R-P3-12 | 2053 | sales_channel, entities[].hint | A1 N7 O1 | MERGE INTO R-P3-12: "ONLY when sales_report" conflicts with v1093, v1108, v1385; code shape -> R-P2-03 |
| 108 | v1198-1214 | A BARE MONTH NAME IS STILL A DATE FILTER | R-X-02 | 1150 | date_filter_* | N1 | MERGE INTO R-X-02: restates DATE FILTER |
| 109 | v1215-1243 | A NARROWING REPLY UNDER AN OPEN REPORT OFFER | R-P1-02 | 1796 | domain_hint, order_status, entities | N2 | MERGE INTO R-P1-02: conflict C5: domain_hint null here vs carried (v204) vs answered domain (S35) |
| 110 | v1244-1253 | OPEN TASK header | R-X-06 | 370 | proceed_anyway, entities[].quantity | - | MERGE INTO R-X-06 |
| 111 | v1254-1266 | entities[].quantity per product | R-P2-05 | 809 | entities[].quantity, demand_qty | A1 | MERGE INTO R-P2-05 |
| 112 | v1267-1287 | AN OPEN TASK IS A FACT | R-P1-06 | 1373 | entities[].quantity, entity_op, proceed_anyway, topic_reset | N3 | MERGE INTO R-P1-06: "Open task:" line not printed under the gate (State pending task) |
| 113 | v1288-1304 | A LINE BEGINNING "Last answered:" | none | 1121 | demand_qty, correction, domain_hint | N2 | DELETE: line not printed under the gate; replaced by set quantity + R-P1-03 |
| 114 | v1305-1321 | OPEN QUESTION object + open_question_answer | R-P1-06 | 1215 | open_question_answer | - | MERGE INTO R-P1-06: value channel of `answer` (chat_state.py apply_changes reads mode) |
| 115 | v1322-1333 | PICKING and CONFIRM words | R-P1-05 | 903 | open_question_answer.picked/mode | - | MERGE INTO R-P1-05: word lists -> meaning |
| 116 | v1334-1357 | QUANTITIES and LAST_ANSWER modes | R-P1-06 | 1590 | open_question_answer.mode/items/qty_for_all, demand_qty | N1 | KEEP: value shapes of the stock question |
| 117 | v1358-1369 | SALES ANALYSIS header | R-X-06 | 348 | sales_basis, sales_company, group_by | - | MERGE INTO R-X-06 |
| 118 | v1370-1387 | SALES ANALYSIS | R-P3-12 | 1153 | order_status, sales_channel, group_by, entities | A1 N1 | MERGE INTO R-P3-12: 9-word list -> meaning |
| 119 | v1388-1393 | DATES ON A SALES ANALYSIS | R-X-02 | 378 | date_filter_* | - | MERGE INTO R-X-02 |
| 120 | v1394-1399 | SALES_BASIS | R-P3-12 | 394 | sales_basis | - | MERGE INTO R-P3-12 |
| 121 | v1400-1404 | SALES_COMPANY | R-P3-12 | 214 | sales_company | N1 | MERGE INTO R-P3-12 |
| 122 | v1405-1415 | SPECIFICATIONS header | R-X-06 | 490 | entities[].spec_key, spec_value | - | MERGE INTO R-X-06 |
| 123 | v1416-1438 | THE specification ENTITY | R-P2-08 | 1848 | entities[specification] | N5 O2 | KEEP |
| 124 | v1439-1441 | A domain word alone after an answer keeps the subject | R-P1-04 | 243 | entities, entity_op | - | MERGE INTO R-P1-04: = switch_domain |
| 125 | v1442-1444 | attachment_type is only a kind of document | R-P2-06 | 271 | entities[].hint | N1 O1 | MERGE INTO R-P2-06 |
| 126 | v1445-1456 | spec examples | R-P2-08 | 597 | entities[specification] | - | MERGE INTO R-P2-08: keep 2 |
| 127 | v1457-1465 | QUANTITY header | R-X-06 | 243 | entities[].quantity | - | MERGE INTO R-X-06: second declaration of the same key (v1249-1252) |
| 128 | v1466-1483 | QUANTITY: a count beside a code | R-P2-05 | 1063 | entities[].quantity, raw | N5 O1 | MERGE INTO R-P2-05 |
| 129 | v1484-1505 | KNOWN BRANDS | R-P2-09 | 1212 | entities[brand] | N5 O1 | KEEP |
| 130 | v1506-1517 | TOP SELLING header | R-X-06 | 389 | rank_by, basis, rank_group, rank_direction | - | MERGE INTO R-X-06 |
| 131 | v1518-1535 | TOP SELLING definition + word list | R-P3-12 | 1203 | order_status, top_n | N2 | MERGE INTO R-P3-12: 20-word list -> meaning |
| 132 | v1536-1539 | TOP_N on a top selling ask | R-P3-14 | 198 | top_n | N1 | MERGE INTO R-P3-14 |
| 133 | v1540-1546 | RANK_BY | R-P3-12 | 327 | rank_by | N1 | MERGE INTO R-P3-12: same concept as measure (v1094): two fields |
| 134 | v1547-1552 | BASIS | R-P3-12 | 306 | basis | - | MERGE INTO R-P3-12 |
| 135 | v1553-1563 | RANK_GROUP | R-P3-12 | 642 | rank_group, entities | - | MERGE INTO R-P3-12 |
| 136 | v1564-1586 | ANSWERING THE BOT'S TOP SELLING QUESTION | R-P1-06 | 1646 | rank_by, rank_group, basis, top_n | N6 O1 | MERGE INTO R-P1-06 |
| 137 | v1587-1594 | Bare number after a ranked list; a year is a period | R-P1-05 | 561 | reference_positions, date_filter_* | N2 O1 | MERGE INTO R-P1-05 |
| 138 | v1595-1604 | ANSWERING "CUSTOMER OR SALES AGENT?" | R-P1-05 | 700 | reference_positions | N4 | MERGE INTO R-P1-05 |
| 139 | v1605-1615 | RANK_DIRECTION | R-P3-12 | 724 | rank_direction, top_n | N2 | MERGE INTO R-P3-12: 8-word list -> meaning |
| 140 | v1616-1636 | NARROWING A TOP SELLING ASK | R-P1-02 | 1546 | entities[].hint, domain_in_message | N4 | MERGE INTO R-P1-02: who-sold / category / brand / customer hints -> R-P2-10 |
| 141 | v1637-1656 | Correction / broaden / name next to agent / split phrase | R-P2-10 | 1429 | correction, broaden_*, entities | N4 | MERGE INTO R-P2-10 |
| 142 | v1657-1668 | FROM A RANKING TO ANOTHER ORDER REPORT | R-P1-04 | 753 | domain_hint, order_status, document | N3 | MERGE INTO R-P1-04 |
| 143 | v1669-1677 | SELF REFERENCE header | R-X-06 | 248 | self_reference | - | MERGE INTO R-X-06 |
| 144 | v1678-1692 | SELF_REFERENCE | R-P3-16 | 1029 | self_reference | N1 | KEEP: 12-word list -> meaning |
| 145 | v1693-1711 | ESCALATION CONFIRMATION: verdict + offer shapes | R-P1-08 | 996 | escalation.is_escalation_confirmation | N1 V1 | KEEP: OUTRANKS every earlier line |
| 146 | v1712-1734 | TRUE / FALSE cases | R-P1-08 | 1734 | escalation.is_escalation_confirmation | - | MERGE INTO R-P1-08 |
| 147 | v1735-1761 | COMPANY-NAME REPLY, narrowed | R-P1-08 | 1998 | escalation.company_pick | O1 V1 | MERGE INTO R-P1-08: OUTRANKS v606-638 |
| 148 | v1762-1768 | is_affirmative is not the escalation verdict | R-P1-08 | 469 | is_affirmative | N1 | MERGE INTO R-P1-08 |
| 149 | v1769-1803 | POLICY BLOCKS (domains, entity kinds, {{specs}}, {{find_filters}}) | R-X-09 | 3718 | domain_hint, entities[].hint, spec_key, find | - | KEEP: literal domain / kind lines -> {{domains_detail}} / {{entity_kinds_detail}} |
| 150 | v1804-1819 | CLOSED LISTS: listed_item + OVERRIDES | R-P2-06 | 1314 | entities[].listed_item | N2 V1 | KEEP: drop the OVERRIDES sentence (v1810-1813) |
| 151 | v1820-1822 | File types {{attachment_types}} | R-P2-06 | 85 | listed_item | - | KEEP |
| 152 | v1823-1831 | Certification kinds and schemes | R-P2-06 | 600 | listed_item | A1 | KEEP |
| 153 | v1832-1847 | Candidates block | R-P2-02 | 993 | entities[].canonical_code, spec_key, spec_value, confident | N1 | KEEP |
| 154 | v1848-1859 | CODE LOOKUP: near code, set code | R-P2-02 | 1097 | entities[product].canonical_code | N1 | MERGE INTO R-P2-02: keep the text; R2-6 tests pin its phrases |
| 155 | v1860-1864 | Asked attributes override | R-P3-05 | 403 | requested_attributes | V1 | MERGE INTO R-P3-05: OVERRIDES closed vocabulary -> single rule |
| 156 | v1865-1869 | A count beside a code (override) | none | 378 | domain_hint, intent_hint, domain_in_message, entity_op, quantity | V1 | DELETE: replaced by R-P1-03 (R-DOM-QTY); conflicts with S35 r2-D |
| 157 | v1870-1872 | A bare code reuses the answer's domain | R-P1-02 | 205 | domain_hint | - | MERGE INTO R-P1-02: third copy of the carry rule |
| 158 | v1873-1881 | When deliver | R-P3-06 | 909 | order_status, domain_hint | N2 | MERGE INTO R-P3-06: word list + exception to "Never infer from context" |
| 159 | v1882-1884 | A spec word that picks a set is no attribute | R-P3-05 | 242 | requested_attributes | N1 | MERGE INTO R-P3-05 |
| 160 | S1-8 | STATE: State block lines | R-P1-01 | 560 | (input) | N1 | KEEP |
| 161 | S9-11 | STATE: alias "where the rules above mention ..." | none | 150 | - | - | DELETE: alias section (F1 delete): base rules are rewritten to read State |
| 162 | S12-15 | STATE: fill fields from THIS message; State items are not entities | R-X-03 | 243 | entities, all fields | - | MERGE INTO R-X-03 |
| 163 | S16-20 | STATE: state_changes item; value lives in the fields | R-P1-01 | 418 | state_changes | N1 | KEEP |
| 164 | S21-32 | STATE: ops table | R-P1-01 | 1648 | state_changes[].op/axis/position | N1 | KEEP |
| 165 | S33-34 | STATE: several items of one axis are one set | R-P1-02 | 108 | state_changes | - | MERGE INTO R-P1-02 |
| 166 | S35 | STATE r2-D: only another item asks the same fact | R-P1-02 | 163 | state_changes, domain_hint | - | KEEP: opposite of v1865-1868 for a code with a count; precedence: see R-P1-03 |
| 167 | S36 | STATE: reference to the held subject is keep | R-P2-13 | 113 | state_changes, entities | N1 | MERGE INTO R-P2-13 |
| 168 | S37-38 | STATE: "and <another item>?" | R-P1-02 | 129 | state_changes | - | MERGE INTO R-P1-02 |
| 169 | S39 | STATE: a quantity for the held item is set quantity | R-P1-03 | 55 | state_changes | - | MERGE INTO R-P1-03 |
| 170 | S40 | STATE: a customer named first stays | R-P1-09 | 87 | state_changes | - | MERGE INTO R-P1-09 |
| 171 | S41-42 | STATE: new ask with its own measure is new_subject | R-P1-04 | 217 | state_changes | - | KEEP |
| 172 | S43 | STATE: close_question | R-P1-07 | 97 | state_changes | - | KEEP |
| 173 | S44 | STATE: small talk is keep | R-P1-10 | 103 | state_changes | - | MERGE INTO R-P1-10 |
| 174 | S45-47 | STATE: [] when unsure or no State | R-P1-10 | 218 | state_changes | - | KEEP: [] falls back to decide() over entity_op (blocker B1) |
| 175 | S48-53 | STATE: held-slot rules (customer, period) | R-P1-09 | 651 | state_changes (customer/period slots) | - | KEEP |
| 176 | S54-57 | STATE: held customer, delivery vs ETA | R-P1-09 | 392 | state_changes, domain_hint | - | MERGE INTO R-P1-09: conflict C6 with v165 / v1879 |

## 2. Conflict pairs

Each pair: the rules that decide one field, how they disagree, the one replacing rule, and the fresh conflict-pair
shapes for parser gold (N=3, old = v178 + STATE vs new). A shape is "State, then message -> expected". Shapes are new
wordings, not held-out items (anti-overfit rule).

### C1. A count beside a code: which domain (4 rules and a regex)

- CODE LOOKUP v1865-1868: a code with a count and no purpose word "is a stock ask whatever the previous domain",
  entity_op "replace", "overrides BARE ENTITY CONTINUATION".
- STATE S35 r2-D (`chat_state_prompt.py:41`): "A message naming only another item ... asks the same fact as the last
  answer: `set product` and keep the domain marked `(answered)`"; S39 "A quantity said for the held item is
  `set quantity`".
- BARE ENTITY CONTINUATION v199-208 and v1870-1871: a bare value continues the previous domain.
- v1288-1303 "Last answered:": a new quantity is inventory, `correction` true.
- `engine.py:500-556` `_as_a_stock_ask_by_its_own_words` (call site `engine.py:5241-5246`, only for a
  `stock_availability_only` profile): an incoming or master_products verdict with a code and a quantity (demand_qty,
  an entity quantity, or ANY standalone number in the text, `engine.py:536-543`; a carried demand_qty fires it too) and no `_ETA_WORDS` match is rewritten to inventory.
- They disagree on "SRTKT73SS x 5" after an ETA answer (CODE LOOKUP and the regex: inventory; r2-D and BEC:
  incoming) and after an outstanding-order answer (CODE LOOKUP: inventory; r2-D: order).
- Replacing rule R-P1-03 (DOM-QTY) (R-DOM-QTY, approved): "A message that states a quantity and names no ask word of its
  own continues the last answer's domain when that domain takes a quantity (stock, incoming, order); otherwise it
  is a stock ask. Ops: `set product` when a product is named, `set quantity`; `switch_domain` only when the last
  answer's domain takes no quantity. An ask word in the message wins (R-P3-01 (DOM))." Deletes v1865-1868, v1288-1303,
  the regex under the state gate, and the r2-D / BEC gap for a count.
- Shapes:
  - subject incoming (answered) SRTWC286; "SRTKT73SS x 5" -> incoming, [set product, set quantity], quantity 5.
  - subject order (answered), status outstanding; "CB88SS 10 pcs" -> order, outstanding, [set product, set quantity].
  - subject master_products (answered, a list price); "SRTKT73SS 5 units" -> inventory, [switch_domain, set product,
    set quantity].
  - subject inventory; "MHS1028 80" -> inventory, [set product, set quantity] (control: every old rule agrees).
  - subject inventory; "ETA SRTKT73SS x 5" -> incoming (control: an ask word wins).
  - no State, `stock_availability_only` contact; "CWCX611 x 300" -> inventory, [] (the regex's own case).
  - subject incoming; "SRTKT73SS" (no count) -> incoming, [set product] (guards R-P1-02 (CARRY)).

### C2. attachment_type: taxonomy canonical_code vs listed_item, and the cert-scheme EXCEPTION

- v330-341: "canonical_code is always the taxonomy value (photo, video, technical drawing, 3D model, certificate,
  installation guide)"; v391: the same, plus "EXCEPTION: for authority/brand-named certificates (SPAN, SIRIM, BOMBA,
  MS####, Halal, Watermark/WCM/PPS) leave canonical_code null and keep the body name in raw"; v402: canonical_code
  "REQUIRED" for attachment_type, one of five kinds (video missing); v1442-1444: "or a certificate body".
- CLOSED LISTS v1804-1818: `listed_item`, "This section OVERRIDES every earlier rule on how an attachment_type is
  written"; v1823-1829: a certificate word is the kind entity, a listed scheme is ONE MORE entity, an unlisted scheme
  is no entity.
- They disagree on "SPAN cert for SRTWC286": EXCEPTION gives one entity (canonical null, raw SPAN); CLOSED LISTS gives
  two (kind + scheme). The parser merges them and loses the kind (arch review M3). Code reads `listed_item` first,
  then `canonical_code` (`grounding.py:720-736`).
- Replacing rule R-P2-06 (FILE): "A file ask is one attachment_type entity per item asked: listed_item is the File type or
  Certificate kind it IS, or "none of these"; canonical_code repeats listed_item. A Certificate scheme the message
  names that is listed is one more attachment_type entity (listed_item the scheme); an unlisted scheme is no entity.
  A property of the product is never a file type." Deletes v330-341's canonical rule and photo list, v391, v402's
  REQUIRED list, the OVERRIDES sentence. (F3 later parents schemes to kinds; this rule then loses its second
  sentence.)
- Shapes: "SPAN cert for SRTWC286" (SPAN listed) -> 2 attachment_type entities + product; "pps cert SRTKT73SS" (PPS
  unlisted) -> 1, the certificate kind; "gambar SRTKT73SS" -> the photo item, canonical_code = listed_item; "BIM file
  for SRTWC286" (no BIM line) -> "none of these"; "video SRTWC286" -> the video item (guards the v402 gap); "gunmetal
  basin photo" -> photo + finish specification, no gunmetal file type.

### C3. requested_attributes: closed vocabulary vs whole phrase vs the CODE LOOKUP override

- v246-247: "an array drawn ONLY from this closed vocabulary. Never invent a value outside it"; v249-252
  master_products: price, dimension, discontinued.
- v244 and its verbatim duplicate v985-986: the customer's phrase, WHOLE, base properties too.
- v958 example: "steel grade of SRTKT73SS" -> `["steel_grade"]` (a registry key, not the phrase).
- CODE LOOKUP v1860-1863: "This overrides the closed vocabulary of REQUESTED ATTRIBUTES for master_products only";
  v1882-1883: a spec word that picks a set is no attribute; no "discontinued" unless asked.
- They disagree on "SRTKT1636SS-GM check weight ?" (closed list drops "weight", CARD cp0-39e88ea65f) and on the form
  of a named property. The engine matches any word by token containment over key or label (`fetch.py:1997-2006`),
  so the closed master_products list has no reader.
- Replacing rule R-P3-05 (ATTR): "requested_attributes lists what this message asks about and nothing else. Incoming: the
  CRM key from the key table (["__all__"] for a container's whole status). Order: delivery, items or quantity. Any
  product ask: the customer's own phrase, whole. A bare "spec" is []. A word that only picks a product, set or
  variant is not an attribute."
- Shapes: "SRTKT1636SS-GM check weight ?" -> ["weight"]; "steel grade of SRTKT73SS" -> ["steel grade"] (grader also
  accepts "steel_grade": both match the key); "SRTKT73SS spec" -> []; "SRTWC286 P-trap set price" -> ["price"], no
  "p-trap"; "has TIIU6323920 cleared CIDB" -> ["inspection_date", "approval_date"]; "is SRTWT9613-BL still sold" ->
  ["discontinued"] (meaning, not the word).

### C4. Six relation channels vs state_changes

- entity_op v446-455 (+ v204 replace_combine, v450 replace, v510 reuse, v1275 modify, v1867 replace);
  reference_positions v571-585, v854-903, v1587-1603; open_question_answer v1305-1355, v1057-1064; topic_reset
  v741-746; domain_in_message v85-103 ("tell a NEW QUESTION from a REFINEMENT"); ranking_refine v1097-1112;
  is_affirmative v23-31. STATE S21-31 ops (keep, new_subject, set, clear, pick, answer, switch_domain,
  close_question) and the S9-10 alias that points the base rules at the State lines.
- One relation is asked six times: "4 stock" over an open roster is reference_positions [4] + domain fields
  (v866-867) and `[pick 4, switch_domain]` (STATE); "drop ABC123" is entity_op "modify" (v1275) and has no STATE op
  at all (no op removes one item of an axis). Arch review: 68/166 held-out items differ in state ops run to run.
- Code fact (#1772 d45781dbf): `apply_changes` reads `open_question_answer.mode` as the value of an `answer` op
  (`chat_state.py`, the `op == "answer"` branch) and `picked` / `qty_for_all` for picks; a `[]` or rejected change
  returns `_reject`, the state is not led, and `apply.py:3433` lets `decide()` read entity_op, reference_positions and
  domain_in_message (`decide.py:393, 519, 631, 653`). So the old channels are still the fallback under the gate.
- Replacing rule: R-P1-01 (STATE) plus the P1 rules decide the relation as ops only. R-X-05 (MIRROR) fills the old fields from the
  ops by a fixed table: keep -> entity_op reuse; set -> replace_combine; new_subject -> replace (topic_reset true
  only when nothing carries); clear of every axis -> clear; pick n -> reference_positions [n] and
  open_question_answer {mode pick, picked [n]}; answer -> open_question_answer mode = the value; no answer ->
  mode null; switch_domain or new_subject -> domain_in_message true; set on a held ranking -> ranking_refine true;
  no State or [] -> entity_op from the message alone (replace_combine when it names a value, else reuse).
  open_question_answer keeps only its VALUE semantics (fill / done / all / cancel, items, qty_for_all) as R-P1-06 (ANSWER).
  When CHAT-STATE confirms the applier and `decide()` read only state_changes (B1), R-X-05 (MIRROR) is deleted and the old
  fields go neutral.
- Shapes: roster 1-4 + "4 stock" -> [pick 4, switch_domain], reference_positions [4]; roster + "check stock" -> 
  [switch_domain], reference_positions []; open stock task (MHS1028, ABC123) + "drop ABC123" -> needs a CHAT-STATE
  ruling (no op); "Sales order" alone over the SO / DO roster -> [pick 1], document ["SO"]; first turn, no State,
  "stock SRTWC286" -> [], entity_op from R-X-05 (MIRROR)'s no-State row (replace_combine).

### C5. domain_hint on a message that only names values

- BEC v204-205: domain_hint = the previous turn's. NARROWING REPLY v1221-1222: domain_hint null, order_status null
  under an open sales_report_detail / outstanding_detail offer. READING v46-50: a domain-only message emits no
  entities. STATE S35: keep the answered domain. NARROWING TOP SELLING v1616-1621 and low stock refining v1051-1055:
  the held report's own order_status / intent.
- "just SRTWC286" under an open outstanding_detail offer: NARROWING -> null; BEC -> order; STATE -> answered domain.
- Replacing rule R-P1-02 (CARRY): "A message that only names values (codes, a customer, a place, a period, a channel) over
  a held subject is one `set` per axis; the ask stays the held one: domain_hint, intent_hint and order_status repeat
  the State subject's, message_type business_query. Only an own ask word makes a switch or a new subject."
  Code to check (CHAT-STATE): the detail-offer refine paths that key on a null domain (`so_status.py:567`,
  `engine.py:2422-2429`, `fetch.py:855`) must read the `set` op on the state path.
- Shapes: open outstanding_detail offer + "just SRTWC286" -> [set product], order, outstanding; answered top 5 sales
  agents + "sorento only" -> [set brand], sales_ranking, ranking_refine true; answered low stock report + "taiyang
  only" -> [set ...], low_stock_report, low_stock.suppliers ["taiyang"]; same + "stock for SRTWC286" -> new_subject,
  inventory (control).

### C6. "when will it arrive" / "when deliver", with and without a held customer

- STATE S54-56: "a delivery or 'when will it arrive' ask with a held customer is delivery to that customer (`keep
  customer`, delivery/order domain)". v165: "when will it arrive" is DECISIVE incoming. v1879-1880: "An arrival ask
  about stock coming in ('when ... arrive', ...) stays incoming". v647-649 and v1873-1878: when deliver is
  outstanding, and v1876-1877 suspends v653 "Never infer from context". Policy line v1775 lists deliver as an order
  switch word.
- Held customer HANLIM + "when will SRTWC286 arrive?": STATE -> order, keep customer; v165 and v1879 -> incoming.
- Replacing rule (R-P3-06 (STATUS) meaning, R-P1-09 (SLOTS) stance): "Who the goods go to decides. Goods reaching a customer
  (named, or held and kept) is an order ask, status outstanding, never a period question. Goods reaching our
  warehouse from a supplier is incoming. With a held customer and no supplier, factory, warehouse or ETA word, an
  arrival ask is delivery to that customer (`keep customer`)." No word list; v653's "never infer" moves to
  R-X-03 (THIS-MESSAGE) and has no exception.
- Shapes: no held customer + "when will SRTWC286 arrive" -> incoming; held HANLIM + the same -> order, outstanding,
  [keep customer]; held HANLIM + "ETA from factory for SRTWC286" -> incoming, [skip customer]; "SRTKT73SS bila sampai
  kedai hanlim" -> order, outstanding; "wen deliverd SRTWC286 to hanlim" -> order, outstanding. Gate: when-deliver
  gold stays >= 31/42.

### C7. Company name and new asks over a hand-over offer

- v618-621: "This applies whatever the message_type ... naming an offered company while the offer is pending IS the
  pick". v1735-1756 (OUTRANKS it): the name is the pick only when the message IS the answer. v627-634 and the
  duplicates v970-980 / v1723-1730: a value or a question of its own is not an answer. v1729: "That question runs,
  and the offer stays open". STATE S43: a message that does not answer the open question adds `close_question`.
  is_affirmative (v23-31, v1762-1767) and is_escalation_confirmation (v1699-1701) are two verdicts on one yes.
- Replacing rule R-P1-08 (ESC): "A hand-over offer (the State open question carries `offer`) is answered (`answer` op)
  only by a reply that agrees, declines or picks one offered team or company, alone or with filler:
  is_escalation_confirmation true and company_pick the listed name on agreement; is_affirmative carries the yes or
  no. A reply with anything of its own (a filter, product, document, brand word or question) is its own ask:
  company_pick null, is_escalation_confirmation false." Whether that own ask closes the offer is the C13 ruling.
- Shapes: open Mocha CS offer + "mocha brand" -> brand entity, order domain, false; + "mocha" -> true, Mocha; + "1"
  -> true; Sorento listed + "yes escalate to srt team" -> true, Sorento; + "PO for SRTWC8517" -> purchase_order ask,
  false.

### C8. A listed code typed back: position AND entity vs never both

- v894-899: "the typed option is both the entity the message names and the position it picks". v903: "Never emit
  BOTH an entity and a reference_position for the same message." Same section, opposite rules.
- Replacing rule R-P1-05 (PICK): a listed code or name typed back is `pick n` and stays an entity as typed (the applier
  swaps in the list row, `chat_state.py` data_picks). v903 is deleted.
- Shape: roster 1. SRTWC286-SH ... 4. SRTWC286-SH-NEW + "stoick SRTWC286-SH-NEW" -> [pick 4, switch_domain],
  inventory, the entity kept.

### C9. sales_channel scope

- v1171-1172: "Emitted ONLY when order_status is "sales_report" this turn". v1093 and v1108: sales_channel on a
  sales ranking; v1385-1386: on a sales analysis.
- Replacing rule R-P3-12 (RPT): sales_channel is the channel word (dealer / project sales) on any sales report, analysis or
  ranking, never on an outstanding ask; a dealer named as the ranked noun is group_by customer.
- Shapes: "top 5 customers by dealer sales this year" -> sales_ranking, dealer; "outstanding dealer quantity for
  hanlim" -> outstanding, null.

### C10. SPO domain

- v659-660: "SPO" moves the domain to incoming. v183-184, v939-943 and policy v1780: SPO is spo_allocation.
  v703: document ["SPO"] also for "shipment" and "container".
- Replacing rule R-P3-01 (DOM): when it last came in and how much = spo_allocation; goods still on the way = incoming; the
  paper word only fills document.
- Shapes: "last SPO for SRTWC8517" -> spo_allocation; "SPO still coming for SRTWC8517" -> incoming, document ["SPO"].

### C11. Enumerations that disagree with the rules that use them

- v82 domain list lacks purchase_order (used v922, policy v1782); v67-81 intents lack check_po and
  low_stock_report; v402 hints lack specification and sales_agent (used v1416, v1071); v774 order_status lacks the
  buckets v825 says "the full set is now"; v782 status values differ from v655.
- Replacing rule R-X-06 (OUT): one key index; domains and intents rendered from the registry (`{{domains}}`, policy block),
  hints from `{{entity_kinds}}` plus sales_agent, each value list stated once. Checked by the $0 lint, not gold.

### C12. Routing for a certificate

- v534-535: product_attachment certificate -> purchasing_certification. Policy v1771: product_attachment escalates
  to marketing_product.
- Replacing rule R-X-08 (ROUTING): the team is the policy line's "Escalates to", except a certificate file ask ->
  purchasing_certification (stated once). Shape: "SIRIM cert SRTWC286" -> purchasing_certification.

### C13. STATE internal: small talk vs close_question; an own ask over an offer

- S43 "When the `open question` is open and the message is not an answer to it, add `close_question`" vs S44 "Small
  talk ... change nothing: [keep]" (for "ok thanks" under an owed question), and vs v1729 "the offer stays open".
- Replacing rule R-P1-07 (CLOSE): "`close_question` only when the message starts an ask of its own and leaves an owed
  question unanswered; small talk never closes it." The hand-over offer case needs a CHAT-STATE ruling (B1).
- Shapes: open period question + "ok thanks" -> [keep]; same + "stock for SRTWC286" -> [new_subject,
  close_question]; open hand-over offer + "price of SRTWC286" -> per ruling.

### C14. correction overloaded

- v518-519: the previous answer was WRONG. v1291-1295: "how about 100?" after a stock answer sets correction true.
  v1637: a correction of a ranking axis.
- Replacing rule: R-P3-17 (CORR) only for "the last answer was wrong"; a new quantity is `set quantity` (R-P1-03 (DOM-QTY));
  v1288-1303 is deleted. Check the stock path's readers of `correction` before the shape is graded.
- Shape: last stock answer SRTGV332-DIY x 20 + "how about 100?" -> [set quantity], demand_qty 100, correction false.

## 3. Word lists (more than 8 trigger items) and their meaning rules

Item counts are the quoted or comma-listed triggers in the block. The F1-A lint refuses a quoted list of more than
8 items (section 5.7), so each of these must become its meaning sentence, not a shorter list. Registry-rendered
lists (policy "Switch words", `{{specs}}` words, `{{find_filters}}`) are data, not template text, and are exempt from
the lint. Value
vocabularies that code reads (the 20 incoming CRM keys v264-283, document codes, enums) are key tables, not
trigger lists, and stay.

| lines | list | items | field | meaning rule (id) |
|---|---|---|---|---|
| v644-649 + v1873-1878 | outstanding words + when-deliver (R2-5 and CODE LOOKUP) | 10 + 4 + 7 | order_status | asking about customer orders not yet delivered, including WHEN goods will be delivered to or reach a customer, is an outstanding ask; goods reaching our warehouse from a supplier is incoming (R-P3-06 (STATUS), C6) |
| v821-822, v832-836 | so_outstanding / do_outstanding phrases | 9 + 7 | order_status | the outstanding bucket is the paper the message names: sales orders -> so_outstanding, delivery orders -> do_outstanding, both -> outstanding_both, none -> outstanding (R-P3-06 (STATUS) table) |
| v86-88 | DOMAIN IN MESSAGE words | 20 | domain_in_message | true when the message itself names what kind of fact it asks (a domain, a status, a paper or a report); false when it only names values, a date or a place (R-P3-03 (DIM)) |
| v117-120 | master_products terms | 15 | domain_hint | what the product IS: identity, description, measurements, material, finish, list price, discontinued (R-P3-01 (DOM)) |
| v122-123 (+ v18-21) | promotion / selling price terms | 9 | domain_hint | an offer or campaign, or a price under one (R-P3-02 (PRICE)) |
| v996-998 | purchase cost terms | 11 | domain_hint | what WE paid a supplier; what we charge is never this (R-P3-02 (PRICE)) |
| v127-128 + v335-336 | product file terms + photo triggers | 10 + 10 | domain_hint, attachment_type | a FILE of one product, including asking to see what it looks like (R-P3-01 (DOM), R-P2-06 (FILE)) |
| v130-134 | resource document terms | 12 | domain_hint, attachment class | a company document not tied to one product (R-P3-01 (DOM), R-P2-07 (RESOURCE)) |
| v165-173 | inbound clearance checkpoints | 23 | domain_hint | any step of a supplier shipment on its way to our warehouse; which step is the CRM key table (R-P3-01 (DOM), R-P3-05 (ATTR)) |
| v802-807, v1033-1038 | group_by phrases (order and low stock) | 23, 18 | group_by, low_stock.group_by | the axis the message asks the answer split by (R-P3-13 (GROUPBY), R-P3-11 (LOWSTOCK)) |
| v1522-1528 | top selling phrases | 20 | order_status | a ranking of items or categories by what was sold (R-P3-12 (RPT)) |
| v1371-1373 | sales analysis phrases | 9 | order_status | the company's own sales totals, no product or customer named (R-P3-12 (RPT)) |
| v1541-1544 | rank_by amount words | 9 (+ 7 quantity) | rank_by | the measure: units (quantity) or money (amount) (R-P3-12 (RPT)) |
| v1606-1611 | bottom / least-sold words | 12 | rank_direction | least sold first is bottom, a slip of spelling included (R-P3-12 (RPT)) |
| v1080-1091 | ranked nouns (salesman, SA, customer, 经销商, ...) | 10 | entities | the noun a ranking ranks is never an entity (R-P2-10 (PARTIES)) |
| v1681-1685 | first-person account words | 12 | self_reference | a first-person word about the asker's own account, any language (R-P3-16 (SELF)) |
| v29-30 | ESCALATE-WORD forms | 9 | is_affirmative | answering an offer with the offer's own verb is a yes (R-P1-08 (ESC)) |
| v1712-1715 | escalation TRUE examples | 9 | is_escalation_confirmation | already "not a list to match": keep the meaning sentence only (R-P1-08 (ESC)) |
| v1323-1333 | pick ordinals and confirm words | 22 | open_question_answer | a pick names options by number, ordinal or name in any language; yes and no in any language (R-P1-05 (PICK), R-P1-06 (ANSWER)) |
| v62-63, v1354-1355 | number words | 9 | reference_positions, quantities | a number written as a word, in any language, is that number (R-X-04 (MEANING)) |
| v405-406 | grammar particles | 10 | entities | a word with no referent of its own is never an entity (R-P2-01 (ENT)) |
| v594-595 | honorifics | 10 | person_mention | a person named in any form, with or without a title (R-P2-11 (PERSON)) |
| v1021-1028 | low stock category translations | 10 | low_stock.categories | each kind of product named, in English (R-P3-11 (LOWSTOCK)) |
| engine.py:494-498 `_ETA_WORDS` | ETA regex alternatives (code) | 14 | domain_hint rewrite | replaced by R-P1-03 (DOM-QTY); the regex is deleted under the gate |

## 4. Size budget

Measured in raw template chars, the unit of the plan's "v178 is 137 KB" (v178 = 137,132 chars). Gate: <= 90,000;
stretch <= 75,000. "Now" is the sum of section 1 rows by the id they map to (DELETE rows counted apart).

| step | now (v178 + STATE) | target | stretch | per id target |
|---|---|---|---|---|
| X | 18,206 | 12,250 | 9,000 | R-X-06 (OUT) 4,000; R-X-09 (POLICY) 3,700 (400 with `{{domains_detail}}` / `{{entity_kinds_detail}}`); R-X-02 (DATE) 1,400; R-X-05 (MIRROR) 900; R-X-08 (ROUTING) 700; R-X-01 (FRAME) 600; R-X-03 (THIS-MESSAGE) 400; R-X-04 (MEANING) 300; R-X-07 (GOAL) 250 |
| P1 | 39,748 | 19,500 | 17,500 | R-P1-06 (ANSWER) 4,300; R-P1-08 (ESC) 3,600; R-P1-05 (PICK) 3,000; R-P1-02 (CARRY) 2,800; R-P1-01 (STATE) 2,400; R-P1-04 (SWITCH) 1,200; R-P1-09 (SLOTS) 1,100; R-P1-03 (DOM-QTY) 500; R-P1-07 (CLOSE) 300; R-P1-10 (UNSURE) 300 |
| P2 | 21,281 | 15,300 | 13,500 | R-P2-02 (CAND) 2,100 (pinned phrases, section 5); R-P2-08 (SPEC) 2,000; R-P2-06 (FILE) 1,900; R-P2-01 (ENT) 1,600; R-P2-03 (SHAPE) 1,600; R-P2-10 (PARTIES) 1,100; R-P2-05 (QTY) 1,000; R-P2-04 (CONF) 800; R-P2-09 (BRAND) 800; R-P2-13 (PRONOUN) 700; R-P2-12 (ACCESS) 600; R-P2-07 (RESOURCE) 600; R-P2-11 (PERSON) 500 |
| P3 | 54,590 | 33,400 | 30,000 | R-P3-12 (RPT) 8,500; R-P3-01 (DOM) 5,500; R-P3-05 (ATTR) 3,800 (incoming key table about 1,600); R-P3-09 (BROADEN) 2,500; R-P3-06 (STATUS) 2,200; R-P3-11 (LOWSTOCK) 2,200; R-P3-04 (MSGTYPE) 2,000; R-P3-07 (PAPER) 1,400; R-P3-02 (PRICE) 1,100; R-P3-10 (ASKS) 900; R-P3-03 (DIM) 700; R-P3-13 (GROUPBY) 700; R-P3-08 (ACTIVE) 500; R-P3-16 (SELF) 500; R-P3-14 (TOPN) 350; R-P3-15 (FLYER) 250; R-P3-17 (CORR) 150; R-P3-18 (MATCH) 150 |
| deleted | 8,659 | 0 | 0 | section 1 DELETE rows |
| total | 142,484 | 80,450 | 70,000 | |

Projected: about 80 K raw (9.5 K headroom under the gate); rendered about 95 K plus the two DB lists (v178 + STATE
renders about 157 K plus the same lists). The stretch needs the policy lines as variables (size-neutral when
rendered, so it is not counted as a saving in the target).

What is cut to get from 142.5 K to 80.5 K (approximate, overlapping categories assigned once):

1. DELETE rows, 8.7 K: verbatim duplicates (v982-988); text keyed on lines the state gate does not print (v33-45,
   v1288-1304); a dead trigger (REFERENCE TARGET v587-592, no code emits the did-you-mean marker); rules superseded by
   a replacing rule (v249-252, v330-342, v391, v402, v446-456, v741-747, v1865-1869); the STATE alias (S9-11).
2. Examples beyond one per rule, about 20 K: v178 has about 340 example or mapping lines (29.2 K chars); about 60
   survive (one per rule, plus the conflict-pair examples that pin a precedence).
3. Repeated explanations, about 12 K: "never carry over / current message only" stated about 14 times (v358, v522-526,
   v546-562, v641-653, v683-684, v699, v801, v816, v1096, v1111-1112, v1172, v1480-1481, v1490-1491, S12-14) becomes
   R-X-03 (THIS-MESSAGE); "read for meaning, any language, misspelt" (v105-106, v667-674, v1611, v1702) becomes R-X-04 (MEANING);
   the DECISIVE / OVERRIDING preambles (v21, v104-114, v132-133); request_for_help defined three times (v316, v323,
   v983); "the document word counts wherever it sits" twice (v707-716, v842-852); "a new question is never a yes"
   three times (v970-980, v1723-1730, v627-634); the why-sentences ("The assistant reads this to ...", "Customers ask
   this ... far more often", "costs the user an extra question").
4. Relation rules folded into ops, about 11 K: the pick, answer, carry and escalation rules spread over 16 sections
   (v199-221, v571-586, v606-639, v854-904, v970-981, v1051-1065, v1097-1124, v1215-1243, v1267-1287, v1305-1357,
   v1564-1604, v1616-1668, v1693-1768) become R-P1-02 (CARRY) / R-P1-05 (PICK) / R-P1-06 (ANSWER) / R-P1-08 (ESC), each stated once on the State.
5. Text keyed on user-block lines the gate replaces, about 5 K inside merged rows: "Current subject" (v42-56),
   "Open question options:" (v855-858), "Pending" (v1216, v1705), "Open task:" (v1268-1270), the Open question object
   description (v1306-1315), all rewritten as one R-P1-01 (STATE) description of the State block.
6. OUTPUT block and the 8 "IN ADDITION to the OUTPUT object" headers, 5.4 K -> R-X-06 (OUT) 4.0 K (one key index with
   value sets and the owning id; the strict schema already holds the keys).
7. Word lists to meaning rules (section 3), about 3.5 K.

## 5. What must stay byte-stable for code

Found by grepping the backend (app, scripts, tests) for every v178 line prefix of 36+ chars and for each label the
prompt names. "Raw" means the unrendered template, which is what the gates read.

### 5.1 Gate markers (raw template, read by `parser.resolve_config` in one registry read)

| text | reader | note |
|---|---|---|
| `== CLOSED LISTS ==` | `closed_lists_prompt.MARKER` / `gate_on` (parser.py `resolve_config`, `uses_closed_lists`) | turns on the candidate block, grounding against the lists, the `listed_item` schema |
| `== CODE LOOKUP ==` | `code_lookup_prompt.MARKER`; `gate_on` needs it AND the CLOSED LISTS marker | near codes in the candidate block, product pick checked against it |
| `## Conversation state and state_changes` | `chat_state_prompt.HEADING` (`resolve_config`: `state_block = HEADING in raw_template`); `build_lane_prompt` idempotence | the schema with `state_changes`, the `State:` block instead of the legacy lines |
| `== PARSER TEMPLATE ==` (new) | F1-A red tests: `parser_template.MARKER`, `ParserConfig.template`, `_as_a_stock_ask_by_its_own_words(..., template=True)` stands down, `scripts/publish_parser_template.py` publishes `TEMPLATE` verbatim and unlabelled | a line of its own (`test_template_keeps_gate_markers`) |
| `<<<CHATBOT POLICY BLOCKS>>>` then `<<<END CHATBOT POLICY BLOCKS>>>`, in that order | `chatbot_parser_prompt.py:1176-1177`; `chatbot_find_prompt.py:35`; `publish_specs_token_prompt`; `chatbot_prompt_vars.py:166` refuses rows that contain them | the policy block, `{{specs}}` and `{{find_filters}}` live between them |

The consolidated template carries all five. A marker is a gate, so its words may sit anywhere (a heading of the
folded text), but each must occur once, verbatim. `test_template_keeps_gate_markers` checks only CLOSED LISTS, CODE
LOOKUP and PARSER TEMPLATE; the state heading is not checked, yet without it `state_block` is False, the schema has
no `state_changes` and the user block has no `State:` (every P1 rule would read nothing). Either the template carries
the heading line or `resolve_config` derives `state_block` from the template marker (B7).

### 5.2 Tokens

`{{current_date}}` (a declared variable: `render` raises when it is missing, `ai_prompt_registry.py:1080`), and the
registry variables `{{specs}}`, `{{find_filters}}`, `{{attachment_types}}`, `{{certification_types}}`. The gated
schema's `listed_item` enum is `closed_list_enum(db)` (`parser.py:resolve_config`): the items the two list tokens
render, plus `"none of these"` (`closed_lists_prompt.NOT_LISTED`, pinned by `test_closed_lists_gate.py:260-263`).
Optional replacements for literal lists: `{{domains}}`, `{{domains_detail}}`, `{{entity_kinds}}`,
`{{entity_kinds_detail}}`, `{{statuses}}`, `{{status_values}}`, `{{teams}}`, `{{agents}}`, `{{access_levels}}`
(`chatbot_prompt_vars.VARIABLES`).

Drift constraint: `test_prompt_dynamic_drift.py:178-209` refuses literal registry lists in any version published
after the wording layer unless its `config_json.identical_report` says "kept literal"
(`chatbot_prompt_vars.py:1012-1020`). v178 matches 7 of the 7 patterns: domains v82, access_levels v351,
entity_kinds v402, statuses v644, status_values v774 and v782, teams v777, agents v778. The F1 template uses the variables or records them kept
literal.

### 5.3 JSON field names and values code compares

- Keys: the 59 `required` keys of `PARSE_OUTPUT_JSON_SCHEMA` (`parser.py:626-686`), `state_changes`
  (`_STATE_CHANGES_SCHEMA`), and the entity keys raw, hint, canonical_code, current_message, confident,
  hint_confident, quantity, spec_key, spec_value, account, listed_item. Names in the prompt must be these exactly.
- Schema enums (provider-enforced): group_by, sales_channel, rank_by, basis, rank_group, rank_direction, sort_by,
  sort_dir, ranking_drill, measure, sales_basis, document (SO, DO, PO, SPO, GRN), open_question_answer.mode (pick,
  yes, no, fill, all, done, cancel), low_stock.group_by, chat_report enums, profile_statements keys,
  state_changes.op (keep, new_subject, set, clear, pick, answer, switch_domain, close_question).
- Free strings code compares (not enforced, so the prompt is their only source): domain_hint and asks[].domain (the
  `chatbot_domains` codes), intent_hint (check_stock, check_incoming, check_product, check_order, check_po,
  check_spo, check_po_cost, low_stock_report, submit_idea, get_forms, get_portal_link, check_goods_receive,
  check_product_attachment, get_resource_attachment, check_promotion), order_status (outstanding, delivered,
  so_outstanding, do_outstanding, outstanding_both, sales_report, sales_analysis, sales_ranking, top_selling),
  status, message_type (request_for_help, business_query, clarification, casual, unknown), entity hints (product,
  category, brand, customer, transporter, order, promotion, attachment, attachment_type, form, inbound_shipment,
  warehouse, specification, sales_agent), attachment classes (catalogue, warranty, price tag template, brand
  guarantee, container status), incoming requested_attributes keys (v264-283) and `__all__`, order attributes
  (delivery, items, quantity), "discontinued" (`fetch.py:1912-1916` `_asks_discontinued`), routing team and agent
  codes, access level strings, broaden_axis / broaden_to (date, all, family, an entity hint), scope_intent,
  entity_op, date_mode, reference_target (result, dym), state_changes axis names (customer, warehouse, brand, tier,
  channel, period, status, document, sort, quantity, plus the entity kinds).
- `grounding.py:418-422` `DOCUMENT_TYPE_CODES` (photo, video, technical drawing, 3d model, certificate, installation
  guide) quotes v341 and is read by `_listed_document_type` when `listed_item` is empty; R-P2-06 (FILE) keeps canonical_code
  equal to the listed item, so this reader still works.

### 5.4 Prompt text that code or tests read

| text (v178) | reader | F1 action |
|---|---|---|
| the words "BARE ENTITY CONTINUATION" (v199) | `product_find.py:331-358` FIND_RULE names it three times; it is rendered by `{{find_filters}}`, which production v63 also reads | keep the words as the title of R-P1-02 (CARRY); changing FIND_RULE changes the production prompt |
| `OUTSTANDING_ANCHOR` = v644-646, `OUTSTANDING_ADDITION` = v647-649 | `scripts/publish_code_lookup_prompt.py:22-59`; `test_code_lookup_gate.py:122-185` | delete with the R2-5 insertion; the F1 publisher replaces this publisher |
| `TRAP_SPECS_ANCHOR` = v1454; `LIST_FRAGMENT_ANCHOR` = v1350 | `chatbot_parser_prompt.py:1062-1080` `with_trap_specs` (no-op when absent) | none: nothing re-applies these patches to an F1 version |
| "Candidates for words of this message" (v1832) | `candidates.HEADER` (`candidates.py:27`); `test_closed_lists_gate.py:60` asserts the prefix is in the section | keep verbatim in R-P2-02 (CAND) |
| candidate line shapes: `code X (name)`, `code X (name), holding "W"`, `near ...`, `set code X (name)`, `product type T (K = V)`, `spec K = V (label)`, `spec K = N`, `spec K (a number)`, `size N <unit> (no dimension named)` | `candidates.py:82-83, 196, 257, 261-272, 534, 537` | describe each; `spec K (a number)` (candidates.py:196) is emitted but described nowhere; the size line is #1755 round 6 (`closed_lists_prompt.py:56-57` at 86d095400b), newer than v178, so fold the current `closed_lists_prompt.SECTION`, not v178's copy |
| `"none of these"` (v1817) | `NOT_LISTED`; grounding `_on_closed_lists`; `test_closed_lists_gate.py:263` | keep verbatim |
| CODE LOOKUP phrases (v1849-1858): "a "near code x (name)" line under a word with a digit", "when two or more are equally plausible", "a "set code x (name)" line is a product set", "pick the set whose name carries it", "plainly the code the message means", "same digits with letters swapped, missing or one letter off", "never its own canonical_code", "pick the listed set or near set code whose name carries the spec"; and no "confident false" | `test_code_lookup_prompt_rules.py` e, f6, f8 (x2), r2_6 (they read `code_lookup_prompt.SECTION`, not the template) | keep verbatim in R-P2-02 (CAND); the tests stay green while SECTION stays |
| CODE LOOKUP phrases for the replaced rules: "5unit", "x 10", "stock ask", "whatever the previous domain" (r6), "bare code" / "reuses" (r6), "when deliver" / "period" / "delivery list" (q5), the "asked attributes." to "a count beside a code." slice (f7), "weight" / "own word" (r4) | `test_code_lookup_prompt_rules.py` r4, r6 x2, q5, f7 | they read SECTION, so they stay green; the F1 template must not carry these rules; add template tests for R-P1-03 (DOM-QTY), R-P3-06 (STATUS), R-P3-05 (ATTR) instead |
| "mode null, picked [], items [], qty_for_all null when there is no Open question line" (v1319-1320) | quoted in `turn/question.py:143-146` (`NO_ANSWER` comment, not a string compare) | none |
| first 200 chars of the template | `console_service.py:414-441` `prompt_base` lineage probe | v178 already reads "other" (v3 differs from `SEMANTIC_PARSER_PROMPT`); free, unless the console should default to F1 as "full" |

### 5.5 User-block labels the prompt names (code emits them; the prompt must use the same words)

- Under the state gate (`turn/context.py` `_assemble_off` / `_render_l2` on #1772, `turn/chat_state.py` `render`):
  `Previous response:`, `Current user message:`, `State:` with `- subject:` (domains marked `(answered)`),
  `- open question:` (JSON; `offer`, `hand_over_to`, `asked`, `clarify`, `other_brands` keys), `- last list (...)`,
  `- pending task:`; `Known brands:`; `Recent exchanges, oldest first:`; `reply to:`; the candidates block.
- NOT printed under the gate: `Current subject:`, `Open task:`, `Last answered:`, `Open question:`,
  `Open question options:`, `Pending: the assistant is waiting for a <kind> reply.` Rules keyed on them are DELETE or
  rewritten to read the State.
- Emitted by no code: `[<N> did-you-mean suggestions active]` (v588) and "Companies OFFERED in the pending offer"
  (v614 is static text since the n8n port).
- Bot reply strings the prompt quotes (code owns the copy): "Would you like me to escalate" (`turn/apply.py`,
  `turn/compose.py`), "Low stock report (" (`lanes/business/low_stock_ask.py`), "Do you mean customer X or sales
  agent Y? Reply 1 ..." (`label_catalog.py`), "By quantity or by amount?", "How many items do you want to see?",
  "Delivered (transferred to DO) or ordered?" (`label_catalog.py`, `ranking_ask.py`), "Top N sales agents ... by
  delivered sales" (`lanes/business/report_ask.py:705`), "Top {n} selling items" (`label_catalog.py:264`). Under
  the gate the State open question (`asked`) carries these; F1 should key on the State, not on reply wording.

### 5.6 Schema keys no v178 rule decides

The strict schema forces them, the model fills them unguided: sub_asks, family, po_refs, chat_report, sort_by,
sort_dir, ranking_drill, promotion_kind, portal_form, profile_statements, continuation (output block only),
entities[].account, entities[].hint_confident (examples only). R-X-06 (OUT) gives each one line (or "null in this
version") so the lint's field-to-rule index is complete.

### 5.7 What the F1-A lint (red tests) will refuse in TEMPLATE

From `tests/chatbot/test_parser_template.py` at 91b5c97c89 (the lint itself is not written yet):

- A block (paragraph) whose first line is not an id line `R-<step>-NN <title>`, and a repeated id. The gate markers
  must still be whole lines (`test_template_keeps_gate_markers` compares stripped lines), so each marker sits on its
  own line inside a block, after that block's id line (`R-P2-06 File types` then `== CLOSED LISTS ==`); the state
  heading may sit in an id line, its gate is a substring test.
- The words "overrides", "override", "alias" anywhere in the raw template. v178 carries the override family at v21,
  v107, v1810, v1862, v1867 (and OUTRANKS at v1697, v1735, same intent); STATE's alias is S9-10. All go.
- More than 8 quoted items in one list (the fixture is one sentence of 9 quoted words). Examples count: keep each
  example's quoted values under 9 (the v1323-1333 pick words and v802-807 group_by lines would trip it).
- Two absolute rules over one backticked field without a "(see R-x)" link. Write field names in backticks, so the
  lint can see them, and give every remaining ALWAYS / NEVER a "see" link when another rule decides the same field.
- `len(TEMPLATE) <= 90_000` chars: the unit of section 4.

## 6. Blockers and open decisions before the template is written

- B1 (blocks deleting the old relation channels; CHAT-STATE): under the gate a `[]` or rejected `state_changes`
  falls back to `decide()` (`apply.py:3433` on #1772), which reads entity_op, reference_positions and
  domain_in_message; `apply_changes` reads `open_question_answer.mode` for every `answer` op. Until CHAT-STATE (F2)
  rules that `[]` is handled without those fields, F1 keeps R-X-05 (MIRROR), a fixed op-to-field table of about
  0.9 K, instead of deleting them. Also needs a CHAT-STATE ruling: an op for removing one item of an axis ("drop ABC123" over an
  open stock task, v1275) and whether an own ask closes a hand-over offer (C7, C13).
- B2 (keeps a legacy name): FIND_RULE (`product_find.py:331-358`) is rendered into production v63 through
  `{{find_filters}}` and cites "BARE ENTITY CONTINUATION" three times. The F1 template keeps those words as the
  title of R-P1-02 (CARRY); renaming it means a FIND_RULE edit that also changes production's rendered prompt.
- B3 (sources): the STATE text F1 folds is #1772's (`origin/crew/chat-state-r2` d45781dbf, with r2-D and
  "(answered)"); this lane's `chat_state_prompt.py` is the older copy. CLOSED LISTS moved during this map (#1755
  round 6, +2 lines: the `size N <unit>` candidate shape), so v178 is no longer the current CLOSED LISTS text; fold
  from the module constants at the head being built, not from v178. The plan's ask a29454970 (where the template
  lives, the CHAT-STATE hand-over, the #1755 prompt freeze) is still open.
- B4 (drift test): the template must use the registry variables for the 7 literal lists or record them kept
  literal (section 5.2), or `test_prompt_dynamic_drift.py` fails once an F1 version is published into a DB that
  holds a wording-layer row (a migration-seeded publish would be).
- B5 (R-DOM-QTY source): no schema or registry field says which domains take a quantity, so "derived from the
  schema" is a 3-item sentence (stock, incoming, order) in R-P1-03 (DOM-QTY); a registry column is the later home.
  `stock_availability_only` contacts lose the regex: check that such a contact never holds an incoming or order
  answer, or add the C1 shape for that profile to gold.
- B6 (code readers to check before grading): `correction` on the stock path (C14), the detail-offer refine paths
  that key on a null domain_hint (C5), and `reference_target` readers (`answer_bridge.py:1481`,
  `lanes/business/answer.py:1996`) once the dead REFERENCE TARGET text is gone (they then always see null, as today).
- B7 (state gate under the template): see 5.1. The red tests do not require the state heading in TEMPLATE; P1
  only works when `state_block` is on. Decide: heading line in the template (simplest, no code) or `template`
  implies `state_block` in `resolve_config`.
