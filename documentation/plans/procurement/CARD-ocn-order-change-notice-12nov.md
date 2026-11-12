# Behaviour card: Order Change Notice (OCN-ORDER-CHANGE-NOTICE)

Status: Gate 1, card v2 12 Nov 2026 (crew answers on v1 folded in, section 8). Waits for the owner on d1, d2
and approval of card + mock v2. Size L, full track (migration, new SLA
rows, portal kind). Mock: `documentation/mockups/ocn/index.html` (Gate 2, filed separately).
Paths: BE = `sorento_crm_backend/app/`, FE = `sorento_crm_frontend/`. Read from `main` aa824637.
Every name, PO number and item code below is invented (public repo).

## 0. What exists today (measured)

1. **An OCN record already exists, half built.** `models/project_so.py:668` `OrderChangeNotice`, table
   `projects.order_change_notices`, company-scoped, audited. The project sales order flow auto-drafts one
   for every amendment to a published SO (`services/project_so_delta_service.py:728`), number
   `OCN-` + digits from numbering type `order_change_notice` (`:88`, `:1465`), with the computed change
   table (`change_table_json`). Publishing the amendment refuses unless the OCN has an approver
   (`:791`). **Nothing in the product sets `approver_id`**: only tests do
   (`tests/test_project_so_delta.py:466`). So today an amendment to a published SO cannot be published
   at all. There is no OCN list, no OCN page, no form, no approval, no SLA, no notice.
2. **PR and SF are one table** (`models/procurement.py:1124`, `request_type`), with no `company_id`, and
   columns that mean nothing for an OCN (sponsor subject, project value, purpose, sales type, price lines).
3. **The live PR and SF SLA rows (crew dump, dev, 12 Nov)** are identical in shape, agent `purchase_request`,
   notify assignee + escalation on, no skip, no grace:

   | Stage (team set)        | Starts on          | Resolves on                                  |
   |-------------------------|--------------------|----------------------------------------------|
   | main (`project_sales`)  | submit             | send_for_approval, reject_submitted, voided  |
   | project_sales_manager   | send_for_approval  | approved, approval_rejected, voided (advance on approved) |
   | customer_service        | approved           | resolved, voided                             |

   Policy tiers (PR and SF the same): 1 Project Sales Admin 24 h, 2 Project Sales Manager 72 h,
   3 Director 24 h (response = resolution). Numbering: `PR{yy}-` / `PSSF{yy}-`, 4 digits, start 300,
   yearly, per company.
4. Several stage rows may start on the same event; each runs its own clock (`services/form_sla_service.py:434`).
   A stage's team comes from its own `agent_code` + `team_set_code` (`:960`, `:1010`), so a Purchasing
   stage can use the `purchasing` team set the Stock Inquiry and NPA already use (agent
   `lead_time_enquiries`, `PLAN-npa-form-sla-08nov.md`): no new teams.

## 1. Design decision: where the OCN lives

| | (a) third `request_type` on `purchase_requests` | (b) its own form on the existing `projects.order_change_notices` (recommended) |
|---|---|---|
| PR / SF screens | Every PR/SF branch becomes three-way: 16 two-way if/else sites that would silently label an OCN as PR or SF, 30 hard-coded `(purchase_request, sponsorship_form)` pairs that would silently drop it, ~25 `isSponsorship` branches in the 1269-line `PurchaseRequestForm.tsx` | Untouched |
| Data shape | No company scope; price lines; no before/after | Already company-scoped; already has project, PO, SO links and a change table |
| Numbering | Would share or fork the counter the amendment OCN already uses | One `OCN{yy}-` counter for both ways an OCN is born |
| SLA registry | New key in the same lists | Same: one new key `order_change_notice` in `FORM_SLA_TYPES` and its lockstep lists |
| Permissions | Merges into `purchase_requests.*` workflow slugs | Own `procurement.order_change_notices.*` set, like SF's own view/create set |
| MCP / assistant / reports | Every PR tool and the SF report learn a third value | One new registry entry each, like the price tag request |
| Cost | Fewer new files, many risky edits in shared PR code | More new files; shared pieces reused, PR-only pieces (approval page, view link) made generic once |

Recommendation (b): the new form IS the existing OCN record. A salesperson raises one by hand, the
amendment flow keeps auto-drafting one, and both go through the same approval + SLA. Its approval is
what finally sets `approver_id`, which unblocks amendment publishing. "One form, not two" is the same
call the sponsorship project link made (`alembic/versions/315_sponsorship_project_link.py`).

