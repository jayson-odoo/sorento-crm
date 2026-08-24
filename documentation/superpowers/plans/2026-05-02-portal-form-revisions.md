# Portal Form Revisions - Plan

Revisions to the user-submission portal so its forms match the backend's CRUD pages, integrate with master data lookups, and improve listing UX. Branch: `claude/user-submission-portal-VSIDo`.

## Goals

1. **Strict backend field parity** - portal field types/widgets must match the BE's admin-side CRUD widgets (dropdowns vs free text vs date).
2. **Master-data lookups** - product code / project customer / DO number must source from production data with searchable async dropdowns + free-text fallback.
3. **Sensible defaults** - salesperson defaults to contact's name; complaint date defaults to today.
4. **Multi-select DO** with rich search (debtor / product / customer).
5. **Post-action navigation** - Save-as-draft AND Submit redirect to portal listing.
6. **Listing improvements** - show document number, search across all fields, status filter.
7. **Responsive layout** - adapt to width/height.
8. **Auto-generate document numbers** - `stock_inquiry_number`, `complaint_number`, etc. on submit.

## Backend changes

### New public endpoints (gated by `X-Portal-Token`)

All under `/api/v1/public/portal/lookups/...`:

1. `GET /lookups/products?q=&limit=20` - search `Product.code` and `Product.name`. Returns `[{code, name, category_code}]`.
2. `GET /lookups/debtors?q=&limit=20` - distinct `DeliveryOrder.debtor_name` matching `q`. Returns `[{value}]`.
3. `GET /lookups/delivery-orders?q=&limit=20` - search by `do_number`, `debtor_name`, `customer_name`, OR by line product code. Returns `[{do_number, debtor_name, customer_name, products}]`.
4. `GET /lookups/sets/{set_key}` - return options for a lookup set (e.g. `complaints_within_warranty`). No auth required for portal-known sets - whitelist these specific sets only.

Each endpoint validates `X-Portal-Token` via `get_portal_token` dependency.

### Auto-generate document numbers

In `PortalService.submit_draft`, after status transition, generate the appropriate document number if NULL:
- `StockInquiry.stock_inquiry_number` = `f"SI-{YYYYMMDD}-{nnnn}"`
- `Complaint.complaint_number` = `f"CMP-{YYYYMMDD}-{nnnn}"`
- `PurchaseRequestHeader.request_number` = `f"PR-{YYYYMMDD}-{nnnn}"` (or `SP-` for sponsorship)

Use a per-day sequence by counting existing rows for that date prefix + 1. Use `with_for_update()` to avoid races.

### Multi-select DO storage

`Complaint.delivery_order_number` is currently a single `Text` column. Either:
- **A.** Repurpose as comma-separated string (low effort, breaks structured queries).
- **B.** Add new `Complaint.delivery_order_numbers` JSONB column (better, requires migration).

Choose **A** for v1. Document choice. Future migration can normalize.

### Listing serializer

Update `PortalService._serialize_summary` so `title` falls back to `stock_inquiry_number || product_code || ...`. Add `document_number` field to summary response.

## Frontend changes

### New shared components

1. `components/portal/AsyncCombobox.tsx` - searchable async select with free-text fallback. Props: `value`, `onChange`, `fetchOptions(q): Promise<Option[]>`, `optionLabel(o)`, `optionValue(o)`, `allowFreeText: boolean`. Debounced search (300ms). Keyboard nav.

2. `components/portal/AsyncMultiCombobox.tsx` - multi-version of above. Stores selected as array of strings.

3. `components/portal/LookupSelect.tsx` - simple Select for portal lookups. Fetches options from `/portal/lookups/sets/{set_key}` once and caches.

### Update `SubmissionForm.tsx`

- Replace generic Input rendering with widget map per field:
 - text / textarea / date / select-lookup / async-combobox / async-multi-combobox / number
