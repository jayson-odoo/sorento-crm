# Behaviour card v3: Project registration from the portal (PROJECT-REG-PORTAL)

Status: card v3 + mock v3 filed (25 Oct 2026): v2 (owner answers 12:30) reshaped by crew's masked summary of the team's
WhatsApp registration chat. Nothing built. Size **L** (one additive migration). v1 / v2 are in git history
(73412ba6, e551fb3f).
Mock: `mockups/project-registration-portal-v3.html` (every element names its component + path).
Paths: BE = `sorento_crm_backend/app/`, FE = `sorento_crm_frontend/`.
The chat summary itself is NOT in this repo (crew rule). Every example below is a fake analogue shaped like a real case.

## Owner rulings folded in (25 Oct 12:30)

- As simple as the legacy desktop **Project Registration Form**: Project Title, Distributor Name, Sales Agent, Customer
  Name, Type of Building, State, Mukim, Status (Pending), PPF No., Date, Your Ref, Developer, Main Contractor, Architect;
  Approve / Reject.
- Sales Agent, PPF No., Date automatic. Developer, State, Mukim filled from the title or by AI from a photo, editable.
- Checker = **Project Sales Admin** (a named grant). Free-typed developer allowed, checker resolves it before Approve.
  Staff keep registering directly. A registration record of its own.
- Duplicate check must be **semantic**, shown to the checker and as a hint in the portal.

## What the chat shows (summary, shapes only) and what changed from v2

| Chat finding | v3 change |
|---|---|
| There is no template. Salespeople send a pasted title, a photo only (almost as often), both, or a one-liner. | **Title can be AI-filled from a photo** (v2 assumed it is always typed). Submit needs a title, however it got there. |
| Titles follow planning wording: "CADANGAN ... DI ATAS LOT/PT ..., MUKIM X, DAERAH Y, NEGERI. UNTUK (TETUAN) <DEVELOPER> SDN BHD" or "PROPOSED ... FOR MESSRS ...". Photos: the PROJECT TITLE box of drawings, BQ / sanitary schedule covers, tenders, PDF screenshots, typed cards, rotated folder covers. | AI extracts **lot/PT and daerah** as well, and a **Type of Building** guess from the title words. |
| State is usually readable, developer often, mukim / daerah / lot about half the time, architect and contractor rarely. The admin keeps asking "Which state?" and "Developer?". Developers include government clients (JKR-type departments) and private persons. | **State and Developer required** on submit. The label reads "Developer / Client". If the place is ambiguous (e.g. Cheras is in Selangor and in KL), AI leaves State empty and the form asks. It never guesses. |
| "Under <distributor>" / "customer: <dealer>" appears in roughly a quarter of requests, ambiguously. | AI reads it as a **distributor hint**, matched against the agent's debtors and offered ("Did you mean ...?"), never picked for them. Q1's recommendation is unchanged. |
| The admin approves by replying with a bare PPF number, and answers "Already registered (under your name) / Project No: PPF... / Date Reg / Sales Agent" about a fifth of the time. | **PPF is drawn on Approve and becomes the project's number** (v2 drew it on submit). Q4 changed, see below. Reject offers that exact sentence as a one-tap reason. |
| The stable duplicate key is **lot/PT + mukim + developer**. Wording drifts: typos, a short-name prefix vs the full uppercase title, location-first reordering, "SUB CONTRACT FOR ..." vs "...", unit counts written two ways. False positives: the same developer with a different project; **different phases on the same lots belong to different salespeople**; a renamed developer ("X (DAHULUNYA Y)"). | The duplicate check is rebuilt around the **lot key + meaning**, with phase-aware labelling. Q3's recommendation is unchanged and now has evidence (a lot match must not block, because phases share lots). |
| "Whose project is this?" lookups come up 20+ times. | The portal gets a **Search registered projects** screen, not just Create. New Q5 asks what it shows. |
| Owner transfers happen ("PPF... From X To Y"). | Out of scope: the existing project owner change (`projects.projects.manage`) covers it after approval. |
| The PPF format changed on 23 Apr 2026: now PPF + YY + MM + 3 digits, reset monthly (PPF2609001 on 1 Sep). Before that it was PPF + YYMM + 4 digits, running. | Confirms Q4's format. The rule continues the current month's series from the highest PPF issued in the legacy system at go-live. |
| About 26 requests a week and 100-130 PPF a month. | 3 digits a month is enough (max 999). One embedding call per check is negligible. |

