# PLAN: Target commission view + shareable commission statement (TARGET-COMMISSION-VIEW)

Status: Built, reviewed (round 1 fixed), browser pass done 1280/375; awaiting owner hand test (standard track: export surface, no migration). PR #2164.
Mock: `mockups/target-commission-view-04nov.html` (owner approved 4 Nov, "ok").
UAC: `target-commission-view-04nov-acceptance-criteria.md`.

Lane TARGET-COMMISSION-VIEW. Coordinates with TARGET-INVOICED (#2162): that lane adds the
Invoiced basis (`_achieved_invoiced`); the document breakdown for Invoiced targets follows on
rebase (trigger: #2162 merges).

## Journey
The owner opens Sales > Targets > TGT-000008 (A CRAFT IDEA SDN BHD 2026 quarterly) and asks: about
6k earned? paid to which account? what is the 1,235.58? Then: "we need to better visualize,
because I want to send to stakeholders to cross check".

## Owner answers (4 Nov, card)
- Q1 xlsx only. Q2 one row per document. Q3 no paid tracking ("Payment is not tracked in the CRM").
- Q4 earned to date = ended periods; the current period apart, "so far, not final".
- Q5 Accounts tab: sales per account per period + a period total row with the commission and the
  account it pays to; commission never split per selling account.

## Design (one computation)
- `target_service.target_detail` gains per-period `tier_rates` (the reached main tier's rates,
  from `tier_ladder`, the engine's own ordering) and target-level `commission_to_date` /
  `commission_current` (`_earned`).
- `achievement_service.achieved_by_period_and_line`: the achievement statement grouped also by
  sales order line, so document rows add up to Achieved by construction.
- `target_service.commission_statements` = `target_detail` + documents + tier table per period.
- `commission_statement_xlsx.build` writes it (openpyxl). Route
  `GET /api/v1/sales/targets/commission-statement?ids=` (view permission, at most 50 targets).
- FE: commission summary card above the tabs; Periods: Tier reached, Rate, Pays to, Total row;
  Accounts: per period rows + Period total; gear item Export commission statement; Targets list
  bulk action Commission statement (N). Commission figures RM with 2 decimals; the commission
  surfaces show dates dd/mm/yyyy.

## Not built (triggers named)
- Paid / not paid tracking: when finance wants to record payouts in the CRM.
- PDF statement: when a stakeholder asks for a non-editable copy.
- Invoiced document breakdown: when #2162 merges (rebase, group `_achieved_invoiced` by doc).
