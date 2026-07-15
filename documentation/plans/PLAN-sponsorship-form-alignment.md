# PLAN — Sponsorship Form Alignment (totals, sponsor-subject lookup, nav, approver fix)

Status: **Implemented (Phase 2)** — backend + frontend wired, pytest + vitest green;
migration written (NOT applied to shared dev DB per task constraint); browser/e2e
verification deferred (stack not booted in this isolated worktree). Grilled 2026-06-24.

Scope: SPONSORSHIP forms only unless stated. `purchase_request` (PR) behaviour is untouched
except where the two share a route/component/column.

Shared data model: both PR and sponsorship live in `purchase_requests` (+ `purchase_request_lines`),
discriminated by `request_type` (`purchase_request` | `sponsorship_form`).

---

## Workstream 1 — Per-line Total + Remark missing in system (Image 1→2)

### 1a. Total not persisted (portal bug — root cause)
- `SubmissionForm.tsx` rendered the per-line Total input with a display-only `computedTotal`
  fallback that was never written to state, and the submit filter dropped price-only lines.
- **Fix (shipped):** `cleanLineItems` (extracted to `portal/lib/line-items.ts`) now persists the
  computed total (`computeLineTotal`) when the Total box is empty, and the filter keeps any line
  with `item_code || quantity || remark || unit_price || total`.
- Backend already maps `unit_price`/`total`/`remark` in every path — no backend change for totals.

### 1b. Remark column (display gap)
- **Fix (shipped):** Remark column added to the sponsorship line-items table in
  `PurchaseRequestDetail.tsx` and to the admin edit-form line items in `PurchaseRequestForm.tsx`
  (Remark header/cell now render for both PR and sponsorship).

---

## Workstream 2 — Purpose → Sponsor Subject convergence + lookup dropdown (Images 3–6)

For sponsorship, "purpose" IS the sponsor subject. `sponsor_subject` is now a **strict lookup**;
an "Others" free-text companion lives in the new `sponsor_subject_other` column.

### 2a. Lookup set (shipped via migration 243)
- Set `procurement_sponsor_subject`: options `showroom` / `mockup` / `others`.
- Keyword synonyms — showroom: "show room"; mockup: "mock up", "mock-up", "sample", "prototype".
- Binding `lookup_bindings(purchase_requests, sponsor_subject)` created LAST.

### 2b. New column (shipped)
- Nullable `purchase_requests.sponsor_subject_other` (Text) on model + schemas + serializers.

### 2c. Data migration (shipped, idempotent, JOIN-based, reversible)
- `alembic/versions/243_sponsor_subject_lookup.py` (down_revision `c1d2e3f4a5b6`).
- Source = purpose if non-empty else old sponsor_subject; keyword-match → showroom/mockup;
  else `others` + park raw text in `sponsor_subject_other`. Binding attaches after backfill.
- **NOT applied** to the shared dev DB (per task constraint); file only.

### 2d. Strict-validator safety on intake (shipped)
- `PurchaseRequestService._normalize_sponsor_subject` resolves incoming `sponsor_subject` via the
  lookup resolver; unmatched → `others` + parked raw text. Applied in external create/update,
  internal create/update + update-and-reply, and the portal save/submit path
  (`PortalService._apply_payload`). Prevents free-text n8n submissions from 422-ing.

### 2e. Forms (shipped)
- Portal `SubmissionForm.tsx`: removed standalone `purpose` from `FIELDS.sponsorship_form`;
  `sponsor_subject` is a `lookup-select` (setKey `procurement_sponsor_subject`) with a conditional
  `sponsor_subject_other` "Please specify" companion (shown only when subject === 'others').
  Portal lookup whitelist updated to allow `procurement_sponsor_subject`.
- Admin `PurchaseRequestForm.tsx`: radio replaced with `LookupBoundField` on
  (`purchase_requests`, `sponsor_subject`) + Others companion; legacy encode/decode helpers removed.

