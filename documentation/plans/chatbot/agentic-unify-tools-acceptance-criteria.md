# UAC: AGENTIC-UNIFY tools, the panel's remaining features as agent tools

Status: written 1 Nov 2026. PR 4 of 4. Owner Q2 (a) on `CARD-agentic-unify-v2-31oct.md` section 4: "add them as agent tools before the pilot". Plan: `PLAN-agentic-unify-tools-1nov.md`.

`CHAT` = `sorento_crm_backend/app/services/chatbot`.

## Panel only (crew ruling on the security review, 2 Nov)

- **AC-0** Every tool in this document is offered only on a staff-principal turn, where the route runs as the user, so the route's own rules hold: its slugs, own scope, field gates, active company. On a console or WhatsApp turn each is not offered and is refused at call time, its label is not sent to Jev, and it does not appear in the prompt's "Outside this user's access" line, so those turns' prompts stay as they are on main. **Deferred from card Q2: "WhatsApp staff gain them too".** Trigger: run these reads as the linked user on non-panel turns, audited tool by tool. Crew tells the owner; the owner may overrule.

## Read tools

- **AC-1** The agent offers these reads, each only to a user holding its slug, and refuses at call time as well:

| Tool | Slug | Panel also accepts |
| --- | --- | --- |
| `crm_complaints_list` | `complaint_management.complaints.view` | `.view_own` |
| `crm_complaint_analytics` | `complaint_management.complaints.view` | |
| `crm_sla_conversation_tracking_dashboard` | `sla_management.conversation_sla_tracking.view` | |
| `crm_sla_conversation_tracking_list` | same | |
| `crm_sla_conversation_event_logs_list` | `sla_management.escalation_logs.view`, the route's and the screen's rule for an unfiltered read (`sla_tracking.py:99-104`) | |
| `crm_projects_list` | `projects.projects.view` | `.view_own` |
| `crm_project_detail` | `projects.projects.view` | `.view_own` |
| `crm_project_quotations_list` | `projects.projects.view` | `.view_own` |
| `crm_project_forecast` | `projects.projects.view` | |
| `crm_order_analytics` | `order_management.orders.view`, and the reveal `sales_orders.sales_report`, as `crm_report_ask` asks; a refused sales read stays refused for the turn | |
| `crm_find` | `inventory.stock.view`, because every answer carries stock; the route itself asks `master_data.products.view` | |
| `crm_system_tool_capabilities_summary` | none, any signed-in staff user | |

- **AC-2** A user holding only `.view_own` sees only their own complaints or projects: the read runs as the user and the route narrows it. A buyer's phone and main contact on a project show only to a user holding `order_management.customers.view`.
- **AC-4** Each read reaches its route through the real compiled MCP tool as staff: blank contact pair, staff header forwarded as `X-Staff-User`, never refused with `scope_required` or a missing-parameter error. Proved in `sorento_crm_mcp/tests`, one case per tool, because panel tests stub MCP.
- **AC-5** A complaint number or project code finds its row, and the catalog's UUID-first rule stays as it is (`test_no_freetext_query_on_data_list_tools` is not edited). Two in-process reads, `crm_complaints_find` and `crm_projects_find`, take `query` and call the screen's list route as the user, so own scope holds on every turn. Slug: the domain's `.view` or `.view_own`. Rows carry the number or code, status, customer or title, and the id, which joins the turn's ids. `crm_projects_find` returns approved projects only, as the catalog's list does.
- **AC-6** On each read: no rows gives status `empty`, never a bare `ok`; an oversized result is cut to the cap with the count of what was cut; the reply never shows a UUID; a panel read covers the user's active company only, where the record carries a company (complaints do not, see known limits).
- **AC-7** Each read is in `CHATBOT_READ_ONLY_TOOLS`. A panel turn has no brand scope, so no brand rule applies here; the brand rule comes back with the trigger in AC-0.
- **AC-8** A label for every tool in this document. Jev's `agent.tools` list carries the labels of the writes below and of the reads in AC-1 except `crm_find` and capabilities. The published router text does not change. A user missing a slug gets the label in the prompt's existing "Outside this user's access" line.

