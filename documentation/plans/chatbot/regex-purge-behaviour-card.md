# REGEX-PURGE behaviour card (step 1, no code)

Audit at origin/main b440c715e5. Paths are under `sorento_crm_backend/app/services/chatbot/`, `../` is
`app/services/`. Every file:line below was grepped at that commit. Risk is judgement from code comments and
PR history; no eval has run yet.

## Findings that change the brief

- **Bigger than size M.** About 45 sites in 21 rows, not 3. All of them in one PR is not reviewable and one
  gate could not say which change moved a row (arm A alone runs TRAIN 95-99). See Q1.
- **Nearly all of it is live on production text.** The parser text on crew's copy
  (`crew/state/eval/span-pass-prod/v69-spans.txt`, md5 57d7d412, noted as prod v189) has none of `== CLOSED LISTS ==`,
  `## Conversation state and state_changes`, `LANGUAGE_ASK`; it has `== LOOKUP SPANS ==`. So `state_gate` is off and
  every text rewriter in `engine.py:5726-5757` runs. UNVERIFIED against the live prod label (crew lanes do not read prod).
- **`head/candidates.py:444 _SIZE_RE` is dormant on production text.** The shortlist runs only
  `if parser_config.closed_lists` (`engine.py:5268-5280`). The live size reader is `head/lookup_lists.py:754 number_hits`.
- **#2030 is still open.** It edits `product_code_family.py` and `engine.py`, and adds no regex or word check over
  message text (grep of its added lines). Lines here shift when it merges; step 2 starts after that.
