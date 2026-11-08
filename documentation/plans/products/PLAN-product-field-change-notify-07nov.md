# PLAN: product field change notify (shared watched-field notifier + List Price)

Status: Review (reviewer READY after fix round 1; awaiting owner hand test). Track: full (migration `pfcn_0001_list_price_notify`).

crew-lane: PRODUCT-FIELD-CHANGE-NOTIFY. PR #2228.

## Owner ask (7 Nov)
Replicate the discontinued notification for a second product column (list price) through ONE shared
function, configured per field.

## Today (measured, before this lane)
- Notifier: `sorento_crm_backend/app/services/product_discontinued_notify_service.py`
  (scheduled task `product_discontinued_check`, registered `app/scheduler/task_scheduler.py:830`).
- Level-triggered: products `is_discontinued AND discontinued_notified_at IS NULL`, stamped first
  (`discontinued_notified_at`, `discontinued_notify_batch_id`, `app/models/product.py:363-368`), one
  batch per company, each recipient gets their slice by `user_product_discontinued_scopes` (company, brand).
- Recipients: users with `notify_email_on_product_discontinued` / `notify_whatsapp_on_product_discontinued`
  (`app/models/user.py:91-92`), set by an admin on the user profile edit dialog.
- Message: count + deep link (`?discontinued_batch_id=`), in-app + email + WhatsApp (`product_discontinued`
  use case, `app/models/respond_template.py:98`).
- The trigger reads current state, so every write path is covered: UI edit, AutoCount ingest
  (`master_ingest_service.py:642`, raw SQL) and Excel import (`product_service.py:2067`).

## Card answers (owner, 7 Nov 16:15: "2228 yes", all recommendations)
1. Recipients: per-field toggles `notify_email/whatsapp_on_product_list_price`, same company/brand scope rows.
2. Every change, no threshold.
3. One digest per company per run: in-app/email list up to 50 lines + "and N more" + link; WhatsApp count + link.
4. List price only.
5. Channels in-app + email + WhatsApp, new use case `product_list_price_changed`. Source: first answered as
   `products.updated_by`; the reviewer showed the AutoCount push never sets it, so crew decided (7 Nov) the
   audit trail instead: the latest `product` UPDATE audit row that set the reported price after the last report,
   integration -> "AutoCount sync", staff -> name, omitted when no such row (e.g. bulk Excel import).

## Design (as built)
- `app/services/product_watched_field_notify_service.py`: `WatchedField` spec (pending query, snapshot,
  stamp, message builder, prefs, link param, optional prepare) + `run_watched_field_check(db, spec)`. The
  runner is the old discontinued code moved over unchanged (stamp-first, per company, scoped slices,
  best-effort fan-out). Two specs: `DISCONTINUED`, `LIST_PRICE`.
- `product_discontinued_notify_service.py` is now a shim that keeps the names the scheduler and tests import.
- List price watermark: `products.list_price_notified` (+ `_at`, `_batch_id`). Pending =
  `list_price <> list_price_notified`; NULL baseline (a new product) is adopted silently at the start of a run.
  A -> B -> A before the tick reports nothing. Migration backfills the baseline so day one is silent.
- Scheduled task `product_list_price_check` (15 minutes), seeded by the migration.
- Product list filter `list_price_batch_id` (BE query param + FE deep link + banner). A product repriced again
  is re-batched, so an older notification's link can show fewer products than its count (discontinued never
  re-batches). Accepted.
- Stamp writes the price from the pre-commit snapshot (the price the message reported), never a re-read row.

## Respond.io template for the owner (use case `product_list_price_changed`)
Suggested body (utility category):

> Hi {{1}}, list prices changed for {{2}} product(s) on {{3}}. View the list: {{4}}

Map in Settings > WhatsApp templates: {{1}} = Contact name, {{2}} = List price change count,
{{3}} = Today's date, {{4}} = List price change link. Also available: Company name, System URL,
Full update message (the one-line text).

## Out of scope / triggers for later
- A % threshold: build it when the digest proves noisy.
- More watched fields (invoice/cost price): one more spec + a watermark migration each.
