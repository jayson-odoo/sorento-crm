# CARD: PS-REGISTER-CHECK-FIRST v1.3 (30 Oct 2026)

**Owner mock v2 notes (30 Oct 09:54), drawn in mock v3:** (1) the Check shows only Clash or No clash: non-blocking
"similar" rows are not shown (rule 3 now reads "No clash"); the server's `find_clashes` and its thresholds are
unchanged. (2) Secondary leads on the Access panel become a table (`components/common/PanelDataGrid.tsx`). (3) "Don't
need to choose type, any document uploaded will do": **Q-C is now (b)**. No Requirements kind, no seed, no Kind select;
the Registered -> Spec In gate passes when the project has ANY live document (rules 11-13 below are superseded where
they name the kind). V1-V3 (tabs) re-asked.

**Owner answers (30 Oct ~00:30): Q-A (a), Q-B (a), Q-C (a), Q-D (a), Q-E (a).** Mock notes (00:32) drive mock v2:
the register form becomes a progressive wizard like Create lead (`FE/leads/components/LeadWizardDialog.tsx:189,350-383`):
step 1 Check with Check as its bottom-right action (Next after a pass, "Register as secondary lead on <code>" on a
match), step 2 Details holds today's Details + Lead, customer and salesperson sections and is the only place Register
shows. Added scope: project tabs reordered to Overview, Documents, Quotation, Samples Request, Sponsorship Form, PO,
SO; the Samples tab removed (`SamplesPanel.tsx` / `SampleDialog.tsx` are used only by that tab; no `?tab=samples`
link in BE or MCP; tests touching it: `PurchaseOrdersPanel.test.tsx:67,389`, `panels.approvalGate.test.tsx:78,102`,
`ProjectDetailClient.sampleRequestsTab.test.ts:22`). Tab questions V1-V3 are in mock v2 section C0.

Paths: BE = `sorento_crm_backend/app`, FE = `sorento_crm_frontend/app/(protected)/project-sales`. Code read on
origin/main ec29a81c3b. People are roles (Sales A, Sales B, Manager); titles are masked.

## How it works today (facts)

- **Check** = a fuzzy match on the project TITLE only (casefold + collapsed spaces, `BE/services/project_clash_service.py:86`),
  scoped to company and developer (`:258`), approved projects only (`:245-249`). Score = best of pg_trgm similarity /
  strict word similarity (`:156`); shown at >= 0.55, blocks at >= 0.70 or containment of 6+ chars (`:45-50`, tunable in
  System Settings, `:134`). It blocks only when the developer is the same or blank, the match is open and not a sibling
  phase (`:287-305`). The response marks each row `blocks: true|false`; there is no "exact" flag (`BE/schemas/projects.py:156-185`).
- **Form**: all sections show from the start (`FE/_shared/components/ProjectForm.tsx:192-196`): "Who and what" (title *,
  developer, type, template, :428-548), "Details" (:550-719), "Lead, customer and salesperson" (:721-805). Check is an
  optional button (:454-464). A failed or timed-out Check is swallowed with no message (:272), and the submit re-check
  ignores a failure too (:394). A block shows "Register interest in <code>" (:811-814, create mode only).
- **Server**: staff Register re-runs the Check and refuses a blocker with 409 `project_already_registered`
  (`BE/services/project_service.py:283-303`). A salesperson with only the submit grant goes through `crm_register`
  (`BE/services/project_registration_service.py:744`), which runs NO fuzzy Check; only an exact title + developer repeat
  is caught, by the unique index (`:811-814`, `BE/models/projects.py:334-342`).
- **"Register interest"** posts a takeover request of kind `dispute` with a reason (`ProjectForm.tsx:913`,
  `FE/_shared/services/projectService.ts:398-406`), table `projects.takeover_requests` (`BE/models/projects.py:500-530`).
  Only the dispute kind notifies (`BE/api/v1/projects/projects.py:972-976`): "<name> registered interest in <code>"
  (`BE/services/project_notify_service.py:207-209`; the email subject is the same line). The Access panel lists them
  under "Interested" with Reassign / Dismiss (`FE/[projectId]/components/ProjectAccessPanel.tsx:104,132,141`); the
  Reassign dialog lists those people first and picking one approves their request (`ReassignProjectDialog.tsx:53-62,81-82`).
- **Leads** are deliberately not unique: "a lead is a rumour ... No fuzzy lock, no clash block, no unique title (AC-O3)"
  (`BE/services/project_lead_service.py:3-6`).