## Write tools, each through the existing propose, Confirm, execute path

- **AC-9** Nothing changes until Confirm. Slug checked at exposure, proposal and execution. A record changed between card and Confirm is refused by the existing re-check. The card and steps carry no UUID.
- **AC-10** `crm_complaint_close`, slug `complaint_management.complaints.close`, args `complaint_id` (from this turn's results, `crm_complaints_find` or the list) and optional `note`. The proposal refuses what the route would refuse: a user limited to their own complaints (`_request_own_scope`, read as the route's guard does), a complaint not yet approved, held by someone else, or with another action pending. It also refuses one already closed: the service treats that as a no-op with no words of its own, and a card must not offer a change that changes nothing. The card names the complaint, its customer quoted, the whole note, and says the contact will be told.
- **AC-11** On Confirm the complaint close goes through the route's own function on the browser channel, with the revision the user confirmed. The screen's grace window applies: the step shows the countdown and Undo withdraws it, using the existing generic withdraw. Withdrawn means status unchanged and no message sent.
- **AC-12** `crm_order_cancel`, slug `order_management.orders.view` (the route's own, as the screen, see plan question 1), args `order_number` and optional `reason`. Order rows carry no UUID, so the proposal finds the order by number in the user's scope. It refuses an unknown number, an order already cancelled, and an order the service would refuse: an AutoCount-owned order answers 409, because `is_cancelled` and `remarks` are its columns. The card names the order, its customer quoted, the whole reason, and says complaints on it are re-evaluated.
- **AC-13** On Confirm the cancel goes through the route's own function, as the user. It has no grace window, as today. The change shows Cancelled: No to Yes.
- **AC-14** `crm_it_support_ticket_create`, no slug (any staff user may raise one, as on the panel today), args `title`, `description`, `priority`, `category`, title required so the server's LLM draft never runs, each shown whole on the card and escaped in the draft, with or without a description. On Confirm a DRAFT ticket is created with the user as raiser and `source_channel = ai_assistant`, and the draft link is put in the reply by code, never by the model.

## Proof

- **AC-15** Red test commit before any code, kill proof after. Touched tests pass, including `tests/test_list_pagination_limit.py` if a list route's params change.
- **AC-16** One live turn per tool family on a crew copy, with the panel as a staff user: complaints, SLA, projects, order analytics, find, capabilities, complaint close with Undo, order cancel, ticket draft. No step shows failed. Live call budget asked of crew first.
- **AC-17** Jev gate: a fresh labelled set of ported-domain questions plus the fixed baseline rows, labels on against labels off. Bar in the plan.
- **AC-18** Browser pass at 1280 and 375 on the panel: cards, countdown, Undo, draft link.

## Known limits, stated not fixed

- `Complaint` has no `company_id`, so complaints read and close across companies, for anyone holding the slug, as on their own screen. Closing one messages that contact. SLA trackers carry `company_id`, but no route filters on it, as on their screen. Not this PR's to change. Trigger: those screens gaining a company rule.
- Raw complaint and SLA rows give the model phones, addresses and staff emails, as the screen does, and so they reach the LLM vendor. The old panel path did the same.
- `crm_order_cancel` takes any number in the user's company, including one named by text the model read. The card names the order and customer, and a Confirm is required in a later message.
- Capabilities lists the catalog's tool names and paths to any staff member, as the old panel did.

- `owner_user_ids` and `assigned_to` take ids the agent has no resolver for, so "projects owned by X" lists and reads the rows. Trigger to fix: real questions in the pilot set.
- Complaint undo after the grace window stays on the screen. Trigger: an owner ask.
- No frontend change expected: cards, countdown and Undo are generic. A failed browser row reopens this.
