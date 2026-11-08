# PLAN: agent bulk wave 4, edit contacts from a pasted table keyed by phone (AGENT-BULK-W4-CONTACTS)

Status: Merge-ready pending crew live run x3 (laneboard/scripts/2256.md); reviewer READY, security review fixes applied, capitals ruling built. Track: full. Track: full (agent write path to contacts).

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

## Decisions (owner, 8 Nov: "2256 all recs")

Q1 (a) Name, the sponsorship switch and the Respond.io Workspace; Q2 (b) the phone is the key only; Q3 (a) a phone on
two contacts is refused; Q4 (a) a blank cell is unchanged, nothing is cleared; Q5 (a) `contacts.edit` only.

## Build

- `app/services/chatbot/agent/contact_edit.py`: `crm_contact_edit` (`plan`, `_execute` through
  `ContactService.update_contact`, audit event `contact.edit_agent`). Registered last in `writes.py` so the label
  lists keep their order; label "edit contacts from a pasted table" (`tools.py`).
- A name that differs only in spacing is the same name (not a change); capitals compare exactly (crew ruling 8 Nov,
  option b: a case-only fix goes through, the card shows it). Workspace by exact name (case and
  spaces aside) or space id; two workspaces with one name: give the space id.
- The confirm re-check compares contact id, name, sponsorship switch and workspace id: a contact edited on screen
  since the preview fails alone.
- Tests: `tests/chatbot/agent/test_agent_bulk_w4_contacts.py` (14). Kill tests: own-contact refusal, case fold,
  audit row, Nothing to change, the name in `before`, the duplicate workspace: each caught by exactly one test.
- Review follow-up on the kept-reason fix: the earlier args travel with the kept reason (third turn), stronger
  tests, and a corrected row of a key-changing write is no longer carried twice (`carried_skips`).
- Known red on main, not this lane: `test_ai_tools_wave2_round3.py::test_I1_the_entity_index_is_in_the_query_tools_description`
  (stock_inquiry has no index hint).

## Review round (8 Nov)

Reviewer READY. Security reviewer fixes: S1 inactive workspaces are not found (the screen lists active only); S2 the
workspace cell needs `system.respond_workspaces.view` for the user and the operator (the screen's picker slug), else
one fixed refusal; N1 the target workspace is in `before` (a rename before Confirm fails the row); N2 the audit row
commits with the change. Tests `test_06_*`, each kill-tested. Case-only rename: owner had no opinion, crew ruled (b), built red-first (`test_07_*`, kill-tested).
