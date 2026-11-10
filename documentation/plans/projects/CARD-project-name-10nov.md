# CARD: PROJECT-NAME v1 (10 Nov 2026)

Status: waiting on the owner (5 questions below, each with a recommendation). Track: normal (additive migration).
Plan: `PLAN-project-name-10nov.md`. Mock: `mockups/project-name-10nov.html` (v1).

Owner ruling 10 Nov ~13:30 MYT: "we need like a project name field so it doesn't bloat the title ... the header put a
project name which can be extracted by the AI extract and also hand filled in the 2nd page, I want to keep the first
page lean which only contains project title and the developer in Project registration".

Paths: BE = `sorento_crm_backend/app`, FE = `sorento_crm_frontend/app/(protected)/project-sales`. Code read on
origin/main a4af6565.

## Facts (today)

- A project has `project_code`, `title` (Text) and `normalised_title`; no short name anywhere
  (`BE/models/projects.py:314-317`). `ProjectSalesProfile` holds no name either (`:417`).
- Header: code + one status pill, then `<h2>` = the title clamped to 2 lines, full on click
  (`FE/[projectId]/components/ProjectDetailClient.tsx:298-335`).
- Overview "The development" card: Developer, Registered company / SPV, Location, Address, State, Area, Project type,
  To-do list template, Reference. No title (`ProjectDetailClient.tsx:534-544`).
- Register wizard, create mode: step 1 "Check" is ALREADY title * + Developer + the AI extract button + the clash
  result (`FE/_shared/components/ProjectForm.tsx:640-689`); step 2 "Details" opens with "Who and what" (type +
  template), then Details, Parties and contacts, Lead source / customer / salesperson (`:693-1140`). Edit mode is one
  page; title is the first field of "Who and what" (`:700-726`). So page 1 is lean already: this lane adds nothing to
  it.
- AI extract: `POST /project-sales/projects/ai-extract` (`BE/api/v1/projects/projects.py:165-235`) runs the shared
  schema `portal.project_registration` (`BE/services/ai_extract/form_schema_registry.py:403-475`) and turns the values
  into proposals (`BE/services/project_ai_extract_service.py:124-137`). The FE review lists Developer, Architect, Main
  contractor, Project type, State, Area, Project title (`FE/_shared/components/ProjectAIExtractDialog.tsx:26-34`); the
  fill never overwrites a typed title (`ProjectForm.tsx:441-443`). The endpoint already takes photos (`files`).
- The same schema serves the dealer portal's extract. The portal form only reads values for its own fields
  (`FE/../(auth)/portal/components/SubmissionForm.tsx:583-588`), so a new extract value it has no field for is dropped.
- Duplicate check (registration lock): unique on company + developer + `normalised_title`
  (`BE/models/projects.py:400-408`), fuzzy preview in `BE/services/project_clash_service.py:213-307`. Leads are not
  unique (29 Oct Q-A answered (a), `CARD-ps-register-check-first-29oct.md:138-143`).
- Search: the projects list (and the pickers that call it) matches title + code only
  (`BE/services/project_service.py:1139-1145`).

## Where the title shows today, and what changes (rule 6, Q1)

| Place | file:line | Today | Proposed |
|---|---|---|---|
| Project header | `FE/[projectId]/components/ProjectDetailClient.tsx:334-335` | title, 2 lines | **name** (fallback title, clamped) |
| "The development" card | `ProjectDetailClient.tsx:534` | no title | **full title, first fact, 2 columns wide, clamped 3 lines, full on demand** |
| Projects grid "Project" column | `FE/_shared/components/ProjectsGrid.tsx:115-125` | title | **name**, `title` tooltip; search placeholder "Search name, title or code" (`:234`) |
| Pipeline board row + kanban card | `FE/pipeline/components/PipelineBoard.tsx:124-125, 287-288` | title | **name** (fallback title) |
| Pickers: editable projects | `FE/_shared/services/projectService.ts:165` | label title | **label name**, description code + developer |
| Pickers: link a project (complaint, PR, sample request) | `FE/../complaint-management/complaints/services/complaintService.ts:506` | "code - title" | **"code - name"** |
| In-project page headers (SO, PO intake, delivery schedule, OI) | `SalesOrderDetailClient.tsx:352-360`, `POIntakeConfirmClient.tsx:182,243-247`, `DeliveryScheduleReviewClient.tsx:406,745-751`, `OrderInquiryClient.tsx:448-450` | "title (code)" | **"name (code)"** |
| Clash / duplicate / already-registered links | `ProjectForm.tsx:1325`, `ClashWarningPanel.tsx:98-99`, `ProjectDetailClient.tsx:480,696` | code + title | **code + name, title under it clamped**: the Check compares titles, so the title must stay visible |
| Lead page project tables | `FE/leads/[leadId]/components/LeadDetailClient.tsx:610-614,730-734` | title | **name** |
| My tasks row | `FE/my-tasks/components/MyTasksClient.tsx:116-119` | project_title | **name** (BE adds `project_name` beside `project_title`, `BE/services/project_task_service.py:820`) |
| Notifications (owner change, secondary lead, pricing, stale, registration decisions) | `BE/services/project_notify_service.py:210,241,292`, `project_staleness_service.py:320-333`, `project_registration_service.py:883-899` | title | **name** (fallback title) |
| Assistant / MCP | `BE/services/project_service.py:838` (payload), `entity_resolver.py:4989-5024`, `sorento_crm_mcp/catalog.py:1664-1740` | title | **add `name`** to the payload, resolver matches name too, catalog text says so; title stays |
| Quotation subject + cover, PDF/Excel | `BE/services/project_quotation_document_service.py:265,2279`, `quotation_cover_service.py:133-138` | title | **unchanged: full title** (a legal document names the development in full) |
| AutoCount SO draft `our_ref_no` | `BE/services/project_so_draft_service.py:3081` | title | **unchanged** |
| Spec sheet, PR free-text `project_title`, sample request PDF, complaint link text | `project_spec_sheet_service.py:700`, `PurchaseRequestForm.tsx:128`, `sample_request_pdf_service.py:73`, `complaints_service.py:346` | title | **unchanged** |
| SCM / OI worklist / fulfilment / allocations columns (~25 files, raw SQL `pj.title`) | e.g. `order_inquiry_worklist_service.py:730,1524`, `scm/demand.py:1063`, `project_allocation_service.py:242-270` | title | **unchanged this lane** (Q1). The OI Project filter matches exact title text (`:1524`), so a swap there is its own change |