- Wire up defaults from `contact` (name) + today's date for `complaint_date`.
- Replace per-form FIELDS array with full field definitions (label, name, widget, source).
- After save-as-draft: `router.replace('/portal')`.
- After submit: already navigates (keep).

### Field map per kind

**Stock Inquiry:**
- product_code → AsyncCombobox(`/lookups/products`) + free-text
- item_description → textarea (auto-fill from selected product name if empty)
- quantity → number
- delivery_date → date
- project_customer → AsyncCombobox(`/lookups/debtors`) + free-text
- project_name → text
- salesperson → text (default to `contact.first_name + ' ' + contact.last_name`)
- remark → textarea

**Complaint:**
- customer_name, contact_person, contact_number → text
- customer_address → textarea
- customer_type → LookupSelect(`complaints_customer_type`) - verify slug exists
- delivery_order_number → AsyncMultiCombobox(`/lookups/delivery-orders`) + free-text. Stored joined `,`.
- complaint_date → date (default today)
- product_code → AsyncCombobox(`/lookups/products`) + free-text → on select also pre-fill product_type with `category_code`
- product_type → text (default from product.category_code)
- within_warranty → LookupSelect(`complaints_within_warranty`)
- defects_discovered → LookupSelect(`complaints_defects_discovered`) - verify slug
- complaint_type → LookupSelect(`complaints_complaint_type`)
- defect_description → textarea
- salesperson → text (default contact name)
- project_title → text

**Purchase Request / Sponsorship Form:**
- ...existing fields...
- product line `item_code` → AsyncCombobox(`/lookups/products`) + free-text per row

### Listing improvements

`portal/page.tsx`:
- Show `document_number` (or fallback to title) with status badge.
- Search input: client-side substring filter across all visible fields.
- Status select filter: All / Draft / Submitted / Rejected.
- Responsive: use Tailwind `sm:`/`md:` breakpoints; tabs go horizontal scroll on small.

### Responsive layout

`SubmissionForm.tsx`: wrap fields in a 1-col → 2-col grid at `sm:` breakpoint where appropriate. Cards already responsive via Tailwind.

## Tasks

### Phase A - Backend (parallel-safe, single domain)

1. **Public lookup endpoints.** Add 4 routes under `/api/v1/public/portal/lookups/`. Whitelist lookup sets accessible without admin.
2. **Document number generation.** Update `PortalService.submit_draft` to mint per-day sequenced numbers.
3. **Multi-select DO storage.** Decide A (comma-separated) and update `_apply_payload` to coerce list → string.
4. **Listing serializer.** Add `document_number` to `_serialize_summary` and prefer it for `title` fallback.

### Phase B - Frontend components (depends on A)

5. **AsyncCombobox** + **AsyncMultiCombobox** + **LookupSelect** in `components/portal/`. Tests for AsyncCombobox basic behavior (search, select, free-text).
6. **SubmissionForm refactor** - widget map, defaults, navigation-on-save.
7. **Field-by-field wiring** for Stock Inquiry, Complaint, Purchase Request, Sponsorship.

### Phase C - Listing + responsive

8. **Listing UX** - document_number column, search, status filter.
9. **Responsive sweep** - verify small/medium/large widths via Playwright at 375px / 768px / 1280px.

### Phase D - E2E verification

10. **Playwright** through each form type confirming widget behavior, defaults, save→listing nav, doc number visible in listing.

## Out of scope

- Backend admin pages (Image 14, 16, 17, 19) - those already exist and aren't being changed.
- Auto-fill complaint customer from contact's RespondContact data - explicit out unless trivial.
- New backend permission gates for the lookup endpoints - portal token guards them.

## Open questions

- Lookup set keys for `complaints_customer_type` and `complaints_defects_discovered` - verify existence in `lookup_sets` table.
- DO multi-select storage: A vs B - choosing A; if BE-side admin breaks, fall back to B with migration in a follow-up.
