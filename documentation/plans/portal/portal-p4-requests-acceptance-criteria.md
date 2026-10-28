# UAC: PORTAL-P4-REQUESTS (28 Oct 2026)

Plan: `PLAN-portal-p4-requests-28oct.md`. Card: `CARD-portal-p4-requests-28oct.md`. Status: DRAFT, items marked
(Qn) follow the owner's answer to that card question.

"Salesperson" = P3 salesperson view (`phone_signin_service.py:302-309`). "Form" = Stock Inquiry, Complaint,
Purchase Request, Sponsorship Form. "Theirs" = `contact_id` = their linked contact (Q1).

## Server scope

- P4-1 A salesperson's staff list of a form returns only their own rows, drafts included; total matches the portal
  list for the same contact.
- P4-2 A salesperson's staff detail (and revisions) of another contact's row answers 404, never the row.
- P4-3 Every other staff route of the 4 forms (PUT, DELETE, bulk delete, update-and-reply, attachments link /
  unlink, workflow actions, conversation, view-link, export) answers 403 for a salesperson.
- P4-4 Staff holding `.view`, admin and superadmin: list, detail and every action unchanged (same rows, same
  responses as before).
- P4-5 A salesperson with no linked contact sees no rows and cannot create.
- P4-6 Form comments: a salesperson reads and posts comments on their own row; on a foreign row 404.
- P4-7 Migration is insert-only: 4 `view_own` slugs; role `salesperson` granted the 4 `view_own` + 4 `.add`;
  downgrade removes exactly those.

## Write path = the portal's

- P4-10 Create from the CRM lands as a draft stamped with their contact and their workspace space, identical
  columns to a portal draft of the same payload (status, `portal_draft_at`, number rules, `source`).
- P4-11 Save as draft, delete draft (drafts only), edit (draft or rejected only) follow the portal rules
  (`portal_service.py:1391-1403, 1505-1517`).
- P4-12 Submit from the CRM produces the same status, number, `portal_form_revisions` row, SLA tracker
  (`conversation_sla_tracking` per `form_sla_configs`), `notifications` + `notification_deliveries` and
  Respond.io / `integration_log` records as a portal submit of the same row.
- P4-13 Reject by a staff approver, then resubmit from the CRM: status `resubmitted`, audit trail headings
  "Rejected" / "Resubmitted" as #1942, then approve to the final state.
- P4-14 Revise a responded / processed Stock Inquiry, Purchase Request, Sponsorship Form from the CRM: revision row,
  `revision_no` bump, restart stage, requestor frozen; revision history visible. Complaint: no revise (Q4).
- P4-15 Requestor options in the CRM equal the portal's `/requestor-options` for the same contact.
- P4-16 Attachments added from the CRM appear on the row as portal uploads do; staff uploads cannot be removed by
  the salesperson.
- P4-17 Impersonation: an admin viewing as a salesperson gets P4-1 to P4-16 exactly as that salesperson; actions
  are recorded as the salesperson with the admin as the real user.

## Screens

- P4-20 MY REQUESTS > each of the 4 forms opens the staff list page; the embedded portal list no longer renders for
  those 4; `/my-requests?type=<one of 4>` and `/my-requests/<kind>/<id>` redirect to the staff list / detail.
- P4-21 Landing on a favourite among the 4 opens its staff list.
- P4-22 List: same columns and filters as staff (Q3); empty state for a salesperson with no rows; Create shown.
- P4-23 Every column of the 4 lists sorts on the server; every dropdown filter is multi-select (Q3).
- P4-24 New / Edit for a salesperson: staff-only fields hidden (Stock Inquiry purchasing response; Complaint
  technical team card); Save as draft + Submit; Duplicate (`?from=`) pre-fills a new draft.
- P4-25 Detail for a salesperson: the portal action set only (Q2); status, responses, comments, attachments and
  revision history visible; no staff action button.
- P4-26 Staff screens unchanged.
- P4-27 Usable at 375 px and 1280 px.
- P4-28 Other MY REQUESTS kinds (Q5).

## Proof

- API-level pytest per form driving flows 1-4 of the card (red first), asserting records, never sending.
- Browser pass on the crew copy: flows 1-2 for Stock Inquiry and Complaint as the salesperson and as an admin
  impersonating them, approver side by a staff approver, each step compared with the portal on the same record;
  admin and a contact without a CRM user spot-checked; 1280 and 375.
