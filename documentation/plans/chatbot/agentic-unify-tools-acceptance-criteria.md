# UAC: AGENTIC-UNIFY tools, the panel's remaining features as agent tools

Status: written 1 Nov 2026. PR 4 of 4. Owner Q2 (a) on `CARD-agentic-unify-v2-31oct.md` section 4: "add them as agent tools before the pilot". Plan: `PLAN-agentic-unify-tools-1nov.md`.

`CHAT` = `sorento_crm_backend/app/services/chatbot`.

## Read tools

- **AC-1** The agent offers these reads, each only to a user holding its slug, and refuses at call time as well:

| Tool | Slug | Panel also accepts |
| --- | --- | --- |
| `crm_complaints_list` | `complaint_management.complaints.view` | `.view_own` |
| `crm_complaint_analytics` | `complaint_management.complaints.view` | |
| `crm_sla_conversation_tracking_dashboard` | `sla_management.conversation_sla_tracking.view` | |
| `crm_sla_conversation_tracking_list` | same | |
| `crm_sla_conversation_event_logs_list` | same (the route has none; the agent asks the screen's) | |
| `crm_projects_list` | `projects.projects.view` | `.view_own` |
| `crm_project_detail` | `projects.projects.view` | `.view_own` |
| `crm_project_quotations_list` | `projects.projects.view` | `.view_own` |
| `crm_project_forecast` | `projects.projects.view` | |
| `crm_order_analytics` | `order_management.orders.view` | |
| `crm_find` | `master_data.products.view` | |
| `crm_system_tool_capabilities_summary` | none, any signed-in staff user | |

- **AC-2** `.view_own` counts on a panel turn only, where the read runs as the user and the route narrows to their own rows. A panel user holding only `.view_own` sees only their own complaints or projects. On a console or WhatsApp turn the read runs as the shared key's user, so a linked user holding only `.view_own` is not offered the tool and is refused it.
- **AC-3** A console operator acting for a linked user must hold the slug too, on every read in AC-1.
- **AC-4** Each read reaches its route through the real compiled MCP tool: as staff (blank contact pair, staff header forwarded as `X-Staff-User`) and as a linked contact. Neither shape is refused with `scope_required` or a missing-parameter error. Proved in `sorento_crm_mcp/tests`, one case per tool per shape, because panel tests stub MCP.
- **AC-5** A complaint number or project code finds its row, and the catalog's UUID-first rule stays as it is (`test_no_freetext_query_on_data_list_tools` is not edited). Two in-process reads, `crm_complaints_find` and `crm_projects_find`, take `query` and call the screen's list route as the user, so own scope holds on every turn. Slug: the domain's `.view` or `.view_own`. Rows carry the number or code, status, customer or title, and the id, which joins the turn's ids. With a console operator, only rows both may see.
- **AC-6** On each read: no rows gives status `empty`, never a bare `ok`; an oversized result is cut to the cap with the count of what was cut; the reply never shows a UUID; a panel read covers the user's active company only, where the record carries a company (complaints do not, see known limits).
- **AC-7** Each read is in `CHATBOT_READ_ONLY_TOOLS`. A brand-scoped linked contact never gets another brand's rows from a read that can return products. Projects carry no brand, so a scope naming a brand gets no project read at all: `crm_projects_list`, `crm_project_detail` and `crm_project_quotations_list` join `crm_project_forecast` in `_TOOLS_DENIED_WHEN_SCOPED`, for the reason of the forecast's ruling, and both finds refuse. Complaint rows stay under the existing guard; a row naming no product passes, as on every filtered tool.
- **AC-8** A label for every tool in this document. Jev's `agent.tools` list carries the labels of the writes below and of the reads in AC-1 except `crm_find` and capabilities. The published router text does not change. A user missing a slug gets the label in the prompt's existing "Outside this user's access" line.

## Write tools, each through the existing propose, Confirm, execute path

- **AC-9** Nothing changes until Confirm. Slug checked at exposure, proposal and execution, for the user and any console operator. A record changed between card and Confirm is refused by the existing re-check. The card and steps carry no UUID.
- **AC-10** `crm_complaint_close`, slug `complaint_management.complaints.close`, args `complaint_id` (from this turn's results, `crm_complaints_find` or the list) and optional `note`. The proposal refuses what the route would refuse: a complaint not yet approved, held by someone else, or with another action pending. It also refuses one already closed: the service treats that as a no-op with no words of its own, and a card must not offer a change that changes nothing. The card names the complaint, its customer, the whole note, and says the contact will be told.
- **AC-11** On Confirm the complaint close goes through the route's own function on the browser channel, with the revision the user confirmed. The screen's grace window applies: the step shows the countdown and Undo withdraws it, using the existing generic withdraw. Withdrawn means status unchanged and no message sent.
- **AC-12** `crm_order_cancel`, slug `order_management.orders.view` (the route's own, as the screen, see plan question 1), args `order_number` and optional `reason`. Order rows carry no UUID, so the proposal finds the order by number in the user's scope. It refuses an unknown number, an order already cancelled, and an order the service would refuse: an AutoCount-owned order answers 409, because `is_cancelled` and `remarks` are its columns. The card names the order and its customer, and says complaints on it are re-evaluated.
- **AC-13** On Confirm the cancel goes through the route's own function, as the user. It has no grace window, as today. The change shows Cancelled: No to Yes.
- **AC-14** `crm_it_support_ticket_create`, no slug (any staff user may raise one, as on the panel today), args `title`, `description`, `priority`, `category`, title required so the server's LLM draft never runs. On Confirm a DRAFT ticket is created with the user as raiser and `source_channel = ai_assistant`, and the draft link is put in the reply by code, never by the model.

## Proof

- **AC-15** Red test commit before any code, kill proof after. Touched tests pass, including `tests/test_list_pagination_limit.py` if a list route's params change.
- **AC-16** One live turn per tool family on a crew copy, with the panel as a staff user: complaints, SLA, projects, order analytics, find, capabilities, complaint close with Undo, order cancel, ticket draft. No step shows failed. Live call budget asked of crew first.
- **AC-17** Jev gate: a fresh labelled set of ported-domain questions plus the fixed baseline rows, labels on against labels off. Bar in the plan.
- **AC-18** Browser pass at 1280 and 375 on the panel: cards, countdown, Undo, draft link.

## Known limits, stated not fixed

- `Complaint` has no `company_id`, so complaints read and close across companies, for anyone holding the slug, as on their own screen. Not this PR's to change. Trigger: complaints gaining a company.

- `owner_user_ids` and `assigned_to` take ids the agent has no resolver for, so "projects owned by X" lists and reads the rows. Trigger to fix: real questions in the pilot set.
- Complaint undo after the grace window stays on the screen. Trigger: an owner ask.
- No frontend change expected: cards, countdown and Undo are generic. A failed browser row reopens this.
