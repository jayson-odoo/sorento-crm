# Behaviour card: MY REQUESTS opens the staff pages, only theirs on the server (PORTAL-P4-REQUESTS, 28 Oct 2026)

Owner, 28 Oct ~14:1x: option (b), hold #1944 until MY REQUESTS opens the staff pages ("the view need to reuse our
system component"). Owner requirement, 28 Oct ~14:2x: the end-to-end flow of every submission works exactly like the
portal for all 4 forms; only create / save as draft / submit move to the staff pages; everything after submit behaves
as today. Plan: `PLAN-portal-p4-requests-28oct.md`. Names below are stand-ins (public repo); record numbers are real
(dev copy `sorento_cagent_stack`, 15 Oct).

**Owner answers (28 Oct ~14:3x, relayed by crew):** Q1 (a) submitter contact only. Q2 (a) portal action set only.
Q3 (a) same staff columns and filters; the grid rules are fixed on all grids for everyone. Q4 (a), but revisions follow
the per-form revision setting for every form, complaint included, exactly as the portal does (setting and values:
crew-note on #1953). Q5 (c): all 9 MY REQUESTS kinds in this lane, no embedded portal view left in the CRM; Project
Registration opens the PROJECT-REGISTER-V2 page. The 5 extra kinds go to card v1.1 before they are built.

## The rule, in plain words

A salesperson opens MY REQUESTS > Stock Inquiry, Complaint, Purchase Request or Sponsorship Form and lands on the SAME
list, detail and new pages staff use. The server returns only their own requests: rows their WhatsApp contact
submitted (`contact_id` = their linked contact), exactly the rows the portal shows them today
(BE `app/services/portal_service.py:852-856, 881-885, 915-919`). Another person's request is "not found".

Create, Save as draft, Submit, Revise, comments and attachments run through the portal's own code
(`create_or_update_draft` PS:1042-1087, `submit_draft` PS:1089-1285, `portal_revision_service.revise` PRS:1507-1685),
called from the CRM with the salesperson's session instead of a portal link. So status, numbering, SLA start,
notifications, "Resubmitted" and revision history are the portal's, by construction. Staff create is NOT reused:
it differs from the portal on every form (Stock Inquiry starts at `new` with no SLA, `procurement_service.py:6321-6343`;
Purchase Request / Sponsorship has no submit at all; Complaint gets no number and no draft, `complaints_service.py:1706-1763`).

After submit nothing changes: staff approve, reject and process exactly as today; the reject message still goes out.

## What the salesperson sees

| Where | Staff today | Salesperson after |
| --- | --- | --- |
| Sidebar MY REQUESTS > form | `/my-requests?type=<kind>` (embedded portal list) | the staff list page of that form |
| List rows | every row (routes pass no contact, e.g. `stock_inquiries.py:78-79`) | own rows only, drafts included |
| List columns / filters | as today | same columns and filters as staff (Q3) |
| Create button | ungated (`StockInquiriesList.tsx:442`, `PurchaseRequestsList.tsx:457`, `ComplaintsList.tsx:387`) | shown; opens the staff New page with Save as draft + Submit |
| New / Edit page | staff form | same staff form; staff-only fields hidden (below); requestor picker lists what the portal lists (`/requestor-options`, `portal.py:787-798`), frozen on revise |
| Detail page | staff detail | same page; status, responses, comments tab, attachments, revision history visible; portal actions only (Q2) |
| Bulk delete, staff workflow buttons | ungated or slug-gated | hidden; the server refuses them for a salesperson |

Staff-only fields hidden from a salesperson: Stock Inquiry purchasing response edit (`StockInquiryForm.tsx:449-471`);
Complaint "Technical Team" card: contact / space id inputs, root cause, resolution, technical response
(`ComplaintForm.tsx:927-1048`; read-only once staff fill them, as the portal shows responses); status and assignee
are never inputs on the staff forms. Staff-only actions hidden: Approve / Reject / Process / Close / Void / Reopen /
Reassign (already slug-gated; a salesperson holds none of those slugs), plus the ungated ones: Update & Reply,
Escalate / Extend SLA, Chat records, Copy approval link, Edit and Delete outside the portal's own rules.

What the salesperson can do = what the portal lets them do today: edit a draft or a rejected request, delete only a
draft (PS:1391-1403, 1505-1517), submit, revise a responded / processed Stock Inquiry, Purchase Request or
Sponsorship Form (Complaint has no revision in the portal, PRS:624-629, Q4), comment, add attachments, duplicate into
a new request (`?from=`, portal `SubmissionForm.tsx:821-845`).

Staff: no change. Admin / superadmin: no change.

## Real examples (dev copy, 15 Oct)

1. Salesperson A (roles salesperson + portal user) submitted 18 stock inquiries, 49 complaints, 7 purchase requests,
   7 sponsorship forms out of 89 / 366 / 58 / 107. MY REQUESTS > Complaint shows their 49 (latest CMP26-0357,
   submitted), not 366. SI26-0184 (responded) shows a Revise action; PR26-0374 (processed by CS) too.
2. PSSF26-0410 was submitted by Salesperson B with Salesperson C as the requestor (13 PR / SF rows are like this).
   Under the portal rule only B sees it; C does not (Q1).
3. A project sales coordinator's contact submitted 34 complaints and SI26-0147 through the portal. They are staff
   (another role, `phone_signin_service.py:302-309`), so nothing changes for them: staff menu, full lists where they
   hold `.view`, portal for the rest.
4. Salesperson D has 7 stock inquiries and nothing else: MY REQUESTS > Complaint opens the staff list with the empty
   state and a Create button.
5. 4 purchase requests are portal drafts today. Staff lists already show other people's portal drafts (no draft
   filter, `procurement_service.py:9129-9183`); a salesperson sees only their own drafts.

