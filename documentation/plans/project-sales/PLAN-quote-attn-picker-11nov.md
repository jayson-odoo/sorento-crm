# PLAN: quote Attn picker, standard multi-select + add-contact CTA (QUOTE-ATTN-PICKER)

Status: in review (PR #2335). Track: small fix (no migration, no auth/RBAC change).

## Owner feedback (11 Nov 2026)
The "Attn at <company>" popup used a hand-rolled checkbox list (no search, no Select all), and
while "+ Add contact" was open the dialog's blue Done stayed visible, so Done closed the dialog
and lost the half-typed contact.

## Change
All in `sorento_crm_frontend/app/(protected)/project-sales/_shared/components/PartyContactsDialog.tsx`,
the one dialog behind every Attn picker (quotation + proposal, create + edit, via
`QuotationRecipientPicker`) and the project parties contacts popup (`ProjectPartiesSection`).

1. The contact list is the standard `components/common/SearchableMultiSelect` (search,
   "Select all (N)"; same component as `scm/reorder/components/RunPlanningModal.tsx` and
   `project-sales/fulfilment-planning`). One row per contact: name, then job title + phone.
   Contacts already on the project are disabled options that stay ticked.
2. While the add-contact form is open its "Add contact" is the only primary CTA: the dialog
   footer (Cancel / Done) is hidden. Adding ticks the new contact and brings Done back;
   cancelling the form brings it back too.
3. "Add number" for a picked contact without a phone stays, listed under the picker.

## UAC
- U1 Picker shows a search box and "Select all (N)" over the party's active contacts.
- U2 Select all ticks every contact; Done saves them all.
- U3 Opening "+ Add contact" hides Done and Cancel; the form's Add contact is the only primary button.
- U4 Adding a contact ticks it and Done returns; Done saves it.
- U5 Cancelling the add form brings Done back with nothing added.
- U6 A contact already on the project shows ticked and cannot be unticked.

## Crew additions (same PR, 11 Nov)

4. Impersonation banner (`components/impersonation/ImpersonationBanner.tsx`) now says records are
   saved as the impersonated user and the audit log shows the admin. Verified first:
   `dependencies.py` stamps `real_user_id`, written to `audit_logs.real_user_id`.
5. Owner ruling 11 Nov ("prepared by should always be the one who create, this is compliance"):
   Prepared By = the document's `created_by` on the document response, the cover page (legacy row
   and the Prepared by name/phone sources), the spec sheet and the new-quotation form (the effective
   user, the impersonated one during a view-as). Not editable. Salesperson sources keep the owner.
   Stored PDFs are not rewritten. UAC line A4 of `quote-cover-page-02nov-acceptance-criteria.md` updated.
6. Found in the browser pass: a disabled `SearchableMultiSelect` (or a disabled option) still let a
   chip X remove a pick; neither offers the X now.

- U7 Prepared By on an owner-owned project, document created by another salesperson = the creator.
