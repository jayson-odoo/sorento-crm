# PLAN: project stage buttons open their own form directly

Status: built, in review (PR #2345). Track: started as the small fix track; the sponsorship ruling
(crew answer, 11 Nov) added a staff write path, so it ran as a normal lane with a security review.
Lane: PROJECT-STAGE-ACTIONS. UAC: `project-stage-actions-acceptance-criteria.md`.

## Journey

A salesperson or admin on a project clicks the header's main stage button. When the stage needs
a document, the button takes them straight to that document's existing form. Cancel or Back from
that form returns to the project tab it belongs to.

## Measured before the lane (main a80d65fa)

- `ProjectDetailClient.tsx` `STAGE_FORM_ROUTE` maps rung key -> form route, fired only after a
  forward move lands: `specified` -> new quotation, `sample_submission` -> new sample request,
  `sponsorship_form` -> `/procurement-management/sponsorship-forms/new?project_id=`.
- `po_received` had no entry: the user had to open the PO tab and click "Upload a PO document"
  (`PurchaseOrdersPanel.tsx`, `POIntakeUploadDialog`).
- Two sponsorship forms existed. `PurchaseRequestForm` rendered the salesperson's (portal
  `SubmissionForm`, `NewOwnRequestForm` -> `MyRequestPortalForm`) only for a user limited to their
  own rows, and the free-text staff form (`StaffPurchaseRequestForm`) for everyone else, admins
  included. `/api/v1/my-requests` refuses a user holding `.view` and admin/superadmin by role.
- Cancel on the new sponsorship and new sample request pages went to the admin lists.

## Rulings

- Owner, 11 Nov: "it should be unified and use the sponsorship form salesperson is using";
  "after I click PO received supposed to directly give me the page of upload a PO document".
- Crew answer, 11 Nov (standing rule CRM forms = portal forms, 28 Oct): staff and admins see the
  SAME salesperson form component, prefilled from the project; `/my-requests` guard unchanged;
  staff save and submit through the staff endpoint, as the clicking user on behalf of the project
  salesperson; never the free-text staff form from a project; add a staff field if one is missing.

## Stage -> what opens

| Rung key | Opens |
| --- | --- |
| registered, quoted, tendering | nothing (no form for these) |
| specified (Spec In) | new proposal page (unchanged) |
| sample_submission | new sample request (unchanged); Cancel returns to the project's Samples Request tab |
| final_negotiation | nothing (no form) |
| sponsorship_form | the salesperson's sponsorship form for everyone, prefilled; Cancel and Submit return to the project's Sponsorship Form tab |
| po_received | the project's PO tab with "Upload a customer PO" open; Cancel leaves the PO tab |
| lost | the existing loss reason dialog (unchanged) |

## Design

1. PO received: `STAGE_FORM_ROUTE.po_received` -> `/project-sales/<id>?tab=orders&upload=po`;
   `PurchaseOrdersPanel` opens `POIntakeUploadDialog` once on `upload=po` and drops the param.
2. Back to the project: the new sponsorship / sample request pages send Cancel (and the
   sponsorship save) back to the project tab when opened with `project_id`.
3. Sponsorship, one form: `PurchaseRequestForm` renders the portal `SubmissionForm` for a new
   sponsorship form opened with a project, for staff too (`StaffProjectSponsorshipForm`), through
   `staffSponsorshipSubmissionClient`: Save draft = staff create / update; Submit = save, then the
   new `POST /purchase-requests/{id}/submit`; profile = the project salesperson's contact
   (projects now carry `owner_contact_id`), so Requested by defaults to them; lookups = the staff
   pickers. Salesperson and staff start from the same seed (`projectSponsorshipSeed`): project,
   title, customer, PIC, address, value. AI Extract is hidden for staff (no staff extract route).
4. `PortalService.submit_staff_request` runs the request branch of the portal submit for a staff
   draft (`source = manual`), and shares its tail (`_finish_submit`: number, history, notify,
   project feed, form SLA) with the portal submit so the two cannot drift.

5. Crew pass, 11 Nov (salesperson path + standing rules): a field the form starts with is shown
   even when its contact rule hides it (both paths show Registered project); the salesperson's
   project-started form has the staff path's Cancel / Submit destination and no AI Extract
   (`MyRequestPortalForm` `paths` / `aiExtract`); the staff client pre-selects each lookup's admin
   default through its `purchase_requests` binding (Sales type = Project), as the salesperson's
   does; the portal form's date fields use the shared DD/MM/YYYY `DatePicker`; the project
   Sponsorships tab and its rollup show the sponsored amount (the form's line Grand total), never
   `total_project_value` (the project's); a form opened from that tab goes Back to it (`?back=`,
   `BackToList originLabel`).
6. Security review: the staff submit takes only a staff-written draft (`source = manual`, no
   `portal_draft_at`) and clears any approval stamp set at create.

The clicking user is recorded by the audit log (the request actor); `purchase_requests` has no
`created_by` column. No new button: the staff submit is the existing form's Submit, so no assistant `ActionDef`
(cloud-lanes DoD line 7). No migration.

## Open

- The form's revision history row is keyed to the salesperson's contact (`portal_form_revisions`
  has no staff actor column); the audit log records the staff user. Naming staff there needs a
  migration: trigger = the owner asks for "submitted by X for Y" in the revision timeline.
- A new sponsorship form opened from the Sponsorship Forms list (not from a project) still shows
  the staff form for staff. Trigger to unify it too: owner confirms that list's Create should
  also be the salesperson form.
- Follow-up (crew pass 11 Nov, not this lane): per-line trash icons on the sponsorship form's
  items; the History tab shows "Line X removed" on a fresh submit.

## Round 3 (crew re-pass, 11 Nov)

- A salesperson's sample request started from a project: bottom Cancel returns to the project's
  Samples Request tab (`MyRequestClientProvider paths`), as the staff form's does.
- Requested by reads the contact's name on the new form too (`owner_contact_name`), as the saved
  form prints it.
- A saved form keeps showing the contact-gated field it holds a value for (Registered project).
- A request submitted without a date takes the submit day (Malaysia), so the tab's Requested is set.
- Both sample request forms' Request Delivery Date use the shared DD/MM/YYYY picker.

