# UAC - Chatbot turn engine re-architecture

Plan: `PLAN-chatbot-turn-rearch.md`. Numbering: AC-15xx. Each criterion names its evidence
(pytest / vitest / turn replay / agent-browser run / owner hand pass). "Contact" = a Respond.io
contact through `/api/v1/external/chat/turn`; "dealer" = a contact with no field reveal
grants; "operator" = a CRM user with `system.chat_history.view`; "owner" = the product owner.
The compatibility contract (appendix A, 129 lines) is the list of behaviours that must still
work; every line has at least one replay case (AC-1590).

Decided by the owner on 15 Sep 2026 (architecture page `.lavish/chatbot-architecture-15sep.html`,
grill rounds 1 to 3). Supersedes the head / dialogue / tail design of
`PLAN-chatbot-turn-engine.md` and lane 1 + lane 2 of `PLAN-chatbot-focus-multi-domain.md`;
their kept behaviours are contract lines, their code is replaced.

## Journey

### A. Dealer on WhatsApp

Arrives from the Respond.io channel mid-conversation. The system already knows: the contact,
their companies, their grants, their profile (tier, language, default ledgers), this
conversation's focus, the one open question if any, and their closed topics (episodes).

1. Dealer types "incoming wc286". One parser call. The narrower for product under incoming
   says "narrow to a code": a ten-row roster with has / no incoming stamps. One question open.
2. Dealer types "8". APPLY resolves the pick from the parser's `reference_positions`; the
   roster stays alive (sticky); fetch runs for the picked code; the Incoming section renders.
3. Dealer types "stock". Domain switch, product kept from focus; no product re-asked.
4. Dealer types "outstanding DO for chin chun". `document = DO`, `status = outstanding`
   from the parser; customer under order must narrow to one: customer picker with family
   rows and ledger counts. "DO" was named, so no "SO, DO or both" question.
5. Dealer types "1". The family (every ledger of the base name) becomes the customer; the
   report renders; the detail question is the one open question.
6. Dealer types "SRT6536-DIY only". Exclusive narrowing on the product axis only; customer
   family kept; report re-renders for the product within the family.
7. Dealer types "7445". Parser hints order; the resolver finds no order 7445 and one product
   7445: reconciled to product, trace says so, domain follows the reconciled kind.
8. Dealer types "same report as yesterday". Parser flags a backward reference; recall reads
   this contact's episodes (if their recall toggle is on) and hands the parser the frame as a
   hint; the report re-runs without re-asking customer or document.
9. Dealer types "stock and eta for SRTWT2634". Two domains: fetch fans out, one section per
   domain, facts printed once, one escalate line only on a total miss; two missed teams
   become one numbered team pick.
10. Dealer says "yes" to an offer: routed, assigned, commented, SLA row. "no it's okay": offer
    closed, focus intact. A casual "thanks" in between changes nothing.

At every step the dealer decides only when the narrower demands it or an offer is open.
Nothing already in profile or focus is asked again.

### B. Owner adding a domain

System Management, Chatbot Domains, Add. One modal: name, label, intents, tools picked from
the MCP list, escalation team picked from Teams, switch words, narrowing per entity kind, date
filter, reveal key, supported. Save. The Prompts page shows "domain block out of date"; the
owner publishes a new parser version (one click, commit message). A developer adds the
composer. The domain answers. Two decisions in total: save, publish.

### C. Operator troubleshooting a turn

Chat history, click a turn. The drawer shows the stages, the parser verdict, the APPLY panel
(verdict in, state diff out, narrowing fired, reconciliation if any, turn plan), the three
memory shelves before and after with their writer, the prompt text sent, one tool entry per
domain. No decisions; Retry if needed.

## Owner decisions (grill, 15 Sep 2026)

