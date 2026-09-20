# PLAN - Chatbot: re-attach the production answer half to the new turn engine

Status: APPROVED by the owner 20 Sep 2026 on `.lavish/chatbot-answer-half-reattach-plan.html` ("follow all your
recommendation, except the cap needs to be configurable, actually I prefer 10"). R1 to R4 done; R5
("production decides") done this round, folded together with the narrow-arm retirement R6 was
scoped to separately (the single-domain roster suppression the R5 design needed IS that
retirement, for `kind == "product"` - done in the same commits; R6's own remaining job is
deleting the now-fully-dead `_ASK_HEADERS` text duplicates and re-recording the `prod_sample`
replay fixtures the design rule changed, not a second design pass).
Owner direction given 20 Sep 2026 (hand pass 8): "agree with the structural change to make this
robust and scalable and be general to all scenarios". Same lane, same PR: `feat/chatbot-turn-rearch`
(#952), tester branch `test/chatbot-turn-rearch-red`. UAC: `chatbot-answer-half-reattach-acceptance-criteria.md`
(AC-1680 to AC-1711). Parent plan: `PLAN-chatbot-turn-rearch.md`.

**Correction (coder 29, 20 Sep 2026):** the bridge module lives at
`app/services/chatbot/answer_bridge.py`, a SIBLING of `turn/` (not `turn/answer_bridge.py` as
first written below) - `turn/`'s own purity guard forbids any file under that package from
importing `chatbot.tail`, and the bridge imports `tail.outcome`/`tail.reply`/`tail.compose`
freely by design (captain ruling 20 Sep 2026). Every "F COMPOSE" reference to `turn/answer_bridge.py`
below means this module.

## Why

Eight hand passes each found "one more" production behaviour missing: the access-level picker with
its has/no promotion stamps, the "Here's what you want" breakdown, the Customer / Product / Dates
scope block, did-you-mean with stamps, the cross-domain stock ladder, the CS member picker. They are
not eight defects. They are one: the parent plan said "the composers, resolver, gate, fetch,
escalation and outer loop are not rewritten", and the build rewrote the composers anyway.

## Measured (coder worktree at 484c79d92, 20 Sep 2026)

| fact | where |
|---|---|
| Production business lane = `run_until_exit` -> `run_fetch` -> `complete_answer`. The new path calls `run_gate` and `run_fetch` only. | grep from `turn/`, `turn_runtime.py`, `engine.py`: zero callers of `complete_answer`, `not_found_error_message`, `build_breakdown_msg`, `miss_suggest`, `dym_annotate`, `run_until_exit` |
| The retired half is about 2,300 lines of production copy and probes; `turn/compose.py` (537) + `turn/narrow.py` (467) stand in for it | `answer.py:2576-3494`, `miss_suggest.py` (1,431), `answer.py:245-335` |
| `resolve_gate.run` ALREADY runs on every business turn and ALREADY returns `{resolved, gate, aggregate, tier_gate, _exit_kind}`. `resolve_kinds` keeps seven derived values and drops the rest | `turn_runtime.py:709-717`, return at `:815-825`; `resolve_gate.py:1063-1143` |
| The entry is hard-coded: `branch_kind="business_query"` and entry `"resolve"`. The `access_check` arm (tier gate, entitlement aggregate, `access_ask` exit) is unreachable, so `run_fetch`'s `tier_ask` arm is dead code | `engine.py:1474`, `turn_runtime.py:711`, `lanes/business/__init__.py:45-49`, `:1026-1053` |
| `make_tool_runner` hands the fetch a SYNTHETIC gate `{"compatible_entities": entities}`; the real gate (`gate_reason`, `require_specific`, `company_team`, `customer_probe_entities`, `gate_debug.allowed_lookup`) never reaches a composer | `turn_runtime.py:1115-1118` |
| The old tail's text ladder is still alive and green: `tail/outcome.escalate_catalog` + `tail/reply_ladder.compose_reply`, used by the canned lanes through `engine.run_tail` | `engine.py:3073-3250`, `FRAGMENT_FIELDS` `engine.py:2884-2896` |
| A roster -> `Pending` converter already exists for the deploy-migration path | `session_state.py:26-34` (`_LEGACY_PENDING_KIND`), `:70` (`_legacy_option`) |
| Security seams sit upstream of every composer and are untouched by this plan | `lanes/business/fetch.py:2105-2188`, `turn_runtime.py:1746`, `lanes/business/__init__.py:1209-1219` (security review of `c9967c34b..484c79d92`, 20 Sep) |

### The three live bugs, root causes

| bug | cause | where |
|---|---|---|
| One-option roster echoing the typed token ("SRTWT165-FT CERT", "Incoming srtwt7202-new", "Technical drawings sttwc286-SH") | (i) `narrow._token_of` does not fold `[-\s]+` while `turn_runtime._token_key` does since `b32b0a500`, so the `unplaced` guard never matches a hyphenated code; (ii) `narrow_to_code` rosters on ONE candidate, `must_narrow_one` correctly needs two | `turn/narrow.py:41-43`, `:386`, `:437-438` |
| Incoming miss, then stock for 50 unrelated products | `_without_guesses` empties `compatible`; `_answered_unfiltered` returns False for an EMPTY entity list; `_climb` re-runs the tool runner with the empty spec, so `crm_inventory_stock_balance_list` runs with no product filter. Production probes per product code and cannot do this. Security review N-1, now seen live | `turn_runtime.py:1562-1563`, `turn/fetch.py:126-182`, `answer.py:1124` |
| Pick a customer or tier, then "No matching results found" when the product token is a family prefix; "has DO" stamped on a customer with no DO for that product | The gate's picker arms REPLACE `compatible_entities` with the picker rows, so the new path sees no product on the asking turn: `probe_customer` gets a customer-only list (production passes `customer_probe_entities`, which carries the product), and the product is never settled on the focus. On the answering turn `filters["product"]` is written and has no reader | `gate.py:1053-1061`, `:864-866`, `:975-979`; `turn_runtime.py:776-783`, `:1086-1093`; `turn/narrow.py:466` |

## Design

One rule: **the new engine decides WHICH turn this is; production decides WHAT the reply says.**
Parser verdict, focus, pending state, routing and grants stay where the parent plan put them. Every
customer-facing word of a business answer, picker or miss comes from the production composer that
already owns it.

```
C APPLY    unchanged: state', plan
E FETCH    resolve_kinds returns a ResolveOutcome (today's seven values PLUS the resolve_gate.run
           payload it already computes); the real branch_kind goes in; the REAL gate reaches the
           tool runner. No second resolver call, no new I/O.
F COMPOSE  single-domain business turn: turn/answer_bridge.py
             exit access_ask / tier-ask -> answer.access_level_choice_message
             exit offer                 -> the gate's own annotated picker
             miss                       -> _run_miss_half (not_found_error_message + miss_suggest)
             hit                        -> _run_answer_half (validator, promo_picker,
                                           run_crossdomain, build_result, sub_answer)
           text   = tail/outcome.escalate_catalog + tail/reply_ladder.compose_reply (alive today)
           pending = session_state._legacy_option + _LEGACY_PENDING_KIND, minted via pending.ask
           -> Answer{text, question, offer, files} -> the EXISTING _run_answer and turn/tail.py
           multi-domain fan-out, outstanding / sales report / forms asks, team pick:
             turn/compose.py, as today (production has no composer for these on this path)
G TAIL     unchanged: one tail, one session writer
```

`turn/answer_bridge.py` is the ONE seam. It calls the production composers with the arguments
`complete_answer` gave them, unchanged, so `test_s6c_answer_lane.py`'s byte-for-byte node grades
keep holding. It adds no copy string.

Narrowing follows production, not a second policy: a product roster only where
`gate.REQUIRE_SPECIFIC_DOMAINS` rosters (incoming, product_attachment); a customer roster from the
gate's own arm; an access-level picker from the tier gate; everywhere else a product token is a
silent prefix filter at the fetch. `turn/narrow.py` keeps `not_applicable`, `list_all`,
`optional_filter`, `narrow_by_type` and the `ledger_family_*` helpers. Before its roster arms are
deleted the coder lists every ask `narrow.decide` raises that production does not; each is either
covered by a signed ruling (AC-1119's outstanding-report product ask, the S19 sales report family
prefix) and moves to the lane question that owns it, or is deleted.

**Grant before roster (security SF-1).** Main's R-S3 check lives in `run_until_exit`, which the new
engine never calls. The check moves to the one place both engines pass through before the resolver
runs, so a contact without `sales_orders.sales_report` reads the refusal and never a customer
roster. `run_fetch:1209-1219` stays as the second line.

**Roster cap (owner ruling 20 Sep 2026): configurable, default 10.** One integer column,
`chatbot_entity_kinds.roster_cap` (NOT NULL, server default 10), edited on the existing Chatbot
entity kinds config screen beside `did_you_mean`. It is read at the ONE place a roster is cut:
the gate's customer arm (`gate.py:938`, today a literal 8), the gate's product arm and the
did-you-mean list. `turn/narrow.py::_ROSTER_CAP` leaves with the roster arms. A preference is a
column on the row that already exists per kind; no settings table, no registry.

### Deleted, in the same commit that makes the production composer live

| deleted | replaced by |
|---|---|
| `turn/compose.py` `_ASK_HEADERS` for product / customer / tier / attachment picks, `_REQUIRE_SPECIFIC_HEADER_DOMAINS`, the "Did you mean:" header, the miss + escalate-offer block, "I could not find X." | `gate.py:857-859`, `gate.py:1044`, `answer.py:312-314`, `build_suggest_offer`, `not_found_error_message` |
| `turn_runtime._alternatives_ask`, `_alternatives_ask_text`, `_resolve_dominant_neighbours` | `miss_suggest.dym_transform` / `dym_annotate` |
| `turn/narrow.py` roster arms (`narrow_to_code`, `must_narrow_one`, `narrow_by_tier`) and `_options` | `run_gate`, `access_level_choice_message` |
| `turn/fetch.py::_climb` re-using the primary spec | `answer.run_crossdomain` (per product code) |

### Simplest thing that works, checked

- No new table or registry. One new module (the bridge), one widened return value, one integer
  column the owner asked for (`roster_cap`).
- Net line count goes DOWN: about 600 lines of re-implemented grammar leave `turn/`.
- Rejected: routing business turns through `engine.run_tail`. Smaller diff, but it is a second tail
  and a second session writer, and a multi-domain `Answer.sections` has nowhere to go in it.
- Rejected: keep porting per finding. Eight hand passes are the evidence.

## Slices (each ends green; one coder, continued; all on #952)

| slice | change | closes | model |
|---|---|---|---|
| R1 | The two pure defects. `narrow._token_of` folds like `_token_key`; `narrow_to_code` needs two candidates; `_answered_unfiltered` treats an empty entity list with a non-empty `unplaced` as unfiltered; `_climb` refuses a rung with no entities. Tester's measured correction (`test_rearch_r1_answer_half_reattach_defects.py`): the unconditional one-option roster arm is reached by `narrow_by_tier` on a non-tier kind too, not `narrow_to_code` only as guessed above - both share the same fallthrough arm and both needed the fix | F8 roster half, F9 leak, security N-1 | Sonnet |
| R2 | `ResolveOutcome` out of `resolve_kinds`; real `branch_kind`; real gate into `make_tool_runner`; grant-before-roster. Nothing consumes the payload yet | security SF-1; F2 stamp scope (`customer_probe_entities`) | Opus (cross-cutting seam) |
| R3 | Bridge arms `access_ask` and `offer`; `roster_cap` column + config field | F2 copy + company suffix + stamps, F3, F6 | same coder |
| R4 | Bridge arm miss (`_run_miss_half`), compose miss block and `_alternatives_ask` deleted | F4, F7, F8 did-you-mean, F9 ladder copy | same coder |
| R5 | Bridge arm hit for single-domain plans (`_run_answer_half`); family-prefix filter reaches the fetch after a pick | F1, F2 pick-then-miss, F5 | same coder |
| R6 | Delete the dead `narrow` arms and `_ASK_HEADERS` duplicates; re-record the `prod_sample` replay fixtures that pinned the new grammar | - | same coder |

Tester first on every slice (red branch). Phase 3 once for the lane: `reviewer` +
`security-reviewer` (Opus: grant ordering, company scope, the re-enabled tier probe) + journey run.
Guide-writer: no user-facing screen changes; the chatbot guide's reply examples are re-checked.

## Testing seams (agreed before Phase 2)

- **Parity corpus is the gate.** Every production reply the owner pasted in hand passes 7 and 8
  becomes a journey chain asserting production text (`tests/chatbot/journeys/parity-*.json`), run
  live by `scripts/chatbot_journey.py` against :8081. Rulings are assertions; parity is measured by
  the runner, not by the owner's hand.
- One structural pytest per invariant, parametrized over every business domain rather than one
  scenario: no production copy string exists twice (source scan of `turn/`); `resolve_gate.run`
  is called once per domain per turn; a rung never runs with an empty entity list; an ungranted
  report ask reaches no resolver.
- `test_s6c_answer_lane.py` (18 answer-half nodes, byte-for-byte) and `test_replay.py` (868) must
  stay green untouched: the bridge changes callers, not nodes. `test_turn_replay.py` fixtures that
  were re-recorded through the new grammar are re-recorded again, with a signed
  `replay_turns/DIVERGENCES.md` entry each.

## Hazards

- **Multi-domain answers.** A production composer is single-domain; `reply_ladder` emits one
  string. R5 is scoped to single-domain plans. A fan-out keeps `turn/compose.py`; a fan-out that
  misses on two domains keeps today's copy. Trigger to revisit: the owner reports a multi-domain
  reply that reads wrong.
- **Sticky roster (contract 36).** The legacy carry has no `answered_positions`. A bridged roster
  is minted through `pending.ask` so `with_answered_positions` still layers onto it.
- **Multi-select access level ("1 and 2", "all").** `decision.positions` is already a list; the
  tier resolver in `apply._answer_pending` must accept more than one. Pinned red first.
- **The tier probe has not run on this branch since S3.** `lanes/business/__init__.py:1026-1053`
  is production code with no live coverage here; R3 re-enables it, and it costs one MCP probe per
  entitled tier on a promotion ask, as production does.
- **Argument reshaping is the real regression risk**, not the composers. The bridge must build
  `payload`, `fetch`, `parser` and `ctx` in `complete_answer`'s own shapes.

## Deferred (triggers)

| deferred | trigger |
|---|---|
| production composer for multi-domain misses | owner reports one reading wrong |
| parser contract consolidation (dialogue acts + slot diff, prompt trim) | after #952 ships; owner has not ruled |
| B3 "chun chun" roster padding (`_and_token_match_counts` counts a repeated word twice) | owner ruled 20 Sep: leave it |
| production composer for multi-domain misses | owner ruled 20 Sep: keep today's copy until one reads wrong |
