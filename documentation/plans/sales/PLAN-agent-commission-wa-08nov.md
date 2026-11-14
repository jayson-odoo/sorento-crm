# PLAN: distance to the next tier and what it would pay (AGENT-COMMISSION-WA)

Status: Re-pass pending after the owner 14 Nov ruling (agent reply = model text only): the code-built next-tier reply is removed, the tool returns each row's next-tier lines with an instruction, capped lists page on "more" (offset). Reviewer READY on 35e99316, fe74c008, e7a07f0e (the #2420 merge) and 5f651cfb (paging); crew re-pass and owner hand test to run. Track: small fix by
kind (registry + agent query helpers, no migration, no new permission). Size M after the paging and model-reply rounds.

Wave W-A of `PLAN-agent-commission-all-08nov.md` "Next waves". Stacks on #2242
(branch `claude/agent-commission-dealers-teams-tvf434`); retarget to main after #2242 merges.

Question: "How far is Agent A / dealer D1 / Team T1 from the next tier, and what would it pay?"

## What exists (no new calculation)

| Piece | Where |
|---|---|
| Tier ladder of a period (rungs sorted by RM threshold, rates per account) | `app/services/sales/target_service.py` `tier_ladder` |
| Reached rule (target of 0 on a pct target = 100%) | `target_service._reached`, engine `commission_service.payout_for` `reached` |
| Next rung + gap, already read by the chat target lines | `target_service.period_progress` `next_tier` |
| The one engine | `target_service.period_payout` -> `commission_service.payout_for` |
| The assistant's batched per-period figures | `target_service.period_figures` |

## Built

- `target_service._next_tier` (called from `period_figures`, key `next_tier`): the first rung of `tier_ladder` not
  `_reached`, and `period_payout` on the achievement raised to that rung's threshold. None at the top tier, without
  commission, with no knowable threshold (points, no ratio) or on a pct target of 0. Since #2262 (dealer targets
  stack, per-account payout) there is no replaced period, and a tier's RM bonus pays one bucket only, as the engine
  says.
- Fields on `agent_target_summary` (per subject; not on the hidden per-period `sales_target`, which has no note to state the assumptions, review S2): `next_tier`, `next_tier_at`,
  `to_next_tier`, `next_tier_payout`, `next_tier_gain`. On the summary the numbers are filled only when the subject
  has one commission target in the window; its live period is today's, else the last one started by today.
- Note (`_summary_note`), only when the question uses a next-tier field: one line per commission target, "tier N at
  RM X, RM Y to go, would pay RM Z (RM W more than now)", "(closed)" for a past period, "has reached its top tier".

Owner card (crew answer 8 Nov, both (a)):

- Q1 dealer with per-account rates: the rest is assumed in the account mix sold so far (split evenly when nothing is
  sold); the line says so in plain words and names each account's rate when they differ.
- Q2 a subject with several targets: per-target lines, the row's numbers empty (no summed distance).

## Fixed live regression set (crew runs it live x3 on the Mac; no Gemini key in the cloud)

Keep #2242's set as it is, plus:

1. How far is Agent A from the next tier this month, and what would it pay?
2. How much more does Agent B need to sell to get commission this month?
3. How far is dealer <dealer name> from its next tier this quarter, and what would it pay?
4. Same question by one of the dealer's account codes.
5. How far is Team <team> from the next tier?
6. Which agents are closest to their next tier this month? (sorted by `to_next_tier`)
7. Agent with two live targets: answered target by target, no summed distance.
8. An agent already at the top tier: says so, no invented next tier.
9. As a view_own salesperson: own agent answered, a dealer or team question answers "not visible to you".

## Tests

`sorento_crm_backend/tests/chatbot/agent/test_agent_commission_wa.py` W1-W14: agent next tier and would-pay (W1,
W2), top tier (W3, W7, W8), kill test the would-pay equals the page after the sale lands (W4), two targets (W5),
dealer (W6), per-account mix and even split with rates (W9, W10), view_own (W11), index hint (W12), per-period rows
(W13: none on the hidden per-period entity), lines only when asked (W14, W21); review round 1: live period (W15, W22), three-way split (W16), negative account (W17), no ratio / no tiers (W18), quantity units (W20); W19 (replaced) retired with #2262.

## Shape rounds (crew live x3 on 0c5c7b78 and bb85f8b5)

Figures were right every run; the shape was not stable. Owner rule (4 Oct, 28 Oct): understanding is semantic only,
never a regex or word list on the message. So `crm_query` takes `next_tier` (distance | closest | furthest) and
`subjects` (agent | dealer | team | all), set by the model; `agent_target_summary`'s `spec_hook` (`sales._next_tier_spec`)
forces the next-tier columns, the distance ranking and the kind filter, refuses closest / furthest without `subjects`
(the model asks the user), and a next-tier call is about the periods containing today (one period basis).
`query_tools.shape_reply` builds the reply from the calls' arguments and data: the next-tier tables alone (no payout
lead line, no targets table), the one "No agent target has a commission ladder this period." line, a same-turn
payout or other answer kept, a named subject not found kept unless a full ranking covers it, and `final_reply`'s
not-done lines. Tests: `test_agent_commission_wa_shape.py` N1-N14, R1-R15.

Semantic round: #2242's `strip_self_agent` and `_user_named` read the message text. Now the model's `about_self`
argument says a question is about the asker; `query_as_asker` runs the call as given and drops the asker's own name
only when the call ran and found nothing (`test_agent_commission_wa_semantic.py` S1-S12). Deferred as rare: a name
variant that is not part of the stored name ("Mr Teh") still counts as a named miss.

## Model-written reply (owner 14 Nov; crew code gate on 2cfc3f83)

The agent's reply text is the model's only: no system-built or system-appended text (a structured card UI may
stay). `query_tools._distance_reply`, the next-tier branch of `shape_reply` and the `admitted` plumbing in
`loop.final_reply` are gone; `shape_reply` leaves a next-tier call untouched. The tool returns the data instead:
each `agent_target_summary` row carries `next_tier_lines` (one sentence per live commission target: period, tier,
threshold, to go, would pay, the mix and rates it assumes, or top tier), the note keeps only what is about the rows
as a whole (no ladder, no target set, no commission set, not visible), a next-tier page is at most 10 rows and never
a card, and the result carries `DISTANCE_INSTRUCTION`, `more` and `next_offset`. The model writes the lines, the
notes and the 'Reply "more" to see the next N.' line itself.

Paging (crew pass L85): `crm_query` takes `offset` on the SQL and computed paths, rows and groups; a cut card ends
with `composers.sets.more_line`; a page past the end keeps the list's own count.

Tests: `test_agent_commission_wa_model_reply.py` MR1-MR7 (the final text is the model's), `..._paging.py` P1-P14.
The shape tests that asserted a code-built reply (N2, N3, N8, R2, R5-R7, R9-R11, R13-R15) are retired; the ones about
the query stay as data checks. Open, not this lane: main's generic `shape_reply` still rewrites labels, appends scope
notes and puts a card under the model's first line for other crm_query answers.
