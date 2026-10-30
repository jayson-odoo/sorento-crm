# PLAN: Escalate a missing technical drawing from a quotation line

Status: Plan, behaviour card v3 (owner answers 30 Oct + dashboard note folded in) filed, waiting on owner approval
(M lane, standard track: new endpoints + several files, expected diff over 300 lines; no new
table, no migration)

Source: owner team meeting 29 Oct (Project Sales module). When a quotation line's product has no
technical drawing, the salesperson needs an "Escalate" action on that line, mirroring the existing
messaging escalation, so the responsible team supplies the drawing. This was asked in the
discussion but is not in the meeting's next-steps list, so the behaviour below is for the owner to
confirm before any code.

## Where things are today (main ec29a81c)

- The Drawing cell prints plain "no drawing":
  `sorento_crm_frontend/app/(protected)/project-sales/[projectId]/components/QuotationLineFileCell.tsx:148`,
  from `line.technical_drawing.state`.
- That state is `NO_DRAWINGS` (`sorento_crm_backend/app/services/project_quotation_image_service.py:66`),
  set per line at :202, served on every line read by `project_quotation_service.py:1519`.
- What counts as a drawing: an image (`image/*`), not deleted, typed exactly
  "Technical Specifications" (`product_image_service.py:84`, `_on_file` :140-146, `files_for`
  :148-180). A PDF drawing, or an image typed anything else, is NOT a drawing to this screen
  today. The quotation documents embed the drawing's image bytes
  (`project_quotation_pdf_service.py:372`, `project_quotation_excel_service.py:430`), so a PDF
  can never be the line's printed drawing.
- **The "existing messaging escalation"** is the WhatsApp bot's hand-off: when a customer asks
  for a product document the bot can't answer, it offers to escalate
  (`chatbot_reply_copy.py:52-58`) and the escalation lane
  (`chatbot/lanes/escalation.py:1-50`) assigns a person by round-robin from a team set and opens
  an SLA tracker with a deadline. Which team: the `product_attachment` domain escalates to team
  set **`marketing_product`** (`chatbot/turn/policy_rows.py:76-81`); plain product/spec questions
  go to `purchasing` (:66).
- The same tracker table serves internal forms through the **form SLA orchestrator**
  (`form_sla_service.py:1-12`): a form type has a stage row in `form_sla_configs` (agent, team
  set, SLA policy), and `_start_for_config` (:891-1087) picks a tier-1 assignee by round-robin,
  sets response/resolution deadlines on the working calendar, writes a
  `conversation_sla_tracking` row keyed by `(source_entity_type, source_entity_id)`, and notifies
  the assignee. It is idempotent per entity (:899-901). Price tag requests use exactly this for
  their single marketing stage (`form_sla_service.py:42-43`), configured in SLA Management, not
  seeded.

- **How a form-SLA task is responded to and resolved today.** Not by a button on the task: the
  My Pending widget hides Respond/Resolve on form rows (`MyPendingSLAWidget.tsx:704`, `!form`) and
  shows the stage's next action as text (`sla_service._form_next_actions`, :2180-2229). The stage
  moves when the form's own record emits the configured `respond_event` / `resolve_event`
  (`form_sla_service.py:342-420`). Event names per type come from `FORM_SLA_EVENT_OPTIONS`
  (`_shared/formSLAService.ts:374`), and the admin picks them in the Form SLA config dialog
  (`FormSLAConfigDialog.tsx:216, 342-366`); agent and team set are free-text fields there
  (:322, :331).
- **Who can open a quotation:** `projects.projects.view` or `view_own` (`api/v1/projects/quotations.py:66-69`).

## Behaviour card v2 (for owner approval)

Owner answers 30 Oct: Q1 the receiver is configurable through the existing team-set
configuration, default the marketing product team, nothing hard-coded. Q2 (a) a task on the
existing SLA tracker. Q3 (a) one open request per product. Q4 no auto-close: the team responds to
and resolves the SLA task the normal way; adding a drawing may notify. Q5 configurable, the admin
sets the step up in SLA Management, no seeded data. Q6 a PDF drawing counts as a drawing. Q7
Escalate on every line without a drawing.

### Rules

1. **Has a drawing** means: the product has a file typed "Technical Specifications" that is an
   image OR a PDF, not deleted (Q6). Only images can be shown in the cell and printed, as today.
