# OCN slice 2 assessment: make the Order Change Notice look and behave like the PR / SF

Read-only assessment of lane OCN-ORDER-CHANGE-NOTICE at head `7b7af55a` (PR #2384). Nothing was edited.

Path shorthands (all under `sorento_crm_frontend/` unless marked BE):

- `PRC` = `app/(protected)/procurement-management/purchase-requests/components`
- `OCN` = `app/(protected)/procurement-management/order-change-notices/components`
- `SH` = `app/(protected)/sla-management/_shared`
- BE = `sorento_crm_backend/app`

## 0. The one structural fact behind most gaps

The PR and the SF are ONE detail component (`PRC/PurchaseRequestDetail.tsx`) wrapped by ONE tab shell
on the page, not inside the component:

- PR page `purchase-requests/[id]/page.tsx:44-51` and SF page `sponsorship-forms/[id]/page.tsx:45-56`
  both render `<FormDetailTabsWithRevisions sourceEntityType=... revisionsKind=... commentsKind=...>`
  around `<PurchaseRequestDetail>`.
- That shell (`SH/FormDetailTabsWithRevisions.tsx:57-107`) delegates to `SH/FormDetailWithSLATabs.tsx`,
  which draws the strip (`:105-120`): **Details** (`FileText`), **Comments (N)** (`MessageSquare`,
  `:40-58`), extra tabs, **Revisions** (`History` icon, `FormDetailTabsWithRevisions.tsx:87-92`, only
  when the revision type is enabled or the record has a lineage), **SLA Tracking** (`Timer`).
- The detail's header goes into `<RecordCardSlot>` (`PRC/PurchaseRequestDetail.tsx:653-1005`), which
  portals it ABOVE the tab strip (`SH/RecordCardSlot.tsx:17-27`, slot owned by
  `FormDetailWithSLATabs.tsx:95-100`).

The OCN instead builds its own `Tabs` inside the detail component (`OCN/OrderChangeNoticeDetail.tsx:78-84`,
`:579-612`): labels Details / Conversation / SLA / History, no icons, a different order, its own
`useUrlTab`. That is why the strip does not line up with the PR's. Every sibling form already reuses the
shell: Complaint (`complaint-management/complaints/[id]/page.tsx:56`), Stock Inquiry
(`stock-inquiries/components/StockInquiryDetailTabs.tsx:67`), Sample Request
(`project-sales/sample-requests/components/SampleRequestDetailTabs.tsx:26`), Ticket.

`FormSLASourceType` already includes `order_change_notice` (`SH/formSLAService.ts:48-58`) and so does
`FormCommentKind` (`types/formComments.ts:2-8`), so `FormDetailWithSLATabs` takes the OCN today with no
type change. `useRequestScope('order_change_notice')` answers `limited: false` (kind not in `BASE`,
`hooks/useRequestScope.ts:6-15,34-42`), so the shell's limited-user bypass does not bite.

## A. Element-by-element table

| Element | Purchase request (component, path:line) | Sponsorship form | OCN today (component, path:line) | Gap | Proposed reuse |
|---|---|---|---|---|---|
| Page header (route page) | `PageHeader title="Purchase Request"` + `BackToList hideForLimited` (`purchase-requests/[id]/page.tsx:21-30`) | same component, title "Sponsorship Form", `originLabel` (`sponsorship-forms/[id]/page.tsx:21-30`) | `PageHeader title="Order Change Notice"` + `BackToList` (`order-change-notices/[id]/page.tsx:20-30`) | none worth changing | reuse as is |
| Record card: number + status + subtitle | Inline `h2` "Purchase Request - PR26-0001-R1" (`withRevisionSuffix`) and muted subtitle "dd/mm/yyyy · Purchase Request" (`PRC/PurchaseRequestDetail.tsx:654-672`). **No status pill in the card**: the pill sits on the document card (`:1271-1297`). Portalled above the tabs via `RecordCardSlot` (`:653`) | same code (`:1423-1449` second branch) | `RecordHeaderCard` with number + pill in the title, subtitle "Customer, PO x" (`OCN/OrderChangeNoticeDetail.tsx:418-429`); plus a `dl` of Created by / Revision / Source under it (`:534-547`). Inside the detail, not portalled | Different markup and content; OCN pill duplicated (card + header); no revision suffix on the number | Wrap the OCN card in `RecordCardSlot`; title `Order Change Notice - OCN26-0001` (with `withRevisionSuffix` from `lib/document-number`), subtitle submitted date. Keep the pill only on the document card like the PR. Note: `RecordHeaderCard` (`components/common/RecordHeaderCard.tsx:23-30`) is the newer house header that "other detail pages move to when next touched"; the owner asked for "same as PR", so match the PR now and move both together later (one line to record in the plan) |
| Actions: pager, gear, print, main button | `DetailActions` (pager `purchaseRequestsPagerQuery`, gear `DetailActionsMenu "Request actions"`, primary buttons, `dialogs` = `EntityDownloadsButton`) (`PRC/PurchaseRequestDetail.tsx:673-1003`). Gear items in order: Download history `:685-693`, Undo last action `:697-708`, Escalate SLA `:709-720`, Extend (`SlaExtendMenuItem`) `:721`, Reassign `:722-732`, Release handling `:733-736`, Mark as closed `:737-748`, Copy approval link `:749-793`, Copy view link `:794-821`, Export to Excel `:822-831`, **Print / Download PDF** `:832-842`, Chat records / Update & Reply `:843-867`, Void `:868-876`, Delete `:877-885` | same | `DetailActions` with gear "Notice actions": Copy link, Revise, Void, Undo last action, Release handling (`OCN/OrderChangeNoticeDetail.tsx:430-476`) | Missing: Escalate SLA, Extend, Reassign (and `SlaActiveTrackerControls`, PR `:1255-1263`), Print/PDF, Export, Download history, Copy approval/view link. Present only on OCN: Copy link, Revise | Reuse the shared SLA pieces as is: `SlaExtendMenuItem`/`SlaExtendDialog` (`SH/SlaExtendAction`), `ReassignDialog`, `SlaActiveTrackerControls`, escalate via `escalateFormTracking`. Print/PDF, Excel, approval/view links are slice B per plan (`PLAN-ocn-...md:65-66,90-91`). Better: lift the PR's SLA gear block into one shared `FormSlaGearItems` component the PR and the OCN both render (the PR copy is ~70 lines inline) |
| Main buttons per status (wording + icons) | Submitted: **Change to pending approval** (`Clock`) `:894-903` + **Reject** (outline destructive, `Trash2`) `:904-917`. Pending: **Approve** (emerald, `ThumbsUp`) `:924-954` + **Reject** (`ThumbsDown`) `:955-967`. Approved with a CS stage: **Processed by CS** (emerald, `BadgeCheck`) `:970-981`, gated on `hasCsStage` `:642-643`. **Edit** (outline, `Edit` icon) at any non-voided status `:983-991` | same | Edit (draft/rejected) `:479-483`, Submit `:484-488`, Send back + Send for approval `:489-503`, Reject + Approve (no icons, Reject first) `:504-523`, **Mark done** `:524-528` (no `hasCsStage` gate) | Wording, icons, colours, order, CS gate differ | One wording table (section B). Make the buttons match the PR's markup exactly (icons, emerald Approve / Processed by CS, Approve before Reject). Keep OCN-only Submit (the OCN raiser submits in the CRM; PR staff never see Submit because the portal form submits). Best: extract the PR's primary block into a shared `FormWorkflowButtons` (props: flags + handlers + labels) used by both |
| Dialog: send for approval | No dialog: one click on Change to pending approval (`useAction` `:360-374`). The `Send for approval` link dialog (`:1043-1205`) is dead code: nothing sets `approvalDialogOpen` true (grep finds no `setApprovalDialogOpen(true)`) | same | No dialog: one click (`:499-501`) | none (both one click) | keep; do not copy the dead PR dialog |
| Dialog: send back (reject a submitted form) | `AlertDialog` "Reject this submission", label "Reason", placeholder, confirm **Confirm reject** (`:1651-1713`) | same | `ReasonDialog` (`Dialog`) "Send back to the raiser", "Reason *", confirm "Send back" (`OCN/...Detail.tsx:95-147`, spec `:99`) | Title, wording, primitive | Shared `ReasonDialog` with title/label/confirm props; PR wording. Caution: a new destructive `AlertDialog` importer is a defect per CLAUDE.md, so make the shared one a `Dialog` (OCN's) and point the PR at it too, or keep OCN's `Dialog` with PR words |
| Dialog: approve / reject | Approve: no dialog. Reject: `AlertDialog` "Reject this request", "Reason", **Confirm reject** (`:1716-1775`) | same | Approve: no dialog. Reject: "Reject this notice", "Remarks *", confirm "Reject" (`:100`) | Wording | same shared dialog, PR words |
| Dialog: void | `VoidDialog` (`components/common/VoidDialog.tsx:42`, `onConfirm(reason)`) + `VoidBanner` (`:1241-1253`) via `useFormVoid` | same | `ReasonDialog` kind void, min 3 chars (`:102`); no void banner | Different dialog, no banner | Reuse `VoidDialog` as is (`onConfirm={(r) => voidIt.mutateAsync({...rev, reason: r})}`) and `VoidBanner` (OCN detail already returns `voided_by_name`, `voided_at`, `void_reason`, `types/orderChangeNotice.ts:79-81`) |
| Dialog: process / Processed by CS | `AlertDialog` "Mark as processed by CS?", body about the contact update, "Message to contact (optional)", confirm **Processed by CS** (`:1858-1907`). Plus gear **Mark as closed** -> "Mark as closed?" / **Confirm close** (`:1909-1957`) | same | "Mark done" / "Customer Service comment (optional)" / "Mark done" (`:101`); no close | Wording; OCN has no close | PR title and confirm word; keep the OCN label "Customer Service comment (optional)" because the OCN sends nothing to a contact (the comment is stored as `cs_comment`). Close is not asked for; leave out |
| Banners above the body | `HandlingLockBanner`, `FormActionBanner`, `UndoActionDialog`, `RejectionReasonBanner` (`:1215-1230`), `RevisionBanner` (`:1233-1239`), `VoidBanner` | same | `HandlingLockBanner`, `FormActionBanner`, `UndoActionDialog` (`:550-577`) | No rejection-reason, revision or void banner | Reuse `RejectionReasonBanner` (fields `approval_comments`, `rejected_by_name`, `approved_at` exist), `VoidBanner` as is; `RevisionBanner` once the OCN has a revision reason (it has `revision_no`, the revise `reason`) |
| Detail / edit layout (view = edit) | View: read card `Card border-2` + badge + pill + centred title + 2-col grid (`:1266-1418`). Edit: separate page with `PurchaseRequestDocumentEditCard` (`PRC/PurchaseRequestForm.tsx:767-777`), footer Cancel / Update & Reply / Update (`:1186-1262`) | same | View: `DetailsCard` same shell (`OCN/...Detail.tsx:149-222`). Edit: separate page, `OrderChangeNoticeForm` same shell (`OCN/OrderChangeNoticeForm.tsx:364-558`) | Already mirrored (both copy the PR shell); field order matches between OCN view and edit except the date being editable on neither | reuse as is; the visual shell is already the PR's. A shared `DocumentCardShell` (badge + pill + centred title) is optional, three copies exist |
| Type of change block | n/a | n/a | Toggle group + boxed "Risk: X" + guide text (`OrderChangeNoticeForm.tsx:476-503`); detail reads name, Risk, guide (`OrderChangeNoticeDetail.tsx:186-197`) | owner item 2 | see section D |
| C.S. in charge | none on the PR (CS person = CS SLA stage assignee; list column "Assigned To" `PRC/PurchaseRequestsList.tsx:483-495`) | same | Manual user picker "C.S. Incharge" (`OrderChangeNoticeForm.tsx:456-465`), shown in detail (`OrderChangeNoticeDetail.tsx:180-182`) | owner item 1 | see section C |
| Sign-off block | `PurchaseRequestSignoffFooter variant="detailCard"`: Requested by / Approved (Rejected) by + date / comments (`PRC/PurchaseRequestSignoffFooter.tsx:106-129`, used `:1415,1590`) | same | Same component, `variant="decision"` (Decision / Name / Date / Remarks) (`OrderChangeNoticeDetail.tsx:240-254`; variant `PurchaseRequestSignoffFooter.tsx:57-75`, the OCN is its only user) | Different variant | Use `detailCard` with `requested_by` (OCN already has it) and drop the `decision` variant (delete-only change in the shared file). Then "Requested by" in the field grid duplicates the footer; the PR has Requested by only in the footer, so move it there |
| Customer Service comment | n/a (PR's process note is a message, not stored on the card) | n/a | Section "Customer Service comment" with empty state "No comment yet / Nothing from Customer Service so far." (`OrderChangeNoticeDetail.tsx:206-216`) | OCN-only field | keep (a field difference); see D for its hint line |
| Attachments | `PurchaseRequestAttachmentsSection` (PanelDataGrid "Linked Attachments", `PRC/PurchaseRequestAttachmentsSection.tsx:200-217`), tied to PR hooks and PR link route (`:10-12`) | same | `EntityAttachmentsSection` (`components/common/EntityAttachmentsSection.tsx`, generic, deferred Unlink, drop zone) (`OrderChangeNoticeDetail.tsx:591-601`) | Different component, same PanelDataGrid look | keep `EntityAttachmentsSection`: it is the generic one and follows the no-confirm Unlink rule; the PR one is PR-bound. Check the title text matches ("Linked Attachments" vs the generic one's) |
| Conversation | Tab **Comments (N)** (`FormComments`, read-only when voided) from the shell (`SH/FormDetailWithSLATabs.tsx:40-58`). Separately, Respond.io "Chat records" sheet (`PurchaseRequestConversationPanel`, `PRC/...Detail.tsx:1608-1643`), only when `respond_inbox_url` | same | Tab **Conversation** = `FormComments kind="order_change_notice"` (`OrderChangeNoticeDetail.tsx:603-605`), never read-only | Label, icon, count, voided read-only | Use the shell's Comments tab. Gap in the shell: `useCommentsTab` reads the voided status only for complaint / stock inquiry / PR / SF (`SH/FormDetailWithSLATabs.tsx:42-48`); add an OCN branch (`useOrderChangeNoticeQuery`) so a voided notice's thread is read-only. `PurchaseRequestConversationPanel` does not apply (no Respond inbox on a notice) |
| History | No tab. **Audit Trail** card at the bottom of Details (`PRC/PurchaseRequestDetail.tsx:1647-1649`); Complaint (`ComplaintDetail.tsx:1409`) and Stock Inquiry (`StockInquiryDetail.tsx:1318`) do the same | same | **History** tab (`OrderChangeNoticeDetail.tsx:609-611`) | Tab vs card | Move to `<AuditTrail entityType="order_change_notice" title="Audit Trail">` at the bottom of Details (reuse as is). Retraining: hand test A10, A11 and step 19 say "History tab" |
| SLA tab | **SLA Tracking** (`Timer`), last, from the shell (`SH/FormDetailWithSLATabs.tsx:116-119,136-141`) | same | **SLA** (no icon), third (`OrderChangeNoticeDetail.tsx:606-608`) | Label, icon, position | comes free with the shell |
| Revisions tab | `FormRevisionsTab` via `FormDetailTabsWithRevisions` (`SH/FormDetailTabsWithRevisions.tsx:84-94`); kinds `stock_inquiry / purchase_request / sponsorship_form / complaint` (`SH/FormRevisionsTab.tsx:57-62`) | same | none (deferred, `OrderChangeNoticeDetail.tsx:77`) | Missing | Slice 2 needs a BE lineage route for the OCN first. Until then use `FormDetailWithSLATabs` (no Revisions); switch to `FormDetailTabsWithRevisions` with a new `order_change_notice` revisions kind when the lineage ships (extend the shell: kind union + record probe `:73-80`) |
| List page | `PurchaseRequestsList` (`PRC/PurchaseRequestsList.tsx`): select column + bulk Delete (`:321,698-706`), Type (unscoped only), Number, Rev, Submitted date, Created At, Last activity (default sort `:90`), Status, Customer, Project Title, Purpose / Sponsor Subject, Sales Type, Requested By, Assigned To, Handled By, blank actions col (`:340-515`). Toolbar: search, Filters (Type, Status, Assigned to, Last activity) with an active-filter chip (`:601-602`), Export, Report (`:681-693`), Create (`:565-570`). `tableLayout={{ columnsVisibility: true }}` (`:582`, no fixed width) | same component, `requestType="sponsorship_form"`, Report permission (`sponsorship-forms/page.tsx:20-24`) | `OrderChangeNoticesList` (`OCN/OrderChangeNoticesList.tsx`): OCN no., Date, Customer, Customer PO no., Type, Risk, Project, Requested by, Status (`:113-205`); Filters Status / Type / Risk (`:255-311`); Export, Create (`:312-322`); `tableLayout` fixed + resizable (`:240`) | No Rev, Last activity, Assigned To, Handled By columns, no active-filter chip, no Report. OCN status words differ (Done) | Keep the OCN list component (field differences, and it already obeys the fixed-layout rule the PR list breaks). Align: status word "Processed by CS" (`:48`), add Rev column (`revision_no` is on the row), optionally Assigned To / Handled By / Last activity (BE serializer has none today: `order_change_notice_service.py` summary ~`:1000-1020`), filter chip via `activeSummary`. Risk column: section D |
| Create page | Staff: `PageHeader` with a Cancel action (`purchase-requests/new/page.tsx:17-24`) + `PurchaseRequestForm` -> `StaffPurchaseRequestForm` (CardTitle "Header" layout), footer Cancel / Create (`PRC/PurchaseRequestForm.tsx:1186-1262`). Limited salesperson: `MyRequestPortalForm` (portal `SubmissionForm`, Save as draft / Submit, `app/(auth)/portal/components/SubmissionForm.tsx:2371,2414`) | Staff from a project: the salesperson's portal form (`PRC/PurchaseRequestForm.tsx:121-125`) | `PageHeader` (no Cancel) + `OrderChangeNoticeForm`, PR document shell, footer Cancel / Save as draft / Submit, pre-save drop zone (`OrderChangeNoticeForm.tsx:540-566`) | OCN create looks like the PR's DOCUMENT card, not the PR staff create card; Cancel in the footer not in the page header | Leave the create form shape (it is the PR document shell the owner tested). Optional: move Cancel to the page header like the PR (`new/page.tsx`, `[id]/edit/page.tsx`). The portal kind (`MyRequestPortalForm`) for the OCN is slice B (`lib/portal-form-kinds.ts:105-139`, `PORTAL_PAGES_PENDING`) |

## B. Status words and button labels, PR / SF vs OCN, and the backend behind them

| Step | PR / SF button | PR / SF route + action key + SLA event | PR status word | OCN button today | OCN route + action key + event | OCN status word today |
|---|---|---|---|---|---|---|
| raiser submits | (portal) Submit | `POST /purchase-requests/{id}/submit` (`BE/api/v1/procurement/purchase_requests.py:329`) | Submitted / Appealed | Submit | `POST /order-change-notices/{id}/submit` (`BE/api/v1/procurement/order_change_notices.py:256`), event `submit` | Submitted / Appealed |
| admin forwards | **Change to pending approval** (`PRC/...Detail.tsx:901`) | `POST /{id}/set-pending-approval` (`:410`), `pr.send_for_approval` (`:514`) | Pending approval | **Send for approval** (`OCN/...Detail.tsx:500`) | `POST /{id}/send-for-approval` (`:264`), `ocn.send_for_approval`, event `send_for_approval` | Pending approval |
| admin returns | **Reject** -> "Confirm reject" (`:915,1709`) | `POST /{id}/reject-submitted` (`:487`), `pr.reject_submitted` (`:559`) | Rejected | **Send back** (`:497`) | `POST /{id}/reject-submitted` (`:284`), `ocn.reject_submitted`, event `reject_submitted` | Rejected |
| approver | **Approve** / **Reject** (`:953,966`) | `POST /{id}/approval-decision` (`:537`), `pr.approval_decision` (`:627`) | Approved / Rejected | Approve / Reject (`:520,513`) | `POST /{id}/approval-decision` (`:305`), `ocn.approval_decision`, events `approved` / `approval_rejected` | Approved / Rejected |
| CS finishes | **Processed by CS** (`:980`), toast "Marked as processed by CS." (`:1893`) | `POST /{id}/process` (`:590`), `pr.finalize` (`:686`), status `processed_by_cs`, event `resolved` | **Processed by CS** (`PRC/PurchaseRequestsList.tsx:73`, detail `:644-645`) | **Mark done** (`:526`), toast "Marked done" (`hooks/useOrderChangeNotices.ts:183`) | `POST /{id}/done` (`:330`), `ocn.finalize`, status `processed_by_cs` (`BE/services/order_change_notice_service.py:56`), event `resolved` | **Done** (`types/orderChangeNotice.ts:152`; BE `order_change_notice_service.py:65`) |
| CS cannot fulfil | gear **Mark as closed** (`:746`) | `POST /{id}/close` (`:659`), `pr.finalize` (`:729`), status `closed` | Closed | none | none | n/a |
| void | gear **Void** | `POST /{id}/void` (`:702`) | Voided | gear Void | `POST /{id}/void` (`:355`) | Voided |
| revise | n/a (portal revisions) | n/a | n/a | gear **Revise** | `POST /{id}/revise` (`:368`) | back to Draft |

Conclusion: the stored values and SLA events already match (the plan mirrored the PR lifecycle,
`PLAN-ocn-order-change-notice-12nov.md:17-24`). Only WORDS differ, so no route, column or event rename is
needed. Changing "Done"/"Mark done" to "Processed by CS" touches these word tables:

- FE: `types/orderChangeNotice.ts:152` (`OCN_STATUS_WORDS`, also feeds History via `lib/audit-fields.ts:76-84`
  and Related records via `project-sales/[projectId]/components/relatedRecordTypes.ts:47-49`);
  `OCN/OrderChangeNoticesList.tsx:48`; `OCN/OrderChangeNoticeDetail.tsx:101,526`;
  `hooks/useOrderChangeNotices.ts:161,166,183` toasts (PR toasts: "Status set to Pending approval" `:369`,
  "Submission rejected; ..." `:1697`, "Marked as processed by CS." `:1893`).
  `ocnStatusPillKey` maps `processed_by_cs` to `completed` (`types/orderChangeNotice.ts:174-178`); both
  are emerald in `lib/status-pill.ts:31,78`, so the colour already matches.
- BE: `services/order_change_notice_service.py:65` (`STATUS_LABELS`, read by the History reader
  `api/v1/audit/audit_logs.py:291-299` and the assistant list `services/assistant_registry/procurement.py:25-34`),
  `:822` (`RAISER_NOTICES "is done"`), `:1325` (`ACTION_WORDS "ocn.finalize": "Mark done"`);
  `services/form_sla_service.py:271` ("mark the notice done (CS)"; PR reads "process the request (CS)" `:256`).
- Tests that pin the old words: FE `OCN/OrderChangeNoticeDetail.test.tsx:14,210,295`,
  `OCN/OrderChangeNoticeDetail.round4.test.tsx:254`, `OCN/OrderChangeNoticesList.test.tsx:211,269`,
  `project-sales/[projectId]/components/TasksPanel.test.tsx`; BE `tests/test_ocn_round7.py`,
  `tests/chatbot/agent/test_ai_order_change_notice.py`, `tests/test_oi_waiting_for_cs.py` (grep hits; read
  before editing). User guide `documentation/user-guides/project-sales-admin/order-change-notice.md:53,100`.
- Optional, for full parity: rename the OCN button "Send for approval" -> "Change to pending approval" and
  "Send back" -> "Reject" (the routes stay `send-for-approval` / `reject-submitted`; `ACTION_WORDS` `:1322-1323`
  follow). Ask the owner: item (3) quotes only the CS step.
- The OCN CS button should also hide until a CS stage exists, as the PR does (`hasCsStage`,
  `PRC/...Detail.tsx:640-643`), or a "No CS" form would offer it. Today the OCN never has "No CS" (see C),
  so this is only for parity.

## C. Owner item (1): derive C.S. in charge from the contact's routing

### What "salesperson routing configured on the contact" is

- Table `respond_contact_cs_routing` (`BE/models/access.py` ~`:419-445`): per `respond_contact_id` +
  `use_case`, rows of `match_conditions` (AND predicates), `priority`, `cs_pic_user_id` (NULL = "No CS").
- Edited on the contact: Contacts > contact > Routing (`app/(protected)/user-management/contacts/[id]/routing/page.tsx`,
  `components/routing/ContactCsRoutingRules.tsx`); the use-case picker offers only Purchase Request and
  Sponsorship Form (`components/routing/csRoutingMock.ts:47-50`).
- Service `BE/services/cs_routing_service.py`: `PINNABLE_USE_CASES = ("purchase_request", "sponsorship_form")`
  (`:39`), eligible PIC rule `eligible_pics_query` (`:50`), routable fields per use-case table (`:155-232`),
  `upsert` refuses other use cases (`:308-311`). Matching engine `BE/services/cs_routing_match.py:47-71`
  (lowest priority wins, empty = wildcard).

### How the PR gets its CS person (it has no CS field)

At CS-stage spawn, `form_sla_service._start_for_config` (`BE/services/form_sla_service.py:1050-1072`):
if the stage reads pins (`_reads_cs_pin`, `:1304-1317`: agent `purchase_request`, team set
`customer_service`, entity type in `PINNABLE_USE_CASES`), it looks up the REQUESTOR contact
(`_routing_contact_id`, `:1255-1301`: `purchase_requests.requested_by_contact_id`), evaluates that
contact's rules against the form's header values (`_load_form_field_values`, `:1150-1189`, plus computed
`product_lines` / `customer_debtor_type` for PR/SF only `:1187-1212`) and assigns the winning PIC
(`_resolve_pinned_assignee`, `:1319-1390`); no pin -> round-robin. The person shows as the SLA tracker's
assignee (list "Assigned To", SLA tab), not as a field on the form.

### What the OCN does today

- `cs_in_charge_user_id` is a manual picker of ANY user (`OrderChangeNoticeForm.tsx:456-465`, validated only as
  "exists" `BE/services/order_change_notice_service.py:360-362`). It drives own-scope visibility
  (`is_mine` `:250-259`, `own_clause` `:307`) and display (`:1018-1019`). Nothing else reads it.
- The OCN CS stage config is a copy of the PR's (same `agent_code`, `team_set_code`; migration
  `BE/../alembic/versions/ocn_0001_order_change_notice.py:449-466`), but `_reads_cs_pin` excludes it (not in
  `PINNABLE_USE_CASES`) and `_routing_contact_id` returns None for it, so the OCN CS stage is always
  round-robin. `_emit_sla` passes no contact (`order_change_notice_service.py:776-788`).
- Result today: the person picked as "C.S. Incharge" and the person the CS SLA task is assigned to are
  unrelated. That is a defect regardless of the owner's request.

### Options

| Option | Source contact | Evidence | Pros | Cons |
|---|---|---|---|---|
| A. Requested-by contact (recommended) | `order_change_notices.requested_by_contact_id` (`BE/models/project_so.py:743-746`), defaulted to the raiser's linked contact (UAC I8, `OrderChangeNoticeForm.tsx:233-244`) | Exactly the PR rule (`form_sla_service.py:1054-1064`, "pin lookup keys on the REQUESTOR", PLAN-requested-by-contact-routing D2) | Same person the salesman's PRs go to; zero new tables | Needs a rule set to read (A1 or A2) |
| B. Customer's sales agent contact | `customers.sales_agent_id` -> `SalesAgent.contact` (`BE/models/order.py:173-177,208-217`) | used for the portal debtor dropdown | Works when Requested by is blank | A notice may have a typed customer (no `customer_id`); a second routing key the PR does not use; diverges from PR |
| C. Project's salesperson | `project_id` | optional field (Q5) | none | Often blank; not the PR rule |

Which rules A reads:

- **A1 (recommended, simplest):** the OCN reads the requestor's `purchase_request` rules, evaluated against the
  OCN's own header (`customer_name`, `customer_id`; compute `customer_debtor_type` the same way). No admin
  re-configuration, no FE routing change. Rules whose conditions name PR-only fields (`project_title`,
  `total_project_value`, `sales_type`, `product_lines`) evaluate against a NULL value and fail (`equals` on
  NULL is false, `cs_routing_match.py:36-44`), so they fall through to the next rule or round-robin; a "No CS"
  rule would also apply (decide whether the OCN honours No CS: the PR form then ends at approval).
  Not measured: how many contacts have PR rules and how many are wildcard; check on the prod copy before
  deciding.
- **A2:** a new `order_change_notice` use case (add to `PINNABLE_USE_CASES`, `_USE_CASE_TABLE`
  `cs_routing_service.py:155-160`, `csRoutingMock.ts:47-50`). Every contact then needs an OCN rule, and
  until an admin adds them every OCN round-robins. Build only on a trigger: the owner wants a different CS
  for notices than for PRs.

Backend change for A1 (no migration):
`form_sla_service.py` `_reads_cs_pin` (`:1313-1317`) admits `order_change_notice`; `_routing_contact_id`
(`:1273-1280`) maps it to `projects.order_change_notices.requested_by_contact_id`; `_resolve_pinned_assignee`
and `_winning_rule_is_no_cs` query `use_case = 'purchase_request'` for an OCN (one mapping dict); and the
OCN service stamps `cs_in_charge_user_id` from the CS tracker's assignee when that stage starts (so own-scope
and the display keep working). `create`/`update` stop accepting `cs_in_charge_user_id` from the client
(`order_change_notice_service.py:360-362,410`).

FE: remove the picker (`OrderChangeNoticeForm.tsx:456-465`, state `:71,85,102,134`, user lookup `:214-218,267-270`);
the detail keeps a read-only "C.S. in charge" (empty "-" until the CS stage starts) or drops it like the PR
(the PR shows the CS person only as the SLA assignee). Recommendation: keep the read-only field (the owner
named it) and fill it from the routing.

Open question for the owner: the CS person is known only once the notice is approved (that is when the CS
stage starts). If they want to see it on a draft, the service would have to evaluate the rule at save time
(a preview), which can differ from the final assignee (coverage redirect, eligibility). Recommend: stamp
at CS-stage start, show "-" before.

## D. Owner item (2): change-type explanation and the disclaimer

Where it renders:

- Form: the boxed panel under the type buttons, `OrderChangeNoticeForm.tsx:492-502`: line "Risk: <level>"
  (`:494-497`) and the guide text (`:498-500`). The guide texts are seeded in the migration
  (`alembic/versions/ocn_0001_order_change_notice.py:106-111`, e.g. "Swap a product for another one: the old
  line goes out, the new one comes in.").
- Detail: "Type of change" field, `OrderChangeNoticeDetail.tsx:186-197`: name, "Risk: <level>" (`:189-194`),
  guide text (`:195`).
- The word "disclaimer" appears nowhere in the OCN UI (grep). Candidates, most likely first: (a) the
  "Risk: <level>" line in the same box as the guide text (form `:494-497`, detail `:189-194`); (b) the
  Customer Service comment empty-state hint "Nothing from Customer Service so far." (`OrderChangeNoticeDetail.tsx:211-214`);
  (c) the user guide sentence "The risk is shown for information. It does not change who approves..."
  (`documentation/user-guides/project-sales-admin/order-change-notice.md:26`). Confirm with the owner which;
  removing (a) and the guide text together removes the whole box.

What else reads them:

- `guide_text`: only these two render sites; BE serializes it (`order_change_notice_service.py:1078,1261`),
  types `types/orderChangeNotice.ts:20,64`. Removing the UI leaves the column harmless (the admin lookup keeps it).
- `risk_level`: list column Risk (`OCN/OrderChangeNoticesList.tsx:169-176`), Risk filter (`:52,76,84,283-293`),
  list query param (`hooks/useOrderChangeNotices.ts:51`, `services/orderChangeNoticeService.ts:80`), BE list
  filter/sort (`api/v1/procurement/order_change_notices.py:152,168`, `order_change_notice_service.py:1137-1139,1187-1203`),
  project panel schema (`BE/schemas/projects.py:1945`), assistant list column
  (`services/assistant_registry/procurement.py:17-22`), seeded on `order_change_types`.
- Recommendation: remove the guide text from form and detail; keep the Risk column and filter on the list
  (the owner asked only about the form, the paper form carries the risk, and the AC F2 sort/filter tests pin
  it) unless the owner says the risk itself is the disclaimer, in which case hide it on form and detail and
  ask separately about the list column. No backend change either way.

## E. Risks, retraining, backend, size

Changes users trained on slice 1 will notice (hand test `laneboard/scripts/2384.md`):

- Tabs become Details / Comments (N) / SLA Tracking with icons; History moves to an "Audit Trail" card at the
  bottom of Details. Hand test A10, A11, steps 14, 19, 20 and the Expected line "Tabs ... Details,
  Conversation, SLA, History" (`2384.md` Expected Part B) change.
- "Mark done" becomes "Processed by CS"; status "Done" becomes "Processed by CS" (A9, steps 18, 26 filter
  "Done").
- "C.S. Incharge" disappears from the form (A6, step 7, step 36); the CS person appears after approval.
- If the optional renames are taken: "Send for approval" -> "Change to pending approval", "Send back" ->
  "Reject" (A7, steps 16, 23).
- The risk/guide box goes (step 8 Expected).
- Gear gains Escalate / Extend / Reassign; loses "Copy link" if aligned strictly (PR has no Copy link; keep it,
  harmless).

Technical risks:

- Moving the OCN to `FormDetailWithSLATabs` moves `useUrlTab` ownership to the shell; existing OCN tests mount
  the detail alone and assert tab labels (`OrderChangeNoticeDetail.slaTab.test.tsx`, `.test.tsx`, `.round4/5`);
  they need the shell or a rewrite. The NPA hit a freeze when an SLA body rendered outside `Tabs`
  (`NewProductApplicationDetail.tsx:557-559`); the shell keeps every body inside `Tabs`, so this is the safe
  direction.
- The shell's Comments tab must learn the OCN's voided status (`SH/FormDetailWithSLATabs.tsx:42-48`) or a
  voided notice's thread stays writable.
- Old History rows keep their stored code `processed_by_cs`; History words are read at render time, so they
  flip to "Processed by CS" retroactively (fine, no data change).
- Reusing PR `AlertDialog` reject dialogs would add destructive `AlertDialog` importers (a defect per CLAUDE.md);
  keep the OCN's `Dialog` with PR wording.
- Deriving CS changes SLA assignment for live notices only from the next CS-stage start; notices already past
  approval keep their round-robin assignee. 0 rows in prod at migration time (`PLAN ...:58`), so nothing to
  backfill if slice 1 is still unmerged.
- CS derivation touches `form_sla_service`, which PR/SF/SI/complaint share: needs a PR regression test that PR
  pin routing is unchanged.

Backend changes needed: word tables (B), CS routing for OCN (C, `form_sla_service.py` + OCN service), stop
accepting `cs_in_charge_user_id` from the client. No migration, no route rename, no permission change. Note
the CS derivation is a routing change in a shared SLA service, which likely pushes the lane out of the
small-fix track (CLAUDE.md track rule: assignment logic is close to RBAC/routing; size alone may still be
under 300 lines).

Size estimates:

| Item | FE | BE | Size |
|---|---|---|---|
| 1. Tab shell (FormDetailWithSLATabs + RecordCardSlot, Comments (N), SLA Tracking, Audit Trail card, voided comments branch) | detail restructure + shell branch + test rewrites | none | M |
| 2. Header like the PR (title "Order Change Notice - OCN..", subtitle date, pill on document card only) | small | none | S |
| 3. Buttons, icons, order, dialogs (shared ReasonDialog with PR words, VoidDialog, banners, hasCsStage gate) | moderate | none | M (S if only the CS words) |
| 3b. "Processed by CS" wording end to end | small | word tables + tests | S |
| 3c. SLA gear items (Escalate, Extend, Reassign, SlaActiveTrackerControls) | reuse, ideally lift a shared block from the PR | none | S-M |
| 4. CS in charge derived from the requestor's routing (A1) | remove picker, read-only field | `form_sla_service` pin path + OCN stamp + write refusal + PR regression test | M |
| 5. Remove guide text (+ risk line if confirmed) | small | none | S |
| 6. List alignment (Processed by CS word, Rev column, filter chip; Assigned To/Handled By/Last activity need BE serializer work) | small-moderate | optional | S (M with the BE columns) |
| 7. Revisions tab | shell kind extension | lineage route (slice B) | L, already slice B |

Overall slice 2 as asked (items 1-5): M-L, full track because of the shared SLA routing change.
