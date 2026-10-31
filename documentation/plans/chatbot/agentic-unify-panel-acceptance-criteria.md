# UAC: AGENTIC-UNIFY panel, the AI side panel on the chatbot's brain

Status: written 31 Oct 2026. PR 3 of 4. Owner: "I need the thinking and brain process to be same as chatbot, simple as that". Answers: card v1 Q2-Q4 (a), card v2 Q1 (b) with agent mode, Q3 (a) rendered, panel plan Q1-Q3 (a). Mock v1 approved.

Contract: `CARD-agentic-unify-v2-31oct.md`, `PLAN-agentic-unify-panel-31oct.md` (its audit table is binding), Panel tabs of `documentation/mockups/agentic-unify/index.html`.

`CHAT` = `sorento_crm_backend/app/services/chatbot`.

## Rollout

- **AC-1** New permission `system.ai_assistant_chat.agent`, granted to nobody by a migration. Without it, a panel turn runs today's `respond()`, unchanged: the existing panel tests stay green untouched.
- **AC-2** With it, `POST /system/ai-assistant/chat` routes through the same Jev as the console, keeping the same route, gate (`system.ai_assistant_chat.use`) and identity from the session. A panel Confirm still waiting from the old path is finished by the old path.

## One brain, as the staff member

- **AC-3** Jev says chat: the same `run_turn`, parser and lanes as WhatsApp answer. Jev says agent, or a proposal waits: the same agent loop answers. Low confidence or over the cap goes to chat.
- **AC-4** The principal needs no `respond_contacts` row, and none is created. Its key is `panel-<conversation id>`, with no colon. A test pins that this key can never be sent to through the outbound path.
- **AC-5** The principal answers the brain's questions: company = the user's active company; brand = all; tier = office; customers = staff; AI allowed = the permission passed. Tools and fields follow the user's permissions, never a contact's grants.
- **AC-6** Lane and agent reads through MCP carry the staff identity from #2048, with a blank contact pair. In-process lane reads check the user's permission at the principal: every such read is listed in the plan with its slug, and a staff member lacking it gets no data.
- **AC-7** `crm_report_ask` and the other contact-only reads have a staff path. The invoiced and unpaid gates (`services/sales/invoiced_sales.py:342,360`) ask both users on it, and the header still cannot widen beyond act-as.
- **AC-8** One daily agent cap and one rate limit per user, across all their threads (default from `system_settings.chatbot_agent_daily_turns`). One turn at a time per thread.

## A live turn that sends nothing

- **AC-9** Nothing goes to WhatsApp or Respond, from the turn or later, by any path: phone gate, staff comment, salesman job, idea status send, low-stock push, file delivery claim, reminder sweep, inbox drain, trace Retry. Each pinned.
- **AC-10** The audit table's decisions hold, each with a test: `ingress = "panel"` is reserved so an API-key caller cannot claim it; no worker offload; no delegated row left open; a duplicate message renders from its row; `dry_run` is false.
- **AC-11** The panel renders `send_message` and `send_attachments`; `assign_conversation`, `add_comment`, `update_contact_fields` are dropped.
- **AC-12** Chat lanes change data as on WhatsApp, as the staff member, and the record says so: an opportunity through the user's own `sales.opportunities.add`, with a real actor. Ideas keep the /ideas link until AGENTIC-IDEATE lands.
- **AC-13** Files that lanes would deliver by the worker go to the user's My Downloads.

## Escalation (owner Q1)

- **AC-14** A panel question that escalates reaches a real person: a round-robin member of the topic's team, sharing the customers' rotation, or the named person. It creates an SLA task with no contact: in their My Pending, with the SLA clock and an in-app notification, and no WhatsApp whatever their toggle says.
- **AC-15** The reply names the person and says they will follow up directly. It never says "they will reply shortly" or "Routed to your PIC", and no assign or comment action goes out. No team to draw from: an honest reply, and no row written.

## Stay out of customers' figures (owner Q2, Q3)

- **AC-16** A panel reply that refers someone adds no Customer asks row.
- **AC-17** Panel turns are not chatbot analytics facts, and do not show in the live and needs-attention lists. Usage is logged with the user's id under panel feature names, in the panel's usage views.

## Thread and page

- **AC-18** The panel's thread list stays the only list: search, deep links, New chat. Agent and lane replies are stored as panel messages. Each thread has its own session and memory, and New chat starts clean. Reopening an old thread continues that thread.
- **AC-19** The current page and record reach the parser, the agent and Jev. A question like "what happened to this stock inquiry" is answered from the page, as today (real case, SI26-0092). With no page context, the parser's input is byte-identical to today (`tests/chatbot/test_parser_user_block_parity.py`). The owner publishes any parser rule.
- **AC-20** Record facts keep #2048's permission and own-scope checks.

## Screen (mock v1)

- **AC-21** Replies render WhatsApp formatting as formatted text: bold, italic, real lists with a hanging indent, links, line breaks, no raw `*` or `_`. Files show with `TurnAttachments`. Clarify and quick replies show as chips.
- **AC-22** Write cards for everyone: before and after, Confirm, Cancel, countdown, Undo, outcome. Routes for confirm, cancel and withdraw are gated by `system.ai_assistant_chat.use`, with the user from the session, never a client-sent contact.
- **AC-23** Pill, steps and trace link only with `system.ai_assistant_settings.view`.
- **AC-24** Usable and non-clipped at 375 and 1280. A failure says so in plain words, no error page.

## Unchanged, each pinned

- **AC-25** Live WhatsApp turns and the console behave as today, including the console's rules on the system role and waiting proposals.
- **AC-26** Panel without the permission: as today, with #2048's reads.

## Measured before default, not before merge

A labelled set of real panel questions run through both paths; "nothing lost" per the card. PR 4's ported tools (complaints, SLA, projects, order analytics, guides, complaint close, order cancel, IT ticket) come first. Until then a question those tools would answer gets an honest "can't yet".

## Known limits

- A panel escalation has the SLA clock and My Pending, but never climbs a tier and refuses a manual escalate: tier climbing goes through the conversation (`/integration/escalate`), which a panel task does not have. Contactless rows leave the runner's list so they cannot starve customers' escalations.
- The chat lane logs an opportunity only when the published parser label carries `OPPORTUNITY_LINE` (UNVERIFIED at prod; `engine.py:6023` says v63 lacks it). Until then staff log one through the agent, with Confirm.

## Hand test

Owner grants the permission to their own role, asks stock, a sales report and a record question on SI26-0092, logs an opportunity, approves a request and undoes it, escalates one question and sees it in the assignee's My Pending.
