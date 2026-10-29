# PLAN: Escalate a missing technical drawing from a quotation line

Status: Plan, behaviour card filed, waiting on owner approval (M lane, standard track: new
endpoint + several files, expected diff over 300 lines; no new table, no migration if Q2 and Q5
go as recommended)

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
  :148-180). A PDF drawing, or an image typed anything else, is NOT a drawing to this screen.
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

## Behaviour card (for owner approval)

### Rules

1. On a quotation line whose Drawing cell is "no drawing" (product on catalogue, no image typed
   Technical Specifications), the cell shows an **Escalate** button instead of the bare text.
   Only for users who can edit the project (`projects.projects.edit`,
   `api/v1/projects/quotation_documents.py:58`); others see "no drawing" as today.
2. Escalate files **one drawing request per PRODUCT**, not per line. It is a form-SLA tracker:
   `source_entity_type = "product_drawing"`, `source_entity_id = <product id>`, assigned by
   round-robin in the configured team, with the SLA policy's deadline. No new tracker table.
3. If the product already has an open request (from this or any other quotation, by anyone),
   Escalate does not open a second one: it adds the salesperson as a requester on the open one
   (an event-log row on the tracker naming the requester and the quotation) and the cell shows
   the existing request's state.
4. The cell then reads **"Escalated <when>"** (the request's first escalation time, Malaysia
   time) with the SLA countdown chip the SLA screens already use (`TicketSlaChips`), on every
   line of every quotation that uses that product.
5. The request **closes itself** when an image typed Technical Specifications is linked to the
   product (or an already-linked image is retyped to it), using the same rule the cell uses, so
   "closed" and "the cell shows a drawing" can never disagree. Every requester gets an in-app
   notification ("Drawing added for <product code>") linking back to their quotation. No
   WhatsApp, no email.
6. The assignee sees it in their SLA task list like any form SLA, and can also close it
   by hand (the existing resolve action) if the product genuinely has no drawing.
7. Issued (frozen) quotation versions show the same escalated state but are never changed by the
   drawing arriving: the drawing reaches the next revision, as today.

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
SRTWT6808's covers 6 variants). The cell shows "no drawing" for these today, so Escalate shows;
the request closes only when an IMAGE arrives (rule 5) or by hand.

**What this means for the questions.** About 3 in 4 quoted lines will lack a drawing, so Escalate
will be on most lines. Team load and the per-product dedupe (Q1, Q3) matter more than whether a
PDF counts as a drawing: counting PDFs would clear under 2% of the gap. Catalogue totals: active
12,435 products, 1,376 with a drawing image, 7,853 with no files at all.

### Edge cases

- **Two salespeople escalate the same product** (same or different quotations, even at the same
  second): one open request; the second is recorded as a requester. The form-SLA idempotency
  check (`form_sla_service.py:899`) is read-then-write, so the endpoint locks the product row
  (`SELECT ... FOR UPDATE`) around it and two clicks cannot open two trackers. Tested.
- **Drawing added while the request is open**: closes, every requester notified once (rule 5).
- **Drawing added, later deleted, product escalated again**: a new request (the old one stays
  closed as history).
- **Product with no brand / no owner team**: routing is the configured team set, not the brand,
  so a brandless product still routes. If the stage has no team configured at all, Escalate
  answers "No team is set up for drawing requests" (409) and creates nothing; it never fails
  silently (`emit_event` would otherwise skip without a word, :383-384).
- **Off-catalogue line / SET line**: off-catalogue has no product, so no button. A SET line uses
  its driver part's product (`project_quotation_image_service.line_product_id`, :91-104).
- **Line added this session, not saved**: no button until Save (the cell claims nothing for an
  unsaved line today, `QuotationLineFileCell.tsx:117`).

### Questions (owner)

**Q1. Who receives it?** (a) the `marketing_product` team set, the team the WhatsApp bot already
routes product-attachment requests to (`policy_rows.py:76-81`); (b) `purchasing`, which takes
product/spec questions (:66); (c) per brand. **Recommendation: (a)**, it is the same team for the
same kind of ask, and brand narrowing can follow later if one team proves too broad.

**Q2. What does it create?** (a) a form-SLA tracker on the existing table, keyed by product,
requesters as event-log rows (no new table, lane stays M); (b) a new `drawing_requests` table
with its own status (lane becomes L). **Recommendation: (a)**, it already carries the assignee,
round-robin, working-hours deadline, overdue escalation, the assignee's task list and manual
close.

**Q3. One open request per product, later escalations add the requester as a follower?**
(a) yes; (b) one per quotation line. **Recommendation: (a)**, marketing draws a product once.

**Q4. Close itself when an image typed Technical Specifications is linked, notifying every
requester in-app?** (a) yes; (b) close by hand only. **Recommendation: (a)**; manual close stays
available for "this product has no drawing".

**Q5. How is the stage set up?** (a) an admin adds a "Product drawing" stage in SLA Management >
Form SLA config (agent, team set `marketing_product`, policy), exactly as price tag requests were
set up, no migration; (b) a migration seeds it. Note: the stage needs its own access agent code,
because naming the WhatsApp conversation agent in a form-SLA stage reclassifies that agent as a
form-SLA agent (`form_sla_service.py:49-66`) and changes its tier-1 routing.
**Recommendation: (a)**, no data guesses in a migration on a public repo, and until it is set up
Escalate answers plainly instead of failing silently.

## Mock

`mockups/quote-drawing-escalate-29oct-mock.html`: the eight cell states and the element-to-component
map.

## Tests (red first, after approval)

- BE: dedupe per product (second escalate adds a requester, no second tracker; concurrent
  escalates make one); auto-close on linking a Technical Specifications image and on retyping
  one, not on a PDF; every requester notified once; 403 without `projects.projects.edit`; 409
  with no configured stage; line read carries the request state.
- FE: cell states (no drawing read-only, Escalate button, Escalated + chip, drawing shown).
