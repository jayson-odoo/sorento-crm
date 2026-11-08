# PLAN: agent bulk wave 4, edit contacts from a pasted table keyed by phone (AGENT-BULK-W4-CONTACTS)

Status: Waiting on owner (behaviour card crew-ask on PR #2256); W3 kept-reason fix done (red-first, kill-tested). Track: full (agent write path to contacts).

Wave 4 after AGENT-BULK-W3-AGENTS (#2253). Pattern: `crm_customer_agent` (`app/services/chatbot/agent/customer_agent.py`)
through `crm_batch_propose` (`batch.py`) and one confirm card.

## Step 1: the contact edit path today (main @ 2d466f98; paths under `sorento_crm_backend/app/`)

1. **Screen.** `ContactEditDialog.tsx` (FE `app/(protected)/user-management/contacts/[id]/components/`) sends
   `PUT /user-management/contacts/{id}` with phone_number, name, workspace_id, access_type_codes,
   requires_registered_project; tags go through their own call; Companies only for a superadmin
   (`PUT /contacts/{id}/companies`).
2. **Route.** `api/v1/user_management/contacts.py:401`, slug `user_management.contacts.edit` (edit_own holders get
   nothing). Service `ContactService.update_contact` (`services/contact_service.py:604`): phone uniqueness 409,
   access types replaced when sent, one commit.
3. **Model.** `respond_contacts` (`models/access.py:265`): `phone_number` unique; name, first_name, last_name. No
   email, no role text, no company text on the contact. Linked customers are `respond_contact_customers` (W1).
4. **Audit.** Default-on listener (`services/audit_service.py:94`) writes before / after for the contact row.
5. **Phone.** `contact_setup_engine.normalise_phone` (`+601` + 8-9 digits); W1 finds a contact on digits in either
   stored form and refuses two (`contact_grant._find_contact`, `contact_grant.py:159`).
6. **Respond.io.** The screen's save does not push the name; Sync (`contacts.py:711`) pulls Respond.io's name over
   the CRM's.

## Behaviour card

Posted as `crew-ask` on #2256 (five questions: field set, phone change, duplicate phone, blank cells, who may run).

## Fix in this lane: a re-sent not-changed row keeps its reason

Crew W3 live: on the pick follow-up the model re-sent a not-changed row without its agent cell; the row read
`Name the sales agent.` instead of `No sales agent named "NOSUCH 77".`. Fix (`batch.keep_earlier_reasons`): each
skipped row stores the arguments it was checked with (`batch_skipped[].args`); on the same table's pick follow-up
(the `carried_skips` condition), a row whose non-empty arguments are a strict part of its earlier ones (cells
dropped, nothing new or changed) keeps the earlier reason. Structured arguments only. Tests:
`tests/chatbot/agent/test_agent_bulk_w3_agents.py::test_w4_*`.

Also: three tests still called `batch.schema_for` after its rename to `batch_tool_schema` (#2244); renamed.
