# UAC - Order inquiry handover email to purchasing (parallel run)

Plan: `PLAN-scm-oi-handover-email.md`. Rulings R1-R10 accepted by the owner in Lavish, 16 Sep 2026
("ok let's have this first and we further improve, go").

## Journey

**Actor:** a customer-service admin (Maryam's team). **Arrives from:** the fulfilment board, an
SO amendment, or the outstanding-book upload, exactly as today. **Decides:** nothing new. She
confirms / amends as she already does. **Holds at the end:** the same order inquiry rows the
system already raises. **Told automatically:** purchasing receives ONE email per write, shaped
like the manual mail she would otherwise have typed (subject `OI: BRW-BB @ SO397450 , SO397460`,
verb headline, SO table, line table with changes struck through in the cell), with herself on Cc.

**Second actor:** the admin who owns the Automation row. Picks recipients (users, roles, extra
addresses) and ticks "Cc the person who raised it". Unticks Enabled when the manual mail is
retired.

**Purchasing:** reads the mail next to the manual one on the same thread and compares. Their own
actions (confirm, reject, link) send nothing.

## Phase 1 (FE mock) - the only FE surface is one checkbox

| id | tag | Given / When / Then |
| --- | --- | --- |
| AC-H16 | [FE] | Given the Automation form's recipient picker, when the admin ticks "Cc the person who raised it", then `recipient_config.include_actor` is `true` in the saved payload, and unticking sets it `false`; the checkbox sits beside the existing "assigned CS PIC" option and round-trips on edit. |

## Phase 2 (BE, test first)

### Trigger and batching

| id | tag | Given / When / Then |
| --- | --- | --- |
| AC-H1 | [BE] | Given one session that raises inquiry rows on two sales orders and commits once, then `AutomationService.dispatch_event("order_inquiry_handover", ...)` is called exactly once, with `handover.orders` holding both SOs and `handover.lines` holding every row raised. |
| AC-H2 | [BE] | Given rows raised with verb ORDER / RESERVE & ORDER / ORDER BACK / PRE-ORDERED / ALREADY INBOUND, then each line has `was = null` and `remark` = the verb label (ORDER BACK appends the cited document; a CS `note` is appended after the verb). |
| AC-H3 | [BE] | Given an existing row settled in place with an earlier delivery date, then the line has `was.delivery_date` = the old date, `delivery_date` = the new one, `remark` = ADVANCE; a later date gives DELAY. |
| AC-H4 | [BE] | Given a settle that lowers qty by N, then `was.qty` = old, `qty` = new, `remark` = `CANCEL BALANCE N NOS`; a settle that raises qty by N gives `remark` = `ORDER N`. |
| AC-H5 | [BE] | Given a settle where need drops to zero (row cancelled), then `qty` = `0`, `was.qty` = the old qty, `remark` = `CANCEL BALANCE <old> NOS`. |
| AC-H6 | [BE] | Given a row raised with verb CHANGE SO NO, then `was.so_number` / `was.customer` / `was.project` = the source order and `so_number` / `customer` / `project` = the target order; `was.qty` and `was.delivery_date` are set only when they differ. |
| AC-H7 | [BE] | Given every line in the write shares one stock location, then `handover.subject_scope` = `<location> @ <SO list>`; mixed or no location gives `<SO list>`. SO list = distinct SO numbers in first-seen order, joined by ` , `. |
| AC-H8 | [BE] | Given purchasing acknowledges, rejects, links (`place_on_po`, `auto_place_for_products`, `link_now`) or unplaces rows, then no `order_inquiry_handover` dispatch happens. |
| AC-H9 | [BE] | Given the order-inquiry sheet importer (`project_order_inquiry_import_service.apply`) raises rows, then no dispatch happens. |
| AC-H10 | [BE] | Given rows are recorded and the session rolls back, then nothing is dispatched and the queue is empty for the next commit. |
| AC-H15 | [BE] | Given a commit, the dispatch runs post-commit on a fresh session (an `EmailOutbox` row exists after the commit; none exists before). A dispatch failure is logged and never raises into the caller. |
| AC-H19 | [BE] | Given a raised row retired by `_retire_uncovered_rows` or `_retire_settled_cancel_balance` (dropped from the buy list on a later confirm / supersede), then the dispatched context holds a line for it with `qty` = `0`, `was.qty` = the old qty, `remark` = `CANCEL BALANCE <old> NOS`. A retire that is replaced in the same commit prints BOTH the cancelled line and the replacement line; the email never pairs them (same rule as R10). |
| AC-H12 | [BE] | `order_inquiry_handover` is registered in the trigger catalog with an empty `config_schema`; the catalog endpoint lists it. |

### Context shape (the template contract)

| id | tag | Given / When / Then |
| --- | --- | --- |
| AC-H17 | [BE] | The dispatched context is `{ "handover": { "subject_scope", "verbs", "headline", "orders": [{so_number, customer, project}], "lines": [{so_date, so_number, customer, project, item_code, qty, delivery_date, remark, was}], "line_count", "link" }, "actor": {name, email}, "today" }`. `verbs` is distinct, in the fixed order ORDER, RESERVE & ORDER, ORDER BACK, PRE-ORDERED, ALREADY INBOUND, ADVANCE, DELAY, CHANGE SO NO, CANCEL BALANCE, RELEASE; `headline` = verbs joined by `, `. Dates are `dd/mm/yyyy`, quantities print without trailing decimals (`_qty_str`). `link` = `build_order_inquiry_link` of the first SO. |
| AC-H18 | [BE] | `actor` = the `actor_user_id` the write seam received (name + email from `users`); when the seam has none it falls back to the inquiry header's `raised_by`; when neither exists `actor` is `null` and `include_actor` adds nothing. |

### Recipients

| id | tag | Given / When / Then |
| --- | --- | --- |
| AC-H11 | [BE] | Given `recipient_config.include_actor = true` and a context with `actor.email`, then `resolve_recipients` includes that address (deduped against users/roles/extra); `false` or a missing actor adds nothing. `_normalize_recipient_config` keeps the key as a bool. |

### Template and seed

| id | tag | Given / When / Then |
| --- | --- | --- |
| AC-H13 | [BE] | The migration seeds `email_templates.code = order_inquiry_handover_default` and one `automations` row (`trigger_type = order_inquiry_handover`, name `Order inquiry to purchasing`, `enabled = true`, `group_matches = false`, `recipient_config = {role_ids: <ids of user_roles whose slug starts with purchasing>, include_actor: true, user_ids: [], extra_emails: []}`), idempotently (re-run creates nothing). Downgrade removes both. |
| AC-H14 | [BE] | Rendering the seeded template with a fixture context yields: subject `OI: <subject_scope>`; HTML with the headline, an SO table (S/O NO, CUSTOMER, PROJECT), a line table (SO DATE, S/O NO, CUSTOMER, PROJECT, ITEM CODE, QTY, DELIVERY DATE, REMARK) where every set `was.*` prints as `<s>old</s> new`; text body prints the same cell as `new (was old)`; the worklist link is present. |

## Out of scope (recorded, not built)

- Workbook attachment (R7). Trigger: purchasing forwards the mail to a supplier and needs the file.
- REPLACE ITEM as one line (R10, slice 2 after go-live): delta pairing rule, amendment may add the
  replacement line, verb + `replaced_item_code`.
- Changes to `order_inquiry_changed_with_links` (R8).
