# PLAN: upload a dealer-contact sheet, bulk-configure each contact's access (BULK-CONTACT-ACCESS)

Status: Phase 1 - behaviour card filed to crew 26 Oct (CARD-bulk-contact-access-26oct.md), waiting on owner answers; mock next. No code yet. Track: L (new upload flow, bulk writes to contact
access settings, customer linking). LEAD pattern. UAC: `bulk-contact-access-26oct-acceptance-criteria.md`
(written after the owner answers the card).

## Owner's words (26 Oct ~14:55, trimmed)
"I have this CSV which are list of contacts and their corresponding companies, linked customer, sales agent. I
want to upload this and be able to auto setup their access. [...] All these dealers have in common: packing list
not allowed, ETA buffer applied. For Business Owner they can access Sorento Dealer promotion, for Employee they can
only access End User promotion. Most importantly is the linkage to the customer based on the text here, try to find
the customers and link to all accounts."

## Input
Respond.io contact export (CSV): First Name, Phone Number, Tags (+ empty Respond columns). Tags shape:
`<dealer company text>, Sorento Sdn Bhd, <agent>, [Mocha Sdn Bhd, <agent>], [<alt company text>],
<Business Owner|Employee>`. 313 contacts, 114 dealer texts. Real file is PII and never enters git.

## What exists already (check before building)
- `sorento_crm_backend/scripts/contact_bulk_setup.py` (PR #1483, merged 8d7bc16404): crew-run CLI over the
  owner's 4 Oct dealer Excel. `RULES` (line 99) is the access template; `run()` (line 421) plans + applies ADD-only
  access writes per contact; `auto_links()` (line 739) links every customer whose normalised name equals the
  dealer text (merge survivor, not held) and leaves the rest to a review sheet; `from_sheet()` (line 1142) writes an
  edited export back.
- `app/services/contact_access_copy_service.py` (PR #1463 / #1732): snapshot + diff + copy of one contact's
  access to many, behind `POST /api/v1/user-management/contacts/bulk-copy-access`.
- Missing today: an in-app upload; the Respond CSV `Tags` parser; per-brand sales agent; packing list off;
  promotion rule per role (to verify).

## Shape (draft, settles after the card answers)
Upload -> server-side preview (no writes) -> admin confirms per dealer company (bulk-confirm exact matches) ->
apply in one transaction -> result report + one audit row per changed contact. Re-upload is idempotent.
Engine lifted from `contact_bulk_setup.py` into a service the script and the endpoint both call (one copy).

## Tickets (draft)
T0 card + mock (lead) -> T1 red tests (tester) -> T2 service + endpoints (coder) -> T3 FE upload/preview (coder)
-> reviewer + security-reviewer + browser pass -> hand test.