| # | Decision |
|---|---|
| D1 | Option C: re-architect stages between parser and fetch, plus the tail. Parser is the only decider of MEANING; the resolver decides IDENTITY. |
| D2 | One APPLY function, one pending object (the five-key session shape kept as-is), one scope (focus). Head overrides (13 sites) become replay cases and prompt responsibilities, never head code. |
| D3 | Fan-out in scope. Episodes with FULL recall in scope, same contact only, toggle per contact, global default off. Profile = one JSONB column on `respond_contacts`. |
| D4 | One narrower declared per (domain, entity kind): must narrow to one / narrow to a code / narrow by type / narrow by tier / optional filter / list all variants / not applicable. Did-you-mean per entity kind. |
| D5 | No cross-kind AND in the resolver. Reconciliation after the resolver: hinted kind first; miss + exactly one other kind hits = that kind wins (trace line); two kinds hit = ask; domain follows the reconciled kind when no domain word was said. Deletes `BARE_ENTITY_TYPE_BY_DOMAIN`. |
| D6 | `order_status` is replaced by two focus slots: `document` (SO, DO, PO, SPO, GRN, ...) and `status` (outstanding, delivered, cancelled, all). Domain follows the document. "SO, DO or both" is asked only when no document is named. |
| D7 | Ledger family by base name is one customer by default (like the customer picker); "only [IBORN]" narrows; profile default-ledgers can override later. |
| D8 | One prompt lineage (v3 shape). v1 and SLIM retired. #921 and #928 fixed in the prompt. Domain block rendered from the domains table; manual publish from the Prompts page with an out-of-date banner. |
| D9 | Big bang on a branch off main. No shadow turn, no engine switch. Rollback = blue/green redeploy. |
| D10 | Gate: key-free turn replay (recorded parser verdicts replayed through the new engine, structural meaning compare, signed divergence list), then the owner's hand pass twice (engine complete, end). Live LLM only for the prompt slice's own cases. |
| D11 | Existing tests: kept code's tests untouched; head / dialogue / tail tests triaged per file (port if it asserts a contract line, retire naming the rule). |
| D12 | Contract = 129 lines (appendix A). #930 builds to green then parks; #866, #833, #760, #912 close after ship; their behaviours are lines 102 to 129. |
| D13 | Configurable as data: domains, entity kinds, ladder, tier order, memory settings. Behaviour (APPLY, route, composers, resolver, MCP catalog) stays code. No rule editor (growth-r1 D5 stands). |
| D14 | No new motion on any surface in this plan. |

## S0 - Data and contracts

- AC-1501 [BE][T] Table `chatbot_domains` exists with columns: `name` (unique), `label`,
  `intents` (text[]), `tools` (text[], validated against `mcp_tools.name`), `primary_tool`,
  `escalation_team_code` (text, nullable; a team-set code as in `agent_teams.code`, e.g.
  `purchasing`; the per-company team is resolved at escalation time through the contact's
  access agent exactly as today, so no FK; the FE picker lists the distinct codes),
  `switch_words` (text[]),
  `takes_date_filter` (bool), `reveal_key` (nullable), `supported` (bool),
  `narrowing` (JSONB: entity kind to policy), `ladder` (text[] of domain names), `sort_order`.
  Seeded by migration from today's `DOMAIN_SPEC`, `chatbot_crossdomain_ladder` and the SF6
  tool sets. Evidence: pytest comparing the seeded rows to the constant field by field.
- AC-1502 [BE][T] Table `chatbot_entity_kinds` exists: `kind` (unique, seeded with the 12
  `ENTITY_HINTS`), `resolver_source`, `did_you_mean` (bool), `default_narrowing`,
  `family_grouping` (nullable), `base_property_words` (JSONB word to `products` column,
  product only, seeded with today's list mapped to the columns they read today, plus
  `discontinued` to `is_discontinued` and `brand` to the brand column). Exactly the 12 kinds,
  no `tier` row: tier order is the system setting `chatbot_tier_order`, seeded with the code's
  literal order `["dealer", "office", "end_user"]` (the three code copies collapse onto it).
  Evidence: pytest on the seed and on the setting default.
