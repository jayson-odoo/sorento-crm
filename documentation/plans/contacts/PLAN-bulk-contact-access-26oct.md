# PLAN: upload a dealer-contact sheet, bulk-configure each contact's access (BULK-CONTACT-ACCESS)

Status: Phase 1 - card + mock v1 filed to crew 26 Oct, waiting on owner answers (Q1-Q5) and mock approval. No code yet. Track: L (new upload flow, bulk writes to contact
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

## Shape
Upload -> server-side preview (no writes) -> admin confirms per dealer (bulk-confirm exact) -> apply in ONE
transaction -> result report + one audit row per changed contact. Re-upload is idempotent. Card section 4.

## Architecture
Layer: backend service + one endpoint; FE dialog through hook -> feature service -> `lib/api-client`.
Shared mechanism (one copy, no second matcher, no second planner):
- `app/services/contact_bulk_setup_engine.py` (new, moved not rewritten): `normalise_name`, `_merge_flags`,
  `_find_contacts`, `_resolve_world`, `_plan_contact`, `_apply_contact` leave `scripts/contact_bulk_setup.py`,
  which re-imports them (its CLI, Excel parser, `from_sheet` stay). Its tests
  (`tests/test_contact_bulk_setup_script.py`, `tests/test_contact_bulk_setup_from_sheet.py`) stay green unchanged.
  The engine keeps taking `rules`; the script keeps its 4 Oct `RULES`. Engine gains only what the 26 Oct
  template needs: a list of owner types per company (Q2 cabana_dealer) and a brands facet (NULL -> template set;
  a set list -> union with the template).
- `app/services/contact_access_sheet_service.py` (new): `TEMPLATE` (the 26 Oct rules: card section 3),
  `parse_respond_csv(bytes)`, `plan(db, rows, actor_id)` (contacts, dealer blocks, candidates, per-contact
  changes, warnings), `apply(db, rows, confirmed, actor_id)` (re-plan, validate confirmed ids, write, audit
  `contact.access_sheet`, one transaction).
- Endpoint `POST /api/v1/user-management/contacts/access-sheet` (multipart `file`, `confirmed` JSON form field
  `{dealer_key: [customer_id]}`, `dry_run` default true), `require_permission("user_management.contacts.edit")`,
  facets via `contact_access_copy_service.facets_to_skip`. Mirrors `POST /sales/targets/import`
  (`app/api/v1/sales/targets.py:163`). File cap 2 MB, row cap 2000.
- FE: `user-management/contacts/components/AccessSheetImportDialog.tsx` (steps as `BulkCopyAccessDialog.tsx`,
  drop zone as `DealerTargetImportDialog.tsx`), `hooks/useAccessSheetImport.ts`,
  `services/contactAccessSheetService.ts`. Entry: Actions menu item via `secondaryActions` +
  `secondaryActionsAsMenu` (`components/ui/data-grid-list-toolbar.tsx:207-209`) in `ContactsList.tsx`, shown with
  `user_management.contacts.edit`. Result step "Download result" = CSV built in the browser from the result JSON
  (cells starting with = + - @ escaped).
Classes fixed (not one shape): any brand-company combination of the row; any role word; dealer text and alt texts;
any number of accounts per company; any prior access on the contact (add-only).

## Tests (tester writes first; fake names/phones)
Backend `tests/test_contact_access_sheet.py` on `tests/_pg_fixture.py`: U1-U3 parse + phone, U4-U6 template x 6,
U7 add-only + warnings, U8 exact fan-out (merge survivor / held excluded), U9 pick/none + unconfirmed skipped,
U10 untagged company unticked, U12 inactive unticked + agent never written, U13 dry run writes nothing, U14
rollback on error, U16 audit rows, U17 re-run = 0 changes, U18 facets skipped per permission, U19 out-of-scope
customer 422, endpoint 403 without `contacts.edit`. Regression: the two script test files above.
FE vitest: dialog steps, Confirm all exact ticks exact dealers only, unconfirmed dealer counted skipped, apply
posts file + confirmed ids.

## Tickets
T0 card + mock (lead, done) -> T1 red tests (tester) -> T2 engine move + service + endpoint (coder) -> T3 FE
dialog (coder, same instance) -> reviewer + security-reviewer + browser pass (crew test copy) -> hand test.