## 2. Rules in plain words

- **Who raises it:** a salesperson (or project sales admin) from the CRM, and a contact from the portal
  (same kinds as PR/SF), after an order is received, whenever something in it changes. The amendment
  flow on a published project SO also creates one (prefilled, status Draft) for the salesperson to send.
- **What it holds:** date, customer (searchable picker; free text kept as the display fallback like the
  PR), customer PO no. (free text), SO no. (free text), project (optional picker), C.S. in charge,
  sales in charge (user pickers), type of change (one of four), the risk level of that type (shown,
  read-only), affected lines (Q3), description, Customer Service comment, Purchasing comment,
  attachments (revised customer PO etc.), management decision + remarks.
- **Life:** Draft -> Submitted -> Pending approval -> Approved -> Done. Submitted can be sent back
  (rejected to the raiser, who amends and resubmits). Pending approval -> Rejected (amend and
  resubmit). Approved is locked; an explicit "Revise" unlocks it and starts a new revision (revision
  fence, same as PR). Void ends it from any open state, with a reason.
- **Who does what:**
  - Raiser: fills and submits; amends after a rejection; may void their own.
  - Project Sales Admin (main stage): checks it, sends it for approval or sends it back.
  - Customer Service: writes the CS comment (before the decision) and, after approval, carries the
    change out and marks it Done.
  - Purchasing: writes the Purchasing comment (did stock arrive, can the supplier PO be cancelled or
    pulled in) before the decision.
  - Management (approval stage, the PR's Project Sales Manager tier, default approver in settings like
    the PR): approves or rejects, with remarks; can also approve from the public approval link.
- **What an OCN does NOT do:** it never edits the sales order, the PO or AutoCount. It is a record +
  approval + SLA + notifications. (The project SO amendment publish stays its own button; it only
  checks that its OCN is approved.)
- **Who may see it:** holders of `procurement.order_change_notices.view` see all of their company;
  `view_own` sees the ones they raised or are named on (sales / C.S. in charge); the SLA assignee of a
  stage sees it; portal contacts see their own (same own-scope as PR/SF, `api/v1/_request_own_scope.py`).

## 3. SLA stages (copied from PR/SF + the two the paper form implies)

Seeded by one idempotent migration that copies the live PR rows (same policy shape, agent, notify flags,
team sets), like `npasla_0001`; a no-op where PR rows are missing. Hours come from a new
`ORDER_CHANGE_NOTICE` policy copied from `PURCHASE_REQUEST` tiers: 24 h / 72 h / 24 h.

| Stage (team set)             | Who                        | Starts on          | Response clock stops on | Resolves on                                 |
|------------------------------|----------------------------|--------------------|-------------------------|---------------------------------------------|
| main (`project_sales`)       | Project Sales Admin        | submit             | -                       | send_for_approval, reject_submitted, voided |
| cs_review (`ocn_cs_review`, see below) NEW, d1 | Customer Service | submit | - | cs_comment, voided   |
| purchasing (`purchasing`, agent `lead_time_enquiries`) NEW, d1 | Purchasing | submit | - | purchasing_comment, voided |
| project_sales_manager        | Management (default approver first) | send_for_approval | -          | approved, approval_rejected, voided         |
| customer_service             | Customer Service           | approved           | -                       | resolved (Done), voided                     |

This table is crew's d1 recommendation (both comment steps in parallel on submit; Send for approval waits
for both comments). Customer Service then appears twice on one record. Stage identity is (type, team set)
(`form_sla_service.py:880`) and several config lookups take `.first()` by that pair (`:771`, `:269`), so two
rows on the same `customer_service` team set would let a late CS comment resolve the after-approval stage.
The CS check therefore gets its own team set code `ocn_cs_review`: the seed copies the existing
`customer_service` tier -> team rows of the `purchase_request` agent under that code (same teams, same
members, no new team). Purchasing stage hours (crew dump 2, 12 Nov prod clone): the SI and NPA purchasing rows both use agent
`lead_time_enquiries`, team set `purchasing`, policy `NORMAL` = tier 1 Executive 72 h, tier 2 Manager 24 h,
tier 3 Director 24 h (teams: Purchasing - Product, Stock Inquiry / Purchasing Manager / Retail Director).
The OCN purchasing row copies the SI purchasing row as is (same agent, team set, policy), like
`npasla_0001` did; the other OCN rows use the new `ORDER_CHANGE_NOTICE` policy (24 / 72 / 24 h).

