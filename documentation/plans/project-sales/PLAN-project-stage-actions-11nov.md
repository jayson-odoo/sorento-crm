# PLAN: project stage buttons open their own form directly

Status: in progress (small fix track: FE only, no migration, no auth/RBAC change)
Lane: PROJECT-STAGE-ACTIONS. UAC: `project-stage-actions-acceptance-criteria.md`.

## Journey

A salesperson or admin on a project clicks the header's main stage button. When the stage needs
a document, the button takes them straight to that document's existing form. Cancel or Back from
that form returns to the project tab it belongs to.

## Measured today (main a80d65fa)

- `ProjectDetailClient.tsx` `STAGE_FORM_ROUTE` maps rung key -> form route, fired only after a
  forward move lands: `specified` -> new quotation, `sample_submission` -> new sample request,
  `sponsorship_form` -> `/procurement-management/sponsorship-forms/new?project_id=`.
- `po_received` has no entry: the user lands wherever they were and must open the PO tab and
  click "Upload a PO document" (`PurchaseOrdersPanel.tsx`, `POIntakeUploadDialog`).
- Sponsorship: `PurchaseRequestForm` already renders the salesperson's (portal) form
  (`NewOwnRequestForm` -> `MyRequestPortalForm`) for a user limited to their own rows, and the
  staff form (`StaffPurchaseRequestForm`) for everyone else. The admin sees the staff form.
  `/api/v1/my-requests` refuses a user holding `.view` and admin/superadmin by role
  (`sorento_crm_backend/app/api/v1/my_requests.py` docstring), so the portal form cannot simply
  be shown to an admin without a backend change.
- Cancel on the new sponsorship and new sample request pages goes to the admin lists, not back to
  the project.

## Stage -> what opens

| Rung key | Opens |
| --- | --- |
| registered, quoted, tendering | nothing (no form for these) |
| specified (Spec In) | new quotation page (unchanged) |
| sample_submission | new sample request (unchanged route; Cancel now returns to the project's Samples Request tab) |
| final_negotiation | nothing (no form) |
| sponsorship_form | the sponsorship form, project prefilled; Cancel and save return to the project's Sponsorship Form tab |
| po_received | the project's PO tab with the "Upload a customer PO" dialog open; Cancel leaves the PO tab |
| lost | the existing loss reason dialog (unchanged) |

## Slices

1. PO received: `STAGE_FORM_ROUTE.po_received` -> `/project-sales/<id>?tab=orders&upload=po`;
   `PurchaseOrdersPanel` opens `POIntakeUploadDialog` once on `upload=po` and drops the param.
2. Back to the project: new sponsorship / sample request pages send Cancel (and the sponsorship
   save) back to the project tab when opened with `project_id`.
3. Sponsorship form for staff: see crew-ask on the PR.
