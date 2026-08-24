# PLAN - Centralized Total Project Value validation (portal == system)

**Status:** Implementing
**Owner:** jayson
**Slug:** project-value-centralized-validation

## Problem
1. **Edit form doesn't preload the value.** The internal edit/create "Total Project
   Value" input binds to `total_project_value_text` (descriptive column), but the
   value lives in `total_project_value` (numeric). A record with `1234` shows blank
   on edit. Not dev-server slowness - a field-binding bug.
2. **Inconsistent validation.** Portal submit rejects non-numeric + too-large
   (Numeric(15,2) overflow). Internal create/update guards too-large but used to
   route non-numeric → text. No single source of truth.

## Decision
Strict numeric **everywhere** (portal + system create/edit). One shared validator.
`total_project_value_text` becomes legacy **display-only** for old rows; new writes
never populate it.

## Validator (single source of truth)
`app/services/validators.py::validate_project_value(raw) -> Optional[Decimal]`
- `None` / `""` → `None`
- non-numeric → 422 "Total project value must be a number."
- `abs(value) >= 10^13` (Numeric(15,2) range) → 422 "Total project value is too large (max 9,999,999,999,999.99)."
- else → `Decimal`

## Backend wiring
- `portal_service._apply_payload` - replace inline coerce+range block with the validator.
- `procurement_service` create (~4541) + update (~4695) - `total_project_value = validate_project_value(...)`; create sets `_text=None`; update leaves existing `_text` untouched (don't clobber legacy).

## Frontend
- `purchase-request-schema.ts` - `total_project_value` gets a numeric+range schema (separate from line `quantitySchema`).
- `PurchaseRequestForm.tsx` + `PurchaseRequestDocumentEditCard.tsx` - bind the visible input to `total_project_value` (number input, preloads); stop rendering/sending `_text`.
- Portal `SubmissionForm.tsx` - TPV field becomes a number input.

## Tests
- pytest: `tests/test_project_value_validator.py` - numeric, non-numeric, too-large, empty, negative, Decimal/int/float/str inputs.
- pytest: portal submit + procurement create/update reject non-numeric and too-large.
- vitest: `PurchaseRequestForm` preloads `total_project_value` into the input.
