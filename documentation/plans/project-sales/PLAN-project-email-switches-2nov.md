# PLAN: own email switch per project-sales email + minimum price wording

Status: in review, PR #2089 (small fix track: under ~300 lines, no migration, no RBAC change, no new ingest)

## Journey

The owner wants to stop the "below minimum price" email without also stopping every other
project mail. Today three project-sales notifications have no mapping in
`app/tasks/notification_tasks.py::_NOTIFICATION_TYPE_TO_EVENT_KEY`, so their email lane resolves
to the generic `notification_delivery` event, whose one switch on System Management > Email Event
Configs also governs quotation approved / rejected, changes requested, PO mismatch and reassigned.

## Change

1. Three new event keys, each a map entry plus an `EventDef` in `email_event_registry.py`
   (seeded enabled by `seed_event_configs`, so nothing changes on deploy):
   - `project_price_floor_breach` -> `project_below_minimum_price` (notify_floor_breach)
   - `project_quotation_approval_requested` -> `project_quotation_approval_requested`
   - `project_interest_registered` -> `project_interest_registered`
2. Email only. The in-app bell row, web push, WhatsApp and the approval gate are untouched: the
   switch acts in the outbox drainer (`email_outbox_tasks`, `event_disabled`), after the
   Notification row already exists.
3. Wording: remaining owner-visible "floor" text becomes "minimum price" (Issue refusal in
   `project_quotation_approval_service.py`, `QuotationApprovalPanel.tsx`, `PriceFloorDialog.tsx`).

No migration: `email_event_configs` rows are upserted at startup (`main.py` startup seed) and
lazily by `_resolve_event_config`.

## Tests

`tests/test_project_email_switches.py`: resolution of the three keys, registry entries exist and
default on, each switch off cancels only its own email and keeps the in-app Notification, and the
generic switch off no longer cancels these three.

## Out of scope (crew ruling 2 Nov: possible follow-up)

Admin-only "floor" wording stays for now: the Project Sales Admin > Price Floors screens (menu
entry, page header, "Floor" column, detail page title, back link and toasts) and the
"Set a floor for this product" button on the product page's Minimum price panel.

## Evidence

`evidence-project-email-switches-2nov/`: Email Event Configs at 1280 and 375 showing the three
rows, the below-minimum-price switch turned off, and the minimum price dialog at 1280 and 375.
