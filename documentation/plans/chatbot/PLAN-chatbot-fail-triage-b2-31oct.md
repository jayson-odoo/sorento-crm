# PLAN: chatbot failure triage, batch 2 (31 Oct 2026)

**Status:** Build. Feature track M, lead pattern (tester red -> coder -> reviewer + security-reviewer). Parser candidate
E, md5 e90461ef, PASSED crew's hidden gate 31 Oct and is pinned: `PROMPT-fail-triage-b2-e90461ef.patch` rebuilds it from
production md5 57d7d412; no further prompt edit without a new gate. Owner answered Q1-Q4 on 31 Oct; publishing waits for the
owner's review of the text and #2018. AC-5 and the no-variant reply in build. Batch 1 is PR #2018 (lane CHATBOT-FAIL-TRIAGE). Parent plan and
UAC: `PLAN-chatbot-fail-triage-30oct.md`, `chatbot-fail-triage-acceptance-criteria.md` (Batch 2 + AC-7f + R1), copied
unchanged so they merge cleanly with #2018.

Hidden gate on E (crew, x2, USD 0.72): whole-parse A 181/226 = E 181/226; `suggested_team` non-null A 102, 101, E 105, 107
(D was 84, 86); per-field within noise. Crew notes two to look at, texts sealed from the lane: 1 stable multi-field loss on
a follow-up pick (picked_option + answers_open_question + products), and 3 rows where E always sets a team and A never does.

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

## Owner answers, 31 Oct ~08:40 (supersede the AC-5 table above and the card's Q1-Q3)

- Q1 (a), decided in code, but: end users and staff with no purchase cost permission keep "not allowed to access purchase
  cost". Dealer vs staff is the contact's TAG, not the access level: both hold the same levels.
- AC-5 output: the dealer cost is not really stored, it is in the PDF. A dealer's "my cost" gets the product's live dealer
  promotions through the EXISTING promotion lookup and presentation, links included, no `dealer_cost` number. The dealer
  opens the promotion to work out the cost. E1 and Q2c fall away.
- Q2 (b) follow `serving_policy`, unified with promotions. Q2b (a) no-date promotions are live, same logic.
- Q3: AC-6 parser side is the glued case only (measured); no new wording, reuse the existing "not found" clause.
- Q4 (a): owner gets text + md5 + edit list and reviews it before pasting into prod.

Tag evidence (`sorento_prod_1028`, aggregates): dealers = Sorento Dealer Brand 215, Sorento Mocha Dealer Tag 112, Mocha
Dealer Tag 32. Staff = Office Staff 58, Project Salesperson 16, Retail Salesperson 15, Admin 1. Untagged 49. No contact
holds both. Purchase cost reveal: 0 of the 359 dealers. 145 of the 359 dealers hold only the `end_user` level, so through
the existing lookup they see end-user promotions, or none: a known consequence of "use our existing logic".

Lead decision, filed with crew: a dealer is a contact with an active tag whose `settings.chatbot.tier` is `dealer`, read the
way `contact_llm_choice.py:36` reads the model. No word match on tag names, no migration. The owner or crew sets the tier on
the 3 tags once; until then every dealer gets today's denial, so it fails safe. Do not press Apply on those tags.

Size no variant holds: the existing "None with size 300mm" clause (`lanes/business/answer.py:3098`), then today's variants.

## Prompt edits (one version, base = production text, F1)

Candidate E, md5 e90461ef (production md5 57d7d412 + the four edits below in their final wording + P5), text kept with crew
at `crew/state/eval/fail-triage-b2/texts/E.txt`. Assumes Q1 = (a). Hidden result on the earlier D (crew, 113 rows, A x2 vs
D x2): whole-parse OK (A 91, 90; D 91, 93), but `suggested_team` non-null fell from 102, 101 to 84, 86, a real regression;
crew ruled not to rely on #2018's fallback. So D is replaced, and the "Known risk" note below is superseded.

- P5 end of the `== ROUTING ==` map: a `domain_hint` from the map always fills both, on every ask; a plain stock, order or
  product question is a routing signal. `suggested_team` non-null on 17 sensitive TRAIN rows x3: E 51/51, production 31/34.
  This is above production's rate, a behaviour change: on 23 TRAIN rows where production had no team, E sets one on 9, all
  with a domain; 0 of 7 null-domain rows.
- P2 final form uses an arrow example, not a JSON object. The JSON form lost routing (32/51); prose with no example kept it
  (44/51) but glued fell to 1/5; arrow alone with the other edits lost it again (28/51) until P5. Glued on E: 13/15.
- Gold on E: 35/36 (miss: glued `SRTKS1248300MM`). E has no full TRAIN arm; hidden is the full whole-parse measure.

