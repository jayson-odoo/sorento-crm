# PLAN: sponsorship form requires a unit price on every line

Status: Track: small fix - in review (round 1 addressed, awaiting merge). Issue #1227.
Branch `fix/sponsorship-unit-price-required`, PR #1232.

UAC: `sponsorship-unit-price-required-acceptance-criteria.md`.

## The ruling

Owner's ask (25 Sep 2026, verbatim): "make the unit price in sponsorship form mandatory
upon portal submission, in system edit and create also, make sure we use the same
validation as what we already did in portal forms."

`request_type = purchase_request` is unchanged everywhere. Existing sponsorship forms
already stored without a price are not migrated - only a new submission, create, or edit
is refused.

## The seam

Three independent surfaces build/validate a sponsorship line, each already had its own
precedent to extend rather than a new pattern to invent:

- **Dealer web portal** (`(auth)/portal`) - `SubmissionForm.tsx` posts through
  `saveDraft`/`submitDraft` (`lib/portal-client.ts`) to `PortalService.create_or_update_draft`
  / `submit_draft` (`app/services/portal_service.py`), which builds `PurchaseRequestLine`
  rows directly from the raw payload dict - it does not go through either Pydantic schema
  below. The gate lives in `submit_draft` (never `_apply_payload`/draft save), mirroring the
  existing sponsorship project-requirement gate already there (`assert_project_requirement`)
  and its own reasoning: a draft may legitimately be incomplete, a submit may not. Refuses
  with the same `AppException(422, detail=f"line:{index}", code=...)` shape
  `price_tag_request_service.py` uses for a line refusal. The client-side check + the
  `lineErrorToast`-style "Line N: <message>" surfacing mirrors `PriceTagRequestForm.tsx`'s
  own precedent (`PriceTagRequestForm.validation.test.tsx`); `SubmissionForm.tsx` had no
  prior per-line naming, so this is the first user of that pattern there, not a rewrite of
  an existing one.
- **System create/edit** (`procurement-management/purchase-requests`) - the zod
  `PurchaseRequestFormSchema.superRefine` already makes `sales_type` mandatory for
  `purchase_request`; the mirror rule adds `unit_price` mandatory for `sponsorship_form`,
  same idiom, same file. `PurchaseRequestForm.tsx` and `PurchaseRequestDocumentEditCard.tsx`
  (create and edit respectively, same shared `form` instance) already render the unit price
  cell through `FormField`/`FormMessage`, so the inline message needs no new wiring - only
  the header's required mark is new.
- **External ingest** (`/api/v1/external/purchase-requests`, the WhatsApp/n8n channel) and
  the **internal** create/update schemas (`app/schemas/procurement.py`) both gain a
  `model_validator(mode="after")` raising the same `AppException` shape as the portal gate
  above (a shared `refuse_missing_sponsorship_unit_prices` helper in
  `app/schemas/procurement.py`, imported by `app/schemas/external/procurement.py`). Blank
  string now coerces to "missing" via a `field_validator(mode="before")` on
  `PurchaseRequestLineBase.unit_price`, matching the external line's own existing blank
  coercion - without it a blank string 422s as a raw pydantic decimal-parsing error instead
  of this rule's own detail shape.

A line with nothing else in it (the portal's own `cleanLineItems` keep-predicate; a mirror
`lineHasContent` in the zod schema) is never "a line" for this rule - a blank filler row
from "Add item"/"Add row" never blocks submission by itself. The backend schemas do not
need this filter: the frontend already drops empty lines from the payload before it is
sent.

## Files touched

- `sorento_crm_backend/app/services/portal_service.py` - `_require_sponsorship_unit_prices`,
  called from `submit_draft`.
- `sorento_crm_backend/app/schemas/procurement.py` - `refuse_missing_sponsorship_unit_prices`,
  the blank-price `field_validator`, and the `model_validator` on
  `PurchaseRequestHeaderCreate`/`Update`.
- `sorento_crm_backend/app/schemas/external/procurement.py` - the same `model_validator` on
  `PurchaseRequestExternalCreate`.
- `sorento_crm_frontend/app/(auth)/portal/lib/portal-client.ts` - `throwSubmissionError`
  (mirrors `PriceTagRequestError`'s `{message, detail, code}` parsing) for `saveDraft`/
  `submitDraft`.
- `sorento_crm_frontend/app/(auth)/portal/components/SubmissionForm.tsx` - client-side
  check + line naming on submit, required mark + inline message on the unit price cell.
- `sorento_crm_frontend/.../purchase-requests/forms/purchase-request-schema.ts` - the
  mirror `superRefine` rule.
- `sorento_crm_frontend/.../purchase-requests/components/PurchaseRequestForm.tsx` and
  `PurchaseRequestDocumentEditCard.tsx` - "U/P *" header.
- Tests: `test_sponsorship_unit_price_required.py` (backend, all three surfaces);
  `SubmissionForm.sponsorshipUnitPrice.test.tsx`,
  `PurchaseRequestForm.sponsorshipUnitPrice.test.tsx`, and additions to
  `purchase-request-schema.test.ts`; `PurchaseRequestDocumentEditCard.lineItems.test.tsx`
  and `test_external_number_suffix_lookup.py` updated for the new required field.
