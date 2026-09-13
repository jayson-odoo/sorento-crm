# UAC - Chatbot focus + multi-domain

Plan: `PLAN-chatbot-focus-multi-domain.md`. Numbering: AC-10xx. Lane 1 (dialogue state) is
AC-1001 to AC-1039; lane 2 (multi-domain fan-out) is AC-1040 onward. Each criterion names its
evidence (pytest / vitest / world / replay / agent-browser run). "Contact" = a Respond.io
contact through `/api/v1/external/chat/turn`; "dealer" = a contact with no field reveal
grants. Supersedes section D (AC-940 to AC-953) of `chatbot-growth-r1-acceptance-criteria.md`;
the mapping is at the bottom.

## Journey

Actor: a dealer on WhatsApp, arriving from the Respond.io channel mid-conversation. The system
already knows the contact, their grants (stock visibility, field reveals), what they asked in
the last few turns (focus), and whether the bot is waiting on an answer (open question).

1. Dealer types "SRTWT2634 stock and eta". Bot resolves the product once. Ambiguous: ONE
   numbered picker, nothing else. Clear: one reply with a Stock section, then an Incoming
   section, in the order the dealer said them, then one escalate offer naming the team or
   teams.
2. Dealer types "SRTWT2635" (bare code). The same two domains rerun for the new code.
3. Dealer types "PO?". Domains switch to purchase order, product kept.
4. Dealer types "promo for CWCX7605". Domains and product both switch.
5. Dealer types "1" on a picker. The pick resolves the product, then every domain in focus
   reruns for it. Numbers never collide: only one question is ever open.
6. Dealer says yes to escalate where two teams apply: the bot asks which team, with buttons.
   One team: assignment straight away.
7. A slot older than the TTL dies. The bot asks "which product?" rather than guess.
8. Dealer types "1" with nothing open. The clarifier, knowing what is alive, asks for the
   missing piece; the dealer's answer lands in the business lane with the alive domains.

Told automatically: the escalation team gets the assignment and the SLA clock. The owner sees
every focus rule, every open-question resolution and every shadow parse per turn in the
console.

## Measured (origin/main, 12 Sep 2026)

- 337 distinct real messages in the replay corpus; 3 name two domains at once. Fan-out is an
  owner ask, not a corpus pressure.
- Every domain in `DOMAIN_SPEC` declares exactly one intent (13 domains, 13 intents), so
  `intent_hint` carries nothing `domain_hint` does not.
- The low-signal clarifier receives the whole 34-key session bag, except when the parser
  labels the message `casual` or `unknown`, where it receives nothing. A bare "1" lands in the
  blanked case.
- n8n is off the turn path: the CRM is the only reader and writer of
  `respond_contacts.session_vars`. Outside the chatbot package only the console and the
  ideation lane (`ideation` key only) read it.
- Slice B of growth-r1 exists as an UNPUSHED local branch `feat/chatbot-growth-dialogue`
  (14 commits, worktree `.claude/worktrees/chatbot-growth-dialogue`, 48 main commits
  behind). Lane 1 builds on it; the plan's "Lane 1 base" table lists the deltas.

## Lane 1 - dialogue state

### A. Focus slots

- AC-1001 [BE][T] After any completed turn, `respond_contacts.session_vars` holds exactly the
  keys `focus`, `open_question`, `ideation`, `access_levels`, `contains_flyer`. None of the 34
  legacy keys is written. `SessionVars` is `extra=forbid` over those five. Evidence: pytest
  asserting the JSONB keys after a business turn, a picker turn and a casual turn.
- AC-1002 [BE] `focus` carries the slots `domains` (list of domain names, dealer order),
  `products`, `customer`, `transporter`, `warehouse`, `date_window`, `attributes`, `tier`,
  `brands`. Every slot is `{value, set_at_turn, set_at, source}`; `source` is the rule name
  that set it (`current_message`, `reuse`, `pick`, `quoted`). Evidence: pytest on the
  contract.
- AC-1003 [BE][T] No counter and no TTL exists anywhere (no turn count, no wall clock, no
  settings field). A focus slot is cleared only by (a) a current-message entity of the same
  axis replacing it, (b) `topic_reset`, or (c) the Respond.io "conversation closed" event:
  the existing SLA close path clears `focus` and `open_question` on the contact directly,
  idempotently, under its last-open-sibling gate (ruling 13 Sep: eager clear, no marker, no
  next-turn arm; `clearing.apply` has no conversation-closed branch). Causes (a) and (b)
  write a `decay` trace line `{slot, reason}` per slot. Evidence: pytest per cause; a world
  per cause.
- AC-1004 [BE][T] After a business turn, a run of five casual or low-signal messages leaves
  every focus slot and the open question exactly as they were. Evidence: world.
