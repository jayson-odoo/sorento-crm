# UAC - Product-discontinued notification: per-company AND per-brand recipient scoping

**Status:** Draft (autonomous crewmate run; brief from firstmate is the requirement source).
Companion plan: `PLAN-product-discontinued-brand-scope.md`. Parent feature:
`PLAN-product-discontinued-notification.md` (implemented 2026-06-21).

## Journey

**Actor:** an internal staff member (e.g. Kia Yee, a brand manager) responsible for a slice of
the catalogue, and the admin who manages user notification preferences.

1. **Where they arrive from:** the admin (or the user, if they have user-management rights on
   themselves) opens User Management -> Users -> the user's detail page -> Edit profile dialog,
   the same place the two product-discontinued channel toggles (email / WhatsApp) live today.
2. **What the system already knows:** the companies in the install and the brands each company
   carries. The user is never asked to type a company or brand name; they pick from selects.
   A user who already had a toggle ON before this feature shipped is shown one pre-existing
   "All companies / All brands" scope row (created by migration), so what they see matches what
   they already receive.
3. **The single decision per step:** for each scope row the user decides one thing: "which slice
   of the catalogue is mine". A row = one company (or All companies) plus a set of brands in
   that company (or All brands). Add row / remove row. The email/WhatsApp toggles keep their
   existing meaning: HOW to be notified. Scopes decide WHAT.
4. **What they hold at the end:** the user's next discontinued notice (in-app / email /
   WhatsApp) reports only products inside their scopes: the count, the wording and the deep
   link all describe their subset, and the link opens the product list already filtered to it.
   A user whose scopes do not touch a batch hears nothing.
5. **What other stakeholders are told automatically:** nothing changes for other subscribers;
   each recipient independently gets their own filtered view of the same per-company batch.

## Acceptance criteria

### Phase 2 - backend (schema, migration, fan-out)

- **AC-1 [BE][T]** Given the new scope table, when a user row has scope (company=NULL,
  brand=NULL), then that user receives every company's batch in full, byte-identical content
  semantics to the pre-feature behavior (count, wording, link with only
  `discontinued_batch_id`).
- **AC-2 [BE][T]** Migration back-compat: given users whose
  `notify_email_on_product_discontinued` OR `notify_whatsapp_on_product_discontinued` is true
  at migration time, when the migration runs, then each gets exactly one
  (NULL company, NULL brand) scope row; re-running the backfill is idempotent (no duplicates).
  Users with both toggles off get no row.
- **AC-3 [BE][T]** Kia Yee scenario end to end: given scopes {Sorento company, brand Mocha} and
  {Mocha company, all brands}, and a run where products became discontinued in
  (Sorento, Mocha-brand), (Sorento, other-brand) and (Mocha company, any brand), then she is
  notified for the Sorento batch with count = only the Mocha-brand products and a deep link
  carrying `discontinued_batch_id=<sorento batch>` plus the Mocha brand filter, AND for the
  Mocha company batch in full (link = plain batch link), and receives nothing for the
  (Sorento, other-brand) products.
- **AC-4 [BE][T]** Given a user with a toggle ON and zero scope rows, when a batch fires, then
  they receive nothing (no in-app row, no delivery).
- **AC-5 [BE][T]** Given a user whose scopes match a company but none of the batch's products
  (brand mismatch on every product), then they receive nothing for that batch.
- **AC-6 [BE][T]** A product with `brand_id IS NULL` is included only for recipients holding an
  all-brands scope for its company (specific-brand scopes never match it).
- **AC-7 [BE][T]** Stamp-first preserved: products are stamped
  (`discontinued_notified_at`, `discontinued_notify_batch_id`) and committed before any send;
  batching stays one batch per company.
- **AC-8 [BE][T]** Best-effort fan-out preserved: one recipient's send failure rolls back only
  that iteration and the loop continues; the failure is logged with user id + batch id.
- **AC-9 [BE][T]** Task `metadata.company_ids` composes: a run scoped to company A detects only
  company A products, and recipient scopes then filter who hears about them; a recipient whose
  only scope is company B receives nothing from that run.
- **AC-10 [BE][T]** Products list endpoint: `brand_id` query param accepts a comma-separated
  list of brand ids and filters with IN; a single value behaves exactly as before. Combined
  `discontinued_batch_id` + multi `brand_id` returns exactly the recipient's subset.
- **AC-11 [BE][T]** Scope rows survive company/brand/user deletion coherently: FK
  `ON DELETE CASCADE` from user, company and brand; the scope table is NOT company-scoped
  (no CompanyScopedMixin), so the scheduler's session scope filter never hides recipients.
- **AC-12 [BE][T]** User API: GET user/me includes `product_discontinued_scopes` (each row with
  company id+name, brand id+code+name, nulls for the all-* arms) in ALL manual UserResponse
  builders; user update accepts an optional `product_discontinued_scopes` list with
  replace-all semantics (omitted = untouched), validates brand belongs to the named company,
  forces brand=NULL when company=NULL, and dedupes.
- **AC-13 [BE][T]** Auth: editing another user's scopes requires the same permission as editing
  their notification toggles today; a user without it is denied.

### Phase 1 - frontend (preferences UI, deep link)

- **AC-14 [FE]** The edit-profile dialog's notification section gains a scope editor directly
  under the two product-discontinued toggles: rows of (company SearchableSelect with an
  "All companies" option, brand SearchableMultiSelect with an "All brands" option scoped to
  the chosen company), plus add-row and remove-row. Selecting "All companies" forces and locks
  brand to "All brands". Follows the dialog's existing field idiom; no UUIDs shown; selects
  searchable per ADR.
- **AC-15 [FE]** When either discontinued toggle is switched ON and the user has zero scope
  rows, the editor pre-populates one "All companies / All brands" row so silence is impossible
  to configure by accident; a user who then deletes every row sees an inline hint that they
  will receive nothing.
- **AC-16 [FE]** View and Edit same layout: the read view of the profile shows the saved scopes
  in the same position/order as the edit dialog's editor (read-only rendering, company and
  brand names).
- **AC-17 [FE]** Deep link: opening
  `/master-data-management/products?discontinued_batch_id=X&brand_id=a,b` keeps BOTH params
  (the current param-stripping effect must preserve brand_id) and the grid shows exactly the
  filtered subset.
- **AC-18 [FE][T]** Vitest: scope-editor component tests cover empty (no rows + hint),
  populated, all-companies-locks-brand, add/remove row; deep-link param preservation covered
  at the ProductsList level or service level.

### Phase 3 - evidence

- **AC-19 [E2E]** Recorded agent-browser evidence run (no new Playwright spec): sidebar-click
  to Users -> edit a user's scopes -> save -> re-open shows them; products deep link with
  batch + brand filter renders the subset. 375px and 1280px.
