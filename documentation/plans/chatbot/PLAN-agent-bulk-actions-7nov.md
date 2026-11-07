# PLAN: Agent bulk actions from a pasted table (AGENT-BULK-ACTIONS)

Status: Build (owner accepted all five card recommendations, "2226 ok", 7 Nov ~16:15). Track: full (L: writes + permissions).

## Journey

The owner pastes a table of dealer contacts (phone, name, access, customer(s), company) into the assistant side
panel and says "grant access to these people". The agent previews every row in one table, and on one Confirm applies
the whole batch through the same code the screens use, with a result per row and an audit row per contact naming the
real user.

## What exists today (read, not assumed)

- One-contact access write: `crm_contact_access_update` (`app/services/chatbot/agent/writes.py:1332`), keyed by a
  `contact_id` the model must first get from `crm_contacts_find` (`writes.py:1270`, max 20 phones). It sets role,
  AI replies and customer links of an EXISTING contact, one step per contact. It cannot create a contact, set a
  company, or take a phone or customer code straight from a pasted table.
- The Respond sheet upload (BULK-CONTACT-ACCESS, `app/services/contact_access_sheet_service.py`, route
  `POST /api/v1/user_management/contacts/access-sheet`, slug `user_management.contacts.edit`) applies the 26 Oct
  template per row (`TEMPLATE`, `contact_access_sheet_service.py:41`) through the shared engine
  (`contact_setup_engine._plan_contact` / `_apply_contact`) and skips facets the caller could not set directly
  (`contact_access_copy_service.facets_to_skip`: companies are superadmin only, agents need the agents slug,
  stock needs `inventory.stock.edit`).
- Confirm (`actions.confirm`, `actions.py:247`): re-checks every step, runs the steps in order, and STOPS at the first
  failure (later steps "not run"). `MAX_STEPS = 20` per confirmation (`actions.py:34`).
- The proposal is shown as numbered lines in the reply (`loop.proposal_block`, `loop.py:670`) plus the
  Confirm / Cancel buttons (`AgentTurnParts.ProposalActions`); results show per step with field lines
  (`ActionsBlock`).

## Design (simplest thing that works)

1. One new row write, `crm_contact_grant` (a `WriteDef`), keyed by EXPLICIT values from the table, not ids:
   `phone`, `name`, `role` (owner / employee), `companies` (SRT / MCH), `customer_codes`, `customer_names`.
   - `read_before` normalises the phone (`contact_setup_engine.normalise_phone`), finds the contact by phone digits
     (`_find_contacts`: two contacts with the same digits = skipped "ambiguous phone"); resolves each customer by
     exact code, or by exact name with exactly one match in the user's scope (else skipped "customer not found" /
     "more than one customer named X"); NO fuzzy matching. It plans the row with the sheet's own engine
     (`_plan_contact` + the template) and returns what will change, or raises the refusal that the preview shows as
     the skip reason.
   - `execute` re-plans and applies the row in ONE transaction: create the contact if new, the engine's apply,
     `link_customer`, one `contact.access_agent` audit row naming the real user; commit. A failure rolls back that
     row only.
2. ONE generic batch tool, `crm_batch_propose` {`write`, `rows`: [args...]}: for any WriteDef that opts in
   (`batchable=True`), runs `propose_step` for each row; rows that refuse are listed as skipped with the reason; the
   rest become the proposal's steps. Next waves (tag contacts, assign sales agent, product fields) add a WriteDef with
   `batchable=True`, not a new flow.
3. Confirm keeps one row per step; a batch action runs every step even after a failed one (each row is its own
   transaction), so the result lists done / failed per row. Single (non-batch) actions keep stop-at-first-failure.
4. The preview is ONE code-rendered table in the reply (the same verbatim-block mechanism `crm_query` tables use,
   `ToolResult.display`), above the existing Confirm / Cancel buttons; no new UI component.

## Behaviour card (crew-ask, 7 Nov)

Example (fake numbers; same columns as the 28 Oct Allowed Contacts sheet):

```
Phone          Name        Access          Customer             Company
012-000 0701   Ali         Business owner  ABC Trading (A123)   Sorento
012-000 0702   Mei Ling    Employee        A123                 Sorento, Mocha
012-000 0703   Raju        Pemilik         XYZ Hardware         Mocha
012-000 0704   Siti        Employee        Kedai Baru Enterprise Sorento
```

Preview the agent shows (one table, then Confirm 3 changes / Cancel):

| # | Phone | Name | Contact | Will change | Skipped / why |
|---|---|---|---|---|---|
| 1 | +60120000701 | Ali | existing | Role Employee -> Business owner (Sorento); link A123 ABC Trading | |
| 2 | +60120000702 | Mei Ling | new | create contact; Employee; link A123; companies Sorento, Mocha | |
| 3 | +60120000703 | Raju | existing | Role -> Business owner (Mocha); link X900 XYZ Hardware | |
| 4 | +60120000704 | Siti | existing | | skipped: no customer named "Kedai Baru Enterprise" (exact code or exact name only) |

Matching rules: phone exact after normalising (0123... / 60123... / +60 1...); customer by code, or by exact name
with exactly one match inside the user's companies; anything else is skipped with its reason, never guessed.

Permission rule: only a user holding `user_management.contacts.edit` (the slug of the contacts screen, the sheet
upload and contact create) is offered the tool; facets the user could not set on the screen (companies: superadmin;
stock / agents: their own slugs) are shown as "not applied" for that row, as the sheet upload does today.

Answers (owner, 7 Nov): (1) the full Respond-sheet template through the same engine; (2) a phone not in the CRM is created, marked new in the preview; (3) Malay and English access words accepted, anything else skips the row; (4) each row all or nothing, the other rows still apply, failures listed; (5) up to 50 rows per Confirm.
