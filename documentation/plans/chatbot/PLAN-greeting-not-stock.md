# PLAN: greeting-not-stock

Status: Plan (small fix track: no migration, no auth/RBAC change, no new ingest surface)

## Bug

A bare greeting ("Hi") from a contact with a remembered usual product was sometimes parsed into a
stock ask for that product. The remembered product reaches the parser as context, and the parser
(Gemini flash-lite for staff-tagged contacts) occasionally turns the greeting into a business ask.

## Rule

A message with no business content (greeting, thanks, ok, emoji) never becomes a business ask from
remembered context alone. Remembered products may only fill a slot of a message that IS a business
ask (e.g. "eta?" resolves to the remembered product).

## Fix

Deterministic guard in code (no prompt edit). Details in the commit that lands it.

## Tests

- greeting + remembered product -> greeting reply, no stock ask
- "eta?" + remembered product -> that product
