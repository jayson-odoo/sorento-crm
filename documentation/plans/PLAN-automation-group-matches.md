# PLAN - Group multi-match automation emails into one

Status: **Implemented** (2026-06-25) - pytest 7/7, vitest 4/4, tsc + prod build green. Browser verify pending FE restart.

## Problem

The `days_before_promotion_end` automation runs daily and fires one `TriggerMatch`
per active promotion whose `end_date == today + days_before`. `_execute` loops
matches → recipients and sends **one email per (promotion × recipient)**. If 5
promotions expire on the same day, each recipient gets 5 emails. User wants **one
combined email per recipient** listing all expiring promotions.

## Decisions (from user)

1. **Per-automation toggle** - add a "Combine into one email" switch to the
   automation modal, default ON. (Not always-on, not a global setting.)
2. **Rewrite the template to loop** - expose a `promotions` list in the render
   context; the "promo expire" template body uses `{% for p in promotions %}`.
   Keep singular `promotion` = `promotions[0]` for back-compat.

## Scope of grouping

Grouping applies **only** to `trigger_type == "days_before_promotion_end"` (the
only multi-match scheduled trigger). Event-driven triggers (complaint/PR/SF
approved) always produce a single match and use singular-entity templates  - 
their behavior is unchanged regardless of the flag.

## Backend

- **Migration 246** (`down_revision = 245_coverage_redirect_assignments`): add
  `automations.group_matches BOOLEAN NOT NULL DEFAULT true`. Existing promo
  automations become grouped (desired).
- **Model** `app/models/automation.py`: add the column.
- **Schema** `app/schemas/automation.py`: `group_matches: bool = True` on
  `AutomationBase`; `Optional[bool]` on `AutomationUpdate`; field on
  `AutomationResponse`.
- **Service** `automation_service.py`:
  - `create`/`update` persist `group_matches`.
  - `_execute`: when `group_matches` AND trigger is the promotion trigger, bucket
    matches by recipient (recipients still resolved per-promo so per-promo
    owner/CS-PIC entitlement is respected), then render **once per recipient** with
    `{ promotions: [...], promotion: promotions[0], promotions_count, today,
    recipient }` and enqueue one email. `event_type` keyed on
    `recipient:{email}:source:promotion_group:id:{run.id}` for idempotency.
  - Non-grouped path unchanged.
- **Template catalog** `email_template_service.py`: document the `promotions` list
  + `promotions_count` variables.
- Rewrite the user's "promo expire" `EmailTemplate.body_html` to loop.

## Frontend

- `automation.types.ts`: add `group_matches` to `Automation` + `AutomationCreateBody`.
- `AutomationForm.tsx`: `groupIntoOne` state (default true), a Switch shown only
  for the promotion trigger, hydrate on edit, include `group_matches` in payload.

## Tests

- pytest: grouped run sends one email per recipient with all promos in context;
  flag-off preserves one-per-promo; per-promo owner entitlement respected.
- vitest: toggle renders for promo trigger, hidden otherwise, included in payload.

## Verify

Playwright MCP: open modal via sidebar, confirm toggle, run-now a promo automation
with ≥2 same-day expiring promos, confirm a single grouped email per recipient in
Outgoing Mails.