- AC-1503 [BE][T] `respond_contacts` gains `chatbot_profile` JSONB (`tier`, `language`,
  `default_ledgers`, `always_full_report`) and `chatbot_recall_enabled` bool default false.
  Both reach the contact detail API (both dict builders). Evidence: pytest on the API shape.
- AC-1504 [BE][T] `SessionVars` keeps exactly the five keys `focus`, `open_question`,
  `ideation`, `access_levels`, `contains_flyer`; `focus` gains `document` and `status` slots
  and drops `order_status`; a stored `order_status` is read once and mapped forward.
  Evidence: pytest on a legacy row.
- AC-1505 [BE][T] `conversation_frames` is the episode store: a frame row per closed topic
  with `contact_respond_id`, `domain`, `intent`, `entities` (JSONB with kinds and ids),
  `tools_used`, `summary`, `opened_at`, `closed_at`, `turn_ids`; embedded through the existing
  `embedding_queue` as `source_type = conversation_frame`. Evidence: pytest on the write path
  in AC-1546.
- AC-1506 [BE][T] The parser contract is one schema (v3 shape) plus `document`, `status`,
  `anaphora.backward_reference` (bool) and `entities[].hint_confident`. `V1_ONLY_KEYS`,
  `emits_v3`, the SLIM body and the dual `schema_for` are deleted. Evidence: pytest that the
  schema builder has one branch; grep guard test for the deleted names.
- AC-1507 [BE][T] The external contract is unchanged: `TurnRequest` / `TurnResponse` /
  `CompleteRequest` / `CompleteResponse` fields and `ACTION_KINDS` byte-identical to main.
  Evidence: pytest pinning the JSON schema of each against a stored fixture.

## S1 - Phase 1 frontend, mocked

- AC-1510 [FE] System Management gains "Chatbot Domains": DataGrid (fixed layout, resizable
  columns, explicit sizes, truncate + title) with columns Domain, Label, Tools, Escalation
  team, Switch words, Narrowing, Date filter, Supported, Updated; search; filters Supported
  and Team; Add domain; row click opens the modal. Evidence: vitest on the column config;
  agent-browser screenshot at 1280 and 375.
- AC-1511 [FE] The domain modal is one layout for view and edit, tabs General / Narrowing /
  Ladder / Prompt block; every select is `SearchableSelect`, every optional select clearable;
  tools come from the MCP tools list, team from Teams; the Prompt block tab is read-only and
  says the block renders on the next publish. Delete is the deferred countdown pattern, no
  confirm dialog. Evidence: vitest; agent-browser.
- AC-1512 [FE] System Management gains "Entity kinds": DataGrid with Kind, Resolved against,
  Did-you-mean, Default narrowing, Family grouping, Base property words; edit modal; the
  `tier` row carries an orderable list. Evidence: vitest; agent-browser.
- AC-1513 [FE] Settings > Chatbot gains three cards: Memory (recall default, episode retention,
  profile fields, focus reset events), Tier order (one orderable list), Cross-domain ladder
  (per-domain ordered rungs, add rung select). The free-text "unsupported domains" input is
  removed; Supported lives on the domain row. Evidence: vitest; agent-browser.
