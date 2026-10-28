# Behaviour card: MY REQUESTS opens the staff pages, only theirs on the server (PORTAL-P4-REQUESTS, 28 Oct 2026)

Owner, 28 Oct ~14:1x: option (b), hold #1944 until MY REQUESTS opens the staff pages ("the view need to reuse our
system component"). Owner requirement, 28 Oct ~14:2x: the end-to-end flow of every submission works exactly like the
portal for all 4 forms; only create / save as draft / submit move to the staff pages; everything after submit behaves
as today. Plan: `PLAN-portal-p4-requests-28oct.md`. Names below are stand-ins (public repo); record numbers are real
(dev copy `sorento_cagent_stack`, 15 Oct).

**Owner answers:** pending.

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
