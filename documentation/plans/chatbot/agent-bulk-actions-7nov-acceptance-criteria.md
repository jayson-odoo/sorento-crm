# UAC: Agent bulk actions from a pasted table (AGENT-BULK-ACTIONS)

Plan: `PLAN-agent-bulk-actions-7nov.md`. Owner answers to the behaviour card: "2226 ok" (7 Nov ~16:15).
Tests: `sorento_crm_backend/tests/chatbot/agent/test_agent_bulk_grant.py` (test number in brackets).

| # | Given / When | Then |
|---|---|---|
| B1 | A user holding `user_management.contacts.edit` | the agent is offered `crm_batch_propose` for `crm_contact_grant`; every array in its schema names its items (01) |
| B2 | A user without that slug (`edit_own` only), or a dealer on WhatsApp | the tool is not offered and a direct call is denied, nothing proposed (01) |
| B3 | A pasted table, "grant access to these people" | ONE preview table in the reply (row, phone, name, new/existing, what will change) and the skipped rows with why; Confirm N changes; nothing written yet (06) |
| B4 | A row's phone in any form (012-..., 6012..., +6012...) | it matches the one contact holding those digits in either stored form; two holders = row skipped (02, 03) |
| B5 | A phone not in the CRM | the row is marked new; Confirm creates the contact with the table's name, plus the agents flagged for new contacts (02, 08) |
| B6 | A customer named by code, or by exact name with one match in the user's companies | it is linked; two matches, a near name, an unknown code or a customer outside the user's companies = row skipped with the reason; never guessed (03) |
| B7 | A customer of a company the row does not name, or a company the user is not granted | row skipped with the reason (03, 08) |
| B8 | Access words Business owner / Owner / Pemilik / Tauke, Employee / Staff / Pekerja | mapped to owner / employee; anything else = row skipped (03) |
| B9 | The access a row grants | the 26 Oct Respond sheet template for that role and those companies, through the same engine as the sheet upload (02, 04) |
| B10 | A facet the user (or a console operator acting for them) could not set on screen: companies, stock, agents | listed "not applied" and not written (05, 07) |
| B11 | A row with nothing to change, or the same phone twice | skipped "already has this access" / "same as row N" (03) |
| B12 | Confirm | every row runs in its own transaction: a failed row is rolled back whole (no half-created contact) and listed with why; the other rows still apply (04) |
| B13 | A row whose contact, links or named customer changed between preview and Confirm | that row fails alone (04, 08) |
| B14 | The slug removed before Confirm | every row fails, nothing written (04) |
| B15 | More than 50 rows, or more than 10 customers on a row | refused (04, 07) |
| B16 | A table proposed with other single changes in the same turn, either order | the later one is refused (08) |
| B17 | Each applied row | one `contact.access_agent` audit row naming the real user, `auth_method = agent` (02) |