- AC-1005 [BE][T] `dialogue/focus.py` holds the carry rules as named functions, each with its
  own test, applied in this order: `replace_same_axis`, `reset_on_topic`, `reuse_alive`,
  `domains_from_asks`, `date_restated_only`, `anaphora_reuses`, `confident_guard`. Evidence:
  test names match rule names.
- AC-1006 [T] A product asked at turn N and never replaced still carries at turn N+10;
  after the conversation is closed in Respond.io the next message with no product asks
  which product. Evidence: two multi-turn worlds.
- AC-1007 [T] "incoming?" after a stock answer keeps the products and sets
  `focus.domains = [incoming]`; "what about Y" after that replaces the product and keeps
  `incoming`. Evidence: world.
- AC-1008 [T] "别的" / "another one" clears product, customer, date and domains, keeps tier
  and brands. Evidence: pytest on `reset_on_topic`.
- AC-1009 [T] After a DO result, "for customer ABC instead" replaces the customer slot and
  reruns the order tool; "last month" then replaces only the date window. Evidence: world.
- AC-1010 [T] "that one" (anaphora) with the product slot empty asks which product; with the
  slot set it reuses it. Evidence: pytest.
- AC-1011 [T] An entity with `confident=false` never replaces an alive product slot without a
  picker. Evidence: pytest.
- AC-1012 [T] A domain word with no product ("PO?") REPLACES `focus.domains` with the named
  domain; it never appends. Evidence: pytest on `domains_from_asks`.

### B. One open question

- AC-1013 [BE] `open_question` is one slot or null: `{kind, expects, options, asked_at_turn,
  asked_at, payload}`. `kind` is one of `product_pick`, `customer_pick`,
  `tier_pick`, `team_pick`, `company_pick`, `member_offer`. `expects` is `pick`, `yes_no` or
  `free`. `options` are frozen rows `{idx, label, uuid, code, domain, ...}` with `idx`
  numbered from 1 across the whole roster. Evidence: pytest on the contract; one handler per
  kind in `dialogue/open_question.py`.
- AC-1014 [T] A picker of 3 products is offered; "2" resolves to the second frozen option even
  if the product list would resolve differently today. AMENDED by owner ruling D19 (13 Sep
  2026, console pass): the roster is NOT consumed by the pick, so "3" next re-resolves against
  the same frozen rows and reruns the alive domains for the third row. Evidence: world.
- AC-1014a [T] (D19) A roster (`product_pick`, `customer_pick`, `tier_pick`) survives its own
  pick with its `options` and `asked_at_turn` unchanged, and clears only by the AC-1020 routes:
  a newer question of a kind other than the one-team escalate offer, `topic_reset`, a message
  naming its own subject, the conversation closing. `team_pick` clarify, `company_pick` and
  `member_offer` are still consumed by being answered. Evidence: pytest per kind, worlds.
- AC-1014b [T] (D19) The one-team yes/no escalate offer a pick's rerun produces RIDES on the
  roster rather than replacing it: `expects` becomes `pick_or_yes_no` and `payload.offer` is
  `{team, domain, options}`. A number re-picks; `yes` runs the escalation lane and consumes the
  whole question; `no` renders the declined copy and leaves the roster with the offer removed
  and `expects` back to `pick`. A `yes` on a roster with no offer resolves nothing. Evidence:
  pytest on the handler, two worlds.
- AC-1015 [T] Escalate offer with one team, then "yes" runs the escalation lane; "no" renders
  the declined copy; "SRTWC8517 stock?" instead is a new ask: the offer is cleared with a
  trace line at `received` and the stock is answered. Evidence: three worlds.
- AC-1016 [T] A quoted reply (`replyTo.id`) to an older picker resolves against THAT
  message's frozen options, not the alive open question. Evidence: pytest.
- AC-1017 [T] Issue #708: a numbered pick over a partial-miss roster keeps the
  already-resolved siblings via `payload.keep`. Evidence: the existing #708 test passes
  against the `product_pick` handler.
- AC-1018 [T] A pick resolves the entity and then reruns every alive domain in
  `focus.domains` for it. Evidence: world (one domain in lane 1; AC-1049 covers many).
- AC-1019 [T] `member_offer` follows the same clearing rule as every other kind (its TTL 3
  is gone); the five legacy `pending` kinds, `dym_offer`, `selection_context` and `picker_*`
  no longer exist as state. Evidence: grep in review + the worlds that exercised them.
- AC-1020 [T] While a question is open: a casual or low-signal message leaves it open; a
  message naming a subject (a current-message entity) that does not answer it clears it with
  a trace line and is handled as a new ask; a newer question replaces it. A domain word alone
  ("stock?") over an open picker is NOT a new ask: the picker stays so the next "1" resolves
  (measured 13 Sep on the pick-reruns world; every intent hint is decisive, so an intent
  cannot be the signal). It never answers silently. Evidence: pytest per case.

