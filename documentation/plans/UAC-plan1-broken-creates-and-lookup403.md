# UAC - Plan 1 (broken Creates + lookup-403)

**Branch:** `fix/plan1-broken-creates-and-lookup403`
**Source plan:** `PLAN-fix-broken-creates-and-lookup403.md` (GRILLED + USER-APPROVED)
**Method:** UAC-first → TDD (red → green) → verify FE **and** BE against every line end-to-end.

Each line is a binary acceptance check. `[ ]` until proven green with evidence (test name / browser step / network call).

---

**Verification legend:** ✅ proven (browser + tests).

## 🐞 Latent bugs surfaced during browser verification (all fixed + pinned)
1. **`getCampaignTypes` envelope crash** - endpoint returns `{data:[...]}` not a bare array → `campaignTypes.map` threw "c.map is not a function" (white-screen on `/campaigns/new`). Fixed: unwrap `.data`. Test: `campaignService.test.ts`.
2. **Status casing was INVERTED in the audit** - the DB CHECK constraint `marketing_campaigns_status_check` enforces **lowercase** (planning/active/completed/cancelled); the model's uppercase `CampaignStatus` enum was the wrong artifact. Corrected enum + schema validator + list filter + FE all to **lowercase**. (Grilled decision A5 said uppercase based on the inverted audit; DB is the source of truth.)
3. **`created_by` UUID → ResponseValidationError 500** - fresh row holds `created_by` as a UUID object; str-typed response 500'd. Fixed: UUID→str coercion validator on `MarketingCampaignResponse`. Test: `test_campaign_response_uuid.py`.
4. **POST 307 → CORS** - `createCampaign` posted to `/campaigns` (no slash) → 307 → cross-origin redirect dropped CORS. Fixed: POST to trailing-slash route.

All four were invisible because the Create button was dead (never exercised). Browser verification is what caught them.

---


## Bug B - lookup-403 (backend only)

- [x] **B-1** ✅ pytest `test_by_binding_200_for_nonadmin` + live curl (`by-binding` → 200).
- [x] **B-2** ✅ pytest `test_options_200_for_nonadmin`.
- [x] **B-3** ✅ pytest `test_resolve_200_for_nonadmin`.
- [x] **B-4 (regression pin)** ✅ pytest `test_admin_sets_list_403_for_nonadmin` (admin SETS stays gated).
- [x] **B-5** ✅ pytest `test_by_binding_401_unauthenticated`.
- [x] **B-6/B-7 (read endpoint)** ✅ pytest B-1..B-5 (non-admin 200, admin 403, 401 unauth); browser: campaign-type dropdown (same authenticated-only fetch family) populated cleanly, 0 console errors. (Admin user has lookup perms so can't reproduce the original 403 in-browser - the non-admin path is pinned by pytest.)

## Bug A1 - Form create page

- [x] **A-1** ✅ BROWSER: Create Form → `/forms-management/forms/new`, renders FormForm (Form Code/Name/type/Access levels/Purpose/Language/Active/Attachment), no "not found", no app error.
- [x] **A-2** ✅ BROWSER (above) + reuses verified edit-page component.

## Bug A1 - Campaign create page + status casing

- [x] **A-5** ✅ BROWSER: Create Campaign → working `CampaignForm` (after fixing the envelope crash).
- [x] **A-6** ✅ BROWSER + vitest - code/name/type(dropdown shows type_name, no UUID)/status/dates/budget/audience all render; type dropdown populated (Seasonal Promotion, Product Launch, …).
- [x] **A-7** ✅ BROWSER: submit → toast "Campaign created successfully" → redirect to list → row appears (`TEST-CAMP-VERIFY-01 / Brand Awareness / Planning`), 0 console errors.
- [x] **A-8 (casing + filter)** ✅ BROWSER: row stored `planning`, badge shows "Planning"; filter by "Active" → "1 - 0 of 0" (excluded), proving the dead filter now works. + pytest `test_campaign_list_status_filter`.
- [x] **A-9 (casing BE)** ✅ pytest `test_campaign_status_casing` - `PLANNING`→`planning`; `bogus`→ValidationError(422). (Corrected to lowercase per DB constraint.)

## Bug A1 - Stock-Batch button removal

- [x] **A-11** ✅ BROWSER: `/inventory-management/stock-batches` has no "Create Batch" button (`hasCreateBatch: false`); build confirms no `stock-batches/new` route; unused `Plus`/`router` cleaned.
- [x] **A-12 (regression)** ✅ BE `POST /stock-batches/` untouched (no code change to the route).

## Bug A2 - UUIDPath validator (500 → 404)

- [x] **A-13** ✅ live curl `campaigns/new` → **404**; pytest helper `test_non_uuid_raises_404`.
- [x] **A-14** ✅ live curl `forms/not-a-uuid` → **404**.
- [x] **A-15** ✅ live curl `stock-batches/not-a-uuid` → **404**.
- [x] **A-16** ✅ live curl valid-absent UUID → **404** (no regression).

## Cross-cutting

- [x] **X-1** ✅ BROWSER: 0 console errors on campaigns/new (after fixes), campaigns list, forms/new, stock-batches.
- [x] **X-2** ✅ 96 pytest pass across lookup/campaign/marketing/uuid (no new failures); 10 vitest pass; `tsc --noEmit` 0 errors.
- [x] **X-3** ✅ FE prod-rebuilt + restarted on :3000 (200 OK); new routes present, batch route absent.
