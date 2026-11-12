# PLAN: chatbot honest scoreboard (CHATBOT-SCOREBOARD, work-order lane 3)

Status: in progress (small fix track: no migration, no auth change, no user-visible change).

UAC: `chatbot-scoreboard-acceptance-criteria.md` (alongside).

## Problem

The weekly chatbot scoreboard (crew-side SQL, two statements) over-counts misses and failures:

1. The dealer quantity question ("How many units of X?") is recorded as outcome `answered_empty`,
   so it lands in the outcome version of couldn't-find (1b). `_stock_ask_reply`
   (`app/services/chatbot/engine.py:9952-10065`) returns the reply with `sections=[]` when it asks
   a quantity, `looked_up.sections` records 0, and `turn_outcome`
   (`app/services/chatbot/analytics/outcome.py`) calls 0 sections `answered_empty` because the
   question is neither a clarify branch, a plan ask nor a `required_ask`.
2. Pick-one menus on `answered` turns (`replied.facts.asking` = `product_pick`, `customer_pick`,
   `tier_pick`, ...; engine.py:10243) are counted as answered: the classifier never reads
   `asking`.
3. Technical failures count every `send_unconfirmed` turn, though most of them have an outgoing
   `chat_histories` row (`chatbot_turn_id`, `delivery_status` delivered/read).
4. There is no dead-end line (couldn't find, and no code offered) and no one-line weekly summary.

## Architecture

| Layer | Change | Mechanism |
|---|---|---|
| Analytics classifier (pure) `app/services/chatbot/analytics/outcome.py` | Two more structured "asked back" signals in `turn_outcome`'s clarify rule | (Q) the turn's `state` event (engine.py:10269, written after the answer) holds a `stock_qty` task with `status = open` and `touched_at_turn = turn_no`: the reply asked a quantity. (P) `replied.facts.asking` is a question kind that is not an escalation offer (`turn/pending.ESCALATION_OFFER_KINDS`, reused) and not a did-you-mean (`state.open_question.payload.did_you_mean`, dealer_stock.py:117-127): "Couldn't find X. Did you mean Y?" stays a miss (brief). No reply text is read. |
| Facts history | none in code | Existing `scripts/chat_facts_sweep.py --since ... --rebuild` (`facts.sweep(rebuild=True)`, facts.py:338) re-stamps past facts under the new rules. Prod run = crew/owner action after release. |
| Scoreboard SQL `app/services/chatbot/analytics/scoreboard.sql` (crew's file moved into the repo, same definitions) | Statement 1 and 2: technical split into engine vs delivery, delivery = `send_unconfirmed` with no outgoing `chat_histories` row for the turn; new stock couldn't-find + dead-end columns. Statement 3 (new): one line per week. | Read-only SELECTs, one parameter `p.week_from`. Dead-end = stock couldn't-find (outcome `answered_empty`/`missed`, intent `check_stock`) whose reply offered no product pick (`replied.facts.asking` is not `product_pick`). |

Classes/functions reused: `outcome._stage`, `outcome._events`, `outcome._still_asking` pattern,
`turn/pending.ESCALATION_OFFER_KINDS` (pending.py:216), `facts.sweep(rebuild=True)` +
`scripts/chat_facts_sweep.py`. No new table, no new job (crew sends the weekly line).

## Steps

1. Import crew's scoreboard.sql unchanged (baseline commit).
2. `test(red):` classifier tests (quantity question, pick menu, did-you-mean stays a miss, offer
   after an answer stays answered) + scoreboard SQL test on a Postgres fixture with fake rows
   (delivered-but-unconfirmed not technical, dead-end line, weekly line).
3. Fix classifier + SQL. Kill test.
4. Before/after on the dev copy (`sorento_prod_1112`, read-only): classifier re-run in Python over
   the window's turns, SQL with and without the delivery join.
5. Reviewer subagent. crew-tests line.

## Standing rules that apply

AI/chatbot: "no keyword, regex or word-list rules" (the classifier change reads structure only);
"Reuse functions" (ESCALATION_OFFER_KINDS, sweep rebuild). Everything else n/a (no UI).

## Open (not this lane)

- Prod facts rebuild after release (`scripts/chat_facts_sweep.py --since 2026-09-21 --rebuild`):
  crew asks the owner.
- The no-push / stale-stock alert: out of scope (owner: shared-service problem).