## 4. Worked examples (masked shapes)

1. **Exchange, delivered stock to collect back.** Customer `Customer A`, PO `XT04/3871`, type Exchange
   (High). Line: `ABC123-RL` 842 sets -> `ABC123-SH` 842 sets; 12 already delivered, to collect back.
   CS comment: collection booked. Purchasing: supplier PO for 830 sets can be switched. Management
   approves. CS marks Done. SO / PO untouched by the OCN.
2. **Quantity cut filed as Cancellation.** `Customer B Sdn Bhd`, PO `300/4800002913`, type Cancellation
   (Highest). Line: `XYZ456A-SS` 976 -> 956 sets. Purchasing: 20 sets already arrived, cannot cancel.
   Management rejects with remark "agree penalty charge first"; the raiser amends and resubmits.
3. **Advance.** `Customer C`, delivery date 15/01/2027 -> 20/12/2026, type Advance (Low). Purchasing:
   material can be pulled in. Approved.
4. **Delay.** `Customer D`, new date 30/03/2027, type Delay (Low). CS comment: let the stock go to another
   project. Approved, Done.
5. **Revised customer PO.** PO `XT04/3871 (R1)`, attachment = revised PO, type Exchange. If the project
   has a published project SO, its amendment already drafted this OCN with the change table filled; the
   salesperson checks and submits it.

## 5. Edge cases

- **Line already delivered:** allowed; the line shows "delivered" qty as information; nothing is blocked.
- **Two OCNs on one PO:** allowed; each is its own record; the list filters by PO no.
- **OCN on a PO revision:** PO no. is free text, so `XT04/3871 (R1)` is just its value; the attachment
  carries the revised PO.
- **No project:** allowed (Q5); it does not show on any project page until someone picks one.
- **Approved OCN changed afterwards:** locked; "Revise" opens a new revision, voids the open stages,
  restarts the chain at submit; the revision fence refuses a stale tab (`require_current_revision`).
- **Cancelled / voided PO or SO:** the OCN does not follow it; it stays as a record (project FK becomes
  ON DELETE SET NULL; today it is CASCADE, so deleting a project deletes its OCNs).
- **Amendment-drafted OCN rejected:** the amendment cannot publish (unchanged rule); the salesperson
  amends the OCN and resubmits.

## 6. Data fields, numbering, permissions, notices

- Additive migration on `projects.order_change_notices`: status, change_type, description, customer
  (id + text), customer PO no., SO no. text, C.S. / sales in charge (user ids), CS comment, purchasing
  comment, decision remarks, submitted/sent/decided/done/voided at+by, void reason, revision, source
  (crm / portal / amendment), requested-by contact; `project_id` nullable + ON DELETE SET NULL; new
  `order_change_notice_lines` (product picker, qty before/after, date before/after, delivered qty,
  remark). Existing amendment rows get status Draft (count to be measured by crew before the migration).
- Change types: an admin-editable lookup seeded with the four paper types + risk level (Q1, Q2).
- **Numbering:** `document_numbering_rules` row `order_change_notice`, `OCN{yy}-`, 4 digits, yearly,
  per company, like PR/SF; the amendment flow's own fallback (`OCN-` + digits) then stops being used.
- **Permissions:** `procurement.order_change_notices.{view, view_own, create, edit, delete, approve,
  report}`, granted to the same roles that hold the matching PR slugs (migration copies the grants).
- **Notices** (only when the receiver has something to do): stage assignee on each stage start
  (SLA assignment notice), escalation on overdue, raiser on reject / approve / done / void, the public
  approval link to the approver; same channels and templates as PR.
- **Menu:** Procurement > Order Change Notices (next to Sponsorship Forms); project page panel via the
  PROJECT-RELATED-RECORDS plug-in; `GET /projects/{id}/order-change-notices` in the sponsorships shape.

## 7. Questions (at most 5)

1. **Types.** (a) exactly the four paper types as an admin-editable lookup; (b) add a fifth "Quantity
   change / Other". Recommendation (a): the sample filed a quantity cut under Cancellation, and the
   amendment's own verbs (`QTY_CHANGE`, `CANCEL_BALANCE`) map onto the four; admins can add one later.
2. **Risk.** (a) show the Sheet2 risk (Highest / High / Low / Low) and the guide text on the form, no
   routing; (b) also route by it (e.g. Highest skips straight to Director, or a shorter SLA).
   Recommendation (a): nothing in PR/SF routes by a field today; route only if the owner says so.
