# UAC - sponsorship form requires a unit price on every line

Plan: `PLAN-sponsorship-unit-price-required.md`. Track: small fix. Issue #1227.

## Portal (dealer web portal, `(auth)/portal`)

- **AC-P1** Submitting a sponsorship form with a real line whose unit price is missing,
  blank, or negative is blocked client-side before any request is sent, naming the line
  ("Line N: Unit price is required.").
- **AC-P2** A server 422 naming `line:<index>` on submit is surfaced the same way
  (`"Line N: <message>"`), for a race the client check did not catch.
- **AC-P3** Once every line has a valid unit price, submit proceeds normally.
- **AC-P4** A draft save with an incomplete line is never blocked - only submit is gated.
- **AC-P5** A fully blank filler line (no field touched) never blocks submit by itself.
- **AC-P6** Purchase requests (`request_type = purchase_request`) are unaffected - a line
  with no unit price still submits.
- **AC-P7** A header with zero lines submits unaffected (existing sponsorship forms are not
  migrated).

## System create/edit (`procurement-management/purchase-requests` and
`.../sponsorship-forms`)

- **AC-S1** The unit price column header carries a required mark on a sponsorship form,
  create and edit alike.
- **AC-S2** Save is blocked with an inline message under the unit price cell when a real
  line's unit price is missing, blank, or negative - create and edit alike.
- **AC-S3** A fully blank filler row (from "Add row") never blocks save by itself.
- **AC-S4** Purchase requests are unaffected - the `sales_type`-mandatory rule this mirrors
  stays scoped to `purchase_request`, and this rule stays scoped to `sponsorship_form`.
- **AC-S5** The line total keeps computing from quantity x unit price - no regression.

## Backend (external ingest + internal create/update schemas)

- **AC-B1** External create (`PurchaseRequestExternalCreate`, the WhatsApp/n8n channel)
  refuses a sponsorship line with a missing, blank, or negative unit price with a 422 naming
  `line:<index>` (`code=SPONSORSHIP_UNIT_PRICE_REQUIRED`).
- **AC-B2** Internal create (`PurchaseRequestHeaderCreate`) and update
  (`PurchaseRequestHeaderUpdate`) refuse the same way.
- **AC-B3** An internal update that omits `products` entirely (not touching lines) is a
  no-op for this rule.
- **AC-B4** A purchase request line without a unit price is unchanged on all three schemas.
- **AC-B5** `PortalService.submit_draft` refuses a sponsorship line the same way, checked
  against the lines actually persisted (covers both a fresh submit payload and a bare
  resubmit of an already-saved draft).
