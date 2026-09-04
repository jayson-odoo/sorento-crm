# PLAN - Product Discontinued Notification

**Status:** Implemented 2026-06-21 (Phases 1 - 3 complete). BE cron + save-path markers + migration + template wiring; FE toggles + product-list deep-link filter. Tests: 8 pytest + 2 vitest green; Playwright-verified end-to-end. Code review (high effort) passed - no correctness findings. **Pending external dep:** create + approve the `product_discontinued` Respond.io template (WhatsApp out-of-window only; email + in-app work now). **Prod deploy:** run `python -m scripts.seed_product_discontinued_task` after migrating.

> **Superseded in part (2026-08-18)** by [`PLAN-product-discontinued-brand-scope.md`](PLAN-product-discontinued-brand-scope.md):
> the recipient scope below (Q2 "Global", Q9 "recipient = user with >=1 toggle on") is no longer how
> this works. A subscription is now a set of `(company, brand)` scopes, each recipient hears about
> only their subset of a batch, and a user with zero scopes hears nothing. Everything else here -
> the discontinue trigger, stamp-first batching, marker reset, channels and template - still stands.

## Problem

A product is **discontinued** when its `description` starts with `****` (4 asterisks, after `lstrip()`)
→ `Product.is_discontinued = True`. Recomputed on every save (single create/edit + bulk import),
never edited manually (`product_service.py:97 is_discontinued_from_description`).

When products become newly discontinued, notify **subscribed** users (configurable per-user: email
and/or WhatsApp) with the **count** of newly-discontinued products and a **link** to the existing
product list filtered to exactly that batch. Must NOT spam: discontinue 10 → 1 message, not 10.
Must NOT repeat: only notify when there is something **new** since last run.

> Correction to original framing: the trigger flips `is_discontinued`, NOT `is_active`. Threshold is
> **4** asterisks, in the `description` field.

## Resolved decisions (grill-me)

| # | Decision | Choice |
|---|----------|--------|
| Q1 | Who is notified | **Admin-configured per-user subscription** (not the actor) |
| Q2 | Scope | **Global** - every subscriber gets count of ALL newly-discontinued; one count, one link for all |
| Q3 | Timing | **Cron-only, batched-by-window.** Realtime path dropped. Every discontinue just marks the product pending; cron sends ONE message per window covering N products regardless of source (edit vs bulk) |
| Q-revert | Accidental discontinue→revert before cron | Solved by **level-triggered** query (current state, not event log) - reverted product no longer `is_discontinued=True`, so excluded |
| Q4 | Marker reset on re-discontinue | **Clear `notified_at=NULL` on any True→False transition** - a 2nd EOL is a real event, re-notifies |
| Q5/Q11 | Link target | **Stamp `discontinued_notify_batch_id` (UUID/run); link = existing `/master-data/products?discontinued_batch_id=<uuid>`.** No new list view |
| Q6 | Message content | **Uniform count + link, every channel.** No product names (WhatsApp param capped 900 chars by `flatten=True`; bulk always overflows; names live behind link) |
| Q7 | WhatsApp template | New `use_case="product_discontinued"`, MANDATORY approved template (staff are out-of-window). User owns Respond.io approval. Reuse existing SLA-staff RespondContact linkage |
| Q8 | Cron cadence | **Configurable `scheduled_tasks` row, default 15 min.** User retunes; no real-time path |
| Q9 | Channels / recipient | 2 new User bool cols; **recipient = user with ≥1 toggle on**; in-app always-on for recipients; email/WhatsApp per-toggle; **empty batch → nothing** |
| Q10 | Config UI | **Existing User edit form** (alongside other `notify_*` toggles). Fix dual-builder gotcha |
| Q12 | Cron order | **Stamp-first, best-effort per-subscriber fan-out.** "Miss some on hard crash" beats "spam on crash" |

## Send mechanism