## The form (legacy field -> filled by -> stored -> on Approve)

| Legacy field | Filled by | Stored on the registration | On Approve |
|---|---|---|---|
| PPF No. | auto **on Approve** | `ppf_no` NULL until approved | **becomes `projects.project_code`** (Q4) |
| Date | auto (submit date) | `submitted_at` | - |
| Status | auto: Pending / Approved / Rejected / Withdrawn | `status` | - |
| Project Title * | typed or pasted, or AI from the photo when empty (long free text) | `title` | `projects.title` |
| Sales Agent | auto: the contact's active sales agent (several = pick own) | `sales_agent_id` | owner = that contact's CRM user (rule 6) |
| Developer / Client * | AI or typed; party pick or free text | `developer_party_id` or `developer_text` | `projects.developer_party_id`, resolved by the checker |
| Main Contractor, Architect | AI or typed / picked | `*_party_id` or `*_text` | `sales_profile.*_party_id` (typed names become parties) |
| State * | AI or pick from `MY_STATES` (FE `app/(protected)/order-management/customers/forms/client-form-constants.ts:1`) | `state` | Q2 |
| Mukim, Daerah, Lot/PT | AI or typed | `mukim`, `daerah`, `lot_no` | Q2 |
| Type of Building | AI guess from title words, or pick from Project types (`BE/models/projects.py:134`) | `type_id` | `projects.type_id` |
| Distributor Name | AI hint from "Under X" or pick from agent's debtors (Q1) | `distributor_customer_id` | Q2 |
| Customer Name | typed (Q1) | `customer_name` | Q2 |
| Your Ref | typed, optional | `your_ref` | Q2 |
| Photos | attached: drawings' title box, BQ cover, tender, screenshot | portal attachments | copied to the project's files |

## Rules

1. **One step, like the legacy form.** Submit -> **Pending** (locked). The checker **Approves** (PPF drawn, project
   created) or **Rejects** (reason required; one-tap "Already registered as PPFxxxx, <holder agent>, <date>" when a
   candidate is picked). A rejected registration is edited and resubmitted; a Pending one can be withdrawn. No Draft,
   no Revise.
2. **PPF No. = the project's number, drawn on Approve.** The admin's bare-PPF reply is the approval today, and "Project
   No: PPF..." is how the team names a project. So Approve sets `projects.project_code` to the next PPF from the
   project numbering rule (`NUMBERING_DOC_TYPE = "project"`, `BE/services/project_service.py:39`), whose template
   becomes `PPF{yy}{month:02d}` + 3 digits with a monthly reset. That is a settings change on the existing rule, not
   code (`BE/services/numbering_service.py:64-86`). `register_project` already draws the code only after the clash
   check passes (`project_service.py:118-129`), so a rejected or withdrawn request never burns a number, which matches
   the paper. Staff registrations get PPF numbers too, because one register needs one series. Existing PRJ-xxxx codes
   are untouched (unique per company, `models/projects.py:320`). Go-live: `next_value` = the highest PPF of the month
   issued in the legacy system + 1, supplied by crew.