2. **Escalate shows on every saved line whose product has no drawing** (Q7), on every version,
   draft or issued, including a SET line (it escalates its driver part, `line_product_id` :91-104),
   for anyone who can open the quotation (`view` or `view_own`). Not on an off-catalogue line (no
   product to draw) and not on an unsaved line (shown after Save, as the cell does today).
3. **A product with only a PDF drawing** shows a PDF tile in the cell that opens the file in a new
   tab. No Escalate. The quotation documents print no drawing for it, as today (they embed images
   only).
4. **Escalate opens one request per PRODUCT** (Q3): a form-SLA task on the existing tracker table
   (Q2), `source_entity_type = "product_drawing"`, `source_entity_id = <product id>`. The admin
   sets the step up in SLA Management > Form SLA config (Q5): access agent, team set, SLA policy,
   and which events respond and resolve it. Choosing type "Product drawing" pre-fills team set
   `marketing_product` (Q1 default, the team set the WhatsApp bot routes product-attachment asks
   to, `policy_rows.py:76-81`); the admin can change it. Nothing about the team is in code.
5. **A product with an open request**: the next Escalate joins it. The caller is recorded as a
   requester (an event-log row on the tracker naming them and the quotation); no second task.
6. **The cell reads "Escalated <date>"** on every line of every quotation with that product,
   coloured by the task's deadline (neutral, amber under 4h, red overdue), hover "Escalated <date>
   by N people. Due <date>." After the team responds it reads "Responded <date>".
7. **The team works it the normal SLA way** (Q4), on the home **Dashboards** page, "My pending
   tasks" (owner note 30 Oct, mock v3). That widget (`MyPendingSLAWidget`, mounted at
   `app/(protected)/(home)/page.tsx:30-33`) is where every form-SLA task already lands: its feed,
   `sla_service.list_my_pending` (:1264), takes every open tracker assigned to the user with no
   type filter, so the drawing task appears there with no new screen. The row is the existing
   row component (`MyPendingSLAWidget.tsx:499-620`): "Product drawing . <product code>",
   "Tier N . Respond|Resolve", "Respond by|Resolve by <date>", with a **Respond** button until
   responded, then **Resolve** (open question N1), plus Extend. It also shows under My Team for
   the team lead. Round-robin assignee, working-hours deadline, overdue escalation up the tiers,
   extend and take-over all work as for any form-SLA task. Clicking the row opens the product
   page (`/master-data-management/products/<id>`), where the drawing is uploaded. What has to be
   added for this: the type in `FORM_SLA_TYPES` (`form_sla_service.py:33`), its label and route
   in `ENTITY_ROUTES` (`MyPendingSLAWidget.tsx:82-87`), the product code as the row reference
   (`sla_service._resolve_my_pending_references`, :2242, has no product mapping today), and the
   two buttons for this type (hidden for form rows today, :704-740).