## Rules (as proposed)

1. New column `projects.projects.name` `VARCHAR(80)`, nullable, additive. Not unique, not part of the lock.
2. Register page 1 (Check) stays exactly as today: Project title * (textarea, first field) + Developer + AI extract +
   Check. Nothing added.
3. Register page 2: "Who and what" opens with **Project name** (input, optional, max 80, counter at 70+), then type
   and template. The section summary shows the name, else the title.
4. AI extract (the existing button on page 1; it takes text and photos) gains a **Project name** row. On confirm the
   name lands in the page 2 field; a typed name is never overwritten (same rule as the title). The extract also
   proposes nothing for the name when it cannot find one. No new extractor: one more field on the existing schema.
5. Edit page: "Who and what" = Project title * (first), then Project name, then developer / type as today.
6. Header shows the name. Overview "The development" shows the full title first. Elsewhere per the table.
7. Fallback, everywhere a name is shown: `name || title`, the title clamped as today.
8. Search: projects list + pickers match name, title and code. The assistant resolver matches name too.
9. Audit: the column is on the audited table, so a rename is in History like a retitle.
10. Dates on any new text: dd/mm/yyyy (none expected).

## Examples

PPF2611003, from the owner's screenshot (developer invented):

| | value |
|---|---|
| Title (unchanged) | CADANGAN MEMBINA 54 UNIT RUMAH TERES DUA TINGKAT DI ATAS LOT 161268, 161269 & 161270, JALAN PERMATANG BADAK PERDANA, MUKIM KUALA KUANTAN, DAERAH KUANTAN, PAHANG DARUL MAKMUR. - PLOT 1: 18 UNIT RUMAH... |
| AI name proposal | 54 Teres 2 Tingkat, Permatang Badak Perdana |
| Header | PPF2611003 · Registered / **54 Teres 2 Tingkat, Permatang Badak Perdana** |

The extract's instruction for the name (draft): "A short name people use for the development, at most 60
characters. Use the scheme, taman, residensi or building name when the title names one (e.g. 'Residensi Contoh
Phase 2'); otherwise '<units> <building type>, <road or place>'. Never lot numbers, mukim, daerah or state. Keep a
phase or plot designator (Phase 3B, Plot 1) when the title has one." Real dev examples (3-5 titles with the AI's
proposal) follow once the `crew-data-request` on the PR is answered.

## Edge cases

- Name blank (every existing project until a backfill, a draft, a portal registration): title shown, clamped.
- Name longer than 80: refused by the schema (422), the input stops at 80.
- Name typed, then AI extract run: the typed name stays.
- Two phases share a name ("Setia Alam" Phase 3A and 3B): allowed; the code tells them apart in every picker.
- Retitle without renaming: the clash check reruns on the title as today; the name is untouched.
- Portal registration approved: name blank; the approver can type it on the edit page.
- 375px: the header name wraps (no clamp needed at 80 chars); the title in the card clamps to 3 lines.

## Questions (recommendation first)

**Q1. Where does the name replace the title?** (a) The screens that identify a project (table above: header, grid,
pipeline, pickers, in-project headers, lead/task rows, notifications, assistant), documents and copies keep the full
title, SCM / OI / fulfilment columns stay on the title this lane. (b) (a) plus every SCM / OI / fulfilment column.
(c) The project header only. Rec **(a)**: it fixes every place a person picks or recognises a project, keeps legal
paper full, and leaves the ~25 SCM files (with an exact-title filter) for a lane of their own if wanted.

**Q2. Existing projects with no name?** (a) One-off AI backfill: a script runs the same extract on each title and
posts a dry-run list (code, title, proposed name) for you; it writes only after you approve; until then the title
shows, clamped. (b) Leave blank; names arrive as people edit. Rec **(a)**: otherwise the header fix waits months.

**Q3. Is the name required?** (a) Optional; the AI fills it and the title stands in when blank. (b) Required to
register (drafts and portal approvals exempt). Rec **(a)**: page 2 already has one required field (lead source), and
the fallback makes a blank name harmless.

**Q4. Does the duplicate check use the name?** (a) No: the lock and the Check stay on title + developer; the name is
not unique. (b) The Check also lists a project with the same name as a near match. Rec **(a)**: the name is typed
on page 2, after the Check has run, and two phases legitimately share one.

**Q5. Leads and the dealer portal?** (a) Staff projects only this lane: the portal form gets no name field (its
extract drops the value), the approver types it on approval, leads keep their title. (b) Add a name to leads and to
the portal form as well. Rec **(a)**: the ruling was about the project header and the register page; a lead
qualifying into a project can carry its title across as today.