Identical to the other 7 notification use cases - `send_text_or_template` (window-aware):
- **In-window** (<23 - 24h since contact's last inbound): render the SAME template with variables, send
  as normal text (message-uniformity, the `16ca8b122` commit).
- **Out-of-window** (the normal case for staff): send the approved Respond.io template with params.

## Data model changes

Migration adds:

**`users`** (per-user subscription, mirror `notify_email_on_assignment` precedent):
- `notify_email_on_product_discontinued BOOL NOT NULL DEFAULT false`
- `notify_whatsapp_on_product_discontinued BOOL NOT NULL DEFAULT false`

**`products`** (notify watermark + batch link):
- `discontinued_notified_at TIMESTAMP NULL`
- `discontinued_notify_batch_id UUID NULL`

**`scheduled_tasks`** (seed row): `key='product_discontinued_check'`, `interval_unit='minutes'`,
`interval_value=15`, `enabled=true`.

**Template default** (seed/admin): `use_case='product_discontinued'`,
`param_mapping={"1":"discontinued_count","2":"discontinued_link"}`. Add `discontinued_count`,
`discontinued_link` to `PARAM_VARIABLES` (`respond_template_service.py`).

## Save-path change (product_service.py)

On every save (create / update / bulk import), after recomputing `is_discontinued`:
- transition **False→True**: leave `discontinued_notified_at = NULL` (becomes cron-eligible).
- transition **True→False**: set `discontinued_notified_at = NULL` AND `discontinued_notify_batch_id = NULL`
  (reset, so a later re-discontinue re-notifies - Q4/A).
- No notification is sent from the save path. Save only marks state.

## Cron handler (`product_discontinued_check`)

Stamp-first, best-effort (Q12/A):
1. `SELECT products WHERE is_discontinued=true AND discontinued_notified_at IS NULL`. Empty → return `{notified:0}` (no message - Q9).
2. Generate `batch_id = uuid4()`. `count = len(rows)`.
3. Stamp all rows `discontinued_notified_at=now`, `discontinued_notify_batch_id=batch_id`. **Commit.**
4. Build absolute **internal** link: `<FRONTEND_BASE_URL>/master-data/products?discontinued_batch_id=<batch_id>`
   (staff link, NOT public token; deep-link-after-login carries it post-signin - `(protected)` layout captures `pathname+search`).
5. Find subscribers: `users WHERE notify_email_on_product_discontinued OR notify_whatsapp_on_product_discontinued`.
6. Per subscriber, **best-effort try/catch** (one failure never aborts the rest):
   ```python
   NotificationService(db).create_with_channel_preferences(
       user_id=u.id, type="product_discontinued",
       title=f"{count} products discontinued",
       body="...",  # count + link, uniform
       data={"whatsapp_use_case": "product_discontinued",
             "whatsapp_context_vars": {"discontinued_count": str(count),
                                       "discontinued_link": link}},
       source_entity_type="product_discontinued_batch",
       source_entity_id=str(batch_id),
       event_type="discontinued",
       send_in_app=True, send_email=True, send_whatsapp=True,
       email_pref_attr="notify_email_on_product_discontinued",
       whatsapp_pref_attr="notify_whatsapp_on_product_discontinued",
   )
   ```
7. Notification idempotency key `(user_id, "product_discontinued_batch", batch_id, "discontinued")`
   makes any future retry of the same batch a no-op.

Handler is an RQ task (`app/tasks/*`) → **worker restart required** after edits.

## FE changes

1. **User edit form** - two toggles in the existing `notify_*` group. Add the two columns to BOTH
   manual `UserResponse(**dict)` builders in `get_user`/`get_me` AND to `UserBase`/`UserResponse`
   (else they render as default-off - known gotcha).
2. **Product list** - `list_query` `products` resource accepts `discontinued_batch_id` exact-match
   filter; list page reads `?discontinued_batch_id=` from URL and applies it.

## Tests (Phase 2 - land here, not deferred)

- **pytest**: cron handler - (a) discontinue→revert-before-tick excluded; (b) re-discontinue after
  reactivation re-notifies; (c) empty batch = no Notification; (d) batch stamps `notified_at`+`batch_id`;
  (e) one subscriber's send failure doesn't abort others; (f) subscriber gating by toggle.
  Save-path: marker reset on True→False. WhatsApp send writes integration_log on 401 (outbox rule).
- **vitest**: user-edit toggles render saved value (regression for the dual-builder gotcha);
  product list applies `discontinued_batch_id` filter param.
- **playwright**: admin ticks toggle on a user → discontinue a product (set desc `****`) → run/trigger
  cron → in-app bell shows "N discontinued" → click link → product grid filtered to the batch.

## Open / external dependencies

- Respond.io template `product_discontinued` must be created + **approved** (manual, user-owned) before
  WhatsApp channel works out-of-window. Email + in-app work without it.
- Confirm staff subscribers have linked RespondContacts (same precondition as `notify_whatsapp_on_assignment`).

## Phasing

- **Phase 1 (FE prototype):** two toggles on user form + product-list batch filter, mock the cron/notification.
- **Phase 2 (BE + tests):** migration, save-path marker, cron handler, template+param vars, list-query filter, wire FE off mocks, all three test suites.
- **Phase 3:** `/code-review`, then PR.