### C. Parser v3 and the clarifier

- AC-1021 [BE][T] Parser v3 (`chatbot_semantic_parser`, new registry version) emits a strict
  schema with `asks: [{domain, entities[]}]` in the order the message names them,
  `answers_open_question: {resolved, picks[], yes_no, free_text}`, `anaphora`, `topic_reset`.
  It has no `domain_hint`, no `intent_hint`, no top-level `entities`. The engine flattens
  `asks` at intake into `domains[]` (order kept), `entities[]` (union, order kept) and a
  per-turn `{domain: [entity refs]}` binding. Evidence: schema test; flatten test.
- AC-1022 [T] Parser v3 never re-emits an entity absent from the current message. Evidence:
  corpus replay assertion over every capture.
- AC-1023 [BE][T] The parser prompt receives `focus_hints` (alive slots only, typed) and
  `open_question_hint` (kind, expects, option labels), never the previous reply text and
  never a "continue the previous turn" instruction. Evidence: pytest on the rendered prompt.
- AC-1024 [BE][T] The low-signal clarifier receives the same `focus_hints` plus
  `open_question: none` for `low_signal` and `unknown` messages; a `casual` message gives it
  nothing. Evidence: pytest on the rendered clarifier prompt.
- AC-1025 [T] "eta?" with `focus.domains` set and no product (cleared by "another one")
  makes the clarifier ask for the missing product; the dealer's "SRTWT2635" then runs the
  business lane over the set domains without a re-ask. Evidence: two-turn world.
- AC-1026 [T] `intent_hint` appears nowhere in the parser schema, `SessionVars`, the trace or
  the prompts; every lane that still needs the word derives it from
  `DOMAIN_SPEC[domain].intents[0]`. The 1:1 guardrail test stays. Evidence: grep in review.

### D. Shadow parse, visible in the console