- **Stage move**: `POST /projects/{id}/status` -> `change_status` (`BE/services/project_service.py:1380`). Guards today:
  edit right (403), approved (409), graph edge exists (422, `BE/services/status_service.py:169-219`). No per-move
  requirement exists; `conditions_json` is read only by automatic edges (`BE/models/status.py:186`). The stage button is
  `ProjectStatusAction` (`FE/[projectId]/components/ProjectStatusAction.tsx:122-140`) in the page header
  (`ProjectDetailClient.tsx:388-392`).
- **Documents**: one kind, an `attachment_types` row with code `project_document` (`BE/services/project_po_reading.py:85-86`,
  seeded on first use `BE/services/project_schedule_service.py:769-792`); the upload dialog hard-codes it
  (`FE/_shared/services/projectDocumentService.ts:72-90`). A "Requirements" kind is a second row: data, no schema change.

## Rules (my recommended answers in place)

Register wizard (create only)
1. Step 1 **Check**: Project title *, Developer (Q-D), the AI extract button, and **Check**. Nothing else shows. Next
   is not offered; the Check is the only way forward.
2. **No match** -> "No existing project matches this title." Step 2 opens below: Details, then Lead, customer and
   salesperson, then Register (staff) or Save draft / Submit for approval (salesperson). Today's required fields stay.
   The step-2 field list lives in one list in the form, so Monday's required/optional ruling is a one-line change each.
3. **Similar only** (rows, none blocking) -> rows listed as "Similar project" (today's muted style,
   `FE/pipeline/components/ClashWarningPanel.tsx:39-59`); step 2 opens as for no match.
4. **Match** (a blocking row) -> the rest of the form stays closed. The card shows the project (code + title; owner name
   for staff only, `projects.py:131-136`) and ONE button: **Register as secondary lead**. It opens today's dialog
   (reason required) and files today's request. The title stays editable; editing it clears the result and the user
   checks again.
5. **Check failed / timed out** -> inline "The check did not finish. Try again." with the same Check button; step 2
   stays closed (today it fails silently, `ProjectForm.tsx:272`).
6. Title or developer changed after a pass -> the result clears, step 2 keeps what was typed, Register is off until
   Check runs again.
7. AI extract (step 1) fills title and developer, keeps the other extracted fields and drops them into step 2 when it opens.
8. **Edit** has no wizard: all sections open, Check as today (re-check on save only when title or developer changed,
   `ProjectForm.tsx:234-237,388-401`).
9. The server stays the guard: staff Register 409 as today; salesperson submit gets the same Check (Q-E).

Rename (Q1 answered: same request, new words)
10. "Register interest in <code>" -> **"Register as secondary lead on <code>"** (form button + dialog title,
    `ProjectForm.tsx:813,905`; Access panel `ProjectAccessPanel.tsx:97,259,300`). Toasts "Interest registered" ->
    **"Registered as secondary lead"** (`FE/_shared/hooks/useProjects.ts:499`, `ProjectForm.tsx:923`). Access panel
    heading "Interested" -> **"Secondary leads"** (`:104`); past decisions "Interest" -> **"Secondary lead"** (`:209`).
    Notification + email "<name> registered interest in <code>" -> **"<name> registered as secondary lead on <code>"**
    (`project_notify_service.py:207-209`). "Ask to join" (the join kind) is unchanged. No stored value changes
    (`kind` stays `dispute`, the notification type key stays).

Requirements document
11. New document kind **Requirements** (code `project_requirements`), seeded on first use like Project Document. The
    upload dialog gets a Kind select (Project Document default, Requirements); the Documents list shows the kind.
12. Moving **Registered -> Spec In** needs at least one Requirements file on the project (Q-B, Q-C). Without one the
    server refuses: 422 `project_requirements_missing`, "Upload the requirements document before moving this project
    to Spec In."
13. On the page, the stage button checks first: no Requirements file -> it opens a small "Requirements needed" dialog
    with a drop zone (kind preset to Requirements) and **Upload and move to Spec In**. One click finishes both.
14. Existing projects already past Registered are not touched; nothing is backfilled. Moves back, Lost, Dormant and
    PO received are not gated (Q-B).

## Real examples (crew dev DB, aggregates only)

Crew ran `documentation/plans/projects/ps-register-check-first-dev-examples.sql` read-only on the crew dev DB
(29 Oct). Rows stay local; only counts are quoted here. 11 projects: 9 staff-registered, 1 approved portal
registration, 1 pending.

1. **Requirements gate, who it hits**: 5 projects sit in Registered and all 5 have 0 documents of any kind. Under
   Q-B (a) each one asks for a Requirements file on its next Spec In move; nothing else changes for them.
