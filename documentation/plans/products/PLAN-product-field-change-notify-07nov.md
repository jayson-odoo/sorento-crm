# PLAN: product field change notify (shared watched-field notifier + List Price)

Status: Plan (behaviour card posted, awaiting owner answers). Track: TBD (likely full track: migration).

crew-lane: PRODUCT-FIELD-CHANGE-NOTIFY

## Owner ask (7 Nov)
Replicate the discontinued notification for a second product column (list price) through ONE shared
function, configured per field.

## Today (measured)
- Notifier: `sorento_crm_backend/app/services/product_discontinued_notify_service.py`
  (scheduled task `product_discontinued_check`, registered `app/scheduler/task_scheduler.py:830`).
- Level-triggered: products `is_discontinued AND discontinued_notified_at IS NULL`, stamped first
  (`discontinued_notified_at`, `discontinued_notify_batch_id`, `app/models/product.py:363-368`), one
  batch per company, per recipient slice by `user_product_discontinued_scopes` (company, brand).
- Recipients: users with `notify_email_on_product_discontinued` / `notify_whatsapp_on_product_discontinued`
  (`app/models/user.py:91-92`), toggled on the user profile edit dialog.
- Message: count + deep link (`?discontinued_batch_id=`), in-app + email + WhatsApp (`product_discontinued`
  WhatsApp use case, `app/models/respond_template.py:98`).
- Write paths are irrelevant to the trigger (level-triggered on current state), so UI edit, AutoCount
  ingest (`master_ingest_service.py:642`) and Excel import (`product_service.py:2067`) are all covered.

## Design
Pending card answers. See PR comments.