3. **AI fill (one mechanism, text and photo).** "Fill from title / photo" sends the title as text plus the photos to the
   existing **`AIExtractService.extract()`** (`BE/services/ai_extract/extract_service.py:284`; text parts accepted
   `:77-79`). The endpoint is the same synchronous `POST /public/portal/ai-extract` (`BE/api/v1/public/ai_extract.py:99-150`),
   reached through `AttachmentDropzone.onExtract` -> `AIExtractDialog` (FE `app/(auth)/portal/components/AttachmentDropzone.tsx:82,97`).
   New form key `portal.project_registration` in `FORM_SCHEMAS` (`BE/services/ai_extract/form_schema_registry.py:400`),
   with fields: title, developer, main_contractor, architect, state, mukim, daerah, lot_no, building_type,
   distributor_hint. The prompt notes say:
   - read Malay and English planning wording: "UNTUK (TETUAN)" / "FOR MESSRS" introduce the developer, "DI ATAS LOT/PT"
     the lot;
   - a government department or a person can be the developer;
   - "DAHULUNYA" means "formerly", so keep the current name;
   - leave the state empty when the place exists in more than one state;
   - photos may be rotated.

   It fills only empty fields, everything stays editable, and party / debtor / type names are offered as "Did you
   mean", never auto-picked.
4. **Duplicate check** (section below): a hint in the portal while filling, and a panel for the checker.
5. **Checker = Project Sales Admin**: new permission `projects.registrations.approve`, seeded to the role of that name
   (existence asked via crew-data-request; admin roles otherwise). The menu item Project Sales > Registrations needs
   it. An applicant never approves their own registration.
6. **Approve** calls the existing `register_project()` (`BE/services/project_service.py:70-195`): first stage
   "Registered" (`BE/services/project_seed_service.py:53`), template tasks, and the spelling lock's 409 for a hard
   duplicate. Before Approve the checker resolves a typed developer to a party and confirms the owner. Owner = the CRM
   user whose `respond_contact_id` is the contact (`_linked_user_id`, `BE/api/v1/public/portal_sample_request.py:50-52`);
   when the agent has no CRM user, the checker picks one.
7. **Who can submit**: portal contacts granted the kind `project_registration` (opt-in, `BE/services/portal_service.py:95`)
   AND linked to an active sales agent (`agents_for_contact`, `BE/services/sales/portal_agent.py:24-33`).
8. **Search registered projects (new, portal).** A search box over the projects of the contact's companies, by PPF / code,
   title words, developer, lot, mukim. It answers "whose project is this?" without a WhatsApp round trip. It reuses
   `projects_for_contact` (`BE/services/sponsorship_link_service.py:45-85`, behind `GET /public/portal/lookups/projects`,
   `BE/api/v1/public/portal.py:530`), widened with developer, state, registration date and (Q5) the holder's sales agent.
   It uses the same semantic ranking as the duplicate hint, so a pasted title finds its project.
9. **Notifications** (NPA pattern, in-app + email): Pending -> holders of `projects.registrations.approve`. Approved
   ("Approved: PPF2610014") and Rejected (with reason) -> the contact's CRM user.
10. **Afterwards** the portal landing kind "Project registration" lists title, developer, status, PPF once approved, and
    the reason once rejected. The approved project appears in the Sample request project picker with no change, so
    `sample_request_require_project` works for portal salespeople.

## Duplicate checking

**Today, in plain words** (`find_clashes`, `BE/services/project_clash_service.py:211`): spelling only. Titles are
lower-cased (`:84-93`), then scored by shared three-letter chunks, overall and "how much of one is inside the other",
both ways (`_score_expression`, `:156-183`), plus whole-substring containment (`titles_overlap`, `:188-208`). A score of
0.55 or more shows as similar. 0.70 or more, with the same developer and the project still open, **blocks**
(`:45-46`, editable in Settings `:134-153`). Different phase numbers never block (`are_sibling_developments`, `:112`).
It knows letters, not meaning or place: the chat's drift cases (short name vs full planning title, reordered wording,
"SUB CONTRACT FOR ..." prefixes, unit counts written differently) mostly fall below 0.55.

**Proposed, three signals, shown together with the reason (the spelling lock stays as is):**
1. **Same lot** (strongest, deterministic): same normalised lot/PT number ("LOT 4321", "PT 4321" and "Lot 4321" all
   read as 4321) in the same mukim. With the same developer, "very likely the same". With a different phase designator
   in the title (reusing `phase_designators`, `project_clash_service.py:96-109`), it reads **"same lots, different
   phase"**: shown, labelled, never treated as a duplicate. This is the chat's Phase 4 / 5 case.
