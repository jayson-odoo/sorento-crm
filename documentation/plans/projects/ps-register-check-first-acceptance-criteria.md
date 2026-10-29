# UAC: PS-REGISTER-CHECK-FIRST (30 Oct 2026)

Source: card `CARD-ps-register-check-first-29oct.md` (owner answers Q-A..Q-E all (a), 30 Oct), mock v2
`documentation/mockups/PS-REGISTER-CHECK-FIRST/index.html`. BE = `sorento_crm_backend/app`, FE =
`sorento_crm_frontend/app/(protected)/project-sales`. Sections W and T follow mock v2 and are final only once the owner
approves v2; sections G, S and R are final.

## G. Requirements document gates Registered -> Spec In (BE + FE)

- AC-G1. A document kind "Requirements" exists: `attachment_types` row, code `project_requirements`, type_name
  `Requirements`, seeded idempotently at startup by the project seed (`BE/services/project_seed_service.py` `run`,
  called from `BE/main.py:546`). Running the seed twice leaves one row. No schema change.
- AC-G2. `POST /api/v1/project-sales/projects/{id}/status` from status key `registered` to key `specified` on a project
  with no live (not `is_deleted`) attachment of kind `project_requirements` linked to it (`entity_attachment_links`,
  `entity_type='project'`, `entity_id=<project id>`) -> 422, code `project_requirements_missing`, message exactly
  "Upload the requirements document before moving this project to Spec In." The project's status is unchanged.
- AC-G3. Same move with one live Requirements attachment linked -> 200, status is Spec In.
- AC-G4. A file of kind Project Document (`project_document`) does not count (Q-C a). A deleted Requirements file
  does not count.
- AC-G5. Not gated (Q-B a): Registered -> Lost, Dormant, PO received, Back to identified; every move that does not start
  at Registered (e.g. Spec In -> Sample Submission); the first-PO automatic move (`BE/services/project_po_service.py:209`).
- AC-G6. Spec In -> Registered (back) then -> Spec In again with no Requirements file -> 422 again.
- AC-G7. FE: clicking the stage action whose target is Spec In on a Registered project and getting 422
  `project_requirements_missing` opens a "Requirements needed" dialog (mock C2) instead of an error toast: the message
  above, a drop zone (kind preset to Requirements), Cancel, and "Upload and move to Spec In", which uploads the files
  as Requirements and then repeats the move. Any other error keeps today's toast.
- AC-G8. FE: the Documents tab upload dialog has a Kind select, Project Document (default) and Requirements; the
  Documents list shows each file's kind (mock C3). The kind is looked up by code (10 legacy types have no code).
- AC-G9. Existing projects are not touched: no backfill, no block on projects already past Registered.

## S. Salesperson submit runs the Check on the server (BE)

- AC-S1. A user with only `projects.registrations.submit` who registers with submit=true (`crm_register`,
  `BE/services/project_registration_service.py:744`) a title + developer that `find_clashes` reports as blocking ->
  409, code `project_already_registered`, the same message staff get (`_describe_blockers`,
  `BE/services/project_service.py:206-243`); no project row is created.
- AC-S2. Submitting an existing draft (`crm_submit`, `:818`) whose title + developer block -> the same 409; the draft
  stays a draft.
- AC-S3. Save draft (submit=false) with a blocking title still saves (Q-E: drafts stay free).
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
- AC-R5. No user-visible "interest" string remains in ProjectForm, ProjectAccessPanel, useProjects toasts or the
  notification service.

## W. Register wizard (FE, create only; per mock v2)

- AC-W1. Create mode shows a step strip (`components/common/WizardSteps.tsx`, steps Check, Details) and step 1 only:
  Project title *, AI extract, Developer. No Details or Lead/customer/salesperson fields, no Register / Save draft /
  Submit for approval. Footer: Back (off on step 1) left; Cancel + Check right.
- AC-W2. Check with no candidates -> "No existing project matches this title."; the forward action becomes Next.
- AC-W3. Check with only non-blocking rows -> rows under "Similar project:"; Next.
- AC-W4. Check with a blocking row -> "Project already registered:" with the row; the forward action is "Register as
  secondary lead on <code>" (opens the dialog, AC-R2); Next never shows.
- AC-W5. Check fails or times out -> "The check did not finish. Try again."; the forward action stays Check.
- AC-W6. Editing title or developer after a Check clears the result and the action returns to Check.
- AC-W7. Next opens step 2 Details: today's Details and "Lead, customer and salesperson" sections and fields, with
  today's required rules; Register project (staff) or Save draft + Submit for approval (submit-only) bottom right;
  Back left returns to step 1 keeping every value typed.
- AC-W8. AI extract on step 1 fills title and developer and keeps the other extracted values for step 2.
- AC-W9. Edit mode: no wizard and no step strip; every section shows; Check behaves as today.
- AC-W10. Usable at 375 px and 1280 px; at 375 the footer stacks like Create lead.

## T. Project tabs (FE; per mock v2 C0, answers V1-V3 pending)

- AC-T1. Tab order: Overview, Documents, Quotation, Samples Request, Sponsorship Form, PO, SO (labels per V3), then
  Stakeholders, Tasks, Activity (per V1).
- AC-T2. PO tab = `PurchaseOrdersPanel`; SO tab = `SalesOrdersPanel` with all the project's SOs (per V2).
- AC-T3. Samples tab removed with `SamplesPanel.tsx` and `SampleDialog.tsx`; `?tab=samples` opens Samples Request;
  `?tab=orders` (and the legacy `pos`, `schedules`, `sales-orders`) opens PO. Stored samples and BE endpoints untouched.
