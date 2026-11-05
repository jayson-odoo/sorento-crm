# PLAN: tier "Additional" as a column (lane TARGET-TIER-ADDITIONAL)

Status: Review - built per owner answers 5 Nov 11:10 (+ 11:30 grids/lightbox, 11:40 header/KPI markup); fold apply waits on owner approval of the dry run. Track: full (migration). UAC: `target-tier-additional-05nov-acceptance-criteria.md`.

## Why

Owner, 5 Nov: put the additional 1% on the tier row itself ("A/C I 6 + 1 %") instead of separate
"+ Additional from X" rows, and could not reproduce 6,143.52 for A CRAFT IDEA A/C I Q1.

## How 6,143.52 is computed today (measured)

`sorento_crm_backend/app/services/sales/commission_service.py`, `payout_for`:

- retroactive (line 140-143): highest main tier reached is 75,000 at 6% ->
  76,793.92 x 6% = 4,607.6352 -> 4,607.64.
- additional (line 155-159): EVERY "+ Additional" row whose own threshold is reached pays its own
  line: from 60,000 1% = 767.9392 -> 767.94; from 75,000 1% = 767.94. From 85,000 not reached.
- each line is rounded on its own then added (line 18-21, ruling 3):
  4,607.64 + 767.94 + 767.94 = 6,143.52 (one combined 8% would be 6,143.51).

So the engine pays 6% + 1% + 1% = 8%. The spreadsheet says tier 2 = 6% + 1% = 7%: 4,607.64 + 767.94 =
5,375.58 (two lines, each rounded; one combined 7% would be 5,375.57).

## Model (owner answers 5 Nov 11:10)

- `target_commission_tiers.additional_rate` (the % Additional, new); the RM Additional reuses
  `bonus_amount` (owner Q2), now paid for the reached tier only. Only the reached tier's
  Additional pays (replaces the 16 Oct Q5 stacking).
- Periods rate cell: "A/C I 6.00% + 1.00%" or "+ RM x".
- Existing `is_additional` rows fold onto the main row of the same period + threshold
  (dry-run report first, owner approves apply).

## Conflict with an earlier ruling

Stacking was ruled on 16 Oct (`PLAN-dealer-sales-targets-15oct.md:68`, Q5; example E2 at `:119`,
additionals at 220,000 / 250,000 that sit on no tier). Asked on the PR which rule wins.

## File map (for the build)

- Engine: `sorento_crm_backend/app/services/sales/commission_service.py` (`payout_for`, 155-159).
- Model: `sorento_crm_backend/app/models/sales.py:524-575` (`SalesTargetCommissionTier`).
- Schemas: `sorento_crm_backend/app/schemas/sales.py:429, 668, 724`.
- Service: `target_service.py` tier save (~600-700), engine input (~1351), Periods rungs
  (~2240-2290, `additional_rates` already paired by threshold).
- Import: `dealer_target_import.py` (`RateEntry.is_additional`, 724-756, 1158-1200, 1380-1460).
- FE: `sorento_crm_frontend/app/(protected)/sales/targets/components/TargetRecord.tsx`
  (Type select 105 / 2234, view 2093) + `types/salesTarget.types.ts`.
- Existing tests: `tests/test_dealer_targets_engine.py` (E2 asserts stacking).

## Count query (read-only)

See the PR crew-note.
