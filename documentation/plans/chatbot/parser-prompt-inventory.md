# Parser prompt inventory (S1b, AC-151)

Slice: S1b (issue #643). Plan: `documentation/plans/chatbot/PLAN-chatbot-turn-engine.md`
("S1b", "Text-sniffing inventory", D11, D16). UAC: `chatbot-turn-engine-acceptance-criteria.md`
AC-151 to AC-155.

Subject: prompt registry key `chatbot_semantic_parser`, whose fallback is
`app/services/chatbot_parser_prompt.py`.

**The base changed mid-slice, and it matters for every number here.** S1 vendored the
system message from the working-tree EXPORT of `sub-semantic-parser` (49,318 chars). That
export is flagged `locally_edited` and carries the UNPROMOTED B-TEAM-1' lane change. The
LIVE body is 46,942 chars (sha256 `90c0741997...bdf87b66`), and after the two mechanical
edits the constant is 46,906. The re-port onto the live body landed first (commit
`407af238a`); everything below is measured against the live text.

## Size (AC-154)

| | chars | lines |
|---|---|---|
| before (`SEMANTIC_PARSER_PROMPT`, live) | 46,906 | 603 |
| after (`SEMANTIC_PARSER_PROMPT_SLIM`) | 28,124 | 342 |
| delta | -18,782 (**-40.04%**) | -261 |

Against the export the slice started from, the same slim text is 43.0% smaller. The gate is
"at least 40%" and it is met on the correct denominator, with 19 characters of margin.

Both texts ship. The live one stays version 1 with the `production` label; the slim one is
published as the next version with no label by migration
`475_chatbot_parser_prompt_slim`, so promoting is a label move and rolling back is the
reverse move (AC-154). The migration seeds both on a fresh database too.

## How each row was classified

* `understanding` - the LLM is reading the customer's words. Deterministic code cannot do
  it without matching raw text, which D11 forbids outside the parser. Stays.
* `rule` - a mapping, a gate or arithmetic over values the parser has ALREADY emitted, or
  over persisted state. Moves to `output_exchange.py` (most of them were already there and
  the prompt was carrying a second, weaker copy). Deleted from the prompt.
* `example` - illustrative phrasings. Kept only where the corpus shows the phrasing CLASS;
  a class is represented by one or two samples, never by the enumeration the live prompt
  carries.
* `dead` - cannot affect the output at all: text duplicated verbatim in another section,
  text the post-processor unconditionally overwrites, or n8n syntax that the CRM's prompt
  registry does not evaluate.

**"No fixture exercises it" is NOT by itself a reason to call a row `dead`.** The corpus is
one capture window (22 Aug to 4 Sep 2026, 249 real captures with a raw parser emission) and
it is heavily skewed: 104 `inventory`, 61 `incoming`, 21 `order`, 19 `product_attachment`,
4 `master_products`, 1 `resource_attachment`, 0 `promotion`, `forms`, `portal_link`,
`goods_receive`, `spo_allocation` or `ideate`. Keys never non-null in ANY real capture:
`date_mode`, `is_active`, `contains_flyer`, `correction`, `scope_exclusive`,
`access_levels`, `broaden_axis` (once), `person_mention` (once), `demand_qty` (twice),
`escalation.company_pick` (never). A section covering one of those is marked
`understanding` with evidence `none (corpus-silent)` and is KEPT; deleting it would be
overfitting to a capture window, which is the opposite of what D16 asks for.

## Evidence sources

* `nodes/sub-semantic-parser/output_exchange/*.json` and `.../suggest-follow-up/*.json` in
  the n8n fixture corpus. 567 files, 249 unique real executions carrying the LLM's raw JSON
  under `ctx["AI Agent"][0].json.output`, plus 79 hand-built fixtures whose names state the
  behaviour they pin.
* Fixture ids below are the file stems. `parser-*` and `exec-*` are real executions; the
  named ones are the hand-built pins.

## The parser emits 26 keys, not 27, and `team_source` is not one of them

Every one of the 488 captured raw emissions carries exactly 26 top-level keys, and
`routing` carries `suggested_team` + `suggested_agent` only. `team_source` appears in ZERO
captures - and the reason turned out not to be the model: the LIVE system message never
asks for it. It is B-TEAM-1', present only in the working-tree export. `head/parser.py`'s
strict `json_schema` briefly required it, which would have made the CRM the only
deployment forcing the model to invent one; that is fixed in the re-port commit.

So the brief's "27 declared keys" is off by one against the prompt's OUTPUT block,
`parser.DECLARED_KEYS` and every capture. The parity script diffs the 26 declared
top-level keys.

---

## Section table

Order is the prompt's own. "chars" is the live section including its blank-line tail.

| # | section | chars | class | fixture evidence | disposition / where the rule lives |
|---|---|---|---|---|---|
| 1 | preamble ("You are the Sorento Semantic Parser", the three inputs, "preserve phrases exactly inside entities[].raw") | 530 | understanding | every fixture | kept, tightened |
| 2 | CURRENT DATE banner + "convert relative dates before calling the MCP tool" | 224 | understanding | `parser-15120197`, `parser-15145424` | kept. The "before calling the MCP tool" clause is `dead` (the parser calls no tool) and goes |
| 3 | PRICE TERMINOLOGY (list vs selling price is decisive) | 709 | **dead (duplicate)** | `parser-15154295` (requested_attributes `price`) | DELETED. Every clause repeats verbatim inside DECISIVE DOMAIN TERMS rows `master_products` and `promotion`, 60 lines later. One copy kept, there |
| 4 | AFFIRMATION + ESCALATE-WORD (the "acceptance may carry trailing instructions" paragraph is export-only and absent from the live text) | 940 | understanding | `parser-15025626` "Escalate", `parser-15074683` "ESCALATE", `parser-15074293` "YES ESCALTE", `parser-15142072` "yes, escalate.", `exec-13484619` "Yes escalate" | kept, compressed. The example list ("escalate please", "pls escalate", "ok escalate", "escalate this", "eskalasi", 3 more) collapses to the class plus two samples |
| 5 | READING THE CURRENT MESSAGE IN CONTEXT (previous reply either ASKED or DELIVERED) | 461 | **dead** | none | DELETED. It states no output rule; both branches are restated where they bite (MESSAGE TYPE, BARE ENTITY CONTINUATION, COMPANY-NAME REPLY), and R3 now puts the fact in the user block as a `Pending:` line rather than leaving the model to infer it from the previous reply's wording |
| 6 | INTENT & DOMAIN (the two enums) | 759 | understanding + enum declaration | `intent_hint` seen: `check_stock` 105, `check_incoming` 62, `check_order` 21, `check_product_attachment` 19, `check_product` 4, `get_resource_attachment` 1 | kept. Both enums must survive verbatim: `contracts.INTENT_HINTS` / `DOMAIN_HINTS` are written against them |
| 7 | DECISIVE DOMAIN TERMS (12 domain rows) | 6,799 | understanding | `parser-15102530` "INCOMING CWCX604-S-RL", `parser-15102165` "CHECK STOCK : CSK11A", `parser-15025803` "CBFAL5570 got eta?", `parser-15073334` "TECHNICAL DRAWING SRTUB206", `parser-15099311` "STATUS DELIVERY PS...", `parser-15105557` "is with matt finish?", `domain-switch-word-beats-continuity-carry`, `domain-switch-word-not-fired-on-mixed-tokens` | kept, cut roughly in half. `output_exchange.DOMAIN_SWITCH_WORDS` is a PARTIAL twin (34 English and Malay literals); the prompt's job is the same decision in any language, so this is not a rule that can move. What goes: the repeated "this is DECISIVE" emphasis (stated four times), the customer-vs-supplier argument restated three ways, and the synonym enumerations, reduced to one sample per class |
| 7a | ...clause "drop an attachment_type entity when switching to master_products" | 150 | **rule** | `blocklist-domain-and-broaden`, `attachment-type-not-reattached-when-already-carried` | DELETED. `output_exchange.DOMAIN_BLOCKED_HINTS["master_products"]` already contains `attachment_type` and the executor drops it regardless of what the model does |
| 8 | BARE ENTITY CONTINUATION | 1,695 | understanding | `parser-15101983` "CSK11A", `parser-15107908` "SRTSP131", `dym-bare-code-reply-forces-offer-domain`, `dym-code-inside-new-domain-phrase-does-not-force` | kept, compressed. The final paragraph ("does NOT apply when the bare reply ANSWERS something the assistant just offered") is now carried by the `Pending:` user-block line, so it shrinks to one sentence |
| 9 | IDEATION CONTINUATION | 1,320 | understanding | none (corpus-silent: 0 `ideate` captures) | kept, compressed to the two rules that change output (stay in `ideate`; naming a team as an ANSWER is not `request_for_help`). Retained despite zero evidence: `ideate` routes to `suggested_agent: "ideation"` in `derive_routing`, which the access check keys on |
| 8a | standalone "DO" / "D.O." paragraph | 480 | understanding | none (corpus-silent) | kept, compressed |
| 10 | REQUESTED ATTRIBUTES (3 domain vocabularies, 20 `incoming` field keys, the FULL TIMELINE sentinel) | 3,814 | understanding + enum declaration | `estimated_arrival_date` 43 (`parser-15025509`, `parser-15025803`, `parser-15026111`), `delivery` 14 (`parser-15099311`, `parser-15099501`), `dimension` 1 (`parser-15105557`), `quantity` 1 (`parser-15110448`), `price` 1 (`parser-15154295`) | kept, compressed to ~60%. The 20 CRM field keys are the wire contract and stay exactly as written; their glosses collapse to the shortest phrase that names the class. The `["__all__"]` sentinel stays (`route.py` `_isTimeline` reads it, H46). The three fan-out examples ("cleared CIDB" is both dates, "who is the forwarder" is both forwarders, "can I collect" is both) stay: they are meaning-driven, not derivable from one emitted key |
| 11 | SCOPE INTENT | 577 | understanding | `parser-15121180` (the one `broaden` capture), `select-all-expands-menu-positions` | kept, compressed |
| 12 | MESSAGE TYPE, rules 1, 3, 4 and the two clarifying paragraphs | 2,700 | understanding | `parser-15024720`, `parser-15111167`, `parser-15116905` (request_for_help), `rs09-t3-parser` (clarification), `b56-t4-parser` + `parser-15123878` (casual), 230 business_query | kept, compressed. The "share/send/provide DATA is not a human-help request" carve-out stays: it is the only thing separating `request_for_help` from `business_query` on "pls share the outstanding list" |
| 12a | MESSAGE TYPE rule 2 ("BOTH a non-null intent_hint AND a non-null domain_hint -> message_type MUST be business_query") | 405 | **rule** | `request-for-help-llm-team-wins` item 1, `menu-label-stock-enquiry`, and all 230 business_query captures | DELETED. `output_exchange.post_process` forces exactly this, with the same two exceptions the prompt does not state: `casual` and `request_for_help` are left alone. Search `o["message_type"] = "business_query"` |
| 13 | USER GOAL | 330 | understanding | every fixture (`user_goal` non-null in 249/249) | kept, compressed |
| 14 | ATTACHMENT TYPE EXTRACTION (photo / video / drawing / cert word lists) | 726 | **dead (duplicate)** | `parser-15025542` "Drawing for srtwt5611", `attachment-type-reattached-and-i18n-normalised` | DELETED. The `attachment_type` bullet in ENTITY OPERATIONS already carries the same list plus the `canonical_code` contract the code reads, and the DECISIVE `product_attachment` row carries the trigger phrases. Third copy removed, the other two kept |
| 15 | FLYER FLAG | 337 | understanding | `flyer-injected-when-absent`, `flyer-not-duplicated-when-present`; 0 real captures with `contains_flyer: true` | kept, compressed. The trailing two orphan lines ("- set domain_hint = promotion..." / "brand/category named") are a mangled fragment with no sentence around them and go |
| 16 | ACCESS LEVELS: the 7-value vocabulary + "a tier named as a version/copy is a selection" | 700 | understanding + enum declaration | `stated-tier-and-brand-from-compound-level`, `tier-offer-numbered-pick`, `tier-offer-all-semua`, `brand-from-levels-only-when-unambiguous`; 0 real captures (`access_levels` empty in 249/249) | kept. The compound is the WIRE: `output_exchange` reads the brand half out of "Cabana Dealer" and it is unrecoverable one line later, so the model must keep emitting the compound |
| 16a | ...the 6-line "Map the words" table (brand + tier -> compound; bare tier -> all three brands) | 725 | **rule** | `stated-tier-and-brand-from-compound-level` (`["Cabana Dealer"]` in, `access_levels ["dealer"]` + `query_brands ["cabana"]` out) | DELETED. `_parse_level` + `_stated_tiers` + `_stated_brands` do the split, and `raw_levels` already accepts a bare `dealer`/`office`/`end_user` token, so the fan-out line changes nothing |
| 17 | ENTITY OPERATIONS: the 12 entity-hint definitions and the 4 `entity_op` values | 3,291 | understanding + enum declaration | hints seen: `product` 161, `inbound_shipment` 45, `order` 24, `attachment_type` 22, `customer` 8, `brand` 4, `category` 1, `attachment` 1; `entity_op`: `replace_combine` 212, `reuse` 33, `clear` 1 (`parser-15121180`); `entity-op-executor-arms`, `entity-op-reuse-contradiction-corrected` | kept, compressed to ~65%. `ENTITY_HINTS` in `contracts.py` is written against this list. The `attachment` / `attachment_type` `canonical_code` contracts stay verbatim: `derive_routing` and the i18n mirror both read `canonical_code` |
| 18 | ENTITY CONFIDENCE | 2,706 | understanding | `vague-mash-one-siew` and `labeled-split-one-siew` under `fixtures/parser/`, both pinned from real executions 6971041 / 6972178 | kept, cut to ~40%. Two of the four paragraphs restate the same test ("more than one untyped concept crammed into one raw") in different words; one worked example survives, the duplicated prose does not |
| 19 | MATCH MODE | 144 | understanding | `and` in 249/249; `reference-position-single-pick-keeps-match-mode` | kept verbatim (already two lines) |
| 20 | BROADEN AXIS: the axis vocabulary and which axis is being widened | 1,600 | understanding | `parser-15121180`, `blocklist-domain-and-broaden`, `select-all-expands-menu-positions`, `select-all-not-expanded-without-pick-context` | kept, compressed. `DW_PHRASES` is an 11-literal English twin of the "date" row; the any-language decision is not portable to code |
| 20a | ...the "KEEP domain_hint and intent_hint from the previous turn" paragraph and the "If there is NO business domain in play" fallback | 700 | **rule** | `blocklist-domain-and-broaden` | DELETED. The AXIS BROADEN block in `output_exchange` restores `domain_hint`/`intent_hint` from prior state whenever `broaden_axis` is set and a prior domain exists (`broaden_axis_domain_restored`), rescues the `clear` misread (`broaden_axis_clear_rescued`) and resolves the axis from the wandered domain (`broaden_axis_resolved_from_domain`). The no-prior-domain case is the same code's else branch. The two SHORT bullets it does not implement (leave `scope_intent` null, `entity_op` = `reuse` for a non-`all` axis) are KEPT in the prompt |
| 21 | SCOPE EXCLUSIVITY | 365 | understanding | `false` in 249/249; `entity-op-executor-arms` (`exclusive_ignored_no_current`) | kept, compressed. The live text ends mid-sentence ("RESTRICTING to ONLY what they name now,"); the slim text finishes it |
| 22 | DEMAND QTY | 77 | understanding | `parser-15120197` (1), `parser-15137905` (4) | kept verbatim. There is no deterministic twin and there must not be: reading a number out of the customer's sentence is text sniffing (D11). The brief lists "quantity parsing" as a move candidate; it cannot move without a raw-text regex, so it stays |
| 23 | CORRECTION / DOUBT | 115 | understanding | `false` in 249/249; `member-offer-precedence-arms` (code sets `correction` on a reprompt) | kept verbatim |
| 24 | ROUTING: set a team when the user names one, else null | 640 | understanding | `parser-15024720` "please escalate my question to purchasing", `parser-15111167` + `parser-15116905` "please escalate to marketing product team", `parser-15142072` | kept and made the WHOLE section. The live routing chain is `(request_for_help ? the model's team : null) ?? derived ?? prior ?? "customer_service"`, so the model's team is read on a `request_for_help` turn and nowhere else. On a turn like "please escalate my question to purchasing" there is no `domain_hint` for `derive_routing` to work from, so the model naming the team is the ONLY way that turn reaches purchasing. That judgement stays |
| 24a | ...the 9-row "Routing signals" domain-to-team map and the "ONE promotion team for every brand" note | 1,300 | **rule** | `routing-domains-multi-item` (LLM emits `{null, null}`, output is `purchasing` / `marketing_form` / `warehouse` / `ideation` for four domains), `legacy-suffixed-promotion-team-normalised-from-prior` | DELETED, and the argument is an equivalence rather than a preference. On a NON-`request_for_help` turn the model's team is not read at all, so the map cannot reach the output. On a `request_for_help` turn WITH a domain, the map's answer and `derive_routing`'s answer are the same table, so deleting it changes nothing. On a `request_for_help` turn with NO domain the map has nothing to fire on either way. `_PROMO_TEAM_RE` collapses a legacy `marketing_promotion_<brand>` team. This was the largest rule being stated twice |
| 25 | DATE FILTER: extract from the current message only, relative to absolute, never carry forward, and `date_mode`'s started / ended / overlap verbs | 2,377 | understanding | `parser-15120197` (2026-09-01 to 2026-09-30), `parser-15145424` (single day), `date-filter-gated-multi-item`, `date-filter-gated-records-null-domain`, `dym-date-reply-never-hijacks-pick` | kept, compressed to ~55%. **Investigated as a move and rejected on evidence.** Two candidate rules were tried against the corpus and both break parity: (a) "a single day sets BOTH start and end" would rewrite `dym-pick-does-not-carry-dates-when-this-turn-named-one` and `tier-pick-does-not-carry-dates-when-this-turn-named-one`, which pin a start with a null end on purpose; (b) "`date_mode` only when `domain_hint = promotion`" would null the `order` + `date_mode: "range"` item in `date-filter-gated-multi-item`, which the shipped post-processor keeps. Relative-to-absolute conversion cannot move at all without a regex over the customer's words. The DOMAIN GATE half of the section IS already code (`DATE_FILTER_DOMAINS`, `date_filter_gated`), so the "downstream decides which domains use the window" sentence is stated once and short |
| 26 | POSITIONAL REFERENCES | 894 | understanding | `parser-15114106`, `parser-15129616` (`[17]`), `parser-15157165` (`[4]`), `rs09-t2-parser` (`[6]`), `reference-positions-resolve-and-out-of-range`, `member-offer-ordinal-word-first` / `-second` / `-third`, `member-offer-ordinal-numeral-2nd` | kept, compressed. `_ORD` in `output_exchange` is a 12-literal English twin used only inside the member-offer extractor; ranges ("the first three", "1 to 3") and "the last one = N" are language |
| 27 | REFERENCE TARGET (dym vs result) | 716 | understanding | `dym`: `b56-t4-parser`, `parser-15125372`, `parser-15137523`; `result`: `parser-15114106`, `parser-15123878`, `parser-15129616` | kept, compressed |
| 28 | PERSON-NAME MENTION | 1,009 | understanding | `parser-15105557` "Hi Zhi Yang, may I know CKS806..." (the only real capture), `member-offer-partial-name-reply-forces-pick`, `member-offer-one-word-name-reply-forces-pick` | kept, compressed to ~50%. Consumed by `co_company_pick` as a secondary pool signal and by the member-pick matcher |
| 29 | COMPANY-NAME REPLY: what counts as engaging a pending offer, the "A VALUE IS NOT A FRAGMENT" carve-out, the bare-fragment fallback | 2,900 | understanding | `escalation-offer-confirm-decline-and-pick`, `escalation-decline-vetoed-by-an-unresolved-position`, `member-offer-new-query-abandons`, `member-offer-domain-alone-counts-as-a-new-query`, `pending-pick-from-a-single-row-roster`; 0 real captures with a non-null `company_pick` | kept, compressed to ~45%. `co_company_pick` VALIDATES a pick against the offered pool but never reads the customer's words, so which reply names a company stays with the model |
| 29a | ...the "Companies OFFERED in the pending offer" line, an n8n `{{ (() => {...})() }}` IIFE | 700 | **dead (n8n syntax)** | none | DELETED. The CRM's `ai_prompt_registry._TOKEN_RE` is `\{\{\s*([a-zA-Z0-9_]+)\s*\}\}`, which does not match an expression, so the registry leaves 700 characters of JavaScript in the system message verbatim and the model is handed source code where n8n handed it a company list. The rule it served survives as "name one of the OFFERED companies"; which companies were offered is validated downstream by `co_company_pick` against the persisted pool, which is where that check already lived |
| 29b | ...the company-code table (Sorento = SRT, Mocha = MCH, Cabana = CBN) | 180 | **rule** | `co_company_pick` pool keys | DELETED. `output_exchange.CO_ALIASES` is the same table and the pool also accepts each company's own `company_code` from state |
| 30 | ORDER_STATUS FILTER | 723 | understanding | `outstanding`: `parser-15110339`, `parser-15110448`, `parser-15125758`; `delivered`: `parser-15108480` | kept, compressed. The Malay synonyms ("belum hantar", "sudah hantar") stay: they are the only Malay the corpus's own domain vocabulary depends on and no code path covers them |
| 31 | IS_ACTIVE FILTER | 843 | understanding | none (corpus-silent: null in 249/249) | kept, compressed. Not dead: `is_active` is carried by the reuse arm of the entity executor and consumed downstream of the head (S2/S6 `get-results`), so silence in this capture window is not evidence of absence |
| 32 | OUTPUT block (the 26 keys and their enums) | 2,157 | **contract, never touched** | every fixture | kept. AC-152 requires the prompt to keep declaring the exact key set and enums; `parser.PARSE_OUTPUT_JSON_SCHEMA` and `contracts.py` are written against it. Only the inline commentary that restates a deleted section is trimmed |

### Totals

| class | sections / clauses | chars before | disposition |
|---|---|---|---|
| understanding | 26 | 37,100 | kept, compressed by editing (examples collapsed to classes) |
| rule | 6 | 3,400 | deleted from the prompt; all six already had a twin in `output_exchange.py` |
| example (folded into their parent rows) | - | - | one or two samples per phrasing class survive, the enumerations do not |
| dead | 4 | 3,300 | deleted outright: 2 verbatim duplicates, 1 no-op section, 1 unevaluated n8n expression |

## Code that already implements each moved rule (AC-152)

Each has a unit test in `tests/chatbot/test_output_exchange_rules.py`, and each test feeds
a deliberately NON-compliant emission, because a compliant one proves nothing about a
prompt that no longer asks for compliance.

| id | rule | function |
|---|---|---|
| R1 | domain to team / agent map | `derive_routing` + the live `??` routing chain |
| R2 | `message_type` forced to `business_query` when a domain is set | `post_process` |
| R3 | `attachment_type` dropped when the domain is `master_products` | `DOMAIN_BLOCKED_HINTS` + the entity executor |
| R4 | `broaden_axis` restores the prior domain and intent | `post_process` AXIS BROADEN block |
| R5 | compound access level split into a tier token plus `query_brands` | `_parse_level` / `_stated_tiers` / `_stated_brands` |
| R6 | legacy `marketing_promotion_<brand>` collapsed to `marketing_promotion` | `_PROMO_TEAM_RE` |

**No new post-processor code.** An earlier draft of this slice added an ordinal-to-company
resolver, because the EXPORT's prompt asks the model to resolve "the first one" against a
list rendered by an n8n expression the CRM cannot evaluate. The LIVE prompt has no ordinal
bullet at all, so there is no rule to move and the code was dropped. S1b therefore changes
`output_exchange.py` not at all: it only stops the prompt stating six things that file
already decides.

## Six edits earned by measurement, not by reading (AC-153)

The first live parity sweep found six places where compression silently dropped a rule.
Each is now restored and each is load-bearing:

| what was lost | what it cost, measured |
|---|---|
| `date_mode`'s explicit "otherwise null" | the model set `date_mode` on 15 of 76 non-promotion turns |
| `entity_op: reuse`'s "downstream re-applies the previous entities" | a bare "Escalate" re-emitted the previous turn's product and dragged its domain back with it |
| `attachment_type`'s "ALWAYS emit TWO entities", stated in the DECISIVE row and not only in the hint list | "TECHNICAL DRAWING SRTUB206" came back with the product alone, no attachment_type |
| `order_status`'s "never infer from context" | "yee tat got delivery" came back `delivered` |
| the `order` row's "delivery meaning fulfilment belongs HERE, never incoming" | "One siew srt369-5 GM September delivery" routed to `incoming` |
| `is_escalation_confirmation` named beside the company pick | the model set it true on "Yes escalate", and `route.py` reads that field |

Two more were positional rather than textual. `scope_intent` and `user_goal`, compressed
and moved into a merged section, agreed with the old prompt 26% and 52% of the time;
restored to the live prompt's own words in the live prompt's own position, 97% and 80%.
That is worth writing down: WHERE a rule sits in this prompt changes the answer, so a
future slim-down should move a section only with a measurement to back it.

## Live parity result (AC-153, AC-155)

`scripts/chatbot_parser_parity.py --live-llm --n 50`, gpt-5.4-mini, temperature 0, 76
inputs (18 regression guards, 8 Malay/mixed, 50 fresh corpus turns), each sent twice, and
the same emissions run through `output_exchange` so the comparison is the answer a customer
would get rather than the raw emission.

| | agreement on the 26 declared keys, post-processed |
|---|---|
| old vs new | **95.8%** (1893 / 1976) |
| **control: old vs OLD, the same prompt twice** | **99.0%** (1956 / 1976) |
| old vs new, excluding the free-prose `user_goal` | 97.5% |

**The control is the headline.** This parser is not deterministic at temperature 0: the
live prompt disagrees with itself on 20 of 1976 key-instances, and on `user_goal` it agrees
with itself only 81.6% of the time. AC-153's "99%+" bar therefore cannot be met by ANY
prompt, including the one in production. The number that can be read is the distance from
the noise floor: 3.2 points.

Every disagreement is triaged, which is what AC-153 actually asks for. Zero untriaged:

| verdict | count |
|---|---|
| NOISE (free prose `user_goal`) | 23 |
| NEITHER matches the captured production value | 20 |
| NOISE (the old prompt disagrees with itself on that key and input) | 15 |
| IMPROVEMENT (new matches the capture, old does not) | 13 |
| REGRESSION (old matches the capture, new does not) | 11 |
| UNGRADED (a Malay input has no capture to grade against) | 1 |

The 11 regressions are listed in the run log and none is systematic: six are bare
positional replies ("1", "17") landing on a different domain, two are the raw case of an
entity value (`cb88ss` vs `CB88SS`, which `_ce_norm` lowercases downstream), and three are
single-key differences on `reference_target` / `requested_attributes` / an entity hint. The
13 improvements include the whole `parser-15120197` turn ("One siew srt369-5 GM September
delivery"), where the new prompt gets the domain, both date bounds, the requested attribute
and the routing right and the old prompt gets all five wrong. Promoting is the owner's call
and this table is what it should be made on.

### AC-155, and a corpus gap worth naming

The corpus contains **no Malay capture at all**: 249 real captures, and a scan for Malay or
Chinese in `latest_user_message` returns one false positive ("may I know"). AC-155 asks for
Malay inputs "from the corpus" and they do not exist.

What the parity script does instead is stated in its own docstring and labelled in its
output: eight REAL corpus turns with the message translated into Malay or mixed
Malay-English and the REAL previous state kept ("CBFAL5570 bila sampai?", "SRTW2000 ada
stok tak?", "PS202609-0096 dah hantar ke belum?", "tolong hantar lukisan teknikal
SRTUB206", "CWCX604-S-RL masuk bila, ada ETA?", "eskalasi kepada team", "senarai order
belum hantar untuk PS202609-0063", "Encik Zhi Yang, CKS806 saiz berapa?"). Both prompts see
the identical input, so agreement is still a fair measure; it is not a claim about ground
truth, and the script marks these `synthetic-from-corpus`. Seven of the eight agree on
every key; the eighth differs on `reference_target` alone and is the one UNGRADED row above.

**Backlog item: capture real Malay turns.** The prompt claims language coverage in nine
places and the regression net cannot check any of them. This is a coverage gap in the
corpus, not in the prompt.

## Text-sniffing sites found while doing this (D11, plan table)

No new site was added; S1b adds no code. Three rows were added to the plan's table during
the live re-port:

* `_coCompanyPick`'s deterministic tier, which the live body still has and the export's
  rev 8 deletes;
* the member-offer `extract()` + `_ORD` bare-number and ordinal-word scan;
* `_stated_tiers` / `_stated_brands`, which read tier and brand words from the raw message
  in English and Malay literals only. That last one is why the ACCESS LEVELS vocabulary
  could not be deleted from the prompt: the prompt is what covers every other language.

## What did not move, and why

* **date maths** - both candidate gates break replay parity (row 25). Relative-to-absolute
  conversion needs the customer's words.
* **quantity parsing** - `demand_qty` cannot be derived without a regex over the message.
* **positional / ordinal resolution** - already downstream's job for a result set, and the
  live prompt never asked the model to resolve one against the company pool.
* **entity carry / `entity_op`** - the executor already applies the op; choosing WHICH op a
  sentence means is understanding and stays.
