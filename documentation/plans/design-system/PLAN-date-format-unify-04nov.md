# PLAN: DATE-FORMAT-UNIFY (every CRM date as dd/mm/yyyy)

Status: Plan (inventory in progress). Track: standard (wide mechanical diff, no migration, no auth change).

## Owner ask (4 Nov 2026, verbatim)
"all the dates need to use dd/mm/yyyy format like a standardized format across the system"

## Rule
- Date: `dd/mm/yyyy`, zero-padded, Malaysia time.
- Range: `dd/mm/yyyy - dd/mm/yyyy` (separator decided in the inventory ask).
- Date-time: `dd/mm/yyyy, h:mm am/pm`.
- Wire formats (ISO) unchanged.

## Steps
1. Inventory of every formatter (FE + BE text surfaces), counts per pattern, existing helpers.
2. One shared `formatDate` / `formatDateRange` / `formatDateTime`, red-first tests, guard test.
3. Replace call sites by module, one commit per batch.
4. Browser pass at 1280/375 on key screens.

## Inventory (4 Nov, main @ 9c6b581e)

### Shared helpers that already exist (FE)
- `lib/helpers.ts:330` `formatDateInMalaysia` -> `04/09/2026` (Malaysia TZ, date-only strings safe). 107 files.
- `lib/helpers.ts:451` `formatDateTimeInMalaysia` -> `30/09/2026, 12:23 pm`. 161 lines.
- `lib/helpers.ts:128` `formatDate` (browser TZ, dd/mm/yyyy) and `lib/helpers.ts:465` `formatDateTime`
  (naive string as wall clock, `PM` upper case) - 73 / 20 files.
- `lib/helpers.ts:187/198` `formatDateSafe` / `formatDateTimeSafe` (fallback `-`).
- `components/ui/date-picker.tsx:12`, `components/ui/date-range-picker.tsx:34` already type and show
  `dd/mm/yyyy`; range label `dd/mm/yyyy - dd/mm/yyyy` (`date-range-picker.tsx:65`).
- `i18n/format.ts` (`Dec 7, 2024`) has zero importers: dead, delete.

### FE call sites NOT dd/mm/yyyy (counts are lines)
| Pattern | Count | Where |
|---|---|---|
| `toLocaleDateString` / `toLocaleTimeString` (browser locale or `d MMM yyyy`) | 31 | portal (`SubmissionList`, `SubmissionForm`, `PriceTagRequest*`, `MyTargetPanel`, `DOFilterMultiSelect`), token pages (`view/request`, `view/complaint`, `approval`), project-sales (`ProjectsGrid`, `PipelineBoard`, `TasksPanel`, `ProjectDetailClient`, `MyTasksClient`), `StockDebtClient:117`, `spoScheduleMatrix:123`, `NotificationItem:41`, `upload-activity/timeUtil:32` |
| `Date.toLocaleString()` (browser locale date-time) | 19 | tickets list + detail, workflow submissions, `EntityActivitiesLayout:76`, `current-sessions:37`, `PromptsList:21`, `PortalLinkDialog:34`, `IntegrationPanel:143`, token pages |
| `Intl.DateTimeFormat` outside helpers | 18 | `ReportFilterBar:47`, `formatPlainDate:14` (cost price uploads), `runListing:86`, `coverageTimeline:23/25`, `AutocountPullReview:81`, `activityPresenters:107-122`, `PromptDetail:641`, `MediaEscalation:21-42`, `CriticalPanel:192` |
| date-fns `format(...)` with a display pattern | ~20 | `stock-inquiries` + `view/stock-inquiry` (`dd/MM/yy`), `AttachmentsInFolderPanel:1283` (`dd MMM yyyy`), `ai-assistant/usage:185` (`LLL dd, y`), `ai-assistant/wishlist:17` (`MMM d, yyyy HH:mm`), `containerRequestMatrix:61-72`, `orderInquiryMatrix:24-26`; Metronic demo layouts (dead demo pages) |
| Hand-rolled `d MMM yyyy` | 2 | `sales/targets/lib/format.ts:40` `shortDate` + `dateRange` (owner's screenshot: TGT periods/commission) |
| SCM 24 h date-time | 1 | `scm/lib/format.ts:224` `fmtDateTime` -> `15/08/2026, 21:05` (1 caller, `SimulationView`) |
| Native `<input type="date">` | 96 | browser renders in OS locale; component cannot force dd/mm/yyyy |

### BE human-facing text NOT dd/mm/yyyy (~45 sites; most BE text already is dd/mm/yyyy)
| Pattern | Count | Surface |
|---|---|---|
| `%d %b %Y` | 15 | complaint PDF, spec sheet, onboarding email, notifications, OI/SO audit and remark text, form SLA due (`form_sla_service.py:214`) |
| `{day} %b %Y` | 7 | chatbot (`so_status.py:81,311`, `ref_status.py:57`, `report_ask.py:171`, `portal_writes.py:373`, `reports/ask.py:592`), low stock report |
| `{day} %b` / `%a d %b HH:MM MYT` | 4 | `planning_change_service.py:196`, `opportunity.py:211`, `chat_asks.py:172`, `sla_service.py:416 format_myt` |
| `%b %d, %Y` | 1 | `portal_service.py:406` WhatsApp portal link |
| `%B` long month | 2 | quotation xlsx `project_quotation_template_service.py:229`, `media_access_service.py:118` |
| `%Y-%m-%d[ %H:%M]` / `.isoformat()` in text | 21 | OI worklist xlsx, escalation text, health alert email, user-facing error messages, OI remarks |
| `%b %Y` month spans | 4 | chatbot status composer, dealer target import summary |
| LLM prompt `%A, %d %B %Y` | 2 | model input only, leave |
Machine formats (bucket keys, filenames, ids, dedup keys, wire values) stay as they are.
