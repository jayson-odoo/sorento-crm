# UAC: PS-REGISTER-CHECK-FIRST (30 Oct 2026, final)

Source: card `CARD-ps-register-check-first-29oct.md` v1.4 (owner answers Q-A..Q-E all (a), then mock notes: Q-C became
(b) "any document uploaded will do"), mock v4 `documentation/mockups/PS-REGISTER-CHECK-FIRST/index.html` approved
30 Oct 10:27 with one change (Spec In hidden, not disabled, while a Registered project has no document); tab
questions V1-V3 = (a). BE = `sorento_crm_backend/app`, FE = `sorento_crm_frontend/app/(protected)/project-sales`.

## G. A document gates Registered -> Spec In (BE + FE)

- AC-G2. `POST /api/v1/project-sales/projects/{id}/status` from status key `registered` to key `specified` on a project
  with no live document -> 422, code `project_requirements_missing`, message exactly "Upload the requirements document
  before moving this project to Spec In." The project's status is unchanged. A live document is exactly what the
  Documents tab lists: an `attachments` row with `entity_type='project'`, `entity_id=<project id>`, not `is_deleted`
  (the upload writes these on the row, `BE/api/v1/resources/attachments.py:1130-1131`; the list filters on them,
  `BE/services/resources_service.py:840-841`). Corrected 30 Oct after the browser pass: the first text named
  `entity_attachment_links`, which the Documents upload never writes.
- AC-G3. Same move with one live document linked (any attachment type, e.g. Project Document) -> 200, status Spec In.
- AC-G4. A deleted document does not count; another project's document does not count. No attachment type is created
  or required (no seed, no new kind).
- AC-G5. Not gated: Registered -> Lost, Dormant, PO received, Back to identified; every move not starting at Registered;
  the first-PO automatic move (`BE/services/project_po_service.py:209`).
- AC-G6. Spec In -> Registered then -> Spec In again with no document -> 422 again.
- AC-G7. FE header (`[projectId]/components/ProjectDetailClient.tsx:388-392`, `ProjectStatusAction.tsx`): a project in
  Registered whose Spec In move is available and that has 0 documents (the Documents tab query
  `['project-documents', id]`, `ProjectDocumentsPanel.tsx:61-69`) shows "Upload Requirement" as the header call to
  action and does NOT show Spec In (hidden: no disabled button, no reason text). Shown only to users who may upload
  (`canWorkOnProject`, `ProjectDocumentsPanel.tsx:215`).
