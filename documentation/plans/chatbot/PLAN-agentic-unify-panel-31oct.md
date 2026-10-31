# PLAN: AGENTIC-UNIFY panel, the staff principal on the chatbot brain

Status: live-turn audit done 31 Oct 2026, waiting on the owner's Q1-Q3 below. PR 3 of 4, after the console PR. Full pipeline, size L.

Behaviour: `CARD-agentic-unify-v2-31oct.md` and its owner table (on branch `crew/agentic-unify`, #2048). Its section 2 (test path) was overruled by the owner: a panel turn is live, with no WhatsApp send. This plan replaces that section.

`A` = `sorento_crm_backend/app`, `S` = `A/services`, `CHAT` = `S/chatbot`.

## Corrections to card v2, from the audit

- **Session:** the card's "console's existing per-run route" is dry-run only (`CHAT/engine.py:4211, 4237, 5005-5006, 8633`). A live panel turn needs a per-thread session store.
- **Daily cap:** a per-thread key caps per thread. Count the user's threads instead (`CHAT/router.py:160-170`).
- **No lane switch override needed:** `chatbot_business_lane_enabled` has no reader in the turn, `chatbot_completed_lanes` reaches only a trace fact (`CHAT/engine.py:5958, 7146`), and `completes_here` is a constant (`:7222`). `_lanes_on()` changes no routing. `offload=False` covers what the panel needs.
- **Escalation has no phantom row today:** with no phone, the assignee read is a 400 before the cursor moves, and the turn fails (`api/v1/external/next_assignee.py:420-425`, `CHAT/engine.py:10604-10629`). The risk appears when someone adds a staff phone to get past it.

## A live panel turn, every switch

Audited 31 rows: keep 8, skip 13, redirect to the user 6, owner decision 4.

| Decision | Behaviour |
| --- | --- |
| **Skip, panel exits first** | Phone gate and staff comment (`CHAT/engine.py:3175-3190`), the top accidental side effect: it would call Respond on the first panel message, before any other gate |
| **Skip** | Inbox queue (guard at `CHAT/inbox_queue.py:226`); worker offload (`offload=False`); session write log (`CHAT/engine.py:12615-12637`); profile facts; salesman job; assign and comment actions; takeover; media quota; trace Retry into live n8n (`api/v1/system/chatbot.py:493`, refuse for panel); ideate state, keeping the /ideas link until AGENTIC-IDEATE lands |
| **Skip, close honestly** | Delegate close: add panel at `CHAT/engine.py:8676`, or a `delegated` row is left with no reply. A non-null `delegate` is a failure |
| **Reserve** | The ingress literal at `CHAT/contracts.py:441-442`, and at `api/v1/external/chat.py:196`, or an API-key caller could claim "panel" |
| **Redirect to the user** | AI gate and scope (`CHAT/engine.py:1072-1117, 3519`); session store; usage logs carry `user_id`; low-stock and sales-analysis files go to My Downloads, never a claim for WhatsApp (`api/v1/scm/low_stock_report.py:672-679`, `api/v1/sales/analysis.py:465-468`); opportunity gate and audit actor (`S/sales/opportunity_chat.py:60-79`); agent eligibility and cap |
| **Keep** | `dry_run` false, pinned; dedup with a unique message id, rendering `duplicate=True` from its row; earlier-message answering, rendering in order; previous reply and Jev state, by thread key; frames; resolver usage; quick replies and `send_attachments` rendered; live trace views, filtered by ingress |
| **Owner, Q1-Q3** | Escalation draw and SLA row; stock ask rows; analytics facts |

`run_turn` executes no action itself; callers do (`CHAT/inbox_queue.py:716-745`). The panel renders `send_message` and `send_attachments`, and drops `assign_conversation`, `add_comment`, `update_contact_fields`.

## Owner questions

**Q1. A staff member's panel question escalates. Who gets it, and how?** It must reach a real person (owner ruling). The draw is a round-robin member of the topic's team, or a named person.
(a) SLA task with no contact: the assignee gets it in My Pending with the SLA clock and an in-app notification (`S/sla_service.py:4406, 4507-4556`), WhatsApp off for this kind. Needs a new branch: `create_tracking` refuses with no contact, though the column is nullable and form rows already have none (`A/models/sla.py:107, 127`).
(b) In-app notification only (`S/notification_service.py:174`): no clock, no task.
(c) IT ticket (`S/ticket_intake_service.py:97-125`): wrong audience for stock or sales.
(d) Email: `S/email_event_registry.py` has no chatbot event.
**Recommend (a):** same clock and task list as customers' escalations, no WhatsApp. The panel's draws share the customers' rotation. The wording "they will reply shortly" (`CHAT/lanes/escalation.py:82`) has no return path to a panel thread, so the reply names the person and says they will follow up directly.

**Q2. Should a panel reply that refers someone create a row on the Customer asks tab?** (`S/stock_ask_service.py:163-165`.) (a) No. (b) Yes, with no contact and no customer.
**Recommend (a):** that tab is customers' asks, and these rows would have neither.

**Q3. Do panel turns count in chatbot analytics?** (`CHAT/analytics/facts.py:84, 116, 363`.) (a) No, they stay in the panel's own usage views. (b) Yes, as an "unknown" audience.
**Recommend (a):** keeps customer figures clean; adding them later is easy.

## Still to count or prove

- In-process lane reads needing a user permission (card v2 section 1).
- A live overridden turn has no test (`tests/chatbot/test_console_switch_override.py:150, 175`); runtime UNVERIFIED.
- `frame_service` and `embedding_worker` on a key with no contact row: UNVERIFIED.
- Slices follow the answers; the page context layer and panel rendering are as in card v2 section 4 and mock v1.
