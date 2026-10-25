# Behaviour card v4: Project registration from the portal (PROJECT-REG-PORTAL)

Status: SETTLED (owner final 25 Oct 13:03, see PLAN). Building.
Size **L** (one additive migration). v1-v3 in git history (73412ba6, e551fb3f, a9356640).
Mock: `mockups/project-registration-portal-v4.html`. Paths: BE = `sorento_crm_backend/app/`, FE = `sorento_crm_frontend/`.
The WhatsApp chat summary is not in this repo (crew rule); every example is a fake analogue.

## Owner rulings so far

- 12:30: as simple as the legacy desktop Project Registration Form; Sales Agent, PPF No., Date automatic; Developer,
  State, Mukim filled from the title or a photo by AI; checker = Project Sales Admin; free-typed developer allowed, the
  checker resolves it; staff keep registering directly; a registration record of its own; semantic duplicate check.
- 12:45 (mock v3 notes):
  1. "follow the fields in the AutoCount screenshot, don't need additional fields";
  2. "reuse our AI extract component";
  3. "don't complicate the Possible duplicate column, just say which project is possible duplicate";
  4. "again, reuse our project registration format, keep it simple" (CRM review screen);
  5. "reuse our portal design, don't create too many new components".

## Fields: exactly the legacy form, nothing else

Project Title, Distributor Name, Sales Agent, Customer Name, Type of Building, State, Mukim, Status, PPF No., Date,
Your Ref, Developer, Main Contractor, Architect. **No** Daerah, Lot/PT, photo field, note or extra column. Lot/PT and
daerah are read from the title **internally** for the duplicate check only (rule 5).

| Field | Who fills it | Existing portal widget (`FE app/(auth)/portal/components/SubmissionForm.tsx:135-150`) |
|---|---|---|
| Project Title * | salesperson (typed / pasted, or AI Extract) | `textarea` |
| Distributor Name | salesperson, from the agent's debtors | `debtor-async` (as sponsorship form `:317`) |
| Sales Agent | auto: the contact's sales agent | read-only text |
| Customer Name | salesperson | `text` |
| Type of Building | salesperson | `lookup-select` over Project types |
| State * | salesperson or AI Extract | `lookup-select` over the 16 states |
| Mukim | salesperson or AI Extract | `text` |
| Status | auto: Pending / Approved / Rejected | header, as every portal record |
| PPF No. | auto, on Approve (Q2) | header reference, as every portal record |
| Date | auto, submit date | header |
| Your Ref | salesperson, optional | `text` |
| Developer * | salesperson or AI Extract, free text | `text` |
| Main Contractor, Architect | salesperson or AI Extract, free text | `text` |

## Rules

1. **Portal = the existing portal submission form and landing.** Project registration is one more kind in
   `SubmissionForm`'s `FIELDS` map (`SubmissionForm.tsx:193`), drawn with the widgets above, listed in the landing's
   existing kind selector (`PortalLanding.tsx`), granted per contact like the other kinds (`GRANTABLE_PORTAL_FORM_TYPES`,
   `BE/services/portal_service.py:95`). No new portal component. Submitters: contacts linked to an active sales agent
   (`agents_for_contact`, `BE/services/sales/portal_agent.py:24`).
2. **AI = the existing "AI Extract" button** on that form (`SubmissionForm.tsx:2233-2243`), which opens the existing
   `AIExtractDialog` (`FE app/(auth)/portal/components/AIExtractDialog.tsx:91`, applied by `handleAIExtractApply`
   `SubmissionForm.tsx:1318`). The salesperson drops the photo or pastes the title into it, as they do for the other
   kinds. Backend: one new entry `portal.project_registration` in `FORM_SCHEMAS`
   (`BE/services/ai_extract/form_schema_registry.py:400`) naming the legacy fields, with extract notes: "UNTUK (TETUAN)" /
   "FOR MESSRS" introduce the developer; a government department or a person can be the developer; leave State empty when
   the place is in two states (e.g. Cheras). Values are proposed and confirmed in the dialog, as today.
