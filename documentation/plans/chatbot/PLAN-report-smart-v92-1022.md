# PLAN: sales reports on parser v92 (lane REPORT-SMART-L, round S1, 22 Oct)

Status: plan, posted to #1816 for crew; code starts after the crew-note. Track: L (parser prompt fields, report access
scope change, cross-lane prompt coordination). Branch `claude/report-smart-1021-r2xexf` rebuilt on
`crew/chat-release-1022` 237424152b (merge #1721 + 23 lane commits, head c925b50327, one alembic head). UAC:
`report-smart-v92-1022-acceptance-criteria.md`.

## Goal

The owner's 21 Oct script on parser v92 (EVAL-BENCH note 6316652256, run `rs1816_rs515_index.jsonl`): step 4 "ordered"
re-asks the period, step 5 "..., dealer sales only" opens a customer picker, step 6 stays in it, step 8 adds a dealer
channel nobody said, step 9 asks period + how many, step 13 "top 10 dealer selling X" ranks sales agents. Plus: counts
and period-over-period compare reachable from chat, "my sales" for a salesperson, and the report rate limit checked.

Owner rulings 22 Oct: (1) the two parser fields (count measures, `compare_to`) may be added to the prompt, additive
only, no override rules, measured on parser gold + hidden; (2) "my sales" for a salesperson = sales of THEIR customers
via the linked CRM user, no name matching; the full agent ranking stays with the sales report grant; (3) no proactive
digest.

## Diagnosis (traces in `sorento_explore1020` chatbot.turns, code at 446eddd92f, unchanged on this head)

| step | v92 parse (what differs from v77) | where it goes wrong | layer |
|---|---|---|---|
| 4 "ordered" | `state_changes [switch_domain]` on a bare refine (v77 `set basis`, rejected) | step 3's answer turn stored domain `order`: `SALES_RANKING_ASK.reroute` (report_ask.py:262) is laid on by `required_fields.reply_verdict` (engine.py:5338) AFTER the report-domain seam (engine.py:5106). Held `order` vs message `sales` -> switch at chat_state.py:1545 -> `_drop_domain_bound` drops the frame -> fresh ask, period blocked (report_ask.py:819-821) | CODE (+ parser op) |
| 9 "amount, delivered" | `[switch_domain]`, held domain already `sales` | the explicit op alone switches onto the domain held (chat_state.py:1523, :1545); frame and its top_n drop -> "Which period? How many?" | CODE (+ parser op) |
| 5 re-typed ask + dealer | `order_status` null, kind in `intent_hint "sales_ranking"` + `asks[{sales, sales_ranking}]`, ranking_refine null | no sales status -> `sales` demoted to `order` (turn_runtime.py:1919-1924); `take_words` skips (report_ask.py:359); the resolver re-types "Water Closet" as a customer under `order` (entity_resolver.py:135-137) -> customer_pick (turn/apply.py:2446-2481) | PARSER |
| 6 "qty, delivered" | `[answer]` over the customer pick | consequence of 5: the mis-typed category rides `Focus.extra` back to the resolver (engine.py:5881, after `take_words` :5366) | CODE (consequence) |
| 8 total for all agents, Sep | `sales_channel dealer`, `measure qty` never said (copied from the previous conversation's Recent exchanges) | the lane runs what was parsed (report_ask.py:619-624) | PARSER |
| 13 top 10 dealer selling X | `group_by sales_agent`, `sales_channel dealer` (v77 `group_by customer`; prompt line 297 says customer, channel null) | the lane runs what was parsed | PARSER |

Shared: v92 emits `switch_domain` on every bare refine, and the State honours an explicit switch onto the held domain;
the answering turn stores `order` over a sales frame. v77 passed 4 and 6 only because its `set basis/measure` ops were
rejected.

## Changes (each red-first, live v92 shapes, >= 8 varied messages per case: en, zh, ms, mixed)

ARCHITECTURE. Layers: the State's domain reading (one normalisation for both sides) and the parser prompt (fields and
rules). Shared mechanism: `turn_runtime.report_domain` (the one report-domain normalisation) applied at apply()'s one
verdict entry, where `coerce_domain_hint` already runs (turn/apply.py:3410), so every writer of a sales verdict stores
`sales`. Other classes fixed: every sales figure ask answered through a required-field question (ranking, total,
analysis, top selling), every explicit `switch_domain` the parser emits onto the held domain. Special cases removed:
none added; no message words read.

- C1 (steps 4, 9; code). (a) apply() entry normalises the report domain (`report_domain`) next to
  `coerce_domain_hint`, so an answering turn's rerouted `order` is stored as `sales`. (b) `chat_state.apply_changes`:
  a `switch_domain` whose target domains are all held is no switch (logged as `switch_onto_held`); only a target not
  held drops the domain-bound axes. Tests: chat_state unit + state-on console (`_state_on`) with the v92 shapes.
- C2 (step 6; code). The held brand / category words of a sales figure ask stay the lane's (`report_ask_words`) and
  never go back to the generic resolver from `Focus.extra` on a sales figure verdict (the top selling shield at
  engine.py:5909 widened to `SALES_FIGURE_STATUSES`).
- P1 (parser, additive, ruling 1). Schema `measure` enum qty|amount|customers|orders|products, new `compare_to`
  previous_period|last_year (head/parser.py:319 schema, `required`, TOLERATED_ABSENT); prompt lines in
  head/parser_template.py (:316 measure sentence, :362 closed list) as in crew-note 6308995565. The lane already reads
  both (report_ask.py:208, :210, :625, :857).
- P2 (parser rules, steps 5, 8, 13; drafted here, handed to CHAT-CLOSED-LISTS-L who owns the prompt): the report kind
  goes in `order_status`, never `intent_hint`; Recent exchanges never fill `sales_channel`, `measure`, `basis` or
  `group_by` when no State holds them; "dealer" as the ranked noun is `group_by customer`, channel null; a bare refine
  of the report on screen carries no `switch_domain`.
- P3 (measure). One candidate prompt version (v92 + P1 + P2) registered by crew / EVAL-BENCH; parser gold rows
  (`scripts/chatbot_eval/gold/`, >= 8 per case, generic wording) + the hidden set, v92 vs candidate, then the 10 script
  turns replayed live on the candidate. Budget: rows x repeats parser calls, under 300 calls/lane/day.
- A1 ("my sales", ruling 2). Report-ask route (api/v1/order_management/report_ask.py): classify the asker with
  `contact_asker.classify` (services/contact_asker.py:135). A salesperson (role-user linked to the contact) is
  narrowed to customers whose `sales_agent_id` is the agent linked to that contact (`sales_agents.contact_id`), the
  chat-report route's pattern (report_ask.py:633-645). "My sales" comes off the parser's `self_reference`
  (head/parser.py:336). The sales_agent axis and agent filters stay behind GRANT (:43, :354). Access tests: dealer,
  salesperson, staff, unknown contact; security-reviewer runs.
- R1 (rate limit, check only). Per Respond contact, fixed window, 10 reports / 10 minutes, fails open when Redis is
  down (services/rate_limit.py:41-66; report_ask.py:378, :383, :611); configurable in System Settings
  (`report_ask_rate_limit`, `report_ask_rate_window_minutes`, models/user.py:640-641; 0 = unlimited). No code change
  proposed; eval copies set the limit to 0.

## Open questions (crew-note, recommendation first)

1. Salesperson WITHOUT the sales report grant: (a) may ask "my sales" (own customers, any axis but sales_agent),
   (b) still 403. Recommend (a): ruling 2 says the grant gates the full agent ranking, not own-customer sales.
2. Salesperson WITH the grant: (a) "my sales" narrows to own customers, a plain ask stays unscoped, (b) always
   narrowed. Recommend (a).
3. P2 lines: (a) I draft and measure them in the same candidate as P1, CHAT-CLOSED-LISTS-L reviews and owns the merge,
   (b) CHAT-CLOSED-LISTS-L writes them. Recommend (a): one measured candidate, one owner of the prompt file.
4. Rate limit: (a) no change, (b) key it on the linked CRM user instead of the contact. Recommend (a).

## Out (named)

Proactive digest (ruling 3). Step 15 ("total sales SEP 2026" -> "Sorento or Mocha?", the company pick) unchanged.

## Gates

Red-first per change (`test(red):` commits), kill test per fix, touched suites `-n 2` on `sorento_rsl_throwaway`,
reviewer + security-reviewer (A1), parser gold + hidden v92 vs candidate, the 10 script turns live on the candidate.
