# PLAN: chatbot failure triage, batch 2 (31 Oct 2026)

**Status:** Plan. Feature track M, lead pattern (tester red -> coder -> reviewer + security-reviewer). Behaviour card
filed with crew, build waits for the answers. Batch 1 is PR #2018 (lane CHATBOT-FAIL-TRIAGE). Parent plan and UAC:
`PLAN-chatbot-fail-triage-30oct.md`, `chatbot-fail-triage-acceptance-criteria.md` (Batch 2 + AC-7f + R1), copied
unchanged so they merge cleanly with #2018.

## Scope

AC-5 dealer cost, AC-6 code + size, AC-7f named team, R1 price tag form in the chat portal-form list. All prompt edits
ship as ONE parser version: eval gate, md5 pin, owner publishes. Global rule stays: never "Sorry, I am busy" or "ran
into a problem understanding".

## Facts that shape the plan

- F1 The production parser text is NOT `head/parser_template.py`. Production (`v69-spans.txt`, ledger v189 id 2247a9af,
  md5 57d7d412, 105,034 chars, 1,005 lines) has other sections; `parser_template.TEMPLATE` is 70,953 chars, md5 81a0d0de.
  `scripts/publish_parser_template.py` would publish the wrong lineage. Base for this version = the production text.
- F2 The production text has no `portal_form` rule at all (grep: 0 hits). The schema still carries the key
  (`head/parser.py:393`, required `:743`), so today's model emits it from the key name only. The addendum
  `alembic/data/chatbot_semantic_parser.portal-form.addendum.txt` is on the older lineage only (`devf_0001`).
- F3 `chatbot_profile.tier` was null on all 495 contacts in backup 1028 (parent plan, Data and method), so the parser's
  `Profile:` block (`head/parser.py:1275`) carries no audience and `is_staff_profile` (`turn/state.py:259`) is no use
  here. The contact's access levels are (`tier_gate.parse_level`, `lanes/business/tier_gate.py:42-47`:
  "Sorento Dealer" -> brand sorento, tier dealer; "End User" -> end_user).
- F4 `dealer_cost` leaves the backend today (`schemas/marketing.py:425`) but MCP strips it from every promotion product
  response for every caller (`sorento_crm_mcp/server.py:1024-1043`). Nothing in `app/services/chatbot` reads it.
- F5 `serving_policy=true` returns lines of expired promotions as `expired_but_usable` (`marketing_service.py:1546-1560`),
  so the existing promotion fetch is not "live today".
- F6 `narrow_code_tokens_by_specs` (`product_code_family.py:154-217`) never reads `any_keys`: a family head + `size` 200
  matches nothing, returns None, and the family stays a which-one pick. `ground_bare` (`head/bare_size.py:84-125`) reads
  only the parser's `spec_key` / `spec_value` / `spec_unit`, never the message.
- F7 The `Size ... any dimension` candidate line (`head/lookup_lists.py:760-819`) is built from the message; its number
  regex guards against eating code digits (`product_spec_search.py` `_QUANTITY_RE`), so a glued size offers no line, and
  the production specification rule allows "ONLY a key that a Spec candidates line names" (text line 781).
- F8 #2018 is not on main: `PORTAL_LINK_COPY` / `portal_submission_type` (`lanes/business/fetch.py:1640,1648`) and
  `portal_service.SUPPORTED_TYPES` (`portal_service.py:82`) lack `price_tag_request`, and AC-7c clarify is #2018's.

## ARCHITECTURE

1. Layer. AC-5: routing + code after the parser. AC-6: prompt + shared spec narrowing. AC-7f, R1: prompt.
2. Shared mechanism changed. `narrow_code_tokens_by_specs` honours `any_keys`, the OR rule `held_family.py:120-175`
   already uses, so every code-family + size ask narrows, not one shape. The grant gate reads a domain by who asks, the
   way `reads_customer_po_refs` (`turn/state.py:269`) reads "PO" by audience.
3. Other classes fixed (UNVERIFIED until measured). Code + any dimension for tanks, basins, mirrors; a size said beside a
   code with a space; the 39 customer denials of "cost price".
4. Special cases removed. The "not allowed to access purchase cost" reply stops reaching dealers and end users. No word
   list, no regex on the message, no parser domain rewrite.

## Behaviour card

### AC-5 dealer cost

