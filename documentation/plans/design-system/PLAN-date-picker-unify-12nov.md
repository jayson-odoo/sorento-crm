# PLAN: DATE-PICKER-UNIFY (12 Nov 2026)

Status: Build slice A - behaviour card answered 12 Nov (Q1-Q5 all option a). Track: size M, cloud lane, sliced
(each slice PR < ~300 non-test lines; one PR per slice, frozen after its hand test).

Owner, 4 Nov: "all the dates need to use dd/mm/yyyy format like a standardized format across the
system" (ranges and pickers too; typing `05/11/2026` is accepted). `PLAN-date-format-unify-04nov.md`
(#2163) shipped the display helpers and deferred two follow-ups (its Q4 and its `formatDateTime`
SLA note). This lane closes both.

## Inventory

`date-picker-unify-inventory.md` (this folder): 107 native date controls (15 `datetime-local`)
in 60 files. Count per area:

| Area | Controls |
| --- | --- |
| scm | 20 |
| procurement-management | 15 |
| system-management | 14 (10 datetime-local) |
| project-sales | 11 |
| sla-management | 7 (6 datetime-local) |
| portal (`app/(auth)/portal`) | 6 |
| sales, marketing, account | 4 each |
| workflow-forms, order-management, master-data | 3 each |
| user-mgmt, resource-mgmt, integration-mgmt, components/ideas | 2 each |
| ticket, complaint, rule-builder, list filter dialog, NewProductApplicationHeader | 1 each |

Timezone / off-by-a-day callers (part 2):

- `PurchaseRequestDetail.tsx:1291` "Submitted date": `formatDate(new Date(submitted_at))`;
  `formatDate` (`lib/helpers.ts:128`) reads the browser's local day and `new Date` reads a naive
  UTC string as local, so a request submitted before 08:00 Malaysia shows the previous day.
- `components/common/ActivitiesNotesPanel/EntityActivitiesLayout.tsx:72` `relativeTime`:
  `new Date(iso)` on a naive UTC string reads it as local, so a row minutes old reads "8h ago".
