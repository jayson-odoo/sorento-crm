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
