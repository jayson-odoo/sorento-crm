# PLAN: quote Attn picker, standard multi-select + add-contact CTA (QUOTE-ATTN-PICKER)

Status: in progress. Track: small fix (FE only, no migration, no auth/RBAC change).

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
