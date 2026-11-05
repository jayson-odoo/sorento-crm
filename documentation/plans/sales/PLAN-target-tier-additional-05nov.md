# PLAN: tier "Additional" as a column (lane TARGET-TIER-ADDITIONAL)

Status: Plan - waiting on owner answers to the card (crew-ask on the PR). Track: TBD (likely full: migration).

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

So the engine pays 6% + 1% + 1% = 8%. The spreadsheet says tier 2 = 6% + 1% = 7% = 5,375.57.

## Proposed model (pending answers)

- `target_commission_tiers` gains `additional_kind` (`pct` | `amount`) + `additional_value`
  on each main tier row; only the reached tier's additional pays.
- Periods rate cell: "A/C I 6.00% + 1.00%" or "+ RM x".
- Existing `is_additional` rows fold onto the main row of the same period + threshold
  (dry-run report first, owner approves apply).

## Count query (read-only)

See the PR crew-note.
