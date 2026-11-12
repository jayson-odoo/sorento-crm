# PLAN: price tag request screen, customer first (multi), one price tag section, notes collapsible, preview before approve

Status: in review, PR #2318 (full track: one migration, ptag_0022_request_customers). Mock v3 approved 10 Nov with the condition that the AI extract is reused unchanged.

Lane: PRICETAG-REQUEST-LAYOUT. UAC: `pricetag-request-layout-acceptance-criteria.md`.

## Journey

Owner + management meeting 9 Nov (relayed 10 Nov). Salesperson's "request price tag" screen:

1. Customer field first, at the top; a multi-select tag input so one request prints for several customers.
2. One merged "Price tags" section: default pricing preference (LP / SP / LP & SP) inside it; manual
   product entry and sales order file upload are one step.
3. Additional info / custom notes move to a secondary collapsible section below.
4. Preview before approval: a Preview button next to Approve; approving opens a preview popup first.

Unchanged: salespeople cannot create templates; custom selling price for items without promotion stays.

## Current screen map (measured, main 03be747b)

- The salesperson's screen, CRM page and portal alike, is ONE component:
  `sorento_crm_frontend/app/(auth)/portal/components/PriceTagRequestForm.tsx` (2675 lines). The CRM
  route `/dealer-kit/price-tag-requests/new` renders it through `PortalPriceTagRequest`
  (`app/(protected)/dealer-kit/price-tag-requests/components/PriceTagRequestPage.tsx:23`); a user
  with only `view_own` sees it for an existing request too (`:15`). Marketing's page is
  `PriceTagRequestDetail.tsx` (not the salesperson's screen).
- Sections today, in order, each a `components/common/FormSection.tsx` card:
  Customer (`PriceTagRequestForm.tsx:2214`), Price (`:2253`, the `PriceModeToggle` "Preferred
  Default"), Sales Order & Lines (`:2290`: `AttachmentDropzone` + per-file AI Extract, then the
  `PriceTagLinesTable`, Add line, and a Preview button at `:2324`), Additional Information
  (`:2386`, Notes). Opening is progressive (`openSectionOnce`, `:538`).
- Customer is a single `SearchableSelect` over the debtor lookup (`:2234`); the payload sends one
  `debtor_code` + `debtor_name` (`:1492`).
- Backend: `price_tag_requests.debtor_code` / `debtor_name` are single columns
  (`sorento_crm_backend/app/models/price_tag.py:97`, `:101`); submit requires `debtor_name`
  (`app/services/price_tag_request_service.py:1657`); list search and sort read `debtor_name`
  (`:2875`, `:2886`). **One request supports exactly one customer today.**
- The printed tag carries no customer: nothing under `lib/dealer-kit`, `components/dealer-kit` or
  the print renderer reads a debtor.
- Price mode is request-level `list` | `selling` (`price_tag.py:107`), each line can flip LP/SP
  (PRICETAG-LPSP); "LP & SP" is a TEMPLATE type (`lib/dealer-kit/template-price-type.ts:6`), not a
  header choice.
- Approve today: the page button calls `handleFinish({kind:'approve'})` (`:2526` -> `:1477`), which
  saves, builds the sheet from the saved request and calls `submitAndApprove` with no preview step.
  The preview popup already exists (`components/dealer-kit/PriceTagLivePreview.tsx:242`, `popup`
  mode on `DesignLightbox`) and opens from the Preview button only.

## Owner rulings

- 10 Nov, mock v1 feedback: Preview is the page's ONE call to action; it opens the preview popup,
  whose main button is Approve (with Back to edit). No Approve button on the page itself.
- 10 Nov, mock v2 feedback: the Price tags section asks ONE choice first, "Upload a file" or "Type
  the items"; only that path and its table show, with a small link to switch. AI extract stays
  where it is (the dropzone tile's action), its wording simpler ("Read items").
- Behaviour answers (recommendations, owner did not object): one request holds N customers; Qty is
  the total typed, not per customer; Preferred default stays List price / Selling price with the
  per-line flip; lists show the first customer "+N" and search matches any.

## Proposed change

1. Customers: `SearchableMultiSelect`; new nullable JSONB column `price_tag_requests.customers`
   (`[{code, name}]`); `debtor_code` / `debtor_name` keep the FIRST customer so list, search, SLA and
   every existing reader keep working unchanged. Submit requires at least one customer.
2. Merge Price into "Price tags": toggle, dropzone and table in one section; Preview button moves to
   the action row as its primary button, and the page's Approve button goes.
   The section opens on the choice (form-local `entryPath`: `null | 'upload' | 'manual'`, not
   stored). Switching keeps lines already in. A saved draft reopens on Upload if it has an
   attachment, else on Type the items once it has lines.
3. Additional information starts folded.
4. Preview runs the checks Approve runs today (`readyToFinish('approve')`), then opens the preview
   popup with Back to edit + Approve (primary); the popup's Approve runs the existing
   `handleFinish({kind:'approve'})`.

## Folded in from UIUX-QUICK-WINS (so the two lanes do not both edit `PriceTagRequestForm.tsx`)

5. "Need by" (`PriceTagRequestForm.tsx:2398-2409`, native `<Input type="date">`) uses the shared
   `<DatePicker>` (dd/mm/yyyy), keeping its current minimum date.
6. Any price tag status chip on this screen renders through the shared `<Badge status>`.