- AC-1027 [BE][T] `system_settings.chatbot_parser_shadow_version` (nullable string, default
  null, value `chatbot_semantic_parser@<version>`, validated on PUT against existing
  versions). When set, every real turn also runs that registry version of the parser AFTER
  the live reply is sent (never on the customer's request path) and stores
  a `chatbot.turns` row with `shadow_of` = the live turn's `message_id`, the shadow parse in
  its trace, and no reply, no session write, no send, no escalation. When null nothing extra
  runs. A shadow failure never fails the live turn. Evidence: pytest with a fake provider.
- AC-1028 [FE][BE][E2E] System > Settings > Chatbot shows "Parser shadow version" as a
  clearable select over the registry versions of `chatbot_semantic_parser`, beside the
  existing chatbot switches, usable at 375px and 1280px. Evidence: vitest, pytest on both
  builders, agent-browser run.
- AC-1029 [FE][E2E] The chat-history list has a "Shadow" filter. A shadow row shows a drift
  badge when its `branch_kind` or its flattened `domains` differ from the live turn's. The
  turn drawer's Parser drift panel shows the live parse and the shadow parse side by side.
  Evidence: vitest on badge logic, agent-browser run.
- AC-1030 [FE][BE] With the Shadow filter on, the list header shows one line: shadow turns
  counted, branch parity percent, asks parity percent, over the filtered range. Evidence:
  pytest on the summary endpoint, vitest on the line.
- AC-1031 [T] Promotion is the existing registry promote. The PR carries the shadow summary
  from AC-1030 for the window the owner ran. Evidence: PR body.

### E. Deletions and guardrails

- AC-1032 [T] `output_exchange.py` no longer contains rules K2, K4, the switch-word override,
  the AXIS BROADEN restore, `_query_brands_carried`, `_tier_carried`, or the date /
  attribute / `is_active` carry arms; each survives only as a named function in
  `dialogue/focus.py`. Evidence: grep in review + test names.
- AC-1033 [T] No persisted mirrors. `SESSION_VAR_KEYS` is the five names of AC-1001. The world
  grader maps legacy expectations onto the new shape in ONE function in
  `tests/chatbot/worlds.py` (`pending` to `open_question.kind` and `team`, `last_result_set`
  and `dym_last_result_set` to `open_question.options`, `entities` to `focus.products`,
  `domain_hint` to `focus.domains[0]`, `query_brands` to `focus.brands`, dates to
  `focus.date_window`). Every world grades green, or its divergence is registered in
  `divergences.py` with a reason. Evidence: `test_worlds.py`.
- AC-1034 [BE][T] `GET` and `PUT /api/v1/external/conversation-variables` carry the shape the
  engine stores: `{variables: {focus, open_question, ideation, access_levels, contains_flyer}}`
  with `extra=forbid` inside `variables`; a GET body PUT back round-trips; a legacy key or a
  flat five-key body without `variables` is a 422. No compatibility shim. Evidence: pytest
  including the round-trip.
- AC-1035 [BE][T] `trace_detail` keeps its nine keys; `focus[]` entries are
  `{slot, before, after, rule, source}` and `open_question` is
  `{before, answer, after, handler, outcome}`, written by the dialogue module. The drawer's
  Focus and Open question panels render them, and render "No focus rule fired this turn"
  when empty. Evidence: pytest on the trace, vitest on the panels.
- AC-1036 [T] The ideation lane still reads and writes only `session_vars.ideation`.
  Evidence: existing ideation tests green.
- AC-1037 [UX] No new motion. The settings field, the Shadow filter chip, the drift badge and
  the drawer panels use existing primitives and presets only. Evidence: review.

## Lane 2 - multi-domain fan-out

- AC-1040 [T] "SRTWT2634 stock and eta" renders ONE message: a Stock section, then an
  Incoming section, in that order, then one escalate line. Two tool calls, two `tool` trace
  events. Evidence: world.
- AC-1041 [T] "stock for A and eta for B" renders Stock listing A only and Incoming listing B
  only. The binding lasts one turn: a bare "C" next turn runs C through both domains.
  Evidence: two-turn world.
- AC-1042 [T] "stock and eta for A and B" renders each section listing both products.
  Evidence: world.
- AC-1043 [T] After a fan-out answer, a bare code reruns every alive domain for the new code.
  Evidence: world.
- AC-1044 [T] After a fan-out answer, "PO?" sets `focus.domains = [purchase_order]`, keeps
  the product, renders one section. Evidence: world.
- AC-1045 [T] "promo for CWCX7605" after a fan-out answer replaces both domains and product.
  Evidence: world.
- AC-1046 [T] Sections render in the dealer's order (the `asks` order), never a canonical
  order. Evidence: world "eta and stock for X" renders Incoming first.
- AC-1047 [T] Nothing prints twice, by one general deduper keyed `(entity id, domain)` shared
  by every section and every ladder rung, for any domain in `DOMAIN_SPEC`; a later renderer
  skips a printed key and a section with every key printed is omitted. "stock and eta for X", no stock,
  incoming exists: one Stock section reading "No stock for X, but there is incoming: ...";
  no Incoming section. Both empty: the ladder climbs past the asked set to PO and the closing
  line appears once. The trace lists the consumed pairs. Evidence: three worlds.
- AC-1048 [T] A domain the contact is not granted renders its section as the existing
  one-line denial copy; the other sections render; no ladder runs for the denied domain.
  Evidence: world with a dealer lacking `purchase_orders.placed`.
- AC-1049 [T] An ambiguous product on a fan-out ask offers ONE `product_pick` and nothing
  else; the pick then fans out over every alive domain. Evidence: two-turn world.
- AC-1050 [T] When a `tier_pick` (promotion) and a `product_pick` would both arise, the
  product is asked first; the tier is asked on the following turn. Evidence: world.
- AC-1051 [T] The escalate offer opens only when at least one section missed (today's
  conditions, per section); every section found means no offer. Teams are the deduped set of
  `DOMAIN_SPEC[d].escalation_team` over the MISSED domains: no stock but incoming found offers
  Warehouse only. One team: today's yes/no offer. Two or more: "Would you like me to escalate
  to Warehouse or Purchasing?" with one numbered quick reply per team plus "No it's okay",
  stored as `team_pick` with those options. "1" picks the first team; a team label picks by
  equality; a bare "yes" re-asks with the same buttons; "no" renders the declined copy.
  Evidence: six worlds.
- AC-1052 [T] The date window applies only to domains that take one; "stock and DO last
  month" filters the order section and leaves stock unfiltered. Evidence: world.
- AC-1053 [T] No cap: a four-domain ask makes four tool calls and four trace events.
  Evidence: pytest with a fake MCP.
- AC-1054 [FE][E2E] The turn drawer shows one `tool` entry per domain, the consumed pairs
  under Cross-domain, and the Focus panel lists `domains` in order. Evidence: agent-browser
  run over a fan-out console turn.

## Supersession map (growth-r1 section D)

| growth-r1 | here |
|---|---|
| AC-940 | AC-1006 |
| AC-941 | AC-1010, AC-1003 (TTL reversed: no counter, owner 12 Sep) |
| AC-942 | AC-1007 |
| AC-943 | AC-1008 |
| AC-944 | AC-1014 |
| AC-945 | AC-1015 |
| AC-946 | AC-1009 |
| AC-947 | AC-1016 |
| AC-948 | AC-1017 |
| AC-949 | AC-1022 |
| AC-950 | AC-1032 |
| AC-951 | reversed by AC-1033 (owner, 12 Sep 2026: no mirrors) |
| AC-952 | AC-1027 to AC-1031 |
| AC-953 | AC-1011 |
