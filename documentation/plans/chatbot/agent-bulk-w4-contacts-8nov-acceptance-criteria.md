# UAC: agent bulk wave 4, contact edits from a pasted table (AGENT-BULK-W4-CONTACTS)

Owner answers 8 Nov ("2256 all recs"). Tests: `sorento_crm_backend/tests/chatbot/agent/test_agent_bulk_w4_contacts.py`.

1. `crm_contact_edit` is a batchable row write under `user_management.contacts.edit` only (the Edit Contact
   screen's slug); `contacts.edit_own` gets no such write and a batch call is denied (Q5).
2. A row edits Name, the sponsorship switch ("Sponsorship must name a registered project") and the Respond.io
   Workspace (by name or space id), nothing else (Q1). The phone is the key only (Q2).
3. The phone matches as W1 does (normalised Malaysian mobile, either stored form). Unknown phone: `No contact with
   the phone <phone>.`, never created. Two contacts: `More than one contact has this phone number; ...` (Q3).
4. A blank cell is unchanged, nothing is cleared (Q4); every cell equal: `Nothing to change.`; no cell: asks for one.
   A name equal apart from spacing is unchanged; capitals compare exactly, so a case-only fix is a rename (crew, 8 Nov).
5. Unknown workspace / two workspaces with the name: not changed with the reason. The user's own contact: refused.
6. The card shows `# | Phone | Name | Will change` and Not changed `... | Why`; nothing changes before Confirm.
7. Confirm writes through `ContactService.update_contact` (the screen's service), one audit row per contact
   ("Agent contact edit for <phone> from a pasted table"); a contact changed on screen since the preview fails alone;
   the slug removed before Confirm fails every row.
8. The workspace is an ACTIVE one, and the cell needs `system.respond_workspaces.view` (the screen's picker slug)
   for the user and the console operator; without it: `You cannot change a contact's Respond.io workspace.`