2. **Past Registered, untouched**: 3 in Spec In and 2 in PO Received, also with 0 documents. Rule 14: no backfill,
   no block on their next moves.
3. **No Requirements kind yet**: 22 attachment types exist, `project_document` among them; no requirements row, and
   the code `project_requirements` is free (10 legacy types have no code, so the lookup must go by code).
4. **Secondary leads**: one request in total, a dispute (today's "Register interest") that was rejected; no project
   has two. "Competing secondary leads" therefore does not exist in dev data: the hand test files two (Sales B and
   Sales C on the same project) to show the Access panel list.
5. **Match / similar**: no pair of titles in the same company reaches even 0.4 similarity, so no live project would
   block or show "Similar" today. The hand test registers a near-copy of an existing Registered project's title with
   the same developer to reach the block (>= 0.70) and a looser one for "Similar" (0.55-0.70).

## Edge cases

- Near match only: rule 3. Check fails or times out: rule 5 (POST budget 120 s, `lib/api.ts:118,140`).
- Salesperson (submit grant only) sees code + title of a blocker, never the owner (`projects.py:131-136`).
- Two salespeople register the same building at once: pending registrations are not "approved", so neither blocks
  the other (`project_clash_service.py:245-249`); the approver sees both. Unchanged by this lane (UNVERIFIED whether
  the approve step shows the clash; Q-E covers submit).
- Edit mode: rule 8. Project already past Registered with no requirements: rule 14.
- Automatic stage moves: only the first PO moves a project on its own (`project_po_service.py:209`); a sample
  request or a sent quotation never moves it (the page calls `change_status` first, `ProjectDetailClient.tsx:118-120`).
  The gate sits in `change_status`, so the PO move passes (Q-B). Admin bulk migrate (`BE/api/v1/system/statuses.py:236`)
  is also ungated.
- A Requirements file later deleted: the project stays where it is (the gate is on the move, not a standing state).

## Questions (recommendation first)

**Q-A. Lead names unique by building name?** Today a lead is a rumour anyone can log (`project_lead_service.py:5`);
the project registration is the claim, and its Check already blocks a matching title and offers the secondary lead.
(a) No uniqueness rule on leads; the Check at registration shows matches and offers "Register as secondary lead".
(b) Warn only: creating a lead lists existing leads/projects with the same or similar building name; saving is still
allowed. (c) Block an exact building-name match on leads, warn on near.
Rec **(a)**: it keeps leads as interests (your words) and one guard where ownership locks. (b) is a cheap add-on later.

**Q-B. Which move needs the requirements document?** Edges out of Registered today: Spec In, PO received, Lost,
Dormant, Back to identified (`BE/services/project_seed_service.py:110,115,124,392-410`; #1961 adds none,
`alembic/versions/stg_0001_project_ladder_edges.py:28-41`). (a) Registered -> Spec In only; PO received, Lost, Dormant
and back moves untouched. (b) Both forward moves (Spec In and the manual PO received). (c) Every move out of
Registered. Rec **(a)**: "the state moves one by one", and Spec In is the next rung; a PO is stronger evidence than a
brief. The first-PO automatic move (`BE/services/project_po_service.py:209`, writes the status directly, not via
`change_status`) is never gated under any option.

**Q-C. What counts as the requirements document?** (a) Any file (PDF, photo, screenshot) filed under the new
"Requirements" kind; existing projects past Registered untouched. (b) Any project document of any kind. (c) Only PDF.
Rec **(a)**: the kind is what makes the audit trail findable; a photo of a site brief is common.

**Q-D. What does step 1 ask before the Check?** (a) Title + Developer (optional): the Check is scoped by developer, so
without it a blank developer is compared against every developer (`project_clash_service.py:258,287-305`).
(b) Title only, developer in step 2 (the Check then runs again on Register if the developer changes the result).
Rec **(a)**: one Check that means what it says.

**Q-E. Salesperson submit runs the Check on the server too?** Today it does not (`project_registration_service.py:744`,
exact repeats only). (a) Yes: Submit for approval refuses a blocking match with the same 409 and message staff get;
Save draft stays free. (b) No: the screen's Check is enough; the approver decides. Rec **(a)**: the meeting moved
registration to salespeople, so their path needs the same guard.

Mock: wizard (no match / similar / match collapsed / failed), stage gate dialog: `documentation/mockups/PS-REGISTER-CHECK-FIRST/`.
Schema: none (a new `attachment_types` row, seeded in code). Size stays M.
