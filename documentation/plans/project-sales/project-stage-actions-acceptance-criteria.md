# UAC: project stage buttons open their own form directly

Plan: `PLAN-project-stage-actions-11nov.md`.

- PSA-1 PO received (header button or gear item) moves the project, then shows the PO tab with
  the "Upload a customer PO" dialog open (drop zone + PO number). Test:
  `ProjectDetailClient.test.tsx` "PROJECT-STAGE-ACTIONS: PO received ..." (2),
  `PurchaseOrdersPanel.stageUpload.test.tsx`.
- PSA-2 Cancel on that dialog closes it and leaves the user on the PO tab; a refresh does not
  reopen it; a reader who cannot upload gets no dialog. `PurchaseOrdersPanel.stageUpload.test.tsx`.
- PSA-3 Sponsorship opens the salesperson's sponsorship form (portal SubmissionForm) for staff
  and admins too, never the free-text staff form.
  `PurchaseRequestForm.projectSponsorship.test.tsx`.
- PSA-4 The form starts from the project: registered project, title, customer, PIC (attn + phone),
  delivery address, total project value; the same start for a salesperson and for staff. Same test.
- PSA-5 Staff write it on behalf of the project salesperson: Requested by defaults to them and the
  form is theirs (its contact). `staffSponsorshipSubmissionClient.test.ts`,
  `tests/test_project_stage_staff_sponsorship.py`.
- PSA-6 Staff Save draft uses the staff create; Submit runs the portal's submit rules (draft only,
  unit prices, required fields, approved project) and side effects (number, form SLA, project feed).
  `tests/test_project_stage_staff_sponsorship.py`.
- PSA-7 Only a user holding the kind's `.add` may submit; a salesperson limited to their own rows
  is refused on the staff route; only a staff-written draft is submitted, never a salesperson's
  own portal draft. Same file.
- PSA-8 Cancel from the sponsorship form and from a new sample request opened from a project
  returns to that project's tab; Submit of the sponsorship form returns there too.
  `page.stageBack.test.tsx` (2), `SampleRequestForm.stageBack.test.tsx`,
  `staffSponsorshipSubmissionClient.test.ts`.
- PSA-9 Spec In, Sample submitted and Final negotiation behave as before. Existing
  `ProjectDetailClient.test.tsx` AC-PS tests.
- PSA-10 From a project the salesperson's form and the staff form start identically: Registered
  project shown, the lookup defaults pre-selected, no AI Extract; the salesperson's bottom Cancel
  and Submit return to the project tab. `SponsorshipForm.portalForm.test.tsx`,
  `PurchaseRequestForm.projectSponsorship.test.tsx`, `staffSponsorshipSubmissionClient.test.ts`.
- PSA-11 Expected delivery date is the shared DD/MM/YYYY picker. `SponsorshipForm.portalForm.test.tsx`.
- PSA-12 The project Sponsorships tab and its total show the sponsored amount (line Grand total),
  not the project value. `SponsorshipsPanel.sponsoredTotal.test.tsx`,
  `tests/test_sponsorship_project_link.py`.
- PSA-13 A sponsorship form opened from the project tab goes "Back to project"; a non-app origin
  is ignored. `BackToList.origin.test.tsx`, `SponsorshipsPanel.sponsoredTotal.test.tsx`.
- PSA-14 A staff draft line with no quantity is refused at Save draft as a plain 422 (no line
  reference), stricter than a portal draft; unchanged staff create behaviour.