### 2f. Detail + List (shipped)
- Detail: Sponsor Subject renders via `LookupBoundLabel`; appends `: <other>` when 'others'.
- List: `purposeOrSponsorSubjectColumn(requestType)` → Sponsor Subject for sponsorship,
  Purpose for PR / combined list (explicit size + truncate + title).

---

## Workstream 3 — Nav: "Project Sales Admin" parent (shipped)
- New top-level group `Project Sales Admin` (`moduleKey: 'procurement'`, icon Briefcase) added to
  both menu definitions in `config/menu.config.tsx`, children = Purchase Requests + Sponsorship
  Forms; the two leaves removed from the Procurement group. URL paths unchanged.

---

## Workstream 4 — "Approved by unknown" notification bug (shipped)
- `_resolve_approver_display_name`: when the `User.id == approved_by` lookup misses AND
  `approver_email` is empty, fall back to the raw stored `approved_by` value when present and NOT
  UUID-shaped (in-system approvals store the display name); only "unknown" when truly empty / a
  bare UUID.

---

## Test matrix (Phase 2) — landed
- pytest (`tests/test_sponsor_subject_lookup.py`): sponsor_subject normalization (keyword/exact/
  unmatched/blank/non-sponsorship/no-set), binding validator accept/reject, create_request
  normalizing free text, and `_resolve_approver_display_name` (name / user-id / email / empty /
  bare-UUID). 16 tests pass. Existing lookup suites re-run green.
- vitest: `portal/lib/line-items.test.ts` (computed total persisted + priced-only / total-only /
  remark-only lines kept, empty dropped), `portal/components/LookupSelect.test.tsx` (sponsor
  subject options load + label), `purchase-requests/.../PurchaseRequestsList.columns.test.tsx`
  (Sponsor Subject for sponsorship, Purpose for PR/combined). 14 tests pass.
- playwright/browser: NOT run (isolated worktree, stack not booted).

## Deviations / notes
- Total + line-cleaning logic extracted to `portal/lib/line-items.ts` so it is unit-testable
  without rendering the radix-heavy form in jsdom (the full-form render hit a jsdom/radix update
  loop). Behaviour unchanged.
- List column selection extracted to `purposeOrSponsorSubjectColumn` for the same reason.

## Phase 3 — Browser verification (2026-06-24) + post-merge fixes
Verified on an isolated stack (test FE :3003 → test BE :8011, shared DB; user's :3000/:8000
untouched). Migration **applied**: binding attached, backfill correct (22 others / 2 mockup /
2 showroom; unmatched purpose parked in `sponsor_subject_other`).

Confirmed in-browser: WS3 nav group; WS2f list "Sponsor Subject" column (label + `Others: detail`);
WS1b/WS2 detail (line Remark column, Grand Total, Sponsor Subject label+companion, no Purpose);
WS2e admin form (lookup dropdown Showroom/Mockup/Others + "Please specify" companion + Remark
column); WS4 resolver returns approver name (no "unknown") on real records.

Two fixes applied to the main checkout during verification:
1. **Document edit card was missed.** Sponsorship create/edit renders via `PurchaseRequestForm`
   → `PurchaseRequestDocumentEditCard.tsx` (a separate component), which still had the old
   `encode/decodeSponsorSubject` RadioGroup (`mock_up`) and gated Remark to `!isSponsorship`.
   Replaced the radio with `LookupBoundField` + `sponsor_subject_other` companion and added the
   Remark column for sponsorship. Lesson: the document-style card is a separate layer from the
   generic form — both must change.
2. **WS4 precedence refined.** Resolver now ranks the stored display name ABOVE `approver_email`
   so the message matches the detail page's "Approved by" (was returning the email when both
   present). Added regression test `test_approver_name_outranks_email`.

After fixes: pytest 17 passed, vitest 14 passed, tsc clean. Portal sponsorship form NOT
browser-verified (live OTP/slug session not driven) — covered by source review + vitest +
public lookup whitelist/normalization checks.