## End-to-end flows the proof drives (owner requirement), per form

1. Happy: create -> save as draft -> submit -> each approval step of that form's SLA config (`form_sla_configs`,
   `form_sla_service.py:359-366`) done by a staff approver -> approved / responded.
2. Reject -> salesperson edits and resubmits -> status Resubmitted + audit trail headings as #1942 -> approved.
3. Notifications at each step asserted as records, never sent: `notifications` + `notification_deliveries`,
   `conversation_sla_tracking`, `integration_log` for the Respond.io message, `audit_logs`, `portal_form_revisions`.
4. Revision: revise a responded request, revision history visible (Stock Inquiry, Purchase Request, Sponsorship).
5. Comments, responses, status and revision history visible to the salesperson on the CRM detail page.

Proof: one API-level pytest per form through these states (red first), plus the browser pass on the crew copy
walking flows 1-2 for Stock Inquiry and Complaint as the salesperson and as an admin impersonating them, with the
approver side done by a staff approver, comparing each step's visible items with the portal on the same record.

## Edge cases

- Impersonation: an admin viewing as a salesperson calls the API as that salesperson (`X-Impersonate-User-Id`,
  `dependencies.py:182-238`), so they see exactly the salesperson's rows and create in their name. If the
  impersonation session has ended, the server falls back to the admin, who sees the full staff page.
- A contact without a CRM user keeps the portal byte for byte.
- A WhatsApp rejection link (`submission_link`, `procurement_service.py:7057-7062`) opened by a salesperson opens the
  CRM detail page of that request (P3 Q5 (b)).
- Space: all 620 dev rows carry one space and no contact has two (query); the CRM matches on the contact and stamps
  the contact's workspace space on create, as impersonation does (`contact_impersonation.py:69-88`).
- A salesperson typing another request's URL: "not found" (404), never the row.
- Pre-existing, not closed here for staff (P3 Q4 accepted gap): staff PUT / DELETE / bulk delete on these 4 forms need
  sign-in only and PUT accepts `contact_id` / `space_id` / `status` (`stock_inquiries.py:457-467, 785-794`;
  `schemas/procurement.py:1357-1358`; `schemas/complaints.py:214-217`). For a salesperson these routes refuse.

## Questions (recommendation first)

**Q1. Whose requests are "theirs"?**
(a) Rows their contact submitted, exactly the portal's rule (PSSF26-0410 shows to B only). (b) Also rows that name
them as the requestor (C sees PSSF26-0410 and can act on it).
Recommendation: (a), because the owner asked for "exactly like the portal"; (b) is new behaviour and can come later.

**Q2. Which actions does the salesperson get on the CRM detail page?**
(a) Exactly the portal's set: edit / delete a draft, submit, revise, comment, attach, duplicate; every staff action
hidden, including PDF download, Copy view link, Escalate and Extend SLA. (b) (a) plus the read-only staff extras: PDF
download and Copy view link.
Recommendation: (a), the portal's set and nothing else.

