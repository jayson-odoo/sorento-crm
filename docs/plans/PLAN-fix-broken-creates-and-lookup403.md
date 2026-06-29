# PLAN — Fix broken Create flows + lookup-403 (top confirmed bugs)

**Status:** DRAFT for USER GRILL, 2026-06-30. No code written. Both bugs CONFIRMED in the audit (see `PLAN-audit-traversal-todo.md`). Per process: grill this → approve → implement vs UAC → verify → deploy. Each item documents: root cause · fix options + recommendation · alternative rejected · risk/blast radius · verification · open questions.

---

## BUG A — 3 broken "Create" buttons (Campaign / Form / Stock-Batch)

**Root cause (confirmed):** the list "Create" button does `router.push('/…/new')`, but there is **no `new/page.tsx`** for these 3 resources, so Next falls through to `[id]/page.tsx` with `id="new"` → `GET /…/{id}` → backend can't parse "new" as UUID → **500** → FE shows "not found". (14 other resources have `new/page.tsx` and work.)
- `CampaignsList.tsx:222` → `/marketing-management/campaigns/new`
- `FormsList.tsx:266` → `/forms-management/forms/new`
- `BatchesList.tsx:231` → `/inventory-management/stock-batches/new`

**Two sub-fixes:**

### A1 — Make the 3 Create flows work
**Option A (recommended): add the missing `new/page.tsx` create pages**, mirroring the 14 working ones (e.g. copy the pattern from `complaints/new` / `warehouses/new`). Each renders the resource's existing create form component.
- *Alternative rejected:* convert to modal-default (ADR prefers modals). Rejected for now because (a) these resources already use dedicated `[id]` detail/edit pages, so a `/new` page is consistent with the rest of the module; (b) modal conversion is a bigger refactor. Revisit modal-default separately if desired.

**Per-resource nuance (OPEN QUESTION — grill):**
- **Campaign** — has `[id]` detail/edit; a `/new` page fits cleanly. Build it.
- **Form** — forms use a builder/definition flow; confirm what "Create Form" should open (blank form? builder?). May differ from a simple create page.
- **Stock-Batch** — the inventory guide flagged batches are created by the **import pipeline**, not manually. So the real fix may be to **REMOVE the "Create Batch" button** rather than build a page. **Grill: is manual batch creation intended at all?**

### A2 — Harden detail GET against non-UUID ids (defensive, broad value)
`GET /…/{id}` returns **500** when `id` isn't a UUID (that's what makes the broken route ugly + leaks an error). Fix: validate/parse the path id; return **404** (or 422) for a non-UUID/missing row, never 500. Apply to the marketing campaign detail GET at minimum; ideally a shared dependency/validator for all `{id}` detail routes.

**Risk/blast radius:** A1 = additive (new pages) — low risk; Stock-Batch removal needs the grill answer. A2 = changes a 500→404 contract on detail GETs — low risk, strictly better; verify no caller relies on the 500.

**Verification (UAC):**
- Clicking Create Campaign / Create Form opens a working create form (or Stock-Batch button removed if not intended); no 500; no "not found".
- A created record appears in the list (round-trip).
- `GET /…/{id}` with a non-UUID id → 404/422, not 500 (test).
- Mobile + desktop; no console errors. Existing tests green.

**Open questions to grill:**
1. Stock-Batch: build a create page, or remove the button (batches come from import)?
2. Form: what should "Create Form" open — a blank create page or the builder?
3. A2: 404 vs 422 for bad id? Apply per-route or via one shared id-validator dependency?

---

## BUG B — lookup-403 breaks form dropdowns (HIGH)

**Root cause (confirmed):** `GET /api/v1/lookup/by-binding` requires permission **`master_data.lookup_sets.view`** (`lookup.py:16-52`). Users who can use Forms / Complaints / Purchase-Requests forms but lack that permission get **403** on every lookup-bound dropdown (via shared `components/common/LookupBoundField.tsx`). Result: empty required dropdowns (e.g. Complaint create: customer_type/within_warranty/complaint_type/defects_discovered), a confusing **"Permission required: master_data.lookup_sets.view"** toast, and the FE retries ~4× spamming the console. A complaint creator may be unable to submit.

**Fix — two parts (both recommended):**

### B1 — Relax the endpoint permission (backend)
Lookup-binding values are **dropdown options**, not sensitive data. Options:
- **Option A (recommended): drop the `master_data.lookup_sets.view` requirement on the READ endpoint** — require only authentication. Lookup OPTIONS aren't sensitive; the SETS admin screen keeps its own permission.
- *Option B:* require ANY of {`master_data.lookup_sets.view`, the parent resource's `.view`/`.create`}. More precise but more complex (endpoint would need to know the caller's intent/resource).
- *Alternative rejected:* grant `master_data.lookup_sets.view` to all affected roles via data/seed — brittle (every new role must remember it), doesn't fix the root mismatch.

### B2 — FE graceful degradation (frontend)
Regardless of B1: `LookupBoundField` / `useLookupOptionsByBinding` should **not retry 4× and spam console + toast** on 403. On failure: stop retrying, render the field as a plain input or show "options unavailable", and suppress the scary permission toast for this background fetch.

**Risk/blast radius:** B1 Option A widens read access to lookup OPTIONS (low sensitivity) — confirm nothing confidential is exposed via a lookup binding (they're enum-like option lists). Affects Forms/Complaints/PR forms positively. B2 is FE-only resilience, low risk.

**Verification (UAC):**
- A user who can create a Complaint (but lacks `lookup_sets.view`) loads `/complaints/new` → all 4 dropdowns populate → can submit. No 403, no permission toast, ≤1 request per binding (no 4× retry).
- Same for Forms + Purchase-Request create/edit.
- The lookup SETS admin screen still gated by its own permission.
- BE test: lookup-by-binding readable by an authenticated non-lookup-admin user (B1); FE test: 403 path degrades gracefully without retry spam (B2).

**Open questions to grill:**
1. B1 Option A (drop the gate to authenticated-only) vs Option B (parent-resource permission)? Confirm no lookup binding exposes sensitive values.
2. B2 fallback: plain text input vs disabled "unavailable" select?
3. Should this also fix the **Forms list** filter (same 403) and the PR forms in the same change?

---

## Suggested sequence
1. **Grill this plan** (answer the open questions).
2. Implement B (lookup-403) first — HIGH, broad impact, low-risk, unblocks form usage.
3. Then A (broken Creates) — bounded, mostly additive.
4. Tests (pytest + vitest + 1 playwright per flow), verify in browser at desktop+mobile, then deploy.

*(Marketing delete no-op, rate-limiting, presigned authz, status casing, dead filters get their own plans — see triage digest. Grouped: "rate-limiting" plan = signup/reset/portal-OTP; "object-level authz" plan = presigned + portal attachment.)*