- P1 `== LAST PURCHASE COST ==`: the asker's own cost ("my cost", "dealer cost", "costing", any language) is this same ask.
  Dropped once after 8/8 cost rows on one production run, restored when 2 of them flipped on the next text: the reading was
  not stable. 8/8 twice with the line.
- P2 new line after `A BARE FAMILY CODE`: a size stuck on a code's end is two entities, code + reserved `size`, even with
  no candidate line; the specification rule gets the one exception (F7). Dash and space forms already parse right on
  production, because the `Size` candidate line exists for them; only the glued form was failing.
- P3 end of `== ROUTING ==`: a named team decides over the domain map; exactly one team maps to the enum, several or none
  emit the user's own word, lowercased, agent null (`head/parser.py:410-428` already documents this).
- P4 `portal_link` domain line gains "price tag request"; `portal_form` joins the IN ADDITION keys with five forms (F2).
  Measured wider than R1: on production `portal_form` is null even for "link for complaint form". The first, larger P4
  (a sentence on the domain line + a key inside the OUTPUT object) was the drag in the bisect and was cut.

## Gate (crew answers 31 Oct: USD 2.60 for this gate, DB `sorento_prod_1020` read-only and rolled back, version 2247a9af)

Harness outside the repo at `crew/state/eval/fail-triage-b2`: gemini-3.5-flash-lite, span extractor v1, startup check
refuses unless the connection is read-only. Crew runs the hidden split on the arm handed over; hidden stays sealed here.

| Run | Text | Result | USD |
|---|---|---|---|
| Arm A, TRAIN 118 | 57d7d412 | 118 of 118 ran, baseline | 0.3774 |
| Gold 32 | 57d7d412 | 17/32 | 0.0949 |
| Gold 32, first draft | 85c286c4 | 26/32: team, portal, cost all pass | 0.0940 |
| Gold 7 glued + negatives | 59146557 | 6/7, glued 4/5, no-unit and exact-code negatives hold | 0.0221 |
| TRAIN 118, first candidates | 59146557, 79f41411 | 96, 92; replaced | 0.7394 |
| Bisect, 34 volatile rows: A x2, P3, P4, P2 x1 each | single edits | pass A 21, 18; P3 20; P4 14; P2 20 | 0.5567 |
| Gold portal + team, size + cost | 129b08cb (C) | 13/14; 20/22 (size 14/14, 2 cost rows flipped) | 0.1110 |
| C on 34 rows; C on 84, stopped after 3 rows | 129b08cb | 18/34; replaced by D | 0.1134 |
| Gold cost x2 | 11c870e6 (D) | 8/8, 8/8 | 0.0488 |
| TRAIN 118 | 11c870e6 (D) | 95/118 | 0.3773 |

Read: A scores 99, 98 and 95 on TRAIN (one full run + two repeats of the 34 volatile rows), so 99 was a lucky baseline and D
sits at A's floor, not above it. The other 84 rows do not flip in any arm (77). Of the rows A got right in all 3 runs D
loses only G112 ("request pricetag"), whose gold predates owner Q5. Size, portal and team gold were not re-run on D's exact
text. The hidden split is crew's; it is the bar, not this table.

Known risk: on the 34 volatile rows `suggested_team` is non-null on 16 with D against 23-27 for A (other 84: 70 = 70).
Whole-parse does not score routing, and no single edit is clearly the cause. #2018's `_route_pair` draws from the turn's
domain when the parser gives no team, so this version is published only after #2018 merges; not yet run end to end.

`sorento_prod_1020` alembic_version is `adp_0001_pcs_attach_delete`, not head `sfq_0001_sample_request_source`; crew
migrates lane schema into it by SQL, and the columns the parser reads are present. Embedder dry: ~10.7% of vector lookups
miss, in every arm alike.

## Code slices

- S1 AC-6 done: `narrow_code_tokens_by_specs` honours `any_keys` (c71a780945). The no-variant reply waits on Q3.
- S2 AC-5: the grant-gate split, in-process dealer cost read, reply wording, MS + ZH in `label_catalog.py`. Waits on Q1, Q2.
- S3 prompt text, gold rows `scripts/chatbot_eval/gold/parser_fail_triage_b2.jsonl`, grader keys done; TRAIN done; hidden with crew.

## Decisions (lead)

- D1 B2 stays based on origin/main. Parser gate and S1, S2 need no #2018 code. R1 and AC-7f end to end do: the console pass
  and hand test run after #2018 merges and main is merged in. Until then a price tag link ask gets #2018's honest text.
- D2 Plan and UAC copies stay byte-identical to #2018's; B2 notes live in this file only.

## Open questions

Filed as one `crew report --ask`, see the behaviour card. Answers recorded here when relayed.