3. **Lines.** (a) one free-text description like the paper; (b) structured lines (product, qty
   before/after, date before/after, delivered qty) plus the description. Recommendation (b): purchasing
   answers "stock arrived / can the supplier PO be cancelled" per item, the amendment flow already has
   the change table per line, and lines use the shared line table (standing rule).
4. **Comment stages (now owner decision d1, see section 8).** The paper puts the CS and Purchasing comments ABOVE the management block.
   (a) CS and Purchasing each get a comment stage that starts on submit, in parallel with the admin
   check, and Send for approval stays allowed before they answer (management sees a blank comment);
   (b) the same, but Send for approval waits for both comments; (c) no comment stages: only Purchasing
   gets one, and CS keeps just the after-approval stage (CS comment stays an optional field).
   Recommendation (c): it adds the one stage the risk guide demands (purchasing must check stock and
   the supplier PO), keeps the PR's three stages exactly, avoids two CS stages on one record, and
   invents no new refusal.
5. **Link.** (a) project optional, with an admin switch "OCN requires a project" (off by default), the
   same switch the sample request has (`models/user.py:477` `sample_request_require_project`,
   `services/sample_request_service.py:346`); PO and SO as free text; (b) project always required;
   (c) also pick the project SO / PO record. Recommendation (a), plus: an OCN that came from an
   amendment keeps the SO / PO link it was born with (read-only). Neither example has an SO no. and the
   PO is the customer's own text. (Checked: the sponsorship form has NO "required for flagged contacts"
   rule; its project is plain optional, `alembic/versions/315_sponsorship_project_link.py:30`.)

## 8. Crew answers on v1 (12 Nov, from owner rulings) and what is still open

Settled: (1) option (b), own form on `projects.order_change_notices`; the PR's approval, SLA, revise and
public approval link pieces are made SHARED once, never copied; PR / SF screens untouched. (2) layout and
buttons = PR (header on top, searchable customer, shared attachments, status chip, rejected = amend and
resubmit, approved = locked, explicit Revise). (3) Q1 (a) the four paper types, admin-editable; a quantity
cut is a Cancellation. (4) Q2 (a) risk + guide text shown, no routing. (5) Q3 (b) shared line table,
product from the product list, qty and date before/after, delivered qty, plus description. (6) Q5 (a)
project optional + setting "OCN requires a project" (off); PO / SO no. typed; an amendment-born OCN keeps
its links read-only; never link by matching PO text. (7) Management = the PR approval stage (Project Sales
Manager, Director escalation), default approver in settings. (8) own `ORDER_CHANGE_NOTICE` policy copied
from PR tiers 24 / 72 / 24 h, editable. (9) raised in CRM and portal, identical form; staff = view + action
buttons. (10) the OCN never edits SO, PO or AutoCount; a project SO changes only through its amendment,
which alone writes AutoCount on publish. (11) open items unchanged (SO changes wait for CS). (12) every
action in History on the shared component. (13) notices only to whoever must act, PR channels.
(14) `OCN{yy}-` 4 digits yearly per company; menu next to Sponsorship Forms; project FK ON DELETE SET NULL;
dates dd/mm/yyyy.

**One change, one notice (mock frame 5).** The amendment dialog (`AmendmentCreateDialog.tsx`) gains one
clearable searchable field "Order change notice": default "Draft a new notice from this change" (today's
behaviour, `project_so_delta_service.py:728`), or a person picks one of this project's notices not yet
linked to another amendment. Picked = no second notice; `so_amendments.ocn_id` points at it. Nothing is
linked by PO text. The notice's own lines stay as written; the linked amendment's change rows show beside
them read-only. A hand-raised notice never creates an amendment.

Open, with the owner now:
- **d1** CS and Purchasing comments before approval. Crew recommends: both steps start in parallel on
  submit, and Send for approval waits for both comments (refused with a plain reason naming the missing
  comment). Drawn that way in mock v2 (tag d1).
- **d2** amendment publish waits for its OCN's approval. Crew recommends yes; that is today's rule
  (`project_so_delta_service.py:791`), and the OCN's approval becomes what sets `approver_id` /
  `approved_at`. Drawn in mock v2 frame 5 (tag d2).
- Data (answered, 12 Nov prod clone): `projects.order_change_notices` has 0 rows, so the migration
  backfills nothing; `projects.so_amendments` has 2 rows, both published with no OCN (they predate or
  bypassed the OCN gate) and are left as they are.
