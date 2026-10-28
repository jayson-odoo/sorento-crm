# CARD: Register a project v2 (PROJECT-REGISTER-V2), v1.2, 28 Oct

## Owner answers (28 Oct ~14:3x) and what changed in v1.2

- Q1 (a) Register interest; Q2 (a) old owner stays collaborator; Q3 (a) notifications, and the management slug
  is fixed (`MANAGEMENT_PERMISSION` -> `projects.projects.manage`).
- Q4 (a) Customer replaces Lead as the required field, Lead optional in Details, BUT salespeople cannot create
  customers ("that requires AutoCount"): Customer is SEARCH-ONLY over existing customers, no create row.
- Q5 (b) Brands removed EVERYWHERE (see "Brands removal" below).
- Long-title clamp stays in scope.

### Customer (search only)

- Picker: async search on the existing `GET /api/v1/order-management/customers/select?query=&limit=`
  (`BE/api/v1/order_management/customers_select.py:27`, server-side search and paging, built because the client has
  6,397 customers; dev copy 6,850). No "Create customer" row. Stored in `sales_profile.customer_id` (`M:387`).
- Required on Register only. Edit keeps it optional so older projects still save (the same rule Lead has today,
  `ProjectForm.tsx:215-217`). The API enforces it on register (not only the FE).
- AI extract: `customer_name` is matched against existing customers only; no match = blank with the name as a hint.
- Conflict found: the Lead wizard CREATES customers today when the buyer is not on file
  (`select_or_create_customer`, `BE/services/project_lead_service.py:321-360`, rows tagged `source='project_lead'`).
  The register form still reaches that wizard through Lead's "Create lead" row. See question 6.

### Brands removal (Q5 b): code only, no migration

Readers and writers to remove (all verified by grep on origin/main `30a40cf04f`):
- BE: `ProjectRegisterRequest.brand_ids`, `ProjectUpdateRequest.brand_ids`, `ProjectApproveRequest.brand_ids`,
  `ProjectResponse.brands/brand_ids`, `ProjectLeadQualifyRequest.brand_ids` (`BE/schemas/projects.py:223,249,282,374,855`);
  validation + diff + `_set_brands` + `_brands_for` + list filter `brand_ids` (`BE/services/project_service.py:142-148,
  186-193,645-661,802,884-885,1106-1112,1180-1214,1288`); clash candidate `brands` (`project_service.py:1511`,
  `BE/schemas/projects.py:156-187`); list route param `brand_id` (`BE/api/v1/projects/projects.py:224`); lead qualify
  (`project_lead_service.py:1009`); portal approve (`project_registration_service.py:965`).
- FE: form field (`ProjectForm.tsx:30,105,135,247,592-606`), Overview line (`ProjectDetailClient.tsx:457-459`), grid
  column (`ProjectsGrid.tsx:192-206`), board card badges (`PipelineBoard.tsx:312-319`), clash panel badges
  (`ClashWarningPanel.tsx:153-157`), list filter param (`projectService.ts:113`), types (`project.types.ts:181-182,
  253,275,346,565`), edit page description (`[projectId]/edit/page.tsx:11`).
- MCP: the project sanitizer's hidden-field list names `brand_ids` (`sorento_crm_mcp/sorento_crm_mcp/server.py:1402`);
  project tools stop showing brands.
- NOT touched: quotation / pricing "series brands" (`ProjectSeriesBrand`), a different table.
- Migration: none. The table `projects.brands` and its rows (dev copy: 3) stay untouched, so the change is
  reversible. Dropping the table is destructive and would be a separate owner-approved cleanup.

Paths: FE = `sorento_crm_frontend/app/(protected)/project-sales`, BE = `sorento_crm_backend/app`,
M = `BE/models/projects.py`. Dev data = shared dev copy `sorento_cagent_stack`, read-only. Person names in
this card are placeholders (Sales A, Sales B); developer firms are as stored.

## Screen today

`/project-sales/new` (`FE/new/page.tsx:14-31`, needs `projects.projects.edit`) renders `ProjectForm`
(`FE/_shared/components/ProjectForm.tsx:72`, same form for edit). Who and what `:296-427` (Developer, Project type,
Title + Check, clash panel, Template); Details `:429-607`, closed on create (Registered company, Location, State,
Mukim, Address, Reference, Value, Launch, Delivery, Architect, Main contractor, Brands); Salesperson and lead
`:609-654`.

## Item 5: the "brand" field