- `ESCALATION_TOPICS` (`lanes/escalation.py:96`, read `:887`): confirmed a label list for the clarify question. Keep.
- `_family_rows` (`../product_code_family.py:71`): Postgres match on product codes, data lookup. Keep.
- Clean: `agent/**` (regexes check the model's own answer), `lanes/casual.py` (its D11 header holds), `analytics/**`,
  `tail/**`, `composers/**`, `label_catalog.py` (own output only).

## Site table

Reads: RAW = customer message, GOAL = parser `user_goal`, VALUE = other parser text. Batch is the recommended order (Q1).

| # | Site | Reads | What it does | Parser field for the same meaning | Rec | Risk | Batch |
|---|---|---|---|---|---|---|---|
| 1 | `lanes/escalation.py:1343,1363,1369` `_TEAM_WORDS` `_NAMED_TEAM` `_named_teams`; `:1390,1398` `_ESCALATE_WORD` `asks_for_a_named_team`; stamped `turn_runtime.py:1661`; read `turn/apply.py:188` (veto `:208`, `:243`), `escalation.py:798,1297`, `turn_runtime.py:1809` | GOAL | Team word + escalate verb forces `request_for_help`, picks the team, blocks "yes" on an offer for another team | **New `escalation.named_team`** (slug, family word or null). `routing.suggested_team` cannot: also filled from the domain (`escalation.py:1376`) | replace | high | 1 |
| 2 | `turn_runtime.py:1696,1703,1714` `_CO_FILLERS` `_CO_NEGATORS` `company_pick` | RAW | Strips about 80 filler words, checks negators, matches company aliases. Parser only a fallback | `escalation.company_pick` (section on prod text) | replace | high | 1 |
| 3 | `../product_code_family.py:44,59,252` `_CODE_WORD` `_code_word_for` `narrow_code_tokens` | RAW (`lanes/business/resolve_gate.py:775`) | Finds a code word, narrows the family by words on its line, drops the parser's token | `entities[hint=specification]` through the existing twin `narrow_code_tokens_by_specs` (`:139`, reads no words) | replace | high | 1 |
| 4 | `turn/apply.py:735` `_DRILL_DOCUMENT_WORDS` | VALUE | Drops "do" / "delivery order" so the reply does not say "could not find DO" | `document` (`turn/decide.py:354`) | replace | med | 1 |
| 5 | `head/grounding.py:1153` `_category_word_under_documents` (`:903`) | GOAL | No document word in goal: rewrites domain `product_attachment` to `master_products` | `domain_hint`, `document` (a post-parse domain override) | remove | med | 1 |
| 6 | `head/lookup_lists.py:711` `normalise_number` | none | Dead code, only 2 tests call it | n/a | remove | low | 1 |
| 7 | `engine.py:426,469,823,831` `_BARE_POSITIONS` `_BARE_ALL` `_ORDINALS` `_QTY_OF_OPTION` (`:850`) | RAW | Number or "all" over an open list overrides the parser's pick | `open_question_answer`, `reference_positions` (section on prod text) | words replace, digits Q2 | high | 2 |
| 8 | `required_fields.py:68,85,86,276,455` word lists, `_from_pick`, `_reply_verdict_by_shape` | RAW | "all", "none", "cancel" or reply length settles a required field | `open_question_answer.mode`; other asks already use it | replace | med | 2 |
| 9 | `turn_runtime.py:1355,1364,1638` counts; `:1507,1553` clarify; `:4786,4791` brand offer | RAW | "show 10", "next 40", "I mean tap", "cabana" | `top_n`, `continuation`, `open_question_answer`, `entities[hint=brand]` | replace | med | 2 |
| 10 | `so_status.py:421,428,492,556,574,582,607` (`engine.py:6083-6121`) | RAW | "sales order", month words, fuzzy "outstanding" override document, status, dates | `document`, `status`, `order_status`, `date_filter_*` | replace after prompt fix | high | 2 |
| 11 | `order_list.py:38,46,68,81` | RAW | "all brands", "how about mocha" clears or switches the brand | `broaden_axis`, `entities[hint=brand]` | replace | med-high | 2 |
| 12 | `engine.py:518,524` `_ETA_WORDS` (dealers) | RAW | No ETA word and a number: flips the intent to stock | `intent_hint`, `domain_hint`, `demand_qty` | remove | med | 2 |
| 13 | `so_status.py:418,446` `_TYPED_SO_NUMBER_RE`; `engine.py:475` `_with_repeated_codes_summed` | RAW | Reads an identifier or quantity beside a code, no meaning | `entities[].raw`, `quantity` | Q2 | med | 2 |
| 14 | `lanes/business/predicate.py:20,21,44,57,65` cert regexes and words, `:331` goal or message | RAW, GOAL, VALUE | Decides certificate ask and scheme. `:21` has no word boundary: "concert", "certainly" match today | `entities[].listed` exists on closed-lists text only; on prod text **new closed `requested_attributes` values** | replace | med | 3 |
| 15 | `predicate.py:140,189,416` `_LEG_BY_ATTRIBUTE_WORD` `_leg_in_words` `_MESSAGE_WORD_RE`; `lanes/business/fetch.py:861` | RAW, VALUE | Word (stok, promosi, harga, sijil) picks the leg; moves domain, team, rows | `intent_hint`, `domain_hint` for 3 legs; cert and price need the same new closed values | replace | high | 3 |
| 16 | `lanes/business/gate.py:208,218`; `head/grounding.py:565`; `engine.py:594`, `engine.py:1019` `typed_here` | VALUE, RAW | Digit and code shape retype product vs category, picker vs miss | `entities[].hint`, `hint_confident`, `current_message` | replace | high | 3 |
| 17 | `head/grounding.py:398,754,299` `_STOPWORDS` `_as_typed` `ground_words` step 3 | RAW, VALUE | Picks the word said back in "Couldn't find X" | `spec_value`; **new `entities[].typed_text`** if the typed form must echo | replace | high | 3 |
| 18 | `../product_spec_search.py:562,822,693` `_PHRASE_STOPWORDS` `unknown_spec_values` `unrecognized_terms` | RAW | Same idea as 17 on the raw message | as 17 | replace | high | 3 |
| 19 | `lanes/business/resolve_gate.py:199` `_incoming_named_in_message`; `:293` 4-word cap; `lanes/business/find.py:218` | RAW | Keeps or drops the incoming domain; caps a bare reply; drops a fit value not in the message | `domain_in_message` (UNVERIFIED reliable for incoming); `find` | replace, find guard UNVERIFIED | med | 3 |
| 20 | `head/candidates.py:444,542` `_SIZE_RE` (dormant); `head/lookup_lists.py:700,754` `_UNITS` `number_hits` | RAW | Feeds master data lines to the parser, parser still chooses | `spec_value`, `spec_unit` | Q3 | med-high | Q3 |
| 21 | `language.py:13,17,25` `_MALAY` `_ENGLISH` `detect` | RAW | Word count picks reply language, every turn on prod text | `message_language` | Q4 | med | Q4 |

## Real examples

Taken from code comments quoting live turns. No SQL on the shared dev DB (browse-through-UI rule).

| Message | Today | After |
|---|---|---|
| "escalate to marketing for srtsc07 full height" (turn 14875614, `lanes/escalation.py:1376`) | Parser: `suggested_team: purchasing_product`. Regex finds marketing, asks which marketing team | `escalation.named_team: marketing`, same reply |
| "pelase escalate to marketing team MWc-SC8609-)PP water closet" (`lanes/escalation.py:1403`) | Parser: master_products. `_ESCALATE_WORD` forces `request_for_help` | Parser must obey its own MESSAGE TYPE rule 1. If it does not, the customer gets a spec sheet: the main risk |
| "Srtwc7604 p trap price" (`../product_code_family.py:5`) | Code word regex, "p trap" narrows to the variant | Parser returns a spec entity, `narrow_code_tokens_by_specs` narrows. UNVERIFIED that prod text emits it; gold row first |
| "2" over 1 Office, 2 Dealer, 3 End user (turn 3f56a40d, `engine.py:433`, `:6127`) | Parser read position 1; regex overrides to 2 | Q2 |
| "okay how about all my sales order?" (`engine.py:6077`, `so_status.py:412`) | Parser said SO in 1 of 3 runs; words force the SO list | Batch 2, prompt fix first |

Edge cases the gold set must hold: "trying to get the marketing flyer" names no team (`lanes/escalation.py:1341`); "the spec
of SRTWC286 for the marketing team" is not a request (`:1407`); "yes" to an offer for team A while naming team B is not a yes
(`turn/apply.py:195`).

## Questions

Q1. Scope of this lane? (a) Batch 1 only (rows 1-6), then batches 2 and 3 as later lanes with their own gate. (b) All rows in
one PR. (c) Only the brief's three (rows 1, 3, 20). **Recommend (a):** the escalation and code clusters are what the brief names,
each batch can be read on its own gate, and a miss can be traced to one family.

Q2. Digits and identifiers typed over what we printed (row 7 digit half, row 13, `required_fields.py:276` digit half)? (a) Keep:
they read a number or an id, no meaning, and the parser demonstrably misreads them (turn 3f56a40d; SO numbers wrong in 2 of 4,
`so_status.py:449`). Words such as "all" or "third" still go. (b) Remove too; prompt fix first. **Recommend (a).**

Q3. Row 20, message words matched to master data lines that only feed the parser? (a) Keep; swap `_UNITS` for registry units and
leave dormant `_SIZE_RE` alone. (b) Remove; parser reads number and unit, code converts by registry factor. **Recommend (a):**
nothing is decided there, and these lines carry DIMENSION-ANY (owner's 28 Oct prod miss). This differs from the brief, which listed
`_SIZE_RE`.

Q4. Row 21, reply language? (a) Leave out of this lane: it moves no routing or answer, it was agreed on its own card
(`documentation/plans/chatbot/chat-language-behaviour-card.md:18`), and a failed parse has no parser to ask. (b) Move to
`message_language`: needs `LANGUAGE_ASK` in the prompt plus a code change, since the schema adds the field only under
closed lists (`head/parser.py:1085-1086`). **Recommend (a).**

Q5. Release order for the new field? Baseline is text E (#2030, md5 e90461ef), so this lane starts after #2030 merges. (a) Code
reads `escalation.named_team` with no word fallback; owner pastes the new text right after release; until then a named-team turn
falls to `routing.suggested_team`. (b) Prompt-literal gate (as `head/parser.py:1071`): the regex runs until the paste, a second
PR deletes it. **Recommend (a):** one path, fewer moving parts. Choose (b) if the paste may lag the release by more than a day.

## Step 2, decided unless the answers change it

Before removing a rule: measure the parser alone against the rule on the batch's gold rows, add near-miss rows. Red tests first,
tester and coder separate. New text gated against fixed arm A, hidden run by crew. Live console pass, reviewer. No new word or regex rule.