- AC-G8. "Upload Requirement" opens an "Upload requirement" dialog: drop zone, Cancel, Upload. Upload files the file(s)
  as a Project Document (today's upload service, `_shared/services/projectDocumentService.ts:72-125`) and makes NO
  status call. After it, the documents query refreshes and the header shows Spec In (today's button) and no longer
  shows Upload Requirement.
- AC-G9. With >= 1 document (any, also one uploaded from the Documents tab) the header is today's: Spec In primary.
- AC-G10. A 422 `project_requirements_missing` from the server (stale page, other tab) shows its message as today's
  error toast; the project stays in Registered.
- AC-G11. Existing projects are not touched: no backfill, no block on projects already past Registered. The Documents
  tab upload dialog is unchanged (no Kind select).

## S. Salesperson submit runs the Check on the server (BE)

- AC-S1. A user with only `projects.registrations.submit` who registers with submit=true (`crm_register`,
  `BE/services/project_registration_service.py:744`) a title + developer that `find_clashes` reports as blocking ->
  409, code `project_already_registered`, the same message staff get (`_describe_blockers`,
  `BE/services/project_service.py:206-243`); no project row is created.
- AC-S2. Submitting an existing draft (`crm_submit`, `:818`) whose title + developer block -> the same 409; the draft
  stays a draft.
- AC-S3. Save draft (submit=false) with a blocking title still saves (Q-E: drafts stay free).
- AC-S5. The 409 a user WITHOUT `projects.projects.view` gets names the project (code, title) but never the holder's
  name (the clash preview already hides owner fields from them, `BE/api/v1/projects/projects.py:131-136`); staff keep
  today's message. (Reviewer blocker, 30 Oct.)
- AC-S4. A similar but not blocking match (below the block threshold, or another developer) does not refuse submit.

## R. "Register interest" reads "Register as secondary lead" (BE + FE)

- AC-R1. Notification (in-app title and email subject) for a dispute request: "<name> registered as secondary lead on
  <code>"; body "<name> registered as secondary lead on <code>: <title>" (`BE/services/project_notify_service.py:207-209`).
  Notification type key and the stored `kind` (`dispute`) are unchanged.
- AC-R2. Register form: the match action and the dialog title read "Register as secondary lead on <code>"; the dialog's
  submit reads "Register as secondary lead"; the salesperson toast reads "Registered as secondary lead on <code>".
- AC-R3. `useProjects.ts:499` toast for a dispute reads "Registered as secondary lead" (join keeps "Request sent to the
  project owner").
- AC-R4. Access panel: button "Register as secondary lead", heading "Secondary leads" (was "Interested"), past
  decision "Secondary lead by <name>" (was "Interest"), dialog title "Register as secondary lead on <code>", submit
  "Register as secondary lead". "Ask to join" unchanged.
- AC-R6. Access panel: pending and decided secondary-lead requests (kind `dispute`) render as one table under
  "Secondary leads" using `components/common/PanelDataGrid.tsx` (fixed layout, resizable columns, long text truncated
  with `title`): columns Salesperson, Date, How they found it, Status (Badge: Pending / Reassigned / Dismissed), and
  for pending rows to a holder of `projects.projects.manage` the actions "Reassign to <name>" and "Dismiss". Ask-to-join
  requests ("Open requests") and their past decisions keep today's rendering. The table sits inside the Access card
  (mock B1). Badges: Pending amber, Reassigned green, Dismissed grey.
- AC-R5. No user-visible "interest" string remains in ProjectForm, ProjectAccessPanel, useProjects toasts or the
  notification service.

## W. Register wizard (FE, create only; mock v4 section A)

- AC-W1. Create mode shows a step strip (`components/common/WizardSteps.tsx`, steps Check, Details) and step 1 only:
  Project title *, AI extract, Developer. No Details or Lead/customer/salesperson fields, no Register / Save draft /
  Submit for approval. Footer: Back (off on step 1) left; Cancel + Check right.
- AC-W2. Check with no blocking candidate -> "No clash"; the forward action becomes Next.
- AC-W3. Check with only non-blocking rows (near match, other developer) -> also just "No clash"; no similar rows are
  shown; Next. The server's matching is unchanged.
- AC-W4. Check with a blocking row -> one line "Clash: <code> <title>"; the forward action is "Register as secondary
  lead on <code>" (opens the dialog, AC-R2); Next never shows.
- AC-W5. Check fails or times out -> "The check did not finish. Try again."; the forward action stays Check.
- AC-W6. Editing title or developer after a Check clears the result and the action returns to Check.
- AC-W7. Next opens step 2 Details: today's Details section and a "Customer and salesperson" section (AC-L1), with
  today's other required rules; Register project (staff) or Save draft + Submit for approval (submit-only) bottom right;
  Back left returns to step 1 keeping every value typed.
- AC-W8. AI extract on step 1 fills title and developer and keeps the other extracted values for step 2.
- AC-W9. Edit mode: no wizard and no step strip; every section shows; Check runs as today but shows the same
  Clash / No clash result (no similar rows).
- AC-W10. Usable at 375 px and 1280 px; at 375 the footer stacks like Create lead (Back, Cancel, forward action).
- AC-W11. A blocking clash found by the re-check at Register on step 2 shows the same "Clash: <code> <title>" line
  with the "Register as secondary lead on <code>" action.

## T. Project tabs (FE; mock C0, V1-V3 = (a))

- AC-T1. Tab labels and order exactly: Overview, Documents, Quotation, Samples Request, Sponsorship Form, PO, SO,
  Stakeholders, Tasks, Activity.
- AC-T2. PO tab = `PurchaseOrdersPanel`; SO tab = `SalesOrdersPanel` showing every sales order of the project (no
  `withoutPurchaseOrder`).
- AC-T3. Samples tab removed with `SamplesPanel.tsx` and `SampleDialog.tsx`; `?tab=samples` opens Samples Request;
  `?tab=orders` (and the legacy `pos`, `schedules`) opens PO; the SO tab's id is `sales-orders`, so `?tab=sales-orders`
  opens SO, and the sales order pages' "back to project" links use it. Stored samples and BE endpoints untouched.

## L. No lead on registration (owner ruling 30 Oct ~13:55: "a"; replaces the 29 Oct "lead governs register" rule)

- AC-L1. The project form (create and edit, staff and submit-only) has no Lead field and no "Create lead" option. Step 2's
  section reads "Customer and salesperson". Customer is the server-search picker (`listCustomerOptions`,
  `FE/_shared/services/projectService.ts:249-261`), always editable, required to Register / Submit for approval as today
  (`require_customer`); Save draft may leave it empty as today.
- AC-L2. Staff `POST /api/v1/project-sales/projects/` without `lead_id` and with a customer -> 201; no
  `project_lead_required` refusal anywhere. The project's customer is the one sent (no customer-from-lead rule).
- AC-L3. Submit-only `crm_register` (draft and submit) and `crm_submit` need no lead; submit still needs a customer.
- AC-L4. Registering never links or changes a lead: no `projects.lead_id` is set, and no lead's outcome / qualified_at /
  status changes, even if a `lead_id` is sent (it is ignored). Leads qualify only through the lead page's Qualify.
- AC-L5. Editing an existing project that already has a lead keeps that link untouched (the form no longer sends
  `lead_id`); its customer is the editable picker. An edit (PUT) that does send `lead_id` ignores it, like register:
  the link, the lead and its customer stay as they were, and the project's customer is the one sent (no
  customer-from-lead rule, no `project_customer_not_lead_customer` refusal). An edit that sends `customer_id: null`
  clears the project's customer, as main does for a project without a lead (reviewer, 30 Oct: never keep it silently);
  a linked lead and its customer are never touched by a project edit.
- AC-L6. Unchanged: the lead pages and their Qualify, the Check, the Spec In document gate, secondary leads, AI extract
  (it does not fill Customer).