It is **Brands** (multi-select, `ProjectForm.tsx:592-606`): the Sorento brands being pushed into this project,
stored in `projects.brands` (M2M onto core `brands`, `M:413-437`, written by `_set_brands`
`BE/services/project_service.py:1180`). Who reads it: the Overview "Brands" line (`ProjectDetailClient.tsx:457`),
the clash panel shows the incumbent's brands (`ClashWarningPanel.tsx:153`, ADR-0004), and the project list's brand
filter (`project_service.py:1105-1112`). Quotations and pricing do NOT use it (they use series brands,
`ProjectSeriesBrand`). Dev copy: 3 rows, all on one of 4 projects (PRJ-000003: OTHERS, INFINITY, BRAVAT).
It is a sales-plan detail, not part of what identifies the project, and is rarely known at registration.

## Item 6: Lead vs Customer

- **Lead** = a `projects.leads` row (`M:708`): a pre-project opportunity (title, source, informant, value, owner),
  NOT a person and NOT a contact. It carries an optional buyer `customer_id` (`M:742`). Required on the form only
  in the FE (`ProjectForm.tsx:217-218`); the API takes it as optional (`BE/schemas/projects.py:192-221`). Create
  opens a 4-step wizard (`FE/leads/components/LeadWizardDialog.tsx:44-63`). Dev copy: 1 lead, linked to 1 of 4
  projects.
