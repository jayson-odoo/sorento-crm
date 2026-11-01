# PLAN: Order inquiry emails routed by sales order class (DEALER-PLANNING PR 3)

**Status:** Built, in review. Track M (no migration, no auth change; email recipients touched, so security review runs). Branch `claude/dealer-oi-route-nepe9z` (crew lane DEALER-OI-ROUTE), PR #2078.

Parent plan: `PLAN-dealer-planning-1nov.md` (section "PR 3", card Q4 (a)). UAC: `dealer-oi-route-1nov-acceptance-criteria.md` beside this file.

## Journey

Dealer CS confirms a retail order's lines on Fulfilment Planning. The order inquiry handover email goes To dealer purchasing, Cc project purchasing and the person who raised it. A project order's email goes exactly where it goes today. An undo follows the same rule. The owner edits To and Cc in System Management > Automation and creates the retail row himself; nothing is seeded.

## Measured facts (code read, origin/main 1fc0fab923)

- `dispatch_event` runs every enabled automation of a trigger (`automation_service.py:286`). A match with no `fact_sources` skips the condition filter (`automation_service.py:573`). The handover and undo triggers exposed no facts.
- One commit drains one handover email for every queued line (`_fire_pending_handover`), so a commit touching a retail and a project order mixed both in one email.
- The SO class is `sales_orders.demand_class` (`models/order.py:672`), vocabulary `project | retail | other` (`scm/demand_class.py`). An authored draft with no core SO has none.
- To vs Cc was positional: first resolved address To, everyone else Cc (`notification_tasks.py`, `park_send.render_preview`). The outbox carried a single To (`email_outbox_service.enqueue(to: str)`).
- "Send to purchasing" (resend) picks ONE automation, `park_send.first_automation` (`oi_handover_resend.handover_automation`).

## Card (posted 1 Nov; crew answered Q1 (a), Q2 (b), Q3 (a))

- Q1 (a): a row with no class condition keeps firing for every class; no change on deploy. The guide tells the owner to add "Sales order class is Project" to the old row when he creates the retail one.
- Q2 (b), crew ruling: an existing row keeps "first address To, the rest Cc" until someone re-saves it in the To/Cc picker, so tomorrow's emails go to exactly today's To/Cc. The picker sets `recipient_config.explicit_to_cc` on save; `resolve_recipients` resolves an unmarked row in its old order and marks it `legacy`, and `order_for_email` sends it with one To.
- Q3 (a): an order with no class reads as Project, today's route.

## Build

1. **Class fact.** `scm.demand_class.email_class`: retail/other -> retail, project/none -> project. Fact source `order_inquiry` with one enum fact `order_inquiry.salesOrderClass` (`rule_engine/registry.py`), resolved off the dispatch context. `TriggerSpec.context_facts` marks a trigger whose facts are read off its context; the handover and undo triggers set it, so `dispatch_event` filters each row by its conditions. The automation form's existing RuleBuilder shows the field for these triggers with no FE change.
2. **One email per class.** `handover_item` / saved-line items carry `sales_order_class` (through `_mockup_facts`, which every queue-item builder shares). `_fire_pending_handover` splits the drained lines by class (`handover_class_groups`) and dispatches once per class; `build_handover_email` stamps `context.sales_order_class`. The undo item and context carry it too.
3. **Resend.** `handover_automation(db, sales_order_class)` picks the oldest enabled row whose conditions pass for the OI's class (no condition passes); else the oldest row, as before. `_plan` picks per OI.
4. **Explicit To and Cc.** `recipient_config` gains `cc_user_ids`, `cc_role_ids`, `cc_emails` (schema, normaliser). `resolve_recipients` tags every entry `cc` (To resolved first, so an address on both is To; actor, raiser, requester are Cc). `order_for_email` orders To, Cc, actor last and returns `to_count`, stored on the notification. `notification_tasks._split_to_cc` splits on `to_count` (default 1, every other sender unchanged); `email_outbox_service.enqueue(extra_to=...)` stores every To in `recipients_json.to`; the drainer sends to that list. The resend / reserve preview names every To.
5. **Picker.** `RecipientPicker` renders a To block and a Cc block (users, roles, emails each); the person-on-the-context checkboxes sit in Cc; the detail page lists To and Cc.

## Not changed

- Rows that do not tick "One email" still get one copy per person; To/Cc does not apply to them.
- Reserve emails (`order_inquiry_reserve*`): no class routing (not in the ruling). They pick up explicit Cc only if the owner configures it.

## Tests

`tests/test_oi_route_by_class.py` (28), `RecipientPicker.to_cc.test.tsx` (5). `test_pr_assignee_and_cs_pic_recipient.py` updated for the new `cc` key.
