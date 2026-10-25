# Behaviour card v2: Project registration from the portal (PROJECT-REG-PORTAL)

Status: card v2 + mock v2 filed (25 Oct 2026), after the owner's answers on v1 (12:30). Nothing built. Size **L**
(one additive migration). v1 is in git history (commit 73412ba6).
Mock: `mockups/project-registration-portal-v2.html` (every element names its component + path).
Paths: BE = `sorento_crm_backend/app/`, FE = `sorento_crm_frontend/`.

## Owner rulings folded in (25 Oct 12:30)

- As simple as the legacy desktop **Project Registration Form**: Project Title, Distributor Name, Sales Agent, Customer
  Name, Type of Building, State, Mukim, Status (Pending), PPF No., Date, Your Ref, Developer, Main Contractor, Architect;
  Approve / Reject.
- Salesperson types the title. Sales Agent, PPF No., Date are automatic. Developer, State, Mukim are filled from the
  title or by AI from an attached photo, editable after.
- Checker = **Project Sales Admin** (a named grant, not every `projects.projects.manage` holder).
- Q2 (a) free-typed developer allowed, checker resolves it before Approve. Q4 (a) staff keep registering directly.
  Q5 (a) a registration record of its own.
- Duplicate check must be **semantic**, shown to the checker and as a hint in the portal.

## The form (legacy field -> where it comes from -> where it lands)

| Legacy field | Filled by | Stored on the registration | On Approve, lands in |
|---|---|---|---|
| PPF No. | auto, on submit | `ppf_no` | shown on the project as "Registered from PPF2610001" |
| Date | auto (submit date) | `submitted_at` | - |
| Status | auto: Pending / Approved / Rejected | `status` | - |
| Project Title * | salesperson types (long free text, e.g. "CADANGAN PEMBANGUNAN 2 BLOK PANGSAPURI SERVIS ... DI LOT 1234, MUKIM BATU, KUALA LUMPUR") | `title` | `projects.title` (Project column) |
| Sales Agent | auto: the portal contact's sales agent | `sales_agent_id` | owner = the CRM user of that contact (Owner column), see rule 6 |
| Developer * | AI fill or typed; picked from developer parties or free text (Q2 a) | `developer_party_id` or `developer_text` | `projects.developer_party_id` (Developer column); checker must resolve free text to a party |
| Main Contractor | AI fill or typed / picked | `main_contractor_party_id` or `_text` | `sales_profile.main_contractor_party_id` |
| Architect | AI fill or typed / picked | `architect_party_id` or `_text` | `sales_profile.architect_party_id` |
| State * | AI fill or picked from the 16 states/territories (`MY_STATES`, FE `app/(protected)/order-management/customers/forms/client-form-constants.ts:1`) | `state` | Q2 |
| Mukim | AI fill or typed | `mukim` | Q2 |
| Type of Building | picked from Project types (`projects.types`, `BE/models/projects.py:134-165`) | `type_id` | `projects.type_id` |
| Distributor Name | picked from the agent's debtors (Q1) | `distributor_customer_id` | Q2 |
| Customer Name | typed (Q1) | `customer_name` | Q2 |
| Your Ref | typed, optional | `your_ref` | Q2 |
| Photo (new, optional) | salesperson attaches site / signboard / tender photos | portal attachments | copied to the project's files |

Required on submit: title, developer (picked or typed), state. Everything else optional, same reasoning as
`ProjectRegisterRequest` (`BE/schemas/projects.py:192-198`).

## Rules

1. **One step, like the legacy form.** Salesperson submits -> **Pending** (locked). Checker **Approves** or **Rejects**
   (reason required). A rejected registration can be edited and resubmitted (Pending again, same PPF No.); the salesperson
   may withdraw a Pending one. No Draft, no separate Revise: that is the whole legacy flow. (NPA's Draft + Revise,
   `BE/services/new_product_application_service.py:349-440`, is more than this form needs.)