- SLA module `formatDateTime` callers (`lib/helpers.ts:499`, wall-clock, no zone shift) on UTC
  API timestamps: FormSLATrackingList, TeamPendingList, SLAKpiDashboardContent, EventLogTable,
  ConversationSLATrackingDetail, ExtendDueDialog, ConversationSLATrackingList, EventLogList,
  FormSLATrackingTab, FormSLATrackerDetail, SlaExtensionBanner (the 11 #2163 listed).

## Approach

- **One shared control per shape.** Single date: `components/ui/date-picker.tsx` `DatePicker`
  (already typeable dd/mm/yyyy, commit on blur/Enter). Range: `components/ui/date-range-picker.tsx`
  `DateRangePicker` (typeable `dd/mm/yyyy - dd/mm/yyyy`). A thin string adapter (`value`/`onChange`
  in `YYYY-MM-DD`) so a react-hook-form `{...field}` call site swaps in one line, no `Date` round
  trip and no `toISOString` (which shifts the day).
- **One formatter.** Display goes through `formatDateInMalaysia` / `formatDateTimeInMalaysia` /
  `formatDateRange` (`lib/helpers.ts`).
- **Timezone rule.** An API timestamp (naive or `Z`) is UTC and is shown in Asia/Kuala_Lumpur. A
  bare `YYYY-MM-DD` is a calendar day and is never shifted. A picker emits `YYYY-MM-DD` built from
  the picked day's own parts.
- **Guard.** A vitest guard (beside `lib/date-format.guard.test.ts`) fails on a native
  `type="date"` / `datetime-local` outside a shrinking allowlist; each slice removes its files
  from the list, the last slice empties it.
- No behaviour change beyond the date control and the formatting: same payloads, same fields.

## Slices (one PR each, next slice on a new branch + PR titled `DATE-PICKER-UNIFY B: ...`)

- **A** shared control fixes (range typed entry gaps, string adapter), the native-input guard
  with the full allowlist, part 2 timezone fixes (PR submitted date, relativeTime, SLA callers),
  plus the brief's named screens: quotation editor Date, Chat History From/To, staff purchase-request
  edit form.
- **B** scm (20).
- **C** procurement, order-management, master-data, marketing (rest of the forms).
- **D** project-sales, sales, complaint, ticket, workflow-forms, account, user/resource/integration,
  components.
- **E** system-management + SLA `datetime-local` (shape per Q1) and the portal (6).
- **F** naive-UTC display sweep (list at the bottom of this plan).

Each slice: red tests (typing, display, timezone) committed alone, kill test, reviewer, browser
pass at 1280 + 375, hand test, user guide check.

## Standing rules that apply

Dates line 1 (dd/mm/yyyy everywhere, ranges `dd/mm/yyyy - dd/mm/yyyy`, date-times
`dd/mm/yyyy, h:mm am/pm`), Dates line 2 (shared picker, typing accepted, no native input),
Forms "Nothing hangs", Wording "plain words". Everything else: n/a (no list, ERP, chatbot change).

## Answers (crew, 12 Nov, from the owner rules)

- Q1 (a) datetime-local From/To pairs become one `DateRangePicker` (whole days); single date-times
  become `DatePicker` + a time box.
- Q2 (a) every native From/To pair merges into one `DateRangePicker`, same two query params.
- Q3 (a) range typing: refuse non-real days, empty text clears both ends, `dd/mm/yyyy -` sets From
  only, `- dd/mm/yyyy` sets To only.
- Q4 (a) generic builders (rule builder, list filter dialog, workflow dynamic fields) render
  `DatePicker` for the date case in this lane.
- Q5 (a) slice A as listed.

## Naive-UTC display sweep (found by the slice A browser pass, 12 Nov)

Slice A fixes `PurchaseRequestsList.tsx:320` (same field as the named Detail fix). The rest of the pattern, `formatDate(` / `formatDateTime(` on an `*_at` / `*At` API timestamp (browser-local, so before 08:00 Malaysia a date reads the previous day), is 66 calls in 46 files and goes to slice F, area by area, each file joining `lib/utc-display.guard.test.ts`:

- `app/(protected)/procurement-management/new-product-applications/components/NewProductApplicationAttachments.tsx:105`
- `app/(protected)/procurement-management/stock-inquiries/components/StockInquiryDetail.tsx:431`
- `app/(protected)/procurement-management/stock-inquiries/components/StockInquiryDetail.tsx:444`
- `app/(protected)/procurement-management/stock-inquiries/components/StockInquiryDetail.tsx:1211`
- `app/(protected)/procurement-management/stock-inquiries/components/StockInquiryDetail.tsx:1228`
- `app/(protected)/procurement-management/stock-inquiries/components/StockInquiryDetail.tsx:1250`
- `app/(protected)/procurement-management/stock-inquiries/components/StockInquiryAttachmentsSection.tsx:147`
- `app/(protected)/procurement-management/purchase-requests/components/PurchaseRequestAttachmentsSection.tsx:138`
- `app/(protected)/procurement-management/purchase-requests/components/PurchaseRequestDocumentEditCard.tsx:401`
- `app/(protected)/procurement-management/suppliers/[id]/components/SupplierDetail.tsx:186`
- `app/(protected)/marketing-management/promotions/components/PromotionAttachmentsTab.tsx:166`
- `app/(protected)/marketing-management/promotions/components/PromotionAttachmentsTab.tsx:305`
- `app/(protected)/marketing-management/campaigns/[id]/components/CampaignDashboard.tsx:164`
- `app/(protected)/account/notifications/components/coverage-manager.tsx:427`
- `app/(protected)/account/notifications/components/coverage-section.tsx:253`
- `app/(protected)/forms-management/forms/components/FormsList.tsx:194`
- `app/(protected)/forms-management/forms/components/FormForm.tsx:395`
- `app/(protected)/forms-management/forms/[id]/components/FormDetail.tsx:209`
- `app/(protected)/forms-management/forms/[id]/components/FormDetail.tsx:213`
- `app/(protected)/master-data-management/units-of-measure/[id]/page.tsx:192`
- `app/(protected)/master-data-management/units-of-measure/[id]/page.tsx:199`
- `app/(protected)/master-data-management/brands/[id]/page.tsx:462`
- `app/(protected)/master-data-management/brands/[id]/page.tsx:464`
- `app/(protected)/master-data-management/products/components/ProductAttachmentsTab.tsx:228`
- `app/(protected)/master-data-management/item-classes/[id]/page.tsx:230`
- `app/(protected)/master-data-management/item-classes/[id]/page.tsx:234`
- `app/(protected)/master-data-management/product-specifications/components/record/SpecKeyRecordCard.tsx:116`
- `app/(protected)/master-data-management/product-categories/[id]/page.tsx:490`
- `app/(protected)/master-data-management/product-categories/[id]/page.tsx:492`
- `app/(protected)/inventory-management/warehouses/[id]/page.tsx:156`
- `app/(protected)/inventory-management/warehouses/[id]/page.tsx:159`
- `app/(protected)/ideas/portal/components/IdeasPortal.tsx:221`
- `app/(protected)/order-management/customer-groups/components/CustomerGroupsList.tsx:182`
- `app/(protected)/order-management/customer-groups/[id]/components/CustomerGroupDetail.tsx:144`
- `app/(protected)/order-management/customer-groups/[id]/components/CustomerGroupDetail.tsx:147`
- `app/(protected)/order-management/orders/components/OrderDetail.tsx:254`
- `app/(protected)/order-management/orders/components/OrderDetail.tsx:261`
- `app/(protected)/order-management/customers/components/CustomerDetail.tsx:224`
- `app/(protected)/order-management/customers/components/CustomerDetail.tsx:231`
- `app/(protected)/order-management/order-statuses/components/OrderStatusDetail.tsx:105`
- `app/(protected)/system-management/activity/components/ActivityTimeline.tsx:404`
- `app/(protected)/system-management/activity/components/ActivityTimeline.tsx:406`
- `app/(protected)/system-management/import-logs/components/ImportLogsList.tsx:173`
- `app/(protected)/system-management/import-logs/[id]/page.tsx:148`
- `app/(protected)/resource-management/attachments/components/AttachmentDetail.tsx:353`
- `app/(protected)/resource-management/attachments/components/AttachmentBrowser.tsx:280`
- `app/(protected)/resource-management/attachments/components/AttachmentDetailModal.tsx:1124`
- `app/(protected)/project-sales/[projectId]/components/ProjectDetailClient.tsx:830`
- `app/(protected)/user-management/contact-access-agents/components/ContactAccessAgentsGroupedList.tsx:407`
- `app/(protected)/user-management/contact-access-agents/components/ContactAccessAgentsList.tsx:209`
- `app/(protected)/user-management/access-agents/components/AccessAgentDetail.tsx:255`
- `app/(protected)/user-management/access-agents/components/AccessAgentDetail.tsx:259`
- `app/(protected)/user-management/access-agents/components/ContactAccessAgentsTable.tsx:93`
- `app/(protected)/user-management/contacts/components/ContactsList.tsx:734`
- `app/(protected)/user-management/contacts/components/ContactsList.tsx:743`
- `app/(protected)/user-management/contacts/[id]/components/ContactAccessAgentsTable.tsx:152`
- `app/(protected)/user-management/contact-tags/components/ContactTagDetail.tsx:175`
- `app/(protected)/user-management/contact-tags/components/ContactTagDetail.tsx:178`
- `app/(protected)/complaint-management/complaints/components/ComplaintManualAttachmentsSection.tsx:144`
- `app/(protected)/complaint-management/complaints/components/ComplaintDetail.tsx:392`
- `app/(protected)/complaint-management/complaints/components/ComplaintDetail.tsx:1384`
- `app/(auth)/portal/ideas/[token]/components/PortalIdeaTrack.tsx:113`
- `components/ideas/IdeaDetail.tsx:473`
- `components/ideas/IdeasListView.tsx:348`
- `components/ideas/IdeasListView.tsx:351`
