# PLAN - Complaint structured update template (concise, reduce visual fatigue)

Status: **Phase 2 - backend wired + tests green. Awaiting user: author template in Respond + map default in modal, then live test.**

## Problem (verified in prod, 2026-06-23)

Complaint update WhatsApp/in-chat message reads:

```
Hi Jayson,
There is an update regarding your recent enquiry: CMP2026-0011
Update: There has been an update regarding your complaint for delivery order PS202605-0473: sdaftest
This is a system-generated message.
```

The `Update:` value carries a verbose prefix - "There has been an update regarding your complaint for delivery order PS202605-0473: " - that duplicates the enquiry/DO context already implied, and buries the actual technical response (`sdaftest`). Visual fatigue.

## Target format (stakeholder, 2026-06-23)

Structured block, the technical response (or status change) sits immediately after `Update:`:

```
Hi {{1}},

Project: {{2}}
Customer: {{3}}
Enquiry number: {{4}}
Delivery Order: {{5}}

Update: {{6}}
```

`Update:` = the bare core only:
- reply           → technical response text (`sdaftest`)
- approve/reject  → `Status changed to approved.` (+ ` Reason: ...` on reject)
- resolve/close   → `Status changed to resolved.` (+ ` Note: ...`)
- salesperson notify → `Resolution is identified as <name>.` / `Root cause is identified as <name>.`

## Decisions (locked 2026-06-23)

- **D1 In-window = structured too.** Both in-window (free text, <24h) and out-of-window (template) render the same concise block. Full uniformity, no format jump across the 24h boundary. Reverses the earlier blanket "button template → in-window raw text" rule *for the complaint use_case only*.
- **D2 Complaint only.** PR / stock_inquiry / sponsorship keep the current shared `update` template. Complaint use_case points at its own structured template.
- **D3 Empty field → `-`.** WhatsApp template params can't be empty; blank Project/DO fills as `-` (existing `sanitize_param`). Template lines are fixed in Respond, can't conditionally hide.

## Contract - template body (authored in Respond.io by user)

Body text (exact, `{{n}}` order is the param→var mapping):

```
Hi {{1}},

Project: {{2}}
Customer: {{3}}
Enquiry number: {{4}}
Delivery Order: {{5}}

Update: {{6}}

This is a system-generated message.
```

Dynamic URL button: `https://fe-sorento.foundryx.my/{{1}}`, text "Click to View".

Param mapping (set in WhatsApp Templates → set-default modal for `complaint`):

| slot | var |
|------|-----|
| 1 | contact_name |
| 2 | project |
| 3 | customer |
| 4 | entity_number |
| 5 | delivery_order |
| 6 | update |
| button_url | portal_url |

## Backend changes

1. **`build_context_vars` (respond_messaging_service.py), complaint branch** - add discrete vars from the row:
   - `project` = `project_title`
   - `customer` = `customer_name`
   - `delivery_order` = `delivery_order_number`
   (`entity_number` = complaint_number, `status` already present.)

2. **Thread `extra_context_vars` through the complaint send chain** (the action-specific `update` core + the explicit `portal_url` cannot be reconstructed from the row alone - a reply vs a status-change send touch the same row):
   - `complaints_service._send_respond_message_for_complaint(..., extra_context_vars=None)`
   - `complaints_service._enqueue_respond_message_for_complaint(..., extra_context_vars=None)` → into the job args
   - `respond_io_tasks.send_complaint_respond_message(..., extra_context_vars=None)` → into `_send_and_log`

3. **4 builders** compute the bare `update` core + pass `extra_context_vars={"update": core, "portal_url": view_url}`:
   - reply (~1182), decide (~1375), finalize (~1566), notify-salesperson (~1862).
   - Keep `display_message` (verbose sentence) as the chat-mirror / fallback text when no template configured.

4. **`render_in_window_text`** - for `use_case == "complaint"`, render the filled structured body (`render_filled_body`) + append `portal_url` (free text has no button so the link must be inline), instead of returning raw fallback. Other button templates (OTP) keep the skip.

5. **Config** - point `respond_template_defaults['complaint']` at the structured template with the mapping above (done via modal, or seed).

## Tests (Phase 2)

- pytest: `build_context_vars` complaint populates project/customer/delivery_order. Each builder threads the right `update` core. `send_template_for_use_case` for complaint emits 6 params + button suffix, no `" | "`, link not duplicated. `render_in_window_text` returns structured block + link for complaint.
- Existing `test_respond_templates.py` / `test_respond_inwindow_template.py` stay green.

## Rollout

User authors the template body in Respond (contract above) → resync → set complaint default + mapping in modal → live test (in-window + out-of-window).