2. **PPF No.** No PPF number exists in the CRM code (grep, 25 Oct); dev and AutoCount data asked via crew-data-request.
   Proposed format PPF + yy + mm + 3-digit sequence resetting monthly: `PPF2605065` = May 2026, number 65. Built with the
   existing `NumberingService` (`BE/services/numbering_service.py:64-86`, monthly reset + `{yy}` already supported)
   with a seeded rule `prefix_template = "PPF{yy}{month:02d}"`, `number_digits = 3`, `reset_policy = monthly`, editable
   in Settings > Numbering. No code change to the numbering service. Drawn on submit, so a withdrawn or rejected one
   keeps its number (as the paper did). If the data shows the legacy sequence never resets, the rule is set to
   `never` with the next value continuing from the highest legacy number.
3. **AI fill (one mechanism for text and photo).** A "Fill from title / photo" action sends the typed title and any
   attached photos to the existing **`AIExtractService`** (`BE/services/ai_extract/extract_service.py:180`, `extract()`
   `:284`) with a new form key `portal.project_registration` in `FORM_SCHEMAS`
   (`BE/services/ai_extract/form_schema_registry.py:400`) listing: developer, main_contractor, architect, state, mukim,
   district, lot_no, short_name. The title travels as a `text/plain` part, which the service already accepts
   (`extract_service.py:77-79`). It is the same synchronous `POST /public/portal/ai-extract` the portal already calls
   (`BE/api/v1/public/ai_extract.py:99-150`), and `AttachmentDropzone`'s `onExtract` already feeds `AIExtractDialog`
   (FE `app/(auth)/portal/components/AttachmentDropzone.tsx:82,97`). Provider: the configured AI assistant provider
   (`_resolve_provider` `:400-440`; Gemini or OpenAI). The result only proposes values: every field stays editable,
   and nothing overwrites a value the salesperson already typed. A Malaysian signboard / planning notice prints exactly
   these fields (Pemaju, Kontraktor Utama, Arkitek, Lot, Mukim, Daerah, Negeri), which is why the legacy form has them.
   Developer / contractor / architect text is then matched to existing parties and offered as a pick ("Did you mean
   <party>?"), never auto-chosen.
4. **Duplicate check, semantic (see "How duplicate checking works" below).** Runs on the portal (hint) and on the
   checker's screen (panel). The checker sees every candidate with the reason it was surfaced.
5. **Checker = Project Sales Admin.** New permission `projects.registrations.approve`, granted by the migration to the
   role named Project Sales Admin (role existence asked via crew-data-request; if it does not exist the migration grants
   admin roles and the owner assigns it in Roles). The menu item Project Sales > Registrations needs it. The applicant
   can never approve their own registration.
6. **Approve** calls the existing `register_project()` (`BE/services/project_service.py:70-195`), so the project gets
   its PRJ code, first stage "Registered" (`BE/services/project_seed_service.py:53`) and template tasks exactly like a
   staff registration, and the trigram lock still refuses a hard duplicate with the existing 409. Before Approve the
   checker must: resolve a typed developer to a party (pick or create under Parties), and confirm the owner. Owner =
   the CRM user whose `respond_contact_id` is the contact (`_linked_user_id`, `BE/api/v1/public/portal_sample_request.py:50-52`); if the sales
   agent has no CRM user, the checker picks the owner (Salesperson select).
7. **Who can submit**: portal contacts granted the new kind `project_registration` (opt-in in
   `GRANTABLE_PORTAL_FORM_TYPES`, `BE/services/portal_service.py:95`) AND linked to at least one active sales agent
   (`agents_for_contact`, `BE/services/sales/portal_agent.py:24-33`). A contact linked to several agents picks which one (the
   PORTAL-MULTI-AGENT rule); one agent = no field.
8. **Notifications** (NPA pattern, in-app + email): Pending -> `projects.registrations.approve` holders; Approved
   ("PPF2610001 approved as PRJ-0151") and Rejected (with reason) -> the CRM user of the contact.
9. **Afterwards the salesperson sees** the portal landing kind "Project registration": PPF No., title, developer,
   status pill, the project code once approved, the reason once rejected. The approved project appears in the Sample
   request project picker with no change (`BE/services/sponsorship_link_service.py:45-85`), so
   `sample_request_require_project` works for portal salespeople.

## How duplicate checking works today (plain words)

`find_clashes` (`BE/services/project_clash_service.py:211`) compares **spelling only**:
1. The title is lower-cased and spaces collapsed (`normalise_project_title`, `:84-93`). Nothing else.
2. Each existing project title in the same company gets the best of three letter-triplet (trigram) scores
   (`_score_expression`, `:156-183`): how alike the two strings are overall, and how much of one is covered by the other,
   both ways. 1.0 = same letters.
3. A title fully inside the other ("kepong metropo" inside "kepong metropolitan serviced apartments") also counts
   (`titles_overlap`, `:188-208`).
4. Score >= **0.55** = shown as "similar"; >= **0.70** AND same developer AND the project is still open = **blocks**
   (`:45-46`, editable in System Settings, `:134-153`). Different phase numbers ("Phase 3A" vs "3B") never block
   (`are_sibling_developments`, `:112`). Calibrated on the 63 live titles (`:23-41`).

What it misses: it knows letters, not meaning. "Setia Alam Ph 3B" vs "Setia Alam Phase 3B" works (0.76), but the
long legal title "CADANGAN PEMBANGUNAN 2 BLOK PANGSAPURI SERVIS 38 TINGKAT DI LOT 1234, MUKIM BATU" against the
marketing name of the same job scores near zero, because they share almost no letters. That is the case the
portal will produce most, since salespeople copy the signboard.

## Proposed semantic check (added alongside, the spelling lock stays as is)

- **What is compared**: one line per project: `title | developer | state, mukim`, using the CRM's existing embedding
  model `text-embedding-3-small` (1536 dims, `BE/config.py:289-299`) and pgvector store (`embedding_chunks`, HNSW
  cosine index, `alembic/versions/142_pgvector_embedding_pipeline.py:117-118`). Projects are not embedded today; this
  adds source type `project` to the existing event-driven worker (`BE/services/embedding_worker.py:94` canonical text,
  listener in `embedding_change_listener.py:186-208`), so every project, old and new, is kept current off the request
  path. The registration's own line is embedded at check time with the existing synchronous call
  (`embedding_worker._embed_text_chunks`, `:616`, as `entity_resolver` already does in-request, `:5269-5280`) and
  searched with `EmbeddingReadService.search_current(source_type="project")` (`BE/services/embedding_service.py:228`).
- **Two plain signals beside the vector**: same **lot number** (extracted, rule 3) under the same mukim = almost
  certainly the same job; same developer + same mukim = worth a look.
- **Thresholds (proposed, calibrated before ship)**: cosine >= **0.80** = "possibly the same project" (the CRM's own
  bar for a confident semantic match, `entity_resolver.py:2932`); same lot + mukim = "very likely the same" regardless
  of score. Phase 2 calibrates 0.80 on the live project titles (crew-data-request), the way the trigram bars were.
- **What it does**: shows, never blocks (Q3). The checker sees each candidate with why: "same lot 1234, Mukim Batu",
  "meaning match 0.86", "spelling match 0.76". The portal hint shows code + short title only, no holder.
- **Cost**: one embedding call per check (a fraction of a sen); no new infrastructure.

## Customer vs distributor vs lead (owner: "our reference is lead, their reference is customer")

How the CRM relates them today:
- A **project** has no customer column (`BE/models/projects.py:225-306`). The buyer appears only later: the quotation
  is addressed to a party (`recipient_party_id`, `:1060`), the PO is issued by a party (`issuing_party_id`, `:1632`), and
  a party is bridged to a debtor (`customers`) **only once it actually issues a PO** (`:100-102`, `:117`). Architects and
  developers never buy, so they are parties, not customers.
- A **lead**'s buyer is optional (`:684-696`): "most real leads arrive long before anyone knows who the buyer will be,
  and requiring one meant inventing a customer row". The lead is our record of the sighting; the debtor link is theirs.
- The portal's other salesperson forms pick a customer only from the agent's own debtors
  (`BE/services/sample_request_service.py:258-289`), never creating one.

So the recommendation (Q1): **Distributor Name = a pick from the salesperson's own debtors** (our ledger, the party we
invoice), optional; **Customer Name = typed text** (their customer, often a contractor not in our books), never linked to
`customers` and never creating a debtor. The registration itself is "our reference" (it plays the lead's role); no Lead
row is created.

## Examples

Pending: crew's masked summary of the team's WhatsApp registration chat. The two shapes already evidenced in the repo:
- Long legal title, from a sales order project field: "CADANGAN PEMBANGUNAN 2 BLOK PANGSAPURI SERVIS 38 TINGKAT DI LOT
  1234, MUKIM BATU, KUALA LUMPUR" (`documentation/plans/scm/evidence/oi-email-print/render_real.py:99`, masked) -> AI fill:
  state Kuala Lumpur (W.P.), mukim Batu, lot 1234; developer empty (not in the title) -> salesperson types or attaches the
  signboard photo.
- Short marketing title near an existing one: "Setia Alam Ph 3B" vs registered "Setia Alam Phase 3B" (spelling 0.76,
  `project_clash_service.py:31`) -> panel "spelling match 0.76", Approve refused by the existing lock if same developer.

## Edge cases

- Two salespeople register the same job while both Pending: both reach the queue; after the first is approved the
  second shows the first's project as a candidate (and, if spelling + developer match, Approve is refused by the lock).
- AI returns nothing or the provider is down: the form says "Couldn't read it, fill the fields yourself" and stays
  usable (AIExtractService already returns per-field empties).
- Photo is not a signboard (a selfie, a floor plan): fields come back empty; nothing is overwritten.
- Numbering rule missing: submit refuses with "No numbering rule for project registrations" (same shape as
  `project_numbering_rule_missing`).
- No UUIDs shown; parties, agents and debtors render by name / code.

## Data (additive migration, schema `projects`)

`project_registrations`: id, company_id, ppf_no (unique per company), status (CHECK pending|approved|rejected|withdrawn),
contact_id, sales_agent_id, applicant_user_id NULL, title, developer_party_id NULL, developer_text NULL,
main_contractor_party_id / _text, architect_party_id / _text, state, mukim, district NULL, lot_no NULL, type_id NULL,
distributor_customer_id NULL, customer_name NULL, your_ref NULL, project_id NULL (set on approve), submitted_at,
decided_at, decided_by, reject_reason, timestamps. Seed: numbering rule `project_registration`, permission
`projects.registrations.approve`. Embedding source type `project` (no schema change: `embedding_documents` is generic).
Plus Q2's columns if (a).

## Questions (recommendation first)

1. **Customer.** (a) Distributor Name = pick from the agent's debtors (optional), Customer Name = typed text, no
   debtor link, no Lead row; (b) Customer Name also picked from debtors; (c) create a Lead alongside. **Rec (a)**:
   matches how the CRM treats buyers today (party first, debtor only on PO, `models/projects.py:100-117`), and a
   contractor not yet in our books never forces a fake debtor.
2. **Where State / Mukim / Distributor / Customer / Your Ref live after approval.** (a) State + Mukim become columns on
   the project (`projects.sales_profile`, additive), so Pipeline can filter by state; Distributor, Customer and Your Ref
   stay on the registration, shown read-only on the project ("Registered from PPF2610001"); (b) all five stay on the
   registration only; (c) all five copied to the project. **Rec (a)**: state and mukim describe the development
   (useful for every project, staff-registered ones too); the other three describe the submission.
3. **Semantic match blocks or only warns?** (a) warns only; the spelling lock keeps blocking as today; (b) a semantic
   match >= 0.90 or same lot + mukim also blocks Approve. **Rec (a)**: a meaning score is not deterministic enough to
   refuse a registration, and the checker is a person who reads the reason; revisit with real false-negative cases.
4. **PPF number format.** (a) PPF + yymm + 3 digits, monthly reset (`PPF2605065` = May 2026 #65), continuing the legacy
   series if the data shows it; (b) a running number that never resets. **Rec (a)**: it reads the example as given;
   the rule is a Settings row, so (b) is a setting change, not a rebuild.