3. **One step.** Submit -> **Pending** (the existing form's Save draft stays available, as on every kind). Project Sales Admin **Approves** or **Rejects** (reason). A rejected
   registration is edited and resubmitted; a pending one can be withdrawn.
4. **CRM review = the existing project registration screen.** Project Sales > Registrations lists pending ones (the
   existing DataGrid listing pattern). Opening one shows the **existing `ProjectForm`** (`FE app/(protected)/project-sales/_shared/components/ProjectForm.tsx`,
   the screen staff register projects with), prefilled from the submission. Header buttons are **Approve / Reject**
   instead of Save. Distributor, Customer, Your Ref, Sales Agent and Date sit as read-only metadata under the header
   (`DESIGN-LANGUAGE.md` rule). Approve = that form's own save, i.e. `register_project()`
   (`BE/services/project_service.py:70-195`): PPF number, stage "Registered", template tasks, and the existing lock's 409
   for a hard duplicate. A typed developer must be picked as a party on that form before Approve, exactly as staff do today.
   Gated by the new permission `projects.registrations.approve`, seeded to the Project Sales Admin role.
5. **Possible duplicate = just the project.** The list column and the review screen say "Possible duplicate:
   PPF2609023 Kilang Alpha Tebrau" (PPF + title, several comma-separated). No scores, no reasons. Underneath, a project is
   named when any of these holds (owner asked for semantic, chat showed the stable key):
   - same lot/PT number + same mukim, read from both titles (deterministic);
   - meaning match of title + developer + state + mukim >= 0.80 (`text-embedding-3-small` on the existing pgvector
     pipeline, `BE/services/embedding_service.py:228`; calibrated in Phase 2);
   - today's spelling match (`find_clashes`, `BE/services/project_clash_service.py:211`, 0.55).

   A title whose phase differs ("FASA 4" vs "FASA 5", `phase_designators` `:96-109`) is not named.

   How today's check works, in plain words: it compares letters only. Titles are lower-cased, then compared by shared
   three-letter chunks. A score of 0.55 or more is "similar"; 0.70 or more, with the same developer and an open project,
   blocks the save. It misses the same job written two ways (short name vs full planning title), which is what the
   other two signals add.
6. **Notifications** (as NPA): Pending -> Project Sales Admin; Approved / Rejected -> the salesperson.
7. **Afterwards**: the portal list shows Status and, once approved, the PPF No.; the project appears in the Sample
   request project picker unchanged (`BE/services/sponsorship_link_service.py:45-85`).

## Examples (fake analogues)

| # | Salesperson | Result |
|---|---|---|
| A | AI Extract on a drawing title-box photo: "CADANGAN MEMBINA KILANG 2 TINGKAT DI ATAS LOT 9001, MUKIM TEBRAU, DAERAH JOHOR BAHRU, JOHOR. UNTUK TETUAN ALPHA PACKAGING SDN BHD" | Dialog proposes the title, Developer "Alpha Packaging Sdn Bhd", State Johor, Mukim Tebrau. Confirm, add Distributor, Submit -> Pending |
| B | Typed "Gamma D'Residence, Cheras" | AI leaves State empty; Submit refused until State is picked |
| C | Same lot 9001 in Mukim Tebrau as approved PPF2609023 | List and review: "Possible duplicate: PPF2609023 Kilang Alpha Tebrau". Admin rejects "Already registered as PPF2609023" |
| D | "TAMAN DELTA FASA 5", same lots as approved "TAMAN DELTA FASA 4" | No duplicate named; Approve -> PPF2610064 |
| E | Rotated folder cover "PEMBAIKAN DAN NAIK TARAF KOMPLEKS JABATAN E, PERLIS" | Title, Developer "Jabatan E", State Perlis; Mukim empty. Submit allowed |

## Data (additive)

`project_registrations` (schema `projects`): the legacy fields as columns (title, distributor_customer_id,
sales_agent_id, customer_name, type_id, state, mukim, your_ref, developer_text, main_contractor_text,
architect_text), status, contact_id, applicant_user_id, project_id (set on Approve), submitted_at, decided_at,
decided_by, reject_reason. `projects.sales_profile` gains **state** and **mukim** (owner: Q2 = State + Mukim only).
Permission `projects.registrations.approve`. Embedding source type `project`.

## Questions left (recommendation first)

1. **Distributor / Customer** (owner unsure). (a) Distributor Name = a pick from the agent's debtors (the existing
   `debtor-async` widget), Customer Name = typed text, no debtor link; (b) both picked from debtors. **Rec (a)**: a
   project has no customer column today and a party becomes a debtor only when it issues a PO
   (`BE/models/projects.py:100-117`); in the team's chat "customer: <dealer>" names the distributor we invoice, while
   the end client is usually not in our books.
2. **PPF No.** (a) Drawn on Approve and used as the project's code: the project numbering rule becomes
   `PPF{yy}{month:02d}` + 3 digits with a monthly reset (a Settings change, no code), staff registrations get one too,
   old PRJ codes stay; (b) drawn on submit as the request's own number, the project keeps a separate PRJ code. **Rec (a)**:
   the admin approves today by replying with the PPF, and the team calls it the project number.
3. **Possible duplicate: warn or block?** (a) Named only; the admin decides (the existing spelling lock still blocks a
   hard duplicate on Approve); (b) a same lot + mukim match also blocks Approve. **Rec (a)**: different phases share
   lots and belong to different salespeople.
4. **"Whose project is this?" in the portal.** (a) No new screen: the existing registered-project picker
   (`project-async` widget, `SubmissionForm.tsx:326-334`) already searches the contact's projects by code/title, so a
   salesperson can check there; (b) a search list showing the holder's sales agent and registration date. **Rec (a)**
   for now, per "don't create too many new components"; (b) is the follow-up if the WhatsApp questions continue.