8. **Adding a drawing does not close the task.** It notifies the assignee in-app ("Drawing added
   for <code>, resolve the request when done").
9. **Resolving notifies every requester** in-app: "Drawing request for <code> resolved", linking
   to the quotation they escalated from. No WhatsApp, no email. The cell then shows the drawing
   if one is on file, else "no drawing" with Escalate again (open question N2).

### Examples from dev data (crew, 29 Oct; 20 Oct prod restore, read-only; counts and codes only)

Rule used is the screen's: typed exactly "Technical Specifications", `image/*`, not deleted.

**Quotation lines (the module is new: 4 lines in the whole DB).**
- SRTWC286-SH: has a drawing image, the cell shows it. No Escalate.
- BRAC73080604-0001: no drawing image, no PDF either. Escalate shows.
- A coupling line on the same quotation: same, Escalate shows.
- SET SRTWC6405: its driver part SRTWCX6405 has no drawing, so the set line reads "no drawing"
  through the driver rule (`project_quotation_image_service.line_product_id`) and Escalate files
  the request for SRTWCX6405, not the set.
- So 3 of 4 lines would show Escalate; none of them has a PDF drawing.

**Same product missing a drawing on several quotations.** Not seen yet on quotations (4 lines),
but project sales orders show what is coming: of 1,245 products on 910 project SOs, 925 have no
drawing image, covering 78% of project SO lines. The most-ordered ones (WESERP10B 1,237 lines,
B2155-NL-BLUE 1,064, C-FH14 663, CB1178A-SS-NEW 414, CB2805A-DIY 401) will each be quoted many
times, which is what one-request-per-product (Q3) is for: one task per product, many requesters.

**A drawing of the wrong type.** 190 products carry 196 files typed Technical Specifications
that are PDFs, not images; no image of another type is named like a drawing. Active products
with a PDF drawing only: 178 of 11,059 without an image (1.6%). They are mostly Sorento SRTWT
codes, and one PDF is often shared by several variants (SRTWT2215 and SRTWT2216 share one;
SRTWT6808's covers 6 variants). The cell shows "no drawing" for these today. Under v2 (Q6) they
count as having a drawing: the cell shows a PDF tile and no Escalate (rule 3).

**What this means for the questions.** About 3 in 4 quoted lines will lack a drawing, so Escalate
will be on most lines. Team load and the per-product dedupe (Q1, Q3) matter more than whether a
PDF counts as a drawing: counting PDFs would clear under 2% of the gap. Catalogue totals: active
12,435 products, 1,376 with a drawing image, 7,853 with no files at all.

### Edge cases

- **Two salespeople escalate the same product** (same or different quotations, even at the same
  second): one open task; the second is recorded as a requester. The form-SLA idempotency check
  (`form_sla_service.py:899`) is read-then-write, so the endpoint locks the product row
  (`SELECT ... FOR UPDATE`) around it and two clicks cannot open two tasks. Tested.
- **Same person escalates twice**: recorded once.
- **Drawing added while the task is open**: the task stays open, the assignee is notified (rule 8);
  the cell shows the drawing at once (it reads the product live) while the task waits to be
  resolved.
- **Resolved without a drawing** (the team says none exists): requesters are told; the cell shows
  Escalate again (N2).
- **Drawing later deleted**: the cell goes back to "no drawing" and Escalate; a new task opens.
- **Product with no brand**: routing is the configured team set, not the brand, so it routes.
- **Step not set up**: Escalate answers "No team is set up for drawing requests" (409) and
  creates nothing; it never fails silently (`emit_event` would otherwise skip without a word,
  `form_sla_service.py:383-384`).
- **Stage reuses the WhatsApp agent's code**: the admin must give the step its own access agent
  code; naming the conversation agent in a form-SLA stage reclassifies it as a form-SLA agent
  (`form_sla_service.py:49-66`) and changes its tier-1 routing. Stated in the hand-test setup.

### Open questions (v2, at most 4)

**N1. Where does the assignee press Respond and Resolve?** (a) on the task's row in the dashboard's "My pending tasks",
the same two buttons a conversation ticket has there today (`MyPendingSLAWidget.tsx:704-740`),
shown for this type only; the row's link opens the product page to upload the drawing; (b) a
Respond/Resolve banner on the product's page. **Recommendation: (a)**, it is where the team
already works SLA tasks, and it needs no new screen on the product page.

**N2. Resolved without a drawing: can it be escalated again?** (a) yes, the cell goes back to
Escalate and a new task opens; the hover shows when the last one was resolved; (b) block
re-escalation for some days. **Recommendation: (a)**, simplest, and a repeat ask is a real signal.

**N3. A PDF-only drawing on the quotation document.** (a) the cell shows a PDF tile that opens it,
the printed quotation shows no drawing for that line (as today); (b) also render the PDF's first
page into the PDF/Excel quotation (lane becomes L). **Recommendation: (a)**.

**N4. Who may escalate** (Q7, "every line"). (a) anyone who can open the quotation (`view` or
`view_own`); (b) only `projects.projects.edit`. **Recommendation: (a)**, escalating changes no
quotation data.

## Mock

`mockups/quote-drawing-escalate-29oct-mock.html` (v3): the cell states, the dashboard's "My pending
tasks" rows, and the element-to-component map.

## Tests (red first, after approval)

- BE: dedupe per product (a second escalate adds a requester, no second task; the same person
  twice is one requester; concurrent escalates make one); a PDF typed Technical Specifications
  counts as a drawing (no escalate, 409 "already has a drawing"); adding a drawing does NOT
  resolve and notifies the assignee; respond and resolve through the configured events, resolve
  notifies every requester once; 403 without view/view_own, 404 for a quotation outside own
  scope; 409 with no configured step; the line read carries the request state; no team code in
  the service.
- FE: cell states (Escalate, escalating, Escalated, Responded, PDF tile, drawing shown,
  off-catalogue blank); My Pending Respond/Resolve on a product_drawing row.