- AC-1514 [FE] The turn drawer gains an APPLY panel (verdict, state diff with added and removed
  values, narrowing applied, reconciliation line, turn plan, collapsible prompt text sent) and
  a Memory panel (Focus, Profile, Episodes with writer badge per row, recall hit or "not
  triggered"). Evidence: vitest on the panel rendering from a fixture turn; agent-browser.
- AC-1515 [FE] Contact > Access gains a "Chatbot" card: recall toggle and the profile fields,
  read-only where the value was set by a pick. Evidence: vitest; agent-browser.
- AC-1516 [FE] Every service file in S1 documents its API contract at the top and calls a mock;
  states loading, empty, error, partial, success are all reachable. Evidence: vitest per
  state.
- AC-1517 [UX] No motion is added on any S1 surface; the list of surfaces that must not
  animate is in the plan. Existing Dialog / Sheet presets apply unchanged. Evidence:
  `review-animations` finds no new motion in the diff.

## S2 - APPLY, pending, narrower, reconciliation (pure, no I/O)

- AC-1520 [BE][T] `turn/apply.py` exposes one function `apply(state, verdict, policy) ->
  (state', plan)`. It reads no message text, calls no regex over text, imports nothing from
  `head/`, `dialogue/`, `tail/`. Evidence: pytest; an import-boundary test; a grep guard for
  `re.` and `.text` inside the module.
- AC-1521 [BE][T] Pending is one object `{kind, expects, options (frozen rows with uuid and
  uuids), team, payload, asked_at_turn}` with one constructor `ask()` and one resolver inside
  `apply`; kinds are the eight existing ones. Arm and resolve sites in the codebase: exactly
  one each. Evidence: pytest; grep guard counting call sites.
- AC-1522 [BE][T] A number with a pending roster resolves that row (multi-pick "1, 3 and 5"
  and "all" included) from `reference_positions` / `answers_open_question`; a pick option's
  `uuids` yields one entity per uuid (contract 103). The roster stays alive after its own pick
  (contract 36). A pick never changes domain (contract 121). Evidence: pytest parametrized
  over the eight kinds.
- AC-1523 [BE][T] A yes or no with a pending offer resolves it from `is_affirmative` /
  `escalation.*` flags only; "no" with own entities is not a decline; a question the same turn
  asks is never consumed by that turn's answer. Evidence: pytest, both arms per kind.
- AC-1524 [BE][T] Exclusive narrowing (`scope_exclusive`) replaces only the axes the message
  names; every other axis is kept. Evidence: pytest for product-only over a customer family
  (journey step 6), location-only, customer-only.
- AC-1525 [BE][T] Focus rules are the existing seven in order (replace same axis, reset on
  topic, reuse alive, domains from asks, date restated only, anaphora reuses, confident guard)
  applied inside `apply`; `document` and `status` are axes; `order_status` is gone. Evidence:
  ported focus tests.
- AC-1526 [BE][T] The narrower reads the domain row's `narrowing` map and returns, per entity
  kind present, one of: proceed / ask roster / ask type / ask tier / filter optional. Product
  under inventory lists all variants; product under incoming and purchase cost asks for a
  code; customer under order asks for one family; attachment type under photos asks the type;
  promotion asks the tier unless profile has one. Evidence: pytest parametrized over the
  seeded matrix.
- AC-1527 [BE][T] Reconciliation: the resolver is asked for the hinted kind first; on a miss
  with exactly one other kind hitting, the entity's kind is rewritten, a trace line
  `reconciled: <from> -> <to>` is written, and the domain follows when the verdict carried no
  domain word; two kinds hitting produces a pending `kind_pick`. No cross-kind AND anywhere:
  a customer roster is identical with or without a product token in the message. Evidence:
  pytest for 7445 (order hint, product hit), for a token that is both, and for "chin chun +
  SRT6536-DIY" roster equality.
- AC-1528 [BE][T] Plan output is data: `{domains: [...], fetch: [{domain, entities, filters,
  date_window}], ask: pending | None, denied: [...]}`. Route reads only the plan. Evidence:
  pytest that `route()` takes the plan and nothing else.

## S3 - Fetch fan-out, compose, tail, episodes, recall

- AC-1530 [BE][T] Fetch loops `plan.fetch` in order: resolve, gate, tool, envelope; a domain the
  contact is not granted yields a denied envelope; grant checks run per domain (contract 128).
  Evidence: ported lane 2 worlds.
- AC-1531 [BE][T] Composers return data first: `{sections: [{domain, entities, figures, files,
  miss}], question: pending | None, offer: {teams} | None, canned: [...]}`; text is rendered
  from that data by the #930 grammar (contract 102). One deduper keyed (entity, domain); one
  escalate line; files folded once (contract 105). Evidence: pytest on the data shape; #930's
  golden bodies as replay cases.
- AC-1532 [BE][T] The tail writes `pending' = composer.question` exactly (or none), persists
  the five keys under `FOR UPDATE`, and records the offer once with the team the composer
  returned. `record_offer`, `team_from_reply`, `_spend_the_answer`, `with_offer`, `_re_armed`
  and the carry helpers are deleted. Evidence: pytest; grep guard for the deleted names.
- AC-1533 [BE][T] Team pick on 2+ missed domains, yes / no on one, numbered options, "No it's
  okay" (contract 127); named-team escalation, family word resolution, brand in the routed
  message, did-you-mean before the team question (contract 106 to 113). Evidence: ported
  #866 tests as replay cases plus pytest on the team set.
- AC-1534 [BE][T] Attribute-first asks: counted set answers, paging by 5 on "more" / "next" /
  "lagi", own-company certificate and tier-visible promotion counts, unknown attribute clarify
  (contract 114 to 120). Evidence: #833's console file as replay cases.
- AC-1535 [BE][T] Base property words come from the entity kinds row: "is it discon?" answers
  from `products.is_discontinued`, never "not recorded". Evidence: pytest on the two owner
  turns of 15 Sep.
- AC-1546 [BE][T] Episode write: on `topic_reset` or conversation close the tail writes one
  `conversation_frames` row for the closed topic and enqueues its embedding. Never mid-topic.
  Evidence: pytest on a three-topic conversation producing two frames.
- AC-1547 [BE][T] Recall: only when `anaphora.backward_reference` is true AND the contact's
  `chatbot_recall_enabled` is true; top 3 frames of this contact by vector similarity then
  recency; handed to the parser as an `Episodes:` hint block on the NEXT parse of the same
  turn (one re-parse, traced as `recall`); never another contact's frames. Evidence: pytest
  with a stubbed embedding; a negative test for another contact; a negative test with the
  toggle off.
- AC-1548 [BE][T] Profile hints: tier, language, default ledgers rendered as a `Profile:` block
  on every parse; a known tier suppresses the tier question. Evidence: pytest.
- AC-1549 [BE][T] The trace carries: `apply` stage record (verdict, state diff, narrowing,
  reconciliation, plan), `memory` record (three shelves before and after, writer per slot,
  recall hits), `prompt_text` (the rendered user block plus hint blocks, capped at 64 KB).
  Evidence: pytest on the trace shape; AC-1514 renders it.

### S3 rulings (16 Sep 2026, coder report at 63bcf8848)

- `chatbot_completed_lanes` no longer gates the turn (the n8n lanes it handed back to read
  the retired head's state); contract line 73 is superseded. Column stays unread until S6;
  S5 FE removes the "Lanes the CRM answers" card.
- `Profile.grants` stays unrestricted in APPLY; per-domain reveal gating stays in the lanes.
  Trigger to move it into policy: S5's grant sweep.
- Session shape: five keys flat at the top level of `session_vars`; a reader falls back to
  the legacy `variables` nest once (`session_state.py`).
- `turn/policy_rows.py` is frozen seed data imported by the S0 migration; policy changes go
  through new migrations, never by editing that file.
- Attribute-first: the described set is scoped by the class word the PARSER named
  (`product_type` / `category` entity) forwarded as `scope_terms`; never sliced from text.
- Twelfth focus slot `set_page {set_key, offset}` carries the counted-set page (contract 115).
- A numbered pick restores the domain the roster was armed under (`pending.payload.domain`).

## S4 - Prompt lineage

- AC-1550 [BE][T] One parser prompt body, v3 shape, with the domain block rendered from
  `chatbot_domains` (name, label, intents, switch words, entity kinds with narrowing, date
  filter, team) and the entity-kind block from `chatbot_entity_kinds`. A migration publishes
  the first version unlabelled. Evidence: pytest rendering the block from the seed and
  diffing against a golden file.
- AC-1551 [BE][T] The prompt emits `document` and `status` for "DO outstanding", "PO
  outstanding", "outstanding" (document null); `reference_positions` for "another one" is
  empty (#933); "only BRW" carries no volunteered position; low stock routing survives (#921).
  Evidence: live parser cases in `console_cases/2026-09-xx-rearch-prompt.yaml`, paced, run
  once per prompt change and recorded as replay verdicts.
- AC-1552 [FE][BE] The Prompts page shows "domain block out of date" when any domain or
  entity-kind row changed after the labelled version's render; publishing renders the block
  fresh. Evidence: vitest on the banner; pytest on the staleness check.

## S5 - Frontend wired

- AC-1560 [FE][E2E] Every S1 mock is swapped for the real service call; the DoD gate passes:
  real data, both dict builders, 375 and 1280, sidebar navigation from `/`. Evidence:
  agent-browser evidence run per page.
- AC-1561 [BE][T] Domain and entity-kind CRUD routes under `/api/v1/system/chatbot/domains`
  and `/entity-kinds` guarded by `system.chat_history.view` (read) and a new
  `system.chatbot_config.manage` (write) with a grant sweep for provisioned admin roles.
  Evidence: pytest happy + denial + validation per route.

## S6 - Gate

### S6 rulings (16 Sep 2026, owner hand pass 1)

- Stock allowance is a CRM fact, not a respond.io custom field. `respond_contacts.chatbot_stock_allowed`
  (boolean, NOT NULL, default TRUE, migration `chatbot_rearch_s6`) is the only source; the envelope's
  `is_allowed_stock` custom field is ignored. Everyone is allowed unless an operator switches the
  contact off on the Contact > Access > Chatbot card ("Stock checks" toggle, same PUT as recall).
  Contract line 61 reads this column; 62 unchanged. Owner: "our contact should have the field and by
  default everyone should be on".
- An open question is answered only when the PARSER says so. `answers_open_question`
  `{resolved, picks, answer}` becomes a declared parser schema key (it was read by APPLY but never
  produced: the parser only emits `reference_positions`). APPLY: `resolved: true` = apply the picks;
  `resolved: false` with an attempt = re-print the same question; absent/null = the message is not
  an answer, run it for what it is and CARRY the pending unchanged (sticky, never repeated). Owner:
  "follow the old bot, it is smarter, no hard coding, LLM aware". Cluster 4 ruled this way.
- The console borrows only a real inbound envelope (`ingress = webhook`, `is_test = false`); a
  console or smoke turn's synthetic envelope is never a base. Found when a smoke turn's empty
  `custom_fields` poisoned every later console turn.

- AC-1590 [T] Turn replay: `tests/chatbot/replay_turns/` holds recorded cases (envelope,
  parser verdict, expected data) for every contract line (129), the 91 console cases, the 17
  owner chains, #930's file, #833's file, and a sample of about 40 real turns per branch kind
  from the prod copy. `pytest tests/chatbot/test_turn_replay.py` runs with the parser mocked
  from the recorded verdict, zero network, under 60 s. Evidence: CI job.
- AC-1591 [T] Comparison is structural: branch kind, tools and args, entity ids fetched,
  action kinds, pending kind and options, focus after, canned sentences verbatim; free text
  only where a case pins it. Every difference from the recorded expectation is either a
  signed entry in `replay_turns/DIVERGENCES.md` (owner initials, reason) or a failure.
  Evidence: the test reads the divergence file.
- AC-1592 [T] Test triage: every file under `tests/chatbot/` that imports `head/`, `dialogue/`
  or `tail/` is ported (asserting a contract line) or retired, with the rule name in the
  commit body; no test is deleted by the coder. Evidence: tester's triage table in the PR.
- AC-1593 [E2E] Owner hand pass on the lane stack, alone on the OpenAI key, once when S3 is
  green and once at the end; each finding becomes a replay case before any fix. Evidence:
  two evidence docs under `documentation/plans/chatbot/evidence/turn-rearch/`.
- AC-1594 [BE] Deleted: `head/output_exchange.py`, `tail/compile_state.py`, `dialogue/`,
  `tail/pending.py` remnants, `DOMAIN_SPEC` and its derived dicts, `SUGGESTED_TEAMS`,
  `_BASE_PROPERTY_WORDS`, the three `TIER_ORDER` copies, `ENTITY_FILTER_REQUIRED_TOOLS`,
  `PRODUCT_ID_REQUIRED_TOOLS`, `BARE_ENTITY_TYPE_BY_DOMAIN`. Evidence: grep guard test.

## No-motion list (D14)

Chatbot Domains list and modal, Entity kinds list and modal, the three Settings cards, the
APPLY and Memory panels in the turn drawer, the Contact Chatbot card. Existing Dialog / Sheet
entry and exit presets apply; nothing else animates.


### Hand pass 3 rulings (17 Sep 2026, owner go)

- `answers_open_question` is RETIRED from the parser schema, the prompt and APPLY. A message
  answers the open question when a `reference_positions` entry or a named entity matches an
  offered option by exact label, when `is_affirmative` answers an offer, or when
  `broaden_axis` is `all`; otherwise the question stays open and the message runs as itself.
  The engine matches labels, it never reads words. Supersedes the S6 cluster-4 wording; the
  behaviour (carry, never re-print) stands.
- The parser's user block gains one line, "Current subject", built from the focus every
  turn (domains, customers, products, document, status, date window), so refinements and
  domain switches are judged with context. `entity_op` remains the parser's call.
- A pick settles only the kind it picked; every other carried entity stays on the fetch.
- The answer header names each customer family once; "all" over a customer roster fetches
  every family's ledgers.
- A document named in the message is a new scope while ANY outstanding question is open.
- The outstanding detail list carries the same filter header as the summary.
- Rosters under promotion and purchase_order carry stamps (has promo / no promo, has PO /
  no PO) from the same probe seam as incoming and DO; the PO picker stays.
- Word numbers ("eight") are positions; the prompt says so.
- Hand pass 3 row 4 withdrawn: the parser returned the date window; only the header was wrong.

## Appendix A - Compatibility contract (129 lines, signed 15 Sep 2026)

Source: architecture page section 9. `main` = live on prod today; `lane` = on
`feat/chatbot-focus` (#863) only; `#nnn` = from that PR. Each line needs a replay case.

Domains and answers: 1 stock by location (main); 2 low stock report, staff grant unlocks
full (main); 3 zero or short stock climbs the ladder (main); 4 incoming with ETA always kept
(main); 5 clearance checkpoints in order (main); 6 PO placed (main); 7 last purchase cost,
refused without grant (main); 8 last in, SPO line per product (main); 9 product info: price,
specs, dimensions, catalogue, discontinued (main); 10 spec answer names what it matched and
what it could not filter (main); 11 attachments by type (main); 12 certificate validity
(main); 13 catalogue, stock list, general files (main); 14 promotions with flyers (main); 15
promotion by tier (main); 16 outstanding SO + DO report by customer and product (main); 17
order and delivery status, DO list (main); 18 customer resolved to narrow an order question
(main); 19 twelve named entity kinds (main); 20 forms (main); 21 portal link (main); 22
ideation captured (main); 23 goods receive refused (main); 24 projects, complaints, SLA,
guides by name (main); 25 46 MCP tools, derived read-only allow-list (main).

Dialogue: 26 did-you-mean per entity kind (main); 27 customer picker has / no DO (main); 28
product roster has / no incoming (main); 29 a number answers the open menu (main); 30
multi-pick (main); 31 "all" over a menu (main); 32 "X only" narrows (main); 33 follow-up
without repeating the product (main); 34 focus slots with replace, reset, reuse (lane); 35
domain switch keeps the product (main); 36 sticky roster (lane); 37 one open question with
eight kinds (lane); 38 SO / DO / both scope question when no document named (main); 39
detail on first pick (main); 40 member offer (main); 41 escalate offer per team (main); 42
decline (main); 43 offer hold (main); 44 explicit correction (main); 45 quoted-message
reference (main); 46 photo input (main); 47 voice input (main); 48 flyer detection (main);
49 low-signal clarifier (main); 50 clarify menu (main); 51 casual chat (main); 52 miss
suggestion (main); 53 company clarify (main); 54 team clarify (main); 55 dash fold (lane);
56 answered question cleared (lane); 57 several asks in one message (lane).

Access and safety: 58 access agent fails closed (main); 59 field reveals (main); 60 SO denial
sentence (main); 61 stock denial switch (lane: reads `respond_contacts.chatbot_stock_allowed`, default on); 62 demand qty ask (main); 63 unsupported
domains (main, becomes the Supported flag); 64 company scope (main); 65 domain hint guard
(main); 66 read-only tools (main); 67 narrowing required for document tools (main, becomes
the narrowing policy); 68 dry-run isolation (main); 69 harness injections (main); 70 dedupe
(main); 71 ingress kinds and retry (main); 72 S7 per-contact ordering (main); 73 lane cutover
flags (main); 74 delegated sweep (main); 75 human intervention (main).

Escalation outputs: 76 five action kinds, CRM never sends (main); 77 eight teams, default
customer service (main, becomes the team FK); 78 round-robin, named pick does not move it
(main); 79 SLA row (main); 80 SLA comment with deep link (main); 81 out-of-scope sentence
(main); 82 routed-to-PIC sentence (main); 83 no assignment while company unpicked (main); 84
canned copy registry-owned (main).

Observability: 85 eight trace stages (main); 86 answered stage (lane); 87 failure stages
(main); 88 tool sub-events (main); 89 chat-history viewer (main); 90 in-app console (main);
91 dialogue shape on trace (lane); 92 shadow parse (lane); 93 parser usage log (main); 94
prompt version pinned on trace (main); 95 settings screens (main).

Test assets: 96 eight console files, 74 cases (main); 97 the 15 Sep owner chains, 17 (lane);
98 replay corpus for kept nodes (main); 99 parser phrase fixtures (main); 100 test modules
(mixed); 101 guardrail tests on the contract (main).

Lane #930: 102 one section grammar, six sentences retired; 103 pick option = one code with
`uuids` + `uuid`, one entity per uuid, compatible entities exact for require-specific
domains; 104 PO CANCELLED and "outstanding purchase order" label; 105 product sets expand at
the gate, files folded once, deduped by id or url, labelled per company.

#866: 106 named team escalates; 107 help with no team = default ask; 108 family word resolves
to the open offer's team; 109 escalate with no team keeps carried; 110 brand in routed
message; 111 did-you-mean before team question; 112 product carries only if team matches;
113 console dry run shows brand and did-you-mean.

#833: 114 counted set answer; 115 more / next / lagi paging; 116 active-warehouse stock only;
117 own-company certificates; 118 promotions by tier and company; 119 unknown attribute
clarify; 120 "any X incoming" leg.

#760: 121 a bare positional never re-domains the turn.

#912: 122 one message, one section per domain; 123 bare code re-runs all asked domains; 124
fact printed once; 125 no-stock-but-incoming fold; 126 pick product first then fan out; 127
team pick for missed domains; 128 per-domain grants on fan-out; 129 turn drawer one tool
entry per domain.
