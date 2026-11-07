# PLAN: distance to the next tier and what it would pay (AGENT-COMMISSION-WA)

Status: Merge-ready (reviewer READY after round 1; crew-done). Track: small fix (registry + one helper, no migration, no new
permission). Size S.

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
  commission, with no knowable threshold (points, no ratio) or on a pct target of 0. A replaced dealer period would
  pay 0 (the replacing target's tier does not move).
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
(W13: none on the hidden per-period entity), lines only when asked (W14, W21); review round 1: live period (W15, W22), three-way split (W16), negative account (W17), no ratio / no tiers (W18), replaced (W19), quantity units (W20).