- **Customer** = core `customers` (`BE/models/order.py:76`), the AutoCount debtor = the dealer (business chain
  salesman -> dealer -> end user; ADR-0007; owner 11 Oct: a customer is a contact with a linked customer).
  The project already has a customer slot, `sales_profile.customer_id` (`M:387`), which the portal fills with a
  debtor pick (PR #1849).
- So the owner is right: the person the salesperson sells the project through is the Customer. Lead is the
  pipeline record a project may come FROM.

## Item 2: AI extract (reuse)

Engine: `AIExtractService.extract` (`BE/services/ai_extract/extract_service.py:284`), sync, one LLM call, takes
text (as a `.txt` file, `:797-803`) and/or photos/PDF (`:458`). Schema already registered for project registration:
`portal.project_registration` (`BE/services/ai_extract/form_schema_registry.py:403-475`). Portal dialog
`app/(auth)/portal/components/AIExtractDialog.tsx` (clipboard text and photos). Provider = the AI assistant config
(`extract_service.py:400-440`), not `DOCUMENT_AI_PROVIDER` (that one is the page-by-page PO reader,
`document_extraction.py:286`, no text input, runner-up only). Staff side has no route: add
`POST /api/v1/project-sales/projects/ai-extract` (`projects.projects.edit`, per-user rate limit as the portal's).

Field mapping (only proposes; the user ticks Apply, nothing is saved until Register):

| Extracted | Form field | Rule |
|---|---|---|
| title | Project title | filled only when the box is empty (photo-only extract); typed text never overwritten |
| developer_name | Developer | exact case-insensitive name match among developer parties; else offer "Create developer '<name>'" |
| architect_name / main_contractor_name | Architect / Main contractor | same; else "Create architect / main contractor '<name>'" |
| type_of_building | Project type | name match against project types; else blank |
| state, mukim | State, Mukim | State via the same `my_state` lookup; unresolved = blank |
| customer_name | Customer (if Q4 a) | customer resolver match; else blank with the name shown as a hint |
| distributor_name, your_ref | not on this form | dropped |

## Item 4: Architect / Main contractor created on the spot

Today both are plain dropdowns loading the first 200 parties (`ProjectForm.tsx:130-132`), while the dev copy holds
1,561 architects, 210 developers, 25 main contractors: 1,361 architects cannot be picked at all. Change: async
search (like Lead) plus "Create architect '<text>'" calling the existing `POST /project-sales/parties/`
(`BE/api/v1/projects/parties.py:58`, needs `projects.parties.edit`; the create row hides without it). One click
creates (name + type only), no wizard. Same for Developer (also capped at 200).

## Item 3: duplicate, register interest, reassign

- Duplicate basis (unchanged, `BE/services/project_clash_service.py:84-307`): same company, approved projects,
  title lower-cased, best of three pg_trgm scores, shown at >= 0.55, a match at >= 0.70 (or one title containing
  the other, 6+ chars) blocks when the developer is the same or blank and the project is still open and not a
  different phase. Today a block disables Register (`ProjectForm.tsx:210-211,662`) and the API returns 409
  (`project_service.py:296-309`); the way out is "Ask to join" / "Dispute".
- Much of the rest exists already: `projects.takeover_requests` (`M:500`, kind join | dispute, reason, status,
  decided_by/at), `projects.collaborators` (`M:482`), a manager-only Reassign (`PUT` owner, `project_service.py:1272`,
  403 otherwise), and the dispute decision that moves the owner and keeps the old owner as collaborator
  (`project_service.py:549-614`). Dev copy: 0 requests, 0 collaborators.
- Proposal: "Register interest" IS the existing dispute request, relabelled (no new table, no migration: `kind` has
  no DB check, verified). Note required: "How and when did you find this project?" (reason is already NOT NULL).
  "Ask to join" stays.
- On the form: when the Check finds a blocking match, the main button becomes **Register interest in PRJ-x**.
- On the project (Overview, Access card `ProjectAccessPanel.tsx`, `ProjectDetailClient.tsx:470`): an **Interested**
  list (name, date, note) visible to everyone who can see the project. Managers (`projects.projects.manage`,
  `BE/rbac/permission_registry.py:588`) get **Reassign to <name>** per row and **Dismiss**; the Reassign dialog
  lists interested people first. Audited by the audit listeners plus an activity-feed line "Reassigned from A to B".
- Users who only hold `view_own` must see a project they registered interest in: add pending requesters to
  `project_clause` (`BE/services/own_scope.py:75-92`).

## Owner addition: very long titles

The detail header prints the whole title as `text-xl` (`FE/[projectId]/components/ProjectDetailClient.tsx:271`), in
every status. Other unclamped sites: "Already registered as" link (`:371`), possible-duplicate links (`:565`),
crumbs in `DeliveryScheduleReviewClient.tsx:397` and `POIntakeConfirmClient.tsx:178`, quotation document heading
(`QuotationDocumentClient.tsx:304`, defaults to the project title), lead heading (`LeadDetailClient.tsx:246`),
7 child-page title lines (order inquiry, PO intake, sales order, schedules, divergence, sample request, complaint),
project pickers (`SearchableSelect` wraps labels; PO intake, schedules, complaints, sample requests, purchase
requests). Already clamped: board card (`PipelineBoard.tsx:284`), list column (`ProjectsGrid.tsx:117-122`), clash
panel. ONE pattern: reuse `components/common/TruncatedTextCell.tsx` (truncate + hover title + an eye button that
opens the full text; its docstring already names "project title"; zero users today), with a `lines` option: 2 lines
in headings, 1 line elsewhere; pickers set the existing `truncateTriggerLabel`.

## Real examples (dev copy)

1. PRJ-000002 "100 UNITS DSTH & 8 UNITS DS SEMI-S AT NUSA UTAMA", S P SETIA BERHAD, owner Sales A. Sales B types
   "100 units DSTH Nusa Utama" with developer S P Setia: today blocked; v2 offers "Register interest in PRJ-000002".
2. PRJ-000001 "Setia Alam", no developer: a blank developer compares against every developer (ADR-0004).
3. PRJ-000003 "Project Title:-Restroom Refurbishment For sekolah memangah": text pasted from a form, the AI extract
   case; also the only project with Brands.
4. PRJ-000004 "TRX Zus Coffee" -> LEAD-000001, whose buyer customer is set: the customer is only reachable via the
   lead today.
5. Architect "create on the spot": 1,561 architects exist, 0 linked to a customer; a new name is the common case.

## Finding outside the ask (not fixed unless you say so)

Project "management" alerts go to holders of `projects.projects.view_all_financials`
(`BE/services/project_notify_service.py:33-64`); that slug is not in the permission registry and not in the dev
copy's permissions table, so floor-breach / staleness / PO-mismatch alerts reach no manager there (prod UNVERIFIED).

## Questions (recommendation first)

1. Duplicate: (a) a blocking match turns Register into "Register interest in PRJ-x", no second project; naming a
   different developer still clears the match; (b) also offer "Register as a new project anyway". Rec (a): one
   development stays one project (ADR-0004) and nobody is dead-ended.
2. Reassign to an interested person: (a) old owner stays as collaborator (what the dispute decision does today),
   other interested people stay listed; (b) old owner loses access. Rec (a).
3. Notifications: (a) new interest -> owner + managers; reassign -> new and old owner; managers =
   `projects.projects.manage` (and point the existing alerts at it too, fixing the finding above); (b) none. Rec (a).
4. Lead -> Customer: (a) Customer (dealer: debtor search + "Create customer" as a prospect via the existing
   `select_or_create_customer`, `project_lead_service.py:321`) replaces Lead as the required field; Lead becomes
   optional in Details; (b) both optional; (c) keep Lead. Rec (a).
5. Brands: (a) off the Register form, kept on Edit + Overview, label "Brands we are pushing"; (b) remove everywhere
   (loses the list filter and clash context); (c) keep. Rec (a).

Answered 28 Oct: 1 (a), 2 (a), 3 (a), 4 (a) with search-only Customer, 5 (b).

6. (new in v1.2) The Lead wizard creates customers (see "Customer (search only)"): (a) in this lane its buyer step
   becomes search-only too, so no screen a salesperson uses creates a customer; (b) a separate lane; (c) leave it.
   Rec (a): the register form reaches the wizard through "Create lead", so leaving it open keeps a back door.

No migration expected. Security review covers the reassign and interest rules.