2. **Meaning**: cosine similarity of `title | developer | state, mukim, daerah` using the CRM's existing
   `text-embedding-3-small` (1536 dims, `BE/config.py:289-299`) in pgvector (`embedding_chunks`, HNSW cosine,
   `alembic/versions/142_pgvector_embedding_pipeline.py:117-118`). Projects become a new embedded source type on the
   existing worker (`BE/services/embedding_worker.py:94`, listener `embedding_change_listener.py:186-208`), so they are
   kept current off the request path. The registration line is embedded in-request with `_embed_text_chunks` (`:616`,
   as `entity_resolver.py:5269-5280` does), then searched with `search_current(source_type="project")`
   (`BE/services/embedding_service.py:228`). The proposed bar is **0.80** (the CRM's own confident-match bar,
   `entity_resolver.py:2932`), calibrated in Phase 2 on the live titles the way the trigram bars were.
3. **Spelling**: today's trigram score, unchanged.
- **Same developer, different project** (the chat's convention-centre case) only matches on developer, so it never
  surfaces on its own: the developer is a qualifier, not a signal.
- **Renamed developer**: the meaning signal carries "X (DAHULUNYA Y)" to projects filed under Y.
- **What it does**: warns only (Q3 a). The checker sees each candidate with its reasons ("same lot 4321, Mukim Klang,
  same developer"; "meaning 0.86"; "same lots, different phase"). The portal hint shows code + short title (+ Q5).

## Customer vs distributor vs lead (owner unsure)

- A project has no customer column (`BE/models/projects.py:225-306`). The buyer appears later as a party on the
  quotation (`recipient_party_id`, `:1060`) or the PO (`issuing_party_id`, `:1632`). A party becomes a debtor only
  once it issues a PO (`:100-102`, `:117`).
- A lead's buyer is optional (`:684-696`): "requiring one meant inventing a customer row".
- The portal's other forms pick only from the agent's own debtors (`BE/services/sample_request_service.py:258-289`).
- The chat: "Under <distributor>" / "customer: <dealer>" name **the dealer we invoice**. The salesperson's
  "customer" is our distributor.

So: **Distributor Name = a pick from the agent's debtors** (AI-offered from "Under X"). **Customer Name = typed** (their
client, usually not in our books). There is no debtor link, nothing is created, and there is no Lead row: the
registration is "our reference".

## Examples (fake analogues of the chat's extraction cases; no real names)

| # | Salesperson sends | Result |
|---|---|---|
| A | Drawing title-box photo only: "CADANGAN MEMBINA KILANG 2 TINGKAT DI ATAS LOT 9001, MUKIM TEBRAU, DAERAH JOHOR BAHRU, JOHOR. UNTUK TETUAN ALPHA PACKAGING SDN BHD" | AI fills the title from the photo, developer "Alpha Packaging Sdn Bhd" (offered: no party yet, typed), state Johor, mukim Tebrau, daerah Johor Bahru, lot 9001, type Factory. Submit -> Pending |
| B | Sanitary-schedule cover photo, Kota Kinabalu, Sembulan; developer only in the caption "dev: Beta Land"; "Under Distributor Q" | Title + state Sabah + mukim from the photo; developer from the caption text; distributor hint "Distributor Q" offered against the agent's debtors |
| C | Typed card "Gamma D'Residence, Cheras", no state | AI leaves State empty (Cheras is in Selangor and in KL); the form asks "Which state?". Submit refused until picked |
| D | "Lot 4321 Kg Sungai Delta, Mukim Klang" + "Under Distributor R"; an approved project already has LOT 4321, Mukim Klang, same developer | Portal hint: "Possibly already registered: PPF2609023". Checker panel: "same lot 4321, Mukim Klang, same developer". Reject with one tap: "Already registered as PPF2609023, SA-004, 03/09/2026" |
| E | Rotated folder cover "PEMBAIKAN DAN NAIK TARAF KOMPLEKS JABATAN E, PERLIS" | Title, client "Jabatan E" (government, entered as developer / client), state Perlis; mukim / lot empty. Submit allowed (state + developer present) |
| F | "TAMAN DELTA FASA 5" on the same lots as an approved "TAMAN DELTA FASA 4" held by another salesperson | Shown as "same lots, different phase", not a duplicate; Approve allowed (the spelling lock also treats phases as siblings) |
| G | Salesperson searches "taman delta" in the portal before registering | Finds the approved Fasa 4 project (PPF, title, developer, registration date, + holder agent per Q5) |

## Edge cases

- Two Pending registrations of the same job: both are in the queue. After the first is approved, the second shows it as
  a "same lot" candidate (and the lock refuses it if spelling + developer match).
- AI finds nothing, or the provider is down: "Couldn't read it, fill the fields yourself"; the form stays usable.
- Photo is not a project document: fields come back empty, nothing is overwritten.
- PPF numbering rule missing at Approve: the existing 422 `project_numbering_rule_missing`; the request stays Pending.
- 999 PPF in one month: the numbering service pads, not truncates, so the 1000th is `PPF26101000`. A 4-digit setting is
  one click if volume grows.
- No UUIDs anywhere; parties, agents and debtors render by name / code.

## Data (additive migration, schema `projects`)

`project_registrations`: id, company_id, status (CHECK pending|approved|rejected|withdrawn), contact_id, sales_agent_id,
applicant_user_id NULL, title, developer_party_id / developer_text, main_contractor_party_id / _text,
architect_party_id / _text, state, mukim, daerah, lot_no, type_id, distributor_customer_id, customer_name, your_ref,
project_id NULL (its project_code IS the PPF), submitted_at, decided_at, decided_by, reject_reason, timestamps.
Seed: permission `projects.registrations.approve`. Numbering rule `project` changed to PPF (settings data, Q4). Embedding
source type `project` (no schema change). Plus Q2's columns.

## Questions (recommendation first; what the chat changed is marked)

1. **Customer.** (a) Distributor = a pick from the agent's debtors (AI-offered from "Under X"); Customer = typed; no
   debtor link, no Lead; (b) Customer also picked from debtors; (c) also create a Lead. **Rec (a), unchanged**, now
   with the chat's evidence that "customer: <dealer>" means the distributor.
2. **Where the place fields live after Approve.** (a) **State, Mukim, Daerah, Lot/PT** become columns on
   `projects.sales_profile` (they are the duplicate key, and Pipeline can filter by state). Distributor, Customer and
   Your Ref stay on the registration, shown on the project. (b) All of them stay on the registration only. (c) All are
   copied. **Rec (a), widened from v2** (v2 had State + Mukim only): the chat shows lot/PT + mukim is the stable
   identity, so it must sit on every project, staff-registered ones included, for the check to see them.
3. **Semantic / lot match blocks or warns?** (a) warns only; the spelling lock blocks as today; (b) same lot + mukim +
   developer also blocks Approve. **Rec (a), unchanged and now with evidence**: different phases on the same lots
   belong to different salespeople, so a lot match is legitimately not a duplicate often enough that a person must decide.
4. **PPF No. (CHANGED).** (a) **Drawn on Approve and used as the project's code**: the project numbering rule becomes
   PPF + yy + mm + 3 digits, monthly reset, continuing the legacy month's sequence; staff registrations get PPF too;
   old PRJ codes stay. (b) PPF drawn on submit as the request's own number; the project keeps a separate PRJ code.
   **Rec (a)**: the chat shows the PPF is given at approval and is what the team calls "Project No". Two numbers per
   project would bring back the "which number?" question. Format confirmed by the 23 Apr 2026 change.
5. **Portal search: show who holds a project? (NEW).** (a) Show the holder's **sales agent code** and the registration
   date, as the admin's WhatsApp replies already do ("Sales Agent / Date Reg"); (b) code + title only, no holder.
   **Rec (a)**: it is what the team already tells each other 20+ times; it removes the round trip without exposing
   anything beyond today's replies. (Pipeline readers in the CRM already see owner names.)
