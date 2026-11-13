# UAC: Order Change Notice (OCN-ORDER-CHANGE-NOTICE)

Source: approved card v3 + mock v3 (`CARD-ocn-order-change-notice-12nov.md`, `documentation/mockups/ocn/index.html`),
owner approval 13 Nov 00:01 ("ok put it under Project Sales Admin and make sure the form obey with our design
principle in sample request, ther est I am okay"). Each line is one test. Slice 1 = this PR; slice 2 = a
follow-up PR titled `OCN-ORDER-CHANGE-NOTICE B: ...`.

## A. Record and numbering (slice 1)

- **A1** Creating an OCN stores it on `projects.order_change_notices` with status `draft`, the creator as
  raiser, `source = crm`, the company of the request, and a number `OCN{yy}-NNNN` from the
  `order_change_notice` numbering rule (yearly, 4 digits, per company).
- **A2** Two companies each get their own sequence; the same number in two companies is allowed, the same
  number twice in one company is refused (existing `uq_ocn_number`).
- **A3** `project_id` is optional and `ON DELETE SET NULL`: deleting a project leaves its OCNs with no
  project (today it is CASCADE).
- **A4** With the setting "OCN requires a project" ON, submit without a project is refused with a plain
  message naming the field; OFF (default) it submits.
- **A5** Change type is one of the four seeded lookup rows (Advance Low, Exchange High, Cancellation
  Highest, Delay Low); the response carries the type's risk level and guide text; an inactive or
  unknown type is refused.
- **A6** Lines: each line has a catalogue product (product id required, no free-text product), qty
  before, qty after, date before, date after, delivered qty, remark; at least one line to submit.
  Quantities are never capped by stock.
- **A7** Customer is picked (customer id) with the typed name kept as display fallback; PO no. and SO no.
  are free text; nothing is linked by matching PO or SO text.

## B. Lifecycle = the purchase request chain (slice 1)

- **B1** Submit: draft -> submitted; emits `submit`; the `main` stage (team set `project_sales`) starts.
- **B2** Send for approval (sales admin): submitted -> pending_approval; emits `send_for_approval`; the
  `main` stage resolves and the `project_sales_manager` stage starts (default approver first when set
  and a member of the team set).
- **B3** Send back (reject submitted): submitted -> rejected with a reason; emits `reject_submitted`; the
  raiser can amend and resubmit (rejected -> submitted emits `submit` again).
- **B4** Approve: pending_approval -> approved; stamps `approver_id` and `approved_at`; emits `approved`;
  the approval stage resolves and the `customer_service` stage starts. Needs the approve permission.
- **B5** Reject (approval): pending_approval -> rejected with remarks; emits `approval_rejected`; amend and
  resubmit as B3.
- **B6** Done (CS): approved -> done with an optional CS comment; emits `resolved`; the
  `customer_service` stage resolves.
- **B7** Void with a reason from any open status (draft, submitted, pending_approval, approved);
  emits `voided`; every open stage is voided, not resolved.
- **B8** Approved is locked: edit is refused; "Revise" (explicit) unlocks it, bumps the revision, voids
  the open stages and returns it to draft; the approval stamp is cleared.
- **B9** Revision fence: a state change sent with a stale revision number is refused (409) for submit,
  send for approval, send back, approve, reject, done, void, revise.
- **B10** A transition from a wrong status is refused (409) with a plain message; nothing is emitted.
- **B11** Every transition and edit shows in History (shared audit trail): who, when, action, old -> new.

## C. SLA (slice 1)

- **C1** The seed migration creates policy `ORDER_CHANGE_NOTICE` with the PURCHASE_REQUEST tiers copied
  (24 / 72 / 24 h) and three `form_sla_configs` rows for `order_change_notice` copied from the
  `purchase_request` rows (main, project_sales_manager, customer_service): same agent, team sets,
  events, notify flags, advance-on.
- **C2** The seed is idempotent (run twice = same rows) and a no-op when no PR rows exist.
- **C3** `order_change_notice` is a form SLA type in every lockstep list (service tuple, schema literal,
  number source, detail link, stage action labels, tracker readers, FE source type).
- **C4** The SLA tab on the OCN page lists the stages of that OCN only.

## D. Permissions and scope (slice 1)

- **D1** Slugs `procurement.order_change_notices.{view, view_own, create, edit, process, delete, approve,
  report}` exist; the migration grants each to the roles that hold the matching purchase request slug
  (`edit` only from `purchase_requests.send_for_approval`, `process` from `purchase_requests.process`).
- **D2** Without `view` or `view_own`, list and detail are 403. With `view_own` only, the list shows only
  OCNs the user raised or is named on (sales in charge / C.S. in charge), and another's detail is 404.
- **D3** Approve / reject needs `.approve`; send for approval / send back needs `.edit`; done needs
  `.process` (CS); the permission is checked BEFORE a move is held for the undo window; the handling lock
  (`assert_can_act_on_form`) applies to every stage move. Ownership only narrows `.view_own`: being the raiser
  or named grants nothing without a slug; `.view`, `.edit`, `.process` and `.approve` see every notice (the
  people who act on others' notices, as on the PR); `.view_own` sees the ones raised by or naming the
  user. Conversation, SLA and History follow the same rule.
- **D4** Company scope: a user of company X never sees, opens or acts on company Y's OCN (404).

## E. Amendment link, one change one notice (slice 1, owner d2)

- **E1** Creating an amendment without an OCN pick drafts a new OCN exactly as today (prefilled change
  table, project, SO, PO links, `source = amendment`, status draft).
- **E2** Creating an amendment with an existing OCN id (same project, not linked to another amendment,
  visible to the author) links it and drafts no second OCN. Pickable: draft, submitted, resubmitted,
  rejected, approved; picking an approved OCN revises it back to draft first, so the change is approved
  before publish (lead ruling on the security review). Pending approval, voided, done, another project's
  or an already linked OCN is refused, and the dialog lists only pickable ones.
- **E3** Publishing an amendment is refused until its OCN is approved (status approved); after approval
  it publishes. A voided or rejected OCN keeps it refused.
- **E4** An amendment-born OCN shows its project, SO and PO links read-only; edit cannot change them.

## F. Project page and list (slice 1)

- **F1** `GET /projects/{id}/order-change-notices` returns that project's OCNs in the sponsorships shape,
  newest first, gated by OCN view permission.
- **F2** The OCN list endpoint sorts server-side on every column and filters status, type, risk as
  multi-select; pagination limit is capped (global guard test).

## G. Frontend (slice 1)

- **G1** Sidebar: "Order Change Notices" under Project Sales Admin, after Sponsorship Forms, gated by
  `.view` / `.view_own`.
- **G2** List: standard DataGrid, one toolbar row (Search, Filters, Columns, Create), single-line rows,
  columns OCN no., Date, Customer, Customer PO no., Type, Risk, Project, Sales in charge, Status, every
  column sortable; row click opens the record; no action column.
- **G3** Form: the sample request document shell (one bordered card, kind badge + status pill, centred
  title, two-column field grid, line items with Add row, Cancel / Save as draft / Submit); Edit opens the
  same form; dates through the shared date picker and formatter (dd/mm/yyyy).
- **G4** Detail: record header (number + status pill, one subtitle, pager, one main button per status and
  permission), tabs Details / Conversation / SLA / History (Revisions comes with the portal in slice 2),
  attachments, the linked amendment's change rows read-only, CS comment block with empty
  state, sign-off block (decision, name, date, remarks).
- **G5** Usable at 375 px and 1280 px; no UUIDs on screen.

## I. Owner hand-test round 20 (13 Nov, findings #1 + #2; pulled forward from H1)

Finding #1 (owner, verbatim): "Ocn should be part of the portal forms right? And it shud appear in tags all
those places right for us to control the form by contact". Finding #2 (owner, verbatim): "the sales in charge is
the salesperson which default to the submitter but can be changed" + "I belive thats how requested by in other
forms work right?" (mirror the purchase request's Requested by).

- **I1** `order_change_notice` is ONE portal form kind, registered once per side: BE
  `GRANTABLE_PORTAL_FORM_TYPES` (portal_service.py) + `_KIND_LABELS` "Order Change Notice"; FE `LANDING_KINDS` /
  `LANDING_LABELS` (lib/portal-form-kinds.ts) + `MY_REQUEST_STAFF_PAGES`. No screen keeps its own list.
- **I2** It is opt-in like Sample Request / New Product Application: NOT in `SUPPORTED_TYPES` (the base). A contact
  sees it only when a tag, an active market segment or the contact's own switch turns it on; a contact switch Off
  hides it even when a tag / segment grants it.
- **I3** It appears, with the label "Order Change Notice", on: the contact's Portal forms card (GET
  /user-management/contacts/{id}/portal-forms row with inherited / override / effective), the contact tag card
  catalog (`portal_forms` options), the market segment editor's Additional portal forms, and PUT validation accepts
  it on all three (no 422 "unknown form type").
- **I4** CRM MY REQUESTS: the hand-added Order Change Notices item is gone; the item comes from the shared
  MY REQUESTS list (path /procurement-management/order-change-notices, permission
  `procurement.order_change_notices.view_own`) and shows only when the salesperson's resolved portal kinds include
  `order_change_notice` (same filter as every other MY REQUESTS form).
- **I5** Portal: GET/POST `/api/v1/public/portal/submissions/order_change_notice` (list / create),
  GET/PUT `.../{id}` (read / update), POST `.../{id}/submit`. Every route first checks the kind is visible for the
  token's contact (403 FORM_TYPE_NOT_VISIBLE otherwise). The raiser is the CRM user linked to the contact
  (`users.respond_contact_id`); a contact with no linked user gets 403 (the kind is a salesperson's form). The
  route builds the actor with `order_change_notice_service.actor_for_user(linked user)`, so the portal applies
  exactly the CRM rules (create grant, own-only list, edit / submit rules, company scope); another user's notice
  id is 404 (no existence leak). Portal lookups (customers, products, change types, projects) reuse the notice's
  own lookup functions under the same rules.
- **I6** Portal pages: list, new and detail for the kind at /portal/c/[slug]/order_change_notice (+ the legacy
  /portal/order_change_notice paths the other kinds have), rendering the SAME notice form component as the CRM
  (data calls injected, not a second form); the portal landing offers the kind in its selector like Sample
  Request.
- **I7** One salesperson field: "Sales Person" (read-only creator) and "Sales Incharge" (user picker) are removed
  from the form, detail, list and API; "Requested by" replaces them: `requested_by_contact_id` + `requested_by`
  text, picked with the shared `RequestorContactSelect`, saved through the shared
  `requestor_options_service.apply_requestor_contact` (422 REQUESTOR_NOT_ELIGIBLE for an ineligible contact; the
  label is the contact's current name), shown in the sign-off "Requested by" column like the purchase request.
  List column "Requested by" (sortable).
- **I8** Default: the submitter's contact (portal: the token's contact; CRM: the creating user's linked contact;
  empty when the user has no linked contact); anyone who may edit the notice may change it.
- **I9** Own-records (`view_own`): a notice is the user's when they created it, are its C.S. in charge, or are the
  user linked to its Requested-by contact (replaces "Sales in charge user").
- **I10** History reads "Requested by: old -> new" with names.

## H. Slice 2 (follow-up PR)

- **H1** Portal kind: pulled into slice 1 by the owner's hand test, see I1-I6.
- **H2** Public approval link and public view link work for an OCN (approval token generic).
- **H3** Print / PDF in the paper layout.
- **H4** Assistant / MCP: list and read OCNs, approve / reject tools, two eval prompts each.
- **H5** Report dataset.
