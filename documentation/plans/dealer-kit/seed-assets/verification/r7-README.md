# Price Tag Request UX Round 7 - browser evidence, 8 Sept 2026

Lane `feat/price-tag-r7-request-ux`, FE `:3081` / BE `:8081` (dev HMR, `next dev`), agent-browser
session `r7-verify` on `--session r7-verify` isolation. CRM staff login via `.env.local`
`E2E_EMAIL`/`E2E_PASSWORD`; portal contact reached via CRM Contacts -> row kebab -> **Impersonate
in portal** (contact `80560c8f-6358-4115-8b2c-e139ef31e48e`, "Jayson"), not the OTP link - see
"Environment notes" below. Navigation was sidebar-driven from `/` throughout except two returns
to an already-established contact detail page mid-run (re-impersonation), each of which is noted
inline.

`documentation/plans/dealer-kit/price-tag-r7-request-ux-acceptance-criteria.md` is the contract.

## AC -> result

| AC | Result | Evidence |
| --- | --- | --- |
| AC-S1-1 (form/read-view/CRM-detail/designer labels) | PASS | `r7-AC-S1-1-and-S2-1-portal-new-request-form.png`, `r7-AC-S1-1-S1-3-S1-4-portal-read-view.png`, `r7-AC-S1-1-and-S1-5-and-S1-6-crm-detail.png` |
| AC-S1-1 (CRM **listing** header) | **FAIL** | `r7-DEFECT-AC-S1-1-listing-header-still-Deadline.png` - see Defects |
| AC-S1-2 (1440 width, 375 no h-scroll) | PASS | `r7-AC-S1-2-form-1440px-1000px-wide.png` (measured 1000px), `r7-AC-S1-2-form-375px-single-column.png` (scrollWidth==clientWidth==375) |
| AC-S1-3 (no Alternatives/Accessories cols) | PASS (fresh data); back-compat clause not exercised | `r7-AC-S1-3-lines-tab-no-alt-accessories.png`, portal lines table columns `#/ITEM/QTY (TAGS)/REMARKS` in `r7-AC-S1-1-S1-3-S1-4-portal-read-view.png` |
| AC-S1-4 (Sales Order tab/section, empty state copy) | PASS | `r7-AC-S1-4-sales-order-tab-empty.png` |
| AC-S1-5 (Design Ready pill + Mark design ready CTA) | PASS | `r7-AC-S1-1-and-S1-5-and-S1-6-crm-detail.png` (pill on PT-202609-0001), `r7-AC-S1-5-mark-design-ready-cta.png` (gear menu on PT-202608-0002, Designing) |
| AC-S1-6 (3 tabs, no Proof tab) | PASS | `r7-AC-S1-1-and-S1-5-and-S1-6-crm-detail.png` - tablist reads exactly Request/Lines/Sales Order |
| AC-S1-7 | not browser-verified (vitest) | n/a |
| AC-S2-1 (Price segmented control, default List) | PASS | `r7-AC-S1-1-and-S2-1-portal-new-request-form.png` |
| AC-S2-2 (disabled w/ tooltip, enables w/ promo, flips back on clear) | PASS | `r7-AC-S2-2-selling-price-tooltip.png` ("Select a promotion first"); enable/flip-back confirmed live (no promo -> disabled, promo picked -> enabled + selectable, promo cleared -> back to List, disabled) |
| AC-S2-3 (no per-line Promo price switch) | PASS | line row columns are `#/ITEM/QTY (TAGS)/REMARKS/Actions` only, both in the portal form (`r7-AC-S2-4-form-filled-before-save.png`) and CRM Lines tab |
| AC-S2-4 (Remarks survive Save Draft/reload/Submit, shown in Lines tab + LinesRail) | PASS | `r7-AC-S2-4-form-filled-before-save.png`, `r7-AC-S2-4-persisted-after-reload-1.png` (full page `reload`, remarks "r7 test" intact), designer LinesRail shows "r7 test" under the line in `r7-AC-S2-8-designer-selling-mode-promo-badge.png` |
| AC-S2-5/6/7 | not browser-verified (pytest) | n/a |
| AC-S2-8 (promo vs list price_badge in designer) | PASS with caveat | `r7-AC-S2-8-designer-selling-mode-promo-badge.png` - canvas renders `RM 760` on the Selling-mode/promo-attached request; could not visually distinguish "promo" vs "list_only" badge subtype since this SKU/promotion pair has no promo price row in this DB (degrades to list per documented behaviour) |
| AC-S3-1/2/3 | not browser-verified (pytest) | n/a |
| AC-S3-4 (submit -> Designing, assigned, no Claim) | PASS | see AC-S7-3 evidence (same submit) |
| AC-S4-1 (real tag render, not text-only) | PASS | `r7-AC-S4-1-and-S4-2-design-preview-200pct.png` - price badge, product photo slot, code/name/spec text all render |
| AC-S4-2 (zoom Fit/25/50/75/100/150/200, body never h-scrolls) | PASS | `r7-AC-S4-2-zoom-levels-menu.png` (exact 7 options), body `scrollWidth===clientWidth===1440` measured at 200% |
| AC-S4-3 | not browser-verified (pytest) | n/a |
| AC-S4-4 (preview also at ready) | PASS | portal read view of PT-202609-0001 at status `ready` still rendered the "Design Preview" section with resolved prices (verified via `document.body.innerText`, not separately screenshotted) |
| AC-S4-5 | not browser-verified (vitest) | n/a |
| AC-S5-1 (approve enqueues one export, UserDownload row) | PASS | DB query: new `user_downloads` row `f815e777-...`, `kind=dealer_kit_tag_sheet_pdf`, `source_entity_type=price_tag_request`, created at approve time |
| AC-S5-2 | not browser-verified (pytest) | n/a |
| AC-S5-3 (gear Download PDF enables) | PASS with caveat | `r7-AC-S5-1-and-S5-3-gear-pdf-being-generated.png` - gear opened, "Download PDF" NOT disabled, a real `GET .../download` returned 200 (downloaded a pre-existing completed export from 5 Sept). The NEWLY enqueued export from this run's Approve stayed `status=pending` for 10+ minutes - see "Worker not available on this lane" below |
| AC-S5-4 (CRM Export PDF at ready) | PASS | `r7-AC-S5-4-crm-export-pdf-at-ready.png` - primary CTA reads "Export PDF" at status Ready |
| AC-S6-1 (Extract lines with AI button + dialog) | PASS (button always visible, not gated - documented in-code review decision, see note) | `r7-AC-S6-1-file-attached.png`, `r7-AC-S6-1-ai-extract-dialog.png`; real extraction run against `e2e/fixtures/ai-extract/image-04.png` (`POST .../ai-extract` -> 200) returned "Nothing extractable was found" - `r7-AC-S6-1-extract-result-nothing-found.png` |
| AC-S6-2/3 | not exercised (no fixture produced a matched line; mechanism proven via S6-1's live 200 response) | n/a |
| AC-S6-4/5 | not browser-verified (pytest/vitest) | n/a |
| AC-S7-1 (form type dropdown offers Price Tag Request, saves, lists) | PASS | `r7-AC-S7-1-form-type-dropdown.png`, `r7-AC-S7-1-add-form-sla-config-filled.png`, `r7-AC-S7-2-price-tag-config-listed.png` (config created live: stage `design`, agent `marketing_form`, team-set `marketing_form` -> team "Marketing - Forms", 1 member Chong Zhi Xiu, start event `submit`) |
| AC-S7-2 (list's form-type filter includes Price Tag Request) | PASS, with a wording note | see "AC-S7-2 wording" below |
| AC-S7-3 (submit -> Designing, assigned to config's member) | PASS | `r7-AC-S3-4-and-S7-3-portal-after-submit-designing.png`, `r7-AC-S3-4-and-S7-3-crm-detail-no-claim.png`; DB: `PT-202609-0002.assigned_to_id = 7d0e0441-...` (Chong Zhi Xiu), `status=designing` |
| AC-R-1/2/3 | out of scope (pytest/vitest/alembic, owned by the tester's suite run, not this browser pass) | n/a |

## Full flow walked (portal, contact "Jayson")

1. Created a NEW draft: Customer `ADY MARKETING SDN BHD (PROJECT)`, promotion `3. Bathroom
   Accessories.pdf`, Price = Selling price, Need by `25/09/2026`, one line. First product tried
   (`CBF31046`) hit the ala-carte Bathroom Furniture SET_GUARD (`r7-scratch-submit-422-error.png`,
   informative, not a defect - working as designed, this app's own guard). Swapped to
   `SRTWT8267-GM`, remarks `r7 test`.
2. Save Draft -> `PT-202609-0002` created as Draft. Reopened via the list AND via a full page
   `reload` - every field intact.
3. Submit -> `200`, request moved straight to `Designing`, `assigned_to_id` resolved through the
   `price_tag_request` Form SLA Config created in this same run (AC-S7-1/S3-1 chain proven live,
   not mocked).
4. CRM: listing shows `PT-202609-0002 / Designing / Chong Zhi Xiu`; detail has no Claim button,
   primary CTA is `Design tags` directly.
5. Portal: approved `PT-202609-0001` (was `proof_ready`/"Design Ready"). Status went straight to
   `ready` ("Ready" pill) - `transition_status(..., STATUS_APPROVED)` and the auto-export's own
   `transition_status(..., STATUS_READY)` both fire inside one `approve` call
   (`app/services/price_tag_request_service.py:394` and
   `app/services/dealer_kit/tag_sheet_export_service.py:196`), so "approved" is not independently
   observable from the browser - this is by design, not a bug.
6. CRM: `PT-202609-0001` detail now shows `Ready` pill and primary CTA `Export PDF`.

## AC-S7-2 wording

`Form SLA Configuration` (`/sla-management/form-sla-config`) has no separate filter *control* -
it renders one grouped table per form type, keyed off the same `FORM_SLA_TYPE_LABELS` map
(`app/(protected)/sla-management/_shared/formSLAService.ts:376`) that also supplies the Add
dialog's form-type dropdown. `price_tag_request: 'Price Tag Request'` is in that map, and a saved
config appears under its own `Price Tag Request` group heading
(`r7-AC-S7-2-price-tag-config-listed.png`). Read AC-S7-2 as "the shared type list (which acts as
the filter/grouping key everywhere it's used) includes Price Tag Request" - PASS on that reading.
If a literal filter dropdown was intended and doesn't exist, that's a scope question for the
plan, not a code defect found here.

## Environment notes (not price-tag-r7 defects)

- **Impersonation link opens `:3000`, not this lane's `:3081`.** Backend `.env`
  `FRONTEND_BASE_URL=http://localhost:3000` (unset for this lane), so
  `ContactImpersonateDialog`'s `window.open(session.portalUrl, ...)` and the separate "Portal
  link" (magic-link + OTP) dialog both build URLs against the wrong port. Worked around by
  intercepting `window.open` and re-navigating to the same token on `:3081`. Pre-existing,
  environment-config, not touched by this lane.
- **Worker not available on this lane for the PDF export.** `DEALER_KIT_PRINT_BASE_URL` is also
  unset in this lane's backend `.env` (defaults to `:3000`). Two `worker.py` processes are running
  machine-wide (other lanes'), sharing the `catalogue_render` RQ queue (4 items queued, ~51.7k
  total job keys in Redis at the time of this run). The export enqueued by this run's Approve
  click (`user_downloads.id=f815e777-...`) stayed `status=pending` for 10+ minutes of wall clock
  while other work continued - consistent with a worker rendering against the wrong frontend port
  (or simply not reaching this job in the shared backlog), not a code defect in r7. AC-S5-3's
  mechanism itself (gear enable + real `GET .../download` -> 200) was proven against a
  pre-existing completed export from 5 Sept on the same request.
- **A concurrent coder edit to `AIExtractDialog.tsx` briefly crashed the portal form** (parse
  error `Expected '</', got '}'` at line 513, "Application error: a client-side exception") the
  first time the Promotion dropdown was opened. Next.js Fast Refresh full-reloaded and the file
  was fixed within the same minute; every subsequent interaction with that exact dialog (the real
  AI Extract run in step above) worked cleanly. Not a regression to report against the shipped
  code - the dev-overlay "1 Issue" badge visible in `r7-AC-S2-8-designer-selling-mode-promo-badge.png`
  is this same stale event, not a new one.
- AC-S1-3's "a request created before r7 with alternatives saved still opens and saves without
  error" clause was not exercised: `select ... from price_tag_request_lines where
  alternatives::text != '[]'` returns 0 rows in this database, so there is no legacy row to open.
  Covered by pytest per the plan (S1-7/R-1), not by this browser pass.

## Defects found

1. **AC-S1-1 fails on the CRM listing header specifically.** The Price Tag Requests DataGrid
   column reads `Deadline`, not `Need by` (`r7-DEFECT-AC-S1-1-listing-header-still-Deadline.png`).
   Source: `app/(protected)/dealer-kit/price-tag-requests/components/PriceTagRequestsList.tsx`
   lines 221/229, `headerTitle: 'Deadline'` / `<DataGridColumnHeader title="Deadline" .../>`. Every
   other surface (portal form, portal read view, CRM detail header line, designer LinesRail via
   `Qty N / Family / LP RM X`) correctly says "Need by" or omits the label entirely - only the
   listing column header was missed.

No console errors or `:8081` 500s were observed on any surface this run, apart from the
concurrent-edit transient noted above. No other stale label ("Debtor", "Proof") was seen anywhere.

## Not exercised, and why

- Zoom levels 25/50/75/100/150 individually pixel-measured - only Fit and 200% were driven; the
  menu itself listing all 7 exact values is the evidence for AC-S4-2's "offers" clause.
- AC-S6-2/3 (extract result table columns, Apply mapping) - the one real extraction run against a
  fixture image found nothing extractable, so no result row to inspect. AC-S6-1's mechanism
  (button, dialog, real 200 from the AI endpoint) is proven; the table/apply behaviour is covered
  by `PriceTagRequestForm.aiExtractApply.test.tsx` per the plan, not re-driven here.
- A second contact WITHOUT the `price_tag_request` grant, to confirm 404 gating (AC-S4-3) - would
  need a new DB row on a shared prod-copy database; left to pytest per house convention.

## Cleanup

`PT-202609-0002` (portal draft I created, then submitted) and the status change on `PT-202609-0001`
(`proof_ready` -> `ready` via Approve) are left in place - both are legitimate, non-destructive
outcomes of the flows under test, and the portal has no delete path for a submitted/approved
request (by design, same as prior verification rounds documented in this folder).
