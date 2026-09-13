# PLAN - Chatbot focus + multi-domain: one dialogue state, then fan-out

Status: APPROVED by owner 12 Sep 2026 on the lavish page ("best quality and the shortest time"); lane 1 `feat/chatbot-focus` S0 to S4 BUILT 13 Sep (backend green on the lane DB, replay 1791, one head 517), S5: reviews CLOSED 13 Sep, pre-PR gate green at 09d5a3af3, DRAFT PR opening 13 Sep; browser verification + owner console pass PENDING (frontend slot); lane 2 `feat/chatbot-multi-domain` stacked after. Two lanes, two PRs. S6 sticky roster (D19) BUILT 13 Sep, review round closed at d72420498 (2 blockers + the owner's B3 promo-menu report + 5 should-fix + 3 nits). S7 multiple-matches picker armed + dash fold at the send boundary BUILT 13 Sep at 3dcb9fb1f. S7c prefix-code pin BUILT 13 Sep at e42eee65b (replay 1791 unmoved, chatbot suite 4224, resolve/intersection files 484, one head 517); owner re-pass on :3081 pending.
UAC: `chatbot-focus-multi-domain-acceptance-criteria.md` (AC-10xx).
Supersedes: Slice B of `PLAN-chatbot-growth-r1.md`. CORRECTION 12 Sep: its lane
`feat/chatbot-growth-dialogue` WAS built, locally, never pushed: 14 commits, 42 files,
+7,253 / -358, in the worktree `.claude/worktrees/chatbot-growth-dialogue`, based on main at
#711 (7 Sep) and 48 main commits behind. Lane 1 starts FROM that branch (see "Lane 1 base").
Growth-r1 section D maps onto this UAC, see its supersession table.
Predecessors: `PLAN-chatbot-turn-engine.md` (LIVE), `PLAN-chatbot-growth-r1.md` lanes 1 and 3
(MERGED), `PLAN-broaden-domain-switch.md` (the last patch on the carry rules this plan
deletes).

## Why

The owner wants one turn to answer stock, incoming and PO for a product, and the next turn
to keep working whether the dealer types a new code, a new domain, both, or a picker number.
The engine cannot do that today because every piece of state that would have to hold two
domains holds one: `domain_hint`, `last_result_set`, `picker_domain`, `pending.team`,
`pending.domain`. Bolting arrays onto the flat 34-key bag means threading them through 75
`domain_hint` reads in `head/output_exchange.py` (3,361 lines) and the 47 key assignments in
`tail/compile_state.py::compile_current_state` (lines 271 to 971). That is the same cost as
the approved Slice B, in a worse shape.

Measured demand is small (3 of 337 distinct real messages name two domains). This is an
owner ask, made on 12 Sep 2026, recorded as such.

## Owner decisions (grill, 12 Sep 2026)

| id | decision |
|---|---|
| D1 | Two lanes. Lane 1 = dialogue state with `domains` a list from day one. Lane 2 = fan-out, stacked. |
| D2 | Fan-out only when the message names 2+ domains. The miss ladder keeps covering the zero case on single-domain asks. A per-contact "always full report" default is deferred; trigger: owner asks after seeing lane 2 in prod. |
| D3 | Parser emits `asks: [{domain, entities[]}]`, dealer order. No `domain_hint`, no `intent_hint`, no top-level `entities`. Engine flattens at intake. |
| D4 | One WhatsApp message, one headed section per domain, one escalate line. |
| D5 | The escalate offer opens only when something was missed (as today: not-found and zero branches). Its teams are the teams of the domains that MISSED, not of every domain rendered. One team: today's yes/no. Two or more: one question with a button per team plus "No it's okay", each option numbered, so "1" picks the first team and a bare "yes" re-asks with the buttons. |
| D6 | One open question at a time. A pick resolves the entity, then every alive domain reruns. Product before tier. |
| D7 | A domain word with no product REPLACES `focus.domains`. Never appends. |
| D8 | No persisted mirrors of the 34 legacy keys. The world grader maps. |
| D9 | No counter, no TTL (owner reversed growth-r1 D11 on 12 Sep: a dealer cannot see a turn count). A focus slot is cleared only by a new entity of the same axis, a topic reset, or the Respond.io "conversation closed" event the SLA path already receives. An open question is cleared only when answered, replaced by a newer question, or when the dealer starts a new ask (a message carrying a domain or an entity); casual and low-signal messages leave it open. `member_offer` loses its TTL 3 and follows the same rule. No settings field. |
| D10 | Parser v3 ships as a new registry version; corpus replay green, then a shadow window on prod the owner watches in the console, then the owner promotes. Extra LLM cost accepted. |
| D11 | Sections in the order the dealer said them. |
| D18 | Estimate given 12 Sep: lane 1 about 3 to 4 working days of build, lane 2 about 2, the shadow window (owner's watch, 3 to 7 days) running alongside lane 2. The wide bars are L1-S3 (reply semantics, 72 test files) and parser v3 replay iterations. |
| D12 | No repeated information, by a GENERAL deduper: a fact key `(entity id, domain)` prints once per message whichever section or rung produced it. Not special-cased to stock / incoming / PO. |
| D13 | A denied domain renders its section as the existing denial copy. |
| D14 | `intent_hint` is dropped from the parser, the state and the trace. Every domain has exactly one intent (measured 13:13). |
| D15 | The low-signal clarifier receives `focus_hints`. `casual` still receives nothing. |
| D16 | No fan-out cap. |
| D17 | Deferred, triggers unchanged: episodes (L2 retrieval), profile, learning from corrections, answer LLM (D1 of growth-r1 stands: no answer LLM). |
| D19 | Owner, 13 Sep 2026, after the console pass on :3081 ("why my dym pick does not stick like before" / "need to restore"): a pick does NOT consume its roster. Restores ruling K rule 1 (6 Sep, AC-816) and the 7 Sep deviation 5, superseding AC-1014's close-on-answer clause the 12 Sep UAC introduced. A ROSTER question (`product_pick`, `customer_pick`, `tier_pick`) stays open after a pick, options frozen, `asked_at_turn` unchanged; a later bare number re-resolves against the same frozen roster. It clears only by the existing rules (a newer question of another kind, `topic_reset`, a message naming its own subject, conversation-closed). The one-team yes/no escalate offer that a pick's rerun-miss produces RIDES on the roster question instead of replacing it: `kind`/`options`/`asked_at_turn` stay the roster's, `expects` becomes `pick_or_yes_no`, `payload.offer` carries `{team, domain, options}`; a number re-picks, `yes` runs escalation and consumes the whole question, `no` declines and the roster stays with the offer stripped. Non-roster kinds (`team_pick` clarify, `company_pick`, `member_offer`) keep today's consume-on-answer behaviour. `OPEN_QUESTION_EXPECTS` gains `pick_or_yes_no` (`contracts.py`). |

## Found during S6 verification (13 Sep 2026)

Three defects the console pass and the browser run surfaced, each fixed in S7. They are
recorded here because two of them are older than this lane and would otherwise read as
S6 regressions.

| what | root cause | where fixed |
|---|---|---|
| The "multiple matches" picker did not survive: `incoming wc286` printed ten numbered products and the next `8` answered nothing (owner, turn 26b15a53-87a8-43be-8e55-5839b3ce3149) | LANE-INTRODUCED at L1-S3d. The five-key session replaced `last_result_set` / `selection_context` with `open_question`, and four of the five roster labels were converted; `disambiguation` was not, so the tail armed nothing and the escalate offer won by default. The did-you-mean roster was unaffected because its own lane freezes it (`miss_suggest._attach_question`). | `_ask_for_turn` gains the `disambiguation` arm, before the offer arm, reading its rows from `last_result_set`, then `specific_options`, then `compatible_entities` |
| A yes/no the customer was never shown was persisted on that same turn | PRE-EXISTING. `is_escalate_offer = not is_clarification` (`tail/outcome.py:148`) and `pickers.annotate_incoming` sets `is_clarification: False` on a numbered PICKER "for parity with the not-found require_specific branch", so the flag asserts an open offer on a turn whose reply ends at row 10. | the offer arm now also requires the reply to carry the frozen "Would you like me to escalate to" phrase; the flag itself is untouched, since other readers depend on it |
| A picked row whose code is a PREFIX of its siblings answered about all of them: picking row 10, `SRTWC286-SH-NEW`, of ten also answered for `-150`, `-P` and `-200` (owner, chain G, turns 00c7c844 -> 7620187b). Everything upstream was right: the roster froze rows 1..10 in render order, the pick resolved to `picks: [10]` and the one correct uuid, and the incoming tool was called with that single `product_ids`. | PRE-EXISTING. `resolve_entity_body` built `entity_pins` only when `match_mode != "and"`, and a bare pick emits `"and"` by default, so the uuid the customer had just chosen was dropped from the request; the resolver re-derived the bare token, and the product fold strips hyphens, so `SRTWC286SHNEW` matched four products. Rows 8 and 9 worked only because their codes are nobody's prefix. Byte-identical on origin/main. | S7c, owner ruling "a pin means this token IS this row": the body always sends its pins, and `references.py` narrows a pinned token on the intersection (`_apply_intersection_pins`) instead of rejecting the pin in AND mode |
| One clarifier turn produced two console bubbles, the second carrying a U+2014 in customer-facing text (tester, chain E) | PRE-EXISTING ON MAIN. The casual lane builds its `send_message` from the clarifier's RAW words before the tail runs, and the tail's fold reaches only the sealed reply - so one turn carried two texts differing by one character, and `console_service._customer_texts` de-duplicates by exact equality. | `sanitize_dashes` (em AND en) at the process boundary: the row `_close_turn` writes, `TurnResult` / `CompleteResult`, and `_attachments_src`. The tail's fold stays em-only, because six graded captures carry a U+2013 in a field it walks |

## What exists (origin/main 62e911e, 12 Sep 2026)

| thing | where |
|---|---|
| session read | `app/services/chatbot/engine.py:417` `_read_session_vars` over `conversation_variables_service.get_for_contact` |
| session write | `engine.py:3066` `overwrite_for_contact` inside `run_tail`, after `compile_current_state` at `engine.py:3001` |
| the stage runner | `engine.py:1099` `_run_stages`; `understood` at 1198 to 1264, `post_process` call at 1225, `suggest_follow_up` at 1226 |
| carry rules | `head/output_exchange.py`: `post_process:970` / `_post_process:997` to 3303; K4 block 395 to 431 and its application at 2128; K2 at 2393; `_switch_word_domain:652`; `_query_brands_carried` at 1705; `_tier_carried` at 1733; AXIS BROADEN at 1400 and 3286; `derive_routing:73` (hard-codes the team per domain, duplicating `DOMAIN_SPEC.escalation_team`); `_team_clarify_pick:789`; dym pick application and reference positions at 1800 to 1870 |
| state compiler | `tail/compile_state.py:271` `compile_current_state`, the `variables` literal at 725, `_partial_dym_block:1380`, `_picker_carry:1723`, `_offer_carry:1858`; `tail/pending.py` writes `pending`; `tail/member_offer.py` |
| business lane | `lanes/business/__init__.py`: `run_until_exit:56` (engine 1452) then `resolve_gate.run:669`; `run_fetch:204` (engine 1526) picks `select_tool(domain)` at 307; `complete_answer:450` (engine 1984) calls `run_crossdomain` at 603 and `build_result` at 623; `miss_suggest.run_miss_lane:1271` builds the dym / sibling / partial-miss roster |
| contracts | `contracts.py`: `DOMAIN_SPEC:88`, `PENDING_KINDS:576`, `SESSION_VAR_KEYS:589`, `Pending:629`, `SessionVars:650`, `Envelope:707` (`shadow_of` at 726), `INGRESS_KINDS:527` |
| parser | `head/parser.py:73` `_build_json_schema`; prompt text `app/services/chatbot_parser_prompt.py` (100,585 bytes); registry key `chatbot_semantic_parser` at `ai_prompt_registry.py:788`; versions are published by data migrations (475, 480, 487, 490), each a new unlabelled version; promote = `AIPromptService.set_label` (`ai_prompt_service.py:281`) via `POST /ai-assistant/prompts/{name}/labels` |
| clarifier | `lanes/casual.py`, key `chatbot_clarifier`, `construct_user_prompt:154` blanks state for `casual` and `unknown` |
| shadow | `chatbot.turns.shadow_of` is written from the envelope at `engine.py:560`; nothing reads it |
| settings | model columns in `app/models/user.py` (567 to 595); schema `SystemSettingUpdate` at `api/v1/user_management/settings.py:20`; GET dict at 379 to 384; `_CHATBOT_COLUMN_DEFAULTS` at 645 to 658; FE `app/(protected)/user-management/settings/chatbot/page.tsx` + `services/chatbotSettingsService.ts`. `chatbot_crossdomain_ladder` is NOT on the FE page yet |
| console | `api/v1/system/chatbot.py`: `list_turns:145` (params `contact_respond_id, from, to, status, limit, cursor, include_test`), `get_turn:295` with `trace_detail.compose_trace_detail:242` (nine keys); FE `app/(protected)/system-management/chat-history/`: `TurnPanel.tsx`, `StateTracePanel.tsx` (Parser drift chip row at 59), `TurnDetailDrawer.tsx`, `hooks/useChatbotTurns.ts`, `services/chatbotTurnService.ts:121` |
| tests | `tests/chatbot/worlds.py` (`World.session_vars` input, `expected_variables` target, `body_difference:536`, `drop_paths:524`), `test_worlds.py` reads `respond_contacts.session_vars` at 252 and strips `pending` at 104; `test_replay.py` grades node captures; `divergences.py`; 72 test files import `output_exchange`, 11 import `compile_state`; CI runs the whole `tests/` sweep |
| migrations | highest prefix 512 (two files, `512_hidden_by_default_col` and `512_integration_ref_company`); this lane numbers from 513 and re-parents with `./scripts/alembic-reparent.sh` at PR time |

## Lane 1 base: the unpushed `feat/chatbot-growth-dialogue` branch

What it already has (worktree `.claude/worktrees/chatbot-growth-dialogue`, HEAD `ba13cabbc`):
`dialogue/decay.py` (per-slot turn TTL, `focus_hints`, `open_question_hint`),
`dialogue/focus.py` (the carry rules as named functions: `replace_same_axis`,
`reset_on_topic`, `reuse_alive`, `reuse_domain_entityless`, ...), `dialogue/open_question.py`
(one typed question, `OPEN_QUESTION_KINDS`, frozen options, one resolver), `Focus` /
`FocusSlot` / `OpenQuestion` contracts, parser v3 keys (`answers_open_question`, `anaphora`,
`topic_reset`) published as an unpromoted registry version by a data migration, engine
wiring, `compile_state` writing `focus` + `open_question`, seven owner worlds, and tests
(`test_focus_decay.py`, `test_focus_rules.py`, `test_open_question.py`, `test_parser_v3.py`).

What it does NOT have, and lane 1 adds or changes (each is a delta on that branch):

| delta | why |
|---|---|
| merge `origin/main` (48 commits; 18 overlapping files, `output_exchange.py`, `compile_state.py`, `engine.py`, `parser.py`, `contracts.py` among them) | the branch predates growth-r1 lanes 1 and 3, the broaden-domain-switch fix and the answer polish |
| renumber its migrations `488_chatbot_focus_ttl`, `489_chatbot_parser_v3`, `490_chatbot_turn_run_id` (main already owns 488 to 491) to `513+`, and DROP `488_chatbot_focus_ttl` + `system_settings.chatbot_focus_ttl_turns` entirely | D9: no TTL |
| `decay.py` becomes `clearing.py`: no `ttl_turns`, no `is_alive` by age; clear on conversation-closed marker and on a new ask; `open_question.ttl_turns` removed | D9 |
| `focus.domain` becomes `focus.domains` (list); parser schema replaces `domain_hint` + `intent_hint` + top-level `entities` with `asks[]`; `intake.flatten` | D3, D14 |
| `SESSION_VAR_KEYS` shrinks to the five keys; every mirror the branch still writes (`picker_domain`, `pending`, ...) goes; grader mapping in `worlds.py` | D8 |
| shadow parse + `ingress = shadow` + console filter, badge, summary, drawer column | D10 |
| clarifier receives `focus_hints` | D15 |

The branch's decay tests retire with the rule; its focus-rule and open-question tests are
kept and extended. Its `test_worlds.py` expectations are re-derived through the mapping.

## Design

### Persisted state (lane 1)

`respond_contacts.session_vars` keeps its JSONB column and its wholesale `FOR UPDATE` write.
The shape becomes:

```
{
  focus: {
    domains:     {value: ["inventory", "incoming"], set_at_turn, set_at, source},
    products:    {value: [entity], ...}, customer, transporter, warehouse,
    date_window: {value: {start, end, mode}, ...}, attributes, tier, brands
  },
  open_question: {
    kind: "product_pick" | "customer_pick" | "tier_pick" | "team_pick" | "company_pick" | "member_offer",
    expects: "pick" | "yes_no" | "free",
    options: [{idx, label, uuid, code, domain, ...frozen row}],
    asked_at_turn, asked_at, payload
  } | null,
  ideation: {...as today},
  access_levels: [...],
  contains_flyer: bool
}
```

`SessionVars` is `extra=forbid` over those five. `Focus`, `FocusSlot`, `OpenQuestion` are
Pydantic models in `contracts.py`. `SESSION_VAR_KEYS`, `PENDING_KINDS`, `Pending` go.
`chatbot_parser_shadow_version` is one new `system_settings` column (migration
`513_chatbot_parser_shadow`), exposed through `SystemSettingUpdate`, both dict builders, and
one field on the chatbot settings page. No new table: one writer,
one reader, one row per contact (PRINCIPLES "one preference does not need a table").

### The dialogue module (lane 1)

New package `app/services/chatbot/dialogue/`, pure functions, no DB, no LLM:

- `clearing.py::apply(session, parse, conversation_closed)` applies D9: clears every slot on
  a conversation-closed marker, clears the open question when the parse carries a new ask
  that is not an answer to it, returns the trace lines (`decay` key in `trace_detail` keeps
  its name; its entries read `{slot, reason}`).
- `hints.py::focus_hints(focus)` and `open_question_hint(oq)` build what the parser and the
  clarifier see. Typed, alive slots only, option labels only.
- `intake.py::flatten(parse)` turns `asks[]` into `domains[]`, `entities[]` and the per-turn
  binding `{domain: [entity index]}`.
- `focus.py::apply(prev_focus, parse, resolved, turn_no)` runs, in order,
  `replace_same_axis`, `reset_on_topic`, `reuse_alive`, `domains_from_asks`,
  `date_restated_only`, `anaphora_reuses`, `confident_guard`. Each is a named function
  returning `(focus, trace_line)`. The outputs keep the axis executor's
  `clear / reuse / modify / replace / replace_combine` vocabulary so `resolve_gate` and the
  lanes read the same shapes they read today.
- `open_question.py::resolve(oq, parse, quoted_options)` dispatches on `kind` to one handler
  each (`product_pick`, `customer_pick`, `tier_pick`, `team_pick`, `company_pick`,
  `member_offer`) and returns an outcome the engine acts on: `focus_patch`, `lane`
  (`business`, `escalation`, `declined`, `none`), `trace`.
- `open_question.py::ask(kind, options, payload, turn_no)` is the ONE constructor every
  lane uses to open a question; `idx` is assigned here, from 1, across the whole roster.

### Turn order (lane 1)

`engine._run_stages` changes in four places:

1. `received`: after `_read_session_vars`, `clearing.apply`, then `hints`. The parser call takes
   `focus_hints` and `open_question_hint` instead of the previous reply text and the raw
   state.
2. `understood`: parser v3 schema; `intake.flatten`; `post_process` shrinks to the emission
   assertions and `derive_routing` (which now reads `DOMAIN_SPEC[d].escalation_team` and
   keeps only the certificate split). Every carry rule listed under "What exists" is
   deleted.
3. NEW `answered` (before `access`): if an open question is alive and
   `answers_open_question.resolved`, `open_question.resolve` runs; its `focus_patch` applies
   and its `lane` overrides routing. An open question that is not answered survives a casual
   or low-signal message; a new ask cleared it at `received` (D9).
4. `focus.apply` runs after `resolve_gate` (it needs the resolver's `entity_type` and
   `confident`); `run_fetch` and `complete_answer` read products, customer, date window and
   domain from `focus`, not from `qf`.

`run_tail`: `compile_current_state` keeps building the reply text and quick replies; its
`variables` output becomes `{focus, open_question, ideation, access_levels, contains_flyer}`
assembled from the dialogue module's outputs. `_partial_dym_block`, `_picker_carry`,
`_offer_carry`, `tail/pending.py` and the `dym_offer` ladder are replaced by
`open_question.ask` calls at the point each lane decides to ask.

`trace_detail` keeps its nine keys; `decay`, `focus[]` and `open_question` are now populated
by the module, so the drawer panels shipped in PR #733 render without change beyond the
`domains` list.

### Parser v3 and the clarifier (lane 1)

Schema (strict, `head/parser.py`): removes `domain_hint`, `intent_hint`, `entities`,
`scope_intent`, `broaden_axis`, `reference_positions`, `reference_target`; adds
`asks: [{domain, entities: [entity]}]`, `answers_open_question: {resolved, picks: [int],
yes_no: bool|null, free_text: str|null}`, `anaphora: bool`, `topic_reset: bool`. Every other
key stays. Prompt v3 text lives beside v1 in `chatbot_parser_prompt.py` and is published as
a new unlabelled version by data migration `514_chatbot_parser_v3`; the `production` label
moves only by the owner's hand (D10). The prompt no longer contains "continue the previous
turn", "keep the previous domain" or "re-emit previous entities"; it receives `focus_hints`
and `open_question_hint` as structured JSON under a fixed heading.

Clarifier prompt v2 (`chatbot_clarifier`, migration `514` too): `construct_user_prompt` sends
`focus_hints` + `open_question: none` for `low_signal` and `unknown`; `casual` sends nothing.
The instruction: ask for the one axis the alive focus lacks for the alive domains.

### Shadow parse (lane 1)

When `chatbot_parser_shadow_version` is set, `run_turn` enqueues (same offload path as the
live turn, fire-and-forget, after the live turn's row is inserted) a shadow job: run the
parser at that version over the same envelope and the same hints, insert a `chatbot.turns`
row with `ingress = "shadow"` (new `INGRESS_KINDS` member), `shadow_of` = the live
`message_id`, `status = done`, the parse in `trace`, no reply, no session write, no send.
A shadow failure is a `failed` shadow row and never touches the live turn.

Console: `list_turns` gains `ingress` as a filter and, when `ingress = shadow`, a `summary`
in the response: `{count, branch_parity, asks_parity}` computed over the filtered rows by
joining each shadow row to its live row on `message_id`. FE: a "Shadow" filter chip on the
chat-history list (`ChatbotTurnFilters` gains `ingress`), a drift `Badge` on a shadow row
when `branch_kind` or `domains` differ from the live row, the summary line in the list
header, and the drawer's Parser drift panel showing live and shadow parse side by side (it
already has the chip row; the side-by-side is one new column).

### Fan-out (lane 2)

`run_fetch` loops `focus.domains` in order; for each domain it runs `select_tool(d)` with the
entity list bound to `d` (or every entity when unbound) and the date window when
`_domain_takes_a_date_filter(d)`. One envelope per domain, one `tool` trace event each.
A domain the contact is not granted yields a `denied` envelope instead of a tool call.

`complete_answer` renders one section per envelope in order. One general deduper:
`printed: set[(entity_id, domain)]`, shared by every section and every ladder rung. Whoever
renders a fact for entity X under domain D first adds `(X, D)`; any later renderer (a section
or a rung, for any domain in `DOMAIN_SPEC`) skips it; a section with every entity already
printed is omitted. After the sections, the ladder climbs only to rungs OUTSIDE the asked
set for codes empty in every asked section, once. A denied envelope renders the existing
denial line and runs no ladder. `tail/compose.crossdomain_compose` writes ONE escalate line.

Escalation: the offer opens only when a section missed (the same `escalate_catalog` /
`offer_open` conditions as today, evaluated per section). Teams =
`{DOMAIN_SPEC[d].escalation_team for d in MISSED domains} - {None}`, deduped, in section
order. Every section found: no offer. One team: today's yes/no (kind `team_pick`, one option,
`expects: yes_no`). Two or more: `team_pick` with `expects: pick`, options numbered from 1,
one quick reply per team plus "No it's okay"; "1" picks the first team, a team label picks by
equality, `yes` re-asks with the same buttons (handler outcome `reask`).

`derive_routing` keeps the certificate split for `product_attachment` and otherwise reads
`DOMAIN_SPEC`; the per-domain `if` chain is deleted.

### Simplest thing that works, checked

- No new table, no memory service, no episode store. Two columns, one package of pure
  functions, one schema change.
- No registry of handlers: `open_question.resolve` is a `match` on six literal kinds.
- No answer LLM; sections are the existing envelope renderer called N times.
- The ladder mechanism is reused, not rebuilt; the only addition is the consumed set.
- `focus` slots carry the four fields the trace needs and nothing else.

## Slices

### Lane 1 - `feat/chatbot-focus` (PR 1, branched from `feat/chatbot-growth-dialogue`)

| slice | scope | ACs |
|---|---|---|
| L1-S0 | Base: branch `feat/chatbot-focus` off `feat/chatbot-growth-dialogue`, merge `origin/main`, resolve conflicts, existing chatbot suite green on the lane DB `sorento_ai_automation_focus`; then contracts + settings: `Focus`, `FocusSlot`, `OpenQuestion`, new `SessionVars`; migration `513_chatbot_parser_shadow` (one column); `SystemSettingUpdate` + both dict builders; FE page field "Parser shadow version" (clearable `SearchableSelect` over `GET /system/chatbot/console/prompt-versions`); `external/conversation_variables` schema; the conversation-closed marker on `respond_contacts.session_vars` written by the existing SLA close path | AC-1001, 1002, 1004, 1013, 1028, 1034 |
| L1-S1 | `dialogue/` package, pure, fully tested: clearing, hints, intake, focus rules, open_question ask/resolve with six handlers | AC-1003, 1005, 1008, 1010, 1011, 1012, 1016, 1017, 1019, 1020, 1021 (flatten half) |
| L1-S2 | Parser v3 schema + prompt text + migration `514` (parser v3, clarifier v2); clarifier hints; replay assertion | AC-1021, 1022, 1023, 1024, 1026 |
| L1-S3 | Engine wiring (`received`, `understood`, `answered`, focus apply), business lane reads focus, `compile_current_state` writes the five keys, delete the carry rules and `tail/pending.py`; world grader mapping; divergences; trace population | AC-1006, 1007, 1009, 1014, 1015, 1018, 1025, 1032, 1033, 1035, 1036 |
| L1-S4 | Shadow: enqueue, `ingress = shadow`, list filter + summary, FE chip + badge + summary line + drawer column | AC-1027, 1029, 1030, 1031 |
| L1-S5 | Owner console pass (`console_cases/2026-09-xx-focus.yaml`), guide, DoD | AC-1037 |
| L1-S6 | Sticky roster (D19): `pick_or_yes_no`, `open_question.ROSTER_KINDS` / `carry_after_answer` / `with_offer`, the tail's carry, the offer merge in `_arm_cross_domain_offer`, `offer_is_open` | AC-1014 (amended), AC-1018, AC-1020 |
| L1-S7 | Found during S6 verification (below): `_ask_for_turn`'s missing `disambiguation` arm, the offer arm gated on the frozen phrase, and the dash fold at the process boundary | AC-1013, AC-1014, AC-1020 |
| L1-S7c | Found during S7 verification: a uuid pin is honoured in AND mode, so a picked prefix code stays one product | AC-1014, AC-1017 |

L1-S3 is the slice that changes reply semantics. Rule for the 72 test files importing
`output_exchange`: the `tester` lists, before the coder starts S3, which tests assert a
deleted rule (they retire with the rule, in the tester's commit, with the rule name in the
commit body) and which assert behaviour that now lives in `dialogue/` (they are ported as
tests of the named rule). The coder deletes no test. `test_replay.py` captures for
`output_exchange` retire with the function; world captures stay through the grader mapping.

### Lane 2 - `feat/chatbot-multi-domain` (PR 2, stacked on lane 1)

| slice | scope | ACs |
|---|---|---|
| L2-S0 | `run_fetch` loop with binding + denial envelopes; `complete_answer` sections + consumed set + closing ladder; `_domain_takes_a_date_filter` per section | AC-1040 to 1048, 1052, 1053 |
| L2-S1 | Team set, `team_pick` multi-option, `yes` re-ask, `derive_routing` on `DOMAIN_SPEC` | AC-1051 |
| L2-S2 | Picker before fan-out, product before tier; worlds; console case yaml; drawer check | AC-1049, 1050, 1054 |

## Testing seams (agreed before Phase 2)

- `dialogue/*`: pure functions, pytest per rule and per handler, no DB.
- Parser and clarifier: fake provider returning a fixed v3 emission; prompt render asserted
  as text.
- Engine: worlds (`tests/chatbot/worlds.py`) with a fake MCP and the Postgres fixture; every
  AC tagged "world" is one `World` entry, multi-turn where stated.
- Console: pytest on `list_turns` with `ingress=shadow`, vitest on the badge, the chip and
  the summary line, agent-browser for the E2E ACs.
- Settings: pytest on both dict builders, vitest on the field.

## Phase 1 (frontend, mocked)

Small: one settings field, one filter chip, one badge, one summary line, one drawer column.
Built first against a mocked `chatbotTurnService` and `chatbotSettingsService`, verified with
agent-browser by sidebar clicks at 375px and 1280px. No motion: the chip, badge and panels
use the existing primitives only (AC-1037).

## Hazards

- **Parser v3 regressions.** The gate is the corpus replay (every capture flattened and
  graded on `asks` and `answers_open_question`), then the shadow window. The `production`
  label does not move in a migration.
- **World grader drift.** The mapping function is the one place legacy expectations are
  translated; a world that cannot be mapped is a registered divergence with a reason, never
  a silent skip.
- **Worker.** Shadow jobs ride the same offload path; a lane that edits `app/tasks/*`
  restarts its worker session (CLAUDE.md).
- **Two 512 migrations on main.** `./scripts/alembic-reparent.sh` at PR time; single head
  asserted before marking ready.
- **`response_model` drops undeclared fields.** The list summary and `ingress` are asserted
  in a route test.
- **Both dict builders.** The new settings column is asserted in the GET and the PUT.

## Deferred (triggers)

| deferred | trigger |
|---|---|
| per-contact "always full report" default | owner asks after seeing lane 2 in prod (D2) |
| `domains_op: add` ("also PO?") | corpus shows "also / and / 还有" asks after a fan-out answer |
| episodes, profile, learning from corrections | growth-r1 triggers unchanged (D17) |
| shadow of the clarifier | parser shadow shows a clarifier-caused drift class |