**Q3. The list grid for a salesperson.**
(a) The same staff columns and filters (Assigned To, Handled By, Print Count included), with your grid rules fixed for
all 4 grids for everyone: every column sortable on the server (today Purchase Request / Sponsorship sorts 5 keys,
`procurement_service.py:9208-9215`; Complaint 8, `complaints_service.py:504-514`) and every dropdown filter
multi-select (Purchase Request / Sponsorship filters are single-select, `PurchaseRequestsList.tsx:495-540`).
(b) Hide the staff-only columns and filters (Assigned To, Handled By, Print Count) from a salesperson.
Recommendation: (a), one view, and seeing who handles their request helps them. Row select like Odoo already ships
on every grid (#1927).

**Q4. Complaint revision.**
The portal has no revision for complaints today (revise answers 422, `portal_revision_service.py:624-629, 1522-1524`;
no Revisions tab on staff complaint pages).
(a) Same as the portal: no complaint revision; a rejected complaint is edited and resubmitted. (b) Build complaint
revision in this lane.
Recommendation: (a), "exactly like the portal".

**Q5. The other MY REQUESTS kinds.**
MY REQUESTS also lists Project Registration, Sample Request, New Product Application, Price Tag Request and Sales
Opportunity (`config/menu.config.tsx:66-89`); this lane moves only the 4 forms.
(a) Those 5 keep the embedded portal page until their own lanes. (b) Hide those 5 from the CRM sidebar until their
lanes (salespeople use the portal link for them). (c) Take all 9 in this lane.
Recommendation: (a), so a salesperson loses nothing, and #1944 + this lane can ship.

---

# v1.1: the 5 extra MY REQUESTS kinds (Q5 (c)) and the revision setting (Q4)

Same rule as v1 for every kind: MY REQUESTS > kind opens a CRM page, the server returns only the salesperson's own rows
(their contact, or for sample requests / NPA also "them" as the salesperson / applicant, the P2 rule), staff pages and
staff routes are read-only for a salesperson, and their own create / draft / submit / revise run the SAME code the
portal runs, called from the CRM session. Staff: no change. Paths: BE `sorento_crm_backend/app`, FE
`sorento_crm_frontend/app/(protected)`.

| Kind | CRM page today | Only theirs on the server today | Portal flow (what must stay identical) | Gaps | Effort |
| --- | --- | --- | --- | --- | --- |
| Sample Request | list / new / detail / edit `project-sales/sample-requests` | yes, `view_own` (P2): salesperson OR contact (`sample_request_service.py:620-625`); detail 404 | own router `public/portal_sample_request.py`: draft, submit, cancel; customer picker = own agents' customers; no revise / comments / attachments | grants (`view_own` + `.create`); staff create stamps `source=staff`, no contact (`sample_requests.py:170`) so the CRM path must stamp like the portal and run its customer / project checks; list shows all statuses like the portal | M |
| New Product Application | list / new / detail / edit `procurement-management/new-product-applications` | yes, `view_own` (P2): applicant OR contact; detail 404 | own router `public/portal_new_product_application.py`: draft, submit, revise, cancel, "start from" an own responded stock inquiry, uploads | grants (`view_own` + `.create`); menu gate lacks `view_own` (`menu.config.tsx:439-444`); staff detail shows item group, base UOM, list price the portal hides (`new_product_applications.py:152`; `new_product_application_service.py:947, 1001`): hidden for a salesperson; portal-raised rows answer 409 on the staff edit (`:292-298`), so the salesperson edits through the portal code | L |
| Sales Opportunity | list + create modal + inline edit `sales/opportunities` | yes, `view_own` (P2): own agents; detail 404 | own router `public/portal_sales_opportunity.py`: create (default agent when the customer has none, `:202-204`), update stage / lost reason; no draft or submit | grants (`view_own` + `.add` + `.edit`); a prospect with no agent gets 403 on the staff path (`opportunities.py:57-81`): the CRM path assigns the portal's default agent; agent picker, Won-to-sales-order link and Delete hidden for a salesperson | M- |
| Price Tag Request | list + detail + designer `dealer-kit/price-tag-requests`; NO staff new / edit page, no staff create API (`price_tag_requests.py:159-1422`) | no: list / detail need `.view` and return everyone (`:168-184, 250-259`); no `view_own` slug | own router `public/portal_price_tag.py`, logic in route bodies: draft (number at draft time), submit (`emit_form_event` + notify + auto-assign, `:431-503`), proof approve / request changes / review comments / collect (`:507-635`), revise (adapter exists, setting OFF on dev), debtor picker (multi-agent) | new slug `dealer_kit.price_tag_requests.view_own` + guard; move the route bodies into a service so portal and CRM run one code; new / edit page = the existing price tag request form (`(auth)/portal/components/PriceTagRequestForm.tsx`, the only form there is, Q8) on a CRM client; staff detail gains the portal action set for the salesperson | L |
| Project Registration | `/project-sales/new` = staff ProjectForm, being rebuilt by lane PROJECT-REGISTER-V2 (needs `projects.projects.edit` today) | yes for projects, `view_own` (P2), pipeline; drafts never show on staff routes | generic portal code: draft, submit to pending / resubmitted, approvers notified, approve draws the code (`project_registration_service.py:591-770, 910-972`) | owner already ruled: opens the REGISTER-V2 page. REGISTER-V2 proposes (its card Q7, pending): a new slug `projects.registrations.submit` (P4 defines and grants it in `pp4_0001`), the salesperson's submit goes to `approval_state=pending` and the existing approve / reject / notify run unchanged, registrations seen in the Projects pipeline under MY WORK (menu gate needs `view_own`, `menu.config.tsx:192-196`); draft and resubmit from that form are its open items | S here (link, slug, grant, menu gate); form in REGISTER-V2 |

Revision setting (Q4 answer, crew-note on #1953): User Management > Settings > Portal revisions, one row per form
(`portal_revision_configs`, `models/portal.py:138-163`) plus a global switch and cap (`system_settings`). A form is
revisable only with revision code AND its row on AND the global switch on (`portal_revision_service.py:745-754`). Dev
(15 Oct): Stock Inquiry ON, Complaint ON but it has no revision code so it does nothing (portal revise answers 422),
Purchase Request / Sponsorship / Price Tag OFF. Sample Request, NPA (own Revise move), Project Registration, Sales
Opportunity are not on that page (`forms/revision_configs.py:38-59`). The CRM follows the setting exactly because it
runs the same code.

## Real examples (dev copy, 15 Oct)

1. Price tag requests: 18 rows from 3 contacts. Today a salesperson granted `.view` would see all 18. After P4 each
   of the 3 sees only their own, and Salesperson A (from example 1 above) sees an empty list with a Create button.
2. New product applications: 15 rows, 8 raised from the portal; Salesperson A raised 7. On the staff detail today those
   7 show item group, base UOM and list price; after P4, as the salesperson, they do not.
3. Sample requests: 1 row (portal). Sales opportunities: none on the 15 Oct copy. The hand test seeds one of each on
   the crew copy through the portal first, then compares with the CRM page.

## Questions (recommendation first)

**Q6. Complaint revision.** Its switch on the settings page shows ON but does nothing (no revision code).
(a) Build complaint revision code (adapter: which fields freeze, restart stage) so the setting really governs
complaints, in the portal and in the CRM alike. (b) Keep complaint without revision and take it off the settings page
so the switch no longer misleads.
Recommendation: (a), because you asked that revisions follow the setting for every form, complaint included.

**Q7. MY REQUESTS > Project Registration until PROJECT-REGISTER-V2 merges.**
The REGISTER-V2 page is not built yet; today `/project-sales/new` needs `projects.projects.edit`, which a salesperson
must not get (it opens the staff register path).
(a) The item is hidden for salespeople until REGISTER-V2 merges; REGISTER-V2 switches it on with its page (P4 ships the
slug and grant). (b) P4 ships the item pointing at `/project-sales/new` now; it shows "no access" until REGISTER-V2
merges.
Recommendation: (a), never a link that fails.

**Q8. Price tag request form in the CRM.** There is no staff form; the only form is the portal's.
(a) The CRM new / edit page renders the existing price tag request form component on a CRM-session client, and the
portal route bodies move into one service both call (one code, exactly the portal's flow). (b) Build a new staff-style
price tag form.
Recommendation: (a), reuse, never reinvent; (b) duplicates 3,800 lines of form logic.

---

# v1.2 (28 Oct, after the owner's v1.1 answers)

**Owner answers to v1.1 (~14:4x, relayed by crew):**
- Q6 (a): build the complaint revision code, so the per-form setting governs complaints in the portal and the CRM.
- Q7: "the Project registration page should be merged with the Project page, should just have 1 project page". So
  there is no MY REQUESTS > Project Registration. A salesperson registers from MY WORK > Projects (Register, which is
  PROJECT-REGISTER-V2's form, with Save draft + Submit for approval). Their own registrations show in that Projects
  list. P4 keeps only the `projects.registrations.submit` slug + grant (agreed with that lane). **8 kinds remain.**
- Q8: reuse the Dealer Kit > Room Designer > Price Tag Requests table and request page.

**What changes that the owner should know (Q8 re-check, crew-note on #1953 6462546044):**
- The Dealer Kit price tag pages are a table, a request page and a designer. There is no create / edit form and no staff create API.
- So for a salesperson, New and Edit price tag request = the staff request page in edit mode: fields become inputs in
  place, the same layout as view (CLAUDE.md "View and Edit are the SAME layout"). Not the portal's form.
- Save / submit / approve proof / request changes / collect / revise run the portal's code, moved into one service.
- Effort stays L.

**Effort now, 8 kinds:**
| Kind | Effort |
| --- | --- |
| Stock Inquiry, Complaint, Purchase Request, Sponsorship, shared server piece | L (in build) |
| Complaint revision code (Q6) | M |
| Sample Request | M |
| New Product Application | L |
| Sales Opportunity | M- |
| Price Tag Request | L |

All in one PR (#1953), merged after #1944.