Who asks decides what a cost ask means. The parser keeps one reading (`purchase_cost`); it gains "my cost", "dealer
cost", "costing" next to "cost price". The grant gate (`lanes/business/__init__.py:1917-1940`) then acts:

| Contact | Answer |
|---|---|
| holds `purchase_orders.cost` | supplier purchase cost, unchanged |
| no grant, holds a Dealer level, no Office level | dealer cost from live dealer promotions |
| no grant, End User | list price |
| no grant, anything else (Office without the reveal) | today's denial (`canned.py:87`) |

Read path: in-process, not MCP (F4 stays true for every other caller, no new external surface). `promotion_products` of
promotions with start <= today <= end, active, `access_levels` overlapping the contact's own Dealer codes, company scoped,
products already through the contact's brand-scoped resolver.

| Case | Real data (backup 1028) | Reply |
|---|---|---|
| one live promotion | UNVERIFIED example, query pending | "SRTWC8122 dealer cost: RM 123.00 (Promotion name, until 31 Dec 2026)" (shape only) |
| E1 in no live promotion | SRTKS1248, SRTWC8036-SH-200, SRTWT5828 | "SRTKS1248 is not in a current dealer promotion, so I have no dealer cost for it. Please ask your salesman." |
| E2 several live, different costs | 239 of 1,106 products | one line per promotion: name, dealer cost, end date |
| E3 only expired | CSS8811-GM, SRT1369-3-GY, SRTKS1035 | same as E1, an expired cost is never shown |
| E4 end user | | list price answer |
| E5 promotion not open to the contact's levels | | same as E1 |
| E6 line with a null dealer cost (`marketing_service.py:288-302`) | UNVERIFIED count | same as E1 |

### AC-6 code + size

| Message | Parser | Reply |
|---|---|---|
| SRTWC286200MM | product SRTWC286, `size` 200 mm | SRTWC286-SH-200 |
| srtwc286-200mm | same | SRTWC286-SH-200 |
| SRTWC286 250MM | product SRTWC286, `size` 250 mm | SRTWC286-SH |
| SRTWC286 300MM | product SRTWC286, `size` 300 mm | no variant holds it: see Q3 |
| SRTWC286200 (no unit) | stays one code | today's did-you-mean; digits alone may be a real code |

Data: `product_specifications` SRTWC286-SH trap_length 250, SRTWC286-SH-150 150, SRTWC286-SH-200 200. 264 replies, 94
contacts in the 30 days (C1c). `dimension_keys` (`product_spec_search.py:183`) reads every numeric mm key from the
registry, so trap length needs no naming. Two variants matching: stays a pick between those two.

### AC-7f named team, R1 price tag form

| Message | Parser | Result |
|---|---|---|
| "Please escalate to product marketing team" | `suggested_team` marketing_product | routes there |
| "escalate marketing" | `suggested_team` "marketing" (own word) | clarify among the marketing teams (`lanes/escalation.py:1222,1254`, already on main) |
| "give me link to request pricetag" | portal_link, `portal_form` price_tag_request | portal link on the price tag form (#2018 code) |

## Prompt edits (one version, base = production text, F1)

- P1 `== LAST PURCHASE COST ==` (line 553): add "my cost", "dealer cost", "costing".
- P2 `== THE specification ENTITY ==` (line 781): a size stuck to a code, or after it, is two entities: the code head as
  the product and reserved `size` with the number and its unit, with or without a candidate line (F7).
- P3 `== ROUTING ==` (line 265): a named team maps to the enum when it is exactly one team; when it maps to several or
  none, emit the user's own word, lowercased (`head/parser.py:410-428` already documents this).
- P4 new `== PORTAL FORM ==` section + `portal_form` output key, five forms (F2).

## Code slices

- S1 AC-6: `narrow_code_tokens_by_specs` honours `any_keys`; the no-variant reply (Q3).
- S2 AC-5: the grant-gate split, in-process dealer cost read, reply wording, MS + ZH in `label_catalog.py`.
- S3 prompt text P1-P4 + gold rows (fresh paraphrases included), gate.

## Decisions (lead)

- D1 B2 stays based on origin/main. Parser gate and S1, S2 need no #2018 code. R1 and AC-7f end to end do: the console pass
  and hand test run after #2018 merges and main is merged in. Until then a price tag link ask gets #2018's honest text.
- D2 Plan and UAC copies stay byte-identical to #2018's; B2 notes live in this file only.

## Open questions

Filed as one `crew report --ask`, see the behaviour card. Answers recorded here when relayed.
